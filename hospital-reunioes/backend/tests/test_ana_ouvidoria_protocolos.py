"""Testes da ouvidoria ponta a ponta na API da Ana (issue #290, ADR 0031 decisões 5 e 7).

Cobre (critérios de aceite):
- Dois registros seguidos recebem números sequenciais no formato ANO-NNNN,
  gerados pelo banco (a aplicação nunca compõe o número).
- Registro sem campo crítico é recusado pela API (e pelo banco, via contrato
  da migration, se a API for contornada).
- A consulta devolve o protocolo registrado; schema e respostas sem nome,
  CPF nem relato (índice, não dossiê).
- Import do NocoDB: a sequence continua do último número usado.
"""

from __future__ import annotations

import os
import re
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ana as ana_router  # noqa: E402
from app.services.ouvidoria_taxonomia import SETOR_PENDENTE  # noqa: E402

CHAVE_CORRETA = "chave-teste-ana-para-pytest"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _BancoOuvidoriaFake:
    """Simula o comportamento do banco (migrations 063 e 064): quem numera e
    formata o protocolo é o Postgres (sequence + coluna gerada), nunca a
    aplicação; as colunas do Dossiê nascem com o default e só mudam pelo que o
    insert mandou."""

    def __init__(self, proximo_numero: int = 1, data_abertura: str = "2026-08-14"):
        self._proximo_numero = proximo_numero
        self._data_abertura = data_abertura
        self.rows: list[dict] = []
        # O que a API mandou gravar, coluna a coluna (o insert cru).
        self.inserts: list[dict] = []

    def inserir(self, payload: dict) -> dict:
        ano = self._data_abertura[:4]
        row = {
            "id": f"uuid-{self._proximo_numero}",
            "numero": self._proximo_numero,
            "protocolo": f"{ano}-{self._proximo_numero:04d}",
            "data_abertura": self._data_abertura,
            "prazo_resposta": "2026-08-21",
            # Default da migration 064: toda manifestacao nasce aguardando a
            # classificacao do ouvidor. Nenhum processo automatico despacha.
            "status": "em_classificacao",
            "conversa_id": "",
            # Defaults da migration 064: o Dossiê chega vazio e o caso nasce
            # com dados incompletos, para o ouvidor completar na validação.
            "relato_integral": None,
            "manifestante_nome": None,
            "manifestante_contato": None,
            "manifestante_vinculo": None,
            "anonimo": False,
            # Default da migration 077: o caso nasce SEM tipo, isto é, não
            # classificado. É a API que decide o sigilo a partir disso.
            "tipo_manifestacao": None,
            "sigilo_reforcado": False,
            "dados_incompletos": True,
            "classificacao_ia": None,
            "desfecho": None,
            "desfecho_descricao": None,
        }
        # O banco grava o que veio no insert, sem opinião: é a API que decide
        # quais colunas entram.
        row.update(payload)
        self._proximo_numero += 1
        self.inserts.append(dict(payload))
        self.rows.append(row)
        return row


class _Query:
    def __init__(self, banco: _BancoOuvidoriaFake):
        self._banco = banco
        self._filters: dict = {}
        self._pending_insert: dict | None = None
        self._colunas: list[str] | None = None

    def select(self, *args, **_kwargs):
        # O PostgREST projeta no servidor: a consulta só recebe as colunas
        # pedidas, mesmo que a tabela tenha o Dossiê inteiro.
        if args and isinstance(args[0], str):
            self._colunas = [c.strip() for c in args[0].split(",")]
        return self

    def insert(self, payload: dict):
        self._pending_insert = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, *_args, **_kwargs):
        return self

    def execute(self):
        if self._pending_insert is not None:
            # O insert devolve a row inteira, projeção nenhuma: é a API que
            # fecha a resposta no índice.
            data = [self._banco.inserir(self._pending_insert)]
        else:
            data = [dict(r) for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
            if self._colunas is not None:
                data = [{c: row.get(c) for c in self._colunas} for row in data]
        return type("R", (), {"data": data})()


SETORES_ATIVOS = ["Recepcao", "Enfermagem"]


class _QuerySetores:
    """A tabela `setores` do jeito que a resolução a lê: só os ativos, por nome."""

    def __init__(self, nomes: list[str]):
        self._nomes = nomes

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("R", (), {"data": [{"nome": nome} for nome in sorted(self._nomes)]})()


def _make_app(banco: _BancoOuvidoriaFake | None = None) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ana_router.router, prefix="/api")

    banco = banco or _BancoOuvidoriaFake()

    class _SupabaseMock:
        def table(self, name: str):
            # A taxonomia da casa: desde a issue #419 o setor que a Ana escreve
            # é resolvido contra ela antes do insert. Área fora da lista não
            # recusa o registro, vira o marcador de pendente.
            if name == "setores":
                return _QuerySetores(SETORES_ATIVOS)
            assert name == "ouvidoria_protocolos", f"Tabela inesperada: {name}"
            return _Query(banco)

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    return TestClient(app)


def _classificado_pelo_ouvidor(banco: _BancoOuvidoriaFake, tipo: str = "reclamacao") -> None:
    """O efeito da porta de classificação (issue #372) sobre o caso da Ana, que
    nasce sem tipo e sigiloso: o ouvidor diz o que o caso é e ele volta ao
    índice geral."""
    banco.rows[0]["tipo_manifestacao"] = tipo
    banco.rows[0]["sigilo_reforcado"] = False


def _payload_valido(**overrides) -> dict:
    payload = {
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-4711",
    }
    payload.update(overrides)
    return payload


class TestRegistroDeProtocolo:
    def test_dois_registros_seguidos_recebem_numeros_sequenciais(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake(proximo_numero=7))

        r1 = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )
        r2 = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(categoria="Higiene", setor="Enfermagem"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["protocolo"] == "2026-0007"
        assert r2.json()["protocolo"] == "2026-0008"
        for r in (r1, r2):
            assert re.fullmatch(r"\d{4}-\d{4}", r.json()["protocolo"])
        assert r1.json()["status"] == "em_classificacao"


def _dossie_completo(**overrides) -> dict:
    """Os campos opcionais que a Ana passa a mandar (issue #324, ADR 0034
    decisão 11), somados ao contrato de sempre."""
    payload = _payload_valido(
        relato_integral=(
            "Cheguei as 8h para consulta marcada as 8h30 e so fui atendida as 11h, "
            "sem ninguem explicar o motivo da espera."
        ),
        manifestante_nome="Maria da Silva",
        manifestante_contato="21 99999-1234",
        manifestante_vinculo="paciente",
        gravidade_sugerida="medio",
        confianca_sugestao=0.82,
    )
    payload.update(overrides)
    return payload


class TestContratoAtualSegueValendo:
    """Regressão zero (ADR 0034, decisão 11): a Ana de hoje não muda de uma vez
    com o app. Enquanto o prompt dela não sobe, o POST antigo continua sendo o
    POST bom."""

    def test_post_sem_campos_novos_registra_e_deixa_o_dossie_vazio(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake(proximo_numero=7)
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert r.json()["protocolo"] == "2026-0007"
        gravado = banco.inserts[0]
        # Nada de dossiê no insert: o caso entra em classificação com os dados
        # incompletos, como antes desta fatia.
        assert gravado["categoria"] == "Demora"
        assert gravado.get("relato_integral") is None
        assert gravado.get("classificacao_ia") is None
        assert banco.rows[0]["dados_incompletos"] is True


class TestDossieOpcionalDaAna:
    def test_post_com_os_campos_novos_grava_o_dossie(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        gravado = banco.inserts[0]
        assert gravado["manifestante_nome"] == "Maria da Silva"
        assert gravado["manifestante_contato"] == "21 99999-1234"
        assert gravado["manifestante_vinculo"] == "paciente"
        assert gravado["relato_integral"].startswith("Cheguei as 8h")

    def test_gravidade_sugerida_vai_para_o_campo_separado_com_a_confianca(self, monkeypatch):
        """A sugestão da Ana mora em classificacao_ia, nunca numa coluna de
        decisão (ADR 0034, decisão 10)."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert banco.inserts[0]["classificacao_ia"] == {"gravidade": "medio", "confianca": 0.82}

    def test_sem_gravidade_sugerida_nao_ha_classificacao_da_ia(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        payload = _dossie_completo()
        del payload["gravidade_sugerida"]
        del payload["confianca_sugestao"]

        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert banco.inserts[0]["classificacao_ia"] is None

    def test_gravidade_sem_confianca_grava_a_sugestao_sem_grau(self, monkeypatch):
        """Sugerir sem saber o quanto confia é legítimo: o que não pode é a
        sugestão sumir."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        payload = _dossie_completo()
        del payload["confianca_sugestao"]

        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert banco.inserts[0]["classificacao_ia"] == {"gravidade": "medio", "confianca": None}

    def test_dossie_completo_marca_o_caso_como_completo(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert banco.inserts[0]["dados_incompletos"] is False

    @pytest.mark.parametrize("faltando", ["relato_integral", "manifestante_nome", "manifestante_contato"])
    def test_dossie_pela_metade_continua_incompleto(self, monkeypatch, faltando):
        """Sem relato, sem nome ou sem contato o ouvidor ainda tem trabalho:
        o caso não pode se declarar pronto."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        payload = _dossie_completo()
        del payload[faltando]

        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert banco.inserts[0]["dados_incompletos"] is True

    @pytest.mark.parametrize("vazio", ["", "   ", "—"])
    @pytest.mark.parametrize("campo", ["relato_integral", "manifestante_nome", "manifestante_contato"])
    def test_campo_opcional_vazio_entra_como_ausente(self, monkeypatch, campo, vazio):
        """A falha silenciosa de interpolação do cliente da Ana (ADR 0031,
        decisão 7) também alcança os campos novos: o vazio não pode virar nome
        em branco no Dossiê nem fazer o caso passar por completo."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(**{campo: vazio}),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert banco.inserts[0][campo] is None
        assert banco.inserts[0]["dados_incompletos"] is True

    def test_tipografia_do_dossie_e_sanitizada(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(relato_integral="Esperei tres horas — ninguem explicou nada."),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert banco.inserts[0]["relato_integral"] == "Esperei tres horas, ninguem explicou nada."

    @pytest.mark.parametrize("vinculo", ["parente", "PACIENTE"])
    def test_vinculo_fora_da_taxonomia_e_recusado(self, monkeypatch, vinculo):
        """O CHECK da migration 064 recusaria depois; a API recusa na entrada,
        com erro que a Ana entende."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(manifestante_vinculo=vinculo),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    @pytest.mark.parametrize("gravidade", ["gravissimo", "Alto", "3"])
    def test_gravidade_fora_da_taxonomia_e_recusada(self, monkeypatch, gravidade):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(gravidade_sugerida=gravidade),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    @pytest.mark.parametrize("confianca", [-0.1, 1.5, 82])
    def test_confianca_fora_de_zero_a_um_e_recusada(self, monkeypatch, confianca):
        """Confiança é fração, não porcentagem: 82 gravado como grau tornaria a
        sugestão ilegível no painel."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(confianca_sugestao=confianca),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    @pytest.mark.parametrize("campo", ["manifestante_vinculo", "gravidade_sugerida", "confianca_sugestao"])
    @pytest.mark.parametrize("vazio", ["", "   "])
    def test_opcional_de_taxonomia_em_branco_nao_derruba_o_registro(self, monkeypatch, campo, vazio):
        """A interpolação vazia do cliente da Ana não pode custar a
        manifestação inteira: em branco é o campo que ela não preencheu, e o
        CHECK da migration 064 aceita NULL de propósito."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(**{campo: vazio}),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        if campo == "manifestante_vinculo":
            assert banco.inserts[0]["manifestante_vinculo"] is None
        elif campo == "gravidade_sugerida":
            assert banco.inserts[0]["classificacao_ia"] is None
        else:
            assert banco.inserts[0]["classificacao_ia"] == {"gravidade": "medio", "confianca": None}

    def test_confianca_sem_gravidade_nao_e_gravada(self, monkeypatch):
        """Grau de confiança sem dizer em que se confia não diz nada, e não é
        motivo para perder a manifestação: entra o registro, não entra a
        classificação."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        payload = _dossie_completo()
        del payload["gravidade_sugerida"]

        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert banco.inserts[0]["classificacao_ia"] is None


class TestSetorDaAnaContraATaxonomia:
    """A terceira porta que grava setor (issue #419).

    A Ana é alimentada por IA e nunca recusa um registro: quem fala do outro
    lado é paciente, e derrubar o protocolo por causa do nome de uma área
    deixaria gente sem número. Então a área é resolvida, não exigida."""

    def test_grafia_da_ia_e_gravada_na_forma_canonica(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(setor="  recepçao "),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201, r.text
        assert banco.rows[0]["setor"] == "Recepcao"

    def test_area_fora_da_taxonomia_vira_pendente_em_vez_de_recusar(self, monkeypatch):
        # O relatório da Diretoria já sabe ignorar o marcador; o que ele não
        # sabe é ignorar uma área inventada, que vira linha de verdade.
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(setor="Setor que a IA inventou"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201, r.text
        assert r.json()["protocolo"], "A Ana nunca fica sem número por causa da área"
        assert banco.rows[0]["setor"] == SETOR_PENDENTE


class TestSugestaoNaoSobrescreveOuvidor:
    """A decisão humana é intocável pela API da Ana (ADR 0034, decisão 10): ela
    registra manifestação, não classifica caso nem encerra nada."""

    @pytest.mark.parametrize(
        "campo, valor",
        [
            ("status", "encerrado"),
            ("desfecho", "improcedente"),
            ("desfecho_descricao", "Sem procedencia."),
            ("sigilo_reforcado", True),
            ("anonimo", True),
            ("dados_incompletos", False),
            ("classificacao_ia", {"gravidade": "critico"}),
            ("numero", 1),
            ("protocolo", "2026-0001"),
        ],
    )
    def test_campo_de_decisao_no_payload_e_recusado(self, monkeypatch, campo, valor):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(**{campo: valor}),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    def test_campo_desconhecido_inofensivo_nao_derruba_o_registro(self, monkeypatch):
        """O cliente da Ana vive em outro repo e sobe em outra hora. Uma chave
        a mais no payload dele (ou uma digitada errado) não pode custar o
        protocolo do paciente: é ignorada, e não chega ao banco."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(origem="whatsapp", manifestante_nomee="Maria"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert "origem" not in banco.inserts[0]
        assert "manifestante_nomee" not in banco.inserts[0]
        # Nem de volta na resposta: aceitar a chave não é ecoá-la.
        assert set(r.json().keys()) == CAMPOS_DO_INDICE

    def test_insert_grava_apenas_as_colunas_do_contrato(self, monkeypatch):
        """Nem status, nem desfecho, nem tipo: o que a API não escreve fica com
        o default do banco, à espera do ouvidor.

        O sigilo é a exceção, e desde a issue #372: ele não é decisão da Ana,
        é consequência de o caso entrar sem classificação, e a API o calcula na
        entrada em vez de deixar o default aberto."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert set(banco.inserts[0]) == {
            "categoria",
            "setor",
            "resumo",
            "conversa_id",
            "relato_integral",
            "manifestante_nome",
            "manifestante_contato",
            "manifestante_vinculo",
            "classificacao_ia",
            "sigilo_reforcado",
            "dados_incompletos",
        }

    def test_resposta_do_post_com_dossie_continua_fechada_no_indice(self, monkeypatch):
        """A Ana fala com pacientes: o Dossiê que ela ajudou a preencher não
        volta na resposta dela."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_dossie_completo(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert set(r.json().keys()) == CAMPOS_DO_INDICE
        assert "Maria da Silva" not in r.text


class TestRecusaDeCampoCritico:
    """Defesa contra a falha silenciosa de interpolação do cliente da Ana
    (ADR 0031, decisão 7): registro sem campo crítico é recusado com erro claro."""

    @pytest.mark.parametrize("campo", ["categoria", "setor", "resumo"])
    def test_campo_critico_ausente_e_recusado(self, monkeypatch, campo):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        payload = _payload_valido()
        del payload[campo]
        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 422
        assert campo in r.text
        assert banco.rows == []

    @pytest.mark.parametrize("vazio", ["", "   "])
    @pytest.mark.parametrize("campo", ["categoria", "setor", "resumo"])
    def test_campo_critico_vazio_e_recusado(self, monkeypatch, campo, vazio):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(**{campo: vazio}),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert campo in r.text
        assert banco.rows == []

    def test_campo_critico_so_com_travessao_e_recusado(self, monkeypatch):
        """Sanitização roda antes da validação: travessão sozinho viraria ','
        no banco e emitiria protocolo real com resumo sem conteúdo."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(resumo="—"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    def test_falha_do_banco_nao_vaza_detalhe_interno(self, monkeypatch):
        """Erro do Postgres (constraint, tabela) não chega ao cliente: do lado
        da Ana qualquer falha aciona a Regra Híbrida, sem número."""
        from postgrest.exceptions import APIError

        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)

        class _BancoQueFalha(_BancoOuvidoriaFake):
            def inserir(self, payload: dict) -> dict:
                raise APIError(
                    {
                        "code": "23505",
                        "message": 'duplicate key value violates unique constraint "ouvidoria_protocolos_numero_key"',
                    }
                )

        client = _make_app(_BancoQueFalha())

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 500
        assert r.json() == {"detail": "Falha ao registrar o protocolo"}
        assert "constraint" not in r.text
        assert "23505" not in r.text

    def test_conversa_id_ausente_nao_recusa(self, monkeypatch):
        """conversa_id não é crítico (ressalva do ADR-0010 da Ana): o vínculo
        pode se fazer na direção inversa, pelo resumo da escalada."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        payload = _payload_valido()
        del payload["conversa_id"]
        r = client.post("/api/ana/ouvidoria/protocolos", json=payload, headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201
        assert r.json()["conversa_id"] == ""


class TestConsultaDeProtocolo:
    def test_consulta_devolve_o_protocolo_registrado(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake(proximo_numero=7)
        client = _make_app(banco)

        registrado = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        ).json()
        # O caso da Ana nasce sigiloso (issue #372) e do sigiloso sai só o
        # andamento. Aqui o ouvidor já classificou e devolveu o caso ao índice
        # geral, que é o cenário deste contrato.
        _classificado_pelo_ouvidor(banco)

        r = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 200
        consultado = r.json()
        assert consultado["protocolo"] == "2026-0007"
        assert consultado["categoria"] == registrado["categoria"]
        assert consultado["setor"] == registrado["setor"]
        assert consultado["resumo"] == registrado["resumo"]
        assert consultado["status"] == "em_classificacao"

    def test_protocolo_inexistente_devolve_404(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        r = client.get("/api/ana/ouvidoria/protocolos/2026-9999", headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 404


class TestAuthPorApiKey:
    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "chave-errada"}])
    def test_registro_sem_chave_ou_com_chave_errada_e_recusado(self, monkeypatch, headers):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers=headers)

        assert r.status_code == 401
        assert banco.rows == []

    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "chave-errada"}])
    def test_consulta_sem_chave_ou_com_chave_errada_e_recusada(self, monkeypatch, headers):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        client = _make_app(_BancoOuvidoriaFake())

        r = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers=headers)

        assert r.status_code == 401


# O índice completo da manifestação, e nada além dele (ADR 0031, decisão 3).
CAMPOS_DO_INDICE = {
    "id",
    "numero",
    "protocolo",
    "data_abertura",
    "prazo_resposta",
    "status",
    "categoria",
    "setor",
    "resumo",
    "conversa_id",
}


def _ddl_migration() -> str:
    migration = os.path.join(
        os.path.dirname(__file__), "..", "..", "supabase", "migrations", "063_ouvidoria_protocolos_ana.sql"
    )
    with open(migration, encoding="utf-8") as f:
        return f.read()


class TestContratoDePrivacidade:
    """A resposta da API da Ana é fechada no índice. Desde o ADR 0034 o app
    guarda o Dossiê (nome, contato, relato integral), mas ele não sai por aqui:
    a Ana fala com pacientes. Campo novo nesta resposta só entra por decisão
    revisada."""

    def test_respostas_expoem_exatamente_o_indice(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake(proximo_numero=7)
        client = _make_app(banco)

        registrado = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        ).json()
        _classificado_pelo_ouvidor(banco)
        consultado = client.get("/api/ana/ouvidoria/protocolos/2026-0007", headers={"X-API-Key": CHAVE_CORRETA}).json()

        assert set(registrado.keys()) == CAMPOS_DO_INDICE
        assert set(consultado.keys()) == CAMPOS_DO_INDICE

    def test_coluna_futura_no_banco_nao_vaza_na_resposta_do_registro(self, monkeypatch):
        """O insert do PostgREST devolve a row inteira: se a tabela ganhar
        coluna nova amanhã, a resposta do registro continua fechada no índice."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)

        class _BancoComColunaNova(_BancoOuvidoriaFake):
            def inserir(self, payload: dict) -> dict:
                row = super().inserir(payload)
                row["coluna_futura"] = "valor que nao pode vazar"
                return row

        client = _make_app(_BancoComColunaNova())

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 201
        assert set(r.json().keys()) == CAMPOS_DO_INDICE

    def test_schema_da_fundacao_nao_tem_coluna_de_dado_pessoal(self):
        """A migration 063 não cria coluna de nome, CPF ou relato.

        O ADR 0034 emendou a decisão 3 do ADR 0031: a manifestação completa
        passou a viver no app, e a migration 064 acrescenta o Dossiê. O que
        segue valendo aqui, e é o que este teste guarda, é que a fundação da
        Ana continua sendo índice: quem quiser dado pessoal precisa da rota da
        Ouvidoria, com perfil e log de acesso (issue #320)."""
        ddl = _ddl_migration().lower()
        for proibido in ("nome", "cpf", "relato", "paciente", "solicitante", "telefone", "email"):
            assert proibido not in ddl, f"Coluna/termo de dado pessoal no schema: {proibido}"


class TestDefesaNoBanco:
    """Se a API for contornada, o banco recusa registro vazio e continua sendo
    o único a numerar (ADR 0031, decisões 5 e 7). Sem Postgres na suíte, o
    contrato é amarrado na DDL da migration, como a 061 amarrou o seed."""

    def test_banco_numera_e_formata_o_protocolo(self):
        ddl = _ddl_migration().lower()
        assert "create sequence" in ddl
        assert "nextval('ouvidoria_protocolos_numero_seq')" in ddl
        assert "generated always as" in ddl
        # greatest(): acima de 9999 o NNNN alarga; lpad sozinho truncaria a direita.
        assert "lpad(numero::text, greatest(4, length(numero::text)), '0')" in ddl

    def test_banco_recusa_campo_critico_vazio_ou_nulo(self):
        ddl = _ddl_migration().lower()
        for campo in ("categoria", "setor", "resumo"):
            assert f"{campo} text not null check (btrim({campo}) <> '')" in ddl

    def test_tabela_nova_tem_rls_default_deny(self):
        assert "ENABLE ROW LEVEL SECURITY" in _ddl_migration()


class TestImportDoExport:
    """Import dos protocolos existentes do NocoDB (ato da virada, fora do git):
    preserva numero e data (numeros ja comunicados seguem consultaveis) e a
    sequence continua do ultimo numero usado, mesmo com buraco na numeracao
    (o NocoDB consumiu Ids de registros de teste apagados)."""

    def _rows(self):
        from scripts.import_ouvidoria_protocolos import parse_export

        fixture = os.path.join(os.path.dirname(__file__), "fixtures", "export_nocodb_ouvidoria_protocolos.csv")
        return parse_export(fixture)

    def test_import_preserva_numero_data_e_status(self):
        rows = self._rows()
        assert [r["numero"] for r in rows] == [2, 3, 5]
        assert rows[0]["data_abertura"] == "2026-08-12"
        assert rows[2]["data_abertura"] == "2026-08-13"
        assert [r["status"] for r in rows] == ["aberto", "respondido", "aberto"]
        assert rows[0]["conversa_id"] == "conv-101"
        assert rows[2]["conversa_id"] == ""
        assert rows[2]["categoria"] == "Elogio"

    def test_protocolo_do_export_confere_com_o_que_o_banco_vai_gerar(self):
        """O parser recusa export inconsistente: o Protocolo da fonte tem que
        recompor de numero + ano, senao o numero comunicado mudaria de dono."""
        for row, esperado in zip(self._rows(), ["2026-0002", "2026-0003", "2026-0005"]):
            ano = row["data_abertura"][:4]
            assert f"{ano}-{row['numero']:04d}" == esperado

    def test_tipografia_sanitizada_no_import(self):
        for row in self._rows():
            for valor in row.values():
                if isinstance(valor, str):
                    assert "—" not in valor
                    assert "–" not in valor
        assert self._rows()[1]["resumo"] == (
            "Manifestante descreve espera acima de duas horas, sem atualizacao da fila."
        )

    def test_timestamp_utc_vira_data_no_fuso_do_hospital(self, tmp_path):
        """Manifestação aberta às 22h12 BRT exporta como dia seguinte em UTC;
        a data de abertura (e o prazo derivado) fica no dia local."""
        from scripts.import_ouvidoria_protocolos import parse_export

        csv_path = tmp_path / "export.csv"
        csv_path.write_text(
            "Id,Protocolo,Data_Abertura,Conversa_Id,Categoria,Setor,Resumo,Status,Prazo_Resposta\n"
            "7,2026-0007,2026-08-13 01:12:00+00:00,conv-107,Demora,Recepcao,Espera longa.,Aberto,2026-08-19\n",
            encoding="utf-8",
        )
        rows = parse_export(str(csv_path))
        assert rows[0]["data_abertura"] == "2026-08-12"

    def test_status_desconhecido_recusa_com_erro_claro(self, tmp_path):
        """Erro do import identifica a linha: quem opera a virada precisa saber
        qual protocolo travou, não um KeyError cru."""
        from scripts.import_ouvidoria_protocolos import parse_export

        csv_path = tmp_path / "export.csv"
        csv_path.write_text(
            "Id,Protocolo,Data_Abertura,Conversa_Id,Categoria,Setor,Resumo,Status,Prazo_Resposta\n"
            "7,2026-0007,2026-08-13 09:00:00+00:00,conv-107,Demora,Recepcao,Espera longa.,Em analise,2026-08-19\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="2026-0007"):
            parse_export(str(csv_path))

    def test_sql_do_import_continua_a_sequence_do_ultimo_numero(self):
        from scripts.import_ouvidoria_protocolos import to_sql

        sql = to_sql(self._rows())
        assert "INSERT INTO ouvidoria_protocolos" in sql
        assert "(2, '2026-08-12'" in sql
        assert "(5, '2026-08-13'" in sql
        assert "ON CONFLICT (numero) DO NOTHING" in sql
        # A sequence nasce do maior numero ja usado: o proximo protocolo e o 6.
        assert "setval('ouvidoria_protocolos_numero_seq', (SELECT MAX(numero) FROM ouvidoria_protocolos))" in sql


class TestSigiloDoCanalDaAna:
    """O caso que chega pela Ana entra fail-closed (issue #372).

    O `resumo` do índice é texto gerado a partir da conversa com quem
    manifestou, e frequentemente já identifica a pessoa. Como a Ana registra
    mas não classifica (ADR 0034, decisão 10), o caso nasce SEM tipo, e sem
    tipo o caso é sigiloso: fica só com a Ouvidoria até o ouvidor classificar.
    """

    def test_manifestacao_da_ana_nasce_sem_tipo_e_sigilosa(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 201, r.text
        assert banco.inserts[0]["sigilo_reforcado"] is True
        assert banco.rows[0]["tipo_manifestacao"] is None

    def test_tipo_mandado_pela_ana_e_recusado(self, monkeypatch):
        """Quem decide o tipo (e com ele o sigilo) é o ouvidor. A sugestão da
        IA vive em `classificacao_ia` e não vira classificação validada."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)

        r = client.post(
            "/api/ana/ouvidoria/protocolos",
            json=_payload_valido(tipo_manifestacao="elogio"),
            headers={"X-API-Key": CHAVE_CORRETA},
        )

        assert r.status_code == 422
        assert banco.rows == []

    def test_consulta_de_protocolo_sigiloso_nao_devolve_resumo_categoria_nem_setor(self, monkeypatch):
        """Os números de protocolo são sequenciais, logo enumeráveis, e a
        consulta não pede login. Do caso sigiloso sai só o andamento: número,
        estado e data (issue #372, decisão 6)."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers={"X-API-Key": CHAVE_CORRETA})

        r = client.get("/api/ana/ouvidoria/protocolos/2026-0001", headers={"X-API-Key": CHAVE_CORRETA})

        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["protocolo"] == "2026-0001"
        assert corpo["status"] == "em_classificacao"
        assert corpo["data_abertura"] == "2026-08-14"
        assert "resumo" not in corpo
        assert "categoria" not in corpo
        assert "setor" not in corpo

    def test_consulta_de_protocolo_nao_sigiloso_segue_com_o_contrato_de_hoje(self, monkeypatch):
        """O time da Ana só perde campos no caso sigiloso: o resto do contrato
        não muda."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE_CORRETA)
        banco = _BancoOuvidoriaFake()
        client = _make_app(banco)
        client.post("/api/ana/ouvidoria/protocolos", json=_payload_valido(), headers={"X-API-Key": CHAVE_CORRETA})
        # O ouvidor classificou como elogio e devolveu o caso ao índice geral.
        banco.rows[0]["tipo_manifestacao"] = "elogio"
        banco.rows[0]["sigilo_reforcado"] = False

        corpo = client.get("/api/ana/ouvidoria/protocolos/2026-0001", headers={"X-API-Key": CHAVE_CORRETA}).json()

        assert corpo["resumo"] == "Paciente relata espera acima de duas horas na recepcao."
        assert corpo["categoria"] == "Demora"
        assert corpo["setor"] == "Recepcao"
