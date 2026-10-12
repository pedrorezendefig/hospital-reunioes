"""Conferências por código e montagem do Guia (issue #1122, PRD #1113, ADR 0070).

Os cinco achados do diretor nas contas reais dele (adendo v1.3, item 9.1) viram
fixtures sintéticas: a conta lida, o prontuário lido e a memória entram como o
resto do Motor os entrega, e cada teste asserta a linha do Guia inteira (ação,
código, quantidades, valor, regra, nível, causa-raiz), não só a presença.

A operadora ALFA é sintética. O ID de cada regra vem da própria memória, no
bloco `regras_das_conferencias` do cabeçalho: a numeração muda de operadora para
operadora (a prescrição plena é ASSIM-PRI-07 e LEVE-PRI-02).
"""

from __future__ import annotations

import os
import sys
from datetime import date
from decimal import Decimal
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.contas_medicas.conferencia import ProntuarioLido, conferir  # noqa: E402
from app.services.contas_medicas.conteudo import Conteudo, Internacao  # noqa: E402
from app.services.contas_medicas.memoria import MemoriaLida, RegraLida  # noqa: E402
from app.services.contas_medicas.prescricao import consolidar  # noqa: E402
from app.services.contas_medicas.prontuario import Prontuario  # noqa: E402
from app.services.contas_medicas.tabelas import NAO_CONFERIDO  # noqa: E402
from app.services.contas_medicas_conta import Conta, ItemConta  # noqa: E402

CENTAVO = Decimal("0.01")


def dia(n: int) -> date:
    return date(2026, 10, n)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures sintéticas
# ═══════════════════════════════════════════════════════════════════════════

REGRAS_DAS_CONFERENCIAS = {
    "preco": "ALFA-PRC-02",
    "coluna_do_plano": "ALFA-PRC-01",
    "diaria": "ALFA-DIA-01",
    "acompanhante": "ALFA-DIA-10",
    "prescricao": "ALFA-PRI-07",
    "sem_registro": "ALFA-PRI-06",
    "ficha_anestesica": "ALFA-CC-07",
    "gas": "ALFA-CC-04",
    "procedimento_do_cabecalho": "ALFA-PRI-12",
    "teto": "ALFA-INS-33",
}

PARAMETROS_ALFA: dict[str, Any] = {
    "operadora": "ALFA",
    "colunas_de_preco": {"padrao": "COMUM", "CARIOCA": ["Alfa Max Qc"]},
    "diaria": {
        "hora_vencimento": "10:00",
        "limite_madrugada": "05:00",
        "diaria_extra_na_origem_apos_vencimento": ["TRANSFERENCIA_DE_SETOR", "OBITO"],
        "codigos": {"cti": "60001038", "enfermaria": "60000805", "apartamento": "60000651", "acompanhante": "60000473"},
    },
    "tetos_por_dia": {
        "luva_procedimento": {"codigo": "70802726", "enfermaria": 20, "cti": 60, "centro_cirurgico_por_cirurgia": 6},
    },
    "gases_centro_cirurgico": {"3": "60010851", "6": "60011092", "9": None},
    "regras_das_conferencias": REGRAS_DAS_CONFERENCIAS,
}


def _memoria(parametros: dict[str, Any] | None = None, *, pendentes: tuple[str, ...] = ()) -> MemoriaLida:
    parametros = PARAMETROS_ALFA if parametros is None else parametros
    ids = set(REGRAS_DAS_CONFERENCIAS.values()) | set((parametros.get("regras_das_conferencias") or {}).values())
    regras = tuple(
        RegraLida(
            codigo=codigo,
            secao=codigo.split("-")[1],
            texto=f"Regra sintética {codigo}.",
            tipo="CONTRATUAL",
            origem="PRÁTICA",
            status="PENDENTE" if codigo in pendentes else "VIGENTE",
            validado_em=None,
        )
        for codigo in sorted(ids)
    )
    return MemoriaLida(
        sigla=str(parametros.get("operadora", "ALFA")),
        nome="Alfa Saúde",
        versao="1.0",
        situacao="PARCIAL",
        parametros=parametros,
        regras=regras,
    )


def _tabela(precos: dict[tuple[str, str], Any]):
    """A busca de preço como a conferência recebe: (categoria, código, data, coluna).

    O valor do dicionário é um preço, `PACOTE`, ou `{coluna: preço}`.
    """

    def preco(categoria: str, codigo: str, data: date, coluna: str | None = None):
        valor = precos.get((categoria, codigo), NAO_CONFERIDO)
        if isinstance(valor, dict):
            valor = valor.get(coluna, NAO_CONFERIDO)
        return Decimal(str(valor)) if isinstance(valor, int | float) else valor

    return preco


def _item(
    codigo: str,
    descricao: str,
    data: date,
    quantidade: float,
    unitario: float,
    *,
    grupo: str = "MEDICAMENTOS",
    setor: str = "CTI ADULTO",
    pagina: int = 2,
    unidade: str = "UN",
) -> ItemConta:
    q, u = Decimal(str(quantidade)), Decimal(str(unitario))
    return ItemConta(
        pagina=pagina,
        data=data,
        codigo=codigo,
        descricao=descricao,
        unidade=unidade,
        percentual=Decimal("100.00"),
        quantidade=q,
        unitario=u,
        total=(q * u).quantize(CENTAVO),
        grupo=grupo,
        setor_codigo="1",
        setor=setor,
        grupo_procedimento=None,
    )


def _conta(
    *itens: ItemConta,
    plano: str = "Alfa Basico",
    inicio: date = dia(1),
    fim: date = dia(6),
    procedimento: str | None = None,
    acomodacao: str | None = "ENFERMARIA",
) -> Conta:
    return Conta(
        atendimento="31245",
        conta="48811",
        tipo="Parcial",
        internacao=None,
        alta=None,
        periodo_inicio=inicio,
        periodo_fim=fim,
        acomodacao=acomodacao,
        procedimento_codigo=procedimento,
        procedimento_descricao="PROCEDIMENTO SINTETICO" if procedimento else None,
        plano=plano,
        guia=None,
        total=sum((i.total for i in itens), Decimal("0.00")),
        itens=tuple(itens),
    )


def _prontuario(
    *,
    prescricoes=(),
    fichas=(),
    descricoes=(),
    movimentacoes=(),
    documentos=(),
    textos: tuple[str, ...] = ("",),
    tipo_impressao: str | None = "Completa",
    idade: int | None = None,
) -> ProntuarioLido:
    estrutura = Prontuario(
        atendimento="31245",
        total_paginas=len(textos),
        tipo_impressao=tipo_impressao,
        grupos_da_capa={},
        paciente_rotulo=None,
        idade_anos=idade,
        documentos=tuple(documentos),
        paginas_sem_texto=(),
        parecer_parcial=(),
    )
    conteudo = Conteudo(
        internacao=Internacao(None, None, None, None, None),
        movimentacoes=tuple(movimentacoes),
        setor_por_dia={},
        prescricoes=tuple(prescricoes),
        prescricao_consolidada=tuple(consolidar(prescricoes)),
        exames_pedidos=(),
        balancos=(),
        glicemias=(),
        descricoes_cirurgicas=tuple(descricoes),
        fichas_anestesicas=tuple(fichas),
        guias_tiss=(),
    )
    return ProntuarioLido(estrutura=estrutura, conteudo=conteudo, texto_por_pagina=textos)


def _campos(linha: dict) -> dict:
    """A linha sem `ordem` (depende das outras linhas), `motivo` e `evidencia_trecho` (texto livre)."""
    return {k: v for k, v in linha.items() if k not in {"ordem", "motivo", "evidencia_trecho"}}


def _linhas(resultado, acao: str, codigo: str | None = None) -> list[dict]:
    return [linha for linha in resultado.linhas if linha["acao"] == acao and (codigo is None or linha["codigo"] == codigo)]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Os cinco achados do diretor
# ═══════════════════════════════════════════════════════════════════════════

AGULHA = "70000017"


class TestAchadosDoDiretor:
    def test_agulha_lancada_a_0_17_com_tabela_0_20_vira_corrigir_preco_de_0_06(self):
        conta = _conta(
            _item(AGULHA, "AGULHA DESC 25X7", dia(4), 2, 0.17, grupo="MATERIAIS DESCARTAVEIS", setor="CENTRO CIRURGICO", pagina=5)
        )
        preco = _tabela({("MATERIAL", AGULHA): {"COMUM": 0.20, "CARIOCA": 0.18}})

        resultado = conferir(conta, _prontuario(tipo_impressao=None), _memoria(), preco)

        [linha] = _linhas(resultado, "CORRIGIR_PRECO", AGULHA)
        assert _campos(linha) == {
            "acao": "CORRIGIR_PRECO",
            "data": "2026-10-04",
            "data_fim": None,
            "setor": "CENTRO CIRURGICO",
            "codigo": AGULHA,
            "descricao": "AGULHA DESC 25X7",
            "quantidade_lancada": 2.0,
            "quantidade_devida": 2.0,
            "preco_lancado": 0.17,
            "preco_tabela": 0.20,
            "valor_diferenca": 0.06,
            "regra_codigo": "ALFA-PRC-02",
            "evidencia_pagina": 5,
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "CADASTRO_PRECO",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
