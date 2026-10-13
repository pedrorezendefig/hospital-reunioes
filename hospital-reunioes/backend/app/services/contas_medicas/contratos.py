"""Contratos e aviso de reajuste (issue #1144, PRD #1129, ADR 0070).

Cada operadora tem um contrato em `cm_contrato`: assinatura, último aditivo
(número e data), início da vigência e vencimento. Ele nasce do bloco
`contrato` da memória da operadora e muda pela tela, quando a pessoa confirma
os campos lidos do contrato ou do aditivo enviado.

O vencimento ausente com vigência presente é a vigência mais um ano, marcado
"calculado" (spec do diretor, item 14). Quando o comentário da linha do
vencimento no cabeçalho da memória diz que a data não é vencimento (Unimed,
Leve: é o início do debate do reajuste), o contrato guarda
`vencimento_e_negociacao` e o aviso diz isso.

A rotina diária avisa no sino, uma vez, na data do aviso: vencimento menos a
antecedência da memória (60 dias quando a memória não diz).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any

__all__ = [
    "ANTECEDENCIA_PADRAO",
    "contrato_da_memoria",
    "gravar_contrato_da_memoria",
]

ANTECEDENCIA_PADRAO = 60

# Os quatro campos que a memória e o envio preenchem; aviso e negociação são só da memória.
CAMPOS_DO_CONTRATO = (
    "data_assinatura",
    "aditivo_numero",
    "aditivo_data",
    "vigencia_inicio",
    "vencimento",
    "vencimento_calculado",
)

_CABECALHO = re.compile(r"\A﻿?---[ \t]*\r?\n(.*?)\r?\n---", re.DOTALL)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").upper()


def _data(valor: Any) -> date | None:
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def mais_um_ano(dia: date) -> date:
    """O mesmo dia no ano seguinte; 29 de fevereiro vira 28."""
    try:
        return dia.replace(year=dia.year + 1)
    except ValueError:
        return dia.replace(year=dia.year + 1, day=28)


def _comentario_do_vencimento(texto_md: str) -> str:
    """O comentário da linha `vencimento:` dentro do bloco `contrato:` do
    cabeçalho, sem acento e em maiúscula. O YAML lido joga o comentário fora."""
    cabecalho = _CABECALHO.match(texto_md or "")
    if not cabecalho:
        return ""
    dentro = False
    for linha in cabecalho.group(1).splitlines():
        if re.match(r"^contrato\s*:", linha):
            dentro = True
            continue
        if dentro and linha.strip() and not linha[0].isspace():
            break
        achado = re.match(r"^\s+vencimento\s*:[^#]*#(.*)$", linha) if dentro else None
        if achado:
            return _sem_acento(achado.group(1))
    return ""


def contrato_da_memoria(parametros: dict[str, Any], texto_md: str) -> dict[str, Any] | None:
    """Os campos de `cm_contrato` lidos do bloco `contrato` da memória, ou
    `None` quando a memória não traz o bloco."""
    bloco = parametros.get("contrato")
    if not isinstance(bloco, dict):
        return None
    aditivo = bloco.get("ultimo_aditivo") if isinstance(bloco.get("ultimo_aditivo"), dict) else {}
    numero = aditivo.get("numero")
    vigencia = _data(aditivo.get("inicio_vigencia"))
    vencimento = _data(bloco.get("vencimento"))
    comentario = _comentario_do_vencimento(texto_md)
    calculado = "CALCULADO" in comentario
    if vencimento is None and vigencia is not None:
        vencimento, calculado = mais_um_ano(vigencia), True
    aviso = bloco.get("aviso_antecedencia_dias")
    return {
        "data_assinatura": _iso(_data(bloco.get("assinatura"))),
        "aditivo_numero": None if numero is None else str(numero),
        "aditivo_data": None,
        "vigencia_inicio": _iso(vigencia),
        "vencimento": _iso(vencimento),
        "vencimento_calculado": calculado and vencimento is not None,
        "vencimento_e_negociacao": "NAO E VENCIMENTO" in comentario,
        "aviso_dias": aviso if isinstance(aviso, int) and not isinstance(aviso, bool) and aviso >= 0 else None,
    }


def _iso(dia: date | None) -> str | None:
    return dia.isoformat() if dia else None


def _contrato_de(supabase, operadora_id: str) -> dict | None:
    linhas = supabase.table("cm_contrato").select("*").eq("operadora_id", operadora_id).execute().data or []
    return linhas[0] if linhas else None


def gravar_contrato_da_memoria(supabase, operadora_id: str, parametros: dict[str, Any], texto_md: str) -> None:
    """O contrato da operadora a partir da memória importada.

    Sem contrato, ele nasce. Com contrato que ninguém confirmou pela tela, a
    memória nova o substitui. Com contrato confirmado pela tela, os quatro
    campos ficam como a pessoa confirmou (vieram do documento) e só a
    antecedência e a marca de negociação, que só a memória diz, mudam.
    """
    campos = contrato_da_memoria(parametros, texto_md)
    if campos is None:
        return
    atual = _contrato_de(supabase, operadora_id)
    if atual is None:
        supabase.table("cm_contrato").insert({"operadora_id": operadora_id, **campos}).execute()
        return
    if atual.get("confirmado_em"):
        campos = {k: v for k, v in campos.items() if k not in CAMPOS_DO_CONTRATO}
    supabase.table("cm_contrato").update(campos).eq("id", atual["id"]).execute()
