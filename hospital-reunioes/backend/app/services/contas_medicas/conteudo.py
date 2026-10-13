"""Leitura do Prontuário por código: o conteúdo (issue #1118, PRD #1113, ADR 0070).

Sobre os documentos que a estrutura monta (`prontuario.ler_prontuario`, #1117),
o código lê o que sustenta cobrança sem passar pela IA: a prescrição, o balanço
hídrico, as glicemias, a internação e a alta, o setor de cada dia com as
transferências, a descrição cirúrgica, a ficha anestésica e a guia TISS.

Entra o mesmo texto por página que a estrutura leu e o Prontuário que ela devolveu;
as páginas de cada documento são lidas pelo número. Função pura: sem banco, sem
rede, sem log (o texto do prontuário nunca vai para log, ADR 0070, decisão 8).
Os campos de texto livre que saem daqui (observação da prescrição, por exemplo)
não estão desidentificados: quem os mandar à IA passa por `desidentificar`.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING

from app.services.contas_medicas.cirurgia import (
    MARCA_DA_DESCRICAO,
    DescricaoCirurgica,
    FichaAnestesica,
    ler_descricao_cirurgica,
    ler_ficha_anestesica,
)
from app.services.contas_medicas.prescricao import (
    ExamePedido,
    ItemConsolidado,
    Prescricao,
    consolidar,
    exames_pedidos,
    ler_itens,
    texto_por_coluna,
)
from app.services.contas_medicas.prontuario import _RODAPE_GLOBAL, Documento, Prontuario, _sem_acento

if TYPE_CHECKING:
    from app.services.contas_medicas_extrator import Palavra

# ----------------------------------------------------------------------------------
# Balanço hídrico e glicemias
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class LinhaDoBalanco:
    item: str
    via: str | None
    # Quantos horários têm valor; o total é o último número da linha (mL nos ganhos).
    lancamentos: int
    total: float


@dataclass(frozen=True)
class Balanco:
    data: date | None
    setor: str | None
    paginas: tuple[int, ...]
    ganhos: tuple[LinhaDoBalanco, ...]
    perdas: tuple[LinhaDoBalanco, ...]
    glicemias: int


@dataclass(frozen=True)
class GlicemiasDoDia:
    """Glicemias de um dia por fonte. A mesma glicemia pode estar na aferição e no
    balanço: somar as duas fontes conta duas vezes, quem confere decide."""

    data: date
    familia: str
    quantidade: int
    paginas: tuple[int, ...]


_VIAS_DO_BALANCO = {"EV", "VO", "SNE", "SNG", "SC", "IM", "GTT", "SOG", "IV"}
_NUMERO = re.compile(r"-?\d+(?:,\d+)?")


def _numero(texto: str) -> float:
    return float(texto.replace(",", "."))


def _ler_balanco(documento: Documento, primeira_pagina: str) -> Balanco:
    """Só a primeira página: a segunda traz os usuários e a assinatura (adendo v1.2, item 6.1).
    A hora de cada valor exige a coluna; aqui saem item, via, lançamentos e total."""
    blocos: dict[str, list[LinhaDoBalanco]] = {"GANHOS": [], "PERDAS": []}
    bloco = None
    glicemias = 0
    for linha in primeira_pagina.split("\n"):
        texto = linha.strip()
        if texto.startswith(("GANHOS", "PERDAS")):
            bloco = texto[:6]
            continue
        if texto.startswith(("SINAIS VITAIS", "Itens de Sinais")):
            bloco = "SINAIS VITAIS"
            continue
        if not texto or texto.startswith(("Total", "EVOLUÇÃO")):
            continue
        palavras = texto.split()
        k = len(palavras)
        while k > 0 and _NUMERO.fullmatch(palavras[k - 1]):
            k -= 1
        numeros = palavras[k:]
        if bloco == "SINAIS VITAIS":
            if texto.upper().startswith("GLICEMIA"):
                glicemias += len(numeros)
        elif bloco in blocos and numeros:
            via = palavras[k - 1] if k > 0 and palavras[k - 1] in _VIAS_DO_BALANCO else None
            item = " ".join(palavras[: k - 1] if via else palavras[:k]).strip(" ,")
            if item:
                blocos[bloco].append(LinhaDoBalanco(item, via, len(numeros) - 1, _numero(numeros[-1])))
    return Balanco(
        data=documento.data,
        setor=documento.setor,
        paginas=documento.paginas,
        ganhos=tuple(blocos["GANHOS"]),
        perdas=tuple(blocos["PERDAS"]),
        glicemias=glicemias,
    )


_GLICEMIA_AFERIDA = re.compile(r"^\s*GLICEMIA\b[^\n]*\d", re.M)


def _glicemias(afericoes: list[tuple[Documento, str]], balancos: list[Balanco]) -> tuple[GlicemiasDoDia, ...]:
    fontes = [(d.data, "AFERICAO", len(_GLICEMIA_AFERIDA.findall(texto)), d.paginas) for d, texto in afericoes]
    fontes += [(b.data, "BALANCO", b.glicemias, b.paginas[:1]) for b in balancos]
    por_dia: dict[tuple[date, str], tuple[int, tuple[int, ...]]] = {}
    for data, familia, quantidade, paginas in fontes:
        if quantidade and data:
            antes, ja_lidas = por_dia.get((data, familia), (0, ()))
            por_dia[data, familia] = (antes + quantidade, ja_lidas + paginas)
    return tuple(
        GlicemiasDoDia(data, familia, quantidade, paginas)
        for (data, familia), (quantidade, paginas) in sorted(por_dia.items())
    )


# ----------------------------------------------------------------------------------
# Internação e alta (adendo v1.2, item 8)
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Internacao:
    entrada: datetime | None
    alta: datetime | None
    motivo_alta: str | None
    acomodacao_na_admissao: str | None
    leito_na_admissao: str | None


_DATA_E_HORA = r"(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"
_INTERNACAO_DA_PRESCRICAO = re.compile(r"Interna[çc][ãa]o\.+:\s*" + _DATA_E_HORA)
_ATENDIMENTO_DO_RESUMO = re.compile(r"DATA DE ATENDIMENTO:\s*" + _DATA_E_HORA)
_ALTA = re.compile(r"DATA DA ALTA\s*-\s*" + _DATA_E_HORA)
_MOTIVO_DA_ALTA = re.compile(r"MOTIVO DA ALTA:\s*(\S.*?)\s*$", re.M)
_ADMISSAO = re.compile(r"Acomoda[çc][ãa]o:\s*(.*?)\s+Leito:\s*(\S+)\s+Unid\. Interna[çc][ãa]o:")


def _data_e_hora(rx: re.Pattern[str], textos: list[str]) -> datetime | None:
    for texto in textos:
        if m := rx.search(texto):
            try:
                return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M")
            except ValueError:
                continue
    return None


def _ler_internacao(por_familia: dict[str, list[str]]) -> Internacao:
    """Internação: `Internação.:` da prescrição; sem prescrição, `DATA DE ATENDIMENTO:` do
    resumo de alta. Alta e motivo: resumo de alta. Acomodação e leito: admissão na unidade."""
    resumos = por_familia.get("RESUMO_ALTA", [])
    entrada = _data_e_hora(_INTERNACAO_DA_PRESCRICAO, por_familia.get("PRESCRICAO", []))
    motivo = next((m.group(1) for texto in resumos if (m := _MOTIVO_DA_ALTA.search(texto))), None)
    admissao = next((m for texto in por_familia.get("ADMISSAO_UNIDADE", []) if (m := _ADMISSAO.search(texto))), None)
    return Internacao(
        entrada=entrada or _data_e_hora(_ATENDIMENTO_DO_RESUMO, resumos),
        alta=_data_e_hora(_ALTA, resumos),
        motivo_alta=motivo,
        acomodacao_na_admissao=admissao.group(1).strip() if admissao else None,
        leito_na_admissao=admissao.group(2) if admissao else None,
    )


# ----------------------------------------------------------------------------------
# Setor por dia e movimentações (adendo v1.2, item 8)
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Movimentacao:
    """No formato que o contador de diárias consome (#1115): em ordem, a INTERNACAO,
    zero ou mais TRANSFERENCIA_SETOR e a saída (ALTA, OBITO ou TRANSFERENCIA_HOSPITAL),
    cada uma com data e hora e o setor (o de destino; na saída, o último). Sem resumo
    de alta não há saída: quem tem o período da Conta fecha com EM_CURSO."""

    tipo: str
    data_hora: datetime
    setor: str | None
    # Transferência de setor: o prontuário não traz a hora exata, só a janela entre o
    # último documento no setor antigo e o primeiro no novo; `data_hora` é o fim dela.
    janela: tuple[datetime, datetime] | None = None


def _setor_por_dia(documentos: Sequence[Documento]) -> dict[date, tuple[str, ...]]:
    """O setor é sempre a unidade (prescrição, SAE, balanço, admissão): o leito muda sem
    transferência e o campo `Cobertura:` da prescrição não acompanha a mudança."""
    por_dia: dict[date, tuple[str, ...]] = {}
    for d in documentos:
        if d.setor and d.data and d.setor not in por_dia.get(d.data, ()):
            por_dia[d.data] = por_dia.get(d.data, ()) + (d.setor,)
    return por_dia


def _tipo_da_saida(motivo: str | None) -> str:
    motivo = _sem_acento(motivo or "").upper()
    if "OBITO" in motivo:
        return "OBITO"
    if "TRANSF" in motivo:
        return "TRANSFERENCIA_HOSPITAL"
    return "ALTA"


def _movimentacoes(internacao: Internacao, documentos: Sequence[Documento]) -> tuple[Movimentacao, ...]:
    if internacao.entrada is None:
        return ()
    # Só documento com hora marca a janela: o balanço tem data sem hora. E só o que cabe
    # entre a internação e a alta: registro feito depois da alta não é transferência, e
    # o contador recusa movimentação fora de ordem.
    datados = sorted((datetime.combine(d.data, d.hora), d.setor) for d in documentos if d.setor and d.data and d.hora)
    fim = internacao.alta or datetime.max
    linha_do_tempo = [(quando, setor) for quando, setor in datados if internacao.entrada <= quando <= fim]
    setor = linha_do_tempo[0][1] if linha_do_tempo else None
    movimentacoes = [Movimentacao("INTERNACAO", internacao.entrada, setor)]
    ultimo_no_setor = internacao.entrada
    for quando, novo in linha_do_tempo:
        if novo != setor:
            movimentacoes.append(Movimentacao("TRANSFERENCIA_SETOR", quando, novo, (ultimo_no_setor, quando)))
            setor = novo
        ultimo_no_setor = quando
    if internacao.alta:
        movimentacoes.append(Movimentacao(_tipo_da_saida(internacao.motivo_alta), internacao.alta, setor))
    return tuple(movimentacoes)


# ----------------------------------------------------------------------------------
# Guia TISS
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class GuiaTiss:
    paginas: tuple[int, ...]
    procedimento_codigo: str | None
    procedimento_descricao: str | None
    acomodacao_autorizada: str | None


# Sem guia real no pacote do diretor: calibrar pela primeira que chegar (ADR 0070, decisão 7).
_PROCEDIMENTO_SOLICITADO = re.compile(r"Procedimento solicitado:\s*(\d{8})\s+([^.\n]+?)\s*(?:\.|$)", re.M)
_ACOMODACAO_AUTORIZADA = re.compile(r"Acomoda[çc][ãa]o autorizada:\s*([^.\n]+?)\s*(?:\.|$)", re.M | re.I)


def _ler_guia_tiss(texto: str, paginas: tuple[int, ...]) -> GuiaTiss:
    procedimento = _PROCEDIMENTO_SOLICITADO.search(texto)
    acomodacao = _ACOMODACAO_AUTORIZADA.search(texto)
    return GuiaTiss(
        paginas=paginas,
        procedimento_codigo=procedimento.group(1) if procedimento else None,
        procedimento_descricao=procedimento.group(2) if procedimento else None,
        acomodacao_autorizada=acomodacao.group(1) if acomodacao else None,
    )


# ----------------------------------------------------------------------------------
# Leitura
# ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Conteudo:
    internacao: Internacao
    movimentacoes: tuple[Movimentacao, ...]
    setor_por_dia: dict[date, tuple[str, ...]]
    prescricoes: tuple[Prescricao, ...]
    prescricao_consolidada: tuple[ItemConsolidado, ...]
    exames_pedidos: tuple[ExamePedido, ...]
    balancos: tuple[Balanco, ...]
    glicemias: tuple[GlicemiasDoDia, ...]
    descricoes_cirurgicas: tuple[DescricaoCirurgica, ...]
    fichas_anestesicas: tuple[FichaAnestesica, ...]
    guias_tiss: tuple[GuiaTiss, ...]


def _paginas(textos: Sequence[str], documento: Documento) -> list[tuple[int, str]]:
    """(número da página no PDF, texto sem o rodapé global) de cada página do documento."""
    return [(n, _RODAPE_GLOBAL.sub("", textos[n - 1])) for n in documento.paginas]


def _por_coluna(paginas: list[tuple[int, str]], palavras: "Mapping[int, Sequence[Palavra]]") -> list[tuple[int, str]]:
    """A página da prescrição remontada pela posição das colunas (#1133); a que não tem
    as palavras ou o cabeçalho de colunas fica com o texto do `-layout`."""
    lidas = []
    for n, texto in paginas:
        remontado = texto_por_coluna(palavras[n]) if palavras.get(n) else None
        lidas.append((n, texto if remontado is None else _RODAPE_GLOBAL.sub("", remontado)))
    return lidas


def ler_conteudo(
    texto_por_pagina: Sequence[str | None],
    prontuario: Prontuario,
    palavras_por_pagina: "Mapping[int, Sequence[Palavra]] | None" = None,
) -> Conteudo:
    """`palavras_por_pagina`: as palavras com posição das páginas da prescrição, pelo
    número da página no PDF. Sem elas, a prescrição é lida por linha."""
    textos = [texto or "" for texto in texto_por_pagina]
    prescricoes: list[Prescricao] = []
    balancos: list[Balanco] = []
    afericoes: list[tuple[Documento, str]] = []
    descricoes: list[DescricaoCirurgica] = []
    fichas: list[FichaAnestesica] = []
    guias: list[GuiaTiss] = []
    # Texto inteiro de cada documento, por Família, na ordem da data.
    por_familia: dict[str, list[str]] = {}
    for d in prontuario.documentos:
        paginas = _paginas(textos, d)
        texto = "\n".join(texto for _, texto in paginas)
        por_familia.setdefault(d.familia, []).append(texto)
        if d.familia == "PRESCRICAO":
            itens = tuple(ler_itens(_por_coluna(paginas, palavras_por_pagina or {})))
            prescricoes.append(Prescricao(d.data, d.hora, d.subtipo, d.setor, d.paginas, itens))
        elif d.familia == "BALANCO":
            balancos.append(_ler_balanco(d, paginas[0][1]))
        elif d.familia == "AFERICAO":
            afericoes.append((d, texto))
        elif d.familia == "FICHA_ANESTESICA":
            fichas.append(ler_ficha_anestesica(texto, d.paginas, d.data))
        elif d.familia == "DOC_EDITOR" and MARCA_DA_DESCRICAO.search(texto):
            descricoes.append(ler_descricao_cirurgica(texto, d.paginas))
        elif d.familia == "GUIA_TISS":
            guias.append(_ler_guia_tiss(texto, d.paginas))
    internacao = _ler_internacao(por_familia)
    return Conteudo(
        internacao=internacao,
        movimentacoes=_movimentacoes(internacao, prontuario.documentos),
        setor_por_dia=_setor_por_dia(prontuario.documentos),
        prescricoes=tuple(prescricoes),
        prescricao_consolidada=tuple(consolidar(prescricoes)),
        exames_pedidos=tuple(exames_pedidos(prescricoes)),
        balancos=tuple(balancos),
        glicemias=_glicemias(afericoes, balancos),
        descricoes_cirurgicas=tuple(descricoes),
        fichas_anestesicas=tuple(fichas),
        guias_tiss=tuple(guias),
    )
