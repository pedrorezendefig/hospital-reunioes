#!/usr/bin/env python3
"""Lint do Manual do usuário (docs/manual/src/content/docs).

Trava a publicação quando o texto que o usuário lê sai do padrão do ADR 0057:
- travessão (U+2014) e meia-risca (U+2013) em qualquer página (ADR 0013);
- jargão técnico em texto visível (mesma lista do gate anti-técnica da /divulgar);
- frontmatter obrigatório faltando.

Avisa, sem travar, quando uma Página de tarefa passa de 250 palavras.

Sem dependências externas. Uso: python3 tools/lint_manual.py [--dir <pasta>]
Sai com código 1 se houver qualquer erro.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

TRAVESSAO = "\u2014"
MEIA_RISCA = "\u2013"

# Mesma lista do gate anti-técnica da /divulgar: palavra de engenharia que o
# usuário do hospital não deve encontrar no manual (ADR 0057, decisão 10).
JARGAO = [
    "migration",
    "endpoint",
    "API",
    "PR",
    "pull request",
    "deploy",
    "RLS",
    "schema",
    "backend",
    "frontend",
    "commit",
    "branch",
    "merge",
    "token",
    "env",
    "SQL",
    "Supabase",
    "Coolify",
    "prompt",
]
RE_JARGAO = re.compile(
    r"\b(" + "|".join(re.escape(j) for j in JARGAO) + r")\b", re.IGNORECASE
)


def ler_frontmatter(texto: str) -> dict[str, str]:
    """Campos de primeiro nível do frontmatter YAML (valor cru, como string)."""
    if not texto.startswith("---\n"):
        return {}
    fim = texto.find("\n---", 3)
    if fim == -1:
        return {}
    campos: dict[str, str] = {}
    for linha in texto[4:fim].splitlines():
        if linha.startswith((" ", "\t", "#")) or ":" not in linha:
            continue
        chave, _, valor = linha.partition(":")
        campos[chave.strip().lower()] = valor.strip()
    return campos


def texto_visivel(texto: str) -> str:
    """O que a pessoa lê na página: sem frontmatter, código, comentário nem marcação.

    Jargão em bloco de código, em atributo de tag ou no alvo de um link não é
    texto visível: travar nisso faria o lint mandar reescrever o que ninguém lê.
    """
    if texto.startswith("---\n"):
        fim = texto.find("\n---", 3)
        if fim != -1:
            texto = texto[fim + 4 :]
    texto = re.sub(r"```.*?```", " ", texto, flags=re.S)
    texto = re.sub(r"`[^`]*`", " ", texto)
    texto = re.sub(r"<!--.*?-->", " ", texto, flags=re.S)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\]\([^)]*\)", "] ", texto)
    return texto


# Páginas de módulo que não são Página de tarefa: a Visão geral, as Novidades e
# o grupo Como funciona. Elas não têm quem faz, então não levam selo.
RESERVADOS = {"index", "novidades"}
GRUPO_COMO_FUNCIONA = "como-funciona"
# Teto da Página de tarefa (ADR 0057, decisão 10): acima disso, aviso.
TETO_DE_PALAVRAS = 250


def e_pagina_de_tarefa(relativo: Path) -> bool:
    """Página de tarefa é a unidade do manual: uma ação dentro de um módulo."""
    if len(relativo.parts) < 2:
        return False  # home do site
    if relativo.stem in RESERVADOS:
        return False
    return GRUPO_COMO_FUNCIONA not in relativo.parts[:-1]


def checar(pasta: Path) -> tuple[list[str], list[str]]:
    """Roda todas as regras. Devolve (erros, avisos)."""
    erros: list[str] = []
    avisos: list[str] = []
    for arquivo in sorted(pasta.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        relativo = arquivo.relative_to(pasta)
        nome = str(relativo)

        campos = ler_frontmatter(texto)
        if len(relativo.parts) > 1:
            obrigatorios = ["title", "prd", "draft"]
            if e_pagina_de_tarefa(relativo):
                obrigatorios.append("papel")
            faltando = [c for c in obrigatorios if not campos.get(c)]
            if faltando:
                erros.append(
                    f"{nome}: frontmatter sem {', '.join(faltando)}. "
                    "Toda página de módulo declara title, prd e draft; "
                    "a Página de tarefa declara também papel (ADR 0057)."
                )
        for linha_num, linha in enumerate(texto.splitlines(), start=1):
            if TRAVESSAO in linha or MEIA_RISCA in linha:
                erros.append(
                    f"{nome}:{linha_num}: travessão ou meia-risca no texto. "
                    "Use vírgula, dois-pontos ou hífen (ADR 0013)."
                )
        visivel = texto_visivel(texto)
        achados = sorted({m.group(1).lower() for m in RE_JARGAO.finditer(visivel)})
        for palavra in achados:
            erros.append(
                f"{nome}: jargão técnico em texto visível: '{palavra}'. "
                "Escreva o que a pessoa faz na tela (ADR 0057, decisão 10)."
            )

        if e_pagina_de_tarefa(relativo):
            palavras = len(visivel.split())
            if palavras > TETO_DE_PALAVRAS:
                avisos.append(
                    f"{nome}: {palavras} palavras, acima do teto de "
                    f"{TETO_DE_PALAVRAS}. Página de tarefa cabe numa tela de "
                    "celular; passou disso, são duas tarefas."
                )
    return erros, avisos


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual/src/content/docs")
    args = ap.parse_args()

    pasta = Path(args.dir)
    if not pasta.is_dir():
        print(f"Lint do Manual: pasta '{pasta}' não existe.", file=sys.stderr)
        return 1

    erros, avisos = checar(pasta)
    for aviso in avisos:
        print(f"aviso: {aviso}")
    if erros:
        print(
            "Lint do Manual falhou:\n" + "\n".join(f"  - {e}" for e in erros),
            file=sys.stderr,
        )
        return 1
    print(f"Lint do Manual OK ({len(list(pasta.rglob('*.md*')))} páginas).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
