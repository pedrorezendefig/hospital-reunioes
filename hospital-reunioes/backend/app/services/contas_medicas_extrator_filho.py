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

Com `--ocr <páginas> <prazo>`, o filho rasteriza cada página pedida pelo
`pdftoppm` e lê a imagem pelo `tesseract` (issue #1191), e devolve em JSON o
texto e a confiança da leitura de cada uma (issue #1398), na ordem pedida. As
páginas digitalizadas do Prontuário são as únicas que chegam aqui.

Topo em stdlib pura: o pai importa este módulo para saber o caminho e as faixas
da confiança.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Sequence

SAIDA_SEM_PDFTOTEXT = 127

# Faixas da qualidade da folha digitalizada (#1398), pela confiança do OCR:
# legível de 70 para cima, duvidosa de 50 a 69, ilegível abaixo de 50. Vêm do
# microteste dos dez pares e batem com a leitura visual das páginas.
LEGIVEL_A_PARTIR_DE = 70
ILEGIVEL_ABAIXO_DE = 50


def palavras(entrada: str, paginas: set[int]) -> dict[str, list[list]]:
    """Página (a primeira é 1) -> [x0, x1, topo, texto] de cada palavra, soltando cada página lida."""
    import pdfplumber

    achadas: dict[str, list[list]] = {}
    with pdfplumber.open(entrada) as pdf:
        for numero in sorted(n for n in paginas if 1 <= n <= len(pdf.pages)):
            pagina = pdf.pages[numero - 1]
            achadas[str(numero)] = [
                [round(p["x0"], 2), round(p["x1"], 2), round(p["top"], 2), p["text"]] for p in pagina.extract_words()
            ]
            pagina.close()
    return achadas


def ocr(entrada: str, paginas: Sequence[int], prazo: float) -> dict[str, dict]:
    """Página (a primeira é 1) -> {"texto", "confianca"} da imagem que o `pdftoppm`
    rasterizou, lida pelo `tesseract -l por` (issues #1191 e #1398), na ordem
    pedida: quem chama põe primeiro as páginas que importam. Os dois herdam o
    `RLIMIT_AS` deste processo. Página que não sai (binário ausente, falha, prazo
    esgotado) fica de fora, e quem chama a dá como não lida."""
    import subprocess
    import tempfile
    import time

    fim = time.monotonic() + prazo
    # Uma thread só: cada thread do OpenMP reserva pilha, e isso conta no `RLIMIT_AS`.
    ambiente = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    lidas: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="ocr-") as pasta:
        for numero in paginas:
            imagem = os.path.join(pasta, str(numero))
            lida = None
            esgotado = False
            try:
                subprocess.run(
                    ["pdftoppm", "-f", str(numero), "-l", str(numero), "-r", "300", "-gray", "-png", "-singlefile"]
                    + [entrada, imagem],
                    capture_output=True,
                    check=True,
                    timeout=max(fim - time.monotonic(), 0.001),
                )
                _desvirar(f"{imagem}.png", ambiente, fim)
                lida = _ler(imagem, ambiente, fim)
                if lida[1] < ILEGIVEL_ABAIXO_DE:
                    # O OSD erra o formulário impresso de cabeça para baixo e diz 0°:
                    # girado, ele passa de ilegível a legível. Fica a leitura melhor.
                    _girar(f"{imagem}.png", 180)
                    lida = max(lida, _ler(imagem, ambiente, fim), key=lambda par: par[1])
            except subprocess.TimeoutExpired:
                esgotado = True
            except (OSError, subprocess.SubprocessError):
                pass
            finally:
                for sufixo in (".png", ".txt", ".tsv"):
                    if os.path.exists(f"{imagem}{sufixo}"):
                        os.remove(f"{imagem}{sufixo}")
            # A segunda leitura que falha ou passa do prazo não apaga a primeira.
            if lida is not None:
                lidas[str(numero)] = {"texto": lida[0], "confianca": lida[1]}
            if esgotado:
                break
    return lidas


def _ler(base: str, ambiente: dict[str, str], fim: float) -> tuple[str, int]:
    """(texto, confiança) de `<base>.png`, numa passada só do `tesseract` com saída
    texto e TSV. A confiança é a média, de 0 a 100, das palavras de 4 letras ou
    mais: as curtas puxam a média para cima até no ruído. Sem palavra, zero."""
    import subprocess
    import time

    subprocess.run(
        ["tesseract", f"{base}.png", base, "-l", "por", "txt", "tsv"],
        capture_output=True,
        check=True,
        timeout=max(fim - time.monotonic(), 0.001),
        env=ambiente,
    )
    with open(f"{base}.txt", encoding="utf-8", errors="replace") as f:
        # O `tesseract` fecha a página com form feed, que no texto guardado abre página nova.
        texto = f.read().replace("\f", "").strip()
    confiancas = []
    with open(f"{base}.tsv", encoding="utf-8", errors="replace") as f:
        for linha in f.read().splitlines()[1:]:
            colunas = linha.split("\t")
            if len(colunas) == 12 and len(colunas[11]) >= 4 and float(colunas[10]) >= 0:
                confiancas.append(float(colunas[10]))
    return texto, round(sum(confiancas) / len(confiancas)) if confiancas else 0


def _desvirar(imagem: str, ambiente: dict[str, str], fim: float) -> None:
    """Gira a imagem para a posição de leitura quando o `tesseract --psm 0` diz que
    ela está virada: folha impressa digitalizada de cabeça para baixo sai lixo no
    OCR. O `--psm 1` faz o mesmo, mas só gira com confiança alta e deixa virada a
    página de pouca confiança. Sem resposta (página com pouca letra), fica como veio."""
    import re
    import subprocess
    import time

    osd = subprocess.run(
        ["tesseract", imagem, "stdout", "--psm", "0"],
        capture_output=True,
        timeout=max(fim - time.monotonic(), 0.001),
        env=ambiente,
    )
    giro = re.search(r"Rotate:\s*(90|180|270)\b", osd.stdout.decode("utf-8", errors="replace"))
    if osd.returncode != 0 or giro is None:
        return
    _girar(imagem, int(giro.group(1)))


def _girar(imagem: str, graus: int) -> None:
    """Gira a imagem `graus` no sentido horário, no lugar."""
    from PIL import Image

    with Image.open(imagem) as original:
        girada = original.rotate(-graus, expand=True)
        # Sem o DPI da rasterização, o `tesseract` supõe resolução baixa e lê pior.
        girada.info["dpi"] = original.info.get("dpi", (300, 300))
    girada.save(imagem, dpi=girada.info["dpi"])


def main(argv: list[str]) -> int:
    limite, entrada = int(argv[1]), argv[2]
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limite, resource.RLIM_INFINITY))
    except (ValueError, OSError, AttributeError):
        # No macOS o kernel recusa `RLIMIT_AS`; quem segura é o vigia do pai.
        print(f"RLIMIT_AS indisponivel em {sys.platform}: quem segura e o vigia do pai", file=sys.stderr)

    if len(argv) > 3 and argv[3] == "--ocr":
        lidas = ocr(entrada, [int(n) for n in argv[4].split(",") if n], float(argv[5]))
        sys.stdout.write(json.dumps(lidas, ensure_ascii=False))
        return 0

    if len(argv) > 3:
        try:
            lidas = palavras(entrada, {int(n) for n in argv[3].split(",") if n})
        except Exception as e:
            # Só o tipo: a mensagem do parser pode citar o conteúdo do arquivo, e o pai loga o stderr.
            print(f"pdfplumber falhou: {type(e).__name__}", file=sys.stderr)
            return 1
        sys.stdout.write(json.dumps(lidas, ensure_ascii=False))
        return 0

    try:
        os.execvp("pdftotext", ["pdftotext", "-layout", "-enc", "UTF-8", entrada, "-"])
    except OSError as e:
        print(f"pdftotext indisponivel: {e}", file=sys.stderr)
    return SAIDA_SEM_PDFTOTEXT


if __name__ == "__main__":
    sys.exit(main(sys.argv))
