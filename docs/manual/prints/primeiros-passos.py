#!/usr/bin/env python3
"""Roteiro de prints do módulo Primeiros passos (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

Duas telas daqui são **abertas, sem conta**: a entrada e o pedido de
redefinição de senha. As outras (Meu Perfil, Configurações) só existem depois
do login, e é por isso que o roteiro tem uma pessoa de exemplo própria, criada
pelo `--semear`: entrar com uma conta de verdade do hospital publicaria nome,
cargo e e-mail de gente real num site público.

Todo print que fica sob um passo leva o **balão numerado** do passo, desenhado
por `balao()` sobre a tela antes da captura (ADR 0057, emenda de 17/09/2026).
Um print por mudança de tela: passos na mesma tela dividem um print com vários
balões.

Receita:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. A pessoa de exemplo: `python3 docs/manual/prints/primeiros-passos.py
   --semear`. É idempotente e recusa rodar contra qualquer banco que não seja
   o local.
4. `python3 docs/manual/prints/primeiros-passos.py`.

Uso: python3 docs/manual/prints/primeiros-passos.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/primeiros-passos] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

# O Playwright só é preciso para capturar: `--semear` e a guarda que protege o
# banco rodam sem ele, e é isso que deixa o teste da guarda importar este
# arquivo numa máquina sem navegador instalado.
if TYPE_CHECKING:
    from playwright.sync_api import Page

# Tela de trabalho sentada: a entrada na plataforma se faz no computador.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

# A pessoa de exemplo do módulo, criada pelo `--semear`.
NOME = "Paula Nogueira"
EMAIL = "paula.nogueira@exemplo.local"
SENHA = "ManualPrimeirosPassos2026!"

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


def _sem_foco(page: Page) -> None:
    """Tira o foco de qualquer campo: o anel de foco numa captura parada vira
    instrução falsa ("clique aqui") para quem lê a página."""
    page.evaluate("() => document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(300)


def entrar(page: Page, base: str) -> None:
    """Login com a pessoa de exemplo, para as telas de dentro da plataforma.

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


def _sem_conta(page: Page, base: str) -> None:
    """Deixa o navegador sem conta antes das telas abertas.

    O roteiro captura telas de dentro e telas de fora na mesma sessão. Sem
    isto, quem já entrou é levado direto para o painel e o print da porta da
    plataforma sai da tela errada.
    """
    page.goto(f"{base}/login", wait_until="domcontentloaded")
    page.evaluate("() => { localStorage.clear(); sessionStorage.clear(); }")
    page.context.clear_cookies()
    page.goto(f"{base}/login", wait_until="networkidle")


def _coluna_do_formulario(page: Page):
    """A coluna estreita onde as telas abertas mostram o formulário.

    Entrada e redefinição de senha são uma coluna no meio de muito branco: o
    recorte é nela, senão a página do manual mostra mais vazio do que campo.
    """
    return page.locator("div.max-w-md").first


def tela_de_entrada(page: Page, base: str, saida: Path) -> None:
    """A porta da plataforma, com os dois campos e o botão de entrar."""
    _sem_conta(page, base)
    page.get_by_role("heading", name="Bem-vindo de volta").wait_for()
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("heading", name="Bem-vindo de volta"), 1)
    balao(page, page.get_by_placeholder("seu@email.com"), 2)
    balao(page, page.get_by_placeholder("••••••••"), 3)
    balao(page, page.get_by_role("button", name="Entrar"), 4)
    capturar(
        page,
        saida / "tela-de-entrada.png",
        "tela-de-entrada",
        alvo=_coluna_do_formulario(page),
    )


def link_esqueci_minha_senha(page: Page, base: str, saida: Path) -> None:
    """O link da senha esquecida, logo abaixo do campo de senha."""
    _sem_conta(page, base)
    page.get_by_role("heading", name="Bem-vindo de volta").wait_for()
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("link", name="Esqueci minha senha"), 1)
    capturar(
        page,
        saida / "link-esqueci-minha-senha.png",
        "link-esqueci-minha-senha",
        alvo=_coluna_do_formulario(page),
    )


def esqueci_minha_senha(page: Page, base: str, saida: Path) -> None:
    """O pedido do link de redefinição, com o único campo que ele precisa."""
    _sem_conta(page, base)
    page.goto(f"{base}/reset-password", wait_until="networkidle")
    page.get_by_role("heading", name="Esqueci minha senha").wait_for()
    page.get_by_placeholder("seu@email.com").fill(EMAIL)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_placeholder("seu@email.com"), 2)
    capturar(
        page,
        saida / "esqueci-minha-senha.png",
        "esqueci-minha-senha",
        alvo=_coluna_do_formulario(page),
    )


def verifique_seu_email(page: Page, base: str, saida: Path) -> None:
    """A resposta do pedido: daqui em diante o caminho é o e-mail.

    A tela de escolher a senha nova nasce do link que chega por e-mail e não
    tem como ser capturada aqui; este é o último estado que a plataforma
    mostra.
    """
    _sem_conta(page, base)
    page.goto(f"{base}/reset-password", wait_until="networkidle")
    page.get_by_role("heading", name="Esqueci minha senha").wait_for()
    page.get_by_placeholder("seu@email.com").fill(EMAIL)
    page.get_by_role("button", name="Enviar link de redefinição").click()
    page.get_by_role("heading", name="Verifique seu email").wait_for(timeout=30000)
    page.wait_for_timeout(800)
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_role("heading", name="Verifique seu email"), 3)
    capturar(
        page,
        saida / "verifique-seu-email.png",
        "verifique-seu-email",
        alvo=_coluna_do_formulario(page),
    )


def _abrir_menu_do_usuario(page: Page, base: str) -> None:
    """Abre o menu que fica sob o seu nome, no alto da tela à direita."""
    entrar(page, base)
    page.goto(f"{base}/dashboard", wait_until="networkidle")
    page.wait_for_timeout(1500)
    page.get_by_text(EMAIL.split("@")[0], exact=True).first.click()
    page.get_by_role("button", name="Meu Perfil").wait_for()
    page.wait_for_timeout(600)


def _recorte_do_menu() -> dict:
    """O canto de cima à direita, onde o menu do usuário se abre."""
    return {"x": 940, "y": 0, "width": 500, "height": 320}


def menu_do_usuario_perfil(page: Page, base: str, saida: Path) -> None:
    """O menu do seu nome, com o caminho para Meu Perfil."""
    _abrir_menu_do_usuario(page, base)
    limpar_baloes(page)
    balao(page, page.get_by_text(EMAIL.split("@")[0], exact=True).first, 1)
    # O balão vai no ícone do item, e não no item inteiro: no canto do menu
    # ele encostaria na borda da janelinha e sairia pela metade.
    balao(page, page.get_by_role("button", name="Meu Perfil").locator("svg"), 2)
    capturar(
        page,
        saida / "menu-do-usuario-perfil.png",
        "menu-do-usuario-perfil",
        clip=_recorte_do_menu(),
    )


def menu_do_usuario_configuracoes(page: Page, base: str, saida: Path) -> None:
    """O mesmo menu, com o caminho para Configurações."""
    _abrir_menu_do_usuario(page, base)
    limpar_baloes(page)
    balao(page, page.get_by_role("button", name="Configurações").locator("svg"), 1)
    capturar(
        page,
        saida / "menu-do-usuario-configuracoes.png",
        "menu-do-usuario-configuracoes",
        clip=_recorte_do_menu(),
    )


def meu_perfil(page: Page, base: str, saida: Path) -> None:
    """O cartão do seu cadastro: com que dados a plataforma conhece você.

    A tela escreve "Area" e "Cargo nao informado" sem acento, e o print sai
    como a tela é: corrigir a imagem faria o manual prometer uma palavra que
    ninguém encontra.
    """
    entrar(page, base)
    page.goto(f"{base}/perfil", wait_until="networkidle")
    page.get_by_text(NOME, exact=True).first.wait_for()
    page.wait_for_timeout(1000)
    _sem_foco(page)
    limpar_baloes(page)
    cartao = page.locator("div.rounded-2xl").first
    # O balão vai na foto, e não no nome nem no cartão inteiro: o nome é
    # cortado com reticências quando não cabe, e um balão no próprio quadro que
    # a captura recorta nasceria para fora da imagem.
    balao(page, cartao.locator("div.rounded-full").first, 3)
    capturar(page, saida / "meu-perfil.png", "meu-perfil", alvo=cartao)


def _abrir_configuracoes(page: Page, base: str, aba: str) -> None:
    entrar(page, base)
    page.goto(f"{base}/configuracoes", wait_until="networkidle")
    page.get_by_role("heading", name="Configurações").wait_for()
    page.get_by_text(aba, exact=True).first.click()
    page.wait_for_timeout(1000)


def configuracoes_seguranca(page: Page, base: str, saida: Path) -> None:
    """A aba Segurança: a troca da senha sem passar pelo e-mail."""
    _abrir_configuracoes(page, base, "Segurança")
    page.get_by_role("button", name="Alterar senha").wait_for()
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_text("Segurança", exact=True).first, 2)
    balao(page, page.get_by_placeholder("Mínimo 8 caracteres"), 3)
    balao(page, page.get_by_placeholder("Repita a nova senha"), 4)
    balao(page, page.get_by_role("button", name="Alterar senha"), 5)
    # Recorte no alto: abaixo do quadro a janela é só branco, que na página do
    # manual viraria uma faixa vazia do tamanho do print.
    capturar(
        page,
        saida / "configuracoes-seguranca.png",
        "configuracoes-seguranca",
        clip={"x": 0, "y": 0, "width": 1440, "height": 420},
    )


def configuracoes_notificacoes(page: Page, base: str, saida: Path) -> None:
    """A aba Notificações, com as quatro chaves que a pessoa liga e desliga."""
    _abrir_configuracoes(page, base, "Notificações")
    page.get_by_text("Menções em comentários").wait_for()
    _sem_foco(page)
    limpar_baloes(page)
    balao(page, page.get_by_text("Notificações", exact=True).first, 2)
    balao(page, page.get_by_text("Menções em comentários"), 3)
    capturar(
        page,
        saida / "configuracoes-notificacoes.png",
        "configuracoes-notificacoes",
        clip={"x": 0, "y": 0, "width": 1440, "height": 470},
    )


PRINTS = {
    "tela-de-entrada": tela_de_entrada,
    "link-esqueci-minha-senha": link_esqueci_minha_senha,
    "esqueci-minha-senha": esqueci_minha_senha,
    "verifique-seu-email": verifique_seu_email,
    "menu-do-usuario-perfil": menu_do_usuario_perfil,
    "menu-do-usuario-configuracoes": menu_do_usuario_configuracoes,
    "meu-perfil": meu_perfil,
    "configuracoes-seguranca": configuracoes_seguranca,
    "configuracoes-notificacoes": configuracoes_notificacoes,
}


# --------------------------------------------------------------------------
# Dados de exemplo (`--semear`)
# --------------------------------------------------------------------------

# A pessoa é inventada e o domínio `exemplo.local` não existe. É o que permite
# um print de Meu Perfil num repositório público.
# O identificador sai da faixa dos outros roteiros de exemplo (P900 no POPs,
# P910 no Admin, P920 na Ouvidoria): repetir um deles sobrescreveria a pessoa
# de exemplo de outro módulo, que este roteiro não criou.
PESSOA = {
    "id": "P930",
    "nome_completo": NOME,
    "email": EMAIL,
    "cargo": "Analista de Qualidade",
    "setor": "Qualidade",
    "area": "Administrativo",
    "role": "coordenador",
    "ativo": True,
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
    """A pessoa de exemplo que entra na plataforma nos prints deste módulo."""
    url, chave = _credenciais_locais()
    _rest(
        url,
        chave,
        "participantes",
        "POST",
        [{**PESSOA, "auth_user_id": _login_de_exemplo(url, chave, EMAIL)}],
        prefer="resolution=merge-duplicates",
    )
    print("dados de exemplo do módulo Primeiros passos prontos.")


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
