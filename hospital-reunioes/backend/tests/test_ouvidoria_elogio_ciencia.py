"""O elogio como acionamento de ciência (issue #1618, PRD #1527, ADR 0088).

O elogio vai ao setor só para ele confirmar que recebeu: sem prazo de resposta,
sem cobrança e fora dos vencidos. O responsável clica em "Elogio recebido" no
email, sem senha, e o caso volta ao ouvidor como Pronto para encerrar. Sem o
clique em 5 dias úteis o email sai de novo, uma vez só. No encerramento, quem
elogiou e deixou um email recebe "Seu elogio foi entregue à equipe."

Os dublês de banco são os da validação (`test_ouvidoria_validacao_acionamento`):
o acionamento de ciência nasce pela MESMA porta, e um segundo fake com regras
próprias deixaria os dois caminhos divergirem sem ninguém notar.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import sys
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_ouvidoria_validacao_acionamento import (  # noqa: E402
    DENTRO_DO_EXPEDIENTE,
    OUVIDOR,
    _manifestacao,
    _SupabaseFake,
)

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import ouvidoria_acionamentos, ouvidoria_encerramento, ouvidoria_notificacoes  # noqa: E402

NOTA_DO_OUVIDOR = "A familia agradece a equipe da Recepcao pelo acolhimento no plantao de domingo."

ELOGIO = {
    "tipo_manifestacao": "elogio",
    "categoria": "Acolhimento",
    "setor": "Recepcao",
    "gravidade": "baixo",
    "extrato_para_o_setor": NOTA_DO_OUVIDOR,
}


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


def _client(monkeypatch, supabase: _SupabaseFake | None = None, agora: dt.datetime = DENTRO_DO_EXPEDIENTE):
    """O painel do ouvidor e o link do email no mesmo app, sobre o mesmo banco:
    o elogio nasce numa porta e é confirmado na outra."""
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")
    app.include_router(ouvidoria_setor_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return OUVIDOR

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: agora)
    monkeypatch.setattr(ouvidoria_setor_router, "agora_utc", lambda: agora)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _validar_o_elogio(monkeypatch, supabase: _SupabaseFake | None = None):
    client, supabase = _client(monkeypatch, supabase)
    r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=ELOGIO)
    assert r.status_code == 200, r.text
    return client, supabase


# =====================================================================
# 1. Validar um elogio cria a ciência, sem vencimento de área
# =====================================================================


class TestValidarOElogio:
    def test_validar_um_elogio_cria_uma_ciencia_com_motivo_elogio(self, monkeypatch):
        _client_, supabase = _validar_o_elogio(monkeypatch)

        acionamentos = supabase.tabelas["ouvidoria_acionamentos"]
        assert len(acionamentos) == 1
        ciencia = acionamentos[0]
        assert ciencia["manifestacao_id"] == "uuid-7"
        assert ciencia["tipo"] == "ciencia"
        assert ciencia["motivo_ciencia"] == "elogio"
        assert ciencia["status"] == "pendente"
        assert ciencia["setor"] == "Recepcao"
        assert ciencia["responsavel_email"] == "carlos@hsm.br"
        assert ciencia["prazo"] is None

    def test_o_elogio_validado_nao_grava_vencimento_de_area(self, monkeypatch):
        """A gravidade baixa não tem prazo de área na tabela, então o teste
        valida o elogio como MÉDIO, que tem: o vencimento não pode nascer nem
        quando a tabela teria um para dar."""
        client, supabase = _client(monkeypatch)

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**ELOGIO, "gravidade": "medio"})

        assert r.status_code == 200, r.text
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == "Recepcao"
        assert caso["validada_em"]
        assert caso["prazo_area_em"] is None, "elogio não tem prazo de resposta da área"
        assert r.json()["prazo_area_em"] is None

    def test_o_responsavel_recebe_o_email_com_o_botao_elogio_recebido(self, monkeypatch, emails):
        _validar_o_elogio(monkeypatch)

        assert [e["destinatario"] for e in emails] == ["carlos@hsm.br"]
        email = emails[0]
        assert "Elogio recebido" in email["html"]
        assert NOTA_DO_OUVIDOR in email["html"] and NOTA_DO_OUVIDOR in email["texto"]
        assert re.search(r"/ouvidoria-setor/elogio/[A-Za-z0-9_-]{20,}", email["html"])
        assert "Prazo" not in email["texto"], "o elogio não cobra prazo de ninguém"

    def test_o_elogio_nao_abre_o_portal_de_resposta(self, monkeypatch):
        """O setor só confirma que recebeu: nenhum link do portal de resposta
        nasce, e nenhuma linha de acionamento de resposta vai para a fila."""
        _client_, supabase = _validar_o_elogio(monkeypatch)

        assert supabase.tabelas.get("ouvidoria_setor_tokens", []) == []
        gatilhos = [n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]]
        assert gatilhos == [ouvidoria_notificacoes.GATILHO_CIENCIA_ELOGIO]

    def test_reclamacao_continua_com_o_acionamento_de_resposta(self, monkeypatch):
        """O tipo decide o acionamento, e só o elogio vira ciência (ADR 0088,
        decisão 1)."""
        client, supabase = _client(monkeypatch)

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/validar",
            json={**ELOGIO, "tipo_manifestacao": "reclamacao", "gravidade": "medio"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas.get("ouvidoria_acionamentos", []) == []
        assert supabase.tabelas["ouvidoria_protocolos"][0]["prazo_area_em"]
        gatilhos = [n["gatilho"] for n in supabase.tabelas["ouvidoria_notificacoes"]]
        assert gatilhos == [ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA]


def _token_do_email(email: dict) -> str:
    achado = re.search(r"/ouvidoria-setor/elogio/([A-Za-z0-9_-]+)", email["html"])
    assert achado, "o email do elogio perdeu o link do botão"
    return achado.group(1)


def _clicar(client, token: str):
    return client.post(f"/api/ouvidoria-setor/elogio/{token}/recebido")


# =====================================================================
# 2. O link Elogio recebido funciona sem login e só uma vez
# =====================================================================


class TestOLinkElogioRecebido:
    def test_o_link_funciona_sem_login(self, monkeypatch, emails):
        """O app de teste não tem sessão nenhuma para a rota do link: quem
        clica é o responsável do setor, que não tem login no aplicativo."""
        client, supabase = _validar_o_elogio(monkeypatch)
        client.app.dependency_overrides.pop(get_current_user)

        r = _clicar(client, _token_do_email(emails[0]))

        assert r.status_code == 200, r.text
        assert r.json()["protocolo"] == "2026-0007"
        ciencia = supabase.tabelas["ouvidoria_acionamentos"][0]
        assert ciencia["status"] == "ciente"
        assert ciencia["respondido_em"] == DENTRO_DO_EXPEDIENTE.isoformat()

    def test_o_link_vale_uma_vez_so(self, monkeypatch, emails):
        client, supabase = _validar_o_elogio(monkeypatch)
        token = _token_do_email(emails[0])

        primeiro = _clicar(client, token)
        segundo = _clicar(client, token)

        assert primeiro.status_code == 200, primeiro.text
        assert segundo.status_code == 410
        assert "já foi confirmado" in segundo.json()["detail"]
        confirmacoes = [
            m
            for m in supabase.tabelas["ouvidoria_movimentos"]
            if (m.get("observacao") or "").startswith("Elogio recebido")
        ]
        assert len(confirmacoes) == 1, "o segundo clique não pode mover o caso de novo"

    def test_link_que_nao_existe_e_recusado(self, monkeypatch):
        client, supabase = _validar_o_elogio(monkeypatch)

        r = _clicar(client, "token-que-nunca-foi-emitido")

        assert r.status_code == 404
        assert supabase.tabelas["ouvidoria_acionamentos"][0]["status"] == "pendente"

    def test_o_banco_guarda_so_o_hash_do_token(self, monkeypatch, emails):
        """Vazar a tabela não pode vazar o link do email."""
        _client_, supabase = _validar_o_elogio(monkeypatch)
        token = _token_do_email(emails[0])

        assert supabase.tabelas["ouvidoria_acionamentos"][0]["token_hash"]
        assert token not in str(supabase.tabelas["ouvidoria_acionamentos"])


# =====================================================================
# 3. Depois do clique o caso fica respondido com a marca Pronto para encerrar
# =====================================================================


class TestDepoisDoClique:
    def test_o_caso_fica_respondido_com_a_marca_pronto_para_encerrar(self, monkeypatch, emails):
        client, supabase = _validar_o_elogio(monkeypatch)

        _clicar(client, _token_do_email(emails[0]))

        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        assert caso["status"] == "respondido"
        ultimo = supabase.tabelas["ouvidoria_movimentos"][-1]
        assert ultimo["estado_novo"] == "respondido"
        assert ultimo["autor_nome"] == "Carlos Titular"
        assert "Pronto para encerrar" in ultimo["observacao"]

    def test_o_link_do_setor_antigo_nao_confirma_o_caso_mandado_a_outro(self, monkeypatch, emails):
        """O ouvidor mandou o elogio de novo a outro setor: o clique no email
        antigo não pode devolver ao ouvidor um caso que o setor novo ainda nem
        viu."""
        client, supabase = _validar_o_elogio(monkeypatch)
        token_antigo = _token_do_email(emails[0])
        caso = supabase.tabelas["ouvidoria_protocolos"][0]
        caso["status"] = "em_classificacao"
        supabase.tabelas["ouvidoria_setor_responsaveis"].append(
            {
                "id": "resp-cti",
                "setor": "CTI",
                "papel": "titular",
                "nome": "Bia do CTI",
                "email": "bia@hsm.br",
                "vigencia_inicio": "2026-01-01",
                "vigencia_fim": None,
            }
        )
        supabase.tabelas["setores"].append({"id": "s2", "nome": "CTI", "ativo": True})
        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json={**ELOGIO, "setor": "CTI"})
        assert r.status_code == 200, r.text

        recusa = _clicar(client, token_antigo)

        assert recusa.status_code == 410
        assert "não vale mais" in recusa.json()["detail"]
        assert caso["status"] == "aguardando_area"
        assert [a["status"] for a in supabase.tabelas["ouvidoria_acionamentos"]] == ["devolvido", "pendente"]


# =====================================================================
# 4. Sem clique em 5 dias úteis o email sai de novo, uma vez só
# =====================================================================

# O elogio foi validado na terça, 25/08/2026, às 14h de Brasília. Os 5 dias
# úteis são 26, 27, 28 e 31/08 e 01/09, e vencem no fechamento do quinto: terça,
# 01/09, às 17h de Brasília (20h UTC). Literais de propósito: recalcular aqui com
# o motor de prazos deixaria passar a contagem errada. O "depois" é a manhã de
# quarta, dentro do expediente: o reenvio respeita a janela comercial, e às 17h30
# de terça ele ficaria na fila até a abertura seguinte.
ANTES_DOS_CINCO_DIAS = dt.datetime(2026, 9, 1, 19, 0, tzinfo=dt.UTC)
DEPOIS_DOS_CINCO_DIAS = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.UTC)
DIAS_DEPOIS = dt.datetime(2026, 9, 10, 15, 0, tzinfo=dt.UTC)
FERIADOS = frozenset({dt.date(2026, 9, 7)})


def _reenviar(supabase, agora: dt.datetime) -> int:
    return ouvidoria_acionamentos.reenviar_os_esquecidos(supabase, agora, FERIADOS)


def _emails_do_elogio(emails: list[dict]) -> list[dict]:
    return [e for e in emails if "/ouvidoria-setor/elogio/" in e["html"]]


class TestReenvioUnico:
    def test_antes_dos_cinco_dias_uteis_nada_sai(self, monkeypatch, emails):
        _client_, supabase = _validar_o_elogio(monkeypatch)

        assert _reenviar(supabase, ANTES_DOS_CINCO_DIAS) == 0
        assert len(_emails_do_elogio(emails)) == 1

    def test_sem_clique_em_cinco_dias_uteis_o_email_sai_de_novo(self, monkeypatch, emails):
        _client_, supabase = _validar_o_elogio(monkeypatch)

        assert _reenviar(supabase, DEPOIS_DOS_CINCO_DIAS) == 1

        enviados = _emails_do_elogio(emails)
        assert [e["destinatario"] for e in enviados] == ["carlos@hsm.br", "carlos@hsm.br"]
        assert supabase.tabelas["ouvidoria_acionamentos"][0]["reenviado_em"] == DEPOIS_DOS_CINCO_DIAS.isoformat()

    def test_o_reenvio_sai_uma_vez_so(self, monkeypatch, emails):
        _client_, supabase = _validar_o_elogio(monkeypatch)

        _reenviar(supabase, DEPOIS_DOS_CINCO_DIAS)
        assert _reenviar(supabase, DEPOIS_DOS_CINCO_DIAS) == 0
        assert _reenviar(supabase, DIAS_DEPOIS) == 0

        assert len(_emails_do_elogio(emails)) == 2

    def test_o_link_do_reenvio_confirma_o_elogio(self, monkeypatch, emails):
        client, supabase = _validar_o_elogio(monkeypatch)
        _reenviar(supabase, DEPOIS_DOS_CINCO_DIAS)

        r = _clicar(client, _token_do_email(_emails_do_elogio(emails)[-1]))

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["status"] == "respondido"

    def test_elogio_ja_confirmado_nao_e_reenviado(self, monkeypatch, emails):
        client, supabase = _validar_o_elogio(monkeypatch)
        _clicar(client, _token_do_email(emails[0]))

        assert _reenviar(supabase, DIAS_DEPOIS) == 0
        assert len(_emails_do_elogio(emails)) == 1

    def test_o_reenvio_roda_sozinho_no_scheduler(self):
        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            assert cron.scheduler.get_job("reenvio_elogios_ouvidoria") is not None
        finally:
            cron.stop_scheduler()


# =====================================================================
# 6. O encerramento de um elogio identificado manda o aviso de elogio entregue
# =====================================================================

ENCERRADO_EM = dt.datetime(2026, 9, 2, 13, 0, tzinfo=dt.UTC)
DESFECHO = "Elogio repassado a equipe da Recepcao."


def _encerrar(supabase, caso: dict) -> str:
    """Chama o aviso do encerramento como a transição o chama, e roda o que
    ele agendou para depois da resposta."""
    tarefas = BackgroundTasks()
    resultado = ouvidoria_encerramento.avisar_encerramento(supabase, caso, DESFECHO, ENCERRADO_EM, tarefas)
    asyncio.run(tarefas())
    return resultado


def _caso_encerrado(**overrides) -> dict:
    return _manifestacao(
        status="encerrado",
        setor="Recepcao",
        manifestante_contato="joana@exemplo.com",
        **overrides,
    )


class TestElogioEntregue:
    def test_o_encerramento_do_elogio_identificado_manda_o_aviso_de_elogio_entregue(self, emails):
        caso = _caso_encerrado(tipo_manifestacao="elogio")
        supabase = _SupabaseFake([caso])

        _encerrar(supabase, caso)

        assert [e["destinatario"] for e in emails] == ["joana@exemplo.com"]
        email = emails[0]
        assert "Seu elogio foi entregue à equipe." in email["html"]
        assert "Seu elogio foi entregue a equipe." in email["texto"]
        assert "elogio" in email["assunto"]
        assert "2026-0007" in email["assunto"]

    def test_a_reclamacao_continua_com_o_desfecho_apurado(self, emails):
        caso = _caso_encerrado(tipo_manifestacao="reclamacao")
        supabase = _SupabaseFake([caso])

        _encerrar(supabase, caso)

        assert "Seu elogio foi entregue" not in emails[0]["html"]
        assert DESFECHO in emails[0]["html"]

    def test_o_elogio_anonimo_encerra_sem_aviso(self, emails):
        caso = _caso_encerrado(tipo_manifestacao="elogio", anonimo=True)
        supabase = _SupabaseFake([caso])

        assert _encerrar(supabase, caso) == ouvidoria_encerramento.SEM_CONTATO
        assert emails == []


# =====================================================================
# 7. O kit de conhecimento diz o comportamento novo
# =====================================================================


class TestOKitDeConhecimento:
    """O Assistente de Tecnologia responde sobre a Ouvidoria pelo kit: se o
    texto não disser como o elogio anda agora, ele responde pelo jeito antigo."""

    @pytest.fixture
    def texto(self) -> str:
        from app.services.conhecimento import CONHECIMENTO_DIR

        return (CONHECIMENTO_DIR / "ouvidoria.md").read_text(encoding="utf-8")

    @pytest.fixture
    def paragrafo(self, texto) -> str:
        """O parágrafo que conta o caminho do elogio. Lido sozinho porque
        "sem senha" e "sem prazo" já aparecem no texto, em outras frases, e o
        teste passaria sobre o texto antigo."""
        achados = [p for p in texto.split("\n\n") if "Elogio recebido" in p]
        assert len(achados) == 1, "o kit precisa de um parágrafo que conte o caminho do elogio"
        return achados[0]

    def test_diz_o_botao_sem_senha_e_de_uso_unico(self, paragrafo):
        assert "sem senha" in paragrafo
        assert "vale uma vez" in paragrafo

    def test_diz_que_o_elogio_nao_tem_prazo_nem_entra_nos_vencidos(self, paragrafo):
        assert "não há prazo de resposta" in paragrafo
        assert "não entra nos vencidos" in paragrafo

    def test_diz_o_reenvio_unico_em_cinco_dias_uteis(self, paragrafo):
        assert "5 dias úteis" in paragrafo
        assert "uma única vez" in paragrafo

    def test_diz_a_marca_e_o_aviso_ao_manifestante(self, paragrafo, texto):
        assert "Pronto para encerrar" in paragrafo
        assert "Seu elogio foi entregue à equipe." in texto


# =====================================================================
# A migration: o registro de acionamento e o gatilho novo no banco
# =====================================================================

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "supabase" / "migrations"
MIGRATION = MIGRATIONS_DIR / "136_ouvidoria_acionamento_de_ciencia.sql"


def _sem_comentarios(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestAMigration:
    """O fake do PostgREST não aplica CHECK nem RLS, então é a leitura do
    arquivo que segura as regras do banco."""

    def test_o_registro_de_acionamento_nasce_com_rls_que_nega_por_padrao(self):
        ddl = _sem_comentarios(MIGRATION.read_text(encoding="utf-8"))

        assert "CREATE TABLE IF NOT EXISTS ouvidoria_acionamentos" in ddl
        assert "ALTER TABLE ouvidoria_acionamentos ENABLE ROW LEVEL SECURITY;" in ddl
        assert "CREATE POLICY" not in ddl.upper(), "só o backend lê o registro, pela service role"

    def test_o_tipo_e_o_motivo_sao_listas_fechadas(self):
        ddl = _sem_comentarios(MIGRATION.read_text(encoding="utf-8"))

        assert "CHECK (tipo IN ('resposta', 'ciencia'))" in ddl
        assert "CHECK (motivo_ciencia IN ('elogio', 'nsp'))" in ddl
        assert "'pendente', 'respondido', 'ciente', 'devolvido', 'sem_resposta'" in ddl

    def test_o_gatilho_do_elogio_entra_no_check_numa_transacao(self):
        ddl = _sem_comentarios(MIGRATION.read_text(encoding="utf-8"))

        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl, f"o CHECK novo perdeu o gatilho {gatilho}"
        assert "BEGIN;" in ddl and "COMMIT;" in ddl

    def test_a_migration_termina_gravando_o_proprio_numero(self):
        ddl = _sem_comentarios(MIGRATION.read_text(encoding="utf-8")).strip()

        assert ddl.endswith("INSERT INTO migracoes_aplicadas (numero) VALUES (136) ON CONFLICT (numero) DO NOTHING;")
