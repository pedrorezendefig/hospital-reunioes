"""Finalização real do Envelope (issue #275, ADR 0030).

Seam: POST /api/webhooks/clicksign com payloads oficiais da ClickSign
(snake_case). O evento `deadline` com ao menos uma assinatura finaliza a
Reunião como um fechamento normal: Pendências restantes nascem, a Reunião vira
ASSINADA e o sistema registra quem não assinou (cruzando os eventos `sign`
com a lista de signers, persistindo a contagem para o selo discreto).
O `document_closed` baixa o PDF assinado (a doc só garante o arquivo aí),
mantendo o fallback best-effort do fechamento.

ClickSign SEMPRE mockado (o .env de teste carrega credenciais reais).
Harness de mock compartilhado com test_aceites_sign_incremental (issue #274).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_aceites_sign_incremental import (  # noqa: E402
    SECRET,
    _client,
    _evento,
    _evento_sign,
    _post,
    _sb,
    _SupabaseMock,
)

from app.config import settings  # noqa: E402
from app.services import clicksign_service, storage  # noqa: E402

ENVELOPE_ID = "env-r1"


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


@pytest.fixture
def pdf_baixado(monkeypatch) -> list[str]:
    """get_signed_document mockado; registra o envelope consultado."""
    chamadas: list[str] = []

    def _fake(envelope_id: str):
        chamadas.append(envelope_id)
        return b"%PDF-signed"

    monkeypatch.setattr(clicksign_service, "get_signed_document", _fake)
    monkeypatch.setattr(storage, "upload_file", lambda *_a, **_kw: "http://storage/pdfs/ata_assinada.pdf")
    return chamadas


def _signer(key: str, email: str, *, assinou: bool) -> dict:
    """Formato de clicksign_service.list_signers (signers × eventos `sign`)."""
    return {
        "signer_id": key,
        "nome": email.split("@")[0].title(),
        "email": email,
        "status": "signed" if assinou else "pending",
        "signed_at": "2026-08-10T09:00:00-03:00" if assinou else None,
    }


@pytest.fixture
def signers_clicksign(monkeypatch) -> list[dict]:
    """Roster de signers devolvido pela consulta à ClickSign (mockada).

    Mutável: cada teste define quem assinou antes de postar o evento.
    """
    roster: list[dict] = []
    monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: roster)
    return roster


def _pendencias(sb: _SupabaseMock) -> list[dict]:
    return sb.tables["pendencias"]


def _aceites(sb: _SupabaseMock) -> list[dict]:
    return sb.tables["reuniao_aceites"]


def _reuniao(sb: _SupabaseMock) -> dict:
    return sb.tables["reunioes"][0]


# ═══════════════════════════════════════════════════════════════════════════
# CA: deadline com ao menos uma assinatura finaliza a Reunião
# ═══════════════════════════════════════════════════════════════════════════


class TestDeadlineComAssinaturaParcial:
    def test_deadline_com_assinatura_parcial_finaliza(self, signers_clicksign, pdf_baixado):
        """deadline após o sign da Ana: Pendências restantes nascem e a
        Reunião vira ASSINADA (fechamento normal, ADR 0030 decisão 2)."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=False),
                _signer("sk-ana", "ana@hsm.com", assinou=True),
                _signer("sk-bruno", "bruno@hsm.com", assinou=False),
            ]
        )
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 4]

        res = _post(client, _evento("deadline"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        assert _reuniao(sb)["data_assinatura"]
        assert sorted(p["quadro_pos"] for p in _pendencias(sb)) == [0, 1, 2, 3, 4]

    def test_deadline_registra_faltantes_para_o_selo(self, signers_clicksign, pdf_baixado):
        """CA: faltantes registrados no Registro de Aceites. A contagem "N de
        M assinaram" fica persistida na Reunião; quem assinou tem aceite
        `clicksign`, quem faltou fica sem aceite."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=False),
                _signer("sk-ana", "ana@hsm.com", assinou=True),
                _signer("sk-bruno", "bruno@hsm.com", assinou=False),
            ]
        )
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        _post(client, _evento("deadline"))

        assert _reuniao(sb)["signatarios_total"] == 3
        assert _reuniao(sb)["signatarios_assinaram"] == 1
        assert len(_aceites(sb)) == 1
        assert _aceites(sb)[0]["participante_id"] == "P_ANA"

    def test_deadline_reconcilia_aceite_de_sign_perdido(self, signers_clicksign, pdf_baixado):
        """Webhook `sign` do Bruno se perdeu: no fechamento, o cruzamento com
        os eventos da ClickSign registra o aceite dele mesmo assim."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=False),
                _signer("sk-ana", "ana@hsm.com", assinou=True),
                _signer("sk-bruno", "bruno@hsm.com", assinou=True),
            ]
        )
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))  # sign do Bruno perdido

        _post(client, _evento("deadline"))

        assert _reuniao(sb)["signatarios_assinaram"] == 2
        aceites = {a.get("signer_key"): a for a in _aceites(sb)}
        assert set(aceites) == {"sk-ana", "sk-bruno"}
        assert aceites["sk-bruno"]["origem"] == "clicksign"
        assert aceites["sk-bruno"]["participante_id"] == "P_BRUNO"
        assert aceites["sk-bruno"]["aceito_em"] == "2026-08-10T09:00:00-03:00"


# ═══════════════════════════════════════════════════════════════════════════
# deadline com zero assinaturas NÃO finaliza (a ClickSign cancela o documento)
# ═══════════════════════════════════════════════════════════════════════════


class TestDeadlineSemAssinatura:
    def test_deadline_com_zero_assinaturas_nao_finaliza(self, signers_clicksign, pdf_baixado):
        """Com zero assinaturas a ClickSign cancela o documento; a finalização
        não acontece (o desfecho desse caso é o modo interno, issue #276)."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=False),
                _signer("sk-ana", "ana@hsm.com", assinou=False),
            ]
        )
        sb = _sb()

        res = _post(_client(sb), _evento("deadline"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _pendencias(sb) == []

    def test_deadline_sem_clicksign_usa_aceites_locais_como_fallback(self, monkeypatch, pdf_baixado):
        """ClickSign indisponível na consulta: os aceites `clicksign` locais
        (gatilho incremental) decidem; com aceite da Ana, finaliza."""
        monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: None)
        sb = _sb()
        client = _client(sb)
        _post(client, _evento_sign("sk-ana", "ana@hsm.com"))

        res = _post(client, _evento("deadline"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        # Sem a consulta não há cruzamento: contagem fica ausente (sem selo)
        assert "signatarios_total" not in _reuniao(sb)

    def test_deadline_sem_clicksign_e_sem_aceite_local_nao_finaliza(self, monkeypatch, pdf_baixado):
        monkeypatch.setattr(clicksign_service, "list_signers", lambda _env: None)
        sb = _sb()

        res = _post(_client(sb), _evento("deadline"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _pendencias(sb) == []

    def test_deadline_fora_de_aguardando_assinatura_e_ignorado(self, signers_clicksign, pdf_baixado):
        """Evento agendado chega tarde por natureza: Reunião de volta em
        validação não pode ser finalizada por deadline do envelope antigo."""
        signers_clicksign.append(_signer("sk-ana", "ana@hsm.com", assinou=True))
        sb = _sb(status_ata="AGUARDANDO_VALIDACAO")

        res = _post(_client(sb), _evento("deadline"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_VALIDACAO"
        assert _pendencias(sb) == []

    def test_deadline_duplicado_apos_assinada_e_ignorado(self, signers_clicksign, pdf_baixado):
        signers_clicksign.append(_signer("sk-ana", "ana@hsm.com", assinou=True))
        sb = _sb()
        client = _client(sb)
        _post(client, _evento("deadline"))
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        antes = len(_pendencias(sb))

        res = _post(client, _evento("deadline"))

        assert res.status_code == 200
        assert len(_pendencias(sb)) == antes


# ═══════════════════════════════════════════════════════════════════════════
# CA: fechamento total (close/auto_close) também persiste a contagem
# ═══════════════════════════════════════════════════════════════════════════


class TestContagemNoFechamentoTotal:
    def test_auto_close_com_todos_assinando_fica_sem_faltantes(self, signers_clicksign, pdf_baixado):
        """100% ClickSign: contagem cheia (o banner não mostra selo)."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=True),
                _signer("sk-ana", "ana@hsm.com", assinou=True),
                _signer("sk-bruno", "bruno@hsm.com", assinou=True),
            ]
        )
        sb = _sb()

        res = _post(_client(sb), _evento("auto_close"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        assert _reuniao(sb)["signatarios_total"] == 3
        assert _reuniao(sb)["signatarios_assinaram"] == 3

    def test_close_manual_com_faltantes_persiste_contagem(self, signers_clicksign, pdf_baixado):
        """Finalização manual antes de todos assinarem também registra os
        faltantes (mesmo caminho da finalização por deadline)."""
        signers_clicksign.extend(
            [
                _signer("sk-fac", "fabio@hsm.com", assinou=True),
                _signer("sk-ana", "ana@hsm.com", assinou=False),
                _signer("sk-bruno", "bruno@hsm.com", assinou=False),
            ]
        )
        sb = _sb()

        res = _post(_client(sb), _evento("close"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        assert _reuniao(sb)["signatarios_total"] == 3
        assert _reuniao(sb)["signatarios_assinaram"] == 1
        assert {a.get("signer_key") for a in _aceites(sb)} == {"sk-fac"}


# ═══════════════════════════════════════════════════════════════════════════
# CA: document_closed baixa o PDF assinado; fallback do fechamento mantido
# ═══════════════════════════════════════════════════════════════════════════


class TestDocumentClosed:
    def test_document_closed_baixa_o_pdf_pelo_envelope_id(self, pdf_baixado):
        """Reunião ASSINADA sem PDF (fallback do fechamento falhou): o
        document_closed baixa o arquivo, consultando pelo envelope_id (v3)."""
        sb = _sb(status_ata="ASSINADA")

        res = _post(_client(sb), _evento("document_closed"))

        assert res.status_code == 200
        assert _reuniao(sb)["url_pdf_assinado"] == "http://storage/pdfs/ata_assinada.pdf"
        assert pdf_baixado == [ENVELOPE_ID]

    def test_document_closed_nao_mexe_no_status(self, pdf_baixado):
        """document_closed pode chegar antes do evento de fechamento: salva o
        PDF e deixa o desfecho de estado para o close/auto_close/deadline."""
        sb = _sb()

        res = _post(_client(sb), _evento("document_closed"))

        assert res.status_code == 200
        assert _reuniao(sb)["status_ata"] == "AGUARDANDO_ASSINATURA"
        assert _reuniao(sb)["url_pdf_assinado"] == "http://storage/pdfs/ata_assinada.pdf"
        assert _pendencias(sb) == []

    def test_document_closed_com_pdf_ja_salvo_e_idempotente(self, pdf_baixado):
        sb = _sb(status_ata="ASSINADA", url_pdf_assinado="http://storage/pdfs/ata_assinada.pdf")

        res = _post(_client(sb), _evento("document_closed"))

        assert res.status_code == 200
        assert pdf_baixado == []

    def test_falha_no_download_nao_quebra_o_webhook(self, monkeypatch):
        def _explode(_env):
            raise RuntimeError("ClickSign fora do ar")

        monkeypatch.setattr(clicksign_service, "get_signed_document", _explode)
        sb = _sb(status_ata="ASSINADA")

        res = _post(_client(sb), _evento("document_closed"))

        assert res.status_code == 200
        assert "url_pdf_assinado" not in _reuniao(sb)

    def test_fechamento_nao_rebaixa_pdf_ja_salvo_pelo_document_closed(self, signers_clicksign, pdf_baixado):
        """document_closed chegou antes do fechamento: o PDF já salvo é
        reaproveitado, sem novo download."""
        signers_clicksign.append(_signer("sk-ana", "ana@hsm.com", assinou=True))
        sb = _sb(url_pdf_assinado="http://storage/pdfs/ata_assinada.pdf")

        _post(_client(sb), _evento("auto_close"))

        assert _reuniao(sb)["status_ata"] == "ASSINADA"
        assert _reuniao(sb)["url_pdf_assinado"] == "http://storage/pdfs/ata_assinada.pdf"
        assert pdf_baixado == []

    def test_fallback_do_fechamento_mantido_e_usa_envelope_id(self, signers_clicksign, pdf_baixado):
        """O fechamento continua tentando o PDF (best-effort), agora pelo
        envelope_id quando ele existe (a consulta v3 é por Envelope)."""
        signers_clicksign.append(_signer("sk-ana", "ana@hsm.com", assinou=True))
        sb = _sb()

        _post(_client(sb), _evento("auto_close"))

        assert _reuniao(sb)["url_pdf_assinado"] == "http://storage/pdfs/ata_assinada.pdf"
        assert pdf_baixado == [ENVELOPE_ID]
