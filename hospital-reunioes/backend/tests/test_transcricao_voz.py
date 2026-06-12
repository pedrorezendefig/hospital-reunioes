"""Testes do comando por voz compartilhado (issue #35; movido de Notas — ADR 0011).

O Facilitador dita (Ata Guiada, chat de POPs): o front grava o áudio
(MediaRecorder), manda pro backend, e o **texto transcrito cai editável** no
destino da tela. A transcrição é um módulo profundo
(`transcricao_service.transcrever(audio, formato) → texto`) que chama o
endpoint `/audio/transcriptions` do OpenRouter com um corpo **JSON**
(`input_audio` em base64 + `format` + `language: "pt"`), autenticado com a
mesma `OPENROUTER_API_KEY` do Pipeline. O texto vem no campo `text` da
resposta. O áudio **não é persistido** — só o texto. Falha → erro claro pro
front cair no fallback de digitação.

Escopo: OpenRouter/transcrição **100% mockado** (mock de `httpx.post`) —
nenhum teste toca chave/rede real.
"""

from __future__ import annotations

import base64
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import config  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import transcricao as transcricao_router  # noqa: E402
from app.services import transcricao_service as transc  # noqa: E402

# ─── Fake do httpx.post ao endpoint de transcrição do OpenRouter ─────────────


class _RespostaFake:
    """Espelha o que o service usa de uma httpx.Response: raise_for_status() +
    json(). `status_error` simula um 4xx/5xx do upstream (o 502 de hoje)."""

    def __init__(self, *, json_data: dict | None = None, status_error: Exception | None = None):
        self._json = json_data or {}
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self) -> dict:
        return self._json


class _PostSpy:
    """Registra cada chamada a httpx.post e devolve a resposta programada (ou
    levanta o erro de conexão programado, simulando o serviço fora do ar)."""

    def __init__(
        self,
        *,
        texto: str | None = None,
        conn_error: Exception | None = None,
        status_error: Exception | None = None,
    ):
        self.texto = texto
        self.conn_error = conn_error
        self.status_error = status_error
        self.chamadas: list[dict] = []

    def __call__(self, url, **kwargs):
        self.chamadas.append({"url": url, **kwargs})
        if self.conn_error is not None:
            raise self.conn_error
        return _RespostaFake(json_data={"text": self.texto}, status_error=self.status_error)


def _fake_openrouter(
    monkeypatch,
    *,
    texto: str | None = None,
    conn_error: Exception | None = None,
    status_error: Exception | None = None,
) -> _PostSpy:
    """Configura a chave do OpenRouter (provider sai do 'mock') e planta um spy
    no lugar de `httpx.post`. Devolve o spy para inspecionar o corpo enviado."""
    monkeypatch.setattr(config.settings, "openrouter_api_key", "sk-or-test-key")
    spy = _PostSpy(texto=texto, conn_error=conn_error, status_error=status_error)
    monkeypatch.setattr(transc.httpx, "post", spy)
    return spy


# ═══════════════════════════════════════════════════════════════════════════
# Service: transcricao_service.transcrever (OpenRouter 100% mockado via httpx)
# ═══════════════════════════════════════════════════════════════════════════


class TestTranscricaoService:
    def test_transcreve_audio_via_openrouter_json_base64(self, monkeypatch):
        """A transcrição manda um corpo JSON ao endpoint `/audio/transcriptions`
        do OpenRouter — `input_audio` com o áudio em base64, `format` derivado
        do MIME e `language: "pt"` — autenticado com a chave do OpenRouter, e lê
        o texto do campo `text`. O texto volta limpo (sem espaços nas bordas),
        pronto pro destino editável."""
        spy = _fake_openrouter(monkeypatch, texto="  Comprar insumos até sexta.  ")

        texto = transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

        assert texto == "Comprar insumos até sexta."
        assert len(spy.chamadas) == 1
        chamada = spy.chamadas[0]
        # Endpoint de transcrição do OpenRouter (base_url + /audio/transcriptions).
        assert chamada["url"] == f"{config.settings.openrouter_base_url}/audio/transcriptions"
        payload = chamada["json"]
        # Modelo de transcrição configurado (default openai/gpt-4o-mini-transcribe).
        assert payload["model"] == config.settings.transcricao_model
        assert payload["language"] == "pt"
        assert payload["input_audio"]["format"] == "webm"
        # Os bytes do áudio viajam em base64 e voltam idênticos ao decodificar.
        assert base64.b64decode(payload["input_audio"]["data"]) == b"RIFF....audio-bytes"
        # Autenticação com a chave do OpenRouter + headers de atribuição do Pipeline.
        headers = chamada["headers"]
        assert headers["Authorization"] == "Bearer sk-or-test-key"
        assert headers["HTTP-Referer"] == "https://hospitalsaomatheus.cloud"
        assert headers["X-Title"] == "Hospital Reunioes"

    def test_mime_com_codecs_e_normalizado_no_formato(self, monkeypatch):
        """O MediaRecorder do Chrome grava "audio/webm;codecs=opus". O parâmetro
        codecs sai e o `format` enviado ao OpenRouter é só "webm"."""
        spy = _fake_openrouter(monkeypatch, texto="ok")

        transc.transcrever(b"RIFF....audio-bytes", "audio/webm;codecs=opus")

        assert spy.chamadas[0]["json"]["input_audio"]["format"] == "webm"

    def test_mp4_do_safari_vira_formato_mp4(self, monkeypatch):
        """Safari grava audio/mp4 — o `format` acompanha o MIME (não fixa webm)."""
        spy = _fake_openrouter(monkeypatch, texto="ok")

        transc.transcrever(b"\x00\x00\x00\x18ftypmp4", "audio/mp4")

        assert spy.chamadas[0]["json"]["input_audio"]["format"] == "mp4"

    def test_audio_vazio_nao_chama_a_ia_e_sinaliza_indisponivel(self, monkeypatch):
        """Áudio vazio não vira chamada de IA (sem custo) — sinaliza
        indisponível para o front cair no fallback de digitação."""
        spy = _fake_openrouter(monkeypatch, texto="não deveria chegar aqui")

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"", "audio/webm")

        assert spy.chamadas == []

    def test_sem_chave_openrouter_sinaliza_indisponivel(self, monkeypatch):
        """Sem a chave do OpenRouter (provider 'mock') a transcrição não inventa
        texto nem chama a rede — sinaliza indisponível, e o Facilitador digita."""
        monkeypatch.setattr(config.settings, "openrouter_api_key", "")

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

    def test_servico_fora_do_ar_sinaliza_indisponivel(self, monkeypatch):
        """Erro de conexão (serviço fora) vira erro claro (não vaza a exceção
        crua), para o front avisar e oferecer digitação."""
        _fake_openrouter(monkeypatch, conn_error=RuntimeError("Connection refused"))

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

    def test_status_de_erro_do_upstream_sinaliza_indisponivel(self, monkeypatch):
        """Um 502/4xx do upstream (raise_for_status levanta) também vira erro
        claro — não vaza como exceção crua."""
        _fake_openrouter(monkeypatch, status_error=RuntimeError("502 Bad Gateway"))

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

    def test_transcricao_nao_persiste_o_audio(self, monkeypatch):
        """O áudio entra como bytes e sai como texto. O service nem conhece a
        camada de storage — guard ESTRUTURAL: se alguém importar `storage` aqui
        (a porta natural pra persistir), este teste cai. E os bytes só viram
        base64 no corpo da chamada, nenhum outro sink."""
        spy = _fake_openrouter(monkeypatch, texto="Conversa transcrita.")

        texto = transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

        assert isinstance(texto, str) and texto == "Conversa transcrita."
        assert base64.b64decode(spy.chamadas[0]["json"]["input_audio"]["data"]) == b"RIFF....audio-bytes"
        assert not hasattr(transc, "storage"), "transcricao_service não deve importar storage"


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint: POST /transcricao/voz (recebe áudio, devolve texto; service mockado)
# ═══════════════════════════════════════════════════════════════════════════


CURRENT_USER = {"id": "auth-uid-1", "email": "diretor@hospital.com"}


def _participante(pid: str = "P1", profile: str = "regular") -> dict:
    return {"id": pid, "nome_completo": f"Facilitador {pid}", "access_profile": profile}


class _TableSpy:
    """Registra inserts por tabela; leitura devolve vazio. Suficiente para
    provar que o endpoint de transcrição não grava nada."""

    def __init__(self, name: str, inserts: dict):
        self._name = name
        self._inserts = inserts

    def insert(self, payload):
        self._inserts.setdefault(self._name, []).append(payload)
        return self

    def select(self, *_a, **_kw):
        return self

    def eq(self, *_a, **_kw):
        return self

    def is_(self, *_a, **_kw):
        return self

    def update(self, *_a, **_kw):
        return self

    def delete(self, *_a, **_kw):
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _SupabaseSpy:
    def __init__(self):
        self.inserts: dict[str, list] = {}

    def table(self, name: str):
        return _TableSpy(name, self.inserts)


@pytest.fixture
def make_client(monkeypatch):
    """TestClient do router de transcrição com o participante logado plugado.
    `me=None` simula usuário sem cadastro de participante."""

    def _factory(*, me: dict | None, supabase: _SupabaseSpy | None = None) -> TestClient:
        app = FastAPI()
        app.include_router(transcricao_router.router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase or _SupabaseSpy()

        async def _fake_get_participante(*_a, **_kw):
            return dict(me) if me else None

        monkeypatch.setattr(transcricao_router, "get_participante_for_user", _fake_get_participante)
        return TestClient(app)

    return _factory


class TestEndpointTranscreverVoz:
    def test_grava_voz_e_recebe_texto_transcrito_editavel(self, make_client, monkeypatch):
        """O Facilitador grava voz e recebe o texto transcrito — os bytes do
        áudio chegam ao service e o texto volta no corpo da resposta (o front
        o joga editável no destino da tela)."""
        recebido: dict = {}

        def _fake_transcrever(audio, formato):
            recebido["audio"] = audio
            recebido["formato"] = formato
            return "Comprar insumos até sexta."

        monkeypatch.setattr(transcricao_router, "transcrever", _fake_transcrever)
        client = make_client(me=_participante())

        r = client.post(
            "/api/transcricao/voz",
            files={"audio": ("voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 200
        assert r.json() == {"texto": "Comprar insumos até sexta."}
        assert recebido["audio"] == b"RIFF....audio-bytes"
        assert recebido["formato"] == "audio/webm"

    def test_falha_na_transcricao_vira_502_com_aviso_de_fallback(self, make_client, monkeypatch):
        """Transcrição indisponível vira 502 com aviso claro que aponta o
        fallback — o front mostra a mensagem e o Facilitador digita."""

        def _explode(audio, formato):
            raise transc.TranscricaoIndisponivelError("providers fora")

        monkeypatch.setattr(transcricao_router, "transcrever", _explode)
        client = make_client(me=_participante())

        r = client.post(
            "/api/transcricao/voz",
            files={"audio": ("voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 502
        assert "manual" in r.json()["detail"].lower()

    def test_transcrever_nao_persiste_nada(self, make_client, monkeypatch):
        """Transcrever só devolve texto — não persiste nada no banco. O destino
        do texto (chat, rascunho) segue sendo um salvar explícito à parte."""
        monkeypatch.setattr(transcricao_router, "transcrever", lambda audio, formato: "Texto ditado.")
        sb = _SupabaseSpy()
        client = make_client(me=_participante(), supabase=sb)

        r = client.post(
            "/api/transcricao/voz",
            files={"audio": ("voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 200
        assert sb.inserts == {}

    def test_exige_participante_cadastrado(self, make_client, monkeypatch):
        """Usuário sem cadastro de participante → 403, e a transcrição nem é
        chamada (barra antes de gastar IA)."""
        chamou: list = []
        monkeypatch.setattr(transcricao_router, "transcrever", lambda a, f: chamou.append(1) or "x")
        client = make_client(me=None)

        r = client.post(
            "/api/transcricao/voz",
            files={"audio": ("voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 403
        assert chamou == []

    def test_audio_acima_do_limite_vira_413(self, make_client, monkeypatch):
        """Áudio grande é barrado com 413 antes de ir pra IA — não estoura
        memória nem bloqueia o worker (padrão do PR #39)."""
        monkeypatch.setattr(transcricao_router, "MAX_AUDIO_BYTES", 10)
        chamou: list = []
        monkeypatch.setattr(transcricao_router, "transcrever", lambda a, f: chamou.append(1) or "x")
        client = make_client(me=_participante())

        r = client.post(
            "/api/transcricao/voz",
            files={"audio": ("voz.webm", b"12345678901", "audio/webm")},  # 11 bytes > 10
        )

        assert r.status_code == 413
        assert chamou == []
