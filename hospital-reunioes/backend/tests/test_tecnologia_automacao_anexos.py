"""A ponte com o desenvolvimento: a rota de automacao dos anexos (issue #1063, ADR 0069, decisao 2).

Quem desenvolve a Demanda busca os prints pelo app, por uma boca so: o script
`pegar-issue/scripts/anexos.py` chama esta rota com `X-API-Key`. A chave e
propria (`TECNOLOGIA_AUTOMACAO_API_KEY`), no molde e com a mesma comparacao
constante da API da Ana: ausente, vazia ou errada recusa igual; sem chave
configurada, 503 (a ponte ainda nao foi ligada, e quem chama precisa saber que
o problema e de cadastro, nao de chave errada).

Pela ROTA de verdade, com o Supabase e o storage dublados no molde dos testes do
Anexo da Demanda (`test_tecnologia_anexos.py`).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_anexos import _StorageFake  # noqa: E402
from test_tecnologia_vinculo import _SupabaseMock  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import tecnologia_automacao  # noqa: E402

CHAVE = "chave-de-automacao-do-teste-1063"
DEMANDA = "3f2a9c1e-7b44-4d0a-9a51-0c6f7e8d1a22"
OUTRA_DEMANDA = "9b1d6e2f-1c3a-4e5b-8f70-2a4c6e8b0d13"
ROTA = f"/api/automacao/tecnologia/demandas/{DEMANDA}/anexos"
BUCKET = "anexos-tecnologia"


def _anexo(ordem: int, nome: str, *, demanda: str = DEMANDA, apagado: bool = False, tipo: str = "image/png") -> dict:
    return {
        "id": f"a-{demanda[:4]}-{ordem}",
        "demanda_id": demanda,
        "ordem": ordem,
        "storage_path": f"demanda-{demanda}/sorteado{ordem}.png",
        "nome_original": nome,
        "content_type": tipo,
        "tamanho_bytes": 10,
        "anexado_por": "P1",
        "criado_em": "2026-10-07T10:00:00Z",
        "apagado_em": "2026-10-07T12:00:00Z" if apagado else None,
        "conversa_id": None,
    }


def _cliente(anexos: list[dict]) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(tecnologia_automacao.router, prefix="/api")
    sb = _SupabaseMock({"tecnologia_anexos": [dict(a) for a in anexos]})
    sb.storage = _StorageFake()
    for anexo in anexos:
        if not anexo["apagado_em"]:
            sb.storage.arquivos[f"{BUCKET}/{anexo['storage_path']}"] = b"png"
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


@pytest.fixture(autouse=True)
def _zera_o_limitador():
    """O limitador guarda a contagem em memoria entre testes e arquivos."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture
def chave_configurada(monkeypatch):
    monkeypatch.setattr(settings, "tecnologia_automacao_api_key", CHAVE)


class TestAChave:
    def test_chave_certa_devolve_nome_tipo_e_url_assinada_de_cada_anexo(self, chave_configurada):
        cliente = _cliente([_anexo(1, "tela do erro.png"), _anexo(2, "depois.jpg", tipo="image/jpeg")])

        resposta = cliente.get(ROTA, headers={"X-API-Key": CHAVE})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json() == {
            "anexos": [
                {
                    "nome": "tela do erro.png",
                    "tipo": "image/png",
                    "url": f"https://storage.local/{BUCKET}/demanda-{DEMANDA}/sorteado1.png?token=assinado&exp=600",
                },
                {
                    "nome": "depois.jpg",
                    "tipo": "image/jpeg",
                    "url": f"https://storage.local/{BUCKET}/demanda-{DEMANDA}/sorteado2.png?token=assinado&exp=600",
                },
            ]
        }

    @pytest.mark.parametrize(
        "cabecalhos",
        [
            {},
            {"X-API-Key": ""},
            {"X-API-Key": "chave-errada"},
            {"X-API-Key": CHAVE + "x"},
            {"X-API-Key": "chavé".encode()},
        ],
        ids=["ausente", "vazia", "errada", "prefixo-certo", "nao-ascii"],
    )
    def test_chave_ausente_vazia_ou_errada_recusa_igual(self, chave_configurada, cabecalhos):
        cliente = _cliente([_anexo(1, "tela do erro.png")])

        resposta = cliente.get(ROTA, headers=cabecalhos)

        assert resposta.status_code == 401
        assert resposta.json() == {"detail": "API key inválida ou ausente"}

    @pytest.mark.parametrize(
        "cabecalhos", [{}, {"X-API-Key": ""}, {"X-API-Key": "qualquer"}], ids=["ausente", "vazia", "qualquer"]
    )
    def test_sem_chave_configurada_responde_503(self, monkeypatch, cabecalhos):
        """A ponte desligada nao se confunde com chave errada: quem chama precisa
        saber que falta o cadastro no Coolify. E chave vazia no servidor nunca
        casa com header vazio."""
        monkeypatch.setattr(settings, "tecnologia_automacao_api_key", "")
        cliente = _cliente([_anexo(1, "tela do erro.png")])

        resposta = cliente.get(ROTA, headers=cabecalhos)

        assert resposta.status_code == 503
        assert "TECNOLOGIA_AUTOMACAO_API_KEY" in resposta.json()["detail"]


class TestOQueALista:
    def test_anexo_apagado_nao_aparece(self, chave_configurada):
        """Concluir e Cancelar apagam o binario e deixam o registro: quem
        desenvolve nao tem o que buscar nele."""
        cliente = _cliente([_anexo(1, "ficou.png"), _anexo(2, "saiu.png", apagado=True)])

        resposta = cliente.get(ROTA, headers={"X-API-Key": CHAVE})

        assert [a["nome"] for a in resposta.json()["anexos"]] == ["ficou.png"]

    def test_so_os_anexos_da_demanda_pedida(self, chave_configurada):
        cliente = _cliente([_anexo(1, "desta.png"), _anexo(1, "de outra.png", demanda=OUTRA_DEMANDA)])

        resposta = cliente.get(ROTA, headers={"X-API-Key": CHAVE})

        assert [a["nome"] for a in resposta.json()["anexos"]] == ["desta.png"]

    def test_demanda_sem_anexo_devolve_lista_vazia(self, chave_configurada):
        resposta = _cliente([]).get(ROTA, headers={"X-API-Key": CHAVE})

        assert resposta.status_code == 200
        assert resposta.json() == {"anexos": []}


class TestOTeto:
    """A rota fica aberta na internet sem login (o gate e a chave), entao tem
    teto por endereco, no molde da API da Ana: 60 por minuto."""

    def test_o_61o_pedido_no_mesmo_minuto_e_429_mesmo_com_a_chave_certa(self, chave_configurada):
        """O teto conta antes da chave: 60 tentativas de chave errada esgotam o
        minuto, e nem a chave certa fura no 61o pedido. Sem isso, adivinhar a
        chave nao tem freio."""
        cliente = _cliente([_anexo(1, "tela do erro.png")])

        tentativas = [cliente.get(ROTA, headers={"X-API-Key": "chave-errada"}) for _ in range(60)]
        assert [r.status_code for r in tentativas] == [401] * 60

        passou_do_teto = cliente.get(ROTA, headers={"X-API-Key": CHAVE})

        assert passou_do_teto.status_code == 429

    def test_quem_desenvolve_busca_os_prints_60_vezes_no_minuto_sem_bater_no_teto(self, chave_configurada):
        cliente = _cliente([_anexo(1, "tela do erro.png")])

        respostas = [cliente.get(ROTA, headers={"X-API-Key": CHAVE}) for _ in range(60)]

        assert [r.status_code for r in respostas] == [200] * 60


def test_a_rota_esta_montada_no_app():
    from app.main import app

    assert "/api/automacao/tecnologia/demandas/{demanda_id}/anexos" in app.openapi()["paths"]
