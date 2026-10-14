"""O draft do Vídeo de tarefa não espera mais OK humano (issue #1253).

Decisão do Pedro em 14/10/2026, depois do piloto #1231: a Fatia de manual
segue como qualquer outra fatia, do PR verde à subida, e quem segura a
qualidade do vídeo são os gates (`hyperframes check`, strips,
`checar_video_manual.py` e `anel_video_manual.py`). As paradas humanas do
fluxo passam de quatro para três: migration, rollback que a subida não fechou
e baixa `ready-for-human`.

A varredura lê o texto que manda no pipeline (skills, agentes, `CLAUDE.md`,
ADRs aceitas, o fluxo do Hospital OS e os scripts do vídeo) e procura as
frases do fluxo antigo. A `/divulgar` fica de fora: o Vídeo de percepção de
valor tem gate humano próprio (ADRs 0026 e 0045), que esta decisão não muda.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# O Vídeo de percepção de valor (/divulgar) mantém o OK humano no draft.
FORA = {
    ".claude/skills/divulgar",
    "docs/adr/0026-percepcao-de-valor-em-video-hyperframes.md",
    "docs/adr/0045-video-e-pagina-de-divulgacao-sao-uma-entrega-so.md",
}

FRASES_DO_FLUXO_ANTIGO = [
    r"[Qq]uatro (paradas|coisas esperam)",
    r"OK humano no draft",
    r"[Pp]ar[ae] no draft de cada",
    r"para no draft do v[ií]deo",
    r"checkpoint de merge com o draft",
    r"Draft do v[ií]deo da #",
    r"fora da subida at[ée] o OK",
    r"draft do v[ií]deo[^.\n]{0,60}esperam o humano",
    r"viu o (draft do )?v[ií]deo\s+rod[ae]",
    r"OK[^.\n]{0,60}render final",
    r"s[óo] o Pedro aprova",
    r"v[ií]deo com OK humano",
    r"antes do OK humano",
]


def _status_aceito(texto: str) -> bool:
    m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
    return bool(m and re.search(r"^status:\s*accepted", m.group(1), re.M))


def textos_do_pipeline() -> dict[str, str]:
    caminhos = [
        *(RAIZ / ".claude" / "skills").rglob("*.md"),
        *(RAIZ / ".claude" / "skills").rglob("*.py"),
        *(RAIZ / ".claude" / "agents").glob("*.md"),
        RAIZ / "CLAUDE.md",
        RAIZ / "tools" / "workflow-dashboard" / "static" / "fluxo.json",
        RAIZ / "tools" / "checar_video_manual.py",
        *(RAIZ / "docs" / "adr").glob("[0-9]*.md"),
    ]
    textos = {}
    for caminho in caminhos:
        rel = caminho.relative_to(RAIZ).as_posix()
        if any(rel == f or rel.startswith(f + "/") for f in FORA):
            continue
        texto = caminho.read_text(encoding="utf-8")
        if rel.startswith("docs/adr/") and not _status_aceito(texto):
            continue
        textos[rel] = texto
    return textos


def test_nenhum_texto_do_pipeline_manda_parar_no_draft_do_video_de_tarefa():
    textos = textos_do_pipeline()
    assert len(textos) >= 40, "a varredura perdeu os textos do pipeline"
    achados = [
        f"{rel}: {m.group(0)!r}"
        for rel, texto in textos.items()
        for padrao in FRASES_DO_FLUXO_ANTIGO
        for m in re.finditer(padrao, texto)
    ]
    assert achados == []


def test_as_paradas_humanas_sao_tres_na_adr_0068_no_claude_md_e_no_painel():
    adr = (RAIZ / "docs" / "adr" / "0068-o-fluxo-em-uma-pagina.md").read_text(
        encoding="utf-8"
    )
    regra_9 = next(li for li in adr.splitlines() if li.startswith("9. "))
    assert "Três coisas esperam o humano" in regra_9
    for parada in ("migration", "rollback que a subida não conseguiu", "baixa"):
        assert parada in regra_9, parada
    assert "vídeo" not in regra_9

    claude_md = (RAIZ / "CLAUDE.md").read_text(encoding="utf-8")
    assert "fora as três paradas da regra 9" in claude_md

    fluxo = json.loads(
        (RAIZ / "tools" / "workflow-dashboard" / "static" / "fluxo.json").read_text(
            encoding="utf-8"
        )
    )
    humanos = {n["id"] for n in fluxo["nos"] if n["classe"] == "humano"}
    assert humanos == {"migration", "rollback", "baixa"}
