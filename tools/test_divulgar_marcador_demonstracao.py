"""O link da Demonstração chega ao card pelo corpo da issue-raiz (ADR 0084, decisão 9).

No fim do `/divulgar`, `divulgar/scripts/marcar_demonstracao.py <issue> <url>` grava
`<!-- demonstracao: <url> -->` no corpo da issue. O webhook do app lê o marcador e o
card ganha o selo "Tem demonstração". Estes testes rodam o script como a sessão roda,
com um `gh` falso no PATH que guarda o corpo num arquivo.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "divulgar" / "scripts" / "marcar_demonstracao.py"
URL = "https://pendencia-hsm.vercel.app"


def _modulo():
    spec = importlib.util.spec_from_file_location("marcar_demonstracao", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_acrescenta_o_marcador_no_fim_do_corpo():
    corpo = _modulo().com_marcador("## O que construir\n\nTexto.\n", URL)
    assert corpo == f"## O que construir\n\nTexto.\n\n<!-- demonstracao: {URL} -->\n"


def test_troca_o_marcador_que_ja_existe_sem_duplicar():
    velho = 'Texto.\n\n<!-- demonstracao: https://velho.vercel.app -->\n\n<!-- demanda-vitta id="x" -->'
    corpo = _modulo().com_marcador(velho, URL)
    assert corpo.count("<!-- demonstracao:") == 1
    assert f"<!-- demonstracao: {URL} -->" in corpo
    assert '<!-- demanda-vitta id="x" -->' in corpo


def test_recusa_link_que_nao_e_https():
    with pytest.raises(ValueError):
        _modulo().com_marcador("Texto.", "http://pendencia-hsm.vercel.app")
    with pytest.raises(ValueError):
        _modulo().com_marcador("Texto.", "https://com espaco.vercel.app")


@pytest.fixture
def gh_falso(tmp_path):
    """Um `gh` que responde `api repos/.../issues/N` com o corpo guardado e grava o PATCH."""
    corpo = tmp_path / "corpo.md"
    corpo.write_text(
        '## O que construir\n\nTexto.\n\n<!-- demanda-vitta id="abc" -->',
        encoding="utf-8",
    )
    gh = tmp_path / "bin" / "gh"
    gh.parent.mkdir()
    gh.write_text(
        f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
corpo = {str(corpo)!r}
if args[:2] == ["repo", "view"]:
    print("dono/repo"); sys.exit(0)
if args[0] == "api" and "--input" in args:
    dados = json.load(open(args[args.index("--input") + 1]))
    open(corpo, "w", encoding="utf-8").write(dados["body"]); print("{{}}"); sys.exit(0)
if args[0] == "api":
    print(json.dumps({{"body": open(corpo, encoding="utf-8").read()}})); sys.exit(0)
sys.exit(2)
""",
        encoding="utf-8",
    )
    gh.chmod(0o755)
    return corpo, gh.parent


def test_grava_o_marcador_na_issue_pelo_gh(gh_falso):
    corpo, bin_dir = gh_falso
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "1548", URL],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    texto = corpo.read_text(encoding="utf-8")
    assert texto.endswith(f"<!-- demonstracao: {URL} -->\n")
    assert '<!-- demanda-vitta id="abc" -->' in texto


def test_link_ruim_sai_com_erro_sem_tocar_na_issue(gh_falso):
    corpo, bin_dir = gh_falso
    antes = corpo.read_text(encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "1548", "http://x.vercel.app"],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 1
    assert corpo.read_text(encoding="utf-8") == antes
    assert "https" in r.stderr
