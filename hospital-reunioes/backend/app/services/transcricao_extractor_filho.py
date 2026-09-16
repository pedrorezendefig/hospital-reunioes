"""Processo filho que lê de fato o `.pdf` e o `.docx` (issue #758).

Roda como script solto (`python transcricao_extractor_filho.py <ext> <arquivo>
<limite>`), fora do processo do uvicorn. O motivo é que o uvicorn sobe com **um
worker** servindo o app inteiro: extração que esgota memória ou queima CPU
derruba junto a Ouvidoria pública, as Reuniões, as Atas e os POPs. Aqui quem
morre é o filho.

Por que script solto e não `multiprocessing`: o `spawn` reimporta o módulo do
alvo e o `__main__`, e o `fork` herda o espaço de endereçamento do worker
inteiro (o `RLIMIT_AS` passaria a contar a memória do pai). Script solto sobe um
interpretador limpo, e a ordem que importa fica explícita:

    1. instala o `RLIMIT_AS`;
    2. só então importa o parser.

Invertida, o próprio import já teria gasto parte do limite, e o teto passaria a
morder o `pdfplumber` subindo em vez do arquivo do atacante.

As constantes do orçamento (quanto de endereçamento, quanto de RSS, quanto
tempo) vivem no `transcricao_extractor`, que é quem decide; este módulo recebe o
limite por argumento. O pai importa este módulo só para saber o caminho do
script e os códigos de saída, por isso o topo aqui é **stdlib pura**: o
`pdfplumber` e o `docx2txt` são importados dentro das funções, depois do limite.
"""

from __future__ import annotations

import sys
from io import BytesIO

STATUS_OK = "OK"
STATUS_RECUSA = "RECUSA"

# O filho bateu no teto de endereçamento e o CPython levantou MemoryError. Sai
# por código, e não por mensagem, porque no instante do estouro qualquer
# alocação nova (inclusive a da mensagem) pode falhar de novo.
SAIDA_SEM_MEMORIA = 97

MIN_PDF_TEXT_BYTES = 200


def instalar_limite_de_enderecamento(limite_em_bytes: int) -> bool:
    """Aplica `RLIMIT_AS` neste processo. Devolve se o limite pegou.

    No Linux (onde o app roda) o limite morde dentro da alocação, inclusive
    dentro do C das bibliotecas de parser: é a única guarda que para um
    `zlib.decompress` de gigabytes no meio. No macOS o kernel recusa
    `setrlimit(RLIMIT_AS)` com EINVAL para qualquer valor, então na máquina de
    desenvolvimento quem segura é o vigia de RSS do processo pai.
    """
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limite_em_bytes, resource.RLIM_INFINITY))
        return True
    except (ValueError, OSError, AttributeError):
        return False


def extrair_pdf(file_bytes: bytes) -> str:
    """Texto de um PDF, uma página por vez e soltando cada página lida.

    O `page.close()` não é higiene: sem ele o `pdfplumber` guarda o objeto de
    cada caractere de **todas** as páginas até o fim, e um PDF honesto de 234 KB
    com 737 mil caracteres chega a 1.465 MB de pico. Com ele, o mesmo arquivo
    devolve o mesmo texto com 51 MB. É essa diferença que faz existir um teto de
    memória capaz de recusar as bombas sem recusar a ata de verdade.
    """
    import pdfplumber

    partes: list[str] = []
    with pdfplumber.open(BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            texto = page.extract_text() or ""
            if texto:
                partes.append(texto)
            page.close()
    return "\n\n".join(partes).strip()


def extrair_docx(file_bytes: bytes) -> str:
    import docx2txt

    texto = docx2txt.process(BytesIO(file_bytes)) or ""
    return texto.strip()


def extrair(ext: str, file_bytes: bytes) -> str:
    """Despacha pela extensão. `ValueError` é recusa com frase pronta em pt-BR."""
    if ext == ".pdf":
        texto = extrair_pdf(file_bytes)
        if len(texto.encode("utf-8")) < MIN_PDF_TEXT_BYTES:
            raise ValueError(
                "PDF parece ser escaneado (sem texto extraivel). Faca OCR antes ou envie a transcricao em texto."
            )
        return texto
    if ext == ".docx":
        return extrair_docx(file_bytes)
    raise ValueError("Formato nao suportado.")


def _responder(status: str, corpo: str) -> None:
    """Primeira linha é o status, o resto é o corpo em UTF-8."""
    saida = sys.stdout.buffer
    saida.write(status.encode("ascii") + b"\n")
    saida.write(corpo.encode("utf-8"))
    saida.flush()


def main(argv: list[str]) -> int:
    ext, caminho, limite = argv[1], argv[2], int(argv[3])

    if not instalar_limite_de_enderecamento(limite):
        print(f"RLIMIT_AS indisponivel em {sys.platform}: quem segura e o vigia do pai", file=sys.stderr)

    try:
        with open(caminho, "rb") as arquivo:
            file_bytes = arquivo.read()
        texto = extrair(ext, file_bytes)
    except MemoryError:
        return SAIDA_SEM_MEMORIA
    except ValueError as e:
        _responder(STATUS_RECUSA, str(e))
        return 0
    except Exception as e:  # noqa: BLE001 - o pai traduz em frase para a tela
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1

    _responder(STATUS_OK, texto)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
