"""Testes do comando por voz na Nota (issue #35).

O Facilitador dita a Nota: o front grava o áudio (MediaRecorder), manda pro
backend, e o **texto transcrito cai editável no corpo**. A transcrição é um
módulo profundo (`transcricao_service.transcrever(audio, formato) → texto`)
que reusa a chave/billing do Pipeline (`_get_llm`) chamando o endpoint
`/audio/transcriptions` do OpenRouter com `gpt-4o-mini-transcribe`. O áudio
**não é persistido** — só o texto. Falha → erro claro pro front cair no
fallback de digitação.

Escopo: OpenRouter/transcrição **100% mockado** — nenhum teste toca
chave/provider real. Mock Supabase fluente espelhado de
`test_extracao_pendencias_nota.py`.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers import notas as notas_router  # noqa: E402
from app.services import transcricao_service as transc  # noqa: E402

# ─── Fake do client OpenRouter (mesma superfície do SDK openai) ──────────────


class _TranscriptionsSpy:
    """Espelha `client.audio.transcriptions`: registra a chamada e devolve o
    texto programado (ou levanta o erro programado, simulando a API fora)."""

    def __init__(self, texto: str | None = None, erro: Exception | None = None):
        self.texto = texto
        self.erro = erro
        self.chamadas: list[dict] = []

    def create(self, **kwargs):
        self.chamadas.append(kwargs)
        if self.erro is not None:
            raise self.erro
        return SimpleNamespace(text=self.texto)


def _fake_llm(monkeypatch, *, texto: str | None = None, erro: Exception | None = None) -> _TranscriptionsSpy:
    """Planta um client OpenRouter falso no service via `_get_llm` (a mesma
    porta que o Pipeline usa) e força o provider 'openrouter'. Devolve o spy
    de transcriptions para inspeção."""
    spy = _TranscriptionsSpy(texto=texto, erro=erro)
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=spy))
    extra = {"extra_headers": {"X-Title": "Hospital Reunioes"}}
    monkeypatch.setattr(transc, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(transc, "_get_llm", lambda: (client, "openai/gpt-5.4-mini", extra))
    return spy


# ═══════════════════════════════════════════════════════════════════════════
# Service: transcricao_service.transcrever (OpenRouter 100% mockado)
# ═══════════════════════════════════════════════════════════════════════════


class TestTranscricaoService:
    def test_transcreve_audio_via_openrouter_com_gpt_4o_mini_transcribe(self, monkeypatch):
        """Critério 2: a transcrição usa `gpt-4o-mini-transcribe` via OpenRouter,
        reusando a chave/billing do Pipeline (o mesmo client de `_get_llm`). O
        texto volta limpo (sem espaços nas bordas), pronto pro corpo editável."""
        spy = _fake_llm(monkeypatch, texto="  Comprar insumos até sexta.  ")

        texto = transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

        assert texto == "Comprar insumos até sexta."
        assert len(spy.chamadas) == 1
        chamada = spy.chamadas[0]
        assert chamada["model"] == "gpt-4o-mini-transcribe"
        # file = (nome, bytes, mimetype) — os bytes do áudio fluem sem alteração.
        assert chamada["file"][1] == b"RIFF....audio-bytes"
        assert chamada["file"][2] == "audio/webm"
        # Reusa os headers do OpenRouter que `_get_llm` entrega (mesma billing).
        assert chamada["extra_headers"] == {"X-Title": "Hospital Reunioes"}

    def test_audio_vazio_nao_chama_a_ia_e_sinaliza_indisponivel(self, monkeypatch):
        """Áudio vazio não vira chamada de IA (sem custo) — sinaliza
        indisponível para o front cair no fallback de digitação."""
        spy = _fake_llm(monkeypatch, texto="não deveria chegar aqui")

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"", "audio/webm")

        assert spy.chamadas == []

    def test_sem_chave_llm_configurada_sinaliza_indisponivel(self, monkeypatch):
        """Critério 4 (backend): sem provider LLM (chave ausente) a transcrição
        não inventa texto — sinaliza indisponível, e o Facilitador digita."""
        monkeypatch.setattr(transc, "_llm_provider", lambda: "mock")

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

    def test_falha_da_api_de_transcricao_sinaliza_indisponivel(self, monkeypatch):
        """Critério 4 (backend): a API de transcrição fora do ar vira erro
        claro (não vaza a exceção crua), para o front avisar e oferecer
        digitação."""
        _fake_llm(monkeypatch, erro=RuntimeError("502 Bad Gateway upstream"))

        with pytest.raises(transc.TranscricaoIndisponivelError):
            transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

    def test_transcricao_nao_persiste_o_audio(self, monkeypatch):
        """Critério 3: o áudio entra como bytes e sai como texto — nada é
        gravado. Guard: se alguém plugar um upload no caminho, este teste cai."""
        from app.services import storage

        uploads: list = []
        monkeypatch.setattr(storage, "upload_file", lambda *a, **k: uploads.append((a, k)))
        _fake_llm(monkeypatch, texto="Conversa transcrita.")

        texto = transc.transcrever(b"RIFF....audio-bytes", "audio/webm")

        assert texto == "Conversa transcrita."
        assert uploads == []


# ═══════════════════════════════════════════════════════════════════════════
# Endpoint: POST /notas/transcrever (recebe áudio, devolve texto; service mockado)
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
    """TestClient do router de notas com o participante logado plugado. `me=None`
    simula usuário sem cadastro de participante."""

    def _factory(*, me: dict | None, supabase: _SupabaseSpy | None = None) -> TestClient:
        app = FastAPI()
        app.include_router(notas_router.router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
        app.dependency_overrides[get_supabase_client] = lambda: supabase or _SupabaseSpy()

        async def _fake_get_participante(*_a, **_kw):
            return dict(me) if me else None

        monkeypatch.setattr(notas_router, "get_participante_for_user", _fake_get_participante)
        return TestClient(app)

    return _factory


class TestEndpointTranscrever:
    def test_grava_voz_e_recebe_texto_transcrito_editavel(self, make_client, monkeypatch):
        """Critério 1: o Facilitador grava voz e recebe o texto transcrito — os
        bytes do áudio chegam ao service e o texto volta no corpo da resposta
        (o front o joga editável no textarea da Nota)."""
        recebido: dict = {}

        def _fake_transcrever(audio, formato):
            recebido["audio"] = audio
            recebido["formato"] = formato
            return "Comprar insumos até sexta."

        monkeypatch.setattr(notas_router, "transcrever", _fake_transcrever)
        client = make_client(me=_participante())

        r = client.post(
            "/api/notas/transcrever",
            files={"audio": ("nota-voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 200
        assert r.json() == {"texto": "Comprar insumos até sexta."}
        assert recebido["audio"] == b"RIFF....audio-bytes"
        assert recebido["formato"] == "audio/webm"

    def test_falha_na_transcricao_vira_502_com_aviso_de_fallback(self, make_client, monkeypatch):
        """Critério 4: transcrição indisponível vira 502 com aviso claro que
        aponta o fallback — o front mostra a mensagem e o Facilitador digita."""

        def _explode(audio, formato):
            raise transc.TranscricaoIndisponivelError("providers fora")

        monkeypatch.setattr(notas_router, "transcrever", _explode)
        client = make_client(me=_participante())

        r = client.post(
            "/api/notas/transcrever",
            files={"audio": ("nota-voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 502
        assert "manual" in r.json()["detail"].lower()

    def test_transcrever_nao_cria_a_nota(self, make_client, monkeypatch):
        """Critério 5 (backend): transcrever só devolve texto — não persiste
        Nota nenhuma. Criar a Nota segue sendo o salvar explícito do editor."""
        monkeypatch.setattr(notas_router, "transcrever", lambda audio, formato: "Texto ditado.")
        sb = _SupabaseSpy()
        client = make_client(me=_participante(), supabase=sb)

        r = client.post(
            "/api/notas/transcrever",
            files={"audio": ("nota-voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 200
        assert sb.inserts == {}

    def test_exige_participante_cadastrado(self, make_client, monkeypatch):
        """Usuário sem cadastro de participante → 403, e a transcrição nem é
        chamada (barra antes de gastar IA)."""
        chamou: list = []
        monkeypatch.setattr(notas_router, "transcrever", lambda a, f: chamou.append(1) or "x")
        client = make_client(me=None)

        r = client.post(
            "/api/notas/transcrever",
            files={"audio": ("nota-voz.webm", b"RIFF....audio-bytes", "audio/webm")},
        )

        assert r.status_code == 403
        assert chamou == []
