"""O Passo B de Contas médicas: a comparação com a memória e a conferência das
linhas da IA (issue #1135, PRD #1128, ADR 0070).

A IA compara os eventos do prontuário com a conta, aplicando a memória da
operadora, e devolve linhas do Guia sem valor em reais. Nenhuma delas chega à
faturista sem as conferências do código: regra existe, regra vigente, evidência
na página, código na tabela, teto recalculado, sem repetir o que o código já
apontou e dentro do período.

Tudo pelo caminho de verdade, com os dublês do processamento (#1124): a rota de
envio, o job da fila, o adaptador de IA com o transporte HTTP trocado e a rota
do Guia. O provedor responde pelo schema pedido: o Passo A devolve eventos, o
Passo B devolve as linhas que cada teste escolhe.
"""

from __future__ import annotations

from typing import Any

from test_contas_medicas_processamento import (  # noqa: F401 (fixtures autouse do processamento)
    PARAMETROS,
    _Banco,
    _cenario,
    _conta,
    _enviar,
    _guia,
    _item_de_tabela,
    _linhas_do_guia,
    _prontuario,
    _regra,
    _reset_rate_limiter,
    _rodar_o_job,
    extrator,
    openrouter,
)

# A página 2 do prontuário sintético (admissão no CTI) diz isto, palavra por palavra.
TRECHO_DA_ADMISSAO = "Chegou com acesso venoso periférico em membro superior esquerdo"


def _cenario_do_passo_b() -> _Banco:
    """O par sintético do processamento, com a tabela de materiais do equipo."""
    banco = _cenario()
    banco.tabelas["cm_regra"].append(_regra("ALFA-INS-03"))
    banco.tabelas["cm_tabela_preco_item"].append(
        _item_de_tabela("it-equipo", "tb-mat", "70000002", "EQUIPO MACROGOTAS", {"comum": 12.5, "carioca": 13.0}, {})
    )
    return banco


def _linha_da_ia(**campos: Any) -> dict[str, Any]:
    """Uma linha no formato do Anexo B: a boa, com o que o teste trocar."""
    return {
        "acao": "INCLUIR",
        "data": "2026-10-03",
        "data_fim": "2026-10-03",
        "setor": "CTI ADULTO",
        "codigo": "70000002",
        "descricao": "EQUIPO MACROGOTAS",
        "quantidade_lancada": 0,
        "quantidade_devida": 1,
        "regra_id": "ALFA-INS-03",
        "motivo": "Acesso venoso periférico na admissão e sem equipo na conta.",
        "evidencia": {"pagina": 2, "trecho": TRECHO_DA_ADMISSAO},
        "nivel_evidencia": "REGISTRADO",
        "causa_raiz": "DISPENSACAO",
        "confianca": "ALTA",
        **campos,
    }


def _analisar(banco: _Banco, openrouter, *linhas: dict[str, Any]) -> tuple[dict, list[dict]]:
    """Envia o par, roda a fila com o Passo B respondendo `linhas` e devolve a
    conta gravada e as linhas do Guia pela rota."""
    openrouter.comparacao = {"linhas": list(linhas), "resumo": "Conta comparada com a memória."}
    _enviar(banco, _conta(), _prontuario())
    _rodar_o_job(banco)
    (conta,) = banco.tabelas["cm_conta"]
    assert conta["situacao"] == "A_FAZER", conta.get("erro_motivo")
    return conta, _linhas_do_guia(_guia(banco, conta["id"]))


class TestConferenciaDasLinhasDaIA:
    def test_a_linha_boa_entra_no_guia_com_origem_ia_e_o_valor_pela_tabela(self, openrouter):
        _, linhas = _analisar(_cenario_do_passo_b(), openrouter, _linha_da_ia())

        (equipo,) = [linha for linha in linhas if linha["codigo"] == "70000002"]
        assert (equipo["origem"], equipo["acao"], equipo["regra_codigo"]) == ("IA", "INCLUIR", "ALFA-INS-03")
        assert (equipo["preco_tabela"], equipo["valor_diferenca"], equipo["confianca"]) == (12.5, 12.5, "ALTA")
        assert {linha["origem"] for linha in linhas if linha["codigo"] != "70000002"} == {"CODIGO"}
