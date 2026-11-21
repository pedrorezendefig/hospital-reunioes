"""Os membros do Comitê de Conduta (issue #1822, PRD #1786, ADR 0097, decisão 3).

O Comitê é o segundo Colegiado, sobre as tabelas `colegiados` e
`participacoes`. Cada Participação tem uma cadeira, a vigência (mandato de
dois anos) e a marcação de diretor, que a Rota Especial usa depois. A
situação é calculada, nunca gravada.

Toda mudança na composição (inclusão, saída) e no perfil de cadastro (dado,
tirado) passa por `mudanca_no_comite`: grava o registro do módulo, com autor
e data, e avisa os membros vigentes no sino e por e-mail. O e-mail não leva
nome nem conteúdo de caso: diz que houve mudança e aponta para a tela.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from app.config import settings
from app.services.conduta.acesso import SLUG_DO_COMITE
from app.services.email_service import _enviar_email, jinja_env

logger = logging.getLogger(__name__)

# A ordem da lista, da cadeira mais alta para a mais baixa.
CADEIRAS = {
    "coordenacao": "Coordenação",
    "segundo_leitor": "Membro e segundo leitor",
    "membro": "Membro",
    "suplente": "Suplente",
}

PERFIL_DE_CADASTRO = "cadastro_de_membros"

COLUNAS = "id, participante_id, papel, e_diretor, vigencia_inicio, vigencia_fim, encerrada_em, termo_assinado_em"

TIPO_DO_AVISO = "CONDUTA"
TITULO_DO_AVISO = "Mudança no Comitê de Conduta"
FRASE_DO_EMAIL = "Houve uma mudança no Comitê de Conduta. Veja o que mudou na tela Membros do Canal de Conduta."


def _data(valor: Any) -> date:
    return valor if isinstance(valor, date) else date.fromisoformat(str(valor)[:10])


def data_br(valor: Any) -> str:
    return _data(valor).strftime("%d/%m/%Y")


def fim_do_mandato(inicio: date) -> date:
    """Dois anos, inclusive nas pontas: de 01/12/2026 a 30/11/2028."""
    try:
        return inicio.replace(year=inicio.year + 2) - timedelta(days=1)
    except ValueError:  # 29 de fevereiro
        return inicio.replace(year=inicio.year + 2, day=28)


def situacao(participacao: dict[str, Any], hoje: date) -> str:
    """`encerrada`, `a_comecar`, `vencida` ou `vigente`."""
    if participacao.get("encerrada_em"):
        return "encerrada"
    if hoje < _data(participacao["vigencia_inicio"]):
        return "a_comecar"
    if hoje > _data(participacao["vigencia_fim"]):
        return "vencida"
    return "vigente"


def vigente_em(participacao: dict[str, Any], dia: date) -> bool:
    """A vigência termina no dia do encerramento; a desfeita antes do início
    (`encerrada_em` antes de `vigencia_inicio`) não vale em dia nenhum."""
    encerrada = participacao.get("encerrada_em")
    if encerrada and dia > _data(encerrada):
        return False
    return _data(participacao["vigencia_inicio"]) <= dia <= _data(participacao["vigencia_fim"])


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------


def id_do_comite(supabase) -> str | None:
    linhas = supabase.table("colegiados").select("id").eq("slug", SLUG_DO_COMITE).limit(1).execute().data or []
    return linhas[0]["id"] if linhas else None


def participacoes(supabase, comite_id: str) -> list[dict]:
    """Todas as do Comitê, encerradas inclusive."""
    return supabase.table("participacoes").select(COLUNAS).eq("colegiado_id", comite_id).execute().data or []


def participacao(supabase, comite_id: str, participacao_id: str) -> dict | None:
    linhas = (
        supabase.table("participacoes")
        .select(COLUNAS)
        .eq("id", participacao_id)
        .eq("colegiado_id", comite_id)
        .limit(1)
        .execute()
        .data
    ) or []
    return linhas[0] if linhas else None


def nomes(supabase, ids: list[str]) -> dict[str, str]:
    if not ids:
        return {}
    linhas = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(set(ids))).execute().data
    return {linha["id"]: linha.get("nome_completo") or "" for linha in linhas or []}


def linhas_da_tela(supabase, lista: list[dict], hoje: date) -> list[dict]:
    """O que a tela mostra de cada membro. Sem e-mail nem telefone. O `termo`
    diz se o Termo de Confidencialidade e Posse foi assinado, espera a
    assinatura ou não saiu (issue #1823)."""
    from app.services.conduta.assinaturas import situacao_dos_termos

    nome_de = nomes(supabase, [p["participante_id"] for p in lista])
    termo_de = situacao_dos_termos(supabase, lista)
    ordem = {papel: i for i, papel in enumerate(CADEIRAS)}
    linhas = [
        {
            "id": p["id"],
            "participante_id": p["participante_id"],
            "nome": nome_de.get(p["participante_id"]),
            "papel": p["papel"],
            "cadeira": CADEIRAS.get(p["papel"], p["papel"]),
            "e_diretor": bool(p.get("e_diretor")),
            "vigencia_inicio": str(p["vigencia_inicio"])[:10],
            "vigencia_fim": str(p["vigencia_fim"])[:10],
            "encerrada_em": str(p["encerrada_em"])[:10] if p.get("encerrada_em") else None,
            "termo_assinado": bool(p.get("termo_assinado_em")),
            "termo": termo_de[p["id"]],
            "situacao": situacao(p, hoje),
        }
        for p in lista
    ]
    return sorted(
        linhas,
        key=lambda x: (x["situacao"] != "vigente", ordem.get(x["papel"], 99), (x["nome"] or "").lower()),
    )


def ids_dos_membros_vigentes(supabase, hoje: date) -> list[str]:
    """Quem está no Comitê hoje, qualquer cadeira, sem os encerrados."""
    comite_id = id_do_comite(supabase)
    if not comite_id:
        return []
    return sorted({p["participante_id"] for p in participacoes(supabase, comite_id) if situacao(p, hoje) == "vigente"})


def ve_os_membros(supabase, participante: dict | None, hoje: date) -> bool:
    """A tela Membros abre para quem tem o perfil de cadastro e para quem está
    no Comitê hoje. O super admin sem um dos dois não entra."""
    if not participante:
        return False
    if participante.get("perfil_conduta") == PERFIL_DE_CADASTRO:
        return True
    return participante["id"] in ids_dos_membros_vigentes(supabase, hoje)


def registro(supabase) -> list[dict]:
    linhas = (
        supabase.table("conduta_registro")
        .select("id, acao, participante_id, autor_id, detalhe, registrado_em")
        .order("registrado_em", desc=True)
        .execute()
        .data
    ) or []
    nome_de = nomes(supabase, [x["participante_id"] for x in linhas] + [x["autor_id"] for x in linhas])
    return [
        {
            "acao": x["acao"],
            "pessoa": nome_de.get(x["participante_id"]),
            "autor": nome_de.get(x["autor_id"]),
            "detalhe": x.get("detalhe") or "",
            "registrado_em": x.get("registrado_em"),
        }
        for x in linhas
    ]


# ---------------------------------------------------------------------------
# Toda mudança: registro e aviso
# ---------------------------------------------------------------------------


def mudanca_no_comite(
    supabase,
    *,
    acao: str,
    participante_id: str,
    autor_id: str,
    mensagem: str,
    hoje: date,
    participacao_id: str | None = None,
    detalhe: str = "",
) -> list[str]:
    """Grava a mudança no registro do módulo e avisa no sino cada membro
    vigente. Devolve quem foi avisado, para o e-mail sair depois da resposta
    (`enviar_emails`). O registro levanta se não gravar; o aviso não desfaz a
    mudança."""
    supabase.table("conduta_registro").insert(
        {
            "acao": acao,
            "participante_id": participante_id,
            "participacao_id": participacao_id,
            "autor_id": autor_id,
            "detalhe": detalhe,
        }
    ).execute()
    destinatarios = ids_dos_membros_vigentes(supabase, hoje)
    if destinatarios:
        try:
            supabase.table("notificacoes").insert(
                [
                    {"destinatario_id": pid, "tipo": TIPO_DO_AVISO, "titulo": TITULO_DO_AVISO, "mensagem": mensagem}
                    for pid in destinatarios
                ]
            ).execute()
        except Exception as erro:  # noqa: BLE001 (o aviso não desfaz a mudança)
            logger.error("[conduta_membros] Aviso do Comitê não gravado no sino: %s", erro)
    return destinatarios


def link_da_tela() -> str:
    return f"{settings.frontend_url}/comite-de-conduta/membros"


def enviar_emails(supabase, destinatarios: list[str]) -> None:
    """Um e-mail por membro avisado, no endereço profissional, sem nome nem
    conteúdo. Best-effort: falha aqui não desfaz nada."""
    if not destinatarios:
        return
    try:
        from app.services.email_constants import get_logo_data_uri

        linhas = (
            supabase.table("participantes").select("id, email").in_("id", sorted(destinatarios)).execute().data
        ) or []
        link = link_da_tela()
        html = jinja_env.get_template("email_conduta_aviso.html").render(
            frase=FRASE_DO_EMAIL, link=link, logo_base64=get_logo_data_uri()
        )
        texto = f"{FRASE_DO_EMAIL}\n\nPara ver: {link}\n"
    except Exception as erro:  # noqa: BLE001
        logger.warning("[conduta_membros] E-mail do aviso não montado: %s", erro)
        return
    for linha in linhas:
        if not linha.get("email"):
            continue
        try:
            _enviar_email(linha["email"], TITULO_DO_AVISO, html, texto, endereco_fora_do_log=True)
        except Exception as erro:  # noqa: BLE001
            logger.warning("[conduta_membros] E-mail do aviso para %s não saiu: %s", linha["id"], erro)
