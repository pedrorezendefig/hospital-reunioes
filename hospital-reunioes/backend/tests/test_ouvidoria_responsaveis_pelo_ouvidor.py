"""Cadastro de Responsável do setor pelo Perfil da Ouvidoria (issue #711, PRD
#706, ADR 0055 decisão 5).

Trocar quem responde por um setor deixa de depender da Diretoria: o ouvidor
encerra a vigência do titular e cadastra o novo, e a próxima cobrança já vai à
pessoa certa. A Tabela de prazos continua onde estava (RN-21), e quem não tem
perfil da Ouvidoria nenhum continua de fora (RN-40).

Os testes entram pelo seam HTTP, no mesmo fake do PostgREST da fatia da
validação: a guarda que decide isso é uma dependência da rota, e exercitá-la
chamando a função da rota direto não provaria porta nenhuma.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_validacao_acionamento import (  # noqa: E402
    DIRETORIA,
    OUVIDOR,
    SECRETARIA,
    SUPER_ADMIN,
    VALIDACAO,
    _client,
    _responsavel,
    _SupabaseFake,
)

from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import ouvidoria_notificacoes  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda o contador em memória de processo: sem o reset, os 429
    de um arquivo caem no seguinte."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o `.env` real (Resend de produção). Todo
    teste deste arquivo passa pelo mock, mesmo os que não olham o email."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append(
            {
                "destinatario": destinatario,
                "assunto": assunto,
                "html": html_content,
                "texto": texto_fallback,
            }
        )
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


# O `audit_log` grava o email do ator, e o participante real sempre o traz
# (`_PARTICIPANTE_FULL_FIELDS`). Os atores do harness da validação nasceram sem
# ele porque lá ninguém o lia; aqui ele é metade do rastro.
OUVIDORA = {**OUVIDOR, "email": "marta@hsm.br"}
DIRETOR = {**DIRETORIA, "email": "diretor@hsm.br"}
ADMIN_TECNICO = {**SUPER_ADMIN, "email": "admin@hsm.br", "perfil_ouvidoria": None}

NOVO_TITULAR = {
    "setor": "Recepcao",
    "papel": "titular",
    "nome": "Bianca Nova",
    "email": "bianca@hsm.br",
    "vigencia_inicio": "2026-09-01",
}


class TestQuemMantemOCadastro:
    """ADR 0055, decisão 5: o Perfil da Ouvidoria inteiro mantém o cadastro."""

    def test_ouvidor_cadastra_responsavel_do_setor(self, monkeypatch):
        """Primeiro critério: a rota de criar aceita o ouvidor, que hoje levava
        403. Sem isso, trocar a pessoa que responde continua passando pela
        Diretoria."""
        # O setor já tem titular vigente; o novo entra depois que o antigo sai,
        # que é como a troca acontece de verdade.
        antigo = _responsavel("titular", vigencia_fim="2026-08-31")
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[antigo]))

        r = client.post("/api/ouvidoria/responsaveis", json=NOVO_TITULAR)

        assert r.status_code == 201, r.text
        gravados = supabase.tabelas["ouvidoria_setor_responsaveis"]
        assert [g["nome"] for g in gravados if g["vigencia_fim"] is None] == ["Bianca Nova"]

    def test_ouvidor_encerra_a_vigencia_do_titular(self, monkeypatch):
        """A outra metade da troca: encerrar a vigência de quem sai é o ato que
        faz a demanda seguinte procurar outra pessoa."""
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-08-31"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_setor_responsaveis"][0]["vigencia_fim"] == "2026-08-31"

    def test_ouvidor_remove_do_cadastro(self, monkeypatch):
        """Cadastrar a pessoa errada é o engano que a remoção conserta, e
        depender da Diretoria para isso era o gargalo."""
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[_responsavel("gestor")]))

        r = client.delete("/api/ouvidoria/responsaveis/resp-gestor")

        assert r.status_code == 204, r.text
        assert supabase.tabelas["ouvidoria_setor_responsaveis"] == []

    @pytest.mark.parametrize(
        "metodo,caminho,corpo",
        [
            ("post", "/api/ouvidoria/responsaveis", NOVO_TITULAR),
            (
                "put",
                "/api/ouvidoria/responsaveis/resp-titular",
                {"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-08-31"},
            ),
            ("delete", "/api/ouvidoria/responsaveis/resp-titular", None),
        ],
    )
    def test_diretoria_continua_mantendo_o_cadastro(self, monkeypatch, metodo, caminho, corpo):
        """A decisão 5 do ADR 0055 SOMA o ouvidor, não troca um perfil pelo
        outro: a Diretoria mantém as três portas."""
        # O titular de hoje já saiu: é o cenário em que o POST cadastra o
        # substituto dele sem esbarrar na guarda de papel único vigente.
        vago = _responsavel("titular", vigencia_fim="2026-08-31")
        client, _ = _client(monkeypatch, DIRETOR, _SupabaseFake(responsaveis=[vago]))

        r = getattr(client, metodo)(caminho, **({"json": corpo} if corpo else {}))

        assert r.status_code in (200, 201, 204), r.text


ESCRITAS_DE_RESPONSAVEL = [
    ("post", "/api/ouvidoria/responsaveis", NOVO_TITULAR),
    (
        "put",
        "/api/ouvidoria/responsaveis/resp-titular",
        {"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-08-31"},
    ),
    ("delete", "/api/ouvidoria/responsaveis/resp-titular", None),
]


class TestOQueNaoMudou:
    """As duas paredes que a decisão 5 do ADR 0055 deixa de pé. Sem elas, trocar
    a guarda por nenhuma guarda passaria verde nos testes de cima."""

    @pytest.mark.parametrize("metodo,caminho,corpo", ESCRITAS_DE_RESPONSAVEL)
    def test_super_admin_tecnico_continua_de_fora(self, monkeypatch, metodo, caminho, corpo):
        """RN-40: papel nas Reuniões não concede nada na Ouvidoria. O super
        admin é o técnico que mantém o app, e ele não decide quem responde por
        um setor do hospital."""
        client, _ = _client(monkeypatch, ADMIN_TECNICO, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        r = getattr(client, metodo)(caminho, **({"json": corpo} if corpo else {}))

        assert r.status_code == 403, r.text

    @pytest.mark.parametrize("metodo,caminho,corpo", ESCRITAS_DE_RESPONSAVEL)
    def test_secretaria_continua_de_fora(self, monkeypatch, metodo, caminho, corpo):
        """Quem não tem perfil da Ouvidoria nenhum nunca entrou e continua sem
        entrar."""
        client, _ = _client(monkeypatch, SECRETARIA, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        r = getattr(client, metodo)(caminho, **({"json": corpo} if corpo else {}))

        assert r.status_code == 403, r.text

    def test_ouvidor_nao_mexe_na_tabela_de_prazos(self, monkeypatch):
        """RN-21, repetida pelo ADR 0055: o ouvidor trabalha com o prazo, quem o
        define é a Diretoria. A porta dos parâmetros não abriu junto."""
        client, _ = _client(monkeypatch, OUVIDORA)

        r = client.put("/api/ouvidoria/prazos/medio/area_resposta", json={"valor": 9, "unidade": "dias_uteis"})

        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "Esta ação da Ouvidoria é exclusiva da Diretoria Executiva"


class TestRastroDeQuemMexeu:
    """Com dois perfis mexendo no mesmo cadastro, "quem trocou o titular" deixa
    de ser óbvio pelo perfil de quem tinha a porta. O ator vai para o
    `audit_log`, a mesma tabela dos outros atos administrativos do app."""

    def test_cadastro_pelo_ouvidor_registra_o_ator(self, monkeypatch):
        antigo = _responsavel("titular", vigencia_fim="2026-08-31")
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[antigo]))

        r = client.post("/api/ouvidoria/responsaveis", json=NOVO_TITULAR)

        assert r.status_code == 201, r.text
        (linha,) = supabase.tabelas["audit_log"]
        assert linha["actor_id"] == "P10"
        assert linha["actor_email"] == "marta@hsm.br"
        assert linha["action"] == "OUVIDORIA_RESPONSAVEL_CREATE"
        assert linha["target_type"] == "responsavel_setor"
        # Sem o setor e o papel no rastro, a linha diz que alguém mexeu no
        # cadastro e não diz em qual cadeia de cobrança isso caiu.
        assert linha["metadata"]["setor"] == "Recepcao"
        assert linha["metadata"]["papel"] == "titular"

    def test_encerramento_de_vigencia_registra_o_ator(self, monkeypatch):
        """A troca de titular é feita por aqui, e é a mudança que mais importa
        rastrear: a partir dela a cobrança muda de pessoa."""
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        r = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-08-31"},
        )

        assert r.status_code == 200, r.text
        (linha,) = supabase.tabelas["audit_log"]
        assert linha["actor_id"] == "P10"
        assert linha["action"] == "OUVIDORIA_RESPONSAVEL_EDIT"
        assert linha["target_id"] == "resp-titular"
        assert linha["metadata"]["vigencia_fim"] == "2026-08-31"

    def test_remocao_registra_o_ator(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[_responsavel("gestor")]))

        r = client.delete("/api/ouvidoria/responsaveis/resp-gestor")

        assert r.status_code == 204, r.text
        (linha,) = supabase.tabelas["audit_log"]
        assert linha["actor_id"] == "P10"
        assert linha["action"] == "OUVIDORIA_RESPONSAVEL_DELETE"
        assert linha["target_id"] == "resp-gestor"

    def test_a_diretoria_deixa_o_mesmo_rastro(self, monkeypatch):
        """O rastro é do ato, não do perfil: gravar só quando é o ouvidor
        deixaria metade das trocas sem autor."""
        client, supabase = _client(monkeypatch, DIRETOR, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        client.delete("/api/ouvidoria/responsaveis/resp-titular")

        (linha,) = supabase.tabelas["audit_log"]
        assert linha["actor_id"] == "P11"
        assert linha["actor_email"] == "diretor@hsm.br"

    def test_ato_recusado_nao_deixa_rastro(self, monkeypatch):
        """A remoção que devolveu 404 não aconteceu, e uma linha de auditoria
        para ela mentiria sobre o cadastro."""
        client, supabase = _client(monkeypatch, OUVIDORA, _SupabaseFake(responsaveis=[_responsavel("titular")]))

        r = client.delete("/api/ouvidoria/responsaveis/resp-que-nao-existe")

        assert r.status_code == 404, r.text
        assert supabase.tabelas.get("audit_log", []) == []


class TestAProximaCobrancaVaiAoNovo:
    """A troca de titular só vale alguma coisa se a cobrança seguinte chegar na
    pessoa nova. O #536 já provou isso com o cadastro trocado à mão; o que a
    #711 acrescenta é a troca feita pelo OUVIDOR, pelas rotas que ele acabou de
    ganhar."""

    def test_titular_trocado_pelo_ouvidor_recebe_a_cobranca(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O caminho inteiro numa sessão só: o caso é acionado com Carlos, o
        ouvidor encerra a vigência dele, cadastra Bianca e cobra. O email da
        cobrança vai para Bianca."""
        client, _ = _client(monkeypatch, OUVIDORA)
        assert client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO).status_code == 200
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["carlos@hsm.br"]

        encerrar = client.put(
            "/api/ouvidoria/responsaveis/resp-titular",
            json={"nome": "Carlos Titular", "email": "carlos@hsm.br", "vigencia_fim": "2026-08-24"},
        )
        assert encerrar.status_code == 200, encerrar.text
        entrar = client.post(
            "/api/ouvidoria/responsaveis",
            json={**NOVO_TITULAR, "nome": "Bianca Nova", "email": "bianca@hsm.br", "vigencia_inicio": "2026-08-25"},
        )
        assert entrar.status_code == 201, entrar.text
        _nunca_envia_email_de_verdade.clear()

        r = client.post("/api/ouvidoria/manifestacoes/uuid-7/cobrar-setor")

        assert r.status_code == 201, r.text
        assert r.json()["destinatario"] == "Bianca Nova"
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == ["bianca@hsm.br"]


class TestARecusaApontaQuemConserta:
    """A cobrança recusada é o lugar onde a falta de cadastro aparece, e a
    frase dela mandava esperar a Diretoria. Agora quem lê é quem conserta, e a
    recusa aponta a tela (issue #711)."""

    def test_setor_sem_ninguem_manda_cadastrar_na_tela(self):
        recusa = ouvidoria_router._recusa_da_cobranca("Recepcao", [], dt.date(2026, 8, 25))

        assert "Responsáveis por setor" in recusa
        assert "Recepcao" in recusa

    def test_responsavel_sem_email_manda_completar_na_tela(self):
        vigente = _responsavel("titular", email="", vigencia_inicio="2026-01-01")
        recusa = ouvidoria_router._recusa_da_cobranca("Recepcao", [vigente], dt.date(2026, 8, 25))

        assert "Responsáveis por setor" in recusa
        assert "Carlos Titular" in recusa
