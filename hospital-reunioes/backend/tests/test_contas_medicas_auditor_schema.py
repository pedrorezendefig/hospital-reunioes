"""A migration 126: o schema do Auditor de Contas médicas (issue #1486, PRD #1484, ADR 0081).

A única migration do PRD. As fatias da Prova da regra, do Faltou isto, da
conversa da Operadora e da Validação decidida gravam nas tabelas que nascem
aqui, então o que se confere é o contrato com elas: as tabelas e colunas, os
valores dos CHECKs que elas vão gravar, o RLS default-deny em toda tabela nova
e o recibo em `migracoes_aplicadas`.
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATION_126 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "126_contas_medicas_auditor.sql"


def _sql() -> str:
    return MIGRATION_126.read_text(encoding="utf-8")


def _sem_comentarios(sql: str) -> str:
    return "\n".join(re.sub(r"--.*$", "", linha) for linha in sql.splitlines())


def _bloco_da_tabela(tabela: str) -> str:
    bloco = re.search(rf"CREATE TABLE IF NOT EXISTS {tabela} \((.*?)\n\);", _sql(), flags=re.DOTALL)
    assert bloco, f"a 126 nao cria {tabela}"
    return bloco.group(1)


def _colunas(tabela: str) -> set[str]:
    return {
        linha.split()[0]
        for linha in _bloco_da_tabela(tabela).splitlines()
        if linha.strip() and linha.strip()[0].isalpha() and not linha.strip().startswith(("CHECK", "UNIQUE"))
    }


def _valores_do_check(tabela: str, coluna: str) -> set[str]:
    (linha,) = [li for li in _bloco_da_tabela(tabela).splitlines() if li.strip().startswith(f"{coluna} ")]
    return set(re.findall(r"'(\w+)'", linha))


class TestMigration126:
    def test_cria_a_conversa_da_operadora_ou_da_conta_e_as_mensagens_ligadas_a_versao_da_memoria(self):
        assert {"contexto", "operadora_id", "conta_id", "criado_por", "criado_em"} <= _colunas("cm_conversa")
        assert _valores_do_check("cm_conversa", "contexto") == {"OPERADORA", "CONTA"}
        assert {"conversa_id", "autor", "autor_id", "texto", "memoria_versao_id", "criado_em"} <= _colunas(
            "cm_conversa_mensagem"
        )
        assert _valores_do_check("cm_conversa_mensagem", "autor") == {"PESSOA", "AUDITOR"}
        mensagem = _bloco_da_tabela("cm_conversa_mensagem")
        assert re.search(r"memoria_versao_id\s+UUID REFERENCES cm_memoria_versao\(id\)", mensagem)

    def test_cria_o_lote_de_propostas_e_os_itens_numerados(self):
        assert {"operadora_id", "conversa_id", "fonte", "estado", "memoria_versao_id"} <= _colunas("cm_lote")
        assert {"lote_id", "numero", "tipo", "regra_codigo", "proposta_json", "motivo", "estado"} <= _colunas(
            "cm_lote_item"
        )
        assert _valores_do_check("cm_lote_item", "tipo") == {
            "REGRA_NOVA",
            "REGRA_ALTERADA",
            "TABELA",
            "PARAMETRO",
            "CARD_TECNOLOGIA",
        }
        # "Corrige o item N": o número é único dentro do lote.
        assert "UNIQUE (lote_id, numero)" in _bloco_da_tabela("cm_lote_item")

    def test_cria_a_prova_da_regra_ligada_a_proposta(self):
        assert {"operadora_id", "lote_item_id", "regra_codigo", "regra_texto", "resultado_json", "mudaria"} <= (
            _colunas("cm_prova")
        )

    def test_cria_o_apontamento_faltou_isto_com_origem_classificacao_e_issue(self):
        colunas = _colunas("cm_faltou_isto")

        assert {"conta_id", "data", "item", "pagina", "texto", "origem", "classificacao", "issue_numero"} <= colunas
        assert _valores_do_check("cm_faltou_isto", "origem") == {"PESSOA", "AGENTE"}
        assert _valores_do_check("cm_faltou_isto", "classificacao") == {"REGRA", "LEITURA", "DEFEITO"}

    def test_o_tema_de_validacao_ganha_a_recomendacao_do_auditor(self):
        sql = _sql()

        for coluna in ("recomendacao", "recomendacao_motivo", "recomendacao_prova_id", "recomendado_em"):
            assert re.search(rf"ALTER TABLE cm_validacao_tema\s+ADD COLUMN IF NOT EXISTS {coluna} ", sql), coluna

    def test_o_passo_da_chamada_de_ia_aceita_conversa_prova_e_revisor_e_mantem_os_de_antes(self):
        bloco = re.search(r"ADD CONSTRAINT cm_chamada_ia_passo_check\s+CHECK \((.*?)\);", _sql(), flags=re.DOTALL)
        assert bloco, "a 126 nao refaz o CHECK do passo"

        assert set(re.findall(r"'(\w+)'", bloco.group(1))) == {
            "A",
            "B",
            "DICIONARIO",
            "OBSERVACAO",
            "CONVERSA",
            "PROVA",
            "REVISOR",
        }
        assert "DROP CONSTRAINT IF EXISTS cm_chamada_ia_passo_check" in _sql()

    def test_toda_tabela_nova_nasce_com_rls_e_sem_policy(self):
        """Varre toda tabela criada, não uma lista escrita à mão: tabela nova
        esquecida no ENABLE fica aberta para a anon_key do bundle."""
        sql = _sem_comentarios(_sql())
        criadas = re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql)

        assert len(criadas) == 6, criadas
        for tabela in criadas:
            assert f"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;" in sql, tabela
        assert "CREATE POLICY" not in sql.upper()

    def test_termina_com_o_recibo_do_proprio_numero(self):
        corpo = _sem_comentarios(_sql()).strip()

        assert corpo.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (126) ON CONFLICT (numero) DO NOTHING;")
