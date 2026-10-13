"""Processo filho que lê as marcações de caixa e botão dos formulários (issue #1132).

No PDF do MV a marcação não está no texto: cada caixa e cada botão é uma imagem,
e há quatro desenhos (caixa vazia e marcada de 14 x 14 pixels, botão vazio e
marcado de 140 x 160). O que separa a marcada da vazia é a fração de pixels
escuros, medida pelo diretor nos desenhos do MV: caixa vazia 0,27 e marcada
0,39, botão vazio 0,48 e marcado 0,61. O limiar fica entre os dois.

O `pdfplumber` entrega as imagens e as palavras com posição, e o Pillow lê os
pixels; os dois já vinham com o app (o `pdfplumber` traz o Pillow), sem a
biblioteca AGPL da referência do diretor. A saída, em JSON, é por página: cada
linha visual que tem marcação, como a lista das palavras e das marcas (`[X]` ou
`[ ]`) na ordem da esquerda para a direita. Quem insere as marcas no texto do
`pdftotext` é o pai (`contas_medicas.marcacoes`).

Roda como script solto (`python -P contas_medicas_marcacoes_filho.py <limite>
<arquivo> <páginas>`), pelo mesmo motivo do `contas_medicas_extrator_filho`: o
parser lê arquivo que vem de fora, e quem morre na leitura hostil é o filho. O
topo é stdlib pura e o `pdfplumber` só é importado depois do `RLIMIT_AS`.

A saída tem texto do prontuário: o `stderr` leva só o tipo do erro.
"""

from __future__ import annotations

import json
import sys

# O filho bateu no teto de endereçamento. Sai por código, como no extrator de
# documentos: no instante do estouro, até a mensagem pode não caber.
SAIDA_SEM_MEMORIA = 97

# (largura, altura) da imagem em pixels -> limiar da fração de pixels escuros.
LIMIAR = {(14, 14): 0.33, (140, 160): 0.55}
# Byte abaixo disto conta como escuro, como na medição do diretor.
ESCURO = 100
# Distância máxima, em pontos, entre o centro vertical de dois itens da mesma linha.
MESMA_LINHA = 5

MARCADA = "[X]"
VAZIA = "[ ]"


def instalar_limite_de_enderecamento(limite_em_bytes: int) -> bool:
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (limite_em_bytes, resource.RLIM_INFINITY))
        return True
    except (ValueError, OSError, AttributeError):
        # No macOS o kernel recusa `RLIMIT_AS`; quem segura é o vigia do pai.
        return False


def fracao_escura(imagem: dict) -> float:
    """Fração de bytes escuros da imagem decodificada, contando todos os canais."""
    from io import BytesIO

    from PIL import Image

    stream = imagem["stream"]
    largura, altura = imagem["srcsize"]
    if any(getattr(nome, "name", nome) == "DCTDecode" for nome, _ in stream.get_filters()):
        figura = Image.open(BytesIO(stream.get_rawdata()))
    else:
        dados = stream.get_data()
        canais = len(dados) // (largura * altura) if imagem.get("bits") == 8 else 0
        modo = {1: "L", 3: "RGB", 4: "CMYK"}.get(canais)
        if modo:
            figura = Image.frombytes(modo, (largura, altura), dados[: largura * altura * canais])
        else:
            figura = Image.frombytes("1", (largura, altura), dados)
    if figura.mode not in ("L", "RGB"):
        figura = figura.convert("RGB")
    pixels = figura.tobytes()
    return sum(1 for byte in pixels if byte < ESCURO) / max(1, len(pixels))


def linhas_com_marcas(pagina) -> list[list[str]]:
    """As linhas visuais da página que têm caixa ou botão, palavra e marca em ordem."""
    marcas = []
    fracoes: dict[object, float] = {}
    for imagem in pagina.images:
        tamanho = tuple(imagem.get("srcsize") or ())
        if tamanho not in LIMIAR:
            continue
        objid = getattr(imagem["stream"], "objid", None) or id(imagem["stream"])
        if objid not in fracoes:
            try:
                fracoes[objid] = fracao_escura(imagem)
            except Exception:  # noqa: BLE001 - imagem que não decodifica fica sem marca, não derruba a página
                fracoes[objid] = -1.0
        if fracoes[objid] < 0:
            continue
        marca = MARCADA if fracoes[objid] > LIMIAR[tamanho] else VAZIA
        marcas.append((imagem["x0"], imagem["top"], imagem["bottom"], marca))
    if not marcas:
        return []

    palavras = sorted(
        ((p["x0"], (p["top"] + p["bottom"]) / 2, p["text"]) for p in pagina.extract_words()),
        key=lambda palavra: (palavra[1], palavra[0]),
    )
    linhas: list[list[tuple]] = []  # cada linha: [(x0, texto, é marca)]
    linha_da_palavra: list[int] = []
    centros: list[float] = []
    for x0, centro, texto in palavras:
        if not centros or abs(centro - centros[-1]) > MESMA_LINHA:
            linhas.append([])
            centros.append(centro)
        linhas[-1].append((x0, texto, False))
        linha_da_palavra.append(len(linhas) - 1)

    for x0, topo, base, marca in marcas:
        # A marca vai para a linha da opção, a palavra logo à direita dela. No MV o
        # botão fica uns pontos abaixo do rótulo da pergunta: pelo centro, ele caía
        # numa linha sem palavra nenhuma e a marcação se perdia.
        centro = (topo + base) / 2
        direita = [i for i, (px, pc, _) in enumerate(palavras) if px >= x0 and abs(pc - centro) <= MESMA_LINHA]
        if direita:
            destino = linha_da_palavra[min(direita, key=lambda i: palavras[i][0])]
        else:
            perto = [i for i, c in enumerate(centros) if abs(c - centro) <= MESMA_LINHA]
            if perto:
                destino = min(perto, key=lambda i: abs(centros[i] - centro))
            else:
                linhas.append([])
                centros.append(centro)
                destino = len(linhas) - 1
        linhas[destino].append((x0, marca, True))
    return [
        [texto for _, texto, _ in sorted(linha, key=lambda item: item[0])]
        for linha in linhas
        if any(e_marca for *_, e_marca in linha)
    ]


def marcacoes(caminho: str, paginas: list[int]) -> dict[str, list[list[str]]]:
    import pdfplumber

    saida: dict[str, list[list[str]]] = {}
    with pdfplumber.open(caminho) as pdf:
        for numero in paginas:
            if not 1 <= numero <= len(pdf.pages):
                continue
            pagina = pdf.pages[numero - 1]
            if linhas := linhas_com_marcas(pagina):
                saida[str(numero)] = linhas
            # Sem o `close`, o `pdfplumber` guarda os objetos de todas as páginas até o fim.
            pagina.close()
    return saida


def _faltou_memoria(erro: BaseException) -> bool:
    visto = set()
    atual: BaseException | None = erro
    while atual is not None and id(atual) not in visto:
        if isinstance(atual, MemoryError):
            return True
        visto.add(id(atual))
        atual = atual.__cause__ or atual.__context__
    return False


def main(argv: list[str]) -> int:
    limite, entrada = int(argv[1]), argv[2]
    paginas = [int(n) for n in argv[3].split(",") if n]
    if not instalar_limite_de_enderecamento(limite):
        print(f"RLIMIT_AS indisponivel em {sys.platform}: quem segura e o vigia do pai", file=sys.stderr)
    try:
        resultado = marcacoes(entrada, paginas)
    except Exception as e:  # noqa: BLE001 - o pai segue sem as marcações
        if _faltou_memoria(e):
            return SAIDA_SEM_MEMORIA
        print(type(e).__name__, file=sys.stderr)
        return 1
    sys.stdout.write(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
