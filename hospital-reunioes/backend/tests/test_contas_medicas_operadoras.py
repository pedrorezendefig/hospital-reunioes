"""Carga da operadora em Contas médicas (issue #1119, PRD #1113, ADR 0070).

A gestão envia o arquivo de memória da operadora, cadastra os nomes de plano
que o MV imprime e os setores com a acomodação de cada um. Tudo pela rota de
verdade, atrás da permissão "regra contratual e tabelas".

As memórias de teste são sintéticas, no formato do MODELO-MEMORIA-OPERADORA.md
do diretor: as reais (ASSIM, Unimed) vivem em `local/contas-medicas/`, fora do
git, e entram em produção pela tela.

O dublê do banco guarda as restrições da migration 116 que a carga pode ferir:
uma versão vigente por operadora, nome do MV único sem diferença de
maiúscula, e os CHECKs de tipo, status, situação e acomodação. Violar uma
delas estoura como o PostgREST estouraria, para o teste não ficar verde sobre
um banco que aceitaria qualquer coisa.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_operadoras as operadoras_router  # noqa: E402
from app.services.contas_medicas.operadoras import memoria_vigente, reconhecer_plano  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contas_medicas" / "memoria"

ROTA_MEMORIA = "/api/contas-medicas/operadoras/memoria"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _memoria(nome: str) -> str:
    return (FIXTURES / nome).read_text(encoding="utf-8")


def _matriz_da_migration() -> list[dict[str, Any]]:
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════

ACOMODACOES = {
    "CTI",
    "ENFERMARIA",
    "APARTAMENTO",
    "ISOLAMENTO",
    "CENTRO_CIRURGICO",
    "HOSPITAL_DIA",
    "PEDIATRIA",
    "UTI_PEDIATRICA",
    "UTI_NEONATAL",
}

# Os padrões de coluna da migration 116 que a carga deixa de mandar.
PADROES = {
    "cm_operadora": {"situacao": "SEM_MEMORIA"},
    "cm_memoria_versao": {"vigente": False, "parametros_json": {}},
    "cm_regra": {"status": "PENDENTE", "ativa": True},
}

# Os CHECKs da migration 116 (valor permitido por coluna; None = nulo aceito).
CHECKS = {
    ("cm_operadora", "situacao"): {"PRONTA", "PARCIAL", "SEM_MEMORIA"},
    ("cm_regra", "tipo"): {None, "CONTRATUAL", "OPERACIONAL"},
    ("cm_regra", "status"): {"VIGENTE", "PENDENTE"},
    ("cm_setor", "acomodacao"): {None, *ACOMODACOES},
}

NAO_NULOS = {
    "cm_operadora": ("sigla", "nome"),
    "cm_memoria_versao": ("operadora_id", "versao"),
    "cm_regra": ("operadora_id", "codigo", "texto"),
    "cm_operadora_plano": ("operadora_id", "nome_mv"),
    "cm_setor": ("nome_mv",),
}


def _erro(codigo: str, mensagem: str) -> APIError:
    return APIError({"code": codigo, "message": mensagem, "details": None, "hint": None})


class _Consulta:
    def __init__(self, banco: _Banco, tabela: str):
        self._banco = banco
        self._tabela = tabela
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._operacao = "select"
        self._payload: Any = None
        self._colunas: list[str] | None = None

    def select(self, colunas: str = "*", **_kw):
        if colunas.strip() != "*":
            self._colunas = [c.strip() for c in colunas.split(",")]
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, _n):
        return self

    def insert(self, payload):
        self._operacao = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._operacao = "update"
        self._payload = payload
        return self

    def _casam(self) -> list[dict]:
        return [linha for linha in self._banco.linhas(self._tabela) if all(f(linha) for f in self._filtros)]

    def execute(self):
        if self._operacao == "insert":
            novas = self._payload if isinstance(self._payload, list) else [self._payload]
            gravadas = [self._banco.inserir(self._tabela, dict(linha)) for linha in novas]
            return SimpleNamespace(data=[dict(g) for g in gravadas], count=len(gravadas))
        if self._operacao == "update":
            alvo = self._casam()
            for linha in alvo:
                self._banco.atualizar(self._tabela, linha, dict(self._payload))
            return SimpleNamespace(data=[dict(linha) for linha in alvo], count=len(alvo))
        casam = [dict(linha) for linha in self._casam()]
        if self._ordem:
            coluna, desc = self._ordem
            casam.sort(key=lambda linha: (linha.get(coluna) is None, linha.get(coluna)), reverse=desc)
        if self._colunas:
            casam = [{c: linha.get(c) for c in self._colunas} for linha in casam]
        return SimpleNamespace(data=casam, count=len(casam))


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]] | None = None):
        self.tabelas: dict[str, list[dict]] = tabelas or {}

    def linhas(self, tabela: str) -> list[dict]:
        return self.tabelas.setdefault(tabela, [])

    def table(self, nome: str):
        return _Consulta(self, nome)

    def _validar(self, tabela: str, linha: dict, ignorar: dict | None = None) -> None:
        for coluna in NAO_NULOS.get(tabela, ()):
            if linha.get(coluna) is None:
                raise _erro("23502", f"null value in column {coluna} of relation {tabela}")
        for (t, coluna), permitidos in CHECKS.items():
            if t == tabela and coluna in linha and linha[coluna] not in permitidos:
                raise _erro("23514", f"new row for relation {tabela} violates check constraint ({coluna})")
        outras = [o for o in self.linhas(tabela) if o is not ignorar]
        if tabela == "cm_operadora" and any(o["sigla"] == linha["sigla"] for o in outras):
            raise _erro("23505", "duplicate key value violates unique constraint cm_operadora_sigla_key")
        if tabela in ("cm_operadora_plano", "cm_setor") and any(
            o["nome_mv"].lower() == linha["nome_mv"].lower() for o in outras
        ):
            raise _erro("23505", f"duplicate key value violates unique constraint idx_{tabela}_nome_mv")
        if tabela == "cm_memoria_versao" and linha.get("vigente"):
            if any(o["operadora_id"] == linha["operadora_id"] and o.get("vigente") for o in outras):
                raise _erro("23505", "duplicate key value violates unique constraint idx_cm_memoria_versao_vigente")

    def inserir(self, tabela: str, linha: dict) -> dict:
        completa = {**PADROES.get(tabela, {}), "id": str(uuid.uuid4()), **linha}
        self._validar(tabela, completa)
        self.linhas(tabela).append(completa)
        return completa

    def atualizar(self, tabela: str, linha: dict, mudancas: dict) -> None:
        self._validar(tabela, {**linha, **mudancas}, ignorar=linha)
        linha.update(mudancas)


def _pessoa(**campos) -> dict[str, Any]:
    base = {
        "id": "P1",
        "auth_user_id": "auth-p1",
        "nome_completo": "Pessoa de Teste",
        "email": "p1@hsm.test",
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": None,
    }
    return {**base, **campos}


GESTAO = _pessoa(perfil_contas_medicas="gestao_contas_medicas")
FATURISTA = _pessoa(perfil_contas_medicas="faturista")


def _cliente(pessoa: dict[str, Any], banco: _Banco | None = None) -> tuple[TestClient, _Banco]:
    banco = banco or _Banco()
    banco.tabelas["participantes"] = [pessoa]
    banco.tabelas["cm_perfil_permissao"] = _matriz_da_migration()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _enviar_memoria(cliente: TestClient, texto: str, nome: str = "MEMORIA.md"):
    return cliente.post(ROTA_MEMORIA, files={"arquivo": (nome, texto.encode("utf-8"), "text/markdown")})


# ═══════════════════════════════════════════════════════════════════════════
# 1. Envio do arquivo de memória
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvioDaMemoria:
    def test_memoria_de_duas_secoes_cria_a_operadora_a_versao_e_as_cinco_regras(self):
        cliente, banco = _cliente(GESTAO)

        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert corpo["operadora"] == "ALFA"
        assert corpo["versao"] == "1.0"
        assert corpo["regras"] == {"total": 5, "vigentes": 3, "pendentes": 2}
        assert corpo["parametros"]["diaria"]["hora_vencimento"] == "10:00"
        assert corpo["parametros"]["colunas_de_preco"]["CARIOCA"] == ["Alfa Max Qc", "Alfa Intermediário Qp"]

        [operadora] = banco.linhas("cm_operadora")
        assert (operadora["sigla"], operadora["nome"], operadora["situacao"]) == ("ALFA", "Alfa Saúde", "PARCIAL")
        [versao] = banco.linhas("cm_memoria_versao")
        assert versao["operadora_id"] == operadora["id"]
        assert versao["vigente"] is True
        assert versao["autor_id"] == "P1"
        regras = {r["codigo"]: r for r in banco.linhas("cm_regra")}
        assert sorted(regras) == ["ALFA-DIA-01", "ALFA-DIA-02", "ALFA-PRI-01", "ALFA-PRI-02", "ALFA-PRI-03"]
        assert all(r["memoria_versao_id"] == versao["id"] for r in regras.values())
        assert {k: (r["secao"], r["tipo"], r["origem"], r["status"]) for k, r in regras.items()} == {
            "ALFA-PRI-01": ("PRI", "OPERACIONAL", "PRÁTICA", "VIGENTE"),
            "ALFA-PRI-02": ("PRI", "OPERACIONAL", "PRÁTICA", "VIGENTE"),
            "ALFA-PRI-03": ("PRI", "CONTRATUAL", "CONTRATO", "PENDENTE"),
            "ALFA-DIA-01": ("DIA", "CONTRATUAL", "PRÁTICA", "VIGENTE"),
            "ALFA-DIA-02": ("DIA", "CONTRATUAL", "PRÁTICA", "PENDENTE"),
        }
        assert regras["ALFA-DIA-01"]["texto"] == (
            "A diária começa em qualquer horário, vence às 10h e é sempre integral."
        )
        assert regras["ALFA-DIA-01"]["validado_em"] == "2026-10-06"
        assert regras["ALFA-DIA-02"]["validado_em"] is None

    def test_quem_nao_tem_regra_contratual_e_tabelas_recebe_403_e_nada_e_gravado(self):
        """Mutante: tirar a permissão da rota. A faturista gravaria a memória."""
        cliente, banco = _cliente(FATURISTA)

        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        assert resposta.status_code == 403
        assert banco.linhas("cm_operadora") == []
        assert banco.linhas("cm_regra") == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. O cabeçalho inteiro em parametros_json, com padrão no que falta
# ═══════════════════════════════════════════════════════════════════════════


class TestParametrosDoCabecalho:
    def test_chave_que_o_codigo_nao_le_fica_guardada_e_volta_na_exportacao(self):
        cliente, banco = _cliente(GESTAO)
        _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        [versao] = banco.linhas("cm_memoria_versao")
        assert versao["parametros_json"]["opme"] == {
            "fornecida_por": "OPERADORA",
            "negociacao": "direta entre o fornecedor e a operadora",
        }
        # O cabeçalho é guardado como veio: o padrão é de quem lê, não do banco.
        assert "tetos_por_dia" not in versao["parametros_json"]

        exportada = cliente.get("/api/contas-medicas/operadoras/ALFA/memoria")
        assert exportada.status_code == 200
        assert exportada.headers["content-type"].startswith("text/markdown")
        assert 'filename="MEMORIA-ALFA-v1.0.md"' in exportada.headers["content-disposition"]
        assert "opme:" in exportada.text
        assert "fornecida_por: OPERADORA" in exportada.text

    def test_chave_ausente_ganha_o_valor_padrao_na_leitura(self):
        """A ALFA não traz `tetos_por_dia`, `fora_da_conta_do_hospital` nem
        `transicao`: quem lê recebe o padrão, e as diretrizes gerais HSM valem."""
        cliente, banco = _cliente(GESTAO)
        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))
        [operadora] = banco.linhas("cm_operadora")

        vigente = memoria_vigente(banco, operadora["id"])

        for parametros in (resposta.json()["parametros"], vigente["parametros"]):
            assert parametros["tetos_por_dia"] == {}
            assert parametros["fora_da_conta_do_hospital"] == []
            assert parametros["pacote_uti_adulto"] is None
            assert parametros["transicao"]["prescrito_vale_como_checado"] is True
            assert parametros["opme"]["fornecida_por"] == "OPERADORA"
            # O que a memória traz não é sobrescrito pelo padrão.
            assert parametros["diaria"]["limite_madrugada"] == "05:00"

    def test_exportar_operadora_sem_memoria_e_404(self):
        cliente, _ = _cliente(GESTAO)

        assert cliente.get("/api/contas-medicas/operadoras/ALFA/memoria").status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# 3. Colunas extras viram texto; Pendentes (resumo) e Histórico ficam de fora
# ═══════════════════════════════════════════════════════════════════════════


class TestTabelasDaMemoria:
    def test_tabela_de_insumos_vira_regra_com_coluna_e_valor_no_texto(self):
        cliente, banco = _cliente(GESTAO)
        resposta = _enviar_memoria(cliente, _memoria("MEMORIA-BETA-v1.0.md"))
        [operadora] = banco.linhas("cm_operadora")

        regras = {r["codigo"]: r for r in memoria_vigente(banco, operadora["id"])["regras"]}

        assert regras["BETA-INS-01"] == {
            "codigo": "BETA-INS-01",
            "secao": "INS",
            "texto": (
                "Gatilho (terapia registrada): Acesso venoso periférico em uso\n"
                "Insumo: Cateter periférico\n"
                "Código: 70135266\n"
                "Quantidade: 1 a cada 96 h, mais trocas justificadas"
            ),
            "tipo": None,
            "origem": "MANUAL DA OPERADORA",
            "status": "VIGENTE",
        }
        assert regras["BETA-INS-02"]["status"] == "PENDENTE"
        assert regras["BETA-INS-02"]["texto"].endswith("Quantidade: 5 por instalação; troca diária a validar")
        assert regras["BETA-INS-00"]["texto"] == (
            "A operadora paga equipos, cateteres e conectores por regra de tempo, não pelo número de dispensações."
        )
        assert resposta.json()["regras"] == {"total": 3, "vigentes": 2, "pendentes": 1}

    def test_secoes_pendentes_resumo_e_historico_nao_viram_regra(self):
        """As duas seções repetem IDs da seção 8 e citam um que não existe
        (BETA-PRC-09): nada delas pode entrar, nem como regra nova nem repetida."""
        cliente, banco = _cliente(GESTAO)
        _enviar_memoria(cliente, _memoria("MEMORIA-BETA-v1.0.md"))

        codigos = sorted(r["codigo"] for r in banco.linhas("cm_regra"))

        assert codigos == ["BETA-INS-00", "BETA-INS-01", "BETA-INS-02"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Versão nova da mesma operadora
# ═══════════════════════════════════════════════════════════════════════════


class TestVersaoNova:
    def test_segunda_importacao_aposenta_a_anterior_e_a_vigente_e_a_nova(self):
        cliente, banco = _cliente(GESTAO)
        v10 = _memoria("MEMORIA-ALFA-v1.0.md")
        v11 = v10.replace('versao_memoria: "1.0"', 'versao_memoria: "1.1"').replace(
            "| ALFA-DIA-02 | Transferência de setor antes das 10h: gera ou não diária extra no setor de origem. "
            "| CONTRATUAL | PRÁTICA | PENDENTE | |",
            "| ALFA-DIA-02 | Transferência de setor antes das 10h não gera diária extra. "
            "| CONTRATUAL | PRÁTICA | VIGENTE | 12/10/2026 |",
        )
        assert v11.count("1.1") == 1 and "não gera diária extra" in v11, "a fixture mudou: refazer a v1.1"

        assert _enviar_memoria(cliente, v10).status_code == 201
        resposta = _enviar_memoria(cliente, v11)

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["regras"] == {"total": 5, "vigentes": 4, "pendentes": 1}
        [operadora] = banco.linhas("cm_operadora")
        assert {v["versao"]: v["vigente"] for v in banco.linhas("cm_memoria_versao")} == {"1.0": False, "1.1": True}

        vigente = memoria_vigente(banco, operadora["id"])
        assert vigente["versao"] == "1.1"
        regras = {r["codigo"]: r for r in vigente["regras"]}
        assert len(regras) == 5
        assert regras["ALFA-DIA-02"]["status"] == "VIGENTE"
        assert regras["ALFA-DIA-02"]["texto"] == "Transferência de setor antes das 10h não gera diária extra."


# ═══════════════════════════════════════════════════════════════════════════
# 5. Dado de paciente não entra
# ═══════════════════════════════════════════════════════════════════════════


class TestCpfNaMemoria:
    def test_arquivo_com_cpf_no_corpo_e_recusado_com_mensagem_clara_e_nada_e_gravado(self):
        cliente, banco = _cliente(GESTAO)
        com_cpf = _memoria("MEMORIA-ALFA-v1.0.md").replace(
            "Não analisar prazo nem elegibilidade.",
            "Não analisar prazo nem elegibilidade. Exemplo: paciente 123.456.789-00.",
        )
        assert "123.456.789-00" in com_cpf, "a fixture mudou: o CPF não entrou"

        resposta = _enviar_memoria(cliente, com_cpf)

        assert resposta.status_code == 422
        detalhe = resposta.json()["detail"]
        assert "CPF" in detalhe
        assert "linha 42" in detalhe
        # A recusa não devolve o número: a mensagem vai para tela e log.
        assert "123.456.789-00" not in detalhe
        assert banco.linhas("cm_operadora") == []
        assert banco.linhas("cm_memoria_versao") == []
        assert banco.linhas("cm_regra") == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. Planos do MV
# ═══════════════════════════════════════════════════════════════════════════

ROTA_PLANOS = "/api/contas-medicas/planos"


def _com_operadoras(*siglas: str) -> _Banco:
    return _Banco({"cm_operadora": [{"id": f"op-{s}", "sigla": s, "nome": s, "situacao": "PARCIAL"} for s in siglas]})


class TestPlanosDoMv:
    def test_plano_cadastrado_aparece_na_lista_com_a_operadora_e_a_coluna(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ASSIM", "UNIMED"))

        criado = cliente.post(
            ROTA_PLANOS, json={"nome_mv": "Rioserv Max Qc", "operadora": "ASSIM", "coluna_preco": "CARIOCA"}
        )

        assert criado.status_code == 201, criado.text
        [linha] = banco.linhas("cm_operadora_plano")
        assert (linha["nome_mv"], linha["operadora_id"], linha["coluna_preco"]) == (
            "Rioserv Max Qc",
            "op-ASSIM",
            "CARIOCA",
        )
        lista = cliente.get(ROTA_PLANOS)
        assert lista.status_code == 200
        assert [{k: p[k] for k in ("nome_mv", "operadora", "coluna_preco")} for p in lista.json()["planos"]] == [
            {"nome_mv": "Rioserv Max Qc", "operadora": "ASSIM", "coluna_preco": "CARIOCA"}
        ]

    def test_reconhecimento_acha_o_plano_com_acento_maiuscula_e_sufixo_diferentes(self):
        cliente, _ = _cliente(GESTAO, _com_operadoras("ASSIM"))
        cliente.post(
            ROTA_PLANOS, json={"nome_mv": "Rioserv Intermediário Qc", "operadora": "ASSIM", "coluna_preco": "CARIOCA"}
        )
        cliente.post(ROTA_PLANOS, json={"nome_mv": "Rioserv Max Qc", "operadora": "ASSIM", "coluna_preco": "CARIOCA"})
        planos = cliente.get(ROTA_PLANOS).json()["planos"]

        achado = reconhecer_plano("RIOSERV INTERMEDIARIO QC ENF", planos)

        assert achado is not None
        assert (achado["nome_mv"], achado["operadora"], achado["coluna_preco"]) == (
            "Rioserv Intermediário Qc",
            "ASSIM",
            "CARIOCA",
        )
        assert reconhecer_plano("Rioserv Top Qp", planos) is None

    def test_nome_que_ja_e_reconhecido_como_outro_plano_e_recusado(self):
        """Dois cadastros que o reconhecimento confunde deixariam a conta com
        operadora ou coluna ao acaso."""
        cliente, banco = _cliente(GESTAO, _com_operadoras("ASSIM", "UNIMED"))
        cliente.post(ROTA_PLANOS, json={"nome_mv": "Rioserv Max Qc", "operadora": "ASSIM", "coluna_preco": "CARIOCA"})

        repetido = cliente.post(ROTA_PLANOS, json={"nome_mv": "RIOSERV MAX QC APT", "operadora": "UNIMED"})

        assert repetido.status_code == 409
        assert "Rioserv Max Qc" in repetido.json()["detail"]
        assert len(banco.linhas("cm_operadora_plano")) == 1

    def test_plano_de_operadora_que_nao_existe_e_recusado(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ASSIM"))

        resposta = cliente.post(ROTA_PLANOS, json={"nome_mv": "Plano X", "operadora": "GAMA"})

        assert resposta.status_code == 422
        assert banco.linhas("cm_operadora_plano") == []

    def test_quem_nao_tem_regra_contratual_e_tabelas_nao_ve_nem_cadastra_plano(self):
        cliente, banco = _cliente(FATURISTA, _com_operadoras("ASSIM"))

        assert cliente.get(ROTA_PLANOS).status_code == 403
        assert cliente.post(ROTA_PLANOS, json={"nome_mv": "Plano X", "operadora": "ASSIM"}).status_code == 403
        assert banco.linhas("cm_operadora_plano") == []


# ═══════════════════════════════════════════════════════════════════════════
# 7. Setores do MV
# ═══════════════════════════════════════════════════════════════════════════

ROTA_SETORES = "/api/contas-medicas/setores"


class TestSetoresDoMv:
    def test_setor_cadastrado_com_a_acomodacao_aparece_na_lista(self):
        cliente, banco = _cliente(GESTAO)

        criado = cliente.post(ROTA_SETORES, json={"nome_mv": "CTI1", "acomodacao": "CTI"})

        assert criado.status_code == 201, criado.text
        [linha] = banco.linhas("cm_setor")
        assert (linha["nome_mv"], linha["acomodacao"]) == ("CTI1", "CTI")
        lista = cliente.get(ROTA_SETORES)
        assert lista.status_code == 200
        assert [(s["nome_mv"], s["acomodacao"]) for s in lista.json()["setores"]] == [("CTI1", "CTI")]

    def test_acomodacao_fora_da_lista_e_recusada(self):
        cliente, banco = _cliente(GESTAO)

        assert cliente.post(ROTA_SETORES, json={"nome_mv": "CTI1", "acomodacao": "UTI"}).status_code == 422
        assert banco.linhas("cm_setor") == []

    def test_setor_repetido_sem_diferenca_de_maiuscula_e_conflito(self):
        cliente, banco = _cliente(GESTAO)
        cliente.post(ROTA_SETORES, json={"nome_mv": "CTI1", "acomodacao": "CTI"})

        repetido = cliente.post(ROTA_SETORES, json={"nome_mv": "cti1", "acomodacao": "ENFERMARIA"})

        assert repetido.status_code == 409
        assert len(banco.linhas("cm_setor")) == 1

    def test_quem_nao_tem_regra_contratual_e_tabelas_nao_ve_nem_cadastra_setor(self):
        cliente, banco = _cliente(FATURISTA)

        assert cliente.get(ROTA_SETORES).status_code == 403
        assert cliente.post(ROTA_SETORES, json={"nome_mv": "CTI1", "acomodacao": "CTI"}).status_code == 403
        assert banco.linhas("cm_setor") == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. A lista das operadoras, que abre a tela
# ═══════════════════════════════════════════════════════════════════════════

ROTA_OPERADORAS = "/api/contas-medicas/operadoras"


class TestListaDasOperadoras:
    def test_cada_operadora_vem_com_situacao_versao_regras_e_tabelas(self):
        banco = _com_operadoras("GAMA")
        banco.tabelas["cm_operadora"][0]["situacao"] = "SEM_MEMORIA"
        cliente, _ = _cliente(GESTAO, banco)
        _enviar_memoria(cliente, _memoria("MEMORIA-ALFA-v1.0.md"))

        resposta = cliente.get(ROTA_OPERADORAS)

        assert resposta.status_code == 200
        assert resposta.json()["operadoras"] == [
            {
                "sigla": "ALFA",
                "nome": "Alfa Saúde",
                "situacao": "PARCIAL",
                "versao": "1.0",
                "regras": {"vigentes": 3, "pendentes": 2},
                "tabelas_carregadas": [],
            },
            {
                "sigla": "GAMA",
                "nome": "GAMA",
                "situacao": "SEM_MEMORIA",
                "versao": None,
                "regras": {"vigentes": 0, "pendentes": 0},
                "tabelas_carregadas": [],
            },
        ]

    def test_quem_nao_tem_regra_contratual_e_tabelas_nao_ve_a_lista(self):
        cliente, _ = _cliente(FATURISTA, _com_operadoras("ASSIM"))

        assert cliente.get(ROTA_OPERADORAS).status_code == 403


class TestAsRotasEstaoNoApp:
    def test_o_app_de_verdade_registra_as_rotas_da_carga(self):
        """O router tem `include_router` próprio no `main.py`. A fonte é o
        schema OpenAPI, e não `app.routes` (FastAPI 0.141, issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "get" in caminhos[ROTA_OPERADORAS]
        assert "post" in caminhos[ROTA_MEMORIA]
        assert "get" in caminhos["/api/contas-medicas/operadoras/{sigla}/memoria"]
        assert {"get", "post"} <= set(caminhos[ROTA_PLANOS])
        assert {"get", "post"} <= set(caminhos[ROTA_SETORES])
