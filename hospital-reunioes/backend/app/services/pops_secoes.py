"""Estrutura dinâmica de seções do POP (issue #151, ADR 0016).

O conteúdo de uma Versão deixa de ser um JSON de chaves fixas e passa a ser uma
lista ordenada de seções `{ id, titulo, conteudo, tipo }`, com `tipo` em
`texto | fluxograma`. A Identificação (seção 1) continua derivando do POP, fora
desta lista. O `id` é estável e atribuído pelo sistema, não derivado do título
(que pode mudar) — é o que mantém o apontar-seção (⌖) e a atualização ao vivo
precisos através de renomear e reordenar.

Este módulo é a lógica de domínio pura (sem HTTP nem LLM):
- `migrar_rascunho_legado`: converte uma vez o rascunho de chaves fixas na lista
  de seções (o Fluxograma vira seção de `tipo=fluxograma`);
- `normalizar_secoes_do_agente`: valida a lista que o agente devolve a cada turno
  e reconcilia os IDs (preserva os existentes, atribui novo só ao inédito).
"""

from __future__ import annotations

import uuid

from app.models.pops_schemas import SECOES_POP_CONTEUDO

TIPOS_SECAO: tuple[str, ...] = ("texto", "fluxograma")

# Título canônico de cada chave legada — base da migração e da estrutura
# institucional que o agente propõe quando não há modelo anexado.
TITULO_POR_CHAVE: dict[str, str] = dict(SECOES_POP_CONTEUDO)


def _novo_id() -> str:
    """ID de seção estável e único na Versão. Opaco de propósito (não carrega
    título nem ordem): renomear e reordenar não o afetam."""
    return uuid.uuid4().hex[:12]


def _tipo_valido(tipo) -> str:
    return tipo if tipo in TIPOS_SECAO else "texto"


def secao_eh_legada(rascunho: dict) -> bool:
    """Rascunho legado = dict de chaves fixas (sem a chave `secoes`). O shape
    novo sempre traz `secoes` (lista)."""
    return isinstance(rascunho, dict) and "secoes" not in rascunho


def migrar_rascunho_legado(rascunho: dict | None) -> dict:
    """Converte o rascunho legado de chaves fixas na lista de seções (uma vez).

    Idempotente: um rascunho já no shape novo (`{secoes: [...]}`) passa intacto.
    Vazio ou None vira `{secoes: []}`. Cada chave conhecida com conteúdo não
    vazio vira uma seção, na ordem canônica do template; a chave `fluxograma`
    vira seção de `tipo=fluxograma`. Chave vazia não polui a lista nova.
    """
    if not rascunho or not isinstance(rascunho, dict):
        return {"secoes": []}
    if not secao_eh_legada(rascunho):
        # Já no shape novo — só garante a forma de cada seção, preservando os
        # IDs já atribuídos (migração idempotente).
        secoes = rascunho.get("secoes") if isinstance(rascunho.get("secoes"), list) else []
        return {"secoes": normalizar_secoes_do_agente(secoes, secoes)}

    secoes: list[dict] = []
    for chave, titulo in SECOES_POP_CONTEUDO:
        conteudo = rascunho.get(chave)
        if not isinstance(conteudo, str) or not conteudo.strip():
            continue
        secoes.append(
            {
                "id": _novo_id(),
                "titulo": titulo,
                "conteudo": conteudo,
                "tipo": "fluxograma" if chave == "fluxograma" else "texto",
            }
        )
    return {"secoes": secoes}


def estrutura_institucional() -> list[dict]:
    """A estrutura institucional (template das seções 2 a 11) que o agente
    propõe como ponto de partida quando não há modelo anexado. Só os títulos e
    tipos; o conteúdo nasce vazio e os IDs são atribuídos no primeiro turno."""
    return [
        {"titulo": titulo, "conteudo": "", "tipo": "fluxograma" if chave == "fluxograma" else "texto"}
        for chave, titulo in SECOES_POP_CONTEUDO
    ]


def normalizar_secoes_do_agente(
    secoes_brutas,
    secoes_anteriores: list[dict] | None,
) -> list[dict]:
    """Valida a lista que o agente devolve e reconcilia os IDs contra o turno
    anterior.

    Contrato (M1): o agente devolve a lista completa a cada turno, ecoando o
    `id` de cada seção que mantém e omitindo (ou deixando vazio) o `id` da seção
    inédita. Aqui:
    - seção que ecoa um `id` existente no turno anterior preserva esse `id`
      (sobrevive a renomear e reordenar); cada `id` anterior só pode casar uma
      vez (um `id` forjado/duplicado pelo agente não rouba o de outra seção);
    - seção sem `id` válido (inédita) recebe `id` novo, único na lista;
    - seção que existia antes e o agente não devolveu simplesmente não está na
      saída (removida);
    - seção malformada (não-dict ou sem título) é descartada;
    - `tipo` fora de `texto|fluxograma` vira `texto`.
    """
    if not isinstance(secoes_brutas, list):
        return []

    ids_anteriores = {s["id"] for s in (secoes_anteriores or []) if isinstance(s, dict) and s.get("id")}
    disponiveis = set(ids_anteriores)
    usados: set[str] = set()
    out: list[dict] = []

    for bruta in secoes_brutas:
        if not isinstance(bruta, dict):
            continue
        titulo = bruta.get("titulo")
        if not isinstance(titulo, str) or not titulo.strip():
            continue

        sid = bruta.get("id")
        if isinstance(sid, str) and sid in disponiveis:
            disponiveis.discard(sid)  # cada id anterior casa no máximo uma vez
        else:
            sid = _novo_id()
        while sid in usados:  # blindagem contra colisão (id forjado já usado)
            sid = _novo_id()
        usados.add(sid)

        conteudo = bruta.get("conteudo")
        out.append(
            {
                "id": sid,
                "titulo": titulo,
                "conteudo": conteudo if isinstance(conteudo, str) else "",
                "tipo": _tipo_valido(bruta.get("tipo")),
            }
        )
    return out
