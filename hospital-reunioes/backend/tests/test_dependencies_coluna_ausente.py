"""Backend novo em banco velho não derruba o app inteiro (issue #375, item 14).

`perfil_ouvidoria` entrou em `_PARTICIPANTE_FULL_FIELDS`, que TODA rota
autenticada seleciona. Num ambiente onde a migration 064 ainda não rodou
(ambiente novo, rollback de banco, ordem invertida de deploy), o PostgREST
recusa o select inteiro com 42703 e todas as rotas autenticadas passam a
responder 500, e não só as da Ouvidoria.

O fallback é por COLUNA e deixa rastro: sem o aviso no log, um ambiente
rodaria meses com a Ouvidoria invisível e ninguém saberia por quê.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_participante_for_user  # noqa: E402

USUARIO = {"id": "auth-1", "email": "marta@hsm.br"}

LINHA = {
    "id": "P10",
    "nome_completo": "Marta Ouvidora",
    "email": "marta@hsm.br",
    "auth_user_id": "auth-1",
    "access_profile": "regular",
}


class _TabelaFake:
    def __init__(self, banco: _SupabaseFake):
        self._banco = banco
        self._colunas = ""
        self._filters: dict = {}

    def select(self, colunas: str = "*", *_a, **_kw):
        self._colunas = colunas
        return self

    def update(self, _payload):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def execute(self):
        self._banco.selects.append(self._colunas)
        if self._banco.coluna_ausente and self._banco.coluna_ausente in self._colunas:
            raise APIError(
                {
                    "code": "42703",
                    "message": f"column participantes.{self._banco.coluna_ausente} does not exist",
                }
            )
        casadas = [r for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
        return type("R", (), {"data": [dict(r) for r in casadas]})()


class _SupabaseFake:
    def __init__(self, coluna_ausente: str | None = None, rows: list[dict] | None = None):
        self.coluna_ausente = coluna_ausente
        self.rows = rows if rows is not None else [dict(LINHA)]
        self.selects: list[str] = []

    def table(self, _nome: str):
        return _TabelaFake(self)


@pytest.fixture(autouse=True)
def _sem_cache_entre_testes():
    _participante_ctx.set(None)
    yield
    _participante_ctx.set(None)


class TestColunaQueAindaNaoExiste:
    @pytest.mark.asyncio
    async def test_banco_sem_perfil_ouvidoria_ainda_resolve_o_participante(self, caplog):
        supabase = _SupabaseFake(coluna_ausente="perfil_ouvidoria")

        with caplog.at_level(logging.WARNING):
            me = await get_participante_for_user(USUARIO, supabase)

        assert me is not None
        assert me["id"] == "P10"
        # Sem a coluna, ninguém tem perfil da Ouvidoria: o gate fecha, e é o
        # certo. O que não pode é derrubar as outras rotas junto.
        assert me.get("perfil_ouvidoria") is None
        assert "perfil_ouvidoria" in caplog.text

    @pytest.mark.asyncio
    async def test_a_segunda_tentativa_pede_menos_colunas(self):
        """A prova de que o fallback é por COLUNA, e não um `select *` que
        traria de volta tudo o que a tupla existe para não trazer."""
        supabase = _SupabaseFake(coluna_ausente="perfil_ouvidoria")

        await get_participante_for_user(USUARIO, supabase)

        assert len(supabase.selects) == 2
        assert "perfil_ouvidoria" in supabase.selects[0]
        assert "perfil_ouvidoria" not in supabase.selects[1]
        assert "*" not in supabase.selects[1]
        # E o resto da tupla continua lá: o fallback tira uma coluna, não a lista.
        assert "access_profile" in supabase.selects[1]

    @pytest.mark.asyncio
    async def test_com_a_coluna_no_lugar_nao_ha_segunda_tentativa(self):
        """O caminho normal não paga pelo fallback."""
        supabase = _SupabaseFake()

        me = await get_participante_for_user(USUARIO, supabase)

        assert me is not None
        assert len(supabase.selects) == 1

    @pytest.mark.asyncio
    async def test_erro_que_nao_e_coluna_ausente_continua_subindo(self):
        """Fallback largo demais esconderia o banco fora do ar: só 42703."""
        supabase = _SupabaseFake()

        def _estoura(_nome):
            raise APIError({"code": "42P01", "message": 'relation "participantes" does not exist'})

        supabase.table = _estoura

        with pytest.raises(APIError):
            await get_participante_for_user(USUARIO, supabase)
