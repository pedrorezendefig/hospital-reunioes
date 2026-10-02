"""A Central conta com o backend rodando num processo só (issue #815).

O cache com frescor da Central (`services/central_de_comando/cache.py`) e o
limitador de taxa do app (`slowapi`, com o balde em memória) moram na memória
do processo. Com um processo só, eles SÃO o cache e o limite do app. Com mais
de um, cada processo teria os seus, e nada quebraria de um jeito visível:

- a mesma tela mostraria carimbos de frescor diferentes conforme o processo
  que respondesse;
- cada processo iria ao Google uma vez por hora e chave;
- o Atualizar agora renovaria só o processo que o atendeu;
- o limite de 5 Atualizar agora por minuto viraria 5 por minuto por processo.

Por isso este teste trava o que está no repositório: o `CMD` do Dockerfile
sobe o uvicorn sem `--workers` (e não o gunicorn), e ninguém define o
`WEB_CONCURRENCY` nem o `UVICORN_WORKERS`, de onde o uvicorn lê o número de
processos quando o `--workers` falta (#834). Uma variável colada à mão no
painel do Coolify fica fora do alcance de qualquer teste; o docstring de
`cache.py` diz o que muda. Quem precisar de mais processos troca antes o cache
e o limitador por um compartilhado, e então muda este teste.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O parse do CMD mora no apoio do Dockerfile (#834), e não num arquivo de
# teste: aqui é mais uma leitura, não mais uma cópia.
from dockerfile_apoio import cmd_do_dockerfile  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND.parent
REPO = APP_DIR.parent

# Os lugares versionados de onde o container de produção ou o local recebem
# configuração de processo.
ARQUIVOS_DE_CONFIGURACAO = (
    BACKEND / "Dockerfile",
    APP_DIR / "docker-compose.yml",
    REPO / "docs" / "spec" / "deploy" / "project.json",
    BACKEND / ".env.example",
    APP_DIR / ".env.example",
)


# As variáveis de onde o uvicorn lê o número de processos quando o `--workers`
# falta: o `WEB_CONCURRENCY`, padrão do `--workers`, e o `UVICORN_WORKERS`, porque
# o CLI dele roda com `auto_envvar_prefix="UVICORN"` e toda opção vira variável.
VARIAVEIS_DE_PROCESSOS = ("WEB_CONCURRENCY", "UVICORN_WORKERS")


def _variaveis_de_processos_em(texto: str) -> list[str]:
    """As variáveis de número de processos que aparecem no texto."""
    return [nome for nome in VARIAVEIS_DE_PROCESSOS if nome in texto]


def test_o_backend_sobe_o_uvicorn_com_um_processo_so():
    cmd = cmd_do_dockerfile()

    assert cmd[0] == "uvicorn", f"o backend deixou de subir pelo uvicorn: {cmd}"
    processos = [parte for parte in cmd if parte == "--workers" or parte.startswith("--workers=")]
    assert processos == [], (
        "O CMD do Dockerfile pede mais de um processo. O cache da Central e o limite do "
        "Atualizar agora são por processo (ver o docstring de services/central_de_comando/cache.py)."
    )


def test_ninguem_pede_mais_processos_pela_variavel_do_uvicorn():
    """Sem `--workers`, o uvicorn lê o número de processos de uma variável se
    ela existir: uma linha de configuração levaria a mais processos sem tocar o
    CMD."""
    for arquivo in ARQUIVOS_DE_CONFIGURACAO:
        assert arquivo.exists(), f"sumiu um arquivo de configuração conferido aqui: {arquivo}"
        variaveis = _variaveis_de_processos_em(arquivo.read_text(encoding="utf-8"))
        assert variaveis == [], (
            f"{arquivo.name} define {', '.join(variaveis)}. O cache da Central e o limite do Atualizar agora "
            "são por processo (ver o docstring de services/central_de_comando/cache.py)."
        )


@pytest.mark.parametrize(
    "linha",
    [
        "ENV WEB_CONCURRENCY=2",
        "ENV UVICORN_WORKERS=2",
        "UVICORN_WORKERS=3",
        "      - UVICORN_WORKERS=2",
        '"WEB_CONCURRENCY": "2"',
    ],
)
def test_a_trava_enxerga_cada_variavel_que_liga_mais_processos(linha):
    """Caso de controle: a trava acima só vale se enxerga as duas variáveis
    (revisão do PR #831, #834). Com `ENV UVICORN_WORKERS=2` no Dockerfile, ou
    a linha no `.env.example`, ela passaria sem isto."""
    assert _variaveis_de_processos_em(linha) != []


# ─── A regra das fatias da Central: nenhum arquivo de teste importa outro ────
#
# Importar um arquivo de teste roda o que ele roda na coleta e amarra um ao
# outro (#815). O que é de mais de um arquivo mora num módulo de apoio
# (`central_de_comando_apoio.py`, `dockerfile_apoio.py`), e não noutro teste.

TESTES = BACKEND / "tests"

# Quem lê o CMD do Dockerfile, e já o importou de `test_proxy_confiavel` (#834).
LEITORES_DO_CMD = ("test_proxy_confiavel.py", "test_ip_cliente_no_log.py")


def _arquivos_de_teste_importados(codigo: str) -> list[str]:
    """Os arquivos de teste (`test_*`) que o código importa."""
    modulos: list[str] = []
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            modulos += [apelido.name for apelido in no.names]
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            modulos.append(no.module)
    return sorted({modulo for modulo in modulos if modulo.split(".")[0].startswith("test_")})


@pytest.mark.parametrize(
    ("codigo", "importados"),
    [
        ("from test_proxy_confiavel import _cmd_do_dockerfile", ["test_proxy_confiavel"]),
        ("import test_proxy_confiavel", ["test_proxy_confiavel"]),
        ("from central_de_comando_apoio import SUPER_ADMIN", []),
        ("from dockerfile_apoio import cmd_do_dockerfile", []),
        ("from conftest import TentativaDeRedeNoTeste", []),
    ],
)
def test_a_regra_enxerga_o_import_de_outro_arquivo_de_teste(codigo, importados):
    assert _arquivos_de_teste_importados(codigo) == importados


def test_nenhum_arquivo_de_teste_da_central_importa_outro():
    arquivos = sorted(TESTES.glob("test_central_de_comando_*.py")) + [TESTES / nome for nome in LEITORES_DO_CMD]
    assert len(arquivos) > len(LEITORES_DO_CMD), "a varredura não achou os testes da Central"

    culpados = {
        arquivo.name: importados
        for arquivo in arquivos
        if (importados := _arquivos_de_teste_importados(arquivo.read_text(encoding="utf-8")))
    }

    assert culpados == {}, "O que é de mais de um arquivo de teste mora num módulo de apoio, e não noutro teste."
