"""A porta do sigilo da Ouvidoria (issue #372, PRD #317, ADR 0034).

Até aqui `sigilo_reforcado` só era escrito no nascimento do caso, a partir de
texto livre, e depois disso não existia porta nenhuma: nem para elevar o sigilo
de um caso que chegou pela Ana, nem para abaixar o do canal aberto, que nasce
fail-closed e ficava invisível para sempre.

Esta suíte cobre os critérios de aceite da issue #372 pelo seam HTTP: o tipo da
manifestação vira lista fechada, quem decide o sigilo é o tipo (não a palavra
digitada), e a classificação do ouvidor é a única porta que sobe e desce o
sigilo, sempre com trilha e log de acesso.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

AGORA = dt.datetime(2026, 8, 25, 17, 0, tzinfo=dt.UTC)

REGISTRO = {
    "canal": "telefone",
    "contato_em": "2026-08-14T16:50:00",
    "tipo_manifestacao": "reclamacao",
    "categoria": "Demora no atendimento",
    "setor": "Recepcao",
    "resumo": "Paciente relata espera acima de duas horas na recepcao.",
    "relato_integral": "Cheguei as 8h com minha mae e so fomos atendidos as 10h30.",
    "manifestante_nome": "Joana da Silva",
    "manifestante_contato": "(31) 99999-0000",
    "manifestante_vinculo": "acompanhante",
}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _manifestacao(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "em_classificacao",
        "tipo_manifestacao": None,
        "categoria": "A classificar",
        "setor": "A definir",
        "resumo": "Sou a Maria Silva, do leito 302, e o enfermeiro me destratou.",
        "conversa_id": "",
        "contato_em": "2026-08-14T19:50:00+00:00",
        "relato_integral": "Sou a Maria Silva, do leito 302, e o enfermeiro me destratou na madrugada.",
        "manifestante_nome": "Maria Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "paciente",
        "anonimo": False,
        "sigilo_reforcado": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "desfecho": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "gravidade": None,
        "prazo_area_em": None,
        "validada_em": None,
        "validada_por": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só o que foi
    pedido, o insert devolve as colunas que o banco geraria e o update escreve
    nas linhas que casaram com o filtro."""

    def __init__(self, nome: str, rows: list[dict]):
        self.nome = nome
        self.rows = rows
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def _gerar_colunas_do_banco(self, row: dict) -> dict:
        if self.nome != "ouvidoria_protocolos":
            row.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
            return row
        numero = len(self.rows) + 7
        abertura = row.get("data_abertura") or "2026-08-24"
        row.setdefault("id", f"uuid-{numero}")
        row["numero"] = numero
        row["data_abertura"] = abertura
        row["protocolo"] = f"{abertura[:4]}-{numero:04d}"
        row["prazo_resposta"] = "2026-08-21"
        row.setdefault("status", "em_classificacao")
        return row

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def range(self, inicio, fim):
        """O recorte de página do PostgREST (issue #430): as leituras integrais
        da Ouvidoria passaram a pedir a resposta em janelas."""
        self._janela = (inicio, fim)
        return self

    def execute(self):
        resposta = self._executar()
        dados = resposta.data or []
        inicio, fim = getattr(self, "_janela", None) or (0, len(dados))
        return type("R", (), {"data": dados[inicio : fim + 1]})()

    def _executar(self):
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = [self._gerar_colunas_do_banco(dict(n)) for n in novos]
            self.rows.extend(gravados)
            return type("R", (), {"data": [dict(g) for g in gravados]})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _AgregadoFake:
    """A leitura da função `ouvidoria_ultimo_movimento` do jeito que a rota a
    faz: em páginas (`ler_tudo`) e com ordem estável. O recorte recorta de
    verdade, senão o laço de paginação giraria até o teto de páginas."""

    def __init__(self, linhas: list[dict]):
        self._linhas = sorted(linhas, key=lambda linha: linha["manifestacao_id"])

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio: int, fim: int):
        return _AgregadoFake(self._linhas[inicio : fim + 1])

    def execute(self):
        return type("R", (), {"data": [dict(linha) for linha in self._linhas]})()


class _SupabaseFake:
    def __init__(self, manifestacoes: list[dict] | None = None):
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": manifestacoes if manifestacoes is not None else [],
            "ouvidoria_movimentos": [],
            "ouvidoria_acessos": [],
            "ouvidoria_anexos": [],
            # A taxonomia da casa: desde a issue #419 o setor da manifestação é
            # conferido contra ela nas portas que o gravam.
            "setores": [{"id": "s1", "nome": "Recepcao", "ativo": True}],
            "ouvidoria_feriados": [],
        }

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []))

    def rpc(self, nome: str, _params: dict):
        """Efeito da função `ouvidoria_ultimo_movimento` (migration 092, issue
        #484): o instante do movimento mais recente de cada caso, agregado da
        trilha. É o outro lado da comparação que acende o ponto de novidade na
        fila do ouvidor."""
        assert nome == "ouvidoria_ultimo_movimento", f"RPC inesperada: {nome}"
        ultimo: dict[str, str] = {}
        for mov in self.tabelas.get("ouvidoria_movimentos", []):
            quando = mov.get("ocorrido_em")
            if quando is None:
                continue
            caso = str(mov["manifestacao_id"])
            ultimo[caso] = max(str(quando), ultimo.get(caso, ""))
        agregado = [{"manifestacao_id": c, "ultimo_movimento_em": q} for c, q in ultimo.items()]
        return _AgregadoFake(agregado)


# Quem está logado no cliente de teste. Um teste que precisa de dois papéis
# (o ouvidor age, alguém de fora confere o índice) TROCA a sessão com
# `_entrar_como`, em vez de montar um segundo client: o participante é
# resolvido por monkeypatch no módulo do router, e um segundo client
# reescreveria esse patch para todos os clients, inclusive o primeiro. O teste
# do índice da secretária passaria lendo o índice do ouvidor.
_SESSAO: dict = {"participante": None}


def _entrar_como(participante: dict | None) -> None:
    _SESSAO["participante"] = participante


def _client(monkeypatch, participante: dict | None, supabase: _SupabaseFake | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()
    _entrar_como(participante)

    async def _fake_participante(_user, _sb, fields=None):
        return _SESSAO["participante"]

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


class TestTipoDecideOSigilo:
    """O sigilo deixa de depender da palavra que o ouvidor digitou."""

    def test_relato_de_conduta_nasce_sigiloso_mesmo_com_rotulo_fora_do_padrao(self, monkeypatch):
        """O rótulo humano "Assédio moral" não casa com nenhuma palavra da
        regra antiga. Quem decide agora é o tipo, e ele é lista fechada: o caso
        nasce sigiloso sem o ouvidor marcar nada."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post(
            "/api/ouvidoria/manifestacoes",
            json=REGISTRO | {"tipo_manifestacao": "relato_de_conduta", "categoria": "Assedio moral"},
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["tipo_manifestacao"] == "relato_de_conduta"
        assert gravado["sigilo_reforcado"] is True


class TestClassificacaoAbaixaOSigilo:
    """O caso do canal aberto nasce fail-closed. A classificação é a porta que
    o devolve à fila de todos (issue #372, decisões 4 e 5)."""

    def test_caso_do_canal_aberto_classificado_como_elogio_volta_ao_indice_de_quem_esta_fora(self, monkeypatch):
        """Antes: manifestação vinda do QR não aparece para a secretária, e
        nunca ia aparecer, porque nenhuma rota abaixava o sigilo. Depois de o
        ouvidor classificar como elogio, ela volta à fila de todos."""
        preso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        supabase = _SupabaseFake([preso])

        client, _ = _client(monkeypatch, SECRETARIA, supabase)
        antes = client.get("/api/ouvidoria/protocolos")
        assert [m["protocolo"] for m in antes.json()["protocolos"]] == []

        _entrar_como(OUVIDOR)
        r = client.post(
            f"/api/ouvidoria/manifestacoes/{preso['id']}/classificacao",
            json={
                "tipo_manifestacao": "elogio",
                "categoria": "Elogio a equipe da recepcao",
                "sigilo_reforcado": False,
            },
        )
        assert r.status_code == 200, r.text

        _entrar_como(SECRETARIA)
        depois = client.get("/api/ouvidoria/protocolos")
        assert [m["protocolo"] for m in depois.json()["protocolos"]] == ["2026-0007"]

    def test_a_classificacao_devolve_o_dossie_com_os_marcos(self, monkeypatch):
        """A página do caso troca o caso da tela pelo corpo desta rota
        (issue #480). Sem os marcos aqui, classificar faz o bloco dos quatro
        marcos, o prazo da área e a data de validação sumirem da tela, sem erro
        nenhum, até a pessoa recarregar a página."""
        caso = _manifestacao(canal="ana", sigilo_reforcado=False, categoria="Demora")
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([caso]))

        r = client.post(
            f"/api/ouvidoria/manifestacoes/{caso['id']}/classificacao",
            json={"tipo_manifestacao": "reclamacao", "categoria": "Demora no atendimento"},
        )

        assert r.status_code == 200, r.text
        assert [m["chave"] for m in r.json()["marcos"]] == ["T0", "T1", "T2", "T3"]
        assert [p["chave"] for p in r.json()["prazos"]] == ["area", "conclusivo"]

    def test_ouvidor_eleva_o_sigilo_de_caso_que_chegou_pela_ana(self, monkeypatch):
        """O caso da Ana nasce sem sigilo e o resumo dele identifica quem
        relatou. Classificado como denúncia, sai do índice de quem está fora da
        Ouvidoria, sem o ouvidor pedir sigilo nenhum: o tipo já manda."""
        aberto = _manifestacao(canal="ana", sigilo_reforcado=False, categoria="Demora")
        supabase = _SupabaseFake([aberto])

        client, _ = _client(monkeypatch, SECRETARIA, supabase)
        assert [m["protocolo"] for m in client.get("/api/ouvidoria/protocolos").json()["protocolos"]] == ["2026-0007"]

        _entrar_como(OUVIDOR)
        r = client.post(
            f"/api/ouvidoria/manifestacoes/{aberto['id']}/classificacao",
            json={"tipo_manifestacao": "denuncia", "categoria": "Assedio moral"},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True
        _entrar_como(SECRETARIA)
        assert client.get("/api/ouvidoria/protocolos").json()["protocolos"] == []

    def test_denuncia_nao_aceita_ter_o_sigilo_retirado(self, monkeypatch):
        """A regra automática é piso, nunca teto: nem o ouvidor tira o sigilo de
        uma denúncia. O caso continua fora do índice de quem está de fora."""
        denuncia = _manifestacao(tipo_manifestacao="denuncia", sigilo_reforcado=True)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([denuncia]))

        r = client.post(
            f"/api/ouvidoria/manifestacoes/{denuncia['id']}/classificacao",
            json={"tipo_manifestacao": "denuncia", "sigilo_reforcado": False},
        )

        assert r.status_code == 409
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is True
        _entrar_como(SECRETARIA)
        assert client.get("/api/ouvidoria/protocolos").json()["protocolos"] == []


class TestQuemPodeMexerNoSigilo:
    """A porta é da Ouvidoria. O Super admin técnico fica de fora (RN-40)."""

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN], ids=["secretaria", "super_admin"])
    def test_quem_esta_fora_da_ouvidoria_nao_classifica_nem_mexe_no_sigilo(self, monkeypatch, participante):
        """O pedido é válido em tudo o mais (caso existe, tipo é da lista, o
        ouvidor conseguiria): o que recusa é só o perfil. Depois da recusa, o
        caso continua exatamente como estava."""
        preso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, participante, _SupabaseFake([preso]))

        r = client.post(
            f"/api/ouvidoria/manifestacoes/{preso['id']}/classificacao",
            json={"tipo_manifestacao": "elogio", "sigilo_reforcado": False},
        )

        assert r.status_code == 403
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["sigilo_reforcado"] is True
        assert gravado["tipo_manifestacao"] is None
        assert supabase.tabelas["ouvidoria_movimentos"] == []

    def test_a_diretoria_executiva_tambem_classifica(self, monkeypatch):
        """O perfil da Ouvidoria são os dois papéis, não só o ouvidor: sem
        isto, o 403 acima poderia estar barrando todo mundo."""
        preso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, DIRETORIA, _SupabaseFake([preso]))

        r = client.post(
            f"/api/ouvidoria/manifestacoes/{preso['id']}/classificacao",
            json={"tipo_manifestacao": "elogio", "sigilo_reforcado": False},
        )

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["sigilo_reforcado"] is False


class TestRastroDaMudancaDeSigilo:
    """Tirar um caso da vista de todos, ou devolvê-lo, deixa rastro com nome."""

    def test_retirada_do_sigilo_entra_na_trilha_e_no_log_de_acesso_com_autor(self, monkeypatch):
        preso = _manifestacao(canal="qr", sigilo_reforcado=True, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([preso]))

        client.post(
            f"/api/ouvidoria/manifestacoes/{preso['id']}/classificacao",
            json={"tipo_manifestacao": "elogio", "categoria": "Elogio a equipe", "sigilo_reforcado": False},
        )

        movimento = supabase.tabelas["ouvidoria_movimentos"][-1]
        assert movimento["autor_nome"] == "Marta Ouvidora"
        assert "Elogio" in movimento["observacao"]
        assert "Sigilo reforçado retirado" in movimento["observacao"]

        acesso = supabase.tabelas["ouvidoria_acessos"][-1]
        assert acesso["ator_nome"] == "Marta Ouvidora"
        assert acesso["acao"] == "classificacao"

    def test_elevacao_do_sigilo_diz_na_trilha_que_o_sigilo_subiu(self, monkeypatch):
        aberto = _manifestacao(canal="ana", sigilo_reforcado=False, tipo_manifestacao=None)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([aberto]))

        client.post(
            f"/api/ouvidoria/manifestacoes/{aberto['id']}/classificacao",
            json={"tipo_manifestacao": "denuncia"},
        )

        assert "Sigilo reforçado aplicado" in supabase.tabelas["ouvidoria_movimentos"][-1]["observacao"]

    def test_classificacao_que_nao_mexe_no_sigilo_nao_inventa_mudanca_na_trilha(self, monkeypatch):
        """Trocar reclamação por sugestão não muda o sigilo, e a trilha não
        pode dizer que mudou: o rastro serve para auditar quem escondeu ou
        devolveu um caso."""
        aberto = _manifestacao(tipo_manifestacao="reclamacao", sigilo_reforcado=False)
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([aberto]))

        client.post(
            f"/api/ouvidoria/manifestacoes/{aberto['id']}/classificacao",
            json={"tipo_manifestacao": "sugestao"},
        )

        observacao = supabase.tabelas["ouvidoria_movimentos"][-1]["observacao"]
        assert "Sigilo" not in observacao


class TestRotuloOpcionalNoRegistro:
    """O rótulo humano virou opcional: quem descreve o caso é o tipo."""

    def test_registro_sem_rotulo_guarda_o_nome_do_tipo(self, monkeypatch):
        """A coluna `categoria` é NOT NULL no banco (migration 063) e o painel
        a mostra. Sem rótulo escrito, vale o nome do tipo escolhido, e não uma
        string vazia que o banco recusaria."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post(
            "/api/ouvidoria/manifestacoes",
            json=REGISTRO | {"tipo_manifestacao": "elogio", "categoria": None},
        )

        assert r.status_code == 201, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["categoria"] == "Elogio"


class TestCasoInexistente:
    def test_classificar_caso_que_nao_existe_devolve_404(self, monkeypatch):
        """Sem esta guarda, a tela receberia um Dossiê com todos os campos
        vazios e apagaria o caso que o ouvidor está lendo."""
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake([]))

        r = client.post(
            "/api/ouvidoria/manifestacoes/uuid-7/classificacao",
            json={"tipo_manifestacao": "elogio"},
        )

        assert r.status_code == 404
        assert supabase.tabelas["ouvidoria_movimentos"] == []


class TestOIndiceDizSeOCasoESigiloso:
    """A tela de validação abre a partir da linha do índice e precisa mostrar
    a marca de sigilo no estado certo (issue #372).

    Sem este campo, a tela abria com a marca desligada num caso protegido e
    mandava `sigilo_reforcado: false` na validação, retirando o sigilo sem
    ninguém ter desmarcado nada."""

    def test_ouvidor_ve_a_marca_de_sigilo_na_linha_do_indice(self, monkeypatch):
        supabase = _SupabaseFake([_manifestacao(sigilo_reforcado=True, tipo_manifestacao="reclamacao")])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        linha = client.get("/api/ouvidoria/protocolos").json()["protocolos"][0]

        assert linha["sigilo_reforcado"] is True

    def test_para_quem_esta_fora_o_indice_so_tem_caso_aberto(self, monkeypatch):
        """A coluna não vira vazamento: a linha sigilosa nem chega a quem está
        fora da Ouvidoria, e o que chega é sempre não sigiloso."""
        supabase = _SupabaseFake(
            [
                _manifestacao(7, sigilo_reforcado=True, tipo_manifestacao="denuncia"),
                _manifestacao(8, sigilo_reforcado=False, tipo_manifestacao="elogio"),
            ]
        )
        client, _ = _client(monkeypatch, SECRETARIA, supabase)

        linhas = client.get("/api/ouvidoria/protocolos").json()["protocolos"]

        assert [linha["protocolo"] for linha in linhas] == ["2026-0008"]
        assert linhas[0]["sigilo_reforcado"] is False
