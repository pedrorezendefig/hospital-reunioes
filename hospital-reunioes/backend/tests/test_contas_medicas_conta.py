"""Leitura da Conta por código (issue #1116, PRD #1113, ADR 0070).

A fixture imita a saída do `pdftotext -layout` sobre o PDF "Fatura Individual"
do MV, uma string por página. É sintética: atendimento, guia, códigos e nomes
são fictícios, e PDF real nunca entra no repositório.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from app.services.contas_medicas_conta import (
    Conta,
    ErroLeitura,
    coluna_do_plano,
    detectar_tipo_do_arquivo,
    ler_conta,
)

PAGINA_1 = """\
HOSPITAL FICTICIO DE TESTE                                                         Página 1 de 2
                                   Fatura Individual

Atendimento: 900001          Conta: 700001          Tipo: INTERNACAO
Internação: 01/09/2026 08:30          Alta: 05/09/2026 14:00
Período da   01/09/2026 a 05/09/2026          Acomodação: ENFERMARIA
Procedimento: 30602076  MASTECTOMIA RADICAL UNILATERAL          CID: C50
Plano: Rioserv Max Qc ENF
Guia: 123456789

Resumo por grupo
HONORARIOS MEDICOS                                                               1.250,00
MEDICAMENTOS                                                                       124,87

HONORARIOS MEDICOS
43  CENTRO CIRURGICO
    Grupo de Procedimento: 01 PROCEDIMENTOS CIRURGICOS
02/09/2026  31009999  HONORARIO DO CIRURGIAO PRINCIPAL        UN      100,00%    1,00   1.250,00   1.250,00
Total do Setor:                                                                  1.250,00

MEDICAMENTOS
12  ENFERMARIA 3 ANDAR
    Grupo de Procedimento: 05 MEDICAMENTOS
01/09/2026  90012345  DIPIRONA SODICA 500MG/ML SOL INJ 2ML    AMP     100,00%    3,00       4,35      13,05
02/09/2026  90054321  CEFAZOLINA SODICA 1G PO P/ SOL INJ      FR      100,00%    2,00      18,90      37,80
                      FRASCO-AMPOLA
Total do Setor:                                                                     50,85
43  CENTRO CIRURGICO
    Grupo de Procedimento: 05 MEDICAMENTOS
02/09/2026  90011111  ONDANSETRONA 2MG/ML SOL INJ 4ML         AMP     100,00%    1,00       9,72       9,72
Total do Setor:                                                                      9,72
"""

PAGINA_2 = """\
HOSPITAL FICTICIO DE TESTE                                                         Página 2 de 2
Atendimento: 900001          Conta: 700001
51  UTI ADULTO
    Grupo de Procedimento: 05 MEDICAMENTOS
03/09/2026  90022222  PANTOPRAZOL SODICO 40MG PO LIOF         FR AMP  100,00%    2,00      32,15      64,30
                      P/ SOL INJ
Total do Setor:                                                                     64,30

Total da Conta:                                                                  1.374,87
"""


def _conta(paginas: list[str]) -> Conta:
    conta = ler_conta(paginas)
    assert isinstance(conta, Conta), conta
    return conta


def test_conta_fatura_individual_e_lida_com_todos_os_campos():
    conta = _conta([PAGINA_1, PAGINA_2])

    assert conta.atendimento == "900001"
    assert conta.conta == "700001"
    assert conta.tipo == "INTERNACAO"
    assert conta.internacao == datetime(2026, 9, 1, 8, 30)
    assert conta.alta == datetime(2026, 9, 5, 14, 0)
    assert conta.periodo_inicio == date(2026, 9, 1)
    assert conta.periodo_fim == date(2026, 9, 5)
    assert conta.acomodacao == "ENFERMARIA"
    assert conta.procedimento_codigo == "30602076"
    assert conta.procedimento_descricao == "MASTECTOMIA RADICAL UNILATERAL"
    assert conta.plano == "Rioserv Max Qc ENF"
    assert conta.guia == "123456789"
    assert conta.total == Decimal("1374.87")

    lidos = [
        (
            i.pagina,
            i.data,
            i.codigo,
            i.descricao,
            i.unidade,
            i.percentual,
            i.quantidade,
            i.unitario,
            i.total,
            i.grupo,
            i.setor_codigo,
            i.setor,
            i.grupo_procedimento,
        )
        for i in conta.itens
    ]
    assert lidos == [
        (
            1,
            date(2026, 9, 2),
            "31009999",
            "HONORARIO DO CIRURGIAO PRINCIPAL",
            "UN",
            Decimal("100.00"),
            Decimal("1.00"),
            Decimal("1250.00"),
            Decimal("1250.00"),
            "HONORARIOS MEDICOS",
            "43",
            "CENTRO CIRURGICO",
            "PROCEDIMENTOS CIRURGICOS",
        ),
        (
            1,
            date(2026, 9, 1),
            "90012345",
            "DIPIRONA SODICA 500MG/ML SOL INJ 2ML",
            "AMP",
            Decimal("100.00"),
            Decimal("3.00"),
            Decimal("4.35"),
            Decimal("13.05"),
            "MEDICAMENTOS",
            "12",
            "ENFERMARIA 3 ANDAR",
            "MEDICAMENTOS",
        ),
        (
            1,
            date(2026, 9, 2),
            "90054321",
            "CEFAZOLINA SODICA 1G PO P/ SOL INJ FRASCO-AMPOLA",
            "FR",
            Decimal("100.00"),
            Decimal("2.00"),
            Decimal("18.90"),
            Decimal("37.80"),
            "MEDICAMENTOS",
            "12",
            "ENFERMARIA 3 ANDAR",
            "MEDICAMENTOS",
        ),
        (
            1,
            date(2026, 9, 2),
            "90011111",
            "ONDANSETRONA 2MG/ML SOL INJ 4ML",
            "AMP",
            Decimal("100.00"),
            Decimal("1.00"),
            Decimal("9.72"),
            Decimal("9.72"),
            "MEDICAMENTOS",
            "43",
            "CENTRO CIRURGICO",
            "MEDICAMENTOS",
        ),
        (
            2,
            date(2026, 9, 3),
            "90022222",
            "PANTOPRAZOL SODICO 40MG PO LIOF P/ SOL INJ",
            "FR AMP",
            Decimal("100.00"),
            Decimal("2.00"),
            Decimal("32.15"),
            Decimal("64.30"),
            "MEDICAMENTOS",
            "51",
            "UTI ADULTO",
            "MEDICAMENTOS",
        ),
    ]


def test_procedimento_do_cabecalho_nao_aparece_entre_os_itens():
    conta = _conta([PAGINA_1, PAGINA_2])

    assert conta.procedimento_codigo == "30602076"
    assert "30602076" not in {i.codigo for i in conta.itens}
    assert not any("MASTECTOMIA" in i.descricao for i in conta.itens)


def test_total_que_nao_fecha_com_a_soma_dos_itens_devolve_erro_de_leitura():
    # Um item que a expressão não pega: a soma fica 64,30 abaixo do total.
    pagina_2_com_item_ilegivel = PAGINA_2.replace("FR AMP  100,00%", "FR AMP  100,00 %")

    resultado = ler_conta([PAGINA_1, pagina_2_com_item_ilegivel])

    assert resultado == ErroLeitura("Não consegui ler a conta inteira")


def test_item_em_que_quantidade_vezes_unitario_nao_fecha_devolve_erro_de_leitura():
    # 3 x 4,35 = 13,05. Lido como 13,15 e com o total da conta acompanhando,
    # a soma fecha e só a conferência por item pega.
    pagina_1 = PAGINA_1.replace("4,35      13,05", "4,35      13,15")
    pagina_2 = PAGINA_2.replace("1.374,87", "1.374,97")

    resultado = ler_conta([pagina_1, pagina_2])

    assert resultado == ErroLeitura("Não consegui ler a conta inteira")


def test_diferenca_de_um_centavo_fica_dentro_da_tolerancia():
    pagina_2 = PAGINA_2.replace("1.374,87", "1.374,88")

    assert _conta([PAGINA_1, pagina_2]).total == Decimal("1374.88")


def test_conta_sem_total_devolve_erro_de_leitura():
    pagina_2 = PAGINA_2.replace("Total da Conta:", "Total geral:")

    assert ler_conta([PAGINA_1, pagina_2]) == ErroLeitura("Não consegui ler a conta inteira")
