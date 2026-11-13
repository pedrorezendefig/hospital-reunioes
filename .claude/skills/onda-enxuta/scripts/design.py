#!/usr/bin/env python3
"""A Lente de design do revisor da Onda: sobe o app do PR para os prints, desce depois e separa os achados.

Uso:
    python3 design.py subir --pr <N>              # o app do PR numa pasta temporária
    python3 design.py descer --pr <N>             # para o app e apaga a pasta (os prints ficam)
    python3 design.py achados --pr <N> <arquivo>  # P0 e P1 para o must-fix; P2 e P3 para o polimento

O bloco `design` do `fluxo.json` diz como: `{"guia": "<caminho>", "subir": "<comando>", "url": "<url>"}`.
O `subir` roda na raiz de um worktree com o código do PR (`git fetch origin pull/<N>/head`) e
fica de pé até o `descer`; a `url` é a da tela, numa porta que o app de verdade não usa.

Saída do `subir`: as linhas `url:`, `pasta:` e `prints:` (a pasta onde o revisor grava os prints),
exit 0. App que não sobe: a linha `design (não rodou: <motivo>)`, que o revisor põe na linha
`Lentes:` do veredito, e exit 1. Erro de uso ou de configuração: exit 2 com o motivo no stderr.

O `achados` lê um achado por linha (`- P<0 a 3> · <onde> · <o que>`; achado sem prioridade conta
como P0). Imprime as linhas P0 e P1, que entram no must-fix do veredito, e a linha `Polimento:`.
P2 e P3 não seguram o merge: viram uma issue `needs-triage` com link para o PR e um comentário
no PR, uma vez só. Sem P2 nem P3, `Polimento: nenhum` e nada no GitHub.
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fluxo  # noqa: E402

ESPERA = 100  # segundos até a url responder; cabe nos 2 minutos do Bash do revisor
PRIORIDADE = re.compile(r"^-\s*P([0-3])\b")


class NaoRodou(Exception):
    """O motivo, numa frase, de a Lente não ter rodado."""


def _pastas(cfg: dict, pr: str) -> tuple[Path, Path]:
    base = Path(tempfile.gettempdir()) / f"{cfg['slug']}-design-pr{pr}"
    return base, base.with_name(base.name + "-prints")


def _responde(url: str) -> bool:
    try:
        urllib.request.urlopen(url, timeout=2).close()
        return True
    except urllib.error.HTTPError:
        return True  # o servidor respondeu, mesmo que com erro
    except (urllib.error.URLError, OSError):
        return False


def _git(*args: str) -> None:
    r = subprocess.run(["git", *args], cwd=fluxo.raiz(), capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        ultima = ((r.stderr or r.stdout).strip().splitlines() or ["sem mensagem"])[-1]
        raise NaoRodou(f"git {args[0]} falhou: {ultima}")


def _parar(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.1)


def descer(cfg: dict, pr: str) -> None:
    pasta, _ = _pastas(cfg, pr)
    pid = pasta.with_name(pasta.name + ".pid")
    if pid.exists():
        _parar(int(pid.read_text(encoding="utf-8")))
        pid.unlink()
    pasta.with_name(pasta.name + ".log").unlink(missing_ok=True)
    if pasta.exists():
        subprocess.run(["git", "worktree", "remove", "--force", str(pasta)], cwd=fluxo.raiz(), capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=fluxo.raiz(), capture_output=True)


def subir(cfg: dict, pr: str) -> dict:
    design = cfg.get("design") or {}
    if not design.get("subir") or not design.get("url"):
        raise NaoRodou("o fluxo.json não diz como subir o app (design.subir e design.url)")
    url = design["url"]
    if _responde(url):
        raise NaoRodou(f"{url} já respondia antes de subir o app do PR (porta ocupada)")
    descer(cfg, pr)
    pasta, prints = _pastas(cfg, pr)
    _git("fetch", "-q", "origin", f"pull/{pr}/head")
    _git("worktree", "add", "-q", "--detach", str(pasta), "FETCH_HEAD")
    log = pasta.with_name(pasta.name + ".log")
    with open(log, "w", encoding="utf-8") as saida:
        processo = subprocess.Popen(design["subir"], shell=True, cwd=pasta, stdout=saida, stderr=subprocess.STDOUT,
                                    start_new_session=True)
    pasta.with_name(pasta.name + ".pid").write_text(str(processo.pid), encoding="utf-8")
    limite = time.monotonic() + ESPERA
    while not _responde(url):
        if processo.poll() is not None:
            fim = " ".join(log.read_text(encoding="utf-8", errors="replace").split()[-30:])
            descer(cfg, pr)
            raise NaoRodou(f"o app saiu com código {processo.returncode}" + (f": {fim}" if fim else ""))
        if time.monotonic() > limite:
            descer(cfg, pr)
            raise NaoRodou(f"{url} não respondeu em {ESPERA} s")
        time.sleep(0.5)
    prints.mkdir(exist_ok=True)
    return {"url": url, "pasta": str(pasta), "prints": str(prints)}


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()


def _corpo(texto: str) -> str:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as f:
        f.write(texto)
    return f.name


def achados(texto: str, pr: str) -> list[str]:
    """As linhas para o veredito: os achados P0 e P1 e, por último, a linha `Polimento:`."""
    linhas = [linha.strip() for linha in texto.splitlines() if linha.strip().startswith("-")]
    prioridade = {linha: int(m.group(1)) if (m := PRIORIDADE.match(linha)) else 0 for linha in linhas}
    must_fix = [linha for linha in linhas if prioridade[linha] <= 1]
    polimento = [linha for linha in linhas if prioridade[linha] >= 2]
    if not polimento:
        return must_fix + ["Polimento: nenhum"]
    lista = "\n".join(polimento)
    corpo = _corpo(f"<!-- automacao -->\nAchados P2 e P3 da Lente de design no PR #{pr}. Nenhum segurou o merge.\n\n"
                   f"{lista}\n")
    try:
        url = _gh("issue", "create", "--title", f"Polimento de design do PR #{pr}", "--label", "needs-triage",
                  "--body-file", corpo).splitlines()[-1]
    finally:
        os.unlink(corpo)
    corpo = _corpo(f"<!-- automacao -->\n## Polimento de design\nAchados P2 e P3, que não seguram o merge. "
                   f"Viraram a issue {url}.\n\n{lista}\n")
    try:
        _gh("pr", "comment", pr, "--body-file", corpo)
    finally:
        os.unlink(corpo)
    return must_fix + [f"Polimento: {url}"]


def main(argv: list[str]) -> int:
    for saida in (sys.stdout, sys.stderr):
        saida.reconfigure(encoding="utf-8")
    tamanho = {"subir": 3, "descer": 3, "achados": 4}
    if not argv or len(argv) != tamanho.get(argv[0]) or argv[1] != "--pr" or not argv[2].isdigit():
        print("uso: design.py subir|descer --pr <N> | achados --pr <N> <arquivo>", file=sys.stderr)
        return 2
    comando, pr = argv[0], argv[2]
    try:
        cfg = fluxo.carregar()
        if comando == "achados":
            print("\n".join(achados(Path(argv[3]).read_text(encoding="utf-8"), pr)))
            return 0
    except subprocess.CalledProcessError as e:
        print(f"erro: {' '.join(e.cmd[:3])} falhou: {(e.stderr or '').strip()}", file=sys.stderr)
        return 2
    except (fluxo.Erro, OSError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    if comando == "descer":
        descer(cfg, pr)
        print(f"desceu: app do PR #{pr}")
        return 0
    try:
        for chave, valor in subir(cfg, pr).items():
            print(f"{chave}: {valor}")
    except NaoRodou as e:
        print(f"design (não rodou: {e})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
