"""A imagem de produção e o CI instalam as dependências pelo `uv.lock` (issue #852).

Antes, o Dockerfile rodava `uv pip install -r pyproject.toml` e o CI rodava
`uv pip install -e ".[dev]"`. Nenhum dos dois lê o `uv.lock`: cada build
resolvia a versão mais nova que o `pyproject.toml` permite, sem conferir hash.
O lock existia, o dev usava, e produção rodava outra coisa. Pesa mais desde que
o processo guarda a chave privada da service account do Google (Central de
Comando, ADR 0058): uma versão nova e envenenada de qualquer dependência
entraria no próximo deploy sem ninguém ver.

Este arquivo trava o que está no repositório:

- a imagem copia o `uv.lock` e instala a partir dele, com o lock congelado
  (`--frozen`) e conferindo o hash de cada pacote (`--require-hashes`), sem as
  dependências de dev;
- o CI do backend instala pelo lock, com o extra de dev;
- um passo do CI reprova o PR quando o `uv.lock` está fora de sincronia com o
  `pyproject.toml`, antes de lint e testes.

Se o mecanismo mudar (por exemplo, `uv sync --frozen` num venv no lugar do
`uv export` com `--require-hashes`), o teste muda junto, desde que o lock siga
sendo a única fonte das versões.
"""

from __future__ import annotations

import shlex
from pathlib import Path

import yaml

BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parents[1]
DOCKERFILE = BACKEND / "Dockerfile"
CI = REPO / ".github" / "workflows" / "ci.yml"


# ---------------------------------------------------------------------------
# Leitura do Dockerfile
# ---------------------------------------------------------------------------


def _instrucoes_do_dockerfile() -> list[tuple[str, str]]:
    """As instruções do Dockerfile como `(INSTRUCAO, argumentos)`.

    Junta as linhas continuadas com `\\` e pula comentários e linhas vazias,
    que é como o Docker lê o arquivo.
    """
    instrucoes: list[tuple[str, str]] = []
    atual = ""
    for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        crua = linha.strip()
        if not atual and (not crua or crua.startswith("#")):
            continue
        if atual and crua.startswith("#"):
            continue
        if crua.endswith("\\"):
            atual += crua[:-1] + " "
            continue
        atual += crua
        nome, _, argumentos = atual.partition(" ")
        instrucoes.append((nome.upper(), argumentos.strip()))
        atual = ""
    return instrucoes


# Palavras do shell que abrem um comando sem ser o comando (`if ! uv lock
# --check; then`): saem da frente para o comando aparecer como é.
_PALAVRAS_DO_SHELL = {"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!"}


def _comandos(texto: str) -> list[list[str]]:
    """Os comandos de shell de um trecho, separados por `&&`, `;`, `|` ou `||`."""
    comandos: list[list[str]] = [[]]
    lexer = shlex.shlex(texto, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    for token in lexer:
        if token in {"&&", ";", "|", "||"}:
            comandos.append([])
        elif comandos[-1] or token not in _PALAVRAS_DO_SHELL:
            comandos[-1].append(token)
    return [c for c in comandos if c]


def _eh(comando: list[str], *prefixo: str) -> bool:
    return tuple(comando[: len(prefixo)]) == prefixo


def _comandos_de_instalacao(texto: str) -> list[list[str]]:
    """Os comandos que instalam ou resolvem dependências Python."""
    return [
        c
        for c in _comandos(texto)
        if _eh(c, "uv", "pip", "install")
        or _eh(c, "uv", "sync")
        or _eh(c, "uv", "export")
        or _eh(c, "pip", "install")
        or _eh(c, "python", "-m", "pip", "install")
    ]


def _runs_de_instalacao() -> list[tuple[int, list[list[str]]]]:
    """Os `RUN` que instalam dependências, com a posição da instrução."""
    return [
        (i, cmds)
        for i, (nome, args) in enumerate(_instrucoes_do_dockerfile())
        if nome == "RUN" and (cmds := _comandos_de_instalacao(args))
    ]


class TestImagemInstalaPeloLock:
    """Critério: o build da imagem do backend usa as versões exatas do `uv.lock`."""

    def test_imagem_instala_dependencias(self):
        assert _runs_de_instalacao(), "Dockerfile sem nenhum RUN que instale dependências Python"

    def test_lock_entra_na_imagem_antes_da_instalacao(self):
        instrucoes = _instrucoes_do_dockerfile()
        copias_do_lock = [i for i, (nome, args) in enumerate(instrucoes) if nome == "COPY" and "uv.lock" in args.split()]
        assert copias_do_lock, "O Dockerfile não copia o uv.lock: a instalação não tem como ler o lock."
        primeira_instalacao = _runs_de_instalacao()[0][0]
        assert copias_do_lock[0] < primeira_instalacao, "O uv.lock precisa entrar na imagem antes do RUN que instala."

    def test_nada_resolve_direto_do_pyproject(self):
        """`-r pyproject.toml` e `install .` resolvem a versão mais nova permitida, sem lock."""
        for _, comandos in _runs_de_instalacao():
            for c in comandos:
                assert "pyproject.toml" not in c, f"Instalação lendo o pyproject.toml, fora do lock: {shlex.join(c)}"
                if "install" in c:
                    alvos = c[c.index("install") + 1 :]
                    assert "." not in alvos and "-e" not in alvos, f"Instalação do projeto, fora do lock: {shlex.join(c)}"

    def test_lock_e_lido_congelado(self):
        """`uv export` e `uv sync` leem o lock como está (`--frozen` ou `--locked`), sem re-resolver."""
        leituras = [c for _, cmds in _runs_de_instalacao() for c in cmds if _eh(c, "uv", "export") or _eh(c, "uv", "sync")]
        assert leituras, "Nenhum `uv export` nem `uv sync` no Dockerfile: nada lê o uv.lock."
        for c in leituras:
            assert "--frozen" in c or "--locked" in c, f"Leitura do lock sem --frozen/--locked: {shlex.join(c)}"

    def test_pip_install_so_em_modo_de_hash(self):
        """Com `--require-hashes`, pacote sem versão exata e hash do lock não entra."""
        for _, comandos in _runs_de_instalacao():
            for c in comandos:
                if _eh(c, "uv", "pip", "install") or _eh(c, "pip", "install") or _eh(c, "python", "-m", "pip", "install"):
                    assert "--require-hashes" in c, f"pip install sem --require-hashes: {shlex.join(c)}"

    def test_imagem_nao_leva_dependencias_de_dev(self):
        for _, comandos in _runs_de_instalacao():
            for c in comandos:
                texto = shlex.join(c)
                assert "--all-extras" not in c and "--all-groups" not in c, f"Extras de dev na imagem: {texto}"
                assert "dev" not in [c[i + 1] for i, t in enumerate(c[:-1]) if t in {"--extra", "--group"}], (
                    f"Extra de dev na imagem: {texto}"
                )
                if _eh(c, "uv", "export") or _eh(c, "uv", "sync"):
                    assert "--no-dev" in c, f"Leitura do lock sem --no-dev: {texto}"


# ---------------------------------------------------------------------------
# Leitura do CI
# ---------------------------------------------------------------------------


def _passos_do_backend() -> list[dict]:
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    return ci["jobs"]["backend"]["steps"]


def _indice(passos: list[dict], condicao) -> list[int]:
    return [i for i, p in enumerate(passos) if condicao(p.get("run", ""))]


def _comandos_do_passo(passo: dict) -> list[list[str]]:
    return [c for linha in passo.get("run", "").splitlines() for c in _comandos(linha)]


class TestCiInstalaPeloLock:
    """Critério: o CI do backend usa as versões exatas do `uv.lock`."""

    def test_ci_sincroniza_pelo_lock_com_o_extra_de_dev(self):
        syncs = [c for p in _passos_do_backend() for c in _comandos_do_passo(p) if _eh(c, "uv", "sync")]
        assert len(syncs) == 1, f"O job de backend precisa de exatamente um `uv sync`, achei {len(syncs)}"
        sync = syncs[0]
        assert "--frozen" in sync or "--locked" in sync, f"`uv sync` sem --frozen/--locked: {shlex.join(sync)}"
        assert "dev" in [sync[i + 1] for i, t in enumerate(sync[:-1]) if t == "--extra"], (
            f"`uv sync` sem o extra de dev (ruff, pytest): {shlex.join(sync)}"
        )

    def test_ci_nao_instala_fora_do_lock(self):
        for passo in _passos_do_backend():
            for c in _comandos_do_passo(passo):
                instala_fora = _eh(c, "uv", "pip", "install") or (
                    _eh(c, "pip", "install") and c[2:] != ["uv"] and "--require-hashes" not in c
                )
                assert not instala_fora, f"Instalação fora do lock no CI: {shlex.join(c)}"

    def test_lint_e_testes_rodam_depois_da_instalacao(self):
        passos = _passos_do_backend()
        sync = _indice(passos, lambda r: "uv sync" in r)[0]
        for ferramenta in ("ruff check", "ruff format", "pytest"):
            usos = _indice(passos, lambda r, f=ferramenta: f in r)
            assert usos and all(i > sync for i in usos), f"`{ferramenta}` roda antes do `uv sync`"


class TestCiReprovaLockForaDeSincronia:
    """Critério: lock desatualizado em relação ao `pyproject.toml` reprova o CI."""

    def _passos_de_checagem(self) -> list[int]:
        return [
            i
            for i, p in enumerate(_passos_do_backend())
            for c in _comandos_do_passo(p)
            if _eh(c, "uv", "lock") and ("--check" in c or "--locked" in c)
        ]

    def test_existe_passo_que_confere_o_lock(self):
        assert self._passos_de_checagem(), "Nenhum passo do CI roda `uv lock --check`."

    def test_checagem_nao_e_opcional(self):
        passos = _passos_do_backend()
        for i in self._passos_de_checagem():
            assert not passos[i].get("continue-on-error"), "`uv lock --check` com continue-on-error não reprova nada."
            assert "|| true" not in passos[i]["run"], "`uv lock --check` com `|| true` não reprova nada."

    def test_checagem_vem_antes_de_instalar(self):
        """Lock velho reprova antes de o `uv sync --frozen` instalar a versão velha em silêncio."""
        passos = _passos_do_backend()
        sync = _indice(passos, lambda r: "uv sync" in r)[0]
        assert min(self._passos_de_checagem()) < sync
