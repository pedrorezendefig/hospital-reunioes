#!/usr/bin/env python3
"""Roteiro de prints do módulo Ouvidoria (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

Receita (a mesma do manual antigo da Ouvidoria, issue #563):

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Tela sem login (formulário público) não precisa de mais nada. Tela de dentro
   do app precisa de login como ouvidor (`admin@hospital.com`, senha do
   `DEFAULT_USER_PASSWORD` do `.env` local, nunca de produção).
4. `python3 docs/manual/prints/ouvidoria.py`.

Lista `<select>`: o menu nativo do sistema não sai na captura. Antes do
screenshot, transforme o campo em lista visível (`el.size = <n>`) e recorte a
área dele.

Uso: python3 docs/manual/prints/ouvidoria.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/ouvidoria] [--print <nome>]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# Celular primeiro: o formulário público nasce do QR do cartaz, e é assim que a
# pessoa vê a tela. O dobro de escala deixa o texto legível no print.
CELULAR = {"width": 390, "height": 844}
ESCALA = 2

RELATO_DE_EXEMPLO = (
    "Fui muito bem atendida na recepção da Farmácia hoje de manhã. "
    "A atendente explicou com calma como retirar o medicamento e ainda "
    "conferiu a receita comigo. Queria registrar o elogio."
)


def formulario_publico(page: Page, base: str, saida: Path) -> None:
    """A tela que o QR do cartaz abre, preenchida como uma pessoa preencheria."""
    page.goto(f"{base}/manifestacao", wait_until="networkidle")
    page.get_by_role("button", name="Elogio").click()
    page.get_by_label("O que aconteceu?").fill(RELATO_DE_EXEMPLO)
    page.get_by_label("Seu nome").fill("Marina Alves")
    page.get_by_label("Telefone ou email").fill("marina.alves@exemplo.com")
    # Sem foco em campo nenhum: o anel de foco no print vira instrução falsa
    # ("clique aqui") na hora que a pessoa lê a página.
    page.get_by_role("heading", name="Ouvidoria").click()
    page.screenshot(path=str(saida / "formulario-publico.png"), full_page=True)


PRINTS = {"formulario-publico": formulario_publico}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/ouvidoria")
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

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(
            viewport=CELULAR, device_scale_factor=ESCALA, locale="pt-BR"
        )
        page = contexto.new_page()
        for nome in escolhidos:
            PRINTS[nome](page, args.base.rstrip("/"), saida)
            print(f"print: {saida / (nome + '.png')}")
        navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
