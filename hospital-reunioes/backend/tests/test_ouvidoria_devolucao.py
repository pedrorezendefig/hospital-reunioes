"""Devolução por insuficiência com meio prazo (issue #334, PRD #318, ADR 0034).

Resposta fraca não encerra o caso: o ouvidor devolve ao setor com motivo
obrigatório, e a área volta a dever resposta com METADE do prazo original da
gravidade contada da devolução, somada ao tempo que já gastou. O relógio não
zera (histórias 6, 7 e 22 do PRD #318).

Cobre os critérios de aceite da #334 pelo seam HTTP, o mesmo das fatias
anteriores. O Resend nunca é chamado de verdade: o envio é mockado no ponto
único por onde todo email do app passa.
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

# Terça-feira, 14h de Brasília, dentro do expediente. Com prazo médio de 4 dias
# úteis, a manifestação validada aqui vence segunda 31/08 às 17h.
VALIDACAO_EM = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
PRAZO_ORIGINAL = "2026-08-31T20:00:00+00:00"

# Quarta-feira, 14h de Brasília: o ouvidor lê a resposta e devolve.
DEVOLUCAO_EM = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)
# Metade de 4 dias úteis são 2 dias úteis de expediente (9h por dia) contados
# da devolução: quarta 14h às 17h gasta 3h, quinta inteira gasta 9h, e as 6h
# que sobram terminam sexta às 14h. Fica ANTES do prazo original de segunda:
# responder mal encurtou o relógio da área, não recomeçou ele.
PRAZO_APOS_DEVOLUCAO = "2026-08-28T17:00:00+00:00"

RESPOSTA_FRACA = "Estamos apurando internamente e retornaremos quando possivel."
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


# O grafo que a RPC `ouvidoria_transicionar` aplica no banco (migrations 064 e
# 074). O fake recusa o que o banco recusaria, para o teste de transição
# proibida não passar só porque o Python foi generoso.
TRANSICOES_DO_BANCO = {
    "novo": {"em_classificacao"},
    "em_classificacao": {"aguardando_area", "encerrado"},
    "aguardando_area": {"respondido", "encerrado", "aguardando_area"},
    "respondido": {"encerrado", "aguardando_area"},
}


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None):
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
        mesma transação, com a regra do grafo aplicada antes."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        if params["p_estado_novo"] not in TRANSICOES_DO_BANCO.get(anterior, set()):
            raise APIError(
                {"message": f"Transicao invalida: {anterior} para {params['p_estado_novo']}", "code": "23514"}
            )
        alvo["status"] = params["p_estado_novo"]
        self.tabelas["ouvidoria_movimentos"].append(
            {
                "id": f"mov-{len(self.tabelas['ouvidoria_movimentos']) + 1}",
                "manifestacao_id": params["p_manifestacao_id"],
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
    participante: dict | None = None,
    relogio: dict | None = None,
):
    """App de teste com o painel do ouvidor E o portal público do setor."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante if participante is not None else OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    # Relógio compartilhado: a devolução acontece um dia depois da validação, e
    # o prazo novo depende do instante em que o ouvidor devolve.
    relogio = relogio if relogio is not None else {"agora": agora}
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


def _respondido(monkeypatch, enviados, relogio: dict | None = None) -> tuple[TestClient, _SupabaseFake]:
    """Caso acionado e já respondido pela área, que é onde a devolução começa."""
    client, sb = _client(monkeypatch, relogio=relogio)
    assert client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO).status_code == 200
    token = _token_do_email(enviados)
    assert client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_FRACA}).status_code == 200
    return client, sb


def _devolver(client, motivo: str = MOTIVO, manifestacao_id: str = "uuid-7"):
    return client.post(f"/api/ouvidoria/manifestacoes/{manifestacao_id}/devolucoes", json={"motivo": motivo})


class TestMotivoObrigatorio:
    """Critério 1: devolução sem motivo é rejeitada. É o motivo escrito que
    diferencia justificativa de solução (história 6)."""

    @pytest.mark.parametrize("motivo", ["", "   ", "\n\t "])
    def test_devolucao_sem_motivo_e_rejeitada(self, monkeypatch, _nunca_envia_email_de_verdade, motivo):
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _devolver(client, motivo=motivo)

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"


class TestTransicaoDaDevolucao:
    """Critério 2: a devolução leva o caso de volta para aguardando área, e as
    transições proibidas continuam proibidas (história 6, PRD #318)."""

    def test_devolucao_leva_o_caso_respondido_de_volta_para_aguardando_area(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade)
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

        resposta = _devolver(client)

        assert resposta.status_code == 201, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"

    def test_devolver_caso_encerrado_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Encerrado é terminal: devolver dali reabriria o caso por uma porta
        que não é a da reabertura."""
        sb = _SupabaseFake([_manifestacao(status="encerrado", gravidade="medio", prazo_area_em=PRAZO_ORIGINAL)])
        client, _ = _client(monkeypatch, supabase=sb, agora=DEVOLUCAO_EM)

        resposta = _devolver(client)

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"

    def test_devolver_caso_em_classificacao_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Não existe resposta a devolver antes de a área ser acionada.

        O setor tem titular de propósito: sem isso o 409 viria da porta errada
        (setor sem responsável) e o teste passaria sem provar nada. O caminho
        `em_classificacao -> aguardando_area` existe no grafo porque é o
        ACIONAMENTO, e acionar por aqui pularia a validação inteira: o caso
        ficaria aguardando a área sem gravidade, sem prazo e sem extrato, e o
        setor receberia "sua resposta foi devolvida" de um caso que nunca viu."""
        sb = _SupabaseFake([_manifestacao(status="em_classificacao", setor="Recepcao")])
        client, _ = _client(monkeypatch, supabase=sb, agora=DEVOLUCAO_EM)

        resposta = _devolver(client)

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "em_classificacao"
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] is None
        assert _nunca_envia_email_de_verdade == []

    def test_devolver_duas_vezes_nao_estica_o_prazo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Sem resposta nova não há o que devolver. Aceitar a segunda devolução
        empurraria o vencimento meio prazo adiante a cada chamada, contornando
        as duas regras da prorrogação (uma só, e teto de 30 dias úteis)."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201
        prazo_da_devolucao = sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"]

        relogio["agora"] = DEVOLUCAO_EM + dt.timedelta(days=1)
        assert _devolver(client, motivo="Continua sem dizer o que foi feito.").status_code == 409

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == prazo_da_devolucao


class TestMeioPrazoSemZerarORelogio:
    """Critério 3: o prazo novo é o tempo já corrido mais metade do prazo da
    gravidade, contada da devolução. Responder mal não dá relógio novo
    (história 7, PRD #318)."""

    def test_prazo_novo_e_metade_do_prazo_da_gravidade_contada_da_devolucao(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["prazo_area_em"] == PRAZO_APOS_DEVOLUCAO

    def test_o_prazo_novo_nao_recomeca_o_relogio_da_gravidade(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Um prazo inteiro novo a partir de quarta venceria na terça seguinte.
        Meio prazo vence antes até do vencimento original de segunda: o tempo
        já gasto pela área continua contando contra ela."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] < PRAZO_ORIGINAL

    def test_a_resposta_devolvida_deixa_de_contar_como_resposta_dada(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O marco T2 sai junto: com ele no lugar, o indicador de cumprimento
        leria a primeira resposta e diria "cumprido" para um caso que ainda
        deve resposta. O texto da área fica, para o ouvidor poder relê-lo."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        assert sb.tabelas["ouvidoria_protocolos"][0]["respondida_em"] is not None

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["respondida_em"] is None
        assert caso["resposta_da_area"] == RESPOSTA_FRACA

    def test_gravidade_sem_prazo_devolve_sem_inventar_vencimento(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Baixo não tem prazo de área na tabela: a devolução não pode criar um."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="respondido",
                    setor="Recepcao",
                    gravidade="baixo",
                    prazo_area_em=None,
                    respondida_em=VALIDACAO_EM.isoformat(),
                    resposta_da_area=RESPOSTA_FRACA,
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=DEVOLUCAO_EM)

        assert _devolver(client).status_code == 201

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] is None


class TestEmailDaDevolucao:
    """Critério 4: a área recebe email de devolução com o motivo. Sem o motivo
    a recusa chega sem dizer o que refazer (história 6, PRD #318)."""

    def test_o_titular_do_setor_recebe_a_devolucao_com_o_motivo(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        _nunca_envia_email_de_verdade.clear()

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        assert len(_nunca_envia_email_de_verdade) == 1
        email = _nunca_envia_email_de_verdade[0]
        assert email["destinatario"] == "carlos@hsm.br"
        assert "devolvida" in email["assunto"]
        assert MOTIVO in email["texto"]
        assert MOTIVO in email["html"]

    def test_o_email_traz_o_prazo_novo_e_nao_o_antigo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quem lê precisa saber até quando responder agora, não qual data
        estava na tela antes da devolução."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        _nunca_envia_email_de_verdade.clear()

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        texto = _nunca_envia_email_de_verdade[0]["texto"]
        assert "28/08/2026" in texto
        assert "31/08/2026" not in texto

    def test_o_email_leva_link_novo_do_portal_porque_o_antigo_ja_foi_usado(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O token do acionamento morreu na resposta que voltou. Sem link novo
        a área lê a devolução e não tem por onde responder."""
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        token_usado = _token_do_email(_nunca_envia_email_de_verdade)
        _nunca_envia_email_de_verdade.clear()

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        token_novo = _token_do_email(_nunca_envia_email_de_verdade)
        assert token_novo != token_usado
        assert client.get(f"/api/ouvidoria-setor/{token_novo}").status_code == 200

    def test_a_devolucao_fica_registrada_na_fila_de_notificacoes(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Sem linha na fila não há prova da devolução nem botão de reenvio."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        fila = [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "resposta_devolvida"]
        assert len(fila) == 1
        assert fila[0]["destinatario_email"] == "carlos@hsm.br"
        assert fila[0]["detalhe"] == MOTIVO
        assert fila[0]["status"] == "enviada"


class TestTrilhaDoCaso:
    """Critério 5: a devolução aparece na trilha imutável do caso, com o motivo
    escrito pelo ouvidor (história 22, PRD #318)."""

    def test_a_devolucao_entra_na_trilha_com_autor_e_motivo(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        movimento = sb.tabelas["ouvidoria_movimentos"][-1]
        assert movimento["estado_anterior"] == "respondido"
        assert movimento["estado_novo"] == "aguardando_area"
        assert movimento["autor_nome"] == "Marta Ouvidora"
        assert MOTIVO in movimento["observacao"]

    def test_a_trilha_guarda_a_resposta_devolvida_e_a_devolucao_em_ordem(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """A história do caso continua completa: acionamento, resposta da área
        e devolução, nessa ordem."""
        relogio = {"agora": VALIDACAO_EM}
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)

        relogio["agora"] = DEVOLUCAO_EM
        assert _devolver(client).status_code == 201

        caminho = [(m["estado_anterior"], m["estado_novo"]) for m in sb.tabelas["ouvidoria_movimentos"]]
        assert caminho == [
            ("em_classificacao", "aguardando_area"),
            ("aguardando_area", "respondido"),
            ("respondido", "aguardando_area"),
        ]


class TestPortaUnica:
    """A devolução tem uma porta só. A transição genérica do painel não pode
    virar caminho de fundo, sem motivo, sem meio prazo e sem aviso à área."""

    def test_transicao_generica_para_aguardando_area_sem_motivo_e_recusada(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, sb = _respondido(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "aguardando_area", "observacao": "voltei"},
        )

        assert resposta.status_code == 422, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

    def test_quem_nao_e_da_ouvidoria_nao_devolve(self, monkeypatch, _nunca_envia_email_de_verdade):
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="respondido",
                    setor="Recepcao",
                    gravidade="medio",
                    respondida_em=VALIDACAO_EM.isoformat(),
                    resposta_da_area=RESPOSTA_FRACA,
                )
            ]
        )
        client, _ = _client(
            monkeypatch,
            supabase=sb,
            agora=DEVOLUCAO_EM,
            participante={"id": "P12", "nome_completo": "Sofia", "access_profile": None, "perfil_ouvidoria": None},
        )

        assert _devolver(client).status_code == 403
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

    def test_devolver_caso_que_ja_voltou_a_esperar_a_area_continua_valendo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O PRD devolve "de respondido ou aguardando área". O ouvidor pode ler
        a resposta e devolvê-la depois de o caso já ter voltado à área, e não
        precisa decorar o estado para agir."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="aguardando_area",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    respondida_em=VALIDACAO_EM.isoformat(),
                    resposta_da_area=RESPOSTA_FRACA,
                )
            ]
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=DEVOLUCAO_EM)

        assert _devolver(client).status_code == 201

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["prazo_area_em"] == PRAZO_APOS_DEVOLUCAO


class TestADevolucaoNaoMenteAoOuvidor:
    """A devolução mexe no prazo antes de avisar a área. Se o aviso não sai, o
    ouvidor precisa saber: o relógio já foi encurtado contra alguém que não foi
    avisado. Mesma régua da rota de acionamento."""

    def test_falha_ao_registrar_o_aviso_nao_devolve_201(self, monkeypatch, _nunca_envia_email_de_verdade):
        relogio = {"agora": VALIDACAO_EM}
        client, _ = _respondido(monkeypatch, _nunca_envia_email_de_verdade, relogio=relogio)
        monkeypatch.setattr(ouvidoria_notificacoes, "registrar", lambda *a, **kw: None)

        relogio["agora"] = DEVOLUCAO_EM
        resposta = _devolver(client)

        assert resposta.status_code == 500, resposta.text
        assert "não foi notificado" in resposta.text or "nao foi notificado" in resposta.text

    def test_devolver_para_setor_sem_titular_avisa_a_diretoria(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O caso volta a correr contra um setor sem titular. É exatamente o
        buraco de cadastro que o alerta à Diretoria existe para não deixar
        virar rotina silenciosa (ADR 0034, decisão 5)."""
        sb = _SupabaseFake(
            [
                _manifestacao(
                    status="respondido",
                    setor="Recepcao",
                    gravidade="medio",
                    prazo_area_em=PRAZO_ORIGINAL,
                    respondida_em=VALIDACAO_EM.isoformat(),
                    resposta_da_area=RESPOSTA_FRACA,
                )
            ]
        )
        # Só gestor vigente: o titular saiu do papel.
        sb.tabelas["ouvidoria_setor_responsaveis"] = [
            _responsavel(papel="gestor", nome="Bia Gestora", email="bia@hsm.br")
        ]
        sb.tabelas["participantes"].append(
            {
                "id": "P11",
                "nome_completo": "Dr. Diretor",
                "email": "diretor@hsm.br",
                "perfil_ouvidoria": "diretoria_executiva",
            }
        )
        client, _ = _client(monkeypatch, supabase=sb, agora=DEVOLUCAO_EM)

        assert _devolver(client).status_code == 201

        alertas = [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "alerta_sem_titular"]
        assert len(alertas) == 1
        assert alertas[0]["destinatario_email"] == "diretor@hsm.br"
