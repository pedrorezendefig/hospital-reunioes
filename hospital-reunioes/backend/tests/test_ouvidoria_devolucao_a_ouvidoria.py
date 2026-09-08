"""Devolução à Ouvidoria (issue #600, PRD #598, ADR 0048).

A área que recebe um caso que não é dela devolve ao ouvidor pelo próprio link
do email, com motivo obrigatório. O caso volta a `em_classificacao`, o relógio
da área para e o link deixa de valer.

Cobre os critérios de aceite da #600 pelo mesmo seam das fatias anteriores do
portal do setor: HTTP no `TestClient`, com o fake do PostgREST. O Resend nunca
é chamado de verdade.
"""

from __future__ import annotations

import glob
import os
import sys

import httpx
import pytest
from postgrest.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.limiter import limiter  # noqa: E402
from app.routers import ouvidoria_setor as ouvidoria_setor_router  # noqa: E402
from app.services import (  # noqa: E402
    ouvidoria_devolucao_a_ouvidoria,
    ouvidoria_estados,
    ouvidoria_notificacoes,
)
from app.services.ouvidoria_prorrogacao import CARIMBOS_DEPENDENTES_DO_PRAZO  # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))

from test_ouvidoria_portal_setor import (  # noqa: E402
    _acionar,
    _client,
    _TabelaFake,
    _token_do_email,
)

MOTIVO = "Este caso é do Centro Médico: a recepção não agenda consulta de especialidade."

# Dois instantes anteriores ao relógio dos testes do portal (25/08/2026 17:00
# UTC): um é o estouro que o caso já carregava de um ciclo fechado antes, o
# outro é o vencimento que a área fura durante a própria devolução.
ESTOURO_DE_UM_CICLO_ANTERIOR = "2026-08-18T20:00:00+00:00"
PRAZO_QUE_A_AREA_FUROU = "2026-08-21T20:00:00+00:00"

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations")
MIGRATION = "098_ouvidoria_devolucao_a_ouvidoria.sql"


def _ddl(nome: str = MIGRATION) -> str:
    with open(os.path.join(MIGRATIONS_DIR, nome), encoding="utf-8") as f:
        return f.read()


def _migration_vigente_do_check_de_gatilhos() -> str:
    """A migration mais recente que redefine o CHECK de gatilhos. As migrations
    são numeradas, então a ordem alfabética é a cronológica."""
    candidatas = sorted(
        os.path.basename(caminho)
        for caminho in glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql"))
        if "ouvidoria_notificacoes_gatilho_check" in open(caminho, encoding="utf-8").read()
    )
    assert candidatas, "Nenhuma migration define o CHECK de gatilhos das notificações"
    return candidatas[-1]


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi acumula contagem entre arquivos: sem isto, o 429 de outra
    suíte reaparece aqui como falha sem causa."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o `.env` real (Resend de produção). Mesma
    trava do arquivo do portal do setor, no mesmo ponto único."""
    enviados: list[dict] = []

    def _fake(destinatario, assunto, html_content, texto_fallback):
        enviados.append({"destinatario": destinatario, "assunto": assunto, "texto": texto_fallback})
        return True

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)
    return enviados


def _portal_com_caso_na_area(monkeypatch, emails):
    """O caso já acionado e o token que chegou ao titular da Recepção, que é
    onde toda devolução começa.

    O recorte a partir do fim da lista existe porque o mesmo teste pode montar
    dois portais: `_token_do_email` pega o PRIMEIRO email do titular, e o
    segundo portal ficaria com o token do primeiro, que aponta para outro
    banco."""
    ja_enviados = len(emails)
    client, sb = _client(monkeypatch)
    _acionar(client)
    return client, sb, _token_do_email(emails[ja_enviados:])


def _caso_no_banco(sb) -> dict:
    return next(m for m in sb.tabelas["ouvidoria_protocolos"] if m["id"] == "uuid-7")


def _token_no_banco(sb) -> dict:
    return sb.tabelas["ouvidoria_setor_tokens"][0]


class TestArestaDaMaquinaDeEstados:
    """A volta para a fila do ouvidor é transição, não escrita de status por
    fora (ADR 0048, decisão 1)."""

    def test_caso_aguardando_area_pode_voltar_para_em_classificacao(self):
        """Critério: a função pura aceita `aguardando_area -> em_classificacao`."""
        ouvidoria_estados.validar_transicao("aguardando_area", "em_classificacao")

    @pytest.mark.parametrize(
        ("atual", "novo"),
        [
            # O grafo do PRD #318, aresta a aresta, como estava antes desta
            # fatia. Só a linha do `aguardando_area` ganhou destino; qualquer
            # outra porta aberta de brinde aparece aqui.
            ("novo", "em_classificacao"),
            ("em_classificacao", "aguardando_area"),
            ("em_classificacao", "encerrado"),
            ("aguardando_area", "respondido"),
            ("aguardando_area", "encerrado"),
            ("aguardando_area", "aguardando_area"),
            ("aguardando_area", "aguardando_manifestante"),
            ("aguardando_manifestante", "aguardando_area"),
            ("aguardando_manifestante", "encerrado"),
            ("respondido", "encerrado"),
            ("respondido", "aguardando_area"),
            ("encerrado", "aguardando_area"),
        ],
    )
    def test_as_arestas_anteriores_continuam_valendo(self, atual, novo):
        assert novo in ouvidoria_estados.TRANSICOES[atual]

    @pytest.mark.parametrize(
        ("atual", "novo"),
        [
            # As portas que continuam fechadas: só quem esperava a área volta
            # à classificação, e a classificação não vira laço.
            ("em_classificacao", "em_classificacao"),
            ("novo", "aguardando_area"),
            ("aguardando_manifestante", "em_classificacao"),
            ("respondido", "em_classificacao"),
            ("encerrado", "em_classificacao"),
        ],
    )
    def test_nenhuma_outra_porta_para_em_classificacao_abriu(self, atual, novo):
        with pytest.raises(ouvidoria_estados.TransicaoInvalidaError):
            ouvidoria_estados.validar_transicao(atual, novo)

    def test_a_volta_a_classificacao_nao_e_devolucao_por_insuficiencia(self):
        """As duas voltas têm nomes diferentes para atos diferentes (PRD #598,
        história 23). `e_devolucao` decide meio prazo e aviso à área: se ela
        casasse aqui, a devolução da área cairia no fluxo do ouvidor."""
        assert ouvidoria_estados.e_devolucao("aguardando_area", "em_classificacao") is False


class TestDevolverPeloLinkDoEmail:
    """A rota nova do portal do setor, irmã de responder e de pedir prazo."""

    def test_devolucao_com_motivo_leva_o_caso_de_volta_a_classificacao(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """Critério: motivo válido leva o caso a `em_classificacao`, consome o
        link, zera `prazo_area_em` e os carimbos dependentes do prazo, e grava
        o movimento com o prefixo que o Dossiê vai reconhecer."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        caso = _caso_no_banco(sb)
        assert caso["status"] == "aguardando_area"
        assert caso["prazo_area_em"], "o acionamento precisa ter aberto o prazo da área"
        # O caso já andou pelos jobs de prazo: é justamente esse carimbo que
        # deixaria o caso fora da varredura se a devolução não o zerasse.
        for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
            caso[carimbo] = "2026-08-26T12:00:00+00:00"

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["protocolo"] == "2026-0007"
        depois = _caso_no_banco(sb)
        assert depois["status"] == "em_classificacao"
        assert depois["prazo_area_em"] is None
        for carimbo in CARIMBOS_DEPENDENTES_DO_PRAZO:
            assert depois[carimbo] is None, f"{carimbo} ficou preso na fila de um prazo que não existe mais"
        assert _token_no_banco(sb)["usado_em"], "o link continuou valendo depois da devolução"
        movimento = sb.tabelas["ouvidoria_movimentos"][-1]
        assert movimento["estado_anterior"] == "aguardando_area"
        assert movimento["estado_novo"] == "em_classificacao"
        assert movimento["observacao"] == f"Devolvido pela área Recepcao: {MOTIVO}"
        # Autor é quem clicou no link, sem id: o responsável do setor não tem
        # login, como na resposta da área.
        assert movimento["autor_nome"] == "Carlos Titular"
        assert movimento["autor_id"] is None

    def test_a_devolucao_deixa_registro_de_acesso_com_o_nome_do_ato(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Todo acesso ao caso deixa registro (LGPD, ADR 0034), e o ato precisa
        ser distinguível dos irmãos. O `_registrar_acesso` engole toda exceção,
        então sem este teste uma troca de string ali sumiria sem barulho."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 200, resposta.text
        acessos = sb.tabelas["ouvidoria_acessos"]
        registro = next(a for a in acessos if a["acao"] == "portal_setor_devolver")
        assert registro["manifestacao_id"] == "uuid-7"
        assert registro["ator_id"] is None, "o responsável do setor não tem login"
        assert registro["ator_nome"] == "Carlos Titular (portal do setor)"

    def test_o_compromisso_com_o_manifestante_nao_e_tocado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: `prazo_conclusivo_em` fica intocado. Ele é o T0 até T3, o
        que foi prometido a quem reclamou, e não depende de qual área está com
        o caso."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _caso_no_banco(sb)["prazo_conclusivo_em"] = "2026-09-15T20:00:00+00:00"

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 200, resposta.text
        assert _caso_no_banco(sb)["prazo_conclusivo_em"] == "2026-09-15T20:00:00+00:00"


class TestAMigration:
    """O banco guarda a mesma regra que o Python (migration 064 em diante):
    contornar a API não pode contornar a máquina de estados."""

    def test_a_aresta_da_devolucao_entra_na_funcao_do_banco(self):
        ddl = _ddl()
        assert "CREATE OR REPLACE FUNCTION ouvidoria_transicionar" in ddl
        aresta = next(linha for linha in ddl.splitlines() if "v_atual = 'aguardando_area'" in linha)
        assert "'em_classificacao'" in aresta

    def test_o_grafo_recriado_carrega_todas_as_arestas_anteriores(self):
        """`CREATE OR REPLACE` substitui o corpo inteiro: uma aresta esquecida
        aqui trava em produção um caminho que hoje funciona."""
        ddl = _ddl()
        for atual, destinos in ouvidoria_estados.TRANSICOES.items():
            linha = next(linha for linha in ddl.splitlines() if f"v_atual = '{atual}'" in linha)
            for destino in destinos:
                assert f"'{destino}'" in linha, f"O banco não deixa ir de {atual} para {destino}"

    def test_o_gatilho_do_aviso_entra_no_check_vigente(self):
        """Critério: o gatilho entra agora para a fatia do aviso não precisar
        de outra migration. O CHECK é recriado inteiro, então a lista precisa
        carregar também os gatilhos que já existem.

        A lista completa é cobrada na migration VIGENTE, não na 098: fixar o
        número aqui seria a mesma trava que este PR tirou do teste do aviso de
        encerramento, e a próxima fatia que mexer no CHECK derrubaria isto sem
        ter quebrado nada. O que é da 098 é o gatilho que ela criou, e esse sim
        é cobrado nela."""
        ddl_vigente = _ddl(_migration_vigente_do_check_de_gatilhos())
        for gatilho in ouvidoria_notificacoes.GATILHOS:
            assert f"'{gatilho}'" in ddl_vigente, f"O CHECK vigente não cobre o gatilho {gatilho}"
        assert "'devolvido_a_ouvidoria'" in ddl_vigente
        assert "'devolvido_a_ouvidoria'" in _ddl(), "a migration desta fatia deixou de trazer o gatilho que ela criou"

    def test_a_rpc_nao_fica_ao_alcance_da_chave_do_bundle(self):
        """O `PUBLIC` no REVOKE não é enfeite: no banco em que a função nascer
        nesta migration, o Postgres concede EXECUTE a PUBLIC no nascimento, e
        `anon` (a chave do bundle do frontend) herda por ali mesmo com o revoke
        nominal. Mesma forma da 095 e da 097."""
        revoke = next(linha for linha in _ddl().splitlines() if linha.startswith("  FROM "))
        assert revoke.strip() == "FROM PUBLIC, anon, authenticated;"

    def test_a_troca_do_check_vai_numa_transacao(self):
        """Roda à mão em produção: a tabela não pode ficar sem constraint se a
        segunda metade falhar."""
        ddl = _ddl()
        assert "BEGIN;" in ddl and "COMMIT;" in ddl
        assert "DROP CONSTRAINT IF EXISTS ouvidoria_notificacoes_gatilho_check" in ddl

    def test_a_devolucao_nao_cria_tabela_nem_coluna(self):
        """O motivo vive na trilha (ADR 0048): tabela nova aqui seria um lugar
        a mais para a Retenção varrer."""
        ddl = _ddl()
        assert "CREATE TABLE" not in ddl.upper()
        assert "ADD COLUMN" not in ddl.upper()


class TestOMotivoEObrigatorio:
    """Nenhum caso volta ao ouvidor sem explicação (PRD #598, história 4)."""

    @pytest.mark.parametrize(
        "motivo",
        [
            "",
            "   ",
            "\n\t ",
            # Os de largura zero, que o `strip` NÃO enxerga: `"​".isspace()`
            # é False. Sem a peneira de invisíveis, este corpo devolvia 200,
            # queimava o link de uso único e gravava na trilha imutável um
            # motivo que o ouvidor não consegue ler nem pedir de novo.
            "​​​",
            "﻿ ‍",
        ],
        ids=["vazio", "so-espaco", "so-branco", "largura-zero", "invisivel-com-espaco"],
    )
    def test_motivo_em_branco_e_recusado_e_o_link_continua_valendo(
        self, monkeypatch, _nunca_envia_email_de_verdade, motivo
    ):
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": motivo})

        assert resposta.status_code == 422, resposta.text
        assert _caso_no_banco(sb)["status"] == "aguardando_area"
        assert _token_no_banco(sb).get("usado_em") is None, "motivo recusado queimou o link do titular"

    def test_motivo_acima_do_teto_e_recusado(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O texto vai para a trilha imutável: acima de 10.000 caracteres ele
        deixaria o Dossiê daquele caso impossível de abrir."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        no_teto = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": "a" * 10_000})
        assert no_teto.status_code == 200, no_teto.text

        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        passou = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": "a" * 10_001})

        assert passou.status_code == 422, passou.text
        assert _caso_no_banco(sb)["status"] == "aguardando_area"

    def test_a_recusa_do_teto_e_a_frase_que_a_tela_repete(self):
        """A tela espelha esta frase (`avisoDoTetoDoMotivo` em `setor.ts`) para
        não ensinar uma saída diferente da que o servidor ensinaria. As duas
        pontas são presas aqui: trocar o texto de um lado só derruba este teste
        ou o irmão do vitest, nunca passa em silêncio."""
        assert ouvidoria_devolucao_a_ouvidoria.RECUSA_LONGA == (
            "O motivo passou de 10.000 caracteres. Resuma por que o caso não é da sua área."
        )
        assert ouvidoria_devolucao_a_ouvidoria.MAXIMO_DE_CARACTERES == 10_000

    def test_travessao_do_motivo_e_sanitizado_antes_de_entrar_na_trilha(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """ADR 0013: o travessão não chega ao Dossiê nem ao PDF. A régua é o
        marcador que o sanitizador deixa, e não a ausência do caractere: o
        texto poderia ter sido cortado inteiro e o teste continuaria verde."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)

        resposta = client.post(
            f"/api/ouvidoria-setor/{token}/devolver",
            json={"motivo": "Não é da recepção — é do Centro Médico."},
        )

        assert resposta.status_code == 200, resposta.text
        observacao = sb.tabelas["ouvidoria_movimentos"][-1]["observacao"]
        assert "recepção, é do Centro Médico." in observacao
        assert "—" not in observacao


class TestPortasFechadas:
    """O link é de uso único e só vale enquanto o caso espera a área."""

    def test_link_ja_usado_devolve_410_e_nada_muda(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: a mesma pessoa não devolve duas vezes o mesmo caso."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        primeira = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})
        assert primeira.status_code == 200, primeira.text
        movimentos = len(sb.tabelas["ouvidoria_movimentos"])

        segunda = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": "Segunda tentativa."})

        assert segunda.status_code == 410, segunda.text
        assert len(sb.tabelas["ouvidoria_movimentos"]) == movimentos, "a segunda devolução entrou na trilha"

    @pytest.mark.parametrize("estado", ["aguardando_manifestante", "respondido", "encerrado"])
    def test_caso_que_a_ouvidoria_ja_movimentou_nao_aceita_devolucao(
        self, monkeypatch, _nunca_envia_email_de_verdade, estado
    ):
        """Critério: fora de `aguardando_area` a resposta é 410, e o link NÃO
        é consumido. Queimar o link de um caso que a Ouvidoria pausou deixaria
        a área sem porta quando o caso voltasse para ela."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _caso_no_banco(sb)["status"] = estado

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 410, resposta.text
        assert _caso_no_banco(sb)["status"] == estado
        assert _token_no_banco(sb).get("usado_em") is None, "o link do titular foi queimado por um caso que andou"


class TestFalhaEntreOClaimEATransicao:
    """A janela em que o link já foi consumido e o caso ainda não andou."""

    def test_recusa_da_rpc_devolve_o_link_e_o_prazo_da_area(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério: falha na RPC devolve o link, no mesmo desenho das rotas
        irmãs. O caso continua com a área, então o relógio dela também volta:
        sem isso, o caso ficaria em `aguardando_area` sem vencimento, fora da
        véspera, da cobrança e da escada."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        prazo = _caso_no_banco(sb)["prazo_area_em"]
        sb.rpc_recusa = APIError({"message": "Transicao invalida", "code": "23514"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        assert _token_no_banco(sb).get("usado_em") is None, "o titular ficou trancado para fora do próprio link"
        depois = _caso_no_banco(sb)
        assert depois["status"] == "aguardando_area"
        assert depois["prazo_area_em"] == prazo

        # E o link devolvido serve mesmo: a segunda tentativa devolve o caso.
        de_novo = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})
        assert de_novo.status_code == 200, de_novo.text
        assert _caso_no_banco(sb)["status"] == "em_classificacao"

    def test_caso_que_sai_da_area_entre_a_leitura_e_o_update_nao_perde_o_vencimento(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """A janela entre `_carregar_caso` (que leu `aguardando_area`) e o
        update que para o relógio são duas idas ao PostgREST. Se a Ouvidoria
        pausar o caso no meio, zerar o prazo às cegas o deixaria sem vencimento
        para sempre: a restauração depois filtra por `aguardando_area` e não
        casa, e os dois jobs de prazo filtram por `.lte("prazo_area_em", ...)`,
        que descarta NULL. O caso sairia da cobrança e do escalonamento em
        silêncio. Mesma prova do `_restaurar_prazo`, três linhas acima."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        prazo = _caso_no_banco(sb)["prazo_area_em"]
        consumir_de_verdade = ouvidoria_setor_router.ouvidoria_setor_tokens.consumir

        def _pausa_no_meio(supabase, vinculo, agora):
            claim = consumir_de_verdade(supabase, vinculo, agora)
            # A Ouvidoria pausou o caso agora mesmo, por outra requisição.
            _caso_no_banco(sb)["status"] = "aguardando_manifestante"
            return claim

        monkeypatch.setattr(ouvidoria_setor_router.ouvidoria_setor_tokens, "consumir", _pausa_no_meio)
        # E o banco recusa a transição, como recusaria de verdade: o grafo não
        # tem `aguardando_manifestante -> em_classificacao`.
        sb.rpc_recusa = APIError({"message": "Transicao invalida", "code": "23514"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        depois = _caso_no_banco(sb)
        assert depois["status"] == "aguardando_manifestante"
        assert depois["prazo_area_em"] == prazo, "o caso pausado perdeu o vencimento e sumiu da cobrança"

    def test_timeout_depois_da_transicao_nao_reabre_o_link_nem_o_prazo(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """O `ReadTimeout` não prova que o Postgres deixou de executar. Aqui a
        transição COMMITOU e a resposta não voltou: devolver o link reabriria a
        leitura do relato integral e da identificação de quem manifestou pelo
        resto dos 30 dias do token, e restaurar o prazo mandaria a cobrança
        atrás de uma área que já devolveu o caso."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        sb.rpc_falha_depois_do_efeito = httpx.ReadTimeout("o banco não respondeu no tempo")

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        assert _token_no_banco(sb)["usado_em"], "o link voltou a valer para um caso que já saiu da área"
        depois = _caso_no_banco(sb)
        assert depois["status"] == "em_classificacao"
        assert depois["prazo_area_em"] is None


def _payloads_de_update(monkeypatch) -> list[tuple[str, dict]]:
    """Cada update que a rota manda ao PostgREST daqui em diante, com o payload
    exatamente como ele saiu.

    O banco não responde a pergunta desta seção: coluna nunca escrita e coluna
    escrita com `None` deixam a MESMA linha. Quem separa as duas é o payload, e
    é nele que a chave precisa faltar."""
    gravados: list[tuple[str, dict]] = []
    update_de_verdade = _TabelaFake.update

    def _espiar(self, payload: dict):
        gravados.append((self.nome, dict(payload)))
        return update_de_verdade(self, payload)

    monkeypatch.setattr(_TabelaFake, "update", _espiar)
    return gravados


def _updates_do_caso(gravados: list[tuple[str, dict]]) -> list[dict]:
    """Só os updates da manifestação, na ordem: a devolução do link mexe na
    tabela dos tokens e não conta aqui."""
    return [payload for nome, payload in gravados if nome == "ouvidoria_protocolos"]


class TestOCarimboDoEstouroNoRollback:
    """O rollback do prazo desfaz o que a ida escreveu, e nada além (issue #623).

    `area_estourou_em` não tem dono exclusivo nesta rota: a devolução por
    insuficiência grava a mesma coluna sem filtrar status. Por isso o que se
    prova aqui é a AUSÊNCIA da chave no payload, e não o valor no banco:
    mandar a chave com `None` é escrita cega sobre um carimbo que esta
    requisição não decidiu apagar, o mesmo apagão que a ida já evita e que o
    `except` repetia."""

    def test_rollback_de_caso_que_nao_estourou_nao_toca_o_carimbo(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 1: sem carimbo a restaurar, a chave não entra no update."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        gravados = _payloads_de_update(monkeypatch)
        sb.rpc_recusa = APIError({"message": "Transicao invalida", "code": "23514"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        ida, rollback = _updates_do_caso(gravados)
        assert "area_estourou_em" not in ida, "a ida carimbou estouro num caso dentro do prazo"
        assert "area_estourou_em" not in rollback, "o rollback apagou às cegas um carimbo que não era dele"

    def test_rollback_de_caso_ja_estourado_devolve_o_carimbo_de_antes(self, monkeypatch, _nunca_envia_email_de_verdade):
        """Critério 1, o outro lado: quando a ida reescreveu o carimbo que já
        estava lá, o rollback devolve aquele mesmo instante. O primeiro estouro
        do caso é o que `cumprimento_da_area` lê, e ele não pode andar."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _caso_no_banco(sb)["area_estourou_em"] = ESTOURO_DE_UM_CICLO_ANTERIOR
        gravados = _payloads_de_update(monkeypatch)
        sb.rpc_recusa = APIError({"message": "Transicao invalida", "code": "23514"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        ida, rollback = _updates_do_caso(gravados)
        assert ida["area_estourou_em"] == ESTOURO_DE_UM_CICLO_ANTERIOR
        assert rollback["area_estourou_em"] == ESTOURO_DE_UM_CICLO_ANTERIOR
        assert _caso_no_banco(sb)["area_estourou_em"] == ESTOURO_DE_UM_CICLO_ANTERIOR

    def test_rollback_apaga_o_carimbo_que_a_propria_ida_acabou_de_gravar(
        self, monkeypatch, _nunca_envia_email_de_verdade
    ):
        """A guarda do #607, no caso em que a condicional mais aperta: a área
        furou o prazo NESTA devolução, a ida carimbou o estouro e a transição
        não entrou. Como o prazo volta, o carimbo tem que voltar junto: prazo
        restaurado com estouro gravado deixa o caso `estourado` para sempre,
        fora do alcance de qualquer prorrogação aprovada depois."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _caso_no_banco(sb)["prazo_area_em"] = PRAZO_QUE_A_AREA_FUROU
        gravados = _payloads_de_update(monkeypatch)
        sb.rpc_recusa = APIError({"message": "Transicao invalida", "code": "23514"})

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 409, resposta.text
        ida, rollback = _updates_do_caso(gravados)
        assert ida["area_estourou_em"] == PRAZO_QUE_A_AREA_FUROU, "a ida não carimbou o prazo furado"
        assert rollback["area_estourou_em"] is None
        depois = _caso_no_banco(sb)
        assert depois["prazo_area_em"] == PRAZO_QUE_A_AREA_FUROU
        assert depois["area_estourou_em"] is None, "o caso ficou estourado por uma devolução que nunca entrou"

    def test_devolucao_que_entra_deixa_o_carimbo_do_estouro_de_pe(self, monkeypatch, _nunca_envia_email_de_verdade):
        """O contraste: sem falha na RPC não há rollback nenhum, e o estouro
        consumado do ciclo que acabou fica gravado, que é o que a memória de
        ciclos do #374 promete."""
        client, sb, token = _portal_com_caso_na_area(monkeypatch, _nunca_envia_email_de_verdade)
        _caso_no_banco(sb)["prazo_area_em"] = PRAZO_QUE_A_AREA_FUROU
        gravados = _payloads_de_update(monkeypatch)

        resposta = client.post(f"/api/ouvidoria-setor/{token}/devolver", json={"motivo": MOTIVO})

        assert resposta.status_code == 200, resposta.text
        (ida,) = _updates_do_caso(gravados)
        assert ida["prazo_area_em"] is None
        assert ida["area_estourou_em"] == PRAZO_QUE_A_AREA_FUROU
        depois = _caso_no_banco(sb)
        assert depois["status"] == "em_classificacao"
        assert depois["area_estourou_em"] == PRAZO_QUE_A_AREA_FUROU
