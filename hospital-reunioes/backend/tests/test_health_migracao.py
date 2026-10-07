"""O número da última migration aplicada no `/api/health` (issue #969).

Toda migration termina gravando o próprio número em `migracoes_aplicadas`, e a
subida (`fechar_onda.py`) só mergeia um lote com migration depois que o health
devolve esse número. A costura é a rota de verdade, montada num app mínimo com
o mesmo prefixo, e o banco é um dublê que se comporta como o PostgREST: ordena,
limita e responde `42P01` quando a tabela ainda não existe (a migration 114
ainda não foi colada no Studio).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.routers import health  # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]


class _Consulta:
    def __init__(self, tabelas: dict[str, list[dict]], nome: str):
        self._tabelas = tabelas
        self._nome = nome
        self._ordem: tuple[str, bool] | None = None
        self._limite: int | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def execute(self):
        if self._nome not in self._tabelas:
            raise APIError(
                {
                    "code": "42P01",
                    "message": f'relation "public.{self._nome}" does not exist',
                }
            )
        linhas = list(self._tabelas[self._nome])
        if self._ordem:
            coluna, desc = self._ordem
            linhas.sort(key=lambda linha: linha[coluna], reverse=desc)
        if self._limite is not None:
            linhas = linhas[: self._limite]
        return SimpleNamespace(data=linhas)


class _BancoFalso:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome):
        return _Consulta(self.tabelas, nome)


def _health(monkeypatch, tabelas: dict[str, list[dict]]):
    monkeypatch.setattr(health, "get_supabase_client", lambda: _BancoFalso(tabelas))
    app = FastAPI()
    app.include_router(health.router, prefix=settings.api_prefix)
    return TestClient(app).get("/api/health")


PARTICIPANTES = {"participantes": [{"id": 1}]}


def test_health_devolve_o_maior_numero_de_migration_aplicada(monkeypatch):
    resp = _health(
        monkeypatch,
        {
            **PARTICIPANTES,
            "migracoes_aplicadas": [{"numero": 114}, {"numero": 116}, {"numero": 115}],
        },
    )

    assert resp.status_code == 200
    assert resp.json()["migracao"] == 116
    assert resp.json()["status"] == "healthy"


def test_health_sem_a_tabela_ainda_responde_healthy_com_migracao_nula(monkeypatch):
    """Antes de a 114 ser colada no Studio a tabela não existe: o health não
    pode cair por isso, senão o deploy desta própria fatia daria rollback."""
    resp = _health(monkeypatch, PARTICIPANTES)

    assert resp.status_code == 200
    corpo = resp.json()
    assert corpo["status"] == "healthy" and corpo["db"] == "healthy"
    assert "migracao" in corpo and corpo["migracao"] is None


def test_health_com_a_tabela_vazia_devolve_migracao_nula(monkeypatch):
    resp = _health(monkeypatch, {**PARTICIPANTES, "migracoes_aplicadas": []})

    assert resp.status_code == 200
    assert resp.json()["migracao"] is None


def test_corpo_do_health_continua_casando_o_regex_da_subida(monkeypatch):
    """A subida confere o health pelo `expected_body_regex` do project.json:
    `status` e `db` primeiro, campo novo só no fim."""
    projeto = json.loads((RAIZ / "docs/spec/deploy/project.json").read_text(encoding="utf-8"))
    backend = next(s for s in projeto["services"] if s["id"] == "backend")
    regex = backend["deploy"]["health_check"]["expected_body_regex"]

    resp = _health(monkeypatch, {**PARTICIPANTES, "migracoes_aplicadas": [{"numero": 114}]})

    assert re.search(regex, resp.text.strip()), resp.text
    assert resp.text.strip().endswith('"migracao":114}'), resp.text


@pytest.mark.parametrize("tabelas", [{}, {"migracoes_aplicadas": [{"numero": 114}]}])
def test_banco_fora_continua_503_degraded(monkeypatch, tabelas):
    """Sem `participantes` o ping do banco falha: o número não mascara o 503."""
    resp = _health(monkeypatch, tabelas)

    assert resp.status_code == 503
    assert resp.json()["db"] == "degraded"


def test_as_duas_leituras_do_health_nunca_correm_em_paralelo_no_mesmo_cliente(monkeypatch):
    """Incidente da v0.163.3: `asyncio.gather` punha o ping e a leitura de
    `migracoes_aplicadas` em duas threads sobre o mesmo cliente Supabase
    (HTTP/2, singleton), e o backend travava por minutos. Aqui o dublê conta
    quantas consultas estão dentro de `execute` ao mesmo tempo."""
    import threading
    import time

    trava = threading.Lock()
    estado = {"dentro": 0, "pico": 0}

    class _Lenta(_Consulta):
        def execute(self):
            with trava:
                estado["dentro"] += 1
                estado["pico"] = max(estado["pico"], estado["dentro"])
            time.sleep(0.05)
            try:
                return super().execute()
            finally:
                with trava:
                    estado["dentro"] -= 1

    class _BancoLento(_BancoFalso):
        def table(self, nome):
            return _Lenta(self.tabelas, nome)

    monkeypatch.setattr(
        health, "get_supabase_client", lambda: _BancoLento({**PARTICIPANTES, "migracoes_aplicadas": [{"numero": 114}]})
    )
    app = FastAPI()
    app.include_router(health.router, prefix=settings.api_prefix)
    resp = TestClient(app).get("/api/health")

    assert resp.status_code == 200
    assert resp.json()["migracao"] == 114
    assert estado["pico"] == 1
