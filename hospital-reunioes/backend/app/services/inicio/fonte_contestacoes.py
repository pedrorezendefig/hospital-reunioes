"""A Contestação na Minha Fila do Facilitador (issue #1870, PRD #1757).

O responsável contesta o item da Ata durante a assinatura; o Facilitador da
Reunião vê a Contestação na hora (decisão 22 do diretor), no alerta e na Minha
Fila, e ela sai de lá quando ele ajusta ou recusa. Nenhum job: a Contestação
aberta sai do histórico da Pendência na hora em que o Início é aberto
(`contestacoes_abertas`).

O item entra no grupo de até 48 horas no dia da Contestação: o prazo dele é o
dia seguinte, e ele passa do prazo se o Facilitador não responder até lá. A
Pendência contestada segue cobrada do responsável, com o prazo dela, pela
fonte de Pendências.

Só a Pendência aberta conta, e o sigilo do Núcleo é o da lista de Pendências
(issue #1772). Quem não tem perfil das Reuniões (ADR 0007) não recebe nada.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from app.dependencies import reunioes_ocultas, tem_acesso_reunioes
from app.services.inicio.regras import FUSO
from app.services.pendencias_consulta import ABERTOS, contestacoes_abertas

ROTULO = "as Contestações"

# O Facilitador responde até o fim do dia seguinte à Contestação.
DIAS_PARA_RESPONDER = 1


def itens(supabase, me: dict, _agora: datetime | None = None) -> list[dict]:
    """Os itens da fonte, no formato comum do Início."""
    if not tem_acesso_reunioes(me):
        return []
    abertas = contestacoes_abertas(supabase, None)
    if not abertas:
        return []
    pendencias = (
        supabase.table("pendencias")
        .select("id_acao, descricao_acao, id_reuniao, responsavel_nome, status")
        .in_("id_acao", sorted(abertas))
        .in_("status", ABERTOS)
        .is_("deleted_at", "null")
        .execute()
        .data
        or []
    )
    ids_reunioes = sorted({p["id_reuniao"] for p in pendencias if p.get("id_reuniao")})
    if not ids_reunioes:
        return []
    facilitadas = {
        r["id_reuniao"]: r
        for r in (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, data, facilitador_id")
            .in_("id_reuniao", ids_reunioes)
            .eq("facilitador_id", me["id"])
            .is_("deleted_at", "null")
            .execute()
            .data
            or []
        )
    }
    if not facilitadas:
        return []
    ocultas = set(reunioes_ocultas(supabase, me))

    saida: list[dict] = []
    for pendencia in pendencias:
        reuniao = facilitadas.get(pendencia.get("id_reuniao"))
        if not reuniao or reuniao["id_reuniao"] in ocultas:
            continue
        evento = abertas[pendencia["id_acao"]]
        contestou_em = datetime.fromisoformat(str(evento["criado_em"])).astimezone(FUSO).date()
        quem = (pendencia.get("responsavel_nome") or evento.get("autor_nome") or "O responsável").strip()
        titulo_da_reuniao = (reuniao.get("titulo") or "Reunião").strip()
        saida.append(
            {
                "tipo": "contestacao",
                "id": pendencia["id_acao"],
                "titulo": f"Contestação: {pendencia.get('descricao_acao') or 'item da Ata'}",
                "origem": f"{quem} contestou este item da Ata de {titulo_da_reuniao}.",
                "prazo": contestou_em + timedelta(days=DIAS_PARA_RESPONDER),
                "chegou_em": contestou_em,
                "area": "Reuniões",
                "acao": "Ajustar ou recusar",
                "destino": f"/pendencias/kanban?highlight={pendencia['id_acao']}",
                "contexto": f"Motivo: {evento.get('anotacao') or ''}".strip(),
            }
        )
    return saida
