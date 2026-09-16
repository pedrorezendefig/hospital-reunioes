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

Uso: python3 docs/manual/prints/pops.py [--base http://localhost:3000]
     [--saida docs/manual/src/assets/pops] [--print <nome>] [--semear]
"""

from __future__ import annotations

import argparse
import json
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

# Tela de trabalho sentada: POPs se usa no computador, não no corredor.
COMPUTADOR = {"width": 1440, "height": 900}
ESCALA = 2

# A pessoa de exemplo do módulo, criada pelo `--semear`.
EMAIL = "marina.alves@exemplo.local"
SENHA = "ManualPops2026!"

ENV_LOCAL = Path(__file__).resolve().parents[3] / "hospital-reunioes" / ".env"


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


def gestao_de_pops(page: Page, base: str, saida: Path) -> None:
    """A tela inicial do módulo: a lista do escopo com o filtro por estado."""
    entrar(page, base)
    page.goto(f"{base}/pops", wait_until="networkidle")
    page.get_by_text("POPs do meu escopo").wait_for()
    page.get_by_role("heading", name="Gestão de POPs").click()
    page.screenshot(path=str(saida / "gestao-de-pops.png"))


def _escolher(page: Page, rotulo: str, opcao: str) -> None:
    """Escolhe um valor numa lista de seleção do app.

    O campo não é um `<select>` nativo e o rótulo não aponta para ele, então a
    busca é pelo primeiro campo depois do rótulo na tela.
    """
    page.locator(
        f"xpath=//label[normalize-space()='{rotulo}']/following::*[@role='combobox'][1]"
    ).click()
    page.get_by_role("option", name=opcao, exact=True).first.click()


def criar_novo_pop(page: Page, base: str, saida: Path) -> None:
    """O formulário de criação, preenchido como quem abre um POP preencheria.

    A captura é do modal, e não da tela toda: o formulário é o assunto, e a
    lista atrás dele entra desfocada no print de página inteira.
    """
    entrar(page, base)
    page.goto(f"{base}/pops", wait_until="networkidle")
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
    # Sem foco em campo nenhum e sem enviar o formulário: o print é da tela
    # preenchida, e criar o POP de verdade sujaria o banco a cada rodada.
    page.get_by_text("O código HSM_[SIGLA]-[NNN] é gerado pelo sistema").click()
    page.wait_for_timeout(400)
    modal = page.get_by_role("heading", name="Criar novo POP").locator(
        "xpath=ancestor::div[contains(@class,'rounded')][1]"
    )
    modal.screenshot(path=str(saida / "criar-novo-pop.png"))


def biblioteca(page: Page, base: str, saida: Path) -> None:
    """A Biblioteca: os POPs publicados por Setor, com o PDF assinado."""
    entrar(page, base)
    page.goto(f"{base}/pops/biblioteca", wait_until="networkidle")
    page.get_by_role("heading", name="Biblioteca").first.wait_for()
    # Recorte no alto da tela: a Biblioteca de exemplo tem um POP, e o resto da
    # janela sairia como uma faixa branca no meio da página do manual.
    page.screenshot(
        path=str(saida / "biblioteca.png"),
        clip={"x": 0, "y": 0, "width": 1440, "height": 560},
    )


def _id_do_pop(page: Page, base: str, codigo: str) -> str:
    """O identificador do POP de exemplo, lido da lista da tela."""
    page.goto(f"{base}/pops", wait_until="networkidle")
    linha = page.get_by_role("row").filter(has_text=codigo).first
    linha.get_by_role("link").first.wait_for()
    destino = linha.get_by_role("link").first.get_attribute("href") or ""
    return destino.split("/pops/")[1].split("/")[0]


def elaboracao(page: Page, base: str, saida: Path) -> None:
    """A tela de elaboração: o POP vivo à esquerda e o Consultor de POPs."""
    entrar(page, base)
    pop_id = _id_do_pop(page, base, "HSM_CTI-002")
    page.goto(f"{base}/pops/{pop_id}/elaboracao", wait_until="networkidle")
    page.get_by_text("Consultor de POPs").wait_for()
    page.get_by_text("1. Identificação").wait_for()
    page.screenshot(path=str(saida / "elaboracao.png"))


def versao_em_revisao(page: Page, base: str, saida: Path) -> None:
    """A leitura da Versão com os botões da etapa de quem revisa."""
    entrar(page, base)
    pop_id = _id_do_pop(page, base, "HSM_CTI-001")
    page.goto(f"{base}/pops/{pop_id}/versao", wait_until="networkidle")
    page.get_by_role("button", name="Aprovar revisão").wait_for()
    page.screenshot(path=str(saida / "versao-em-revisao.png"))


def fluxograma(page: Page, base: str, saida: Path) -> None:
    """O palco do fluxograma, na seção de fluxograma da Versão.

    O desenho é a última seção do POP: rolar até o título dela é o que põe o
    palco inteiro no print, e não o ícone do cabeçalho.
    """
    entrar(page, base)
    pop_id = _id_do_pop(page, base, "HSM_CTI-001")
    page.goto(f"{base}/pops/{pop_id}/versao", wait_until="networkidle")
    titulo = page.get_by_text("Fluxograma", exact=False).last
    titulo.wait_for()
    titulo.scroll_into_view_if_needed()
    page.mouse.wheel(0, 330)
    page.wait_for_timeout(2000)
    page.screenshot(path=str(saida / "fluxograma.png"))


PRINTS = {
    "gestao-de-pops": gestao_de_pops,
    "criar-novo-pop": criar_novo_pop,
    "biblioteca": biblioteca,
    "elaboracao": elaboracao,
    "versao-em-revisao": versao_em_revisao,
    "fluxograma": fluxograma,
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

POPS_DE_EXEMPLO = [
    ("HSM_CTI-001", 1, "CTI", "POP Higienização das Mãos", "CRITICA", "EM_REVISAO", "P901", "P900", "P902"),
    ("HSM_CTI-002", 2, "CTI", "POP Aspiração de Vias Aéreas", "ALTA", "EM_ELABORACAO", "P900", "P901", "P902"),
    ("HSM_CC-001", 1, "CC", "POP Cirurgia Segura", "CRITICA", "EM_VALIDACAO", "P901", "P902", "P900"),
    ("HSM_FARM-001", 1, "FARM", "POP Dispensação de Medicamentos Potencialmente Perigosos", "CRITICA", "PUBLICADO", "P902", "P901", "P900"),
    ("HSM_FARM-002", 2, "FARM", "POP Recebimento de Medicamentos", "MEDIA", "A_ELABORAR", "P900", "P901", "P902"),
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
