"""
Service de liberação de pendências (tarefas) após assinatura da ata.

Após o webhook ClickSign (close / auto_close) ser recebido com sucesso,
este módulo extrai o `quadro_atribuicoes` do json_ata e insere cada ação
na tabela `pendencias` com status PENDENTE.
"""

import logging
import re

logger = logging.getLogger(__name__)


def _get_last_id_num(supabase) -> int:
    """Retorna o número do último ID de ação (ex: 9 para 'A009')."""
    result = supabase.table("pendencias").select("id_acao").order("id_acao", desc=True).limit(1).execute()
    if result.data:
        last_id = result.data[0]["id_acao"]
        # Extrair apenas os números
        nums = re.sub(r"[^0-9]", "", last_id)
        return int(nums) if nums else 0
    return 0


def _find_participante(supabase, nome: str) -> dict | None:
    """Busca um participante pelo nome (match parcial, case-insensitive).

    Retorna `{id, cargo}` quando encontra exatamente o primeiro match, ou `None`.
    O cargo é puxado pra que o caller possa popular `pendencias.cargo` a partir
    da fonte canônica (`participantes.cargo`) em vez do texto que o LLM colocou
    no `quadro_atribuicoes[].cargo`.
    """
    if not nome or str(nome).lower() in ("null", "none", "n/a", ""):
        return None
    result = (
        supabase.table("participantes")
        .select("id, nome_completo, cargo")
        .ilike("nome_completo", f"%{nome.strip()}%")
        .limit(1)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {"id": row["id"], "cargo": row.get("cargo")}
    return None


def _normalizar_prazo(prazo_raw: str | None) -> str | None:
    """
    Normaliza qualquer formato de data para YYYY-MM-DD (exigido pelo Postgres).
    """
    if not prazo_raw or str(prazo_raw).lower() in ("null", "none", "a definir", ""):
        return None

    prazo_str = str(prazo_raw).strip()

    # Já está no formato correto YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", prazo_str):
        return prazo_str

    # DD/MM/YYYY ou DD-MM-YYYY
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", prazo_str)
    if m:
        d, mes, ano = m.group(1), m.group(2), m.group(3)
        return f"{ano}-{mes.zfill(2)}-{d.zfill(2)}"

    # Tenta parsing genérico
    try:
        from datetime import datetime as _dt

        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                parsed = _dt.strptime(prazo_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue
    except Exception:
        pass

    logger.warning(f"[PendenciaService] Formato de prazo não reconhecido: '{prazo_str}'")
    return None


def liberar_pendencias(supabase, id_reuniao: str, origem: str = "NÃO_ESPECIFICADA") -> int:
    """
    Extrai o quadro_atribuicoes do json_ata da reunião e cria
    as pendências na tabela `pendencias` em lote.
    """
    logger.info(f"[PendenciaService] Iniciando liberação de pendências para {id_reuniao} (Origem: {origem})")

    # 1. Buscar json_ata da reunião
    result = supabase.table("reunioes").select("json_ata, status_ata").eq("id_reuniao", id_reuniao).execute()
    if not result.data:
        logger.warning(f"[PendenciaService] Reunião {id_reuniao} não encontrada no banco.")
        return 0

    reuniao_db = result.data[0]
    json_ata = reuniao_db.get("json_ata")

    if not json_ata:
        logger.warning(
            f"[PendenciaService] json_ata está vazio ou nulo para {id_reuniao}. Status atual: {reuniao_db.get('status_ata')}"  # noqa: E501
        )
        return 0

    json_ata = result.data[0]["json_ata"]
    logger.info(f"[PendenciaService] Keys no json_ata: {list(json_ata.keys())}")
    quadro = json_ata.get("quadro_atribuicoes")

    if quadro is None:
        quadro = json_ata.get("atribuicoes") or json_ata.get("acoes") or []
        if quadro:
            logger.info("[PendenciaService] Usando fallback para quadro de atribuições")

    logger.info(f"[PendenciaService] {len(quadro) if quadro else 0} itens no quadro_atribuicoes")

    if not quadro:
        logger.info(
            f"[PendenciaService] Nenhuma ação no quadro_atribuicoes para {id_reuniao}. json_ata keys: {list(json_ata.keys())}"  # noqa: E501
        )
        return 0

    # 2. Verificar pendências já existentes (idempotência)
    existing = supabase.table("pendencias").select("id_acao").eq("id_reuniao", id_reuniao).execute()
    if existing.data:
        logger.info(f"[PendenciaService] {len(existing.data)} pendências já existem para {id_reuniao}. Ignorando.")
        return 0

    # 3. Preparar lote de inserção
    last_num = _get_last_id_num(supabase)
    batch_pendencias = []

    for i, acao in enumerate(quadro):
        responsavel_nome = acao.get("responsavel") or acao.get("responsavel_nome") or ""
        participante = _find_participante(supabase, responsavel_nome)
        responsavel_id = participante["id"] if participante else None
        # Quando o nome resolve pra um participante, usar cargo canônico do cadastro;
        # fallback no texto que o LLM colocou no quadro_atribuicoes pra cobrir casos
        # em que o responsável não está cadastrado (alucinação ou pessoa de passagem).
        cargo_canonico = (
            (participante.get("cargo") or "").strip()
            if participante and participante.get("cargo")
            else (str(acao.get("cargo") or "").strip() or None)
        )

        prazo_normalizado = _normalizar_prazo(acao.get("prazo"))
        new_id_acao = f"A{last_num + i + 1:03d}"

        pendencia = {
            "id_acao": new_id_acao,
            "id_reuniao": id_reuniao,
            "descricao_acao": acao.get("acao") or acao.get("descricao_acao") or "Ação sem descrição",
            "responsavel_nome": responsavel_nome,
            "responsavel_id": responsavel_id,
            "cargo": cargo_canonico,
            "prazo": prazo_normalizado,
            "meta_entregavel": acao.get("meta_entregavel") or acao.get("entregavel") or None,
            "status": "PENDENTE",
        }
        batch_pendencias.append(pendencia)

    # 4. Executar inserções em lote
    try:
        if batch_pendencias:
            logger.info(f"[PendenciaService] Inserindo {len(batch_pendencias)} pendências em lote...")
            supabase.table("pendencias").insert(batch_pendencias).execute()

            logger.info(
                f"[PendenciaService] ✅ Sucesso: {len(batch_pendencias)} pendências liberadas para {id_reuniao}"
            )
            return len(batch_pendencias)
    except Exception as e:
        logger.error(f"[PendenciaService] Erro Crítico no Batch Insert para {id_reuniao}: {e}")
        raise e
    return 0
