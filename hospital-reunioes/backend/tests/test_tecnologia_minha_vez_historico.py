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


def _resposta(autor_id: str | None, texto: str = "resposta", mencoes: list[str] | None = None, **campos) -> dict:
    return {"linha": "resposta", "autor_id": autor_id, "texto": texto, "mencoes": mencoes or [], **campos}


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


class TestAMencaoQueEntrouNaCorrecao:
    """A mencao acrescentada na janela de 10 minutos conta a partir do
    `editado_em` (issue #670).

    A correcao NAO mexe no `criado_em`, entao a linha fica onde estava na fila.
    Sem olhar o `editado_em`, uma resposta escrita ENTRE o envio e a correcao
    ficaria depois da mencao na ordem e daria por atendida uma chamada que ainda
    nao existia quando ela foi escrita.

    A linha nao guarda QUAIS mencoes entraram na correcao (nao ha coluna para
    isso), entao toda mencao de linha corrigida conta do `editado_em`. Uma
    correcao de virgula pode trazer de volta uma chamada ja respondida, e esse e
    o lado seguro do erro: a Demanda reaparece na aba, em vez de uma chamada
    sumir de vista.
    """

    ENVIO = "2026-09-02T09:00:00Z"
    ANTES_DA_CORRECAO = "2026-09-02T09:03:00Z"
    CORRECAO = "2026-09-02T09:05:00Z"
    DEPOIS_DA_CORRECAO = "2026-09-02T09:07:00Z"

    def _mencao_corrigida(self, **campos) -> dict:
        datas = {"criado_em": self.ENVIO, "editado_em": self.CORRECAO, **campos}
        return _resposta("P1", "@Sócia Vitta e agora?", mencoes=["P2"], **datas)

    def test_a_resposta_anterior_a_correcao_nao_atende_a_mencao_nova(self):
        """O caso da issue: a Sócia falou no fio antes de ser chamada, e a
        chamada so passou a existir na correcao."""
        linhas = [
            self._mencao_corrigida(),
            _resposta("P2", "nao era comigo", criado_em=self.ANTES_DA_CORRECAO),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is True

    def test_a_resposta_posterior_a_correcao_encerra_a_vez(self):
        """A irma de presenca: sem ela, uma regra que ignorasse a resposta
        depois da correcao prenderia a Demanda na aba para sempre."""
        linhas = [
            self._mencao_corrigida(),
            _resposta("P2", "agora vi", criado_em=self.DEPOIS_DA_CORRECAO),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_a_linha_que_ninguem_corrigiu_continua_valendo_pela_ordem(self):
        """Sem `editado_em`, nada de relogio: quem manda e a POSICAO das linhas,
        como antes desta issue."""
        linhas = [
            _resposta("P1", "@Sócia Vitta e agora?", mencoes=["P2"], criado_em=self.CORRECAO, editado_em=None),
            _resposta("P2", "respondi", criado_em=self.ENVIO),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_o_carimbo_que_vale_e_o_da_ultima_mencao(self):
        """Vale a ultima chamada, e o `editado_em` e o DELA.

        Duas chamadas para a mesma pessoa: a segunda nunca foi corrigida, entao
        cai na ordem, e a resposta que veio depois dela encerra a vez. A
        primeira linha so foi corrigida MAIS TARDE, e uma regra que lesse o
        carimbo da linha errada deixaria a Demanda presa na aba em cima de um
        instante que nao e o da chamada que vale.
        """
        linhas = [
            _resposta("P1", "@Sócia Vitta e agora?", mencoes=["P2"], criado_em=self.ENVIO, editado_em=self.CORRECAO),
            _resposta(
                "P1",
                "@Sócia Vitta, e isto aqui?",
                mencoes=["P2"],
                criado_em=self.ANTES_DA_CORRECAO,
                editado_em=None,
            ),
            _resposta("P2", "vi as duas", criado_em="2026-09-02T09:04:00Z"),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_data_ilegivel_na_correcao_cai_na_ordem_das_linhas(self):
        """A data quebrada nao pode prender a Demanda na aba: sem instante
        legivel, vale a ordem, que e a regra que sempre valeu."""
        linhas = [
            self._mencao_corrigida(editado_em="ontem"),
            _resposta("P2", "respondi", criado_em=self.ANTES_DA_CORRECAO),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False

    def test_resposta_com_data_ilegivel_conta_como_atendida(self):
        """O mesmo cuidado pelo outro lado: e a linha da RESPOSTA que vem sem
        instante legivel, e a Demanda tambem nao fica presa."""
        linhas = [
            self._mencao_corrigida(),
            _resposta("P2", "respondi", criado_em="ontem"),
        ]
        assert esperando_resposta_da_pessoa(linhas=linhas, pessoa_id="P2") is False


class TestMotivoDaMinhaVez:
    """Por que esta Demanda esta na minha aba.

    E o par na tela da regra do backend: sem ele, quem abre "Minha vez" ve um
    card cujo responsavel e OUTRA pessoa e nao descobre por que ele esta ali.
    """

    def test_sou_o_responsavel(self):
        assert motivo_da_minha_vez(responsavel_id="P2", pessoa_id="P2") == "responsavel"

    def test_fui_mencionada(self):
        assert motivo_da_minha_vez(responsavel_id="P1", pessoa_id="P2") == "mencao"

    def test_demanda_sem_responsavel_cai_como_mencao(self):
        """Demanda sem responsavel nao e de ninguem.

        Isto NAO e uma guarda: `pessoa_id` vem do `ator["id"]` da sessao e nunca
        e nulo, entao `None == "P2"` ja e False. O caso esta escrito porque a
        coluna e anulavel e a linha existe no banco, e nao porque haja codigo
        defendendo dela.
        """
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
    """PostgREST minimo: select/eq/in_/order/range, e nada mais. Estas duas
    rotas so LEEM: nem insert nem update, e por isso o dublê nao os tem.

    `teto` imita o `PGRST_DB_MAX_ROWS` do `supabase/config.toml`: o servidor
    corta a resposta nesse numero de linhas, com HTTP 200 e sem aviso nenhum. E
    o modo de falha que a paginacao da issue #430 veio consertar, e a unica
    forma de prova-lo aqui e ter um dublê que corte de verdade.

    `order` guarda a LISTA de colunas, e nao uma so: o desempate por `id` e o
    que faz o recorte em paginas ser estavel, e um dublê que guardasse apenas a
    ultima chamada nao veria diferenca entre ter e nao ter desempate.
    """

    def __init__(self, rows: list[dict], teto: int | None = None, selects: list[str] | None = None):
        self._rows = rows
        self._teto = teto
        self._selects = selects
        self._colunas = "*"
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._order: list[str] = []
        self._range: tuple[int, int] | None = None

    def select(self, *a, **_kw):
        self._colunas = str(a[0]) if a else "*"
        if self._selects is not None:
            self._selects.append(self._colunas)
        return self

    def _projetado(self, linha: dict) -> dict:
        """A linha com as colunas que a consulta PEDIU, e so elas.

        E o que o PostgREST faz, e sem isso a lista de colunas de cada aba nao
        seria testavel: com o dublê devolvendo tudo de qualquer jeito, tirar
        `mencoes` do `select` da "Minha vez" nao mudaria resposta nenhuma.
        """
        if self._colunas == "*":
            return dict(linha)
        pedidas = [c.strip() for c in self._colunas.split(",")]
        return {c: linha.get(c) for c in pedidas}

    def order(self, coluna, **_kw):
        self._order.append(coluna)
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def range(self, inicio, fim):
        self._range = (inicio, fim)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        casadas = [linha for linha in self._rows if self._casa(linha)]
        # Da ultima chave para a primeira, que e como se compoe ordenacao
        # estavel: o `sort` do Python preserva empates.
        for coluna in reversed(self._order):
            casadas.sort(key=lambda linha, c=coluna: (linha.get(c) is None, linha.get(c)))
        if self._range is not None:
            inicio, fim = self._range
            casadas = casadas[inicio : fim + 1]
        # O corte do servidor vem DEPOIS da janela pedida, como no PostgREST de
        # verdade: quem pede mil linhas com teto de duas recebe duas, e nada na
        # resposta diz que faltou.
        if self._teto is not None:
            casadas = casadas[: self._teto]
        return _Result(data=[self._projetado(linha) for linha in casadas])


class _SupabaseMock:
    """O Supabase dublado, com o registro do que cada consulta PEDIU.

    `selects_de` guarda a lista de colunas de cada leitura por tabela: e o que
    permite cobrar que "Minha vez" nao peca o `texto` da Conversa, que e um
    contrato com o SERVIDOR (o dado que atravessa a rede), e nao um detalhe
    interno.
    """

    def __init__(self, tabelas: dict[str, list[dict]], teto: int | None = None):
        self.tabelas = tabelas
        self.teto = teto
        self.selects: dict[str, list[str]] = {}

    def selects_de(self, tabela: str) -> list[str]:
        return self.selects.get(tabela, [])

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []), self.teto, self.selects.setdefault(nome, []))


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
    teto: int | None = None,
) -> TestClient:
    """A tela pronta. Quem precisa olhar o que as consultas PEDIRAM usa o
    `_montar_com_duble`, que devolve o dublê junto."""
    return _montar_com_duble(logado=logado, demandas=demandas, conversas=conversas, produtos=produtos, teto=teto)[0]


def _montar_com_duble(
    *,
    logado: dict = PEDRO,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    produtos: list[dict] | None = None,
    teto: int | None = None,
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(tecnologia_router.router, prefix="/api")

    sb = _SupabaseMock(
        tabelas={
            "participantes": [dict(PEDRO), dict(SOCIA)],
            "tecnologia_produtos": [dict(p) for p in (produtos or [{"id": "prod-1", "nome": "Ana"}])],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        },
        teto=teto,
    )

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


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


# ─── 5. A ordem do fio e o teto do PostgREST (rodada 1 de fix) ───────────────


class TestAOrdemDoFio:
    """A regra da mencao conta a POSICAO das linhas, entao a leitura do fio
    precisa PEDIR ordem.

    Sem `ORDER BY`, o PostgREST devolve na ordem fisica do heap, que muda depois
    de um `UPDATE`, e a Conversa tem porta de `UPDATE` (a correcao de 10 minutos
    da issue #638): corrigir uma resposta pode empurrar a linha para o fim, e a
    mencao ja respondida voltaria a prender a Demanda em "Minha vez".

    Nos dois testes abaixo as linhas entram na lista na ordem ERRADA, com o
    `criado_em` dizendo o contrario. Todo cenario dos outros testes monta o fio
    ja em ordem cronologica, e com a entrada ja ordenada o `.order` fica
    invisivel: apagar da consulta nao muda resposta nenhuma.

    Os `id` sao escolhidos de proposito para DISCORDAR do relogio nos dois
    casos: assim, uma consulta que ordenasse so pelo `id` (o que sobra se o
    `criado_em` sair do `_fio_ordenado`) responde errado, em vez de acertar por
    acaso.
    """

    MENCAO = dict(autor_id="P1", texto="@Sócia Vitta o que acha?", mencoes=["P2"])
    RESPOSTA = dict(autor_id="P2", texto="acho que sim")

    def test_a_resposta_depois_da_mencao_encerra_a_vez_mesmo_chegando_primeiro(self):
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[
                # Na entrada, a resposta vem antes; no relogio, ela vem depois.
                # E o `id` dela e MENOR, para a ordem por id tambem errar.
                _linha("d1", id="c1", **self.RESPOSTA, criado_em="2026-09-03T09:00:00Z"),
                _linha("d1", id="c2", **self.MENCAO, criado_em="2026-09-02T09:00:00Z"),
            ],
        )

        assert client.get(f"{BASE}/minha-vez").json() == []

    def test_a_resposta_antes_da_mencao_mantem_a_vez_mesmo_chegando_por_ultimo(self):
        """A irma de presenca da de cima, com o MESMO desalinho entre a ordem da
        entrada e a do relogio. Sem ela, uma consulta que devolvesse o fio ao
        contrario passaria naquela por acaso, e as duas juntas so passam quando
        a ordem vem do `criado_em`."""
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[
                # Na entrada, a mencao vem antes; no relogio, ela vem depois. O
                # `id` dela e MENOR, entao a ordem por id tambem erra.
                _linha("d1", id="c1", **self.MENCAO, criado_em="2026-09-03T09:00:00Z"),
                _linha("d1", id="c2", **self.RESPOSTA, criado_em="2026-09-02T09:00:00Z"),
            ],
        )

        assert [d["id"] for d in client.get(f"{BASE}/minha-vez").json()] == ["d1"]

    def test_duas_linhas_no_mesmo_instante_sao_desempatadas_pelo_id(self):
        """`criado_em` sozinho nao e chave unica. Duas linhas gravadas no mesmo
        instante deixariam a regra entregue ao acaso do plano do Postgres, e o
        recorte em paginas do `ler_tudo` exige ordem por chave unica, senao a
        pagina seguinte repete ou pula linha.

        Aqui a resposta tem `id` MAIOR que o da mencao, entao com o desempate
        ela fica depois: a vez esta encerrada."""
        client = _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[
                _linha("d1", id="c2-resposta", autor_id="P2", texto="acho que sim", criado_em="2026-09-02T09:00:00Z"),
                _linha(
                    "d1",
                    id="c1-mencao",
                    autor_id="P1",
                    texto="@Sócia Vitta o que acha?",
                    mencoes=["P2"],
                    criado_em="2026-09-02T09:00:00Z",
                ),
            ],
        )

        assert client.get(f"{BASE}/minha-vez").json() == []


class TestAMencaoDaCorrecaoPelaRota:
    """A mesma regra da correcao, pela rota (issue #670).

    A prova pura nao basta aqui: a "Minha vez" le o fio com uma LISTA de
    colunas (`COLUNAS_DO_FIO_PARA_MENCAO`), o dublê projeta como o PostgREST, e
    uma regra certa em cima de um `select` que nao pede `editado_em` responde
    "ninguem te chamou" com a chamada gravada no banco.
    """

    ENVIO = "2026-09-02T09:00:00Z"
    ANTES_DA_CORRECAO = "2026-09-02T09:03:00Z"
    CORRECAO = "2026-09-02T09:05:00Z"
    DEPOIS_DA_CORRECAO = "2026-09-02T09:07:00Z"

    def _client(self, resposta_em: str):
        return _montar(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[
                _linha(
                    "d1",
                    id="c1",
                    autor_id="P1",
                    texto="@Sócia Vitta e agora?",
                    mencoes=["P2"],
                    criado_em=self.ENVIO,
                    editado_em=self.CORRECAO,
                ),
                _linha("d1", id="c2", autor_id="P2", texto="nao era comigo", criado_em=resposta_em),
            ],
        )

    def test_a_demanda_aparece_para_quem_a_correcao_chamou(self):
        client = self._client(self.ANTES_DA_CORRECAO)

        assert [d["id"] for d in client.get(f"{BASE}/minha-vez").json()] == ["d1"]

    def test_e_sai_quando_a_resposta_veio_depois_da_correcao(self):
        client = self._client(self.DEPOIS_DA_CORRECAO)

        assert client.get(f"{BASE}/minha-vez").json() == []


class TestOTetoDoPostgrest:
    """O `PGRST_DB_MAX_ROWS` corta a resposta com HTTP 200 e sem aviso nenhum
    (issue #430, `app/services/paginacao.py`).

    Aqui a leitura NAO falha: ela volta menor. Uma aba que afirmasse "nada
    esperando por você" ou "a busca não achou" em cima de uma resposta cortada
    estaria dizendo um fato que o backend nao verificou, que e a mesma familia
    das frases de vazio que esta fatia ja segura quando ha erro.

    O teto e de 2 linhas em vez das 1000 de producao porque o modo de falha e o
    mesmo e o cenario cabe na cabeca: o que se prova e que a leitura continua
    inteira com o servidor cortando, e nao um numero especifico.
    """

    def test_o_duble_corta_de_verdade(self):
        """O controle das tres abaixo: se o dublê nao cortasse, elas passariam
        sem exercitar nada, e a paginacao ficaria "provada" sobre um servidor
        que devolve tudo de qualquer jeito."""
        sb = _SupabaseMock({"t": [{"id": f"x{i}"} for i in range(5)]}, teto=2)

        assert len(sb.table("t").select("*").execute().data) == 2
        # Sem teto, as cinco voltam: o corte e do dublê configurado, e nao da
        # tabela ter menos linhas.
        assert len(_SupabaseMock({"t": [{"id": f"x{i}"} for i in range(5)]}).table("t").select("*").execute().data) == 5

    def test_minha_vez_nao_perde_a_mencao_que_ficou_alem_do_teto(self):
        """A ordem do fio e global e CRESCENTE, entao o corte come as linhas
        mais NOVAS de todas as Demandas juntas: exatamente as mencoes recentes,
        que sao as que criam a vez. Cada arrastar no Quadro escreve uma linha de
        movimento, entao mil linhas nao e um numero distante."""
        client = _montar(
            logado=SOCIA,
            teto=2,
            demandas=[_demanda(f"d{i}", responsavel_id="P1") for i in range(3)],
            conversas=[
                _linha("d0", id="c0", linha="movimento", autor_id=None, criado_em="2026-09-01T09:00:00Z"),
                _linha("d1", id="c1", linha="movimento", autor_id=None, criado_em="2026-09-02T09:00:00Z"),
                # A mencao e a linha mais NOVA de todas: e a primeira a cair no
                # corte.
                _linha(
                    "d2",
                    id="c2",
                    autor_id="P1",
                    texto="@Sócia Vitta o que acha?",
                    mencoes=["P2"],
                    criado_em="2026-09-03T09:00:00Z",
                ),
            ],
        )

        assert [d["id"] for d in client.get(f"{BASE}/minha-vez").json()] == ["d2"]

    def test_o_historico_nao_perde_as_demandas_alem_do_teto(self):
        client = _montar(
            teto=2,
            demandas=[
                _demanda(f"d{i}", estado="concluida", concluida_em=f"2026-09-0{i + 1}T10:00:00Z") for i in range(3)
            ],
        )

        corpo = client.get(f"{BASE}/historico").json()

        assert {d["id"] for d in corpo} == {"d0", "d1", "d2"}

    def test_a_busca_acha_o_que_ficou_alem_do_teto(self):
        """O mesmo corte pelo outro lado: sem paginacao, a busca diria "não
        achei" sobre uma Conversa que ela nem chegou a ler inteira."""
        client = _montar(
            teto=2,
            demandas=[
                _demanda(f"d{i}", titulo=f"Demanda {i}", estado="concluida", concluida_em=f"2026-09-0{i + 1}T10:00:00Z")
                for i in range(3)
            ],
            conversas=[
                _linha("d0", id="c0", texto="conversa antiga", criado_em="2026-09-01T09:00:00Z"),
                _linha("d1", id="c1", texto="outra conversa", criado_em="2026-09-02T09:00:00Z"),
                _linha("d2", id="c2", texto="combinamos a régua de 24 horas", criado_em="2026-09-03T09:00:00Z"),
            ],
        )

        corpo = client.get(f"{BASE}/historico", params={"busca": "régua"}).json()

        assert [d["id"] for d in corpo] == ["d2"]


class TestAsColunasDoFio:
    """Cada aba pede do fio so o que ela le.

    `select("*")` traria o `texto` (ate 5000 caracteres por resposta) de toda
    Demanda aberta em TODA abertura de "Minha vez", que nao le o texto de nada.
    Na conta do revisor de seguranca, 300 Demandas com 20 respostas cada dao 30
    MB pela rede a cada carregamento, por pessoa. Menos dado tambem e menos
    chance de bater no teto de linhas do PostgREST.

    Sao duas provas diferentes, e as duas fazem falta: que a consulta PEDE as
    colunas certas (contrato com o servidor, o que atravessa a rede) e que a
    regra continua funcionando SO com elas (o dublê projeta, entao coluna que
    faltasse na lista sumiria da linha).
    """

    def _cenario_da_mencao(self) -> tuple[TestClient, _SupabaseMock]:
        return _montar_com_duble(
            logado=SOCIA,
            demandas=[_demanda("d1", responsavel_id="P1")],
            conversas=[_linha("d1", autor_id="P1", texto="@Sócia Vitta o que acha?", mencoes=["P2"])],
        )

    def test_minha_vez_nao_pede_o_texto_da_conversa(self):
        client, sb = self._cenario_da_mencao()

        client.get(f"{BASE}/minha-vez")
        pedidos = sb.selects_de("tecnologia_conversas")

        assert pedidos, "a rota nem leu a Conversa: a asserção abaixo passaria sobre nada"
        for pedido in pedidos:
            assert "texto" not in pedido
            # A irma de presenca: ela pede o que a regra usa, entao "sem texto"
            # nao e "sem coluna nenhuma".
            assert "mencoes" in pedido

    def test_a_regra_da_mencao_funciona_so_com_as_colunas_pedidas(self):
        """O dublê projeta como o PostgREST: se `mencoes` ou `autor_id` saissem
        da lista, a linha chegaria sem eles e a mencao sumiria."""
        client, _ = self._cenario_da_mencao()

        assert [d["id"] for d in client.get(f"{BASE}/minha-vez").json()] == ["d1"]

    def test_a_busca_do_historico_pede_o_texto(self):
        """O par do primeiro: a busca varre o texto das respostas, entao aqui a
        coluna TEM que vir. Uma lista de colunas cravada sem `texto` nas duas
        abas passaria naquele teste e quebraria a busca."""
        client, sb = _montar_com_duble(
            demandas=[_demanda("d1", estado="concluida", concluida_em="2026-09-08T10:00:00Z")],
            conversas=[_linha("d1", texto="combinamos a régua de 24 horas")],
        )

        corpo = client.get(f"{BASE}/historico", params={"busca": "régua"}).json()

        assert [d["id"] for d in corpo] == ["d1"]
        assert all("texto" in pedido for pedido in sb.selects_de("tecnologia_conversas"))

    def test_sem_termo_de_busca_o_historico_nem_le_a_conversa(self):
        """A leitura do fio so acontece quando ha o que procurar nele: abrir a
        aba sem buscar nada nao paga a Conversa inteira do Historico."""
        client, sb = _montar_com_duble(
            demandas=[_demanda("d1", estado="concluida", concluida_em="2026-09-08T10:00:00Z")],
            conversas=[_linha("d1", texto="combinamos a régua de 24 horas")],
        )

        client.get(f"{BASE}/historico")

        assert sb.selects_de("tecnologia_conversas") == []
        # A irma de presenca: com termo, ela le.
        client.get(f"{BASE}/historico", params={"busca": "régua"})
        assert sb.selects_de("tecnologia_conversas") != []


class TestMinhaVezEAutorizacaoNaoFiltro:
    """ "Minha vez" e a caixa de entrada de QUEM ESTA LOGADO, e nao uma consulta
    parametrizavel por pessoa.

    Os tres filtros da aba (`tipo`, `produto_id`, `responsavel_id`) so
    ESTREITAM a lista, e o `responsavel_id` e o unico deles que fala de gente:
    ele e a porta por onde um "me mostre a vez de outra pessoa" entraria. Nao
    entra, e e isto que fica preso aqui.

    Nao e sigilo: dentro da aba todo mundo ve tudo (ADR 0050, decisao 11), e
    quem quiser as Demandas de outra pessoa pede `/demandas?responsavel_id=`,
    que e o Quadro e existe para isso. E que "Minha vez" tem que continuar
    querendo dizer MINHA vez: uma aba cujo dono muda conforme o parametro nao
    responde mais a pergunta que ela promete responder, e o e-mail e as
    contagens que vierem depois passariam a falar da caixa de outra pessoa.
    """

    def _cenario(self, logado: dict) -> TestClient:
        return _montar(
            logado=logado,
            demandas=[
                _demanda("do_pedro", responsavel_id="P1"),
                _demanda("da_socia", responsavel_id="P2"),
                _demanda("chamou_o_pedro", responsavel_id="P2"),
            ],
            conversas=[
                _linha("chamou_o_pedro", autor_id="P2", texto="@Pedro Vitta o que acha?", mencoes=["P1"]),
            ],
        )

    def test_pedir_com_o_id_de_outra_pessoa_nao_devolve_a_vez_dela(self):
        """O caso que prende a propriedade. Pedro pede `?responsavel_id=P2`: o
        que volta e a INTERSECAO com a vez dele (a Demanda em que a Sócia o
        chamou), e nunca `da_socia`, que e a vez da Sócia e de mais ninguem."""
        corpo = self._cenario(PEDRO).get(f"{BASE}/minha-vez", params={"responsavel_id": "P2"}).json()

        assert [d["id"] for d in corpo] == ["chamou_o_pedro"]
        assert "da_socia" not in {d["id"] for d in corpo}

    def test_o_par_de_presenca_o_filtro_com_o_proprio_id_funciona(self):
        """Sem esta, uma rota que devolvesse lista vazia para qualquer
        `responsavel_id` passaria na de cima, e o teste estaria provando que o
        filtro nao funciona, e nao que a autorizacao vale."""
        corpo = self._cenario(PEDRO).get(f"{BASE}/minha-vez", params={"responsavel_id": "P1"}).json()

        assert [d["id"] for d in corpo] == ["do_pedro"]

    def test_sem_parametro_nenhum_cada_um_ve_a_propria_vez(self):
        """O terceiro lado: as duas listas inteiras, para o filtro acima nao ser
        a unica coisa medida."""
        do_pedro = self._cenario(PEDRO).get(f"{BASE}/minha-vez").json()
        da_socia = self._cenario(SOCIA).get(f"{BASE}/minha-vez").json()

        assert {d["id"] for d in do_pedro} == {"do_pedro", "chamou_o_pedro"}
        assert {d["id"] for d in da_socia} == {"da_socia", "chamou_o_pedro"}

    def test_o_id_de_outra_pessoa_nao_troca_o_dono_do_motivo(self):
        """O `motivo` continua respondendo "por que isto esta na MINHA aba", e
        nao "quem e o responsavel": pedindo com o id da Sócia, a Demanda em que
        ela chamou o Pedro continua marcada como mencao PARA ELE."""
        corpo = self._cenario(PEDRO).get(f"{BASE}/minha-vez", params={"responsavel_id": "P2"}).json()

        assert corpo[0]["motivo"] == "mencao"
