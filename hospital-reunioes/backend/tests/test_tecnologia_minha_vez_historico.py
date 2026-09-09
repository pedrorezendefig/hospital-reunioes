"""Minha vez e Historico (issue #641, PRD #634, ADR 0050).

Dois seams, na mesma ordem das fatias anteriores:

* **As regras puras**, testadas direto e sem HTTP: a ordem de "Minha vez", a
  conta de "fui mencionado e ainda nao respondi", o desfecho da Demanda
  (quando e por quem ela fechou) e o que a busca do Historico procura.
* **Os dois endpoints**, pela ROTA de verdade com o Supabase dublado, no molde
  do `test_tecnologia_demandas.py`. E o unico jeito de provar que "Minha vez"
  usa o participante LOGADO, e nao um id que a tela mandaria.

O gate de papel nao se repete aqui: a matriz de `test_admin_tecnologia.py`
varre o schema OpenAPI e engole as duas rotas novas (o piso dela subiu de 13
para 15 no mesmo commit).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services.tecnologia import (  # noqa: E402
    ESTADOS,
    ESTADOS_ABERTOS,
    ESTADOS_FECHADOS,
    PRIORIDADES,
    demanda_casa_a_busca,
    esperando_resposta_da_pessoa,
    fechamento_da_demanda,
    motivo_da_minha_vez,
    ordenar_historico,
    ordenar_minha_vez,
    peso_da_prioridade,
    textos_de_resposta,
)

# ─── 1. As regras puras ──────────────────────────────────────────────────────


class TestOsDoisGruposDeEstado:
    """Aberto e fechado sao o complemento um do outro sobre os cinco estados.

    Um estado novo que ficasse de fora dos dois sumiria das DUAS abas em
    silencio: nao apareceria em "Minha vez" (que le os abertos) nem no
    Historico (que le os fechados), e ninguem veria erro nenhum.
    """

    def test_juntos_dao_os_cinco_estados(self):
        assert set(ESTADOS_ABERTOS) | set(ESTADOS_FECHADOS) == set(ESTADOS)

    def test_nenhum_estado_esta_nos_dois(self):
        assert not set(ESTADOS_ABERTOS) & set(ESTADOS_FECHADOS)

    def test_o_que_esta_em_cada_grupo(self):
        """Escrito a mao a partir da issue #641: "Minha vez" traz o que NAO
        esta Concluida nem Cancelada, e o Historico traz essas duas."""
        assert set(ESTADOS_ABERTOS) == {"nova", "em_andamento", "aguardando"}
        assert set(ESTADOS_FECHADOS) == {"concluida", "cancelada"}


class TestPesoDaPrioridade:
    def test_a_ordem_e_alta_normal_baixa(self):
        """Os numeros sao escritos a mao, e nao lidos do proprio dicionario:
        cobrar `peso("alta") == PESO_DA_PRIORIDADE["alta"]` seria comparar a
        constante consigo mesma e passaria com qualquer ordem."""
        assert peso_da_prioridade("alta") == 0
        assert peso_da_prioridade("normal") == 1
        assert peso_da_prioridade("baixa") == 2

    def test_toda_prioridade_da_lista_fechada_tem_peso_proprio(self):
        """Piso: as tres da lista precisam de tres pesos distintos, senao duas
        delas empatariam e a ordem dependeria do acaso."""
        assert len({peso_da_prioridade(p) for p in PRIORIDADES}) == len(PRIORIDADES)

    @pytest.mark.parametrize("estranha", ("urgentissima", "", None))
    def test_prioridade_que_a_lista_nao_conhece_vai_para_o_fim(self, estranha):
        """Linha antiga, ou valor que entrou por fora do app. Ela aparece, mas
        depois de todas as conhecidas: sumir seria pior, e vir na frente
        empurraria as Altas para baixo."""
        assert peso_da_prioridade(estranha) > peso_da_prioridade("baixa")


def _resposta(autor_id: str | None, texto: str = "resposta", mencoes: list[str] | None = None) -> dict:
    return {"linha": "resposta", "autor_id": autor_id, "texto": texto, "mencoes": mencoes or []}


def _movimento(texto: str = "Pedro moveu para Aguardando") -> dict:
    return {"linha": "movimento", "autor_id": None, "texto": texto, "mencoes": []}


class TestEsperandoResposta:
    """ "Fui mencionado e ainda nao respondi DEPOIS da mencao" (issue #641).

    A conta e sobre a ORDEM das linhas, e nao sobre o relogio: o fio chega do
    banco ordenado por `criado_em`, e comparar instantes aqui traria de volta o
    problema da data ilegivel, que viraria "a mencao nunca foi respondida".
    """

    def test_sem_mencao_nenhuma_nao_e_a_minha_vez(self):
        linhas = [_resposta("P1", "oi"), _movimento()]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_mencionada_e_calada_e_a_minha_vez(self):
        linhas = [_resposta("P1", "@Sócia Vitta o que acha?", mencoes=["P2"])]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_some_quando_ela_responde_depois(self):
        linhas = [
            _resposta("P1", "@Sócia Vitta o que acha?", mencoes=["P2"]),
            _resposta("P2", "acho que sim"),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_resposta_antes_da_mencao_nao_conta(self):
        """O caso que separa "ja respondeu" de "respondeu sobre outra coisa":
        uma conta que so perguntasse "ela ja falou neste fio?" daria a mencao
        por atendida por uma frase escrita antes de alguem chamar."""
        linhas = [
            _resposta("P2", "passei por aqui"),
            _resposta("P1", "@Sócia Vitta e agora?", mencoes=["P2"]),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_vale_a_ultima_mencao_e_nao_a_primeira(self):
        """Ela respondeu a primeira chamada, e foi chamada de novo depois."""
        linhas = [
            _resposta("P1", "@Sócia Vitta olha isso", mencoes=["P2"]),
            _resposta("P2", "olhei"),
            _resposta("P1", "@Sócia Vitta e isto aqui?", mencoes=["P2"]),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_resposta_de_outra_pessoa_nao_atende_a_mencao(self):
        linhas = [
            _resposta("P1", "@Sócia Vitta o que acha?", mencoes=["P2"]),
            _resposta("P3", "eu acho que sim"),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_mencionar_a_si_mesma_nao_cria_vez(self):
        """Escrever "@Sócia Vitta" na propria resposta e citar-se, nao chamar:
        a Demanda cairia na aba de quem acabou de falar nela."""
        linhas = [_resposta("P2", "eu, @Sócia Vitta, fico com isso", mencoes=["P2"])]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_linha_que_nao_e_resposta_nao_atende_a_mencao(self):
        """So `resposta` responde. A linha automatica de movimento hoje vem com
        `autor_id` NULL, mas o fio pode ganhar outros tipos de linha, e uma
        delas assinada pela pessoa nao e ela dizendo nada a quem chamou."""
        linhas = [
            _resposta("P1", "@Sócia Vitta e agora?", mencoes=["P2"]),
            {"linha": "movimento", "autor_id": "P2", "texto": "moveu", "mencoes": []},
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_mencoes_ausentes_na_linha_nao_quebram(self):
        """Coluna NULL: o PostgREST devolve `None`, e `None` nao e iteravel."""
        linhas = [{"linha": "resposta", "autor_id": "P1", "texto": "oi", "mencoes": None}]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_fio_vazio(self):
        assert esperando_resposta_da_pessoa(linhas=[], pessoa_id="P2") is False


class TestMotivoDaMinhaVez:
    """Por que esta Demanda esta na minha aba.

    E o par na tela da regra do backend: sem ele, quem abre "Minha vez" ve um
    card cujo responsavel e OUTRA pessoa e nao descobre por que ele esta ali.
    """

    def test_sou_o_responsavel(self):
        assert motivo_da_minha_vez(responsavel_id="P2", pessoa_id="P2") == "responsavel"

    def test_fui_mencionada(self):
        assert motivo_da_minha_vez(responsavel_id="P1", pessoa_id="P2") == "mencao"

    def test_responsavel_nulo_nao_vira_responsavel(self):
        """`.eq`/`==` em coluna anulavel: uma Demanda sem responsavel nao e de
        ninguem, e um `pessoa_id` nulo nao pode casar com ela."""
        assert motivo_da_minha_vez(responsavel_id=None, pessoa_id="P2") == "mencao"


class TestFechamentoDaDemanda:
    """Quando e por quem a Demanda fechou (criterio: "cada linha do Historico
    mostra data e pessoa que concluiu ou cancelou")."""

    def test_concluida_traz_os_carimbos_de_conclusao(self):
        demanda = {
            "estado": "concluida",
            "concluida_em": "2026-09-08T10:00:00Z",
            "concluida_por": "P1",
            "cancelada_em": None,
            "cancelada_por": None,
        }
        assert fechamento_da_demanda(demanda) == ("2026-09-08T10:00:00Z", "P1")

    def test_cancelada_traz_os_carimbos_de_cancelamento(self):
        demanda = {
            "estado": "cancelada",
            "concluida_em": None,
            "concluida_por": None,
            "cancelada_em": "2026-09-08T11:00:00Z",
            "cancelada_por": "P2",
        }
        assert fechamento_da_demanda(demanda) == ("2026-09-08T11:00:00Z", "P2")

    def test_quem_manda_e_o_estado_e_nao_o_carimbo_preenchido(self):
        """Reabrir limpa os quatro carimbos, entao os dois pares nao deveriam
        estar preenchidos juntos. Se estiverem (linha suja, escrita por fora do
        app), o Historico conta o desfecho em que a Demanda ESTA, e nao o
        primeiro carimbo que encontrar."""
        demanda = {
            "estado": "cancelada",
            "concluida_em": "2026-09-01T10:00:00Z",
            "concluida_por": "P1",
            "cancelada_em": "2026-09-08T11:00:00Z",
            "cancelada_por": "P2",
        }
        assert fechamento_da_demanda(demanda) == ("2026-09-08T11:00:00Z", "P2")

    @pytest.mark.parametrize("aberto", ESTADOS_ABERTOS)
    def test_demanda_aberta_nao_tem_desfecho(self, aberto):
        demanda = {"estado": aberto, "concluida_em": "2026-09-01T10:00:00Z", "concluida_por": "P1"}
        assert fechamento_da_demanda(demanda) == (None, None)


class TestTextosDeResposta:
    def test_so_o_que_as_pessoas_escreveram(self):
        """A busca do Historico NAO varre a linha de movimento: o texto dela e
        montado pelo backend com o nome de quem moveu ("Pedro moveu para
        Concluída"), e busca por "Pedro" acharia toda Demanda que ele tocou,
        inclusive as em que ele nunca escreveu uma palavra."""
        linhas = [
            _resposta("P1", "decidimos manter o encerramento automático"),
            _movimento("Pedro moveu para Concluída"),
        ]
        assert textos_de_resposta(linhas) == ["decidimos manter o encerramento automático"]

    def test_texto_nulo_vira_vazio(self):
        assert textos_de_resposta([{"linha": "resposta", "texto": None}]) == [""]


class TestBuscaDoHistorico:
    """O que a busca procura (issue #641: titulo, descricao e Conversa)."""

    DEMANDA = {
        "titulo": "Encerrar conversas da Ana",
        "descricao": "O diretor precisa decidir o critério de encerramento.",
    }
    CONVERSA = ["Combinamos que a régua é de 24 horas."]

    def _casa(self, termo: str, demanda: dict | None = None, conversa: list[str] | None = None) -> bool:
        return demanda_casa_a_busca(
            demanda=demanda if demanda is not None else self.DEMANDA,
            textos_da_conversa=self.CONVERSA if conversa is None else conversa,
            termo=termo,
        )

    @pytest.mark.parametrize("vazio", ("", "   ", "\n\t"))
    def test_busca_vazia_traz_tudo(self, vazio):
        """Apagar a caixa de busca volta ao Historico inteiro, e nao a uma lista
        vazia: uma busca por nada nao e uma busca que nao achou nada."""
        assert self._casa(vazio) is True

    def test_acha_pelo_titulo(self):
        assert self._casa("encerrar conversas") is True

    def test_acha_pela_descricao(self):
        assert self._casa("critério de encerramento") is True

    def test_acha_pelo_texto_da_conversa(self):
        assert self._casa("régua") is True

    def test_termo_que_nao_esta_em_lugar_nenhum_nao_acha(self):
        """A irma de presenca das tres acima: sem ela, uma busca que dissesse
        "sim" para tudo passaria nas outras."""
        assert self._casa("ouvidoria") is False

    def test_nao_distingue_maiusculas(self):
        assert self._casa("ENCERRAR CONVERSAS") is True

    def test_termo_sem_acento_acha_texto_com_acento(self):
        assert self._casa("regua") is True

    def test_termo_com_acento_acha_texto_sem_acento(self):
        assert self._casa("Aná", demanda={"titulo": "Encerrar conversas da Ana", "descricao": None}) is True

    def test_espaco_em_volta_do_termo_nao_atrapalha(self):
        assert self._casa("   régua   ") is True

    def test_descricao_nula_nao_quebra_a_busca(self):
        assert self._casa("encerrar", demanda={"titulo": "Encerrar conversas", "descricao": None}) is True

    def test_sem_conversa_a_busca_ainda_le_titulo_e_descricao(self):
        assert self._casa("encerrar", conversa=[]) is True


def _para_ordenar(did: str, prioridade: str) -> dict:
    return {"id": did, "prioridade": prioridade}


class TestOrdenarMinhaVez:
    def test_alta_primeiro_baixa_por_ultimo(self):
        ordenadas = ordenar_minha_vez(
            [_para_ordenar("b", "baixa"), _para_ordenar("n", "normal"), _para_ordenar("a", "alta")]
        )
        assert [d["id"] for d in ordenadas] == ["a", "n", "b"]

    def test_dentro_da_prioridade_a_ordem_que_chegou_e_mantida(self):
        """A ordenacao e ESTAVEL de proposito: quem entrega a idade e a leitura
        do banco, ordenada por `criado_em` crescente. Uma ordenacao que
        embaralhasse os empates perderia o "mais velha primeiro" do criterio
        sem dizer nada."""
        ordenadas = ordenar_minha_vez(
            [
                _para_ordenar("velha", "normal"),
                _para_ordenar("alta-velha", "alta"),
                _para_ordenar("nova", "normal"),
                _para_ordenar("alta-nova", "alta"),
            ]
        )
        assert [d["id"] for d in ordenadas] == ["alta-velha", "alta-nova", "velha", "nova"]

    def test_prioridade_desconhecida_vai_para_o_fim(self):
        ordenadas = ordenar_minha_vez([_para_ordenar("x", "urgentissima"), _para_ordenar("b", "baixa")])
        assert [d["id"] for d in ordenadas] == ["b", "x"]


def _fechada(did: str, *, estado: str = "concluida", quando: str | None) -> dict:
    campo = "concluida_em" if estado == "concluida" else "cancelada_em"
    return {"id": did, "estado": estado, campo: quando}


class TestOrdenarHistorico:
    def test_a_que_fechou_por_ultimo_vem_primeiro(self):
        ordenadas = ordenar_historico(
            [
                _fechada("antiga", quando="2026-01-02T10:00:00Z"),
                _fechada("recente", quando="2026-09-08T10:00:00Z"),
                _fechada("meio", estado="cancelada", quando="2026-05-05T10:00:00Z"),
            ]
        )
        assert [d["id"] for d in ordenadas] == ["recente", "meio", "antiga"]

    def test_sem_data_de_fechamento_vai_para_o_fim(self):
        """Linha fechada por fora do app, sem carimbo. Ela aparece (nada some
        do Historico), mas nao na frente de quem tem data."""
        ordenadas = ordenar_historico(
            [_fechada("sem_data", quando=None), _fechada("com_data", quando="2026-01-02T10:00:00Z")]
        )
        assert [d["id"] for d in ordenadas] == ["com_data", "sem_data"]


# ─── 2. Supabase dublê e cenario ─────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    """PostgREST minimo: select/eq/in_/order, e nada mais. Estas duas rotas so
    LEEM: nem insert nem update, e por isso o dublê nao os tem."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._order: str | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order = coluna
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        casadas = [linha for linha in self._rows if self._casa(linha)]
        if self._order:
            casadas.sort(key=lambda linha: (linha.get(self._order) is None, linha.get(self._order)))
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []))


def _pessoa(pid: str, nome: str, *, access_profile: str | None = "super_admin") -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid}@hsm.com",
        "ativo": True,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
    }


PEDRO = _pessoa("P1", "Pedro Vitta")
SOCIA = _pessoa("P2", "Sócia Vitta")

BASE = "/api/admin/tecnologia"


def _demanda(did: str, **campos) -> dict:
    base = {
        "id": did,
        "titulo": "Encerrar conversas da Ana",
        "descricao": None,
        "tipo": "decisao",
        "produto_id": "prod-1",
        "estado": "nova",
        "responsavel_id": "P1",
        "autor_id": "P1",
        "prioridade": "normal",
        "prazo": None,
        "criado_em": "2026-09-01T09:00:00Z",
        "atualizado_em": "2026-09-01T09:00:00Z",
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
    }
    base.update(campos)
    return base


def _linha(did: str, **campos) -> dict:
    base = {
        "id": f"c-{did}",
        "demanda_id": did,
        "autor_id": "P1",
        "linha": "resposta",
        "texto": "uma resposta",
        "mencoes": [],
        "movimento_campo": None,
        "movimento_de": None,
        "movimento_para": None,
        "criado_em": "2026-09-02T09:00:00Z",
        "editado_em": None,
    }
    base.update(campos)
    return base


def _montar(
    *,
    logado: dict = PEDRO,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    produtos: list[dict] | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(tecnologia_router.router, prefix="/api")

    sb = _SupabaseMock(
        tabelas={
            "participantes": [dict(PEDRO), dict(SOCIA)],
            "tecnologia_produtos": [dict(p) for p in (produtos or [{"id": "prod-1", "nome": "Ana"}])],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        }
    )

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ─── 3. Minha vez, pela rota ─────────────────────────────────────────────────


class TestMinhaVezPelaRota:
    def test_traz_so_as_abertas_em_que_eu_sou_o_responsavel(self):
        client = _montar(
            logado=SOCIA,
            demandas=[
                _demanda("minha", responsavel_id="P2"),
                _demanda("da_outra", responsavel_id="P1"),
                _demanda("sem_dono", responsavel_id=None),
            ],
        )

        corpo = client.get(f"{BASE}/minha-vez").json()

        assert {d["id"] for d in corpo} == {"minha"}

    @pytest.mark.parametrize("fechado", ESTADOS_FECHADOS)
    def test_o_que_ja_fechou_nao_espera_por_ninguem(self, fechado):
        client = _montar(
            logado=SOCIA,
            demandas=[
                _demanda("aberta", responsavel_id="P2", estado="aguardando"),
                _demanda("fechada", responsavel_id="P2", estado=fechado),
            ],
        )

        corpo = client.get(f"{BASE}/minha-vez").json()

        # A irma de presenca: a aberta aparece no MESMO pedido, entao a
        # ausencia da fechada nao e uma lista vazia disfarcada.
        assert {d["id"] for d in corpo} == {"aberta"}

    def test_traz_tambem_a_demanda_em_que_fui_mencionada_e_nao_respondi(self):
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[_linha("d1", autor_id="P1", texto="@Sócia Vitta o que acha?", mencoes=["P2"])],
        )

        corpo = client.get(f"{BASE}/minha-vez").json()

        assert [d["id"] for d in corpo] == ["d1"]
        assert corpo[0]["motivo"] == "mencao"

    def test_a_mencao_some_da_minha_vez_quando_ela_responde(self):
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[
                _linha(
                    "d1",
                    id="c1",
                    autor_id="P1",
                    texto="@Sócia Vitta o que acha?",
                    mencoes=["P2"],
                    criado_em="2026-09-02T09:00:00Z",
                ),
                _linha("d1", id="c2", autor_id="P2", texto="acho que sim", criado_em="2026-09-03T09:00:00Z"),
            ],
        )

        assert client.get(f"{BASE}/minha-vez").json() == []

    def test_o_motivo_diz_por_que_o_card_esta_na_aba(self):
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("minha", responsavel_id="P2"), _demanda("chamada", responsavel_id="P1")],
            conversas=[_linha("chamada", autor_id="P1", texto="@Sócia Vitta olha", mencoes=["P2"])],
        )

        por_id = {d["id"]: d for d in client.get(f"{BASE}/minha-vez").json()}

        assert por_id["minha"]["motivo"] == "responsavel"
        assert por_id["chamada"]["motivo"] == "mencao"

    def test_a_ordem_e_prioridade_e_depois_idade(self):
        client = _montar(
            logado=SOCIA,
            demandas=[
                _demanda("normal_nova", responsavel_id="P2", prioridade="normal", criado_em="2026-09-05T09:00:00Z"),
                _demanda("alta_nova", responsavel_id="P2", prioridade="alta", criado_em="2026-09-06T09:00:00Z"),
                _demanda("baixa_velha", responsavel_id="P2", prioridade="baixa", criado_em="2026-01-01T09:00:00Z"),
                _demanda("alta_velha", responsavel_id="P2", prioridade="alta", criado_em="2026-02-02T09:00:00Z"),
                _demanda("normal_velha", responsavel_id="P2", prioridade="normal", criado_em="2026-03-03T09:00:00Z"),
            ],
        )

        corpo = client.get(f"{BASE}/minha-vez").json()

        assert [d["id"] for d in corpo] == [
            "alta_velha",
            "alta_nova",
            "normal_velha",
            "normal_nova",
            "baixa_velha",
        ]

    def test_a_lista_e_do_participante_logado(self):
        """O criterio inteiro desta aba. Duas pessoas, o mesmo Quadro, duas
        listas: sem isso, "Minha vez" seria "a vez de alguem"."""
        demandas = [_demanda("do_pedro", responsavel_id="P1"), _demanda("da_socia", responsavel_id="P2")]

        do_pedro = _montar(logado=PEDRO, demandas=demandas).get(f"{BASE}/minha-vez").json()
        da_socia = _montar(logado=SOCIA, demandas=demandas).get(f"{BASE}/minha-vez").json()

        assert [d["id"] for d in do_pedro] == ["do_pedro"]
        assert [d["id"] for d in da_socia] == ["da_socia"]

    def test_traz_o_nome_do_produto_e_do_responsavel(self):
        client = _montar(logado=SOCIA, demandas=[_demanda("d1", responsavel_id="P2")])

        corpo = client.get(f"{BASE}/minha-vez").json()

        assert corpo[0]["produto_nome"] == "Ana"
        assert corpo[0]["responsavel_nome"] == "Sócia Vitta"

    @pytest.mark.parametrize(
        "filtro,esperado",
        (
            ({}, {"d1", "d2"}),
            ({"tipo": "defeito"}, {"d2"}),
            ({"produto_id": "prod-2"}, {"d2"}),
            ({"responsavel_id": "P1"}, set()),
        ),
    )
    def test_os_filtros_da_aba_valem_aqui_tambem(self, filtro, esperado):
        """Os filtros sao COMPARTILHADOS entre as tres abas (issue #639), e a
        aba que os ignorasse mostraria uma lista que contradiz os campos
        preenchidos logo acima dela."""
        client = _montar(
            logado=SOCIA,
            produtos=[{"id": "prod-1", "nome": "Ana"}, {"id": "prod-2", "nome": "POPs"}],
            demandas=[
                _demanda("d1", responsavel_id="P2", tipo="decisao", produto_id="prod-1"),
                _demanda("d2", responsavel_id="P2", tipo="defeito", produto_id="prod-2"),
            ],
        )

        corpo = client.get(f"{BASE}/minha-vez", params=filtro).json()

        assert {d["id"] for d in corpo} == esperado


# ─── 4. Historico, pela rota ─────────────────────────────────────────────────


class TestHistoricoPelaRota:
    def _cenario(self, **kwargs) -> TestClient:
        return _montar(
            demandas=[
                _demanda(
                    "fechada",
                    titulo="Encerrar conversas da Ana",
                    descricao="O diretor decide o critério.",
                    estado="concluida",
                    concluida_em="2026-09-08T10:00:00Z",
                    concluida_por="P2",
                ),
                _demanda(
                    "desistida",
                    titulo="Trocar o logotipo",
                    estado="cancelada",
                    cancelada_em="2026-09-07T10:00:00Z",
                    cancelada_por="P1",
                ),
                _demanda("aberta", titulo="Integração com o MV", estado="aguardando"),
            ],
            conversas=[_linha("fechada", texto="Combinamos a régua de 24 horas.")],
            **kwargs,
        )

    def test_traz_so_concluida_e_cancelada(self):
        corpo = self._cenario().get(f"{BASE}/historico").json()

        assert {d["id"] for d in corpo} == {"fechada", "desistida"}

    def test_cada_linha_diz_quando_e_por_quem_fechou(self):
        por_id = {d["id"]: d for d in self._cenario().get(f"{BASE}/historico").json()}

        assert por_id["fechada"]["fechada_em"] == "2026-09-08T10:00:00Z"
        assert por_id["fechada"]["fechada_por_nome"] == "Sócia Vitta"
        assert por_id["desistida"]["fechada_em"] == "2026-09-07T10:00:00Z"
        assert por_id["desistida"]["fechada_por_nome"] == "Pedro Vitta"

    @pytest.mark.parametrize(
        "termo,esperado",
        (
            ("encerrar", {"fechada"}),
            ("critério", {"fechada"}),
            ("régua", {"fechada"}),
            ("regua", {"fechada"}),
            ("logotipo", {"desistida"}),
            ("integração", set()),
            ("ouvidoria", set()),
        ),
    )
    def test_a_busca_varre_titulo_descricao_e_conversa(self, termo, esperado):
        """ "integração" esta no titulo da Demanda ABERTA: a busca nao pode
        trazer de volta o que o Historico nao mostra."""
        corpo = self._cenario().get(f"{BASE}/historico", params={"busca": termo}).json()

        assert {d["id"] for d in corpo} == esperado

    @pytest.mark.parametrize("vazio", ("", "   "))
    def test_busca_vazia_traz_o_historico_inteiro(self, vazio):
        corpo = self._cenario().get(f"{BASE}/historico", params={"busca": vazio}).json()

        assert {d["id"] for d in corpo} == {"fechada", "desistida"}

    def test_a_ordem_e_a_que_fechou_por_ultimo_primeiro(self):
        corpo = self._cenario().get(f"{BASE}/historico").json()

        assert [d["id"] for d in corpo] == ["fechada", "desistida"]

    def test_os_filtros_da_aba_valem_aqui_tambem(self):
        client = _montar(
            produtos=[{"id": "prod-1", "nome": "Ana"}, {"id": "prod-2", "nome": "POPs"}],
            demandas=[
                _demanda("d1", estado="concluida", produto_id="prod-1", concluida_em="2026-09-08T10:00:00Z"),
                _demanda("d2", estado="concluida", produto_id="prod-2", concluida_em="2026-09-07T10:00:00Z"),
            ],
        )

        corpo = client.get(f"{BASE}/historico", params={"produto_id": "prod-2"}).json()

        assert {d["id"] for d in corpo} == {"d2"}

    def test_a_busca_nao_le_a_linha_de_movimento(self):
        """O texto do movimento carrega o nome de quem moveu. Se ele entrasse
        na busca, procurar "Pedro" acharia toda Demanda que ele tocou, mesmo as
        em que ele nunca escreveu uma palavra."""
        client = _montar(
            demandas=[
                _demanda("d1", titulo="Trocar o logotipo", estado="concluida", concluida_em="2026-09-08T10:00:00Z")
            ],
            conversas=[
                _linha("d1", linha="movimento", autor_id=None, texto="Pedro Vitta moveu para Concluída"),
            ],
        )

        assert client.get(f"{BASE}/historico", params={"busca": "Pedro"}).json() == []
        # A irma de presenca, no mesmo cenario: a busca funciona, ela so nao
        # olha a linha de movimento.
        assert [d["id"] for d in client.get(f"{BASE}/historico", params={"busca": "logotipo"}).json()] == ["d1"]

    def test_fechada_sem_carimbo_de_pessoa_ainda_aparece(self):
        """Linha antiga ou escrita por fora do app: o Historico nao esconde a
        Demanda por falta de carimbo, e a tela e que diz que nao ha registro."""
        client = _montar(
            demandas=[_demanda("d1", estado="concluida", concluida_em="2026-09-08T10:00:00Z", concluida_por=None)]
        )

        corpo = client.get(f"{BASE}/historico").json()

        assert [d["id"] for d in corpo] == ["d1"]
        assert corpo[0]["fechada_por_nome"] is None
