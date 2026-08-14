"""
Envio de emails relacionados a reunioes programadas:
  - convite na criacao da reuniao;
  - convite incremental para participantes adicionados depois;
  - lembrete 24 horas antes do horario marcado.

Todos os envios passam pelo email_service._enviar_email, que ja resolve
Resend (primario) -> SMTP (fallback) -> mock (dev). Falhas individuais
nao interrompem o lote, ficam logadas em logger.error.
"""

from __future__ import annotations

import logging
from datetime import date, time
from typing import Any

from jinja2 import Environment, FileSystemLoader

from app.config import settings
from app.services.email_service import TEMPLATES_DIR, _enviar_email

logger = logging.getLogger(__name__)

_env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)

_DIAS_SEMANA_PTBR = {
    0: "segunda-feira",
    1: "terça-feira",
    2: "quarta-feira",
    3: "quinta-feira",
    4: "sexta-feira",
    5: "sábado",
    6: "domingo",
}


def _formatar_data_ptbr(d: date) -> str:
    """Formata data como '15/05/2026 (quinta-feira)' em pt-BR."""
    dia_semana = _DIAS_SEMANA_PTBR[d.weekday()]
    return f"{d.strftime('%d/%m/%Y')} ({dia_semana})"


def _formatar_hora(h: time | str | None) -> str | None:
    """Aceita time, string HH:MM ou HH:MM:SS, retorna HH:MM. None se vazio."""
    if h is None or h == "":
        return None
    if isinstance(h, str):
        partes = h.split(":")
        if len(partes) >= 2:
            return f"{partes[0].zfill(2)}:{partes[1].zfill(2)}"
        return h
    return h.strftime("%H:%M")


def _parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _buscar_dados_reuniao(supabase, id_reuniao: str) -> dict | None:
    """Carrega titulo, data, hora, tipo, objetivo e id do facilitador."""
    res = (
        supabase.table("reunioes")
        .select("id_reuniao, titulo, data, hora_inicio, tipo, objetivo, facilitador_id")
        .eq("id_reuniao", id_reuniao)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _buscar_facilitador_nome(supabase, facilitador_id: str | None) -> str | None:
    if not facilitador_id:
        return None
    res = supabase.table("participantes").select("nome_completo").eq("id", facilitador_id).limit(1).execute()
    if not res.data:
        return None
    return res.data[0].get("nome_completo")


def _buscar_destinatarios(supabase, participante_ids: list[str], facilitador_id: str | None) -> list[dict]:
    """Retorna lista de {id, nome, email} dos destinatarios validos (exclui facilitador, inativos e sem email)."""
    ids_filtrados = [pid for pid in participante_ids if pid and pid != facilitador_id]
    if not ids_filtrados:
        return []
    res = supabase.table("participantes").select("id, nome_completo, email, ativo").in_("id", ids_filtrados).execute()
    out: list[dict] = []
    for row in res.data or []:
        if not row.get("ativo"):
            continue
        email = (row.get("email") or "").strip()
        if not email:
            continue
        out.append(
            {
                "id": row["id"],
                "nome": row.get("nome_completo") or "Participante",
                "email": email,
            }
        )
    return out


def _montar_contexto(reuniao: dict, destinatario_nome: str, facilitador_nome: str | None) -> dict[str, Any]:
    data_obj = _parse_date(reuniao.get("data"))
    return {
        "id_reuniao": reuniao["id_reuniao"],
        "titulo": reuniao.get("titulo") or "Reunião sem título",
        "data_formatada": _formatar_data_ptbr(data_obj) if data_obj else "A definir",
        "hora_formatada": _formatar_hora(reuniao.get("hora_inicio")),
        "tipo": reuniao.get("tipo"),
        "facilitador_nome": facilitador_nome,
        "objetivo": reuniao.get("objetivo"),
        "destinatario_nome": destinatario_nome,
        "frontend_url": settings.frontend_url,
        # URL absoluta servida pelo frontend (Next.js public/). Em prod o Gmail consegue
        # baixar via proxy; data URI base64 embutido seria filtrado por ser muito grande.
        "logo_base64": f"{settings.frontend_url}/logo-hsm.png",
    }


def _renderizar(template_name: str, contexto: dict[str, Any]) -> str:
    return _env.get_template(template_name).render(**contexto)


def _texto_fallback(reuniao: dict, destinatario_nome: str, facilitador_nome: str | None, prefixo: str) -> str:
    data_obj = _parse_date(reuniao.get("data"))
    data_str = _formatar_data_ptbr(data_obj) if data_obj else "data a definir"
    hora_str = _formatar_hora(reuniao.get("hora_inicio")) or "horário a definir"
    objetivo = reuniao.get("objetivo")
    link = f"{settings.frontend_url}/reunioes/{reuniao['id_reuniao']}"
    linhas = [
        f"Olá, {destinatario_nome}!",
        "",
        prefixo,
        "",
        f"Reunião: {reuniao.get('titulo') or 'Sem título'}",
        f"Data: {data_str}",
        f"Horário: {hora_str}",
    ]
    if reuniao.get("tipo"):
        linhas.append(f"Tipo: {reuniao['tipo']}")
    if facilitador_nome:
        linhas.append(f"Facilitador: {facilitador_nome}")
    if objetivo:
        linhas.append("")
        linhas.append(f"Objetivo: {objetivo}")
    linhas.append("")
    linhas.append(f"Ver na plataforma: {link}")
    linhas.append("")
    linhas.append("Hospital São Matheus")
    return "\n".join(linhas)


def enviar_convites(supabase, id_reuniao: str, participante_ids: list[str]) -> None:
    """Envia email convite para os participantes informados. Best-effort: erros vao para log."""
    if not participante_ids:
        return

    reuniao = _buscar_dados_reuniao(supabase, id_reuniao)
    if not reuniao:
        logger.warning(f"[convite] Reunião {id_reuniao} não encontrada, abortando envio de convites.")
        return

    facilitador_id = reuniao.get("facilitador_id")
    facilitador_nome = _buscar_facilitador_nome(supabase, facilitador_id)
    destinatarios = _buscar_destinatarios(supabase, participante_ids, facilitador_id)

    if not destinatarios:
        logger.info(
            f"[convite] Nenhum destinatário válido para reunião {id_reuniao} "
            "(após filtrar facilitador/inativos/sem email)."
        )
        return

    assunto = f"Convite: {reuniao.get('titulo') or 'Reunião'}"
    enviados = 0
    for dest in destinatarios:
        try:
            contexto = _montar_contexto(reuniao, dest["nome"], facilitador_nome)
            html = _renderizar("email_convite_reuniao.html", contexto)
            texto = _texto_fallback(
                reuniao,
                dest["nome"],
                facilitador_nome,
                "Você foi convidado(a) para a reunião abaixo.",
            )
            ok = _enviar_email(dest["email"], assunto, html, texto)
            if ok:
                enviados += 1
        except Exception as exc:
            logger.error(
                f"[convite] Falha ao enviar para {dest['email']} (reunião {id_reuniao}): {exc}",
                exc_info=True,
            )

    logger.info(f"[convite] Reunião {id_reuniao}: {enviados}/{len(destinatarios)} convites enviados.")


def enviar_email_aceite_interno(
    supabase,
    reuniao: dict,
    destinatario_nome: str,
    destinatario_email: str,
    link: str,
) -> bool:
    """Email do Aceite interno (ADR 0030, issue #277): o Envelope ClickSign
    morreu e o signatario pendente com acoes recebe o link publico tokenizado
    para ver a ata completa e clicar "Li e aceito". Retorna True no sucesso."""
    facilitador_nome = _buscar_facilitador_nome(supabase, reuniao.get("facilitador_id"))
    contexto = _montar_contexto(reuniao, destinatario_nome or "Participante", facilitador_nome)
    contexto["aceite_link"] = link
    html = _renderizar("email_aceite_interno.html", contexto)

    data_str = contexto["data_formatada"]
    texto = "\n".join(
        [
            f"Ola, {destinatario_nome or 'Participante'}!",
            "",
            "A coleta de assinaturas digitais desta ata foi encerrada e o seu aceite ainda esta pendente.",
            "Abra o link abaixo para ler a ata completa e registrar o seu aceite:",
            "",
            link,
            "",
            f"Reuniao: {reuniao.get('titulo') or 'Sem titulo'}",
            f"Data: {data_str}",
            "",
            "O link e pessoal e vale para um unico aceite.",
            "",
            "Hospital Sao Matheus",
        ]
    )
    assunto = f"Aceite pendente: {reuniao.get('titulo') or 'Ata de reuniao'}"
    return _enviar_email(destinatario_email, assunto, html, texto)


def enviar_lembrete_24h(supabase, id_reuniao: str) -> bool:
    """Envia lembrete 24h aos participantes. Retorna True quando a flag pode ser marcada.

    True quando: ao menos 1 envio teve sucesso, OU a lista de destinatarios elegiveis e vazia
                  (nao adianta tentar de novo no proximo tick, evita loop).
    False quando: ha destinatarios elegiveis mas todos os envios falharam (provider quebrado),
                   o tick seguinte tenta de novo.
    """
    reuniao = _buscar_dados_reuniao(supabase, id_reuniao)
    if not reuniao:
        logger.warning(f"[lembrete] Reunião {id_reuniao} não encontrada, abortando.")
        return True

    facilitador_id = reuniao.get("facilitador_id")
    facilitador_nome = _buscar_facilitador_nome(supabase, facilitador_id)

    rel = supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute()
    todos_ids = [row["participante_id"] for row in (rel.data or [])]
    destinatarios = _buscar_destinatarios(supabase, todos_ids, facilitador_id)

    if not destinatarios:
        logger.info(f"[lembrete] Nenhum destinatário válido para reunião {id_reuniao}; marcando flag mesmo assim.")
        return True

    titulo = reuniao.get("titulo") or "Reunião"
    hora_str = _formatar_hora(reuniao.get("hora_inicio"))
    if hora_str:
        assunto = f"Lembrete: {titulo} amanhã às {hora_str}"
    else:
        assunto = f"Lembrete: {titulo} é amanhã"

    enviados = 0
    falhas = 0
    for dest in destinatarios:
        try:
            contexto = _montar_contexto(reuniao, dest["nome"], facilitador_nome)
            html = _renderizar("email_lembrete_reuniao.html", contexto)
            texto = _texto_fallback(
                reuniao,
                dest["nome"],
                facilitador_nome,
                "Sua reunião acontece em aproximadamente 24 horas. Detalhes abaixo.",
            )
            ok = _enviar_email(dest["email"], assunto, html, texto)
            if ok:
                enviados += 1
            else:
                falhas += 1
        except Exception as exc:
            falhas += 1
            logger.error(
                f"[lembrete] Falha ao enviar para {dest['email']} (reunião {id_reuniao}): {exc}",
                exc_info=True,
            )

    logger.info(
        f"[lembrete] Reunião {id_reuniao}: {enviados}/{len(destinatarios)} lembretes enviados (falhas={falhas})."
    )
    return enviados > 0
