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
import uuid
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

    def linha(self, nome: str) -> dict:
        return next(linha for linha in self.tabelas["cm_guia_linha"] if linha["descricao"] == nome)

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


def _uid(nome: str) -> str:
    """O id da linha é UUID, como no banco; o teste fala pelo nome (a descrição)."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cm-guia-linha/{nome}"))


def _g(id_, acao, valor, data, setor, ordem, **campos) -> dict:
    return {
        **_linha(acao, valor, id=_uid(id_)),
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
        grupos = [(g["data"], g["setor"], [linha["descricao"] for linha in g["linhas"]]) for g in guia["grupos"]]
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


# ═══════════════════════════════════════════════════════════════════════════
# 3. Feito, Não procede, Bloqueado e Desfazer
# ═══════════════════════════════════════════════════════════════════════════


def _rota_marcacao(nome: str) -> str:
    return f"{ROTA_GUIA}/linhas/{_uid(nome)}/marcacao"


class TestMarcarLinha:
    def test_feito_muda_o_estado_e_grava_quem_e_quando(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(_rota_marcacao("luva"), json={"estado": "FEITO"})

        assert resposta.status_code == 200
        linha = banco.linha("luva")
        assert (linha["estado"], linha["marcado_por"]) == ("FEITO", "F1")
        assert linha["marcado_em"] is not None
        assert resposta.json()["estado"] == "FEITO"

    def test_bloqueado_muda_o_estado_e_grava_quem_e_quando(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(_rota_marcacao("agulha"), json={"estado": "BLOQUEADO"})

        assert resposta.status_code == 200
        linha = banco.linha("agulha")
        assert (linha["estado"], linha["marcado_por"]) == ("BLOQUEADO", "F1")
        assert linha["marcado_em"] is not None

    def test_nao_procede_com_motivo_e_sem_texto(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(
            _rota_marcacao("senha"), json={"estado": "NAO_PROCEDE", "motivo": "JA_ESTA_NA_CONTA"}
        )

        assert resposta.status_code == 200
        linha = banco.linha("senha")
        assert (linha["estado"], linha["motivo_nao_procede"], linha["texto_nao_procede"]) == (
            "NAO_PROCEDE",
            "JA_ESTA_NA_CONTA",
            None,
        )
        assert (linha["marcado_por"], linha["marcado_em"] is not None) == ("F1", True)

    def test_nao_procede_com_motivo_e_texto(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(
            _rota_marcacao("senha"),
            json={"estado": "NAO_PROCEDE", "motivo": "SEM_EVIDENCIA", "texto": "Não achei na evolução"},
        )

        assert resposta.status_code == 200
        linha = banco.linha("senha")
        assert (linha["motivo_nao_procede"], linha["texto_nao_procede"]) == ("SEM_EVIDENCIA", "Não achei na evolução")

    def test_nao_procede_outro_sem_texto_e_recusado(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(
            _rota_marcacao("senha"), json={"estado": "NAO_PROCEDE", "motivo": "OUTRO", "texto": "   "}
        )

        assert resposta.status_code == 422
        assert banco.linha("senha")["estado"] == "ABERTA"

    def test_nao_procede_outro_com_texto_passa(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(
            _rota_marcacao("senha"), json={"estado": "NAO_PROCEDE", "motivo": "OUTRO", "texto": "Senha vencida"}
        )

        assert resposta.status_code == 200
        assert banco.linha("senha")["motivo_nao_procede"] == "OUTRO"

    def test_nao_procede_sem_motivo_e_recusado(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(_rota_marcacao("senha"), json={"estado": "NAO_PROCEDE"})

        assert resposta.status_code == 422

    def test_linha_validar_nao_tem_botao(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(_rota_marcacao("unidade-pendente"), json={"estado": "FEITO"})

        assert resposta.status_code == 409
        assert banco.linha("unidade-pendente")["estado"] == "EM_VALIDACAO"

    def test_faturista_que_nao_e_dona_nao_marca(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("outra_faturista", banco).post(_rota_marcacao("luva"), json={"estado": "FEITO"})

        assert resposta.status_code == 403
        assert banco.linha("luva")["estado"] == "ABERTA"

    def test_linha_de_outra_conta_recebe_404(self):
        outra = _g("de-outra-conta", "INCLUIR", 10.0, "2026-10-03", "CTI", 1, conta_id="outra")
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=[*_linhas_do_guia(), outra])

        resposta = _cliente("dona", banco).post(_rota_marcacao("de-outra-conta"), json={"estado": "FEITO"})

        assert resposta.status_code == 404
        assert banco.linha("de-outra-conta")["estado"] == "ABERTA"


class TestDesfazer:
    def test_desfazer_volta_para_aberta_e_grava_quem_e_quando(self):
        linhas = _linhas_do_guia()
        senha = next(linha for linha in linhas if linha["descricao"] == "senha")
        senha.update(
            estado="NAO_PROCEDE",
            motivo_nao_procede="OUTRO",
            texto_nao_procede="x",
            marcado_por="F1",
            marcado_em="2026-10-08T10:00:00+00:00",
        )
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("coordenadora", banco).delete(_rota_marcacao("senha"))

        assert resposta.status_code == 200
        linha = banco.linha("senha")
        assert (linha["estado"], linha["motivo_nao_procede"], linha["texto_nao_procede"]) == ("ABERTA", None, None)
        assert linha["marcado_por"] == "CO"
        assert linha["marcado_em"] != "2026-10-08T10:00:00+00:00"

    def test_desfazer_depois_de_concluida_e_recusado(self):
        linhas = _linhas_do_guia()
        next(linha for linha in linhas if linha["descricao"] == "luva").update(estado="FEITO", marcado_por="F1")
        banco = _cenario(conta=_conta(situacao="CONCLUIDA_COM_PENDENCIA"), linhas=linhas)

        resposta = _cliente("dona", banco).delete(_rota_marcacao("luva"))

        assert resposta.status_code == 409
        assert banco.linha("luva")["estado"] == "FEITO"

    def test_marcar_depois_de_concluida_e_recusado(self):
        banco = _cenario(conta=_conta(situacao="CONCLUIDA_COM_PENDENCIA"))

        resposta = _cliente("dona", banco).post(_rota_marcacao("luva"), json={"estado": "FEITO"})

        assert resposta.status_code == 409
        assert banco.linha("luva")["estado"] == "ABERTA"


def _marcadas(linhas: list[dict], **estados: str) -> list[dict]:
    """As linhas do Guia com algumas já marcadas (nome=estado)."""
    for linha in linhas:
        if linha["descricao"] in estados:
            linha.update(estado=estados[linha["descricao"]], marcado_por="F1", marcado_em="2026-10-08T10:00:00+00:00")
    return linhas


# ═══════════════════════════════════════════════════════════════════════════
# 4. Marcar o dia como feito
# ═══════════════════════════════════════════════════════════════════════════


class TestMarcarODiaComoFeito:
    def test_marca_so_as_linhas_abertas_do_grupo(self):
        linhas = _marcadas(_linhas_do_guia(), senha="NAO_PROCEDE", agulha="BLOQUEADO")
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("dona", banco).post(f"{ROTA_GUIA}/dia/feito", json={"data": "2026-10-03", "setor": "CTI"})

        assert resposta.status_code == 200
        assert resposta.json() == {"marcadas": 2}
        estados = {linha["descricao"]: linha["estado"] for linha in banco.tabelas["cm_guia_linha"]}
        assert estados == {
            "luva": "FEITO",
            "lavagem": "FEITO",
            "senha": "NAO_PROCEDE",
            "agulha": "BLOQUEADO",
            "fita": "ABERTA",
            "fisioterapia": "ABERTA",
            "cateter": "ABERTA",
            "unidade-pendente": "EM_VALIDACAO",
            "diaria-acompanhante": "ABERTA",
            "lanceta": "ABERTA",
        }
        assert (banco.linha("luva")["marcado_por"], banco.linha("luva")["marcado_em"] is not None) == ("F1", True)
        assert banco.linha("agulha")["marcado_em"] == "2026-10-08T10:00:00+00:00"

    def test_dia_com_linha_validar_nao_mexe_nela(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(f"{ROTA_GUIA}/dia/feito", json={"data": "2026-10-04", "setor": "CTI"})

        assert resposta.json() == {"marcadas": 2}
        assert banco.linha("unidade-pendente")["estado"] == "EM_VALIDACAO"

    def test_depois_de_concluida_e_recusado(self):
        banco = _cenario(conta=_conta(situacao="CONCLUIDA"))

        resposta = _cliente("dona", banco).post(f"{ROTA_GUIA}/dia/feito", json={"data": "2026-10-03", "setor": "CTI"})

        assert resposta.status_code == 409
        assert banco.linha("luva")["estado"] == "ABERTA"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Concluir
# ═══════════════════════════════════════════════════════════════════════════

ROTA_CONCLUIR = f"{ROTA_GUIA}/concluir"
NOVE = ("luva", "lavagem", "agulha", "senha", "fita", "fisioterapia", "cateter", "diaria-acompanhante", "lanceta")


def _sem_a_validar() -> list[dict]:
    return [linha for linha in _linhas_do_guia() if linha["acao"] != "VALIDAR"]


def _outra_conta(id_: str, faturista: str, situacao: str, ordem: int) -> dict:
    return _conta(id=id_, faturista_id=faturista, situacao=situacao, ordem_fila=ordem, numero_conta=id_[:4])


class TestConcluir:
    def test_todas_resolvidas_fica_concluida(self):
        linhas = _marcadas(_sem_a_validar(), **{**dict.fromkeys(NOVE, "FEITO"), "senha": "NAO_PROCEDE"})
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        assert resposta.status_code == 200
        assert (resposta.json()["situacao"], resposta.json()["pendencias"]) == ("CONCLUIDA", 0)
        assert banco.conta(CONTA)["situacao"] == "CONCLUIDA"
        assert banco.conta(CONTA)["concluida_em"] is not None

    def test_aberta_em_validacao_e_bloqueada_ficam_como_pendencia_com_a_contagem(self):
        feitas = dict.fromkeys(NOVE[:7], "FEITO")
        linhas = _marcadas(_linhas_do_guia(), **feitas, **{"diaria-acompanhante": "BLOQUEADO"})
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        # lanceta sem marcação, diária bloqueada e a unidade em validação
        assert (resposta.json()["situacao"], resposta.json()["pendencias"]) == ("CONCLUIDA_COM_PENDENCIA", 3)
        assert banco.conta(CONTA)["situacao"] == "CONCLUIDA_COM_PENDENCIA"

    def test_so_a_linha_em_validacao_ja_e_pendencia(self):
        linhas = _marcadas(_linhas_do_guia(), **dict.fromkeys(NOVE, "FEITO"))
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        assert (resposta.json()["situacao"], resposta.json()["pendencias"]) == ("CONCLUIDA_COM_PENDENCIA", 1)

    def test_traz_a_proxima_a_fazer_da_faturista_na_ordem_de_envio(self):
        outras = [
            _outra_conta("aaaaaaaa-0000-0000-0000-000000000030", "F1", "A_FAZER", 30),
            _outra_conta("aaaaaaaa-0000-0000-0000-000000000020", "F1", "A_FAZER", 20),
            _outra_conta("aaaaaaaa-0000-0000-0000-000000000005", "F1", "EM_CORRECAO", 5),
            _outra_conta("aaaaaaaa-0000-0000-0000-000000000001", "F2", "A_FAZER", 1),
            _outra_conta("aaaaaaaa-0000-0000-0000-000000000002", "F1", "CONCLUIDA", 2),
        ]
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), outras_contas=outras)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        assert resposta.json()["proxima_conta_id"] == "aaaaaaaa-0000-0000-0000-000000000020"

    def test_sem_proxima_a_fazer_vem_nulo(self):
        outras = [_outra_conta("aaaaaaaa-0000-0000-0000-000000000001", "F2", "A_FAZER", 1)]
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), outras_contas=outras)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        assert resposta.json()["proxima_conta_id"] is None

    def test_nota_de_entrada_sem_as_nao_procede_e_maior_e_a_bruta_nao_muda(self):
        """Sem a senha (-19,97) e a diária (+239,67): apontado 324,96, devido
        2.030,30, nota 84. A bruta, 74, fica como estava."""
        linhas = _marcadas(_linhas_do_guia(), senha="NAO_PROCEDE", **{"diaria-acompanhante": "NAO_PROCEDE"})
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"), linhas=linhas)

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={})

        assert (resposta.json()["nota_entrada"], resposta.json()["nota_bruta"]) == (84, 74)
        assert (banco.conta(CONTA)["nota_entrada"], banco.conta(CONTA)["nota_bruta"]) == (84, 74)

    def test_observacao_para_a_gestao_fica_gravada_com_o_autor(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        _cliente("dona", banco).post(ROTA_CONCLUIR, json={"observacao": "  Luva já vem no kit do CTI  "})

        assert banco.tabelas["cm_observacao"] == [
            {"id": "cm_observacao-1", "conta_id": CONTA, "autor_id": "F1", "texto": "Luva já vem no kit do CTI"}
        ]

    def test_observacao_em_branco_nao_grava_nada(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        resposta = _cliente("dona", banco).post(ROTA_CONCLUIR, json={"observacao": "   "})

        assert resposta.status_code == 200
        assert banco.tabelas["cm_observacao"] == []

    def test_concluir_de_novo_e_recusado(self):
        banco = _cenario(conta=_conta(situacao="CONCLUIDA"))

        assert _cliente("dona", banco).post(ROTA_CONCLUIR, json={}).status_code == 409

    def test_faturista_que_nao_e_dona_nao_conclui(self):
        banco = _cenario(conta=_conta(situacao="EM_CORRECAO"))

        assert _cliente("outra_faturista", banco).post(ROTA_CONCLUIR, json={}).status_code == 403
        assert banco.conta(CONTA)["situacao"] == "EM_CORRECAO"
