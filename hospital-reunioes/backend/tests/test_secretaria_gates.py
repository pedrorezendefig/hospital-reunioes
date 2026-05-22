"""Testes dos gates 403 que bloqueiam secretária em endpoints de ata/pendência/comentário.

Garante que a expansão do papel secretária (visão global de calendário) não vaza
acesso a conteúdo de ata via canais paralelos: endpoints diretos, GET de reunião
com `json_ata`, ou endpoints de comentário/pendência.

Mocka `get_participante_for_user` no nível do router pra retornar dict com
`access_profile = "secretaria"` e confirma que o gate dispara antes da query.

Também valida o caso degenerado de `me=None` (token órfão pós-delete) — não
deve passar pelo gate (mas também não deve crashear).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import BackgroundTasks, HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import comentarios as comentarios_router  # noqa: E402
from app.routers import pendencias as pendencias_router  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402

CURRENT_USER = {"id": "auth-uid-1", "email": "secretaria@hospital.com"}


class _NoopSupabase:
    """Mock que nunca chega a ser usado — todos os gates devem disparar antes."""

    def table(self, name: str):
        raise AssertionError(f"Gate 403 deveria ter disparado antes de qualquer query. Tentou usar table {name!r}.")


@pytest.fixture
def secretaria(monkeypatch):
    """Patch `get_participante_for_user` em todos os routers pra retornar secretária."""
    me_dict = {"id": "P_SEC", "access_profile": "secretaria"}

    async def _fake(*_a, **_kw):
        return me_dict

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _fake)
    monkeypatch.setattr(pendencias_router, "get_participante_for_user", _fake)
    monkeypatch.setattr(comentarios_router, "get_participante_for_user", _fake)
    return me_dict


# ─── Routers de ata em reunioes.py ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_secretaria_403_em_pular_resolucao(secretaria):
    with pytest.raises(HTTPException) as exc:
        await reunioes_router.pular_resolucao_participantes(
            id_reuniao="R1",
            background_tasks=BackgroundTasks(),
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_secretaria_403_em_patch_quadro_atribuicoes(secretaria):
    from app.models.schemas import QuadroAtribuicaoUpdate

    with pytest.raises(HTTPException) as exc:
        await reunioes_router.patch_quadro_atribuicao(
            id_reuniao="R1",
            index=0,
            body=QuadroAtribuicaoUpdate(responsavel="x"),
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


# ─── Routers de pendência ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secretaria_403_em_list_pendencias(secretaria):
    from starlette.responses import Response

    with pytest.raises(HTTPException) as exc:
        await pendencias_router.list_pendencias(
            response=Response(),
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_secretaria_403_em_get_pendencia(secretaria):
    with pytest.raises(HTTPException) as exc:
        await pendencias_router.get_pendencia(
            id_acao="A1",
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_secretaria_403_em_stats_pendencias(secretaria):
    with pytest.raises(HTTPException) as exc:
        await pendencias_router.get_pendencias_stats(
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


# ─── Routers de comentário ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secretaria_403_em_list_comentarios(secretaria):
    with pytest.raises(HTTPException) as exc:
        await comentarios_router.list_comentarios(
            id_acao="A1",
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_secretaria_403_em_create_comentario(secretaria):
    from app.models.schemas import ComentarioCreate

    with pytest.raises(HTTPException) as exc:
        await comentarios_router.create_comentario(
            id_acao="A1",
            req=ComentarioCreate(conteudo="oi"),
            current_user=CURRENT_USER,
            supabase=_NoopSupabase(),
        )
    assert exc.value.status_code == 403


# ─── Edge case: me=None (token órfão pós-delete) ────────────────────────────


@pytest.mark.asyncio
async def test_me_none_nao_passa_pelo_gate_de_secretaria(monkeypatch):
    """Se `get_participante_for_user` retorna None (participante deletado mas JWT
    ainda válido), `is_secretaria(None)` é False — o gate NÃO dispara. Outro
    check (participante inexistente) precisa interceptar mais embaixo.
    Este teste documenta o comportamento atual.
    """
    from app.dependencies import is_secretaria

    assert is_secretaria(None) is False
    assert is_secretaria({}) is False
    assert is_secretaria({"access_profile": "regular"}) is False
    assert is_secretaria({"access_profile": "secretaria"}) is True
    assert is_secretaria({"access_profile": "super_admin"}) is False
