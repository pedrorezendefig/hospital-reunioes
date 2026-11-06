"""O sino marca avisos, mas o painel abre vazio (issue #1430).

O contador (`GET /notificacoes/count`) só conta linhas; a lista
(`GET /notificacoes`) valida cada linha no `NotificacaoResponse`, cujo `tipo`
é o enum `TipoNotificacao`. O banco aceita mais tipos que o enum (ACEITE_INTERNO
desde a 060, CONTAS_MEDICAS desde a 116): um aviso desses na janela da lista
derrubava a rota com 500, a tela engolia o erro e dizia "Sem notificações" com
o sino marcando 3.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.models.schemas import TipoNotificacao  # noqa: E402
from app.routers import notificacoes as notificacoes_router  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
DESTINATARIO = "p-1"


def _tipos_do_check_mais_recente() -> list[str]:
    """Os tipos do último CHECK `notificacoes_tipo_check` gravado nas migrations."""
    ultimo: str | None = None
    for arquivo in sorted(MIGRATIONS.glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        for bloco in re.findall(
            r"ADD CONSTRAINT notificacoes_tipo_check\s+CHECK\s*\(\s*tipo IN\s*\((.*?)\)\s*\)",
            texto,
            flags=re.S,
        ):
            ultimo = bloco
    assert ultimo, "nenhum CHECK notificacoes_tipo_check encontrado nas migrations"
    return re.findall(r"'([A-Z_]+)'", ultimo)


class _Consulta:
    def __init__(self, linhas: list[dict[str, Any]]):
        self._linhas = linhas
        self._filtros: list[tuple[str, Any]] = []
        self._contar = False

    def select(self, *_args, count: str | None = None, **_kw):
        self._contar = count is not None
        return self

    def eq(self, coluna: str, valor: Any):
        self._filtros.append((coluna, valor))
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def execute(self):
        linhas = [linha for linha in self._linhas if all(linha.get(c) == v for c, v in self._filtros)]
        resultado = type("R", (), {})()
        resultado.data = linhas
        resultado.count = len(linhas) if self._contar else None
        return resultado


class _Banco:
    def __init__(self, linhas: list[dict[str, Any]]):
        self.linhas = linhas

    def table(self, nome: str):
        assert nome == "notificacoes"
        return _Consulta(self.linhas)


def _aviso(i: int, tipo: str, referencia: str | None) -> dict[str, Any]:
    return {
        "id": f"n-{i}",
        "destinatario_id": DESTINATARIO,
        "tipo": tipo,
        "titulo": f"Aviso {i}",
        "mensagem": None,
        "referencia_id": referencia,
        "lida": False,
        "created_at": "2026-11-05T12:00:00+00:00",
    }


def _cliente(banco: _Banco, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _participante(*_a, **_kw):
        return {"id": DESTINATARIO}

    monkeypatch.setattr(notificacoes_router, "get_participante_for_user", _participante)
    app = FastAPI()
    app.include_router(notificacoes_router.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"id": "auth-1", "email": "a@b.c"}
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def test_enum_cobre_todos_os_tipos_que_o_banco_aceita():
    tipos_do_banco = _tipos_do_check_mais_recente()
    assert "CONTAS_MEDICAS" in tipos_do_banco
    faltando = sorted(set(tipos_do_banco) - {t.value for t in TipoNotificacao})
    assert faltando == []


def test_painel_lista_a_mesma_quantidade_que_o_sino_conta(monkeypatch):
    banco = _Banco(
        [
            _aviso(1, "CONTAS_MEDICAS", "envio-1"),
            _aviso(2, "ACEITE_INTERNO", "reuniao-1"),
            _aviso(3, "MENCAO", "pendencia-1"),
        ]
    )
    cliente = _cliente(banco, monkeypatch)

    contagem = cliente.get("/api/notificacoes/count")
    lista = cliente.get("/api/notificacoes", params={"limit": 20})

    assert contagem.status_code == 200
    assert contagem.json()["nao_lidas"] == 3
    assert lista.status_code == 200
    assert [n["tipo"] for n in lista.json()] == ["CONTAS_MEDICAS", "ACEITE_INTERNO", "MENCAO"]
