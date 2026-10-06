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

import pytest

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


# ---------------------------------------------------------- /onda-enxuta

def test_onda_enxuta_chama_o_rabo_so_com_opcoes_que_o_script_tem():
    onda = texto("onda-enxuta")
    ajuda = ajuda_do_rabo()
    trechos = re.findall(r"fechar_onda\.py([^`]*)`", onda)
    assert len(trechos) >= 2, "o fechamento e a tabela de scripts citam o comando"
    opcoes = {o for t in trechos for o in re.findall(r"(--[a-z-]+)", t)}
    assert "--prs" in opcoes and "--sessao" in opcoes, opcoes
    assert sorted(o for o in opcoes if o not in ajuda) == []


def test_onda_enxuta_descreve_o_rabo_que_grava_so_history_e_state():
    """ADR 0062, decisões 9 e 10: o fechamento descreve o rabo enxuto."""
    fechamento = re.search(r"^### 6\. Fechamento da onda.*?(?=^### )", texto("onda-enxuta"),
                           re.S | re.M).group(0)
    item = next(li for li in fechamento.splitlines() if "fechar_onda.py --prs" in li)
    assert "history.json" in item and "state.json" in item, item
    for termo in ("changelog", "publicar.sh", "best-effort"):
        assert termo not in item.lower(), termo


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


# ------------------------------------------- versão sem commit (#967)

# A versão não vira commit: vive no APP_VERSION dos dois apps e na tag do
# squash. Texto que ainda manda commitar o bump, ou ler a versão do
# package.json congelado, ensinaria o agente a refazer a corrida de bump.
COMMIT_DE_BUMP = re.compile(
    r"chore\(release\)|commit (de|do) bump|bump (como|vira um|em) commit|bump na branch"
    r"|bump fantasma|re-bump|escrever_versao|PACKAGE_JSON|frontend/package\.json'\)\)\['version'\]",
    re.I,
)
FONTES_DO_RABO = [
    FECHAR_ONDA,
    ".claude/skills/ship/SKILL.md",
    ".claude/skills/deploy/SKILL.md",
    ".claude/skills/onda-enxuta/SKILL.md",
    "CLAUDE.md",
    "docs/onboarding/dev.md",
    "docs/onboarding/claude-setup.md",
    "docs/spec/VERSIONING.md",
]


def test_nenhuma_referencia_viva_a_commit_de_bump():
    achados = [
        f"{rel}:{n}: {li.strip()[:120]}"
        for rel in FONTES_DO_RABO
        for n, li in enumerate((RAIZ / rel).read_text(encoding="utf-8").splitlines(), 1)
        if COMMIT_DE_BUMP.search(li)
    ]
    assert achados == [], "\n".join(achados)


# ------------------------------------------- rabo PR a PR (#989)

# ADR 0064, decisão 3: cada PR do lote entra pela API no próprio número. Texto
# que ainda fala da branch de lote ou do PR que a embrulhava ensina o agente a
# procurar um PR que o rabo não abre mais.
LOTE_EMBRULHADO = re.compile(r"\bonda/|\bde entrega\b", re.I)


@pytest.mark.parametrize("rel", [FECHAR_ONDA, ".claude/skills/onda-enxuta/SKILL.md",
                                 ".claude/skills/ship/SKILL.md", "CLAUDE.md"])
def test_nenhuma_referencia_viva_a_branch_onda_nem_ao_pr_de_entrega(rel):
    assert LOTE_EMBRULHADO.search("merge local na branch `onda/<sessao>`")
    assert LOTE_EMBRULHADO.search("abre o PR de entrega")
    achados = [
        f"{rel}:{n}: {li.strip()[:120]}"
        for n, li in enumerate((RAIZ / rel).read_text(encoding="utf-8").splitlines(), 1)
        if LOTE_EMBRULHADO.search(li)
    ]
    assert achados == [], "\n".join(achados)


def test_onda_enxuta_e_claude_md_descrevem_o_merge_pr_a_pr():
    fechamento = fechamento_da_onda()
    item = next(li for li in fechamento.splitlines() if "fechar_onda.py --prs" in li)
    assert "PR a PR" in item and "intermediário" in item, item
    assert "PR a PR" in next(li for li in (RAIZ / "CLAUDE.md").read_text(encoding="utf-8").splitlines()
                             if "Modo AFK" in li)


def test_o_rabo_grava_app_version_nos_dois_apps_e_cria_a_tag():
    deploy = texto("deploy")
    modo = secao(deploy, "Modo `ship`")
    assert "backend e no frontend" in modo and "tag" in modo, modo
    ship = secao(texto("ship"), "Passo 10")
    assert "backend e no frontend" in ship and "tag" in ship, ship


# ------------------------------------------- rollback automático (#968)

# O rabo é script e não chama agente (PRD #963): ele volta a imagem anterior e
# devolve o código; o revert, a issue reaberta, a tentativa e a notificação são
# de quem o chamou. Skill que não diz isso deixa o defeito na main.

def codigo_do_rabo(nome: str) -> str:
    fonte = (RAIZ / FECHAR_ONDA).read_text(encoding="utf-8")
    return re.search(rf"^{nome} = (\d+)$", fonte, re.M).group(1)


def fechamento_da_onda() -> str:
    return re.search(r"^### 6\. Fechamento da onda.*?(?=^### )", texto("onda-enxuta"), re.S | re.M).group(0)


def item_da_saida(trecho: str, codigo: str) -> str:
    itens = [li for li in trecho.splitlines() if f"Saída `{codigo}`" in li]
    assert len(itens) == 1, f"um item para a saída {codigo}: {itens}"
    return itens[0]


@pytest.mark.parametrize("skill", ["ship", "onda-enxuta"])
def test_quem_chama_o_rabo_reverte_reabre_conta_e_notifica_no_rollback_feito(skill):
    trecho = secao(texto("ship"), "Passo 10") if skill == "ship" else fechamento_da_onda()
    item = item_da_saida(trecho, codigo_do_rabo("EXIT_ROLLBACK"))

    assert "PR de revert" in item and "git revert" in item and "sem rebuild" in item, item
    assert "gh issue reopen" in item and "ready-for-agent" in item, item
    assert "linha `health:`" in item, "o comentário leva o que o health respondeu: " + item
    assert "tentativa" in item, item
    assert "PushNotification" in item and "rollback disparado no PR" in item, item
    assert "semáforo" in item and "solto" in item and "/deploy rollback" not in item, item


@pytest.mark.parametrize("skill", ["ship", "onda-enxuta"])
def test_saida_4_continua_sendo_o_rollback_que_falhou_com_semaforo_preso(skill):
    trecho = texto("ship") if skill == "ship" else fechamento_da_onda()
    saida_4 = [li for li in trecho.splitlines() if re.search(r"\b4 health|`4`", li)]
    assert saida_4, "a saída 4 segue descrita"
    assert any(re.search(r"rollback\b.*\bfalh", li) and "preso" in li for li in saida_4), saida_4


def test_tabelas_de_saida_listam_o_rollback_feito():
    codigo = codigo_do_rabo("EXIT_ROLLBACK")
    tabela = next(li for li in texto("onda-enxuta").splitlines() if li.startswith("| `scripts/fechar_onda.py"))
    assert f"{codigo} rollback feito" in tabela, tabela
    falha = next(li for li in texto("ship").splitlines() if "diz o que fazer pelo código de saída" in li)
    assert f"{codigo} rollback feito" in falha, falha


# ----------------------------------------- migration com recibo (#969)

# O rabo espera a migration aparecer no /api/health antes do semáforo e, em
# 24 h sem ela, sai com código próprio sem tocar na main. Texto que ainda manda
# aplicar "antes do rabo" e esperar o "apliquei" para o fluxo à toa.

TEXTOS_DO_FLUXO = [
    SKILLS / "ship" / "SKILL.md",
    SKILLS / "onda-enxuta" / "SKILL.md",
    SKILLS / "onda-enxuta" / "references" / "prompts.md",
    RAIZ / "docs" / "onboarding" / "dev.md",
]


@pytest.mark.parametrize("caminho", TEXTOS_DO_FLUXO, ids=lambda p: str(p.relative_to(RAIZ)))
def test_nenhum_texto_manda_aplicar_a_migration_antes_de_rodar_o_rabo(caminho):
    md = caminho.read_text(encoding="utf-8")
    velhos = [li for li in md.splitlines()
              if re.search(r"antes (do rabo|de rodar|do \"vai\"|do fechamento)|\"apliquei\" do humano", li, re.I)]
    assert velhos == [], velhos


@pytest.mark.parametrize("skill", ["ship", "onda-enxuta"])
def test_quem_chama_o_rabo_sabe_o_que_fazer_com_a_migration_vencida(skill):
    trecho = secao(texto("ship"), "Passo 10") if skill == "ship" else fechamento_da_onda()
    item = item_da_saida(trecho, codigo_do_rabo("EXIT_MIGRACAO"))

    assert "migration" in item and "/api/health" in item and "24 h" in item, item
    assert re.search(r"nada entrou na `?main", item) and "semáforo" in item, item
    assert "PushNotification" in item, item
    assert "/deploy rollback" not in item and "git revert" not in item, item


def test_tabelas_de_saida_listam_a_migration_vencida():
    codigo = codigo_do_rabo("EXIT_MIGRACAO")
    tabela = next(li for li in texto("onda-enxuta").splitlines() if li.startswith("| `scripts/fechar_onda.py"))
    assert f"{codigo} migration vencida" in tabela, tabela
    falha = next(li for li in texto("ship").splitlines() if "diz o que fazer pelo código de saída" in li)
    assert f"{codigo} migration vencida" in falha, falha


def test_gate_de_migrations_do_ship_diz_que_o_rabo_espera_o_numero_no_health():
    gate = secao(texto("ship"), "Passo 8.6")

    assert "migracoes_aplicadas" in gate and "/api/health" in gate and "24 h" in gate, gate
    assert ":1" in gate, "o caminho clicável continua sendo o caminho principal"
