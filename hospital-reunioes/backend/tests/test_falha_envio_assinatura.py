"""
Falha silenciosa no envio para assinatura (issue #193).

O /aprovar responde sucesso na hora e agenda start_signature_flow em background.
Antes do fix, qualquer falha na coreografia ClickSign (baixar PDF, criar
Envelope, anexar documento, adicionar signatarios, ativar) apenas logava e
retornava: a Reuniao ficava parada em AGUARDANDO_VALIDACAO sem nenhum registro
consultavel do erro.

Contrato coberto aqui:
  1. Falha em CADA passo da coreografia grava `falha_envio_assinatura` na
     Reuniao (dict com passo, detalhe e hora) e NAO transiciona o status.
  2. Sucesso continua transicionando para AGUARDANDO_ASSINATURA e LIMPA a
     falha registrada por uma tentativa anterior (reenvio manual).
  3. Fluxo sem falha: nenhum registro de falha e comportamento igual ao de hoje.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@dataclass
class _Result:
    data: Any


class _TableQuery:
    """Mock fluente minimo: select/update + eq/order."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def order(self, *_a, **_kw):
        return self

    def execute(self):
        matched = [r for r in self._rows if all(r.get(c) == v for c, v in self._filters)]
        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)

    def table(self, name: str):
        rows = getattr(self, name, None)
        if rows is None:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(rows)


def _supabase_base(falha_previa: dict | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        participantes=[
            {"id": "P001", "nome_completo": "Caroline Soares", "email": "caroline@hsm.com"},
        ],
        reuniao_participantes=[
            {"id_reuniao": "R_TEST", "participante_id": "P001", "sequence_assinatura": 1},
        ],
        reunioes=[
            {
                "id_reuniao": "R_TEST",
                "status_ata": "AGUARDANDO_VALIDACAO",
                "envelope_key_clicksign": None,
                "envelope_id_clicksign": None,
                "falha_envio_assinatura": falha_previa,
            }
        ],
    )


def _patch_fluxo_feliz(monkeypatch):
    """Todos os passos da coreografia funcionando; testes quebram um por vez."""
    from app.services import clicksign_service, storage

    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"PDF_BYTES")
    monkeypatch.setattr(clicksign_service, "create_envelope", lambda _name: "env-id")
    monkeypatch.setattr(clicksign_service, "add_document", lambda *_a, **_kw: "doc-id")
    monkeypatch.setattr(clicksign_service, "add_signer", lambda *_a, **_kw: "signer-id")
    monkeypatch.setattr(clicksign_service, "create_qualification_requirement", lambda *_a, **_kw: "qual-id")
    monkeypatch.setattr(clicksign_service, "create_auth_requirement", lambda *_a, **_kw: "auth-id")
    monkeypatch.setattr(clicksign_service, "activate_envelope", lambda _env: True)
    monkeypatch.setattr(clicksign_service, "notify_signers", lambda _env: True)


def _run(sb):
    from app.services import clicksign_service

    clicksign_service.start_signature_flow(sb, "R_TEST", {"id_reuniao": "R_TEST"})
    return sb.reunioes[0]


def _assert_falha_registrada(reuniao: dict, passo: str):
    assert reuniao["status_ata"] == "AGUARDANDO_VALIDACAO", (
        f"Falha nao pode avancar o status; veio {reuniao['status_ata']}"
    )
    falha = reuniao.get("falha_envio_assinatura")
    assert isinstance(falha, dict), f"Esperava registro consultavel da falha; veio {falha!r}"
    assert falha.get("passo") == passo, f"Esperava passo={passo!r}; veio {falha.get('passo')!r}"
    assert falha.get("em"), "Registro da falha deve ter a hora (campo 'em')"
    assert falha.get("detalhe"), "Registro da falha deve ter o detalhe do erro"


# ───────────────────────────────────────────────────────────────────────────
# 1. Cada passo da coreografia falhando vira registro consultavel
# ───────────────────────────────────────────────────────────────────────────


def test_falha_baixar_pdf_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import storage

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: None)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "baixar_pdf")


def test_falha_criar_envelope_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "create_envelope", lambda _name: None)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "criar_envelope")


def test_falha_anexar_documento_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "add_document", lambda *_a, **_kw: None)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "anexar_documento")


def test_nenhum_signatario_adicionado_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "add_signer", lambda *_a, **_kw: None)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "adicionar_signatarios")


def test_falha_ativar_envelope_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "activate_envelope", lambda _env: False)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "ativar_envelope")


def test_excecao_inesperada_registra_erro_e_nao_avanca(monkeypatch):
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)

    def _boom(_name):
        raise RuntimeError("timeout inesperado")

    monkeypatch.setattr(clicksign_service, "create_envelope", _boom)

    reuniao = _run(_supabase_base())
    _assert_falha_registrada(reuniao, "excecao")


def test_falha_notificar_registra_erro_mas_status_avanca(monkeypatch):
    """Falha so na notificacao NAO bloqueia o status: o Envelope ja esta ativo
    (abortar convidaria um reenvio que criaria um segundo Envelope ativo).
    A falha fica registrada para a tela orientar o uso do Lembrar."""
    from app.services import clicksign_service

    _patch_fluxo_feliz(monkeypatch)
    monkeypatch.setattr(clicksign_service, "notify_signers", lambda _env: False)

    reuniao = _run(_supabase_base())

    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["envelope_id_clicksign"] == "env-id"
    falha = reuniao["falha_envio_assinatura"]
    assert isinstance(falha, dict)
    assert falha["passo"] == "notificar_signatarios"
    assert falha["em"]
    assert falha["detalhe"]


def test_excecao_pos_ativacao_registra_passo_finalizar(monkeypatch):
    """Excecao DEPOIS da ativacao (ex: update final do banco falha) registra o
    passo 'finalizar': o Envelope pode ja estar ativo com emails enviados, e a
    tela precisa avisar antes de um reenvio que duplicaria o Envelope."""
    _patch_fluxo_feliz(monkeypatch)

    sb = _supabase_base()

    class _TableExplodeNoSucesso(_TableQuery):
        def update(self, payload):
            if (payload or {}).get("status_ata") == "AGUARDANDO_ASSINATURA":
                raise RuntimeError("update final falhou")
            return super().update(payload)

    class _SupabaseExplodeNoSucesso:
        def table(self, name):
            rows = getattr(sb, name)
            return _TableExplodeNoSucesso(rows)

    from app.services import clicksign_service

    clicksign_service.start_signature_flow(_SupabaseExplodeNoSucesso(), "R_TEST", {"id_reuniao": "R_TEST"})
    reuniao = sb.reunioes[0]

    assert reuniao["status_ata"] == "AGUARDANDO_VALIDACAO"
    falha = reuniao["falha_envio_assinatura"]
    assert isinstance(falha, dict)
    assert falha["passo"] == "finalizar"
    assert "ativação" in falha["detalhe"]


# ───────────────────────────────────────────────────────────────────────────
# 2. Reenvio apos falha: sucesso limpa o registro e avanca o status
# ───────────────────────────────────────────────────────────────────────────


def test_reenvio_com_sucesso_limpa_falha_e_avanca_status(monkeypatch):
    _patch_fluxo_feliz(monkeypatch)

    falha_previa = {"passo": "criar_envelope", "detalhe": "HTTP 500", "em": "2026-07-17T10:00:00+00:00"}
    reuniao = _run(_supabase_base(falha_previa=falha_previa))

    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["falha_envio_assinatura"] is None, (
        f"Sucesso deve limpar a falha anterior; veio {reuniao['falha_envio_assinatura']!r}"
    )
    assert reuniao["envelope_id_clicksign"] == "env-id"
    assert reuniao["envelope_key_clicksign"] == "doc-id"


# ───────────────────────────────────────────────────────────────────────────
# 3. Fluxo sem falha: nenhuma mudanca de comportamento visivel
# ───────────────────────────────────────────────────────────────────────────


def test_fluxo_sem_falha_nao_registra_erro(monkeypatch):
    _patch_fluxo_feliz(monkeypatch)

    reuniao = _run(_supabase_base())

    assert reuniao["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao["falha_envio_assinatura"] is None
    assert reuniao["envelope_id_clicksign"] == "env-id"
    assert reuniao["envelope_key_clicksign"] == "doc-id"
