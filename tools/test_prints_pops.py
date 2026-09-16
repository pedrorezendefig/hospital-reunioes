"""Testes da guarda de banco do Roteiro de prints de POPs.

O roteiro do módulo POPs (`docs/manual/prints/pops.py`) não só lê tela: o
`--semear` cria login, concede perfil e grava POPs. O que separa isso de um
banco que não é o de desenvolvimento são as três linhas de
`_credenciais_locais`, que leem o `.env` e recusam toda URL que não seja
`127.0.0.1` ou `localhost`. É essa recusa que estes testes provam, com o
`.env` apontado para um arquivo temporário.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROTEIRO = (
    Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "pops.py"
)


def carregar_roteiro():
    """Importa o roteiro pelo caminho.

    Ele vive em `docs/manual/prints/`, fora de qualquer pacote, e não importa o
    Playwright no topo justamente para caber aqui.
    """
    spec = importlib.util.spec_from_file_location("roteiro_prints_pops", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def escrever_env(tmp_path: Path, url: str) -> Path:
    env = tmp_path / ".env"
    linhas = ["# comentário que o leitor ignora", "SUPABASE_SERVICE_KEY=chave-de-teste"]
    if url is not None:
        linhas.append(f"SUPABASE_URL={url}")
    env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return env


# Endereços de mentira de propósito: o repositório é público, e o que o teste
# precisa provar é que a guarda recusa qualquer hostname que não seja o da
# máquina, não qual é o endereço de verdade. O TLD `.invalid` é reservado pela
# RFC 2606 para exemplo e nunca resolve.
@pytest.mark.parametrize(
    "url",
    [
        "https://db.exemplo.invalid",
        "https://projeto.exemplo.invalid",
        "http://192.168.0.10:54321",
    ],
)
def test_recusa_banco_que_nao_e_o_local(tmp_path, monkeypatch, url):
    """Qualquer endereço fora da máquina para o roteiro antes de gravar nada."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, url))

    with pytest.raises(SystemExit) as erro:
        roteiro._credenciais_locais()

    # A mensagem inteira, não um pedaço dela: asserir só "recusado" sobrevive a
    # trocar a frase por outra que não diz qual endereço foi barrado.
    assert str(erro.value) == f"recusado: '{url}' não é o Supabase local."


def test_recusa_env_sem_supabase_url(tmp_path, monkeypatch):
    """Falha fechada: `.env` sem a URL não vira permissão para gravar."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, None))

    with pytest.raises(SystemExit) as erro:
        roteiro._credenciais_locais()

    assert str(erro.value) == "recusado: '' não é o Supabase local."


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:54351", "http://localhost:54321", "http://127.0.0.1:8000"]
)
def test_aceita_o_banco_local_e_devolve_as_credenciais(tmp_path, monkeypatch, url):
    """O caminho bom continua passando, com URL e chave lidas do arquivo."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, url))

    assert roteiro._credenciais_locais() == (url, "chave-de-teste")


def test_semear_para_no_primeiro_passo_quando_o_banco_nao_e_local(tmp_path, monkeypatch):
    """A guarda roda antes de qualquer escrita: `_rest` nem chega a ser chamado."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(
        roteiro, "ENV_LOCAL", escrever_env(tmp_path, "https://db.exemplo.invalid")
    )

    def nao_deve_gravar(*args, **kwargs):
        raise AssertionError("o roteiro gravou no banco com a guarda recusando")

    monkeypatch.setattr(roteiro, "_rest", nao_deve_gravar)
    monkeypatch.setattr(roteiro, "_login_de_exemplo", nao_deve_gravar)

    with pytest.raises(SystemExit):
        roteiro.semear()
