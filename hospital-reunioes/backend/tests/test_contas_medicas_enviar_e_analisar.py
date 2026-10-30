"""Enviar contas e Analisar contas separados (issue #1308, PRD #1303, ADR 0073 decisão 4).

Quem só sobe contas (a secretária) ganha o perfil Apoio ao faturamento: envia e
acompanha "Meus envios", sem pegar conta para analisar. A chave antiga
`enviar_corrigir_contas` não muda de nome (vira "Analisar contas" na tela) e a
nova, `enviar_contas`, nasce ligada para todo perfil que tinha a antiga: o
código velho segue funcionando entre a migration e a subida.

O esperado de cada perfil é escrito à mão a partir da ADR, não derivado da
migration: é a fonte que pode discordar dela.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contas_medicas_apoio import aplicar, banco_da_matriz, linhas  # noqa: E402

MIGRATION_121 = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "121_contas_medicas_enviar_e_analisar.sql"

PERFIS_ANTIGOS = (
    "faturista",
    "coordenadora",
    "gestao_contas_medicas",
    "diretoria_medica",
    "diretoria_executiva",
    "credenciamento",
)
PERMISSOES_ANTIGAS = (
    "enviar_corrigir_contas",
    "decidir_validacao",
    "incluir_regra_operacional",
    "regra_contratual_tabelas",
    "contratos_avisos",
    "painel_completo",
    "habilitar_pessoas",
    "conferencia_coordenacao",
)
TODAS = ("enviar_contas", *PERMISSOES_ANTIGAS)

# Da carga da 116: quem tinha "enviar e corrigir contas" ligada.
QUEM_ANALISAVA = {"faturista", "coordenadora", "gestao_contas_medicas", "diretoria_medica", "diretoria_executiva"}


def _sql_121() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION_121.read_text(encoding="utf-8"))


def _ligadas(matriz: list[dict], perfil: str) -> set[str]:
    return {linha["permissao"] for linha in matriz if linha["perfil"] == perfil and linha["ligada"]}


def _matriz_depois_da_121(*habilitacao: str) -> list[dict]:
    """A 116, depois o que a Habilitação mudou em produção, depois a 121."""
    banco = banco_da_matriz()
    aplicar(banco, ate=120)
    for comando in habilitacao:
        banco.execute(comando)
    aplicar(banco, de=121, ate=121)
    return linhas(banco)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 121
# ═══════════════════════════════════════════════════════════════════════════


class TestMigration121:
    def test_e_aditiva_nao_renomeia_nem_apaga_nada(self):
        """Os únicos DROPs são dos três CHECKs que voltam com a lista ampliada."""
        sql = _sql_121()

        for proibido in (r"\bDELETE\b", r"\bUPDATE\b", r"\bRENAME\b", r"\bTRUNCATE\b", r"DROP\s+(TABLE|COLUMN)"):
            assert not re.search(proibido, sql, flags=re.IGNORECASE), proibido
        drops = re.findall(r"DROP CONSTRAINT IF EXISTS (\w+)", sql)
        assert sorted(drops) == [
            "cm_perfil_permissao_perfil_check",
            "cm_perfil_permissao_permissao_check",
            "participantes_perfil_contas_medicas_check",
        ]
        for nome in drops:
            assert re.search(rf"ADD CONSTRAINT {nome}\b", sql), nome

    @pytest.mark.parametrize(
        ("restricao", "valores"),
        [
            ("participantes_perfil_contas_medicas_check", (*PERFIS_ANTIGOS, "apoio_faturamento")),
            ("cm_perfil_permissao_perfil_check", (*PERFIS_ANTIGOS, "apoio_faturamento")),
            ("cm_perfil_permissao_permissao_check", TODAS),
        ],
    )
    def test_as_listas_fechadas_ganham_o_novo_e_mantem_os_antigos(self, restricao, valores):
        bloco = re.search(rf"ADD CONSTRAINT {restricao}\s+CHECK\s*\((.*?)\);", _sql_121(), flags=re.DOTALL)
        assert bloco, restricao

        assert sorted(re.findall(r"'(\w+)'", bloco.group(1))) == sorted(valores)

    def test_todo_perfil_que_analisava_tambem_envia(self):
        matriz = _matriz_depois_da_121()

        for perfil in PERFIS_ANTIGOS:
            assert ("enviar_contas" in _ligadas(matriz, perfil)) == (perfil in QUEM_ANALISAVA), perfil

    def test_a_copia_segue_o_que_a_habilitacao_mudou_em_producao(self):
        """A 121 copia do banco, não da carga da 116: o credenciamento que
        ganhou "Analisar" pela Habilitação também passa a enviar, e a faturista
        que perdeu continua sem enviar."""
        matriz = _matriz_depois_da_121(
            "UPDATE cm_perfil_permissao SET ligada = true"
            " WHERE perfil = 'credenciamento' AND permissao = 'enviar_corrigir_contas'",
            "UPDATE cm_perfil_permissao SET ligada = false"
            " WHERE perfil = 'faturista' AND permissao = 'enviar_corrigir_contas'",
        )

        assert "enviar_contas" in _ligadas(matriz, "credenciamento")
        assert "enviar_contas" not in _ligadas(matriz, "faturista")

    def test_apoio_ao_faturamento_so_envia(self):
        assert _ligadas(_matriz_depois_da_121(), "apoio_faturamento") == {"enviar_contas"}

    def test_toda_celula_existe_para_a_habilitacao_ligar(self):
        """Sete perfis vezes nove permissões, ligada ou não."""
        pares = {(linha["perfil"], linha["permissao"]) for linha in _matriz_depois_da_121()}

        assert pares == {(perfil, p) for perfil in (*PERFIS_ANTIGOS, "apoio_faturamento") for p in TODAS}

    def test_reaplicar_nao_desfaz_o_que_a_habilitacao_mudou_depois(self):
        banco = banco_da_matriz()
        aplicar(banco)
        banco.execute(
            "UPDATE cm_perfil_permissao SET ligada = false WHERE perfil = 'apoio_faturamento' AND permissao = 'enviar_contas'"
        )
        aplicar(banco, de=121, ate=121)

        assert _ligadas(linhas(banco), "apoio_faturamento") == set()

    def test_termina_com_o_recibo_da_121(self):
        ultima = _sql_121().strip().splitlines()[-1]
        assert ultima == "INSERT INTO migracoes_aplicadas (numero) VALUES (121) ON CONFLICT (numero) DO NOTHING;"
