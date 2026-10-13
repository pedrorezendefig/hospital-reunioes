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
from dataclasses import replace
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.contas_medicas.cirurgia import (  # noqa: E402
    DescricaoCirurgica,
    FichaAnestesica,
    Gas,
    MedicamentoDaFicha,
    Procedimento,
)
from app.services.contas_medicas.conferencia import Pacote, ProntuarioLido, conferir  # noqa: E402
from app.services.contas_medicas.conteudo import (  # noqa: E402
    Balanco,
    Conteudo,
    GlicemiasDoDia,
    Internacao,
    LinhaDoBalanco,
    Movimentacao,
)
from app.services.contas_medicas.memoria import MemoriaLida, RegraLida  # noqa: E402
from app.services.contas_medicas.prescricao import ExamePedido, ItemPrescrito, Prescricao, consolidar  # noqa: E402
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
    "exame": "ALFA-SAD-01",
    "glicemia": "ALFA-INS-18",
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
    exames=(),
    glicemias=(),
    balancos=(),
    textos: tuple[str, ...] = ("",),
    tipo_impressao: str | None = "Completa",
    idade: int | None = None,
    alta: datetime | None = None,
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
        internacao=Internacao(None, alta, None, None, None),
        movimentacoes=tuple(movimentacoes),
        setor_por_dia={},
        prescricoes=tuple(prescricoes),
        prescricao_consolidada=tuple(consolidar(prescricoes)),
        exames_pedidos=tuple(exames),
        balancos=tuple(balancos),
        glicemias=tuple(glicemias),
        descricoes_cirurgicas=tuple(descricoes),
        fichas_anestesicas=tuple(fichas),
        guias_tiss=(),
    )
    return ProntuarioLido(estrutura=estrutura, conteudo=conteudo, texto_por_pagina=textos)


def _prescrito(nome: str, pagina: int, *, colunas: str = "1 FA EV 24HS/24", doses: int | None = 1) -> ItemPrescrito:
    return ItemPrescrito(
        secao="MEDICAMENTOS",
        numero=1,
        nome=nome,
        generico=None,
        dose="1 FA",
        frequencia="24HS/24",
        via="EV",
        horarios=(),
        doses_por_dia=doses,
        se_necessario=False,
        suspenso=False,
        obs="",
        componentes=(),
        pedido=None,
        colunas=colunas,
        pagina=pagina,
    )


def _prescricao(data: date, *itens: ItemPrescrito, setor: str = "CTI ADULTO") -> Prescricao:
    return Prescricao(data, time(9, 0), "PRESCRICAO MEDICA", setor, tuple(i.pagina for i in itens), tuple(itens))


def _ficha(*, gases=(), medicamentos=(), data: date = dia(4)) -> FichaAnestesica:
    return FichaAnestesica(
        paginas=(20, 21),
        data=data,
        inicio=time(16, 50),
        fim=time(19, 20),
        tecnica="GERAL BALANCEADA",
        gases=tuple(gases),
        volatil=None,
        medicamentos=tuple(medicamentos),
        monitorizacao=(),
    )


def _campos(linha: dict) -> dict:
    """A linha sem `ordem` (depende das outras linhas), `motivo` e `evidencia_trecho` (texto livre)."""
    return {k: v for k, v in linha.items() if k not in {"ordem", "motivo", "evidencia_trecho"}}


def _linhas(resultado, acao: str, codigo: str | None = None) -> list[dict]:
    return [
        linha for linha in resultado.linhas if linha["acao"] == acao and (codigo is None or linha["codigo"] == codigo)
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 1. Os cinco achados do diretor
# ═══════════════════════════════════════════════════════════════════════════

AGULHA = "70000017"
PANTOCAL = "90123456"
TAZOCIN = "90654321"
O2_3L_CC = "60010851"
O2_6L_CC = "60011092"
CC = "CENTRO CIRURGICO"

# Materiais com preço diferente nas duas colunas da tabela.
MATERIAIS = [f"7010000{n}" for n in range(1, 6)]
TABELA_DE_MATERIAIS = {("MATERIAL", codigo): {"COMUM": 1.00, "CARIOCA": 0.85} for codigo in MATERIAIS}
# Na conta cirúrgica do diretor, a agulha estava no preço da coluna Carioca num plano Comum.
TABELA_DA_CIRURGIA = {**TABELA_DE_MATERIAIS, ("MATERIAL", AGULHA): {"COMUM": 0.20, "CARIOCA": 0.17}}


def _conta_cirurgica() -> Conta:
    """Plano Comum: a agulha no preço Carioca e outros 4 materiais no preço certo."""
    return _conta(
        _item(AGULHA, "AGULHA DESC 25X7", dia(4), 2, 0.17, grupo="MATERIAIS DESCARTAVEIS", setor=CC, pagina=5),
        *(
            _item(c, "MATERIAL SINTETICO", dia(4), 1, 1.00, grupo="MATERIAIS DESCARTAVEIS", setor=CC)
            for c in MATERIAIS[:4]
        ),
    )


class TestAchadosDoDiretor:
    def test_agulha_lancada_a_0_17_com_tabela_0_20_vira_corrigir_preco_de_0_06(self):
        resultado = conferir(
            _conta_cirurgica(), _prontuario(tipo_impressao=None), _memoria(), _tabela(TABELA_DA_CIRURGIA)
        )

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
        assert "coluna errada" in linha["motivo"]
        assert _linhas(resultado, "CORRIGIR_PRECO") == [linha]

    def test_pantoprazol_prescrito_em_6_dias_e_lancado_em_3_vira_incluir_718_95(self):
        # Medicamento sem Brasíndice carregado: a busca não confere, e o valor sai
        # do unitário que a própria conta já lançou (spec v1.0, item 9.5, passo 10).
        prescricoes = [_prescricao(dia(n), _prescrito("PANTOCAL 40MG FA", pagina=10 + n)) for n in range(1, 7)]
        conta = _conta(*(_item(PANTOCAL, "PANTOCAL 40 MG PO LIOF INJ FA", dia(n), 1, 239.65) for n in (1, 2, 3)))

        resultado = conferir(conta, _prontuario(prescricoes=prescricoes, textos=("PANTOCAL",)), _memoria(), _tabela({}))

        [linha] = _linhas(resultado, "INCLUIR", PANTOCAL)
        assert _campos(linha) == {
            "acao": "INCLUIR",
            "data": "2026-10-04",
            "data_fim": "2026-10-06",
            "setor": "CTI ADULTO",
            "codigo": PANTOCAL,
            "descricao": "PANTOCAL 40 MG PO LIOF INJ FA",
            "quantidade_lancada": 0.0,
            "quantidade_devida": 3.0,
            "preco_lancado": 239.65,
            "preco_tabela": None,
            "valor_diferenca": 718.95,
            "regra_codigo": "ALFA-PRI-07",
            "evidencia_pagina": 14,
            "nivel_evidencia": "PRESCRITO",
            "causa_raiz": "DISPENSACAO",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert "preço da conta, não conferido" in linha["motivo"]

    def test_piperacilina_lancada_sem_mencao_no_prontuario_vira_validar_com_sugestao_retirar(self):
        conta = _conta(
            _item(PANTOCAL, "PANTOCAL 40 MG PO LIOF INJ FA", dia(2), 1, 239.65),
            _item(TAZOCIN, "TAZOCIN 4,5 G PO LIOF INJ FA (PIPERACILINA+TAZOBACTAM)", dia(2), 1, 331.99, pagina=3),
        )
        textos = ("EVOLUÇÃO MÉDICA\nSegue com Pantocal 40 mg EV.", "Sem intercorrências.")

        resultado = conferir(conta, _prontuario(textos=textos), _memoria(), _tabela({}))

        [linha] = _linhas(resultado, "VALIDAR", TAZOCIN)
        assert _campos(linha) == {
            "acao": "VALIDAR",
            "data": "2026-10-02",
            "data_fim": None,
            "setor": "CTI ADULTO",
            "codigo": TAZOCIN,
            "descricao": "TAZOCIN 4,5 G PO LIOF INJ FA (PIPERACILINA+TAZOBACTAM)",
            "quantidade_lancada": 1.0,
            "quantidade_devida": 0.0,
            "preco_lancado": 331.99,
            "preco_tabela": None,
            "valor_diferenca": -331.99,
            "regra_codigo": "ALFA-PRI-06",
            "evidencia_pagina": 3,
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "REGISTRO_ASSISTENCIAL",
            "confianca": "MEDIA",
            "origem": "CODIGO",
        }
        assert "sugestão: retirar" in linha["motivo"].lower()
        assert _linhas(resultado, "VALIDAR", PANTOCAL) == []

    def test_marca_curta_sem_generico_nao_vira_sugestao_de_retirar_sem_ter_sido_procurada(self):
        # AAS e KCL não dão termo de busca (menos de 4 letras, sem genérico entre
        # parênteses): sem procurar no prontuário, a ausência não está provada.
        aas, kcl = "90111111", "90222222"
        conta = _conta(
            _item(aas, "AAS 100 MG CP", dia(2), 1, 0.35),
            _item(kcl, "KCL 19,1% AMP 10 ML", dia(2), 1, 1.20),
        )
        textos = ("EVOLUÇÃO MÉDICA\nMantido AAS 100 mg VO e KCl 19,1% EV.",)

        resultado = conferir(conta, _prontuario(textos=textos), _memoria(), _tabela({}))

        assert _linhas(resultado, "VALIDAR", aas) == []
        assert _linhas(resultado, "VALIDAR", kcl) == []

    def test_oxigenio_2_l_por_150_min_lancado_como_6_l_por_3_h_vira_ajustar_para_3_l_e_3_h(self):
        ficha = _ficha(gases=(Gas("O2", 2.0, 150), Gas("AR", 2.0, 150)))
        conta = _conta(
            _item(
                O2_6L_CC, "OXIGENIO 6 L/MIN POR HORA CC", dia(4), 3, 9.61, grupo="GASES MEDICINAIS", setor=CC, pagina=6
            )
        )
        preco = _tabela({("DIARIA_TAXA", O2_3L_CC): {"COMUM": 4.80, "CARIOCA": 4.80}, ("DIARIA_TAXA", O2_6L_CC): 9.61})

        resultado = conferir(conta, _prontuario(fichas=[ficha], tipo_impressao=None), _memoria(), preco)

        [linha] = _linhas(resultado, "AJUSTAR_QUANTIDADE")
        assert _campos(linha) == {
            "acao": "AJUSTAR_QUANTIDADE",
            "data": "2026-10-04",
            "data_fim": None,
            "setor": CC,
            "codigo": O2_3L_CC,
            "descricao": "Oxigênio 3 L/min no centro cirúrgico, por hora",
            "quantidade_lancada": 3.0,
            "quantidade_devida": 3.0,
            "preco_lancado": 9.61,
            "preco_tabela": 4.80,
            "valor_diferenca": -14.43,
            "regra_codigo": "ALFA-CC-04",
            "evidencia_pagina": 20,
            "nivel_evidencia": "REGISTRADO",
            "causa_raiz": "LANCAMENTO_MANUAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert O2_6L_CC in linha["motivo"]

    def test_cabecalho_com_1_procedimento_e_descricao_cirurgica_com_5_vira_validar(self):
        descricao = DescricaoCirurgica(
            paginas=(30, 31),
            procedimentos=(
                Procedimento("31005497", "COLECISTECTOMIA COM COLANGIOGRAFIA POR VIDEO", True),
                Procedimento("31009328", "HERNIORRAFIA UMBILICAL POR VIDEO", False),
                Procedimento("31005470", "COLANGIOGRAFIA INTRAOPERATORIA", False),
                Procedimento("31003079", "LIBERACAO DE ADERENCIAS POR VIDEO", False),
                Procedimento("31009166", "BIOPSIA HEPATICA POR VIDEO", False),
            ),
            inicio=datetime(2026, 10, 4, 17, 40),
            fim=datetime(2026, 10, 4, 20, 0),
            anatomopatologico=None,
            consignados=None,
        )
        conta = _conta(
            _item(AGULHA, "AGULHA DESC 25X7", dia(4), 2, 0.20, grupo="MATERIAIS DESCARTAVEIS"), procedimento="31005462"
        )

        resultado = conferir(conta, _prontuario(descricoes=[descricao], tipo_impressao=None), _memoria(), _tabela({}))

        [linha] = _linhas(resultado, "VALIDAR", "31005462")
        assert _campos(linha) == {
            "acao": "VALIDAR",
            "data": "2026-10-04",
            "data_fim": None,
            "setor": None,
            "codigo": "31005462",
            "descricao": "PROCEDIMENTO SINTETICO",
            "quantidade_lancada": None,
            "quantidade_devida": None,
            "preco_lancado": None,
            "preco_tabela": None,
            "valor_diferenca": None,
            "regra_codigo": "ALFA-PRI-12",
            "evidencia_pagina": 30,
            "nivel_evidencia": "REGISTRADO",
            "causa_raiz": "LANCAMENTO_MANUAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert "5 procedimentos" in linha["motivo"]

    def test_ficha_anestesica_sem_lancamento_vira_incluir_e_lancado_a_menos_vira_validar(self):
        # Cetoprofeno registrado e não lançado; bromoprida: ficha 2, lançado 1.
        ficha = _ficha(
            medicamentos=(MedicamentoDaFicha("Cetoprofeno", 1, False), MedicamentoDaFicha("Bromoprida", 2, False))
        )
        conta = _conta(_item("90777777", "BROMOPRIDA 10 MG/2 ML AMP", dia(4), 1, 3.20, setor=CC))
        dicionario = {"CETOPROFENO": {"90888888"}}

        resultado = conferir(
            conta, _prontuario(fichas=[ficha], tipo_impressao=None), _memoria(), _tabela({}), dicionario=dicionario
        )

        [incluir] = _linhas(resultado, "INCLUIR")
        assert {
            k: incluir[k] for k in ("codigo", "descricao", "quantidade_devida", "valor_diferenca", "regra_codigo")
        } == {
            "codigo": "90888888",
            "descricao": "Cetoprofeno",
            "quantidade_devida": 1.0,
            "valor_diferenca": None,
            "regra_codigo": "ALFA-CC-07",
        }
        [validar] = _linhas(resultado, "VALIDAR", "90777777")
        assert (validar["quantidade_lancada"], validar["quantidade_devida"], validar["nivel_evidencia"]) == (
            1.0,
            2.0,
            "REGISTRADO",
        )


# ═══════════════════════════════════════════════════════════════════════════
# 2. A regra citada
# ═══════════════════════════════════════════════════════════════════════════


class TestRegraCitada:
    def test_regra_pendente_citada_faz_a_linha_sair_validar_e_nunca_ordem(self):
        resultado = conferir(
            _conta_cirurgica(),
            _prontuario(tipo_impressao=None),
            _memoria(pendentes=("ALFA-PRC-02",)),
            _tabela(TABELA_DA_CIRURGIA),
        )

        [linha] = resultado.linhas
        assert (linha["acao"], linha["codigo"], linha["regra_codigo"], linha["valor_diferenca"]) == (
            "VALIDAR",
            AGULHA,
            "ALFA-PRC-02",
            0.06,
        )
        assert "pendente" in linha["motivo"]

    def test_regra_que_a_memoria_nao_tem_descarta_a_linha_e_registra_o_motivo(self):
        parametros = {**PARAMETROS_ALFA, "regras_das_conferencias": {**REGRAS_DAS_CONFERENCIAS, "preco": "ALFA-PRC-99"}}
        memoria = _memoria(parametros)
        memoria = MemoriaLida(
            **{**memoria.__dict__, "regras": tuple(r for r in memoria.regras if r.codigo != "ALFA-PRC-99")}
        )

        resultado = conferir(_conta_cirurgica(), _prontuario(tipo_impressao=None), memoria, _tabela(TABELA_DA_CIRURGIA))

        assert resultado.linhas == ()
        [descartada] = resultado.descartadas
        assert descartada["linha"]["codigo"] == AGULHA
        assert "ALFA-PRC-99" in descartada["motivo"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Preço: contraprova da coluna, não conferido e pacote
# ═══════════════════════════════════════════════════════════════════════════


class TestPreco:
    def test_80_por_cento_dos_materiais_na_outra_coluna_geram_um_validar_e_nenhuma_correcao(self):
        # Plano Comum, e 4 dos 5 materiais lançados no preço Carioca.
        conta = _conta(
            *(
                _item(codigo, "MATERIAL SINTETICO", dia(2), 1, unitario, grupo="MATERIAIS DESCARTAVEIS")
                for codigo, unitario in zip(MATERIAIS, (0.85, 0.85, 0.85, 0.85, 1.00), strict=True)
            )
        )

        resultado = conferir(conta, _prontuario(tipo_impressao=None), _memoria(), _tabela(TABELA_DE_MATERIAIS))

        assert _linhas(resultado, "CORRIGIR_PRECO") == []
        [linha] = resultado.linhas
        assert (linha["acao"], linha["regra_codigo"], linha["causa_raiz"]) == (
            "VALIDAR",
            "ALFA-PRC-01",
            "CADASTRO_PRECO",
        )
        assert "plano e preços apontam colunas diferentes" in linha["motivo"].lower()

    def test_preco_nao_conferido_leva_etiqueta_e_fica_fora_do_apontado_e_pacote_nao_gera_correcao(self):
        dentro_do_pacote = "70200000"
        prescricoes = [_prescricao(dia(n), _prescrito("PANTOCAL 40MG FA", pagina=10 + n)) for n in range(1, 7)]
        conta = _conta(
            *_conta_cirurgica().itens,
            *(_item(PANTOCAL, "PANTOCAL 40 MG PO LIOF INJ FA", dia(n), 1, 239.65) for n in (1, 2, 3)),
            _item(dentro_do_pacote, "KIT SINTETICO", dia(4), 1, 5.00, grupo="MATERIAIS DESCARTAVEIS", setor=CC),
        )
        preco = _tabela({**TABELA_DA_CIRURGIA, ("MATERIAL", dentro_do_pacote): "PACOTE"})

        resultado = conferir(conta, _prontuario(prescricoes=prescricoes, tipo_impressao=None), _memoria(), preco)

        [incluir] = _linhas(resultado, "INCLUIR", PANTOCAL)
        assert (incluir["preco_tabela"], incluir["valor_diferenca"]) == (None, 718.95)
        assert "preço da conta, não conferido" in incluir["motivo"]
        assert _linhas(resultado, "CORRIGIR_PRECO", dentro_do_pacote) == []
        # Só a agulha entra no R$ apontado: o Incluir sem preço de tabela fica de fora.
        assert resultado.nota.apontado == Decimal("0.06")


# ═══════════════════════════════════════════════════════════════════════════
# 4. Lançado sem registro
# ═══════════════════════════════════════════════════════════════════════════


def _conta_com_solucoes() -> Conta:
    return _conta(
        _item(TAZOCIN, "TAZOCIN 4,5 G PO LIOF INJ FA (PIPERACILINA+TAZOBACTAM)", dia(2), 1, 331.99),
        _item("90000001", "SORO FISIOLOGICO 0,9% 100 ML", dia(2), 1, 4.10),
        _item("90000002", "AGUA DESTILADA 10 ML AMP", dia(2), 2, 0.90),
    )


class TestLancadoSemRegistro:
    def test_ignora_soro_e_agua_destilada(self):
        resultado = conferir(
            _conta_com_solucoes(), _prontuario(textos=("Sem menção a nada.",)), _memoria(), _tabela({})
        )

        assert [linha["codigo"] for linha in _linhas(resultado, "VALIDAR")] == [TAZOCIN]

    def test_nao_roda_com_impressao_parcial(self):
        prontuario = _prontuario(textos=("Sem menção a nada.",), tipo_impressao="Parcial")

        resultado = conferir(_conta_com_solucoes(), prontuario, _memoria(), _tabela({}))

        assert resultado.linhas == ()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Diárias
# ═══════════════════════════════════════════════════════════════════════════

DIARIA_CTI = "60001038"
ACOMPANHANTE = "60000473"
CTI = "CTI ADULTO"
SETORES = {
    CTI: "CTI",
    "ENFERMARIA 3": "ENFERMARIA",
    "ISOLAMENTO 2": "ISOLAMENTO",
    "DAY CLINIC": "HOSPITAL_DIA",
    CC: "CENTRO_CIRURGICO",
}
TABELA_DE_DIARIAS = {
    ("DIARIA_TAXA", DIARIA_CTI): {"COMUM": 609.60, "CARIOCA": 609.60},
    ("DIARIA_TAXA", ACOMPANHANTE): 64.04,
}


def _internacao(entrada: datetime, saida: datetime, setor: str = CTI) -> list[Movimentacao]:
    return [Movimentacao("INTERNACAO", entrada, setor), Movimentacao("ALTA", saida, setor)]


def _diarias_lancadas(codigo: str, *dias: int, unitario: float = 609.60, setor: str = CTI) -> list[ItemConta]:
    return [
        _item(codigo, "DIARIA SINTETICA", dia(n), 1, unitario, grupo="DIARIAS", setor=setor, pagina=1) for n in dias
    ]


class TestDiarias:
    # Internação às 14h do dia 1 e alta às 15h do dia 4: diárias que começam nos
    # dias 1, 2 e 3 (a alta depois das 10h não paga o dia).
    TRES_DIARIAS = (datetime(2026, 10, 1, 14, 0), datetime(2026, 10, 4, 15, 0))

    def test_3_diarias_de_cti_devidas_e_2_lancadas_vira_incluir_1(self):
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2))
        prontuario = _prontuario(movimentacoes=_internacao(*self.TRES_DIARIAS), tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        [linha] = resultado.linhas
        assert _campos(linha) | {"evidencia_pagina": None} == {
            "acao": "INCLUIR",
            "data": "2026-10-03",
            "data_fim": None,
            "setor": CTI,
            "codigo": DIARIA_CTI,
            "descricao": "Diária de CTI",
            "quantidade_lancada": 0.0,
            "quantidade_devida": 1.0,
            "preco_lancado": None,
            "preco_tabela": 609.60,
            "valor_diferenca": 609.60,
            "regra_codigo": "ALFA-DIA-01",
            "evidencia_pagina": None,
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "REGRA_AUTOMATICA",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }

    def test_2_diarias_devidas_e_3_lancadas_vira_retirar_1(self):
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3))
        prontuario = _prontuario(
            movimentacoes=_internacao(datetime(2026, 10, 1, 14, 0), datetime(2026, 10, 3, 15, 0)), tipo_impressao=None
        )

        resultado = conferir(conta, prontuario, _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        [linha] = resultado.linhas
        assert {
            k: linha[k]
            for k in ("acao", "data", "codigo", "quantidade_lancada", "quantidade_devida", "valor_diferenca")
        } == {
            "acao": "RETIRAR",
            "data": "2026-10-03",
            "codigo": DIARIA_CTI,
            "quantidade_lancada": 1.0,
            "quantidade_devida": 0.0,
            "valor_diferenca": -609.60,
        }
        assert (linha["regra_codigo"], linha["causa_raiz"]) == ("ALFA-DIA-01", "REGRA_AUTOMATICA")

    def test_acompanhante_de_paciente_com_60_anos_ou_mais_tem_as_mesmas_diarias(self):
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3))
        prontuario = _prontuario(movimentacoes=_internacao(*self.TRES_DIARIAS), idade=70, tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        [linha] = resultado.linhas
        assert {
            k: linha[k] for k in ("acao", "codigo", "data", "data_fim", "quantidade_devida", "valor_diferenca")
        } == {
            "acao": "INCLUIR",
            "codigo": ACOMPANHANTE,
            "data": "2026-10-01",
            "data_fim": "2026-10-03",
            "quantidade_devida": 3.0,
            "valor_diferenca": 192.12,
        }
        assert linha["regra_codigo"] == "ALFA-DIA-10"

    def test_acompanhante_incluso_na_diaria_global_nao_gera_linha(self):
        # Como na Unimed: diária global e acompanhante incluso (parâmetro nulo).
        parametros = {
            **PARAMETROS_ALFA,
            "diaria": {**PARAMETROS_ALFA["diaria"], "acompanhante_segue_a_regra_do_paciente": None},
            "diaria_global": {"uti_adulto_classe_1": {"codigo": DIARIA_CTI, "valor": 609.60}},
        }
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3))
        prontuario = _prontuario(movimentacoes=_internacao(*self.TRES_DIARIAS), idade=70, tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(parametros), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        assert resultado.linhas == ()

    # Sem contagem completa, a diária lançada não vira ordem: ausência de dado é Validar.
    def test_diaria_lancada_sem_movimentacao_no_prontuario_nao_vira_retirar(self):
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3))

        resultado = conferir(
            conta, _prontuario(tipo_impressao=None), _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES
        )

        assert _linhas(resultado, "RETIRAR") == []

    def test_diaria_lancada_em_setor_sem_acomodacao_cadastrada_vira_so_validar(self):
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3, setor="UTI NEO"))
        prontuario = _prontuario(movimentacoes=_internacao(*self.TRES_DIARIAS, setor="UTI NEO"), tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        assert [linha["acao"] for linha in resultado.linhas] == ["VALIDAR"]
        assert "sem acomodação cadastrada" in resultado.linhas[0]["motivo"]

    def test_parte_da_internacao_em_setor_sem_acomodacao_nao_retira_a_diaria_lancada_daqueles_dias(self):
        # Dias 1 e 2 no CTI (contados); do dia 3 em diante num setor fora do cadastro,
        # lançado com o mesmo código do CTI: a diária do dia 3 não foi conferida.
        movimentacoes = [
            Movimentacao("INTERNACAO", datetime(2026, 10, 1, 14, 0), CTI),
            Movimentacao("TRANSFERENCIA_DE_SETOR", datetime(2026, 10, 3, 9, 0), "UTI NEO"),
            Movimentacao("ALTA", datetime(2026, 10, 4, 15, 0), "UTI NEO"),
        ]
        conta = _conta(*_diarias_lancadas(DIARIA_CTI, 1, 2, 3))

        resultado = conferir(
            conta,
            _prontuario(movimentacoes=movimentacoes, tipo_impressao=None),
            _memoria(),
            _tabela(TABELA_DE_DIARIAS),
            setores=SETORES,
        )

        assert _linhas(resultado, "RETIRAR") == []
        assert any("sem acomodação cadastrada" in linha["motivo"] for linha in _linhas(resultado, "VALIDAR"))

    def test_diaria_lancada_sem_o_codigo_da_acomodacao_na_memoria_nao_vira_retirar(self):
        # A memória não traz o código do CTI; a diária de enfermaria lançada nos dias do CTI não é conferível.
        parametros = {
            **PARAMETROS_ALFA,
            "diaria": {**PARAMETROS_ALFA["diaria"], "codigos": {"enfermaria": "60000805"}},
        }
        conta = _conta(*_diarias_lancadas("60000805", 1, 2, 3))
        prontuario = _prontuario(movimentacoes=_internacao(*self.TRES_DIARIAS), tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(parametros), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        assert _linhas(resultado, "RETIRAR") == []
        assert any("não traz o código" in linha["motivo"] for linha in _linhas(resultado, "VALIDAR"))


# ═══════════════════════════════════════════════════════════════════════════
# 7. Teto por dia
# ═══════════════════════════════════════════════════════════════════════════

LUVA = "70802726"


class TestTeto:
    def test_luva_com_3_diarias_de_cti_pagas_deve_no_maximo_180(self):
        # Teto da luva no CTI: 60 por diária paga (tetos_por_dia da memória).
        conta = _conta(
            *_diarias_lancadas(DIARIA_CTI, 1, 2, 3),
            _item(LUVA, "LUVA PROCEDIMENTO", dia(1), 100, 0.30, grupo="MATERIAIS DESCARTAVEIS", setor=CTI, pagina=4),
            _item(LUVA, "LUVA PROCEDIMENTO", dia(2), 100, 0.30, grupo="MATERIAIS DESCARTAVEIS", setor=CTI, pagina=4),
        )
        prontuario = _prontuario(movimentacoes=_internacao(*TestDiarias.TRES_DIARIAS), tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(), _tabela(TABELA_DE_DIARIAS), setores=SETORES)

        [linha] = resultado.linhas
        assert _campos(linha) == {
            "acao": "AJUSTAR_QUANTIDADE",
            "data": "2026-10-01",
            "data_fim": "2026-10-03",
            "setor": CTI,
            "codigo": LUVA,
            "descricao": "LUVA PROCEDIMENTO",
            "quantidade_lancada": 200.0,
            "quantidade_devida": 180.0,
            "preco_lancado": 0.30,
            "preco_tabela": None,
            "valor_diferenca": -6.00,
            "regra_codigo": "ALFA-INS-33",
            "evidencia_pagina": 4,
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "LANCAMENTO_MANUAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }


# ═══════════════════════════════════════════════════════════════════════════
# 8. Diária global (Unimed, Leve): item incluso, isolamento, pacote, pernoite
# ═══════════════════════════════════════════════════════════════════════════

ENFERMARIA_GLOBAL = "60000090"
APARTAMENTO_GLOBAL = "60034068"
HOSPITAL_DIA = "60034424"
UTI_CLASSE_1 = "60034599"
TAXA_ISOLAMENTO = "60029080"

# Como a Leve: diária semi-global, item cobrável a partir de R$ 400 o frasco.
PARAMETROS_GLOBAL: dict[str, Any] = {
    **PARAMETROS_ALFA,
    "colunas_de_preco": {"padrao": None},
    "diaria": {**PARAMETROS_ALFA["diaria"], "acompanhante_segue_a_regra_do_paciente": None, "codigos": {}},
    "diaria_global": {
        "hospital_dia": {"codigo": HOSPITAL_DIA, "valor": 480.00},
        "enfermaria": {"codigo": ENFERMARIA_GLOBAL, "valor": 900.00},
        "apartamento": {"codigo": APARTAMENTO_GLOBAL, "valor": 1100.00},
        "uti_adulto_classe_1": {"codigo": UTI_CLASSE_1, "valor": 1850.00},
        "uti_adulto_classe_2": {"codigo": "60034602", "valor": 2650.00},
        "taxa_isolamento_dia": {"codigo": TAXA_ISOLAMENTO, "valor": 100.00},
    },
    "tetos_por_dia": {},
    "precos": {"corte_valor_unitario": 400.00},
    "regras_das_conferencias": {
        **REGRAS_DAS_CONFERENCIAS,
        "taxa_isolamento": "ALFA-DIA-20",
        "hospital_dia_pernoite": "ALFA-DIA-16",
        "pacote_pelo_tuss": "ALFA-PAC-03",
    },
}

TABELA_GLOBAL = {
    ("DIARIA_TAXA", ENFERMARIA_GLOBAL): 900.00,
    ("DIARIA_TAXA", APARTAMENTO_GLOBAL): 1100.00,
    ("DIARIA_TAXA", HOSPITAL_DIA): 480.00,
    ("DIARIA_TAXA", UTI_CLASSE_1): 1850.00,
    ("DIARIA_TAXA", TAXA_ISOLAMENTO): 100.00,
}


class TestDiariaGlobal:
    def test_so_o_item_acima_do_corte_gera_incluir_e_o_incluso_nao_gera_retirar(self):
        zyvox, dipirona, meronem, omeprazol = "91000001", "91000002", "91000003", "91000004"
        nomes = ("ZYVOX 600MG BOLSA", "DIPIRONA 1G AMP", "MERONEM 1G FA")
        prescricoes = [_prescricao(dia(n), *(_prescrito(nome, pagina=10 + n) for nome in nomes)) for n in (1, 2, 3)]
        conta = _conta(
            _item(zyvox, "ZYVOX 600 MG BOLSA 300 ML", dia(1), 1, 520.00),
            _item(dipirona, "DIPIRONA 1 G AMP", dia(1), 1, 2.00),
            _item(meronem, "MERONEM 1 G FA", dia(1), 1, 380.00),
            # Lançado sem menção no prontuário, mas incluso na diária: entra sem cobrança.
            _item(omeprazol, "OMEPRAZOL 40 MG FA", dia(1), 1, 30.00),
        )
        preco = _tabela(
            {("MEDICAMENTO", zyvox): 520.00, ("MEDICAMENTO", dipirona): 2.00, ("MEDICAMENTO", omeprazol): 30.00}
        )
        textos = ("Zyvox, dipirona e Meronem conforme prescrição.",)

        resultado = conferir(
            conta, _prontuario(prescricoes=prescricoes, textos=textos), _memoria(PARAMETROS_GLOBAL), preco
        )

        assert [(linha["acao"], linha["codigo"]) for linha in resultado.linhas] == [
            ("INCLUIR", zyvox),
            ("VALIDAR", meronem),
        ]
        incluir, validar = resultado.linhas
        assert (incluir["data"], incluir["data_fim"], incluir["quantidade_devida"], incluir["valor_diferenca"]) == (
            "2026-10-02",
            "2026-10-03",
            2.0,
            1040.00,
        )
        assert "conferir se passa do corte" in validar["motivo"]

    def test_taxa_de_isolamento_por_dia_de_isolamento(self):
        # Isolamento de enfermaria: a diária é a da contratada, mais a taxa por dia.
        conta = _conta(
            *_diarias_lancadas(ENFERMARIA_GLOBAL, 1, 2, 3, unitario=900.00, setor="ISOLAMENTO 2"),
            *_diarias_lancadas(TAXA_ISOLAMENTO, 1, unitario=100.00, setor="ISOLAMENTO 2"),
        )
        prontuario = _prontuario(
            movimentacoes=_internacao(*TestDiarias.TRES_DIARIAS, setor="ISOLAMENTO 2"), tipo_impressao=None
        )

        resultado = conferir(conta, prontuario, _memoria(PARAMETROS_GLOBAL), _tabela(TABELA_GLOBAL), setores=SETORES)

        [linha] = resultado.linhas
        assert {
            k: linha[k] for k in ("acao", "codigo", "data", "data_fim", "quantidade_devida", "valor_diferenca")
        } == {
            "acao": "INCLUIR",
            "codigo": TAXA_ISOLAMENTO,
            "data": "2026-10-02",
            "data_fim": "2026-10-03",
            "quantidade_devida": 2.0,
            "valor_diferenca": 200.00,
        }
        assert linha["regra_codigo"] == "ALFA-DIA-20"

    def test_hospital_dia_que_pernoita_troca_para_a_diaria_da_contratada(self):
        # Day clinic das 7h do dia 1 às 11h do dia 2: atravessou o vencimento das 10h.
        conta = _conta(
            *_diarias_lancadas(HOSPITAL_DIA, 1, unitario=480.00, setor="DAY CLINIC"), acomodacao="APARTAMENTO"
        )
        prontuario = _prontuario(
            movimentacoes=_internacao(datetime(2026, 10, 1, 7, 0), datetime(2026, 10, 2, 11, 0), setor="DAY CLINIC"),
            tipo_impressao=None,
        )

        resultado = conferir(conta, prontuario, _memoria(PARAMETROS_GLOBAL), _tabela(TABELA_GLOBAL), setores=SETORES)

        assert [(linha["acao"], linha["codigo"], linha["data"]) for linha in resultado.linhas] == [
            ("INCLUIR", APARTAMENTO_GLOBAL, "2026-10-01"),
            ("RETIRAR", HOSPITAL_DIA, "2026-10-01"),
        ]
        incluir = resultado.linhas[0]
        assert (incluir["regra_codigo"], incluir["valor_diferenca"]) == ("ALFA-DIA-16", 1100.00)
        assert "conferir pernoite" in incluir["motivo"].lower()

    def test_hospital_dia_sem_pernoite_e_uma_diaria_de_hospital_dia(self):
        conta = _conta(
            *_diarias_lancadas(HOSPITAL_DIA, 1, unitario=480.00, setor="DAY CLINIC"), acomodacao="APARTAMENTO"
        )
        prontuario = _prontuario(
            movimentacoes=_internacao(datetime(2026, 10, 1, 7, 0), datetime(2026, 10, 1, 16, 0), setor="DAY CLINIC"),
            tipo_impressao=None,
        )

        resultado = conferir(conta, prontuario, _memoria(PARAMETROS_GLOBAL), _tabela(TABELA_GLOBAL), setores=SETORES)

        assert resultado.linhas == ()

    def test_pacote_pelo_tuss_da_descricao_cirurgica_com_diaria_excedente(self):
        # Cesariana com pacote de 2 diárias; internação às 4h do dia 1 e alta às 15h
        # do dia 4 somam 4 diárias: pacote mais 2 excedentes da enfermaria contratada.
        cesariana = DescricaoCirurgica(
            paginas=(30,),
            procedimentos=(Procedimento("31309054", "CESARIANA", True),),
            inicio=datetime(2026, 10, 1, 8, 0),
            fim=datetime(2026, 10, 1, 9, 0),
            anatomopatologico=None,
            consignados=None,
        )
        pacotes = {
            "31309054": Pacote(codigo="89450171", descricao="Cesariana", permanencia=2, valor=Decimal("3300.00"))
        }
        prontuario = _prontuario(
            descricoes=[cesariana],
            movimentacoes=_internacao(datetime(2026, 10, 1, 4, 0), datetime(2026, 10, 4, 15, 0), setor="ENFERMARIA 3"),
            tipo_impressao=None,
        )

        resultado = conferir(
            _conta(),
            prontuario,
            _memoria(PARAMETROS_GLOBAL),
            _tabela(TABELA_GLOBAL),
            setores=SETORES,
            pacote_do_tuss=lambda tuss, data: pacotes.get(tuss),
        )

        resumo = [
            (linha["codigo"], linha["data"], linha["data_fim"], linha["quantidade_devida"], linha["valor_diferenca"])
            for linha in _linhas(resultado, "INCLUIR")
        ]
        assert resumo == [
            ("89450171", "2026-10-01", None, 1.0, 3300.00),
            (ENFERMARIA_GLOBAL, "2026-10-02", "2026-10-03", 2.0, 1800.00),
        ]
        assert {linha["regra_codigo"] for linha in resultado.linhas} == {"ALFA-PAC-03"}

    def test_diaria_de_uti_em_operadora_com_classes_sai_na_classe_mais_baixa_para_conferir(self):
        # Lançadas 2 diárias na classe II; a classe do dia é do Passo B (PRD 2).
        conta = _conta(*_diarias_lancadas("60034602", 1, 2, unitario=2650.00))
        prontuario = _prontuario(movimentacoes=_internacao(*TestDiarias.TRES_DIARIAS), tipo_impressao=None)

        resultado = conferir(conta, prontuario, _memoria(PARAMETROS_GLOBAL), _tabela(TABELA_GLOBAL), setores=SETORES)

        [linha] = resultado.linhas
        assert (linha["acao"], linha["codigo"], linha["data"], linha["valor_diferenca"]) == (
            "INCLUIR",
            UTI_CLASSE_1,
            "2026-10-03",
            1850.00,
        )
        assert "conferir classe de uti" in linha["motivo"].lower()


# ═══════════════════════════════════════════════════════════════════════════
# 5. Montagem: item diário, período, duplicadas
# ═══════════════════════════════════════════════════════════════════════════


class TestMontagem:
    def test_duplicadas_sao_unidas(self):
        # A urgência do dia 4 repete o pantoprazol da prescrição médica: as duas
        # conferências pedem o mesmo Incluir no mesmo dia, e o Guia mostra um só.
        prescricoes = [_prescricao(dia(n), _prescrito("PANTOCAL 40MG FA", pagina=10 + n)) for n in range(1, 7)]
        urgencia = Prescricao(
            dia(4), time(3, 0), "PRESCRICAO URGENCIA", "CTI ADULTO", (40,), (_prescrito("PANTOCAL 40MG FA", 40),)
        )
        conta = _conta(*(_item(PANTOCAL, "PANTOCAL 40 MG PO LIOF INJ FA", dia(n), 1, 239.65) for n in (1, 2, 3)))

        resultado = conferir(
            conta, _prontuario(prescricoes=[*prescricoes, urgencia], tipo_impressao=None), _memoria(), _tabela({})
        )

        [linha] = _linhas(resultado, "INCLUIR", PANTOCAL)
        assert (linha["data"], linha["data_fim"], linha["quantidade_devida"], linha["valor_diferenca"]) == (
            "2026-10-04",
            "2026-10-06",
            3.0,
            718.95,
        )

    def test_linha_fora_do_periodo_da_conta_e_descartada_e_registrada(self):
        # Ficha anestésica do dia 8 numa parcial de 1 a 6: o Incluir cai fora do período.
        ficha = _ficha(medicamentos=(MedicamentoDaFicha("Cetoprofeno", 1, False),), data=dia(8))

        resultado = conferir(_conta(), _prontuario(fichas=[ficha], tipo_impressao=None), _memoria(), _tabela({}))

        assert resultado.linhas == ()
        [descartada] = resultado.descartadas
        assert descartada["linha"]["descricao"] == "Cetoprofeno"
        assert "fora do período" in descartada["motivo"]


# ═══════════════════════════════════════════════════════════════════════════
# 6. Exame solicitado × exame lançado (adendo v1.3, item 6, conferência 9)
# ═══════════════════════════════════════════════════════════════════════════

HEMOGRAMA = "40304361"
UREIA = "40301630"
GASOMETRIA = "40302040"


class TestExames:
    def test_2_exames_pedidos_e_1_lancado_vira_incluir_com_o_pedido_e_lancado_sem_pedido_vira_validar(self):
        exames = [
            ExamePedido("HEMOGRAMA COMPLETO", "3014", dia(2), 30),
            ExamePedido("UREIA", "3015", dia(2), 30),
        ]
        conta = _conta(
            _item(HEMOGRAMA, "HEMOGRAMA COMPLETO", dia(2), 1, 15.00, grupo="EXAMES", pagina=7),
            _item(GASOMETRIA, "GASOMETRIA ARTERIAL", dia(3), 1, 30.00, grupo="EXAMES", pagina=7),
        )

        resultado = conferir(conta, _prontuario(exames=exames), _memoria(), _tabela({}), dicionario={"UREIA": {UREIA}})

        [incluir] = _linhas(resultado, "INCLUIR")
        assert _campos(incluir) == {
            "acao": "INCLUIR",
            "data": "2026-10-02",
            "data_fim": None,
            "setor": None,
            "codigo": UREIA,
            "descricao": "UREIA",
            "quantidade_lancada": 0.0,
            "quantidade_devida": 1.0,
            "preco_lancado": None,
            "preco_tabela": None,
            "valor_diferenca": None,
            "regra_codigo": "ALFA-SAD-01",
            "evidencia_pagina": 30,
            "nivel_evidencia": "PRESCRITO",
            "causa_raiz": "LANCAMENTO_MANUAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert "pedido 3015" in incluir["motivo"]
        [validar] = _linhas(resultado, "VALIDAR")
        assert _campos(validar) == {
            "acao": "VALIDAR",
            "data": "2026-10-03",
            "data_fim": None,
            "setor": "CTI ADULTO",
            "codigo": GASOMETRIA,
            "descricao": "GASOMETRIA ARTERIAL",
            "quantidade_lancada": 1.0,
            "quantidade_devida": 0.0,
            "preco_lancado": 30.00,
            "preco_tabela": None,
            "valor_diferenca": -30.00,
            "regra_codigo": "ALFA-SAD-01",
            "evidencia_pagina": 7,
            "nivel_evidencia": "POR_REGRA",
            "causa_raiz": "REGISTRO_ASSISTENCIAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert len(resultado.linhas) == 2

    def test_pedido_da_parcial_anterior_repetido_na_prescricao_do_dia_seguinte_nao_vira_incluir(self):
        exames = [
            ExamePedido("HEMOGRAMA COMPLETO", "3014", dia(2), 30),
            ExamePedido("HEMOGRAMA COMPLETO", "3014", dia(3), 31),
        ]
        conta = _conta(inicio=dia(3), fim=dia(6))

        resultado = conferir(conta, _prontuario(exames=exames), _memoria(), _tabela({}), dicionario={})

        assert _linhas(resultado, "INCLUIR") == []

    def test_dois_pedidos_do_mesmo_exame_no_mesmo_dia_sem_lancamento_viram_incluir_2_com_os_dois_pedidos(self):
        exames = [
            ExamePedido("GASOMETRIA ARTERIAL", "4001", dia(3), 40),
            ExamePedido("GASOMETRIA ARTERIAL", "4002", dia(3), 40),
            ExamePedido("GASOMETRIA ARTERIAL", "4003", dia(3), 40),
            ExamePedido("GASOMETRIA ARTERIAL", "4004", dia(3), 40),
        ]
        conta = _conta(_item(GASOMETRIA, "GASOMETRIA ARTERIAL", dia(3), 2, 30.00, grupo="EXAMES", pagina=7))

        resultado = conferir(conta, _prontuario(exames=exames), _memoria(), _tabela({}), dicionario={})

        [incluir] = _linhas(resultado, "INCLUIR")
        assert incluir["codigo"] == GASOMETRIA
        assert incluir["quantidade_devida"] == 2.0
        assert incluir["valor_diferenca"] == 60.00
        assert "pedidos 4003, 4004" in incluir["motivo"]
        assert not resultado.descartadas


# ═══════════════════════════════════════════════════════════════════════════
# 7. Glicemia × fita, lanceta e algodão (conferência 10, ASSIM-INS-18)
# ═══════════════════════════════════════════════════════════════════════════

FITA = "70902771"
LANCETA = "70902925"
ALGODAO = "70019860"

PARAMETROS_COM_GLICEMIA: dict[str, Any] = {
    **PARAMETROS_ALFA,
    "glicemia_capilar": {"codigos": [FITA, LANCETA, ALGODAO], "por_afericao": 1},
}

# A mesma glicemia está na aferição e no balanço do dia: são 4, não 8.
GLICEMIAS_DO_DIA_3 = (
    GlicemiasDoDia(dia(3), "AFERICAO", 4, (40, 41, 42, 43)),
    GlicemiasDoDia(dia(3), "BALANCO", 4, (50,)),
)


def _conta_com_2_fitas() -> Conta:
    material = {"grupo": "MATERIAIS DESCARTAVEIS"}
    return _conta(
        _item(FITA, "FITA GLICEMIA ACCU CHEK", dia(3), 2, 3.00, pagina=8, **material),
        _item(LANCETA, "LANCETA DESC", dia(3), 4, 0.50, pagina=8, **material),
    )


class TestGlicemia:
    def test_4_glicemias_no_dia_e_2_fitas_lancadas_vira_ajustar_para_4_e_sem_algodao_vira_incluir(self):
        resultado = conferir(
            _conta_com_2_fitas(),
            _prontuario(glicemias=GLICEMIAS_DO_DIA_3),
            _memoria(PARAMETROS_COM_GLICEMIA),
            _tabela({("MATERIAL", FITA): 3.00}),
        )

        [ajustar] = _linhas(resultado, "AJUSTAR_QUANTIDADE")
        assert _campos(ajustar) == {
            "acao": "AJUSTAR_QUANTIDADE",
            "data": "2026-10-03",
            "data_fim": None,
            "setor": "CTI ADULTO",
            "codigo": FITA,
            "descricao": "FITA GLICEMIA ACCU CHEK",
            "quantidade_lancada": 2.0,
            "quantidade_devida": 4.0,
            "preco_lancado": 3.00,
            "preco_tabela": 3.00,
            "valor_diferenca": 6.00,
            "regra_codigo": "ALFA-INS-18",
            "evidencia_pagina": 40,
            "nivel_evidencia": "REGISTRADO",
            "causa_raiz": "LANCAMENTO_MANUAL",
            "confianca": "ALTA",
            "origem": "CODIGO",
        }
        assert "4 glicemias" in ajustar["motivo"]
        [incluir] = _linhas(resultado, "INCLUIR")
        assert (
            incluir["codigo"],
            incluir["quantidade_devida"],
            incluir["regra_codigo"],
            incluir["evidencia_pagina"],
        ) == (
            ALGODAO,
            4.0,
            "ALFA-INS-18",
            40,
        )
        assert len(resultado.linhas) == 2

    def test_sem_regra_de_glicemia_na_memoria_nenhuma_linha(self):
        sem_regra = {
            **PARAMETROS_COM_GLICEMIA,
            "regras_das_conferencias": {k: v for k, v in REGRAS_DAS_CONFERENCIAS.items() if k != "glicemia"},
        }

        resultado = conferir(
            _conta_com_2_fitas(),
            _prontuario(glicemias=GLICEMIAS_DO_DIA_3),
            _memoria(sem_regra),
            _tabela({("MATERIAL", FITA): 3.00}),
        )

        assert resultado.linhas == ()


class TestRegraPendenteDeExameEGlicemia:
    def test_regra_pendente_faz_exame_e_glicemia_sairem_validar(self):
        resultado = conferir(
            _conta_com_2_fitas(),
            _prontuario(glicemias=GLICEMIAS_DO_DIA_3, exames=[ExamePedido("UREIA", "3015", dia(2), 30)]),
            _memoria(PARAMETROS_COM_GLICEMIA, pendentes=("ALFA-INS-18", "ALFA-SAD-01")),
            _tabela({("MATERIAL", FITA): 3.00}),
        )

        assert sorted((linha["acao"], linha["codigo"] or "", linha["regra_codigo"]) for linha in resultado.linhas) == [
            ("VALIDAR", "", "ALFA-SAD-01"),
            ("VALIDAR", ALGODAO, "ALFA-INS-18"),
            ("VALIDAR", FITA, "ALFA-INS-18"),
        ]
        assert all(linha["motivo"].startswith("Regra ALFA-") for linha in resultado.linhas)


# ═══════════════════════════════════════════════════════════════════════════
# 8. "Se necessário" com os eventos do Passo A (issue #1134)
# ═══════════════════════════════════════════════════════════════════════════

DIPIRONA = "91000002"
TEXTO_SN = "Confira a checagem em papel. Sem uso, marque NÃO PROCEDE."

PARAMETROS_SN: dict[str, Any] = {
    **PARAMETROS_ALFA,
    "regras_das_conferencias": {**REGRAS_DAS_CONFERENCIAS, "se_necessario": "ALFA-PRI-09"},
}


def _sn(nome: str, pagina: int, *, suspenso: bool = False) -> ItemPrescrito:
    """Item "se necessário" como a leitura por código entrega: sem doses no dia."""
    return replace(
        _prescrito(nome, pagina, colunas="1 AMP EV S EV", doses=None),
        se_necessario=True,
        suspenso=suspenso,
        frequencia=None,
    )


def _evento_de_prescricao(
    nome: str, data: date, *, indicio: str | None = None, doses: float | None = None, suspenso: bool = False
) -> dict[str, Any]:
    """Uma prescrição do Passo A no formato que `cm_eventos` guarda."""
    return {
        "data": data.isoformat(),
        "setor": CTI,
        "item": nome,
        "via": "EV",
        "doses_no_dia": doses,
        "se_necessario": True,
        "indicio_de_uso": indicio,
        "suspenso": suspenso,
        "diluente": None,
        "em_bomba": False,
        "pagina": 40 + data.day,
        "trecho": indicio or nome,
        "etiquetas": [],
        "confianca": None,
    }


def _eventos(*, prescricoes=(), terapias=(), procedimentos=()) -> dict[str, Any]:
    return {
        "movimentacoes": [],
        "terapias": list(terapias),
        "prescricoes": list(prescricoes),
        "procedimentos": list(procedimentos),
        "cirurgias": [],
        "documentos_ausentes": [],
        "observacoes": [],
        "divergencias": [],
    }


class TestSeNecessario:
    DICIONARIO = {"DIPIRONA": {DIPIRONA}}
    TABELA = {("MEDICAMENTO", DIPIRONA): 2.00}

    def _conferir(self, prontuario, eventos, parametros=None, tabela=None):
        return conferir(
            _conta(),
            prontuario,
            _memoria(parametros or PARAMETROS_SN),
            _tabela(tabela or self.TABELA),
            dicionario=self.DICIONARIO,
            eventos=eventos,
        )

    def test_indicio_em_2_de_4_dias_inclui_as_doses_indicadas_e_1_por_dia_nos_outros_com_o_texto(self):
        prescricoes = [_prescricao(dia(n), _sn("DIPIRONA 1G AMP", pagina=10 + n)) for n in (1, 2, 3, 4)]
        # Dia 1: a evolução cita 2 doses. Dia 2: o balanço registra 1 lançamento.
        eventos = _eventos(
            prescricoes=[_evento_de_prescricao("DIPIRONA 1G AMP", dia(1), indicio="Feita dipirona 2x", doses=2)]
        )
        balanco = Balanco(dia(2), CTI, (30,), (LinhaDoBalanco("DIPIRONA 1G", "EV", 1, 10.0),), (), 0)

        resultado = self._conferir(_prontuario(prescricoes=prescricoes, balancos=[balanco]), eventos)

        resumo = [
            (
                linha["acao"],
                linha["codigo"],
                linha["data"],
                linha["data_fim"],
                linha["quantidade_devida"],
                linha["valor_diferenca"],
                linha["nivel_evidencia"],
                linha["regra_codigo"],
            )
            for linha in resultado.linhas
        ]
        assert sorted(resumo) == [
            ("INCLUIR", DIPIRONA, "2026-10-01", "2026-10-02", 3.0, 6.00, "REGISTRADO", "ALFA-PRI-09"),
            ("INCLUIR", DIPIRONA, "2026-10-03", "2026-10-04", 2.0, 4.00, "PRESCRITO_SN", "ALFA-PRI-09"),
        ]
        registrado = next(linha for linha in resultado.linhas if linha["nivel_evidencia"] == "REGISTRADO")
        sem_registro = next(linha for linha in resultado.linhas if linha["nivel_evidencia"] == "PRESCRITO_SN")
        assert (registrado["evidencia_pagina"], registrado["evidencia_trecho"]) == (41, "Feita dipirona 2x")
        assert sem_registro["motivo"].endswith(TEXTO_SN)
        assert TEXTO_SN not in registrado["motivo"]

    def test_suspenso_ou_alterado_no_dia_3_e_dia_depois_da_alta_nao_geram_linha(self):
        # Dia 3: a prescrição da manhã suspende e a da tarde prescreve de novo (alterado).
        prescricoes = [
            *(_prescricao(dia(n), _sn("DIPIRONA 1G AMP", pagina=10 + n)) for n in (1, 2, 4, 5)),
            _prescricao(dia(3), _sn("DIPIRONA 1G AMP", pagina=13, suspenso=True)),
            _prescricao(dia(3), _sn("DIPIRONA 1G AMP", pagina=14)),
        ]
        prontuario = _prontuario(prescricoes=prescricoes, alta=datetime(2026, 10, 4, 15, 0))

        resultado = self._conferir(prontuario, _eventos())

        assert [(linha["data"], linha["data_fim"], linha["quantidade_devida"]) for linha in resultado.linhas] == [
            ("2026-10-01", "2026-10-02", 2.0),
            ("2026-10-04", None, 1.0),
        ]
        assert {linha["nivel_evidencia"] for linha in resultado.linhas} == {"PRESCRITO_SN"}

    def test_2_doses_por_dia_sem_registro_na_memoria_viram_2_por_dia(self):
        prescricoes = [_prescricao(dia(n), _sn("DIPIRONA 1G AMP", pagina=10 + n)) for n in (1, 2)]
        parametros = {**PARAMETROS_SN, "transicao": {"se_necessario_doses_por_dia_sem_registro": 2}}

        resultado = self._conferir(_prontuario(prescricoes=prescricoes), _eventos(), parametros)

        [linha] = resultado.linhas
        assert (linha["data"], linha["data_fim"], linha["quantidade_devida"], linha["valor_diferenca"]) == (
            "2026-10-01",
            "2026-10-02",
            4.0,
            8.00,
        )
        assert "2 por dia" in linha["motivo"]

    def test_diaria_global_item_incluso_nao_gera_linha_e_acima_do_corte_gera(self):
        zyvox = "91000001"
        prescricoes = [
            _prescricao(dia(n), _sn("DIPIRONA 1G AMP", pagina=10 + n), _sn("ZYVOX 600MG BOLSA", pagina=20 + n))
            for n in (1, 2)
        ]
        parametros = {**PARAMETROS_GLOBAL, "regras_das_conferencias": PARAMETROS_SN["regras_das_conferencias"]}
        tabela = {("MEDICAMENTO", DIPIRONA): 2.00, ("MEDICAMENTO", zyvox): 520.00}

        resultado = conferir(
            _conta(),
            _prontuario(prescricoes=prescricoes),
            _memoria(parametros),
            _tabela(tabela),
            dicionario={**self.DICIONARIO, "ZYVOX": {zyvox}},
            eventos=_eventos(),
        )

        [linha] = resultado.linhas
        assert (linha["acao"], linha["codigo"], linha["quantidade_devida"], linha["nivel_evidencia"]) == (
            "INCLUIR",
            zyvox,
            2.0,
            "PRESCRITO_SN",
        )

    def test_sem_os_eventos_do_passo_a_o_se_necessario_nao_roda(self):
        prescricoes = [_prescricao(dia(1), _sn("DIPIRONA 1G AMP", pagina=11))]

        resultado = self._conferir(_prontuario(prescricoes=prescricoes), None)

        assert resultado.linhas == ()


# ═══════════════════════════════════════════════════════════════════════════
# 8b. Classe de UTI do dia pelos eventos do Passo A (issue #1134)
# ═══════════════════════════════════════════════════════════════════════════

UNIMED_CLASSE_1, UNIMED_CLASSE_2, UNIMED_CLASSE_5 = "60000252", "60000236", "60000260"
ASSIM_NIVEL_1, ASSIM_NIVEL_2 = "98032437", "98032445"
REGRAS_COM_CLASSE = {**REGRAS_DAS_CONFERENCIAS, "classe_de_uti": "ALFA-DIA-14"}

# Como a Unimed: diária global com as classes I, II e V da UTI adulto.
PARAMETROS_UNIMED: dict[str, Any] = {
    **PARAMETROS_GLOBAL,
    "diaria_global": {
        "uti_adulto_classe_1": {"codigo": UNIMED_CLASSE_1, "valor": 2415.00},
        "uti_adulto_classe_2": {"codigo": UNIMED_CLASSE_2, "valor": 3492.88},
        "uti_adulto_classe_5": {"codigo": UNIMED_CLASSE_5, "valor": 4831.55},
    },
    "regras_das_conferencias": REGRAS_COM_CLASSE,
}
TABELA_UNIMED = {
    ("DIARIA_TAXA", UNIMED_CLASSE_1): 2415.00,
    ("DIARIA_TAXA", UNIMED_CLASSE_2): 3492.88,
    ("DIARIA_TAXA", UNIMED_CLASSE_5): 4831.55,
}

# Como a ASSIM: pacote de UTI adulto em dois níveis, só na Linha Carioca.
PARAMETROS_ASSIM: dict[str, Any] = {
    **PARAMETROS_ALFA,
    "pacote_uti_adulto": {
        "somente_linha_carioca": True,
        "nivel_1": {"codigo": ASSIM_NIVEL_1, "valor": 1406.77},
        "nivel_2": {"codigo": ASSIM_NIVEL_2, "valor": 1954.46},
    },
    "regras_das_conferencias": REGRAS_COM_CLASSE,
}
TABELA_ASSIM = {
    **TABELA_DE_DIARIAS,
    ("PACOTE", ASSIM_NIVEL_1): 1406.77,
    ("PACOTE", ASSIM_NIVEL_2): 1954.46,
}


def _terapia(tipo: str, inicio: str, fim: str | None, *, pagina: int, trecho: str) -> dict[str, Any]:
    """Uma terapia do Passo A no formato que `cm_eventos` guarda."""
    return {
        "tipo": tipo,
        "descricao": trecho,
        "setor": CTI,
        "inicio": inicio,
        "fim": fim,
        "pagina": pagina,
        "trecho": trecho,
        "etiquetas": [],
        "confianca": None,
    }


def _resumo_das_diarias(resultado) -> list[tuple]:
    return sorted(
        (
            linha["acao"],
            linha["codigo"],
            linha["data"],
            linha["data_fim"],
            linha["quantidade_devida"] if linha["acao"] == "INCLUIR" else linha["quantidade_lancada"],
            linha["valor_diferenca"],
            linha["regra_codigo"],
        )
        for linha in resultado.linhas
    )


class TestClasseDeUti:
    VENTILACAO = _terapia(
        "VENTILACAO_MECANICA", "2026-10-01T15:00", "2026-10-02T22:00", pagina=50, trecho="Em VM, modo PCV"
    )

    def _prontuario_de_cti(self) -> ProntuarioLido:
        return _prontuario(movimentacoes=_internacao(*TestDiarias.TRES_DIARIAS), tipo_impressao=None)

    def test_ventilacao_mecanica_em_2_de_3_dias_sai_classe_v_nos_2_e_classe_i_no_terceiro(self):
        resultado = conferir(
            _conta(),
            self._prontuario_de_cti(),
            _memoria(PARAMETROS_UNIMED),
            _tabela(TABELA_UNIMED),
            setores=SETORES,
            eventos=_eventos(terapias=[self.VENTILACAO]),
        )

        assert _resumo_das_diarias(resultado) == [
            ("INCLUIR", UNIMED_CLASSE_1, "2026-10-03", None, 1.0, 2415.00, "ALFA-DIA-14"),
            ("INCLUIR", UNIMED_CLASSE_5, "2026-10-01", "2026-10-02", 2.0, 9663.10, "ALFA-DIA-14"),
        ]
        classe_1, classe_5 = sorted(resultado.linhas, key=lambda linha: linha["codigo"])
        assert (classe_5["evidencia_pagina"], classe_5["evidencia_trecho"]) == (50, "Em VM, modo PCV")
        assert "ventilação mecânica" in classe_5["motivo"]
        assert classe_1["evidencia_trecho"].startswith("Setor CTI ADULTO: de 01/10/2026 14:00")
        assert all("conferir classe de uti" in linha["motivo"].lower() for linha in resultado.linhas)

    def test_classe_i_lancada_nos_dias_de_ventilacao_sai_para_retirar_com_a_observacao(self):
        conta = _conta(*_diarias_lancadas(UNIMED_CLASSE_1, 1, 2, 3, unitario=2415.00))

        resultado = conferir(
            conta,
            self._prontuario_de_cti(),
            _memoria(PARAMETROS_UNIMED),
            _tabela(TABELA_UNIMED),
            setores=SETORES,
            eventos=_eventos(terapias=[self.VENTILACAO]),
        )

        assert _resumo_das_diarias(resultado) == [
            ("INCLUIR", UNIMED_CLASSE_5, "2026-10-01", "2026-10-02", 2.0, 9663.10, "ALFA-DIA-14"),
            ("RETIRAR", UNIMED_CLASSE_1, "2026-10-01", "2026-10-02", 2.0, -4830.00, "ALFA-DIA-14"),
        ]
        retirar = _linhas(resultado, "RETIRAR")[0]
        assert "conferir classe de uti" in retirar["motivo"].lower()

    def test_assim_linha_carioca_monitorizacao_invasiva_no_dia_2_e_nivel_2_e_os_outros_nivel_1(self):
        pai = _terapia("PRESSAO_INVASIVA", "2026-10-02T09:00", "2026-10-02T18:00", pagina=52, trecho="PAI radial")

        resultado = conferir(
            _conta(plano="Alfa Max Qc"),
            self._prontuario_de_cti(),
            _memoria(PARAMETROS_ASSIM),
            _tabela(TABELA_ASSIM),
            setores=SETORES,
            eventos=_eventos(terapias=[pai]),
        )

        assert _resumo_das_diarias(resultado) == [
            ("INCLUIR", ASSIM_NIVEL_1, "2026-10-01", None, 1.0, 1406.77, "ALFA-DIA-14"),
            ("INCLUIR", ASSIM_NIVEL_1, "2026-10-03", None, 1.0, 1406.77, "ALFA-DIA-14"),
            ("INCLUIR", ASSIM_NIVEL_2, "2026-10-02", None, 1.0, 1954.46, "ALFA-DIA-14"),
        ]
        nivel_2 = _linhas(resultado, "INCLUIR", ASSIM_NIVEL_2)[0]
        assert (nivel_2["evidencia_pagina"], nivel_2["evidencia_trecho"]) == (52, "PAI radial")
        assert all("conferir classe de uti" in linha["motivo"].lower() for linha in resultado.linhas)

    def test_assim_fora_da_linha_carioca_segue_a_diaria_de_cti(self):
        pai = _terapia("PRESSAO_INVASIVA", "2026-10-02T09:00", "2026-10-02T18:00", pagina=52, trecho="PAI radial")

        resultado = conferir(
            _conta(plano="Alfa Basico"),
            self._prontuario_de_cti(),
            _memoria(PARAMETROS_ASSIM),
            _tabela(TABELA_ASSIM),
            setores=SETORES,
            eventos=_eventos(terapias=[pai]),
        )

        assert {linha["codigo"] for linha in resultado.linhas} == {DIARIA_CTI}


# ═══════════════════════════════════════════════════════════════════════════
# 9. Tipografia (ADR 0013)
# ═══════════════════════════════════════════════════════════════════════════


KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


def test_o_kit_de_conhecimento_diz_como_o_se_necessario_e_a_classe_de_uti_entram_no_guia():
    secao = KIT.read_text(encoding="utf-8").split("## O Guia", 1)[1].split("\n## ", 1)[0]

    for trecho in (
        '"se necessário"',
        "SE NECESSÁRIO · SEM REGISTRO NO MV",
        TEXTO_SN,
        "uma dose por dia de prescrição",
        "as doses indicadas",
        "Prescrito SN",
        "sem evidência no prontuário",
        "conferir classe de UTI",
        "ventilação mecânica",
    ):
        assert trecho in secao, trecho


def test_motivo_e_evidencia_sem_travessao_nem_meia_risca():
    """O motivo e o trecho vão para a tela da faturista: o módulo não escreve
    travessão nem meia-risca em nenhuma frase."""
    fonte = (Path(__file__).resolve().parents[1] / "app" / "services" / "contas_medicas" / "conferencia.py").read_text(
        encoding="utf-8"
    )

    assert chr(0x2014) not in fonte  # travessão
    assert chr(0x2013) not in fonte  # meia-risca
