"""O `/ship` para no PR verde e o rabo é o `fechar_onda.py` (issue #907, ADR 0061).

Skill não executa nada aqui: é instrução que um agente segue num terminal.
Flag que sumiu e continua sendo passada, passo de merge esquecido no meio do
texto, comando do rabo com opção que o script não tem: tudo isso só apareceria
na hora de subir para produção. Estes testes leem as skills e provam aqui.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SKILLS = RAIZ / ".claude" / "skills"
AGENTES = RAIZ / ".claude" / "agents"
FECHAR_ONDA = ".claude/skills/onda-enxuta/scripts/fechar_onda.py"

FLAGS_QUE_SUMIRAM = ["--no-bump", "--no-deploy", "--no-merge", "--bump-manual"]


def texto(skill: str) -> str:
    return (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")


def secao(md: str, titulo: str) -> str:
    """De um `## <titulo>` até o próximo `## `."""
    achado = re.search(rf"^## {re.escape(titulo)}.*?(?=^## |\Z)", md, re.S | re.M)
    assert achado, f"seção ausente: {titulo}"
    return achado.group(0)


def ajuda_do_rabo() -> str:
    proc = subprocess.run(
        [sys.executable, str(RAIZ / FECHAR_ONDA), "--help"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc.stdout


def comandos_do_rabo(md: str) -> list[str]:
    return [li.strip() for li in md.splitlines()
            if "fechar_onda.py" in li and re.search(r"python3? ", li)]


def conferir_comando(comando: str, ajuda: str) -> None:
    caminho = re.search(r"(\S*fechar_onda\.py)", comando).group(1).strip("`")
    assert caminho == FECHAR_ONDA, comando
    assert (RAIZ / caminho).exists()
    opcoes = set(re.findall(r"(--[a-z-]+)", comando))
    assert "--prs" in opcoes, comando
    assert "--sessao" not in opcoes, "PR avulso não passa sessão: " + comando
    assert [o for o in opcoes if o not in ajuda] == [], comando


# ---------------------------------------------------------------- /ship

def test_ship_nao_aceita_mais_no_bump_no_deploy_no_merge_e_mantem_skip_review():
    ship = texto("ship")
    assert [f for f in FLAGS_QUE_SUMIRAM if f in ship] == []
    opcoes = secao(ship, "Sintaxe")
    assert re.search(r"^\| `--skip-review` \|", opcoes, re.M), "a tabela de opções mantém o --skip-review"
    assert "--skip-review" in re.search(r"^description: (.+)$", ship, re.M).group(1)


def test_ship_termina_no_pr_verde_sem_bump_app_version_merge_nem_deploy():
    ship = texto("ship")
    proibidos = [
        "gh pr merge",
        "--approve",
        "pulls/",  # merge pela API
        "coolify app env",
        "chore(release): bump",
        '["version"] =',
    ]
    assert [p for p in proibidos if p in ship] == []
    blocos = re.findall(r"```(?:bash)?\n(.*?)```", ship, re.S)
    assert [b for b in blocos if "/deploy" in b] == [], "nenhum bloco chama o /deploy"
    passos = re.findall(r"^## (Passo [^\n]*)", ship, re.M)
    assert passos, "o /ship ainda é uma sequência de passos"
    assert [p for p in passos if re.search(r"bump|APP_VERSION|merge|deploy", p, re.I)] == []


def test_ship_imprime_o_comando_do_rabo_com_opcoes_que_o_script_tem():
    ship = texto("ship")
    ajuda = ajuda_do_rabo()
    saida = secao(ship, "Output final")
    comandos = comandos_do_rabo(saida)
    assert comandos, "o resumo final imprime o comando do rabo"
    for comando in comandos_do_rabo(ship):
        conferir_comando(comando, ajuda)


def test_quem_chama_o_ship_nao_passa_flag_que_sumiu():
    fontes = sorted(AGENTES.glob("*.md")) + sorted(SKILLS.glob("**/*.md"))
    assert len(fontes) > 20, "piso de sanidade da varredura"
    achados = [
        f"{arq.relative_to(RAIZ)}: {li.strip()[:120]}"
        for arq in fontes
        for li in arq.read_text(encoding="utf-8").splitlines()
        if "/ship" in li and any(f in li for f in FLAGS_QUE_SUMIRAM)
    ]
    assert achados == []


# -------------------------------------------------------------- /deploy

def test_deploy_ship_aponta_para_o_fechar_onda_e_sai():
    deploy = texto("deploy")
    ship = secao(deploy, "Modo `ship`")
    assert "### " not in ship, "o modo ship não tem mais passos próprios"
    for proibido in ("git push", "coolify ", "semaforo.sh"):
        assert proibido not in ship, proibido
    comandos = comandos_do_rabo(ship)
    assert len(comandos) == 1, comandos
    conferir_comando(comandos[0], ajuda_do_rabo())
    linha = next(li for li in deploy.splitlines() if li.startswith("| `/deploy` |"))
    assert "fechar_onda.py" in linha, linha


def test_deploy_mantem_status_rollback_e_setup_e_os_passos_que_eles_usam():
    deploy = texto("deploy")
    for modo in ("status", "rollback", "setup"):
        assert re.search(rf"^## Modo `{modo}`", deploy, re.M), modo
        assert re.search(rf"^\| `/deploy {modo}` \|", deploy, re.M), modo
    for ref in ("modo-rollback.md", "modo-setup.md"):
        assert (SKILLS / "deploy" / "references" / ref).exists()
    # o rollback monitora pelo Passo 5 e confere pelo Passo 7; o setup, pelo 5
    for passo in ("### Passo 5", "### Passo 7", "### Passo 8"):
        assert re.search(rf"^{passo}\b", deploy, re.M), passo
    descricao = re.search(r"^description: (.+)$", deploy, re.M).group(1)
    assert "fechar_onda.py" in descricao
    for modo in ("status", "rollback", "setup"):
        assert modo in descricao
