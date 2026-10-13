"""A fundacao do modulo Contas medicas (issue #1114, PRD #1113, ADR 0070).

O eixo de permissao proprio (`perfil_contas_medicas`, ADR 0070 decisao 10), a
matriz perfil x permissao que a migration 116 carrega e a rota que diz a
pessoa o que ela pode fazer no modulo.

A matriz do dublê do banco e lida da PROPRIA migration, nao decorada aqui: o
que o teste confere e o que o Studio vai gravar. O esperado de cada perfil, ao
contrario, e escrito a mao a partir da spec do diretor (secao 3 e adendo
v1.1), para o teste poder discordar da migration.
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

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

ROTA_ME = "/api/contas-medicas/me"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _matriz_da_migration() -> list[dict[str, Any]]:
    """As linhas do INSERT em `cm_perfil_permissao`, como o banco as tera."""
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._eq: dict[str, Any] = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def execute(self):
        casam = [dict(linha) for linha in self._linhas if all(linha.get(c) == v for c, v in self._eq.items())]
        return SimpleNamespace(data=casam)


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _Consulta(self.tabelas.setdefault(nome, []))


def _pessoa(**campos) -> dict[str, Any]:
    base = {
        "id": "P1",
        "auth_user_id": "auth-p1",
        "nome_completo": "Pessoa de Teste",
        "email": "p1@hsm.test",
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


def _cliente(pessoa: dict[str, Any], app: FastAPI | None = None) -> TestClient:
    app = app or FastAPI()
    app.state.limiter = limiter
    app.include_router(contas_medicas_router.router, prefix="/api")
    banco = _Banco({"participantes": [pessoa], "cm_perfil_permissao": _matriz_da_migration()})

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# 1. GET /api/contas-medicas/me
# ═══════════════════════════════════════════════════════════════════════════


class TestQuemTemOEixo:
    def test_a_faturista_recebe_o_perfil_e_as_permissoes_ligadas(self):
        resposta = _cliente(_pessoa(perfil_contas_medicas="faturista")).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": "faturista", "permissoes": ["enviar_corrigir_contas"]}


class TestQuemNaoTemOEixo:
    def test_sem_perfil_de_contas_medicas_recebe_403(self):
        """Mutante: tirar o gate da rota. Quem e so de Reunioes receberia 200."""
        pessoa = _pessoa(access_profile="regular", perfil_ouvidoria="ouvidor")

        assert _cliente(pessoa).get(ROTA_ME).status_code == 403

    def test_pessoa_desligada_recebe_403_mesmo_com_o_perfil(self):
        pessoa = _pessoa(perfil_contas_medicas="diretoria_medica", ativo=False)

        assert _cliente(pessoa).get(ROTA_ME).status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 2. A matriz inicial bate com a spec
# ═══════════════════════════════════════════════════════════════════════════

TODAS = (
    "enviar_corrigir_contas",
    "decidir_validacao",
    "incluir_regra_operacional",
    "regra_contratual_tabelas",
    "contratos_avisos",
    "painel_completo",
    "habilitar_pessoas",
    "conferencia_coordenacao",
)

# Escrito a mao a partir da spec (secao 3) e do adendo v1.1, e nao derivado da
# migration: e a fonte independente que pode discordar dela.
ESPERADO_POR_PERFIL = {
    "faturista": ["enviar_corrigir_contas"],
    "coordenadora": ["enviar_corrigir_contas", "painel_completo", "conferencia_coordenacao"],
    "gestao_contas_medicas": [p for p in TODAS if p != "habilitar_pessoas"],
    "diretoria_medica": list(TODAS),
    "diretoria_executiva": list(TODAS),
    "credenciamento": ["contratos_avisos"],
}


class TestSuperAdminPassa:
    def test_super_admin_sem_perfil_passa_com_as_oito_permissoes(self):
        """Super admin do app passa, como nos outros modulos (ADR 0070)."""
        resposta = _cliente(_pessoa(access_profile="super_admin", is_super_admin=True)).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": None, "permissoes": list(TODAS)}


class TestMatrizInicial:
    @pytest.mark.parametrize("perfil", sorted(ESPERADO_POR_PERFIL))
    def test_a_rota_devolve_as_permissoes_do_perfil_na_carga_da_migration(self, perfil):
        """Mutante: ligar "incluir regra operacional" para a coordenadora na
        migration. A rota passa a devolve-la e o teste do perfil fica vermelho."""
        resposta = _cliente(_pessoa(perfil_contas_medicas=perfil)).get(ROTA_ME)

        assert resposta.status_code == 200
        assert resposta.json() == {"perfil": perfil, "permissoes": ESPERADO_POR_PERFIL[perfil]}

    def test_a_carga_tem_as_oito_permissoes_de_cada_um_dos_seis_perfis(self):
        """Toda combinacao existe, ligada ou nao: a Habilitacao liga e desliga
        linha que ja esta la. Tambem e o piso do leitor do INSERT: se a regex
        parar de casar, a matriz volta vazia e os testes acima mentem."""
        matriz = _matriz_da_migration()
        pares = {(linha["perfil"], linha["permissao"]) for linha in matriz}

        assert len(matriz) == 48
        assert pares == {(perfil, p) for perfil in ESPERADO_POR_PERFIL for p in TODAS}


# ═══════════════════════════════════════════════════════════════════════════
# 3. O guard por permissao
# ═══════════════════════════════════════════════════════════════════════════


def _cliente_com_sonda(pessoa: dict[str, Any], permissao: str) -> TestClient:
    """Uma rota de mentira atras de `require_permissao_cm(permissao)`: as rotas
    de verdade que usam cada permissao chegam nas fatias seguintes."""
    app = FastAPI()

    @app.get("/sonda")
    async def _sonda(me: dict = Depends(require_permissao_cm(permissao))) -> dict:
        return {"id": me["id"]}

    return _cliente(pessoa, app)


class TestGuardPorPermissao:
    def test_quem_tem_a_permissao_ligada_passa(self):
        pessoa = _pessoa(perfil_contas_medicas="coordenadora")

        assert _cliente_com_sonda(pessoa, "painel_completo").get("/sonda").status_code == 200

    def test_quem_tem_o_eixo_sem_a_permissao_recebe_403(self):
        """Mutante: o guard conferir so o eixo e ignorar a matriz."""
        pessoa = _pessoa(perfil_contas_medicas="faturista")

        assert _cliente_com_sonda(pessoa, "painel_completo").get("/sonda").status_code == 403

    def test_permissao_desligada_na_matriz_recusa(self):
        pessoa = _pessoa(perfil_contas_medicas="coordenadora")

        assert _cliente_com_sonda(pessoa, "incluir_regra_operacional").get("/sonda").status_code == 403

    def test_super_admin_passa_em_qualquer_permissao(self):
        pessoa = _pessoa(access_profile="super_admin", is_super_admin=True)

        assert _cliente_com_sonda(pessoa, "habilitar_pessoas").get("/sonda").status_code == 200

    def test_permissao_escrita_errada_quebra_na_montagem_e_nao_em_producao(self):
        with pytest.raises(ValueError):
            require_permissao_cm("painel")


# ═══════════════════════════════════════════════════════════════════════════
# 4. A migration 116
# ═══════════════════════════════════════════════════════════════════════════

# As tabelas das decisoes de implementacao do PRD #1113, escritas a mao.
TABELAS_DO_PRD = (
    "cm_operadora",
    "cm_operadora_plano",
    "cm_memoria_versao",
    "cm_regra",
    "cm_tabela_preco",
    "cm_tabela_preco_item",
    "cm_operadora_tabela",
    "cm_setor",
    "cm_item_dicionario",
    "cm_envio",
    "cm_arquivo",
    "cm_atendimento",
    "cm_eventos",
    "cm_prescricao",
    "cm_prescricao_item",
    "cm_cirurgia",
    "cm_glicemia_dia",
    "cm_conta",
    "cm_conta_item",
    "cm_guia_linha",
    "cm_observacao",
    "cm_perfil_permissao",
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


def _sql() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _sql_sem_comentarios() -> str:
    return re.sub(r"--[^\n]*", "", _sql())


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


class TestMigration116:
    def test_cria_todas_as_tabelas_do_prd_e_so_elas(self):
        """Mutante: apagar o CREATE de uma tabela."""
        assert sorted(_tabelas_criadas()) == sorted(TABELAS_DO_PRD)

    @pytest.mark.parametrize("tabela", TABELAS_DO_PRD)
    def test_toda_tabela_tem_rls_ligado(self, tabela):
        """Mutante: tirar o ENABLE ROW LEVEL SECURITY de uma tabela."""
        assert re.search(rf"ALTER TABLE {tabela} ENABLE ROW LEVEL SECURITY;", _sql_sem_comentarios())

    @pytest.mark.parametrize("tabela", TABELAS_DO_PRD)
    def test_nenhuma_tabela_guarda_dado_que_identifica_o_paciente(self, tabela):
        """Mutante: acrescentar `cpf TEXT` ao atendimento."""
        assert [c for c in _tabelas_criadas()[tabela] if c in COLUNAS_PROIBIDAS] == []

    def test_o_atendimento_guarda_rotulo_e_idade(self):
        assert {"paciente_rotulo", "idade_anos"} <= set(_tabelas_criadas()["cm_atendimento"])

    def test_o_leitor_de_colunas_enxerga_coluna(self):
        """Piso do detector acima: se a regex de coluna parar de casar, toda
        tabela volta sem coluna e a ausencia de CPF fica verde sobre nada."""
        assert "numero_atendimento" in _tabelas_criadas()["cm_atendimento"]
        assert "cpf" in COLUNAS_PROIBIDAS

    def test_o_eixo_tem_check_com_os_seis_perfis(self):
        sql = _sql_sem_comentarios()
        bloco = re.search(r"participantes_perfil_contas_medicas_check\s+CHECK\s*\((.*?)\)\);", sql, re.DOTALL)
        assert bloco
        assert sorted(re.findall(r"'(\w+)'", bloco.group(1))) == sorted(ESPERADO_POR_PERFIL)

    def test_o_sino_ganha_contas_medicas_sem_perder_os_tipos_de_hoje(self):
        """O CHECK de `notificacoes.tipo` e refeito inteiro: esquecer um tipo
        antigo derrubaria a mencao, o aceite ou o comentario."""
        bloco = re.search(r"ADD CONSTRAINT notificacoes_tipo_check\s+CHECK \(tipo IN \((.*?)\)\);", _sql(), re.DOTALL)
        assert bloco
        assert sorted(re.findall(r"'(\w+)'", bloco.group(1))) == sorted(
            [
                "MENCAO",
                "STATUS_ALTERADO",
                "COMENTARIO",
                "PRAZO_PROXIMO",
                "RESPONSAVEL_ATRIBUIDO",
                "ACEITE_INTERNO",
                "CONTAS_MEDICAS",
            ]
        )

    def test_o_bucket_e_privado_e_tem_teto_de_100_mib(self):
        sql = _sql_sem_comentarios()
        bloco = re.search(r"INSERT INTO storage\.buckets\s*\(([^)]*)\)\s*VALUES\s*\(([^)]*)\)", sql)
        assert bloco
        colunas = [c.strip() for c in bloco.group(1).split(",")]
        valores = dict(zip(colunas, [v.strip() for v in bloco.group(2).split(",")], strict=True))
        assert valores["id"] == "'contas-medicas'"
        assert valores["public"] == "false"
        assert valores["file_size_limit"] == str(100 * 1024 * 1024)

    @pytest.mark.parametrize(
        ("tabela", "colunas"),
        [
            ("cm_conta", "faturista_id, situacao, ordem_fila"),
            ("cm_guia_linha", "conta_id"),
            ("cm_tabela_preco_item", "tabela_id, codigo"),
            ("cm_atendimento", "numero_atendimento"),
        ],
    )
    def test_os_indices_do_prd_existem(self, tabela, colunas):
        assert re.search(rf"INDEX IF NOT EXISTS \w+\s+ON {tabela}\s*\({colunas}\)", _sql_sem_comentarios())

    def test_termina_com_o_recibo_da_116(self):
        ultima = _sql_sem_comentarios().strip().splitlines()[-1]
        assert ultima == "INSERT INTO migracoes_aplicadas (numero) VALUES (116) ON CONFLICT (numero) DO NOTHING;"


# ═══════════════════════════════════════════════════════════════════════════
# 5. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestTextoDoProduto:
    """A sanidade geral (piso, secoes, sem rota nem tabela) mora em
    `test_kit_conhecimento.py`; aqui, o que ESTE texto tem que dizer."""

    def test_diz_o_que_o_modulo_e(self):
        abertura = KIT.read_text(encoding="utf-8").split("\n## ")[0]
        for termo in ("conta", "prontuário", "operadora", "Guia"):
            assert termo in abertura, termo

    def test_diz_o_que_ja_esta_no_ar(self):
        no_ar = KIT.read_text(encoding="utf-8").split("## O que já está no ar")[1].split("\n## ")[0]
        # O envio entrou no ar com a issue #1123: a tela deixou de abrir sempre vazia.
        for termo in ("menu", "envio dos PDFs", "Último envio"):
            assert termo in no_ar, termo


# ═══════════════════════════════════════════════════════════════════════════
# 6. O `pdftotext` na imagem do backend
# ═══════════════════════════════════════════════════════════════════════════

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


class TestPdftotextNaImagem:
    """A leitura da conta e do prontuario roda `pdftotext -layout` (ADR 0070,
    decisao 6). O build do Docker no CI e a prova de verdade: a linha que roda
    o binario reprova a imagem se o pacote sumir. Este teste trava as duas
    pontas no repositorio, para ninguem tirar uma sem ver a outra."""

    def test_o_dockerfile_instala_o_poppler(self):
        """Mutante: tirar `poppler-utils` do apt-get."""
        instalacao = re.search(r"apt-get install[^\n]*\\\n(.*?)&& rm -rf", DOCKERFILE.read_text(encoding="utf-8"), re.S)
        assert instalacao
        assert "poppler-utils" in instalacao.group(1).split()

    def test_o_build_reprova_a_imagem_sem_o_pdftotext(self):
        """Mutante: tirar a linha que roda o binario no build."""
        linhas = [linha.strip() for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines()]
        assert "RUN pdftotext -v" in linhas

    def test_o_build_reprova_a_imagem_sem_o_ocr_em_portugues(self):
        """Mutante: tirar o `grep -qx por` (ou a linha) da sanidade do OCR (#1191)."""
        linhas = [linha.strip() for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines()]
        assert "RUN pdftoppm -v && tesseract --version && tesseract --list-langs | grep -qx por" in linhas


class TestOMenuSabeDoEixo:
    def test_participantes_me_devolve_o_perfil_de_contas_medicas(self):
        """O menu lateral decide pelo `/participantes/me`, a fonte unica dos
        eixos no front. Sem o campo no schema de resposta, o FastAPI o descarta
        e o item nunca aparece."""
        from app.routers import participantes as participantes_router

        app = FastAPI()
        app.include_router(participantes_router.router, prefix="/api")
        cliente = _cliente(_pessoa(perfil_contas_medicas="coordenadora"), app)

        resposta = cliente.get("/api/participantes/me")

        assert resposta.status_code == 200
        assert resposta.json()["perfil_contas_medicas"] == "coordenadora"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Palavra proibida e tipografia nos arquivos do modulo
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]

# Os arquivos que o modulo trouxe nesta fundacao. O glob por "contas-medicas"
# e "contas_medicas" pega tambem o que as fatias seguintes criarem com o nome.
ARQUIVOS_DO_MODULO = sorted(
    arquivo
    for arquivo in {
        *RAIZ_DO_APP.glob("backend/app/**/*contas_medicas*"),
        *RAIZ_DO_APP.glob("backend/app/**/*contas-medicas*"),
        *RAIZ_DO_APP.glob("frontend/src/**/contas-medicas/**/*"),
        *RAIZ_DO_APP.glob("supabase/migrations/*contas_medicas*"),
    }
    if arquivo.is_file() and arquivo.suffix in {".py", ".md", ".sql", ".ts", ".tsx"}
)


class TestPalavraProibida:
    def test_o_glob_acha_os_arquivos_do_modulo(self):
        """Piso do detector: glob vazio deixaria os testes abaixo verdes sobre nada."""
        nomes = {arquivo.name for arquivo in ARQUIVOS_DO_MODULO}
        assert {"contas_medicas.py", "contas-medicas.md", "116_contas_medicas_fundacao.sql", "page.tsx"} <= nomes

    @pytest.mark.parametrize("arquivo", ARQUIVOS_DO_MODULO, ids=lambda a: a.name)
    def test_sem_a_palavra_auditoria(self, arquivo):
        """Decisao do diretor (ADR 0070, decisao 12). Mutante: escrever a
        palavra no texto do kit."""
        assert "auditoria" not in arquivo.read_text(encoding="utf-8").lower()

    @pytest.mark.parametrize("arquivo", ARQUIVOS_DO_MODULO, ids=lambda a: a.name)
    def test_sem_travessao_nem_meia_risca(self, arquivo):
        texto = arquivo.read_text(encoding="utf-8")
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto


class TestARotaEstaNoApp:
    def test_o_app_de_verdade_registra_a_rota(self):
        """O router tem `include_router` proprio no `main.py`. A fonte e o
        schema OpenAPI, e nao `app.routes` (FastAPI 0.141, issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "get" in caminhos[ROTA_ME]
