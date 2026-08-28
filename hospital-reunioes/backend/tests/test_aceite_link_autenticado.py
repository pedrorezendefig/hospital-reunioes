"""Link de Aceite interno pelo sino, sem token em claro no banco (issue #295).

O PR #294 guardava o token do aceite EM CLARO no `referencia_id` da
notificacao in-app, para o sino rotear direto para /aceite/{token}. Isso
quebrava o invariante hash-only da tabela `reuniao_aceite_tokens`: num
vazamento do banco, os tokens saiam utilizaveis.

Agora a notificacao guarda o id da Reuniao, e o sino pede o link a um
endpoint autenticado que so atende o proprio destinatario. Como o banco so
tem o SHA-256, o link nao pode ser "lido de volta": ele e reemitido, e o
hash antigo e substituido.
"""

from __future__ import annotations

import hashlib
import os
import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import _participante_ctx, get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import aceite as aceite_router  # noqa: E402
from app.services import aceite_service  # noqa: E402

ID_REUNIAO = "R1"
FAC = {
    "id": "P_FAC",
    "auth_user_id": "auth-fac",
    "email": "fac@hsm.com",
    "nome_completo": "Fernanda Facilitadora",
    "access_profile": "regular",
    "is_super_admin": False,
    "role": "facilitador",
    "ativo": True,
}
OUTRO = {**FAC, "id": "P_OUTRO", "auth_user_id": "auth-outro", "email": "outro@hsm.com"}


@pytest.fixture(autouse=True)
def _reset_estado_global():
    limiter._storage.reset()
    _participante_ctx.set(None)
    yield
    limiter._storage.reset()
    _participante_ctx.set(None)


# ─── Mock Supabase minimo ─────────────────────────────────────────────────────


class _Query:
    def __init__(self, rows: list):
        self._rows = rows
        self._op = "select"
        self._payload: Any = None
        self._filtros: list[tuple[str, Any]] = []

    def select(self, *_a, **_kw):
        self._op = "select"
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def eq(self, col, valor):
        self._filtros.append((col, valor))
        return self

    def is_(self, col, _valor):
        self._filtros.append((col, None))
        return self

    def execute(self):
        casadas = [r for r in self._rows if all(r.get(c) == v for c, v in self._filtros)]
        if self._op == "update":
            for row in casadas:
                row.update(self._payload)
        return type("_R", (), {"data": [dict(r) for r in casadas]})()


class _Supabase:
    def __init__(self, tokens: list, reunioes: list, participantes: list):
        self.tabelas = {
            "reuniao_aceite_tokens": tokens,
            "reunioes": reunioes,
            "participantes": participantes,
        }

    def table(self, nome: str):
        return _Query(self.tabelas[nome])


def _reuniao(**mudancas) -> dict:
    return {
        "id_reuniao": ID_REUNIAO,
        "titulo": "Reuniao de Diretoria",
        "tipo": "DIRETORIA",
        "data": "2026-08-01",
        "hora_inicio": "09:00",
        "status_ata": "AGUARDANDO_ASSINATURA",
        "modo_interno_desde": "2026-08-02T10:00:00Z",
        "facilitador_id": "P_FAC",
        "json_ata": {"pauta": []},
        "deleted_at": None,
        **mudancas,
    }


def _token_row(participante_id: str = "P_FAC", **mudancas) -> dict:
    return {
        "id": f"tok-{participante_id}",
        "id_reuniao": ID_REUNIAO,
        "participante_id": participante_id,
        "token_hash": hashlib.sha256(b"token-antigo-do-email").hexdigest(),
        "criado_em": "2026-08-02T10:00:00Z",
        "usado_em": None,
        **mudancas,
    }


def _app(sb: _Supabase, logado_como: dict | None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(aceite_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: sb
    if logado_como is not None:

        async def _fake_user() -> dict:
            return {"id": logado_como["auth_user_id"], "email": logado_como["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _fake_user
    return TestClient(app)


def _cenario(tokens: list | None = None, participantes: list | None = None, reuniao: dict | None = None):
    return _Supabase(
        tokens if tokens is not None else [_token_row()],
        [reuniao or _reuniao()],
        participantes if participantes is not None else [dict(FAC), dict(OUTRO)],
    )


# ─── O caminho feliz ──────────────────────────────────────────────────────────


def test_destinatario_recebe_um_link_novo_e_valido():
    sb = _cenario()
    resp = _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 200, resp.text
    url = resp.json()["url"]
    assert url.startswith("/aceite/")
    token = url.rsplit("/", 1)[1]
    assert token, "o endpoint devolveu um link sem token"

    linha = sb.tabelas["reuniao_aceite_tokens"][0]
    assert linha["token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_o_banco_continua_hash_only():
    """O que a issue #295 pede: o token devolvido nao pode estar em lugar
    nenhum do banco em claro."""
    sb = _cenario()
    resp = _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})
    token = resp.json()["url"].rsplit("/", 1)[1]

    for _nome, linhas in sb.tabelas.items():
        for linha in linhas:
            for valor in linha.values():
                assert valor != token, "o token vazou em claro para o banco"


def test_o_hash_antigo_e_substituido():
    """Reemitir troca o hash: o link que foi por email deixa de valer. E o
    preco de manter hash-only, porque o hash nao volta ao token."""
    hash_antigo = hashlib.sha256(b"token-antigo-do-email").hexdigest()
    sb = _cenario()
    _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert sb.tabelas["reuniao_aceite_tokens"][0]["token_hash"] != hash_antigo


def test_reemissao_nao_marca_o_aceite_como_usado():
    sb = _cenario()
    _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert sb.tabelas["reuniao_aceite_tokens"][0]["usado_em"] is None


# ─── As recusas ───────────────────────────────────────────────────────────────


def test_outra_pessoa_nao_pega_o_link_do_destinatario():
    """A porta que importa: quem esta logado nao e o dono do token.

    O cenario tem UM token, e ele e do Facilitador. A outra pessoa e um
    participante valido e ativo, com sessao boa: se o endpoint respondesse
    pelo id da Reuniao em vez de pelo par (reuniao, participante), ela sairia
    daqui com o link de aceite alheio."""
    sb = _cenario()
    resp = _app(sb, OUTRO).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 404
    assert (
        sb.tabelas["reuniao_aceite_tokens"][0]["token_hash"] == hashlib.sha256(b"token-antigo-do-email").hexdigest()
    ), "o token do Facilitador foi reemitido por um pedido de outra pessoa"


def test_sem_login_nao_ha_link():
    sb = _cenario()
    resp = _app(sb, None).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 401


def test_token_ja_usado_nao_reemite():
    usado = _token_row(usado_em=datetime.now(UTC).isoformat())
    sb = _cenario(tokens=[usado])
    resp = _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 410
    assert sb.tabelas["reuniao_aceite_tokens"][0]["token_hash"] == hashlib.sha256(b"token-antigo-do-email").hexdigest()


def test_reuniao_fora_do_modo_interno_nao_reemite():
    sb = _cenario(reuniao=_reuniao(status_ata="ASSINADA", modo_interno_desde=None))
    resp = _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 410
    assert sb.tabelas["reuniao_aceite_tokens"][0]["token_hash"] == hashlib.sha256(b"token-antigo-do-email").hexdigest()


def test_reuniao_sem_token_para_a_pessoa_devolve_404():
    sb = _cenario(tokens=[])
    resp = _app(sb, FAC).post("/api/aceite/meu-link", json={"id_reuniao": ID_REUNIAO})

    assert resp.status_code == 404


# ─── O servico, direto ────────────────────────────────────────────────────────


def test_servico_recusa_participante_sem_token():
    sb = _cenario(tokens=[_token_row("P_OUTRO")])
    with pytest.raises(aceite_service.TokenInvalidoError):
        aceite_service.reemitir_link_aceite_interno(sb, ID_REUNIAO, "P_FAC")


def test_servico_devolve_token_diferente_a_cada_chamada():
    sb = _cenario()
    primeiro = aceite_service.reemitir_link_aceite_interno(sb, ID_REUNIAO, "P_FAC")
    segundo = aceite_service.reemitir_link_aceite_interno(sb, ID_REUNIAO, "P_FAC")

    assert primeiro != segundo
    assert sb.tabelas["reuniao_aceite_tokens"][0]["token_hash"] == hashlib.sha256(segundo.encode("utf-8")).hexdigest()
