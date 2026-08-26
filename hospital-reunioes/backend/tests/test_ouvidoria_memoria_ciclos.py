"""Memória dos ciclos de resposta da Ouvidoria (issue #374, PRD #318).

A devolução por insuficiência (#334) criou o SEGUNDO ciclo de resposta de um
caso, e nada no modelo sabia contar ciclos. Dois buracos saíram disso:

1. A resposta do setor vive numa coluna única (`resposta_da_area`), que o
   portal sobrescreve inteira na resposta seguinte. A resposta devolvida sumia
   justo quando o ouvidor precisava comparar o que recusou com o que veio
   depois (origem: #370).

2. A devolução apaga o marco T2 de propósito, e com ele sumia o estouro JÁ
   CONSUMADO: quem respondeu atrasado e mal voltava a ler `em_prazo`. Responder
   mal limpava a ficha, o contrário da história 5 do PRD #318 (origem: #369).

Cobre os critérios de aceite da #374 pelo seam HTTP, o mesmo das fatias
anteriores da Ouvidoria. O Resend nunca é chamado de verdade.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

EXTRATO = "Demora na recepcao do plantao noturno. Apurar e responder a Ouvidoria."

VALIDACAO = {
    # Lista fechada desde a issue #372: é o tipo, e não o rótulo, que decide o
    # sigilo do caso.
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "gravidade": "medio",
    "extrato_para_o_setor": EXTRATO,
}

# Terça-feira, 14h de Brasília. Com prazo médio de 4 dias úteis, a manifestação
# validada aqui vence segunda 31/08 às 17h de Brasília.
VALIDACAO_EM = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
PRAZO_ORIGINAL = "2026-08-31T20:00:00+00:00"

# Quarta-feira, 14h de Brasília: dentro do prazo original.
DENTRO_DO_PRAZO_EM = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)
# Terça 01/09, 14h de Brasília: DEPOIS do vencimento de segunda 31/08 às 17h.
FORA_DO_PRAZO_EM = dt.datetime(2026, 9, 1, 17, 0, tzinfo=dt.UTC)

PRIMEIRA_RESPOSTA = "Estamos apurando internamente e retornaremos quando possivel."
SEGUNDA_RESPOSTA = "Revisamos a escala do plantao noturno e abrimos mais um guiche das 7h as 10h."
TERCEIRA_RESPOSTA = "A escala nova comecou em 05/09 e o tempo medio de espera caiu para 25 minutos."
MOTIVO = "A resposta nao diz o que foi apurado nem que providencia foi tomada."


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção). Todo teste
    deste arquivo passa pelo mock, mesmo os que não olham o email."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append(
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "em_classificacao",
        "categoria": "A classificar",
        "setor": "A definir",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "",
        "contato_em": "2026-08-14T19:50:00+00:00",
        "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "tipo_manifestacao": None,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "gravidade": None,
        "prazo_area_em": None,
        "prazo_rompido_em": None,
        "vespera_avisada_em": None,
        "escalonado_gestor_em": None,
        "escalonado_diretoria_em": None,
        "critico_avisado_em": None,
        "validada_em": None,
        "validada_por": None,
        "respondida_em": None,
        "resposta_da_area": None,
        "respondida_por_nome": None,
        "encerrada_em": None,
        "pausada_em": None,
        "minutos_pausados": 0,
        "reincidencia": False,
        "reaberta_em": None,
        "area_estourou_em": None,
    }
    row.update(overrides)
    return row


def _responsavel(papel: str = "titular", **overrides) -> dict:
    row = {
        "id": f"resp-{papel}",
        "setor": "Recepcao",
        "papel": papel,
        "nome": "Carlos Titular",
        "email": "carlos@hsm.br",
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    row.update(overrides)
    return row


PRAZOS = [
    {"gravidade": "critico", "marco": "area_resposta", "valor": 4, "unidade": "horas_uteis"},
    {"gravidade": "alto", "marco": "area_resposta", "valor": 2, "unidade": "dias_uteis"},
    {"gravidade": "medio", "marco": "area_resposta", "valor": 4, "unidade": "dias_uteis"},
    {"gravidade": "baixo", "marco": "area_resposta", "valor": None, "unidade": "dias_uteis"},
]


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, o insert devolve a linha com id, e os filtros filtram como lá."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._in: dict = {}
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None

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

    def is_(self, col, value):
        self._filters[col] = None if value in ("null", None) else value
        return self

    def in_(self, col, values):
        self._in[col] = list(values)
        return self

    def lte(self, col, value):
        self._ate[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, _n):
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados})()
        casadas = [
            r
            for r in self.rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in v for c, v in self._in.items())
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


# O grafo que a RPC `ouvidoria_transicionar` aplica no banco (migrations 064,
# 074 e 075). O fake recusa o que o banco recusaria.
TRANSICOES_DO_BANCO = {
    "novo": {"em_classificacao"},
    "em_classificacao": {"aguardando_area", "encerrado"},
    "aguardando_area": {"respondido", "encerrado", "aguardando_area", "aguardando_manifestante"},
    "aguardando_manifestante": {"aguardando_area", "encerrado"},
    "respondido": {"encerrado", "aguardando_area"},
    "encerrado": {"aguardando_area"},
}


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, relogio: dict | None = None):
        self.relogio = relogio
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_prorrogacoes": [],
            "ouvidoria_setor_responsaveis": [_responsavel()],
            "ouvidoria_setor_tokens": [],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            "participantes": [
                {
                    "id": "P10",
                    "nome_completo": "Marta Ouvidora",
                    "email": "marta@hsm.br",
                    "perfil_ouvidoria": "ouvidor",
                },
            ],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar`: estado e movimento na
        mesma transação, com a regra do grafo aplicada antes.

        `ocorrido_em` sai do relógio do teste, não do `now()` do banco: o
        histórico de respostas é lido em ordem cronológica, e um carimbo real
        aqui deixaria os três ciclos no mesmo instante."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        if params["p_estado_novo"] not in TRANSICOES_DO_BANCO.get(anterior, set()):
            raise APIError(
                {"message": f"Transicao invalida: {anterior} para {params['p_estado_novo']}", "code": "23514"}
            )
        alvo["status"] = params["p_estado_novo"]
        for campo in ("desfecho", "desfecho_descricao"):
            valor = params.get(f"p_{campo}")
            if valor is not None:
                alvo[campo] = valor
        agora = (self.relogio or {}).get("agora") or dt.datetime.now(dt.UTC)
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
                "ocorrido_em": agora.isoformat(),
                "estado_anterior": anterior,
                "estado_novo": params["p_estado_novo"],
                "autor_id": params["p_autor_id"],
                "autor_nome": params["p_autor_nome"],
                "observacao": params.get("p_observacao"),
            }
        )
        return type("Exec", (), {"execute": lambda _s: type("R", (), {"data": [dict(alvo)]})()})()


def _client(
    monkeypatch,
    supabase: _SupabaseFake | None = None,
    agora: dt.datetime = VALIDACAO_EM,
    relogio: dict | None = None,
):
    """App de teste com o painel do ouvidor E o portal público do setor."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    relogio = relogio if relogio is not None else {"agora": agora}
    supabase = supabase if supabase is not None else _SupabaseFake(relogio=relogio)
    supabase.relogio = relogio

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: relogio["agora"])
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: relogio["agora"])
    monkeypatch.setattr(settings, "frontend_url", "http://app.test")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _token_do_email(enviados: list[dict]) -> str:
    email = next(e for e in reversed(enviados) if e["destinatario"] == "carlos@hsm.br")
    achado = re.search(r"http://app\.test/ouvidoria-setor/([A-Za-z0-9_-]+)", email["texto"])
    assert achado, f"O email do setor não tem link tokenizado: {email['texto']}"
    return achado.group(1)


def _acionar(monkeypatch, relogio: dict) -> tuple[TestClient, _SupabaseFake]:
    """Caso validado e já despachado à área, que é onde o primeiro ciclo de
    resposta começa."""
    client, sb = _client(monkeypatch, relogio=relogio)
    assert client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO).status_code == 200
    return client, sb


def _responder(client, enviados: list[dict], texto: str):
    return client.post(f"/api/ouvidoria-setor/{_token_do_email(enviados)}/responder", data={"resposta": texto})


def _devolver(client, motivo: str = MOTIVO):
    return client.post("/api/ouvidoria/manifestacoes/uuid-7/devolucoes", json={"motivo": motivo})


class TestTextoNaTrilha:
    """Critério 1: o texto de cada resposta do setor fica registrado no
    movimento da trilha, um por ciclo.

    A trilha é imutável por desenho (migration 064), então guardar o texto ali
    faz o histórico nascer de graça: nada sobrescreve o que já foi gravado."""

    def test_resposta_do_setor_grava_o_texto_no_movimento_da_trilha(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200

        movimento = next(m for m in sb.tabelas["ouvidoria_movimentos"] if m["estado_novo"] == "respondido")
        assert PRIMEIRA_RESPOSTA in (movimento["observacao"] or ""), (
            f"O movimento registra que HOUVE resposta, mas não o que ela dizia: observacao={movimento['observacao']!r}"
        )


def _respostas(client, manifestacao_id: str = "uuid-7"):
    return client.get(f"/api/ouvidoria/manifestacoes/{manifestacao_id}/respostas")


class TestHistoricoDeRespostas:
    """Critérios 2, 3 e 4: a resposta devolvida continua legível depois da
    seguinte, e o ouvidor vê um ciclo por resposta, com data e autor."""

    def test_resposta_devolvida_continua_legivel_depois_da_resposta_seguinte(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _devolver(client).status_code == 201
        relogio["agora"] = DENTRO_DO_PRAZO_EM + dt.timedelta(hours=2)
        assert _responder(client, _nunca_envia_email_de_verdade, SEGUNDA_RESPOSTA).status_code == 200

        # A coluna do caso já foi sobrescrita: é a trilha que guarda o resto.
        assert sb.tabelas["ouvidoria_protocolos"][0]["resposta_da_area"] == SEGUNDA_RESPOSTA

        resposta = _respostas(client)

        assert resposta.status_code == 200, resposta.text
        textos = [ciclo["resposta"] for ciclo in resposta.json()["respostas"]]
        assert textos == [PRIMEIRA_RESPOSTA, SEGUNDA_RESPOSTA]

    def test_cada_ciclo_traz_a_data_e_quem_respondeu(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200

        ciclo = _respostas(client).json()["respostas"][0]

        assert ciclo["respondida_por_nome"] == "Carlos Titular"
        assert ciclo["respondida_em"] == DENTRO_DO_PRAZO_EM.isoformat()

    def test_caso_devolvido_duas_vezes_tem_as_tres_respostas_legiveis(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        for passo, texto in enumerate((PRIMEIRA_RESPOSTA, SEGUNDA_RESPOSTA, TERCEIRA_RESPOSTA)):
            relogio["agora"] = DENTRO_DO_PRAZO_EM + dt.timedelta(hours=passo)
            assert _responder(client, _nunca_envia_email_de_verdade, texto).status_code == 200
            if texto is not TERCEIRA_RESPOSTA:
                assert _devolver(client, motivo=f"{MOTIVO} ({passo})").status_code == 201

        textos = [ciclo["resposta"] for ciclo in _respostas(client).json()["respostas"]]
        assert textos == [PRIMEIRA_RESPOSTA, SEGUNDA_RESPOSTA, TERCEIRA_RESPOSTA]

    def test_devolucao_do_ouvidor_nao_entra_como_ciclo_de_resposta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A trilha guarda todo ato do caso. O histórico lista só o que a ÁREA
        respondeu: o motivo escrito pelo ouvidor na devolução é o contrário
        disso, e listá-lo ali faria o Dossiê contar ciclos a mais."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _devolver(client).status_code == 201

        respostas = _respostas(client).json()["respostas"]

        assert len(respostas) == 1
        assert MOTIVO not in respostas[0]["resposta"]

    def test_caso_sem_resposta_nenhuma_devolve_historico_vazio(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        resposta = _respostas(client)

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["respostas"] == []


def _cumprimento(client, numero: int = 7) -> str:
    indice = client.get("/api/ouvidoria/protocolos")
    assert indice.status_code == 200, indice.text
    caso = next(p for p in indice.json()["protocolos"] if p["numero"] == numero)
    return caso["cumprimento"]


class TestEstouroSobreviveADevolucao:
    """Critérios 5 e 6: a devolução não apaga o estouro já consumado, e não
    inventa estouro nenhum para quem respondeu no prazo.

    A devolução limpa o marco T2 de propósito (#334). Sem memória do estouro,
    essa limpeza fazia o indicador voltar a ler `em_prazo` para quem respondeu
    atrasado: responder mal virava um jeito de limpar a ficha."""

    def test_setor_que_respondeu_atrasado_e_foi_devolvido_continua_estourado(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL

        relogio["agora"] = FORA_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _cumprimento(client) == "estourado"

        assert _devolver(client).status_code == 201

        assert _cumprimento(client) == "estourado", (
            "A devolução moveu o prazo para frente e limpou o marco T2: sem a "
            "memória do estouro, responder atrasado e mal limpa a ficha da área"
        )

    def test_setor_que_respondeu_no_prazo_e_foi_devolvido_nao_e_punido(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _cumprimento(client) == "cumprido"

        assert _devolver(client).status_code == 201

        assert _cumprimento(client) == "em_prazo"

    def test_a_devolucao_continua_limpando_o_marco_t2(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Regressão da #334: o marco T2 precisa sair mesmo na devolução.

        A memória do estouro é um carimbo NOVO, ao lado do T2, e não um jeito
        de manter o T2 vivo: mantê-lo faria o indicador dizer "cumprido" para
        quem respondeu no prazo e ainda deve a resposta refeita."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)

        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert sb.tabelas["ouvidoria_protocolos"][0]["respondida_em"] is not None

        assert _devolver(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["respondida_em"] is None
        assert caso["respondida_por_nome"] is None

    def test_o_primeiro_estouro_manda_e_a_segunda_devolucao_nao_o_reescreve(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O carimbo guarda QUANDO o prazo rompeu, que é o vencimento que a
        área furou, e não a hora em que a resposta atrasada chegou: os
        relatórios do PRD 3 leem esse instante como o momento do estouro, e a
        hora da resposta fica 21 horas adiante dele neste cenário.

        A segunda devolução também não pode empurrá-lo para frente, senão o
        último atraso passaria por primeiro."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)

        relogio["agora"] = FORA_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _devolver(client).status_code == 201
        primeiro = sb.tabelas["ouvidoria_protocolos"][0]["area_estourou_em"]
        assert primeiro == PRAZO_ORIGINAL

        relogio["agora"] = FORA_DO_PRAZO_EM + dt.timedelta(days=7)
        assert _responder(client, _nunca_envia_email_de_verdade, SEGUNDA_RESPOSTA).status_code == 200
        assert _devolver(client, motivo="Continua sem dizer o que foi feito.").status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["area_estourou_em"] == primeiro


class TestReaberturaComecaFichaLimpa:
    """A reincidência (#335) NÃO herda o estouro, ao contrário da devolução.

    São dois atos diferentes. A devolução mantém o MESMO ciclo em pé: a área
    ainda deve a resposta daquele prazo, e por isso o atraso continua contando.
    A reabertura já zera o ciclo inteiro (desfecho, marco T2, tempo de espera,
    carimbos dos jobs) e dá prazo INTEIRO novo: é tramitação nova, e carregar o
    estouro para dentro dela puniria a área por um ciclo em que ela não errou.
    """

    ENCERRADA_EM = FORA_DO_PRAZO_EM + dt.timedelta(days=2)
    REABERTURA_EM = FORA_DO_PRAZO_EM + dt.timedelta(days=5)

    def _encerrado_com_estouro(self) -> _SupabaseFake:
        return _SupabaseFake(
            [
                _manifestacao(
                    status="encerrado",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    validada_em=VALIDACAO_EM.isoformat(),
                    validada_por="P10",
                    encerrada_em=self.ENCERRADA_EM.isoformat(),
                    desfecho="procedente",
                    desfecho_descricao="Escala do plantao noturno revista.",
                    area_estourou_em=FORA_DO_PRAZO_EM.isoformat(),
                )
            ]
        )

    def test_reabertura_apaga_o_estouro_do_ciclo_encerrado(self, monkeypatch, _nunca_envia_email_de_verdade):
        sb = self._encerrado_com_estouro()
        client, _ = _client(monkeypatch, supabase=sb, agora=self.REABERTURA_EM)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/reaberturas",
            json={"motivo": "A espera na recepcao voltou ao que era."},
        )

        assert resposta.status_code == 201, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["area_estourou_em"] is None
        assert _cumprimento(client) == "em_prazo"


class TestCicloAnteriorAoDeploy:
    """O caso que JÁ foi devolvido em produção é o motivo desta fatia (#370), e
    o movimento dele não tem o texto: quando ele foi gravado, a observação era
    só o rótulo.

    Descartar esse movimento faria o histórico começar do zero justo nos casos
    que precisam dele, e ainda numeraria a segunda resposta como "1ª"."""

    def test_movimento_sem_texto_continua_contando_como_ciclo(self, monkeypatch, _nunca_envia_email_de_verdade):
        from app.services import ouvidoria_respostas

        relogio = {"agora": VALIDACAO_EM}
        client, sb = _acionar(monkeypatch, relogio)

        # O movimento que o código antigo gravava: o rótulo, sem separador nem
        # texto. Entra à mão porque nenhum caminho do código novo o produz.
        sb.tabelas["ouvidoria_movimentos"].append(
            {
                "id": "mov-antigo",
                "manifestacao_id": "uuid-7",
                "ocorrido_em": VALIDACAO_EM.isoformat(),
                "estado_anterior": "aguardando_area",
                "estado_novo": "respondido",
                "autor_id": None,
                "autor_nome": "Carlos Titular",
                "observacao": ouvidoria_respostas.MARCA,
            }
        )
        relogio["agora"] = DENTRO_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, SEGUNDA_RESPOSTA).status_code == 200

        respostas = _respostas(client).json()["respostas"]

        assert len(respostas) == 2
        assert respostas[0]["resposta"] != ""
        assert respostas[0]["respondida_por_nome"] == "Carlos Titular"
        assert respostas[1]["resposta"] == SEGUNDA_RESPOSTA


class TestPortalDoSetorLeOMesmoIndicador:
    """O portal do setor projeta o prazo com a MESMA função do painel. Se a
    coluna nova não entra no select dele, as duas APIs discordam sobre o
    indicador de que o PRD #318 inteiro trata."""

    def test_portal_e_painel_dizem_o_mesmo_cumprimento(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _acionar(monkeypatch, relogio)

        relogio["agora"] = FORA_DO_PRAZO_EM
        assert _responder(client, _nunca_envia_email_de_verdade, PRIMEIRA_RESPOSTA).status_code == 200
        assert _devolver(client).status_code == 201

        # O email da devolução traz o link novo do setor.
        token = _token_do_email(_nunca_envia_email_de_verdade)
        portal = client.get(f"/api/ouvidoria-setor/{token}")

        assert portal.status_code == 200, portal.text
        assert portal.json()["cumprimento"] == _cumprimento(client) == "estourado"
