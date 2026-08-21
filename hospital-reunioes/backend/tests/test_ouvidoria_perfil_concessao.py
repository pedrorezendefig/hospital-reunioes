"""Concessao do perfil de Ouvidoria pela tela de Usuarios (issue #320).

Os perfis `ouvidor` e `diretoria_executiva` nascem nesta fatia (ADR 0034,
decisao 8). Quem concede e o Super Admin de Reunioes, pela mesma tela onde ja
concede o perfil POP (precedente do ADR 0014): sem esse caminho, ninguem abre
o Dossie sem SQL manual em producao.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers.admin import usuarios as usuarios_router  # noqa: E402

SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin", "email": "p@hsm.br"}


@dataclass
class _Result:
    data: list


class _Query:
    def __init__(self, rows: list[dict]):
        self.rows = rows
        self._filtros: dict = {}
        self._update: dict | None = None
        self._insert: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def update(self, payload):
        self._update = payload
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def eq(self, col, val):
        self._filtros[col] = val
        return self

    def order(self, *_a, **_kw):
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        if self._insert is not None:
            self.rows.append(dict(self._insert))
            return _Result([dict(self._insert)])
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filtros.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        return _Result([dict(r) for r in casadas])


class _Supabase:
    def __init__(self, participantes: list[dict]):
        self.tabelas = {"participantes": participantes, "audit_log": []}

    def table(self, nome: str):
        return _Query(self.tabelas.setdefault(nome, []))


def _pessoa(**overrides) -> dict:
    row = {
        "id": "P10",
        "nome_completo": "Marta Ouvidora",
        "email": "marta@hsm.br",
        "auth_user_id": "auth-marta",
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "ativo": True,
    }
    row.update(overrides)
    return row


def _pedido(perfil, motivo="Ouvidora do hospital."):
    from app.models.admin_schemas import PerfilOuvidoriaUpdate

    return PerfilOuvidoriaUpdate(perfil_ouvidoria=perfil, reason=motivo)


class _RequestFalso:
    client = None
    headers: dict = {}


@pytest.mark.asyncio
async def test_super_admin_concede_o_perfil_de_ouvidor():
    supabase = _Supabase([_pessoa()])

    resposta = await usuarios_router.definir_perfil_ouvidoria(
        participante_id="P10",
        body=_pedido("ouvidor"),
        request=_RequestFalso(),
        actor=SUPER_ADMIN,
        supabase=supabase,
    )

    assert resposta.perfil_ouvidoria == "ouvidor"
    assert supabase.tabelas["participantes"][0]["perfil_ouvidoria"] == "ouvidor"


@pytest.mark.asyncio
async def test_revogar_o_perfil_limpa_o_acesso():
    supabase = _Supabase([_pessoa(perfil_ouvidoria="ouvidor")])

    await usuarios_router.definir_perfil_ouvidoria(
        participante_id="P10",
        body=_pedido(None, motivo="Saiu da funcao."),
        request=_RequestFalso(),
        actor=SUPER_ADMIN,
        supabase=supabase,
    )

    assert supabase.tabelas["participantes"][0]["perfil_ouvidoria"] is None


@pytest.mark.asyncio
async def test_concessao_e_revogacao_ficam_no_audit_log():
    """Quem pode ler denuncia e decisao rastreavel: a concessao vira registro."""
    supabase = _Supabase([_pessoa()])

    await usuarios_router.definir_perfil_ouvidoria(
        participante_id="P10",
        body=_pedido("diretoria_executiva"),
        request=_RequestFalso(),
        actor=SUPER_ADMIN,
        supabase=supabase,
    )

    registros = supabase.tabelas["audit_log"]
    assert len(registros) == 1
    assert registros[0]["target_id"] == "P10"
    assert "OUVIDORIA" in registros[0]["action"]
    assert registros[0]["metadata"]["perfil_depois"] == "diretoria_executiva"


@pytest.mark.asyncio
async def test_perfil_invalido_e_recusado():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        _pedido("super_ouvidor")


@pytest.mark.asyncio
async def test_pessoa_inexistente_devolve_404():
    supabase = _Supabase([])

    with pytest.raises(HTTPException) as erro:
        await usuarios_router.definir_perfil_ouvidoria(
            participante_id="P99",
            body=_pedido("ouvidor"),
            request=_RequestFalso(),
            actor=SUPER_ADMIN,
            supabase=supabase,
        )

    assert erro.value.status_code == 404


def test_listagem_de_usuarios_mostra_o_perfil_de_ouvidoria():
    """Sem o campo na resposta, o modal de edicao abriria sempre em 'Sem
    acesso' e revogaria o perfil sem querer no primeiro save."""
    from app.models.admin_schemas import AdminUsuarioResponse

    assert "perfil_ouvidoria" in AdminUsuarioResponse.model_fields
