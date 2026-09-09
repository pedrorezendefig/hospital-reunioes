"""A fundacao da aba Tecnologia (issue #636, PRD #634, ADR 0050).

Tres blocos, tres seams:

* **A migration 102**, lida como texto. O repo nao tem Postgres na suite e a
  migration e aplicada a mao no Studio, entao o que da para provar aqui e o que
  o arquivo manda o banco fazer. Molde: `TestMigration` de
  `test_ouvidoria_retencao.py`.
* **O gate**, pela ROTA de verdade, com `require_super_admin` de pe. So
  `get_current_user` e `get_supabase_client` sao dublados: trocar a guarda por
  um dublê deixaria o teste verde sobre nada.
* **As regras de Produto**, tambem pela rota, com o Supabase dublado. A regra
  pura ("ativo exige dono") tem ainda o seu teste direto, sem HTTP.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services.tecnologia import e_pessoa_da_aba, produto_ativo_sem_dono  # noqa: E402

# ─── Supabase dublê ──────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    """PostgREST minimo: select/eq/in_/order/insert/update, e nada mais."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._order: str | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order = coluna
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def insert(self, payload):
        linhas = payload if isinstance(payload, list) else [payload]
        self._insert = [dict(linha) for linha in linhas]
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        if self._insert is not None:
            for linha in self._insert:
                linha.setdefault("id", f"prod-{len(self._rows) + 1}")
                linha.setdefault("ordem", 0)
                linha.setdefault("ativo", True)
                linha.setdefault("dono_id", None)
            self._rows.extend(self._insert)
            return _Result(data=[dict(linha) for linha in self._insert])

        casadas = [linha for linha in self._rows if self._casa(linha)]

        if self._update is not None:
            for linha in casadas:
                linha.update(self._update)
            return _Result(data=[dict(linha) for linha in casadas])

        if self._order:
            casadas.sort(key=lambda linha: (linha.get(self._order) is None, linha.get(self._order)))
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []))


# ─── Pessoas e telas de teste ────────────────────────────────────────────────


def _pessoa(
    pid: str,
    nome: str,
    *,
    access_profile: str | None = "super_admin",
    ativo: bool | None = True,
) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid}@hsm.com",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": ativo,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "data_cadastro": "2026-01-01",
    }


def _produto(pid: str, nome: str, *, ordem: int, dono_id: str | None = None, ativo: bool = True) -> dict:
    return {"id": pid, "nome": nome, "ativo": ativo, "ordem": ordem, "dono_id": dono_id}


def _montar(
    *,
    logado: dict,
    participantes: list[dict] | None = None,
    produtos: list[dict] | None = None,
) -> tuple[TestClient, _SupabaseMock]:
    app = FastAPI()
    app.include_router(tecnologia_router.router, prefix="/api")

    pessoas = list(participantes if participantes is not None else [])
    if all(p["id"] != logado["id"] for p in pessoas):
        pessoas.append(logado)

    sb = _SupabaseMock(
        tabelas={
            "participantes": pessoas,
            "tecnologia_produtos": list(produtos or []),
        }
    )

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb


# ─── 1. A migration 102 ──────────────────────────────────────────────────────


TABELAS = ("tecnologia_produtos", "tecnologia_demandas", "tecnologia_conversas")

SETE_PRODUTOS = (
    "Ana",
    "Integração Ana x MV",
    "Reuniões",
    "Ouvidoria",
    "POPs",
    "Site",
    "Infra",
)


class TestMigration:
    """As tres tabelas nascem juntas, no formato final da PRD, com RLS ligado e
    sem policy, e os sete Produtos entram sem dono."""

    @pytest.fixture
    def ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "102_tecnologia_fundacao.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read()

    @pytest.fixture
    def comandos(self, ddl) -> str:
        """So o SQL, sem os comentarios: afirmar o que a migration NAO faz
        exige olhar os comandos, nao a prosa que explica o porque."""
        return "\n".join(linha for linha in ddl.lower().splitlines() if not linha.strip().startswith("--"))

    @pytest.mark.parametrize("tabela", TABELAS)
    def test_cada_tabela_nasce_aqui(self, comandos, tabela):
        assert f"create table if not exists {tabela}" in comandos

    @pytest.mark.parametrize("tabela", TABELAS)
    def test_cada_tabela_nasce_com_rls_ligado(self, comandos, tabela):
        assert f"alter table {tabela} enable row level security" in comandos

    def test_nenhuma_policy(self, comandos):
        """Default-deny da casa: RLS ligado e policy nenhuma, entao so a
        service_role passa. Uma policy aqui abriria a tabela para a anon_key
        que vai no bundle do frontend."""
        assert "create policy" not in comandos

    @pytest.mark.parametrize("nome", SETE_PRODUTOS)
    def test_os_sete_produtos_entram_no_seed(self, ddl, nome):
        assert f"('{nome}'," in ddl

    def test_o_seed_nao_carimba_dono(self, comandos):
        """O dono e definido na tela antes do primeiro uso: a migration nao
        inventa um. As colunas do INSERT sao so nome e ordem."""
        assert "insert into tecnologia_produtos (nome, ordem)" in comandos

    def test_o_seed_e_idempotente(self, comandos):
        assert "on conflict do nothing" in comandos

    @pytest.mark.parametrize(
        "indice",
        (
            "idx_tecnologia_demandas_estado",
            "idx_tecnologia_demandas_responsavel",
            "idx_tecnologia_demandas_produto",
        ),
    )
    def test_indices_da_demanda(self, comandos, indice):
        """Os tres eixos por onde a tela varre: coluna do Quadro, Minha vez e
        filtro por Produto."""
        assert f"create index if not exists {indice}" in comandos

    def test_tipo_da_demanda_e_a_lista_fechada_de_sete(self, comandos):
        for tipo in ("decisao", "informacao", "terceiro", "ajuste", "novo", "defeito", "consultoria"):
            assert f"'{tipo}'" in comandos

    def test_estado_da_demanda_e_a_lista_fechada_de_cinco(self, comandos):
        for estado in ("nova", "em_andamento", "aguardando", "concluida", "cancelada"):
            assert f"'{estado}'" in comandos

    def test_produto_com_demanda_nao_e_apagado(self, comandos):
        """ON DELETE RESTRICT: a saida do Produto e desativar, nao apagar."""
        assert "references tecnologia_produtos(id) on delete restrict" in comandos

    def test_nao_encosta_nas_pendencias(self, comandos):
        """A aba e apartada das Pendencias de Ata (ADR 0050).

        A prova nao pode ser "a palavra pendencias nao aparece": ela aparece
        nos COMMENT, justamente dizendo que nada aqui le aquela tabela. O que
        se afirma e o conjunto de tabelas que a migration escreve e referencia.
        """
        escritas = set(re.findall(r"(?:create table if not exists|alter table|insert into)\s+(\w+)", comandos))
        assert escritas == set(TABELAS)

        referenciadas = set(re.findall(r"references\s+(\w+)\(", comandos))
        assert referenciadas == {"participantes", "tecnologia_produtos", "tecnologia_demandas"}


# ─── 2. O gate ───────────────────────────────────────────────────────────────


ROTAS = [
    ("GET", "/api/admin/tecnologia/pessoas", None),
    ("GET", "/api/admin/tecnologia/produtos", None),
    ("POST", "/api/admin/tecnologia/produtos", {"nome": "Novo Produto", "dono_id": "P1"}),
    ("PATCH", "/api/admin/tecnologia/produtos/prod-1", {"nome": "Renomeado"}),
]

PERSONAS_SEM_ACESSO = {
    "facilitador": "regular",
    "secretaria": "secretaria",
    "sem_papel": None,
}


@pytest.mark.parametrize("metodo,caminho,corpo", ROTAS, ids=lambda v: v if isinstance(v, str) else "")
@pytest.mark.parametrize("persona", list(PERSONAS_SEM_ACESSO))
def test_quem_nao_e_super_admin_leva_403(persona, metodo, caminho, corpo):
    dono = _pessoa("P1", "Dona Vitta")
    intruso = _pessoa("P9", "Fulano", access_profile=PERSONAS_SEM_ACESSO[persona])
    client, _ = _montar(
        logado=intruso,
        participantes=[dono, intruso],
        produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")],
    )
    assert client.request(metodo, caminho, json=corpo).status_code == 403


@pytest.mark.parametrize("metodo,caminho,corpo", ROTAS, ids=lambda v: v if isinstance(v, str) else "")
def test_super_admin_passa_em_todas(metodo, caminho, corpo):
    """O par de presenca do teste acima: sem ele, um 403 cravado em toda rota
    passaria pelos dois."""
    dono = _pessoa("P1", "Dona Vitta")
    client, _ = _montar(
        logado=dono,
        participantes=[dono],
        produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")],
    )
    resposta = client.request(metodo, caminho, json=corpo)
    assert resposta.status_code != 403
    assert resposta.status_code < 500


# ─── 3. A lista de pessoas com acesso a aba ──────────────────────────────────


class TestPessoasDaAba:
    def test_so_participante_ativo_com_super_admin(self):
        dentro = _pessoa("P1", "Ativa Super")
        fora = [
            _pessoa("P2", "Inativa Super", ativo=False),
            _pessoa("P3", "Facilitador", access_profile="regular"),
            _pessoa("P4", "Secretaria", access_profile="secretaria"),
        ]
        client, _ = _montar(logado=dentro, participantes=[dentro, *fora])

        corpo = client.get("/api/admin/tecnologia/pessoas").json()

        assert [p["id"] for p in corpo] == ["P1"]
        assert corpo[0]["nome_completo"] == "Ativa Super"

    def test_ativo_nulo_conta_como_ativo(self):
        """`ativo` nasceu com DEFAULT TRUE e linha antiga pode estar NULL.
        Tratar NULL como inativo tiraria da lista gente que usa o app."""
        assert e_pessoa_da_aba(_pessoa("P1", "Sem carimbo", ativo=None)) is True

    def test_desativado_fica_de_fora_mesmo_com_super_admin(self):
        assert e_pessoa_da_aba(_pessoa("P1", "Saiu", ativo=False)) is False

    def test_regular_ativo_fica_de_fora(self):
        assert e_pessoa_da_aba(_pessoa("P1", "Facilitador", access_profile="regular")) is False


# ─── 4. A regra pura do dono ─────────────────────────────────────────────────


class TestRegraDoDono:
    def test_ativo_sem_dono_e_recusado(self):
        assert produto_ativo_sem_dono(ativo=True, dono_id=None) is True

    def test_ativo_com_dono_passa(self):
        assert produto_ativo_sem_dono(ativo=True, dono_id="P1") is False

    def test_inativo_pode_ficar_sem_dono(self):
        assert produto_ativo_sem_dono(ativo=False, dono_id=None) is False


# ─── 5. Produtos pela tela ───────────────────────────────────────────────────


class TestProdutos:
    def test_lista_traz_os_produtos_na_ordem_de_exibicao(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(
            logado=dono,
            produtos=[
                _produto("prod-3", "Reuniões", ordem=3, dono_id="P1"),
                _produto("prod-1", "Ana", ordem=1, dono_id="P1"),
                _produto("prod-2", "Integração Ana x MV", ordem=2, dono_id="P1"),
            ],
        )

        corpo = client.get("/api/admin/tecnologia/produtos").json()

        assert [p["nome"] for p in corpo] == ["Ana", "Integração Ana x MV", "Reuniões"]

    def test_lista_resolve_o_nome_do_dono(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")])

        corpo = client.get("/api/admin/tecnologia/produtos").json()

        assert corpo[0]["dono_nome"] == "Dona Vitta"

    def test_produto_sem_dono_volta_sem_nome_de_dono(self):
        """O par de presenca do teste acima: `dono_nome` nulo aqui e o mesmo
        campo que resolve la, entao um `dono_nome` cravado quebraria um dos
        dois."""
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1)])

        corpo = client.get("/api/admin/tecnologia/produtos").json()

        assert corpo[0]["dono_nome"] is None

    def test_cria_produto_com_dono(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono)

        resposta = client.post(
            "/api/admin/tecnologia/produtos",
            json={"nome": "  Portal   do   Paciente ", "dono_id": "P1", "ordem": 8},
        )

        assert resposta.status_code == 201
        assert resposta.json()["nome"] == "Portal do Paciente"
        assert resposta.json()["dono_nome"] == "Dona Vitta"
        assert [p["nome"] for p in sb.tabelas["tecnologia_produtos"]] == ["Portal do Paciente"]

    def test_cria_produto_sem_dono_e_recusado_com_o_motivo(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono)

        resposta = client.post("/api/admin/tecnologia/produtos", json={"nome": "Portal"})

        assert resposta.status_code == 422
        assert "precisa de dono" in resposta.json()["detail"]
        assert sb.tabelas["tecnologia_produtos"] == []

    def test_dono_precisa_estar_na_lista_da_aba(self):
        dono = _pessoa("P1", "Dona Vitta")
        forasteiro = _pessoa("P9", "Facilitador", access_profile="regular")
        client, sb = _montar(logado=dono, participantes=[dono, forasteiro])

        resposta = client.post("/api/admin/tecnologia/produtos", json={"nome": "Portal", "dono_id": "P9"})

        assert resposta.status_code == 422
        assert "Super admin" in resposta.json()["detail"]
        assert sb.tabelas["tecnologia_produtos"] == []

    def test_nome_repetido_e_recusado_sem_distinguir_maiusculas(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")])

        resposta = client.post("/api/admin/tecnologia/produtos", json={"nome": "ana", "dono_id": "P1"})

        assert resposta.status_code == 409

    def test_renomeia_produto(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")])

        resposta = client.patch("/api/admin/tecnologia/produtos/prod-1", json={"nome": "Ana WhatsApp"})

        assert resposta.status_code == 200
        assert sb.tabelas["tecnologia_produtos"][0]["nome"] == "Ana WhatsApp"

    def test_desativar_nao_apaga_nem_esconde(self):
        """Criterio da issue: a linha continua no banco e volta na lista
        marcada como inativa."""
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")])

        assert client.patch("/api/admin/tecnologia/produtos/prod-1", json={"ativo": False}).status_code == 200

        assert len(sb.tabelas["tecnologia_produtos"]) == 1
        lista = client.get("/api/admin/tecnologia/produtos").json()
        assert [(p["nome"], p["ativo"]) for p in lista] == [("Ana", False)]

    def test_define_o_dono_pela_tela(self):
        dono = _pessoa("P1", "Dona Vitta")
        outro = _pessoa("P2", "Outro Socio")
        client, sb = _montar(
            logado=dono,
            participantes=[dono, outro],
            produtos=[_produto("prod-1", "Ana", ordem=1, ativo=False)],
        )

        resposta = client.patch(
            "/api/admin/tecnologia/produtos/prod-1",
            json={"dono_id": "P2", "ativo": True},
        )

        assert resposta.status_code == 200
        assert resposta.json()["dono_nome"] == "Outro Socio"
        assert sb.tabelas["tecnologia_produtos"][0]["dono_id"] == "P2"

    def test_tirar_o_dono_de_produto_ativo_e_recusado(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")])

        resposta = client.patch("/api/admin/tecnologia/produtos/prod-1", json={"dono_id": None})

        assert resposta.status_code == 422
        assert "precisa de dono" in resposta.json()["detail"]
        assert sb.tabelas["tecnologia_produtos"][0]["dono_id"] == "P1"

    def test_reativar_produto_sem_dono_e_recusado(self):
        """A regra vale sobre o RESULTADO da edicao: nem o corpo trouxe dono,
        nem a linha tinha um."""
        dono = _pessoa("P1", "Dona Vitta")
        client, sb = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1, ativo=False)])

        resposta = client.patch("/api/admin/tecnologia/produtos/prod-1", json={"ativo": True})

        assert resposta.status_code == 422
        assert sb.tabelas["tecnologia_produtos"][0]["ativo"] is False

    def test_desativar_produto_sem_dono_passa(self):
        """O par de presenca: a recusa e do ATIVO sem dono, nao de todo Produto
        sem dono."""
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(logado=dono, produtos=[_produto("prod-1", "Ana", ordem=1)])

        assert client.patch("/api/admin/tecnologia/produtos/prod-1", json={"ativo": False}).status_code == 200

    def test_produto_inexistente_da_404(self):
        dono = _pessoa("P1", "Dona Vitta")
        client, _ = _montar(logado=dono)

        assert client.patch("/api/admin/tecnologia/produtos/nao-existe", json={"nome": "X"}).status_code == 404
