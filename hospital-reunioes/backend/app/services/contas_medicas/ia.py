"""O adaptador de IA de Contas médicas (issue #1130, PRD #1128).

A única porta do módulo para a IA, sobre o cliente do OpenRouter que o app já
usa. Três chamadas:

- `extrair_eventos`: o passo A, que lê o prontuário e lista os eventos
  (Anexo A da spec);
- `comparar_conta`: o passo B, que compara a conta com a memória da operadora
  e devolve as linhas do Guia (Anexo B, com o "se necessário" do adendo v1.1);
- `chamada_curta`: a pergunta curta do dicionário e das observações, com o
  schema que quem chama escolhe.

Toda chamada sai igual: saída estruturada estrita (`json_schema` com
`strict`), só para provedor que respeita os parâmetros, sem retenção do texto
(`zdr`) e sem coleta para treino. Quando o modelo é Anthropic, a instrução e a
memória vão em bloco de cache. A resposta é validada pelo Pydantic.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Literal

from openai import APIError, OpenAI
from pydantic import BaseModel, ConfigDict, ValidationError

from app.config import settings
from app.services.ai_processor import _OPENROUTER_HEADERS
from app.services.prompt_loader import load_prompt

__all__ = [
    "ErroDaIA",
    "EventosDoProntuario",
    "LinhasDaComparacao",
    "chamada_curta",
    "comparar_conta",
    "extrair_eventos",
]

logger = logging.getLogger(__name__)

# Três tentativas, com espera crescente entre elas. Uma chamada inteira (três
# prazos e as duas esperas) fica abaixo de 10 minutos, dentro dos 15 em que o
# processamento considera a conta presa e a devolve para a fila.
TENTATIVAS = 3
ESPERAS_S = (5, 20)
PRAZO_DA_TENTATIVA_S = 180

# Toda chamada do módulo: só provedor que aceita o schema, sem retenção do
# texto e sem coleta para treino. O prontuário nunca fica no provedor.
PROVEDOR = {"require_parameters": True, "zdr": True, "data_collection": "deny"}

_esperar = time.sleep


class ErroDaIA(Exception):  # noqa: N818, o nome do domínio
    """A IA não respondeu no formato. A mensagem é técnica e nunca leva texto
    do prontuário; o pipeline transforma em Erro com a frase para a faturista."""


# ----------------------------------------------------------------------------------
# Os formatos de resposta (Anexos A e B da spec)
# ----------------------------------------------------------------------------------


class _Estrito(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Movimentacao(_Estrito):
    tipo: Literal["INTERNACAO", "TRANSFERENCIA_SETOR", "TRANSFERENCIA_HOSPITAL", "ALTA", "OBITO"]
    data_hora: str | None
    setor: str | None
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
    setor: str | None
    inicio: str | None
    fim: str | None
    pagina: int
    trecho: str


class Prescricao(_Estrito):
    data: str
    setor: str | None
    item: str
    via: str | None
    doses_no_dia: float | None
    se_necessario: bool
    indicio_de_uso: str | None
    suspenso: bool
    diluente: str | None
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
    data_hora: str | None
    setor: str | None
    detalhe: str | None
    quantidade: float | None
    pagina: int
    trecho: str


class Cirurgia(_Estrito):
    data: str
    inicio: str | None
    fim: str | None
    procedimento: str
    codigo: str | None
    anestesia: str | None
    cobranca_honorario: Literal["VIA_HOSPITAL", "VIA_EQUIPE", "NAO_SINALIZADO"]
    equipamentos: list[str]
    pagina: int
    trecho: str


class EventosDoProntuario(_Estrito):
    """A saída do passo A (Anexo A)."""

    atendimento: str | None
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
    motivo: str
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


# ----------------------------------------------------------------------------------
# O schema estrito
# ----------------------------------------------------------------------------------


def _schema_estrito(modelo: type[BaseModel]) -> dict[str, Any]:
    """O JSON schema do modelo como a saída estrita pede: as referências
    resolvidas no lugar, todo objeto fechado e com todas as chaves obrigatórias,
    sem título nem valor padrão."""
    bruto = modelo.model_json_schema()
    definicoes = bruto.pop("$defs", {})

    def resolver(no: Any) -> Any:
        if isinstance(no, list):
            return [resolver(v) for v in no]
        if not isinstance(no, dict):
            return no
        if "$ref" in no:
            return resolver(definicoes[no["$ref"].rsplit("/", 1)[-1]])
        limpo = {chave: resolver(valor) for chave, valor in no.items() if chave not in ("title", "default")}
        if limpo.get("type") == "object" and "properties" in limpo:
            limpo["additionalProperties"] = False
            limpo["required"] = list(limpo["properties"])
        return limpo

    return resolver(bruto)


# ----------------------------------------------------------------------------------
# A chamada
# ----------------------------------------------------------------------------------


def _cliente() -> OpenAI:
    if not settings.openrouter_api_key:
        raise ErroDaIA("OPENROUTER_API_KEY vazia")
    return OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
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

    def somar(self, resposta: Any) -> None:
        uso = getattr(resposta, "usage", None)
        if uso is None:
            return
        detalhes = getattr(uso, "prompt_tokens_details", None)
        custo = getattr(uso, "cost", None)
        if custo is None:
            custo = (getattr(uso, "model_extra", None) or {}).get("cost")
        self.entrada += uso.prompt_tokens or 0
        self.saida += uso.completion_tokens or 0
        self.cache += (getattr(detalhes, "cached_tokens", None) or 0) if detalhes else 0
        self.custo += float(custo or 0)


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
    cada um com a marca de cache, que só vale quando o modelo é Anthropic."""
    anthropic = modelo.startswith("anthropic/")
    mensagens = [
        {"role": "system", "content": [_bloco(instrucao, cache=anthropic)]},
        {"role": "user", "content": [_bloco(texto, cache=anthropic and cache) for texto, cache in blocos]},
    ]
    formato = {
        "type": "json_schema",
        "json_schema": {"name": saida.__name__, "strict": True, "schema": _schema_estrito(saida)},
    }
    cliente = _cliente()
    uso = _Uso()
    falha = ""
    inicio = perf_counter()
    for tentativa in range(1, TENTATIVAS + 1):
        if tentativa > 1:
            _esperar(ESPERAS_S[tentativa - 2])
        try:
            resposta = cliente.chat.completions.create(
                model=modelo,
                messages=mensagens,
                response_format=formato,
                extra_headers=_OPENROUTER_HEADERS,
                extra_body={"provider": PROVEDOR, "usage": {"include": True}},
            )
            uso.somar(resposta)
            conteudo = resposta.choices[0].message.content if resposta.choices else None
            resultado = saida.model_validate_json(conteudo or "")
        except (APIError, ValidationError) as erro:
            # O tipo do erro, nunca a mensagem: a resposta inválida pode citar o prontuário.
            falha = type(erro).__name__
            logger.warning("[ContasMedicas] IA %s, tentativa %s: %s", modelo, tentativa, falha)
            continue
        _gravar(onde, modelo, uso, round((perf_counter() - inicio) * 1000), tentativa, sucesso=True)
        return resultado
    _gravar(onde, modelo, uso, round((perf_counter() - inicio) * 1000), TENTATIVAS, sucesso=False)
    raise ErroDaIA(f"A IA não respondeu no formato em {TENTATIVAS} tentativas ({falha})")


# ----------------------------------------------------------------------------------
# As três portas
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
) -> LinhasDaComparacao:
    """O passo B: as linhas do Guia que a IA propõe. A memória vai em bloco de
    cache: é o mesmo texto para todas as contas da operadora."""
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
        onde=_Onde(supabase, conta_id, atendimento_id, "B"),
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
