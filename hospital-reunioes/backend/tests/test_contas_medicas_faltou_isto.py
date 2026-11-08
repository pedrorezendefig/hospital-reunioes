"""O Faltou isto no Guia, a conversa da Conta e o pedido para a Tecnologia
(issue #1489, PRD #1484, ADR 0081, decisão 4).

Quem vê o Guia aponta, num dia da Conta, o item e a página que o módulo não
achou. O Auditor recebe os eventos e as páginas daquele dia, explica por que
não achou e classifica a origem: REGRA, LEITURA ou DEFEITO. Com LEITURA ou
DEFEITO e o ok de quem apontou, o backend abre a issue no GitHub, num
repositório público: o corpo nunca leva valor lido da capa.

Tudo pelo caminho de verdade, com os dublês do processamento (#1124): a rota de
envio e o job da fila fazem a Conta com o Guia pronto a partir do par
sintético (a capa da paciente fictícia ANTÔNIA MELO FARIAS), o adaptador de IA
tem o transporte HTTP trocado e o cliente do GitHub é trocado na porta
`criar_issue`.
"""

from __future__ import annotations

import json
import re
from typing import Any

import pytest
from anthropic_apoio import cliente_por_transporte, nomear_schemas
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_contas_medicas_auditor_schema import MIGRATION_126, _colunas, _valores_do_check
from test_contas_medicas_processamento import (
    EVENTOS_DA_IA,
    PASSO_A,
    PASSO_B,
    _Banco,
    _cenario,
    _conta,
    _enviar,
    _Extrator,
    _ExtratorDePalavras,
    _IAFalsa,
    _pessoa,
    _prontuario,
    _rodar_o_job,
)
from test_contas_medicas_prontuario import VALORES_PESSOAIS, aparece

from app.config import settings
from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_envio as envio_router
from app.routers import contas_medicas_guia as guia_router
from app.services import github_client
from app.services.contas_medicas import envio as envio_service
from app.services.contas_medicas import ia, processamento

DIAGNOSTICO = "DiagnosticoDoFaltouIsto"

# A página 2 do prontuário sintético (admissão no CTI) diz isto, palavra por palavra.
TRECHO_DA_ADMISSAO = "Chegou com acesso venoso periférico em membro superior esquerdo"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _extrator(monkeypatch) -> _Extrator:
    duble = _Extrator()
    monkeypatch.setattr(envio_service, "extrair_paginas", duble)
    monkeypatch.setattr(processamento, "extrair_paginas", duble)
    monkeypatch.setattr(processamento, "extrair_palavras", _ExtratorDePalavras())
    return duble


@pytest.fixture(autouse=True)
def ia_falsa(monkeypatch) -> _IAFalsa:
    """O provedor do teste na fronteira HTTP: nada chega à Anthropic. O Passo A
    lê o acesso periférico na página 2, em 03/10."""
    duble = _IAFalsa()
    duble.nomes = nomear_schemas(monkeypatch)
    duble.eventos = {
        **EVENTOS_DA_IA,
        "terapias": [
            {
                "tipo": "ACESSO_PERIFERICO",
                "descricao": "Acesso venoso periférico em MSE",
                "setor": "CTI ADULTO",
                "inicio": "2026-10-03",
                "fim": "",
                "pagina": 2,
                "trecho": TRECHO_DA_ADMISSAO,
            }
        ],
    }
    duble.respostas[DIAGNOSTICO] = {
        "classificacao": "DEFEITO",
        "explicacao": "O acesso periférico está no evento da página 2, mas o Guia não pediu o equipo.",
        "esperado": "Incluir 1 equipo macrogotas em 03/10, pelo acesso periférico da admissão.",
    }
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


# ═══════════════════════════════════════════════════════════════════════════
# O cenário: a Conta com o Guia pronto, aberta pela faturista
# ═══════════════════════════════════════════════════════════════════════════

PESSOAS = {
    "faturista": _pessoa("F1", "faturista"),
    "outra_faturista": _pessoa("F2", "faturista"),
    "coordenadora": _pessoa("CO", "coordenadora"),
    "gestao": _pessoa("G1", "gestao_contas_medicas"),
    "diretoria_medica": _pessoa("DM", "diretoria_medica"),
    "diretoria_executiva": _pessoa("DE", "diretoria_executiva"),
    "credenciamento": _pessoa("CR", "credenciamento"),
}


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


def _conta_no_guia() -> tuple[_Banco, str]:
    """O par sintético enviado e analisado; a faturista F1 abre o Guia e puxa a Conta."""
    banco = _cenario()
    banco.tabelas["participantes"] = list(PESSOAS.values())
    _enviar(banco, _conta(), _prontuario())
    _rodar_o_job(banco)
    (conta,) = banco.tabelas["cm_conta"]
    assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
    aberta = _cliente(banco).get(f"/api/contas-medicas/contas/{conta['id']}/guia")
    assert aberta.status_code == 200, aberta.text
    return banco, conta["id"]


def _rota(conta_id: str) -> str:
    return f"/api/contas-medicas/contas/{conta_id}/guia/faltou-isto"


APONTAMENTO = {
    "data": "2026-10-03",
    "item": "Equipo macrogotas",
    "pagina": 2,
    "texto": "Por que você não achou o equipo nesta página?",
}


def _apontar(banco: _Banco, conta_id: str, quem: str = "faturista", **campos) -> Any:
    return _cliente(banco, quem).post(_rota(conta_id), json={**APONTAMENTO, **campos})


# ═══════════════════════════════════════════════════════════════════════════
# 1. O apontamento e a conversa da Conta
# ═══════════════════════════════════════════════════════════════════════════


class TestApontamento:
    def test_grava_item_pagina_texto_origem_pessoa_e_a_classificacao_do_auditor(self):
        banco, conta_id = _conta_no_guia()

        resposta = _apontar(banco, conta_id)

        assert resposta.status_code == 200, resposta.text
        (gravado,) = banco.tabelas["cm_faltou_isto"]
        assert {chave: gravado[chave] for chave in ("conta_id", "data", "item", "pagina", "texto", "origem")} == {
            "conta_id": conta_id,
            "data": "2026-10-03",
            "item": "Equipo macrogotas",
            "pagina": 2,
            "texto": "Por que você não achou o equipo nesta página?",
            "origem": "PESSOA",
        }
        assert gravado["apontado_por"] == "F1"
        assert gravado["classificacao"] == "DEFEITO"
        assert gravado["explicacao"] == (
            "O acesso periférico está no evento da página 2, mas o Guia não pediu o equipo.\n\n"
            "O Guia deveria ter apontado: Incluir 1 equipo macrogotas em 03/10, pelo acesso periférico da admissão."
        )
        assert gravado["classificado_em"]
        assert resposta.json()["apontamento"]["classificacao"] == "DEFEITO"

    def test_abre_a_conversa_da_conta_com_a_fala_de_quem_apontou_e_a_do_auditor(self):
        banco, conta_id = _conta_no_guia()

        _apontar(banco, conta_id)
        _apontar(banco, conta_id, data="2026-10-04", item="Fralda geriátrica", pagina=None, texto=None)

        (conversa,) = banco.tabelas["cm_conversa"]
        assert (conversa["contexto"], conversa["conta_id"], conversa["operadora_id"]) == ("CONTA", conta_id, "op-alfa")
        falas = [(m["autor"], m.get("autor_id"), m["texto"]) for m in banco.tabelas["cm_conversa_mensagem"]]
        explicacao = banco.tabelas["cm_faltou_isto"][0]["explicacao"]
        assert falas == [
            (
                "PESSOA",
                "F1",
                "Faltou isto em 03/10, página 2: Equipo macrogotas. Por que você não achou o equipo nesta página?",
            ),
            ("AUDITOR", None, explicacao),
            ("PESSOA", "F1", "Faltou isto em 04/10: Fralda geriátrica."),
            ("AUDITOR", None, explicacao),
        ]
        assert {f["conversa_id"] for f in banco.tabelas["cm_faltou_isto"]} == {conversa["id"]}

    def test_o_auditor_recebe_os_eventos_e_as_paginas_daquele_dia(self, ia_falsa):
        banco, conta_id = _conta_no_guia()

        _apontar(banco, conta_id)

        (corpo,) = [c for c in ia_falsa.corpos if c["formato"] == DIAGNOSTICO]
        conteudo = "\n".join(bloco["text"] for bloco in corpo["messages"][0]["content"])
        dia = json.loads(conteudo.split("O DIA NA CONTA\n", 1)[1].split("\nO QUE FALTOU\n", 1)[0])
        (acesso,) = dia["eventos_do_dia"]["terapias"]
        assert (acesso["pagina"], acesso["trecho"]) == (2, TRECHO_DA_ADMISSAO)
        assert dia["documentos_do_dia"] != []
        assert {d["data"] for d in dia["documentos_do_dia"]} == {"2026-10-03"}
        assert "Página do prontuário: 2" in conteudo
        assert "MEMÓRIA DA OPERADORA" in conteudo

    def test_a_chamada_do_auditor_fica_gravada_no_passo_conversa(self):
        banco, conta_id = _conta_no_guia()
        antes = len(banco.tabelas["cm_chamada_ia"])

        _apontar(banco, conta_id)

        (chamada,) = banco.tabelas["cm_chamada_ia"][antes:]
        assert (chamada["passo"], chamada["conta_id"], chamada["sucesso"]) == ("CONVERSA", conta_id, True)
        assert "CONVERSA" in _passos_da_chamada()

    def test_o_que_grava_cabe_nas_colunas_e_nos_checks_da_migration_126(self):
        banco, conta_id = _conta_no_guia()

        _apontar(banco, conta_id)

        for tabela in ("cm_conversa", "cm_conversa_mensagem", "cm_faltou_isto"):
            for linha in banco.tabelas[tabela]:
                assert set(linha) <= _colunas(tabela) | {"id", "criado_em"}, tabela
        (gravado,) = banco.tabelas["cm_faltou_isto"]
        assert gravado["origem"] in _valores_do_check("cm_faltou_isto", "origem")
        assert gravado["classificacao"] in _valores_do_check("cm_faltou_isto", "classificacao")
        autores = {m["autor"] for m in banco.tabelas["cm_conversa_mensagem"]}
        assert autores <= _valores_do_check("cm_conversa_mensagem", "autor")

    def test_auditor_fora_do_ar_responde_503_e_nada_fica_gravado(self, ia_falsa):
        banco, conta_id = _conta_no_guia()
        ia_falsa.fora_do_formato_em = {DIAGNOSTICO}

        resposta = _apontar(banco, conta_id)

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == (
            "O Auditor não respondeu agora. Nada foi gravado: tente de novo em alguns minutos."
        )
        assert banco.tabelas.get("cm_faltou_isto", []) == []
        assert banco.tabelas.get("cm_conversa_mensagem", []) == []


class TestQuemAponta:
    @pytest.mark.parametrize("quem", ["faturista", "coordenadora", "gestao", "diretoria_medica", "diretoria_executiva"])
    def test_quem_ve_o_guia_aponta_faltou_isto(self, quem):
        banco, conta_id = _conta_no_guia()

        resposta = _apontar(banco, conta_id, quem)

        assert resposta.status_code == 200, resposta.text
        (gravado,) = banco.tabelas["cm_faltou_isto"]
        assert gravado["apontado_por"] == PESSOAS[quem]["id"]

    @pytest.mark.parametrize("quem", ["outra_faturista", "credenciamento"])
    def test_quem_nao_ve_o_guia_desta_conta_nao_aponta(self, quem):
        banco, conta_id = _conta_no_guia()

        resposta = _apontar(banco, conta_id, quem)

        assert resposta.status_code == 403
        assert banco.tabelas.get("cm_faltou_isto", []) == []

    def test_aponta_num_dia_do_periodo_sem_linha_no_guia(self):
        banco, conta_id = _conta_no_guia()
        (conta,) = banco.tabelas["cm_conta"]
        dias_com_linha = {linha["data"] for linha in banco.tabelas["cm_guia_linha"]}
        assert "2026-10-02" not in dias_com_linha and conta["periodo_inicio"] == "2026-10-02"

        resposta = _apontar(banco, conta_id, data="2026-10-02")

        assert resposta.status_code == 200, resposta.text
        assert banco.tabelas["cm_faltou_isto"][0]["data"] == "2026-10-02"

    def test_dia_fora_do_periodo_da_conta_e_recusado(self):
        banco, conta_id = _conta_no_guia()

        resposta = _apontar(banco, conta_id, data="2026-10-09")

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == "Escolha um dia do período da conta, de 02/10 a 06/10."
        assert banco.tabelas.get("cm_faltou_isto", []) == []

    def test_aponta_na_conta_concluida(self):
        banco, conta_id = _conta_no_guia()
        concluida = _cliente(banco).post(f"/api/contas-medicas/contas/{conta_id}/guia/concluir", json={})
        assert concluida.status_code == 200, concluida.text

        resposta = _apontar(banco, conta_id)

        assert resposta.status_code == 200, resposta.text


# ═══════════════════════════════════════════════════════════════════════════
# 2. O pedido para a Tecnologia
# ═══════════════════════════════════════════════════════════════════════════


class _GithubFalso:
    """A porta `criar_issue` do cliente do GitHub: guarda cada issue pedida."""

    def __init__(self):
        self.issues: list[dict[str, Any]] = []
        self.falha: Exception | None = None

    def __call__(self, *, titulo: str, corpo: str, labels: list[str], assignees=None) -> dict[str, Any]:
        if self.falha is not None:
            raise self.falha
        self.issues.append({"titulo": titulo, "corpo": corpo, "labels": labels, "assignees": assignees})
        return {"number": 4321, "html_url": "https://github.com/exemplo/repo/issues/4321"}


@pytest.fixture(autouse=True)
def github(monkeypatch) -> _GithubFalso:
    duble = _GithubFalso()
    monkeypatch.setattr(github_client, "criar_issue", duble)
    monkeypatch.setattr(github_client, "integracao_configurada", lambda: True)
    return duble


def _pedido(banco: _Banco, conta_id: str, faltou_id: str, quem: str = "faturista") -> Any:
    return _cliente(banco, quem).post(f"{_rota(conta_id)}/{faltou_id}/pedido")


def _apontado(banco: _Banco, conta_id: str, quem: str = "faturista", **campos) -> str:
    resposta = _apontar(banco, conta_id, quem, **campos)
    assert resposta.status_code == 200, resposta.text
    return resposta.json()["apontamento"]["id"]


class TestPedidoParaATecnologia:
    @pytest.mark.parametrize("classificacao", ["LEITURA", "DEFEITO"])
    def test_com_o_ok_de_quem_apontou_o_github_recebe_a_issue_pronta_para_o_agente(
        self, ia_falsa, github, classificacao
    ):
        ia_falsa.respostas[DIAGNOSTICO] = {**ia_falsa.respostas[DIAGNOSTICO], "classificacao": classificacao}
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)

        resposta = _pedido(banco, conta_id, faltou_id)

        assert resposta.status_code == 200, resposta.text
        (issue,) = github.issues
        assert "ready-for-agent" in issue["labels"]
        assert not issue["assignees"]
        corpo = issue["corpo"]
        criterios = corpo.split("## Critérios de aceite", 1)[1].split("\n## ", 1)[0]
        assert criterios.count("\n- [ ] ") >= 2
        assert "Incluir 1 equipo macrogotas em 03/10, pelo acesso periférico da admissão." in criterios
        assert f"- **Trecho da página (desidentificado):** {TRECHO_DA_ADMISSAO}" in corpo
        assert f"- **Código da Conta:** `{conta_id}`" in corpo
        assert "- **Página do prontuário:** 2" in corpo
        assert "- **Explicação do Auditor:** O acesso periférico está no evento da página 2" in corpo
        assert "- **Mensagem de quem apontou:** Por que você não achou o equipo nesta página?" in corpo
        assert f'<!-- auditor-contas-medicas faltou-isto="{faltou_id}" -->' in corpo
        (gravado,) = banco.tabelas["cm_faltou_isto"]
        assert gravado["issue_numero"] == 4321
        assert resposta.json()["apontamento"]["pedido_aberto"] is True

    def test_antes_do_ok_nada_vai_ao_github(self, github):
        banco, conta_id = _conta_no_guia()

        resposta = _apontar(banco, conta_id)

        assert github.issues == []
        assert resposta.json()["apontamento"]["pode_abrir_pedido"] is True
        assert banco.tabelas["cm_faltou_isto"][0].get("issue_numero") is None

    def test_falta_de_regra_nao_vira_pedido(self, ia_falsa, github):
        ia_falsa.respostas[DIAGNOSTICO] = {**ia_falsa.respostas[DIAGNOSTICO], "classificacao": "REGRA"}
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)

        resposta = _pedido(banco, conta_id, faltou_id)

        assert resposta.status_code == 409
        assert github.issues == []
        assert banco.tabelas["cm_faltou_isto"][0]["classificacao"] == "REGRA"

    def test_so_quem_apontou_da_o_ok(self, github):
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)

        resposta = _pedido(banco, conta_id, faltou_id, "gestao")

        assert resposta.status_code == 403
        assert github.issues == []

    def test_o_segundo_ok_nao_abre_outro_pedido(self, github):
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)
        assert _pedido(banco, conta_id, faltou_id).status_code == 200

        resposta = _pedido(banco, conta_id, faltou_id)

        assert resposta.status_code == 409
        assert len(github.issues) == 1

    def test_github_fora_do_ar_responde_502_e_o_ok_vale_de_novo(self, github):
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)
        github.falha = github_client.GithubIndisponivelError("GitHub respondeu 500")

        resposta = _pedido(banco, conta_id, faltou_id)

        assert resposta.status_code == 502
        assert banco.tabelas["cm_faltou_isto"][0].get("issue_numero") is None
        github.falha = None
        assert _pedido(banco, conta_id, faltou_id).status_code == 200

    def test_sem_a_integracao_configurada_responde_503(self, monkeypatch, github):
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id)
        monkeypatch.setattr(github_client, "integracao_configurada", lambda: False)

        resposta = _pedido(banco, conta_id, faltou_id)

        assert resposta.status_code == 503
        assert github.issues == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. A desidentificação do pedido: o repositório é público
# ═══════════════════════════════════════════════════════════════════════════

# O que a capa da Conta imprime e o app guarda (o cabeçalho da "Fatura
# Individual" do par sintético e o rótulo que a leitura tira da capa do
# prontuário), somado a cada valor da capa do prontuário que o teste de
# desidentificação do módulo já procura.
CAPA_DA_CONTA = {
    "número do atendimento": "31245",
    "número da conta": "48811",
    "guia": "123456789",
    "plano": "ALFA BASICO ENF",
    "data da internação": "02/10/2026",
    "rótulo da paciente": "Antônia F.",
}
VALORES_DA_CAPA = {**VALORES_PESSOAIS, **CAPA_DA_CONTA}

# Quem apontou escreve a identificação inteira, e o Auditor a repete: os dois
# textos chegam ao corpo da issue.
MENSAGEM_COM_A_CAPA = (
    "A paciente Antônia Melo Farias, filha de Josefa Ribeiro Costa, nascida em 14/03/1951, CPF 529.982.247-25, "
    "RG 20.481.337-6, carteira 0817734, telefone 98765-4321, atendimento 31245, conta 48811, guia 123456789, "
    "plano ALFA BASICO ENF, internada em 02/10/2026, rótulo Antônia F. O médico do CPF 111.444.777-35 prescreveu."
)
ITEM_COM_A_CAPA = "Equipo da ANTONIA MELO, carteira 0817734"


class TestDesidentificacao:
    def _pedido_com_a_capa(self, ia_falsa, github) -> tuple[_Banco, str]:
        ia_falsa.respostas[DIAGNOSTICO] = {
            "classificacao": "LEITURA",
            "explicacao": f"Sobre a mensagem: {MENSAGEM_COM_A_CAPA}",
            "esperado": "Incluir o equipo de ANTÔNIA MELO FARIAS, carteira 0817734, atendimento 31245.",
        }
        banco, conta_id = _conta_no_guia()
        faltou_id = _apontado(banco, conta_id, item=ITEM_COM_A_CAPA, texto=MENSAGEM_COM_A_CAPA)
        assert _pedido(banco, conta_id, faltou_id).status_code == 200
        return banco, conta_id

    def test_a_entrada_traz_cada_valor_da_capa(self, ia_falsa, github):
        """Guarda do teste de baixo: sem isto ele passaria sobre um texto que nunca teve o dado."""
        banco, _ = self._pedido_com_a_capa(ia_falsa, github)
        (gravado,) = banco.tabelas["cm_faltou_isto"]
        entrada = f"{gravado['item']}\n{gravado['texto']}\n{gravado['explicacao']}"

        assert [nome for nome, valor in VALORES_DA_CAPA.items() if not aparece(valor, entrada)] == []

    def test_nenhum_valor_lido_da_capa_aparece_no_corpo_nem_no_titulo_da_issue(self, ia_falsa, github):
        self._pedido_com_a_capa(ia_falsa, github)
        (issue,) = github.issues
        publico = f"{issue['titulo']}\n{issue['corpo']}"

        assert [nome for nome, valor in VALORES_DA_CAPA.items() if aparece(valor, publico)] == []
        # O dado sai como marcador, e o resto da mensagem fica legível.
        assert "carteira [NUMERO], telefone [TELEFONE], atendimento [NUMERO], conta [NUMERO]" in issue["corpo"]
        assert "prescreveu" in issue["corpo"]

    def test_o_que_vai_ao_auditor_tambem_sai_sem_a_capa(self, ia_falsa, github):
        self._pedido_com_a_capa(ia_falsa, github)
        (corpo,) = [c for c in ia_falsa.corpos if c["formato"] == DIAGNOSTICO]
        pergunta = corpo["messages"][0]["content"][-1]["text"]

        assert pergunta.startswith("O QUE FALTOU")
        assert [nome for nome, valor in VALORES_PESSOAIS.items() if aparece(valor, pergunta)] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. A conversa não é memória (ADR 0081, decisão 3)
# ═══════════════════════════════════════════════════════════════════════════

FALA_DA_PESSOA = "Pergunta só da conversa: e a bomba de seringa da madrugada?"
FALA_DO_AUDITOR = "Resposta só da conversa: a bomba de seringa ficou fora porque falta regra."


class TestConversaForaDaAnalise:
    def test_a_conversa_da_conta_nao_entra_no_prompt_do_passo_a_nem_do_passo_b(self, monkeypatch, ia_falsa):
        ia_falsa.respostas[DIAGNOSTICO] = {"classificacao": "REGRA", "explicacao": FALA_DO_AUDITOR, "esperado": ""}
        banco, conta_id = _conta_no_guia()
        assert _apontar(banco, conta_id, texto=FALA_DA_PESSOA).status_code == 200
        conversa = json.dumps(banco.tabelas["cm_conversa_mensagem"], ensure_ascii=False)
        assert FALA_DA_PESSOA in conversa and FALA_DO_AUDITOR in conversa

        # A conta volta para a análise, e o modelo novo do Passo A faz a IA ler o prontuário de novo.
        assert _cliente(banco, "gestao").post(f"/api/contas-medicas/contas/{conta_id}/reanalisar").status_code == 200
        monkeypatch.setattr(settings, "cm_ia_modelo_passo_a", "claude-opus-5-5")
        ia_falsa.corpos.clear()
        _rodar_o_job(banco)

        assert banco.conta(conta_id)["situacao"] == "A_FAZER"
        prompts = {
            passo: json.dumps([c["messages"] for c in ia_falsa.corpos if c["formato"] == passo], ensure_ascii=False)
            for passo in (PASSO_A, PASSO_B)
        }
        # Os dois passos rodaram, cada um com o que é dele.
        assert "Chegou com acesso venoso" in prompts[PASSO_A]
        assert "AGULHA HIPODERMICA" in prompts[PASSO_B]
        for passo, prompt in prompts.items():
            assert FALA_DA_PESSOA not in prompt, passo
            assert FALA_DO_AUDITOR not in prompt, passo
            assert "bomba de seringa" not in prompt, passo


def _passos_da_chamada() -> set[str]:
    sql = MIGRATION_126.read_text(encoding="utf-8")
    bloco = re.search(r"cm_chamada_ia_passo_check\s+CHECK \(passo IN \((.*?)\)\)", sql, flags=re.DOTALL)
    assert bloco, "a 126 nao refaz o CHECK do passo"
    return set(re.findall(r"'(\w+)'", bloco.group(1)))
