"""O Código de Conduta publicado pela coordenação, com versões (issue #1841,
PRD #1786, decisão 37 do diretor).

A coordenação do Comitê publica o PDF, e cada publicação vira uma versão, com
data de vigência e autor. Nenhuma versão sai. A vigente tem um endereço
público estável, sem login, e o aplicativo diz qual versão valia numa data.

As pessoas daqui são de teste. O banco é o dublê de `conduta_apoio`, e o
Storage é o dublê de baixo.
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from typing import Any

import pytest
from conduta_apoio import Banco
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import conduta_codigo, conduta_publico  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

ROTA = "/api/comite-de-conduta/codigo-de-conduta"
ROTA_PUBLICA = "/api/conduta/codigo-de-conduta"
RECUSA = {"detail": "Sem acesso a este conteúdo do Canal de Conduta"}

HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}

CODIGO_2025 = b"%PDF-1.7\nCodigo de Conduta, edicao de 2025\n%%EOF"
CODIGO_2026 = b"%PDF-1.7\nCodigo de Conduta, edicao de 2026, com o item de assedio\n%%EOF"


class _Balde:
    def __init__(self, arquivos: dict[str, bytes]):
        self._arquivos = arquivos

    def upload(self, caminho: str, conteudo: bytes, _opcoes: dict | None = None):
        self._arquivos[caminho] = conteudo
        return {"Key": caminho}

    def download(self, caminho: str) -> bytes:
        return self._arquivos[caminho]

    def remove(self, caminhos: list[str]):
        for caminho in caminhos:
            self._arquivos.pop(caminho, None)
        return [{"name": caminho} for caminho in caminhos]


class _Storage:
    def __init__(self):
        self.baldes: dict[str, dict[str, bytes]] = {}

    def from_(self, balde: str) -> _Balde:
        return _Balde(self.baldes.setdefault(balde, {}))


@pytest.fixture(autouse=True)
def _ambiente():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _pessoa(pid: str, nome: str, **campos) -> dict[str, Any]:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
        **campos,
    }


def _participacao(pid: str, papel: str) -> dict:
    return {
        "id": f"part-{pid}",
        "colegiado_id": COMITE["id"],
        "participante_id": pid,
        "papel": papel,
        "vigencia_inicio": (HOJE - timedelta(days=30)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=600)).isoformat(),
        "termo_assinado_em": "2026-10-01T12:00:00+00:00",
    }


COORDENACAO = _pessoa("P1", "Coordenadora de Teste")
MEMBRO = _pessoa("P2", "Membro de Teste")
SUPER_ADMIN = _pessoa("P3", "Super Admin de Teste", is_super_admin=True, access_profile="super_admin")


@pytest.fixture
def banco() -> Banco:
    banco = Banco(
        {
            "participantes": [COORDENACAO, MEMBRO, SUPER_ADMIN],
            "colegiados": [dict(COMITE)],
            "participacoes": [_participacao("P1", "coordenacao"), _participacao("P2", "membro")],
        }
    )
    banco.storage = _Storage()
    return banco


@pytest.fixture
def canal_aberto(monkeypatch):
    monkeypatch.setattr(settings, "conduta_canal_aberto", True)


def _cliente(banco: Banco, pessoa: dict | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(conduta_codigo.router, prefix="/api")
    app.include_router(conduta_publico.router, prefix="/api")
    if pessoa is not None:

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _publicar(cliente: TestClient, conteudo: bytes, vigente_desde=None, nome: str = "codigo.pdf"):
    dados = {"vigente_desde": vigente_desde.isoformat()} if vigente_desde else {}
    return cliente.post(ROTA, files={"arquivo": (nome, conteudo, "application/pdf")}, data=dados)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A coordenação publica, e as versões anteriores continuam consultáveis
# ═══════════════════════════════════════════════════════════════════════════


def test_coordenacao_publica_versao_nova_e_a_anterior_continua_consultavel(banco):
    cliente = _cliente(banco, COORDENACAO)
    _publicar(cliente, CODIGO_2025)

    resposta = _publicar(cliente, CODIGO_2026, nome="codigo-2026.pdf")

    assert resposta.status_code == 201, resposta.text
    nova = resposta.json()
    assert (nova["versao"], nova["vigente_desde"], nova["autor"]) == (2, HOJE.isoformat(), "Coordenadora de Teste")
    assert nova["nome_arquivo"] == "codigo-2026.pdf"
    versoes = cliente.get(ROTA).json()["versoes"]
    assert [(v["versao"], v["autor"]) for v in versoes] == [(2, "Coordenadora de Teste"), (1, "Coordenadora de Teste")]
    antiga = cliente.get(f"{ROTA}/arquivo", params={"versao": 1})
    assert antiga.status_code == 200
    assert antiga.content == CODIGO_2025
    assert antiga.headers["content-type"] == "application/pdf"


def test_nenhuma_rota_do_codigo_altera_ou_apaga_versao():
    """Só GET e POST no Código de Conduta, em nenhum perfil. O banco recusa o
    resto (migration 194)."""
    metodos = {
        metodo
        for router in (conduta_codigo.router, conduta_publico.router)
        for rota in router.routes
        if "codigo-de-conduta" in rota.path
        for metodo in rota.methods
    }

    assert metodos == {"GET", "POST"}


def test_arquivo_que_nao_e_pdf_responde_422_e_nada_e_gravado(banco):
    resposta = _publicar(_cliente(banco, COORDENACAO), b"MZ\x90\x00 executavel", nome="codigo.pdf")

    assert resposta.status_code == 422
    assert banco.tabelas.get("conduta_codigo_versoes", []) == []
    assert banco.storage.baldes.get("conduta-codigo", {}) == {}


def test_vigencia_no_passado_responde_422(banco):
    """Publicar com vigência retroativa trocaria a versão que valia numa data
    já passada, e uma punição já dada citaria outro texto."""
    resposta = _publicar(_cliente(banco, COORDENACAO), CODIGO_2025, vigente_desde=HOJE - timedelta(days=1))

    assert resposta.status_code == 422
    assert banco.tabelas.get("conduta_codigo_versoes", []) == []


def test_vigencia_antes_da_ultima_versao_responde_422(banco):
    cliente = _cliente(banco, COORDENACAO)
    _publicar(cliente, CODIGO_2025, vigente_desde=HOJE + timedelta(days=10))

    resposta = _publicar(cliente, CODIGO_2026, vigente_desde=HOJE + timedelta(days=5))

    assert resposta.status_code == 422
    assert len(banco.tabelas["conduta_codigo_versoes"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 2. Só a coordenação publica
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pessoa", [MEMBRO, SUPER_ADMIN], ids=["membro", "super_admin"])
def test_quem_nao_e_da_coordenacao_recebe_403_ao_publicar_e_nada_e_gravado(banco, pessoa):
    resposta = _publicar(_cliente(banco, pessoa), CODIGO_2026)

    assert (resposta.status_code, resposta.json()) == (403, RECUSA)
    assert banco.tabelas.get("conduta_codigo_versoes", []) == []
    assert banco.storage.baldes.get("conduta-codigo", {}) == {}


# ═══════════════════════════════════════════════════════════════════════════
# 3. O endereço público devolve a vigente, sem login
# ═══════════════════════════════════════════════════════════════════════════


def test_endereco_publico_devolve_a_versao_vigente_sem_login(banco, canal_aberto):
    coordenacao = _cliente(banco, COORDENACAO)
    _publicar(coordenacao, CODIGO_2025)
    _publicar(coordenacao, CODIGO_2026)

    resposta = _cliente(banco).get(ROTA_PUBLICA)

    assert resposta.status_code == 200, resposta.text
    assert resposta.content == CODIGO_2026
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.headers["x-codigo-de-conduta-versao"] == "2"


def test_endereco_publico_ignora_a_versao_que_ainda_nao_comecou(banco, canal_aberto):
    coordenacao = _cliente(banco, COORDENACAO)
    _publicar(coordenacao, CODIGO_2025)
    _publicar(coordenacao, CODIGO_2026, vigente_desde=HOJE + timedelta(days=15))

    resposta = _cliente(banco).get(ROTA_PUBLICA)

    assert resposta.content == CODIGO_2025
    assert resposta.headers["x-codigo-de-conduta-versao"] == "1"


def test_endereco_publico_sem_codigo_publicado_responde_404(banco, canal_aberto):
    resposta = _cliente(banco).get(ROTA_PUBLICA)

    assert resposta.status_code == 404
    assert resposta.json() == {"detail": "O Código de Conduta ainda não foi publicado"}


def test_com_o_canal_fechado_o_endereco_publico_responde_404(banco):
    _publicar(_cliente(banco, COORDENACAO), CODIGO_2025)

    resposta = _cliente(banco).get(ROTA_PUBLICA)

    assert (resposta.status_code, resposta.json()) == (404, {"detail": "Not Found"})


# ═══════════════════════════════════════════════════════════════════════════
# 4. Dada uma data, a versão que valia
# ═══════════════════════════════════════════════════════════════════════════


def test_dada_uma_data_o_aplicativo_diz_qual_versao_valia(banco):
    cliente = _cliente(banco, COORDENACAO)
    _publicar(cliente, CODIGO_2025)
    _publicar(cliente, CODIGO_2026, vigente_desde=HOJE + timedelta(days=10))

    def versao_em(dias: int):
        resposta = cliente.get(f"{ROTA}/vigente", params={"data": (HOJE + timedelta(days=dias)).isoformat()})
        assert resposta.status_code == 200, resposta.text
        versao = resposta.json()["versao"]
        return versao and versao["versao"]

    assert [versao_em(d) for d in (-1, 0, 9, 10, 400)] == [None, 1, 1, 2, 2]


def test_duas_versoes_com_a_mesma_vigencia_vale_a_publicada_depois(banco):
    """Publicar de novo no mesmo dia corrige o arquivo: a mais nova manda."""
    cliente = _cliente(banco, COORDENACAO)
    _publicar(cliente, CODIGO_2025)
    _publicar(cliente, CODIGO_2026)

    resposta = cliente.get(f"{ROTA}/vigente", params={"data": HOJE.isoformat()})

    assert resposta.json()["versao"]["versao"] == 2
