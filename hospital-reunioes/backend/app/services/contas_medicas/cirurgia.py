"""Descrição cirúrgica e ficha anestésica lidas por código (issue #1118, PRD #1113, ADR 0070).

Descrição cirúrgica (documento do editor, título "DESCRIÇÃO CIRÚRGICA"): cirurgia
principal com código, procedimentos adicionais depois de `Código CBHPM/TUSS`, início
e término, peça para anatomopatológico e materiais consignados. Ficha anestésica:
início e fim da anestesia, técnica, gases com minutos, volátil, medicamentos com
quantidade (`[ 1 ] Alfentanila` e os anotados ao lado, `sugamadex 1`) e a
monitorização marcada com `[ x ]` (adendo v1.3, item 7).

As expressões vêm da referência do diretor (`local/contas-medicas/pacote-v1.3/
leitura/cirurgia.py`, fora do git). Função pura, sem log.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, time

MARCA_DA_DESCRICAO = re.compile(r"DESCRI[ÇC][ÃA]O\s+CIR[ÚU]RGICA|Cirurgia Principal:")


@dataclass(frozen=True)
class Procedimento:
    codigo: str
    descricao: str
    principal: bool


@dataclass(frozen=True)
class DescricaoCirurgica:
    paginas: tuple[int, ...]
    procedimentos: tuple[Procedimento, ...]
    inicio: datetime | None
    fim: datetime | None
    anatomopatologico: str | None
    consignados: str | None


def _data_e_hora(rx: str, texto: str) -> datetime | None:
    if m := re.search(rx + r"\s*(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2})", texto):
        try:
            return datetime.strptime(m.group(1), "%d/%m/%Y %H:%M")
        except ValueError:
            return None
    return None


def ler_descricao_cirurgica(texto: str, paginas: tuple[int, ...]) -> DescricaoCirurgica:
    procedimentos = []
    if m := re.search(r"Cirurgia Principal:\s*(.+?)\s*-\s*(\d{8})", texto):
        procedimentos.append(Procedimento(m.group(2), m.group(1).strip(), True))
    # A tabela pode repetir a principal: cada código entra uma vez.
    tabela = texto.split("Código CBHPM/TUSS", 1)[1] if "Código CBHPM/TUSS" in texto else ""
    for m in re.finditer(r"^\s*(\d{8})\s{2,}(\S.*?)\s*$", tabela, re.M):
        if m.group(1) not in {p.codigo for p in procedimentos}:
            procedimentos.append(Procedimento(m.group(1), m.group(2), False))
    peca = re.search(r"Quais\?\s*(.+)", texto) if re.search("anatomopatol", texto, re.I) else None
    consignados = re.search(r"justificados na folha de OPME:\s*\n\s*(.+)", texto)
    return DescricaoCirurgica(
        paginas=paginas,
        procedimentos=tuple(procedimentos),
        inicio=_data_e_hora(r"IN[ÍI]CIO DA CIRURGIA:", texto),
        fim=_data_e_hora(r"T[ÉE]RMINO DA CIRURGIA:", texto),
        anatomopatologico=peca.group(1).strip() if peca else None,
        consignados=consignados.group(1).strip() if consignados else None,
    )


@dataclass(frozen=True)
class Gas:
    gas: str
    litros_por_minuto: float
    minutos: int


@dataclass(frozen=True)
class MedicamentoDaFicha:
    nome: str
    quantidade: int
    # Escrito à mão ao lado ("sugamadex 1"), não marcado no campo da ficha.
    anotado: bool


@dataclass(frozen=True)
class FichaAnestesica:
    paginas: tuple[int, ...]
    data: date | None
    inicio: time | None
    fim: time | None
    tecnica: str | None
    gases: tuple[Gas, ...]
    volatil: str | None
    medicamentos: tuple[MedicamentoDaFicha, ...]
    monitorizacao: tuple[str, ...]


_HORARIOS_DA_ANESTESIA = re.compile(
    r"Hr\. Inicial Anestesia\s+Hr\. Final Anestesia\s+T[ée]cnica Anest[ée]sica\s*\n\s*"
    r"(\d{2}:\d{2})\s+(\d{2}:\d{2})\s+(.+)"
)
_GAS = re.compile(r"(O2|AR|N2O)\s+(\d+(?:,\d+)?)\s*L/min:\s*(\d+)\s*min")
_MEDICAMENTO_MARCADO = re.compile(r"\[\s*(\d+)\s*\]\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ%,.0-9 ]*?)(?=\s{2,}|\s*\[|\s*$)", re.M)
_MEDICAMENTO_ANOTADO = re.compile(r"^.*?\s{2,}([a-záéíóúç]+)\s+(\d+)\s*$", re.M)
_MONITOR_MARCADO = re.compile(r"\[\s*x\s*\]\s*([A-Za-zÀ-ÿ][A-Za-zÀ-ÿ .0-9-]*?)(?=\s{2,}|\s*\[|\s*$)", re.M | re.I)


def _hora(texto: str) -> time | None:
    try:
        return datetime.strptime(texto, "%H:%M").time()
    except ValueError:
        return None


def ler_ficha_anestesica(texto: str, paginas: tuple[int, ...], data: date | None) -> FichaAnestesica:
    horarios = _HORARIOS_DA_ANESTESIA.search(texto)
    volatil = re.search(r"Sevorane:\s*([\d,]+%)", texto)
    medicamentos = [
        MedicamentoDaFicha(m.group(2).strip(), int(m.group(1)), False) for m in _MEDICAMENTO_MARCADO.finditer(texto)
    ]
    medicamentos += [
        MedicamentoDaFicha(m.group(1), int(m.group(2)), True) for m in _MEDICAMENTO_ANOTADO.finditer(texto)
    ]
    return FichaAnestesica(
        paginas=paginas,
        data=data,
        inicio=_hora(horarios.group(1)) if horarios else None,
        fim=_hora(horarios.group(2)) if horarios else None,
        tecnica=horarios.group(3).strip() if horarios else None,
        gases=tuple(
            Gas(m.group(1), float(m.group(2).replace(",", ".")), int(m.group(3))) for m in _GAS.finditer(texto)
        ),
        volatil=f"sevoflurano {volatil.group(1)}" if volatil else None,
        medicamentos=tuple(medicamentos),
        monitorizacao=tuple(m.group(1).strip() for m in _MONITOR_MARCADO.finditer(texto)),
    )
