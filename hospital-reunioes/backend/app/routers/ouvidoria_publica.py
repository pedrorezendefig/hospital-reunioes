"""Canal aberto da Ouvidoria: formulário público e QR setorial (issue #323).

Sem login. O manifestante registra a Manifestação e recebe o Protocolo na tela;
o caso entra em classificação, sem área definida, para o ouvidor validar
(ADR 0034, decisões 3 e 9).

O cartaz impresso aponta para `<app>/ouvidoria/qr` (que o Next reescreve para
`GET /api/ouvidoria/qr`, aqui), e é o servidor que decide o destino: hoje ele
abre este formulário; quando a Ana entrar no WhatsApp oficial, a mesma URL passa
a oferecer a conversa, sem reimprimir cartaz nenhum.

Endpoint público, sem credencial: rate limit por IP, honeypot, lista fechada de
setores e nada de campo que decida classificação, estado ou sigilo. O caso nasce
sigiloso (fail-closed), e quem abaixa é o ouvidor ao classificar.
"""

import logging
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, field_validator

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.services import ouvidoria_pontos
from app.services.ouvidoria_taxonomia import CATEGORIA_PENDENTE, SETOR_PENDENTE, nasce_sigilosa
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria-publica"])


# O que o manifestante vê depois de enviar: o recibo, e nada do Dossiê que ele
# acabou de entregar. Tupla fechada, no padrão da API da Ana.
_CAMPOS_RECIBO = ("protocolo", "data_abertura", "prazo_resposta", "status")

# Quem classifica é o ouvidor, na validação (ADR 0034, decisão 3). O marcador de
# pendente que este canal grava vive na taxonomia, junto de quem precisa
# reconhecê-lo depois (`CATEGORIA_PENDENTE`, `SETOR_PENDENTE`).

# O resumo é a vitrine da fila; o documento é o relato integral.
_LIMITE_RESUMO = 200

# Caminho da página pública no frontend. Não é `/ouvidoria/...` de propósito:
# aquele espaço é da área logada do ouvidor.
CAMINHO_FORMULARIO = "/manifestacao"

_DETALHE_FALHA = "Não foi possível registrar sua manifestação agora. Tente novamente em instantes."

# Quem assina o primeiro movimento do caso que veio pelo canal aberto. Não há
# participante logado aqui: `autor_id` fica nulo e o rótulo diz de onde veio.
AUTOR_CANAL_ABERTO = "Canal aberto"


def _limpar(valor: str | None) -> str | None:
    """Vazio é ausência, não conteúdo: espaço em branco (ou travessão sozinho,
    que a sanitização deixa em pontuação) entra como NULL, em vez de fazer o
    Dossiê parecer preenchido."""
    if valor is None:
        return None
    valor = sanitizar_travessao(valor).strip()
    return valor if re.search(r"\w", valor) else None


def _resumir(relato: str) -> str:
    """Primeira linha do relato para o índice do ouvidor, sem cortar palavra ao
    meio e sem nunca devolver vazio (o banco recusaria).

    O resumo é vitrine: aparece nas telas do hospital, então vale a tipografia
    da casa (ADR 0013). O relato integral, esse fica como a pessoa escreveu."""
    relato = sanitizar_travessao(relato).strip()
    if len(relato) <= _LIMITE_RESUMO:
        return relato
    corte = relato[: _LIMITE_RESUMO - 3]
    espaco = corte.rfind(" ")
    if espaco > 0:
        corte = corte[:espaco]
    return f"{corte}..."


def _setor_da_taxonomia(supabase, setor: str | None) -> str | None:
    """Resolve o setor do cartaz contra os Setores cadastrados e devolve o nome
    canônico, ou None. É a lista fechada que impede o canal aberto de virar
    porta para texto arbitrário na área da manifestação, e é a taxonomia que já
    existe, sem cadastro paralelo."""
    procurado = _limpar(setor)
    if not procurado:
        return None
    # A comparação é em Python de propósito. Empurrar para o PostgREST pediria
    # `ilike` com valor de canal aberto, e ali `%` e `_` são curinga: um `%`
    # sozinho casaria com o primeiro setor da lista. São poucas dezenas de
    # linhas; trazer todas e comparar é mais barato que a armadilha.
    try:
        result = supabase.table("setores").select("nome").eq("ativo", True).execute()
    except APIError as exc:
        logger.warning("Falha ao consultar setores do canal aberto (código %s)", exc.code)
        # Para o canal aberto, falha de leitura e setor inexistente dão no
        # mesmo: o caso entra sem origem, e é melhor que recusar a manifestação
        # de quem está com o formulário aberto. Quem precisa separar os dois
        # (o cadastro do Ponto de escuta, que responde a um humano esperando)
        # usa `taxonomia_disponivel` antes de perguntar.
        return None
    for linha in result.data or []:
        nome = (linha.get("nome") or "").strip()
        if nome.casefold() == procurado.casefold():
            return nome
    return None


def taxonomia_disponivel(supabase) -> bool:
    """A tabela de setores respondeu.

    Existe porque `_setor_da_taxonomia` devolve None nos dois casos, e quem
    cadastra um cartaz precisa saber a diferença: dizer "o setor Recepção não
    existe" com a Recepção lá manda o ouvidor caçar um cadastro que está no
    lugar (issue #378, achado da review)."""
    try:
        supabase.table("setores").select("nome").eq("ativo", True).limit(1).execute()
    except Exception:
        return False
    return True


class ManifestacaoPublica(BaseModel):
    """O que o canal aberto aceita. Nada aqui classifica o caso, define área,
    estado ou sigilo: essas decisões são do ouvidor, e campo que não está neste
    modelo simplesmente não chega ao banco."""

    relato: str = Field(max_length=10_000)
    nome: str | None = Field(default=None, max_length=200)
    contato: str | None = Field(default=None, max_length=200)
    anonimo: bool = False
    # O código do cartaz que a pessoa leu. É a ÚNICA origem aceita desde o
    # ADR 0036 (decisão 10): o setor e o ponto vêm do cadastro, não do cliente,
    # então não sobra texto vindo daqui para virar dado do caso.
    p: str | None = Field(default=None, max_length=16)
    # Honeypot: campo escondido no formulário, que pessoa nenhuma preenche.
    assunto_alternativo: str | None = Field(default=None, max_length=200)

    @field_validator("relato")
    @classmethod
    def relato_com_conteudo(cls, valor: str) -> str:
        """O relato entra cru, travessão incluso: o sanitizador da casa existe
        para tirar marca de IA de texto GERADO (ADR 0013), não para reescrever a
        palavra de quem manifestou, num campo que é o documento do caso. A
        checagem de vazio roda sobre a versão sanitizada (travessão sozinho é
        pontuação, não conteúdo), mas quem é gravado é o texto original."""
        if _limpar(valor) is None:
            raise ValueError("conte o que aconteceu para registrarmos sua manifestação")
        return valor.strip()

    @field_validator("nome", "contato")
    @classmethod
    def opcional_vazio_e_ausencia(cls, valor: str | None) -> str | None:
        return _limpar(valor)


@router.get("/qr")
@limiter.limit("60/minute")
async def abrir_pelo_qr(
    request: Request,
    # Sem teto de tamanho aqui de propósito: um `?p=` comprido faria o FastAPI
    # responder 422, e a decisão 6 diz que este caminho NUNCA devolve página de
    # erro. Quem filtra é `por_codigo`, pelo alfabeto e pelo tamanho exatos,
    # antes de tocar o banco.
    p: str | None = None,
    supabase=Depends(get_supabase_client),
):
    """Destino do QR do cartaz: manda ao formulário, com o código do Ponto de
    escuta quando ele resolve um cartaz ativo.

    Só `?p=` desde o ADR 0036 (decisão 4). O formato antigo
    (`?setor=X&ponto=Y`) foi aposentado: manter as duas portas deixaria aberta a
    brecha do texto arbitrário que o código curto veio fechar, e não há cartaz
    impresso no formato velho para quebrar.

    Código ausente, desconhecido ou de cartaz aposentado cai no formulário
    normal, sem origem, e NUNCA numa página de erro (decisão 6): ninguém parado
    na frente de um cartaz pode ficar sem canal por causa de faxina no cadastro.

    O redirect é temporário de propósito: o navegador não guarda o destino, e o
    dia em que ele mudar (a conversa da Ana no WhatsApp oficial) o cartaz que já
    está na parede muda junto."""
    destino = f"{settings.frontend_url.rstrip('/')}{CAMINHO_FORMULARIO}"
    # O destino sai da configuração do servidor; o parâmetro só escolhe o
    # pré-preenchimento. Não há caminho por onde o QR aponte para fora do app.
    cartaz = ouvidoria_pontos.por_codigo(supabase, p)
    if cartaz:
        destino = f"{destino}?{urlencode({'p': cartaz['codigo']})}"
    return RedirectResponse(destino, status_code=status.HTTP_302_FOUND)


@router.get("/publico/pontos/{codigo}")
@limiter.limit("30/minute")
async def rotulo_do_cartaz(
    request: Request,
    codigo: str,
    supabase=Depends(get_supabase_client),
):
    """De qual cartaz veio quem está com o formulário aberto.

    A página pergunta, em vez de exibir o que estava na URL: é isto que fecha o
    item 9 da #375 em definitivo, porque não sobra texto vindo do cliente para
    renderizar (ADR 0036, decisão 10).

    404 no resto (código desconhecido, cartaz aposentado): a página
    simplesmente não mostra origem nenhuma. Só o que a tela precisa exibir sai
    daqui, e nada do cadastro."""
    cartaz = ouvidoria_pontos.por_codigo(supabase, codigo)
    if not cartaz:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cartaz não encontrado")
    return {"setor": cartaz["setor"], "ponto": cartaz["ponto"]}


@router.post("/publico/manifestacoes", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def registrar_manifestacao_publica(
    request: Request,
    manifestacao: ManifestacaoPublica,
    supabase=Depends(get_supabase_client),
):
    """Registra a manifestação do canal aberto e devolve o protocolo ANO-NNNN."""
    if _limpar(manifestacao.assunto_alternativo):
        logger.warning("Envio do canal aberto recusado pelo honeypot")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não foi possível registrar sua manifestação. Recarregue a página e tente de novo.",
        )

    # O pedido de anonimato vence a identificação que venha junto, por engano do
    # formulário ou de quem monte a requisição na mão.
    nome = None if manifestacao.anonimo else manifestacao.nome
    contato = None if manifestacao.anonimo else manifestacao.contato

    # Canal QR só quando o código resolve um Ponto de escuta ATIVO. Setor e
    # ponto saem do CADASTRO, e é isso que fecha a porta do texto arbitrário: o
    # cliente manda um código de seis caracteres, e nada mais (ADR 0036).
    cartaz = ouvidoria_pontos.por_codigo(supabase, manifestacao.p)
    if manifestacao.p and not cartaz:
        # Vale registro: pode ser cartaz aposentado, código digitado errado ou o
        # banco fora do ar na hora da consulta. O caso entra como se tivesse
        # vindo do site, nunca com origem inventada.
        logger.warning("Origem de QR descartada: código sem Ponto de escuta ativo")
    origem = cartaz["setor"] if cartaz else None
    # Anônimo não grava o ponto do cartaz (issue #375, item 12, decisão 5).
    # Em sala pequena, "Poltrona 12" em tal dia identifica a pessoa cruzando com
    # o registro de atendimento do próprio hospital. O ponto serve para o
    # ouvidor achar o cartaz, e isso não vale o risco de reidentificação. O
    # `canal_setor` fica: é a área inteira, não a poltrona.
    ponto = cartaz["ponto"] if (cartaz and not manifestacao.anonimo) else None

    linha = {
        "categoria": CATEGORIA_PENDENTE,
        # A área responsável é sempre do ouvidor, mesmo vindo do QR: o cartaz diz
        # de ONDE a pessoa leu, não CONTRA QUEM ela reclama. Quem lê o QR da
        # Recepção para reclamar da Farmácia não apontou área nenhuma.
        "setor": SETOR_PENDENTE,
        "resumo": _resumir(manifestacao.relato),
        "relato_integral": manifestacao.relato,
        "manifestante_nome": nome,
        "manifestante_contato": contato,
        "anonimo": manifestacao.anonimo,
        # Anônimo não é caso incompleto: não há o que completar, é escolha de
        # quem manifestou. Identificação pela metade, sim.
        "dados_incompletos": not (manifestacao.anonimo or (nome and contato)),
        # Fail-closed (ADR 0034, decisão 1). O canal aberto entra SEM TIPO, e o
        # índice de quem está fora da Ouvidoria mostra o `resumo`, que é o
        # começo do relato: uma denúncia escrita no QR viraria texto visível na
        # fila de todo mundo até alguém classificar. O ouvidor enxerga e
        # trabalha o caso normalmente (o filtro só vale para quem está fora da
        # Ouvidoria), e é a classificação dele que devolve o caso à fila de
        # todos, pela rota de classificação ou pela validação (issue #372).
        "sigilo_reforcado": nasce_sigilosa(None),
        "canal": "qr" if origem else "site",
        "canal_setor": origem,
        "canal_ponto": ponto,
    }
    try:
        result = supabase.table("ouvidoria_protocolos").insert(linha).execute()
    except APIError as exc:
        # Detalhe do Postgres não vai para um canal aberto; o manifestante vê
        # que não deu e pode tentar de novo.
        logger.error("Falha ao registrar manifestação pública (código %s)", exc.code)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_DETALHE_FALHA) from exc
    if not result.data:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=_DETALHE_FALHA)
    row = result.data[0]
    _abrir_a_trilha(supabase, row, linha["canal"])
    return {campo: row.get(campo) for campo in _CAMPOS_RECIBO}


def _abrir_a_trilha(supabase, row: dict, canal: str) -> None:
    """O primeiro movimento do caso é o nascimento dele (CONTEXT.md).

    O registro manual do ouvidor já abria a trilha; o canal aberto não, e todo
    caso vindo do QR ou do site nascia com `ouvidoria_movimentos` vazio (issue
    #375, item 7). Não há usuário logado aqui: `autor_id` é nullable e o nome é
    o rótulo do canal, não um participante inventado.

    Falha aqui não desfaz o registro, pelo mesmo motivo do registro manual: o
    protocolo já foi dito a quem manifestou. Perder a trilha é ruim, perder a
    manifestação é pior."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": row["id"],
                "estado_anterior": None,
                "estado_novo": row.get("status") or "em_classificacao",
                "autor_id": None,
                "autor_nome": AUTOR_CANAL_ABERTO,
                "observacao": f"Registro pelo canal aberto (canal: {canal})",
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de abertura da manifestação %s", row.get("id"))
