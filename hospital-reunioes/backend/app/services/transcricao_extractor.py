"""
Extrator de texto de transcricoes em multiplos formatos.

Aceita .txt, .md, .pdf e .docx. Rejeita .doc legado e PDFs escaneados sem OCR.
Usado pelos endpoints /anexar-transcricao e /upload-transcricao para normalizar
o input antes de mandar para a IA gerar a ata, e tambem pela Ata Guiada e pelos
materiais de referencia dos POPs.

## Por que o parser nao roda aqui dentro (issue #758)

O arquivo chega de fora do hospital por desenho: basta mandar por e-mail para
alguem que anexe. O uvicorn sobe com **um worker** servindo o app inteiro, entao
uma extracao que esgota memoria ou queima CPU derruba junto a Ouvidoria publica,
as Reunioes, as Atas e os POPs.

As quatro rodadas de revisao do PR #751 tentaram fechar isso filtro a filtro
dentro deste processo, e cada rodada fechava um e a seguinte achava o proximo
(`/FlateDecode`, depois `/LZWDecode`, depois `/ASCII85Decode`, depois o `.docx`
por membro isca). Aqui a aposta e outra: em vez de triar filtro por filtro, todo
formato que precisa de **parser** roda num processo separado, com teto de
memoria e prazo. O que estoura o orcamento mata o filho, e o worker nem sente.
Filtro que ninguem triou esta coberto pelo mesmo teto.

Quem fica de fora do isolamento e so quem nao tem parser: `.txt` e `.md` sao
decodificacao de bytes com limite de entrada ja aplicado, sem amplificacao
possivel. Qualquer formato novo nasce isolado, porque o caminho em processo e
uma lista fechada e nao o caso padrao.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time

from app.services import transcricao_extractor_filho as filho

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_BYTES_TEXT = 5 * 1024 * 1024
MAX_BYTES_BINARY = 15 * 1024 * 1024
MIN_PDF_TEXT_BYTES = filho.MIN_PDF_TEXT_BYTES

# Unicos formatos que nao precisam de processo separado: viram texto por
# `bytes.decode`, cujo custo e multiplo fixo do arquivo de entrada. Tirar um
# formato daqui e barato; POR um formato aqui exige provar que ele nao tem
# parser nenhum no caminho.
FORMATOS_DE_TEXTO_PURO = {".txt", ".md"}

CONTENT_TYPE_BY_EXT = {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# ─── Orcamento do processo filho ────────────────────────────────────────────
#
# Os numeros vem de medicao, nao de chute (todos com o `page.close()` do filho
# em vigor, que e o que torna possivel existir um teto):
#
#   | arquivo                                  | tempo  | pico de RSS |
#   |------------------------------------------|--------|-------------|
#   | PDF honesto, 234 KB, 737 mil caracteres  |  7,5 s |     51 MB   |
#   | .docx honesto, 19 mil paragrafos         |  0,1 s |     51 MB   |
#   | PDF /FlateDecode + /ASCII85Decode, 17 KB | 29,1 s |  1.584 MB   |
#   | .docx com membro isca, XML de 60 MB      |  ~2 s  |    ~900 MB  |
#
# O teto de RSS fica 10x acima do pior legitimo medido e bem abaixo das duas
# bombas. O prazo e folgado de proposito: ele nao e quem pega as bombas de
# memoria (essas morrem em segundos pelo teto de RSS), e sim a rede para o
# ataque que queima CPU dentro do orcamento de memoria.
TETO_DE_MEMORIA_DO_FILHO = 512 * 1024 * 1024
PRAZO_DA_EXTRACAO = 45.0
INTERVALO_DE_VIGIA = 0.25

# `RLIMIT_AS` limita ESPACO DE ENDERECAMENTO, que e sempre maior que o RSS
# (bibliotecas mapeadas, arenas do alocador, pilhas de thread). Por isso ele
# fica acima do teto de RSS: quem decide primeiro no caso normal e o vigia, e o
# `RLIMIT_AS` e a rede para a alocacao unica e enorme que acontece entre duas
# amostras do vigia (um `zlib.decompress` de gigabytes numa chamada so).
LIMITE_DE_ENDERECAMENTO = 1280 * 1024 * 1024

# Teto por filho nao e teto da maquina: N uploads simultaneos sao N filhos. O
# `@limiter.limit` das rotas conta requisicoes POR MINUTO, e nao ao mesmo tempo,
# entao dez uploads disparados juntos passam pelos "5/minute" e multiplicariam
# o orcamento por dez. Com duas vagas o pior caso da extracao fica em 1 GB, que
# e numero que se confere contra a memoria do container.
#
# Duas e folgado para o uso real (a extracao honesta mais cara medida leva 7,5 s,
# e a de `.docx` 0,1 s): a terceira pessoa ESPERA uma vaga, nao leva recusa, e so
# ouve "estou lendo outros documentos" se a fila nao andar dentro do prazo.
VAGAS_DE_EXTRACAO = 2
_vagas = threading.BoundedSemaphore(VAGAS_DE_EXTRACAO)

# Esperar na fila e esperar a leitura sao coisas diferentes, e por isso o
# orcamento e outro. Se a fila usasse o prazo da extracao, o pior caso de uma
# requisicao seria 45 s de espera mais 45 s de leitura: um minuto e meio de
# ampulheta, sem nada na tela explicando. Dez segundos cobrem duas rodadas de
# `.docx` honesto e deixam o pior caso inteiro em 55 s.
PRAZO_DA_FILA = 10.0

MENSAGEM_FILA_CHEIA = (
    "O sistema está lendo outros documentos neste momento e não conseguiu uma vaga "
    "para o seu. Tente de novo em instantes."
)

MENSAGEM_GRANDE_DEMAIS = (
    "Este arquivo é grande ou complexo demais para ser lido. Não é defeito no arquivo: "
    "a leitura foi interrompida antes de comprometer o sistema. Envie a transcrição em "
    ".txt, ou divida o documento em partes menores."
)

_CAMINHO_DO_FILHO = os.path.abspath(filho.__file__)


def _normalizar_extensao(filename: str) -> str:
    _, ext = os.path.splitext(filename or "")
    return ext.lower()


def _rss_em_bytes(pid: int) -> int | None:
    """RSS do processo `pid`, ou None quando nao da para saber.

    No Linux le `/proc`, que e barato. Fora dele cai no `ps`, que e o que existe
    no macOS da maquina de desenvolvimento (onde `RLIMIT_AS` nao funciona e este
    vigia e a unica guarda de memoria).
    """
    caminho = f"/proc/{pid}/statm"
    try:
        if os.path.exists(caminho):
            with open(caminho) as f:
                residentes = int(f.read().split()[1])
            return residentes * os.sysconf("SC_PAGE_SIZE")
        saida = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            capture_output=True,
            timeout=5,
        )
        bruto = saida.stdout.decode().strip()
        return int(bruto) * 1024 if bruto else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def _acompanhar(proc: subprocess.Popen) -> tuple[str | None, bytes, bytes]:
    """Espera o filho vigiando memoria e relogio.

    Devolve (motivo_da_morte, stdout, stderr). `motivo_da_morte` e None quando o
    filho terminou sozinho.
    """
    limite_do_relogio = time.monotonic() + PRAZO_DA_EXTRACAO
    while True:
        try:
            saida, erro = proc.communicate(timeout=INTERVALO_DE_VIGIA)
            return None, saida, erro
        except subprocess.TimeoutExpired:
            pass

        rss = _rss_em_bytes(proc.pid)
        if rss is not None and rss > TETO_DE_MEMORIA_DO_FILHO:
            return _matar(proc, "memoria", rss)
        if time.monotonic() >= limite_do_relogio:
            return _matar(proc, "tempo", rss)


def _matar(proc: subprocess.Popen, motivo: str, rss: int | None) -> tuple[str, bytes, bytes]:
    proc.kill()
    saida, erro = proc.communicate()
    logger.warning(
        "Extracao isolada morta por %s (pid %s, RSS %s MB)",
        motivo,
        proc.pid,
        round(rss / (1024 * 1024)) if rss is not None else "?",
    )
    return motivo, saida, erro


def _extrair_isolado(ext: str, file_bytes: bytes) -> str:
    """Le o arquivo num processo separado, com teto de memoria e prazo.

    O arquivo vai por disco e nao por `stdin` de proposito: com os dois lados
    escrevendo em pipe (o pai mandando 15 MB, o filho devolvendo o texto) um
    trava esperando o outro, e o vigia nunca chegaria a rodar.
    """
    if not _vagas.acquire(timeout=PRAZO_DA_FILA):
        logger.warning("Extracao isolada sem vaga apos %ss lendo %s", PRAZO_DA_FILA, ext)
        raise ValueError(MENSAGEM_FILA_CHEIA)

    caminho: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            caminho = tmp.name

        proc = subprocess.Popen(
            [sys.executable, _CAMINHO_DO_FILHO, ext, caminho, str(LIMITE_DE_ENDERECAMENTO)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        motivo, saida, erro = _acompanhar(proc)
    finally:
        # A gravacao do temporario fica DENTRO do try: com disco cheio ela
        # levanta, e uma vaga que nao volta e pior que o erro que a prendeu.
        # Duas vagas presas param a leitura de documento para sempre, sem log
        # novo e sem jeito de reabrir a nao ser reiniciando o container.
        _vagas.release()
        if caminho is not None:
            try:
                os.unlink(caminho)
            except OSError:
                pass

    if motivo is not None:
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    if proc.returncode == filho.SAIDA_SEM_MEMORIA:
        logger.warning("Extracao isolada bateu no RLIMIT_AS lendo %s", ext)
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    cabecalho, _, corpo = saida.partition(b"\n")
    status = cabecalho.decode("ascii", errors="replace")

    if proc.returncode == 0 and status == filho.STATUS_OK:
        return corpo.decode("utf-8", errors="replace")

    if proc.returncode == 0 and status == filho.STATUS_RECUSA:
        raise ValueError(corpo.decode("utf-8", errors="replace"))

    logger.error(
        "Extracao isolada de %s falhou (codigo %s): %s",
        ext,
        proc.returncode,
        erro.decode("utf-8", errors="replace")[-500:],
    )
    raise ValueError(f"Nao foi possivel ler o arquivo {ext}. Verifique se nao esta corrompido.")


def extrair_texto(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """
    Extrai texto plano UTF-8 de uma transcricao em txt/md/pdf/docx.

    Retorna (texto, extensao_normalizada). Levanta ValueError com mensagem
    em pt-BR pronta para virar HTTPException(422).
    """
    if not filename:
        raise ValueError("Arquivo sem nome. Anexe novamente.")

    ext = _normalizar_extensao(filename)

    if ext == ".doc":
        raise ValueError("Formato .doc nao suportado. Salve como .docx ou PDF antes de enviar.")

    if ext not in SUPPORTED_EXTENSIONS:
        aceitos = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(f"Formato nao suportado. Aceitos: {aceitos}.")

    tamanho = len(file_bytes)
    if ext in FORMATOS_DE_TEXTO_PURO:
        if tamanho > MAX_BYTES_TEXT:
            raise ValueError(f"Arquivo de texto excede o limite de {MAX_BYTES_TEXT // (1024 * 1024)} MB.")
    else:
        if tamanho > MAX_BYTES_BINARY:
            raise ValueError(f"Arquivo excede o limite de {MAX_BYTES_BINARY // (1024 * 1024)} MB.")

    if tamanho == 0:
        raise ValueError("Arquivo vazio. Anexe um arquivo com conteudo.")

    try:
        if ext in FORMATOS_DE_TEXTO_PURO:
            texto = file_bytes.decode("utf-8", errors="replace").strip()
        else:
            texto = _extrair_isolado(ext, file_bytes)
    except ValueError:
        raise
    except Exception as e:
        logger.exception(f"Falha ao extrair texto de {filename} ({ext}): {e}")
        raise ValueError(f"Nao foi possivel ler o arquivo {ext}. Verifique se nao esta corrompido.") from e

    if not texto.strip():
        raise ValueError("Nao foi possivel extrair texto do arquivo. Verifique o conteudo.")

    return texto, ext


async def extrair_texto_async(filename: str, file_bytes: bytes) -> tuple[str, str]:
    """Mesma extracao, sem prender o event loop do unico worker.

    As rotas que chamam isto sao `async def`, e ate a #758 a leitura acontecia
    dentro do loop: um PDF de 25 segundos congelava a aplicacao inteira mesmo
    sem estourar memoria. O timeout tinha sido recusado no PR #751 com razao,
    porque `asyncio.wait_for` sobre `to_thread` nao cancela a thread e ela segue
    queimando CPU no executor compartilhado. Aqui a thread nao queima nada: ela
    espera um `pipe` e, no prazo, MATA o processo que queima. E por isso que
    mandar para thread so ficou seguro depois do isolamento.
    """
    return await asyncio.to_thread(extrair_texto, filename, file_bytes)
