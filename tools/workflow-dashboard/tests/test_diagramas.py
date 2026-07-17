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
    assert tabelas["setores"]["colunas"][0] == {
        "nome": "id",
        "tipo": "UUID",
        "pk": True,
        "fk": False,
    }
    fk = next(c for c in tabelas["pops"]["colunas"] if c["nome"] == "setor_id")
    assert fk["fk"] is True and fk["pk"] is False
    assert d["relacoes"] == [
        {
            "origem": "setores",
            "destino": "pops",
            "rotulo": "setor_id",
            "cardinalidade": "||--o{",
        }
    ]


def test_marcador_mais_colunas_vira_extras_e_nao_coluna():
    pops = next(t for t in parse_bloco(ER_MINIMO)["tabelas"] if t["nome"] == "pops")

    assert pops["extras"] == 8
    assert [c["nome"] for c in pops["colunas"]] == ["id", "setor_id"]


def test_tabela_so_citada_em_relacao_aparece_sem_colunas():
    d = parse_bloco(
        'erDiagram\n    a ||--o{ b : "a_id"\n    a {\n        UUID id PK\n    }\n'
    )

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
    codigo = "gantt\n    title Cronograma\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


ESTADO_MINIMO = """stateDiagram-v2
    [*] --> RASCUNHO: autor cria
    RASCUNHO --> PUBLICADO: autor publica
    RASCUNHO --> ERRO: validacao falha
    ERRO --> RASCUNHO: autor corrige
    PUBLICADO --> [*]
"""


def test_state_minimo_vira_estados_e_transicoes_rotuladas():
    d = parse_bloco(ESTADO_MINIMO)

    assert d["tipo"] == "estado"
    assert d["estados"] == ["RASCUNHO", "PUBLICADO", "ERRO"]
    assert d["transicoes"][0] == {
        "origem": "[*]",
        "destino": "RASCUNHO",
        "rotulo": "autor cria",
    }
    assert d["transicoes"][1] == {
        "origem": "RASCUNHO",
        "destino": "PUBLICADO",
        "rotulo": "autor publica",
    }
    # transição sem rótulo (terminal) vira rótulo vazio, não None
    assert d["transicoes"][-1] == {
        "origem": "PUBLICADO",
        "destino": "[*]",
        "rotulo": "",
    }


def test_state_fora_do_subset_degrada_para_codigo_cru():
    codigo = "stateDiagram-v2\n    state Composto {\n        [*] --> A\n    }\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_state_sem_transicao_degrada_para_codigo_cru():
    codigo = "stateDiagram-v2\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_fluxogramas_md_real_parseia_os_2_ciclos_de_vida():
    texto = (RAIZ / "docs" / "spec" / "snapshots" / "FLUXOGRAMAS.md").read_text(
        encoding="utf-8"
    )
    estados = [d for d in extrair_diagramas(texto) if d["tipo"] == "estado"]

    assert len(estados) == 2
    reuniao, pendencia = estados
    assert {
        "PROGRAMADA",
        "PROCESSANDO",
        "AGUARDANDO_VALIDACAO",
        "ASSINADA",
        "ERRO",
        "CORRIGINDO",
    } <= set(reuniao["estados"])
    assert {"PENDENTE", "EM_PROGRESSO", "CONCLUIDO", "ATRASADO", "REPACTUADA"} <= set(
        pendencia["estados"]
    )
    for d in estados:
        nomes = set(d["estados"]) | {"[*]"}
        # toda transição referencia estado conhecido ou o marcador [*], o renderer confia nisso
        for t in d["transicoes"]:
            assert t["origem"] in nomes and t["destino"] in nomes
        # os 2 ciclos têm estado inicial e final, o renderer ancora a espinha neles
        assert any(t["origem"] == "[*]" for t in d["transicoes"])
        assert any(t["destino"] == "[*]" for t in d["transicoes"])


def test_extrair_diagramas_le_os_blocos_mermaid_na_ordem():
    md = f'# Doc\n\n```mermaid\n{ER_MINIMO}```\n\ntexto\n\n```mermaid\npie\n    "a": 1\n```\n'
    assert [d["tipo"] for d in extrair_diagramas(md)] == ["er", "codigo"]


def test_bloco_mermaid_com_crlf_parseia_como_lf():
    md = '```mermaid\r\nerDiagram\r\n    a ||--o{ b : "a_id"\r\n    a {\r\n        UUID id PK\r\n    }\r\n```\r\n'
    ds = extrair_diagramas(md)

    assert [d["tipo"] for d in ds] == ["er"]
    assert {t["nome"] for t in ds[0]["tabelas"]} == {"a", "b"}


def test_markdown_sem_bloco_mermaid_devolve_lista_vazia():
    assert extrair_diagramas("# Doc\n\n```bash\necho oi\n```\n") == []
    assert extrair_diagramas("") == []
    assert extrair_diagramas(None) == []


SEQ_MINIMO = """sequenceDiagram
    participant A as App (backend)
    participant B as Banco

    A->>B: grava registro
    B-->>A: ok
"""


def test_seq_minimo_vira_participantes_e_mensagens_ordenadas():
    d = parse_bloco(SEQ_MINIMO)

    assert d["tipo"] == "seq"
    assert d["participantes"] == [
        {"id": "A", "nome": "App (backend)"},
        {"id": "B", "nome": "Banco"},
    ]
    assert d["mensagens"] == [
        {"de": "A", "para": "B", "texto": "grava registro", "seta": "->>"},
        {"de": "B", "para": "A", "texto": "ok", "seta": "-->>"},
    ]


def test_seq_participante_sem_declaracao_entra_na_ordem_de_uso():
    d = parse_bloco("sequenceDiagram\n    A->>B: oi\n    C->>A: tchau\n")

    assert [p["id"] for p in d["participantes"]] == ["A", "B", "C"]
    assert all(p["nome"] == p["id"] for p in d["participantes"])


def test_seq_mensagem_para_si_mesmo_e_texto_com_dois_pontos():
    d = parse_bloco(
        "sequenceDiagram\n    WH->>WH: valida HMAC\n    FE->>BE: GET /x (Authorization: Bearer <JWT>)\n"
    )

    assert d["tipo"] == "seq"
    assert d["mensagens"][0] == {
        "de": "WH",
        "para": "WH",
        "texto": "valida HMAC",
        "seta": "->>",
    }
    assert d["mensagens"][1]["texto"] == "GET /x (Authorization: Bearer <JWT>)"


def test_seq_linha_fora_do_subset_degrada_para_codigo_cru():
    codigo = "sequenceDiagram\n    A->>B: oi\n    Note over A: fora do subset\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_seq_sem_mensagens_degrada_para_codigo_cru():
    codigo = "sequenceDiagram\n    participant A as App\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_fluxogramas_md_real_parseia_as_2_sequencias():
    texto = (RAIZ / "docs" / "spec" / "snapshots" / "FLUXOGRAMAS.md").read_text(
        encoding="utf-8"
    )
    seqs = [d for d in extrair_diagramas(texto) if d["tipo"] == "seq"]

    assert len(seqs) == 2
    clicksign, auth = seqs
    assert [p["id"] for p in clicksign["participantes"]] == [
        "App",
        "CS",
        "P",
        "WH",
        "DB",
        "R",
    ]
    assert len(clicksign["mensagens"]) == 9
    assert (
        clicksign["mensagens"][6]["de"] == "WH"
        and clicksign["mensagens"][6]["para"] == "WH"
    )
    assert [p["id"] for p in auth["participantes"]] == ["U", "FE", "SA", "BE", "DB"]
    assert len(auth["mensagens"]) == 14
    # toda mensagem liga participantes presentes, o renderer confia nisso
    for d in seqs:
        ids = {p["id"] for p in d["participantes"]}
        for m in d["mensagens"]:
            assert m["de"] in ids and m["para"] in ids


def test_schema_md_real_parseia_em_er_consistente():
    texto = (RAIZ / "docs" / "spec" / "snapshots" / "SCHEMA.md").read_text(
        encoding="utf-8"
    )
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


FLOW_MINIMO = """flowchart TD
    A[Comeca aqui] --> B{Deu certo?}
    B -- sim --> C[Fim feliz<br/>com duas linhas]
    B -- nao --> D
    D --> C
"""


def test_flow_minimo_vira_nos_e_arestas_rotuladas():
    d = parse_bloco(FLOW_MINIMO)

    assert d["tipo"] == "flow"
    nos = {n["id"]: n for n in d["nos"]}
    assert set(nos) == {"A", "B", "C", "D"}
    assert nos["A"] == {"id": "A", "linhas": ["Comeca aqui"], "decisao": False}
    assert nos["B"] == {"id": "B", "linhas": ["Deu certo?"], "decisao": True}
    # <br/> vira quebra de linha real no nó
    assert nos["C"]["linhas"] == ["Fim feliz", "com duas linhas"]
    assert d["arestas"][0] == {"origem": "A", "destino": "B", "rotulo": ""}
    assert d["arestas"][1] == {"origem": "B", "destino": "C", "rotulo": "sim"}
    assert d["arestas"][2] == {"origem": "B", "destino": "D", "rotulo": "nao"}


def test_flow_no_so_citado_vira_passo_com_o_proprio_id():
    nos = {n["id"]: n for n in parse_bloco(FLOW_MINIMO)["nos"]}
    assert nos["D"] == {"id": "D", "linhas": ["D"], "decisao": False}


def test_flow_fora_do_subset_degrada_para_codigo_cru():
    codigo = "flowchart TD\n    subgraph Grupo\n    A --> B\n    end\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_flow_orientacao_fora_do_subset_degrada_para_codigo_cru():
    # o renderer desenha espinha vertical; outra orientação fica no código cru
    codigo = "flowchart LR\n    A --> B\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_flow_sem_aresta_degrada_para_codigo_cru():
    codigo = "flowchart TD\n"
    assert parse_bloco(codigo) == {"tipo": "codigo", "codigo": codigo}


def test_fluxogramas_md_real_parseia_o_pipeline_de_ia():
    texto = (RAIZ / "docs" / "spec" / "snapshots" / "FLUXOGRAMAS.md").read_text(
        encoding="utf-8"
    )
    flows = [d for d in extrair_diagramas(texto) if d["tipo"] == "flow"]

    assert len(flows) == 1
    flow = flows[0]
    nos = {n["id"]: n for n in flow["nos"]}
    assert set(nos) == set("ABCDEFGHIJKLM")
    # a única decisão é o casamento de nomes, com as quebras de linha preservadas
    assert [n["id"] for n in flow["nos"] if n["decisao"]] == ["D"]
    assert nos["D"]["linhas"] == [
        "Todos os nomes",
        "casados com",
        "participantes do banco?",
    ]
    # ramos da decisão rotulados; o resto das arestas sem rótulo
    rotuladas = {
        (a["origem"], a["destino"]): a["rotulo"] for a in flow["arestas"] if a["rotulo"]
    }
    assert rotuladas == {("D", "E"): "nao", ("D", "F"): "sim"}
    # toda aresta liga nós presentes, o renderer confia nisso
    for a in flow["arestas"]:
        assert a["origem"] in nos and a["destino"] in nos


def test_snapshots_do_collect_servem_diagramas_junto_do_body():
    import collect

    docs = collect._snapshots(RAIZ)

    schema = next(d for d in docs if d["name"] == "SCHEMA")
    assert any(x["tipo"] == "er" for x in schema["diagramas"])
