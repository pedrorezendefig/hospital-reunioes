"""Triagem de e-mail, a fundação (issue #648, PRD #646, ADR 0051).

O e-mail que chega em ouvidoria@ é copiado para o subdomínio de recebimento do
Resend, e o Resend chama o webhook do app. Daqui para a frente ele é um item da
Triagem de e-mail: só o Perfil da Ouvidoria vê, e nenhum e-mail vira caso sem
ato do ouvidor. Nesta fatia o ouvidor só lê.

Seam 1, o webhook: requisição assinada (svix) com o evento `email.received`, e
a função única de leitura do Resend (`email_service.ler_email_recebido`)
dublada para devolver corpo, cabeçalhos e anexos. Seam 2, as rotas da triagem:
listar e ver o item, com anexo por URL assinada. Rede de verdade nenhuma: a
trava do `conftest` cobre o arquivo, e a leitura real do Resend é provada com
`httpx.MockTransport`, que não abre socket.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_triagem_email as triagem_router  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import email_service  # noqa: E402
from app.services.email_service import AnexoDoResend, EmailDoResend, LeituraDoResendError  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

# O formato do segredo do Resend (svix): prefixo `whsec_` e a chave em base64.
SEGREDO = "whsec_" + base64.b64encode(b"segredo-de-teste-da-triagem-0648").decode("ascii")

PDF = b"%PDF-1.4\n% laudo de teste\n%%EOF\n"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _segredo_configurado(monkeypatch):
    """O segredo de pé, como estará no Coolify. Quem prova a recusa sem ele é o
    teste que o apaga de propósito."""
    monkeypatch.setattr(settings, "resend_webhook_secret", SEGREDO)
    monkeypatch.setattr(settings, "ouvidoria_dominio_interno", "hospitalsaomatheus.com.br")


# ─── Dublês ──────────────────────────────────────────────────────────────────


class _Resposta:
    def __init__(self, data):
        self.data = data


class _TabelaFake:
    """PostgREST fiel no que importa aqui: o insert gera id, a coluna única do
    identificador do Resend recusa a segunda linha (23505), o update casa pelos
    filtros e o select projeta só o que foi pedido."""

    UNICAS = {"ouvidoria_emails_recebidos": ("resend_email_id",)}

    def __init__(self, dono: _SupabaseFake, nome: str):
        self.dono = dono
        self.nome = nome
        self.rows = dono.tabelas.setdefault(nome, [])
        self._filtros: list[tuple[str, str, object]] = []
        self._ordens: list[tuple[str, bool]] = []
        self._insert = None
        self._update = None
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload):
        self._update = payload
        return self

    def eq(self, coluna, valor):
        self._filtros.append(("eq", coluna, valor))
        return self

    def in_(self, coluna, valores):
        self._filtros.append(("in", coluna, list(valores)))
        return self

    def order(self, coluna, desc=False):
        self._ordens.append((coluna, desc))
        return self

    def range(self, inicio, fim):
        self._janela = (inicio, fim)
        return self

    def _casa(self, row: dict) -> bool:
        for op, coluna, valor in self._filtros:
            if op == "eq" and row.get(coluna) != valor:
                return False
            if op == "in" and row.get(coluna) not in valor:
                return False
        return True

    def execute(self):
        self.dono.consultas.append(self.nome)
        if self._insert is not None:
            return self._inserir()
        if self._update is not None:
            casadas = [r for r in self.rows if self._casa(r)]
            for r in casadas:
                r.update(self._update)
            return _Resposta([dict(r) for r in casadas])
        casadas = [r for r in self.rows if self._casa(r)]
        for coluna, desc in reversed(self._ordens):
            casadas = sorted(casadas, key=lambda r: str(r.get(coluna) or ""), reverse=desc)
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        if self._colunas is not None:
            return _Resposta([{c: r.get(c) for c in self._colunas} for r in casadas])
        return _Resposta([dict(r) for r in casadas])

    def _inserir(self):
        novos = self._insert if isinstance(self._insert, list) else [self._insert]
        gravados = []
        for novo in novos:
            for coluna in self.UNICAS.get(self.nome, ()):
                if any(r.get(coluna) == novo.get(coluna) for r in self.rows):
                    raise APIError({"code": "23505", "message": f"duplicate key value violates unique ({coluna})"})
            linha = dict(novo)
            linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
            linha.setdefault("created_at", f"2026-09-10T14:03:{len(self.rows):02d}")
            self.rows.append(linha)
            gravados.append(dict(linha))
        return _Resposta(gravados)


class _BucketFake:
    def __init__(self, dono: _StorageFake, bucket: str):
        self.dono = dono
        self.bucket = bucket

    def upload(self, path, content, _opcoes=None):
        self.dono.arquivos[f"{self.bucket}/{path}"] = content
        self.dono.uploads.append({"path": f"{self.bucket}/{path}", "opcoes": dict(_opcoes or {})})

    def remove(self, paths):
        for path in paths:
            self.dono.arquivos.pop(f"{self.bucket}/{path}", None)
        return [{"name": p} for p in paths]

    def create_signed_url(self, path, expires_in):
        chave = f"{self.bucket}/{path}"
        if chave not in self.dono.arquivos:
            raise RuntimeError("Objeto inexistente no storage")
        self.dono.assinaturas.append({"path": chave, "expires_in": expires_in})
        return {"signedURL": f"https://storage.local/{chave}?token=assinado&exp={expires_in}"}

    def get_public_url(self, path):
        self.dono.publicas.append(f"{self.bucket}/{path}")
        return f"https://storage.local/public/{self.bucket}/{path}"


class _StorageFake:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}
        self.uploads: list[dict] = []
        self.assinaturas: list[dict] = []
        self.publicas: list[str] = []

    def from_(self, bucket: str):
        return _BucketFake(self, bucket)


class _SupabaseFake:
    def __init__(self):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_emails_recebidos": [],
            "ouvidoria_emails_recebidos_anexos": [],
            "ouvidoria_acessos": [],
        }
        self.storage = _StorageFake()
        self.consultas: list[str] = []

    def table(self, nome: str):
        return _TabelaFake(self, nome)


class _ResendFake:
    """A função única de leitura do Resend, dublada. Cada e-mail responde o que
    o teste mandar; o que não foi configurado é leitura que falhou."""

    def __init__(self):
        self.respostas: dict[str, EmailDoResend | Exception] = {}
        self.chamadas: list[str] = []

    def __call__(self, email_id: str) -> EmailDoResend:
        self.chamadas.append(email_id)
        resposta = self.respostas.get(email_id, LeituraDoResendError("não configurado no teste"))
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def _client(monkeypatch, participante: dict | None = OUVIDOR):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhooks_router.router, prefix="/api")
    app.include_router(triagem_router.router, prefix="/api")

    supabase = _SupabaseFake()
    resend = _ResendFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(email_service, "ler_email_recebido", resend)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase, resend


def _evento(
    email_id: str = "em_0001",
    *,
    remetente: str = "Joana da Silva <joana.silva@gmail.com>",
    assunto: str = "Demora na recepção do ambulatório",
    anexos: list[dict] | None = None,
    tipo: str = "email.received",
) -> dict:
    """O corpo do evento `email.received`, no formato que o Resend documenta:
    só metadados, sem corpo nem binário (quem busca é o app, no ato)."""
    return {
        "type": tipo,
        "created_at": "2026-09-10T14:02:11.000Z",
        "data": {
            "email_id": email_id,
            "created_at": "2026-09-10T14:02:10.000Z",
            "from": remetente,
            "to": ["ouvidoria@inbound.hospitalsaomatheus.cloud"],
            "cc": [],
            "bcc": [],
            "message_id": "<CAF+joana@mail.gmail.com>",
            "subject": assunto,
            "attachments": anexos
            if anexos is not None
            else [{"id": "at_1", "filename": "laudo.pdf", "content_type": "application/pdf"}],
        },
    }


def _lido(
    texto: str = "Esperei três horas na recepção sem informação nenhuma.",
    *,
    html: str | None = "<p>Esperei três horas na recepção sem informação nenhuma.</p>",
    anexos: tuple[AnexoDoResend, ...] | None = None,
) -> EmailDoResend:
    return EmailDoResend(
        texto=texto,
        html=html,
        cabecalhos={"message-id": "<CAF+joana@mail.gmail.com>", "reply-to": "joana.silva@gmail.com"},
        anexos=anexos
        if anexos is not None
        else (AnexoDoResend(id="at_1", filename="laudo.pdf", content_type="application/pdf", conteudo=PDF),),
    )


def _assinatura(corpo: bytes, *, msg_id: str = "msg_2Xy", timestamp: int | None = None, segredo: str = SEGREDO):
    """Os três cabeçalhos do svix: `{id}.{timestamp}.{corpo}` assinado com a
    chave decodificada do segredo, em base64, com o prefixo de versão."""
    carimbo = str(int(time.time()) if timestamp is None else timestamp)
    chave = base64.b64decode(segredo.removeprefix("whsec_"))
    conteudo = f"{msg_id}.{carimbo}.".encode() + corpo
    assinatura = base64.b64encode(hmac.new(chave, conteudo, hashlib.sha256).digest()).decode("ascii")
    return {"svix-id": msg_id, "svix-timestamp": carimbo, "svix-signature": f"v1,{assinatura}"}


def _entregar(cliente: TestClient, evento: dict, *, cabecalhos: dict | None = None):
    corpo = json.dumps(evento).encode("utf-8")
    headers = {"Content-Type": "application/json"} | (cabecalhos if cabecalhos is not None else _assinatura(corpo))
    return cliente.post("/api/webhooks/resend", content=corpo, headers=headers)


# ─── Seam 1: o webhook ───────────────────────────────────────────────────────


class TestOEmailChegaEApareceNaTriagem:
    def test_email_assinado_aparece_na_triagem_com_corpo_cabecalho_e_anexos(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()

        r = _entregar(cliente, _evento())

        assert r.status_code == 200, r.text
        assert resend.chamadas == ["em_0001"]

        lista = cliente.get("/api/ouvidoria/triagem-email")
        assert lista.status_code == 200, lista.text
        [item] = lista.json()["emails"]
        assert item["remetente_endereco"] == "joana.silva@gmail.com"
        assert item["remetente_nome"] == "Joana da Silva"
        assert item["assunto"] == "Demora na recepção do ambulatório"
        assert item["recebido_em"].startswith("2026-09-10T14:02:10")
        assert item["estado"] == "pendente"
        assert item["quantidade_de_anexos"] == 1
        assert item["incompleto"] is False

        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}")
        assert aberto.status_code == 200, aberto.text
        corpo = aberto.json()
        assert corpo["corpo_texto"] == "Esperei três horas na recepção sem informação nenhuma."
        assert corpo["cabecalhos"]["message-id"] == "<CAF+joana@mail.gmail.com>"
        assert corpo["destinatarios"] == ["ouvidoria@inbound.hospitalsaomatheus.cloud"]
        assert [a["filename"] for a in corpo["anexos"]] == ["laudo.pdf"]
        assert corpo["anexos"][0]["disponivel"] is True
        # O binário foi baixado no ato e guardado no bucket privado da Ouvidoria.
        assert list(supabase.storage.arquivos.values()) == [PDF]
