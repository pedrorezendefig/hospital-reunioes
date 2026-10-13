"""A Habilitacao de Contas medicas e a migration 118 (issue #1139, PRD #1129).

A diretoria liga e desliga pela tela o que cada perfil do modulo pode fazer
(`cm_perfil_permissao`) e da ou tira o perfil de uma pessoa
(`participantes.perfil_contas_medicas`). Cada mudanca fica em `cm_registro`,
com autor, data, antes e depois. O guard le a matriz a cada requisicao: quem
perde a permissao recebe 403 ja na seguinte.

A matriz do duble do banco e lida da migration 116, como no teste da fundacao:
o que o teste confere e o que o Studio gravou.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client, require_permissao_cm  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas as contas_medicas_router  # noqa: E402
from app.routers import contas_medicas_habilitacao as habilitacao_router  # noqa: E402
from app.routers import participantes as participantes_router  # noqa: E402

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION_118 = MIGRATIONS / "118_contas_medicas_gestao.sql"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A migration 118
# ═══════════════════════════════════════════════════════════════════════════

# As tabelas das decisoes de implementacao do PRD #1129, escritas a mao.
TABELAS_DA_118 = (
    "cm_regra_historico",
    "cm_validacao_tema",
    "cm_validacao_tema_linha",
    "cm_cenario",
    "cm_cenario_item",
    "cm_lembrete",
    "cm_lembrete_item",
    "cm_contrato",
    "cm_aviso",
    "cm_registro",
)

# Dado de paciente que nao pode morar em tabela nenhuma (ADR 0070, decisao 8).
COLUNAS_PROIBIDAS = (
    "nome_completo",
    "nome_paciente",
    "paciente_nome",
    "nome_mae",
    "cpf",
    "rg",
    "cns",
    "carteira",
    "carteirinha",
    "data_nascimento",
    "nascimento",
    "endereco",
    "telefone",
)

_PALAVRAS_DE_RESTRICAO = {"primary", "unique", "check", "foreign", "constraint", "exclude"}


def _sql_sem_comentarios() -> str:
    return re.sub(r"--[^\n]*", "", MIGRATION_118.read_text(encoding="utf-8"))


def _tabelas_criadas() -> dict[str, list[str]]:
    """Cada `CREATE TABLE cm_*` da migration com as colunas dele."""
    tabelas: dict[str, list[str]] = {}
    for nome, corpo in re.findall(
        r"CREATE TABLE IF NOT EXISTS (cm_\w+)\s*\((.*?)\n\);", _sql_sem_comentarios(), flags=re.DOTALL
    ):
        colunas = []
        for linha in corpo.splitlines():
            palavra = re.match(r"\s*([a-z_][a-z0-9_]*)\s", linha)
            if palavra and palavra.group(1).lower() not in _PALAVRAS_DE_RESTRICAO:
                colunas.append(palavra.group(1))
        tabelas[nome] = colunas
    return tabelas


class TestMigration118:
    def test_cria_as_tabelas_do_prd_e_so_elas(self):
        """Mutante: apagar o CREATE de uma tabela."""
        assert sorted(_tabelas_criadas()) == sorted(TABELAS_DA_118)

    @pytest.mark.parametrize("tabela", TABELAS_DA_118)
    def test_toda_tabela_tem_rls_ligado(self, tabela):
        """Mutante: tirar o ENABLE ROW LEVEL SECURITY de uma tabela."""
        assert re.search(rf"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;", _sql_sem_comentarios())

    @pytest.mark.parametrize("tabela", TABELAS_DA_118)
    def test_nenhuma_tabela_guarda_dado_que_identifica_o_paciente(self, tabela):
        assert [c for c in _tabelas_criadas()[tabela] if c in COLUNAS_PROIBIDAS] == []

    def test_o_leitor_de_colunas_enxerga_coluna(self):
        """Piso do detector acima: regex que nao casa deixaria tudo verde sobre nada."""
        assert "entidade_id" in _tabelas_criadas()["cm_registro"]

    def test_o_registro_guarda_autor_data_entidade_antes_e_depois(self):
        colunas = set(_tabelas_criadas()["cm_registro"])

        assert {"autor_id", "data", "entidade", "entidade_id", "antes_json", "depois_json"} <= colunas

    def test_a_tabela_de_preco_ganha_mapeamento_e_arquivo_original(self):
        sql = _sql_sem_comentarios()
        for coluna in ("mapeamento_json", "arquivo_original"):
            assert re.search(rf"ALTER TABLE cm_tabela_preco\s+ADD COLUMN IF NOT EXISTS {coluna}\s", sql), coluna

    def test_termina_com_o_recibo_da_118(self):
        ultima = _sql_sem_comentarios().strip().splitlines()[-1]
        assert ultima == "INSERT INTO migracoes_aplicadas (numero) VALUES (118) ON CONFLICT (numero) DO NOTHING;"


# ═══════════════════════════════════════════════════════════════════════════
# 2. O duble do banco e as pessoas
# ═══════════════════════════════════════════════════════════════════════════

ROTA_MATRIZ = "/api/contas-medicas/habilitacao"
ROTA_PERMISSAO = "/api/contas-medicas/habilitacao/matriz"
ROTA_PESSOAS = "/api/contas-medicas/habilitacao/pessoas"
ROTA_ME = "/api/contas-medicas/me"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _matriz_da_migration() -> list[dict[str, Any]]:
    """As linhas do INSERT em `cm_perfil_permissao` da 116, como o banco as tem."""
    sql = (MIGRATIONS / "116_contas_medicas_fundacao.sql").read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


# A chave de cada tabela que o duble atualiza por upsert.
CHAVES = {"cm_perfil_permissao": ("perfil", "permissao")}


class _Consulta:
    def __init__(self, banco: _Banco, tabela: str):
        self._banco = banco
        self._tabela = tabela
        self._filtros: list = []
        self._mudancas: dict | None = None
        self._nova: dict | None = None
        self._upsert = False
        self._limite: int | None = None
        self._ordem: str | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        self._filtros.append(lambda linha: linha.get(coluna) in list(valores))
        return self

    def ilike(self, coluna, padrao):
        trecho = padrao.strip("%").lower()
        self._filtros.append(lambda linha: trecho in (linha.get(coluna) or "").lower())
        return self

    def order(self, coluna, **_kw):
        self._ordem = coluna
        return self

    def limit(self, n):
        self._limite = n
        return self

    def update(self, mudancas):
        self._mudancas = mudancas
        return self

    def insert(self, linha):
        self._nova = linha
        return self

    def upsert(self, linha, **_kw):
        self._nova = linha
        self._upsert = True
        return self

    def execute(self):
        linhas = self._banco.linhas(self._tabela)
        if self._nova is not None:
            if self._upsert:
                chave = CHAVES[self._tabela]
                existente = next((x for x in linhas if all(x[c] == self._nova[c] for c in chave)), None)
                if existente is not None:
                    existente.update(self._nova)
                    return SimpleNamespace(data=[dict(existente)])
            linhas.append(dict(self._nova))
            return SimpleNamespace(data=[dict(self._nova)])
        casam = [linha for linha in linhas if all(f(linha) for f in self._filtros)]
        if self._mudancas is not None:
            for linha in casam:
                linha.update(self._mudancas)
        if self._ordem:
            casam = sorted(casam, key=lambda linha: linha.get(self._ordem) or "")
        if self._limite is not None:
            casam = casam[: self._limite]
        return SimpleNamespace(data=[dict(linha) for linha in casam])


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def linhas(self, tabela: str) -> list[dict]:
        return self.tabelas.setdefault(tabela, [])

    def table(self, nome: str):
        return _Consulta(self, nome)


def _pessoa(pid: str, nome: str, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid.lower()}@hsm.test",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": None,
        "github_login": None,
        "data_cadastro": "2026-01-01",
    }
    return {**base, **campos}


class _Hospital:
    """Um app com as rotas do modulo, um banco so e varias pessoas, cada
    requisicao feita em nome de quem `como` escolheu."""

    def __init__(self, *pessoas: dict[str, Any]):
        self.banco = _Banco(
            {"participantes": [dict(p) for p in pessoas], "cm_perfil_permissao": _matriz_da_migration()}
        )
        self._quem: dict[str, Any] = {}
        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(contas_medicas_router.router, prefix="/api")
        app.include_router(habilitacao_router.router, prefix="/api")
        app.include_router(participantes_router.router, prefix="/api")

        @app.get("/api/contas-medicas/sonda-painel")
        async def _sonda(me: dict = Depends(require_permissao_cm("painel_completo"))) -> dict:
            """O painel completo chega no PRD #1128; a sonda tem o mesmo guard."""
            return {"id": me["id"]}

        async def _usuario() -> dict[str, Any]:
            return {"id": self._quem["auth_user_id"], "email": self._quem["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        self._cliente = TestClient(app)

    def como(self, pessoa: dict[str, Any]) -> TestClient:
        self._quem = pessoa
        return self._cliente

    def registro(self) -> list[dict]:
        return self.banco.linhas("cm_registro")


DIRETORA = _pessoa("D1", "Diretora Executiva", perfil_contas_medicas="diretoria_executiva")
COORDENADORA = _pessoa("C1", "Carla Coordenadora", perfil_contas_medicas="coordenadora")
SEM_EIXO = _pessoa("F9", "Fernanda Faturista")


# ═══════════════════════════════════════════════════════════════════════════
# 3. A matriz pela rota
# ═══════════════════════════════════════════════════════════════════════════


class TestAMatriz:
    def test_quem_habilita_le_a_matriz_perfil_por_permissao(self):
        hospital = _Hospital(DIRETORA, COORDENADORA)

        resposta = hospital.como(DIRETORA).get(ROTA_MATRIZ)

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["matriz"]["coordenadora"]["painel_completo"] is True
        assert corpo["matriz"]["coordenadora"]["incluir_regra_operacional"] is False
        assert corpo["perfis"][0] == "faturista"
        assert len(corpo["permissoes"]) == 8


class TestAPerdaValeNaHora:
    def test_desligar_o_painel_da_coordenadora_fecha_a_requisicao_seguinte_e_religar_abre(self):
        """O guard le a matriz a cada requisicao. Mutante: guardar as
        permissoes de cada perfil num cache; a coordenadora, que ja abriu o
        painel uma vez, continuaria entrando depois de perder a permissao."""
        hospital = _Hospital(DIRETORA, COORDENADORA)
        assert hospital.como(COORDENADORA).get("/api/contas-medicas/sonda-painel").status_code == 200

        desligar = hospital.como(DIRETORA).put(
            ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel_completo", "ligada": False}
        )
        assert desligar.status_code == 200
        assert hospital.como(COORDENADORA).get("/api/contas-medicas/sonda-painel").status_code == 403

        religar = hospital.como(DIRETORA).put(
            ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel_completo", "ligada": True}
        )
        assert religar.status_code == 200
        assert hospital.como(COORDENADORA).get("/api/contas-medicas/sonda-painel").status_code == 200

    def test_a_matriz_relida_mostra_a_celula_desligada(self):
        hospital = _Hospital(DIRETORA, COORDENADORA)
        diretora = hospital.como(DIRETORA)

        diretora.put(ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel_completo", "ligada": False})

        assert diretora.get(ROTA_MATRIZ).json()["matriz"]["coordenadora"]["painel_completo"] is False

    def test_permissao_que_nao_existe_e_recusada(self):
        hospital = _Hospital(DIRETORA)

        resposta = hospital.como(DIRETORA).put(
            ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel", "ligada": True}
        )

        assert resposta.status_code == 422
        assert hospital.registro() == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. O perfil da pessoa
# ═══════════════════════════════════════════════════════════════════════════


class TestOPerfilDaPessoa:
    def test_atribuir_o_perfil_abre_o_modulo_e_retirar_fecha(self):
        """Mutante: a rota responder sem gravar o perfil em `participantes`."""
        hospital = _Hospital(DIRETORA, SEM_EIXO)
        assert hospital.como(SEM_EIXO).get(ROTA_ME).status_code == 403

        dar = hospital.como(DIRETORA).put(f"{ROTA_PESSOAS}/F9", json={"perfil": "faturista"})

        assert dar.status_code == 200
        me = hospital.como(SEM_EIXO).get(ROTA_ME)
        assert me.status_code == 200
        assert me.json()["perfil"] == "faturista"
        # O item do menu lateral decide pelo `/participantes/me`.
        assert hospital.como(SEM_EIXO).get("/api/participantes/me").json()["perfil_contas_medicas"] == "faturista"

        tirar = hospital.como(DIRETORA).put(f"{ROTA_PESSOAS}/F9", json={"perfil": None})

        assert tirar.status_code == 200
        assert hospital.como(SEM_EIXO).get(ROTA_ME).status_code == 403
        assert hospital.como(SEM_EIXO).get("/api/participantes/me").json()["perfil_contas_medicas"] is None

    def test_perfil_que_nao_existe_e_recusado(self):
        hospital = _Hospital(DIRETORA, SEM_EIXO)

        resposta = hospital.como(DIRETORA).put(f"{ROTA_PESSOAS}/F9", json={"perfil": "estagiario"})

        assert resposta.status_code == 422
        assert hospital.banco.linhas("participantes")[1]["perfil_contas_medicas"] is None

    def test_pessoa_que_nao_existe_recebe_404(self):
        hospital = _Hospital(DIRETORA)

        assert hospital.como(DIRETORA).put(f"{ROTA_PESSOAS}/X0", json={"perfil": "faturista"}).status_code == 404


class TestABuscaDePessoa:
    def test_a_busca_acha_pelo_pedaco_do_nome_sem_distinguir_maiusculas(self):
        hospital = _Hospital(DIRETORA, COORDENADORA, SEM_EIXO)

        pessoas = hospital.como(DIRETORA).get(ROTA_PESSOAS, params={"busca": "fernanda"}).json()["pessoas"]

        assert [(p["id"], p["nome_completo"], p["perfil"]) for p in pessoas] == [("F9", "Fernanda Faturista", None)]

    def test_sem_busca_lista_quem_ja_tem_perfil_no_modulo(self):
        hospital = _Hospital(DIRETORA, COORDENADORA, SEM_EIXO)

        pessoas = hospital.como(DIRETORA).get(ROTA_PESSOAS).json()["pessoas"]

        assert sorted(p["id"] for p in pessoas) == ["C1", "D1"]

    def test_quem_foi_desligado_nao_aparece_na_busca(self):
        desligada = _pessoa("F8", "Fernanda Antiga", ativo=False)
        hospital = _Hospital(DIRETORA, SEM_EIXO, desligada)

        pessoas = hospital.como(DIRETORA).get(ROTA_PESSOAS, params={"busca": "Fernanda"}).json()["pessoas"]

        assert [p["id"] for p in pessoas] == ["F9"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O registro de cada mudanca
# ═══════════════════════════════════════════════════════════════════════════


class TestORegistro:
    def test_desligar_uma_celula_grava_autor_data_antes_e_depois(self):
        """Mutante: trocar `antes` por `depois` no registro."""
        hospital = _Hospital(DIRETORA, COORDENADORA)

        hospital.como(DIRETORA).put(
            ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel_completo", "ligada": False}
        )

        [registro] = hospital.registro()
        assert registro["autor_id"] == "D1"
        assert registro["data"]
        assert registro["entidade"] == "cm_perfil_permissao"
        assert registro["entidade_id"] == "coordenadora:painel_completo"
        assert registro["antes_json"] == {"ligada": True}
        assert registro["depois_json"] == {"ligada": False}

    def test_dar_e_tirar_o_perfil_grava_um_registro_cada(self):
        hospital = _Hospital(DIRETORA, SEM_EIXO)
        diretora = hospital.como(DIRETORA)

        diretora.put(f"{ROTA_PESSOAS}/F9", json={"perfil": "faturista"})
        diretora.put(f"{ROTA_PESSOAS}/F9", json={"perfil": None})

        assert [(r["autor_id"], r["entidade_id"], r["antes_json"], r["depois_json"]) for r in hospital.registro()] == [
            ("D1", "F9", {"perfil": None}, {"perfil": "faturista"}),
            ("D1", "F9", {"perfil": "faturista"}, {"perfil": None}),
        ]
        assert all(r["entidade"] == "participantes.perfil_contas_medicas" and r["data"] for r in hospital.registro())

    def test_repetir_o_que_ja_esta_nao_grava_registro(self):
        hospital = _Hospital(DIRETORA, COORDENADORA)

        hospital.como(DIRETORA).put(
            ROTA_PERMISSAO, json={"perfil": "coordenadora", "permissao": "painel_completo", "ligada": True}
        )

        assert hospital.registro() == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. 403 sem "habilitar pessoas"
# ═══════════════════════════════════════════════════════════════════════════

ROTAS_DA_HABILITACAO = (
    ("get", ROTA_MATRIZ, None),
    ("put", ROTA_PERMISSAO, {"perfil": "coordenadora", "permissao": "habilitar_pessoas", "ligada": True}),
    ("get", ROTA_PESSOAS, None),
    ("put", f"{ROTA_PESSOAS}/C1", {"perfil": "diretoria_executiva"}),
)


class TestSemHabilitarPessoas:
    @pytest.mark.parametrize(("metodo", "rota", "corpo"), ROTAS_DA_HABILITACAO, ids=lambda x: str(x))
    def test_a_coordenadora_recebe_403_e_nada_muda(self, metodo, rota, corpo):
        """Mutante: tirar o guard de uma rota. A coordenadora tentando se dar
        "habilitar pessoas" ou o perfil da diretoria e o caso que importa."""
        hospital = _Hospital(DIRETORA, COORDENADORA)

        resposta = getattr(hospital.como(COORDENADORA), metodo)(rota, **({"json": corpo} if corpo else {}))

        assert resposta.status_code == 403
        assert hospital.registro() == []
        assert hospital.banco.linhas("participantes")[1]["perfil_contas_medicas"] == "coordenadora"
        assert hospital.como(COORDENADORA).get(ROTA_MATRIZ).status_code == 403

    @pytest.mark.parametrize(("metodo", "rota", "corpo"), ROTAS_DA_HABILITACAO, ids=lambda x: str(x))
    def test_quem_nao_tem_o_eixo_recebe_403(self, metodo, rota, corpo):
        hospital = _Hospital(DIRETORA, SEM_EIXO)

        resposta = getattr(hospital.como(SEM_EIXO), metodo)(rota, **({"json": corpo} if corpo else {}))

        assert resposta.status_code == 403

    def test_a_diretoria_executiva_tem_habilitar_pessoas_na_carga(self):
        """Piso dos testes acima: se ninguem passasse, o 403 seria de graca."""
        hospital = _Hospital(DIRETORA)

        assert hospital.como(DIRETORA).get(ROTA_PESSOAS).status_code == 200


class TestARotaEstaNoApp:
    def test_o_app_de_verdade_registra_as_rotas_da_habilitacao(self):
        """A fonte e o schema OpenAPI, e nao `app.routes` (issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "get" in caminhos[ROTA_MATRIZ]
        assert "put" in caminhos[ROTA_PERMISSAO]
        assert "get" in caminhos[ROTA_PESSOAS]
        assert "put" in caminhos[f"{ROTA_PESSOAS}/{{participante_id}}"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


def _secao(titulo: str) -> str:
    return KIT.read_text(encoding="utf-8").split(f"## {titulo}")[1].split("\n## ")[0]


class TestOKitDizQueAHabilitacaoEPorTela:
    """O Assistente de Tecnologia responde Demanda com este texto: se ele
    disser que o perfil e gravado pela tecnologia, manda a pessoa esperar por
    quem nao faz mais isso."""

    def test_quem_ve_diz_que_a_diretoria_habilita_pela_tela_e_vale_na_hora(self):
        quem_ve = _secao("Quem vê")

        assert "tela de **Habilitação**" in quem_ve
        assert "vale na hora" in quem_ve
        assert "equipe de tecnologia" not in quem_ve

    def test_o_que_ja_esta_no_ar_inclui_a_habilitacao(self):
        assert "tela de Habilitação" in _secao("O que já está no ar")

    def test_o_pedido_de_perfil_aponta_para_a_tela(self):
        demanda = _secao("O que costuma virar Demanda")

        assert "na tela de Habilitação" in demanda
