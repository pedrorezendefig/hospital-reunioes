#!/usr/bin/env python3
"""Reescreve, uma vez, a seção Valor entregue dos PRs da janela do Hospital OS
(issue #1222, ADR 0071, decisão 4).

O par `**Antes:**`/`**Depois:**` vira o parágrafo `**O que muda:**`; PR sem a
seção ganha uma no topo (depois do marcador `<!-- automacao -->`, que fica na
primeira linha). O resto do corpo fica byte a byte igual. PR que já tem o
parágrafo é pulado, então rodar de novo não muda nada.

O parágrafo não nasce aqui: é texto para fora, escrito a partir das fontes
(`--fontes`) e passado pelo humanizer, e chega pronto em `--paragrafos`.

Uso:
    python3 tools/reescrever_valor_entregue.py --fontes /tmp/fontes.json
    python3 tools/reescrever_valor_entregue.py --paragrafos <json> --dry-run
    python3 tools/reescrever_valor_entregue.py --paragrafos <json>
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys

# a mesma janela do coletor do Hospital OS (RESUMO_LIMIT do collect.py)
JANELA = "200"
MARCADOR = "<!-- automacao -->\n"
_TITULO_VALOR = re.compile(r"(?m)^##[^\n]*Valor entregue[^\n]*\n")
_PROXIMO_TITULO = re.compile(r"(?m)^## ")
_ANTES_DEPOIS = re.compile(r"(?m)(?:^\*\*(?:Antes|Depois):\*\*[^\n]*(?:\n|\Z))+")


def _secao_valor(body: str) -> tuple[int, int] | None:
    """Início e fim do conteúdo da seção Valor entregue (sem o título)."""
    m = _TITULO_VALOR.search(body)
    if not m:
        return None
    prox = _PROXIMO_TITULO.search(body, m.end())
    return m.end(), prox.start() if prox else len(body)


def ja_reescrito(body: str | None) -> bool:
    span = _secao_valor(body or "")
    return bool(span) and "**O que muda:**" in (body or "")[span[0] : span[1]]


def reescrever_corpo(body: str | None, paragrafo: str) -> str | None:
    """Corpo novo, ou None se o PR já tem o parágrafo."""
    body = body or ""
    if ja_reescrito(body):
        return None
    linha = f"**O que muda:** {paragrafo.strip()}\n"
    span = _secao_valor(body)
    if span:
        ini, fim = span
        conteudo, n = _ANTES_DEPOIS.subn(linha, body[ini:fim], count=1)
        if not n:
            raise ValueError("seção Valor entregue sem Antes e Depois")
        return body[:ini] + conteudo + body[fim:]
    topo = len(MARCADOR) if body.startswith(MARCADOR) else 0
    return body[:topo] + "## 💬 Valor entregue\n\n" + linha + "\n" + body[topo:]
