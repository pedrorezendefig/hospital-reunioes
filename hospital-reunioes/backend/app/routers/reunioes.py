import asyncio
import logging
from datetime import UTC, date, datetime

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
    AdicionarParticipantesRequest,
    AgendarReuniaoRequest,
    ChatCorrecaoRequest,
    EditarReuniaoRequest,
    ResolverParticipantesRequest,
    ReuniaoResponse,
    TipoReuniao,
)
from app.services import audit, reuniao_email_service
from app.utils.query_params import parse_csv_param

router = APIRouter(prefix="/reunioes", tags=["reunioes"])
logger = logging.getLogger(__name__)


class CorrecaoInternaRequest(BaseModel):
    texto: str


def _generate_reuniao_id(data: date) -> str:
    import uuid

    ts = datetime.now().strftime("%H%M%S")
    uid = uuid.uuid4().hex[:2].upper()
    return f"RD_{data.strftime('%Y%m%d')}_{ts}{uid}"


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

    Visibilidade controlada por get_allowed_reuniao_ids. Para a secretária,
    isso retorna todas as reuniões PROGRAMADAS futuras (gestora de agendamentos).
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

    # Enricher with participants for PROGRAMADA meetings
    if reuniao.get("status_ata") == "PROGRAMADA":
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

    return reuniao


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

    Secretária só pode editar reuniões que ela criou (criada_por = self.id).
    Super_admin sempre pode. Demais usuários: comportamento padrão (precisam
    ser participantes/facilitadores da reunião via filtro de visibilidade).
    """
    result = supabase.table("reunioes").select("status_ata, criada_por").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    reuniao = result.data[0]
    if reuniao["status_ata"] != "PROGRAMADA":
        raise HTTPException(status_code=400, detail="Apenas reuniões PROGRAMADAS podem ser editadas")

    me = await get_participante_for_user(current_user, supabase)
    # Secretária pode editar qualquer reunião PROGRAMADA (ainda sem transcrição).
    # O check de status_ata == 'PROGRAMADA' acima já garante o gate.

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
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """
    Resolve participantes não reconhecidos pela IA e retoma o pipeline.

    Para cada nome identificado pela IA mas não matchado, o facilitador escolhe:
    - `vincular`: apontar um participante existente (interno ativo ou externo já
      cadastrado) — evita duplicatas quando o matcher falhou por similaridade.
    - `cadastrar_externo`: criar novo externo (email opcional).
    - `ignorar`: descartar (erro de transcrição).
    """
    # 1. Verifica reunião + status
    reuniao = supabase.table("reunioes").select("status_ata, tipo").eq("id_reuniao", id_reuniao).execute()
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

    # 5. Limpa o JSONB (todas as entradas foram processadas nesta chamada)
    supabase.table("reunioes").update({"participantes_nao_reconhecidos": []}).eq("id_reuniao", id_reuniao).execute()

    # 6. Retoma pipeline
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
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """
    Ignora participantes não reconhecidos e retoma o pipeline sem cadastrá-los.
    """
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
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    result = supabase.table("reunioes").select("*").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao.get("status_ata") == "ASSINADA":
        raise HTTPException(status_code=400, detail="Reunião já assinada não pode ser reprocessada")

    from app.config import settings
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
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
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


@router.post("/{id_reuniao}/aprovar-bypass")
async def aprovar_reuniao_bypass(
    id_reuniao: str,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    if not settings.enable_bypass_endpoints:
        raise HTTPException(status_code=404, detail="Not Found")
    """
    Aprova a ata e simula a assinatura digital instantaneamente (Bypass).
    Útil para testes locais sem precisar enviar documentos reais ao ClickSign.
    """
    result = supabase.table("reunioes").select("status_ata, url_pdf_preliminar").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")
    if result.data[0]["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Reunião não está aguardando validação")

    from datetime import datetime

    from app.services import pendencia_service

    pdf_preliminar = result.data[0].get("url_pdf_preliminar")

    # Marca como assinada diretamente
    update_data = {
        "status_ata": "ASSINADA",
        "data_assinatura": datetime.now(UTC).date().isoformat(),
        "url_pdf_assinado": pdf_preliminar,  # Usa o preliminar como documento assinado
    }

    supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()

    try:
        total = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="MANUAL_BYPASS")
        return {"message": f"Ata aprovada via bypass e {total} pendências liberadas com sucesso."}
    except Exception as e:
        logger.error(f"Erro ao liberar pendências no bypass para {id_reuniao}: {e}")
        return {
            "message": "Ata aprovada via bypass, mas houve um erro ao criar pendências automaticamente.",
            "error": str(e),
        }


@router.post("/aprovar-bypass-todas")
async def aprovar_reuniao_bypass_todas(
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    if not settings.enable_bypass_endpoints:
        raise HTTPException(status_code=404, detail="Not Found")
    """
    Aprova todas as atas aguardando validação simulando assinatura.
    Útil para testes locais em massa.
    """
    result = (
        supabase.table("reunioes")
        .select("id_reuniao, url_pdf_preliminar")
        .eq("status_ata", "AGUARDANDO_VALIDACAO")
        .execute()
    )
    if not result.data:
        return {"message": "Nenhuma reunião aguardando validação para aprovar."}

    from datetime import datetime

    from app.services import pendencia_service

    aprovadas = 0
    erros = 0
    for r in result.data:
        id_reuniao = r["id_reuniao"]
        pdf_preliminar = r.get("url_pdf_preliminar")

        update_data = {
            "status_ata": "ASSINADA",
            "data_assinatura": datetime.now(UTC).date().isoformat(),
            "url_pdf_assinado": pdf_preliminar,
        }

        try:
            supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()
            pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="BULK_BYPASS")
            aprovadas += 1
        except Exception as e:
            logger.error(f"Erro ao aprovar em massa a reunião {id_reuniao}: {e}")
            erros += 1

    return {"message": f"{aprovadas} atas aprovadas e pendências liberadas. {erros} falhas."}


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
    result = (
        supabase.table("reunioes").select("status_ata, ciclo_correcao, tipo").eq("id_reuniao", id_reuniao).execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao["status_ata"] != "AGUARDANDO_VALIDACAO":
        raise HTTPException(status_code=400, detail="Reunião não pode ser corrigida neste status")

    ciclo = reuniao.get("ciclo_correcao", 0)
    me = await get_participante_for_user(current_user, supabase)
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
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Chat conversacional para correção de ATA. Leve, síncrono, sem pipeline."""
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


@router.post("/{id_reuniao}/simular-assinatura")
async def simular_assinatura_clicksign(
    id_reuniao: str,
    background_tasks: BackgroundTasks,
    _: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    if not settings.enable_bypass_endpoints:
        raise HTTPException(status_code=404, detail="Not Found")
    """
    Simula o callback de conclusão do ClickSign (AutoClose/todos assinaram).

    Dispara exatamente o mesmo fluxo do webhook real:
    - Baixa o PDF do Storage (se disponível)
    - Atualiza status para ASSINADA
    - Libera as pendências (quadro_atribuicoes)

    USE APENAS EM DESENVOLVIMENTO / SANDBOX.
    """
    result = (
        supabase.table("reunioes")
        .select("id_reuniao, status_ata, envelope_key_clicksign, url_pdf_preliminar")
        .eq("id_reuniao", id_reuniao)
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=404, detail="Reunião não encontrada")

    reuniao = result.data[0]
    if reuniao["status_ata"] != "AGUARDANDO_ASSINATURA":
        raise HTTPException(
            status_code=400, detail=f"Reunião não está aguardando assinatura (status atual: {reuniao['status_ata']})"
        )

    background_tasks.add_task(_executar_simulacao, supabase, id_reuniao, reuniao)

    return {
        "message": "Simulação de assinatura iniciada. A ata será marcada como ASSINADA em instantes.",
        "id_reuniao": id_reuniao,
    }


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


def _executar_simulacao(supabase, id_reuniao: str, reuniao: dict) -> None:
    """Executa a lógica idêntica ao webhook ClickSign de conclusão."""
    from datetime import datetime

    from app.config import settings
    from app.services import pendencia_service, storage

    logger.info(f"[SimularAssinatura] Iniciando simulação para {id_reuniao}")

    try:
        update_data = {
            "status_ata": "ASSINADA",
            "data_assinatura": datetime.now(UTC).date().isoformat(),
        }

        # Tenta usar o PDF preliminar como "assinado" para o teste
        envelope_key = reuniao.get("envelope_key_clicksign")
        if envelope_key:
            try:
                from app.services import clicksign_service

                pdf_assinado = clicksign_service.get_signed_document(envelope_key)
                if pdf_assinado:
                    url_pdf_assinado = storage.upload_file(
                        supabase,
                        bucket=settings.supabase_storage_bucket_pdfs_assinados,
                        path=f"{id_reuniao}/ata_assinada.pdf",
                        content=pdf_assinado,
                        content_type="application/pdf",
                    )
                    update_data["url_pdf_assinado"] = url_pdf_assinado
                    logger.info(f"[SimularAssinatura] PDF assinado salvo: {url_pdf_assinado}")
                else:
                    # Sandbox sem PDF — usa o PDF preliminar como fallback
                    pdf_url = reuniao.get("url_pdf_preliminar")
                    if pdf_url:
                        update_data["url_pdf_assinado"] = pdf_url
                        logger.info(f"[SimularAssinatura] Usando PDF preliminar como fallback: {pdf_url}")
            except Exception as e:
                logger.warning(f"[SimularAssinatura] Não foi possível baixar PDF assinado: {e}. Continuando sem ele.")
                # Fallback: usa PDF preliminar
                pdf_url = reuniao.get("url_pdf_preliminar")
                if pdf_url:
                    update_data["url_pdf_assinado"] = pdf_url
        else:
            # Sem envelope (ex: ClickSign não configurado) — usa PDF preliminar
            pdf_url = reuniao.get("url_pdf_preliminar")
            if pdf_url:
                update_data["url_pdf_assinado"] = pdf_url

        supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()
        logger.info(f"[SimularAssinatura] ✅ Reunião {id_reuniao} marcada como ASSINADA.")

        total = pendencia_service.liberar_pendencias(supabase, id_reuniao, origem="SIMULACAO_CLICK")
        logger.info(f"[SimularAssinatura] 📋 {total} pendências liberadas para {id_reuniao}.")

    except Exception as e:
        logger.error(f"[SimularAssinatura] Erro crítico para {id_reuniao}: {e}", exc_info=True)
