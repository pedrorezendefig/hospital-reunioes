#!/usr/bin/env python3
"""Parse dos snapshots de área em estrutura pro front (visual-first).

O corpo markdown de cada doc de docs/spec/snapshots/ vira `dados` no payload:
a SPA desenha capas interativas (explorador de rotas, timeline de migrations,
diagrama de contexto, árvore anotada, fichas de tabela) sem parsear markdown.

Mesmo contrato do diagramas.py: parse nunca quebra. Qualquer erro degrada para
`None` e a SPA mantém o markdown renderizado de sempre.
"""

from __future__ import annotations

import re

_CELULA_CODE = re.compile(r"`([^`]*)`")


def _limpa(cel: str) -> str:
    """Célula de tabela markdown → texto puro (sem backticks, sem —)."""
    cel = cel.strip()
    m = _CELULA_CODE.fullmatch(cel)
    if m:
        cel = m.group(1)
    return "" if cel in ("—", "-", "") else cel


def _linhas_tabela(bloco: str) -> list[list[str]]:
    """Linhas `| a | b |` de um trecho markdown, sem cabeçalho nem separador."""
    linhas = []
    for linha in bloco.splitlines():
        linha = linha.strip()
        if not linha.startswith("|"):
            continue
        celulas = [c.strip() for c in linha.strip("|").split("|")]
        if celulas and set(celulas[0]) <= {"-", ":", " "} and len(celulas[0]) >= 3:
            continue  # separador |---|---|
        linhas.append(celulas)
    return linhas[1:] if linhas else []  # descarta o cabeçalho


def _secoes(body_md: str) -> list[tuple[str, str]]:
    """Pares (título do ##, corpo até o próximo ##)."""
    partes = re.split(r"(?m)^## ", body_md)
    out = []
    for parte in partes[1:]:
        titulo, _, corpo = parte.partition("\n")
        out.append((titulo.strip(), corpo))
    return out


# ---------- ENTIDADES: ficha completa por tabela ----------

_ORIGEM = re.compile(r"> Origem: `([^`]+)`(?:\s*\(alterada em: ([^)]*)\))?")
_INDEX = re.compile(r"- `([^`]+)` em `([^`]*)`(?: \(de `([^`]+)`\))?")


def parse_entidades(body_md: str) -> dict | None:
    tabelas = []
    for titulo, corpo in _secoes(body_md):
        nome = titulo.strip()
        if not re.fullmatch(r"\w+", nome):
            continue
        m = _ORIGEM.search(corpo)
        origem = m.group(1) if m else None
        alteradas = [a.strip() for a in (m.group(2) or "").split(",") if a.strip()] if m else []
        colunas = []
        for cel in _linhas_tabela(corpo):
            if len(cel) < 5:
                continue
            campo, tipo, cons, default, fk = (_limpa(c) for c in cel[:5])
            if not campo:
                continue
            colunas.append(
                {
                    "nome": campo,
                    "tipo": tipo,
                    "pk": "PK" in cons,
                    "nn": "NOT NULL" in cons,
                    "unique": "UNIQUE" in cons,
                    "default": default or None,
                    "fk_ref": fk or None,
                }
            )
        indexes = [{"nome": i.group(1), "campos": i.group(2), "de": i.group(3)} for i in _INDEX.finditer(corpo)]
        if colunas:
            tabelas.append(
                {"nome": nome, "origem": origem, "alteradas": alteradas, "colunas": colunas, "indexes": indexes}
            )
    return {"tabelas": tabelas} if tabelas else None


# ---------- ROTAS: endpoints estruturados ----------

_ROTAS_TITULO = re.compile(r"^(\S+)\s*\(`([^`]+)`\)$")


def parse_rotas(body_md: str) -> dict | None:
    grupos = []
    for titulo, corpo in _secoes(body_md):
        m = _ROTAS_TITULO.match(titulo)
        if not m:
            continue
        rotas = []
        for cel in _linhas_tabela(corpo):
            if len(cel) < 4:
                continue
            metodo, rota, desc, auth = cel[0].strip(), _limpa(cel[1]), cel[2].strip(), cel[3].strip()
            if not metodo or not rota:
                continue
            rotas.append({"metodo": metodo, "rota": rota, "desc": desc, "auth": "✅" in auth})
        if rotas:
            grupos.append({"grupo": m.group(1), "arquivo": m.group(2), "rotas": rotas})
    return {"grupos": grupos} if grupos else None


# ---------- MIGRATIONS: linha do tempo ----------


def parse_migrations(body_md: str) -> dict | None:
    migs = []
    for cel in _linhas_tabela(body_md):
        if len(cel) < 7:
            continue
        try:
            n = int(cel[0])
            c, a, i, d = (int(x) for x in cel[3:7])
        except ValueError:
            continue
        migs.append(
            {
                "n": n,
                "arquivo": _limpa(cel[1]),
                "resumo": cel[2].strip(),
                "criadas": c,
                "alteradas": a,
                "indexes": i,
                "drops": d,
            }
        )
    return {"migrations": migs} if migs else None


# ---------- INTEGRACOES: serviços externos ----------

_CAMPO_NEGRITO = re.compile(r"\*\*([^*]+):\*\*\s*(.*)")


def parse_integracoes(body_md: str) -> dict | None:
    servicos = []
    for titulo, corpo in _secoes(body_md):
        campos = {}
        for linha in corpo.splitlines():
            m = _CAMPO_NEGRITO.match(linha.strip())
            if m:
                campos[m.group(1).strip().lower()] = m.group(2).strip()
        if "pra que serve" not in campos:
            continue
        servicos.append(
            {
                "nome": titulo.strip(),
                "papel": campos.get("pra que serve", ""),
                "onde": [c for c in _CELULA_CODE.findall(campos.get("onde aparece no código", ""))],
                "secret": _limpa(campos.get("secret/env primária", "")),
                "relacionadas": [c for c in _CELULA_CODE.findall(campos.get("variáveis relacionadas", ""))],
            }
        )
    return {"servicos": servicos} if servicos else None


# ---------- ESTRUTURA: árvore de pastas anotada ----------

_GALHO = re.compile(r"^((?:[│ ]\s{3})*)(?:[├└]──\s*)?(\S+)\s*(?:#\s*(.*))?$")
_LOCALIZACAO = re.compile(r"Localização: (.+)")


def parse_estrutura(body_md: str) -> dict | None:
    secoes = []
    for titulo, corpo in _secoes(body_md):
        m = _LOCALIZACAO.search(corpo)
        fences = re.findall(r"```\n(.*?)```", corpo, re.S)
        if not fences:
            continue
        nos = []
        for linha in fences[0].splitlines():
            if not linha.strip():
                continue
            g = _GALHO.match(linha)
            if not g:
                continue
            prefixo, nome, comentario = g.groups()
            nivel = 0 if "──" not in linha else 1 + len(prefixo) // 4
            nos.append(
                {"nome": nome, "nivel": nivel, "dir": nome.endswith("/"), "comentario": (comentario or "").strip()}
            )
        if nos:
            secoes.append({"titulo": titulo.strip(), "local": _limpa(m.group(1)) if m else "", "nos": nos})
    return {"secoes": secoes} if secoes else None


# ---------- FLUXOGRAMAS: explicação leiga por estado ----------

_ESTADO_EXP = re.compile(r"- \*\*(\w+)\*\*\s*[—–-]+\s*(.+)")


def parse_fluxogramas(body_md: str) -> dict | None:
    estados = {}
    for m in _ESTADO_EXP.finditer(body_md):
        estados.setdefault(m.group(1), m.group(2).strip())
    return {"estados": estados} if estados else None


# ---------- despacho por doc + merge ER ----------

PARSERS = {
    "ENTIDADES": parse_entidades,
    "ROTAS": parse_rotas,
    "MIGRATIONS": parse_migrations,
    "INTEGRACOES": parse_integracoes,
    "ESTRUTURA": parse_estrutura,
    "FLUXOGRAMAS": parse_fluxogramas,
}


def parse_area(name: str, body_md: str) -> dict | None:
    fn = PARSERS.get(name)
    if not fn:
        return None
    try:
        return fn(body_md or "")
    except Exception:
        return None  # degrada pro markdown renderizado, nunca quebra o payload


def fundir_colunas_no_er(docs: list[dict]) -> None:
    """Colunas completas do ENTIDADES no ER do SCHEMA (resolve o "+N extras").

    O erDiagram do snapshot trunca as colunas; a ficha completa vive no
    ENTIDADES.md. Tabela com ficha ganha a lista inteira (com NOT NULL,
    default e destino da FK) e extras=0; sem ficha, fica como veio.
    """
    entidades = next((d for d in docs if d["name"] == "ENTIDADES"), None)
    schema = next((d for d in docs if d["name"] == "SCHEMA"), None)
    dados = entidades and entidades.get("dados")
    if not dados or not schema:
        return
    fichas = {t["nome"]: t for t in dados["tabelas"]}
    for diag in schema.get("diagramas") or []:
        if diag.get("tipo") != "er":
            continue
        for tab in diag.get("tabelas") or []:
            ficha = fichas.get(tab["nome"])
            if not ficha:
                continue
            tab["colunas"] = [
                {
                    "nome": c["nome"],
                    "tipo": c["tipo"],
                    "pk": c["pk"],
                    "fk": bool(c["fk_ref"]),
                    "nn": c["nn"],
                    "default": c["default"],
                    "fk_ref": c["fk_ref"],
                }
                for c in ficha["colunas"]
            ]
            tab["extras"] = 0
