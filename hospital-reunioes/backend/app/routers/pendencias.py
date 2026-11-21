import logging
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from postgrest.exceptions import APIError

from app.dependencies import (
    RECUSA_DO_NSP,
    get_current_user,
    get_participante_for_user,
    get_recorte_das_pendencias,
    get_supabase_client,
    is_secretaria,
    is_super_admin,
    require_acesso_reunioes,
)
from app.models.schemas import (
    AcaoPendenciaRequest,
    HistoricoPendenciaResponse,
    LinkDoAnexoResponse,
    PendenciaResponse,
    PendenciaStats,
)
from app.services import painel_reunioes, pendencia_anexo
from app.services.painel_reunioes import FiltrosDoPainel, PainelDeReunioes, montar_painel
from app.services.pendencia_acao import agir
from app.services.pendencia_ciclo import (
    AcaoRecusada,
    Comando,
    Papel,
    acoes_disponiveis,
    decidir,
    situacao,
)
from app.services.pendencia_service import e_lembrete_do_nucleo
from app.services.pendencias_consulta import (
    as_data,
    consultar_pendencias,
    contestacoes_abertas,
    filtrar_por_status,
    hoje_em_brasilia,
    ids_repactuados,
    no_recorte,
)
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

    # O recorte pelo vínculo (issue #1863) e o sigilo do Núcleo (issue #1772):
    # os números do painel contam só o que a lista mostra a esta pessoa.
    recorte = await get_recorte_das_pendencias(current_user, supabase)
    query = no_recorte(
        supabase.table("pendencias")
        .select("id_acao, status, responsavel_id, prazo, id_reuniao, co_responsavel_id")
        .is_("deleted_at", "null")
        .not_.is_("id_reuniao", "null"),
        recorte,
    )
    if query is None:
        return PendenciaStats()

    # Filtro de facilitador: as reuniões que cada facilitador pedido conduz.
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

    # O filtro de facilitador vale junto com o recorte, como na lista.
    if facilitator_meeting_ids is not None:
        query = query.in_("id_reuniao", facilitator_meeting_ids)

    # Filtro por setor (super user only — filtra por responsavel_id de participantes do setor)
    setores = parse_csv_param(setor)
    if setores and recorte.reunioes is None:
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

    # Atrasada e Repactuada são calculadas (ADR 0098, decisão 4): cada
    # pendência conta uma vez, na situação que a tela mostra.
    hoje = hoje_em_brasilia()
    repactuados = ids_repactuados(supabase, [r["id_acao"] for r in rows if r.get("id_acao")])
    stats = PendenciaStats()
    for row in rows:
        s = situacao(
            row.get("status", ""),
            as_data(row.get("prazo")),
            hoje,
            repactuada=row.get("id_acao") in repactuados,
        )
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


@router.get("/painel", response_model=PainelDeReunioes)
async def get_painel(
    responsavel_id: str | None = Query(None, description="Responsáveis separados por vírgula"),
    setor: str | None = Query(None, description="Setores separados por vírgula"),
    prazo_de: date | None = Query(None),
    prazo_ate: date | None = Query(None),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """O painel de Reuniões (issue #1868): os cards, as situações e as Atas dos
    cards, da base inteira e no recorte de quem pede. A Secretária não recebe
    dado de Pendência (decisão 53 do diretor no PRD #1757). O gráfico de
    atrasos por setor e o ranking de 90 dias (issue #1871) vão só para o Super
    admin e para quem facilita ao menos uma Reunião."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")
    recorte = await get_recorte_das_pendencias(current_user, supabase)
    super_admin = is_super_admin(me)
    facilita_alguma = False
    if me and not super_admin:
        facilita_alguma = bool(
            supabase.table("reunioes")
            .select("id_reuniao")
            .eq("facilitador_id", me["id"])
            .is_("deleted_at", "null")
            .limit(1)
            .execute()
            .data
        )
    filtros = FiltrosDoPainel(
        responsaveis=frozenset(parse_csv_param(responsavel_id) or ()),
        setores=frozenset(parse_csv_param(setor) or ()),
        prazo_de=prazo_de,
        prazo_ate=prazo_ate,
    )
    return montar_painel(
        supabase,
        recorte,
        hoje=hoje_em_brasilia(),
        agora=painel_reunioes.agora_utc(),
        filtros=filtros,
        com_ranking=painel_reunioes.ve_ranking(me, super_admin=super_admin, facilita_alguma=facilita_alguma),
    )


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
    query = (
        supabase.table("pendencias")
        .select("*")
        .eq("responsavel_id", participante_id)
        .is_("deleted_at", "null")
        .not_.is_("id_reuniao", "null")
    )

    if status:
        query = filtrar_por_status(query, supabase, status)
    if prazo_ate:
        query = query.lte("prazo", str(prazo_ate))

    result = query.order("prazo", desc=False, nullsfirst=False).range(offset, offset + limit - 1).execute()
    return _enrich_ciclo(supabase, _enrich_externo_flag(supabase, result.data or []))


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
    """Lista as pendências do recorte de quem pede (issue #1863): as dele, as das
    reuniões que ele facilita, e todas para o Super admin.

    Retorna header `X-Total-Count` com o total de itens (antes de limit/offset) para
    que a UI consiga sinalizar truncamento e/ou paginação.
    """
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    rows, total = consultar_pendencias(
        supabase,
        recorte=await get_recorte_das_pendencias(current_user, supabase),
        status=status,
        responsaveis=parse_csv_param(responsavel_id),
        id_reuniao=id_reuniao,
        prazo_de=prazo_de,
        prazo_ate=prazo_ate,
        setores=parse_csv_param(setor),
        facilitadores=parse_csv_param(facilitador_id),
        limit=limit,
        offset=offset,
    )
    response.headers["X-Total-Count"] = str(total)
    enriched = _enrich_externo_flag(supabase, rows)
    return _enrich_ciclo(supabase, _enrich_comentarios_count(supabase, enriched))


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

    result = supabase.table("pendencias").select("*").eq("id_acao", id_acao).is_("deleted_at", "null").execute()
    if not result.data or e_lembrete_do_nucleo(result.data[0]):
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    pendencia = result.data[0]

    # O sigilo do Núcleo (issue #1772), antes de tudo e para todo perfil.
    recorte = await get_recorte_das_pendencias(current_user, supabase)
    if pendencia.get("id_reuniao") in recorte.ocultas:
        raise HTTPException(status_code=403, detail=RECUSA_DO_NSP)

    # O recorte pelo vínculo (issue #1863): responsável, co-responsável,
    # Facilitador da reunião ou Super admin. Fora dele, 404.
    if not recorte.ve(pendencia):
        raise HTTPException(status_code=404, detail="Pendência não encontrada")

    return _enrich_ciclo(supabase, _enrich_externo_flag(supabase, [pendencia]))[0]


# ─── Ciclo de vida (ADR 0098, decisões 4 e 5; issue #1862) ──────────────────
# A única porta da API que muda estado e prazo da Pendência é `POST /{id}/acoes`,
# sempre com anotação, pelo comando de ação de `pendencia_acao` (a regra pura
# de `pendencia_ciclo` e a gravação de `registrar_acao_da_pendencia`, que
# atualiza a Pendência e insere o evento no histórico juntos). A conclusão com
# anexo (`POST /{id}/conclusao`, issue #1865) passa pela mesma regra.

_HTTP_DA_RECUSA = {"permissao": 403, "transicao": 409, "dados": 422}


def _enrich_ciclo(supabase, rows: list[dict]) -> list[dict]:
    """Atrasada, Repactuada e a situação que a tela mostra, calculadas."""
    hoje = hoje_em_brasilia()
    repactuados = ids_repactuados(supabase, [r["id_acao"] for r in rows if r.get("id_acao")])
    for r in rows:
        prazo = as_data(r.get("prazo"))
        r["repactuada"] = r.get("id_acao") in repactuados
        r["situacao"] = situacao(r.get("status", ""), prazo, hoje, repactuada=r["repactuada"])
        r["atrasada"] = r["situacao"] == "ATRASADO"
    return rows


async def _pendencia_e_papeis(
    id_acao: str, current_user: dict, supabase
) -> tuple[dict, dict | None, set[Papel], dict[str, bool]]:
    """A Pendência que quem pede enxerga, os papéis dele nela e o momento dela
    (a Ata em assinatura e a Contestação aberta, issue #1870). Mesmo portão do
    GET: secretária 403, Núcleo oculto 403, fora do recorte 404."""
    pendencia, me, recorte = await _pendencia_sem_recorte(id_acao, current_user, supabase)

    # O recorte pelo vínculo (issue #1863), como no GET: responsável,
    # co-responsável, Facilitador da reunião ou Super admin. Fora dele, 404.
    if not recorte.ve(pendencia):
        raise HTTPException(status_code=404, detail="Pendência não encontrada")
    reuniao = _reuniao_da(pendencia, supabase)
    momento = {
        "ata_em_assinatura": reuniao.get("status_ata") == "AGUARDANDO_ASSINATURA",
        "contestada": id_acao in contestacoes_abertas(supabase, [id_acao]),
    }
    return pendencia, me, _papeis(pendencia, me, supabase, reuniao), momento


async def _pendencia_sem_recorte(id_acao: str, current_user: dict, supabase):
    """A Pendência, o participante e o recorte: secretária 403, inexistente
    404, Núcleo oculto 403. Quem chama decide o que fazer com o recorte."""
    me = await get_participante_for_user(current_user, supabase)
    if is_secretaria(me):
        raise HTTPException(status_code=403, detail="Secretária não tem acesso a pendências")

    result = supabase.table("pendencias").select("*").eq("id_acao", id_acao).is_("deleted_at", "null").execute()
    if not result.data or e_lembrete_do_nucleo(result.data[0]):
        raise HTTPException(status_code=404, detail="Pendência não encontrada")
    pendencia = result.data[0]

    # O sigilo do Núcleo (issue #1772), como no GET: antes de tudo e para todo perfil.
    recorte = await get_recorte_das_pendencias(current_user, supabase)
    if pendencia.get("id_reuniao") in recorte.ocultas:
        raise HTTPException(status_code=403, detail=RECUSA_DO_NSP)
    return pendencia, me, recorte


def _reuniao_da(pendencia: dict, supabase) -> dict:
    """O Facilitador e o estado da Ata da Reunião da Pendência."""
    return (
        supabase.table("reunioes")
        .select("facilitador_id, status_ata")
        .eq("id_reuniao", pendencia["id_reuniao"])
        .execute()
        .data
        or [{}]
    )[0]


def _papeis(pendencia: dict, me: dict | None, supabase, reuniao: dict | None = None) -> set[Papel]:
    """Os papéis de quem pede na Pendência, pelo vínculo."""
    my_id = me.get("id") if me else None
    papeis: set[Papel] = set()
    if is_super_admin(me):
        papeis.add(Papel.SUPER_ADMIN)
    if my_id is not None:
        if pendencia.get("responsavel_id") == my_id:
            papeis.add(Papel.RESPONSAVEL)
        if pendencia.get("co_responsavel_id") == my_id:
            papeis.add(Papel.CO_RESPONSAVEL)
        if (reuniao if reuniao is not None else _reuniao_da(pendencia, supabase)).get("facilitador_id") == my_id:
            papeis.add(Papel.FACILITADOR)
    return papeis


@router.post("/{id_acao}/acoes", response_model=PendenciaResponse)
async def agir_na_pendencia(
    id_acao: str,
    body: AcaoPendenciaRequest,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Iniciar, anotar, concluir, repactuar, cancelar, reabrir, contestar,
    ajustar ou recusar, sempre com anotação."""
    pendencia, me, papeis, momento = await _pendencia_e_papeis(id_acao, current_user, supabase)
    try:
        mudanca = agir(
            supabase,
            pendencia,
            Comando(body.comando),
            papeis,
            anotacao=body.anotacao,
            autor_id=me.get("id") if me else None,
            autor_nome=(me or {}).get("nome_completo") or current_user.get("email") or "Sem nome",
            hoje=hoje_em_brasilia(),
            prazo_novo=body.prazo,
            responsavel_novo=body.responsavel_id,
            **momento,
        )
    except AcaoRecusada as recusa:
        raise HTTPException(status_code=_HTTP_DA_RECUSA[recusa.tipo], detail=recusa.motivo) from recusa
    except APIError as erro:
        if erro.code == "PT409":
            raise HTTPException(status_code=409, detail=erro.message) from erro
        if erro.code == "PT404":
            raise HTTPException(status_code=404, detail="Pendência não encontrada") from erro
        raise

    logger.info(f"[Pendencias] {id_acao}: {body.comando} ({pendencia['status']} -> {mudanca.status})")
    return _pendencia_atualizada(supabase, id_acao)


def _decidir(comando: Comando, papeis: set[Papel], pendencia: dict, anotacao: str | None, prazo_novo=None):
    try:
        return decidir(
            comando,
            papeis,
            status=pendencia["status"],
            prazo=as_data(pendencia.get("prazo")),
            hoje=hoje_em_brasilia(),
            anotacao=anotacao,
            prazo_novo=prazo_novo,
        )
    except AcaoRecusada as recusa:
        raise HTTPException(status_code=_HTTP_DA_RECUSA[recusa.tipo], detail=recusa.motivo) from recusa


def _parametros(id_acao: str, anotacao: str, me: dict | None, current_user: dict, pendencia: dict, mudanca) -> dict:
    """Os parâmetros comuns às duas funções de gravação do Postgres."""
    return {
        "p_id_acao": id_acao,
        "p_anotacao": anotacao,
        "p_autor_id": me.get("id") if me else None,
        "p_autor_nome": (me or {}).get("nome_completo") or current_user.get("email") or "Sem nome",
        "p_status_esperado": pendencia["status"],
        "p_status_novo": mudanca.status,
        "p_concluida": mudanca.concluida,
        "p_conta_atraso": mudanca.conta_atraso,
    }


def _gravar(supabase, funcao: str, params: dict) -> None:
    try:
        supabase.rpc(funcao, params).execute()
    except APIError as erro:
        if erro.code == "PT409":
            raise HTTPException(status_code=409, detail=erro.message) from erro
        if erro.code == "PT404":
            raise HTTPException(status_code=404, detail="Pendência não encontrada") from erro
        raise


def _pendencia_atualizada(supabase, id_acao: str) -> dict:
    atualizada = supabase.table("pendencias").select("*").eq("id_acao", id_acao).execute()
    return _enrich_ciclo(supabase, _enrich_externo_flag(supabase, atualizada.data or []))[0]


# ─── Anexo da conclusão (issue #1865) ───────────────────────────────────────
# Concluir com a anotação obrigatória e, se vier, uma foto ou um PDF de até
# 10 MB. Toda recusa (regra do ciclo, tipo, tamanho) vem antes do bucket; o
# binário sobe antes da gravação e sai se a conclusão não entrar. A conclusão
# e o anexo entram juntos pela `registrar_conclusao_com_anexo` (migration 174).


@router.post("/{id_acao}/conclusao", response_model=PendenciaResponse)
async def concluir_a_pendencia(
    id_acao: str,
    anotacao: str = Form("", max_length=5000),
    arquivo: UploadFile | None = File(None),
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Concluir com anotação e, se quiser, uma foto ou um PDF."""
    anotacao = anotacao.strip()
    pendencia, me, papeis, _momento = await _pendencia_e_papeis(id_acao, current_user, supabase)
    mudanca = _decidir(Comando.CONCLUIR, papeis, pendencia, anotacao)
    params = _parametros(id_acao, anotacao, me, current_user, pendencia, mudanca)

    if arquivo is None or not arquivo.filename:
        _gravar(supabase, "registrar_acao_da_pendencia", {**params, "p_comando": "concluir", "p_prazo_novo": None})
        return _pendencia_atualizada(supabase, id_acao)

    conteudo = await arquivo.read(pendencia_anexo.LIMITE_BYTES + 1)
    try:
        extensao, content_type = pendencia_anexo.conferir(arquivo.filename, conteudo)
        path = pendencia_anexo.guardar(
            supabase, id_acao=id_acao, extensao=extensao, conteudo=conteudo, content_type=content_type
        )
    except pendencia_anexo.AnexoRecusado as recusa:
        raise HTTPException(status_code=recusa.status_code, detail=recusa.motivo) from recusa

    try:
        _gravar(
            supabase,
            "registrar_conclusao_com_anexo",
            {
                **params,
                "p_storage_path": path,
                "p_nome_original": arquivo.filename,
                "p_content_type": content_type,
                "p_tamanho_bytes": len(conteudo),
            },
        )
    except BaseException:
        # Sem a linha, o binário é órfão que ninguém alcança: sai agora.
        pendencia_anexo.descartar(supabase, path)
        raise
    logger.info(f"[Pendencias] {id_acao}: concluir com anexo ({pendencia['status']} -> {mudanca.status})")
    return _pendencia_atualizada(supabase, id_acao)


@router.get("/{id_acao}/anexos/{anexo_id}/link", response_model=LinkDoAnexoResponse)
async def link_do_anexo(
    id_acao: str,
    anexo_id: int,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """Link assinado de poucos minutos, só para o responsável, o Facilitador da
    Reunião e o Super admin. Quem está fora dos três recebe 403, inclusive quem
    vê a Pendência por outro vínculo (co-responsável, membro do Núcleo)."""
    pendencia, me, _recorte = await _pendencia_sem_recorte(id_acao, current_user, supabase)
    if not pendencia_anexo.pode_abrir(_papeis(pendencia, me, supabase)):
        raise HTTPException(status_code=403, detail=pendencia_anexo.RECUSA_DO_LINK)
    linhas = (
        supabase.table("pendencia_anexos").select("*").eq("id", anexo_id).eq("id_acao", id_acao).execute().data or []
    )
    if not linhas:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    url = pendencia_anexo.link(supabase, linhas[0]["storage_path"])
    if not url:
        raise HTTPException(status_code=503, detail="Não foi possível abrir o anexo agora. Tente de novo em instantes.")
    return {"url": url}


@router.get("/{id_acao}/historico", response_model=HistoricoPendenciaResponse)
async def historico_da_pendencia(
    id_acao: str,
    current_user: dict = Depends(get_current_user),
    supabase=Depends(get_supabase_client),
):
    """O histórico em ordem e as ações que quem olha pode fazer agora."""
    pendencia, _me, papeis, momento = await _pendencia_e_papeis(id_acao, current_user, supabase)
    eventos = (
        supabase.table("pendencia_historico").select("*").eq("id_acao", id_acao).order("criado_em").execute().data or []
    )
    eventos.sort(key=lambda e: (e.get("criado_em") or "", e.get("id") or 0))
    anexos = supabase.table("pendencia_anexos").select("*").eq("id_acao", id_acao).execute().data or []
    por_evento = {a["evento_id"]: a for a in anexos}
    for evento in eventos:
        anexo = por_evento.get(evento.get("id"))
        if anexo:
            evento["anexo"] = {
                "id": anexo["id"],
                "nome": anexo.get("nome_original") or "",
                "tipo": anexo.get("content_type") or "",
                "tamanho_bytes": anexo.get("tamanho_bytes") or 0,
            }
    return {
        "eventos": eventos,
        "acoes_permitidas": [c.value for c in acoes_disponiveis(papeis, pendencia["status"], **momento)],
        "pode_abrir_anexos": pendencia_anexo.pode_abrir(papeis),
    }
