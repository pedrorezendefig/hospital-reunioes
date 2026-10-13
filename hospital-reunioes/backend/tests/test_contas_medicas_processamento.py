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

import dataclasses
import json
import logging
import os
import re
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_envio as envio_router  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.services.contas_medicas import envio as envio_service  # noqa: E402
from app.services.contas_medicas import ia, processamento  # noqa: E402
from app.services.contas_medicas.conferencia import ProntuarioLido, conferir  # noqa: E402
from app.services.contas_medicas.conteudo import ler_conteudo  # noqa: E402
from app.services.contas_medicas.memoria import MemoriaLida, RegraLida, parametros_lidos  # noqa: E402
from app.services.contas_medicas.prontuario import ler_prontuario  # noqa: E402
from app.services.contas_medicas.tabelas import NAO_CONFERIDO, Pacote  # noqa: E402
from app.services.contas_medicas_conta import ler_conta  # noqa: E402
from app.services.contas_medicas_extrator import ErroLeitura, Pagina, Palavra  # noqa: E402

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


# Os DEFAULT da 116 que o processamento deixa o banco preencher.
PADROES_DA_MIGRATION = {
    "cm_conta": {"tentativas": 0, "parecer_parcial": False},
    "cm_guia_linha": {"estado": "ABERTA", "origem": "CODIGO"},
    "notificacoes": {"lida": False},
}


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
        self._inicio = 0
        self._update: dict | None = None
        self._insert: dict | list | None = None
        self._upsert: tuple[list, list[str]] | None = None
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

    def range(self, inicio, fim):
        self._inicio, self._limite = inicio, fim - inicio + 1
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

    def upsert(self, linhas, on_conflict: str):
        self._upsert = (list(linhas), on_conflict.split(","))
        return self

    def execute(self):
        if self._insert is not None and self._nome == "cm_eventos" and self._banco.antes_de_gravar_eventos:
            self._banco.antes_de_gravar_eventos()
        with self._banco.trava:
            resposta = self._executar()
        leitura = self._insert is None and self._update is None and self._upsert is None and not self._delete
        if leitura and self._nome == "cm_conta" and self._banco.ao_ler_contas:
            self._banco.ao_ler_contas()
        return resposta

    def _executar(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._upsert is not None:
            novas, chave = self._upsert
            for nova in novas:
                velha = next((v for v in tabela if all(v.get(c) == nova[c] for c in chave)), None)
                if velha is None:
                    tabela.append(dict(nova))
                else:
                    velha.update(nova)
            return SimpleNamespace(data=[dict(nova) for nova in novas])
        if self._insert is not None:
            novas = self._insert if isinstance(self._insert, list) else [self._insert]
            gravadas = []
            for nova in novas:
                if violacao := _violacao(self._nome, nova):
                    raise APIError({"message": violacao, "code": "23514"})
                # O índice único do termo (migration 116).
                if self._nome == "cm_item_dicionario" and any(t["termo"] == nova["termo"] for t in tabela):
                    raise APIError({"message": "idx_cm_item_dicionario_termo", "code": "23505"})
                self._banco.relogio += 1
                gravadas.append(
                    {
                        "id": str(uuid.uuid4()),
                        "criado_em": f"2026-10-12T10:00:00.{self._banco.relogio:06d}+00:00",
                        **PADROES_DA_MIGRATION.get(self._nome, {}),
                        **nova,
                    }
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
        casam = casam[self._inicio :]
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
        # Gancho do teste das duas parciais em paralelo: roda fora da trava,
        # antes de cada gravação em `cm_eventos`.
        self.antes_de_gravar_eventos = None
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


# ═══════════════════════════════════════════════════════════════════════════
# 2. A conta presa em PROCESSANDO
# ═══════════════════════════════════════════════════════════════════════════


def _ha(minutos: int) -> str:
    return (AGORA - timedelta(minutes=minutos)).isoformat()


def _presa(minutos: int, tentativas: int) -> dict:
    return _conta_na_fila("c1", 1, situacao="PROCESSANDO", processando_desde=_ha(minutos), tentativas=tentativas)


class TestContaPresa:
    def test_processando_ha_16_minutos_volta_para_a_fila_e_o_claim_seguinte_e_a_tentativa_2(self):
        banco = _Banco({"cm_conta": [_presa(16, tentativas=1)]})

        processamento.devolver_presas(banco, AGORA)

        conta = banco.conta("c1")
        assert (conta["situacao"], conta["processando_desde"], conta["tentativas"]) == ("NA_FILA", None, 1)
        assert processamento.pegar_da_fila(banco, AGORA)["tentativas"] == 2

    def test_processando_ha_14_minutos_segue_processando(self):
        banco = _Banco({"cm_conta": [_presa(14, tentativas=1)]})

        processamento.devolver_presas(banco, AGORA)

        assert banco.conta("c1") == _presa(14, tentativas=1)

    def test_na_terceira_tentativa_presa_vira_erro_com_a_mensagem(self):
        banco = _Banco({"cm_conta": [_presa(16, tentativas=3)]})

        processamento.devolver_presas(banco, AGORA)

        conta = banco.conta("c1")
        assert (conta["situacao"], conta["erro_motivo"], conta["processando_desde"]) == (
            "ERRO",
            "A análise não terminou em três tentativas. Envie de novo.",
            None,
        )
        assert processamento.pegar_da_fila(banco, AGORA) is None


# ═══════════════════════════════════════════════════════════════════════════
# O par sintético: a conta, o prontuário, a memória e as tabelas
# ═══════════════════════════════════════════════════════════════════════════

ATENDIMENTO = "31245"
FIXTURES = Path(__file__).parent / "fixtures" / "contas_medicas"
QUEBRA = "<<<QUEBRA DE PÁGINA>>>"

# Um trecho que só existe no prontuário (a capa e a descrição cirúrgica): não
# pode aparecer em linha nenhuma de log.
TRECHO_DO_PRONTUARIO = "ANTÔNIA MELO FARIAS"


def _br(valor: Decimal) -> str:
    return f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


# (grupo da conta, dia de outubro, código, descrição, unidade, quantidade, unitário)
ITENS_DA_CONTA = [
    ("DIARIAS", 3, "60001038", "DIARIA DE UTI ADULTO", "UN", "1", "1000.00"),
    ("DIARIAS", 4, "60001038", "DIARIA DE UTI ADULTO", "UN", "1", "1000.00"),
    ("DIARIAS", 5, "60001038", "DIARIA DE UTI ADULTO", "UN", "1", "1000.00"),
    ("MEDICAMENTOS", 3, "90030001", "CLEXANE 40MG/0,4ML SER PREENCH", "SER", "1", "45.00"),
    ("MEDICAMENTOS", 4, "90030001", "CLEXANE 40MG/0,4ML SER PREENCH", "SER", "1", "45.00"),
    ("MATERIAIS DESCARTAVEIS", 3, "70000001", "AGULHA HIPODERMICA 40X12", "UN", "10", "0.17"),
]


def _texto_da_conta(conta: str, inicio: int, fim: int, *, total_errado: bool = False, agulha: str = "0.17") -> str:
    """A "Fatura Individual" do MV com os itens do período (dias de outubro).
    `agulha` é o unitário lançado da agulha (a tabela diz 0,20)."""
    linhas = [
        "HOSPITAL FICTICIO DE TESTE                                                         Página 1 de 1",
        "                                   Fatura Individual",
        "",
        f"Atendimento: {ATENDIMENTO}          Conta: {conta}          Tipo: PARCIAL",
        "Internação: 02/10/2026 22:40",
        f"Período da   {inicio:02d}/10/2026 a {fim:02d}/10/2026          Acomodação: ENFERMARIA",
        "Procedimento: 31005497  COLECISTECTOMIA COM COLANGIOGRAFIA          CID: K80",
        "Plano: ALFA BASICO ENF",
        "Guia: 123456789",
        "",
    ]
    total = Decimal(0)
    grupo_atual = None
    for grupo, dia, codigo, descricao, unidade, quantidade, unitario in ITENS_DA_CONTA:
        if not inicio <= dia <= fim:
            continue
        if grupo != grupo_atual:
            linhas += [grupo, "51  CTI ADULTO", "    Grupo de Procedimento: 01 GERAL"]
            grupo_atual = grupo
        q, u = Decimal(quantidade), Decimal(agulha if codigo == "70000001" else unitario)
        total += q * u
        valores = f"{_br(q):>8}  {_br(u):>10}  {_br(q * u):>10}"
        linhas.append(f"{dia:02d}/10/2026  {codigo}  {descricao:<40}{unidade:<8}100,00%  {valores}")
    if total_errado:
        total += Decimal("10.00")
    linhas += ["", f"Total da Conta:                                                                  {_br(total)}", ""]
    return "\n".join(linhas)


def _fixture(nome: str) -> list[str]:
    return [p.strip("\n") for p in (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8").split(QUEBRA)]


CABECALHO_DA_PRESCRICAO = (
    "MEDICAMENTOS NORMAIS                       Dose Padrão     Duração   Frequência   SN   Apl   Datas/Horários"
)
CLEXANE = " 1 CLEXANE 40MG/0,4ML SER PREENCH          1 SERINGA                 24HS/24HS          SC    . 22"


def _prescricao(dia: int) -> str:
    return "\n".join(
        [
            "HOSPITAL SÃO MATHEUS                                                    Página: 1 / 1",
            f"Prescrição.: {778800 + dia}  Data: {dia:02d}/10/2026 10:15",
            f"Atendimento: {ATENDIMENTO}",
            "Unid. Int..: CTI ADULTO   Leito..: CTI-04   Cobertura: UTI ADULTO GERAL",
            "Internação.: 02/10/2026 22:40",
            "PRESCRIÇÃO MÉDICA",
            CABECALHO_DA_PRESCRICAO,
            CLEXANE,
        ]
    )


def _paginas_do_prontuario(fisioterapias: int = 0) -> list[str]:
    """Internação no CTI de 02/10 22:40 à alta em 06/10 15:20, com Clexane
    prescrito todo dia e a colecistectomia em 04/10. A capa lista três
    evoluções médicas que o arquivo não trouxe: o guia sai com parecer parcial.
    `fisioterapias`: quantas avaliações respiratórias iguais entram (#1132)."""
    (capa,) = _fixture("prontuario/capa")
    capa += "\nGrupo: EVOLUÇÃO MEDICA      Quantidade: 3"
    paginas = [
        capa,
        *_fixture("prontuario/admissao_unidade"),
        *(_prescricao(dia) for dia in (3, 4, 5, 6)),
        *_fixture("prontuario/fisio_resp") * fisioterapias,
        *_fixture("conteudo/descricao_cirurgica"),
        *_fixture("prontuario/resumo_alta"),
    ]
    return [
        f"{texto}\n\n          Impressão de Prontuário - Página {n} de {len(paginas)}"
        for n, texto in enumerate(paginas, start=1)
    ]


def _arquivo_do_envio(nome: str, texto: str):
    return ("arquivos", (nome, texto.encode("utf-8"), "application/pdf"))


def _conta(conta: str = "48811", inicio: int = 2, fim: int = 6, **kw):
    return _arquivo_do_envio(f"conta-{conta}.pdf", _texto_da_conta(conta, inicio, fim, **kw))


def _prontuario(fisioterapias: int = 0):
    return _arquivo_do_envio("prontuario.pdf", "\f".join(_paginas_do_prontuario(fisioterapias)))


REGRAS_DAS_CONFERENCIAS = {
    "preco": "ALFA-PRC-02",
    "diaria": "ALFA-DIA-01",
    "prescricao": "ALFA-PRI-07",
    "sem_registro": "ALFA-PRI-06",
    "procedimento_do_cabecalho": "ALFA-PRI-12",
    "pacote_pelo_tuss": "ALFA-PAC-03",
}

PARAMETROS = {
    "operadora": "ALFA",
    "colunas_de_preco": {"padrao": "COMUM"},
    "diaria": {"hora_vencimento": "10:00", "limite_madrugada": "05:00", "codigos": {"cti": "60001038"}},
    "regras_das_conferencias": REGRAS_DAS_CONFERENCIAS,
}

# A tabela de materiais e a de pacotes como a carga grava (#1120).
PRECO_DA_AGULHA = {"comum": 0.20, "carioca": 0.25}
PACOTE_DA_COLECISTECTOMIA = {"codigo": "98005497", "descricao": "PACOTE COLECISTECTOMIA", "valor": 4500.0}


def _matriz_da_migration() -> list[dict[str, Any]]:
    bloco = re.search(r"INSERT INTO cm_perfil_permissao\s*\([^)]*\)\s*VALUES(.*?);", _SQL, flags=re.DOTALL)
    assert bloco, "a migration 116 nao carrega a matriz"
    linhas = re.findall(r"\(\s*'(\w+)'\s*,\s*'(\w+)'\s*,\s*(true|false)\s*\)", bloco.group(1))
    return [{"perfil": p, "permissao": k, "ligada": v == "true"} for p, k, v in linhas]


def _pessoa(pid: str, perfil: str | None) -> dict[str, Any]:
    return {
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


PESSOAS = {"faturista": _pessoa("F1", "faturista"), "gestao": _pessoa("G1", "gestao_contas_medicas")}


def _regra(codigo: str) -> dict[str, Any]:
    return {
        "id": f"rg-{codigo}",
        "operadora_id": "op-alfa",
        "memoria_versao_id": "mv-alfa",
        "codigo": codigo,
        "secao": codigo.split("-")[1],
        "texto": f"Regra sintética {codigo}.",
        "tipo": "CONTRATUAL",
        "origem": "PRÁTICA",
        "status": "VIGENTE",
        "ativa": True,
    }


def _item_de_tabela(id_: str, tabela_id: str, codigo: str, descricao: str, precos: dict, extra: dict) -> dict:
    return {
        "id": id_,
        "tabela_id": tabela_id,
        "codigo": codigo,
        "codigo_alternativo": None,
        "descricao": descricao,
        "precos_json": precos,
        "extra_json": extra,
    }


def _cenario() -> _Banco:
    pacote = PACOTE_DA_COLECISTECTOMIA
    return _Banco(
        {
            "participantes": list(PESSOAS.values()),
            "cm_perfil_permissao": _matriz_da_migration(),
            "cm_operadora": [{"id": "op-alfa", "sigla": "ALFA", "nome": "Alfa Saúde", "situacao": "PARCIAL"}],
            "cm_operadora_plano": [
                {"id": "pl-1", "operadora_id": "op-alfa", "nome_mv": "ALFA BASICO", "coluna_preco": "COMUM"}
            ],
            "cm_memoria_versao": [
                {
                    "id": "mv-alfa",
                    "operadora_id": "op-alfa",
                    "versao": "1.0",
                    "parametros_json": PARAMETROS,
                    "vigente": True,
                }
            ],
            "cm_regra": [_regra(codigo) for codigo in sorted(REGRAS_DAS_CONFERENCIAS.values())],
            "cm_tabela_preco": [
                {"id": "tb-mat", "nome": "materiais.csv", "vigencia_inicio": "2026-01-01", "vigencia_fim": None},
                {"id": "tb-pac", "nome": "pacotes.csv", "vigencia_inicio": "2026-01-01", "vigencia_fim": None},
            ],
            "cm_tabela_preco_item": [
                _item_de_tabela("it-1", "tb-mat", "70000001", "AGULHA HIPODERMICA", PRECO_DA_AGULHA, {}),
                _item_de_tabela(
                    "it-2",
                    "tb-pac",
                    pacote["codigo"],
                    pacote["descricao"],
                    {"valor": pacote["valor"]},
                    {"codigos_tuss": ["31005497"], "permanencia": "2"},
                ),
            ],
            "cm_operadora_tabela": [
                {"operadora_id": "op-alfa", "categoria": categoria, "tabela_id": tabela, "regra_uso_json": {}}
                for categoria, tabela in (("MATERIAL", "tb-mat"), ("PACOTE", "tb-pac"))
            ],
            "cm_setor": [
                {"id": "st-1", "nome_mv": "CTI ADULTO", "acomodacao": "CTI"},
                {"id": "st-2", "nome_mv": "CENTRO CIRURGICO", "acomodacao": "CENTRO_CIRURGICO"},
            ],
            "cm_item_dicionario": [
                {"id": "dc-1", "termo": "Clexane", "codigo_conta": "90030001", "situacao": "CONFIRMADO"}
            ],
            "cm_envio": [],
            "cm_arquivo": [],
            "cm_atendimento": [],
            "cm_conta": [],
            "cm_conta_item": [],
            "cm_eventos": [],
            "cm_prescricao": [],
            "cm_prescricao_item": [],
            "cm_cirurgia": [],
            "cm_glicemia_dia": [],
            "cm_guia_linha": [],
            "notificacoes": [],
        }
    )


def _cliente(banco: _Banco, quem: str = "faturista") -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(envio_router.router, prefix="/api")
    app.include_router(guia_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


class _Extrator:
    """O `pdftotext` do teste: o "PDF" é o texto com as páginas separadas por
    form feed. Conta as chamadas por tipo de arquivo."""

    def __init__(self):
        self.chamadas: list[str] = []

    def __call__(self, pdf: bytes):
        texto = pdf.decode("utf-8")
        self.chamadas.append("PRONTUARIO" if "DECLARAÇÃO DE RECEBIMENTO" in texto else "CONTA")
        return [Pagina(numero=n, texto=t, sem_texto=not t.strip()) for n, t in enumerate(texto.split("\f"), start=1)]


def _palavras_de_largura_fixa(texto: str) -> list[Palavra]:
    """As palavras do texto com a posição de uma fonte de largura fixa: 5 pontos por
    caractere, 10 por linha. É o que o `extract_words` devolve de um PDF assim."""
    return [
        Palavra(m.start() * 5.0, m.end() * 5.0, n * 10.0, m.group())
        for n, linha in enumerate(texto.split("\n"))
        for m in re.finditer(r"\S+", linha)
    ]


class _ExtratorDePalavras:
    """O `extract_words` do teste: lê as palavras do "PDF" de texto e guarda as páginas pedidas."""

    def __init__(self):
        self.pedidas: list[list[int]] = []
        self.falha: ErroLeitura | None = None

    def __call__(self, pdf: bytes, paginas):
        pedidas = sorted(paginas)
        self.pedidas.append(pedidas)
        if self.falha is not None:
            return self.falha
        textos = pdf.decode("utf-8").split("\f")
        return {n: _palavras_de_largura_fixa(textos[n - 1]) for n in pedidas}


@pytest.fixture(autouse=True)
def extrator(monkeypatch) -> _Extrator:
    duble = _Extrator()
    monkeypatch.setattr(envio_service, "extrair_paginas", duble)
    monkeypatch.setattr(processamento, "extrair_paginas", duble)
    return duble


@pytest.fixture(autouse=True)
def extrator_de_palavras(monkeypatch) -> _ExtratorDePalavras:
    duble = _ExtratorDePalavras()
    monkeypatch.setattr(processamento, "extrair_palavras", duble)
    return duble


class _NaHora:
    """Executor que roda a análise na hora, na thread do teste."""

    def submit(self, funcao, *args, **kwargs):
        funcao(*args, **kwargs)


def _enviar(banco: _Banco, *arquivos) -> dict:
    resposta = _cliente(banco).post("/api/contas-medicas/envios", files=list(arquivos))
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["recusas"] == []
    return resposta.json()


def _rodar_o_job(banco: _Banco) -> int:
    return processamento.alimentar_fila(banco, AGORA, executor=_NaHora())


def _guia(banco: _Banco, conta_id: str) -> dict:
    resposta = _cliente(banco).get(f"/api/contas-medicas/contas/{conta_id}/guia")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


def _linhas_do_guia(guia: dict) -> list[dict]:
    return sorted((linha for grupo in guia["grupos"] for linha in grupo["linhas"]), key=lambda linha: linha["ordem"])


def _conferencia_esperada(conta: str = "48811", inicio: int = 2, fim: int = 6):
    """O que `conferir` devolve para o par sintético, com as buscas dadas à mão:
    é a fonte da verdade do guia que o pipeline grava."""
    conta_lida = ler_conta([_texto_da_conta(conta, inicio, fim)])
    textos = _paginas_do_prontuario()
    estrutura = ler_prontuario(textos, ATENDIMENTO)
    memoria = MemoriaLida(
        sigla="ALFA",
        nome="Alfa Saúde",
        versao="1.0",
        situacao="PARCIAL",
        parametros=parametros_lidos(PARAMETROS),
        regras=tuple(
            RegraLida(codigo, r["secao"], r["texto"], r["tipo"], r["origem"], r["status"], None)
            for codigo, r in ((c, _regra(c)) for c in sorted(REGRAS_DAS_CONFERENCIAS.values()))
        ),
    )

    def preco(categoria, codigo, _data, coluna):
        if (categoria, codigo) == ("MATERIAL", "70000001") and coluna:
            return Decimal(str(PRECO_DA_AGULHA[coluna.lower()]))
        return NAO_CONFERIDO

    def pacote(tuss, _data):
        if tuss != "31005497":
            return None
        p = PACOTE_DA_COLECISTECTOMIA
        return Pacote(p["codigo"], p["descricao"], 2, Decimal(str(p["valor"])))

    return estrutura, conferir(
        conta_lida,
        ProntuarioLido(estrutura, ler_conteudo(textos, estrutura), textos),
        memoria,
        preco,
        setores={"CTI ADULTO": "CTI", "CENTRO CIRURGICO": "CENTRO_CIRURGICO"},
        dicionario={"CLEXANE": {"90030001"}},
        pacote_do_tuss=pacote,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 3. O pipeline de ponta a ponta
# ═══════════════════════════════════════════════════════════════════════════


class TestPipeline:
    def test_a_conta_sai_a_fazer_com_o_guia_coerente_com_conferir(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())
        (conta,) = banco.tabelas["cm_conta"]
        assert conta["situacao"] == "NA_FILA"

        assert _rodar_o_job(banco) == 1

        gravada = banco.conta(conta["id"])
        assert gravada["situacao"] == "A_FAZER", gravada.get("erro_motivo")
        estrutura, esperada = _conferencia_esperada()
        assert esperada.linhas, "o par sintético tem que gerar linhas"
        assert gravada["nota_bruta"] == esperada.nota.nota
        assert gravada["valor_apontado"] == float(esperada.nota.apontado)
        assert gravada["valor_em_validacao"] == float(esperada.nota.em_validacao)
        assert gravada["total_lancado"] == 3091.70
        assert gravada["memoria_versao_id"] == "mv-alfa"
        assert gravada["pronta_em"] is not None
        assert len(banco.tabelas["cm_conta_item"]) == len(ITENS_DA_CONTA)
        (na_fila,) = _fila(banco)
        assert (na_fila["situacao"], na_fila["nota_entrada"], na_fila["valor_apontado"]) == (
            "A_FAZER",
            esperada.nota.nota,
            float(esperada.nota.apontado),
        )

        guia = _guia(banco, conta["id"])
        linhas = _linhas_do_guia(guia)
        campos = list(esperada.linhas[0])
        assert [{k: linha[k] for k in campos} for linha in linhas] == list(esperada.linhas)
        assert {linha["estado"] for linha in linhas} == {"ABERTA"}
        # A tabela de materiais do banco chegou à conferência: agulha a 0,17 com tabela 0,20.
        agulha = next(linha for linha in linhas if linha["codigo"] == "70000001")
        assert (agulha["acao"], agulha["preco_tabela"], agulha["valor_diferenca"]) == ("CORRIGIR_PRECO", 0.20, 0.30)
        # A busca de pacote pelo TUSS no banco chegou à conferência.
        pacote = next(linha for linha in linhas if linha["codigo"] == "98005497")
        assert (pacote["acao"], pacote["valor_diferenca"]) == ("INCLUIR", 4500.0)

        assert guia["cabecalho"]["situacao"] == "EM_CORRECAO"
        assert guia["cabecalho"]["parecer_parcial"] is True
        assert guia["cabecalho"]["faltantes"] == ["O arquivo não trouxe: evolução médica (3 na capa)."]
        assert list(estrutura.parecer_parcial) == guia["cabecalho"]["faltantes"]
        assert guia["cabecalho"]["paciente_rotulo"] == "Antônia F."


# O nome termina um espaço antes da coluna da dose: lido por linha, a dose entra no nome.
CLEXANE_ENCOSTADO = " 1 CLEXANE 40MG/0,4ML SER PREENCH SC 40 MG 1 SERINGA                 24HS/24HS          SC    . 22"


def _prontuario_com_o_nome_encostado():
    assert CLEXANE_ENCOSTADO.index("1 SERINGA") == CABECALHO_DA_PRESCRICAO.index("Dose Padrão")
    paginas = [p.replace(CLEXANE, CLEXANE_ENCOSTADO) for p in _paginas_do_prontuario()]
    return _arquivo_do_envio("prontuario.pdf", "\f".join(paginas))


class TestPrescricaoPorColuna:
    def test_as_paginas_da_prescricao_sao_lidas_pela_posicao_das_colunas(self, extrator_de_palavras):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario_com_o_nome_encostado())

        _rodar_o_job(banco)

        assert banco.tabelas["cm_conta"][0]["situacao"] == "A_FAZER"
        paginas_da_prescricao = [n for n, t in enumerate(_paginas_do_prontuario(), start=1) if "Prescrição.:" in t]
        assert extrator_de_palavras.pedidas == [paginas_da_prescricao]
        itens = banco.tabelas["cm_prescricao_item"]
        assert len(itens) == 4
        nome = "CLEXANE 40MG/0,4ML SER PREENCH SC 40 MG"
        assert {(i["nome"], i["colunas"]["dose"]) for i in itens} == {(nome, "1 SERINGA")}

    def test_sem_a_leitura_das_palavras_a_prescricao_e_lida_por_linha_e_a_conta_fica_pronta(self, extrator_de_palavras):
        extrator_de_palavras.falha = ErroLeitura("qualquer")
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        assert banco.tabelas["cm_conta"][0]["situacao"] == "A_FAZER"
        itens = banco.tabelas["cm_prescricao_item"]
        assert {(i["nome"], i["colunas"]["dose"]) for i in itens} == {("CLEXANE 40MG/0,4ML SER PREENCH", "1 SERINGA")}


# ═══════════════════════════════════════════════════════════════════════════
# 4. O prontuário é extraído uma vez por atendimento
# ═══════════════════════════════════════════════════════════════════════════


def _duas_parciais(banco: _Banco) -> list[dict]:
    _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6), _prontuario())
    return sorted(banco.tabelas["cm_conta"], key=lambda c: c["numero_conta"])


class TestProntuarioUmaVez:
    def test_a_segunda_parcial_nao_extrai_o_prontuario_de_novo(self, extrator):
        banco = _cenario()
        _duas_parciais(banco)
        assert extrator.chamadas.count("PRONTUARIO") == 1  # o envio, que lê o atendimento

        assert _rodar_o_job(banco) == 2

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert extrator.chamadas.count("PRONTUARIO") == 1
        assert extrator.chamadas.count("CONTA") == 2

    def test_sem_o_texto_guardado_a_primeira_parcial_extrai_e_a_segunda_le_o_que_ela_guardou(self, extrator):
        """O arquivo enviado antes desta fatia não tem o texto ao lado do PDF."""
        banco = _cenario()
        _duas_parciais(banco)
        banco.bucket = {chave: conteudo for chave, conteudo in banco.bucket.items() if chave[1].endswith(".pdf")}
        extrator.chamadas.clear()

        _rodar_o_job(banco)

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert extrator.chamadas.count("PRONTUARIO") == 1

    def test_a_estrutura_do_prontuario_e_gravada_uma_vez_com_a_data_ate_onde_ele_vai(self):
        banco = _cenario()
        _duas_parciais(banco)

        _rodar_o_job(banco)

        (eventos,) = banco.tabelas["cm_eventos"]
        # Alta em 06/10: é até onde o prontuário vai, e o aviso do envio (#1123) compara com isso.
        assert eventos["prontuario_ate"] == "2026-10-06"
        assert len(banco.tabelas["cm_prescricao"]) == 4
        (cirurgia,) = banco.tabelas["cm_cirurgia"]
        assert cirurgia["procedimentos_json"][0]["codigo"] == "31005497"
        (atendimento,) = banco.tabelas["cm_atendimento"]
        assert atendimento["paciente_rotulo"] == "Antônia F."

    def test_o_formulario_em_branco_e_aprendido_uma_vez_por_arquivo_e_a_resposta_fica_no_texto(self, monkeypatch):
        banco = _cenario()
        _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6), _prontuario(fisioterapias=3))
        lidos = []
        conferir_de_verdade = processamento.conferir

        def conferir_guardando_o_prontuario(lida, prontuario, *args, **kwargs):
            lidos.append(prontuario.estrutura)
            return conferir_de_verdade(lida, prontuario, *args, **kwargs)

        monkeypatch.setattr(processamento, "conferir", conferir_guardando_o_prontuario)

        assert _rodar_o_job(banco) == 2
        assert len(lidos) >= 2  # cada parcial confere antes e depois do Passo A

        aprendidas = banco.tabelas["cm_linha_formulario"]
        conduta = "Conduta: exercícios respiratórios, incentivador inspiratório, 2 séries de 10 repetições."
        assert ("FISIO_RESP", conduta) in {(r["familia"], r["linha"]) for r in aprendidas}
        # As duas parciais leem o mesmo arquivo: a contagem é de prontuários, soma uma vez.
        assert {r["contagem"] for r in aprendidas} == {1}
        # Repetida nas três fisioterapias de um paciente só, é evolução copiada: fica.
        for estrutura in lidos:
            fisioterapias = [d for d in estrutura.documentos if d.familia == "FISIO_RESP"]
            assert len(fisioterapias) == 3
            assert all(conduta in d.linhas for d in fisioterapias)

    def test_duas_parciais_em_vagas_paralelas_gravam_o_prontuario_uma_vez(self, openrouter):
        """As duas vagas pegam as parciais do mesmo atendimento juntas. A barreira
        segura a primeira vaga na porta da gravação até a outra chegar lá: sem
        trava por atendimento, as duas já leram `cm_eventos` vazio e apagaram,
        e as duas gravam. Com a trava, a segunda espera a primeira terminar, a
        barreira estoura e a primeira segue sozinha; a segunda acha o arquivo
        gravado e não grava de novo."""
        banco = _cenario()
        _duas_parciais(banco)
        as_duas_na_porta = threading.Barrier(2, timeout=1)

        def esperar_a_outra_vaga():
            try:
                as_duas_na_porta.wait()
            except threading.BrokenBarrierError:
                pass

        banco.antes_de_gravar_eventos = esperar_a_outra_vaga
        vagas = ThreadPoolExecutor(max_workers=2)
        try:
            assert processamento.alimentar_fila(banco, AGORA, executor=vagas) == 2
        finally:
            vagas.shutdown(wait=True)

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert [c["tentativas"] for c in banco.tabelas["cm_conta"]] == [1, 1]
        gravadas = {t: len(banco.tabelas.get(t, [])) for t in ("cm_eventos", "cm_prescricao", "cm_cirurgia")}
        assert gravadas == {"cm_eventos": 1, "cm_prescricao": 4, "cm_cirurgia": 1}
        # A trava do atendimento vale também para o Passo A: a segunda vaga
        # espera a primeira e acha a leitura da IA guardada.
        assert openrouter.formatos.count(PASSO_A) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 5. O reprocesso
# ═══════════════════════════════════════════════════════════════════════════


class TestReprocesso:
    def test_preserva_as_linhas_marcadas_e_substitui_as_abertas(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())
        _rodar_o_job(banco)
        (conta,) = banco.tabelas["cm_conta"]
        antes = _linhas_do_guia(_guia(banco, conta["id"]))
        pacote = next(linha for linha in antes if linha["codigo"] == "98005497")
        marcada = _cliente(banco).post(
            f"/api/contas-medicas/contas/{conta['id']}/guia/linhas/{pacote['id']}/marcacao", json={"estado": "FEITO"}
        )
        assert marcada.status_code == 200, marcada.text
        abertas_antes = {linha["id"] for linha in antes if linha["id"] != pacote["id"]}

        # A faturista corrigiu o preço da agulha no MV e mandou a mesma conta de novo.
        _enviar(banco, _conta(agulha="0.20"))
        assert banco.conta(conta["id"])["situacao"] == "NA_FILA"
        _rodar_o_job(banco)

        assert banco.conta(conta["id"])["situacao"] == "A_FAZER"
        depois = _linhas_do_guia(_guia(banco, conta["id"]))
        pacotes = [linha for linha in depois if linha["codigo"] == "98005497"]
        assert [(p["id"], p["estado"], p["marcado_por"]) for p in pacotes] == [(pacote["id"], "FEITO", "F1")]
        assert "70000001" not in {linha["codigo"] for linha in depois}
        abertas_depois = [linha for linha in depois if linha["estado"] == "ABERTA"]
        assert abertas_depois
        assert abertas_antes.isdisjoint(linha["id"] for linha in abertas_depois)
        assert len(depois) == len(antes) - 1


def _reanalisar(banco: _Banco, conta_id: str, quem: str = "gestao"):
    return _cliente(banco, quem).post(f"/api/contas-medicas/contas/{conta_id}/reanalisar")


def _conta_com_uma_linha_feita(banco: _Banco) -> tuple[dict, list[dict], dict]:
    """A conta analisada, aberta pela faturista, com a linha do pacote Feito."""
    _enviar(banco, _conta(), _prontuario())
    _rodar_o_job(banco)
    (conta,) = banco.tabelas["cm_conta"]
    antes = _linhas_do_guia(_guia(banco, conta["id"]))
    pacote = next(linha for linha in antes if linha["codigo"] == "98005497")
    marcada = _cliente(banco).post(
        f"/api/contas-medicas/contas/{conta['id']}/guia/linhas/{pacote['id']}/marcacao", json={"estado": "FEITO"}
    )
    assert marcada.status_code == 200, marcada.text
    return conta, antes, pacote


class TestReanalisar:
    """O botão "Reanalisar" (issue #1130): a gestão manda a conta A fazer ou Em
    correção para a análise de novo, depois de mudar regra ou tabela."""

    def test_reanalisar_reprocessa_e_preserva_as_linhas_marcadas(self):
        banco = _cenario()
        conta, antes, pacote = _conta_com_uma_linha_feita(banco)
        assert banco.conta(conta["id"])["situacao"] == "EM_CORRECAO"

        resposta = _reanalisar(banco, conta["id"])

        assert resposta.status_code == 200, resposta.text
        assert banco.conta(conta["id"])["situacao"] == "NA_FILA"
        _rodar_o_job(banco)
        assert banco.conta(conta["id"])["situacao"] == "A_FAZER"
        depois = _linhas_do_guia(_guia(banco, conta["id"]))
        pacotes = [linha for linha in depois if linha["codigo"] == "98005497"]
        assert [(p["id"], p["estado"], p["marcado_por"]) for p in pacotes] == [(pacote["id"], "FEITO", "F1")]
        abertas_antes = {linha["id"] for linha in antes if linha["id"] != pacote["id"]}
        abertas_depois = [linha for linha in depois if linha["estado"] == "ABERTA"]
        assert len(abertas_depois) == len(abertas_antes)
        assert abertas_antes.isdisjoint(linha["id"] for linha in abertas_depois)

    def test_o_guia_diz_quem_ve_o_botao(self):
        """A tela desenha o botão pelo que o Guia responde, sem perguntar de novo."""
        banco = _cenario()
        conta, _, _ = _conta_com_uma_linha_feita(banco)
        rota = f"/api/contas-medicas/contas/{conta['id']}/guia"

        assert _cliente(banco, "gestao").get(rota).json()["pode_reanalisar"] is True
        assert _cliente(banco, "faturista").get(rota).json()["pode_reanalisar"] is False
        banco.conta(conta["id"])["situacao"] = "CONCLUIDA"
        assert _cliente(banco, "gestao").get(rota).json()["pode_reanalisar"] is False

    def test_sem_a_permissao_de_regra_contratual_e_tabelas_recebe_403(self):
        banco = _cenario()
        conta, _, _ = _conta_com_uma_linha_feita(banco)

        resposta = _reanalisar(banco, conta["id"], quem="faturista")

        assert resposta.status_code == 403
        assert banco.conta(conta["id"])["situacao"] == "EM_CORRECAO"

    @pytest.mark.parametrize("situacao", ["NA_FILA", "PROCESSANDO", "ERRO", "CONCLUIDA"])
    def test_so_reanalisa_conta_a_fazer_ou_em_correcao(self, situacao):
        banco = _cenario()
        conta, _, _ = _conta_com_uma_linha_feita(banco)
        banco.conta(conta["id"])["situacao"] = situacao

        resposta = _reanalisar(banco, conta["id"])

        assert resposta.status_code == 409
        assert banco.conta(conta["id"])["situacao"] == situacao


# ═══════════════════════════════════════════════════════════════════════════
# 6. A leitura que não fecha
# ═══════════════════════════════════════════════════════════════════════════


def _fila(banco: _Banco) -> list[dict]:
    resposta = _cliente(banco).get("/api/contas-medicas/fila")
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["fila"]


def _trocar_o_pdf(banco: _Banco, tipo: str, texto: str) -> None:
    """O PDF do tipo pedido passa a ser `texto`, sem o texto guardado ao lado."""
    arquivo = next(a for a in banco.tabelas["cm_arquivo"] if a["tipo"] == tipo)
    banco.bucket.pop(("contas-medicas", arquivo["chave_bucket"] + ".txt"))
    banco.bucket[("contas-medicas", arquivo["chave_bucket"])] = texto.encode("utf-8")


class TestLeituraQueNaoFecha:
    def test_conta_que_nao_fecha_a_soma_sai_erro_sem_nova_tentativa(self):
        banco = _cenario()
        _enviar(banco, _conta(total_errado=True), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert (conta["situacao"], conta["erro_motivo"], conta["tentativas"]) == (
            "ERRO",
            "Não consegui ler a conta inteira",
            1,
        )
        assert [(c["situacao"], c["erro_motivo"]) for c in _fila(banco)] == [
            ("ERRO", "Não consegui ler a conta inteira")
        ]
        assert banco.tabelas["cm_guia_linha"] == []

    def test_pdf_sem_texto_sai_erro_com_a_frase_de_exportar_de_novo(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())
        _trocar_o_pdf(banco, "PRONTUARIO", "\f   \f\f")

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert (conta["situacao"], conta["erro_motivo"]) == ("ERRO", "Este PDF não tem texto. Exporte de novo pelo MV")

    def test_prontuario_com_pagina_faltando_sai_erro_de_arquivo_incompleto(self):
        banco = _cenario()
        _enviar(banco, _conta(), _arquivo_do_envio("prontuario.pdf", "\f".join(_paginas_do_prontuario()[:-1])))

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert (conta["situacao"], conta["erro_motivo"]) == (
            "ERRO",
            "Prontuário com arquivo incompleto: o rodapé indica 8 páginas e vieram 7.",
        )

    def test_falha_inesperada_volta_para_a_fila_e_na_terceira_tentativa_vira_erro_com_a_etapa(self, monkeypatch):
        tentativas = []

        def conferir_quebrado(*_a, **_kw):
            tentativas.append(1)
            raise RuntimeError("PostgREST fora do ar")

        monkeypatch.setattr(processamento, "conferir", conferir_quebrado)
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert len(tentativas) == 3
        assert (conta["situacao"], conta["erro_motivo"], conta["tentativas"]) == (
            "ERRO",
            "A análise parou na conferência. Envie de novo.",
            3,
        )


# ═══════════════════════════════════════════════════════════════════════════
# 6b. A IA: o Passo A no pipeline (issues #1130 e #1131)
# ═══════════════════════════════════════════════════════════════════════════

EVENTOS_DA_IA = {
    "atendimento": ATENDIMENTO,
    "idade_anos": 67,
    "movimentacoes": [],
    "terapias": [],
    "prescricoes": [],
    "procedimentos": [],
    "cirurgias": [],
    "documentos_ausentes": [],
    "observacoes": [],
}


PASSO_A, PASSO_B = "EventosDoProntuario", "LinhasDaComparacao"


class _OpenRouter:
    """O provedor do teste, na fronteira HTTP: responde pelo schema pedido
    (`eventos` no formato do Anexo A, `comparacao` no do Anexo B, `respostas`
    para os outros), fora do formato enquanto `fora_do_formato` for verdade
    (todos) ou o schema estiver em `fora_do_formato_em`, e guarda o corpo e o
    schema de cada requisição."""

    def __init__(self):
        self.requisicoes = 0
        self.fora_do_formato = False
        self.fora_do_formato_em: set[str] = set()
        self.eventos = EVENTOS_DA_IA
        self.comparacao: dict = {"linhas": [], "resumo": "Conta conferida."}
        self.respostas: dict[str, dict] = {}
        self.uso: dict = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "cost": 0.001}
        self.formatos: list[str] = []
        self.corpos: list[dict] = []
        # Gancho dos testes de corrida: roda com o schema pedido, antes da resposta.
        self.antes_de_responder = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes += 1
        corpo = json.loads(request.content)
        formato = corpo["response_format"]["json_schema"]["name"]
        if self.antes_de_responder:
            self.antes_de_responder(formato)
        self.formatos.append(formato)
        self.corpos.append(corpo)
        resposta = {PASSO_A: self.eventos, PASSO_B: self.comparacao}.get(formato) or self.respostas.get(formato)
        fora = self.fora_do_formato or formato in self.fora_do_formato_em or resposta is None
        conteudo = "não é JSON" if fora else json.dumps(resposta)
        return httpx.Response(
            200,
            json={
                "id": "gen",
                "object": "chat.completion",
                "created": 1,
                "model": "m",
                "choices": [
                    {"index": 0, "message": {"role": "assistant", "content": conteudo}, "finish_reason": "stop"}
                ],
                "usage": self.uso,
            },
        )


@pytest.fixture(autouse=True)
def openrouter(monkeypatch) -> _OpenRouter:
    """Toda conta passa pelo Passo A: sem este dublê, o pipeline falaria com o
    OpenRouter de verdade (a trava de rede da suíte reprova antes)."""
    duble = _OpenRouter()
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda: OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        ),
    )
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


class TestIAForaDoFormato:
    def test_a_conta_fica_em_erro_com_a_frase_e_o_reprocesso_funciona(self, openrouter):
        openrouter.fora_do_formato = True
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        # As três tentativas são do adaptador; o pipeline não repete a conta.
        assert openrouter.formatos == [PASSO_A] * 3
        assert (conta["situacao"], conta["erro_motivo"], conta["tentativas"]) == (
            "ERRO",
            "Tente de novo em alguns minutos",
            1,
        )
        assert [(c["situacao"], c["erro_motivo"]) for c in _fila(banco)] == [
            ("ERRO", "Tente de novo em alguns minutos")
        ]

        # O botão da conta em Erro manda a mesma conta de novo; a IA voltou.
        openrouter.fora_do_formato = False
        _enviar(banco, _conta())
        _rodar_o_job(banco)

        assert openrouter.formatos.count(PASSO_A) == 4
        assert banco.conta(conta["id"])["situacao"] == "A_FAZER"
        assert banco.conta(conta["id"])["erro_motivo"] is None


class TestPassoANoPipeline:
    def test_a_segunda_parcial_do_atendimento_nao_chama_o_passo_a(self, openrouter):
        banco = _cenario()
        _duas_parciais(banco)

        assert _rodar_o_job(banco) == 2

        assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["A_FAZER", "A_FAZER"]
        assert openrouter.formatos.count(PASSO_A) == 1
        (eventos,) = banco.tabelas["cm_eventos"]
        assert eventos["eventos_json"]["ia"]["atendimento"] == ATENDIMENTO

    def test_o_guia_sai_da_conferencia_com_os_eventos_do_passo_a(self, openrouter, monkeypatch):
        # A IA recebe os achados da conferência sem os eventos; o guia gravado é
        # o da conferência que roda depois, com os eventos que ela leu (#1134).
        ventilacao = {
            "tipo": "VENTILACAO_MECANICA",
            "descricao": "VM",
            "setor": "CTI ADULTO",
            "inicio": "2026-10-03T08:00",
            "fim": None,
            "pagina": 5,
            "trecho": "VM",
        }
        openrouter.eventos = {**EVENTOS_DA_IA, "terapias": [ventilacao]}
        recebidos = []
        original = processamento.conferir

        def conferir_espiado(*args, **kwargs):
            resultado = original(*args, **kwargs)
            if kwargs.get("eventos") is not None:
                # Só a primeira linha: o guia gravado tem que ser este, não o de antes.
                resultado = dataclasses.replace(resultado, linhas=resultado.linhas[:1])
            recebidos.append((kwargs.get("eventos"), resultado))
            return resultado

        monkeypatch.setattr(processamento, "conferir", conferir_espiado)
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
        (gravados,) = banco.tabelas["cm_eventos"]
        assert [eventos for eventos, _ in recebidos] == [None, gravados["eventos_json"]["ia"]]
        assert [t["tipo"] for t in recebidos[-1][0]["terapias"]] == ["VENTILACAO_MECANICA"]
        final = recebidos[-1][1]
        linhas = _linhas_do_guia(_guia(banco, conta["id"]))
        assert len(recebidos[0][1].linhas) > 1
        assert [{k: linha[k] for k in final.linhas[0]} for linha in linhas] == list(final.linhas)

    def test_a_chamada_do_passo_a_fica_gravada_com_os_tokens(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        (chamada,) = [c for c in banco.tabelas["cm_chamada_ia"] if c["passo"] == "A"]
        assert {k: chamada[k] for k in ("conta_id", "atendimento_id", "passo", "tokens_entrada", "tokens_saida")} == {
            "conta_id": conta["id"],
            "atendimento_id": conta["atendimento_id"],
            "passo": "A",
            "tokens_entrada": 10,
            "tokens_saida": 5,
        }

    def test_a_divergencia_os_documentos_ausentes_e_as_observacoes_da_ia_entram_no_parecer(self, openrouter):
        # O código leu a alta em 06/10 15:20 no resumo de alta; a IA leu 18:00.
        alta = {
            "tipo": "ALTA",
            "data_hora": "2026-10-06T18:00",
            "setor": "CTI ADULTO",
            "pagina": 8,
            "trecho": "DATA DA ALTA - 06/10/2026",
        }
        meia_risca = chr(0x2013)
        openrouter.eventos = {
            **EVENTOS_DA_IA,
            "movimentacoes": [alta],
            "documentos_ausentes": ["FICHA ANESTESICA"],
            "observacoes": [f"Evolução de enfermagem de 05/10 ilegível {meia_risca} página 22"],
        }
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        cabecalho = _guia(banco, conta["id"])["cabecalho"]
        assert cabecalho["parecer_parcial"] is True
        assert cabecalho["faltantes"] == [
            "O arquivo não trouxe: evolução médica (3 na capa).",
            "Documento ausente: FICHA ANESTESICA.",
            "Observação da IA: Evolução de enfermagem de 05/10 ilegível, página 22",
            "Movimentação divergente: a IA leu alta em 06/10/2026 18:00 (página 8); "
            "vale a leitura do código, alta em 06/10/2026 15:20.",
        ]
        (eventos,) = banco.tabelas["cm_eventos"]
        assert [(m["tipo"], m["data_hora"]) for m in eventos["eventos_json"]["ia"]["movimentacoes"]] == [
            ("INTERNACAO", "2026-10-02T22:40"),
            ("ALTA", "2026-10-06T15:20"),
        ]


# ═══════════════════════════════════════════════════════════════════════════
# 7. O aviso no sino
# ═══════════════════════════════════════════════════════════════════════════


def _avisos(banco: _Banco) -> list[dict]:
    return [n for n in banco.tabelas["notificacoes"] if n["tipo"] == "CONTAS_MEDICAS"]


class TestAvisoNoSino:
    def test_ao_fim_do_envio_a_faturista_recebe_um_aviso_com_quantas_contas_ficaram_prontas(self):
        banco = _cenario()
        envio = _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6), _prontuario())

        _rodar_o_job(banco)

        (aviso,) = _avisos(banco)
        assert (aviso["destinatario_id"], aviso["titulo"], aviso["referencia_id"], aviso["lida"]) == (
            "F1",
            "2 contas prontas",
            envio["envio_id"],
            False,
        )

    def test_nada_de_aviso_enquanto_uma_conta_do_envio_esta_na_fila(self):
        banco = _cenario()
        _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6), _prontuario())

        processamento.processar(banco, processamento.pegar_da_fila(banco, AGORA))

        assert _avisos(banco) == []
        processamento.processar(banco, processamento.pegar_da_fila(banco, AGORA))
        assert [a["titulo"] for a in _avisos(banco)] == ["2 contas prontas"]

    def test_o_envio_avisa_uma_vez_so(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())
        _rodar_o_job(banco)
        (conta,) = banco.tabelas["cm_conta"]

        # A mesma conta passa de novo pelo fim (uma vaga atrasada, por exemplo).
        processamento._avisar_se_o_envio_terminou(banco, conta)

        assert [a["titulo"] for a in _avisos(banco)] == ["1 conta pronta"]

    def test_a_conta_com_erro_entra_no_aviso(self):
        banco = _cenario()
        _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6, total_errado=True), _prontuario())

        _rodar_o_job(banco)

        (aviso,) = _avisos(banco)
        assert (aviso["titulo"], aviso["mensagem"]) == (
            "1 conta pronta",
            "O guia está na fila de Contas médicas. 1 conta com erro.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 8. O tempo de cada etapa
# ═══════════════════════════════════════════════════════════════════════════


class TestTempoDasEtapas:
    def test_o_tempo_de_cada_etapa_fica_gravado_na_conta(self):
        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())

        _rodar_o_job(banco)

        (conta,) = banco.tabelas["cm_conta"]
        tempos = conta["faltantes"]["tempos_por_etapa_s"]
        assert set(tempos) == {
            "texto_da_conta",
            "leitura_da_conta",
            "texto_do_prontuario",
            "leitura_do_prontuario",
            "dicionario",
            "conferencia",
            "passo_a",
            "conferencia_com_eventos",
            "passo_b",
            "gravacao",
            "total",
        }
        assert all(isinstance(segundos, float) and segundos >= 0 for segundos in tempos.values())
        assert tempos["total"] >= max(segundos for etapa, segundos in tempos.items() if etapa != "total")


# ═══════════════════════════════════════════════════════════════════════════
# 9. O log não leva texto de prontuário
# ═══════════════════════════════════════════════════════════════════════════


def _linhas_de_log(caplog) -> list[str]:
    formatador = logging.Formatter("%(name)s %(levelname)s %(message)s")
    return [formatador.format(registro) for registro in caplog.records]


class TestLogSemProntuario:
    def test_nenhuma_linha_de_log_tem_texto_do_prontuario_nem_no_erro(self, caplog, monkeypatch):
        """A exceção que nasce na leitura pode citar o texto que não leu: o log
        leva o tipo e o lugar, nunca a mensagem dela."""
        caplog.set_level(logging.DEBUG)
        leituras = []

        def ler_conteudo_que_cita_o_texto(textos, estrutura, palavras=None):
            leituras.append(1)
            if len(leituras) == 2:
                raise ValueError(f"campo ilegível: {textos[0]}")
            return ler_conteudo(textos, estrutura, palavras)

        monkeypatch.setattr(processamento, "ler_conteudo", ler_conteudo_que_cita_o_texto)
        banco = _cenario()
        _enviar(banco, _conta("48811", 2, 4), _conta("48812", 5, 6), _prontuario())

        _rodar_o_job(banco)

        linhas = _linhas_de_log(caplog)
        assert any("pronta em" in linha for linha in linhas)
        assert any("falhou na etapa leitura_do_prontuario" in linha and "ValueError" in linha for linha in linhas)
        assert [linha for linha in linhas if TRECHO_DO_PRONTUARIO in linha] == []


# ═══════════════════════════════════════════════════════════════════════════
# 10. O job no scheduler
# ═══════════════════════════════════════════════════════════════════════════


class TestJobNoScheduler:
    def test_o_job_roda_a_cada_10_segundos_uma_instancia_por_vez(self):
        from apscheduler.triggers.interval import IntervalTrigger

        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            job = cron.scheduler.get_job("fila_contas_medicas")
            assert job is not None
            assert job.func is cron.processar_fila_contas_medicas
            assert isinstance(job.trigger, IntervalTrigger)
            assert job.trigger.interval == timedelta(seconds=10)
            assert job.max_instances == 1
        finally:
            cron.stop_scheduler()

    def test_o_job_consome_a_fila_do_banco(self, monkeypatch):
        from app.cron import scheduler as cron

        banco = _cenario()
        _enviar(banco, _conta(), _prontuario())
        monkeypatch.setattr(cron, "_supabase", lambda: banco)
        entregues = []
        monkeypatch.setattr(
            processamento, "alimentar_fila", lambda sb, agora: entregues.append((sb, agora.tzinfo is not None))
        )

        cron.processar_fila_contas_medicas()

        assert entregues == [(banco, True)]


class TestDuasVagas:
    def test_o_job_entrega_no_maximo_duas_contas_enquanto_as_duas_vagas_estao_ocupadas(self, monkeypatch):
        monkeypatch.setattr(processamento, "processar", lambda _sb, _conta: None)
        banco = _Banco({"cm_conta": [_conta_na_fila(f"c{n}", n) for n in (1, 2, 3)]})
        guardadas = []

        class _Guardado:
            def submit(self, funcao, *args):
                guardadas.append((funcao, args))

        try:
            assert processamento.alimentar_fila(banco, AGORA, executor=_Guardado()) == 2
            assert processamento.alimentar_fila(banco, AGORA, executor=_Guardado()) == 0
            assert [c["situacao"] for c in banco.tabelas["cm_conta"]] == ["PROCESSANDO", "PROCESSANDO", "NA_FILA"]
        finally:
            for funcao, args in guardadas:
                funcao(*args)  # a análise termina e devolve a vaga

        assert processamento.alimentar_fila(banco, AGORA, executor=_Guardado()) == 1
        for funcao, args in guardadas[2:]:
            funcao(*args)


# ═══════════════════════════════════════════════════════════════════════════
# 11. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestKitDeConhecimento:
    """A sanidade geral (piso, seções, sem rota nem tabela) mora em
    `test_kit_conhecimento.py`; aqui, o que o texto tem que dizer da análise."""

    def test_diz_que_a_analise_roda_em_segundo_plano_e_avisa_no_sino(self):
        secao = KIT.read_text(encoding="utf-8").split("## A análise", 1)[1].split("\n## ", 1)[0]

        for trecho in (
            "segundo plano",
            "sino",
            "duas contas ao mesmo tempo",
            "três tentativas",
            "Este PDF não tem texto",
            "Não consegui ler a conta inteira",
            "arquivo incompleto",
        ):
            assert trecho in secao, trecho

    def test_nao_promete_mais_a_analise_para_uma_proxima_entrega(self):
        texto = KIT.read_text(encoding="utf-8")

        assert "chega nas próximas entregas" not in texto
        assert "Até lá a conta fica Na fila" not in texto


# ═══════════════════════════════════════════════════════════════════════════
# 12. Tipografia
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]

# O scheduler e o sino ficam de fora: têm travessão antigo em comentário, que
# ninguém vê, e o lint do front já trava o texto visível do sino.
ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/processamento.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/tabelas.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/envio.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas_extrator.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_guia.py",
    RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md",
    RAIZ_DO_APP / "frontend/src/components/layout/NotificacoesDropdown.test.tsx",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto


# ═══════════════════════════════════════════════════════════════════════════
# 13. A busca do pacote pelo TUSS no banco
# ═══════════════════════════════════════════════════════════════════════════


class TestPacotePeloTuss:
    def _buscar(self, banco: _Banco, tuss: str = "31005497", dia: int = 4):
        from datetime import date

        from app.services.contas_medicas.tabelas import pacote_pelo_tuss

        return pacote_pelo_tuss(banco, "op-alfa", tuss, date(2026, 10, dia))

    def test_acha_o_pacote_do_tuss_na_tabela_vigente(self):
        assert self._buscar(_cenario()) == Pacote("98005497", "PACOTE COLECISTECTOMIA", 2, Decimal("4500.0"))

    def test_tuss_sem_pacote_nao_tem_pacote(self):
        assert self._buscar(_cenario(), tuss="31009158") is None

    def test_tuss_em_dois_pacotes_nao_escolhe_um(self):
        banco = _cenario()
        banco.tabelas["cm_tabela_preco_item"].append(
            _item_de_tabela("it-3", "tb-pac", "98005498", "OUTRO", {"valor": 1.0}, {"codigos_tuss": ["31005497"]})
        )

        assert self._buscar(banco) is None

    def test_sem_permanencia_legivel_nao_inventa_diarias(self):
        banco = _cenario()
        banco.tabelas["cm_tabela_preco_item"][1]["extra_json"]["permanencia"] = "ver contrato"

        assert self._buscar(banco) is None

    def test_sem_valor_na_coluna_o_pacote_sai_sem_valor(self):
        banco = _cenario()
        banco.tabelas["cm_tabela_preco_item"][1]["precos_json"] = {"valor": "PACOTE"}

        assert self._buscar(banco).valor is None
