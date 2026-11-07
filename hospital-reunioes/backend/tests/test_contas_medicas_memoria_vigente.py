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


# ═══════════════════════════════════════════════════════════════════════════
# 2. A troca que dá certo continua deixando a nova vigente, e só ela
# ═══════════════════════════════════════════════════════════════════════════


class TestATrocaQueDaCerto:
    def test_importar_e_editar_deixam_a_versao_nova_vigente_com_uma_so_por_operadora(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        _importar(cliente, "MEMORIA-BETA-v1.0.md")
        _importar(cliente, "MEMORIA-ALFA-v1.1.md", _v11())
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}

        resposta = cliente.put(
            _regra("ALFA", "ALFA-DIA-01"),
            json={"texto": DIA_01_DEPOIS, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
        )

        assert resposta.status_code == 200, resposta.text
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": False, "1.2": True}
        assert _versoes(banco, "BETA") == {"1.0": True}, "a troca da ALFA não mexe na BETA"
        assert sorted(len(v) for v in _vigentes(banco).values()) == [1, 1]
        assert memoria_vigente(banco, _operadora_id(banco, "ALFA"))["versao"] == "1.2"


# ═══════════════════════════════════════════════════════════════════════════
# 3. O que o banco de verdade faz mora no SQL da migration
# ═══════════════════════════════════════════════════════════════════════════


def _sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


def _migration_da_funcao() -> str:
    """O SQL da migration que cria a função, achada por varredura: renumerar
    migration é rotina entre sessões paralelas."""
    achados = [
        arquivo
        for arquivo in sorted(MIGRATIONS.glob("*.sql"))
        if re.search(
            rf"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?{FUNCAO}\s*\(",
            _sem_comentarios(arquivo.read_text(encoding="utf-8")),
            re.IGNORECASE,
        )
    ]
    assert len(achados) == 1, f"a função precisa nascer em UMA migration só: {[a.name for a in achados]}"
    return _sem_comentarios(achados[0].read_text(encoding="utf-8"))


def _corpo(sql: str) -> str:
    achado = re.search(r"AS\s+\$\$(.*?)\$\$", sql, re.DOTALL)
    assert achado, "a função não tem corpo $$ ... $$"
    return achado.group(1)


class TestOSQLDaFuncao:
    def test_desmarca_a_antiga_e_marca_a_nova_dentro_do_mesmo_corpo_sem_bloco_exception(self):
        corpo = _corpo(_migration_da_funcao())

        escritas = re.findall(r"UPDATE\s+cm_memoria_versao\s+SET\s+vigente\s*=\s*(\w+)", corpo, re.IGNORECASE)
        assert [e.lower() for e in escritas] == ["false", "true"]
        assert not re.search(r"\bEXCEPTION\s+WHEN\b", corpo, re.IGNORECASE)

    def test_recusa_versao_de_outra_operadora(self):
        corpo = _corpo(_migration_da_funcao())

        guarda = re.search(r"IF\s+NOT\s+EXISTS\s*\((.*?)\)\s*THEN\s+RAISE\s+EXCEPTION", corpo, re.DOTALL | re.I)
        assert guarda, "sem RAISE para a versão que não é da operadora"
        assert re.search(r"\bid\s*=\s*p_versao_id", guarda.group(1))
        assert re.search(r"\boperadora_id\s*=\s*p_operadora_id", guarda.group(1))

    def test_security_invoker_e_execute_so_para_a_service_role(self):
        sql = _migration_da_funcao()

        assert re.search(r"\bSECURITY\s+INVOKER\b", sql, re.IGNORECASE)
        assert not re.search(r"\bSECURITY\s+DEFINER\b", sql, re.IGNORECASE)
        revoke = re.search(
            rf"REVOKE\s+EXECUTE\s+ON\s+FUNCTION\s+{FUNCAO}\s*\(\s*UUID\s*,\s*UUID\s*\)\s+FROM\s+([^;]+);", sql, re.I
        )
        assert revoke, "o REVOKE não fecha a assinatura (UUID, UUID) que o CREATE declara"
        assert {r.strip().lower() for r in revoke.group(1).split(",")} == {"public", "anon", "authenticated"}
        grants = re.findall(rf"GRANT\s+EXECUTE\s+ON\s+FUNCTION\s+{FUNCAO}\s*\([^)]*\)\s+TO\s+([^;]+);", sql, re.I)
        assert [g.strip().lower() for g in grants] == ["service_role"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Ninguém mais no backend escreve `vigente` em cm_memoria_versao
# ═══════════════════════════════════════════════════════════════════════════

_ESCRITA_DA_VIGENTE = re.compile(r"""\.update\(\s*\{[^}]*["']vigente["']""")


def _escritas_da_vigente(codigo: str) -> list[str]:
    return _ESCRITA_DA_VIGENTE.findall(codigo)


class TestNenhumaOutraEscrita:
    def test_o_detector_pega_o_update_de_vigente_e_deixa_o_filtro_passar(self):
        antes = 'supabase.table("cm_memoria_versao").update({"vigente": False}).eq("id", x).execute()'
        assert _escritas_da_vigente(antes)
        assert _escritas_da_vigente("t.update(\n    {'texto_md': t, 'vigente': True}\n)")
        assert not _escritas_da_vigente('supabase.table("x").update({"texto_md": t}).eq("vigente", True)')

    def test_nenhum_arquivo_do_backend_faz_update_de_vigente(self):
        achados: dict[str, Any] = {}
        for arquivo in sorted((BACKEND / "app").rglob("*.py")):
            escritas = _escritas_da_vigente(arquivo.read_text(encoding="utf-8"))
            if escritas:
                achados[str(arquivo.relative_to(BACKEND))] = escritas
        assert achados == {}, "a vigente só se troca pela função cm_trocar_memoria_vigente"
