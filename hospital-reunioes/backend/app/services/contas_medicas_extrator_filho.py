"""Processo filho que instala o teto de memória e vira o `pdftotext` (issue #1116).

Roda como script solto (`python -P contas_medicas_extrator_filho.py <limite>
<arquivo>`), fora do processo do uvicorn, pelo mesmo motivo do
`transcricao_extractor_filho`: quem morre na leitura hostil é o filho, não o
worker que serve o app inteiro.

O `pdftotext` é binário, então não dá para instalar o `RLIMIT_AS` dentro dele.
Este script instala o limite e se substitui pelo `pdftotext` com `exec`: o
processo é o mesmo, e o limite atravessa o `exec`. A alternativa, `preexec_fn`
no `Popen` do pai, não é segura com threads, e a leitura roda em thread.

Com uma lista de páginas no terceiro argumento, o filho não vira o `pdftotext`:
devolve em JSON as palavras dessas páginas com a posição de cada uma, pelo
`extract_words` do `pdfplumber` (issue #1133). É o que a prescrição usa para ler
pela coordenada das colunas. O `pdfplumber` é importado depois do limite.

Topo em stdlib pura: o pai importa este módulo só para saber o caminho.
"""

from __future__ import annotations

import json
import os
import sys
from io import BytesIO

SAIDA_SEM_PDFTOTEXT = 127


def palavras(entrada: str, paginas: set[int]) -> dict[str, list[list]]:
    """Página (a primeira é 1) -> [x0, x1, topo, texto] de cada palavra, soltando cada página lida."""
    import pdfplumber

    with open(entrada, "rb") as f:
        conteudo = f.read()
    achadas: dict[str, list[list]] = {}
    with pdfplumber.open(BytesIO(conteudo)) as pdf:
        for numero in sorted(n for n in paginas if 1 <= n <= len(pdf.pages)):
            pagina = pdf.pages[numero - 1]
            achadas[str(numero)] = [
                [round(p["x0"], 2), round(p["x1"], 2), round(p["top"], 2), p["text"]] for p in pagina.extract_words()
            ]
            pagina.close()
    return achadas


def main(argv: list[str]) -> int:
    limite, entrada = int(argv[1]), argv[2]
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limite, resource.RLIM_INFINITY))
    except (ValueError, OSError, AttributeError):
        # No macOS o kernel recusa `RLIMIT_AS`; quem segura é o vigia do pai.
        print(f"RLIMIT_AS indisponivel em {sys.platform}: quem segura e o vigia do pai", file=sys.stderr)

    if len(argv) > 3:
        paginas = {int(n) for n in argv[3].split(",") if n}
        sys.stdout.write(json.dumps(palavras(entrada, paginas), ensure_ascii=False))
        return 0

    try:
        os.execvp("pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", entrada, "-"])
    except OSError as e:
        print(f"pdftotext indisponivel: {e}", file=sys.stderr)
    return SAIDA_SEM_PDFTOTEXT


if __name__ == "__main__":
    sys.exit(main(sys.argv))
