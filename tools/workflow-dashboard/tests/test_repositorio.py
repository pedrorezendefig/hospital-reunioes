"""Aba Repositório (issue #596): árvore do git, resumos extraídos da fonte,
leitura segura de arquivo e diagnóstico da máquina sob demanda.

Os testes rodam contra um repositório git de fixture em tmp_path: nada aqui
lê a árvore real do projeto.
"""

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import repositorio  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Repo git com pastas de nível 1 e 2, um .env ignorado e um README com tabelas."""
    _git(tmp_path, "init", "-q")
    (tmp_path / ".gitignore").write_text("*.env\n/local/\n/tokens/.env\n", encoding="utf-8")
    (tmp_path / "docs" / "adr").mkdir(parents=True)
    (tmp_path / "docs" / "adr" / "0001-x.md").write_text("---\nstatus: accepted\n---\n\n# Primeira decisão\n\nCorpo.\n", encoding="utf-8")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text('"""Sobe o app."""\nprint(1)\n', encoding="utf-8")
    (tmp_path / "app" / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "tokens").mkdir()
    (tmp_path / "tokens" / ".env.example").write_text("X=\n", encoding="utf-8")
    (tmp_path / "tokens" / ".env").write_text("X=segredo\n", encoding="utf-8")
    (tmp_path / "local").mkdir()
    (tmp_path / "local" / "dump.sql").write_text("select 1;", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "# Mapa\n\n## Raiz\n\n"
        "| Pasta ou arquivo | O que é | Por que existe | O que você acha dentro | Para que serve no dia a dia |\n"
        "|---|---|---|---|---|\n"
        "| `README.md` | Este mapa | Quem clona precisa saber | O que você está lendo | Primeiro dia |\n"
        "| `docs/` | Documentação viva | Ver seção abaixo | | |\n"
        "| `tokens/` | Tokens da **máquina** | O deploy fala com o Coolify | `.env.example` | Preencher uma vez |\n\n"
        "## `docs/`\n\n"
        "| Pasta | O que é | Por que existe | O que tem | Quando abrir |\n|---|---|---|---|---|\n"
        "| `adr/` | Decisões de arquitetura e domínio | Decisão sem registro é re-litigada | um `.md` por decisão | Antes de propor mudança |\n",
        encoding="utf-8",
    )
    _git(tmp_path, "add", "-A")
    return tmp_path


# ---------- 1. árvore vem do git e esconde o ignorado ----------


def test_arvore_lista_pastas_de_nivel_1_e_2_que_o_git_conhece(repo):
    arv = repositorio.arvore(repo)
    pastas = {p["path"] for p in arv["pastas"]}
    assert {"docs", "docs/adr", "app", "tokens"} <= pastas


def test_arvore_nao_mostra_env_tokens_env_nem_local(repo):
    arv = repositorio.arvore(repo)
    arquivos = {a["path"] for p in arv["pastas"] for a in p["arquivos"]}
    assert "app/.env" not in arquivos
    assert "tokens/.env" not in arquivos
    assert "tokens/.env.example" in arquivos
    assert not any(p["path"].startswith("local") for p in arv["pastas"])


# ---------- 2. resumo de pasta vem da tabela do README ----------


def test_resumo_de_pasta_vem_da_linha_do_readme(repo):
    readme = (repo / "README.md").read_text(encoding="utf-8")
    r = repositorio.resumo_pasta(readme, "docs/adr")
    assert r["o_que_e"] == "Decisões de arquitetura e domínio"
    assert r["por_que"] == "Decisão sem registro é re-litigada"
    assert r["para_que"] == "Antes de propor mudança"


def test_pasta_de_raiz_casa_com_barra_final_e_markdown_da_celula(repo):
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert repositorio.resumo_pasta(readme, "tokens")["o_que_e"] == "Tokens da máquina"


def test_pasta_sem_linha_no_readme_devolve_sem_resumo(repo):
    readme = (repo / "README.md").read_text(encoding="utf-8")
    assert repositorio.resumo_pasta(readme, "app")["o_que_e"] == "sem resumo"


def test_arvore_carrega_o_resumo_de_cada_pasta(repo):
    por_path = {p["path"]: p for p in repositorio.arvore(repo)["pastas"]}
    assert por_path["docs/adr"]["resumo"]["o_que_e"] == "Decisões de arquitetura e domínio"
    assert por_path["app"]["resumo"]["o_que_e"] == "sem resumo"


# ---------- 3. resumo de arquivo vem da fonte ----------


def test_skill_resume_pela_description_do_frontmatter():
    txt = "---\nname: deploy\ndescription: Deploy via Coolify. Modos: ship, status.\n---\n\n# Deploy\n\nTexto longo.\n"
    assert repositorio.resumo_arquivo("x/SKILL.md", txt) == "Deploy via Coolify. Modos: ship, status."


def test_python_resume_pela_docstring_da_primeira_linha():
    txt = '#!/usr/bin/env python3\n"""Coleta tudo que o workflow produz.\n\nDetalhe.\n"""\nimport os\n'
    assert repositorio.resumo_arquivo("tools/collect.py", txt) == "Coleta tudo que o workflow produz."


def test_html_resume_pelo_title():
    txt = "<!doctype html><html><head><title>Manual da Ouvidoria</title></head><body></body></html>"
    assert repositorio.resumo_arquivo("docs/manual/index.html", txt) == "Manual da Ouvidoria"


def test_markdown_resume_por_titulo_mais_primeiro_paragrafo():
    txt = "# Versionamento\n\nComo a versão é decidida, exibida e documentada.\n\n## Regra\n"
    assert repositorio.resumo_arquivo("docs/spec/VERSIONING.md", txt) == (
        "Versionamento. Como a versão é decidida, exibida e documentada."
    )


def test_adr_com_frontmatter_sem_description_resume_pelo_titulo_e_paragrafo():
    txt = "---\nstatus: accepted\namends: 0044\n---\n\n# O README é o mapa\n\nO mapa nasceu escondido.\n"
    assert repositorio.resumo_arquivo("docs/adr/0046-x.md", txt) == "O README é o mapa. O mapa nasceu escondido."


def test_arquivo_sem_nada_devolve_sem_resumo():
    assert repositorio.resumo_arquivo("app/x.ts", "export const a = 1;\n") == "sem resumo"
    assert repositorio.resumo_arquivo("app/y.py", "import os\nprint(1)\n") == "sem resumo"


def test_arvore_carrega_o_resumo_de_cada_arquivo(repo):
    por_path = {p["path"]: p for p in repositorio.arvore(repo)["pastas"]}
    main = next(a for a in por_path["app"]["arquivos"] if a["path"] == "app/main.py")
    assert main["resumo"] == "Sobe o app."


# ---------- link da Vercel só quando a URL está na fonte ----------


def test_link_vercel_vem_do_proprio_arquivo_ou_do_readme_da_pasta():
    assert repositorio.link_vercel("veja https://ouvidoria-hsm.vercel.app/x hoje", "") == "https://ouvidoria-hsm.vercel.app/x"
    assert repositorio.link_vercel("nada aqui", "publicado em https://manual-hsm.vercel.app.") == "https://manual-hsm.vercel.app"
    assert repositorio.link_vercel("nada", "nada") is None


# ---------- 4. ler arquivo: só o rastreado pelo git, com teto ----------


def test_ler_arquivo_serve_o_rastreado_pelo_git(repo):
    r = repositorio.ler_arquivo(repo, "app/main.py")
    assert r["conteudo"] == '"""Sobe o app."""\nprint(1)\n'
    assert r["tipo"] == "texto"


def test_ler_arquivo_recusa_ponto_ponto_absoluto_ignorado_e_symlink_para_fora(repo, tmp_path_factory):
    fora = tmp_path_factory.mktemp("fora")
    (fora / "segredo.txt").write_text("x", encoding="utf-8")
    (repo / "app" / "link.txt").symlink_to(fora / "segredo.txt")
    _git(repo, "add", "app/link.txt")
    assert repositorio.ler_arquivo(repo, "../fora/segredo.txt") is None
    assert repositorio.ler_arquivo(repo, str(repo / "app" / "main.py")) is None
    assert repositorio.ler_arquivo(repo, "app/.env") is None
    assert repositorio.ler_arquivo(repo, "tokens/.env") is None
    assert repositorio.ler_arquivo(repo, "app/link.txt") is None


def test_ler_arquivo_acima_do_teto_devolve_so_o_aviso(repo):
    (repo / "app" / "grande.txt").write_text("a" * (repositorio.TETO_BYTES + 1), encoding="utf-8")
    _git(repo, "add", "app/grande.txt")
    r = repositorio.ler_arquivo(repo, "app/grande.txt")
    assert r["tipo"] == "grande"
    assert "conteudo" not in r


def test_ler_arquivo_binario_devolve_so_o_aviso(repo):
    (repo / "app" / "logo.png").write_bytes(b"\x89PNG\x00\x00binario")
    _git(repo, "add", "app/logo.png")
    r = repositorio.ler_arquivo(repo, "app/logo.png")
    assert r["tipo"] == "binario"
    assert "conteudo" not in r


def test_ler_arquivo_classifica_markdown_e_html(repo):
    (repo / "docs" / "p.html").write_text("<title>P</title>", encoding="utf-8")
    _git(repo, "add", "docs/p.html")
    assert repositorio.ler_arquivo(repo, "README.md")["tipo"] == "markdown"
    assert repositorio.ler_arquivo(repo, "docs/p.html")["tipo"] == "html"


# ---------- 5. diagnóstico: quatro classes de linha, só sob demanda ----------

SAIDA_DIAGNOSTICO = (
    "\nNível 1: pipeline (issues, tdd, PR)\n"
    "  OK     git                                \n"
    "  FALTA  clone atualizado                   main está 2 commit(s) atrás: git pull --ff-only origin main\n"
    "  AVISO  tokens/.env: ANA_API_KEY           só para smoke test contra prod\n"
    "\nNível 3: app local (opcional, hoje ninguém usa)\n"
    "  OPC    docker no ar                       instale o Docker Desktop e abra\n"
    "\n1 item(ns) obrigatório(s) faltando. Conserte um por vez, com confirmação.\n"
)


def test_parse_diagnostico_separa_as_quatro_classes_com_nome_conserto_e_secao():
    itens = repositorio.parse_diagnostico(SAIDA_DIAGNOSTICO)
    assert [i["classe"] for i in itens] == ["OK", "FALTA", "AVISO", "OPC"]
    falta = itens[1]
    assert falta["nome"] == "clone atualizado"
    assert falta["conserto"] == "main está 2 commit(s) atrás: git pull --ff-only origin main"
    assert falta["secao"] == "Nível 1: pipeline (issues, tdd, PR)"
    assert itens[0]["conserto"] == ""
    assert itens[3]["secao"].startswith("Nível 3")


def test_parse_diagnostico_nao_corta_nome_maior_que_a_coluna():
    # o script imprime %-34s: nome maior que 34 letras vaza da coluna sem padding
    saida = "  OK     clone atualizado (main = origin/main) \n  FALTA  hospital-reunioes/.env existe      printf 'x' > hospital-reunioes/.env\n"
    itens = repositorio.parse_diagnostico(saida)
    assert itens[0]["nome"] == "clone atualizado (main = origin/main)" and itens[0]["conserto"] == ""
    assert itens[1]["nome"] == "hospital-reunioes/.env existe"
    assert itens[1]["conserto"] == "printf 'x' > hospital-reunioes/.env"


def _script_fake(repo: Path, corpo: str) -> Path:
    s = repo / ".claude" / "skills" / "setup-maquina" / "scripts" / "diagnostico.sh"
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text("#!/usr/bin/env bash\n" + corpo, encoding="utf-8")
    s.chmod(0o755)
    return s


def test_rodar_diagnostico_executa_o_script_e_devolve_itens_com_hora(repo):
    _script_fake(repo, "printf '%s' \"$SAIDA\"\nexit 1\n")
    import os
    os.environ["SAIDA"] = SAIDA_DIAGNOSTICO
    try:
        r = repositorio.rodar_diagnostico(repo)
    finally:
        del os.environ["SAIDA"]
    assert r["faltas"] == 1
    assert [i["classe"] for i in r["itens"]] == ["OK", "FALTA", "AVISO", "OPC"]
    assert r["quando"]


def test_coleta_normal_nao_roda_o_script_de_diagnostico(repo):
    marca = repo / "rodou.txt"
    _script_fake(repo, f"touch '{marca}'\n")
    import collect
    collect.collect(repo)
    assert not marca.exists(), "a coleta do /api/data disparou o diagnóstico"


def test_coleta_traz_a_arvore_do_repositorio(repo):
    import collect
    data = collect.collect(repo)
    assert {p["path"] for p in data["repositorio"]["pastas"]} >= {"docs/adr", "app"}


# ---------- rotas: /api/arquivo e /api/diagnostico ----------


@pytest.fixture
def servidor(repo, monkeypatch):
    import json
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError

    import serve
    monkeypatch.setattr(serve, "ROOT", repo)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"

    def chamar(path, method="GET"):
        try:
            with urlopen(Request(base + path, method=method), timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except HTTPError as e:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")

    yield chamar
    srv.shutdown()


def test_rota_arquivo_serve_rastreado_e_recusa_o_resto(servidor, repo):
    status, corpo = servidor("/api/arquivo?path=app/main.py")
    assert status == 200 and corpo["conteudo"].startswith('"""Sobe o app."""')
    for ruim in ("../x", "/etc/passwd", "app/.env", "tokens/.env", "nao/existe.md"):
        status, _ = servidor(f"/api/arquivo?path={ruim}")
        assert status == 404, ruim


def test_rota_arquivo_acima_do_teto_e_binario_respondem_so_o_aviso(servidor, repo):
    (repo / "app" / "grande.txt").write_text("a" * (repositorio.TETO_BYTES + 1), encoding="utf-8")
    (repo / "app" / "logo.png").write_bytes(b"\x89PNG\x00\x00")
    _git(repo, "add", "app/grande.txt", "app/logo.png")
    status, corpo = servidor("/api/arquivo?path=app/grande.txt")
    assert status == 200 and corpo["tipo"] == "grande" and "conteudo" not in corpo
    status, corpo = servidor("/api/arquivo?path=app/logo.png")
    assert status == 200 and corpo["tipo"] == "binario" and "conteudo" not in corpo


def test_rota_diagnostico_roda_o_script_so_no_post(servidor, repo):
    marca = repo / "rodou.txt"
    _script_fake(repo, f"touch '{marca}'\nprintf '  OK     git                                \\n'\n")
    status, _ = servidor("/api/data")
    assert status == 200 and not marca.exists()
    status, corpo = servidor("/api/diagnostico", method="POST")
    assert status == 200 and marca.exists()
    assert corpo["itens"][0]["classe"] == "OK" and corpo["quando"]
    status, corpo = servidor("/api/diagnostico")  # GET devolve o último resultado, sem rodar de novo
    marca.unlink()
    assert status == 200 and corpo["itens"][0]["nome"] == "git" and not marca.exists()
