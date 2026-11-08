"""A fila de Validação chega decidida pelo Auditor (issue #1491, PRD #1484, ADR 0081, decisão 13).

Cada Tema aberto ganha a recomendação do Auditor: a decisão, o motivo e, no
Tema de Regra pendente, a Prova da regra. Quem decide na Validação aprova o
lote de uma vez; o Tema que ele corrigir antes segue a correção. A decisão
aplicada segue o caminho de hoje: versão nova da Memória e Retorno da Conta
concluída só com as Linhas decididas.

Tudo pelas rotas de verdade, com o dublê do banco da Validação e o provedor da
IA dublado no transporte HTTP: o Auditor responde pelo título do Tema que está
no pedido, e o Passo B da prova não traz Linha nova.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem
from test_contas_medicas_validacao import (
    C1,
    C2,
    C3,
    CATETER,
    REGRA_PENDENTE,
    REGRA_VIGENTE,
    TEXTO_PENDENTE,
    _Banco,
    _cenario,
    _cliente,
    _decidir,
    _fila_de_validacao,
    _gravar,
    _guia,
    _linha_do_guia,
    _linhas_do_guia,
    _marcar,
    _tema_no_banco,
)

from app.limiter import limiter
from app.services.contas_medicas import ia
from app.services.contas_medicas.validacao_decidida import recomendar_abertos

RAIZ_DO_APP = Path(__file__).resolve().parents[2]
KIT = RAIZ_DO_APP / "backend" / "app" / "conhecimento" / "contas-medicas.md"
MIGRATION_126 = RAIZ_DO_APP / "supabase" / "migrations" / "126_contas_medicas_auditor.sql"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


RESPOSTA_AO_TIME = "Na ALFA o Clexane vem no pacote: a regra segue como está."

# O que o Auditor responde, pelo título do Tema.
RECOMENDACOES = {
    f"Regra {REGRA_PENDENTE}": {
        "decisao": "VALIDAR_REGRA",
        "motivo": "A seringa pronta é cobrada à parte no contrato da ALFA.",
        "texto": "",
    },
    f"Código {CATETER} bloqueado": {
        "decisao": "DESCARTAR",
        "motivo": "O cateter já tem código novo no MV.",
        "texto": "",
    },
    f"Observações sobre a regra {REGRA_VIGENTE}": {
        "decisao": "RESPONDER",
        "motivo": "A regra já cobre o caso.",
        "texto": RESPOSTA_AO_TIME,
    },
}


class _Provedor:
    """A Anthropic do teste: o Auditor responde pelo título do Tema; o Passo B
    da prova responde sem Linha nova. Guarda o texto de cada pedido."""

    def __init__(self):
        self.pedidos: list[str] = []
        self.recomendacoes = dict(RECOMENDACOES)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        corpo = json.loads(request.content)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append(texto)
        if "O TEMA DE VALIDAÇÃO" in texto:
            titulo = re.search(r"Título: (.+)", texto).group(1).strip()
            return httpx2.Response(200, json=mensagem(json.dumps(self.recomendacoes[titulo])))
        return httpx2.Response(200, json=mensagem(json.dumps({"linhas": [], "resumo": "Comparada."})))

    def do_auditor(self) -> list[str]:
        return [p for p in self.pedidos if "O TEMA DE VALIDAÇÃO" in p]


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


def _conta_concluida_com_eventos(banco: _Banco) -> None:
    """A C3 concluída, com o período, os itens e os eventos que a análise
    guardou: é a conta que a Prova da regra refaz."""
    conta = banco.conta(C3)
    conta.update(
        {"concluida_em": "2026-10-06T18:00:00+00:00", "periodo_inicio": "2026-10-01", "periodo_fim": "2026-10-05"}
    )
    banco.tabelas["cm_conta_item"] = [
        {
            "id": "i3",
            "conta_id": C3,
            "ordem": 1,
            "data": "2026-10-03",
            "grupo_conta": "MATERIAL",
            "setor": "CTI ADULTO",
            "codigo": "70000099",
            "descricao": "Seringa comum",
            "quantidade": 1,
            "unidade": "UN",
            "valor_unitario": 10.0,
            "valor_total": 10.0,
            "percentual": 100.0,
        }
    ]
    banco.tabelas["cm_eventos"] = [
        {
            "id": "ev3",
            "atendimento_id": "at-3",
            "criado_em": "2026-10-06T08:00:00+00:00",
            "eventos_json": {"ia": {"movimentacoes": [], "prescricoes": [], "observacoes": ["seringa pronta"]}},
        }
    ]
    banco.tabelas.setdefault("cm_prova", [])


def _tres_temas(banco: _Banco) -> dict[str, dict]:
    """Regra pendente nas três contas (a C3 concluída, com uma Linha já Feita
    que não volta), o cateter bloqueado na C1 e na C2 e um Não procede na C2."""
    _conta_concluida_com_eventos(banco)
    cateter = _linha_do_guia("INCLUIR", CATETER, 33.0, REGRA_VIGENTE, descricao="CATETER")
    clexane = _linha_do_guia("INCLUIR", "90030001", 45.0, REGRA_VIGENTE, descricao="CLEXANE")
    _gravar(banco, C1, _linha_do_guia("VALIDAR", "70000010", 120.0, REGRA_PENDENTE), cateter)
    _gravar(banco, C2, _linha_do_guia("VALIDAR", "70000010", 80.0, REGRA_PENDENTE), cateter, clexane)
    _gravar(banco, C3, _linha_do_guia("VALIDAR", "70000010", 50.5, REGRA_PENDENTE), clexane)
    for linha in list(banco.tabelas["cm_guia_linha"]):
        if linha["codigo"] == CATETER:
            _marcar(banco, linha["conta_id"], linha["id"], {"estado": "BLOQUEADO"})
        elif linha["codigo"] == "90030001" and linha["conta_id"] == C2:
            _marcar(
                banco,
                C2,
                linha["id"],
                {"estado": "NAO_PROCEDE", "motivo": "REGRA_E_OUTRA", "texto": "Na ALFA o Clexane vem no pacote"},
            )
        elif linha["codigo"] == "90030001":
            linha["estado"] = "FEITO"
    return {t["tipo"]: t for t in _fila_de_validacao(banco)["temas"]}


def _aprovar(banco: _Banco, temas: list[str], quem: str = "gestao"):
    return _cliente(banco, quem).post("/api/contas-medicas/validacao/lote", json={"temas": temas})


# ═══════════════════════════════════════════════════════════════════════════
# 1. A recomendação do Auditor em cada Tema aberto
# ═══════════════════════════════════════════════════════════════════════════


class TestARecomendacao:
    def test_temas_abertos_recebem_decisao_e_motivo_e_a_regra_pendente_traz_a_prova(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        assert {t["recomendacao"] for t in temas.values()} == {None}

        recomendados = recomendar_abertos(banco)

        assert recomendados == 3
        fila = {t["tipo"]: t for t in _fila_de_validacao(banco)["temas"]}
        regra = fila["REGRA_PENDENTE"]["recomendacao"]
        assert (regra["decisao"], regra["motivo"]) == (
            "VALIDAR_REGRA",
            "A seringa pronta é cobrada à parte no contrato da ALFA.",
        )
        # A prova refez a única concluída da ALFA com a regra vigente, e diz o que mudaria.
        assert regra["prova"]["contas"] == 1
        assert regra["prova"]["mudaria"] is False
        [prova] = banco.tabelas["cm_prova"]
        assert (prova["regra_codigo"], prova["contas"]) == (REGRA_PENDENTE, 1)
        assert _tema_no_banco(banco, temas["REGRA_PENDENTE"]["id"])["recomendacao_prova_id"] == prova["id"]
        # O Auditor leu a prova antes de recomendar.
        [pedido_da_regra] = [p for p in provedor.do_auditor() if f"Título: Regra {REGRA_PENDENTE}" in p]
        assert "não mudaria nada" in pedido_da_regra
        assert TEXTO_PENDENTE in pedido_da_regra

        bloqueado = fila["BLOQUEADO"]["recomendacao"]
        assert (bloqueado["decisao"], bloqueado["motivo"], bloqueado["prova"]) == (
            "DESCARTAR",
            "O cateter já tem código novo no MV.",
            None,
        )
        observacao = fila["OBSERVACAO"]["recomendacao"]
        assert (observacao["decisao"], observacao["motivo"], observacao["texto"]) == (
            "RESPONDER",
            "A regra já cobre o caso.",
            RESPOSTA_AO_TIME,
        )
        # Nada foi decidido: quem aprova é a pessoa.
        assert {t["estado"] for t in banco.tabelas["cm_validacao_tema"]} == {"ABERTO"}
        # O custo do Auditor e da prova entra na semana do Painel com o passo próprio.
        passos = [c["passo"] for c in banco.tabelas["cm_chamada_ia"]]
        assert passos.count("CONVERSA") == 3 and passos.count("PROVA") == 1

    def test_tema_ja_recomendado_nao_pergunta_de_novo_e_observacao_nova_pede_recomendacao_nova(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        recomendar_abertos(banco)

        assert recomendar_abertos(banco) == 0
        assert len(provedor.do_auditor()) == 3

        concluida = _cliente(banco, "faturista").post(
            f"/api/contas-medicas/contas/{C1}/guia/concluir",
            json={"observacao": f"A {REGRA_VIGENTE} também não vale para o Clexane desta conta."},
        )
        assert concluida.status_code == 200, concluida.text

        assert _tema_no_banco(banco, temas["OBSERVACAO"]["id"])["recomendacao"] is None
        assert recomendar_abertos(banco) == 1

    def test_decisao_que_nao_cabe_no_tema_nao_vira_recomendacao(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        provedor.recomendacoes[f"Código {CATETER} bloqueado"] = {
            "decisao": "VALIDAR_REGRA",
            "motivo": "Errado.",
            "texto": "",
        }
        provedor.recomendacoes[f"Observações sobre a regra {REGRA_VIGENTE}"] = {
            "decisao": "RESPONDER",
            "motivo": "Sem a resposta.",
            "texto": "",
        }

        recomendar_abertos(banco)

        assert _tema_no_banco(banco, temas["BLOQUEADO"]["id"])["recomendacao"] is None
        assert _tema_no_banco(banco, temas["OBSERVACAO"]["id"])["recomendacao"] is None
        assert _tema_no_banco(banco, temas["REGRA_PENDENTE"]["id"])["recomendacao"] == "VALIDAR_REGRA"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Aprovar o lote
# ═══════════════════════════════════════════════════════════════════════════


def _vigente(banco: _Banco) -> dict:
    return next(v for v in banco.tabelas["cm_memoria_versao"] if v["vigente"])


class TestOLote:
    def test_aprovar_o_lote_aplica_todas_as_recomendacoes_pelo_caminho_de_decisao(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        recomendar_abertos(banco)

        resposta = _aprovar(banco, [t["id"] for t in temas.values()])

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["falhas"] == []
        gravados = {tipo: _tema_no_banco(banco, t["id"]) for tipo, t in temas.items()}
        assert {tipo: (t["estado"], t["decisao"], t["decidido_por"]) for tipo, t in gravados.items()} == {
            "REGRA_PENDENTE": ("DECIDIDO", "VALIDAR_REGRA", "G1"),
            "BLOQUEADO": ("DECIDIDO", "DESCARTAR", "G1"),
            "OBSERVACAO": ("DECIDIDO", "RESPONDER", "G1"),
        }
        # A regra validada: vigente numa versão nova da memória, como pelo cartão.
        vigente = _vigente(banco)
        assert vigente["versao"] == "1.1"
        regra = next(
            r
            for r in banco.tabelas["cm_regra"]
            if r["memoria_versao_id"] == vigente["id"] and r["codigo"] == REGRA_PENDENTE
        )
        assert (regra["status"], regra["texto"], regra["validado_por"]) == ("VIGENTE", TEXTO_PENDENTE, "G1")
        # A resposta ao time aparece no Guia da conta que levantou a questão.
        [recado] = _guia(banco, C2)["respostas"]
        assert recado["resposta"] == RESPOSTA_AO_TIME
        assert _fila_de_validacao(banco)["temas"] == []

    def test_corrigir_um_tema_aplica_a_correcao_so_nele_e_o_resto_segue_a_recomendacao(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        recomendar_abertos(banco)

        corrigido = _decidir(banco, temas["REGRA_PENDENTE"]["id"], {"decisao": "DEIXAR_PENDENTE"})
        assert corrigido.status_code == 200, corrigido.text
        resposta = _aprovar(banco, [t["id"] for t in temas.values()])

        assert resposta.status_code == 200, resposta.text
        assert _tema_no_banco(banco, temas["REGRA_PENDENTE"]["id"])["decisao"] == "DEIXAR_PENDENTE"
        assert [v["versao"] for v in banco.tabelas["cm_memoria_versao"]] == ["1.0"]
        assert {
            (linha["acao"], linha["estado"])
            for linha in banco.tabelas["cm_guia_linha"]
            if linha["codigo"] == "70000010"
        } == {("VALIDAR", "ABERTA")}
        assert _tema_no_banco(banco, temas["BLOQUEADO"]["id"])["decisao"] == "DESCARTAR"
        assert _tema_no_banco(banco, temas["OBSERVACAO"]["id"])["decisao"] == "RESPONDER"

    def test_conta_concluida_afetada_vai_para_retorno_so_com_as_linhas_que_mudaram(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        recomendar_abertos(banco)

        assert _aprovar(banco, [temas["REGRA_PENDENTE"]["id"]]).status_code == 200

        assert {c["id"]: c["situacao"] for c in banco.tabelas["cm_conta"]} == {
            C1: "EM_CORRECAO",
            C2: "A_FAZER",
            C3: "RETORNO",
        }
        linhas = _linhas_do_guia(_guia(banco, C3))
        assert [(linha["codigo"], linha["acao"], linha["estado"]) for linha in linhas] == [
            ("70000010", "INCLUIR", "DECIDIDA")
        ]

    def test_tema_sem_recomendacao_fica_na_fila(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)

        resposta = _aprovar(banco, [t["id"] for t in temas.values()])

        assert resposta.status_code == 200, resposta.text
        assert {t["estado"] for t in banco.tabelas["cm_validacao_tema"]} == {"ABERTO"}

    def test_enviar_ao_cadastro_aprovado_no_lote_deixa_a_lista_para_baixar(self, provedor):
        banco = _cenario()
        temas = _tres_temas(banco)
        provedor.recomendacoes[f"Código {CATETER} bloqueado"] = {
            "decisao": "ENVIAR_AO_CADASTRO",
            "motivo": "O código não está no cadastro do MV.",
            "texto": "",
        }
        recomendar_abertos(banco)
        bloqueado = temas["BLOQUEADO"]["id"]

        resposta = _aprovar(banco, [bloqueado])

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["cadastro"] == [bloqueado]
        lista = _cliente(banco).get(f"/api/contas-medicas/validacao/temas/{bloqueado}/cadastro")
        assert lista.status_code == 200, lista.text
        assert lista.content.decode("utf-8-sig").splitlines()[1].startswith(f"{CATETER};")
        # Só o tema mandado ao cadastro tem lista.
        outro = _cliente(banco).get(f"/api/contas-medicas/validacao/temas/{temas['OBSERVACAO']['id']}/cadastro")
        assert outro.status_code == 409

    @pytest.mark.parametrize("quem", ["faturista", "coordenadora"])
    def test_so_quem_decide_validacao_aprova_o_lote(self, provedor, quem):
        banco = _cenario()
        temas = _tres_temas(banco)
        recomendar_abertos(banco)

        resposta = _aprovar(banco, [t["id"] for t in temas.values()], quem)

        assert resposta.status_code == 403
        assert {t["estado"] for t in banco.tabelas["cm_validacao_tema"]} == {"ABERTO"}
        lista = _cliente(banco, quem).get(f"/api/contas-medicas/validacao/temas/{temas['BLOQUEADO']['id']}/cadastro")
        assert lista.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# 3. O relógio e o kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════


def test_o_auditor_recomenda_a_fila_pelo_relogio_do_backend():
    from app.cron import scheduler as cron

    try:
        cron.start_scheduler()
        job = cron.scheduler.get_job("validacao_decidida_contas_medicas")
        assert job is not None
        assert job.func is cron.recomendar_validacao_contas_medicas
    finally:
        cron.stop_scheduler()


def test_o_job_recomenda_os_temas_abertos(monkeypatch, provedor):
    from app.cron import scheduler as cron

    banco = _cenario()
    _tres_temas(banco)
    monkeypatch.setattr(cron, "_supabase", lambda: banco)

    cron.recomendar_validacao_contas_medicas()

    assert {t["recomendacao"] for t in banco.tabelas["cm_validacao_tema"]} == {
        "VALIDAR_REGRA",
        "DESCARTAR",
        "RESPONDER",
    }


def test_a_migration_126_tem_as_colunas_da_recomendacao():
    """Piso do dublê: as colunas que o serviço grava existem na migration."""
    sql = MIGRATION_126.read_text(encoding="utf-8")
    for coluna in ("recomendacao", "recomendacao_motivo", "recomendacao_prova_id", "recomendado_em"):
        assert f"ADD COLUMN IF NOT EXISTS {coluna} " in sql, coluna


def test_o_kit_diz_que_a_fila_chega_decidida_e_e_aprovada_em_lote():
    validacao = KIT.read_text(encoding="utf-8").split("## A Validação")[1].split("\n## ")[0]

    for trecho in (
        "recomendação do Auditor",
        "Aprovar o lote",
        "Prova da regra",
        "corrigir",
    ):
        assert trecho in validacao, trecho


ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/validacao_decidida.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_recomendacao.md",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto


def test_o_motivo_do_auditor_sai_sem_travessao(provedor):
    banco = _cenario()
    temas = _tres_temas(banco)
    provedor.recomendacoes[f"Código {CATETER} bloqueado"] = {
        "decisao": "DESCARTAR",
        "motivo": f"O cateter {chr(0x2014)} o duplo {chr(0x2013)} já tem código.",
        "texto": "",
    }

    recomendar_abertos(banco)

    motivo = next(t for t in _fila_de_validacao(banco)["temas"] if t["id"] == temas["BLOQUEADO"]["id"])
    assert motivo["recomendacao"]["motivo"] == "O cateter, o duplo, já tem código."
