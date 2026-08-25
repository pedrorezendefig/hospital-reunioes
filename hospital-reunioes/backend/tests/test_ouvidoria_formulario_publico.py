"""Formulário público de ouvidoria e QR setorial (issue #323, ADR 0034 decisão 9).

Canal aberto: sem login, o manifestante registra a Manifestação e recebe o
Protocolo na tela. Os testes seguem o seam HTTP do PRD #317, o mesmo dos testes
da API da Ana, e cobrem os critérios de aceite da issue:

- protocolo na tela e caso em classificação;
- QR com setor e ponto pré-preenche e grava canal `qr` com o ponto;
- sem parâmetros, formulário limpo e canal `site`;
- rate limit por IP com resposta clara;
- envio vazio (ou só espaços) recusado;
- registro anônimo sem nome e sem contato.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import settings  # noqa: E402
from app.dependencies import get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria_publica  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _BancoFake:
    """Simula o que o Postgres faz sozinho (migrations 063/064): numeração por
    sequence, protocolo ANO-NNNN como coluna gerada e defaults da manifestação.
    Guarda o insert cru, para o teste provar quais colunas a API escreve."""

    def __init__(self, proximo_numero: int = 1, setores: list[str] | None = None):
        self._proximo_numero = proximo_numero
        self.rows: list[dict] = []
        self.inserts: list[dict] = []
        self.setores = [{"nome": nome} for nome in (setores if setores is not None else ["Recepção", "Enfermagem"])]

    def inserir(self, payload: dict) -> dict:
        # NOT NULL + CHECK anti-vazio da migration 063: contornar a API não
        # contorna o banco, e o fake precisa recusar o mesmo que ele recusa.
        for critico in ("categoria", "setor", "resumo"):
            if not str(payload.get(critico) or "").strip():
                raise APIError({"code": "23502", "message": f"null value in column {critico}"})
        self.inserts.append(dict(payload))
        row = {
            "id": f"uuid-{self._proximo_numero}",
            "numero": self._proximo_numero,
            "protocolo": f"2026-{self._proximo_numero:04d}",
            "data_abertura": "2026-08-24",
            "prazo_resposta": "2026-08-31",
            "status": "em_classificacao",
            "canal": "site",
            "canal_setor": None,
            "canal_ponto": None,
            "anonimo": False,
            "dados_incompletos": True,
            "sigilo_reforcado": False,
            **payload,
        }
        self._proximo_numero += 1
        self.rows.append(row)
        return row


class _Query:
    def __init__(self, banco: _BancoFake, tabela: str):
        self._banco = banco
        self._tabela = tabela
        self._filters: dict = {}
        self._pending_insert: dict | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_args, **_kwargs):
        if colunas != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
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
            data = [self._banco.inserir(self._pending_insert)]
        elif self._tabela == "setores":
            data = [dict(s) for s in self._banco.setores]
        else:
            data = [dict(r) for r in self._banco.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._colunas:
            data = [{c: row.get(c) for c in self._colunas} for row in data]
        return type("R", (), {"data": data})()


# Quem conecta no backend em produção é o container do proxy, com IP privado
# da rede do Docker. O TestClient, por padrão, se apresenta como "testclient",
# que não é IP nenhum: é o cliente de fora, sem proxy no meio.
PROXY_DO_NEXT = ("10.0.0.2", 51000)
# IP público de verdade: as faixas de documentação (203.0.113.x e companhia)
# contam como privadas para o `ipaddress`, e não serviriam para provar o
# caminho de quem vem da internet.
CLIENTE_DIRETO = ("189.40.12.7", 51000)


def _make_app(
    banco: _BancoFake | None = None,
    cliente: tuple[str, int] | None = None,
) -> tuple[TestClient, _BancoFake]:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_publica.router, prefix="/api")

    banco = banco or _BancoFake()

    class _SupabaseMock:
        def table(self, name: str):
            assert name in ("ouvidoria_protocolos", "setores"), f"Tabela inesperada: {name}"
            return _Query(banco, name)

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    kwargs = {"client": cliente} if cliente else {}
    return TestClient(app, follow_redirects=False, **kwargs), banco


RELATO = "Esperei duas horas na recepção sem nenhuma informação sobre a demora."


def _payload(**overrides) -> dict:
    payload = {"relato": RELATO}
    payload.update(overrides)
    return payload


class TestProtocoloNaTela:
    def test_manifestante_envia_e_ve_o_protocolo_na_tela(self):
        client, _banco = _make_app(_BancoFake(proximo_numero=7))

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload())

        assert r.status_code == 201
        assert r.json()["protocolo"] == "2026-0007"

    def test_caso_entra_em_classificacao_na_fila_do_ouvidor(self):
        """Nenhum canal despacha sozinho (ADR 0034, decisão 3): o status é o
        default do banco, e a API não manda status nenhum no insert."""
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload())

        assert r.status_code == 201
        assert r.json()["status"] == "em_classificacao"
        assert "status" not in banco.inserts[0]

    def test_caso_entra_sem_area_definida_e_com_resumo_legivel_na_fila(self):
        """O manifestante não classifica nada: quem define tipo e área é o
        ouvidor na validação. Mas categoria, setor e resumo são NOT NULL desde
        a migration 063, então o canal aberto entra com marcador de pendente e
        um resumo tirado do próprio relato, para a fila não ficar cega."""
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload())

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["setor"] == "A definir"
        assert gravado["categoria"] == "A classificar"
        assert gravado["resumo"].startswith("Esperei duas horas na recepção")
        assert gravado["relato_integral"] == RELATO

    def test_resumo_longo_e_cortado_sem_perder_o_relato_integral(self):
        """O resumo é vitrine de fila, o relato é o documento. Relato de
        romance não estica a coluna do índice, e nada do texto se perde."""
        relato = "Reclamação detalhada. " * 60
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(relato=relato))

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert len(gravado["resumo"]) <= 200
        assert gravado["relato_integral"] == relato.strip()


class TestIdentificacaoOpcional:
    def test_manifestante_que_se_identifica_tem_nome_e_contato_no_dossie(self):
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(nome="Maria Souza", contato="maria@exemplo.com"),
        )

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["manifestante_nome"] == "Maria Souza"
        assert gravado["manifestante_contato"] == "maria@exemplo.com"
        assert gravado["anonimo"] is False
        # Com relato, nome e contato não falta nada para o ouvidor validar.
        assert gravado["dados_incompletos"] is False

    def test_registro_anonimo_funciona_sem_nome_e_sem_contato(self):
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(anonimo=True))

        assert r.status_code == 201
        assert r.json()["protocolo"]
        gravado = banco.rows[0]
        assert gravado["anonimo"] is True
        assert gravado["manifestante_nome"] is None
        assert gravado["manifestante_contato"] is None

    def test_anonimo_descarta_nome_e_contato_que_venham_no_envio(self):
        """Quem marcou anônimo não é identificado, nem por engano do formulário
        nem por quem monta a requisição na mão: o pedido de anonimato vence."""
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(anonimo=True, nome="Maria Souza", contato="21999999999"),
        )

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["manifestante_nome"] is None
        assert gravado["manifestante_contato"] is None

    def test_identificacao_pela_metade_deixa_o_caso_marcado_como_incompleto(self):
        """Nome sem contato não fecha o Dossiê: o ouvidor ainda tem o que
        completar antes de validar."""
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(nome="Maria Souza"))

        assert r.status_code == 201
        assert banco.rows[0]["dados_incompletos"] is True


class TestEnvioVazio:
    @pytest.mark.parametrize("relato", ["", "   ", "\n\t ", "—"])
    def test_envio_vazio_ou_so_espacos_e_recusado(self, relato):
        """Padrão anti-vazio da casa (ADR 0031, decisão 7; ADR 0013 para o
        travessão sozinho): nada disso emite protocolo."""
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(relato=relato))

        assert r.status_code == 422
        assert banco.rows == []

    def test_envio_sem_relato_nenhum_e_recusado(self):
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json={})

        assert r.status_code == 422
        assert banco.rows == []


class TestQrSetorial:
    """O cartaz impresso aponta para `/ouvidoria/qr`, e é o servidor que decide
    o destino (ADR 0034, decisão 9): o cartaz nunca precisa ser reimpresso."""

    def test_qr_com_setor_e_ponto_abre_o_formulario_preenchido(self, monkeypatch):
        monkeypatch.setattr(settings, "frontend_url", "https://app.hospital.exemplo")
        client, _banco = _make_app()

        r = client.get("/api/ouvidoria/qr", params={"setor": "Recepção", "ponto": "Poltrona 12"})

        assert r.status_code == 302
        destino = urlsplit(r.headers["location"])
        assert f"{destino.scheme}://{destino.netloc}{destino.path}" == "https://app.hospital.exemplo/manifestacao"
        assert parse_qs(destino.query) == {"setor": ["Recepção"], "ponto": ["Poltrona 12"]}

    def test_qr_sem_parametros_abre_o_formulario_limpo(self, monkeypatch):
        monkeypatch.setattr(settings, "frontend_url", "https://app.hospital.exemplo")
        client, _banco = _make_app()

        r = client.get("/api/ouvidoria/qr")

        assert r.status_code == 302
        assert r.headers["location"] == "https://app.hospital.exemplo/manifestacao"

    def test_qr_com_setor_desconhecido_abre_o_formulario_limpo(self, monkeypatch):
        """Setor que não está na taxonomia não vira pré-preenchimento: o QR não
        é porta para texto arbitrário entrar no registro."""
        monkeypatch.setattr(settings, "frontend_url", "https://app.hospital.exemplo")
        client, _banco = _make_app(_BancoFake(setores=["Recepção"]))

        r = client.get("/api/ouvidoria/qr", params={"setor": "<script>alert(1)</script>", "ponto": "x"})

        assert r.status_code == 302
        assert r.headers["location"] == "https://app.hospital.exemplo/manifestacao"

    def test_qr_reconhece_o_setor_sem_depender_de_maiuscula(self, monkeypatch):
        """O cartaz é impresso uma vez e o cadastro pode ser renomeado depois;
        o nome que vai para o formulário é sempre o canônico da taxonomia."""
        monkeypatch.setattr(settings, "frontend_url", "https://app.hospital.exemplo")
        client, _banco = _make_app(_BancoFake(setores=["Recepção"]))

        r = client.get("/api/ouvidoria/qr", params={"setor": "  recepção "})

        assert parse_qs(urlsplit(r.headers["location"]).query)["setor"] == ["Recepção"]

    def test_qr_nunca_manda_o_manifestante_para_fora_do_app(self, monkeypatch):
        """Open redirect: o destino sai da configuração do servidor, o
        parâmetro só escolhe o pré-preenchimento."""
        monkeypatch.setattr(settings, "frontend_url", "https://app.hospital.exemplo")
        client, _banco = _make_app()

        r = client.get("/api/ouvidoria/qr", params={"setor": "https://phishing.exemplo", "ponto": "//evil.com"})

        assert r.headers["location"].startswith("https://app.hospital.exemplo/manifestacao")


class TestCanalDeOrigem:
    def test_manifestacao_do_qr_grava_canal_qr_com_setor_e_ponto_de_origem(self):
        client, banco = _make_app(_BancoFake(setores=["Recepção"]))

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(setor="Recepção", ponto="Poltrona 12"),
        )

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["canal"] == "qr"
        assert gravado["canal_setor"] == "Recepção"
        assert gravado["canal_ponto"] == "Poltrona 12"

    def test_setor_do_cartaz_e_origem_e_nao_area_responsavel(self):
        """Quem lê o QR da Recepção para reclamar da Farmácia leu o cartaz da
        Recepção, e não apontou área nenhuma. Gravar o cartaz em `setor` faria o
        caso parecer já classificado na fila do ouvidor."""
        client, banco = _make_app(_BancoFake(setores=["Recepção"]))

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(setor="Recepção", ponto="Poltrona 12"),
        )

        assert r.status_code == 201
        assert banco.rows[0]["setor"] == "A definir"

    def test_manifestacao_sem_parametros_grava_canal_site(self):
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload())

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["canal"] == "site"
        assert gravado["canal_ponto"] is None

    def test_setor_fora_da_taxonomia_nao_entra_no_registro(self):
        """Sem lista fechada, qualquer um escreveria o que quisesse na área da
        manifestação. Fora da taxonomia, o caso entra sem área, como o do site."""
        client, banco = _make_app(_BancoFake(setores=["Recepção"]))

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(setor="Setor Inventado", ponto="Poltrona 12"),
        )

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["setor"] == "A definir"
        assert gravado["canal"] == "site"
        assert gravado["canal_setor"] is None
        assert gravado["canal_ponto"] is None

    def test_ponto_sem_setor_nao_vira_qr(self):
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(ponto="Poltrona 12"))

        assert r.status_code == 201
        gravado = banco.rows[0]
        assert gravado["canal"] == "site"
        assert gravado["canal_setor"] is None
        assert gravado["canal_ponto"] is None


class TestProtecoesDoCanalAberto:
    def test_rajada_do_mesmo_ip_e_limitada_com_resposta_clara(self):
        """Canal sem credencial: o rate limit da casa (slowapi, por IP) é a
        única barreira contra quem quiser encher a fila do ouvidor."""
        client, banco = _make_app()

        respostas = [client.post("/api/ouvidoria/publico/manifestacoes", json=_payload()) for _ in range(8)]

        assert respostas[0].status_code == 201
        assert respostas[-1].status_code == 429
        aceitos = [r for r in respostas if r.status_code == 201]
        assert len(banco.rows) == len(aceitos) < 8

    def test_rajada_de_uma_pessoa_nao_fecha_o_canal_para_as_outras(self):
        """A página chama a API por caminho relativo, então o Next proxia no
        servidor dele e o backend veria o IP do container para todo mundo. Sem
        olhar o primeiro salto do X-Forwarded-For, um cartaz em corredor
        movimentado fecharia o canal na sexta pessoa do dia."""
        client, _banco = _make_app(cliente=PROXY_DO_NEXT)

        gastadas = [
            client.post(
                "/api/ouvidoria/publico/manifestacoes",
                json=_payload(),
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.2"},
            )
            for _ in range(8)
        ]
        outra_pessoa = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(),
            headers={"X-Forwarded-For": "203.0.113.99, 10.0.0.2"},
        )

        assert gastadas[-1].status_code == 429
        assert outra_pessoa.status_code == 201

    def test_leitura_do_qr_nao_e_limitada_como_escrita(self):
        """Cartaz num corredor movimentado: várias pessoas escaneiam o mesmo QR
        do mesmo IP (o wifi do hospital) e todas precisam chegar ao formulário."""
        client, _banco = _make_app()

        respostas = [client.get("/api/ouvidoria/qr") for _ in range(8)]

        assert all(r.status_code == 302 for r in respostas)

    def test_honeypot_preenchido_nao_emite_protocolo(self):
        """Campo escondido que pessoa nenhuma vê: preenchido, é robô."""
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(assunto_alternativo="http://spam.exemplo"),
        )

        assert r.status_code == 400
        assert banco.rows == []

    def test_resposta_publica_devolve_so_o_recibo(self):
        """O manifestante recebe prova do registro, não o Dossiê: nada de id,
        relato, identificação ou sigilo volta por um canal sem credencial."""
        client, _banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(nome="Maria Souza", contato="maria@exemplo.com"),
        )

        assert r.status_code == 201
        assert set(r.json()) == {"protocolo", "data_abertura", "prazo_resposta", "status"}

    def test_envio_nao_decide_classificacao_estado_nem_desfecho(self):
        """Campo que só o ouvidor decide não chega ao banco nem quando alguém o
        manda na mão: o modelo de entrada não o conhece."""
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(
                status="encerrado",
                desfecho="improcedente",
                classificacao_ia={"gravidade": "baixo"},
                numero=99,
                protocolo="2026-9999",
            ),
        )

        assert r.status_code == 201
        gravado = banco.inserts[0]
        for proibido in ("status", "desfecho", "classificacao_ia", "numero", "protocolo"):
            assert proibido not in gravado

    def test_relato_gigante_e_recusado_em_vez_de_engolido(self):
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(relato="a" * 10_001))

        assert r.status_code == 422
        assert banco.rows == []


class TestSigiloDoCanalAberto:
    """Fail-closed: o canal aberto é por onde a denúncia tende a chegar, e ele
    entra sem categoria (quem classifica é o ouvidor). Como `nasce_sigilosa()`
    olha a categoria, ela não tem como rodar aqui: sem sigilo na entrada, o
    `resumo` (os primeiros 200 caracteres do relato) apareceria no índice de
    todo facilitador, secretária e super admin até alguém classificar."""

    def test_manifestacao_do_canal_aberto_nasce_sigilosa(self):
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(relato="O médico Fulano me agrediu verbalmente na frente da minha filha."),
        )

        assert r.status_code == 201
        assert banco.inserts[0]["sigilo_reforcado"] is True
        assert banco.rows[0]["sigilo_reforcado"] is True

    def test_envio_nao_consegue_abaixar_o_sigilo(self):
        """O sigilo da entrada é do servidor: quem monta a requisição na mão não
        derruba a proteção mandando o campo."""
        client, banco = _make_app()

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json=_payload(sigilo_reforcado=False),
        )

        assert r.status_code == 201
        assert banco.inserts[0]["sigilo_reforcado"] is True

    def test_recibo_nao_conta_ao_manifestante_que_o_caso_e_sigiloso(self):
        """Sigilo é assunto interno da Ouvidoria; o recibo continua sendo só a
        prova do registro."""
        client, _banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload())

        assert set(r.json()) == {"protocolo", "data_abertura", "prazo_resposta", "status"}


class TestRelatoCru:
    """O relato integral é o documento do caso: a palavra de quem manifestou
    entra como ela escreveu. O sanitizador da casa existe para tirar marca de IA
    de texto gerado (ADR 0013), não para editar texto de cidadão."""

    def test_relato_integral_guarda_o_texto_como_a_pessoa_escreveu(self):
        relato = "Esperei 3 horas \u2014 ningu\u00e9m apareceu para explicar."
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(relato=relato))

        assert r.status_code == 201
        assert banco.rows[0]["relato_integral"] == relato

    def test_resumo_da_vitrine_continua_sanitizado(self):
        """O resumo aparece nas telas do hospital, e ali vale a tipografia da
        casa."""
        relato = "Esperei 3 horas \u2014 ningu\u00e9m apareceu para explicar."
        client, banco = _make_app()

        r = client.post("/api/ouvidoria/publico/manifestacoes", json=_payload(relato=relato))

        assert r.status_code == 201
        resumo = banco.rows[0]["resumo"]
        assert "\u2014" not in resumo
        assert "\u2013" not in resumo
        assert resumo.startswith("Esperei 3 horas, ningu\u00e9m apareceu")


class TestChaveDoRateLimit:
    """O X-Forwarded-For só vale quando quem conectou é o proxy de dentro da
    rede. Vindo da internet, o cabeçalho é do próprio cliente e não pode
    escolher o balde dele."""

    def test_cliente_direto_nao_abre_balde_novo_forjando_o_cabecalho(self):
        client, banco = _make_app(cliente=CLIENTE_DIRETO)

        respostas = [
            client.post(
                "/api/ouvidoria/publico/manifestacoes",
                json=_payload(),
                headers={"X-Forwarded-For": f"198.51.100.{i}"},
            )
            for i in range(8)
        ]

        assert respostas[-1].status_code == 429
        assert len(banco.rows) < 8

    def test_cabecalho_sem_ip_valido_nao_vira_balde(self):
        """Lixo no cabeçalho não é identidade: cai no endereço real de quem
        conectou."""
        client, _banco = _make_app(cliente=CLIENTE_DIRETO)

        respostas = [
            client.post(
                "/api/ouvidoria/publico/manifestacoes",
                json=_payload(),
                headers={"X-Forwarded-For": f"balde-{i}"},
            )
            for i in range(8)
        ]

        assert respostas[-1].status_code == 429

    def test_caminho_direto_continua_com_teto_agregado(self):
        """Segundo limite, mais folgado, pela ponta da conexão: nenhum caminho
        de entrada fica sem teto, nem se o cabeçalho for confiável.

        A contagem sai da própria constante: o teto é escolha de operação (ver o
        comentário dela no router) e mudar o número não pode calar este teste."""
        client, _banco = _make_app(cliente=PROXY_DO_NEXT)
        teto = ouvidoria_publica.TETO_AGREGADO_POR_MINUTO

        respostas = [
            client.post(
                "/api/ouvidoria/publico/manifestacoes",
                json=_payload(),
                # Um IP diferente por envio: cada um é um manifestante novo, e o
                # que sobra para barrar é só o teto agregado.
                headers={"X-Forwarded-For": f"203.0.113.{i % 254 + 1}"},
            )
            for i in range(teto + 5)
        ]

        assert respostas[-1].status_code == 429
        aceitos = [r for r in respostas if r.status_code == 201]
        assert 5 < len(aceitos) <= teto
