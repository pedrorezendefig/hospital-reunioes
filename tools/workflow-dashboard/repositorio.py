#!/usr/bin/env python3
"""Aba Repositório do painel (issue #596): árvore do git com resumos lidos da fonte.

Só o que o git conhece entra (`git ls-files -co --exclude-standard`): `.env`,
`tokens/.env` e `local/` nunca aparecem nem abrem. Nenhum resumo é escrito à
mão: pasta lê a tabela do README.md da raiz; arquivo lê frontmatter, docstring,
<title> ou título mais primeiro parágrafo. Sem nada, "sem resumo".
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SEM_RESUMO = "sem resumo"


def _ls_files(root: Path) -> list[str]:
    p = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=20,
    )
    if p.returncode != 0:
        return []
    return [linha for linha in p.stdout.splitlines() if linha.strip()]


def _limpa(cell: str) -> str:
    return re.sub(r"[*`]", "", cell).strip()


def _tabelas_do_readme(readme: str) -> dict[str, dict]:
    """Uma entrada por caminho citado na primeira coluna das tabelas do README.

    O título da seção (`## \\`docs/\\``) dá o prefixo das linhas abaixo dele:
    `adr/` sob `docs/` vira `docs/adr`. Tabela de 5 colunas (o que é, por quê,
    o que tem, para quê) e de 3 colunas (por quê, quando abrir) entram do mesmo
    jeito: primeira célula explica, última diz quando abrir.
    """
    out: dict[str, dict] = {}
    prefixo = ""
    for line in readme.splitlines():
        h = re.match(r"^#+\s+(.*)$", line)
        if h:
            m = re.search(r"`([^`]+?)/`", h.group(1))
            prefixo = m.group(1).strip("/") + "/" if m else ""
            continue
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            len(cells) < 3
            or set(cells[0]) <= {"-", ":", " "}
            or not cells[0].startswith("`")
        ):
            continue
        path = _limpa(cells[0]).rstrip("/")
        key = (prefixo + path) if not path.startswith(prefixo) else path
        out[key] = {
            "o_que_e": _limpa(cells[1]) or SEM_RESUMO,
            "por_que": _limpa(cells[2]) if len(cells) > 3 else "",
            "o_que_tem": _limpa(cells[3]) if len(cells) > 4 else "",
            "para_que": _limpa(cells[-1]),
        }
    return out


def resumo_pasta(readme: str, path: str) -> dict:
    """Linha da tabela do README cujo primeiro campo casa com o caminho."""
    return _tabelas_do_readme(readme).get(path.rstrip("/")) or {
        "o_que_e": SEM_RESUMO,
        "por_que": "",
        "o_que_tem": "",
        "para_que": "",
    }


_FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
_CABECA_BYTES = 4096  # o resumo mora no começo do arquivo; o resto não se lê na coleta


def _primeira_frase(s: str) -> str:
    s = " ".join(s.split())
    m = re.match(r"(.+?[.!?])(\s|$)", s)
    return (m.group(1) if m else s).strip()


def resumo_arquivo(path: str, texto: str) -> str:
    """Resumo lido da fonte, nesta ordem: `description` do frontmatter, docstring
    da primeira linha (.py), <title> (.html), título mais primeiro parágrafo (.md).
    Nunca inventa: sem nada, "sem resumo"."""
    nome = path.rsplit("/", 1)[-1].lower()
    fm = _FRONTMATTER.match(texto)
    if fm:
        d = re.search(r"(?m)^description:\s*(.+?)\s*$", fm.group(1))
        if d:
            return _limpa(d.group(1))
        texto = texto[fm.end() :]
    if nome.endswith(".py"):
        m = re.match(
            r'\s*(?:#![^\n]*\n)?(?:#[^\n]*\n|[ \t]*\n)*(?:r|u)?"""([^\n]+?)(?:"""|\n)',
            texto,
        )
        return _primeira_frase(m.group(1)) if m else SEM_RESUMO
    if nome.endswith((".html", ".htm")):
        m = re.search(r"<title>(.*?)</title>", texto, re.S | re.I)
        return _limpa(m.group(1)) if m else SEM_RESUMO
    if nome.endswith(".md"):
        t = re.search(r"(?m)^#\s+(.+?)\s*$", texto)
        if not t:
            return SEM_RESUMO
        resto = texto[t.end() :]
        par = ""
        for line in resto.splitlines():
            s = line.strip()
            if not s or s.startswith(("#", "<!--", "|", "```", ">", "---")):
                if par:
                    break
                continue
            par += (" " if par else "") + s
        titulo = _limpa(t.group(1))
        return f"{titulo}. {_primeira_frase(_limpa(par))}" if par else titulo
    return SEM_RESUMO


_VERCEL = re.compile(r"https://[\w.-]+\.vercel\.app(?:/[\w./-]*)?")


def link_vercel(texto: str, readme_da_pasta: str) -> str | None:
    """URL `*.vercel.app` escrita no próprio arquivo ou no README da pasta; senão None."""
    for fonte in (texto, readme_da_pasta):
        m = _VERCEL.search(fonte or "")
        if m:
            return m.group(0).rstrip("./")
    return None


TETO_BYTES = 512 * 1024  # acima disso a aba mostra só o aviso e o link do GitHub


def _tipo(nome: str) -> str:
    n = nome.lower()
    if n.endswith(".md"):
        return "markdown"
    if n.endswith((".html", ".htm")):
        return "html"
    return "texto"


def ler_arquivo(root: Path, rel: str) -> dict | None:
    """Conteúdo de um arquivo que o git conhece. Qualquer outro caminho (`..`,
    absoluto, git-ignored, symlink para fora do repo) devolve None."""
    if not rel or rel.startswith(("/", "~")) or ".." in rel.split("/"):
        return None
    if rel not in set(_ls_files(root)):
        return None
    alvo = root / rel
    try:
        alvo.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if alvo.is_symlink() or not alvo.is_file():
        return None
    tamanho = alvo.stat().st_size
    pasta = rel.rsplit("/", 1)[0] if "/" in rel else ""
    readme_pasta = _cabeca(root, f"{pasta}/README.md") if pasta else ""
    base = {**_resumo_do_arquivo(root, rel, readme_pasta), "bytes": tamanho}
    if tamanho > TETO_BYTES:
        return {**base, "tipo": "grande"}
    raw = alvo.read_bytes()
    if b"\x00" in raw[:8192]:
        return {**base, "tipo": "binario"}
    return {
        **base,
        "tipo": _tipo(rel),
        "conteudo": raw.decode("utf-8", errors="replace"),
    }


SCRIPT_DIAGNOSTICO = ".claude/skills/setup-maquina/scripts/diagnostico.sh"
_LINHA_DIAG = re.compile(r"^  (OK|FALTA|AVISO|OPC) +(.*)$")


def parse_diagnostico(saida: str) -> list[dict]:
    """Linhas `OK`/`FALTA`/`AVISO`/`OPC` do diagnostico.sh, com nome, conserto e a
    seção (o título "Nível N: ...") em que apareceram. O script imprime o nome
    numa coluna de 34 caracteres e o conserto depois dela."""
    itens, secao = [], ""
    for line in saida.splitlines():
        m = _LINHA_DIAG.match(line)
        if not m:
            if line and not line.startswith(" "):
                secao = line.strip()
            continue
        campo = line[9:]
        classe = m.group(1)
        if (
            classe == "OK"
        ):  # OK nunca tem conserto: o campo inteiro é o nome, sem ambiguidade
            nome, conserto = campo, ""
        elif len(campo) <= 35 or campo[34] == " ":
            nome, conserto = campo[:34], campo[35:]
        else:  # nome maior que a coluna: vaza sem padding, e o conserto vem depois do próximo espaço
            corte = campo.find(" ", 34)
            nome, conserto = (
                (campo, "") if corte < 0 else (campo[:corte], campo[corte + 1 :])
            )
        itens.append(
            {
                "classe": classe,
                "nome": nome.strip(),
                "conserto": conserto.strip(),
                "secao": secao,
            }
        )
    return itens


def rodar_diagnostico(root: Path) -> dict:
    """Roda o diagnostico.sh (só lê a máquina; o único toque no git é o fetch) e
    devolve os itens parseados. Nunca roda na coleta do /api/data: só sob demanda."""
    from datetime import datetime

    script = root / SCRIPT_DIAGNOSTICO
    if not script.is_file():
        return {
            "erro": f"{SCRIPT_DIAGNOSTICO} não encontrado",
            "itens": [],
            "faltas": 0,
            "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
    p = subprocess.run(
        ["bash", str(script)],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    itens = parse_diagnostico(p.stdout)
    return {
        "itens": itens,
        "faltas": sum(1 for i in itens if i["classe"] == "FALTA"),
        "exit": p.returncode,
        "quando": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def _cabeca(root: Path, rel: str) -> str:
    try:
        with open(root / rel, "rb") as f:
            raw = f.read(_CABECA_BYTES)
    except OSError:
        return ""
    if b"\x00" in raw:
        return ""
    return raw.decode("utf-8", errors="replace")


_VAZIO = {"o_que_e": SEM_RESUMO, "por_que": "", "o_que_tem": "", "para_que": ""}


def _agrupar(root: Path) -> dict[str, list[str]]:
    """Arquivos que o git conhece, agrupados por pasta de nível 1 ou 2 ("" é a raiz)."""
    pastas: dict[str, list[str]] = {}
    for rel in _ls_files(root):
        partes = rel.split("/")
        if len(partes) == 1:
            pastas.setdefault("", []).append(rel)
            continue
        pastas.setdefault(partes[0], [])
        chave = partes[0] if len(partes) == 2 else "/".join(partes[:2])
        pastas.setdefault(chave, []).append(rel)
    return pastas


def _resumo_do_arquivo(root: Path, rel: str, readme_pasta: str) -> dict:
    cabeca = _cabeca(root, rel)
    item = {"path": rel, "resumo": resumo_arquivo(rel, cabeca)}
    vercel = link_vercel(cabeca, readme_pasta)
    if vercel:
        item["vercel"] = vercel
    return item


def arvore(root: Path) -> dict:
    """Pastas de nível 1 e 2 com o resumo do README e a contagem de arquivos.

    Só a árvore entra na coleta do /api/data; a lista de arquivos de cada pasta
    vem sob demanda por `listar_pasta` (rota /api/pasta), ao clicar."""
    readme = (
        (root / "README.md").read_text(encoding="utf-8")
        if (root / "README.md").is_file()
        else ""
    )
    tabelas = _tabelas_do_readme(readme)
    grupos = _agrupar(root)
    return {
        "pastas": [
            {
                "path": path,
                "resumo": tabelas.get(path, _VAZIO),
                "n_arquivos": len(grupos[path]),
            }
            for path in sorted(grupos)
        ]
    }


def listar_pasta(root: Path, path: str) -> dict | None:
    """Arquivos de uma pasta da árvore, cada um com o resumo lido da fonte.
    Pasta que o git não conhece devolve None."""
    grupos = _agrupar(root)
    path = path.strip("/")
    if path not in grupos:
        return None
    readme_pasta = _cabeca(root, f"{path}/README.md") if path else ""
    return {
        "path": path,
        "arquivos": [
            _resumo_do_arquivo(root, a, readme_pasta) for a in sorted(grupos[path])
        ],
    }
