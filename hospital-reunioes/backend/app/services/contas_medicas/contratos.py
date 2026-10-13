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
from datetime import UTC, date, datetime, timedelta
from typing import Any

from postgrest.exceptions import APIError

from app.dependencies import foi_desligado, selecionar_participantes

__all__ = [
    "ANTECEDENCIA_PADRAO",
    "avisar_contratos",
    "contrato_da_memoria",
    "gravar_contrato_da_memoria",
    "listar_contratos",
    "situacao",
]

ANTECEDENCIA_PADRAO = 60

# O aviso guarda o contrato na referência do sino com este prefixo: é por ele
# que o clique no sino leva à tela Contratos, e não à fila de contas.
PREFIXO_DA_REFERENCIA = "contrato:"

# Até quantos dias antes do vencimento o contrato está em Negociar reajuste.
LIMITE_EM_DIA = 60

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


def situacao(vencimento: date | None, hoje: date) -> tuple[int | None, str]:
    """Os dias que faltam e a situação (spec do diretor, item 14): mais de 60
    dias Em dia; 60 ou menos Negociar reajuste; passou Vencido; sem data, Sem
    contrato. O limite é o da spec, não a antecedência do aviso."""
    if vencimento is None:
        return None, "SEM_CONTRATO"
    dias = (vencimento - hoje).days
    if dias < 0:
        return dias, "VENCIDO"
    return dias, "NEGOCIAR" if dias <= LIMITE_EM_DIA else "EM_DIA"


def antecedencia(contrato: dict[str, Any]) -> int:
    aviso = contrato.get("aviso_dias")
    return ANTECEDENCIA_PADRAO if aviso is None else int(aviso)


def listar_contratos(supabase, hoje: date) -> list[dict[str, Any]]:
    """Uma linha por operadora, com o contrato, os dias que faltam, a situação
    e a data do aviso. A operadora sem contrato aparece como Sem contrato."""
    operadoras = supabase.table("cm_operadora").select("id, sigla, nome").order("sigla").execute().data or []
    contratos = {c["operadora_id"]: c for c in supabase.table("cm_contrato").select("*").execute().data or []}
    linhas = []
    for operadora in operadoras:
        contrato = contratos.get(operadora["id"])
        vencimento = _data((contrato or {}).get("vencimento"))
        dias, estado = situacao(vencimento, hoje)
        aviso = vencimento - timedelta(days=antecedencia(contrato)) if contrato and vencimento else None
        linhas.append(
            {
                "sigla": operadora["sigla"],
                "nome": operadora["nome"],
                "contrato": contrato,
                "dias": dias,
                "situacao": estado,
                "data_aviso": _iso(aviso),
            }
        )
    return linhas


def _data_br(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def texto_do_aviso(sigla: str, vencimento: date, dias: int, negociacao: bool) -> str:
    """O texto da spec: "ASSIM: o contrato vence em 60 dias (01/05/2027).
    Iniciar a negociação do reajuste." Quando a memória diz que a data não é
    vencimento (Unimed, Leve), o texto diz que é o início do debate."""
    quando = "hoje" if dias == 0 else f"em {dias} {'dia' if dias == 1 else 'dias'}"
    if negociacao:
        return (
            f"{sigla}: {quando} ({_data_br(vencimento)}) inicia o debate do reajuste. "
            "A data não é o vencimento do contrato."
        )
    return f"{sigla}: o contrato vence {quando} ({_data_br(vencimento)}). Iniciar a negociação do reajuste."


def _quem_recebe(supabase) -> list[str]:
    """Quem tem "contratos e avisos" pela matriz e não foi desligado."""
    perfis = [
        linha["perfil"]
        for linha in supabase.table("cm_perfil_permissao")
        .select("perfil")
        .eq("permissao", "contratos_avisos")
        .eq("ligada", True)
        .execute()
        .data
        or []
    ]
    if not perfis:
        return []
    pessoas = selecionar_participantes(
        supabase, "id, ativo, perfil_contas_medicas", lambda q: q.in_("perfil_contas_medicas", perfis)
    )
    return [p["id"] for p in pessoas.data or [] if not foi_desligado(p)]


def _aviso_registrado(supabase, contrato_id: str, data_prevista: date) -> dict | None:
    linhas = (
        supabase.table("cm_aviso")
        .select("*")
        .eq("contrato_id", contrato_id)
        .eq("data_prevista", data_prevista.isoformat())
        .execute()
        .data
        or []
    )
    return linhas[0] if linhas else None


def avisar_contratos(supabase, hoje: date, agora: datetime | None = None) -> int:
    """A rotina diária: na data do aviso (vencimento menos a antecedência), um
    aviso CONTAS_MEDICAS no sino de cada pessoa com "contratos e avisos".

    Uma vez por contrato e data: `cm_aviso` guarda a data prevista e o envio.
    O dia perdido (container fora do ar na hora) sai no dia seguinte, até o
    vencimento; contrato vencido não recebe aviso atrasado. Devolve quantos
    contratos foram avisados."""
    agora = agora or datetime.now(UTC)
    destinatarios: list[str] | None = None
    operadoras = {o["id"]: o["sigla"] for o in supabase.table("cm_operadora").select("id, sigla").execute().data or []}
    avisados = 0
    for contrato in supabase.table("cm_contrato").select("*").execute().data or []:
        vencimento = _data(contrato.get("vencimento"))
        if vencimento is None:
            continue
        data_prevista = vencimento - timedelta(days=antecedencia(contrato))
        if not data_prevista <= hoje <= vencimento:
            continue
        aviso = _aviso_registrado(supabase, contrato["id"], data_prevista)
        if aviso and aviso.get("enviado_em"):
            continue
        if aviso is None:
            try:
                aviso = (
                    supabase.table("cm_aviso")
                    .insert({"contrato_id": contrato["id"], "data_prevista": data_prevista.isoformat()})
                    .execute()
                    .data[0]
                )
            except APIError as exc:
                if exc.code == "23505":  # outra passada chegou antes
                    continue
                raise
        if destinatarios is None:
            destinatarios = _quem_recebe(supabase)
        sigla = operadoras.get(contrato["operadora_id"], "Operadora")
        mensagem = texto_do_aviso(
            sigla, vencimento, (vencimento - hoje).days, bool(contrato.get("vencimento_e_negociacao"))
        )
        if destinatarios:
            supabase.table("notificacoes").insert(
                [
                    {
                        "destinatario_id": pessoa,
                        "tipo": "CONTAS_MEDICAS",
                        "titulo": f"Contrato {sigla}: reajuste",
                        "mensagem": mensagem,
                        "referencia_id": f"{PREFIXO_DA_REFERENCIA}{aviso['id']}",
                    }
                    for pessoa in destinatarios
                ]
            ).execute()
        supabase.table("cm_aviso").update({"enviado_em": agora.isoformat()}).eq("id", aviso["id"]).execute()
        avisados += 1
    return avisados
