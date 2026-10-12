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
                        "id": f"{self._nome}-{len(tabela) + len(gravadas) + 1}",
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
