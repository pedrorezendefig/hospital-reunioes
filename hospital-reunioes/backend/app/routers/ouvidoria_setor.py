"""Portal do setor por link tokenizado (issue #326, ADR 0034 decisão 4).

Rotas públicas, sem login: quem chega aqui veio pelo link do email de
acionamento, no padrão do Aceite interno. O token restringe tudo a UMA
manifestação e UM destinatário; a página mostra só o extrato necessário
(escrito pelo ouvidor), nunca o relato cru, e caso sigiloso ou anônimo sai
sem identificação de quem manifestou.
"""

from __future__ import annotations

import datetime as dt
import logging
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from postgrest.exceptions import APIError

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services import ouvidoria_setor_tokens, storage
from app.services.ouvidoria_anexos import AnexoRecusadoError, validar_anexo
from app.services.ouvidoria_notificacoes import _identificacao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria-setor", tags=["ouvidoria-setor"])

# O que o portal pode saber do caso. Fechado campo a campo, como no email
# (`_CAMPOS_DO_EMAIL`): o setor recebe o necessário para resolver, nada além.
_CAMPOS_DO_PORTAL = (
    "id, protocolo, setor, categoria, gravidade, extrato_para_o_setor, "
    "prazo_area_em, status, sigilo_reforcado, anonimo, manifestante_nome, respondida_em"
)

_SEM_EXTRATO = "A Ouvidoria acionou o setor sobre esta manifestação."


def agora_utc() -> dt.datetime:
    """O relógio do módulo, num ponto só (mesmo padrão do painel)."""
    return dt.datetime.now(dt.UTC)


def _carregar_caso(supabase, token: str, agora: dt.datetime) -> tuple[dict, dict]:
    """Valida o token e carrega a manifestação dele. Recusa sem vazar: token
    inválido é 404 seco, e nenhuma recusa diz se o caso existe."""
    try:
        vinculo = ouvidoria_setor_tokens.carregar(supabase, token, agora)
    except ouvidoria_setor_tokens.TokenInvalidoError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link inválido") from None
    except ouvidoria_setor_tokens.TokenUsadoError:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Este link já foi usado: a resposta do setor já entrou"
        ) from None
    except ouvidoria_setor_tokens.TokenExpiradoError:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Este link expirou") from None

    result = (
        supabase.table("ouvidoria_protocolos")
        .select(_CAMPOS_DO_PORTAL)
        .eq("id", vinculo["manifestacao_id"])
        .limit(1)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Link inválido")
    return vinculo, result.data[0]


def _registrar_acesso(supabase, vinculo: dict, acao: str) -> None:
    """Todo acesso ao caso deixa registro (LGPD, ADR 0034). Best-effort: o log
    não derruba a página do titular."""
    try:
        supabase.table("ouvidoria_acessos").insert(
            {
                "manifestacao_id": vinculo["manifestacao_id"],
                "ator_id": None,
                "ator_nome": f"{vinculo['destinatario_nome']} (portal do setor)",
                "acao": acao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao registrar acesso do portal do setor à manifestação %s", vinculo["manifestacao_id"])


@router.get("/{token}")
@limiter.limit("30/minute")
async def abrir_portal(
    request: Request,
    token: str,
    supabase=Depends(get_supabase_client),
):
    """O que o titular vê ao abrir o link do email: extrato, prazo e se o caso
    ainda aceita resposta."""
    from app.routers.ouvidoria import _projetar_prazo, carregar_feriados

    agora = agora_utc()
    vinculo, caso = _carregar_caso(supabase, token, agora)
    _registrar_acesso(supabase, vinculo, "portal_setor_abrir")

    prazo = _projetar_prazo(caso, agora, carregar_feriados(supabase))
    return {
        "protocolo": caso.get("protocolo"),
        "setor": caso.get("setor"),
        "categoria": caso.get("categoria"),
        "gravidade": caso.get("gravidade"),
        "extrato": (caso.get("extrato_para_o_setor") or "").strip() or _SEM_EXTRATO,
        "identificacao": _identificacao(caso),
        "sigiloso": bool(caso.get("sigilo_reforcado")),
        "destinatario_nome": vinculo["destinatario_nome"],
        "aceita_resposta": caso.get("status") == "aguardando_area",
        **prazo,
    }


@router.post("/{token}/responder")
@limiter.limit("10/minute")
async def responder(
    request: Request,
    token: str,
    resposta: str = Form(...),
    arquivos: list[UploadFile] = File(default=[]),
    supabase=Depends(get_supabase_client),
):
    """A resposta da área: o que foi FEITO para corrigir. Grava o marco T2,
    leva o caso para "respondido" e registra o movimento, tudo pela mesma
    máquina de estados do painel (RPC `ouvidoria_transicionar`).

    O token é de uso único, com claim atômico: a segunda tentativa pelo mesmo
    link não duplica resposta nem quebra o estado (critério 6)."""
    agora = agora_utc()
    vinculo, caso = _carregar_caso(supabase, token, agora)

    texto = resposta.strip()
    if not texto:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Escreva o que o setor fez para corrigir: a resposta não pode ficar em branco",
        )
    if caso.get("status") != "aguardando_area":
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="A Ouvidoria já movimentou este caso e ele não aceita mais resposta por este link",
        )

    # Os anexos passam pelas MESMAS regras do registro manual (issue #321), e a
    # validação vem toda ANTES do claim do token: arquivo recusado não queima o
    # link do titular, ele troca o arquivo e envia de novo.
    from app.routers.ouvidoria import _recusa_de_anexo

    validados: list[tuple[str, str, str, bytes]] = []
    for arquivo in arquivos:
        try:
            extensao, content_type = validar_anexo(arquivo.filename or "", arquivo.size or 0)
        except AnexoRecusadoError as exc:
            raise _recusa_de_anexo(exc) from exc
        conteudo = await arquivo.read()
        # O tamanho real manda: o Content-Length é do cliente.
        try:
            validar_anexo(arquivo.filename or "", len(conteudo))
        except AnexoRecusadoError as exc:
            raise _recusa_de_anexo(exc) from exc
        validados.append((arquivo.filename or "anexo", extensao, content_type, conteudo))

    if not ouvidoria_setor_tokens.consumir(supabase, vinculo, agora):
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Este link já foi usado: a resposta do setor já entrou"
        )

    try:
        supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": vinculo["manifestacao_id"],
                "p_estado_novo": "respondido",
                "p_autor_id": None,
                "p_autor_nome": vinculo["destinatario_nome"],
                "p_observacao": "Resposta da área pelo portal do setor",
            },
        ).execute()
    except APIError as exc:
        # A regra do banco recusou (corrida com outra transição) ou a RPC
        # falhou: o claim volta, para o titular poder tentar de novo.
        ouvidoria_setor_tokens.devolver(supabase, vinculo)
        if exc.code == "23514":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A Ouvidoria movimentou o caso agora mesmo: recarregue a página",
            ) from exc
        logger.error("Erro na RPC ouvidoria_transicionar pelo portal do setor (código %s)", exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar a resposta agora. Tente de novo.",
        ) from exc

    # O marco T2 e a resposta ficam no caso. Falha aqui não desfaz a transição
    # (o movimento é a fonte da verdade do ato); fica no log para conferência.
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update(
                {
                    "respondida_em": agora.isoformat(),
                    "resposta_da_area": texto,
                    "respondida_por_nome": vinculo["destinatario_nome"],
                }
            )
            .eq("id", vinculo["manifestacao_id"])
            .execute()
        )
    except APIError:
        logger.error("Falha ao carimbar o T2 da manifestação %s", vinculo["manifestacao_id"])

    # A resposta já entrou; os anexos são best-effort a partir daqui, no mesmo
    # desenho do registro manual: caminho sorteado, binário no bucket privado,
    # só metadados no banco, e sem linha órfã apontando para o vazio.
    anexos_gravados = 0
    for filename, extensao, content_type, conteudo in validados:
        path = f"manifestacao-{vinculo['manifestacao_id']}/{uuid.uuid4().hex}{extensao}"
        if not storage.upload_private(
            supabase,
            bucket=settings.supabase_storage_bucket_anexos_ouvidoria,
            path=path,
            content=conteudo,
            content_type=content_type,
        ):
            logger.error("Falha ao subir o anexo %s da resposta do setor (%s)", filename, vinculo["manifestacao_id"])
            continue
        try:
            (
                supabase.table("ouvidoria_anexos")
                .insert(
                    {
                        "manifestacao_id": vinculo["manifestacao_id"],
                        "filename": filename,
                        "content_type": content_type,
                        "tamanho_bytes": len(conteudo),
                        "storage_path": path,
                        "enviado_por": None,
                        "enviado_por_nome": vinculo["destinatario_nome"],
                    }
                )
                .execute()
            )
            anexos_gravados += 1
        except APIError:
            storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, path)
            logger.error(
                "Falha ao registrar o anexo %s da resposta do setor (%s)", filename, vinculo["manifestacao_id"]
            )

    _registrar_acesso(supabase, vinculo, "portal_setor_responder")
    return {
        "protocolo": caso.get("protocolo"),
        "respondida_em": agora.isoformat(),
        "anexos_gravados": anexos_gravados,
    }
