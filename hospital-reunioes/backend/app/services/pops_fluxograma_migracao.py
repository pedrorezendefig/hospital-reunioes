"""Migração one-shot do Fluxograma legado: Mermaid para a gramática JSON (issue #224).

O prompt antigo (ADR 0017) fazia o agente emitir um subset pequeno de Mermaid
`flowchart TD`: terminais `([Texto])`, passos `[Texto]`, decisões binárias
`{Pergunta?}` com ramos `-->|Sim|` / `-->|Não|` e retornos a passos anteriores.
Este módulo converte esse subset para o objeto da gramática restrita do
ADR 0024 (`app.models.pops_fluxograma`), com fidelidade semântica: só converte
o que o layout de coluna única expressa sem mudar o sentido do procedimento.
O que estiver fora do subset levanta `MermaidInconversivelError` com motivo
legível; a migração deixa o conteúdo como estava (cai no fallback existente).

Funções puras (sem banco). O script `scripts.oneshot.migrar_fluxogramas_mermaid`
aplica sobre `pops_versoes.rascunho`, com dry-run e relatório.
"""

from __future__ import annotations

import re

from app.models.pops_fluxograma import FluxogramaInvalidoError, validar_fluxograma
from app.services.pops_secoes import migrar_rascunho_legado, secao_eh_legada


class MermaidInconversivelError(ValueError):
    """O código Mermaid está fora do subset conversível da migração."""


_RE_CABECALHO = re.compile(r"^(?:flowchart|graph)\s+(?:TD|TB)$", re.IGNORECASE)
_RE_ROTULO = re.compile(r"^\|(?P<rotulo>[^|]*)\|\s*(?P<resto>.+)$")
_RE_TERMINAL = re.compile(r"^(?P<id>\w+)\(\[(?P<texto>.+)\]\)$")
_RE_DECISAO = re.compile(r"^(?P<id>\w+)\{(?P<texto>.+)\}$")
_RE_PASSO = re.compile(r"^(?P<id>\w+)\[(?P<texto>.+)\]$")
_RE_REFERENCIA = re.compile(r"^(?P<id>\w+)$")


def _limpar_texto(texto: str) -> str:
    """Texto do nó: sem aspas de contorno, sem `<br/>` e com espaços colapsados."""
    t = re.sub(r"<br\s*/?>", " ", texto.strip(), flags=re.IGNORECASE)
    t = t.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"':
        t = t[1:-1]
    return re.sub(r"\s+", " ", t).strip()


def _registrar_no(nos: dict[str, dict], nid: str, tipo: str, texto: str) -> None:
    existente = nos.get(nid)
    if existente is None or existente["tipo"] is None:
        nos[nid] = {"tipo": tipo, "texto": texto}
        return
    if existente["tipo"] != tipo or existente["texto"] != texto:
        raise MermaidInconversivelError(f"nó '{nid}' redefinido com forma ou texto diferente")


def _no_do_token(token: str, nos: dict[str, dict]) -> str:
    token = token.strip()
    for regex, tipo in ((_RE_TERMINAL, "terminal"), (_RE_DECISAO, "decisao"), (_RE_PASSO, "passo")):
        m = regex.match(token)
        if m:
            texto = _limpar_texto(m.group("texto"))
            if not texto:
                raise MermaidInconversivelError(f"nó '{m.group('id')}' sem texto")
            _registrar_no(nos, m.group("id"), tipo, texto)
            return m.group("id")
    m = _RE_REFERENCIA.match(token)
    if m:
        nos.setdefault(m.group("id"), {"tipo": None, "texto": ""})
        return m.group("id")
    raise MermaidInconversivelError(f"trecho fora do subset conversível: '{token}'")


def _analisar(codigo: str) -> tuple[dict[str, dict], list[tuple[str, str, str | None]]]:
    """Lê o código linha a linha e devolve (nós, arestas). Aresta = (origem,
    destino, rótulo ou None). Linha fora do subset é inconversível."""
    linhas = [linha.strip().rstrip(";").strip() for linha in codigo.strip().splitlines()]
    linhas = [linha for linha in linhas if linha and not linha.startswith("%%")]
    if not linhas or not _RE_CABECALHO.match(linhas[0]):
        raise MermaidInconversivelError("o código não começa com 'flowchart TD'")

    nos: dict[str, dict] = {}
    arestas: list[tuple[str, str, str | None]] = []
    for linha in linhas[1:]:
        partes = linha.split("-->")
        origem = _no_do_token(partes[0], nos)
        for parte in partes[1:]:
            parte = parte.strip()
            rotulo: str | None = None
            m = _RE_ROTULO.match(parte)
            if m:
                rotulo = _limpar_texto(m.group("rotulo"))
                if not rotulo:
                    raise MermaidInconversivelError(f"ramo com rótulo vazio saindo de '{origem}'")
                parte = m.group("resto")
            destino = _no_do_token(parte, nos)
            arestas.append((origem, destino, rotulo))
            origem = destino

    sem_forma = [nid for nid, no in nos.items() if no["tipo"] is None]
    if sem_forma:
        raise MermaidInconversivelError(f"nó '{sem_forma[0]}' sem definição de forma (passo, decisão ou terminal)")
    return nos, arestas


def _primeiro_no(
    nos: dict[str, dict],
    saidas: dict[str, list[tuple[str, str | None, int]]],
    entradas: dict[str, int],
    consumidas: set[int],
) -> str:
    """O nó que abre a coluna principal: o destino do terminal de Início, ou o
    único nó sem entradas quando não há terminal de partida."""
    terminais_partida = [nid for nid, no in nos.items() if no["tipo"] == "terminal" and saidas.get(nid)]
    terminais_partida = [nid for nid in terminais_partida if entradas.get(nid, 0) == 0]
    if len(terminais_partida) > 1:
        raise MermaidInconversivelError("mais de um terminal de partida")
    if terminais_partida:
        partida = saidas[terminais_partida[0]]
        if len(partida) != 1 or partida[0][1] is not None:
            raise MermaidInconversivelError("o terminal de Início deve ter uma única saída sem rótulo")
        consumidas.add(partida[0][2])
        return partida[0][0]

    candidatos = [nid for nid, no in nos.items() if no["tipo"] != "terminal" and entradas.get(nid, 0) == 0]
    if len(candidatos) != 1:
        raise MermaidInconversivelError("não há um ponto de partida único no fluxo")
    return candidatos[0]


def _tentar_desvio(
    candidato: str,
    outro: str,
    nos: dict[str, dict],
    saidas: dict[str, list[tuple[str, str | None, int]]],
    em_coluna: set[str],
) -> dict | None:
    """O ramo cabe como card lateral de desvio? Sim quando é um passo fora da
    coluna com uma única saída sem rótulo que retorna a um nó já na coluna
    (`retorna_para`) ou reentra exatamente no alvo do outro ramo (segue o
    fluxo). Devolve {retorna_para, aresta} ou None."""
    no = nos.get(candidato)
    if no is None or no["tipo"] != "passo" or candidato in em_coluna:
        return None
    arestas_do_candidato = saidas.get(candidato, [])
    if len(arestas_do_candidato) != 1:
        return None
    destino, rotulo, idx = arestas_do_candidato[0]
    if rotulo is not None:
        return None
    if destino in em_coluna:
        return {"retorna_para": destino, "aresta": idx}
    if destino == outro:
        return {"retorna_para": None, "aresta": idx}
    return None


def converter_mermaid_para_fluxograma(codigo: str) -> dict:
    """Converte o subset Mermaid do prompt antigo no objeto da gramática
    restrita (ADR 0024). Levanta `MermaidInconversivelError` com motivo legível
    quando o código está fora do subset (nada é convertido "mais ou menos":
    a semântica do procedimento não muda)."""
    if not isinstance(codigo, str) or not codigo.strip():
        raise MermaidInconversivelError("conteúdo vazio")
    nos, arestas = _analisar(codigo)

    saidas: dict[str, list[tuple[str, str | None, int]]] = {}
    entradas: dict[str, int] = {}
    for idx, (origem, destino, rotulo) in enumerate(arestas):
        saidas.setdefault(origem, []).append((destino, rotulo, idx))
        entradas[destino] = entradas.get(destino, 0) + 1

    consumidas: set[int] = set()
    atual = _primeiro_no(nos, saidas, entradas, consumidas)

    coluna: list[str] = []
    em_coluna: set[str] = set()
    usados_como_desvio: set[str] = set()
    ramos_por_decisao: dict[str, list[dict]] = {}

    while True:
        no = nos[atual]
        if no["tipo"] == "terminal":
            break  # Fim explícito: na gramática nova ele é implícito.
        if atual in em_coluna or atual in usados_como_desvio:
            raise MermaidInconversivelError(f"o fluxo volta ao nó '{atual}' sem card de desvio")
        coluna.append(atual)
        em_coluna.add(atual)

        arestas_do_no = saidas.get(atual, [])
        if no["tipo"] == "passo":
            if not arestas_do_no:
                break  # último passo: Fim implícito.
            if len(arestas_do_no) != 1 or arestas_do_no[0][1] is not None:
                raise MermaidInconversivelError(f"o passo '{atual}' tem mais de uma saída ou saída rotulada")
            destino, _rotulo, idx = arestas_do_no[0]
            consumidas.add(idx)
            atual = destino
            continue

        # Decisão: exatamente 2 ramos rotulados nesta fatia (3+ ficam na #222).
        if len(arestas_do_no) != 2:
            raise MermaidInconversivelError(
                f"a decisão '{atual}' tem {len(arestas_do_no)} saída(s); o subset é a decisão binária"
            )
        if any(rotulo is None for _destino, rotulo, _idx in arestas_do_no):
            raise MermaidInconversivelError(f"a decisão '{atual}' tem ramo sem rótulo")
        (dest_a, rot_a, idx_a), (dest_b, rot_b, idx_b) = arestas_do_no
        consumidas.update((idx_a, idx_b))

        if dest_a == dest_b:
            # Os dois ramos convergem no mesmo nó: nenhum desvia.
            ramos_por_decisao[atual] = [{"rotulo": rot_a}, {"rotulo": rot_b}]
            atual = dest_a
            continue

        desvio_a = _tentar_desvio(dest_a, dest_b, nos, saidas, em_coluna)
        desvio_b = _tentar_desvio(dest_b, dest_a, nos, saidas, em_coluna)
        if desvio_a and desvio_b:
            raise MermaidInconversivelError(f"os dois ramos da decisão '{atual}' desviam; um deve seguir o fluxo")
        if not desvio_a and not desvio_b:
            raise MermaidInconversivelError(
                f"os ramos da decisão '{atual}' seguem caminhos independentes, fora da coluna única da gramática"
            )
        if desvio_a:
            lateral, rot_lateral, reto, desvio = dest_a, rot_a, dest_b, desvio_a
            primeiro_ramo_desvia = True
        else:
            lateral, rot_lateral, reto, desvio = dest_b, rot_b, dest_a, desvio_b
            primeiro_ramo_desvia = False

        card = {"texto": nos[lateral]["texto"]}
        if desvio["retorna_para"] is not None:
            card["retorna_para"] = desvio["retorna_para"]
        ramo_lateral = {"rotulo": rot_lateral, "desvio": card}
        ramo_reto = {"rotulo": rot_a if not primeiro_ramo_desvia else rot_b}
        ramos_por_decisao[atual] = [ramo_lateral, ramo_reto] if primeiro_ramo_desvia else [ramo_reto, ramo_lateral]
        consumidas.add(desvio["aresta"])
        usados_como_desvio.add(lateral)
        atual = reto

    if not coluna:
        raise MermaidInconversivelError("o fluxo não tem nenhum passo ou decisão")

    nao_percorridas = [arestas[i] for i in range(len(arestas)) if i not in consumidas]
    if nao_percorridas:
        origem, destino, _rotulo = nao_percorridas[0]
        raise MermaidInconversivelError(f"parte do fluxo não foi percorrida (ex.: '{origem} --> {destino}')")
    fora_do_fluxo = [
        nid
        for nid, no in nos.items()
        if no["tipo"] != "terminal" and nid not in em_coluna and nid not in usados_como_desvio
    ]
    if fora_do_fluxo:
        raise MermaidInconversivelError(f"nó fora do fluxo principal: '{fora_do_fluxo[0]}'")

    estrutura = {"nos": []}
    for nid in coluna:
        no = nos[nid]
        if no["tipo"] == "decisao":
            estrutura["nos"].append(
                {"id": nid, "tipo": "decisao", "texto": no["texto"], "ramos": ramos_por_decisao[nid]}
            )
        else:
            estrutura["nos"].append({"id": nid, "tipo": "passo", "texto": no["texto"]})

    try:
        validar_fluxograma(estrutura)
    except FluxogramaInvalidoError as e:
        raise MermaidInconversivelError(f"o resultado não obedece à gramática: {e}") from e
    return estrutura


def migrar_rascunho_fluxogramas(rascunho: dict) -> tuple[dict, list[dict]]:
    """Converte as seções de fluxograma com Mermaid legado de um rascunho.

    Devolve (rascunho novo, relatórios por seção de fluxograma). Cada relatório
    tem `secao_id`, `titulo`, `status` (convertida | pulada | inconversivel) e
    `motivo`. Não muta o rascunho de entrada; o SVG persistido e as demais
    chaves da seção atravessam intactos (o PDF assinado não muda um byte).
    Rascunho legado de chaves fixas (anterior ao ADR 0016) primeiro migra de
    shape pela função existente `migrar_rascunho_legado`.
    """
    base = migrar_rascunho_legado(rascunho) if secao_eh_legada(rascunho) else rascunho
    secoes = base.get("secoes") if isinstance(base.get("secoes"), list) else []

    relatorios: list[dict] = []
    secoes_novas: list = []
    for secao in secoes:
        if not isinstance(secao, dict) or secao.get("tipo") != "fluxograma":
            secoes_novas.append(secao)
            continue

        conteudo = secao.get("conteudo")
        relatorio = {"secao_id": secao.get("id"), "titulo": secao.get("titulo")}
        if isinstance(conteudo, dict):
            relatorio |= {"status": "pulada", "motivo": "já é objeto da gramática (ADR 0024)"}
            secoes_novas.append(secao)
        elif not isinstance(conteudo, str) or not conteudo.strip():
            relatorio |= {"status": "pulada", "motivo": "seção sem conteúdo"}
            secoes_novas.append(secao)
        elif conteudo.lstrip().startswith("{"):
            relatorio |= {"status": "pulada", "motivo": "string JSON (objeto inválido, fica no aviso de regeração)"}
            secoes_novas.append(secao)
        else:
            try:
                objeto = converter_mermaid_para_fluxograma(conteudo)
                relatorio |= {"status": "convertida", "motivo": "subset Mermaid convertido"}
                secoes_novas.append({**secao, "conteudo": objeto})
            except MermaidInconversivelError as e:
                relatorio |= {"status": "inconversivel", "motivo": str(e)}
                secoes_novas.append(secao)
        relatorios.append(relatorio)

    return {**base, "secoes": secoes_novas}, relatorios
