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
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services import (
    ouvidoria_notificacoes,
    ouvidoria_prorrogacao,
    ouvidoria_respostas,
    ouvidoria_setor_tokens,
    storage,
)
from app.services.ouvidoria_anexos import AnexoRecusadoError, validar_anexo
from app.services.ouvidoria_notificacoes import _identificacao
from app.services.ouvidoria_prazos import TETO_PRORROGACAO_DIAS_UTEIS, vencimento_prorrogado
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria-setor", tags=["ouvidoria-setor"])

# O que o portal pode saber do caso. Fechado campo a campo, como no email
# (`_CAMPOS_DO_EMAIL`): o setor recebe o necessário para resolver, nada além.
# `contato_em` e `data_abertura` entram por causa do teto da prorrogação, que
# conta da entrada da manifestação; nenhum dos dois vai para a resposta.
_CAMPOS_DO_PORTAL = (
    "id, protocolo, setor, categoria, gravidade, extrato_para_o_setor, "
    "prazo_area_em, status, sigilo_reforcado, anonimo, manifestante_nome, "
    # `area_estourou_em` entra porque o portal projeta o prazo com a MESMA
    # função do painel: sem a coluna, as duas APIs diriam `cumprimento`
    # diferente para o mesmo caso devolvido (issue #374).
    "contato_em, data_abertura, respondida_em, area_estourou_em"
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


def _limpar_t2(supabase, vinculo: dict) -> None:
    """Desfaz o carimbo T2 quando a transição não entrou. Best-effort: sobrar
    carimbo num caso ainda aguardando área é inofensivo (a próxima resposta
    sobrescreve), e o claim devolvido é o que importa."""
    try:
        (
            supabase.table("ouvidoria_protocolos")
            .update({"respondida_em": None, "resposta_da_area": None, "respondida_por_nome": None})
            .eq("id", vinculo["manifestacao_id"])
            .execute()
        )
    except APIError:
        logger.warning("Falha ao limpar o T2 da manifestação %s", vinculo["manifestacao_id"])


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
    from app.routers.ouvidoria import _projetar_prazo, carregar_feriados_ou_degradado

    agora = agora_utc()
    vinculo, caso = _carregar_caso(supabase, token, agora)
    _registrar_acesso(supabase, vinculo, "portal_setor_abrir")

    # O calendário que não pôde ser lido viaja na resposta (issue #449): esta
    # página afirma "vence em N dias úteis" para quem tem que responder, e sem a
    # marca ela afirmava isso com um calendário vazio por falha de leitura.
    feriados, degradado = carregar_feriados_ou_degradado(supabase)
    prazo = _projetar_prazo(caso, agora, feriados)
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
        # As regras da prorrogação ficam visíveis mesmo quando o pedido não
        # cabe mais (PRD #318, história 2): quem lê precisa saber que o
        # recurso existe e por que não está disponível.
        "prorrogacao": ouvidoria_prorrogacao.resumo_para_o_portal(
            caso, ouvidoria_prorrogacao.carregar_pedido(supabase, vinculo["manifestacao_id"]), agora
        ),
        "degradado": degradado,
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

    # A regra do que vale como resposta vive inteira no serviço, e recebe o
    # texto CRU: é lá que "espaço em volta não conta" é decidido, num lugar só.
    recusa = ouvidoria_respostas.motivo_de_recusa(resposta)
    if recusa:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=recusa)
    texto = resposta.strip()
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

    # O texto da área e o marco T2 entram ANTES da transição: sem transação
    # entre as duas escritas, a ordem decide o que se perde numa falha. Assim,
    # falha aqui devolve o claim e nada mudou; falha na RPC limpa o carimbo. O
    # caso nunca vira "respondido" sem a resposta gravada.
    carimbo_t2 = {
        "respondida_em": agora.isoformat(),
        "resposta_da_area": texto,
        "respondida_por_nome": vinculo["destinatario_nome"],
    }
    try:
        supabase.table("ouvidoria_protocolos").update(carimbo_t2).eq("id", vinculo["manifestacao_id"]).execute()
    except APIError as exc:
        ouvidoria_setor_tokens.devolver(supabase, vinculo)
        logger.error("Falha ao carimbar o T2 da manifestação %s", vinculo["manifestacao_id"])
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar a resposta agora. Tente de novo.",
        ) from exc

    try:
        supabase.rpc(
            "ouvidoria_transicionar",
            {
                "p_manifestacao_id": vinculo["manifestacao_id"],
                "p_estado_novo": "respondido",
                "p_autor_id": None,
                "p_autor_nome": vinculo["destinatario_nome"],
                # O TEXTO viaja junto: a coluna `resposta_da_area` guarda só
                # a resposta corrente, e o portal a sobrescreve no ciclo
                # seguinte. É este movimento que faz a resposta devolvida
                # sobreviver à resposta que veio depois (issue #374).
                "p_observacao": ouvidoria_respostas.observacao_da_resposta(texto),
            },
        ).execute()
    except APIError as exc:
        # A regra do banco recusou (corrida com outra transição) ou a RPC
        # falhou: o carimbo sai e o claim volta, para o titular tentar de novo.
        _limpar_t2(supabase, vinculo)
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
            # Mesma limpeza do anexo da manifestação: sem a linha, o binário
            # fica órfão. Se nem a limpeza der certo, o caminho vai para o log.
            if not storage.delete_file(supabase, settings.supabase_storage_bucket_anexos_ouvidoria, path):
                logger.error("Anexo órfão no bucket após falha de registro: %s", path)
            logger.error(
                "Falha ao registrar o anexo %s da resposta do setor (%s)", filename, vinculo["manifestacao_id"]
            )

    _registrar_acesso(supabase, vinculo, "portal_setor_responder")
    return {
        "protocolo": caso.get("protocolo"),
        "respondida_em": agora.isoformat(),
        "anexos_gravados": anexos_gravados,
    }


class PedidoDeProrrogacao(BaseModel):
    """O que a área manda para pedir mais prazo. A justificativa é obrigatória:
    é ela que a Ouvidoria lê para decidir."""

    justificativa: str
    dias_uteis: int = Field(ge=1, le=ouvidoria_prorrogacao.MAX_DIAS_UTEIS_PEDIDOS)

    @field_validator("justificativa")
    @classmethod
    def _justificativa_nao_vazia(cls, valor: str) -> str:
        valor = sanitizar_travessao(valor).strip()
        if not valor:
            raise ValueError("a justificativa da prorrogação não pode ficar em branco")
        return valor


def _avisar_a_ouvidoria(supabase, manifestacao_id: str, gravidade: str | None, agora, feriados) -> None:
    """O pedido chega a quem decide. Melhor esforço no envio, nunca no
    registro: a notificação nasce como linha (é o que prova o aviso e é o que
    o ouvidor reenvia), e o email pode sair depois pelo job da fila.

    Só quem está ATIVO, pelo mesmo motivo de `ler_diretoria_executiva`
    (issue #403): o assunto deste email leva o número do protocolo e o corpo
    leva o setor, e o desligamento do hospital é soft delete que não limpa
    `perfil_ouvidoria`."""
    from app.routers.ouvidoria import PERFIS_OUVIDORIA

    try:
        result = (
            supabase.table("participantes")
            .select("id, nome_completo, email, perfil_ouvidoria")
            .in_("perfil_ouvidoria", list(PERFIS_OUVIDORIA))
            .eq("ativo", True)
            .execute()
        )
        destinos = [d for d in (result.data or []) if (d.get("email") or "").strip()]
    except Exception:
        logger.error("Falha ao buscar a Ouvidoria para avisar do pedido de prorrogação de %s", manifestacao_id)
        return
    if not destinos:
        logger.error("Pedido de prorrogação em %s sem ninguém da Ouvidoria com email", manifestacao_id)
        return

    for pessoa in destinos:
        aviso = ouvidoria_notificacoes.registrar(
            supabase,
            manifestacao_id=manifestacao_id,
            gatilho=ouvidoria_notificacoes.GATILHO_PRORROGACAO_SOLICITADA,
            destinatario_nome=pessoa.get("nome_completo") or pessoa["email"],
            destinatario_email=pessoa["email"],
            papel_destinatario=pessoa.get("perfil_ouvidoria"),
            enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, gravidade, feriados),
        )
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, aviso, agora, feriados)


@router.post("/{token}/prorrogacao", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def pedir_prorrogacao(
    request: Request,
    token: str,
    pedido: PedidoDeProrrogacao,
    supabase=Depends(get_supabase_client),
):
    """O pedido de mais prazo, feito pelo próprio link do email (issue #333).

    As três regras da casa valem aqui, e o sistema as aplica sozinho: uma vez
    só, antes do vencimento, com justificativa. O teto de 30 dias úteis da
    entrada é do motor, que devolve o prazo novo já cortado nele.

    O token NÃO é consumido: quem pede prorrogação ainda precisa do mesmo link
    para responder depois."""
    from app.routers.ouvidoria import carregar_feriados

    agora = agora_utc()
    vinculo, caso = _carregar_caso(supabase, token, agora)

    anterior = ouvidoria_prorrogacao.carregar_pedido(supabase, vinculo["manifestacao_id"])
    motivo = ouvidoria_prorrogacao.motivo_de_recusa(caso, anterior, agora)
    if motivo:
        # Recusa automática: 409 porque o estado do caso é que fecha a porta,
        # não o que o setor digitou.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=motivo)

    entrada = ouvidoria_prorrogacao.entrada_da_manifestacao(caso)
    if entrada is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Esta manifestação não tem data de entrada registrada, então o teto da prorrogação não é calculável."
            ),
        )
    feriados = carregar_feriados(supabase)
    prazo_atual = dt.datetime.fromisoformat(str(caso["prazo_area_em"]))
    prazo_novo = vencimento_prorrogado(entrada, prazo_atual, pedido.dias_uteis, feriados)
    if prazo_novo is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "O prazo desta manifestação já alcançou o teto de "
                f"{TETO_PRORROGACAO_DIAS_UTEIS} dias úteis da entrada. Não há prorrogação possível."
            ),
        )

    try:
        criado = (
            supabase.table("ouvidoria_prorrogacoes")
            .insert(
                {
                    "manifestacao_id": vinculo["manifestacao_id"],
                    "justificativa": pedido.justificativa,
                    "dias_uteis_pedidos": pedido.dias_uteis,
                    "prazo_anterior": prazo_atual.isoformat(),
                    "prazo_novo": prazo_novo.isoformat(),
                    "status": ouvidoria_prorrogacao.PENDENTE,
                    "solicitada_em": agora.isoformat(),
                    "solicitante_nome": vinculo["destinatario_nome"],
                    "solicitante_email": vinculo["destinatario_email"],
                }
            )
            .execute()
        )
    except APIError as exc:
        # O índice único da migration 073 é a mesma regra do "uma vez só",
        # aplicada no banco: corrida entre dois cliques vira recusa, não 500.
        if exc.code == "23505":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Esta manifestação já teve um pedido de prorrogação. A regra permite apenas um.",
            ) from exc
        logger.error("Falha ao gravar o pedido de prorrogação de %s (código %s)", vinculo["manifestacao_id"], exc.code)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar o pedido agora. Tente de novo.",
        ) from exc
    if not criado.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível registrar o pedido agora. Tente de novo.",
        )

    ouvidoria_prorrogacao.registrar_movimento(
        supabase,
        vinculo["manifestacao_id"],
        autor_id=None,
        autor_nome=vinculo["destinatario_nome"],
        observacao=(
            f"Prorrogação solicitada pelo setor: {pedido.dias_uteis} dia(s) útil(eis). "
            f"Justificativa: {pedido.justificativa}"
        ),
    )
    _avisar_a_ouvidoria(supabase, vinculo["manifestacao_id"], caso.get("gravidade"), agora, feriados)
    _registrar_acesso(supabase, vinculo, "portal_setor_pedir_prorrogacao")

    linha = criado.data[0]
    return {
        "protocolo": caso.get("protocolo"),
        "prorrogacao": {campo: linha.get(campo) for campo in ouvidoria_prorrogacao.CAMPOS_PRORROGACAO_TUPLA},
    }
