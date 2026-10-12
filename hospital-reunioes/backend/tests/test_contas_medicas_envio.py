"""Envio e fila de Contas médicas (issue #1123, PRD #1113, ADR 0070).

A faturista arrasta a conta e o prontuário do MV, o app pareia os dois pelo
número do atendimento lido dentro de cada PDF e a conta entra na fila. Tudo
pela rota de verdade, atrás da permissão "enviar e corrigir contas".

Os PDFs são sintéticos. O extrator (`pdftotext` num processo isolado) é
trocado por um dublê que devolve o texto de cada página: o "PDF" do teste é o
próprio texto, com as páginas separadas por form feed, como o `pdftotext` as
separa. Um teste só passa pelo extrator de verdade, com um PDF gerado aqui.

O dublê do banco guarda as restrições da migration 116 que o envio pode ferir:
o número do atendimento é único, e a situação da conta e o tipo do arquivo
têm CHECK. Violar uma delas estoura como o PostgREST estouraria.
"""

from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import UTC, datetime, timedelta
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
from app.routers import contas_medicas_envio as envio_router  # noqa: E402
from app.services.contas_medicas import envio as envio_service  # noqa: E402
from app.services.contas_medicas_extrator import Pagina  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

ROTA_ENVIO = "/api/contas-medicas/envios"
ROTA_FILA = "/api/contas-medicas/fila"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _extrator_de_texto(monkeypatch):
    """O "PDF" do teste é o texto das páginas separado por form feed."""

    def extrair(pdf: bytes):
        partes = pdf.decode("utf-8").split("\f")
        return [Pagina(numero=n, texto=t, sem_texto=not t.strip()) for n, t in enumerate(partes, start=1)]

    monkeypatch.setattr(envio_service, "extrair_paginas", extrair)


# ═══════════════════════════════════════════════════════════════════════════
# Os PDFs sintéticos
# ═══════════════════════════════════════════════════════════════════════════


def _texto_da_conta(atendimento: str, conta: str, inicio: str, fim: str, plano: str = "ASSIM CARIOCA ENF") -> str:
    """A primeira página da "Fatura Individual" do MV, só o cabeçalho e o total."""
    return f"""\
HOSPITAL FICTICIO DE TESTE                                                         Página 1 de 1
                                   Fatura Individual

Atendimento: {atendimento}          Conta: {conta}          Tipo: INTERNACAO
Internação: {inicio} 08:30
Período da   {inicio} a {fim}          Acomodação: ENFERMARIA
Plano: {plano}
Guia: 123456789

Total da Conta:                                                                  1.374,87
"""


CAPA = """\
                         HOSPITAL FICTICIO DE TESTE
               DECLARAÇÃO DE RECEBIMENTO DE PRONTUÁRIO
Nome: PACIENTE FICTICIA DE TESTE
Tipo da impressão: Completa
Grupos impressos
Grupo: EVOLUÇÃO MÉDICA      Quantidade: 2
"""


def _pagina_de_evolucao(atendimento: str, dia: str) -> str:
    return f"""\
EVOLUÇÃO MÉDICA
ATENDIMENTO: {atendimento}
Data/Hora do Documento: {dia} 09:00
Paciente estável, segue em observação no leito.
"""


def _texto_do_prontuario(atendimento: str, *, pronto_socorro: str | None = None) -> str:
    paginas = [CAPA, _pagina_de_evolucao(atendimento, "02/10/2026"), _pagina_de_evolucao(atendimento, "03/10/2026")]
    if pronto_socorro:
        paginas.insert(1, _pagina_de_evolucao(pronto_socorro, "01/10/2026"))
    return "\f".join(paginas)


def _conta(atendimento: str, conta: str, inicio="01/10/2026", fim="05/10/2026", nome=None, plano="ASSIM CARIOCA ENF"):
    texto = _texto_da_conta(atendimento, conta, inicio, fim, plano)
    return ("arquivos", (nome or f"conta-{conta}.pdf", texto.encode("utf-8"), "application/pdf"))


def _prontuario(atendimento: str, nome=None, **kw):
    texto = _texto_do_prontuario(atendimento, **kw)
    return ("arquivos", (nome or f"prontuario-{atendimento}.pdf", texto.encode("utf-8"), "application/pdf"))


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════


def _matriz_da_migration() -> list[dict[str, Any]]:
    sql = MIGRATION.read_text(encoding="utf-8")
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", sql, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


SITUACOES_DA_CONTA = {
    "AGUARDANDO_ARQUIVO",
    "NA_FILA",
    "PROCESSANDO",
    "A_FAZER",
    "EM_CORRECAO",
    "CONCLUIDA",
    "CONCLUIDA_COM_PENDENCIA",
    "RETORNO",
    "ERRO",
}


def _violacao(nome: str, linha: dict) -> str | None:
    if nome == "cm_conta" and "situacao" in linha and linha["situacao"] not in SITUACOES_DA_CONTA:
        return "cm_conta_situacao_check"
    if nome == "cm_arquivo" and "tipo" in linha and linha["tipo"] not in {"CONTA", "PRONTUARIO"}:
        return "cm_arquivo_tipo_check"
    return None


class _Consulta:
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

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def gt(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and str(linha.get(coluna)) > str(valor))
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
            gravadas = []
            for nova in novas:
                if violacao := _violacao(self._nome, nova):
                    raise APIError({"message": violacao, "code": "23514"})
                if self._nome == "cm_atendimento" and any(
                    a["numero_atendimento"] == nova["numero_atendimento"] for a in tabela
                ):
                    raise APIError({"message": "idx_cm_atendimento_numero", "code": "23505"})
                self._banco.relogio += 1
                gravadas.append(
                    {
                        "id": str(uuid.uuid4()),
                        "criado_em": f"2026-10-12T10:00:00.{self._banco.relogio:06d}+00:00",
                        **nova,
                    }
                )
            tabela.extend(gravadas)
            return SimpleNamespace(data=[dict(g) for g in gravadas])
        casam = [linha for linha in tabela if all(f(linha) for f in self._filtros)]
        if self._update is not None:
            for linha in casam:
                if violacao := _violacao(self._nome, {**linha, **self._update}):
                    raise APIError({"message": violacao, "code": "23514"})
                linha.update(self._update)
            return SimpleNamespace(data=[dict(linha) for linha in casam])
        for coluna, desc in reversed(self._ordem):
            casam.sort(key=lambda linha, c=coluna: (linha.get(c) is None, str(linha.get(c) or "")), reverse=desc)
        if self._limite is not None:
            casam = casam[: self._limite]
        return SimpleNamespace(data=[dict(linha) for linha in casam])


class _Bucket:
    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self._nome = nome

    def upload(self, caminho, conteudo, _opcoes=None):
        self._banco.bucket[(self._nome, caminho)] = conteudo
        return SimpleNamespace(path=caminho)


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas
        self.bucket: dict[tuple[str, str], bytes] = {}
        self.relogio = 0
        self.storage = SimpleNamespace(from_=lambda nome: _Bucket(self, nome))

    def table(self, nome: str):
        return _Consulta(self, nome)

    def contas_do_atendimento(self, numero: str) -> list[dict]:
        atendimento = next(a for a in self.tabelas["cm_atendimento"] if a["numero_atendimento"] == numero)
        return [c for c in self.tabelas.get("cm_conta", []) if c["atendimento_id"] == atendimento["id"]]


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
    "faturista": _pessoa("F1", "faturista"),
    "outra_faturista": _pessoa("F2", "faturista"),
    "coordenadora": _pessoa("CO", "coordenadora"),
    "credenciamento": _pessoa("CR", "credenciamento"),
    "sem_eixo": _pessoa("RG", None, access_profile="regular"),
}


def _cenario(**tabelas) -> _Banco:
    base = {
        "participantes": list(PESSOAS.values()),
        "cm_perfil_permissao": _matriz_da_migration(),
        "cm_operadora": [{"id": "op-1", "sigla": "ASSIM", "nome": "ASSIM Saúde", "situacao": "PRONTA"}],
        "cm_operadora_plano": [
            {"id": "pl-1", "operadora_id": "op-1", "nome_mv": "ASSIM CARIOCA", "coluna_preco": "CARIOCA"},
        ],
        "cm_envio": [],
        "cm_arquivo": [],
        "cm_atendimento": [],
        "cm_conta": [],
        "cm_eventos": [],
        "cm_guia_linha": [],
    }
    return _Banco({**base, **tabelas})


def _cliente(quem: str, banco: _Banco) -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(envio_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _situacoes(banco: _Banco, numero: str) -> list[str]:
    return sorted(c["situacao"] for c in banco.contas_do_atendimento(numero))


# ═══════════════════════════════════════════════════════════════════════════
# 1. O envio e o "Último envio"
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvio:
    def test_tres_pares_devolvem_as_tres_frases_da_spec_e_entram_na_fila_conforme_o_caso(self):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO,
            files=[
                _conta("31302", "48001"),
                _prontuario("31302"),
                _conta("31310", "48010", "01/10/2026", "15/10/2026"),
                _conta("31310", "48011", "16/10/2026", "31/10/2026"),
                _prontuario("31310"),
                _conta("31318", "48018"),
            ],
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [linha["texto"] for linha in corpo["ultimo_envio"]] == [
            "31302, conta e prontuário",
            "31310, 2 parciais e prontuário",
            "31318, falta o prontuário",
        ]
        assert corpo["recusas"] == []
        assert _situacoes(banco, "31302") == ["NA_FILA"]
        assert _situacoes(banco, "31310") == ["NA_FILA", "NA_FILA"]
        assert _situacoes(banco, "31318") == ["AGUARDANDO_ARQUIVO"]
        assert {c["faturista_id"] for c in banco.tabelas["cm_conta"]} == {"F1"}

    @pytest.mark.parametrize("quem", ["credenciamento", "sem_eixo"])
    def test_sem_a_permissao_de_enviar_e_corrigir_contas_recebe_403(self, quem):
        banco = _cenario()

        resposta = _cliente(quem, banco).post(ROTA_ENVIO, files=[_conta("31302", "48001"), _prontuario("31302")])

        assert resposta.status_code == 403
        assert banco.tabelas["cm_conta"] == []
        assert banco.bucket == {}


# ═══════════════════════════════════════════════════════════════════════════
# 2. O tipo vem do conteúdo, não do nome
# ═══════════════════════════════════════════════════════════════════════════


def _pdf_de_verdade(*paginas: str) -> bytes:
    """PDF gerado pelo WeasyPrint do projeto, uma página por texto, em `<pre>`
    para o `pdftotext -layout` devolver as linhas como estão."""
    from html import escape

    from weasyprint import HTML

    corpo = "".join(
        f'<pre style="page-break-before: always; font-size: 7pt">{escape(texto)}</pre>' for texto in paginas
    )
    return HTML(string=f"<html><body>{corpo}</body></html>").write_pdf()


class TestTipoPeloConteudo:
    def test_conta_com_nome_de_prontuario_entra_como_conta(self):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48001", nome="prontuario.pdf"), _prontuario("31302", nome="conta.pdf")]
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["ultimo_envio"][0]["texto"] == "31302, conta e prontuário"
        conta = banco.contas_do_atendimento("31302")[0]
        arquivo_da_conta = next(a for a in banco.tabelas["cm_arquivo"] if a["id"] == conta["arquivo_id"])
        assert arquivo_da_conta["tipo"] == "CONTA"
        assert conta["numero_conta"] == "48001"
        assert sorted(a["tipo"] for a in banco.tabelas["cm_arquivo"]) == ["CONTA", "PRONTUARIO"]

    def test_o_pdf_de_verdade_passa_pelo_pdftotext_e_e_lido_pelo_conteudo(self, monkeypatch):
        """Sem o dublê: o PDF gerado aqui atravessa o extrator isolado."""
        from app.services import contas_medicas_extrator

        monkeypatch.setattr(envio_service, "extrair_paginas", contas_medicas_extrator.extrair_paginas)
        banco = _cenario()
        conta = _pdf_de_verdade(_texto_da_conta("31302", "48001", "01/10/2026", "05/10/2026"))

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[("arquivos", ("prontuario.pdf", conta, "application/pdf"))]
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["ultimo_envio"][0]["texto"] == "31302, falta o prontuário"
        assert banco.contas_do_atendimento("31302")[0]["periodo_fim"] == "2026-10-05"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Plano sem par
# ═══════════════════════════════════════════════════════════════════════════


class TestPlanoSemPar:
    def test_recusa_so_a_conta_do_plano_desconhecido_e_os_outros_atendimentos_seguem(self):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO,
            files=[
                _conta("31302", "48001", nome="conta-unimed.pdf", plano="UNIMED RIO ENF"),
                _conta("31310", "48010"),
                _prontuario("31310"),
            ],
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["recusas"] == [
            {
                "arquivo": "conta-unimed.pdf",
                "numero_atendimento": "31302",
                "motivo": "Plano UNIMED RIO ENF ainda não configurado",
            }
        ]
        assert [linha["texto"] for linha in corpo["ultimo_envio"]] == ["31310, conta e prontuário"]
        assert _situacoes(banco, "31310") == ["NA_FILA"]
        assert [c["numero_conta"] for c in banco.tabelas["cm_conta"]] == ["48010"]
        assert len(banco.bucket) == 2

    def test_o_plano_reconhecido_leva_a_operadora_e_a_coluna_para_o_atendimento(self):
        banco = _cenario()

        _cliente("faturista", banco).post(ROTA_ENVIO, files=[_conta("31302", "48001", plano="Assim Carioca APT")])

        atendimento = banco.tabelas["cm_atendimento"][0]
        assert (atendimento["operadora_id"], atendimento["plano"], atendimento["coluna_preco"]) == (
            "op-1",
            "Assim Carioca APT",
            "CARIOCA",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 4. O prontuário que já está no sistema
# ═══════════════════════════════════════════════════════════════════════════


def _daqui_a(dias: int) -> str:
    return (datetime.now(UTC) + timedelta(days=dias)).isoformat()


def _com_prontuario_no_sistema(apagar_em: str, prontuario_ate: str = "2026-10-10", **arquivo) -> _Banco:
    """O atendimento 31302 com a parcial 1 já analisada e o prontuário de um envio anterior."""
    return _cenario(
        cm_atendimento=[{"id": "at-1", "numero_atendimento": "31302"}],
        cm_arquivo=[
            {
                "id": "arq-antigo",
                "envio_id": "envio-antigo",
                "tipo": "PRONTUARIO",
                "atendimento_id": "at-1",
                "numero_atendimento": "31302",
                "apagar_em": apagar_em,
                "apagado_em": None,
                **arquivo,
            }
        ],
        cm_eventos=[{"id": "ev-1", "atendimento_id": "at-1", "prontuario_ate": prontuario_ate}],
        cm_conta=[
            {
                "id": "parcial-1",
                "atendimento_id": "at-1",
                "arquivo_id": "arq-conta-1",
                "numero_conta": "48001",
                "situacao": "A_FAZER",
                "faturista_id": "F1",
                "ordem_fila": 1,
            }
        ],
    )


class TestProntuarioNoSistema:
    def test_conta_nova_pareia_com_o_prontuario_de_ate_7_dias_e_avisa_o_periodo_alem_dele(self):
        banco = _com_prontuario_no_sistema(apagar_em=_daqui_a(3))

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48002", "11/10/2026", "20/10/2026")]
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["ultimo_envio"] == [
            {
                "numero_atendimento": "31302",
                "frase": "conta e prontuário",
                "texto": "31302, conta e prontuário",
                "aviso": "O período da conta vai até 20/10/2026 e o prontuário no sistema, até 10/10/2026. "
                "Envie o prontuário atualizado.",
            }
        ]
        nova = next(c for c in banco.contas_do_atendimento("31302") if c["numero_conta"] == "48002")
        assert nova["situacao"] == "NA_FILA"
        assert [a["tipo"] for a in banco.tabelas["cm_arquivo"]] == ["PRONTUARIO", "CONTA"]

    def test_periodo_dentro_do_prontuario_nao_avisa(self):
        banco = _com_prontuario_no_sistema(apagar_em=_daqui_a(3), prontuario_ate="2026-10-20")

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48002", "11/10/2026", "20/10/2026")]
        )

        assert resposta.json()["ultimo_envio"][0]["aviso"] is None

    @pytest.mark.parametrize(
        "arquivo",
        [{"apagar_em": _daqui_a(-1)}, {"apagar_em": _daqui_a(3), "apagado_em": _daqui_a(-1)}],
        ids=["passou-dos-7-dias", "ja-saiu-do-bucket"],
    )
    def test_prontuario_de_mais_de_7_dias_nao_pareia(self, arquivo):
        banco = _com_prontuario_no_sistema(**arquivo)

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48002", "11/10/2026", "20/10/2026")]
        )

        assert resposta.json()["ultimo_envio"][0]["texto"] == "31302, falta o prontuário"
        nova = next(c for c in banco.contas_do_atendimento("31302") if c["numero_conta"] == "48002")
        assert nova["situacao"] == "AGUARDANDO_ARQUIVO"

    def test_o_prontuario_que_chega_depois_poe_na_fila_a_conta_que_esperava(self):
        banco = _cenario()
        cliente = _cliente("faturista", banco)
        cliente.post(ROTA_ENVIO, files=[_conta("31318", "48018")])
        assert _situacoes(banco, "31318") == ["AGUARDANDO_ARQUIVO"]

        resposta = cliente.post(ROTA_ENVIO, files=[_prontuario("31318")])

        # A conta não falta: ela já estava no sistema e agora fecha o par.
        assert resposta.json()["ultimo_envio"][0]["texto"] == "31318, conta e prontuário"
        assert _situacoes(banco, "31318") == ["NA_FILA"]

    def test_prontuario_sem_conta_deixa_a_conta_a_espera_e_a_conta_que_chega_ocupa_o_lugar(self):
        banco = _cenario()
        cliente = _cliente("faturista", banco)

        cliente.post(ROTA_ENVIO, files=[_prontuario("31320")])
        espera = banco.contas_do_atendimento("31320")
        assert [(c["situacao"], c.get("arquivo_id")) for c in espera] == [("AGUARDANDO_ARQUIVO", None)]

        resposta = cliente.post(ROTA_ENVIO, files=[_conta("31320", "48020")])

        assert resposta.json()["ultimo_envio"][0]["texto"] == "31320, conta e prontuário"
        contas = banco.contas_do_atendimento("31320")
        assert [(c["numero_conta"], c["situacao"]) for c in contas] == [("48020", "NA_FILA")]

    def test_o_pronto_socorro_no_mesmo_arquivo_nao_muda_o_atendimento_do_prontuario(self):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48001"), _prontuario("31302", pronto_socorro="31190")]
        )

        assert [linha["texto"] for linha in resposta.json()["ultimo_envio"]] == ["31302, conta e prontuário"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Os limites do envio
# ═══════════════════════════════════════════════════════════════════════════


class TestLimites:
    def test_o_11o_atendimento_e_recusado_com_mensagem_e_os_10_primeiros_entram(self):
        banco = _cenario()
        contas = [_conta(str(31301 + i), str(48001 + i)) for i in range(11)]

        resposta = _cliente("faturista", banco).post(ROTA_ENVIO, files=contas)

        corpo = resposta.json()
        assert len(corpo["ultimo_envio"]) == 10
        assert corpo["recusas"] == [
            {
                "arquivo": "conta-48011.pdf",
                "numero_atendimento": "31311",
                "motivo": "O envio já tem 10 atendimentos, o limite. Mande o atendimento 31311 num próximo envio.",
            }
        ]
        assert len(banco.tabelas["cm_conta"]) == 10

    def test_o_limite_de_atendimentos_vale_para_o_envio_inteiro_e_nao_para_o_lote(self):
        banco = _cenario()
        cliente = _cliente("faturista", banco)
        primeiro = cliente.post(ROTA_ENVIO, files=[_conta(str(31301 + i), str(48001 + i)) for i in range(10)])
        envio_id = primeiro.json()["envio_id"]

        resposta = cliente.post(
            ROTA_ENVIO,
            data={"envio_id": envio_id},
            files=[_prontuario("31301"), _conta("31311", "48011")],
        )

        corpo = resposta.json()
        assert corpo["envio_id"] == envio_id
        assert [r["numero_atendimento"] for r in corpo["recusas"]] == ["31311"]
        assert corpo["ultimo_envio"][0]["texto"] == "31301, conta e prontuário"
        assert len(corpo["ultimo_envio"]) == 10

    def test_o_31o_arquivo_e_recusado_com_mensagem(self):
        banco = _cenario()
        parciais = [_conta("31302", str(48001 + i)) for i in range(31)]

        resposta = _cliente("faturista", banco).post(ROTA_ENVIO, files=parciais)

        corpo = resposta.json()
        assert corpo["recusas"] == [
            {
                "arquivo": "conta-48031.pdf",
                "numero_atendimento": None,
                "motivo": "O envio já tem 30 arquivos, o limite. Mande este num próximo envio.",
            }
        ]
        assert corpo["ultimo_envio"][0]["texto"] == "31302, 30 parciais, falta o prontuário"
        assert len(banco.tabelas["cm_arquivo"]) == 30

    def test_o_lote_de_outra_pessoa_nao_entra_no_envio_dela(self):
        banco = _cenario()
        envio_id = _cliente("faturista", banco).post(ROTA_ENVIO, files=[_conta("31302", "48001")]).json()["envio_id"]

        resposta = _cliente("outra_faturista", banco).post(
            ROTA_ENVIO, data={"envio_id": envio_id}, files=[_prontuario("31302")]
        )

        assert resposta.status_code == 404
        assert len(banco.tabelas["cm_arquivo"]) == 1

    def test_arquivo_de_101_mb_e_recusado_pela_rota_com_o_teto_do_corpo_de_sempre(self):
        """O app de verdade tem o teto de 100 MiB no corpo, que não muda. O arquivo
        de 101 MB (como o computador mostra) passa por ele e é a rota que recusa,
        com a frase dela, e não o 413 genérico do teto."""
        from app.middleware.limite_corpo import LIMITE_CORPO_BYTES, LimiteDeCorpoMiddleware

        assert LIMITE_CORPO_BYTES == 100 * 1024 * 1024
        banco = _cenario()
        cliente = _cliente("faturista", banco)
        cliente.app.add_middleware(LimiteDeCorpoMiddleware)
        grande = _texto_da_conta("31302", "48001", "01/10/2026", "05/10/2026").encode("utf-8")
        grande += b" " * (101 * 1000 * 1000 - len(grande))

        resposta = cliente.post(
            ROTA_ENVIO,
            files=[("arquivos", ("conta-grande.pdf", grande, "application/pdf")), _conta("31310", "48010")],
        )

        assert resposta.status_code == 200, resposta.text[:200]
        corpo = resposta.json()
        assert corpo["recusas"] == [
            {
                "arquivo": "conta-grande.pdf",
                "numero_atendimento": None,
                "motivo": "O arquivo passa de 100 MB, o limite por arquivo.",
            }
        ]
        assert [linha["texto"] for linha in corpo["ultimo_envio"]] == ["31310, falta o prontuário"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Reprocesso
# ═══════════════════════════════════════════════════════════════════════════


class TestReprocesso:
    def test_mesmo_atendimento_e_mesma_conta_de_novo_volta_para_a_fila_sem_duplicar(self):
        banco = _com_prontuario_no_sistema(apagar_em=_daqui_a(3))
        banco.tabelas["cm_conta"][0].update(
            situacao="ERRO", erro_motivo="Não consegui ler a conta inteira", tentativas=3, processando_desde="x"
        )

        resposta = _cliente("faturista", banco).post(ROTA_ENVIO, files=[_conta("31302", "48001")])

        assert resposta.json()["ultimo_envio"][0]["texto"] == "31302, conta e prontuário"
        contas = banco.contas_do_atendimento("31302")
        assert len(contas) == 1
        conta = contas[0]
        assert conta["id"] == "parcial-1"
        assert (conta["situacao"], conta["erro_motivo"], conta["tentativas"], conta["processando_desde"]) == (
            "NA_FILA",
            None,
            0,
            None,
        )
        novo_arquivo = next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == "CONTA")
        assert conta["arquivo_id"] == novo_arquivo["id"]
        assert conta["ordem_fila"] > 1

    def test_a_mesma_conta_duas_vezes_no_mesmo_envio_conta_uma_so(self):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[_conta("31302", "48001"), _conta("31302", "48001"), _prontuario("31302")]
        )

        assert resposta.json()["ultimo_envio"][0]["texto"] == "31302, conta e prontuário"
        assert _situacoes(banco, "31302") == ["NA_FILA"]


# ═══════════════════════════════════════════════════════════════════════════
# 7. O arquivo no bucket
# ═══════════════════════════════════════════════════════════════════════════


class TestArquivoNoBucket:
    def test_o_pdf_vai_para_o_bucket_privado_com_hash_e_apagar_em_7_dias_depois_do_envio(self):
        import hashlib

        banco = _cenario()
        conta, prontuario = _conta("31302", "48001"), _prontuario("31302")

        _cliente("faturista", banco).post(ROTA_ENVIO, files=[conta, prontuario])

        envio = banco.tabelas["cm_envio"][0]
        assert envio["usuario_id"] == "F1"
        enviados = {"CONTA": conta[1][1], "PRONTUARIO": prontuario[1][1]}
        for arquivo in banco.tabelas["cm_arquivo"]:
            conteudo = enviados[arquivo["tipo"]]
            assert banco.bucket[("contas-medicas", arquivo["chave_bucket"])] == conteudo
            assert arquivo["hash"] == hashlib.sha256(conteudo).hexdigest()
            prazo = datetime.fromisoformat(arquivo["apagar_em"]) - datetime.fromisoformat(envio["criado_em"])
            assert prazo == timedelta(days=7)
            assert arquivo["envio_id"] == envio["id"]
            assert "31302" not in arquivo["chave_bucket"]

    def test_falha_no_bucket_recusa_o_arquivo_e_nao_deixa_linha_sem_pdf(self, monkeypatch):
        banco = _cenario()

        def recusar(*_a, **_kw):
            raise RuntimeError("storage fora do ar")

        monkeypatch.setattr(_Bucket, "upload", recusar)

        resposta = _cliente("faturista", banco).post(ROTA_ENVIO, files=[_conta("31302", "48001")])

        assert resposta.json()["recusas"][0]["motivo"] == "Não consegui guardar o arquivo. Envie de novo."
        assert banco.tabelas["cm_arquivo"] == []
        assert banco.tabelas["cm_conta"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 8. A fila
# ═══════════════════════════════════════════════════════════════════════════


def _c(id_: str, situacao: str, ordem: int, faturista="F1", **campos) -> dict:
    base = {
        "id": id_,
        "atendimento_id": f"at-{id_}",
        "arquivo_id": f"arq-{id_}",
        "numero_conta": f"conta-{id_}",
        "periodo_inicio": "2026-10-01",
        "periodo_fim": "2026-10-05",
        "situacao": situacao,
        "faturista_id": faturista,
        "ordem_fila": ordem,
        "valor_apontado": None,
        "nota_entrada": None,
        "nota_bruta": None,
        "erro_motivo": None,
    }
    return {**base, **campos}


def _l(conta_id: str, acao: str, estado: str) -> dict:
    return {"id": f"{conta_id}-{acao}-{estado}-{uuid.uuid4()}", "conta_id": conta_id, "acao": acao, "estado": estado}


def _fila_semeada() -> _Banco:
    """Contas em todas as situações, semeadas fora de ordem. O valor apontado
    cresce ao contrário da ordem de envio: ordenar por valor daria outra lista."""
    contas = [
        _c("a-fazer", "A_FAZER", 30, valor_apontado=10.0, nota_bruta=90, nota_entrada=90),
        _c("na-fila", "NA_FILA", 10, valor_apontado=999.0),
        _c("erro", "ERRO", 20, erro_motivo="Não consegui ler a conta inteira"),
        _c("da-outra", "AGUARDANDO_ARQUIVO", 15, faturista="F2"),
        _c("concluida", "CONCLUIDA_COM_PENDENCIA", 5, nota_entrada=80),
        _c("em-correcao", "EM_CORRECAO", 25),
        _c("falta-conta", "AGUARDANDO_ARQUIVO", 40, arquivo_id=None, numero_conta=None),
        _c("processando", "PROCESSANDO", 35),
        _c("falta-prontuario", "AGUARDANDO_ARQUIVO", 12),
    ]
    atendimentos = [{"id": c["atendimento_id"], "numero_atendimento": f"31{n:03d}"} for n, c in enumerate(contas)]
    linhas = [
        _l("a-fazer", "INCLUIR", "FEITO"),
        _l("a-fazer", "RETIRAR", "ABERTA"),
        _l("a-fazer", "CORRIGIR_PRECO", "ABERTA"),
        _l("a-fazer", "VALIDAR", "EM_VALIDACAO"),
        _l("concluida", "INCLUIR", "FEITO"),
        _l("concluida", "RETIRAR", "BLOQUEADO"),
    ]
    return _cenario(cm_conta=contas, cm_atendimento=atendimentos, cm_guia_linha=linhas)


class TestFila:
    def test_a_faturista_ve_so_as_proprias_na_ordem_de_envio_e_as_concluidas_a_parte(self):
        resposta = _cliente("faturista", _fila_semeada()).get(ROTA_FILA)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [c["id"] for c in corpo["fila"]] == [
            "na-fila",
            "falta-prontuario",
            "erro",
            "em-correcao",
            "a-fazer",
            "processando",
            "falta-conta",
        ]
        assert [c["id"] for c in corpo["concluidas"]] == ["concluida"]

    def test_painel_completo_ve_as_contas_de_todas(self):
        corpo = _cliente("coordenadora", _fila_semeada()).get(ROTA_FILA).json()

        assert [c["id"] for c in corpo["fila"]][:3] == ["na-fila", "falta-prontuario", "da-outra"]
        assert len(corpo["fila"]) == 8

    def test_a_outra_faturista_nao_ve_as_contas_da_primeira(self):
        corpo = _cliente("outra_faturista", _fila_semeada()).get(ROTA_FILA).json()

        assert [c["id"] for c in corpo["fila"]] == ["da-outra"]
        assert corpo["concluidas"] == []

    def test_cada_conta_traz_o_que_a_situacao_dela_pede(self):
        corpo = _cliente("faturista", _fila_semeada()).get(ROTA_FILA).json()
        por_id = {c["id"]: c for c in corpo["fila"] + corpo["concluidas"]}

        a_fazer = por_id["a-fazer"]
        assert (a_fazer["situacao"], a_fazer["nota_entrada"], a_fazer["valor_apontado"]) == ("A_FAZER", 90, 10.0)
        assert (a_fazer["itens_feitos"], a_fazer["itens_total"]) == (1, 3)
        assert a_fazer["numero_atendimento"] == "31000"
        assert a_fazer["numero_conta"] == "conta-a-fazer"
        assert por_id["erro"]["erro_motivo"] == "Não consegui ler a conta inteira"
        assert por_id["falta-prontuario"]["falta"] == "prontuario"
        assert por_id["falta-conta"]["falta"] == "conta"
        assert por_id["na-fila"]["falta"] is None
        assert por_id["concluida"]["pendencias"] == 1

    @pytest.mark.parametrize("quem", ["credenciamento", "sem_eixo"])
    def test_sem_a_permissao_de_enviar_e_corrigir_contas_recebe_403(self, quem):
        assert _cliente(quem, _fila_semeada()).get(ROTA_FILA).status_code == 403


class TestAsRotasEstaoNoApp:
    def test_o_app_de_verdade_registra_o_envio_e_a_fila(self):
        """A fonte é o schema OpenAPI, e não `app.routes` (FastAPI 0.141, issues #542 e #546)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "post" in caminhos[ROTA_ENVIO]
        assert "get" in caminhos[ROTA_FILA]


# ═══════════════════════════════════════════════════════════════════════════
# 10. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestKitDeConhecimento:
    """A sanidade geral (piso, seções, sem rota nem tabela) mora em
    `test_kit_conhecimento.py`; aqui, o que o texto tem que dizer do envio."""

    def test_diz_como_enviar_e_o_que_o_ultimo_envio_mostra(self):
        secao = KIT.read_text(encoding="utf-8").split("## O envio e a fila", 1)[1].split("\n## ", 1)[0]

        for trecho in (
            "arrasta",
            "Selecionar arquivos",
            "Último envio",
            "conta e prontuário",
            "2 parciais e prontuário",
            "falta o prontuário",
            "ainda não configurado",
            "10 atendimentos",
            "30 arquivos",
            "100 MB",
            "Enviar de novo",
            "Concluídas",
        ):
            assert trecho in secao, trecho


# ═══════════════════════════════════════════════════════════════════════════
# 11. Tipografia
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]

# Os arquivos desta fatia. O de `services/contas_medicas/envio.py` não tem
# "contas_medicas" no nome, e o glob da fundação não o alcança.
ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/envio.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_envio.py",
    RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md",
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/page.tsx",
    RAIZ_DO_APP / "frontend/src/lib/contas-medicas/envio.ts",
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
