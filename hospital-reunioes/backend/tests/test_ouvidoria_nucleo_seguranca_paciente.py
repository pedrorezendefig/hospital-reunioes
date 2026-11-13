"""O envio ao Núcleo de Segurança do Paciente (issue #1621, PRD #1527, ADR 0088).

O ouvidor manda ao Núcleo (NSP) o caso que fala de incidente com o paciente, e
o Núcleo confirma o recebimento por um link sem senha. Quando o agente de
triagem aponta o caso, "Validar e acionar" só conclui depois de o ouvidor
confirmar o envio ou descartar com motivo. O link do Núcleo mostra o relato
integral mesmo no caso sigiloso (a única exceção ao sigilo), o email só avisa e
traz o link, e sem o Recebido no prazo a cobrança sobe ao gestor e à Diretoria.
A ciência corre em paralelo: o caso com o selo responde e encerra normalmente.

Os dublês de banco são os da validação (`test_ouvidoria_validacao_acionamento`),
como no elogio: a ciência do Núcleo nasce pela mesma porta do acionamento.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_validacao_acionamento import (  # noqa: E402
    DENTRO_DO_EXPEDIENTE,
    OUVIDOR,
    VALIDACAO,
    _manifestacao,
    _responsavel,
    _SupabaseFake,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402

NUCLEO = "Nucleo de Seguranca do Paciente"
PRESIDENTE = {"nome": "Dra. Helena Presidente", "email": "nsp@hsm.br"}

RELATO = "Minha mae caiu da cama no quarto 412 na madrugada e ninguem veio ajudar por meia hora."
JUSTIFICATIVA_SIMPLES = "O relato descreve uma queda de paciente internado, que e incidente de assistencia."
JUSTIFICATIVA_TECNICA = "Queda do leito, internacao, madrugada de 24/08. Dano relatado: escoriacao no braco."


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def emails(monkeypatch) -> list[dict]:
    """Toda saída de email do módulo passa por `_enviar_email`. Nenhum teste
    deste arquivo encosta no provedor de verdade."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html, texto=None, **_kwargs):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "html": html, "texto": texto})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _caso(**overrides) -> dict:
    """Um caso já com a área, com o relato da queda, o paciente e o quarto."""
    base = {
        "status": "aguardando_area",
        "tipo_manifestacao": "reclamacao",
        "setor": "Recepcao",
        "gravidade": "medio",
        "relato_integral": RELATO,
        "extrato_para_o_setor": "Apurar o atendimento da equipe no plantao noturno.",
        "paciente_nome": "Ana Maria Souza",
        "paciente_nascimento": "1948-03-02",
        "profissionais": "Enfermeiro do plantao noturno",
        "quarto": "Leito Girassol",
        "nsp_sugerido": False,
        "nsp_justificativa_simples": None,
        "nsp_justificativa_tecnica": None,
        "nsp_decisao": None,
        "nsp_decisao_motivo": None,
    }
    return _manifestacao(**(base | overrides))


def _banco(caso: dict | None = None) -> _SupabaseFake:
    """O banco com o Núcleo configurado e com titular e gestor cadastrados."""
    supabase = _SupabaseFake(
        [caso if caso is not None else _caso()],
        responsaveis=[
            _responsavel(),
            _responsavel("titular", id="resp-nsp", setor=NUCLEO, **PRESIDENTE),
            _responsavel("gestor", id="resp-nsp-gestor", setor=NUCLEO, nome="Gestor do Nucleo", email="g@hsm.br"),
        ],
    )
    supabase.tabelas["setores"].append({"id": "s2", "nome": NUCLEO, "ativo": True})
    supabase.tabelas["ouvidoria_config"] = [{"id": True, "nsp_setor": NUCLEO}]
    return supabase


def _client(monkeypatch, supabase: _SupabaseFake | None = None, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
    """O painel do ouvidor e o link do email no mesmo app, sobre o mesmo banco."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _banco()

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _enviar_ao_nucleo(client):
    return client.post("/api/ouvidoria/manifestacoes/uuid-7/nsp")


def _ciencias_do_nucleo(supabase: _SupabaseFake) -> list[dict]:
    return [a for a in supabase.tabelas.get("ouvidoria_acionamentos", []) if a.get("motivo_ciencia") == "nsp"]


# =====================================================================
# 1. Enviar ao NSP funciona sem sugestão
# =====================================================================


class TestEnviarAoNucleoSemSugestao:
    def test_enviar_ao_nsp_sem_sugestao_cria_a_ciencia_do_nucleo_e_marca_o_selo(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        r = _enviar_ao_nucleo(client)

        assert r.status_code == 200, r.text
        ciencias = _ciencias_do_nucleo(supabase)
        assert len(ciencias) == 1
        ciencia = ciencias[0]
        assert ciencia["tipo"] == "ciencia"
        assert ciencia["status"] == "pendente"
        assert ciencia["setor"] == NUCLEO
        assert ciencia["responsavel_email"] == "nsp@hsm.br"
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["nsp_decisao"] == "confirmado"
        assert caso["nsp_decidido_por"] == OUVIDOR["id"]
        assert r.json()["selo"] == "Em análise pelo NSP"


class _BancoComAFalhaNaDecisao(_SupabaseFake):
    """O banco de verdade no que o envio pela metade precisa: o índice único da
    migration 139 recusa a segunda ciência do Núcleo do caso (23505), e o
    update que grava a decisão estoura uma vez, como o PostgREST em timeout."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.falhas_da_decisao = 1

    def table(self, nome: str):
        from postgrest.exceptions import APIError

        tabela = super().table(nome)
        if nome == "ouvidoria_acionamentos":
            insert_original = tabela.insert

            def _insert(payload):
                ja_tem = any(
                    a.get("motivo_ciencia") == "nsp" and a.get("manifestacao_id") == payload.get("manifestacao_id")
                    for a in tabela.rows
                )
                if payload.get("motivo_ciencia") == "nsp" and ja_tem:
                    raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
                return insert_original(payload)

            tabela.insert = _insert
        if nome == "ouvidoria_protocolos":
            update_original = tabela.update

            def _update(payload: dict):
                if "nsp_decisao" in payload and self.falhas_da_decisao:
                    self.falhas_da_decisao -= 1
                    raise APIError({"code": "57014", "message": "canceling statement due to statement timeout"})
                return update_original(payload)

            tabela.update = _update
        return tabela


class TestOEnvioQueFicouPelaMetade:
    def test_a_nova_tentativa_completa_o_envio_que_falhou_na_decisao(self, monkeypatch, emails):
        """A ciência gravou e a decisão não: o ouvidor tenta de novo e o envio
        termina, com a decisão, a trilha e o email ao Núcleo. Sem isso o caso
        respondia "já foi enviado" para sempre e o Núcleo nunca recebia o link."""
        supabase = _BancoComAFalhaNaDecisao([_caso()], responsaveis=_banco().tabelas["ouvidoria_setor_responsaveis"])
        supabase.tabelas["setores"].append({"id": "s2", "nome": NUCLEO, "ativo": True})
        supabase.tabelas["ouvidoria_config"] = [{"id": True, "nsp_setor": NUCLEO}]
        client, supabase = _client(monkeypatch, supabase)

        primeira = _enviar_ao_nucleo(client)
        assert primeira.status_code == 500
        assert emails == []

        segunda = _enviar_ao_nucleo(client)

        assert segunda.status_code == 200, segunda.text
        assert len(_ciencias_do_nucleo(supabase)) == 1
        assert supabase.tabelas["ouvidoria_protocolos"][0]["nsp_decisao"] == "confirmado"
        assert [e["destinatario"] for e in emails] == ["nsp@hsm.br"]
        trilha = [m["observacao"] for m in supabase.tabelas["ouvidoria_movimentos"]]
        assert sum("Enviado ao Núcleo" in (o or "") for o in trilha) == 1


# =====================================================================
# 2. Com sugestão, a validação só conclui depois da decisão sobre o Núcleo
# =====================================================================


def _caso_apontado(**overrides) -> dict:
    """O caso que o agente de triagem apontou ao Núcleo, ainda em classificação."""
    return _caso(
        status="em_classificacao",
        setor="A definir",
        gravidade=None,
        nsp_sugerido=True,
        nsp_justificativa_simples=JUSTIFICATIVA_SIMPLES,
        nsp_justificativa_tecnica=JUSTIFICATIVA_TECNICA,
        **overrides,
    )


def _validar(client, **corpo):
    return client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO | corpo)


class TestDecisaoSobreONucleoNaValidacao:
    def test_com_sugestao_validar_sem_decidir_sobre_o_nucleo_e_recusado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client)

        assert r.status_code == 422, r.text
        assert "Núcleo de Segurança do Paciente" in r.json()["detail"]
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "em_classificacao", "a recusa vem antes de qualquer efeito"
        assert supabase.tabelas["ouvidoria_notificacoes"] == []
        assert emails == []

    def test_descartar_sem_motivo_e_recusado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="descartado", nsp_motivo="   ")

        assert r.status_code == 422, r.text
        assert "motivo" in r.json()["detail"]
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "em_classificacao"
        assert caso["nsp_decisao"] is None
        assert emails == []

    def test_descartar_com_motivo_grava_a_decisao_e_aciona_a_area(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="descartado", nsp_motivo="Queda sem dano, ja notificada pela enfermagem.")

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["nsp_decisao"] == "descartado"
        assert caso["nsp_decisao_motivo"] == "Queda sem dano, ja notificada pela enfermagem."
        assert caso["nsp_decidido_por"] == OUVIDOR["id"]
        assert _ciencias_do_nucleo(supabase) == []
        assert [e["destinatario"] for e in emails] == ["carlos@hsm.br"]

    def test_confirmar_na_validacao_envia_ao_nucleo_e_aciona_a_area(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))

        r = _validar(client, nsp_decisao="confirmado")

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["nsp_decisao"] == "confirmado"
        ciencias = _ciencias_do_nucleo(supabase)
        assert len(ciencias) == 1
        assert ciencias[0]["status"] == "pendente", "o acionamento da área não derruba a ciência do Núcleo"
        assert sorted(e["destinatario"] for e in emails) == ["carlos@hsm.br", "nsp@hsm.br"]

    def test_a_decisao_ja_tomada_nao_e_pedida_de_novo(self, monkeypatch):
        """O caso devolvido à Ouvidoria volta à validação: a decisão sobre o
        Núcleo já foi tomada e não trava o reacionamento."""
        client, _supabase = _client(monkeypatch, _banco(_caso_apontado(nsp_decisao="descartado")))

        r = _validar(client)

        assert r.status_code == 200, r.text


# =====================================================================
# 3. O email ao Núcleo só avisa e traz o link
# =====================================================================


def _email_do_nucleo(emails: list[dict]) -> dict:
    do_nucleo = [e for e in emails if e["destinatario"] == "nsp@hsm.br"]
    assert len(do_nucleo) == 1, "o Núcleo recebe um email"
    return do_nucleo[0]


def _token_do_nucleo(email: dict) -> str:
    achado = re.search(r"/ouvidoria-setor/nsp/([A-Za-z0-9_-]{20,})", email["html"])
    assert achado, "o email do Núcleo perdeu o link"
    assert f"/ouvidoria-setor/nsp/{achado.group(1)}" in email["texto"]
    return achado.group(1)


class TestOEmailAoNucleo:
    def test_o_email_ao_nucleo_nao_leva_relato_nem_justificativa(self, monkeypatch, emails):
        caso = _caso(
            nsp_sugerido=True,
            nsp_justificativa_simples=JUSTIFICATIVA_SIMPLES,
            nsp_justificativa_tecnica=JUSTIFICATIVA_TECNICA,
        )
        client, _supabase = _client(monkeypatch, _banco(caso))

        assert _enviar_ao_nucleo(client).status_code == 200

        email = _email_do_nucleo(emails)
        _token_do_nucleo(email)
        assert "2026-0007" in email["assunto"]
        for corpo in (email["html"], email["texto"]):
            assert "Protocolo 2026-0007" in corpo
            assert RELATO not in corpo
            assert JUSTIFICATIVA_TECNICA not in corpo
            assert JUSTIFICATIVA_SIMPLES not in corpo
            assert "Ana Maria Souza" not in corpo
            assert "Leito Girassol" not in corpo


# =====================================================================
# 4. O link do Núcleo mostra o relato integral, mesmo no caso sigiloso
# =====================================================================


def _abrir_o_link_do_nucleo(client, token: str):
    return client.get(f"/api/ouvidoria-setor/nsp/{token}")


class TestOLinkDoNucleo:
    def test_o_link_do_nucleo_de_um_caso_sigiloso_mostra_o_relato_e_nao_quem_manifestou(self, monkeypatch, emails):
        caso = _caso(
            tipo_manifestacao="denuncia",
            sigilo_reforcado=True,
            nsp_justificativa_tecnica=JUSTIFICATIVA_TECNICA,
        )
        client, _supabase = _client(monkeypatch, _banco(caso))
        assert _enviar_ao_nucleo(client).status_code == 200
        client.app.dependency_overrides.pop(get_current_user)

        r = _abrir_o_link_do_nucleo(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert r.status_code == 200, r.text
        tela = r.json()
        assert tela["protocolo"] == "2026-0007"
        assert tela["relato_integral"] == RELATO
        assert tela["justificativa_tecnica"] == JUSTIFICATIVA_TECNICA
        assert tela["paciente"] == {"nome": "Ana Maria Souza", "nascimento": "1948-03-02"}
        assert tela["profissionais"] == "Enfermeiro do plantao noturno"
        assert tela["quarto"] == "Leito Girassol"
        assert tela["quem_manifestou"] is None
        assert "Joana da Silva" not in r.text

    def test_o_link_de_outra_area_no_mesmo_caso_sigiloso_continua_so_com_a_nota(self, monkeypatch, emails):
        caso = _caso_apontado(tipo_manifestacao="denuncia", sigilo_reforcado=True)
        client, _supabase = _client(monkeypatch, _banco(caso))
        r = _validar(client, tipo_manifestacao="denuncia", nsp_decisao="confirmado")
        assert r.status_code == 200, r.text
        client.app.dependency_overrides.pop(get_current_user)

        email_da_area = next(e for e in emails if e["destinatario"] == "carlos@hsm.br")
        token_da_area = re.search(r"/ouvidoria-setor/([A-Za-z0-9_-]{20,})", email_da_area["html"]).group(1)
        da_area = client.get(f"/api/ouvidoria-setor/{token_da_area}")
        do_nucleo = _abrir_o_link_do_nucleo(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert da_area.status_code == 200, da_area.text
        assert [b["chave"] for b in da_area.json()["blocos"]] == ["nota_da_ouvidoria"]
        assert RELATO not in da_area.text
        assert do_nucleo.json()["relato_integral"] == RELATO

    def test_o_caso_comum_identificado_mostra_quem_manifestou(self, monkeypatch, emails):
        client, _supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200

        r = _abrir_o_link_do_nucleo(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert r.json()["quem_manifestou"] == "Joana da Silva"

    def test_o_caso_anonimo_nao_mostra_quem_manifestou(self, monkeypatch, emails):
        client, _supabase = _client(monkeypatch, _banco(_caso(anonimo=True)))
        assert _enviar_ao_nucleo(client).status_code == 200

        r = _abrir_o_link_do_nucleo(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert r.json()["quem_manifestou"] is None
        assert r.json()["relato_integral"] == RELATO

    def test_o_link_de_um_elogio_nao_abre_a_tela_do_nucleo(self, monkeypatch, emails):
        """O token de outra ciência do registro não pode abrir o relato
        integral: a tela do Núcleo só aceita a ciência do Núcleo."""
        caso = _caso(status="em_classificacao", setor="A definir", gravidade=None, tipo_manifestacao=None)
        client, _supabase = _client(monkeypatch, _banco(caso))
        r = _validar(client, tipo_manifestacao="elogio", gravidade="baixo")
        assert r.status_code == 200, r.text
        token_do_elogio = re.search(r"/ouvidoria-setor/elogio/([A-Za-z0-9_-]+)", emails[0]["html"]).group(1)

        assert _abrir_o_link_do_nucleo(client, token_do_elogio).status_code == 404

    def test_link_que_nao_existe_e_recusado(self, monkeypatch):
        client, _supabase = _client(monkeypatch)

        assert _abrir_o_link_do_nucleo(client, "x" * 43).status_code == 404


# =====================================================================
# 5. Recebido pelo NSP funciona sem login e uma vez só
# =====================================================================


def _recebido(client, token: str):
    return client.post(f"/api/ouvidoria-setor/nsp/{token}/recebido")


class TestRecebidoPeloNucleo:
    def test_recebido_pelo_nsp_funciona_sem_login(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200
        client.app.dependency_overrides.pop(get_current_user)

        r = _recebido(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert r.status_code == 200, r.text
        assert r.json()["protocolo"] == "2026-0007"
        ciencia = _ciencias_do_nucleo(supabase)[0]
        assert ciencia["status"] == "ciente"
        assert ciencia["respondido_em"] == DENTRO_DO_EXPEDIENTE.isoformat()
        trilha = [m["observacao"] for m in supabase.tabelas["ouvidoria_movimentos"]]
        assert any(o.startswith("Recebido pelo NSP: Dra. Helena Presidente") for o in trilha), trilha

    def test_recebido_pelo_nsp_vale_uma_vez_so(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200
        token = _token_do_nucleo(_email_do_nucleo(emails))

        primeiro = _recebido(client, token)
        segundo = _recebido(client, token)

        assert primeiro.status_code == 200, primeiro.text
        assert segundo.status_code == 410
        assert segundo.json()["detail"] == "O Núcleo já confirmou o recebimento deste caso."
        recebidos = [m for m in supabase.tabelas["ouvidoria_movimentos"] if "Recebido pelo NSP" in m["observacao"]]
        assert len(recebidos) == 1

    def test_o_recebido_nao_mexe_no_estado_do_caso(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200

        _recebido(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "aguardando_area"

    def test_depois_do_recebido_o_link_ainda_mostra_o_caso_com_a_marca(self, monkeypatch, emails):
        client, _supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200
        token = _token_do_nucleo(_email_do_nucleo(emails))
        _recebido(client, token)

        tela = _abrir_o_link_do_nucleo(client, token).json()

        assert tela["recebido"] is True
        assert tela["recebido_em"] == DENTRO_DO_EXPEDIENTE.isoformat()

    def test_o_link_do_nucleo_nao_confirma_elogio(self, monkeypatch, emails):
        """O botão do elogio devolve o caso ao ouvidor como Pronto para
        encerrar: o token do Núcleo não pode passar por ali."""
        client, supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200

        r = client.post(f"/api/ouvidoria-setor/elogio/{_token_do_nucleo(_email_do_nucleo(emails))}/recebido")

        assert r.status_code == 404
        assert _ciencias_do_nucleo(supabase)[0]["status"] == "pendente"


# =====================================================================
# 6. Sem Recebido no prazo, a cobrança sobe ao gestor e à Diretoria
# =====================================================================

# O caso médio enviado na terça 14h tem o Recebido até o fim do dia útil
# seguinte: quarta, 17h de Brasília. A escada é a da área: +24h úteis o gestor
# (quinta 17h), +48h úteis a Diretoria (sexta 17h). Os instantes da cobrança
# são a manhã seguinte a cada degrau, dentro do expediente: às 17h05 o email
# já espera a próxima abertura, pela janela comercial.
PRAZO_DO_RECEBIDO = dt.datetime(2026, 8, 26, 20, 0, tzinfo=dt.UTC)
DEPOIS_DO_PRAZO = dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.UTC)  # quinta, 9h
UM_DIA_UTIL_DEPOIS = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.UTC)  # sexta, 9h
DOIS_DIAS_UTEIS_DEPOIS = dt.datetime(2026, 8, 31, 12, 0, tzinfo=dt.UTC)  # segunda, 9h


def _com_a_diretoria(supabase: _SupabaseFake) -> _SupabaseFake:
    for participante in supabase.tabelas["participantes"]:
        if participante["id"] == "P11":
            participante["perfil_ouvidoria"] = "diretoria_executiva"
    return supabase


def _cobrar(supabase, agora: dt.datetime) -> int:
    from app.services import ouvidoria_nucleo

    return ouvidoria_nucleo.cobrar_o_recebido(supabase, agora, frozenset())


def _destinatarios(emails: list[dict]) -> list[str]:
    return [e["destinatario"] for e in emails]


class TestCobrancaDoRecebido:
    def _enviado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _com_a_diretoria(_banco()))
        assert _enviar_ao_nucleo(client).status_code == 200
        emails.clear()
        return client, supabase

    def test_o_prazo_do_recebido_e_de_um_dia_util(self, monkeypatch, emails):
        _client_, supabase = self._enviado(monkeypatch, emails)

        assert _ciencias_do_nucleo(supabase)[0]["prazo"] == PRAZO_DO_RECEBIDO.isoformat()

    def test_caso_critico_tem_o_recebido_pedido_na_hora(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _banco(_caso(gravidade="critico")))
        assert _enviar_ao_nucleo(client).status_code == 200

        assert _ciencias_do_nucleo(supabase)[0]["prazo"] == DENTRO_DO_EXPEDIENTE.isoformat()

    def test_logo_depois_do_prazo_ninguem_e_cobrado_ainda(self, monkeypatch, emails):
        _client_, supabase = self._enviado(monkeypatch, emails)

        assert _cobrar(supabase, DEPOIS_DO_PRAZO) == 0
        assert emails == []

    def test_sem_recebido_a_cobranca_sobe_ao_gestor_e_depois_a_diretoria_executiva(self, monkeypatch, emails):
        _client_, supabase = self._enviado(monkeypatch, emails)

        assert _cobrar(supabase, UM_DIA_UTIL_DEPOIS) == 1
        assert _destinatarios(emails) == ["g@hsm.br"]

        assert _cobrar(supabase, DOIS_DIAS_UTEIS_DEPOIS) == 1
        assert _destinatarios(emails) == ["g@hsm.br", "diretor@hsm.br"]

    def test_cada_degrau_sobe_uma_vez_so(self, monkeypatch, emails):
        _client_, supabase = self._enviado(monkeypatch, emails)

        _cobrar(supabase, DOIS_DIAS_UTEIS_DEPOIS)
        _cobrar(supabase, DOIS_DIAS_UTEIS_DEPOIS)

        assert sorted(_destinatarios(emails)) == ["diretor@hsm.br", "g@hsm.br"]

    def test_a_cobranca_nao_leva_o_relato(self, monkeypatch, emails):
        _client_, supabase = self._enviado(monkeypatch, emails)

        _cobrar(supabase, DOIS_DIAS_UTEIS_DEPOIS)

        for email in emails:
            assert "2026-0007" in email["assunto"]
            assert "Recebido pelo NSP" in email["texto"]
            assert RELATO not in email["html"] and RELATO not in email["texto"]

    def test_com_o_recebido_ninguem_e_cobrado(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch, _com_a_diretoria(_banco()))
        assert _enviar_ao_nucleo(client).status_code == 200
        assert _recebido(client, _token_do_nucleo(_email_do_nucleo(emails))).status_code == 200
        emails.clear()

        assert _cobrar(supabase, DOIS_DIAS_UTEIS_DEPOIS) == 0
        assert emails == []

    def test_setor_do_nucleo_sem_gestor_leva_o_degrau_a_diretoria(self, monkeypatch, emails):
        supabase = _com_a_diretoria(_banco())
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [
            r for r in supabase.tabelas["ouvidoria_setor_responsaveis"] if r["papel"] != "gestor"
        ]
        client, supabase = _client(monkeypatch, supabase)
        assert _enviar_ao_nucleo(client).status_code == 200
        emails.clear()

        _cobrar(supabase, UM_DIA_UTIL_DEPOIS)

        assert _destinatarios(emails) == ["diretor@hsm.br"]

    def test_a_cobranca_do_nucleo_roda_mesmo_quando_a_escada_da_area_falha(self, monkeypatch):
        """O degrau não depende de alguém lembrar: o job do escalonamento da
        Ouvidoria chama a cobrança do Núcleo, e a falha da escada da área
        naquela rodada não pula a cobrança do Núcleo."""
        from app.cron import scheduler
        from app.services import ouvidoria_escalonamento, ouvidoria_nucleo

        def _escada_quebrada(*_a, **_kw):
            raise RuntimeError("PostgREST fora do ar")

        cobrancas: list[object] = []
        banco = object()
        monkeypatch.setattr(scheduler, "_supabase", lambda: banco)
        monkeypatch.setattr(ouvidoria_router, "carregar_feriados", lambda _sb: frozenset())
        monkeypatch.setattr(ouvidoria_escalonamento, "escalar_prazos", _escada_quebrada)
        monkeypatch.setattr(ouvidoria_nucleo, "cobrar_o_recebido", lambda sb, *_a: cobrancas.append(sb) or 0)

        scheduler.escalonar_prazos_ouvidoria()

        assert cobrancas == [banco]


# =====================================================================
# 7. O caso com o selo responde e encerra normalmente
# =====================================================================


class TestOCasoComOSelo:
    def test_o_caso_com_selo_responde_e_encerra_normalmente(self, monkeypatch, emails):
        """A ciência do Núcleo corre em paralelo (ADR 0088, decisão 8): sem o
        Recebido, a área responde e o ouvidor encerra, e a ciência continua
        esperando o Núcleo."""
        client, supabase = _client(monkeypatch, _banco(_caso_apontado()))
        assert _validar(client, nsp_decisao="confirmado").status_code == 200
        email_da_area = next(e for e in emails if e["destinatario"] == "carlos@hsm.br")
        token_da_area = re.search(r"/ouvidoria-setor/([A-Za-z0-9_-]{20,})", email_da_area["html"]).group(1)

        respondeu = client.post(
            f"/api/ouvidoria-setor/{token_da_area}/responder",
            data={"resposta": "A equipe de enfermagem reviu o protocolo de quedas do 4o andar."},
        )
        encerrou = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={
                "estado": "encerrado",
                "desfecho": "procedente",
                "desfecho_descricao": "A area reviu o protocolo e o caso segue em analise pelo Nucleo.",
            },
        )

        assert respondeu.status_code == 200, respondeu.text
        assert encerrou.status_code == 200, encerrou.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "encerrado"
        assert caso["nsp_decisao"] == "confirmado"
        assert _ciencias_do_nucleo(supabase)[0]["status"] == "pendente"

    def test_o_nucleo_confirma_mesmo_com_o_caso_encerrado(self, monkeypatch, emails):
        caso = _caso(status="encerrado")
        client, supabase = _client(monkeypatch, _banco(caso))
        assert _enviar_ao_nucleo(client).status_code == 200

        r = _recebido(client, _token_do_nucleo(_email_do_nucleo(emails)))

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "encerrado"


# =====================================================================
# O Dossiê mostra o apontamento e a decisão; a configuração diz o setor
# =====================================================================


class TestODossieEAConfiguracao:
    def test_o_dossie_traz_o_alerta_e_a_decisao_sobre_o_nucleo(self, monkeypatch):
        client, _supabase = _client(monkeypatch, _banco(_caso_apontado(nsp_decisao="descartado")))

        dossie = client.get("/api/ouvidoria/manifestacoes/uuid-7").json()

        assert dossie["nsp_sugerido"] is True
        assert dossie["nsp_justificativa_simples"] == JUSTIFICATIVA_SIMPLES
        assert dossie["nsp_decisao"] == "descartado"

    def test_sem_o_setor_do_nucleo_configurado_o_envio_e_recusado(self, monkeypatch, emails):
        supabase = _banco()
        supabase.tabelas["ouvidoria_config"] = [{"id": True, "nsp_setor": ""}]
        client, supabase = _client(monkeypatch, supabase)

        r = _enviar_ao_nucleo(client)

        assert r.status_code == 409
        assert "Responsáveis por setor" in r.json()["detail"]
        assert _ciencias_do_nucleo(supabase) == []
        assert emails == []

    def test_o_caso_ja_enviado_nao_vai_ao_nucleo_de_novo(self, monkeypatch, emails):
        client, supabase = _client(monkeypatch)
        assert _enviar_ao_nucleo(client).status_code == 200

        r = _enviar_ao_nucleo(client)

        assert r.status_code == 409
        assert len(_ciencias_do_nucleo(supabase)) == 1

    def test_o_ouvidor_le_e_escolhe_o_setor_do_nucleo(self, monkeypatch):
        supabase = _banco()
        supabase.tabelas["ouvidoria_config"] = [{"id": True, "nsp_setor": ""}]
        client, supabase = _client(monkeypatch, supabase)

        gravou = client.put("/api/ouvidoria/nucleo", json={"setor": "nucleo de seguranca do paciente"})
        lido = client.get("/api/ouvidoria/nucleo")

        assert gravou.status_code == 200, gravou.text
        assert supabase.tabelas["ouvidoria_config"][0]["nsp_setor"] == NUCLEO, "grava a grafia da taxonomia"
        assert lido.json() == {"setor": NUCLEO}

    def test_setor_fora_da_taxonomia_nao_vira_o_nucleo(self, monkeypatch):
        client, supabase = _client(monkeypatch)

        r = client.put("/api/ouvidoria/nucleo", json={"setor": "Setor que nao existe"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_config"][0]["nsp_setor"] == NUCLEO


class TestAFilaLevaOApontamento:
    """A tela de validação abre também pela fila, como no anônimo da issue
    #769. Sem o apontamento na linha, a tela aberta pela fila não pergunta
    sobre o Núcleo e a validação volta recusada, sem o ouvidor ter onde
    decidir. Só a Ouvidoria recebe as marcas: o caso apontado ao Núcleo é
    incidente com o paciente, e quem está fora dela só acompanha a fila."""

    @pytest.fixture(autouse=True)
    def _sem_a_trilha(self, monkeypatch):
        # O ponto de novidade da fila lê a trilha por uma RPC que o dublê da
        # validação não tem; ele não é o assunto aqui.
        monkeypatch.setattr(ouvidoria_router.ouvidoria_novidade, "ultimo_movimento_ou_degradado", lambda _sb: ({}, []))

    def test_a_ouvidoria_le_o_apontamento_e_a_decisao_na_fila(self, monkeypatch):
        client, _supabase = _client(monkeypatch, _banco(_caso_apontado()))

        linha = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert linha["nsp_sugerido"] is True
        assert linha["nsp_decisao"] is None

    def test_quem_esta_fora_da_ouvidoria_recebe_a_linha_sem_o_apontamento(self, monkeypatch):
        client, _supabase = _client(monkeypatch, _banco(_caso_apontado()))

        async def _secretaria(_user, _sb, fields=None):
            return {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}

        monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _secretaria)

        linha = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert linha["protocolo"] == "2026-0007"
        assert "nsp_sugerido" not in linha
        assert "nsp_decisao" not in linha


# =====================================================================
# 8. O kit de conhecimento diz o comportamento novo
# =====================================================================


class TestOKitDeConhecimento:
    """O Assistente de Tecnologia responde sobre a Ouvidoria pelo kit: se o
    texto não disser como o Núcleo recebe o caso agora, ele responde pelo
    jeito antigo, em que isso ainda "vai" acontecer."""

    @pytest.fixture
    def texto(self) -> str:
        from app.services.conhecimento import CONHECIMENTO_DIR

        return (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")

    @pytest.fixture
    def paragrafo(self, texto) -> str:
        """O parágrafo que conta o envio ao Núcleo, lido sozinho: "sem senha" e
        "prazo" já aparecem em outras frases do texto."""
        achados = [p for p in texto.split("\n\n") if "Recebido pelo NSP" in p]
        assert len(achados) == 1, "o kit precisa de um parágrafo que conte o envio ao Núcleo"
        return achados[0]

    def test_diz_a_decisao_do_ouvidor_quando_o_agente_aponta(self, paragrafo):
        assert "Possível evento de segurança do paciente" in paragrafo
        assert "Confirmar envio ao NSP" in paragrafo
        assert "Descartar" in paragrafo and "motivo" in paragrafo
        assert "Enviar ao NSP" in paragrafo

    def test_diz_o_que_o_link_mostra_e_o_que_o_email_nao_leva(self, paragrafo):
        assert "relato integral" in paragrafo
        assert "mesmo no caso sigiloso" in paragrafo
        assert "só o aviso e o link" in paragrafo

    def test_diz_o_prazo_a_cobranca_e_que_nao_bloqueia(self, paragrafo):
        assert "1 dia útil" in paragrafo
        assert "gestor" in paragrafo and "diretoria executiva" in paragrafo
        assert "não bloqueia a resposta nem o encerramento" in paragrafo
        assert "Em análise pelo NSP" in paragrafo

    def test_a_lista_de_decisoes_fala_do_nucleo_no_presente(self, texto):
        assert "O Núcleo de Segurança do Paciente vai receber" not in texto
        assert "O Núcleo de Segurança do Paciente recebe o relato integral" in texto


# =====================================================================
# A migration: os campos, o índice e os gatilhos no banco
# =====================================================================

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "139_ouvidoria_envio_ao_nucleo.sql"


def _sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestAMigration:
    """O fake do PostgREST não aplica CHECK nem índice, então é a leitura do
    arquivo que segura as regras do banco."""

    @pytest.fixture
    def ddl(self) -> str:
        return _sem_comentarios(MIGRATION.read_text(encoding="utf-8"))

    def test_os_campos_do_caso_e_da_configuracao_sao_reaplicaveis(self, ddl):
        assert "ADD COLUMN IF NOT EXISTS nsp_setor TEXT NOT NULL DEFAULT ''" in ddl
        for coluna in (
            "nsp_sugerido BOOLEAN NOT NULL DEFAULT FALSE",
            "nsp_justificativa_simples TEXT",
            "nsp_justificativa_tecnica TEXT",
            "nsp_decisao TEXT",
            "nsp_decisao_motivo TEXT",
            "nsp_decidido_por VARCHAR(10) REFERENCES participantes(id)",
            "nsp_decidido_em TIMESTAMPTZ",
            "escalonado_gestor_em TIMESTAMPTZ",
            "escalonado_diretoria_em TIMESTAMPTZ",
        ):
            assert f"ADD COLUMN IF NOT EXISTS {coluna}" in ddl, coluna

    def test_a_decisao_e_lista_fechada_e_o_descarte_exige_motivo(self, ddl):
        assert "nsp_decisao IN ('confirmado', 'descartado')" in ddl
        assert "nsp_decisao IS DISTINCT FROM 'descartado' OR length(btrim(coalesce(nsp_decisao_motivo, ''))) > 0" in ddl

    def test_um_caso_tem_uma_ciencia_do_nucleo_so(self, ddl):
        assert re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS \w+\s+ON ouvidoria_acionamentos\(manifestacao_id\)\s+"
            r"WHERE motivo_ciencia = 'nsp'",
            ddl,
        )

    def test_o_check_de_gatilhos_cobre_o_catalogo_inteiro_numa_transacao(self, ddl):
        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl, f"o CHECK novo perdeu o gatilho {gatilho}"
        assert "BEGIN;" in ddl and "COMMIT;" in ddl

    def test_sem_tabela_nova_nem_policy(self, ddl):
        assert "CREATE TABLE" not in ddl.upper()
        assert "CREATE POLICY" not in ddl.upper()

    def test_a_migration_termina_gravando_o_proprio_numero(self, ddl):
        assert ddl.strip().endswith(
            "INSERT INTO migracoes_aplicadas (numero) VALUES (139) ON CONFLICT (numero) DO NOTHING;"
        )

    def test_a_retencao_apaga_as_justificativas_e_o_motivo(self):
        from app.services.ouvidoria_retencao import CAMPOS_DO_DOSSIE

        for campo in ("nsp_justificativa_simples", "nsp_justificativa_tecnica", "nsp_decisao_motivo"):
            assert campo in CAMPOS_DO_DOSSIE, f"a Retenção não apaga {campo}"
