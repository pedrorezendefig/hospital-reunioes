"""Teto de tamanho do corpo de requisição (issue #349, item 4).

Nenhum POST do app tinha limite antes do pydantic: um corpo gigante era lido
inteiro para a memória antes de qualquer recusa, e os endpoints públicos são os
mais expostos. O teto vale para o app inteiro e vive no próprio app, porque há
caminho de entrada que não passa pelo Traefik (o rewrite interno do Next).
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.middleware.limite_corpo import LIMITE_CORPO_BYTES, LimiteDeCorpoMiddleware  # noqa: E402

TETO_DE_TESTE = 1024


def _make_app(teto: int = TETO_DE_TESTE) -> TestClient:
    app = FastAPI()
    app.add_middleware(LimiteDeCorpoMiddleware, limite_bytes=teto)

    @app.post("/eco")
    async def eco(request: Request):
        corpo = await request.body()
        return {"bytes": len(corpo)}

    return TestClient(app)


class TestTetoDeCorpo:
    def test_corpo_maior_que_o_teto_e_recusado(self):
        client = _make_app()

        r = client.post("/eco", content=b"x" * (TETO_DE_TESTE + 1))

        assert r.status_code == 413

    def test_corpo_dentro_do_teto_passa_inteiro(self):
        client = _make_app()

        r = client.post("/eco", content=b"x" * TETO_DE_TESTE)

        assert r.status_code == 200
        assert r.json() == {"bytes": TETO_DE_TESTE}

    def test_corpo_em_pedacos_sem_content_length_tambem_e_barrado(self):
        """Sem Content-Length (transfer-encoding chunked) o tamanho só aparece
        lendo: a contagem corta assim que o teto estoura."""
        client = _make_app()

        def pedacos():
            for _ in range(4):
                yield b"x" * (TETO_DE_TESTE // 2)

        r = client.post("/eco", content=pedacos())

        assert r.status_code == 413

    def test_teto_default_cobre_o_maior_upload_de_arquivo_unico(self):
        """O maior corpo legítimo de arquivo único é o áudio da transcrição: o
        teto global precisa ficar acima dele, senão vira recusa de feature."""
        from app.routers.transcricao import MAX_AUDIO_BYTES

        assert LIMITE_CORPO_BYTES > MAX_AUDIO_BYTES

    def test_teto_default_cobre_um_lote_de_materiais_de_pop(self):
        """Materiais de referência de POP sobem em LOTE, num request só, cada
        arquivo com até 15 MB. Meia dúzia de arquivos no talo é uso plausível, e
        o teto global não pode recusar o lote inteiro: aquela rota promete
        recusar arquivo a arquivo, sem derrubar os válidos."""
        from app.services.transcricao_extractor import MAX_BYTES_BINARY

        assert LIMITE_CORPO_BYTES >= 6 * MAX_BYTES_BINARY

    def test_app_real_liga_o_teto(self):
        from app.main import app

        assert any(m.cls is LimiteDeCorpoMiddleware for m in app.user_middleware)
