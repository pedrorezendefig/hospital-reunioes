#!/usr/bin/env python3
"""As Lentes que o revisor da Onda lê num PR, pelos arquivos dele e pela configuração do Projeto.

Uso:
    python3 lentes.py <arquivo...>   # arquivos do PR, caminho a partir da raiz do repo
    python3 lentes.py --pr <N>       # o mesmo, com os arquivos do PR (gh pr diff --name-only)

Saída: uma linha `<lente>\t<arquivo da Lente>\t(<motivo>)` por Lente escolhida e, por
último, a linha `Lentes: <nomes>` (ou `Lentes: nenhuma`), que o revisor copia no veredito.
Exit 0 com a resposta, 2 com o motivo no stderr.

- banco: o PR tem arquivo na pasta `migrations.pasta` do `fluxo.json`.
- seguranca: o PR toca arquivo de login, permissão, rota ou segredo (pelo nome) ou
  arquivo da lista `revisao-sensivel.txt` do Projeto.
- design: o Projeto tem `design.guia` no `fluxo.json` e o PR muda tela (componente, página ou
  estilo na pasta do app, fora dos testes). O passo a passo é o `design.py`.

Cada Lente é um arquivo curto em `../lentes/<nome>.md`, com teto de tamanho (`TETO`, em
caracteres): o revisor lê a Lente inteira a cada PR, e o teste do pacote barra a que passa dele.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fluxo  # noqa: E402
from sensivel import casa, ler_globs  # noqa: E402

PASTA = Path(__file__).resolve().parent.parent / "lentes"
LISTA = Path(__file__).resolve().parent.parent / "revisao-sensivel.txt"
TETO = 1500
# Nome de arquivo ou pasta que fala de login, permissão, rota ou segredo.
DE_SEGURANCA = re.compile(
    r"auth|login|logout|senha|password|permiss|sess(ao|ion)|token|segredo|secret|credencia|seguranca|security"
    r"|middleware|polic|(?<![a-z])rls|(?<![a-z])rotas?(?![a-z])|routes?(?![a-z])|routers?(?![a-z])|(^|/)\.env"
)
# Arquivo de tela: componente, página ou estilo. Teste não muda tela.
DE_TELA = re.compile(r"\.(tsx|jsx|vue|svelte|astro|html|css|scss|sass|less)$")
DE_TESTE = re.compile(r"(^|/)(tests?|__tests__)/|\.(test|spec)\.")


def _pasta_de_migrations(cfg: dict) -> str | None:
    pasta = (cfg.get("migrations") or {}).get("pasta")
    return pasta.rstrip("/") + "/" if pasta else None


def acima_do_teto(pasta: Path = PASTA) -> list[Path]:
    """As Lentes da pasta que passam do teto de tamanho."""
    return [p for p in sorted(Path(pasta).glob("*.md")) if len(p.read_text(encoding="utf-8")) > TETO]


def escolher(arquivos: list[str], cfg: dict) -> list[tuple[str, str]]:
    """(lente, motivo) de cada Lente que o PR recebe, na ordem em que o revisor lê."""
    arquivos = [a.replace("\\", "/") for a in arquivos]
    escolhidas = []
    migrations = _pasta_de_migrations(cfg)
    if migrations:
        com_migration = [a for a in arquivos if a.startswith(migrations)]
        if com_migration:
            escolhidas.append(("banco", "migration: " + ", ".join(com_migration)))
    globs = [g for g, _ in ler_globs(LISTA)] if LISTA.exists() else []
    de_seguranca = [a for a in arquivos if DE_SEGURANCA.search(a.lower()) or any(casa(a, g) for g in globs)]
    if de_seguranca:
        escolhidas.append(("seguranca", "login, permissão, rota ou segredo: " + ", ".join(de_seguranca)))
    if (cfg.get("design") or {}).get("guia"):
        de_tela = [a for a in arquivos if a.startswith(cfg["app"]) and DE_TELA.search(a) and not DE_TESTE.search(a)]
        if de_tela:
            escolhidas.append(("design", "tela: " + ", ".join(de_tela)))
    return escolhidas


def main(argv: list[str]) -> int:
    for saida in (sys.stdout, sys.stderr):
        saida.reconfigure(encoding="utf-8")
    try:
        cfg = fluxo.carregar()
        arquivos = fluxo._arquivos_do_pr(argv[1]) if argv[:1] == ["--pr"] and len(argv) == 2 else argv
        escolhidas = escolher(arquivos, cfg)
    except (fluxo.Erro, subprocess.CalledProcessError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    raiz = fluxo.raiz()
    for nome, motivo in escolhidas:
        arquivo = PASTA / f"{nome}.md"
        try:
            caminho = arquivo.relative_to(raiz)
        except ValueError:
            caminho = arquivo
        print(f"{nome}\t{caminho}\t({motivo})")
    print("Lentes: " + (", ".join(nome for nome, _ in escolhidas) or "nenhuma"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
