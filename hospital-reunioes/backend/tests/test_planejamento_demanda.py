"""Planejamento da Demanda: a primeira pergunta ponta a ponta (issue #1345, PRD #1344, ADR 0075).

O botão "Planejar com a IA" abre uma conversa em que a IA faz as perguntas de
negócio, uma por vez, com duas opções e a recomendada marcada. Aqui:

* **A migration 123**, lida do disco: as duas tabelas e o RLS default-deny.
* **O turno**, direto no serviço, com o cliente da Anthropic dublado no molde
  de `test_assistente_tecnologia` (troca `ai_processor._get_llm`). Nenhum teste
  chega à API de verdade: o `_llm_provider` nasce em mock em todo teste, e a
  trava de rede da suíte (`conftest.py`) reprova quem tentar.
* **As rotas**, pelo router de verdade, com o Supabase dublado do
  `test_tecnologia_vinculo` (o mesmo cenário que os testes dos Anexos usam).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_123 = MIGRATIONS / "123_tecnologia_planejamento.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 123
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_123.read_text(encoding="utf-8")


def _colunas_da_tabela(sql: str, tabela: str) -> dict[str, str]:
    """Coluna -> o resto da linha que a declara."""
    bloco = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\);", sql, flags=re.DOTALL)
    assert bloco, f"a 123 nao cria {tabela}"
    colunas = {}
    for linha in bloco.group(1).splitlines():
        partes = linha.strip().split(None, 1)
        if partes and partes[0][0].isalpha() and partes[0].upper() != "CHECK":
            colunas[partes[0]] = partes[1] if len(partes) > 1 else ""
    return colunas


class TestMigracao:
    def test_cria_o_planejamento_um_por_demanda(self):
        colunas = _colunas_da_tabela(_sql(), "tecnologia_planejamentos")

        assert {"demanda_id", "estado", "mensagens", "decisoes", "modelo", "criado_em", "atualizado_em"} <= set(
            colunas
        )
        # Um planejamento por Demanda: a unicidade mora no banco.
        assert "UNIQUE" in colunas["demanda_id"]
        assert "REFERENCES tecnologia_demandas(id)" in colunas["demanda_id"]
        assert colunas["mensagens"].startswith("JSONB")
        assert colunas["decisoes"].startswith("JSONB")

    def test_cria_a_chamada_de_ia_da_tecnologia_no_molde_de_contas_medicas(self):
        colunas = _colunas_da_tabela(_sql(), "tecnologia_chamadas_ia")

        assert {
            "demanda_id",
            "modelo",
            "tokens_entrada",
            "tokens_saida",
            "tokens_cache",
            "custo_usd",
            "duracao_ms",
            "sucesso",
            "criado_em",
        } <= set(colunas)
        # O custo fica, mesmo que a Demanda saia.
        assert "ON DELETE SET NULL" in colunas["demanda_id"]

    def test_rls_default_deny_nas_duas_tabelas(self):
        sql = _sql()

        for tabela in ("tecnologia_planejamentos", "tecnologia_chamadas_ia"):
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela
        # Default-deny: quem le e escreve e o backend com a service_role.
        assert "CREATE POLICY" not in sql.upper()

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = "\n".join(linha for linha in _sql().splitlines() if not linha.startswith("--")).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (123) ON CONFLICT (numero) DO NOTHING;")


@pytest.fixture(autouse=True)
def _llm_em_mock(monkeypatch):
    """O pytest carrega o `.env` real (chave de PROD). Sem isto, qualquer teste
    que chegasse ao servico bateria no provedor de verdade."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield
