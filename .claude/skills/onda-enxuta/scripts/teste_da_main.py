"""teste_da_main.py: o passo depois do merge da subida (issue #327). A main que quebra e desfeita sozinha.

Quem chama e o `fechar_onda.py`, no fim do lote sem deploy de uma onda, com o `teste_da_main` do
`.claude/fluxo.json` (o comando de teste do Projeto, rodado na raiz do worktree; saida 0 e verde) e os
squashes que o lote pos na main, na ordem.

  1. Testa a ponta da origin/main num worktree descartavel. Verde: termina sem abrir PR.
  2. Vermelha: testa a main de antes do lote (o pai do primeiro squash, o ultimo ponto verde) e depois
     cada squash do lote, na ordem. O primeiro vermelho e o culpado. Main ja vermelha antes do lote, ou
     nenhum squash vermelho (quebrou por um merge de fora do lote): a Onda quebra, nada e desfeito.
     Vermelho so conta repetido em RODADAS_DO_VERMELHO rodadas no mesmo commit; o commit que falha e
     depois passa tem um teste instavel, e a Onda quebra sem desfazer nada (um PR inocente nao e culpado).
  3. O revert do culpado sobre a ponta da main e testado aqui; verde, vira o PR `revert/<chave>-pr<N>`,
     que espera o CI e entra pela API, como o revert do rollback.
  4. Cada issue que o PR revertido fechava volta para `ready-for-agent`, com o fim da falha num
     comentario, e o Estado da Onda ganha o evento `revert` com o nome da Fatia (linha `push:`).
  5. Revert com conflito, ainda vermelho, com o CI vermelho ou recusado: nada e mergeado, e o Estado da
     Onda ganha o evento `erro` (a Onda quebrou, linha `push:`).

Toda linha `push:` que o `estado_onda.py` imprime sai aqui, para a sessao mandar ao celular.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

VERDE = "verde"
REVERTIDA = "revertida"
QUEBRADA = "quebrada"
VERMELHO = "vermelho"
INSTAVEL = "instavel"
RODADAS_DO_VERMELHO = 3  # um vermelho so conta se repete: o teste que falha 1 em 5 nao acha culpado
ESTADO = Path(__file__).resolve().parent / "estado_onda.py"
FIM_DA_SAIDA = 60  # linhas da falha que vao no PR do revert e na issue reaberta, como o `tail -60` da Onda
TETO_S = 30 * 60  # o teste que nao termina conta como vermelho
CHAVE_DA_ONDA = re.compile(r"^(.+)-onda(\d+)$")  # a chave da subida da Onda: `<sessao>-onda<N>`


@dataclass
class Merge:
    """Um PR do lote que entrou na main: o squash dele e as issues que ele fecha."""
    pr: int
    sha: str
    issues: list[int] = field(default_factory=list)
    nome: str = ""  # o nome da Fatia, para o Aviso


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} -> {proc.returncode}: {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc


def testar(wt: Path, comando: str, ref: str) -> tuple[bool, str]:
    """Roda o teste do Projeto no `ref`. Devolve (verde, o fim da saida)."""
    git(wt, "checkout", "-q", "-f", "--detach", ref)
    try:
        proc = subprocess.run(comando, shell=True, cwd=str(wt), capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=TETO_S)
    except subprocess.TimeoutExpired:
        return False, f"o teste passou de {TETO_S // 60} min e foi cortado"
    return proc.returncode == 0, "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-FIM_DA_SAIDA:])


def criar_worktree(raiz: Path, wt: Path) -> None:
    if wt.exists():
        git(raiz, "worktree", "remove", "--force", str(wt), check=False)
        shutil.rmtree(wt, ignore_errors=True)
    git(raiz, "worktree", "prune", check=False)
    git(raiz, "worktree", "add", "-q", "--detach", str(wt), "origin/main")


def remover_worktree(raiz: Path, wt: Path) -> None:
    git(raiz, "worktree", "remove", "--force", str(wt), check=False)
    shutil.rmtree(wt, ignore_errors=True)
    git(raiz, "worktree", "prune", check=False)


class Quebrou(Exception):
    """O revert nao deixa a main verde: nada entra."""


def veredito(wt: Path, comando: str, ref: str) -> tuple[str, str]:
    """VERDE, VERMELHO ou INSTAVEL no `ref`, e a falha. Um verde basta (quebra de verdade nao passa); o
    vermelho roda de novo ate RODADAS_DO_VERMELHO vezes, e um verde no meio faz o commit INSTAVEL."""
    falha = ""
    for rodada in range(RODADAS_DO_VERMELHO):
        verde, saida = testar(wt, comando, ref)
        if verde:
            return (VERDE if rodada == 0 else INSTAVEL), falha
        falha = saida
    return VERMELHO, falha


def primeiro_vermelho(wt: Path, comando: str, merges: list[Merge]) -> tuple[Merge | None, str, str]:
    """Merge a merge, na ordem do lote: o primeiro squash que nao fica verde, o veredito dele (VERMELHO
    ou INSTAVEL) e a falha."""
    for m in merges:
        estado, falha = veredito(wt, comando, m.sha)
        if estado != VERDE:
            return m, estado, falha
    return None, VERDE, ""


def reverter(raiz: Path, wt: Path, chave: str, comando: str, culpado: Merge, falha: str, github) -> tuple[int, str]:
    """O revert do `culpado` sobre a ponta da main, testado aqui antes do PR; o PR espera o CI dele e
    mergeia. Devolve (PR do revert, squash dele na main)."""
    git(raiz, "fetch", "-q", "origin", "main")
    git(wt, "checkout", "-q", "-f", "--detach", "origin/main")
    if git(wt, "revert", "--no-edit", culpado.sha, check=False).returncode != 0:
        git(wt, "revert", "--abort", check=False)
        raise Quebrou(f"o revert do squash {culpado.sha[:8]} deu conflito com a main")
    verde, saida = testar(wt, comando, "HEAD")
    if not verde:
        raise Quebrou("o teste segue vermelho com o revert: " + (saida.splitlines() or ["sem saída"])[-1][:200])
    titulo = f"revert: desfaz o PR #{culpado.pr}, que quebrou o teste da main"
    corpo = (f"<!-- automacao -->\nRevert do squash {culpado.sha[:8]} do PR #{culpado.pr}, aberto pelo "
             f"`fechar_onda.py` depois do merge da chave {chave}: o teste da main (`{comando}`) ficou vermelho "
             f"nesse merge e verde com o revert (issue #327).\n\nFalha:\n```\n{falha}\n```\n")
    pr, head = github.entregar(wt, f"revert/{chave}-pr{culpado.pr}", titulo, corpo)
    return pr, github.mergear(pr, head, f"{titulo} (#{pr})")


def reabrir(chave: str, comando: str, culpado: Merge, falha: str, pr_rev: int, github) -> None:
    """Cada issue que o PR revertido fechava volta para a Fila, com a falha num comentario. O revert ja
    entrou: falha aqui so avisa."""
    corpo = (f"<!-- automacao -->\nRevert depois do merge (chave {chave}): o teste da main (`{comando}`) ficou "
             f"vermelho no squash {culpado.sha[:8]} do PR #{culpado.pr}, e o PR #{pr_rev} desfez esse merge. "
             f"A issue volta para `ready-for-agent`.\n\nFalha:\n```\n{falha}\n```\n")
    for issue in culpado.issues:
        try:
            github.reabrir(issue, corpo)
            print(f"reaberta: issue #{issue}, de volta à Fila com a falha")
        except Exception as e:  # noqa: BLE001
            print(f"aviso: a issue #{issue} não foi reaberta ({str(e)[:200]})")


def registrar(raiz: Path, chave: str, tipo: str, texto: str, pr: int | None) -> None:
    """O evento no Estado da Onda da chave. A linha `push:` que ele imprime sai aqui, para a sessao mandar
    ao celular. Chave que nao e de Onda, ou Estado que nao grava, so avisa: a main ja foi tratada."""
    achado = CHAVE_DA_ONDA.match(chave)
    if not achado:
        return
    cmd = [sys.executable, str(ESTADO), "evento", "--sessao", achado[1], "--onda", achado[2], "--tipo", tipo,
           "--texto", texto, *(["--pr", str(pr)] if pr else [])]
    try:
        r = subprocess.run(cmd, cwd=str(raiz), capture_output=True, text=True, encoding="utf-8", timeout=30)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"aviso: Estado da Onda não atualizado ({str(e)[:200]})")
        return
    if r.returncode != 0:
        print(f"aviso: Estado da Onda não atualizado ({(r.stderr or r.stdout).strip()[:200]})")
        return
    for linha in r.stdout.splitlines():
        if linha.startswith("push: "):
            print(linha)


def quebrar(raiz: Path, chave: str, motivo: str, pr: int | None) -> str:
    """A Onda termina quebrada: a main segue vermelha e nada foi mergeado pelo passo."""
    print(f"quebrada: {motivo}; nada foi mergeado")
    registrar(raiz, chave, "erro", motivo, pr)
    return QUEBRADA


def depois_do_merge(raiz: Path, chave: str, comando: str, merges: list[Merge], github, wt: Path) -> str:
    """O passo inteiro. `github` abre, espera e mergeia o PR do revert e reabre a issue (`entregar`,
    `mergear`, `reabrir`); `wt` e o caminho do worktree descartavel. Devolve VERDE, REVERTIDA ou QUEBRADA."""
    git(raiz, "fetch", "-q", "origin", "main")
    criar_worktree(raiz, wt)
    try:
        ponta = git(wt, "rev-parse", "HEAD").stdout.strip()
        estado, _ = veredito(wt, comando, ponta)
        if estado == VERDE:
            print(f"teste da main: verde em {ponta[:8]}")
            return VERDE
        if estado == INSTAVEL:
            return quebrar(raiz, chave, f"o teste da main falhou e depois passou em {ponta[:8]}: teste instável, "
                           "nenhum merge foi desfeito", None)
        # o ultimo ponto verde e a main de antes do primeiro squash do lote (o pai dele)
        base = git(wt, "rev-parse", f"{merges[0].sha}^").stdout.strip()
        estado, _ = veredito(wt, comando, base)
        if estado == INSTAVEL:
            return quebrar(raiz, chave, f"o teste falhou e depois passou na main de antes do lote ({base[:8]}): "
                           "teste instável, nenhum merge foi desfeito", None)
        if estado == VERMELHO:
            return quebrar(raiz, chave, f"a main já estava vermelha antes do lote ({base[:8]}), e nenhum merge "
                           "dele foi desfeito", None)
        culpado, estado, falha = primeiro_vermelho(wt, comando, merges)
        if culpado is None:
            return quebrar(raiz, chave, f"a main ficou vermelha em {ponta[:8]}, mas nenhum merge do lote quebra "
                           "o teste sozinho", None)
        if estado == INSTAVEL:
            return quebrar(raiz, chave, f"o teste falhou e depois passou no squash do PR #{culpado.pr} "
                           f"({culpado.nome}): teste instável, nenhum merge foi desfeito", culpado.pr)
        print(f"teste da main: vermelho na ponta {ponta[:8]}; o primeiro merge que quebra é o PR #{culpado.pr} "
              f"(squash {culpado.sha[:8]})")
        try:
            pr_rev, sha_rev = reverter(raiz, wt, chave, comando, culpado, falha, github)
        except Exception as e:  # noqa: BLE001
            return quebrar(raiz, chave, f"a main ficou vermelha depois do PR #{culpado.pr} ({culpado.nome}) e o "
                           f"revert não entrou: {str(e)[:200]}", culpado.pr)
        print(f"revert: PR #{culpado.pr} desfeito pelo PR #{pr_rev} ({sha_rev[:8]}), a main voltou ao verde")
        reabrir(chave, comando, culpado, falha, pr_rev, github)
        registrar(raiz, chave, "revert", f"{culpado.nome} voltou para a Fila (o PR #{culpado.pr} quebrou o teste "
                  f"da main e saiu pelo PR #{pr_rev})", culpado.pr)
        return REVERTIDA
    finally:
        remover_worktree(raiz, wt)
