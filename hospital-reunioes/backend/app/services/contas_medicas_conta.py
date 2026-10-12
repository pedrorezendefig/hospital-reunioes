"""Leitura da Conta por código (issue #1116, PRD #1113, ADR 0070).

A Conta chega como o PDF "Fatura Individual" do faturamento do MV, e o
extrator (`contas_medicas_extrator`) devolve o texto do `pdftotext -layout`,
uma string por página. Este módulo é puro: recebe esse texto e devolve a Conta
lida ou um `ErroLeitura`. As expressões vêm do código de referência do diretor
(`local/contas-medicas/pacote-v1.3/leitura/conta.py`, fora do git), calibrado
nas contas reais dele.

Layout, de cima para baixo: cabeçalho do Atendimento; resumo por grupo; itens
agrupados por grupo da conta (HONORARIOS MEDICOS, DIARIAS, MEDICAMENTOS...),
por setor (`43  CENTRO CIRURGICO`) e por "Grupo de Procedimento". Cada item tem
data, código, descrição (que pode continuar na linha de baixo), unidade,
percentual, quantidade, unitário e total. No fim, "Total da Conta".

A leitura só vale com a conferência da leitura: a soma dos itens fecha com o
total e cada item fecha quantidade vezes unitário, com tolerância de R$ 0,01.
Sem isso a Conta volta como `ErroLeitura`, porque um item que a expressão não
pegou some em silêncio e o Guia sairia com cara de completo.

O procedimento do cabeçalho não é item lançado e não define pacote (memória
ASSIM, ASSIM-PRI-12): ele fica nos campos da Conta, nunca entre os itens.

O texto da Conta tem dado do paciente: nada daqui vai para log.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.services.contas_medicas_extrator import ErroLeitura

__all__ = [
    "Conta",
    "ErroLeitura",
    "ItemConta",
    "MENSAGEM_CONTA_INCOMPLETA",
    "coluna_do_plano",
    "detectar_tipo_do_arquivo",
    "ler_conta",
]

MENSAGEM_CONTA_INCOMPLETA = "Não consegui ler a conta inteira"
TOLERANCIA = Decimal("0.01")
CENTAVO = Decimal("0.01")

# Sufixos de acomodação no fim do nome do Plano (memória ASSIM, `comparacao_do_nome`).
SUFIXOS_DE_ACOMODACAO = frozenset({"ENF", "APT"})

GRUPOS_DA_CONTA = frozenset(
    {
        "HONORARIOS MEDICOS",
        "DIARIAS",
        "TAXAS",
        "GASES MEDICINAIS",
        "MEDICAMENTOS",
        "MATERIAIS DESCARTAVEIS",
        "PACOTES ESPECIAIS",
        "SADT",
        "EXAMES",
        "OPME",
        "HEMODERIVADOS",
        "DIETAS",
    }
)

_ITEM = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(\d{6,10})\s+(.+?)\s{2,}(\S+(?: \S+)?)\s+(\d{1,3},\d{2})%"
    r"\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)\s*$"
)
_SETOR = re.compile(r"^(\d{1,4})\s{2,}(\S.*?)\s*$")
_GRUPO_DE_PROCEDIMENTO = re.compile(r"^\s*Grupo de Procedimento:\s*(\d+)\s+(.*?)\s*$")
_FIM_DA_CONTINUACAO = re.compile(r"Total|HOSPITAL|P[áa]gina")

_CABECALHO = {
    "atendimento": re.compile(r"Atendimento:\s*(\d+)"),
    "conta": re.compile(r"Conta:\s*(\d+)"),
    "tipo": re.compile(r"Tipo:\s*(.+?)\s*$", re.M),
    "internacao": re.compile(r"Interna[çc][ãa]o:\s*(\d{2}/\d{2}/\d{4} \d{2}:\d{2})"),
    "alta": re.compile(r"Alta:\s*(\d{2}/\d{2}/\d{4} \d{2}:\d{2})"),
    "periodo": re.compile(r"Per[íi]odo da\s+(\d{2}/\d{2}/\d{4}) a (\d{2}/\d{2}/\d{4})"),
    "acomodacao": re.compile(r"Acomoda[çc][ãa]o:\s*(.+?)\s*$", re.M),
    "procedimento": re.compile(r"Procedimento:\s*(\d+)\s+(.+?)(?:\s+CID:|\s*$)", re.M),
    "plano": re.compile(r"Plano:\s*(.+?)\s*$", re.M),
    "guia": re.compile(r"Guia:\s*(\d+)"),
    "total": re.compile(r"Total da Conta:\s*([\d.,]+)"),
}


@dataclass(frozen=True)
class ItemConta:
    pagina: int
    data: date
    codigo: str
    descricao: str
    unidade: str
    percentual: Decimal
    quantidade: Decimal
    unitario: Decimal
    total: Decimal
    grupo: str | None
    setor_codigo: str | None
    setor: str | None
    grupo_procedimento: str | None


@dataclass(frozen=True)
class Conta:
    atendimento: str
    conta: str | None
    tipo: str | None
    internacao: datetime | None
    alta: datetime | None
    periodo_inicio: date | None
    periodo_fim: date | None
    acomodacao: str | None
    procedimento_codigo: str | None
    procedimento_descricao: str | None
    plano: str
    guia: str | None
    total: Decimal
    itens: tuple[ItemConta, ...]


def _numero(texto: str) -> Decimal:
    return Decimal(texto.replace(".", "").replace(",", "."))


def _data(texto: str) -> date:
    return datetime.strptime(texto, "%d/%m/%Y").date()


def _data_hora(texto: str | None) -> datetime | None:
    return datetime.strptime(texto, "%d/%m/%Y %H:%M") if texto else None


def _cabecalho(texto: str) -> dict[str, tuple[str, ...]]:
    achados = {}
    for campo, expressao in _CABECALHO.items():
        m = expressao.search(texto)
        if m:
            achados[campo] = tuple(g.strip() for g in m.groups())
    return achados


def _itens(texto_por_pagina: Sequence[str]) -> list[ItemConta]:
    itens: list[dict] = []
    grupo = setor_codigo = setor = grupo_procedimento = None
    for numero, texto in enumerate(texto_por_pagina, start=1):
        ultimo = None  # descrição não continua de uma página para a outra
        for bruta in texto.split("\n"):
            linha = bruta.strip()
            if not linha:
                continue
            if linha in GRUPOS_DA_CONTA:
                grupo, ultimo = linha, None
                continue
            m = _GRUPO_DE_PROCEDIMENTO.match(bruta)
            if m:
                grupo_procedimento, ultimo = m.group(2), None
                continue
            m = _ITEM.match(linha)
            if m:
                dia, codigo, descricao, unidade, percentual, quantidade, unitario, total = m.groups()
                ultimo = {
                    "pagina": numero,
                    "data": _data(dia),
                    "codigo": codigo,
                    "descricao": descricao.strip(),
                    "unidade": unidade,
                    "percentual": _numero(percentual),
                    "quantidade": _numero(quantidade),
                    "unitario": _numero(unitario),
                    "total": _numero(total),
                    "grupo": grupo,
                    "setor_codigo": setor_codigo,
                    "setor": setor,
                    "grupo_procedimento": grupo_procedimento,
                }
                itens.append(ultimo)
                continue
            m = _SETOR.match(linha)
            if m and grupo and not linha.startswith("Total"):
                setor_codigo, setor, ultimo = m.group(1), m.group(2), None
                continue
            if ultimo and bruta.startswith("   ") and not _FIM_DA_CONTINUACAO.search(linha):
                ultimo["descricao"] += " " + linha
                continue
            if linha.startswith("Total"):
                ultimo = None
    return [ItemConta(**i) for i in itens]


def _fecha(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) <= TOLERANCIA


def _conferencia_da_leitura(itens: Sequence[ItemConta], total: Decimal) -> bool:
    """Soma dos itens igual ao total e, em cada item, quantidade vezes unitário igual ao total."""
    if not itens or not _fecha(sum((i.total for i in itens), Decimal(0)), total):
        return False
    return all(_fecha((i.quantidade * i.unitario).quantize(CENTAVO, ROUND_HALF_UP), i.total) for i in itens)


def ler_conta(texto_por_pagina: Sequence[str]) -> Conta | ErroLeitura:
    """Lê a Conta do texto do `pdftotext -layout`, uma string por página.

    Devolve `ErroLeitura` quando falta o que identifica a Conta (atendimento,
    plano, total) ou quando a conferência da leitura não fecha.
    """
    cab = _cabecalho("\n".join(texto_por_pagina))
    if not {"atendimento", "plano", "total"} <= cab.keys():
        return ErroLeitura(MENSAGEM_CONTA_INCOMPLETA)
    itens = _itens(texto_por_pagina)
    total = _numero(cab["total"][0])
    if not _conferencia_da_leitura(itens, total):
        return ErroLeitura(MENSAGEM_CONTA_INCOMPLETA)
    periodo = cab.get("periodo")
    procedimento = cab.get("procedimento")
    return Conta(
        atendimento=cab["atendimento"][0],
        conta=cab.get("conta", (None,))[0],
        tipo=cab.get("tipo", (None,))[0],
        internacao=_data_hora(cab.get("internacao", (None,))[0]),
        alta=_data_hora(cab.get("alta", (None,))[0]),
        periodo_inicio=_data(periodo[0]) if periodo else None,
        periodo_fim=_data(periodo[1]) if periodo else None,
        acomodacao=cab.get("acomodacao", (None,))[0],
        procedimento_codigo=procedimento[0] if procedimento else None,
        procedimento_descricao=procedimento[1] if procedimento else None,
        plano=cab["plano"][0],
        guia=cab.get("guia", (None,))[0],
        total=total,
        itens=tuple(itens),
    )


def _normalizar(texto: str) -> str:
    """Sem acento, em maiúscula e com espaço simples."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return " ".join(sem_acento.upper().split())


def _sem_sufixo_de_acomodacao(plano: str) -> str:
    palavras = plano.split()
    while len(palavras) > 1 and palavras[-1] in SUFIXOS_DE_ACOMODACAO:
        palavras.pop()
    return " ".join(palavras)


def coluna_do_plano(plano: str, lista_da_memoria: Sequence[str]) -> Literal["CARIOCA", "COMUM"]:
    """Coluna de preço do Plano da Conta: CARIOCA se está na lista da memória, senão COMUM.

    Compara sem acento, sem diferença de maiúscula e ignorando o sufixo de
    acomodação (`comparacao_do_nome` da memória ASSIM).
    """
    lista = {_sem_sufixo_de_acomodacao(_normalizar(nome)) for nome in lista_da_memoria}
    return "CARIOCA" if _sem_sufixo_de_acomodacao(_normalizar(plano)) in lista else "COMUM"


TipoDoArquivo = Literal["CONTA", "PRONTUARIO", "DESCONHECIDO"]


def detectar_tipo_do_arquivo(primeira_pagina: str) -> TipoDoArquivo:
    """Conta ou Prontuário pela primeira página do PDF.

    O Prontuário vem primeiro porque a assinatura dele é a mais específica: a
    capa é a "Declaração de recebimento de prontuário". "Fatura" é palavra
    inteira, para "faturamento" num relatório qualquer não virar Conta.
    """
    texto = _normalizar(primeira_pagina)
    if "DECLARACAO DE RECEBIMENTO DE PRONTUARIO" in texto:
        return "PRONTUARIO"
    if re.search(r"\bFATURA\b", texto):
        return "CONTA"
    return "DESCONHECIDO"
