"""Espinha do nascimento incremental (issue #274, ADR 0030).

Seam principal: POST /api/webhooks/clicksign com payloads oficiais da ClickSign
(evento `sign`, snake_case). A assinatura de um signatario cria na hora so as
Pendencias dele, plenas; a assinatura do Facilitador da Reuniao cria tambem as
de responsaveis fora do Envelope. O aceite fica persistido em `reuniao_aceites`
com origem `clicksign` e timestamp. Idempotencia por acao do quadro
(`quadro_pos`) e numeracao `A###` protegida contra webhooks concorrentes.

ClickSign SEMPRE mockado (o .env de teste carrega credenciais reais).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import clicksign_service, pendencia_service, storage  # noqa: E402

SECRET = "test-secret"

# ─── Mock Supabase com unicidade (indices da migration 057) ──────────────────


class _UniqueViolationError(Exception):
    """Simula o erro 23505 do Postgres via PostgREST."""

    def __init__(self, constraint: str):
        super().__init__(f'23505 duplicate key value violates unique constraint "{constraint}"')
        self.code = "23505"


@dataclass
class _Result:
    data: list


def _checar_unicidade(table: str, rows: list[dict], row: dict) -> None:
    if table == "pendencias":
        if any(r.get("id_acao") == row.get("id_acao") for r in rows):
            raise _UniqueViolationError("pendencias_pkey")
        if row.get("quadro_pos") is not None and any(
            r.get("id_reuniao") == row.get("id_reuniao") and r.get("quadro_pos") == row.get("quadro_pos") for r in rows
        ):
            raise _UniqueViolationError("ux_pendencias_reuniao_quadro_pos")
    if table == "reuniao_aceites":
        for col, constraint in (
            ("signer_key", "ux_reuniao_aceites_signer_key"),
            ("email", "ux_reuniao_aceites_email"),
            ("participante_id", "ux_reuniao_aceites_participante"),
        ):
            if row.get(col) is not None and any(
                r.get("id_reuniao") == row.get("id_reuniao") and r.get(col) == row.get(col) for r in rows
            ):
                raise _UniqueViolationError(constraint)


class _TableQuery:
    def __init__(self, sb: _SupabaseMock, table: str):
        self._sb = sb
        self._rows = sb.tables[table]
        self._table = table
        self._filters: dict = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self._order = (col, desc)
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

    def execute(self):
        if self._insert_payload is not None:
            hook = self._sb.antes_do_insert.pop(self._table, None)
            if hook is not None:
                hook()
            inserted = []
            for row in self._insert_payload:
                row = dict(row)
                _checar_unicidade(self._table, self._rows, row)
                row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
                inserted.append(row)
            # Lote atomico: só grava depois de validar todas as linhas
            self._rows.extend(inserted)
            return _Result(data=[dict(r) for r in inserted])

        filtered = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        if self._order is not None:
            col, desc = self._order
            filtered = sorted(filtered, key=lambda r: r.get(col) or "", reverse=desc)
        if self._limit is not None:
            filtered = filtered[: self._limit]
        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        # Hooks de concorrencia: funcao executada uma unica vez logo antes do
        # proximo insert na tabela (simula outra transacao ganhando a corrida).
        self.antes_do_insert: dict[str, Callable[[], None]] = {}

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self, name)


# ─── Dados ───────────────────────────────────────────────────────────────────

DOC_KEY = "doc-key-r1"


def _participante(pid: str, nome: str, email: str) -> dict:
    return {"id": pid, "nome_completo": nome, "email": email, "cargo": "Cargo", "setor": "Setor", "ativo": True}


def _quadro() -> list[dict]:
    return [
        {"acao": "Revisar protocolo", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-01"},
        {"acao": "Comprar insumos", "responsavel": "Bruno Costa", "responsavel_id": "P_BRUNO", "prazo": "10/09/2026"},
        {"acao": "Treinar equipe", "responsavel": "Carla Dias", "responsavel_id": "P_CARLA", "prazo": "2026-09-15"},
        {"acao": "Mapear riscos", "responsavel": "Ze Ninguem", "prazo": None},
        {"acao": "Auditar estoque", "responsavel": "Ana Lima", "responsavel_id": "P_ANA", "prazo": "2026-09-20"},
    ]


def _sb(**reuniao_over) -> _SupabaseMock:
    reuniao = {
        "id_reuniao": "R1",
        "status_ata": "AGUARDANDO_ASSINATURA",
        "envelope_key_clicksign": DOC_KEY,
        "envelope_id_clicksign": "env-r1",
        "facilitador_id": "P_FAC",
        "json_ata": {"quadro_atribuicoes": _quadro()},
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
                _participante("P_CARLA", "Carla Dias", "carla@hsm.com"),
            ],
            # Envelope = roster da Reuniao: Facilitador, Ana e Bruno (Carla fora)
            "reuniao_participantes": [
                {"id_reuniao": "R1", "participante_id": "P_FAC"},
                {"id_reuniao": "R1", "participante_id": "P_ANA"},
                {"id_reuniao": "R1", "participante_id": "P_BRUNO"},
            ],
            "pendencias": [],
            "reuniao_aceites": [],
        }
    )


def _client(sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(webhooks_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app, raise_server_exceptions=False)


def _post(client: TestClient, payload: dict, *, secret: str = SECRET) -> Any:
    body = json.dumps(payload).encode("utf-8")
    assinatura = hmac_lib.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return client.post(
        "/api/webhooks/clicksign",
        content=body,
        headers={"Content-Hmac": f"sha256={assinatura}", "Content-Type": "application/json"},
    )


def _evento_sign(signer_key: str | None, email: str, nome: str = "Signatario") -> dict:
    """Payload oficial do evento `sign` (developers.clicksign.com/docs/evento-sign)."""
    signer: dict = {"email": email, "name": nome, "sign_as": "party"}
    if signer_key is not None:
        signer["key"] = signer_key
    return {
        "event": {
            "name": "sign",
            "data": {"signer": signer},
            "occurred_at": "2026-08-14T10:00:00.000-03:00",
        },
        "document": {"key": DOC_KEY},
    }


def _evento(nome: str) -> dict:
    return {
        "event": {"name": nome, "data": None, "occurred_at": "2026-08-14T12:00:00.000-03:00"},
        "document": {"key": DOC_KEY},
    }


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SECRET)


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


def _pendencias(sb: _SupabaseMock) -> list[dict]:
    return sb.tables["pendencias"]


def _aceites(sb: _SupabaseMock) -> list[dict]:
    return sb.tables["reuniao_aceites"]


# ═══════════════════════════════════════════════════════════════════════════
# CA: sign de um signatario cria na hora so as Pendencias dele, plenas
# ═══════════════════════════════════════════════════════════════════════════


class TestSignIndividual:
    def test_sign_cria_so_as_pendencias_do_signatario(self):
        sb = _sb()
        res = _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com", "Ana Lima"))

        assert res.status_code == 200
        criadas = _pendencias(sb)
        assert len(criadas) == 2  # posicoes 0 e 4 (as duas acoes da Ana)
        assert all(p["responsavel_id"] == "P_ANA" for p in criadas)
        assert sorted(p["quadro_pos"] for p in criadas) == [0, 4]

    def test_pendencia_nasce_plena(self):
        sb = _sb()
        _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com", "Ana Lima"))

        por_pos = {p["quadro_pos"]: p for p in _pendencias(sb)}
        p0 = por_pos[0]
        assert p0["status"] == "PENDENTE"
        assert p0["prazo"] == "2026-09-01"
        assert p0["descricao_acao"] == "Revisar protocolo"
        assert p0["id_acao"].startswith("A")

    def test_reuniao_nao_avanca_de_estado_no_sign(self):
        sb = _sb()
        _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"))
        assert sb.tables["reunioes"][0]["status_ata"] == "AGUARDANDO_ASSINATURA"

    def test_sign_repetido_e_idempotente(self):
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        res = _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert len(_pendencias(sb)) == 2
        assert len(_aceites(sb)) == 1

    def test_sign_sem_correlacao_nao_cria_nada(self):
        sb = _sb()
        res = _post(_client(sb), _evento_sign("sk-x", "desconhecido@fora.com"))

        assert res.status_code == 200
        assert _pendencias(sb) == []
        # aceite persiste mesmo sem Participante correlacionado (auditoria)
        assert len(_aceites(sb)) == 1
        assert _aceites(sb)[0]["participante_id"] is None


# ═══════════════════════════════════════════════════════════════════════════
# CA: aceite persistido com origem clicksign e timestamp
# ═══════════════════════════════════════════════════════════════════════════


class TestRegistroDeAceite:
    def test_aceite_persistido_com_origem_e_timestamp(self):
        sb = _sb()
        _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"))

        assert len(_aceites(sb)) == 1
        aceite = _aceites(sb)[0]
        assert aceite["id_reuniao"] == "R1"
        assert aceite["participante_id"] == "P_ANA"
        assert aceite["signer_key"] == "sk-ana"
        assert aceite["email"] == "ana@hsm.com"
        assert aceite["origem"] == "clicksign"
        assert aceite["aceito_em"]

    def test_correlacao_por_signer_key_vence_email_divergente(self):
        """Mesmo signer_key com email trocado nao duplica o aceite."""
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        _post(client, _evento_sign("sk-ana", "ana.lima@outro.com"))

        assert len(_aceites(sb)) == 1
        assert len(_pendencias(sb)) == 2

    def test_fallback_por_email_normalizado_sem_signer_key(self):
        sb = _sb()
        res = _post(_client(sb), _evento_sign(None, "  BRUNO@hsm.com "))

        assert res.status_code == 200
        criadas = _pendencias(sb)
        assert len(criadas) == 1
        assert criadas[0]["responsavel_id"] == "P_BRUNO"
        assert _aceites(sb)[0]["email"] == "bruno@hsm.com"

    def test_redelivery_recorrelaciona_aceite_sem_participante(self):
        """Aceite gravado sem correlacao (email divergente na epoca) nao
        congela o signatario: apos corrigir o cadastro, o redelivery do sign
        correlaciona, atualiza o aceite e cria as Pendencias."""
        sb = _sb()
        # No primeiro evento, o cadastro da Ana tem email antigo (nao casa)
        for p in sb.tables["participantes"]:
            if p["id"] == "P_ANA":
                p["email"] = "ana@antigo.com"
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        assert _pendencias(sb) == []
        assert _aceites(sb)[0]["participante_id"] is None

        # Cadastro corrigido; ClickSign reenvia o mesmo evento
        for p in sb.tables["participantes"]:
            if p["id"] == "P_ANA":
                p["email"] = "ana@hsm.com"
        res = _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert len(_aceites(sb)) == 1
        assert _aceites(sb)[0]["participante_id"] == "P_ANA"
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 4]


# ═══════════════════════════════════════════════════════════════════════════
# CA: sign do Facilitador cria tambem as Pendencias de fora do Envelope
# ═══════════════════════════════════════════════════════════════════════════


class TestSignDoFacilitador:
    def test_facilitador_libera_fora_do_envelope(self):
        sb = _sb()
        res = _post(_client(sb), _evento_sign("sk-fac", "fabio@hsm.com", "Fabio Facilitador"))

        assert res.status_code == 200
        criadas = _pendencias(sb)
        # Carla (fora do Envelope, pos 2) + acao sem vinculo (pos 3)
        assert sorted(p["quadro_pos"] for p in criadas) == [2, 3]
        assert {p.get("responsavel_id") for p in criadas} == {"P_CARLA", None}

    def test_sign_de_nao_facilitador_nao_libera_fora_do_envelope(self):
        sb = _sb()
        _post(_client(sb), _evento_sign("sk-bruno", "bruno@hsm.com"))

        criadas = _pendencias(sb)
        assert sorted(p["quadro_pos"] for p in criadas) == [1]

    def test_membro_do_roster_sem_email_conta_como_fora_do_envelope(self):
        """add_signer exige email: quem esta no roster sem email nunca assina,
        entao a assinatura do Facilitador libera as Pendencias dele tambem."""
        sb = _sb()
        davi = {"id": "P_DAVI", "nome_completo": "Davi Externo", "email": None, "cargo": None, "setor": None}
        sb.tables["participantes"].append({**davi, "ativo": True})
        sb.tables["reuniao_participantes"].append({"id_reuniao": "R1", "participante_id": "P_DAVI"})
        reuniao = sb.tables["reunioes"][0]
        reuniao["json_ata"]["quadro_atribuicoes"].append(
            {"acao": "Levantar orcamento", "responsavel": "Davi Externo", "responsavel_id": "P_DAVI", "prazo": None}
        )

        _post(_client(sb), _evento_sign("sk-fac", "fabio@hsm.com", "Fabio Facilitador"))

        criadas = _pendencias(sb)
        assert sorted(p["quadro_pos"] for p in criadas) == [2, 3, 5]
        assert {p.get("responsavel_id") for p in criadas} == {"P_CARLA", None, "P_DAVI"}

    def test_sem_facilitador_no_envelope_fora_fica_para_finalizacao(self):
        sb = _sb()
        # Facilitador sai do roster (nao e Signatario do Envelope)
        sb.tables["reuniao_participantes"] = [
            rp for rp in sb.tables["reuniao_participantes"] if rp["participante_id"] != "P_FAC"
        ]
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        _post(client, _evento_sign("sk-bruno", "bruno@hsm.com"))
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 1, 4]

        # Finalizacao cria o resto (posicoes 2 e 3) sem duplicar nada
        _post(client, _evento("auto_close"))
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 1, 2, 3, 4]
        assert sb.tables["reunioes"][0]["status_ata"] == "ASSINADA"


# ═══════════════════════════════════════════════════════════════════════════
# CA: sem regressao nos caminhos atuais (fechamento total)
# ═══════════════════════════════════════════════════════════════════════════


class TestFechamentoIncremental:
    def test_auto_close_apos_signs_cria_o_resto_sem_duplicar(self):
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        res = _post(client, _evento("auto_close"))

        assert res.status_code == 200
        criadas = _pendencias(sb)
        assert sorted(p["quadro_pos"] for p in criadas) == [0, 1, 2, 3, 4]
        assert len({p["id_acao"] for p in criadas}) == 5
        assert sb.tables["reunioes"][0]["status_ata"] == "ASSINADA"

    def test_auto_close_sem_signs_cria_tudo(self):
        sb = _sb()
        res = _post(_client(sb), _evento("auto_close"))

        assert res.status_code == 200
        assert len(_pendencias(sb)) == 5
        assert sb.tables["reunioes"][0]["status_ata"] == "ASSINADA"

    def test_sign_apos_assinada_e_ignorado(self):
        sb = _sb(status_ata="ASSINADA")
        res = _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert _pendencias(sb) == []
        assert _aceites(sb) == []

    def test_sign_fora_de_aguardando_assinatura_e_ignorado(self):
        """Reuniao de volta em validacao (recusa/expiracao): sign tardio ou
        redelivery nao pode criar Pendencia de uma ata em revisao."""
        sb = _sb(status_ata="AGUARDANDO_VALIDACAO")
        res = _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert _pendencias(sb) == []
        assert _aceites(sb) == []

    def test_pendencias_legadas_sem_quadro_pos_nao_duplicam(self):
        """Reuniao com liberacao total pre-incremental (sem quadro_pos) nao recria nada."""
        sb = _sb()
        sb.tables["pendencias"].extend(
            [
                {"id_acao": "A001", "id_reuniao": "R1", "status": "PENDENTE"},
                {"id_acao": "A002", "id_reuniao": "R1", "status": "PENDENTE"},
            ]
        )
        res = _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert len(_pendencias(sb)) == 2


# ═══════════════════════════════════════════════════════════════════════════
# CA: dois sign concorrentes nao duplicam Pendencia nem numeracao A###
# ═══════════════════════════════════════════════════════════════════════════


class TestConcorrencia:
    def test_corrida_na_numeracao_reexecuta_e_nao_duplica_id(self, monkeypatch):
        """Leitura defasada do ultimo A### colide no PK e o retry renumera."""
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))  # A001, A002

        real = pendencia_service._get_last_id_num
        chamadas = {"n": 0}

        def _defasado(supabase):
            chamadas["n"] += 1
            if chamadas["n"] == 1:
                return 0  # leitura defasada: outra sessao ja gravou A001/A002
            return real(supabase)

        monkeypatch.setattr(pendencia_service, "_get_last_id_num", _defasado)
        res = _post(client, _evento_sign("sk-bruno", "bruno@hsm.com"))

        assert res.status_code == 200
        ids = [p["id_acao"] for p in _pendencias(sb)]
        assert len(ids) == len(set(ids)) == 3
        assert chamadas["n"] >= 2  # houve retry

    def test_corrida_na_mesma_acao_nao_duplica_pendencia(self):
        """Outro webhook ganha a corrida da mesma acao entre a leitura e o insert."""
        sb = _sb()
        client = _client(sb)

        def _outro_webhook_insere_antes():
            sb.tables["pendencias"].append(
                {
                    "id_acao": "A001",
                    "id_reuniao": "R1",
                    "status": "PENDENTE",
                    "responsavel_id": "P_ANA",
                    "quadro_pos": 0,
                }
            )
            sb.tables["pendencias"].append(
                {
                    "id_acao": "A002",
                    "id_reuniao": "R1",
                    "status": "PENDENTE",
                    "responsavel_id": "P_ANA",
                    "quadro_pos": 4,
                }
            )

        sb.antes_do_insert["pendencias"] = _outro_webhook_insere_antes
        res = _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        criadas = _pendencias(sb)
        assert sorted(p["quadro_pos"] for p in criadas) == [0, 4]  # nada duplicado

    def test_aceite_concorrente_nao_quebra_nem_duplica(self):
        """Outra transacao grava o mesmo aceite entre a leitura e o insert."""
        sb = _sb()
        client = _client(sb)

        def _outra_transacao_grava_aceite():
            sb.tables["reuniao_aceites"].append(
                {
                    "id": "aceite-x",
                    "id_reuniao": "R1",
                    "participante_id": "P_ANA",
                    "signer_key": "sk-ana",
                    "email": "ana@hsm.com",
                    "origem": "clicksign",
                    "aceito_em": "2026-08-14T09:59:59-03:00",
                }
            )

        sb.antes_do_insert["reuniao_aceites"] = _outra_transacao_grava_aceite
        res = _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        assert res.status_code == 200
        assert len(_aceites(sb)) == 1
        assert len(_pendencias(sb)) == 2  # as Pendencias da Ana nascem mesmo assim


# ═══════════════════════════════════════════════════════════════════════════
# Guardas do seam
# ═══════════════════════════════════════════════════════════════════════════


class TestGuardas:
    def test_hmac_invalido_rejeitado(self):
        sb = _sb()
        res = _post(_client(sb), _evento_sign("sk-ana", "ana@hsm.com"), secret="segredo-errado")
        assert res.status_code == 401
        assert _pendencias(sb) == []

    def test_evento_desconhecido_sem_efeito(self):
        sb = _sb()
        res = _post(_client(sb), _evento("signature_started"))
        assert res.status_code == 200
        assert _pendencias(sb) == []
        assert _aceites(sb) == []

    def test_sign_sem_signer_e_ignorado(self):
        sb = _sb()
        payload = {"event": {"name": "sign", "data": {}}, "document": {"key": DOC_KEY}}
        res = _post(_client(sb), payload)
        assert res.status_code == 200
        assert _pendencias(sb) == []
