#!/usr/bin/env python3
"""fechar_onda.py: o rabo unico (ADR 0061). Leva um PR avulso ou uma onda da
`/onda-enxuta` a producao com um merge por PR na main e UM build.

Uso:
    python fechar_onda.py --prs 850 851 852 --sessao onda-a-1 [--dry-run] [--raiz <repo>]
    python fechar_onda.py --prs 907 [--dry-run]     # PR avulso: sem --sessao, a chave e pr-907

A ordem dos PRs e a ordem de merge. O script nunca toca na arvore principal
(ela pode estar suja): todo o trabalho acontece num worktree descartavel de
caminho curto (`~/wt-<sessao>`, por causa do MAX_PATH do Windows).

A main e protegida por ruleset (issue #910, ADR 0061 decisao 3): PR
obrigatorio, CI obrigatorio e em dia com a base, sem push direto. Por isso o
script nunca empurra na main: cada PR do lote entra pela API do GitHub com
squash (o unico metodo que o repositorio permite), no proprio numero, em ordem,
como o PR avulso (ADR 0064, decisao 3). A onda e o avulso com mais PRs.

Classe do lote, pelos arquivos (issue #965): "app" se algum esta em
`hospital-reunioes/`, "ferramenta" se nenhum esta. Lote misto e app. Os
arquivos sao os do `git diff --no-renames` de cada PR, como no detector do CI:
mover codigo para fora de `hospital-reunioes/` conta como app. Classe, versao
e servicos saem do lote inteiro, antes do primeiro merge.
  - app: a sequencia inteira abaixo.
  - ferramenta: so merge pela API depois do CI verde (passos 1 a 4 e 9). Sem
    versao nova, sem APP_VERSION, sem tag, sem esperar build, sem health, sem PR de
    registro e sem entrada no history.json. Se o webhook do Coolify disparar
    build em algum merge, o rabo o cancela, como faz com o build do registro.

Sequencia (cada passo imprime no maximo uma linha, o 4 uma por PR; sucesso
cabe em 10 linhas mais uma por PR, fora as da migration):
  1. pre-condicoes (gh, coolify, PRs abertos e verdes, origin/main buscado,
     nenhuma migration nova com numero que a main ja usa, e o corpo do PR
     declarando o sha256 de cada migration nova igual ao do arquivo).
     Migration nova no lote (issue #969): imprime o caminho clicavel
     `<arquivo>:1` de cada uma (copia do head do PR, fora do repositorio) e
     consulta o /api/health do backend ate ele devolver o numero da maior, com
     teto de 24 h: toda migration termina gravando o proprio numero em
     `migracoes_aplicadas`, e o health devolve o maior. A espera vem ANTES do
     semaforo: 24 h com a trava pega parariam os outros deploys, e o
     semaforo.sh a da por velha em 60 min. Backend no ar sem o campo
     `migracao` (anterior ao #969): avisa e segue sem esperar, como antes
  2. semaforo de deploy (chave = nome da sessao, unica por construcao)
  3. versao nova (semver) pelo tipo dominante dos commits do lote, a partir do
     `last_app_version` do state.json conferido com a maior tag vX.Y.Z
     (ferramenta nao muda a versao). Sem commit (issue #967): o package.json do
     frontend fica congelado
  4. PR a PR, na ordem, num worktree descartavel na branch do PR: a origin/main
     por merge se a branch ficou atras (o ruleset exige em dia com a base, e o
     merge do PR anterior do lote deixa o seguinte atras), push na branch do PR
     (nunca na main; em dia, o head nao muda e o CI dele ja vale), CI verde no
     head e merge pela API (squash, conferindo o sha do head). Antes do primeiro
     merge: a imagem no ar de cada app do lote (alvo do rollback) e o
     APP_VERSION no backend e no frontend do Coolify (o backend a le no runtime,
     o frontend no build, pelo ARG do Dockerfile). PR que nao mergeia (conflito
     com a main depois do anterior, push recusado, CI vermelho, head que andou,
     merge recusado) imprime uma linha `de fora:` e o lote segue sem ele; os ja
     mergeados ficam
  5. tag vX.Y.Z no squash do ultimo PR que entrou, pela API (tag que falha nao
     para o deploy)
  6. um build: o deploy que o webhook do Coolify dispara para cada squash
     intermediario e cancelado (o mesmo mecanismo do registro, issue #851) e o
     rabo monitora so o do ultimo, em cada service; forca se nao disparar
  7. health com version match. Health ruim: rollback automatico (issue #968),
     cada app do lote volta a imagem anterior no Coolify, a que estava no ar
     antes do primeiro merge (`current` do `coolify app rollback images`, lida
     antes dele, e `rollback run`, sem forcar build) e o APP_VERSION antigo volta
     aos apps, antes da imagem subir; o health e conferido de novo na versao antiga
  8. registro num PR so de docs, so com history.json (todos os deploys, sem
     teto) e state.json (ADR 0062, decisao 9), mergeado pela API; o build que o
     webhook do Coolify dispara para ele e cancelado (issue #851). Snapshot e
     draft do Manual nao sao do rabo: a Action do push da main roda os dois
     depois do registro (ADR 0062, decisao 10)
  9. limpeza (worktrees, worktrees de agente ja entregues) e soltar o semaforo

Commits que chegam a main:
  - um squash por PR que entrou, "<titulo do PR> (#N)", no PR avulso e na onda;
    a versao nao vira commit: vive no APP_VERSION do Coolify e na tag
  - o do registro: "chore(deploy): registro do PR #N (vX.Y.Z) (#R)" ou
    "chore(deploy): registro da onda <sessao> (vX.Y.Z) (#R)"
No PR avulso, o registro do history.json nomeia PR e issue, sem a onda; na
onda, cada PR e a issue dele. O campo `sha` do history.json e o do squash do
ultimo PR: o commit que foi para producao. O registro vem depois, so com docs.

Codigos de saida:
  0  todos os PRs na main, health verde, registro na main (ferramenta: merges na main)
  1  pre-condicao falhou ou trava velha: nada foi tocado
  2  algum PR ficou de fora (conflito com a main, push na branch rejeitado, CI
     vermelho, head que andou ou merge recusado), cada um com a linha `de fora:`;
     os que entraram seguem o fluxo inteiro e o semaforo e solto. Nenhum entrou:
     nada na main, worktree removido, semaforo solto. Rode de novo so com os de
     fora, depois de corrigir. Com 3 a 6, as linhas `de fora:` saem do mesmo jeito
  3  build falhou no Coolify: SEMAFORO FICA PRESO, rode `/deploy rollback` com a chave impressa
  4  health falhou (ou versao nao bate) e o rollback automatico tambem falhou (sem
     imagem anterior, Coolify recusou, ou health ainda ruim): SEMAFORO FICA PRESO,
     mesma instrucao do 3
  5  producao ok, mas o PR de registro nao entrou: semaforo solto; mergeie o PR impresso
     quando o CI dele ficar verde. Ferramenta: merge feito, producao intacta,
     semaforo solto, mas a arrumacao depois do merge falhou (a linha diz o que falta)
  6  rollback feito: o health falhou, a imagem anterior e o APP_VERSION antigo
     voltaram e o health ficou verde de novo; semaforo solto, sem registro. A tag
     vX.Y.Z fica no squash ruim, e a proxima versao sai depois dela. Os squashes
     seguem na main: quem chamou abre o PR de revert deles (sem rebuild), reabre a
     issue de cada um com `ready-for-agent` e a linha `health:` (o que o health
     respondeu), conta uma tentativa de cada fatia e notifica
  7  migration vencida: o /api/health nao devolveu o numero da migration do lote
     em 24 h: nada entrou na main, o semaforo nao chegou a ser pego e os PRs
     seguem abertos; quem chamou notifica, e o rabo roda de novo depois que a
     migration for colada no Studio

`--dry-run`: executa 1 e calcula o 3 sem escrever; imprime o plano (PR,
issue, classe e tipo de versao: "app: bump ..." ou "ferramenta: só merge") e o
que faria nos demais (um merge pela API por PR, em ordem, com a espera da
migration, sem consultar o health); nao pega semaforo, nao toca no Coolify,
nao pusha.

Windows: `bash` do Git no PATH (para o semaforo.sh).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# A guarda de migration repetida e a mesma do CI (issue #903): vem do tools/
# do mesmo checkout deste script.
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools"))
import checar_migration_repetida  # noqa: E402
import ci_sem_runner  # noqa: E402

EXIT_PRECOND = 1
EXIT_MERGE = 2
EXIT_BUILD = 3
EXIT_HEALTH = 4
EXIT_REGISTRO = 5
EXIT_ROLLBACK = 6
EXIT_MIGRACAO = 7

SEMAFORO = ".claude/skills/deploy/scripts/semaforo.sh"
SPEC = "docs/spec"
HISTORY = f"{SPEC}/deploy/history.json"
STATE = f"{SPEC}/deploy/state.json"
APP = "hospital-reunioes/"
BUILD_WAIT_WEBHOOK_S = 120
BUILD_POLL_S = 10
BUILD_TIMEOUT_S = 40 * 60
CHECKS_POLL_S = 15
CHECKS_TIMEOUT_S = 40 * 60
HEAD_ATRASADO_S = 120  # o GitHub registra o push no PR em segundos
REGISTRO_JANELA_S = 90  # o webhook do Coolify dispara em segundos
MIGRACAO_TIMEOUT_S = 24 * 60 * 60  # teto da espera pela migration colada no Studio (issue #969)
MIGRACAO_POLL_S = 60
SEM_CAMPO = "sem-campo"  # o /api/health no ar e anterior ao #969: nao informa a migration
VERDE = ("SUCCESS", "NEUTRAL", "SKIPPED")
VERMELHO = ("FAILURE", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED", "STARTUP_FAILURE", "STALE", "ERROR")
COAUTHOR = "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"

# Windows: "bash" nu no subprocess cai no System32 (WSL) antes do PATH.
BASH = shutil.which("bash") or "bash"

T0 = time.time()


# ----------------------------------------------------------------- utilidades

def falhar(msg: str, code: int) -> None:
    print(msg)
    sys.exit(code)


def run(cmd: list[str], cwd: Path | None = None, check: bool = True,
        timeout: int | None = 600, env: dict | None = None) -> subprocess.CompletedProcess:
    full_env = dict(os.environ)
    full_env.setdefault("PYTHONUTF8", "1")
    if env:
        full_env.update(env)
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          timeout=timeout, env=full_env)
    if check and proc.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} -> {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:400]}")
    return proc


def gh_json(args: list[str], cwd: Path | None = None):
    proc = run(["gh", *args], cwd=cwd)
    return json.loads(proc.stdout or "null")


def ler_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def escrever_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def agora_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def dur(seg: float | int | None) -> str:
    if seg is None:
        return "?"
    seg = int(seg)
    return f"{seg // 60}m{seg % 60:02d}s"


def bash_path(p: Path) -> str:
    return str(p).replace("\\", "/")


# ------------------------------------------------------------- pre-condicoes

def checar_pre_condicoes(raiz: Path, prs: list[int], dry: bool) -> tuple[list[dict], list[tuple[str, str]]]:
    """Devolve as infos dos PRs e (head, caminho) de cada migration nova do lote."""
    if run(["gh", "auth", "status"], check=False).returncode != 0:
        falhar("pre-condicao: `gh auth status` falhou.", EXIT_PRECOND)
    if not shutil.which("coolify"):
        if dry:
            print("aviso: `coolify` nao esta no PATH (o dry-run segue; o fechamento real precisa dele).")
        else:
            falhar("pre-condicao: `coolify` nao esta no PATH.", EXIT_PRECOND)
    if not shutil.which("bash"):
        falhar("pre-condicao: `bash` (Git Bash) nao esta no PATH; o semaforo precisa dele.", EXIT_PRECOND)
    run(["git", "fetch", "-q", "origin", "main"], cwd=raiz)

    infos = []
    problemas = []
    for n in prs:
        info = None
        for tentativa in range(6):
            info = gh_json(["pr", "view", str(n), "--json",
                            "number,state,mergeable,mergeStateStatus,statusCheckRollup,headRefName,"
                            "headRefOid,isCrossRepository,baseRefName,title,files,commits,url,"
                            "closingIssuesReferences,body"], cwd=raiz)
            if info.get("mergeable") != "UNKNOWN":
                break
            time.sleep(5)
        if info.get("state") != "OPEN":
            problemas.append(f"#{n} esta {info.get('state')}")
        if info.get("baseRefName") not in (None, "main"):
            problemas.append(f"#{n} tem base {info.get('baseRefName')}, nao main")
        if info.get("mergeable") != "MERGEABLE":
            problemas.append(f"#{n} nao e MERGEABLE ({info.get('mergeable')}/{info.get('mergeStateStatus')})")
        checks = info.get("statusCheckRollup") or []
        ruins = [c for c in checks
                 if (c.get("conclusion") or c.get("state") or "").upper()
                 not in ("SUCCESS", "NEUTRAL", "SKIPPED")]
        if ruins:
            nomes = ", ".join((c.get("name") or c.get("context") or "?") for c in ruins[:4])
            problemas.append(f"#{n} com check nao verde: {nomes}")
        elif not checks:
            # o CI nao rodou: o ruleset exige os checks e o esperar_checks nao
            # aceita lista vazia, entao vale para app e ferramenta (issue #965)
            problemas.append(f"#{n} sem nenhum check (o CI nao rodou)")
        infos.append(info)
    if problemas:
        falhar("pre-condicao: " + "; ".join(problemas) + ".", EXIT_PRECOND)
    return infos, conferir_migrations(raiz, infos)


def conferir_migrations(raiz: Path, infos: list[dict]) -> list[tuple[str, str]]:
    """Para se algum PR adiciona migration com numero que a origin/main ja usa,
    ou se o sha256 que o corpo do PR declara nao e o do arquivo. Devolve
    (head, caminho) de cada migration nova do lote.

    Roda depois do `git fetch origin main`: o CI conferiu contra a main da hora
    do push, e ela pode ter andado desde entao. Renumerar e do autor.
    """
    novas = []
    for info in infos:
        n = info["number"]
        run(["git", "fetch", "-q", "origin", f"pull/{n}/head"], cwd=raiz)
        head = run(["git", "rev-parse", "FETCH_HEAD"], cwd=raiz).stdout.strip()
        info["head_conferido"] = head  # o mergear recusa outro head (revisao do PR #996)
        achadas = checar_migration_repetida.colisoes(raiz, "origin/main", head)
        if achadas:
            falhar(f"pre-condicao: #{n}: " + checar_migration_repetida.mensagem(achadas), EXIT_PRECOND)
        novas += [(head, caminho) for caminho in conferir_hash_das_migrations(raiz, n, head, info.get("body") or "")]
    return novas


def conferir_hash_das_migrations(raiz: Path, n: int, head: str, corpo: str) -> list[str]:
    """Para se o corpo do PR nao traz o sha256 de cada migration nova do head.
    Devolve o caminho de cada uma.

    O SQL que o humano cola no Studio e o que a review leu no corpo do PR, e o
    hash do corpo e a prova de que e o mesmo arquivo que vai entrar na main.
    """
    novas = run(["git", "diff", "--name-only", "-M", "--diff-filter=A", f"origin/main...{head}", "--",
                 checar_migration_repetida.PASTA], cwd=raiz).stdout.split()
    declarados = sorted({h.lower() for h in re.findall(r"\b[0-9a-fA-F]{64}\b", corpo)})
    conferidas = []
    for caminho in novas:
        if run(["git", "cat-file", "-e", f"origin/main:{caminho}"], cwd=raiz, check=False).returncode == 0:
            continue  # ja esta na main (PR empilhado sobre um que entrou por squash)
        conteudo = subprocess.run(["git", "show", f"{head}:{caminho}"], cwd=str(raiz),
                                  capture_output=True, check=True).stdout
        sha = hashlib.sha256(conteudo).hexdigest()
        if sha in declarados:
            conferidas.append(caminho)
            continue
        nome = Path(caminho).name
        if not declarados:
            falhar(f"pre-condicao: #{n}: o corpo do PR nao declara o sha256 de {nome}; "
                   f"o arquivo no head tem {sha}. Ponha o hash no corpo e rode de novo.", EXIT_PRECOND)
        falhar(f"pre-condicao: #{n}: o sha256 de {nome} no corpo do PR ({', '.join(declarados)}) "
               f"nao bate com o arquivo no head ({sha}). Atualize o SQL e o hash do corpo e rode de novo.",
               EXIT_PRECOND)
    return conferidas


# ---------------------------------------------------------------- migration

def migracao_no_health(url: str) -> int | str | None:
    """O numero da ultima migration aplicada que o /api/health devolve (issue #969).
    None: o health nao respondeu, a resposta nao e a do health, ou a tabela
    `migracoes_aplicadas` esta vazia ou ainda nao existe. SEM_CAMPO: a resposta e
    a do health, sem o campo `migracao` (backend anterior ao #969)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fechar_onda"}),
                                    timeout=15) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        try:
            body = e.read()  # o 503 do banco degradado ainda traz o numero
        except Exception:
            return None
    except Exception:
        return None
    try:
        dado = json.loads(body)
    except ValueError:
        return None
    if not isinstance(dado, dict) or "status" not in dado or "db" not in dado:
        return None
    if "migracao" not in dado:
        return SEM_CAMPO
    numero = dado["migracao"]
    return numero if isinstance(numero, int) and not isinstance(numero, bool) else None


def esperar_migracao(url: str, numero: int) -> tuple[str, int | None]:
    """Consulta o /api/health ate ele devolver `numero` ou mais, com teto de
    MIGRACAO_TIMEOUT_S. Devolve ("aplicada", SEM_CAMPO ou "vencida", o ultimo
    numero lido)."""
    limite = time.time() + MIGRACAO_TIMEOUT_S
    ultimo = None
    while True:
        lido = migracao_no_health(url)
        if lido == SEM_CAMPO:
            return SEM_CAMPO, None
        if lido is not None:
            ultimo = lido
            if lido >= numero:
                return "aplicada", lido
        if time.time() >= limite:
            return "vencida", ultimo
        time.sleep(MIGRACAO_POLL_S)


def esperar_migrations_do_lote(raiz: Path, backend: dict, novas: list[tuple[str, str]], numero: int,
                               sessao: str, prs_txt: str) -> bool:
    """Pede ao humano cada migration nova pelo caminho clicavel e espera a maior
    aparecer no /api/health (issue #969). False se venceu o teto."""
    pasta = Path(tempfile.gettempdir()) / "fechar_onda" / sessao
    pasta.mkdir(parents=True, exist_ok=True)
    for head, caminho in novas:
        # o arquivo do head do PR, nunca o corpo do PR: e o que vai entrar na main
        conteudo = subprocess.run(["git", "show", f"{head}:{caminho}"], cwd=str(raiz),
                                  capture_output=True, check=True).stdout
        arquivo = pasta / Path(caminho).name
        arquivo.write_bytes(conteudo)
        linhas = conteudo.count(b"\n")
        print(f"migration: cole no Studio {arquivo}:1 ({linhas} linhas, sha256 "
              f"{hashlib.sha256(conteudo).hexdigest()[:12]}); o rabo espera o {numero} no /api/health",
              flush=True)
    t = time.time()
    status, ultimo = esperar_migracao(url_do_health(backend), numero)
    if status == SEM_CAMPO:
        print(f"migration: o /api/health no ar nao informa a migration aplicada (backend anterior ao #969); "
              f"o rabo segue sem esperar, confira que a {numero} foi colada no Studio.", flush=True)
    elif status == "aplicada":
        print(f"migration: {numero} aplicada, o /api/health devolveu {ultimo} em {dur(time.time() - t)}", flush=True)
    else:
        print(f"migration: vencida, o /api/health nao chegou a {numero} em {MIGRACAO_TIMEOUT_S // 3600} h "
              f"(ultimo: {ultimo}). Nada entrou na main e o semaforo nao foi pego; PRs {prs_txt} seguem abertos. "
              "Cole a migration no Studio e rode o rabo de novo.")
        return False
    return True


# ----------------------------------------------------------------- semaforo

def semaforo(raiz: Path, acao: str, chave: str, descricao: str = "") -> int:
    cmd = [BASH, bash_path(raiz / SEMAFORO), acao, chave]
    if descricao:
        cmd.append(descricao)
    proc = run(cmd, cwd=raiz, check=False, timeout=700)
    return proc.returncode


def pegar_semaforo(raiz: Path, chave: str, prs: list[int], avulso: bool = False) -> None:
    desc = (f"fechar_onda: PR avulso #{prs[0]}" if avulso
            else f"onda-enxuta {chave}: PRs " + " ".join(f"#{p}" for p in prs))
    while True:
        rc = semaforo(raiz, "pegar", chave, desc)
        if rc == 0:
            return
        if rc == 3:
            print("semaforo: outra sessao esta deployando, esperando mais um ciclo.")
            continue
        if rc == 2:
            falhar("semaforo: trava velha (mais de 60 min). Confira `coolify app deployments list` e, "
                   "sem build rodando, `semaforo.sh soltar <chave-do-dono> --forcar`.", EXIT_PRECOND)
        falhar(f"semaforo: saida inesperada {rc}.", EXIT_PRECOND)


# ----------------------------------------------------------------- worktree

def criar_worktree(raiz: Path, sessao: str) -> Path:
    wt = Path.home() / f"wt-{sessao}"
    if wt.exists():
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=raiz, check=False)
        shutil.rmtree(wt, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=raiz, check=False)
    run(["git", "worktree", "add", "--detach", str(wt), "origin/main"], cwd=raiz)
    return wt


def remover_worktree(raiz: Path, wt: Path | None) -> None:
    if wt and wt.exists():
        run(["git", "worktree", "remove", "--force", str(wt)], cwd=raiz, check=False)
        shutil.rmtree(wt, ignore_errors=True)
    run(["git", "worktree", "prune"], cwd=raiz, check=False)


# ------------------------------------------------------------------- merges

class MergeConflito(Exception):
    def __init__(self, pr: int, arquivos: list[str]):
        super().__init__(pr)
        self.pr = pr
        self.arquivos = arquivos


def entrar_na_branch_do_pr(wt: Path, info: dict) -> bool:
    """O worktree vai para a ponta da branch do PR, que e o que entra na main.
    O ruleset exige a branch em dia com a base: se a main andou (inclusive pelo
    merge do PR anterior do lote), ela vem por merge. Devolve True quando
    precisou trazer a main."""
    n, branch = info["number"], info["headRefName"]
    run(["git", "fetch", "-q", "origin", f"+refs/heads/{branch}:refs/remotes/origin/{branch}"], cwd=wt)
    run(["git", "checkout", "-q", "--detach", f"origin/{branch}"], cwd=wt)
    ponta = run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()
    # um push no PR durante a espera da migration entraria sem a conferencia do sha256
    conferido = info.get("head_conferido") or info.get("headRefOid")
    if conferido and ponta != conferido:
        raise EntregaFalhou(f"#{n} andou depois das pre-condicoes ({ponta[:8]}): rode de novo")
    if run(["git", "merge-base", "--is-ancestor", "origin/main", "HEAD"], cwd=wt, check=False).returncode == 0:
        return False
    proc = run(["git", "merge", "--no-ff", "origin/main", "-m", f"Merge da main em {branch}"], cwd=wt, check=False)
    if proc.returncode != 0:
        conflitos = run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wt, check=False).stdout.split()
        run(["git", "merge", "--abort"], cwd=wt, check=False)
        raise MergeConflito(n, conflitos)
    return True


# ------------------------------------------------- entrega por PR (#910)

class EntregaFalhou(Exception):
    """O PR nao entrou na main: push na branch recusado, CI vermelho, head que
    andou, merge recusado."""


def empurrar_branch(wt: Path, branch: str) -> str:
    """Push do HEAD do worktree numa branch que nao e a main. Devolve o sha."""
    proc = run(["git", "push", "-q", "origin", f"HEAD:refs/heads/{branch}"], cwd=wt, check=False)
    if proc.returncode != 0:
        raise EntregaFalhou(f"push na branch {branch} recusado ({(proc.stderr or '').strip()[:160]})")
    return run(["git", "rev-parse", "HEAD"], cwd=wt).stdout.strip()


def abrir_pr(raiz: Path, branch: str, titulo: str, corpo: str) -> int:
    try:
        pr = gh_json(["api", "-X", "POST", "repos/{owner}/{repo}/pulls", "-f", f"title={titulo}",
                      "-f", f"head={branch}", "-f", "base=main", "-f", f"body={corpo}"], cwd=raiz)
    except RuntimeError as e:
        raise EntregaFalhou(f"nao consegui abrir o PR da branch {branch} ({str(e)[:160]})") from e
    return int(pr["number"])


def _resultado(check: dict) -> str:
    return (check.get("conclusion") or check.get("state") or "").upper()


def esperar_checks(raiz: Path, pr: int, sha: str) -> None:
    """Espera o CI do head `sha` do PR ficar verde e o GitHub liberar o merge
    (mergeStateStatus CLEAN). Com o ruleset, check obrigatorio pendente deixa o
    PR em BLOCKED; branch atras da base, em BEHIND. Job que o GitHub cancelou
    por falta de runner (incidente do Actions, issue #953) e repetido, nao e
    vermelho de codigo."""
    inicio = time.time()
    repeticoes = 0
    while True:
        info = gh_json(["pr", "view", str(pr), "--json", "headRefOid,statusCheckRollup,mergeStateStatus"],
                       cwd=raiz)
        estado = (info.get("mergeStateStatus") or "").upper()
        checks = info.get("statusCheckRollup") or []
        if info.get("headRefOid") == sha:
            vermelhos = [c for c in checks if _resultado(c) in VERMELHO]
            runs = ci_sem_runner.runs_sem_runner(vermelhos, lambda job: [
                a.get("message") or "" for a in gh_json(
                    ["api", f"repos/{{owner}}/{{repo}}/check-runs/{job}/annotations"], cwd=raiz)])
            if runs and repeticoes >= ci_sem_runner.REPETICOES_MAX:
                raise EntregaFalhou(f"PR #{pr}: o GitHub Actions ficou sem runner {repeticoes} vezes seguidas "
                                    "(incidente, veja githubstatus.com); nada do codigo falhou")
            if runs:
                if all(run(["gh", "run", "rerun", r, "--failed"], cwd=raiz, check=False).returncode == 0
                       for r in sorted(runs)):
                    repeticoes += 1
                    print(f"CI do PR #{pr} cancelado sem runner do GitHub: rerun {repeticoes} de "
                          f"{ci_sem_runner.REPETICOES_MAX}")
            elif vermelhos:
                nomes = [c.get("name") or c.get("context") or "?" for c in vermelhos]
                raise EntregaFalhou(f"CI vermelho no PR #{pr}: {', '.join(nomes[:4])}")
            if estado in ("BEHIND", "DIRTY"):
                raise EntregaFalhou(f"PR #{pr} em {estado}: a main andou durante o CI")
            if checks and all(_resultado(c) in VERDE for c in checks) and estado in ("CLEAN", "HAS_HOOKS"):
                return
        elif time.time() - inicio > HEAD_ATRASADO_S:
            raise EntregaFalhou(f"PR #{pr} esta em {str(info.get('headRefOid'))[:8]}, nao no {sha[:8]} empurrado")
        if time.time() - inicio > CHECKS_TIMEOUT_S:
            raise EntregaFalhou(f"PR #{pr}: CI nao ficou verde em {CHECKS_TIMEOUT_S // 60} min "
                                f"(mergeStateStatus {estado or '?'}, {len(checks)} checks)")
        time.sleep(CHECKS_POLL_S)


def mergear_pela_api(raiz: Path, pr: int, sha: str, titulo: str) -> str:
    """Squash pela API, conferindo que o head ainda e o `sha` com CI verde.
    Devolve o sha do commit que entrou na main."""
    try:
        resp = gh_json(["api", "-X", "PUT", f"repos/{{owner}}/{{repo}}/pulls/{pr}/merge",
                        "-f", "merge_method=squash", "-f", f"sha={sha}", "-f", f"commit_title={titulo}"], cwd=raiz)
    except RuntimeError as e:
        raise EntregaFalhou(f"o GitHub recusou o merge do PR #{pr} ({str(e)[:200]})") from e
    return resp["sha"]


def entregar(raiz: Path, wt: Path, branch: str, pr: int | None, titulo: str, corpo: str) -> tuple[int, str]:
    """Push da branch, PR (abre se `pr` e None) e espera o CI. Devolve (pr, head)."""
    head = empurrar_branch(wt, branch)
    if pr is None:
        pr = abrir_pr(raiz, branch, titulo, corpo)
    esperar_checks(raiz, pr, head)
    return pr, head


def preparar_pr(raiz: Path, wt: Path, info: dict) -> tuple[str, bool]:
    """Leva um PR do lote ao ponto de merge: a branch dele no worktree, com a
    origin/main por merge se ficou atras, push na branch (em dia, o head nao
    muda e o CI dele ja vale) e CI verde no head. Devolve (head, trouxe a main)."""
    run(["git", "fetch", "-q", "origin", "main"], cwd=wt)  # o squash do PR anterior do lote
    trouxe = entrar_na_branch_do_pr(wt, info)
    _, head = entregar(raiz, wt, info["headRefName"], info["number"], "", "")
    return head, trouxe


# --------------------------------------------------------------------- bump

def classe_do_lote(caminhos) -> str:
    """"app" se algum arquivo esta em hospital-reunioes/, "ferramenta" se nenhum
    esta (issue #965). Lote misto e app."""
    return "app" if any(c.startswith(APP) for c in caminhos) else "ferramenta"


def tipo_de_bump(infos: list[dict]) -> str:
    nivel = "patch"
    for info in infos:
        for c in info.get("commits") or []:
            head = (c.get("messageHeadline") or "").strip()
            body = c.get("messageBody") or ""
            if "BREAKING CHANGE" in body or re.match(r"^\w+(\([^)]*\))?!:", head):
                return "major"
            if re.match(r"^feat(\([^)]*\))?:", head):
                nivel = "minor"
        if re.match(r"^feat(\([^)]*\))?:", info["title"].strip()) and nivel == "patch":
            nivel = "minor"
    return nivel


def proxima_versao(atual: str, tipo: str) -> str:
    major, minor, patch = (int(x) for x in atual.split(".")[:3])
    if tipo == "major":
        return f"{major + 1}.0.0"
    if tipo == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def _semver(v: str) -> tuple[int, int, int]:
    return tuple(int(x) for x in v.split(".")[:3])  # type: ignore[return-value]


def versao_em_producao(wt: Path, ref: str) -> str:
    """Versao de onde a proxima sai (issue #967): o `last_app_version` do
    state.json no `ref`, conferido com a maior tag vX.Y.Z do remoto. A versao
    nao e mais commitada: o package.json do frontend fica congelado. Vale a
    maior das duas: tag a frente do state.json e um rabo que mergeou e
    etiquetou mas nao registrou, e repetir a versao dele confundiria o health."""
    do_state = json.loads(run(["git", "show", f"{ref}:{STATE}"], cwd=wt).stdout).get("last_app_version")
    tags = re.findall(r"refs/tags/v(\d+\.\d+\.\d+)$", run(["git", "ls-remote", "--tags", "origin"], cwd=wt).stdout,
                      re.M)
    maior_tag = max(tags, key=_semver, default=None)
    if not do_state and not maior_tag:
        raise RuntimeError("sem versao de partida: o state.json nao tem last_app_version e nao ha tag vX.Y.Z")
    if do_state and maior_tag and _semver(maior_tag) > _semver(do_state):
        print(f"versao: o state.json diz v{do_state} e a maior tag e v{maior_tag}; sigo da tag")
    return max((v for v in (do_state, maior_tag) if v), key=_semver)


# -------------------------------------------------------------- bookkeeping

def prds_do_lote(raiz: Path, infos: list[dict]) -> list[int]:
    prds = set()
    for info in infos:
        for ref in info.get("closingIssuesReferences") or []:
            try:
                body = gh_json(["issue", "view", str(ref["number"]), "--json", "body"], cwd=raiz).get("body") or ""
            except Exception:
                continue
            m = re.search(r"^## Pai[^\n]*\n(?:.*\n)*?[^\n]*#(\d+)", body, re.M)
            if not m:
                m = re.search(r"^## Pai[^\n]*#(\d+)", body, re.M)
            if m:
                prds.add(int(m.group(1)))
    return sorted(prds)


def humanizar(subject: str) -> str:
    s = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", subject)
    s = re.sub(r"\s*\(#\d+\)\s*$", "", s)
    return (s[:1].upper() + s[1:]) if s else subject


def sem_travessao(s: str) -> str:
    """Travessao e meia-risca viram hifen entre numeros e virgula no resto (ADR 0013)."""
    s = re.sub(r"(\d)\s*[\u2013\u2014]\s*(\d)", r"\1-\2", s)
    return re.sub(r"\s*[\u2013\u2014]\s*", ", ", s)


def rotulo_issues(info: dict) -> str:
    nums = [ref["number"] for ref in info.get("closingIssuesReferences") or []]
    if not nums:
        return "sem issue"
    return ("issue " if len(nums) == 1 else "issues ") + " ".join(f"#{n}" for n in nums)


def escrever_registro(wt: Path, sessao: str, infos: list[dict], versao: str | None,
                      sha_codigo: str, prds: list[int], migs: list[str], servicos: list[str],
                      duracoes: dict[str, int | None], healths: dict[str, dict], resultado: str,
                      com_app_version: list[str], avulso: bool = False) -> None:
    """A verdade do deploy que o GitHub nao tem (ADR 0062, decisao 9): history.json,
    com todos os deploys, e state.json."""
    history = ler_json(wt / HISTORY)
    state = ler_json(wt / STATE)
    when = agora_iso()
    prs_txt = " ".join(f"#{i['number']}" for i in infos)
    como = "Merge pela API do GitHub, um build. Registro num PR so de docs depois do health."
    if avulso:
        # PR avulso (ADR 0061): o registro nomeia PR e issue, e a palavra onda nao aparece.
        pr = infos[0]
        subject = f"PR #{pr['number']}, {rotulo_issues(pr)}: {humanizar(pr['title'])}"
        raw_subject = f"chore(deploy): registro do PR avulso (#{pr['number']})"
        notes = f"PR avulso: PR #{pr['number']}, {rotulo_issues(pr)}. {como}"
    else:
        subject = f"Onda {sessao}: " + "; ".join(humanizar(i["title"]) for i in infos)
        raw_subject = f"chore(deploy): registro da onda {sessao} ({prs_txt})"
        # um "PR #N (issue #M)" por PR: o painel correlaciona cada um (`_correlate`)
        lote = ", ".join(f"PR #{i['number']} ({rotulo_issues(i)})" for i in infos)
        notes = f"onda-enxuta {sessao}: {lote}, mergeados PR a PR. {como}"
    subject = sem_travessao(subject)[:200]
    entrada = {
        "at": when,
        "sha": sha_codigo,
        "app_version": versao,
        "subject": subject,
        "raw_subject": raw_subject,
        "scope": servicos,
        "prds": prds,
        "result": resultado,
        "duration_seconds": int(time.time() - T0),
        "services_touched": servicos,
        "env_changes": [{"service": sid, "action": "update", "keys": ["APP_VERSION"]} for sid in com_app_version],
        "migrations_applied": migs,
        "rollback_target_sha": None,
        "notes": notes,
    }
    deploys = history.setdefault("deploys", [])
    deploys.insert(0, entrada)
    escrever_json(wt / HISTORY, history)

    modo = "pr-avulso" if avulso else "onda-enxuta"
    state["updated_at"] = when
    state["updated_by"] = f"{modo}@fechar_onda"
    if versao:
        state["last_app_version"] = versao
    for svc in state.get("services") or []:
        if svc.get("id") in servicos:
            svc["last_deploy_sha"] = sha_codigo
            svc["last_deploy_at"] = when
            h = healths.get(svc["id"]) or {}
            svc["status"] = "healthy" if h.get("ok") else "warning"
            svc["last_health_check"] = {"at": when, "latency_ms": h.get("latency_ms"),
                                        "http_status": h.get("status"), "body_ok": bool(h.get("ok"))}
            svc["build_duration_seconds"] = duracoes.get(svc["id"])
    state["last_run"] = {"mode": modo, "sha": sha_codigo, "result": resultado,
                         "duration_seconds": int(time.time() - T0)}
    state.pop("next_actions", None)
    escrever_json(wt / STATE, state)


def commitar(wt: Path, msg: str, paths: list[str]) -> str:
    existentes = [p for p in paths if (wt / p).exists()]
    if existentes:
        run(["git", "add", "--", *existentes], cwd=wt)
    if not run(["git", "status", "--porcelain"], cwd=wt).stdout.strip():
        return run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()
    run(["git", "commit", "-q", "-m", msg, "-m", COAUTHOR], cwd=wt)
    return run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()


# ------------------------------------------------------------------ coolify

def coolify_json(args: list[str], timeout: int = 120):
    proc = run(["coolify", *args, "--format", "json"], check=False, timeout=timeout)
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def setar_app_version(backend_uuid: str, versao: str) -> None:
    proc = run(["coolify", "app", "env", "update", backend_uuid, "APP_VERSION", "--value", versao], check=False)
    if proc.returncode != 0:
        run(["coolify", "app", "env", "create", backend_uuid, "--key", "APP_VERSION", "--value", versao])


def apps_do_coolify(servicos_cfg: dict) -> list[str]:
    return [sid for sid, s in servicos_cfg.items() if s.get("type") != "supabase" and s.get("uuid")]


def setar_app_version_nos_apps(servicos_cfg: dict, versao: str) -> list[str]:
    """APP_VERSION em todo app do Coolify (issue #967): o backend a le no
    runtime e devolve no /api/health; o frontend a recebe no build (ARG do
    Dockerfile) e a grava no rodape. Devolve os servicos gravados."""
    apps = apps_do_coolify(servicos_cfg)
    for sid in apps:
        setar_app_version(servicos_cfg[sid]["uuid"], versao)
    return apps


def criar_tag(raiz: Path, versao: str, sha: str) -> None:
    """Tag vX.Y.Z no squash que foi para a main, pela API (o commit so existe
    no GitHub). E a conferencia da proxima versao_em_producao."""
    gh_json(["api", "-X", "POST", "repos/{owner}/{repo}/git/refs", "-f", f"ref=refs/tags/v{versao}",
             "-f", f"sha={sha}"], cwd=raiz)


def _lista(d):
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("data", "deployments", "items"):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def _campo(d: dict, *nomes, default=None):
    for n in nomes:
        if n in d and d[n] not in (None, ""):
            return d[n]
    return default


def _parse_ts(v) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def esperar_build(service: dict, desde: float, sha_push: str, ignorar: tuple[str, ...] = ()) -> tuple[str, int | None]:
    """Espera o deploy disparado pelo webhook. Devolve (status, duracao_s).
    `ignorar`: os squashes intermediarios da onda, cujo deploy o rabo cancelou e
    que a janela de horario pegaria."""
    uuid = service["uuid"]
    dep = None
    limite = time.time() + BUILD_WAIT_WEBHOOK_S
    forcado = False
    while dep is None:
        for d in _lista(coolify_json(["app", "deployments", "list", uuid])):
            criado = _parse_ts(_campo(d, "created_at", "createdAt"))
            commit = str(_campo(d, "commit", "git_commit_sha", default=""))
            if commit and any(commit.startswith(s) or s.startswith(commit) for s in ignorar):
                continue  # squash intermediario da onda: o deploy dele foi cancelado
            if (criado and criado >= desde - 60) or (sha_push and commit.startswith(sha_push)):
                dep = d
                break
        if dep is None:
            if time.time() > limite and not forcado:
                run(["coolify", "deploy", "uuid", uuid], check=False)
                forcado = True
                limite = time.time() + BUILD_WAIT_WEBHOOK_S
            elif time.time() > limite:
                return "sem-deploy", None
            time.sleep(BUILD_POLL_S)
    return acompanhar_deploy(dep)


def acompanhar_deploy(dep: dict) -> tuple[str, int | None]:
    """Acompanha um deploy do Coolify ate terminar. Devolve (status, duracao_s)."""
    dep_id = _campo(dep, "deployment_uuid", "uuid", "id")
    fim = time.time() + BUILD_TIMEOUT_S
    status = str(_campo(dep, "status", default="")).lower()
    while status not in ("finished", "failed", "cancelled") and time.time() < fim:
        time.sleep(BUILD_POLL_S)
        atual = coolify_json(["deploy", "get", str(dep_id)]) or {}
        if isinstance(atual, dict) and "data" in atual and isinstance(atual["data"], dict):
            atual = atual["data"]
        if atual:
            dep = atual
            status = str(_campo(dep, "status", default=status)).lower()
    ini = _parse_ts(_campo(dep, "started_at", "created_at"))
    fim_ts = _parse_ts(_campo(dep, "finished_at", "updated_at"))
    duracao = int(fim_ts - ini) if ini and fim_ts else None
    return status or "desconhecido", duracao


def cancelar_build_do_registro(servicos_cfg: dict, sha: str) -> list[str]:
    """O merge do registro e o de um lote de ferramenta sao push na main, e o
    webhook do Coolify rebuilda os apps mesmo com o commit fora do app (issues
    #851 e #965). Cancela o deploy desse
    commit, e so dele, se aparecer na janela; com filtro de caminho no Coolify,
    nao aparece nenhum. Devolve os servicos cancelados."""
    apps = {sid: s["uuid"] for sid, s in servicos_cfg.items() if s.get("type") != "supabase" and s.get("uuid")}
    cancelados = []
    limite = time.time() + REGISTRO_JANELA_S
    while apps:
        for sid, uuid in list(apps.items()):
            for d in _lista(coolify_json(["app", "deployments", "list", uuid])):
                commit = str(_campo(d, "commit", "git_commit_sha", default=""))
                if not commit or not (commit.startswith(sha) or sha.startswith(commit)):
                    continue
                if str(_campo(d, "status", default="")).lower() in ("queued", "in_progress"):
                    run(["coolify", "deploy", "cancel", str(_campo(d, "deployment_uuid", "uuid", "id")), "--force"],
                        check=False)
                    cancelados.append(sid)
                del apps[sid]
                break
        if not apps or time.time() >= limite:
            break
        time.sleep(BUILD_POLL_S)
    return cancelados


# ----------------------------------------------------------------- rollback

def imagem_no_ar(uuid: str) -> str | None:
    """A imagem que o app roda agora (`current` do Coolify), lida antes do merge:
    e para ela que o rollback volta (issue #968). A mais nova da lista nao serve:
    a imagem ruim que um rollback anterior tirou do ar segue la, mais nova."""
    dado = coolify_json(["app", "rollback", "images", uuid])
    atual = dado.get("current") if isinstance(dado, dict) else None
    return str(atual) if atual else None


def ids_de_deploy(uuid: str) -> set[str]:
    return {str(_campo(d, "deployment_uuid", "uuid", "id"))
            for d in _lista(coolify_json(["app", "deployments", "list", uuid]))}


def esperar_rollback(service: dict, antes: set[str]) -> str:
    """Espera o deploy que o `rollback run` criou (o que nao estava em `antes`)
    terminar. Nunca forca build: um `deploy uuid` aqui rebuildaria a main, com o
    defeito dentro."""
    limite = time.time() + BUILD_WAIT_WEBHOOK_S
    while True:
        novos = [d for d in _lista(coolify_json(["app", "deployments", "list", service["uuid"]]))
                 if str(_campo(d, "deployment_uuid", "uuid", "id")) not in antes]
        if novos:
            return acompanhar_deploy(novos[0])[0]
        if time.time() > limite:
            return "sem-deploy"
        time.sleep(BUILD_POLL_S)


def reverter(servicos_cfg: dict, servicos: list[str], alvos: dict[str, str | None], versao_antiga: str | None,
             com_app_version: list[str]) -> tuple[bool, str]:
    """Rollback automatico (issue #968): cada app do lote volta a imagem que
    estava no ar antes do merge (`alvos`, de `imagem_no_ar`), o APP_VERSION
    antigo volta aos apps em que o rabo o trocou e o health e conferido de novo.
    Devolve (deu certo, o que aconteceu)."""
    try:
        alvos = {sid: alvos.get(sid) for sid in servicos}
        sem = [sid for sid, alvo in alvos.items() if not alvo]
        if sem:
            return False, "sem imagem anterior no Coolify (lida antes do merge) para " + ", ".join(sem)
        # antes de subir a imagem: o backend le o APP_VERSION no start do container
        for sid in com_app_version:
            setar_app_version(servicos_cfg[sid]["uuid"], versao_antiga)
        for sid, alvo in alvos.items():
            uuid = servicos_cfg[sid]["uuid"]
            antes = ids_de_deploy(uuid)
            if run(["coolify", "app", "rollback", "run", uuid, "--commit", alvo], check=False).returncode != 0:
                return False, f"o Coolify recusou o rollback do {sid} para {alvo[:8]}"
            status = esperar_rollback(servicos_cfg[sid], antes)
            if status != "finished":
                return False, f"o deploy do rollback do {sid} terminou {status}"
        healths = {sid: checar_health(servicos_cfg[sid], versao_antiga if sid == "backend" else None)
                   for sid in servicos}
        ruins = [f"{sid}: {linha_de_health(h)}" for sid, h in healths.items() if not h["ok"]]
        if ruins:
            return False, "health ainda ruim depois do rollback (" + "; ".join(ruins) + ")"
    except Exception as e:  # noqa: BLE001
        return False, str(e)[:300]
    return True, ", ".join(f"{sid} na imagem {alvo[:8]}" for sid, alvo in alvos.items())


# ------------------------------------------------------------------- health

def linha_de_health(h: dict) -> str:
    return " ".join(p for p in (f"http {h.get('status')}", h.get("nota"), h.get("corpo")) if p)


def url_do_health(service: dict) -> str:
    hc = (service.get("deploy") or {}).get("health_check") or {}
    return hc.get("url") or ((service.get("deploy") or {}).get("fqdn") or "") + (hc.get("path") or "/")


def checar_health(service: dict, versao_esperada: str | None) -> dict:
    hc = (service.get("deploy") or {}).get("health_check") or {}
    url = url_do_health(service)
    if not url:
        return {"ok": True, "status": None, "latency_ms": None, "nota": "sem health"}
    resultado = {"ok": False, "status": None, "latency_ms": None}
    for tentativa in range(6):
        t = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "fechar_onda"}), timeout=15) as r:
                body = r.read().decode("utf-8", "replace")
                resultado["status"] = r.status
        except urllib.error.HTTPError as e:
            resultado["status"] = e.code
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
        except Exception:
            body = ""
        resultado["latency_ms"] = int((time.time() - t) * 1000)
        ok = resultado["status"] == hc.get("expected_status", 200)
        regex = hc.get("expected_body_regex")
        if ok and regex and not re.search(regex, body.strip()):
            ok = False
        if ok and versao_esperada and regex:
            try:
                versao = json.loads(body).get("version")
            except Exception:
                versao = None
            resultado["versao"] = versao
            if versao != versao_esperada:
                ok = False
                resultado["nota"] = f"esperava v{versao_esperada}, /api/health devolveu v{versao}"
        resultado["ok"] = ok
        if ok:
            return resultado
        # o que o health respondeu vai na linha do rabo e no comentario da issue reaberta (issue #968)
        resultado["corpo"] = " ".join(body.split())[:200]
        time.sleep(10)
    return resultado


# ------------------------------------------------------------------ limpeza

def limpar_worktrees_de_agente(raiz: Path, entregues: dict[str, str] | None = None) -> int:
    """Remove worktrees de agente cuja branch ja esta na main. `entregues` e
    branch -> head que entrou: com squash a branch nao vira ancestral da main e
    o `--merged` nao a acha, entao vale o worktree parado no head entregue."""
    entregues = entregues or {}
    porcelain = run(["git", "worktree", "list", "--porcelain"], cwd=raiz, check=False).stdout
    merged = set(b.strip().lstrip("* ").strip() for b in
                 run(["git", "branch", "--merged", "origin/main"], cwd=raiz, check=False).stdout.splitlines())
    removidos = 0
    atual_path, atual_branch, atual_head = None, None, None
    entradas = []
    for ln in porcelain.splitlines() + [""]:
        if ln.startswith("worktree "):
            atual_path = ln[9:].strip()
        elif ln.startswith("HEAD "):
            atual_head = ln[5:].strip()
        elif ln.startswith("branch "):
            atual_branch = ln[7:].strip().replace("refs/heads/", "")
        elif ln == "":
            if atual_path:
                entradas.append((atual_path, atual_branch, atual_head))
            atual_path, atual_branch, atual_head = None, None, None
    # o PR avulso roda do worktree do autor, na branch do PR, que o push acabou de
    # mergear: remover o proprio checkout apaga trabalho sujo e o cwd do script
    cwd = Path.cwd().resolve()
    proprios = {raiz.resolve()}
    for path, branch, head in entradas:
        if ".claude/worktrees/" not in path.replace("\\", "/") or not branch:
            continue
        p = Path(path).resolve()
        if p in proprios or cwd == p or p in cwd.parents:
            continue
        entregue = bool(head) and entregues.get(branch) == head
        if (branch in merged or entregue) and branch != "main":
            run(["git", "worktree", "remove", "--force", path], cwd=raiz, check=False)
            run(["git", "branch", "-D" if entregue else "-d", branch], cwd=raiz, check=False)
            removidos += 1
    run(["git", "worktree", "prune"], cwd=raiz, check=False)
    return removidos


# --------------------------------------------------------------------- main

def resolver_sessao(prs: list[int], sessao: str | None) -> tuple[str, bool]:
    """Devolve (sessao, avulso). Sem `--sessao`, um PR so e um PR avulso (ADR 0061)
    e a chave do semaforo e do worktree sai do numero dele."""
    if sessao:
        return sessao, False
    if len(prs) == 1:
        return f"pr-{prs[0]}", True
    falhar("--sessao e obrigatorio com mais de um PR (onda); um PR so dispensa a opcao.", EXIT_PRECOND)
    raise AssertionError("inalcancavel")


def main() -> int:
    ap = argparse.ArgumentParser(description="Fecha um PR avulso ou uma onda: merge pela API PR a PR, um build.")
    ap.add_argument("--prs", nargs="+", type=int, required=True, help="PRs na ordem de merge")
    ap.add_argument("--sessao", help="nome da sessao (chave do semaforo); sem ela, um PR so e um PR avulso (pr-<N>)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--raiz", help="raiz do repositorio (default: git rev-parse)")
    args = ap.parse_args()

    args.sessao, avulso = resolver_sessao(args.prs, args.sessao)
    if not re.fullmatch(r"[A-Za-z0-9._-]+", args.sessao):
        falhar("--sessao so aceita letras, numeros, ponto, hifen e underscore.", EXIT_PRECOND)
    raiz = Path(args.raiz).resolve() if args.raiz else Path(
        run(["git", "rev-parse", "--show-toplevel"]).stdout.strip()).resolve()
    projeto = ler_json(raiz / SPEC / "deploy" / "project.json")
    servicos_cfg = {s["id"]: s for s in projeto["services"]}

    infos, novas = checar_pre_condicoes(raiz, args.prs, args.dry_run)
    de_fork = " ".join(f"#{i['number']}" for i in infos if i.get("isCrossRepository"))
    if de_fork:
        falhar(f"pre-condicao: {de_fork} vem de um fork; a main entra na branch do PR, "
               "que precisa estar neste repositorio.", EXIT_PRECOND)
    prs_txt = " ".join(f"#{i['number']}" for i in infos)
    print(f"pre-condicoes ok: {prs_txt}, migrations sem numero repetido contra origin/main e com o sha256 do corpo"
          + (" (dry-run)" if args.dry_run else ""), flush=True)
    numeros = [n for n in (checar_migration_repetida._numero(Path(c).name) for _, c in novas) if n is not None]
    # antes do semaforo: a espera pode levar horas (issue #969)
    if numeros and not args.dry_run and not esperar_migrations_do_lote(
            raiz, servicos_cfg["backend"], novas, max(numeros), args.sessao, prs_txt):
        return EXIT_MIGRACAO

    wt = None
    wt_reg = None
    semaforo_pego = False
    mergeados: list[tuple[dict, str, float]] = []  # (PR, squash na main, hora do merge)
    try:
        if not args.dry_run:
            pegar_semaforo(raiz, args.sessao, args.prs, avulso)
            semaforo_pego = True
        wt = criar_worktree(raiz, args.sessao)
        base = run(["git", "rev-parse", "--short=8", "HEAD"], cwd=wt).stdout.strip()

        # classe, versao e servicos saem do lote inteiro, antes do primeiro merge
        versao_antiga = versao_em_producao(wt, base)
        # --no-renames, como o detector do CI: o `files` do gh mostra um rename so
        # pelo caminho novo, e tirar codigo do app passaria por ferramenta
        arquivos = set()
        for i in infos:
            arquivos.update(run(["git", "diff", "--no-renames", "--name-only", f"{base}...{i['head_conferido']}"],
                                cwd=wt).stdout.split())
            arquivos.update(f["path"] for f in i.get("files") or [])
        ferramenta = classe_do_lote(arquivos) == "ferramenta"
        tipo = None if ferramenta else tipo_de_bump(infos)
        versao_nova = proxima_versao(versao_antiga, tipo) if tipo else None
        # supabase nao tem build: migration se aplica a mao no Studio (o deploy nao aplica SQL)
        servicos = [sid for sid, s in servicos_cfg.items()
                    if s.get("type") != "supabase" and any(re.match(tp.replace("**", ".*").replace("*", "[^/]*"), a)
                           for a in arquivos for tp in (s.get("diff_routing") or {}).get("trigger_paths") or [])]
        if not ferramenta and not servicos:
            servicos = [sid for sid, s in servicos_cfg.items() if s.get("type") in ("nextjs", "fastapi", "node", "python", "generic")]

        if args.dry_run:
            prds = prds_do_lote(raiz, infos)
            migs = [Path(c).name for _, c in novas]
            classe = (f"ferramenta: só merge, versao segue v{versao_antiga}" if ferramenta
                      else f"app: bump {tipo} v{versao_antiga} -> v{versao_nova}")
            print("plano: " + ", ".join(f"PR #{i['number']} ({rotulo_issues(i)})" for i in infos)
                  + f"; {classe}; chave {args.sessao}")
            faria = ("faria: " + (f"esperar a {max(numeros)} no /api/health (teto {MIGRACAO_TIMEOUT_S // 3600} h), "
                                  if numeros else "")
                     + ("" if ferramenta else f"APP_VERSION v{versao_nova} no "
                        + " e no ".join(apps_do_coolify(servicos_cfg)) + ", ")
                     + "em ordem: " + ", ".join(f"merge pela API do PR #{i['number']}" for i in infos)
                     + " (squash, com a main trazida por merge no PR que estiver atras e o CI verde no head), ")
            if ferramenta:
                print(faria + "cancela o build que o webhook disparar em cada merge, limpeza; "
                      "sem bump, APP_VERSION, build, health nem registro.")
            else:
                print(faria + ("cancela o build dos squashes intermediarios, " if len(infos) > 1 else "")
                      + f"tag v{versao_nova} no squash do ultimo, um build, health, registro em PR so de docs "
                      f"(prds {prds or '[]'}, migrations {migs or '[]'}, services {servicos or '[]'}), limpeza.")
            remover_worktree(raiz, wt)
            wt = None
            print("dry-run terminou sem tocar em nada.")
            return 0

        versao = versao_nova or versao_antiga
        if versao_nova:
            print(f"versao: v{versao_antiga} -> v{versao_nova} ({tipo}), sem commit: vai no APP_VERSION e na tag")
        else:
            print(f"versao: segue v{versao_antiga} (ferramenta)")

        # PR a PR, na ordem (ADR 0064, decisao 3). PR que nao mergeia fica de fora
        # e o lote segue sem ele; os ja mergeados ficam.
        no_ar: dict[str, str | None] = {}
        com_app_version: list[str] = []
        antes_do_primeiro = True
        de_fora: list[int] = []
        for info in infos:
            n = info["number"]
            try:
                head, trouxe_main = preparar_pr(raiz, wt, info)
                if antes_do_primeiro:
                    # a imagem no ar antes do primeiro merge e o alvo de um rollback (issue #968)
                    no_ar = {sid: imagem_no_ar(servicos_cfg[sid]["uuid"]) for sid in servicos}
                    com_app_version = setar_app_version_nos_apps(servicos_cfg, versao_nova) if versao_nova else []
                    antes_do_primeiro = False
                titulo = info["title"].strip()
                titulo = titulo if f"(#{n})" in titulo else f"{titulo} (#{n})"
                t = time.time()
                sha = mergear_pela_api(raiz, n, head, titulo)
            except MergeConflito as e:
                de_fora.append(n)
                print(f"de fora: conflito no merge de #{e.pr} em: {', '.join(e.arquivos) or '?'}. "
                      "Mande um corretor rebasear o PR sobre origin/main e rode o rabo de novo com ele.")
                continue
            except EntregaFalhou as e:
                de_fora.append(n)
                print(f"de fora: PR #{n}, {e}.")
                continue
            mergeados.append((info, sha, t))
            print(f"merge: PR #{n} na main pela API, squash {sha[:8]}"
                  + (f", com a main trazida por merge e o CI verde no head {head[:8]}" if trouxe_main else ""))
        remover_worktree(raiz, wt)
        wt = None

        fora = " ".join(f"#{n}" for n in de_fora)
        if not mergeados:
            semaforo(raiz, "soltar", args.sessao)
            semaforo_pego = False
            print(f"nada entrou na main: {fora} de fora, semaforo solto. Rode de novo depois de corrigir.")
            return EXIT_MERGE
        lote = [i for i, _, _ in mergeados]
        entraram = " ".join(f"#{i['number']}" for i in lote)
        sha_main, t_merge = mergeados[-1][1], mergeados[-1][2]
        intermediarios = tuple(s for _, s, _ in mergeados[:-1])
        squashes = " ".join(s[:8] for _, s, _ in mergeados)
        if avulso:
            fechou = f"PR {entraram} fechado"
        else:
            fechou = f"onda {args.sessao} fechada" + (f" sem {fora} (de fora, saida 2)" if de_fora else "")
        if versao_nova:
            try:
                criar_tag(raiz, versao_nova, sha_main)
                print(f"tag: v{versao_nova} no squash {sha_main[:8]} do PR #{lote[-1]['number']}")
            except RuntimeError as e:
                # a tag e conferencia, nao deploy: falhar aqui nao para o build
                print(f"tag: a tag v{versao_nova} falhou ({str(e)[:120]}), crie depois com `gh api -X POST "
                      f"repos/{{owner}}/{{repo}}/git/refs -f ref=refs/tags/v{versao_nova} -f sha={sha_main}`")

        if ferramenta:
            # producao nao muda: sem build, health nem registro (issue #965). Falha
            # daqui em diante e codigo 5, nunca o 3: nada a reverter no Coolify
            try:
                cancelados = [sid for _, s, _ in mergeados for sid in cancelar_build_do_registro(servicos_cfg, s)]
                n_wt = limpar_worktrees_de_agente(raiz, {i["headRefName"]: i.get("headRefOid") for i in lote})
            except Exception as e:  # noqa: BLE001
                semaforo(raiz, "soltar", args.sessao)
                print(f"pos-merge: {e}; merge feito, producao intacta e semaforo solto; confira no Coolify "
                      f"se o webhook rodou build de {squashes}.")
                return EXIT_REGISTRO
            semaforo(raiz, "soltar", args.sessao)
            semaforo_pego = False
            print(f"{fechou} (ferramenta: só merge): versao segue v{versao_antiga} · PRs {entraram} · "
                  f"squash {squashes} · sem build, health nem registro"
                  + (f" · build do webhook cancelado ({', '.join(cancelados)})" if cancelados else "")
                  + f" · {n_wt} worktrees limpos · {dur(time.time() - T0)}")
            return EXIT_MERGE if de_fora else 0

        # um build: o webhook dispara um deploy por merge, e so o do ultimo roda (issue #851)
        cancelados = [sid for s in intermediarios for sid in cancelar_build_do_registro(servicos_cfg, s)]
        duracoes: dict[str, int | None] = {}
        falhas = []
        for sid in servicos:
            status, d = esperar_build(servicos_cfg[sid], t_merge, sha_main, intermediarios)
            duracoes[sid] = d
            if status != "finished":
                falhas.append(f"{sid}: {status}")
        if falhas:
            print("build: " + "; ".join(falhas) + f". Semaforo preso na chave {args.sessao}: rode `/deploy rollback` com ela.")
            return EXIT_BUILD
        print("build: " + ", ".join(f"{sid} {dur(duracoes.get(sid))}" for sid in servicos)
              + (f", build dos squashes intermediarios cancelado ({', '.join(cancelados)})" if cancelados else ""))

        healths = {}
        for sid in (servicos or [s for s in servicos_cfg if s != "supabase"]):
            healths[sid] = checar_health(servicos_cfg[sid], versao_nova if sid == "backend" else None)
        ruins = [f"{sid}: {linha_de_health(h)}" for sid, h in healths.items() if not h["ok"]]
        if ruins:
            print("health: " + "; ".join(ruins))
            voltou, como = reverter(servicos_cfg, servicos, no_ar, versao_antiga if versao_nova else None,
                                    com_app_version)
            if not voltou:
                print(f"rollback: falhou, {como}. Semaforo preso na chave {args.sessao}: rode `/deploy rollback` com ela.")
                return EXIT_HEALTH
            semaforo(raiz, "soltar", args.sessao)
            semaforo_pego = False
            print(f"rollback: {como}, APP_VERSION v{versao_antiga}, health ok e semaforo solto. "
                  f"Reverter na main: {squashes}; reabrir: "
                  + ", ".join(f"PR #{i['number']} ({rotulo_issues(i)})" for i in lote) + "."
                  + (f" De fora: {fora}." if de_fora else ""))
            return EXIT_ROLLBACK
        vm = " (version match)" if versao_nova else ""
        print(f"health: ok{vm}")

        # registro: so depois do health, num PR so de docs (o CI pula os jobs pesados).
        # Daqui em diante producao esta certa: falha aqui e codigo 5, nunca o 3.
        pr_reg = None
        try:
            run(["git", "fetch", "-q", "origin", "main"], cwd=raiz)
            wt_reg = criar_worktree(raiz, f"{args.sessao}-registro")
            heads = {i.get("head_conferido") for i in lote}
            migs = [Path(c).name for h, c in novas if h in heads]
            escrever_registro(wt_reg, args.sessao, lote, versao_nova, sha_main, prds_do_lote(raiz, lote), migs,
                              servicos, duracoes, healths, "healthy", com_app_version, avulso)
            do_lote = f"do PR {entraram}" if avulso else f"da onda {args.sessao}"
            titulo_reg = f"chore(deploy): registro {do_lote} (v{versao})"
            commitar(wt_reg, titulo_reg, [HISTORY, STATE])
            pr_reg, head_reg = entregar(raiz, wt_reg, f"registro/{args.sessao}-{sha_main[:8]}", None, titulo_reg,
                                        "<!-- automacao -->\nRegistro do deploy de producao (history.json e "
                                        "state.json), aberto e mergeado pelo `fechar_onda.py` depois do health "
                                        "(ADR 0061). Snapshot e draft do Manual sao da Action do push da main "
                                        "(ADR 0062). So docs.\n")
            sha_reg = mergear_pela_api(raiz, pr_reg, head_reg, f"{titulo_reg} (#{pr_reg})")
        except Exception as e:  # noqa: BLE001
            if wt_reg:
                remover_worktree(raiz, wt_reg)
            semaforo(raiz, "soltar", args.sessao)
            falta = (f"mergeie o PR #{pr_reg} quando o CI dele ficar verde" if pr_reg
                     else f"o registro nao virou PR; registre a mao o merge {sha_main[:8]} (v{versao})")
            print(f"registro: {e}. Producao ok e semaforo solto; {falta}.")
            return EXIT_REGISTRO
        cancelados = cancelar_build_do_registro(servicos_cfg, sha_reg)
        print(f"registro: PR #{pr_reg} so de docs na main ({sha_reg[:8]})"
              + (f", build do registro cancelado ({', '.join(cancelados)})" if cancelados else ""))

        remover_worktree(raiz, wt_reg)
        wt_reg = None
        n_wt = limpar_worktrees_de_agente(raiz, {i["headRefName"]: i.get("headRefOid") for i in lote})
        semaforo(raiz, "soltar", args.sessao)
        semaforo_pego = False
        builds = ", ".join(f"{sid} {dur(duracoes.get(sid))}" for sid in servicos) or "sem build"
        print(f"{fechou}: v{versao_antiga} -> v{versao} · PRs {entraram} · squash {squashes} · "
              f"build {builds} · health ok{vm} · {n_wt} worktrees limpos · {dur(time.time() - T0)}")
        return EXIT_MERGE if de_fora else 0
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001
        print(f"erro: {e}")
        for w in (wt, wt_reg):
            if w:
                remover_worktree(raiz, w)
        if mergeados:
            print(f"o merge ja aconteceu. Semaforo preso na chave {args.sessao}: confira o Coolify e o health, "
                  f"depois `semaforo.sh soltar {args.sessao}` ou `/deploy rollback`.")
            return EXIT_BUILD
        if semaforo_pego:
            semaforo(raiz, "soltar", args.sessao)
        return EXIT_MERGE


if __name__ == "__main__":
    sys.exit(main())
