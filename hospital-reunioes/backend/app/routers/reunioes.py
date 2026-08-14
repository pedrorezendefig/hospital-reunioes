import asyncio
import logging
import time
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel
from starlette.requests import Request

from app.config import settings
from app.dependencies import (
    get_allowed_reuniao_ids,
    get_current_user,
    get_participante_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
    require_acesso_reunioes,
    require_role,
    require_super_admin,
)
from app.limiter import limiter
from app.models.admin_schemas import (
    ForceEditReuniaoRequest,
    ForceStatusReuniaoRequest,
    ReasonRequest,
    TransferirFacilitadorRequest,
)
from app.models.schemas import (
    AdicionarParticipanteAtaRequest,
    AdicionarParticipantesRequest,
    AgendarReuniaoRequest,
    AtaGuiadaChatRequest,
    AtaGuiadaConcluirRequest,
    ChatCorrecaoRequest,
    EditarReuniaoRequest,
    ExcluirParticipanteAtaRequest,
    QuadroAtribuicaoUpdate,
    ResolverParticipantesRequest,
    ReuniaoResponse,
    TipoReuniao,
)
from app.services import audit, participantes_ata_service, reuniao_email_service
from app.utils.query_params import parse_csv_param

router = APIRouter(
    prefix="/reunioes",
    tags=["reunioes"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router.
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)


class CorrecaoInternaRequest(BaseModel):
    texto: str


def _generate_reuniao_id(data: date) -> str:
    import uuid

    ts = datetime.now().strftime("%H%M%S")
    uid = uuid.uuid4().hex[:2].upper()
    return f"RD_{data.strftime('%Y%m%d')}_{ts}{uid}"


# Campos da reunião que carregam conteúdo de ata (ou ponteiros pra ele) e
# NÃO devem ser servidos pra secretária — mesmo que ela tenha acesso a ver a
# linha da reunião. Os endpoints de criação/manipulação de ata já bloqueiam
# secretária com 403; estas chaves cuidam do canal de leitura via GET, que
# antes era barrado implicitamente pelo filtro de visibilidade.
_ATA_FIELDS_TO_REDACT = (
    "json_ata",
    "participantes_nao_reconhecidos",
    "url_pdf_preliminar",
    "url_pdf_assinado",
)


def _redact_ata_fields(row: dict) -> dict:
    for k in _ATA_FIELDS_TO_REDACT:
        if k in row:
            row[k] = None
    return row


@router.post("/agendar")
async def agendar_reuniao(
    req: AgendarReuniaoRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Cria uma reunião programada no calendário (sem transcrição).

    Aceita `facilitador_id` no payload (usado por secretárias pra alocar outro
    facilitador). Se vier ausente, faz fallback resolvendo pelo email do
    usuário logado (comportamento histórico). Popula `criada_por` com o id do
    participante que está marcando. Quando criada_por != facilitador_id,
    dispara email de notificação pro facilitador alocado.
    """
    id_reuniao = _generate_reuniao_id(req.data)

    # Resolve o participante autenticado (quem está criando).
    me = await get_participante_for_user(current_user, supabase)
    criador_id = me.get("id") if me else None

    # Resolve facilitador_id: usa o do payload se informado e válido, senão
    # cai no fallback histórico (email do usuário logado).
    facilitador_id: str | None = None
    if req.facilitador_id:
        try:
            fac_result = (
                supabase.table("participantes")
                .select("id, nome_completo, email, ativo")
                .eq("id", req.facilitador_id)
                .limit(1)
                .execute()
            )
            if not fac_result.data:
                raise HTTPException(status_code=404, detail="Facilitador informado não encontrado")
            facilitador_row = fac_result.data[0]
            if not facilitador_row.get("ativo"):
                raise HTTPException(status_code=400, detail="Facilitador informado está inativo")
            facilitador_id = facilitador_row["id"]
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Não foi possível validar facilitador_id {req.facilitador_id}: {e}")
            raise HTTPException(status_code=500, detail="Erro ao validar facilitador")
    else:
        try:
            fac_result = (
                supabase.table("participantes").select("id").eq("email", current_user["email"]).limit(1).execute()
            )
            if fac_result.data:
                facilitador_id = fac_result.data[0]["id"]
        except Exception as e:
            logger.warning(f"Não foi possível resolver facilitador_id para {current_user['email']}: {e}")

    reuniao_data = {
        "id_reuniao": id_reuniao,
        "titulo": req.titulo,
        "data": str(req.data),
        "hora_inicio": str(req.hora_inicio) if req.hora_inicio else None,
        "hora_fim": str(req.hora_fim) if req.hora_fim else None,
        "tipo": req.tipo.value if req.tipo else None,
        "objetivo": req.objetivo,
        "status_ata": "PROGRAMADA",
        "fonte": "MOCK",
        "facilitador_id": facilitador_id,
        "criada_por": criador_id,
        "id_grupo_recorrencia": req.id_grupo_recorrencia,
        "nome_grupo_recorrencia": req.nome_grupo_recorrencia,
    }
    try:
        supabase.table("reunioes").insert(reuniao_data).execute()
    except Exception:
        logger.exception(f"Erro ao inserir reunião {id_reuniao}")
        raise HTTPException(status_code=500, detail="Erro ao salvar reunião no banco de dados.")

    # Vincular participantes
    participante_ids = list(req.participante_ids)
    # Garantir que o facilitador também esteja na lista de participantes
    if facilitador_id and facilitador_id not in participante_ids:
        participante_ids.append(facilitador_id)

    if participante_ids:
        rows = [{"id_reuniao": id_reuniao, "participante_id": pid} for pid in participante_ids]
        try:
            supabase.table("reuniao_participantes").insert(rows).execute()
        except Exception:
            logger.exception(f"Erro ao vincular participantes da reunião {id_reuniao}")
            raise HTTPException(
                status_code=500,
                detail="Reunião criada mas erro ao vincular participantes.",
            )

    logger.info(
        f"Reunião {id_reuniao} PROGRAMADA para {req.data} por {current_user['email']} "
        f"(criador: {criador_id}, facilitador: {facilitador_id})"
    )

    # Dispara convites por email em background (best-effort, nao bloqueia a resposta).
    # Facilitador e excluido dentro do service, mas filtramos aqui tambem para evitar
    # uma chamada redundante quando ele e o unico participante.
    ids_para_notificar = [pid for pid in participante_ids if pid != facilitador_id]
    if ids_para_notificar:
        background_tasks.add_task(reuniao_email_service.enviar_convites, supabase, id_reuniao, ids_para_notificar)

    # Notifica o facilitador quando outra pessoa (ex: secretária) marca a reunião pra ele.
    if facilitador_id and criador_id and facilitador_id != criador_id:
        try:
            from app.services.email_service import send_meeting_scheduled_notification

            background_tasks.add_task(
                send_meeting_scheduled_notification,
                supabase,
                id_reuniao,
                facilitador_id,
                criador_id,
            )
        except Exception as e:
            logger.warning(f"Falha ao enfileirar email de notificação pra facilitador {facilitador_id}: {e}")

    return {
        "id_reuniao": id_reuniao,
        "titulo": req.titulo,
        "status": "PROGRAMADA",
        "facilitador_id": facilitador_id,
        "criada_por": criador_id,
        "message": "Reunião agendada com sucesso.",
    }


@router.get("/calendario")
async def list_reunioes_calendario(
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Lista reuniões para exibição no calendário, com participantes vinculados.

    Visibilidade controlada por get_allowed_reuniao_ids: super_admin e secretária
    veem tudo (None = sem filtro); regular vê só as reuniões em que aparece como
    participante. O select abaixo é uma whitelist explícita de colunas — não
    expõe json_ata/url_pdf_*. Nenhuma redação extra necessária pra secretária.
    """
    query = (
        supabase.table("reunioes")
        .select(
            "id_reuniao, data, hora_inicio, tipo, titulo, objetivo, status_ata, facilitador_id, criada_por, id_grupo_recorrencia, nome_grupo_recorrencia"  # noqa: E501
        )
        .neq("status_ata", "CANCELADA")
    )
    if data_inicio:
        query = query.gte("data", str(data_inicio))
    if data_fim:
        query = query.lte("data", str(data_fim))

    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None:
        if not allowed_ids:
            return []
        query = query.in_("id_reuniao", allowed_ids)

    result = query.order("data", desc=False).execute()
    reunioes = result.data

    # Enriquecer com participantes
    ids = [r["id_reuniao"] for r in reunioes]
    participantes_map = {r: [] for r in ids}
    if ids:
        part_result = (
            supabase.table("reuniao_participantes")
            .select("id_reuniao, participante_id, participantes(nome_completo, cargo)")
            .in_("id_reuniao", ids)
            .execute()
        )
        for row in part_result.data:
            rid = row["id_reuniao"]
            if rid in participantes_map:
                part = row.get("participantes")
                if isinstance(part, list) and part:
                    part = part[0]
                if part and isinstance(part, dict) and part.get("nome_completo"):
                    participantes_map[rid].append(
                        {
                            "id": row["participante_id"],
                            "nome": part["nome_completo"],
                            "cargo": part.get("cargo", ""),
                        }
                    )

    for r in reunioes:
        r["participantes"] = participantes_map.get(r["id_reuniao"], [])

    return reunioes


@router.get("", response_model=list[ReuniaoResponse])
async def list_reunioes(
    response: Response,
    status: str | None = Query(None, description="Status separados por vírgula"),
    tipo: str | None = Query(None, description="Tipos separados por vírgula"),
    facilitador_id: str | None = Query(None, description="Facilitadores separados por vírgula"),
    data_inicio: date | None = Query(None),
    data_fim: date | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    query = supabase.table("reunioes").select("*", count="exact").is_("deleted_at", "null")

    statuses = parse_csv_param(status)
    if statuses:
        query = query.in_("status_ata", statuses) if len(statuses) > 1 else query.eq("status_ata", statuses[0])

    tipos = parse_csv_param(tipo)
    if tipos:
        query = query.in_("tipo", tipos) if len(tipos) > 1 else query.eq("tipo", tipos[0])

    facilitadores = parse_csv_param(facilitador_id)
    if facilitadores:
        query = (
            query.in_("facilitador_id", facilitadores)
            if len(facilitadores) > 1
            else query.eq("facilitador_id", facilitadores[0])
        )

    if data_inicio:
        query = query.gte("data", str(data_inicio))
    if data_fim:
        query = query.lte("data", str(data_fim))

    # Visibilidade binária
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None:
        if not allowed_ids:
            response.headers["X-Total-Count"] = "0"
            return []
        query = query.in_("id_reuniao", allowed_ids)

    result = query.order("data", desc=True).range(offset, offset + limit - 1).execute()
    response.headers["X-Total-Count"] = str(result.count or 0)

    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        return [_redact_ata_fields(r) for r in (result.data or [])]
    return result.data


@router.get("/{id_reuniao}")
async def get_reuniao(
    id_reuniao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    result = supabase.table("reunioes").select("*").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]

    # Visibilidade binária — 404 para não-autorizados (previne enumeration)
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    # Enricher de participantes vinculados — usado pela tela de PROGRAMADA pra mostrar
    # quem foi convidado e pela tela de AGUARDANDO_VALIDACAO pra alimentar o dropdown
    # de responsável da coluna RESPONSÁVEL do quadro de atribuições.
    part_result = (
        supabase.table("reuniao_participantes")
        .select("participante_id, participantes(id, nome_completo, cargo, email, area)")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    participantes = []
    for row in part_result.data:
        part = row.get("participantes")
        if isinstance(part, list) and part:
            part = part[0]
        if part and isinstance(part, dict):
            participantes.append(
                {
                    "id": part.get("id"),
                    "nome": part.get("nome_completo"),
                    "cargo": part.get("cargo", ""),
                    "email": part.get("email", ""),
                    "area": part.get("area"),
                }
            )
    reuniao["participantes_programada"] = participantes

    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        reuniao = _redact_ata_fields(reuniao)

    return reuniao


# ─── Status ao vivo dos signatarios ClickSign ───────────────────────────────


def _fetch_signatarios_locais(supabase, id_reuniao: str) -> list[dict]:
    """Lista participantes vinculados à reuniao com status `pending`.

    Fallback usado quando ClickSign nao retorna detalhe (reunioes pre-PR2 sem
    envelope_id_clicksign) ou pra enriquecer nome quando a API devolve so email.
    """
    result = (
        supabase.table("reuniao_participantes")
        .select("participantes(id, nome_completo, email)")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    out: list[dict] = []
    for row in result.data or []:
        p = row.get("participantes")
        if isinstance(p, list) and p:
            p = p[0]
        if p and isinstance(p, dict):
            out.append(
                {
                    "signer_id": None,
                    "participante_id": p.get("id"),
                    "nome": p.get("nome_completo", "") or "",
                    "email": p.get("email", "") or "",
                    "status": "pending",
                    "signed_at": None,
                }
            )
    return out


def _signatarios_status_modo_interno(supabase, reuniao: dict, progresso: dict) -> dict:
    """Variante do card de Signatários no modo interno (ADR 0030, issue #276).

    Lista o roster local e cruza com o Registro de Aceites (correlação por
    participante_id, fallback por email normalizado, mesmo padrão do
    aceite_service): quem tem aceite firmou compromisso; os demais aparecem
    como pendentes, aguardando o Aceite interno.
    """
    id_reuniao = reuniao["id_reuniao"]
    locais = _fetch_signatarios_locais(supabase, id_reuniao)
    aceites = (
        supabase.table("reuniao_aceites")
        .select("participante_id, email, aceito_em")
        .eq("id_reuniao", id_reuniao)
        .execute()
        .data
        or []
    )
    por_participante = {a["participante_id"]: a for a in aceites if a.get("participante_id")}
    por_email = {(a.get("email") or "").strip().lower(): a for a in aceites if a.get("email")}

    signatarios_out: list[dict] = []
    for p in locais:
        aceite = por_participante.get(p.get("participante_id")) or por_email.get((p["email"] or "").strip().lower())
        signatarios_out.append(
            {
                "signer_id": None,
                "nome": p["nome"],
                "email": p["email"],
                "status": "signed" if aceite else "pending",
                "signed_at": aceite.get("aceito_em") if aceite else None,
            }
        )
    return {
        "total": len(signatarios_out),
        "assinaram": sum(1 for s in signatarios_out if s["status"] == "signed"),
        "envelope_id": reuniao.get("envelope_id_clicksign"),
        "signatarios": signatarios_out,
        "modo_interno": True,
        "modo_interno_desde": reuniao.get("modo_interno_desde"),
        **progresso,
    }


def _build_reminder_message(reuniao: dict) -> str:
    """Template PT-BR do lembrete de assinatura.

    ClickSign anexa este texto ao corpo padrão do email (que já inclui o link
    clicável de assinatura). Não tentamos compor o link — é responsabilidade do
    ClickSign na notification.
    """
    tipo = reuniao.get("tipo") or "Reunião"
    data_iso = reuniao.get("data") or ""
    try:
        d = date.fromisoformat(data_iso)
        data_fmt = d.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        data_fmt = data_iso
    return (
        f"Olá! Este é um lembrete amigável: a ata da reunião "
        f'"{tipo} — {data_fmt}" do Hospital São Matheus ainda aguarda a sua assinatura.\n\n'
        f"Por favor, clique no link desta mensagem para revisar e assinar o documento. "
        f"Se você já assinou, pode ignorar este email.\n\n"
        f"Equipe Hospital São Matheus"
    )


# Cooldown em memoria do self-heal: quando a recuperacao falha de forma
# persistente (ex.: Envelope nao localizavel na conta), evita re-varrer a conta
# ClickSign a cada atualizacao automatica do card (polling 30s). Estado efemero,
# sem coluna nova — reinicia junto com o processo.
_SELF_HEAL_COOLDOWN_S = 300.0
_self_heal_failures: dict[str, float] = {}


def _try_recover_envelope_id(supabase, reuniao: dict) -> str | None:
    """Self-heal: recupera o `envelope_id_clicksign` faltante de uma Ata pre-039.

    Localiza o Envelope na conta ClickSign pelo nome deterministico + o
    document_id (`envelope_key_clicksign`), grava no banco (idempotente) e
    devolve o id. Devolve None se nao recuperou — o caller mantem o modo
    degradado vigente. Em falha persistente, respeita um cooldown curto em
    memoria para nao re-varrer a conta a cada polling.
    """
    id_reuniao = reuniao.get("id_reuniao")
    document_id = reuniao.get("envelope_key_clicksign")
    if not id_reuniao or not document_id:
        return None

    last_fail = _self_heal_failures.get(id_reuniao)
    if last_fail is not None and (time.monotonic() - last_fail) < _SELF_HEAL_COOLDOWN_S:
        return None  # falhou ha pouco — nao re-varre a conta agora

    from app.services import clicksign_service

    envelope_id = clicksign_service.find_envelope_id(clicksign_service.envelope_name(id_reuniao), document_id)
    if not envelope_id:
        _self_heal_failures[id_reuniao] = time.monotonic()
        return None

    supabase.table("reunioes").update({"envelope_id_clicksign": envelope_id}).eq("id_reuniao", id_reuniao).execute()
    _self_heal_failures.pop(id_reuniao, None)
    return envelope_id


@router.get("/{id_reuniao}/signatarios/status")
@limiter.limit("60/minute")
async def get_signatarios_status(
    request: Request,
    id_reuniao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna lista live de signatarios do ClickSign pra essa reuniao.

    Usado pelo SignatariosCard (polling 30s + botão "Atualizar") pra mostrar
    quem ja assinou vs quem falta, sem o diretor precisar entrar no ClickSign.

    Modo degradado (HTTP 200 + `legacy_warning`): reunioes enviadas antes da
    migration 039 ficam sem `envelope_id_clicksign`, entao devolvemos a lista
    local (todos `pending`) + flag pra UI exibir banner explicativo.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    allowed = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed is not None and id_reuniao not in allowed:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = (
        supabase.table("reunioes")
        .select("id_reuniao, status_ata, envelope_key_clicksign, envelope_id_clicksign, modo_interno_desde")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    reuniao = result.data[0]

    if not reuniao.get("envelope_key_clicksign"):
        raise HTTPException(status_code=400, detail="Reunião ainda não foi enviada para assinatura digital")

    from app.services import aceite_service

    # Progresso do nascimento incremental (ADR 0030): "Pendências criadas: X de Y"
    progresso = aceite_service.progresso_pendencias(supabase, id_reuniao)

    if reuniao.get("modo_interno_desde"):
        # Modo interno (ADR 0030): o Envelope morreu (recusa/cancelamento/
        # deadline sem assinaturas), então não há o que consultar na ClickSign.
        # A verdade por signatário vive no Registro de Aceites: quem tem aceite
        # firmou compromisso; os demais seguem pendentes.
        return _signatarios_status_modo_interno(supabase, reuniao, progresso)

    envelope_id = reuniao.get("envelope_id_clicksign")
    if not envelope_id:
        envelope_id = _try_recover_envelope_id(supabase, reuniao)
    if not envelope_id:
        locais = _fetch_signatarios_locais(supabase, id_reuniao)
        return {
            "total": len(locais),
            "assinaram": 0,
            "envelope_id": None,
            "signatarios": locais,
            **progresso,
            "legacy_warning": (
                "Não conseguimos consultar automaticamente o status das assinaturas desta Ata. "
                "Confira diretamente no painel da ClickSign. O webhook continua marcando a Ata "
                "como ASSINADA quando todos concluírem."
            ),
            "clicksign_url": settings.clicksign_base_url,
        }

    from app.services import clicksign_service

    signers = clicksign_service.list_signers(envelope_id)
    if signers is None:
        raise HTTPException(
            status_code=503,
            detail="Não foi possível consultar status dos signatários no ClickSign. Tente novamente.",
        )

    locais_by_email = {p["email"]: p for p in _fetch_signatarios_locais(supabase, id_reuniao) if p["email"]}
    signatarios_out: list[dict] = []
    for s in signers:
        local = locais_by_email.get(s.get("email") or "")
        signatarios_out.append(
            {
                "signer_id": s.get("signer_id"),
                "nome": s.get("nome") or (local["nome"] if local else ""),
                "email": s.get("email") or "",
                "status": s.get("status") or "pending",
                "signed_at": s.get("signed_at"),
            }
        )
    return {
        "total": len(signatarios_out),
        "assinaram": sum(1 for s in signatarios_out if s["status"] == "signed"),
        "envelope_id": envelope_id,
        "signatarios": signatarios_out,
        **progresso,
    }


@router.post("/{id_reuniao}/signatarios/{signer_id}/lembrar")
@limiter.limit("10/minute")
async def lembrar_signatario(
    request: Request,
    id_reuniao: str,
    signer_id: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Reenvia o email de assinatura para um signatário pendente.

    Usado pelo botão "Lembrar" no SignatariosCard ao lado de cada signer com
    status `pending`. Backend chama ClickSign com mensagem PT-BR custom.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não pode reenviar lembrete")

    allowed = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed is not None and id_reuniao not in allowed:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = (
        supabase.table("reunioes")
        .select("id_reuniao, status_ata, envelope_id_clicksign, envelope_key_clicksign, tipo, data, modo_interno_desde")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    reuniao = result.data[0]

    if reuniao.get("status_ata") != "AGUARDANDO_ASSINATURA":
        raise HTTPException(status_code=400, detail="Reunião não está aguardando assinatura")

    if reuniao.get("modo_interno_desde"):
        # Modo interno (ADR 0030): o Envelope morreu e nenhuma ação via
        # ClickSign fica disponível (sem lembrete, sem reenvio).
        raise HTTPException(
            status_code=400,
            detail="Reunião no modo interno de aceites: o Envelope foi encerrado e não há ações via ClickSign",
        )

    envelope_id = reuniao.get("envelope_id_clicksign")
    if not envelope_id:
        envelope_id = _try_recover_envelope_id(supabase, reuniao)
    if not envelope_id:
        raise HTTPException(
            status_code=400,
            detail="Reunião enviada antes da atualização (migration 039) — lembrete individual indisponível",
        )

    from app.services import clicksign_service

    message = _build_reminder_message(reuniao)
    ok = clicksign_service.remind_signer(envelope_id, signer_id, message=message)
    if not ok:
        raise HTTPException(status_code=502, detail="Não foi possível enviar o lembrete via ClickSign")

    return {"sent": True, "signer_id": signer_id}


@router.delete("/{id_reuniao}")
async def cancelar_reuniao(
    id_reuniao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Deleta permanentemente uma reunião PROGRAMADA ou em ERRO.

    Quem pode cancelar:
    - super_admin sempre.
    - diretor / presidente / gerente sempre.
    - secretária pode cancelar qualquer reunião PROGRAMADA (gestão de agendamentos).
    """
    result = supabase.table("reunioes").select("status_ata, criada_por").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    status_ata = reuniao["status_ata"]
    if status_ata not in ["PROGRAMADA", "ERRO"]:
        raise HTTPException(
            status_code=400,
            detail=f"Apenas reuniões PROGRAMADAS ou em ERRO podem ser deletadas (status atual: {status_ata})",
        )

    me = await get_participante_for_user(current_user, supabase)
    if not me:
        raise HTTPException(status_code=403, detail="Participante não encontrado")

    autorizado = False
    if is_super_admin(me):
        autorizado = True
    elif is_secretaria(me):
        autorizado = status_ata == "PROGRAMADA"
    else:
        autorizado = (me.get("role") or "") in ("diretor", "presidente", "gerente")

    if not autorizado:
        raise HTTPException(status_code=403, detail="Permissão insuficiente para cancelar esta reunião")

    supabase.table("reunioes").delete().eq("id_reuniao", id_reuniao).execute()
    logger.info(f"Reunião {id_reuniao} DELETADA permanentemente por {current_user['email']}")
    return {"message": "Reunião deletada com sucesso.", "id_reuniao": id_reuniao}


@router.delete("/grupo/{id_grupo_recorrencia}")
async def cancelar_grupo_recorrencia(
    id_grupo_recorrencia: str,
    current_user: dict = Depends(require_role("diretor", "presidente", "gerente")),
    supabase=Depends(get_supabase_client),
):
    """Deleta permanentemente todas as reuniões PROGRAMADAS ou em ERRO de um mesmo grupo de recorrência."""
    result = supabase.table("reunioes").select("status_ata").eq("id_grupo_recorrencia", id_grupo_recorrencia).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Grupo de recorrência não encontrado")

    bloqueadas = [r for r in result.data if r["status_ata"] not in ["PROGRAMADA", "ERRO"]]
    if bloqueadas:
        raise HTTPException(
            status_code=400,
            detail=f"A exclusão do grupo foi bloqueada: {len(bloqueadas)} reunião(ões) desta série já estão em andamento ou concluídas.",  # noqa: E501
        )

    del_res = supabase.table("reunioes").delete().eq("id_grupo_recorrencia", id_grupo_recorrencia).execute()
    len(del_res.data) if hasattr(del_res, "data") and del_res.data else 0
    logger.info(f"Grupo de recorrência {id_grupo_recorrencia} DELETADO por {current_user['email']}")
    return {"message": "Série recorrente deletada com sucesso.", "id_grupo_recorrencia": id_grupo_recorrencia}


@router.patch("/{id_reuniao}")
async def editar_reuniao(
    id_reuniao: str,
    req: EditarReuniaoRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Edita campos de uma reunião PROGRAMADA.

    Qualquer usuário autenticado pode editar enquanto status == PROGRAMADA
    (gate de status logo abaixo). Secretária edita reuniões alheias livremente
    como parte da visão de gestora de agendamentos.
    """
    result = supabase.table("reunioes").select("status_ata, criada_por").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    reuniao = result.data[0]
    if reuniao["status_ata"] != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Apenas reuniões PROGRAMADAS podem ser editadas")

    me = await get_participante_for_user(current_user, supabase)

    # Se for secretária editando facilitador, valida que o novo existe e está ativo.
    if req.facilitador_id and is_secretaria(me):
        fac = supabase.table("participantes").select("id, ativo").eq("id", req.facilitador_id).limit(1).execute()
        if not fac.data:
            raise HTTPException(status_code=404, detail="Facilitador informado não encontrado")
        if not fac.data[0].get("ativo"):
            raise HTTPException(status_code=400, detail="Facilitador informado está inativo")

    updates: dict = {k: v for k, v in req.model_dump(exclude_none=True).items()}
    if "tipo" in updates and updates["tipo"] is not None:
        updates["tipo"] = updates["tipo"].value if hasattr(updates["tipo"], "value") else updates["tipo"]
    if "hora_inicio" in updates and updates["hora_inicio"] is not None:
        updates["hora_inicio"] = str(updates["hora_inicio"])
    if "hora_fim" in updates and updates["hora_fim"] is not None:
        updates["hora_fim"] = str(updates["hora_fim"])
    if "data" in updates and updates["data"] is not None:
        updates["data"] = str(updates["data"])

    if not updates:
        raise HTTPException(status_code=422, detail="Nenhum campo enviado para atualizar")

    # Se a data ou hora foi alterada, reseta a flag de lembrete 24h.
    # O job de cron reavalia e envia de novo se a nova programacao ainda for >= 24h no futuro.
    if "data" in updates or "hora_inicio" in updates:
        updates["lembrete_24h_enviado_at"] = None

    supabase.table("reunioes").update(updates).eq("id_reuniao", id_reuniao).execute()
    logger.info(f"Reunião {id_reuniao} editada: {list(updates.keys())}")
    return {"message": "Reunião atualizada com sucesso.", "campos_atualizados": list(updates.keys())}


@router.post("/{id_reuniao}/participantes")
async def adicionar_participantes(
    id_reuniao: str,
    req: AdicionarParticipantesRequest,
    background_tasks: BackgroundTasks,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Adiciona participantes a uma reunião PROGRAMADA."""
    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Só é possível adicionar participantes em reuniões PROGRAMADAS")

    # Quem ja estava na reuniao nao recebe convite de novo. Calcula delta antes do upsert.
    existentes_res = (
        supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute()
    )
    existentes = {row["participante_id"] for row in (existentes_res.data or [])}
    novos_ids = [pid for pid in req.participante_ids if pid not in existentes]

    rows = [{"id_reuniao": id_reuniao, "participante_id": pid} for pid in req.participante_ids]
    # upsert to avoid duplicates (UNIQUE constraint)
    supabase.table("reuniao_participantes").upsert(rows, on_conflict="id_reuniao,participante_id").execute()
    logger.info(f"Participantes {req.participante_ids} adicionados à reunião {id_reuniao}")

    if novos_ids:
        background_tasks.add_task(reuniao_email_service.enviar_convites, supabase, id_reuniao, novos_ids)

    return {"message": f"{len(rows)} participante(s) adicionado(s)."}


@router.delete("/{id_reuniao}/participantes/{participante_id}")
async def remover_participante(
    id_reuniao: str,
    participante_id: str,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Remove um participante de uma reunião PROGRAMADA."""
    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Só é possível remover participantes em reuniões PROGRAMADAS")

    supabase.table("reuniao_participantes").delete().eq("id_reuniao", id_reuniao).eq(
        "participante_id", participante_id
    ).execute()
    logger.info(f"Participante {participante_id} removido da reunião {id_reuniao}")
    return {"message": "Participante removido."}


@router.post("/{id_reuniao}/anexar-transcricao")
@limiter.limit("5/minute")
async def anexar_transcricao(
    request: Request,
    id_reuniao: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Anexa uma transcrição a uma reunião PROGRAMADA existente e dispara o pipeline de IA."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    from app.services.transcricao_extractor import extrair_texto

    file_bytes = await file.read()
    try:
        texto_extraido, extensao = extrair_texto(file.filename or "", file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    result = supabase.table("reunioes").select("status_ata, tipo").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Só é possível anexar transcrição em reuniões PROGRAMADAS")

    tipo = result.data[0].get("tipo") or "Gerencial"

    # Atualiza status para PROCESSANDO (mantém todos os outros campos)
    supabase.table("reunioes").update({"status_ata": "PROCESSANDO"}).eq("id_reuniao", id_reuniao).execute()

    from app.pipeline.orchestrator import run_pipeline

    background_tasks.add_task(run_pipeline, supabase, id_reuniao, file_bytes, texto_extraido, extensao, tipo)

    logger.info(f"Transcrição anexada à reunião {id_reuniao} por {current_user['email']}, pipeline iniciado")
    return {
        "id_reuniao": id_reuniao,
        "status": "PROCESSANDO",
        "message": "Transcrição recebida. Pipeline de IA iniciado em background.",
    }


@router.post("/upload-transcricao")
@limiter.limit("5/minute")
async def upload_transcricao(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    titulo: str = Form(...),
    data: date = Form(...),
    tipo: TipoReuniao = Form(TipoReuniao.GERENCIAL),
    objetivo: str | None = Form(None),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    from app.services.transcricao_extractor import extrair_texto

    file_bytes = await file.read()
    try:
        texto_extraido, extensao = extrair_texto(file.filename or "", file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    id_reuniao = _generate_reuniao_id(data)

    # Cria o registro no banco antes de disparar o pipeline
    reuniao_data = {
        "id_reuniao": id_reuniao,
        "data": str(data),
        "tipo": tipo.value,
        "objetivo": objetivo,
        "titulo": titulo,
        "status_ata": "PROGRAMADA",
        "fonte": "MOCK",
    }
    insert_result = supabase.table("reunioes").insert(reuniao_data).execute()
    if not insert_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar reunião")

    # Atualiza para PROCESSANDO antes de disparar o pipeline
    supabase.table("reunioes").update({"status_ata": "PROCESSANDO"}).eq("id_reuniao", id_reuniao).execute()

    # Dispara o pipeline em background (não bloqueia o response)
    from app.pipeline.orchestrator import run_pipeline

    background_tasks.add_task(run_pipeline, supabase, id_reuniao, file_bytes, texto_extraido, extensao, tipo.value)

    logger.info(f"Reunião {id_reuniao} criada por {current_user['email']}, pipeline iniciado")
    return {
        "id_reuniao": id_reuniao,
        "titulo": titulo,
        "status": "PROCESSANDO",
        "message": "Transcrição recebida. Pipeline de IA iniciado em background.",
    }


@router.post("/{id_reuniao}/resolver-participantes", status_code=200)
async def resolver_participantes(
    id_reuniao: str,
    body: ResolverParticipantesRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """
    Resolve participantes não reconhecidos pela IA e retoma o pipeline.

    Para cada nome identificado pela IA mas não matchado, o facilitador escolhe:
    - `vincular`: apontar um participante existente (interno ativo ou externo já
      cadastrado) — evita duplicatas quando o matcher falhou por similaridade.
    - `cadastrar_externo`: criar novo externo (email opcional).
    - `ignorar`: descartar (erro de transcrição) e remover o nome de
      `json_ata.participantes` (fatia #203), sumindo da Ata e do PDF.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    # 1. Verifica reunião + status
    reuniao = supabase.table("reunioes").select("status_ata, tipo, json_ata").eq("id_reuniao", id_reuniao).execute()
    if not reuniao.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if reuniao.data[0]["status_ata"] != "AGUARDANDO_RESOLUCAO":
        raise HTTPException(
            status_code=400,
            detail=f"Reunião não está em AGUARDANDO_RESOLUCAO (status atual: {reuniao.data[0]['status_ata']})",
        )

    # Limite defensivo — evita payloads abusivos que bloqueariam o event loop
    if len(body.resolucoes) > 200:
        raise HTTPException(status_code=400, detail="Máximo 200 resoluções por chamada")

    from app.pipeline.orchestrator import resume_pipeline_after_resolution

    if not body.resolucoes:
        supabase.table("reunioes").update({"participantes_nao_reconhecidos": []}).eq("id_reuniao", id_reuniao).execute()
        background_tasks.add_task(resume_pipeline_after_resolution, supabase, id_reuniao)
        return {
            "message": "0 resolução(ões) processada(s). Pipeline retomando...",
            "vinculados": 0,
            "cadastrados": 0,
            "ignorados": 0,
        }

    itens_vincular = [r for r in body.resolucoes if r.acao == "vincular"]
    itens_cadastrar = [r for r in body.resolucoes if r.acao == "cadastrar_externo"]
    itens_ignorar = [r for r in body.resolucoes if r.acao == "ignorar"]

    participante_ids_final: list[str] = []

    # 2. vincular — valida existência + ativo
    if itens_vincular:
        ids_solicitados = [r.participante_id for r in itens_vincular if r.participante_id]
        sel = supabase.table("participantes").select("id, ativo").in_("id", ids_solicitados).execute()
        existentes: dict[str, dict] = {row["id"]: row for row in (sel.data or [])}
        for item in itens_vincular:
            p = existentes.get(item.participante_id or "")
            if not p:
                raise HTTPException(
                    status_code=404,
                    detail=f"Participante {item.participante_id} não encontrado",
                )
            if not p.get("ativo"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Participante {item.participante_id} está inativo e não pode ser vinculado",
                )
            participante_ids_final.append(item.participante_id)  # type: ignore[arg-type]

    # 3. cadastrar_externo — dedup por email (quando há), depois provisiona o restante
    if itens_cadastrar:
        from app.services.auth_provisioning import provision_with_compensation
        from app.services.cargo_mapping import get_cargo_info

        def _build_participante_dict(dados) -> dict:
            """Monta dict de INSERT em participantes a partir de NovoExternoDados."""
            cargo_info = get_cargo_info(dados.cargo) if dados.cargo else None
            role = cargo_info.role if cargo_info else "coordenador"
            setor = cargo_info.setor if cargo_info else None
            area = cargo_info.area if cargo_info else None
            return {
                "nome_completo": dados.nome_completo,
                "cargo": dados.cargo,
                "email": dados.email,
                "setor": setor,
                "area": area,
                "role": role,
                "ativo": True,
                "is_externo": True,
            }

        emails_para_checar = [
            item.novo_externo.email  # type: ignore[union-attr]
            for item in itens_cadastrar
            if item.novo_externo and item.novo_externo.email
        ]
        by_email: dict[str, dict] = {}
        if emails_para_checar:
            existentes_res = (
                supabase.table("participantes").select("id, email").in_("email", emails_para_checar).execute()
            )
            by_email = {(row["email"] or "").lower(): row for row in (existentes_res.data or [])}

        novos_to_create: list = []
        for item in itens_cadastrar:
            dados = item.novo_externo
            if not dados:
                continue
            key = (dados.email or "").lower()
            if key and key in by_email:
                participante_ids_final.append(by_email[key]["id"])
            else:
                novos_to_create.append(item)

        if novos_to_create:
            dicts = [_build_participante_dict(item.novo_externo) for item in novos_to_create]
            tasks = [asyncio.to_thread(provision_with_compensation, supabase, d, role=d["role"]) for d in dicts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for item, res in zip(novos_to_create, results):
                if isinstance(res, Exception):
                    logger.warning(
                        f"[resolver-participantes] provision falhou para {item.novo_externo.nome_completo}: {res}"  # type: ignore[union-attr]
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=(
                            f"Erro ao criar participante {item.novo_externo.nome_completo}: {res}"  # type: ignore[union-attr]
                        ),
                    )
                new_participant, _auth_uid = res
                participante_ids_final.append(new_participant["id"])

    # 4. UPSERT em reuniao_participantes (dedup defensivo caso dois itens apontem pro mesmo id)
    if participante_ids_final:
        unique_ids = list(dict.fromkeys(participante_ids_final))
        links = [{"id_reuniao": id_reuniao, "participante_id": pid} for pid in unique_ids]
        supabase.table("reuniao_participantes").upsert(links, on_conflict="id_reuniao,participante_id").execute()

    # 5. ignorar: remove também de json_ata.participantes, reaproveitando o helper
    # do ADR 0023 (fatia #203), pra sumir da tela e do PDF, casando pelo nome
    # canônico que a IA registrou (não cria vínculo no roster).
    update_reuniao: dict = {"participantes_nao_reconhecidos": []}
    if itens_ignorar:
        json_ata = reuniao.data[0].get("json_ata") or {}
        participantes = json_ata.get("participantes")
        for item in itens_ignorar:
            participantes, _ = participantes_ata_service.remover_da_lista(participantes, item.nome_identificado)
        json_ata["participantes"] = participantes
        update_reuniao["json_ata"] = json_ata

    # 6. Limpa o JSONB (todas as entradas foram processadas nesta chamada)
    supabase.table("reunioes").update(update_reuniao).eq("id_reuniao", id_reuniao).execute()

    # 7. Retoma pipeline
    background_tasks.add_task(resume_pipeline_after_resolution, supabase, id_reuniao)

    return {
        "message": (
            f"{len(itens_vincular)} vinculado(s), {len(itens_cadastrar)} cadastrado(s), "
            f"{len(itens_ignorar)} ignorado(s). Pipeline retomando..."
        ),
        "vinculados": len(itens_vincular),
        "cadastrados": len(itens_cadastrar),
        "ignorados": len(itens_ignorar),
    }


@router.post("/{id_reuniao}/pular-resolucao", status_code=200)
async def pular_resolucao_participantes(
    id_reuniao: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """
    Ignora participantes não reconhecidos e retoma o pipeline sem cadastrá-los.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not reuniao.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if reuniao.data[0]["status_ata"] != "AGUARDANDO_RESOLUCAO":
        raise HTTPException(
            status_code=400,
            detail=f"Reunião não está em AGUARDANDO_RESOLUCAO (status atual: {reuniao.data[0]['status_ata']})",
        )

    # Clear nao_reconhecidos and resume
    supabase.table("reunioes").update({"participantes_nao_reconhecidos": []}).eq("id_reuniao", id_reuniao).execute()

    from app.pipeline.orchestrator import resume_pipeline_after_resolution

    background_tasks.add_task(resume_pipeline_after_resolution, supabase, id_reuniao)

    return {"message": "Resolução ignorada. Pipeline retomando..."}


@router.post("/{id_reuniao}/reprocessar")
@limiter.limit("3/minute")
async def reprocessar_reuniao(
    request: Request,
    id_reuniao: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("*").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao.get("status_ata") == "ASSINADA":
        raise HTTPException(status_code=400, detail="Reunião já assinada não pode ser reprocessada")

    from app.services.storage import download_file

    transcricao = download_file(
        supabase,
        settings.supabase_storage_bucket_transcricoes,
        f"{id_reuniao}/transcricao.txt",
    )
    if not transcricao:
        raise HTTPException(status_code=404, detail="Arquivo de transcrição não encontrado no Storage")

    supabase.table("reunioes").update({"status_ata": "PROCESSANDO"}).eq("id_reuniao", id_reuniao).execute()

    from app.pipeline.orchestrator import run_pipeline

    texto_extraido = transcricao.decode("utf-8", errors="replace")
    background_tasks.add_task(
        run_pipeline,
        supabase,
        id_reuniao,
        transcricao,
        texto_extraido,
        ".txt",
        reuniao.get("tipo", "Gerencial"),
    )

    return {"id_reuniao": id_reuniao, "status": "PROCESSANDO", "message": "Reprocessamento iniciado"}


@router.post("/{id_reuniao}/aprovar")
@limiter.limit("10/minute")
async def aprovar_reuniao(
    request: Request,
    id_reuniao: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = (
        supabase.table("reunioes")
        .select("status_ata, url_pdf_preliminar, tipo, objetivo")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Reunião não está aguardando validação")

    # Dispara o fluxo ClickSign em background
    from app.services import clicksign_service

    background_tasks.add_task(clicksign_service.start_signature_flow, supabase, id_reuniao, result.data[0])

    return {"message": "Ata aprovada. Processo de assinatura digital iniciado."}


@router.post("/{id_reuniao}/aprovar-sem-assinatura")
@limiter.limit("10/minute")
async def aprovar_sem_assinatura(
    request: Request,
    id_reuniao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Finaliza a Ata sem assinatura digital: cria as Pendências na hora e leva a
    Reunião ao estado terminal APROVADA — sem Envelope, sem ClickSign.

    Irmão do /aprovar: mesmas guardas (Secretária 403, status 400, reunião 404),
    mas SÍNCRONO — retorna a contagem de Pendências pra UI. Reusa liberar_pendencias
    (idempotente). Ordem: cria as Pendências primeiro, marca APROVADA depois — se a
    criação falhar, o status permanece AGUARDANDO_VALIDACAO e a ação é re-tentável
    (a idempotência garante que não duplica).
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Reunião não está aguardando validação")

    from app.services.pendencia_service import liberar_pendencias

    total = liberar_pendencias(supabase, id_reuniao, origem="APROVACAO_SEM_ASSINATURA")
    supabase.table("reunioes").update({"status_ata": "APROVADA"}).eq("id_reuniao", id_reuniao).execute()

    audit.log_action(
        supabase,
        actor=me,
        action="APROVACAO_SEM_ASSINATURA",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"total_pendencias": total},
        request=request,
    )

    logger.info(
        f"Reunião {id_reuniao} APROVADA sem assinatura por {current_user['email']} ({total} pendência(s) criada(s))"
    )
    return {
        "status": "APROVADA",
        "total_pendencias": total,
        "message": (
            f"Ata aprovada sem assinatura. {total} pendência(s) criada(s)."
            if total
            else "Ata aprovada sem assinatura. Nenhuma pendência a criar."
        ),
    }


@router.post("/{id_reuniao}/corrigir")
@limiter.limit("5/minute")
async def corrigir_reuniao(
    request: Request,
    id_reuniao: str,
    req: CorrecaoInternaRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = (
        supabase.table("reunioes").select("status_ata, ciclo_correcao, tipo").eq("id_reuniao", id_reuniao).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Reunião não pode ser corrigida neste status")

    ciclo = reuniao.get("ciclo_correcao", 0)
    if not is_super_admin(me) and ciclo >= 5:
        raise HTTPException(status_code=400, detail="Atingido o limite de 5 ciclos de correção.")

    supabase.table("reunioes").update({"status_ata": "PROCESSANDO", "ciclo_correcao": ciclo + 1}).eq(
        "id_reuniao", id_reuniao
    ).execute()

    from app.pipeline.orchestrator import run_correction_pipeline

    # Dispara o novo pipeline de correção inteligente
    background_tasks.add_task(run_correction_pipeline, supabase, id_reuniao, req.texto)

    return {"message": "Instrução de correção recebida. A IA está reescrevendo a ata em background."}


@router.post("/{id_reuniao}/chat-correcao")
@limiter.limit("10/minute")
async def chat_correcao_endpoint(
    request: Request,
    id_reuniao: str,
    req: ChatCorrecaoRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Chat conversacional para correção de ATA. Leve, síncrono, sem pipeline."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade (#194): só age em Reunião que o chamador enxerga (mesmo gate
    # da Ata Guiada) - 404 pra não vazar existência.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata, json_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Chat de correção disponível apenas em AGUARDANDO_VALIDACAO")

    json_ata = reuniao.get("json_ata")
    if not json_ata:
        raise HTTPException(status_code=400, detail="ATA não disponível")

    if not req.messages:
        raise HTTPException(status_code=422, detail="Lista de mensagens não pode ser vazia")

    from app.services.ai_processor import chat_correcao

    response = chat_correcao(
        json_ata_atual=json_ata,
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
        section_context=req.section_context,
        current_plan=[item.model_dump() for item in req.current_plan],
    )

    return response


# ─── Ata Guiada (ADR 0005): segundo modo de gerar a Ata, sem Transcrição ─────


@router.post("/{id_reuniao}/ata-guiada/chat")
@limiter.limit("10/minute")
async def chat_ata_guiada_endpoint(
    request: Request,
    id_reuniao: str,
    req: AtaGuiadaChatRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Chat da Ata Guiada — stateless, síncrono, sem pipeline. Recebe o rascunho
    enxuto + as mensagens e devolve `{ reply, rascunho }`. Disponível só enquanto a
    Reunião está PROGRAMADA (antes de existir Ata). Espelha o `chat-correcao`.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade: só atende reunião que o usuário enxerga (mesmo gate do
    # patch_quadro_atribuicao) — evita probe de existência/status por id alheio.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(
            status_code=400,
            detail="A Ata Guiada só é montada enquanto a Reunião está PROGRAMADA",
        )

    if not req.messages:
        raise HTTPException(status_code=422, detail="Lista de mensagens não pode ser vazia")

    from app.services.ai_processor import chat_ata_guiada
    from app.services.resolucao_service import montar_candidatos

    # Resolução ao vivo (ADR 0008, #79): o agente enxerga os candidatos no prompt
    # e o quadro devolvido volta vinculado deterministicamente pelo backend.
    return chat_ata_guiada(
        rascunho=req.rascunho,
        messages=[{"role": m.role, "content": m.content} for m in req.messages],
        section_context=req.section_context,
        documento_apoio=req.documento_apoio,
        candidatos=montar_candidatos(supabase, id_reuniao),
    )


@router.post("/{id_reuniao}/ata-guiada/extrair-documento")
@limiter.limit("10/minute")
async def extrair_documento_apoio(
    request: Request,
    id_reuniao: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Extrai o texto de um Documento de apoio (ADR 0006) para a Ata Guiada,
    reusando o `transcricao_extractor` (mesma normalização do anexar-transcrição).
    É contexto efêmero: devolve só o texto normalizado — não persiste na Reunião
    nem dispara o pipeline. Mesmos gates do chat da Guiada: Secretária 403, visível
    só ao dono (404) e apenas com a Reunião PROGRAMADA (400).
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Mesma visibilidade do chat: não vaza existência/status por id alheio.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(
            status_code=400,
            detail="A Ata Guiada só é montada enquanto a Reunião está PROGRAMADA",
        )

    from app.services.transcricao_extractor import extrair_texto

    file_bytes = await file.read()
    try:
        texto, extensao = extrair_texto(file.filename or "", file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return {"texto": texto, "filename": file.filename, "extensao": extensao}


@router.post("/{id_reuniao}/ata-guiada/concluir")
@limiter.limit("10/minute")
async def concluir_ata_guiada(
    request: Request,
    id_reuniao: str,
    req: AtaGuiadaConcluirRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Persiste a Ata Guiada: grava o `json_ata` enxuto (resumo + quadro), marca
    `metodo_geracao=GUIADA` e leva a Reunião de PROGRAMADA a AGUARDANDO_VALIDACAO.

    A partir daí o fluxo existente assume sem mudanças — validar, editar o quadro
    (`PATCH quadro-atribuicoes`) e finalizar sem assinatura (`aprovar-sem-assinatura`
    → `liberar_pendencias`). Nunca toca ClickSign nem gera PDF (ADR 0005).
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade: só conclui reunião que o usuário enxerga (mesmo gate do
    # patch_quadro_atribuicao) — sem isso, qualquer Facilitador sobrescreveria a Ata
    # de qualquer Reunião PROGRAMADA conhecendo só o id.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "PROGRAMADA":
        raise HTTPException(
            status_code=400,
            detail="A Ata Guiada só pode ser concluída a partir de uma Reunião PROGRAMADA",
        )

    from app.services.resolucao_service import montar_candidatos, resolver_quadro

    rascunho = req.rascunho or {}
    # Só itens dict entram no quadro — protege liberar_pendencias (que faz acao.get(...))
    # de um item malformado (ex.: string) virar 500 na liberação de pendências.
    quadro = [a for a in (rascunho.get("quadro_atribuicoes") or []) if isinstance(a, dict)]
    # Revalidação server-side dos vínculos (ADR 0008): o quadro do cliente não é
    # confiável — anota ids que faltarem e derruba id forjado/inexistente/inativo,
    # que volta à Resolução pelo nome. Id inválido nunca persiste no json_ata.
    quadro = resolver_quadro(quadro, montar_candidatos(supabase, id_reuniao))
    json_ata = {
        "resumo_executivo": (rascunho.get("resumo_executivo") or "").strip(),
        "quadro_atribuicoes": quadro,
    }

    # Responsável casado entra no roster da Reunião (espelha o Pipeline de
    # Transcrição) — mantém o invariante do dropdown da validação (responsável
    # escolhível ⊆ roster). O on_conflict torna o upsert idempotente.
    vinculados = {a["responsavel_id"] for a in quadro if a.get("responsavel_id")}
    if vinculados:
        supabase.table("reuniao_participantes").upsert(
            [{"id_reuniao": id_reuniao, "participante_id": pid} for pid in sorted(vinculados)],
            on_conflict="id_reuniao,participante_id",
        ).execute()

    supabase.table("reunioes").update(
        {
            "json_ata": json_ata,
            "metodo_geracao": "GUIADA",
            "status_ata": "AGUARDANDO_VALIDACAO",
        }
    ).eq("id_reuniao", id_reuniao).execute()

    audit.log_action(
        supabase,
        actor=me,
        action="CONCLUSAO_ATA_GUIADA",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"n_acoes": len(json_ata["quadro_atribuicoes"])},
        request=request,
    )

    logger.info(
        f"Reunião {id_reuniao} concluída via Ata Guiada por {current_user['email']} "
        f"({len(json_ata['quadro_atribuicoes'])} ação(ões) no quadro)"
    )
    return {"status": "AGUARDANDO_VALIDACAO", "json_ata": json_ata}


@router.patch("/{id_reuniao}/quadro-atribuicoes/{index}")
async def patch_quadro_atribuicao(
    id_reuniao: str,
    index: int,
    body: QuadroAtribuicaoUpdate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Edita um item do `json_ata.quadro_atribuicoes` antes da liberação de pendências.

    Permitido em ATA com status AGUARDANDO_VALIDACAO e, no modo interno (ADR
    0030), só para ações ainda sem Pendência. Substitui a edição implícita
    por chat pra o caso do responsável: quando `responsavel_participante_id` é
    informado, sobrescreve `responsavel`/`cargo` com os dados canônicos do participante
    (corrige o bug em que mudar o nome via chat deixava o cargo desatualizado) e grava
    o vínculo (`responsavel_id`) no item — honrado depois por `liberar_pendencias`
    (ADR 0008). Quando só texto vem, grava como texto livre (fallback "Digitar
    livremente" do dropdown) e limpa o vínculo anterior.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    # Visibilidade — usuário precisa ter acesso à reunião (mesmo gate dos demais
    # endpoints que lêem/mutam ata). Sem isso, qualquer autenticado podia editar
    # quadro_atribuicoes de qualquer reunião conhecendo só o id.
    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = (
        supabase.table("reunioes")
        .select("status_ata, json_ata, modo_interno_desde")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    # Janela de edição: AGUARDANDO_VALIDACAO (regra original) ou o modo interno
    # (ADR 0030, issue #276): AGUARDANDO_ASSINATURA com Envelope morto, onde só
    # as ações ainda sem Pendência seguem editáveis.
    modo_interno = reuniao["status_ata"] == "AGUARDANDO_ASSINATURA" and bool(reuniao.get("modo_interno_desde"))
    if reuniao["status_ata"] != "AGUARDANDO_VALIDACAO" and not modo_interno:
        raise HTTPException(
            status_code=400,
            detail="Quadro de atribuições só pode ser editado quando a ATA aguarda validação",
        )

    json_ata = reuniao.get("json_ata") or {}
    quadro = json_ata.get("quadro_atribuicoes") or []
    if index < 0 or index >= len(quadro):
        raise HTTPException(status_code=404, detail="Item do quadro de atribuições não encontrado")

    if modo_interno:
        # Ação com Pendência nascida fica travada: o compromisso já foi firmado
        # por quem assinou e não pode mudar por baixo dele. Pendência legada sem
        # quadro_pos (liberação total pré-incremental) trava o quadro inteiro.
        # Sem filtro de soft-delete: o índice único de quadro_pos também não
        # filtra, e linha viva ou não já representa compromisso firmado.
        rows = supabase.table("pendencias").select("quadro_pos").eq("id_reuniao", id_reuniao).execute().data or []
        posicoes = {r.get("quadro_pos") for r in rows}
        if None in posicoes or index in posicoes:
            raise HTTPException(
                status_code=409,
                detail="Esta ação já virou Pendência e está travada para edição no modo interno",
            )

    item = dict(quadro[index])

    if body.responsavel_participante_id:
        p_join = (
            supabase.table("reuniao_participantes")
            .select("participantes(id, nome_completo, cargo)")
            .eq("id_reuniao", id_reuniao)
            .eq("participante_id", body.responsavel_participante_id)
            .limit(1)
            .execute()
        )
        if not p_join.data or not p_join.data[0].get("participantes"):
            raise HTTPException(
                status_code=422,
                detail="Participante não está vinculado a esta reunião",
            )
        participante = p_join.data[0]["participantes"]
        item["responsavel"] = (participante.get("nome_completo") or "").strip()
        item["cargo"] = (participante.get("cargo") or "").strip()
        item["responsavel_id"] = body.responsavel_participante_id
    else:
        if body.responsavel is not None:
            item["responsavel"] = body.responsavel.strip()
        if body.cargo is not None:
            item["cargo"] = body.cargo.strip()
        # Texto livre desfaz o vínculo: sem isso, a Pendência liberada ainda
        # apontaria para o Colaborador antigo (ADR 0008).
        item["responsavel_id"] = None

    item["editado_manualmente"] = True

    quadro[index] = item
    json_ata["quadro_atribuicoes"] = quadro

    upd = supabase.table("reunioes").update({"json_ata": json_ata}).eq("id_reuniao", id_reuniao).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar quadro de atribuições")

    logger.info(
        f"[Reunioes] Quadro de atribuições item {index} editado em {id_reuniao}: "
        f"responsavel='{item.get('responsavel')}' cargo='{item.get('cargo')}'"
    )

    if modo_interno:
        # Reatribuição no modo interno (issue #277): o novo responsável precisa
        # do link de Aceite interno (ou, se já firmou compromisso, da liberação
        # direta). A recoleta é idempotente; falha não bloqueia a edição.
        from app.services import aceite_service

        try:
            aceite_service.iniciar_coleta_interna(supabase, id_reuniao)
        except Exception as e:
            logger.error(f"[Reunioes] Falha best-effort na recoleta de aceites de {id_reuniao}: {e}")

    return item


async def _carregar_ata_para_edicao(id_reuniao: str, current_user: dict, supabase) -> dict:
    """Gates + carga da Ata para os editores manuais da validação (ADR 0023).

    Réplica parcial dos gates de `patch_quadro_atribuicao`: Secretária sem
    acesso (403), visibilidade da Reunião (404) e janela AGUARDANDO_VALIDACAO
    (400). Diferente do quadro de atribuições, a lista de participantes da Ata
    não abre no modo interno (ADR 0030, issue #276): fica restrita à validação.
    Devolve a linha `{status_ata, json_ata}` já validada.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a atas")

    allowed_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_ids is not None and id_reuniao not in allowed_ids:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    result = supabase.table("reunioes").select("status_ata, json_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(
            status_code=400,
            detail="A lista de participantes só pode ser editada quando a Ata aguarda validação",
        )
    return reuniao


@router.post("/{id_reuniao}/ata-participantes/excluir", status_code=200)
async def excluir_participante_ata(
    id_reuniao: str,
    body: ExcluirParticipanteAtaRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Exclui um participante da lista da Ata na validação (ADR 0023).

    Remove o nome de `json_ata.participantes` E o vínculo espelhado em
    `reuniao_participantes`, mantendo tela, PDF e ClickSign consistentes. Bloqueia
    (400, nada muda) quando a pessoa é responsável de uma ação no Quadro, preservando
    o invariante do ADR 0008 (responsável escolhível ⊆ roster). Determinístico, sem IA.
    """
    reuniao = await _carregar_ata_para_edicao(id_reuniao, current_user, supabase)
    json_ata = reuniao.get("json_ata") or {}
    quadro = json_ata.get("quadro_atribuicoes") or []

    # Resolve o nome ao vínculo do roster (se houver): necessário para espelhar a
    # exclusão e para a guarda do responsável — ambos antes de qualquer escrita.
    participante_id = participantes_ata_service.id_no_roster_por_nome(supabase, id_reuniao, body.nome)
    if participante_id and participantes_ata_service.eh_responsavel_no_quadro(quadro, participante_id):
        raise HTTPException(
            status_code=400,
            detail=(
                f'"{body.nome}" é responsável por uma ação no Quadro de Atribuições. '
                "Reatribua a ação antes de excluir o participante."
            ),
        )

    nova_lista, removeu = participantes_ata_service.remover_da_lista(json_ata.get("participantes"), body.nome)
    if not removeu:
        raise HTTPException(status_code=404, detail="Participante não encontrado na lista da Ata")

    # Espelha no roster: remove o vínculo (idempotente; no-op quando não há vínculo).
    if participante_id:
        supabase.table("reuniao_participantes").delete().eq("id_reuniao", id_reuniao).eq(
            "participante_id", participante_id
        ).execute()

    json_ata["participantes"] = nova_lista
    upd = supabase.table("reunioes").update({"json_ata": json_ata}).eq("id_reuniao", id_reuniao).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar a lista de participantes")

    logger.info(f"[Reunioes] Participante '{body.nome}' excluído da Ata {id_reuniao} (vínculo={participante_id})")
    return {"participantes": nova_lista, "total": len(nova_lista)}


@router.post("/{id_reuniao}/ata-participantes", status_code=200)
async def adicionar_participante_ata(
    id_reuniao: str,
    body: AdicionarParticipanteAtaRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Adiciona um participante do cadastro à lista da Ata na validação (ADR 0023).

    Grava a entrada canônica em `json_ata.participantes` e faz upsert idempotente do
    vínculo em `reuniao_participantes` (sem duplicar). Mesmo contrato de `vincular`
    da tela de resolução (participante existente e ativo). Determinístico, sem IA.
    """
    reuniao = await _carregar_ata_para_edicao(id_reuniao, current_user, supabase)
    json_ata = reuniao.get("json_ata") or {}

    sel = (
        supabase.table("participantes")
        .select("id, nome_completo, cargo, setor, ativo")
        .eq("id", body.participante_id)
        .limit(1)
        .execute()
    )
    if not sel.data:
        raise HTTPException(status_code=404, detail=f"Participante {body.participante_id} não encontrado")
    participante = sel.data[0]
    if not participante.get("ativo"):
        raise HTTPException(status_code=400, detail="Participante inativo não pode ser adicionado")

    # Espelha no roster: upsert idempotente (não duplica vínculo já existente).
    supabase.table("reuniao_participantes").upsert(
        [{"id_reuniao": id_reuniao, "participante_id": body.participante_id}],
        on_conflict="id_reuniao,participante_id",
    ).execute()

    nova_lista, _ = participantes_ata_service.adicionar_na_lista(
        json_ata.get("participantes"),
        participante.get("nome_completo") or "",
        participante.get("cargo"),
        participante.get("setor"),
    )
    json_ata["participantes"] = nova_lista
    upd = supabase.table("reunioes").update({"json_ata": json_ata}).eq("id_reuniao", id_reuniao).execute()
    if not upd.data:
        raise HTTPException(status_code=500, detail="Erro ao salvar a lista de participantes")

    logger.info(f"[Reunioes] Participante {body.participante_id} adicionado à Ata {id_reuniao}")
    return {"participantes": nova_lista, "total": len(nova_lista)}


# ─── Acoes de super admin (force) ────────────────────────────────────────────


@router.delete("/{id_reuniao}/force")
async def force_deletar_reuniao(
    id_reuniao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin only: deleta uma reuniao em QUALQUER status. Motivo obrigatorio."""
    result = supabase.table("reunioes").select("status_ata, titulo").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    status_before = result.data[0].get("status_ata")
    titulo = result.data[0].get("titulo")

    supabase.table("reunioes").delete().eq("id_reuniao", id_reuniao).execute()

    audit.log_action(
        supabase,
        actor=actor,
        action="DELETE_REUNIAO",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"status_before": status_before, "titulo": titulo},
        reason=body.reason,
        request=request,
    )

    logger.info(
        f"Reunião {id_reuniao} FORCE-DELETADA (status_before={status_before}) por super admin {actor.get('email')}"
    )
    return {
        "message": "Reunião deletada com sucesso (force).",
        "id_reuniao": id_reuniao,
        "status_before": status_before,
    }


@router.patch("/{id_reuniao}/force-status")
async def force_status_reuniao(
    id_reuniao: str,
    body: ForceStatusReuniaoRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin only: forca qualquer transicao de status (mesmo invalidas). Motivo obrigatorio."""
    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    status_before = result.data[0].get("status_ata")
    status_after = body.novo_status.value

    supabase.table("reunioes").update({"status_ata": status_after}).eq("id_reuniao", id_reuniao).execute()

    audit.log_action(
        supabase,
        actor=actor,
        action="FORCE_STATUS",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={"status_before": status_before, "status_after": status_after},
        reason=body.reason,
        request=request,
    )

    logger.info(
        f"Reunião {id_reuniao} FORCE-STATUS {status_before} → {status_after} por super admin {actor.get('email')}"
    )
    return {
        "message": "Status forçado com sucesso.",
        "id_reuniao": id_reuniao,
        "status_before": status_before,
        "status_after": status_after,
    }


@router.patch("/{id_reuniao}/force")
async def force_editar_reuniao(
    id_reuniao: str,
    body: ForceEditReuniaoRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin only: edita qualquer campo de uma reuniao em qualquer status.

    Inclui participantes e facilitador. Motivo obrigatorio.
    """
    result = supabase.table("reunioes").select("status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    status_before = result.data[0].get("status_ata")

    # Extrai campos editaveis (exclui reason + participante_ids, tratados separadamente)
    payload = body.model_dump(exclude_none=True)
    payload.pop("reason", None)
    participante_ids = payload.pop("participante_ids", None)

    updates: dict = {}
    for key, value in payload.items():
        if key == "tipo":
            updates[key] = value.value if hasattr(value, "value") else value
        elif key in ("hora_inicio", "hora_fim", "data") and value is not None:
            updates[key] = str(value)
        else:
            updates[key] = value

    campos_mudados: list[str] = list(updates.keys())
    if participante_ids is not None:
        campos_mudados.append("participante_ids")

    if not updates and participante_ids is None:
        raise HTTPException(status_code=422, detail="Nenhum campo enviado para atualizar")

    # Se a data ou hora foi alterada, reseta a flag de lembrete 24h (mesma logica do editar_reuniao).
    if "data" in updates or "hora_inicio" in updates:
        updates["lembrete_24h_enviado_at"] = None

    if updates:
        supabase.table("reunioes").update(updates).eq("id_reuniao", id_reuniao).execute()

    if participante_ids is not None:
        # Substitui a lista de participantes da reunião
        supabase.table("reuniao_participantes").delete().eq("id_reuniao", id_reuniao).execute()
        if participante_ids:
            rows = [{"id_reuniao": id_reuniao, "participante_id": pid} for pid in participante_ids]
            supabase.table("reuniao_participantes").upsert(rows, on_conflict="id_reuniao,participante_id").execute()

    audit.log_action(
        supabase,
        actor=actor,
        action="EDIT_REUNIAO_FORCE",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={
            "status_before": status_before,
            "campos_mudados": campos_mudados,
        },
        reason=body.reason,
        request=request,
    )

    logger.info(f"Reunião {id_reuniao} FORCE-EDITADA (campos={campos_mudados}) por super admin {actor.get('email')}")
    return {
        "message": "Reunião editada com sucesso (force).",
        "id_reuniao": id_reuniao,
        "campos_atualizados": campos_mudados,
    }


@router.post("/{id_reuniao}/transferir-facilitador")
async def transferir_facilitador(
    id_reuniao: str,
    body: TransferirFacilitadorRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin troca o facilitador de uma reuniao por outro super admin.

    Validacoes:
    - Reuniao existe e nao foi deletada (soft-delete via deleted_at).
    - Novo facilitador existe, e super admin e esta ativo.
    - Novo facilitador e diferente do atual.

    Side effects:
    - Atualiza reunioes.facilitador_id.
    - Adiciona o novo facilitador em reuniao_participantes (idempotente) se
      ainda nao estiver, garantindo que ele apareca na lista da reuniao com
      a coroa.
    - Grava audit_log com action="TRANSFER_FACILITADOR".
    """
    r = (
        supabase.table("reunioes")
        .select("id_reuniao, facilitador_id, deleted_at")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )
    if not r.data or r.data[0].get("deleted_at"):
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    facilitador_anterior = r.data[0].get("facilitador_id")

    p = (
        supabase.table("participantes")
        .select("id, is_super_admin, ativo, nome_completo")
        .eq("id", body.novo_facilitador_id)
        .execute()
    )
    if not p.data:
        raise HTTPException(status_code=404, detail="Novo facilitador não encontrado")
    novo = p.data[0]
    if not novo.get("is_super_admin"):
        raise HTTPException(status_code=400, detail="Novo facilitador deve ser Super Admin")
    if not novo.get("ativo"):
        raise HTTPException(status_code=400, detail="Novo facilitador está inativo")

    if facilitador_anterior == body.novo_facilitador_id:
        raise HTTPException(status_code=400, detail="Esse já é o facilitador atual")

    supabase.table("reunioes").update({"facilitador_id": body.novo_facilitador_id}).eq(
        "id_reuniao", id_reuniao
    ).execute()

    rp = (
        supabase.table("reuniao_participantes")
        .select("participante_id")
        .eq("id_reuniao", id_reuniao)
        .eq("participante_id", body.novo_facilitador_id)
        .execute()
    )
    adicionado_como_participante = not rp.data
    if adicionado_como_participante:
        supabase.table("reuniao_participantes").upsert(
            {"id_reuniao": id_reuniao, "participante_id": body.novo_facilitador_id},
            on_conflict="id_reuniao,participante_id",
        ).execute()

    audit.log_action(
        supabase,
        actor=actor,
        action="TRANSFER_FACILITADOR",
        target_type="reuniao",
        target_id=id_reuniao,
        metadata={
            "facilitador_anterior": facilitador_anterior,
            "facilitador_novo": body.novo_facilitador_id,
            "facilitador_novo_nome": novo.get("nome_completo"),
            "adicionado_como_participante": adicionado_como_participante,
        },
        request=request,
    )

    logger.info(
        f"Reunião {id_reuniao} TRANSFER_FACILITADOR "
        f"{facilitador_anterior} → {body.novo_facilitador_id} "
        f"por super admin {actor.get('email')}"
    )
    return {
        "message": "Facilitador transferido com sucesso.",
        "id_reuniao": id_reuniao,
        "facilitador_anterior": facilitador_anterior,
        "facilitador_novo": body.novo_facilitador_id,
        "adicionado_como_participante": adicionado_como_participante,
    }
