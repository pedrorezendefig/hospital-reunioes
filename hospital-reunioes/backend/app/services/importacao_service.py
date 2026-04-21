"""
Service compartilhado entre o router HTTP de importação e o script CLI de
migração em massa. Agrupa helpers puros (sem dependência de FastAPI) que
montam o payload consumido pela RPC `confirmar_importacao_atomico`.

Arquitetura:
  - Router HTTP (routers/importacao.py) valida input, chama os helpers daqui
    para montar o payload e chama a RPC atômica.
  - Script CLI (scripts/bulk_import_atas.py) faz o mesmo mas iterando sobre
    múltiplos PDFs e carregando o input de um arquivo JSON pré-revisado.

Erros de validação lançam ImportacaoServiceError (status_code semântico); o
caller decide se converte para HTTPException (router) ou loga e pula (CLI).
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.models.schemas import (
    ConfirmarImportacaoRequest,
    ParticipanteExternoPreview,
)
from app.services.auth_provisioning import provision_with_compensation
from app.services.cargo_mapping import get_cargo_info
from app.services.participant_matcher import _normalize as _normalize_nome

logger = logging.getLogger(__name__)


class ImportacaoServiceError(Exception):
    """Erro de validação/lógica durante montagem do payload de importação."""

    def __init__(self, message: str, status_code: int = 422):
        super().__init__(message)
        self.status_code = status_code


# ---------------------------------------------------------------------------
# Helpers puros — sem dependência de FastAPI
# ---------------------------------------------------------------------------


def format_participantes_ativos(participantes: list[dict]) -> str:
    """Renderiza listagem de participantes para consumo como contexto da IA."""
    if not participantes:
        return "Nenhum participante ativo cadastrado"
    lines = []
    for p in participantes:
        cargo = p.get("cargo") or ""
        setor = p.get("setor") or ""
        extra = f" — {cargo}" if cargo else ""
        if setor:
            extra += f" / {setor}"
        lines.append(f"- {p['nome_completo']}{extra}")
    return "\n".join(lines)


def check_duplicata(
    supabase,
    arquivo_hash: Optional[str],
    documento_id: Optional[str],
) -> Optional[dict]:
    """Retorna dict {motivo, id_reuniao, titulo, data} se duplicata for encontrada.

    Ordem: tenta primeiro por hash, depois por documento_id.
    """
    if arquivo_hash:
        r = (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, data")
            .eq("arquivo_hash", arquivo_hash)
            .limit(1)
            .execute()
        )
        if r.data:
            return {"motivo": "hash", **r.data[0]}
    if documento_id:
        r = (
            supabase.table("reunioes")
            .select("id_reuniao, titulo, data")
            .eq("documento_id_origem", documento_id)
            .limit(1)
            .execute()
        )
        if r.data:
            return {"motivo": "documento_id", **r.data[0]}
    return None


def generate_reuniao_id(data) -> str:
    """Gera id_reuniao único com prefixo MIG_ para ATAs migradas."""
    ts = datetime.now().strftime("%H%M%S")
    uid = uuid.uuid4().hex[:2].upper()
    data_str = data.strftime("%Y%m%d") if hasattr(data, "strftime") else str(data).replace("-", "")
    return f"MIG_{data_str}_{ts}{uid}"


def get_last_id_acao_num(supabase) -> int:
    """Retorna o maior número encontrado em pendencias.id_acao (ex: 'A042' -> 42)."""
    result = (
        supabase.table("pendencias")
        .select("id_acao")
        .order("id_acao", desc=True)
        .limit(1)
        .execute()
    )
    if result.data:
        last_id = result.data[0]["id_acao"]
        nums = re.sub(r"[^0-9]", "", last_id)
        return int(nums) if nums else 0
    return 0


def ensure_external_stub(
    supabase,
    *,
    nome: str,
    cargo: Optional[str],
    setor: Optional[str],
    cache: dict[str, str],
) -> Optional[str]:
    """Garante a existência de um stub externo (is_externo=true, ativo=false)
    para um responsável de pendência que não casou com matched nem com externo
    do preview.

    Reusa stubs existentes por nome_completo normalizado para não criar
    duplicatas quando a mesma pessoa aparece em várias pendências/ATAs. O
    `cache` é passado pelo caller para memoizar dentro da mesma execução.

    Retorna o id do participante ou None se o nome vier vazio ou a inserção
    falhar.
    """
    nome_limpo = (nome or "").strip()
    if not nome_limpo:
        return None

    nome_norm = _normalize_nome(nome_limpo)
    if nome_norm in cache:
        return cache[nome_norm]

    existing = (
        supabase.table("participantes")
        .select("id, nome_completo")
        .eq("is_externo", True)
        .is_("email", "null")
        .ilike("nome_completo", nome_limpo)
        .limit(1)
        .execute()
    )
    if existing.data:
        pid = existing.data[0]["id"]
        cache[nome_norm] = pid
        return pid

    cargo_info = get_cargo_info(cargo) if cargo else None
    role = cargo_info.role if cargo_info else "coordenador"
    setor_final = cargo_info.setor if cargo_info else setor
    area_final = cargo_info.area if cargo_info else None

    try:
        stub = (
            supabase.table("participantes")
            .insert(
                {
                    "nome_completo": nome_limpo,
                    "cargo": cargo or "",
                    "email": None,
                    "setor": setor_final,
                    "area": area_final,
                    "role": role,
                    "ativo": False,
                    "is_externo": True,
                    "auth_user_id": None,
                }
            )
            .execute()
        )
    except Exception as exc:
        logger.error(f"[importacao_service] Erro ao criar stub '{nome_limpo}': {exc}")
        return None

    if not stub.data:
        logger.error(f"[importacao_service] INSERT stub '{nome_limpo}' sem retorno")
        return None

    pid = stub.data[0]["id"]
    cache[nome_norm] = pid
    return pid


# ---------------------------------------------------------------------------
# Provisionamento de externos declarados no preview
# ---------------------------------------------------------------------------


def provision_externos(
    supabase,
    externos: list[ParticipanteExternoPreview],
) -> tuple[dict[int, str], int, int]:
    """Provisiona cada externo do preview (com ou sem email) ANTES da RPC.

    Externos com email: reusa por email existente OU cria via
    provision_with_compensation (saga Auth + participante).
    Externos sem email: cria stub is_externo=true, ativo=false, email=null
    (requer migration 026).

    Falhas individuais são logadas e puladas (o externo problemático apenas
    não receberá id; a pendência correspondente cai no fallback de stub por
    nome no build_confirmacao_payload).

    Retorna (externo_idx_to_id, total_criados_com_email, total_stubs).
    """
    externo_idx_to_id: dict[int, str] = {}
    total_criados = 0
    total_stubs = 0

    for idx, e in enumerate(externos):
        email_str = str(e.email) if e.email else None
        cargo_info = get_cargo_info(e.cargo)
        role = cargo_info.role if cargo_info else "coordenador"
        setor = cargo_info.setor if cargo_info else e.setor
        area = cargo_info.area if cargo_info else None

        if email_str:
            existing = (
                supabase.table("participantes").select("id").eq("email", email_str).execute()
            )
            if existing.data:
                externo_idx_to_id[idx] = existing.data[0]["id"]
                continue

            try:
                new_p, _auth_uid = provision_with_compensation(
                    supabase,
                    {
                        "nome_completo": e.nome,
                        "cargo": e.cargo,
                        "email": email_str,
                        "setor": setor,
                        "area": area,
                        "role": role,
                        "ativo": True,
                        "is_externo": True,
                    },
                    role=role,
                )
            except Exception as exc:
                logger.error(
                    f"[importacao_service] Erro ao criar externo '{e.nome}' "
                    f"(rollback executado): {exc}"
                )
                continue

            externo_idx_to_id[idx] = new_p["id"]
            total_criados += 1
        else:
            try:
                stub = (
                    supabase.table("participantes")
                    .insert(
                        {
                            "nome_completo": e.nome,
                            "cargo": e.cargo,
                            "email": None,
                            "setor": setor,
                            "area": area,
                            "role": role,
                            "ativo": False,
                            "is_externo": True,
                            "auth_user_id": None,
                        }
                    )
                    .execute()
                )
            except Exception as exc:
                logger.error(
                    f"[importacao_service] Erro ao criar stub sem email '{e.nome}': {exc}"
                )
                continue

            if not stub.data:
                logger.error(
                    f"[importacao_service] INSERT stub '{e.nome}' sem retorno"
                )
                continue

            externo_idx_to_id[idx] = stub.data[0]["id"]
            total_stubs += 1

    return externo_idx_to_id, total_criados, total_stubs


# ---------------------------------------------------------------------------
# Montagem do payload RPC
# ---------------------------------------------------------------------------


def build_confirmacao_payload(
    supabase,
    *,
    req: ConfirmarImportacaoRequest,
    id_reuniao: str,
    facilitador_id: Optional[str],
    importador_id: Optional[str],
    url_pdf: Optional[str],
    externo_idx_to_id: dict[int, str],
    stub_fallback_cache: dict[str, str],
) -> tuple[dict, list[dict], list[dict], list[dict]]:
    """Monta os 3 payloads consumidos pela RPC confirmar_importacao_atomico.

    `stub_fallback_cache` é mutável e pode ser populado internamente para
    cada responsável de pendência que não resolveu nem por matched, nem por
    externo_idx, nem por stub já existente — o caller pode inspecioná-lo
    depois para contar stubs fallback criados.

    Retorna:
        (reuniao_payload, pendencias_payload, externos_links_payload, pendencias_ignoradas)
    Levanta ImportacaoServiceError quando regras de co-responsável ou lookups
    essenciais falham.
    """
    last_num = get_last_id_acao_num(supabase)
    pendencias_payload: list[dict] = []
    pendencias_ignoradas: list[dict] = []

    for i, p in enumerate(req.pendencias):
        resp_id = p.responsavel_id
        if not resp_id and p.responsavel_externo_idx is not None:
            resp_id = externo_idx_to_id.get(p.responsavel_externo_idx)
        if not resp_id:
            resp_id = ensure_external_stub(
                supabase,
                nome=p.responsavel_nome,
                cargo=p.cargo,
                setor=None,
                cache=stub_fallback_cache,
            )
        if not resp_id:
            logger.warning(
                f"[importacao_service] Pendência #{i+1} '{p.acao[:60]}' sem "
                f"responsável (nome vazio) — ignorada"
            )
            pendencias_ignoradas.append({"acao": p.acao, "motivo": "sem_responsavel"})
            continue

        resp_info = (
            supabase.table("participantes")
            .select("nome_completo, cargo, is_externo")
            .eq("id", resp_id)
            .execute()
        )
        if not resp_info.data:
            logger.warning(f"[importacao_service] responsavel_id {resp_id} não encontrado")
            pendencias_ignoradas.append(
                {"acao": p.acao, "motivo": "responsavel_nao_encontrado"}
            )
            continue
        resp_row = resp_info.data[0]
        resp_nome = resp_row["nome_completo"]
        resp_cargo = resp_row.get("cargo") or p.cargo
        resp_is_externo = bool(resp_row.get("is_externo"))

        co_resp_id = p.co_responsavel_id
        co_resp_nome = None
        if co_resp_id:
            if not resp_is_externo:
                raise ImportacaoServiceError(
                    f"Co-responsável só pode ser definido para pendências de "
                    f"externos (ação '{p.acao[:40]}')"
                )
            co_info = (
                supabase.table("participantes")
                .select("nome_completo, is_externo")
                .eq("id", co_resp_id)
                .execute()
            )
            if not co_info.data:
                raise ImportacaoServiceError(
                    f"Co-responsável {co_resp_id} não encontrado"
                )
            if co_info.data[0].get("is_externo"):
                raise ImportacaoServiceError(
                    "Co-responsável deve ser participante interno"
                )
            co_resp_nome = co_info.data[0]["nome_completo"]

        new_id_acao = f"A{last_num + len(pendencias_payload) + 1:03d}"
        pendencias_payload.append(
            {
                "id_acao": new_id_acao,
                "id_reuniao": id_reuniao,
                "descricao_acao": p.acao,
                "responsavel_id": resp_id,
                "responsavel_nome": resp_nome,
                "cargo": resp_cargo,
                "prazo": str(p.prazo) if p.prazo else None,
                "meta_entregavel": p.meta_entregavel,
                "status": p.status.value if hasattr(p.status, "value") else str(p.status),
                "co_responsavel_id": co_resp_id,
                "co_responsavel_nome": co_resp_nome,
            }
        )

    reuniao_payload = {
        "id_reuniao": id_reuniao,
        "titulo": req.metadados.titulo,
        "data": str(req.metadados.data),
        "hora_inicio": str(req.metadados.hora_inicio) if req.metadados.hora_inicio else None,
        "hora_fim": str(req.metadados.hora_fim) if req.metadados.hora_fim else None,
        "tipo": req.metadados.tipo.value,
        "objetivo": req.metadados.objetivo,
        "facilitador_id": facilitador_id,
        "status_ata": "MIGRADA",
        "fonte": "IMPORTACAO_LEGADA",
        "documento_id_origem": req.documento_id_origem,
        "arquivo_hash": req.arquivo_hash,
        "nome_arquivo_original": req.nome_arquivo_original,
        "importado_por_id": importador_id,
        "url_pdf_preliminar": url_pdf,
        "url_pdf_assinado": url_pdf,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "json_ata": {
            "participantes": [p.model_dump(mode="json") for p in req.participantes_matched]
            + [p.model_dump(mode="json") for p in req.participantes_externos],
            "quadro_atribuicoes": [p.model_dump(mode="json") for p in req.pendencias],
            "registro_narrativo": req.registro_narrativo,
            "resumo_executivo": req.resumo_executivo,
            "_migrada": True,
        },
    }

    todos_participantes_ids: set[str] = {
        p.participante_id for p in req.participantes_matched
    }
    todos_participantes_ids.update(externo_idx_to_id.values())
    todos_participantes_ids.update(stub_fallback_cache.values())
    if importador_id:
        todos_participantes_ids.add(importador_id)
    externos_links_payload: list[dict] = [
        {"id_reuniao": id_reuniao, "participante_id": pid}
        for pid in todos_participantes_ids
    ]

    return reuniao_payload, pendencias_payload, externos_links_payload, pendencias_ignoradas
