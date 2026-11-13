"""O teste do convite ao Google no QR (issue #1625, PRD #1527, ADR 0089).

Quem dá nota 4 ou 5 no cartaz vê o convite para avaliar o hospital no Google,
só com a chave geral e a chave do ponto ligadas. Só a diretoria executiva
liga e desliga, com auditoria de/para. O clique passa por uma rota que conta
antes de redirecionar, e a Central mostra convites, cliques e taxa por ponto,
com o aviso de reavaliar depois de 60 dias.

Os testes sobem as rotas reais com um banco falso em memória.
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

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_publica  # noqa: E402

CODIGO = "AB2CD3"
OUTRO = "XY7ZW8"
URL_DO_GOOGLE = "https://search.google.com/local/writereview?placeid=ChIJN5IUl-vfmwARsSET9nFjh70"

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _ponto(codigo: str, *, convite: bool = False, nome: str = "Emergência adulta") -> dict:
    return {
        "id": f"ponto-{codigo}",
        "codigo": codigo,
        "setor": "Pronto Socorro",
        "ponto": "Hall da emergência",
        "ativo": True,
        "criado_em": "2026-11-01T12:00:00+00:00",
        "nome_publico": nome,
        "descricao_local": "Hall, parede ao lado da passagem",
        "titulo_cartaz": "atendimento_hoje",
        "codigo_controle": None,
        "ala_internacao": False,
        "google_teste_ativo": convite,
    }


class _Tabela:
    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self.nome = nome
        self._filtros: list = []
        self._colunas: tuple[str, ...] | None = None
        self._insert: dict | None = None
        self._update: dict | None = None
        self._ordem: tuple[str, bool] | None = None

    def select(self, colunas: str = "*", *_a, **_k):
        if colunas != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload: dict):
        self._insert = dict(payload)
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def delete(self):
        raise AssertionError(f"ninguém apaga linha de {self.nome}")

    def eq(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: r.get(c) == v)
        return self

    def gte(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: str(r.get(c)) >= v)
        return self

    def lt(self, col, valor):
        self._filtros.append(lambda r, c=col, v=valor: str(r.get(c)) < v)
        return self

    def order(self, col, desc=False):
        self._ordem = (col, desc)
        return self

    def limit(self, _n):
        return self

    def range(self, *_a):
        return self

    def execute(self):
        linhas = self._banco.tabelas.setdefault(self.nome, [])
        if self._insert is not None:
            linha = {"id": f"{self.nome}-{len(linhas) + 1}", **self._insert}
            if self.nome == "ouvidoria_avaliacoes":
                linha.setdefault("criada_em", self._banco.agora)
                linha.setdefault("convite_google_exibido", False)
                linha.setdefault("convite_google_clicado", False)
            linhas.append(linha)
            self._banco.escritas.append((self.nome, "insert", dict(linha)))
            return type("R", (), {"data": [dict(linha)]})()
        casadas = [r for r in linhas if all(f(r) for f in self._filtros)]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            self._banco.escritas.append((self.nome, "update", dict(self._update)))
        if self._ordem:
            col, desc = self._ordem
            casadas = sorted(casadas, key=lambda r: str(r.get(col) or ""), reverse=desc)
        dados = [({c: r.get(c) for c in self._colunas} if self._colunas else dict(r)) for r in casadas]
        return type("R", (), {"data": dados})()


class _Banco:
    def __init__(self, *, pontos: list[dict] | None = None, global_ligado: bool = False, ligado_em=None):
        self.agora = "2026-11-12T15:00:00+00:00"
        self.escritas: list[tuple[str, str, dict]] = []
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_pontos": pontos if pontos is not None else [_ponto(CODIGO), _ponto(OUTRO)],
            "ouvidoria_config": [
                {
                    "id": True,
                    "google_place_id": "ChIJN5IUl-vfmwARsSET9nFjh70",
                    "google_review_url": URL_DO_GOOGLE,
                    "google_teste_global": global_ligado,
                    "google_teste_ligado_em": ligado_em,
                }
            ],
            "ouvidoria_avaliacoes": [],
            "ouvidoria_convite_google_auditoria": [],
        }

    def table(self, nome: str):
        return _Tabela(self, nome)

    @property
    def avaliacoes(self) -> list[dict]:
        return self.tabelas["ouvidoria_avaliacoes"]

    @property
    def auditoria(self) -> list[dict]:
        return self.tabelas["ouvidoria_convite_google_auditoria"]


def _publico(banco: _Banco) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_publica.router, prefix="/api")
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app, follow_redirects=False)


def _avaliar(client: TestClient, nota: int, codigo: str = CODIGO):
    return client.post(f"/api/ouvidoria/publico/pontos/{codigo}/avaliacoes", json={"nota": nota})


class TestOConviteSoComAsDuasChaves:
    """CA: com uma das chaves desligada, nota 4 ou 5 não mostra o convite;
    com as duas ligadas, mostra e grava convite exibido."""

    @pytest.mark.parametrize(
        ("global_ligado", "ponto_ligado"),
        [(False, False), (True, False), (False, True)],
    )
    def test_uma_chave_desligada_nao_mostra_o_convite(self, global_ligado, ponto_ligado):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=ponto_ligado)], global_ligado=global_ligado)
        client = _publico(banco)

        r = _avaliar(client, 5)

        assert r.status_code == 201, r.text
        assert r.json()["convite_google"] is False
        assert banco.avaliacoes[0]["convite_google_exibido"] is False

    @pytest.mark.parametrize("nota", [4, 5])
    def test_as_duas_chaves_ligadas_mostram_e_gravam_o_convite(self, nota):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)
        client = _publico(banco)

        r = _avaliar(client, nota)

        assert r.status_code == 201, r.text
        assert r.json()["convite_google"] is True
        assert banco.avaliacoes[0]["convite_google_exibido"] is True

    def test_a_chave_de_outro_ponto_nao_liga_este(self):
        banco = _Banco(pontos=[_ponto(CODIGO), _ponto(OUTRO, convite=True)], global_ligado=True)
        client = _publico(banco)

        r = _avaliar(client, 5, CODIGO)

        assert r.json()["convite_google"] is False

    def test_falha_ao_ler_a_configuracao_grava_a_nota_sem_convite(self):
        """O convite é o que se perde, nunca a nota."""
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)
        banco.tabelas.pop("ouvidoria_config")
        original = banco.table

        def _quebra(nome):
            if nome == "ouvidoria_config":
                raise RuntimeError("PostgREST fora do ar")
            return original(nome)

        banco.table = _quebra
        client = _publico(banco)

        r = _avaliar(client, 5)

        assert r.status_code == 201, r.text
        assert r.json()["convite_google"] is False
        assert banco.avaliacoes[0]["convite_google_exibido"] is False


class TestNotasBaixasNuncaConvidam:
    """CA: notas 1 a 3 nunca mostram o convite."""

    @pytest.mark.parametrize("nota", [1, 2, 3])
    def test_nota_de_1_a_3_nao_mostra_o_convite_nem_com_tudo_ligado(self, nota):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)
        client = _publico(banco)

        r = _avaliar(client, nota)

        assert r.status_code == 201, r.text
        assert r.json()["convite_google"] is False
        assert banco.avaliacoes[0]["convite_google_exibido"] is False


def _clique(client: TestClient, avaliacao_id: str):
    return client.get(f"/api/ouvidoria/publico/avaliacoes/{avaliacao_id}/convite-google")


class TestOCliqueEContadoAntesDeRedirecionar:
    """CA: o clique é gravado antes do redirecionamento."""

    def test_o_clique_grava_e_so_entao_redireciona_ao_link_da_configuracao(self):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)
        client = _publico(banco)
        avaliacao_id = _avaliar(client, 5).json()["id"]

        r = _clique(client, avaliacao_id)

        assert r.status_code == 302
        assert r.headers["location"] == URL_DO_GOOGLE
        assert banco.avaliacoes[0]["convite_google_clicado"] is True
        # A escrita do clique aconteceu dentro do pedido, antes da resposta que
        # leva a pessoa ao Google.
        assert ("ouvidoria_avaliacoes", "update", {"convite_google_clicado": True}) in banco.escritas

    def test_clique_numa_nota_que_nao_viu_o_convite_nao_conta(self):
        """Quem chama a rota com o id de uma nota sem convite não infla a taxa."""
        banco = _Banco(pontos=[_ponto(CODIGO)], global_ligado=True)
        client = _publico(banco)
        avaliacao_id = _avaliar(client, 5).json()["id"]

        r = _clique(client, avaliacao_id)

        assert r.status_code == 302
        assert banco.avaliacoes[0]["convite_google_clicado"] is False

    def test_o_destino_vem_so_da_configuracao(self):
        """Nada da URL do pedido decide para onde a pessoa vai, e link que não
        é https não vira redirecionamento."""
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)
        client = _publico(banco)
        avaliacao_id = _avaliar(client, 5).json()["id"]
        banco.tabelas["ouvidoria_config"][0]["google_review_url"] = "javascript:alert(1)"

        r = client.get(
            f"/api/ouvidoria/publico/avaliacoes/{avaliacao_id}/convite-google",
            params={"url": "https://exemplo.com"},
        )

        assert r.status_code == 404


def _admin(monkeypatch, participante: dict, banco: _Banco) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


class TestSoADiretoriaLigaEDesliga:
    """CA: só a diretoria executiva liga e desliga; ouvidor recebe 403; cada
    mudança grava de/para."""

    def test_a_diretoria_liga_a_chave_geral_e_a_auditoria_grava_de_para(self, monkeypatch):
        banco = _Banco()
        client = _admin(monkeypatch, DIRETORIA, banco)

        r = client.put("/api/ouvidoria/convite-google", json={"ligado": True})

        assert r.status_code == 200, r.text
        config = banco.tabelas["ouvidoria_config"][0]
        assert config["google_teste_global"] is True
        assert config["google_teste_ligado_em"]
        assert r.json()["global"] is True
        [registro] = banco.auditoria
        assert registro["chave"] == "global"
        assert registro["ponto_id"] is None
        assert (registro["valor_anterior"], registro["valor_novo"]) == (False, True)
        assert registro["alterado_por"] == "P11"
        assert registro["alterado_por_nome"] == "Dr. Diretor"

    def test_a_diretoria_liga_a_chave_do_ponto_e_a_auditoria_grava_de_para(self, monkeypatch):
        banco = _Banco()
        client = _admin(monkeypatch, DIRETORIA, banco)

        r = client.put(f"/api/ouvidoria/pontos/ponto-{CODIGO}/convite-google", json={"ligado": True})

        assert r.status_code == 200, r.text
        pontos = {p["id"]: p for p in banco.tabelas["ouvidoria_pontos"]}
        assert pontos[f"ponto-{CODIGO}"]["google_teste_ativo"] is True
        assert pontos[f"ponto-{OUTRO}"]["google_teste_ativo"] is False
        [registro] = banco.auditoria
        assert registro["chave"] == "ponto"
        assert registro["ponto_id"] == f"ponto-{CODIGO}"
        assert (registro["valor_anterior"], registro["valor_novo"]) == (False, True)
        assert registro["alterado_por"] == "P11"

    def test_desligar_grava_de_ligado_para_desligado(self, monkeypatch):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True, ligado_em="2026-09-01T12:00:00+00:00")
        client = _admin(monkeypatch, DIRETORIA, banco)

        client.put("/api/ouvidoria/convite-google", json={"ligado": False})
        client.put(f"/api/ouvidoria/pontos/ponto-{CODIGO}/convite-google", json={"ligado": False})

        assert [(a["chave"], a["valor_anterior"], a["valor_novo"]) for a in banco.auditoria] == [
            ("global", True, False),
            ("ponto", True, False),
        ]
        assert banco.tabelas["ouvidoria_config"][0]["google_teste_global"] is False

    def test_salvar_o_mesmo_valor_nao_e_mudanca(self, monkeypatch):
        banco = _Banco(global_ligado=True, ligado_em="2026-09-01T12:00:00+00:00")
        client = _admin(monkeypatch, DIRETORIA, banco)

        r = client.put("/api/ouvidoria/convite-google", json={"ligado": True})

        assert r.status_code == 200
        assert banco.auditoria == []
        # Religar o que já estava ligado não recomeça os 60 dias.
        assert banco.tabelas["ouvidoria_config"][0]["google_teste_ligado_em"] == "2026-09-01T12:00:00+00:00"

    @pytest.mark.parametrize(
        "rota",
        ["/api/ouvidoria/convite-google", f"/api/ouvidoria/pontos/ponto-{CODIGO}/convite-google"],
    )
    def test_o_ouvidor_recebe_403_e_nada_muda(self, monkeypatch, rota):
        banco = _Banco()
        client = _admin(monkeypatch, OUVIDOR, banco)

        r = client.put(rota, json={"ligado": True})

        assert r.status_code == 403
        assert banco.auditoria == []
        assert banco.tabelas["ouvidoria_config"][0]["google_teste_global"] is False
        assert all(p["google_teste_ativo"] is False for p in banco.tabelas["ouvidoria_pontos"])

    def test_a_edicao_do_ponto_nao_liga_a_chave_por_tras(self, monkeypatch):
        """O PATCH do cartaz é dos dois perfis: a chave não pode passar por ele."""
        banco = _Banco()
        client = _admin(monkeypatch, OUVIDOR, banco)

        r = client.patch(f"/api/ouvidoria/pontos/ponto-{CODIGO}", json={"ponto": "Hall", "google_teste_ativo": True})

        assert r.status_code == 200, r.text
        assert banco.tabelas["ouvidoria_pontos"][0]["google_teste_ativo"] is False

    def test_ponto_que_nao_existe_e_404(self, monkeypatch):
        banco = _Banco()
        client = _admin(monkeypatch, DIRETORIA, banco)

        r = client.put("/api/ouvidoria/pontos/ponto-nenhum/convite-google", json={"ligado": True})

        assert r.status_code == 404
        assert banco.auditoria == []

    def test_a_tela_de_pontos_le_a_chave_geral_e_a_de_cada_ponto(self, monkeypatch):
        banco = _Banco(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True, ligado_em="2026-09-01T12:00:00+00:00")
        client = _admin(monkeypatch, OUVIDOR, banco)

        r = client.get("/api/ouvidoria/pontos")

        assert r.status_code == 200, r.text
        assert r.json()["convite_google"] == {"global": True, "ligado_em": "2026-09-01T12:00:00+00:00"}
        assert r.json()["pontos"][0]["google_teste_ativo"] is True
