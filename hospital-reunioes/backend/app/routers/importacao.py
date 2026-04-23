"""
Router para importação de ATAs antigas (migradas do sistema legado).

Fluxo em 3 endpoints:
  1. POST /reunioes/importacao/preparar    — parseia PDF + IA + matcher, retorna preview stateless
  2. POST /reunioes/importacao/confirmar   — persiste reunião MIGRADA + externos + pendências
  3. GET  /reunioes/importacao/check-duplicata — consulta dedup por hash ou documento_id

Todos os endpoints exigem super admin (require_super_admin).
Reuniões criadas aqui nascem com status_ata='MIGRADA' e fonte='IMPORTACAO_LEGADA'.
Não passam pelo pipeline normal (sem ClickSign, sem PDF gerado pelo WeasyPrint).
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import ValidationError

from app.config import settings
from app.dependencies import get_supabase_client, require_super_admin
from app.models.schemas import (
    AtaMigradaPreview,
    CheckDuplicataResponse,
    ConfirmarImportacaoRequest,
    ConfirmarImportacaoResponse,
    HistoricoImportacaoItem,
    MetadadosImportacao,
    ParticipanteExternoPreview,
    ParticipanteMatchedPreview,
    PendenciaIgnorada,
    PendenciaImportacao,
    StatusPendencia,
    TipoReuniao,
)
from app.services import pdf_parser_ata_migrada as pdf_parser
from app.services.ai_processor import process_ata_migrada
from app.services.importacao_service import (
    ImportacaoServiceError,
    build_confirmacao_payload,
    check_duplicata,
    format_participantes_ativos,
    generate_reuniao_id,
    provision_externos,
)
from app.services.participant_matcher import _normalize as _normalize_nome
from app.services.participant_matcher import match_participants, match_single_name
from app.services.storage import upload_file

router = APIRouter(prefix="/reunioes/importacao", tags=["importacao"])
logger = logging.getLogger(__name__)


MAX_FILE_BYTES = 15 * 1024 * 1024  # 15 MB
MIN_TEXTO_BYTES = 200  # abaixo disso, presume PDF escaneado/vazio


# ---------------------------------------------------------------------------
# GET /check-duplicata
# ---------------------------------------------------------------------------


@router.get("/check-duplicata", response_model=CheckDuplicataResponse)
async def check_duplicata_endpoint(
    documento_id: str | None = Query(None),
    arquivo_hash: str | None = Query(None),
    _me: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Consulta se uma ATA já foi importada. Chamado pelo frontend antes do upload completo."""
    if not documento_id and not arquivo_hash:
        raise HTTPException(422, "Informe documento_id ou arquivo_hash")
    dup = check_duplicata(supabase, arquivo_hash, documento_id)
    if not dup:
        return CheckDuplicataResponse(duplicada=False)
    return CheckDuplicataResponse(
        duplicada=True,
        id_reuniao=dup.get("id_reuniao"),
        titulo=dup.get("titulo"),
        data=dup.get("data"),
        motivo=dup.get("motivo"),
    )


# ---------------------------------------------------------------------------
# POST /preparar
# ---------------------------------------------------------------------------


@router.post("/preparar", response_model=AtaMigradaPreview)
async def preparar_importacao(
    file: UploadFile = File(...),
    _me: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Parseia PDF, chama IA e matcher, retorna preview (stateless — não persiste)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(422, "Somente arquivos PDF são aceitos")

    arquivo_bytes = await file.read()
    if len(arquivo_bytes) == 0:
        raise HTTPException(422, "Arquivo vazio")
    if len(arquivo_bytes) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Arquivo excede o limite de {MAX_FILE_BYTES // (1024 * 1024)} MB")

    # 1. Hash + parse PDF
    arquivo_hash = pdf_parser.calcular_hash(arquivo_bytes)

    try:
        estrutura = pdf_parser.extrair_estrutura(arquivo_bytes)
    except Exception as e:
        logger.error(f"[importacao] Erro ao parsear PDF '{file.filename}': {e}")
        raise HTTPException(400, f"Não foi possível parsear o PDF: {e}")

    texto_len = len(estrutura.get("texto_completo") or "")
    if texto_len < MIN_TEXTO_BYTES:
        raise HTTPException(
            400,
            "PDF parece escaneado ou vazio (pouco texto extraível). Envie uma versão com texto nativo.",
        )

    documento_id = estrutura.get("documento_id_origem")

    # 2. Dedup check
    dup = check_duplicata(supabase, arquivo_hash, documento_id)
    if dup:
        raise HTTPException(
            status_code=409,
            detail={
                "erro": "ATA já importada",
                "id_reuniao_existente": dup["id_reuniao"],
                "titulo": dup.get("titulo"),
                "data": str(dup.get("data")) if dup.get("data") else None,
                "motivo": dup["motivo"],
            },
        )

    # 3. Diretório de participantes ativos para contexto da IA
    part_result = supabase.table("participantes").select("id, nome_completo, cargo, setor").eq("ativo", True).execute()
    participantes_ativos = part_result.data or []
    participantes_dir = format_participantes_ativos(participantes_ativos)

    # 4. IA — normaliza e retorna JSON tipado
    ia_result = process_ata_migrada(estrutura, participantes_ativos_dir=participantes_dir)
    if "error" in ia_result:
        logger.error(f"[importacao] IA falhou para {file.filename}: {ia_result['error']}")
        raise HTTPException(502, f"Erro na IA: {ia_result['error']}")

    # 5. Matcher (sem criar vínculos — reunião ainda não existe)
    participantes_json = ia_result.get("participantes", []) or []
    matched_ids, nao_reconhecidos = match_participants(
        supabase,
        id_reuniao="__preview__",
        participantes_json=participantes_json,
        link_on_match=False,
    )

    # 6. Monta matched_previews (enriquece com dados do banco)
    part_map = {p["id"]: p for p in participantes_ativos}
    matched_previews: list[ParticipanteMatchedPreview] = [
        ParticipanteMatchedPreview(
            nome=part_map[pid]["nome_completo"],
            participante_id=pid,
            cargo=part_map[pid].get("cargo"),
        )
        for pid in matched_ids
        if pid in part_map
    ]

    # 7. Externos (IA não reconheceu)
    externos: list[ParticipanteExternoPreview] = [
        ParticipanteExternoPreview(
            nome=nr["nome"],
            cargo=nr.get("cargo") or "",
            setor=nr.get("setor"),
            email=None,
        )
        for nr in nao_reconhecidos
    ]

    # 8. Resolução responsável → matched_id ou externo_idx por nome normalizado
    matched_by_norm: dict[str, str] = {_normalize_nome(p.nome): p.participante_id for p in matched_previews}
    externo_by_norm: dict[str, int] = {_normalize_nome(e.nome): idx for idx, e in enumerate(externos)}
    # Rows dos participantes que casaram como presentes na reunião. A IA costuma
    # citar o responsável da ação de forma abreviada ("Gisele Nunes" em vez de
    # "Gisele Nunes de Vasconcellos") — aqui reaplicamos a cascata do matcher
    # restrita ao conjunto de participantes já identificados, para não atribuir
    # uma ação a alguém que nem esteve presente.
    matched_rows = [part_map[pid] for pid in matched_ids if pid in part_map]

    pendencias_preview: list[PendenciaImportacao] = []
    for q in ia_result.get("quadro_atribuicoes") or []:
        nome_resp = (q.get("responsavel") or "").strip()
        nome_norm = _normalize_nome(nome_resp) if nome_resp else ""
        # Ordem de resolução (prioridade):
        #   1. Match exato normalizado em matched_by_norm (interno já identificado)
        #   2. Match exato normalizado em externo_by_norm (externo detectado pela IA)
        #      — preferimos NÃO deixar fuzzy roubar um nome externo para um
        #      primeiro-nome de interno homônimo.
        #   3. Fuzzy/primeiro-nome via match_single_name (matched_rows).
        # Se nada resolver, o /confirmar cria stub externo com o nome cru.
        resp_id = matched_by_norm.get(nome_norm)
        externo_idx: int | None = None
        if not resp_id:
            externo_idx = externo_by_norm.get(nome_norm)
        if not resp_id and externo_idx is None and nome_resp:
            resp_id = match_single_name(
                nome_resp,
                matched_rows,
                cargo_ia=(q.get("cargo") or ""),
            )

        prazo_iso = q.get("prazo")
        # Se IA retornou null, campo date do Pydantic aceita None
        prazo_date = None
        if prazo_iso:
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(prazo_iso))
            if m:
                from datetime import date as _date

                prazo_date = _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))

        status_raw = (q.get("status") or "PENDENTE").upper()
        if status_raw == "CONCLUÍDO":
            status_raw = "CONCLUIDO"
        try:
            status_enum = StatusPendencia(status_raw)
        except ValueError:
            status_enum = StatusPendencia.PENDENTE

        pendencias_preview.append(
            PendenciaImportacao(
                acao=q.get("acao") or "",
                responsavel_nome=nome_resp,
                responsavel_id=resp_id,
                responsavel_externo_idx=externo_idx,
                cargo=q.get("cargo"),
                prazo=prazo_date,
                prazo_original=q.get("prazo_original"),
                meta_entregavel=q.get("entregavel"),
                status=status_enum,
                co_responsavel_id=None,
            )
        )

    # 9. Metadados — converte data ISO para date, mapeia tipo pro enum
    data_str = ia_result.get("data") or (estrutura.get("metadados_brutos") or {}).get("data")
    from datetime import date as _date
    from datetime import datetime as _dt

    if data_str:
        try:
            data_obj = _dt.strptime(data_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            data_obj = _dt.today().date()
    else:
        data_obj = _dt.today().date()

    tipo_raw = ia_result.get("tipo") or "Coordenação"
    try:
        tipo_enum = TipoReuniao(tipo_raw)
    except ValueError:
        tipo_enum = TipoReuniao.COORDENACAO

    titulo = (ia_result.get("titulo") or "").strip()
    if not titulo:
        titulo = (estrutura.get("metadados_brutos") or {}).get("titulo_ata") or "ATA migrada"

    metadados = MetadadosImportacao(
        titulo=titulo[:255],
        tipo=tipo_enum,
        data=data_obj,
        hora_inicio=ia_result.get("hora_inicio"),
        hora_fim=ia_result.get("hora_fim"),
        facilitador_id=None,
        assunto=(ia_result.get("assunto") or None),
        objetivo=(ia_result.get("objetivo") or None),
    )

    logger.info(
        f"[importacao] Preview pronto: {file.filename} | "
        f"matched={len(matched_previews)} externos={len(externos)} "
        f"pendencias={len(pendencias_preview)}"
    )

    return AtaMigradaPreview(
        arquivo_hash=arquivo_hash,
        documento_id_origem=documento_id,
        nome_arquivo_original=file.filename,
        metadados=metadados,
        participantes_matched=matched_previews,
        participantes_externos=externos,
        pendencias=pendencias_preview,
        registro_narrativo=ia_result.get("registro_narrativo"),
        resumo_executivo=ia_result.get("resumo_executivo"),
        paginas=estrutura.get("paginas", 0),
        is_mock=bool(ia_result.get("_mock")),
    )


# ---------------------------------------------------------------------------
# POST /confirmar
# ---------------------------------------------------------------------------


@router.post("/confirmar", response_model=ConfirmarImportacaoResponse)
async def confirmar_importacao(
    file: UploadFile = File(...),
    payload: str = Form(...),
    me: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """
    Persiste a ATA migrada. Recebe o PDF re-uploadado + JSON editado no preview.
    Cria em transação logical: reuniao MIGRADA + externos + participantes + pendências.
    """
    # 1. Parse payload
    try:
        req = ConfirmarImportacaoRequest.model_validate_json(payload)
    except ValidationError as e:
        raise HTTPException(422, f"Payload inválido: {e}")

    # 2. Validate file
    arquivo_bytes = await file.read()
    if len(arquivo_bytes) == 0:
        raise HTTPException(422, "Arquivo vazio")
    if len(arquivo_bytes) > MAX_FILE_BYTES:
        raise HTTPException(413, f"Arquivo excede {MAX_FILE_BYTES // (1024 * 1024)} MB")

    # Hash must match preview
    hash_atual = pdf_parser.calcular_hash(arquivo_bytes)
    if hash_atual != req.arquivo_hash:
        raise HTTPException(
            400,
            "Hash do arquivo diverge do preview — o arquivo foi alterado. Refaça o /preparar.",
        )

    # 3. Re-dedup (defesa em profundidade)
    dup = check_duplicata(supabase, req.arquivo_hash, req.documento_id_origem)
    if dup:
        raise HTTPException(
            status_code=409,
            detail={
                "erro": "ATA já importada",
                "id_reuniao_existente": dup["id_reuniao"],
                "titulo": dup.get("titulo"),
                "data": str(dup.get("data")) if dup.get("data") else None,
                "motivo": dup["motivo"],
            },
        )

    # 4. Gerar id_reuniao (externos sem email são ignorados silenciosamente abaixo)
    id_reuniao = generate_reuniao_id(req.metadados.data)

    # 5. Upload PDF para Storage (bucket de transcrições, prefixo migradas/)
    #    Roda ANTES da RPC atômica: se falhar, apenas seguimos sem URL.
    #    Storage não participa da transação DB.
    storage_path = f"migradas/{id_reuniao}.pdf"
    url_pdf = upload_file(
        supabase,
        bucket=settings.supabase_storage_bucket_transcricoes,
        path=storage_path,
        content=arquivo_bytes,
        content_type="application/pdf",
    )
    if not url_pdf:
        logger.warning(f"[importacao] Upload do PDF falhou para {id_reuniao}, continuando sem URL")

    # 6. Facilitador: usa o do request OU o próprio super admin
    facilitador_id = req.metadados.facilitador_id or me.get("id")

    # 7. Provisionar externos e montar payloads via service compartilhado.
    externo_idx_to_id, total_externos_criados, total_externos_stub = provision_externos(
        supabase, req.participantes_externos
    )

    # 8-10. Montar payloads (reunião + pendências + vínculos) via service.
    #       Stubs fallback (responsáveis não resolvidos) preenchem o cache.
    stub_fallback_cache: dict[str, str] = {}
    try:
        (
            reuniao_payload,
            pendencias_payload,
            externos_links_payload,
            pendencias_ignoradas,
        ) = build_confirmacao_payload(
            supabase,
            req=req,
            id_reuniao=id_reuniao,
            facilitador_id=facilitador_id,
            importador_id=me.get("id"),
            url_pdf=url_pdf,
            externo_idx_to_id=externo_idx_to_id,
            stub_fallback_cache=stub_fallback_cache,
        )
    except ImportacaoServiceError as exc:
        raise HTTPException(exc.status_code, str(exc))

    # 11. RPC atômica: reunião + pendências + vínculos + total_acoes em UMA transação.
    #     Qualquer falha → Postgres desfaz tudo (sem reunião órfã / hash órfão).
    try:
        rpc_result = supabase.rpc(
            "confirmar_importacao_atomico",
            {
                "p_reuniao": reuniao_payload,
                "p_pendencias": pendencias_payload,
                "p_externos_links": externos_links_payload,
            },
        ).execute()
    except Exception as exc:
        logger.exception(f"[importacao.confirmar] RPC atômica falhou para {id_reuniao}")
        raise HTTPException(500, f"Falha atômica ao confirmar importação: {exc}")

    if not rpc_result.data:
        raise HTTPException(500, "RPC confirmar_importacao_atomico não retornou resultado")

    confirmacao = rpc_result.data[0]
    pendencias_count = int(confirmacao.get("pendencias_count") or 0)

    # Stubs fallback (criados automaticamente a partir do nome da IA quando o
    # responsável da pendência não resolveu) contam como stubs sem email para
    # o usuário, mas são distintos dos stubs do preview. Cache pode incluir
    # reuso de stubs pré-existentes — idealmente contaríamos só os novos, mas
    # o custo de separar aqui é maior que o benefício.
    total_externos_stub_fallback = len(stub_fallback_cache)
    total_stubs_final = total_externos_stub + total_externos_stub_fallback

    logger.info(
        f"[importacao] ATA migrada importada (atomica): {id_reuniao} | "
        f"{pendencias_count} pendências | "
        f"{total_externos_criados} externos novos | "
        f"{total_externos_stub} stubs sem email | "
        f"{total_externos_stub_fallback} stubs fallback (responsáveis não resolvidos) | "
        f"{len(pendencias_ignoradas)} pendências ignoradas"
    )

    return ConfirmarImportacaoResponse(
        id_reuniao=id_reuniao,
        total_pendencias=pendencias_count,
        total_externos_criados=total_externos_criados,
        total_externos_stub=total_stubs_final,
        pendencias_ignoradas=[PendenciaIgnorada(**p) for p in pendencias_ignoradas],
        url_pdf=url_pdf,
    )


# ---------------------------------------------------------------------------
# GET /historico
# ---------------------------------------------------------------------------


@router.get("/historico", response_model=list[HistoricoImportacaoItem])
async def listar_historico_importacao(
    limit: int = Query(20, ge=1, le=100),
    _me: dict = Depends(require_super_admin),
    supabase=Depends(get_supabase_client),
):
    """Retorna as últimas ATAs importadas (status_ata='MIGRADA'), mais recentes primeiro.

    Fonte única de verdade: reunioes. Rota serve a UI da página /reunioes/importar
    para exibir um histórico persistente que não depende do state em memória.
    """
    res = (
        supabase.table("reunioes")
        .select(
            "id_reuniao,titulo,data,documento_id_origem,nome_arquivo_original,total_acoes,importado_por_id,created_at"
        )
        .eq("status_ata", "MIGRADA")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows = res.data or []

    # Enriquecer com nome do importador (lookup em batch)
    ids = {r["importado_por_id"] for r in rows if r.get("importado_por_id")}
    nomes_por_id: dict[str, str] = {}
    if ids:
        part_res = supabase.table("participantes").select("id,nome_completo").in_("id", list(ids)).execute()
        nomes_por_id = {p["id"]: p["nome_completo"] for p in (part_res.data or [])}

    return [
        HistoricoImportacaoItem(
            id_reuniao=r["id_reuniao"],
            titulo=r.get("titulo"),
            data=r.get("data"),
            documento_id_origem=r.get("documento_id_origem"),
            nome_arquivo_original=r.get("nome_arquivo_original"),
            total_pendencias=r.get("total_acoes") or 0,
            importado_por_id=r.get("importado_por_id"),
            importado_por_nome=nomes_por_id.get(r.get("importado_por_id")) if r.get("importado_por_id") else None,
            importado_em=r.get("created_at"),
        )
        for r in rows
    ]
