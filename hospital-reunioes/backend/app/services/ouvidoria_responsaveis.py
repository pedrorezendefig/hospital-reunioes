"""Quem responde por cada setor da Ouvidoria (issue #325, ADR 0034 decisão 5).

Módulo fundo e **puro**: recebe as linhas do cadastro e o dia, e devolve para
quem a demanda vai. Não lê banco, não consulta o relógio e não conhece HTTP.

A cadeia desta fatia é curta de propósito. O titular vigente é o destinatário
normal; sem ele o setor não é acionável e a demanda sobe ao gestor da área, com
alerta à Diretoria (ADR 0034, decisão 5). O substituto entra na cobrança do
prazo rompido, que é do PRD de governança (#318), e por isso não recebe o
acionamento aqui: colocá-lo no meio da cadeia esconderia da Diretoria o setor
que está sem titular.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

TITULAR = "titular"
SUBSTITUTO = "substituto"
GESTOR = "gestor"
PAPEIS = (TITULAR, SUBSTITUTO, GESTOR)

# Ordem em que o acionamento procura destinatário.
CADEIA_DE_ACIONAMENTO = (TITULAR, GESTOR)


@dataclass(frozen=True)
class Destinatario:
    """Para quem o email de acionamento vai, e em que papel.

    `alerta_diretoria` é verdadeiro quando o setor foi acionado sem titular
    vigente: a Diretoria precisa saber que a demanda subiu."""

    nome: str
    email: str
    papel: str
    alerta_diretoria: bool


def esta_vigente(responsavel: dict, dia: date) -> bool:
    """A pessoa responde pelo setor neste dia.

    Vigência sem fim é o caso comum (o titular de hoje). O fim é inclusivo:
    quem sai no dia 31 ainda responde no dia 31."""
    inicio = responsavel.get("vigencia_inicio")
    fim = responsavel.get("vigencia_fim")
    if inicio and date.fromisoformat(str(inicio)) > dia:
        return False
    if fim and date.fromisoformat(str(fim)) < dia:
        return False
    return True


def escolher_destinatario(responsaveis: list[dict], dia: date) -> Destinatario | None:
    """Para quem o acionamento vai hoje, ou None se o setor não tem ninguém.

    None não é caso de rotina: significa setor sem titular e sem gestor, e a
    validação recusa em vez de mandar a demanda para o vazio."""
    vigentes = [r for r in responsaveis if esta_vigente(r, dia) and (r.get("email") or "").strip()]
    for papel in CADEIA_DE_ACIONAMENTO:
        for responsavel in vigentes:
            if responsavel.get("papel") == papel:
                return Destinatario(
                    nome=responsavel.get("nome") or responsavel["email"],
                    email=responsavel["email"].strip(),
                    papel=papel,
                    alerta_diretoria=papel != TITULAR,
                )
    return None
