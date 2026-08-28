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

    def test_o_qr_aponta_para_o_caminho_reservado_ao_cartaz(self):
        """ADR 0036, decisão 2: `https://<app>/ouvidoria/qr?p=<codigo>`. O
        `next.config.ts` tem um rewrite dedicado a este caminho, com o comentário
        dizendo que ele mora no domínio do app e SEM o prefixo `/api`.

        Passar pelo proxy genérico `/api/:path*` funciona hoje e é errado por
        dois motivos: são bytes a mais num símbolo que a decisão 2 existe para
        encolher, e amarra todo cartaz impresso à forma do proxy da API."""
        from app.services.ouvidoria_pontos import url_do_cartaz

        url = url_do_cartaz("AB2CD3")

        assert url.endswith("/ouvidoria/qr?p=AB2CD3")
        assert "/api/" not in url

    def test_o_endereco_impresso_resolve_sozinho(self):
        """O endereço que vai no papel para quem não conseguiu ler o QR precisa
        levar o código consigo: `/manifestacao` não tem campo de código, então
        mandar a pessoa "informar o código" lá a deixaria numa tela sem onde
        digitar, e o caso entraria como se tivesse vindo do site."""
        from app.services.ouvidoria_pontos import endereco_impresso

        endereco = endereco_impresso("AB2CD3")

        assert "AB2CD3" in endereco
        assert "ouvidoria/qr?p=" in endereco
        # Sem esquema: quem digita não escreve "https://".
        assert not endereco.startswith("http")


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


NOVO_PONTO = {"setor": "Recepção", "ponto": "Poltrona 12"}


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
    """O cartaz é o produto desta fatia: é ele que vai para a gráfica."""

    def _html(self) -> str:
        from app.services.ouvidoria_pontos import html_do_cartaz

        return html_do_cartaz(_ponto())

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
    """CA: ler o QR de um ponto ativo abre o formulário e a página diz de qual
    setor é o cartaz; o formato velho `?setor=&ponto=` não vale mais."""

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

    def test_codigo_de_ponto_ativo_leva_o_codigo_ao_formulario(self):
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/qr", params={"p": "AB2CD3"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/manifestacao?p=AB2CD3")

    def test_codigo_de_ponto_desativado_abre_o_formulario_sem_origem(self):
        """CA e decisão 6: nunca uma página de erro. Ninguém parado na frente
        de um cartaz pode ficar sem canal por causa de faxina no cadastro."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto(ativo=False)]))

        r = client.get("/api/ouvidoria/qr", params={"p": "AB2CD3"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/manifestacao")

    def test_codigo_inventado_abre_o_formulario_sem_origem(self):
        client = self._client_publico(_SupabaseFake())

        r = client.get("/api/ouvidoria/qr", params={"p": "ZZ9YY8"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/manifestacao")

    def test_lixo_no_parametro_tambem_cai_no_formulario_limpo(self):
        """Decisão 6: NUNCA uma página de erro. O teto de tamanho no parâmetro
        fazia o FastAPI responder 422 para um `?p=` comprido, e quem estivesse
        parado na frente do cartaz veria erro em vez do formulário. A régua do
        alfabeto já recusa antes de tocar o banco, então o teto não comprava
        nada e cobrava isso."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        for lixo in ["https://phishing.exemplo/caminho/muito/longo", "a" * 200, "AB2CD3ZZZZ", "%%%"]:
            r = client.get("/api/ouvidoria/qr", params={"p": lixo})

            assert r.status_code == 302, f"{lixo} devolveu {r.status_code}"
            assert r.headers["location"].endswith("/manifestacao")

    def test_o_formato_velho_nao_vale_mais(self):
        """CA: `?setor=Recepção&ponto=Poltrona 12` não grava origem nenhuma.
        Manter as duas portas deixaria aberta a brecha do texto arbitrário que
        o código curto veio fechar (ADR 0036, decisão 4)."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/qr", params={"setor": "Recepção", "ponto": "Poltrona 12"})

        assert r.status_code == 302
        assert r.headers["location"].endswith("/manifestacao")
        assert "setor" not in r.headers["location"]

    def test_a_pagina_pergunta_o_rotulo_do_cartaz_ao_servidor(self):
        """CA: nenhum texto que a página exibe vem da query string. Ela manda o
        código e o servidor devolve o rótulo."""
        client = self._client_publico(_SupabaseFake(pontos=[_ponto()]))

        r = client.get("/api/ouvidoria/publico/pontos/AB2CD3")

        assert r.status_code == 200
        assert r.json() == {"setor": "Recepção", "ponto": "Poltrona 12"}

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

        r = client.post("/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "p": "AB2CD3"})

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

        r = client.post("/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "p": "AB2CD3"})

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal"] == "site"
        assert gravado["canal_setor"] is None
        assert gravado["canal_ponto"] is None

    def test_codigo_inventado_entra_como_site(self):
        """CA: montar `?p=<código inventado>` não grava origem."""
        supabase = _SupabaseFake()
        client = self._client_publico(supabase)

        r = client.post("/api/ouvidoria/publico/manifestacoes", json={"relato": self.RELATO, "p": "ZZ9YY8"})

        assert r.status_code == 201, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["canal"] == "site"

    def test_setor_e_ponto_no_corpo_nao_gravam_mais_nada(self):
        """A porta velha fecha aqui também: o texto que vinha do cliente não
        pode virar origem por outro caminho (ADR 0036, decisão 10)."""
        supabase = _SupabaseFake(pontos=[_ponto()])
        client = self._client_publico(supabase)

        r = client.post(
            "/api/ouvidoria/publico/manifestacoes",
            json={"relato": self.RELATO, "setor": "Recepção", "ponto": "Poltrona 12"},
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
            json={"relato": self.RELATO, "p": "AB2CD3", "anonimo": True},
        )

        assert r.status_code == 201, r.text
        gravado = supabase.tabelas["ouvidoria_protocolos"][0]
        assert gravado["canal_ponto"] is None
        assert gravado["canal_setor"] == "Recepção"
        assert gravado["canal"] == "qr"
