"""A rota antiga de convite saiu do app (issue #1286).

`POST /api/auth/invite/{id}` abria para qualquer `role = coordenador`, que é o
papel de todo participante, e criava conta no Auth sem passar pelo admin. O
fluxo de acesso de hoje é `/admin/usuarios`, e o frontend não chama mais a rota
antiga: ela foi apagada em vez de restrita.
"""

from __future__ import annotations

import os
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402

ROTA_DO_CONVITE = "/api/auth/invite/{participante_id}"


def _caminhos_do_app() -> dict:
    """A fonte é o schema OpenAPI, e não `app.routes` (issues #542 e #546)."""
    from app.main import app

    cache = app.openapi_schema
    try:
        return app.openapi()["paths"]
    finally:
        app.openapi_schema = cache


class _BancoQueNaoPodeSerTocado:
    def table(self, nome):
        raise AssertionError(f"A rota de convite chegou ao banco ({nome})")


def test_a_rota_de_convite_nao_existe_mais_no_app():
    caminhos = _caminhos_do_app()

    assert len(caminhos) > 50, "O schema voltou quase vazio: a varredura estaria olhando para nada"
    assert "/api/auth/me" in caminhos
    assert ROTA_DO_CONVITE not in caminhos


def test_coordenador_nao_cria_conta_pelo_convite():
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: {
        "id": "auth-coordenador",
        "email": "coordenador@exemplo.com",
        "role": "coordenador",
    }
    app.dependency_overrides[get_supabase_client] = lambda: _BancoQueNaoPodeSerTocado()
    try:
        r = TestClient(app).post("/api/auth/invite/participante-1")
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_supabase_client, None)

    assert r.status_code == 404
