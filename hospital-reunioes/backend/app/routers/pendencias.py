import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from starlette.requests import Request

from app.dependencies import (
    get_allowed_reuniao_ids,
    get_current_user,
    get_participante_for_user,
    get_participante_id_for_user,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
    require_acesso_reunioes,
    require_super_admin,
)
from app.models.admin_schemas import ForceEditPendenciaRequest, ReasonRequest
from app.models.schemas import PendenciaResponse, PendenciaStats, PendenciaUpdate
from app.services import audit
from app.services.notificacao_service import criar_notificacao_responsavel
from app.utils.query_params import parse_csv_param

router = APIRouter(
    prefix="/pendencias",
    tags=["pendencias"],
    # Gate de contexto (ADR 0007): sem papel nas Reuniões -> 403 em todo o router.
    dependencies=[Depends(require_acesso_reunioes)],
)
logger = logging.getLogger(__name__)


def _enrich_externo_flag(supabase, rows: list[dict]) -> list[dict]:
    """Enriquece cada pendência com `responsavel_is_externo` via lookup em batch.

    Importante para o kanban/cards distinguirem responsáveis externos (sem email,
    ativos=false) dos internos — sem esse flag, a UI não sabe que deve oferecer
    o dropdown de co-responsável nem renderizar a badge "Externo".
    """
    if not rows:
        return rows
    resp_ids = {r.get("responsavel_id") for r in rows if r.get("responsavel_id")}
    if not resp_ids:
        for r in rows:
            r["responsavel_is_externo"] = None
        return rows
    res = supabase.table("participantes").select("id, is_externo").in_("id", list(resp_ids)).execute()
    flag_by_id: dict[str, bool] = {p["id"]: bool(p.get("is_externo")) for p in (res.data or [])}
    for r in rows:
        rid = r.get("responsavel_id")
        r["responsavel_is_externo"] = flag_by_id.get(rid) if rid else None
    return rows


def _enrich_comentarios_count(supabase, rows: list[dict]) -> list[dict]:
    """Enriquece cada pendência com `total_comentarios` via lookup em batch.

    A lista (tabela e kanban) usa esse contador pra mostrar um chip discreto
    sinalizando "tem chat aqui" sem precisar abrir o modal pra cada item.
    """
    if not rows:
        return rows
    ids = [r.get("id_acao") for r in rows if r.get("id_acao")]
    if not ids:
        for r in rows:
            r["total_comentarios"] = 0
        return rows
    res = supabase.table("comentarios_pendencias").select("id_acao").in_("id_acao", ids).execute()
    counts: dict[str, int] = {}
    for c in res.data or []:
        cid = c.get("id_acao")
        if cid:
            counts[cid] = counts.get(cid, 0) + 1
    for r in rows:
        rid = r.get("id_acao")
        r["total_comentarios"] = counts.get(rid, 0) if rid else 0
    return rows


@router.get("/stats", response_model=PendenciaStats)
async def get_pendencias_stats(
    responsavel_id: str | None = Query(None, description="Responsáveis separados por vírgula"),
    setor: str | None = Query(None, description="Setores separados por vírgula"),
    facilitador_id: str | None = Query(None, description="Facilitadores separados por vírgula"),
    prazo_de: date | None = Query(None),
    prazo_ate: date | None = Query(None),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna contadores de pendências agrupados por status para o dashboard."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    allowed_reuniao_ids = await get_allowed_reuniao_ids(current_user, supabase)
    my_participante_id = await get_participante_id_for_user(current_user, supabase)

    query = (
        supabase.table("pendencias")
        .select("status, responsavel_id, prazo, id_reuniao, co_responsavel_id")
        .is_("deleted_at", "null")
    )

    # Resolve filtro de facilitador cedo (afeta a aplicação de visibilidade)
    facilitadores = parse_csv_param(facilitador_id)
    facilitator_meeting_ids: list[str] | None = None
    if facilitadores:
        rq = supabase.table("reunioes").select("id_reuniao").is_("deleted_at", "null")
        rq = (
            rq.in_("facilitador_id", facilitadores)
            if len(facilitadores) > 1
            else rq.eq("facilitador_id", facilitadores[0])
        )
        rq_res = rq.execute()
        facilitator_meeting_ids = [r["id_reuniao"] for r in (rq_res.data or [])]
        if not facilitator_meeting_ids:
            return PendenciaStats()

    # Visibilidade binária + filtro facilitador.
    # Quando facilitador está presente, ele é mais restritivo que o OR de co-responsável:
    # ignoramos co_responsavel_id pra que "filtrar pelo facilitador X" signifique
    # exatamente "pendências das reuniões dele", sem vazar pendências externas.
    if facilitator_meeting_ids is not None:
        if allowed_reuniao_ids is not None:
            allowed_set = set(allowed_reuniao_ids)
            facilitator_meeting_ids = [m for m in facilitator_meeting_ids if m in allowed_set]
            if not facilitator_meeting_ids:
                return PendenciaStats()
        query = query.in_("id_reuniao", facilitator_meeting_ids)
    elif allowed_reuniao_ids is not None:
        if not allowed_reuniao_ids and not my_participante_id:
            return PendenciaStats()
        elif my_participante_id:
            # Visível: reuniões permitidas OU co-responsável.
            condicoes = [f"co_responsavel_id.eq.{my_participante_id}"]
            if allowed_reuniao_ids:
                condicoes.insert(0, f"id_reuniao.in.({','.join(allowed_reuniao_ids)})")
            query = query.or_(",".join(condicoes))
        else:
            query = query.in_("id_reuniao", allowed_reuniao_ids)

    # Filtro por setor (super user only — filtra por responsavel_id de participantes do setor)
    setores = parse_csv_param(setor)
    if setores and allowed_reuniao_ids is None:
        has_sem_setor = "Sem Setor" in setores
        setores_real = [s for s in setores if s != "Sem Setor"]
        pq = supabase.table("participantes").select("id")
        if has_sem_setor and setores_real:
            in_list = ",".join(setores_real)
            pq = pq.or_(f"setor.is.null,setor.in.({in_list})")
        elif has_sem_setor:
            pq = pq.is_("setor", "null")
        elif len(setores_real) == 1:
            pq = pq.eq("setor", setores_real[0])
        else:
            pq = pq.in_("setor", setores_real)
        p_res = pq.execute()
        sector_ids = [p["id"] for p in (p_res.data or [])]
        if sector_ids:
            query = query.in_("responsavel_id", sector_ids)
        else:
            return PendenciaStats()

    # Filtro por responsável específico
    responsaveis = parse_csv_param(responsavel_id)
    if responsaveis:
        if len(responsaveis) == 1:
            query = query.eq("responsavel_id", responsaveis[0])
        else:
            query = query.in_("responsavel_id", responsaveis)

    # Filtros temporais
    if prazo_de:
        query = query.gte("prazo", str(prazo_de))
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.execute()
    rows = result.data or []

    stats = PendenciaStats()
    for row in rows:
        s = row.get("status", "")
        if s == "PENDENTE":
            stats.pendente += 1
        elif s == "EM_PROGRESSO":
            stats.em_progresso += 1
        elif s == "CONCLUIDO":
            stats.concluido += 1
        elif s == "ATRASADO":
            stats.atrasado += 1
        elif s == "CANCELADO":
            stats.cancelado += 1
        elif s == "REPACTUADA":
            stats.repactuada += 1
    stats.total = len(rows)
    return stats


@router.get("/minhas", response_model=list[PendenciaResponse])
async def list_minhas_pendencias(
    status: str | None = Query(None),
    prazo_ate: date | None = Query(None),
    limit: int = Query(200, le=1000),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Lista apenas as pendências atreladas diretamente ao usuário autenticado."""
    participante = await get_participante_for_user(current_user, supabase)
    if is_secretaria(participante):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")
    if not participante:
        return []

    participante_id = participante["id"]
    query = supabase.table("pendencias").select("*").eq("responsavel_id", participante_id).is_("deleted_at", "null")

    if status:
        query = query.eq("status", status)
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.order("prazo", desc=False, nullsfirst=False).range(offset, offset + limit - 1).execute()
    return _enrich_externo_flag(supabase, result.data or [])


@router.get("", response_model=list[PendenciaResponse])
async def list_pendencias(
    response: Response,
    status: str | None = Query(None),
    responsavel_id: str | None = Query(None, description="Responsáveis separados por vírgula"),
    id_reuniao: str | None = Query(None),
    prazo_de: date | None = Query(None),
    prazo_ate: date | None = Query(None),
    setor: str | None = Query(None, description="Setores separados por vírgula"),
    facilitador_id: str | None = Query(None, description="Facilitadores separados por vírgula"),
    limit: int = Query(500, le=2000),
    offset: int = Query(0),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Lista pendências com visibilidade binária: super users veem tudo, demais veem por reunião.

    Retorna header `X-Total-Count` com o total de itens (antes de limit/offset) para
    que a UI consiga sinalizar truncamento e/ou paginação.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    allowed_reuniao_ids = await get_allowed_reuniao_ids(current_user, supabase)
    my_participante_id = await get_participante_id_for_user(current_user, supabase)

    query = supabase.table("pendencias").select("*", count="exact").is_("deleted_at", "null")

    # Resolve filtro de facilitador cedo (afeta a aplicação de visibilidade)
    facilitadores = parse_csv_param(facilitador_id)
    facilitator_meeting_ids: list[str] | None = None
    if facilitadores:
        rq = supabase.table("reunioes").select("id_reuniao").is_("deleted_at", "null")
        rq = (
            rq.in_("facilitador_id", facilitadores)
            if len(facilitadores) > 1
            else rq.eq("facilitador_id", facilitadores[0])
        )
        rq_res = rq.execute()
        facilitator_meeting_ids = [r["id_reuniao"] for r in (rq_res.data or [])]
        if not facilitator_meeting_ids:
            response.headers["X-Total-Count"] = "0"
            return []

    # Visibilidade binária + filtro facilitador.
    # Quando facilitador está presente, é mais restritivo: ignoramos o OR de co-responsável
    # para que "filtrar pelo facilitador X" signifique exatamente "pendências das reuniões dele".
    if facilitator_meeting_ids is not None:
        if allowed_reuniao_ids is not None:
            allowed_set = set(allowed_reuniao_ids)
            facilitator_meeting_ids = [m for m in facilitator_meeting_ids if m in allowed_set]
            if not facilitator_meeting_ids:
                response.headers["X-Total-Count"] = "0"
                return []
        query = query.in_("id_reuniao", facilitator_meeting_ids)
    elif allowed_reuniao_ids is not None:
        if not allowed_reuniao_ids and not my_participante_id:
            return []
        elif my_participante_id:
            # Visível: reuniões permitidas OU co-responsável.
            condicoes = [f"co_responsavel_id.eq.{my_participante_id}"]
            if allowed_reuniao_ids:
                condicoes.insert(0, f"id_reuniao.in.({','.join(allowed_reuniao_ids)})")
            query = query.or_(",".join(condicoes))
        else:
            query = query.in_("id_reuniao", allowed_reuniao_ids)

    # Filtro por setor (super user only)
    setores = parse_csv_param(setor)
    if setores and allowed_reuniao_ids is None:
        has_sem_setor = "Sem Setor" in setores
        setores_real = [s for s in setores if s != "Sem Setor"]
        pq = supabase.table("participantes").select("id")
        if has_sem_setor and setores_real:
            in_list = ",".join(setores_real)
            pq = pq.or_(f"setor.is.null,setor.in.({in_list})")
        elif has_sem_setor:
            pq = pq.is_("setor", "null")
        elif len(setores_real) == 1:
            pq = pq.eq("setor", setores_real[0])
        else:
            pq = pq.in_("setor", setores_real)
        p_res = pq.execute()
        sector_ids = [p["id"] for p in (p_res.data or [])]
        if sector_ids:
            query = query.in_("responsavel_id", sector_ids)
        else:
            return []

    # Filtro por responsável específico
    responsaveis = parse_csv_param(responsavel_id)
    if responsaveis:
        if len(responsaveis) == 1:
            query = query.eq("responsavel_id", responsaveis[0])
        else:
            query = query.in_("responsavel_id", responsaveis)

    if status:
        query = query.eq("status", status)
    if id_reuniao:
        query = query.eq("id_reuniao", id_reuniao)
    if prazo_de:
        query = query.gte("prazo", str(prazo_de))
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.order("prazo", desc=False, nullsfirst=False).range(offset, offset + limit - 1).execute()
    response.headers["X-Total-Count"] = str(result.count or 0)
    enriched = _enrich_externo_flag(supabase, result.data or [])
    return _enrich_comentarios_count(supabase, enriched)


@router.get("/{id_acao}", response_model=PendenciaResponse)
async def get_pendencia(
    id_acao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Retorna uma pendência específica."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    result = supabase.table("pendencias").select("*").eq("id_acao", id_acao).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = result.data[0]

    # Visibilidade binária: super users veem tudo, demais checam reunião + co-responsável.
    allowed_reuniao_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_reuniao_ids is not None:
        my_id = await get_participante_id_for_user(current_user, supabase)
        pendencia_reuniao = pendencia.get("id_reuniao")
        pendencia_coresp = pendencia.get("co_responsavel_id")
        if pendencia_reuniao not in allowed_reuniao_ids and pendencia_coresp != my_id:
            raise HTTPException(status_code=404, detail="Pendência não encontrada")

    return _enrich_externo_flag(supabase, [pendencia])[0]


@router.patch("/{id_acao}", response_model=PendenciaResponse)
async def update_pendencia_status(
    id_acao: str,
    req: PendenciaUpdate,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Atualiza campos de uma pendência. Quando concluída, incrementa acoes_concluidas na reunião."""
    me_check = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me_check):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    existing = (
        supabase.table("pendencias")
        .select("id_acao, id_reuniao, status, responsavel_id, co_responsavel_id, descricao_acao")
        .eq("id_acao", id_acao)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = existing.data[0]

    # Visibilidade binária (reunião + co-responsável)
    allowed_reuniao_ids = await get_allowed_reuniao_ids(current_user, supabase)
    if allowed_reuniao_ids is not None:
        my_id = await get_participante_id_for_user(current_user, supabase)
        pendencia_reuniao = pendencia.get("id_reuniao")
        pendencia_coresp = pendencia.get("co_responsavel_id")
        if pendencia_reuniao not in allowed_reuniao_ids and pendencia_coresp != my_id:
            raise HTTPException(status_code=404, detail="Pendência não encontrada")

    # Validar co_responsavel_id se enviado
    if req.co_responsavel_id is not None:
        me = await get_participante_for_user(current_user, supabase, fields="id, role, is_super_admin")
        if not me or not is_super_admin(me):
            raise HTTPException(status_code=403, detail="Apenas super admins podem atribuir co-responsável")
        # Verificar que responsável da pendência é externo
        resp_id = pendencia.get("responsavel_id")
        if resp_id:
            resp = supabase.table("participantes").select("is_externo").eq("id", resp_id).execute()
            if resp.data and not resp.data[0].get("is_externo"):
                raise HTTPException(
                    status_code=422,
                    detail="Co-responsável só pode ser definido para pendências de participantes externos",
                )
        # Verificar que co-responsável é interno
        co_resp = supabase.table("participantes").select("is_externo").eq("id", req.co_responsavel_id).execute()
        if not co_resp.data:
            raise HTTPException(status_code=422, detail="Co-responsável não encontrado")
        if co_resp.data[0].get("is_externo"):
            raise HTTPException(status_code=422, detail="Co-responsável deve ser um participante interno")

    status_anterior = pendencia["status"]
    responsavel_anterior = pendencia.get("responsavel_id")

    # Extrair apenas campos enviados na requisição
    update_data = req.model_dump(exclude_unset=True)
    if not update_data:
        result = supabase.table("pendencias").select("*").eq("id_acao", id_acao).execute()
        return _enrich_externo_flag(supabase, result.data or [])[0]

    # Denormalizar co_responsavel_nome quando co_responsavel_id é setado
    if "co_responsavel_id" in update_data and update_data["co_responsavel_id"]:
        co_resp_data = (
            supabase.table("participantes").select("nome_completo").eq("id", update_data["co_responsavel_id"]).execute()
        )
        if co_resp_data.data:
            update_data["co_responsavel_nome"] = co_resp_data.data[0]["nome_completo"]

    # Quando responsavel_id muda, puxar nome+cargo canônicos do participante.
    # `cargo` e `responsavel_nome` só são sobrescritos quando NÃO foram enviados
    # no body — assim quem mandou explicitamente preserva override manual.
    if "responsavel_id" in update_data and update_data["responsavel_id"]:
        resp_data = (
            supabase.table("participantes")
            .select("nome_completo, cargo")
            .eq("id", update_data["responsavel_id"])
            .execute()
        )
        if resp_data.data:
            canonical = resp_data.data[0]
            if "responsavel_nome" not in update_data and canonical.get("nome_completo"):
                update_data["responsavel_nome"] = canonical["nome_completo"]
            if "cargo" not in update_data and canonical.get("cargo"):
                update_data["cargo"] = canonical["cargo"]

    if "status" in update_data and update_data["status"] is not None:
        update_data["status"] = update_data["status"].value
        if update_data["status"] == "REPACTUADA":
            update_data["prazo"] = None

    if "prazo" in update_data and update_data["prazo"] is not None:
        update_data["prazo"] = str(update_data["prazo"])

    # Atualizar pendência no banco
    result = supabase.table("pendencias").update(update_data).eq("id_acao", id_acao).execute()

    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar pendência")

    novo_status = result.data[0].get("status")
    novo_responsavel_id = result.data[0].get("responsavel_id")

    # Tratar contador de ações concluídas quando status muda.
    if "status" in update_data and novo_status != status_anterior:
        if pendencia.get("id_reuniao"):
            if novo_status == "CONCLUIDO" and status_anterior != "CONCLUIDO":
                _incrementar_acoes_concluidas(supabase, pendencia["id_reuniao"])
            if status_anterior == "CONCLUIDO" and novo_status != "CONCLUIDO":
                _decrementar_acoes_concluidas(supabase, pendencia["id_reuniao"])
        logger.info(f"[Pendencias] {id_acao}: status alterado {status_anterior} → {novo_status}")

    # Notificar novo responsável quando ele é atribuído (e mudou de pessoa)
    if "responsavel_id" in update_data and novo_responsavel_id and novo_responsavel_id != responsavel_anterior:
        p_user = (
            supabase.table("participantes").select("nome_completo").eq("auth_user_id", current_user["id"]).execute()
        )
        atribuido_por = p_user.data[0]["nome_completo"] if p_user.data else current_user.get("email", "Sistema")

        descricao = pendencia.get("descricao_acao") or result.data[0].get("descricao_acao", "")
        criar_notificacao_responsavel(
            supabase,
            id_acao=id_acao,
            descricao_acao=descricao,
            responsavel_id=novo_responsavel_id,
            atribuido_por=atribuido_por,
        )

    return _enrich_externo_flag(supabase, result.data or [])[0]


def _incrementar_acoes_concluidas(supabase, id_reuniao: str) -> None:
    try:
        supabase.rpc("incrementar_acoes_concluidas", {"p_id_reuniao": id_reuniao}).execute()
    except Exception as e:
        logger.error(f"[Pendencias] Erro ao incrementar acoes_concluidas para {id_reuniao}: {e}")


def _decrementar_acoes_concluidas(supabase, id_reuniao: str) -> None:
    try:
        supabase.rpc("decrementar_acoes_concluidas", {"p_id_reuniao": id_reuniao}).execute()
    except Exception as e:
        logger.error(f"[Pendencias] Erro ao decrementar acoes_concluidas para {id_reuniao}: {e}")


# ─── Acoes de super admin (force) ────────────────────────────────────────────


@router.delete("/{id_acao}/force")
async def force_deletar_pendencia(
    id_acao: str,
    body: ReasonRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin only: deleta uma pendencia em qualquer status. Motivo obrigatorio."""
    existing = (
        supabase.table("pendencias")
        .select("id_acao, id_reuniao, status, responsavel_id, descricao_acao")
        .eq("id_acao", id_acao)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = existing.data[0]
    status_before = pendencia.get("status")

    supabase.table("pendencias").delete().eq("id_acao", id_acao).execute()

    # Se estava concluida, decrementa contador da reuniao
    if status_before == "CONCLUIDO" and pendencia.get("id_reuniao"):
        _decrementar_acoes_concluidas(supabase, pendencia["id_reuniao"])

    audit.log_action(
        supabase,
        actor=actor,
        action="DELETE_PENDENCIA",
        target_type="pendencia",
        target_id=id_acao,
        metadata={
            "status_before": status_before,
            "id_reuniao": pendencia.get("id_reuniao"),
            "responsavel_id": pendencia.get("responsavel_id"),
            "descricao_acao": pendencia.get("descricao_acao"),
        },
        reason=body.reason,
        request=request,
    )

    logger.info(
        f"Pendencia {id_acao} FORCE-DELETADA (status_before={status_before}) por super admin {actor.get('email')}"
    )
    return {"message": "Pendência deletada com sucesso (force).", "id_acao": id_acao}


@router.patch("/{id_acao}/force", response_model=PendenciaResponse)
async def force_editar_pendencia(
    id_acao: str,
    body: ForceEditPendenciaRequest,
    request: Request,
    actor: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Super admin only: edita qualquer campo da pendencia em qualquer status.

    Motivo e OBRIGATORIO quando status ou responsavel_id sao alterados.
    """
    existing = (
        supabase.table("pendencias")
        .select("id_acao, id_reuniao, status, responsavel_id, co_responsavel_id, descricao_acao")
        .eq("id_acao", id_acao)
        .execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = existing.data[0]

    payload = body.model_dump(exclude_unset=True)
    reason = payload.pop("reason", None)

    if not payload:
        raise HTTPException(status_code=422, detail="Nenhum campo enviado para atualizar")

    # Motivo obrigatorio se mudar status ou responsavel
    muda_status = "status" in payload and payload["status"] is not None
    muda_responsavel = "responsavel_id" in payload and payload["responsavel_id"] != pendencia.get("responsavel_id")
    if (muda_status or muda_responsavel) and not reason:
        raise HTTPException(
            status_code=422,
            detail="Motivo (reason) é obrigatório ao alterar status ou responsável",
        )

    status_anterior = pendencia["status"]
    responsavel_anterior = pendencia.get("responsavel_id")

    # Normalizar valores
    update_data: dict = {}
    for key, value in payload.items():
        if key == "status" and value is not None:
            update_data[key] = value.value if hasattr(value, "value") else value
            if update_data[key] == "REPACTUADA":
                update_data["prazo"] = None
        elif key == "prazo" and value is not None:
            update_data[key] = str(value)
        else:
            update_data[key] = value

    # Denormalizar co_responsavel_nome quando co_responsavel_id e setado
    if "co_responsavel_id" in update_data and update_data["co_responsavel_id"]:
        co_resp_data = (
            supabase.table("participantes").select("nome_completo").eq("id", update_data["co_responsavel_id"]).execute()
        )
        if co_resp_data.data:
            update_data["co_responsavel_nome"] = co_resp_data.data[0]["nome_completo"]

    # Quando responsavel_id muda, puxar nome+cargo canônicos do participante.
    # `cargo` e `responsavel_nome` só são sobrescritos quando NÃO foram enviados
    # no body — assim quem mandou explicitamente preserva override manual.
    if "responsavel_id" in update_data and update_data["responsavel_id"]:
        resp_data = (
            supabase.table("participantes")
            .select("nome_completo, cargo")
            .eq("id", update_data["responsavel_id"])
            .execute()
        )
        if resp_data.data:
            canonical = resp_data.data[0]
            if "responsavel_nome" not in update_data and canonical.get("nome_completo"):
                update_data["responsavel_nome"] = canonical["nome_completo"]
            if "cargo" not in update_data and canonical.get("cargo"):
                update_data["cargo"] = canonical["cargo"]

    result = supabase.table("pendencias").update(update_data).eq("id_acao", id_acao).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar pendência")

    novo_status = result.data[0].get("status")
    novo_responsavel_id = result.data[0].get("responsavel_id")

    # Atualiza contador de acoes concluidas
    if "status" in update_data and novo_status != status_anterior and pendencia.get("id_reuniao"):
        if novo_status == "CONCLUIDO" and status_anterior != "CONCLUIDO":
            _incrementar_acoes_concluidas(supabase, pendencia["id_reuniao"])
        if status_anterior == "CONCLUIDO" and novo_status != "CONCLUIDO":
            _decrementar_acoes_concluidas(supabase, pendencia["id_reuniao"])

    audit.log_action(
        supabase,
        actor=actor,
        action="EDIT_PENDENCIA_FORCE",
        target_type="pendencia",
        target_id=id_acao,
        metadata={
            "campos_mudados": list(update_data.keys()),
            "status_before": status_anterior,
            "status_after": novo_status,
            "responsavel_before": responsavel_anterior,
            "responsavel_after": novo_responsavel_id,
        },
        reason=reason,
        request=request,
    )

    logger.info(
        f"Pendencia {id_acao} FORCE-EDITADA (campos={list(update_data.keys())}) por super admin {actor.get('email')}"
    )
    return _enrich_externo_flag(supabase, result.data or [])[0]
