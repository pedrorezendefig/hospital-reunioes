#!/usr/bin/env python3
"""Roteiro de prints do módulo POPs (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

Receita:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Dados de exemplo do módulo (Setores, pessoas com perfil POP e um POP em
   cada estado): `python3 docs/manual/prints/pops.py --semear`. É idempotente
   e recusa rodar contra qualquer banco que não seja o local.
4. `python3 docs/manual/prints/pops.py`.

As telas de POPs só existem para quem tem perfil POP, então o roteiro entra com
a pessoa de exemplo (Marina Alves, Superadmin), criada pelo `--semear`.

Todo print que fica sob um passo leva o **balão numerado** do passo, desenhado
por `balao()` sobre a tela antes da captura (ADR 0057, emenda de 17/09/2026).
Um print por mudança de tela: passos na mesma tela dividem um print com vários
balões.

Uso: python3 docs/manual/prints/pops.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/pops] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

# O Playwright só é preciso para capturar: `--semear` e a guarda que protege o
# banco rodam sem ele, e é isso que deixa o teste da guarda importar este
# arquivo numa máquina sem navegador instalado.
if TYPE_CHECKING:
    from playwright.sync_api import Page

# Tela de trabalho sentada: POPs se usa no computador, não no corredor.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

# A pessoa de exemplo do módulo, criada pelo `--semear`.
EMAIL = "marina.alves@exemplo.local"
SENHA = "ManualPops2026!"

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"


# --------------------------------------------------------------------------
# Guardas e marcação (Print de passo)
# --------------------------------------------------------------------------

# O que não pode aparecer num print publicado: o endereço da máquina de quem
# capturou. O manual é um site público, e "localhost:3000" numa figura é uma
# instrução que não abre para ninguém.
#
# A guarda responde sobre "endereço local", e não sobre três strings: casar
# `localhost` e parar ali deixaria passar o `[::1]` do IPv6, a forma curta
# `127.1` e o `192.168.` de um notebook na rede do hospital. Por isso são
# padrões com forma de endereço, comparados sem caixa.
#
# Rede interna (`.local`, `.internal`, `.test`) só conta como endereço dentro
# de uma URL: os dados de exemplo deste módulo são e-mails `@exemplo.local`,
# domínio reservado para exemplo, e travar neles pararia toda captura correta
# em nome de um endereço que ninguém digita no navegador.
ENDERECOS_LOCAIS = (
    r"\blocalhost\b",
    r"\b127\.0\.0\.1\b",
    r"\b127\.1\b",
    r"\b0\.0\.0\.0\b",
    r"\[::1\]",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b",
    r"https?://[\w.-]+\.(?:local|internal|test)\b",
    r"\b[\w-]+(?:\.[\w-]+)*\.(?:local|internal|test)(?::\d+|/)",
)
RE_ENDERECO_LOCAL = re.compile("|".join(ENDERECOS_LOCAIS), re.IGNORECASE)

# A base do app em produção: não é chute, é o domínio do frontend no contrato
# de deploy (`docs/spec/deploy/project.json`).
BASE_DO_APP_EM_PRODUCAO = "https://app.hospitalsaomatheus.cloud"


class EnderecoLocalNoPrint(Exception):
    """O print ia para o manual com o endereço da máquina de quem capturou."""


def exigir_endereco_de_producao(texto_visivel: str, nome: str) -> None:
    """Recusa a captura quando o que a pessoa lê no print traz endereço local.

    Olha o texto visível, e não o HTML: o `__NEXT_DATA__` e os chunks do
    frontend citam localhost em desenvolvimento sem que nada disso apareça na
    imagem, e travar neles faria a guarda gritar em todo print do app local.
    """
    achados = sorted({m.group(0) for m in RE_ENDERECO_LOCAL.finditer(texto_visivel)})
    if achados:
        raise EnderecoLocalNoPrint(
            f"{nome}: o print mostra {', '.join(achados)}. O manual é público: "
            f"monte a tela com {BASE_DO_APP_EM_PRODUCAO} antes de capturar."
        )


# O balão numerado do Print de passo: círculo de 28 px no navy do app, número
# branco na fonte do app, ancorado no canto superior esquerdo do elemento,
# de onde ele sai deixando só 6 px sobre o elemento. É a única marcação permitida sobre a tela (ADR 0057,
# emenda de 17/09/2026), e quem desenha é este roteiro, antes da captura, nunca
# um editor de imagem: quando a tela muda, o roteiro roda de novo e o balão vai
# junto.
#
# O balão entra no DOM **dentro** do elemento que ele marca (ou do pai, quando
# o elemento é um campo, que não aceita filho), posicionado em relação a ele.
# Coordenada de tela não serve: a captura de uma janela mais alta que o
# navegador é remontada pelo Playwright, e um balão preso à tela sairia longe do
# botão que ele aponta. Preso ao elemento, ele vai junto.
BALAO_JS = """
(alvo, numero) => {
  // `tagName` de um SVG vem em caixa baixa, ao contrário do HTML: sem
  // normalizar, o balão nasceria dentro do <svg>, onde uma <div> não aparece.
  const vazio = ['INPUT', 'TEXTAREA', 'IMG', 'SVG', 'BR', 'HR'];
  let hospedeiro = vazio.includes(alvo.tagName.toUpperCase())
    ? alvo.parentElement
    : alvo;
  // O balão sobe até um hospedeiro que não o estrague. Botão apagado é pai
  // translúcido e o filho desbota junto; lista com barra de rolagem é pai que
  // corta o que passa da borda, e o balão, que nasce para fora do elemento,
  // sairia pela metade. Os dois defeitos só a olhada na imagem pega.
  const estraga = (el) => {
    const e = getComputedStyle(el);
    return parseFloat(e.opacity) < 1 || e.overflow !== 'visible';
  };
  for (let i = 0; i < 6 && hospedeiro.parentElement && estraga(hospedeiro); i++) {
    hospedeiro = hospedeiro.parentElement;
  }
  if (getComputedStyle(hospedeiro).position === 'static') {
    hospedeiro.style.position = 'relative';
  }
  const h = hospedeiro.getBoundingClientRect();
  const a = alvo.getBoundingClientRect();
  const b = document.createElement('div');
  b.className = 'manual-balao';
  b.textContent = String(numero);
  Object.assign(b.style, {
    position: 'absolute',
    left: (a.left - h.left - 22) + 'px',
    top: (a.top - h.top - 22) + 'px',
    width: '28px',
    height: '28px',
    borderRadius: '9999px',
    background: '#2B2E7E',
    color: '#FFFFFF',
    font: '600 15px/28px "HP Simplified", system-ui, sans-serif',
    textAlign: 'center',
    boxShadow: '0 1px 4px rgba(0,0,0,.35)',
    pointerEvents: 'none',
    zIndex: '2147483647',
  });
  hospedeiro.appendChild(b);
}
"""


def balao(page, seletor, numero: int) -> None:
    """Desenha o balão do passo `numero` sobre o elemento que o passo cita.

    O `seletor` é um locator do Playwright ou um seletor da tela, sempre pelo
    texto do botão ou do campo e nunca por posição fixa: balão em cima de
    elemento errado engana mais do que print nenhum.
    """
    alvo = (page.locator(seletor) if isinstance(seletor, str) else seletor).first
    alvo.wait_for(state="visible", timeout=15000)
    alvo.scroll_into_view_if_needed()
    alvo.evaluate(BALAO_JS, numero)


def limpar_baloes(page) -> None:
    """Tira os balões da tela: a mesma página serve a mais de um print."""
    page.evaluate(
        "() => document.querySelectorAll('.manual-balao').forEach((b) => b.remove())"
    )


# Folga em volta do quadro capturado. O balão nasce para fora do elemento que
# ele marca, e um campo encostado na borda do quadro o jogaria para fora do
# recorte: a folga nos quatro lados é o que mantém o balão, e o que o quadro
# mostra na borda, inteiros na imagem. Vale para toda captura de quadro.
FOLGA_DO_BALAO = 34


def capturar(page, caminho: Path, nome: str, alvo=None, folga=True, **kwargs) -> None:
    """Confere o texto visível e só então grava a imagem.

    A guarda vive aqui, no caminho por onde todo print passa, e não em cada
    função: print novo nasce protegido sem ninguém lembrar de chamar nada.
    """
    exigir_endereco_de_producao(page.inner_text("body"), nome)
    if alvo is None:
        page.screenshot(path=str(caminho), **kwargs)
        return
    if folga:
        # Somada ao recuo que o quadro já tem, e não no lugar dele: um modal
        # que já vinha com 24 px de padding trocaria 24 por 26 e o balão
        # continuaria cortado.
        alvo.evaluate(
            "(el, f) => {"
            " const e = getComputedStyle(el);"
            " for (const lado of ['Top', 'Right', 'Bottom', 'Left']) {"
            "   el.style['padding' + lado] ="
            "     (parseFloat(e['padding' + lado]) + f) + 'px';"
            " } }",
            FOLGA_DO_BALAO,
        )
        page.wait_for_timeout(200)
    alvo.screenshot(path=str(caminho), **kwargs)


# --------------------------------------------------------------------------
# Prints
# --------------------------------------------------------------------------


def entrar(page: Page, base: str) -> None:
    """Login com a pessoa de exemplo. As telas de POPs exigem perfil POP.

    A espera é por sair de `/login`: seguir direto para a tela antes disso
    devolve o roteiro ao login e o print sai da tela errada.
    """
    if "/login" not in page.url and page.url.startswith(base):
        return
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(EMAIL)
    page.get_by_placeholder("••••••••").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)


def _abrir_gestao(page: Page, base: str) -> None:
    """A tela inicial do módulo, carregada e parada no alto."""
    entrar(page, base)
    page.goto(f"{base}/pops", wait_until="networkidle")
    page.get_by_text("POPs do meu escopo").wait_for()
    # A lista chega depois da tela: capturar antes disso pega o esqueleto de
    # carregamento no lugar dos POPs.
    page.get_by_role("row").filter(has_text="HSM_CTI-001").first.wait_for()
    page.wait_for_timeout(800)


def _item_pops(page: Page):
    """O item POPs do menu da esquerda, marcado pelo ícone dele.

    O balão sai para fora do elemento pela esquerda, e o item do menu encosta
    na borda da janela: ancorado no ícone, que já tem o recuo do item, o balão
    cabe inteiro no print.
    """
    return page.get_by_role("link", name="POPs", exact=True).locator("svg").first


def _linha(page: Page, codigo: str):
    """A linha de um POP na lista, pelo Código que ela mostra."""
    return page.get_by_role("row").filter(has_text=codigo).first


def _sem_foco(page: Page) -> None:
    """Tira o foco de qualquer campo: o anel de foco numa captura parada vira
    instrução falsa ("clique aqui") para quem lê a página."""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)


def gestao_de_pops(page: Page, base: str, saida: Path) -> None:
    """A tela inicial do módulo: a lista do escopo com o filtro por estado.

    Sem balão: esta é a figura da Visão geral, que não ilustra passo nenhum.
    """
    _abrir_gestao(page, base)
    page.get_by_role("heading", name="Gestão de POPs").click()
    _sem_foco(page)
    capturar(page, saida / "gestao-de-pops.png", "gestao-de-pops")


def menu_pops(page: Page, base: str, saida: Path) -> None:
    """O item POPs no menu da esquerda: o passo 1 de quase toda tarefa daqui."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _item_pops(page), 1)
    capturar(
        page,
        saida / "menu-pops.png",
        "menu-pops",
        clip={"x": 0, "y": 0, "width": 540, "height": 500},
    )


def gestao_de_pops_criar(page: Page, base: str, saida: Path) -> None:
    """Onde a criação começa: o menu e o botão que abre o formulário."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _item_pops(page), 1)
    balao(page, page.get_by_role("button", name="Criar novo POP"), 2)
    capturar(page, saida / "gestao-de-pops-criar.png", "gestao-de-pops-criar")


def _escolher(page: Page, rotulo: str, opcao: str) -> None:
    """Escolhe um valor numa lista de seleção do app.

    O campo não é um `<select>` nativo e o rótulo não aponta para ele, então a
    busca é pelo primeiro campo depois do rótulo na tela.
    """
    _campo_de_lista(page, rotulo).click()
    page.get_by_role("option", name=opcao, exact=True).first.click()


def _campo_de_lista(page: Page, rotulo: str):
    """A lista de seleção que vem logo depois de um rótulo na tela.

    O rótulo é `<label>` no formulário e `<span>` na barra da elaboração, e em
    nenhum dos dois ele aponta para o campo: a busca é pelo primeiro campo
    depois do texto que a pessoa lê.
    """
    return page.locator(
        f"xpath=//*[self::label or self::span][normalize-space()='{rotulo}']"
        "/following::*[@role='combobox'][1]"
    ).first


def criar_novo_pop(page: Page, base: str, saida: Path) -> None:
    """O formulário de criação, preenchido como quem abre um POP preencheria.

    A captura é do modal, e não da tela toda: o formulário é o assunto, e a
    lista atrás dele entra desfocada no print de página inteira. O formulário
    é preenchido e NÃO é enviado, para não criar POP a cada rodada.
    """
    _abrir_gestao(page, base)
    page.get_by_role("button", name="Criar novo POP").click()
    page.get_by_text("O código HSM_[SIGLA]-[NNN] é gerado pelo sistema").wait_for()
    # A abertura do modal tem animação: capturar antes dela terminar sai translúcido.
    page.wait_for_timeout(1200)
    _escolher(page, "Setor", "Centro Cirúrgico (CC)")
    _escolher(page, "Criticidade", "CRÍTICA")
    page.get_by_placeholder("Ex.: Higienização das Mãos").fill("POP Cirurgia Segura")
    _escolher(page, "Elaborador", "Marina Alves")
    _escolher(page, "Revisor", "Rafael Pimenta")
    _escolher(page, "Validador", "Helena Duarte")
    _escolher(page, "Periodicidade de revisão", "6 meses")
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, _campo_de_lista(page, "Setor"), 3)
    balao(page, _campo_de_lista(page, "Elaborador"), 4)
    balao(page, _campo_de_lista(page, "Periodicidade de revisão"), 5)
    balao(page, page.get_by_role("button", name="Criar POP"), 6)
    modal = page.get_by_role("heading", name="Criar novo POP").locator(
        "xpath=ancestor::div[contains(@class,'rounded')][1]"
    )
    capturar(page, saida / "criar-novo-pop.png", "criar-novo-pop", alvo=modal)


def cartao_biblioteca(page: Page, base: str, saida: Path) -> None:
    """O cartão que abre a Biblioteca, no meio da tela de Gestão de POPs.

    O cartão fica bem abaixo da lista, e o item POPs do menu sai da janela
    quando a tela rola até ele: o passo do menu é ilustrado pelo print
    `menu-pops`, e este mostra só o cartão que o passo seguinte cita.
    """
    _abrir_gestao(page, base)
    cartao = page.get_by_role("link", name="Biblioteca")
    limpar_baloes(page)
    balao(page, cartao, 2)
    # A captura é da fileira dos dois cartões, e não só do de Biblioteca: o
    # balão sai para fora do cartão que ele marca, e recortar no cartão o
    # cortaria pela metade.
    capturar(
        page,
        saida / "cartao-biblioteca.png",
        "cartao-biblioteca",
        alvo=cartao.locator("xpath=.."),
    )


def _abrir_biblioteca(page: Page, base: str) -> None:
    entrar(page, base)
    page.goto(f"{base}/pops/biblioteca", wait_until="networkidle")
    page.get_by_role("heading", name="Biblioteca").first.wait_for()
    page.get_by_role("row").filter(has_text="HSM_FARM-001").first.wait_for()
    page.wait_for_timeout(600)


def biblioteca(page: Page, base: str, saida: Path) -> None:
    """A Biblioteca: os POPs publicados por Setor, com o PDF assinado.

    Recorte no alto da tela: a Biblioteca de exemplo tem um POP, e o resto da
    janela sairia como uma faixa branca no meio da página do manual.
    """
    _abrir_biblioteca(page, base)
    limpar_baloes(page)
    linha = _linha(page, "HSM_FARM-001")
    balao(page, page.get_by_text("FARMÁCIA · FARM"), 3)
    balao(page, linha.get_by_text("v1.0"), 4)
    balao(page, linha.get_by_text("HSM_FARM-001"), 5)
    capturar(
        page,
        saida / "biblioteca.png",
        "biblioteca",
        clip={"x": 0, "y": 0, "width": 1440, "height": 430},
    )


def ficha_do_pop(page: Page, base: str, saida: Path) -> None:
    """A Ficha do POP: as datas de cada etapa, os responsáveis e o documento."""
    _abrir_biblioteca(page, base)
    _linha(page, "HSM_FARM-001").get_by_title("Ficha do POP").click()
    page.get_by_text("Datas de cada etapa").wait_for()
    page.wait_for_timeout(1000)
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Baixar PDF assinado"), 6)
    modal = page.get_by_text("Datas de cada etapa").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )
    capturar(page, saida / "ficha-do-pop.png", "ficha-do-pop", alvo=modal)


def gestao_de_pops_elaborar(page: Page, base: str, saida: Path) -> None:
    """A lista com o botão da etapa de quem escreve, na linha do POP."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _linha(page, "HSM_CTI-002").get_by_role("link", name="Elaborar"), 1)
    capturar(page, saida / "gestao-de-pops-elaborar.png", "gestao-de-pops-elaborar")


def gestao_de_pops_abrir(page: Page, base: str, saida: Path) -> None:
    """Os botões que abrem um POP para leitura, na linha dele."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _linha(page, "HSM_CTI-001").get_by_role("link", name="Revisar"), 1)
    capturar(page, saida / "gestao-de-pops-abrir.png", "gestao-de-pops-abrir")


def gestao_de_pops_revisar(page: Page, base: str, saida: Path) -> None:
    """O caminho de quem revisa: o menu e o botão Revisar da linha."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _item_pops(page), 1)
    balao(page, _linha(page, "HSM_CTI-001").get_by_role("link", name="Revisar"), 2)
    capturar(page, saida / "gestao-de-pops-revisar.png", "gestao-de-pops-revisar")


def gestao_de_pops_validar(page: Page, base: str, saida: Path) -> None:
    """O caminho de quem valida: o menu e o botão Validar da linha."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _item_pops(page), 1)
    balao(page, _linha(page, "HSM_CC-001").get_by_role("link", name="Validar"), 2)
    capturar(page, saida / "gestao-de-pops-validar.png", "gestao-de-pops-validar")


def gestao_de_pops_assinatura(page: Page, base: str, saida: Path) -> None:
    """Os dois estados que a assinatura atravessa, lado a lado na lista."""
    _abrir_gestao(page, base)
    limpar_baloes(page)
    balao(page, _linha(page, "HSM_CC-002").get_by_text("Em Assinatura"), 5)
    balao(page, _linha(page, "HSM_FARM-001").get_by_text("Publicado"), 6)
    capturar(page, saida / "gestao-de-pops-assinatura.png", "gestao-de-pops-assinatura")


def _id_do_pop(page: Page, base: str, codigo: str) -> str:
    """O identificador do POP de exemplo, lido da lista da tela."""
    _abrir_gestao(page, base)
    linha = _linha(page, codigo)
    linha.get_by_role("link").first.wait_for()
    destino = linha.get_by_role("link").first.get_attribute("href") or ""
    return destino.split("/pops/")[1].split("/")[0]


def _abrir_elaboracao(page: Page, base: str, codigo: str) -> None:
    pop_id = _id_do_pop(page, base, codigo)
    page.goto(f"{base}/pops/{pop_id}/elaboracao", wait_until="networkidle")
    page.get_by_text("Consultor de POPs").wait_for()
    page.wait_for_timeout(1200)


def elaboracao(page: Page, base: str, saida: Path) -> None:
    """A tela de elaboração: o POP vivo à esquerda e o Consultor de POPs.

    O Consultor só responde com a chave do modelo configurada; a tela é
    capturada como ela nasce, com a primeira fala do assistente e o campo
    ainda vazio, que é o que a pessoa vê ao chegar.
    """
    entrar(page, base)
    _abrir_elaboracao(page, base, "HSM_CTI-002")
    page.get_by_text("1. Identificação").wait_for()
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_placeholder("Descreva o procedimento, passo a passo..."), 2)
    balao(page, page.get_by_role("heading", name="2. Objetivo").locator("xpath=following::button[1]"), 3)
    balao(page, _campo_de_lista(page, "Periodicidade de revisão"), 4)
    # O balão do "confira o documento" vai no cartão da primeira seção, e não
    # no texto dela: em cima do título ele taparia justamente a palavra que a
    # pessoa procura na tela.
    balao(
        page,
        page.get_by_role("heading", name="1. Identificação").locator(
            "xpath=ancestor::section[1]"
        ),
        5,
    )
    balao(page, page.get_by_role("button", name="Aprovar versão final"), 6)
    capturar(page, saida / "elaboracao.png", "elaboracao")


# O material de referência de exemplo: um POP antigo em texto, do jeito que a
# pessoa anexa. Nome e conteúdo são fictícios, como todo dado deste roteiro.
MATERIAL_DE_EXEMPLO = "POP-Recebimento-de-Medicamentos-2019.txt"
TEXTO_DO_MATERIAL = (
    "PROCEDIMENTO OPERACIONAL PADRÃO - RECEBIMENTO DE MEDICAMENTOS\n"
    "Farmácia Central - versão de 2019\n\n"
    "1. Conferir a nota fiscal com o pedido de compra.\n"
    "2. Conferir lote, validade e integridade da embalagem.\n"
    "3. Registrar a entrada no sistema e encaminhar ao armazenamento.\n"
)


def _painel_do_consultor(page: Page):
    """O painel da direita, que é o assunto dos prints de material."""
    return page.get_by_text("Consultor de POPs").locator(
        "xpath=ancestor::div[contains(@class,'rounded')][last()]"
    )


def _com_material_anexado(page: Page, base: str, tmp: Path) -> None:
    """Deixa o POP de exemplo com um material anexado, sem duplicar.

    O anexo é gravado de verdade pela tela, então o roteiro reaproveita o que
    já anexou numa rodada anterior em vez de empilhar cópias a cada execução.
    """
    _abrir_elaboracao(page, base, "HSM_FARM-002")
    etiqueta = page.get_by_title(MATERIAL_DE_EXEMPLO)
    if etiqueta.count() == 0:
        arquivo = tmp / MATERIAL_DE_EXEMPLO
        arquivo.write_text(TEXTO_DO_MATERIAL, encoding="utf-8")
        page.locator('input[type="file"]').set_input_files(str(arquivo))
        etiqueta.first.wait_for(timeout=30000)
    page.wait_for_timeout(1000)


def material_anexado(page: Page, base: str, saida: Path) -> None:
    """O painel do Consultor de POPs com o material de referência anexado."""
    entrar(page, base)
    with tempfile.TemporaryDirectory() as tmp:
        _com_material_anexado(page, base, Path(tmp))
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Anexar materiais de referência"), 2)
    # O ícone da etiqueta: o nome do arquivo ao lado é cortado com reticências
    # quando não cabe, e a etiqueta inteira encosta na borda da lista, que tem
    # barra de rolagem e corta o que passa dela.
    balao(page, page.get_by_title(MATERIAL_DE_EXEMPLO).locator("xpath=..").locator("svg").first, 3)
    balao(
        page,
        page.get_by_role(
            "button", name="Elaborar a nova versão a partir do material anexado"
        ),
        4,
    )
    balao(page, page.get_by_role("button", name=f"Remover {MATERIAL_DE_EXEMPLO}"), 6)
    capturar(
        page,
        saida / "material-anexado.png",
        "material-anexado",
        alvo=_painel_do_consultor(page),
    )


def pedido_de_elaboracao(page: Page, base: str, saida: Path) -> None:
    """O pedido pronto no campo de mensagem, antes de a pessoa enviar.

    O botão de arranque só preenche o campo: nada é enviado, e é esse o estado
    que o passo descreve.
    """
    entrar(page, base)
    with tempfile.TemporaryDirectory() as tmp:
        _com_material_anexado(page, base, Path(tmp))
    page.get_by_role(
        "button", name="Elaborar a nova versão a partir do material anexado"
    ).click()
    page.wait_for_timeout(800)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_placeholder("Descreva o procedimento, passo a passo..."), 5)
    capturar(
        page,
        saida / "pedido-de-elaboracao.png",
        "pedido-de-elaboracao",
        alvo=_painel_do_consultor(page),
    )


def _abrir_versao(page: Page, base: str, codigo: str) -> None:
    pop_id = _id_do_pop(page, base, codigo)
    page.goto(f"{base}/pops/{pop_id}/versao", wait_until="networkidle")
    page.get_by_text("1. Identificação").wait_for()
    page.wait_for_timeout(800)


def versao_em_revisao(page: Page, base: str, saida: Path) -> None:
    """A leitura da Versão com os botões da etapa de quem revisa."""
    entrar(page, base)
    _abrir_versao(page, base, "HSM_CTI-001")
    limpar_baloes(page)
    balao(page, page.get_by_text("1. Identificação"), 3)
    balao(page, page.get_by_role("button", name="Aprovar revisão"), 4)
    balao(page, page.get_by_role("button", name="Devolver com comentários"), 5)
    capturar(page, saida / "versao-em-revisao.png", "versao-em-revisao")


def versao_em_validacao(page: Page, base: str, saida: Path) -> None:
    """A leitura da Versão com os botões da etapa de quem valida."""
    entrar(page, base)
    _abrir_versao(page, base, "HSM_CC-001")
    limpar_baloes(page)
    balao(page, page.get_by_text("1. Identificação"), 3)
    balao(page, page.get_by_role("button", name="Aprovar validação"), 4)
    balao(page, page.get_by_role("button", name="Devolver com comentários"), 6)
    capturar(page, saida / "versao-em-validacao.png", "versao-em-validacao")


def devolver_com_comentarios(page: Page, base: str, saida: Path) -> None:
    """A janela da devolução: o motivo é obrigatório e vai com nome e hora.

    A janela abre e o roteiro não confirma nada: devolver de verdade moveria a
    Versão de estado e o print seguinte sairia de outra etapa.
    """
    entrar(page, base)
    _abrir_versao(page, base, "HSM_CTI-001")
    page.get_by_role("button", name="Devolver com comentários").click()
    page.get_by_role("heading", name="Devolver à elaboração?").wait_for()
    page.wait_for_timeout(1200)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Devolver", exact=True), 6)
    modal = page.get_by_role("heading", name="Devolver à elaboração?").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )
    capturar(
        page, saida / "devolver-com-comentarios.png", "devolver-com-comentarios", alvo=modal
    )


def fluxograma(page: Page, base: str, saida: Path) -> None:
    """O palco do fluxograma, na seção de fluxograma da Versão.

    O desenho é a última seção do POP: rolar até o título dela é o que põe o
    palco inteiro no print, e não o ícone do cabeçalho.
    """
    entrar(page, base)
    _abrir_versao(page, base, "HSM_CTI-001")
    titulo = page.get_by_text("6. Fluxograma", exact=False).last
    titulo.wait_for()
    titulo.scroll_into_view_if_needed()
    page.mouse.wheel(0, 330)
    page.wait_for_timeout(2000)
    limpar_baloes(page)
    balao(page, titulo, 2)
    balao(page, page.get_by_title("Aumentar zoom"), 3)
    balao(page, page.get_by_title("Ajustar à tela"), 4)
    balao(page, page.get_by_title("Baixar como PNG"), 5)
    balao(page, page.get_by_title("Baixar como SVG"), 6)
    capturar(page, saida / "fluxograma.png", "fluxograma")


def _rolar_ate(page: Page, titulo) -> None:
    """Põe um bloco do fim da tela no alto do print, com uma folga acima dele.

    `scroll_into_view_if_needed` não serve aqui: o bloco costuma já estar
    visível no pé da janela, e aí ele não rola nada e o print sai com o
    assunto espremido no rodapé.
    """
    titulo.first.evaluate("(el) => el.scrollIntoView({block: 'start'})")
    page.mouse.wheel(0, -90)
    page.wait_for_timeout(700)


def _bloco(page: Page, titulo: str):
    """O quadro inteiro de um bloco da tela, pelo título que ele mostra.

    Os blocos Setores e Acesso ao POPs ficam no pé de uma tela longa e não
    sobem até o alto da janela: a captura é do quadro, e não do que couber na
    janela, senão o assunto sai espremido no rodapé.
    """
    return page.get_by_role("heading", name=titulo, exact=True).locator(
        "xpath=ancestor::section[1]"
    )


def setores(page: Page, base: str, saida: Path) -> None:
    """O bloco Setores: onde a sigla que trava o Código dos POPs é cadastrada."""
    _abrir_gestao(page, base)
    _rolar_ate(page, page.get_by_role("heading", name="Setores", exact=True))
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Novo Setor"), 2)
    balao(
        page,
        page.get_by_role("row").filter(has_text="Centro de Terapia Intensiva").get_by_title("Editar"),
        6,
    )
    capturar(
        page, saida / "setores.png", "setores", alvo=_bloco(page, "Setores")
    )


def novo_setor(page: Page, base: str, saida: Path) -> None:
    """O cadastro de um Setor, preenchido e não salvo.

    Salvar criaria um Setor a cada rodada; o print é da janela preenchida, que
    é o que os passos descrevem.
    """
    _abrir_gestao(page, base)
    _rolar_ate(page, page.get_by_role("heading", name="Setores", exact=True))
    page.get_by_role("button", name="Novo Setor").click()
    page.get_by_role("heading", name="Novo Setor").wait_for()
    page.wait_for_timeout(1200)
    # O Nome aceita escolher da lista ou digitar, e a Sigla vem sugerida dele:
    # digitar é o caminho de quem cadastra uma unidade que ainda não existe.
    page.get_by_placeholder("Selecione ou digite").fill("Central de Material Esterilizado")
    # Digitar abre a lista de sugestões por cima do campo Sigla: clicar no
    # título fecha a lista e devolve a janela ao estado que o passo descreve.
    page.get_by_role("heading", name="Novo Setor").click()
    page.wait_for_timeout(500)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_placeholder("Selecione ou digite"), 3)
    balao(page, page.get_by_placeholder("Ex.: CTI"), 4)
    balao(page, page.get_by_role("button", name="Salvar"), 5)
    modal = page.get_by_role("heading", name="Novo Setor").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )
    capturar(page, saida / "novo-setor.png", "novo-setor", alvo=modal)


def acesso_ao_pops(page: Page, base: str, saida: Path) -> None:
    """O bloco Acesso ao POPs: quem entra na área e com que perfil."""
    _abrir_gestao(page, base)
    _rolar_ate(page, page.get_by_role("heading", name="Acesso ao POPs"))
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Conceder perfil"), 2)
    linha = page.get_by_role("row").filter(has_text="Rafael Pimenta")
    balao(page, linha.get_by_title("Setores da pessoa"), 5)
    balao(page, linha.get_by_title("Revogar perfil POP"), 6)
    capturar(
        page,
        saida / "acesso-ao-pops.png",
        "acesso-ao-pops",
        alvo=_bloco(page, "Acesso ao POPs"),
    )


def conceder_perfil(page: Page, base: str, saida: Path) -> None:
    """A escolha do perfil de quem vai entrar na Gestão de POPs.

    A janela é preenchida até a escolha do perfil e nada é concedido: conceder
    de verdade mudaria o acesso de uma pessoa a cada rodada.
    """
    _abrir_gestao(page, base)
    _rolar_ate(page, page.get_by_role("heading", name="Acesso ao POPs"))
    page.get_by_role("button", name="Conceder perfil").click()
    page.get_by_role("heading", name="Conceder perfil POP").wait_for()
    page.get_by_placeholder("Buscar pessoa por nome ou email…").fill("Bruno")
    page.get_by_text("Bruno Tavares").first.click()
    page.get_by_role("button", name="Conceder", exact=True).wait_for()
    page.wait_for_timeout(1000)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, _campo_de_lista(page, "Perfil"), 3)
    modal = page.get_by_role("heading", name="Conceder perfil POP").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )
    capturar(page, saida / "conceder-perfil.png", "conceder-perfil", alvo=modal)


def setores_da_pessoa(page: Page, base: str, saida: Path) -> None:
    """Os Setores marcados para uma pessoa: é isso que decide o que ela enxerga.

    A janela abre com o que já está marcado e o roteiro não salva: salvar
    mudaria o escopo de alguém a cada rodada.
    """
    _abrir_gestao(page, base)
    _rolar_ate(page, page.get_by_role("heading", name="Acesso ao POPs"))
    page.get_by_role("row").filter(has_text="Rafael Pimenta").get_by_title(
        "Setores da pessoa"
    ).click()
    page.get_by_role("heading", name="Setores da pessoa").wait_for()
    page.wait_for_timeout(1200)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Salvar"), 5)
    modal = page.get_by_role("heading", name="Setores da pessoa").locator(
        "xpath=ancestor::div[contains(@class,'rounded-2xl')][1]"
    )
    capturar(page, saida / "setores-da-pessoa.png", "setores-da-pessoa", alvo=modal)


PRINTS = {
    "gestao-de-pops": gestao_de_pops,
    "menu-pops": menu_pops,
    "gestao-de-pops-criar": gestao_de_pops_criar,
    "criar-novo-pop": criar_novo_pop,
    "cartao-biblioteca": cartao_biblioteca,
    "biblioteca": biblioteca,
    "ficha-do-pop": ficha_do_pop,
    "gestao-de-pops-elaborar": gestao_de_pops_elaborar,
    "gestao-de-pops-abrir": gestao_de_pops_abrir,
    "gestao-de-pops-revisar": gestao_de_pops_revisar,
    "gestao-de-pops-validar": gestao_de_pops_validar,
    "gestao-de-pops-assinatura": gestao_de_pops_assinatura,
    "elaboracao": elaboracao,
    "material-anexado": material_anexado,
    "pedido-de-elaboracao": pedido_de_elaboracao,
    "versao-em-revisao": versao_em_revisao,
    "versao-em-validacao": versao_em_validacao,
    "devolver-com-comentarios": devolver_com_comentarios,
    "fluxograma": fluxograma,
    "setores": setores,
    "novo-setor": novo_setor,
    "acesso-ao-pops": acesso_ao_pops,
    "conceder-perfil": conceder_perfil,
    "setores-da-pessoa": setores_da_pessoa,
}


# --------------------------------------------------------------------------
# Dados de exemplo (`--semear`)
# --------------------------------------------------------------------------

PESSOAS = [
    ("P900", "Marina Alves", EMAIL, "superadmin"),
    ("P901", "Rafael Pimenta", "rafael.pimenta@exemplo.local", "gerente"),
    ("P902", "Helena Duarte", "helena.duarte@exemplo.local", "coordenador"),
]

SETORES = [
    ("Centro de Terapia Intensiva", "CTI"),
    ("Farmácia", "FARM"),
    ("Centro Cirúrgico", "CC"),
]

FLUXOGRAMA_DE_EXEMPLO = {
    "nos": [
        {"id": "n1", "tipo": "passo", "texto": "Higienizar as mãos e reunir o material"},
        {
            "id": "n2",
            "tipo": "passo",
            "texto": "Conferir a prescrição e a identificação do paciente",
        },
        {
            "id": "n3",
            "tipo": "decisao",
            "texto": "A prescrição confere com a identificação?",
            "ramos": [
                {"rotulo": "Sim", "vai_para": "n4"},
                {
                    "rotulo": "Não",
                    "desvio": {
                        "texto": "Suspender e acionar o enfermeiro responsável",
                        "retorna_para": "n2",
                    },
                },
            ],
        },
        {"id": "n4", "tipo": "passo", "texto": "Executar o procedimento conforme a técnica"},
        {"id": "n5", "tipo": "passo", "texto": "Registrar o procedimento no prontuário"},
    ]
}

# O POP que ainda está sendo escrito tem poucas seções: é assim que a tela de
# elaboração aparece no começo da conversa com o agente.
SECOES_EM_ELABORACAO = [
    {
        "id": "a1",
        "titulo": "Objetivo",
        "tipo": "texto",
        "conteudo": (
            "Padronizar a aspiração de vias aéreas em pacientes intubados do "
            "Centro de Terapia Intensiva, preservando a oxigenação e prevenindo "
            "lesão de mucosa."
        ),
    },
    {
        "id": "a2",
        "titulo": "Aplicação",
        "tipo": "texto",
        "conteudo": "Equipe de enfermagem e fisioterapia do Centro de Terapia Intensiva.",
    },
    {
        "id": "a3",
        "titulo": "Materiais necessários",
        "tipo": "texto",
        "conteudo": (
            "- Sonda de aspiração estéril\n"
            "- Luva estéril e óculos de proteção\n"
            "- Soro fisiológico a 0,9%"
        ),
    },
]

SECOES_DE_EXEMPLO = [
    {
        "id": "s1",
        "titulo": "Objetivo",
        "tipo": "texto",
        "conteudo": (
            "Padronizar a higienização das mãos da equipe do Centro de Terapia "
            "Intensiva, reduzindo o risco de infecção relacionada à assistência."
        ),
    },
    {
        "id": "s2",
        "titulo": "Aplicação",
        "tipo": "texto",
        "conteudo": "Equipe assistencial do Centro de Terapia Intensiva, em todos os turnos.",
    },
    {
        "id": "s3",
        "titulo": "Materiais necessários",
        "tipo": "texto",
        "conteudo": "- Sabonete líquido\n- Papel toalha\n- Preparação alcoólica a 70%",
    },
    {
        "id": "s4",
        "titulo": "Descrição do procedimento",
        "tipo": "texto",
        "conteudo": (
            "1. Retire adornos das mãos e dos punhos.\n"
            "2. Abra a torneira e molhe as mãos sem encostar na pia.\n"
            "3. Ensaboe palmas, dorsos, espaços entre os dedos e polegares.\n"
            "4. Enxágue das pontas dos dedos em direção aos punhos.\n"
            "5. Seque com papel toalha e feche a torneira com ele."
        ),
    },
    {
        "id": "s5",
        "titulo": "Fluxograma",
        "tipo": "fluxograma",
        "conteudo": FLUXOGRAMA_DE_EXEMPLO,
    },
    {
        "id": "s6",
        "titulo": "Referências",
        "tipo": "texto",
        "conteudo": "ANVISA. Segurança do paciente em serviços de saúde: higienização das mãos.",
    },
]

# O POP do Centro Cirúrgico tem conteúdo próprio: reaproveitar as seções da
# higienização das mãos aqui deixava a tela de validação com um documento que
# fala de outro procedimento, e o print contaria uma história falsa.
SECOES_DE_CIRURGIA = [
    {
        "id": "c1",
        "titulo": "Objetivo",
        "tipo": "texto",
        "conteudo": (
            "Padronizar a conferência de segurança cirúrgica do Centro "
            "Cirúrgico, confirmando paciente, procedimento e lateralidade "
            "antes da incisão."
        ),
    },
    {
        "id": "c2",
        "titulo": "Aplicação",
        "tipo": "texto",
        "conteudo": "Equipe cirúrgica, anestesia e enfermagem do Centro Cirúrgico.",
    },
    {
        "id": "c3",
        "titulo": "Materiais necessários",
        "tipo": "texto",
        "conteudo": (
            "- Lista de verificação de cirurgia segura\n"
            "- Prontuário do paciente\n"
            "- Termo de consentimento assinado"
        ),
    },
    {
        "id": "c4",
        "titulo": "Descrição do procedimento",
        "tipo": "texto",
        "conteudo": (
            "1. Confirme com o paciente nome, procedimento e lado a ser operado.\n"
            "2. Confira o consentimento e a marcação do sítio cirúrgico.\n"
            "3. Faça a pausa cirúrgica com a equipe inteira presente.\n"
            "4. Confirme a contagem inicial de compressas e instrumentais.\n"
            "5. Registre a conferência no prontuário antes da incisão."
        ),
    },
    {
        "id": "c5",
        "titulo": "Fluxograma",
        "tipo": "fluxograma",
        "conteudo": FLUXOGRAMA_DE_EXEMPLO,
    },
    {
        "id": "c6",
        "titulo": "Referências",
        "tipo": "texto",
        "conteudo": "OMS. Lista de verificação de segurança cirúrgica; Manual ONA.",
    },
]


POPS_DE_EXEMPLO = [
    ("HSM_CTI-001", 1, "CTI", "POP Higienização das Mãos", "CRITICA", "EM_REVISAO", "P901", "P900", "P902"),
    ("HSM_CTI-002", 2, "CTI", "POP Aspiração de Vias Aéreas", "ALTA", "EM_ELABORACAO", "P900", "P901", "P902"),
    ("HSM_CC-001", 1, "CC", "POP Cirurgia Segura", "CRITICA", "EM_VALIDACAO", "P901", "P902", "P900"),
    ("HSM_FARM-001", 1, "FARM", "POP Dispensação de Medicamentos Potencialmente Perigosos", "CRITICA", "PUBLICADO", "P902", "P901", "P900"),
    ("HSM_FARM-002", 2, "FARM", "POP Recebimento de Medicamentos", "MEDIA", "A_ELABORAR", "P900", "P901", "P902"),
    ("HSM_CC-002", 2, "CC", "POP Contagem de Compressas", "ALTA", "EM_ASSINATURA", "P901", "P902", "P900"),
]


def _credenciais_locais() -> tuple[str, str]:
    """URL e chave de serviço do `.env` local, nunca de produção."""
    env = {}
    for linha in ENV_LOCAL.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            env[chave] = valor.strip().strip('"')
    url = env.get("SUPABASE_URL", "")
    chave = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        raise SystemExit(f"recusado: '{url}' não é o Supabase local.")
    return url, chave


def _rest(url: str, chave: str, caminho: str, metodo="GET", corpo=None, prefer=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(
        f"{url}/rest/v1/{caminho}", data=dados, headers=cabecalhos, method=metodo
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}")


def _login_de_exemplo(url: str, chave: str, email: str) -> str:
    """Cria (ou reaproveita) o login da pessoa de exemplo no Supabase local."""
    corpo = json.dumps({"email": email, "password": SENHA, "email_confirm": True}).encode()
    cabecalhos = {
        "apikey": chave,
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(f"{url}/auth/v1/admin/users", data=corpo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}")
    busca = urllib.request.Request(
        f"{url}/auth/v1/admin/users?page=1&per_page=200",
        headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
    )
    with urllib.request.urlopen(busca, timeout=20) as resposta:
        for usuario in json.load(resposta)["users"]:
            if usuario["email"] == email:
                return usuario["id"]
    raise SystemExit(f"login {email} não encontrado depois de criado.")


def semear() -> None:
    """Setores, pessoas com perfil POP e um POP em cada estado do fluxo."""
    url, chave = _credenciais_locais()

    for pid, nome, email, perfil in PESSOAS:
        _rest(
            url,
            chave,
            "participantes",
            "POST",
            [
                {
                    "id": pid,
                    "nome_completo": nome,
                    "email": email,
                    "cargo": "Coordenação",
                    "area": "Assistencial",
                    "setor": "Qualidade",
                    "role": "coordenador",
                    "ativo": True,
                    "auth_user_id": _login_de_exemplo(url, chave, email),
                    "perfil_pop": perfil,
                }
            ],
            prefer="resolution=merge-duplicates",
        )

    for nome, sigla in SETORES:
        if not _rest(url, chave, f"pops_setores?sigla=eq.{sigla}&select=id"):
            _rest(url, chave, "pops_setores", "POST", [{"nome": nome, "sigla": sigla}])
    setores = {s["sigla"]: s["id"] for s in _rest(url, chave, "pops_setores?select=id,sigla")}

    for pid, _, _, _ in PESSOAS:
        for sigla in setores:
            _rest(
                url,
                chave,
                "pops_setores_participantes",
                "POST",
                [{"setor_id": setores[sigla], "participante_id": pid}],
                prefer="resolution=ignore-duplicates",
            )

    for codigo, numero, sigla, nome, criticidade, estado, elab, rev, val in POPS_DE_EXEMPLO:
        campos = {
            "setor_id": setores[sigla],
            "numero": numero,
            "codigo": codigo,
            "nome": nome,
            "criticidade": criticidade,
            "periodicidade_revisao": "6_meses" if criticidade == "CRITICA" else "1_ano",
            "base_normativa": "RDC 63/2011; Manual ONA",
            "elaborador_id": elab,
            "revisor_id": rev,
            "validador_id": val,
            "criado_por": "P900",
        }
        ja = _rest(url, chave, f"pops?codigo=eq.{codigo}&select=id")
        if ja:
            pop_id = ja[0]["id"]
            _rest(url, chave, f"pops?id=eq.{pop_id}", "PATCH", campos)
        else:
            pop_id = _rest(
                url, chave, "pops", "POST", [campos], prefer="return=representation"
            )[0]["id"]

        if estado == "A_ELABORAR":
            secoes = None
        elif estado == "EM_ELABORACAO":
            secoes = {"secoes": SECOES_EM_ELABORACAO}
        elif sigla == "CC":
            secoes = {"secoes": SECOES_DE_CIRURGIA}
        else:
            secoes = {"secoes": SECOES_DE_EXEMPLO}
        versao = {
            "pop_id": pop_id,
            "numero_versao": "1.0",
            "estado": estado,
            "rascunho": secoes,
        }
        if estado == "PUBLICADO":
            versao["data_publicacao"] = "2026-09-02T14:10:00-03:00"
        atual = _rest(url, chave, f"pops_versoes?pop_id=eq.{pop_id}&select=id")
        if atual:
            versao_id = atual[0]["id"]
            _rest(url, chave, f"pops_versoes?id=eq.{versao_id}", "PATCH", versao)
        else:
            versao_id = _rest(
                url, chave, "pops_versoes", "POST", [versao], prefer="return=representation"
            )[0]["id"]

        # A Devolução é a pauta da correção: ela mora no POP que voltou para a
        # elaboração, e em nenhum outro, senão o print conta uma história falsa.
        _rest(url, chave, f"pops_devolucoes?versao_id=eq.{versao_id}", "DELETE")
        if codigo == "HSM_CTI-002":
            _rest(
                url,
                chave,
                "pops_devolucoes",
                "POST",
                [
                    {
                        "versao_id": versao_id,
                        "autor_id": "P901",
                        "etapa_retorno": "EM_REVISAO",
                        "comentarios": (
                            "Faltou o tempo mínimo de aspiração e o intervalo "
                            "entre as passagens da sonda. Inclua também o "
                            "registro no prontuário no fluxograma."
                        ),
                    }
                ],
            )

    print("dados de exemplo do módulo POPs prontos.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/pops")
    ap.add_argument(
        "--print",
        dest="escolhido",
        choices=sorted(PRINTS),
        help="captura só um print; sem isto, o roteiro inteiro roda.",
    )
    ap.add_argument(
        "--semear",
        action="store_true",
        help="cria os dados de exemplo no Supabase local e sai.",
    )
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

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
