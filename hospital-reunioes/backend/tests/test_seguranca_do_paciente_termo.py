"""O Termo de Adesão do Núcleo (issue #1768, PRD #1764, ADR 0095).

Cadastrar o membro gera um documento só (o Termo preenchido e o Regimento
vigente na íntegra) e o manda para a assinatura eletrônica com um signatário.
O retorno da assinatura deixa o membro Ativo sozinho; a Presidência reconsulta,
reenvia ou libera à mão, com justificativa.

A assinatura eletrônica é sempre um dublê (a `_Assinatura` abaixo): nenhum
teste daqui fala com ela de verdade. O banco e o Storage são dublês em memória.
Nenhum nome, registro ou e-mail de pessoa real: as pessoas daqui são de teste.
O PDF é gerado de verdade (WeasyPrint) e lido de volta com o pdfplumber.
"""

from __future__ import annotations

import hashlib
import hmac as hmac_lib
import io
import json
import os
import re
import sys
import uuid
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pdfplumber
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import seguranca_do_paciente_documentos as documentos_router  # noqa: E402
from app.routers import seguranca_do_paciente_membros as membros_router  # noqa: E402
from app.routers import seguranca_do_paciente_termo as termo_router  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import clicksign_service  # noqa: E402
from app.services.seguranca_do_paciente import permissao  # noqa: E402

ROTA = "/api/nsp/membros"
RECUSA_DO_CONTEUDO = {"detail": "Conteúdo restrito ao Núcleo de Segurança do Paciente"}
SEGREDO_DO_WEBHOOK = "segredo-de-teste"

HOJE = permissao.hoje_em_sao_paulo()
NUCLEO = {"id": "col-nsp", "slug": "nsp", "nome": "Núcleo de Segurança do Paciente", "setor_id": None}
ASSINADO = "2026-01-10T12:00:00+00:00"

TRAVESSAO, MEIA_RISCA = chr(0x2014), chr(0x2013)

# O Regimento de teste traz travessão e meia-risca de propósito: o PDF não pode
# sair com nenhum dos dois.
TEXTO_DO_REGIMENTO = (
    f"Art. 1º O Núcleo de Segurança do Paciente {TRAVESSAO} instância consultiva {TRAVESSAO} reúne-se mensalmente.\n"
    f"Art. 2º O prazo de análise é de 10{MEIA_RISCA}15 dias corridos."
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _dia_fixo(monkeypatch):
    monkeypatch.setattr(membros_router, "hoje_em_sao_paulo", lambda: HOJE)
    monkeypatch.setattr(termo_router, "hoje_em_sao_paulo", lambda: HOJE)
    monkeypatch.setattr(permissao, "hoje_em_sao_paulo", lambda: HOJE)


@pytest.fixture(autouse=True)
def _segredo_do_webhook(monkeypatch):
    monkeypatch.setattr(settings, "clicksign_webhook_secret", SEGREDO_DO_WEBHOOK)


def _iso(delta: int) -> str:
    return (HOJE + timedelta(days=delta)).isoformat()


# ═══════════════════════════════════════════════════════════════════════════
# Dublês
# ═══════════════════════════════════════════════════════════════════════════


class _Assinatura:
    """A assinatura eletrônica de mentira: anota cada chamada e responde
    como a de verdade responderia. `falhar_em` derruba um passo."""

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
        return f"sig-{envelope_id}" if self._passo("add_signer", envelope_id, nome, email) else None

    def create_qualification_requirement(self, envelope_id, documento_id, signatario_id):
        return "req-q" if self._passo("create_qualification_requirement", envelope_id) else None

    def create_auth_requirement(self, envelope_id, documento_id, signatario_id):
        return "req-a" if self._passo("create_auth_requirement", envelope_id) else None

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
        self._passo("get_signed_document", envelope_id)
        return b"%PDF-1.4 assinado"

    def nomes(self) -> list[str]:
        return [c[0] for c in self.chamadas]


@pytest.fixture(autouse=True)
def assinatura(monkeypatch) -> _Assinatura:
    """Toda função da assinatura eletrônica que o módulo usa vira dublê. A que
    não estiver aqui explode: nenhum teste chega à assinatura de verdade."""
    dubla = _Assinatura()
    for nome in (
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
    ):
        monkeypatch.setattr(clicksign_service, nome, getattr(dubla, nome))
    return dubla


class _Consulta:
    def __init__(self, banco: _Banco, nome: str):
        self._banco = banco
        self._nome = nome
        self._filtros: list = []
        self._teto: int | None = None
        self._ordem: tuple | None = None
        self._operacao = ("select", None)
        self._recorte: tuple[int, int] | None = None

    @property
    def _linhas(self) -> list[dict]:
        return self._banco.tabelas.setdefault(self._nome, [])

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def in_(self, coluna, valores):
        valores = list(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def lte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) <= str(valor))
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) >= str(valor))
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, n):
        self._teto = n
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim)
        return self

    def insert(self, linha):
        self._operacao = ("insert", linha)
        return self

    def update(self, campos: dict):
        self._operacao = ("update", campos)
        return self

    def delete(self):
        raise AssertionError("Nada se apaga no módulo do Núcleo")

    def execute(self):
        operacao, carga = self._operacao
        if operacao == "insert":
            gravadas = []
            for linha in carga if isinstance(carga, list) else [carga]:
                nova = {"id": str(uuid.uuid4()), "created_at": f"{HOJE.isoformat()}T12:00:00+00:00", **linha}
                self._linhas.append(nova)
                gravadas.append(dict(nova))
            return SimpleNamespace(data=gravadas)
        casam = [linha for linha in self._linhas if all(f(linha) for f in self._filtros)]
        if operacao == "update":
            for linha in casam:
                linha.update(carga)
            return SimpleNamespace(data=[dict(linha) for linha in casam])
        casam = [dict(linha) for linha in casam]
        if self._ordem:
            coluna, desc = self._ordem
            casam.sort(key=lambda linha: str(linha.get(coluna) or ""), reverse=desc)
        if self._recorte:
            inicio, fim = self._recorte
            casam = casam[inicio : fim + 1]
        return SimpleNamespace(data=casam[: self._teto] if self._teto is not None else casam)


class _Balde:
    def __init__(self, arquivos: dict, nome: str):
        self._arquivos = arquivos
        self._nome = nome

    def upload(self, caminho, conteudo, _opcoes=None):
        self._arquivos[(self._nome, caminho)] = conteudo

    def create_signed_url(self, caminho, _segundos):
        assert (self._nome, caminho) in self._arquivos
        return {"signedURL": f"https://storage.test/{self._nome}/{caminho}?token=t"}


class _Storage:
    def __init__(self):
        self.arquivos: dict[tuple[str, str], bytes] = {}

    def from_(self, nome):
        return _Balde(self.arquivos, nome)


class _Banco:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas
        self.storage = _Storage()

    def table(self, nome: str):
        return _Consulta(self, nome)

    def rpc(self, nome: str, params: dict):
        """O que a `nsp_publicar_documento` faz: a versão seguinte do tipo
        nasce vigente e a vigente anterior do mesmo tipo deixa de ser."""
        assert nome == "nsp_publicar_documento", nome
        documentos = self.tabelas.setdefault("nsp_documentos", [])
        do_tipo = [d for d in documentos if d["tipo"] == params["p_tipo"]]
        for anterior in do_tipo:
            anterior["vigente"] = False
        novo = {
            "id": f"doc-{params['p_tipo']}-{len(do_tipo) + 2}",
            "tipo": params["p_tipo"],
            "versao": max((d["versao"] for d in do_tipo), default=0) + 1,
            "titulo": params["p_titulo"],
            "texto": params["p_texto"],
            "natureza_revisao": params["p_natureza_revisao"],
            "vigente": True,
            "arquivo_assinado_path": None,
            "publicado_por": params["p_publicado_por"],
            "publicado_em": f"{HOJE.isoformat()}T12:00:00+00:00",
        }
        documentos.append(novo)
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=dict(novo)))


# ═══════════════════════════════════════════════════════════════════════════
# Cenário
# ═══════════════════════════════════════════════════════════════════════════


def _pessoa(pid: str, **campos) -> dict[str, Any]:
    base = {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": f"Pessoa de Teste {pid}",
        "email": f"{pid.lower()}@hsm.test",
        "cargo": "Enfermeira de teste",
        "area": None,
        "setor": "Setor de teste",
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "perfil_contas_medicas": None,
        "perfil_nsp": None,
        "github_login": None,
        "conselho_profissional": None,
        "registro_profissional": None,
        "registro_uf": None,
        "data_cadastro": "2026-01-01",
    }
    return {**base, **campos}


def _participacao(pid: str, *, papel="membro", termo=True, **campos) -> dict[str, Any]:
    return {
        "id": f"part-{pid}",
        "colegiado_id": NUCLEO["id"],
        "participante_id": pid,
        "papel": papel,
        "area": "UTI adulto",
        "vigencia_inicio": _iso(-30),
        "vigencia_fim": _iso(300),
        "encerrada_em": None,
        "termo_assinado_em": ASSINADO if termo else None,
        **campos,
    }


# P1 é o Acesso pleno; P2, a Presidência; P3, um membro com Termo; P4, a pessoa
# cadastrada nos testes; P5, o super admin; P6, a Diretoria.
ACESSO_PLENO = _pessoa("P1", perfil_nsp="acesso_pleno")
PRESIDENCIA = _pessoa("P2")
MEMBRO = _pessoa("P3")
NOVA = _pessoa("P4")
SUPER_ADMIN = _pessoa("P5", access_profile="super_admin", is_super_admin=True)
DIRETORIA = _pessoa("P6", role="diretor")

REGIMENTO = {
    "id": "doc-regimento-2",
    "tipo": "regimento",
    "versao": 2,
    "titulo": "Regimento Interno do Núcleo",
    "texto": TEXTO_DO_REGIMENTO,
    "natureza_revisao": "material",
    "vigente": True,
    "publicado_por": "P2",
    # Antes da assinatura de teste: quem assinou levou este Regimento no Termo.
    "publicado_em": "2025-12-01T12:00:00+00:00",
}

NOVO = {
    "participante_id": "P4",
    "papel": "membro",
    "area": "Farmácia",
    "vigencia_inicio": _iso(0),
    "vigencia_fim": _iso(365),
    "conselho_profissional": "CRF",
    "registro_profissional": "000444",
    "registro_uf": "rj",
}


class _Cenario:
    def __init__(self, quem: dict, participacoes: list[dict] | None = None, *, regimento: bool = True):
        if participacoes is None:
            participacoes = [_participacao("P2", papel="presidencia"), _participacao("P3")]
        self.banco = _Banco(
            {
                "participantes": [dict(p) for p in (ACESSO_PLENO, PRESIDENCIA, MEMBRO, NOVA, SUPER_ADMIN, DIRETORIA)],
                "colegiados": [dict(NUCLEO)],
                "participacoes": [dict(p) for p in participacoes],
                "participacoes_trilha": [],
                "nsp_documentos": [dict(REGIMENTO)] if regimento else [],
                "nsp_termos_envios": [],
                "nsp_documentos_envios": [],
                "reunioes": [],
                "pops_versoes": [],
                # O quinto destino do webhook (issue #1823): o Canal de Conduta.
                "conduta_assinaturas": [],
            }
        )
        app = FastAPI()
        app.state.limiter = limiter
        app.include_router(membros_router.router, prefix="/api")
        app.include_router(termo_router.router, prefix="/api")
        app.include_router(webhooks_router.router, prefix="/api")
        app.include_router(documentos_router.router, prefix="/api")

        async def _usuario() -> dict[str, Any]:
            return {"id": quem["auth_user_id"], "email": quem["email"], "metadata": {}}

        app.dependency_overrides[get_current_user] = _usuario
        app.dependency_overrides[get_supabase_client] = lambda: self.banco
        self.api = TestClient(app)

    def tabela(self, nome: str) -> list[dict]:
        return self.banco.tabelas.setdefault(nome, [])

    def participacao(self, pid: str) -> dict:
        return next(p for p in self.tabela("participacoes") if p["participante_id"] == pid)

    def envios(self, pid: str) -> list[dict]:
        part = self.participacao(pid)["id"]
        return [e for e in self.tabela("nsp_termos_envios") if e["participacao_id"] == part]

    def trilha(self, acao: str) -> list[dict]:
        return [t for t in self.tabela("participacoes_trilha") if t["acao"] == acao]

    def estado(self, pid: str) -> str:
        part = self.participacao(pid)["id"]
        return next(m for m in self.api.get(ROTA).json()["membros"] if m["id"] == part)["estado"]

    def retorno_da_assinatura(self, documento_key: str, evento: str = "sign"):
        corpo = json.dumps({"event": {"name": evento}, "document": {"key": documento_key}}).encode()
        assinatura = hmac_lib.new(SEGREDO_DO_WEBHOOK.encode(), corpo, hashlib.sha256).hexdigest()
        return self.api.post(
            "/api/webhooks/clicksign",
            content=corpo,
            headers={"content-hmac": f"sha256={assinatura}", "content-type": "application/json"},
        )

    def cadastrar(self) -> dict:
        resposta = self.api.post(ROTA, json=NOVO)
        assert resposta.status_code == 201, resposta.text
        return resposta.json()


def _assert_recusado(resposta) -> None:
    assert resposta.status_code == 403, resposta.text
    assert resposta.json() == RECUSA_DO_CONTEUDO


def _texto_do_pdf(pdf: bytes) -> str:
    with pdfplumber.open(io.BytesIO(pdf)) as documento:
        texto = "\n".join(pagina.extract_text() or "" for pagina in documento.pages)
    return re.sub(r"\s+", " ", texto)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Cadastrar gera um documento só e o envia com um signatário
# ═══════════════════════════════════════════════════════════════════════════


class TestCadastroGeraEEnvia:
    def test_cadastro_gera_um_documento_com_termo_e_regimento_e_envia_com_um_signatario(self, assinatura):
        """Mutante: não chamar o envio do Termo no cadastro."""
        cenario = _Cenario(PRESIDENCIA)

        corpo = cenario.cadastrar()

        assert corpo["estado"] == "aguardando_assinatura"
        assert assinatura.nomes().count("create_envelope") == 1
        assert assinatura.nomes().count("add_document") == 1
        signatarios = [c for c in assinatura.chamadas if c[0] == "add_signer"]
        assert signatarios == [("add_signer", "env-1", "Pessoa de Teste P4", "p4@hsm.test")]
        assert "activate_envelope" in assinatura.nomes()
        texto = _texto_do_pdf(assinatura.documentos[0])
        assert "TERMO DE ADESÃO" in texto.upper()
        assert "Pessoa de Teste P4" in texto
        assert "reúne-se mensalmente" in texto
        assert "O prazo de análise é de 10-15 dias corridos" in texto
        [envio] = cenario.envios("P4")
        assert envio["situacao"] == "enviado"
        assert envio["documento_key"] == "doc-env-1"
        assert envio["regimento_id"] == REGIMENTO["id"]

    def test_sem_regimento_vigente_o_cadastro_fica_de_pe_e_avisa(self, assinatura):
        cenario = _Cenario(PRESIDENCIA, regimento=False)

        corpo = cenario.cadastrar()

        assert corpo["estado"] == "cadastrado"
        assert "Publique o Regimento" in corpo["aviso_termo"]
        assert assinatura.chamadas == []
        assert cenario.envios("P4") == []

    def test_assinatura_fora_do_ar_deixa_o_documento_gerado_e_avisa(self, assinatura):
        assinatura.falhar_em = "activate_envelope"
        cenario = _Cenario(PRESIDENCIA)

        corpo = cenario.cadastrar()

        assert corpo["estado"] == "documento_gerado"
        assert "Reenviar" in corpo["aviso_termo"]
        [envio] = cenario.envios("P4")
        assert envio["situacao"] == "gerado"


# ═══════════════════════════════════════════════════════════════════════════
# 2. O retorno da assinatura deixa o membro Ativo, sem repetir nada
# ═══════════════════════════════════════════════════════════════════════════


class TestRetornoDaAssinatura:
    def test_assinatura_deixa_o_membro_ativo_e_guarda_o_termo_nos_documentos(self):
        """Mutante: o tratamento do envelope do Núcleo não carimbar a Participação."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()

        resposta = cenario.retorno_da_assinatura("doc-env-1", "sign")

        assert resposta.status_code == 200, resposta.text
        assert cenario.estado("P4") == "ativo"
        assert cenario.participacao("P4")["termo_assinado_em"]
        [assinado] = cenario.trilha("termo_assinado")
        assert assinado["autor_id"] == "P4"
        [documento] = [d for d in cenario.tabela("nsp_documentos") if d["tipo"] == "termo"]
        assert documento["termo_envio_id"] == cenario.envios("P4")[0]["id"]
        assert documento["vigente"] is False
        assert "Pessoa de Teste P4" in documento["titulo"]
        guardado = (settings.supabase_storage_bucket_nsp_documentos, documento["arquivo_assinado_path"])
        assert cenario.banco.storage.arquivos[guardado] == b"%PDF-1.4 assinado"

    def test_evento_repetido_nao_duplica_nada(self):
        """Mutante: tirar a troca condicional (só o envio "enviado" vira assinado)."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()

        for evento in ("sign", "sign", "auto_close", "document_closed"):
            assert cenario.retorno_da_assinatura("doc-env-1", evento).status_code == 200

        assert len(cenario.trilha("termo_assinado")) == 1
        assert len([d for d in cenario.tabela("nsp_documentos") if d["tipo"] == "termo"]) == 1

    def test_dois_retornos_simultaneos_carimbam_uma_vez(self):
        """Os dois leram o envio ainda "enviado". Mutante: tirar a troca
        condicional (só o envio "enviado" vira assinado)."""
        from app.services.seguranca_do_paciente import termo

        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        [lido_pelos_dois] = cenario.envios("P4")
        lido_pelos_dois = dict(lido_pelos_dois)

        termo.processar_evento(cenario.banco, lido_pelos_dois, "sign")
        termo.processar_evento(cenario.banco, lido_pelos_dois, "auto_close")

        assert len(cenario.trilha("termo_assinado")) == 1

    @pytest.mark.parametrize("conserto", ["reenvio_do_evento", "reconsulta"])
    def test_carimbo_que_falhou_depois_da_troca_se_conserta_no_reenvio_e_na_reconsulta(self, conserto, assinatura):
        """O envio já virou assinado, mas o carimbo da Participação estourou o
        tempo. Mutante: o ramo `assinado` só guardar o PDF, sem carimbar."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        tabela_de_verdade = cenario.banco.table
        falhas = {"restantes": 1}

        class _CarimboQueEstoura(_Consulta):
            def execute(self):
                operacao, carga = self._operacao
                if operacao == "update" and "termo_assinado_em" in carga and falhas["restantes"]:
                    falhas["restantes"] -= 1
                    raise httpx.ReadTimeout("o banco não respondeu")
                return super().execute()

        cenario.banco.table = lambda nome: (
            _CarimboQueEstoura(cenario.banco, nome) if nome == "participacoes" else tabela_de_verdade(nome)
        )

        assert cenario.retorno_da_assinatura("doc-env-1", "sign").status_code == 500
        [envio] = cenario.envios("P4")
        assert envio["situacao"] == "assinado"
        assert cenario.participacao("P4").get("termo_assinado_em") is None

        if conserto == "reenvio_do_evento":
            assert cenario.retorno_da_assinatura("doc-env-1", "sign").status_code == 200
            assert cenario.retorno_da_assinatura("doc-env-1", "auto_close").status_code == 200
        else:
            assinatura.status = "closed"
            part = cenario.participacao("P4")["id"]
            assert cenario.api.post(f"{ROTA}/{part}/termo/reconsultar").status_code == 200
            assert cenario.api.post(f"{ROTA}/{part}/termo/reconsultar").status_code == 200

        assert cenario.estado("P4") == "ativo"
        assert cenario.participacao("P4")["termo_assinado_em"] == envio["assinado_em"]
        [assinado] = cenario.trilha("termo_assinado")
        assert assinado["autor_id"] == "P4"
        assert cenario.trilha("liberacao_manual") == []

    def test_envelope_desconhecido_nao_muda_nada(self):
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        antes = json.dumps(cenario.banco.tabelas, sort_keys=True, default=str)

        resposta = cenario.retorno_da_assinatura("doc-fantasma", "sign")

        assert resposta.status_code == 200
        assert json.dumps(cenario.banco.tabelas, sort_keys=True, default=str) == antes
        assert cenario.estado("P4") == "aguardando_assinatura"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Reconsultar aplica o mesmo tratamento
# ═══════════════════════════════════════════════════════════════════════════


class TestReconsultar:
    def test_reconsultar_com_o_envelope_fechado_ativa_como_o_retorno_automatico(self, assinatura):
        """Mutante: a reconsulta só ler o status e não aplicar o tratamento."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        assinatura.status = "closed"
        part = cenario.participacao("P4")["id"]

        resposta = cenario.api.post(f"{ROTA}/{part}/termo/reconsultar")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "ativo"
        assert len(cenario.trilha("termo_assinado")) == 1
        assert len([d for d in cenario.tabela("nsp_documentos") if d["tipo"] == "termo"]) == 1

    def test_reconsultar_ainda_sem_assinatura_nao_muda_nada(self, assinatura):
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        assinatura.status = "running"
        part = cenario.participacao("P4")["id"]

        resposta = cenario.api.post(f"{ROTA}/{part}/termo/reconsultar")

        assert resposta.status_code == 200
        assert resposta.json()["estado"] == "aguardando_assinatura"
        assert cenario.trilha("termo_assinado") == []

    def test_assinatura_fora_do_ar_na_reconsulta_responde_503(self, assinatura):
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        assinatura.status = None
        part = cenario.participacao("P4")["id"]

        resposta = cenario.api.post(f"{ROTA}/{part}/termo/reconsultar")

        assert resposta.status_code == 503
        assert "não respondeu" in resposta.json()["detail"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. O reenvio cancela o envelope anterior e gera outro identificador
# ═══════════════════════════════════════════════════════════════════════════


class TestReenvio:
    def test_reenvio_cancela_o_anterior_e_gera_outro_identificador(self, assinatura):
        """Mutante: o reenvio não cancelar o envio aberto."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        [antigo] = cenario.envios("P4")
        part = cenario.participacao("P4")["id"]

        resposta = cenario.api.post(f"{ROTA}/{part}/termo/reenviar")

        assert resposta.status_code == 200, resposta.text
        assert ("cancel_envelope", antigo["envelope_id"]) in assinatura.chamadas
        antigo, novo = sorted(cenario.envios("P4"), key=lambda e: e["situacao"])
        assert (antigo["situacao"], novo["situacao"]) == ("cancelado", "enviado")
        assert novo["id"] != antigo["id"]
        assert novo["envelope_id"] != antigo["envelope_id"]
        assert novo["documento_key"] != antigo["documento_key"]
        assert novo["id"] in _texto_do_pdf(assinatura.documentos[-1])
        assert len(cenario.trilha("termo_reenviado")) == 1

    def test_retorno_do_envelope_cancelado_nao_ativa(self):
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        part = cenario.participacao("P4")["id"]
        cenario.api.post(f"{ROTA}/{part}/termo/reenviar")

        assert cenario.retorno_da_assinatura("doc-env-1", "sign").status_code == 200

        assert cenario.estado("P4") == "aguardando_assinatura"
        assert cenario.trilha("termo_assinado") == []

    def test_termo_ja_assinado_nao_se_reenvia(self):
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")

        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "O Termo deste membro já está assinado."}


# ═══════════════════════════════════════════════════════════════════════════
# 5. A liberação manual: justificativa, trilha, e só Presidência e Acesso pleno
# ═══════════════════════════════════════════════════════════════════════════


def _com_pendente() -> list[dict]:
    return [_participacao("P2", papel="presidencia"), _participacao("P3"), _participacao("P4", termo=False)]


class TestLiberacaoManual:
    @pytest.mark.parametrize("quem", [ACESSO_PLENO, PRESIDENCIA], ids=["acesso_pleno", "presidencia"])
    def test_liberacao_grava_autor_data_e_motivo_e_ativa(self, quem):
        cenario = _Cenario(quem, _com_pendente())

        resposta = cenario.api.post(
            f"{ROTA}/part-P4/termo/liberar", json={"justificativa": "  Assinatura eletrônica fora do ar no dia  "}
        )

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["estado"] == "ativo"
        [linha] = cenario.trilha("liberacao_manual")
        assert linha["autor_id"] == quem["id"]
        assert linha["created_at"]
        assert linha["motivo"] == "Assinatura eletrônica fora do ar no dia"

    @pytest.mark.parametrize("justificativa", ["", "   "], ids=["vazia", "so_espacos"])
    def test_liberacao_sem_justificativa_e_recusada(self, justificativa):
        """Mutante: aceitar justificativa em branco."""
        cenario = _Cenario(PRESIDENCIA, _com_pendente())

        resposta = cenario.api.post(f"{ROTA}/part-P4/termo/liberar", json={"justificativa": justificativa})

        assert resposta.status_code == 422
        assert cenario.participacao("P4").get("termo_assinado_em") is None
        assert cenario.trilha("liberacao_manual") == []

    @pytest.mark.parametrize(
        "quem", [DIRETORIA, SUPER_ADMIN, MEMBRO], ids=["diretoria", "super_admin_sem_acesso_pleno", "membro"]
    )
    def test_so_presidencia_e_acesso_pleno_liberam(self, quem):
        """ADR 0095, decisão 4. Mutante: trocar o recurso da liberação de `gerir_nucleo` para `membros`."""
        cenario = _Cenario(quem, _com_pendente())

        resposta = cenario.api.post(f"{ROTA}/part-P4/termo/liberar", json={"justificativa": "Motivo qualquer"})

        _assert_recusado(resposta)
        assert cenario.participacao("P4").get("termo_assinado_em") is None
        assert cenario.trilha("liberacao_manual") == []

    @pytest.mark.parametrize("acao", ["reconsultar", "reenviar"])
    @pytest.mark.parametrize("quem", [DIRETORIA, SUPER_ADMIN], ids=["diretoria", "super_admin_sem_acesso_pleno"])
    def test_diretoria_e_super_admin_nao_reconsultam_nem_reenviam(self, quem, acao, assinatura):
        _assert_recusado(_Cenario(quem, _com_pendente()).api.post(f"{ROTA}/part-P4/termo/{acao}"))
        assert assinatura.chamadas == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. A faixa: o membro sem Termo acha o documento pendente
# ═══════════════════════════════════════════════════════════════════════════


class TestMeuTermo:
    def test_membro_sem_termo_recebe_o_link_do_documento_pendente(self):
        """Mutante: a rota responder `pendente` sem o link do documento."""
        presidencia = _Cenario(PRESIDENCIA)
        presidencia.cadastrar()
        membro = _Cenario(NOVA, presidencia.tabela("participacoes"))
        membro.banco = presidencia.banco

        corpo = membro.api.get("/api/nsp/meu-termo").json()

        [envio] = presidencia.envios("P4")
        assert corpo["pendente"] is True
        bucket = settings.supabase_storage_bucket_nsp_documentos
        assert corpo["documento_url"] == f"https://storage.test/{bucket}/{envio['arquivo_path']}?token=t"

    def test_membro_com_termo_nao_tem_pendencia(self):
        corpo = _Cenario(MEMBRO).api.get("/api/nsp/meu-termo").json()

        assert corpo == {"pendente": False, "documento_url": None}

    def test_super_admin_nao_pergunta_pelo_termo(self):
        _assert_recusado(_Cenario(SUPER_ADMIN).api.get("/api/nsp/meu-termo"))


# ═══════════════════════════════════════════════════════════════════════════
# 7. O PDF: sem travessão nem meia-risca, com conselho, registro e UF
# ═══════════════════════════════════════════════════════════════════════════


class TestPdfDoTermo:
    def test_pdf_traz_conselho_registro_e_uf_e_nao_tem_travessao(self, assinatura):
        """Mutante: tirar o sanitizador dos dados do Termo (o Regimento de teste traz os dois sinais)."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()

        texto = _texto_do_pdf(assinatura.documentos[0])

        assert "CRF nº 000444/RJ" in texto
        assert TRAVESSAO not in texto and MEIA_RISCA not in texto
        assert "Núcleo de Segurança do Paciente, instância consultiva, reúne-se" in texto


# ═══════════════════════════════════════════════════════════════════════════
# 9. Novo Termo: renovação, mudança de papel e revisão material (issue #1769)
# ═══════════════════════════════════════════════════════════════════════════


def _dia_br(delta: int) -> str:
    return (HOJE + timedelta(days=delta)).strftime("%d/%m/%Y")


class TestNovoTermoPorRenovacao:
    def test_renovar_a_vigencia_gera_novo_documento_e_envia_para_assinatura(self, assinatura):
        """Mutante: a renovação não gerar o Termo."""
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["aviso_termo"] is None
        [envio] = cenario.envios("P3")
        assert envio["situacao"] == "enviado"
        assert envio["regimento_id"] == REGIMENTO["id"]
        assert ("add_signer", "env-1", "Pessoa de Teste P3", "p3@hsm.test") in assinatura.chamadas
        assert "activate_envelope" in assinatura.nomes()
        texto = _texto_do_pdf(assinatura.documentos[0])
        assert _dia_br(700) in texto
        assert envio["id"] in texto
        assert len(cenario.trilha("termo_enviado")) == 1

    def test_enquanto_o_novo_termo_nao_e_assinado_o_membro_ativo_segue_ativo(self):
        """Mutante: gerar o novo Termo apagando a assinatura anterior."""
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert resposta.json()["estado"] == "ativo"
        assert cenario.participacao("P3")["termo_assinado_em"] == ASSINADO

    def test_em_carencia_que_renova_segue_contando_ate_assinar(self):
        cenario = _Cenario(
            PRESIDENCIA,
            [_participacao("P2", papel="presidencia"), _participacao("P3", vigencia_fim=_iso(-10))],
        )

        resposta = cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert resposta.json()["estado"] == "ativo"
        assert [e["situacao"] for e in cenario.envios("P3")] == ["enviado"]

    def test_assinar_o_novo_termo_carimba_a_nova_assinatura(self):
        cenario = _Cenario(PRESIDENCIA)
        cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert cenario.retorno_da_assinatura("doc-env-1", "sign").status_code == 200

        assert cenario.participacao("P3")["termo_assinado_em"] != ASSINADO
        assert cenario.estado("P3") == "ativo"
        assert len(cenario.trilha("termo_assinado")) == 1

    def test_renovar_com_termo_ainda_aberto_cancela_o_anterior(self, assinatura):
        """Só um envio aberto por Participação (o índice único da migration 151)."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        part = cenario.participacao("P4")["id"]

        resposta = cenario.api.post(f"{ROTA}/{part}/renovar", json={"vigencia_fim": _iso(700)})

        assert resposta.status_code == 200, resposta.text
        assert ("cancel_envelope", "env-1") in assinatura.chamadas
        assert sorted(e["situacao"] for e in cenario.envios("P4")) == ["cancelado", "enviado"]

    def test_renovacao_com_a_assinatura_fora_do_ar_fica_de_pe_e_avisa(self, assinatura):
        assinatura.falhar_em = "activate_envelope"
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert resposta.status_code == 200
        assert "Reenviar" in resposta.json()["aviso_termo"]
        assert cenario.participacao("P3")["vigencia_fim"] == _iso(700)


class TestNovoTermoPorMudancaDePapel:
    def test_mudar_o_papel_na_mesma_vigencia_gera_novo_documento_e_envia(self, assinatura):
        """Mutante: a edição não gerar o Termo quando o papel muda."""
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.patch(f"{ROTA}/part-P3", json={"papel": "suplente"})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["aviso_termo"] is None
        assert resposta.json()["estado"] == "ativo"
        [envio] = cenario.envios("P3")
        assert envio["situacao"] == "enviado"
        assert ("add_signer", "env-1", "Pessoa de Teste P3", "p3@hsm.test") in assinatura.chamadas
        assert "Suplente da Presidência" in _texto_do_pdf(assinatura.documentos[0])
        assert len(cenario.trilha("termo_enviado")) == 1

    @pytest.mark.parametrize(
        "pedido",
        [{"area": "Centro cirúrgico"}, {"papel": "membro"}, {"registro_profissional": "000033"}],
        ids=["so_a_area", "o_mesmo_papel", "so_o_registro"],
    )
    def test_editar_sem_mudar_o_papel_nao_gera_termo(self, pedido, assinatura):
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.patch(f"{ROTA}/part-P3", json=pedido)

        assert resposta.status_code == 200, resposta.text
        assert assinatura.chamadas == []
        assert cenario.envios("P3") == []


# Um membro em cada estado: P2 Ativo, P3 A vencer, P4 Em carência, P1 Vencido,
# P6 Aguardando assinatura e P5 Encerrado.
def _um_de_cada_estado() -> list[dict]:
    return [
        _participacao("P2", papel="presidencia"),
        _participacao("P3", vigencia_fim=_iso(30)),
        _participacao("P4", vigencia_fim=_iso(-10)),
        _participacao("P1", vigencia_inicio=_iso(-400), vigencia_fim=_iso(-40)),
        _participacao("P6", termo=False, termo_gerado_em=ASSINADO, termo_enviado_em=ASSINADO),
        _participacao("P5", encerrada_em=_iso(-5), vigencia_fim=_iso(-5)),
    ]


TEXTO_DA_REVISAO = "Art. 1º O Núcleo reúne-se quinzenalmente, na revisão material."


def _publicar_regimento(cenario: _Cenario, natureza: str):
    return cenario.api.post(
        "/api/nsp/documentos",
        json={
            "tipo": "regimento",
            "titulo": "Regimento Interno do Núcleo, revisão 3",
            "texto": TEXTO_DA_REVISAO,
            "natureza_revisao": natureza,
        },
    )


class TestNovoTermoPorRevisaoDoRegimento:
    def test_os_estados_do_cenario_sao_os_que_o_teste_diz(self):
        """O detector: sem isto, um cenário errado passaria por filtro certo."""
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        estados = {pid: cenario.estado(pid) for pid in ("P2", "P3", "P4", "P1", "P6", "P5")}

        assert estados == {
            "P2": "ativo",
            "P3": "a_vencer",
            "P4": "em_carencia",
            "P1": "vencido",
            "P6": "aguardando_assinatura",
            "P5": "encerrado",
        }

    def test_revisao_material_gera_novo_termo_para_ativo_a_vencer_e_em_carencia(self, assinatura):
        """Mutante: incluir o Vencido entre os que assinam a revisão."""
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        resposta = _publicar_regimento(cenario, "material")

        assert resposta.status_code == 201, resposta.text
        signatarios = sorted(c[2] for c in assinatura.chamadas if c[0] == "add_signer")
        assert signatarios == ["Pessoa de Teste P2", "Pessoa de Teste P3", "Pessoa de Teste P4"]
        nova = next(d for d in cenario.tabela("nsp_documentos") if d["tipo"] == "regimento" and d["vigente"])
        for pid in ("P2", "P3", "P4"):
            [envio] = cenario.envios(pid)
            assert envio["situacao"] == "enviado"
            assert envio["regimento_id"] == nova["id"]
        for pid in ("P1", "P6", "P5"):
            assert cenario.envios(pid) == []
        assert all("reúne-se quinzenalmente" in _texto_do_pdf(pdf) for pdf in assinatura.documentos)
        assert len(cenario.trilha("termo_enviado")) == 3

    def test_revisao_material_mantem_os_membros_no_estado_ate_assinarem(self):
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        _publicar_regimento(cenario, "material")

        assert cenario.estado("P2") == "ativo"
        assert cenario.estado("P3") == "a_vencer"
        assert cenario.estado("P4") == "em_carencia"

    def test_revisao_de_redacao_nao_gera_documento_nem_envio(self, assinatura):
        """Mutante: a revisão de redação também gerar o Termo."""
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        resposta = _publicar_regimento(cenario, "redacao")

        assert resposta.status_code == 201, resposta.text
        assert "create_envelope" not in assinatura.nomes()
        assert assinatura.chamadas == []
        assert cenario.tabela("nsp_termos_envios") == []
        assert cenario.trilha("termo_enviado") == []

    def test_publicar_outro_tipo_nao_gera_termo(self, assinatura):
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        resposta = cenario.api.post(
            "/api/nsp/documentos",
            json={"tipo": "plano_seguranca_paciente", "titulo": "Plano", "natureza_revisao": "material"},
        )

        assert resposta.status_code == 201, resposta.text
        assert assinatura.chamadas == []

    def test_falha_num_membro_nao_impede_os_outros(self, assinatura):
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())
        p3 = next(p for p in cenario.tabela("participantes") if p["id"] == "P3")
        p3["email"] = None

        resposta = _publicar_regimento(cenario, "material")

        assert resposta.status_code == 201, resposta.text
        signatarios = sorted(c[2] for c in assinatura.chamadas if c[0] == "add_signer")
        assert signatarios == ["Pessoa de Teste P2", "Pessoa de Teste P4"]
        # Quem falhou fica com o reenvio na ficha, depois de corrigir o e-mail.
        p3["email"] = "p3@hsm.test"
        reenvio = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")
        assert reenvio.status_code == 200, reenvio.text
        assert [e["situacao"] for e in cenario.envios("P3")] == ["enviado"]
        assert "reúne-se quinzenalmente" in _texto_do_pdf(assinatura.documentos[-1])

    def test_falha_antes_de_gerar_qualquer_termo_deixa_o_reenvio_para_todos(self, assinatura, monkeypatch):
        """A leitura dos membros estoura depois da publicação. Mutante: a
        pendência da revisão material depender do documento gerado."""
        from app.services.seguranca_do_paciente import termo

        def _estoura(*_a, **_kw):
            raise httpx.ReadTimeout("o banco não respondeu")

        monkeypatch.setattr(termo, "ler_tudo", _estoura)
        cenario = _Cenario(PRESIDENCIA, _um_de_cada_estado())

        resposta = _publicar_regimento(cenario, "material")

        assert resposta.status_code == 201, resposta.text
        assert cenario.tabela("nsp_termos_envios") == []
        pendentes = {m["participante_id"]: m["termo_pendente"] for m in cenario.api.get(ROTA).json()["membros"]}
        assert pendentes == {"P2": True, "P3": True, "P4": True, "P1": False, "P6": True, "P5": False}
        reenvio = cenario.api.post(f"{ROTA}/part-P4/termo/reenviar")
        assert reenvio.status_code == 200, reenvio.text
        assert cenario.api.post(f"{ROTA}/part-P1/termo/reenviar").status_code == 409

    def test_quem_assina_depois_da_revisao_material_nao_tem_termo_pendente(self):
        """A revisão material saiu entre a assinatura de P3 e a de P2."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.tabela("nsp_documentos")[0]["publicado_em"] = "2026-03-01T12:00:00+00:00"
        cenario.participacao("P2")["termo_assinado_em"] = "2026-03-02T09:00:00+00:00"

        assert cenario.api.post(f"{ROTA}/part-P2/termo/reenviar").status_code == 409
        assert cenario.api.post(f"{ROTA}/part-P3/termo/reenviar").status_code == 200


class TestCadaTermoNosDocumentos:
    def test_cada_termo_assinado_fica_nos_documentos_por_membro_e_por_vigencia(self):
        """Mutante: o Termo assinado entrar nos Documentos uma vez por
        Participação (e não por envio)."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        cenario.retorno_da_assinatura("doc-env-1", "sign")
        part = cenario.participacao("P4")["id"]
        cenario.api.post(f"{ROTA}/{part}/renovar", json={"vigencia_fim": _iso(700)})
        [renovacao] = [e for e in cenario.envios("P4") if e["situacao"] == "enviado"]

        assert cenario.retorno_da_assinatura(renovacao["documento_key"], "sign").status_code == 200

        termos = sorted(
            (d for d in cenario.tabela("nsp_documentos") if d["tipo"] == "termo"), key=lambda d: d["versao"]
        )
        assert [d["termo_envio_id"] for d in termos] == [e["id"] for e in cenario.envios("P4")]
        primeiro, segundo = termos
        assert "Pessoa de Teste P4" in primeiro["titulo"] and "Pessoa de Teste P4" in segundo["titulo"]
        assert f"de {_dia_br(0)} a {_dia_br(365)}" in primeiro["titulo"]
        assert f"de {_dia_br(0)} a {_dia_br(700)}" in segundo["titulo"]
        assert primeiro["arquivo_assinado_path"] != segundo["arquivo_assinado_path"]


class TestNovoTermoPendenteNaFicha:
    def test_presidencia_reenvia_o_novo_termo_de_quem_ja_tinha_assinado(self, assinatura):
        """A renovação com a assinatura fora do ar manda usar o reenvio, e o
        membro tem a assinatura anterior. Mutante: o reenvio recusar todo
        membro com assinatura."""
        assinatura.falhar_em = "activate_envelope"
        cenario = _Cenario(PRESIDENCIA)
        cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})
        assinatura.falhar_em = None

        resposta = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["aviso_termo"] is None
        assert sorted(e["situacao"] for e in cenario.envios("P3")) == ["cancelado", "enviado"]

    def test_carimbo_do_novo_termo_que_falhou_se_conserta_na_reconsulta(self, assinatura):
        """O membro já tinha assinatura; o novo Termo virou assinado e o
        carimbo estourou. Mutante: o conserto pular quem já tem assinatura."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})
        tabela_de_verdade = cenario.banco.table
        falhas = {"restantes": 1}

        class _CarimboQueEstoura(_Consulta):
            def execute(self):
                operacao, carga = self._operacao
                if operacao == "update" and "termo_assinado_em" in carga and falhas["restantes"]:
                    falhas["restantes"] -= 1
                    raise httpx.ReadTimeout("o banco não respondeu")
                return super().execute()

        cenario.banco.table = lambda nome: (
            _CarimboQueEstoura(cenario.banco, nome) if nome == "participacoes" else tabela_de_verdade(nome)
        )
        assert cenario.retorno_da_assinatura("doc-env-1", "sign").status_code == 500
        assinatura.status = "closed"

        assert cenario.api.post(f"{ROTA}/part-P3/termo/reconsultar").status_code == 200
        assert cenario.api.post(f"{ROTA}/part-P3/termo/reconsultar").status_code == 200

        [envio] = cenario.envios("P3")
        assert cenario.participacao("P3")["termo_assinado_em"] == envio["assinado_em"]
        assert len(cenario.trilha("termo_assinado")) == 1

    def test_renovacao_sem_email_deixa_o_reenvio_para_depois_de_corrigir_o_cadastro(self, assinatura):
        """O Termo nem chega a ser gerado (a pessoa não tem e-mail). Mutante:
        o Termo novo só contar como pendente depois do documento gerado."""
        cenario = _Cenario(PRESIDENCIA)
        p3 = next(p for p in cenario.tabela("participantes") if p["id"] == "P3")
        p3["email"] = None

        renovacao = cenario.api.post(f"{ROTA}/part-P3/renovar", json={"vigencia_fim": _iso(700)})

        assert "e-mail" in renovacao.json()["aviso_termo"]
        assert renovacao.json()["termo_pendente"] is True
        assert cenario.envios("P3") == []
        p3["email"] = "p3@hsm.test"
        resposta = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")
        assert resposta.status_code == 200, resposta.text
        assert [e["situacao"] for e in cenario.envios("P3")] == ["enviado"]
        assert _dia_br(700) in _texto_do_pdf(assinatura.documentos[0])

    def test_mudanca_de_papel_com_o_pdf_falhando_deixa_o_reenvio(self, assinatura, monkeypatch):
        """O WeasyPrint estoura antes do carimbo do documento gerado."""
        from app.services.seguranca_do_paciente import termo

        def _estoura(_dados):
            raise TimeoutError("o PDF não saiu")

        pdf_de_verdade = termo.gerar_pdf_do_termo
        monkeypatch.setattr(termo, "gerar_pdf_do_termo", _estoura)
        cenario = _Cenario(PRESIDENCIA)

        edicao = cenario.api.patch(f"{ROTA}/part-P3", json={"papel": "suplente"})

        assert "Reenviar" in edicao.json()["aviso_termo"]
        assert edicao.json()["termo_pendente"] is True
        monkeypatch.setattr(termo, "gerar_pdf_do_termo", pdf_de_verdade)
        resposta = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")
        assert resposta.status_code == 200, resposta.text
        assert "Suplente da Presidência" in _texto_do_pdf(assinatura.documentos[-1])

    def test_reconsultar_o_termo_antigo_nao_carimba_o_novo_que_nao_saiu(self, assinatura):
        """O último envio é o Termo antigo, já assinado; o novo nem foi gerado.
        Mutante: o conserto do carimbo aceitar o envio que já estava carimbado."""
        cenario = _Cenario(PRESIDENCIA)
        cenario.cadastrar()
        cenario.retorno_da_assinatura("doc-env-1", "sign")
        part = cenario.participacao("P4")["id"]
        next(p for p in cenario.tabela("participantes") if p["id"] == "P4")["email"] = None
        cenario.api.post(f"{ROTA}/{part}/renovar", json={"vigencia_fim": _iso(700)})
        assinatura.status = "closed"

        resposta = cenario.api.post(f"{ROTA}/{part}/termo/reconsultar")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["termo_pendente"] is True
        assert len(cenario.trilha("termo_assinado")) == 1

    def test_membro_ativo_sem_termo_novo_continua_sem_reenvio(self):
        cenario = _Cenario(PRESIDENCIA)

        resposta = cenario.api.post(f"{ROTA}/part-P3/termo/reenviar")

        assert resposta.status_code == 409
        assert resposta.json() == {"detail": "O Termo deste membro já está assinado."}


# ═══════════════════════════════════════════════════════════════════════════
# 8. Nenhum teste chama a assinatura eletrônica de verdade
# ═══════════════════════════════════════════════════════════════════════════


def test_toda_chamada_do_termo_a_assinatura_eletronica_esta_dublada():
    """O dublê autouse cobre toda função de `clicksign_service` que o Termo
    chama. Função nova sem dublê faz este teste falhar.
    Mutante: tirar `cancel_envelope` da lista do dublê."""
    from app.services.seguranca_do_paciente import termo

    with open(termo.__file__, encoding="utf-8") as arquivo:
        usadas = set(re.findall(r"clicksign_service\.(\w+)\(", arquivo.read()))
    assert "create_envelope" in usadas
    for nome in usadas:
        assert isinstance(getattr(getattr(clicksign_service, nome), "__self__", None), _Assinatura), nome
