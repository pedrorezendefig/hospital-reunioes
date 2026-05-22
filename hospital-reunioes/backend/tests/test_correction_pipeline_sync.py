"""
Teste de integração do bug 7→4:

    diretor sobe transcrição → IA extrai 7 participantes →
    diretor corrige pra 4 via Chat de Correção →
    ao aprovar, ClickSign DEVE receber 4 signers (não 7).

Antes do fix em participant_matcher.match_participants, a tabela
`reuniao_participantes` ficava com os 7 originais mesmo depois da
correção, e start_signature_flow lia tudo e mandava email pros 7.

Este arquivo cobre dois caminhos:

  1. run_correction_pipeline ⇒ tabela junção fica com 4 vínculos
  2. start_signature_flow ⇒ chama add_signer 4× com emails dos 4 corretos
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
    """Mock fluente com suporte a select/update/delete/upsert + eq/in_/ilike/limit/order."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str = "select"
        self._payload: Any = None
        self._filters: list[tuple[str, Any]] = []
        self._in_filters: list[tuple[str, list]] = []
        self._ilike_filters: list[tuple[str, str]] = []
        self._on_conflict: str | None = None
        self._limit: int | None = None

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def upsert(self, payload, on_conflict=None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def eq(self, col, value):
        self._filters.append((col, value))
        return self

    def in_(self, col, values):
        self._in_filters.append((col, list(values)))
        return self

    def ilike(self, col, pattern):
        self._ilike_filters.append((col, pattern))
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, n):
        self._limit = n
        return self

    def _matches(self, r: dict) -> bool:
        for col, value in self._filters:
            if r.get(col) != value:
                return False
        for col, values in self._in_filters:
            if r.get(col) not in values:
                return False
        for col, pattern in self._ilike_filters:
            needle = pattern.strip("%").lower()
            if needle not in str(r.get(col) or "").lower():
                return False
        return True

    def execute(self):
        if self._op == "upsert":
            keys = (self._on_conflict or "").split(",") if self._on_conflict else []
            keys = [k.strip() for k in keys if k.strip()]
            if keys:
                for r in list(self._rows):
                    if all(r.get(k) == self._payload.get(k) for k in keys):
                        self._rows.remove(r)
                        break
            self._rows.append(dict(self._payload))
            return _Result(data=[dict(self._payload)])

        matched = [r for r in self._rows if self._matches(r)]
        if self._limit is not None:
            matched = matched[: self._limit]

        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))

        if self._op == "delete":
            for r in list(matched):
                self._rows.remove(r)
            return _Result(data=list(matched))

        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "participantes":
            return _TableQuery(self.participantes)
        if name == "reuniao_participantes":
            return _TableQuery(self.reuniao_participantes)
        if name == "reunioes":
            return _TableQuery(self.reunioes)
        raise AssertionError(f"Tabela inesperada: {name}")


def _participante(pid, nome, email, cargo=""):
    return {
        "id": pid,
        "nome_completo": nome,
        "email": email,
        "cargo": cargo,
        "setor": None,
        "ativo": True,
    }


# ───────────────────────────────────────────────────────────────────────────
# Cenário canônico: 7 participantes pré-vinculados, diretor corrige pra 4
# ───────────────────────────────────────────────────────────────────────────


def _sb_com_7_vinculados() -> _SupabaseMock:
    participantes = [
        _participante("P001", "Caroline Soares", "caroline@hsm.com", "Diretora"),
        _participante("P002", "Fernando Bastos", "fernando@hsm.com", "Gerente"),
        _participante("P003", "Ana Lima", "ana@hsm.com", "Enfermeira"),
        _participante("P004", "Bruno Castro", "bruno@hsm.com", "Médico"),
        _participante("P005", "Carla Mendes", "carla@hsm.com", "Analista"),
        _participante("P006", "Daniel Rocha", "daniel@hsm.com", "Técnico"),
        _participante("P007", "Eduardo Pires", "eduardo@hsm.com", "Coordenador"),
    ]
    vinculos = [{"id_reuniao": "R_TEST", "participante_id": p["id"], "sequence_assinatura": 2} for p in participantes]
    reunioes = [
        {
            "id_reuniao": "R_TEST",
            "data": "2026-05-22",
            "tipo": "Diretoria",
            "json_ata": {"participantes": [{"nome": p["nome_completo"]} for p in participantes]},
            "objetivo": None,
            "hora_inicio": None,
            "hora_fim": None,
            "status_ata": "AGUARDANDO_VALIDACAO",
        }
    ]
    return _SupabaseMock(participantes=participantes, reuniao_participantes=vinculos, reunioes=reunioes)


def test_correcao_remove_3_participantes_sincroniza_tabela(monkeypatch):
    """
    run_correction_pipeline com prune_missing=True deve deixar
    reuniao_participantes com 4 rows após o diretor remover 3.
    """
    from app.pipeline import orchestrator
    from app.services import ai_processor, storage

    sb = _sb_com_7_vinculados()

    # Mock IA: retorna json_ata corrigido com 4 participantes
    json_ata_corrigido = {
        "participantes": [
            {"nome": "Caroline Soares"},
            {"nome": "Fernando Bastos"},
            {"nome": "Ana Lima"},
            {"nome": "Bruno Castro"},
        ],
        "quadro_atribuicoes": [],  # vazio pra pular _canonicalize_cargos_quadro
    }
    monkeypatch.setattr(
        ai_processor,
        "process_correcao",
        lambda *_a, **_kw: json_ata_corrigido,
    )

    # Mock storage download (retorna bytes dummy de transcrição)
    monkeypatch.setattr(
        storage,
        "download_file",
        lambda *_a, **_kw: b"transcricao dummy",
    )

    # Mock _generate_and_upload_pdf pra não invocar WeasyPrint real
    monkeypatch.setattr(
        orchestrator,
        "_generate_and_upload_pdf",
        lambda *_a, **_kw: "https://fake/url/ata.pdf",
    )

    orchestrator.run_correction_pipeline(sb, "R_TEST", "remover Carla, Daniel e Eduardo")

    ids_finais = {row["participante_id"] for row in sb.reuniao_participantes if row["id_reuniao"] == "R_TEST"}
    assert ids_finais == {"P001", "P002", "P003", "P004"}, (
        f"Esperava 4 sobreviventes após correção (P001..P004), veio: {sorted(ids_finais)}"
    )

    reuniao_final = sb.reunioes[0]
    assert reuniao_final["status_ata"] == "AGUARDANDO_VALIDACAO"
    assert reuniao_final["json_ata"] == json_ata_corrigido


# ───────────────────────────────────────────────────────────────────────────
# start_signature_flow lê só os 4 sobreviventes e manda email pros 4
# ───────────────────────────────────────────────────────────────────────────


def test_start_signature_flow_envia_para_4_emails_corretos(monkeypatch):
    """
    Depois da correção (4 rows em reuniao_participantes), start_signature_flow
    deve chamar add_signer EXATAMENTE 4 vezes com os emails dos 4 sobreviventes.
    """
    from app.services import clicksign_service, storage

    # Estado pós-correção: só 4 vínculos sobreviveram (P001..P004)
    sb = _SupabaseMock(
        participantes=[
            _participante("P001", "Caroline Soares", "caroline@hsm.com"),
            _participante("P002", "Fernando Bastos", "fernando@hsm.com"),
            _participante("P003", "Ana Lima", "ana@hsm.com"),
            _participante("P004", "Bruno Castro", "bruno@hsm.com"),
        ],
        reuniao_participantes=[
            {"id_reuniao": "R_TEST", "participante_id": "P001", "sequence_assinatura": 2},
            {"id_reuniao": "R_TEST", "participante_id": "P002", "sequence_assinatura": 2},
            {"id_reuniao": "R_TEST", "participante_id": "P003", "sequence_assinatura": 2},
            {"id_reuniao": "R_TEST", "participante_id": "P004", "sequence_assinatura": 2},
        ],
        reunioes=[
            {
                "id_reuniao": "R_TEST",
                "envelope_key_clicksign": None,
                "status_ata": "AGUARDANDO_VALIDACAO",
            }
        ],
    )

    monkeypatch.setattr(storage, "download_file", lambda *_a, **_kw: b"PDF_BYTES")

    monkeypatch.setattr(clicksign_service, "create_envelope", lambda _name: "env-id")
    monkeypatch.setattr(clicksign_service, "add_document", lambda *_a, **_kw: "doc-id")
    monkeypatch.setattr(
        clicksign_service,
        "create_qualification_requirement",
        lambda *_a, **_kw: "qual-id",
    )
    monkeypatch.setattr(
        clicksign_service,
        "create_auth_requirement",
        lambda *_a, **_kw: "auth-id",
    )
    monkeypatch.setattr(clicksign_service, "activate_envelope", lambda _env: True)
    monkeypatch.setattr(clicksign_service, "notify_signers", lambda _env: True)

    # Spy em add_signer
    chamadas_add_signer: list[dict] = []

    def _fake_add_signer(envelope_id, nome, email):
        chamadas_add_signer.append({"envelope_id": envelope_id, "nome": nome, "email": email})
        return f"signer-{email}"

    monkeypatch.setattr(clicksign_service, "add_signer", _fake_add_signer)

    clicksign_service.start_signature_flow(sb, "R_TEST", {"id_reuniao": "R_TEST"})

    emails = sorted(c["email"] for c in chamadas_add_signer)
    assert emails == ["ana@hsm.com", "bruno@hsm.com", "caroline@hsm.com", "fernando@hsm.com"], (
        f"Esperava add_signer chamado 4x pros 4 corretos; veio: {emails}"
    )
    assert len(chamadas_add_signer) == 4

    reuniao_final = sb.reunioes[0]
    assert reuniao_final["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert reuniao_final["envelope_key_clicksign"] == "doc-id"
