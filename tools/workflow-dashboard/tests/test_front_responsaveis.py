"""Aba Issues agrupada por responsável (issue #908, ADR 0061).

O agrupamento é calculado no módulo puro responsaveis.py e chega pronto em
/api/data como S.data.responsaveis; o front só filtra (matchIssue) e desenha.
Mesmo molde de test_front_plano_issues.py: corpo das functions do app.js
extraído por contagem de chaves e conferido por substring.
"""

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parents[1] / "static"
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")


def _bloco(i):
    """Do primeiro "{" a partir de i até a chave que o fecha."""
    j = APP_JS.index("{", i)
    depth = 0
    for k in range(j, len(APP_JS)):
        if APP_JS[k] == "{":
            depth += 1
        elif APP_JS[k] == "}":
            depth -= 1
            if depth == 0:
                return APP_JS[i:k + 1]
    raise AssertionError("bloco sem fechamento")


def _fn(nome):
    i = APP_JS.find(f"function {nome}(")
    assert i >= 0, f"app.js sem function {nome}"
    return _bloco(i)


def _ramo(act):
    """Ramo do despacho de cliques para um data-act."""
    i = APP_JS.find(f"act === '{act}'")
    assert i >= 0, f"despacho sem act === '{act}'"
    return _bloco(i)


# ---------- botão e estado ----------


def test_botao_agrupar_por_responsavel_na_aba_issues():
    controles = _fn("renderIssues")
    m = re.search(r'<button class="fchip[^>]*data-act="fagrupar"[^>]*>([^<]*)</button>', controles)
    assert m, "aba Issues sem o botão fchip data-act=fagrupar"
    assert m.group(1).strip() == "agrupar por responsável"
    assert "${f.agrupar ? 'on' : ''}" in m.group(0), "botão não acende pelo estado da aba"
    assert 'aria-pressed="${f.agrupar}"' in m.group(0), "botão de alternância sem aria-pressed"


def test_agrupar_ligado_por_padrao_junto_dos_filtros():
    m = re.search(r"fIssues: \{([^}]*)\}", APP_JS)
    assert m, "estado S.fIssues sumiu"
    assert "agrupar: true" in m.group(1), "agrupamento não nasce ligado no estado dos filtros"
    # vindo de outra aba (gotab) os filtros são recriados: a escolha de agrupar sobrevive
    assert "agrupar: S.fIssues.agrupar" in _ramo("gotab")


def test_desligado_volta_a_lista_atual_sem_perder_filtro_nem_busca():
    lista = _fn("issueListHtml")
    corpo = lista[lista.index("{") + 1:].strip()
    assert corpo.startswith("if (S.fIssues.agrupar && S.data.responsaveis) return responsaveisHtml();"), \
        "issueListHtml não desvia para os grupos só com o botão ligado"
    # o resto é a árvore PRD > fatias + issues avulsas de antes, intacta
    for trecho in ("prd-group", "children", "issues avulsas", "filter(matchIssue)"):
        assert trecho in lista, f"lista plana perdeu {trecho!r}"
    # alternar o botão só mexe no agrupar: estado, label e busca ficam
    ramo = _ramo("fagrupar")
    assert "S.fIssues.agrupar = !S.fIssues.agrupar" in ramo
    assert not re.search(r"S\.fIssues(\.(state|label|q))?\s*=[^=]", ramo.replace("S.fIssues.agrupar =", "")), \
        "alternar o agrupamento reescreve filtro ou busca"


# ---------- grupos ----------


def test_filtro_de_estado_label_e_busca_antes_do_agrupamento():
    grupos = _fn("responsaveisHtml")
    # cada item do grupo passa pelo mesmo matchIssue da lista plana antes de virar card
    assert "g.itens.filter(it => byN[it.number] && matchIssue(byN[it.number]))" in grupos
    assert "if (!itens.length) continue;" in grupos, "grupo sem nenhum item no filtro continua aparecendo"
    assert "g.itens.map(" not in grupos, "card desenhado a partir da lista sem filtro"
    # e o matchIssue cobre abertas, fechadas e todas, label e busca por título ou número
    filtro = _fn("matchIssue")
    assert "f.state !== 'all' && i.state !== f.state" in filtro
    assert "i.labels.includes(f.label)" in filtro
    assert "`#${i.number} ${i.title}`" in filtro


def test_um_grupo_por_responsavel_mais_sem_responsavel_abertos_ao_nascer():
    grupos = _fn("responsaveisHtml")
    assert "for (const g of r.grupos)" in grupos, "grupos não vêm de S.data.responsaveis"
    assert "g.responsavel ? esc(g.responsavel) : 'sem responsável'" in grupos
    # aberto ao nascer: só fecha o que o usuário fechou
    assert re.search(r"const S = \{[^;]*respFechado: new Set\(\)", APP_JS, re.S), "estado dos grupos fechados sumiu"
    assert "const aberto = !S.respFechado.has(chave);" in grupos
    m = re.search(r'<button class="resp-toggle[ "][^>]*>', grupos)
    assert m, "grupo sem cabeçalho clicável"
    assert 'data-act="resp"' in m.group(0) and 'aria-expanded="${aberto}"' in m.group(0)
    assert "${aberto ? `" in grupos, "cards do grupo não somem com o grupo fechado"
    ramo = _ramo("resp")
    assert "S.respFechado.delete(" in ramo and "S.respFechado.add(" in ramo
    assert "refreshIssueList()" in ramo
