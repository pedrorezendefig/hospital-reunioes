"""A troca da memória vigente numa operação só (issue #1471, PRD #1415).

Em 05/11 a ASSIM ficou sem memória: a edição da ASSIM-PRI-09 desmarcou a
versão 3.18 e não chegou a marcar a 3.19, porque a troca eram dois `update`
separados. Daí em diante toda conta da ASSIM parou com CM-CFG-MEMORIA.

Desde a migration 125 a troca é a função `cm_trocar_memoria_vigente`, que
desmarca a antiga e marca a nova na mesma transação. O dublê do banco a serve
como o Postgres serve uma transação: se o passo que marca a nova falhar, a
antiga volta a ser a vigente. O que garante isso no banco de verdade é o SQL,
e os guardas no fim deste arquivo o leem.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from test_contas_medicas_memoria_tela import _cliente, _importar, _operadora_id, _regra, _versoes
from test_contas_medicas_operadoras import GESTAO, _Banco, _erro, _memoria

from app.services.contas_medicas.memoria import ler_memoria
from app.services.contas_medicas.operadoras import importar_memoria, memoria_vigente

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS = BACKEND.parent / "supabase" / "migrations"
FUNCAO = "cm_trocar_memoria_vigente"

DIA_01_DEPOIS = "A diária começa em qualquer horário, vence às 12h e é sempre integral."


class _BancoQueCaiAoMarcarANova(_Banco):
    """O 05/11 reproduzido: depois de ligado, o passo que marca a versão nova
    como vigente falha (rede, timeout do PostgREST, restart do container)."""

    def __init__(self):
        super().__init__()
        self.cair = False

    def atualizar(self, tabela: str, linha: dict, mudancas: dict) -> None:
        if self.cair and tabela == "cm_memoria_versao" and mudancas.get("vigente") is True:
            raise _erro("57014", "canceling statement due to statement timeout")
        super().atualizar(tabela, linha, mudancas)


def _v11() -> str:
    v11 = _memoria("MEMORIA-ALFA-v1.0.md").replace('versao_memoria: "1.0"', 'versao_memoria: "1.1"')
    assert v11.count('versao_memoria: "1.1"') == 1, "a fixture mudou: refazer a v1.1"
    return v11


def _vigentes(banco: _Banco) -> dict[str, list[str]]:
    """Por operadora, as versões marcadas como vigentes."""
    por_operadora: dict[str, list[str]] = {}
    for versao in banco.linhas("cm_memoria_versao"):
        if versao["vigente"]:
            por_operadora.setdefault(versao["operadora_id"], []).append(versao["versao"])
    return por_operadora


# ═══════════════════════════════════════════════════════════════════════════
# 1. A troca que falha não deixa a operadora sem memória
# ═══════════════════════════════════════════════════════════════════════════


class TestATrocaQueFalha:
    def test_importar_com_a_troca_falhando_deixa_a_versao_anterior_vigente(self):
        banco = _BancoQueCaiAoMarcarANova()
        v10 = _memoria("MEMORIA-ALFA-v1.0.md")
        importar_memoria(banco, ler_memoria(v10), v10, None)
        oid = _operadora_id(banco, "ALFA")
        banco.cair = True

        with pytest.raises(APIError):
            importar_memoria(banco, ler_memoria(_v11()), _v11(), None)

        assert _versoes(banco, "ALFA") == {"1.0": True, "1.1": False}
        vigente = memoria_vigente(banco, oid)
        assert vigente is not None, "a operadora ficou sem memória, como a ASSIM em 05/11"
        assert vigente["versao"] == "1.0"

    def test_editar_regra_com_a_troca_falhando_deixa_a_versao_anterior_vigente(self):
        banco = _BancoQueCaiAoMarcarANova()
        cliente, _ = _cliente(GESTAO, banco)
        _importar(cliente)
        banco.cair = True

        resposta = TestClient(cliente.app, raise_server_exceptions=False).put(
            _regra("ALFA", "ALFA-DIA-01"),
            json={"texto": DIA_01_DEPOIS, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
        )

        assert resposta.status_code == 500
        assert _versoes(banco, "ALFA") == {"1.0": True, "1.1": False}
        assert memoria_vigente(banco, _operadora_id(banco, "ALFA"))["versao"] == "1.0"
