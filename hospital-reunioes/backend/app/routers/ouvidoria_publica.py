"""Canal aberto da Ouvidoria: formulário público e QR setorial (issue #323).

Sem login. O manifestante registra a Manifestação e recebe o Protocolo na tela;
o caso entra em classificação, sem área definida, para o ouvidor validar
(ADR 0034, decisões 3 e 9).

O cartaz impresso aponta para `<app>/ouvidoria/qr` (que o Next reescreve para
`GET /api/ouvidoria/qr`, aqui), e é o servidor que decide o destino: hoje ele
abre este formulário; quando a Ana entrar no WhatsApp oficial, a mesma URL passa
a oferecer a conversa, sem reimprimir cartaz nenhum.

Endpoint público, sem credencial: rate limit por IP, honeypot, lista fechada de
setores e nada de campo que decida classificação, estado ou sigilo.
"""

import logging
import re
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel, Field, field_validator
from slowapi.util import get_remote_address

from app.config import settings
from app.dependencies import get_supabase_client
from app.limiter import limiter
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ouvidoria", tags=["ouvidoria-publica"])


def chave_do_manifestante(request: Request) -> str:
    """Quem é "o mesmo IP" para o rate limit deste canal.

    A página pública chama a API pelo caminho relativo, então o Next proxia a
    requisição no servidor dele: sem isto, `get_remote_address` devolveria o IP
    do container do frontend para TODO mundo, e o balde de 5 por minuto seria
    do hospital inteiro. Um cartaz em corredor movimentado fecharia o canal na
    sexta pessoa.

    O primeiro salto do `X-Forwarded-For` é o cliente. Ele é falsificável por
    quem bate direto na API, e tudo bem: rate limit aqui é contenção de abuso,
    não fronteira de segurança, e falsificar só evita o próprio limite, em vez
    de derrubar o de todos os outros, que é o estrago de hoje."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    primeiro = encaminhado.split(",")[0].strip()
    if primeiro:
        return primeiro
    return get_remote_address(request)


# O que o manifestante vê depois de enviar: o recibo, e nada do Dossiê que ele
# acabou de entregar. Tupla fechada, no padrão da API da Ana.
_CAMPOS_RECIBO = ("protocolo", "data_abertura", "prazo_resposta", "status")

# Quem classifica é o ouvidor, na validação (ADR 0034, decisão 3). Mas
# categoria, setor e resumo são NOT NULL com CHECK anti-vazio desde a migration
# 063, então o canal aberto entra com marcador explícito de pendente, em vez de
# um palpite que passaria por classificação de verdade na fila.
CATEGORIA_PENDENTE = "A classificar"
SETOR_PENDENTE = "A definir"

# O resumo é a vitrine da fila; o documento é o relato integral.
_LIMITE_RESUMO = 200

# O ponto é o lugar exato do cartaz ("Poltrona 12"), não um endereço: cabe num
# rótulo curto, e o que passar disso é ruído e não entra.
_LIMITE_PONTO = 80

# Caminho da página pública no frontend. Não é `/ouvidoria/...` de propósito:
# aquele espaço é da área logada do ouvidor.
CAMINHO_FORMULARIO = "/manifestacao"

_DETALHE_FALHA = "Não foi possível registrar sua manifestação agora. Tente novamente em instantes."


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
    meio e sem nunca devolver vazio (o banco recusaria)."""
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
        return None
    for linha in result.data or []:
        nome = (linha.get("nome") or "").strip()
        if nome.casefold() == procurado.casefold():
            return nome
    return None


def _ponto_do_cartaz(ponto: str | None) -> str | None:
    limpo = _limpar(ponto)
    return limpo[:_LIMITE_PONTO] if limpo else None


class ManifestacaoPublica(BaseModel):
    """O que o canal aberto aceita. Nada aqui classifica o caso, define área,
    estado ou sigilo: essas decisões são do ouvidor, e campo que não está neste
    modelo simplesmente não chega ao banco."""

    relato: str = Field(max_length=10_000)
    nome: str | None = Field(default=None, max_length=200)
    contato: str | None = Field(default=None, max_length=200)
    anonimo: bool = False
    # Vêm do QR, e valem só depois de passar pela taxonomia.
    setor: str | None = Field(default=None, max_length=200)
    ponto: str | None = Field(default=None, max_length=200)
    # Honeypot: campo escondido no formulário, que pessoa nenhuma preenche.
    assunto_alternativo: str | None = Field(default=None, max_length=200)

    @field_validator("relato")
    @classmethod
    def relato_com_conteudo(cls, valor: str) -> str:
        limpo = _limpar(valor)
        if limpo is None:
            raise ValueError("conte o que aconteceu para registrarmos sua manifestação")
        return limpo

    @field_validator("nome", "contato")
    @classmethod
    def opcional_vazio_e_ausencia(cls, valor: str | None) -> str | None:
        return _limpar(valor)


@router.get("/qr")
@limiter.limit("60/minute", key_func=chave_do_manifestante)
async def abrir_pelo_qr(
    request: Request,
    setor: str | None = Query(default=None, max_length=200),
    ponto: str | None = Query(default=None, max_length=200),
    supabase=Depends(get_supabase_client),
):
    """Destino do QR setorial: manda ao formulário, pré-preenchido quando o
    setor do cartaz existe na taxonomia.

    O redirect é temporário de propósito: o navegador não guarda o destino, e o
    dia em que ele mudar (a conversa da Ana no WhatsApp oficial) o cartaz que já
    está na parede muda junto."""
    destino = f"{settings.frontend_url.rstrip('/')}{CAMINHO_FORMULARIO}"
    # O destino sai da configuração do servidor; o parâmetro só escolhe o
    # pré-preenchimento. Não há caminho por onde o QR aponte para fora do app.
    resolvido = _setor_da_taxonomia(supabase, setor)
    if resolvido:
        parametros = {"setor": resolvido}
        do_cartaz = _ponto_do_cartaz(ponto)
        if do_cartaz:
            parametros["ponto"] = do_cartaz
        destino = f"{destino}?{urlencode(parametros)}"
    return RedirectResponse(destino, status_code=status.HTTP_302_FOUND)


@router.post("/publico/manifestacoes", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute", key_func=chave_do_manifestante)
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

    # Canal QR só quando o setor do cartaz é de verdade: é o único sinal de que
    # a pessoa veio de um ponto físico, e ponto sem setor não prova nada.
    origem = _setor_da_taxonomia(supabase, manifestacao.setor)
    if manifestacao.setor and not origem:
        # A origem do cartaz se perdeu. Vale registro: pode ser cartaz com setor
        # que saiu da taxonomia (ou o banco fora do ar na hora da consulta), e o
        # caso vai entrar como se tivesse vindo do site.
        logger.warning("Origem de QR descartada: setor fora da taxonomia ou indisponível")
    ponto = _ponto_do_cartaz(manifestacao.ponto) if origem else None

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
    return {campo: row.get(campo) for campo in _CAMPOS_RECIBO}
