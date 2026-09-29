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
from dataclasses import dataclass

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
from app.services import ouvidoria_triagem_email as triagem  # noqa: E402
from app.services.email_service import (  # noqa: E402
    AnexoAcimaDoTetoError,
    AnexoDoResend,
    EmailDoResend,
    LeituraDoResendError,
)

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


@dataclass(frozen=True)
class _AnexoDeTeste(AnexoDoResend):
    """O anexo como a leitura devolve, com o binário que o download dublado
    entrega (ou a falha que ele levanta)."""

    binario: bytes | Exception | None = None


def _anexo(anexo_id: str, filename: str, content_type: str, binario: bytes | Exception, *, tamanho=...):
    declarado = (len(binario) if isinstance(binario, bytes) else None) if tamanho is ... else tamanho
    return _AnexoDeTeste(
        id=anexo_id,
        filename=filename,
        content_type=content_type,
        tamanho=declarado,
        download_url=f"https://cdn.resend.test/{anexo_id}",
        binario=binario,
    )


class _ResendFake:
    """A leitura do Resend e o download do anexo, dublados. Cada e-mail
    responde o que o teste mandar; o que não foi configurado é leitura que
    falhou. O download honra o teto como o real: passou, levanta."""

    def __init__(self):
        self.respostas: dict[str, EmailDoResend | Exception] = {}
        self.chamadas: list[str] = []
        self.downloads: list[tuple[str, int]] = []

    def baixar(self, anexo: AnexoDoResend, *, limite_bytes: int) -> bytes:
        self.downloads.append((anexo.id, limite_bytes))
        binario = getattr(anexo, "binario", None)
        if isinstance(binario, Exception):
            raise binario
        if binario is None:
            raise LeituraDoResendError("sem binário no teste")
        if len(binario) > limite_bytes:
            raise AnexoAcimaDoTetoError("binário acima do teto")
        return binario

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
    monkeypatch.setattr(email_service, "baixar_anexo_recebido", resend.baixar)
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
        anexos=anexos if anexos is not None else (_anexo("at_1", "laudo.pdf", "application/pdf", PDF),),
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

    def test_o_mesmo_evento_duas_vezes_gera_um_item_so_e_sucesso_nas_duas(self, monkeypatch):
        """O Resend reentrega o que acha que falhou, e o svix pode mandar a
        mesma entrega de novo. O e-mail é um só, e a triagem também."""
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()

        primeira = _entregar(cliente, _evento())
        segunda = _entregar(cliente, _evento())

        assert primeira.status_code == 200, primeira.text
        assert segunda.status_code == 200, segunda.text
        assert segunda.json()["desfecho"] == "duplicado"
        assert len(supabase.tabelas["ouvidoria_emails_recebidos"]) == 1
        assert len(supabase.tabelas["ouvidoria_emails_recebidos_anexos"]) == 1
        # A reentrega de item completo não gasta cota nem tempo no Resend.
        assert resend.chamadas == ["em_0001"]
        assert len(cliente.get("/api/ouvidoria/triagem-email").json()["emails"]) == 1

    def test_evento_que_nao_e_email_recebido_e_ignorado_sem_gravar(self, monkeypatch):
        """O mesmo endpoint do Resend pode receber os eventos do e-mail que o
        app ENVIA. Eles não são triagem."""
        cliente, supabase, resend = _client(monkeypatch)

        r = _entregar(cliente, _evento(tipo="email.delivered"))

        assert r.status_code == 200
        assert r.json() == {"ignorado": "evento"}
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []
        assert resend.chamadas == []

    def test_remetente_do_dominio_do_hospital_entra_com_a_marca_interno(self, monkeypatch):
        """Resposta de área e e-mail de colega chegam na mesma caixa. A marca
        ajuda o ouvidor a não confundir isso com manifestação."""
        cliente, _, resend = _client(monkeypatch)
        remetentes = {
            "em_interno": "Faturamento <faturamento@hospitalsaomatheus.com.br>",
            "em_sub": "ti@sistemas.hospitalsaomatheus.com.br",
            "em_fora": "Joana <joana@gmail.com>",
            # O domínio no fim do nome de outro domínio não é o hospital.
            "em_parecido": "golpe@falsohospitalsaomatheus.com.br",
        }
        for email_id, remetente in remetentes.items():
            resend.respostas[email_id] = _lido(anexos=())
            assert _entregar(cliente, _evento(email_id, remetente=remetente, anexos=[])).status_code == 200

        emails = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        marcas = {e["remetente_endereco"]: e["interno"] for e in emails}
        assert marcas == {
            "faturamento@hospitalsaomatheus.com.br": True,
            "ti@sistemas.hospitalsaomatheus.com.br": True,
            "joana@gmail.com": False,
            "golpe@falsohospitalsaomatheus.com.br": False,
        }


class TestAAssinaturaGuardaAPorta:
    """A porta é pública e não tem login: a assinatura do Resend é a única
    prova de que a entrega veio dele. Sem ela, qualquer um poria e-mail falso
    na triagem."""

    def test_assinatura_invalida_e_recusada_e_nada_e_gravado(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()
        corpo = json.dumps(_evento()).encode("utf-8")
        outro_segredo = "whsec_" + base64.b64encode(b"outro-segredo-que-nao-e-o-nosso!").decode("ascii")

        r = _entregar(cliente, _evento(), cabecalhos=_assinatura(corpo, segredo=outro_segredo))

        assert r.status_code == 401
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []
        assert supabase.storage.arquivos == {}
        assert resend.chamadas == []

    def test_corpo_alterado_depois_de_assinado_e_recusado(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()
        assinado = json.dumps(_evento()).encode("utf-8")

        r = _entregar(cliente, _evento(assunto="Assunto trocado no caminho"), cabecalhos=_assinatura(assinado))

        assert r.status_code == 401
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []

    def test_entrega_sem_os_cabecalhos_do_svix_e_recusada(self, monkeypatch):
        cliente, supabase, _ = _client(monkeypatch)

        r = _entregar(cliente, _evento(), cabecalhos={})

        assert r.status_code == 401
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []

    def test_entrega_assinada_mas_velha_e_recusada(self, monkeypatch):
        """Uma entrega capturada não pode valer para sempre: o carimbo de tempo
        entra na assinatura e tem janela de cinco minutos."""
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()
        corpo = json.dumps(_evento()).encode("utf-8")

        r = _entregar(cliente, _evento(), cabecalhos=_assinatura(corpo, timestamp=int(time.time()) - 3600))

        assert r.status_code == 401
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []

    def test_segredo_ausente_recusa_tudo_e_nada_e_gravado(self, monkeypatch):
        """Fail-closed: sem o segredo não há o que conferir, e aceitar seria a
        porta aberta com aparência de guarda."""
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido()
        monkeypatch.setattr(settings, "resend_webhook_secret", "")

        r = _entregar(cliente, _evento())

        assert r.status_code == 503
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []
        assert resend.chamadas == []

    def test_segredo_que_nao_decodifica_tambem_fecha_a_porta(self, monkeypatch):
        cliente, supabase, _ = _client(monkeypatch)
        monkeypatch.setattr(settings, "resend_webhook_secret", "whsec_isto nao e base64!")

        r = _entregar(cliente, _evento(), cabecalhos={"svix-id": "x", "svix-timestamp": "1", "svix-signature": "v1,x"})

        assert r.status_code == 503
        assert supabase.tabelas["ouvidoria_emails_recebidos"] == []


class TestOQueVeioNaoSePerde:
    """Falha ao buscar corpo ou anexo grava o item com o que veio, marcado como
    incompleto; a reentrega do Resend completa em vez de duplicar."""

    def test_anexo_que_falha_deixa_o_item_visivel_e_incompleto_e_a_reentrega_completa(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        anexos = [
            {"id": "at_1", "filename": "laudo.pdf", "content_type": "application/pdf"},
            {"id": "at_2", "filename": "foto.jpg", "content_type": "image/jpeg"},
        ]
        resend.respostas["em_0001"] = _lido(
            anexos=(
                _anexo("at_1", "laudo.pdf", "application/pdf", PDF),
                _anexo("at_2", "foto.jpg", "image/jpeg", LeituraDoResendError("ReadTimeout"), tamanho=None),
            )
        )

        primeira = _entregar(cliente, _evento(anexos=anexos))

        # O não-2xx é o que faz o Resend reentregar com espera crescente.
        assert primeira.status_code == 503
        [item] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert item["incompleto"] is True
        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()
        assert aberto["corpo_texto"] == "Esperei três horas na recepção sem informação nenhuma."
        assert {a["filename"]: a["disponivel"] for a in aberto["anexos"]} == {"laudo.pdf": True, "foto.jpg": False}

        resend.respostas["em_0001"] = _lido(
            anexos=(
                _anexo("at_1", "laudo.pdf", "application/pdf", PDF),
                _anexo("at_2", "foto.jpg", "image/jpeg", b"\xff\xd8jpeg"),
            )
        )
        segunda = _entregar(cliente, _evento(anexos=anexos))

        assert segunda.status_code == 200, segunda.text
        assert segunda.json()["desfecho"] == "completado"
        [item] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert item["incompleto"] is False
        assert item["quantidade_de_anexos"] == 2
        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()
        assert {a["filename"]: a["disponivel"] for a in aberto["anexos"]} == {"laudo.pdf": True, "foto.jpg": True}
        # O laudo, que já estava guardado, não subiu de novo, nem foi baixado.
        assert sorted(supabase.storage.arquivos.values()) == sorted([PDF, b"\xff\xd8jpeg"])
        assert [anexo_id for anexo_id, _ in resend.downloads] == ["at_1", "at_2", "at_2"]

    def test_corpo_que_nao_vem_grava_o_cabecalho_e_a_reentrega_traz_o_corpo(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = LeituraDoResendError("HTTPStatusError")

        primeira = _entregar(cliente, _evento())

        assert primeira.status_code == 503
        [item] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert item["incompleto"] is True
        assert item["assunto"] == "Demora na recepção do ambulatório"
        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()
        assert aberto["corpo_texto"] is None
        # O anexo anunciado no evento aparece, sem binário.
        assert [(a["filename"], a["disponivel"]) for a in aberto["anexos"]] == [("laudo.pdf", False)]

        resend.respostas["em_0001"] = _lido()
        segunda = _entregar(cliente, _evento())

        assert segunda.status_code == 200, segunda.text
        assert len(supabase.tabelas["ouvidoria_emails_recebidos"]) == 1
        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()
        assert aberto["incompleto"] is False
        assert aberto["corpo_texto"] == "Esperei três horas na recepção sem informação nenhuma."
        assert [(a["filename"], a["disponivel"]) for a in aberto["anexos"]] == [("laudo.pdf", True)]

    def test_reentrega_nao_devolve_nada_a_um_email_ja_decidido(self, monkeypatch):
        """Item decidido (o descarte apaga corpo e anexos) não é completado por
        reentrega atrasada: o corpo apagado não pode voltar pela porta dos
        fundos."""
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = LeituraDoResendError("HTTPStatusError")
        _entregar(cliente, _evento())
        linha = supabase.tabelas["ouvidoria_emails_recebidos"][0]
        linha.update({"estado": "descartado", "decidido_em": "2026-09-11T09:00:00+00:00"})

        resend.respostas["em_0001"] = _lido()
        r = _entregar(cliente, _evento())

        assert r.status_code == 200
        assert linha["corpo_texto"] is None
        assert resend.chamadas == ["em_0001"]


# ─── Seam 2: as rotas da triagem ─────────────────────────────────────────────


def _um_email_na_triagem(monkeypatch, participante):
    cliente, supabase, resend = _client(monkeypatch, participante)
    resend.respostas["em_0001"] = _lido()
    assert _entregar(cliente, _evento()).status_code == 200
    email_id = supabase.tabelas["ouvidoria_emails_recebidos"][0]["id"]
    anexo_id = supabase.tabelas["ouvidoria_emails_recebidos_anexos"][0]["id"]
    return cliente, supabase, email_id, anexo_id


class TestSoOPerfilDaOuvidoriaVe:
    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_perfil_sem_ouvidoria_recebe_403_na_listagem_no_item_e_no_anexo(self, monkeypatch, participante):
        cliente, supabase, email_id, anexo_id = _um_email_na_triagem(monkeypatch, participante)

        assert cliente.get("/api/ouvidoria/triagem-email").status_code == 403
        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").status_code == 403
        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/anexos/{anexo_id}/url").status_code == 403
        assert supabase.storage.assinaturas == []

    @pytest.mark.parametrize("participante", [OUVIDOR, DIRETORIA])
    def test_os_dois_perfis_da_ouvidoria_leem(self, monkeypatch, participante):
        cliente, _, email_id, _ = _um_email_na_triagem(monkeypatch, participante)

        assert cliente.get("/api/ouvidoria/triagem-email").status_code == 200
        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").status_code == 200

    def test_abrir_o_item_entra_no_log_de_acesso_com_o_email_como_alvo(self, monkeypatch):
        cliente, supabase, email_id, _ = _um_email_na_triagem(monkeypatch, OUVIDOR)

        cliente.get(f"/api/ouvidoria/triagem-email/{email_id}")

        [acesso] = supabase.tabelas["ouvidoria_acessos"]
        assert acesso["email_recebido_id"] == email_id
        assert acesso["ator_id"] == "P10"
        assert acesso["ator_nome"] == "Marta Ouvidora"
        assert acesso["acao"] == "ver_email_recebido"
        assert "manifestacao_id" not in acesso


class TestOAnexoSoSaiPorUrlAssinada:
    def test_anexo_do_email_e_lido_por_url_assinada_nunca_por_caminho_publico(self, monkeypatch):
        cliente, supabase, email_id, anexo_id = _um_email_na_triagem(monkeypatch, OUVIDOR)

        r = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/anexos/{anexo_id}/url")

        assert r.status_code == 200, r.text
        assert "token=assinado" in r.json()["url"]
        assert r.json()["filename"] == "laudo.pdf"
        assert r.json()["expira_em_segundos"] == 1800
        [assinatura] = supabase.storage.assinaturas
        assert assinatura["path"].startswith("anexos-ouvidoria/email-recebido-")
        assert supabase.storage.publicas == []
        # Nem a lista nem o item entregam caminho de storage: sem a rota que
        # assina, não há como chegar ao binário.
        assert "storage_path" not in json.dumps(cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").json())
        assert "email-recebido-" not in json.dumps(cliente.get("/api/ouvidoria/triagem-email").json())

    def test_anexo_de_outro_email_nao_abre_por_este(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_a"] = _lido()
        resend.respostas["em_b"] = _lido()
        _entregar(cliente, _evento("em_a"))
        _entregar(cliente, _evento("em_b"))
        email_a = supabase.tabelas["ouvidoria_emails_recebidos"][0]["id"]
        anexo_de_b = supabase.tabelas["ouvidoria_emails_recebidos_anexos"][1]["id"]

        r = cliente.get(f"/api/ouvidoria/triagem-email/{email_a}/anexos/{anexo_de_b}/url")

        assert r.status_code == 404
        assert supabase.storage.assinaturas == []

    def test_anexo_fora_do_catalogo_nao_vai_ao_bucket_e_fica_com_o_motivo(self, monkeypatch):
        """O tipo declarado é de quem mandou. Um `.html` servido como
        `text/html` pela URL assinada abriria como página: fora do catálogo da
        Ouvidoria, o anexo nem é baixado."""
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido(anexos=(_anexo("at_1", "fatura.html", "text/html", b"<script>"),))

        r = _entregar(cliente, _evento(anexos=[{"id": "at_1", "filename": "fatura.html", "content_type": "text/html"}]))

        assert r.status_code == 200, r.text
        assert supabase.storage.uploads == []
        assert resend.downloads == []
        [item] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert item["incompleto"] is False
        [anexo] = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()["anexos"]
        assert anexo["disponivel"] is False
        assert anexo["motivo_indisponivel"] == triagem.MOTIVO_TIPO


MB = 1024 * 1024


class TestOAnexoTemTeto:
    """O remetente é anônimo, e o teto é do app (revisão de segurança do PR
    #899): anexo acima do teto vira linha sem binário, com motivo, que não
    deixa o item incompleto, e um anexo por vez, só os que faltam."""

    def test_anexo_declarado_acima_do_teto_nem_e_baixado_e_nao_deixa_o_item_incompleto(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        grande = _anexo("at_2", "gravacao.wav", "audio/wav", b"x", tamanho=triagem.LIMITE_BYTES_POR_ANEXO + 1)
        resend.respostas["em_0001"] = _lido(anexos=(_anexo("at_1", "laudo.pdf", "application/pdf", PDF), grande))

        r = _entregar(cliente, _evento(anexos=[]))

        assert r.status_code == 200, r.text
        assert [anexo_id for anexo_id, _ in resend.downloads] == ["at_1"]
        [item] = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]
        assert item["incompleto"] is False
        anexos = cliente.get(f"/api/ouvidoria/triagem-email/{item['id']}").json()["anexos"]
        assert {a["filename"]: (a["disponivel"], a["motivo_indisponivel"]) for a in anexos} == {
            "laudo.pdf": (True, None),
            "gravacao.wav": (False, triagem.MOTIVO_GRANDE),
        }
        assert list(supabase.storage.arquivos.values()) == [PDF]

    def test_anexo_sem_tamanho_declarado_para_no_teto_durante_o_download(self, monkeypatch):
        monkeypatch.setattr(triagem, "LIMITE_BYTES_POR_ANEXO", 10)
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido(anexos=(_anexo("at_1", "foto.jpg", "image/jpeg", b"y" * 11, tamanho=None),))

        r = _entregar(cliente, _evento(anexos=[]))

        assert r.status_code == 200, r.text
        assert resend.downloads == [("at_1", 10)]
        assert supabase.storage.uploads == []
        [linha] = supabase.tabelas["ouvidoria_emails_recebidos_anexos"]
        assert linha["storage_path"] is None
        assert linha["motivo_sem_binario"] == triagem.MOTIVO_GRANDE

    def test_anexo_recusado_nao_e_baixado_de_novo_na_reentrega(self, monkeypatch):
        cliente, _supabase, resend = _client(monkeypatch)
        grande = _anexo("at_2", "gravacao.wav", "audio/wav", b"x", tamanho=triagem.LIMITE_BYTES_POR_ANEXO + 1)
        falha = _anexo("at_1", "laudo.pdf", "application/pdf", LeituraDoResendError("ReadTimeout"), tamanho=None)
        resend.respostas["em_0001"] = _lido(anexos=(falha, grande))

        assert _entregar(cliente, _evento(anexos=[])).status_code == 503
        resend.respostas["em_0001"] = _lido(anexos=(_anexo("at_1", "laudo.pdf", "application/pdf", PDF), grande))
        assert _entregar(cliente, _evento(anexos=[])).status_code == 200

        assert [anexo_id for anexo_id, _ in resend.downloads] == ["at_1", "at_1"]

    def test_passado_o_numero_maximo_de_anexos_o_resto_fica_com_o_motivo(self, monkeypatch):
        monkeypatch.setattr(triagem, "LIMITE_ANEXOS_POR_EMAIL", 2)
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido(
            anexos=tuple(_anexo(f"at_{i}", f"foto{i}.jpg", "image/jpeg", b"\xff\xd8") for i in range(1, 4))
        )

        r = _entregar(cliente, _evento(anexos=[]))

        assert r.status_code == 200, r.text
        assert [anexo_id for anexo_id, _ in resend.downloads] == ["at_1", "at_2"]
        motivos = {
            a["resend_anexo_id"]: a["motivo_sem_binario"] for a in supabase.tabelas["ouvidoria_emails_recebidos_anexos"]
        }
        assert motivos == {"at_1": None, "at_2": None, "at_3": triagem.MOTIVO_QUANTIDADE}

    def test_o_total_do_email_tem_teto_e_o_download_so_pede_o_que_resta(self, monkeypatch):
        monkeypatch.setattr(triagem, "LIMITE_BYTES_POR_EMAIL", 10)
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido(
            anexos=(
                _anexo("at_1", "a.pdf", "application/pdf", b"1" * 6),
                _anexo("at_2", "b.pdf", "application/pdf", b"2" * 6, tamanho=None),
                _anexo("at_3", "c.pdf", "application/pdf", b"3" * 6),
            )
        )

        r = _entregar(cliente, _evento(anexos=[]))

        assert r.status_code == 200, r.text
        # O segundo, sem tamanho declarado, só pode trazer os 4 bytes que restam.
        assert resend.downloads == [("at_1", 10), ("at_2", 4)]
        motivos = {
            a["resend_anexo_id"]: a["motivo_sem_binario"] for a in supabase.tabelas["ouvidoria_emails_recebidos_anexos"]
        }
        assert motivos == {"at_1": None, "at_2": triagem.MOTIVO_TOTAL, "at_3": triagem.MOTIVO_TOTAL}


class TestOHtmlNuncaSaiParaATela:
    def test_o_item_entrega_o_corpo_em_texto_e_nunca_o_html(self, monkeypatch):
        cliente, supabase, resend = _client(monkeypatch)
        resend.respostas["em_0001"] = _lido(texto="texto puro", html='<img src=x onerror="alert(1)">')
        _entregar(cliente, _evento())
        email_id = supabase.tabelas["ouvidoria_emails_recebidos"][0]["id"]

        aberto = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").json()

        # Guardado, para as fatias seguintes e para a auditoria...
        assert supabase.tabelas["ouvidoria_emails_recebidos"][0]["corpo_html"] == '<img src=x onerror="alert(1)">'
        # ...e fora da resposta.
        assert "corpo_html" not in aberto
        assert "onerror" not in json.dumps(aberto)
        assert aberto["corpo_texto"] == "texto puro"


class TestAOrdemDaTriagem:
    def test_pendentes_primeiro_e_o_mais_antigo_primeiro(self, monkeypatch):
        cliente, supabase, _ = _client(monkeypatch)
        base = {"remetente_nome": None, "assunto": "", "incompleto": False, "interno": False}
        supabase.tabelas["ouvidoria_emails_recebidos"].extend(
            [
                base
                | {"id": "e1", "remetente_endereco": "a@x.com", "recebido_em": "2026-09-01T10:00:00+00:00"}
                | {"estado": "descartado", "decidido_em": "2026-09-02T10:00:00+00:00"},
                base
                | {"id": "e2", "remetente_endereco": "b@x.com", "recebido_em": "2026-09-05T10:00:00+00:00"}
                | {"estado": "pendente"},
                base
                | {"id": "e3", "remetente_endereco": "c@x.com", "recebido_em": "2026-09-03T10:00:00+00:00"}
                | {"estado": "pendente"},
            ]
        )

        emails = cliente.get("/api/ouvidoria/triagem-email").json()["emails"]

        assert [e["id"] for e in emails] == ["e3", "e2", "e1"]


# ─── A função única de leitura do Resend ────────────────────────────────────


class TestALeituraDoResend:
    """A leitura real, contra um transporte dublado (`httpx.MockTransport` não
    abre socket). Prova o contrato com a API de recebimento do Resend: onde
    pede, com que chave, e que o anexo que falha volta com erro em vez de
    derrubar a leitura."""

    @staticmethod
    def _cliente_http(rotas: dict[str, httpx.Response], pedidos: list[httpx.Request]) -> httpx.Client:
        def responder(pedido: httpx.Request) -> httpx.Response:
            pedidos.append(pedido)
            return rotas.get(str(pedido.url), httpx.Response(404))

        return httpx.Client(transport=httpx.MockTransport(responder))

    def test_busca_corpo_cabecalhos_e_os_metadados_de_cada_anexo_sem_baixar(self, monkeypatch):
        monkeypatch.setattr(settings, "resend_inbound_api_key", "re_leitura")
        monkeypatch.setattr(settings, "resend_inbound_base_url", "https://api.resend.test")
        base = "https://api.resend.test/emails/receiving/em_0001"
        pedidos: list[httpx.Request] = []
        rotas = {
            base: httpx.Response(
                200,
                json={
                    "object": "email",
                    "id": "em_0001",
                    "text": "corpo em texto",
                    "html": "<p>corpo</p>",
                    "message_id": "<abc@mail>",
                    "reply_to": ["joana@gmail.com"],
                    "headers": {"Auto-Submitted": "no", "Received": "from mx.google.com", "DKIM-Signature": "v=1"},
                    "attachments": [
                        {"id": "at_1", "filename": "laudo.pdf", "content_type": "application/pdf", "size": 30},
                        {"id": "at_2", "filename": "foto.jpg", "content_type": "image/jpeg"},
                    ],
                },
            ),
            f"{base}/attachments": httpx.Response(
                200,
                json={
                    "object": "list",
                    "data": [
                        {"id": "at_1", "download_url": "https://cdn.resend.test/at_1?sig=1"},
                        {"id": "at_2", "download_url": "https://cdn.resend.test/at_2?sig=2"},
                    ],
                },
            ),
            "https://cdn.resend.test/at_1?sig=1": httpx.Response(200, content=PDF),
            "https://cdn.resend.test/at_2?sig=2": httpx.Response(500),
        }

        with self._cliente_http(rotas, pedidos) as http:
            lido = email_service.ler_email_recebido("em_0001", cliente=http)

        assert lido.texto == "corpo em texto"
        assert lido.html == "<p>corpo</p>"
        assert lido.cabecalhos == {
            "auto-submitted": "no",
            "message-id": "<abc@mail>",
            "reply-to": "joana@gmail.com",
        }
        assert [(a.id, a.tamanho, a.download_url) for a in lido.anexos] == [
            ("at_1", 30, "https://cdn.resend.test/at_1?sig=1"),
            ("at_2", None, "https://cdn.resend.test/at_2?sig=2"),
        ]
        assert {p.headers["authorization"] for p in pedidos} == {"Bearer re_leitura"}
        # Nenhum binário é baixado na leitura: o download é um por vez, com teto.
        assert all(p.url.host == "api.resend.test" for p in pedidos)

    def test_o_download_do_anexo_vai_sem_a_chave_e_traz_o_binario(self, monkeypatch):
        pedidos: list[httpx.Request] = []
        rotas = {"https://cdn.resend.test/at_1?sig=1": httpx.Response(200, content=PDF)}
        anexo = AnexoDoResend("at_1", "laudo.pdf", "application/pdf", download_url="https://cdn.resend.test/at_1?sig=1")

        with self._cliente_http(rotas, pedidos) as http:
            assert email_service.baixar_anexo_recebido(anexo, limite_bytes=1024, cliente=http) == PDF

        # A chave do Resend não vai para o host que serve o binário.
        assert all("authorization" not in p.headers for p in pedidos)

    def test_o_download_para_no_teto_mesmo_sem_content_length(self, monkeypatch):
        entregues: list[int] = []

        def pedacos():
            for _ in range(100):
                entregues.append(1)
                yield b"z" * 1024

        rotas = {"https://cdn.resend.test/at_1?sig=1": httpx.Response(200, content=pedacos())}
        anexo = AnexoDoResend("at_1", "gravacao.wav", "audio/wav", download_url="https://cdn.resend.test/at_1?sig=1")

        with self._cliente_http(rotas, []) as http, pytest.raises(AnexoAcimaDoTetoError):
            email_service.baixar_anexo_recebido(anexo, limite_bytes=4 * 1024, cliente=http)

        # Parou no pedaço que passou: os outros 95 KB nem foram lidos.
        assert len(entregues) == 5

    def test_content_length_acima_do_teto_recusa_antes_de_ler_o_corpo(self, monkeypatch):
        rotas = {
            "https://cdn.resend.test/at_1?sig=1": httpx.Response(
                200, content=b"a" * 10, headers={"Content-Length": str(50 * MB)}
            )
        }
        anexo = AnexoDoResend("at_1", "gravacao.wav", "audio/wav", download_url="https://cdn.resend.test/at_1?sig=1")

        with self._cliente_http(rotas, []) as http, pytest.raises(AnexoAcimaDoTetoError):
            email_service.baixar_anexo_recebido(anexo, limite_bytes=MB, cliente=http)

    @pytest.mark.parametrize("url", [None, "http://cdn.resend.test/at_1"])
    def test_download_sem_link_https_nao_acontece(self, monkeypatch, url):
        anexo = AnexoDoResend("at_1", "laudo.pdf", "application/pdf", download_url=url)
        pedidos: list[httpx.Request] = []

        with self._cliente_http({}, pedidos) as http, pytest.raises(LeituraDoResendError):
            email_service.baixar_anexo_recebido(anexo, limite_bytes=MB, cliente=http)

        assert pedidos == []

    def test_download_com_status_de_erro_levanta_erro_de_leitura(self, monkeypatch):
        rotas = {"https://cdn.resend.test/at_1?sig=1": httpx.Response(500)}
        anexo = AnexoDoResend("at_1", "laudo.pdf", "application/pdf", download_url="https://cdn.resend.test/at_1?sig=1")

        with self._cliente_http(rotas, []) as http, pytest.raises(LeituraDoResendError, match="HTTPStatusError"):
            email_service.baixar_anexo_recebido(anexo, limite_bytes=MB, cliente=http)

    def test_email_que_a_api_nao_devolve_levanta_erro_de_leitura(self, monkeypatch):
        monkeypatch.setattr(settings, "resend_inbound_api_key", "re_leitura")
        monkeypatch.setattr(settings, "resend_inbound_base_url", "https://api.resend.test")

        with self._cliente_http({}, []) as http, pytest.raises(LeituraDoResendError):
            email_service.ler_email_recebido("em_inexistente", cliente=http)

    def test_sem_chave_nenhuma_nao_ha_leitura(self, monkeypatch):
        monkeypatch.setattr(settings, "resend_inbound_api_key", "")
        monkeypatch.setattr(settings, "resend_api_key", "")

        with pytest.raises(LeituraDoResendError):
            email_service.ler_email_recebido("em_0001")

    def test_sem_chave_de_leitura_propria_usa_a_chave_do_resend_da_casa(self, monkeypatch):
        monkeypatch.setattr(settings, "resend_inbound_api_key", "")
        monkeypatch.setattr(settings, "resend_api_key", "re_da_casa")
        monkeypatch.setattr(settings, "resend_inbound_base_url", "https://api.resend.test")
        pedidos: list[httpx.Request] = []
        rotas = {"https://api.resend.test/emails/receiving/em_0001": httpx.Response(200, json={"text": "oi"})}

        with self._cliente_http(rotas, pedidos) as http:
            lido = email_service.ler_email_recebido("em_0001", cliente=http)

        assert lido.texto == "oi"
        assert pedidos[0].headers["authorization"] == "Bearer re_da_casa"


# ─── A migration ─────────────────────────────────────────────────────────────


class TestMigration:
    TABELAS = ("ouvidoria_emails_recebidos", "ouvidoria_emails_recebidos_anexos")

    @pytest.fixture
    def comandos(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__), "..", "..", "supabase", "migrations", "112_ouvidoria_triagem_email.sql"
        )
        with open(caminho, encoding="utf-8") as f:
            ddl = f.read()
        # Só o SQL, sem a prosa dos comentários.
        return "\n".join(linha for linha in ddl.lower().splitlines() if not linha.strip().startswith("--"))

    @pytest.mark.parametrize("tabela", TABELAS)
    def test_cada_tabela_nasce_com_rls_ligado(self, comandos, tabela):
        assert f"create table if not exists {tabela}" in comandos
        assert f"alter table {tabela} enable row level security" in comandos

    def test_nenhuma_policy(self, comandos):
        """Default-deny: só a service_role do backend passa. Uma policy aqui
        abriria o corpo do e-mail para a anon_key do bundle."""
        assert "create policy" not in comandos

    def test_a_dedup_tem_coluna_unica_no_banco(self, comandos):
        assert "resend_email_id    text not null unique" in comandos

    def test_linha_de_anexo_tem_binario_ou_motivo_nunca_os_dois(self, comandos):
        assert "motivo_sem_binario text" in comandos
        assert "check (storage_path is null or motivo_sem_binario is null)" in comandos

    def test_os_quatro_estados_da_triagem(self, comandos):
        assert "estado in ('pendente', 'virou_manifestacao', 'juntado', 'descartado')" in comandos
