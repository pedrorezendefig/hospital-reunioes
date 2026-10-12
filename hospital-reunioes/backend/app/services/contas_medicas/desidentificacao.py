"""Desidentificação do texto do Prontuário (issue #1117, ADR 0070, decisão 8).

Roda antes de qualquer envio à IA e de qualquer gravação em banco. Os valores
vêm da capa, que imprime a identificação da paciente; o que é desenho (CPF, RG,
CNS, telefone, data de nascimento atrás de pista) vem da pseudonimização que a
Ouvidoria já usa. Da identificação só saem o rótulo ("Maria S.") e a idade.

Nome tem limite de palavra, sempre: sem ele, um nome comum some de dentro de
outra palavra ("MELO" de "MELOXICAM"), e o texto que a análise lê fica errado.
"""

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from app.services.ouvidoria_pseudonimizacao import (
    MARCADOR_CPF,
    MARCADOR_DATA_NASCIMENTO,
    MARCADOR_RG,
    pseudonimizar_numeros,
)

MARCADOR_PACIENTE = "PACIENTE"
MARCADOR_NUMERO = "[NUMERO]"

# Palavra do nome com menos letras que isso não sai sozinha: "DA", "DOS", "LUZ"
# casariam em todo canto. Sai dentro do nome completo e do nome truncado.
_MINIMO_DE_LETRAS = 4
_LETRA = "A-Za-zÀ-ÖØ-öø-ÿ"
_VARIANTES = {"a": "aàáâãä", "e": "eèéêë", "i": "iìíîï", "o": "oòóôõö", "u": "uùúûü", "c": "cç", "n": "nñ"}

# Carteira, CNS e qualquer número de 15 a 20 dígitos (adendo v1.2, item 6.2).
_NUMERO_LONGO = re.compile(r"(?<!\d)\d{15,20}(?!\d)")
# CPF em qualquer linha, inclusive o do médico no bloco de assinatura, com ou sem
# pontuação e sem conferir o dígito verificador.
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_RG_COM_ROTULO = re.compile(r"\bRG:?\s*[\dXx.\-]{5,}")


@dataclass(frozen=True)
class Identificacao:
    """O que a capa imprime da paciente. Vive só durante a leitura."""

    nome: str | None = None
    mae: str | None = None
    nascimento: str | None = None
    cpf: str | None = None
    rg: str | None = None
    carteira: str | None = None


_CAMPOS_DA_CAPA = {
    "nome": r"^\s*Nome:\s*(.+?)(?:\s{2,}|$)",
    "mae": r"Nome da M[ãa]e:\s*(.+?)(?:\s{2,}|$)",
    "nascimento": r"Data de Nascimento:\s*(\d{2}/\d{2}/\d{4})",
    "cpf": r"CPF:\s*([\d.\-]+)",
    "rg": r"\bRG:\s*([\dXx.\-]+)",
    "carteira": r"Carteira:\s*(\d+)",
}


def ler_identificacao(texto_da_capa: str) -> Identificacao:
    valores = {}
    for campo, rx in _CAMPOS_DA_CAPA.items():
        if m := re.search(rx, texto_da_capa, re.M):
            valores[campo] = m.group(1).strip()
    return Identificacao(**valores)


def rotulo(identificacao: Identificacao) -> str | None:
    """Primeiro nome e a inicial do último sobrenome: "ANTÔNIA MELO FARIAS" vira "Antônia F."."""
    if not identificacao.nome:
        return None
    palavras = identificacao.nome.split()
    if len(palavras) == 1:
        return palavras[0].capitalize()
    return f"{palavras[0].capitalize()} {palavras[-1][0].upper()}."


def idade_em_anos(identificacao: Identificacao, na_data: date | None) -> int | None:
    if not identificacao.nascimento or na_data is None:
        return None
    dia, mes, ano = (int(parte) for parte in identificacao.nascimento.split("/"))
    return na_data.year - ano - ((na_data.month, na_data.day) < (mes, dia))


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _padrao_do_nome(nome: str) -> str:
    """Casa o nome com ou sem acento, em qualquer caixa, com qualquer espaço entre as
    palavras (o layout alinha colunas) e com limite de palavra."""
    palavras = []
    for palavra in nome.split():
        letras = (f"[{_VARIANTES[c]}]" if c in _VARIANTES else re.escape(c) for c in _sem_acento(palavra).lower())
        palavras.append("".join(letras))
    espaco = r"\s+"
    return rf"(?<![{_LETRA}]){espaco.join(palavras)}(?![{_LETRA}])"


def _nomes_a_apagar(identificacao: Identificacao) -> re.Pattern[str] | None:
    """Nome completo, nome truncado pelo layout (as primeiras k palavras) e, do nome da
    paciente, cada palavra com 4 letras ou mais. O mais longo vem antes."""
    alvos = set()
    for nome, palavra_a_palavra in ((identificacao.nome, True), (identificacao.mae, False)):
        if not nome:
            continue
        palavras = nome.split()
        alvos.update(" ".join(palavras[:k]) for k in range(2, len(palavras) + 1))
        if palavra_a_palavra:
            alvos.update(palavras)
    alvos = {a for a in alvos if len(a) >= _MINIMO_DE_LETRAS}
    if not alvos:
        return None
    em_ordem = sorted(alvos, key=len, reverse=True)
    return re.compile("|".join(_padrao_do_nome(a) for a in em_ordem), re.I)


def desidentificar(linhas: list[str], identificacao: Identificacao) -> list[str]:
    nomes = _nomes_a_apagar(identificacao)
    valores = [
        (identificacao.nascimento, MARCADOR_DATA_NASCIMENTO),
        (identificacao.cpf, MARCADOR_CPF),
        (identificacao.rg, MARCADOR_RG),
        (identificacao.carteira, MARCADOR_NUMERO),
    ]
    saida = []
    for linha in linhas:
        if nomes:
            linha = nomes.sub(MARCADOR_PACIENTE, linha)
        for valor, marcador in valores:
            if valor:
                linha = linha.replace(valor, marcador)
        linha = _NUMERO_LONGO.sub(MARCADOR_NUMERO, linha)
        linha = _CPF.sub(MARCADOR_CPF, linha)
        linha = _RG_COM_ROTULO.sub(MARCADOR_RG, linha)
        saida.append(pseudonimizar_numeros(linha))
    return saida
