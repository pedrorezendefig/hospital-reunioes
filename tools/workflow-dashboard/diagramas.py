#!/usr/bin/env python3
"""Parse dos subsets Mermaid usados nos snapshots (ADR 0025).

O dashboard desenha os diagramas com renderer próprio em SVG na SPA; quem
extrai a estrutura dos blocos ```mermaid dos snapshots é este módulo, no
coletor. Bloco fora do subset (ou tipo ainda sem parser) degrada para código
cru, nunca quebra: a SPA mantém o fallback de sempre.

Parsers de hoje: `erDiagram` do SCHEMA.md; `sequenceDiagram`,
`stateDiagram-v2` e `flowchart` (ciclos de vida e pipeline de IA) do
FLUXOGRAMAS.md. Tipo novo entra registrando parser aqui, sem tocar na SPA.
"""

from __future__ import annotations

import re

_BLOCO_MERMAID = re.compile(r"```mermaid[ \t]*\r?\n(.*?)```", re.S)

# subset do erDiagram gerado pelo /snapshot:
#   relação    `origem ||--o{ destino : "coluna_fk"`
#   tabela     `nome {` ... `}` com linhas `TIPO nome [PK|FK|UK] ["comentário"]`
#   truncagem  `_ mais_colunas "+N"` (marca do gerador, vira `extras`)
_RELACAO = re.compile(
    r'^(\w+)\s+([|o}{.-]*(?:--|\.\.)[|o}{.-]*)\s+(\w+)\s*:\s*"([^"]*)"$'
)
_ABRE_TABELA = re.compile(r"^(\w+)\s*\{$")
_COLUNA = re.compile(r'^(\S+)\s+(\w+)(?:\s+(PK|FK|UK))?(?:\s+"([^"]*)")?$')
_MAIS_COLUNAS = re.compile(r"^\+(\d+)$")

# subset do sequenceDiagram curado no FLUXOGRAMAS.md:
#   participante  `participant ID as Nome legível` (o `as` é opcional)
#   mensagem      `A->>B: texto` (síncrona) ou `A-->>B: texto` (resposta)
_PARTICIPANTE = re.compile(r"^participant\s+(\w+)(?:\s+as\s+(.+?))?$")
_MENSAGEM = re.compile(r"^(\w+)\s*(--?>>)\s*(\w+)\s*:\s*(.+)$")

# subset do stateDiagram-v2 dos ciclos de vida curados:
#   transição  `A --> B: rótulo` (rótulo opcional), com `[*]` de inicial/final
_TRANSICAO = re.compile(r"^(\[\*\]|\w+)\s*-->\s*(\[\*\]|\w+)(?:\s*:\s*(.+?))?$")

# subset do flowchart TD curado no FLUXOGRAMAS.md (pipeline de IA):
#   aresta `A --> B` ou `A -- rotulo --> B`, onde cada ponta pode definir o
#   nó inline: passo `id[Texto<br/>linha 2]` ou decisão `id{Texto}`
_ARESTA_FLOW = re.compile(
    r"^(\w+)(?:\[([^\]]+)\]|\{([^}]+)\})?"
    r"\s*--(?:\s*(.+?)\s*--)?>\s*"
    r"(\w+)(?:\[([^\]]+)\]|\{([^}]+)\})?$"
)
_QUEBRA = re.compile(r"<br\s*/?>")


def extrair_diagramas(body_md: str | None) -> list[dict]:
    """Todos os blocos ```mermaid do markdown, parseados na ordem em que aparecem."""
    return [parse_bloco(m.group(1)) for m in _BLOCO_MERMAID.finditer(body_md or "")]


def parse_bloco(codigo: str) -> dict:
    """Um bloco Mermaid → estrutura JSON, ou fallback de código cru."""
    try:
        linhas = [linha.strip() for linha in codigo.splitlines() if linha.strip()]
        if linhas and linhas[0] == "erDiagram":
            er = _parse_er(linhas[1:])
            if er is not None:
                return er
        if linhas and linhas[0] == "sequenceDiagram":
            seq = _parse_seq(linhas[1:])
            if seq is not None:
                return seq
        if linhas and linhas[0] == "stateDiagram-v2":
            estado = _parse_estado(linhas[1:])
            if estado is not None:
                return estado
        if linhas and linhas[0] == "flowchart TD":
            flow = _parse_flow(linhas[1:])
            if flow is not None:
                return flow
    except Exception:
        pass  # o contrato do módulo: parse nunca quebra, degrada para código cru
    return {"tipo": "codigo", "codigo": codigo}


def _parse_estado(linhas: list[str]) -> dict | None:
    """Corpo do stateDiagram-v2 → estados + transições rotuladas; None se sair do subset."""
    estados: list[str] = []
    transicoes: list[dict] = []

    for linha in linhas:
        m = _TRANSICAO.match(linha)
        if not m:
            return None
        origem, destino, rotulo = m.group(1), m.group(2), (m.group(3) or "").strip()
        transicoes.append({"origem": origem, "destino": destino, "rotulo": rotulo})
        for nome in (origem, destino):
            if nome != "[*]" and nome not in estados:
                estados.append(nome)

    if not transicoes:
        return None
    return {"tipo": "estado", "estados": estados, "transicoes": transicoes}


def _parse_flow(linhas: list[str]) -> dict | None:
    """Corpo do flowchart TD → nós (passo/decisão) + arestas rotuladas; None fora do subset."""
    nos: dict[str, dict] = {}
    arestas: list[dict] = []

    def registrar(nid: str, passo: str | None, decisao: str | None) -> None:
        no = nos.setdefault(nid, {"id": nid, "linhas": [nid], "decisao": False})
        texto = passo if passo is not None else decisao
        if texto is not None:
            partes = [parte.strip() for parte in _QUEBRA.split(texto)]
            # <br/> sobrando (no fim ou dobrado) não vira linha em branco no desenho
            no["linhas"] = [parte for parte in partes if parte] or [nid]
            no["decisao"] = decisao is not None

    for linha in linhas:
        m = _ARESTA_FLOW.match(linha)
        if not m:
            return None
        origem, o_passo, o_dec, rotulo, destino, d_passo, d_dec = m.groups()
        registrar(origem, o_passo, o_dec)
        registrar(destino, d_passo, d_dec)
        arestas.append(
            {"origem": origem, "destino": destino, "rotulo": (rotulo or "").strip()}
        )

    if not arestas:
        return None
    return {"tipo": "flow", "nos": list(nos.values()), "arestas": arestas}


def _parse_er(linhas: list[str]) -> dict | None:
    """Corpo do erDiagram → tabelas (colunas/PK/FK) + relações; None se sair do subset."""
    tabelas: dict[str, dict] = {}
    relacoes: list[dict] = []
    atual: dict | None = None

    for linha in linhas:
        if atual is None:
            m = _ABRE_TABELA.match(linha)
            if m:
                atual = {"nome": m.group(1), "colunas": [], "extras": 0}
                tabelas[atual["nome"]] = atual
                continue
            m = _RELACAO.match(linha)
            if m:
                relacoes.append(
                    {
                        "origem": m.group(1),
                        "destino": m.group(3),
                        "rotulo": m.group(4),
                        "cardinalidade": m.group(2),
                    }
                )
                continue
            return None
        if linha == "}":
            atual = None
            continue
        m = _COLUNA.match(linha)
        if not m:
            return None
        tipo, nome, chave, comentario = m.groups()
        truncagem = _MAIS_COLUNAS.match(comentario or "")
        if nome == "mais_colunas" and truncagem:
            atual["extras"] = int(truncagem.group(1))
            continue
        atual["colunas"].append(
            {"nome": nome, "tipo": tipo, "pk": chave == "PK", "fk": chave == "FK"}
        )

    if atual is not None:  # tabela sem fechar
        return None

    # tabela só citada em relação também existe no desenho (sem colunas conhecidas)
    for r in relacoes:
        for nome in (r["origem"], r["destino"]):
            tabelas.setdefault(nome, {"nome": nome, "colunas": [], "extras": 0})

    return {"tipo": "er", "tabelas": list(tabelas.values()), "relacoes": relacoes}


def _parse_seq(linhas: list[str]) -> dict | None:
    """Corpo do sequenceDiagram → participantes ordenados + mensagens; None se sair do subset."""
    participantes: dict[str, dict] = {}
    mensagens: list[dict] = []

    for linha in linhas:
        m = _PARTICIPANTE.match(linha)
        if m:
            pid, nome = m.groups()
            participantes.setdefault(pid, {"id": pid, "nome": nome or pid})
            continue
        m = _MENSAGEM.match(linha)
        if not m:
            return None
        de, seta, para, texto = m.groups()
        # participante usado sem declarar existe no desenho, na ordem do primeiro uso
        for pid in (de, para):
            participantes.setdefault(pid, {"id": pid, "nome": pid})
        mensagens.append({"de": de, "para": para, "texto": texto.strip(), "seta": seta})

    if not mensagens:  # sequência sem mensagem não é o diagrama que o renderer desenha
        return None
    return {
        "tipo": "seq",
        "participantes": list(participantes.values()),
        "mensagens": mensagens,
    }
