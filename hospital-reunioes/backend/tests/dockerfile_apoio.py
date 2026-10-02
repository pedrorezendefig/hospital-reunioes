"""Apoio compartilhado dos testes que leem o Dockerfile do backend (issue #834).

O parse do `CMD` morava no arquivo do contrato de proxy
(`test_proxy_confiavel.py`, issue #349), e o log do IP (issue #543) e a trava
de processo único da Central (issue #815) o importavam de lá. Importar um
arquivo de teste roda o que ele roda na coleta e amarra um ao outro; aqui ele
serve a quem precisar ler o CMD sem isso, no molde do
`central_de_comando_apoio.py`. Quem usa importa pelo nome:

    from dockerfile_apoio import cmd_do_dockerfile

Não é arquivo de teste (não começa com `test_`), então o pytest não o coleta.
"""

from __future__ import annotations

import json
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "Dockerfile"


def cmd_do_dockerfile() -> list[str]:
    """O `CMD` do Dockerfile do backend, em forma exec, como lista."""
    # O `CMD [` da forma exec, não o `CMD curl` de dentro do HEALTHCHECK.
    for linha in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        if linha.strip().startswith("CMD ["):
            return json.loads(linha.strip().removeprefix("CMD").strip())
    raise AssertionError("Dockerfile sem linha CMD em forma exec")
