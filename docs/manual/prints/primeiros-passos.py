#!/usr/bin/env python3
"""Roteiro de prints do módulo Primeiros passos (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

As duas telas daqui são **abertas, sem conta**: a entrada e o pedido de
redefinição de senha. Por isso o roteiro não entra na plataforma, não semeia
dado nenhum e não toca no banco. Isso também é o que garante que nenhuma
imagem carregue dado de pessoa real, que num repositório público é bloqueante.

As telas de dentro (Meu Perfil, Configurações) exigem conta com dados reais do
banco local e ficaram sem print de propósito.

Receita:

1. Stack do app no ar em `http://localhost:3000`
   (`bash .claude/skills/atualizar-app/scripts/apply.sh`).
2. `python3 docs/manual/prints/primeiros-passos.py`.

Uso: python3 docs/manual/prints/primeiros-passos.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/primeiros-passos] [--print <nome>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# O Playwright só é preciso para capturar: importar este arquivo numa máquina
# sem navegador instalado continua funcionando.
if TYPE_CHECKING:
    from playwright.sync_api import Page

# Tela de trabalho sentada: a entrada na plataforma se faz no computador.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2


# --------------------------------------------------------------------------
# Prints
# --------------------------------------------------------------------------


def tela_de_entrada(page: Page, base: str, saida: Path) -> None:
    """A porta da plataforma, com os dois campos e o link de senha esquecida."""
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_role("heading", name="Bem-vindo de volta").wait_for()
    # Sem foco em campo nenhum: o anel de foco numa captura parada vira
    # instrução falsa ("clique aqui") para quem lê a página.
    page.get_by_role("heading", name="Bem-vindo de volta").click()
    page.screenshot(path=str(saida / "tela-de-entrada.png"))


def esqueci_minha_senha(page: Page, base: str, saida: Path) -> None:
    """O pedido do link de redefinição, com o único campo que ele precisa."""
    page.goto(f"{base}/reset-password", wait_until="networkidle")
    page.get_by_role("heading", name="Esqueci minha senha").wait_for()
    page.get_by_role("heading", name="Esqueci minha senha").click()
    page.screenshot(path=str(saida / "esqueci-minha-senha.png"))


PRINTS = {
    "tela-de-entrada": tela_de_entrada,
    "esqueci-minha-senha": esqueci_minha_senha,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/primeiros-passos")
    ap.add_argument(
        "--print",
        dest="escolhido",
        choices=sorted(PRINTS),
        help="captura só um print; sem isto, o roteiro inteiro roda.",
    )
    args = ap.parse_args()

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else sorted(PRINTS)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(
            viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR"
        )
        page = contexto.new_page()
        for nome in escolhidos:
            PRINTS[nome](page, args.base.rstrip("/"), saida)
            print(f"print: {saida / (nome + '.png')}")
        navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
