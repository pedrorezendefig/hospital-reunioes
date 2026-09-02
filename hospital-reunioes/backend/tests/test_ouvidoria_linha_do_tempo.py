"""A linha do tempo do caso (issue #485, PRD #470, RN-63 a RN-65).

A trilha de movimentos existe desde a migration 064 e nunca foi LIDA por
ninguém: o caso guardava a própria história e não a mostrava (diagnóstico da
Diretoria, D-08). Esta suíte cobre a rota que a lê e o serviço puro que a
traduz em eventos.

O seam é a rota, como nas fatias anteriores da Ouvidoria. Os movimentos entram
direto na tabela do fake quando o que se prova é a LEITURA (ordem, autor,
tempo, anonimização), e pelo fluxo real de encerramento quando o que se prova é
a ESCRITA: o texto que o ouvidor manda ao manifestante passou a entrar na
trilha nesta fatia, e um teste que injetasse o movimento pronto não provaria
isso.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_respostas  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

AGORA = dt.datetime(2026, 8, 31, 17, 0, tzinfo=dt.UTC)

# Os instantes da tramitação, em hora de Brasília (o expediente é 8h as 17h).
# Cada par vira uma conta de minutos úteis que o teste afirma no número.
ABERTURA_EM = "2026-08-24T13:00:00+00:00"  # segunda, 10h
CLASSIFICACAO_EM = "2026-08-24T14:00:00+00:00"  # segunda, 11h
ACIONAMENTO_EM = "2026-08-25T17:00:00+00:00"  # terça, 14h
LEMBRETE_EM = "2026-08-26T12:00:00+00:00"  # quarta, 9h
RESPOSTA_EM = "2026-08-26T17:00:00+00:00"  # quarta, 14h
DEVOLUCAO_EM = "2026-08-27T13:00:00+00:00"  # quinta, 10h
SEGUNDA_RESPOSTA_EM = "2026-08-28T13:00:00+00:00"  # sexta, 10h
ENCERRAMENTO_EM = "2026-08-28T19:00:00+00:00"  # sexta, 16h

# Segunda 10h ate terça 14h: 7h na segunda e 6h na terça.
MINUTOS_DA_TRIAGEM = 13 * 60
# Terça 14h ate quarta 14h: 3h na terça e 6h na quarta, um dia útil cheio.
MINUTOS_DA_AREA = 9 * 60
# Sexta 10h ate sexta 16h, tudo no mesmo dia.
MINUTOS_DO_DESFECHO = 6 * 60

RESPOSTA_DA_AREA = (
    "Revisamos a escala do plantao noturno e abrimos mais um guiche das 7h as 10h, "
    "com remanejamento de duas recepcionistas."
)
SEGUNDA_RESPOSTA = "A escala nova comecou em 05/09 e o tempo medio de espera caiu para 25 minutos."
MOTIVO_DA_DEVOLUCAO = "A resposta nao diz o que foi apurado nem que providencia foi tomada no plantao."
DESFECHO_AO_MANIFESTANTE = (
    "Apuramos a demora com a chefia da recepcao: a escala do plantao noturno foi refeita e "
    "um guiche a mais passou a abrir das 7h as 10h. Pedimos desculpas pela espera."
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-24",
        "prazo_resposta": "2026-08-31",
        "status": "respondido",
        "tipo_manifestacao": "reclamacao",
        "categoria": "Demora no atendimento",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
        "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "qr",
        "gravidade": "medio",
        "prazo_area_em": "2026-08-31T20:00:00+00:00",
        "prazo_conclusivo_em": None,
        "validada_em": ACIONAMENTO_EM,
        "respondida_em": SEGUNDA_RESPOSTA_EM,
        "encerrada_em": None,
        "pausada_em": None,
        "minutos_pausados": 0,
        "reaberta_em": None,
        "anonimizada_em": None,
    }
    row.update(overrides)
    return row


def _movimento(ocorrido_em: str, anterior: str | None, novo: str, autor: str, autor_id: str | None, obs: str | None):
    return {
        "id": f"mov-{ocorrido_em}",
        "manifestacao_id": "uuid-7",
        "ocorrido_em": ocorrido_em,
        "estado_anterior": anterior,
        "estado_novo": novo,
        "autor_id": autor_id,
        "autor_nome": autor,
        "observacao": obs,
    }


def _tramitacao_completa() -> list[dict]:
    """A trilha de um caso que passou por tudo: entrada pelo canal aberto,
    classificação, acionamento, lembrete automático, resposta da área,
    devolução por insuficiência e a segunda resposta."""
    return [
        _movimento(
            ABERTURA_EM, None, "em_classificacao", "Canal aberto", None, "Registro pelo canal aberto (canal: qr)"
        ),
        _movimento(
            CLASSIFICACAO_EM,
            "em_classificacao",
            "em_classificacao",
            "Marta Ouvidora",
            "P10",
            "Classificada como Reclamação (Demora no atendimento)",
        ),
        _movimento(
            ACIONAMENTO_EM,
            "em_classificacao",
            "aguardando_area",
            "Marta Ouvidora",
            "P10",
            "Validada e acionada: setor Recepcao, gravidade medio",
        ),
        _movimento(
            LEMBRETE_EM,
            "aguardando_area",
            "aguardando_area",
            "Sistema (cobrança de prazos)",
            None,
            "Lembrete de véspera enviado ao titular do setor",
        ),
        _movimento(
            RESPOSTA_EM,
            "aguardando_area",
            "respondido",
            "Carlos Titular",
            None,
            ouvidoria_respostas.observacao_da_resposta(RESPOSTA_DA_AREA),
        ),
        _movimento(
            DEVOLUCAO_EM,
            "respondido",
            "aguardando_area",
            "Marta Ouvidora",
            "P10",
            f"Resposta devolvida por insuficiência. Motivo: {MOTIVO_DA_DEVOLUCAO}",
        ),
        _movimento(
            SEGUNDA_RESPOSTA_EM,
            "aguardando_area",
            "respondido",
            "Carlos Titular",
            None,
            ouvidoria_respostas.observacao_da_resposta(SEGUNDA_RESPOSTA),
        ),
    ]


class _TabelaFake:
    """Fake do PostgREST fiel no que importa aqui: o select projeta as colunas
    pedidas, o filtro casa por igualdade e a ordenação ordena de verdade, que é
    justamente o que esta fatia afirma."""

    def __init__(self, nome: str, rows: list[dict], falhas: set[str]):
        self.nome = nome
        self.rows = rows
        self.falhas = falhas
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None
        self._ordem: tuple[str, bool] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def limit(self, _quantas):
        return self

    def order(self, coluna: str, desc: bool = False):
        self._ordem = (coluna, desc)
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self.nome in self.falhas:
            raise httpx.ReadTimeout(f"o PostgREST nao respondeu por {self.nome}")
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = [dict(n) for n in novos]
            self.rows.extend(gravados)
            return type("R", (), {"data": gravados})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._ordem is not None:
            coluna, desc = self._ordem
            casadas = sorted(casadas, key=lambda r: str(r.get(coluna) or ""), reverse=desc)
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


TRANSICOES_DO_BANCO = {
    "novo": {"em_classificacao"},
    "em_classificacao": {"aguardando_area", "encerrado"},
    "aguardando_area": {"respondido", "encerrado", "aguardando_area", "aguardando_manifestante"},
    "aguardando_manifestante": {"aguardando_area", "encerrado"},
    "respondido": {"encerrado", "aguardando_area"},
    "encerrado": {"aguardando_area"},
}


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, movimentos: list[dict] | None = None):
        self.relogio: dict = {"agora": AGORA}
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": movimentos if movimentos is not None else [],
            "ouvidoria_acessos": [],
            "ouvidoria_feriados": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_tentativas_contato": [],
        }
        self.falhas: set[str] = set()

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.falhas)

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar`: estado e movimento na
        mesma transação, com a regra do grafo aplicada antes."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        assert params["p_estado_novo"] in TRANSICOES_DO_BANCO.get(anterior, set())
        alvo["status"] = params["p_estado_novo"]
        for campo in ("desfecho", "desfecho_descricao"):
            valor = params.get(f"p_{campo}")
            if valor is not None:
                alvo[campo] = valor
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "ocorrido_em": self.relogio["agora"].isoformat(),
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_id": params["p_autor_id"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


_SESSAO: dict = {"participante": None}


def _client(monkeypatch, participante: dict | None, supabase: _SupabaseFake | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()
    _SESSAO["participante"] = participante

    async def _fake_participante(_user, _sb, fields=None):
        return _SESSAO["participante"]

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: supabase.relogio["agora"])
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _linha_do_tempo(client, manifestacao_id: str = "uuid-7"):
    return client.get(f"/api/ouvidoria/manifestacoes/{manifestacao_id}/movimentos")


def _por_descricao(eventos: list[dict], trecho: str) -> dict:
    achados = [e for e in eventos if trecho.lower() in e["descricao"].lower()]
    assert achados, f"Nenhum evento com {trecho!r} em {[e['descricao'] for e in eventos]}"
    return achados[0]


class TestOrdemEConteudoDaTrilha:
    """Critério 1: a rota devolve os movimentos do caso em ordem decrescente.

    Decrescente e não crescente: a pergunta que a página do caso responde é "o
    que aconteceu de mais novo", e o ouvidor que abre um caso de meses não pode
    precisar rolar até o fim para ver o último ato."""

    def test_eventos_saem_do_mais_novo_para_o_mais_antigo(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        resposta = _linha_do_tempo(client)

        assert resposta.status_code == 200
        eventos = resposta.json()["movimentos"]
        assert len(eventos) == 7
        quando = [e["ocorrido_em"] for e in eventos]
        assert quando == sorted(quando, reverse=True), f"A trilha não veio decrescente: {quando}"
        assert quando[0] == SEGUNDA_RESPOSTA_EM
        assert quando[-1] == ABERTURA_EM

    def test_cada_evento_traz_data_autor_e_descricao_de_uma_linha(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        for evento in eventos:
            assert evento["ocorrido_em"]
            assert evento["autor"]
            assert evento["descricao"]
            assert "\n" not in evento["descricao"], f"Descrição em mais de uma linha: {evento['descricao']!r}"

    def test_observacao_de_duas_linhas_nao_estoura_a_descricao(self, monkeypatch):
        """A descrição do evento sem mudança de estado sai da observação, e o
        rótulo do caso entra nela por texto livre do ouvidor (a classificação
        monta a frase com a categoria que ele digitou). Categoria com quebra de
        linha viraria um bloco no lugar da linha única que a RN-63 pede."""
        movimentos = [
            _movimento(
                CLASSIFICACAO_EM,
                "em_classificacao",
                "em_classificacao",
                "Marta Ouvidora",
                "P10",
                "Classificada como Reclamação (Demora)\nsegunda linha que nao pode entrar",
            )
        ]
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=movimentos))

        evento = _linha_do_tempo(client).json()["movimentos"][0]

        assert evento["descricao"] == "Classificada como Reclamação (Demora)"

    def test_manifestacao_inexistente_responde_404(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        assert _linha_do_tempo(client, "uuid-inexistente").status_code == 404

    def test_falha_de_leitura_da_trilha_nao_vira_caso_sem_historia(self, monkeypatch):
        """Timeout do PostgREST sobe como `httpx`, que `APIError` não pega. Uma
        lista vazia aqui diria ao ouvidor que o caso não tem trilha nenhuma."""
        supabase = _SupabaseFake(movimentos=_tramitacao_completa())
        supabase.falhas.add("ouvidoria_movimentos")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _linha_do_tempo(client).status_code == 503


class TestAutorDosEventos:
    """Critério: o evento automático se assina como Sistema.

    O `autor_nome` é gravado no ato e nunca muda (migration 064), então quem lê
    a trilha lê o nome de quem agiu naquele dia, e não o cadastro de hoje."""

    def test_evento_automatico_assina_como_sistema(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        lembrete = _por_descricao(eventos, "Lembrete de véspera")
        assert lembrete["autor"] == "Sistema (cobrança de prazos)"
        assert lembrete["sistema"] is True

    def test_ato_de_pessoa_nao_se_disfarca_de_sistema(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        acionamento = _por_descricao(eventos, "acionada")
        assert acionamento["autor"] == "Marta Ouvidora"
        assert acionamento["sistema"] is False


class TestTextoIntegral:
    """Critério 3 (RN-64): resposta da área, devolução e resposta ao
    manifestante aparecem inteiras na própria linha do tempo.

    São as três trocas de conteúdo do caso. Truncar qualquer uma delas
    obrigaria o ouvidor a pular de tela justamente para ler o que foi dito, que
    é o motivo de a linha do tempo existir."""

    def test_resposta_da_area_aparece_inteira(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        respostas = [e for e in eventos if e["marco"] == "T2"]
        assert len(respostas) == 2
        assert respostas[0]["texto"] == SEGUNDA_RESPOSTA
        assert respostas[1]["texto"] == RESPOSTA_DA_AREA
        # O rótulo interno da trilha não vaza para a tela: ele existe para
        # separar a resposta do portal de outra transição para "respondido".
        assert ouvidoria_respostas.MARCA not in respostas[1]["texto"]

    def test_devolucao_aparece_com_o_motivo_inteiro(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        devolucao = _por_descricao(eventos, "devolvida")
        assert devolucao["texto"] == MOTIVO_DA_DEVOLUCAO

    def test_resposta_ao_manifestante_entra_na_trilha_no_encerramento(self, monkeypatch):
        """A escrita, e não a leitura: até esta fatia o texto do desfecho ia
        só para a coluna do caso, e a trilha guardava um encerramento mudo."""
        supabase = _SupabaseFake(movimentos=_tramitacao_completa())
        supabase.relogio["agora"] = dt.datetime.fromisoformat(ENCERRAMENTO_EM)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        encerrar = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={
                "estado": "encerrado",
                "desfecho": "procedente",
                "desfecho_descricao": DESFECHO_AO_MANIFESTANTE,
            },
        )
        assert encerrar.status_code == 200, encerrar.text

        eventos = _linha_do_tempo(client).json()["movimentos"]
        encerramento = eventos[0]
        assert encerramento["marco"] == "T3"
        assert encerramento["texto"] == DESFECHO_AO_MANIFESTANTE


class TestTempoEntreMarcos:
    """Critério 4 (RN-65): a transição de marco traz o tempo desde o marco
    anterior, em minutos de EXPEDIENTE contados no servidor.

    Dias corridos mentiriam sobre quem demorou: acusar de lentidão a área que
    respondeu na segunda um caso de sexta é o contrário do que esta tela existe
    para mostrar. O calendário é o mesmo do motor de prazos, e a conta sai
    daqui e não do navegador."""

    def test_marco_traz_os_minutos_uteis_desde_o_marco_anterior(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        acionamento = _por_descricao(eventos, "acionada")
        assert acionamento["marco"] == "T1"
        assert acionamento["desde_marco"] == "T0"
        assert acionamento["minutos_uteis"] == MINUTOS_DA_TRIAGEM

        primeira_resposta = [e for e in eventos if e["marco"] == "T2"][1]
        assert primeira_resposta["desde_marco"] == "T1"
        assert primeira_resposta["minutos_uteis"] == MINUTOS_DA_AREA

    def test_primeiro_marco_nao_inventa_tempo_decorrido(self, monkeypatch):
        """Antes da entrada não houve caso: zero ali diria que a Ouvidoria
        recebeu e despachou no mesmo instante."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        abertura = eventos[-1]
        assert abertura["marco"] == "T0"
        assert abertura["minutos_uteis"] is None
        assert abertura["desde_marco"] is None

    def test_evento_que_nao_e_marco_nao_recebe_tempo(self, monkeypatch):
        """O lembrete automático e a classificação acontecem DENTRO de um
        trecho. Dar tempo a eles quebraria a leitura de onde o caso emperrou."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        for trecho in ("Lembrete de véspera", "Classificada como"):
            evento = _por_descricao(eventos, trecho)
            assert evento["marco"] is None
            assert evento["minutos_uteis"] is None

    def test_volta_do_caso_a_area_nao_conta_a_triagem_de_novo(self, monkeypatch):
        """A devolução chega ao mesmo estado que o acionamento, mas não fecha
        marco nenhum: ela DESFAZ o T2. Tratá-la como T1 faria a linha do tempo
        cobrar a triagem da Ouvidoria uma segunda vez, meses depois, e ainda
        roubaria da resposta seguinte o tempo que a área de fato levou."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        eventos = _linha_do_tempo(client).json()["movimentos"]

        devolucao = [e for e in eventos if e["ocorrido_em"] == DEVOLUCAO_EM][0]
        assert devolucao["marco"] is None, f"A devolução virou marco {devolucao['marco']}"
        assert devolucao["minutos_uteis"] is None

        # E a segunda resposta continua contando do marco de verdade.
        segunda = [e for e in eventos if e["ocorrido_em"] == SEGUNDA_RESPOSTA_EM][0]
        assert segunda["desde_marco"] == "T2"

    def test_calendario_que_nao_pode_ser_lido_chega_marcado(self, monkeypatch):
        """Feriado que falhou conta como dia trabalhado, e a conta erra sem
        denunciar a si mesma: calendário fora do ar dá exatamente o mesmo
        número que hospital sem feriado nenhum. A marca é o que deixa a tela
        dizer "sem confirmação do calendário" em vez de afirmar dias úteis que
        ninguém confirmou (issue #449)."""
        supabase = _SupabaseFake(movimentos=_tramitacao_completa())
        supabase.falhas.add("ouvidoria_feriados")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _linha_do_tempo(client).json()

        assert corpo["degradado"] == ["feriados"]

    def test_calendario_lido_nao_marca_nada(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(movimentos=_tramitacao_completa()))

        assert _linha_do_tempo(client).json()["degradado"] == []

    def test_conclusao_conta_do_marco_anterior(self, monkeypatch):
        supabase = _SupabaseFake(movimentos=_tramitacao_completa())
        supabase.relogio["agora"] = dt.datetime.fromisoformat(ENCERRAMENTO_EM)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "encerrado", "desfecho": "procedente", "desfecho_descricao": DESFECHO_AO_MANIFESTANTE},
        )
        eventos = _linha_do_tempo(client).json()["movimentos"]

        encerramento = eventos[0]
        assert encerramento["desde_marco"] == "T2"
        assert encerramento["minutos_uteis"] == MINUTOS_DO_DESFECHO


class TestCasoAnonimizado:
    """Critério 5: o caso que a Retenção já limpou mostra os FATOS sem os
    textos, e sem erro.

    A anonimização zera a `observacao` dos movimentos (issue #375): o que
    aconteceu, quando e por quem continua na trilha, o que foi dito não. A
    linha do tempo tem que sobreviver a isso sem inventar nem quebrar."""

    def _trilha_anonimizada(self) -> list[dict]:
        movimentos = _tramitacao_completa()
        for movimento in movimentos:
            movimento["observacao"] = None
        return movimentos

    def test_eventos_continuam_visiveis_sem_os_textos(self, monkeypatch):
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(anonimizada_em="2031-09-01T12:00:00+00:00")],
            movimentos=self._trilha_anonimizada(),
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        resposta = _linha_do_tempo(client)

        assert resposta.status_code == 200
        eventos = resposta.json()["movimentos"]
        assert len(eventos) == 7
        assert all(e["texto"] is None for e in eventos), "Texto sobreviveu à anonimização"
        assert all(e["descricao"] for e in eventos), "Evento sem descrição depois da anonimização"

    def test_o_fato_da_devolucao_sobrevive_ao_texto_apagado(self, monkeypatch):
        """A devolução é reconhecida pelo caminho no grafo (respondido de volta
        para a área), e não pelo texto da observação. Reconhecê-la pelo texto
        faria o caso anonimizado exibir a devolução como acionamento novo, que
        é um fato que nunca aconteceu."""
        supabase = _SupabaseFake(
            manifestacoes=[_manifestacao(anonimizada_em="2031-09-01T12:00:00+00:00")],
            movimentos=self._trilha_anonimizada(),
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        eventos = _linha_do_tempo(client).json()["movimentos"]

        devolucao = [e for e in eventos if e["ocorrido_em"] == DEVOLUCAO_EM][0]
        assert "devolv" in devolucao["descricao"].lower(), devolucao["descricao"]
        assert devolucao["texto"] is None


class TestGateDaTrilha:
    """Critério 1, o outro lado: a trilha é o Dossiê inteiro em ordem, e por
    isso ela mora atrás do mesmo gate (ADR 0034, decisão 8) e deixa registro no
    log de acesso. Papel nas Reuniões, inclusive super admin, não concede."""

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_sem_perfil_da_ouvidoria_a_rota_nega(self, monkeypatch, participante):
        client, _ = _client(monkeypatch, participante, _SupabaseFake(movimentos=_tramitacao_completa()))

        assert _linha_do_tempo(client).status_code == 403

    def test_diretoria_executiva_le_a_trilha(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA, _SupabaseFake(movimentos=_tramitacao_completa()))

        assert _linha_do_tempo(client).status_code == 200

    def test_leitura_da_trilha_deixa_registro_no_log_de_acesso(self, monkeypatch):
        supabase = _SupabaseFake(movimentos=_tramitacao_completa())
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        _linha_do_tempo(client)

        acessos = supabase.tabelas["ouvidoria_acessos"]
        assert len(acessos) == 1
        assert acessos[0]["ator_id"] == "P10"
        assert acessos[0]["acao"] == "listar_movimentos"
