"""
Registro de Aceites (ADR 0030): módulo profundo do nascimento incremental.

Persiste, por Reunião e Signatário, a origem do compromisso ('clicksign',
'aceite_interno', 'super_admin') e o timestamp na tabela `reuniao_aceites`,
e encapsula TODA a regra incremental de nascimento de Pendências:

- Signatário assina no ClickSign: nascem na hora as Pendências dele, plenas.
- O Facilitador da Reunião assina: nascem também as de responsáveis fora do
  Envelope (sem vínculo ou fora do roster de signatários).

Correlação signatário ↔ Participante por `signer.key`, com fallback por email
normalizado (mesmo padrão da tela de signatários). Webhook e endpoints são
cascas finas por cima deste serviço.
"""

import logging
from datetime import UTC, datetime

from app.services import pendencia_service
from app.services.pendencia_service import _e_conflito_unicidade

logger = logging.getLogger(__name__)


def _normalizar_email(email: str | None) -> str:
    return (email or "").strip().lower()


def _buscar_aceite(supabase, id_reuniao: str, signer_key: str | None, email_norm: str) -> dict | None:
    """Aceite já registrado para este signatário? Chave primária de correlação
    é o signer_key; fallback por email normalizado."""
    rows = (
        supabase.table("reuniao_aceites")
        .select("id, participante_id, signer_key, email")
        .eq("id_reuniao", id_reuniao)
        .execute()
        .data
        or []
    )
    if signer_key:
        achado = next((r for r in rows if r.get("signer_key") == signer_key), None)
        if achado:
            return achado
    if email_norm:
        return next((r for r in rows if (r.get("email") or "") == email_norm), None)
    return None


def _correlacionar_participante(supabase, id_reuniao: str, email_norm: str) -> str | None:
    """Resolve o Participante do roster da Reunião pelo email normalizado."""
    if not email_norm:
        return None
    vinculos = (
        supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    roster_ids = [v["participante_id"] for v in vinculos]
    if not roster_ids:
        return None
    pessoas = supabase.table("participantes").select("id, email").eq("ativo", True).execute().data or []
    for p in pessoas:
        if p["id"] in roster_ids and _normalizar_email(p.get("email")) == email_norm:
            return p["id"]
    return None


def _roster_ids(supabase, id_reuniao: str) -> set:
    vinculos = (
        supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute().data
        or []
    )
    return {v["participante_id"] for v in vinculos}


def registrar_assinatura_clicksign(
    supabase,
    id_reuniao: str,
    signer_key: str | None,
    signer_email: str | None,
    aceito_em: str | None = None,
) -> int:
    """Registra o aceite de um signatário ClickSign e cria as Pendências dele.

    Idempotente: evento repetido não duplica aceite nem Pendência (a criação
    delega em `liberar_pendencias`, idempotente por ação do quadro). Retorna o
    número de Pendências criadas nesta chamada.
    """
    email_norm = _normalizar_email(signer_email)

    aceite = _buscar_aceite(supabase, id_reuniao, signer_key, email_norm)
    if aceite is not None:
        participante_id = aceite.get("participante_id")
    else:
        participante_id = _correlacionar_participante(supabase, id_reuniao, email_norm)
        registro = {
            "id_reuniao": id_reuniao,
            "participante_id": participante_id,
            "signer_key": signer_key,
            "email": email_norm or None,
            "origem": "clicksign",
            "aceito_em": aceito_em or datetime.now(UTC).isoformat(),
        }
        try:
            supabase.table("reuniao_aceites").insert(registro).execute()
        except Exception as e:
            if not _e_conflito_unicidade(e):
                raise
            # Webhook duplicado em paralelo já gravou o mesmo aceite: segue em
            # frente, a criação de Pendências abaixo é idempotente.
            logger.info(f"[AceiteService] Aceite de {signer_key or email_norm} em {id_reuniao} já registrado.")

    if not participante_id:
        logger.warning(
            f"[AceiteService] Signatário sem correlação com Participante em {id_reuniao} "
            f"(key={signer_key}, email={email_norm}). Aceite registrado; nenhuma Pendência criada."
        )
        return 0

    reuniao_q = supabase.table("reunioes").select("facilitador_id").eq("id_reuniao", id_reuniao).execute()
    facilitador_id = (reuniao_q.data or [{}])[0].get("facilitador_id")
    eh_facilitador = bool(facilitador_id) and participante_id == facilitador_id
    roster = _roster_ids(supabase, id_reuniao) if eh_facilitador else set()

    def _filtro(acao: dict) -> bool:
        responsavel_id = acao.get("responsavel_id")
        if responsavel_id == participante_id:
            return True
        # A assinatura do Facilitador libera quem está fora do Envelope:
        # responsável sem vínculo ou que não é Signatário (fora do roster).
        return eh_facilitador and (responsavel_id is None or responsavel_id not in roster)

    criadas = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="CLICKSIGN_SIGN", filtro=_filtro)
    logger.info(
        f"[AceiteService] Aceite clicksign de {participante_id} em {id_reuniao}: "
        f"{criadas} Pendências criadas (facilitador={eh_facilitador})."
    )
    return criadas


def progresso_pendencias(supabase, id_reuniao: str) -> dict:
    """Progresso do nascimento incremental: Pendências criadas × total de ações
    do quadro. Alimenta a linha "Pendências criadas: X de Y" do card."""
    reuniao_q = supabase.table("reunioes").select("json_ata").eq("id_reuniao", id_reuniao).execute()
    json_ata = (reuniao_q.data or [{}])[0].get("json_ata") or {}
    quadro = json_ata.get("quadro_atribuicoes") or json_ata.get("atribuicoes") or json_ata.get("acoes") or []
    criadas = supabase.table("pendencias").select("id_acao").eq("id_reuniao", id_reuniao).execute().data or []
    return {"pendencias_criadas": len(criadas), "total_acoes": len(quadro)}
