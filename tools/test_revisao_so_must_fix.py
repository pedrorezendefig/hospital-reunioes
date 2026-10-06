"""O gatilho de segurança por PR: `sensivel.py` e a lista `revisao-sensivel.txt` (ADR 0064).

O `hr-revisor-seguranca` só roda em rota sem login ou migration. Estes testes
provam que a lista cobre o que a varredura do `sensivel.py` acha hoje e que o
script falha fechado.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"


def ler(caminho: Path) -> str:
    return caminho.read_text(encoding="utf-8")


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

