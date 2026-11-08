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

from typing import Any

import pytest
from anthropic_apoio import cliente_por_transporte, nomear_schemas
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_contas_medicas_auditor_schema import _colunas, _valores_do_check
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

from app.dependencies import get_current_user, get_supabase_client
from app.limiter import limiter
from app.routers import contas_medicas_envio as envio_router
from app.routers import contas_medicas_guia as guia_router
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
