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

from app.services.conduta import trilha
from app.services.conduta.portao import CasoAberto
from app.services.conduta.ritos import agora_utc
from app.services.conduta.triagem import AcaoRecusadaError

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


def declarar_impedimento(supabase, aberto: CasoAberto, *, motivo: str) -> dict:
    if motivo not in MOTIVOS:
        raise AcaoRecusadaError(422, "Escolha o motivo do impedimento.")
    caso_id = aberto.caso["id"]
    trilha.registrar(supabase, caso_id, aberto.autor_id, "impedimento", f"declarou impedimento: {MOTIVOS[motivo]}")
    _impedir(supabase, caso_id, aberto.autor_id, motivo)
    return aberto.caso
