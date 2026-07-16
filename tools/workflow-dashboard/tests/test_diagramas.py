"""Testes do módulo diagramas: parse dos subsets Mermaid dos snapshots (ADR 0025).

Contrato: o coletor entrega estrutura JSON pronta pro renderer próprio da SPA;
bloco fora do subset degrada para código cru, nunca quebra. Sem rede, sem gh.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from diagramas import extrair_diagramas, parse_bloco  # noqa: E402

RAIZ = Path(__file__).resolve().parents[3]

ER_MINIMO = """erDiagram
    setores ||--o{ pops : "setor_id"

    setores {
        UUID id PK
        TEXT nome
    }
    pops {
        UUID id PK
        UUID setor_id FK
        _ mais_colunas "+8"
    }
"""


def test_er_minimo_vira_tabelas_com_pk_fk_e_relacoes():
    d = parse_bloco(ER_MINIMO)

    assert d["tipo"] == "er"
    tabelas = {t["nome"]: t for t in d["tabelas"]}
    assert set(tabelas) == {"setores", "pops"}
    assert tabelas["setores"]["colunas"][0] == {"nome": "id", "tipo": "UUID", "pk": True, "fk": False}
    fk = next(c for c in tabelas["pops"]["colunas"] if c["nome"] == "setor_id")
    assert fk["fk"] is True and fk["pk"] is False
    assert d["relacoes"] == [{"origem": "setores", "destino": "pops", "rotulo": "setor_id", "cardinalidade": "||--o{"}]


def test_marcador_mais_colunas_vira_extras_e_nao_coluna():
    pops = next(t for t in parse_bloco(ER_MINIMO)["tabelas"] if t["nome"] == "pops")

    assert pops["extras"] == 8
    assert [c["nome"] for c in pops["colunas"]] == ["id", "setor_id"]


def test_tabela_so_citada_em_relacao_aparece_sem_colunas():
    d = parse_bloco('erDiagram\n    a ||--o{ b : "a_id"\n    a {\n        UUID id PK\n    }\n')

    tabelas = {t["nome"]: t for t in d["tabelas"]}
    assert set(tabelas) == {"a", "b"}
    assert tabelas["b"] == {"nome": "b", "colunas": [], "extras": 0}


def test_er_com_linha_fora_do_subset_degrada_para_codigo_cru():
    codigo = 'erDiagram\n    a ==> b : "seta que nao existe no er"\n'
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_er_com_tabela_sem_fechar_degrada_para_codigo_cru():
    codigo = "erDiagram\n    a {\n        UUID id PK\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_tipo_de_diagrama_desconhecido_degrada_para_codigo_cru():
    codigo = "flowchart TD\n    A --> B\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_extrair_diagramas_le_os_blocos_mermaid_na_ordem():
    md = f"# Doc\n\n```mermaid\n{ER_MINIMO}```\n\ntexto\n\n```mermaid\nflowchart TD\n    A --> B\n```\n"
    assert [d["tipo"] for d in extrair_diagramas(md)] == ["er", "codigo"]


def test_markdown_sem_bloco_mermaid_devolve_lista_vazia():
    assert extrair_diagramas("# Doc\n\n```bash\necho oi\n```\n") == []
    assert extrair_diagramas("") == []
    assert extrair_diagramas(None) == []


def test_schema_md_real_parseia_em_er_consistente():
    texto = (RAIZ / "docs" / "spec" / "snapshots" / "SCHEMA.md").read_text(encoding="utf-8")
    ers = [d for d in extrair_diagramas(texto) if d["tipo"] == "er"]

    assert len(ers) == 1
    er = ers[0]
    nomes = {t["nome"] for t in er["tabelas"]}
    assert {"participantes", "reunioes", "pops"} <= nomes
    assert len(er["tabelas"]) >= 15
    assert len(er["relacoes"]) >= 20
    # toda relação aponta para tabela presente, o renderer confia nisso
    for r in er["relacoes"]:
        assert r["origem"] in nomes and r["destino"] in nomes
    participantes = next(t for t in er["tabelas"] if t["nome"] == "participantes")
    assert any(c["pk"] for c in participantes["colunas"])


def test_snapshots_do_collect_servem_diagramas_junto_do_body():
    import collect

    docs = collect._snapshots(RAIZ)

    schema = next(d for d in docs if d["name"] == "SCHEMA")
    assert any(x["tipo"] == "er" for x in schema["diagramas"])
