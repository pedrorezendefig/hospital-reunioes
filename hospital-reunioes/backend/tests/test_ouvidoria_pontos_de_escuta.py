"""Ponto de escuta: o cadastro dos cartazes de QR (issue #378, ADR 0036).

O canal `qr` existia desde a #323 e nunca foi usado: o app sabia receber a
manifestação vinda de um cartaz, mas não sabia gerar o cartaz. Aqui nasce a
entidade que faltava, e com ela o código curto que vai impresso no papel.

Cobre o cadastro pelo seam HTTP (é onde o perfil da Ouvidoria é exigido), a
geração do código pela função pura, e a resolução do QR pelas rotas públicas.
"""

from __future__ import annotations

import os
import re
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import RequestContextMiddleware  # noqa: E402
from app.routers import ouvidoria as ouvidoria_router  # noqa: E402
from app.services.ouvidoria_pontos import ALFABETO_DO_CODIGO, TAMANHO_DO_CODIGO, gerar_codigo  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class TestOQueOQrCarrega:
    """A URL impressa é imutável: ela vai para a parede e não volta."""

    def test_o_qr_carrega_o_endereco_curto(self, monkeypatch):
        """ADR 0086, decisão 5: o QR leva `https://<app>/a/<codigo>`. QR com
        menos dados tem módulos maiores e a câmera lê melhor de longe, e o
        caminho é do domínio do app, sem o prefixo `/api`."""
        from app.config import settings
        from app.services.ouvidoria_pontos import url_do_cartaz

        monkeypatch.setattr(settings, "frontend_url", "https://app.hospitalsaomatheus.cloud/")

        assert url_do_cartaz("AB2CD3") == "https://app.hospitalsaomatheus.cloud/a/AB2CD3"

    def test_o_endereco_impresso_e_o_mesmo_endereco_curto_sem_o_esquema(self, monkeypatch):
        """O endereço em letra, para quem não conseguiu ler o QR, é o que o
        modelo da Diretoria imprime: "app.hospitalsaomatheus.cloud/a/{código}".
        Sem esquema: quem digita não escreve "https://"."""
        from app.config import settings
        from app.services.ouvidoria_pontos import endereco_impresso

        monkeypatch.setattr(settings, "frontend_url", "https://app.hospitalsaomatheus.cloud")

        assert endereco_impresso("AB2CD3") == "app.hospitalsaomatheus.cloud/a/AB2CD3"


class TestCodigoDoCartaz:
    """O código é o que vai impresso, é lido em voz alta e digitado à mão
    quando a câmera não coopera (ADR 0036, decisão 3)."""

    def test_o_codigo_tem_seis_caracteres_do_alfabeto(self):
        codigo = gerar_codigo()

        assert len(codigo) == TAMANHO_DO_CODIGO == 6
        assert set(codigo) <= set(ALFABETO_DO_CODIGO)

    def test_o_alfabeto_nao_tem_os_pares_ambiguos(self):
        """`0` e `O`, `1` e `I`: quem lê o cartaz de longe erra os dois."""
        assert "0" not in ALFABETO_DO_CODIGO
        assert "O" not in ALFABETO_DO_CODIGO
        assert "1" not in ALFABETO_DO_CODIGO
        assert "I" not in ALFABETO_DO_CODIGO

    def test_o_alfabeto_nao_tem_minuscula(self):
        """Cartaz é lido em maiúscula, e `l` minúsculo é outro par ambíguo."""
        assert ALFABETO_DO_CODIGO == ALFABETO_DO_CODIGO.upper()

    def test_o_codigo_bate_com_o_check_da_migration(self):
        """A régua vive nos dois lados: contornar a API não pode gravar um
        código que a câmera confunde."""
        caminho = os.path.join(
            os.path.dirname(__file__), "..", "..", "supabase", "migrations", "085_ouvidoria_pontos_de_escuta.sql"
        )
        with open(caminho, encoding="utf-8") as f:
            ddl = f.read()

        padrao = re.search(r"codigo ~ '(\^\[[^']+\]\{\d+\}\$)'", ddl)
        assert padrao, "a migration precisa travar o alfabeto do código"
        assert re.fullmatch(padrao.group(1), gerar_codigo())

    def test_dois_sorteios_seguidos_nao_saem_iguais(self):
        """Não prova aleatoriedade, prova que o código não é constante: um
        gerador que devolvesse sempre a mesma coisa passaria em tudo acima."""
        assert len({gerar_codigo() for _ in range(50)}) > 1


class _TabelaFake:
    """Fake do PostgREST fiel no que importa aqui: o índice único do `codigo`
    (é ele que decide a colisão da geração) e a projeção do select."""

    def __init__(self, banco: _SupabaseFake, nome: str):
        self._banco = banco
        self.nome = nome
        self.rows = banco.tabelas.setdefault(nome, [])
        self._filters: dict = {}
        self._insert: dict | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload: dict):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def delete(self):
        raise AssertionError("Ponto de escuta desativa, nunca apaga (ADR 0036, decisão 6)")

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, _n):
        return self

    def execute(self):
        if self._insert is not None:
            linha = dict(self._insert)
            if self.nome == "ouvidoria_protocolos":
                linha.setdefault("id", f"uuid-{len(self.rows) + 1}")
                linha.setdefault("numero", len(self.rows) + 1)
                linha.setdefault("protocolo", f"2026-{len(self.rows) + 1:04d}")
                linha.setdefault("data_abertura", "2026-08-27")
                linha.setdefault("prazo_resposta", "2026-09-03")
                linha.setdefault("status", "em_classificacao")
                linha.setdefault("canal_setor", None)
                linha.setdefault("canal_ponto", None)
            if self.nome == "ouvidoria_pontos":
                # O índice único da migration 085.
                if any(r.get("codigo") == linha.get("codigo") for r in self.rows):
                    raise APIError({"code": "23505", "message": "duplicate key value violates unique constraint"})
                linha.setdefault("id", f"ponto-{len(self.rows) + 1}")
                linha.setdefault("ativo", True)
                linha.setdefault("criado_em", "2026-08-27T12:00:00+00:00")
            self.rows.append(linha)
            self._banco.tabelas[self.nome] = self.rows
            return type("R", (), {"data": [dict(linha)]})()
        if self.nome == "setores" and self._banco.setores_indisponiveis:
            raise APIError({"code": "42P01", "message": 'relation "setores" does not exist'})
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
        dados = [({c: r.get(c) for c in self._colunas} if self._colunas else dict(r)) for r in casadas]
        return type("R", (), {"data": dados})()


class _SupabaseFake:
    def __init__(self, pontos: list[dict] | None = None, setores: list[str] | None = None):
        # A leitura da taxonomia estourando, como um timeout do PostgREST.
        self.setores_indisponiveis = False
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_pontos": pontos if pontos is not None else [],
            "ouvidoria_protocolos": [],
            "ouvidoria_movimentos": [],
            "setores": [{"nome": n, "ativo": True} for n in (setores if setores is not None else ["Recepção"])],
        }

    def table(self, nome: str):
        return _TabelaFake(self, nome)


def _ponto(codigo: str = "AB2CD3", **overrides) -> dict:
    linha = {
        "id": f"ponto-{codigo}",
        "codigo": codigo,
        "setor": "Recepção",
        "ponto": "Poltrona 12",
        "ativo": True,
        "criado_em": "2026-08-27T12:00:00+00:00",
        "criado_por": "P10",
        "nome_publico": None,
        "descricao_local": "Parede ao lado da poltrona 12",
        "titulo_cartaz": "atendimento_hoje",
        "codigo_controle": None,
        "ala_internacao": False,
    }
    linha.update(overrides)
    return linha


def _client(monkeypatch, participante: dict | None, supabase: _SupabaseFake | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()

    async def _fake_participante(_user, _sb, fields=None):
        return participante

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


NOVO_PONTO = {"setor": "Recepção", "ponto": "Poltrona 12", "descricao_local": "Parede ao lado da poltrona 12"}

# O cartaz da Emergência adulta, como o anexo da especificação da Diretoria
# (seção 11) o descreve.
PONTO_COMPLETO = {
    "setor": "Recepção",
    "ponto": "Hall da Emergência",
    "nome_publico": "Emergência adulta",
    "descricao_local": "Hall da Emergência, parede ao lado da passagem para a espera",
    "titulo_cartaz": "atendimento_hoje",
    "codigo_controle": "PSA-01",
    "ala_internacao": False,
}


class TestOsCamposDoCartaz:
    """CA: cadastrar e editar um ponto com nome público, descrição do local,
    título, código de controle e ala de internação; descrição vazia é recusada
    (ADR 0086, decisão 10)."""

    def test_o_ouvidor_cadastra_o_ponto_com_os_campos_do_cartaz(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json=PONTO_COMPLETO)

        assert r.status_code == 201, r.text
        corpo = r.json()
        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        for campo, valor in {
            "nome_publico": "Emergência adulta",
            "descricao_local": "Hall da Emergência, parede ao lado da passagem para a espera",
            "titulo_cartaz": "atendimento_hoje",
            "codigo_controle": "PSA-01",
            "ala_internacao": False,
        }.items():
            assert gravado[campo] == valor, campo
            assert corpo[campo] == valor, campo

    def test_a_ala_de_internacao_e_o_outro_titulo_sao_gravados(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post(
            "/api/ouvidoria/pontos",
            json={**PONTO_COMPLETO, "titulo_cartaz": "um_minuto", "ala_internacao": True},
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        assert gravado["titulo_cartaz"] == "um_minuto"
        assert gravado["ala_internacao"] is True

    @pytest.mark.parametrize("descricao", ["", "   ", "..."])
    def test_descricao_do_local_vazia_e_recusada_no_cadastro(self, monkeypatch, descricao):
        """O local descrito é o que o painel vai mostrar: sem ele, ninguém sabe
        em que parede está o cartaz."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json={**PONTO_COMPLETO, "descricao_local": descricao})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_pontos"] == []

    def test_cadastro_sem_descricao_do_local_e_recusado(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)
        sem_descricao = {k: v for k, v in PONTO_COMPLETO.items() if k != "descricao_local"}

        r = client.post("/api/ouvidoria/pontos", json=sem_descricao)

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_pontos"] == []

    def test_titulo_fora_dos_dois_modelos_e_recusado(self, monkeypatch):
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json={**PONTO_COMPLETO, "titulo_cartaz": "outro"})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_pontos"] == []

    def test_o_ouvidor_edita_os_campos_do_cartaz(self, monkeypatch):
        supabase = _SupabaseFake(pontos=[_ponto()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.patch(
            "/api/ouvidoria/pontos/ponto-AB2CD3",
            json={
                "nome_publico": "Internação · Ala 2A",
                "descricao_local": "2º pavimento, corredor a 3 m do hall do elevador",
                "titulo_cartaz": "um_minuto",
                "codigo_controle": "INT-2A",
                "ala_internacao": True,
            },
        )

        assert r.status_code == 200, r.text
        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        assert gravado["nome_publico"] == "Internação · Ala 2A"
        assert gravado["descricao_local"] == "2º pavimento, corredor a 3 m do hall do elevador"
        assert gravado["titulo_cartaz"] == "um_minuto"
        assert gravado["codigo_controle"] == "INT-2A"
        assert gravado["ala_internacao"] is True
        assert r.json()["nome_publico"] == "Internação · Ala 2A"
        # O que está impresso não muda com a edição.
        assert gravado["codigo"] == "AB2CD3"
        assert gravado["setor"] == "Recepção"

    def test_apagar_o_nome_publico_volta_a_valer_o_rotulo(self, monkeypatch):
        """Nome público em branco é ausência, não conteúdo: a edição limpa o
        campo, e o rótulo volta a ser o que o paciente vê."""
        supabase = _SupabaseFake(pontos=[_ponto(nome_publico="Emergência adulta", codigo_controle="PSA-01")])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"nome_publico": "  ", "codigo_controle": ""})

        assert r.status_code == 200, r.text
        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        assert gravado["nome_publico"] is None
        assert gravado["codigo_controle"] is None

    @pytest.mark.parametrize("descricao", ["", "   ", None])
    def test_a_edicao_nao_esvazia_a_descricao_do_local(self, monkeypatch, descricao):
        supabase = _SupabaseFake(pontos=[_ponto()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"descricao_local": descricao})

        assert r.status_code == 422
        assert supabase.tabelas["ouvidoria_pontos"][0]["descricao_local"] == "Parede ao lado da poltrona 12"

    def test_a_lista_traz_os_campos_do_cartaz(self, monkeypatch):
        client, _ = _client(
            monkeypatch,
            OUVIDOR,
            _SupabaseFake(pontos=[_ponto(nome_publico="Emergência adulta", codigo_controle="PSA-01")]),
        )

        linha = client.get("/api/ouvidoria/pontos").json()["pontos"][0]

        assert linha["nome_publico"] == "Emergência adulta"
        assert linha["descricao_local"] == "Parede ao lado da poltrona 12"
        assert linha["titulo_cartaz"] == "atendimento_hoje"
        assert linha["codigo_controle"] == "PSA-01"
        assert linha["ala_internacao"] is False

    def test_os_titulos_batem_com_o_check_da_migration(self):
        """A lista fechada vive nos dois lados: contornar a API não pode gravar
        um título que o cartaz não sabe desenhar."""
        from app.services.ouvidoria_pontos import TITULOS_DO_CARTAZ

        migration = "135_ouvidoria_ponto_nome_publico_cartaz_a4.sql"
        caminho = os.path.join(os.path.dirname(__file__), "..", "..", "supabase", "migrations", migration)
        with open(caminho, encoding="utf-8") as f:
            ddl = f.read()

        check = re.search(r"titulo_cartaz IN \(([^)]*)\)", ddl)
        assert check, "a migration precisa travar os títulos do cartaz"
        assert (
            set(re.findall(r"'([a-z_]+)'", check.group(1)))
            == set(TITULOS_DO_CARTAZ)
            == {
                "atendimento_hoje",
                "um_minuto",
            }
        )


class TestCadastroDoPonto:
    def test_o_ouvidor_cadastra_e_recebe_o_codigo(self, monkeypatch):
        """CA: o ouvidor cadastra informando setor e rótulo, e o sistema devolve
        um código de 6 caracteres sem letras ambíguas."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json=NOVO_PONTO)

        assert r.status_code == 201, r.text
        corpo = r.json()
        assert len(corpo["codigo"]) == 6
        assert set(corpo["codigo"]) <= set(ALFABETO_DO_CODIGO)
        assert corpo["setor"] == "Recepção"
        assert corpo["ponto"] == "Poltrona 12"
        assert corpo["ativo"] is True
        assert supabase.tabelas["ouvidoria_pontos"][0]["criado_por"] == "P10"

    def test_o_setor_gravado_e_o_nome_canonico_da_taxonomia(self, monkeypatch):
        """Digitado em caixa diferente, o cadastro grava como a casa escreve:
        é esse nome que o Dossiê vai mostrar."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json={**NOVO_PONTO, "setor": "recepção"})

        assert r.status_code == 201, r.text
        assert supabase.tabelas["ouvidoria_pontos"][0]["setor"] == "Recepção"

    def test_setor_fora_da_taxonomia_e_recusado_falando_de_setor(self, monkeypatch):
        """CA: setor que não existe recusa o cadastro, com mensagem que fala de
        setor. Sem isso o cartaz apontaria para uma área que não existe."""
        client, supabase = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json={**NOVO_PONTO, "setor": "Setor Inventado"})

        assert r.status_code == 422
        assert "setor" in r.json()["detail"].lower()
        assert supabase.tabelas["ouvidoria_pontos"] == []

    def test_taxonomia_fora_do_ar_nao_manda_procurar_um_setor_que_existe(self, monkeypatch):
        """`_setor_da_taxonomia` devolve None tanto para "setor não existe"
        quanto para "a leitura falhou". Colapsar os dois faria o ouvidor ler
        "O setor Recepção não existe" com a Recepção lá, e sair procurando.

        É a mesma armadilha que a edição de responsável já nomeia: traduzir
        falha de leitura em "não encontrado" manda a pessoa caçar um cadastro
        que está no lugar."""
        supabase = _SupabaseFake()
        supabase.setores_indisponiveis = True
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.post("/api/ouvidoria/pontos", json=NOVO_PONTO)

        assert r.status_code == 503
        assert "não existe" not in r.json()["detail"]

    def test_rotulo_vazio_e_recusado(self, monkeypatch):
        """O rótulo é o que faz alguém achar o cartaz na parede."""
        client, _ = _client(monkeypatch, OUVIDOR)

        r = client.post("/api/ouvidoria/pontos", json={**NOVO_PONTO, "ponto": "   "})

        assert r.status_code == 422

    def test_codigo_que_colide_e_sorteado_de_novo(self, monkeypatch):
        """Quem decide a colisão é o índice único do banco, não uma consulta
        antes do insert: entre a consulta e a gravação cabe outro cadastro."""
        from app.services import ouvidoria_pontos

        sorteios = iter(["AAAAAA", "AAAAAA", "BBBBBB"])
        monkeypatch.setattr(ouvidoria_pontos, "gerar_codigo", lambda: next(sorteios))
        client, supabase = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto("AAAAAA")]))

        r = client.post("/api/ouvidoria/pontos", json=NOVO_PONTO)

        assert r.status_code == 201, r.text
        assert r.json()["codigo"] == "BBBBBB"


class TestQuemGereOCartaz:
    """CA: quem não tem Perfil da Ouvidoria toma 403 em toda rota de pontos."""

    @pytest.mark.parametrize("participante", [SECRETARIA, SUPER_ADMIN, None])
    def test_quem_esta_fora_da_ouvidoria_nao_entra(self, monkeypatch, participante):
        client, _ = _client(monkeypatch, participante)

        assert client.get("/api/ouvidoria/pontos").status_code == 403
        assert client.post("/api/ouvidoria/pontos", json=NOVO_PONTO).status_code == 403

    def test_a_diretoria_tambem_gere(self, monkeypatch):
        """Decisão 7 do ADR 0036: cartaz é operação do canal, e os dois perfis
        da Ouvidoria fazem."""
        client, _ = _client(monkeypatch, DIRETORIA)

        assert client.post("/api/ouvidoria/pontos", json=NOVO_PONTO).status_code == 201


class TestListaDeCartazes:
    def test_a_lista_traz_o_qr_embutido(self, monkeypatch):
        """CA: a lista mostra o PNG do QR de cada ponto, sem clique extra. O
        front autentica por header e `<img src>` não manda header, então a
        imagem viaja no JSON como data URI."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/pontos")

        assert r.status_code == 200, r.text
        linha = r.json()["pontos"][0]
        assert linha["codigo"] == "AB2CD3"
        assert linha["qr_data_uri"].startswith("data:image/png;base64,")

    def test_o_ponto_inativo_continua_na_lista(self, monkeypatch):
        """Desativar não é apagar: o ouvidor precisa ver o cartaz aposentado
        para saber que aquele código já foi usado."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto("ZZ9YY8", ativo=False)]))

        r = client.get("/api/ouvidoria/pontos")

        assert [p["codigo"] for p in r.json()["pontos"]] == ["ZZ9YY8"]
        assert r.json()["pontos"][0]["ativo"] is False


class TestDesativarEReativar:
    def test_desativar_e_reativar_nao_muda_o_codigo(self, monkeypatch):
        """CA: o código é imutável. Mudá-lo invalidaria o cartaz que já está
        na parede."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"ativo": False}).status_code == 200
        assert supabase.tabelas["ouvidoria_pontos"][0]["ativo"] is False
        assert client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"ativo": True}).status_code == 200

        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        assert gravado["ativo"] is True
        assert gravado["codigo"] == "AB2CD3"

    def test_editar_o_rotulo_nao_muda_o_codigo_nem_o_setor(self, monkeypatch):
        """Renomear o ponto é justamente o que o código curto veio permitir sem
        reimprimir o cartaz (ADR 0036, decisão 2)."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"ponto": "Poltrona 14"})

        assert r.status_code == 200, r.text
        gravado = supabase.tabelas["ouvidoria_pontos"][0]
        assert gravado["ponto"] == "Poltrona 14"
        assert gravado["codigo"] == "AB2CD3"
        assert gravado["setor"] == "Recepção"

    def test_o_codigo_nao_pode_ser_editado(self, monkeypatch):
        """Campo que não está no modelo não chega ao banco: mandar `codigo` no
        PATCH não pode reescrever o que está impresso."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.patch("/api/ouvidoria/pontos/ponto-AB2CD3", json={"codigo": "XXXXXX", "ponto": "Poltrona 14"})

        assert supabase.tabelas["ouvidoria_pontos"][0]["codigo"] == "AB2CD3"

    def test_nao_existe_rota_que_apague_um_ponto(self, monkeypatch):
        """CA: o histórico de casos aponta para o ponto. O fake estoura se um
        DELETE chegar à tabela, então esta é a prova pelos dois lados."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto()]))

        r = client.delete("/api/ouvidoria/pontos/ponto-AB2CD3")

        assert r.status_code == 405


class TestArtefatosParaImprimir:
    """CA: o botão de PNG baixa a imagem do QR; o de cartaz baixa um PDF A5
    com logo, convite, QR e setor."""

    def test_o_png_do_qr_sai_como_imagem(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/pontos/ponto-AB2CD3/qr.png")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "image/png"
        # A assinatura do PNG: o teste falha se a rota devolver JSON ou HTML.
        assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
        assert "AB2CD3" in r.headers["content-disposition"]

    def test_o_cartaz_sai_como_pdf(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/pontos/ponto-AB2CD3/cartaz.pdf")

        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"

    def test_o_cartaz_de_ponto_que_nao_existe_e_404(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR)

        assert client.get("/api/ouvidoria/pontos/ponto-nenhum/cartaz.pdf").status_code == 404
        assert client.get("/api/ouvidoria/pontos/ponto-nenhum/qr.png").status_code == 404

    @pytest.mark.parametrize("artefato", ["qr.png", "cartaz.pdf"])
    def test_quem_esta_fora_da_ouvidoria_nao_baixa(self, monkeypatch, artefato):
        client, _ = _client(monkeypatch, SECRETARIA, _SupabaseFake(pontos=[_ponto()]))

        assert client.get(f"/api/ouvidoria/pontos/ponto-AB2CD3/{artefato}").status_code == 403

    def test_o_cartaz_aposentado_continua_baixavel(self, monkeypatch):
        """Reimprimir um cartaz que voltou à parede é o caso de uso do
        reativar: exigir ponto ativo aqui obrigaria a reativar antes de ver o
        que vai ser impresso."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto(ativo=False)]))

        assert client.get("/api/ouvidoria/pontos/ponto-AB2CD3/cartaz.pdf").status_code == 200


class TestOQueVaiNoCartaz:
    """O cartaz A5 da issue #378. Continua disponível depois do A4 (seção 4.13
    da especificação da Diretoria), só não é mais o padrão."""

    def _html(self) -> str:
        from app.services.ouvidoria_pontos import html_do_cartaz

        return html_do_cartaz(_ponto(), formato="a5")

    def test_o_cartaz_convida_em_vez_de_dizer_so_ouvidoria(self):
        """A spec da Diretoria (RN-14) observa que o cartaz converte muito mais
        com convite direto do que com a palavra "Ouvidoria" sozinha."""
        html = self._html().lower()

        assert "sua opinião" in html or "fale com a gente" in html

    def test_o_cartaz_diz_o_setor_e_onde_ele_vai_colado(self):
        html = self._html()

        assert "Recepção" in html
        # O rótulo do ponto é para quem cola o cartaz saber onde vai.
        assert "Poltrona 12" in html

    def test_o_cartaz_leva_o_codigo_por_extenso(self):
        """A câmera falha, e alguém precisa digitar o endereço à mão."""
        assert "AB2CD3" in self._html()

    def test_o_cartaz_leva_o_qr_embutido_e_a_marca_do_hospital(self):
        html = self._html()

        assert "data:image/png;base64," in html
        assert "logo" in html.lower()

    def test_o_cartaz_e_a5(self):
        """A5 é o tamanho que a gráfica recebe pronto."""
        assert "a5" in self._html().lower()

    def test_o_cartaz_nao_tem_travessao(self):
        """Regra da casa: travessão é marca de texto gerado por IA, e este é um
        papel que vai para a parede do hospital."""
        html = self._html()

        assert "—" not in html
        assert "–" not in html


class TestOQrResolveOCodigo:
    """CA: o QR antigo leva ao endereço curto `/a/{código}`, a página pergunta
    ao servidor o nome público do ponto, e o formato velho `?setor=&ponto=` não
    vale mais."""

    @staticmethod
    def _client_publico(supabase: _SupabaseFake):
        from app.routers import ouvidoria_publica

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(RequestContextMiddleware)
        app.include_router(ouvidoria_publica.router, prefix="/api")
        app.dependency_overrides[get_supabase_client] = lambda: supabase
        return TestClient(app, follow_redirects=False)

    def test_o_qr_antigo_de_ponto_ativo_redireciona_ao_endereco_curto(self):
        """CA: `/ouvidoria/qr?p=` redireciona para `/a/{código}` (ADR 0086,
        decisão 5). Os cartazes de teste já impressos continuam valendo."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/qr", params={"p": "AB2CD3"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/a/AB2CD3")

    def test_o_codigo_vai_em_maiuscula_ao_endereco_curto(self):
        """O cartaz é lido em maiúscula, mas quem digita o endereço à mão pode
        escrever em minúscula."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/qr", params={"p": " ab2cd3 "})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/a/AB2CD3")

    def test_qr_antigo_de_ponto_desativado_tambem_vai_ao_endereco_curto(self):
        """Decisão 6 da ADR 0036: nunca uma página de erro. Quem decide que o
        ponto aposentado entra sem origem é o endereço curto, como para o
        cartaz novo, e não o redirecionamento."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto(ativo=False)]))

        r = client.get("/api/ouvidoria/qr", params={"p": "AB2CD3"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/a/AB2CD3")

    def test_lixo_no_parametro_cai_no_formulario_limpo(self):
        """Decisão 6: NUNCA uma página de erro. O que não tem forma de código
        não vira caminho do app: vai ao formulário, sem origem."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        for lixo in ["https://phishing.exemplo/caminho/muito/longo", "a" * 200, "AB2CD3ZZZZ", "%%%", "../x"]:
            r = client.get("/api/ouvidoria/qr", params={"p": lixo})

            assert r.status_code == 302, f"{lixo} devolveu {r.status_code}"
            assert r.headers["location"].endswith("/manifestacao"), lixo

    def test_o_formato_velho_nao_vale_mais(self):
        """CA: `?setor=Recepção&ponto=Poltrona 12` não grava origem nenhuma.
        Manter as duas portas deixaria aberta a brecha do texto arbitrário que
        o código curto veio fechar (ADR 0036, decisão 4)."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/qr", params={"setor": "Recepção", "ponto": "Poltrona 12"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/manifestacao")
        assert "setor" not in r.headers["location"]

    def test_a_rota_publica_devolve_o_nome_publico_e_nunca_o_setor(self):
        """CA: a pessoa na frente do cartaz vê o nome público do ponto, nunca o
        nome interno do setor (ADR 0086, decisão 10)."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto(nome_publico="Emergência adulta")]))

        r = client.get("/api/ouvidoria/publico/pontos/AB2CD3")

        assert r.status_code == 200
        assert r.json() == {"nome_publico": "Emergência adulta"}
        assert "Recepção" not in r.text

    def test_sem_nome_publico_a_rota_devolve_o_rotulo_do_ponto(self):
        client = self._client_publico(_SupabaseFake(pontos=[_ponto(nome_publico=None)]))

        r = client.get("/api/ouvidoria/publico/pontos/AB2CD3")

        assert r.status_code == 200
        assert r.json() == {"nome_publico": "Poltrona 12"}
        assert "Recepção" not in r.text

    def test_ponto_desativado_nao_devolve_rotulo(self):
        client = self._client_publico(_SupabaseFake(pontos=[_ponto(ativo=False)]))

        assert client.get("/api/ouvidoria/publico/pontos/AB2CD3").status_code == 404

    def test_codigo_inventado_nao_devolve_rotulo(self):
        """CA: montar `?p=<código inventado>` não exibe rótulo nenhum."""
        client = self._client_publico(_SupabaseFake())

        assert client.get("/api/ouvidoria/publico/pontos/ZZ9YY8").status_code == 404

    def test_a_rota_publica_nao_entrega_o_id_nem_quem_cadastrou(self):
        """A porta é pública: ela devolve o que a página precisa mostrar, e
        nada do cadastro."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        corpo = client.get("/api/ouvidoria/publico/pontos/AB2CD3").text

        assert "ponto-AB2CD3" not in corpo
        assert "criado_por" not in corpo


class TestManifestacaoQueNasceDoCartaz:
    """CA: a manifestação enviada por esse caminho nasce com `canal = 'qr'`,
    `canal_setor` e `canal_ponto` VINDOS DO CADASTRO, e não do cliente."""

    @staticmethod
    def _client_publico(supabase: _SupabaseFake):
        from app.routers import ouvidoria_publica

        app = FastAPI()
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
        app.add_middleware(RequestContextMiddleware)
        app.include_router(ouvidoria_publica.router, prefix="/api")
        app.dependency_overrides[get_supabase_client] = lambda: supabase
        return TestClient(app)

    RELATO = "Esperei duas horas na recepção sem nenhuma informação sobre a demora."

    def test_o_codigo_do_cartaz_vira_a_origem_da_manifestacao(self):
        supabase = _SupabaseFake(pontos=[_ponto()])
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "sobre": "mim", "p": "AB2CD3"}
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal"] == "qr"
        assert gravado["canal_setor"] == "Recepção"
        assert gravado["canal_ponto"] == "Poltrona 12"

    def test_codigo_de_cartaz_aposentado_entra_como_site(self):
        """CA: ler o QR de um ponto desativado abre o formulário normal e a
        manifestação nasce com `canal = 'site'`."""
        supabase = _SupabaseFake(pontos=[_ponto(ativo=False)])
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "sobre": "mim", "p": "AB2CD3"}
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal"] == "site"
        assert gravado["canal_setor"] is None
        assert gravado["canal_ponto"] is None

    def test_codigo_inventado_entra_como_site(self):
        """CA: montar `?p=<código inventado>` não grava origem."""
        supabase = _SupabaseFake()
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "sobre": "mim", "p": "ZZ9YY8"}
        )

        assert r.status_code == 201, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["canal"] == "site"

    def test_setor_e_ponto_no_corpo_nao_gravam_mais_nada(self):
        """A porta velha fecha aqui também: o texto que vinha do cliente não
        pode virar origem por outro caminho (ADR 0036, decisão 10)."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": self.RELATO, "sobre": "mim", "setor": "Recepção", "ponto": "Poltrona 12"},
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal"] == "site"
        assert gravado["canal_setor"] is None
        assert gravado["canal_ponto"] is None

    def test_caso_anonimo_do_cartaz_nao_grava_o_ponto(self):
        """A decisão 5 da #375 continua valendo sobre o ponto cadastrado: em
        sala pequena, a poltrona reidentifica quem pediu anonimato."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": self.RELATO, "sobre": "mim", "p": "AB2CD3", "anonimo": True},
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal_ponto"] is None
        assert gravado["canal_setor"] == "Recepção"
        assert gravado["canal"] == "qr"


# O cartaz da Emergência adulta e o da Ala 2A, como o anexo da especificação da
# Diretoria (seção 11) os descreve.
EMERGENCIA_ADULTA = {
    "nome_publico": "Emergência adulta",
    "descricao_local": "Hall da Emergência, parede ao lado da passagem para a espera, voltada para a sala verde",
    "titulo_cartaz": "atendimento_hoje",
    "codigo_controle": "PSA-01",
}
ALA_2A = {
    "nome_publico": "Internação · Ala 2A",
    "descricao_local": "2º pavimento, ala longa, parede do corredor a 3 m do hall do elevador",
    "titulo_cartaz": "um_minuto",
    "codigo_controle": "INT-2A",
    "ala_internacao": True,
}

# A4 e A5 retrato, em pontos de PDF (1/72 de polegada), como o `/MediaBox` os
# escreve.
A4_EM_PONTOS = (595.28, 841.89)
A5_EM_PONTOS = (419.53, 595.28)
MM = 96 / 25.4  # milímetro em pixel CSS, a unidade do layout do WeasyPrint


def _pdf_legivel(pdf: bytes) -> bytes:
    """O PDF com os streams comprimidos abertos: o WeasyPrint guarda o
    dicionário da página e o da fonte dentro de object streams."""
    import zlib

    abertos = []
    for stream in re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S):
        try:
            abertos.append(zlib.decompress(stream))
        except zlib.error:
            continue
    return pdf + b"".join(abertos)


def _tamanho_da_pagina(pdf: bytes) -> tuple[float, float]:
    caixa = re.search(rb"/MediaBox\s*\[\s*0\s+0\s+([\d.]+)\s+([\d.]+)\s*\]", _pdf_legivel(pdf))
    assert caixa, "o PDF não declara o tamanho da página"
    return round(float(caixa.group(1)), 2), round(float(caixa.group(2)), 2)


def _caixas(caixa):
    """Todas as caixas do layout. O `descendants()` do WeasyPrint para no
    marcador de caixa posicionada (`position: absolute`), e o cartaz tem três:
    a moldura, o rodapé e a linha de controle."""
    caixa = getattr(caixa, "_box", caixa)
    yield caixa
    for filha in getattr(caixa, "children", None) or []:
        yield from _caixas(filha)


def _caixa(folha, tag: str, classe: str):
    [achada] = [
        c
        for c in _caixas(folha._page_box)
        if getattr(c, "element_tag", None) == tag
        and c.element.get("class") == classe
        and type(c).__name__ in ("BlockBox", "BlockReplacedBox")
    ]
    return achada


class TestOCartazA4:
    """CA: o PDF A4 sai com o título do ponto, o QR de 9 cm, o endereço
    `/a/{código}` e a linha de controle, no layout 4.13 da especificação da
    Diretoria (ADR 0086, decisão 10)."""

    @staticmethod
    def _html(**campos) -> str:
        from app.services.ouvidoria_pontos import html_do_cartaz

        return html_do_cartaz(_ponto(**campos))

    @staticmethod
    def _texto(**campos) -> str:
        """O texto do cartaz como a pessoa lê, sem as tags e com os espaços
        juntos: a asserção é sobre o que vai no papel, não sobre a marcação."""
        sem_tags = re.sub(r"<[^>]+>", " ", TestOCartazA4._html(**campos).split("</style>", 1)[1])
        return re.sub(r"\s+", " ", sem_tags)

    def test_o_cartaz_padrao_sai_em_a4_e_o_a5_continua_disponivel(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto(**EMERGENCIA_ADULTA)]))

        a4 = client.get("/api/ouvidoria/pontos/ponto-AB2CD3/cartaz.pdf")
        a5 = client.get("/api/ouvidoria/pontos/ponto-AB2CD3/cartaz.pdf", params={"formato": "a5"})

        assert a4.status_code == 200, a4.text
        assert a5.status_code == 200, a5.text
        assert _tamanho_da_pagina(a4.content) == A4_EM_PONTOS
        assert _tamanho_da_pagina(a5.content) == A5_EM_PONTOS

    def test_formato_que_nao_existe_e_recusado(self, monkeypatch):
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/pontos/ponto-AB2CD3/cartaz.pdf", params={"formato": "a3"})

        assert r.status_code == 422

    def test_o_cartaz_cabe_numa_folha_a4_com_o_qr_de_9_cm(self):
        """Medido no layout que o WeasyPrint monta, e não lido do CSS: o QR de
        9 cm é o que a especificação garante ler a 50 cm e a 1 m, e o cartaz
        que transborda para uma segunda folha não vai inteiro para a parede."""
        from weasyprint import HTML

        from app.services.ouvidoria_pontos import _assets_do_cartaz_a4, html_do_cartaz
        from app.services.pdf_url_fetcher import criar_pdf_url_fetcher

        for campos in (EMERGENCIA_ADULTA, ALA_2A):
            documento = HTML(
                string=html_do_cartaz(_ponto(**campos)), url_fetcher=criar_pdf_url_fetcher(_assets_do_cartaz_a4())
            ).render()

            assert len(documento.pages) == 1, campos["codigo_controle"]
            folha = documento.pages[0]
            assert (round(folha.width / MM), round(folha.height / MM)) == (210, 297)
            qr = _caixa(folha, "img", "qr")
            assert (round(qr.width / MM, 1), round(qr.height / MM, 1)) == (90.0, 90.0)
            # O rodapé é posicionado no pé da moldura: o texto de cima não
            # pode correr por trás dele.
            lgpd = _caixa(folha, "p", "lgpd")
            rodape = _caixa(folha, "div", "rodape")
            assert lgpd.position_y + lgpd.margin_height() <= rodape.position_y, campos["codigo_controle"]
            # A linha de controle fica fora da moldura, ainda dentro da folha.
            moldura = _caixa(folha, "div", "moldura")
            controle = _caixa(folha, "p", "controle")
            assert controle.position_y >= moldura.position_y + moldura.margin_height()
            assert controle.position_y + controle.margin_height() <= folha.height

    def test_o_titulo_atendimento_hoje_sai_com_o_subtitulo_dele(self):
        texto = self._texto(**EMERGENCIA_ADULTA)

        assert "Como foi seu atendimento hoje?" in texto
        assert "Leva menos de um minuto" in texto
        assert "Um minuto para nos contar" not in texto

    def test_o_titulo_um_minuto_sai_com_o_subtitulo_dele(self):
        texto = self._texto(**ALA_2A)

        assert "Um minuto para nos contar" in texto
        assert "Como está sendo sua estadia?" in texto
        assert "Como foi seu atendimento hoje?" not in texto

    def test_titulo_e_subtitulo_saem_em_caixa_alta_so_na_exibicao(self):
        """ADR 0080: o texto fica em maiúscula e minúscula e o CSS sobe a caixa."""
        html = self._html(**EMERGENCIA_ADULTA)

        for classe in ("titulo", "subtitulo"):
            regra = re.search(rf"\.{classe}\s*\{{([^}}]*)\}}", html)
            assert regra, classe
            assert "text-transform: uppercase" in regra.group(1), classe

    def test_o_endereco_impresso_e_o_curto(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "frontend_url", "https://app.hospitalsaomatheus.cloud")

        texto = self._texto(**EMERGENCIA_ADULTA)

        assert "ou acesse app.hospitalsaomatheus.cloud/a/AB2CD3" in texto
        assert "ouvidoria/qr" not in self._html(**EMERGENCIA_ADULTA)

    def test_o_qr_e_vetorial_na_cor_da_marca(self):
        """PDF vetorial: o QR vai como SVG, que a gráfica amplia sem serrilhar,
        com os módulos em `#282760`."""
        html = self._html(**EMERGENCIA_ADULTA)

        qr = re.search(r'<img class="qr" src="([^"]+)"', html)
        assert qr, "o cartaz A4 precisa do QR"
        assert qr.group(1).startswith("data:image/svg+xml")
        assert "282760" in qr.group(1)

    def test_a_linha_de_controle_traz_o_codigo_o_nome_e_o_local_resumido(self):
        texto = self._texto(**EMERGENCIA_ADULTA)

        assert "Ponto PSA-01 · Emergência adulta · Hall da Emergência, parede ao lado da passagem" in texto
        # Resumida: a descrição inteira não cabe numa linha de 7 pt.
        assert "voltada para a sala verde" not in texto

    def test_sem_codigo_de_controle_a_linha_leva_o_codigo_do_qr(self):
        texto = self._texto(**{**EMERGENCIA_ADULTA, "codigo_controle": None})

        assert "Ponto AB2CD3 · Emergência adulta" in texto

    def test_a_ala_de_internacao_manda_falar_com_a_enfermagem_do_posto(self):
        assert "Fale com a enfermagem do posto desta ala." in self._texto(**ALA_2A)
        assert "Fale com a equipe deste setor." not in self._texto(**ALA_2A)

    def test_fora_da_internacao_manda_falar_com_a_equipe_do_setor(self):
        assert "Fale com a equipe deste setor." in self._texto(**EMERGENCIA_ADULTA)
        assert "enfermagem do posto" not in self._texto(**EMERGENCIA_ADULTA)

    def test_o_cartaz_traz_os_avisos_a_lgpd_e_o_rodape_da_ouvidoria(self):
        texto = self._texto(**EMERGENCIA_ADULTA)

        for trecho in (
            "Aponte a câmera do celular",
            "Quer um retorno?",
            "Deixe seu contato ao final ou registre de forma anônima.",
            "Precisa de ajuda agora?",
            "Seus dados são usados apenas para tratar sua avaliação, conforme a LGPD.",
            "Ouvidoria",
            "ouvidoria@hospitalsaomatheus.com.br",
        ):
            assert trecho in texto, trecho

    def test_o_cartaz_nao_mostra_o_nome_interno_do_setor(self):
        """O paciente vê o nome público, nunca o nome interno do setor."""
        assert "Recepção" not in self._html(**EMERGENCIA_ADULTA)
        assert "Recepção" not in self._html(**{**EMERGENCIA_ADULTA, "nome_publico": None})

    def test_a_fonte_hp_simplified_vai_embutida_no_pdf(self):
        from app.services.ouvidoria_pontos import pdf_do_cartaz

        pdf = _pdf_legivel(pdf_do_cartaz(_ponto(**EMERGENCIA_ADULTA)))

        # Subconjunto embutido: o nome da fonte vem depois do prefixo de seis
        # letras que o PDF dá a toda fonte recortada.
        assert re.search(rb"/BaseFont\s*/[A-Z]{6}\+HP-Simplified", pdf)

    def test_o_cartaz_a4_nao_tem_travessao(self):
        html = self._html(**ALA_2A)

        assert "\u2014" not in html
        assert "\u2013" not in html
