"""Testes do editor manual de participantes na validação da Ata (ADR 0023, #201).

Cobre as duas operações determinísticas (sem IA) da lista de participantes da Ata
enquanto a Reunião está em AGUARDANDO_VALIDACAO:

- Excluir: remove de `json_ata.participantes` E do roster `reuniao_participantes`
  na mesma ação (tela, PDF e ClickSign consistentes). Bloqueia quando a pessoa é
  responsável de uma ação no Quadro (invariante do ADR 0008).
- Adicionar: recebe um participante do cadastro, grava em `json_ata.participantes`
  e faz upsert idempotente no roster.

Mais os gates herdados do editor de Quadro (`patch_quadro_atribuicao`): só em
AGUARDANDO_VALIDACAO, gate de visibilidade (404) e Secretária sem acesso (403).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import (  # noqa: E402
    AdicionarParticipanteAtaRequest,
    ExcluirParticipanteAtaRequest,
)
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import participantes_ata_service  # noqa: E402

CURRENT_USER = {"id": "auth-uid-1", "email": "facilitador@hospital.com"}


# ─── Mock Supabase (select/eq/in_/update/upsert/delete) ─────────────────────


@dataclass
class _Result:
    data: Any


class _Query:
    """Suporta select().eq()/in_().limit().execute(), update().eq().execute(),
    upsert([...], on_conflict=...).execute() (idempotente pela chave de conflito)
    e delete().eq().eq().execute()."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str | None = None
        self._payload: Any = None
        self._on_conflict: str | None = None
        self._filters_eq: list[tuple[str, Any]] = []
        self._filters_in: list[tuple[str, list]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def upsert(self, payload, *, on_conflict: str | None = None):
        self._op = "upsert"
        self._payload = payload
        self._on_conflict = on_conflict
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, col, val):
        self._filters_eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._filters_in.append((col, list(vals)))
        return self

    def limit(self, _n):
        return self

    def _match(self) -> list:
        matched = list(self._rows)
        for col, val in self._filters_eq:
            matched = [r for r in matched if r.get(col) == val]
        for col, vals in self._filters_in:
            matched = [r for r in matched if r.get(col) in vals]
        return matched

    def execute(self):
        if self._op == "upsert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            keys = [k.strip() for k in (self._on_conflict or "").split(",") if k.strip()]
            written = []
            for row in rows:
                existing = None
                if keys:
                    existing = next((r for r in self._rows if all(r.get(k) == row.get(k) for k in keys)), None)
                if existing is not None:
                    existing.update(row)
                    written.append(existing)
                else:
                    self._rows.append(row)
                    written.append(row)
            return _Result(data=written)

        if self._op == "insert":
            rows = self._payload if isinstance(self._payload, list) else [self._payload]
            self._rows.extend(rows)
            return _Result(data=list(rows))

        matched = self._match()

        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
            return _Result(data=list(matched))

        if self._op == "delete":
            for r in matched:
                self._rows.remove(r)
            return _Result(data=list(matched))

        return _Result(data=list(matched))


@dataclass
class _SupabaseMock:
    reunioes: list = field(default_factory=list)
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)

    def table(self, name: str):
        if name == "reunioes":
            return _Query(self.reunioes)
        if name == "participantes":
            return _Query(self.participantes)
        if name == "reuniao_participantes":
            return _Query(self.reuniao_participantes)
        raise AssertionError(f"Tabela inesperada no mock: {name}")


# ─── Fixtures de dados ──────────────────────────────────────────────────────


def _json_ata(*, com_responsavel: bool = False) -> dict:
    quadro = []
    if com_responsavel:
        quadro = [
            {
                "acao": "Elaborar relatório",
                "responsavel": "Ana Silva",
                "cargo": "Gerente",
                "responsavel_id": "P002",
            }
        ]
    return {
        "participantes": [
            {"nome": "Pedro Rezende", "cargo": "Diretor", "setor": "Diretoria", "presente": True},
            {"nome": "Ana Silva", "cargo": "Gerente", "setor": "Enfermagem", "presente": True},
        ],
        "quadro_atribuicoes": quadro,
    }


def _reuniao(status: str = "AGUARDANDO_VALIDACAO", *, com_responsavel: bool = False) -> dict:
    return {
        "id_reuniao": "R123",
        "status_ata": status,
        "json_ata": _json_ata(com_responsavel=com_responsavel),
    }


def _roster() -> list[dict]:
    return [
        {"id_reuniao": "R123", "participante_id": "P001"},
        {"id_reuniao": "R123", "participante_id": "P002"},
    ]


def _cadastro() -> list[dict]:
    return [
        {"id": "P001", "nome_completo": "Pedro Rezende", "cargo": "Diretor", "setor": "Diretoria", "ativo": True},
        {"id": "P002", "nome_completo": "Ana Silva", "cargo": "Gerente", "setor": "Enfermagem", "ativo": True},
        {
            "id": "P003",
            "nome_completo": "Carlos Ferreira",
            "cargo": "Coordenador",
            "setor": "Financeiro",
            "ativo": True,
        },
    ]


@pytest.fixture
def facilitador(monkeypatch):
    """Usuário regular com acesso à Reunião (passa Secretária e visibilidade)."""

    async def _me(*_a, **_kw):
        return {"id": "P_ME", "access_profile": "regular"}

    async def _allowed(*_a, **_kw):
        return None  # None = sem restrição de visibilidade

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _me)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _allowed)


# ─── Service puro (reaproveitável pela fatia #203 "ignorar") ────────────────


class TestServicoPuro:
    def test_remover_da_lista_casa_por_nome_normalizado(self):
        lista = [{"nome": "Ana Silva"}, {"nome": "Pedro Rezende"}]
        nova, removeu = participantes_ata_service.remover_da_lista(lista, "ana silva")
        assert removeu is True
        assert [p["nome"] for p in nova] == ["Pedro Rezende"]

    def test_remover_da_lista_nome_ausente_nao_remove(self):
        lista = [{"nome": "Ana Silva"}]
        nova, removeu = participantes_ata_service.remover_da_lista(lista, "Fulano")
        assert removeu is False
        assert nova == lista

    def test_adicionar_na_lista_idempotente_por_nome(self):
        lista = [{"nome": "Ana Silva", "cargo": "Gerente", "setor": None, "presente": True}]
        nova, adicionou = participantes_ata_service.adicionar_na_lista(lista, "Ana Silva", "Gerente", None)
        assert adicionou is False
        assert len(nova) == 1

    def test_adicionar_na_lista_novo_marca_presente(self):
        nova, adicionou = participantes_ata_service.adicionar_na_lista(
            [], "Carlos Ferreira", "Coordenador", "Financeiro"
        )
        assert adicionou is True
        assert nova[0] == {
            "nome": "Carlos Ferreira",
            "cargo": "Coordenador",
            "setor": "Financeiro",
            "presente": True,
        }

    def test_eh_responsavel_no_quadro(self):
        quadro = [{"responsavel_id": "P002"}, {"responsavel_id": None}]
        assert participantes_ata_service.eh_responsavel_no_quadro(quadro, "P002") is True
        assert participantes_ata_service.eh_responsavel_no_quadro(quadro, "P001") is False
        assert participantes_ata_service.eh_responsavel_no_quadro(quadro, None) is False


# ─── Excluir ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_excluir_remove_dos_dois_lados(facilitador):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())

    res = await reunioes_router.excluir_participante_ata(
        id_reuniao="R123",
        body=ExcluirParticipanteAtaRequest(nome="Ana Silva"),
        current_user=CURRENT_USER,
        supabase=sb,
    )

    # json_ata (fonte do PDF) não mostra mais a pessoa
    nomes = [p["nome"] for p in sb.reunioes[0]["json_ata"]["participantes"]]
    assert "Ana Silva" not in nomes
    assert "Pedro Rezende" in nomes
    # roster (dirige ClickSign/Pendências) também perdeu o vínculo
    ids = {r["participante_id"] for r in sb.reuniao_participantes}
    assert ids == {"P001"}
    # resposta reflete lista + contador para a UI atualizar sem reload
    assert res["total"] == 1
    assert [p["nome"] for p in res["participantes"]] == ["Pedro Rezende"]


@pytest.mark.asyncio
async def test_excluir_responsavel_bloqueia_e_nao_altera_nada(facilitador):
    sb = _SupabaseMock(
        reunioes=[_reuniao(com_responsavel=True)],
        participantes=_cadastro(),
        reuniao_participantes=_roster(),
    )

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.excluir_participante_ata(
            id_reuniao="R123",
            body=ExcluirParticipanteAtaRequest(nome="Ana Silva"),
            current_user=CURRENT_USER,
            supabase=sb,
        )

    assert exc.value.status_code == 400
    assert "respons" in exc.value.detail.lower()
    # nada mudou: lista e roster intactos
    nomes = [p["nome"] for p in sb.reunioes[0]["json_ata"]["participantes"]]
    assert "Ana Silva" in nomes
    assert {r["participante_id"] for r in sb.reuniao_participantes} == {"P001", "P002"}


@pytest.mark.asyncio
async def test_excluir_nome_ausente_na_lista_retorna_404(facilitador):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.excluir_participante_ata(
            id_reuniao="R123",
            body=ExcluirParticipanteAtaRequest(nome="Fulano Inexistente"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_excluir_participante_so_no_json_ata_sem_vinculo(facilitador):
    """Nome que a IA listou mas nunca virou vínculo: some do json_ata, roster intacto."""
    ata = _json_ata()
    ata["participantes"].append({"nome": "Fantasma IA", "cargo": "", "setor": None, "presente": True})
    sb = _SupabaseMock(
        reunioes=[{"id_reuniao": "R123", "status_ata": "AGUARDANDO_VALIDACAO", "json_ata": ata}],
        participantes=_cadastro(),
        reuniao_participantes=_roster(),
    )

    await reunioes_router.excluir_participante_ata(
        id_reuniao="R123",
        body=ExcluirParticipanteAtaRequest(nome="Fantasma IA"),
        current_user=CURRENT_USER,
        supabase=sb,
    )

    nomes = [p["nome"] for p in sb.reunioes[0]["json_ata"]["participantes"]]
    assert "Fantasma IA" not in nomes
    assert {r["participante_id"] for r in sb.reuniao_participantes} == {"P001", "P002"}


@pytest.mark.asyncio
async def test_excluir_status_invalido_retorna_400(facilitador):
    sb = _SupabaseMock(
        reunioes=[_reuniao(status="APROVADA")], participantes=_cadastro(), reuniao_participantes=_roster()
    )

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.excluir_participante_ata(
            id_reuniao="R123",
            body=ExcluirParticipanteAtaRequest(nome="Ana Silva"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_excluir_gate_visibilidade_retorna_404(monkeypatch):
    async def _me(*_a, **_kw):
        return {"id": "P_ME", "access_profile": "regular"}

    async def _allowed(*_a, **_kw):
        return ["OUTRA_REUNIAO"]  # R123 não está na lista permitida

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _me)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _allowed)

    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.excluir_participante_ata(
            id_reuniao="R123",
            body=ExcluirParticipanteAtaRequest(nome="Ana Silva"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_excluir_secretaria_bloqueada_403(monkeypatch):
    async def _me(*_a, **_kw):
        return {"id": "P_SEC", "access_profile": "secretaria"}

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _me)

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.excluir_participante_ata(
            id_reuniao="R123",
            body=ExcluirParticipanteAtaRequest(nome="Ana Silva"),
            current_user=CURRENT_USER,
            supabase=_SupabaseMock(),
        )
    assert exc.value.status_code == 403


# ─── Adicionar ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_adicionar_grava_nos_dois_lados(facilitador):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())

    res = await reunioes_router.adicionar_participante_ata(
        id_reuniao="R123",
        body=AdicionarParticipanteAtaRequest(participante_id="P003"),
        current_user=CURRENT_USER,
        supabase=sb,
    )

    # json_ata ganha a entrada canônica do cadastro
    entrada = next(p for p in sb.reunioes[0]["json_ata"]["participantes"] if p["nome"] == "Carlos Ferreira")
    assert entrada["cargo"] == "Coordenador"
    assert entrada["presente"] is True
    # roster ganha o vínculo
    assert "P003" in {r["participante_id"] for r in sb.reuniao_participantes}
    assert res["total"] == 3


@pytest.mark.asyncio
async def test_adicionar_idempotente_sem_duplicar_vinculo(facilitador):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())

    for _ in range(2):
        await reunioes_router.adicionar_participante_ata(
            id_reuniao="R123",
            body=AdicionarParticipanteAtaRequest(participante_id="P003"),
            current_user=CURRENT_USER,
            supabase=sb,
        )

    # sem duplicar no json_ata
    nomes = [p["nome"] for p in sb.reunioes[0]["json_ata"]["participantes"]]
    assert nomes.count("Carlos Ferreira") == 1
    # sem duplicar o vínculo
    vinculos_p003 = [r for r in sb.reuniao_participantes if r["participante_id"] == "P003"]
    assert len(vinculos_p003) == 1


@pytest.mark.asyncio
async def test_adicionar_participante_inexistente_404(facilitador):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.adicionar_participante_ata(
            id_reuniao="R123",
            body=AdicionarParticipanteAtaRequest(participante_id="P999"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_adicionar_status_invalido_retorna_400(facilitador):
    sb = _SupabaseMock(
        reunioes=[_reuniao(status="APROVADA")], participantes=_cadastro(), reuniao_participantes=_roster()
    )

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.adicionar_participante_ata(
            id_reuniao="R123",
            body=AdicionarParticipanteAtaRequest(participante_id="P003"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_adicionar_gate_visibilidade_retorna_404(monkeypatch):
    async def _me(*_a, **_kw):
        return {"id": "P_ME", "access_profile": "regular"}

    async def _allowed(*_a, **_kw):
        return ["OUTRA_REUNIAO"]

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _me)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _allowed)

    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=_cadastro(), reuniao_participantes=_roster())
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.adicionar_participante_ata(
            id_reuniao="R123",
            body=AdicionarParticipanteAtaRequest(participante_id="P003"),
            current_user=CURRENT_USER,
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_adicionar_secretaria_bloqueada_403(monkeypatch):
    async def _me(*_a, **_kw):
        return {"id": "P_SEC", "access_profile": "secretaria"}

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _me)

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.adicionar_participante_ata(
            id_reuniao="R123",
            body=AdicionarParticipanteAtaRequest(participante_id="P003"),
            current_user=CURRENT_USER,
            supabase=_SupabaseMock(),
        )
    assert exc.value.status_code == 403
