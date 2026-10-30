"""O reenvio da conta corrigida e a nota de saída (issue #1136, PRD #1128, ADR 0070).

Depois de corrigir no MV, a faturista pode reenviar só o PDF da conta de uma
conta concluída: pelo botão do Guia ou arrastando na tela Contas. O app lê a
conta nova com o leitor de sempre, compara os itens com as linhas Feito
(Incluir que entrou, Retirar que sumiu) e calcula a nota de saída pelo mesmo
helper da nota de entrada, só com as linhas Feito que continuam na conta. O
prontuário não é lido de novo e a IA não é chamada.

O "PDF" do teste é o texto das páginas separado por form feed, como nos testes
do envio: o extrator é trocado por um dublê.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from contas_medicas_apoio import matriz_aplicada  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_envio as envio_router  # noqa: E402
from app.routers import contas_medicas_guia as guia_router  # noqa: E402
from app.services.contas_medicas import envio as envio_service  # noqa: E402
from app.services.contas_medicas import ia  # noqa: E402
from app.services.contas_medicas import prontuario as leitura_do_prontuario  # noqa: E402
from app.services.contas_medicas import reenvio as reenvio_service  # noqa: E402
from app.services.contas_medicas_extrator import Pagina  # noqa: E402

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "116_contas_medicas_fundacao.sql"

CONTA = "22222222-2222-2222-2222-222222222222"
ROTA_REENVIO = f"/api/contas-medicas/contas/{CONTA}/reenvio"
ROTA_GUIA = f"/api/contas-medicas/contas/{CONTA}/guia"
ROTA_ENVIO = "/api/contas-medicas/envios"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _extrair(pdf: bytes):
    partes = pdf.decode("utf-8").split("\f")
    return [Pagina(numero=n, texto=t, sem_texto=not t.strip()) for n, t in enumerate(partes, start=1)]


@pytest.fixture(autouse=True)
def _extrator_de_texto(monkeypatch):
    """O "PDF" do teste é o texto das páginas separado por form feed."""
    monkeypatch.setattr(envio_service, "extrair_paginas", _extrair)
    monkeypatch.setattr(reenvio_service, "extrair_paginas", _extrair)


@pytest.fixture
def chamadas(monkeypatch) -> list[str]:
    """Conta toda chamada à leitura do prontuário e ao adaptador de IA."""
    registro: list[str] = []

    def contar(nome):
        def chamada(*_a, **_kw):
            registro.append(nome)

        return chamada

    monkeypatch.setattr(leitura_do_prontuario, "ler_prontuario", contar("ler_prontuario"))
    for nome in ("extrair_eventos", "comparar_conta", "chamada_curta"):
        monkeypatch.setattr(ia, nome, contar(nome))
    return registro


# ═══════════════════════════════════════════════════════════════════════════
# A conta corrigida
# ═══════════════════════════════════════════════════════════════════════════

# Os itens da conta como o MV imprime: data, código, descrição, unidade,
# percentual, quantidade, unitário e total.
LUVA = "03/10/2026  90000001  LUVA DE PROCEDIMENTO                 PAR     100,00%    2,00      25,00      50,00"
DIPIRONA = "04/10/2026  90000002  DIPIRONA SODICA 500MG/ML 2ML         AMP     100,00%    1,00      30,00      30,00"
SENHA = "03/10/2026  90000003  SENHA DE ACESSO AO SISTEMA           UN      100,00%    1,00     120,00     120,00"
DIARIA = "03/10/2026  90000004  DIARIA DE ENFERMARIA                 DIA     100,00%    1,00     800,00     800,00"


def _texto_da_conta(itens: list[str], total: str, atendimento="31302", conta="48001") -> str:
    corpo = "\n".join(itens)
    return f"""\
HOSPITAL FICTICIO DE TESTE                                                         Página 1 de 1
                                   Fatura Individual

Atendimento: {atendimento}          Conta: {conta}          Tipo: INTERNACAO
Internação: 03/10/2026 08:30
Período da   03/10/2026 a 05/10/2026          Acomodação: ENFERMARIA
Plano: ASSIM CARIOCA ENF
Guia: 123456789

MATERIAIS DESCARTAVEIS
43  ENFERMARIA
{corpo}

Total da Conta:                                                                  {total}
"""


def _conta_corrigida(**kw) -> bytes:
    """A luva e a dipirona entraram; a senha, que era para sair, continua."""
    return _texto_da_conta([LUVA, DIPIRONA, SENHA, DIARIA], "1.000,00", **kw).encode("utf-8")


def _pdf(conteudo: bytes, nome="conta-corrigida.pdf"):
    return (nome, conteudo, "application/pdf")


# ═══════════════════════════════════════════════════════════════════════════
# O dublê do banco
# ═══════════════════════════════════════════════════════════════════════════


def _matriz_da_migration() -> list[dict[str, Any]]:
    """A matriz depois de todas as migrations: a 121 separa Enviar de Analisar (issue #1308)."""
    return matriz_aplicada()


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
                self._banco.relogio += 1
                criado_em = f"2026-10-12T10:00:00.{self._banco.relogio:06d}+00:00"
                gravadas.append({"id": str(uuid.uuid4()), "criado_em": criado_em, **nova})
            tabela.extend(gravadas)
            return SimpleNamespace(data=[dict(g) for g in gravadas])
        casam = [linha for linha in tabela if all(f(linha) for f in self._filtros)]
        if self._update is not None:
            for linha in casam:
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

    def conta(self) -> dict:
        return next(c for c in self.tabelas["cm_conta"] if c["id"] == CONTA)


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


PESSOAS = {"faturista": _pessoa("F1", "faturista"), "outra_faturista": _pessoa("F2", "faturista")}


def _uid(nome: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"cm-guia-linha-reenvio/{nome}"))


def _linha(nome, acao, codigo, data, valor, estado="FEITO", **campos) -> dict:
    base = {
        "id": _uid(nome),
        "conta_id": CONTA,
        "acao": acao,
        "codigo": codigo,
        "descricao": nome,
        "data": data,
        "data_fim": None,
        "setor": "ENFERMARIA",
        "ordem": 1,
        "valor_diferenca": valor,
        "preco_lancado": None,
        "preco_tabela": 1.0,
        "quantidade_lancada": None,
        "quantidade_devida": None,
        "estado": estado,
    }
    return {**base, **campos}


def _linhas() -> list[dict]:
    """Três linhas Feito (2 Incluir, 1 Retirar) e uma ainda aberta."""
    return [
        _linha("luva", "INCLUIR", "90000001", "2026-10-03", 50.00, quantidade_devida=2, preco_tabela=25.0),
        _linha("dipirona", "INCLUIR", "90000002", "2026-10-04", 30.00, quantidade_devida=1, preco_tabela=30.0),
        _linha("senha", "RETIRAR", "90000003", "2026-10-03", -120.00, quantidade_lancada=1, preco_tabela=None),
        _linha("fita", "INCLUIR", "90000009", "2026-10-05", 100.00, estado="ABERTA"),
    ]


def _conta(**campos) -> dict:
    base = {
        "id": CONTA,
        "atendimento_id": "at-1",
        "arquivo_id": "arq-original",
        "numero_conta": "48001",
        "periodo_inicio": "2026-10-03",
        "periodo_fim": "2026-10-05",
        # A conta antes da correção: a diária e a senha, sem a luva e a dipirona.
        "total_lancado": 920.00,
        "situacao": "CONCLUIDA_COM_PENDENCIA",
        "parecer_parcial": False,
        "faltantes": {"itens": [], "tempos_por_etapa_s": {"leitura": 1.0}},
        "nota_bruta": 79,
        "nota_entrada": 79,
        "nota_saida": None,
        "reenviada_em": None,
        "faturista_id": "F1",
        "ordem_fila": 10,
    }
    return {**base, **campos}


def _cenario(conta: dict | None = None) -> _Banco:
    return _Banco(
        {
            "participantes": list(PESSOAS.values()),
            "cm_perfil_permissao": _matriz_da_migration(),
            "cm_operadora": [{"id": "op-1", "sigla": "ASSIM", "nome": "ASSIM Saúde", "situacao": "PRONTA"}],
            "cm_operadora_plano": [
                {"id": "pl-1", "operadora_id": "op-1", "nome_mv": "ASSIM CARIOCA", "coluna_preco": "CARIOCA"},
            ],
            "cm_atendimento": [
                {
                    "id": "at-1",
                    "numero_atendimento": "31302",
                    "paciente_rotulo": "Maria S.",
                    "operadora_id": "op-1",
                    "plano": "ASSIM CARIOCA ENF",
                    "coluna_preco": "CARIOCA",
                }
            ],
            "cm_conta": [conta or _conta()],
            "cm_guia_linha": _linhas(),
            "cm_envio": [],
            "cm_arquivo": [],
            "cm_eventos": [],
            "cm_observacao": [],
        }
    )


def _cliente(quem: str, banco: _Banco) -> TestClient:
    pessoa = PESSOAS[quem]
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(guia_router.router, prefix="/api")
    app.include_router(envio_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


def _marcas(guia: dict) -> dict[str, str | None]:
    return {linha["descricao"]: linha["reenvio"] for grupo in guia["grupos"] for linha in grupo["linhas"]}


# ═══════════════════════════════════════════════════════════════════════════
# 1. O reenvio pelo botão do Guia
# ═══════════════════════════════════════════════════════════════════════════


class TestReenvioPeloGuia:
    def test_incluidas_que_entraram_saem_corrigidas_e_a_retirada_que_ficou_continua(self, chamadas):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert (corpo["corrigidas"], corpo["ainda_na_conta"]) == (2, 1)
        assert corpo["linhas"] == {
            _uid("luva"): "CORRIGIDA",
            _uid("dipirona"): "CORRIGIDA",
            _uid("senha"): "AINDA_NA_CONTA",
        }

    def test_nota_de_saida_e_calculada_so_com_a_linha_feito_que_continua(self, chamadas):
        """Só a senha continua: R$ 120 apontados. A conta corrigida soma R$
        1.000 e a senha sai com sinal negativo: R$ devido 880. Nota:
        100 x (1 - 120 / 880) = 86,4, arredondada para 86."""
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        assert resposta.json()["nota_saida"] == 86
        conta = banco.conta()
        assert conta["nota_saida"] == 86
        assert conta["reenviada_em"] is not None
        # A conta continua concluída, com a nota de entrada como estava.
        assert (conta["situacao"], conta["nota_entrada"]) == ("CONCLUIDA_COM_PENDENCIA", 79)

    def test_o_guia_mostra_a_marca_de_cada_linha_e_a_nota_de_saida(self, chamadas):
        banco = _cenario()
        cliente = _cliente("faturista", banco)
        cliente.post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        guia = cliente.get(ROTA_GUIA).json()

        assert _marcas(guia) == {"luva": "CORRIGIDA", "dipirona": "CORRIGIDA", "senha": "AINDA_NA_CONTA", "fita": None}
        assert guia["reenvio"]["nota_saida"] == 86
        assert (guia["reenvio"]["corrigidas"], guia["reenvio"]["ainda_na_conta"]) == (2, 1)
        assert guia["pode_reenviar"] is True
        # O que o processamento guardou ao lado continua lá.
        assert banco.conta()["faltantes"]["tempos_por_etapa_s"] == {"leitura": 1.0}

    def test_guia_sem_reenvio_nao_tem_marca_nem_nota_de_saida(self, chamadas):
        guia = _cliente("faturista", _cenario()).get(ROTA_GUIA).json()

        assert set(_marcas(guia).values()) == {None}
        assert guia["reenvio"] is None
        assert guia["pode_reenviar"] is True

    def test_nao_le_o_prontuario_nem_chama_a_ia(self, chamadas):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        assert resposta.status_code == 200
        assert chamadas == []

    @pytest.mark.parametrize("situacao", ["A_FAZER", "EM_CORRECAO"])
    def test_conta_nao_concluida_e_recusada_com_mensagem(self, chamadas, situacao):
        banco = _cenario(_conta(situacao=situacao))

        resposta = _cliente("faturista", banco).post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == "Só a conta concluída pode ser reenviada."
        assert banco.conta()["nota_saida"] is None

    def test_conta_em_aberto_nao_mostra_o_botao(self, chamadas):
        guia = _cliente("faturista", _cenario(_conta(situacao="EM_CORRECAO"))).get(ROTA_GUIA).json()

        assert guia["pode_reenviar"] is False

    def test_pdf_de_outra_conta_e_recusado(self, chamadas):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(
            ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida(conta="48999"))}
        )

        assert resposta.status_code == 422
        assert "48001" in resposta.json()["detail"]
        assert banco.conta()["nota_saida"] is None

    def test_faturista_que_nao_e_dona_nao_reenvia(self, chamadas):
        banco = _cenario()

        resposta = _cliente("outra_faturista", banco).post(ROTA_REENVIO, files={"arquivo": _pdf(_conta_corrigida())})

        assert resposta.status_code == 403
        assert banco.conta()["nota_saida"] is None


# ═══════════════════════════════════════════════════════════════════════════
# 2. O reenvio pela tela Contas
# ═══════════════════════════════════════════════════════════════════════════


class TestReenvioPelaTelaContas:
    def test_conta_de_atendimento_concluido_entra_como_reenvio_e_o_ultimo_envio_diz(self, chamadas):
        banco = _cenario()

        resposta = _cliente("faturista", banco).post(ROTA_ENVIO, files=[("arquivos", _pdf(_conta_corrigida()))])

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["recusas"] == []
        assert [linha["texto"] for linha in corpo["ultimo_envio"]] == [
            "31302, reenvio da conta 48001: 2 corrigidas no MV, 1 ainda na conta, nota de saída 86"
        ]
        conta = banco.conta()
        # Reenvio não é reprocesso: a conta não volta para a fila.
        assert (conta["situacao"], conta["nota_saida"]) == ("CONCLUIDA_COM_PENDENCIA", 86)
        assert chamadas == []

    def test_a_fila_mostra_as_duas_notas_da_conta_concluida(self, chamadas):
        banco = _cenario()
        cliente = _cliente("faturista", banco)
        cliente.post(ROTA_ENVIO, files=[("arquivos", _pdf(_conta_corrigida()))])

        concluidas = cliente.get("/api/contas-medicas/fila").json()["concluidas"]

        assert [(c["nota_entrada"], c["nota_saida"]) for c in concluidas] == [(79, 86)]


def _prontuario_do_atendimento() -> bytes:
    capa = "HOSPITAL FICTICIO DE TESTE\nDECLARAÇÃO DE RECEBIMENTO DE PRONTUÁRIO\nGrupo: EVOLUÇÃO MÉDICA\n"
    pagina = "EVOLUÇÃO MÉDICA\nATENDIMENTO: 31302\nData/Hora do Documento: 05/10/2026 09:00\n"
    return f"{capa}\f{pagina}".encode()


def _parcial_a_espera_do_prontuario() -> dict:
    return _conta(
        id="33333333-3333-3333-3333-333333333333",
        arquivo_id="arq-parcial-2",
        numero_conta="48002",
        situacao="AGUARDANDO_ARQUIVO",
        nota_bruta=None,
        nota_entrada=None,
    )


class TestEnvioSoComOProntuario:
    """A parcial 1 está concluída, a parcial 2 espera o prontuário e a
    faturista manda só o prontuário: nada ali é reenvio."""

    def test_conta_concluida_sem_reenvio_nao_derruba_o_ultimo_envio(self, chamadas):
        banco = _cenario()
        banco.tabelas["cm_conta"].append(_parcial_a_espera_do_prontuario())

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[("arquivos", _pdf(_prontuario_do_atendimento(), "prontuario.pdf"))]
        )

        assert resposta.status_code == 200, resposta.text
        assert [linha["texto"] for linha in resposta.json()["ultimo_envio"]] == ["31302, 2 parciais e prontuário"]
        situacoes = {c["numero_conta"]: c["situacao"] for c in banco.tabelas["cm_conta"]}
        assert situacoes == {"48001": "CONCLUIDA_COM_PENDENCIA", "48002": "NA_FILA"}

    def test_conta_reenviada_antes_nao_aparece_como_reenvio_deste_envio(self, chamadas):
        banco = _cenario(_conta(reenviada_em="2026-10-11T10:00:00+00:00", nota_saida=86))
        banco.tabelas["cm_conta"].append(_parcial_a_espera_do_prontuario())

        resposta = _cliente("faturista", banco).post(
            ROTA_ENVIO, files=[("arquivos", _pdf(_prontuario_do_atendimento(), "prontuario.pdf"))]
        )

        assert resposta.status_code == 200, resposta.text
        assert [linha["texto"] for linha in resposta.json()["ultimo_envio"]] == ["31302, 2 parciais e prontuário"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. As rotas no app de verdade, o kit e a tipografia
# ═══════════════════════════════════════════════════════════════════════════


class TestAsRotasEstaoNoApp:
    def test_o_app_de_verdade_registra_a_rota_do_reenvio(self):
        """A fonte é o schema OpenAPI, e não `app.routes` (FastAPI 0.141)."""
        from app.main import app

        cache = app.openapi_schema
        try:
            caminhos = app.openapi()["paths"]
        finally:
            app.openapi_schema = cache

        assert len(caminhos) > 50
        assert "post" in caminhos["/api/contas-medicas/contas/{conta_id}/reenvio"]


KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestKitDeConhecimento:
    def test_o_texto_do_produto_diz_que_o_reenvio_e_opcional_e_o_que_ele_mostra(self):
        secao = KIT.read_text(encoding="utf-8").split("## O reenvio da conta corrigida", 1)[1].split("\n## ", 1)[0]

        for trecho in (
            "Reenviar conta corrigida",
            "opcional",
            "produção",
            "corrigida no MV",
            "ainda na conta",
            "nota de saída",
            "não é lido de novo",
        ):
            assert trecho in secao, trecho


RAIZ_DO_APP = Path(__file__).resolve().parents[2]

ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/reenvio.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/envio.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_guia.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_envio.py",
    RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md",
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/guia/[contaId]/page.tsx",
    RAIZ_DO_APP / "frontend/src/components/contas-medicas/LinhaDoGuia.tsx",
    RAIZ_DO_APP / "frontend/src/lib/contas-medicas/guia.ts",
    RAIZ_DO_APP / "frontend/src/lib/contas-medicas/envio.ts",
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
