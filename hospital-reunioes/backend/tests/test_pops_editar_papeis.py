"""Testes da edição de papéis do POP: Elaborador/Revisor/Validador (issue #156).

ADR 0015 (docs/pops/CONTEXT.md, PRD #76): os papéis do fluxo deixam de ser
imutáveis. Um PATCH /pops/{id} edita SOMENTE elaborador_id, revisor_id e
validador_id enquanto a Versão ativa (a mais recente) estiver antes da
assinatura (A_ELABORAR, EM_ELABORACAO, EM_REVISAO ou EM_VALIDACAO). Trava em
EM_ASSINATURA e PUBLICADO. Quem edita = mesmo escopo de quem cria o POP
(Superadmin POP e Gestor de Qualidade institucionais; Gerente/Coordenador nos
seus Setores), senão 403. Ao trocar, a pessoa nova da etapa ativa é notificada.
O Código permanece imutável: o endpoint rejeita qualquer campo fora dos papéis.

Supabase mock no padrão de test_pops_criar (com order/limit reais p/ a Versão
mais recente); emails capturados no boundary de IO.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.routers.pops import pops as pops_router  # noqa: E402
from app.services import pops_email_service  # noqa: E402

# ─── Mock Supabase (padrão test_pops_criar, com order/limit reais) ────────────


@dataclass
class _Result:
    data: list


class _TableQuery:
    def __init__(self, rows: list[dict], table: str):
        self._rows = rows
        self._table = table
        self._filters: dict = {}
        self._in_filters: dict = {}
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._insert_payload: list[dict] | None = None
        self._update_payload: dict | None = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def in_(self, col, values):
        self._in_filters[col] = list(values)
        return self

    def order(self, col, *, desc: bool = False, **_kwargs):
        self._order = (col, desc)
        return self

    def limit(self, n: int, *_args, **_kwargs):
        self._limit = n
        return self

    def insert(self, payload: dict | list):
        rows = payload if isinstance(payload, list) else [payload]
        self._insert_payload = [dict(r) for r in rows]
        return self

    def update(self, payload: dict):
        self._update_payload = dict(payload)
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

        if self._update_payload is not None:
            for row in filtered:
                row.update(self._update_payload)
            return _Result(data=[dict(r) for r in filtered])

        if self._order is not None:
            col, desc = self._order
            filtered = sorted(filtered, key=lambda r: (r.get(col) is None, r.get(col) or ""), reverse=desc)
        if self._limit is not None:
            filtered = filtered[: self._limit]

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
        "estado": "A_ELABORAR",
        "created_at": "2026-06-10T12:00:00+00:00",
    }
    base.update(over)
    return base


# Quem CRIA o POP (e portanto edita): institucionais + de Setor.
SUPERADMIN = _pessoa("ADM", perfil_pop="superadmin")
GESTOR_QUALIDADE = _pessoa("GQ", perfil_pop="gestor_qualidade")
COORDENADOR = _pessoa("CO", perfil_pop="coordenador")
SEM_PERFIL = _pessoa("NX", perfil_pop=None)

# Designáveis (têm perfil POP) usados como papéis atuais e novos.
P1 = _pessoa("P1", perfil_pop="coordenador")
P2 = _pessoa("P2", perfil_pop="gestor_qualidade")
P3 = _pessoa("P3", perfil_pop="gerente")
P4 = _pessoa("P4", perfil_pop="coordenador")
NOVO = _pessoa("P9", perfil_pop="coordenador")
NOVO_SEM_PERFIL = _pessoa("P8", perfil_pop=None)


def _sb(
    *,
    versao: dict | None = None,
    pop: dict | None = None,
    vinculos: list[dict] | None = None,
    participantes: list[dict] | None = None,
) -> _SupabaseMock:
    pessoas = participantes or [
        SUPERADMIN,
        GESTOR_QUALIDADE,
        COORDENADOR,
        SEM_PERFIL,
        P1,
        P2,
        P3,
        P4,
        NOVO,
        NOVO_SEM_PERFIL,
    ]
    return _SupabaseMock(
        {
            "participantes": pessoas,
            "pops_setores": [{"id": "s-cti", "nome": "Coordenação do CTI", "sigla": "CTI"}],
            "pops_setores_participantes": list(vinculos or []),
            "pops": [pop or _pop()],
            "pops_versoes": [versao or _versao()],
            "audit_log": [],
        }
    )


@pytest.fixture(autouse=True)
def emails_enviados(monkeypatch) -> list[dict]:
    """Captura emails no boundary de IO: template e montagem rodam de verdade."""
    capturados: list[dict] = []

    def _fake_enviar(destinatario: str, assunto: str, html_content: str, texto_fallback: str) -> bool:
        capturados.append(
            {"destinatario": destinatario, "assunto": assunto, "html": html_content, "texto": texto_fallback}
        )
        return True

    monkeypatch.setattr(pops_email_service, "_enviar_email", _fake_enviar)
    return capturados


def _client_para(pessoa: dict, sb: _SupabaseMock) -> TestClient:
    app = FastAPI()
    app.include_router(pops_router.router, prefix="/api")

    async def _fake_user() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Edição permitida nos 4 estados antes da assinatura
# ═══════════════════════════════════════════════════════════════════════════


class TestEdicaoPermitidaAntesDaAssinatura:
    @pytest.mark.parametrize("estado", ["A_ELABORAR", "EM_ELABORACAO", "EM_REVISAO", "EM_VALIDACAO"])
    def test_edita_os_tres_papeis_nos_estados_pre_assinatura(self, estado):
        sb = _sb(versao=_versao(estado=estado))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch(
            "/api/pops/pop-1",
            json={"elaborador_id": "P9", "revisor_id": "P9", "validador_id": "P9"},
        )

        assert res.status_code == 200, res.text
        pop = sb.tables["pops"][0]
        assert pop["elaborador_id"] == "P9"
        assert pop["revisor_id"] == "P9"
        assert pop["validador_id"] == "P9"
        # O Código nunca muda.
        assert pop["codigo"] == "HSM_CTI-001"

    def test_edicao_parcial_so_altera_o_campo_enviado(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})

        assert res.status_code == 200, res.text
        pop = sb.tables["pops"][0]
        assert pop["revisor_id"] == "P9"
        assert pop["elaborador_id"] == "P1"  # intocado
        assert pop["validador_id"] == "P3"  # intocado

    def test_edicao_audita_com_autor_e_papeis(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})

        assert res.status_code == 200, res.text
        registros = sb.tables["audit_log"]
        assert len(registros) == 1
        log = registros[0]
        assert log["action"] == "POPS_EDITAR_PAPEIS"
        assert log["target_type"] == "pop"
        assert log["target_id"] == "pop-1"
        assert log["actor_id"] == "GQ"
        assert log["metadata"]["revisor_id"] == "P9"


# ═══════════════════════════════════════════════════════════════════════════
# Edição travada a partir da assinatura
# ═══════════════════════════════════════════════════════════════════════════


class TestEdicaoTravadaNaAssinatura:
    @pytest.mark.parametrize("estado", ["EM_ASSINATURA", "PUBLICADO"])
    def test_bloqueia_edicao_em_assinatura_e_publicado(self, estado):
        sb = _sb(versao=_versao(estado=estado))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})

        assert res.status_code == 400, res.text
        # Nada muda na trava.
        assert sb.tables["pops"][0]["revisor_id"] == "P2"

    def test_versao_ativa_e_a_mais_recente(self):
        # POP com duas Versões: a vigente Publicada e nenhuma em fluxo → travado.
        sb = _sb(
            versao=_versao(estado="PUBLICADO"),
        )
        # adiciona uma 2ª Versão mais antiga já encerrada (não deve destravar)
        sb.tables["pops_versoes"].append(
            _versao(id="v-0", numero_versao="0.9", estado="A_ELABORAR", created_at="2026-01-01T00:00:00+00:00")
        )
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})

        assert res.status_code == 400, res.text


# ═══════════════════════════════════════════════════════════════════════════
# Escopo de quem pode editar (mesmo de quem cria)
# ═══════════════════════════════════════════════════════════════════════════


class TestEscopoDeEdicao:
    def test_institucionais_editam_qualquer_setor(self):
        for ator in (SUPERADMIN, GESTOR_QUALIDADE):
            sb = _sb(versao=_versao(estado="A_ELABORAR"))
            client = _client_para(ator, sb)
            res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})
            assert res.status_code == 200, f"{ator['perfil_pop']}: {res.text}"

    def test_coordenador_no_seu_setor_edita(self):
        sb = _sb(
            versao=_versao(estado="A_ELABORAR"),
            vinculos=[{"setor_id": "s-cti", "participante_id": "CO"}],
        )
        client = _client_para(COORDENADOR, sb)
        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})
        assert res.status_code == 200, res.text

    def test_coordenador_fora_do_seu_setor_recebe_403(self):
        sb = _sb(
            versao=_versao(estado="A_ELABORAR"),
            vinculos=[{"setor_id": "s-outro", "participante_id": "CO"}],
        )
        client = _client_para(COORDENADOR, sb)
        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})
        assert res.status_code == 403, res.text
        assert sb.tables["pops"][0]["revisor_id"] == "P2"

    def test_sem_perfil_pop_recebe_403(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(SEM_PERFIL, sb)
        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})
        assert res.status_code == 403, res.text


# ═══════════════════════════════════════════════════════════════════════════
# Código imutável: o PATCH rejeita campos fora dos papéis
# ═══════════════════════════════════════════════════════════════════════════


class TestCodigoImutavel:
    def test_codigo_no_corpo_e_rejeitado(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"codigo": "HSM_CTI-999", "revisor_id": "P9"})

        assert res.status_code == 422, res.text
        assert sb.tables["pops"][0]["codigo"] == "HSM_CTI-001"
        assert sb.tables["pops"][0]["revisor_id"] == "P2"  # nada foi aplicado

    def test_campo_fora_dos_papeis_e_rejeitado(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"nome": "Outro nome", "setor_id": "s-far"})

        assert res.status_code == 422, res.text
        assert sb.tables["pops"][0]["nome"] == "Higienização das Mãos"
        assert sb.tables["pops"][0]["setor_id"] == "s-cti"

    def test_corpo_vazio_e_rejeitado(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)
        res = client.patch("/api/pops/pop-1", json={})
        assert res.status_code == 400, res.text


# ═══════════════════════════════════════════════════════════════════════════
# Designado novo precisa de perfil POP
# ═══════════════════════════════════════════════════════════════════════════


class TestDesignadoNovo:
    def test_novo_sem_perfil_pop_recebe_400(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)
        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P8"})  # P8 = NOVO_SEM_PERFIL
        assert res.status_code == 400, res.text
        assert "P8" in res.json()["detail"]
        assert sb.tables["pops"][0]["revisor_id"] == "P2"

    def test_novo_inexistente_recebe_400(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)
        res = client.patch("/api/pops/pop-1", json={"validador_id": "ZZ"})
        assert res.status_code == 400, res.text
        assert sb.tables["pops"][0]["validador_id"] == "P3"

    def test_pop_inexistente_recebe_404(self):
        sb = _sb(versao=_versao(estado="A_ELABORAR"))
        client = _client_para(GESTOR_QUALIDADE, sb)
        res = client.patch("/api/pops/nao-existe", json={"revisor_id": "P9"})
        assert res.status_code == 404, res.text


# ═══════════════════════════════════════════════════════════════════════════
# Notificação à pessoa nova da etapa ativa
# ═══════════════════════════════════════════════════════════════════════════


class TestNotificacaoEtapaAtiva:
    def test_troca_de_elaborador_na_elaboracao_notifica_o_novo(self, emails_enviados):
        sb = _sb(versao=_versao(estado="EM_ELABORACAO"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"elaborador_id": "P9"})

        assert res.status_code == 200, res.text
        assert len(emails_enviados) == 1
        assert emails_enviados[0]["destinatario"] == "p9@hsm.com"  # novo Elaborador
        assert "HSM_CTI-001" in emails_enviados[0]["assunto"] or "HSM_CTI-001" in emails_enviados[0]["html"]

    def test_troca_de_revisor_na_revisao_notifica_o_novo(self, emails_enviados):
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P9"})

        assert res.status_code == 200, res.text
        assert len(emails_enviados) == 1
        assert emails_enviados[0]["destinatario"] == "p9@hsm.com"  # novo Revisor

    def test_troca_de_validador_na_validacao_notifica_o_novo(self, emails_enviados):
        sb = _sb(versao=_versao(estado="EM_VALIDACAO"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"validador_id": "P9"})

        assert res.status_code == 200, res.text
        assert len(emails_enviados) == 1
        assert emails_enviados[0]["destinatario"] == "p9@hsm.com"  # novo Validador

    def test_trocar_papel_inativo_na_etapa_nao_notifica(self, emails_enviados):
        # Estado EM_REVISAO: a etapa ativa é a Revisão. Trocar o Validador
        # (etapa futura) não notifica ninguém agora.
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"validador_id": "P9"})

        assert res.status_code == 200, res.text
        assert emails_enviados == []

    def test_manter_a_mesma_pessoa_nao_notifica(self, emails_enviados):
        # PATCH com o mesmo revisor atual na etapa de Revisão: sem troca, sem email.
        sb = _sb(versao=_versao(estado="EM_REVISAO"))
        client = _client_para(GESTOR_QUALIDADE, sb)

        res = client.patch("/api/pops/pop-1", json={"revisor_id": "P2"})

        assert res.status_code == 200, res.text
        assert emails_enviados == []
