"""
Bulk import de ATAs migradas em massa.

Dois modos de operação:

    # 1) Extração (sem tocar no banco para persistência; lê participantes ativos)
    uv run python -m scripts.bulk_import_atas dry-run \
        --dir ../atas-migracao/ \
        --out ../atas-migracao-preview.json

    # 2) Persistência (lê JSON possivelmente editado e insere via RPC atômica)
    uv run python -m scripts.bulk_import_atas apply \
        --in ../atas-migracao-preview.json \
        --importador-id P001

Reusa 100% do pipeline de importação: `pdf_parser_ata_migrada`,
`ai_processor.process_ata_migrada`, `participant_matcher.match_single_name_scored`
e a RPC `confirmar_importacao_atomico` (migration 024).

O JSON gerado no dry-run é editável manualmente antes do apply — threshold de
match (default 80 auto / 60 sugestão) permite confirmar sugestões ou forçar
externo trocando o campo `resolucao`.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date as _date
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import settings
from app.models.schemas import (
    ConfirmarImportacaoRequest,
    MetadadosImportacao,
    ParticipanteExternoPreview,
    ParticipanteMatchedPreview,
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
from app.services.participant_matcher import (
    DEFAULT_AUTO_THRESHOLD,
    MatchResult,
    match_single_name_scored,
)
from app.services.storage import upload_file
from supabase import create_client

logging.basicConfig(
    level=logging.INFO,
    format="[bulk_import_atas] %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_REVIEW_THRESHOLD = 60

RESOLUCAO_AUTO = "auto_match"
RESOLUCAO_SUGESTAO = "sugestao_pendente"
RESOLUCAO_EXTERNO = "externo_automatico"


# ---------------------------------------------------------------------------
# Helpers compartilhados entre dry-run e apply
# ---------------------------------------------------------------------------


def _make_supabase():
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


def _serialize_match(result: MatchResult) -> dict[str, Any]:
    return {
        "participante_id": result.participante_id,
        "score": result.score,
        "strategy": result.strategy,
        "candidates_ambiguos": result.candidates_ambiguos,
    }


def _classify(
    result: MatchResult,
    auto_threshold: int,
    review_threshold: int,
) -> str:
    """Decide resolucao com base em score e threshold."""
    if result.participante_id and result.score >= auto_threshold:
        return RESOLUCAO_AUTO
    if result.participante_id and result.score >= review_threshold:
        return RESOLUCAO_SUGESTAO
    return RESOLUCAO_EXTERNO


# ---------------------------------------------------------------------------
# DRY-RUN — lê PDFs e gera JSON
# ---------------------------------------------------------------------------


def _process_one_pdf(
    pdf_path: Path,
    supabase,
    ativos_rows: list[dict],
    participantes_dir: str,
    auto_threshold: int,
    review_threshold: int,
) -> dict[str, Any]:
    """Gera item do JSON para um PDF. Retorna dict com status 'pronto' |
    'duplicado' | 'erro_extracao'."""
    try:
        arquivo_bytes = pdf_path.read_bytes()
    except Exception as exc:
        return {
            "arquivo": str(pdf_path),
            "arquivo_hash": None,
            "status": "erro_extracao",
            "erro": f"Falha ao ler arquivo: {exc}",
        }

    arquivo_hash = pdf_parser.calcular_hash(arquivo_bytes)

    # Parse PDF (se falhar marca erro)
    try:
        estrutura = pdf_parser.extrair_estrutura(arquivo_bytes)
    except Exception as exc:
        return {
            "arquivo": str(pdf_path),
            "arquivo_hash": arquivo_hash,
            "status": "erro_extracao",
            "erro": f"Falha no parser do PDF: {exc}",
        }

    documento_id = estrutura.get("documento_id_origem")

    # Dedup check — economiza tokens
    dup = check_duplicata(supabase, arquivo_hash, documento_id)
    if dup:
        return {
            "arquivo": str(pdf_path),
            "arquivo_hash": arquivo_hash,
            "documento_id_origem": documento_id,
            "status": "duplicado",
            "duplicado_de": dup.get("id_reuniao"),
            "titulo_existente": dup.get("titulo"),
            "motivo_duplicata": dup.get("motivo"),
        }

    texto_len = len(estrutura.get("texto_completo") or "")
    if texto_len < 200:
        return {
            "arquivo": str(pdf_path),
            "arquivo_hash": arquivo_hash,
            "status": "erro_extracao",
            "erro": "PDF com pouco texto (escaneado ou vazio)",
        }

    # IA
    ia_result = process_ata_migrada(estrutura, participantes_ativos_dir=participantes_dir)
    if "error" in ia_result:
        return {
            "arquivo": str(pdf_path),
            "arquivo_hash": arquivo_hash,
            "status": "erro_extracao",
            "erro": f"IA falhou: {ia_result['error']}",
        }

    # Participantes — aplica cascata com score
    part_map = {p["id"]: p for p in ativos_rows}
    participantes_serializados: list[dict[str, Any]] = []
    for p in (ia_result.get("participantes") or []):
        nome_ia = (p.get("nome") or "").strip()
        if not nome_ia:
            continue
        cargo_ia = p.get("cargo") or ""
        setor_ia = p.get("setor") or ""
        result = match_single_name_scored(
            nome_ia, ativos_rows, cargo_ia=cargo_ia, setor_ia=setor_ia
        )
        resolucao = _classify(result, auto_threshold, review_threshold)
        entry: dict[str, Any] = {
            "nome_ia": nome_ia,
            "cargo_ia": cargo_ia,
            "setor_ia": setor_ia,
            "resolucao": resolucao,
            **_serialize_match(result),
        }
        if resolucao == RESOLUCAO_AUTO:
            pid = result.participante_id
            if pid in part_map:
                entry["nome_cadastrado"] = part_map[pid]["nome_completo"]
        elif resolucao == RESOLUCAO_SUGESTAO:
            entry["sugestao_participante_id"] = result.participante_id
            entry["fallback_se_nao_confirmado"] = "externo"
            entry["participante_id"] = None  # cleiton forçar revisão manual
        else:  # externo_automatico
            entry["participante_id"] = None
        participantes_serializados.append(entry)

    # Restringe o matching de responsáveis aos participantes que efetivamente
    # foram resolvidos como presentes na reunião (invariante: responsável de
    # uma ação precisa ter estado lá).
    matched_auto_rows = [
        part_map[entry["participante_id"]]
        for entry in participantes_serializados
        if entry["resolucao"] == RESOLUCAO_AUTO
        and entry["participante_id"]
        and entry["participante_id"] in part_map
    ]

    # Pendências
    pendencias_serializadas: list[dict[str, Any]] = []
    for q in (ia_result.get("quadro_atribuicoes") or []):
        nome_resp = (q.get("responsavel") or "").strip()
        prazo_iso = q.get("prazo")
        prazo_str = None
        if prazo_iso:
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(prazo_iso))
            if m:
                prazo_str = str(prazo_iso)

        resp_resolucao = RESOLUCAO_EXTERNO
        resp_result = MatchResult()
        if nome_resp and matched_auto_rows:
            resp_result = match_single_name_scored(
                nome_resp,
                matched_auto_rows,
                cargo_ia=(q.get("cargo") or ""),
            )
            resp_resolucao = _classify(resp_result, auto_threshold, review_threshold)

        status_raw = (q.get("status") or "PENDENTE").upper()
        if status_raw == "CONCLUÍDO":
            status_raw = "CONCLUIDO"

        entry = {
            "acao": q.get("acao") or "",
            "responsavel_nome_ia": nome_resp,
            "responsavel_resolucao": resp_resolucao,
            "responsavel_id": resp_result.participante_id
                if resp_resolucao == RESOLUCAO_AUTO
                else None,
            "responsavel_sugestao_id": resp_result.participante_id
                if resp_resolucao == RESOLUCAO_SUGESTAO
                else None,
            "responsavel_score": resp_result.score,
            "responsavel_strategy": resp_result.strategy,
            "cargo": q.get("cargo"),
            "prazo": prazo_str,
            "prazo_original": q.get("prazo_original"),
            "meta_entregavel": q.get("entregavel"),
            "status": status_raw,
        }
        pendencias_serializadas.append(entry)

    # Metadados
    data_str = ia_result.get("data") or (estrutura.get("metadados_brutos") or {}).get("data")
    if data_str:
        try:
            data_obj = datetime.strptime(data_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            data_obj = datetime.today().date()
    else:
        data_obj = datetime.today().date()

    tipo_raw = ia_result.get("tipo") or "Coordenação"
    try:
        tipo_enum = TipoReuniao(tipo_raw)
    except ValueError:
        tipo_enum = TipoReuniao.COORDENACAO

    titulo = (ia_result.get("titulo") or "").strip()
    if not titulo:
        titulo = (estrutura.get("metadados_brutos") or {}).get("titulo_ata") or "ATA migrada"

    metadados = {
        "titulo": titulo[:255],
        "tipo": tipo_enum.value,
        "data": data_obj.isoformat(),
        "hora_inicio": ia_result.get("hora_inicio"),
        "hora_fim": ia_result.get("hora_fim"),
        "facilitador_id": None,
        "assunto": ia_result.get("assunto") or None,
        "objetivo": ia_result.get("objetivo") or None,
    }

    warnings: list[str] = []
    if not data_str:
        warnings.append(f"Data não extraída pela IA — usando hoje ({data_obj.isoformat()})")
    if ia_result.get("_mock"):
        warnings.append("Processado em modo mock (OPENAI_API_KEY ausente) — revisar tudo")

    return {
        "arquivo": str(pdf_path),
        "arquivo_hash": arquivo_hash,
        "documento_id_origem": documento_id,
        "status": "pronto",
        "paginas": estrutura.get("paginas", 0),
        "metadados": metadados,
        "participantes": participantes_serializados,
        "pendencias": pendencias_serializadas,
        "registro_narrativo": ia_result.get("registro_narrativo"),
        "resumo_executivo": ia_result.get("resumo_executivo"),
        "is_mock": bool(ia_result.get("_mock")),
        "warnings": warnings,
    }


def cmd_dry_run(args: argparse.Namespace) -> int:
    diretorio = Path(args.dir).expanduser().resolve()
    if not diretorio.is_dir():
        logger.error(f"Diretório não existe: {diretorio}")
        return 2

    pdfs = sorted(diretorio.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        logger.error(f"Nenhum PDF encontrado em {diretorio}")
        return 2

    logger.info(f"Processando {len(pdfs)} PDFs de {diretorio}")

    supabase = _make_supabase()

    part_result = (
        supabase.table("participantes")
        .select("id, nome_completo, cargo, setor")
        .eq("ativo", True)
        .execute()
    )
    ativos_rows = part_result.data or []
    participantes_dir = format_participantes_ativos(ativos_rows)
    logger.info(f"{len(ativos_rows)} participantes ativos carregados")

    atas: list[dict[str, Any]] = []
    stats = {"pronto": 0, "duplicado": 0, "erro_extracao": 0}

    for idx, pdf_path in enumerate(pdfs, 1):
        logger.info(f"[{idx}/{len(pdfs)}] {pdf_path.name}")
        item = _process_one_pdf(
            pdf_path,
            supabase,
            ativos_rows,
            participantes_dir,
            args.auto_match_threshold,
            args.review_threshold,
        )
        atas.append(item)
        stats[item["status"]] = stats.get(item["status"], 0) + 1

    out = {
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "auto_match_threshold": args.auto_match_threshold,
        "review_threshold": args.review_threshold,
        "total_pdfs": len(atas),
        "atas": atas,
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info(
        f"Concluído: {stats['pronto']} prontos, {stats['duplicado']} duplicados, "
        f"{stats['erro_extracao']} erros. JSON em {out_path}"
    )
    return 0


# ---------------------------------------------------------------------------
# APPLY — lê JSON e persiste via RPC atômica
# ---------------------------------------------------------------------------


def _build_request_from_item(item: dict, nome_arquivo: str) -> ConfirmarImportacaoRequest:
    """Converte um item do JSON em ConfirmarImportacaoRequest (schema Pydantic)."""
    meta = item["metadados"]

    # Separar participantes por resolucao
    matched_previews: list[ParticipanteMatchedPreview] = []
    externos_previews: list[ParticipanteExternoPreview] = []
    # nome_ia normalizado -> indice em externos (para pendências referenciarem)
    externo_idx_by_nome: dict[str, int] = {}
    # participante_id matched -> já vinculado (para evitar duplicata no matched)
    matched_ids_set: set[str] = set()

    for p in item.get("participantes") or []:
        resolucao = p.get("resolucao")
        participante_id = p.get("participante_id")
        nome_ia = p.get("nome_ia") or ""

        if resolucao == RESOLUCAO_AUTO and participante_id:
            if participante_id in matched_ids_set:
                continue
            matched_previews.append(
                ParticipanteMatchedPreview(
                    nome=p.get("nome_cadastrado") or nome_ia,
                    participante_id=participante_id,
                    cargo=p.get("cargo_ia") or None,
                )
            )
            matched_ids_set.add(participante_id)
        elif resolucao == RESOLUCAO_SUGESTAO and participante_id:
            # Usuário editou o JSON e confirmou manualmente a sugestão.
            if participante_id in matched_ids_set:
                continue
            matched_previews.append(
                ParticipanteMatchedPreview(
                    nome=p.get("nome_cadastrado") or nome_ia,
                    participante_id=participante_id,
                    cargo=p.get("cargo_ia") or None,
                )
            )
            matched_ids_set.add(participante_id)
        else:
            idx = len(externos_previews)
            externos_previews.append(
                ParticipanteExternoPreview(
                    nome=nome_ia,
                    cargo=p.get("cargo_ia") or "",
                    setor=p.get("setor_ia") or None,
                    email=None,
                )
            )
            externo_idx_by_nome[_norm(nome_ia)] = idx

    # Pendências
    pendencias: list[PendenciaImportacao] = []
    for q in item.get("pendencias") or []:
        resp_id = q.get("responsavel_id")
        # Se usuário editou 'responsavel_resolucao' para auto e preencheu id, respeita
        if not resp_id and q.get("responsavel_resolucao") == RESOLUCAO_AUTO:
            resp_id = q.get("responsavel_sugestao_id")

        externo_idx: Optional[int] = None
        if not resp_id:
            nome_resp = q.get("responsavel_nome_ia") or ""
            externo_idx = externo_idx_by_nome.get(_norm(nome_resp))

        prazo_date = None
        prazo_iso = q.get("prazo")
        if prazo_iso:
            try:
                prazo_date = datetime.strptime(prazo_iso, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        try:
            status_enum = StatusPendencia(q.get("status") or "PENDENTE")
        except ValueError:
            status_enum = StatusPendencia.PENDENTE

        pendencias.append(
            PendenciaImportacao(
                acao=q.get("acao") or "",
                responsavel_nome=q.get("responsavel_nome_ia") or "",
                responsavel_id=resp_id,
                responsavel_externo_idx=externo_idx,
                cargo=q.get("cargo"),
                prazo=prazo_date,
                prazo_original=q.get("prazo_original"),
                meta_entregavel=q.get("meta_entregavel"),
                status=status_enum,
                co_responsavel_id=None,
            )
        )

    metadados = MetadadosImportacao(
        titulo=meta["titulo"],
        tipo=TipoReuniao(meta["tipo"]),
        data=_date.fromisoformat(meta["data"]),
        hora_inicio=meta.get("hora_inicio"),
        hora_fim=meta.get("hora_fim"),
        facilitador_id=meta.get("facilitador_id"),
        assunto=meta.get("assunto"),
        objetivo=meta.get("objetivo"),
    )

    return ConfirmarImportacaoRequest(
        arquivo_hash=item["arquivo_hash"],
        documento_id_origem=item.get("documento_id_origem"),
        nome_arquivo_original=nome_arquivo,
        metadados=metadados,
        participantes_matched=matched_previews,
        participantes_externos=externos_previews,
        pendencias=pendencias,
        registro_narrativo=item.get("registro_narrativo"),
        resumo_executivo=item.get("resumo_executivo"),
    )


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _apply_one(item: dict, supabase, importador_id: Optional[str]) -> dict[str, Any]:
    """Processa um item do JSON. Retorna relatório com status/contagens."""
    arquivo = item.get("arquivo")
    nome_arquivo = Path(arquivo).name if arquivo else "ata-migrada.pdf"

    # Status já decidido no dry-run: duplicado ou erro → pula
    if item.get("status") == "duplicado":
        return {
            "arquivo": arquivo,
            "resultado": "pulado_duplicata",
            "id_reuniao_existente": item.get("duplicado_de"),
        }
    if item.get("status") == "erro_extracao":
        return {
            "arquivo": arquivo,
            "resultado": "pulado_erro_extracao",
            "erro": item.get("erro"),
        }

    # Defense-in-depth: revalida duplicata antes do insert
    dup = check_duplicata(supabase, item.get("arquivo_hash"), item.get("documento_id_origem"))
    if dup:
        return {
            "arquivo": arquivo,
            "resultado": "pulado_duplicata",
            "id_reuniao_existente": dup.get("id_reuniao"),
        }

    # Lê arquivo do disco (obrigatório para upload ao Storage)
    arquivo_bytes: Optional[bytes] = None
    url_pdf: Optional[str] = None
    if arquivo and Path(arquivo).is_file():
        try:
            arquivo_bytes = Path(arquivo).read_bytes()
        except Exception as exc:
            logger.warning(f"Não foi possível ler {arquivo} (seguindo sem upload): {exc}")

    # Monta request
    try:
        req = _build_request_from_item(item, nome_arquivo)
    except Exception as exc:
        return {"arquivo": arquivo, "resultado": "erro", "erro": f"Schema inválido: {exc}"}

    id_reuniao = generate_reuniao_id(req.metadados.data)

    # Upload PDF para Storage (opcional — se falhar, segue sem URL)
    if arquivo_bytes is not None:
        storage_path = f"migradas/{id_reuniao}.pdf"
        try:
            url_pdf = upload_file(
                supabase,
                bucket=settings.supabase_storage_bucket_transcricoes,
                path=storage_path,
                content=arquivo_bytes,
                content_type="application/pdf",
            )
        except Exception as exc:
            logger.warning(f"Upload storage falhou para {id_reuniao}: {exc}")

    facilitador_id = req.metadados.facilitador_id or importador_id

    # Provisionar externos
    externo_idx_to_id, _criados, _stubs = provision_externos(
        supabase, req.participantes_externos
    )

    # Montar payload
    stub_cache: dict[str, str] = {}
    try:
        reuniao_payload, pendencias_payload, externos_links_payload, pend_ignoradas = (
            build_confirmacao_payload(
                supabase,
                req=req,
                id_reuniao=id_reuniao,
                facilitador_id=facilitador_id,
                importador_id=importador_id,
                url_pdf=url_pdf,
                externo_idx_to_id=externo_idx_to_id,
                stub_fallback_cache=stub_cache,
            )
        )
    except ImportacaoServiceError as exc:
        return {"arquivo": arquivo, "resultado": "erro", "erro": str(exc)}

    # RPC
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
        return {"arquivo": arquivo, "resultado": "erro", "erro": f"RPC falhou: {exc}"}

    if not rpc_result.data:
        return {
            "arquivo": arquivo,
            "resultado": "erro",
            "erro": "RPC retornou sem dados",
        }

    data = rpc_result.data[0]
    return {
        "arquivo": arquivo,
        "resultado": "importado",
        "id_reuniao": data.get("reuniao_id"),
        "pendencias": int(data.get("pendencias_count") or 0),
        "pendencias_ignoradas": len(pend_ignoradas),
        "externos_stubs_fallback": len(stub_cache),
    }


def cmd_apply(args: argparse.Namespace) -> int:
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        logger.error(f"Arquivo JSON não existe: {input_path}")
        return 2

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error(f"JSON inválido: {exc}")
        return 2

    atas = data.get("atas") or []
    if not atas:
        logger.error("JSON não contém 'atas'")
        return 2

    supabase = _make_supabase()

    logger.info(f"Aplicando {len(atas)} atas (importador_id={args.importador_id})")

    relatorio: list[dict] = []
    contagem = {"importado": 0, "pulado_duplicata": 0, "pulado_erro_extracao": 0, "erro": 0}

    for idx, item in enumerate(atas, 1):
        nome = Path(item.get("arquivo") or "").name or f"ata-{idx}"
        logger.info(f"[{idx}/{len(atas)}] {nome}")
        resultado = _apply_one(item, supabase, args.importador_id)
        relatorio.append(resultado)
        contagem[resultado["resultado"]] = contagem.get(resultado["resultado"], 0) + 1

    logger.info(
        "Concluído. "
        f"importados={contagem['importado']} "
        f"pulados_duplicata={contagem['pulado_duplicata']} "
        f"pulados_erro_extracao={contagem['pulado_erro_extracao']} "
        f"erros={contagem['erro']}"
    )

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps({"contagem": contagem, "detalhes": relatorio}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"Relatório detalhado em {report_path}")

    return 0 if contagem["erro"] == 0 else 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bulk_import_atas",
        description="Migração em massa de ATAs antigas (PDFs → RPC atômica).",
    )
    subs = parser.add_subparsers(dest="cmd", required=True)

    p_dry = subs.add_parser("dry-run", help="Extrai e gera JSON preview (não persiste).")
    p_dry.add_argument("--dir", required=True, help="Diretório com os PDFs")
    p_dry.add_argument("--out", required=True, help="Arquivo JSON de saída")
    p_dry.add_argument("--limit", type=int, help="Processa só os primeiros N PDFs (teste)")
    p_dry.add_argument(
        "--auto-match-threshold",
        type=int,
        default=DEFAULT_AUTO_THRESHOLD,
        help=f"Score mínimo para auto-match (default {DEFAULT_AUTO_THRESHOLD})",
    )
    p_dry.add_argument(
        "--review-threshold",
        type=int,
        default=DEFAULT_REVIEW_THRESHOLD,
        help=f"Score mínimo para sugestão manual (default {DEFAULT_REVIEW_THRESHOLD})",
    )
    p_dry.set_defaults(func=cmd_dry_run)

    p_apply = subs.add_parser("apply", help="Lê JSON e persiste via RPC atômica.")
    p_apply.add_argument("--in", dest="input", required=True, help="Arquivo JSON do dry-run")
    p_apply.add_argument(
        "--importador-id",
        help="participante_id que será registrado como importado_por_id",
    )
    p_apply.add_argument("--report", help="Arquivo JSON opcional com relatório detalhado")
    p_apply.set_defaults(func=cmd_apply)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
