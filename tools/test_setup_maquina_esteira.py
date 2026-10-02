"""Quem mergeia o próprio PR (ADR 0061) precisa de três acessos, conferidos antes.

O `/setup-maquina` confere (issue #906): o `git config user.email` é um e-mail
verificado da conta `gh` logada, senão o commit sai em nome de outra pessoa
(aconteceu em setembro); a CLI do Coolify responde com o contexto do hospital;
o Studio do Supabase de produção é alcançável. Cada conferência roda isolada,
com `gh`, `coolify` e `curl` de mentira no PATH, e só diz se falta e de onde
vem o acesso: nenhuma imprime nem grava segredo.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SCRIPT = RAIZ / ".claude" / "skills" / "setup-maquina" / "scripts" / "diagnostico.sh"
TEXTO = SCRIPT.read_text(encoding="utf-8")

SEGREDO = "tok-SEGREDO-0123456789"
STUDIO = "https://studio.exemplo.test"
# As saídas do script, reduzidas ao que o teste lê: a palavra e o resto da linha.
SAIDAS = 'ok() { echo "OK $*"; }\nfalta() { echo "FALTA $*"; }\naviso() { echo "AVISO $*"; }\n'


def funcao(nome: str) -> str:
    """O corpo da função tal como está no script, para rodar isolada."""
    achado = re.search(rf"^{nome}\(\) \{{.*?^\}}", TEXTO, re.S | re.M)
    assert achado, f"o script não tem a função {nome}()"
    return achado.group(0)


def falso(tmp_path: Path, nome: str, corpo: str) -> None:
    pasta = tmp_path / "bin"
    pasta.mkdir(exist_ok=True)
    arquivo = pasta / nome
    arquivo.write_text("#!/bin/sh\n" + corpo + "\n", encoding="utf-8")
    arquivo.chmod(0o755)


def roda(tmp_path: Path, *chamadas: str) -> str:
    """Roda as conferências com só os falsos, o jq e o básico do sistema no PATH.

    A casa e a pasta de trabalho são uma pasta vazia: o que a conferência
    gravar aparece nela.
    """
    pasta = tmp_path / "bin"
    pasta.mkdir(exist_ok=True)
    if not (pasta / "jq").exists():
        (pasta / "jq").symlink_to(shutil.which("jq"))
    casa = tmp_path / "casa"
    casa.mkdir(exist_ok=True)
    funcoes = "\n".join(funcao(c.split()[0]) for c in chamadas)
    r = subprocess.run(
        ["bash", "-c", SAIDAS + funcoes + "\n" + "\n".join(chamadas)],
        cwd=casa,
        env={"PATH": f"{pasta}:/usr/bin:/bin", "HOME": str(casa)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    return r.stdout + r.stderr


def linha(saida: str, rotulo: str) -> str:
    achadas = [li for li in saida.splitlines() if rotulo in li]
    assert len(achadas) == 1, f"esperava uma linha com {rotulo!r}: {saida}"
    return achadas[0]


# ------------------------------------------------- identidade do git


def gh_falso(tmp_path: Path, emails: list[dict] | None, publico: str | None = None) -> None:
    """`gh api user` devolve o perfil; `gh api user/emails`, a lista (None = sem escopo)."""
    dados = tmp_path / "gh"
    dados.mkdir(exist_ok=True)
    perfil = {"login": "fulana", "id": 42, "email": publico}
    (dados / "perfil.json").write_text(json.dumps(perfil), encoding="utf-8")
    if emails is None:
        lista = (
            "echo '{\"message\":\"Not Found\",\"status\":\"404\"}'; "
            "echo 'gh: This API operation needs the \"user\" scope.' >&2; exit 1"
        )
    else:
        (dados / "emails.json").write_text(json.dumps(emails), encoding="utf-8")
        lista = f'cat "{dados}/emails.json"'
    falso(
        tmp_path,
        "gh",
        f'case "$1 $2" in\n'
        f'  "api user") cat "{dados}/perfil.json" ;;\n'
        f'  "api user/emails") {lista} ;;\n'
        f'  "auth token") echo "{SEGREDO}" ;;\n'
        f'  *) exit 1 ;;\n'
        f'esac',
    )


VERIFICADO = [{"email": "fulana@hospital.test", "verified": True, "primary": True}]
ROTULO_EMAIL = "user.email"


def test_email_verificado_da_conta_passa(tmp_path):
    gh_falso(tmp_path, VERIFICADO)
    saida = roda(tmp_path, 'checa_email_git "fulana@hospital.test"')
    assert linha(saida, ROTULO_EMAIL).startswith("OK")


def test_email_e_comparado_sem_caixa(tmp_path):
    gh_falso(tmp_path, VERIFICADO)
    saida = roda(tmp_path, 'checa_email_git "Fulana@Hospital.TEST"')
    assert linha(saida, ROTULO_EMAIL).startswith("OK")


def test_email_de_outra_pessoa_acusa_e_diz_como_corrigir(tmp_path):
    gh_falso(tmp_path, VERIFICADO)
    li = linha(roda(tmp_path, 'checa_email_git "pedro@outro.test"'), ROTULO_EMAIL)
    assert li.startswith("FALTA")
    assert "fulana" in li, "diz qual conta o gh tem logada"
    assert 'git config --global user.email "' in li, "diz como corrigir"
    assert "42+fulana@users.noreply.github.com" in li, "sugere o e-mail que sempre vale"


def test_email_nao_verificado_nao_conta(tmp_path):
    gh_falso(tmp_path, [{"email": "fulana@hospital.test", "verified": False}])
    saida = roda(tmp_path, 'checa_email_git "fulana@hospital.test"')
    assert linha(saida, ROTULO_EMAIL).startswith("FALTA")


def test_sem_escopo_o_noreply_e_o_publico_ainda_passam(tmp_path):
    gh_falso(tmp_path, None, publico="fulana@publico.test")
    noreply = roda(tmp_path, 'checa_email_git "42+fulana@users.noreply.github.com"')
    publico = roda(tmp_path, 'checa_email_git "fulana@publico.test"')
    assert linha(noreply, ROTULO_EMAIL).startswith("OK")
    assert linha(publico, ROTULO_EMAIL).startswith("OK")


def test_sem_escopo_e_sem_bater_pede_o_escopo(tmp_path):
    gh_falso(tmp_path, None)
    li = linha(roda(tmp_path, 'checa_email_git "fulana@hospital.test"'), ROTULO_EMAIL)
    assert li.startswith("FALTA")
    assert "gh auth refresh -h github.com -s user:email" in li


def test_sem_rede_para_o_gh_so_avisa(tmp_path):
    falso(tmp_path, "gh", "exit 1")
    saida = roda(tmp_path, 'checa_email_git "fulana@hospital.test"')
    assert linha(saida, ROTULO_EMAIL).startswith("AVISO")


# ------------------------------------------------- CLI do Coolify

TABELA = (
    "│ # │ name │ fqdn │ token │ default │\n"
    "│ 1 │ cloud │ https://app.coolify.io │ ******** │ false │\n"
    f"│ 2 │ hsm │ https://coolify.hospitalsaomatheus.cloud │ {SEGREDO} │ true │"
)
SEM_HSM = "│ # │ name │ fqdn │ token │ default │\n│ 1 │ cloud │ https://app.coolify.io │ ******** │ true │"
VERIFY_OK = "echo '✓ Connection successful'; echo '✓ Authentication valid'"
SEM_CONEXAO = (
    'echo "Error: verification failed: request failed: dial tcp: connection refused '
    f'({SEGREDO})"; echo "{SEGREDO}" >&2; exit 1'
)
TOKEN_RECUSADO = (
    f'echo "Error: verification failed: API error 401 on version: Unauthenticated. {SEGREDO}"; exit 1'
)


def coolify_falso(tmp_path: Path, lista: str | None, verify: str = VERIFY_OK) -> None:
    """`coolify context list` imprime a tabela (None = a CLI quebrada)."""
    dados = tmp_path / "coolify"
    dados.mkdir(exist_ok=True)
    if lista is None:
        lista_cmd = "echo 'panic: config ilegível' >&2; exit 1"
    else:
        (dados / "lista.txt").write_text(lista + "\n", encoding="utf-8")
        lista_cmd = f'cat "{dados}/lista.txt"'
    falso(
        tmp_path,
        "coolify",
        f'case "$1 $2" in\n'
        f'  "context list") {lista_cmd} ;;\n'
        f'  "context verify") {verify} ;;\n'
        f'  *) exit 1 ;;\n'
        f'esac',
    )


def faltas(saida: str) -> list[str]:
    return [li for li in saida.splitlines() if li.startswith("FALTA")]


def test_coolify_com_contexto_e_resposta_passa(tmp_path):
    coolify_falso(tmp_path, TABELA)
    saida = roda(tmp_path, "checa_coolify")
    assert faltas(saida) == []
    assert linha(saida, "contexto hsm").startswith("OK")
    assert linha(saida, "servidor do Coolify").startswith("OK")


def test_coolify_que_nao_responde_acusa(tmp_path):
    coolify_falso(tmp_path, None)
    li = linha(roda(tmp_path, "checa_coolify"), "CLI do Coolify")
    assert li.startswith("FALTA")
    assert "claude-setup.md" in li, "diz onde está o passo de instalar"


def test_coolify_sem_o_contexto_do_hospital_acusa(tmp_path):
    coolify_falso(tmp_path, SEM_HSM)
    saida = roda(tmp_path, "checa_coolify")
    li = linha(saida, "contexto hsm")
    assert li.startswith("FALTA")
    assert "Pedro" in li, "diz de quem vem a conta no Coolify"
    assert len(faltas(saida)) == 1, "sem contexto, não segue conferindo o resto"


def test_servidor_do_coolify_sem_resposta_acusa_sem_culpar_o_token(tmp_path):
    coolify_falso(tmp_path, TABELA, verify=SEM_CONEXAO)
    saida = roda(tmp_path, "checa_coolify")
    assert linha(saida, "servidor do Coolify").startswith("FALTA")
    assert "token" not in " ".join(faltas(saida)).lower()


def test_token_recusado_pelo_coolify_pede_token_novo(tmp_path):
    coolify_falso(tmp_path, TABELA, verify=TOKEN_RECUSADO)
    li = linha(roda(tmp_path, "checa_coolify"), "token do Coolify")
    assert li.startswith("FALTA")
    assert "Keys & Tokens" in li, "diz de onde vem o token"


# ------------------------------------------------- Studio de produção


def curl_falso(tmp_path: Path, codigo: str, saida: int = 0) -> None:
    """Imita `curl -w '%{http_code}'`: imprime o código HTTP (000 = sem resposta)."""
    falso(tmp_path, "curl", f'printf "{codigo}"; exit {saida}')


def test_studio_que_pede_login_esta_alcancavel(tmp_path):
    curl_falso(tmp_path, "401")
    li = linha(roda(tmp_path, f'checa_studio "{STUDIO}"'), "Studio")
    assert li.startswith("OK")
    assert "Pedro" in li, "diz de quem vem o login"


def test_studio_sem_resposta_acusa_e_diz_a_quem_pedir(tmp_path):
    curl_falso(tmp_path, "000", saida=7)
    li = linha(roda(tmp_path, f'checa_studio "{STUDIO}"'), "Studio")
    assert li.startswith("FALTA")
    assert STUDIO in li
    assert "Pedro" in li


def test_studio_fora_do_ar_acusa(tmp_path):
    curl_falso(tmp_path, "502")
    li = linha(roda(tmp_path, f'checa_studio "{STUDIO}"'), "Studio")
    assert li.startswith("FALTA")
    assert "502" in li


def test_o_script_confere_o_studio_do_project_json():
    """O endereço vem do contrato de deploy, não de uma cópia no script."""
    projeto = json.loads((RAIZ / "docs/spec/deploy/project.json").read_text(encoding="utf-8"))
    fqdn = next(s["deploy"]["fqdn"] for s in projeto["services"] if s["type"] == "supabase")
    assert fqdn not in TEXTO
    assert re.search(r'^\s*checa_studio "\$STUDIO_URL"', TEXTO, re.M)


# ------------------------------------------------- segredo


def test_nenhuma_conferencia_imprime_nem_grava_segredo(tmp_path):
    """Os falsos põem o segredo em toda saída que poderia carregá-lo."""
    gh_falso(tmp_path, None)
    coolify_falso(tmp_path, TABELA, verify=SEM_CONEXAO)
    curl_falso(tmp_path, "000", saida=7)
    saida = roda(
        tmp_path,
        'checa_email_git "fulana@hospital.test"',
        "checa_coolify",
        f'checa_studio "{STUDIO}"',
    )
    assert len(faltas(saida)) == 3, saida
    assert SEGREDO not in saida
    assert list((tmp_path / "casa").iterdir()) == [], "nada gravado na casa nem na pasta"

    coolify_falso(tmp_path, TABELA, verify=TOKEN_RECUSADO)
    assert SEGREDO not in roda(tmp_path, "checa_coolify")


def test_sem_travessao_no_script():
    assert "—" not in TEXTO and "–" not in TEXTO
