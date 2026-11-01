"""O PRD do diretor no terminal (issue #1350, ADR 0075, decisão 1).

O "sim" do Planejamento da Demanda, na aba Tecnologia, cria uma issue
`needs-triage` com a metade de negócio do PRD: o bloco "Para o diretor",
Problema, Solução, Histórias, Decisões de negócio e "Ficou em aberto", com o
marcador da Demanda no fim. As seções técnicas nascem aqui, no terminal, na
mesma issue.

Uso:
  python3 prd_do_diretor.py ler <N>                 roteiro do /grill-with-docs #N
  python3 prd_do_diretor.py completar <N> <arquivo>  o /to-prd completa a issue

`ler` só lê. `completar` insere as seções técnicas do arquivo antes da Origem,
sem tocar no resto do corpo, e troca `needs-triage` por `ready-for-agent`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

CABECALHO_DO_BLOCO = "## 👔 Para o diretor"
MARCADOR_DA_DEMANDA = re.compile(r'<!--\s*demanda-vitta id="[^"]*"\s*-->')
TITULO_TOMADAS = "Já decidido pelo diretor (não pergunte de novo):"
TITULO_EM_ABERTO = "Ficou em aberto (o grill técnico começa por aqui):"
NAO_E_PRD_DO_DIRETOR = (
    "Não é PRD do diretor (sem o marcador da Demanda ou sem a seção \"Ficou em aberto\"): "
    "siga o /grill-with-docs normal."
)
SECOES_OBRIGATORIAS = ("Decisões de implementação", "Decisões de teste")


def _secao(corpo: str, titulo: str) -> str | None:
    """O texto de uma seção `## titulo` até o próximo `## ` ou o marcador."""
    m = re.search(rf"^## {re.escape(titulo)}\s*$", corpo, re.M)
    if not m:
        return None
    resto = corpo[m.end() :]
    fim = re.search(r"^## |<!--", resto, re.M)
    return (resto[: fim.start()] if fim else resto).strip()


def ler(corpo: str) -> dict:
    em_aberto = _secao(corpo, "Ficou em aberto")
    return {
        "prd_do_diretor": bool(MARCADOR_DA_DEMANDA.search(corpo)) and em_aberto is not None,
        "decisoes": _secao(corpo, "Decisões de negócio") or "",
        "em_aberto": [
            linha[2:].strip() for linha in (em_aberto or "").splitlines() if linha.startswith("- ")
        ],
        "completo": _secao(corpo, "Decisões de implementação") is not None,
    }


def roteiro_do_grill(corpo: str) -> str:
    """O que o /grill-with-docs #N mostra antes da primeira pergunta."""
    lido = ler(corpo)
    if not lido["prd_do_diretor"]:
        return NAO_E_PRD_DO_DIRETOR
    linhas = [TITULO_TOMADAS, "", lido["decisoes"] or "(nenhuma)", "", TITULO_EM_ABERTO, ""]
    linhas += [f"- {item}" for item in lido["em_aberto"]] or ["(nada; vá direto às perguntas técnicas)"]
    if lido["completo"]:
        linhas += ["", "Atenção: a issue já tem Decisões de implementação; o /to-prd já passou por ela."]
    return "\n".join(linhas)


def completar(corpo: str, secoes: str) -> str:
    """O corpo com as seções técnicas antes da Origem; o resto fica byte a byte."""
    lido = ler(corpo)
    if not lido["prd_do_diretor"]:
        raise ValueError("a issue não é PRD do diretor; use o /to-prd normal")
    if lido["completo"]:
        raise ValueError("a issue já tem Decisões de implementação")
    for titulo in SECOES_OBRIGATORIAS:
        if _secao(secoes, titulo) is None:
            raise ValueError(f"faltou a seção ## {titulo}")
    if "Para o diretor" in secoes:
        raise ValueError('o bloco "Para o diretor" é do app; as seções técnicas não o reescrevem')
    bloco = secoes.strip() + "\n\n"
    origem = re.search(r"^## Origem\s*$", corpo, re.M) or MARCADOR_DA_DEMANDA.search(corpo)
    return corpo[: origem.start()] + bloco + corpo[origem.start() :]


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def main(argv: list[str], gh=_gh) -> int:
    if len(argv) >= 2 and argv[0] == "ler":
        print(roteiro_do_grill(gh("issue", "view", argv[1], "--json", "body", "-q", ".body")))
        return 0
    if len(argv) == 3 and argv[0] == "completar":
        numero = argv[1]
        corpo = gh("issue", "view", numero, "--json", "body", "-q", ".body")
        try:
            novo = completar(corpo, Path(argv[2]).read_text(encoding="utf-8"))
        except ValueError as erro:
            print(f"não completei a #{numero}: {erro}", file=sys.stderr)
            return 1
        with tempfile.NamedTemporaryFile("w", suffix=".md", encoding="utf-8", delete=False) as f:
            f.write(novo)
        try:
            gh(
                "issue", "edit", numero, "--body-file", f.name,
                "--remove-label", "needs-triage", "--add-label", "ready-for-agent",
            )
        finally:
            Path(f.name).unlink(missing_ok=True)
        print(f"PRD do diretor #{numero} completado com as seções técnicas.")
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
