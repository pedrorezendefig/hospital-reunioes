"""A aba Entregas da Tecnologia (issue #1556, PRD #1548, ADR 0084, decisao 8).

A rota de leitura conta por card os entregues por semana ou por mes, com a
data de entrega (o fechamento da issue-raiz), a data em producao e o
Responsavel, e filtra por periodo, tipo, Origem e Responsavel. Card apagado e
card nao entregue ficam fora. Ninguem escreve por ela.

Tudo pela ROTA, no molde de `test_tecnologia_lista_filtros`.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import _cenario  # noqa: E402
from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _pessoa  # noqa: E402

from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import tecnologia_envio  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.tecnologia_entregas import ritmo, tamanho_da_entrega  # noqa: E402

ENTREGAS = f"{BASE}/entregas"

RIB = _pessoa("P4", "Pedro Rib", github_login="pedrorib")
OUTRA_DIRETORA = _pessoa("P7", "Outra Diretora")
# Tem acesso ao app, mas nao e Super admin: nao ve a aba.
FACILITADOR = _pessoa("P8", "Facilitador", access_profile="facilitador")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _entregue(did: str, numero: int, fechada_em: str, **campos) -> dict:
    campos.setdefault("etapa", "em_producao")
    foto = {"fechada_em": fechada_em, **campos.pop("foto", {})}
    return _demanda(did, github_issue_numero=numero, github_foto=foto, **campos)


def _demandas() -> list[dict]:
    """As datas sao fixas. O hospital fica em Sao Paulo (UTC-3): o fechamento
    as 01h de 02/11 em UTC e o domingo 01/11 no hospital, semana de 26/10; o das
    02h de 01/11 em UTC e o sabado 31/10, mes de outubro."""
    return [
        _entregue(
            "e-bug-diretor",
            901,
            "2026-11-03T12:00:00Z",
            titulo="Botao de responder sumiu",
            tipo="defeito",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            em_producao_em="2026-11-04T15:00:00Z",
        ),
        _entregue(
            "e-vitta-rib",
            902,
            "2026-11-05T20:00:00Z",
            etapa="entregue",
            titulo="Aviso quando a ata sair",
            tipo="novo",
            origem="vitta",
            autor_id=PEDRO["id"],
            responsavel_id=RIB["id"],
        ),
        _entregue(
            "e-domingo",
            903,
            "2026-11-02T01:00:00Z",
            titulo="Relatorio por setor",
            tipo="novo",
            autor_id=DIRETOR["id"],
            responsavel_id=PEDRO["id"],
            em_producao_em="2026-11-02T18:00:00Z",
            # Nasceu sem o Responsavel e ninguem passou pelo "Designar de novo":
            # o motivo traz o numero da issue dentro do texto.
            envio_estado=tecnologia_envio.ESTADO_DESIGNACAO_FALHOU,
            envio_motivo=tecnologia_envio.motivo_da_designacao(903, ["pedrovitta"]),
        ),
        _entregue(
            "e-vitta-terceiro",
            904,
            "2026-11-01T02:00:00Z",
            titulo="Impressao da escala",
            tipo="defeito",
            origem="vitta",
            autor_id=PEDRO["id"],
            responsavel_id=None,
            foto={"assignee": "terceiro-gh"},
        ),
        _entregue(
            "e-outra-diretora",
            905,
            "2026-10-15T12:00:00Z",
            titulo="Painel da outra diretora",
            tipo="novo",
            autor_id=OUTRA_DIRETORA["id"],
            responsavel_id=PEDRO["id"],
        ),
        # Fora: apagado, ainda em desenvolvimento, e fechado como nao planejado.
        _entregue(
            "x-apagado",
            906,
            "2026-11-03T12:00:00Z",
            titulo="Apagado",
            autor_id=DIRETOR["id"],
            apagada_em="2026-11-06T10:00:00Z",
        ),
        _demanda(
            "x-em-desenvolvimento",
            github_issue_numero=907,
            etapa="em_desenvolvimento",
            titulo="Ainda sendo feito",
            autor_id=DIRETOR["id"],
        ),
        _entregue(
            "x-nao-sera-feita",
            908,
            "2026-11-03T12:00:00Z",
            etapa="nao_sera_feita",
            titulo="Nao sera feita",
            autor_id=DIRETOR["id"],
        ),
    ]


@pytest.fixture
def entregas(monkeypatch):
    monkeypatch.setattr(tecnologia_router, "agora_utc", lambda: AGORA)

    def pedir(logado: dict, consulta: str = ""):
        client, _, _ = _cenario(
            monkeypatch,
            logado=logado,
            participantes=[PEDRO, DIRETOR, RIB, OUTRA_DIRETORA, FACILITADOR],
            demandas=_demandas(),
        )
        return client.get(f"{ENTREGAS}?{consulta}" if consulta else ENTREGAS)

    return pedir


def _corpo(resposta) -> dict:
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _ids(resposta) -> list[str]:
    return [d["id"] for d in _corpo(resposta)["entregas"]]


# ═══════════════════════════════════════════════════════════════════════════
# 0. O Tamanho da entrega (ADR 0092, decisao 3)
# ═══════════════════════════════════════════════════════════════════════════


class TestTamanhoDaEntrega:
    @pytest.mark.parametrize(
        ("partes", "tamanho"),
        [(None, "P"), (0, "P"), (1, "P"), (2, "M"), (5, "M"), (6, "G"), (9, "G")],
    )
    def test_o_tamanho_sai_do_numero_de_partes(self, partes, tamanho):
        """Ate 1 parte e P, de 2 a 5 e M, 6 ou mais e G. O bug sem sub-issue
        (partes nulas na sincronizacao) e P."""
        assert tamanho_da_entrega(partes) == tamanho


# ═══════════════════════════════════════════════════════════════════════════
# 0b. O ritmo, na regra pura (ADR 0092, decisoes 1 e 3)
# ═══════════════════════════════════════════════════════════════════════════

# Sexta 13/11/2026, meio-dia no hospital. A semana corrente comeca na segunda
# 09/11; as 4 do topo vao de 19/10 a 15/11, e as 4 anteriores de 21/09 a 18/10.
AGORA = datetime(2026, 11, 13, 15, 0, tzinfo=UTC)


def _card(did: str, **campos) -> dict:
    """Uma Demanda com card, pedida pelo diretor bem antes da janela."""
    campos.setdefault("github_issue_numero", 700)
    campos.setdefault("criado_em", "2026-01-05T12:00:00Z")
    return _demanda(did, **campos)


def _fechado(did: str, fechada_em: str, **campos) -> dict:
    campos.setdefault("etapa", "em_producao")
    return _card(did, github_foto={"fechada_em": fechada_em, **campos.pop("foto", {})}, **campos)


def _semana(resultado: dict, inicio: str) -> dict:
    [semana] = [s for s in resultado["semanas"] if s["inicio"] == inicio]
    return semana


class TestRitmo:
    def test_a_semana_comeca_na_segunda_pelo_fuso_de_sao_paulo(self):
        """Fechado no domingo 08/11 as 22h do hospital, que ja e segunda 09/11
        em UTC: conta na semana que termina naquele domingo, a de 02/11."""
        resultado = ritmo([_fechado("domingo", "2026-11-09T01:00:00Z", titulo="Fechado no domingo")], agora=AGORA)

        assert _semana(resultado, "2026-11-02")["entregas"] == [{"titulo": "Fechado no domingo", "tamanho": "P"}]
        assert _semana(resultado, "2026-11-09")["entregas"] == []

    def test_o_topo_conta_as_4_semanas_com_a_corrente_e_as_4_anteriores(self):
        """A borda e a meia-noite de segunda no hospital: 00h30 de 19/10 entra
        nas 4 do topo, e 23h de 18/10 ja e das anteriores. Antes de 21/09 nao
        conta em nenhuma das duas."""
        resultado = ritmo(
            [
                _fechado("corrente", "2026-11-12T15:00:00Z"),
                _fechado("borda-de-dentro", "2026-10-19T03:30:00Z"),
                _fechado("borda-de-fora", "2026-10-19T02:00:00Z"),
                _fechado("anterior", "2026-09-21T12:00:00Z"),
                _fechado("antes-de-tudo", "2026-09-20T12:00:00Z"),
            ],
            agora=AGORA,
        )

        assert resultado["topo"]["entregas"]["total"] == 2
        assert resultado["topo"]["entregas"]["anteriores"] == 2

    def test_o_pedido_conta_na_semana_em_que_o_card_nasceu(self):
        """Na Origem Vitta, a criacao da issue-raiz que a foto guarda
        (`criada_em`); sem ela, a criacao da Demanda. Na Origem diretor, o
        Criar o card, e nao o comeco da conversa. Conversa sem card nao e
        pedido."""
        resultado = ritmo(
            [
                _card(
                    "vitta-com-data",
                    origem="vitta",
                    criado_em="2026-11-10T12:00:00Z",
                    github_foto={"criada_em": "2026-10-07T12:00:00Z"},
                ),
                _card("vitta-sem-data", origem="vitta", criado_em="2026-10-28T12:00:00Z", github_foto={}),
                _card("diretor", criado_em="2026-09-23T12:00:00Z", envio_em="2026-11-03T12:00:00Z"),
                _demanda("so-conversa", criado_em="2026-11-11T12:00:00Z"),
            ],
            agora=AGORA,
        )

        pedidos = {s["inicio"]: s["pedidos"] for s in resultado["semanas"] if s["pedidos"]}
        assert pedidos == {"2026-10-05": 1, "2026-10-26": 1, "2026-11-02": 1}
        assert resultado["topo"]["pedidos"]["total"] == 2
        assert resultado["topo"]["pedidos"]["anteriores"] == 1

    def test_a_composicao_dos_numeros_e_das_semanas(self):
        """Os pedidos se abrem em bugs e melhorias; as entregas, em G, M e P,
        no topo e em cada semana. A semana lista o que saiu, o mais novo
        primeiro, com o titulo e o tamanho."""
        resultado = ritmo(
            [
                _fechado("g", "2026-11-10T12:00:00Z", titulo="Painel novo", partes_total=7, envio_em=None),
                _fechado("m", "2026-11-12T12:00:00Z", titulo="Aviso da ata", partes_total=3),
                _fechado("p", "2026-11-03T12:00:00Z", titulo="Botao sumiu", tipo="defeito"),
                _card("bug-novo", tipo="defeito", envio_em="2026-11-11T12:00:00Z"),
                _card("melhoria-nova", tipo="novo", envio_em="2026-10-20T12:00:00Z"),
                _card("bug-antigo", tipo="defeito", envio_em="2026-10-01T12:00:00Z"),
            ],
            agora=AGORA,
        )

        assert resultado["topo"]["pedidos"] == {"total": 2, "anteriores": 1, "bugs": 1, "melhorias": 1}
        assert resultado["topo"]["entregas"] == {"total": 3, "anteriores": 0, "g": 1, "m": 1, "p": 1}
        corrente = _semana(resultado, "2026-11-09")
        assert (corrente["g"], corrente["m"], corrente["p"]) == (1, 1, 0)
        assert corrente["entregas"] == [
            {"titulo": "Aviso da ata", "tamanho": "M"},
            {"titulo": "Painel novo", "tamanho": "G"},
        ]
        assert (_semana(resultado, "2026-11-02")["p"], _semana(resultado, "2026-11-02")["pedidos"]) == (1, 0)

    def test_as_12_semanas_vem_da_mais_antiga_para_a_corrente(self):
        semanas = ritmo([], agora=AGORA)["semanas"]

        assert len(semanas) == 12
        assert semanas[0]["inicio"] == "2026-08-24"
        assert semanas[-1]["inicio"] == "2026-11-09"
        assert semanas[-1] == {"inicio": "2026-11-09", "pedidos": 0, "g": 0, "m": 0, "p": 0, "entregas": []}

    def test_nao_sera_feita_nao_conta_como_entrega(self):
        """Fechada na semana corrente como Nao sera feita: o pedido conta, a
        entrega nao."""
        resultado = ritmo(
            [_fechado("recusado", "2026-11-12T12:00:00Z", etapa="nao_sera_feita", envio_em="2026-11-10T12:00:00Z")],
            agora=AGORA,
        )

        assert resultado["topo"]["entregas"]["total"] == 0
        assert _semana(resultado, "2026-11-09")["entregas"] == []
        assert _semana(resultado, "2026-11-09")["pedidos"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 1. O ritmo pela rota: o topo e as 12 semanas
# ═══════════════════════════════════════════════════════════════════════════


def _topo(resposta) -> tuple[int, int]:
    """As entregas das 4 semanas do topo e das 4 anteriores."""
    entregas = _corpo(resposta)["topo"]["entregas"]
    return entregas["total"], entregas["anteriores"]


def _titulos_da_semana(resposta, inicio: str) -> list[str]:
    [semana] = [s for s in _corpo(resposta)["semanas"] if s["inicio"] == inicio]
    return [e["titulo"] for e in semana["entregas"]]


class TestRitmoPelaRota:
    def test_a_rota_devolve_o_topo_e_as_12_semanas(self, entregas):
        """Com o relogio na sexta 13/11: o bug e o aviso fecharam na semana de
        02/11, o domingo e o terceiro na de 26/10 (pelo dia do hospital), e o
        painel da outra diretora na de 12/10, que ja e das 4 anteriores."""
        corpo = _corpo(entregas(PEDRO))

        assert corpo["topo"]["entregas"] == {"total": 4, "anteriores": 1, "g": 0, "m": 0, "p": 4}
        assert [s["inicio"] for s in corpo["semanas"]][::11] == ["2026-08-24", "2026-11-09"]
        assert len(corpo["semanas"]) == 12
        assert _titulos_da_semana(entregas(PEDRO), "2026-11-02") == [
            "Aviso quando a ata sair",
            "Botao de responder sumiu",
        ]
        assert "agrupar" not in corpo and "periodos" not in corpo

    def test_o_diretor_conta_as_dele_e_as_da_vitta(self, entregas):
        """A mesma regra da lista do chat (`pode_ver`): o pedido de outra
        diretora nao entra, nem no topo."""
        resposta = entregas(DIRETOR)

        assert _topo(resposta) == (4, 0)
        assert "e-outra-diretora" not in _ids(resposta)

    def test_a_lista_vem_da_entrega_mais_recente_para_a_mais_antiga(self, entregas):
        assert _ids(entregas(PEDRO)) == [
            "e-vitta-rib",
            "e-bug-diretor",
            "e-domingo",
            "e-vitta-terceiro",
            "e-outra-diretora",
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Os filtros valem para o topo, as semanas e a lista
# ═══════════════════════════════════════════════════════════════════════════


class TestFiltros:
    @pytest.mark.parametrize(
        ("consulta", "topo", "semana_02_11", "lista"),
        [
            ("tipo=bug", (2, 0), ["Botao de responder sumiu"], ["e-bug-diretor", "e-vitta-terceiro"]),
            ("origem=vitta", (2, 0), ["Aviso quando a ata sair"], ["e-vitta-rib", "e-vitta-terceiro"]),
            (
                "responsavel=P1",
                (2, 1),
                ["Botao de responder sumiu"],
                ["e-bug-diretor", "e-domingo", "e-outra-diretora"],
            ),
            ("responsavel=terceiro-gh", (1, 0), [], ["e-vitta-terceiro"]),
            ("tipo=melhoria&origem=diretor&responsavel=P1", (1, 1), [], ["e-domingo", "e-outra-diretora"]),
        ],
    )
    def test_tipo_origem_e_responsavel_valem_para_tudo(self, entregas, consulta, topo, semana_02_11, lista):
        resposta = entregas(PEDRO, consulta)

        assert _topo(resposta) == topo
        assert _titulos_da_semana(resposta, "2026-11-02") == semana_02_11
        assert _ids(resposta) == lista

    def test_os_filtros_valem_para_os_pedidos(self, entregas):
        """Os pedidos nasceram todos em 01/09 (a criacao da Demanda, sem foto
        com a data): a semana de 31/08 conta os do filtro."""

        def pedidos_de_31_08(resposta) -> int:
            [semana] = [s for s in _corpo(resposta)["semanas"] if s["inicio"] == "2026-08-31"]
            return semana["pedidos"]

        assert pedidos_de_31_08(entregas(PEDRO)) == 7
        assert pedidos_de_31_08(entregas(PEDRO, "origem=vitta")) == 2

    def test_o_diretor_filtra_por_responsavel(self, entregas):
        """Nas Entregas o Responsavel e filtro de todos: e a pergunta do diretor
        "o que o Rib entregou"."""
        assert _ids(entregas(DIRETOR, "responsavel=P4")) == ["e-vitta-rib"]

    def test_as_opcoes_do_responsavel_vem_de_tudo_o_que_ele_ve_entregue(self, entregas):
        """As opcoes nao somem com o filtro ligado, senao nao da para trocar."""
        corpo = _corpo(entregas(DIRETOR, "responsavel=P4"))

        assert corpo["responsaveis"] == [
            {"valor": "P4", "nome": "Pedro Rib"},
            {"valor": "P1", "nome": "Pedro Vitta"},
            {"valor": "terceiro-gh", "nome": "terceiro-gh"},
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 3. O que fica fora
# ═══════════════════════════════════════════════════════════════════════════


class TestFicamFora:
    @pytest.mark.parametrize("did", ["x-apagado", "x-em-desenvolvimento", "x-nao-sera-feita"])
    def test_card_apagado_e_card_nao_entregue_ficam_fora_da_lista(self, entregas, did):
        assert did not in _ids(entregas(PEDRO))

    def test_card_apagado_e_nao_sera_feita_nao_contam_na_semana(self, entregas):
        """O apagado e o Nao sera feita tem a data de 03/11, a mesma do bug
        entregue: a semana de 02/11 lista so os dois entregues."""
        assert _titulos_da_semana(entregas(PEDRO), "2026-11-02") == [
            "Aviso quando a ata sair",
            "Botao de responder sumiu",
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 4. A lista: datas e Responsavel
# ═══════════════════════════════════════════════════════════════════════════


def _folhas(valor):
    """Todo valor do JSON, em qualquer profundidade."""
    if isinstance(valor, dict):
        for filho in valor.values():
            yield from _folhas(filho)
    elif isinstance(valor, list):
        for filho in valor:
            yield from _folhas(filho)
    else:
        yield valor


NUMEROS_DAS_ISSUES = set(range(901, 909))


class TestLista:
    def test_a_entrega_traz_data_de_entrega_data_em_producao_e_responsavel(self, entregas):
        [entrega] = _corpo(entregas(DIRETOR, "tipo=bug&origem=diretor"))["entregas"]

        assert entrega["id"] == "e-bug-diretor"
        assert entrega["fechada_em"] == "2026-11-03T12:00:00Z"
        assert entrega["em_producao_em"] == "2026-11-04T15:00:00Z"
        assert entrega["responsavel"] == "Pedro Vitta"
        assert entrega["etapa"] == "em_producao"

    def test_a_entrega_que_nao_subiu_vem_sem_data_em_producao(self, entregas):
        [entrega] = _corpo(entregas(DIRETOR, "responsavel=P4"))["entregas"]

        assert entrega["fechada_em"] == "2026-11-05T20:00:00Z"
        assert entrega["em_producao_em"] is None

    def test_o_responsavel_de_fora_do_app_aparece_pelo_login(self, entregas):
        [entrega] = _corpo(entregas(DIRETOR, "responsavel=terceiro-gh"))["entregas"]

        assert entrega["responsavel"] == "terceiro-gh"

    @pytest.mark.parametrize("logado", [PEDRO, DIRETOR], ids=["desenvolvedor", "diretor"])
    def test_nenhum_numero_de_issue_sai_na_resposta(self, entregas, logado):
        """Nem para o Desenvolvedor (PRD #1689): diretor e Desenvolvedor
        recebem a mesma resposta. Procura em toda a resposta, e nao so nos
        campos conhecidos: o numero e o link da issue de nenhum card aparecem."""
        folhas = list(_folhas(_corpo(entregas(logado))))
        textos = [f for f in folhas if isinstance(f, str)]

        assert NUMEROS_DAS_ISSUES.isdisjoint(f for f in folhas if isinstance(f, int))
        assert not [t for t in textos if "/issues/" in t]
        assert not [t for t in textos for n in NUMEROS_DAS_ISSUES if str(n) in t]

    def test_o_card_com_designacao_falhada_sai_igual_para_os_dois(self, entregas):
        """O motivo da designacao falhada traz "#903" no texto: nao sai nem
        para o Desenvolvedor, e o card sai igual para diretor e Desenvolvedor."""

        def _card(logado):
            [card] = [d for d in _corpo(entregas(logado))["entregas"] if d["id"] == "e-domingo"]
            return card

        dev, diretor = _card(PEDRO), _card(DIRETOR)

        assert dev["envio_motivo"] is None
        assert dev["designacao_falhou"] is False
        assert dev["autor"] is None
        assert {k: v for k, v in dev.items() if k != "minha"} == {k: v for k, v in diretor.items() if k != "minha"}


# ═══════════════════════════════════════════════════════════════════════════
# 5. Quem ve
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemVe:
    @pytest.mark.parametrize("logado", [PEDRO, DIRETOR])
    def test_o_diretor_e_o_desenvolvedor_abrem_as_entregas(self, entregas, logado):
        assert entregas(logado).status_code == 200

    def test_quem_nao_e_super_admin_e_recusado(self, entregas):
        assert entregas(FACILITADOR).status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 6. O Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def _kit() -> str:
    return (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")


def _secao(titulo: str) -> str:
    return _kit().split(f"## {titulo}", 1)[1].split("\n## ", 1)[0]


class TestKit:
    def test_o_kit_diz_que_a_aba_tem_conversas_e_entregas(self):
        """O Assistente fala pela lingua do Kit: sem isto, ele diria que a aba
        e uma tela so."""
        abertura = _kit().split("\n## ", 1)[0]

        assert "**Conversas**" in abertura
        assert "**Entregas**" in abertura
        assert "tela só" not in _kit()

    def test_o_kit_explica_as_entregas(self):
        secao = _secao("As Entregas")
        for trecho in (
            "últimas 4 semanas",
            "4 anteriores",
            "12 semanas",
            "segunda-feira",
            "data de entrega",
            "em produção",
            "Responsável",
            "Origem",
            "combinam",
            "apagado",
            "Não será feita",
            "Documento do card",
            "nada se move",
        ):
            assert trecho in secao, trecho

    def test_o_kit_diz_o_que_os_numeros_e_o_grafico_mostram(self):
        """Os dois numeros, o que o mouse abre neles e a previa da semana no
        grafico (ADR 0092, decisoes 1 e 4)."""
        secao = _secao("As Entregas")
        for trecho in (
            "**pedidos**",
            "**entregas**",
            "bugs e melhorias",
            "lado a lado",
            "o título e o tamanho",
        ):
            assert trecho in secao, trecho

    def test_o_kit_explica_o_tamanho_da_entrega(self):
        """P ate 1 parte, M de 2 a 5, G de 6 em diante, sem estimativa (ADR
        0092, decisao 3). O seletor de periodo e o "por mes" sairam da aba."""
        secao = _secao("As Entregas")

        assert "**Tamanho da entrega**" in secao
        assert "**P** é o pedido de até 1 parte" in secao
        assert "**M**, de 2 a 5" in secao
        assert "**G**, de 6 partes em diante" in secao
        assert "ninguém estima" in secao
        assert "por mês" not in _kit()
