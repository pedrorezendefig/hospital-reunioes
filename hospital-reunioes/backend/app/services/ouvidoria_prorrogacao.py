"""Prorrogação de prazo da área (issue #333, PRD #318, ADR 0034 decisão 12).

A regra da casa cabe em três linhas: a área pede UMA vez, com justificativa, e
ANTES de vencer. O sistema recusa sozinho o que fura qualquer uma delas, sem
depender da atenção do ouvidor.

Este módulo é a regra, não a rota: `motivo_de_recusa` é função pura sobre o
estado do caso, e o cálculo do prazo novo vem do motor
(`ouvidoria_prazos.vencimento_prorrogado`), que já corta no teto de 30 dias
úteis. Quem grava e quem notifica são as rotas.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.services.ouvidoria_prazos import FUSO, esta_vencido

logger = logging.getLogger(__name__)

PENDENTE = "pendente"
APROVADA = "aprovada"
NEGADA = "negada"

# Quantos dias úteis a área pode pedir de uma vez. O teto real é o de 30 dias
# úteis da entrada, aplicado pelo motor; este limite existe para o formulário
# não aceitar um número absurdo antes de o motor cortar.
MAX_DIAS_UTEIS_PEDIDOS = 30

AGUARDANDO_AREA = "aguardando_area"

CAMPOS_PRORROGACAO_TUPLA = (
    "id",
    "manifestacao_id",
    "justificativa",
    "dias_uteis_pedidos",
    "prazo_anterior",
    "prazo_novo",
    "status",
    "solicitada_em",
    "solicitante_nome",
    "solicitante_email",
    "decidida_em",
    "decidida_por_nome",
    "decisao_justificativa",
)
CAMPOS_PRORROGACAO = ", ".join(CAMPOS_PRORROGACAO_TUPLA)

# As regras que a página do portal mostra ao responsável ANTES de ele pedir
# (PRD #318, história 2): contar com um recurso que não existe é pior do que
# não ter o recurso.
REGRAS = (
    "A prorrogação pode ser pedida uma única vez por manifestação.",
    "O pedido precisa ser feito antes do vencimento do prazo: depois disso o sistema recusa sozinho.",
    "A justificativa é obrigatória e vai para a Ouvidoria decidir.",
    f"O prazo novo nunca passa de {MAX_DIAS_UTEIS_PEDIDOS} dias úteis contados da entrada da manifestação.",
)


def motivo_de_recusa(caso: dict, pedido_anterior: dict | None, agora: dt.datetime) -> str | None:
    """Por que este caso não aceita um pedido de prorrogação agora.

    None significa que o pedido pode entrar. O texto devolvido é o que o
    responsável do setor lê, então ele diz a regra, não o código dela.

    A ordem importa: "já pediu" vem antes de "venceu" porque é a informação
    mais útil a quem tenta de novo, e um caso pode furar as duas."""
    if caso.get("status") != AGUARDANDO_AREA:
        return "Este caso não está aguardando a resposta do setor, então não há prazo a prorrogar."
    if pedido_anterior is not None:
        return "Esta manifestação já teve um pedido de prorrogação. A regra permite apenas um."
    bruto = caso.get("prazo_area_em")
    if not bruto:
        return "Esta manifestação não tem prazo definido, então não há o que prorrogar."
    if esta_vencido(dt.datetime.fromisoformat(str(bruto)), agora):
        return "O prazo desta manifestação já venceu. A prorrogação só vale se pedida antes do vencimento."
    return None


def carregar_pedido(supabase, manifestacao_id: str) -> dict | None:
    """O pedido de prorrogação do caso, se houver. Um por manifestação (índice
    único da migration 072), então a primeira linha é a única."""
    result = (
        supabase.table("ouvidoria_prorrogacoes")
        .select(CAMPOS_PRORROGACAO)
        .eq("manifestacao_id", manifestacao_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def resumo_para_o_portal(caso: dict, pedido: dict | None, agora: dt.datetime) -> dict:
    """O bloco de prorrogação que a página do portal do setor mostra: as
    regras, se o pedido cabe agora e, quando não cabe, por quê."""
    motivo = motivo_de_recusa(caso, pedido, agora)
    return {
        "regras": list(REGRAS),
        "max_dias_uteis": MAX_DIAS_UTEIS_PEDIDOS,
        "permitida": motivo is None,
        "motivo": motivo,
        "pedido": {campo: (pedido or {}).get(campo) for campo in CAMPOS_PRORROGACAO_TUPLA} if pedido else None,
    }


def entrada_da_manifestacao(caso: dict) -> dt.datetime | None:
    """O T0 do caso, de onde o teto de 30 dias úteis conta.

    `contato_em` é o instante real do contato (o que o ouvidor digita no
    registro manual); `data_abertura` é o fallback dos casos antigos, e ali só
    existe a data, então a contagem abre no começo do expediente daquele dia.
    None quando o caso não tem nem um nem outro, e aí não há teto a calcular."""
    bruto = caso.get("contato_em") or caso.get("data_abertura")
    if not bruto:
        return None
    texto = str(bruto)
    if len(texto) == 10:
        return dt.datetime.fromisoformat(texto).replace(hour=8, tzinfo=FUSO)
    momento = dt.datetime.fromisoformat(texto)
    return momento if momento.tzinfo else momento.replace(tzinfo=FUSO)


def registrar_movimento(
    supabase, manifestacao_id: str, *, autor_id: str | None, autor_nome: str, observacao: str
) -> None:
    """Pedido e decisão entram na trilha imutável do caso (PRD #318, história
    22). Não são transição de estado (o caso segue aguardando a área), então o
    insert é direto, no molde do movimento de abertura e do de prazo rompido.

    Melhor esforço: a trilha não pode derrubar o ato que ela registra."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": manifestacao_id,
                "estado_anterior": AGUARDANDO_AREA,
                "estado_novo": AGUARDANDO_AREA,
                "autor_id": autor_id,
                "autor_nome": autor_nome,
                "observacao": observacao,
            }
        ).execute()
    except Exception:
        logger.warning("Falha ao gravar o movimento de prorrogação da manifestação %s", manifestacao_id)
