"""Aba Repositório (issue #596): contrato estático do front, no estilo da suíte
(estrutura e contrato, nunca pixel): aba registrada, render com árvore e
detalhe, arquivo aberto na própria aba (markdown, texto, HTML em quadro
isolado), diagnóstico só por botão, referência a ADR levando ao Domínio,
e o README do painel listando a aba.
"""

import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
STATIC = HERE / "static"
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")
APP_JS = (STATIC / "app.js").read_text(encoding="utf-8")
CSS = (STATIC / "style.css").read_text(encoding="utf-8")
README = (HERE / "README.md").read_text(encoding="utf-8")


def _fn(nome: str) -> str:
    m = re.search(rf"function {nome}\([^)]*\)[\s\S]*?\n\}}", APP_JS)
    assert m, f"app.js sem {nome}"
    return m.group(0)


# ---------- aba registrada ----------


def test_aba_repositorio_existe_nas_tabs_e_no_render():
    assert '<button data-tab="repositorio">Repositório</button>' in INDEX
    assert re.search(r"const TABS = \[[^\]]*'repositorio'", APP_JS)
    assert re.search(r"repositorio:\s*renderRepositorio", APP_JS)


# ---------- árvore com resumo e detalhe ----------


def test_render_mostra_arvore_com_resumo_do_readme_e_detalhe_da_selecao():
    corpo = _fn("renderRepositorio")
    assert "S.data.repositorio" in corpo, "não lê a árvore coletada"
    assert 'data-act="rpasta"' in APP_JS, "pasta sem ação de abrir"
    assert 'data-act="rarq"' in APP_JS, "arquivo sem ação de abrir"
    assert "o_que_e" in APP_JS and "para_que" in APP_JS, "resumo do README não aparece"


def test_arquivo_tem_links_abrir_aqui_e_github_e_vercel_so_quando_existe():
    assert "/blob/main/" in APP_JS, "sem link GitHub na main"
    m = re.search(r"a\.vercel\s*\?", APP_JS) or re.search(r"\.vercel\s*\?", APP_JS)
    assert m, "link Vercel precisa ser condicional à URL extraída"


# ---------- abrir aqui: markdown, texto, html em quadro isolado ----------


def test_lista_de_arquivos_da_pasta_vem_sob_demanda_ao_clicar():
    assert "/api/pasta?path=" in APP_JS, "a lista de arquivos precisa vir da rota, não da coleta"
    assert "n_arquivos" in _fn("renderRepositorio"), "a árvore mostra só a contagem"


def test_abrir_aqui_busca_a_rota_de_arquivo_e_desenha_por_tipo():
    assert "/api/arquivo?path=" in APP_JS
    assert re.search(r"tipo === 'markdown'[\s\S]*?md\(", APP_JS), "markdown não passa pelo marked"
    assert re.search(r"<iframe[^>]*sandbox[^>]*srcdoc", APP_JS) or re.search(r"<iframe[^>]*srcdoc[^>]*sandbox", APP_JS), \
        "HTML precisa rodar num iframe sandbox com srcdoc"
    assert re.search(r"tipo === 'grande'|tipo === 'binario'", APP_JS), "aviso de teto/binário sem tratamento"
    # frontmatter de ADR/skill não pode virar título: sai como linha de metadados antes do markdown
    fn = _fn("arqConteudoHtml")
    assert re.search(r"\^---\\n", fn) and "docmeta" in fn, "frontmatter não é separado do markdown"


# ---------- referência a ADR leva ao Domínio ----------


def test_referencia_a_adr_no_resumo_vira_link_para_a_aba_dominio():
    fn = _fn("adrLinks")
    assert "ADR" in fn and 'data-act="gotab"' in fn and 'data-go="dominio"' in fn
    assert "adrLinks(" in _fn("renderRepositorio") or "adrLinks(" in _fn("arqDetalheHtml")


# ---------- diagnóstico: botão, POST, cartões nas três cores ----------


def test_diagnostico_so_roda_pelo_botao_com_post():
    assert 'data-act="diag"' in APP_JS, "sem botão de rodar diagnóstico"
    assert re.search(r"fetch\('/api/diagnostico',\s*\{\s*method:\s*'POST'", APP_JS)
    # só o handler do botão faz o POST: uma ocorrência, e nenhuma na carga inicial
    assert len(re.findall(r"method:\s*'POST'", APP_JS)) == 1
    assert "diagnostico" not in _fn("load"), "a carga inicial não pode disparar o diagnóstico"


def test_cartoes_do_diagnostico_nas_tres_cores_com_conserto_copiavel():
    assert re.search(r"diag-ok", APP_JS) and re.search(r"diag-aviso", APP_JS) and re.search(r"diag-falta", APP_JS)
    assert re.search(r"\.diag-ok\{[^}]*var\(--green", CSS)
    assert re.search(r"\.diag-aviso\{[^}]*var\(--amber", CSS)
    assert re.search(r"\.diag-falta\{[^}]*var\(--red", CSS)
    fn = _fn("diagHtml")
    assert "copyBlock(" in fn, "conserto sem botão de copiar"
    assert "quando" in fn, "sem hora da última rodada"


# ---------- README do painel ----------


def test_readme_do_painel_lista_a_aba_e_o_nome_novo():
    assert README.startswith("# Aplicativo Hospital")
    assert "**Repositório**" in README
    assert "setup de máquina nova" not in README.split("**Guia**")[1].split("\n")[0]
