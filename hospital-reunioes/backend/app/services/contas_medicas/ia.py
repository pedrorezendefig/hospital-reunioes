"""O adaptador de IA de Contas médicas (issue #1130, PRD #1128).

A única porta do módulo para a IA, pelo SDK oficial da Anthropic (issue #1302).
Nove chamadas:

- `extrair_eventos`: o passo A, que lê o prontuário e lista os eventos
  (Anexo A da spec);
- `comparar_conta`: o passo B, que compara a conta com a memória da operadora
  e devolve as linhas do Guia (Anexo B, com o "se necessário" do adendo v1.1);
- `chamada_curta`: a pergunta curta do dicionário e das observações, com o
  schema que quem chama escolhe;
- `propor_regra`: a regra nova que a pessoa escreveu em linguagem comum, no
  formato da memória da operadora (issue #1141);
- `explicar_faltou_isto`: o Auditor na conversa da Conta, que explica o
  Faltou isto do Guia e classifica a origem (issue #1489);
- `propor_lote` e `corrigir_item`: o Auditor na conversa da Operadora, que
  devolve o lote de propostas e refaz um item dele (issue #1490);
- `revisar_pendentes` e `corrigir_pendente`: o "revisar pendentes" da mesma
  conversa, que decide cada Regra pendente e refaz uma decisão (issue #1494).

Toda chamada sai igual: saída estruturada estrita (`output_config.format` com
`json_schema`), a instrução e a memória em bloco de cache, e a resposta
validada pelo Pydantic. A API da Anthropic guarda a requisição por até 30 dias
e não usa o texto para treino, sem ZDR (ADR 0074, issue #1302). O custo é calculado aqui, pelos tokens da
resposta e pela tabela de preço, porque a Anthropic não devolve o custo pronto.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from time import perf_counter
from typing import Annotated, Any, Literal

import anthropic
import httpx2
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError, WithJsonSchema

from app.config import settings
from app.services.prompt_loader import load_prompt

__all__ = [
    "DiagnosticoDoFaltouIsto",
    "ErroDaIA",
    "IASemCredito",
    "EventosDoProntuario",
    "DecisaoDaPendente",
    "ItemCorrigido",
    "LinhasDaComparacao",
    "LoteDoAuditor",
    "PendenteCorrigida",
    "PropostaDeRegra",
    "PropostaDoAuditor",
    "RecomendacaoDoTema",
    "chamada_curta",
    "comparar_conta",
    "corrigir_item",
    "corrigir_pendente",
    "explicar_faltou_isto",
    "extrair_eventos",
    "propor_lote",
    "propor_regra",
    "recomendar_tema",
    "revisar_pendentes",
]

logger = logging.getLogger(__name__)

# Três tentativas, com espera crescente entre elas.
TENTATIVAS = 3
ESPERAS_S = (5, 20)
# A chamada sai em streaming: o prazo vale para cada leitura do stream (a API
# manda eventos o tempo todo), não para a resposta inteira.
PRAZO_DA_TENTATIVA_S = 180

# O teto de saída de cada chamada, raciocínio incluído: o máximo do Sonnet 5.5
# e do Opus 5.5. A leitura de um prontuário de 660 páginas deu 40 mil tokens e
# a comparação de uma conta de 265 itens, 57,6 mil (issues #1412 e o lote de
# 04/11/2026); com o teto antigo, de 16 mil, toda leitura grande saía cortada.
MAX_TOKENS = 128000


@dataclass(frozen=True)
class Preco:
    """Dólares por milhão de tokens, de cada parte da chamada."""

    entrada: float
    saida: float
    leitura_cache: float
    escrita_cache: float  # cache de 5 minutos, o padrão do `ephemeral`


# A Anthropic devolve os tokens, não o custo. Modelo novo entra aqui junto com
# a troca da variável; fora da tabela, a chamada grava custo zero e avisa no log.
PRECO_POR_MILHAO: dict[str, Preco] = {
    "claude-sonnet-5-5": Preco(entrada=2.00, saida=10.00, leitura_cache=0.20, escrita_cache=2.50),
    "claude-opus-5-5": Preco(entrada=4.00, saida=20.00, leitura_cache=0.20, escrita_cache=5.00),
}

MENSAGEM_SEM_CREDITO = "A IA está sem crédito. Avise o Pedro."

# O motivo de cada linha do Guia, como a faturista lê: uma frase curta (Anexo B).
MOTIVO_MAX = 140

_esperar = time.sleep


class ErroDaIA(Exception):  # noqa: N818, o nome do domínio
    """A IA não respondeu no formato. Carrega a causa (o tipo da falha, de que
    nasce o Código do erro da conta), o tipo do erro da última tentativa, o
    código HTTP e o `request_id` dela. A mensagem da API só vem no 4xx de
    validação do pedido (`_mensagem_da_api`); toda outra resposta pode citar o
    prontuário e fica sem ela (issues #1337 e #1410). O pipeline transforma em
    Erro com a frase."""

    def __init__(
        self,
        mensagem: str,
        *,
        causa: str,
        tipo: str,
        http: int | None = None,
        mensagem_da_api: str | None = None,
        request_id: str | None = None,
    ):
        super().__init__(mensagem)
        self.causa = causa
        self.tipo = tipo
        self.http = http
        self.mensagem_da_api = mensagem_da_api
        self.request_id = request_id


class IASemCredito(ErroDaIA):  # noqa: N818, o nome do domínio
    """A conta da Anthropic ficou sem saldo (400 de saldo ou 402). Não adianta
    tentar de novo: alguém tem que pôr crédito."""

    def __init__(self, *, tipo: str, http: int):
        super().__init__(MENSAGEM_SEM_CREDITO, causa="credito", tipo=tipo, http=http)


def _sem_credito(erro: anthropic.APIStatusError) -> bool:
    """402, ou o 400 que a Anthropic devolve quando o saldo acaba."""
    return erro.status_code == 402 or (erro.status_code == 400 and "credit balance" in str(erro.message).lower())


def _grande_demais(erro: anthropic.APIStatusError) -> bool:
    """O 400 do contexto excedido (o texto passou do que o modelo aceita) ou o
    413 da requisição grande demais."""
    mensagem = str(erro.message).lower()
    return erro.status_code == 413 or (
        erro.status_code == 400 and ("too long" in mensagem or "context" in mensagem and "exceed" in mensagem)
    )


# As causas que repetir não resolve: a chave, o modelo e o tamanho não mudam
# entre uma tentativa e outra (o crédito tem o próprio erro, `IASemCredito`).
DEFINITIVAS = frozenset({"chave", "modelo", "tamanho"})


def _causa(erro: anthropic.APIError | httpx2.HTTPError | ValidationError) -> tuple[str, int | None]:
    """A causa da falha e o código HTTP, para o Código do erro. Lê a mensagem
    da resposta só para separar o 400 de tamanho; ela não sai daqui."""
    if isinstance(erro, ValidationError):
        return "formato", 200
    if isinstance(erro, anthropic.APIStatusError):
        http = erro.status_code
        if http == 401:
            return "chave", http
        if http == 404:
            return "modelo", http
        if _grande_demais(erro):
            return "tamanho", http
        if http == 429 or http >= 500:
            return "fora_do_ar", http
        return "recusa", http
    if isinstance(erro, anthropic.APIConnectionError):  # inclui o tempo esgotado
        return "fora_do_ar", None
    if isinstance(erro, httpx2.HTTPError):  # a conexão ou o prazo que cai no meio do stream
        return "fora_do_ar", None
    return "recusa", None


# O teto da mensagem da API que vai para o detalhe da conta e para o log.
MENSAGEM_DA_API_MAX = 500


def _mensagem_da_api(erro: anthropic.APIStatusError, causa: str) -> str | None:
    """A mensagem do 4xx de validação do pedido (schema, parâmetro, modelo),
    que fala do pedido que o app montou e não do prontuário (issue #1410). Sai
    só o campo `error.message` da resposta, nunca o corpo do pedido, e com teto.
    A que fala de `messages`, o campo que leva o prontuário, fica de fora, como
    as de chave, modelo inexistente, tamanho e fora do ar (issue #1337)."""
    if causa != "recusa" or erro.type != "invalid_request_error" or not 400 <= erro.status_code < 500:
        return None
    falha = erro.body.get("error") if isinstance(erro.body, dict) else None
    mensagem = falha.get("message") if isinstance(falha, dict) else None
    if not isinstance(mensagem, str) or "messages" in mensagem.lower():
        return None
    return mensagem[:MENSAGEM_DA_API_MAX]


# ----------------------------------------------------------------------------------
# Os formatos de resposta (Anexos A e B da spec)
# ----------------------------------------------------------------------------------


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


# A saída estrita da Anthropic recusa com 400 o schema com mais de 16
# parâmetros anuláveis ("too many parameters with union types"), e o passo A
# tinha 20. O texto opcional do passo A sai para a IA como string, vazia quando
# o prontuário não diz, e volta aqui como None: quem consome não muda.
TextoOpcional = Annotated[
    str | None,
    BeforeValidator(lambda valor: valor or None),
    WithJsonSchema({"type": "string", "description": "Vazio quando o prontuário não disser."}),
]


class Movimentacao(_Estrito):
    tipo: Literal["INTERNACAO", "TRANSFERENCIA_SETOR", "TRANSFERENCIA_HOSPITAL", "ALTA", "OBITO"]
    data_hora: TextoOpcional
    setor: TextoOpcional
    pagina: int
    trecho: str


class Terapia(_Estrito):
    tipo: Literal[
        "VENTILACAO_MECANICA",
        "VENTILACAO_NAO_INVASIVA",
        "OXIGENIO",
        "BOMBA_INFUSAO",
        "DIETA_ENTERAL_BOMBA",
        "SONDA_ENTERAL",
        "SONDA_VESICAL",
        "ACESSO_PERIFERICO",
        "ACESSO_CENTRAL",
        "MONITOR_CARDIACO",
        "OXIMETRO",
        "PRESSAO_INVASIVA",
        "NUTRICAO_PARENTERAL",
        "ISOLAMENTO",
        "OUTRA",
    ]
    descricao: str
    setor: TextoOpcional
    inicio: TextoOpcional
    fim: TextoOpcional
    pagina: int
    trecho: str


class Prescricao(_Estrito):
    data: str
    setor: TextoOpcional
    item: str
    via: TextoOpcional
    doses_no_dia: float | None
    se_necessario: bool
    indicio_de_uso: TextoOpcional
    suspenso: bool
    diluente: TextoOpcional
    em_bomba: bool
    pagina: int
    trecho: str


class Procedimento(_Estrito):
    tipo: Literal[
        "CURATIVO",
        "SONDAGEM_VESICAL",
        "PASSAGEM_SONDA_ENTERAL",
        "INTUBACAO",
        "PUNCAO_PROFUNDA",
        "GLICEMIA_CAPILAR",
        "ASPIRACAO",
        "NEBULIZACAO",
        "FISIOTERAPIA_RESPIRATORIA",
        "FISIOTERAPIA_MOTORA",
        "FONOAUDIOLOGIA",
        "VISITA_MEDICA",
        "PARECER",
        "HEMOTRANSFUSAO",
        "OUTRO",
    ]
    data_hora: TextoOpcional
    setor: TextoOpcional
    detalhe: TextoOpcional
    quantidade: float | None
    pagina: int
    trecho: str


class Cirurgia(_Estrito):
    data: str
    inicio: TextoOpcional
    fim: TextoOpcional
    procedimento: str
    codigo: TextoOpcional
    anestesia: TextoOpcional
    cobranca_honorario: Literal["VIA_HOSPITAL", "VIA_EQUIPE", "NAO_SINALIZADO"]
    equipamentos: list[str]
    pagina: int
    trecho: str


class EventosDoProntuario(_Estrito):
    """A saída do passo A (Anexo A)."""

    atendimento: TextoOpcional
    idade_anos: int | None
    movimentacoes: list[Movimentacao]
    terapias: list[Terapia]
    prescricoes: list[Prescricao]
    procedimentos: list[Procedimento]
    cirurgias: list[Cirurgia]
    documentos_ausentes: list[str]
    observacoes: list[str]


class Evidencia(_Estrito):
    pagina: int | None
    trecho: str | None


class LinhaDaComparacao(_Estrito):
    acao: Literal["INCLUIR", "AJUSTAR_QUANTIDADE", "RETIRAR", "VALIDAR"]
    data: str
    data_fim: str
    setor: str | None
    codigo: str | None
    descricao: str
    quantidade_lancada: float
    quantidade_devida: float
    regra_id: str
    motivo: str = Field(max_length=MOTIVO_MAX)
    evidencia: Evidencia
    nivel_evidencia: Literal["REGISTRADO", "PRESCRITO", "PRESCRITO_SN", "POR_REGRA"]
    causa_raiz: Literal[
        "DISPENSACAO", "REGRA_AUTOMATICA", "CADASTRO_PRECO", "REGISTRO_ASSISTENCIAL", "LANCAMENTO_MANUAL"
    ]
    confianca: Literal["ALTA", "MEDIA", "BAIXA"]


class LinhasDaComparacao(_Estrito):
    """A saída do passo B (Anexo B). A IA não devolve valor em reais."""

    linhas: list[LinhaDaComparacao]
    resumo: str


class RegraProposta(_Estrito):
    secao: Literal["PRI", "PRC", "DIA", "PAC", "TAX", "CC", "HON", "INS", "MED"]
    texto: str
    tipo: Literal["CONTRATUAL", "OPERACIONAL"]
    origem: str


class ParametroProposto(_Estrito):
    """A chave do cabeçalho com ponto entre os níveis (`diaria.hora_vencimento`)
    e o valor novo em JSON, porque o valor pode ser texto, número, sim ou não."""

    chave: str
    valor_json: str


class PropostaDeRegra(_Estrito):
    """A regra nova proposta pela IA: os quatro blocos que a tela mostra."""

    regra: RegraProposta
    parametro: ParametroProposto | None
    conflitos: list[str]
    efeito_no_guia: str


class DiagnosticoDoFaltouIsto(_Estrito):
    """A resposta do Auditor a um Faltou isto (ADR 0081, decisão 4): a origem
    da omissão, a explicação para quem apontou e o que o Guia deveria ter dito."""

    classificacao: Literal["REGRA", "LEITURA", "DEFEITO"]
    explicacao: str
    esperado: str


class ConflitoDaProposta(_Estrito):
    """A regra da memória com que a proposta conflita e o que o Auditor propõe
    fazer com ela (ADR 0081, decisão 8)."""

    codigo: str
    resolucao: Literal["JUNTAR", "SUBSTITUIR"]


class PropostaDoAuditor(_Estrito):
    """Um item do lote do Auditor (issue #1490). Os campos que não cabem no tipo
    vêm vazios: a regra nova não tem código, o parâmetro não tem texto de regra.
    Texto vazio em vez de nulo, pelo teto de anuláveis da saída estrita."""

    tipo: Literal["REGRA_NOVA", "REGRA_ALTERADA", "PARAMETRO"]
    regra_codigo: str
    secao: Literal["PRI", "PRC", "DIA", "PAC", "TAX", "CC", "HON", "INS", "MED"]
    texto: str
    tipo_regra: Literal["CONTRATUAL", "OPERACIONAL"]
    origem: str
    parametro: str
    valor_json: str
    motivo: str
    conflitos: list[ConflitoDaProposta]


class LoteDoAuditor(_Estrito):
    """A resposta do Auditor na conversa da Operadora: a fala dele e as
    propostas do lote, já decididas (ADR 0081, decisão 1)."""

    resposta: str
    propostas: list[PropostaDoAuditor]


class ItemCorrigido(_Estrito):
    """O "corrige o item N": a fala do Auditor e o item refeito."""

    resposta: str
    proposta: PropostaDoAuditor


class DecisaoDaPendente(_Estrito):
    """O que o Auditor sugere para uma Regra pendente (issue #1494): validar como
    está, alterar o texto ou descartar. O texto vem vazio fora do ALTERAR."""

    regra_codigo: str
    decisao: Literal["VALIDAR", "ALTERAR", "DESCARTAR"]
    texto: str
    motivo: str


class RevisaoDasPendentes(_Estrito):
    """O "revisar pendentes": a fala do Auditor e uma decisão por Regra pendente."""

    resposta: str
    decisoes: list[DecisaoDaPendente]


class PendenteCorrigida(_Estrito):
    """O "corrige o item N" no lote das pendentes: a fala e a decisão refeita."""

    resposta: str
    decisao: DecisaoDaPendente


class RecomendacaoDoTema(_Estrito):
    """A recomendação do Auditor a um Tema de validação (ADR 0081, decisão 13):
    a decisão, o motivo para quem aprova e o texto que a decisão leva (a regra
    editada ou a resposta ao time; vazio nas outras)."""

    decisao: Literal[
        "VALIDAR_REGRA",
        "DEIXAR_PENDENTE",
        "ENVIAR_AO_CADASTRO",
        "DESCARTAR",
        "MANTER_REGRA",
        "EDITAR_REGRA",
        "RESPONDER",
        "CONFIRMAR",
        "REJEITAR",
    ]
    motivo: str
    texto: str


# ----------------------------------------------------------------------------------
# O schema estrito
# ----------------------------------------------------------------------------------


def _schema_estrito(modelo: type[BaseModel]) -> dict[str, Any]:
    """O JSON schema do modelo como a saída estrita pede: as referências
    resolvidas no lugar, todo objeto fechado e com todas as chaves obrigatórias,
    sem título nem valor padrão. Sem `maxLength`, que a saída estrita da
    Anthropic recusa com 400: o limite fica no Pydantic, que valida a resposta."""
    bruto = modelo.model_json_schema()
    definicoes = bruto.pop("$defs", {})

    def resolver(no: Any) -> Any:
        if isinstance(no, list):
            return [resolver(v) for v in no]
        if not isinstance(no, dict):
            return no
        if "$ref" in no:
            return resolver(definicoes[no["$ref"].rsplit("/", 1)[-1]])
        limpo = {
            chave: resolver(valor) for chave, valor in no.items() if chave not in ("title", "default", "maxLength")
        }
        if limpo.get("type") == "object" and "properties" in limpo:
            limpo["additionalProperties"] = False
            limpo["required"] = list(limpo["properties"])
        return limpo

    return resolver(bruto)


# ----------------------------------------------------------------------------------
# A chamada
# ----------------------------------------------------------------------------------


def _cliente() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise ErroDaIA("ANTHROPIC_API_KEY vazia", causa="chave", tipo="ChaveVazia")
    return anthropic.Anthropic(
        api_key=settings.anthropic_api_key,
        max_retries=0,  # as três tentativas são deste adaptador
        timeout=PRAZO_DA_TENTATIVA_S,
    )


def _bloco(texto: str, *, cache: bool) -> dict[str, Any]:
    bloco: dict[str, Any] = {"type": "text", "text": texto}
    if cache:
        bloco["cache_control"] = {"type": "ephemeral"}
    return bloco


@dataclass
class _Uso:
    """O que a chamada custou, somado entre as tentativas: a tentativa que
    voltou fora do formato também foi cobrada."""

    entrada: int = 0
    saida: int = 0
    cache: int = 0
    custo: float = 0.0

    def somar(self, resposta: Any, preco: Preco | None) -> None:
        """`entrada` conta tudo que entrou (sem cache, lido e escrito no
        cache); `cache` é o que veio lido do cache."""
        uso = getattr(resposta, "usage", None)
        if uso is None:
            return
        sem_cache = uso.input_tokens or 0
        lidos = uso.cache_read_input_tokens or 0
        escritos = uso.cache_creation_input_tokens or 0
        saida = uso.output_tokens or 0
        self.entrada += sem_cache + lidos + escritos
        self.saida += saida
        self.cache += lidos
        if preco is not None:
            self.custo += (
                sem_cache * preco.entrada
                + saida * preco.saida
                + lidos * preco.leitura_cache
                + escritos * preco.escrita_cache
            ) / 1_000_000


@dataclass(frozen=True)
class _Onde:
    """Onde a chamada fica gravada."""

    supabase: Any
    conta_id: str | None
    atendimento_id: str | None
    passo: str


def _gravar(onde: _Onde, modelo: str, uso: _Uso, duracao_ms: int, tentativas: int, sucesso: bool) -> None:
    """A chamada em `cm_chamada_ia` e a soma das chamadas da conta em
    `cm_conta`. Falha ao gravar o custo não derruba a análise: refazer a conta
    pagaria a IA de novo."""
    try:
        onde.supabase.table("cm_chamada_ia").insert(
            {
                "conta_id": onde.conta_id,
                "atendimento_id": onde.atendimento_id,
                "passo": onde.passo,
                "modelo": modelo,
                "tokens_entrada": uso.entrada,
                "tokens_saida": uso.saida,
                "tokens_cache": uso.cache,
                "custo_usd": round(uso.custo, 6),
                "duracao_ms": duracao_ms,
                "tentativas": tentativas,
                "sucesso": sucesso,
            }
        ).execute()
        if onde.conta_id:
            _somar_na_conta(onde.supabase, onde.conta_id)
    except Exception as erro:
        logger.error("[ContasMedicas] Custo da IA da conta %s sem gravação: %s", onde.conta_id, type(erro).__name__)


def _somar_na_conta(supabase, conta_id: str) -> None:
    """A conta guarda a soma de todas as chamadas dela, inclusive as do
    reprocesso: é o que a IA custou de verdade para aquela conta."""
    chamadas = (
        supabase.table("cm_chamada_ia")
        .select("modelo, tokens_entrada, tokens_saida, tokens_cache, custo_usd")
        .eq("conta_id", conta_id)
        .order("criado_em")
        .execute()
        .data
        or []
    )
    supabase.table("cm_conta").update(
        {
            "tokens_entrada": sum(int(c.get("tokens_entrada") or 0) for c in chamadas),
            "tokens_saida": sum(int(c.get("tokens_saida") or 0) for c in chamadas),
            "tokens_cache": sum(int(c.get("tokens_cache") or 0) for c in chamadas),
            "custo_usd": round(sum(float(c.get("custo_usd") or 0) for c in chamadas), 4),
            "modelo_ia": ", ".join(dict.fromkeys(c["modelo"] for c in chamadas if c.get("modelo"))),
        }
    ).eq("id", conta_id).execute()


def _chamar_a_ia[Saida: BaseModel](
    *,
    modelo: str,
    instrucao: str,
    blocos: list[tuple[str, bool]],
    saida: type[Saida],
    onde: _Onde,
) -> Saida:
    """Uma chamada, em até três tentativas. `blocos` é o conteúdo do usuário,
    cada um com a marca de cache; a instrução vai sempre em cache."""
    sistema = [_bloco(instrucao, cache=True)]
    mensagens = [{"role": "user", "content": [_bloco(texto, cache=cache) for texto, cache in blocos]}]
    formato = {"format": {"type": "json_schema", "schema": _schema_estrito(saida)}}
    preco = PRECO_POR_MILHAO.get(modelo)
    if preco is None:
        logger.warning("[ContasMedicas] Modelo %s sem preço na tabela: o custo fica zero", modelo)
    cliente = _cliente()
    uso = _Uso()
    falha = ErroDaIA("A IA não foi chamada", causa="recusa", tipo="SemTentativa")
    inicio = perf_counter()
    for tentativa in range(1, TENTATIVAS + 1):
        if tentativa > 1:
            _esperar(ESPERAS_S[tentativa - 2])
        try:
            with cliente.messages.stream(
                model=modelo,
                max_tokens=MAX_TOKENS,
                system=sistema,
                messages=mensagens,
                output_config=formato,
            ) as stream:
                resposta = stream.get_final_message()
            uso.somar(resposta, preco)
            if resposta.stop_reason in ("max_tokens", "model_context_window_exceeded"):
                # Cortada no teto de saída ou na janela de contexto do modelo: o JSON
                # veio pela metade, e repetir dá o mesmo corte.
                logger.warning(
                    "[ContasMedicas] IA %s, tentativa %s: resposta cortada (%s)",
                    modelo,
                    tentativa,
                    resposta.stop_reason,
                )
                limite = f"teto de {MAX_TOKENS} tokens" if resposta.stop_reason == "max_tokens" else "janela do modelo"
                falha = ErroDaIA(
                    f"A resposta da IA passou do {limite}",
                    causa="tamanho",
                    tipo="RespostaCortada",
                    http=200,
                )
                break
            conteudo = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")
            resultado = saida.model_validate_json(conteudo)
        except (anthropic.APIError, httpx2.HTTPError, ValidationError) as erro:
            # O SDK só traduz o erro do envio; o que cai na leitura do stream (conexão
            # perdida, prazo de leitura esgotado) sobe cru do httpx2, o transporte dele.
            # O tipo do erro e, só no 400 de validação do pedido, a mensagem da API:
            # a resposta inválida pode citar o prontuário.
            tipo = type(erro).__name__
            if isinstance(erro, anthropic.APIStatusError) and _sem_credito(erro):
                logger.error(
                    "[ContasMedicas] IA %s sem crédito (HTTP %s): sem nova tentativa", modelo, erro.status_code
                )
                _gravar(onde, modelo, uso, round((perf_counter() - inicio) * 1000), tentativa, sucesso=False)
                raise IASemCredito(tipo=tipo, http=erro.status_code) from None
            causa, http = _causa(erro)
            status = isinstance(erro, anthropic.APIStatusError)
            mensagem_da_api = _mensagem_da_api(erro, causa) if status else None
            request_id = erro.request_id if status else None
            logger.warning(
                "[ContasMedicas] IA %s, tentativa %s: %s (HTTP %s, request_id %s)%s",
                modelo,
                tentativa,
                tipo,
                http,
                request_id,
                f": {mensagem_da_api}" if mensagem_da_api else "",
            )
            falha = ErroDaIA(
                f"A IA falhou na tentativa {tentativa} ({causa}, {tipo}, HTTP {http})",
                causa=causa,
                tipo=tipo,
                http=http,
                mensagem_da_api=mensagem_da_api,
                request_id=request_id,
            )
            if causa in DEFINITIVAS:
                break
            continue
        _gravar(onde, modelo, uso, round((perf_counter() - inicio) * 1000), tentativa, sucesso=True)
        return resultado
    _gravar(onde, modelo, uso, round((perf_counter() - inicio) * 1000), tentativa, sucesso=False)
    raise falha


# ----------------------------------------------------------------------------------
# As portas
# ----------------------------------------------------------------------------------


def _json(valor: Any) -> str:
    if isinstance(valor, BaseModel):
        return valor.model_dump_json()
    return json.dumps(valor, ensure_ascii=False, default=str)


def _tabela(itens: list[dict[str, Any]]) -> str:
    """Os itens lançados na conta em tabela, uma linha por item."""
    if not itens:
        return "(conta sem itens)"
    colunas = list(dict.fromkeys(chave for item in itens for chave in item))
    linhas = [" | ".join(colunas), " | ".join("---" for _ in colunas)]
    linhas += [" | ".join("" if item.get(c) is None else str(item.get(c)) for c in colunas) for item in itens]
    return "\n".join(linhas)


def extrair_eventos(
    texto: str, orientacoes: str, *, supabase, conta_id: str | None, atendimento_id: str | None
) -> EventosDoProntuario:
    """O passo A: os eventos do prontuário, com página e trecho em cada um.
    Não recebe a conta nem a tabela de preço."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_a,
        instrucao=load_prompt("contas_medicas_passo_a"),
        blocos=[
            (f"ORIENTAÇÕES DE LEITURA DA OPERADORA\n{orientacoes}", False),
            (f"TEXTO DO PRONTUÁRIO\n{texto}", False),
        ],
        saida=EventosDoProntuario,
        onde=_Onde(supabase, conta_id, atendimento_id, "A"),
    )


def comparar_conta(
    memoria: str,
    eventos: EventosDoProntuario | dict[str, Any],
    itens: list[dict[str, Any]],
    calculos: dict[str, Any],
    *,
    supabase,
    conta_id: str | None,
    atendimento_id: str | None,
    passo: Literal["B", "PROVA"] = "B",
) -> LinhasDaComparacao:
    """O passo B: as linhas do Guia que a IA propõe. A memória vai em bloco de
    cache: é o mesmo texto para todas as contas da operadora.

    `passo="PROVA"` é o Passo B refeito pela Prova da regra (#1488): a mesma
    chamada, gravada com o passo próprio."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_passo_b"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"EVENTOS\n{_json(eventos)}", False),
            (f"CONTA\n{_tabela(itens)}", False),
            (f"CÁLCULOS\n{_json(calculos)}", False),
        ],
        saida=LinhasDaComparacao,
        onde=_Onde(supabase, conta_id, atendimento_id, passo),
    )


def chamada_curta[Saida: BaseModel](
    instrucao: str,
    conteudo: str,
    saida: type[Saida],
    *,
    passo: Literal["DICIONARIO", "OBSERVACAO"],
    supabase,
    conta_id: str | None,
    atendimento_id: str | None = None,
) -> Saida:
    """A pergunta curta (dicionário e observações), no modelo do passo A, com o
    schema que quem chama escolhe."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_a,
        instrucao=instrucao,
        blocos=[(conteudo, False)],
        saida=saida,
        onde=_Onde(supabase, conta_id, atendimento_id, passo),
    )


def explicar_faltou_isto(
    memoria: str, dia: str, apontamento: str, *, supabase, conta_id: str, atendimento_id: str | None
) -> DiagnosticoDoFaltouIsto:
    """O Auditor na conversa da Conta (issue #1489): por que o Guia não achou o
    item apontado naquele dia, e de onde a omissão veio. No modelo do Passo B,
    com a memória da operadora em bloco de cache; o dia traz os eventos, as
    páginas, as linhas do Guia e os itens da conta, já sem identificação."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_faltou_isto"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"O DIA NA CONTA\n{dia}", False),
            (f"O QUE FALTOU\n{apontamento}", False),
        ],
        saida=DiagnosticoDoFaltouIsto,
        onde=_Onde(supabase, conta_id, atendimento_id, "CONVERSA"),
    )


def propor_lote(texto: str, memoria: str, *, supabase) -> LoteDoAuditor:
    """O Auditor na conversa da Operadora (issue #1490): a mensagem de quem
    decide vira um lote de propostas. Só a mensagem desta vez vai junto da
    memória: a conversa não é memória (ADR 0081, decisão 3)."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_auditor"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"MENSAGEM DE QUEM DECIDE\n{texto}", False),
        ],
        saida=LoteDoAuditor,
        onde=_Onde(supabase, None, None, "CONVERSA"),
    )


def corrigir_item(memoria: str, item: str, pedido: str, *, supabase) -> ItemCorrigido:
    """O "corrige o item N" (issue #1490): o item atual do lote, em JSON, e o
    que quem decide pediu para mudar nele. Volta um item só."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_auditor"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"ITEM ATUAL DO LOTE\n{item}", False),
            (f"CORREÇÃO PEDIDA\n{pedido}", False),
        ],
        saida=ItemCorrigido,
        onde=_Onde(supabase, None, None, "CONVERSA"),
    )


def revisar_pendentes(memoria: str, pendentes: str, *, supabase) -> RevisaoDasPendentes:
    """O "revisar pendentes" (issue #1494): a decisão sugerida para cada Regra
    pendente da Operadora, com a memória inteira para o contexto."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_auditor_pendentes"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"REGRAS PENDENTES\n{pendentes}", False),
        ],
        saida=RevisaoDasPendentes,
        onde=_Onde(supabase, None, None, "CONVERSA"),
    )


def corrigir_pendente(memoria: str, item: str, pedido: str, *, supabase) -> PendenteCorrigida:
    """O "corrige o item N" no lote das pendentes (issue #1494): a decisão atual
    do item, em JSON, e o que quem decide pediu para mudar nela."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_auditor_pendentes"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"ITEM ATUAL DO LOTE\n{item}", False),
            (f"CORREÇÃO PEDIDA\n{pedido}", False),
        ],
        saida=PendenteCorrigida,
        onde=_Onde(supabase, None, None, "CONVERSA"),
    )


def recomendar_tema(memoria: str, tema: str, *, supabase) -> RecomendacaoDoTema:
    """O Auditor decide um Tema da fila de Validação (issue #1491): no modelo do
    Passo B, com a memória da operadora em bloco de cache. Gravada como
    CONVERSA, o passo do Auditor, sem conta: o Tema junta várias."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_recomendacao"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"O TEMA DE VALIDAÇÃO\n{tema}", False),
        ],
        saida=RecomendacaoDoTema,
        onde=_Onde(supabase, None, None, "CONVERSA"),
    )


def propor_regra(texto: str, memoria: str, *, supabase) -> PropostaDeRegra:
    """A regra nova que a pessoa escreveu, no formato da memória: a regra, o
    parâmetro do cabeçalho que muda, as regras com que conflita e o efeito no
    Guia. No modelo do passo B, com a memória em bloco de cache.

    Fica gravada como OBSERVACAO, a leitura de texto livre sobre regra: a
    migration 118 é a única do PRD e o CHECK do passo não tem valor próprio."""
    return _chamar_a_ia(
        modelo=settings.cm_ia_modelo_passo_b,
        instrucao=load_prompt("contas_medicas_regra_nova"),
        blocos=[
            (f"MEMÓRIA DA OPERADORA\n{memoria}", True),
            (f"REGRA EM LINGUAGEM COMUM\n{texto}", False),
        ],
        saida=PropostaDeRegra,
        onde=_Onde(supabase, None, None, "OBSERVACAO"),
    )
