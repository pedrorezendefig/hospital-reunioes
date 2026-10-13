"""Ensinar uma regra nova na Memória da operadora (issue #1141, PRD #1129, ADR 0070).

A pessoa escreve a regra em linguagem comum; a IA propõe a regra no formato da
memória, o parâmetro do cabeçalho que muda, as regras com que ela conflita e o
efeito no Guia. Nada é gravado até o "Validar regra", que cria uma versão nova
da memória como a edição pela tela faz. As contas A fazer e Em correção da
operadora analisadas com a versão anterior ganham a marca "regra nova desde a
análise" e o botão "Reanalisar com a regra nova".

Tudo pela rota de verdade, com o dublê do banco da carga da operadora e o
provedor da IA dublado no transporte HTTP (o adaptador roda inteiro).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI
from test_contas_medicas_memoria_tela import _importar, _operadora_id, _versao, _versoes
from test_contas_medicas_operadoras import GESTAO, _Banco, _Consulta, _matriz_da_migration, _pessoa

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_guia as guia_router
from app.routers import contas_medicas_memoria as memoria_router
from app.routers import contas_medicas_operadoras as operadoras_router
from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria import ler_memoria
from app.services.contas_medicas.operadoras import memoria_vigente


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


DIA_03 = "Transferência de setor antes das 12h não gera diária extra no setor de origem."

PROPOSTA_DA_IA = {
    "regra": {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"},
    "parametro": {"chave": "diaria.hora_vencimento", "valor_json": '"12:00"'},
    # ALFA-DIA-99 não existe: a IA inventou, e a rota não repassa.
    "conflitos": ["ALFA-DIA-01", "ALFA-DIA-99"],
    "efeito_no_guia": "A diária do dia da transferência deixa de ser cobrada no setor de origem.",
}


class _Provedor:
    """O OpenRouter do teste: guarda o corpo de cada requisição e devolve a proposta."""

    def __init__(self):
        self.corpos: list[dict] = []
        self.resposta: dict = PROPOSTA_DA_IA

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.corpos.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "gen-1",
                "object": "chat.completion",
                "created": 1,
                "model": self.corpos[-1]["model"],
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": json.dumps(self.resposta)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020, "cost": 0.004},
            },
        )


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()

    def cliente():
        return OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        )

    monkeypatch.setattr(ia, "_cliente", cliente)
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


def _cliente(
    pessoa: dict[str, Any], banco: _Banco | None = None, ligar: tuple[str, ...] = ()
) -> tuple[TestClient, _Banco]:
    """O app com a carga, a Memória por tela e o Guia. `ligar` liga permissões
    no perfil da pessoa, como a Habilitação faria."""
    banco = banco or _Banco()
    banco.tabelas["participantes"] = [pessoa]
    matriz = _matriz_da_migration()
    for linha in matriz:
        if linha["perfil"] == pessoa["perfil_contas_medicas"] and linha["permissao"] in ligar:
            linha["ligada"] = True
    banco.tabelas["cm_perfil_permissao"] = matriz
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(operadoras_router.router, prefix="/api")
    app.include_router(memoria_router.router, prefix="/api")
    app.include_router(guia_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _proposta(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras/proposta"


def _validar(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/regras"


# ═══════════════════════════════════════════════════════════════════════════
# 1. A proposta da IA
# ═══════════════════════════════════════════════════════════════════════════


class TestPropostaDaIa:
    def test_a_proposta_traz_os_quatro_blocos_e_nao_grava_nada(self, provedor):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        regras_antes = len(banco.linhas("cm_regra"))

        resposta = cliente.post(
            _proposta("ALFA"), json={"texto": "Na ALFA a transferência antes do meio-dia não gera diária extra."}
        )

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["regra"] == {"secao": "DIA", "texto": DIA_03, "tipo": "CONTRATUAL", "origem": "PRÁTICA"}
        # O antes vem da memória vigente, não da IA.
        assert corpo["parametro"] == {"chave": "diaria.hora_vencimento", "antes": "10:00", "depois": "12:00"}
        assert corpo["conflitos"] == [
            {"codigo": "ALFA-DIA-01", "texto": "A diária começa em qualquer horário, vence às 10h e é sempre integral."}
        ]
        assert corpo["efeito_no_guia"] == PROPOSTA_DA_IA["efeito_no_guia"]

        # Nada gravado antes do Validar.
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert len(banco.linhas("cm_regra")) == regras_antes
        assert banco.linhas("cm_regra_historico") == []

        # A IA recebeu o texto da pessoa e a memória vigente.
        [corpo_da_ia] = provedor.corpos
        conteudo = json.dumps(corpo_da_ia["messages"], ensure_ascii=False)
        assert "transferência antes do meio-dia" in conteudo
        assert "ALFA-DIA-01" in conteudo
        assert corpo_da_ia["response_format"]["json_schema"]["strict"] is True


# ═══════════════════════════════════════════════════════════════════════════
# 2. Validar regra
# ═══════════════════════════════════════════════════════════════════════════

REGRA_VALIDADA = {
    "secao": "DIA",
    # A pessoa editou o texto que a IA propôs.
    "texto": "Transferência de setor antes das 12h não gera diária extra na origem.",
    "tipo": "CONTRATUAL",
    "origem": "PRÁTICA",
    "parametro": {"chave": "diaria.hora_vencimento", "valor": "12:00"},
}


def _regra_da_versao(banco: _Banco, versao: dict, codigo: str) -> dict:
    return next(r for r in banco.linhas("cm_regra") if r["memoria_versao_id"] == versao["id"] and r["codigo"] == codigo)


class TestValidarRegra:
    def test_validar_cria_versao_nova_com_a_regra_o_historico_e_o_parametro(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        resposta = cliente.post(_validar("ALFA"), json=REGRA_VALIDADA)

        assert resposta.status_code == 200, resposta.text
        assert (resposta.json()["versao"], resposta.json()["regra"]) == ("1.1", "ALFA-DIA-03")
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        nova = _versao(banco, "ALFA", "1.1")
        assert nova["autor_id"] == "P1"

        # O parâmetro mudou no cabeçalho da versão nova; o resto ficou, e a anterior não mudou.
        assert nova["parametros_json"]["diaria"]["hora_vencimento"] == "12:00"
        assert nova["parametros_json"]["diaria"]["limite_madrugada"] == "05:00"
        assert nova["parametros_json"]["opme"]["fornecida_por"] == "OPERADORA"
        assert _versao(banco, "ALFA", "1.0")["parametros_json"]["diaria"]["hora_vencimento"] == "10:00"

        # A regra entra vigente, com quem validou e a data, ao lado das cinco que já estavam.
        assert len(memoria_vigente(banco, _operadora_id(banco, "ALFA"))["regras"]) == 6
        regra = _regra_da_versao(banco, nova, "ALFA-DIA-03")
        assert (regra["texto"], regra["secao"], regra["tipo"], regra["origem"], regra["status"]) == (
            REGRA_VALIDADA["texto"],
            "DIA",
            "CONTRATUAL",
            "PRÁTICA",
            "VIGENTE",
        )
        assert regra["validado_por"] == "P1"
        assert regra["validado_em"]

        # O histórico guarda a regra nova, sem texto anterior.
        [historico] = banco.linhas("cm_regra_historico")
        assert (historico["regra_id"], historico["texto_anterior"], historico["texto_novo"]) == (
            regra["id"],
            None,
            REGRA_VALIDADA["texto"],
        )

        # O texto da versão nova, gerado do banco, já tem a regra e o parâmetro.
        lida = ler_memoria(nova["texto_md"])
        assert "ALFA-DIA-03" in {r.codigo for r in lida.regras}
        assert lida.parametros["diaria"]["hora_vencimento"] == "12:00"

    def test_sem_parametro_o_cabecalho_fica_como_estava(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        resposta = cliente.post(_validar("ALFA"), json={**REGRA_VALIDADA, "parametro": None})

        assert resposta.status_code == 200, resposta.text
        assert _versao(banco, "ALFA", "1.1")["parametros_json"]["diaria"]["hora_vencimento"] == "10:00"

    def test_permissao_segue_o_tipo_da_regra_e_a_recusa_nao_grava_nada(self):
        """Só a operacional ligada: 403 na regra contratual e na operacional que
        mexe em parâmetro do cabeçalho; a operacional sem parâmetro entra. Só a
        contratual: 403 na operacional."""
        banco = _Banco()
        gestao, _ = _cliente(GESTAO, banco)
        _importar(gestao)
        coordenadora, _ = _cliente(
            _pessoa(perfil_contas_medicas="coordenadora"), banco, ligar=("incluir_regra_operacional",)
        )
        operacional = {**REGRA_VALIDADA, "secao": "PRI", "tipo": "OPERACIONAL", "parametro": None}

        contratual = coordenadora.post(_validar("ALFA"), json=REGRA_VALIDADA)
        com_parametro = coordenadora.post(
            _validar("ALFA"), json={**operacional, "parametro": REGRA_VALIDADA["parametro"]}
        )

        assert (contratual.status_code, com_parametro.status_code) == (403, 403)
        assert _versoes(banco, "ALFA") == {"1.0": True}
        assert banco.linhas("cm_regra_historico") == []

        resposta = coordenadora.post(_validar("ALFA"), json=operacional)
        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["regra"] == "ALFA-PRI-04"

        so_contratual, _ = _cliente(
            _pessoa(perfil_contas_medicas="credenciamento"), banco, ligar=("regra_contratual_tabelas",)
        )
        assert so_contratual.post(_validar("ALFA"), json=operacional).status_code == 403
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}

    def test_regra_com_cpf_ou_chave_protegida_e_recusada(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)

        com_cpf = cliente.post(_validar("ALFA"), json={**REGRA_VALIDADA, "texto": "Paciente 123.456.789-09 paga."})
        protegida = cliente.post(
            _validar("ALFA"), json={**REGRA_VALIDADA, "parametro": {"chave": "versao_memoria", "valor": "9.9"}}
        )

        assert (com_cpf.status_code, protegida.status_code) == (409, 409)
        assert _versoes(banco, "ALFA") == {"1.0": True}


# ═══════════════════════════════════════════════════════════════════════════
# 3. As contas analisadas antes da regra nova
# ═══════════════════════════════════════════════════════════════════════════


A_FAZER_ALFA = "00000000-0000-4000-8000-0000000000a1"
EM_CORRECAO_ALFA = "00000000-0000-4000-8000-0000000000a2"
CONCLUIDA_ALFA = "00000000-0000-4000-8000-0000000000a3"
A_FAZER_BETA = "00000000-0000-4000-8000-0000000000b1"


def _com_contas(banco: _Banco) -> None:
    """Contas analisadas com a versão vigente de hoje: três da ALFA (A fazer,
    Em correção e Concluída) e uma A fazer da BETA."""
    versao = {sigla: _versao(banco, sigla, "1.0")["id"] for sigla in ("ALFA", "BETA")}
    banco.tabelas["cm_atendimento"] = [
        {"id": "at-alfa", "numero_atendimento": "31245", "operadora_id": _operadora_id(banco, "ALFA")},
        {"id": "at-beta", "numero_atendimento": "31302", "operadora_id": _operadora_id(banco, "BETA")},
    ]

    def conta(id_: str, atendimento: str, sigla: str, situacao: str) -> dict:
        return {
            "id": id_,
            "atendimento_id": atendimento,
            "numero_conta": f"N-{id_}",
            "situacao": situacao,
            "faturista_id": "F1",
            "memoria_versao_id": versao[sigla],
            "tentativas": 0,
        }

    banco.tabelas["cm_conta"] = [
        conta(A_FAZER_ALFA, "at-alfa", "ALFA", "A_FAZER"),
        conta(EM_CORRECAO_ALFA, "at-alfa", "ALFA", "EM_CORRECAO"),
        conta(CONCLUIDA_ALFA, "at-alfa", "ALFA", "CONCLUIDA"),
        conta(A_FAZER_BETA, "at-beta", "BETA", "A_FAZER"),
    ]
    banco.tabelas["cm_guia_linha"] = [
        {"id": "l-feita", "conta_id": EM_CORRECAO_ALFA, "estado": "FEITO", "acao": "INCLUIR", "valor": 10.0},
    ]


ROTA_CONTAS = "/api/contas-medicas/contas"


def _marcadas(cliente: TestClient, sigla: str) -> set[str]:
    resposta = cliente.get(f"/api/contas-medicas/operadoras/{sigla}")
    assert resposta.status_code == 200, resposta.text
    return {c["id"] for c in resposta.json()["contas_com_regra_nova"]}


class TestContasComRegraNova:
    def test_so_as_contas_abertas_da_operadora_ficam_marcadas_e_reanalisar_devolve_para_a_fila(self):
        cliente, banco = _cliente(GESTAO)
        _importar(cliente)
        _importar(cliente, "MEMORIA-BETA-v1.0.md")
        _com_contas(banco)
        assert _marcadas(cliente, "ALFA") == set()

        validada = cliente.post(_validar("ALFA"), json=REGRA_VALIDADA)

        assert validada.status_code == 200, validada.text
        assert validada.json()["contas_com_regra_nova"] == 2
        assert _marcadas(cliente, "ALFA") == {A_FAZER_ALFA, EM_CORRECAO_ALFA}
        assert _marcadas(cliente, "BETA") == set()
        [marcada] = [
            c
            for c in cliente.get("/api/contas-medicas/operadoras/ALFA").json()["contas_com_regra_nova"]
            if c["id"] == A_FAZER_ALFA
        ]
        assert (marcada["numero_atendimento"], marcada["numero_conta"], marcada["situacao"]) == (
            "31245",
            f"N-{A_FAZER_ALFA}",
            "A_FAZER",
        )

        # O Guia mostra a marca na conta da ALFA, e não na da BETA.
        guia = cliente.get(f"{ROTA_CONTAS}/{EM_CORRECAO_ALFA}/guia").json()
        assert guia["regra_nova_desde_analise"] is True
        assert guia["pode_reanalisar"] is True
        assert cliente.get(f"{ROTA_CONTAS}/{A_FAZER_BETA}/guia").json()["regra_nova_desde_analise"] is False

        # Reanalisar com a regra nova devolve a conta para a fila e não apaga a linha marcada.
        assert cliente.post(f"{ROTA_CONTAS}/{EM_CORRECAO_ALFA}/reanalisar").json() == {"situacao": "NA_FILA"}
        assert next(c for c in banco.linhas("cm_conta") if c["id"] == EM_CORRECAO_ALFA)["situacao"] == "NA_FILA"
        assert [linha["id"] for linha in banco.linhas("cm_guia_linha")] == ["l-feita"]
        assert _marcadas(cliente, "ALFA") == {A_FAZER_ALFA}

    def test_operadora_com_mais_atendimentos_que_o_limite_marca_as_abertas_sem_consultar_os_concluidos(self):
        """`cm_atendimento` cresce para sempre. O banco de verdade corta o select
        em 1000 linhas e recusa lista de ids grande na query string; a marca e a
        Memória continuam de pé, e os atendimentos concluídos ficam fora da consulta."""
        cliente, banco = _cliente(GESTAO, _BancoComLimites())
        _importar(cliente)
        _importar(cliente, "MEMORIA-BETA-v1.0.md")
        _com_contas(banco)
        versao = _versao(banco, "ALFA", "1.0")["id"]
        alfa = _operadora_id(banco, "ALFA")
        concluidos = [f"at-concluido-{i}" for i in range(_BancoComLimites.MAX_ROWS + 200)]
        banco.tabelas["cm_atendimento"] = [
            {"id": a, "numero_atendimento": f"9{i:05d}", "operadora_id": alfa} for i, a in enumerate(concluidos)
        ] + banco.tabelas["cm_atendimento"]
        # As concluídas são as mais antigas: vêm antes das abertas no banco.
        banco.tabelas["cm_conta"] = [
            {"id": f"c-{a}", "atendimento_id": a, "situacao": "CONCLUIDA", "memoria_versao_id": versao}
            for a in concluidos
        ] + banco.tabelas["cm_conta"]

        validada = cliente.post(_validar("ALFA"), json=REGRA_VALIDADA)

        assert validada.status_code == 200, validada.text
        assert validada.json()["contas_com_regra_nova"] == 2
        assert _marcadas(cliente, "ALFA") == {A_FAZER_ALFA, EM_CORRECAO_ALFA}
        consultados = {v for valores in banco.listas_consultadas for v in valores}
        assert not consultados & set(concluidos)


# A faturista da conta (issue #1207): "Reanalisar com a regra nova" é dela
# quando a memória mudou depois da análise; sem regra nova, é da gestão.
FATURISTA_DA_CONTA = _pessoa(id="F1", auth_user_id="auth-f1", perfil_contas_medicas="faturista")


def _regra_nova_na_alfa() -> _Banco:
    """A gestão ensina uma regra na ALFA: as contas abertas da ALFA ficam com a
    marca, a A fazer da BETA não."""
    cliente, banco = _cliente(GESTAO)
    _importar(cliente)
    _importar(cliente, "MEMORIA-BETA-v1.0.md")
    _com_contas(banco)
    assert cliente.post(_validar("ALFA"), json=REGRA_VALIDADA).status_code == 200
    return banco


def _situacao(banco: _Banco, conta_id: str) -> str:
    return next(c for c in banco.linhas("cm_conta") if c["id"] == conta_id)["situacao"]


class TestFaturistaReanalisaComARegraNova:
    def test_faturista_da_conta_reanalisa_a_conta_com_regra_nova(self):
        banco = _regra_nova_na_alfa()
        cliente, _ = _cliente(FATURISTA_DA_CONTA, banco)

        resposta = cliente.post(f"{ROTA_CONTAS}/{A_FAZER_ALFA}/reanalisar")

        assert resposta.status_code == 200, resposta.text
        assert _situacao(banco, A_FAZER_ALFA) == "NA_FILA"

    def test_faturista_da_conta_sem_regra_nova_recebe_403(self):
        banco = _regra_nova_na_alfa()
        cliente, _ = _cliente(FATURISTA_DA_CONTA, banco)

        resposta = cliente.post(f"{ROTA_CONTAS}/{A_FAZER_BETA}/reanalisar")

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Reanalisar sem regra nova é da gestão"
        assert _situacao(banco, A_FAZER_BETA) == "A_FAZER"

    def test_outra_faturista_com_regra_nova_recebe_403(self):
        banco = _regra_nova_na_alfa()
        outra = _pessoa(id="F2", auth_user_id="auth-f2", perfil_contas_medicas="faturista")
        cliente, _ = _cliente(outra, banco)

        resposta = cliente.post(f"{ROTA_CONTAS}/{A_FAZER_ALFA}/reanalisar")

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == "Esta conta é de outra faturista"
        assert _situacao(banco, A_FAZER_ALFA) == "A_FAZER"

    def test_quem_tem_regra_contratual_e_tabelas_reanalisa_sem_regra_nova(self):
        banco = _regra_nova_na_alfa()
        cliente, _ = _cliente(GESTAO, banco)

        resposta = cliente.post(f"{ROTA_CONTAS}/{A_FAZER_BETA}/reanalisar")

        assert resposta.status_code == 200, resposta.text
        assert _situacao(banco, A_FAZER_BETA) == "NA_FILA"

    def test_o_guia_mostra_o_botao_a_faturista_da_conta_so_com_regra_nova(self):
        banco = _regra_nova_na_alfa()
        cliente, _ = _cliente(FATURISTA_DA_CONTA, banco)

        com_regra_nova = cliente.get(f"{ROTA_CONTAS}/{EM_CORRECAO_ALFA}/guia").json()
        sem_regra_nova = cliente.get(f"{ROTA_CONTAS}/{A_FAZER_BETA}/guia").json()

        assert (com_regra_nova["regra_nova_desde_analise"], com_regra_nova["pode_reanalisar"]) == (True, True)
        assert (sem_regra_nova["regra_nova_desde_analise"], sem_regra_nova["pode_reanalisar"]) == (False, False)


class _ConsultaComLimites(_Consulta):
    def in_(self, coluna, valores):
        valores = list(valores)
        if len(valores) > _BancoComLimites.MAX_IDS_NA_URL:
            raise RuntimeError("414 Request-URI Too Large")
        self._banco.listas_consultadas.append(valores)
        return super().in_(coluna, valores)

    def execute(self):
        resposta = super().execute()
        if self._operacao == "select":
            resposta.data = resposta.data[: _BancoComLimites.MAX_ROWS]
        return resposta


class _BancoComLimites(_Banco):
    """O dublê com os dois limites do banco de verdade: o `max_rows` do PostgREST
    e o tamanho da linha de requisição do gateway (cerca de 200 UUIDs)."""

    MAX_ROWS = 1000
    MAX_IDS_NA_URL = 200

    def __init__(self):
        super().__init__()
        self.listas_consultadas: list[list] = []

    def table(self, nome: str):
        return _ConsultaComLimites(self, nome)


# ═══════════════════════════════════════════════════════════════════════════
# 4. O texto do Produto e a tipografia
# ═══════════════════════════════════════════════════════════════════════════

RAIZ_DO_APP = Path(__file__).resolve().parents[2]
KIT = RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md"


class TestTextoDoProduto:
    """A sanidade geral do kit mora em `test_kit_conhecimento.py`; aqui, o que
    ESTE texto tem que dizer da regra ensinada pela tela."""

    def test_diz_que_regra_nova_se_ensina_em_linguagem_comum(self):
        no_ar = KIT.read_text(encoding="utf-8").split("## O que já está no ar")[1].split("\n## ")[0]

        for termo in (
            "Ensinar uma regra nova",
            "linguagem comum",
            "Validar regra",
            "regra nova desde a análise",
            "Reanalisar com a regra nova",
        ):
            assert termo in no_ar, termo


ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/regra_nova.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/memoria_edicao.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/ia.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_regra_nova.md",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_memoria.py",
    RAIZ_DO_APP / "backend/app/routers/contas_medicas_guia.py",
    KIT,
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/operadoras/[sigla]/page.tsx",
    RAIZ_DO_APP / "frontend/src/app/contas-medicas/guia/[contaId]/page.tsx",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
