"""O Guia da faturista (issue #1121, PRD #1113, ADR 0070).

A faturista abre o Guia de uma Conta, vê o que corrigir linha por linha, marca
Feito, Não procede ou Bloqueado e conclui. As linhas reais chegam pelo
processamento, em outra fatia; aqui os testes semeiam `cm_guia_linha` direto.

A nota de entrada segue a spec do diretor (item 9.7): `100 × (1 − R$ apontado
÷ R$ devido)`, arredondada, mínimo 0. O exemplo da spec é a fonte do esperado:
9 linhas somam R$ 584,60 em valor absoluto e a nota 74 corresponde a um R$
devido de cerca de R$ 2.250.
"""

from __future__ import annotations

import os
import re
import sys
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.services.contas_medicas.guia import nota_de_entrada  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

# As 9 linhas do exemplo: 584,60 em valor absoluto. Diferença com sinal:
# Incluir e preço a maior são positivos; Retirar e quantidade a menos, negativos.
# A soma com sinal dá 459,98; com 1.790,02 lançados, o R$ devido fica 2.250,00.
TOTAL_LANCADO_DO_EXEMPLO = 1790.02


def _linha(acao: str, valor: float | None, **campos) -> dict:
    base = {
        "id": f"l-{acao}-{valor}",
        "acao": acao,
        "valor_diferenca": valor,
        "preco_lancado": 1.0,
        "preco_tabela": 1.0,
        "estado": "EM_VALIDACAO" if acao == "VALIDAR" else "ABERTA",
    }
    return {**base, **campos}


def _nove_linhas_do_exemplo() -> list[dict]:
    return [
        _linha("INCLUIR", 68.40, id="luva"),
        _linha("AJUSTAR_QUANTIDADE", -4.17, id="lavagem"),
        _linha("RETIRAR", -19.97, id="senha", preco_tabela=None),
        _linha("CORRIGIR_PRECO", 12.72, id="agulha"),
        _linha("INCLUIR", 239.67, id="diaria-acompanhante"),
        _linha("INCLUIR", 120.00, id="fisioterapia"),
        _linha("CORRIGIR_PRECO", 45.50, id="cateter"),
        _linha("AJUSTAR_QUANTIDADE", -38.17, id="fita"),
        _linha("INCLUIR", 36.00, id="lanceta"),
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 1. nota_de_entrada, o helper puro
# ═══════════════════════════════════════════════════════════════════════════


class TestNotaDeEntrada:
    def test_as_nove_linhas_do_exemplo_da_spec_dao_nota_74(self):
        nota = nota_de_entrada(_nove_linhas_do_exemplo(), TOTAL_LANCADO_DO_EXEMPLO)

        assert nota.apontado == Decimal("584.60")
        assert nota.devido == Decimal("2250.00")
        assert nota.nota == 74
        assert nota.itens_apontados == 9

    def test_linha_validar_fica_fora_da_nota_e_vai_para_o_em_validacao(self):
        linhas = [*_nove_linhas_do_exemplo(), _linha("VALIDAR", 1212.00, id="unidade-pendente")]

        nota = nota_de_entrada(linhas, TOTAL_LANCADO_DO_EXEMPLO)

        assert (nota.nota, nota.apontado, nota.itens_apontados) == (74, Decimal("584.60"), 9)
        assert nota.em_validacao == Decimal("1212.00")

    def test_linha_nao_conferido_fica_fora_da_nota(self):
        """Não conferido: Incluir sem preço de tabela (o valor saiu do unitário
        da própria conta) e linha sem valor nenhum."""
        linhas = [
            *_nove_linhas_do_exemplo(),
            _linha("INCLUIR", 300.00, id="preco-da-conta", preco_tabela=None),
            _linha("AJUSTAR_QUANTIDADE", None, id="sem-valor"),
        ]

        nota = nota_de_entrada(linhas, TOTAL_LANCADO_DO_EXEMPLO)

        assert (nota.nota, nota.apontado, nota.itens_apontados) == (74, Decimal("584.60"), 9)

    def test_retirar_sem_preco_de_tabela_entra_na_nota(self):
        """Retirar tira o que foi lançado: o valor vem da conta, não da tabela."""
        nota = nota_de_entrada([_linha("RETIRAR", -100.00, preco_tabela=None)], 1000)

        assert (nota.nota, nota.apontado) == (89, Decimal("100.00"))

    def test_nota_nunca_fica_abaixo_de_zero(self):
        nota = nota_de_entrada([_linha("INCLUIR", 500.00), _linha("RETIRAR", -900.00)], 1000)

        assert nota.nota == 0


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco e o cenário semeado
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _matriz_da_migration() -> list[dict[str, Any]]:
    """A matriz perfil x permissão como a migration 116 grava."""
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


class _Consulta:
    """O pedaço do cliente do Supabase que as rotas do Guia usam."""

    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: list[tuple[str, bool]] = []
        self._limite: int | None = None
        self._update: dict | None = None
        self._insert: dict | list | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def order(self, coluna, desc=False):
        self._ordem.append((coluna, desc))
        return self

    def limit(self, n):
        self._limite = n
        return self

    def update(self, campos):
        self._update = dict(campos)
        return self

    def insert(self, linhas):
        self._insert = linhas
        return self

    def execute(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            novas = self._insert if isinstance(self._insert, list) else [self._insert]
            gravadas = [{"id": f"{self._nome}-{len(tabela) + i + 1}", **n} for i, n in enumerate(novas)]
            tabela.extend(gravadas)
            return SimpleNamespace(data=[dict(g) for g in gravadas])
        casam = [linha for linha in tabela if all(f(linha) for f in self._filtros)]
        if self._update is not None:
            for linha in casam:
                linha.update(self._update)
            return SimpleNamespace(data=[dict(linha) for linha in casam])
        for coluna, desc in reversed(self._ordem):
            casam.sort(key=lambda linha, c=coluna: (linha.get(c) is None, linha.get(c) or 0), reverse=desc)
        if self._limite is not None:
            casam = casam[: self._limite]
        return SimpleNamespace(data=[dict(linha) for linha in casam])


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _Consulta(self, nome)

    def linha(self, linha_id: str) -> dict:
        return next(linha for linha in self.tabelas["cm_guia_linha"] if linha["id"] == linha_id)

    def conta(self, conta_id: str) -> dict:
        return next(conta for conta in self.tabelas["cm_conta"] if conta["id"] == conta_id)


def _pessoa(pid: str, perfil: str | None, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": f"Pessoa {pid}",
        "email": f"{pid.lower()}@hsm.test",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": perfil,
        "github_login": None,
    }
    return {**base, **campos}


PESSOAS = {
    "dona": _pessoa("F1", "faturista"),
    "outra_faturista": _pessoa("F2", "faturista"),
    "coordenadora": _pessoa("CO", "coordenadora"),
    "credenciamento": _pessoa("CR", "credenciamento"),
    "sem_eixo": _pessoa("RG", None, access_profile="regular"),
}

CONTA = "11111111-1111-1111-1111-111111111111"


def _g(id_, acao, valor, data, setor, ordem, **campos) -> dict:
    return {
        **_linha(acao, valor, id=id_),
        "conta_id": CONTA,
        "data": data,
        "data_fim": None,
        "setor": setor,
        "ordem": ordem,
        "codigo": f"COD-{id_}",
        "descricao": id_,
        "marcado_por": None,
        "marcado_em": None,
        "motivo_nao_procede": None,
        "texto_nao_procede": None,
        **campos,
    }


def _linhas_do_guia() -> list[dict]:
    """As 9 linhas do exemplo, espalhadas por dia e setor, mais uma Validar.
    Semeadas fora de ordem: a ordem da tela é a do servidor."""
    return [
        _g("lanceta", "INCLUIR", 36.00, "2026-10-05", "CTI", 9),
        _g("unidade-pendente", "VALIDAR", 1212.00, "2026-10-04", "CTI", 10),
        _g("senha", "RETIRAR", -19.97, "2026-10-03", "CTI", 3, preco_tabela=None),
        _g("fita", "AJUSTAR_QUANTIDADE", -38.17, "2026-10-03", "ENFERMARIA", 8),
        _g("cateter", "CORRIGIR_PRECO", 45.50, "2026-10-04", "CTI", 7),
        _g("agulha", "CORRIGIR_PRECO", 12.72, "2026-10-03", "CTI", 4),
        _g("diaria-acompanhante", "INCLUIR", 239.67, "2026-10-05", "CTI", 5),
        _g("lavagem", "AJUSTAR_QUANTIDADE", -4.17, "2026-10-03", "CTI", 2),
        _g("fisioterapia", "INCLUIR", 120.00, "2026-10-04", "CTI", 6),
        _g("luva", "INCLUIR", 68.40, "2026-10-03", "CTI", 1, data_fim="2026-10-05"),
    ]


def _conta(**campos) -> dict:
    base = {
        "id": CONTA,
        "atendimento_id": "at-1",
        "numero_conta": "48811",
        "parcial_ordem": 1,
        "periodo_inicio": "2026-10-03",
        "periodo_fim": "2026-10-07",
        "total_lancado": TOTAL_LANCADO_DO_EXEMPLO,
        "situacao": "A_FAZER",
        "parecer_parcial": False,
        "faltantes": None,
        "nota_bruta": 74,
        "nota_entrada": 74,
        "faturista_id": "F1",
        "ordem_fila": 10,
        "aberta_em": None,
        "concluida_em": None,
    }
    return {**base, **campos}


def _cenario(conta: dict | None = None, linhas: list[dict] | None = None, outras_contas=()) -> _Banco:
    return _Banco(
        {
            "participantes": list(PESSOAS.values()),
            "cm_perfil_permissao": _matriz_da_migration(),
            "cm_operadora": [{"id": "op-1", "sigla": "ASSIM", "nome": "ASSIM Saúde"}],
            "cm_atendimento": [
                {
                    "id": "at-1",
                    "numero_atendimento": "31245",
                    "paciente_rotulo": "Maria S.",
                    "idade_anos": 67,
                    "operadora_id": "op-1",
                    "plano": "ASSIM CARIOCA ENF",
                    "coluna_preco": "CARIOCA",
                }
            ],
            "cm_conta": [conta or _conta(), *outras_contas],
            "cm_guia_linha": _linhas_do_guia() if linhas is None else linhas,
            "cm_observacao": [],
        }
    )


def _cliente(quem: str, banco: _Banco) -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(guia_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


ROTA_GUIA = f"/api/contas-medicas/contas/{CONTA}/guia"


# ═══════════════════════════════════════════════════════════════════════════
# 2. GET do Guia
# ═══════════════════════════════════════════════════════════════════════════


class TestAbrirOGuia:
    def test_devolve_cabecalho_tres_numeros_e_linhas_agrupadas_por_dia_e_setor(self):
        resposta = _cliente("dona", _cenario()).get(ROTA_GUIA)

        assert resposta.status_code == 200
        guia = resposta.json()
        assert guia["cabecalho"] == {
            "numero_atendimento": "31245",
            "paciente_rotulo": "Maria S.",
            "numero_conta": "48811",
            "operadora": "ASSIM",
            "coluna_preco": "CARIOCA",
            "periodo_inicio": "2026-10-03",
            "periodo_fim": "2026-10-07",
            "situacao": "EM_CORRECAO",
            "parecer_parcial": False,
            "faltantes": [],
        }
        assert guia["numeros"] == {
            "nota_entrada": 74,
            "valor_a_ajustar": 584.60,
            "itens_a_ajustar": 9,
            "valor_em_validacao": 1212.00,
            "itens_feitos": 0,
            "itens_total": 9,
            "itens_sem_marcacao": 9,
        }
        grupos = [(g["data"], g["setor"], [linha["id"] for linha in g["linhas"]]) for g in guia["grupos"]]
        assert grupos == [
            ("2026-10-03", "CTI", ["luva", "lavagem", "agulha", "senha"]),
            ("2026-10-03", "ENFERMARIA", ["fita"]),
            ("2026-10-04", "CTI", ["fisioterapia", "cateter", "unidade-pendente"]),
            ("2026-10-05", "CTI", ["diaria-acompanhante", "lanceta"]),
        ]

    def test_faturista_que_nao_e_dona_recebe_403(self):
        assert _cliente("outra_faturista", _cenario()).get(ROTA_GUIA).status_code == 403

    def test_quem_nao_tem_o_eixo_recebe_403(self):
        assert _cliente("sem_eixo", _cenario()).get(ROTA_GUIA).status_code == 403

    def test_credenciamento_sem_enviar_e_corrigir_recebe_403(self):
        assert _cliente("credenciamento", _cenario()).get(ROTA_GUIA).status_code == 403

    def test_painel_completo_abre_conta_de_outra_faturista(self):
        resposta = _cliente("coordenadora", _cenario()).get(ROTA_GUIA)

        assert resposta.status_code == 200
        assert resposta.json()["cabecalho"]["numero_atendimento"] == "31245"

    def test_conta_que_nao_existe_recebe_404(self):
        outra = "22222222-2222-2222-2222-222222222222"

        assert _cliente("dona", _cenario()).get(f"/api/contas-medicas/contas/{outra}/guia").status_code == 404


class TestAbrirMudaParaEmCorrecao:
    def test_abrir_muda_de_a_fazer_para_em_correcao_e_grava_quando(self):
        banco = _cenario()

        _cliente("dona", banco).get(ROTA_GUIA)

        conta = banco.conta(CONTA)
        assert conta["situacao"] == "EM_CORRECAO"
        assert conta["aberta_em"] is not None

    def test_reabrir_nao_muda_a_situacao_nem_o_carimbo(self):
        banco = _cenario()
        cliente = _cliente("dona", banco)
        cliente.get(ROTA_GUIA)
        primeira_abertura = banco.conta(CONTA)["aberta_em"]

        cliente.get(ROTA_GUIA)

        assert banco.conta(CONTA)["situacao"] == "EM_CORRECAO"
        assert banco.conta(CONTA)["aberta_em"] == primeira_abertura

    def test_abrir_conta_concluida_nao_volta_para_em_correcao(self):
        banco = _cenario(conta=_conta(situacao="CONCLUIDA"))

        _cliente("dona", banco).get(ROTA_GUIA)

        assert banco.conta(CONTA)["situacao"] == "CONCLUIDA"

    def test_conta_sem_guia_pronto_recebe_409(self):
        banco = _cenario(conta=_conta(situacao="PROCESSANDO"))

        assert _cliente("dona", banco).get(ROTA_GUIA).status_code == 409
