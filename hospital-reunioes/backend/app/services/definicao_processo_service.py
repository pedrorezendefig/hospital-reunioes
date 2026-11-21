"""As Definições de processo do setor (ADR 0098, decisão 9; issue #1875).

A linha do tipo Processo do quadro da Ata entra, no envio, na lista do setor
da Reunião, com o trecho da Ata copiado: a lista não muda se a Ata for
corrigida depois. Sem responsável, sem prazo e sem lembrete.

Quem vê sai do vínculo, até o organograma (decisões 85 e 86 da #1757): o
Facilitador vê a lista de todo setor em que conduz alguma Reunião, e os itens
das Reuniões que ele mesmo conduz; o Super admin vê todas. Tirar da lista pede
anotação e cabe ao Facilitador da Reunião de origem e ao Super admin; o item
fica registrado como retirado.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from app.services.quadro_classificacao import PROCESSO, tipo_da_linha

logger = logging.getLogger(__name__)

ATIVA = "ATIVA"
RETIRADA = "RETIRADA"


class RetiradaRecusada(ValueError):  # noqa: N818, o nome do domínio
    """Tirar da lista sem anotação."""


class JaRetirada(ValueError):  # noqa: N818, o nome do domínio
    """O item já saiu da lista."""


def _texto(valor) -> str:
    return valor.strip() if isinstance(valor, str) else ""


def nascer_definicoes(supabase, id_reuniao: str, quadro: list[dict]) -> int:
    """Cria um item por linha de Processo do quadro. Idempotente pela posição
    no quadro: Reenviar e a reconciliação das 5h30 não duplicam."""
    from app.services.pendencia_service import _e_conflito_unicidade

    linhas = [
        (posicao, item)
        for posicao, item in enumerate(quadro or [])
        if isinstance(item, dict) and tipo_da_linha(item) == PROCESSO
    ]
    if not linhas:
        return 0
    existentes = (
        supabase.table("definicoes_processo").select("quadro_pos").eq("id_reuniao", id_reuniao).execute().data or []
    )
    ocupadas = {r.get("quadro_pos") for r in existentes}
    criadas = 0
    for posicao, item in linhas:
        if posicao in ocupadas:
            continue
        definicao = {
            "id_reuniao": id_reuniao,
            "quadro_pos": posicao,
            "trecho": _texto(item.get("acao")) or _texto(item.get("descricao_acao")) or "Processo sem descrição",
            "objetivo": _texto(item.get("objetivo_meta")) or None,
            "status": ATIVA,
        }
        try:
            supabase.table("definicoes_processo").insert(definicao).execute()
            criadas += 1
        except Exception as e:
            # Dois envios ao mesmo tempo: o outro já criou este item.
            if not _e_conflito_unicidade(e):
                raise
    if criadas:
        logger.info("[Processo] %s definição(ões) de processo da Reunião %s", criadas, id_reuniao)
    return criadas


# ─── Quem vê e quem tira (regra pura) ────────────────────────────────────────


def pode_ver(
    reuniao: dict | None,
    *,
    me_id: str | None,
    super_admin: bool,
    setores_que_conduz: set[str],
    ocultas: set[str],
) -> bool:
    """Vê o item quem conduz a Reunião de origem ou alguma Reunião do mesmo
    setor; o Super admin vê todos. A Reunião oculta (Núcleo) some para todos."""
    if reuniao is None or reuniao.get("id_reuniao") in ocultas:
        return False
    if super_admin:
        return True
    if me_id is not None and reuniao.get("facilitador_id") == me_id:
        return True
    setor = reuniao.get("setor_id")
    return setor is not None and setor in setores_que_conduz


def pode_retirar(reuniao: dict, *, me_id: str | None, super_admin: bool) -> bool:
    """Tiram da lista o Facilitador da Reunião de origem e o Super admin."""
    return super_admin or (me_id is not None and reuniao.get("facilitador_id") == me_id)


# ─── Leitura e retirada no banco ─────────────────────────────────────────────


def _reunioes(supabase, ids) -> dict[str, dict]:
    ids = sorted(set(ids))
    if not ids:
        return {}
    linhas = (
        supabase.table("reunioes")
        .select("id_reuniao, titulo, data, setor_id, facilitador_id")
        .in_("id_reuniao", ids)
        .execute()
        .data
    )
    return {r["id_reuniao"]: r for r in linhas or []}


def _setores_que_conduz(supabase, me_id: str | None) -> tuple[set[str], set[str]]:
    """As Reuniões que a pessoa conduz e os setores delas."""
    if me_id is None:
        return set(), set()
    linhas = supabase.table("reunioes").select("id_reuniao, setor_id").eq("facilitador_id", me_id).execute().data or []
    return {r["id_reuniao"] for r in linhas}, {r["setor_id"] for r in linhas if r.get("setor_id")}


def listar(supabase, *, me_id: str | None, super_admin: bool, ocultas: set[str]) -> list[dict]:
    """Os itens na lista que quem pede vê, com a Reunião e o setor de origem."""
    conduzidas, setores = _setores_que_conduz(supabase, me_id)
    if not super_admin and not conduzidas:
        return []
    # A lista do hospital inteiro é pequena (só as linhas de Processo): a regra
    # de quem vê fica num lugar só, em `pode_ver`.
    itens = supabase.table("definicoes_processo").select("*").eq("status", ATIVA).execute().data or []
    reunioes = _reunioes(supabase, [i["id_reuniao"] for i in itens])
    ids_de_setor = sorted({r["setor_id"] for r in reunioes.values() if r.get("setor_id")})
    nomes = {}
    if ids_de_setor:
        linhas = supabase.table("setores").select("id, nome").in_("id", ids_de_setor).execute().data or []
        nomes = {s["id"]: s["nome"] for s in linhas}
    saida = []
    for item in itens:
        reuniao = reunioes.get(item["id_reuniao"])
        regra = {"me_id": me_id, "super_admin": super_admin}
        if not pode_ver(reuniao, setores_que_conduz=setores, ocultas=ocultas, **regra):
            continue
        saida.append(
            {
                **item,
                "reuniao_titulo": reuniao.get("titulo"),
                "reuniao_data": reuniao.get("data"),
                "setor_id": reuniao.get("setor_id"),
                "setor_nome": nomes.get(reuniao.get("setor_id")),
                "pode_retirar": pode_retirar(reuniao, **regra),
            }
        )
    saida.sort(key=lambda i: ((i["setor_nome"] or "~").lower(), str(i.get("created_at") or "")))
    return saida


class ItemInexistente(LookupError):  # noqa: N818, o nome do domínio
    """O item não existe ou quem pede não o vê."""


class SemPermissao(PermissionError):  # noqa: N818, o nome do domínio
    """Vê o item, mas não é o Facilitador da Reunião de origem."""


def retirar(
    supabase,
    id_item: str,
    anotacao: str | None,
    *,
    me_id: str | None,
    autor_nome: str,
    super_admin: bool,
    ocultas: set[str],
) -> dict:
    """Tira o item da lista com anotação. Ele fica registrado como retirado."""
    linhas = supabase.table("definicoes_processo").select("*").eq("id", id_item).execute().data
    item = linhas[0] if linhas else None
    reuniao = _reunioes(supabase, [item["id_reuniao"]]).get(item["id_reuniao"]) if item else None
    _, setores = _setores_que_conduz(supabase, me_id)
    regra = {"me_id": me_id, "super_admin": super_admin}
    if item is None or not pode_ver(reuniao, setores_que_conduz=setores, ocultas=ocultas, **regra):
        raise ItemInexistente("Definição de processo não encontrada")
    if not pode_retirar(reuniao, **regra):
        raise SemPermissao("Só o Facilitador da Reunião de origem tira o item da lista")
    texto = _texto(anotacao)
    if not texto:
        raise RetiradaRecusada("Tirar da lista pede uma anotação dizendo por quê.")
    if item.get("status") != ATIVA:
        raise JaRetirada("Este item já saiu da lista.")
    mudanca = {
        "status": RETIRADA,
        "retirada_em": datetime.now(UTC).isoformat(),
        "retirada_por_id": me_id,
        "retirada_por_nome": autor_nome,
        "anotacao_retirada": texto,
    }
    # Só tira o que ainda está na lista: dois cliques não sobrescrevem a anotação.
    gravada = supabase.table("definicoes_processo").update(mudanca).eq("id", id_item).eq("status", ATIVA).execute().data
    if not gravada:
        raise JaRetirada("Este item já saiu da lista.")
    return gravada[0]
