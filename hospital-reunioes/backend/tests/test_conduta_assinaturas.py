"""As assinaturas do Canal de Conduta e o Termo de Confidencialidade e Posse
(issue #1823, PRD #1786, ADR 0097, decisões 2 e 13).

Cadastrar um membro gera o Termo, com o Regimento do Comitê como parte
integrante, e o envia à ClickSign para o e-mail profissional dele. A
assinatura volta pelo webhook (ou pelo "Reconsultar status"), carimba a
Participação e a cópia do PDF assinado fica guardada, cifrada. Sem o Termo
assinado, o membro vê a tela inicial e não abre caso.

A ClickSign é dublê em todo teste daqui (o `.env` local carrega credencial de
produção): as funções que o módulo usa viram dublê e o `httpx` explode se
alguém tentar sair para a rede.
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_lib
import io
import json
import os
import re
import secrets
import sys
from datetime import timedelta
from typing import Any

import httpx
import pdfplumber
import pytest
from conduta_apoio import Banco
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import conduta_comite, conduta_membros, webhooks  # noqa: E402
from app.services import clicksign_service  # noqa: E402
from app.services.conduta import assinaturas, casos, cifra  # noqa: E402
from app.services.conduta import membros as servico_de_membros  # noqa: E402
from app.services.conduta.acesso import hoje_em_sao_paulo  # noqa: E402

ROTA = "/api/comite-de-conduta/membros"
SEGREDO_DO_WEBHOOK = "segredo-de-teste-do-webhook"
RECUSA = {"detail": "Sem acesso a este conteúdo do Canal de Conduta"}
PDF_ASSINADO = b"%PDF-1.4 assinado pelo membro"

HOJE = hoje_em_sao_paulo()
COMITE = {"id": "col-conduta", "slug": "conduta", "nome": "Comitê de Conduta"}
CADASTRO = {"perfil_conduta": "cadastro_de_membros"}


# ═══════════════════════════════════════════════════════════════════════════
# Dublês
# ═══════════════════════════════════════════════════════════════════════════


class _ClickSign:
    """A ClickSign de mentira: anota cada chamada e responde como a de verdade.
    `falhar_em` derruba um passo."""

    def __init__(self):
        self.chamadas: list[tuple] = []
        self.documentos: list[bytes] = []
        self.status: str | None = "running"
        self.falhar_em: str | None = None
        self._n = 0

    def _passo(self, nome: str, *args):
        self.chamadas.append((nome, *args))
        return self.falhar_em != nome

    def create_envelope(self, nome):
        self._n += 1
        return f"env-{self._n}" if self._passo("create_envelope", nome) else None

    def add_document(self, envelope_id, pdf, nome_do_arquivo):
        self.documentos.append(pdf)
        return f"doc-{envelope_id}" if self._passo("add_document", envelope_id, nome_do_arquivo) else None

    def add_signer(self, envelope_id, nome, email):
        return f"sig-{envelope_id}-{email}" if self._passo("add_signer", envelope_id, nome, email) else None

    def create_qualification_requirement(self, envelope_id, documento_id, signatario_id):
        return "req-q" if self._passo("create_qualification_requirement", envelope_id, signatario_id) else None

    def create_auth_requirement(self, envelope_id, documento_id, signatario_id):
        return "req-a" if self._passo("create_auth_requirement", envelope_id, signatario_id) else None

    def activate_envelope(self, envelope_id):
        return self._passo("activate_envelope", envelope_id)

    def notify_signers(self, envelope_id):
        return self._passo("notify_signers", envelope_id)

    def cancel_envelope(self, envelope_id):
        return self._passo("cancel_envelope", envelope_id)

    def get_envelope_status(self, envelope_id):
        self._passo("get_envelope_status", envelope_id)
        return self.status

    def get_signed_document(self, envelope_id):
        return PDF_ASSINADO if self._passo("get_signed_document", envelope_id) else None

    def nomes(self) -> list[str]:
        return [c[0] for c in self.chamadas]


# Os de verdade, guardados antes de qualquer dublê, para o teste do download.
_CLIENTE_HTTP = httpx.Client
_BAIXAR_ASSINADO = clicksign_service.get_signed_document

FUNCOES_DA_CLICKSIGN = (
    "create_envelope",
    "add_document",
    "add_signer",
    "create_qualification_requirement",
    "create_auth_requirement",
    "activate_envelope",
    "notify_signers",
    "cancel_envelope",
    "get_envelope_status",
    "get_signed_document",
)


@pytest.fixture(autouse=True)
def clicksign(monkeypatch) -> _ClickSign:
    """Toda função da ClickSign que o módulo usa vira dublê, e o `httpx`
    explode: nenhum teste daqui chega à ClickSign de verdade."""
    dubla = _ClickSign()
    for nome in FUNCOES_DA_CLICKSIGN:
        monkeypatch.setattr(clicksign_service, nome, getattr(dubla, nome))

    def _rede(*_a, **_kw):
        raise AssertionError("teste tentou sair para a rede")

    monkeypatch.setattr(clicksign_service.httpx, "Client", _rede)
    return dubla


@pytest.fixture(autouse=True)
def _ambiente(monkeypatch):
    limiter._storage.reset()
    monkeypatch.setattr(settings, "conduta_chave_cifra", base64.b64encode(secrets.token_bytes(32)).decode())
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SEGREDO_DO_WEBHOOK)
    monkeypatch.setattr(servico_de_membros, "_enviar_email", lambda *_a, **_kw: True)
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def guardados(monkeypatch) -> dict[tuple[str, str], bytes]:
    """O bucket privado de mentira: (bucket, caminho) -> bytes."""
    arquivos: dict[tuple[str, str], bytes] = {}

    def _subir(_supabase, bucket, caminho, conteudo, _tipo="application/octet-stream"):
        arquivos[(bucket, caminho)] = conteudo
        return True

    monkeypatch.setattr(assinaturas.storage, "upload_private", _subir)
    return arquivos


def _pessoa(pid: str, nome: str | None = None, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome or f"Pessoa {pid}",
        "email": f"{pid.lower()}@hsm.test",
        "role": None,
        "ativo": True,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_conduta": None,
    }
    return {**base, **campos}


def _participacao(pid: str, *, papel="membro", termo=True, **campos) -> dict:
    return {
        "id": f"part-{pid}",
        "colegiado_id": COMITE["id"],
        "participante_id": pid,
        "papel": papel,
        "e_diretor": False,
        "vigencia_inicio": (HOJE - timedelta(days=30)).isoformat(),
        "vigencia_fim": (HOJE + timedelta(days=600)).isoformat(),
        "encerrada_em": None,
        "termo_assinado_em": "2026-10-01T12:00:00+00:00" if termo else None,
        **campos,
    }


class _Cenario:
    def __init__(self, quem: dict, pessoas: list[dict] = (), participacoes: list[dict] = (), **tabelas):
        self.quem = quem
        self.banco = Banco(
            {
                "participantes": [quem, *pessoas],
                "colegiados": [dict(COMITE)],
                "participacoes": [dict(p) for p in participacoes],
                **tabelas,
            }
        )

    def cliente(self) -> TestClient:
        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(conduta_membros.router, prefix="/api")
        app.include_router(conduta_comite.router, prefix="/api")
        app.include_router(webhooks.router, prefix="/api")
        quem = self.quem

        async def _usuario() -> dict[str, Any]:
            return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        return TestClient(app)

    def tabela(self, nome: str) -> list[dict]:
        return self.banco.tabelas.get(nome, [])

    def participacao(self, pid: str) -> dict:
        [linha] = [p for p in self.tabela("participacoes") if p["participante_id"] == pid]
        return linha

    def assinaturas(self) -> list[dict]:
        return self.tabela("conduta_assinaturas")

    def incluir(self, pid: str = "N1"):
        corpo = {"participante_id": pid, "papel": "membro", "vigencia_inicio": HOJE.isoformat()}
        return self.cliente().post(ROTA, json=corpo)


def _retorno_da_clicksign(cliente: TestClient, documento_key: str, evento: str = "auto_close"):
    corpo = json.dumps({"event": {"name": evento}, "document": {"key": documento_key}}).encode()
    assinatura = hmac_lib.new(SEGREDO_DO_WEBHOOK.encode(), corpo, hashlib.sha256).hexdigest()
    return cliente.post(
        "/api/webhooks/clicksign",
        content=corpo,
        headers={"content-hmac": f"sha256={assinatura}", "content-type": "application/json"},
    )


def _texto_do_pdf(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as documento:
        texto = "\n".join(pagina.extract_text() or "" for pagina in documento.pages)
    return re.sub(r"\s+", " ", texto)


def _cenario_do_cadastro() -> _Cenario:
    return _Cenario(_pessoa("C1", **CADASTRO), [_pessoa("N1", "Nina Nova", email="nina.nova@hsm.test")])


# ═══════════════════════════════════════════════════════════════════════════
# 1. Cadastrar gera o Termo e o envia à ClickSign
# ═══════════════════════════════════════════════════════════════════════════


class TestCadastroGeraOTermo:
    def test_cadastrar_um_membro_gera_o_termo_e_envia_ao_email_profissional_dele(self, clicksign):
        """Mutante: o cadastro não chamar o envio do Termo."""
        cenario = _cenario_do_cadastro()

        resposta = cenario.incluir()

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["termo"] == "aguardando_assinatura"
        assert resposta.json()["aviso_termo"] is None
        assert clicksign.nomes().count("create_envelope") == 1
        assert [c for c in clicksign.chamadas if c[0] == "add_signer"] == [
            ("add_signer", "env-1", "Nina Nova", "nina.nova@hsm.test")
        ]
        assert "activate_envelope" in clicksign.nomes()
        texto = _texto_do_pdf(clicksign.documentos[0])
        assert "TERMO DE CONFIDENCIALIDADE E POSSE" in texto.upper()
        assert "Nina Nova" in texto
        assert "Regimento do Comitê de Conduta" in texto
        [termo] = cenario.assinaturas()
        assert termo["tipo"] == "termo_de_posse"
        assert termo["participacao_id"] == cenario.participacao("N1")["id"]
        assert termo["signatarios"] == ["N1"]
        assert termo["situacao"] == "enviado"
        assert termo["documento_key"] == "doc-env-1"
        assert termo["id"] in texto

    def test_clicksign_fora_do_ar_mantem_o_cadastro_e_avisa(self, clicksign):
        clicksign.falhar_em = "activate_envelope"
        cenario = _cenario_do_cadastro()

        resposta = cenario.incluir()

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["termo"] == "nao_enviado"
        assert "Reenviar o Termo" in resposta.json()["aviso_termo"]
        [termo] = cenario.assinaturas()
        assert termo["situacao"] == "gerado"

    def test_pessoa_sem_email_fica_cadastrada_e_o_aviso_diz_o_motivo(self, clicksign):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), [_pessoa("N1", email=None)])

        resposta = cenario.incluir()

        assert resposta.status_code == 201, resposta.text
        assert "e-mail" in resposta.json()["aviso_termo"]
        assert clicksign.chamadas == []
        assert cenario.assinaturas() == []

    def test_reenviar_cancela_o_envio_aberto_e_manda_outro(self, clicksign):
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        participacao_id = cenario.participacao("N1")["id"]

        resposta = cenario.cliente().post(f"{ROTA}/{participacao_id}/termo/reenviar")

        assert resposta.status_code == 200, resposta.text
        assert ("cancel_envelope", "env-1") in clicksign.chamadas
        assert [a["situacao"] for a in cenario.assinaturas()] == ["cancelado", "enviado"]
        assert resposta.json()["termo"] == "aguardando_assinatura"

    def test_o_termo_vai_so_com_o_perfil_de_cadastro(self, clicksign):
        cenario = _Cenario(_pessoa("M1"), [_pessoa("N1")], [_participacao("M1")])
        cenario.banco.tabelas["participacoes"].append(_participacao("N1", termo=False))
        cliente = cenario.cliente()

        reenviar = cliente.post(f"{ROTA}/part-N1/termo/reenviar")
        reconsultar = cliente.post(f"{ROTA}/part-N1/termo/reconsultar")

        assert reenviar.status_code == 403 and reenviar.json() == RECUSA
        assert reconsultar.status_code == 403 and reconsultar.json() == RECUSA
        assert clicksign.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. A assinatura volta pelo webhook, e a cópia fica guardada, cifrada
# ═══════════════════════════════════════════════════════════════════════════


class TestRetornoPeloWebhook:
    def test_a_assinatura_volta_pelo_webhook_e_a_copia_fica_guardada_cifrada(self, clicksign, guardados):
        """Mutante: guardar o PDF assinado sem cifrar."""
        cenario = _cenario_do_cadastro()
        cenario.incluir()

        resposta = _retorno_da_clicksign(cenario.cliente(), "doc-env-1", "auto_close")

        assert resposta.status_code == 200, resposta.text
        assert cenario.participacao("N1").get("termo_assinado_em")
        [termo] = cenario.assinaturas()
        assert termo["situacao"] == "assinado"
        assert termo["assinado_em"]
        [(bucket, caminho)] = guardados
        assert (bucket, caminho) == ("conduta-arquivos", termo["arquivo_assinado_path"])
        assert PDF_ASSINADO not in guardados[(bucket, caminho)]
        assert cifra.decifrar_arquivo(guardados[(bucket, caminho)]) == PDF_ASSINADO

    def test_assinatura_de_um_so_signatario_nao_fecha_antes_do_envelope(self, clicksign):
        """`sign` chega a cada assinatura; só o fechamento do envelope conta."""
        cenario = _cenario_do_cadastro()
        cenario.incluir()

        _retorno_da_clicksign(cenario.cliente(), "doc-env-1", "sign")

        assert cenario.participacao("N1").get("termo_assinado_em") is None
        assert cenario.assinaturas()[0]["situacao"] == "enviado"

    def test_pdf_ainda_indisponivel_e_guardado_no_document_closed(self, clicksign, guardados):
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        clicksign.falhar_em = "get_signed_document"
        cliente = cenario.cliente()

        _retorno_da_clicksign(cliente, "doc-env-1", "auto_close")
        assert cenario.participacao("N1").get("termo_assinado_em")
        assert guardados == {}

        clicksign.falhar_em = None
        _retorno_da_clicksign(cliente, "doc-env-1", "document_closed")

        assert len(guardados) == 1
        assert cenario.assinaturas()[0]["arquivo_assinado_path"]

    def test_evento_repetido_nao_guarda_de_novo_nem_troca_a_data(self, clicksign, guardados):
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        cliente = cenario.cliente()
        _retorno_da_clicksign(cliente, "doc-env-1", "auto_close")
        carimbo = cenario.participacao("N1").get("termo_assinado_em")

        _retorno_da_clicksign(cliente, "doc-env-1", "auto_close")
        _retorno_da_clicksign(cliente, "doc-env-1", "document_closed")

        assert cenario.participacao("N1").get("termo_assinado_em") == carimbo
        assert clicksign.nomes().count("get_signed_document") == 1
        assert len(guardados) == 1

    def test_envelope_cancelado_pelo_reenvio_nao_muda_nada(self, clicksign):
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        cliente = cenario.cliente()
        cliente.post(f"{ROTA}/{cenario.participacao('N1')['id']}/termo/reenviar")

        _retorno_da_clicksign(cliente, "doc-env-1", "auto_close")

        assert cenario.participacao("N1").get("termo_assinado_em") is None


# ═══════════════════════════════════════════════════════════════════════════
# 3. Sem o Termo assinado: a tela inicial abre, o caso não
# ═══════════════════════════════════════════════════════════════════════════


class TestSemTermoAssinado:
    def _cenario(self, termo: bool) -> tuple[_Cenario, dict]:
        cenario = _Cenario(_pessoa("M1"), [], [_participacao("M1", termo=termo)])
        caso = casos.registrar_caso(cenario.banco, relato="Relato de teste.", categoria="assedio_moral", rota="comum")
        return cenario, caso

    def test_membro_sem_termo_ve_a_tela_inicial_e_recebe_403_ao_abrir_caso(self):
        """Mutante: a tela inicial recusar o membro sem Termo, como antes."""
        cenario, caso = self._cenario(termo=False)
        cliente = cenario.cliente()

        inicial = cliente.get("/api/comite-de-conduta/minha-vez")
        aberto = cliente.get(f"/api/comite-de-conduta/casos/{caso['id']}")

        assert inicial.status_code == 200, inicial.text
        assert inicial.json() == {"itens": [], "termo_pendente": True}
        assert aberto.status_code == 403 and aberto.json() == RECUSA
        assert [t["acao"] for t in cenario.tabela("conduta_trilha")] == ["recebimento"]

    def test_membro_com_termo_assinado_abre_o_caso(self):
        cenario, caso = self._cenario(termo=True)
        cliente = cenario.cliente()

        inicial = cliente.get("/api/comite-de-conduta/minha-vez")
        aberto = cliente.get(f"/api/comite-de-conduta/casos/{caso['id']}")

        assert inicial.status_code == 200 and inicial.json()["termo_pendente"] is False
        assert aberto.status_code == 200, aberto.text

    def test_quem_nao_esta_no_comite_segue_recusado_na_tela_inicial(self):
        cenario = _Cenario(_pessoa("X1"), [], [])
        resposta = cenario.cliente().get("/api/comite-de-conduta/minha-vez")
        assert resposta.status_code == 403 and resposta.json() == RECUSA

    def test_assinado_pelo_webhook_o_membro_passa_a_abrir_caso(self, clicksign):
        cenario, caso = self._cenario(termo=False)
        cenario.banco.tabelas["conduta_assinaturas"] = [
            {
                "id": "ass-1",
                "tipo": "termo_de_posse",
                "participacao_id": "part-M1",
                "signatarios": ["M1"],
                "situacao": "enviado",
                "envelope_id": "env-9",
                "documento_key": "doc-env-9",
                "created_at": "2026-11-20T12:00:00+00:00",
            }
        ]
        cliente = cenario.cliente()

        _retorno_da_clicksign(cliente, "doc-env-9", "auto_close")

        assert cliente.get(f"/api/comite-de-conduta/casos/{caso['id']}").status_code == 200


# ═══════════════════════════════════════════════════════════════════════════
# 4. "Reconsultar status" atualiza sem depender do webhook
# ═══════════════════════════════════════════════════════════════════════════


class TestReconsultar:
    def test_reconsultar_status_atualiza_a_situacao_sem_o_webhook(self, clicksign, guardados):
        """Mutante: a reconsulta não aplicar o envelope fechado."""
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        clicksign.status = "closed"
        participacao_id = cenario.participacao("N1")["id"]

        resposta = cenario.cliente().post(f"{ROTA}/{participacao_id}/termo/reconsultar")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["termo"] == "assinado"
        assert ("get_envelope_status", "env-1") in clicksign.chamadas
        assert cenario.assinaturas()[0]["situacao"] == "assinado"
        assert len(guardados) == 1

    def test_envelope_ainda_aberto_nao_muda_nada(self, clicksign):
        cenario = _cenario_do_cadastro()
        cenario.incluir()

        resposta = cenario.cliente().post(f"{ROTA}/{cenario.participacao('N1')['id']}/termo/reconsultar")

        assert resposta.status_code == 200
        assert resposta.json()["termo"] == "aguardando_assinatura"

    def test_clicksign_sem_resposta_da_503(self, clicksign):
        cenario = _cenario_do_cadastro()
        cenario.incluir()
        clicksign.status = None

        resposta = cenario.cliente().post(f"{ROTA}/{cenario.participacao('N1')['id']}/termo/reconsultar")

        assert resposta.status_code == 503

    def test_sem_termo_enviado_a_reconsulta_pede_o_reenvio(self, clicksign):
        cenario = _Cenario(_pessoa("C1", **CADASTRO), [_pessoa("N1")], [_participacao("N1", termo=False)])
        resposta = cenario.cliente().post(f"{ROTA}/part-N1/termo/reconsultar")
        assert resposta.status_code == 409
        assert "Reenviar o Termo" in resposta.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Os envelopes de Reuniões, POPs e do Núcleo continuam achados
# ═══════════════════════════════════════════════════════════════════════════


class TestRoteamentoDoWebhook:
    @pytest.fixture
    def destinos(self, monkeypatch) -> list[tuple[str, str]]:
        """Cada destino do webhook anota quem recebeu o evento."""
        from app.services.seguranca_do_paciente import assinatura_dos_documentos, termo

        chegou: list[tuple[str, str]] = []
        monkeypatch.setattr(
            webhooks, "_processar_reuniao", lambda _s, r, *_a: chegou.append(("reuniao", r["id_reuniao"]))
        )
        monkeypatch.setattr(webhooks, "_processar_versao_pop", lambda _s, v, *_a: chegou.append(("pop", v["id"])))
        monkeypatch.setattr(termo, "processar_evento", lambda _s, e, *_a, **_kw: chegou.append(("termo_nsp", e["id"])))
        monkeypatch.setattr(
            assinatura_dos_documentos,
            "tratar_retorno_da_versao",
            lambda _s, v, *_a, **_kw: chegou.append(("documento_nsp", v["id"])),
        )
        monkeypatch.setattr(
            assinaturas, "processar_evento", lambda _s, a, *_a: chegou.append(("canal_de_conduta", a["id"]))
        )
        return chegou

    def test_cada_envelope_chega_ao_seu_destino(self, destinos):
        """Cada chave no seu destino, e o Canal sem tomar a chave dos outros."""
        cenario = _Cenario(
            _pessoa("C1"),
            reunioes=[{"id_reuniao": "R1", "envelope_key_clicksign": "k-reuniao"}],
            pops_versoes=[{"id": "V1", "envelope_key_clicksign": "k-pop"}],
            nsp_termos_envios=[{"id": "T1", "documento_key": "k-termo-nsp"}],
            nsp_documentos_envios=[{"id": "D1", "documento_key": "k-documento-nsp"}],
            conduta_assinaturas=[{"id": "A1", "documento_key": "k-canal", "situacao": "enviado"}],
        )
        cliente = cenario.cliente()

        for chave in ("k-reuniao", "k-pop", "k-termo-nsp", "k-documento-nsp", "k-canal"):
            assert _retorno_da_clicksign(cliente, chave).status_code == 200

        assert destinos == [
            ("reuniao", "R1"),
            ("pop", "V1"),
            ("termo_nsp", "T1"),
            ("documento_nsp", "D1"),
            ("canal_de_conduta", "A1"),
        ]

    def test_chave_desconhecida_nao_chega_a_destino_nenhum(self, destinos):
        """Mutante: o Canal achar a assinatura sem filtrar pela chave."""
        cenario = _Cenario(_pessoa("C1"), conduta_assinaturas=[{"id": "A1", "documento_key": "k-canal"}])
        resposta = _retorno_da_clicksign(cenario.cliente(), "k-ninguem")
        assert resposta.json() == {"message": "Documento não encontrado."}
        assert destinos == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. Nenhum teste chama a ClickSign de verdade
# ═══════════════════════════════════════════════════════════════════════════


def test_toda_funcao_da_clicksign_que_o_canal_usa_e_dubla_aqui():
    """O dublê cobre o que o serviço do Canal chama da ClickSign: função nova
    no serviço sem dublê fica vermelha aqui, antes de algum teste sair para a
    rede com a credencial de produção do `.env` local."""
    import inspect

    fonte = inspect.getsource(assinaturas)
    usadas = set(re.findall(r"clicksign_service\.(\w+)\(", fonte))
    assert usadas
    assert usadas <= set(FUNCOES_DA_CLICKSIGN), usadas - set(FUNCOES_DA_CLICKSIGN)


def test_a_rede_esta_fechada_para_a_clicksign_nos_testes():
    with pytest.raises(AssertionError, match="rede"):
        clicksign_service.httpx.Client()


# ═══════════════════════════════════════════════════════════════════════════
# 7. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


def test_o_kit_do_canal_diz_como_o_termo_e_assinado():
    from pathlib import Path

    kit = (Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "canal-de-conduta.md").read_text(
        encoding="utf-8"
    )
    assert "## O Termo de Confidencialidade e Posse" in kit
    assert "chega à ClickSign no e-mail profissional do membro" in kit
    assert "Reconsultar status" in kit
    assert "cifrada" in kit
    assert "vê a tela inicial, mas não abre caso" in kit
    assert "o Termo de Confidencialidade e Posse do membro chegam nas próximas entregas" not in kit


# ═══════════════════════════════════════════════════════════════════════════
# O PDF assinado vem em `links.files.signed` (pesquisa na #1786)
# ═══════════════════════════════════════════════════════════════════════════


def test_o_pdf_assinado_e_baixado_do_link_signed_da_v3(monkeypatch):
    """Mutante: ler só o `attributes.download_url`. A ClickSign aqui é um
    transporte de mentira, sem rede."""
    pedidos: list[str] = []

    def _responder(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(str(pedido.url))
        if pedido.url.path.endswith("/envelopes/env-1/documents"):
            return httpx.Response(
                200,
                json={"data": [{"attributes": {}, "links": {"files": {"signed": "https://arquivos.test/assinado"}}}]},
            )
        if str(pedido.url) == "https://arquivos.test/assinado":
            return httpx.Response(200, content=PDF_ASSINADO)
        return httpx.Response(404)

    def _cliente(*_a, **kw):
        return _CLIENTE_HTTP(transport=httpx.MockTransport(_responder), timeout=kw.get("timeout"))

    monkeypatch.setattr(clicksign_service.httpx, "Client", _cliente)

    assert _BAIXAR_ASSINADO("env-1") == PDF_ASSINADO
    assert pedidos[-1] == "https://arquivos.test/assinado"
