"""Testes do backend em paralelo, com a lista de rodar sozinho (issue #971).

O job de backend do `ci.yml` roda a suíte com `pytest-xdist` (`-n auto`). Teste
que só falha em paralelo não ganha retry: ganha o marcador `rodar_sozinho` e
roda num passo serial à parte, depois do paralelo. Retry esconderia a
instabilidade, e um teste instável que passa na segunda tentativa vira verde
sobre nada.

Estes testes leem o `ci.yml` e o `pyproject.toml` como dado: os dois passos
existem, todo `pytest` do job é um deles, e não há retry em lugar nenhum.
"""

from __future__ import annotations

import re
import shlex
import tomllib
from pathlib import Path

import yaml

RAIZ = Path(__file__).resolve().parent.parent
CI = RAIZ / ".github" / "workflows" / "ci.yml"
BACKEND = RAIZ / "hospital-reunioes" / "backend"
PYPROJECT = BACKEND / "pyproject.toml"
LOCK = BACKEND / "uv.lock"

MARCADOR = "rodar_sozinho"
# Plugins e flags que repetem teste que falhou. Nenhum pode existir.
RETRY = ("rerunfailures", "pytest-retry", "flaky", "--reruns", "--lf", "--last-failed", "retry")


def passos_do_backend() -> list[dict]:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["backend"]["steps"]


def chamadas_do_pytest() -> list[tuple[str, list[str]]]:
    """(nome do passo, argumentos) de cada `pytest` que o job de backend roda."""
    chamadas = []
    for passo in passos_do_backend():
        for linha in str(passo.get("run", "")).splitlines():
            palavras = shlex.split(linha, comments=True)
            if palavras and palavras[0] == "pytest":
                chamadas.append((passo.get("name", ""), palavras[1:]))
    return chamadas


def filtro(args: list[str]) -> str | None:
    return args[args.index("-m") + 1] if "-m" in args else None


def paralela(args: list[str]) -> bool:
    return "-n" in args or any(a.startswith(("-n", "--numprocesses")) for a in args)


def pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_a_suite_roda_em_paralelo_sem_a_lista_de_rodar_sozinho():
    paralelas = [(nome, a) for nome, a in chamadas_do_pytest() if paralela(a)]
    assert len(paralelas) == 1, chamadas_do_pytest()
    _, args = paralelas[0]
    assert args[args.index("-n") + 1] == "auto", args
    assert filtro(args) == f"not {MARCADOR}", args


def test_a_lista_de_rodar_sozinho_roda_num_passo_serial_a_parte_depois_do_paralelo():
    chamadas = chamadas_do_pytest()
    seriais = [(nome, a) for nome, a in chamadas if filtro(a) == MARCADOR]
    assert len(seriais) == 1, chamadas
    nome_serial, args = seriais[0]
    assert not paralela(args), args
    nomes = [nome for nome, _ in chamadas]
    nome_paralelo = next(nome for nome, a in chamadas if paralela(a))
    assert nome_serial != nome_paralelo
    assert nomes.index(nome_paralelo) < nomes.index(nome_serial), nomes


def test_todo_pytest_do_job_e_o_paralelo_ou_o_serial():
    """Um terceiro `pytest` sem filtro rodaria a suíte de novo (ou a lista em
    paralelo), e o marcador deixaria de valer."""
    filtros = sorted(filtro(a) or "" for _, a in chamadas_do_pytest())
    assert filtros == sorted([f"not {MARCADOR}", MARCADOR]), chamadas_do_pytest()


def test_lista_vazia_nao_reprova_o_passo_serial():
    """Sem teste marcado o pytest sai com 5 (nada coletado). Lista vazia é o
    estado bom, então o passo serial aceita o 5 e só ele."""
    nome = next(nome for nome, a in chamadas_do_pytest() if filtro(a) == MARCADOR)
    script = next(p["run"] for p in passos_do_backend() if p.get("name") == nome)
    assert "set +e" in script, script
    assert re.search(r'"\$\w+" -eq 5 \]; then exit 0', script), script


def test_nenhum_retry_automatico_no_job_nem_nas_dependencias():
    job = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]["backend"]
    assert "continue-on-error" not in job
    for passo in job["steps"]:
        assert "continue-on-error" not in passo, passo
        texto = f"{passo.get('uses', '')}\n{passo.get('run', '')}".lower()
        for termo in RETRY:
            assert termo not in texto, (termo, passo.get("name"))
    dev = " ".join(pyproject()["project"]["optional-dependencies"]["dev"]).lower()
    addopts = str(pyproject()["tool"]["pytest"]["ini_options"].get("addopts", "")).lower()
    lock = LOCK.read_text(encoding="utf-8").lower()
    for termo in ("rerunfailures", "pytest-retry", "flaky"):
        assert termo not in dev, termo
        assert f'name = "{termo}' not in lock, termo
    assert "reruns" not in addopts, addopts


def test_xdist_no_extra_de_dev_e_marcador_registrado():
    dev = pyproject()["project"]["optional-dependencies"]["dev"]
    assert any(d.startswith("pytest-xdist") for d in dev), dev
    marcadores = pyproject()["tool"]["pytest"]["ini_options"].get("markers", [])
    assert any(m.startswith(f"{MARCADOR}:") for m in marcadores), marcadores
    assert 'name = "pytest-xdist"' in LOCK.read_text(encoding="utf-8")
