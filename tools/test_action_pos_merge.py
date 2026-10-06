"""A Action pós-merge: snapshot e draft do Manual direto na `main` (issue #940).

ADR 0062, decisão 10: o rabo deixou de rodar o `snapshot.py` e o
`tirar_draft_manual.py` (#939), e quem roda os dois é um workflow no push da
`main`, que commita como `github-actions[bot]` pelo bypass do ruleset. A ADR
0065 separou o workflow em dois jobs: o `gerar` instala e roda tudo sem
credencial e entrega um patch por artefato; o `commitar`, que não instala
nada, aplica o patch e empurra com a deploy key de um Environment restrito à
`main`. Estes testes amarram o contrato do workflow (evento, branch, autor,
`[skip ci]`, onde mora a credencial, o filtro que impede a Action de acordar
com o próprio commit) e rodam os passos de shell dele de verdade, num repo
git de brinquedo.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tirar_draft_manual import sem_draft  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
WORKFLOW = RAIZ / ".github" / "workflows" / "pos-merge.yml"


def workflow(arquivo: Path = WORKFLOW) -> dict:
    return yaml.safe_load(arquivo.read_text(encoding="utf-8"))


def gatilhos(arquivo: Path = WORKFLOW) -> dict:
    # O PyYAML segue o YAML 1.1, em que `on` é booleano: a chave vira True.
    w = workflow(arquivo)
    return w["on"] if "on" in w else w[True]


def test_dispara_no_push_da_main_e_nunca_em_pull_request():
    """O commit vai direto na `main` pelo bypass; em PR a Action escreveria na
    branch de outra pessoa, ou commitaria snapshot de código que não subiu."""
    on = gatilhos()
    assert on["push"]["branches"] == ["main"]
    assert "pull_request" not in on
    assert "pull_request_target" not in on
    assert "workflow_run" not in on


def test_credencial_de_escrita_so_no_job_que_nao_instala_nada():
    """ADR 0065: o `GITHUB_TOKEN` só lê, e a deploy key (o ator do bypass) só
    existe no `commitar`, num Environment restrito à `main`. O `gerar` roda
    pip, uv sync e o import do app sem token no `.git/config`; o `commitar`
    só usa checkout, download do artefato e git."""
    w = workflow()
    assert w["permissions"] == {"contents": "read"}
    assert set(w["jobs"]) == {"gerar", "commitar"}
    for nome, job in w["jobs"].items():
        assert "permissions" not in job, nome
    gerar, commitar = w["jobs"]["gerar"], w["jobs"]["commitar"]

    assert "environment" not in gerar
    assert gerar["steps"][0]["uses"].startswith("actions/checkout@")
    assert gerar["steps"][0]["with"]["persist-credentials"] is False
    assert "secrets." not in yaml.safe_dump(gerar)

    assert commitar["environment"] == "pos-merge"
    assert commitar["needs"] == "gerar"
    usos = [p["uses"].split("@")[0] for p in commitar["steps"] if "uses" in p]
    assert usos == ["actions/checkout", "actions/download-artifact"]
    checkout = commitar["steps"][0]["with"]
    assert checkout["ssh-key"] == "${{ secrets.POS_MERGE_DEPLOY_KEY }}"
    assert checkout["ref"] == "main"
    scripts = " ".join(p["run"] for p in commitar["steps"] if "run" in p)
    for instalador in ("pip", "uv ", "npm", "pnpm", "corepack", "apt", "python", "curl", "wget"):
        assert instalador not in scripts, instalador
    assert WORKFLOW.read_text(encoding="utf-8").count("secrets.") == 1


def casa(padrao: str, caminho: str) -> bool:
    """O glob do filtro de caminhos do GitHub: `**` atravessa pastas, `*` não."""
    regex = ""
    i = 0
    while i < len(padrao):
        if padrao.startswith("**", i):
            regex += ".*"
            i += 2
        elif padrao[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(padrao[i])
            i += 1
    return re.fullmatch(regex, caminho) is not None


def acorda(mudados: list[str]) -> bool:
    """Com `paths-ignore`, o push só não acorda a Action se todo caminho cair
    num padrão ignorado."""
    ignorados = gatilhos()["push"]["paths-ignore"]
    return any(not any(casa(p, c) for p in ignorados) for c in mudados)


def test_push_que_so_toca_snapshot_e_paginas_do_manual_nao_acorda_a_action():
    """É o que a própria Action escreve. O push da deploy key dispara
    workflow: o filtro e o `[skip ci]` impedem o loop."""
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/spec/snapshots/SCHEMA.md"])
    assert not acorda(["docs/ARQUITETURA.md"])
    assert not acorda(["docs/manual/src/content/docs/ouvidoria/manifestacoes/registrar.mdx"])
    assert not acorda(["docs/spec/snapshots/ROTAS.md", "docs/ARQUITETURA.md",
                       "docs/manual/src/content/docs/index.mdx"])


def test_merge_do_registro_e_de_codigo_acordam_a_action():
    """O gatilho que importa é o PR de registro do rabo: com o `history.json`
    na `main`, o draft sabe o que está em produção."""
    assert acorda(["docs/spec/deploy/history.json", "docs/spec/deploy/state.json"])
    assert acorda(["hospital-reunioes/backend/app/routers/atas.py"])
    assert acorda(["docs/spec/snapshots/ROTAS.md", "hospital-reunioes/supabase/migrations/115_x.sql"])
    assert acorda(["docs/manual/video/ouvidoria/registrar/index.html"])


# --------------------------------------------------- os passos de shell, rodados

def passo(trecho: str, job: str = "gerar") -> dict:
    """O passo do job cujo nome contém o trecho."""
    passos = workflow()["jobs"][job]["steps"]
    achados = [p for p in passos if trecho in p.get("name", "")]
    assert len(achados) == 1, [p.get("name") for p in passos]
    return achados[0]


# Sem identidade nem config global: quem diz o autor do commit é o passo.
ENV_GIT = {
    **{k: v for k, v in os.environ.items() if not k.startswith(("GIT_AUTHOR_", "GIT_COMMITTER_"))},
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
}


def rodar(trecho: str, cwd: Path, env: dict[str, str] | None = None,
          job: str = "gerar") -> subprocess.CompletedProcess:
    """Roda o `run:` do passo como o GitHub Actions roda: `bash -e {0}`."""
    script = cwd.parent / "passo.sh"
    script.write_text(passo(trecho, job)["run"], encoding="utf-8")
    return subprocess.run(["bash", "-e", str(script)], cwd=cwd, env={**ENV_GIT, **(env or {})},
                          capture_output=True, text=True, check=False)


TIRAR_DRAFT_FALSO = """\
import os, sys
from pathlib import Path
Path("chamadas.txt").open("a").write(" ".join(sys.argv[1:]) + "\\n")
sys.exit(int(os.environ.get("SAIDA_DO_DRAFT", "0")))
"""


def arvore_do_draft(tmp_path: Path, prds: list[int]) -> Path:
    raiz = tmp_path / "repo"
    (raiz / "docs" / "spec" / "deploy").mkdir(parents=True)
    (raiz / "tools").mkdir()
    deploys = [{"app_version": "0.2.0", "prds": prds}, {"app_version": "0.1.0", "prds": [700]}]
    (raiz / "docs" / "spec" / "deploy" / "history.json").write_text(
        json.dumps({"schema_version": 1, "deploys": deploys}), encoding="utf-8")
    (raiz / "tools" / "tirar_draft_manual.py").write_text(TIRAR_DRAFT_FALSO, encoding="utf-8")
    return raiz


def chamadas(raiz: Path) -> list[str]:
    arq = raiz / "chamadas.txt"
    return arq.read_text(encoding="utf-8").splitlines() if arq.exists() else []


def test_draft_sai_para_os_prds_do_ultimo_deploy(tmp_path):
    raiz = arvore_do_draft(tmp_path, [963, 646])
    proc = rodar("Tirar do draft", raiz)
    assert proc.returncode == 0, proc.stderr
    assert chamadas(raiz) == ["--prd 963 --prd 646"]


def test_ultimo_deploy_sem_prd_nao_chama_o_tirar_draft(tmp_path):
    """PR avulso registra `prds: []`. Sem `--prd` o argparse sai com 2, e o
    passo não pode confundir isso com o bloqueio do MP4."""
    raiz = arvore_do_draft(tmp_path, [])
    proc = rodar("Tirar do draft", raiz)
    assert proc.returncode == 0, proc.stderr
    assert chamadas(raiz) == []


def test_bloqueio_do_mp4_avisa_e_nao_derruba_a_action(tmp_path):
    """Saída 2: o tirar-draft não escreveu nada (o MP4 do Vídeo de tarefa não
    vem no clone, issue #951). A página fica em draft e o snapshot segue."""
    raiz = arvore_do_draft(tmp_path, [963])
    proc = rodar("Tirar do draft", raiz, {"SAIDA_DO_DRAFT": "2"})
    assert proc.returncode == 0, proc.stderr
    assert "::warning::" in proc.stdout
    assert chamadas(raiz) == ["--prd 963"]


def test_pasta_errada_do_manual_derruba_a_action(tmp_path):
    raiz = arvore_do_draft(tmp_path, [963])
    proc = rodar("Tirar do draft", raiz, {"SAIDA_DO_DRAFT": "1"})
    assert proc.returncode == 1


SNAPSHOT_FALSO = """\
import sys
from pathlib import Path
Path("args.txt").write_text(" ".join(sys.argv[1:]))
"""


def test_snapshot_roda_sem_commitar_sozinho(tmp_path):
    """Sem `--no-commit` o `snapshot.py` commita por conta própria, com outra
    mensagem e sem `[skip ci]`; quem commita aqui é o job do bot."""
    raiz = tmp_path / "repo"
    scripts = raiz / ".claude" / "skills" / "snapshot" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "snapshot.py").write_text(SNAPSHOT_FALSO, encoding="utf-8")
    proc = rodar("Snapshot", raiz)
    assert proc.returncode == 0, proc.stderr
    assert (raiz / "args.txt").read_text(encoding="utf-8").split() == ["--root", ".", "--no-commit"]


def test_backend_montado_com_o_mesmo_ambiente_do_ci():
    """O snapshot lê as rotas do app montado (`introspect_routes.py`, pelo
    `.venv` do backend). Sem o venv, ou sem as variáveis que o Settings exige,
    ele cai no parser AST e rebaixa o ROTAS.md (o modo parcial do macOS)."""
    ci = workflow(RAIZ / ".github" / "workflows" / "ci.yml")
    assert workflow()["jobs"]["gerar"]["env"] == ci["jobs"]["backend"]["env"]
    venv = passo("backend")
    assert venv["working-directory"] == "hospital-reunioes/backend"
    assert "uv sync --frozen" in venv["run"]


# O que a Action escreve, um caminho de cada filtro. A página do Manual só
# muda pelo draft: o resto dela é o que o PR revisado deixou na `main`.
SNAPSHOTS = ["docs/spec/snapshots/ROTAS.md", "docs/ARQUITETURA.md"]
PAGINA = "docs/manual/src/content/docs/ouvidoria/index.mdx"
ESCRITOS = [*SNAPSHOTS, PAGINA]
PAGINA_EM_DRAFT = "---\ntitle: Ouvidoria\nprd: [646]\ndraft: true\n---\n\nTexto da página.\n"
APAGAVEL = "docs/spec/snapshots/VELHO.md"
CODIGO = "hospital-reunioes/backend/app/main.py"


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=alguem", "-c", "user.email=alguem@example.com", *args],
        cwd=cwd, env=ENV_GIT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def escrever(raiz: Path, caminho: str, texto: str) -> None:
    arq = raiz / caminho
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_text(texto, encoding="utf-8")


def main_de_brinquedo(tmp_path: Path) -> tuple[Path, Path]:
    """A `main` (repo bare) e um clone de quem mergeia PR."""
    origem = tmp_path / "origem.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origem))
    outro = tmp_path / "outro"
    git(tmp_path, "clone", "-q", str(origem), str(outro))
    for caminho in [*SNAPSHOTS, APAGAVEL, CODIGO, "hospital-reunioes/backend/uv.lock"]:
        escrever(outro, caminho, "antes\n")
    escrever(outro, PAGINA, PAGINA_EM_DRAFT)
    git(outro, "add", "-A")
    git(outro, "commit", "-q", "-m", "base")
    git(outro, "push", "-q", "origin", "HEAD:main")
    return origem, outro


def clonar(tmp_path: Path, origem: Path, nome: str) -> Path:
    """O checkout de um job: a ponta da `main` naquela hora."""
    destino = tmp_path / nome / "repo"
    destino.parent.mkdir()
    git(tmp_path, "clone", "-q", "-b", "main", str(origem), str(destino))
    return destino


def resolver_runner_temp(valor: str, temp: Path) -> Path:
    return Path(valor.replace("${{ runner.temp }}", str(temp)))


def passar_artefato(temp_gerar: Path, temp_commitar: Path) -> None:
    """O upload do `gerar` e o download do `commitar`, lidos do YAML: um
    arquivo só, zipado no upload e extraído com o mesmo nome no `path`."""
    w = workflow()
    upload = [p for p in w["jobs"]["gerar"]["steps"] if p.get("uses", "").startswith("actions/upload-artifact@")]
    download = [p for p in w["jobs"]["commitar"]["steps"]
                if p.get("uses", "").startswith("actions/download-artifact@")]
    assert len(upload) == 1 and len(download) == 1
    assert upload[0]["with"]["name"] == download[0]["with"]["name"]
    arquivo = resolver_runner_temp(upload[0]["with"]["path"], temp_gerar)
    destino = resolver_runner_temp(download[0]["with"]["path"], temp_commitar)
    destino.mkdir(parents=True, exist_ok=True)
    shutil.copy(arquivo, destino / arquivo.name)


def gerar_e_commitar(tmp_path: Path, origem: Path, mexer, entre_os_jobs=None,
                     durante_o_commit=None) -> subprocess.CompletedProcess:
    """O run inteiro: checkout e escrita no `gerar`, empacotar, artefato,
    checkout do `commitar` e o passo do commit."""
    gerador = clonar(tmp_path, origem, "gerar")
    mexer(gerador)
    temp_gerar = tmp_path / "temp-gerar"
    temp_gerar.mkdir()
    proc = rodar("Empacotar", gerador, {"RUNNER_TEMP": str(temp_gerar)})
    assert proc.returncode == 0, proc.stderr
    if entre_os_jobs:
        entre_os_jobs()
    commitador = clonar(tmp_path, origem, "commitar")
    temp_commitar = tmp_path / "temp-commitar"
    passar_artefato(temp_gerar, temp_commitar)
    if durante_o_commit:
        durante_o_commit()
    return rodar("Commitar", commitador, {"RUNNER_TEMP": str(temp_commitar)}, job="commitar")


def mergear_pr(outro: Path, caminho: str, mensagem: str) -> str:
    git(outro, "pull", "-q", "origin", "main")
    escrever(outro, caminho, f"{mensagem}\n")
    git(outro, "add", "-A")
    git(outro, "commit", "-q", "-m", mensagem)
    git(outro, "push", "-q", "origin", "HEAD:main")
    return git(outro, "rev-parse", "HEAD")


def test_commit_do_bot_com_skip_ci_so_do_que_a_action_escreve(tmp_path):
    origem, _ = main_de_brinquedo(tmp_path)

    def mexer(gerador: Path) -> None:
        for caminho in SNAPSHOTS:
            escrever(gerador, caminho, "novo\n")
        escrever(gerador, PAGINA, sem_draft(PAGINA_EM_DRAFT))
        (gerador / APAGAVEL).unlink()
        escrever(gerador, "hospital-reunioes/backend/uv.lock", "mexido pelo ambiente\n")
        escrever(gerador, "lixo-do-runner.txt", "fora do git\n")

    proc = gerar_e_commitar(tmp_path, origem, mexer)

    assert proc.returncode == 0, proc.stderr
    autor, email, assunto = git(origem, "log", "-1", "--format=%an|%ae|%s", "main").split("|")
    assert autor == "github-actions[bot]"
    assert email == "41898282+github-actions[bot]@users.noreply.github.com"
    assert "[skip ci]" in assunto
    arquivos = git(origem, "show", "--name-only", "--format=", "main").splitlines()
    assert sorted(arquivos) == sorted([*ESCRITOS, APAGAVEL])
    assert APAGAVEL not in git(origem, "ls-tree", "-r", "--name-only", "main").splitlines()
    assert git(origem, "show", f"main:{PAGINA}") + "\n" == PAGINA_EM_DRAFT.replace("draft: true", "draft: false")
    assert not acorda(arquivos), "o commit do bot acordaria a própria Action"


def test_patch_com_caminho_de_fora_so_entra_nos_tres_caminhos(tmp_path):
    """O `gerar` roda pacote do PyPI e pode entregar artefato adulterado: o
    `commitar` aplica só o que cai nos caminhos da Action."""
    origem, _ = main_de_brinquedo(tmp_path)
    gerador = clonar(tmp_path, origem, "adulterado")
    escrever(gerador, CODIGO, "codigo malicioso\n")
    escrever(gerador, ".github/workflows/x.yml", "on: push\n")
    escrever(gerador, "docs/spec/snapshots/ROTAS.md", "rota nova\n")
    git(gerador, "add", "-A")
    patch = tmp_path / "temp-commitar" / "pos-merge" / "pos-merge.patch"
    patch.parent.mkdir(parents=True)
    patch.write_text(git(gerador, "diff", "--cached", "--binary") + "\n", encoding="utf-8")
    commitador = clonar(tmp_path, origem, "commitar")

    proc = rodar("Commitar", commitador, {"RUNNER_TEMP": str(tmp_path / "temp-commitar")}, job="commitar")

    assert proc.returncode == 0, proc.stderr
    arquivos = git(origem, "show", "--name-only", "--format=", "main").splitlines()
    assert arquivos == ["docs/spec/snapshots/ROTAS.md"]
    assert git(origem, "show", f"main:{CODIGO}") == "antes"


def commitar_patch_adulterado(tmp_path: Path, origem: Path, adulterar) -> subprocess.CompletedProcess:
    """O `commitar` sobre um patch montado à mão, com detecção de rename."""
    gerador = clonar(tmp_path, origem, "adulterado")
    adulterar(gerador)
    git(gerador, "add", "-A")
    patch = tmp_path / "temp-commitar" / "pos-merge" / "pos-merge.patch"
    patch.parent.mkdir(parents=True)
    patch.write_text(git(gerador, "diff", "--cached", "--binary", "-M") + "\n", encoding="utf-8")
    commitador = clonar(tmp_path, origem, "commitar")
    return rodar("Commitar", commitador, {"RUNNER_TEMP": str(tmp_path / "temp-commitar")}, job="commitar")


def test_rename_de_fora_para_dentro_dos_tres_caminhos_e_recusado(tmp_path):
    """O --include do `git apply` só olha o nome novo: `rename from` o código
    `rename to` o snapshot passaria e apagaria o código da `main`."""
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    def adulterar(gerador: Path) -> None:
        git(gerador, "mv", CODIGO, "docs/spec/snapshots/main.py")

    proc = commitar_patch_adulterado(tmp_path, origem, adulterar)

    assert "rename from " + CODIGO in (tmp_path / "temp-commitar" / "pos-merge" / "pos-merge.patch").read_text()
    assert proc.returncode != 0
    assert git(origem, "rev-parse", "main") == antes
    assert git(origem, "show", f"main:{CODIGO}") == "antes"


def test_symlink_nos_tres_caminhos_e_recusado(tmp_path):
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    def adulterar(gerador: Path) -> None:
        (gerador / "docs/spec/snapshots/link.md").symlink_to("../../../" + CODIGO)

    proc = commitar_patch_adulterado(tmp_path, origem, adulterar)

    assert "new file mode 120000" in (tmp_path / "temp-commitar" / "pos-merge" / "pos-merge.patch").read_text()
    assert proc.returncode != 0
    assert git(origem, "rev-parse", "main") == antes


def test_gitlink_nos_tres_caminhos_e_recusado(tmp_path):
    """Gitlink (modo 160000) sem `.gitmodules` faz o `git submodule update` do
    clone sair com 128: nenhum build sobe até alguém apagar o gitlink."""
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    def adulterar(gerador: Path) -> None:
        sub = gerador / "docs/spec/snapshots/sub"
        sub.mkdir()
        git(sub, "init", "-q")
        git(sub, "commit", "-q", "--allow-empty", "-m", "sub")

    proc = commitar_patch_adulterado(tmp_path, origem, adulterar)

    assert "new file mode 160000" in (tmp_path / "temp-commitar" / "pos-merge" / "pos-merge.patch").read_text()
    assert proc.returncode != 0
    assert "modo" in proc.stdout
    assert git(origem, "rev-parse", "main") == antes


# O que executa no `pnpm build` de quem roda o `publicar.sh` depois do draft.
CODIGO_NA_MDX = {
    "import": 'import { execSync } from "node:child_process";\nexport const x = execSync("id");\n',
    "expressao": '{require("node:child_process").execSync("id")}\n',
}


@pytest.mark.parametrize("codigo", CODIGO_NA_MDX.values(), ids=CODIGO_NA_MDX.keys())
def test_pagina_do_manual_que_muda_alem_do_draft_e_recusada(tmp_path, codigo):
    """O `tirar_draft_manual.py` só troca `true` por `false` na linha
    `draft:`. Qualquer outra linha que o patch traga para a MDX é código no
    build de quem publica, com o login da Vercel e o `gh` na máquina."""
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    def adulterar(gerador: Path) -> None:
        escrever(gerador, PAGINA, sem_draft(PAGINA_EM_DRAFT) + codigo)

    proc = commitar_patch_adulterado(tmp_path, origem, adulterar)

    assert proc.returncode != 0
    assert PAGINA in proc.stdout
    assert git(origem, "rev-parse", "main") == antes


def nova_pagina(gerador: Path) -> None:
    escrever(gerador, "docs/manual/src/content/docs/ouvidoria/nova.mdx",
             "---\ntitle: Nova\ndraft: false\n---\n\n" + CODIGO_NA_MDX["import"])


def apagar_pagina(gerador: Path) -> None:
    (gerador / PAGINA).unlink()


@pytest.mark.parametrize("adulterar", [nova_pagina, apagar_pagina], ids=["nova", "apagada"])
def test_pagina_nova_ou_apagada_no_manual_e_recusada(tmp_path, adulterar):
    """Página do Manual nasce e morre por PR revisado; a Action só tira draft."""
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    proc = commitar_patch_adulterado(tmp_path, origem, adulterar)

    assert proc.returncode != 0
    assert "cria ou apaga" in proc.stdout
    assert git(origem, "rev-parse", "main") == antes


def test_sem_diff_nao_commita(tmp_path):
    origem, _ = main_de_brinquedo(tmp_path)
    antes = git(origem, "rev-parse", "main")

    def mexer(gerador: Path) -> None:
        escrever(gerador, "hospital-reunioes/backend/uv.lock", "mexido pelo ambiente\n")

    proc = gerar_e_commitar(tmp_path, origem, mexer)

    assert proc.returncode == 0, proc.stderr
    assert git(origem, "rev-parse", "main") == antes


def test_merge_que_entra_durante_a_action_nao_derruba_o_push(tmp_path):
    """Um PR pode entrar na `main` entre os dois jobs (o patch aplica sobre a
    ponta nova) e outro durante o commit: sem rebase o push seria recusado
    (non_fast_forward no ruleset)."""
    origem, outro = main_de_brinquedo(tmp_path)
    shas: list[str] = []

    def mexer(gerador: Path) -> None:
        escrever(gerador, "docs/ARQUITETURA.md", "bloco AUTO novo\n")

    proc = gerar_e_commitar(
        tmp_path, origem, mexer,
        entre_os_jobs=lambda: shas.append(mergear_pr(outro, "hospital-reunioes/backend/app/a.py", "PR 1")),
        durante_o_commit=lambda: shas.append(mergear_pr(outro, "hospital-reunioes/backend/app/b.py", "PR 2")),
    )

    assert proc.returncode == 0, proc.stderr
    assert git(origem, "rev-parse", "main~1") == shas[1]
    assert git(origem, "rev-parse", "main~2") == shas[0]
    assert git(origem, "log", "-1", "--format=%an", "main") == "github-actions[bot]"
    assert git(origem, "show", "main:docs/ARQUITETURA.md") == "bloco AUTO novo"


def test_um_run_por_vez_e_o_draft_nao_se_perde_com_o_snapshot_vermelho():
    """Runs na fila partem da ponta da `main` (o commit do run anterior), não
    do commit do evento. O draft vem antes do backend e o patch sai e é
    commitado mesmo com o snapshot vermelho: o próximo registro troca os PRDs
    do último deploy, e o draft que não entrou agora não entraria mais."""
    w = workflow()
    assert w["concurrency"]["cancel-in-progress"] is False
    passos = w["jobs"]["gerar"]["steps"]
    assert passos[0]["uses"].startswith("actions/checkout@") and passos[0]["with"]["ref"] == "main"
    ordem = [p.get("name") for p in passos]
    assert (ordem.index(passo("Tirar do draft")["name"])
            < ordem.index(passo("backend")["name"])
            < ordem.index(passo("Snapshot")["name"])
            < ordem.index(passo("Empacotar")["name"]))
    sempre = "${{ !cancelled() }}"
    assert passo("Empacotar")["if"] == sempre
    upload = [p for p in passos if p.get("uses", "").startswith("actions/upload-artifact@")]
    assert upload[0]["if"] == sempre
    assert w["jobs"]["commitar"]["if"] == sempre


def test_estes_testes_rodam_quando_so_o_workflow_muda():
    """Os testes de `tools/` rodam no `manual.yml`, que só acorda pelos caminhos
    dele: PR que mexesse só no YAML entraria sem este contrato rodar."""
    on = gatilhos(RAIZ / ".github" / "workflows" / "manual.yml")
    for evento in ("push", "pull_request"):
        assert ".github/workflows/pos-merge.yml" in on[evento]["paths"], evento
