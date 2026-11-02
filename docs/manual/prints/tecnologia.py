#!/usr/bin/env python3
"""Roteiro de prints do módulo Tecnologia do Manual (ADR 0057, decisão 3).

A aba Tecnologia entrou no site do Manual como último módulo do menu (issue
#1367, PRD #1365); até lá ela tinha página própria, e este roteiro veio de lá.
O print segue a regra dos outros roteiros desta pasta: tela real do app em
localhost, capturada por código versionado, nunca recorte à mão.

**Dado de exemplo e só ele.** O Quadro mostra TODA Demanda do banco, sem
filtro, e o repositório é público. Por isso o roteiro recusa capturar se o
banco local tiver Demanda que ele não semeou (`_conferir_que_so_ha_exemplo`).
As pessoas são inventadas (`@exemplo.local`), na faixa P950 dos roteiros.

O planejamento é semeado já com uma pergunta da IA guardada: a tela abre a
conversa que está no banco e não chama a IA, então o print sai sem custo e
igual a cada rodada.

Receita:

1. Supabase local no ar, com as migrations da aba até a 123 aplicadas.
2. Stack com o código da tela: `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. `python3 docs/manual/prints/tecnologia.py --semear` (idempotente, só no
   banco local).
4. `python3 docs/manual/prints/tecnologia.py`.

As telas do Vídeo de visão geral (`video-NN-<passo>`) saem em 1920x1080, sem
balão, com as caixas dos elementos citados em `video-alvos.json`:
`python3 docs/manual/prints/tecnologia.py --video` (issue #1373).

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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Page

COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

EMAIL = "marina.duarte@exemplo.local"
SENHA = "ManualTecnologia2026!"

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"
# Quem entra para o print do Vínculo: os controles só aparecem para quem tem
# login no GitHub (ADR 0054, decisão 9), e a Marina não tem.
EMAIL_DA_VITTA = "rafael.moura@exemplo.local"

# (id, nome, email, login no GitHub). Todos Super admin: é quem entra na aba.
PESSOAS = [
    ("P950", "Marina Duarte", EMAIL, None),
    ("P951", "Rafael Moura", "rafael.moura@exemplo.local", "rafael-exemplo"),
    ("P952", "Tiago Lins", "tiago.lins@exemplo.local", "tiago-exemplo"),
]

DONO_DO_PRODUTO = {
    "Ana": "P951",
    "Integração Ana x MV": "P951",
    "Reuniões": "P952",
    "Ouvidoria": "P951",
    "POPs": "P952",
    "Site": "P952",
    "Infra": "P951",
    "Central de Comando": "P952",
    "Contas médicas": "P951",
}


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-a000-000000095{n:03d}"


# A Demanda que o print do card abre: a devolvida em Em produção, com imagem.
DEMANDA_DO_CARD = _uuid(1)

# (n, título, tipo, Produto, estado, responsável, prioridade, dias de idade,
#  Etapa, versão em produção, partes entregues, partes total, nº da issue)
DEMANDAS = [
    (1, "Aviso por e-mail quando a Ouvidoria encerrar um caso", "novo", "Ouvidoria", "aguardando", "P950",
     "normal", 9, "em_producao", "v0.167.0", 3, 3, 9901),
    (2, "O botão de salvar o POP não responde", "defeito", "POPs", "em_andamento", "P952",
     "alta", 3, "em_desenvolvimento", None, None, None, 9902),
    (3, "Decidir em quantos minutos a Ana encerra a conversa", "decisao", "Ana", "aguardando", "P950",
     "normal", 5, "registrada", None, None, None, None),
    (4, "Lista atualizada de setores para a Ouvidoria", "informacao", "Ouvidoria", "nova", "P951",
     "normal", 1, "registrada", None, None, None, None),
    (5, "Números do Instagram na Central de Comando", "novo", "Central de Comando", "em_andamento", "P952",
     "normal", 16, "planejada", None, 0, 2, 9903),
    (6, "Trocar o texto do rodapé do e-mail da ata", "ajuste", "Reuniões", "concluida", "P950",
     "baixa", 20, "em_producao", "v0.165.0", None, None, 9904),
    (7, "Avaliar a troca do provedor de e-mail", "consultoria", "Infra", "cancelada", "P951",
     "normal", 25, "registrada", None, None, None, None),
    (8, "Lembrete por e-mail na véspera da reunião", "novo", "Reuniões", "nova", "P952",
     "normal", 2, "registrada", None, None, None, None),
    (9, "Mostrar o nome do setor no cartaz do QR da Ouvidoria", "ajuste", "Ouvidoria", "em_andamento", "P951",
     "normal", 4, "registrada", None, None, None, None),
]

# O card que mostra o botão Planejar com a IA (Novo, sem Vínculo, sem
# conversa) e a Demanda cujo planejamento já começou.
DEMANDA_DO_BOTAO = _uuid(8)
DEMANDA_PLANEJADA = _uuid(9)
# A Demanda sem Vínculo que o print do Vínculo abre.
DEMANDA_SEM_VINCULO = _uuid(4)

# A conversa guardada: uma pergunta respondida e a seguinte em aberto, que é
# o que a tela mostra com as duas opções e a recomendada. A tela desenha só o
# `contexto` da pergunta, então a pergunta vai dentro dele, como a IA faz.
PLANEJAMENTO = {
    "mensagens": [
        {
            "tipo": "pergunta",
            "contexto": "O cartaz fica na porta do setor e o QR leva ao formulário da Ouvidoria. "
            "O nome do setor entra só no cartaz impresso, ou também no formulário que abre pelo QR?",
            "opcoes": [
                {"letra": "A", "texto": "Nos dois: quem lê o QR vê de que setor está falando"},
                {"letra": "B", "texto": "Só no cartaz impresso"},
            ],
            "recomendada": "A",
        },
        {"tipo": "resposta", "opcao": "A", "texto": "Nos dois: quem lê o QR vê de que setor está falando"},
        {
            "tipo": "pergunta",
            "contexto": "Alguns setores dividem a mesma porta, como a Recepção e a Internação. "
            "Quando isso acontece, o cartaz mostra os dois nomes ou cada setor tem o seu?",
            "opcoes": [
                {"letra": "A", "texto": "Cada setor com o seu cartaz e o seu QR"},
                {"letra": "B", "texto": "Um cartaz com os dois nomes"},
            ],
            "recomendada": "A",
        },
    ],
    "decisoes": ["O nome do setor aparece no cartaz e no formulário que abre pelo QR."],
}

O_QUE_MUDA = {
    1: "Quando a Ouvidoria encerra um caso, quem manifestou recebe um e-mail avisando, com o resumo da resposta.",
    2: "O botão Salvar do POP volta a gravar a versão e avisa quando a gravação falha.",
    5: "A Central de Comando passa a mostrar os números do Instagram ao lado dos do Site.",
    6: "O rodapé do e-mail da ata passa a dizer onde a ata fica guardada.",
}

NOME_DA_IMAGEM = "ouvidoria-encerrar-caso.png"
CAMINHO_DA_IMAGEM = f"exemplo/{DEMANDA_DO_CARD}/print-1.png"


# --------------------------------------------------------------------------
# Banco local
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


def _pedir(url: str, chave: str, caminho: str, metodo="GET", corpo=None, prefer=None, tipo="application/json", extra=None):
    if corpo is None:
        dados = None
    elif isinstance(corpo, bytes):
        dados = corpo
    else:
        dados = json.dumps(corpo).encode()
    cabecalhos = {"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": tipo}
    if prefer:
        cabecalhos["Prefer"] = prefer
    cabecalhos.update(extra or {})
    req = urllib.request.Request(f"{url}/{caminho}", data=dados, headers=cabecalhos, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=20) as resposta:
            texto = resposta.read().decode()
            return json.loads(texto) if texto.strip() else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{metodo} {caminho}: {e.code} {e.read().decode()[:300]}")


def _rest(url, chave, caminho, metodo="GET", corpo=None, prefer=None):
    return _pedir(url, chave, f"rest/v1/{caminho}", metodo, corpo, prefer)


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


def _quando(agora: datetime, dias: float) -> str:
    return (agora - timedelta(days=dias)).isoformat()


def _imagem_de_exemplo() -> bytes:
    """O print anexado: uma tela de encerramento inventada, desenhada pelo navegador."""
    from playwright.sync_api import sync_playwright

    html = """
    <body style="margin:0;font-family:Helvetica,Arial;background:#f8fafc">
      <div style="padding:40px 48px">
        <div style="font-size:44px;font-weight:700;color:#1e293b">Encerrar o caso</div>
        <div style="margin-top:8px;color:#64748b;font-size:26px">Ouvidoria, caso de exemplo</div>
        <div style="margin-top:28px;height:110px;border:2px solid #cbd5e1;border-radius:14px;background:#fff"></div>
        <div style="margin-top:28px;display:flex;gap:20px;align-items:center">
          <span style="padding:14px 34px;border-radius:14px;background:#2B2E7E;color:#fff;font-size:28px;font-weight:600">Encerrar</span>
          <span style="color:#b91c1c;font-size:26px">Ninguém é avisado</span>
        </div>
      </div>
    </body>"""
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        page = navegador.new_page(viewport={"width": 640, "height": 400})
        page.set_content(html)
        dados = page.screenshot()
        navegador.close()
    return dados


def semear() -> None:
    url, chave = _credenciais_locais()
    agora = datetime.now(timezone.utc)

    for pid, nome, email, github in PESSOAS:
        _rest(url, chave, "participantes", "POST", [{
            "id": pid,
            "nome_completo": nome,
            "email": email,
            "ativo": True,
            "access_profile": "super_admin",
            "is_super_admin": True,
            "is_externo": False,
            "github_login": github,
            "auth_user_id": _login_de_exemplo(url, chave, email),
        }], prefer="resolution=merge-duplicates")

    for produto, dono in DONO_DO_PRODUTO.items():
        _rest(url, chave, f"tecnologia_produtos?nome=eq.{urllib.parse.quote(produto)}", "PATCH", {"dono_id": dono})
    produtos = {p["nome"]: p["id"] for p in _rest(url, chave, "tecnologia_produtos?select=id,nome")}

    ids = ",".join(_uuid(n) for n, *_ in DEMANDAS)
    # O fio e as imagens são refeitos do zero a cada semeadura, só os das
    # Demandas de exemplo (pelo id), para o print não acumular linhas.
    _rest(url, chave, f"tecnologia_anexos?demanda_id=in.({ids})", "DELETE")
    _rest(url, chave, f"tecnologia_conversas?demanda_id=in.({ids})", "DELETE")
    _rest(url, chave, f"tecnologia_planejamentos?demanda_id=in.({ids})", "DELETE")

    for n, titulo, tipo, produto, estado, resp, prio, dias, etapa, versao, feitas, total, issue in DEMANDAS:
        linha = {
            "id": _uuid(n),
            "titulo": titulo,
            "descricao": O_QUE_MUDA.get(n, "Detalhes na Conversa."),
            "tipo": tipo,
            "produto_id": produtos[produto],
            "estado": estado,
            "responsavel_id": resp,
            "autor_id": "P950" if n != 4 else "P951",
            "prioridade": prio,
            "criado_em": _quando(agora, dias),
            "github_issue_numero": issue,
            "etapa": etapa,
            "partes_entregues": feitas,
            "partes_total": total,
            "o_que_muda": O_QUE_MUDA.get(n),
            "versao_em_producao": versao,
            "entregue_em": _quando(agora, 1 if n == 1 else 6) if etapa == "em_producao" else None,
            "concluida_em": _quando(agora, 2) if estado == "concluida" else None,
            "concluida_por": "P950" if estado == "concluida" else None,
            "cancelada_em": _quando(agora, 10) if estado == "cancelada" else None,
            "cancelada_por": "P951" if estado == "cancelada" else None,
        }
        _rest(url, chave, "tecnologia_demandas", "POST", [linha], prefer="resolution=merge-duplicates")

    def fio(n: int, dias: float, texto: str, autor=None, mencoes=None, campo=None, de=None, para=None):
        return {
            "demanda_id": _uuid(n),
            "autor_id": autor,
            "linha": "movimento" if campo else "resposta",
            "texto": texto,
            "mencoes": mencoes or [],
            "movimento_campo": campo,
            "movimento_de": de,
            "movimento_para": para,
            "criado_em": _quando(agora, dias),
        }

    _rest(url, chave, "tecnologia_conversas", "POST", [
        fio(1, 8.9, "Hoje quem manifestou não fica sabendo que o caso acabou. Mandei o print da tela de encerramento.",
            autor="P950"),
        fio(1, 7, "Rafael Moura moveu para Em andamento", campo="estado", de="nova", para="em_andamento"),
        fio(1, 1.01, "Em produção na v0.167.0", campo="etapa", de="entregue", para="em_producao"),
        fio(1, 1, "A entrega moveu para Aguardando", campo="estado", de="em_andamento", para="aguardando"),
        fio(3, 4, "@Marina Duarte, os planos costumam usar 30 minutos. Você prefere mais folgado?",
            autor="P951", mencoes=["P950"]),
        fio(3, 4, "Rafael Moura moveu para Aguardando", campo="estado", de="nova", para="aguardando"),
        # A Conversa do card que o Vídeo de visão geral abre (issue #1373).
        fio(9, 3.9, "@Rafael Moura, a Recepção e a Internação dividem a mesma porta. Como fica o cartaz?",
            autor="P950", mencoes=["P951"]),
        fio(9, 3.6, "Rafael Moura moveu para Em andamento", campo="estado", de="nova", para="em_andamento"),
        fio(9, 3.5, "Boa pergunta. Vale planejar com a IA: as perguntas são de quem usa o cartaz.",
            autor="P951"),
    ])

    caminho = f"storage/v1/object/anexos-tecnologia/{CAMINHO_DA_IMAGEM}"
    imagem = _imagem_de_exemplo()
    # `x-upsert`: a semeadura roda de novo sem tropeçar no arquivo de antes.
    _pedir(url, chave, caminho, "POST", imagem, tipo="image/png", extra={"x-upsert": "true"})
    _rest(url, chave, "tecnologia_anexos", "POST", [{
        "demanda_id": DEMANDA_DO_CARD,
        "ordem": 1,
        "storage_path": CAMINHO_DA_IMAGEM,
        "nome_original": NOME_DA_IMAGEM,
        "content_type": "image/png",
        "tamanho_bytes": len(imagem),
        "anexado_por": "P950",
        "criado_em": _quando(agora, 8.9),
    }])
    _rest(url, chave, "tecnologia_planejamentos", "POST", [{
        "demanda_id": DEMANDA_PLANEJADA,
        "estado": "em_andamento",
        "mensagens": PLANEJAMENTO["mensagens"],
        "decisoes": PLANEJAMENTO["decisoes"],
        "modelo": "exemplo",
    }])
    print("dados de exemplo da aba Tecnologia prontos.")


def _conferir_que_so_ha_exemplo() -> None:
    """Recusa capturar quando o banco tem Demanda que não é de exemplo."""
    url, chave = _credenciais_locais()
    nossas = {_uuid(n) for n, *_ in DEMANDAS}
    alheias = [d["titulo"] for d in _rest(url, chave, "tecnologia_demandas?select=id,titulo") if d["id"] not in nossas]
    if alheias:
        raise SystemExit(f"recusado: o banco local tem {len(alheias)} Demanda(s) fora do exemplo, e o Quadro mostra todas.")


# --------------------------------------------------------------------------
# Prints
# --------------------------------------------------------------------------


def sem_foco(page) -> None:
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.wait_for_timeout(200)


def entrar(page: Page, base: str, email: str = EMAIL) -> None:
    if "/login" not in page.url and page.url.startswith(base):
        return
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(email)
    page.get_by_placeholder("••••••••").fill(SENHA)
    page.get_by_role("button", name="Entrar").click()
    page.wait_for_url(lambda url: "/login" not in url, timeout=30000)


def _abrir_a_aba(page: Page, base: str) -> None:
    entrar(page, base)
    page.goto(f"{base}/admin/tecnologia", wait_until="networkidle")
    page.get_by_text("Decidir em quantos minutos").first.wait_for(timeout=20000)


def quadro(page: Page, base: str, saida: Path) -> None:
    _abrir_a_aba(page, base)
    sem_foco(page)
    page.screenshot(path=str(saida / "quadro.png"))


def painel(page: Page, base: str, saida: Path) -> None:
    _abrir_a_aba(page, base)
    page.get_by_role("tab", name="Painel").or_(page.get_by_role("button", name="Painel")).first.click()
    page.get_by_label("Números do Painel").wait_for(timeout=20000)
    page.get_by_text("Trocar o texto do rodapé").first.wait_for(timeout=20000)
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1180})
    sem_foco(page)
    page.screenshot(path=str(saida / "painel.png"))
    page.set_viewport_size(COMPUTADOR)


def card(page: Page, base: str, saida: Path) -> None:
    entrar(page, base)
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1500})
    page.goto(f"{base}/admin/tecnologia?demanda={DEMANDA_DO_CARD}", wait_until="networkidle")
    page.get_by_label("Imagens da Demanda").wait_for(timeout=20000)
    page.locator("section[aria-label='Imagens da Demanda'] img").first.wait_for(timeout=20000)
    page.wait_for_timeout(800)
    sem_foco(page)
    page.screenshot(path=str(saida / "card.png"))
    page.set_viewport_size(COMPUTADOR)


def produtos(page: Page, base: str, saida: Path) -> None:
    _abrir_a_aba(page, base)
    page.get_by_role("link", name="Produtos").click()
    page.get_by_label("Nome do Produto").wait_for(timeout=20000)
    page.get_by_text("Central de Comando").first.wait_for(timeout=20000)
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1100})
    sem_foco(page)
    page.screenshot(path=str(saida / "produtos.png"))
    page.set_viewport_size(COMPUTADOR)


def formulario(page: Page, base: str, saida: Path) -> None:
    entrar(page, base)
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1100})
    page.goto(f"{base}/admin/tecnologia/nova", wait_until="networkidle")
    page.get_by_text("prefiro preencher à mão").click()
    page.get_by_text("Abrir Demanda").first.wait_for(timeout=20000)
    page.wait_for_timeout(500)
    sem_foco(page)
    page.screenshot(path=str(saida / "formulario.png"))
    page.set_viewport_size(COMPUTADOR)


def _abrir_o_card(page: Page, base: str, demanda: str, altura: int = 1300) -> None:
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": altura})
    page.goto(f"{base}/admin/tecnologia?demanda={demanda}", wait_until="networkidle")
    page.get_by_role("button", name="Copiar para IA").first.wait_for(timeout=20000)
    page.wait_for_timeout(800)
    sem_foco(page)


def planejar(page: Page, base: str, saida: Path) -> None:
    entrar(page, base)
    _abrir_o_card(page, base, DEMANDA_DO_BOTAO)
    page.get_by_text("Planejar com a IA").first.wait_for(timeout=20000)
    page.screenshot(path=str(saida / "planejar.png"))
    page.set_viewport_size(COMPUTADOR)


def planejamento(page: Page, base: str, saida: Path) -> None:
    entrar(page, base)
    page.set_viewport_size({"width": COMPUTADOR["width"], "height": 1000})
    page.goto(f"{base}/admin/tecnologia/planejamento/{DEMANDA_PLANEJADA}", wait_until="networkidle")
    page.get_by_role("group", name="Opções").wait_for(timeout=20000)
    page.wait_for_timeout(500)
    sem_foco(page)
    page.screenshot(path=str(saida / "planejamento.png"))
    page.set_viewport_size(COMPUTADOR)


def vinculo(page: Page, base: str, saida: Path) -> None:
    """O card visto por quem tem login no GitHub, num contexto à parte."""
    contexto = page.context.browser.new_context(viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR")
    outra = contexto.new_page()
    try:
        entrar(outra, base, EMAIL_DA_VITTA)
        _abrir_o_card(outra, base, DEMANDA_SEM_VINCULO)
        outra.get_by_label("Vincular issue").wait_for(timeout=20000)
        outra.screenshot(path=str(saida / "vinculo.png"))
    finally:
        contexto.close()


# --------------------------------------------------------------------------
# As telas do Vídeo de visão geral (ADR 0076, issue #1373)
# --------------------------------------------------------------------------
#
# Janela inteira de 1920x1080, sem balão: no vídeo quem aponta é o cursor e o
# destaque. Cada tela grava em `video-alvos.json` a caixa (x, y, largura,
# altura, em pixels da janela) de cada elemento que a fala cita, e a cena do
# Remotion põe o destaque em cima dela sem medir a olho.
#
# O vídeo segue a Demanda do cartaz do QR (a 9) do registro ao "sim". Os
# estados que o banco de exemplo não guarda (a conversa do assistente, o
# resumo, o enviado, o card depois do sim) entram pela tela de verdade, com a
# resposta do servidor trocada no navegador; nada disso grava no banco.

VIDEO = {"width": 1920, "height": 1080}

TITULO_DO_VIDEO = "Mostrar o nome do setor no cartaz do QR da Ouvidoria"

# A primeira fala do assistente, igual à da tela (PRIMEIRA_MENSAGEM).
BOAS_VINDAS = (
    "Oi. Me conta o que você precisa, do jeito que vier: o que aconteceu, o que você queria, "
    "ou a dúvida que ficou. Dá para escrever, falar no microfone, anexar um áudio ou um documento "
    "e mandar um print da tela. Eu vou montando o pedido aqui do lado e você confere antes de criar."
)

CONVERSA_DO_ASSISTENTE = [
    {"role": "assistant", "content": BOAS_VINDAS},
    {"role": "user", "content": "O cartaz com o QR da Ouvidoria não diz de que setor é. "
                                "Quem lê o QR não sabe de onde está falando."},
    {"role": "assistant", "content": "Entendi. O nome do setor precisa aparecer só no cartaz impresso, "
                                     "ou também no formulário que abre pelo QR?"},
    {"role": "user", "content": "Nos dois. É um ajuste, sem pressa."},
    {"role": "assistant", "content": "Montei o pedido ao lado: um Ajuste na Ouvidoria, prioridade Normal. "
                                     "Confira e clique em Criar Demanda."},
]

DESCRICAO_DO_VIDEO = (
    "Onde: no cartaz com o QR de cada setor e no formulário que abre pelo QR.\n"
    "O que mudar: mostrar o nome do setor nos dois, para quem manifesta saber de que setor está falando."
)

RESUMO_DO_VIDEO = {
    "decisoes": [
        {
            "pergunta": "O nome do setor entra só no cartaz impresso, ou também no formulário que abre pelo QR?",
            "escolha": "Nos dois: quem lê o QR vê de que setor está falando",
            "porque": "Quem manifesta precisa saber de que setor está falando antes de escrever.",
        },
        {
            "pergunta": "Quando dois setores dividem a mesma porta, o cartaz mostra os dois nomes ou cada setor tem o seu?",
            "escolha": "Cada setor com o seu cartaz e o seu QR",
            "porque": "Assim a manifestação já chega ao setor certo.",
        },
    ],
    "em_aberto": ["Onde fica cada cartaz quando a Recepção e a Internação dividem a porta."],
}

O_QUE_MUDA_DO_VIDEO = (
    "O cartaz com o QR e o formulário da Ouvidoria passam a mostrar o nome do setor. "
    "Cada setor tem o seu cartaz e o seu QR, mesmo quando divide a porta com outro."
)


def _caixa(alvo) -> list[float]:
    caixa = alvo.bounding_box()
    return [round(caixa[k], 1) for k in ("x", "y", "width", "height")]


def _tela_do_video(page: Page, saida: Path, nome: str, alvos: dict) -> None:
    """Captura a janela e grava as caixas dos alvos ao lado das telas."""
    page.wait_for_load_state("networkidle")
    sem_foco(page)
    # O vídeo não escreve versão (o carimbo mora no meta.json), e o build
    # local mostra a versão do package.json, não a de produção.
    page.evaluate(
        "document.querySelectorAll(\"span[aria-label^='Versão']\").forEach((e) => { e.style.visibility = 'hidden'; })"
    )
    page.wait_for_timeout(400)
    caixas = {chave: _caixa(alvo) for chave, alvo in alvos.items()}
    page.screenshot(path=str(saida / f"{nome}.png"))
    arquivo = saida / "video-alvos.json"
    dados = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.is_file() else {}
    dados[nome] = caixas
    arquivo.write_text(json.dumps(dados, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def _lista_trocada(page: Page, demanda: str, campos: dict) -> None:
    """A lista do Quadro chega com `campos` trocados na Demanda (só no navegador)."""

    def tratar(rota):
        resposta = rota.fetch()
        lista = resposta.json()
        for item in lista:
            if item["id"] == demanda:
                item.update(campos)
        rota.fulfill(response=resposta, json=lista)

    page.route(lambda url: urllib.parse.urlparse(url).path.rstrip("/") == "/api/admin/tecnologia/demandas", tratar)


def _planejamento_trocado(page: Page, campos: dict) -> None:
    """O planejamento da Demanda 9 chega com `campos` trocados (só no navegador)."""

    def tratar(rota):
        if rota.request.method != "GET":
            rota.continue_()
            return
        resposta = rota.fetch()
        corpo = resposta.json()
        corpo.update(campos)
        rota.fulfill(response=resposta, json=corpo)

    page.route(f"**/api/admin/tecnologia/demandas/{DEMANDA_PLANEJADA}/planejamento", tratar)


def _quadro_no_video(page: Page, base: str) -> None:
    page.set_viewport_size(VIDEO)
    _abrir_a_aba(page, base)


def _card_no_video(page: Page, base: str, demanda: str, email: str = EMAIL) -> None:
    page.set_viewport_size(VIDEO)
    entrar(page, base, email)
    page.goto(f"{base}/admin/tecnologia?demanda={demanda}", wait_until="networkidle")
    page.get_by_role("button", name="Copiar para IA").first.wait_for(timeout=20000)
    page.wait_for_timeout(800)


def _cartao(page: Page, raia: str, titulo: str):
    return page.get_by_role("region", name=raia).locator("li").filter(has_text=titulo).first


def video_01_quadro(page: Page, base: str, saida: Path) -> None:
    """O Quadro: Nova Demanda, as três raias e os selos da Etapa."""
    _quadro_no_video(page, base)
    nova = _cartao(page, "Nova", "Lembrete por e-mail")
    _tela_do_video(page, saida, "video-01-quadro", {
        "nova_demanda": page.get_by_role("link", name="Nova Demanda"),
        "raias": page.get_by_role("region", name="Nova").locator(".."),
        "raia_nova": page.get_by_role("region", name="Nova"),
        "raia_andamento": page.get_by_role("region", name="Em andamento"),
        "raia_aguardando": page.get_by_role("region", name="Aguardando"),
        "cartao_nova": nova,
        "dono_nova": nova.get_by_text("Tiago Lins"),
        "selo_planejada": page.locator("[aria-label^='Etapa: Planejada']").first,
        "selo_desenvolvimento": page.locator("[aria-label^='Etapa: Em desenvolvimento']").first,
        "selo_producao": page.locator("[aria-label^='Etapa: Em produção']").first,
    })


def video_02_assistente(page: Page, base: str, saida: Path) -> None:
    """O assistente com a conversa do cartaz do QR e o Rascunho montado ao lado."""
    url, chave = _credenciais_locais()
    ouvidoria = _rest(url, chave, "tecnologia_produtos?select=id&nome=eq.Ouvidoria")[0]["id"]
    estado = {
        "messages": CONVERSA_DO_ASSISTENTE,
        "rascunho": {
            "titulo": TITULO_DO_VIDEO,
            "tipo": "ajuste",
            "produto_id": ouvidoria,
            "prioridade": "normal",
            "prazo": None,
            "descricao": DESCRICAO_DO_VIDEO,
        },
        "prints": [],
    }
    page.set_viewport_size(VIDEO)
    entrar(page, base)
    page.add_init_script(f"window.sessionStorage.setItem('tecnologia:assistente', {json.dumps(json.dumps(estado))});")
    page.goto(f"{base}/admin/tecnologia/nova", wait_until="networkidle")
    page.get_by_text("Montei o pedido ao lado").wait_for(timeout=20000)
    page.wait_for_timeout(800)
    # A conversa rola até a última fala e leva a página junto: o alto volta.
    page.evaluate("window.scrollTo(0, 0)")
    rascunho = page.locator("section").filter(has=page.get_by_role("heading", name="Rascunho da Demanda")).first
    _tela_do_video(page, saida, "video-02-assistente", {
        "rascunho": rascunho,
        "titulo": page.get_by_label("Título"),
        "conversa": page.get_by_text("Nos dois. É um ajuste").locator(".."),
        "mensagem": page.get_by_label("Mensagem").locator(".."),
        "microfone": page.get_by_role("button", name="Gravar voz"),
        "print": page.get_by_role("button", name="Anexar print"),
        "criar": page.get_by_role("button", name="Criar Demanda"),
    })


def video_03_conversa(page: Page, base: str, saida: Path) -> None:
    """O card da Demanda 9 aberto na Conversa, com a menção."""
    _lista_trocada(page, DEMANDA_PLANEJADA, {"tem_planejamento": False})
    _card_no_video(page, base, DEMANDA_PLANEJADA)
    conversa = page.get_by_role("heading", name="Conversa").locator("..")
    conversa.scroll_into_view_if_needed()
    page.get_by_role("button", name="Responder").scroll_into_view_if_needed()
    _tela_do_video(page, saida, "video-03-conversa", {
        "conversa": conversa,
        "mencao": page.get_by_text("a Recepção e a Internação dividem").first,
        "linhas": conversa.locator("ol").first,
        "linha_mencao": conversa.locator("li").first,
        "caixa": page.get_by_label("Resposta", exact=True),
        "responder": page.get_by_role("button", name="Responder"),
    })


def video_04_planejar(page: Page, base: str, saida: Path) -> None:
    """O card da Demanda 9, de tipo Ajuste, com o botão Planejar com a IA."""
    _lista_trocada(page, DEMANDA_PLANEJADA, {"tem_planejamento": False})
    _card_no_video(page, base, DEMANDA_PLANEJADA)
    botao = page.get_by_role("link", name="Planejar com a IA")
    botao.scroll_into_view_if_needed()
    _tela_do_video(page, saida, "video-04-planejar", {
        "planejar": botao,
        "titulo": page.get_by_label("Título"),
    })


def video_05_planejamento(page: Page, base: str, saida: Path) -> None:
    """A pergunta em aberto, as duas opções com a Recomendada e O que já decidimos."""
    page.set_viewport_size(VIDEO)
    entrar(page, base)
    page.goto(f"{base}/admin/tecnologia/planejamento/{DEMANDA_PLANEJADA}", wait_until="networkidle")
    opcoes = page.get_by_role("group", name="Opções")
    opcoes.wait_for(timeout=20000)
    _tela_do_video(page, saida, "video-05-planejamento", {
        "pergunta": page.get_by_text("Alguns setores dividem a mesma porta").first,
        "opcoes": opcoes,
        "recomendada": opcoes.get_by_role("button").first,
        "selo_recomendada": opcoes.get_by_text("Recomendada", exact=True),
        "resposta": page.get_by_label("Sua resposta"),
        "microfone": page.get_by_role("button", name="Gravar voz"),
        "decididos": page.get_by_role("region", name="O que já decidimos"),
        "fechar": page.get_by_role("button", name="Fechar e resumir"),
    })


def video_06_resumo(page: Page, base: str, saida: Path) -> None:
    """O resumo: as decisões com o porquê, o que ficou em aberto, o sim e o não."""
    _planejamento_trocado(page, {"estado": "resumido", "resumo": RESUMO_DO_VIDEO})
    page.set_viewport_size(VIDEO)
    entrar(page, base)
    page.goto(f"{base}/admin/tecnologia/planejamento/{DEMANDA_PLANEJADA}", wait_until="networkidle")
    sim = page.get_by_role("button", name="Sim, mandar para os desenvolvedores")
    sim.wait_for(timeout=20000)
    decisoes = page.get_by_role("region", name="Decisões")
    _tela_do_video(page, saida, "video-06-resumo", {
        "resumo": sim.locator("xpath=ancestor::section[1]"),
        "decisoes": decisoes,
        "porque": decisoes.get_by_text("Por quê:").first.locator(".."),
        "em_aberto": page.get_by_role("region", name="Ficou em aberto"),
        "sim": sim,
        "nao": page.get_by_role("button", name="Não", exact=True),
    })


def video_07_enviado(page: Page, base: str, saida: Path) -> None:
    """Depois do sim: Mandado para os desenvolvedores."""
    _planejamento_trocado(page, {"estado": "enviado", "resumo": RESUMO_DO_VIDEO})
    page.set_viewport_size(VIDEO)
    entrar(page, base)
    page.goto(f"{base}/admin/tecnologia/planejamento/{DEMANDA_PLANEJADA}", wait_until="networkidle")
    titulo = page.get_by_role("heading", name="Mandado para os desenvolvedores")
    titulo.wait_for(timeout=20000)
    _tela_do_video(page, saida, "video-07-enviado", {
        "enviado": titulo.locator("xpath=ancestor::section[1]"),
    })


# A Demanda 9 depois do sim, como a lista do Quadro passa a trazê-la.
DEPOIS_DO_SIM = {
    "etapa": "em_analise",
    "o_que_muda": O_QUE_MUDA_DO_VIDEO,
    "tem_vinculo": True,
    "tem_planejamento": True,
    "github_issue_numero": 9905,
}


def video_08_em_analise(page: Page, base: str, saida: Path) -> None:
    """O Quadro depois do sim: o card do cartaz do QR com o selo Em análise."""
    _lista_trocada(page, DEMANDA_PLANEJADA, DEPOIS_DO_SIM)
    _quadro_no_video(page, base)
    cartao = _cartao(page, "Em andamento", "nome do setor no cartaz")
    _tela_do_video(page, saida, "video-08-em-analise", {
        "cartao": cartao,
        "selo": cartao.locator("[aria-label^='Etapa: Em análise']"),
    })


def video_09_o_que_muda(page: Page, base: str, saida: Path) -> None:
    """O card depois do sim, aberto: o O que muda com as decisões."""
    _lista_trocada(page, DEMANDA_PLANEJADA, DEPOIS_DO_SIM)
    _card_no_video(page, base, DEMANDA_PLANEJADA)
    _tela_do_video(page, saida, "video-09-o-que-muda", {
        "o_que_muda": page.get_by_role("region", name="O que muda"),
    })


def video_10_vinculo(page: Page, base: str, saida: Path) -> None:
    """O Vínculo visto por quem é da Vitta: o número ou Levar para desenvolvimento."""
    # A janela de cada tela do vídeo nasce sem sessão: entra direto quem tem
    # login no GitHub, porque os controles só aparecem para ele.
    _card_no_video(page, base, DEMANDA_SEM_VINCULO, EMAIL_DA_VITTA)
    campo = page.get_by_label("Vincular issue")
    campo.scroll_into_view_if_needed()
    _tela_do_video(page, saida, "video-10-vinculo", {
        "vinculo": page.get_by_role("region", name="Vínculo com o desenvolvimento"),
        "numero": campo,
        "vincular": page.get_by_role("button", name="Vincular", exact=True),
        "levar": page.get_by_role("button", name="Levar para desenvolvimento"),
    })


def video_11_painel(page: Page, base: str, saida: Path) -> None:
    """O Painel: a entrega em Com você, com o recado de conferir e concluir."""
    _quadro_no_video(page, base)
    page.get_by_role("tab", name="Painel").or_(page.get_by_role("button", name="Painel")).first.click()
    com_voce = page.get_by_role("region", name="Com você")
    com_voce.wait_for(timeout=20000)
    page.get_by_text("Trocar o texto do rodapé").first.wait_for(timeout=20000)
    linha = com_voce.locator("li").filter(has_text="Aviso por e-mail quando a Ouvidoria").first
    _tela_do_video(page, saida, "video-11-painel", {
        "com_voce": com_voce,
        "entregue": linha,
        "recado": linha.get_by_text("Entregue, confira e conclua"),
    })


def video_12_entrega(page: Page, base: str, saida: Path) -> None:
    """O card da entrega: o O que muda e o Concluir, em Mover."""
    _card_no_video(page, base, DEMANDA_DO_CARD)
    mover = page.get_by_role("group", name="Mover")
    mover.scroll_into_view_if_needed()
    _tela_do_video(page, saida, "video-12-entrega", {
        "o_que_muda": page.get_by_role("region", name="O que muda"),
        "mover": mover,
        "concluir": page.get_by_role("button", name="Concluir a Demanda"),
    })


def video_13_entrega_conversa(page: Page, base: str, saida: Path) -> None:
    """O mesmo card, na Conversa: a linha Em produção e a caixa de resposta."""
    _card_no_video(page, base, DEMANDA_DO_CARD)
    responder = page.get_by_role("button", name="Responder")
    responder.scroll_into_view_if_needed()
    conversa = page.get_by_role("heading", name="Conversa").locator("..")
    _tela_do_video(page, saida, "video-13-entrega-conversa", {
        "conversa": conversa,
        "linha_producao": conversa.locator("li").filter(has_text="Em produção na v0.167.0").first,
        "caixa": page.get_by_label("Resposta", exact=True),
        "responder": responder,
    })


PRINTS = {
    "quadro": quadro,
    "painel": painel,
    "card": card,
    "produtos": produtos,
    "formulario": formulario,
    "planejar": planejar,
    "planejamento": planejamento,
    "vinculo": vinculo,
    "video-01-quadro": video_01_quadro,
    "video-02-assistente": video_02_assistente,
    "video-03-conversa": video_03_conversa,
    "video-04-planejar": video_04_planejar,
    "video-05-planejamento": video_05_planejamento,
    "video-06-resumo": video_06_resumo,
    "video-07-enviado": video_07_enviado,
    "video-08-em-analise": video_08_em_analise,
    "video-09-o-que-muda": video_09_o_que_muda,
    "video-10-vinculo": video_10_vinculo,
    "video-11-painel": video_11_painel,
    "video-12-entrega": video_12_entrega,
    "video-13-entrega-conversa": video_13_entrega_conversa,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/src/assets/tecnologia")
    ap.add_argument("--print", dest="escolhido", choices=sorted(PRINTS))
    ap.add_argument("--semear", action="store_true", help="cria os dados de exemplo no Supabase local e sai.")
    ap.add_argument("--video", action="store_true", help="captura só as telas do Vídeo de visão geral.")
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

    _conferir_que_so_ha_exemplo()
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else sorted(PRINTS)
    if args.video:
        escolhidos = [nome for nome in escolhidos if nome.startswith("video-")]

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR")
        page = contexto.new_page()
        try:
            for nome in escolhidos:
                if nome.startswith("video-"):
                    # Uma janela por tela do vídeo, sem o service worker do
                    # app: com ele, a resposta trocada no navegador não chega
                    # à tela, e a troca de uma tela vazaria para a seguinte.
                    janela = navegador.new_context(
                        viewport=VIDEO, device_scale_factor=ESCALA, locale="pt-BR", service_workers="block"
                    )
                    try:
                        PRINTS[nome](janela.new_page(), args.base.rstrip("/"), saida)
                    finally:
                        janela.close()
                else:
                    PRINTS[nome](page, args.base.rstrip("/"), saida)
                print(f"print: {saida / (nome + '.png')}")
        finally:
            navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
