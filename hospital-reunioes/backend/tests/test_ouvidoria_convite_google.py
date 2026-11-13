"""O teste do convite ao Google no QR (issue #1625, PRD #1527, ADR 0089).

Quem dá nota 4 ou 5 no cartaz vê o convite para avaliar o hospital no Google,
só com a chave geral e a chave do ponto ligadas. Só a diretoria executiva
liga e desliga, com auditoria de/para. O clique passa por uma rota que conta
antes de redirecionar, e a Central mostra convites, cliques e taxa por ponto,
com o aviso de reavaliar depois de 60 dias.

Os testes sobem as rotas reais com um banco falso em memória.
"""

from __future__ import annotations

import datetime as dt
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
        self._recorte: tuple[int, int] | None = None

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

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
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
        if self._recorte:
            casadas = casadas[self._recorte[0] : self._recorte[1] + 1]
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


HOJE = dt.date(2026, 11, 13)


def _avaliacao(ponto: str, criada_em: str, *, clicou: bool = False, convite: bool = True) -> dict:
    return {
        "id": f"av-{ponto}-{criada_em}-{clicou}",
        "ponto_id": f"ponto-{ponto}",
        "canal": "qr",
        "nota": 5,
        "criada_em": criada_em,
        "convite_google_exibido": convite,
        "convite_google_clicado": clicou,
    }


class _BancoDaCentral(_Banco):
    """O gate da Central lê `participantes`; os números, as tabelas da Ouvidoria."""

    def __init__(self, **kwargs):
        from central_de_comando_apoio import FACILITADOR, SECRETARIA, SUPER_ADMIN, SupabaseDosParticipantes

        super().__init__(**kwargs)
        self._gate = SupabaseDosParticipantes([SUPER_ADMIN, SECRETARIA, FACILITADOR])

    def table(self, nome: str):
        return self._gate.table(nome) if nome == "participantes" else super().table(nome)


def _lente(monkeypatch, banco: _Banco, periodo: str = "28d") -> dict:
    from central_de_comando_apoio import PREFIXO_DA_CENTRAL, SUPER_ADMIN, cliente_da_central

    from app.services.central_de_comando import periodo as periodo_da_central

    monkeypatch.setattr(periodo_da_central, "hoje_utc", lambda *_a: HOJE)
    cliente = cliente_da_central(SUPER_ADMIN)
    cliente.app.dependency_overrides[get_supabase_client] = lambda: banco
    r = cliente.get(f"{PREFIXO_DA_CENTRAL}/objetivos/google-reputacao", params={"periodo": periodo})
    assert r.status_code == 200, r.text
    return r.json()["convite"]


@pytest.mark.usefixtures("gate_e_limitador_zerados")
class TestACentralMedeOTeste:
    """CA: a Central mostra convites, cliques e taxa por ponto e o aviso depois
    de 60 dias, e o convite continua aparecendo."""

    def test_convites_cliques_e_taxa_por_ponto_no_periodo(self, monkeypatch):
        banco = _BancoDaCentral(
            pontos=[_ponto(CODIGO, convite=True), _ponto(OUTRO, convite=True, nome="Centro médico")],
            global_ligado=True,
            ligado_em="2026-10-20T12:00:00+00:00",
        )
        banco.tabelas["ouvidoria_avaliacoes"] = [
            _avaliacao(CODIGO, "2026-11-01T13:00:00+00:00", clicou=True),
            _avaliacao(CODIGO, "2026-11-05T13:00:00+00:00"),
            _avaliacao(CODIGO, "2026-11-06T13:00:00+00:00"),
            _avaliacao(CODIGO, "2026-11-07T13:00:00+00:00", clicou=True),
            _avaliacao(OUTRO, "2026-11-08T13:00:00+00:00"),
            # Fora do período de 28 dias (16/10 a 12/11): antes e hoje.
            _avaliacao(CODIGO, "2026-10-10T13:00:00+00:00", clicou=True),
            _avaliacao(CODIGO, "2026-11-13T13:00:00+00:00", clicou=True),
            # A nota que não viu o convite não entra na conta.
            _avaliacao(OUTRO, "2026-11-08T14:00:00+00:00", convite=False),
        ]

        convite = _lente(monkeypatch, banco)

        assert convite["ligado"] is True
        assert convite["intervalo"] == {"inicio": "2026-10-16", "fim": "2026-11-12"}
        por_nome = {p["nome"]: p for p in convite["pontos"]}
        assert por_nome["Emergência adulta"]["convites"] == 4
        assert por_nome["Emergência adulta"]["cliques"] == 2
        assert por_nome["Emergência adulta"]["taxa"] == 0.5
        assert por_nome["Centro médico"]["convites"] == 1
        assert por_nome["Centro médico"]["cliques"] == 0
        assert por_nome["Centro médico"]["taxa"] == 0.0
        assert convite["total"] == {"convites": 5, "cliques": 2, "taxa": 0.4}

    def test_antes_dos_60_dias_nao_avisa(self, monkeypatch):
        banco = _BancoDaCentral(global_ligado=True, ligado_em="2026-10-20T12:00:00+00:00")

        convite = _lente(monkeypatch, banco)

        assert convite["dias_ligado"] == 24
        assert convite["reavaliar"] is False

    def test_depois_de_60_dias_avisa_e_o_convite_continua_aparecendo(self, monkeypatch):
        ligado_em = "2026-09-01T12:00:00+00:00"
        banco = _BancoDaCentral(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True, ligado_em=ligado_em)

        convite = _lente(monkeypatch, banco)

        assert convite["dias_ligado"] == 73
        assert convite["reavaliar"] is True
        # O teste não se desliga sozinho (ADR 0089, decisão 7).
        r = _avaliar(_publico(banco), 5)
        assert r.json()["convite_google"] is True

    def test_desligado_nao_avisa_nem_conta_dias(self, monkeypatch):
        banco = _BancoDaCentral(global_ligado=False, ligado_em="2026-09-01T12:00:00+00:00")

        convite = _lente(monkeypatch, banco)

        assert convite["ligado"] is False
        assert convite["reavaliar"] is False
        assert convite["dias_ligado"] is None

    def test_ponto_sem_convite_no_periodo_fica_sem_taxa(self, monkeypatch):
        banco = _BancoDaCentral(pontos=[_ponto(CODIGO, convite=True)], global_ligado=True)

        convite = _lente(monkeypatch, banco, "7d")

        assert convite["intervalo"] == {"inicio": "2026-11-06", "fim": "2026-11-12"}
        assert convite["total"] == {"convites": 0, "cliques": 0, "taxa": None}
