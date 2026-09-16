"""Extração de documento isolada em processo (issue #758).

O que estes testes cobram, e por que cada um existe:

O `.pdf` e o `.docx` chegam de fora do hospital por desenho, e o uvicorn serve o
app inteiro com **um worker**. As quatro rodadas de revisão do PR #751 tentaram
fechar isso filtro a filtro dentro do worker, e cada rodada fechava um e a
seguinte achava o próximo. Os dois ataques que sobraram medidos estão aqui como
arquivo de verdade, montados byte a byte:

  * `_pdf_ascii85_em_cima_do_flate`: `/Filter[/FlateDecode/ASCII85Decode]`.
    O atalho `z` do ASCII85 faz um caractere virar quatro bytes, e o
    `base64.a85decode` monta uma lista de pedaços antes do `join`. Medido sem
    proteção: 17.933 bytes de arquivo, 29,1 s e pico de 1.584 MB.
  * `_docx_com_membro_isca`: o primeiro membro do zip tem CRC-32 corrompido de
    propósito. É a isca que desarmava a conferência do PR #751, onde o `except`
    embrulhava o laço e não o membro. Atrás dela vem a bomba de XML.

E o par que importa tanto quanto: entrada legítima não pode morder. O PDF
honesto de ~740 mil caracteres e o `.docx` de 19 mil parágrafos atravessam.

Os testes batem na **rota** (`POST /api/reunioes/{id}/ata-guiada/extrair-documento`),
que é um consumidor real do extrator e não dispara pipeline nem storage. Testar
a função em vez da rota já deixou passar furo neste PRD.
"""

from __future__ import annotations

import asyncio
import io
import os
import resource
import struct
import subprocess
import sys
import time
import zipfile
import zlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import transcricao_extractor as extrator  # noqa: E402

# ─── Harness mínimo da rota ──────────────────────────────────────────────────


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def select(self, *_a, **_kw):
        return self

    def update(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def execute(self):
        return _Result(self._rows)


class _SupabaseFake:
    def __init__(self, rows):
        self._rows = rows

    def table(self, _nome):
        return _Query(self._rows)


@pytest.fixture(autouse=True)
def _zerar_rate_limiter():
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture
def app(monkeypatch) -> FastAPI:
    app = FastAPI()
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")

    sb = _SupabaseFake([{"id_reuniao": "R1", "status_ata": "PROGRAMADA", "tipo": "Gerencial"}])
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "facilitador@hospital.com"}
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _participante(*_a, **_kw):
        return {"id": "p1", "nome": "Facilitador", "cargo": "Diretor"}

    async def _permitidas(*_a, **_kw):
        return None

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _permitidas)
    monkeypatch.setattr(reunioes_router, "is_secretaria", lambda _me: False)

    return app


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


def _enviar(client: TestClient, nome: str, dados: bytes):
    return client.post(
        "/api/reunioes/R1/ata-guiada/extrair-documento",
        files={"file": (nome, dados, "application/octet-stream")},
    )


# ─── Os dois ataques medidos, montados byte a byte ───────────────────────────


def _pdf_ascii85_em_cima_do_flate(megabytes_de_z: int = 17) -> bytes:
    """PDF cujo stream é zlib de N MB de 'z', com /Filter[/FlateDecode/ASCII85Decode].

    O pdfminer aplica os filtros na ordem do array, e quem escreve o PDF escolhe
    a ordem: o Flate devolve N MB de 'z', e cada 'z' vira quatro bytes no ASCII85.
    """
    return _montar_pdf(
        zlib.compress(b"z" * (megabytes_de_z * 1024 * 1024), 9),
        b"/Filter [/FlateDecode /ASCII85Decode]",
    )


def _pdf_sem_texto() -> bytes:
    """PDF válido cuja página só desenha uma linha. É o caso do escaneado sem OCR."""
    return _montar_pdf(b"0 0 m 100 100 l S", b"")


def _montar_pdf(stream: bytes, filtros: bytes) -> bytes:
    bruto = stream
    objs = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Length "
        + str(len(bruto)).encode()
        + b" "
        + filtros
        + b" >>\nstream\n"
        + bruto
        + b"\nendstream\nendobj\n",
        b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
    ]
    saida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for o in objs:
        offsets.append(len(saida))
        saida += o
    inicio_xref = len(saida)
    saida += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n0000000000 65535 f \n"
    for off in offsets:
        saida += f"{off:010d} 00000 n \n".encode()
    saida += (
        b"trailer\n<< /Size "
        + str(len(objs) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(inicio_xref).encode()
        + b"\n%%EOF\n"
    )
    return bytes(saida)


def _corromper_crc(zip_bytes: bytes, nome: bytes) -> bytes:
    """Estraga o CRC-32 de `nome` no header local e no diretório central."""
    dados = bytearray(zip_bytes)
    pos = dados.find(b"PK\x03\x04")
    while pos != -1:
        n = struct.unpack("<H", dados[pos + 26 : pos + 28])[0]
        if bytes(dados[pos + 30 : pos + 30 + n]) == nome:
            dados[pos + 14 : pos + 18] = b"\xde\xad\xbe\xef"
            break
        pos = dados.find(b"PK\x03\x04", pos + 1)
    pos = dados.find(b"PK\x01\x02")
    while pos != -1:
        n = struct.unpack("<H", dados[pos + 28 : pos + 30])[0]
        if bytes(dados[pos + 46 : pos + 46 + n]) == nome:
            dados[pos + 16 : pos + 20] = b"\xde\xad\xbe\xef"
            break
        pos = dados.find(b"PK\x01\x02", pos + 1)
    return bytes(dados)


def _docx_com_membro_isca(megabytes_de_xml: int = 60) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("docProps/app.xml", b"<Properties/>")  # a isca vem primeiro
        bomba = (
            b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            b'wordprocessingml/2006/main"><w:body>'
            + b"<w:p><w:r><w:t>a</w:t></w:r></w:p>" * (megabytes_de_xml * 1024 * 1024 // 34)
            + b"</w:body></w:document>"
        )
        z.writestr("word/document.xml", bomba)
        z.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
    return _corromper_crc(buf.getvalue(), b"docProps/app.xml")


# ─── Os pares de presença, também arquivo de verdade ─────────────────────────


def _docx_de_muito_texto(megabytes: int = 20) -> bytes:
    """`.docx` honesto na estrutura e enorme na saída: 65 KB viram 20 MB de texto.

    Não é bomba de memória: o filho lê isto com pico de 143 MB, folgado dentro
    do teto dele. O dano seria na VOLTA, com os 20 MB atravessando inteiros para
    dentro do worker. Escalando o mesmo arquivo, 326 KB devolvem 100 MB.
    """
    bloco = ("texto corrido de uma ata muito longa do hospital. " * 200).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b"<Types/>")
        corpo = b"".join(
            b"<w:p><w:r><w:t>" + bloco + b"</w:t></w:r></w:p>" for _ in range(megabytes * 1024 * 1024 // len(bloco))
        )
        z.writestr(
            "word/document.xml",
            b'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            b"<w:body>" + corpo + b"</w:body></w:document>",
        )
    return buf.getvalue()


def _pdf_honesto(paragrafos: int = 6000) -> bytes:
    from weasyprint import HTML

    corpo = "".join(
        f"<p>Paragrafo {i}: a equipe combinou revisar o indicador de espera e "
        f"levar o numero na proxima reuniao gerencial do hospital.</p>"
        for i in range(paragrafos)
    )
    return HTML(string=f"<html><body>{corpo}</body></html>").write_pdf()


def _docx_honesto(paragrafos: int = 19000) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        corpo = b"".join(
            b"<w:p><w:r><w:t>Paragrafo " + str(i).encode() + b" da ata honesta do hospital.</w:t></w:r></w:p>"
            for i in range(paragrafos)
        )
        z.writestr(
            "word/document.xml",
            b'<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/'
            b'wordprocessingml/2006/main"><w:body>' + corpo + b"</w:body></w:document>",
        )
    return buf.getvalue()


@pytest.fixture(scope="module")
def pdf_ataque() -> bytes:
    return _pdf_ascii85_em_cima_do_flate()


@pytest.fixture(scope="module")
def docx_ataque() -> bytes:
    return _docx_com_membro_isca()


@pytest.fixture(scope="module")
def pdf_honesto() -> bytes:
    return _pdf_honesto()


@pytest.fixture(scope="module")
def docx_honesto() -> bytes:
    return _docx_honesto()


def _plataforma_aplica_rlimit_as() -> bool:
    """O macOS recusa `setrlimit(RLIMIT_AS)` com EINVAL para qualquer valor.

    A decisão é da PLATAFORMA e não da nossa função de propósito. Perguntar a
    `instalar_limite_de_enderecamento` daria ao código sob teste o poder de
    desligar o próprio teste: um `return True` sem `setrlimit` nenhum passaria
    pela guarda, e um `return False` mandaria o pytest pular. Aqui o Linux
    (que é onde o app roda, e onde o CI roda) nunca pula.
    """
    return sys.platform.startswith("linux")


def _rss_do_worker_em_bytes() -> int:
    """Pico de RSS DESTE processo, que no app é o worker do uvicorn."""
    bruto = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return bruto if sys.platform == "darwin" else bruto * 1024


# ═══════════════════════════════════════════════════════════════════════════
# 1. Os dois ataques medidos não derrubam nem travam o worker
# ═══════════════════════════════════════════════════════════════════════════


class TestOsDoisAtaquesMedidos:
    def test_pdf_ascii85_em_cima_do_flate_e_recusado_sem_tocar_o_worker(self, client, pdf_ataque):
        """Sem isolamento este arquivo custa 29 s e 1.584 MB DENTRO do worker.

        Cobra as três coisas de uma vez: a recusa acontece, o pico do worker fica
        onde estava (a memória nunca entrou aqui) e o tempo fica na casa do teto
        de memória, não na dos 29 s.
        """
        assert len(pdf_ataque) < 100 * 1024, "o ataque cabe folgado no limite de upload"

        pico_antes = _rss_do_worker_em_bytes()
        t0 = time.monotonic()
        r = _enviar(client, "orcamento.pdf", pdf_ataque)
        decorrido = time.monotonic() - t0
        crescimento = _rss_do_worker_em_bytes() - pico_antes

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS
        assert crescimento < 200 * 1024 * 1024, (
            f"o worker cresceu {crescimento // (1024 * 1024)} MB: a extracao nao foi isolada"
        )
        assert decorrido < extrator.PRAZO_DA_EXTRACAO, "o teto de memoria tem que morder antes do prazo"

    def test_docx_com_membro_isca_e_recusado_sem_tocar_o_worker(self, client, docx_ataque):
        """A isca de CRC no primeiro membro não ajuda mais: não há conferência
        de zip para desarmar, o orçamento é do processo inteiro."""
        assert len(docx_ataque) < 1024 * 1024, "a bomba de XML cabe em menos de 1 MB no disco"

        pico_antes = _rss_do_worker_em_bytes()
        r = _enviar(client, "proposta.docx", docx_ataque)
        crescimento = _rss_do_worker_em_bytes() - pico_antes

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS
        assert crescimento < 200 * 1024 * 1024, (
            f"o worker cresceu {crescimento // (1024 * 1024)} MB: a extracao nao foi isolada"
        )

    async def test_o_resto_do_app_responde_durante_uma_extracao_longa(self, app, pdf_honesto):
        """O worker é um só, e o event loop dele não pode ficar preso na leitura.

        Até esta fatia as quatro rotas chamavam o extrator DENTRO do loop: um PDF
        de 7,5 s congelava a Ouvidoria pública, as Reuniões, as Atas e os POPs por
        7,5 s mesmo sem estourar memória nenhuma. Aqui o PDF honesto (que leva os
        mesmos 7,5 s) roda no filho enquanto outra requisição entra e sai.
        """
        import httpx

        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as ac:
            rota = "/api/reunioes/R1/ata-guiada/extrair-documento"
            lenta = asyncio.create_task(
                ac.post(rota, files={"file": ("ata-longa.pdf", pdf_honesto, "application/pdf")})
            )
            await asyncio.sleep(1.0)  # a extracao longa ja esta em andamento
            assert not lenta.done(), "o PDF honesto tinha que estar sendo lido ainda"

            t0 = time.monotonic()
            rapida = await ac.post(rota, files={"file": ("bilhete.txt", b"Anotacao curta da reuniao.")})
            espera = time.monotonic() - t0

            assert rapida.status_code == 200
            assert espera < 2.0, f"a requisicao curta esperou {espera:.1f}s pela longa"
            assert (await lenta).status_code == 200

    def test_o_texto_devolvido_tambem_tem_teto(self, client):
        """O terceiro caminho, que nenhum dos dois ataques acima usa.

        O teto do filho protege o filho. Um `.docx` de 65 KB devolve 20 MB de
        texto com pico de 143 MB, folgado DENTRO do teto: a leitura não é o
        problema, a volta é. Sem teto de saída o isolamento protegeria a leitura
        e entregaria a conta na porta, vezes o número de vagas.
        """
        gordo = _docx_de_muito_texto(20)
        assert len(gordo) < 200 * 1024, "o arquivo em si e pequeno, o texto e que e enorme"

        pico_antes = _rss_do_worker_em_bytes()
        r = _enviar(client, "ata-gorda.docx", gordo)
        crescimento = _rss_do_worker_em_bytes() - pico_antes

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS
        assert crescimento < 40 * 1024 * 1024, (
            f"o worker cresceu {crescimento // (1024 * 1024)} MB: o texto entrou assim mesmo"
        )

    def test_worker_continua_atendendo_depois_dos_dois_ataques(self, client, pdf_ataque, docx_ataque):
        """O ponto da fatia em uma frase: quem morre é o filho.

        Depois dos dois ataques na sequência, a mesma aplicação responde na rota
        seguinte. Sem isolamento, é aqui que a Ouvidoria pública teria parado.
        """
        _enviar(client, "orcamento.pdf", pdf_ataque)
        _enviar(client, "proposta.docx", docx_ataque)

        r = _enviar(client, "depois.txt", b"A reuniao seguiu normalmente apos os dois anexos.")
        assert r.status_code == 200
        assert "seguiu normalmente" in r.json()["texto"]


# ═══════════════════════════════════════════════════════════════════════════
# 2. O par de presença: entrada legítima não morde
# ═══════════════════════════════════════════════════════════════════════════


class TestEntradaLegitimaAtravessa:
    def test_pdf_honesto_grande_atravessa_inteiro(self, client, pdf_honesto):
        """O PDF honesto de centenas de páginas continua passando, e passa
        INTEIRO: o número de caracteres é o mesmo de antes do isolamento."""
        r = _enviar(client, "ata-longa.pdf", pdf_honesto)

        assert r.status_code == 200, r.text
        texto = r.json()["texto"]
        assert len(texto) > 700_000, f"so vieram {len(texto)} caracteres"
        assert "Paragrafo 5999" in texto, "o fim do documento tem que chegar junto"

    def test_docx_honesto_de_19_mil_paragrafos_atravessa(self, client, docx_honesto):
        r = _enviar(client, "ata-longa.docx", docx_honesto)

        assert r.status_code == 200, r.text
        texto = r.json()["texto"]
        assert "Paragrafo 18999" in texto

    def test_pdf_honesto_cabe_folgado_no_teto_de_memoria(self, pdf_honesto):
        """A folga entre o legítimo e o teto é o que separa guarda de indisponibilidade.

        Sem o `page.close()` do filho o MESMO arquivo custa 1.465 MB e passaria a
        ser recusado como se fosse bomba. Este teste mede o pico do filho de
        verdade e exige folga de pelo menos 4x.
        """
        pico = _pico_do_filho(".pdf", pdf_honesto)

        assert pico * 4 < extrator.TETO_DE_MEMORIA_DO_FILHO, (
            f"o PDF honesto custa {pico // (1024 * 1024)} MB contra um teto de "
            f"{extrator.TETO_DE_MEMORIA_DO_FILHO // (1024 * 1024)} MB: folga pequena demais"
        )


def _pico_de_tempo_de_uma_leitura(dados: bytes) -> float:
    """Quanto UMA leitura deste arquivo custa, medido na hora.

    Um número fixo aqui envelheceria com a máquina do CI; o que importa é a
    razão entre uma leitura e três, e a razão se mede no mesmo lugar.
    """
    t0 = time.monotonic()
    _rodar_filho(".pdf", dados, extrator.LIMITE_DE_ENDERECAMENTO)
    return time.monotonic() - t0


def _rodar_filho(ext: str, dados: bytes, limite: int, teto_do_texto: int | None = None) -> subprocess.CompletedProcess:
    """Roda o processo filho de verdade, com os mesmos argumentos que o extrator passa."""
    import tempfile

    if teto_do_texto is None:
        teto_do_texto = extrator.TETO_DO_TEXTO_DEVOLVIDO
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(dados)
        caminho = tmp.name
    try:
        return subprocess.run(
            [sys.executable, "-P", extrator._CAMINHO_DO_FILHO, ext, caminho, str(limite), str(teto_do_texto)],
            capture_output=True,
            timeout=120,
        )
    finally:
        os.unlink(caminho)


def _pico_do_filho(ext: str, dados: bytes) -> int:
    """Pico de RSS do filho, em bytes, medido de um processo limpo.

    O `getrusage(RUSAGE_CHILDREN)` deste processo não serve: ele guarda o maior
    pico entre TODOS os filhos já colhidos, inclusive as bombas dos testes
    acima, e a ordem dos testes mudaria o número. Aqui um processo intermediário
    nasce só para rodar o filho e contar o pico dele.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(dados)
        caminho = tmp.name
    medidor = (
        "import resource, subprocess, sys;"
        f"subprocess.run([sys.executable, '-P', {extrator._CAMINHO_DO_FILHO!r}, {ext!r},"
        f" {caminho!r}, {str(extrator.LIMITE_DE_ENDERECAMENTO)!r},"
        f" {str(extrator.TETO_DO_TEXTO_DEVOLVIDO)!r}], check=True,"
        " stdout=subprocess.DEVNULL);"
        "bruto = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss;"
        "print(bruto if sys.platform == 'darwin' else bruto * 1024)"
    )
    try:
        p = subprocess.run([sys.executable, "-c", medidor], capture_output=True, timeout=180)
        assert p.returncode == 0, p.stderr.decode()[-400:]
        return int(p.stdout.decode().strip())
    finally:
        os.unlink(caminho)


# ═══════════════════════════════════════════════════════════════════════════
# 3. As duas mortes, cada uma isolada
# ═══════════════════════════════════════════════════════════════════════════


class TestAsDuasMortes:
    def test_o_prazo_mata_quem_queima_cpu_dentro_do_orcamento_de_memoria(self, client, monkeypatch, pdf_honesto):
        """O teto de memória não pega quem gasta tempo sem gastar memória.

        Arquivo de verdade, leitura de verdade, parser de verdade: só o orçamento
        de tempo é encolhido, de 45 s para 1 s, contra um PDF que leva 7,5 s. É a
        miniatura fiel do ataque que queima CPU dentro do orçamento de memória.
        """
        monkeypatch.setattr(extrator, "PRAZO_DA_EXTRACAO", 1.0)

        t0 = time.monotonic()
        r = _enviar(client, "ata-longa.pdf", pdf_honesto)
        decorrido = time.monotonic() - t0

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS
        assert decorrido < 15, f"a rota levou {decorrido:.1f}s: o filho nao foi morto no prazo"

    def test_o_vigia_de_rss_mata_sozinho_com_o_enderecamento_liberado(self, client, monkeypatch, docx_ataque):
        """Isola o vigia do pai da outra guarda de memória.

        No Linux o `RLIMIT_AS` costuma morder primeiro, e sem isto o vigia
        passaria a viagem inteira sem ser cobrado lá (no macOS ele é o único, e
        os dois testes acima o cobram). Com o endereçamento em 8 GB, o
        `RLIMIT_AS` não tem como recusar nada: quem sobra é o vigia.
        """
        monkeypatch.setattr(extrator, "LIMITE_DE_ENDERECAMENTO", 8 * 1024 * 1024 * 1024)

        r = _enviar(client, "proposta.docx", docx_ataque)

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS

    def test_o_teto_de_memoria_mata_sem_ajuda_do_prazo(self, client, monkeypatch, pdf_ataque):
        """O oposto do teste acima, para provar que os dois são guardas distintas.

        Com o prazo em 300 s, o único que pode recusar é o teto de memória.
        """
        monkeypatch.setattr(extrator, "PRAZO_DA_EXTRACAO", 300.0)

        t0 = time.monotonic()
        r = _enviar(client, "orcamento.pdf", pdf_ataque)
        decorrido = time.monotonic() - t0

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS
        assert decorrido < 60, "com prazo de 300s, quem recusou tem que ter sido a memoria"


# ═══════════════════════════════════════════════════════════════════════════
# 4. A frase na tela, e as frases que ela NÃO pode engolir
# ═══════════════════════════════════════════════════════════════════════════


class TestAFraseQueAPessoaVe:
    def test_a_frase_distingue_grande_demais_de_deu_erro(self):
        """A frase existe para a pessoa decidir o que fazer, e não para ela achar
        que o arquivo está corrompido."""
        frase = extrator.MENSAGEM_GRANDE_DEMAIS

        assert "grande ou complexo demais" in frase
        assert "Não é defeito no arquivo" in frase
        assert ".txt" in frase, "a frase tem que dizer a saída, não só o problema"
        for texto in (frase, extrator.MENSAGEM_FILA_CHEIA):
            assert "—" not in texto and "–" not in texto

    def test_quem_espera_vaga_demais_ouve_o_motivo_certo(self, client, monkeypatch):
        """Fila cheia não é arquivo grande demais, e o conselho é oposto.

        Dizer "divida o documento" a quem só pegou um momento movimentado manda
        a pessoa mexer no arquivo que estava certo. As duas vagas aqui estão
        ocupadas de verdade, e o prazo de espera é encolhido para o teste não
        levar 45 segundos.
        """
        monkeypatch.setattr(extrator, "PRAZO_DA_FILA", 0.5)
        # Com prazo, e nao `acquire()` seco: se uma vaga tiver vazado num teste
        # anterior, este teste TEM que falhar dizendo isso, e nao ficar pendurado
        # para sempre. Vaga presa e exatamente o defeito que ele existe para pegar.
        tomadas = [extrator._vagas.acquire(timeout=10) for _ in range(extrator.VAGAS_DE_EXTRACAO)]
        assert all(tomadas), "alguma vaga de extracao vazou antes deste teste"
        try:
            r = _enviar(client, "ata.docx", _docx_honesto(200))
        finally:
            for pegou in tomadas:
                if pegou:
                    extrator._vagas.release()

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_FILA_CHEIA
        assert r.json()["detail"] != extrator.MENSAGEM_GRANDE_DEMAIS

    def test_pdf_escaneado_continua_com_a_frase_dele(self, client):
        """Recusa de conteúdo atravessa o processo filho com o texto intacto.

        Se o isolamento tivesse engolido as recusas do parser, toda recusa viraria
        "grande demais" e a pessoa com um PDF escaneado seria mandada dividir o
        arquivo, que não resolve nada.
        """
        r = _enviar(client, "escaneado.pdf", _pdf_sem_texto())

        assert r.status_code == 422
        detalhe = r.json()["detail"]
        assert detalhe != extrator.MENSAGEM_GRANDE_DEMAIS
        assert "escaneado" in detalhe

    def test_filho_morto_por_sinal_de_fora_nao_vira_arquivo_corrompido(self, client, monkeypatch, tmp_path):
        """O OOM killer do cgroup mata sem avisar, e a conta é de tamanho.

        Um contêiner com menos memória que o `RLIMIT_AS`, ou uma alocação única
        entre duas amostras do vigia, derruba o filho por sinal: código de saída
        negativo, nenhum `MemoryError` para ler. Culpar o arquivo aqui repetiria,
        por outra porta, o defeito do `MemoryError` que o `pdfminer` embrulha.

        Aqui o programa do filho é trocado por um que se mata: não existe jeito
        determinístico de fazer o kernel escolher o nosso processo. O caminho
        testado continua sendo o da rota e o do pai de verdade.
        """
        suicida = tmp_path / "filho_morto_por_sinal.py"
        suicida.write_text("import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n")
        monkeypatch.setattr(extrator, "_CAMINHO_DO_FILHO", str(suicida))

        r = _enviar(client, "ata.docx", _docx_honesto(50))

        assert r.status_code == 422
        assert r.json()["detail"] == extrator.MENSAGEM_GRANDE_DEMAIS

    def test_arquivo_corrompido_continua_com_a_frase_dele(self, client):
        """Falha de leitura não pode virar "grande demais": são conselhos opostos."""
        r = _enviar(client, "quebrado.docx", b"PK\x03\x04isto nao e um zip de verdade")

        assert r.status_code == 422
        detalhe = r.json()["detail"]
        assert detalhe != extrator.MENSAGEM_GRANDE_DEMAIS
        assert "corrompido" in detalhe


# ═══════════════════════════════════════════════════════════════════════════
# 5. As guardas do próprio isolamento
# ═══════════════════════════════════════════════════════════════════════════


class TestAsGuardasDoIsolamento:
    def test_importar_o_filho_nao_sobe_parser_nenhum(self):
        """O topo do módulo filho é stdlib pura, e isso é o que torna a ordem possível.

        Se o `pdfplumber` subisse no import do módulo, ele estaria carregado
        antes de qualquer `setrlimit` e o orçamento começaria gasto. O pai
        importa este módulo dentro do worker, então um parser no topo também
        pesaria no worker sem necessidade.
        """
        sonda = (
            "import sys;"
            f"sys.path.insert(0, {os.path.dirname(extrator._CAMINHO_DO_FILHO)!r});"
            "import transcricao_extractor_filho;"
            "print([m for m in ('pdfplumber', 'pdfminer', 'docx2txt') if m in sys.modules])"
        )
        p = subprocess.run([sys.executable, "-c", sonda], capture_output=True, timeout=60)

        assert p.returncode == 0, p.stderr.decode()[-400:]
        assert p.stdout.decode().strip() == "[]"

    def test_o_limite_e_instalado_antes_de_importar_o_parser(self, pdf_honesto):
        """A ordem, cobrada pelo desfecho e não por inspeção.

        Medido no Linux: com 48 MB de endereçamento o `pdfplumber` nem importa
        (`ImportError`), e com 64 MB ele lê o mesmo arquivo. Se o `setrlimit`
        acontecesse depois do import, o arquivo sairia com `OK` sob os 48 MB e o
        limite teria virado enfeite. O controle folgado logo abaixo prova que
        quem recusou foi o limite, e não o arquivo.
        """
        if not _plataforma_aplica_rlimit_as():
            pytest.skip(f"{sys.platform} nao aceita setrlimit(RLIMIT_AS); quem segura e o vigia de RSS")

        apertado = _rodar_filho(".pdf", pdf_honesto, limite=48 * 1024 * 1024)
        folgado = _rodar_filho(".pdf", pdf_honesto, limite=extrator.LIMITE_DE_ENDERECAMENTO)

        assert not apertado.stdout.startswith(b"OK"), "leu o arquivo apesar do limite de 48 MB"
        assert apertado.returncode != 0
        assert folgado.stdout.startswith(b"OK"), folgado.stderr.decode()[-400:]

    async def test_uploads_simultaneos_nao_multiplicam_o_orcamento(self, app, pdf_honesto):
        """Teto por filho não é teto da máquina.

        O `@limiter.limit` das rotas conta requisições por MINUTO, não ao mesmo
        tempo: dez uploads disparados juntos passam pelos "5/minute" e seriam dez
        filhos de até 512 MB cada. Três leituras de 7,5 s entrando juntas contra
        duas vagas têm que sair em duas rodadas, não em uma, e as três têm que
        SAIR (fila que recusa vira indisponibilidade, não guarda).
        """
        import httpx

        assert extrator.VAGAS_DE_EXTRACAO == 2, "este teste conta rodadas para duas vagas"
        quantas = extrator.VAGAS_DE_EXTRACAO + 1

        uma_so = _pico_de_tempo_de_uma_leitura(pdf_honesto)

        transporte = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transporte, base_url="http://teste", timeout=120) as ac:
            rota = "/api/reunioes/R1/ata-guiada/extrair-documento"
            t0 = time.monotonic()
            respostas = await asyncio.gather(
                *[
                    ac.post(rota, files={"file": ("ata-longa.pdf", pdf_honesto, "application/pdf")})
                    for _ in range(quantas)
                ]
            )
            juntas = time.monotonic() - t0

        assert all(r.status_code == 200 for r in respostas), [r.status_code for r in respostas]
        assert juntas > uma_so * 1.4, (
            f"as {quantas} leituras sairam em {juntas:.1f}s contra {uma_so:.1f}s de uma: as vagas nao seguraram nada"
        )

    def test_a_espera_na_fila_cobre_uma_leitura_inteira(self):
        """Esperar menos que uma leitura é recusar quem seria atendido.

        Uma vaga só vaga quando a leitura em curso acaba, e ela acaba no máximo
        no prazo da extração. Este número já foi 10 s e o CI derrubou: na máquina
        de duas CPUs do runner, a terceira pessoa levava recusa com o arquivo
        dela perfeitamente em ordem.
        """
        assert extrator.PRAZO_DA_FILA >= extrator.PRAZO_DA_EXTRACAO

    def test_o_teto_do_texto_devolvido_cabe_dezesseis_vezes_o_maior_legitimo(self, pdf_honesto, docx_honesto):
        """A folga do teto de saída, medida contra arquivo de verdade.

        Sem isto o número viraria decoração: um teto abaixo do que a ata honesta
        devolve recusaria a ata honesta, e um teto grande demais não guardaria
        nada. O piso mede os dois legítimos; o topo é a conta que justificou o
        número no comentário do módulo.
        """
        for nome, dados in (("pdf", pdf_honesto), ("docx", docx_honesto)):
            saida = _rodar_filho(
                f".{nome}",
                dados,
                limite=extrator.LIMITE_DE_ENDERECAMENTO,
                teto_do_texto=extrator.TETO_DO_TEXTO_DEVOLVIDO,
            )
            assert saida.stdout.startswith(b"OK"), saida.stderr.decode()[-300:]
            texto = saida.stdout.partition(b"\n")[2]
            assert len(texto) * 16 <= extrator.TETO_DO_TEXTO_DEVOLVIDO, (
                f"o {nome} honesto devolve {len(texto) // 1024} KB contra um teto de "
                f"{extrator.TETO_DO_TEXTO_DEVOLVIDO // (1024 * 1024)} MB: folga pequena demais"
            )

    def test_o_teto_de_rss_fica_abaixo_do_limite_de_enderecamento(self):
        """Quem decide primeiro no caso normal é o vigia de RSS.

        Espaço de endereçamento é sempre maior que RSS. Um `RLIMIT_AS` menor que
        o teto de RSS mataria o filho por endereçamento de biblioteca mapeada
        antes de ele ler byte nenhum do arquivo.
        """
        assert extrator.TETO_DE_MEMORIA_DO_FILHO < extrator.LIMITE_DE_ENDERECAMENTO

    def test_so_formato_sem_parser_escapa_do_isolamento(self):
        """Tripwire, e não identidade: mexer nesta lista é decisão consciente.

        Tudo em `SUPPORTED_EXTENSIONS` roda isolado por padrão; a exceção é lista
        fechada. Pôr um formato aqui exige provar que ele não tem parser nenhum
        no caminho, porque é o que dispensa o processo separado.
        """
        assert extrator.FORMATOS_DE_TEXTO_PURO == {".txt", ".md"}
        assert extrator.FORMATOS_DE_TEXTO_PURO < extrator.SUPPORTED_EXTENSIONS

    def test_o_arquivo_temporario_do_filho_nao_fica_para_tras(self, client, docx_honesto):
        """O conteúdo do upload passa pelo disco para chegar no filho. Passa, não fica."""
        import glob
        import tempfile

        antes = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.docx")))
        r = _enviar(client, "ata-longa.docx", docx_honesto)
        depois = set(glob.glob(os.path.join(tempfile.gettempdir(), "*.docx")))

        assert r.status_code == 200
        assert depois == antes, f"sobrou no disco: {depois - antes}"
