"""A Revisao com o codigo de hoje, a conversa (issue #1557, PRD #1548, ADR 0084, decisao 3).

Um card de melhoria Em analise ou Planejada volta a mesma conversa do
planejamento. O primeiro turno e o **Retrato de hoje**: o agente le o card como
esta na issue, os comentarios dela, as subidas do `history.json` desde a data
do card e o codigo, e devolve tres blocos (Ja existe, com a versao; Mudou desde
o card; Continua em aberto). Cada item de Ja existe vira a pergunta "isso
atende?", feita pelo codigo e nao pelo modelo, e so sai do pedido com o sim.
Depois o planejamento segue pelas lacunas, sem teto.

O que aqui e sem I/O: a estimativa, as subidas desde a data, o escopo e a
pergunta do "isso atende?". O retrato chama o modelo do planejamento pela
mesma porta (`planejamento_demanda.chamar_o_modelo`), com o custo gravado.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.config import settings
from app.services import ai_processor, ferramentas_do_codigo, github_client, planejamento_demanda
from app.services.custo_da_conversa import nome_de_exibicao
from app.services.tecnologia import instante_do_banco, recuar_continuacao
from app.services.tecnologia_vinculo import LABEL_EM_ANDAMENTO, marcador_da_demanda, texto_do_diretor
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

TIPO_DO_RETRATO = "retrato"

OPCAO_ATENDE = "Atende, pode sair do pedido."
OPCAO_NAO_ATENDE = "Não atende, continua no pedido."

MOTIVO_RETRATO_FALHOU = planejamento_demanda.MOTIVO_TURNO_FALHOU

# ─── A estimativa (ADR 0082) ─────────────────────────────────────────────────

# Uns quatro caracteres por token, a conta de bolso do portugues.
CARACTERES_POR_TOKEN = 4
# Os comentarios e as subidas so sao lidos depois da confirmacao: a estimativa
# reserva o tamanho de uma leitura tipica.
RESERVA_DAS_LEITURAS = 4_000
# A resposta do retrato: tres listas curtas, mais o pensamento do modelo.
SAIDA_DO_RETRATO = 3_000


def estimativa(*, caracteres: int, kit: str) -> dict:
    """A faixa em dolar do Retrato de hoje, pelo tamanho da conversa e do PRD
    (`caracteres`) e do kit, com o preco do modelo do planejamento.

    O minimo e uma chamada so, sem consultar o codigo. O maximo e o teto de
    consultas do turno, cada rodada reenviando o pedido e o arquivo lido.
    Modelo sem preco na tabela devolve a faixa nula: a tela diz que nao estimou.
    """
    modelo = settings.llm_model_planejamento
    preco = planejamento_demanda.PRECO_POR_MILHAO.get(modelo)
    if preco is None:
        return {"modelo": nome_de_exibicao(modelo), "minimo_usd": None, "maximo_usd": None}
    entrada = (caracteres + len(kit)) // CARACTERES_POR_TOKEN + RESERVA_DAS_LEITURAS
    por_arquivo = ferramentas_do_codigo.TETO_DO_ARQUIVO // CARACTERES_POR_TOKEN
    rodadas = ferramentas_do_codigo.TETO_DE_CONSULTAS + 1
    minimo = entrada * preco.entrada + SAIDA_DO_RETRATO * preco.saida
    maximo = sum((entrada + k * por_arquivo) * preco.entrada for k in range(rodadas)) + (
        rodadas * SAIDA_DO_RETRATO * preco.saida
    )
    return {
        "modelo": nome_de_exibicao(modelo),
        "minimo_usd": round(minimo / 1_000_000, 2),
        "maximo_usd": round(maximo / 1_000_000, 2),
    }


# ─── O que subiu desde o card ────────────────────────────────────────────────


def versao(valor: str | None) -> str:
    """`0.245.0` vira `v0.245.0`; o que ja tem o `v` fica."""
    texto = " ".join((valor or "").split())
    return f"v{texto}" if texto[:1].isdigit() else texto


def subidas_desde(historico: list[dict], desde: datetime | None) -> list[dict]:
    """As subidas do `history.json` a partir da data do card, a mais antiga
    primeiro. Entrada sem data ou sem versao fica de fora: sem ela o retrato
    nao teria como dizer em que versao algo entrou."""
    subidas = []
    for entrada in historico:
        quando = instante_do_banco(entrada.get("at"))
        if quando is None or not entrada.get("app_version") or (desde is not None and quando < desde):
            continue
        subidas.append({**entrada, "_quando": quando})
    return sorted(subidas, key=lambda e: e["_quando"])


def _linha_da_subida(entrada: dict) -> str:
    prds = ", ".join(f"#{n}" for n in entrada.get("prds") or [])
    sufixo = f" (PRDs {prds})" if prds else ""
    return recuar_continuacao(
        f"- {versao(entrada.get('app_version'))} ({entrada['_quando'].date().isoformat()}): "
        f"{entrada.get('subject') or ''}{sufixo}"
    )


# ─── O retrato ───────────────────────────────────────────────────────────────


class _ItemQueJaExiste(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item: str
    versao: str

    @field_validator("item", "versao")
    @classmethod
    def _preenchido(cls, valor: str) -> str:
        if not valor.strip():
            raise ValueError("item de Já existe sem texto ou sem versão")
        return valor


class _SaidaDoRetrato(BaseModel):
    """O esquema do Retrato de hoje. Item de Ja existe sem versao derruba o
    retrato: e a versao que diz ao diretor desde quando aquilo esta no ar."""

    model_config = ConfigDict(extra="ignore")

    ja_existe: list[_ItemQueJaExiste]
    mudou: list[str]
    em_aberto: list[str]


@dataclass(frozen=True)
class ResultadoDoRetrato:
    """`mensagem` e a fala do retrato, pronta para a conversa; `erro`, a frase
    da tela quando ele nao saiu. `chamada` e nula so no modo mock."""

    mensagem: dict | None
    erro: str | None
    chamada: dict | None


RETRATO_MOCK = {
    "tipo": TIPO_DO_RETRATO,
    "ja_existe": [],
    "mudou": [],
    "em_aberto": ["[MOCK] Revisar com o código de hoje exige a IA configurada."],
}


def _limpo(texto: str) -> str:
    return sanitizar_travessao(" ".join(texto.split()))


def _mensagem_do_retrato(saida: _SaidaDoRetrato) -> dict:
    return {
        "tipo": TIPO_DO_RETRATO,
        "ja_existe": [{"item": _limpo(i.item), "versao": versao(i.versao)} for i in saida.ja_existe],
        "mudou": [_limpo(t) for t in saida.mudou if t.strip()],
        "em_aberto": [_limpo(t) for t in saida.em_aberto if t.strip()],
    }


def pedido_do_retrato(
    *,
    demanda: dict,
    mensagens: list[dict],
    corpo_da_issue: str,
    comentarios: list[dict],
    subidas: list[dict],
    data_do_card: datetime | None,
) -> str:
    """O pedido do Retrato de hoje. O card, os comentarios e as subidas sao
    texto de gente: entram recuados, nenhuma linha deles chega a coluna zero."""
    data = data_do_card.date().isoformat() if data_do_card else "(sem data)"
    linhas_dos_comentarios = [
        recuar_continuacao(f"- {c.get('autor') or '?'}: {c.get('corpo') or ''}") for c in comentarios
    ] or ["(nenhum comentário)"]
    linhas_das_subidas = [_linha_da_subida(s) for s in subidas] or ["(nada subiu desde o card)"]
    return "\n".join(
        [
            "PEDIDO: RETRATO DE HOJE",
            "",
            planejamento_demanda.pedido_do_turno(demanda, mensagens),
            "",
            "O CARD COMO ESTÁ HOJE NO DESENVOLVIMENTO",
            recuar_continuacao(f"    {corpo_da_issue or '(sem texto)'}"),
            "",
            "COMENTÁRIOS DO CARD",
            *linhas_dos_comentarios,
            "",
            f"O QUE SUBIU DESDE A DATA DO CARD ({data})",
            *linhas_das_subidas,
            "",
            f"VERSÃO DE HOJE: {versao(settings.app_version)}",
        ]
    )


def retrato_de_hoje(*, demanda: dict, mensagens: list[dict], kit: str, **leituras) -> ResultadoDoRetrato:
    """O primeiro turno da revisao. Sem estado: tudo chega por parametro, e
    `leituras` sao as de `pedido_do_retrato`. O modelo leva as ferramentas de
    leitura do codigo, como o turno da melhoria."""
    if ai_processor._llm_provider() == "mock":
        logger.warning("Modo MOCK ativo para o Retrato de hoje (sem chave LLM)")
        return ResultadoDoRetrato(mensagem=json.loads(json.dumps(RETRATO_MOCK)), erro=None, chamada=None)
    saida, chamada = planejamento_demanda.chamar_o_modelo(
        demanda=demanda,
        passo="pergunta",
        conteudo=pedido_do_retrato(demanda=demanda, mensagens=mensagens, **leituras),
        kit=kit,
        validar=_SaidaDoRetrato.model_validate,
        consultas=ferramentas_do_codigo.Consultas(),
    )
    if saida is None:
        return ResultadoDoRetrato(mensagem=None, erro=MOTIVO_RETRATO_FALHOU, chamada=chamada)
    return ResultadoDoRetrato(mensagem=_mensagem_do_retrato(saida), erro=None, chamada=chamada)


# ─── "Isso atende?" e o escopo ───────────────────────────────────────────────


def _ultimo_retrato(mensagens: list[dict]) -> int | None:
    for i in range(len(mensagens) - 1, -1, -1):
        if mensagens[i].get("tipo") == TIPO_DO_RETRATO:
            return i
    return None


def pergunta_de_atende(item: dict, indice: int) -> dict:
    """A pergunta que o codigo faz por item de Ja existe. A recomendada e o
    "nao atende": nada sai do pedido sem o sim do diretor."""
    return {
        "tipo": "pergunta",
        "contexto": f"Isso atende? Já existe desde a {item['versao']}: {item['item']}",
        "opcoes": [{"letra": "A", "texto": OPCAO_ATENDE}, {"letra": "B", "texto": OPCAO_NAO_ATENDE}],
        "recomendada": "B",
        "atende": indice,
    }


def proxima_pergunta_de_atende(mensagens: list[dict]) -> dict | None:
    """O proximo "isso atende?" do retrato mais recente, ou `None` quando todos
    ja foram feitos ou quando ha pergunta esperando resposta."""
    inicio = _ultimo_retrato(mensagens)
    if inicio is None or (mensagens and mensagens[-1].get("tipo") == "pergunta"):
        return None
    itens = mensagens[inicio].get("ja_existe") or []
    feitas = sum(1 for m in mensagens[inicio:] if m.get("tipo") == "pergunta" and "atende" in m)
    return pergunta_de_atende(itens[feitas], feitas) if feitas < len(itens) else None


def escopo(mensagens: list[dict]) -> dict | None:
    """O que o "isso atende?" decidiu no retrato mais recente: `saiu` com o
    sim (a opcao A), `continua` com qualquer outra resposta. Item ainda nao
    respondido fica fora das duas. `None` sem retrato."""
    inicio = _ultimo_retrato(mensagens)
    if inicio is None:
        return None
    itens = mensagens[inicio].get("ja_existe") or []
    saiu, continua = [], []
    depois = mensagens[inicio:]
    for i, mensagem in enumerate(depois):
        if mensagem.get("tipo") != "pergunta" or "atende" not in mensagem or i + 1 >= len(depois):
            continue
        resposta = depois[i + 1]
        if resposta.get("tipo") != "resposta" or not 0 <= mensagem["atende"] < len(itens):
            continue
        texto = itens[mensagem["atende"]]["item"]
        (saiu if resposta.get("opcao") == "A" else continua).append(texto)
    return {"saiu": saiu, "continua": continua}


# ─── "Atualizar o card" (issue #1558) ────────────────────────────────────────

# O marcador da Demanda como ele estiver na issue (o mesmo padrao do
# `prd_do_leitor` do fluxo): espaco a mais nao o torna outro marcador.
_MARCADOR_DA_DEMANDA = re.compile(r'<!--\s*demanda-vitta id="[^"]*"\s*-->')


def corpo_revisado(*, corpo_atual: str | None, corpo_novo: str, demanda_id: str) -> str:
    """O PRD revisado com o marcador da Demanda da issue, byte a byte.

    O corpo novo sai do `corpo_do_prd_do_diretor`, que escreve o marcador do
    jeito de hoje. Quem acha a Demanda pela issue (a reconciliacao, o
    `anexos.py`) le o PRIMEIRO marcador do corpo, e o que ja esta la e o que
    vale: ele substitui o escrito. Sem marcador na issue, fica o novo.
    """
    achado = _MARCADOR_DA_DEMANDA.search(corpo_atual or "")
    if achado is None:
        return corpo_novo
    return corpo_novo.replace(marcador_da_demanda(demanda_id), achado.group(0))


# As secoes do PRD do diretor que sao o escopo: as decisoes e o que ficou em
# aberto. O bloco "Para o diretor" e as historias repetem as decisoes, e a
# Origem nao e escopo.
_SECOES_DO_ESCOPO = ("Decisões de negócio", "Decisões de implementação", "Decisões de teste", "Ficou em aberto")
_PERGUNTA_DA_DECISAO = re.compile(r"^\d+\.\s+\*\*(.*)\*\*$")


def escopo_do_corpo(corpo: str | None) -> list[str]:
    """Os itens do escopo de um PRD do diretor, na ordem: cada decisao de
    negocio como "pergunta escolha", e cada item de lista das outras secoes."""
    itens: list[str] = []
    secao, pergunta = None, ""
    for bruta in (corpo or "").splitlines():
        linha = bruta.strip()
        if linha.startswith("## "):
            secao, pergunta = linha[3:].strip(), ""
            continue
        if secao not in _SECOES_DO_ESCOPO:
            continue
        if achada := _PERGUNTA_DA_DECISAO.match(linha):
            pergunta = achada.group(1).strip()
        elif linha.startswith("Escolha:"):
            itens.append(f"{pergunta} {linha.removeprefix('Escolha:').strip()}".strip())
        elif linha.startswith("- "):
            itens.append(linha[2:].strip())
    return list(dict.fromkeys(item for item in itens if item))


NADA_NO_COMENTARIO = "- Nada."


def comentario_da_atualizacao(
    *,
    corpo_antes: str | None,
    corpo_depois: str,
    saiu_por_atender: list[str],
    partes_fechadas: list[int],
    versao_base: str | None,
) -> str:
    """O comentario que o "Atualizar o card" deixa na issue-raiz: o que entrou
    e o que saiu do escopo, pela diferenca entre os dois corpos, mais o que ja
    existe e quem pediu disse que atende. A primeira linha o marca como do
    agente. O repositorio e publico: o item que veio do retrato passa pela
    mesma peneira do PRD."""
    antes, depois = escopo_do_corpo(corpo_antes), escopo_do_corpo(corpo_depois)
    entrou = [item for item in depois if item not in antes]
    saiu = [item for item in antes if item not in depois]
    saiu += [f"{' '.join(texto_do_diretor(item).split())} (já existe no app, e quem pediu disse que atende)"
             for item in saiu_por_atender]
    base = f", com o app na {versao_base}" if versao_base else ""
    linhas = [
        "<!-- automacao -->",
        f"O card foi atualizado pela Revisão com o código de hoje, na aba Tecnologia do app{base}.",
        "",
        "Entrou no escopo:",
        *([f"- {item}" for item in entrou] or [NADA_NO_COMENTARIO]),
        "",
        "Saiu do escopo:",
        *([f"- {item}" for item in saiu] or [NADA_NO_COMENTARIO]),
    ]
    if partes_fechadas:
        partes = ", ".join(f"#{n}" for n in partes_fechadas)
        linhas += ["", f"Partes que não tinham começado, fechadas como não planejadas: {partes}."]
    linhas += ["", "O card volta para a triagem, para um novo `/to-issues`."]
    return "\n".join(linhas)


# O motivo na parte que fecha. A primeira linha o marca como do agente.
COMENTARIO_DA_PARTE_FECHADA = (
    "<!-- automacao -->\n"
    "O card #{raiz} foi revisado com o código de hoje na aba Tecnologia do app, e esta parte ainda não "
    "tinha começado. Ela fecha como não planejada; as partes novas saem de um novo `/to-issues`."
)


class ParteJaComecouError(RuntimeError):
    """Uma parte do card esta em desenvolvimento: o card nao se atualiza."""


def _labels_da_issue(dados: dict) -> list[str]:
    return [str(label["name"]) for label in dados.get("labels") or [] if isinstance(label, dict) and label.get("name")]


def atualizar_no_github(
    numero: int,
    *,
    demanda_id: str,
    corpo_novo: str,
    saiu_por_atender: list[str],
    versao_base: str | None,
) -> list[int]:
    """Leva o PRD revisado a issue-raiz. Devolve as partes que fechou.

    Le a raiz e as partes NA HORA, e nao do cache da Demanda: a parte que pegou
    `in-progress` depois da ultima sincronizacao levanta `ParteJaComecouError`
    antes de qualquer escrita. Depois, pela ordem: o comentario (antes do
    corpo, que e de onde sai o "o que mudou"), as partes abertas fechadas como
    nao planejadas e, por ultimo, a raiz regravada. Falha do GitHub sobe como
    `GithubIndisponivelError`; o clique seguinte refaz o que faltou, e a parte
    ja fechada nao fecha de novo.
    """
    dados = github_client.ler_issue(numero)
    partes = [p for p in github_client.ler_sub_issues(numero) if isinstance(p, dict)]
    abertas = [p for p in partes if p.get("state") == "open" and isinstance(p.get("number"), int)]
    if any(LABEL_EM_ANDAMENTO in {n.lower() for n in _labels_da_issue(p)} for p in [dados, *abertas]):
        raise ParteJaComecouError(numero)
    fechadas = [p["number"] for p in abertas]

    corpo = corpo_revisado(corpo_atual=dados.get("body"), corpo_novo=corpo_novo, demanda_id=demanda_id)
    github_client.comentar(
        numero,
        comentario_da_atualizacao(
            corpo_antes=dados.get("body"),
            corpo_depois=corpo,
            saiu_por_atender=saiu_por_atender,
            partes_fechadas=fechadas,
            versao_base=versao_base,
        ),
    )
    for parte in fechadas:
        github_client.fechar_como_nao_planejada(parte, comentario=COMENTARIO_DA_PARTE_FECHADA.format(raiz=numero))
    github_client.regravar(numero, corpo=corpo, labels=_labels_da_issue(dados))
    return fechadas
