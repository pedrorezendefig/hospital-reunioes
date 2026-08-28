"""Aceite interno ponta-a-ponta com desfecho terminal (issue #277, ADR 0030).

Seams testados:
- POST /api/webhooks/clicksign: ao abrir o modo interno, cada signatario
  pendente COM acoes recebe email com link publico tokenizado (token opaco,
  uso unico); signatario sem acao nao recebe link; Facilitador pendente
  recebe tambem notificacao in-app apontando para o aceite.
- GET /api/aceite/{token}: pagina publica ve a ata completa.
- POST /api/aceite/{token}/aceitar: cria todas as Pendencias do signatario e
  registra o aceite com origem `aceite_interno` e timestamp. Token reusado,
  expirado ou invalido falha sem nenhum efeito.
- Desfecho terminal (regra exclusiva do modo interno): quando toda acao do
  quadro tem Pendencia nascida, a Reuniao vira ASSINADA com `data_assinatura`
  e o selo de assinaturas mistas (contagem persistida).

ClickSign e email SEMPRE mockados (o .env de teste carrega credenciais reais).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
import sys
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.routers import aceite as aceite_router  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import clicksign_service, reuniao_email_service, storage  # noqa: E402

SECRET = "test-secret"
DOC_KEY = "doc-key-r1"

# ─── Mock Supabase (mesmo estilo de test_modo_interno_eventos) ───────────────


class _Result:
    def __init__(self, data: list):
        self.data = data


class _TableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}
        self._is_filters: dict = {}
        self._in_filters: dict = {}
        self._limit: int | None = None
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def is_(self, col, value):
        self._is_filters[col] = None if value in ("null", None) else value
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        if self._insert_payload is not None:
            for row in self._insert_payload:
                row.setdefault("id", f"row-{len(self._rows) + 1}")
                self._rows.append(dict(row))
            return _Result(data=[dict(r) for r in self._insert_payload])

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
            and all(r.get(c) == v for c, v in self._is_filters.items())
        ]
        if getattr(self, "_delete", False):
            for row in filtered:
                self._rows.remove(row)
            return _Result(data=[dict(r) for r in filtered])
        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name])


# ─── Dados ───────────────────────────────────────────────────────────────────


def _participante(pid: str, nome: str, email: str) -> dict:
    return {"id": pid, "nome_completo": nome, "cargo": "Cargo", "setor": "Setor", "email": email, "ativo": True}


def _quadro() -> list[dict]:
    return [
        {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-01"},
        {"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": "2026-09-10"},
        {"acao": "Atualizar POP", "responsavel": "Fabio Facilitador", "responsavel_id": "P_FAC", "prazo": None},
    ]


def _sb(**reuniao_over) -> _SupabaseMock:
    reuniao = {
        "id_reuniao": "R1",
        "titulo": "Comissao de Farmacia",
        "tipo": "Comissao",
        "data": "2026-08-01",
        "hora_inicio": "10:00",
        "objetivo": "Alinhar compras",
        "status_ata": "AGUARDANDO_ASSINATURA",
        "envelope_key_clicksign": DOC_KEY,
        "envelope_id_clicksign": "env-r1",
        "facilitador_id": "P_FAC",
        "modo_interno_desde": None,
        "data_assinatura": None,
        "url_pdf_assinado": None,
        "json_ata": {"objetivo": "Alinhar compras", "quadro_atribuicoes": _quadro()},
    }
    reuniao.update(reuniao_over)
    return _SupabaseMock(
        {
            "reunioes": [reuniao],
            "pops_versoes": [],
            "participantes": [
                _participante("P_FAC", "Fabio Facilitador", "fabio@hsm.com"),
                _participante("P_ANA", "Ana Lima", "ana@hsm.com"),
                _participante("P_BRUNO", "Bruno Costa", "bruno@hsm.com"),
                _participante("P_SEM", "Sonia Sem Acao", "sonia@hsm.com"),
            ],
            "reuniao_participantes": [
                {"id_reuniao": "R1", "participante_id": "P_FAC"},
                {"id_reuniao": "R1", "participante_id": "P_ANA"},
                {"id_reuniao": "R1", "participante_id": "P_BRUNO"},
                {"id_reuniao": "R1", "participante_id": "P_SEM"},
            ],
            "pendencias": [],
            "reuniao_aceites": [],
            "reuniao_aceite_tokens": [],
            "notificacoes": [],
        }
    )


def _aceite_clicksign(pid: str, signer_key: str, email: str) -> dict:
    return {
        "id": f"aceite-{pid}",
        "id_reuniao": "R1",
        "participante_id": pid,
        "signer_key": signer_key,
        "email": email,
        "origem": "clicksign",
        "aceito_em": "2026-08-10T10:00:00-03:00",
    }


def _pendencia_nascida(id_acao: str, quadro_pos: int, responsavel_id: str) -> dict:
    return {
        "id_acao": id_acao,
        "id_reuniao": "R1",
        "status": "PENDENTE",
        "responsavel_id": responsavel_id,
        "quadro_pos": quadro_pos,
    }


# ─── App e helpers ───────────────────────────────────────────────────────────


def _client(sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhooks_router.router, prefix="/api")
    app.include_router(aceite_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app, raise_server_exceptions=False)


def _post_webhook(client: TestClient, payload: dict) -> Any:
    body = json.dumps(payload).encode("utf-8")
    assinatura = hmac_lib.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/clicksign",
        content=body,
        headers={"Content-Hmac": f"sha256={assinatura}", "Content-Type": "application/json"},
    )


def _evento_refusal() -> dict:
    return {
        "event": {
            "name": "refusal",
            "data": {"signer": {"key": "sk-ana", "email": "ana@hsm.com", "name": "Ana Lima"}},
            "occurred_at": "2026-08-14T12:00:00.000-03:00",
        },
        "document": {"key": DOC_KEY},
    }


def _reuniao(sb: _SupabaseMock) -> dict:
    return sb.tables["reunioes"][0]


def _token_do_link(link: str) -> str:
    return link.rstrip("/").split("/")[-1]


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SECRET)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from app.limiter import limiter

    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _bloquear_httpx(monkeypatch):
    import httpx

    def _explode(*_a, **_kw):
        raise AssertionError("Chamada httpx real bloqueada nos testes")

    monkeypatch.setattr(httpx, "Client", _explode)


@pytest.fixture(autouse=True)
def _clicksign_e_storage_mockados(monkeypatch):
    monkeypatch.setattr(clicksign_service, "get_signed_document", lambda _env: b"%PDF-signed")
    monkeypatch.setattr(storage, "upload_file", lambda *_a, **_kw: "http://storage/pdfs/ata_assinada.pdf")
    monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: None)


@pytest.fixture
def emails(monkeypatch) -> list[dict]:
    """Captura os emails enviados (email SEMPRE mockado)."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html, texto):
        enviados.append({"para": destinatario, "assunto": assunto, "html": html, "texto": texto})
        return True

    monkeypatch.setattr(reuniao_email_service, "_enviar_email", _fake)
    return enviados


def _abrir_modo_interno(sb: _SupabaseMock, client: TestClient) -> None:
    res = _post_webhook(client, _evento_refusal())
    assert res.status_code == 200
    assert _reuniao(sb)["modo_interno_desde"]


# ═══════════════════════════════════════════════════════════════════════════
# CA1: abertura do modo interno dispara os links de Aceite interno
# ═══════════════════════════════════════════════════════════════════════════


class TestAberturaDisparaLinks:
    def test_signatario_pendente_com_acoes_recebe_email_com_link_tokenizado(self, emails):
        """Ana ja assinou (aceite clicksign, Pendencia dela nascida); Bruno e
        Fabio estao pendentes com acoes; Sonia esta pendente sem acao."""
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))

        _abrir_modo_interno(sb, _client(sb))

        destinos = sorted(e["para"] for e in emails)
        assert destinos == ["bruno@hsm.com", "fabio@hsm.com"]
        for e in emails:
            assert f"{settings.frontend_url}/aceite/" in e["texto"]

    def test_link_carrega_token_opaco_persistido_como_hash(self, emails):
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))

        _abrir_modo_interno(sb, _client(sb))

        tokens = sb.tables["reuniao_aceite_tokens"]
        assert {t["participante_id"] for t in tokens} == {"P_BRUNO", "P_FAC"}
        for e in emails:
            token = _token_do_link(e["texto"].split(f"{settings.frontend_url}/aceite/")[1].split()[0])
            # token opaco NUNCA persistido em claro: so o hash vive no banco
            assert all(t.get("token_hash") != token for t in tokens)
            h = hashlib.sha256(token.encode("utf-8")).hexdigest()
            assert any(t.get("token_hash") == h for t in tokens)

    def test_facilitador_pendente_recebe_notificacao_in_app(self, emails):
        sb = _sb()
        _abrir_modo_interno(sb, _client(sb))

        notifs = sb.tables["notificacoes"]
        assert len(notifs) == 1
        assert notifs[0]["destinatario_id"] == "P_FAC"
        assert notifs[0]["tipo"] == "ACEITE_INTERNO"
        # A referencia aponta para a REUNIAO, nao para o token (issue #295).
        assert notifs[0]["referencia_id"] == "R1"

    def test_notificacao_nao_carrega_o_token_em_claro(self, emails):
        """O invariante hash-only da issue #295: nenhum token emitido nesta
        coleta pode ser recuperado a partir do que a notificacao guarda.

        A checagem e por hash, nao por igualdade de string: se a referencia
        virasse o token de novo, o SHA-256 dela casaria com uma linha de
        `reuniao_aceite_tokens` e este teste ficaria vermelho."""
        sb = _sb()
        _abrir_modo_interno(sb, _client(sb))

        tokens = sb.tables["reuniao_aceite_tokens"]
        assert tokens, "sem token emitido o teste nao prova nada"
        for notif in sb.tables["notificacoes"]:
            referencia = str(notif.get("referencia_id") or "")
            h = hashlib.sha256(referencia.encode("utf-8")).hexdigest()
            assert all(t.get("token_hash") != h for t in tokens), (
                "a notificacao guarda o token em claro: o hash da referencia casou com um token vivo"
            )

    def test_evento_duplicado_nao_reenvia_emails(self, emails):
        sb = _sb()
        client = _client(sb)
        _abrir_modo_interno(sb, client)
        enviados_antes = len(emails)

        res = _post_webhook(client, _evento_refusal())
        assert res.status_code == 200
        assert len(emails) == enviados_antes

    def test_falha_no_envio_de_email_nao_quebra_o_webhook(self, monkeypatch):
        def _explode(*_a, **_kw):
            raise RuntimeError("provider fora do ar")

        monkeypatch.setattr(reuniao_email_service, "_enviar_email", _explode)
        sb = _sb()
        res = _post_webhook(_client(sb), _evento_refusal())

        assert res.status_code == 200
        assert _reuniao(sb)["modo_interno_desde"]


# ═══════════════════════════════════════════════════════════════════════════
# CA2: pagina publica mostra a ata completa e o aceite cria as Pendencias
# ═══════════════════════════════════════════════════════════════════════════


def _fluxo_com_link_do_bruno(sb: _SupabaseMock, emails: list[dict]) -> tuple[TestClient, str]:
    client = _client(sb)
    _abrir_modo_interno(sb, client)
    email_bruno = next(e for e in emails if e["para"] == "bruno@hsm.com")
    link = email_bruno["texto"].split(f"{settings.frontend_url}/aceite/")[1].split()[0]
    return client, _token_do_link(f"{settings.frontend_url}/aceite/{link}")


class TestPaginaPublicaEAceite:
    def test_get_token_valido_mostra_ata_completa(self, emails):
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client, token = _fluxo_com_link_do_bruno(sb, emails)

        res = client.get(f"/api/aceite/{token}")

        assert res.status_code == 200
        body = res.json()
        assert body["reuniao"]["titulo"] == "Comissao de Farmacia"
        assert body["signatario"]["nome"] == "Bruno Costa"
        assert body["ata"]["quadro_atribuicoes"] == _quadro()

    def test_aceite_cria_pendencias_do_signatario_com_origem_e_timestamp(self, emails):
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client, token = _fluxo_com_link_do_bruno(sb, emails)

        res = client.post(f"/api/aceite/{token}/aceitar")

        assert res.status_code == 200
        assert res.json()["pendencias_criadas"] == 1
        pendencias_bruno = [p for p in sb.tables["pendencias"] if p.get("responsavel_id") == "P_BRUNO"]
        assert len(pendencias_bruno) == 1
        assert pendencias_bruno[0]["quadro_pos"] == 1

        aceites = [a for a in sb.tables["reuniao_aceites"] if a.get("origem") == "aceite_interno"]
        assert len(aceites) == 1
        assert aceites[0]["participante_id"] == "P_BRUNO"
        assert aceites[0]["aceito_em"]

    def test_aceite_parcial_mantem_reuniao_aguardando_assinatura(self, emails):
        """Falta a acao do Fabio: o aceite do Bruno nao fecha a Reuniao."""
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client, token = _fluxo_com_link_do_bruno(sb, emails)

        res = client.post(f"/api/aceite/{token}/aceitar")

        assert res.status_code == 200
        assert res.json()["reuniao_assinada"] is False
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"


# ═══════════════════════════════════════════════════════════════════════════
# CA3: token reusado, expirado ou invalido falha sem nenhum efeito
# ═══════════════════════════════════════════════════════════════════════════


class TestTokenSemEfeito:
    def test_token_invalido_falha_404(self, emails):
        sb = _sb()
        client = _client(sb)
        _abrir_modo_interno(sb, client)
        antes = [dict(p) for p in sb.tables["pendencias"]]

        assert client.get("/api/aceite/nao-existe").status_code == 404
        assert client.post("/api/aceite/nao-existe/aceitar").status_code == 404
        assert sb.tables["pendencias"] == antes
        assert [a for a in sb.tables["reuniao_aceites"] if a["origem"] == "aceite_interno"] == []

    def test_token_reusado_falha_410_sem_novo_efeito(self, emails):
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client, token = _fluxo_com_link_do_bruno(sb, emails)

        assert client.post(f"/api/aceite/{token}/aceitar").status_code == 200
        pendencias_depois = [dict(p) for p in sb.tables["pendencias"]]
        aceites_depois = [dict(a) for a in sb.tables["reuniao_aceites"]]

        res = client.post(f"/api/aceite/{token}/aceitar")

        assert res.status_code == 410
        assert sb.tables["pendencias"] == pendencias_depois
        assert sb.tables["reuniao_aceites"] == aceites_depois

    def test_token_de_reuniao_ja_assinada_expira_410_sem_efeito(self, emails):
        sb = _sb()
        client, token = _fluxo_com_link_do_bruno(sb, emails)
        _reuniao(sb)["status_ata"] = "ASSINADA"
        antes = [dict(p) for p in sb.tables["pendencias"]]

        assert client.get(f"/api/aceite/{token}").status_code == 410
        res = client.post(f"/api/aceite/{token}/aceitar")

        assert res.status_code == 410
        assert sb.tables["pendencias"] == antes
        assert [a for a in sb.tables["reuniao_aceites"] if a["origem"] == "aceite_interno"] == []


# ═══════════════════════════════════════════════════════════════════════════
# CA5: desfecho terminal do modo interno (toda acao com Pendencia = ASSINADA)
# ═══════════════════════════════════════════════════════════════════════════


class TestDesfechoTerminal:
    def test_ultimo_aceite_necessario_leva_a_assinada_com_selo_misto(self, emails):
        """Ana assinou (clicksign); Bruno e Fabio dao o Aceite interno. O
        ultimo aceite fecha: ASSINADA + data_assinatura + contagem persistida
        (selo de assinaturas mistas: 1 de 4 assinaram no ClickSign)."""
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client = _client(sb)
        _abrir_modo_interno(sb, client)

        tokens = {}
        for e in emails:
            link = e["texto"].split(f"{settings.frontend_url}/aceite/")[1].split()[0]
            tokens[e["para"]] = _token_do_link(link)

        res_bruno = client.post(f"/api/aceite/{tokens['bruno@hsm.com']}/aceitar")
        assert res_bruno.json()["reuniao_assinada"] is False

        res_fabio = client.post(f"/api/aceite/{tokens['fabio@hsm.com']}/aceitar")

        assert res_fabio.status_code == 200
        assert res_fabio.json()["reuniao_assinada"] is True
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "ASSINADA"
        assert reuniao["data_assinatura"]
        assert reuniao["signatarios_total"] == 4
        assert reuniao["signatarios_assinaram"] == 1

    def test_aceite_do_facilitador_libera_acoes_sem_vinculo_e_de_nao_signatarios(self, emails):
        """Espelho da regra do ClickSign (ADR 0030, decisão 1): o aceite do
        Facilitador libera também as ações sem vínculo (responsável não
        resolvido), senão o desfecho terminal nunca chega."""
        quadro = [
            {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": None},
            {"acao": "Contratar externo", "responsavel": "Pessoa Externa", "prazo": None},
            {"acao": "Atualizar POP", "responsavel": "Fabio Facilitador", "responsavel_id": "P_FAC", "prazo": None},
        ]
        sb = _sb(json_ata={"quadro_atribuicoes": quadro})
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client = _client(sb)
        _abrir_modo_interno(sb, client)

        email_fabio = next(e for e in emails if e["para"] == "fabio@hsm.com")
        token = _token_do_link(email_fabio["texto"].split(f"{settings.frontend_url}/aceite/")[1].split()[0])

        res = client.post(f"/api/aceite/{token}/aceitar")

        assert res.status_code == 200
        assert res.json()["pendencias_criadas"] == 2  # a dele + a sem vínculo
        assert res.json()["reuniao_assinada"] is True
        assert _reuniao(sb)["status_ata"] == "ASSINADA"

    def test_facilitador_pendente_recebe_link_quando_so_ha_acao_sem_vinculo(self, emails):
        """Facilitador sem ação própria mas com ação sem vínculo aberta no
        quadro precisa do link: só o aceite dele consegue liberá-la."""
        quadro = [{"acao": "Contratar externo", "responsavel": "Pessoa Externa", "prazo": None}]
        sb = _sb(json_ata={"quadro_atribuicoes": quadro})
        _abrir_modo_interno(sb, _client(sb))

        assert [e["para"] for e in emails] == ["fabio@hsm.com"]
        assert {t["participante_id"] for t in sb.tables["reuniao_aceite_tokens"]} == {"P_FAC"}

    def test_sign_atrasado_no_modo_interno_completa_o_desfecho(self, emails):
        """Um `sign` que chega depois do modo interno aberto ainda conta: se
        era a última ação sem Pendência, a Reunião fecha (desfecho terminal)."""
        sb = _sb(modo_interno_desde="2026-08-14T12:00:00+00:00")
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 1, "P_BRUNO"))
        sb.tables["pendencias"].append(_pendencia_nascida("A002", 2, "P_FAC"))
        sb.tables["reuniao_aceites"].append(
            {"id": "ac-b", "id_reuniao": "R1", "participante_id": "P_BRUNO", "origem": "aceite_interno"}
        )
        sb.tables["reuniao_aceites"].append(
            {"id": "ac-f", "id_reuniao": "R1", "participante_id": "P_FAC", "origem": "aceite_interno"}
        )
        payload = {
            "event": {
                "name": "sign",
                "data": {"signer": {"key": "sk-ana", "email": "ana@hsm.com"}},
                "occurred_at": "2026-08-14T13:00:00.000-03:00",
            },
            "document": {"key": DOC_KEY},
        }

        res = _post_webhook(_client(sb), payload)

        assert res.status_code == 200
        assert any(p.get("responsavel_id") == "P_ANA" for p in sb.tables["pendencias"])
        assert _reuniao(sb)["status_ata"] == "ASSINADA"

    def test_responsavel_reatribuido_com_aceite_previo_nasce_na_recoleta(self, emails):
        """Ação reatribuída para quem JÁ firmou compromisso: a recoleta libera
        direto, sem novo token nem email (o aceite dele já vale)."""
        from app.services import aceite_service

        quadro = [{"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": None}]
        sb = _sb(
            json_ata={"quadro_atribuicoes": quadro},
            modo_interno_desde="2026-08-14T12:00:00+00:00",
        )
        sb.tables["reuniao_aceites"].append(
            {"id": "ac-b", "id_reuniao": "R1", "participante_id": "P_BRUNO", "origem": "aceite_interno"}
        )

        resultado = aceite_service.iniciar_coleta_interna(sb, "R1")

        assert emails == []
        assert sb.tables["reuniao_aceite_tokens"] == []
        assert any(p.get("responsavel_id") == "P_BRUNO" for p in sb.tables["pendencias"])
        assert resultado["desfecho_terminal"] is True
        assert _reuniao(sb)["status_ata"] == "ASSINADA"

    def test_selo_ignora_aceite_clicksign_sem_correlacao(self, emails):
        """Aceite clicksign sem Participante correlacionado nao infla o
        contador do selo: assinaram conta so signatarios do roster."""
        sb = _sb()
        sb.tables["reuniao_aceites"].append(_aceite_clicksign("P_ANA", "sk-ana", "ana@hsm.com"))
        sb.tables["reuniao_aceites"].append(
            {
                "id": "ac-x",
                "id_reuniao": "R1",
                "participante_id": None,
                "signer_key": "sk-ghost",
                "email": "ghost@x.com",
                "origem": "clicksign",
            }  # noqa: E501
        )
        sb.tables["pendencias"].append(_pendencia_nascida("A001", 0, "P_ANA"))
        client = _client(sb)
        _abrir_modo_interno(sb, client)

        tokens = {}
        for e in emails:
            link = e["texto"].split(f"{settings.frontend_url}/aceite/")[1].split()[0]
            tokens[e["para"]] = _token_do_link(link)
        client.post(f"/api/aceite/{tokens['bruno@hsm.com']}/aceitar")
        client.post(f"/api/aceite/{tokens['fabio@hsm.com']}/aceitar")

        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "ASSINADA"
        assert reuniao["signatarios_total"] == 4
        assert reuniao["signatarios_assinaram"] == 1

    def test_email_falhado_solta_o_token_para_reemissao(self, monkeypatch):
        """Envio falhou e nenhum canal chegou ao signatario: o token e
        removido para uma recoleta futura reemitir o link."""

        def _explode(*_a, **_kw):
            raise RuntimeError("provider fora do ar")

        monkeypatch.setattr(reuniao_email_service, "_enviar_email", _explode)
        sb = _sb()
        res = _post_webhook(_client(sb), _evento_refusal())

        assert res.status_code == 200
        # Bruno e Ana (nao-facilitadores) perdem o token; o do Facilitador fica
        # porque a notificacao in-app dele ainda aponta pro aceite.
        assert {t["participante_id"] for t in sb.tables["reuniao_aceite_tokens"]} == {"P_FAC"}

    def test_desfecho_imediato_quando_toda_acao_ja_tem_pendencia(self, emails):
        """Envelope morre com todas as acoes ja nascidas (quem tinha acao
        assinou; quem recusou nao tem acao): a Reuniao fecha direto, sem
        emails de Aceite interno."""
        sb = _sb()
        for pid, pos in (("P_ANA", 0), ("P_BRUNO", 1), ("P_FAC", 2)):
            sb.tables["reuniao_aceites"].append(_aceite_clicksign(pid, f"sk-{pid}", f"{pid.lower()}@hsm.com"))
            sb.tables["pendencias"].append(_pendencia_nascida(f"A00{pos + 1}", pos, pid))

        res = _post_webhook(_client(sb), _evento_refusal())

        assert res.status_code == 200
        reuniao = _reuniao(sb)
        assert reuniao["status_ata"] == "ASSINADA"
        assert reuniao["data_assinatura"]
        assert emails == []
