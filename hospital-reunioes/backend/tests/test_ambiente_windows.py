"""A suíte e os scripts do repo rodam numa máquina Windows (issue #844).

Toda onda rodada no Windows pagou o mesmo pedágio: falhas que só existem lá
(módulo `resource`, `pgrep`, `SIGKILL`, `sendmsg`, `read_text()` caindo em
cp1252) e scripts que só andavam com `PYTHONUTF8=1`. Cada agente redescobria e
escrevia o próprio contorno fora do repo.

O CI é Linux, então estes testes não rodam no Windows de verdade: eles provam
as regras que fazem o Windows funcionar, e que o Linux não perde nada com elas.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import conftest
import pytest


class _ItemDeMentira:
    """O mínimo de um `pytest.Item` que a regra do `so_unix` consulta."""

    def __init__(self, *marcas: pytest.MarkDecorator) -> None:
        self._marcas = [m.mark for m in marcas]
        self.acrescentadas: list[pytest.Mark] = []

    def get_closest_marker(self, nome: str):
        return next((m for m in self._marcas if m.name == nome), None)

    def add_marker(self, marca: pytest.MarkDecorator) -> None:
        self.acrescentadas.append(marca.mark)


class TestSoUnix:
    def test_no_windows_o_teste_marcado_vira_skip_com_o_motivo(self):
        item = _ItemDeMentira(pytest.mark.so_unix("mede RSS pelo ps"))

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="win32")

        assert [m.name for m in item.acrescentadas] == ["skip"]
        assert "mede RSS pelo ps" in item.acrescentadas[0].kwargs["reason"]

    def test_no_linux_o_teste_marcado_continua_rodando(self):
        """O CI é Linux: a marca não pode tirar teste nenhum de lá."""
        item = _ItemDeMentira(pytest.mark.so_unix("mede RSS pelo ps"))

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="linux")

        assert item.acrescentadas == []

    def test_no_windows_o_teste_sem_marca_continua_rodando(self):
        item = _ItemDeMentira()

        conftest._pular_o_que_so_roda_no_unix([item], plataforma="win32")

        assert item.acrescentadas == []


# O que só existe no Unix e já mordeu no Windows. Arquivo de teste que usa um
# destes precisa declarar `so_unix` em algum lugar, senão a falha volta a ser
# "de ambiente" e todo agente no Windows aprende de novo a ignorá-la.
SINAIS_SO_UNIX = ("import resource", "pgrep", "signal.SIGKILL", ".sendmsg(")
PASTA_DOS_TESTES = Path(__file__).resolve().parent


def test_todo_arquivo_que_usa_recurso_so_do_unix_declara_so_unix():
    proprios = {"conftest.py", Path(__file__).name}

    sem_marca = []
    for arquivo in sorted(PASTA_DOS_TESTES.glob("test_*.py")):
        if arquivo.name in proprios:
            continue
        texto = arquivo.read_text(encoding="utf-8")
        usados = [s for s in SINAIS_SO_UNIX if s in texto]
        if usados and "pytest.mark.so_unix(" not in texto:
            sem_marca.append(f"{arquivo.name}: {', '.join(usados)}")

    assert sem_marca == [], f"usa recurso só do Unix e não marca com so_unix: {sem_marca}"


def _leituras_e_escritas_sem_encoding(codigo: str) -> list[int]:
    """As linhas de `read_text`, `write_text` e `open` em modo texto sem
    `encoding`. Sem ele o Python usa a codificação do sistema, que no Windows
    é cp1252, e o arquivo com acento quebra ou sai trocado."""
    linhas = []
    for no in ast.walk(ast.parse(codigo)):
        if not isinstance(no, ast.Call) or any(k.arg == "encoding" for k in no.keywords):
            continue
        funcao = no.func
        if isinstance(funcao, ast.Attribute) and funcao.attr in ("read_text", "write_text"):
            linhas.append(no.lineno)
        elif isinstance(funcao, ast.Name) and funcao.id == "open":
            modo = no.args[1] if len(no.args) > 1 else next((k.value for k in no.keywords if k.arg == "mode"), None)
            binario = isinstance(modo, ast.Constant) and "b" in str(modo.value)
            if not binario:
                linhas.append(no.lineno)
    return linhas


def test_o_detector_de_encoding_pega_os_tres_jeitos_e_poupa_o_binario():
    """Sem esta prova, um detector que nunca acha nada passaria no teste de baixo."""
    codigo = (
        "p.read_text()\n"
        "p.write_text('á')\n"
        "open(caminho)\n"
        "open(caminho, 'rb')\n"
        "p.read_text(encoding='utf-8')\n"
        "open(caminho, 'w', encoding='utf-8')\n"
    )

    assert _leituras_e_escritas_sem_encoding(codigo) == [1, 2, 3]


def test_os_testes_leem_e_escrevem_arquivo_em_utf8():
    sem_encoding = []
    for arquivo in sorted(PASTA_DOS_TESTES.glob("*.py")):
        for linha in _leituras_e_escritas_sem_encoding(arquivo.read_text(encoding="utf-8")):
            sem_encoding.append(f"{arquivo.name}:{linha}")

    assert sem_encoding == [], f'passe encoding="utf-8": {sem_encoding}'


RAIZ_DO_REPO = PASTA_DOS_TESTES.parents[2]


def test_snapshot_do_vitest_sai_do_git_com_lf_em_qualquer_maquina():
    """O vitest grava o `.snap` com LF. Com `core.autocrlf=true` (o padrão do
    Git no Windows) o checkout vinha com CRLF, o vitest regravava, e o arquivo
    aparecia modificado em todo worktree, com diff de conteúdo vazio."""
    snaps = subprocess.run(
        ["git", "ls-files", "*.snap"], cwd=RAIZ_DO_REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    assert snaps, "o repo não tem mais .snap: o teste perdeu o objeto"

    eol = subprocess.run(
        ["git", "check-attr", "eol", "--", *snaps], cwd=RAIZ_DO_REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    assert eol == [f"{snap}: eol: lf" for snap in snaps]


SNAPSHOT = RAIZ_DO_REPO / ".claude" / "skills" / "snapshot" / "scripts" / "snapshot.py"


def _repo_minimo(raiz: Path) -> Path:
    """O bastante para o `snapshot.py --check` rodar e imprimir a moldura."""
    (raiz / "docs" / "spec" / "deploy").mkdir(parents=True)
    (raiz / "docs" / "spec" / "snapshots").mkdir(parents=True)
    (raiz / "docs" / "spec" / "deploy" / "project.json").write_text(
        json.dumps({"project": {"name": "Projeto"}, "services": []}), encoding="utf-8"
    )
    return raiz


def test_snapshot_imprime_a_moldura_num_console_cp1252(tmp_path):
    """O console do Windows é cp1252, e o `═` da moldura não existe nele.
    `PYTHONIOENCODING=cp1252` reproduz esse console em qualquer máquina; sem o
    `reconfigure` o script morria com `UnicodeEncodeError` no primeiro `print`."""
    repo = _repo_minimo(tmp_path)
    ambiente = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    ambiente.update(PYTHONIOENCODING="cp1252", PYTHONUTF8="0")

    processo = subprocess.run(
        [sys.executable, str(SNAPSHOT), "--root", str(repo), "--check"],
        capture_output=True,
        env=ambiente,
        timeout=120,
    )

    assert processo.returncode == 0, processo.stderr.decode("utf-8", "replace")[-600:]
    assert "═══ /snapshot --check" in processo.stdout.decode("utf-8")


def test_snapshot_decodifica_em_utf8_tudo_que_le_de_subprocesso():
    """`text=True` sem `encoding` decodifica pela codificação do sistema: no
    Windows, o `git show` de um router com acento sai trocado ou quebra."""
    sem_encoding = [
        no.lineno
        for no in ast.walk(ast.parse(SNAPSHOT.read_text(encoding="utf-8")))
        if isinstance(no, ast.Call)
        and any(k.arg == "text" for k in no.keywords)
        and not any(k.arg == "encoding" for k in no.keywords)
    ]

    assert sem_encoding == [], f'passe encoding="utf-8" nas linhas {sem_encoding} do snapshot.py'


BACKEND = PASTA_DOS_TESTES.parent


def _carregar_snapshot():
    """O script vive fora do pacote do backend (é script de skill)."""
    spec = importlib.util.spec_from_file_location("snapshot_do_ambiente_windows", SNAPSHOT)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _backend_sem_env(raiz: Path) -> Path:
    """Uma cópia do backend sem `hospital-reunioes/.env`, que é o worktree
    novo. Cópia do `app/`, e não link: o `config.py` acha o `.env` pelo
    próprio caminho resolvido, e um link o levaria ao `.env` desta máquina."""
    backend = raiz / "hospital-reunioes" / "backend"
    shutil.copytree(BACKEND / "app", backend / "app", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copy(BACKEND / ".env.example", backend / ".env.example")
    (backend / ".venv").symlink_to(BACKEND / ".venv")
    return backend


class TestSnapshotSemEnv:
    def test_sem_env_as_rotas_vem_do_app_montado(self, tmp_path, monkeypatch):
        """Sem `.env` a introspecção falhava no campo obrigatório do Settings e
        caía no parser AST, que não toca o ROTAS.md (saída 4). Os placeholders
        do `.env.example` bastam para o app montar e listar as rotas."""
        backend = _backend_sem_env(tmp_path)
        for chave in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "ENVIRONMENT"):
            monkeypatch.delenv(chave, raising=False)

        rotas = _carregar_snapshot()._introspect_routes_runtime(backend / "app" / "routers")

        assert rotas is not None, "a introspecção não rodou: o snapshot cairia no parser AST"
        assert ("GET", "/.well-known/oauth-protected-resource") in {(r["method"], r["path"]) for r in rotas}

    def test_com_env_o_placeholder_nao_passa_por_cima(self, tmp_path):
        """Variável de ambiente ganha do `.env` no pydantic: injetar o
        placeholder com o `.env` presente trocaria o valor real por `<PREENCHER>`."""
        backend = tmp_path / "hospital-reunioes" / "backend"
        backend.mkdir(parents=True)
        shutil.copy(BACKEND / ".env.example", backend / ".env.example")
        (backend.parent / ".env").write_text("SUPABASE_URL=http://127.0.0.1:54321\n", encoding="utf-8")

        assert _carregar_snapshot()._placeholders_sem_env(backend) == {}

    def test_sem_env_o_ambiente_e_development_e_nada_vem_de_fora_do_exemplo(self, tmp_path):
        backend = tmp_path / "hospital-reunioes" / "backend"
        backend.mkdir(parents=True)
        (backend / ".env.example").write_text(
            "# comentário\n\nSUPABASE_URL=<PREENCHER>\nENVIRONMENT=production\n", encoding="utf-8"
        )

        assert _carregar_snapshot()._placeholders_sem_env(backend) == {
            "SUPABASE_URL": "<PREENCHER>",
            "ENVIRONMENT": "development",
        }
