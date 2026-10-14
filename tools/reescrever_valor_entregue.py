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
# o par vira uma linha só, com ou sem linha em branco entre as duas metades
_ANTES_DEPOIS = re.compile(r"(?m)^\*\*Antes:\*\*[^\n]*\n(?:[ \t]*\n)*\*\*Depois:\*\*[^\n]*")


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
    linha = f"**O que muda:** {paragrafo.strip()}"
    span = _secao_valor(body)
    if span:
        ini, fim = span
        conteudo, n = _ANTES_DEPOIS.subn(lambda _: linha, body[ini:fim], count=1)
        if not n:
            raise ValueError("seção Valor entregue sem Antes e Depois")
        return body[:ini] + conteudo + body[fim:]
    topo = len(MARCADOR) if body.startswith(MARCADOR) else 0
    return body[:topo] + "## 💬 Valor entregue\n\n" + linha + "\n\n" + body[topo:]


def _gh(args: list[str], entrada: str | None = None) -> str:
    return subprocess.run(["gh", *args], input=entrada, capture_output=True, text=True, check=True).stdout


def _janela(gh) -> list[dict]:
    return json.loads(gh(["pr", "list", "--state", "all", "--limit", JANELA, "--json", "number,title,body"]))


def _fontes(prs: list[dict]) -> dict:
    """O que o redator do parágrafo lê, só dos PRs ainda não reescritos."""
    fontes = {}
    for pr in prs:
        body = pr.get("body") or ""
        if ja_reescrito(body):
            continue
        # só o par da seção Valor entregue: o par da Evidência fala de teste, não de valor
        span = _secao_valor(body)
        secao = body[span[0] : span[1]] if span else ""
        antes = re.search(r"\*\*Antes:\*\*\s*(.+)", secao)
        depois = re.search(r"\*\*Depois:\*\*\s*(.+)", secao)
        fontes[str(pr["number"])] = {
            "titulo": pr.get("title"),
            "antes": antes.group(1).strip() if antes else None,
            "depois": depois.group(1).strip() if depois else None,
            "corpo": None if antes or depois else body[:1500],
        }
    return fontes


def main(argv: list[str] | None = None, gh=_gh) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fontes", help="grava as fontes dos PRs ainda não reescritos neste JSON e sai")
    ap.add_argument("--paragrafos", help='JSON {"<número do PR>": "<parágrafo O que muda>"}')
    ap.add_argument("--dry-run", action="store_true", help="imprime o diff de cada PR e não grava nada")
    args = ap.parse_args(argv)
    if not (args.fontes or args.paragrafos):
        ap.error("informe --fontes ou --paragrafos")

    prs = _janela(gh)
    if args.fontes:
        with open(args.fontes, "w", encoding="utf-8") as f:
            json.dump(_fontes(prs), f, ensure_ascii=False, indent=1)
        return 0
    with open(args.paragrafos, encoding="utf-8") as f:
        paragrafos = json.load(f)

    faltando = 0
    for pr in prs:
        numero, body = pr["number"], pr.get("body") or ""
        if ja_reescrito(body):
            print(f"#{numero}: já reescrito")
            continue
        if str(numero) not in paragrafos:
            print(f"#{numero}: sem parágrafo, não gravado")
            faltando += 1
            continue
        novo = reescrever_corpo(body, paragrafos[str(numero)])
        if args.dry_run:
            diff = difflib.unified_diff(
                body.splitlines(keepends=True),
                novo.splitlines(keepends=True),
                f"PR #{numero} (atual)",
                f"PR #{numero} (novo)",
                n=1,
            )
            sys.stdout.writelines(linha if linha.endswith("\n") else linha + "\n" for linha in diff)
            continue
        gh(
            ["api", "-X", "PATCH", f"repos/{{owner}}/{{repo}}/pulls/{numero}", "--input", "-"],
            json.dumps({"body": novo}),
        )
        print(f"#{numero}: gravado")
    return 1 if faltando else 0


if __name__ == "__main__":
    sys.exit(main())
