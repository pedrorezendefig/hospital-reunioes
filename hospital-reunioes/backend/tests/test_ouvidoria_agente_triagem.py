"""O agente de triagem da Ouvidoria (issue #1624, PRD #1527, ADR 0087).

Logo depois da chegada de toda manifestação e de toda avaliação com
comentário, o relato pseudonimizado vai ao modelo, uma vez, e o agente devolve
o assunto de uma linha, o apontamento ao Núcleo de Segurança do Paciente com
as duas justificativas e, na avaliação, a marca Para revisar com o motivo. Só
sugere: nunca grava tipo, gravidade, sigilo nem área. Se falhar, ou se o teto
de 300 chamadas por dia acabou, o caso entra normal, sem assunto e sem alerta.

Os testes sobem a rota real com o banco falso do formulário público e o
cliente da Anthropic simulado (`ClienteFalso`): nada chega à IA de verdade.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from anthropic_apoio import ClienteFalso  # noqa: E402
from test_ouvidoria_avaliacao import CODIGO, ROTA_AVALIACAO, _BancoComAvaliacoes, _QueryComAvaliacoes  # noqa: E402
from test_ouvidoria_formulario_publico import _make_app  # noqa: E402

from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import ouvidoria_agente_triagem  # noqa: E402

ROTA_MANIFESTACAO = "/api/ouvidoria/publico/manifestacoes"

RELATO_DE_QUEDA = (
    "Minha mãe Maria Aparecida Souza caiu do leito no quarto 204 na madrugada de ontem "
    "porque a grade estava abaixada, e ninguém veio quando apertamos a campainha. "
    "Meu CPF é 123.456.789-09."
)

RESPOSTA_COM_NUCLEO = json.dumps(
    {
        "assunto": "Queda do leito com grade abaixada na internação",
        "nsp_sugerido": True,
        "nsp_justificativa_simples": "Relata queda do paciente do leito, um incidente com a assistência.",
        "nsp_justificativa_tecnica": "Queda do leito; internação, quarto 204; madrugada; dano potencial.",
    }
)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _Banco(_BancoComAvaliacoes):
    """O banco do formulário público e da avaliação, mais o update do caso e a
    reserva da cota diária do agente (a função da migration 143)."""

    def __init__(self, *, cota_livre: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.cota_livre = cota_livre
        self.reservas = 0
        self.updates_do_caso: list[dict] = []

    def reservar(self, nome: str, params: dict):
        assert nome == "ouvidoria_agente_reservar_chamada"
        assert params == {"p_teto": 300}
        self.reservas += 1
        return [{"reservada": self.cota_livre}]


class _QueryDoAgente(_QueryComAvaliacoes):
    def execute(self):
        if self._tabela == "ouvidoria_protocolos" and self._pending_update is not None:
            # O carimbo do acuse também é update do caso; o teste lê só o resto.
            if not any(coluna.startswith("acuse") for coluna in self._pending_update):
                self._banco.updates_do_caso.append(dict(self._pending_update))
            alvo = [r for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
            for linha in alvo:
                linha.update(self._pending_update)
            return type("R", (), {"data": [dict(r) for r in alvo]})()
        return super().execute()


def _app(banco: _Banco | None = None):
    banco = banco or _Banco()
    client, _ = _make_app(banco)

    class _Supabase:
        def table(self, name: str):
            return _QueryDoAgente(banco, name)

        def rpc(self, nome: str, params: dict):
            return type("Rpc", (), {"execute": lambda _self: type("R", (), {"data": banco.reservar(nome, params)})()})()

    client.app.dependency_overrides[get_supabase_client] = _Supabase
    return client, banco


@pytest.fixture
def modelo(monkeypatch):
    """O cliente da Anthropic simulado. O teste troca `modelo.texto` para mudar
    o que o agente responde."""
    cliente = ClienteFalso(RESPOSTA_COM_NUCLEO)
    monkeypatch.setattr(ouvidoria_agente_triagem, "_cliente", lambda: cliente)
    return cliente


def _enviar(client, relato: str = RELATO_DE_QUEDA):
    return client.post(ROTA_MANIFESTACAO, json={"relato": relato, "sobre": "mim"})


def _texto_enviado(cliente: ClienteFalso) -> str:
    (chamada,) = cliente.chamadas
    return json.dumps(chamada["messages"], ensure_ascii=False) + (chamada.get("system") or "")


class TestAChegadaGravaAssuntoENucleo:
    """Critério 1: com o cliente simulado, a chegada grava o assunto e, quando
    for o caso, a sugestão do Núcleo com as duas justificativas."""

    def test_a_manifestacao_publica_chega_com_assunto_e_apontamento_ao_nucleo(self, modelo):
        client, banco = _app()

        r = _enviar(client)

        assert r.status_code == 201
        caso = banco.rows[0]
        assert caso["assunto"] == "Queda do leito com grade abaixada na internação"
        assert caso["nsp_sugerido"] is True
        assert caso["nsp_justificativa_simples"] == (
            "Relata queda do paciente do leito, um incidente com a assistência."
        )
        assert caso["nsp_justificativa_tecnica"] == (
            "Queda do leito; internação, quarto 204; madrugada; dano potencial."
        )
        assert modelo.chamadas[0]["model"] == "claude-sonnet-5-5"

    def test_relato_que_nao_e_do_nucleo_ganha_so_o_assunto(self, modelo):
        modelo.texto = json.dumps(
            {"assunto": "Demora na recepção", "nsp_sugerido": False, "nsp_justificativa_simples": None}
        )
        client, banco = _app()

        _enviar(client, "Esperei duas horas na recepção sem informação nenhuma.")

        caso = banco.rows[0]
        assert caso["assunto"] == "Demora na recepção"
        assert caso.get("nsp_sugerido") is not True
        assert banco.updates_do_caso == [{"assunto": "Demora na recepção"}]

    def test_apontamento_sem_as_duas_justificativas_nao_acende_o_alerta(self, modelo):
        modelo.texto = json.dumps(
            {"assunto": "Queda na internação", "nsp_sugerido": True, "nsp_justificativa_simples": "Queda."}
        )
        client, banco = _app()

        _enviar(client)

        assert banco.updates_do_caso == [{"assunto": "Queda na internação"}]


class TestOModeloLeOTextoPseudonimizado:
    """Critério 2: o texto enviado ao modelo é o pseudonimizado."""

    def test_nome_e_cpf_do_relato_nao_saem_do_app(self, modelo):
        client, _banco = _app()

        _enviar(client)

        enviado = _texto_enviado(modelo)
        assert "Maria Aparecida Souza" not in enviado
        assert "123.456.789-09" not in enviado
        assert "[NOME]" in enviado
        assert "[CPF]" in enviado
        assert "caiu do leito no quarto 204" in enviado

    def test_nome_que_o_modelo_escreva_no_assunto_vira_marcador(self, modelo):
        modelo.texto = json.dumps({"assunto": "Queda da paciente Maria Aparecida Souza", "nsp_sugerido": False})
        client, banco = _app()

        _enviar(client)

        assert banco.rows[0]["assunto"] == "Queda da paciente [NOME]"


class TestFalhaETetoNaoTravamOCaso:
    """Critério 3: falha do modelo e teto estourado deixam o caso sem assunto e
    sem alerta, e o envio público responde normal."""

    def test_modelo_fora_do_ar_deixa_o_caso_sem_assunto_e_o_envio_responde(self, modelo):
        modelo.texto = RuntimeError("API fora do ar")
        client, banco = _app()

        r = _enviar(client)

        assert r.status_code == 201
        assert r.json()["protocolo"] == "2026-0001"
        caso = banco.rows[0]
        assert caso.get("assunto") is None
        assert caso.get("nsp_sugerido") is not True
        assert banco.updates_do_caso == []
        assert banco.movimentos[-1]["autor_nome"] == "Agente de triagem"
        assert banco.movimentos[-1]["observacao"] == "Assunto não gerado: o agente de triagem não respondeu."

    def test_resposta_que_nao_e_json_conta_como_falha(self, modelo):
        modelo.texto = "Não consigo ajudar com isso."
        client, banco = _app()

        r = _enviar(client)

        assert r.status_code == 201
        assert banco.updates_do_caso == []
        assert banco.movimentos[-1]["observacao"] == "Assunto não gerado: o agente de triagem não respondeu."

    def test_teto_do_dia_estourado_nao_chama_o_modelo(self, modelo):
        client, banco = _app(_Banco(cota_livre=False))

        r = _enviar(client)

        assert r.status_code == 201
        assert modelo.chamadas == []
        assert banco.updates_do_caso == []
        assert banco.movimentos[-1]["observacao"] == (
            "Assunto não gerado: o limite de 300 leituras por dia foi atingido."
        )

    def test_cada_caso_gasta_uma_chamada_da_cota(self, modelo):
        client, banco = _app()

        _enviar(client)
        _enviar(client, "Outro relato sobre a recepção.")

        assert banco.reservas == 2
        assert len(modelo.chamadas) == 2


class TestOAgenteSoSugere:
    """Critério 4: a saída do agente nunca altera tipo, gravidade, sigilo ou
    área."""

    def test_campos_de_classificacao_na_resposta_sao_ignorados(self, modelo):
        modelo.texto = json.dumps(
            {
                "assunto": "Queda do leito",
                "nsp_sugerido": False,
                "tipo_manifestacao": "elogio",
                "gravidade": "baixa",
                "sigilo_reforcado": False,
                "setor": "Recepção",
                "categoria": "Elogio",
                "status": "encerrado",
            }
        )
        client, banco = _app()

        _enviar(client)

        assert banco.updates_do_caso == [{"assunto": "Queda do leito"}]
        caso = banco.rows[0]
        assert caso["sigilo_reforcado"] is True
        assert caso["status"] == "em_classificacao"
        assert caso.get("tipo_manifestacao") is None
        assert caso.get("gravidade") is None


class TestParaRevisarNaAvaliacao:
    """Critério 5: avaliação com comentário grave recebe Para revisar com
    motivo; sem comentário, o agente não é chamado."""

    def test_comentario_grave_marca_para_revisar_com_motivo(self, modelo):
        modelo.texto = json.dumps({"revisar": True, "revisar_motivo": "Relata agressão de um funcionário."})
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json={"nota": 4, "comentario": "O segurança empurrou meu pai na porta."})

        assert r.status_code == 201
        avaliacao = banco.avaliacoes[0]
        assert avaliacao["revisar"] is True
        assert avaliacao["revisar_motivo"] == "Relata agressão de um funcionário."
        assert "O segurança empurrou meu pai" in _texto_enviado(modelo)

    def test_comentario_comum_nao_marca(self, modelo):
        modelo.texto = json.dumps({"revisar": False, "revisar_motivo": None})
        client, banco = _app()

        client.post(ROTA_AVALIACAO, json={"nota": 5, "comentario": "Equipe muito atenciosa."})

        assert banco.avaliacoes[0].get("revisar") is not True
        assert len(modelo.chamadas) == 1

    def test_nota_sem_comentario_nao_chama_o_agente(self, modelo):
        client, banco = _app()

        r = client.post(ROTA_AVALIACAO, json={"nota": 2, "motivos": ["tempo_espera"]})

        assert r.status_code == 201
        assert modelo.chamadas == []
        assert banco.reservas == 0

    def test_o_comentario_vai_pseudonimizado(self, modelo):
        modelo.texto = json.dumps({"revisar": False})
        client, _banco = _app()

        client.post(ROTA_AVALIACAO, json={"nota": 1, "comentario": "A enfermeira Joana Ribeiro gritou comigo."})

        assert "Joana Ribeiro" not in _texto_enviado(modelo)


@pytest.fixture
def agendados(monkeypatch) -> list[dict]:
    """Os casos que as rotas puseram na fila do agente."""
    casos: list[dict] = []
    monkeypatch.setattr(ouvidoria_agente_triagem, "agendar_caso", lambda _t, _sb, caso: casos.append(caso))
    return casos


class TestTodoCanalPassaPeloAgente:
    """A chegada de toda manifestação, de qualquer canal, passa pelo agente
    (ADR 0087, decisão 1): o balcão do ouvidor e a Ana, além do canal aberto."""

    def test_o_registro_do_balcao_vai_ao_agente(self, monkeypatch, agendados):
        from test_ouvidoria_registro_manual import OUVIDOR, REGISTRO
        from test_ouvidoria_registro_manual import _client as cliente_manual

        client, _supabase = cliente_manual(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/manifestacoes", json=REGISTRO)

        assert r.status_code == 201
        assert [caso["relato_integral"] for caso in agendados] == [REGISTRO["relato_integral"]]

    def test_o_protocolo_da_ana_vai_ao_agente(self, monkeypatch, agendados):
        from test_ana_ouvidoria_protocolos import CHAVE_CORRETA, _payload_valido
        from test_ana_ouvidoria_protocolos import _make_app as app_da_ana

        from app.config import settings

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = app_da_ana()

        r = client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert [caso["protocolo"] for caso in agendados] == [r.json()["protocolo"]]


class TestAFilaMostraOAssunto:
    """Critério 6 (lado do servidor): a fila da Ouvidoria traz o assunto, e o
    nome do paciente não viaja na linha."""

    def test_a_ouvidoria_le_o_assunto_na_fila_sem_o_paciente(self, monkeypatch):
        from test_ouvidoria_sigilo import OUVIDOR, _client, _manifestacao, _SupabaseFake

        caso = _manifestacao(7, assunto="Queda do leito na internação", paciente_nome="José Pereira Lima")
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        resposta = client.get("/api/ouvidoria/protocolos")

        linha = resposta.json()["protocolos"][0]
        assert linha["assunto"] == "Queda do leito na internação"
        assert "José Pereira Lima" not in resposta.text

    def test_caso_sem_assunto_chega_com_o_assunto_vazio(self, monkeypatch):
        from test_ouvidoria_sigilo import OUVIDOR, _client, _manifestacao, _SupabaseFake

        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_manifestacao(7)]))

        linha = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert "assunto" in linha
        assert linha["assunto"] is None

    def test_quem_esta_fora_da_ouvidoria_nao_recebe_o_assunto(self, monkeypatch):
        from test_ouvidoria_sigilo import SECRETARIA, _client, _manifestacao, _SupabaseFake

        caso = _manifestacao(7, tipo_manifestacao="reclamacao", assunto="Demora na recepção")
        client, _ = _client(monkeypatch, SECRETARIA, _SupabaseFake([caso]))

        resposta = client.get("/api/ouvidoria/protocolos")

        assert "assunto" not in resposta.json()["protocolos"][0]
        assert "Demora na recepção" not in resposta.text
