"""As configurações e os textos com versão do Canal de Conduta (issue #1826,
PRD #1786, especificação seção 15).

A tela é da coordenação do Comitê. Cada alteração vira uma versão nova, com
autor e data, e a anterior continua lá. As telas públicas leem a versão
vigente e recebem junto o identificador dela, para dizer qual versão mostraram.

As pessoas daqui são de teste. O banco é o dublê de `conduta_apoio`.
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
from app.routers import conduta_comite, conduta_publico  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

ROTA = "/api/comite-de-conduta/configuracoes"
ROTA_PUBLICA = "/api/conduta/textos"
RECUSA = {"detail": "Sem acesso a este conteúdo do Canal de Conduta"}

HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}

AVISO_3 = (
    "Relato equivocado, feito de boa-fé, não gera nenhuma consequência. Acusação que a pessoa sabe "
    "ser falsa, feita para prejudicar alguém, é falta grave e pode ser crime contra a honra."
)
AVISO_3_DO_JURIDICO = "Relato feito de boa-fé não gera consequência. Acusação sabidamente falsa é falta grave."


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
    return Banco(
        {
            "participantes": [COORDENACAO, MEMBRO, SUPER_ADMIN],
            "colegiados": [dict(COMITE)],
            "participacoes": [_participacao("P1", "coordenacao"), _participacao("P2", "membro")],
        }
    )


def _cliente(banco: Banco, pessoa: dict | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(conduta_comite.router, prefix="/api")
    app.include_router(conduta_publico.router, prefix="/api")
    if pessoa is not None:

        async def _usuario() -> dict[str, Any]:
            return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _item(corpo: dict, chave: str) -> dict:
    return next(item for item in corpo["itens"] if item["chave"] == chave)


# ═══════════════════════════════════════════════════════════════════════════
# 1. A coordenação edita, e cada alteração vira versão nova
# ═══════════════════════════════════════════════════════════════════════════


def test_coordenacao_salva_o_aviso_e_ele_vira_versao_com_autor_e_data(banco):
    cliente = _cliente(banco, COORDENACAO)

    resposta = cliente.post(f"{ROTA}/aviso_p1_boa_fe", json={"texto": AVISO_3})

    assert resposta.status_code == 201, resposta.text
    versao = resposta.json()
    assert versao["versao"] == 1
    assert versao["texto"] == AVISO_3
    assert versao["autor"] == "Coordenadora de Teste"
    assert versao["criado_em"]
    (item,) = [i for i in cliente.get(ROTA).json()["itens"] if i["chave"] == "aviso_p1_boa_fe"]
    assert item["versoes"][0]["texto"] == AVISO_3
    assert item["versoes"][0]["autor"] == "Coordenadora de Teste"


def test_a_versao_anterior_continua_consultavel_depois_da_nova(banco):
    cliente = _cliente(banco, COORDENACAO)
    cliente.post(f"{ROTA}/aviso_p1_boa_fe", json={"texto": AVISO_3})

    resposta = cliente.post(f"{ROTA}/aviso_p1_boa_fe", json={"texto": AVISO_3_DO_JURIDICO})

    assert resposta.json()["versao"] == 2
    item = _item(cliente.get(ROTA).json(), "aviso_p1_boa_fe")
    assert [(v["versao"], v["texto"]) for v in item["versoes"]] == [(2, AVISO_3_DO_JURIDICO), (1, AVISO_3)]


def test_nenhuma_rota_do_modulo_altera_ou_apaga_versao_de_configuracao():
    """Só GET e POST: não há PUT, PATCH nem DELETE nas configurações, em
    nenhum perfil. O banco recusa o resto (test_conduta_configuracoes_banco)."""
    metodos = {
        metodo
        for router in (conduta_comite.router, conduta_publico.router)
        for rota in router.routes
        if "configurac" in rota.path or "textos" in rota.path
        for metodo in rota.methods
    }

    assert metodos == {"GET", "POST"}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Só a coordenação
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("pessoa", [MEMBRO, SUPER_ADMIN], ids=["membro", "super_admin"])
def test_quem_nao_e_da_coordenacao_recebe_403_e_nada_e_gravado(banco, pessoa):
    cliente = _cliente(banco, pessoa)

    leitura = cliente.get(ROTA)
    escrita = cliente.post(f"{ROTA}/contato_dp", json={"texto": "Ramal 2040"})

    assert (leitura.status_code, leitura.json()) == (403, RECUSA)
    assert (escrita.status_code, escrita.json()) == (403, RECUSA)
    assert banco.tabelas.get("conduta_configuracoes", []) == []


def test_coordenacao_com_a_participacao_vencida_recebe_403(banco):
    banco.tabelas["participacoes"][0]["vigencia_fim"] = (HOJE - timedelta(days=1)).isoformat()

    resposta = _cliente(banco, COORDENACAO).get(ROTA)

    assert (resposta.status_code, resposta.json()) == (403, RECUSA)


@pytest.mark.parametrize("em_branco", ["   ", "\n", " \t\n "])
def test_texto_em_branco_responde_422_e_nada_e_gravado(banco, em_branco):
    resposta = _cliente(banco, COORDENACAO).post(f"{ROTA}/contato_dp", json={"texto": em_branco})

    assert resposta.status_code == 422
    assert banco.tabelas.get("conduta_configuracoes", []) == []


def test_item_que_nao_existe_responde_404(banco):
    resposta = _cliente(banco, COORDENACAO).post(f"{ROTA}/qualquer_coisa", json={"texto": "x"})

    assert resposta.status_code == 404
    assert banco.tabelas.get("conduta_configuracoes", []) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. As telas públicas leem a vigente, com o identificador
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def canal_aberto(monkeypatch):
    monkeypatch.setattr(settings, "conduta_canal_aberto", True)


def test_a_leitura_publica_devolve_a_vigente_com_o_identificador_da_versao(banco, canal_aberto):
    coordenacao = _cliente(banco, COORDENACAO)
    coordenacao.post(f"{ROTA}/aviso_p1_boa_fe", json={"texto": AVISO_3})
    vigente = coordenacao.post(f"{ROTA}/aviso_p1_boa_fe", json={"texto": AVISO_3_DO_JURIDICO}).json()

    resposta = _cliente(banco).get(ROTA_PUBLICA)

    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["textos"]["aviso_p1_boa_fe"] == {
        "texto": AVISO_3_DO_JURIDICO,
        "versao": 2,
        "versao_id": vigente["id"],
    }


def test_a_leitura_publica_nao_leva_o_que_e_do_comite_nem_o_autor(banco, canal_aberto):
    coordenacao = _cliente(banco, COORDENACAO)
    coordenacao.post(f"{ROTA}/local_guarda_envelopes", json={"texto": "Armário 3 da Diretoria"})
    coordenacao.post(f"{ROTA}/contato_dp", json={"texto": "Ramal 2040"})

    textos = _cliente(banco).get(ROTA_PUBLICA).json()["textos"]

    assert "local_guarda_envelopes" not in textos
    assert "consentimento_gravacao" not in textos
    assert set(textos["contato_dp"]) == {"texto", "versao", "versao_id"}
    assert textos["orientacao_nsp"] is None


def test_com_o_canal_fechado_a_leitura_publica_responde_404(banco):
    assert _cliente(banco).get(ROTA_PUBLICA).status_code == 404


def test_a_leitura_publica_tem_limite_por_aparelho(banco, canal_aberto):
    cliente = _cliente(banco)

    respostas = [cliente.get(ROTA_PUBLICA) for _ in range(61)]

    assert respostas[-2].status_code == 200
    assert respostas[-1].status_code == 429


# ═══════════════════════════════════════════════════════════════════════════
# 4. Sem e-mail do DP (decisão 4 do diretor)
# ═══════════════════════════════════════════════════════════════════════════


def test_nao_existe_campo_de_email_do_dp(banco):
    cliente = _cliente(banco, COORDENACAO)
    itens = cliente.get(ROTA).json()["itens"]

    rotulos = " ".join(f"{item['chave']} {item['rotulo']}" for item in itens).lower()
    assert "mail" not in rotulos
    assert cliente.post(f"{ROTA}/email_dp", json={"texto": "dp@hsm.test"}).status_code == 404
