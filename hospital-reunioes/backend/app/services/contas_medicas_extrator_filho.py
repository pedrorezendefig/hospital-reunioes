"""Processo filho que instala o teto de memória e vira o `pdftotext` (issue #1116).

Roda como script solto (`python -P contas_medicas_extrator_filho.py <limite>
<arquivo>`), fora do processo do uvicorn, pelo mesmo motivo do
`transcricao_extractor_filho`: quem morre na leitura hostil é o filho, não o
worker que serve o app inteiro.

O `pdftotext` é binário, então não dá para instalar o `RLIMIT_AS` dentro dele.
Este script instala o limite e se substitui pelo `pdftotext` com `exec`: o
processo é o mesmo, e o limite atravessa o `exec`. A alternativa, `preexec_fn`
no `Popen` do pai, não é segura com threads, e a leitura roda em thread.

Topo em stdlib pura: o pai importa este módulo só para saber o caminho.
"""

from __future__ import annotations

import os
import sys

SAIDA_SEM_PDFTOTEXT = 127


def main(argv: list[str]) -> int:
    limite, entrada = int(argv[1]), argv[2]
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limite, resource.RLIM_INFINITY))
    except (ValueError, OSError, AttributeError):
        # No macOS o kernel recusa `RLIMIT_AS`; quem segura é o vigia do pai.
        print(f"RLIMIT_AS indisponivel em {sys.platform}: quem segura e o vigia do pai", file=sys.stderr)

    try:
        os.execvp("pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", entrada, "-"])
    except OSError as e:
        print(f"pdftotext indisponivel: {e}", file=sys.stderr)
    return SAIDA_SEM_PDFTOTEXT


if __name__ == "__main__":
    sys.exit(main(sys.argv))
