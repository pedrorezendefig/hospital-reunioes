#!/usr/bin/env python3
"""Roteiro de prints do módulo Admin (ADR 0057, decisão 3).

Cada print do manual é tela real do app rodando em localhost, capturada por
este roteiro, e não recorte feito à mão: quando a tela muda, é este arquivo que
roda de novo e refaz as imagens.

**Este módulo é o mais perigoso do manual para dado pessoal.** A tela de
Usuários é, literalmente, a lista de nome e email de gente real, e o
repositório é público. Por isso o roteiro nunca captura a lista inteira: ele
digita `exemplo` na busca da tela, que filtra por nome ou email, e só as
pessoas de exemplo criadas pelo `--semear` (todas em `@exemplo.local`)
sobrevivem ao filtro. Tirar esse filtro publica dado real.

Receita:

1. Supabase local no ar (`supabase start` em `hospital-reunioes/`).
2. Stack do app com o código que o print vai mostrar:
   `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. Dados de exemplo do módulo (as quatro pessoas fictícias e a conta de Super
   Admin que entra na plataforma):
   `python3 docs/manual/prints/admin.py --semear`. É idempotente e recusa
   rodar contra qualquer banco que não seja o local.
4. `python3 docs/manual/prints/admin.py`.

O painel de Administração só mostra as quatro seções para quem é Super Admin,
então o roteiro entra com a pessoa de exemplo (Camila Prado), criada pelo
`--semear`.

Uso: python3 docs/manual/prints/admin.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/admin] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

# O Playwright só é preciso para capturar: `--semear` e a guarda que protege o
# banco rodam sem ele, e é isso que deixa o teste da guarda importar este
# arquivo numa máquina sem navegador instalado.
if TYPE_CHECKING:
    from playwright.sync_api import Page

# Tela de trabalho sentada: administração se faz no computador.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

# A pessoa de exemplo do módulo, criada pelo `--semear`.
EMAIL = "camila.prado@exemplo.local"
SENHA = "ManualAdmin2026!"

# A pessoa de exemplo do print da senha gerada. Ela existe só para isso: a
# janela "Senha gerada" mostra uma senha de verdade, e senha de verdade num
# print só pode ser de gente que não existe. O roteiro a desativa no fim, para
# não deixar de pé uma conta de exemplo com senha conhecida.
# (id, nome, email, cargo, setor, role, perfil de acesso, super admin, externo)
PESSOA_DA_SENHA = (
    "P914",
    "Helena Castro",
    "helena.castro@exemplo.local",
    "Coordenador de Enfermagem",
    "Centro de Terapia Intensiva",
    "coordenador",
    "regular",
    False,
    False,
)

# O termo que a busca da tela de Usuários recebe. Ele casa com o domínio de
# email de toda pessoa de exemplo e com nenhuma pessoa real: é a peneira que
# mantém dado de gente de verdade fora do print.
#
# O valor é carga, não enfeite. Vazio, a busca devolve a lista inteira; curto
# demais ("a"), casa gente de verdade. Por isso ele é conferido em tempo de
# execução por `_conferir_o_filtro` e travado no valor exato pelo teste.
FILTRO_DE_EXEMPLO = "exemplo"

# Abaixo disto o termo deixa de ser específico e passa a casar nome de gente
# real. Quatro letras é o que separa "exemplo" de "a".
MINIMO_DO_FILTRO = 4

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"


# O email de cada pessoa de exemplo, que é a peneira de um print de uma linha
# só. Sempre o email, e nunca o primeiro nome: "Helena" casaria uma Helena de
# verdade, e o domínio de exemplo não casa ninguém do hospital.
EMAIL_DE = {
    "Bruno Tavares": "bruno.tavares@exemplo.local",
    "Sofia Lemos": "sofia.lemos@exemplo.local",
    "Diego Rocha": "diego.rocha@exemplo.local",
    "Helena Castro": "helena.castro@exemplo.local",
}


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
# Prints
# --------------------------------------------------------------------------


def entrar(page: Page, base: str) -> None:
    """Login com a pessoa de exemplo. O painel inteiro exige Super Admin.

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


def _conferir_o_filtro(termo: str) -> None:
    """Recusa capturar quando o filtro deixou de ser uma peneira.

    A guarda é de execução, e não só de teste, porque o dano é gravar um
    arquivo: com o termo vazio a busca devolve a lista inteira, e o `.png` com
    nome e email de gente do hospital já estaria escrito em disco quando
    alguém fosse reparar. Falha fechada, antes de abrir a tela.

    Duas exigências, e não uma. O tamanho sozinho não basta: um print que
    peneira por uma pessoa (o email inteiro dela) passaria no tamanho e ainda
    assim casaria gente de verdade se o nome fosse "Helena". O que separa
    exemplo de gente do hospital é o domínio `exemplo.local`, e é por ele que
    todo termo tem que passar.
    """
    limpo = termo.strip()
    if len(limpo) < MINIMO_DO_FILTRO:
        raise SystemExit(
            f"recusado: o filtro da busca é '{termo}', com menos de "
            f"{MINIMO_DO_FILTRO} letras. Termo curto casa gente de verdade, e o "
            "print da lista de Usuários sairia com nome e email reais."
        )
    if FILTRO_DE_EXEMPLO not in limpo.lower():
        raise SystemExit(
            f"recusado: o filtro da busca é '{termo}', que não contém "
            f"'{FILTRO_DE_EXEMPLO}'. Só o domínio das pessoas de exemplo "
            "mantém gente do hospital fora do print."
        )


def _usuarios_filtrados(
    page: Page, base: str, termo: str = None, espera: str = "Camila Prado"
) -> None:
    """Abre a tela de Usuários já peneirada pelas pessoas de exemplo.

    A busca é digitada ANTES de qualquer espera de linha: entre abrir a tela e
    filtrar existe um instante com a lista real na tela, e capturar nele seria
    publicar nome e email de gente do hospital.

    `termo` estreita a peneira quando o balão do passo aponta uma linha: com o
    termo largo a lista cresce a cada pessoa de exemplo que outro roteiro
    cria, e a linha que o print precisa mostrar escorrega para fora do corte.
    """
    # O padrão é lido AQUI, e não na assinatura: preso no `def`, ele guardaria
    # para sempre o valor do arranque, e trocar a constante (inclusive para
    # testar a guarda com um termo frouxo) não mudaria nada.
    termo = termo or FILTRO_DE_EXEMPLO
    _conferir_o_filtro(termo)
    page.goto(f"{base}/admin/usuarios", wait_until="networkidle")
    busca = page.get_by_placeholder("Buscar por nome ou email…")
    busca.wait_for()
    busca.fill(termo)
    page.get_by_role("cell", name=espera).wait_for(timeout=15000)
    # A lista recarrega a cada tecla: sem esta pausa o print pega o esqueleto
    # de carregamento no lugar das linhas.
    page.wait_for_timeout(1500)


def _mudar_ativo_da_pessoa_da_senha(ativo: bool) -> None:
    """Liga e desliga a pessoa de exemplo do print da senha.

    Só ela, e pelo id: é registro que este roteiro criou, e o banco local é
    compartilhado com o resto do trabalho.
    """
    url, chave = _credenciais_locais()
    _rest(
        url,
        chave,
        f"participantes?id=eq.{PESSOA_DA_SENHA[0]}",
        "PATCH",
        {"ativo": ativo},
    )


def _ativar_pessoa_da_senha() -> None:
    _mudar_ativo_da_pessoa_da_senha(True)


def _desativar_pessoa_da_senha() -> None:
    _mudar_ativo_da_pessoa_da_senha(False)


def _com_janela_alta(page: Page, altura: int = 1400):
    """Aumenta a altura da janela para o formulário caber inteiro no print.

    Alguns formulários do painel são mais altos do que uma tela de notebook e
    rolam por dentro. Num print isso obriga a escolher entre mostrar o alto e
    mostrar o fim, e um dos balões do passo sempre fica de fora. A janela mais
    alta é a mesma tela, num monitor maior: nada de layout muda, só cabe mais.
    """
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": altura})
    page.wait_for_timeout(500)


def _janela_normal(page: Page) -> None:
    page.set_viewport_size(COMPUTADOR)
    page.wait_for_timeout(500)


def _modal(page: Page, titulo: str):
    """A caixa do modal, para capturar o formulário sem a lista desfocada atrás."""
    return page.get_by_role("heading", name=titulo, exact=True).locator(
        "xpath=ancestor::div[contains(@class,'rounded')][1]"
    )


def _campo(page: Page, rotulo: str):
    """O `input` que vem depois do rótulo escrito na tela."""
    return page.locator(
        f"xpath=//span[starts-with(normalize-space(),'{rotulo}')]/following::input[1]"
    )


def _campo_do_bloco(page: Page, legenda: str):
    """O controle logo abaixo da legenda de um bloco do formulário.

    O balão vai no controle, e não na legenda: a legenda encosta na borda
    esquerda do formulário, e ali o balão comeria as primeiras letras dela.
    """
    return page.locator("fieldset").filter(has_text=legenda).locator(
        "[role='combobox'], input, select"
    ).first


def _link_da_barra(page: Page, href: str):
    return page.locator(f"aside a[href='{href}']")


def _cabecalho(page: Page, texto: str):
    """A célula de cabeçalho da tabela, pelo texto que ela guarda.

    Não é `get_by_role("columnheader", name=...)`: o cabeçalho é desenhado em
    caixa alta pelo CSS, e o nome acessível que o Playwright calcula vem da
    caixa RENDERIZADA ("ATIVO"), não do texto do DOM ("Ativo").
    """
    return page.locator("thead th").filter(has_text=texto).first


def _linha(page: Page, nome: str):
    """A linha da tabela de uma pessoa de exemplo."""
    return page.get_by_role("row").filter(has_text=nome).first


def _acao_da_linha(page: Page, nome: str, titulo: str):
    """O ícone de ação da linha, achado pelo `title` que a tela usa."""
    return _linha(page, nome).locator(f"button[title^='{titulo}']").first


def painel_de_administracao(page: Page, base: str, saida: Path) -> None:
    """O painel inteiro: a barra com as quatro seções e a lista de Usuários.

    É o print da Visão geral do módulo, e por isso o único sem balão: ele não
    ilustra passo nenhum.
    """
    entrar(page, base)
    _usuarios_filtrados(page, base)
    page.screenshot(
        path=str(saida / "painel-de-administracao.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 620},
    )


def usuarios_cadastrar(page: Page, base: str, saida: Path) -> None:
    """Cadastrar uma pessoa, passos 1 e 2: a lista e o botão que abre a ficha."""
    entrar(page, base)
    _usuarios_filtrados(page, base)
    sem_foco(page)
    balao(page, _link_da_barra(page, "/admin/usuarios"), 1)
    balao(page, page.get_by_role("button", name="Novo Usuário"), 2)
    page.screenshot(
        path=str(saida / "usuarios-cadastrar.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 620},
    )
    limpar_baloes(page)


def novo_usuario(page: Page, base: str, saida: Path) -> None:
    """O formulário de cadastro, preenchido como quem cadastra preencheria.

    A captura é do modal, e não da tela toda: o formulário é o assunto, e a
    lista atrás dele entra desfocada no print de página inteira. O formulário
    é preenchido e NÃO é enviado, para não criar gente a cada rodada.
    """
    entrar(page, base)
    _usuarios_filtrados(page, base)
    page.get_by_role("button", name="Novo Usuário").click()
    page.get_by_role("heading", name="Novo usuário").wait_for()
    # A abertura do modal tem animação: capturar antes dela terminar sai
    # translúcido.
    page.wait_for_timeout(1200)
    _campo(page, "Nome completo").fill("Bruno Tavares")
    _campo(page, "Email").fill("bruno.tavares@exemplo.local")
    _campo(page, "Cargo").fill("Coordenador de Enfermagem")
    _campo(page, "Setor").fill("Centro de Terapia Intensiva")
    # Sem foco em campo nenhum: o cursor piscando no último campo aparece no
    # print como um traço solto.
    page.get_by_role("heading", name="Novo usuário").click()
    sem_foco(page)
    balao(page, page.locator("legend", has_text="Perfil de acesso"), 3)
    balao(page, _campo(page, "Nome completo"), 4)
    balao(page, _campo(page, "Cargo"), 5)
    balao(page, page.locator("legend, span").filter(has_text="Role (cargo hospitalar)").first, 6)
    _modal(page, "Novo usuário").screenshot(path=str(saida / "novo-usuario.png"))
    limpar_baloes(page)


def usuarios_resetar_senha(page: Page, base: str, saida: Path) -> None:
    """Entregar o acesso, passos 1 e 2: achar a pessoa e clicar na chave."""
    entrar(page, base)
    _ativar_pessoa_da_senha()
    _usuarios_filtrados(page, base, EMAIL_DE["Helena Castro"], "Helena Castro")
    sem_foco(page)
    balao(page, page.get_by_placeholder("Buscar por nome ou email…"), 1)
    balao(page, _acao_da_linha(page, PESSOA_DA_SENHA[1], "Resetar senha"), 2, "acima")
    page.screenshot(
        path=str(saida / "usuarios-resetar-senha.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def resetar_senha_motivo(page: Page, base: str, saida: Path) -> None:
    """Entregar o acesso, passos 3 e 4: o motivo obrigatório e a confirmação."""
    entrar(page, base)
    _ativar_pessoa_da_senha()
    _usuarios_filtrados(page, base, EMAIL_DE["Helena Castro"], "Helena Castro")
    _acao_da_linha(page, PESSOA_DA_SENHA[1], "Resetar senha").click()
    page.get_by_role("heading", name="Resetar senha").wait_for()
    page.wait_for_timeout(1200)
    page.locator("textarea").first.fill("Primeiro acesso da coordenadora nova.")
    sem_foco(page)
    balao(page, page.locator("textarea").first, 3)
    # O rodapé do modal tem Cancelar à esquerda do botão de confirmar: o
    # balão à esquerda cairia em cima da palavra errada.
    balao(
        page,
        _modal(page, "Resetar senha").get_by_role("button", name="Resetar senha"),
        4,
        "acima",
    )
    _modal(page, "Resetar senha").screenshot(path=str(saida / "resetar-senha-motivo.png"))
    limpar_baloes(page)


def senha_gerada(page: Page, base: str, saida: Path) -> None:
    """Entregar o acesso, passos 5 e 6: a janela que mostra a senha uma vez.

    A senha do print é gerada pelo app LOCAL para a pessoa de exemplo, e nunca
    a de uma conta de verdade. Quando o print está pronto, a pessoa de exemplo
    é desativada: conta de exemplo com senha conhecida não fica de pé.
    """
    entrar(page, base)
    _ativar_pessoa_da_senha()
    _usuarios_filtrados(page, base, EMAIL_DE["Helena Castro"], "Helena Castro")
    _acao_da_linha(page, PESSOA_DA_SENHA[1], "Resetar senha").click()
    page.get_by_role("heading", name="Resetar senha").wait_for()
    page.locator("textarea").first.fill("Primeiro acesso da coordenadora nova.")
    _modal(page, "Resetar senha").get_by_role("button", name="Resetar senha").click()
    page.get_by_role("heading", name="Senha gerada").wait_for(timeout=30000)
    page.wait_for_timeout(1200)
    sem_foco(page)
    balao(page, page.get_by_role("button", name="Copiar"), 5)
    # O X do alto também se chama "Fechar": o balão vai no botão que tem a
    # palavra escrita, que é o que o passo manda clicar.
    balao(page, page.locator("button").filter(has_text="Fechar"), 6)
    _modal(page, "Senha gerada").screenshot(path=str(saida / "senha-gerada.png"))
    limpar_baloes(page)


def usuarios_perfil_de_acesso(page: Page, base: str, saida: Path) -> None:
    """Mudar o perfil, passos 1, 5 e 6: o lápis, o escudo e a coluna Perfil."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Bruno Tavares"], "Bruno Tavares")
    sem_foco(page)
    balao(page, _acao_da_linha(page, "Bruno Tavares", "Editar"), 1, "acima")
    balao(page, _acao_da_linha(page, "Bruno Tavares", "Tornar super admin"), 5, "acima")
    balao(page, _cabecalho(page, "Perfil"), 6, "acima-inicio")
    page.screenshot(
        path=str(saida / "usuarios-perfil-de-acesso.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def editar_perfil_de_acesso(page: Page, base: str, saida: Path) -> None:
    """Mudar o perfil, passos 2, 3 e 4: as três opções, o motivo e o Salvar."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Bruno Tavares"], "Bruno Tavares")
    _com_janela_alta(page)
    _acao_da_linha(page, "Bruno Tavares", "Editar").click()
    page.get_by_role("heading", name="Editar usuário").wait_for()
    page.wait_for_timeout(1200)
    sem_foco(page)
    balao(page, page.locator("legend", has_text="Perfil de acesso"), 2)
    balao(page, page.locator("textarea").last, 3)
    balao(
        page,
        _modal(page, "Editar usuário").get_by_role("button", name="Salvar"),
        4,
        "acima",
    )
    _modal(page, "Editar usuário").screenshot(
        path=str(saida / "editar-perfil-de-acesso.png")
    )
    limpar_baloes(page)
    _janela_normal(page)


def usuarios_acessos(page: Page, base: str, saida: Path) -> None:
    """Dar acesso aos POPs e à Ouvidoria, passo 1: o lápis da pessoa."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Bruno Tavares"], "Bruno Tavares")
    sem_foco(page)
    balao(page, _acao_da_linha(page, "Bruno Tavares", "Editar"), 1, "acima")
    page.screenshot(
        path=str(saida / "usuarios-acessos.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def editar_acessos(page: Page, base: str, saida: Path) -> None:
    """Dar acesso aos POPs e à Ouvidoria, passos 2, 3 e 4: os dois blocos.

    Os dois blocos só existem ao EDITAR, e é isso que o print tem que mostrar.
    """
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Bruno Tavares"], "Bruno Tavares")
    _com_janela_alta(page)
    _acao_da_linha(page, "Bruno Tavares", "Editar").click()
    page.get_by_role("heading", name="Editar usuário").wait_for()
    page.wait_for_timeout(1200)
    sem_foco(page)
    balao(page, _campo_do_bloco(page, "Acesso aos POPs"), 2)
    balao(page, _campo_do_bloco(page, "Acesso à Ouvidoria"), 3)
    balao(page, _modal(page, "Editar usuário").get_by_role("button", name="Salvar"), 4, "acima")
    _modal(page, "Editar usuário").screenshot(path=str(saida / "editar-acessos.png"))
    limpar_baloes(page)
    _janela_normal(page)


def usuarios_externo(page: Page, base: str, saida: Path) -> None:
    """Resolver um externo, passos 1 e 5: o ícone laranja e a chave da senha."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Diego Rocha"], "Diego Rocha")
    sem_foco(page)
    balao(page, _acao_da_linha(page, "Diego Rocha", "Resolver externo"), 1, "acima")
    balao(page, _acao_da_linha(page, "Diego Rocha", "Resetar senha"), 5, "acima")
    page.screenshot(
        path=str(saida / "usuarios-externo.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def resolver_externo(page: Page, base: str, saida: Path) -> None:
    """Resolver um externo, passos 2 e 3: a escolha e o que a mesclagem pede.

    A janela abre já em **Mesclar com interno**, então os dois passos moram na
    mesma tela e dividem um print. O formulário NÃO é enviado: mesclar apaga a
    linha externa, e o roteiro roda todo dia.
    """
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Diego Rocha"], "Diego Rocha")
    _acao_da_linha(page, "Diego Rocha", "Resolver externo").click()
    page.get_by_role("heading", name="Resolver participante externo").wait_for()
    page.wait_for_timeout(1200)
    sem_foco(page)
    balao(page, page.get_by_text("Mesclar com interno", exact=True), 2)
    balao(page, page.get_by_placeholder("Digite nome ou email (min. 2 chars)"), 3)
    _modal(page, "Resolver participante externo").screenshot(
        path=str(saida / "resolver-externo.png")
    )
    limpar_baloes(page)


def promover_a_interno(page: Page, base: str, saida: Path) -> None:
    """Resolver um externo, passo 4: os campos de quem vira gente de casa."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Diego Rocha"], "Diego Rocha")
    _acao_da_linha(page, "Diego Rocha", "Resolver externo").click()
    page.get_by_role("heading", name="Resolver participante externo").wait_for()
    page.get_by_text("Promover a interno", exact=True).click()
    page.wait_for_timeout(1000)
    _campo(page, "Email").fill("diego.rocha@exemplo.local")
    _campo(page, "Cargo").fill("Analista de Qualidade")
    # O campo Cargo sugere enquanto se digita, e a lista aberta tapa o Motivo
    # logo abaixo: clicar fora fecha a sugestão. Escape, não: Escape fecha a
    # janela inteira.
    page.get_by_role("heading", name="Resolver participante externo").click()
    page.wait_for_timeout(600)
    sem_foco(page)
    balao(page, _campo(page, "Email"), 4)
    _modal(page, "Resolver participante externo").screenshot(
        path=str(saida / "promover-a-interno.png")
    )
    limpar_baloes(page)


def usuarios_desligar(page: Page, base: str, saida: Path) -> None:
    """Tirar o acesso, passos 1, 4 e 6: o lápis, a coluna Ativo e o filtro."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Sofia Lemos"], "Sofia Lemos")
    sem_foco(page)
    balao(page, _acao_da_linha(page, "Sofia Lemos", "Editar"), 1, "acima")
    balao(page, _cabecalho(page, "Ativo"), 4, "acima-inicio")
    balao(page, page.get_by_text("Ativo: todos", exact=True), 6)
    page.screenshot(
        path=str(saida / "usuarios-desligar.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def editar_desligar(page: Page, base: str, saida: Path) -> None:
    """Tirar o acesso, passos 2, 3 e 5: Ativo, o motivo e os dois acessos."""
    entrar(page, base)
    _usuarios_filtrados(page, base, EMAIL_DE["Sofia Lemos"], "Sofia Lemos")
    _com_janela_alta(page)
    _acao_da_linha(page, "Sofia Lemos", "Editar").click()
    page.get_by_role("heading", name="Editar usuário").wait_for()
    page.wait_for_timeout(1200)
    sem_foco(page)
    balao(page, _campo_do_bloco(page, "Acesso aos POPs"), 5)
    # "É externo" fica logo à esquerda de "Ativo": ali o balão marcaria a
    # caixa errada.
    balao(page, page.locator("xpath=//label[normalize-space()='Ativo']"), 2, "acima")
    balao(page, page.locator("textarea").last, 3)
    _modal(page, "Editar usuário").screenshot(path=str(saida / "editar-desligar.png"))
    limpar_baloes(page)
    _janela_normal(page)


# --------------------------------------------------------------------------
# Taxonomia: Setores, Cargos e Tipos de Reunião
# --------------------------------------------------------------------------
# As três telas são a mesma (`components/admin/TaxonomyPage`), com o nome do
# item trocado, e as três páginas do manual descrevem os mesmos seis passos.
# Por isso os prints saem de duas funções parametrizadas, e não de seis
# funções iguais: o dia em que a tela mudar, muda num lugar.


def _lista_da_taxonomia(
    page: Page,
    base: str,
    saida: Path,
    rota: str,
    item: str,
    arquivo: str,
    numeros: dict,
) -> None:
    """A lista de uma taxonomia com os balões dos passos da página dela.

    Os números vêm de fora porque as três páginas contam os passos de um jeito
    diferente: em Setores e Cargos o lápis é o passo 4, e em Tipos de Reunião
    é o 3. Balão com o número do passo de outra página é instrução errada.
    """
    entrar(page, base)
    page.goto(f"{base}{rota}", wait_until="networkidle")
    page.get_by_role("heading", level=1).wait_for()
    page.wait_for_timeout(1500)
    sem_foco(page)
    novo = f"Novo {item}"
    primeira = page.get_by_role("row").nth(1)
    balao(page, _link_da_barra(page, rota), numeros["barra"])
    balao(page, page.get_by_role("button", name=novo), numeros["novo"])
    balao(page, primeira.locator("button[title='Editar']"), numeros["editar"], "acima")
    balao(page, primeira.locator("button[title='Arquivar']"), numeros["arquivar"], "acima")
    balao(page, page.get_by_text("Apenas ativos", exact=True), numeros["filtro"])
    if "status" in numeros:
        balao(page, _cabecalho(page, "Status"), numeros["status"], "acima-inicio")
    page.screenshot(
        path=str(saida / arquivo), clip={"x": 0, "y": 0, "width": 1440, "height": 620}
    )
    limpar_baloes(page)


def _novo_da_taxonomia(
    page: Page,
    base: str,
    saida: Path,
    rota: str,
    item: str,
    arquivo: str,
    exemplo: str,
    numero: int = 3,
) -> None:
    entrar(page, base)
    page.goto(f"{base}{rota}", wait_until="networkidle")
    novo = f"Novo {item}"
    page.get_by_role("button", name=novo).click()
    page.get_by_role("heading", name=novo).wait_for()
    page.wait_for_timeout(1200)
    # Preenchido e não enviado: a lista é compartilhada com o resto do
    # trabalho, e o print da tela preenchida diz o mesmo sem criar nada.
    page.locator("input[type='text']").last.fill(exemplo)
    sem_foco(page)
    balao(page, page.locator("input[type='text']").last, numero)
    _modal(page, novo).screenshot(path=str(saida / arquivo))
    limpar_baloes(page)


def setores(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um setor, passos 1, 2, 4, 5 e 6, todos na mesma lista."""
    _lista_da_taxonomia(
        page,
        base,
        saida,
        "/admin/setores",
        "setor",
        "setores.png",
        {"barra": 1, "novo": 2, "editar": 4, "arquivar": 5, "filtro": 6},
    )


def novo_setor(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um setor, passo 3: o Nome e o Criar."""
    _novo_da_taxonomia(
        page, base, saida, "/admin/setores", "setor", "novo-setor.png", "Farmácia Central"
    )


def cargos(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um cargo, passos 1, 2, 4, 5 e 6, todos na mesma lista."""
    _lista_da_taxonomia(
        page,
        base,
        saida,
        "/admin/cargos",
        "cargo",
        "cargos.png",
        {"barra": 1, "novo": 2, "editar": 4, "arquivar": 5, "filtro": 6},
    )


def novo_cargo(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um cargo, passo 3: o Nome e o Criar."""
    _novo_da_taxonomia(
        page, base, saida, "/admin/cargos", "cargo", "novo-cargo.png", "Técnico de Farmácia"
    )


def tipos_de_reuniao(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um tipo de reunião: os seis itens que a tela atende."""
    _lista_da_taxonomia(
        page,
        base,
        saida,
        "/admin/tipos-reuniao",
        "tipo de reunião",
        "tipos-de-reuniao.png",
        {"barra": 1, "novo": 2, "editar": 3, "arquivar": 4, "filtro": 5, "status": 6},
    )


def novo_tipo_de_reuniao(page: Page, base: str, saida: Path) -> None:
    """Cadastrar um tipo de reunião, item 2: o Nome, campo único."""
    _novo_da_taxonomia(
        page,
        base,
        saida,
        "/admin/tipos-reuniao",
        "tipo de reunião",
        "novo-tipo-de-reuniao.png",
        "Comissão de Farmácia",
        numero=2,
    )


# --------------------------------------------------------------------------
# Atendimento: Dados do Atendimento e o Espelho
# --------------------------------------------------------------------------


def dados_do_atendimento(page: Page, base: str, saida: Path) -> None:
    """Manter os Dados do Atendimento, passos 1, 2, 4 e 6."""
    entrar(page, base)
    page.goto(f"{base}/admin/dados-atendimento", wait_until="networkidle")
    page.get_by_role("button", name="Consultas particulares").wait_for()
    page.wait_for_timeout(2000)
    sem_foco(page)
    primeira = page.get_by_role("row").nth(1)
    balao(page, _link_da_barra(page, "/admin/dados-atendimento"), 1)
    balao(page, page.get_by_role("button", name="Consultas particulares"), 2)
    balao(page, page.get_by_role("button", name="Nova consulta particular"), 3)
    balao(page, primeira.locator("button[title='Editar']"), 4, "acima")
    balao(page, primeira.locator("button[title='Desativar']"), 6, "acima")
    page.screenshot(
        path=str(saida / "dados-do-atendimento.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 700},
    )
    limpar_baloes(page)


def nova_consulta_particular(page: Page, base: str, saida: Path) -> None:
    """Manter os Dados do Atendimento, passos 3 e 5: os campos e a Ana."""
    entrar(page, base)
    page.goto(f"{base}/admin/dados-atendimento", wait_until="networkidle")
    _com_janela_alta(page)
    page.get_by_role("button", name="Nova consulta particular").click()
    page.get_by_role("heading", name="Nova consulta particular").wait_for()
    page.wait_for_timeout(1200)
    sem_foco(page)
    modal = _modal(page, "Nova consulta particular")
    balao(page, modal.locator("input").first, 3)
    # O balão vai no campo, e não no rótulo acima dele: encostado na borda
    # esquerda, ele cai dentro do campo vazio e não em cima da palavra.
    balao(
        page,
        modal.get_by_text("Observações para a Ana", exact=True).locator(
            "xpath=following::textarea[1]"
        ),
        5,
    )
    modal.screenshot(path=str(saida / "nova-consulta-particular.png"))
    limpar_baloes(page)
    _janela_normal(page)


def dados_do_atendimento_espelho(page: Page, base: str, saida: Path) -> None:
    """Consultar o Espelho, passo 1: o botão que abre a janela da agenda."""
    entrar(page, base)
    page.goto(f"{base}/admin/dados-atendimento", wait_until="networkidle")
    page.get_by_role("button", name="Espelho da Global Health").wait_for()
    page.wait_for_timeout(2000)
    sem_foco(page)
    balao(page, page.get_by_role("button", name="Espelho da Global Health"), 1)
    page.screenshot(
        path=str(saida / "dados-do-atendimento-espelho.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )
    limpar_baloes(page)


def espelho_da_global_health(page: Page, base: str, saida: Path) -> None:
    """Consultar o Espelho, passos 2 e 3: atualizar e abrir a especialidade.

    O corte para antes de **Profissionais disponíveis** de propósito. Dali
    para baixo a tela lista, com nome e sobrenome, os médicos que a agenda
    online publica, e a lista **Médico** do fim repete os mesmos nomes: é
    gente de verdade, e o repositório do manual é público. Os passos 5 e 6
    ficam sem print, e o PR diz por quê.
    """
    entrar(page, base)
    page.goto(f"{base}/admin/dados-atendimento", wait_until="networkidle")
    page.get_by_role("button", name="Espelho da Global Health").click()
    especialidade = page.get_by_text("Consulta Cardiologica").first
    especialidade.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    especialidade.click()
    # O convênio chega depois da especialidade, numa segunda consulta à agenda:
    # sem esta espera o bloco sai escrito "Carregando…".
    page.get_by_role("heading", name="Convênios aceitos").wait_for(timeout=30000)
    page.wait_for_timeout(6000)
    sem_foco(page)
    balao(page, page.get_by_role("button", name="Atualizar").first, 2)
    balao(page, especialidade, 3)
    fim = page.evaluate(
        "() => { const h = [...document.querySelectorAll('h4')]"
        ".find((e) => e.textContent.includes('Profissionais')); "
        "return h ? h.getBoundingClientRect().top + window.scrollY - 16 : 900; }"
    )
    page.screenshot(
        path=str(saida / "espelho-da-global-health.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": round(fim)},
    )
    limpar_baloes(page)


class AgendaOnlineForaDoAr(Exception):
    """A agenda externa não respondeu, e o print sairia com a tela de espera
    ou com o aviso vermelho da consulta que falhou."""


# O que o bloco diz enquanto a lista não chega, e o que ele diz quando a
# consulta à agenda estoura o tempo. Nenhum dos dois é a tela que a página
# do manual explica.
SEM_LISTA_NO_ESPELHO = ("Carregando", "falhou", "falhar")


def _esperar_a_lista(bloco, segundos: int = 40) -> None:
    """Espera a lista chegar de verdade antes de alguém capturar.

    O Espelho é a única tela do manual que depende de um serviço de fora (a
    agenda online). Quando ela demora, a espera por tempo fixo termina com o
    bloco ainda vazio e o print publicado vira uma tela de espera, ou o aviso
    vermelho da consulta que falhou: o leitor conclui que a plataforma trava
    ali. Melhor não gravar nada e manter a imagem da rodada anterior, que
    mostra a tela de verdade.
    """
    for _ in range(segundos):
        texto = bloco.inner_text()
        if not any(marca in texto for marca in SEM_LISTA_NO_ESPELHO):
            return
        bloco.page.wait_for_timeout(1000)
    raise AgendaOnlineForaDoAr(
        "a agenda online não devolveu a lista de convênios. O print ficou "
        "como estava: rode este roteiro de novo quando ela responder."
    )


def _abrir_a_cadeia_do_espelho(page: Page, base: str):
    """Deixa o Espelho aberto na especialidade de exemplo e devolve a linha dela."""
    entrar(page, base)
    page.goto(f"{base}/admin/dados-atendimento", wait_until="networkidle")
    page.get_by_role("button", name="Espelho da Global Health").click()
    especialidade = page.get_by_text("Consulta Cardiologica").first
    especialidade.wait_for(timeout=30000)
    page.wait_for_timeout(1500)
    especialidade.click()
    # O convênio chega depois da especialidade, numa segunda consulta à agenda:
    # sem esta espera o bloco sai escrito "Carregando…".
    page.get_by_role("heading", name="Convênios aceitos").wait_for(timeout=30000)
    page.wait_for_timeout(8000)
    return especialidade


def espelho_convenios(page: Page, base: str, saida: Path) -> None:
    """Consultar o Espelho, passo 4: a lista de convênios da especialidade.

    O corte é da COLUNA da esquerda, e não da tela inteira. **Convênios
    aceitos** e **Profissionais disponíveis** são duas colunas lado a lado, e
    a da direita lista, com nome e sobrenome, os médicos que a agenda online
    publica: gente de verdade num repositório público.
    """
    _abrir_a_cadeia_do_espelho(page, base)
    sem_foco(page)
    coluna = page.get_by_role("heading", name="Convênios aceitos").locator(
        "xpath=ancestor::div[2]"
    )
    _esperar_a_lista(coluna)
    caixa = coluna.bounding_box()
    balao(page, page.get_by_role("heading", name="Convênios aceitos"), 4)
    page.screenshot(
        path=str(saida / "espelho-convenios.png"),
        clip={
            "x": max(0, caixa["x"] - 40),
            "y": max(0, caixa["y"] - 16),
            "width": caixa["width"] + 56,
            "height": caixa["height"] + 32,
        },
    )
    limpar_baloes(page)


PRINTS = {
    # Visão geral do módulo (sem balão)
    "painel-de-administracao": painel_de_administracao,
    # Cadastrar uma pessoa
    "usuarios-cadastrar": usuarios_cadastrar,
    "novo-usuario": novo_usuario,
    # Entregar o acesso a uma pessoa
    "usuarios-resetar-senha": usuarios_resetar_senha,
    "resetar-senha-motivo": resetar_senha_motivo,
    "senha-gerada": senha_gerada,
    # Mudar o perfil de acesso
    "usuarios-perfil-de-acesso": usuarios_perfil_de_acesso,
    "editar-perfil-de-acesso": editar_perfil_de_acesso,
    # Dar acesso aos POPs e à Ouvidoria
    "usuarios-acessos": usuarios_acessos,
    "editar-acessos": editar_acessos,
    # Resolver um participante externo
    "usuarios-externo": usuarios_externo,
    "resolver-externo": resolver_externo,
    "promover-a-interno": promover_a_interno,
    # Tirar o acesso de quem saiu
    "usuarios-desligar": usuarios_desligar,
    "editar-desligar": editar_desligar,
    # Taxonomia
    "setores": setores,
    "novo-setor": novo_setor,
    "cargos": cargos,
    "novo-cargo": novo_cargo,
    "tipos-de-reuniao": tipos_de_reuniao,
    "novo-tipo-de-reuniao": novo_tipo_de_reuniao,
    # Atendimento
    "dados-do-atendimento": dados_do_atendimento,
    "nova-consulta-particular": nova_consulta_particular,
    "dados-do-atendimento-espelho": dados_do_atendimento_espelho,
    "espelho-da-global-health": espelho_da_global_health,
    "espelho-convenios": espelho_convenios,
}


# --------------------------------------------------------------------------
# Dados de exemplo (`--semear`)
# --------------------------------------------------------------------------

# Toda pessoa daqui é inventada, e o domínio `exemplo.local` não existe. É o
# que permite o print da tela de Usuários existir num repositório público.
# (id, nome, email, cargo, setor, role, perfil de acesso, super admin, externo)
PESSOAS = [
    ("P910", "Camila Prado", EMAIL, "Gerente Administrativo", "Administração", "gerente", "super_admin", True, False),
    ("P911", "Bruno Tavares", "bruno.tavares@exemplo.local", "Coordenador de Enfermagem", "Centro de Terapia Intensiva", "coordenador", "regular", False, False),
    ("P912", "Sofia Lemos", "sofia.lemos@exemplo.local", None, "Administração", None, "secretaria", False, False),
    ("P913", "Diego Rocha", "diego.rocha@exemplo.local", None, None, None, "regular", False, True),
    PESSOA_DA_SENHA,
]

CARGOS = ["Gerente Administrativo", "Coordenador de Enfermagem", "Analista de Qualidade"]


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
    """As quatro pessoas de exemplo e os cargos que o formulário sugere."""
    url, chave = _credenciais_locais()

    for pid, nome, email, cargo, setor, role, perfil, super_admin, externo in PESSOAS:
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
                    "cargo": cargo,
                    "setor": setor,
                    "role": role,
                    "ativo": True,
                    "access_profile": perfil,
                    "is_super_admin": super_admin,
                    "is_externo": externo,
                    "auth_user_id": _login_de_exemplo(url, chave, email),
                }
            ],
            prefer="resolution=merge-duplicates",
        )

    for nome in CARGOS:
        if not _rest(url, chave, f"cargos?nome=eq.{urllib.parse.quote(nome)}&select=id"):
            _rest(url, chave, "cargos", "POST", [{"nome": nome}])

    print("dados de exemplo do módulo Admin prontos.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/admin")
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
        try:
            pulados = []
            for nome in escolhidos:
                try:
                    PRINTS[nome](page, args.base.rstrip("/"), saida)
                except AgendaOnlineForaDoAr as fora:
                    # Serviço de fora não é tela deste repositório: o resto do
                    # módulo continua, e quem rodou fica sabendo o que falta.
                    pulados.append(f"{nome}: {fora}")
                    continue
                print(f"print: {saida / (nome + '.png')}")
            for aviso in pulados:
                print(f"PULADO {aviso}", file=sys.stderr)
        finally:
            # A conta de exemplo da senha não fica de pé depois da captura,
            # nem quando a captura falha no meio.
            _desativar_pessoa_da_senha()
            navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
