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

# Quem a cobrança de prazo rompido alcança (issue #327): titular e substituto,
# todos de uma vez. Diferente do acionamento, aqui não há escolha de um único
# destinatário; o gestor e a Diretoria entram nos degraus seguintes (#318).
CADEIA_DE_COBRANCA = (TITULAR, SUBSTITUTO)

# Os degraus restantes da escada (PRD #318, issue #336). A véspera fala só com
# o titular: avisar o substituto de um prazo que ainda não venceu gastaria a
# atenção de quem só entra na ausência dele. O degrau seguinte é do gestor da
# área; sem gestor cadastrado, quem chama sobe direto à Diretoria.
CADEIA_DA_VESPERA = (TITULAR,)
CADEIA_DO_GESTOR = (GESTOR,)


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


def destinatarios_da_cobranca(responsaveis: list[dict], dia: date) -> list[Destinatario]:
    """Para quem a cobrança de prazo rompido vai: titular e substituto vigentes.

    Lista vazia significa setor sem ninguém para cobrar; quem chama decide o
    que fazer com o silêncio (o degrau do gestor é do PRD #318). Um mesmo
    email recebe uma cobrança só, mesmo acumulando papéis."""
    return destinatarios_nos_papeis(responsaveis, dia, CADEIA_DE_COBRANCA)


def destinatarios_nos_papeis(responsaveis: list[dict], dia: date, papeis: tuple[str, ...]) -> list[Destinatario]:
    """Quem responde pelo setor hoje em algum dos `papeis`, na ordem pedida.

    É por aqui que cada degrau da escada de escalonamento (PRD #318) escolhe a
    quem cobrar: a véspera fala com o titular, o vencimento com titular e
    substituto, o degrau seguinte com o gestor. Lista vazia significa setor sem
    ninguém naquele papel; quem chama decide o que fazer com o silêncio. Um
    mesmo email aparece uma vez só, mesmo acumulando papéis."""
    vigentes = [r for r in responsaveis if esta_vigente(r, dia) and (r.get("email") or "").strip()]
    destinatarios: list[Destinatario] = []
    vistos: set[str] = set()
    for papel in papeis:
        for r in vigentes:
            email = r["email"].strip().lower()
            if r.get("papel") != papel or email in vistos:
                continue
            vistos.add(email)
            destinatarios.append(
                Destinatario(
                    nome=r.get("nome") or r["email"],
                    email=r["email"].strip(),
                    papel=papel,
                    alerta_diretoria=False,
                )
            )
    return destinatarios


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
