"""Testes dos Materiais de referência da elaboração de POP (issue #84).

Materiais de referência (docs/pops/CONTEXT.md): arquivos que o Elaborador
sobe na Elaboração (POPs antigos, RDCs, resoluções, artigos). O agente os lê
e usa **ativamente** — pode reescrever e reestruturar sem preservar o
original. Conduta oposta à do Documento de apoio da Ata Guiada (contexto sob
demanda). Extração reusa o extractor existente (.txt/.md/.pdf/.docx); o
texto extraído persiste vinculado à Versão e entra no prompt do agente em
toda interação; remover o material o tira do contexto seguinte.

LLM SEMPRE mockado (padrão test_pops_elaboracao): testa contrato e presença
no prompt, nunca qualidade de texto. Storage mockado no boundary
(app.services.storage) — upload é best-effort: o valor central é o texto.
"""

from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import elaboracao as elaboracao_router  # noqa: E402
from app.services import storage  # noqa: E402

# ─── Mock Supabase (padrão do test_pops_elaboracao, + delete) ─────────────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None
        self._delete = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
        return self

    def delete(self):
        self._delete = True
        return self

    def execute(self):
        if self._insert_payload is not None:
            inserted = []
            for row in self._insert_payload:
                row = dict(row)
                row.setdefault("id", f"{self._table}-{len(self._rows) + 1}")
                self._rows.append(row)
                inserted.append(dict(row))
            return _Result(data=inserted)

        filtered = [
            r
            for r in self._rows
            if all(r.get(c) == v for c, v in self._filters.items())
            and all(r.get(c) in vs for c, vs in self._in_filters.items())
        ]

        if self._delete:
            self._rows[:] = [r for r in self._rows if r not in filtered]
            return _Result(data=[dict(r) for r in filtered])

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        return _Result(data=[dict(r) for r in filtered])


class _SupabaseMock:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables

    def table(self, name: str):
        if name not in self.tables:
            raise AssertionError(f"Tabela inesperada: {name}")
        return _TableQuery(self.tables[name], name)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _pessoa(pid: str, perfil_pop: str | None = None) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "email": f"{pid.lower()}@hsm.com",
        "nome_completo": f"Pessoa {pid}",
        "cargo": "Cargo",
        "ativo": True,
        "is_externo": False,
        "is_super_admin": False,
        "access_profile": None,
        "perfil_pop": perfil_pop,
    }


def _pop(**over) -> dict:
    base = {
        "id": "pop-1",
        "setor_id": "s-cti",
        "numero": 1,
        "codigo": "HSM_CTI-001",
        "nome": "Higienização das Mãos",
        "criticidade": "CRITICA",
        "base_normativa": "RDC 63/2011",
        "periodicidade_revisao": "1_ano",
        "prazo_elaboracao_dias": 15,
        "prazo_revisao_dias": 30,
        "elaborador_id": "P1",
        "revisor_id": "P2",
        "validador_id": "P3",
        "criado_por": "P4",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


def _versao(**over) -> dict:
    base = {
        "id": "v-1",
        "pop_id": "pop-1",
        "numero_versao": "1.0",
        "estado": "EM_ELABORACAO",
        "rascunho": None,
        "periodicidade_sugerida": None,
    }
    base.update(over)
    return base


def _material(mid: str, *, versao_id: str = "v-1", filename: str = "ref.txt", texto: str = "Texto.", **over) -> dict:
    base = {
        "id": mid,
        "versao_id": versao_id,
        "filename": filename,
        "extensao": ".txt",
        "tamanho_bytes": len(texto.encode("utf-8")),
        "storage_path": f"versao-{versao_id}/{mid}.txt",
        "texto": texto,
        "criado_por": "P1",
        "created_at": "2026-06-11T09:00:00+00:00",
    }
    base.update(over)
    return base


ELABORADOR = _pessoa("P1", perfil_pop="coordenador")
REVISOR = _pessoa("P2", perfil_pop="gestor_qualidade")
VALIDADOR = _pessoa("P3", perfil_pop="gerente")
INTRUSO = _pessoa("P4", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("P5", perfil_pop=None)


def _sb(versao: dict | None = None, pop: dict | None = None, materiais: list[dict] | None = None) -> _SupabaseMock:
    return _SupabaseMock(
        {
            "participantes": [ELABORADOR, REVISOR, VALIDADOR, INTRUSO, SEM_PERFIL],
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
            "pops_materiais_referencia": list(materiais or []),
            # O GET/chat da elaboração consultam as Devoluções (#85).
            "pops_devolucoes": [],
            "audit_log": [],
        }
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O limiter do slowapi acumula hits por IP entre arquivos da suíte (storage
    global); zera antes de cada teste pra cada um partir limpo."""
    from app.limiter import limiter

    limiter._storage.reset()
    yield


@pytest.fixture(autouse=True)
def _mock_llm_by_default(monkeypatch):
    """O pytest carrega o `.env` real (chave OpenRouter de PROD); força o caminho
    MOCK por padrão — os testes da IA real sobrescrevem com `_stub_openrouter`."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


@pytest.fixture(autouse=True)
def storage_mock(monkeypatch) -> SimpleNamespace:
    """Storage no boundary de IO: registra uploads/remoções sem rede. Upload é
    best-effort no endpoint — o teste de indisponibilidade troca o retorno."""
    chamadas = SimpleNamespace(uploads=[], removidos=[], upload_retorno="https://storage/fake")

    def _fake_upload(_supabase, bucket: str, path: str, content: bytes, content_type: str = "") -> str | None:
        chamadas.uploads.append({"bucket": bucket, "path": path, "tamanho": len(content), "content_type": content_type})
        return chamadas.upload_retorno

    def _fake_delete(_supabase, bucket: str, path: str) -> bool:
        chamadas.removidos.append({"bucket": bucket, "path": path})
        return True

    monkeypatch.setattr(storage, "upload_file", _fake_upload)
    monkeypatch.setattr(storage, "delete_file", _fake_delete, raising=False)
    return chamadas


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    from app.limiter import limiter

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(elaboracao_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ─── Arquivos de teste (bytes reais — o extractor roda de verdade) ────────────


def _pdf_minimo(linhas: list[str]) -> bytes:
    """PDF 1.4 mínimo com texto extraível pelo pdfplumber (xref válido).
    O extractor rejeita PDFs com <200 bytes de texto — mande linhas bastantes."""
    conteudo = "BT /F1 12 Tf 72 720 Td " + " ".join(f"({linha}) Tj 0 -16 Td" for linha in linhas) + " ET"
    stream = conteudo.encode("latin-1")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = []
    for i, corpo in enumerate(objetos, start=1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + corpo + b"\nendobj\n")
    xref_pos = out.tell()
    out.write(f"xref\n0 {len(objetos) + 1}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(
        b"trailer\n<< /Size "
        + str(len(objetos) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF\n"
    )
    return out.getvalue()


def _docx_minimo(texto: str) -> bytes:
    """DOCX mínimo (zip com word/document.xml) que o docx2txt lê."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{texto}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def _upload(client: TestClient, *arquivos: tuple[str, bytes, str]):
    return client.post(
        "/api/pops/pop-1/elaboracao/materiais",
        files=[("files", (nome, conteudo, ctype)) for nome, conteudo, ctype in arquivos],
    )


# ─── Fake LLM (nunca toca o OpenRouter real — padrão test_pops_elaboracao) ────


class _FakeCompletions:
    def __init__(self, *, content: str | None, exc: Exception | None, calls: list):
        self._content = content
        self._exc = exc
        self._calls = calls

    def create(self, **kwargs):
        self._calls.append(kwargs)
        if self._exc is not None:
            raise self._exc
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self._content))])


class _FakeLLMClient:
    def __init__(self, *, content: str | None = None, exc: Exception | None = None):
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=_FakeCompletions(content=content, exc=exc, calls=self.calls))


def _stub_openrouter(monkeypatch, *, content: str | None = None, exc: Exception | None = None) -> _FakeLLMClient:
    from app.services import ai_processor

    client = _FakeLLMClient(content=content, exc=exc)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (client, "modelo-teste", {}))
    return client


def _resposta_ia(reply: str = "Anotei.") -> str:
    return json.dumps(
        {
            "reply": reply,
            "rascunho": {"objetivo": "Padronizar a higienização das mãos."},
            "periodicidade_sugerida": None,
        }
    )


def _chat(client: TestClient, *, mensagem: str = "Use os materiais que enviei."):
    return client.post(
        "/api/pops/pop-1/elaboracao/chat",
        json={"rascunho": {}, "messages": [{"role": "user", "content": mensagem}], "section_context": None},
    )


# ═══════════════════════════════════════════════════════════════════════════
# POST /pops/{pop_id}/elaboracao/materiais — upload múltiplo com extração
# ═══════════════════════════════════════════════════════════════════════════


class TestUploadMateriais:
    def test_upload_multiplo_extrai_e_persiste_por_versao(self, sb=None):
        """CA: upload múltiplo simultâneo com extração e persistência por
        Versão — cada arquivo vira um Material com o texto extraído."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _upload(
            client,
            ("POP-antigo.txt", b"Procedimento antigo de higienizacao.", "text/plain"),
            ("RDC-63.md", b"# RDC 63\nRequisitos de boas praticas.", "text/markdown"),
        )

        assert res.status_code == 200
        body = res.json()
        assert body["erros"] == []
        assert [m["filename"] for m in body["materiais"]] == ["POP-antigo.txt", "RDC-63.md"]
        assert [m["extensao"] for m in body["materiais"]] == [".txt", ".md"]

        rows = sb.tables["pops_materiais_referencia"]
        assert len(rows) == 2
        assert all(r["versao_id"] == "v-1" for r in rows)
        assert rows[0]["texto"] == "Procedimento antigo de higienizacao."
        assert "Requisitos de boas praticas." in rows[1]["texto"]

    def test_upload_extrai_pdf(self):
        """CA: extração por formato — PDF real passa pelo extractor existente."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)
        linhas = ["RDC 63 de 2011 dispoe sobre requisitos de boas praticas de funcionamento."] * 5

        res = _upload(client, ("rdc63.pdf", _pdf_minimo(linhas), "application/pdf"))

        assert res.status_code == 200
        assert res.json()["erros"] == []
        rows = sb.tables["pops_materiais_referencia"]
        assert len(rows) == 1
        assert rows[0]["extensao"] == ".pdf"
        assert "RDC 63 de 2011" in rows[0]["texto"]

    def test_upload_extrai_docx(self):
        """CA: extração por formato — DOCX real passa pelo extractor existente."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _upload(
            client,
            (
                "protocolo.docx",
                _docx_minimo("Protocolo de higienizacao das maos conforme ANVISA."),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        )

        assert res.status_code == 200
        assert res.json()["erros"] == []
        rows = sb.tables["pops_materiais_referencia"]
        assert rows[0]["extensao"] == ".docx"
        assert "Protocolo de higienizacao" in rows[0]["texto"]

    def test_upload_formato_nao_suportado_erro_claro_sem_persistir(self):
        """CA: formato não suportado → erro claro por arquivo, sem quebrar a
        tela (resposta 200 estruturada) e sem persistir nada."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _upload(client, ("planilha.xlsx", b"binario-qualquer", "application/octet-stream"))

        assert res.status_code == 200
        body = res.json()
        assert body["materiais"] == []
        assert len(body["erros"]) == 1
        assert body["erros"][0]["filename"] == "planilha.xlsx"
        assert "Formato nao suportado" in body["erros"][0]["detail"]
        assert sb.tables["pops_materiais_referencia"] == []

    def test_upload_tamanho_excedido_erro_claro(self):
        """CA: tamanho excedido → erro claro (limite do extractor: 5 MB para
        texto), sem persistir."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)
        grande = b"x" * (5 * 1024 * 1024 + 1)

        res = _upload(client, ("gigante.txt", grande, "text/plain"))

        assert res.status_code == 200
        body = res.json()
        assert body["materiais"] == []
        assert "excede o limite" in body["erros"][0]["detail"]
        assert sb.tables["pops_materiais_referencia"] == []

    def test_upload_misto_persiste_validos_e_reporta_invalidos(self):
        """Upload múltiplo é por-arquivo: o válido entra, o inválido volta com
        erro claro — um PDF escaneado não invalida os demais."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _upload(
            client,
            ("valido.txt", b"Conteudo valido de referencia.", "text/plain"),
            ("legado.doc", b"formato legado", "application/msword"),
        )

        assert res.status_code == 200
        body = res.json()
        assert [m["filename"] for m in body["materiais"]] == ["valido.txt"]
        assert [e["filename"] for e in body["erros"]] == ["legado.doc"]
        assert ".docx" in body["erros"][0]["detail"]  # mensagem orienta o formato certo
        assert len(sb.tables["pops_materiais_referencia"]) == 1

    def test_upload_storage_indisponivel_persiste_texto(self, storage_mock):
        """Storage é best-effort: o valor central é o texto extraído no banco.
        Upload falhou → material persiste com storage_path nulo, sem erro."""
        storage_mock.upload_retorno = None
        sb = _sb()
        client = _client_para(ELABORADOR, sb)

        res = _upload(client, ("ref.txt", b"Texto de referencia.", "text/plain"))

        assert res.status_code == 200
        assert res.json()["erros"] == []
        rows = sb.tables["pops_materiais_referencia"]
        assert len(rows) == 1
        assert rows[0]["storage_path"] is None
        assert rows[0]["texto"] == "Texto de referencia."

    def test_upload_sobe_arquivo_original_ao_storage(self, storage_mock):
        """O arquivo original vai ao storage (bucket de materiais) e o path
        fica gravado no Material."""
        sb = _sb()
        client = _client_para(ELABORADOR, sb)
        conteudo = b"Texto de referencia."

        res = _upload(client, ("ref.txt", conteudo, "text/plain"))

        assert res.status_code == 200
        assert len(storage_mock.uploads) == 1
        upload = storage_mock.uploads[0]
        assert upload["tamanho"] == len(conteudo)
        assert upload["path"].endswith(".txt")
        assert sb.tables["pops_materiais_referencia"][0]["storage_path"] == upload["path"]

    def test_upload_nao_elaborador_403(self):
        """CA: só o Elaborador designado anexa materiais — até perfis de escopo
        total (Gestor de Qualidade) levam 403."""
        for pessoa in (INTRUSO, REVISOR):
            sb = _sb()
            client = _client_para(pessoa, sb)
            res = _upload(client, ("ref.txt", b"Texto.", "text/plain"))
            assert res.status_code == 403, f"{pessoa['id']} deveria levar 403"
            assert sb.tables["pops_materiais_referencia"] == []

    def test_upload_sem_perfil_pop_403(self):
        client = _client_para(SEM_PERFIL, _sb())
        res = _upload(client, ("ref.txt", b"Texto.", "text/plain"))
        assert res.status_code == 403

    def test_upload_estado_invalido_400(self):
        """Fora da elaboração (Versão já em revisão ou além) não entra material."""
        for estado in ("EM_REVISAO", "EM_VALIDACAO", "EM_ASSINATURA", "PUBLICADO"):
            sb = _sb(versao=_versao(estado=estado))
            client = _client_para(ELABORADOR, sb)
            res = _upload(client, ("ref.txt", b"Texto.", "text/plain"))
            assert res.status_code == 400, f"estado {estado} deveria dar 400"
            assert sb.tables["pops_materiais_referencia"] == []

    def test_upload_pop_inexistente_404(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.post(
            "/api/pops/pop-999/elaboracao/materiais",
            files=[("files", ("ref.txt", b"Texto.", "text/plain"))],
        )
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════
# Materiais no contexto do agente — uso ativo, em toda interação
# ═══════════════════════════════════════════════════════════════════════════


class TestMateriaisNoContextoDoAgente:
    def test_materiais_entram_no_prompt_em_toda_interacao(self, monkeypatch):
        """CA: o texto dos materiais entra no contexto do agente em TODA
        interação (verificável com LLM mockado) — o chat lê da Versão, não
        depende do cliente reenviar."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        materiais = [
            _material("m-1", filename="POP-antigo.txt", texto="Procedimento antigo de higienizacao das maos."),
            _material("m-2", filename="RDC-63.md", texto="RDC 63 exige paramentacao adequada."),
        ]
        client = _client_para(ELABORADOR, _sb(materiais=materiais))

        _chat(client)
        _chat(client, mensagem="Continue a descricao do procedimento.")

        assert len(client_llm.calls) == 2
        for call in client_llm.calls:
            user_prompt = call["messages"][1]["content"]
            assert "MATERIAIS DE REFERÊNCIA" in user_prompt
            assert "POP-antigo.txt" in user_prompt
            assert "Procedimento antigo de higienizacao das maos." in user_prompt
            assert "RDC-63.md" in user_prompt
            assert "RDC 63 exige paramentacao adequada." in user_prompt

    def test_remocao_tira_do_contexto_das_interacoes_seguintes(self, monkeypatch):
        """CA: remover material o tira do contexto das interações seguintes —
        o que ficou continua entrando."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        materiais = [
            _material("m-1", filename="removido.txt", texto="Conteudo que sera removido."),
            _material("m-2", filename="mantido.txt", texto="Conteudo que permanece."),
        ]
        sb = _sb(materiais=materiais)
        client = _client_para(ELABORADOR, sb)

        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-1")
        assert res.status_code == 204

        _chat(client)

        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "Conteudo que sera removido." not in user_prompt
        assert "removido.txt" not in user_prompt
        assert "Conteudo que permanece." in user_prompt

    def test_sem_materiais_prompt_sem_bloco(self, monkeypatch):
        """Sem materiais o bloco some do prompt — o agente não vê seção vazia."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb())

        _chat(client)

        user_prompt = client_llm.calls[0]["messages"][1]["content"]
        assert "MATERIAIS DE REFERÊNCIA" not in user_prompt

    def test_system_prompt_orienta_uso_ativo_dos_materiais(self, monkeypatch):
        """Conduta oposta ao Documento de apoio da Guiada (DRF §4.2): ler
        criticamente, apontar lacunas e reescrever sem preservar o original."""
        client_llm = _stub_openrouter(monkeypatch, content=_resposta_ia())
        client = _client_para(ELABORADOR, _sb(materiais=[_material("m-1")]))

        _chat(client)

        system_prompt = client_llm.calls[0]["messages"][0]["content"]
        assert "Materiais de referência" in system_prompt
        assert "criticamente" in system_prompt
        assert "lacunas" in system_prompt


# ═══════════════════════════════════════════════════════════════════════════
# DELETE /pops/{pop_id}/elaboracao/materiais/{material_id}
# ═══════════════════════════════════════════════════════════════════════════


class TestRemoverMaterial:
    def test_delete_remove_material_e_arquivo_do_storage(self, storage_mock):
        sb = _sb(materiais=[_material("m-1", storage_path="versao-v-1/m-1.txt")])
        client = _client_para(ELABORADOR, sb)

        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-1")

        assert res.status_code == 204
        assert sb.tables["pops_materiais_referencia"] == []
        assert storage_mock.removidos == [{"bucket": storage_mock.removidos[0]["bucket"], "path": "versao-v-1/m-1.txt"}]

    def test_delete_material_inexistente_404(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-999")
        assert res.status_code == 404

    def test_delete_material_de_outra_versao_404(self):
        """Material de outra Versão não é alcançável por este POP — 404, e
        nada some do banco."""
        sb = _sb(materiais=[_material("m-outro", versao_id="v-2")])
        client = _client_para(ELABORADOR, sb)

        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-outro")

        assert res.status_code == 404
        assert len(sb.tables["pops_materiais_referencia"]) == 1

    def test_delete_nao_elaborador_403(self):
        sb = _sb(materiais=[_material("m-1")])
        client = _client_para(INTRUSO, sb)

        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-1")

        assert res.status_code == 403
        assert len(sb.tables["pops_materiais_referencia"]) == 1

    def test_delete_estado_invalido_400(self):
        """A Versão saiu da elaboração: os materiais ficam congelados com ela."""
        sb = _sb(versao=_versao(estado="EM_REVISAO"), materiais=[_material("m-1")])
        client = _client_para(ELABORADOR, sb)

        res = client.delete("/api/pops/pop-1/elaboracao/materiais/m-1")

        assert res.status_code == 400
        assert len(sb.tables["pops_materiais_referencia"]) == 1


# ═══════════════════════════════════════════════════════════════════════════
# GET /pops/{pop_id}/elaboracao — a lista de materiais carrega com a tela
# ═══════════════════════════════════════════════════════════════════════════


class TestGetElaboracaoComMateriais:
    def test_get_devolve_materiais_da_versao(self):
        """A tela carrega a lista junto do rascunho — payload enxuto, sem o
        texto extraído (que é insumo do agente, não da UI)."""
        materiais = [
            _material("m-1", filename="POP-antigo.txt", texto="Um texto bem grande de referencia."),
            _material("m-2", filename="RDC-63.md", extensao=".md", texto="Outro texto."),
        ]
        client = _client_para(ELABORADOR, _sb(materiais=materiais))

        res = client.get("/api/pops/pop-1/elaboracao")

        assert res.status_code == 200
        body = res.json()
        assert [m["filename"] for m in body["materiais"]] == ["POP-antigo.txt", "RDC-63.md"]
        assert [m["extensao"] for m in body["materiais"]] == [".txt", ".md"]
        assert all("texto" not in m for m in body["materiais"])
        assert all(m["tamanho_bytes"] > 0 for m in body["materiais"])

    def test_get_sem_materiais_lista_vazia(self):
        client = _client_para(ELABORADOR, _sb())
        res = client.get("/api/pops/pop-1/elaboracao")
        assert res.status_code == 200
        assert res.json()["materiais"] == []
