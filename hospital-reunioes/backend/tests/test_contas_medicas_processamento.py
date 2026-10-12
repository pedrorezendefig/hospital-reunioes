"""Processamento da fila de Contas médicas, o pipeline e o aviso no sino
(issue #1124, PRD #1113, ADR 0070).

A conta entra na fila pelo envio (#1123) e sai dela pelo job do APScheduler:
claim atômico de uma conta `NA_FILA`, o pipeline inteiro (texto dos PDFs,
leitura da conta e do prontuário, conferências, Guia) e, no fim do envio, a
notificação no sino. Tudo pelos caminhos de verdade: a rota de envio, o job e a
rota do Guia.

Os PDFs são sintéticos. O extrator (`pdftotext` num processo isolado) é
trocado por um dublê que devolve o texto de cada página e conta as chamadas:
o "PDF" do teste é o próprio texto, com as páginas separadas por form feed.

O dublê do banco guarda as restrições da migration 116 que o processamento
pode ferir (a situação da conta, a ação e o estado da linha do Guia, o trecho
de evidência de até 300 caracteres e o tipo da notificação) e é atômico por
operação, como o Postgres é por linha: é o que dá sentido ao teste do claim
concorrente.
"""

from __future__ import annotations

import os
import re
import sys
import threading
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
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.services.contas_medicas import envio as envio_service  # noqa: E402
from app.services.contas_medicas import processamento  # noqa: E402
from app.services.contas_medicas_extrator import Pagina  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

AGORA = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════


def _lista_do_check(sql: str, tabela_e_coluna: str) -> set[str]:
    bloco = re.search(tabela_e_coluna + r".*?CHECK \((.*?)\)\)", sql, flags=re.DOTALL)
    assert bloco, f"a migration 116 nao tem o CHECK de {tabela_e_coluna}"
    return set(re.findall(r"'(\w+)'", bloco.group(1)))


_SQL = MIGRATION.read_text(encoding="utf-8")
SITUACOES_DA_CONTA = _lista_do_check(_SQL, r"situacao\s+TEXT NOT NULL DEFAULT 'AGUARDANDO_ARQUIVO'")
ACOES_DA_LINHA = _lista_do_check(_SQL, r"\bacao\s+TEXT NOT NULL")
ESTADOS_DA_LINHA = _lista_do_check(_SQL, r"\bestado\s+TEXT NOT NULL DEFAULT 'ABERTA'")
TIPOS_DE_NOTIFICACAO = _lista_do_check(_SQL, r"ADD CONSTRAINT notificacoes_tipo_check")


def test_o_duble_le_os_checks_da_migration():
    """Piso do detector: regex que parou de casar devolveria conjunto vazio."""
    assert {"NA_FILA", "PROCESSANDO", "A_FAZER", "ERRO"} <= SITUACOES_DA_CONTA
    assert {"INCLUIR", "VALIDAR"} <= ACOES_DA_LINHA
    assert {"ABERTA", "FEITO", "NAO_PROCEDE"} <= ESTADOS_DA_LINHA
    assert {"CONTAS_MEDICAS", "MENCAO"} <= TIPOS_DE_NOTIFICACAO


def _violacao(nome: str, linha: dict) -> str | None:
    if nome == "cm_conta" and "situacao" in linha and linha["situacao"] not in SITUACOES_DA_CONTA:
        return "cm_conta_situacao_check"
    if nome == "cm_guia_linha":
        if linha.get("acao") not in ACOES_DA_LINHA:
            return "cm_guia_linha_acao_check"
        if linha.get("estado", "ABERTA") not in ESTADOS_DA_LINHA:
            return "cm_guia_linha_estado_check"
        if len(linha.get("evidencia_trecho") or "") > 300:
            return "cm_guia_linha_evidencia_trecho_check"
    if nome == "notificacoes" and linha.get("tipo") not in TIPOS_DE_NOTIFICACAO:
        return "notificacoes_tipo_check"
    return None


def _contem(valor: Any, parte: Any) -> bool:
    """O `@>` do JSONB, o bastante para `{"codigos_tuss": [codigo]}`."""
    if isinstance(parte, dict):
        return isinstance(valor, dict) and all(_contem(valor.get(k), v) for k, v in parte.items())
    if isinstance(parte, list):
        return isinstance(valor, list) and all(any(_contem(v, p) for v in valor) for p in parte)
    return valor == parte


class _Consulta:
    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._ordem: list[tuple[str, bool]] = []
        self._limite: int | None = None
        self._update: dict | None = None
        self._insert: dict | list | None = None
        self._delete = False

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def neq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and linha.get(coluna) != valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def _compara(self, coluna, valor, teste):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and teste(str(linha.get(coluna)), str(valor)))
        return self

    def gt(self, coluna, valor):
        return self._compara(coluna, valor, lambda a, b: a > b)

    def gte(self, coluna, valor):
        return self._compara(coluna, valor, lambda a, b: a >= b)

    def lt(self, coluna, valor):
        return self._compara(coluna, valor, lambda a, b: a < b)

    def lte(self, coluna, valor):
        return self._compara(coluna, valor, lambda a, b: a <= b)

    def contains(self, coluna, parte):
        self._filtros.append(lambda linha: _contem(linha.get(coluna), parte))
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

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        with self._banco.trava:
            resposta = self._executar()
        leitura = self._insert is None and self._update is None and not self._delete
        if leitura and self._nome == "cm_conta" and self._banco.ao_ler_contas:
            self._banco.ao_ler_contas()
        return resposta

    def _executar(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            novas = self._insert if isinstance(self._insert, list) else [self._insert]
            gravadas = []
            for nova in novas:
                if violacao := _violacao(self._nome, nova):
                    raise APIError({"message": violacao, "code": "23514"})
                self._banco.relogio += 1
                gravadas.append(
                    {"id": str(uuid.uuid4()), "criado_em": f"2026-10-12T10:00:00.{self._banco.relogio:06d}+00:00", **nova}
                )
            tabela.extend(gravadas)
            return SimpleNamespace(data=[dict(g) for g in gravadas])
        casam = [linha for linha in tabela if all(f(linha) for f in self._filtros)]
        if self._delete:
            self._banco.tabelas[self._nome] = [linha for linha in tabela if linha not in casam]
            return SimpleNamespace(data=[dict(linha) for linha in casam])
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

    def download(self, caminho):
        if (self._nome, caminho) not in self._banco.bucket:
            raise RuntimeError("Object not found")
        return self._banco.bucket[(self._nome, caminho)]


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas
        self.bucket: dict[tuple[str, str], bytes] = {}
        self.relogio = 0
        self.trava = threading.RLock()
        # Gancho do teste do claim concorrente: roda fora da trava, depois de
        # cada leitura de `cm_conta`.
        self.ao_ler_contas = None
        self.storage = SimpleNamespace(from_=lambda nome: _Bucket(self, nome))

    def table(self, nome: str):
        return _Consulta(self, nome)

    def conta(self, conta_id: str) -> dict:
        return next(c for c in self.tabelas["cm_conta"] if c["id"] == conta_id)


def _conta_na_fila(id_: str, ordem: int, situacao: str = "NA_FILA", **campos) -> dict:
    return {
        "id": id_,
        "atendimento_id": f"at-{id_}",
        "arquivo_id": f"arq-{id_}",
        "situacao": situacao,
        "tentativas": 0,
        "processando_desde": None,
        "faturista_id": "F1",
        "ordem_fila": ordem,
        **campos,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 1. O claim atômico
# ═══════════════════════════════════════════════════════════════════════════


class TestClaim:
    def test_duas_chamadas_concorrentes_pegam_contas_diferentes(self):
        """As duas leem a fila antes de qualquer uma escrever: a mesma primeira
        conta para as duas. Só o UPDATE condicionado à situação separa."""
        banco = _Banco({"cm_conta": [_conta_na_fila("c1", 1), _conta_na_fila("c2", 2)]})
        as_duas_leram = threading.Barrier(2, timeout=5)
        leituras = threading.local()

        def esperar_a_outra_na_primeira_leitura():
            if not getattr(leituras, "feita", False):
                leituras.feita = True
                as_duas_leram.wait()

        banco.ao_ler_contas = esperar_a_outra_na_primeira_leitura
        pegas: list = []

        def pegar():
            pegas.append(processamento.pegar_da_fila(banco, AGORA))

        threads = [threading.Thread(target=pegar) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert sorted(p["id"] for p in pegas) == ["c1", "c2"]
        assert {c["situacao"] for c in banco.tabelas["cm_conta"]} == {"PROCESSANDO"}
        assert {c["processando_desde"] for c in banco.tabelas["cm_conta"]} == {AGORA.isoformat()}

    def test_sem_conta_na_fila_nenhuma_chamada_pega(self):
        outras = [
            _conta_na_fila("c1", 1, situacao="AGUARDANDO_ARQUIVO"),
            _conta_na_fila("c2", 2, situacao="A_FAZER"),
            _conta_na_fila("c3", 3, situacao="PROCESSANDO", processando_desde=AGORA.isoformat()),
        ]
        banco = _Banco({"cm_conta": [dict(c) for c in outras]})

        assert processamento.pegar_da_fila(banco, AGORA) is None
        assert processamento.pegar_da_fila(banco, AGORA) is None
        assert banco.tabelas["cm_conta"] == outras

    def test_pega_na_ordem_de_envio(self):
        banco = _Banco({"cm_conta": [_conta_na_fila("c2", 20), _conta_na_fila("c1", 10)]})

        assert processamento.pegar_da_fila(banco, AGORA)["id"] == "c1"
