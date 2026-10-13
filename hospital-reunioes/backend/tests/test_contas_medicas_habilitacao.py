"""A Habilitacao de Contas medicas e a migration 118 (issue #1139, PRD #1129).

A diretoria liga e desliga pela tela o que cada perfil do modulo pode fazer
(`cm_perfil_permissao`) e da ou tira o perfil de uma pessoa
(`participantes.perfil_contas_medicas`). Cada mudanca fica em `cm_registro`,
com autor, data, antes e depois. O guard le a matriz a cada requisicao: quem
perde a permissao recebe 403 ja na seguinte.

A matriz do duble do banco e lida da migration 116, como no teste da fundacao:
o que o teste confere e o que o Studio gravou.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_118 = MIGRATIONS / "118_contas_medicas_gestao.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 118
# ═══════════════════════════════════════════════════════════════════════════

# As tabelas das decisoes de implementacao do PRD #1129, escritas a mao.
TABELAS_DA_118 = (
    "cm_regra_historico",
    "cm_validacao_tema",
    "cm_validacao_tema_linha",
    "cm_cenario",
    "cm_cenario_item",
    "cm_lembrete",
    "cm_lembrete_item",
    "cm_contrato",
    "cm_aviso",
    "cm_registro",
)

# Dado de paciente que nao pode morar em tabela nenhuma (ADR 0070, decisao 8).
COLUNAS_PROIBIDAS = (
    "nome_completo",
    "nome_paciente",
    "paciente_nome",
    "nome_mae",
    "cpf",
    "rg",
    "cns",
    "carteira",
    "carteirinha",
    "data_nascimento",
    "nascimento",
    "endereco",
    "telefone",
)

_PALAVRAS_DE_RESTRICAO = {"primary", "unique", "check", "foreign", "constraint", "exclude"}


def _sql_sem_comentarios() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION_118.read_text(encoding="utf-8"))


def _tabelas_criadas() -> dict[str, list[str]]:
    """Cada `CREATE TABLE cm_*` da migration com as colunas dele."""
    tabelas: dict[str, list[str]] = {}
    for nome, corpo in re.findall(
        r"CREATE TABLE IF NOT EXISTS (cm_\w+)\s*\((.*?)\n\);", _sql_sem_comentarios(), flags=re.DOTALL
    ):
        colunas = []
        for linha in corpo.splitlines():
            palavra = re.match(r"\s*([a-z_][a-z0-9_]*)\s", linha)
            if palavra and palavra.group(1).lower() not in _PALAVRAS_DE_RESTRICAO:
                colunas.append(palavra.group(1))
        tabelas[nome] = colunas
    return tabelas


class TestMigration118:
    def test_cria_as_tabelas_do_prd_e_so_elas(self):
        """Mutante: apagar o CREATE de uma tabela."""
        assert sorted(_tabelas_criadas()) == sorted(TABELAS_DA_118)

    @pytest.mark.parametrize("tabela", TABELAS_DA_118)
    def test_toda_tabela_tem_rls_ligado(self, tabela):
        """Mutante: tirar o ENABLE ROW LEVEL SECURITY de uma tabela."""
        assert re.search(rf"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;", _sql_sem_comentarios())

    @pytest.mark.parametrize("tabela", TABELAS_DA_118)
    def test_nenhuma_tabela_guarda_dado_que_identifica_o_paciente(self, tabela):
        assert [c for c in _tabelas_criadas()[tabela] if c in COLUNAS_PROIBIDAS] == []

    def test_o_leitor_de_colunas_enxerga_coluna(self):
        """Piso do detector acima: regex que nao casa deixaria tudo verde sobre nada."""
        assert "entidade_id" in _tabelas_criadas()["cm_registro"]

    def test_o_registro_guarda_autor_data_entidade_antes_e_depois(self):
        colunas = set(_tabelas_criadas()["cm_registro"])

        assert {"autor_id", "data", "entidade", "entidade_id", "antes_json", "depois_json"} <= colunas

    def test_a_tabela_de_preco_ganha_mapeamento_e_arquivo_original(self):
        sql = _sql_sem_comentarios()
        for coluna in ("mapeamento_json", "arquivo_original"):
            assert re.search(rf"ALTER TABLE cm_tabela_preco\s+ADD COLUMN IF NOT EXISTS {coluna}\s", sql), coluna

    def test_termina_com_o_recibo_da_118(self):
        ultima = _sql_sem_comentarios().strip().splitlines()[-1]
        assert ultima == "INSERT INTO migracoes_aplicadas (numero) VALUES (118) ON CONFLICT (numero) DO NOTHING;"
