#!/usr/bin/env python3
"""Roteiro de prints do módulo Tecnologia do Manual (ADR 0057, decisão 3).

Desde a ADR 0077 (PRD #1380) a aba é uma tela só: o chat do Assistente de
Tecnologia, com a lista dos pedidos ao lado. O print segue a regra dos outros
roteiros desta pasta: tela real do app em localhost, capturada por código
versionado, nunca recorte à mão.

**A conversa vem do roteiro, não do banco.** O chat chama a IA a cada fala, e
cada pedido que chega ao fim cria um card no GitHub. Por isso a tela abre com
a lista e a conversa trocadas no navegador (`_trocar_o_chat`): as respostas do
servidor para a lista e para a conversa aberta são as de `LISTA_*` e
`CONVERSAS`, e nenhuma fala sai da tela. Nada grava no banco, e nenhum pedido
de verdade aparece no print. O banco local só guarda o login da pessoa de
exemplo (`--semear`), inventada (`@exemplo.local`), na faixa P950 dos
roteiros.

Receita:

1. Supabase local no ar.
2. Stack com o código da tela: `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. `python3 docs/manual/prints/tecnologia.py --semear` (idempotente, só no
   banco local).
4. `python3 docs/manual/prints/tecnologia.py`.

As telas do Vídeo de visão geral (`video-NN-<passo>`) saem em 1920x1080, sem
balão, com as caixas dos elementos citados em `video-alvos.json`:
`python3 docs/manual/prints/tecnologia.py --video`.

Uso: python3 docs/manual/prints/tecnologia.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/tecnologia] [--print <nome>] [--semear]
     [--video]
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

if TYPE_CHECKING:
    from playwright.sync_api import Page

COMPUTADOR = {"width": 1440, "height": 900}
VIDEO = {"width": 1920, "height": 1080}
ESCALA = 2

EMAIL = "marina.duarte@exemplo.local"
SENHA = "ManualTecnologia2026!"

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"

# (id, nome, email). Super admin: é quem entra na aba.
PESSOAS = [("P950", "Marina Duarte", EMAIL)]


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-a000-000000095{n:03d}"


# --------------------------------------------------------------------------
# Os pedidos de exemplo
# --------------------------------------------------------------------------
#
# Dois casos andam pelo módulo: o bug do botão Salvar do POP e a melhoria do
# nome do setor no cartaz do QR da Ouvidoria. Os outros pedidos só enchem a
# lista com as Etapas que a pessoa vai ver.

BUG = _uuid(21)
MELHORIA = _uuid(22)
INSTAGRAM = _uuid(23)
AVISO_DA_OUVIDORIA = _uuid(24)
LEMBRETE = _uuid(25)

TITULO_DO_BUG = "O botão Salvar do POP não grava a versão nova"
TITULO_DA_MELHORIA = "Nome do setor no cartaz do QR da Ouvidoria"

# A mesma pergunta que o backend guarda como primeira fala (ABERTURA da tela).
ABERTURA = "Isso é um bug, algo que não funciona como deveria, ou uma melhoria?"


def _ia(texto: str, opcoes: list[str] | None = None, recomendada: str | None = None) -> dict:
    return {
        "autor": "ia",
        "texto": texto,
        "fonte": None,
        "opcoes": opcoes or [],
        "recomendada": recomendada,
        "nao_bateu": False,
    }


def _diretor(texto: str) -> dict:
    return {"autor": "diretor", "texto": texto, "fonte": None, "opcoes": [], "recomendada": None, "nao_bateu": False}


FALAS_DO_BUG = [
    _ia(ABERTURA, ["Bug", "Melhoria"]),
    _diretor("Bug"),
    _ia("Certo, vamos registrar o problema. Onde aconteceu? Em que tela você estava?"),
    _diretor("Na tela do POP de Higienização das mãos, quando cliquei em Salvar depois de editar o texto."),
    _ia("E o que aconteceu? O que você esperava que acontecesse?"),
    _diretor("O botão não fez nada e a versão nova sumiu quando recarreguei. Esperava ver a versão 3 salva."),
    _ia("Entendi. Se tiver um print da tela, mande pelo botão de imagem, ao lado da caixa de mensagem."),
]

RESUMO_DO_BUG = {
    "titulo": TITULO_DO_BUG,
    "onde": "Na tela do POP de Higienização das mãos, no botão Salvar, depois de editar o texto.",
    "o_que_aconteceu": "O botão não fez nada, e a versão nova sumiu ao recarregar a página.",
    "o_que_esperava": "Que a versão 3 fosse salva e aparecesse na lista de versões.",
    "como_repetir": "Abrir um POP, editar o texto e clicar em Salvar.",
    "criterios": [
        "Ao clicar em Salvar, a versão nova aparece na lista de versões do POP.",
        "Se a gravação falhar, a tela avisa, e o texto editado continua na tela.",
    ],
}

FALAS_DA_MELHORIA = [
    _ia(ABERTURA, ["Bug", "Melhoria"]),
    _diretor("Melhoria"),
    _ia("Boa. Me conta o que você quer melhorar, do jeito que vier."),
    _diretor("Quero que o cartaz com o QR da Ouvidoria mostre o nome do setor."),
    _ia(
        "O cartaz fica na porta do setor, e o QR abre a página de manifestação. "
        "O nome do setor entra só no cartaz impresso, ou também na página que abre pelo QR?",
        ["Nos dois: quem lê o QR vê de que setor está falando", "Só no cartaz impresso"],
        "A",
    ),
    _diretor("Nos dois: quem lê o QR vê de que setor está falando"),
    _ia(
        "Alguns setores dividem a mesma porta, como a Recepção e a Internação. "
        "Nesse caso, cada setor tem o seu cartaz, ou um cartaz mostra os dois nomes?",
        ["Cada setor com o seu cartaz e o seu QR", "Um cartaz com os dois nomes"],
        "A",
    ),
]

RESUMO_DA_MELHORIA = {
    "decisoes": [
        {
            "pergunta": "O nome do setor entra só no cartaz impresso, ou também na página que abre pelo QR?",
            "escolha": "Nos dois: quem lê o QR vê de que setor está falando",
            "porque": "Quem manifesta precisa saber de que setor está falando antes de escrever.",
        },
        {
            "pergunta": "Quando dois setores dividem a mesma porta, cada um tem o seu cartaz?",
            "escolha": "Cada setor com o seu cartaz e o seu QR",
            "porque": "Assim a manifestação já chega ao setor certo.",
        },
    ],
    "em_aberto": ["Onde fica cada cartaz quando a Recepção e a Internação dividem a porta."],
}

O_QUE_MUDA_DA_MELHORIA = (
    "O cartaz com o QR e a página de manifestação da Ouvidoria passam a mostrar o nome do setor. "
    "Cada setor tem o seu cartaz e o seu QR, mesmo quando divide a porta com outro."
)


def _conversa(demanda: str, falas: list[dict], estado: str = "em_andamento", **resto) -> dict:
    corpo = {
        "demanda_id": demanda,
        "estado": estado,
        "mensagens": falas,
        "resumo": None,
        "resumo_da_melhoria": None,
        "anexos": 0,
        "planejamento": False,
        "aviso_dos_anexos": None,
    }
    corpo.update(resto)
    return corpo


def _pedido(demanda: str, titulo: str, etapa: str = "registrada", **resto) -> dict:
    corpo = {"id": demanda, "titulo": titulo, "etapa": etapa, "tem_vinculo": etapa != "registrada"}
    corpo.update(resto)
    return corpo


# A lista com as Etapas que a pessoa vai ver, da mais recente para a mais antiga.
LISTA_DO_DIA_A_DIA = [
    _pedido(MELHORIA, TITULO_DA_MELHORIA, "em_analise", o_que_muda=O_QUE_MUDA_DA_MELHORIA),
    _pedido(
        BUG,
        TITULO_DO_BUG,
        "em_desenvolvimento",
        o_que_muda="O botão Salvar do POP volta a gravar a versão e avisa quando a gravação falha.",
    ),
    _pedido(LEMBRETE, "Lembrete na véspera da reunião"),
    _pedido(
        INSTAGRAM, "Números do Instagram na Central de Comando", "planejada", partes_entregues=0, partes_total=2
    ),
    _pedido(
        AVISO_DA_OUVIDORIA,
        "Aviso quando a Ouvidoria encerrar um caso",
        "em_producao",
        versao="v0.167.0",
        o_que_muda="Quando a Ouvidoria encerra um caso, quem manifestou recebe um aviso com o resumo da resposta.",
    ),
]

# A lista de quem ainda está no meio das duas conversas.
LISTA_NO_MEIO = [
    _pedido(MELHORIA, TITULO_DA_MELHORIA),
    _pedido(BUG, TITULO_DO_BUG),
    *LISTA_DO_DIA_A_DIA[2:],
]

CONVERSAS = {
    "bug": _conversa(BUG, FALAS_DO_BUG),
    "resumo_do_bug": _conversa(BUG, FALAS_DO_BUG, "resumido", resumo=RESUMO_DO_BUG, anexos=1),
    "bug_enviado": _conversa(BUG, FALAS_DO_BUG, "enviado", resumo=RESUMO_DO_BUG, anexos=1),
    "melhoria": _conversa(MELHORIA, FALAS_DA_MELHORIA, planejamento=True),
    "resumo_da_melhoria": _conversa(
        MELHORIA, FALAS_DA_MELHORIA, "resumido", planejamento=True, resumo_da_melhoria=RESUMO_DA_MELHORIA
    ),
    "melhoria_enviada": _conversa(
        MELHORIA, FALAS_DA_MELHORIA, "enviado", planejamento=True, resumo_da_melhoria=RESUMO_DA_MELHORIA
    ),
}


# --------------------------------------------------------------------------
# Banco local: só o login da pessoa de exemplo
# --------------------------------------------------------------------------


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
    dados = None if corpo is None else json.dumps(corpo).encode()
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    if prefer:
        cabecalhos["Prefer"] = prefer
    req = urllib.request.Request(f"{url}/rest/v1/{caminho}", data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}")


def _login_de_exemplo(url: str, chave: str, email: str) -> str:
    """Cria (ou reaproveita) o login da pessoa de exemplo no Supabase local."""
    corpo = json.dumps({"email": email, "password": SENHA, "email_confirm": True}).encode()
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{url}/auth/v1/admin/users", data=corpo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            return json.load(resposta)["id"]
    except urllib.error.HTTPError as e:
        texto = e.read().decode()
        if e.code not in (400, 422) or "already" not in texto:
            raise SystemExit(f"login {email}: {e.code} {texto[:300]}")
    busca = urllib.request.Request(
        f"{url}/auth/v1/admin/users?page=1&per_page=500",
        headers={"apikey": chave, "Authorization": f"Bearer {chave}"},
    )
    with urllib.request.urlopen(busca, timeout=20) as resposta:
        for usuario in json.load(resposta)["users"]:
            if usuario["email"] == email:
                return usuario["id"]
    raise SystemExit(f"login {email} não encontrado depois de criado.")


def semear() -> None:
    url, chave = _credenciais_locais()
    for pid, nome, email in PESSOAS:
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
                    "ativo": True,
                    "access_profile": "super_admin",
                    "is_super_admin": True,
                    "is_externo": False,
                    "auth_user_id": _login_de_exemplo(url, chave, email),
                }
            ],
            prefer="resolution=merge-duplicates",
        )
    print("login de exemplo da aba Tecnologia pronto.")


# --------------------------------------------------------------------------
# A tela
# --------------------------------------------------------------------------

# O navy do app (`--color-primary` do `globals.css`): o balão é marcação do
# manual, mas não é corpo estranho na tela.
NAVY = "#2B2E7E"
DIAMETRO = 28
FOLGA = 6

RAIZ_DO_CHAT = "/api/admin/tecnologia/chat"


def sem_foco(page) -> None:
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(200)


def entrar(page: Page, base: str, email: str = EMAIL) -> None:
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(email)
    page.get_by_placeholder("••••••••").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)


def _do_chat(url: str) -> bool:
    return urllib.parse.urlparse(url).path.rstrip("/").startswith(RAIZ_DO_CHAT)


def _trocar_o_chat(page: Page, lista: list[dict], conversa: dict | None) -> None:
    """A lista e a conversa aberta chegam do roteiro (só no navegador).

    Qualquer outro pedido ao chat (uma fala, o Criar o card) é recusado aqui:
    o print nunca chama a IA nem cria card."""

    def tratar(rota):
        caminho = urllib.parse.urlparse(rota.request.url).path.rstrip("/")
        if rota.request.method != "GET":
            rota.fulfill(status=409, json={"detail": "o roteiro de prints não manda falas"})
        elif caminho == RAIZ_DO_CHAT:
            rota.fulfill(json=lista)
        elif conversa is not None and caminho == f"{RAIZ_DO_CHAT}/{conversa['demanda_id']}":
            rota.fulfill(json=conversa)
        else:
            rota.fulfill(status=404, json={"detail": "Demanda nao encontrada"})

    page.route(_do_chat, tratar)


def abrir_o_chat(page: Page, base: str, lista: list[dict], conversa: dict | None = None, titulo: str | None = None):
    """Entra, abre a aba e, com `titulo`, clica no pedido da lista."""
    _trocar_o_chat(page, lista, conversa)
    entrar(page, base)
    page.goto(f"{base}/admin/tecnologia", wait_until="networkidle")
    na_tela = page.get_by_role("navigation", name="Suas conversas")
    na_tela.get_by_role("button").first.wait_for(timeout=20000)
    if titulo:
        na_tela.get_by_role("button").filter(has_text=titulo).first.click()
        page.wait_for_load_state("networkidle")
    page.wait_for_timeout(600)
    # A conversa rola até a última fala e leva a página junto: o alto volta.
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(300)
    return na_tela


def balao(page: Page, alvo, numero: int) -> None:
    """O balão do passo `numero`, no canto superior esquerdo do `alvo` (um Locator).

    Um `div` injetado por cima de tudo, sem receber clique, que some no
    recarregamento: nada disto fica no app."""
    caixa = alvo.bounding_box()
    if caixa is None:
        raise SystemExit(f"balão {numero}: o elemento não está na tela. Confira o seletor.")
    page.evaluate(
        """([x, y, numero, diametro, cor]) => {
            const b = document.createElement('div');
            b.textContent = String(numero);
            Object.assign(b.style, {
                position: 'absolute', left: (x + window.scrollX) + 'px', top: (y + window.scrollY) + 'px',
                width: diametro + 'px', height: diametro + 'px', borderRadius: '9999px', background: cor,
                color: '#ffffff', font: '700 15px/' + diametro + 'px "HP Simplified", system-ui, sans-serif',
                textAlign: 'center', boxShadow: '0 2px 6px rgba(0,0,0,0.35)', pointerEvents: 'none',
                zIndex: '2147483647',
            });
            document.body.appendChild(b);
        }""",
        [max(2, caixa["x"] - DIAMETRO + FOLGA), max(2, caixa["y"] - DIAMETRO + FOLGA), numero, DIAMETRO, NAVY],
    )


def _sem_versao(page: Page) -> None:
    """O build local mostra a versão do package.json, não a de produção: o
    rodapé sai do print para não ensinar um número errado."""
    page.evaluate(
        "document.querySelectorAll(\"span[aria-label^='Versão']\").forEach((e) => { e.style.visibility = 'hidden'; })"
    )


def _capturar(page: Page, saida: Path, nome: str) -> None:
    sem_foco(page)
    _sem_versao(page)
    page.screenshot(path=str(saida / f"{nome}.png"))


def _aberta(page: Page):
    return page.get_by_role("region", name="Conversa aberta")


def _na_lista(page: Page, titulo: str):
    return page.get_by_role("navigation", name="Suas conversas").get_by_role("button").filter(has_text=titulo)


# --------------------------------------------------------------------------
# Os prints das Páginas de tarefa
# --------------------------------------------------------------------------


def bug_escolher(page: Page, base: str, saida: Path) -> None:
    """A conversa nova: a pergunta da IA e o botão Bug."""
    abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA)
    balao(page, page.get_by_role("button", name="Nova conversa"), 1)
    balao(page, page.get_by_role("group", name="Opções").get_by_role("button", name="Bug"), 1)
    _capturar(page, saida, "bug-escolher")


def melhoria_escolher(page: Page, base: str, saida: Path) -> None:
    """A conversa nova: a pergunta da IA e o botão Melhoria."""
    abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA)
    balao(page, page.get_by_role("button", name="Nova conversa"), 1)
    balao(page, page.get_by_role("group", name="Opções").get_by_role("button", name="Melhoria"), 1)
    _capturar(page, saida, "melhoria-escolher")


def bug_conversa(page: Page, base: str, saida: Path) -> None:
    """O bug no meio: as perguntas, a caixa de mensagem e o botão do print."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["bug"], TITULO_DO_BUG)
    page.get_by_text("Se tiver um print da tela").wait_for(timeout=20000)
    balao(page, page.get_by_label("Sua mensagem"), 2)
    balao(page, page.get_by_role("button", name="Mandar um print"), 3)
    _capturar(page, saida, "bug-conversa")


def resumo_do_bug(page: Page, base: str, saida: Path) -> None:
    """O Resumo do bug, com Não bateu e Criar o card."""
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1180})
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["resumo_do_bug"], TITULO_DO_BUG)
    criar = page.get_by_role("button", name="Criar o card")
    criar.wait_for(timeout=20000)
    balao(page, page.get_by_role("region", name="Resumo do bug").get_by_role("heading").first, 4)
    balao(page, criar, 5)
    _capturar(page, saida, "resumo-do-bug")


def melhoria_pergunta(page: Page, base: str, saida: Path) -> None:
    """A pergunta da melhoria: as duas opções com a Recomendada e o Fechar e resumir."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["melhoria"], TITULO_DA_MELHORIA)
    opcoes = page.get_by_role("group", name="Opções")
    opcoes.wait_for(timeout=20000)
    balao(page, opcoes.get_by_role("button").first, 2)
    balao(page, page.get_by_role("button", name="Fechar e resumir"), 3)
    _capturar(page, saida, "melhoria-pergunta")


def resumo_da_melhoria(page: Page, base: str, saida: Path) -> None:
    """O Resumo da melhoria: as Decisões, o Ficou em aberto e o Criar o card."""
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1200})
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["resumo_da_melhoria"], TITULO_DA_MELHORIA)
    criar = page.get_by_role("button", name="Criar o card")
    criar.wait_for(timeout=20000)
    balao(page, page.get_by_role("heading", name="Decisões"), 4)
    balao(page, criar, 5)
    _capturar(page, saida, "resumo-da-melhoria")


def lista_de_pedidos(page: Page, base: str, saida: Path) -> None:
    """A lista com a Etapa de cada pedido, e o pedido Registrada que retoma a conversa."""
    lista = abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA)
    balao(page, lista, 1)
    balao(page, _na_lista(page, "Lembrete na véspera"), 2)
    _capturar(page, saida, "lista-de-pedidos")


def acompanhamento(page: Page, base: str, saida: Path) -> None:
    """O pedido que já foi para a Vitta: a Etapa e O que muda."""
    abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA, CONVERSAS["melhoria_enviada"], TITULO_DA_MELHORIA)
    o_que_muda = page.get_by_role("region", name="O que muda")
    o_que_muda.wait_for(timeout=20000)
    balao(page, _na_lista(page, TITULO_DA_MELHORIA), 3)
    balao(page, o_que_muda, 3)
    _capturar(page, saida, "acompanhamento")


# --------------------------------------------------------------------------
# As telas do Vídeo de visão geral (ADR 0076)
# --------------------------------------------------------------------------
#
# Janela inteira de 1920x1080, sem balão: no vídeo quem aponta é o cursor e o
# destaque. Cada tela grava em `video-alvos.json` a caixa (x, y, largura,
# altura, em pixels da janela) de cada elemento que a fala cita, e a cena do
# Remotion põe o destaque em cima dela sem medir a olho.


def _caixa(nome: str, alvo) -> list[float]:
    caixa = alvo.bounding_box()
    if caixa is None:
        raise SystemExit(f"alvo do vídeo fora da tela: {nome}. Confira o seletor.")
    return [round(caixa[k], 1) for k in ("x", "y", "width", "height")]


def _tela_do_video(page: Page, saida: Path, nome: str, alvos: dict) -> None:
    """Captura a janela e grava as caixas dos alvos ao lado das telas."""
    page.wait_for_load_state("networkidle")
    sem_foco(page)
    # O vídeo não escreve versão: o carimbo mora no meta.json.
    _sem_versao(page)
    page.wait_for_timeout(400)
    caixas = {chave: _caixa(chave, alvo) for chave, alvo in alvos.items()}
    page.screenshot(path=str(saida / f"{nome}.png"))
    arquivo = saida / "video-alvos.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.is_file() else {}
    dados = {k: v for k, v in dados.items() if k in PRINTS}
    dados[nome] = caixas
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def video_01_abertura(page: Page, base: str, saida: Path) -> None:
    """A aba aberta: a lista ao lado, a pergunta bug ou melhoria e a caixa de mensagem."""
    lista = abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA)
    opcoes = page.get_by_role("group", name="Opções")
    _tela_do_video(
        page,
        saida,
        "video-01-abertura",
        {
            "chat": _aberta(page).locator("section").first,
            "lista": lista,
            "nova_conversa": page.get_by_role("button", name="Nova conversa"),
            "pergunta": page.get_by_text(ABERTURA),
            "opcoes": opcoes,
            "bug": opcoes.get_by_role("button", name="Bug"),
            "melhoria": opcoes.get_by_role("button", name="Melhoria"),
            "mensagem": page.get_by_label("Sua mensagem"),
            "microfone": page.get_by_role("button", name="Gravar voz"),
            "print": page.get_by_role("button", name="Mandar um print"),
            "aviso": page.get_by_text("Evite dados de paciente"),
        },
    )


def video_02_bug(page: Page, base: str, saida: Path) -> None:
    """O bug no meio: as perguntas uma por vez e o pedido do print."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["bug"], TITULO_DO_BUG)
    page.get_by_text("Se tiver um print da tela").wait_for(timeout=20000)
    log = _aberta(page).get_by_role("log")
    _tela_do_video(
        page,
        saida,
        "video-02-bug",
        {
            "conversa": log,
            "onde": log.get_by_text("Onde aconteceu?"),
            "o_que": log.get_by_text("E o que aconteceu?"),
            "pede_print": log.get_by_text("Se tiver um print da tela"),
            "mensagem": page.get_by_label("Sua mensagem"),
            "print": page.get_by_role("button", name="Mandar um print"),
            "microfone": page.get_by_role("button", name="Gravar voz"),
            "pedido_na_lista": _na_lista(page, TITULO_DO_BUG),
        },
    )


def video_03_resumo_do_bug(page: Page, base: str, saida: Path) -> None:
    """O Resumo do bug: o que você disse, como saber que foi resolvido e os dois botões."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["resumo_do_bug"], TITULO_DO_BUG)
    resumo = page.get_by_role("region", name="Resumo do bug")
    resumo.wait_for(timeout=20000)
    _tela_do_video(
        page,
        saida,
        "video-03-resumo-do-bug",
        {
            "resumo": resumo,
            "campos": resumo.locator("dl"),
            "criterios": resumo.get_by_role("heading", name="Como saber que foi resolvido").locator(".."),
            "criar": page.get_by_role("button", name="Criar o card"),
            "nao_bateu": page.get_by_role("button", name="Não bateu"),
        },
    )


def video_04_enviado(page: Page, base: str, saida: Path) -> None:
    """Depois do Criar o card: o bug na fila do desenvolvimento."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["bug_enviado"], TITULO_DO_BUG)
    recado = page.get_by_text("A Vitta recebeu o seu relato")
    recado.wait_for(timeout=20000)
    _tela_do_video(
        page,
        saida,
        "video-04-enviado",
        {
            "enviado": recado.locator("xpath=ancestor::section[1]"),
            "outra": page.get_by_role("button", name="Começar outra conversa"),
        },
    )


def video_05_melhoria(page: Page, base: str, saida: Path) -> None:
    """A pergunta da melhoria: o contexto, as duas opções, a Recomendada e o Fechar e resumir."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["melhoria"], TITULO_DA_MELHORIA)
    opcoes = page.get_by_role("group", name="Opções")
    opcoes.wait_for(timeout=20000)
    log = _aberta(page).get_by_role("log")
    _tela_do_video(
        page,
        saida,
        "video-05-melhoria",
        {
            "conversa": log,
            "pergunta": log.get_by_text("Alguns setores dividem a mesma porta"),
            "opcoes": opcoes,
            "recomendada": opcoes.get_by_role("button").first,
            "selo_recomendada": opcoes.get_by_text("Recomendada", exact=True),
            "mensagem": page.get_by_label("Sua mensagem"),
            "microfone": page.get_by_role("button", name="Gravar voz"),
            "fechar": page.get_by_role("button", name="Fechar e resumir"),
        },
    )


def video_06_resumo_da_melhoria(page: Page, base: str, saida: Path) -> None:
    """O Resumo da melhoria: as Decisões com o porquê e o que ficou em aberto."""
    abrir_o_chat(page, base, LISTA_NO_MEIO, CONVERSAS["resumo_da_melhoria"], TITULO_DA_MELHORIA)
    resumo = page.get_by_role("region", name="Resumo da melhoria")
    resumo.wait_for(timeout=20000)
    _tela_do_video(
        page,
        saida,
        "video-06-resumo-da-melhoria",
        {
            "resumo": resumo,
            "decisoes": resumo.get_by_role("heading", name="Decisões").locator(".."),
            "porque": resumo.get_by_text("Por quê:").first.locator(".."),
            "em_aberto": resumo.get_by_role("heading", name="Ficou em aberto").locator(".."),
            "criar": page.get_by_role("button", name="Criar o card"),
            "nao_bateu": page.get_by_role("button", name="Não bateu"),
        },
    )


def video_07_lista(page: Page, base: str, saida: Path) -> None:
    """A lista com a Etapa de cada pedido."""
    lista = abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA)

    def etapa(titulo: str):
        return _na_lista(page, titulo).locator("span").last

    _tela_do_video(
        page,
        saida,
        "video-07-lista",
        {
            "lista": lista,
            "em_analise": etapa(TITULO_DA_MELHORIA),
            "em_desenvolvimento": etapa(TITULO_DO_BUG),
            "registrada": etapa("Lembrete na véspera"),
            "planejada": etapa("Números do Instagram"),
            "em_producao": etapa("Aviso quando a Ouvidoria"),
            "pedido_registrado": _na_lista(page, "Lembrete na véspera"),
        },
    )


def video_08_acompanhamento(page: Page, base: str, saida: Path) -> None:
    """O pedido que já foi para a Vitta: a Etapa e O que muda."""
    abrir_o_chat(page, base, LISTA_DO_DIA_A_DIA, CONVERSAS["melhoria_enviada"], TITULO_DA_MELHORIA)
    o_que_muda = page.get_by_role("region", name="O que muda")
    o_que_muda.wait_for(timeout=20000)
    _tela_do_video(
        page,
        saida,
        "video-08-acompanhamento",
        {
            "pedido_na_lista": _na_lista(page, TITULO_DA_MELHORIA),
            "selo": _aberta(page).locator("[aria-label^='Etapa: ']").first,
            "o_que_muda": o_que_muda,
        },
    )


PRINTS = {
    "bug-escolher": bug_escolher,
    "bug-conversa": bug_conversa,
    "resumo-do-bug": resumo_do_bug,
    "melhoria-escolher": melhoria_escolher,
    "melhoria-pergunta": melhoria_pergunta,
    "resumo-da-melhoria": resumo_da_melhoria,
    "lista-de-pedidos": lista_de_pedidos,
    "acompanhamento": acompanhamento,
    "video-01-abertura": video_01_abertura,
    "video-02-bug": video_02_bug,
    "video-03-resumo-do-bug": video_03_resumo_do_bug,
    "video-04-enviado": video_04_enviado,
    "video-05-melhoria": video_05_melhoria,
    "video-06-resumo-da-melhoria": video_06_resumo_da_melhoria,
    "video-07-lista": video_07_lista,
    "video-08-acompanhamento": video_08_acompanhamento,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/tecnologia")
    ap.add_argument("--print", dest="escolhido", choices=sorted(PRINTS))
    ap.add_argument("--semear", action="store_true", help="cria o login de exemplo no Supabase local e sai.")
    ap.add_argument("--video", action="store_true", help="captura só as telas do Vídeo de visão geral.")
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else sorted(PRINTS)
    if args.video:
        escolhidos = [nome for nome in escolhidos if nome.startswith("video-")]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            for nome in escolhidos:
                # Uma janela por tela, sem o service worker do app: com ele, a
                # resposta trocada no navegador não chega à tela, e a troca de
                # uma tela vazaria para a seguinte.
                tamanho = VIDEO if nome.startswith("video-") else COMPUTADOR
                janela = navegador.new_context(
                    viewport=tamanho, device_scale_factor=ESCALA, locale="pt-BR", service_workers="block"
                )
                try:
                    PRINTS[nome](janela.new_page(), args.base.rstrip("/"), saida)
                finally:
                    janela.close()
                print(f"print: {saida / (nome + '.png')}")
        finally:
            navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
