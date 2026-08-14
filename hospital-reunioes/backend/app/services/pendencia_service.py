"""
Service de criação de Pendências — origem única: a Reunião (ADR 0003/0011).

`liberar_pendencias` extrai o `quadro_atribuicoes` do json_ata e cria as
Pendências com status PENDENTE. Desde o ADR 0030 o nascimento é incremental:
a idempotência é POR AÇÃO do quadro (chave estável `quadro_pos` = posição da
ação no quadro_atribuicoes), e um `filtro` opcional restringe quais ações
nascem (ex.: só as do signatário que acabou de assinar). O caminho total
(webhook close/auto_close → ASSINADA, "finalizar sem assinatura" → APROVADA)
é o mesmo fluxo sem filtro. O núcleo `_inserir_pendencias` numera os IDs
`A###` na sequência global com retry contra inserções concorrentes.
"""

import logging
import re
from collections.abc import Callable

from app.services.resolucao_service import montar_candidatos, resolver_quadro

logger = logging.getLogger(__name__)

_MAX_TENTATIVAS_INSERT = 4


def _get_last_id_num(supabase) -> int:
    """Retorna o número do último ID de ação (ex: 9 para 'A009')."""
    result = supabase.table("pendencias").select("id_acao").order("id_acao", desc=True).limit(1).execute()
    if result.data:
        last_id = result.data[0]["id_acao"]
        # Extrair apenas os números
        nums = re.sub(r"[^0-9]", "", last_id)
        return int(nums) if nums else 0
    return 0


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


def _e_conflito_unicidade(e: Exception) -> bool:
    """Detecta violação de unicidade do Postgres (23505) vinda do PostgREST."""
    if getattr(e, "code", None) == "23505":
        return True
    msg = str(e)
    return "23505" in msg or "duplicate key" in msg.lower()


def _posicoes_ocupadas(supabase, id_reuniao: str) -> set:
    rows = supabase.table("pendencias").select("quadro_pos").eq("id_reuniao", id_reuniao).execute().data or []
    return {r.get("quadro_pos") for r in rows if r.get("quadro_pos") is not None}


def _inserir_pendencias(supabase, id_reuniao: str, itens: list[dict]) -> list[dict]:
    """Núcleo compartilhado de inserção: numera os IDs `A###` continuando a
    sequência global e insere o lote na tabela `pendencias`.

    Cada item chega com a origem já definida (`id_reuniao`), o `quadro_pos` e
    os campos de domínio prontos; aqui nascem só o `id_acao` e o status.

    Webhooks `sign` chegam em paralelo (ADR 0030): uma violação de unicidade
    (PK `A###` ou índice parcial por `quadro_pos`) significa que outra sessão
    ganhou a corrida. O retry relê a numeração e as posições já ocupadas,
    descarta o que já nasceu e re-insere o restante; nada duplica.
    """
    restantes = list(itens)
    for tentativa in range(1, _MAX_TENTATIVAS_INSERT + 1):
        if not restantes:
            return []
        last_num = _get_last_id_num(supabase)
        batch = [
            {"status": "PENDENTE", **item, "id_acao": f"A{last_num + i + 1:03d}"} for i, item in enumerate(restantes)
        ]
        try:
            supabase.table("pendencias").insert(batch).execute()
            return batch
        except Exception as e:
            if not _e_conflito_unicidade(e) or tentativa == _MAX_TENTATIVAS_INSERT:
                raise
            logger.warning(
                f"[PendenciaService] Conflito de unicidade na tentativa {tentativa} para {id_reuniao} "
                f"(inserção concorrente); relendo estado e re-tentando: {e}"
            )
            ocupadas = _posicoes_ocupadas(supabase, id_reuniao)
            restantes = [item for item in restantes if item.get("quadro_pos") not in ocupadas]
    return []


def liberar_pendencias(
    supabase,
    id_reuniao: str,
    origem: str = "NÃO_ESPECIFICADA",
    filtro: Callable[[dict], bool] | None = None,
) -> int:
    """
    Extrai o quadro_atribuicoes do json_ata da reunião e cria
    as pendências na tabela `pendencias` em lote.

    Idempotência POR AÇÃO do quadro (ADR 0030): cada Pendência carrega
    `quadro_pos` (posição da ação no quadro) e ações já nascidas são puladas.
    `filtro` opcional recebe a ação RESOLVIDA (com `responsavel_id`) e decide
    se ela nasce nesta chamada; é o modo incremental do gatilho por
    assinatura; sem filtro, nascem todas as ações restantes (fechamento total
    e aprovação sem assinatura).

    Guarda de legado: se a Reunião já tem Pendência sem `quadro_pos` (liberação
    total pré-incremental), nada é criado, comportamento idêntico ao antigo.
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

    # 2. Idempotência por ação (ADR 0030): posições do quadro já com Pendência
    existing = supabase.table("pendencias").select("id_acao, quadro_pos").eq("id_reuniao", id_reuniao).execute()
    existentes = existing.data or []
    if any(r.get("quadro_pos") is None for r in existentes):
        # Legado pré-incremental: a liberação total já aconteceu sem quadro_pos;
        # sem a chave por ação, recriar seria duplicar. Mantém o contrato antigo.
        logger.info(
            f"[PendenciaService] {len(existentes)} pendências legadas (sem quadro_pos) em {id_reuniao}. Ignorando."
        )
        return 0
    posicoes_ocupadas = {r["quadro_pos"] for r in existentes}

    # 3. Resolver responsáveis pela Resolução canônica (ADR 0008): roster da
    # Reunião primeiro, só ativos, ambiguidade/desconhecido fica sem vínculo.
    # Vínculo pré-gravado no item (validação/Ata Guiada) é honrado; id forjado
    # ou de inativo é descartado e o item volta à resolução por nome.
    candidatos = montar_candidatos(supabase, id_reuniao)
    quadro_normalizado = []
    for acao in quadro:
        item = dict(acao)
        nome_bruto = str(item.get("responsavel") or item.get("responsavel_nome") or "").strip()
        item["responsavel"] = "" if nome_bruto.lower() in ("null", "none", "n/a") else nome_bruto
        quadro_normalizado.append(item)
    quadro_resolvido = resolver_quadro(quadro_normalizado, candidatos)

    # 4. Preparar lote de inserção: pula posições já nascidas e aplica o filtro
    batch_pendencias = []

    for posicao, acao in enumerate(quadro_resolvido):
        if posicao in posicoes_ocupadas:
            continue
        if filtro is not None and not filtro(acao):
            continue
        pendencia = {
            "id_reuniao": id_reuniao,
            "quadro_pos": posicao,
            "descricao_acao": acao.get("acao") or acao.get("descricao_acao") or "Ação sem descrição",
            # Com vínculo, resolver_quadro já trocou responsavel/cargo pelos
            # canônicos do cadastro; sem vínculo fica o texto do quadro (LLM).
            "responsavel_nome": acao.get("responsavel") or "",
            "responsavel_id": acao.get("responsavel_id"),
            "cargo": str(acao.get("cargo") or "").strip() or None,
            "prazo": _normalizar_prazo(acao.get("prazo")),
            "meta_entregavel": acao.get("meta_entregavel") or acao.get("entregavel") or None,
        }
        batch_pendencias.append(pendencia)

    # 5. Executar inserções em lote (núcleo compartilhado numera os A###)
    try:
        if batch_pendencias:
            logger.info(f"[PendenciaService] Inserindo {len(batch_pendencias)} pendências em lote...")
            criadas = _inserir_pendencias(supabase, id_reuniao, batch_pendencias)

            logger.info(f"[PendenciaService] ✅ Sucesso: {len(criadas)} pendências liberadas para {id_reuniao}")
            return len(criadas)
    except Exception as e:
        logger.error(f"[PendenciaService] Erro Crítico no Batch Insert para {id_reuniao}: {e}")
        raise e
    return 0
