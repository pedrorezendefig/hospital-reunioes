"""A ferramenta da fila da Ouvidoria no Conector (issue #1611, ADR 0085,
decisão 3).

Só leitura, para quem tem `diretoria_executiva` (o gate mora no
`conector_mcp`). A ferramenta é casca fina sobre a leitura da fila na tela
(`routers.ouvidoria.ler_fila`): os mesmos casos (lista de trabalho, sem o
arquivo), o mesmo prazo projetado pela Tabela de prazos e pelo Calendário útil.
Prazo estourado é a marca que a fila pinta (`classificarPrazoDaManifestacao` em
`frontend/src/lib/ouvidoria/prazo.ts`): o veredito do motor, mais as guardas da
tela (caso fora do relógio e elogio não estouram; caso sem gravidade cai no
prazo de referência).

É lista, como a fila: não grava em `ouvidoria_acessos` (ADR 0085, decisão 5).
O Dossiê é a ferramenta do caso, em outra fatia.

Lista longa volta cortada em `TETO`, com o total e o aviso de que há mais,
para o Claude refinar o filtro.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

NOME = "get_ouvidoria_prazo_estourado"

# Quantos casos uma resposta traz, o mesmo teto das Pendências.
TETO = 50

# Os estados da Manifestação, como a fila os grava e mostra.
SITUACOES = (
    "novo",
    "em_classificacao",
    "aguardando_area",
    "aguardando_manifestante",
    "respondido",
    "encerrado",
)

# Os estados em que o relógio da área corre (`EM_ANDAMENTO` da tela). A pausa
# aguardando o manifestante fica de fora (issue #335).
_EM_ANDAMENTO = frozenset({"novo", "em_classificacao", "aguardando_area"})

_FUSO = ZoneInfo("America/Sao_Paulo")


class PedidoRecusadoError(Exception):
    """A ferramenta não responde este pedido; a mensagem vai ao Claude como
    erro de ferramenta, sem dado."""


def definicao() -> dict:
    """A entrada da ferramenta no `tools/list`."""
    return {
        "name": NOME,
        "title": "Casos da Ouvidoria e prazos",
        "description": (
            "A fila da Ouvidoria do hospital, somente leitura: os casos em trabalho (sem os arquivados), "
            "cada um com protocolo, setor, situação, gravidade e prazo. Filtre por \"prazoEstourado\" "
            '(verdadeiro traz só os estourados), por "setor" (parte do nome) e por "situacao" (novo, '
            "em_classificacao, aguardando_area, aguardando_manifestante, respondido, encerrado). Sem filtro, "
            "vem a fila inteira. Prazo estourado é a mesma marca vermelha da fila na tela: conta em dias úteis "
            "pela Tabela de prazos e pelo Calendário útil; caso já respondido, parado aguardando o "
            "manifestante, ou elogio nunca está estourado. \"vencimento\" é o prazo da área; caso ainda sem "
            'gravidade não tem prazo da área e é medido pelo "prazoDeReferencia". A lista vem pelo prazo, '
            f'o mais antigo primeiro; "total" é quantos atendem ao filtro e "haMais" verdadeiro quer dizer que '
            f"só os {TETO} primeiros vieram: refine o filtro para ver o resto. \"degradado\" não vazio quer "
            "dizer que parte da leitura falhou e o prazo pode não estar confirmado. Não invente casos que não "
            "estejam no payload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "prazoEstourado": {"type": "boolean", "description": "Verdadeiro: só os casos com prazo estourado."},
                "setor": {"type": "string", "description": "Parte do nome do setor."},
                "situacao": {"type": "string", "enum": list(SITUACOES), "description": "A situação do caso."},
            },
            "additionalProperties": False,
        },
    }


def executar(argumentos: dict, participante: dict, supabase) -> dict:
    """Os casos que a fila da Ouvidoria mostra a esta pessoa, com o filtro
    pedido. Levanta `PedidoRecusadoError` para argumento inválido."""
    from app.routers import ouvidoria

    estourado = argumentos.get("prazoEstourado")
    if estourado is not None and not isinstance(estourado, bool):
        raise PedidoRecusadoError('"prazoEstourado" é verdadeiro ou falso.')
    setor = argumentos.get("setor")
    if setor is not None and (not isinstance(setor, str) or not setor.strip()):
        raise PedidoRecusadoError("O setor é parte do nome, em texto.")
    situacao = argumentos.get("situacao")
    if situacao is not None and (not isinstance(situacao, str) or situacao not in SITUACOES):
        raise PedidoRecusadoError(f"Situação desconhecida: {situacao}. Use uma de: {', '.join(SITUACOES)}.")

    agora = ouvidoria.agora_utc()
    hoje = agora.astimezone(_FUSO).date()
    casos, degradado = ouvidoria.ler_fila(supabase, participante, "nao", agora)
    linhas = [row | prazo | {"_estourado": estourado_na_fila(row, prazo, hoje)} for row, prazo in casos]

    if estourado is not None:
        linhas = [r for r in linhas if r["_estourado"] is estourado]
    if setor is not None:
        trecho = setor.strip().casefold()
        linhas = [r for r in linhas if trecho in (r.get("setor") or "").casefold()]
    if situacao is not None:
        linhas = [r for r in linhas if r.get("status") == situacao]

    linhas.sort(key=lambda r: (_prazo_de_ordem(r) is None, _prazo_de_ordem(r) or "", r.get("numero") or 0))
    mostradas = linhas[:TETO]
    total = len(linhas)
    ha_mais = total > len(mostradas)
    return {
        "total": total,
        "mostrados": len(mostradas),
        "haMais": ha_mais,
        "aviso": (
            f"Há {total} casos com este filtro e vieram só os {len(mostradas)} primeiros. Refine o filtro."
            if ha_mais
            else None
        ),
        "degradado": degradado,
        "casos": [_caso(r) for r in mostradas],
    }


def estourado_na_fila(row: dict, prazo: dict, hoje: dt.date) -> bool:
    """A marca vermelha de estourado da fila (`classificarPrazoDaManifestacao`
    da tela), sobre o prazo que o motor projetou."""
    if row.get("status") not in _EM_ANDAMENTO:
        return False
    if row.get("tipo_manifestacao") == "elogio":
        return False
    if not row.get("prazo_area_em"):
        referencia = row.get("prazo_resposta")
        return bool(referencia) and dt.date.fromisoformat(str(referencia)) < hoje
    dia = dt.datetime.fromisoformat(str(row["prazo_area_em"])).astimezone(_FUSO).date()
    return bool(prazo.get("prazo_estourado")) or dia < hoje


def _prazo_de_ordem(r: dict) -> str | None:
    """O instante que ordena a lista: o prazo da área, ou o de referência."""
    if r.get("prazo_area_em"):
        return dt.datetime.fromisoformat(str(r["prazo_area_em"])).astimezone(dt.UTC).isoformat()
    return str(r["prazo_resposta"]) if r.get("prazo_resposta") else None


def _caso(r: dict) -> dict:
    return {
        "protocolo": r.get("protocolo"),
        "setor": r.get("setor"),
        "situacao": r.get("status"),
        "gravidade": r.get("gravidade"),
        "tipo": r.get("tipo_manifestacao"),
        "vencimento": r.get("vencimento_formatado"),
        "rotuloPrazo": r.get("rotulo_prazo"),
        "prazoDeReferencia": r.get("prazo_resposta"),
        "prazoEstourado": r["_estourado"],
    }
