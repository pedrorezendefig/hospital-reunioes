"""Prorrogação de prazo ponta a ponta (issue #333, PRD #318, ADR 0034 decisão 12).

O responsável do setor pede mais prazo pelo próprio link tokenizado do portal
(issue #326), com justificativa. O sistema recusa sozinho pedido pós-vencimento
e segundo pedido. O ouvidor aprova ou nega, e o prazo novo respeita o teto de
30 dias úteis da entrada, que vem do motor da issue #331.

Cobre os critérios de aceite da #333 pelo seam HTTP, que é o mesmo das fatias
anteriores. O Resend nunca é chamado de verdade: o envio é mockado no ponto
único por onde todo email do app passa.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes, ouvidoria_prorrogacao  # noqa: E402

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

# Terça-feira, 14h de Brasília, dentro do expediente: o email sai na hora.
# Com prazo médio de 4 dias úteis, a manifestação vence segunda 31/08 às 17h.
DENTRO_DO_EXPEDIENTE = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)
PRAZO_ORIGINAL = "2026-08-31T20:00:00+00:00"
# Cinco dias úteis a mais, com a Independência (07/09) fora do calendário útil.
PRAZO_PRORROGADO = "2026-09-08T20:00:00+00:00"
# O trigésimo dia útil contado da entrada (14/08 16h50), com o mesmo feriado.
TETO = "2026-09-28T20:00:00+00:00"


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
        self._nao_nulos: list[str] = []
        self._negar_proximo = False
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

    @property
    def not_(self):
        """Nega o próximo filtro, como no PostgREST (`q.not_.is_(col, "null")`)."""
        self._negar_proximo = True
        return self

    def is_(self, col, value):
        if self._negar_proximo:
            self._negar_proximo = False
            self._nao_nulos.append(col)
            return self
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
            and all(r.get(c) is not None for c in self._nao_nulos)
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


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
            # `ativo` espelha a tabela real (DEFAULT true desde a
            # `001_create_participantes.sql`): quem é desligado do hospital vira
            # `ativo: False` e para de ser avisado (issue #403).
            "participantes": [
                {
                    "id": "P10",
                    "nome_completo": "Marta Ouvidora",
                    "email": "marta@hsm.br",
                    "perfil_ouvidoria": "ouvidor",
                    "ativo": True,
                },
                {
                    "id": "P11",
                    "nome_completo": "Dr. Diretor",
                    "email": "diretor@hsm.br",
                    "perfil_ouvidoria": "diretoria_executiva",
                    "ativo": True,
                },
                {
                    "id": "P12",
                    "nome_completo": "Sofia Secretaria",
                    "email": "sofia@hsm.br",
                    "perfil_ouvidoria": None,
                    "ativo": True,
                },
            ],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar` (migration 064): estado e
        movimento na mesma transação."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
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
    agora: dt.datetime = DENTRO_DO_EXPEDIENTE,
    participante: dict | None = None,
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
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(settings, "frontend_url", "http://app.test")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _acionar(client) -> None:
    resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
    assert resposta.status_code == 200, resposta.text


def _token_do_email(enviados: list[dict]) -> str:
    email = next(e for e in enviados if e["destinatario"] == "carlos@hsm.br")
    achado = re.search(r"http://app\.test/ouvidoria-setor/([A-Za-z0-9_-]+)", email["texto"])
    assert achado, f"O email de acionamento não tem link tokenizado: {email['texto']}"
    return achado.group(1)


def _portal(monkeypatch, enviados, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
    """Aciona a área e devolve o cliente já com o token do titular na mão."""
    client, sb = _client(monkeypatch, agora=agora)
    _acionar(client)
    return client, sb, _token_do_email(enviados)


JUSTIFICATIVA = "A auditoria interna so devolve o laudo na semana que vem."


def _pedir(client, token: str, dias: int = 5, justificativa: str = JUSTIFICATIVA):
    return client.post(
        f"/api/ouvidoria-setor/{token}/prorrogacao",
        json={"justificativa": justificativa, "dias_uteis": dias},
    )


class TestRegrasVisiveisNoPortal:
    """Critério 1, primeira metade: a página do link mostra as regras antes de
    o responsável contar com um recurso que talvez não tenha (história 2)."""

    def test_portal_mostra_as_regras_e_libera_o_pedido(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        corpo = client.get(f"/api/ouvidoria-setor/{token}").json()

        prorrogacao = corpo["prorrogacao"]
        assert prorrogacao["permitida"] is True
        assert prorrogacao["motivo"] is None
        assert prorrogacao["pedido"] is None
        assert prorrogacao["max_dias_uteis"] == 30
        texto_das_regras = " ".join(prorrogacao["regras"])
        assert "uma única vez" in texto_das_regras
        assert "antes do vencimento" in texto_das_regras
        assert "justificativa" in texto_das_regras.lower()

    def test_regras_do_portal_saem_sem_travessao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Regra da casa (ADR 0013): nada que o usuário lê leva travessão."""
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        prorrogacao = client.get(f"/api/ouvidoria-setor/{token}").json()["prorrogacao"]

        assert "—" not in " ".join(prorrogacao["regras"])
        assert "–" not in " ".join(prorrogacao["regras"])


class TestPedidoPeloPortal:
    """Critério 1, segunda metade: o pedido entra pelo link, com justificativa
    obrigatória, e o prazo proposto sai do motor."""

    def test_pedido_valido_entra_como_pendente_com_o_prazo_proposto(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _pedir(client, token, dias=5)

        assert resposta.status_code == 201, resposta.text
        pedido = resposta.json()["prorrogacao"]
        assert pedido["status"] == "pendente"
        assert pedido["dias_uteis_pedidos"] == 5
        assert pedido["prazo_anterior"] == PRAZO_ORIGINAL
        assert pedido["prazo_novo"] == PRAZO_PRORROGADO
        assert pedido["solicitante_nome"] == "Carlos Titular"
        assert len(sb.tabelas["ouvidoria_prorrogacoes"]) == 1

    def test_pedido_pendente_nao_move_o_prazo_do_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quem decide é a Ouvidoria: pedir não é ganhar."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        _pedir(client, token)

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL

    def test_justificativa_em_branco_e_recusada(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _pedir(client, token, justificativa="   ")

        assert resposta.status_code == 422
        assert sb.tabelas["ouvidoria_prorrogacoes"] == []

    def test_pedir_prorrogacao_nao_queima_o_link_da_resposta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O token é de uso único para RESPONDER. Quem pede prazo ainda precisa
        do mesmo link depois, então o pedido não pode consumi-lo."""
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        _pedir(client, token)

        resposta = client.post(
            f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "Reforcamos a escala do plantao."}
        )
        assert resposta.status_code == 200, resposta.text

    def test_portal_passa_a_mostrar_o_pedido_e_a_fechar_a_porta(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token)

        prorrogacao = client.get(f"/api/ouvidoria-setor/{token}").json()["prorrogacao"]

        assert prorrogacao["permitida"] is False
        assert "apenas um" in prorrogacao["motivo"]
        assert prorrogacao["pedido"]["status"] == "pendente"


class TestRecusaAutomatica:
    """Critérios 2 e 3: pedido após o vencimento e segundo pedido são recusados
    pelo sistema, sem depender da atenção do ouvidor."""

    def test_pedido_depois_do_vencimento_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Mesmo caso, mesmo link, uma semana depois do prazo: a porta fechou."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        # O relógio anda para depois do vencimento (31/08 17h de Brasília).
        depois = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: depois)

        resposta = _pedir(client, token)

        assert resposta.status_code == 409
        assert "já venceu" in resposta.json()["detail"]
        assert sb.tabelas["ouvidoria_prorrogacoes"] == []

    def test_recusa_por_vencimento_nao_depende_de_ninguem_decidir(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A recusa automática não gera pedido pendente para o ouvidor olhar,
        nem email para ele."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        depois = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: depois)

        _pedir(client, token)

        gatilhos = [n["gatilho"] for n in sb.tabelas["ouvidoria_notificacoes"]]
        assert "prorrogacao_solicitada" not in gatilhos

    def test_segundo_pedido_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        assert _pedir(client, token).status_code == 201

        segundo = _pedir(client, token, dias=3, justificativa="O laudo atrasou de novo.")

        assert segundo.status_code == 409
        assert "apenas um" in segundo.json()["detail"]
        assert len(sb.tabelas["ouvidoria_prorrogacoes"]) == 1

    def test_segundo_pedido_e_recusado_mesmo_depois_de_negado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Negada continua sendo o pedido do caso: a regra é uma por
        manifestação, não uma por aprovação."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token).json()["prorrogacao"]
        client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": False, "justificativa": "Prazo suficiente."},
        )

        segundo = _pedir(client, token, dias=2, justificativa="Tentando de novo.")

        assert segundo.status_code == 409
        assert len(sb.tabelas["ouvidoria_prorrogacoes"]) == 1

    def test_caso_que_saiu_de_aguardando_area_nao_aceita_pedido(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        sb.tabelas["ouvidoria_protocolos"][0]["status"] = "respondido"

        resposta = _pedir(client, token)

        assert resposta.status_code == 409
        assert "não está aguardando" in resposta.json()["detail"]


class TestDecisaoDoOuvidor:
    """Critério 4: o ouvidor aprova ou nega, e o prazo novo respeita o teto de
    30 dias úteis contados da entrada."""

    def _pedido_pendente(self, monkeypatch, enviados, dias: int = 5):
        client, sb, token = _portal(monkeypatch, enviados)
        criado = _pedir(client, token, dias=dias).json()["prorrogacao"]
        return client, sb, criado

    def test_ouvidor_ve_o_pedido_pendente_no_painel(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, criado = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade)

        lista = client.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"]

        assert [p["id"] for p in lista] == [criado["id"]]
        assert lista[0]["justificativa"].startswith("A auditoria interna")

    def test_aprovar_move_o_prazo_do_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, criado = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": True, "justificativa": "Justificativa aceita."},
        )

        assert resposta.status_code == 200, resposta.text
        pedido = resposta.json()["prorrogacao"]
        assert pedido["status"] == "aprovada"
        assert pedido["decidida_por_nome"] == "Marta Ouvidora"
        assert pedido["prazo_novo"] == PRAZO_PRORROGADO
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_PRORROGADO

    def test_negar_deixa_o_prazo_onde_estava(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, criado = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": False, "justificativa": "O caso ja tem prazo folgado."},
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["prorrogacao"]["status"] == "negada"
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL

    def test_pedido_alem_do_teto_e_aprovado_ate_o_teto_e_nao_alem(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Vinte dias úteis a mais passariam do trigésimo dia útil da entrada.
        O prazo novo para no teto, e não no que a área pediu."""
        client, sb, criado = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade, dias=20)

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == TETO

    def test_segunda_decisao_e_recusada(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, criado = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade)
        rota = f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir"
        assert client.post(rota, json={"aprovada": True}).status_code == 200

        segunda = client.post(rota, json={"aprovada": False})

        assert segunda.status_code == 409
        assert "já foi decidido" in segunda.json()["detail"]

    def test_pedido_de_outro_caso_nao_e_decidido_por_aqui(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, _ = self._pedido_pendente(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/pedido-de-outro-caso/decidir", json={"aprovada": True}
        )

        assert resposta.status_code == 404


class TestProrrogacaoDevolveOCasoParaAFila:
    """Aprovar depois do prazo ter rompido precisa apagar o carimbo da
    cobrança, senão o prazo NOVO nunca é cobrado.

    `ouvidoria_cobranca` só olha caso com `prazo_rompido_em` nulo (índice da
    migration 071). Carimbo velho de um prazo que já não vale deixa o caso
    fora da fila para sempre, e ainda mente na trilha: prazo em setembro com
    carimbo de rompido em agosto."""

    def test_aprovar_apos_o_vencimento_limpa_o_carimbo_da_cobranca(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        # O job de cobrança rodou entre o pedido e a decisão: o prazo original
        # venceu e o caso foi cobrado.
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": True},
        )

        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["prazo_area_em"] == PRAZO_PRORROGADO
        assert caso["prazo_rompido_em"] is None

    def test_o_caso_prorrogado_volta_a_ser_cobravel_pelo_job(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A prova pelo lado de quem cobra: o filtro do job (aguardando área,
        sem carimbo) volta a enxergar o caso, e o prazo que ele vê é o novo."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        na_fila = [
            c
            for c in sb.tabelas["ouvidoria_protocolos"]
            if c["status"] == "aguardando_area" and c["prazo_rompido_em"] is None
        ]
        assert [c["id"] for c in na_fila] == ["uuid-7"]
        assert na_fila[0]["prazo_area_em"] == PRAZO_PRORROGADO

    def test_aprovar_limpa_os_carimbos_da_escada_inteira(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A cobrança não é o único job que depende de `prazo_area_em`: a
        escada de escalonamento (issue #336) tem os seus três carimbos, e
        `escalonar_prazos` pula todo degrau carimbado. O caso comum é
        exatamente esse: o pedido nasce PERTO do vencimento, quando a véspera
        já saiu."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0].update(
            {
                "prazo_rompido_em": "2026-08-31T20:10:00+00:00",
                "vespera_avisada_em": "2026-08-28T20:00:00+00:00",
                "escalonado_gestor_em": "2026-09-01T20:00:00+00:00",
                "escalonado_diretoria_em": "2026-09-02T20:00:00+00:00",
            }
        )

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": True},
        )

        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        for carimbo in ouvidoria_prorrogacao.CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert caso[carimbo] is None, carimbo

    def test_a_lista_de_carimbos_cobre_todo_degrau_do_escalonamento(self):
        """Todo carimbo de `DEGRAUS` está na lista que a prorrogação limpa.

        O alcance da guarda é o de `DEGRAUS`, e não o de "todo degrau que
        existir": degrau novo que não entre naquela tupla escapa deste teste
        do mesmo jeito que escaparia do motor, porque é ela que o motor
        percorre. É o `escalar_prazos` que a mantém honesta.

        `critico_avisado_em` fica de fora de propósito: não depende de prazo."""
        from app.services.ouvidoria_escalonamento import DEGRAUS

        carimbos = set(ouvidoria_prorrogacao.CARIMBOS_DEPENDENTES_DO_PRAZO)

        assert {degrau.carimbo for degrau in DEGRAUS} <= carimbos
        assert "prazo_rompido_em" in carimbos
        assert "critico_avisado_em" not in carimbos

    def test_aviso_de_caso_critico_nao_e_refeito(self, monkeypatch, _nunca_envia_email_de_verdade):
        """`critico_avisado_em` não sai do prazo: é o aviso de que existe um
        caso grave. Zerá-lo mandaria a Diretoria ser avisada duas vezes do
        mesmo caso só porque o setor ganhou mais prazo."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] = "2026-08-25T17:00:00+00:00"

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        assert sb.tabelas["ouvidoria_protocolos"][0]["critico_avisado_em"] == "2026-08-25T17:00:00+00:00"

    def test_o_caso_prorrogado_volta_a_varredura_do_escalonamento(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A prova pelo lado de quem escalona: `escalar_prazos` tira da
        varredura todo caso com `escalonado_diretoria_em` carimbado, e o caso
        prorrogado precisa voltar a ser lido.

        Quem responde é o motor de verdade (issue #375, item 19): a versão
        antiga reimplementava o filtro numa list comprehension do próprio
        teste, então mudar o WHERE do job deixava o teste verde."""
        from app.services import ouvidoria_escalonamento

        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        caso["escalonado_diretoria_em"] = "2026-09-02T20:00:00+00:00"
        caso["vespera_avisada_em"] = "2026-08-28T20:00:00+00:00"
        caso["escalonado_gestor_em"] = "2026-09-01T20:00:00+00:00"

        # Antes da decisão, a escada já subiu inteira: o motor não acha degrau
        # nenhum para dar neste caso.
        depois_do_novo_prazo = dt.datetime(2026, 9, 10, 20, 0, tzinfo=dt.UTC)
        assert ouvidoria_escalonamento.escalar_prazos(sb, depois_do_novo_prazo, frozenset()) == 0

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        # Depois, o caso volta à varredura e a escada sobe de novo sobre o
        # prazo novo. É o motor quem diz isso, não uma cópia do WHERE dele.
        assert ouvidoria_escalonamento.escalar_prazos(sb, depois_do_novo_prazo, frozenset()) > 0
        assert [n["manifestacao_id"] for n in sb.tabelas["ouvidoria_notificacoes"] if "escalonamento" in n["gatilho"]]

    def test_negar_nao_mexe_em_carimbo_nenhum(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Negar não move prazo, então nenhum degrau precisa acontecer de novo:
        limpar carimbo aqui faria o setor ser cobrado duas vezes pelo mesmo
        vencimento."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        carimbados = {
            "prazo_rompido_em": "2026-08-31T20:10:00+00:00",
            "vespera_avisada_em": "2026-08-28T20:00:00+00:00",
        }
        sb.tabelas["ouvidoria_protocolos"][0].update(carimbados)

        client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": False}
        )

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert {k: caso[k] for k in carimbados} == carimbados

    def test_negar_nao_mexe_no_carimbo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Negar não move prazo nenhum, então a cobrança que já saiu continua
        valendo: apagar o carimbo aqui faria o setor ser cobrado duas vezes
        pelo mesmo vencimento."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"

        client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": False}
        )

        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] == "2026-08-31T20:10:00+00:00"


class TestDecisaoSimultanea:
    """O painel é de mais de uma pessoa. Checar o status em Python e gravar
    numa segunda viagem ao banco deixa duas decisões passarem: duas linhas na
    trilha IMUTÁVEL, dois emails, e aprovar mais negar deixando o prazo movido
    com o pedido marcado negada.

    O claim é o mesmo idioma dos vizinhos (`ouvidoria_notificacoes._reivindicar`,
    `ouvidoria_cobranca._reivindicar_caso`): o update carrega a condição."""

    def _dois_ouvidores_leram_pendente(self, monkeypatch, sb):
        """Congela a leitura do pedido no estado pendente: é o que uma corrida
        real produz, e é o que faz o pré-check em Python deixar os dois passar."""
        instantaneo = dict(sb.tabelas["ouvidoria_prorrogacoes"][0])
        monkeypatch.setattr(ouvidoria_prorrogacao, "carregar_pedido", lambda *_a, **_kw: dict(instantaneo))

    def test_so_a_primeira_decisao_vale(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        self._dois_ouvidores_leram_pendente(monkeypatch, sb)
        rota = f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir"

        primeira = client.post(rota, json={"aprovada": True})
        segunda = client.post(rota, json={"aprovada": False, "justificativa": "Mudei de ideia."})

        assert primeira.status_code == 200, primeira.text
        assert segunda.status_code == 409
        assert "já foi decidido" in segunda.json()["detail"]

    def test_a_corrida_nao_deixa_prazo_movido_com_pedido_negado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        self._dois_ouvidores_leram_pendente(monkeypatch, sb)
        rota = f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir"

        client.post(rota, json={"aprovada": True})
        client.post(rota, json={"aprovada": False, "justificativa": "Mudei de ideia."})

        assert sb.tabelas["ouvidoria_prorrogacoes"][0]["status"] == "aprovada"
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_PRORROGADO

    def test_a_corrida_nao_duplica_a_trilha_nem_o_email(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        self._dois_ouvidores_leram_pendente(monkeypatch, sb)
        rota = f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir"

        client.post(rota, json={"aprovada": True})
        client.post(rota, json={"aprovada": False, "justificativa": "Mudei de ideia."})

        decisoes = [
            m
            for m in sb.tabelas["ouvidoria_movimentos"]
            if "Prorrogação aprovada" in (m["observacao"] or "") or "Prorrogação negada" in (m["observacao"] or "")
        ]
        assert len(decisoes) == 1
        avisos = [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_decidida"]
        assert len(avisos) == 1


class TestRespostaNoMeioDaDecisao:
    """O pré-check de `status = aguardando_area` roda sobre o caso lido no
    começo da rota. Se o setor responder entre aquela leitura e a escrita do
    prazo, mover o vencimento reabriria a cobrança de um caso já respondido."""

    def _a_area_responde_no_meio(self, monkeypatch, sb):
        real = ouvidoria_prorrogacao.carregar_pedido

        def _com_resposta_no_meio(*args, **kwargs):
            # Depois de o caso ter sido lido, antes de o prazo ser escrito.
            sb.tabelas["ouvidoria_protocolos"][0]["status"] = "respondido"
            return real(*args, **kwargs)

        monkeypatch.setattr(ouvidoria_prorrogacao, "carregar_pedido", _com_resposta_no_meio)

    def test_o_prazo_nao_se_move_num_caso_que_acabou_de_responder(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"
        self._a_area_responde_no_meio(monkeypatch, sb)

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True}
        )

        assert resposta.status_code == 409
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["prazo_area_em"] == PRAZO_ORIGINAL
        assert caso["prazo_rompido_em"] == "2026-08-31T20:10:00+00:00"

    def test_o_pedido_volta_a_pendente_com_a_proposta_intacta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O claim é devolvido para o ouvidor poder decidir de novo, e
        `prazo_novo` sobrevive: ele nasce no pedido do portal, não na decisão,
        e sem ele o reenvio do email diria "prazo proposto: sem prazo
        definido"."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        self._a_area_responde_no_meio(monkeypatch, sb)

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        pedido = sb.tabelas["ouvidoria_prorrogacoes"][0]
        assert pedido["status"] == "pendente"
        assert pedido["prazo_novo"] == PRAZO_PRORROGADO
        assert pedido["decidida_em"] is None

    def test_a_decisao_abortada_nao_deixa_rastro_na_trilha_nem_email(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        self._a_area_responde_no_meio(monkeypatch, sb)

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        assert not [m for m in sb.tabelas["ouvidoria_movimentos"] if "Prorrogação aprovada" in (m["observacao"] or "")]
        assert not [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_decidida"]


class TestIndicadorDeCumprimento:
    """Critério 5: prorrogação aprovada conta como cumprido; vencido em
    silêncio conta como estouro."""

    def test_resposta_dentro_do_prazo_prorrogado_conta_como_cumprida(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})
        # A área responde 02/09, depois do prazo ORIGINAL (31/08) e dentro do
        # prorrogado (08/09).
        depois_do_original = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: depois_do_original)
        client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "Escala reforcada no plantao."})

        monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: depois_do_original)
        linha = next(p for p in client.get("/api/ouvidoria/protocolos").json()["protocolos"] if p["id"] == "uuid-7")

        assert linha["cumprimento"] == "cumprido"
        assert sb.tabelas["ouvidoria_prorrogacoes"][0]["status"] == "aprovada"

    def test_sem_a_prorrogacao_a_mesma_resposta_contaria_estouro(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O contraste que prova que é a prorrogação aprovada que muda o
        indicador, e não a data da resposta por si só."""
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        depois_do_original = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: depois_do_original)
        client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "Escala reforcada no plantao."})

        monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: depois_do_original)
        linha = next(p for p in client.get("/api/ouvidoria/protocolos").json()["protocolos"] if p["id"] == "uuid-7")

        assert linha["cumprimento"] == "estourado"

    def test_vencido_em_silencio_conta_estouro(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, _ = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        depois = dt.datetime(2026, 9, 2, 17, 0, tzinfo=dt.UTC)
        monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: depois)

        linha = next(p for p in client.get("/api/ouvidoria/protocolos").json()["protocolos"] if p["id"] == "uuid-7")

        assert linha["cumprimento"] == "estourado"

    def test_prazo_correndo_ainda_nao_e_nem_cumprido_nem_estouro(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, _ = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        linha = next(p for p in client.get("/api/ouvidoria/protocolos").json()["protocolos"] if p["id"] == "uuid-7")

        assert linha["cumprimento"] == "em_prazo"


class TestTrilhaDoCaso:
    """Critério 6: pedido e decisão aparecem na trilha imutável do caso."""

    def test_pedido_e_decisao_viram_movimentos(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": True, "justificativa": "Justificativa aceita."},
        )

        observacoes = [m["observacao"] or "" for m in sb.tabelas["ouvidoria_movimentos"]]

        pedido = next(o for o in observacoes if "Prorrogação solicitada" in o)
        assert "A auditoria interna" in pedido
        decisao = next(o for o in observacoes if "Prorrogação aprovada" in o)
        assert "08/09/2026" in decisao
        assert "Justificativa aceita." in decisao

    def test_movimento_do_pedido_credita_quem_pediu_e_nao_muda_o_estado(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        _pedir(client, token)

        movimento = next(
            m for m in sb.tabelas["ouvidoria_movimentos"] if "Prorrogação solicitada" in (m["observacao"] or "")
        )
        assert movimento["autor_nome"] == "Carlos Titular"
        assert movimento["autor_id"] is None
        assert movimento["estado_anterior"] == movimento["estado_novo"] == "aguardando_area"


class TestEmailsDaProrrogacao:
    """Critério 7: solicitada e decidida são enviadas, registradas e
    reenviáveis. O Resend é mockado."""

    def test_pedido_avisa_a_ouvidoria_e_fica_registrado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)

        _pedir(client, token, dias=5)

        registradas = [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_solicitada"]
        assert {n["destinatario_email"] for n in registradas} == {"marta@hsm.br", "diretor@hsm.br"}
        assert all(n["status"] == "enviada" for n in registradas)
        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "marta@hsm.br")
        assert "prorrogacao" in email["assunto"]
        assert "A auditoria interna" in email["texto"]
        assert "08/09/2026" in email["texto"]

    def test_diretora_desligada_nao_e_avisada_do_pedido_de_prorrogacao(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Issue #403: o assunto deste email leva o número do protocolo e o
        corpo leva o setor, e a leitura da Ouvidoria (que inclui a Diretoria)
        não filtrava `ativo`. O desligamento do hospital é soft delete e não
        limpa `perfil_ouvidoria`, então quem saiu continuava sendo avisado de
        cada pedido, inclusive em denúncia sigilosa.

        A ouvidora ATIVA recebe no mesmo cenário: a porta certa fica aberta."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        diretora = next(p for p in sb.tabelas["participantes"] if p["id"] == "P11")
        diretora["ativo"] = False

        _pedir(client, token, dias=5)

        registradas = [n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_solicitada"]
        assert {n["destinatario_email"] for n in registradas} == {"marta@hsm.br"}
        assert "diretor@hsm.br" not in [e["destinatario"] for e in _nunca_envia_email_de_verdade]

    def test_decisao_avisa_quem_pediu_com_o_prazo_que_passa_a_valer(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        _nunca_envia_email_de_verdade.clear()

        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        registrada = next(n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_decidida")
        assert registrada["destinatario_email"] == "carlos@hsm.br"
        assert registrada["status"] == "enviada"
        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")
        assert "aprovada" in email["assunto"]
        assert "08/09/2026" in email["texto"]

    def test_email_da_negativa_diz_que_o_prazo_continua(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        _nunca_envia_email_de_verdade.clear()

        client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir",
            json={"aprovada": False, "justificativa": "O prazo atual ja e suficiente."},
        )

        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")
        assert "negada" in email["assunto"]
        assert "31/08/2026" in email["texto"]
        assert "O prazo atual ja e suficiente." in email["texto"]

    def test_emails_da_prorrogacao_sao_reenviaveis_pelo_painel(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})
        decidida = next(n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == "prorrogacao_decidida")
        _nunca_envia_email_de_verdade.clear()

        resposta = client.post(f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{decidida['id']}/reenviar")

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["entregue"] is True
        assert any(e["destinatario"] == "carlos@hsm.br" for e in _nunca_envia_email_de_verdade)

    def test_email_do_setor_leva_link_tokenizado_e_o_da_ouvidoria_nao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Quem responde sem login precisa do token; quem tem painel, não."""
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        aviso_ouvidoria = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "marta@hsm.br")
        _nunca_envia_email_de_verdade.clear()
        client.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})
        aviso_setor = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")

        assert "/ouvidoria-setor/" not in aviso_ouvidoria["texto"]
        assert re.search(r"http://app\.test/ouvidoria-setor/[A-Za-z0-9_-]+", aviso_setor["texto"])


class TestOQuePortalNaoRevela:
    """O bloco de prorrogação do portal é fechado campo a campo, como o resto
    da página: o link é de fora da Ouvidoria."""

    def test_pedido_no_portal_nao_leva_id_interno_nem_email_de_outra_pessoa(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """`manifestacao_id` é UUID interno que `abrir_portal` nunca devolve, e
        `solicitante_email` é o endereço do titular: o substituto tem link do
        mesmo caso e não precisa dele."""
        client, _, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token)

        pedido = client.get(f"/api/ouvidoria-setor/{token}").json()["prorrogacao"]["pedido"]

        assert "manifestacao_id" not in pedido
        assert "solicitante_email" not in pedido
        assert "uuid-7" not in str(pedido)
        assert "carlos@hsm.br" not in str(pedido)
        # O que o titular precisa continua lá.
        assert pedido["status"] == "pendente"
        assert pedido["solicitante_nome"] == "Carlos Titular"


class TestIndicadorNoPortal:
    """O portal projeta o prazo pelo mesmo motor do painel, então o indicador
    tem de enxergar a resposta da área. Sem o marco T2 no select, ele diria
    que ninguém respondeu, num endpoint semi-público."""

    def test_caso_respondido_aparece_cumprido_para_quem_abre_o_link(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        # A área respondeu por outro link do mesmo caso (titular e substituto
        # têm cada um o seu), antes do vencimento de 31/08.
        sb.tabelas["ouvidoria_protocolos"][0].update(
            {"status": "respondido", "respondida_em": "2026-08-27T14:00:00+00:00"}
        )

        corpo = client.get(f"/api/ouvidoria-setor/{token}").json()

        assert corpo["aceita_resposta"] is False
        assert corpo["cumprimento"] == "cumprido"


class TestGateDoPainel:
    """As rotas de prorrogação do painel são da Ouvidoria: quem não tem perfil
    não lista nem decide (ADR 0034, decisão 8)."""

    SECRETARIA = {
        "id": "P12",
        "nome_completo": "Sofia Secretaria",
        "access_profile": "secretaria",
        "perfil_ouvidoria": None,
    }

    def test_quem_nao_e_da_ouvidoria_nao_lista_nem_decide(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        # Mesmo supabase, outra pessoa logada.
        de_fora, _ = _client(monkeypatch, supabase=sb, participante=self.SECRETARIA)

        listagem = de_fora.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes")
        decisao = de_fora.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True}
        )

        assert listagem.status_code == 403
        assert decisao.status_code == 403
        assert sb.tabelas["ouvidoria_prorrogacoes"][0]["status"] == "pendente"
        assert sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] == PRAZO_ORIGINAL


class TestRegistroNoApp:
    """Os testes acima montam um FastAPI próprio: este prova que as rotas
    existem no app de verdade (mesmo padrão de test_ouvidoria_prazos)."""

    def test_rotas_da_prorrogacao_existem_no_app_real(self):
        from app.main import app as app_real

        paths = app_real.openapi()["paths"]
        assert "post" in paths["/api/ouvidoria-setor/{token}/prorrogacao"]
        assert "get" in paths["/api/ouvidoria/manifestacoes/{manifestacao_id}/prorrogacoes"]
        assert "post" in paths["/api/ouvidoria/manifestacoes/{manifestacao_id}/prorrogacoes/{prorrogacao_id}/decidir"]


# Semanas depois do vencimento original (31/08): a Ouvidoria só olhou o pedido
# agora. Somar os 5 dias úteis pedidos sobre o prazo VIGENTE devolve 08/09, que
# já passou. Segunda-feira, dentro do expediente.
DECISAO_TARDIA = dt.datetime(2026, 9, 21, 17, 0, tzinfo=dt.UTC)


class TestAprovacaoTardia:
    """Issue #373, defeito 1: `vencimento_prorrogado` conta dias úteis sobre o
    prazo vigente, nunca sobre `agora`. Decisão tomada muito depois do
    vencimento nasce com o prazo novo no passado, e o setor recebe "prorrogação
    aprovada" seguido de "prazo rompido"."""

    def _pedido_pendente_e_decisao_tardia(self, monkeypatch, enviados, dias: int = 5):
        """O pedido entra a tempo; a decisão só acontece semanas depois."""
        client, sb, token = _portal(monkeypatch, enviados)
        criado = _pedir(client, token, dias=dias).json()["prorrogacao"]
        tardio, _ = _client(monkeypatch, supabase=sb, agora=DECISAO_TARDIA)
        return tardio, sb, criado

    def test_aprovacao_que_nasceria_vencida_e_recusada(self, monkeypatch, _nunca_envia_email_de_verdade):
        tardio, _, criado = self._pedido_pendente_e_decisao_tardia(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = tardio.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True}
        )

        assert resposta.status_code == 409, resposta.text
        assert "não há prazo a conceder" in resposta.json()["detail"]

    def test_recusa_tardia_nao_manda_aprovada_seguida_de_prazo_rompido(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O sintoma que o setor vê. A recusa acontece ANTES do claim, então o
        pedido segue pendente, o prazo não anda e nenhum email de decisão sai."""
        tardio, sb, criado = self._pedido_pendente_e_decisao_tardia(monkeypatch, _nunca_envia_email_de_verdade)
        # O prazo original rompeu no meio do caminho, e o setor já foi cobrado.
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"
        _nunca_envia_email_de_verdade.clear()

        tardio.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["prazo_area_em"] == PRAZO_ORIGINAL
        # O carimbo da cobrança fica: zerá-lo devolveria o caso à fila do job
        # com o mesmo prazo vencido, e ele cobraria de novo.
        assert caso["prazo_rompido_em"] == "2026-08-31T20:10:00+00:00"
        assert sb.tabelas["ouvidoria_prorrogacoes"][0]["status"] == "pendente"
        assert _nunca_envia_email_de_verdade == []

    def test_a_escada_nao_sobe_dois_degraus_depois_de_uma_aprovacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A prova pelo lado do job: com a recusa, os carimbos da escada não
        são zerados, então gestor e Diretoria não sobem juntos na rodada
        seguinte."""
        tardio, sb, criado = self._pedido_pendente_e_decisao_tardia(monkeypatch, _nunca_envia_email_de_verdade)
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        caso["prazo_rompido_em"] = "2026-08-31T20:10:00+00:00"
        caso["vespera_avisada_em"] = "2026-08-28T20:00:00+00:00"
        caso["escalonado_gestor_em"] = "2026-09-01T20:00:00+00:00"

        tardio.post(f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True})

        assert caso["vespera_avisada_em"] == "2026-08-28T20:00:00+00:00"
        assert caso["escalonado_gestor_em"] == "2026-09-01T20:00:00+00:00"

    def test_painel_avisa_o_ouvidor_antes_de_ele_confirmar(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O 409 não pode ser surpresa: a listagem que a tela lê já diz que
        aprovar não tem efeito, e diz por quê."""
        tardio, _, criado = self._pedido_pendente_e_decisao_tardia(monkeypatch, _nunca_envia_email_de_verdade)

        pedido = tardio.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"][0]

        assert pedido["id"] == criado["id"]
        assert pedido["aprovacao_possivel"] is False
        assert "não há prazo a conceder" in pedido["motivo_da_aprovacao"]

    def test_painel_libera_a_aprovacao_quando_ainda_ha_prazo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O outro caminho da mesma guarda: decisão no dia, prazo novo no
        futuro, botão liberado."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token, dias=5)

        pedido = client.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"][0]

        assert pedido["aprovacao_possivel"] is True
        assert pedido["motivo_da_aprovacao"] is None

    def test_painel_avisa_quando_o_caso_saiu_de_aguardando_area(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A terceira recusa do `decidir` também não pode ser surpresa: o caso
        respondeu enquanto o pedido esperava decisão, e aprovar não tem efeito."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token, dias=5)
        sb.tabelas["ouvidoria_protocolos"][0]["status"] = "respondida"

        pedido = client.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"][0]

        assert pedido["aprovacao_possivel"] is False
        assert "aguardando a área" in pedido["motivo_da_aprovacao"]

    def test_caso_sem_entrada_nao_e_confundido_com_teto_alcancado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Três situações diferentes davam a mesma mensagem de teto. O ouvidor
        que lê "teto de 30 dias úteis" num caso sem data de entrada vai conferir
        o calendário em vez do cadastro do caso."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token, dias=5)
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        caso["contato_em"] = None
        caso["data_abertura"] = None

        pedido = client.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"][0]

        assert pedido["aprovacao_possivel"] is False
        assert "teto" not in pedido["motivo_da_aprovacao"].lower()
        assert "entrada" in pedido["motivo_da_aprovacao"].lower()

    def test_pedido_no_teto_diz_teto_e_nao_prazo_no_passado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O par que separa as quatro recusas. Sem ele, trocar a mensagem do
        teto pela do prazo no passado não quebraria teste nenhum, e o ouvidor
        leria "negue o pedido" quando o certo é "o teto acabou"."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        _pedir(client, token, dias=5)
        # Prazo vigente já no teto de 30 dias úteis da entrada: somar dias não
        # produz vencimento novo.
        sb.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"] = TETO

        pedido = client.get("/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes").json()["prorrogacoes"][0]

        assert pedido["aprovacao_possivel"] is False
        assert "teto" in pedido["motivo_da_aprovacao"].lower()
        assert "passado" not in pedido["motivo_da_aprovacao"].lower()

    def test_data_ilegivel_recusa_com_409_e_nao_com_500(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A rota calculava o prazo por fora de `prazo_novo_proposto`, então
        uma data ilegível estourava `ValueError` e virava 500."""
        client, sb, token = _portal(monkeypatch, _nunca_envia_email_de_verdade)
        criado = _pedir(client, token, dias=5).json()["prorrogacao"]
        sb.tabelas["ouvidoria_protocolos"][0]["contato_em"] = "data-que-nao-e-data"

        resposta = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/prorrogacoes/{criado['id']}/decidir", json={"aprovada": True}
        )

        assert resposta.status_code == 409, resposta.text
        assert sb.tabelas["ouvidoria_prorrogacoes"][0]["status"] == "pendente"


class TestComentariosApontamParaAMigrationCerta:
    """Issue #375, item 17: os dois comentários citavam a migration 072 para o
    índice `idx_ouvidoria_prorrogacoes_unica`, que mora na 073 (a 072 é a
    escada de escalonamento). A referência ficou stale na renumeração e virou
    ativamente enganosa: quem for conferir a regra abre o arquivo errado.

    O teste existe porque a próxima renumeração faz de novo."""

    ARQUIVOS = (
        "app/routers/ouvidoria_setor.py",
        "app/services/ouvidoria_prorrogacao.py",
    )
    INDICE = "idx_ouvidoria_prorrogacoes_unica"

    def _migration_do_indice(self) -> str:
        raiz = Path(__file__).resolve().parents[2]
        for caminho in sorted((raiz / "supabase" / "migrations").glob("*.sql")):
            if self.INDICE in caminho.read_text(encoding="utf-8"):
                return caminho.name.split("_")[0]
        raise AssertionError(f"Nenhuma migration cria o índice {self.INDICE}")

    def test_quem_cita_o_indice_unico_cita_a_migration_que_o_cria(self):
        numero = self._migration_do_indice()
        backend = Path(__file__).resolve().parents[1]

        for relativo in self.ARQUIVOS:
            texto = (backend / relativo).read_text(encoding="utf-8")
            citadas = set(re.findall(r"índice\s+único\s+da\s+migration\s+(\d+)", texto))
            assert citadas, f"{relativo} deixou de citar o índice único; ajuste ou remova este teste"
            assert citadas == {numero}, f"{relativo} cita a migration {citadas}, mas o índice mora na {numero}"
