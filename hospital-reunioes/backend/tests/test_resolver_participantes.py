"""Testes do endpoint POST /reunioes/{id}/resolver-participantes.

Cobre:
- Validação Pydantic dos schemas ResolverNaoReconhecidoItem e NovoExternoDados.
- Vincular participante interno existente (ação nova da feature).
- Vincular retorna 404/400 quando participante inexistente ou inativo.
- Cadastrar externo sem email (novo, alinhado à migration 026).
- Cadastrar externo com email que já existe reutiliza o id.
- Ignorar só remove do JSONB sem criar nada.
- Mix das 3 ações em uma única chamada (atomicidade do contrato).
- 400 quando reunião não está em AGUARDANDO_RESOLUCAO.
- Limite defensivo de 200 resoluções.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import (  # noqa: E402
    NovoExternoDados,
    ResolverNaoReconhecidoItem,
    ResolverParticipantesRequest,
)
from app.routers import reunioes as reunioes_router  # noqa: E402

# ─── Mock Supabase suportando as operações do endpoint ──────────────────────


@dataclass
class _Result:
    data: Any


class _Query:
    """Mock que suporta select().eq()/in_().execute() + update().eq().execute()
    + upsert([...], on_conflict=...).execute()."""

    def __init__(self, rows_ref: list):
        self._rows = rows_ref
        self._op: str | None = None
        self._payload: Any = None
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
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def eq(self, col, val):
        self._filters_eq.append((col, val))
        return self

    def in_(self, col, vals):
        self._filters_in.append((col, list(vals)))
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a):
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._op in ("upsert", "insert"):
            if isinstance(self._payload, list):
                self._rows.extend(self._payload)
                return _Result(data=list(self._payload))
            self._rows.append(self._payload)
            return _Result(data=[self._payload])

        matched = list(self._rows)
        for col, val in self._filters_eq:
            matched = [r for r in matched if r.get(col) == val]
        for col, vals in self._filters_in:
            matched = [r for r in matched if r.get(col) in vals]

        if self._op == "update":
            for r in matched:
                r.update(self._payload or {})
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


def _reuniao(status: str = "AGUARDANDO_RESOLUCAO") -> dict:
    return {
        "id_reuniao": "R123",
        "status_ata": status,
        "tipo": "diretoria",
        "participantes_nao_reconhecidos": [
            {"nome": "João Silva", "cargo": "Analista", "setor": "TI"},
        ],
    }


def _interno(pid: str, nome: str = "Nome", ativo: bool = True) -> dict:
    return {
        "id": pid,
        "nome_completo": nome,
        "email": f"{pid.lower()}@ex.com",
        "ativo": ativo,
        "is_externo": False,
    }


# ─── Schema validation ──────────────────────────────────────────────────────


class TestResolverNaoReconhecidoItem:
    def test_vincular_exige_participante_id(self):
        with pytest.raises(ValidationError) as exc:
            ResolverNaoReconhecidoItem(nome_identificado="João", acao="vincular")
        assert "participante_id" in str(exc.value)

    def test_cadastrar_externo_exige_novo_externo(self):
        with pytest.raises(ValidationError) as exc:
            ResolverNaoReconhecidoItem(nome_identificado="João", acao="cadastrar_externo")
        assert "novo_externo" in str(exc.value)

    def test_ignorar_nao_exige_extras(self):
        item = ResolverNaoReconhecidoItem(nome_identificado="Fantasma", acao="ignorar")
        assert item.acao == "ignorar"
        assert item.participante_id is None
        assert item.novo_externo is None

    def test_novo_externo_aceita_email_nulo(self):
        dados = NovoExternoDados(nome_completo="João Silva")
        assert dados.email is None
        assert dados.cargo is None


# ─── Endpoint behavior ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_vincular_interno_existente_adiciona_em_reuniao_participantes(monkeypatch):
    sb = _SupabaseMock(
        reunioes=[_reuniao()],
        participantes=[_interno("P042", "João Carlos Silva")],
    )
    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="vincular",
                participante_id="P042",
            )
        ]
    )

    res = await reunioes_router.resolver_participantes(
        id_reuniao="R123",
        body=body,
        background_tasks=BackgroundTasks(),
        current_user={"id": "test-uid", "email": "test@example.com"},
        supabase=sb,
    )

    assert res["vinculados"] == 1
    assert res["cadastrados"] == 0
    assert res["ignorados"] == 0
    # UPSERT cria o link
    assert len(sb.reuniao_participantes) == 1
    assert sb.reuniao_participantes[0]["participante_id"] == "P042"
    # JSONB limpo
    assert sb.reunioes[0]["participantes_nao_reconhecidos"] == []


@pytest.mark.asyncio
async def test_vincular_participante_inexistente_retorna_404():
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=[])
    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="vincular",
                participante_id="P999",
            )
        ]
    )
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.resolver_participantes(
            id_reuniao="R123",
            body=body,
            background_tasks=BackgroundTasks(),
            current_user={"id": "test-uid", "email": "test@example.com"},
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_vincular_participante_inativo_retorna_400():
    sb = _SupabaseMock(
        reunioes=[_reuniao()],
        participantes=[_interno("P042", ativo=False)],
    )
    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="vincular",
                participante_id="P042",
            )
        ]
    )
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.resolver_participantes(
            id_reuniao="R123",
            body=body,
            background_tasks=BackgroundTasks(),
            current_user={"id": "test-uid", "email": "test@example.com"},
            supabase=sb,
        )
    assert exc.value.status_code == 400
    assert "inativo" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_cadastrar_externo_sem_email_chama_provision(monkeypatch):
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=[])
    novo = {
        "id": "P100",
        "nome_completo": "Maria Externa",
        "email": None,
        "ativo": True,
        "is_externo": True,
    }

    def fake_provision(supabase, dados, role):  # noqa: ARG001
        supabase.participantes.append(novo)
        return (novo, None)

    monkeypatch.setattr(
        "app.services.auth_provisioning.provision_with_compensation",
        fake_provision,
    )

    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="cadastrar_externo",
                novo_externo=NovoExternoDados(nome_completo="Maria Externa"),
            )
        ]
    )

    res = await reunioes_router.resolver_participantes(
        id_reuniao="R123",
        body=body,
        background_tasks=BackgroundTasks(),
        current_user={"id": "test-uid", "email": "test@example.com"},
        supabase=sb,
    )

    assert res["cadastrados"] == 1
    assert any(r["participante_id"] == "P100" for r in sb.reuniao_participantes)


@pytest.mark.asyncio
async def test_cadastrar_externo_email_ja_existente_reutiliza_id():
    sb = _SupabaseMock(
        reunioes=[_reuniao()],
        participantes=[
            {
                "id": "P050",
                "nome_completo": "Carlos Externo",
                "email": "carlos@ex.com",
                "ativo": True,
                "is_externo": True,
            }
        ],
    )
    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="cadastrar_externo",
                novo_externo=NovoExternoDados(
                    nome_completo="Carlos Externo",
                    email="carlos@ex.com",
                ),
            )
        ]
    )

    res = await reunioes_router.resolver_participantes(
        id_reuniao="R123",
        body=body,
        background_tasks=BackgroundTasks(),
        current_user={"id": "test-uid", "email": "test@example.com"},
        supabase=sb,
    )

    assert res["cadastrados"] == 1
    # Reaproveita id existente — não cria novo participante
    assert len(sb.participantes) == 1
    assert sb.reuniao_participantes[0]["participante_id"] == "P050"


@pytest.mark.asyncio
async def test_ignorar_nao_cria_nada_mas_limpa_jsonb():
    sb = _SupabaseMock(reunioes=[_reuniao()], participantes=[])
    body = ResolverParticipantesRequest(
        resolucoes=[ResolverNaoReconhecidoItem(nome_identificado="João Silva", acao="ignorar")]
    )

    res = await reunioes_router.resolver_participantes(
        id_reuniao="R123",
        body=body,
        background_tasks=BackgroundTasks(),
        current_user={"id": "test-uid", "email": "test@example.com"},
        supabase=sb,
    )

    assert res["ignorados"] == 1
    assert sb.reuniao_participantes == []
    assert sb.participantes == []
    assert sb.reunioes[0]["participantes_nao_reconhecidos"] == []


@pytest.mark.asyncio
async def test_mix_tres_acoes_em_uma_chamada(monkeypatch):
    sb = _SupabaseMock(
        reunioes=[_reuniao()],
        participantes=[_interno("P042", "João Carlos Silva")],
    )
    novo = {
        "id": "P100",
        "nome_completo": "Beltrano",
        "email": None,
        "ativo": True,
        "is_externo": True,
    }
    monkeypatch.setattr(
        "app.services.auth_provisioning.provision_with_compensation",
        lambda sb_, dados, role: sb_.participantes.append(novo) or (novo, None),
    )

    body = ResolverParticipantesRequest(
        resolucoes=[
            ResolverNaoReconhecidoItem(
                nome_identificado="João Silva",
                acao="vincular",
                participante_id="P042",
            ),
            ResolverNaoReconhecidoItem(
                nome_identificado="Beltrano X",
                acao="cadastrar_externo",
                novo_externo=NovoExternoDados(nome_completo="Beltrano"),
            ),
            ResolverNaoReconhecidoItem(nome_identificado="Fantasma", acao="ignorar"),
        ]
    )

    res = await reunioes_router.resolver_participantes(
        id_reuniao="R123",
        body=body,
        background_tasks=BackgroundTasks(),
        current_user={"id": "test-uid", "email": "test@example.com"},
        supabase=sb,
    )

    assert res["vinculados"] == 1
    assert res["cadastrados"] == 1
    assert res["ignorados"] == 1
    ids_linkados = {r["participante_id"] for r in sb.reuniao_participantes}
    assert ids_linkados == {"P042", "P100"}
    assert sb.reunioes[0]["participantes_nao_reconhecidos"] == []


@pytest.mark.asyncio
async def test_400_quando_status_nao_e_aguardando_resolucao():
    sb = _SupabaseMock(reunioes=[_reuniao(status="AGUARDANDO_VALIDACAO")])
    body = ResolverParticipantesRequest(resolucoes=[])
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.resolver_participantes(
            id_reuniao="R123",
            body=body,
            background_tasks=BackgroundTasks(),
            current_user={"id": "test-uid", "email": "test@example.com"},
            supabase=sb,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_404_quando_reuniao_nao_encontrada():
    sb = _SupabaseMock(reunioes=[])
    body = ResolverParticipantesRequest(resolucoes=[])
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.resolver_participantes(
            id_reuniao="R-INEXISTENTE",
            body=body,
            background_tasks=BackgroundTasks(),
            current_user={"id": "test-uid", "email": "test@example.com"},
            supabase=sb,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_400_quando_excede_limite_de_200():
    sb = _SupabaseMock(reunioes=[_reuniao()])
    body = ResolverParticipantesRequest(
        resolucoes=[ResolverNaoReconhecidoItem(nome_identificado=f"n{i}", acao="ignorar") for i in range(201)]
    )
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.resolver_participantes(
            id_reuniao="R123",
            body=body,
            background_tasks=BackgroundTasks(),
            current_user={"id": "test-uid", "email": "test@example.com"},
            supabase=sb,
        )
    assert exc.value.status_code == 400
