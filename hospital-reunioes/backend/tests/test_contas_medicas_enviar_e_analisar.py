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

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contas_medicas_apoio import MIGRATIONS, aplicar, banco_da_matriz, linhas  # noqa: E402
from test_contas_medicas_envio import (  # noqa: E402
    ROTA_ENVIO,
    ROTA_FILA,
    _cenario,
    _cliente,
    _conta,
    _extrator_de_texto,  # noqa: F401 (autouse: o "PDF" do teste é texto)
    _fila_semeada,
    _prontuario,
    _reset_rate_limiter,  # noqa: F401 (autouse)
)

from app.routers import contas_medicas as contas_medicas_router  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402

MIGRATION_121 = MIGRATIONS / "121_contas_medicas_enviar_e_analisar.sql"

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
            "UPDATE cm_perfil_permissao SET ligada = false"
            " WHERE perfil = 'apoio_faturamento' AND permissao = 'enviar_contas'"
        )
        aplicar(banco, de=121, ate=121)

        assert _ligadas(linhas(banco), "apoio_faturamento") == set()

    def test_termina_com_o_recibo_da_121(self):
        ultima = _sql_121().strip().splitlines()[-1]
        assert ultima == "INSERT INTO migracoes_aplicadas (numero) VALUES (121) ON CONFLICT (numero) DO NOTHING;"


# ═══════════════════════════════════════════════════════════════════════════
# 2. As guardas, pelas rotas de verdade
# ═══════════════════════════════════════════════════════════════════════════

ROTA_MEUS_ENVIOS = "/api/contas-medicas/meus-envios"
ROTA_ME = "/api/contas-medicas/me"
UMA_CONTA = "aaaaaaaa-0000-0000-0000-000000000001"
ROTA_GUIA = f"/api/contas-medicas/contas/{UMA_CONTA}/guia"
ROTA_CONCLUIR = f"/api/contas-medicas/contas/{UMA_CONTA}/guia/concluir"


def _app(quem: str, banco):
    cliente = _cliente(quem, banco)
    cliente.app.include_router(guia_router.router, prefix="/api")
    cliente.app.include_router(contas_medicas_router.router, prefix="/api")
    return cliente


def _desligar(banco, perfil: str, permissao: str) -> None:
    for linha in banco.tabelas["cm_perfil_permissao"]:
        if (linha["perfil"], linha["permissao"]) == (perfil, permissao):
            linha["ligada"] = False


class TestApoioAoFaturamento:
    def test_me_devolve_so_enviar_contas(self):
        resposta = _app("apoio", _cenario()).get(ROTA_ME)

        assert resposta.json() == {"perfil": "apoio_faturamento", "permissoes": ["enviar_contas"]}

    def test_envia_e_ve_o_envio_em_meus_envios(self):
        banco = _cenario()
        cliente = _app("apoio", banco)

        enviado = cliente.post(ROTA_ENVIO, files=[_conta("31302", "48001"), _prontuario("31302")])
        assert enviado.status_code == 200, enviado.text
        [conta] = banco.tabelas["cm_conta"]

        resposta = cliente.get(ROTA_MEUS_ENVIOS)
        assert resposta.status_code == 200, resposta.text
        assert [c["id"] for c in resposta.json()["meus_envios"]] == [conta["id"]]

    @pytest.mark.parametrize(("metodo", "rota"), [("get", ROTA_FILA), ("get", ROTA_GUIA), ("post", ROTA_CONCLUIR)])
    def test_recebe_403_na_fila_no_guia_e_no_puxar(self, metodo, rota):
        """Abrir o Guia é o que puxa a conta, e o Concluir puxa a próxima."""
        resposta = getattr(_app("apoio", _fila_semeada()), metodo)(rota)

        assert resposta.status_code == 403


class TestFaturistaContinuaEnviandoEAnalisando:
    def test_me_devolve_as_duas(self):
        resposta = _app("faturista", _cenario()).get(ROTA_ME)

        assert resposta.json() == {"perfil": "faturista", "permissoes": ["enviar_contas", "enviar_corrigir_contas"]}

    def test_envia_ve_meus_envios_e_a_fila(self):
        cliente = _app("faturista", _fila_semeada())

        assert cliente.post(ROTA_ENVIO, files=[_conta("31999", "48999"), _prontuario("31999")]).status_code == 200
        assert cliente.get(ROTA_MEUS_ENVIOS).status_code == 200
        assert cliente.get(ROTA_FILA).status_code == 200


class TestCadaRotaPedeASuaChave:
    """Uma chave desligada pela Habilitação fecha só as rotas dela."""

    @pytest.mark.parametrize(("metodo", "rota"), [("post", ROTA_ENVIO), ("get", ROTA_MEUS_ENVIOS)])
    def test_sem_enviar_contas_a_faturista_nao_envia_nem_ve_meus_envios(self, metodo, rota):
        banco = _fila_semeada()
        _desligar(banco, "faturista", "enviar_contas")
        cliente = _app("faturista", banco)
        kwargs = {"files": [_conta("31999", "48999")]} if metodo == "post" else {}

        assert getattr(cliente, metodo)(rota, **kwargs).status_code == 403
        assert cliente.get(ROTA_FILA).status_code == 200

    def test_sem_analisar_contas_a_faturista_envia_mas_nao_ve_a_fila(self):
        banco = _fila_semeada()
        _desligar(banco, "faturista", "enviar_corrigir_contas")
        cliente = _app("faturista", banco)

        assert cliente.get(ROTA_FILA).status_code == 403
        assert cliente.get(ROTA_MEUS_ENVIOS).status_code == 200
