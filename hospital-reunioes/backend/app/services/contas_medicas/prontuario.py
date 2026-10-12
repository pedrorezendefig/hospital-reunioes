"""Leitura do Prontuário por código: a estrutura (issue #1117, PRD #1113, ADR 0070).

Entra o texto de cada página do PDF "Impressão de Prontuário" do MV, na ordem do
arquivo, e o número do Atendimento da Conta. Sai a estrutura que o resto do
Motor usa. Função pura: não lê banco, não fala com rede, não escreve log. O texto
do prontuário nunca vai para log (ADR 0070, decisão 8), e por isso este módulo
não tem logger.

O passo a passo segue o pipeline do adendo v1.2 (item 5), com a v1.3 por cima:

1. integridade pelo rodapé global;
2. capa: grupos, tipo de impressão e identificação (esta só para desidentificar
   e calcular a idade; nunca sai daqui);
3. Família de cada página pela primeira assinatura que casar;
4. filtro das páginas de outro Atendimento (o pronto-socorro vem no mesmo arquivo);
5. documento pela paginação da Família;
6. campos: atendimento, data e hora, setor pela unidade, conselho de quem assinou;
7. ordenação pela data do próprio documento (a exportação não vem em ordem).

As assinaturas, os campos e o boilerplate vêm do código de referência do diretor
(`local/contas-medicas/pacote-v1.3/leitura/referencia_prontuario.py`, fora do
git), calibrados na saída do `pdftotext -layout` de prontuários reais. Mudam por
PR quando o MV mudar de versão (ADR 0070, decisão 7).
"""

import re
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time


class ErroLeitura(Exception):  # noqa: N818, nome da spec, o mesmo da leitura da Conta (#1116)
    """Leitura impossível. A mensagem é a frase que a faturista vê na Situação Erro
    e nunca carrega texto do prontuário."""


@dataclass(frozen=True)
class Documento:
    familia: str
    paginas: tuple[int, ...]
    atendimento: str | None
    data: date | None
    hora: time | None
    setor: str | None
    conselho: str | None
    subtipo: str | None

    @property
    def pagina_inicial(self) -> int:
        return self.paginas[0]

    @property
    def pagina_final(self) -> int:
        return self.paginas[-1]


@dataclass(frozen=True)
class Prontuario:
    atendimento: str
    total_paginas: int
    tipo_impressao: str | None
    grupos_da_capa: dict[str, int]
    documentos: tuple[Documento, ...]
    # Uma frase por motivo; vazio quer dizer que o Guia não é parcial.
    parecer_parcial: tuple[str, ...]


# ----------------------------------------------------------------------------------
# Integridade
# ----------------------------------------------------------------------------------

# Rodapé global de toda página. Em algumas Famílias a linha quebra em duas, por isso
# o espaço entre as palavras aceita quebra de linha (adendo v1.2, item 3).
_RODAPE_GLOBAL = re.compile(r"Impress[ãa]o\s+de\s+Prontu[áa]rio\s*-\s*P[áa]gina\s+(\d+)\s+de\s+(\d+)")


def _conferir_integridade(paginas: list[str]) -> None:
    """O T do rodapé "Página N de T" tem de ser o número de páginas do arquivo."""
    totais = {int(m.group(2)) for texto in paginas for m in _RODAPE_GLOBAL.finditer(texto)}
    if any(total != len(paginas) for total in totais):
        declarado = max(totais)
        raise ErroLeitura(
            f"Prontuário com arquivo incompleto: o rodapé indica {declarado} páginas e vieram {len(paginas)}."
        )


# ----------------------------------------------------------------------------------
# Capa
# ----------------------------------------------------------------------------------

_MARCA_DA_CAPA = "DECLARAÇÃO DE RECEBIMENTO DE PRONTUÁRIO"
_MAXIMO_DE_PAGINAS_DA_CAPA = 6
_GRUPO_DA_CAPA = re.compile(r"Grupo:\s*(.+?)\s+Quantidade:\s*(\d+)")
_TIPO_DE_IMPRESSAO = re.compile(r"Tipo da impress[ãa]o:\s*(\S+)")


@dataclass(frozen=True)
class _Capa:
    paginas: int
    grupos: dict[str, int]
    tipo_impressao: str | None


def _ler_capa(paginas: list[str]) -> _Capa:
    grupos: dict[str, int] = {}
    tipo_impressao = None
    quantas = 0
    for texto in paginas[:_MAXIMO_DE_PAGINAS_DA_CAPA]:
        if _MARCA_DA_CAPA not in texto:
            break
        quantas += 1
        for m in _GRUPO_DA_CAPA.finditer(texto):
            grupo = m.group(1).strip()
            grupos[grupo] = grupos.get(grupo, 0) + int(m.group(2))
        if m := _TIPO_DE_IMPRESSAO.search(texto):
            tipo_impressao = m.group(1)
    return _Capa(paginas=quantas, grupos=grupos, tipo_impressao=tipo_impressao)


# Grupos sem os quais a análise de cobrança fica parcial: a capa lista o grupo e o
# corpo pode não trazer (o perfil de impressão das faturistas ainda não imprime tudo).
# Grupo da capa → (como a faturista lê, como o corpo do documento escreve).
_GRUPOS_ESSENCIAIS = {
    "PRESCRICAO MEDICA": ("prescrição médica", r"PRESCRI[ÇC][ÃA]O\s+M[ÉE]DICA"),
    "PRESCRICAO URGENCIA": ("prescrição de urgência", r"PRESCRI[ÇC][ÃA]O\s+(DE\s+)?URG"),
    "PRESCRIÇÃO NUTRICIONAL": ("prescrição nutricional", r"PRESCRI[ÇC][ÃA]O\s+NUTRI"),
    "EVOLUÇÃO MEDICA": ("evolução médica", r"EVOLU[ÇC][ÃA]O\s+M[ÉE]DICA"),
    "EVOLUÇÃO DIA CTI": ("evolução dia do CTI", r"EVOLU[ÇC][ÃA]O\s+DIA"),
    "EVOLUÇÃO NOITE CTI": ("evolução noite do CTI", r"EVOLU[ÇC][ÃA]O\s+NOITE"),
    "EVOLUÇÃO ROTINA CTI": ("evolução rotina do CTI", r"EVOLU[ÇC][ÃA]O\s+ROTINA"),
    "EVOLUÇÃO ENFERMEIRO": ("evolução do enfermeiro", r"EVOLU[ÇC][ÃA]O\s+(DO\s+)?ENFERMEIRO"),
    "ANOTAÇÕES DE ENFERMAGEM": ("anotações de enfermagem", r"ANOTA[ÇC]([ÕO]ES|[ÃA]O)\s+DE\s+ENFERMAGEM"),
}


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _grupos_que_faltam(capa: _Capa, corpo: str) -> str | None:
    """Grupo essencial com quantidade na capa e nenhum documento no corpo. O corpo é
    o arquivo inteiro depois da capa, como na referência, calibrada em arquivo real."""
    faltam = []
    for grupo, (nome, rx) in _GRUPOS_ESSENCIAIS.items():
        quantidade = sum(q for g, q in capa.grupos.items() if _sem_acento(g).upper() == _sem_acento(grupo).upper())
        if quantidade and not re.search(rx, corpo, re.I):
            faltam.append(f"{nome} ({quantidade} na capa)")
    return f"O arquivo não trouxe: {', '.join(faltam)}." if faltam else None


# ----------------------------------------------------------------------------------
# Limpeza: cabeçalho, rodapé, assinatura e identificação (adendo v1.2, item 6.2)
# ----------------------------------------------------------------------------------

_BOILERPLATE = [
    re.compile(x, re.I)
    for x in (
        r"^\s*HOSPITAL S[ÃA]O MATHEUS.*$",
        r"^\s*MV ?PEP .*$",
        r"^\s*MVPEP - .*$",
        r"^\s*MV \| SoulMV.*$",
        r"^.*\| Vers[ãa]o SMA-PEP.*$",
        r"^\s*Prontu[áa]rio\s+- P[áa]gina \d+ de \d+\s*$",
        r"^.*Impress[ãa]o\s+de\s+Prontu[áa]rio\s*-\s*P[áa]gina.*$",
        r"^\s*Documento assinado digitalmente.*$",
        r"^\s*Estado: Assinatura digital v[áa]lida.*$",
        r"^\s*NOTA: TODAS AS INFORMA.*$",
        r"^.*SILVA CARDOSO, 689.*$",
        r"^.*R\. Silva Cardoso, 689.*$",
        r"^\s*C[óo]digo:\s*\w{4,6}\s*$",
        r"^\s*P[áa]gina:?\s*\d+\s*(de|/)\s*\d+\s*$",
        r"^\s*P[ÁA]GINA \d+ DE \d+\s*$",
        r"^\s*P[áa]g\.:\s*\d+\s*$",
        r"^\s*null\s*$",
        r"^\s*1ª VIA\s*$",
        r"^\s*2ª VIA\s*$",
        r"^\s*Identidade de G[êe]nero:.*$",
        r"^\s*Tipo Sangu[íi]neo:.*$",
        r"^\s*Estado Civil:.*$",
        r"^\s*Peso\.+:.*Rubrica.*$",
        r"^.*Emitido [Pp]or:.*$",
        r"^\s*Usu[áa]rio\.+:.*$",
        r"^.*Para validar digitalmente este documento.*$",
        r"^\s*ACESSOPRD.*$",
    )
]

# Linhas de identificação saem inteiras: o que interessa delas é lido antes, por campo.
_IDENTIFICACAO = [
    re.compile(x, re.I)
    for x in (
        r"^\s*PACIENTE:.*$",
        r"^\s*Paciente\.*:.*$",
        r"^\s*Nome( da)? M[ãa]e:.*$",
        r"^\s*NOME( DA M[ÃA]E)?:.*$",
        r"^\s*Nome Social:.*$",
        r"^\s*Data de Nascimento:.*$",
        r"^\s*Dt\.? Nasc.*$",
        r"^\s*NASC\.:.*$",
        r"^\s*RG:.*$",
        r"^\s*CONVENIO:.*$",
        r"^\s*Conv[êe]nio\.*:.*$",
        r"^\s*MEDICO:.*$",
        r"^\s*M[ée]dico(\(a\) Assistente)?\.*:.*$",
        r"^\s*ATENDIMENTO:.*$",
        r"^\s*Atendimento:.*$",
        r"^\s*IDADE:.*$",
        r"^\s*CNS PACIENTE:.*$",
        r"^\s*Respons[áa]vel:.*Profiss[ãa]o:.*$",
        r"^\s*Leito:\s*\S*\s+Data Nasc.*$",
        r"^\s*Prontu[áa]rio:.*$",
        r"^\s*Data de Interna[çc][ãa]o:.*Especialidade.*$",
        r"^\s*Especialidade M[ée]dica:.*$",
    )
]

# Assinatura digital: "<nome>, CPF <n>, CRM/RJ-<n>, às hh:mm BRT de dd/mm/aaaa".
_ASSINATURA = re.compile(
    r"(CPF [\d.\-]+|CNPJ [\d./\-]+),?\s*((?:CRM|COREN|CREFITO|CRFA|CRN|CRF|CRP)/?\w*-?\s*\d+)?,?\s*"
    r"[àa]s (\d{2}:\d{2}) BRT de (\d{2}/\d{2}/\d{4})"
)


def _limpar(texto: str) -> list[str]:
    """Tira cabeçalho, rodapé, bloco de assinatura e linhas de identificação. Devolve as linhas úteis."""
    uteis: list[str] = []
    apos_emitido = False
    for linha in texto.split("\n"):
        if not linha.strip():
            continue
        if apos_emitido:  # o nome de quem emitiu quebra em duas linhas
            apos_emitido = False
            if re.fullmatch(r"\s*[A-ZÁÉÍÓÚÂÊÔÃÕÇ' ]{3,40}\s*", linha):
                continue
        if "Emitido por:" in linha or "Emitido Por:" in linha:
            apos_emitido = True
        if any(rx.match(linha) for rx in _BOILERPLATE) or any(rx.match(linha) for rx in _IDENTIFICACAO):
            continue
        if _ASSINATURA.search(linha):
            continue
        uteis.append(re.sub(r"[ \t]{2,}", "  ", linha.strip()))
    return uteis


# ----------------------------------------------------------------------------------
# Famílias de documento (adendo v1.3, item 2). A primeira que casar define a página.
# ----------------------------------------------------------------------------------

_FAMILIAS: list[tuple[str, Callable[[str], bool]]] = [
    ("AFERICAO", lambda t: "Relatório de Aferição" in t),
    ("EVOLUCAO", lambda t: "Relatório de Evolução" in t),
    ("AVALIACAO", lambda t: "Relatório de Avaliação" in t),
    ("ANOTACAO_ENF", lambda t: "Relatório de Anotação de Enfermagem" in t),
    ("DIAG_ENF", lambda t: "Relatório de Diagnóstico de Enfermagem" in t),
    (
        "FICHA_ANESTESICA",
        lambda t: ("Técnica Anestésica" in t and "Cirurgias Propostas" in t) or "Gases - Tempo de Utilização" in t,
    ),
    # "SING IN" e "SING OUT" é como o MV escreve.
    (
        "CHECKLIST_CIRURGIA",
        lambda t: re.search(r"SI[NG]+ (IN|OUT)\s*-", t) is not None or "TIME OUT" in t.upper()[:800],
    ),
    ("BALANCO", lambda t: "Sistema de Gerenciamento da Unidade" in t),
    ("SAE", lambda t: "Relatório de Histórico de Enfermagem" in t),
    ("PRESCRICAO", lambda t: re.search(r"Prescri[çc][ãa]o\.+:\s*\d+", t) is not None),
    ("RESUMO_ALTA", lambda t: "Relatório de Resumo de Alta" in t),
    ("DIAGNOSTICO", lambda t: "Relatório de Diagnóstico" in t),
    ("ANEXO", lambda t: "Relatório de Anexo do Prontuário" in t),
    ("ADMISSAO_UNIDADE", lambda t: re.search(r"Admiss[ãa]o:\s*\d+\s+Usu[áa]rio:", t) is not None),
    ("GUIA_TISS", lambda t: "GUIA DE SOLICITAÇÃO" in t[:600]),
    (
        "FISIO_ADMISSAO",
        lambda t: (
            "ADMISSÃO DE FISIOTERAPIA" in t
            or (re.search(r"P[áa]g\.:\s*\d+", t) is not None and "SILVA CARDOSO, 689" in t)
        ),
    ),
    (
        "ESCALA",
        lambda t: re.search(r"^\s*Escala\s+de\s", t, re.M) is not None and "Especialidade Médica" in t,
    ),
    (
        "FISIO_RESP",
        lambda t: (
            "AVALIAÇÃO RESPIRATÓRIA - VENTILAÇÃO" in t
            or ("EVOLUÇÃO DE FISIOTERAPIA" in t and "Mecânica Ventilatória" in t)
        ),
    ),
    (
        "FISIO_MOTORA",
        lambda t: (
            "Diagnóst. Fisio. Motora" in t or "Conduta da fisioterapia motora" in t or "Discutido com a Diaria" in t
        ),
    ),
    ("DOC_EDITOR", lambda t: re.search(r"PACIENTE:.*\n\s*ATENDIMENTO:", t) is not None),
]

# Só rodapé, assinatura e o nome de quem assinou: o corpo da página é imagem.
_MINIMO_DE_CARACTERES_UTEIS = 120


def _familia(texto: str) -> str:
    if sum(len(linha) for linha in _limpar(texto)) < _MINIMO_DE_CARACTERES_UTEIS:
        return "DIGITALIZADO"
    for nome, casa in _FAMILIAS:
        if casa(texto):
            return nome
    return "NAO_RECONHECIDO"


# ----------------------------------------------------------------------------------
# Campos da página
# ----------------------------------------------------------------------------------

# Página x de y DO DOCUMENTO; o rodapé global sai antes de procurar.
_PAGINACAO = [
    re.compile(r"P[áa]gina:\s*(\d+)\s*/\s*(\d+)"),  # PRESCRICAO, DIAGNOSTICO, ADMISSAO_UNIDADE
    re.compile(r"P[ÁA]GINA\s+(\d+)\s+DE\s+(\d+)"),  # RESUMO_ALTA
    re.compile(r"P[áa]gina\s+(\d+)\s+de\s+(\d+)"),  # SAE, BALANCO, FISIO, ANEXO, DOC_EDITOR
    re.compile(r"P[áa]g\.:\s*(\d+)"),  # FISIO_ADMISSAO, sem total
]


def _paginacao(texto: str) -> int | None:
    sem_rodape = _RODAPE_GLOBAL.sub("", texto)
    for rx in _PAGINACAO:
        if m := rx.search(sem_rodape):
            return int(m.group(1))
    return None


# O "Atendimento" do cabeçalho; o espaço não atravessa linha, porque o formulário em
# branco imprime "ATENDIMENTO:" vazio e o número da linha de baixo não é dele.
_ATENDIMENTO = re.compile(r"\bATENDIMENTO\b:?[ \t]*(\d{3,})", re.I)

_DATA_DA_FAMILIA = {
    "SAE": [
        r"Data do Hist\.:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})",
        r"Data da Emiss[ãa]o:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})",
    ],
    "PRESCRICAO": [r"Prescri[çc][ãa]o\.+:\s*\d+\s+Data:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "BALANCO": [r"Data de Realiza[çc][ãa]o do Balan[çc]o:\s*(\d{2}/\d{2}/\d{4})()"],
    "RESUMO_ALTA": [r"DATA DA ALTA\s*-\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "DIAGNOSTICO": [r"DATA DIAGN[ÓO]STICO:\s*(\d{2}/\d{2}/\d{4})()"],
    "ADMISSAO_UNIDADE": [r"Em:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "FISIO_RESP": [r"Emitido em:\s*(\d{2}/\d{2}/\d{4})()"],
    "FISIO_ADMISSAO": [r"^\s*Data:\s*(\d{2}/\d{2}/\d{4})()"],
    "ANEXO": [r"Data de Refer[êe]ncia:\s*(\d{2}/\d{2}/\d{4})()"],
    "EVOLUCAO": [r"Data/Hora do Documento:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "ANOTACAO_ENF": [r"Data da Anota[çc][ãa]o:\s*(\d{2}/\d{2}/\d{4})\s+Hora da Anota[çc][ãa]o:\s*(\d{2}:\d{2})"],
    "AFERICAO": [r"Data do Documento:\s*(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "AVALIACAO": [r"\(FECHADO\)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "DIAG_ENF": [r"DIAGN[ÓO]STICO REALIZADO:\s*\d+\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})"],
    "FICHA_ANESTESICA": [r"Data da Cir[úu]rgic[oa]\s+Cirurgias Propostas\s*\n\s*(\d{2}/\d{2}/\d{4})()"],
}

# Setor na data do documento: sempre a UNIDADE. O leito do balanço é o box físico e
# muda sem transferência de setor; o cabeçalho "LEITO | UNID" do DOC_EDITOR mostra o
# leito na hora da IMPRESSÃO, não na data do documento (adendo v1.2, item 8).
_SETOR_DA_FAMILIA = {
    "PRESCRICAO": r"Unid\. Int\.+:\s*(.*?)\s*Leito\.+:",
    "BALANCO": r"^\s*Unidade:\s*(\S.*?)\s*$",
    "SAE": r"^\s*Setor:\s*(\S.*?)\s*$",
    "ADMISSAO_UNIDADE": r"Unid\. Interna[çc][ãa]o:\s*(\S.*?)\s*$",
}

_SUBTIPO_DA_FAMILIA = {
    "PRESCRICAO": r"(PRESCRI[ÇC][ÃA]O\s+(?:DE\s+)?[A-ZÇÃÉÊ]+)",
    "SAE": r"Relat[óo]rio de Hist[óo]rico de Enfermagem.*\n\s*(\S.*?)\s*$",
    "EVOLUCAO": r"^\s*(EVOLU[ÇC][ÃA]O [A-ZÇÃÉÊÍÓÚ \u2013\-]{3,40}?)\s*$",
}


@dataclass
class _Campos:
    atendimento: str | None = None
    data: date | None = None
    hora: time | None = None
    setor: str | None = None
    conselho: str | None = None
    subtipo: str | None = None


def _data(texto: str) -> date | None:
    try:
        return datetime.strptime(texto, "%d/%m/%Y").date()
    except ValueError:
        return None


def _hora(texto: str | None) -> time | None:
    try:
        return datetime.strptime(texto, "%H:%M").time() if texto else None
    except ValueError:
        return None


def _campos(texto: str, familia: str) -> _Campos:
    campos = _Campos()
    if m := _ATENDIMENTO.search(texto):
        campos.atendimento = m.group(1)
    for rx in _DATA_DA_FAMILIA.get(familia, []):
        if m := re.search(rx, texto, re.M):
            campos.data, campos.hora = _data(m.group(1)), _hora(m.group(2))
            break
    # Sem campo próprio, a data e a hora vêm da última assinatura digital.
    if assinaturas := _ASSINATURA.findall(texto):
        _, conselho, hora, dia = assinaturas[-1]
        if conselho:
            campos.conselho = re.match(r"[A-Z]+", conselho).group(0)
        if campos.data is None:
            campos.data, campos.hora = _data(dia), _hora(hora)
        elif campos.hora is None and campos.data == _data(dia):
            campos.hora = _hora(hora)
    if (rx := _SETOR_DA_FAMILIA.get(familia)) and (m := re.search(rx, texto, re.M)) and m.group(1).strip():
        campos.setor = m.group(1).strip()
    if (rx := _SUBTIPO_DA_FAMILIA.get(familia)) and (m := re.search(rx, texto, re.M)):
        campos.subtipo = re.sub(r"\s+", " ", m.group(1)).strip()
    return campos


# ----------------------------------------------------------------------------------
# Páginas e documentos
# ----------------------------------------------------------------------------------


@dataclass
class _Pagina:
    numero: int
    texto: str
    familia: str
    paginacao: int | None
    campos: _Campos


def _paginas_do_atendimento(paginas: list[_Pagina], atendimento: str) -> list[_Pagina]:
    """Página sem número de Atendimento pertence à vizinhança: herda o da anterior
    (ou, no começo do corpo, o da seguinte). Fica só o Atendimento da Conta."""
    conhecido = next((p.campos.atendimento for p in paginas if p.campos.atendimento), None)
    for pagina in paginas:
        if pagina.campos.atendimento:
            conhecido = pagina.campos.atendimento
        else:
            pagina.campos.atendimento = conhecido
    return [p for p in paginas if p.campos.atendimento == atendimento]


def _montar_documentos(paginas: list[_Pagina]) -> list[list[_Pagina]]:
    """Página com x = 1 abre documento; x > 1 da mesma Família, logo depois de x - 1,
    continua. Sem paginação: uma página, um documento."""
    documentos: list[list[_Pagina]] = []
    for pagina in paginas:
        atual = documentos[-1] if documentos else None
        continua = (
            atual is not None
            and pagina.familia != "DIGITALIZADO"
            and pagina.paginacao is not None
            and pagina.paginacao > 1
            and atual[-1].familia == pagina.familia
            and atual[-1].paginacao == pagina.paginacao - 1
        )
        if continua:
            atual.append(pagina)
        else:
            documentos.append([pagina])
    return documentos


def _juntar_campos(paginas: list[_Pagina]) -> _Campos:
    """Os campos do documento são os da primeira página, completados pelas seguintes;
    a assinatura que vale é a última."""
    campos = _Campos()
    for pagina in paginas:
        for nome, valor in vars(pagina.campos).items():
            if valor is not None and (getattr(campos, nome) is None or nome == "conselho"):
                setattr(campos, nome, valor)
    return campos


def _ordenar_por_data(documentos: list[tuple[list[_Pagina], _Campos]]) -> list[tuple[list[_Pagina], _Campos]]:
    """Documento sem data herda a do vizinho (o anterior; no começo, o seguinte), e a
    lista sai pela data do próprio documento, não pela ordem das páginas."""
    anterior = next(((c.data, c.hora) for _, c in documentos if c.data), (None, None))
    for _, campos in documentos:
        if campos.data is None:
            campos.data, campos.hora = anterior
        else:
            anterior = (campos.data, campos.hora)
    return sorted(documentos, key=lambda d: (d[1].data or date.min, d[1].hora or time.min))


def ler_prontuario(texto_por_pagina: Sequence[str | None], atendimento: str | int) -> Prontuario:
    textos = [texto or "" for texto in texto_por_pagina]
    _conferir_integridade(textos)
    capa = _ler_capa(textos)

    paginas = []
    for numero, texto in enumerate(textos[capa.paginas :], start=capa.paginas + 1):
        familia = _familia(texto)
        paginas.append(_Pagina(numero, texto, familia, _paginacao(texto), _campos(texto, familia)))

    do_atendimento = _paginas_do_atendimento(paginas, str(atendimento))
    agrupados = [(grupo, _juntar_campos(grupo)) for grupo in _montar_documentos(do_atendimento)]
    documentos = tuple(
        Documento(
            familia=grupo[0].familia,
            paginas=tuple(p.numero for p in grupo),
            atendimento=campos.atendimento,
            data=campos.data,
            hora=campos.hora,
            setor=campos.setor,
            conselho=campos.conselho,
            subtipo=campos.subtipo,
        )
        for grupo, campos in _ordenar_por_data(agrupados)
    )
    parecer_parcial = [_grupos_que_faltam(capa, "\n".join(textos[capa.paginas :]))]
    return Prontuario(
        atendimento=str(atendimento),
        total_paginas=len(textos),
        tipo_impressao=capa.tipo_impressao,
        grupos_da_capa=capa.grupos,
        documentos=documentos,
        parecer_parcial=tuple(motivo for motivo in parecer_parcial if motivo),
    )
