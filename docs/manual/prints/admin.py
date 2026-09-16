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


def _conferir_o_filtro() -> None:
    """Recusa capturar quando o filtro deixou de ser uma peneira.

    A guarda é de execução, e não só de teste, porque o dano é gravar um
    arquivo: com o termo vazio a busca devolve a lista inteira, e o `.png` com
    nome e email de gente do hospital já estaria escrito em disco quando
    alguém fosse reparar. Falha fechada, antes de abrir a tela.
    """
    termo = FILTRO_DE_EXEMPLO.strip()
    if len(termo) < MINIMO_DO_FILTRO:
        raise SystemExit(
            f"recusado: o filtro da busca é '{FILTRO_DE_EXEMPLO}', com menos de "
            f"{MINIMO_DO_FILTRO} letras. Termo curto casa gente de verdade, e o "
            "print da lista de Usuários sairia com nome e email reais."
        )


def _usuarios_filtrados(page: Page, base: str) -> None:
    """Abre a tela de Usuários já peneirada pelas pessoas de exemplo.

    A busca é digitada ANTES de qualquer espera de linha: entre abrir a tela e
    filtrar existe um instante com a lista real na tela, e capturar nele seria
    publicar nome e email de gente do hospital.
    """
    _conferir_o_filtro()
    page.goto(f"{base}/admin/usuarios", wait_until="networkidle")
    busca = page.get_by_placeholder("Buscar por nome ou email…")
    busca.wait_for()
    busca.fill(FILTRO_DE_EXEMPLO)
    page.get_by_role("cell", name="Camila Prado").wait_for(timeout=15000)
    # A lista recarrega a cada tecla: sem esta pausa o print pega o esqueleto
    # de carregamento no lugar das linhas.
    page.wait_for_timeout(1500)


def painel_de_administracao(page: Page, base: str, saida: Path) -> None:
    """O painel inteiro: a barra com as quatro seções e a lista de Usuários."""
    entrar(page, base)
    _usuarios_filtrados(page, base)
    page.screenshot(
        path=str(saida / "painel-de-administracao.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 620},
    )


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
    campo = lambda rotulo: page.locator(  # noqa: E731
        f"xpath=//span[starts-with(normalize-space(),'{rotulo}')]"
        "/following::input[1]"
    )
    campo("Nome completo").fill("Bruno Tavares")
    campo("Email").fill("bruno.tavares@exemplo.local")
    campo("Cargo").fill("Coordenador de Enfermagem")
    campo("Setor").fill("Centro de Terapia Intensiva")
    # Sem foco em campo nenhum: o cursor piscando no último campo aparece no
    # print como um traço solto.
    page.get_by_role("heading", name="Novo usuário").click()
    page.wait_for_timeout(400)
    modal = page.get_by_role("heading", name="Novo usuário").locator(
        "xpath=ancestor::div[contains(@class,'rounded')][1]"
    )
    modal.screenshot(path=str(saida / "novo-usuario.png"))


PRINTS = {
    "painel-de-administracao": painel_de_administracao,
    "novo-usuario": novo_usuario,
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
        for nome in escolhidos:
            PRINTS[nome](page, args.base.rstrip("/"), saida)
            print(f"print: {saida / (nome + '.png')}")
        navegador.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
