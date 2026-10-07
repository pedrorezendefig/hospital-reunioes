"""Decisões viram mapa de miniaturas por tema (issue #1082).

As setas saem só do frontmatter (`amends`/`supersedes` e os inversos); citação
solta no corpo vira a lista "cita" do popover, nunca seta. O agrupamento por
tema (static/decisoes.js) põe a seta dentro do tema e troca o vínculo com outro
tema por um chip "→ 0054 (Tecnologia)".
"""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DASH = Path(__file__).resolve().parents[1]
STATIC = DASH / "static"
RAIZ = Path(__file__).resolve().parents[3]

sys.path.insert(0, str(DASH))
from collect import _parse_adrs, arestas_adr, citacoes_adr, numeros_adr  # noqa: E402

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


# ---------- extração das arestas: frontmatter vs citação ----------


def test_numeros_do_frontmatter_viram_inteiros():
    assert numeros_adr("0029, 0061, 0062") == [29, 61, 62]
    assert numeros_adr("0054") == [54]
    assert numeros_adr(None) == [] and numeros_adr("") == []


def test_citacao_no_corpo_pega_adr_lista_e_link_sem_a_propria_nem_a_inexistente():
    corpo = (
        "Segue a ADR 0034, como as ADRs 0057 e 0068 e a ADR 0054, decisões 4 e 5. "
        "Veja [0031](0031-x.md). Esta é a ADR 0040. Número solto 0013 não conta, "
        "nem a ADR 0999 que não existe."
    )
    existentes = {31, 34, 40, 54, 57, 68}
    assert citacoes_adr(corpo, 40, existentes) == [31, 34, 54, 57, 68]


def _adr(tmp_path, nome, front, corpo="corpo"):
    d = tmp_path / "docs" / "adr"
    d.mkdir(parents=True, exist_ok=True)
    (d / nome).write_text(f"---\n{front}\n---\n\n# Título {nome}\n\n{corpo}\n", encoding="utf-8")


def test_adr_traz_os_vinculos_do_frontmatter_e_a_citacao_sem_repetir(tmp_path):
    _adr(tmp_path, "0016-a.md", "status: accepted\namended_by: 0021")
    _adr(tmp_path, "0018-b.md", "status: superseded\nsuperseded_by: 0021")
    _adr(
        tmp_path,
        "0021-c.md",
        "status: accepted\nsupersedes: 0018\namends: 0016",
        "Emenda a ADR 0016 e cita a ADR 0018 e a ADR 0030.",
    )
    _adr(tmp_path, "0030-d.md", "status: accepted")
    por_n = {a["number"]: a for a in _parse_adrs(tmp_path)}
    c = por_n[21]
    assert c["emenda"] == [16] and c["substitui"] == [18]
    assert c["emendada_por"] == [] and c["substituida_por"] == []
    # o que já é vínculo de frontmatter não se repete em "cita"
    assert c["cita"] == [30]
    assert por_n[16]["emendada_por"] == [21]
    assert por_n[18]["substituida_por"] == [21]


def test_arestas_so_do_frontmatter_sem_duplicar_os_dois_lados(tmp_path):
    _adr(tmp_path, "0016-a.md", "status: accepted\namended_by: 0021")
    _adr(tmp_path, "0018-b.md", "status: superseded\nsuperseded_by: 0021")
    _adr(
        tmp_path,
        "0021-c.md",
        "status: accepted\nsupersedes: 0018\namends: 0016",
        "Cita a ADR 0030 no corpo.",
    )
    _adr(tmp_path, "0030-d.md", "status: accepted\namended_by: 0099")
    arestas = arestas_adr(_parse_adrs(tmp_path))
    # emenda aponta para a emendada; substituição aponta para a sucessora
    assert arestas == [
        {"de": 18, "para": 21, "tipo": "substitui"},
        {"de": 21, "para": 16, "tipo": "emenda"},
    ]


def test_arestas_do_repo_real_batem_com_o_frontmatter():
    arestas = arestas_adr(_parse_adrs(RAIZ))
    assert {"de": 22, "para": 68, "tipo": "substitui"} in arestas
    assert {"de": 69, "para": 54, "tipo": "emenda"} in arestas
    assert len(arestas) == len({(a["de"], a["para"], a["tipo"]) for a in arestas})


# ---------- agrupamento por tema (static/decisoes.js no Node) ----------

ADRS = [
    {"number": 16, "title": "A", "status": "accepted", "body_md": "fala de reunião"},
    {"number": 18, "title": "B", "status": "superseded", "body_md": "antiga"},
    {"number": 21, "title": "C", "status": "accepted", "body_md": "cita a ADR 0054", "cita": [54]},
    {"number": 54, "title": "Vínculo", "status": "accepted", "body_md": "tecnologia"},
    {"number": 70, "title": "Sem tema", "status": "accepted", "body_md": "x"},
]
TEMAS = [
    {"tema": "Reuniões e Atas", "numeros": [16, 18, 21]},
    {"tema": "Tecnologia", "numeros": [54]},
]
ARESTAS = [
    {"de": 18, "para": 21, "tipo": "substitui"},
    {"de": 21, "para": 16, "tipo": "emenda"},
    {"de": 21, "para": 54, "tipo": "emenda"},
]


def _mapa(tmp_path, opcoes):
    prog = (
        f"import {{ mapaDecisoes }} from '{(STATIC / 'decisoes.js').as_uri()}';\n"
        f"const m = mapaDecisoes({json.dumps(ADRS)}, {json.dumps(TEMAS)}, {json.dumps(ARESTAS)}, {json.dumps(opcoes)});\n"
        "console.log('@@' + JSON.stringify(m.map(g => ({ tema: g.tema, nos: g.nos.map(n => n.number),"
        " setas: g.setas, chips: g.chips }))));\n"
    )
    arq = tmp_path / "m.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(["node", str(arq)], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    return json.loads([x for x in out.stdout.splitlines() if x.startswith("@@")][-1][2:])


@com_node
def test_tema_tem_as_aceitas_em_ordem_seta_dentro_e_chip_para_outro_tema(tmp_path):
    m = _mapa(tmp_path, {"hist": False, "q": ""})
    assert [g["tema"] for g in m] == ["Reuniões e Atas", "Tecnologia", "Fora do índice"]
    reunioes, tecnologia, fora = m
    assert reunioes["nos"] == [16, 21] and fora["nos"] == [70]
    # a superada fica fora sem histórico, e a seta dela também
    assert reunioes["setas"] == [{"de": 21, "para": 16, "tipo": "emenda"}]
    # vínculo com outro tema vira chip nas duas pontas; citação solta não vira nada
    assert reunioes["chips"] == {"21": [{"n": 54, "tema": "Tecnologia", "sai": True}]}
    assert tecnologia["chips"] == {"54": [{"n": 21, "tema": "Reuniões e Atas", "sai": False}]}
    assert tecnologia["setas"] == []


@com_node
def test_historico_traz_a_superada_com_seta_para_a_sucessora(tmp_path):
    reunioes = _mapa(tmp_path, {"hist": True, "q": ""})[0]
    assert reunioes["nos"] == [16, 18, 21]
    assert {"de": 18, "para": 21, "tipo": "substitui"} in reunioes["setas"]


@com_node
def test_busca_tira_quem_nao_casa_e_as_setas_dele(tmp_path):
    m = _mapa(tmp_path, {"hist": False, "q": "REUNIÃO"})
    assert [(g["tema"], g["nos"]) for g in m] == [("Reuniões e Atas", [16])]
    assert m[0]["setas"] == [] and m[0]["chips"] == {}


def test_decisoes_js_sem_travessao_nem_meia_risca():
    for arq in ("decisoes.js", "app.js", "style.css"):
        txt = (STATIC / arq).read_text(encoding="utf-8")
        assert chr(0x2014) not in txt and chr(0x2013) not in txt, arq
    assert not re.search("[–—]", (DASH / "collect.py").read_text(encoding="utf-8"))
