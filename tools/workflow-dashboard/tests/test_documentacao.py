"""Aba Documentação: o fluxo de trabalho (static/fluxo.json) e as Decisões por tema.

O fluxo é um JSON desenhado à mão, mantido junto com o /ask-pedro, e o
diagramas.js desenha (tipo `fluxo`). Aqui mora o contrato do arquivo: JSON
válido, grafo fechado (toda aresta aponta para nó que existe), todo passo de
skill aponta para skill que existe em .claude/skills/<nome>/SKILL.md, nenhum
travessão, e as classes e paradas humanas que o painel promete. As Decisões
agrupam as ADRs pelo índice docs/adr/README.md, parseado no collect.py.
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
FLUXO_TXT = (STATIC / "fluxo.json").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
DIAGRAMAS_JS = (STATIC / "diagramas.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
README = (DASH / "README.md").read_text(encoding="utf-8")

sys.path.insert(0, str(DASH))
from collect import frase_da_decisao, parse_temas_adr

com_node = pytest.mark.skipif(not shutil.which("node"), reason="node ausente")


@pytest.fixture(scope="module")
def fluxo():
    return json.loads(FLUXO_TXT)


# ---------- fluxo.json: o contrato do arquivo ----------


def test_fluxo_json_valido_do_tipo_fluxo(fluxo):
    assert fluxo["tipo"] == "fluxo"
    assert fluxo["nos"] and fluxo["arestas"]


def test_todo_no_referenciado_por_aresta_existe_e_os_ids_sao_unicos(fluxo):
    ids = [n["id"] for n in fluxo["nos"]]
    assert len(ids) == len(set(ids)), "id de nó repetido"
    for a in fluxo["arestas"]:
        assert a["de"] in ids, f"aresta sai de nó inexistente: {a['de']}"
        assert a["para"] in ids, f"aresta chega em nó inexistente: {a['para']}"
    ligados = {a["de"] for a in fluxo["arestas"]} | {
        a["para"] for a in fluxo["arestas"]
    }
    assert set(ids) <= ligados, f"nó solto, sem aresta: {set(ids) - ligados}"


def test_todo_no_de_skill_aponta_para_skill_que_existe(fluxo):
    de_skill = [n for n in fluxo["nos"] if n.get("skill")]
    assert len(de_skill) >= 8, "o fluxo perdeu os passos de skill"
    for n in de_skill:
        assert (RAIZ / ".claude" / "skills" / n["skill"] / "SKILL.md").is_file(), (
            f"nó {n['id']} aponta para skill inexistente: {n['skill']}"
        )


def test_fluxo_sem_travessao_nem_meia_risca():
    assert chr(0x2014) not in FLUXO_TXT, "fluxo.json contém travessão"
    assert chr(0x2013) not in FLUXO_TXT, "fluxo.json contém meia-risca"


def test_classes_das_cores_e_as_paradas_humanas_da_0068(fluxo):
    classes = {n["classe"] for n in fluxo["nos"]}
    assert classes <= {"auto", "humano", "decisao", "fim"}, classes
    humanos = {n["id"] for n in fluxo["nos"] if n["classe"] == "humano"}
    # as paradas humanas que o painel promete: migration, draft do vídeo,
    # rollback que a subida não conseguiu e a baixa ready-for-human
    assert {"migration", "draft", "rollback", "baixa"} <= humanos
    assert [n["id"] for n in fluxo["nos"] if n["classe"] == "decisao"] == ["porta"]
    for n in fluxo["nos"]:
        assert n.get("detalhe"), f"nó {n['id']} sem a regra (campo detalhe)"


def test_as_tres_portas_e_a_legenda_vem_do_json(fluxo):
    portas = [p["porta"] for p in fluxo["portas"]]
    assert [p[0] for p in portas] == ["A", "B", "C"]
    assert all(p["quando"] and p["caminho"] for p in fluxo["portas"])
    assert [l["classe"] for l in fluxo["legenda"]] == ["auto", "humano", "decisao"]
    # o front não tem o texto do fluxo hardcoded: os rótulos vêm do JSON
    for n in fluxo["nos"][:5]:
        assert n["titulo"] not in APP_JS


def test_renderer_proprio_registra_o_tipo_fluxo_sem_mermaid():
    assert "fluxo: fluxoSvg" in DIAGRAMAS_JS
    # a classe do nó sai de fx-${classe}; a mão só existe no nó humano
    assert "fx-mao" in DIAGRAMAS_JS and "n.classe === 'humano'" in DIAGRAMAS_JS
    assert (
        ".fx-humano rect" in CSS
        and ".fx-decisao rect" in CSS
        and ".fx-auto rect" in CSS
    )
    assert "mermaid.min.js" not in DIAGRAMAS_JS and "window.mermaid" not in DIAGRAMAS_JS


@com_node
def test_renderer_desenha_o_fluxo_inteiro_e_cabe_em_1400px(tmp_path, fluxo):
    prog = (
        f"import {{ renderDiagrama }} from '{(STATIC / 'diagramas.js').as_uri()}';\n"
        f"const svg = renderDiagrama({json.dumps(fluxo)});\n"
        "console.log('@@' + JSON.stringify(svg));\n"
    )
    arq = tmp_path / "h.mjs"
    arq.write_text(prog, encoding="utf-8")
    out = subprocess.run(
        ["node", str(arq)], capture_output=True, text=True, check=False
    )
    assert out.returncode == 0, out.stderr
    svg = json.loads([x for x in out.stdout.splitlines() if x.startswith("@@")][-1][2:])
    assert svg, "renderer devolveu null para o fluxo.json"
    largura = int(re.search(r'viewBox="0 0 (\d+)', svg).group(1))
    assert largura <= 1400
    for n in fluxo["nos"]:
        assert f'data-id="{n["id"]}"' in svg
        assert 'data-act="fluxono"' in svg
    assert svg.count('<g class="fx-rel"') == len(fluxo["arestas"])
    assert svg.count("fx-mao") == len(
        [n for n in fluxo["nos"] if n["classe"] == "humano"]
    )


def test_readme_avisa_que_o_fluxo_anda_junto_com_o_ask_pedro():
    assert "fluxo.json" in README and "/ask-pedro" in README
    assert "### Documentação" in README


# ---------- Decisões: temas do índice e a frase da decisão ----------

INDICE = """# Índice dos ADRs por tema

## Ouvidoria

| ADR | Status | Título |
|---|---|---|
| [0031](0031-x.md) | accepted | Dados migram |
| [0047](0047-y.md) | accepted | Apagar é retenção |

## Workflow de agentes e ondas

| ADR | Status | Título |
|---|---|---|
| [0022](0022-z.md) | superseded | Onda |
| [0068](0068-w.md) | accepted | O fluxo em uma página |

## Comunicação e layout do repo

| ADR | Status | Título |
|---|---|---|
| [0047](0047-y.md) | accepted | Apagar é retenção (repetida) |

Novo ADR: acrescente a linha no tema certo.
"""


def test_temas_do_indice_na_ordem_e_adr_repetida_fica_no_primeiro_tema():
    assert parse_temas_adr(INDICE) == [
        {"tema": "Ouvidoria", "numeros": [31, 47]},
        {"tema": "Workflow de agentes e ondas", "numeros": [22, 68]},
    ]


def test_indice_sem_tema_parseavel_devolve_vazio():
    assert parse_temas_adr("# só texto\n\nsem tabela\n") == []
    assert parse_temas_adr("") == []


def test_indice_real_agrupa_a_0068_no_workflow():
    temas = parse_temas_adr(
        (RAIZ / "docs" / "adr" / "README.md").read_text(encoding="utf-8")
    )
    por_tema = {t["tema"]: t["numeros"] for t in temas}
    assert len(por_tema) >= 5
    assert 68 in por_tema["Workflow de agentes e ondas"]


def test_frase_da_decisao_prefere_a_secao_decisao_e_cai_no_primeiro_paragrafo():
    com_secao = "Contexto longo.\n\n## Decisão\n\nA fatia entra uma onda depois.\nSegunda linha.\n\nOutro parágrafo.\n"
    assert (
        frase_da_decisao(com_secao) == "A fatia entra uma onda depois. Segunda linha."
    )
    sem_secao = (
        "---\n## Contexto\n\n- lista\n\nO primeiro parágrafo de verdade.\n\nOutro.\n"
    )
    assert frase_da_decisao(sem_secao) == "O primeiro parágrafo de verdade."
    assert frase_da_decisao("") == ""


def test_frase_da_decisao_corta_na_palavra():
    longa = "palavra " * 60
    frase = frase_da_decisao(longa, maximo=50)
    assert frase.endswith("...") and len(frase) <= 54 and " pal..." not in frase


def test_decisoes_mostram_so_accepted_por_padrao_com_historico_e_busca():
    fn = re.search(r"function adrGrupos\(\)[\s\S]*?\n\}", APP_JS)
    assert fn, "app.js sem adrGrupos"
    corpo = fn.group(0)
    assert "S.adrHist || a.status === 'accepted'" in corpo
    assert "adr_temas" in corpo and "temasPorPrefixo" in corpo
    assert "ver histórico (" in APP_JS
    assert "substituída pela" in APP_JS and "→" not in re.search(
        r"function adrPointerBadge[\s\S]*?\n\}", APP_JS
    ).group(0)


# ---------- a aba viva no Node: sub-pills, histórico e âncora do glossário ----------

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_router import DADOS, _app

DADOS_DOC = {
    **DADOS,
    "adrs": [
        {
            "number": 22,
            "title": "Onda antiga",
            "status": "superseded",
            "superseded_by": "0068",
            "decisao": "Ondas com checkpoint.",
            "body_md": "corpo da 22",
            "file": "docs/adr/0022.md",
        },
        {
            "number": 68,
            "title": "O fluxo em uma página",
            "status": "accepted",
            "decisao": "O que o pipeline faz hoje.",
            "body_md": "corpo da 68 fala de subida",
            "file": "docs/adr/0068.md",
        },
        {
            "number": 1,
            "title": "Supabase self-hosted",
            "status": "accepted",
            "decisao": "Supabase no Coolify.",
            "body_md": "corpo da 1",
            "file": "docs/adr/0001.md",
        },
    ],
    "adr_temas": [{"tema": "Workflow de agentes e ondas", "numeros": [22, 68]}],
    "context_md": "# Glossário\n\n## Reunião e Ata\n\n**Ata Guiada**:\nSegundo modo.\n\n**Ata**:\nO documento.\n",
}


@com_node
def test_sub_pills_vao_para_o_hash_e_os_enderecos_antigos_caem_nelas(tmp_path):
    passos = _app(
        tmp_path,
        "_h",
        hash_inicial="#mapa",
        dados=DADOS_DOC,
        antes="""
        const _h = [[location.hash, S.tab, subDoc()]];
        _clicar({ act: 'docsub', sub: 'decisoes' }); _h.push([location.hash, subDoc()]);
        _clicar({ act: 'docsub', sub: 'fluxo' }); _h.push([location.hash, subDoc()]);
        _navegar('#dominio'); _h.push([location.hash, subDoc()]);
        _aba('documentacao'); _h.push([location.hash, subDoc()]);
        """,
    )
    assert passos == [
        ["#documentacao/mapa", "documentacao", "mapa"],
        ["#documentacao/decisoes", "decisoes"],
        ["#documentacao/fluxo", "fluxo"],
        ["#documentacao/decisoes", "decisoes"],
        ["#documentacao", "fluxo"],
    ]


@com_node
def test_decisoes_por_tema_so_accepted_e_o_historico_esmaecido_com_ponteiro(tmp_path):
    antes, depois = _app(
        tmp_path,
        "[_antes, _view.innerHTML]",
        hash_inicial="#documentacao/decisoes",
        dados=DADOS_DOC,
        antes="const _antes = _view.innerHTML; _clicar({ act: 'adrhist' });",
    )
    assert "Workflow de agentes e ondas · 1" in antes and "Fora do índice · 1" in antes
    assert "O fluxo em uma página" in antes and "Supabase self-hosted" in antes
    assert "Onda antiga" not in antes
    assert "ver histórico (1)" in antes
    assert "O que o pipeline faz hoje." in antes  # a frase da decisão no card
    assert "Workflow de agentes e ondas · 2" in depois and "Onda antiga" in depois
    assert re.search(
        r'class="card tst adr[^"]*adr-hist"[\s\S]{0,900}substituída pela 0068', depois
    )
    assert "→" not in depois


@com_node
def test_glossario_tem_indice_em_chips_e_o_termo_do_hash_em_destaque(tmp_path):
    # o marked vendorizado entra no harness: sem ele o CONTEXT.md vira <pre> e não há termo a ancorar
    # (o UMD vira CommonJS no Node: o módulo é o próprio objeto marked)
    marked = f"import _marked from '{(STATIC / 'vendor' / 'marked.min.js').as_uri()}';\nglobalThis.marked = window.marked = _marked;\n"
    html = _app(
        tmp_path,
        "_view.innerHTML",
        hash_inicial="#documentacao/glossario/ata-guiada",
        dados=DADOS_DOC,
        preludio_extra=marked,
    )
    assert (
        '<a class="chip" href="#documentacao/glossario/ata-guiada">Ata Guiada</a>'
        in html
    )
    assert '<a class="chip" href="#documentacao/glossario/ata">Ata</a>' in html
    assert 'id="g-ata-guiada" class="g-termo g-alvo" aria-current="true"' in html
    assert 'id="g-ata" class="g-termo"' in html
    assert "Segundo modo." in html  # o corpo segue intacto
