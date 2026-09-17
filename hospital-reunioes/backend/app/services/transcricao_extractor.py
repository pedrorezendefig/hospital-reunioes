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
from concurrent.futures import ThreadPoolExecutor

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

# O teto do filho protege o filho. Este protege o PAI, na volta.
#
# Medido: um `.docx` de 326 KB devolve 100 MB de texto com pico de RSS que passa
# folgado pelo teto do filho, e esses 100 MB atravessariam inteiros para dentro
# do worker (mais o custo do `.decode()`), vezes o numero de vagas. Sem este
# numero, o isolamento protege a leitura e entrega a conta na porta de saida.
#
# 16 MB e dezesseis vezes o maior legitimo medido (o PDF honesto de 737 mil
# caracteres devolve 0,72 MB de texto; o `.docx` de 19 mil paragrafos devolve
# 0,80 MB, que e o maior) e fica na ordem de milhares de paginas, que nenhuma
# transcricao de reuniao nem material de POP alcanca.
TETO_DO_TEXTO_DEVOLVIDO = 16 * 1024 * 1024

# Todo canal de volta tem teto, e nao so o que devolve texto.
#
# O `stdout` ja tinha o numero acima, conferido pelo filho antes de escrever;
# estes dois sao o teto do CANAL, conferido pelo vigia no tamanho do arquivo, e
# valem inclusive para quem escreve no descritor por fora do Python.
#
# O `stderr` nao tinha numero nenhum, e isso era regressao contra a `main`: la o
# `logging` do app engolia os avisos do `pdfminer` (36 pontos so no
# `pdfinterp.py`, varios por operador dentro do laco do fluxo de conteudo), e
# aqui eles viravam bytes acumulados no worker. Medido: um `.pdf` de 306 KB com
# `"0 BMC "` repetido produz centenas de MB de aviso, com o filho parado.
#
# 4 MB de aviso e muito mais do que qualquer diagnostico util (o log guarda o
# rabo, nao o todo) e muito menos do que faz diferenca na memoria do worker.
TETO_DA_SAIDA_DO_FILHO = TETO_DO_TEXTO_DEVOLVIDO + 4096
TETO_DO_ERRO_DO_FILHO = 4 * 1024 * 1024
RABO_DO_ERRO_NO_LOG = 500

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

# Executor PROPRIO, para a extracao nao disputar thread com o resto do app.
#
# O `/health` (`app/routers/health.py`) roda no executor default com timeout de
# 2 s. Com a extracao tambem la, uma rajada de upload prendia as threads, o
# `/health` estourava, devolvia 503 e o `HEALTHCHECK` do Dockerfile declarava o
# container doente: a guarda que existe para nao derrubar o app o derrubava por
# outra porta.
#
# Sao mais threads que vagas de proposito. A thread que passa das vagas fica
# PARADA num semaforo, sem queimar CPU e por no maximo o prazo da fila, e e ela
# que entrega a `MENSAGEM_FILA_CHEIA`. Um executor do tamanho exato das vagas
# empurraria essa espera para a fila interna do executor, que nao tem prazo nem
# mensagem: a pessoa ficaria na ampulheta sem nunca saber por que.
_EXECUTOR_DE_EXTRACAO = ThreadPoolExecutor(
    max_workers=VAGAS_DE_EXTRACAO * 8,
    thread_name_prefix="extracao",
)

# Uma vaga so pode vagar quando a leitura em curso termina, e ela termina no
# maximo no `PRAZO_DA_EXTRACAO`. Esperar MENOS que isso recusa gente que teria
# sido atendida daqui a pouco, que e guarda-corpo virando indisponibilidade.
#
# Este numero ja foi 10 s, escolhido para encurtar o pior caso da requisicao, e
# o CI derrubou: na maquina de duas CPUs do runner, duas leituras honestas em
# paralelo passam de 10 s e a terceira pessoa levava recusa sem nada de errado
# no arquivo dela. O preco de acertar isso e o pior caso somado, espera mais
# leitura, e ele fica escrito aqui em vez de escondido.
PRAZO_DA_FILA = PRAZO_DA_EXTRACAO

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


def _tamanho(caminho: str) -> int:
    try:
        return os.path.getsize(caminho)
    except OSError:
        return 0


def _ler(caminho: str) -> bytes:
    """Le o arquivo inteiro, e so e chamado depois que o tamanho foi conferido.

    Nao tem teto proprio de proposito: teto aqui seria CORTE, e corte silencioso
    e o unico desfecho que nao aparece na tela de ninguem. Quem decide e a
    conferencia do tamanho, antes, e ela recusa em vez de cortar.
    """
    try:
        with open(caminho, "rb") as f:
            return f.read()
    except OSError:
        return b""


def _ler_cauda(caminho: str, quantos: int) -> str:
    """O fim do arquivo de erro, que e onde esta a falha que interessa."""
    try:
        with open(caminho, "rb") as f:
            f.seek(max(0, _tamanho(caminho) - quantos))
            return f.read(quantos).decode("utf-8", errors="replace")
    except OSError:
        return ""


def _acompanhar(proc: subprocess.Popen, saida: str, erro: str) -> str | None:
    """Espera o filho vigiando memoria, relogio e os DOIS canais de volta.

    Devolve o motivo da morte, ou None quando o filho terminou sozinho.

    O vigia mede o tamanho dos arquivos porque e ai que estao os canais: o que
    o filho escreve vai para disco, nao para a memoria deste processo. Isso e o
    que impede que o pai pague pelo que o filho produz. Um `communicate()` em
    `PIPE` faz o contrario: acumula tudo aqui dentro, sem teto, e foi assim que
    um PDF de 306 KB com aviso por operador fez o worker crescer 522 MB enquanto
    o filho ficava parado em 239 MB.
    """
    limite_do_relogio = time.monotonic() + PRAZO_DA_EXTRACAO
    while True:
        try:
            proc.wait(timeout=INTERVALO_DE_VIGIA)
            return None
        except subprocess.TimeoutExpired:
            pass

        rss = _rss_em_bytes(proc.pid)
        if rss is not None and rss > TETO_DE_MEMORIA_DO_FILHO:
            return _matar(proc, "memoria", rss)
        if _tamanho(saida) > TETO_DA_SAIDA_DO_FILHO:
            return _matar(proc, "saida", rss)
        if _tamanho(erro) > TETO_DO_ERRO_DO_FILHO:
            return _matar(proc, "ruido", rss)
        if time.monotonic() >= limite_do_relogio:
            return _matar(proc, "tempo", rss)


def _matar(proc: subprocess.Popen, motivo: str, rss: int | None) -> str:
    proc.kill()
    proc.wait()
    logger.warning(
        "Extracao isolada morta por %s (pid %s, RSS %s MB)",
        motivo,
        proc.pid,
        round(rss / (1024 * 1024)) if rss is not None else "?",
    )
    return motivo


def _ambiente_do_filho() -> dict[str, str]:
    """O ambiente minimo que o parser precisa, e nada alem disso.

    O filho abre o arquivo hostil. Herdar `os.environ` inteiro entrega a ele
    `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `CLICKSIGN_API_KEY`,
    `RESEND_API_KEY` e companhia, e o canal de volta dele vira TEXTO EXTRAIDO na
    tela de quem subiu o arquivo: exfiltrar nao precisaria nem de rede. O parser
    nao usa nenhuma dessas chaves.

    A lista e de permissao, e nao de bloqueio, porque bloqueio esquece a chave
    que nasce amanha.
    """
    permitidas = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR", "TEMP", "TMP")
    ambiente = {nome: os.environ[nome] for nome in permitidas if nome in os.environ}
    ambiente.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    return ambiente


def _extrair_isolado(ext: str, file_bytes: bytes) -> str:
    """Le o arquivo num processo separado, com teto de memoria, prazo e canais.

    Tudo vai por disco e nao por `pipe` de proposito. Na entrada, porque com os
    dois lados escrevendo em pipe um trava esperando o outro e o vigia nunca
    rodaria. Na volta, porque `pipe` mais `communicate()` significa acumular no
    worker, sem teto, exatamente o que a fatia existe para impedir.
    """
    if not _vagas.acquire(timeout=PRAZO_DA_FILA):
        logger.warning("Extracao isolada sem vaga apos %ss lendo %s", PRAZO_DA_FILA, ext)
        raise ValueError(MENSAGEM_FILA_CHEIA)

    try:
        with tempfile.TemporaryDirectory(prefix="extracao-") as pasta:
            entrada = os.path.join(pasta, f"entrada{ext}")
            saida = os.path.join(pasta, "saida")
            erro = os.path.join(pasta, "erro")
            with open(entrada, "wb") as f:
                f.write(file_bytes)

            with open(saida, "wb") as f_saida, open(erro, "wb") as f_erro:
                proc = subprocess.Popen(
                    # `-P` tira o diretorio do script do `sys.path`. Sem ele, o
                    # filho nasce com `app/services/` na frente do site-packages,
                    # e os modulos do projeto disputariam nome com qualquer
                    # import da cadeia do parser.
                    [
                        sys.executable,
                        "-P",
                        _CAMINHO_DO_FILHO,
                        ext,
                        entrada,
                        str(LIMITE_DE_ENDERECAMENTO),
                        str(TETO_DO_TEXTO_DEVOLVIDO),
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=f_saida,
                    stderr=f_erro,
                    env=_ambiente_do_filho(),
                )
                motivo = _acompanhar(proc, saida, erro)

            if motivo is None and _tamanho(saida) > TETO_DA_SAIDA_DO_FILHO:
                # O filho despejou e SAIU entre duas amostras do vigia, entao o
                # vigia nunca o viu. Cortar aqui e devolver 200 seria pior que
                # recusar: a Ata ou a Demanda nasceria de um texto incompleto
                # que parece completo, e ninguem seria avisado. Documento que
                # volta pela metade em silencio e o unico desfecho que nao
                # aparece na tela de ninguem.
                motivo = "saida"
            bruto = b"" if motivo is not None else _ler(saida)
            diagnostico = _ler_cauda(erro, RABO_DO_ERRO_NO_LOG)
    finally:
        # A gravacao do temporario fica DENTRO do try: com disco cheio ela
        # levanta, e uma vaga que nao volta e pior que o erro que a prendeu.
        # Duas vagas presas param a leitura de documento para sempre, sem log
        # novo e sem jeito de reabrir a nao ser reiniciando o container.
        _vagas.release()

    if motivo is not None:
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    if proc.returncode == filho.SAIDA_SEM_MEMORIA:
        logger.warning("Extracao isolada bateu no RLIMIT_AS lendo %s", ext)
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    if proc.returncode == filho.SAIDA_TEXTO_GRANDE_DEMAIS:
        logger.warning("Extracao isolada devolveria texto acima do teto lendo %s", ext)
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    if proc.returncode is not None and proc.returncode < 0:
        # Codigo negativo e sinal: o filho foi MORTO, nao terminou. Quem mata
        # sem avisar e o OOM killer do cgroup (container com menos memoria que
        # o `RLIMIT_AS`) ou o kernel numa alocacao unica entre duas amostras do
        # vigia. Culpar o arquivo aqui seria repetir, por outra porta, o defeito
        # do `MemoryError` que o `pdfminer` embrulha: mandar a pessoa conferir
        # um arquivo que nao tem nada de errado.
        logger.warning("Extracao isolada morta pelo sinal %s lendo %s", -proc.returncode, ext)
        raise ValueError(MENSAGEM_GRANDE_DEMAIS)

    cabecalho, _, corpo = bruto.partition(b"\n")
    status = cabecalho.decode("ascii", errors="replace")

    if proc.returncode == 0 and status == filho.STATUS_OK:
        return corpo.decode("utf-8", errors="replace")

    if proc.returncode == 0 and status == filho.STATUS_RECUSA:
        raise ValueError(corpo.decode("utf-8", errors="replace"))

    logger.error(
        "Extracao isolada de %s falhou (codigo %s): %s",
        ext,
        proc.returncode,
        diagnostico,
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
    """Mesma extracao, sem prender o event loop nem o executor de todo mundo.

    As rotas que chamam isto sao `async def`, e ate a #758 a leitura acontecia
    dentro do loop: um PDF de 25 segundos congelava a aplicacao inteira mesmo
    sem estourar memoria. O timeout tinha sido recusado no PR #751 com razao,
    porque `asyncio.wait_for` sobre `to_thread` nao cancela a thread e ela segue
    queimando CPU no executor compartilhado. Aqui a thread nao queima nada: ela
    espera o filho e, no prazo, MATA o processo que queima.

    O `to_thread`, porem, usa o executor DEFAULT, que e o mesmo do `/health`
    (`app/routers/health.py`, com timeout de 2 s). Uma rajada de upload prendia
    threads de la e o `/health` estourava, devolvendo 503 e fazendo o
    `HEALTHCHECK` do Dockerfile declarar o container doente: a guarda que existe
    para nao derrubar o app derrubava o app por outra porta. Por isso a extracao
    tem executor PROPRIO, e ninguem mais divide thread com ela. Ele e MAIOR que
    o numero de vagas de proposito: quem passa das vagas fica parado no semaforo
    e e assim que ouve a `MENSAGEM_FILA_CHEIA`. O porque do tamanho esta na
    definicao do executor.
    """
    laco = asyncio.get_running_loop()
    return await laco.run_in_executor(_EXECUTOR_DE_EXTRACAO, extrair_texto, filename, file_bytes)
