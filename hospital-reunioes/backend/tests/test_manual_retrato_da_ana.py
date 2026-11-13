"""A aba Ana do manual: o Retrato servido do repositório privado da Ana
(issue #1720, ADR 0094, decisão 3).

A rota roda de verdade, com `require_super_admin` de pé: só o login
(`get_current_user`) e o Supabase são dublados. O cliente do GitHub também
roda inteiro; falso é só o transporte (`httpx.request` dentro do módulo dele),
que faz o papel do repositório da Ana.
"""

from __future__ import annotations

import base64
import os
import sys
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.admin import manual as manual_router  # noqa: E402
from app.services import github_client  # noqa: E402

REPO_DA_ANA = "dona/programa-ana"

# O repositório da Ana, como o transporte falso o devolve: o caminho a partir
# da raiz e o conteúdo. O `gerar.py` mora em `retrato/`, mas não é página.
ARQUIVOS: dict[str, bytes] = {
    "retrato/index.html": b"<!doctype html><title>Retrato da Ana</title>",
    "retrato/assets/retrato.css": b"body { color: #2B2E7E; }",
    "retrato/assets/fonts/HPSimplified_Rg.ttf": b"\x00\x01fonte",
    "retrato/dados/retrato.json": b'{"esferas": []}',
    "retrato/gerar.py": b"print('gerador')",
    "README.md": b"# programa-ana",
}


class _Supabase:
    """Só o que o gate lê: o participante pelo `auth_user_id`."""

    def __init__(self, pessoas: list[dict]):
        self._pessoas = pessoas
        self._filtro: tuple[str, Any] | None = None

    def table(self, _nome):
        return self

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtro = (coluna, valor)
        return self

    def update(self, *_a, **_kw):
        return self

    def execute(self):
        coluna, valor = self._filtro or ("", None)
        return type("R", (), {"data": [p for p in self._pessoas if p.get(coluna) == valor]})()


def _pessoa(access_profile: str | None) -> dict:
    return {
        "id": "P17270",
        "auth_user_id": "auth-P17270",
        "nome_completo": "Pessoa Ficticia",
        "email": "p17270@exemplo.test",
        "ativo": True,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
    }


@pytest.fixture
def pedidos(monkeypatch) -> list[str]:
    """Liga a integração da Ana e troca o transporte pelo repositório falso."""
    monkeypatch.setattr(settings, "github_integracao_token", "token-falso")
    monkeypatch.setattr(settings, "github_integracao_repo_ana", REPO_DA_ANA)
    feitos: list[str] = []

    def _transporte(metodo, url, **_kw):
        feitos.append(f"{metodo} {url}")
        prefixo = f"https://api.github.com/repos/{REPO_DA_ANA}/contents/"
        caminho = url.removeprefix(prefixo)
        if not url.startswith(prefixo) or caminho not in ARQUIVOS:
            return httpx.Response(404, json={"message": "Not Found"})
        conteudo = base64.b64encode(ARQUIVOS[caminho]).decode()
        return httpx.Response(200, json={"type": "file", "encoding": "base64", "content": conteudo})

    monkeypatch.setattr(github_client.httpx, "request", _transporte)
    return feitos


def _cliente(*, logado: dict | None) -> TestClient:
    app = FastAPI()
    app.include_router(manual_router.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: _Supabase([logado] if logado else [])
    if logado is not None:

        async def _usuario() -> dict[str, Any]:
            return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
    return TestClient(app)


ROTA = "/api/admin/manual/ana/retrato"


class TestQuemRecebeORetrato:
    def test_super_admin_recebe_a_pagina_do_retrato(self, pedidos):
        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/index.html")

        assert resposta.status_code == 200
        assert resposta.content == ARQUIVOS["retrato/index.html"]
        assert resposta.headers["content-type"].startswith("text/html")
        assert pedidos == [f"GET https://api.github.com/repos/{REPO_DA_ANA}/contents/retrato/index.html"]

    def test_super_admin_recebe_os_arquivos_de_assets_e_os_dados(self, pedidos):
        cliente = _cliente(logado=_pessoa("super_admin"))

        css = cliente.get(f"{ROTA}/assets/retrato.css")
        fonte = cliente.get(f"{ROTA}/assets/fonts/HPSimplified_Rg.ttf")
        dados = cliente.get(f"{ROTA}/dados/retrato.json")

        assert (css.status_code, css.content) == (200, ARQUIVOS["retrato/assets/retrato.css"])
        assert css.headers["content-type"].startswith("text/css")
        assert (fonte.status_code, fonte.content) == (200, ARQUIVOS["retrato/assets/fonts/HPSimplified_Rg.ttf"])
        assert (dados.status_code, dados.json()) == (200, {"esferas": []})

    def test_outro_perfil_recebe_403_sem_ir_ao_github(self, pedidos):
        cliente = _cliente(logado=_pessoa("regular"))

        resposta = cliente.get(f"{ROTA}/index.html")

        assert resposta.status_code == 403
        assert pedidos == []

    def test_sem_login_recebe_401_sem_ir_ao_github(self, pedidos):
        resposta = _cliente(logado=None).get(f"{ROTA}/index.html")

        assert resposta.status_code == 401
        assert pedidos == []


class TestSoSaiArquivoDoRetrato:
    @pytest.mark.parametrize(
        "caminho",
        [
            "gerar.py",
            "../README.md",
            "assets/../../README.md",
            "/README.md",
            "/retrato/index.html",
            "assets/..",
            "dados/../gerar.py",
            "assets\\..\\gerar.py",
            "",
        ],
    )
    def test_caminho_fora_do_retrato_e_recusado(self, pedidos, caminho):
        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/{caminho}")

        assert resposta.status_code in (400, 404)
        assert pedidos == []

    def test_ponto_ponto_codificado_na_url_tambem_e_recusado(self, pedidos):
        """O cliente HTTP normaliza `..` cru; o `%2E%2E` chega à rota como `..`."""
        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/assets/%2E%2E/%2E%2E/README.md")

        assert resposta.status_code in (400, 404)
        assert pedidos == []

    @pytest.mark.parametrize(
        "caminho",
        ["index.html", "assets/retrato.css", "assets/fonts/HPSimplified_Rg.ttf", "dados/retrato.json"],
    )
    def test_os_caminhos_da_pagina_sao_aceitos(self, caminho):
        assert manual_router.caminho_no_retrato(caminho) == f"retrato/{caminho}"

    @pytest.mark.parametrize(
        "caminho", ["../README.md", "/etc/passwd", "assets/../gerar.py", "gerar.py", "dados/x.json"]
    )
    def test_o_guarda_recusa_o_que_nao_e_pagina(self, caminho):
        assert manual_router.caminho_no_retrato(caminho) is None


class TestSemAcesso:
    def test_sem_a_variavel_da_ana_responde_que_nao_esta_ligado(self, pedidos, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_repo_ana", "")

        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/index.html")

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == "O Retrato da Ana ainda não está ligado"
        assert pedidos == []

    def test_sem_acesso_ao_repositorio_responde_que_nao_esta_ligado(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "token-falso")
        monkeypatch.setattr(settings, "github_integracao_repo_ana", REPO_DA_ANA)
        monkeypatch.setattr(
            github_client.httpx, "request", lambda *_a, **_kw: httpx.Response(403, json={"message": "Forbidden"})
        )

        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/index.html")

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == "O Retrato da Ana ainda não está ligado"

    def test_arquivo_que_nao_existe_e_404(self, pedidos):
        resposta = _cliente(logado=_pessoa("super_admin")).get(f"{ROTA}/assets/sumiu.js")

        assert resposta.status_code == 404
