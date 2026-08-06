"""Testes de menções em comentários de Pendências (issue #270).

Cobre:
- Automenção gera notificação MENCAO para o próprio autor.
- Menção restrita a quem enxerga a Pendência (roster + co-responsável + super admin).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.schemas import ComentarioCreate  # noqa: E402
from app.routers import comentarios as comentarios_router  # noqa: E402

# ─── Mocks ────────────────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _FakeTable:
    """Tabela em memória com o subconjunto de query builder usado nos routers."""

    def __init__(self, rows: list[dict], inserts_sink: list | None = None):
        self._rows = rows
        self._inserts_sink = inserts_sink if inserts_sink is not None else rows
        self._filters_eq: dict = {}
        self._pending_insert: dict | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, val):
        self._filters_eq[col] = val
        return self

    def insert(self, row):
        self._pending_insert = row
        return self

    def execute(self):
        if self._pending_insert is not None:
            self._inserts_sink.append(self._pending_insert)
            return _Result([self._pending_insert])
        rows = [r for r in self._rows if all(r.get(k) == v for k, v in self._filters_eq.items())]
        return _Result(rows)


@dataclass
class _Sb:
    pendencias: list = field(default_factory=list)
    participantes: list = field(default_factory=list)
    reuniao_participantes: list = field(default_factory=list)
    comentarios: list = field(default_factory=list)
    notificacoes: list = field(default_factory=list)

    def table(self, name):
        if name == "pendencias":
            return _FakeTable(self.pendencias)
        if name == "participantes":
            return _FakeTable(self.participantes)
        if name == "reuniao_participantes":
            return _FakeTable(self.reuniao_participantes)
        if name == "comentarios_pendencias":
            return _FakeTable([], inserts_sink=self.comentarios)
        if name == "notificacoes":
            return _FakeTable([], inserts_sink=self.notificacoes)
        raise AssertionError(f"Tabela inesperada: {name}")


PEDRO = {"id": "P01", "nome_completo": "Pedro Rezende", "auth_user_id": "auth-p01"}
CURRENT_USER = {"id": "auth-p01", "email": "pedro@ex.com"}


def _sb_com_pendencia() -> _Sb:
    return _Sb(
        pendencias=[
            {
                "id_acao": "A001",
                "descricao_acao": "Revisar escala",
                "responsavel_id": "P99",
                "id_reuniao": "RD_001",
                "co_responsavel_id": None,
            }
        ],
        participantes=[dict(PEDRO)],
        reuniao_participantes=[{"id_reuniao": "RD_001", "participante_id": "P01"}],
    )


def _patch_deps(monkeypatch, autor: dict, allowed: list[str] | None):
    async def _fake_participante(_user, _sb, fields=None):
        return dict(autor)

    async def _fake_allowed(_user, _sb):
        return allowed

    monkeypatch.setattr(comentarios_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(comentarios_router, "get_allowed_reuniao_ids", _fake_allowed)


# ─── Testes ───────────────────────────────────────────────────────────────────


class TestAutomencao:
    @pytest.mark.asyncio
    async def test_automencao_notifica_o_proprio_autor(self, monkeypatch):
        sb = _sb_com_pendencia()
        _patch_deps(monkeypatch, autor=PEDRO, allowed=None)

        await comentarios_router.create_comentario(
            id_acao="A001",
            req=ComentarioCreate(conteudo="Lembrete: @Pedro Rezende conferir amanhã"),
            current_user=CURRENT_USER,
            supabase=sb,
        )

        mencoes = [n for n in sb.notificacoes if n["tipo"] == "MENCAO"]
        assert len(mencoes) == 1
        assert mencoes[0]["destinatario_id"] == "P01"
        assert mencoes[0]["referencia_id"] == "A001"


CAROLINE = {"id": "C01", "nome_completo": "Caroline Souza", "auth_user_id": "auth-c01"}


class TestMencaoRestritaAQuemEnxerga:
    def _sb_com_roster(self) -> _Sb:
        sb = _sb_com_pendencia()
        sb.participantes = [
            {"id": "C01", "nome_completo": "Caroline Souza", "is_super_admin": False},
            {"id": "Z01", "nome_completo": "Zé Fora", "is_super_admin": False},
            {"id": "D01", "nome_completo": "Diretor Geral", "is_super_admin": True},
        ]
        sb.reuniao_participantes = [{"id_reuniao": "RD_001", "participante_id": "C01"}]
        return sb

    @pytest.mark.asyncio
    async def test_mencao_a_quem_nao_enxerga_a_pendencia_nao_notifica(self, monkeypatch):
        sb = self._sb_com_roster()
        _patch_deps(monkeypatch, autor=CAROLINE, allowed=["RD_001"])

        await comentarios_router.create_comentario(
            id_acao="A001",
            req=ComentarioCreate(conteudo="@Zé Fora dá uma olhada"),
            current_user={"id": "auth-c01", "email": "caroline@ex.com"},
            supabase=sb,
        )

        assert [n for n in sb.notificacoes if n["tipo"] == "MENCAO"] == []
        assert sb.comentarios[0]["mencoes"] == []

    @pytest.mark.asyncio
    async def test_super_admin_fora_do_roster_e_mencionavel(self, monkeypatch):
        sb = self._sb_com_roster()
        _patch_deps(monkeypatch, autor=CAROLINE, allowed=["RD_001"])

        await comentarios_router.create_comentario(
            id_acao="A001",
            req=ComentarioCreate(conteudo="@Diretor Geral para ciência"),
            current_user={"id": "auth-c01", "email": "caroline@ex.com"},
            supabase=sb,
        )

        mencoes = [n for n in sb.notificacoes if n["tipo"] == "MENCAO"]
        assert len(mencoes) == 1
        assert mencoes[0]["destinatario_id"] == "D01"

    @pytest.mark.asyncio
    async def test_endpoint_mencionaveis_lista_so_quem_enxerga(self, monkeypatch):
        sb = self._sb_com_roster()
        _patch_deps(monkeypatch, autor=CAROLINE, allowed=["RD_001"])

        resultado = await comentarios_router.listar_mencionaveis(
            id_acao="A001",
            current_user={"id": "auth-c01", "email": "caroline@ex.com"},
            supabase=sb,
        )

        ids = {p["id"] for p in resultado}
        assert ids == {"C01", "D01"}


class TestTokenOrfao:
    @pytest.mark.asyncio
    async def test_token_orfao_recebe_404_em_pendencia_sem_corresponsavel(self, monkeypatch):
        """Órfão (sem participante vinculado): allowed=[] e my_id=None não podem desarmar o gate."""
        sb = _sb_com_pendencia()

        async def _sem_participante(_user, _sb, fields=None):
            return None

        async def _allowed_vazio(_user, _sb):
            return []

        monkeypatch.setattr(comentarios_router, "get_participante_for_user", _sem_participante)
        monkeypatch.setattr(comentarios_router, "get_allowed_reuniao_ids", _allowed_vazio)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await comentarios_router.listar_mencionaveis(
                id_acao="A001",
                current_user={"id": "auth-orfao", "email": "orfao@ex.com"},
                supabase=sb,
            )
        assert exc.value.status_code == 404
