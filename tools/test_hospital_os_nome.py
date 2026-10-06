"""O painel se chama Hospital OS (issue #947, ADR 0062, decisão 1).

O nome vale na tela, no README do painel, no `CLAUDE.md` e no `/ask-pedro`.
O caminho `tools/workflow-dashboard/` continua: o que some é o nome antigo
("painel do fluxo", "painel do workflow", "workflow-dashboard" solto). O
vocabulário do painel (fase, funil, raia, tentativa) mora no README dele; o
`CONTEXT.md` segue glossário do hospital. Este teste varre todo arquivo
versionado.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
README = RAIZ / "tools/workflow-dashboard/README.md"

# "workflow-dashboard" colado em barra, ponto ou palavra é caminho ou
# identificador (`tools/workflow-dashboard/`, `com.<slug>.workflow-dashboard`,
# `workflow-dashboard.log`); solto, inclusive no fim da frase, é o nome antigo.
NOME_ANTIGO = re.compile(
    r"painel do fluxo|painel do workflow|(?<![/.\w-])workflow-dashboard(?![/\w-]|\.\w)",
    re.IGNORECASE,
)

# Onde o nome antigo é história.
EXCECOES = [
    "docs/adr/",  # registro do que foi decidido (a ADR 0025 diz "workflow-dashboard")
    "docs/spec/deploy/history.json",  # notas de deploys antigos
    "docs/spec/snapshots/",  # auto-gerado
    "tools/test_hospital_os_nome.py",  # este arquivo
]


def grep(padrao: str, excecoes: list[str]) -> list[str]:
    proc = subprocess.run(
        [
            "git",
            "grep",
            "-n",
            "-I",
            "-i",
            "-E",
            padrao,
            "--",
            ".",
            *(f":(exclude){e}" for e in excecoes),
        ],
        cwd=RAIZ,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert proc.returncode in (0, 1), proc.stderr  # 1: nada encontrado
    return proc.stdout.splitlines()


def nome_antigo(excecoes: list[str]) -> list[str]:
    linhas = grep("painel do fluxo|painel do workflow|workflow-dashboard", excecoes)
    # tira o prefixo `arquivo:linha:` antes de olhar o que vem antes da palavra
    return [li for li in linhas if NOME_ANTIGO.search(li.split(":", 2)[-1])]


def secao(texto: str, titulo: str) -> str:
    m = re.search(
        rf"^## {re.escape(titulo)}\n(.*?)(?=^## |\Z)", texto, re.DOTALL | re.MULTILINE
    )
    assert m, f"README do painel sem a seção '## {titulo}'"
    return m.group(1)


def test_a_varredura_acha_o_nome_antigo_quando_ele_existe():
    """Piso de sanidade: sem as exceções, a mesma busca acha a ADR 0025."""
    assert [li for li in nome_antigo([]) if li.startswith("docs/adr/0025-")]


def test_caminho_e_identificador_nao_contam_como_nome():
    for caminho in (
        "python3 tools/workflow-dashboard/serve.py",
        "`workflow-dashboard/` (painel)",
        'LABEL="com.hospital-reunioes.workflow-dashboard"',
        "~/Library/Logs/workflow-dashboard.log",
    ):
        assert not NOME_ANTIGO.search(caminho), caminho
    for nome in (
        "A aba Mapa do workflow-dashboard",
        "Abra o workflow-dashboard.",
        "# Aplicativo Hospital, painel do fluxo",
        "**Painel do workflow**",
    ):
        assert NOME_ANTIGO.search(nome), nome


def test_nenhum_arquivo_versionado_usa_o_nome_antigo_fora_das_excecoes():
    assert nome_antigo(EXCECOES) == []


def test_hospital_os_nas_superficies_da_adr():
    for caminho in (
        "tools/workflow-dashboard/static/index.html",
        "tools/workflow-dashboard/README.md",
        "CLAUDE.md",
        ".claude/skills/ask-pedro/SKILL.md",
    ):
        assert "Hospital OS" in (RAIZ / caminho).read_text(encoding="utf-8"), caminho
    assert README.read_text(encoding="utf-8").startswith("# Hospital OS\n")


def test_readme_tem_as_cinco_abas_com_a_fonte_de_cada_uma():
    abas = secao(README.read_text(encoding="utf-8"), "Abas")
    cabecalho = re.search(r"^\| *Aba *\|.*\| *Fonte *\|$", abas, re.MULTILINE)
    assert cabecalho, "seção Abas sem a tabela Aba | ... | Fonte"
    linhas = [li for li in abas[cabecalho.end() :].splitlines() if li.startswith("|")][
        1:
    ]  # pula o |---|
    celulas = [[c.strip() for c in li.strip("|").split("|")] for li in linhas]
    nomes = [re.sub(r"[*`]|\(.*?\)", "", c[0]).strip() for c in celulas]
    assert nomes == ["Issues", "PRs", "Produção", "Mapa", "Domínio"]
    for c in celulas:
        assert c[-1], f"aba {c[0]} sem fonte"


def test_readme_tem_o_vocabulario_do_painel():
    vocab = secao(README.read_text(encoding="utf-8"), "Vocabulário")
    termos = re.findall(r"^- \*\*(.+?)\*\*:", vocab, re.MULTILINE)
    for termo in (
        "Fase",
        "Funil",
        "Raia",
        "Tentativa",
        "Branch criada",
        "Cor da pessoa",
    ):
        assert termo in termos, f"vocabulário sem '{termo}'"


def test_vocabulario_do_plano_saiu_de_todo_lugar():
    assert (
        grep("Vocabulário do Plano", ["docs/adr/", "tools/test_hospital_os_nome.py"])
        == []
    )


def test_context_md_segue_glossario_do_hospital():
    assert "Hospital OS" not in (RAIZ / "CONTEXT.md").read_text(encoding="utf-8")
