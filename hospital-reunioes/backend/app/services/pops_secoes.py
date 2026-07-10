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

import json
import uuid

from app.models.pops_fluxograma import fluxograma_valido
from app.models.pops_schemas import SECOES_POP_CONTEUDO

TIPOS_SECAO: tuple[str, ...] = ("texto", "fluxograma")


def _novo_id() -> str:
    """ID de seção estável e único na Versão. Opaco de propósito (não carrega
    título nem ordem): renomear e reordenar não o afetam."""
    return uuid.uuid4().hex[:12]


def _tipo_valido(tipo) -> str:
    return tipo if tipo in TIPOS_SECAO else "texto"


def _conteudo_normalizado(tipo: str, conteudo) -> str | dict:
    """Conteúdo aceito numa seção: string sempre; na seção de fluxograma,
    também o objeto JSON da gramática restrita (ADR 0024).

    Objeto VÁLIDO persiste como objeto (o renderer próprio desenha). Objeto
    fora da gramática vira string JSON: a tela mostra o aviso de pedir a
    regeração no chat, e o turno seguinte (que ecoa o rascunho) continua
    aceito pelo endpoint, sem travar a Elaboração. String Mermaid legada
    atravessa intacta durante a transição (migração é a fatia #224)."""
    if tipo == "fluxograma" and isinstance(conteudo, dict):
        if fluxograma_valido(conteudo):
            return conteudo
        return json.dumps(conteudo, ensure_ascii=False)
    return conteudo if isinstance(conteudo, str) else ""


def secao_tem_conteudo(secao: dict) -> bool:
    """Seção com conteúdo de verdade: string não em branco, ou o objeto do
    fluxograma (ADR 0024) não vazio."""
    conteudo = secao.get("conteudo")
    if isinstance(conteudo, str):
        return bool(conteudo.strip())
    return bool(conteudo)


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
    - `tipo` fora de `texto|fluxograma` vira `texto`;
    - conteúdo da seção de fluxograma (ADR 0024): objeto JSON da gramática
      restrita quando válido; objeto inválido vira string JSON (a tela avisa);
      string legada (Mermaid) atravessa intacta durante a transição;
    - SVG do fluxograma (ADR 0017): o `svg` capturado no cliente NÃO vem do
      agente. Carrega-se o `svg` do turno anterior para a mesma seção de
      `tipo=fluxograma` SOMENTE quando o `conteudo` não mudou.
      Se o fluxo mudou, o SVG antigo cai (defasado) e o cliente re-captura.
    """
    if not isinstance(secoes_brutas, list):
        return []

    anteriores_por_id = {s["id"]: s for s in (secoes_anteriores or []) if isinstance(s, dict) and s.get("id")}
    disponiveis = set(anteriores_por_id)
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
            anterior = anteriores_por_id[sid]
        else:
            sid = _novo_id()
            anterior = None
        while sid in usados:  # blindagem contra colisão (id forjado já usado)
            sid = _novo_id()
            anterior = None
        usados.add(sid)

        tipo = _tipo_valido(bruta.get("tipo"))
        conteudo = _conteudo_normalizado(tipo, bruta.get("conteudo"))
        secao = {"id": sid, "titulo": titulo, "conteudo": conteudo, "tipo": tipo}

        svg_carregado = _svg_a_preservar(tipo, conteudo, anterior)
        if svg_carregado:
            secao["svg"] = svg_carregado

        out.append(secao)
    return out


def _svg_a_preservar(tipo: str, conteudo: str | dict, anterior: dict | None) -> str | None:
    """SVG do fluxograma a carregar do turno anterior (ADR 0017): só vale para
    `tipo=fluxograma` e só quando o conteúdo (objeto da gramática, ou a string
    Mermaid legada) não mudou, diagrama novo invalida o SVG antigo
    (re-captura no cliente)."""
    if tipo != "fluxograma" or not isinstance(anterior, dict):
        return None
    svg = anterior.get("svg")
    if not isinstance(svg, str) or not svg.strip():
        return None
    return svg if (anterior.get("conteudo") or "") == (conteudo or "") else None
