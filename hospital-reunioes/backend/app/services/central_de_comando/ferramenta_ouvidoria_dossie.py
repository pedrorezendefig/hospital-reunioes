"""A ferramenta do caso da Ouvidoria no Conector (issue #1612, ADR 0085,
decisões 4 e 5).

Só leitura, para quem tem `diretoria_executiva` (o gate mora no
`conector_mcp`). Recebe um protocolo e devolve o que a página do caso entrega
à diretoria executiva, pelas MESMAS montagens das rotas da tela: o Dossiê
(`dossie_completo`), a linha do tempo (`linha_do_tempo_do_caso`) e o histórico
de respostas da área (`ouvidoria_respostas.historico`). Sem segundo formato:
relato integral, identificação gravada e sigilo reforçado vão como a tela os
mostra; o caso anônimo leva o que o Dossiê dele tem.

O caso apagado chega como a tela o mostra: o aviso no lugar do resumo e do
relato.

Cada chamada que devolve o caso grava `consulta_conector` em
`ouvidoria_acessos`, pelo `registrar_acesso` da tela (falha no registro não
derruba a leitura). Nada mais é escrito: nem o visto da Ouvidoria, que a
página do caso carimba, porque quem consulta pelo Claude não está trabalhando
a fila.
"""

from __future__ import annotations

import datetime as dt

from fastapi.encoders import jsonable_encoder
from httpx import HTTPError
from postgrest.exceptions import APIError

from app.services import ouvidoria_respostas

NOME = "get_ouvidoria_dossie"

# A ação do log de acesso (ADR 0085, decisão 5), ao lado do `abrir_dossie` da tela.
ACAO_DO_ACESSO = "consulta_conector"


class PedidoRecusadoError(Exception):
    """A ferramenta não responde este pedido; a mensagem vai ao Claude como
    erro de ferramenta, sem dado."""


def definicao() -> dict:
    """A entrada da ferramenta no `tools/list`."""
    return {
        "name": NOME,
        "title": "Caso da Ouvidoria",
        "description": (
            "O Dossiê de um caso da Ouvidoria do hospital pelo protocolo (AAAA-NNNN), somente leitura, como a "
            'página do caso mostra para a diretoria executiva. "dossie" traz a ficha do caso, o relato '
            "integral, a identificação que o caso gravou (quem manifestou e o Paciente do caso), o sigilo "
            "reforçado, a resposta corrente da área e os quatro marcos com os prazos. Caso anônimo não tem "
            'identificação: não deduza quem manifestou. "trilha" é a linha do tempo, do mais novo para o mais '
            'antigo, com o tempo útil entre os marcos; "respostas" são todas as respostas da área, da mais antiga '
            'para a mais nova. Caso apagado não tem relato nem identificação: "aviso_caso_apagado" diz quando '
            'e por quê. "degradado" lista o que não pôde ser lido (o calendário útil, por exemplo): sem ele, '
            "o tempo em dias úteis não está confirmado. Esta consulta fica registrada no histórico de acesso "
            "do caso. Não invente dado que não esteja no payload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "protocolo": {"type": "string", "description": "O protocolo do caso, como 2026-0123."},
            },
            "required": ["protocolo"],
            "additionalProperties": False,
        },
    }


def executar(argumentos: dict, participante: dict, supabase) -> dict:
    """O caso pelo protocolo, como a página do caso o entrega. Levanta
    `PedidoRecusadoError` para protocolo inválido ou inexistente e para falha
    de leitura do caso ou da trilha."""
    from app.routers import ouvidoria

    protocolo = argumentos.get("protocolo")
    if not isinstance(protocolo, str) or not protocolo.strip():
        raise PedidoRecusadoError("Informe o protocolo do caso, como 2026-0123.")
    protocolo = protocolo.strip()
    try:
        row = ouvidoria.ler_caso_por_protocolo(supabase, protocolo)
        if row is None:
            raise PedidoRecusadoError(f"Nenhum caso da Ouvidoria tem o protocolo {protocolo}.")
        movimentos = ouvidoria.ler_movimentos_do_caso(supabase, row["id"])
    except (APIError, HTTPError) as exc:
        raise PedidoRecusadoError("Não foi possível ler o caso agora. Tente de novo em instantes.") from exc

    dossie = ouvidoria.dossie_completo(supabase, row, ouvidoria.agora_utc())
    if dossie.get("anonimizada_em"):
        dossie = _no_lugar_do_relato(dossie)
    payload = {
        "dossie": dossie,
        "trilha": ouvidoria.linha_do_tempo_do_caso(supabase, movimentos),
        "respostas": ouvidoria_respostas.historico(supabase, row["id"]),
    }
    ouvidoria.registrar_acesso(supabase, participante, row["id"], ACAO_DO_ACESSO)
    return jsonable_encoder(payload)


def _no_lugar_do_relato(dossie: dict) -> dict:
    """O caso apagado (issue #593): o aviso ocupa o lugar do resumo e do
    relato, como na tela. O resumo do caso apagado é o marcador interno da
    Retenção, e não vai ao Claude."""
    from app.routers.ouvidoria import FUSO_HOSPITAL

    apagado_em = dt.datetime.fromisoformat(str(dossie["anonimizada_em"])).astimezone(FUSO_HOSPITAL)
    aviso = f"Este caso foi apagado em {apagado_em:%d/%m/%Y às %H:%M}."
    if dossie.get("apagamento_motivo"):
        aviso += f" Motivo: {str(dossie['apagamento_motivo']).rstrip('.')}."
    aviso += (
        " O relato, a identificação de quem manifestou, os anexos e a resposta da área não estão mais "
        "disponíveis. A ficha do caso e a linha do tempo continuam."
    )
    resto = {campo: valor for campo, valor in dossie.items() if campo not in ("resumo", "relato_integral")}
    return resto | {"aviso_caso_apagado": aviso}
