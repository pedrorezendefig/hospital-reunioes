#!/usr/bin/env python3
"""Roteiro de prints do módulo Ouvidoria (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

Receita (a mesma do manual antigo da Ouvidoria, issue #563):

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Dados de exemplo do módulo (as contas que enxergam cada tela e uma
   manifestação por situação que as páginas citam):
   `python3 docs/manual/prints/ouvidoria.py --semear`. É idempotente e recusa
   rodar contra qualquer banco que não seja o local.
4. `python3 docs/manual/prints/ouvidoria.py`.

Tela sem login (formulário público, portal do setor) não precisa de conta. As
telas de dentro do app saem das pessoas de exemplo, e não da conta de ninguém:
a ouvidora para a fila e o caso, a diretora para a Tabela de prazos (que
recusa quem não é Diretoria Executiva) e o administrador para a tela de
Usuários (que recusa quem não é Super Admin).

O banco local é compartilhado com o resto do trabalho. O roteiro só cria e só
mexe no que é dele, marcado em `conversa_id`, e repõe o estado das
manifestações de exemplo antes de capturar: capturar mexe no banco (o print do
Arquivar clica no Arquivar) e a rodada seguinte precisa da mesma tela.

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
import datetime as dt
import hashlib
import json
import re
import subprocess
import sys
import textwrap
import urllib.error
import urllib.parse
import urllib.request
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
#
# A guarda responde sobre "endereço local", e não sobre três strings: casar
# `localhost` e parar ali deixaria passar o `[::1]` do IPv6, a forma curta
# `127.1`, o `192.168.` de um notebook na rede do hospital, o `.local` do
# Bonjour e um `LOCALHOST` em caixa alta. Por isso são padrões, comparados sem
# caixa.
#
# E são padrões com forma de endereço, não pedaços soltos: o manual fala em
# "10.000 caracteres" e em preço com milhar, e um `10.` cru travaria a captura
# de um print correto. Faixa privada só casa com os quatro octetos.
ENDERECOS_LOCAIS = (
    r"\blocalhost\b",
    r"\b127\.0\.0\.1\b",
    r"\b127\.1\b",
    r"\b0\.0\.0\.0\b",
    r"\[::1\]",
    r"\b192\.168\.\d{1,3}\.\d{1,3}\b",
    r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
    r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b",
    # `.local` é nome de máquina na rede (o `macbook.local` do Bonjour), e é
    # isso que a guarda persegue. O domínio das PESSOAS DE EXEMPLO do manual é
    # `exemplo.local`, escolhido de propósito para não existir, e ele aparece
    # em todo print de tela que lista gente: travar nele proibiria justamente
    # o dado de exemplo que o manual precisa mostrar.
    r"(?<!exemplo)\.local\b",
    r"\.internal\b",
    r"\.test\b",
)
RE_ENDERECO_LOCAL = re.compile("|".join(ENDERECOS_LOCAIS), re.IGNORECASE)

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
# O desfecho é o texto que o ouvidor escreve PARA a pessoa, em linguagem simples
# (RN-64). O código interno do enum, `procedente`, é o que o próprio montador do
# e-mail proíbe por escrito ("`procedente` não é português",
# `ouvidoria_notificacoes.py:1026`), e era ele que estava no print publicado.
DESFECHO_DE_EXEMPLO = (
    "Apuramos o que você relatou com a equipe responsável e corrigimos o "
    "atendimento no mesmo dia. Obrigado por avisar a Ouvidoria."
)


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


# --------------------------------------------------------------------------
# O balão numerado (Print de passo)
# --------------------------------------------------------------------------

# O navy da logo (`frontend/src/app/globals.css`, `--color-primary`) e a fonte
# do app: o balão é do manual, mas tem que parecer parte da tela.
NAVY_DO_APP = "#2B2E7E"

# 6 px para fora do canto superior esquerdo do elemento, como manda a receita
# (`.claude/skills/manual/references/prints.md`): à esquerda dele, na altura
# do topo.
FOLGA_DO_BALAO = 6

_JS_DO_BALAO = """
({ el, numero, folga, cor, onde }) => {
  const circulo = document.createElement('div');
  circulo.className = 'balao-do-manual';
  circulo.textContent = String(numero);

  // O balão entra no MESMO container que rola junto com o elemento, e não
  // solto no `body`: dentro de um modal que rola por dentro, um balão preso à
  // página escorrega do alvo assim que o balão seguinte rola o corpo, e o
  // print sai apontando o campo de baixo.
  //
  // O container que interessa é o primeiro ancestral que rola. Um `div` com
  // `overflow-y: auto` e `position: static` não é `offsetParent` de ninguém,
  // então ficar no `offsetParent` deixaria o balão parado enquanto o campo
  // desce. Quando esse ancestral é estático, ele vira `relative` para servir
  // de referência: é a mesma caixa, no mesmo lugar.
  let pai = null;
  for (let no = el.parentElement; no && no !== document.body; no = no.parentElement) {
    const estilo = getComputedStyle(no);
    const rola = /(auto|scroll)/.test(estilo.overflowY + estilo.overflowX);
    // Uma folga de 8px: um bloco que passa por 1 ou 2 pixels não rola de
    // verdade, e tratá-lo como o container espremeria o balão contra a borda.
    if (rola && (no.scrollHeight > no.clientHeight + 8 || no.scrollWidth > no.clientWidth + 8)) {
      pai = no;
      break;
    }
  }
  // Sem bloco que rola, o balão vive no `body`, em coordenada de página: é
  // ali que ele tem a largura inteira da janela à esquerda. Preso ao
  // `offsetParent` (a caixinha em volta de um campo), ele não teria para onde
  // ir e acabaria dentro do próprio campo.
  pai = pai || document.body;
  if (pai !== document.body && getComputedStyle(pai).position === 'static') {
    pai.style.position = 'relative';
  }
  const caixaDoPai = pai.getBoundingClientRect();
  const caixa = el.getBoundingClientRect();
  const x = caixa.left - caixaDoPai.left + pai.scrollLeft;
  const y = caixa.top - caixaDoPai.top + pai.scrollTop;

  // O círculo fica INTEIRO fora do elemento: sobreposto ao canto ele comia a
  // primeira letra do rótulo, e rótulo pela metade num print de manual é pior
  // do que balão nenhum.
  //
  // À esquerda é o padrão, que é onde sobra espaço num formulário. `acima`
  // existe para o ícone solto numa fileira de ícones, onde a esquerda é o
  // ícone vizinho: ali o balão à esquerda marcaria o botão errado.
  let lado = onde;
  // Sem folga à esquerda (o campo encostado na borda do bloco que rola), o
  // balão à esquerda sairia do corte. Nesse caso ele encosta na borda do
  // próprio elemento, na altura do meio: dentro de um campo isso cai em
  // espaço vazio, e não em cima do rótulo que fica acima dele.
  // A pergunta é se cabe na TELA, e por isso ela usa a posição do elemento na
  // janela, e não a posição dele dentro do bloco que rola: num modal, a
  // margem do formulário é estreita, mas à esquerda dela ainda há a borda da
  // janela inteira.
  const semFolga = caixa.left - folga - 28 < 2;
  if (lado === 'esquerda' && semFolga) lado = 'borda';
  let esquerda;
  let topo;
  if (lado === 'acima') {
    esquerda = x + caixa.width / 2 - 14;
    topo = y - folga - 28;
  } else if (lado === 'acima-inicio') {
    // Célula larga com o texto encostado à esquerda (o cabeçalho de uma
    // coluna): centrar no meio da célula deixaria o balão no vazio, longe da
    // palavra que o passo cita.
    esquerda = x + 6;
    topo = y - folga - 28;
  } else if (lado === 'borda') {
    esquerda = x - 6;
    topo = y + caixa.height / 2 - 14;
  } else {
    esquerda = x - folga - 28;
    topo = y - folga;
  }

  Object.assign(circulo.style, {
    position: 'absolute',
    left: Math.max(2, esquerda) + 'px',
    top: Math.max(2, topo) + 'px',
    width: '28px',
    height: '28px',
    borderRadius: '9999px',
    background: cor,
    color: '#ffffff',
    font: '700 15px/28px "HP Simplified", system-ui, sans-serif',
    textAlign: 'center',
    boxShadow: '0 0 0 2px #ffffff, 0 1px 4px rgba(0,0,0,0.35)',
    pointerEvents: 'none',
    zIndex: '2147483647',
  });
  pai.appendChild(circulo);
}
"""


def balao(
    page,
    alvo,
    numero: int,
    onde: str = "esquerda",
    folga: int = FOLGA_DO_BALAO,
    rolar: bool = True,
) -> None:
    """Desenha o balão do passo `numero` no canto do elemento `alvo`.

    `alvo` é um seletor do Playwright ou um locator já pronto, e aponta o
    elemento que o passo CITA (o botão **Novo Usuário**, o campo **Email**):
    balão em cima de elemento errado é instrução errada, e só olhar a imagem
    pega isso.

    `rolar` fica em `False` quando trazer o elemento para a vista rolaria o
    formulário para longe do que o print precisa mostrar (um botão do rodapé
    fixo, que já está visível).

    `onde` diz de que lado o balão encosta: `esquerda` (o padrão) serve a
    campo, botão e rótulo; `acima` serve ao ícone de uma fileira de ícones,
    onde a esquerda já é o ícone vizinho; `acima-inicio` serve à célula larga
    com o texto à esquerda, como o cabeçalho de uma coluna.

    O balão nasce dentro do mesmo bloco de posicionamento do elemento, então
    ele acompanha o alvo quando o balão seguinte rola a página ou o corpo de
    um modal.
    """
    if onde not in ("esquerda", "acima", "acima-inicio"):
        raise ValueError(
            f"balão {numero}: '{onde}' não é esquerda, acima nem acima-inicio."
        )
    alvo = page.locator(alvo) if isinstance(alvo, str) else alvo
    alvo = alvo.first
    if rolar:
        alvo.scroll_into_view_if_needed()
    if not alvo.bounding_box():
        raise RuntimeError(f"balão {numero}: o elemento não está na tela.")
    page.evaluate(
        _JS_DO_BALAO,
        {
            "el": alvo.element_handle(),
            "numero": numero,
            "folga": folga,
            "cor": NAVY_DO_APP,
            "onde": onde,
        },
    )


def limpar_baloes(page) -> None:
    """Apaga os balões da tela. A mesma página serve a mais de um print."""
    page.evaluate(
        "document.querySelectorAll('.balao-do-manual').forEach((b) => b.remove())"
    )


def sem_foco(page) -> None:
    """Tira o foco de qualquer campo antes de capturar.

    O anel de foco num campo vira instrução falsa ("clique aqui") na hora que
    a pessoa lê a página.
    """
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(200)


# --------------------------------------------------------------------------
# Navegação e captura
# --------------------------------------------------------------------------

# Tela de trabalho sentada: a Ouvidoria se faz no computador. O celular é para
# o que nasce do QR e do link do email (formulário público e portal do setor).
COMPUTADOR = {"width": 1440, "height": 900}


def computador(page) -> None:
    page.set_viewport_size(COMPUTADOR)
    page.wait_for_timeout(400)


def celular(page) -> None:
    page.set_viewport_size(CELULAR)
    page.wait_for_timeout(400)


# Quem está logado agora. Trocar de conta custa um logout, e o roteiro só
# paga esse preço quando a tela exige outro papel.
_CONTA_ABERTA = {"email": None}


def entrar(page, base: str, conta: dict = None) -> None:
    """Login com a pessoa de exemplo que enxerga a tela.

    A espera é por sair de `/login`: seguir direto para a tela antes disso
    devolve o roteiro ao login e o print sai da tela errada.
    """
    conta = conta or OUVIDORA
    computador(page)
    if _CONTA_ABERTA["email"] == conta["email"] and page.url.startswith(base):
        return
    if _CONTA_ABERTA["email"]:
        page.context.clear_cookies()
        page.goto(f"{base}/login", wait_until="networkidle")
        page.evaluate("window.localStorage.clear(); window.sessionStorage.clear();")
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(conta["email"])
    page.get_by_placeholder("••••••••").fill(conta["senha"])
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)
    _CONTA_ABERTA["email"] = conta["email"]


def capturar_elemento(page, elemento, caminho: Path, nome: str) -> None:
    """A guarda de endereço local vale também para o recorte de um elemento."""
    exigir_endereco_de_producao(page.inner_text("body"), nome)
    elemento.screenshot(path=str(caminho))


def botao(page, texto: str):
    """O botão (ou link) pelo texto que está escrito no DOM.

    Não é `get_by_role(name=...)`: os rótulos de ação da Ouvidoria são
    desenhados em CAIXA ALTA pelo CSS (issue #489, RN-76), e o nome acessível
    que o Playwright calcula vem da caixa renderizada ("COBRAR"), não do texto
    do DOM ("Cobrar").
    """
    return page.locator("button, a").filter(has_text=re.compile(rf"^\s*{re.escape(texto)}\s*$", re.I)).first


def bloco(page, titulo: str):
    """O cartão do caso que começa pelo título escrito na tela."""
    return page.get_by_text(titulo, exact=True).first


def _janela_do_modal(page):
    """A CAIXA BRANCA do modal aberto.

    O `role="dialog"` da casa (`components/admin/AdminModal`) fica na camada
    que cobre a tela inteira, e não na caixa: capturar esse elemento devolve a
    página toda com o fundo desfocado. A caixa é o filho dele.
    """
    return page.locator("[role='dialog'] > div").last


def cartao(page, titulo: str):
    """O cartão da tela que começa pelo título escrito nele.

    Os balões dos campos são procurados DENTRO do cartão: a barra do app tem
    um campo de busca no alto de toda tela, e um `input` solto acha esse, não
    o do formulário.
    """
    # O ancestral é escolhido por CONTEÚDO, e não por classe: a caixa que
    # interessa é a menor que tem o título e os campos juntos, e o nome das
    # classes do tema muda sem avisar.
    return page.get_by_text(titulo, exact=False).first.locator(
        "xpath=ancestor::div[.//input or .//select][1]"
    )


def abrir_caso(page, base: str, apelido: str):
    """Abre a página de uma manifestação de exemplo pelo protocolo dela."""
    entrar(page, base)
    page.goto(f"{base}/ouvidoria/m/{protocolo_do(apelido)}", wait_until="networkidle")
    page.get_by_text("Manifestação", exact=False).first.wait_for(timeout=30000)
    page.wait_for_timeout(2500)


def abrir_a_lista(page, base: str) -> None:
    entrar(page, base)
    page.goto(f"{base}/ouvidoria", wait_until="networkidle")
    page.get_by_role("heading", name="Ouvidoria").first.wait_for(timeout=30000)
    page.wait_for_timeout(3000)


def linha_do_caso(page, apelido: str):
    """A linha da manifestação de exemplo na lista, achada pelo protocolo."""
    return page.locator(f"li[data-protocolo='{protocolo_do(apelido)}']")


def formulario_publico(page, base: str, saida: Path) -> None:
    """A tela que o QR do cartaz abre, preenchida como uma pessoa preencheria.

    Os seis passos da página acontecem nesta mesma tela, então ela leva os
    seis balões. O formulário é preenchido e NÃO é enviado: cada envio criaria
    uma manifestação de verdade no banco local.
    """
    celular(page)
    page.goto(f"{base}/manifestacao", wait_until="networkidle")
    page.get_by_role("button", name="Elogio").click()
    page.get_by_label("O que aconteceu?").fill(RELATO_DE_EXEMPLO)
    # "Este relato é sobre quem?" é obrigatório: sem responder, o botão de
    # enviar fica apagado e o print do último passo sairia mostrando a recusa
    # em vez do caminho.
    page.get_by_role("button", name="Sobre mim").click()
    page.get_by_label("Seu nome").fill("Marina Alves")
    page.get_by_label("Telefone ou email").fill("marina.alves@exemplo.com")
    # Sem foco em campo nenhum: o anel de foco no print vira instrução falsa
    # ("clique aqui") na hora que a pessoa lê a página.
    page.get_by_role("heading", name="Ouvidoria").click()
    sem_foco(page)
    balao(page, page.get_by_role("heading", name="Ouvidoria").first, 1)
    balao(page, page.get_by_role("button", name="Elogio"), 2)
    balao(page, page.get_by_label("O que aconteceu?"), 3)
    balao(page, page.get_by_text("Este relato é sobre quem?").first, 4)
    balao(page, page.get_by_text("Quero registrar de forma anônima", exact=False).first, 5)
    balao(page, botao(page, "Enviar manifestação"), 6)
    capturar(page, saida / "formulario-publico.png", "formulario-publico", full_page=True)
    limpar_baloes(page)
    computador(page)


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
        full_page=True,
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
        full_page=True,
        clip={"x": 0, "y": 0, "width": 720, "height": round(fim) + 32},
    )


# --------------------------------------------------------------------------
# A lista de casos e os atalhos
# --------------------------------------------------------------------------

# O corte padrão das telas de dentro do app: o alto da página, que é onde o
# passo acontece. Sem ele, a lista inteira vira um print de dois metros.
CORTE = {"x": 0, "y": 0, "width": 1440, "height": 720}


def fila_cobrar(page, base: str, saida: Path) -> None:
    """Cobrar o setor, passos 1, 2 e 3: achar a linha e clicar em Cobrar."""
    abrir_a_lista(page, base)
    linha = linha_do_caso(page, "com_a_area")
    linha.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    # O balão da linha vai no protocolo, que é onde a linha começa: em cima
    # do carimbo do prazo ele cairia sobre o resumo da linha de cima.
    balao(page, linha.locator("span").filter(has_text=re.compile(r"^\d{4}-\d{4}$")).first, 1)
    balao(page, linha.locator("button").filter(has_text="Cobrar").first, 2)
    capturar(
        page,
        saida / "fila-cobrar.png",
        "fila-cobrar",
        full_page=True,
        clip=_corte_da_linha(page, linha),
    )
    limpar_baloes(page)


def _corte_da_linha(page, linha):
    """Um pedaço da lista em volta da linha do exemplo, e não a lista inteira.

    O alto do corte cai no começo de uma linha vizinha, e não num número
    qualquer de pixels: cortado no meio de uma linha, o print abre com meia
    frase e meio carimbo.
    """
    rolagem = page.evaluate("window.scrollY")
    caixa = linha.bounding_box()
    topo = page.evaluate(
        "(el) => { let n = el;"
        " for (let i = 0; i < 2 && n.previousElementSibling; i++)"
        "   n = n.previousElementSibling;"
        " return n.getBoundingClientRect().top + window.scrollY; }",
        linha.element_handle(),
    )
    # Tudo em coordenada de DOCUMENTO, que é o que o corte de uma captura de
    # página inteira entende. Misturar com a coordenada de janela (que é o que
    # `bounding_box` devolve) corta o lugar errado assim que a página rola.
    fim = caixa["y"] + rolagem + caixa["height"] + 10
    return {"x": 0, "y": max(0, topo), "width": 1440, "height": fim - max(0, topo)}


def fila_arquivar(page, base: str, saida: Path) -> None:
    """Arquivar um caso, passos 1 e 3: a linha e o lote do grupo Encerrada."""
    abrir_a_lista(page, base)
    linha = linha_do_caso(page, "encerrado")
    linha.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    balao(page, linha.locator("button").filter(has_text="Arquivar").first, 1, "acima")
    lote = botao(page, "Arquivar todos os encerrados")
    balao(page, lote, 3)
    # O corte é o grupo Encerrada, e não a lista inteira: o print da fila toda
    # sai com três metros de altura e o passo some no meio dela.
    capturar(
        page,
        saida / "fila-arquivar.png",
        "fila-arquivar",
        full_page=True,
        clip=_corte_do_bloco(page, lote, 70, 240),
    )
    limpar_baloes(page)


def fila_arquivados(page, base: str, saida: Path) -> None:
    """Arquivar um caso, passos 4 e 5: o filtro ligado e o Desarquivar."""
    abrir_a_lista(page, base)
    botao(page, "Arquivados").click()
    linha = linha_do_caso(page, "arquivado")
    linha.wait_for(timeout=20000)
    linha.scroll_into_view_if_needed()
    page.wait_for_timeout(1500)
    balao(page, botao(page, "Arquivados"), 4, "acima")
    balao(page, linha.locator("button").filter(has_text="Desarquivar").first, 5)
    # O corte começa no alto da tela, e não na linha: no arquivo costuma haver
    # um caso só, e um recorte de uma linha sozinha não diz onde ela está.
    capturar(
        page,
        saida / "fila-arquivados.png",
        "fila-arquivados",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 620},
    )
    limpar_baloes(page)


def fila_nova_manifestacao(page, base: str, saida: Path) -> None:
    """Registrar pela Ouvidoria, passo 1: o botão que abre a janela."""
    abrir_a_lista(page, base)
    sem_foco(page)
    balao(page, botao(page, "Nova manifestação"), 1)
    capturar(
        page,
        saida / "fila-nova-manifestacao.png",
        "fila-nova-manifestacao",
        full_page=True,
        clip=CORTE,
    )
    limpar_baloes(page)


def fila_painel(page, base: str, saida: Path) -> None:
    """Acompanhar o painel, passo 1: o atalho que leva ao painel."""
    abrir_a_lista(page, base)
    sem_foco(page)
    balao(page, page.locator("nav[aria-label='Atalhos da Ouvidoria'] a").first, 1)
    capturar(
        page,
        saida / "fila-painel.png",
        "fila-painel",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 420},
    )
    limpar_baloes(page)


def _atalho(page, nome: str):
    return page.locator(f"nav[aria-label='Atalhos da Ouvidoria'] a[title='{nome}']")


def painel(page, base: str, saida: Path) -> None:
    """Acompanhar o painel, passos 2 a 5: os blocos, na ordem da leitura."""
    entrar(page, base)
    page.goto(f"{base}/ouvidoria/painel", wait_until="networkidle")
    page.get_by_text("Críticos abertos", exact=False).first.wait_for(timeout=30000)
    page.wait_for_timeout(3000)
    sem_foco(page)
    balao(page, page.get_by_text("Críticos abertos", exact=False).first, 2)
    # "Já venceu (8)": o texto de abertura da página também diz "já venceu",
    # e sem o parêntese o balão cairia no parágrafo em vez do bloco.
    balao(page, page.get_by_text("Já venceu (", exact=False).first, 3)
    balao(page, page.get_by_text("Próximos vencimentos", exact=False).first, 4)
    balao(page, page.get_by_text("Vencidos por área", exact=False).first, 5)
    capturar(page, saida / "painel.png", "painel", full_page=True)
    limpar_baloes(page)


def prazos(page, base: str, saida: Path) -> None:
    """Ajustar a tabela de prazos, passos 1 a 5.

    A tela recusa quem não é Diretoria Executiva, e por isso o print sai da
    conta da diretora de exemplo, e não da ouvidora.
    """
    entrar(page, base, DIRETORA)
    page.goto(f"{base}/ouvidoria/prazos", wait_until="networkidle")
    page.get_by_text("Tabela de prazos", exact=False).first.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    sem_foco(page)
    balao(page, page.get_by_text("Tabela de prazos", exact=False).first, 1)
    balao(page, page.locator("th").filter(has_text="Marco").first, 2)
    balao(page, page.locator("input[type='number']").first, 3)
    balao(page, page.get_by_role("heading", name="Feriados").first, 4)
    remover = botao(page, "Remover")
    if remover.count():
        balao(page, remover, 5)
    # O corte para logo abaixo das primeiras linhas de feriado: a lista inteira
    # tem dois anos de datas, e o print da página toda sai com três metros de
    # altura, que no site vira letra de formiga.
    capturar(
        page,
        saida / "prazos.png",
        "prazos",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 1440},
    )
    limpar_baloes(page)


def responsaveis(page, base: str, saida: Path) -> None:
    """Cadastrar responsáveis de setor, passos 1 a 6."""
    entrar(page, base)
    page.goto(f"{base}/ouvidoria/responsaveis", wait_until="networkidle")
    page.get_by_text("Cadastrar responsável", exact=False).first.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    sem_foco(page)
    formulario = cartao(page, "Cadastrar responsável")
    balao(page, page.get_by_text("Responsáveis por setor", exact=True).first, 1)
    balao(page, formulario.locator("select").first, 2)
    balao(page, formulario.locator("select").nth(1), 3)
    balao(page, formulario.locator("input").first, 4)
    balao(page, botao(page, "Cadastrar"), 5)
    encerrar = botao(page, "Encerrar vigência hoje")
    if encerrar.count():
        balao(page, encerrar, 6)
    capturar(
        page,
        saida / "responsaveis.png",
        "responsaveis",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 1100},
    )
    limpar_baloes(page)


def pontos(page, base: str, saida: Path) -> None:
    """Imprimir o cartaz, passos 1 a 6, todos na tela de pontos de escuta."""
    entrar(page, base)
    page.goto(f"{base}/ouvidoria/pontos", wait_until="networkidle")
    page.get_by_text("Pontos de escuta", exact=True).first.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    sem_foco(page)
    novo = cartao(page, "Novo ponto de escuta")
    balao(page, page.get_by_text("Pontos de escuta", exact=True).first, 1)
    balao(page, novo.locator("select").first, 2)
    balao(page, novo.locator("input").first, 3)
    balao(page, botao(page, "Criar cartaz"), 4)
    balao(page, botao(page, "Cartaz A5"), 5, "acima")
    balao(page, botao(page, "Aposentar"), 6, "acima")
    # O corte para depois do primeiro cartaz: a lista repete o mesmo cartão em
    # cada ponto cadastrado, e a página inteira vira um print de três metros.
    capturar(
        page,
        saida / "pontos.png",
        "pontos",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 1000},
    )
    limpar_baloes(page)


def nota_externa(page, base: str, saida: Path) -> None:
    """Lançar a nota, passos 1, 3, 5 e 6.

    Os passos 2 e 4 acontecem fora do app (abrir a página do hospital no
    Google e no Reclame Aqui), e por isso não têm balão: não há tela nossa
    para marcar.
    """
    entrar(page, base)
    page.goto(f"{base}/ouvidoria/nota-externa", wait_until="networkidle")
    page.get_by_text("Nota externa do hospital", exact=True).first.wait_for(timeout=30000)
    page.wait_for_timeout(2500)
    sem_foco(page)
    google = cartao(page, "Google")
    reclame = cartao(page, "Reclame Aqui")
    balao(page, page.get_by_text("Nota externa do hospital", exact=True).first, 1)
    balao(page, google.locator("input").first, 3)
    balao(page, reclame.locator("input").first, 5)
    registrada = google.get_by_text("Registrada em", exact=False).first
    if registrada.count():
        balao(page, registrada, 6)
    capturar(page, saida / "nota-externa.png", "nota-externa", full_page=True)
    limpar_baloes(page)


# --------------------------------------------------------------------------
# A página de um caso
# --------------------------------------------------------------------------

# O alto da página do caso: o cabeçalho com os botões e a ficha. É onde
# começam quase todos os passos.
TOPO_DO_CASO = {"x": 0, "y": 0, "width": 1440, "height": 640}


def _janela_alta(page, altura: int = 1500) -> None:
    """Janela mais alta para o formulário caber inteiro no print.

    Alguns modais da Ouvidoria são mais altos do que uma tela de notebook e
    rolam por dentro. Num print isso obriga a escolher entre mostrar o alto e
    mostrar o fim, e um dos balões do passo sempre fica de fora. A janela mais
    alta é a mesma tela, num monitor maior: nada de layout muda, só cabe mais.
    """
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": altura})
    page.wait_for_timeout(500)


def _corte_do_bloco(page, elemento, folga_acima: int = 60, folga_abaixo: int = 60):
    """O recorte em volta de um bloco do caso, em coordenada de documento."""
    rolagem = page.evaluate("window.scrollY")
    caixa = elemento.bounding_box()
    topo = max(0, caixa["y"] + rolagem - folga_acima)
    return {
        "x": 0,
        "y": topo,
        "width": 1440,
        "height": caixa["height"] + folga_acima + folga_abaixo,
    }


def caso_validar(page, base: str, saida: Path) -> None:
    """Classificar e acionar, passo 1: abrir o caso e chamar a janela."""
    abrir_caso(page, base, "para_classificar")
    sem_foco(page)
    balao(page, botao(page, "Validar e acionar"), 1)
    capturar(
        page,
        saida / "caso-validar.png",
        "caso-validar",
        full_page=True,
        clip=TOPO_DO_CASO,
    )
    limpar_baloes(page)


def validar_modal(page, base: str, saida: Path) -> None:
    """Classificar e acionar, passos 2 a 6: a janela inteira, preenchida."""
    abrir_caso(page, base, "para_classificar")
    _janela_alta(page)
    botao(page, "Validar e acionar").click()
    page.get_by_text("Tipo da manifestação", exact=False).first.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    janela = _janela_do_modal(page)
    janela.locator("select").first.select_option(label="Reclamação")
    page.wait_for_timeout(500)
    janela.locator("select").nth(1).select_option(label="Recepção")
    page.wait_for_timeout(500)
    janela.get_by_text("Médio", exact=True).click()
    page.wait_for_timeout(400)
    # O primeiro `textarea` da janela é o Extrato; o segundo é a Observação da
    # validação. A página atrás também tem os dois rótulos, então tudo aqui é
    # procurado DENTRO da janela.
    janela.locator("textarea").first.fill(
        "Apurar por que a fila do fim da tarde ficou sem senha de prioridade e "
        "o que a Recepção fez para atender quem tem preferência."
    )
    sem_foco(page)
    balao(page, janela.get_by_text("Tipo da manifestação", exact=False).first, 2)
    balao(page, janela.get_by_text("Área responsável", exact=False).first, 3)
    balao(page, janela.get_by_text("Gravidade", exact=True).first, 4)
    balao(page, janela.get_by_text("Extrato para o setor", exact=False).first, 5)
    # O rodapé tem Cancelar à esquerda do botão de confirmar: o balão à
    # esquerda cairia em cima da palavra errada.
    balao(page, janela.locator("button").filter(has_text="Validar e acionar a área"), 6, "acima")
    capturar_elemento(
        page, janela, saida / "validar-modal.png", "validar-modal"
    )
    limpar_baloes(page)
    computador(page)


def caso_encerrar(page, base: str, saida: Path) -> None:
    """Encerrar um caso, passo 1: abrir o caso e clicar em Encerrar."""
    abrir_caso(page, base, "respondido")
    sem_foco(page)
    balao(page, botao(page, "Encerrar"), 1)
    capturar(
        page,
        saida / "caso-encerrar.png",
        "caso-encerrar",
        full_page=True,
        clip=TOPO_DO_CASO,
    )
    limpar_baloes(page)


def encerrar_modal(page, base: str, saida: Path) -> None:
    """Encerrar um caso, passos 2 a 5: o desfecho e o texto que sai por email."""
    abrir_caso(page, base, "respondido")
    _janela_alta(page, 1200)
    botao(page, "Encerrar").click()
    page.get_by_text("Desfecho", exact=True).first.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    janela = _janela_do_modal(page)
    janela.locator("button").filter(has_text="Procedente").first.click()
    page.wait_for_timeout(400)
    janela.locator("textarea").first.fill(DESFECHO_DE_EXEMPLO)
    sem_foco(page)
    balao(page, janela.get_by_text("Desfecho", exact=True).first, 2)
    balao(page, janela.get_by_text("Desfecho para o manifestante", exact=False).first, 3)
    balao(page, janela.locator("textarea").first, 4)
    # O rodapé tem Cancelar à esquerda do botão de confirmar: o balão à
    # esquerda cairia em cima da palavra errada.
    balao(page, janela.locator("button").filter(has_text="Encerrar caso"), 5, "acima")
    capturar_elemento(page, janela, saida / "encerrar-modal.png", "encerrar-modal")
    limpar_baloes(page)
    computador(page)


def caso_respondido(page, base: str, saida: Path) -> None:
    """Devolver uma resposta fraca, passos 1, 2 e 3, no fim da página do caso."""
    abrir_caso(page, base, "respondido")
    bloco_resposta = page.get_by_text("Resposta da área", exact=False).last
    bloco_resposta.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    motivo = page.locator("textarea").last
    motivo.fill(
        "A resposta não conta o que foi feito com quem orientou o preparo do "
        "exame. Precisamos do que mudou no balcão, e não de um compromisso."
    )
    sem_foco(page)
    balao(page, bloco_resposta, 1)
    balao(page, motivo, 2)
    balao(page, botao(page, "Devolver por insuficiência"), 3)
    capturar(
        page,
        saida / "caso-respondido.png",
        "caso-respondido",
        full_page=True,
        clip=_corte_do_bloco(page, bloco_resposta, 40, 140),
    )
    limpar_baloes(page)


def caso_prorrogacao(page, base: str, saida: Path) -> None:
    """Decidir um pedido de mais prazo, passos 1 a 4, no bloco do pedido."""
    abrir_caso(page, base, "com_pedido_de_prazo")
    pedido = page.get_by_text("Prorrogação de prazo", exact=False).first
    pedido.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    sem_foco(page)
    balao(page, pedido, 1)
    balao(page, page.get_by_text("A copa está em reforma", exact=False).first, 2)
    # O campo do motivo é o DESTE bloco: o último `textarea` da página é o do
    # bloco Manifestante, logo abaixo.
    motivo = page.get_by_placeholder("Motivo da decisão", exact=False)
    if motivo.count():
        balao(page, motivo, 3)
    balao(page, botao(page, "Aprovar"), 4)
    capturar(
        page,
        saida / "caso-prorrogacao.png",
        "caso-prorrogacao",
        full_page=True,
        clip=_corte_do_bloco(page, pedido, 40, 100),
    )
    limpar_baloes(page)


def caso_pausar(page, base: str, saida: Path) -> None:
    """Pausar o caso, passos 1, 2 e 3: o bloco Manifestante e o Parar."""
    abrir_caso(page, base, "com_a_area")
    manifestante = page.get_by_text("Manifestante", exact=True).last
    manifestante.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    falta = page.locator("textarea").last
    falta.fill(
        "Precisamos do dia e do horário em que a senha de prioridade não estava "
        "em uso, e do nome de quem atendeu no balcão."
    )
    sem_foco(page)
    balao(page, manifestante, 1)
    balao(page, falta, 2)
    balao(page, botao(page, "Parar: falta dado do manifestante"), 3)
    capturar(
        page,
        saida / "caso-pausar.png",
        "caso-pausar",
        full_page=True,
        clip=_corte_do_bloco(page, manifestante, 40, 120),
    )
    limpar_baloes(page)


def caso_reabrir(page, base: str, saida: Path) -> None:
    """Reabrir por reincidência, passos 1, 2 e 3, no caso encerrado."""
    abrir_caso(page, base, "encerrado")
    manifestante = page.get_by_text("Manifestante", exact=True).last
    manifestante.scroll_into_view_if_needed()
    page.wait_for_timeout(800)
    texto = page.locator("textarea").last
    texto.fill(
        "A pessoa voltou a ligar dizendo que a dieta chegou fria de novo no "
        "mesmo quarto, duas semanas depois do encerramento."
    )
    sem_foco(page)
    balao(page, manifestante, 1)
    balao(page, texto, 2)
    balao(page, botao(page, "Reabrir por reincidência"), 3)
    capturar(
        page,
        saida / "caso-reabrir.png",
        "caso-reabrir",
        full_page=True,
        clip=_corte_do_bloco(page, manifestante, 40, 120),
    )
    limpar_baloes(page)


def caso_redirecionar(page, base: str, saida: Path) -> None:
    """Redirecionar o caso, passo 1: o botão no alto da página do caso."""
    abrir_caso(page, base, "com_a_area")
    sem_foco(page)
    balao(page, botao(page, "Redirecionar"), 1)
    capturar(
        page,
        saida / "caso-redirecionar.png",
        "caso-redirecionar",
        full_page=True,
        clip=TOPO_DO_CASO,
    )
    limpar_baloes(page)


def redirecionar_modal(page, base: str, saida: Path) -> None:
    """Redirecionar o caso, passos 2 a 5: a janela já preenchida.

    A área escolhida é uma que TEM titular vigente: numa área sem responsável
    a janela responde com um aviso em vermelho, e o print do passo mostraria a
    recusa em vez do caminho.
    """
    abrir_caso(page, base, "com_a_area")
    _janela_alta(page, 2100)
    botao(page, "Redirecionar").click()
    page.get_by_text("Motivo do redirecionamento", exact=False).first.wait_for(
        timeout=20000
    )
    page.wait_for_timeout(1500)
    janela = _janela_do_modal(page)
    janela.locator("select").nth(1).select_option(label="Faturamento")
    page.wait_for_timeout(600)
    # O primeiro `textarea` da janela de redirecionamento é o motivo; depois
    # dele vêm o extrato e a observação da validação.
    motivo = janela.locator("textarea").first
    motivo.fill(
        "O relato é de cobrança de exame, que a Recepção não apura. O caso é do "
        "Faturamento desde o começo."
    )
    sem_foco(page)
    balao(page, janela.get_by_text("Tipo da manifestação", exact=False).first, 2)
    balao(page, janela.get_by_text("Área responsável", exact=False).first, 3)
    balao(page, motivo, 4)
    # O rodapé tem Cancelar à esquerda do botão de confirmar: o balão à
    # esquerda cairia em cima da palavra errada.
    balao(
        page,
        janela.locator("button").filter(has_text="Redirecionar para a área nova"),
        5,
        "acima",
    )
    capturar_elemento(
        page, janela, saida / "redirecionar-modal.png", "redirecionar-modal"
    )
    limpar_baloes(page)
    computador(page)

def nova_manifestacao_modal(page, base: str, saida: Path) -> None:
    """Registrar pela Ouvidoria, passos 2 a 6: a janela inteira, preenchida.

    O formulário é preenchido e NÃO é enviado: cada envio criaria um caso de
    verdade no banco local, que é compartilhado com o resto do trabalho.
    """
    abrir_a_lista(page, base)
    _janela_alta(page, 1600)
    botao(page, "Nova manifestação").click()
    page.get_by_text("Canal de origem", exact=False).first.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    janela = _janela_do_modal(page)
    janela.locator("select").first.select_option(label="Telefone")
    page.wait_for_timeout(400)
    janela.locator("select").nth(1).select_option(label="Reclamação")
    janela.locator("select").nth(2).select_option(label="Nutrição")
    page.wait_for_timeout(400)
    janela.locator("#resumo").fill(
        "Ligou dizendo que a dieta chegou fria no quarto 312"
    )
    janela.locator("#relato").fill(
        "Ligou às 9h contando que o almoço chegou frio no quarto 312 na segunda "
        "e na terça, e que avisou a copa nos dois dias sem troca da refeição."
    )
    janela.locator("#nome").fill("Otávio Brandão")
    janela.locator("#contato").fill("otavio.brandao@exemplo.local")
    sem_foco(page)
    balao(page, janela.get_by_text("Canal de origem", exact=False).first, 2)
    balao(page, janela.get_by_text("Data e hora do contato", exact=False).first, 3)
    balao(page, janela.get_by_text("Resumo", exact=True).first, 4)
    balao(page, janela.get_by_text("Relato integral", exact=False).first, 5)
    # O rodapé tem Cancelar à esquerda do botão de confirmar: o balão à
    # esquerda cairia em cima da palavra errada.
    balao(page, janela.locator("button").filter(has_text="Registrar manifestação"), 6, "acima")
    capturar_elemento(
        page, janela, saida / "nova-manifestacao-modal.png", "nova-manifestacao-modal"
    )
    limpar_baloes(page)
    computador(page)


def canal_de_origem(page, base: str, saida: Path) -> None:
    """Registrar pela Ouvidoria, passo 2: a lista de canais aberta.

    O menu nativo de um `select` não sai na captura: antes do print o campo
    vira uma lista visível, e o recorte é a área dele.
    """
    abrir_a_lista(page, base)
    _janela_alta(page, 1200)
    botao(page, "Nova manifestação").click()
    page.get_by_text("Canal de origem", exact=False).first.wait_for(timeout=20000)
    page.wait_for_timeout(1200)
    janela = _janela_do_modal(page)
    campo = janela.locator("select").first
    campo.evaluate("(el) => { el.size = el.options.length; }")
    page.wait_for_timeout(600)
    sem_foco(page)
    balao(page, janela.get_by_text("Canal de origem", exact=False).first, 2)
    # O corte é em coordenada de página, e não o recorte do elemento: o balão
    # encosta à esquerda do rótulo, fora da caixa do campo, e o recorte do
    # elemento o deixaria de fora.
    rolagem = page.evaluate("window.scrollY")
    caixa = campo.locator("xpath=ancestor::div[1]").bounding_box()
    capturar(
        page,
        saida / "canal-de-origem.png",
        "canal-de-origem",
        full_page=True,
        clip={
            "x": max(0, caixa["x"] - 56),
            "y": max(0, caixa["y"] + rolagem - 16),
            "width": caixa["width"] + 72,
            "height": caixa["height"] + 32,
        },
    )
    limpar_baloes(page)
    computador(page)


# --------------------------------------------------------------------------
# O portal do setor e o formulário público (celular)
# --------------------------------------------------------------------------


def _abrir_o_portal(page, base: str) -> None:
    """A tela que o link do email abre, no celular, sem login."""
    celular(page)
    page.goto(
        f"{base}/ouvidoria-setor/{TOKEN_DO_PORTAL}", wait_until="networkidle"
    )
    page.get_by_text("Demanda da Ouvidoria", exact=False).first.wait_for(timeout=30000)
    page.wait_for_timeout(2000)


def portal_setor_mobile(page, base: str, saida: Path) -> None:
    """Responder pelo portal, passos 2 a 6.

    O passo 1 é abrir o email, que não é tela do app: quem o ilustra é o print
    do próprio email, ao lado.
    """
    _abrir_o_portal(page, base)
    resposta = page.locator("textarea").first
    resposta.fill(
        "Recolocamos a senha de prioridade no balcão da tarde e o turno passou "
        "a conferir o equipamento na abertura. A equipe foi orientada hoje."
    )
    sem_foco(page)
    balao(page, page.get_by_text("Prazo de resposta", exact=False).first, 2)
    balao(page, page.get_by_text("Nota da Ouvidoria", exact=False).first, 3)
    balao(page, resposta, 4)
    balao(page, page.get_by_text("Anexar arquivos", exact=False).first, 5)
    balao(page, botao(page, "Responder à Ouvidoria"), 6)
    capturar(
        page,
        saida / "portal-setor-mobile.png",
        "portal-setor-mobile",
        full_page=True,
    )
    limpar_baloes(page)
    computador(page)


def email_demanda(page, base: str, saida: Path) -> None:
    """Responder pelo portal, passo 1: o email que chega para a área.

    Montado pelo código do próprio app com a base de produção, como o cartaz e
    o aviso de encerramento: o link do email vai para a caixa de entrada de
    gente do hospital, e o endereço da máquina de quem capturou não serve.
    """
    caso = {
        "protocolo": "2026-0042",
        "resumo": "Cadeira de rodas sem disponibilidade na entrada principal",
        "relato_integral": (
            "Cheguei de táxi com meu marido, que não anda sozinho, e não havia "
            "cadeira de rodas livre na entrada principal."
        ),
        "extrato_para_o_setor": (
            "Verificar quantas cadeiras de rodas ficam na entrada principal no "
            "turno da manhã e o que a Recepção fez no dia do relato."
        ),
        "setor": "Recepção",
        "categoria": "Atendimento",
        "gravidade": "medio",
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "prazo_area_em": "2026-09-22T18:00:00+00:00",
    }
    html = _montar_no_app(
        "__import__('app.services.ouvidoria_notificacoes', fromlist=['x'])"
        f".montar_nova_demanda({caso!r}, 'Vera Antunes', "
        "__import__('datetime').datetime(2026, 9, 18, 9, 0, "
        "tzinfo=__import__('datetime').timezone.utc), frozenset(), "
        "'https://app.hospitalsaomatheus.cloud/ouvidoria-setor/exemplo')[1]"
    )
    page.set_viewport_size({"width": 720, "height": 1200})
    page.set_content(html, wait_until="networkidle")
    page.wait_for_timeout(600)
    alvo = page.get_by_role("link").first
    balao(page, alvo, 1)
    fim = page.evaluate(
        "document.querySelector('table table').getBoundingClientRect().bottom"
    )
    capturar(
        page,
        saida / "email-demanda.png",
        "email-demanda",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 720, "height": round(fim) + 32},
    )
    limpar_baloes(page)
    computador(page)


def portal_prorrogacao(page, base: str, saida: Path) -> None:
    """Pedir mais prazo, passos 2 e 3: as regras e o botão que abre o pedido."""
    _abrir_o_portal(page, base)
    bloco_prazo = page.get_by_text("Precisa de mais prazo?", exact=False).first
    bloco_prazo.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    sem_foco(page)
    balao(page, bloco_prazo, 2)
    balao(page, botao(page, "Solicitar prorrogação de prazo"), 3)
    capturar(
        page,
        saida / "portal-prorrogacao.png",
        "portal-prorrogacao",
        full_page=True,
        clip=_corte_no_celular(page, bloco_prazo, 40, 60),
    )
    limpar_baloes(page)
    computador(page)


def _corte_no_celular(page, elemento, folga_acima=40, folga_abaixo=40):
    rolagem = page.evaluate("window.scrollY")
    caixa = elemento.bounding_box()
    topo = max(0, caixa["y"] + rolagem - folga_acima)
    return {
        "x": 0,
        "y": topo,
        "width": CELULAR["width"],
        "height": caixa["height"] + folga_acima + folga_abaixo,
    }


def portal_prorrogacao_formulario(page, base: str, saida: Path) -> None:
    """Pedir mais prazo, passos 4, 5 e 6: o formulário do pedido."""
    _abrir_o_portal(page, base)
    botao(page, "Solicitar prorrogação de prazo").click()
    page.get_by_text("Quantos dias úteis a mais", exact=False).first.wait_for(
        timeout=20000
    )
    page.wait_for_timeout(1000)
    justificativa = page.locator("textarea").last
    justificativa.fill(
        "A chefia da Recepção está em férias e o relatório do turno da tarde só "
        "fica pronto na quinta. Preferimos responder com o dado na mão."
    )
    sem_foco(page)
    balao(page, page.get_by_text("Quantos dias úteis a mais", exact=False).first, 4)
    balao(page, justificativa, 5)
    balao(page, botao(page, "Enviar pedido"), 6)
    capturar(
        page,
        saida / "portal-prorrogacao-formulario.png",
        "portal-prorrogacao-formulario",
        full_page=True,
        clip=_corte_no_celular(
            page, page.get_by_text("Quantos dias úteis a mais", exact=False).first, 60, 460
        ),
    )
    limpar_baloes(page)
    computador(page)


def portal_devolver(page, base: str, saida: Path) -> None:
    """Devolver um caso, passo 2: o link embaixo dos dois botões."""
    _abrir_o_portal(page, base)
    link = page.get_by_text("Este caso não é do meu setor?", exact=False).first
    link.scroll_into_view_if_needed()
    page.wait_for_timeout(600)
    sem_foco(page)
    balao(page, link, 2)
    capturar(
        page,
        saida / "portal-devolver.png",
        "portal-devolver",
        full_page=True,
        clip=_corte_no_celular(page, link, 180, 60),
    )
    limpar_baloes(page)
    computador(page)


def portal_devolver_formulario(page, base: str, saida: Path) -> None:
    """Devolver um caso, passos 3 e 4: o motivo e o botão que devolve."""
    _abrir_o_portal(page, base)
    page.get_by_text("Este caso não é do meu setor?", exact=False).first.click()
    page.get_by_text("Por que este caso não é da sua área", exact=False).first.wait_for(
        timeout=20000
    )
    page.wait_for_timeout(1000)
    motivo = page.locator("textarea").last
    motivo.fill(
        "As cadeiras de rodas da entrada são do setor de Hotelaria, que faz a "
        "reposição. A Recepção só entrega a cadeira que já está lá."
    )
    sem_foco(page)
    balao(page, motivo, 3)
    balao(page, botao(page, "Devolver à Ouvidoria"), 4)
    capturar(
        page,
        saida / "portal-devolver-formulario.png",
        "portal-devolver-formulario",
        full_page=True,
        clip=_corte_no_celular(
            page,
            page.get_by_text("Por que este caso não é da sua área", exact=False).first,
            60,
            400,
        ),
    )
    limpar_baloes(page)
    computador(page)


# --------------------------------------------------------------------------
# Dar acesso à Ouvidoria (a tela é do painel de administração)
# --------------------------------------------------------------------------


def usuarios_acesso_ouvidoria(page, base: str, saida: Path) -> None:
    """Dar acesso à Ouvidoria, passo 1: achar a pessoa e abrir a ficha.

    A tela é do painel de administração e só o Super Admin a abre, então o
    print sai da conta do administrador de exemplo.

    A busca é digitada ANTES de esperar qualquer linha: entre abrir a tela e
    filtrar existe um instante com a lista real do hospital, e capturar nele
    seria publicar nome e email de gente de verdade.
    """
    entrar(page, base, ADMINISTRADOR)
    page.goto(f"{base}/admin/usuarios", wait_until="networkidle")
    busca = page.get_by_placeholder("Buscar por nome ou email…")
    busca.wait_for()
    busca.fill(EMAIL_DA_PESSOA_DE_EXEMPLO)
    page.get_by_text(OUVIDORA["nome"], exact=True).first.wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    sem_foco(page)
    balao(
        page,
        page.get_by_role("row")
        .filter(has_text=OUVIDORA["nome"])
        .locator("button[title='Editar']")
        .first,
        1,
        "acima",
    )
    capturar(
        page,
        saida / "usuarios-acesso-ouvidoria.png",
        "usuarios-acesso-ouvidoria",
        full_page=True,
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def editar_acesso_ouvidoria(page, base: str, saida: Path) -> None:
    """Dar acesso à Ouvidoria, passos 2, 3 e 4: o bloco e o Salvar."""
    entrar(page, base, ADMINISTRADOR)
    page.goto(f"{base}/admin/usuarios", wait_until="networkidle")
    busca = page.get_by_placeholder("Buscar por nome ou email…")
    busca.wait_for()
    busca.fill(EMAIL_DA_PESSOA_DE_EXEMPLO)
    page.get_by_text(OUVIDORA["nome"], exact=True).first.wait_for(timeout=20000)
    _janela_alta(page)
    page.get_by_role("row").filter(has_text=OUVIDORA["nome"]).locator(
        "button[title='Editar']"
    ).first.click()
    page.get_by_role("heading", name="Editar usuário").wait_for(timeout=20000)
    page.wait_for_timeout(1500)
    sem_foco(page)
    janela = _janela_do_modal(page)
    acesso = janela.locator("fieldset").filter(has_text="Acesso à Ouvidoria").locator(
        "[role='combobox'], select"
    ).first
    balao(page, janela.get_by_text("Acesso à Ouvidoria", exact=False).first, 2)
    balao(page, acesso, 3)
    balao(page, janela.locator("button").filter(has_text="Salvar"), 4, "acima")
    capturar_elemento(
        page, janela, saida / "editar-acesso-ouvidoria.png", "editar-acesso-ouvidoria"
    )
    limpar_baloes(page)
    computador(page)


# --------------------------------------------------------------------------
# Dados de exemplo (`--semear`)
# --------------------------------------------------------------------------
# Nada aqui é relato de gente de verdade. O banco local é compartilhado com o
# resto do trabalho, então o roteiro só cria e só mexe no que é dele: toda
# manifestação de exemplo nasce com `conversa_id` igual a MARCA_DE_EXEMPLO, e
# é por ela que a segunda rodada encontra a primeira em vez de duplicar.

MARCA_DE_EXEMPLO = "manual-ouvidoria"

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"

# A ouvidora de exemplo. O painel da Ouvidoria só abre para quem tem o acesso,
# e o nome dela aparece no alto de todo print: por isso é gente inventada, e
# não a conta de ninguém.
#
# A faixa de identificadores é P940 em diante porque o banco local é um só e
# cada módulo do manual tem o seu roteiro: P920 a P924 são as pessoas de
# Reuniões e metas, e semear por cima delas trocava o nome de quem responde
# pelas pendências, deixando o roteiro do outro módulo sem a tela dele.
OUVIDORA = {
    "id": "P940",
    "nome": "Cláudia Bastos",
    "email": "claudia.bastos@exemplo.local",
    "senha": "ManualOuvidoria2026!",
}

# A diretora de exemplo. A Tabela de prazos recusa quem não é Diretoria
# Executiva, e a página do manual traz esse selo: o print tem que sair da
# conta que enxerga a tela.
DIRETORA = {
    "id": "P941",
    "nome": "Regina Villaça",
    "email": "regina.villaca@exemplo.local",
    "senha": "ManualDiretoria2026!",
}

# O administrador de exemplo. Só o Super Admin abre a tela de Usuários, que é
# por onde se concede o Acesso à Ouvidoria: ter o acesso à Ouvidoria não abre
# essa porta, e a conta da ouvidora recebe "Acesso negado" nela.
ADMINISTRADOR = {
    "id": "P942",
    "nome": "Marcelo Prates",
    "email": "marcelo.prates@exemplo.local",
    "senha": "ManualAdministracao2026!",
}

# O token do portal do setor em claro. O banco guarda só o sha256 dele
# (`app/services/ouvidoria_setor_tokens.py`), então o roteiro não tem como
# descobrir o link de um token que não emitiu: ele emite o seu.
TOKEN_DO_PORTAL = "manual-do-usuario-portal-do-setor-exemplo-2026"

# A peneira da busca da tela de Usuários, no print de dar acesso: o email
# inteiro da ouvidora de exemplo. Um termo curto casaria gente de verdade, e a
# lista do hospital não entra em print de manual público.
EMAIL_DA_PESSOA_DE_EXEMPLO = OUVIDORA["email"]

RESPONSAVEL_DE_EXEMPLO = {
    "nome": "Vera Antunes",
    "email": "vera.antunes@exemplo.local",
    "setor": "Recepção",
}

# As manifestações de exemplo, uma por situação que as páginas citam. A chave
# é o apelido que o roteiro usa; `resumo` é o que identifica a linha no banco.
CASOS = {
    "para_classificar": {
        "status": "em_classificacao",
        "setor": "A definir",
        "categoria": "A classificar",
        "canal": "qr",
        "canal_setor": "Recepção",
        "canal_ponto": "Balcão principal",
        "tipo_manifestacao": None,
        "gravidade": None,
        "sigilo_reforcado": True,
        "resumo": "Esperou mais de uma hora na Recepção depois do horário marcado",
        "relato_integral": (
            "Cheguei às 8h para uma consulta marcada para 8h30 e só fui chamada "
            "perto das 10h. Ninguém explicou o motivo da demora e não havia "
            "cadeira livre na sala de espera."
        ),
        "manifestante_nome": "Marta Nogueira",
        "manifestante_contato": "marta.nogueira@exemplo.local",
        "manifestante_vinculo": "paciente",
    },
    "com_a_area": {
        "status": "aguardando_area",
        "setor": "Recepção",
        "categoria": "Atendimento",
        "canal": "telefone",
        "tipo_manifestacao": "reclamacao",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "resumo": "Fila da Recepção sem senha de prioridade no fim da tarde",
        "relato_integral": (
            "Levei minha mãe, que tem 78 anos, para um exame no fim da tarde e "
            "não havia senha de prioridade funcionando. Ficamos de pé por quase "
            "quarenta minutos."
        ),
        "extrato_para_o_setor": (
            "Apurar por que a senha de prioridade não estava em uso no turno da "
            "tarde e o que a Recepção fez para atender quem tem preferência."
        ),
        "manifestante_nome": "Iris Camargo",
        "manifestante_contato": "iris.camargo@exemplo.local",
        "manifestante_vinculo": "acompanhante",
        "prazo_area_em": "-2 dias",
        "validada_em": "-6 dias",
    },
    # O portal do setor sai deste, e não do de cima: com o prazo vencido a
    # tela recusa o pedido de prorrogação por escrito, e o print do passo
    # mostraria a recusa no lugar do caminho.
    "no_prazo": {
        "status": "aguardando_area",
        "setor": "Recepção",
        "categoria": "Atendimento",
        "canal": "site",
        "tipo_manifestacao": "reclamacao",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "resumo": "Cadeira de rodas sem disponibilidade na entrada principal",
        "relato_integral": (
            "Cheguei de táxi com meu marido, que não anda sozinho, e não havia "
            "cadeira de rodas livre na entrada principal. Esperamos vinte "
            "minutos na calçada."
        ),
        "extrato_para_o_setor": (
            "Verificar quantas cadeiras de rodas ficam na entrada principal no "
            "turno da manhã e o que a Recepção fez no dia do relato."
        ),
        "manifestante_nome": "Dalva Siqueira",
        "manifestante_contato": "dalva.siqueira@exemplo.local",
        "manifestante_vinculo": "acompanhante",
        "prazo_area_em": "+3 dias",
        "validada_em": "-1 dia",
        "token": True,
    },
    "com_pedido_de_prazo": {
        "status": "aguardando_area",
        "setor": "Nutrição",
        "categoria": "Dieta",
        "canal": "email",
        "tipo_manifestacao": "reclamacao",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "resumo": "Dieta entregue fria no quarto 312 em dois dias seguidos",
        "relato_integral": (
            "O almoço chegou frio no quarto 312 na segunda e na terça. Avisei a "
            "copa nos dois dias e não houve troca da refeição."
        ),
        "extrato_para_o_setor": (
            "Verificar o horário de saída das refeições do quarto 312 e o que a "
            "Nutrição fez depois do aviso da copa."
        ),
        "manifestante_nome": "Otávio Brandão",
        "manifestante_contato": "otavio.brandao@exemplo.local",
        "manifestante_vinculo": "paciente",
        "prazo_area_em": "+2 dias",
        "validada_em": "-3 dias",
        "prorrogacao": True,
    },
    "respondido": {
        "status": "respondido",
        "setor": "Recepção",
        "categoria": "Atendimento",
        "canal": "presencial",
        "tipo_manifestacao": "reclamacao",
        "gravidade": "medio",
        "sigilo_reforcado": False,
        "resumo": "Informação trocada sobre o preparo de um exame de sangue",
        "relato_integral": (
            "Me disseram no balcão que eu podia comer antes do exame e na hora "
            "da coleta descobri que precisava estar em jejum. Perdi a manhã de "
            "trabalho e tive que voltar outro dia."
        ),
        "extrato_para_o_setor": (
            "Apurar quem orientou o preparo do exame e o que a Recepção mudou "
            "para a orientação sair certa da próxima vez."
        ),
        "resposta_da_area": "Conversamos com a equipe e vamos reforçar o treinamento.",
        "respondida_por_nome": "Vera Antunes",
        "respondida_em": "-1 dia",
        "manifestante_nome": "Teresa Vilela",
        "manifestante_contato": "teresa.vilela@exemplo.local",
        "prazo_area_em": "+1 dia",
        "validada_em": "-4 dias",
    },
    "encerrado": {
        "status": "encerrado",
        "setor": "Nutrição",
        "categoria": "Dieta",
        "canal": "telefone",
        "tipo_manifestacao": "elogio",
        "gravidade": "baixo",
        "sigilo_reforcado": False,
        "resumo": "Elogio à equipe da Nutrição pelo atendimento no quarto 208",
        "relato_integral": (
            "Queria registrar o cuidado da equipe da Nutrição com a dieta do meu "
            "pai, internado no quarto 208. Explicaram tudo com paciência."
        ),
        "extrato_para_o_setor": "Registrar o elogio com a equipe da Nutrição.",
        "resposta_da_area": "Elogio repassado à equipe na reunião do setor.",
        "respondida_por_nome": "Vera Antunes",
        "respondida_em": "-8 dias",
        "manifestante_nome": "Sérgio Bastos",
        "manifestante_contato": "sergio.bastos@exemplo.local",
        "desfecho": "procedente",
        "desfecho_descricao": (
            "Levamos o seu elogio à equipe da Nutrição. Obrigado por avisar a "
            "Ouvidoria."
        ),
        "encerrada_em": "-6 dias",
        "validada_em": "-12 dias",
    },
    "arquivado": {
        "status": "encerrado",
        "setor": "Recepção",
        "categoria": "Atendimento",
        "canal": "site",
        "tipo_manifestacao": "sugestao",
        "gravidade": "baixo",
        "sigilo_reforcado": False,
        "resumo": "Sugestão de placa indicando o caminho até o laboratório",
        "relato_integral": (
            "Seria bom ter uma placa no corredor do térreo indicando o caminho "
            "até o laboratório. Muita gente se perde na primeira vez."
        ),
        "extrato_para_o_setor": "Avaliar a sinalização do corredor do térreo.",
        "resposta_da_area": "Sinalização nova encomendada para o corredor.",
        "respondida_por_nome": "Vera Antunes",
        "respondida_em": "-20 dias",
        "manifestante_nome": "Nilce Ferraz",
        "manifestante_contato": "nilce.ferraz@exemplo.local",
        "desfecho": "procedente",
        "desfecho_descricao": (
            "A sinalização do corredor foi encomendada. Obrigado pela sugestão."
        ),
        "encerrada_em": "-18 dias",
        "validada_em": "-25 dias",
        "arquivada_em": "-10 dias",
    },
}


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


def _rest(url, chave, caminho, metodo="GET", corpo=None, prefer=None):
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


def _quando(receita: str) -> str:
    """"-2 dias" e "+1 dia" viram o instante correspondente, em ISO."""
    sinal = -1 if receita.startswith("-") else 1
    dias = int(receita.strip("+-").split()[0])
    momento = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=sinal * dias)
    return momento.isoformat()


def _login_de_exemplo(url: str, chave: str, email: str, senha: str) -> str:
    """Cria (ou reaproveita) o login da pessoa de exemplo no Supabase local."""
    corpo = json.dumps({"email": email, "password": senha, "email_confirm": True}).encode()
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


def _caso_semeado(url: str, chave: str, apelido: str, receita: dict) -> dict:
    """Cria a manifestação de exemplo, ou devolve a que já existe.

    A busca é pelo `resumo` dentro da marca do roteiro: o protocolo é gerado
    pelo banco e muda de máquina para máquina, então ele não serve de chave.
    """
    filtro = (
        f"ouvidoria_protocolos?conversa_id=eq.{MARCA_DE_EXEMPLO}"
        f"&resumo=eq.{urllib.parse.quote(receita['resumo'])}&select=*"
    )
    achado = _rest(url, chave, filtro)
    if achado:
        return achado[0]

    linha = {
        "conversa_id": MARCA_DE_EXEMPLO,
        "data_abertura": dt.date.today().isoformat(),
        "dados_incompletos": False,
        "anonimo": False,
        "manifestante_vinculo": "paciente",
    }
    for campo, valor in receita.items():
        if campo in ("prorrogacao", "token"):
            continue
        if isinstance(valor, str) and (valor.startswith("-") or valor.startswith("+")) and "dia" in valor:
            linha[campo] = _quando(valor)
        else:
            linha[campo] = valor
    criado = _rest(
        url, chave, "ouvidoria_protocolos", "POST", [linha], prefer="return=representation"
    )
    return criado[0]


def semear() -> None:
    """A ouvidora de exemplo, os responsáveis e uma manifestação por situação."""
    url, chave = _credenciais_locais()

    _rest(
        url,
        chave,
        "participantes",
        "POST",
        [
            {
                "id": OUVIDORA["id"],
                "nome_completo": OUVIDORA["nome"],
                "email": OUVIDORA["email"],
                "cargo": "Ouvidora",
                "setor": "Administração",
                "role": "coordenador",
                "ativo": True,
                "access_profile": "regular",
                "perfil_ouvidoria": "ouvidor",
                "is_super_admin": True,
                "is_externo": False,
                "auth_user_id": _login_de_exemplo(
                    url, chave, OUVIDORA["email"], OUVIDORA["senha"]
                ),
            }
        ],
        prefer="resolution=merge-duplicates",
    )

    if not _rest(
        url,
        chave,
        "ouvidoria_setor_responsaveis?setor=eq."
        + urllib.parse.quote(RESPONSAVEL_DE_EXEMPLO["setor"])
        + "&email=eq."
        + urllib.parse.quote(RESPONSAVEL_DE_EXEMPLO["email"])
        + "&select=id",
    ):
        _rest(
            url,
            chave,
            "ouvidoria_setor_responsaveis",
            "POST",
            [
                {
                    "setor": RESPONSAVEL_DE_EXEMPLO["setor"],
                    "papel": "titular",
                    "nome": RESPONSAVEL_DE_EXEMPLO["nome"],
                    "email": RESPONSAVEL_DE_EXEMPLO["email"],
                    "vigencia_inicio": "2026-01-01",
                }
            ],
        )

    _rest(
        url,
        chave,
        "participantes",
        "POST",
        [
            {
                "id": DIRETORA["id"],
                "nome_completo": DIRETORA["nome"],
                "email": DIRETORA["email"],
                "cargo": "Diretora Executiva",
                "setor": "Administração",
                "role": "gerente",
                "ativo": True,
                "access_profile": "regular",
                "perfil_ouvidoria": "diretoria_executiva",
                "is_super_admin": False,
                "is_externo": False,
                "auth_user_id": _login_de_exemplo(
                    url, chave, DIRETORA["email"], DIRETORA["senha"]
                ),
            }
        ],
        prefer="resolution=merge-duplicates",
    )

    _rest(
        url,
        chave,
        "participantes",
        "POST",
        [
            {
                "id": ADMINISTRADOR["id"],
                "nome_completo": ADMINISTRADOR["nome"],
                "email": ADMINISTRADOR["email"],
                "cargo": "Analista de Sistemas",
                "setor": "Administração",
                "role": "coordenador",
                "ativo": True,
                "access_profile": "super_admin",
                "is_super_admin": True,
                "is_externo": False,
                "auth_user_id": _login_de_exemplo(
                    url, chave, ADMINISTRADOR["email"], ADMINISTRADOR["senha"]
                ),
            }
        ],
        prefer="resolution=merge-duplicates",
    )

    for apelido, receita in CASOS.items():
        caso = _caso_semeado(url, chave, apelido, receita)
        if receita.get("token"):
            hash_do_token = hashlib.sha256(TOKEN_DO_PORTAL.encode()).hexdigest()
            existente = _rest(
                url,
                chave,
                f"ouvidoria_setor_tokens?token_hash=eq.{hash_do_token}"
                "&select=id,manifestacao_id",
            )
            if existente and existente[0]["manifestacao_id"] != caso["id"]:
                # O link é um só, e ele acompanha o caso de exemplo do portal.
                # Quando o roteiro troca de caso, o token existente muda de
                # dono em vez de nascer um segundo, que abriria a porta antiga.
                _rest(
                    url,
                    chave,
                    f"ouvidoria_setor_tokens?id=eq.{existente[0]['id']}",
                    "PATCH",
                    {
                        "manifestacao_id": caso["id"],
                        "expira_em": _quando("+20 dias"),
                        "usado_em": None,
                        "revogado_em": None,
                    },
                )
            elif not existente:
                _rest(
                    url,
                    chave,
                    "ouvidoria_setor_tokens",
                    "POST",
                    [
                        {
                            "manifestacao_id": caso["id"],
                            "destinatario_nome": RESPONSAVEL_DE_EXEMPLO["nome"],
                            "destinatario_email": RESPONSAVEL_DE_EXEMPLO["email"],
                            "token_hash": hash_do_token,
                            "expira_em": _quando("+20 dias"),
                        }
                    ],
                )
        if receita.get("prorrogacao") and not _rest(
            url, chave, f"ouvidoria_prorrogacoes?manifestacao_id=eq.{caso['id']}&select=id"
        ):
            _rest(
                url,
                chave,
                "ouvidoria_prorrogacoes",
                "POST",
                [
                    {
                        "manifestacao_id": caso["id"],
                        "justificativa": (
                            "A copa está em reforma até sexta e o horário de saída "
                            "das refeições muda todo dia. Precisamos da semana "
                            "inteira para apurar com segurança."
                        ),
                        "dias_uteis_pedidos": 2,
                        "prazo_anterior": caso["prazo_area_em"],
                        "prazo_novo": _quando("+4 dias"),
                        "status": "pendente",
                        "solicitante_nome": RESPONSAVEL_DE_EXEMPLO["nome"],
                        "solicitante_email": RESPONSAVEL_DE_EXEMPLO["email"],
                    }
                ],
            )

    print("dados de exemplo do módulo Ouvidoria prontos.")



def restaurar_os_casos() -> None:
    """Devolve as manifestações de exemplo ao estado em que foram semeadas.

    Capturar mexe no banco: o print do Arquivar clica no Arquivar, e o caso
    encerrado sai da lista para a rodada seguinte. Em vez de pedir que cada
    função desfaça o que fez, o roteiro repõe o estado antes de começar. Só as
    linhas com a marca deste roteiro, e sempre pela marca.
    """
    url, chave = _credenciais_locais()
    for receita in CASOS.values():
        campos = {
            "status": receita["status"],
            "arquivada_em": _quando(receita["arquivada_em"])
            if receita.get("arquivada_em")
            else None,
        }
        _rest(
            url,
            chave,
            f"ouvidoria_protocolos?conversa_id=eq.{MARCA_DE_EXEMPLO}"
            f"&resumo=eq.{urllib.parse.quote(receita['resumo'])}",
            "PATCH",
            campos,
        )


def protocolo_do(apelido: str) -> str:
    """O protocolo da manifestação de exemplo, lido do banco local."""
    url, chave = _credenciais_locais()
    resumo = CASOS[apelido]["resumo"]
    achado = _rest(
        url,
        chave,
        f"ouvidoria_protocolos?conversa_id=eq.{MARCA_DE_EXEMPLO}"
        f"&resumo=eq.{urllib.parse.quote(resumo)}&select=protocolo",
    )
    if not achado:
        raise SystemExit(
            f"não achei a manifestação de exemplo '{apelido}'. Rode "
            "`python3 docs/manual/prints/ouvidoria.py --semear` antes."
        )
    return achado[0]["protocolo"]


PRINTS = {
    # Registrar uma manifestação pelo formulário
    "formulario-publico": formulario_publico,
    # Imprimir o cartaz com o QR do setor
    "pontos": pontos,
    "cartaz-pa": cartaz_pa,
    # Registrar uma manifestação pela Ouvidoria
    "fila-nova-manifestacao": fila_nova_manifestacao,
    # Cobrar o setor que não respondeu
    "fila-cobrar": fila_cobrar,
    # Arquivar um caso encerrado
    "fila-arquivar": fila_arquivar,
    "fila-arquivados": fila_arquivados,
    # Acompanhar o painel da Ouvidoria
    "fila-painel": fila_painel,
    "painel": painel,
    # Ajustar a tabela de prazos e os feriados
    "prazos": prazos,
    # Cadastrar responsáveis de setor
    "responsaveis": responsaveis,
    # Lançar a nota do Google e do Reclame Aqui
    "nota-externa": nota_externa,
    # Classificar e acionar um caso
    "caso-validar": caso_validar,
    "validar-modal": validar_modal,
    # Registrar uma manifestação pela Ouvidoria
    "nova-manifestacao-modal": nova_manifestacao_modal,
    "canal-de-origem": canal_de_origem,
    # Encerrar um caso e avisar a pessoa
    "caso-encerrar": caso_encerrar,
    "encerrar-modal": encerrar_modal,
    "email-encerramento": email_encerramento,
    # Devolver uma resposta fraca ao setor
    "caso-respondido": caso_respondido,
    # Decidir um pedido de mais prazo
    "caso-prorrogacao": caso_prorrogacao,
    # Pausar o caso quando falta informação
    "caso-pausar": caso_pausar,
    # Reabrir um caso por reincidência
    "caso-reabrir": caso_reabrir,
    # Redirecionar o caso para outra área
    "caso-redirecionar": caso_redirecionar,
    "redirecionar-modal": redirecionar_modal,
    # Responder um caso pelo portal do setor
    "email-demanda": email_demanda,
    "portal-setor-mobile": portal_setor_mobile,
    # Pedir mais prazo pelo portal do setor
    "portal-prorrogacao": portal_prorrogacao,
    "portal-prorrogacao-formulario": portal_prorrogacao_formulario,
    # Devolver um caso que não é do seu setor
    "portal-devolver": portal_devolver,
    "portal-devolver-formulario": portal_devolver_formulario,
    # Dar acesso à Ouvidoria a alguém
    "usuarios-acesso-ouvidoria": usuarios_acesso_ouvidoria,
    "editar-acesso-ouvidoria": editar_acesso_ouvidoria,
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
    ap.add_argument(
        "--semear",
        action="store_true",
        help="cria os dados de exemplo no Supabase local e sai.",
    )
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

    restaurar_os_casos()

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
