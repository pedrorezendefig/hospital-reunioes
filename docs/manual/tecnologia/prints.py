#!/usr/bin/env python3
"""Roteiro de prints do manual da aba Tecnologia (issue #1066, PRD #1056).

A aba Tecnologia fica fora do site do Manual (ADR 0057, decisão 1) e tem
página própria (`index.html` desta pasta). O print segue a mesma regra dos
roteiros de `docs/manual/prints/`: tela real do app em localhost, capturada por
código versionado, nunca recorte à mão.

**Dado de exemplo e só ele.** O Quadro mostra TODA Demanda do banco, sem
filtro, e o repositório é público. Por isso o roteiro recusa capturar se o
banco local tiver Demanda que ele não semeou (`_conferir_que_so_ha_exemplo`).
As pessoas são inventadas (`@exemplo.local`), na faixa P950 dos roteiros.

Receita:

1. Supabase local no ar, com as migrations da aba até a 115 aplicadas.
2. Stack com o código da tela: `bash .claude/skills/atualizar-app/scripts/apply.sh`.
3. `python3 docs/manual/tecnologia/prints.py --semear` (idempotente, só no
   banco local).
4. `python3 docs/manual/tecnologia/prints.py`.

Uso: python3 docs/manual/tecnologia/prints.py [--base http://localhost:3000]
     [--saida docs/manual/tecnologia/img] [--print <nome>] [--semear]
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
]

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


def entrar(page: Page, base: str) -> None:
    if "/login" not in page.url and page.url.startswith(base):
        return
    page.goto(f"{base}/login", wait_until="networkidle")
    page.get_by_placeholder("seu@email.com").fill(EMAIL)
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


PRINTS = {"quadro": quadro, "painel": painel, "card": card, "produtos": produtos}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--saida", default="docs/manual/tecnologia/img")
    ap.add_argument("--print", dest="escolhido", choices=sorted(PRINTS))
    ap.add_argument("--semear", action="store_true", help="cria os dados de exemplo no Supabase local e sai.")
    args = ap.parse_args()

    if args.semear:
        semear()
        return 0

    _conferir_que_so_ha_exemplo()
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    escolhidos = [args.escolhido] if args.escolhido else sorted(PRINTS)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        navegador = p.chromium.launch()
        contexto = navegador.new_context(viewport=COMPUTADOR, device_scale_factor=ESCALA, locale="pt-BR")
        page = contexto.new_page()
        try:
            for nome in escolhidos:
                PRINTS[nome](page, args.base.rstrip("/"), saida)
                print(f"print: {saida / (nome + '.png')}")
        finally:
            navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
