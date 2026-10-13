"""A IA de Contas médicas: a migration 117 e o adaptador (issue #1130, PRD #1128).

O adaptador é a única porta do módulo para a IA: toda chamada sai com saída
estruturada estrita, sem retenção do texto no provedor, com cache da instrução
e da memória quando o modelo é Anthropic, e com o custo gravado.

Os testes do adaptador conversam com o SDK de verdade e trocam só o transporte
HTTP (`httpx.MockTransport`): o que eles leem é o corpo JSON que sairia para o
OpenRouter, e nenhum deles chega à rede (a trava da suíte, `conftest.py`,
reprova quem tentar).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_117 = MIGRATIONS / "117_contas_medicas_ia.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 117
# ═══════════════════════════════════════════════════════════════════════════


def _sql() -> str:
    return MIGRATION_117.read_text(encoding="utf-8")


def _colunas_da_tabela(sql: str, tabela: str) -> set[str]:
    bloco = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\);", sql, flags=re.DOTALL)
    assert bloco, f"a 117 nao cria {tabela}"
    return {linha.split()[0] for linha in bloco.group(1).splitlines() if linha.strip() and linha.strip()[0].isalpha()}


def _valores_do_check(sql: str, constraint: str) -> set[str]:
    bloco = re.search(rf"ADD CONSTRAINT {constraint}\s+CHECK \((.*?)\);", sql, flags=re.DOTALL)
    assert bloco, f"a 117 nao refaz o CHECK {constraint}"
    return set(re.findall(r"'(\w+)'", bloco.group(1)))


class TestMigration117:
    def test_cria_a_chamada_de_ia_com_o_custo_de_cada_chamada(self):
        colunas = _colunas_da_tabela(_sql(), "cm_chamada_ia")

        assert {
            "conta_id",
            "atendimento_id",
            "passo",
            "modelo",
            "tokens_entrada",
            "tokens_saida",
            "tokens_cache",
            "custo_usd",
            "duracao_ms",
            "tentativas",
            "criado_em",
        } <= colunas

    def test_cria_a_linha_de_formulario_aprendida(self):
        assert {"familia", "linha", "contagem"} <= _colunas_da_tabela(_sql(), "cm_linha_formulario")

    def test_o_nivel_de_evidencia_aceita_prescrito_se_necessario(self):
        assert _valores_do_check(_sql(), "cm_guia_linha_nivel_evidencia_check") == {
            "REGISTRADO",
            "PRESCRITO",
            "PRESCRITO_SN",
            "POR_REGRA",
        }

    def test_a_conta_ganha_a_nota_de_saida_e_a_data_do_reenvio(self):
        sql = _sql()

        assert re.search(r"ALTER TABLE cm_conta\s+ADD COLUMN IF NOT EXISTS nota_saida NUMERIC", sql)
        assert re.search(r"ALTER TABLE cm_conta\s+ADD COLUMN IF NOT EXISTS reenviada_em TIMESTAMPTZ", sql)

    def test_o_dicionario_aceita_a_proposta_da_ia(self):
        sql = _sql()

        assert "PROPOSTO" in _valores_do_check(sql, "cm_item_dicionario_situacao_check")
        assert "IA" in _valores_do_check(sql, "cm_item_dicionario_origem_check")

    def test_indice_do_guia_por_causa_raiz_e_data(self):
        assert re.search(r"CREATE INDEX IF NOT EXISTS \w+\s+ON cm_guia_linha \(causa_raiz, data\)", _sql())

    def test_rls_nas_tabelas_novas(self):
        sql = _sql()

        for tabela in ("cm_chamada_ia", "cm_linha_formulario"):
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = "\n".join(linha for linha in _sql().splitlines() if not linha.startswith("--")).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (117) ON CONFLICT (numero) DO NOTHING;")
