"""
Service de liberação de pendências (tarefas) após assinatura da ata.

Após o webhook ClickSign (close / auto_close) ser recebido com sucesso,
este módulo extrai o `quadro_atribuicoes` do json_ata e insere cada ação
na tabela `pendencias` com status PENDENTE.
"""
import logging
import re
from typing import Optional

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


def _find_participante_id(supabase, nome: str) -> Optional[str]:
    """Busca o ID de um participante pelo nome (match exato ou parcial)."""
    if not nome or str(nome).lower() in ("null", "none", "n/a", ""):
        return None
    result = supabase.table("participantes").select("id, nome_completo").ilike(
        "nome_completo", f"%{nome.strip()}%"
    ).limit(1).execute()
    if result.data:
        return result.data[0]["id"]
    return None


def _normalizar_prazo(prazo_raw: Optional[str]) -> Optional[str]:
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
        logger.warning(f"[PendenciaService] json_ata está vazio ou nulo para {id_reuniao}. Status atual: {reuniao_db.get('status_ata')}")
        return 0

    json_ata = result.data[0]["json_ata"]
    logger.info(f"[PendenciaService] Keys no json_ata: {list(json_ata.keys())}")
    quadro = json_ata.get("quadro_atribuicoes")
    
    if quadro is None:
        quadro = json_ata.get("atribuicoes") or json_ata.get("acoes") or []
        if quadro:
            logger.info(f"[PendenciaService] Usando fallback para quadro de atribuições")

    logger.info(f"[PendenciaService] {len(quadro) if quadro else 0} itens no quadro_atribuicoes")

    if not quadro:
        logger.info(f"[PendenciaService] Nenhuma ação no quadro_atribuicoes para {id_reuniao}. json_ata keys: {list(json_ata.keys())}")
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
        responsavel_id = _find_participante_id(supabase, responsavel_nome)

        prazo_normalizado = _normalizar_prazo(acao.get("prazo"))
        new_id_acao = f"A{last_num + i + 1:03d}"

        pendencia = {
            "id_acao": new_id_acao,
            "id_reuniao": id_reuniao,
            "descricao_acao": acao.get("acao") or acao.get("descricao_acao") or "Ação sem descrição",
            "responsavel_nome": responsavel_nome,
            "responsavel_id": responsavel_id,
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

            logger.info(f"[PendenciaService] ✅ Sucesso: {len(batch_pendencias)} pendências liberadas para {id_reuniao}")
            return len(batch_pendencias)
    except Exception as e:
        logger.error(f"[PendenciaService] Erro Crítico no Batch Insert para {id_reuniao}: {e}")
        raise e
    return 0
