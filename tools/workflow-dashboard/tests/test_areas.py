"""Parsers dos snapshots de área (areas.py) + contrato estático das capas.

Os parsers rodam contra fixtures no formato real dos docs de
docs/spec/snapshots/. O contrato do módulo é o mesmo do diagramas.py:
parse nunca quebra — corpo fora do formato degrada pra None e a SPA
mantém o markdown renderizado.
"""

from pathlib import Path

from areas import (
    fundir_colunas_no_er,
    parse_area,
    parse_entidades,
    parse_estrutura,
    parse_fluxogramas,
    parse_integracoes,
    parse_migrations,
    parse_rotas,
)

STATIC = Path(__file__).resolve().parents[1] / "static"
AREAS_JS = (STATIC / "areas.js").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


# ---------- ENTIDADES ----------

ENTIDADES_MD = """# ENTIDADES.md

## participantes

> Origem: `001_create_participantes.sql` (alterada em: 014_x.sql, 017_y.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `VARCHAR(10)` | PK | `gen_id()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `setor_id` | `UUID` | — | — | `setores.id` |

**Indexes:**
- `idx_p_email` em `(email)` (de `001_create_participantes.sql`)
"""


def test_entidades_extrai_ficha_completa():
    dados = parse_entidades(ENTIDADES_MD)
    (t,) = dados["tabelas"]
    assert t["nome"] == "participantes"
    assert t["origem"] == "001_create_participantes.sql"
    assert t["alteradas"] == ["014_x.sql", "017_y.sql"]
    assert [c["nome"] for c in t["colunas"]] == ["id", "nome", "setor_id"]
    assert t["colunas"][0]["pk"] and t["colunas"][0]["default"] == "gen_id()"
    assert t["colunas"][1]["nn"] and t["colunas"][1]["default"] is None
    assert t["colunas"][2]["fk_ref"] == "setores.id"
    assert t["indexes"][0]["nome"] == "idx_p_email"


def test_fundir_colunas_no_er_resolve_truncagem():
    docs = [
        {"name": "ENTIDADES", "dados": parse_entidades(ENTIDADES_MD)},
        {
            "name": "SCHEMA",
            "diagramas": [
                {
                    "tipo": "er",
                    "tabelas": [
                        {
                            "nome": "participantes",
                            "colunas": [{"nome": "id", "tipo": "VARCHAR", "pk": True, "fk": False}],
                            "extras": 2,
                        },
                        {"nome": "desconhecida", "colunas": [], "extras": 3},
                    ],
                    "relacoes": [],
                }
            ],
        },
    ]
    fundir_colunas_no_er(docs)
    er = docs[1]["diagramas"][0]
    assert len(er["tabelas"][0]["colunas"]) == 3  # ficha completa entrou
    assert er["tabelas"][0]["extras"] == 0
    assert er["tabelas"][0]["colunas"][2]["fk"] is True
    assert er["tabelas"][1]["extras"] == 3  # sem ficha: fica como veio


# ---------- ROTAS ----------

ROTAS_MD = """# ROTAS.md

## reunioes (`app/routers/reunioes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/reunioes` | Lista reuniões | ✅ |
| POST | `/reunioes/agendar` | Agenda | ❌ |
"""


def test_rotas_estrutura_grupos_e_auth():
    dados = parse_rotas(ROTAS_MD)
    (g,) = dados["grupos"]
    assert g["arquivo"] == "app/routers/reunioes.py"
    assert g["rotas"][0] == {"metodo": "GET", "rota": "/reunioes", "desc": "Lista reuniões", "auth": True}
    assert g["rotas"][1]["auth"] is False


# ---------- MIGRATIONS ----------

MIGRATIONS_MD = """
| # | Arquivo | Resumo | C | A | I | D |
|---|---------|--------|---|---|---|---|
| 1 | `001_a.sql` | Tabela a | 1 | 0 | 4 | 0 |
| 45 | `045_pops.sql` | POPs fundação | 2 | 1 | 4 | 1 |
"""


def test_migrations_vira_timeline():
    dados = parse_migrations(MIGRATIONS_MD)
    assert dados["migrations"][0]["n"] == 1
    m = dados["migrations"][1]
    assert (m["criadas"], m["alteradas"], m["indexes"], m["drops"]) == (2, 1, 4, 1)


# ---------- INTEGRACOES ----------

INTEGRACOES_MD = """# INTEGRACOES.md

## ClickSign
**Pra que serve:** Assinatura digital de atas
**Onde aparece no código:** `app/a.py`, `app/b.py`
**Secret/env primária:** `CLICKSIGN_API_KEY`
**Variáveis relacionadas:** `CLICKSIGN_BASE_URL`
"""


def test_integracoes_extrai_servicos():
    (s,) = parse_integracoes(INTEGRACOES_MD)["servicos"]
    assert s["nome"] == "ClickSign"
    assert s["papel"].startswith("Assinatura")
    assert s["onde"] == ["app/a.py", "app/b.py"]
    assert s["secret"] == "CLICKSIGN_API_KEY"
    assert s["relacionadas"] == ["CLICKSIGN_BASE_URL"]


# ---------- ESTRUTURA ----------

ESTRUTURA_MD = """# ESTRUTURA.md

## Backend (FastAPI)

Localização: `hospital-reunioes/backend/`

```
app/
├── routers/         # endpoints HTTP
├── services/        # lógica de negócio
tests/               # pytest
```
"""


def test_estrutura_vira_arvore_anotada():
    (sec,) = parse_estrutura(ESTRUTURA_MD)["secoes"]
    assert sec["local"] == "hospital-reunioes/backend/"
    assert sec["nos"][0] == {"nome": "app/", "nivel": 0, "dir": True, "comentario": ""}
    assert sec["nos"][1]["nome"] == "routers/"
    assert sec["nos"][1]["nivel"] == 1
    assert sec["nos"][1]["comentario"] == "endpoints HTTP"


# ---------- FLUXOGRAMAS ----------


def test_fluxogramas_extrai_estados_explicados():
    md = "- **PROGRAMADA** — reunião marcada na agenda.\n- **ERRO** — falha técnica."
    dados = parse_fluxogramas(md)
    assert dados["estados"]["PROGRAMADA"].startswith("reunião marcada")
    assert "ERRO" in dados["estados"]


# ---------- contrato geral ----------


def test_parse_area_nunca_quebra():
    assert parse_area("ENTIDADES", None) is None
    assert parse_area("ROTAS", "corpo sem tabela nenhuma") is None
    assert parse_area("DESCONHECIDO", "qualquer coisa") is None


def test_capas_existem_para_todas_as_areas():
    # cada área com dados estruturados tem renderer registrado na SPA
    for area in ("ROTAS", "ENTIDADES", "MIGRATIONS", "INTEGRACOES", "ESTRUTURA", "SCHEMA"):
        assert f"{area}:" in AREAS_JS.replace(" ", ""), f"sem renderer pra {area}"
    # FLUXOGRAMAS mantém o markdown, mas ganha o hover leigo nos estados
    assert "wireFluxogramas" in AREAS_JS
    assert "st-pop" in AREAS_JS


def test_fonte_do_snapshot_continua_acessivel():
    # visual-first não esconde nada: o markdown original fica no "ver fonte"
    assert "ver fonte" in APP_JS
