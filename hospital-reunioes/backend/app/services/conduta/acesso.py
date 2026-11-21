"""Quem abre um caso do Canal de Conduta (ADR 0097, decisão 4; especificação,
regras C3 e C4 e seção 3.2).

Ninguém vê caso por ter um cargo: vê porque está designado naquele caso. A
Participação vigente no Comitê, como coordenação ou membro e com o Termo
assinado, é a designação para os casos da fila comum. As outras (suplente
convocado, apurador, CIPA, grupo da Rota Especial) são caso a caso, em
`conduta_atribuicoes`, e valem com o Termo assinado: o da atribuição ou o da
Participação vigente.

Por cima de tudo: o Citado e o impedido não abrem o caso, em nenhum perfil. O
super admin não entra na conta.

A regra é `pode_abrir`, pura. As leituras do banco ficam ao lado.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

# O slug do Comitê na tabela `colegiados` (a migration 175 o cria).
SLUG_DO_COMITE = "conduta"

# Quem lê a fila comum pela Participação, o segundo leitor inclusive
# (especificação, 3.2). O suplente só pela convocação.
PAPEIS_DA_FILA_COMUM = ("coordenacao", "segundo_leitor", "membro")

# O que a lista mostra: metadados em claro, nunca o conteúdo cifrado.
CAMPOS_DA_LISTA = (
    "id",
    "protocolo",
    "rota",
    "etapa",
    "categoria",
    "recebido_em",
    "prazo_em",
    "escopo",
    "rito",
    "destino",
    "triagem_em",
    "conferida_em",
    "prorrogado_em",
    "encerrado_em",
    "desfecho",
)


@dataclass(frozen=True)
class PessoaNoComite:
    id: str
    papel: str | None
    termo_valido: bool

    @property
    def na_fila_comum(self) -> bool:
        return self.papel in PAPEIS_DA_FILA_COMUM and self.termo_valido


def hoje_em_sao_paulo() -> date:
    return datetime.now(tz=ZoneInfo("America/Sao_Paulo")).date()


def _atribuicao_vale(atribuicao: dict[str, Any], pessoa: PessoaNoComite) -> bool:
    """Não revogada, e com o Termo assinado: o da atribuição ou o da
    Participação vigente."""
    return atribuicao.get("revogada_em") is None and bool(atribuicao.get("termo_assinado_em") or pessoa.termo_valido)


def papel_no_caso(papel: str | None, atribuicoes: list[dict]) -> str | None:
    """O papel da pessoa naquele caso. O suplente convocado faz o que o
    substituído fazia (issue #1828): o papel dele vem da convocação."""
    for atribuicao in atribuicoes:
        if (
            atribuicao.get("motivo") == "suplente_convocado"
            and atribuicao.get("substitui_papel")
            and not atribuicao.get("revogada_em")
            and not atribuicao.get("impedido_em")
        ):
            return atribuicao["substitui_papel"]
    return papel


def pode_abrir(caso: dict[str, Any], pessoa: PessoaNoComite, atribuicoes: list[dict], citado: bool) -> bool:
    """`atribuicoes` são as da pessoa neste caso."""
    if citado:
        return False
    if any(a.get("impedido_em") for a in atribuicoes):
        return False
    if any(_atribuicao_vale(a, pessoa) for a in atribuicoes):
        return True
    return caso.get("rota") == "comum" and pessoa.na_fila_comum


def pessoa_no_comite(supabase, participante_id: str, hoje: date | None = None) -> PessoaNoComite:
    hoje = hoje or hoje_em_sao_paulo()
    comite = supabase.table("colegiados").select("id").eq("slug", SLUG_DO_COMITE).limit(1).execute().data or []
    linhas = (
        (
            supabase.table("participacoes")
            .select("papel, termo_assinado_em, encerrada_em")
            .eq("colegiado_id", comite[0]["id"])
            .eq("participante_id", participante_id)
            .lte("vigencia_inicio", hoje.isoformat())
            .gte("vigencia_fim", hoje.isoformat())
            .execute()
            .data
        )
        if comite
        else []
    ) or []
    # A vigência termina no dia do encerramento: a desfeita antes do início
    # nunca vale, nem no primeiro dia.
    linhas = [x for x in linhas if not x.get("encerrada_em") or str(x["encerrada_em"])[:10] >= hoje.isoformat()]
    # Termo válido primeiro, depois o papel que lê a fila comum.
    melhor = min(
        linhas,
        key=lambda x: (not x.get("termo_assinado_em"), x.get("papel") not in PAPEIS_DA_FILA_COMUM),
        default=None,
    )
    return PessoaNoComite(
        id=participante_id,
        papel=melhor.get("papel") if melhor else None,
        termo_valido=bool(melhor and melhor.get("termo_assinado_em")),
    )


def _atribuicoes_e_citacoes(supabase, pessoa: PessoaNoComite) -> tuple[dict[str, list[dict]], set[str]]:
    atribuicoes: dict[str, list[dict]] = defaultdict(list)
    for linha in (
        supabase.table("conduta_atribuicoes").select("*").eq("participante_id", pessoa.id).execute().data or []
    ):
        atribuicoes[linha["caso_id"]].append(linha)
    citados = supabase.table("conduta_citados").select("caso_id").eq("participante_id", pessoa.id).execute().data
    return atribuicoes, {linha["caso_id"] for linha in citados or []}


def casos_da_pessoa(supabase, pessoa: PessoaNoComite) -> list[dict] | None:
    """Os casos que a pessoa abre, só com os metadados da lista. `None` quando
    ela não tem designação nenhuma no Canal: a rota responde 403."""
    atribuicoes, citados = _atribuicoes_e_citacoes(supabase, pessoa)
    if not pessoa.na_fila_comum and not any(_atribuicao_vale(a, pessoa) for x in atribuicoes.values() for a in x):
        return None
    candidatos: dict[str, dict] = {}
    if pessoa.na_fila_comum:
        for caso in (
            supabase.table("conduta_casos").select(", ".join(CAMPOS_DA_LISTA)).eq("rota", "comum").execute().data or []
        ):
            candidatos[caso["id"]] = caso
    if atribuicoes:
        for caso in (
            supabase.table("conduta_casos")
            .select(", ".join(CAMPOS_DA_LISTA))
            .in_("id", list(atribuicoes))
            .execute()
            .data
            or []
        ):
            candidatos[caso["id"]] = caso
    abertos = [
        {campo: caso.get(campo) for campo in CAMPOS_DA_LISTA}
        for caso in candidatos.values()
        if pode_abrir(caso, pessoa, atribuicoes.get(caso["id"], []), caso["id"] in citados)
    ]
    return sorted(abertos, key=lambda caso: str(caso.get("recebido_em") or ""), reverse=True)


def caso_se_a_pessoa_abre(supabase, pessoa: PessoaNoComite, caso_id: str) -> tuple[dict, list[dict]] | None:
    """O caso inteiro (com o conteúdo cifrado) e as atribuições da pessoa nele,
    se ela abre; senão None. Caso que não existe e caso fechado para ela dão o
    mesmo None."""
    linhas = supabase.table("conduta_casos").select("*").eq("id", caso_id).limit(1).execute().data or []
    if not linhas:
        return None
    atribuicoes, citados = _atribuicoes_e_citacoes(supabase, pessoa)
    caso = linhas[0]
    do_caso = atribuicoes.get(caso_id, [])
    return (caso, do_caso) if pode_abrir(caso, pessoa, do_caso, caso_id in citados) else None
