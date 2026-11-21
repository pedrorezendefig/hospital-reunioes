"""Impedimento, suplente convocado e Citado (issue #1828; especificação, 3.3 e
6.9; ADR 0097, decisões 4 e 5).

Quem fica impedido num caso ganha a marca na atribuição dele ao caso, e o
portão (`acesso.pode_abrir`) passa a recusá-lo na hora. Se o impedido tinha
papel de membro votante no caso, um suplente vigente é convocado no lugar e
passa a ver só aquele caso, com o papel do substituído.

Toda declaração, decisão e convocação grava a sua linha na trilha antes de
mudar o banco: sem a linha, nada acontece.
"""

from __future__ import annotations

import logging

from app.services.conduta import membros, trilha
from app.services.conduta.acesso import hoje_em_sao_paulo
from app.services.conduta.portao import CasoAberto
from app.services.conduta.ritos import PAPEIS_VOTANTES, agora_utc
from app.services.conduta.triagem import AcaoRecusadaError

logger = logging.getLogger(__name__)

MOTIVOS = {
    "parte": "parte no caso",
    "chefia_direta": "chefia direta de envolvido",
    "parentesco": "parentesco",
    "relacao_pessoal": "relação pessoal",
    "interesse": "interesse no resultado",
}


def _impedir(supabase, caso_id: str, pessoa_id: str, motivo: str) -> None:
    """Marca a pessoa impedida no caso. A Participação no Comitê não tem linha
    de atribuição: o impedimento cria a dele."""
    campos = {"impedido_em": agora_utc().isoformat(), "impedimento_motivo": motivo}
    abertas = (
        supabase.table("conduta_atribuicoes")
        .update(campos)
        .eq("caso_id", caso_id)
        .eq("participante_id", pessoa_id)
        .is_("impedido_em", "null")
        .execute()
        .data
    )
    if not abertas:
        supabase.table("conduta_atribuicoes").insert(
            {"caso_id": caso_id, "participante_id": pessoa_id, "motivo": "membro_do_comite", **campos}
        ).execute()


def _suplente_livre(supabase, caso_id: str) -> str | None:
    """O primeiro suplente vigente, com o Termo assinado, que ainda não tem
    nada no caso (convocação, impedimento) e não é Citado nele."""
    comite_id = membros.id_do_comite(supabase)
    if not comite_id:
        return None
    hoje = hoje_em_sao_paulo()
    candidatos = sorted(
        (
            p
            for p in membros.participacoes(supabase, comite_id)
            if p["papel"] == "suplente" and p.get("termo_assinado_em") and membros.vigente_em(p, hoje)
        ),
        key=lambda p: (str(p["vigencia_inicio"]), p["participante_id"]),
    )
    no_caso = supabase.table("conduta_atribuicoes").select("participante_id").eq("caso_id", caso_id).execute().data
    citados = supabase.table("conduta_citados").select("participante_id").eq("caso_id", caso_id).execute().data
    ocupados = {linha["participante_id"] for linha in (no_caso or []) + (citados or [])}
    return next((p["participante_id"] for p in candidatos if p["participante_id"] not in ocupados), None)


def _avisar_o_suplente(supabase, suplente_id: str) -> None:
    """Sino, sem protocolo nem conteúdo. O aviso não desfaz a convocação."""
    try:
        supabase.table("notificacoes").insert(
            {
                "destinatario_id": suplente_id,
                "tipo": membros.TIPO_DO_AVISO,
                "titulo": "Convocação no Comitê de Conduta",
                "mensagem": "Você foi convocado como suplente para um caso. Veja em Casos, no Canal de Conduta.",
            }
        ).execute()
    except Exception as erro:  # noqa: BLE001
        logger.error("[conduta_impedimento] Aviso da convocação não gravado no sino: %s", erro)


def _convocar_no_lugar(supabase, caso_id: str, impedido_id: str, papel: str | None) -> None:
    """Quem ficou impedido votava no caso: um suplente entra no lugar, com o
    papel do substituído. Sem suplente livre, a trilha diz isso."""
    if papel not in PAPEIS_VOTANTES:
        return
    suplente = _suplente_livre(supabase, caso_id)
    if suplente is None:
        trilha.registrar(supabase, caso_id, None, "sem_suplente", "nenhum suplente livre para convocar")
        return
    trilha.registrar(supabase, caso_id, None, "convocacao", "convocou um suplente no lugar de quem ficou impedido")
    supabase.table("conduta_atribuicoes").insert(
        {
            "caso_id": caso_id,
            "participante_id": suplente,
            "motivo": "suplente_convocado",
            "substitui_id": impedido_id,
            "substitui_papel": papel,
        }
    ).execute()
    _avisar_o_suplente(supabase, suplente)


def declarar_impedimento(supabase, aberto: CasoAberto, *, motivo: str) -> dict:
    if motivo not in MOTIVOS:
        raise AcaoRecusadaError(422, "Escolha o motivo do impedimento.")
    caso_id = aberto.caso["id"]
    trilha.registrar(supabase, caso_id, aberto.autor_id, "impedimento", f"declarou impedimento: {MOTIVOS[motivo]}")
    _impedir(supabase, caso_id, aberto.autor_id, motivo)
    _convocar_no_lugar(supabase, caso_id, aberto.autor_id, aberto.pessoa.papel)
    return aberto.caso
