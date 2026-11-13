"""A ferramenta de Reuniões do Conector (issue #1610, ADR 0085, decisão 3).

Só leitura, para quem tem `diretoria_executiva` (o gate mora no
`conector_mcp`). Casca fina sobre as consultas das telas de Reuniões
(`services/reunioes_consulta.py`): a mesma visibilidade e a mesma ordem da
lista de Reuniões, os mesmos Participantes vinculados do calendário. As
Pendências de cada Reunião saem da consulta da tela de Pendências
(`services/pendencias_consulta.py`) e chegam com a situação que a ferramenta de
Pendências usa, a mesma da tela.

O que a tela não mostra para a pessoa, a ferramenta também não mostra (ADR
0085, decisão 1): quem não tem papel nas Reuniões, ou é Secretária (a tela
esconde dela a Ata e as Pendências), recebe a recusa.

Lista longa volta cortada em `TETO`, com o total e o aviso de que há mais,
para o Claude refinar a busca.
"""

from __future__ import annotations

from datetime import date

from app.services.central_de_comando import ferramenta_pendencias
from app.services.pendencias_consulta import consultar_pendencias
from app.services.reunioes_consulta import consultar_reunioes, participantes_por_reuniao

NOME = "get_reunioes"

# Quantas Reuniões uma resposta traz. Cada uma vem com a Ata, então o teto é
# mais baixo que o das Pendências; acima disso o total e o aviso pedem uma
# busca mais fina.
TETO = 20

# Quantas Pendências, somadas, as Reuniões de uma resposta trazem.
TETO_DE_PENDENCIAS = 200


class PedidoRecusadoError(Exception):
    """A ferramenta não responde este pedido; a mensagem vai ao Claude como
    erro de ferramenta, sem dado."""


def definicao() -> dict:
    """A entrada da ferramenta no `tools/list`."""
    return {
        "name": NOME,
        "title": "Reuniões",
        "description": (
            "As Reuniões do hospital, somente leitura, cada uma com a Ata, os Participantes e as Pendências "
            'que saíram dela. Busque por período ("dataDe" e "dataAte", AAAA-MM-DD, pela data da Reunião) e '
            'por "termo" (procura no título, no objetivo e no resumo executivo da Ata). Sem filtro, vêm as '
            'mais recentes. "situacaoDaAta" é o estado da Reunião (PROGRAMADA, AGUARDANDO_VALIDACAO, '
            'ASSINADA, APROVADA, CANCELADA e outros); "ata" é nula quando a Reunião ainda não tem Ata. '
            'Cada Pendência traz o responsável, o prazo e a "situacao" (atrasada, pendente, em_progresso, '
            "concluida, cancelada, repactuada), a mesma da tela de Pendências; o diretor chama de meta a "
            'Pendência com prazo. A lista vem da mais recente para a mais antiga; "total" é quantas atendem '
            f'à busca e "haMais" verdadeiro quer dizer que só as {TETO} primeiras vieram: refine a busca '
            "para ver o resto. Não invente Reuniões, decisões ou Pendências que não estejam no payload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "dataDe": {"type": "string", "description": "Reuniões a partir deste dia (AAAA-MM-DD)."},
                "dataAte": {"type": "string", "description": "Reuniões até este dia (AAAA-MM-DD)."},
                "termo": {"type": "string", "description": "Palavra ou trecho a procurar."},
            },
            "additionalProperties": False,
        },
    }


def executar(argumentos: dict, participante: dict, supabase) -> dict:
    """As Reuniões que a tela mostra a esta pessoa, com a busca pedida.
    Levanta `PedidoRecusadoError` para argumento inválido ou para quem não vê
    a Ata na tela."""
    from app.dependencies import is_secretaria, reunioes_visiveis, tem_acesso_reunioes

    if is_secretaria(participante) or not tem_acesso_reunioes(participante):
        raise PedidoRecusadoError("A Ata das Reuniões não está aberta para o seu acesso.")

    data_de = _data(argumentos.get("dataDe"), "dataDe")
    data_ate = _data(argumentos.get("dataAte"), "dataAte")
    termo = _termo(argumentos.get("termo"))

    reunioes, total = consultar_reunioes(
        supabase,
        allowed_reuniao_ids=reunioes_visiveis(supabase, participante),
        data_inicio=data_de,
        data_fim=data_ate,
        termo=termo,
        limit=TETO,
    )
    ids = [r["id_reuniao"] for r in reunioes]
    participantes = participantes_por_reuniao(supabase, ids)
    # As Pendências das Reuniões desta página, pela consulta da tela de
    # Pendências: a visibilidade é a das próprias Reuniões, já filtradas acima.
    pendencias, total_de_pendencias = consultar_pendencias(
        supabase, allowed_reuniao_ids=ids, my_participante_id=None, limit=TETO_DE_PENDENCIAS
    )
    por_reuniao: dict[str, list[dict]] = {i: [] for i in ids}
    for linha in pendencias:
        por_reuniao.setdefault(linha.get("id_reuniao"), []).append(ferramenta_pendencias.serializar_pendencia(linha))

    ha_mais = total > len(reunioes)
    return {
        "total": total,
        "mostradas": len(reunioes),
        "haMais": ha_mais,
        "aviso": (
            f"Há {total} Reuniões nesta busca e vieram só as {len(reunioes)} mais recentes. Refine a busca."
            if ha_mais
            else None
        ),
        "pendenciasCortadas": total_de_pendencias > len(pendencias),
        "reunioes": [
            _reuniao(r, participantes.get(r["id_reuniao"], []), por_reuniao.get(r["id_reuniao"], [])) for r in reunioes
        ],
    }


def _data(valor: object, campo: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise PedidoRecusadoError(f'"{campo}" é uma data AAAA-MM-DD.')


def _termo(valor: object) -> str | None:
    """O termo sem o que o filtro `or` do PostgREST leria como sintaxe (vírgula,
    parêntese, ponto, curinga, aspas): só letra, número, espaço e hífen."""
    if valor is None:
        return None
    if isinstance(valor, str):
        limpo = " ".join("".join(c if c.isalnum() or c == "-" else " " for c in valor).split())
        if limpo:
            return limpo
    raise PedidoRecusadoError('"termo" é uma palavra ou trecho, em texto.')


def _reuniao(linha: dict, participantes: list[dict], pendencias: list[dict]) -> dict:
    return {
        "id": linha.get("id_reuniao"),
        "titulo": linha.get("titulo"),
        "data": linha.get("data"),
        "horaInicio": linha.get("hora_inicio"),
        "horaFim": linha.get("hora_fim"),
        "tipo": linha.get("tipo"),
        "objetivo": linha.get("objetivo"),
        "situacaoDaAta": linha.get("status_ata"),
        "ata": _ata(linha.get("json_ata")),
        "participantes": [{"nome": p["nome"], "cargo": p["cargo"]} for p in participantes],
        "pendencias": pendencias,
    }


def _ata(json_ata: object) -> dict | None:
    """O que a Ata diz: o resumo executivo, os tópicos com a decisão de cada um
    e a próxima Reunião. O quadro de ações não vai: as Pendências que nasceram
    dele vêm ao lado, com a situação de hoje."""
    if not isinstance(json_ata, dict) or not json_ata:
        return None
    topicos = json_ata.get("discussao") or []
    return {
        "resumoExecutivo": json_ata.get("resumo_executivo"),
        "topicos": [
            {"titulo": t.get("titulo"), "descricao": t.get("descricao"), "decisao": t.get("decisao")}
            for t in topicos
            if isinstance(t, dict)
        ],
        "proximaReuniao": json_ata.get("proxima_reuniao"),
    }
