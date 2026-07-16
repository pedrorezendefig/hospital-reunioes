#!/usr/bin/env python3
"""Parse dos subsets Mermaid usados nos snapshots (ADR 0025).

O dashboard desenha os diagramas com renderer próprio em SVG na SPA; quem
extrai a estrutura dos blocos ```mermaid dos snapshots é este módulo, no
coletor. Bloco fora do subset (ou tipo ainda sem parser) degrada para código
cru, nunca quebra: a SPA mantém o fallback de sempre.

Hoje só o `erDiagram` do SCHEMA.md tem parser; os subsets dos diagramas
curados (stateDiagram-v2, sequenceDiagram, flowchart) entram nas fatias
seguintes do PRD #212 registrando novos parsers em `_PARSERS`.
"""

from __future__ import annotations

import re

_BLOCO_MERMAID = re.compile(r"```mermaid[ \t]*\r?\n(.*?)```", re.S)

# subset do erDiagram gerado pelo /snapshot:
#   relação    `origem ||--o{ destino : "coluna_fk"`
#   tabela     `nome {` ... `}` com linhas `TIPO nome [PK|FK|UK] ["comentário"]`
#   truncagem  `_ mais_colunas "+N"` (marca do gerador, vira `extras`)
_RELACAO = re.compile(r'^(\w+)\s+([|o}{.-]*(?:--|\.\.)[|o}{.-]*)\s+(\w+)\s*:\s*"([^"]*)"$')
_ABRE_TABELA = re.compile(r"^(\w+)\s*\{$")
_COLUNA = re.compile(r'^(\S+)\s+(\w+)(?:\s+(PK|FK|UK))?(?:\s+"([^"]*)")?$')
_MAIS_COLUNAS = re.compile(r"^\+(\d+)$")


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
    except Exception:
        pass  # o contrato do módulo: parse nunca quebra, degrada para código cru
    return {"tipo": "codigo", "codigo": codigo}


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
        atual["colunas"].append({"nome": nome, "tipo": tipo, "pk": chave == "PK", "fk": chave == "FK"})

    if atual is not None:  # tabela sem fechar
        return None

    # tabela só citada em relação também existe no desenho (sem colunas conhecidas)
    for r in relacoes:
        for nome in (r["origem"], r["destino"]):
            tabelas.setdefault(nome, {"nome": nome, "colunas": [], "extras": 0})

    return {"tipo": "er", "tabelas": list(tabelas.values()), "relacoes": relacoes}
