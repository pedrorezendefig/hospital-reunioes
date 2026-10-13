"""Tabela de preço em PDF ou planilha, lida por mapeamento (issue #1146, PRD #1129).

A tabela que o convênio manda no formato dele (PDF, XLSX ou CSV com cabeçalho
que não é de nenhum formato conhecido) entra em dois passos:

1. a proposta: o arquivo vira cabeçalho e linhas, a IA diz qual coluna é
   código, código alternativo, descrição, unidade e preço (ou preços), e a tela
   mostra 20 linhas convertidas e o total. Nada é gravado;
2. a confirmação: com o mapeamento que a pessoa conferiu (e talvez ajustou), o
   arquivo é lido de novo, guardado no bucket, e o importador das tabelas
   grava a versão com o mapeamento e a chave do arquivo.

O arquivo com o mesmo cabeçalho de um mapeamento já confirmado reaproveita o
mapeamento, sem IA. Depois de confirmada, a busca de preço acha os itens pelo
código, como na tabela que entrou por CSV.

O PDF é lido pelo extrator do módulo (`pdftotext -layout`, que preserva as
colunas): cada linha vira células pelas sequências de dois ou mais espaços. A
linha de cabeçalho é a primeira com três células ou mais; valem as linhas com o
mesmo número de células dela.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from dataclasses import dataclass
from typing import Any
from xml.etree import ElementTree

from pydantic import BaseModel, ConfigDict, ValidationError

from app.services import storage
from app.services.contas_medicas.ia import chamada_curta
from app.services.contas_medicas.tabelas import (
    FORMATOS,
    TabelaLida,
    TabelaRecusadaError,
    _Formato,
    _preco_da_celula,
    importar_tabela,
)
from app.services.contas_medicas_extrator import ErroLeitura, extrair_paginas
from app.services.contas_medicas_retencao import BUCKET
from app.services.prompt_loader import load_prompt

__all__ = [
    "AMOSTRA",
    "ArquivoDeTabela",
    "Mapeamento",
    "gravar_tabela_mapeada",
    "ler_arquivo",
    "proposta_de_mapeamento",
]

AMOSTRA = 20

# As linhas que vão para a IA junto com o cabeçalho: bastam para ela ver o
# que cada coluna traz, sem pagar a tabela inteira.
LINHAS_PARA_A_IA = 30

# Teto do XLSX descompactado: o zip de poucos KB que abre em gigabytes não
# passa da leitura do índice.
TETO_DESCOMPACTADO = 200 * 1024 * 1024

# As extensões aceitas, com o tipo do arquivo guardado no bucket.
_TIPOS = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}

_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_CELULAS_DO_PDF = re.compile(r"\s{2,}")
_CHAVE_DE_PRECO = re.compile(r"[a-z0-9_]+")


class ColunaDePreco(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chave: str
    coluna: str


class Mapeamento(BaseModel):
    """Qual coluna do arquivo é cada campo do item da tabela de preço."""

    model_config = ConfigDict(extra="forbid")

    codigo: str
    codigo_alternativo: str | None
    descricao: str | None
    unidade: str | None
    precos: list[ColunaDePreco]


@dataclass(frozen=True)
class ArquivoDeTabela:
    extensao: str
    cabecalho: list[str]
    linhas: list[list[str]]
    # O CSV com `;` cujo cabeçalho é de um formato conhecido vai pela carga direta.
    formato_conhecido: str | None = None


# ----------------------------------------------------------------------------------
# A leitura do arquivo: cabeçalho e linhas
# ----------------------------------------------------------------------------------


def _extensao(nome: str) -> str:
    extensao = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ""
    if extensao not in _TIPOS:
        raise TabelaRecusadaError("Envie a tabela em PDF, planilha XLSX ou CSV.")
    return extensao


def _sem_vazias(linhas: list[list[str]]) -> list[list[str]]:
    return [[c.strip() for c in linha] for linha in linhas if any(c.strip() for c in linha)]


def _do_csv(conteudo: bytes) -> tuple[list[list[str]], str]:
    try:
        texto = conteudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        # A planilha salva como CSV pelo Excel no Windows.
        texto = conteudo.decode("cp1252", errors="replace")
    primeira = texto.split("\n", 1)[0]
    separador = max((";", ",", "\t"), key=primeira.count)
    return _sem_vazias(list(csv.reader(io.StringIO(texto), delimiter=separador))), separador


def _texto_xml(no: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in no.iter(f"{{{_NS['x']}}}t"))


def _indice_da_coluna(referencia: str) -> int | None:
    letras = re.match(r"[A-Z]+", referencia or "")
    if not letras:
        return None
    indice = 0
    for letra in letras.group(0):
        indice = indice * 26 + ord(letra) - 64
    return indice - 1


def _do_xlsx(conteudo: bytes) -> list[list[str]]:
    """A primeira aba da planilha, com o texto compartilhado resolvido."""
    try:
        with zipfile.ZipFile(io.BytesIO(conteudo)) as zf:
            if sum(info.file_size for info in zf.infolist()) > TETO_DESCOMPACTADO:
                raise TabelaRecusadaError("A planilha é grande demais para uma tabela.")
            nomes = zf.namelist()
            abas = sorted(
                (n for n in nomes if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)),
                key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[-1]).group(0)),
            )
            if not abas:
                raise KeyError("sem aba")
            compartilhados = []
            if "xl/sharedStrings.xml" in nomes:
                raiz = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
                compartilhados = [_texto_xml(si) for si in raiz.findall("x:si", _NS)]
            aba = ElementTree.fromstring(zf.read(abas[0]))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise TabelaRecusadaError(
            "Não consegui ler a planilha. Confira se ela abre no Excel e envie de novo."
        ) from None
    linhas = []
    for linha in aba.iterfind(".//x:sheetData/x:row", _NS):
        celulas: dict[int, str] = {}
        for posicao, celula in enumerate(linha.findall("x:c", _NS)):
            indice = _indice_da_coluna(celula.get("r", ""))
            valor = celula.find("x:v", _NS)
            bruto = valor.text if valor is not None and valor.text else ""
            tipo = celula.get("t")
            if tipo == "s" and bruto.isdigit() and int(bruto) < len(compartilhados):
                texto = compartilhados[int(bruto)]
            elif tipo == "inlineStr":
                texto = _texto_xml(celula)
            else:
                texto = bruto
            celulas[posicao if indice is None else indice] = texto
        if celulas:
            linhas.append([celulas.get(i, "") for i in range(max(celulas) + 1)])
    return _sem_vazias(linhas)


def _do_pdf(conteudo: bytes) -> list[list[str]]:
    paginas = extrair_paginas(conteudo)
    if isinstance(paginas, ErroLeitura):
        raise TabelaRecusadaError(paginas.motivo)
    linhas = [
        _CELULAS_DO_PDF.split(linha.strip())
        for pagina in paginas
        for linha in pagina.texto.splitlines()
        if linha.strip()
    ]
    inicio = next((i for i, linha in enumerate(linhas) if len(linha) >= 3), None)
    if inicio is None:
        raise TabelaRecusadaError("O PDF não tem uma tabela com colunas que dê para ler. Envie a planilha, se tiver.")
    largura = len(linhas[inicio])
    return [linha for linha in linhas[inicio:] if len(linha) == largura]


def _formato_conhecido(cabecalho: list[str], separador: str) -> str | None:
    colunas = {c.lower() for c in cabecalho}
    if separador != ";":
        return None
    return next((f.descricao for f in FORMATOS if set(f.colunas) <= colunas), None)


def ler_arquivo(nome: str, conteudo: bytes) -> ArquivoDeTabela:
    """O arquivo em cabeçalho e linhas, ou `TabelaRecusadaError`. O PDF passa
    pelo extrator isolado: quem chama do event loop roda isto numa thread."""
    extensao = _extensao(nome)
    conhecido = None
    if extensao == ".csv":
        linhas, separador = _do_csv(conteudo)
        conhecido = _formato_conhecido(linhas[0], separador) if linhas else None
    elif extensao == ".xlsx":
        linhas = _do_xlsx(conteudo)
    else:
        linhas = _do_pdf(conteudo)
    if len(linhas) < 2:
        raise TabelaRecusadaError("O arquivo não tem linhas de tabela depois do cabeçalho.")
    cabecalho = [c or f"Coluna {i + 1}" for i, c in enumerate(linhas[0])]
    largura = len(cabecalho)
    corpo = [(linha + [""] * largura)[:largura] for linha in linhas[1:]]
    return ArquivoDeTabela(extensao=extensao, cabecalho=cabecalho, linhas=corpo, formato_conhecido=conhecido)


# ----------------------------------------------------------------------------------
# O mapeamento aplicado: os itens
# ----------------------------------------------------------------------------------


def _numero_com_ponto(texto: str) -> str:
    """`R$ 1.234,56`, `1234,56` e `1,234.56` viram `1234.56`; o resto fica como está."""
    valor = texto.replace("R$", "").replace("\xa0", "").replace(" ", "")
    if "," in valor and "." in valor:
        if valor.rfind(",") > valor.rfind("."):
            return valor.replace(".", "").replace(",", ".")
        return valor.replace(",", "")
    return valor.replace(",", ".")


def _conferir(arquivo: ArquivoDeTabela, mapeamento: Mapeamento) -> None:
    usadas = [mapeamento.codigo, mapeamento.codigo_alternativo, mapeamento.descricao, mapeamento.unidade]
    usadas += [p.coluna for p in mapeamento.precos]
    fora = [c for c in usadas if c is not None and c not in arquivo.cabecalho]
    if fora:
        raise TabelaRecusadaError(f"A coluna {fora[0]!r} não está no cabeçalho do arquivo.")
    if not mapeamento.precos:
        raise TabelaRecusadaError("Escolha ao menos uma coluna de preço.")
    chaves = [p.chave for p in mapeamento.precos]
    if len(set(chaves)) != len(chaves) or not all(_CHAVE_DE_PRECO.fullmatch(c) for c in chaves):
        raise TabelaRecusadaError("O nome de cada preço é único, em minúsculas e sem espaço (valor, comum, carioca).")


def _itens(arquivo: ArquivoDeTabela, mapeamento: Mapeamento) -> list[dict[str, Any]]:
    _conferir(arquivo, mapeamento)
    posicao = {coluna: i for i, coluna in enumerate(arquivo.cabecalho)}
    proprias = {mapeamento.codigo, mapeamento.codigo_alternativo, mapeamento.descricao, mapeamento.unidade}
    proprias |= {p.coluna for p in mapeamento.precos}

    def celula(linha: list[str], coluna: str | None) -> str | None:
        return (linha[posicao[coluna]] or None) if coluna else None

    itens = []
    for numero, linha in enumerate(arquivo.linhas, start=2):
        codigo = celula(linha, mapeamento.codigo)
        # Sem código não é item (a continuação da descrição no PDF), e o
        # cabeçalho repetido em cada página do PDF também não.
        if not codigo or linha == arquivo.cabecalho:
            continue
        itens.append(
            {
                "codigo": codigo,
                "codigo_alternativo": celula(linha, mapeamento.codigo_alternativo),
                "descricao": celula(linha, mapeamento.descricao),
                "grupo": None,
                "unidade": celula(linha, mapeamento.unidade),
                "precos_json": {
                    p.chave: _preco_da_celula(_numero_com_ponto(linha[posicao[p.coluna]]), numero, p.coluna)
                    for p in mapeamento.precos
                },
                "extra_json": {c: linha[i] for c, i in posicao.items() if c not in proprias and linha[i]},
            }
        )
    if not itens:
        raise TabelaRecusadaError(f"Nenhuma linha tem código na coluna {mapeamento.codigo!r}.")
    return itens


def _amostra(itens: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "codigo": item["codigo"],
            "codigo_alternativo": item["codigo_alternativo"],
            "descricao": item["descricao"],
            "unidade": item["unidade"],
            "precos": item["precos_json"],
        }
        for item in itens[:AMOSTRA]
    ]


# ----------------------------------------------------------------------------------
# A proposta
# ----------------------------------------------------------------------------------


def _assinatura(cabecalho: list[str]) -> str:
    """O cabeçalho como chave do mapeamento: sem caixa e sem espaço nas pontas."""
    return "|".join(c.strip().lower() for c in cabecalho)


def _mapeamento_confirmado(supabase, cabecalho: list[str]) -> Mapeamento | None:
    """O mapeamento da última tabela confirmada com o mesmo cabeçalho, com os
    nomes das colunas do cabeçalho novo: a assinatura casa sem caixa, então
    `CÓD. TUSS` acha o mapeamento de `Cód. TUSS` e cada coluna é traduzida
    pela posição no cabeçalho gravado."""
    gravadas = (
        supabase.table("cm_tabela_preco")
        .select("mapeamento_json, criado_em")
        .contains("mapeamento_json", {"assinatura": _assinatura(cabecalho)})
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    for gravada in gravadas:
        mapeamento_json = gravada.get("mapeamento_json") or {}
        try:
            mapeamento = Mapeamento.model_validate(mapeamento_json.get("colunas"))
        except ValidationError:
            return None
        traducao = dict(zip(mapeamento_json.get("cabecalho") or [], cabecalho, strict=False))
        return _traduzido(mapeamento, traducao)
    return None


def _traduzido(mapeamento: Mapeamento, traducao: dict[str, str]) -> Mapeamento:
    def nome(coluna: str | None) -> str | None:
        return traducao.get(coluna, coluna) if coluna is not None else None

    return Mapeamento(
        codigo=nome(mapeamento.codigo),
        codigo_alternativo=nome(mapeamento.codigo_alternativo),
        descricao=nome(mapeamento.descricao),
        unidade=nome(mapeamento.unidade),
        precos=[ColunaDePreco(chave=p.chave, coluna=nome(p.coluna)) for p in mapeamento.precos],
    )


def _tabela_para_a_ia(arquivo: ArquivoDeTabela) -> str:
    linhas = [arquivo.cabecalho, *arquivo.linhas[:LINHAS_PARA_A_IA]]
    return "TABELA DO CONVÊNIO (a primeira linha é o cabeçalho)\n" + "\n".join(" | ".join(linha) for linha in linhas)


def proposta_de_mapeamento(supabase, arquivo: ArquivoDeTabela, da_pessoa: Mapeamento | None) -> dict[str, Any]:
    """O mapeamento, 20 itens convertidos e o total, sem gravar nada.

    O mapeamento é o da pessoa (o ajuste na tela), o de um arquivo já
    confirmado com o mesmo cabeçalho, ou o que a IA propõe. Mapeamento que não
    converte volta com o `erro`, para a pessoa ajustar.
    """
    if da_pessoa is not None:
        mapeamento, origem = da_pessoa, "PESSOA"
    else:
        mapeamento, origem = _mapeamento_confirmado(supabase, arquivo.cabecalho), "CONFIRMADO"
        if mapeamento is None:
            mapeamento = chamada_curta(
                load_prompt("contas_medicas_tabela"),
                _tabela_para_a_ia(arquivo),
                Mapeamento,
                passo="DICIONARIO",
                supabase=supabase,
                conta_id=None,
            )
            origem = "IA"
    resposta: dict[str, Any] = {
        "cabecalho": arquivo.cabecalho,
        "mapeamento": mapeamento.model_dump(),
        "origem": origem,
        "amostra": [],
        "total": 0,
        "erro": None,
    }
    try:
        itens = _itens(arquivo, mapeamento)
    except TabelaRecusadaError as exc:
        resposta["erro"] = str(exc)
        return resposta
    resposta["amostra"] = _amostra(itens)
    resposta["total"] = len(itens)
    return resposta


# ----------------------------------------------------------------------------------
# A confirmação
# ----------------------------------------------------------------------------------


class ArquivoNaoGuardadoError(RuntimeError):
    """O bucket recusou o arquivo: nada foi gravado."""


def tabela_lida(arquivo: ArquivoDeTabela, mapeamento: Mapeamento) -> TabelaLida:
    """A tabela como o importador recebe, ou `TabelaRecusadaError`."""
    formato = _Formato(
        nome="MAPEAMENTO",
        descricao="tabela lida por mapeamento",
        colunas=tuple(arquivo.cabecalho),
        codigo=mapeamento.codigo,
        codigo_alternativo=mapeamento.codigo_alternativo,
        precos={p.chave: p.coluna for p in mapeamento.precos},
        regra_preco="COLUNA",
        chave="codigo",
    )
    return TabelaLida(formato=formato, itens=tuple(_itens(arquivo, mapeamento)))


def gravar_tabela_mapeada(
    supabase,
    operadora_id: str,
    categoria: str,
    arquivo: ArquivoDeTabela,
    conteudo: bytes,
    mapeamento: Mapeamento,
    **versao: Any,
) -> dict[str, Any]:
    """Guarda o arquivo no bucket e grava a versão pelo importador das tabelas,
    com o mapeamento e a chave do arquivo. `versao` são a vigência, a versão, o
    nome do arquivo e o autor, como o importador recebe."""
    tabela = tabela_lida(arquivo, mapeamento)
    chave = f"tabelas/{uuid.uuid4()}{arquivo.extensao}"
    if not storage.upload_private(supabase, BUCKET, chave, conteudo, _TIPOS[arquivo.extensao]):
        raise ArquivoNaoGuardadoError
    return importar_tabela(
        supabase,
        operadora_id,
        categoria,
        tabela,
        mapeamento_json={
            "assinatura": _assinatura(arquivo.cabecalho),
            "cabecalho": arquivo.cabecalho,
            "colunas": mapeamento.model_dump(),
        },
        arquivo_original=chave,
        **versao,
    )
