"""Prescrição do MV PEP lida por código (issue #1118, PRD #1113, ADR 0070).

A prescrição (médica, urgência, nutricional, enfermagem e solicitação de exames)
sai do MV como tabela: seção, número do item, nome, dose, frequência, coluna SN,
via, horários aprazados, observação e componentes (`|-> SERINGA ...`). Aqui cada
prescrição vira itens, e os itens de todas viram um registro por item com os dias
em que foi prescrito e as doses de cada dia.

A leitura é por linha do `pdftotext -layout`, como na referência do diretor
(`local/contas-medicas/pacote-v1.3/leitura/prescricao.py`, fora do git). Ler pela
coordenada das colunas é pendência registrada no PRD (#1133). Função pura, sem log:
o texto do prontuário nunca vai para log (ADR 0070, decisão 8).
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

_SECAO = re.compile(r"^\s*(\S.*?)\s{2,}Dose Padr[ãa]o\s+Dura[çc][ãa]o")
_ITEM = re.compile(r"^\s{0,10}(\d{1,3})\s(\S.*)$")
# Fim da tabela: rodapé, assinatura digital, cabeçalho do sistema.
_FIM = re.compile(r"^(C[óo]digo:|Documento assinado|MV \||HOSPITAL S|Impress[ãa]o|NOTA: TODAS)")
# "CRM : 52998": quem assina vem na linha de cima, e não é item.
_CONSELHO = re.compile(r"^\s*(CRM|CRN|COREN|CRF|CREFITO)\s*:")
_PEDIDO = re.compile(r"\s*;\s*(?:Pedido|Exame):\s*(\d+)")
_DIA_DO_ANTIMICROBIANO = re.compile(r"^\(D\d+/\d+\)\s*")
_GENERICO = re.compile(r"\(([A-ZÀ-Ý][A-ZÀ-Ý ,+]{3,})\)\s*$")
_SUSPENSO = re.compile(r"Suspenso dia\.?:?\s*\d+", re.I)
_VIAS = r"(?:EV|VO|SC|IM|SNE|SNG|IN|TOP|VR|SL|OF|INAL|DT|ID|IT|RET|VAG)"
_VIA = re.compile(rf"(?:^|\s)({_VIAS})(?=\s|$)")
_SE_NECESSARIO = re.compile(rf"(?:^|\s)S\s+{_VIAS}\b|\bACM\b")
_HORARIO = re.compile(r"(?:^|\s)\.\s(\d{2})(?=\s|$)")
_DOSE = re.compile(r"^\d+(?:[.,]\d+)?\s+(?!X\b)[A-ZÀ-Ý][A-ZÀ-Ý/.]*$")
_FREQUENCIA = re.compile(
    r"\d+HS/\d+(?:HS)?|\d\s*X AO DIA|\bM/N\b|\bMANHA\b|\bNOITE\b|\bTARDE\b|\bACM\b|\bCONTINUA\b|\bAGORA\b"
    r"|\bDOSE UNICA\b|\bAS\s+\d{2}:\d{2}|\d{2}:\d{2}HS"
)
# Frequência → doses por dia. ACM, CONTINUA e "se necessário" puro: sem número.
_DOSES_DA_FREQUENCIA = [
    (r"24HS/24", 1),
    (r"12HS/12", 2),
    (r"8HS/8", 3),
    (r"6HS/6", 4),
    (r"4HS/4", 6),
    (r"3HS/3", 8),
    (r"2HS/2", 12),
    (r"1HS/1", 24),
    (r"(\d)\s*X AO DIA", None),
    (r"M/N", 2),
    (r"MANHA|NOITE|TARDE|AS\s+\d{2}:\d{2}|\d{2}:\d{2}HS|AGORA|DOSE UNICA", 1),
]


@dataclass(frozen=True)
class ItemPrescrito:
    secao: str | None
    numero: int
    nome: str
    generico: str | None
    dose: str | None
    frequencia: str | None
    via: str | None
    horarios: tuple[str, ...]
    doses_por_dia: int | None
    se_necessario: bool
    suspenso: bool
    obs: str
    componentes: tuple[str, ...]
    pedido: str | None
    # As colunas depois do nome, numa linha só (o que a IA lê no lugar das páginas).
    colunas: str
    # Página do PDF onde o item começa: a evidência que o Guia mostra.
    pagina: int

    @property
    def exame(self) -> bool:
        return (self.secao or "").startswith("EXAMES")


def _doses_por_dia(colunas: str) -> int | None:
    """Horários aprazados ('. 06 . 14 . 22') têm prioridade; senão, a frequência."""
    if horarios := _HORARIO.findall(colunas):
        return len(horarios)
    for rx, doses in _DOSES_DA_FREQUENCIA:
        if m := re.search(rx, colunas):
            return int(m.group(1)) if doses is None else doses
    return None


@dataclass
class _Rascunho:
    secao: str | None
    numero: int
    nome: str
    celulas: list[str]
    pagina: int
    obs: str = ""
    componentes: list[str] = field(default_factory=list)


def _celulas(texto: str) -> list[str]:
    return [c for c in re.split(r"\s{2,}", texto.strip()) if c]


def _rascunhos(paginas: Sequence[tuple[int, str]]) -> list[_Rascunho]:
    itens: list[_Rascunho] = []
    secao = None
    atual: _Rascunho | None = None
    em_preparo = False
    for numero_da_pagina, texto in paginas:
        linhas = texto.split("\n")
        assinatura = {i - 1 for i, linha in enumerate(linhas) if _CONSELHO.match(linha)}
        dentro = False
        for i, bruta in enumerate(linhas):
            linha = bruta.strip()
            if not linha or i in assinatura:
                continue
            if m := _SECAO.match(bruta):
                secao, dentro, atual = m.group(1).strip(), True, None
                continue
            if not dentro:
                continue
            if _FIM.match(linha) or _CONSELHO.match(linha):
                dentro, atual = False, None
                continue
            if (m := _ITEM.match(bruta)) and not linha.startswith("|->"):
                nome, *celulas = _celulas(m.group(2))
                atual = _Rascunho(secao, int(m.group(1)), nome, celulas, numero_da_pagina)
                itens.append(atual)
                em_preparo = False
                continue
            if atual is None:
                continue
            if linha.startswith("|->"):
                atual.componentes.append(re.sub(r"\s{2,}", " ", linha[3:].strip()))
                em_preparo = False
                continue
            if linha.startswith(("Obs.:", "Justificativa:")):
                # Em exame, "Obs.: Preparo:" é instrução de coleta: sai, com as linhas seguintes.
                em_preparo = "Preparo:" in linha
                if not em_preparo:
                    atual.obs += " " + linha.removeprefix("Obs.:")
                continue
            if em_preparo:
                continue
            recuo = len(bruta) - len(bruta.lstrip())
            celulas = _celulas(linha)
            if atual.componentes and recuo > 10:
                atual.componentes[-1] += " " + celulas[0]
            elif atual.obs and not re.search(r"\dHS/|\.\s\d{2}", linha):
                atual.obs += " " + linha
            elif recuo < 14:  # continuação do nome, no mesmo recuo
                atual.nome += " " + celulas[0]
                atual.celulas += celulas[1:]
            else:
                atual.celulas += celulas
    return itens


def _item(rascunho: _Rascunho) -> ItemPrescrito:
    nome = re.sub(r"\s+", " ", rascunho.nome).strip()
    juntas = " ".join(rascunho.celulas)
    pedido = m.group(1) if (m := _PEDIDO.search(f"{nome} {juntas}")) else None
    nome = _DIA_DO_ANTIMICROBIANO.sub("", _PEDIDO.sub("", nome)).strip()
    colunas = re.sub(r"\s+", " ", _PEDIDO.sub("", juntas)).strip()
    exame = (rascunho.secao or "").startswith("EXAMES")
    generico = m.group(1).strip() if not exame and (m := _GENERICO.search(nome)) else None
    dose = next((c for c in rascunho.celulas if _DOSE.match(c)), None)
    frequencia = m.group(0) if (m := _FREQUENCIA.search(colunas)) else None
    return ItemPrescrito(
        secao=rascunho.secao,
        numero=rascunho.numero,
        nome=nome,
        generico=generico,
        dose=dose,
        frequencia=frequencia,
        via=m.group(1) if (m := _VIA.search(colunas)) else None,
        horarios=tuple(_HORARIO.findall(colunas)),
        doses_por_dia=_doses_por_dia(colunas),
        se_necessario=_SE_NECESSARIO.search(colunas) is not None,
        suspenso=_SUSPENSO.search(f"{nome} {colunas}") is not None,
        obs=re.sub(r"\s+", " ", rascunho.obs).strip(),
        componentes=tuple(rascunho.componentes),
        pedido=pedido,
        colunas=colunas,
        pagina=rascunho.pagina,
    )


def ler_itens(paginas: Sequence[tuple[int, str]]) -> list[ItemPrescrito]:
    """`paginas`: (número da página no PDF, texto) de UMA prescrição, na ordem."""
    return [_item(rascunho) for rascunho in _rascunhos(paginas)]
