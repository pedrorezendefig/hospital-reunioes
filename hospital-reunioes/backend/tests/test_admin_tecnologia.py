"""A fundacao da aba Tecnologia (issue #636, PRD #634, ADR 0050).

Dois blocos, dois seams:

* **A migration 102**, lida como texto. O repo nao tem Postgres na suite e a
  migration e aplicada a mao no Studio, entao o que da para provar aqui e o que
  o arquivo manda o banco fazer. Molde: `TestMigration` de
  `test_ouvidoria_retencao.py`.
* **O gate**, pela ROTA de verdade, com `require_super_admin` de pe. So
  `get_current_user` e `get_supabase_client` sao dublados: trocar a guarda por
  um dublê deixaria o teste verde sobre nada.

As regras de Produto e a tela de Produtos sairam com a ADR 0077 (issue #1386):
a aba e o chat do agente.
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

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services.tecnologia import ESTADOS_ABERTOS, ESTADOS_FECHADOS  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda a contagem num storage de PROCESSO.

    As rotas do chat tem `@limiter.limit`, e o `TestClient` sempre chega do
    mesmo endereco: sem este reset, o request que passa do teto leva 429 e o
    teste que quebra e o proximo da fila, nao o que estourou o teto.
    """
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ─── Supabase dublê ──────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    """PostgREST minimo: select/eq/in_/order/range/insert/update, e nada mais.

    `range` entrou com a issue #641: as duas rotas de recorte da lista leem
    paginado (`ler_tudo`), e sem ele a matriz de gate morreria de
    `AttributeError` em vez de medir o 403. `order` acumula as colunas, porque
    essas leituras ordenam por duas.
    """

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._order: list[str] = []
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order.append(coluna)
        return self

    def range(self, inicio, fim):
        self._range = (inicio, fim)
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

        for coluna in reversed(self._order):
            casadas.sort(key=lambda linha, c=coluna: (linha.get(c) is None, linha.get(c)))
        if self._range is not None:
            inicio, fim = self._range
            casadas = casadas[inicio : fim + 1]
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
    github_login: str | None = None,
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
        "github_login": github_login,
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
    # O limitador das rotas do chat precisa do `app.state` (o `main.py` faz o
    # mesmo): sem ele, `@limiter.limit` estoura em vez de limitar.
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
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

    def test_abertos_e_fechados_sao_o_complemento_um_do_outro(self):
        """O estado de antes da ADR 0077 fica congelado na coluna, e a
        sincronizacao da Etapa e o apagamento dos prints ainda o leem pelos dois
        grupos. Um estado que ficasse de fora dos dois sumiria da reconciliacao
        em silencio; um que estivesse nos dois seria lido como aberto e
        fechado."""
        assert set(ESTADOS_ABERTOS) == {"nova", "em_andamento", "aguardando"}
        assert set(ESTADOS_FECHADOS) == {"concluida", "cancelada"}

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


class TestMigrationDoProdutoCentralDeComando:
    """O Produto "Central de Comando" (issue #827, ADR 0058): entra por migration
    idempotente, no molde do seed da 102, e nasce COM dono.

    O dono nao e inventado: e o do Site, que um Super admin ja escolheu na tela.
    A Central sao os numeros do Site e do Instagram, e quem responde pelo Site do
    lado da Vitta e quem responde por eles. Quem ja escolheu um dono para a
    Central pela tela nao perde a escolha, e o Site sem dono deixa a Central sem
    dono tambem, para a tela cobrar como cobra dos sete do seed.
    """

    @pytest.fixture
    def comandos(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "111_tecnologia_produto_central_de_comando.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            ddl = f.read()
        linhas = (linha for linha in ddl.lower().splitlines() if not linha.strip().startswith("--"))
        return re.sub(r"\s+", " ", " ".join(linhas))

    def test_o_produto_entra_so_com_nome_e_ordem(self, comandos):
        assert "insert into tecnologia_produtos (nome, ordem) values ('central de comando'," in comandos

    def test_a_ordem_e_a_proxima_livre_como_no_cadastro_da_tela(self, comandos):
        assert "(select coalesce(max(ordem), 0) + 1 from tecnologia_produtos)" in comandos

    def test_a_insercao_e_idempotente(self, comandos):
        assert "on conflict do nothing" in comandos

    def test_o_dono_e_o_do_site(self, comandos):
        """Mutante: tirar o UPDATE deixa a Central sem dono, e a API recusa
        criar Demanda em Produto sem dono."""
        assert "set dono_id = site.dono_id" in comandos
        assert "lower(site.nome) = 'site'" in comandos
        assert "lower(central.nome) = 'central de comando'" in comandos

    def test_nao_sobrescreve_o_dono_escolhido_na_tela(self, comandos):
        """Mutante: tirar a guarda faz rodar de novo trocar o dono que alguem
        ja escolheu para a Central pela tela."""
        assert "central.dono_id is null" in comandos

    def test_site_sem_dono_nao_apaga_nada(self, comandos):
        assert "site.dono_id is not null" in comandos

    def test_so_escreve_nos_produtos(self, comandos):
        escritas = set(re.findall(r"(?:insert into|update|alter table|delete from)\s+(\w+)", comandos))
        assert escritas == {"tecnologia_produtos"}


# ─── 2. O gate ───────────────────────────────────────────────────────────────


PREFIXO = "/api/admin/tecnologia"


def _rotas_da_aba() -> list[tuple[str, str, dict | None]]:
    """Toda rota de `admin/tecnologia` que o app REALMENTE publica.

    Varredura, e nao lista cravada: o gate e o produto desta fatia, e uma rota
    acrescentada ao router numa fatia seguinte sem `require_super_admin`
    entraria sem deixar teste vermelho.

    A fonte e o schema OpenAPI, e nao `app.routes`: desde o FastAPI 0.141 o
    `include_router` guarda o router incluido em vez de copiar as rotas para
    cima, e a lista volta quase vazia. Isso nao daria erro, daria varredura
    vazia, que e o pior jeito de uma defesa morrer (mordeu nas issues #542 e
    #546). O piso de sanidade abaixo e a trava contra isso.
    """
    from app.main import app

    # `app.openapi()` CACHEIA o schema em `app.openapi_schema`, e esta varredura
    # roda na coleta. Congelar o cache aqui envelheceria o schema para quem
    # acrescenta rota ao app real depois (o `test_handler_global_excecao.py`
    # registra uma em tempo de import), e o
    # `test_nenhuma_rota_esta_escondida_do_schema` ficaria vermelho por
    # contaminação, nao por defeito. Por isso o cache volta como estava.
    cache = app.openapi_schema
    try:
        caminhos = app.openapi()["paths"]
    finally:
        app.openapi_schema = cache

    achadas: list[tuple[str, str, dict | None]] = []
    for caminho, operacoes in caminhos.items():
        if not caminho.startswith(PREFIXO):
            continue
        # `{demanda_id}` e afins viram um id qualquer: o que se mede aqui e o
        # gate, que responde antes de o id existir ou nao.
        concreto = re.sub(r"\{[^}]+\}", "prod-1", caminho)
        for metodo in operacoes:
            verbo = metodo.upper()
            corpo = {"nome": "Novo Produto", "dono_id": "P1"} if verbo in ("POST", "PUT", "PATCH") else None
            achadas.append((verbo, concreto, corpo))
    return sorted(achadas)


ROTAS = _rotas_da_aba()


def test_a_varredura_enxerga_as_rotas_da_aba():
    """Controle, antes de qualquer asserção sobre a matriz: varredura vazia
    satisfaz "toda rota responde 403" sem olhar rota nenhuma.

    O piso é o número de operações que a aba publica hoje, desde que ela virou
    o chat do agente (issue #1386, ADR 0077): a lista e o primeiro turno, ler e
    responder a conversa, o "Não bateu", o "Fechar e resumir", o "Criar o card"
    e a leitura do print. Ele acompanha a aba de propósito. Um piso que ficasse
    para trás deixaria de guardar as rotas novas: bastaria um refactor mover o
    chat para outro prefixo para a varredura cair, este teste continuar VERDE e
    as rotas saírem da matriz de 403 em silêncio, que é a morte por varredura
    parcial das issues #542 e #546. Fatia que acrescentar rota sobe o número
    junto.
    """
    assert len(ROTAS) >= 8, f"a varredura só achou {len(ROTAS)} rotas em {PREFIXO}: {ROTAS}"


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
    passaria pelos dois. A persona e o diretor, sem `github_login`: o chat nao
    tem segundo gate (ADR 0077)."""
    dono = _pessoa("P1", "Diretor do Hospital")
    client, _ = _montar(
        logado=dono,
        participantes=[dono],
        produtos=[_produto("prod-1", "Ana", ordem=1, dono_id="P1")],
    )
    resposta = client.request(metodo, caminho, json=corpo)
    assert resposta.status_code != 403
    assert resposta.status_code < 500
