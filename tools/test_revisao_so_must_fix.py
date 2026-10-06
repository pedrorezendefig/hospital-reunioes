"""Revisor só de must-fix, uma rodada de correção, segurança por PRD (issue #988, ADR 0064).

Decisão 1: o veredito tem uma lista, must-fix (bug que o teste não pega, teste
vácuo, spec não cumprida, segredo, regressão de permissão), e uma rodada de
correção; a segunda revisão com must-fix tira a fatia da onda. Decisão 4: o
`hr-revisor-seguranca` só roda em rota sem login ou migration, uma vez, em
esforço high e sem ninguém esperar por ele; o resto da segurança é a lente do
`hr-auditor-prd` sobre o diff acumulado do PRD. Prompt é instrução que um
agente segue: estes testes leem os textos.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
AGENTES = RAIZ / ".claude" / "agents"

TEXTOS_DA_REVISAO = [
    AGENTES / "hr-revisor.md",
    AGENTES / "hr-revisor-seguranca.md",
    AGENTES / "hr-corretor.md",
    AGENTES / "hr-corretor-max.md",
    SKILLS / "onda-enxuta" / "SKILL.md",
    SKILLS / "onda-enxuta" / "references" / "prompts.md",
    SKILLS / "ship" / "SKILL.md",
]

# O que a ADR 0064 tirou do veredito.
FORA_DO_VEREDITO = re.compile(
    r"should[- ]fix|\bnits?\b|observa[çc][õo]es|issue futura|PEDE_REVISOR_SEGURANCA", re.I
)


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


def secao(md: str, titulo: str, nivel: str = "##") -> str:
    """De um `<nivel> <titulo>` até o próximo título do mesmo nível."""
    achado = re.search(rf"^{nivel} {re.escape(titulo)}.*?(?=^{nivel} |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


# ------------------------------------------- decisão 1: só must-fix

@pytest.mark.parametrize("caminho", TEXTOS_DA_REVISAO, ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhum_texto_da_revisao_pede_should_fix_nit_ou_observacao(caminho):
    achados = [
        f"{n}: {li.strip()[:140]}"
        for n, li in enumerate(ler(caminho).splitlines(), 1)
        if FORA_DO_VEREDITO.search(li)
    ]
    assert achados == [], "\n".join(achados)


def test_o_veredito_do_revisor_tem_uma_lista_so_de_must_fix():
    veredito = secao(ler(AGENTES / "hr-revisor.md"), "Veredito")
    assert "uma lista só" in veredito, veredito
    for categoria in (
        "bug que o teste não pega",
        "teste vácuo",
        "spec não cumprida",
        "segredo",
        "regressão de permissão",
    ):
        assert categoria in veredito, categoria
    assert "`VEREDITO: LIMPO`" in veredito and "`VEREDITO: MUST-FIX (n)`" in veredito, veredito


# ------------------------------------------- decisão 1: uma rodada de correção na onda

ONDA = SKILLS / "onda-enxuta" / "SKILL.md"


def passo_4_da_onda() -> str:
    return secao(ler(ONDA), "4. Por PR", "###")


def item(trecho: str, inicio: str) -> str:
    itens = [li for li in trecho.splitlines() if li.startswith(inicio)]
    assert len(itens) == 1, f"um item começando por {inicio!r}: {itens}"
    return itens[0]


def test_a_onda_corrige_uma_vez_e_a_segunda_revisao_com_must_fix_tira_a_fatia():
    assert not re.search(r"\b(2|duas|dois) rodadas", ler(ONDA), re.I)
    veredito = item(passo_4_da_onda(), "- **Veredito do `hr-revisor`**")
    assert "**Uma rodada de correção**" in veredito, veredito
    assert "rodada 2 com must-fix é baixa na hora" in veredito, veredito
    assert "--add-label ready-for-human" in veredito and "o que ficou" in veredito, veredito
    assert "o lote segue sem ela" in veredito, veredito


# ------------------------------------------- decisão 4: segurança por PRD

def test_a_onda_dispara_a_seguranca_uma_vez_e_ninguem_espera_por_ela():
    assert "e de segurança, se havia" not in ler(ONDA)
    passo = passo_4_da_onda()
    assert "**uma vez só**" in item(passo, "3. Dispare `hr-revisor`")

    veredito = item(passo, "- **Veredito do `hr-revisor`**")
    assert "sem esperar o veredito de segurança" in veredito, veredito
    assert "rodada 2 só do `hr-revisor`" in veredito, veredito

    seguranca = item(passo, "- **Veredito de segurança**")
    assert "não roda de novo depois da correção" in seguranca, seguranca
    assert "`hr-corretor`" in seguranca and "mesmo teto de 3 tentativas" in seguranca, seguranca

    papel = item(ler(ONDA), "| `hr-revisor-seguranca` |")
    assert papel.startswith("| `hr-revisor-seguranca` | high |"), papel
    assert "rota sem login" in papel and "migration" in papel, papel


def test_o_revisor_de_seguranca_roda_em_high_so_em_rota_sem_login_e_migration():
    frente = ler(AGENTES / "hr-revisor-seguranca.md").split("---")[1]
    assert re.search(r"^effort: high$", frente, re.M), frente
    descricao = item(frente, "description:")
    assert "rota sem login" in descricao and "migration" in descricao, descricao
    assert not re.search(r"rota nova|middleware|\benv\b|workflows|revisor padrão", descricao), descricao


LISTA_SENSIVEL = SKILLS / "onda-enxuta" / "revisao-sensivel.txt"


def _globs_sensiveis() -> list[str]:
    linhas = (li.strip() for li in ler(LISTA_SENSIVEL).splitlines())
    return [li for li in linhas if li and not li.startswith("#")]


def _sensivel():
    import importlib.util

    spec = importlib.util.spec_from_file_location("sensivel", SKILLS / "onda-enxuta" / "scripts" / "sensivel.py")
    sensivel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sensivel)
    return sensivel


def _casa(caminho: str) -> bool:
    return any(_sensivel().casa(caminho, g.lstrip("+")) for g in _globs_sensiveis())


@pytest.mark.parametrize(
    "caminho",
    [
        "hospital-reunioes/supabase/migrations/115_qualquer.sql",
        # o gate de cada porta sem login vive fora do router
        "hospital-reunioes/backend/app/services/ouvidoria_triagem_email.py",
        "hospital-reunioes/backend/app/services/ouvidoria_setor_tokens.py",
        "hospital-reunioes/backend/app/services/aceite_service.py",
        "hospital-reunioes/backend/app/services/ouvidoria_anexos.py",
        "hospital-reunioes/backend/app/services/central_de_comando/conector_mcp.py",
        "hospital-reunioes/backend/app/services/clicksign_service.py",
        "hospital-reunioes/backend/app/dependencies.py",
        "hospital-reunioes/frontend/src/app/auth/callback/route.ts",
        "hospital-reunioes/frontend/src/app/actions/auth.ts",
        "hospital-reunioes/frontend/src/lib/login/destino.ts",
    ],
)
def test_a_seguranca_por_pr_dispara_em_migration_e_no_gate_das_portas_sem_login(caminho):
    assert (RAIZ / caminho).exists() or "migrations" in caminho, f"caminho velho no teste: {caminho}"
    assert _casa(caminho), caminho


APP = RAIZ / "hospital-reunioes" / "backend" / "app"
FRONT = RAIZ / "hospital-reunioes" / "frontend" / "src"


def _fontes_locais(raiz: Path) -> dict[str, str]:
    return {p.relative_to(raiz).as_posix(): p.read_text(encoding="utf-8") for p in raiz.rglob("*.py")}


def test_todo_router_com_rota_sem_login_esta_na_lista():
    sensivel = _sensivel()
    achados = sensivel.rotas_sem_login(_fontes_locais(APP))
    # piso: hoje são sete; varredura que volta quase vazia é varredura quebrada
    assert len(achados) >= 7 and sensivel.FORA_DA_LISTA <= achados.keys(), achados
    faltam = [
        f"{router}: {rotas}"
        for router, rotas in achados.items()
        if router not in sensivel.FORA_DA_LISTA and not _casa(f"hospital-reunioes/backend/app/{router}")
    ]
    assert faltam == [], "\n".join(faltam)


# Alvo de Depends das rotas abertas que não é gate (só entrega o cliente do banco).
NAO_E_GATE = {"get_supabase_client"}


def test_o_arquivo_que_define_cada_gate_das_rotas_sem_login_esta_na_lista():
    sensivel = _sensivel()
    fontes = _fontes_locais(APP)
    definido_em: dict[str, set[str]] = {}
    for caminho, codigo in fontes.items():
        for no in ast.parse(codigo).body:
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                definido_em.setdefault(no.name, set()).add(caminho)

    gates: set[str] = set()
    for router, rotas in sensivel.rotas_sem_login(fontes).items():
        arvore = ast.parse(fontes[router])
        for no in arvore.body:
            if isinstance(no, ast.Assign) and getattr(getattr(no.value, "func", None), "id", None) == "APIRouter":
                gates |= sensivel.depends(no.value)
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name in rotas:
                gates |= sensivel.depends(no.args) | set().union(*map(sensivel.depends, no.decorator_list))
    assert "require_ana_api_key" in gates, gates

    faltam = [
        f"{gate} em {arquivo}"
        for gate in sorted(gates - NAO_E_GATE)
        for arquivo in sorted(definido_em.get(gate, ()))
        if not _casa(f"hospital-reunioes/backend/app/{arquivo}")
    ]
    assert faltam == [], "\n".join(faltam)


def test_toda_porta_do_frontend_esta_na_lista():
    portas = [
        p.relative_to(RAIZ).as_posix()
        for p in FRONT.rglob("*")
        if p.suffix in {".ts", ".tsx"} and _sensivel().porta_do_front(p.name, p.read_text(encoding="utf-8"))
    ]
    # piso: o callback do login e as server actions do login
    assert len(portas) >= 2, portas
    assert [p for p in portas if not _casa(p)] == []


ROUTERS_DE_TESTE = {
    "dependencies.py": (
        "def get_current_user(c=Depends(bearer)): ...\n"
        "def require_admin(u=Depends(get_current_user)): ...\n"
        "def require_perfil(*p):\n"
        "    def checar(u=Depends(get_current_user)): ...\n"
        "    return checar\n"
        "def require_api_key(x=Header(None)): ...\n"
    ),
    "routers/aberta.py": "router = APIRouter()\n@router.post('/x')\ndef publica(dado: dict): ...\n",
    "routers/api_key.py": (
        "router = APIRouter(dependencies=[Depends(require_api_key)])\n@router.get('/x')\ndef so_chave(): ...\n"
    ),
    "routers/admin.py": "router = APIRouter()\n@router.get('/x')\ndef lista(u=Depends(require_admin)): ...\n",
    "routers/fabrica.py": "router = APIRouter()\n@router.get('/x')\ndef lista(u=Depends(require_perfil('a'))): ...\n",
    "routers/no_router.py": (
        "router = APIRouter(dependencies=[Depends(get_current_user)])\n@router.get('/x')\ndef lista(): ...\n"
    ),
    "routers/no_decorador.py": (
        "router = APIRouter()\n@router.get('/x', dependencies=[Depends(deps.require_admin)])\ndef lista(): ...\n"
    ),
    "routers/health.py": "router = APIRouter()\n@router.get('/health')\ndef health(): ...\n",
}


def test_a_varredura_segue_a_cadeia_de_depends():
    assert _sensivel().rotas_sem_login(ROUTERS_DE_TESTE) == {
        "routers/aberta.py": ["publica"],
        "routers/api_key.py": ["so_chave"],
        "routers/health.py": ["health"],
    }


def test_o_sensivel_varre_o_head_do_pr_e_acusa_rota_sem_login_fora_da_lista():
    """Router fora da lista com rota sem login dispara; com login, não (ADR 0064, decisão 4)."""
    sensivel = _sensivel()
    globs = sensivel.ler_globs(LISTA_SENSIVEL)
    pedidos = []

    def fontes_do_head(caminhos):
        pedidos.append(caminhos)
        fontes = {f"hospital-reunioes/backend/app/{k}": v for k, v in ROUTERS_DE_TESTE.items()}
        fontes["hospital-reunioes/frontend/src/app/api/x/route.ts"] = "export async function GET() {}\n"
        fontes["hospital-reunioes/frontend/src/app/acoes.ts"] = '"use server";\nexport async function f() {}\n'
        fontes["hospital-reunioes/frontend/src/app/tela.tsx"] = "export default function Tela() {}\n"
        return fontes

    arquivos = [
        {"filename": f"hospital-reunioes/backend/app/routers/{nome}", "status": "added"}
        for nome in ("aberta.py", "api_key.py", "admin.py", "no_decorador.py", "health.py")
    ] + [
        {"filename": "hospital-reunioes/frontend/src/app/api/x/route.ts", "status": "added"},
        {"filename": "hospital-reunioes/frontend/src/app/acoes.ts", "status": "modified"},
        {"filename": "hospital-reunioes/frontend/src/app/tela.tsx", "status": "modified"},
    ]
    acusados = [nome for nome, _ in sensivel.sensiveis(arquivos, globs, fontes_do_head)]
    assert acusados == [
        "hospital-reunioes/backend/app/routers/aberta.py",
        "hospital-reunioes/backend/app/routers/api_key.py",
        "hospital-reunioes/frontend/src/app/api/x/route.ts",
        "hospital-reunioes/frontend/src/app/acoes.ts",
    ], acusados

    # PR sem router nem código do frontend não busca o head
    pedidos.clear()
    so_texto = [
        {"filename": "docs/x.md", "status": "modified"},
        {"filename": "hospital-reunioes/backend/app/routers/aberta.py", "status": "removed"},
    ]
    assert sensivel.sensiveis(so_texto, globs, fontes_do_head) == [] and pedidos == []


def test_o_sensivel_le_o_head_pelo_git():
    fontes = _sensivel().fontes_do_commit("HEAD", ["hospital-reunioes/backend/app"], RAIZ)
    assert "hospital-reunioes/backend/app/routers/ana.py" in fontes, sorted(fontes)[:5]
    assert "require_ana_api_key" in fontes["hospital-reunioes/backend/app/dependencies.py"]


# ------------------------------------------- o sensivel.py falha fechado

CHAMADA_DO_SENSIVEL = 'uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py'
ROUTER_ABERTO = "router = APIRouter()\n@router.get('/x')\ndef publica(): ...\n"


def _pr_de_mentira(tmp_path: Path, router: str) -> tuple[Path, dict]:
    """Repo com o sensivel.py e um PR (migration + router) no head, e um `gh` falso no PATH.

    Roda o script como o fluxo roda: processo, `gh` para o PR, `git fetch` e `git archive` do head.
    """
    import json
    import os
    import shutil
    import subprocess

    repo = tmp_path / "repo"
    scripts = repo / ".claude" / "skills" / "onda-enxuta" / "scripts"
    scripts.mkdir(parents=True)
    shutil.copy(SKILLS / "onda-enxuta" / "scripts" / "sensivel.py", scripts)
    shutil.copy(LISTA_SENSIVEL, scripts.parent)
    arquivos = {
        "hospital-reunioes/supabase/migrations/200_x.sql": "select 1;\n",
        "hospital-reunioes/backend/app/routers/novo.py": router,
    }
    for nome, codigo in arquivos.items():
        (repo / nome).parent.mkdir(parents=True, exist_ok=True)
        (repo / nome).write_text(codigo, encoding="utf-8")

    def git(*argumentos: str) -> str:
        return subprocess.run(["git", "-C", str(repo), *argumentos], check=True, capture_output=True, text=True).stdout

    git("init", "-q")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-qm", "pr")
    git("remote", "add", "origin", str(repo))
    head = git("rev-parse", "HEAD").strip()

    (tmp_path / "files.json").write_text(json.dumps([{"filename": n, "status": "added"} for n in arquivos]))
    binario = tmp_path / "bin"
    binario.mkdir()
    gh = binario / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  "repo view"*) echo dono/repo ;;\n'
        f'  *"/files --paginate") cat "{tmp_path / "files.json"}" ;;\n'
        f"  *) echo {head} ;;\n"
        "esac\n"
    )
    gh.chmod(0o755)
    return repo, {**os.environ, "PATH": f"{binario}{os.pathsep}{os.environ['PATH']}"}


def _rodar_sensivel(python: str, repo: Path, ambiente: dict):
    import subprocess

    script = repo / ".claude" / "skills" / "onda-enxuta" / "scripts" / "sensivel.py"
    return subprocess.run([python, str(script), "7"], cwd=repo, env=ambiente, capture_output=True, text=True, check=False)


def test_o_sensivel_como_processo_acusa_migration_e_rota_sem_login_do_head(tmp_path):
    """Controle: com o head legível, o mesmo arranjo sai 0 (a saída 2 do teste abaixo não é do arranjo)."""
    import sys

    repo, ambiente = _pr_de_mentira(tmp_path, ROUTER_ABERTO)
    feito = _rodar_sensivel(sys.executable, repo, ambiente)
    assert feito.returncode == 0, feito.stderr
    assert "migrations/200_x.sql" in feito.stdout and "routers/novo.py" in feito.stdout, feito.stdout


def test_o_sensivel_falha_fechado_quando_a_varredura_quebra(tmp_path):
    """Router do head que não compila: a varredura levanta e a saída é 2, nunca 1 ("não sensível")."""
    import sys

    repo, ambiente = _pr_de_mentira(tmp_path, "def quebrado(:\n")
    feito = _rodar_sensivel(sys.executable, repo, ambiente)
    assert feito.returncode == 2, (feito.returncode, feito.stdout, feito.stderr)
    assert "SyntaxError" in feito.stderr, feito.stderr


def _python_antigo() -> str | None:
    import shutil
    import subprocess

    for candidato in ("/usr/bin/python3", "python3.9", "python3.10", "python3.11"):
        caminho = shutil.which(candidato)
        if not caminho:
            continue
        versao = subprocess.run(
            [caminho, "-c", "import sys; print(sys.version_info >= (3, 12))"], capture_output=True, text=True, check=False
        ).stdout.strip()
        if versao == "False":
            return caminho
    return None


@pytest.mark.skipif(_python_antigo() is None, reason="nenhum Python abaixo do 3.12 nesta máquina")
def test_o_sensivel_em_python_antigo_sai_2(tmp_path):
    repo, ambiente = _pr_de_mentira(tmp_path, ROUTER_ABERTO)
    feito = _rodar_sensivel(_python_antigo(), repo, ambiente)
    assert feito.returncode == 2, (feito.returncode, feito.stdout, feito.stderr)
    assert "3.12" in feito.stderr, feito.stderr


@pytest.mark.parametrize(
    "caminho, trecho",
    [
        (SKILLS / "onda-enxuta" / "SKILL.md", ("4. Por PR", "###")),
        (SKILLS / "ship" / "SKILL.md", ("Gate 2:", "###")),
    ],
    ids=["onda-enxuta", "ship"],
)
def test_o_fluxo_chama_o_sensivel_em_python_3_12_e_para_em_saida_fora_de_0_e_1(caminho, trecho):
    md = ler(caminho)
    assert not re.search(r"(?<!uv run --no-project --python \">=3\.12\" )python3? \.claude/skills/onda-enxuta/scripts/sensivel\.py", md), (
        "chamada do sensivel.py sem o Python 3.12+"
    )
    parte = secao(md, *trecho)
    assert CHAMADA_DO_SENSIVEL in parte, parte
    assert "qualquer outra saída" in parte.lower() and "não sensível" in parte, parte


@pytest.mark.parametrize(
    "caminho",
    [
        "hospital-reunioes/backend/app/routers/reunioes.py",
        "hospital-reunioes/backend/app/middleware/auth.py",
        "hospital-reunioes/backend/app/config.py",
        "hospital-reunioes/backend/.env.example",
        ".github/workflows/ci.yml",
        ".claude/agents/hr-revisor-seguranca.md",
        ".claude/skills/ship/SKILL.md",
    ],
)
def test_rota_com_login_middleware_env_workflow_e_o_fluxo_de_revisao_sairam_do_gatilho(caminho):
    assert not _casa(caminho), caminho


def test_rota_nova_saiu_do_gatilho():
    # o prefixo "+" disparava quando o PR criava um router qualquer
    assert [g for g in _globs_sensiveis() if g.startswith("+")] == []


def gate_do_ship(gate: str) -> str:
    return secao(secao(ler(SKILLS / "ship" / "SKILL.md"), "Passo 8 "), gate, "###")


def test_o_ship_dispara_a_seguranca_uma_vez_sem_esperar_e_o_spec_x_diff_so_traz_must_fix():
    gate1 = gate_do_ship("Gate 1:")
    assert "sem esperar o Gate 2" in gate1 and "só must-fix" in gate1, gate1

    gate15 = gate_do_ship("Gate 1.5")
    assert "só o que impede o merge" in gate15, gate15
    assert "scope creep" not in gate15.lower() and "sem travar" not in gate15, gate15

    gate2 = gate_do_ship("Gate 2:")
    assert gate2.splitlines()[0].endswith("(rota sem login ou migration)"), gate2.splitlines()[0]
    assert "**uma vez só**" in gate2 and "Ninguém espera por ele" in gate2, gate2
    assert "não roda de novo" in gate2, gate2
    assert "nova rodada do `hr-revisor-seguranca`" not in gate2, gate2


@pytest.mark.parametrize(
    "caminho",
    [ONDA, SKILLS / "ship" / "SKILL.md", RAIZ / "docs" / "onboarding" / "dev.md"],
    ids=lambda p: str(p.relative_to(RAIZ)),
)
def test_o_gatilho_de_seguranca_e_rota_sem_login_ou_migration_nos_textos_do_fluxo(caminho):
    linhas = [li for li in ler(caminho).splitlines() if "caminho sensível" in li]
    assert linhas == [], linhas


def test_o_auditor_do_prd_passa_a_lente_de_seguranca_no_diff_acumulado():
    auditor = ler(AGENTES / "hr-auditor-prd.md")
    lente = secao(auditor, "Segurança do diff acumulado")
    assert "uma rodada" in lente.lower(), lente
    # os PRs vêm de todas as sub-issues do PRD, não só das desta sessão
    prs = item(lente, "1. ")
    assert "issues/<PRD>/sub_issues --jq" in prs and "closedByPullRequestsReferences" in prs, prs
    assert "gh pr diff <PR>" in prs, prs
    assert "gh issue create" in lente and "must-fix" in lente, lente
    assert "`ready-for-agent`" in lente and "`ready-for-human` se for grave" in lente, lente
    assert "Segurança: MUST-FIX (n)" in secao(auditor, "Veredito"), "o comentário do PRD conta os achados"

    prompts = ler(SKILLS / "onda-enxuta" / "references" / "prompts.md")
    disparo = item(prompts, "PRD #<PRD>. Versão em produção")
    assert "lente de segurança no diff acumulado" in disparo, disparo
    papel = item(ler(ONDA), "| `hr-auditor-prd` |")
    assert "lente de segurança" in papel, papel


# ------------------------------------------- o must-fix de segurança é conferido

REVISOR = AGENTES / "hr-revisor.md"
LINHA_DO_VEREDITO = "Veredito de segurança a conferir: <URL do comentário>"


def test_a_rodada_seguinte_do_revisor_recebe_e_confere_o_veredito_de_seguranca():
    prompts = ler(SKILLS / "onda-enxuta" / "references" / "prompts.md")
    bloco = secao(prompts, "hr-revisor\n")
    assert LINHA_DO_VEREDITO in bloco, bloco

    revisor = ler(REVISOR)
    entrada = secao(revisor, "Entrada")
    assert "`Veredito de segurança a conferir: <URL>`" in entrada, entrada
    assert "issues/comments/" in entrada, entrada
    spec = item(secao(revisor, "Lentes"), "1. ")
    assert "cada must-fix do veredito de segurança a conferir" in spec, spec
    assert "sem teste que prove" in spec, spec

    seguranca = item(passo_4_da_onda(), "- **Veredito de segurança**")
    assert "`Veredito de segurança a conferir: <URL>`" in seguranca, seguranca
    gate2 = gate_do_ship("Gate 2:")
    assert "`Veredito de segurança a conferir: <URL>`" in gate2, gate2


RODADA_2_ESPERA_OS_CORRETORES = (
    "**só quando não houver corretor no PR**",
    "o de segurança inclusive",
    "com o `VEREDITO SEGURANCA:` já dado",
    "não há rodada 3",
)


def test_a_rodada_2_so_sai_depois_de_todo_corretor_e_do_veredito_de_seguranca():
    """O corretor de segurança e a rodada 2 saem do mesmo evento; a rodada 2 não corre com ele."""
    veredito = item(passo_4_da_onda(), "- **Veredito do `hr-revisor`**")
    gate1 = gate_do_ship("Gate 1:")
    for trecho in RODADA_2_ESPERA_OS_CORRETORES:
        assert trecho in veredito, trecho
        assert trecho in gate1, trecho
    assert "quando ele terminar, rodada 2" not in veredito + gate1

    seguranca = item(passo_4_da_onda(), "- **Veredito de segurança**")
    assert "quem confere é a rodada 2 do `hr-revisor`" in seguranca, seguranca
    assert "quem confere é a rodada 2 do Gate 1" in gate_do_ship("Gate 2:")


def test_afrouxar_o_proprio_fluxo_de_revisao_e_must_fix_do_revisor():
    lente = item(secao(ler(REVISOR), "Lentes"), "3. ")
    for trecho in (
        "afrouxa gatilho, gate, filtro de autor ou teto",
        "`.claude/agents/`",
        "`.claude/skills/ship/`",
        "`.claude/skills/onda-enxuta/`",
        "`revisao-sensivel.txt`",
        "`sensivel.py`",
        "`.claude/settings*.json`",
        "`.github/`",
        "sem a issue pedir",
        "é must-fix (regressão de permissão)",
    ):
        assert trecho in lente, trecho


def test_o_achado_de_seguranca_do_auditor_sai_neutro_no_repositorio_publico():
    lente = secao(ler(AGENTES / "hr-auditor-prd.md"), "Segurança do diff acumulado")
    achado = item(lente, "3. ")
    assert "`Segurança: correção no PRD #<PRD>`" in achado, achado
    assert "**sem arquivo, linha nem cenário**" in achado, achado
    assert "security-advisories" in achado and "rascunho" in achado, achado
    assert "`PushNotification`" in achado, achado
    assert "Segurança: <resumo>" not in lente, lente


def test_o_ship_avulso_e_a_issue_sem_prd_tambem_passam_pela_lente_do_auditor():
    gate2 = gate_do_ship("Gate 2:")
    lente = [li for li in gate2.splitlines() if li.startswith("**Lente do `hr-auditor-prd` no `/ship` avulso**")]
    assert len(lente) == 1, gate2
    for trecho in ("rabo verde", "última fatia aberta do PRD", "issue sem PRD", "`PR #<N>` no lugar do PRD"):
        assert trecho in lente[0], trecho

    entrada = secao(ler(AGENTES / "hr-auditor-prd.md"), "Entrada")
    assert "`PR #<N>` no lugar do PRD" in entrada, entrada

    prompts = ler(SKILLS / "onda-enxuta" / "references" / "prompts.md")
    disparo = item(prompts, "PR #<PR> (issue sem PRD).")
    assert "lente de segurança" in disparo, disparo

    papel = item(ler(ONDA), "| `hr-auditor-prd` |")
    assert "issue sem PRD" in papel and "`PR #<N>`" in papel, papel
