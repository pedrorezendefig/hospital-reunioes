"""A guarda do Roteiro de prints de Contas médicas: só escreve no banco local.

O `--semear` apaga e recria contas, atendimentos e envios. Contra o banco de
produção isso seria apagar conta de faturista de verdade, então toda escrita
passa por `_rest`, que pergunta ao `.env` antes de abrir a conexão.

O teste mede o comportamento: com um `.env` apontando para fora da máquina, o
`semear` para antes de qualquer requisição sair (o dublê de `urlopen` registra
cada tentativa).

Prova por mutação: trocar a chamada de `_credenciais_locais()` dentro de
`_rest` por credenciais fixas faz `test_cada_escrita_pergunta_ao_env_antes`
falhar, porque a requisição chega ao dublê de `urlopen`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROTEIRO = Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "contas-medicas.py"


def carregar_roteiro():
    spec = importlib.util.spec_from_file_location("prints_contas_medicas", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def escrever_env(pasta: Path, url: str) -> Path:
    env = pasta / ".env"
    env.write_text(f"SUPABASE_URL={url}\nSUPABASE_SERVICE_ROLE_KEY=chave-falsa\n", encoding="utf-8")
    return env


@pytest.fixture
def chamadas(monkeypatch):
    registro: list[str] = []

    def urlopen_dubles(req, timeout=None):
        registro.append(getattr(req, "full_url", str(req)))
        raise AssertionError("o roteiro abriu conexão")

    monkeypatch.setattr("urllib.request.urlopen", urlopen_dubles)
    return registro


@pytest.mark.parametrize("url", ["https://abcd.supabase.co", "https://db.exemplo.invalid"])
def test_semear_nao_abre_conexao_fora_do_banco_local(tmp_path, monkeypatch, chamadas, url):
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, url))
    monkeypatch.setattr(roteiro, "_login_de_exemplo", lambda email: "id-falso")
    with pytest.raises(SystemExit, match="não é o Supabase local"):
        roteiro.semear()
    assert chamadas == []


def test_cada_escrita_pergunta_ao_env_antes(tmp_path, monkeypatch, chamadas):
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, "https://abcd.supabase.co"))
    with pytest.raises(SystemExit, match="não é o Supabase local"):
        roteiro._rest("cm_conta?faturista_id=eq.P950", "DELETE")
    assert chamadas == []


def test_aceita_o_banco_local(tmp_path, monkeypatch):
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, "http://127.0.0.1:54351"))
    assert roteiro._credenciais_locais() == ("http://127.0.0.1:54351", "chave-falsa")
