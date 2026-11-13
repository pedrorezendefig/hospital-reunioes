"""sem_volta.py: a conferencia "sem volta" da subida, antes de cada merge (issue #324).

Quem chama e o `fechar_onda.py`, logo depois das pre-condicoes, com os PRs do lote. Um PR e sem volta
quando o diff dele contra a origin/main:
  - acrescenta numa migration (pasta `migrations.pasta` do `.claude/fluxo.json`) SQL que apaga tabela,
    coluna ou dado (DROP TABLE, DROP COLUMN, ALTER TABLE ... DROP, DROP SCHEMA, TRUNCATE, DELETE FROM),
    fora dos comentarios do SQL;
  - toca arquivo de segredo (`.env` e `.env.*` menos os de exemplo, chave, certificado, credencial);
  - toca caminho que o Projeto declara como protegido: a lista de globs `protegidos` do fluxo.json, com a
    regra do `revisao-sensivel.txt` (glob sem `/` casa o nome em qualquer pasta, `/**` a pasta inteira).

Na Noite e na Sesta (a chave da subida comeca com `noite-` ou `sesta-`), o PR sem volta fica de fora do
lote, com a linha `de fora: #<PR> sem volta (<motivo>)`, recebe um comentario com o motivo e a issue que
ele fecha vai para a Etapa Humana (`ready-for-human`, sem `in-progress`). No Estado da Onda da chave, a issue
fica em `baixa` com o PR e a Onda ganha o evento `pronto-para-voce` com o motivo ("espera voce"); a linha
`push:` sai aqui, para a sessao mandar ao celular. O GitHub ou o Estado que falham so avisam: o PR fica de
fora do mesmo jeito. Fora da Noite e da Sesta a subida so avisa (linha `aviso:`) e o PR segue. No
`--dry-run`, so a linha, sem comentario.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sensivel import casa  # noqa: E402
from teste_da_main import CHAVE_DA_ONDA, ESTADO, registrar  # noqa: E402

DA_NOITE = re.compile(r"^(noite|sesta)-")
# O SQL que apaga tabela, coluna ou dado. `ALTER TABLE ... DROP` sem COLUMN tambem apaga a coluna; DROP de
# restricao, default, NOT NULL, identidade ou expressao nao apaga dado.
APAGA = re.compile(
    r"\bDROP\s+(TABLE|SCHEMA|DATABASE|COLUMN)\b|\bTRUNCATE\b|\bDELETE\s+FROM\b"
    r"|\bALTER\s+TABLE\b[^;]*?\bDROP\s+(?!CONSTRAINT\b|DEFAULT\b|NOT\b|IDENTITY\b|EXPRESSION\b)",
    re.I,
)
COMENTARIO_SQL = re.compile(r"--[^\n]*|/\*.*?\*/", re.S)
SEGREDOS = (".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks", "id_rsa", "id_ed25519",
            "credentials.json", "service-account*.json")
DE_EXEMPLO = (".env.example", ".env.sample", ".env.template", ".env.exemplo")


def na_noite(chave: str) -> bool:
    """A subida e de uma sessao da Noite ou da Sesta: ninguem acordado para decidir o que nao tem volta."""
    return bool(DA_NOITE.match(chave))


def _git(raiz: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=str(raiz), capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def _acrescentado(raiz: Path, base: str, head: str, caminho: str) -> str:
    """As linhas que o PR acrescenta no arquivo (o arquivo inteiro, se ele e novo)."""
    diff = _git(raiz, "diff", "--no-renames", "-U0", f"{base}...{head}", "--", caminho)
    return "\n".join(linha[1:] for linha in diff.splitlines() if linha.startswith("+") and not linha.startswith("+++"))


def motivos(raiz: Path, base: str, head: str, cfg: dict) -> list[str]:
    """Por que o PR nao tem volta, um motivo por arquivo; lista vazia se ele tem."""
    arquivos = _git(raiz, "diff", "--no-renames", "--name-only", f"{base}...{head}").split()
    achados = []
    pasta = ((cfg.get("migrations") or {}).get("pasta") or "").rstrip("/")
    for caminho in arquivos:
        if pasta and caminho.startswith(pasta + "/"):
            sql = COMENTARIO_SQL.sub(" ", _acrescentado(raiz, base, head, caminho))
            if APAGA.search(sql):
                achados.append(f"migration que apaga dado: {Path(caminho).name}")
        elif any(casa(caminho, g) for g in SEGREDOS) and Path(caminho).name not in DE_EXEMPLO:
            achados.append(f"arquivo de segredo: {caminho}")
        elif any(casa(caminho, g) for g in cfg.get("protegidos") or []):
            achados.append(f"caminho protegido: {caminho}")
    return achados


class GitHub:
    """O lado do GitHub da conferencia: o comentario no PR e a issue na Etapa Humana."""

    def __init__(self, raiz: Path):
        self.raiz = raiz

    def _gh(self, *args: str, check: bool = True) -> None:
        subprocess.run(["gh", *args], cwd=str(self.raiz), capture_output=True, text=True, encoding="utf-8",
                       check=check)

    def comentar(self, pr: int, corpo: str) -> None:
        self._gh("pr", "comment", str(pr), "--body", corpo)

    def para_o_humano(self, issue: int) -> None:
        # a issue pode nao ter o `in-progress`: tirar o que nao esta la nao pode impedir o resto
        self._gh("issue", "edit", str(issue), "--remove-label", "in-progress", check=False)
        self._gh("issue", "edit", str(issue), "--add-label", "ready-for-human")


def marcar_baixa(raiz: Path, chave: str, issue: int, pr: int) -> None:
    """A issue em `baixa` no Estado da Onda da chave. Chave que nao e de Onda, ou Estado que nao grava, so
    avisa: o PR ja ficou de fora."""
    achado = CHAVE_DA_ONDA.match(chave)
    if not achado:
        return
    r = subprocess.run([sys.executable, str(ESTADO), "issue", "--sessao", achado[1], "--onda", achado[2],
                        "--numero", str(issue), "--pr", str(pr), "--status", "baixa"],
                       cwd=str(raiz), capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        print(f"aviso: Estado da Onda não atualizado ({(r.stderr or r.stdout).strip()[:200]})")


def comentario(pr: int, motivos_do_pr: list[str]) -> str:
    return ("<!-- automacao -->\n**Este PR espera você.** A Noite não mergeia o que não tem volta, e este PR "
            "tem:\n\n" + "\n".join(f"- {m}" for m in motivos_do_pr)
            + f"\n\nEle fica aberto, e a issue foi para a Etapa Humana. Depois de revisar, suba com "
            f"`fechar_onda.py --prs {pr}`.")


def da_subida(raiz: Path, infos: list[dict], chave: str, cfg: dict, dry: bool = False,
              github=None) -> list[int]:
    """Os PRs do lote que ficam de fora por nao ter volta. Fora da Noite e da Sesta, nenhum: so o aviso."""
    noite = na_noite(chave)
    github = github or GitHub(raiz)
    fora = []
    for info in infos:
        n = info["number"]
        achados = motivos(raiz, "origin/main", info["head_conferido"], cfg)
        if not achados:
            continue
        texto = "; ".join(achados)
        if not noite:
            print(f"aviso: #{n} sem volta ({texto}); fora da Noite a subida so avisa e segue")
            continue
        fora.append(n)
        print(f"de fora: #{n} sem volta ({texto}): espera voce, na Etapa Humana")
        if dry:
            continue
        try:
            github.comentar(n, comentario(n, achados))
            for ref in info.get("closingIssuesReferences") or []:
                github.para_o_humano(ref["number"])
        except (subprocess.CalledProcessError, OSError) as e:
            print(f"aviso: comentario ou Etapa Humana de #{n} nao gravados ({str(e)[:200]}); o PR fica de fora")
        for ref in info.get("closingIssuesReferences") or []:
            marcar_baixa(raiz, chave, ref["number"], n)
        registrar(raiz, chave, "pronto-para-voce", f"PR #{n} sem volta, espera você: {texto}", n)
    return fora
