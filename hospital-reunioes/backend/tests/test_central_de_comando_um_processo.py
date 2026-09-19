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
`WEB_CONCURRENCY`, de onde o uvicorn lê o número de processos quando o
`--workers` falta. Uma variável colada à mão no painel do Coolify fica fora do
alcance de qualquer teste; o docstring de `cache.py` diz o que muda. Quem
precisar de mais processos troca antes o cache e o limitador por um
compartilhado, e então muda este teste.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O parse do CMD mora no arquivo do contrato de proxy (issue #349), e o de
# log do IP (issue #543) já o reaproveita: aqui é a terceira leitura, não a
# terceira cópia.
from test_proxy_confiavel import _cmd_do_dockerfile  # noqa: E402

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


def test_o_backend_sobe_o_uvicorn_com_um_processo_so():
    cmd = _cmd_do_dockerfile()

    assert cmd[0] == "uvicorn", f"o backend deixou de subir pelo uvicorn: {cmd}"
    processos = [parte for parte in cmd if parte == "--workers" or parte.startswith("--workers=")]
    assert processos == [], (
        "O CMD do Dockerfile pede mais de um processo. O cache da Central e o limite do "
        "Atualizar agora são por processo (ver o docstring de services/central_de_comando/cache.py)."
    )


def test_ninguem_pede_mais_processos_pela_variavel_do_uvicorn():
    """Sem `--workers`, o uvicorn usa o `WEB_CONCURRENCY` se ele existir: uma
    linha de configuração levaria a mais processos sem tocar o CMD."""
    for arquivo in ARQUIVOS_DE_CONFIGURACAO:
        assert arquivo.exists(), f"sumiu um arquivo de configuração conferido aqui: {arquivo}"
        assert "WEB_CONCURRENCY" not in arquivo.read_text(encoding="utf-8"), (
            f"{arquivo.name} define WEB_CONCURRENCY. O cache da Central e o limite do Atualizar agora "
            "são por processo (ver o docstring de services/central_de_comando/cache.py)."
        )
