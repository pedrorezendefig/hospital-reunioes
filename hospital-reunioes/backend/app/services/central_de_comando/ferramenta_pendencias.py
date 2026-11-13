"""A ferramenta de Pendências do Conector (issue #1609, ADR 0085, decisão 3).

Só leitura, para quem tem `diretoria_executiva` (o gate mora no
`conector_mcp`). A ferramenta é casca fina sobre a consulta da tela de
Pendências (`services/pendencias_consulta.py`): a mesma visibilidade, o mesmo
filtro de situação, responsável e prazo, a mesma ordem. Atrasada é o status
`ATRASADO`, o que a tela mostra como atrasada; nada aqui recalcula prazo.

O que a tela não mostra para a pessoa, a ferramenta também não mostra (ADR
0085, decisão 1): a visibilidade é a das Reuniões dela, e quem não abre a tela
de Pendências (secretária, ou sem papel nas Reuniões) recebe a recusa.

Lista longa volta cortada em `TETO`, com o total e o aviso de que há mais,
para o Claude refinar o filtro.
"""

from __future__ import annotations

from datetime import date

from app.services.pendencias_consulta import consultar_pendencias

NOME = "get_pendencias"

# Quantas pendências uma resposta traz. Cabe na conversa do Claude e sobra para
# a pergunta comum ("o que está atrasado de fulano"); acima disso o total e o
# aviso pedem um filtro mais fino.
TETO = 50

# A situação como o diretor diz, e o status que a tela grava e mostra.
SITUACOES = {
    "atrasada": "ATRASADO",
    "pendente": "PENDENTE",
    "em_progresso": "EM_PROGRESSO",
    "concluida": "CONCLUIDO",
    "cancelada": "CANCELADO",
    "repactuada": "REPACTUADA",
}
_SITUACAO_DO_STATUS = {status: situacao for situacao, status in SITUACOES.items()}


class PedidoRecusadoError(Exception):
    """A ferramenta não responde este pedido; a mensagem vai ao Claude como
    erro de ferramenta, sem dado."""


def definicao() -> dict:
    """A entrada da ferramenta no `tools/list`."""
    return {
        "name": NOME,
        "title": "Pendências",
        "description": (
            "As Pendências das Reuniões do hospital, somente leitura: cada uma é uma ação atribuída a um "
            "responsável, com prazo, que nasce da Ata. O diretor chama de meta a Pendência com prazo. "
            'Filtre por "situacao" (atrasada, pendente, em_progresso, concluida, cancelada, repactuada), '
            'por "responsavel" (parte do nome) e por prazo ("prazoDe" e "prazoAte", AAAA-MM-DD). Sem filtro, '
            "vêm todas. Atrasada é a mesma marca da tela de Pendências: a pendência pendente cujo prazo "
            'venceu. A lista vem por prazo, a mais antiga primeiro; "total" é quantas atendem ao filtro e '
            f'"haMais" verdadeiro quer dizer que só as {TETO} primeiras vieram: refine o filtro para ver o '
            'resto. "repactuada" é a pendência com prazo apagado, à espera da data nova. Não invente '
            "pendências que não estejam no payload."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "situacao": {"type": "string", "enum": list(SITUACOES), "description": "A situação da pendência."},
                "responsavel": {"type": "string", "description": "Parte do nome do responsável."},
                "prazoDe": {"type": "string", "description": "Prazo a partir deste dia (AAAA-MM-DD)."},
                "prazoAte": {"type": "string", "description": "Prazo até este dia (AAAA-MM-DD)."},
            },
            "additionalProperties": False,
        },
    }


def executar(argumentos: dict, participante: dict, supabase) -> dict:
    """As pendências que a tela de Pendências mostra a esta pessoa, com o
    filtro pedido. Levanta `PedidoRecusadoError` para argumento inválido ou para
    quem não abre a tela."""
    from app.dependencies import is_secretaria, reunioes_visiveis, tem_acesso_reunioes

    if is_secretaria(participante) or not tem_acesso_reunioes(participante):
        raise PedidoRecusadoError("A tela de Pendências não está aberta para o seu acesso.")

    situacao = argumentos.get("situacao")
    if situacao is not None and (not isinstance(situacao, str) or situacao not in SITUACOES):
        raise PedidoRecusadoError(f"Situação desconhecida: {situacao}. Use uma de: {', '.join(SITUACOES)}.")
    prazo_de = _data(argumentos.get("prazoDe"), "prazoDe")
    prazo_ate = _data(argumentos.get("prazoAte"), "prazoAte")

    responsaveis = None
    nome = argumentos.get("responsavel")
    if nome is not None:
        if not isinstance(nome, str) or not nome.strip():
            raise PedidoRecusadoError("O responsável é parte do nome, em texto.")
        responsaveis = _ids_pelo_nome(supabase, nome)
        if not responsaveis:
            return _payload([], 0)

    linhas, total = consultar_pendencias(
        supabase,
        allowed_reuniao_ids=reunioes_visiveis(supabase, participante),
        my_participante_id=participante.get("id"),
        status=SITUACOES.get(situacao) if situacao else None,
        responsaveis=responsaveis,
        prazo_de=prazo_de,
        prazo_ate=prazo_ate,
        limit=TETO,
    )
    return _payload(linhas, total)


def _data(valor: object, campo: str) -> date | None:
    if valor is None:
        return None
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor)
        except ValueError:
            pass
    raise PedidoRecusadoError(f'"{campo}" é uma data AAAA-MM-DD.')


def _ids_pelo_nome(supabase, nome: str) -> list[str]:
    """Os participantes cujo nome contém o trecho pedido. O filtro da tela é
    por id; o diretor fala o nome."""
    trecho = nome.strip().replace("%", "").replace("_", " ")
    resultado = supabase.table("participantes").select("id").ilike("nome_completo", f"%{trecho}%").execute()
    return [linha["id"] for linha in (resultado.data or [])]


def _payload(linhas: list[dict], total: int) -> dict:
    ha_mais = total > len(linhas)
    return {
        "total": total,
        "mostradas": len(linhas),
        "haMais": ha_mais,
        "aviso": (
            f"Há {total} pendências com este filtro e vieram só as {len(linhas)} primeiras. Refine o filtro."
            if ha_mais
            else None
        ),
        "pendencias": [serializar_pendencia(linha) for linha in linhas],
    }


def serializar_pendencia(linha: dict) -> dict:
    """Uma pendência para o Claude, com a situação da tela. A ferramenta de
    Reuniões (#1610) serializa as pendências de cada Reunião por aqui."""
    status = linha.get("status")
    return {
        "id": linha.get("id_acao"),
        "descricao": linha.get("descricao_acao"),
        "responsavel": linha.get("responsavel_nome"),
        "coResponsavel": linha.get("co_responsavel_nome"),
        "prazo": linha.get("prazo"),
        "situacao": _SITUACAO_DO_STATUS.get(status, status),
        "atrasada": status == "ATRASADO",
        "metaEntregavel": linha.get("meta_entregavel"),
        "reuniao": linha.get("id_reuniao"),
    }
