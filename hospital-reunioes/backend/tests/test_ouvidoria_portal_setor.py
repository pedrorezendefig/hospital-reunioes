"""Portal do setor por link tokenizado (issue #326, PRD #317).

O titular do setor recebe o email de acionamento com um link seguro, sem
login, no padrão do Aceite interno (ADR 0030): token de uso restrito por
manifestação e destinatário, só o hash no banco. A página pública mostra o
extrato necessário do caso e o prazo, e colhe a resposta da área (T2). O
ouvidor então encerra com desfecho e descrição (T3).

Cobre os critérios de aceite da issue #326 pelo seam HTTP. O Resend nunca é
chamado de verdade: o envio é mockado no ponto único por onde todo email
do app passa.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import re
import sys

import httpx
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
from app.middleware.sem_cache import SemCacheMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes, ouvidoria_setor_tokens  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}

EXTRATO = "Conduta da equipe de enfermagem no plantao noturno. Apurar e responder a Ouvidoria."
# O resumo e o relato do caso, que desde o ADR 0041 viajam com o extrato nos
# três blocos do acionamento (issue #481).
RESUMO = "Paciente relata espera acima de duas horas na recepcao."
RELATO = "Cheguei as 8h com minha mae e so fomos atendidos as 10h30."

VALIDACAO = {
    # Lista fechada desde a issue #372: é o tipo, e não o rótulo, que decide o
    # sigilo do caso.
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "gravidade": "medio",
    "extrato_para_o_setor": EXTRATO,
}

# Terça-feira, 14h de Brasília: dentro do expediente, o email sai na hora.
DENTRO_DO_EXPEDIENTE = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)


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
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
            }
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
        "resumo": RESUMO,
        "conversa_id": "",
        "contato_em": "2026-08-14T19:50:00+00:00",
        "relato_integral": RELATO,
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
    pedido, o insert devolve a linha com id, e `is_`/`eq` filtram como lá."""

    def __init__(self, nome: str, rows: list[dict], falha_no_execute: Exception | None = None):
        self.nome = nome
        self.rows = rows
        # A falha levantada DENTRO do `execute` (issue #449): é onde o
        # transporte quebra de verdade, porque o cliente PostgREST só toca a
        # rede aí. Fake que quebra no `table()` não exercita esse caminho.
        self.falha_no_execute = falha_no_execute
        self._filters: dict = {}
        self._ate: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
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

    def delete(self):
        self._delete = True
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def is_(self, col, value):
        self._filters[col] = None if value in ("null", None) else value
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

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        if self.falha_no_execute is not None:
            raise self.falha_no_execute
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
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
            and all(str(r.get(c) or "") <= v for c, v in self._ate.items())
        ]
        if self._update is not None:
            atualizadas = []
            for r in casadas:
                r.update(self._update)
                atualizadas.append(dict(r))
            return type("R", (), {"data": atualizadas})()
        if self._delete:
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": []})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _BucketFake:
    def __init__(self, arquivos: dict):
        self.arquivos = arquivos

    def upload(self, path, content, _opts=None):
        self.arquivos[path] = content

    def remove(self, paths):
        for p in paths:
            self.arquivos.pop(p, None)


class _StorageFake:
    """Bucket privado em memória: o teste confere que o binário subiu."""

    def __init__(self):
        self.arquivos: dict[str, bytes] = {}

    def from_(self, _bucket):
        return _BucketFake(self.arquivos)


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None, responsaveis: list[dict] | None = None):
        self.storage = _StorageFake()
        # Quando preenchido, a próxima transição levanta esse erro em vez de
        # mudar o estado: é como o Postgres recusa a corrida entre transições.
        self.rpc_recusa: APIError | None = None
        # Tabelas que o banco recusa a servir, para exercitar a degradação
        # (issue #449). Mesmo mecanismo do fake das métricas.
        self.indisponiveis: set[str] = set()
        # Por tabela, a exceção que o `execute` da leitura levanta. É como a
        # falha de transporte do httpx chega: antes de existir resposta HTTP, e
        # por isso nunca como `APIError`.
        self.falhas_no_execute: dict[str, Exception] = {}
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [_manifestacao()],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            "ouvidoria_notificacoes": [],
            "ouvidoria_setor_responsaveis": responsaveis if responsaveis is not None else [_responsavel()],
            "ouvidoria_setor_tokens": [],
            "ouvidoria_prazos": [dict(p) for p in PRAZOS],
            "ouvidoria_feriados": [{"data": "2026-09-07", "nome": "Independencia", "abrangencia": "nacional"}],
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            "participantes": [
                {"id": "P11", "nome_completo": "Dr. Diretor", "email": "diretor@hsm.br"},
            ],
        }

    def table(self, nome: str):
        if nome in self.indisponiveis:
            raise APIError({"message": f"{nome} indisponivel", "code": "PGRST000"})
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self.falhas_no_execute.get(nome))

    def rpc(self, nome: str, params: dict):
        """Efeito da função `ouvidoria_transicionar` (migration 064): estado e
        movimento na mesma transação."""
        assert nome == "ouvidoria_transicionar", f"RPC inesperada: {nome}"
        if self.rpc_recusa is not None:
            erro, self.rpc_recusa = self.rpc_recusa, None
            raise erro
        alvo = next(m for m in self.tabelas["ouvidoria_protocolos"] if m["id"] == params["p_manifestacao_id"])
        anterior = alvo["status"]
        alvo["status"] = params["p_estado_novo"]
        if params.get("p_desfecho"):
            alvo["desfecho"] = params["p_desfecho"]
        if params.get("p_desfecho_descricao"):
            alvo["desfecho_descricao"] = params["p_desfecho_descricao"]
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
    participante: dict | None = None,
    supabase: _SupabaseFake | None = None,
    agora: dt.datetime = DENTRO_DO_EXPEDIENTE,
):
    """App de teste com o painel do ouvidor E o portal público do setor."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    # Na mesma ordem do `main`: o portal do setor é uma das áreas que saem com
    # `no-store`, e sem a peça montada aqui a promessa dele ficaria sem teste
    # que a exercite de verdade (issue #439).
    app.add_middleware(SemCacheMiddleware)
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
    """Valida e aciona a manifestação uuid-7 pelo fluxo real da F4."""
    resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
    assert resposta.status_code == 200, resposta.text


def _token_do_email(enviados: list[dict]) -> str:
    """Extrai o token do link do email, como o titular clicaria."""
    email = next(e for e in enviados if e["destinatario"] == "carlos@hsm.br")
    achado = re.search(r"http://app\.test/ouvidoria-setor/([A-Za-z0-9_-]+)", email["texto"])
    assert achado, f"O email de acionamento não tem link tokenizado: {email['texto']}"
    return achado.group(1)


class TestLinkTokenizadoNoEmail:
    """O email de acionamento leva o portal do setor, não mais um placeholder."""

    def test_titular_abre_o_link_do_email_e_ve_extrato_prazo_e_campo_de_resposta(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Critério 1: o link do email abre o extrato do caso, o prazo em
        linguagem natural e o caso aceita resposta."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["protocolo"] == "2026-0007"
        assert corpo["setor"] == "Recepcao"
        assert corpo["extrato"] == EXTRATO
        assert "dias úteis" in corpo["rotulo_prazo"]
        assert corpo["aceita_resposta"] is True
        # Caso comum, sem sigilo: o titular vê quem manifestou.
        assert corpo["identificacao"] == "Joana da Silva"

    def test_portal_diz_quando_o_calendario_nao_pode_ser_lido(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O portal afirma "vence em N dias úteis" para quem tem que responder,
        e o número sai do calendário de feriados. Quando a leitura falha, a
        resposta marca isso em `degradado` (issue #449): sem a marca, a página
        afirmava o prazo com um calendário vazio por falha, e o titular não
        tinha como saber que a conta estava contando feriado como dia útil.

        As outras portas ficam abertas de propósito: extrato, identificação e o
        campo de resposta continuam vindo, então o teste mede a marca e não uma
        falha que apagou a página."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        lido = client.get(f"/api/ouvidoria-setor/{token}")
        assert lido.status_code == 200, lido.text
        assert lido.json()["degradado"] == []

        sb.indisponiveis = {"ouvidoria_feriados"}
        ilegivel = client.get(f"/api/ouvidoria-setor/{token}")
        assert ilegivel.status_code == 200, ilegivel.text
        corpo = ilegivel.json()
        assert corpo["degradado"] == ["feriados"]
        assert corpo["extrato"] == EXTRATO, "a página continuou abrindo: o fail-open é a promessa"
        assert corpo["aceita_resposta"] is True

    @pytest.mark.parametrize(
        "falha",
        [
            pytest.param(httpx.ReadTimeout("o banco não respondeu no tempo"), id="read-timeout"),
            pytest.param(httpx.ConnectError("conexão recusada"), id="connect-error"),
        ],
    )
    def test_timeout_no_calendario_nao_fecha_a_porta_do_setor(self, monkeypatch, _nunca_envia_email_de_verdade, falha):
        """A falha de rede é a mais provável de todas, e nenhuma exceção do httpx
        é `APIError` nem `OSError`: elas nascem antes de existir resposta HTTP.
        Se a tupla do `except` não as cobrisse, esta porta devolveria 500 e quem
        tem que responder perderia extrato, campo de resposta e prorrogação,
        com o relógio do prazo correndo (issue #449)."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        sb.falhas_no_execute = {"ouvidoria_feriados": falha}
        resposta = client.get(f"/api/ouvidoria-setor/{token}")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["degradado"] == ["feriados"]
        # A página inteira continuou de pé: é isso que o fail-open promete.
        assert corpo["extrato"] == EXTRATO
        assert corpo["aceita_resposta"] is True
        assert corpo["prorrogacao"]["regras"], "o bloco de prorrogação sumiu junto"

    def test_banco_guarda_so_o_hash_do_token(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O token em claro vive só no email (padrão do Aceite, migration 060):
        vazar o banco não vaza o link."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        linhas = sb.tabelas["ouvidoria_setor_tokens"]
        assert len(linhas) == 1
        assert linhas[0]["manifestacao_id"] == "uuid-7"
        assert linhas[0]["destinatario_email"] == "carlos@hsm.br"
        assert token not in str(linhas[0])

    def test_o_log_do_container_tambem_guarda_so_o_hash(self, monkeypatch, caplog, _nunca_envia_email_de_verdade):
        """A outra ponta do mesmo invariante (issue #465).

        O path do portal É o token, e a linha de request do middleware gravava
        ele inteiro: o banco guardar só o hash não adiantava, porque quem lê o
        log do Coolify abria o caso e respondia pelo setor. Aqui é o portal
        aberto de verdade, com token válido e resposta 200."""
        client, _sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        with caplog.at_level(logging.INFO, logger="app.requests"):
            resposta = client.get(f"/api/ouvidoria-setor/{token}")

        assert resposta.status_code == 200, resposta.text
        registros = [r for r in caplog.records if r.name == "app.requests"]
        assert registros, "o request do portal não foi logado"
        assert all(token not in getattr(r, "path", "") for r in registros)
        assert registros[-1].path == "/api/ouvidoria-setor/{token}"


class TestRecusasDoToken:
    """Critério 2: token inválido, expirado ou de outro caso é recusado com
    erro claro, sem vazar a existência do caso."""

    def test_token_invalido_e_404_sem_nada_do_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        resposta = client.get("/api/ouvidoria-setor/um-token-que-nao-existe")
        assert resposta.status_code == 404
        assert "2026-0007" not in resposta.text

    def test_token_expirado_e_410(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        sb.tabelas["ouvidoria_setor_tokens"][0]["expira_em"] = "2026-08-01T00:00:00+00:00"

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        assert resposta.status_code == 410
        assert "expirou" in resposta.json()["detail"]
        assert "2026-0007" not in resposta.text

    def test_token_de_um_caso_nao_abre_outro(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O token carrega o caso dele: o link do caso 7 nunca mostra o caso 8,
        mesmo os dois estando acionados no mesmo setor."""
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7), _manifestacao(8)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        assert resposta.status_code == 200
        assert resposta.json()["protocolo"] == "2026-0007"
        assert "2026-0008" not in resposta.text

    def test_caso_sigiloso_sai_sem_identificacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 1, parte do sigilo: o extrato aparece, o manifestante não."""
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7, sigilo_reforcado=True)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["identificacao"] is None
        assert corpo["sigiloso"] is True
        assert "Joana da Silva" not in resposta.text


RESPOSTA_DA_AREA = "Conversamos com a equipe do plantao e reforcamos o protocolo de atendimento."


class TestRespostaDoSetor:
    """Critérios 3 e 6: a resposta grava T2, vira respondido e não duplica."""

    def test_resposta_grava_t2_vira_respondido_e_registra_movimento(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert resposta.status_code == 200, resposta.text

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "respondido"
        assert caso["resposta_da_area"] == RESPOSTA_DA_AREA
        assert caso["respondida_em"] == DENTRO_DO_EXPEDIENTE.isoformat()
        assert caso["respondida_por_nome"] == "Carlos Titular"

        movimento = sb.tabelas["ouvidoria_movimentos"][-1]
        assert movimento["estado_novo"] == "respondido"
        assert movimento["autor_id"] is None
        assert movimento["autor_nome"] == "Carlos Titular"

    def test_resposta_aparece_imediatamente_no_painel_do_ouvidor(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})

        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-7")
        assert dossie.status_code == 200
        corpo = dossie.json()
        assert corpo["status"] == "respondido"
        assert corpo["resposta_da_area"] == RESPOSTA_DA_AREA
        assert corpo["respondida_por_nome"] == "Carlos Titular"

    def test_resposta_vazia_e_422_e_o_link_continua_valendo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A página pede o que foi FEITO: espaço em branco não é resposta, e a
        recusa não pode queimar o token do titular."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "   "})
        assert resposta.status_code == 422
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"
        assert client.get(f"/api/ouvidoria-setor/{token}").status_code == 200

    def test_responder_duas_vezes_pelo_mesmo_link_nao_duplica(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 6: a segunda resposta é recusada com clareza e o estado do
        caso fica como estava."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        primeira = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert primeira.status_code == 200
        segunda = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "De novo"})
        assert segunda.status_code == 410
        assert "usado" in segunda.json()["detail"]

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "respondido"
        assert caso["resposta_da_area"] == RESPOSTA_DA_AREA
        respondidos = [m for m in sb.tabelas["ouvidoria_movimentos"] if m["estado_novo"] == "respondido"]
        assert len(respondidos) == 1


class TestMinimoDaResposta:
    """Issue #482 (RN-61): a resposta da área vale a partir de 20 caracteres, e
    a regra é do servidor, não da tela. Resposta de uma palavra não descreve o
    que foi FEITO, e o ouvidor recebe um caso "respondido" sem conteúdo."""

    def test_resposta_curta_e_recusada_com_o_minimo_na_mensagem(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Dezenove caracteres: um a menos que o mínimo, e o setor precisa ler
        quanto falta, não um "inválido" seco."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "Ja foi resolvido ok"})

        assert resposta.status_code == 422
        assert "20 caracteres" in resposta.json()["detail"]
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["resposta_da_area"] is None
        assert caso["respondida_em"] is None

    def test_recusa_da_resposta_curta_nao_queima_o_link(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A recusa é do texto, não do link: o titular escreve mais e envia de
        novo pelo mesmo email."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "Resolvido"})

        assert client.get(f"/api/ouvidoria-setor/{token}").status_code == 200
        segunda = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert segunda.status_code == 200, segunda.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

    def test_resposta_no_minimo_exato_segue_o_fluxo_normal(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Vinte caracteres cravados entram: a fronteira é "a partir de", e o
        caso vira respondido com o texto na trilha que o ouvidor lê."""
        no_limite = "Trocamos a escala!!!"
        assert len(no_limite) == 20, "a fronteira do teste tem que ser o mínimo exato"
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": no_limite})

        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "respondido"
        assert caso["resposta_da_area"] == no_limite
        assert sb.tabelas["ouvidoria_movimentos"][-1]["estado_novo"] == "respondido"

        # E chega à Ouvidoria: é no Dossiê que o ouvidor lê a resposta da área.
        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-7")
        assert dossie.status_code == 200
        assert dossie.json()["resposta_da_area"] == no_limite

    def test_espaco_nao_conta_para_o_minimo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Vinte caracteres de espaço em volta de uma palavra continuam sendo
        uma palavra: quem conta é o texto, já aparado."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": "   Resolvido        "})

        assert resposta.status_code == 422
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"


class TestTetoDaResposta:
    """Issue #482, rodada de review: o campo tinha piso e não tinha teto. As
    duas colunas que recebem o texto são TEXT sem limite, e `ouvidoria_movimentos`
    é trilha imutável: um envio enorme entraria lá para sempre e deixaria o
    Dossiê daquele caso impossível de abrir."""

    def test_resposta_acima_do_teto_e_recusada_e_nada_e_gravado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Todas as outras portas abertas de propósito: token válido e virgem,
        caso aguardando a área, sem anexo. Só o tamanho recusa, e a recusa não
        deixa rastro nenhum, nem no caso nem na trilha."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        movimentos_antes = len(sb.tabelas["ouvidoria_movimentos"])
        # O número entra literal de propósito: escrito como
        # `MAXIMO_DE_CARACTERES + 1`, o teste acompanharia qualquer mudança da
        # constante e nunca a pegaria. Ele vem do precedente do projeto, o
        # relato do canal público.
        gigante = "a" * 10_001

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": gigante})

        assert resposta.status_code == 422
        assert "10.000 caracteres" in resposta.json()["detail"]
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["resposta_da_area"] is None
        assert caso["respondida_em"] is None
        assert len(sb.tabelas["ouvidoria_movimentos"]) == movimentos_antes
        assert not any("aaaa" in str(m.get("observacao") or "") for m in sb.tabelas["ouvidoria_movimentos"])
        # E o link segue valendo: a recusa é do tamanho, não do token.
        assert client.get(f"/api/ouvidoria-setor/{token}").status_code == 200

    def test_resposta_no_teto_exato_entra(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A fronteira é "até o teto", não "abaixo dele"."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        no_teto = "b" * 10_000

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": no_teto})

        assert resposta.status_code == 200, resposta.text
        assert sb.tabelas["ouvidoria_protocolos"][0]["resposta_da_area"] == no_teto

    def test_quebra_de_linha_chega_como_crlf_e_conta_dois(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O navegador serializa toda quebra de linha do campo como CRLF no
        multipart, o parser entrega esse CRLF inteiro e o teto mede o que
        chegou. Logo, cada quebra custa DOIS caracteres do teto, não um.

        Esta resposta tem 10.000 caracteres na memória do navegador e 10.001 no
        fio, por causa de uma única quebra. A tela conta a mesma coisa que este
        teste manda (issue #512): sem isso, o responsável escrevia em parágrafos,
        o contador dizia que havia folga, o botão liberava e ele perdia o texto
        para um 422."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        na_fronteira = "c" * 5_000 + "\r\n" + "c" * 4_999

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": na_fronteira})

        assert len(na_fronteira) == 10_001, "a fixture tem que estar um caractere acima do teto"
        assert resposta.status_code == 422
        assert "10.000 caracteres" in resposta.json()["detail"]
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"

    def test_invisivel_conta_para_o_teto_mesmo_sem_contar_para_o_piso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """As duas medidas são de propósito diferentes, e a tela espelha as duas
        (issue #512): o piso mede o texto normalizado, que é o que o ouvidor lê,
        e o teto mede o texto como chegou, que é o que trafega e o que precisa
        caber na trilha imutável.

        Este texto cabe no teto depois de normalizado e passa dele como chegou.
        Medir o teto aqui depois de descartar os invisíveis aceitaria no
        servidor o que o botão da tela barra, e a divergência de contagem que a
        #512 fechou voltaria pelo outro lado."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        no_teto_mais_invisivel = "c" * 10_000 + "​"

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": no_teto_mais_invisivel})

        assert resposta.status_code == 422
        assert "10.000 caracteres" in resposta.json()["detail"]
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"
        assert sb.tabelas["ouvidoria_protocolos"][0]["resposta_da_area"] is None


class TestTextoInvisivelNaResposta:
    """O piso conta caracteres, e caractere de largura zero é caractere: sem
    normalizar, vinte deles viram uma resposta que o ouvidor abre em branco."""

    def test_largura_zero_nao_conta_para_o_minimo(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        invisivel = "\u200b" * 25

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": invisivel})

        assert resposta.status_code == 422
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"

    def test_travessao_da_area_e_sanitizado_antes_de_gravar(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Mesmo tratamento da justificativa da prorrogação (ADR 0013): o texto
        da área vira Dossiê e trilha, que o diretor lê."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        enviado = "Falamos com a equipe \u2014 e trocamos a escala do plantao."
        assert client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": enviado}).status_code == 200

        gravado = sb.tabelas["ouvidoria_protocolos"][0]["resposta_da_area"]
        assert "\u2014" not in gravado
        assert gravado == "Falamos com a equipe, e trocamos a escala do plantao."
        assert "\u2014" not in str(sb.tabelas["ouvidoria_movimentos"][-1]["observacao"])


class TestFalhaNoMeioDaResposta:
    """A resposta são duas escritas sem transação entre elas. Quando a segunda
    recusa, nada pode ficar pela metade: nem caso "respondido" sem resposta,
    nem link queimado."""

    def test_transicao_recusada_nao_deixa_t2_gravado_nem_queima_o_link(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        # A Ouvidoria movimentou o caso no mesmo instante: o banco recusa a
        # transição com check_violation, como a RPC da migration 064 faz.
        sb.rpc_recusa = APIError({"code": "23514", "message": "Transicao invalida"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert resposta.status_code == 409

        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["resposta_da_area"] is None
        assert caso["respondida_em"] is None
        assert sb.tabelas["ouvidoria_movimentos"][-1]["estado_novo"] != "respondido"

        # O link volta a valer, e a tentativa seguinte entra normalmente.
        assert client.get(f"/api/ouvidoria-setor/{token}").status_code == 200
        segunda = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert segunda.status_code == 200
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"


class TestReenvioDoAcionamento:
    """O link do email já entregue não pode morrer porque o despacho tentou de
    novo: o titular tem aquele link na caixa de entrada."""

    def test_token_novo_nao_invalida_o_link_ja_entregue(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        primeiro = _token_do_email(_nunca_envia_email_de_verdade)

        # Segunda emissão para o mesmo titular do mesmo caso (o que o retry do
        # despacho e o botão de reenvio fazem).
        segundo = ouvidoria_setor_tokens.emitir(
            sb,
            manifestacao_id="uuid-7",
            destinatario_nome="Carlos Titular",
            destinatario_email="carlos@hsm.br",
        )
        assert segundo != primeiro
        assert len(sb.tabelas["ouvidoria_setor_tokens"]) == 2

        # O link antigo continua abrindo o caso.
        assert client.get(f"/api/ouvidoria-setor/{primeiro}").status_code == 200
        assert client.get(f"/api/ouvidoria-setor/{segundo}").status_code == 200

        # E quem responder primeiro fecha a porta para o outro, sem duplicar.
        assert (
            client.post(f"/api/ouvidoria-setor/{primeiro}/responder", data={"resposta": RESPOSTA_DA_AREA}).status_code
            == 200
        )
        recusada = client.post(
            f"/api/ouvidoria-setor/{segundo}/responder",
            data={"resposta": "Reforcamos tambem a orientacao da equipe da recepcao."},
        )
        assert recusada.status_code == 410
        respondidos = [m for m in sb.tabelas["ouvidoria_movimentos"] if m["estado_novo"] == "respondido"]
        assert len(respondidos) == 1


class TestAnexosDoSetor:
    """Critério 4: anexo do setor fica no caso, nas mesmas regras de tipo e
    tamanho do registro manual (issue #321)."""

    def test_anexo_da_resposta_fica_no_caso_em_nome_do_titular(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(
            f"/api/ouvidoria-setor/{token}/responder",
            data={"resposta": RESPOSTA_DA_AREA},
            files=[("arquivos", ("evidencia.pdf", b"%PDF-1.4 conteudo", "application/pdf"))],
        )
        assert resposta.status_code == 200, resposta.text

        anexos = sb.tabelas["ouvidoria_anexos"]
        assert len(anexos) == 1
        assert anexos[0]["manifestacao_id"] == "uuid-7"
        assert anexos[0]["filename"] == "evidencia.pdf"
        assert anexos[0]["content_type"] == "application/pdf"
        assert anexos[0]["enviado_por"] is None
        assert anexos[0]["enviado_por_nome"] == "Carlos Titular"
        # O binário está no bucket, no caminho que o metadado aponta.
        assert sb.storage.arquivos[anexos[0]["storage_path"]] == b"%PDF-1.4 conteudo"

    def test_tipo_proibido_e_415_sem_queimar_o_link(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.post(
            f"/api/ouvidoria-setor/{token}/responder",
            data={"resposta": RESPOSTA_DA_AREA},
            files=[("arquivos", ("virus.exe", b"MZ", "application/octet-stream"))],
        )
        assert resposta.status_code == 415
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"
        assert sb.tabelas["ouvidoria_anexos"] == []
        assert client.get(f"/api/ouvidoria-setor/{token}").status_code == 200

    def test_anexo_grande_demais_e_413(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        gigante = b"x" * (20 * 1024 * 1024 + 1)
        resposta = client.post(
            f"/api/ouvidoria-setor/{token}/responder",
            data={"resposta": RESPOSTA_DA_AREA},
            files=[("arquivos", ("foto.png", gigante, "image/png"))],
        )
        assert resposta.status_code == 413
        assert sb.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"
        assert sb.tabelas["ouvidoria_anexos"] == []


class TestEncerramentoDoOuvidor:
    """Critério 5: encerrar exige desfecho + descrição e grava o marco T3."""

    def _responder(self, client, enviados) -> None:
        _acionar(client)
        token = _token_do_email(enviados)
        enviada = client.post(f"/api/ouvidoria-setor/{token}/responder", data={"resposta": RESPOSTA_DA_AREA})
        assert enviada.status_code == 200

    def test_ouvidor_encerra_com_desfecho_e_o_caso_grava_t3(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        self._responder(client, _nunca_envia_email_de_verdade)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={
                "estado": "encerrado",
                "desfecho": "procedente",
                "desfecho_descricao": "A area corrigiu o protocolo e o manifestante foi informado.",
            },
        )
        assert resposta.status_code == 200, resposta.text
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "encerrado"
        assert caso["desfecho"] == "procedente"
        assert caso["encerrada_em"] == DENTRO_DO_EXPEDIENTE.isoformat()

    def test_encerrar_sem_descricao_e_bloqueado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        self._responder(client, _nunca_envia_email_de_verdade)

        resposta = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "encerrado", "desfecho": "procedente", "desfecho_descricao": "   "},
        )
        assert resposta.status_code == 422
        caso = sb.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "respondido"
        assert caso["encerrada_em"] is None


class TestPortalDoSetorNaoFicaGuardado:
    """O portal sai com `Cache-Control: no-store` (issue #344, item de peças
    globais da #439). Até aqui ele estava coberto só por herança de nome:
    "/api/ouvidoria-setor" começa com "/api/ouvidoria", e nenhum teste abria o
    portal para conferir o cabeçalho. A página que o titular abre pelo link do
    email carrega protocolo, setor, extrato e a identificação de quem
    manifestou, e atravessa rede que não é nossa."""

    def test_a_pagina_do_link_do_email_sai_sem_cache(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")

        assert resposta.status_code == 200, resposta.text
        assert resposta.headers.get("cache-control") == "no-store"
        # A resposta precisa mesmo carregar o dossiê, senão o teste passaria
        # num corpo vazio sem provar nada sobre o que está sendo protegido.
        assert resposta.json()["protocolo"] == "2026-0007"
        assert resposta.json()["identificacao"] == "Joana da Silva"

    def test_a_recusa_do_link_invalido_tambem_sai_sem_cache(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O 404 do token inválido é resposta como outra qualquer: guardada no
        caminho, ela prenderia fora o titular que abre o link de novo depois de
        o reenvio chegar."""
        client, _ = _client(monkeypatch)

        resposta = client.get("/api/ouvidoria-setor/um-token-que-nao-existe")

        assert resposta.status_code == 404
        assert resposta.headers.get("cache-control") == "no-store"

    def test_o_410_do_link_expirado_tambem_sai_sem_cache(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Dos três status que o portal devolve, o 410 é o que mais precisa do
        carimbo: a RFC 9111 o lista como heuristicamente cacheável (o 500 não
        está lá), e a frase dele conta o andamento do caso a quem só tem o
        link. Guardado num cache compartilhado, ele viraria oráculo de estado."""
        client, sb = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        sb.tabelas["ouvidoria_setor_tokens"][0]["expira_em"] = "2026-08-01T00:00:00+00:00"

        resposta = client.get(f"/api/ouvidoria-setor/{token}")

        assert resposta.status_code == 410, resposta.text
        assert resposta.headers.get("cache-control") == "no-store"
        # O que estaria sendo guardado: a frase que conta o andamento.
        assert "expirou" in resposta.json()["detail"]


class TestOsTresBlocosNaRotaDoToken:
    """Issue #481 (ADR 0041, RN-78): a rota do token devolve RESUMO, RELATO
    INTEGRAL e NOTA DA OUVIDORIA, na mesma ordem e separação do email."""

    def test_payload_traz_os_tres_blocos_na_ordem(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        corpo = client.get(f"/api/ouvidoria-setor/{token}").json()

        assert [b["chave"] for b in corpo["blocos"]] == ["resumo", "relato_integral", "nota_da_ouvidoria"]
        assert [b["texto"] for b in corpo["blocos"]] == [RESUMO, RELATO, EXTRATO]

    def test_caso_sigiloso_vem_sem_relato_e_com_o_extrato_no_lugar(self, monkeypatch, _nunca_envia_email_de_verdade):
        """RN-79 na rota: o relato do manifestante não sai, e o que a área lê no
        lugar dele é o extrato preparado pela Ouvidoria."""
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7, sigilo_reforcado=True)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        corpo = resposta.json()

        assert [b["chave"] for b in corpo["blocos"]] == ["nota_da_ouvidoria"]
        assert corpo["blocos"][-1]["texto"] == EXTRATO
        # A resposta INTEIRA, e não só os blocos: `_CAMPOS_DO_PORTAL` carrega
        # resumo e relato no dict do caso, então basta alguém pendurar mais uma
        # chave no payload para a palavra crua sair por aqui.
        assert RELATO not in resposta.text
        assert RESUMO not in resposta.text
        # As outras portas seguem abertas: o teste mede o sigilo, não uma
        # resposta que esvaziou.
        assert corpo["identificacao"] is None
        assert corpo["aceita_resposta"] is True


class TestOsTresBlocosNoEmailDeAcionamento:
    """Critério 1 pelo fluxo real: o email que sai do acionamento carrega os
    três blocos, com os campos que a leitura do caso pediu ao banco."""

    def test_email_do_acionamento_leva_resumo_relato_e_nota(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        _acionar(client)

        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")

        for pedaco in (email["html"], email["texto"]):
            assert pedaco.index(RESUMO) < pedaco.index(RELATO) < pedaco.index(EXTRATO)

    def test_email_do_acionamento_sigiloso_nao_leva_relato_nem_nome(self, monkeypatch, _nunca_envia_email_de_verdade):
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7, sigilo_reforcado=True)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)

        email = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")

        for pedaco in (email["html"], email["texto"]):
            assert RELATO not in pedaco
            assert "Joana da Silva" not in pedaco
            assert EXTRATO in pedaco


class TestReenvioLevaOsMesmosBlocos:
    """Critério 5: o reenvio manda os mesmos três blocos gravados no caso, para
    provar o que a área recebeu."""

    def test_reenvio_repete_os_blocos_do_primeiro_envio(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, sb = _client(monkeypatch)
        _acionar(client)
        primeiro = next(e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br")
        acionamento = ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA
        notificacao = next(n for n in sb.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == acionamento)

        reenvio = client.post(
            f"/api/ouvidoria/manifestacoes/uuid-7/notificacoes/{notificacao['id']}/reenviar",
        )
        assert reenvio.status_code == 201, reenvio.text
        assert reenvio.json()["entregue"] is True

        segundo = [e for e in _nunca_envia_email_de_verdade if e["destinatario"] == "carlos@hsm.br"][-1]
        assert segundo is not primeiro
        for texto in (segundo["texto"],):
            assert texto.index(RESUMO) < texto.index(RELATO) < texto.index(EXTRATO)
        # O link tokenizado é novo a cada envio, então a prova é o conteúdo dos
        # blocos, não o email inteiro.
        for bloco in (RESUMO, RELATO, EXTRATO):
            assert bloco in primeiro["texto"] and bloco in segundo["texto"]


class TestCasoAnonimoNaRotaDoToken:
    """O anônimo recebe a mesma proteção do sigiloso (a identificação viaja
    dentro do próprio texto), e a rota diz por que o caso veio com um bloco só."""

    def test_rota_do_caso_anonimo_traz_so_a_nota_e_o_aviso(self, monkeypatch, _nunca_envia_email_de_verdade):
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7, anonimo=True, manifestante_nome=None)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        resposta = client.get(f"/api/ouvidoria-setor/{token}")
        corpo = resposta.json()

        assert [b["chave"] for b in corpo["blocos"]] == ["nota_da_ouvidoria"]
        assert "anônima" in corpo["aviso"].lower()
        assert RELATO not in resposta.text
        assert RESUMO not in resposta.text
        # As outras portas seguem abertas: o teste mede a proteção, não uma
        # resposta que esvaziou.
        assert corpo["aceita_resposta"] is True
        assert corpo["extrato"] == EXTRATO

    def test_rota_do_caso_comum_nao_inventa_aviso(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _client(monkeypatch)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)

        assert client.get(f"/api/ouvidoria-setor/{token}").json()["aviso"] is None


class TestCasoSemExtratoDizAMesmaCoisaNosDoisLugares:
    """A montagem única não vale só para o texto do ouvidor: o caso que chegou
    ao acionamento SEM extrato tem um fallback só. Dois textos diferentes para o
    mesmo conteúdo, na mesma resposta, é a divergência que o critério 4 mata."""

    def test_payload_sem_extrato_repete_a_mesma_frase_no_campo_e_no_bloco(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        sb = _SupabaseFake(manifestacoes=[_manifestacao(7)])
        client, _ = _client(monkeypatch, supabase=sb)
        _acionar(client)
        token = _token_do_email(_nunca_envia_email_de_verdade)
        # O extrato some do caso DEPOIS do acionamento (o painel o apaga, uma
        # migration o zera): é assim que a página encontra o caso sem ele.
        sb.tabelas["ouvidoria_protocolos"][0]["extrato_para_o_setor"] = ""

        corpo = client.get(f"/api/ouvidoria-setor/{token}").json()

        nota = next(b for b in corpo["blocos"] if b["chave"] == "nota_da_ouvidoria")
        assert corpo["extrato"] == nota["texto"]
        assert "não registrou o extrato" in corpo["extrato"]
