"""Redirecionamento pelo ouvidor (issue #708, PRD #706, ADR 0055).

O ouvidor tira o caso de uma área e o aciona em outra numa requisição só, com
motivo obrigatório. A área nova recebe prazo cheio e T1 novo; o compromisso com
o manifestante não se move; os links da área antiga deixam de valer.

Cobre os critérios de aceite da #708 pelo seam HTTP, no fake do PostgREST da
fatia da validação (o redirecionamento chega à MESMA função de acionamento, e
testá-lo por outro harness esconderia justamente o que ele reusa). O Resend
nunca é chamado de verdade.

O relógio anda de propósito entre o acionamento inicial e o redirecionamento:
com o instante congelado nos dois, "T1 novo" e "prazo cheio" ficariam
indistinguíveis de "T1 intocado" e "prazo herdado", e todo mutante que não
recarimba passaria verde.
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import sys

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services import (  # noqa: E402
    ouvidoria_estados,
    ouvidoria_notificacoes,
    ouvidoria_redirecionamento,
)
from app.services.ouvidoria_prorrogacao import CARIMBOS_DEPENDENTES_DO_PRAZO  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_validacao_acionamento import (  # noqa: E402
    EXTRATO,
    OUVIDOR,
    RELATO_CRU,
    SECRETARIA,
    SUPER_ADMIN,
    VALIDACAO,
    _client,
    _manifestacao,
    _responsavel,
    _SupabaseFake,
    _TabelaFake,
)

SETOR_NOVO = "Centro Medico"
EMAIL_DO_SETOR_NOVO = "alice@hsm.br"
EMAIL_DA_RECEPCAO = "carlos@hsm.br"

MOTIVO = "A Recepcao nao agenda consulta de especialidade: quem responde por isso e o Centro Medico."

# O dia seguinte ao do acionamento inicial, 14h de Brasília: dentro do
# expediente, longe de feriado, e um dia útil adiante. É a distância que faz o
# prazo novo e o T1 novo terem valores diferentes dos do primeiro despacho.
UM_DIA_DEPOIS = dt.datetime(2026, 8, 26, 17, 0, tzinfo=dt.UTC)

# Prazo da área do médio, 4 dias úteis. Literais de propósito, e distintos:
# recalculá-los no teste com o mesmo motor do código deixaria passar o erro que
# mais importa aqui, que é não recalcular nada.
PRAZO_DO_PRIMEIRO_DESPACHO = "2026-08-31T20:00:00+00:00"  # 4 dias úteis de 25/08
PRAZO_DA_AREA_NOVA = "2026-09-01T20:00:00+00:00"  # 4 dias úteis de 26/08
# Conclusiva do médio, 7 dias úteis contados do T0 (14/08). Congelada no
# PRIMEIRO despacho e intocada daqui em diante (issue #601).
CONCLUSIVO_CONGELADO = "2026-08-25T20:00:00+00:00"

# O que a rota do portal grava quando a área responde: o marco T2, o texto e
# quem respondeu, os três na mesma escrita da transição para `respondido`.
RESPOSTA_DA_RECEPCAO = "Nao e nosso: quem agenda especialidade e o Centro Medico."
T2_DA_RECEPCAO = "2026-08-25T18:00:00+00:00"
CARIMBO_T2_DA_RECEPCAO = {
    "respondida_em": T2_DA_RECEPCAO,
    "resposta_da_area": RESPOSTA_DA_RECEPCAO,
    "respondida_por_nome": "Carlos Titular",
}

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION = "107_ouvidoria_redirecionamento_pelo_ouvidor.sql"

REDIRECIONAMENTO = {**VALIDACAO, "setor": SETOR_NOVO, "motivo": MOTIVO}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi acumula contagem entre arquivos: sem isto, o 429 de outra
    suíte reaparece aqui como falha sem causa."""
    from app.limiter import limiter

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


def _ddl(nome: str = MIGRATION) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


def _migration_vigente_do_grafo() -> str:
    """A migration que recriou o grafo por último, e portanto a única cujo corpo
    vale no banco: `CREATE OR REPLACE` substitui o anterior inteiro. As
    migrations são numeradas, então a ordem alfabética é a cronológica.

    Mesmo helper (e mesma razão) do arquivo da Devolução à Ouvidoria: número
    fixo aqui faria a próxima fatia que acrescentar uma aresta derrubar o teste
    sem ter quebrado nada."""
    candidatas = sorted(
        os.path.basename(caminho)
        for caminho in glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
        if "CREATE OR REPLACE FUNCTION ouvidoria_transicionar" in open(caminho, encoding="utf-8").read()
    )
    assert candidatas, "Nenhuma migration recria o grafo da RPC"
    return candidatas[-1]


def _banco(**overrides) -> _SupabaseFake:
    """Um caso a despachar, duas áreas na taxonomia e um responsável em cada.

    A segunda área existe porque o redirecionamento sem destino cadastrado é
    outro cenário (o do 409), e o caminho felicidade precisa de uma área que
    de fato possa receber o caso."""
    supabase = _SupabaseFake(
        [_manifestacao(**overrides)],
        responsaveis=[
            _responsavel(),
            _responsavel(
                id="resp-titular-novo",
                setor=SETOR_NOVO,
                nome="Dra. Alice",
                email=EMAIL_DO_SETOR_NOVO,
            ),
        ],
    )
    supabase.tabelas["setores"].append({"id": "s2", "nome": SETOR_NOVO, "ativo": True})
    return supabase


def _com_o_caso_na_recepcao(monkeypatch, emails, supabase=None, estado: str = "aguardando_area"):
    """O caso já acionado na Recepção, com prazo, T1, token do portal e a
    notificação do acionamento, e o relógio já adiantado para o dia seguinte.

    Parte de um acionamento DE VERDADE pela rota de validar, e não de colunas
    escritas à mão: é o que garante que o token da área antiga existe para ser
    revogado e que os valores de partida são os que o motor produz."""
    supabase = supabase if supabase is not None else _banco()
    client, _ = _client(monkeypatch, OUVIDOR, supabase)
    resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)
    assert resposta.status_code == 200, resposta.text
    caso = _caso(supabase)
    assert caso["status"] == "aguardando_area"
    assert caso["prazo_area_em"] == PRAZO_DO_PRIMEIRO_DESPACHO
    assert caso["prazo_conclusivo_em"] == CONCLUSIVO_CONGELADO
    # O caso já andou pelos jobs de prazo: é justamente esse carimbo que o
    # deixaria fora da véspera, da cobrança e da escada se o redirecionamento
    # não o zerasse.
    for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
        caso[carimbo] = "2026-08-26T12:00:00+00:00"
    if estado != "aguardando_area":
        caso["status"] = estado
    if estado == "respondido":
        # O marco T2 e o texto, gravados na MESMA escrita da transição pela rota
        # do portal (`ouvidoria_setor.py`, o `carimbo_t2`).
        #
        # Escrever só `status = "respondido"` era o vácuo que escondia o
        # MUST-FIX 1 da review: o caso "respondido" do teste era um caso que
        # nunca foi respondido, então o critério de aceite 2 inteiro passava
        # verde sobre um mundo que não existe.
        caso.update(dict(CARIMBO_T2_DA_RECEPCAO))
    emails.clear()
    # O relógio anda: daqui para frente é o dia seguinte.
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: UM_DIA_DEPOIS)
    return client, supabase


def _caso(supabase) -> dict:
    return next(m for m in supabase.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")


def _redirecionar(client, corpo: dict | None = None):
    return client.post(
        "/api/ouvidoria/manifestacoes/uuid-7/redirecionamentos",
        json=REDIRECIONAMENTO if corpo is None else corpo,
    )


def _movimentos(supabase) -> list[dict]:
    return supabase.tabelas["ouvidoria_movimentos"]


def _tokens(supabase) -> list[dict]:
    return supabase.tabelas.setdefault("ouvidoria_setor_tokens", [])


def _notificacoes(supabase, gatilho: str) -> list[dict]:
    return [n for n in supabase.tabelas["ouvidoria_notificacoes"] if n["gatilho"] == gatilho]


class TestOCasoSaiDaAreaAntigaEEntraNaNova:
    """Primeiro critério de aceite, ponta a ponta."""

    def test_caso_aguardando_area_termina_com_a_area_nova_e_prazo_cheio(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        caso = _caso(supabase)
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == SETOR_NOVO
        assert caso["prazo_area_em"] == PRAZO_DA_AREA_NOVA, "a área nova não recebeu o prazo cheio do próprio dia"
        assert caso["validada_em"] == UM_DIA_DEPOIS.isoformat(), "o T1 não foi recarimbado no redirecionamento"
        assert caso["validada_por"] == "P10"
        assert caso["prazo_conclusivo_em"] == CONCLUSIVO_CONGELADO, "o compromisso com o manifestante se moveu"
        for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert caso[carimbo] is None, f"{carimbo} ficou preso na fila de um prazo que não existe mais"

    def test_a_trilha_conta_a_saida_e_o_acionamento_nesta_ordem(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: dois movimentos, na ordem, e o de saída com o prefixo que
        o Dossiê vai usar para NÃO contar isto como devolução da área."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        ja_na_trilha = len(_movimentos(supabase))

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        saida, acionamento = _movimentos(supabase)[ja_na_trilha:]
        assert (saida["estado_anterior"], saida["estado_novo"]) == ("aguardando_area", "em_classificacao")
        assert saida["observacao"] == f"Redirecionado pelo ouvidor (de Recepcao): {MOTIVO}"
        assert saida["autor_id"] == "P10"
        assert saida["autor_nome"] == "Marta Ouvidora"
        assert (acionamento["estado_anterior"], acionamento["estado_novo"]) == ("em_classificacao", "aguardando_area")
        assert f"setor {SETOR_NOVO}" in acionamento["observacao"]

    def test_o_setor_antigo_fica_congelado_na_observacao(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O acionamento sobrescreve `setor` no caso na MESMA requisição. Lido
        do caso na hora de montar a frase, o movimento diria que o caso saiu da
        área em que ele acabou de entrar.

        A asserção olha só o CABEÇALHO da observação, e não a frase inteira: o
        nome da área nova aparece de dentro do próprio motivo o tempo todo
        ("não é nosso, isso é do Centro Médico"), e cobrar a ausência dele na
        frase toda seria um teste cego ao que ele existe para pegar."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        saida = next(m for m in _movimentos(supabase) if m["estado_novo"] == "em_classificacao")
        cabecalho = saida["observacao"].split(": ", 1)[0]
        assert cabecalho == "Redirecionado pelo ouvidor (de Recepcao)"
        assert SETOR_NOVO not in cabecalho, "a trilha culpou a área nova pela saída da antiga"

    def test_a_area_nova_e_acionada_por_email_com_link_novo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: `nova_demanda` para a área nova, com link novo. E a
        contraprova da revogação: o link da área antiga cai, o da nova não."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        tokens_da_recepcao = [dict(t) for t in _tokens(supabase)]
        assert tokens_da_recepcao, "o acionamento inicial precisa ter emitido o link da Recepção"

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        acionamentos = _notificacoes(supabase, ouvidoria_notificacoes.GATILHO_NOVA_DEMANDA)
        assert acionamentos[-1]["destinatario_email"] == EMAIL_DO_SETOR_NOVO
        assert [e["destinatario"] for e in _nunca_envia_email_de_verdade] == [EMAIL_DO_SETOR_NOVO]
        vivos = [t for t in _tokens(supabase) if t.get("revogado_em") is None]
        assert len(vivos) == 1, "sobrou link vivo da área antiga, ou o link da área nova nasceu revogado"
        assert vivos[0]["destinatario_email"] == EMAIL_DO_SETOR_NOVO
        antigos = {t["token_hash"] for t in tokens_da_recepcao}
        assert vivos[0]["token_hash"] not in antigos, "a área nova recebeu o link da área antiga"

    def test_o_visto_da_ouvidoria_e_carimbado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: o ouvidor acabou de trabalhar no caso, então o ponto de
        novidade não pode acender pelos movimentos que ele mesmo gravou."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        assert _caso(supabase)["vista_pela_ouvidoria_em"], "o visto não foi carimbado"

    def test_o_registro_de_acesso_nomeia_o_ato(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: registro de acesso gravado (LGPD, ADR 0034), e com nome
        próprio. `registrar_acesso` engole toda exceção, então sem este teste
        uma troca de string ali sumiria sem barulho."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        _redirecionar(client)

        registro = next(a for a in supabase.tabelas["ouvidoria_acessos"] if a["acao"] == "redirecionamento")
        assert registro["manifestacao_id"] == "uuid-7"
        assert registro["ator_id"] == "P10"

    def test_redirecionar_duas_vezes_e_permitido(self, monkeypatch, _nunca_envia_email_de_verdade):
        """ADR 0055, decisão 6: sem limite de vezes, porque a cada volta há um
        humano decidindo."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        assert _redirecionar(client).status_code == 201

        de_volta = _redirecionar(client, {**REDIRECIONAMENTO, "setor": "Recepcao"})

        assert de_volta.status_code == 201, de_volta.text
        assert _caso(supabase)["setor"] == "Recepcao"


class TestOCasoQueAAreaErradaJaRespondeu:
    """Segundo critério: o mesmo ato a partir de `respondido`, que é a área que
    escreveu "isso é do Centro Médico" no campo de resposta em vez de devolver
    pelo link."""

    def test_caso_respondido_e_redirecionado_e_termina_na_area_nova(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado="respondido")

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        caso = _caso(supabase)
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == SETOR_NOVO
        assert caso["prazo_area_em"] == PRAZO_DA_AREA_NOVA
        saida = next(m for m in _movimentos(supabase) if m["estado_novo"] == "em_classificacao")
        assert saida["estado_anterior"] == "respondido"
        assert saida["observacao"] == f"Redirecionado pelo ouvidor (de Recepcao): {MOTIVO}"

    def test_a_resposta_da_area_errada_fica_na_trilha_e_nao_viaja(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: a resposta da área errada fica onde está (a trilha é
        imutável) e não vai para a área nova, que tem que responder ao paciente
        e não à área anterior."""
        supabase = _banco()
        client, supabase = _com_o_caso_na_recepcao(
            monkeypatch, _nunca_envia_email_de_verdade, supabase, estado="respondido"
        )
        resposta_da_recepcao = "Nao e nosso: quem agenda especialidade e o Centro Medico."
        supabase.tabelas["ouvidoria_respostas"] = [
            {"id": "r1", "manifestacao_id": "uuid-7", "texto": resposta_da_recepcao, "setor": "Recepcao"}
        ]

        assert _redirecionar(client).status_code == 201

        assert supabase.tabelas["ouvidoria_respostas"][0]["texto"] == resposta_da_recepcao
        email = _nunca_envia_email_de_verdade[0]
        for corpo in (email["html"], email["texto"]):
            assert resposta_da_recepcao not in corpo, "a resposta da área errada viajou para a área nova"


class TestAsPortasFechadas:
    """Terceiro critério: a porta vale só onde faz sentido, e cada recusa diz o
    que fazer antes."""

    @pytest.mark.parametrize(
        ("estado", "frase"),
        [
            ("aguardando_manifestante", ouvidoria_redirecionamento.RECUSA_PAUSADO),
            ("em_classificacao", ouvidoria_redirecionamento.RECUSA_EM_CLASSIFICACAO),
            ("encerrado", ouvidoria_redirecionamento.RECUSA_ENCERRADO),
            ("novo", ouvidoria_redirecionamento.RECUSA_SEM_AREA),
        ],
    )
    def test_estado_fora_do_par_recusa_com_frase_propria(
        self, monkeypatch, estado, frase, _nunca_envia_email_de_verdade
    ):
        """Prova por mutação da guarda de estado da rota: o mutante que aceita
        `aguardando_manifestante` (ou qualquer um destes) morre aqui, porque a
        asserção não é só o 409, é o caso INTOCADO do outro lado."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado=estado)
        antes = dict(_caso(supabase))

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == frase
        depois = _caso(supabase)
        assert depois["status"] == estado
        assert depois["setor"] == "Recepcao", "o caso mudou de área por um redirecionamento recusado"
        assert depois["prazo_area_em"] == antes["prazo_area_em"], "o relógio da área parou numa recusa"
        assert _nunca_envia_email_de_verdade == [], "a recusa saiu mandando email"
        assert not any(m["estado_novo"] == "em_classificacao" for m in _movimentos(supabase))

    def test_o_caso_pausado_le_que_precisa_ser_retomado_antes(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: frase PRÓPRIA para o caso pausado (ADR 0055, decisão 3).
        Asserta o marcador positivo, e não a ausência de outra frase: a recusa
        genérica do estado passaria por qualquer teste que só cobrasse o 409."""
        client, _ = _com_o_caso_na_recepcao(
            monkeypatch, _nunca_envia_email_de_verdade, estado="aguardando_manifestante"
        )

        detalhe = _redirecionar(client).json()["detail"]

        assert "Retome o caso antes de redirecionar" in detalhe

    def test_area_nova_sem_responsavel_recusa_e_o_caso_fica_onde_estava(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Critério: mesma frase da validação, e "nada acontece" (ADR 0055,
        decisão 1). É a guarda que mais importa desta fatia: conferida depois
        do relógio parar, ela deixaria o caso parado em classificação, fora de
        toda cobrança, por causa de um cadastro que dava para ler antes."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        supabase.tabelas["ouvidoria_setor_responsaveis"] = [_responsavel()]
        prazo = _caso(supabase)["prazo_area_em"]

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == ouvidoria_router.recusa_de_setor_sem_responsavel(SETOR_NOVO)
        caso = _caso(supabase)
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == "Recepcao"
        assert caso["prazo_area_em"] == prazo, "o caso perdeu o relógio por uma área nova que não podia receber"
        for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert caso[carimbo] is not None, f"{carimbo} foi zerado por um redirecionamento que não aconteceu"
        assert _nunca_envia_email_de_verdade == []

    @pytest.mark.parametrize("motivo", ["", "   ", "​"])
    def test_motivo_vazio_e_recusado(self, monkeypatch, motivo, _nunca_envia_email_de_verdade):
        """Critério: 422 de motivo vazio. O invisível entra na lista porque o
        `strip` não o enxerga: sem a peneira, um caractere de largura zero
        passaria por motivo escrito."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "motivo": motivo})

        assert resposta.status_code == 422, resposta.text
        assert resposta.json()["detail"] == ouvidoria_redirecionamento.RECUSA_VAZIA
        assert _caso(supabase)["setor"] == "Recepcao"

    def test_motivo_acima_do_teto_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: 422 de motivo longo. O teto existe porque o texto vai para
        a trilha imutável."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        gigante = "a" * (ouvidoria_redirecionamento.MAXIMO_DE_CARACTERES + 1)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "motivo": gigante})

        assert resposta.status_code == 422, resposta.text
        assert resposta.json()["detail"] == ouvidoria_redirecionamento.RECUSA_LONGA
        assert _caso(supabase)["setor"] == "Recepcao"

    def test_o_motivo_no_teto_exato_passa(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A contraprova do teto: `>` e `>=` trocados fariam o limite recusar o
        texto que ele promete aceitar."""
        client, _ = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        no_limite = "a" * ouvidoria_redirecionamento.MAXIMO_DE_CARACTERES

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "motivo": no_limite})

        assert resposta.status_code == 201, resposta.text

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_quem_nao_e_da_ouvidoria_nao_redireciona_nem_pela_api(
        self, monkeypatch, participante, _nunca_envia_email_de_verdade
    ):
        """Critério: 403 sem Perfil da Ouvidoria. Nem o super admin técnico
        (RN-40), que administra o sistema e não lê o caso."""
        supabase = _banco(status="aguardando_area", setor="Recepcao")
        client, _ = _client(monkeypatch, participante, supabase)

        resposta = _redirecionar(client)

        assert resposta.status_code == 403, resposta.text
        assert _caso(supabase)["setor"] == "Recepcao"
        assert _nunca_envia_email_de_verdade == []

    def test_manifestacao_inexistente_e_404(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, _ = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-nao-existe/redirecionamentos", json=REDIRECIONAMENTO)

        assert resposta.status_code == 404, resposta.text


# O carimbo que a Retenção grava no fim da anonimização (migration 079), e o
# pedido que a Diretoria grava antes dele (issue #595).
APAGADO_EM = "2026-09-01T03:00:00+00:00"


class TestCasoApagadoPelaRetencao:
    """Critério: o caso apagado pela Retenção não é redirecionado.

    É a guarda mais forte da fatia: redirecionar manda para FORA do painel, por
    email e com token de portal sem login, o relato de um caso que a Diretoria
    mandou apagar (ADR 0047)."""

    @pytest.mark.parametrize("carimbo", ["anonimizada_em", "apagamento_pedido_em"])
    def test_o_caso_apagado_nao_sai_para_outra_area(self, monkeypatch, carimbo, _nunca_envia_email_de_verdade):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        _caso(supabase)[carimbo] = APAGADO_EM

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        caso = _caso(supabase)
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == "Recepcao"
        assert _nunca_envia_email_de_verdade == [], "o relato de um caso apagado saiu por email"


class TestCasoProtegido:
    """Quarto critério: sigiloso e anônimo saem com a MESMA guarda do
    acionamento, porque o redirecionamento chega à mesma função (RN-79)."""

    def _protegido(self, **overrides) -> _SupabaseFake:
        return _banco(resumo=RELATO_CRU, relato_integral=RELATO_CRU, **overrides)

    @pytest.mark.parametrize(
        "protecao",
        [
            {"sigilo_reforcado": True},
            {"anonimo": True, "manifestante_nome": None},
        ],
    )
    def test_o_email_da_area_nova_nao_leva_o_relato_cru_nem_a_identificacao(
        self, monkeypatch, protecao, _nunca_envia_email_de_verdade
    ):
        client, _ = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, self._protegido(**protecao))

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        email = _nunca_envia_email_de_verdade[0]
        assert email["destinatario"] == EMAIL_DO_SETOR_NOVO
        assert EXTRATO in email["html"], "o extrato do ouvidor é o que sustenta o trabalho da área protegida"
        for corpo in (email["html"], email["texto"]):
            assert "Maria Silva" not in corpo
            assert "leito 302" not in corpo


class TestFalhaNoMeio:
    """Quinto critério: a ordem dos passos é a ordem de compensação."""

    def test_falha_na_rpc_de_saida_restaura_prazo_e_carimbos(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A falha é injetada DENTRO do `execute`, que é onde ela nasce de
        verdade: um fake que levanta no `rpc` pularia o bloco que a guarda
        protege e o teste passaria sobre nada."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        prazo = _caso(supabase)["prazo_area_em"]
        rpc_de_verdade = supabase.rpc

        def _falha_so_na_saida(nome, params):
            if params["p_estado_novo"] == "em_classificacao":

                class _Recusa:
                    def execute(self):
                        raise APIError({"code": "23514", "message": "Transicao invalida"})

                return _Recusa()
            return rpc_de_verdade(nome, params)

        monkeypatch.setattr(supabase, "rpc", _falha_so_na_saida)

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        depois = _caso(supabase)
        assert depois["status"] == "aguardando_area"
        assert depois["setor"] == "Recepcao"
        assert depois["prazo_area_em"] == prazo, "o caso ficou sem vencimento e sumiu da cobrança"
        # Os carimbos dos jobs NÃO voltam, e é assimetria de propósito (a
        # mesma que a devolução já tinha): a linha casada prova que o caso
        # continua com a área, e um carimbo zerado a mais custa um aviso
        # repetido, enquanto restaurá-lo errado custa a cobrança que não sai.
        for nome in CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert depois[nome] is None
        assert _nunca_envia_email_de_verdade == []

    def test_timeout_na_saida_tambem_restaura(self, monkeypatch, _nunca_envia_email_de_verdade):
        """`HTTPError` não é `APIError`: timeout do PostgREST nasce antes de
        existir resposta HTTP. Sem ele na tupla, a falha de rede escaparia crua
        e o caso ficaria sem vencimento com um 500 mudo."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        prazo = _caso(supabase)["prazo_area_em"]
        rpc_de_verdade = supabase.rpc

        def _timeout_na_saida(nome, params):
            if params["p_estado_novo"] == "em_classificacao":

                class _Timeout:
                    def execute(self):
                        raise httpx.ReadTimeout("o banco não respondeu no tempo")

                return _Timeout()
            return rpc_de_verdade(nome, params)

        monkeypatch.setattr(supabase, "rpc", _timeout_na_saida)

        resposta = _redirecionar(client)

        assert resposta.status_code >= 400
        depois = _caso(supabase)
        assert depois["status"] == "aguardando_area"
        assert depois["prazo_area_em"] == prazo

    def test_falha_no_acionamento_deixa_o_caso_em_classificacao_e_aponta_o_validar(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Critério: nunca em `aguardando_area` sem acionamento válido. O caso
        para em `em_classificacao`, com o movimento da saída na trilha, e a
        resposta diz onde ele ficou e qual botão usar."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        rpc_de_verdade = supabase.rpc

        def _falha_so_na_entrada(nome, params):
            if params["p_estado_novo"] == "aguardando_area":

                class _Cai:
                    def execute(self):
                        raise APIError({"code": "57014", "message": "statement timeout"})

                return _Cai()
            return rpc_de_verdade(nome, params)

        monkeypatch.setattr(supabase, "rpc", _falha_so_na_entrada)

        resposta = _redirecionar(client)

        assert resposta.status_code == 500, resposta.text
        assert "Validar e acionar" in resposta.json()["detail"]
        caso = _caso(supabase)
        assert caso["status"] == "em_classificacao", "o caso ficou aguardando uma área que ninguém acionou"
        assert caso["prazo_area_em"] is None
        saida = next(m for m in _movimentos(supabase) if m["estado_novo"] == "em_classificacao")
        assert saida["observacao"] == f"Redirecionado pelo ouvidor (de Recepcao): {MOTIVO}"
        assert _nunca_envia_email_de_verdade == []

    def test_falha_ao_parar_o_relogio_nao_move_o_caso(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O primeiro passo que escreve. Falhar aqui é não ter começado: o caso
        continua com a área antiga, com o prazo dela."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        prazo = _caso(supabase)["prazo_area_em"]
        update_de_verdade = _TabelaFake.update

        def _cai_ao_parar_o_relogio(self, payload):
            if self.nome == "ouvidoria_protocolos" and payload.get("prazo_area_em", "?") is None:
                raise httpx.ConnectError("conexão recusada")
            return update_de_verdade(self, payload)

        monkeypatch.setattr(_TabelaFake, "update", _cai_ao_parar_o_relogio)

        resposta = _redirecionar(client)

        assert resposta.status_code == 500, resposta.text
        assert "continua com ela" in resposta.json()["detail"]
        caso = _caso(supabase)
        assert caso["status"] == "aguardando_area"
        assert caso["setor"] == "Recepcao"
        assert caso["prazo_area_em"] == prazo
        assert not any(m["estado_novo"] == "em_classificacao" for m in _movimentos(supabase))


class TestOEstouroConsumadoDaAreaAntiga:
    """A conta do prazo é a da devolução (ADR 0048, decisão 2, que o ADR 0055
    repete): o tempo perdido com a área errada não pode ser cobrado da certa."""

    def test_area_nova_nao_nasce_estourada_pela_area_antiga(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A Recepção furou o prazo antes do redirecionamento. O carimbo do
        estouro sai quando a área MUDA, senão `cumprimento_da_area` leria o
        caso da área nova como estourado no primeiro instante dela, e nenhuma
        prorrogação aprovada depois conseguiria limpá-lo."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        _caso(supabase)["prazo_area_em"] = "2026-08-24T20:00:00+00:00"

        assert _redirecionar(client).status_code == 201

        assert _caso(supabase)["area_estourou_em"] is None


class TestRedirecionarParaAMesmaArea:
    """Decisão do Pedro na review do PR #714: a área nova tem que ser OUTRA.

    Sem esta recusa o redirecionamento seria o caminho para dar prazo INTEIRO
    novo a quem já falhou, só escrevendo um motivo, contornando a devolução por
    insuficiência, que dá MEIO prazo de propósito."""

    def test_a_mesma_area_e_recusada_e_o_caso_fica_intocado(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        antes = dict(_caso(supabase))

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "setor": "Recepcao"})

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == ouvidoria_router.RECUSA_DA_MESMA_AREA
        assert "devolução por insuficiência" in resposta.json()["detail"], (
            "a recusa não aponta o ato previsto para cobrar de novo a mesma área"
        )
        depois = _caso(supabase)
        assert depois["setor"] == "Recepcao"
        assert depois["prazo_area_em"] == antes["prazo_area_em"], (
            "a área ganhou prazo novo por um redirecionamento recusado"
        )
        assert depois["validada_em"] == antes["validada_em"], "o T1 foi recarimbado numa recusa"
        for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert depois[carimbo] == antes[carimbo]
        assert _nunca_envia_email_de_verdade == []
        assert not any(m["estado_novo"] == "em_classificacao" for m in _movimentos(supabase))

    def test_a_grafia_da_taxonomia_e_que_decide(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A comparação é contra a grafia CANÔNICA, não contra o que o ouvidor
        digitou: sem isso, "recepcao" em caixa baixa passaria por área diferente
        de "Recepcao" e o contorno voltaria pela porta da digitação (issue
        #419)."""
        client, _ = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "setor": "  recepcao  "})

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == ouvidoria_router.RECUSA_DA_MESMA_AREA

    def test_a_area_estourada_nao_limpa_a_ficha_por_esta_porta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O que a recusa protege, dito pelo efeito: a área que estourou o prazo
        não consegue zerar o relógio nem a própria ficha por aqui. Zerar o
        carimbo na área RECONFIRMADA é o que a migration 076 existe para
        impedir."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        _caso(supabase)["prazo_area_em"] = "2026-08-24T20:00:00+00:00"
        _caso(supabase)["area_estourou_em"] = "2026-08-24T20:00:00+00:00"

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "setor": "Recepcao"})

        assert resposta.status_code == 409, resposta.text
        depois = _caso(supabase)
        assert depois["area_estourou_em"] == "2026-08-24T20:00:00+00:00"
        assert depois["prazo_area_em"] == "2026-08-24T20:00:00+00:00"


class TestAValidacaoContinuaRecusandoAChegada:
    """Nono critério: a rota de validar continua sendo a porta só do despacho a
    partir de `em_classificacao`, e agora ela NOMEIA o redirecionamento."""

    @pytest.mark.parametrize("estado", ["aguardando_area", "respondido"])
    def test_validar_recusa_o_caso_que_ja_esta_com_a_area(self, monkeypatch, estado, _nunca_envia_email_de_verdade):
        supabase = _banco(status=estado)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        resposta = client.post("/api/ouvidoria/manifestacoes/uuid-7/validar", json=VALIDACAO)

        assert resposta.status_code == 409, resposta.text
        detalhe = resposta.json()["detail"]
        assert "devolução por insuficiência" in detalhe, "a frase perdeu a saída que ela já oferecia"
        assert "redirecionamento" in detalhe, "a frase não conta ao ouvidor a saída que esta fatia criou"
        assert _nunca_envia_email_de_verdade == []


class TestValidarTransicaoExigeOMotivo:
    """Sétimo critério, na função pura: nenhuma das duas arestas de saída para
    `em_classificacao` passa calada pela transição genérica (ADR 0055)."""

    @pytest.mark.parametrize("origem", ["aguardando_area", "respondido"])
    def test_a_aresta_e_aceita_com_motivo(self, origem):
        ouvidoria_estados.validar_transicao(origem, "em_classificacao", motivo_redirecionamento=MOTIVO)

    @pytest.mark.parametrize("origem", ["aguardando_area", "respondido"])
    @pytest.mark.parametrize("motivo", [None, "", "   "])
    def test_a_aresta_e_recusada_sem_motivo(self, origem, motivo):
        """O mutante que remove a guarda morre aqui, e nas DUAS origens: a
        `aguardando_area` já existia desde a #600 e passava calada."""
        with pytest.raises(ouvidoria_estados.DadosInsuficientesError):
            ouvidoria_estados.validar_transicao(origem, "em_classificacao", motivo_redirecionamento=motivo)

    def test_o_redirecionamento_nao_e_devolucao_nem_pausa(self):
        """As famílias não se confundem: `e_devolucao` decide meio prazo e
        aviso à área, e casar aqui jogaria o redirecionamento no fluxo errado."""
        assert ouvidoria_estados.e_redirecionamento("aguardando_area", "em_classificacao") is True
        assert ouvidoria_estados.e_redirecionamento("respondido", "em_classificacao") is True
        assert ouvidoria_estados.e_redirecionamento("aguardando_manifestante", "em_classificacao") is False
        assert ouvidoria_estados.e_devolucao("aguardando_area", "em_classificacao") is False
        assert ouvidoria_estados.e_pausa("aguardando_area", "em_classificacao") is False

    def test_a_pausa_continua_fora_das_origens(self):
        """ADR 0055, decisão 3. A régua é a lista da máquina, não a tabela de
        frases do serviço."""
        assert "aguardando_manifestante" not in ouvidoria_estados.ORIGENS_DO_REDIRECIONAMENTO
        with pytest.raises(ouvidoria_estados.TransicaoInvalidaError):
            ouvidoria_estados.validar_transicao(
                "aguardando_manifestante", "em_classificacao", motivo_redirecionamento=MOTIVO
            )


class TestAPortaDosFundosEstaFechada:
    """Decisão do Pedro na review do PR #714: a rota genérica de transição passa
    a RECUSAR as duas arestas de saída para `em_classificacao`.

    Ela tirava o caso da área sem parar o relógio, sem derrubar os links da área
    antiga, sem carimbar o estouro consumado e sem o prefixo que o Dossiê usa
    para não contar o ato como devolução. Nenhuma tela mandava esse destino: só
    requisição montada à mão chegava lá."""

    @pytest.mark.parametrize("estado", ["aguardando_area", "respondido"])
    @pytest.mark.parametrize("corpo_extra", [{}, {"observacao": MOTIVO}])
    def test_a_rota_generica_recusa_e_aponta_o_redirecionamento(
        self, monkeypatch, estado, corpo_extra, _nunca_envia_email_de_verdade
    ):
        """Recusa COM e SEM observação: escrever um motivo não é mais o preço de
        entrada, porque a porta não existe mais."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado=estado)
        antes = dict(_caso(supabase))

        muda = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "em_classificacao", **corpo_extra},
        )

        assert muda.status_code == 409, muda.text
        assert muda.json()["detail"] == ouvidoria_router.RECUSA_DA_TRANSICAO_GENERICA
        assert "redirecionamento" in muda.json()["detail"], "a recusa não diz por onde o ato se faz"
        depois = _caso(supabase)
        assert depois["status"] == estado
        assert depois["prazo_area_em"] == antes["prazo_area_em"]
        assert not any(m["estado_novo"] == "em_classificacao" for m in _movimentos(supabase))

    def test_o_travessao_nao_entra_mais_na_trilha_por_essa_porta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A `observacao` da rota genérica nunca passou por `sem_invisiveis` nem
        por `sanitizar_travessao`: enquanto ela respondia pelo motivo do
        redirecionamento, um travessão colado pelo ouvidor entrava CRU na trilha
        imutável (ADR 0013). Fechada a porta, o texto não chega à trilha."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        muda = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "em_classificacao", "observacao": "Area errada — e do Centro Medico"},
        )

        assert muda.status_code == 409, muda.text
        assert not any("—" in (m.get("observacao") or "") for m in _movimentos(supabase))

    def test_um_ponto_final_nao_abre_mais_a_porta(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A guarda de motivo da rota genérica só enfrentava `.strip()`: um
        caractere não branco qualquer bastava. Agora nem isso passa."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        muda = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": "em_classificacao", "observacao": "."},
        )

        assert muda.status_code == 409, muda.text
        assert _caso(supabase)["status"] == "aguardando_area"

    @pytest.mark.parametrize(
        ("de", "para"),
        [("aguardando_area", "aguardando_manifestante"), ("aguardando_manifestante", "aguardando_area")],
    )
    def test_a_pausa_e_a_retomada_continuam_passando(self, monkeypatch, de, para, _nunca_envia_email_de_verdade):
        """A contraprova, que é o que separa guarda de indisponibilidade: a rota
        genérica continua sendo a porta da pausa e da retomada, que são os dois
        estados que o Dossiê de fato manda."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado=de)

        muda = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/transicoes",
            json={"estado": para, "observacao": "O manifestante precisa confirmar a data do atendimento."},
        )

        assert muda.status_code == 200, muda.text
        assert _caso(supabase)["status"] == para


class TestARecusaDoEstadoComoFuncaoPura:
    """A tabela de frases fecha por lista de origens, não por lista de frases."""

    @pytest.mark.parametrize("estado", ["aguardando_area", "respondido"])
    def test_as_duas_origens_passam(self, estado):
        assert ouvidoria_redirecionamento.recusa_do_estado(estado) is None

    @pytest.mark.parametrize("estado", ["novo", "em_classificacao", "aguardando_manifestante", "encerrado", None, ""])
    def test_o_resto_recusa(self, estado):
        assert ouvidoria_redirecionamento.recusa_do_estado(estado)

    def test_estado_desconhecido_recusa_em_vez_de_liberar(self):
        """Fail-closed: estado que a tabela de frases não nomeia é recusado. Se
        a régua fosse a tabela, um estado novo na máquina nasceria
        redirecionável sem ninguém decidir isso."""
        assert ouvidoria_redirecionamento.recusa_do_estado("estado_que_nao_existe")


class TestAMigration:
    """O banco guarda a mesma regra que o Python: contornar a API não pode
    contornar a máquina de estados (migration 064 em diante)."""

    def test_a_aresta_nova_entra_na_funcao_do_banco(self):
        ddl = _ddl()
        assert "CREATE OR REPLACE FUNCTION ouvidoria_transicionar" in ddl
        aresta = next(linha for linha in ddl.splitlines() if "v_atual = 'respondido'" in linha)
        assert "'em_classificacao'" in aresta

    def test_o_grafo_recriado_carrega_todas_as_arestas(self):
        """`CREATE OR REPLACE` substitui o corpo inteiro: uma aresta esquecida
        trava em produção um caminho que hoje funciona, e quem manda é o ÚLTIMO
        corpo criado.

        Por isso a cobrança é na migration VIGENTE do grafo, e não na 107 fixa:
        é o mesmo desenho do teste irmão em `test_ouvidoria_devolucao_a_ouvidoria`,
        e é ele que continua valendo na próxima fatia que acrescentar uma aresta.
        Fixar o número aqui derrubaria este teste sem nada ter quebrado, e ainda
        deixaria de olhar justamente a migration que passou a valer."""
        ddl = _ddl(_migration_vigente_do_grafo())
        for atual, destinos in ouvidoria_estados.TRANSICOES.items():
            linha = next(linha for linha in ddl.splitlines() if f"v_atual = '{atual}'" in linha)
            for destino in destinos:
                assert f"'{destino}'" in linha, f"O banco não deixa ir de {atual} para {destino}"

    def test_a_rpc_nao_fica_ao_alcance_da_chave_do_bundle(self):
        """O `PUBLIC` no REVOKE não é enfeite: no banco em que a função nascer
        nesta migration, o Postgres concede EXECUTE a PUBLIC no nascimento, e
        `anon` (a chave do bundle do frontend) herda por ali mesmo com o revoke
        nominal. Mesma forma da 095, da 097 e da 098."""
        revoke = next(linha for linha in _ddl().splitlines() if linha.startswith("  FROM "))
        assert revoke.strip() == "FROM PUBLIC, anon, authenticated;"
        assert "GRANT EXECUTE ON FUNCTION ouvidoria_transicionar" in _ddl()

    def test_a_migration_nao_cria_tabela_nem_coluna(self):
        """O motivo e o setor antigo vivem na trilha (ADR 0055): coluna nova
        aqui seria um lugar a mais para a Retenção varrer."""
        ddl = _ddl().upper()
        assert "CREATE TABLE" not in ddl
        assert "ADD COLUMN" not in ddl

    def test_a_migration_nao_mexe_no_check_de_gatilhos(self):
        """O aviso à área antiga (`redirecionamento_area`) é fatia própria. Uma
        lista de gatilhos recriada aqui, incompleta, derrubaria a constraint em
        produção sem nenhum ganho para esta fatia."""
        assert "ouvidoria_notificacoes_gatilho_check" not in _ddl()


class TestSemTravessao:
    """Décimo critério (ADR 0013): travessão e meia-risca são marca de texto
    gerado por IA e não aparecem em nada que o time lê."""

    @pytest.mark.parametrize(
        "texto",
        [
            ouvidoria_redirecionamento.RECUSA_VAZIA,
            ouvidoria_redirecionamento.RECUSA_LONGA,
            ouvidoria_redirecionamento.RECUSA_PAUSADO,
            ouvidoria_redirecionamento.RECUSA_EM_CLASSIFICACAO,
            ouvidoria_redirecionamento.RECUSA_ENCERRADO,
            ouvidoria_redirecionamento.RECUSA_SEM_AREA,
            ouvidoria_router.RECUSA_DO_CASO_JA_NA_AREA,
            ouvidoria_router.FALHA_DEPOIS_DA_SAIDA,
            ouvidoria_router.SAIU_DA_AREA_NO_MEIO,
            ouvidoria_router.recusa_de_setor_sem_responsavel(SETOR_NOVO),
        ],
    )
    def test_nenhuma_frase_da_fatia_tem_travessao(self, texto):
        assert "—" not in texto
        assert "–" not in texto

    def test_o_travessao_do_motivo_e_sanitizado_antes_da_trilha(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O ouvidor cola um texto de outro lugar e o travessão vem junto. Ele
        morre na peneira do motivo, antes de a trilha imutável o guardar."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = _redirecionar(client, {**REDIRECIONAMENTO, "motivo": "Area errada — e do Centro Medico"})

        assert resposta.status_code == 201, resposta.text
        saida = next(m for m in _movimentos(supabase) if m["estado_novo"] == "em_classificacao")
        assert "—" not in saida["observacao"]
        assert "Area errada" in saida["observacao"]


class TestARegraDoRelogioSaiuDaRotaDaDevolucao:
    """Sexto critério: a lógica de parar o relógio virou função compartilhada.

    Os testes que provam que a devolução do setor não regrediu ficam no arquivo
    dela (`test_ouvidoria_devolucao_a_ouvidoria.py`), que a exercita PELA ROTA
    do portal. O que se prova aqui é que as duas portas passam pela MESMA
    função: uma cópia nova em qualquer das duas deixaria este teste verde e a
    outra porta sem os ajustes das issues #607 e #623."""

    def test_as_duas_portas_chamam_a_mesma_funcao(self):
        from app.routers import ouvidoria_setor
        from app.services import ouvidoria_relogio_da_area

        assert ouvidoria_setor.ouvidoria_relogio_da_area is ouvidoria_relogio_da_area
        assert ouvidoria_router.ouvidoria_relogio_da_area is ouvidoria_relogio_da_area
        assert not hasattr(ouvidoria_setor, "_restaurar_prazo"), (
            "a cópia antiga do rollback voltou a existir na rota da devolução"
        )

    def test_parar_o_relogio_filtra_pelo_estado_de_origem_lido(self):
        """A generalização que a fatia exigiu: a devolução parte só de
        `aguardando_area`, o redirecionamento também de `respondido`. O filtro
        é o estado LIDO, e não um literal, senão o update do caso respondido
        não casaria linha nenhuma e o caso iria para a área nova com o relógio
        da antiga ainda correndo."""
        from app.services import ouvidoria_relogio_da_area

        vistos: list[tuple[str, object]] = []

        class _Tabela:
            def update(self, payload):
                vistos.append(("update", payload))
                return self

            def eq(self, coluna, valor):
                vistos.append((coluna, valor))
                return self

            def execute(self):
                return type("R", (), {"data": [{}]})()

        class _Supabase:
            def table(self, _nome):
                return _Tabela()

        parado = ouvidoria_relogio_da_area.parar(
            _Supabase(), "uuid-7", {"status": "respondido", "prazo_area_em": PRAZO_DO_PRIMEIRO_DESPACHO}, None
        )

        assert ("status", "respondido") in vistos
        assert parado.estado_de_origem == "respondido"
        assert parado.prazo_anterior == PRAZO_DO_PRIMEIRO_DESPACHO
        assert parado.carimbo_a_restaurar == {}, "sem estouro a gravar, o rollback não toca o carimbo"


class TestOMarcoT2DaAreaAntiga:
    """MUST-FIX 1 da review do PR #714: o caso que vem de `respondido` não pode
    chegar à área nova com o marco T2 da área ERRADA.

    `cumprimento_da_area` lê `respondida_em` como "a resposta do ciclo
    CORRENTE": com o carimbo da Recepção de pé, o Centro Médico nasce
    `cumprido` e continua `cumprido` mesmo sem nunca responder, porque
    `ouvidoria_prazos` corta em `if respondida_em is not None` antes de olhar o
    vencimento. É a mesma limpeza que a devolução por insuficiência e a
    reabertura por reincidência fazem, pelo motivo escrito nas duas."""

    def test_o_caso_chega_a_area_nova_sem_o_t2_da_antiga(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado="respondido")
        assert _caso(supabase)["respondida_em"] == T2_DA_RECEPCAO, "o fixture precisa gravar o T2 de verdade"

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        caso = _caso(supabase)
        assert caso["setor"] == SETOR_NOVO
        assert caso["respondida_em"] is None, "a área nova nasceu com a resposta da área errada carimbada"
        assert caso["respondida_por_nome"] is None
        # O TEXTO fica, como na devolução por insuficiência: ele é a resposta
        # corrente que o ouvidor relê, e a trilha guarda a cópia imutável dele.
        # O que mentia era o MARCO, não o texto.
        assert caso["resposta_da_area"] == RESPOSTA_DA_RECEPCAO

    def test_a_api_nao_diz_cumprido_para_a_area_que_nao_respondeu(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A prova pela RESPOSTA da própria rota, que é o que o Dossiê e o
        portal do responsável leem. Antes do conserto vinha "cumprido" no
        primeiro instante da área nova."""
        client, _ = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado="respondido")

        resposta = _redirecionar(client)

        assert resposta.status_code == 201, resposta.text
        assert resposta.json()["cumprimento"] != "cumprido", (
            "a área nova aparece como cumprida sem ter escrito uma linha"
        )

    def test_o_caso_nao_some_das_pendencias_por_area(self, monkeypatch, _nunca_envia_email_de_verdade):
        """`_esta_com_a_area` é `status == aguardando_area and not
        respondida_em`. Com o T2 velho de pé o caso sumia das pendências por
        área da Diretoria enquanto o prazo dele corria."""
        from app.services import ouvidoria_metricas

        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado="respondido")

        assert _redirecionar(client).status_code == 201

        assert ouvidoria_metricas._esta_com_a_area(_caso(supabase)) is True

    def test_o_rollback_devolve_o_t2_quando_a_saida_falha(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O par do `limpar_a_resposta`: desfazer meio par é pior que não
        desfazer nada. Sem isto o rollback deixaria um caso `respondido` sem
        marco T2, que é o mesmo meio-desfazer que a issue #623 corrigiu."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade, estado="respondido")
        rpc_de_verdade = supabase.rpc

        def _falha_so_na_saida(nome, params):
            if params["p_estado_novo"] == "em_classificacao":

                class _Recusa:
                    def execute(self):
                        raise APIError({"code": "23514", "message": "Transicao invalida"})

                return _Recusa()
            return rpc_de_verdade(nome, params)

        monkeypatch.setattr(supabase, "rpc", _falha_so_na_saida)

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        caso = _caso(supabase)
        assert caso["status"] == "respondido"
        assert caso["respondida_em"] == T2_DA_RECEPCAO, "o caso ficou respondido sem o marco da resposta"
        assert caso["respondida_por_nome"] == "Carlos Titular"
        assert caso["prazo_area_em"] == PRAZO_DO_PRIMEIRO_DESPACHO

    def test_o_caso_que_vem_de_aguardando_area_nao_ganha_marco_nenhum(self, monkeypatch, _nunca_envia_email_de_verdade):
        """A contraprova da limpeza: o caso que nunca foi respondido continua
        sem T2 depois do redirecionamento."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)

        assert _redirecionar(client).status_code == 201

        caso = _caso(supabase)
        assert caso["respondida_em"] is None
        assert caso["setor"] == SETOR_NOVO


def _espiar_os_updates():
    """Um dublê mínimo do PostgREST que só guarda o payload de cada update.

    Existe porque a pergunta desta seção é sobre o PAYLOAD, e não sobre o estado
    final: coluna nunca escrita e coluna escrita com `None` deixam a MESMA
    linha, e é no payload que a chave precisa faltar."""
    enviados: list[dict] = []

    class _Tabela:
        def update(self, payload):
            enviados.append(dict(payload))
            return self

        def eq(self, _coluna, _valor):
            return self

        def execute(self):
            return type("R", (), {"data": [{}]})()

    class _Supabase:
        def table(self, _nome):
            return _Tabela()

    return _Supabase(), enviados


CASO_RESPONDIDO_CRU = {
    "status": "respondido",
    "prazo_area_em": PRAZO_DO_PRIMEIRO_DESPACHO,
    "area_estourou_em": None,
    "respondida_em": T2_DA_RECEPCAO,
    "respondida_por_nome": "Carlos Titular",
}


class TestOPayloadDaDevolucaoNaoMudou:
    """A outra metade do MUST-FIX 1: a limpeza do T2 é opt-in, e a Devolução à
    Ouvidoria (rota PÚBLICA, sem login) continua mandando o payload de sempre.

    É a exigência da review de segurança: mexer no payload de uma rota sem login
    para resolver um problema do painel é risco que não se paga."""

    def test_sem_o_opt_in_o_payload_e_byte_a_byte_o_de_antes(self):
        from app.services import ouvidoria_prorrogacao, ouvidoria_relogio_da_area

        supabase, enviados = _espiar_os_updates()

        parado = ouvidoria_relogio_da_area.parar(
            supabase, "uuid-7", dict(CASO_RESPONDIDO_CRU, status="aguardando_area"), None
        )

        assert enviados == [{"prazo_area_em": None} | ouvidoria_prorrogacao.carimbos_a_zerar()], (
            "o payload da devolução do setor mudou"
        )
        assert "respondida_em" not in enviados[0]
        assert "respondida_por_nome" not in enviados[0]
        assert parado.carimbo_da_resposta_a_restaurar == {}

    def test_com_o_opt_in_as_duas_colunas_do_marco_entram(self):
        from app.services import ouvidoria_relogio_da_area

        supabase, enviados = _espiar_os_updates()

        parado = ouvidoria_relogio_da_area.parar(
            supabase, "uuid-7", dict(CASO_RESPONDIDO_CRU), None, limpar_a_resposta=True
        )

        assert enviados[0]["respondida_em"] is None
        assert enviados[0]["respondida_por_nome"] is None
        # `resposta_da_area` fica FORA do payload: o texto não é o marco.
        assert "resposta_da_area" not in enviados[0]
        assert parado.carimbo_da_resposta_a_restaurar == {
            "respondida_em": T2_DA_RECEPCAO,
            "respondida_por_nome": "Carlos Titular",
        }

    def test_sem_o_opt_in_o_rollback_tambem_nao_toca_o_marco(self):
        from app.services import ouvidoria_relogio_da_area

        supabase, enviados = _espiar_os_updates()
        parado = ouvidoria_relogio_da_area.parar(
            supabase, "uuid-7", dict(CASO_RESPONDIDO_CRU, status="aguardando_area"), None
        )

        ouvidoria_relogio_da_area.restaurar(supabase, "uuid-7", parado)

        assert enviados[-1] == {"prazo_area_em": PRAZO_DO_PRIMEIRO_DESPACHO}


class TestACorridaDaRespostaQueChegaNoMeio:
    """A corrida que a aresta nova destrancou (achado da review do PR #714).

    Antes desta fatia, o caso que mudava de estado entre a leitura e a parada
    era recusado pela RPC, porque `respondido -> em_classificacao` não existia
    no grafo. Com a aresta aberta a RPC ACEITA, e seguir em frente mandaria à
    área nova um caso com o relógio da anterior correndo e a resposta
    recém-chegada intacta. Quem barra agora é o `parar` devolvendo None."""

    def test_o_redirecionamento_aborta_quando_a_area_responde_no_meio(self, monkeypatch, _nunca_envia_email_de_verdade):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        update_de_verdade = _TabelaFake.update

        def _a_area_responde_antes_da_parada(self, payload):
            if self.nome == "ouvidoria_protocolos" and payload.get("prazo_area_em", "?") is None:
                caso = _caso(supabase)
                if caso["status"] == "aguardando_area":
                    # Outra requisição, pelo link do portal, entrou agora.
                    caso["status"] = "respondido"
                    caso.update(dict(CARIMBO_T2_DA_RECEPCAO))
            return update_de_verdade(self, payload)

        monkeypatch.setattr(_TabelaFake, "update", _a_area_responde_antes_da_parada)

        resposta = _redirecionar(client)

        assert resposta.status_code == 409, resposta.text
        assert resposta.json()["detail"] == ouvidoria_router.SAIU_DA_AREA_NO_MEIO
        caso = _caso(supabase)
        assert caso["status"] == "respondido", "o caso saiu da área depois de ter sido respondido"
        assert caso["setor"] == "Recepcao"
        assert caso["prazo_area_em"] == PRAZO_DO_PRIMEIRO_DESPACHO, "o relógio da área parou numa corrida perdida"
        assert caso["respondida_em"] == T2_DA_RECEPCAO, "a resposta recém-chegada foi apagada"
        assert not any(m["estado_novo"] == "em_classificacao" for m in _movimentos(supabase))
        assert _nunca_envia_email_de_verdade == []


class TestFalhaCruaDepoisDaSaida:
    """MUST-FIX 2 da review do PR #714: `except HTTPException` não pegava
    `APIError` nem `httpx`.

    Dentro de `acionar_a_area` há escritas cuja falha não vira `HTTPException`:
    o update da classificação (sem `except`), a RPC de entrada (`except
    APIError` sem `HTTPError`) e o `select` final do Dossiê. Um `ReadTimeout`
    ali escapava cru até o FastAPI, e o ouvidor recebia um 500 sem corpo: nunca
    lia que o caso tinha saído da área antiga."""

    def _com_a_rpc_de_entrada_caindo(self, supabase, monkeypatch, erro: Exception):
        rpc_de_verdade = supabase.rpc

        def _cai_na_entrada(nome, params):
            if params["p_estado_novo"] == "aguardando_area":

                class _Cai:
                    def execute(self):
                        raise erro

                return _Cai()
            return rpc_de_verdade(nome, params)

        monkeypatch.setattr(supabase, "rpc", _cai_na_entrada)

    def test_timeout_na_rpc_de_entrada_vira_a_frase_e_nao_um_500_mudo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """`httpx.ReadTimeout` não é `APIError` e não vira `HTTPException`
        dentro do acionamento: é o tipo exato que escapava cru até o
        `TestClient`."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        self._com_a_rpc_de_entrada_caindo(supabase, monkeypatch, httpx.ReadTimeout("o banco não respondeu"))

        resposta = _redirecionar(client)

        assert resposta.status_code == 500, resposta.text
        assert "Validar e acionar" in resposta.json()["detail"]
        caso = _caso(supabase)
        assert caso["status"] == "em_classificacao"
        saida = next(m for m in _movimentos(supabase) if m["estado_novo"] == "em_classificacao")
        assert saida["observacao"].startswith("Redirecionado pelo ouvidor (de Recepcao)")

    def test_apierror_na_rpc_de_entrada_continua_com_a_frase(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O tipo que já era convertido continua sendo."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        self._com_a_rpc_de_entrada_caindo(
            supabase, monkeypatch, APIError({"code": "57014", "message": "statement timeout"})
        )

        resposta = _redirecionar(client)

        assert resposta.status_code == 500, resposta.text
        assert "Validar e acionar" in resposta.json()["detail"]
        assert _caso(supabase)["status"] == "em_classificacao"

    def test_falha_crua_no_update_da_classificacao_tambem_vira_a_frase(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """A escrita SEM `except` nenhum dentro do acionamento."""
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        update_de_verdade = _TabelaFake.update

        def _cai_na_classificacao(self, payload):
            if self.nome == "ouvidoria_protocolos" and "tipo_manifestacao" in payload:
                raise APIError({"code": "57014", "message": "statement timeout"})
            return update_de_verdade(self, payload)

        monkeypatch.setattr(_TabelaFake, "update", _cai_na_classificacao)

        resposta = _redirecionar(client)

        assert resposta.status_code == 500, resposta.text
        assert "Validar e acionar" in resposta.json()["detail"]
        assert _caso(supabase)["status"] == "em_classificacao"
        assert _nunca_envia_email_de_verdade == []


class TestNenhumaLeituraDepoisDoPontoSemVolta:
    """NIT 3 da review de segurança do PR #714: `carregar_feriados` e
    `carregar_prazo_da_area` rodavam DENTRO do acionamento, ou seja, depois de o
    caso já ter saído da área.

    O que se prova aqui é a ORDEM, e não um código de erro, porque as duas
    leituras são fail-open por desenho (`carregar_prazo` devolve
    `Prazo(valor=None)` em qualquer exceção, e o calendário volta vazio): um
    teste que injetasse falha nelas passaria verde com as leituras em qualquer
    lugar, e seria vácuo. O que a mudança entrega é o invariante auditável
    "depois do ponto sem volta, nenhuma ida ao banco que dê para fazer antes", e
    é ele que esta asserção guarda."""

    def test_a_tabela_de_prazos_e_o_calendario_sao_lidos_antes_da_primeira_escrita(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        client, supabase = _com_o_caso_na_recepcao(monkeypatch, _nunca_envia_email_de_verdade)
        passos: list[str] = []
        select_de_verdade = _TabelaFake.select
        update_de_verdade = _TabelaFake.update

        def _anotar_leitura(self, colunas="*", *a, **kw):
            if self.nome in ("ouvidoria_prazos", "ouvidoria_feriados"):
                passos.append(f"leu {self.nome}")
            return select_de_verdade(self, colunas, *a, **kw)

        def _anotar_escrita(self, payload):
            if self.nome == "ouvidoria_protocolos" and payload.get("prazo_area_em", "?") is None:
                passos.append("parou o relogio")
            return update_de_verdade(self, payload)

        monkeypatch.setattr(_TabelaFake, "select", _anotar_leitura)
        monkeypatch.setattr(_TabelaFake, "update", _anotar_escrita)

        assert _redirecionar(client).status_code == 201

        assert "parou o relogio" in passos, "o teste não exercitou a parada do relógio"
        parada = passos.index("parou o relogio")
        assert "leu ouvidoria_prazos" in passos[:parada], (
            "a tabela de prazos foi lida depois de o caso já ter saído da área"
        )
        assert "leu ouvidoria_feriados" in passos[:parada], (
            "o calendário foi lido depois de o caso já ter saído da área"
        )
        assert "leu ouvidoria_prazos" not in passos[parada:], "sobrou leitura de prazo depois do ponto sem volta"
        assert "leu ouvidoria_feriados" not in passos[parada:], "sobrou leitura do calendário depois do ponto sem volta"
