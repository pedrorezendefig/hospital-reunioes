"""O fluxo automático não pode parar nem abrir porta na máquina de quem roda (ADR 0063, issue #964).

A trava contra mexer no ruleset é do servidor: o `gh` das sessões de agente usa
um token fine-grained sem a permissão Administration, e o GitHub recusa a
mudança por qualquer caminho. Regra de deny por prefixo não trava isso (escapa
com `-X DELETE`, `--method=PUT`, `graphql`, `curl`), então ela não existe mais.
No `~/.claude/settings.json` de cada pessoa ficam o deny de force push contra a
`main` e o `autoMode` (o modo auto não lê `autoMode` do settings do projeto):
o rabo, a `/minhas-issues` e a escrituração em issue e PR vão em
`autoMode.allow`, em prosa, para o classificador seguir olhando destino e
conteúdo, e nunca em `permissions.allow`, que pula o classificador. O
`/setup-maquina` confere e diz o que falta e por quê; nunca grava o arquivo e
nunca imprime nada dele nem o token (o bloco `env` guarda token).
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
from pathlib import Path

from test_setup_maquina_esteira import (
    RAIZ,
    SAIDAS,
    SCRIPT,
    SEGREDO,
    falso,
    funcao,
    linha,
    roda,
)

DENY = [
    "Bash(git push *-f* main*)",
    "Bash(git push *-f*:main*)",
    "Bash(git push *-f*/main*)",
    "Bash(git push * main*-f*)",
    "Bash(git push *:main*-f*)",
    "Bash(git push */main*-f*)",
    "Bash(git push *+*main*)",
]
AMBIENTE = [
    "$defaults",
    "**Source control**: o repositório confiável é pedrorezendefig/hospital-reunioes, público",
    "**CI/CD deploy targets**: Coolify (coolify.exemplo.test), deploy de produção pelo fechar_onda.py",
    "**Trusted internal domains**: manual-hsm.vercel.app",
]
AUTO_ALLOW = [
    "$defaults",
    "Rodar fechar_onda.py e minhas_issues.py do repositório quando o script não foi editado",
    "Escrituração com gh issue create, comment e edit só no repositório",
    "Escrituração com gh pr create e comment só no repositório",
]
# As regras que já foram do guia e pulam o classificador: nenhuma pode voltar.
ABERTAS = [
    "Bash(python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py:*)",
    "Bash(python3 .claude/skills/minhas-issues/scripts/minhas_issues.py:*)",
    "Bash(gh issue edit:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh issue create:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr comment *)",
    "Bash(gh:*)",
    "Bash(gh api:*)",
    "Bash(git:*)",
    "Bash(git push *)",
    "Bash(coolify deploy uuid:*)",
    "Bash(curl -sf http://localhost:*)",
    "Bash(python3 *)",
    "Bash(python3 ./.claude/skills/onda-enxuta/scripts/fechar_onda.py *)",
    "Bash(npx:*)",
    "Bash(uv *)",
    "Bash(git add:*)",
    "Bash(lsof *)",
    "Bash(cat*)",
    "Bash(find:*)",
    "Bash(vercel *)",
    "Bash(git fetch *)",
    "Bash(*)",
    "Bash",
]
ROTULOS_DENY = [f"deny {r[5:-1]}" for r in DENY]
ROTULOS_AMBIENTE = ["repositório", "Coolify", "Vercel"]
ROTULOS_AUTO = ["fechar_onda.py", "minhas_issues.py", "gh issue", "gh pr"]
LINHAS = (
    len(DENY) + len(ROTULOS_AMBIENTE) + len(ROTULOS_AUTO) + 1
)  # +1: sem allow aberto


def settings(
    pasta: Path, allow=(), deny=DENY, ambiente=AMBIENTE, auto=AUTO_ALLOW, **extra
) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / "settings.json"
    dados = {
        "permissions": {"allow": list(allow), "deny": list(deny)},
        "autoMode": {"environment": list(ambiente), "allow": list(auto)},
        **extra,
    }
    arquivo.write_text(json.dumps(dados, indent=2), encoding="utf-8")
    return arquivo


def confere(tmp_path: Path, arquivo: Path) -> str:
    return roda(tmp_path, f'checa_permissoes_claude "{arquivo}"')


def faltas(saida: str) -> list[str]:
    return [li for li in saida.splitlines() if li.startswith("FALTA")]


def test_settings_completo_passa_regra_por_regra(tmp_path):
    saida = confere(tmp_path, settings(tmp_path))
    assert faltas(saida) == [], saida
    for rotulo in ROTULOS_DENY:
        assert linha(saida, rotulo).startswith("OK"), rotulo
    for item in ROTULOS_AMBIENTE:
        assert linha(saida, f"autoMode.environment: {item}").startswith("OK")
    for item in ROTULOS_AUTO:
        assert linha(saida, f"autoMode.allow: {item}").startswith("OK")
    assert linha(saida, "sem allow que pula o classificador").startswith("OK")


def test_settings_incompleto_aponta_cada_regra_que_falta_e_o_conserto(tmp_path):
    arquivo = settings(
        tmp_path,
        deny=[r for r in DENY if r != "Bash(git push *+*main*)"],
        ambiente=[a for a in AMBIENTE if "vercel" not in a],
        auto=[a for a in AUTO_ALLOW if "gh issue" not in a],
    )
    saida = confere(tmp_path, arquivo)
    assert len(faltas(saida)) == 3, saida

    mais = linha(saida, "deny git push *+*main*")
    assert mais.startswith("FALTA")
    assert '"Bash(git push *+*main*)"' in mais and "permissions.deny" in mais, (
        "diz a regra exata e onde pôr"
    )
    assert "~/.claude/settings.json" in mais, (
        "o arquivo é o do usuário, não o do projeto"
    )

    vercel = linha(saida, "autoMode.environment: Vercel")
    assert vercel.startswith("FALTA") and "manual-hsm.vercel.app" in vercel, (
        "pede o host exato"
    )
    assert "não lê autoMode do settings do projeto" in vercel, (
        "diz por que tem de ser no do usuário"
    )

    issue = linha(saida, "autoMode.allow: gh issue")
    assert issue.startswith("FALTA") and "classificador" in issue

    assert linha(saida, "deny git push *-f* main*").startswith("OK")
    assert linha(saida, "autoMode.environment: Coolify").startswith("OK")
    assert linha(saida, "autoMode.allow: gh pr").startswith("OK")


def test_vercel_generico_nao_basta(tmp_path):
    """`*.vercel.app` qualquer conta registra; só o host do Manual é confiável."""
    ambiente = AMBIENTE[:3] + [
        "**Trusted internal domains**: os projetos do time na Vercel"
    ]
    saida = confere(tmp_path, settings(tmp_path, ambiente=ambiente))
    assert linha(saida, "autoMode.environment: Vercel").startswith("FALTA")


def test_nao_ha_mais_regra_de_ruleset(tmp_path):
    """A trava do ruleset é o token sem Administration, não um deny que se contorna."""
    saida = confere(tmp_path, settings(tmp_path))
    assert "ruleset" not in saida.lower(), saida
    assert "ruleset" not in "".join(DENY)


# ------------------------------------------------- allow que pula o classificador


def test_cada_allow_aberto_acusa_e_diz_por_que(tmp_path):
    saida = confere(
        tmp_path, settings(tmp_path, allow=ABERTAS + ["Bash(gh run rerun:*)"])
    )
    acusadas = [li for li in faltas(saida) if "allow aberto" in li]
    assert len(acusadas) == len(ABERTAS), saida
    for regra in ABERTAS:
        li = next(li for li in acusadas if f'"{regra}"' in li)
        assert "permissions.allow" in li and "classificador" in li, li
    assert "sem allow que pula o classificador" not in saida
    assert "gh run rerun" not in saida, "rerun não publica texto: fica"


def test_allow_de_leitura_e_de_outra_ferramenta_nao_acusa(tmp_path):
    allow = [
        "Bash(gh issue list:*)",
        "Bash(gh pr view *)",
        "Bash(git status:*)",
        "Bash(git diff *)",
        "Bash(ls ~/.claude/mcp*)",
        "Bash(curl -sf http://localhost:8000/api/health)",
        "Bash(jq:*)",
        "Read(/Users/fulana/PedroDev/Hospital/**)",
        "mcp__coolify__*",
    ]
    saida = confere(tmp_path, settings(tmp_path, allow=allow))
    assert faltas(saida) == [], saida


# ------------------------------------------------- o deny de force push


def casa(comando: str, regra: str) -> bool:
    """Leitura da regra como o Claude Code faz: `*` é qualquer texto, o resto é literal."""
    return fnmatch.fnmatchcase(comando, regra[len("Bash(") : -1].replace("[", "[[]"))


FORCA_NA_MAIN = [
    "git push --force origin main",
    "git push origin main --force",
    "git push -f origin main",
    "git push origin main -f",
    "git push --force-with-lease origin main",
    "git push origin main --force-with-lease",
    "git push --force origin HEAD:main",
    "git push -f origin HEAD:main",
    "git push origin +main",
    "git push origin +HEAD:main",
    "git push --force origin HEAD:refs/heads/main",
    "git push origin HEAD:refs/heads/main --force",
    "git push origin +HEAD:refs/heads/main",
]
PUSH_DO_FLUXO = [
    "git push -u origin docs/adr-0063-setup-maquina-permissoes-964",
    "git push --force-with-lease",
    "git push --force-with-lease origin fix/domain-sem-main",
    "git push origin chore/pr-de-ferramenta-so-faz-merge-965",
    "git push -q origin HEAD:refs/heads/entrega-onda-3",
    "git push origin main",
]


def test_deny_pega_force_push_na_main_em_toda_forma():
    for comando in FORCA_NA_MAIN:
        assert any(casa(comando, r) for r in DENY), comando


def test_deny_nao_trava_o_push_do_fluxo():
    """O corretor sobe rebase com --force-with-lease na branch do PR; a main tem o ruleset."""
    for comando in PUSH_DO_FLUXO:
        assert not any(casa(comando, r) for r in DENY), comando


# ------------------------------------------------- casos de borda do arquivo


def test_settings_sem_autoMode_e_sem_permissoes_acusa_tudo(tmp_path):
    arquivo = tmp_path / "settings.json"
    arquivo.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    assert len(faltas(confere(tmp_path, arquivo))) == LINHAS - 1


def test_settings_que_nao_existe_acusa_tudo(tmp_path):
    saida = confere(tmp_path, tmp_path / "nao-existe.json")
    assert len(faltas(saida)) == LINHAS - 1, saida


def test_o_trecho_do_onboarding_passa_no_diagnostico(tmp_path):
    """O FALTA manda a pessoa ao trecho da seção 5.1; ele tem de bastar."""
    guia = (RAIZ / "docs" / "onboarding" / "claude-setup.md").read_text(
        encoding="utf-8"
    )
    secao = guia.split("### 5.1 ", 1)[1].split("\n## ", 1)[0]
    bloco = secao.split("```json\n", 1)[1].split("```", 1)[0]
    arquivo = tmp_path / "settings.json"
    arquivo.write_text(bloco, encoding="utf-8")
    saida = confere(tmp_path, arquivo)
    assert faltas(saida) == [], saida
    assert len(saida.splitlines()) == LINHAS, saida


def test_o_guia_base_nao_libera_gh_inteiro(tmp_path):
    """O `Bash(gh:*)` da seção 5 tiraria o classificador da escrituração de novo."""
    guia = (RAIZ / "docs" / "onboarding" / "claude-setup.md").read_text(
        encoding="utf-8"
    )
    for bloco in guia.split("```json\n")[1:]:
        json_bloco = bloco.split("```", 1)[0]
        arquivo = tmp_path / "settings.json"
        arquivo.write_text(json_bloco, encoding="utf-8")
        saida = confere(tmp_path, arquivo)
        assert not [li for li in faltas(saida) if "allow aberto" in li], saida


# ------------------------------------------------- o token do gh sem Administration


def gh_admin(
    tmp_path: Path,
    sessao: str,
    chaveiro: str,
    classico: str = "401",
    login: str = "fulana",
) -> None:
    """`gh api .../keys` (deploy keys exigem Administration) responde conforme a credencial.

    Com GH_TOKEN no ambiente, o gh usa o token da sessão; sem ele, o do chaveiro.
    Cada modo: admin (200), 403, 404, semlogin, rede. O falso também cospe o
    segredo nas duas saídas, para provar que a conferência não repassa nada.
    """
    falso(
        tmp_path,
        "gh",
        'case "$*" in *"repos/pedrorezendefig/hospital-reunioes/keys"*) ;;\n'
        f'  "api user --jq .login") echo {login}; exit 0 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
        f'if [ "${{GH_TOKEN:-}}" = pat_classico ]; then m="{classico}"\n'
        f'elif [ -n "${{GH_TOKEN:-}}${{GITHUB_TOKEN:-}}" ]; then m="{sessao}"; else m="{chaveiro}"; fi\n'
        f'echo "{SEGREDO}"; echo "{SEGREDO}" >&2\n'
        'case "$m" in\n'
        "  admin) exit 0 ;;\n"
        "  403) echo 'gh: Resource not accessible by personal access token (HTTP 403)' >&2; exit 1 ;;\n"
        "  404) echo 'gh: Not Found (HTTP 404)' >&2; exit 1 ;;\n"
        "  401) echo 'gh: Bad credentials (HTTP 401)' >&2; exit 1 ;;\n"
        "  limite) echo 'gh: API rate limit exceeded (HTTP 403)' >&2; exit 1 ;;\n"
        "  semlogin) echo 'To get started with GitHub CLI, please run:  gh auth login' >&2; exit 4 ;;\n"
        "  rede) echo 'error connecting to api.github.com' >&2; exit 1 ;;\n"
        "esac",
    )


SESSAO = "gh da sessão sem Administration"
CHAVEIRO = "gh do chaveiro sem Administration"


def admin(tmp_path: Path, com_token: bool, **outros: str) -> str:
    """Como o `roda`, mas com ou sem GH_TOKEN no ambiente da conferência."""
    if not (tmp_path / "bin" / "security").exists():
        falso(tmp_path, "security", "exit 44")  # nada guardado no Acesso às Chaves
    env = {"PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin", "HOME": str(tmp_path)}
    if com_token:
        env["GH_TOKEN"] = "github_pat_falso"
    env.update(outros)
    r = subprocess.run(
        [
            "bash",
            "-c",
            SAIDAS
            + funcao("eh_admin")
            + "\n"
            + funcao("admin_responde")
            + "\n"
            + funcao("checa_gh_sem_admin")
            + "\ncheca_gh_sem_admin",
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return r.stdout + r.stderr


def test_token_fine_grained_sem_admin_e_chaveiro_vazio_passam(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin")
    saida = admin(tmp_path, com_token=True)
    assert linha(saida, SESSAO).startswith("OK"), saida
    assert linha(saida, CHAVEIRO).startswith("OK"), saida
    assert SEGREDO not in saida


def test_token_da_sessao_com_admin_acusa_e_manda_criar_o_fine_grained(tmp_path):
    gh_admin(tmp_path, sessao="admin", chaveiro="semlogin")
    li = linha(admin(tmp_path, com_token=True), SESSAO)
    assert li.startswith("FALTA"), li
    assert "Administration" in li and "GH_TOKEN" in li and "tokens/.env" in li, li
    assert "5.1" in li, "aponta o passo a passo"
    assert SEGREDO not in li


def test_chaveiro_com_admin_acusa_mesmo_com_o_token_certo(tmp_path):
    """O agente escapa do GH_TOKEN com `env -u GH_TOKEN gh ...` e cai no chaveiro."""
    gh_admin(tmp_path, sessao="403", chaveiro="admin")
    saida = admin(tmp_path, com_token=True)
    assert linha(saida, SESSAO).startswith("OK"), saida
    li = linha(saida, CHAVEIRO)
    assert li.startswith("FALTA") and "gh auth logout" in li, li
    assert SEGREDO not in saida


def test_sem_GH_TOKEN_a_sessao_e_o_chaveiro(tmp_path):
    """Colaborador sem admin no repositório: o 404 do chaveiro vale como sem Administration."""
    gh_admin(tmp_path, sessao="admin", chaveiro="404")
    saida = admin(tmp_path, com_token=False)
    assert linha(saida, SESSAO).startswith("OK"), saida
    assert CHAVEIRO not in saida, "sem GH_TOKEN, a sessão já é o chaveiro"


def test_sem_GH_TOKEN_e_admin_no_chaveiro_acusa(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="admin")
    li = linha(admin(tmp_path, com_token=False), SESSAO)
    assert li.startswith("FALTA") and "GH_TOKEN" in li, li


def test_403_de_limite_de_taxa_nao_vale_como_sem_admin(tmp_path):
    gh_admin(tmp_path, sessao="limite", chaveiro="semlogin")
    assert linha(admin(tmp_path, com_token=True), SESSAO).startswith("AVISO")


def test_sem_rede_avisa_e_nao_da_ok(tmp_path):
    gh_admin(tmp_path, sessao="rede", chaveiro="rede")
    saida = admin(tmp_path, com_token=True)
    assert linha(saida, SESSAO).startswith("AVISO"), saida
    assert linha(saida, CHAVEIRO).startswith("AVISO"), saida


def test_outro_token_do_github_exportado_com_admin_acusa(tmp_path):
    """O tokens/.env vai inteiro para a sessão: um PAT clássico ali contorna o GH_TOKEN."""
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin", classico="admin")
    saida = admin(tmp_path, com_token=True, GITHUB_PERSONAL_ACCESS_TOKEN="pat_classico")
    li = linha(saida, "GITHUB_PERSONAL_ACCESS_TOKEN sem Administration")
    assert li.startswith("FALTA") and "tokens/.env" in li, li
    assert linha(saida, SESSAO).startswith("OK"), saida
    assert "pat_classico" not in saida and SEGREDO not in saida


def test_GITHUB_TOKEN_ao_lado_do_GH_TOKEN_tambem_e_testado(tmp_path):
    """O gh lê o GH_TOKEN antes; `env -u GH_TOKEN gh ...` cai no GITHUB_TOKEN."""
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin", classico="admin")
    saida = admin(tmp_path, com_token=True, GITHUB_TOKEN="pat_classico")
    assert linha(saida, "GITHUB_TOKEN sem Administration").startswith("FALTA"), saida


def test_token_do_github_com_outro_nome_tambem_e_testado(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin", classico="admin")
    saida = admin(tmp_path, com_token=True, HOMEBREW_GITHUB_API_TOKEN="pat_classico")
    assert linha(saida, "HOMEBREW_GITHUB_API_TOKEN sem Administration").startswith(
        "FALTA"
    )


def test_dono_com_token_fine_grained_conta_como_admin(tmp_path):
    """Com o token sem Administration o papel pode não vir ADMIN; o login do dono decide."""
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin", login="pedrorezendefig")
    falso(tmp_path, "security", "exit 0")
    saida = admin(tmp_path, com_token=True)
    assert linha(saida, "Acesso às Chaves").startswith("FALTA"), saida


def test_outro_token_sem_admin_ou_vazio_passa(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin", classico="401")
    saida = admin(
        tmp_path,
        com_token=True,
        GITHUB_PERSONAL_ACCESS_TOKEN="pat_classico",
        GH_TOKEN_VAZIO="",
    )
    assert linha(saida, "GITHUB_PERSONAL_ACCESS_TOKEN sem Administration").startswith(
        "OK"
    )
    assert "GH_TOKEN_VAZIO" not in saida


def test_regra_acusada_nao_imprime_segredo_dentro_dela(tmp_path):
    regra = "Bash(curl -H 'Authorization: token ghp_" + "A" * 36 + "' *)"
    saida = confere(tmp_path, settings(tmp_path, allow=[regra]))
    li = linha(saida, "allow aberto")
    assert li.startswith("FALTA") and "<omitido>" in li and "A" * 36 not in li, li


def test_allow_que_o_jq_nao_le_acusa_em_vez_de_dar_ok(tmp_path):
    """JSON válido com item que não é texto: o jq falha, e a falha não pode virar OK."""
    arquivo = settings(tmp_path, allow=["Bash(gh:*)", 5])
    saida = confere(tmp_path, arquivo)
    assert "sem allow que pula o classificador" not in saida, saida
    assert linha(saida, "allow aberto").startswith("FALTA")


def test_settings_invalido_acusa_o_json_e_nao_da_ok_falso(tmp_path):
    arquivo = tmp_path / "settings.json"
    arquivo.write_text('{"permissions": {"allow": ["Bash(gh:*)"],}', encoding="utf-8")
    saida = confere(tmp_path, arquivo)
    assert linha(saida, "JSON válido").startswith("FALTA"), saida
    assert "sem allow que pula o classificador" not in saida
    assert len(faltas(saida)) == 1, "uma falta só, com o conserto certo"


def test_allow_do_projeto_tambem_conta(tmp_path):
    usuario = settings(tmp_path / "usuario")
    projeto = tmp_path / "projeto" / "settings.local.json"
    projeto.parent.mkdir()
    projeto.write_text(
        json.dumps({"permissions": {"allow": ["Bash(gh:*)"]}}), encoding="utf-8"
    )
    saida = roda(tmp_path, f'checa_permissoes_claude "{usuario}" "{projeto}"')
    li = linha(saida, "allow aberto")
    assert (
        li.startswith("FALTA") and "settings.local.json" in li and '"Bash(gh:*)"' in li
    ), li


def test_credencial_guardada_fora_do_gh_acusa_quem_e_admin(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin")
    falso(tmp_path, "security", "exit 0")
    (tmp_path / ".git-credentials").write_text(
        f"https://fulana:{SEGREDO}@github.com\n", encoding="utf-8"
    )
    saida = admin(tmp_path, com_token=True, perm="ADMIN")
    assert linha(saida, "Acesso às Chaves").startswith("FALTA"), saida
    assert linha(saida, "git-credentials").startswith("FALTA"), saida
    assert SEGREDO not in saida


def test_credencial_guardada_de_quem_nao_e_admin_nao_acusa(tmp_path):
    gh_admin(tmp_path, sessao="403", chaveiro="semlogin")
    falso(tmp_path, "security", "exit 0")
    (tmp_path / ".git-credentials").write_text(
        "https://x:y@github.com\n", encoding="utf-8"
    )
    saida = admin(tmp_path, com_token=True, perm="WRITE")
    assert "Acesso às Chaves" not in saida and "git-credentials" not in saida, saida


# ------------------------------------------------- segredo e escrita


def test_nao_imprime_valor_do_env_nem_grava_o_arquivo(tmp_path):
    """O token falso fica no `env`, onde o settings de verdade guarda chave."""
    arquivo = settings(
        tmp_path,
        allow=ABERTAS[:1],
        ambiente=AMBIENTE[:2],
        env={"COOLIFY_ACCESS_TOKEN": SEGREDO, "GH_TOKEN": SEGREDO},
    )
    antes = arquivo.read_bytes()
    saida = confere(tmp_path, arquivo)
    assert len(faltas(saida)) == 3, saida
    assert SEGREDO not in saida
    assert arquivo.read_bytes() == antes, "nunca grava a configuração sozinho"
    assert list((tmp_path / "casa").iterdir()) == [], (
        "nada gravado na casa nem na pasta"
    )


# ------------------------------------------------- o script inteiro


def roda_script(tmp_path: Path, nivel: str) -> str:
    """O `diagnostico.sh` de verdade, numa cópia mínima do repo e com HOME falso."""
    repo = tmp_path / "repo"
    pasta_script = repo / ".claude" / "skills" / "setup-maquina" / "scripts"
    pasta_script.mkdir(parents=True, exist_ok=True)
    shutil.copy(SCRIPT, pasta_script / "diagnostico.sh")
    (pasta_script.parent / "references").mkdir(exist_ok=True)
    (pasta_script.parent / "references" / "plugins.txt").write_text(
        "", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    pasta = tmp_path / "bin"
    pasta.mkdir(exist_ok=True)
    if not (pasta / "jq").exists():
        (pasta / "jq").symlink_to(shutil.which("jq"))
    r = subprocess.run(
        ["bash", str(pasta_script / "diagnostico.sh"), "--nivel", nivel],
        cwd=tmp_path / "casa",
        env={"PATH": f"{pasta}:/usr/bin:/bin", "HOME": str(tmp_path / "casa")},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return r.stdout + r.stderr


def test_o_script_confere_o_settings_do_usuario_no_nivel_2(tmp_path):
    (tmp_path / "casa" / ".claude").mkdir(parents=True)
    settings(tmp_path / "casa" / ".claude", env={"COOLIFY_ACCESS_TOKEN": SEGREDO})
    saida = roda_script(tmp_path, "2")
    for rotulo in ROTULOS_DENY:
        assert linha(saida, rotulo).split()[0] == "OK", saida
    assert linha(saida, "autoMode.environment: Vercel").split()[0] == "OK", saida
    assert linha(saida, "autoMode.allow: gh pr").split()[0] == "OK", saida
    assert SEGREDO not in saida


def test_o_script_confere_o_token_do_gh_no_nivel_2(tmp_path):
    """O script põe ~/.local/bin na frente do PATH (antes do Homebrew): o falso vai lá e no PATH."""
    (tmp_path / "casa" / ".local").mkdir(parents=True)
    corpo = (
        'case "$*" in\n'
        '  "auth status") exit 0 ;;\n'
        '  "repo view"*) echo ADMIN ;;\n'
        '  *"repos/pedrorezendefig/hospital-reunioes/keys"*) echo "[]" ;;\n'
        "  *) exit 1 ;;\n"
        "esac"
    )
    falso(tmp_path, "gh", corpo)
    falso(tmp_path / "casa" / ".local", "gh", corpo)
    saida = roda_script(tmp_path, "2")
    assert linha(saida, SESSAO).split()[0] == "FALTA", saida


def test_gh_sem_autenticar_ainda_confere_o_chaveiro(tmp_path):
    """GH_TOKEN vencido derruba o `gh auth status`, mas o login guardado segue alcançável."""
    (tmp_path / "casa" / ".local").mkdir(parents=True)
    corpo = (
        'case "$*" in\n'
        '  "auth status") exit 1 ;;\n'
        '  *"repos/pedrorezendefig/hospital-reunioes/keys"*) echo "[]" ;;\n'
        "  *) exit 1 ;;\n"
        "esac"
    )
    falso(tmp_path, "gh", corpo)
    falso(tmp_path / "casa" / ".local", "gh", corpo)
    saida = roda_script(tmp_path, "2")
    assert linha(saida, SESSAO).split()[0] == "FALTA", saida


def test_o_script_varre_o_allow_do_projeto_e_o_pat_do_tokens_env(tmp_path):
    (tmp_path / "casa" / ".local").mkdir(parents=True)
    corpo = (
        'case "$*" in\n'
        '  "auth status") exit 0 ;;\n'
        '  "repo view"*) echo ADMIN ;;\n'
        "  *) exit 1 ;;\n"
        "esac"
    )
    falso(tmp_path, "gh", corpo)
    falso(tmp_path / "casa" / ".local", "gh", corpo)
    settings(tmp_path / "casa" / ".claude")
    local = tmp_path / "repo" / ".claude" / "settings.local.json"
    local.parent.mkdir(parents=True)
    local.write_text(
        json.dumps({"permissions": {"allow": ["Bash(git:*)"]}}), encoding="utf-8"
    )
    (tmp_path / "repo" / "tokens").mkdir()
    (tmp_path / "repo" / "tokens" / ".env").write_text(
        f"GITHUB_PERSONAL_ACCESS_TOKEN={SEGREDO}\n", encoding="utf-8"
    )
    saida = roda_script(tmp_path, "2")
    li = linha(saida, "allow aberto")
    assert li.split()[0] == "FALTA" and "settings.local.json" in li, saida
    assert linha(saida, "tokens/.env sem PAT clássico").split()[0] == "FALTA", saida
    assert SEGREDO not in saida


def test_settings_do_projeto_nao_conta(tmp_path):
    """O modo auto não lê `autoMode` do projeto: só o arquivo do usuário vale."""
    (tmp_path / "casa").mkdir()
    settings(tmp_path / "repo" / ".claude")
    saida = roda_script(tmp_path, "2")
    assert linha(saida, "deny git push *+*main*").split()[0] == "FALTA", saida
    assert linha(saida, "autoMode.environment: Coolify").split()[0] == "FALTA", saida


def test_o_nivel_1_nao_confere_as_permissoes(tmp_path):
    (tmp_path / "casa").mkdir()
    saida = roda_script(tmp_path, "1")
    assert "autoMode" not in saida and SESSAO not in saida


# ------------------------------------------------- ADR 0063


def cabecalho(caminho: Path) -> dict[str, str]:
    bloco = caminho.read_text(encoding="utf-8").split("---\n")[1]
    return dict(li.split(": ", 1) for li in bloco.splitlines() if ": " in li)


def adr(numero: str) -> Path:
    achados = sorted((RAIZ / "docs" / "adr").glob(f"{numero}-*.md"))
    assert len(achados) == 1, f"esperava um ADR {numero}: {achados}"
    return achados[0]


def test_adr_0063_aceito_e_emendando_o_0061_nos_dois_sentidos():
    nova = cabecalho(adr("0063"))
    assert nova["status"] == "accepted"
    assert nova["amends"] == "0061"
    assert "0063" in cabecalho(adr("0061"))["amended_by"].split(", ")
    assert adr("0063").name in (RAIZ / "docs" / "adr" / "README.md").read_text(
        encoding="utf-8"
    )


def test_adr_0063_poe_a_trava_no_servidor_e_diz_por_que_o_deny_nao_serve():
    texto = adr("0063").read_text(encoding="utf-8")
    assert "Administration" in texto and "fine-grained" in texto
    for contorno in ("-X DELETE", "--method=PUT", "graphql", "curl"):
        assert contorno in texto, contorno
    assert "rulesets:*" not in texto, "nenhuma regra de deny do ruleset sobrou"


def test_texto_novo_sem_travessao():
    skill = SCRIPT.parent.parent / "SKILL.md"
    for caminho in (adr("0063"), SCRIPT, skill, Path(__file__)):
        texto = caminho.read_text(encoding="utf-8")
        assert "\u2014" not in texto and "\u2013" not in texto, caminho
