"""Triagem de e-mail: virar manifestação, com acuse ao remetente (issue #650,
PRD #646, ADR 0051 decisões 2 e 3).

Virar manifestação não é um segundo caminho de criação: é o registro manual que
já existe, aberto com os valores do e-mail (a pré-carga) e salvo com o
identificador do e-mail de origem. O caso nasce pelas regras de sempre, os
anexos do e-mail passam a ser anexos do caso, o item sai dos pendentes ligado
ao caso, e o acuse de recebimento sai pelo caminho do ADR 0042.

O acuse é do CASO, não do canal (ADR 0042, issue #493): o telefone continua
como hoje, com acuse quando há e-mail utilizável no contato. A triagem da issue
(28/09/2026) tirou daqui o critério "telefone sem acuse", que descrevia o mundo
anterior ao ADR 0042.

Seams: o webhook põe o e-mail na triagem (como na fundação, #648), e as rotas
da triagem e do registro manual fazem o resto. Os dublês são os da fundação,
com o que esta fatia acrescenta: `delete` e os defaults que o Postgres põe na
linha do caso (número e protocolo).
"""

from __future__ import annotations

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_triagem_email import (  # noqa: E402
    OUVIDOR,
    PDF,
    SECRETARIA,
    SEGREDO,
    SUPER_ADMIN,
    _entregar,
    _evento,
    _lido,
    _ResendFake,
    _SupabaseFake,
    _TabelaFake,
)

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_triagem_email as triagem_router  # noqa: E402
from app.routers import webhooks as webhooks_router  # noqa: E402
from app.services import email_service, ouvidoria_notificacoes  # noqa: E402

CHEGADA = "2026-09-10T14:02:10.000Z"


class _TabelaDaFatia(_TabelaFake):
    """A tabela da fundação, mais o `delete` (o anexo que sai do item) e o que
    o Postgres preenche sozinho na linha do caso."""

    def __init__(self, dono, nome):
        super().__init__(dono, nome)
        self._delete = False

    def delete(self):
        self._delete = True
        return self

    def limit(self, quantidade: int):
        # O despacho do acuse lê o caso com `.limit(1)`.
        return self.range(0, quantidade - 1)

    def execute(self):
        if self._delete:
            self.dono.consultas.append(self.nome)
            casadas = [r for r in self.rows if self._casa(r)]
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        if self._insert is not None and self.nome == "ouvidoria_protocolos":
            numero = 7 + len(self.rows)
            self._insert = {
                "numero": numero,
                "protocolo": f"2026-{numero:04d}",
                "prazo_resposta": "2026-09-17",
                "status": "em_classificacao",
            } | self._insert
        return super().execute()


class _BancoDaFatia(_SupabaseFake):
    def __init__(self):
        super().__init__()
        self.tabelas |= {
            "ouvidoria_protocolos": [],
            "ouvidoria_anexos": [],
            "ouvidoria_movimentos": [],
            "ouvidoria_notificacoes": [],
            "setores": [{"nome": "Recepção", "ativo": True}],
        }

    def table(self, nome: str):
        return _TabelaDaFatia(self, nome)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _segredo_configurado(monkeypatch):
    monkeypatch.setattr(settings, "resend_webhook_secret", SEGREDO)
    monkeypatch.setattr(settings, "ouvidoria_dominio_interno", "hospitalsaomatheus.com.br")


@pytest.fixture
def emails(monkeypatch) -> list[tuple]:
    """Toda saída de e-mail do módulo passa por `_enviar_email`: nada encosta
    em provedor de verdade."""
    enviados: list[tuple] = []

    def _fake(destinatario, assunto, html, texto=None, **_kwargs):
        enviados.append((destinatario, assunto, html, texto))
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _client(monkeypatch, participante: dict | None = OUVIDOR):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(webhooks_router.router, prefix="/api")
    app.include_router(triagem_router.router, prefix="/api")
    app.include_router(ouvidoria_router.router, prefix="/api")

    banco = _BancoDaFatia()
    resend = _ResendFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(email_service, "ler_email_recebido", resend)
    monkeypatch.setattr(email_service, "baixar_anexo_recebido", resend.baixar)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco, resend


def _email_na_triagem(monkeypatch, participante: dict | None = OUVIDOR, *, lido=None, evento=None):
    """Um e-mail chega pelo webhook e fica pendente na triagem. Devolve o
    cliente, o banco e o id do item."""
    cliente, banco, resend = _client(monkeypatch, participante)
    evento = evento or _evento()
    resend.respostas[evento["data"]["email_id"]] = lido or _lido()
    assert _entregar(cliente, evento).status_code == 200
    return cliente, banco, banco.tabelas["ouvidoria_emails_recebidos"][0]["id"]


# ─── A pré-carga ─────────────────────────────────────────────────────────────


class TestAPreCarga:
    def test_pre_carga_devolve_os_valores_do_email_para_o_registro_manual(self, monkeypatch):
        cliente, _, email_id = _email_na_triagem(monkeypatch)

        r = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga")

        assert r.status_code == 200
        corpo = r.json()
        assert corpo["canal"] == "email"
        # A data de chegada do e-mail, e não a do clique (ADR 0051, decisão 2).
        assert corpo["contato_em"] == CHEGADA
        assert corpo["manifestante_nome"] == "Joana da Silva"
        assert corpo["manifestante_contato"] == "joana.silva@gmail.com"
        assert corpo["resumo"] == ""
        assert corpo["relato_integral"] == "Esperei três horas na recepção sem informação nenhuma."
        assert [a["filename"] for a in corpo["anexos"]] == ["laudo.pdf"]


# ─── Virar manifestação ──────────────────────────────────────────────────────


def _o_ouvidor_salva(pre_carga: dict, **alteracoes) -> dict:
    """O modal aberto com a pré-carga, com o que o ouvidor completa (tipo,
    setor, resumo) e o que ele quiser trocar."""
    corpo = {campo: valor for campo, valor in pre_carga.items() if campo != "anexos"}
    corpo |= {"tipo_manifestacao": "reclamacao", "setor": "Recepção", "resumo": "Espera longa na recepção."}
    return corpo | alteracoes


def _virar(cliente, email_id: str, **alteracoes):
    pre_carga = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").json()
    return cliente.post("/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga, **alteracoes))


class TestVirarManifestacao:
    def test_virar_manifestacao_cria_o_caso_com_os_dados_do_email(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        r = _virar(cliente, email_id)

        assert r.status_code == 201
        [caso] = banco.tabelas["ouvidoria_protocolos"]
        assert caso["canal"] == "email"
        assert caso["contato_em"] == "2026-09-10T14:02:10+00:00"
        # 14h02 em UTC é 11h02 em Brasília: o mesmo dia.
        assert caso["data_abertura"] == "2026-09-10"
        assert caso["manifestante_nome"] == "Joana da Silva"
        assert caso["manifestante_contato"] == "joana.silva@gmail.com"
        assert caso["relato_integral"] == "Esperei três horas na recepção sem informação nenhuma."
        assert r.json()["protocolo"] == caso["protocolo"]

    def test_o_item_sai_dos_pendentes_ligado_ao_caso(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        r = _virar(cliente, email_id)

        [item] = banco.tabelas["ouvidoria_emails_recebidos"]
        assert item["estado"] == "virou_manifestacao"
        assert item["manifestacao_id"] == r.json()["id"]
        assert item["decidido_por"] == "P10"
        assert item["decidido_por_nome"] == "Marta Ouvidora"
        assert item["decidido_em"] is not None


class TestOsAnexosVaoParaOCaso:
    def test_os_anexos_do_email_aparecem_no_caso_e_somem_do_item(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        caso_id = _virar(cliente, email_id).json()["id"]

        anexos_do_caso = cliente.get(f"/api/ouvidoria/manifestacoes/{caso_id}/anexos").json()["anexos"]
        assert [a["filename"] for a in anexos_do_caso] == ["laudo.pdf"]
        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}").json()["anexos"] == []

    def test_o_anexo_do_caso_abre_o_mesmo_binario_por_url_assinada(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        caso_id = _virar(cliente, email_id).json()["id"]
        [anexo] = cliente.get(f"/api/ouvidoria/manifestacoes/{caso_id}/anexos").json()["anexos"]

        r = cliente.get(f"/api/ouvidoria/manifestacoes/{caso_id}/anexos/{anexo['id']}/url")

        assert r.status_code == 200
        [assinada] = banco.storage.assinaturas
        assert banco.storage.arquivos[assinada["path"]] == PDF


class TestOAcuseVaiParaQuemEscreveu:
    def test_o_acuse_fica_registrado_para_o_endereco_do_remetente(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        r = _virar(cliente, email_id)

        [notificacao] = banco.tabelas["ouvidoria_notificacoes"]
        assert notificacao["gatilho"] == ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO
        assert notificacao["destinatario_email"] == "joana.silva@gmail.com"
        assert notificacao["manifestacao_id"] == r.json()["id"]
        # O TestClient roda as tarefas depois da resposta: o e-mail saiu, com o
        # protocolo.
        [(destinatario, _assunto, html, _texto)] = emails
        assert destinatario == "joana.silva@gmail.com"
        assert r.json()["protocolo"] in html


class TestValeOQueOOuvidorSalvou:
    def test_o_ouvidor_troca_os_campos_pre_preenchidos_e_vale_o_que_ele_salvou(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        _virar(
            cliente,
            email_id,
            canal="telefone",
            contato_em="2026-09-09T08:00:00-03:00",
            manifestante_nome="Joana Silva Pereira",
            manifestante_contato="joana.pereira@exemplo.com",
            relato_integral="Relato reescrito pelo ouvidor depois de ligar para a Joana.",
        )

        [caso] = banco.tabelas["ouvidoria_protocolos"]
        assert caso["canal"] == "telefone"
        assert caso["data_abertura"] == "2026-09-09"
        assert caso["manifestante_nome"] == "Joana Silva Pereira"
        assert caso["relato_integral"] == "Relato reescrito pelo ouvidor depois de ligar para a Joana."
        # O acuse segue o contato SALVO, e não o remetente do e-mail.
        [notificacao] = banco.tabelas["ouvidoria_notificacoes"]
        assert notificacao["destinatario_email"] == "joana.pereira@exemplo.com"

    def test_anonimo_marcado_no_modal_nao_grava_o_remetente_nem_manda_acuse(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        _virar(cliente, email_id, anonimo=True)

        [caso] = banco.tabelas["ouvidoria_protocolos"]
        assert caso["manifestante_contato"] is None
        assert caso["acuse_sem_contato_em"] is not None
        assert banco.tabelas["ouvidoria_notificacoes"] == []
        assert emails == []


class TestEmailJaDecididoNaoViraCasoDeNovo:
    def test_virar_de_novo_recebe_409_e_nao_cria_segundo_caso(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        pre_carga = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").json()
        assert cliente.post("/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga)).status_code == 201

        # O segundo clique, com o modal ainda aberto na outra aba.
        r = cliente.post("/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga))

        assert r.status_code == 409
        assert len(banco.tabelas["ouvidoria_protocolos"]) == 1
        assert len(banco.tabelas["ouvidoria_notificacoes"]) == 1

    @pytest.mark.parametrize("estado", ["descartado", "juntado"])
    def test_item_decidido_por_outra_acao_tambem_recusa(self, monkeypatch, emails, estado):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        pre_carga = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").json()
        banco.tabelas["ouvidoria_emails_recebidos"][0] |= {"estado": estado, "decidido_em": "2026-09-11T10:00:00"}

        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").status_code == 409
        assert cliente.post("/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga)).status_code == 409
        assert banco.tabelas["ouvidoria_protocolos"] == []

    def test_email_inexistente_recebe_404_e_nao_cria_caso(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)
        pre_carga = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").json()

        r = cliente.post(
            "/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga, email_recebido_id="nao-existe")
        )

        assert r.status_code == 404
        assert banco.tabelas["ouvidoria_protocolos"] == []


class TestSoAOuvidoriaViraManifestacao:
    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_perfil_sem_ouvidoria_recebe_403_e_o_item_fica_pendente(self, monkeypatch, emails, participante):
        cliente, banco, email_id = _email_na_triagem(monkeypatch, participante)
        corpo = {
            "email_recebido_id": email_id,
            "canal": "email",
            "contato_em": CHEGADA,
            "tipo_manifestacao": "reclamacao",
            "setor": "Recepção",
            "resumo": "Espera longa.",
            "relato_integral": "Esperei três horas.",
        }

        assert cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").status_code == 403
        assert cliente.post("/api/ouvidoria/manifestacoes", json=corpo).status_code == 403
        assert banco.tabelas["ouvidoria_protocolos"] == []
        assert banco.tabelas["ouvidoria_emails_recebidos"][0]["estado"] == "pendente"


class TestOGestoEntraNoLogDeAcesso:
    def test_virar_manifestacao_grava_o_acesso_com_o_item_e_o_caso(self, monkeypatch, emails):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        caso_id = _virar(cliente, email_id).json()["id"]

        [acesso] = [a for a in banco.tabelas["ouvidoria_acessos"] if a["acao"] == "virar_manifestacao"]
        assert acesso["email_recebido_id"] == email_id
        assert acesso["manifestacao_id"] == caso_id
        assert acesso["ator_id"] == "P10"
        assert acesso["ator_nome"] == "Marta Ouvidora"

    def test_abrir_a_pre_carga_tambem_entra_no_log(self, monkeypatch):
        cliente, banco, email_id = _email_na_triagem(monkeypatch)

        cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga")

        [acesso] = banco.tabelas["ouvidoria_acessos"]
        assert acesso["email_recebido_id"] == email_id
        assert acesso["acao"] == "pre_carga_manifestacao"


TRAVESSOES = ("\u2014", "\u2013")


class TestSemTravessaoNoQueOHumanoLe:
    def test_nem_a_pre_carga_nem_o_caso_nem_o_acuse_tem_travessao(self, monkeypatch, emails):
        lido = _lido(texto="Esperei três horas \u2014 sem informação \u2013 nenhuma.", html=None)
        evento = _evento(remetente="Joana \u2014 da Silva <joana.silva@gmail.com>")
        cliente, banco, email_id = _email_na_triagem(monkeypatch, lido=lido, evento=evento)

        pre_carga = cliente.get(f"/api/ouvidoria/triagem-email/{email_id}/pre-carga").json()
        cliente.post("/api/ouvidoria/manifestacoes", json=_o_ouvidor_salva(pre_carga))

        [caso] = banco.tabelas["ouvidoria_protocolos"]
        [(_destinatario, assunto, html, texto)] = emails
        lidos_por_gente = [
            pre_carga["relato_integral"],
            pre_carga["manifestante_nome"],
            caso["relato_integral"],
            caso["manifestante_nome"],
            assunto,
            html,
            texto or "",
        ]
        for lido_por_gente in lidos_por_gente:
            assert not any(t in lido_por_gente for t in TRAVESSOES), lido_por_gente
        # O texto continua o do e-mail, só com a tipografia da casa.
        assert "sem informação" in pre_carga["relato_integral"]
