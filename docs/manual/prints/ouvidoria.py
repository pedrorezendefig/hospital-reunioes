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

**Endereço impresso.** O app local monta cartaz, QR e e-mail com a base do
`FRONTEND_URL` dele, que é `http://localhost:3000`. Um cartaz com esse endereço
vai para a parede do hospital e não abre para ninguém, e foi isso que a
auditoria do PRD #731 encontrou publicado. O que a base do endereço muda é o
documento, não a tela, então o cartaz e o e-mail são montados aqui pelo código
do próprio app, num processo à parte, com a base de produção. O resto continua
saindo do navegador contra o app local.

Uso: python3 docs/manual/prints/ouvidoria.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/ouvidoria] [--print <nome>]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import textwrap
from pathlib import Path

# Celular primeiro: o formulário público nasce do QR do cartaz, e é assim que a
# pessoa vê a tela. O dobro de escala deixa o texto legível no print.
CELULAR = {"width": 390, "height": 844}
ESCALA = 2

# A base do app em produção. Não é chute nem o endereço do manual: é o domínio
# do frontend no contrato de deploy (`docs/spec/deploy/project.json`, serviço
# `frontend`), o mesmo que o CORS do backend libera
# (`docs/spec/snapshots/ESTRUTURA.md`: "CORS travado no domínio do frontend
# (app.hospitalsaomatheus.cloud, via frontend_url)").
BASE_DO_APP_EM_PRODUCAO = "https://app.hospitalsaomatheus.cloud"

# O que não pode aparecer num print publicado: o endereço da máquina de quem
# capturou. Um cartaz impresso com isto é papel na parede que não abre.
ENDERECOS_LOCAIS = ("localhost", "127.0.0.1", "0.0.0.0")

RELATO_DE_EXEMPLO = (
    "Fui muito bem atendida na recepção da Farmácia hoje de manhã. "
    "A atendente explicou com calma como retirar o medicamento e ainda "
    "conferiu a receita comigo. Queria registrar o elogio."
)

# Dados de exemplo do cartaz publicado no manual, os mesmos do capítulo 1 em
# vídeo: o que muda de um cartaz para outro é só o cadastro por trás do código.
PONTO_DE_EXEMPLO = {
    "codigo": "QWQK8Q",
    "setor": "Pronto Atendimento",
    "ponto": "Sala de espera",
}
PROTOCOLO_DE_EXEMPLO = "2026-0007"
DESFECHO_DE_EXEMPLO = "procedente"


class EnderecoLocalNoPrint(Exception):
    """O print ia para o manual com o endereço da máquina de quem capturou."""


def exigir_endereco_de_producao(texto_visivel: str, nome: str) -> None:
    """Recusa a captura quando o que a pessoa lê no print traz endereço local.

    Olha o texto visível, e não o HTML: o `__NEXT_DATA__` e os chunks do
    frontend citam localhost em desenvolvimento sem que nada disso apareça na
    imagem, e travar neles faria a guarda gritar em todo print do app local.
    """
    achados = [e for e in ENDERECOS_LOCAIS if e in texto_visivel]
    if achados:
        raise EnderecoLocalNoPrint(
            f"{nome}: o print mostra {', '.join(achados)}. O manual é público e "
            "o cartaz vai para a parede: monte o documento com "
            f"{BASE_DO_APP_EM_PRODUCAO} antes de capturar."
        )


def capturar(page, caminho: Path, nome: str, **kwargs) -> None:
    """Confere o texto visível e só então grava a imagem.

    A guarda vive aqui, no caminho por onde todo print passa, e não em cada
    função: print novo nasce protegido sem ninguém lembrar de chamar nada.
    """
    exigir_endereco_de_producao(page.inner_text("body"), nome)
    page.screenshot(path=str(caminho), **kwargs)


def _python_do_backend() -> str:
    """O interpretador que tem as dependências do app (jinja, segno).

    O `.venv` do backend não é versionado, então num worktree novo ele não
    existe: nesse caso vale o da árvore principal, que é o mesmo código.
    """
    raiz = Path(__file__).resolve().parents[3]
    candidatos = [
        raiz / "hospital-reunioes" / "backend" / ".venv" / "bin" / "python",
        Path.home() / "PedroDev" / "Hospital" / "hospital-reunioes" / "backend" / ".venv" / "bin" / "python",
    ]
    for candidato in candidatos:
        if candidato.is_file():
            return str(candidato)
    raise SystemExit(
        "não achei o Python do backend (.venv). Rode `uv sync` em "
        "hospital-reunioes/backend ou capture a partir da árvore principal."
    )


def _montar_no_app(expressao: str) -> str:
    """Roda o código do app num processo à parte, com a base de produção.

    O documento (cartaz e e-mail) é montado pelo mesmo template que o app usa,
    sem tocar no backend que está de pé: o que muda é só o `FRONTEND_URL` deste
    processo. As outras variáveis existem porque o `Settings` exige o conjunto
    inteiro para carregar, e nenhuma delas entra no documento.
    """
    raiz = Path(__file__).resolve().parents[3]
    codigo = textwrap.dedent(
        f"""
        import os, sys
        os.environ["FRONTEND_URL"] = "{BASE_DO_APP_EM_PRODUCAO}"
        os.environ["CLICKSIGN_BASE_URL"] = "https://app.clicksign.com"
        os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:54321")
        os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "sem-uso-neste-render")
        os.environ.setdefault("SUPABASE_ANON_KEY", "sem-uso-neste-render")
        sys.path.insert(0, {str(raiz / "hospital-reunioes" / "backend")!r})
        sys.stdout.write({expressao})
        """
    )
    saida = subprocess.run(
        [_python_do_backend(), "-c", codigo],
        capture_output=True,
        text=True,
        check=False,
    )
    if saida.returncode != 0:
        raise SystemExit(f"o app não montou o documento:\n{saida.stderr[-2000:]}")
    return saida.stdout


def formulario_publico(page, base: str, saida: Path) -> None:
    """A tela que o QR do cartaz abre, preenchida como uma pessoa preencheria."""
    page.goto(f"{base}/manifestacao", wait_until="networkidle")
    page.get_by_role("button", name="Elogio").click()
    page.get_by_label("O que aconteceu?").fill(RELATO_DE_EXEMPLO)
    page.get_by_label("Seu nome").fill("Marina Alves")
    page.get_by_label("Telefone ou email").fill("marina.alves@exemplo.com")
    # Sem foco em campo nenhum: o anel de foco no print vira instrução falsa
    # ("clique aqui") na hora que a pessoa lê a página.
    page.get_by_role("heading", name="Ouvidoria").click()
    capturar(page, saida / "formulario-publico.png", "formulario-publico", full_page=True)


def cartaz_pa(page, base: str, saida: Path) -> None:
    """O cartaz A5, do mesmo template que vira o PDF da gráfica."""
    html = _montar_no_app(
        "__import__('app.services.ouvidoria_pontos', fromlist=['x'])"
        f".html_do_cartaz({PONTO_DE_EXEMPLO!r})"
    )
    # O template é A5 com margem de 14mm (`@page`), medida que o navegador
    # ignora: a largura sai daí e a altura é cortada no rodapé do cartaz, senão
    # o print leva junto a metade em branco da folha.
    page.set_viewport_size({"width": 840, "height": 1188})
    page.set_content(html, wait_until="networkidle")
    fim = page.evaluate(
        "document.querySelector('.rodape').getBoundingClientRect().bottom"
    )
    capturar(
        page,
        saida / "cartaz-pa.png",
        "cartaz-pa",
        clip={"x": 0, "y": 0, "width": 840, "height": round(fim) + 40},
    )


def email_encerramento(page, base: str, saida: Path) -> None:
    """O aviso de encerramento, como chega na caixa de quem manifestou."""
    html = _montar_no_app(
        "__import__('app.services.ouvidoria_notificacoes', fromlist=['x'])"
        f".montar_encerramento_manifestante({PROTOCOLO_DE_EXEMPLO!r}, {DESFECHO_DE_EXEMPLO!r})[1]"
    )
    # O e-mail é a tabela de 560 de largura do `email_base.html`, centrada num
    # fundo que se estica: o corte para no fim do cartão para o print não virar
    # um retângulo cinza com um e-mail no alto.
    page.set_viewport_size({"width": 720, "height": 900})
    page.set_content(html, wait_until="networkidle")
    fim = page.evaluate(
        "document.querySelector('table table').getBoundingClientRect().bottom"
    )
    capturar(
        page,
        saida / "email-encerramento.png",
        "email-encerramento",
        clip={"x": 0, "y": 0, "width": 720, "height": round(fim) + 32},
    )


PRINTS = {
    "formulario-publico": formulario_publico,
    "cartaz-pa": cartaz_pa,
    "email-encerramento": email_encerramento,
}


def main() -> int:
    from playwright.sync_api import sync_playwright

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
