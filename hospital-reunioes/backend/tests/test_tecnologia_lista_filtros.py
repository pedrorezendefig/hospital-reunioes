"""A lista da Tecnologia com busca e filtros combináveis (issue #1551, PRD #1548).

A rota da lista aceita a busca pelo título (sem diferenciar maiúscula e
acento) e os filtros Tipo, Etapa, Responsável e Envio falhou, que combinam
entre si e com o recorte de hoje (Para mim, Minhas, Todas). Responsável, Envio
falhou e Para mim são do Desenvolvedor: a rota os recusa ao diretor.

Tudo pela ROTA, no molde de `test_tecnologia_responsavel`.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import CHAT, _cenario  # noqa: E402
from test_tecnologia_vinculo import DIRETOR, PEDRO, _demanda, _pessoa  # noqa: E402

from app.limiter import limiter  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

RIB = _pessoa("P4", "Pedro Rib", github_login="pedrorib")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _participantes() -> list[dict]:
    return [PEDRO, DIRETOR, RIB]


def _com_card(did: str, numero: int, **campos) -> dict:
    return _demanda(did, github_issue_numero=numero, **campos)


def _demandas() -> list[dict]:
    """Um pedido de cada jeito, do mais recente para o mais antigo."""
    return [
        _com_card(
            "d-bug-rib",
            901,
            titulo="O relatório some da tela",
            tipo="defeito",
            etapa="em_analise",
            autor_id=DIRETOR["id"],
            responsavel_id=RIB["id"],
            criado_em="2026-11-06T10:00:00Z",
        ),
        _com_card(
            "d-bug-pedro",
            902,
            titulo="BOTÃO DE RESPONDER SUMIU",
            tipo="defeito",
            etapa="em_analise",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            criado_em="2026-11-05T10:00:00Z",
        ),
        _com_card(
            "d-melhoria-pedro",
            903,
            titulo="Aviso quando a ata sair",
            tipo="novo",
            etapa="em_producao",
            autor_id=PEDRO["id"],
            responsavel_id=PEDRO["id"],
            criado_em="2026-11-04T10:00:00Z",
        ),
        _demanda(
            "d-falhou-pedro",
            titulo="Relatorio de custo por setor",
            tipo="novo",
            autor_id=PEDRO["id"],
            envio_estado="falhou",
            criado_em="2026-11-03T10:00:00Z",
        ),
        _demanda(
            "d-falhou-diretor",
            titulo="Botão de imprimir",
            tipo="defeito",
            autor_id=DIRETOR["id"],
            envio_estado="falhou",
            criado_em="2026-11-02T10:00:00Z",
        ),
    ]


@pytest.fixture
def lista(monkeypatch):
    def pedir(logado: dict, consulta: str = ""):
        client, _, _ = _cenario(monkeypatch, logado=logado, participantes=_participantes(), demandas=_demandas())
        return client.get(f"{CHAT}?{consulta}" if consulta else CHAT)

    return pedir


def _ids(resposta) -> list[str]:
    assert resposta.status_code == 200, resposta.text
    return [d["id"] for d in resposta.json()]


# ═══════════════════════════════════════════════════════════════════════════
# 1. A busca pelo título
# ═══════════════════════════════════════════════════════════════════════════


class TestBusca:
    def test_a_busca_acha_o_titulo_sem_diferenciar_acento(self, lista):
        assert _ids(lista(PEDRO, "filtro=todas&busca=relatorio")) == ["d-bug-rib", "d-falhou-pedro"]

    def test_a_busca_acha_o_titulo_sem_diferenciar_maiuscula(self, lista):
        assert _ids(lista(PEDRO, "filtro=todas&busca=Botao de RESP")) == ["d-bug-pedro"]

    def test_o_diretor_busca_nas_dele(self, lista):
        assert _ids(lista(DIRETOR, "busca=botão")) == ["d-bug-pedro", "d-falhou-diretor"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Os filtros combinam
# ═══════════════════════════════════════════════════════════════════════════


class TestFiltrosCombinam:
    @pytest.mark.parametrize(
        ("consulta", "esperado"),
        [
            ("filtro=todas&tipo=bug", ["d-bug-rib", "d-bug-pedro", "d-falhou-diretor"]),
            ("filtro=todas&tipo=bug&etapa=em_analise", ["d-bug-rib", "d-bug-pedro"]),
            ("filtro=todas&tipo=bug&etapa=em_analise&responsavel=P4", ["d-bug-rib"]),
            ("filtro=todas&tipo=melhoria&etapa=em_producao", ["d-melhoria-pedro"]),
            ("filtro=para_mim&tipo=bug", ["d-bug-pedro"]),
            ("filtro=para_mim&etapa=em_producao", ["d-melhoria-pedro"]),
            ("filtro=minhas&envio_falhou=true", ["d-falhou-pedro"]),
            ("filtro=todas&envio_falhou=true&tipo=bug", ["d-falhou-diretor"]),
            ("filtro=todas&envio_falhou=true&busca=relatorio", ["d-falhou-pedro"]),
            ("filtro=todas&etapa=registrada", ["d-falhou-pedro", "d-falhou-diretor"]),
        ],
    )
    def test_o_desenvolvedor_combina_os_filtros_com_o_recorte(self, lista, consulta, esperado):
        assert _ids(lista(PEDRO, consulta)) == esperado

    def test_o_diretor_combina_tipo_e_etapa(self, lista):
        assert _ids(lista(DIRETOR, "tipo=bug&etapa=em_analise")) == ["d-bug-rib", "d-bug-pedro"]

    def test_sem_filtro_a_lista_continua_a_de_hoje(self, lista):
        assert _ids(lista(DIRETOR)) == ["d-bug-rib", "d-bug-pedro", "d-falhou-diretor"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. O que é só do Desenvolvedor
# ═══════════════════════════════════════════════════════════════════════════


class TestSoDoDesenvolvedor:
    @pytest.mark.parametrize("consulta", ["filtro=para_mim", "responsavel=P4", "envio_falhou=true"])
    def test_a_rota_recusa_ao_diretor_o_filtro_do_desenvolvedor(self, lista, consulta):
        resposta = lista(DIRETOR, consulta)

        assert resposta.status_code == 403, resposta.text


# ═══════════════════════════════════════════════════════════════════════════
# 4. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def _secao(titulo: str) -> str:
    texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")
    return texto.split(f"## {titulo}", 1)[1].split("\n## ", 1)[0]


class TestKit:
    def test_o_kit_diz_ao_diretor_que_ele_busca_e_filtra_a_lista(self):
        """O Assistente fala pela língua do Kit: sem isto, ele diria que a
        lista só rola, sem busca nem filtro."""
        secao = _secao("A conversa com o Assistente")
        for trecho in (
            "busca",
            "maiúscula",
            "acento",
            "**Bug**",
            "**Melhoria**",
            "Etapa",
            "recolhe",
            "Voltar às conversas",
        ):
            assert trecho in secao, trecho

    def test_o_kit_diz_os_filtros_que_sao_so_do_desenvolvedor(self):
        secao = _secao("Quem vê")
        for trecho in ("**Responsável**", "**Envio falhou**", "**Para mim**", "combinam"):
            assert trecho in secao, trecho
