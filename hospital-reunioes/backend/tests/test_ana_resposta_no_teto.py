"""Testes da API da Ana: resposta dentro do teto de leitura do cliente (issue #314).

A plataforma que hospeda a Ana corta o corpo de toda resposta de HTTP tool em
4.000 caracteres, sem aviso (ADR 0032). Estes testes provam o contrato de
leitura pelo seam HTTP: filtro por termo, degrau de detalhe declarado no corpo
e, acima de tudo, que a degradação tira campo e nunca tira linha.
"""

from __future__ import annotations

import os
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
from app.routers import ana as ana_router  # noqa: E402
from app.scripts.import_consultas_particulares import parse_export as parse_export_consultas  # noqa: E402
from app.scripts.import_tabelas_ana import parse_export as parse_export_tabelas  # noqa: E402

CHAVE = "chave-teste-ana-para-pytest"

# O teto do cliente com folga (ADR 0032 decisão 3). Repetido aqui de propósito:
# o teste afirma sobre o contrato, não sobre a constante do código de produção.
LIMITE = 3500


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _make_app(tabelas: dict[str, list]) -> TestClient:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(ana_router.router, prefix="/api")

    class _Query:
        def __init__(self, rows: list):
            self._rows = rows
            self._filters: dict = {}

        def select(self, *_args, **_kwargs):
            return self

        def eq(self, col, value):
            self._filters[col] = value
            return self

        def order(self, *_args, **_kwargs):
            return self

        def execute(self):
            data = [dict(r) for r in self._rows if all(r.get(c) == v for c, v in self._filters.items())]
            self._filters = {}
            return type("R", (), {"data": data})()

    class _SupabaseMock:
        def table(self, name: str):
            assert name in tabelas, f"Tabela inesperada: {name}"
            return _Query(tabelas[name])

    app.dependency_overrides[get_supabase_client] = _SupabaseMock
    return TestClient(app)


def _get(client: TestClient, url: str):
    return client.get(url, headers={"X-API-Key": CHAVE})


def _tamanho_do_corpo(resposta) -> int:
    """Mede o que a Ana recebe: o corpo serializado, em caracteres."""
    return len(resposta.content.decode("utf-8"))


def _nomes_da_lista(itens: list, *campos: str) -> list[str]:
    """Os nomes dos registros, seja qual for o degrau: no índice cada item já é
    o nome em texto; nos outros é um objeto."""
    return [item if isinstance(item, str) else " / ".join(str(item[c]) for c in campos) for item in itens]


def _exame_row(nome: str, valor: float, ativo: bool = True) -> dict:
    return {
        "id": f"id-{nome.lower().replace(' ', '-')}",
        "nome_exame": nome,
        "tipo_exame": "Cardiológico",
        "convenio_aceito": True,
        "valor_particular_rs": valor,
        "requer_pedido_medico": True,
        "preparo_necessario": False,
        "instrucoes_preparo_completas": "Não requer preparo especial.",
        "tempo_resultado": "No ato / 48h",
        "local_realizacao": "Hospital São Matheus, Cardiologia",
        "diferencial_1": "Equipamento de última geração",
        "diferencial_2": "Laudo integrado ao prontuário",
        "observacoes_ana": "",
        "ativo": ativo,
        "ultima_atualizacao": "2026-03-10",
    }


class TestEnvelope:
    def test_resposta_declara_o_degrau_e_o_gesto_seguinte(self, monkeypatch):
        """Sem o modo explícito, a Ana lê campo ausente como dado inexistente."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app({"exames": [_exame_row("Ecocardiograma", 320.00)]})

        r = _get(client, "/api/ana/exames")

        assert r.status_code == 200
        corpo = r.json()
        assert corpo["modo"] == "completo"
        assert corpo["dica"]
        assert _tamanho_do_corpo(r) <= LIMITE
        assert [e["nome_exame"] for e in corpo["exames"]] == ["Ecocardiograma"]
        assert corpo["exames"][0]["instrucoes_preparo_completas"] == "Não requer preparo especial."


class TestFiltroPorTermo:
    def test_termo_acha_o_exame_ignorando_caixa_acento_e_pontuacao(self, monkeypatch):
        """O paciente fala "raio x"; o cadastro diz "Raio-X (RX)"."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "exames": [
                    _exame_row("Raio-X (RX)", 90.00),
                    _exame_row("Ecocardiograma", 320.00),
                ]
            }
        )

        r = _get(client, "/api/ana/exames?exame=raio x")

        assert r.status_code == 200
        assert [e["nome_exame"] for e in r.json()["exames"]] == ["Raio-X (RX)"]

    def test_termo_de_varias_palavras_exige_todas_no_nome(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "exames": [
                    _exame_row("Tomografia Computadorizada (TC)", 580.00),
                    _exame_row("Tomografia de Tórax", 620.00),
                ]
            }
        )

        r = _get(client, "/api/ana/exames?exame=tomografia torax")

        assert [e["nome_exame"] for e in r.json()["exames"]] == ["Tomografia de Tórax"]

    @pytest.mark.parametrize("query", ["", "?exame=", "?exame=%20%20%20"])
    def test_termo_ausente_vazio_ou_so_espacos_vale_como_sem_filtro(self, monkeypatch, query):
        """O cliente da Ana interpola variável não preenchida como string vazia,
        em silêncio: ler isso como busca por vazio esconderia a tabela inteira."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "exames": [
                    _exame_row("Raio-X (RX)", 90.00),
                    _exame_row("Ecocardiograma", 320.00),
                ]
            }
        )

        r = _get(client, f"/api/ana/exames{query}")

        assert [e["nome_exame"] for e in r.json()["exames"]] == ["Raio-X (RX)", "Ecocardiograma"]


class TestDegrauPorTamanho:
    @pytest.mark.parametrize(
        "quantidade,modo_esperado",
        [(2, "completo"), (12, "resumo"), (90, "indice")],
    )
    def test_degrau_cai_por_tamanho_e_nenhuma_linha_some(self, monkeypatch, quantidade, modo_esperado):
        """A degradação tira campo, jamais tira linha: a contagem é sempre a
        mesma do cadastro, nos três degraus."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        exames = [_exame_row(f"Exame {i:02d}", 100.00 + i) for i in range(quantidade)]
        client = _make_app({"exames": exames})

        r = _get(client, "/api/ana/exames")

        corpo = r.json()
        assert corpo["modo"] == modo_esperado
        assert len(corpo["exames"]) == quantidade
        assert _tamanho_do_corpo(r) <= LIMITE
        assert _nomes_da_lista(corpo["exames"], "nome_exame") == [f"Exame {i:02d}" for i in range(quantidade)]

    def test_o_completo_traz_os_campos_e_o_resumo_so_a_vitrine(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)

        completo = _get(_make_app({"exames": [_exame_row("Exame 00", 100.00)]}), "/api/ana/exames").json()
        resumo = _get(
            _make_app({"exames": [_exame_row(f"Exame {i:02d}", 100.00 + i) for i in range(12)]}),
            "/api/ana/exames",
        ).json()
        indice = _get(
            _make_app({"exames": [_exame_row(f"Exame {i:02d}", 100.00 + i) for i in range(90)]}),
            "/api/ana/exames",
        ).json()

        assert completo["exames"][0]["instrucoes_preparo_completas"] == "Não requer preparo especial."
        assert resumo["exames"][0] == {"nome_exame": "Exame 00", "valor_particular_rs": 100.00}
        # No índice o nome vem em texto: repetir o nome do campo em cada linha é
        # o que faz o degrau mais magro estourar quando a tabela cresce.
        assert indice["exames"][0] == "Exame 00"


class TestFiltroSemResultado:
    def test_devolve_200_com_lista_vazia_e_os_nomes_que_existem(self, monkeypatch):
        """A Ana vê que não achou, vê o nome certo e repergunta, em vez de
        insistir na mesma chamada."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "exames": [
                    _exame_row("Raio-X (RX)", 90.00),
                    _exame_row("Ecocardiograma", 320.00),
                ]
            }
        )

        r = _get(client, "/api/ana/exames?exame=ressonancia")

        assert r.status_code == 200
        corpo = r.json()
        assert corpo["exames"] == []
        assert corpo["disponiveis"] == ["Raio-X (RX)", "Ecocardiograma"]
        assert corpo["dica"]
        assert _tamanho_do_corpo(r) <= LIMITE

    def test_a_lista_de_nomes_nao_traz_nenhum_valor(self, monkeypatch):
        """Sem preço junto, não há como confundir a lista com resultado."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app({"exames": [_exame_row("Raio-X (RX)", 90.00)]})

        r = _get(client, "/api/ana/exames?exame=ressonancia")

        assert "90" not in r.content.decode("utf-8")
        assert r.json()["disponiveis"] == ["Raio-X (RX)"]


def _consulta_row(especialidade: str, valor: float, ativo: bool = True) -> dict:
    return {
        "id": f"id-{especialidade.lower()}",
        "especialidade": especialidade,
        "valor_rs": valor,
        "descricao_servico": f"Consulta de {especialidade}.",
        "diferencial_1": "Estrutura hospitalar completa",
        "diferencial_2": "Equipe experiente",
        "diferencial_3": "Exames integrados",
        "alta_demanda": False,
        "observacoes_ana": "",
        "ativo": ativo,
        "ultima_atualizacao": "2026-03-10",
    }


class TestConsultasParticulares:
    def test_termo_sem_acento_acha_a_especialidade(self, monkeypatch):
        """O paciente escreve `obstetricia`; o cadastro diz "Obstetrícia"."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "consultas_particulares": [
                    _consulta_row("Obstetrícia", 400.00),
                    _consulta_row("Pediatria", 350.00),
                ]
            }
        )

        r = _get(client, "/api/ana/consultas-particulares?especialidade=obstetricia")

        assert r.status_code == 200
        corpo = r.json()
        assert [c["especialidade"] for c in corpo["consultas_particulares"]] == ["Obstetrícia"]
        assert corpo["modo"] == "completo"
        assert corpo["dica"]

    def test_lista_grande_cabe_no_teto_sem_perder_especialidade(self, monkeypatch):
        """O defeito que esta fatia mata: a Ana afirmava que o hospital não
        atendia uma especialidade que estava cadastrada."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        especialidades = [f"Especialidade {i:02d}" for i in range(30)] + ["Pediatria", "Urologia"]
        client = _make_app({"consultas_particulares": [_consulta_row(nome, 300.00) for nome in especialidades]})

        r = _get(client, "/api/ana/consultas-particulares")

        corpo = r.json()
        assert _tamanho_do_corpo(r) <= LIMITE
        assert [c["especialidade"] for c in corpo["consultas_particulares"]] == especialidades


def _cirurgia_row(procedimento: str, total: float, caveat: str = "Esta é uma estimativa geral.") -> dict:
    return {
        "id": f"id-{procedimento.lower().replace(' ', '-')}",
        "procedimento": procedimento,
        "descricao_procedimento": f"Cirurgia de {procedimento}.",
        "honorarios_equipe_rs": total - 3000.00,
        "valor_internacao_rs": 3000.00,
        "estimativa_total_rs": total,
        "o_que_inclui_honorarios": "Cirurgião, auxiliares, instrumentador e anestesista",
        "o_que_inclui_internacao": "Centro cirúrgico, internação, materiais e medicamentos",
        "diferencial_1": "Técnica minimamente invasiva",
        "diferencial_2": "UTI integrada",
        "caveat_obrigatorio_ana": caveat,
        "observacoes_ana": "",
        "ativo": True,
        "ultima_atualizacao": "2026-03-10",
    }


class TestCirurgias:
    def test_termo_acha_o_procedimento(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "cirurgias_estimativas": [
                    _cirurgia_row("Colecistectomia Videolaparoscópica", 9000.00),
                    _cirurgia_row("Herniorrafia (Hérnia Inguinal)", 7500.00),
                ]
            }
        )

        r = _get(client, "/api/ana/cirurgias-estimativas?procedimento=hernia inguinal")

        assert [c["procedimento"] for c in r.json()["cirurgias_estimativas"]] == ["Herniorrafia (Hérnia Inguinal)"]

    @pytest.mark.parametrize("quantidade,modo_esperado", [(12, "resumo"), (90, "indice")])
    def test_aviso_obrigatorio_sai_uma_vez_no_envelope_quando_a_linha_encolhe(
        self, monkeypatch, quantidade, modo_esperado
    ):
        """Nenhuma resposta de cirurgia com valor sai sem o aviso."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {"cirurgias_estimativas": [_cirurgia_row(f"Cirurgia {i:02d}", 8000.00) for i in range(quantidade)]}
        )

        r = _get(client, "/api/ana/cirurgias-estimativas")

        corpo = r.json()
        assert corpo["modo"] == modo_esperado
        assert corpo["caveat_obrigatorio_ana"] == "Esta é uma estimativa geral."
        assert r.content.decode("utf-8").count("Esta é uma estimativa geral.") == 1
        assert len(corpo["cirurgias_estimativas"]) == quantidade

    def test_o_texto_do_aviso_vem_do_banco_e_nao_do_codigo(self, monkeypatch):
        """É conteúdo editável pelas secretárias: muda no cadastro, muda na
        resposta."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        texto_novo = "Valores sujeitos a avaliação da equipe médica em consulta."
        client = _make_app(
            {
                "cirurgias_estimativas": [
                    _cirurgia_row(f"Cirurgia {i:02d}", 8000.00, caveat=texto_novo) for i in range(12)
                ]
            }
        )

        r = _get(client, "/api/ana/cirurgias-estimativas")

        assert r.json()["caveat_obrigatorio_ana"] == texto_novo

    def test_no_degrau_completo_o_aviso_continua_na_linha(self, monkeypatch):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app({"cirurgias_estimativas": [_cirurgia_row("Colecistectomia", 9000.00)]})

        r = _get(client, "/api/ana/cirurgias-estimativas")

        corpo = r.json()
        assert corpo["modo"] == "completo"
        assert corpo["cirurgias_estimativas"][0]["caveat_obrigatorio_ana"] == "Esta é uma estimativa geral."


def _convenio_row(convenio: str, especialidade: str, cobre: bool = True) -> dict:
    return {
        "id": f"id-{convenio.lower()}-{especialidade.lower()}",
        "convenio": convenio,
        "especialidade": especialidade,
        "cobre": cobre,
        "observacao": f"Cobre consultas de {especialidade}.",
        "ativo": True,
        "ultima_atualizacao": "2026-03-10",
    }


class TestConvenios:
    def test_os_dois_filtros_valem_juntos(self, monkeypatch):
        """ "O plano X cobre cardiologia?" é uma chamada só."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        client = _make_app(
            {
                "convenios_especialidade": [
                    _convenio_row("Bradesco Saúde", "Cardiologia"),
                    _convenio_row("Bradesco Saúde", "Pediatria"),
                    _convenio_row("Unimed", "Cardiologia"),
                ]
            }
        )

        r = _get(client, "/api/ana/convenios-especialidade?convenio=bradesco&especialidade=cardiologia")

        corpo = r.json()
        assert [(c["convenio"], c["especialidade"]) for c in corpo["convenios_especialidade"]] == [
            ("Bradesco Saúde", "Cardiologia")
        ]
        assert corpo["convenios_especialidade"][0]["cobre"] is True

    def test_o_nome_do_registro_e_o_par_convenio_mais_especialidade(self, monkeypatch):
        """Nenhum dos dois sozinho identifica a linha: no índice ficam os dois.

        6 convênios por 8 especialidades é o volume plausível já em 2026 que o
        ADR 0032 usou para rejeitar a versão com só dois degraus."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        convenios = ["Bradesco Saúde", "Unimed", "SulAmérica", "Amil", "Golden Cross", "Porto Seguro"]
        especialidades = [
            "Cardiologia",
            "Pediatria",
            "Ortopedia",
            "Urologia",
            "Ginecologia",
            "Dermatologia",
            "Neurologia",
            "Oftalmologia",
        ]
        pares = [(conv, esp) for conv in convenios for esp in especialidades]
        client = _make_app({"convenios_especialidade": [_convenio_row(conv, esp) for conv, esp in pares]})

        r = _get(client, "/api/ana/convenios-especialidade")

        corpo = r.json()
        # O degrau é decisão do servidor; o que o contrato promete é que o par
        # identifica cada linha em qualquer degrau, e que nada some.
        assert corpo["modo"] in ("resumo", "indice")
        assert _tamanho_do_corpo(r) <= LIMITE
        assert _nomes_da_lista(corpo["convenios_especialidade"], "convenio", "especialidade") == [
            f"{conv} / {esp}" for conv, esp in pares
        ]


class TestPisoDoIndice:
    def test_quando_nem_o_indice_cabe_a_resposta_sai_inteira(self, monkeypatch):
        """O índice é o piso. Cortar a lista é o defeito que a regra existe para
        matar, então a linha vence o limite (decisão 4 do ADR 0032)."""
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        exames = [_exame_row(f"Exame de nome bastante comprido número {i:03d}", 100.00) for i in range(150)]
        client = _make_app({"exames": exames})

        r = _get(client, "/api/ana/exames")

        corpo = r.json()
        assert corpo["modo"] == "indice"
        assert len(corpo["exames"]) == 150
        assert _tamanho_do_corpo(r) > LIMITE


def _inflar(linhas: list[dict], campo_nome: str, vezes: int = 3) -> list[dict]:
    """Repete o cadastro real N vezes, com nomes distintos, para provar a regra
    contra o crescimento e não só contra os dados de hoje."""
    inflado = []
    for repeticao in range(vezes):
        for linha in linhas:
            copia = dict(linha)
            if repeticao:
                copia[campo_nome] = f"{linha[campo_nome]} {repeticao + 1}"
            inflado.append(copia)
    return inflado


class TestCrescimentoDaTabela:
    """Decisão 8 do ADR 0032: a regra é provada com a tabela inflada a 3x o
    volume de hoje, com os dados reais do export como base."""

    @pytest.mark.parametrize(
        "tabela,rota,chave,campo_nome",
        [
            ("consultas_particulares", "consultas-particulares", "consultas_particulares", "especialidade"),
            ("exames", "exames", "exames", "nome_exame"),
            ("cirurgias_estimativas", "cirurgias-estimativas", "cirurgias_estimativas", "procedimento"),
            ("convenios_especialidade", "convenios-especialidade", "convenios_especialidade", "convenio"),
        ],
    )
    def test_tabela_a_3x_cabe_no_teto_e_nao_perde_registro(self, monkeypatch, tabela, rota, chave, campo_nome):
        monkeypatch.setattr(settings, "ana_api_key", CHAVE)
        linhas = _linhas_do_export(tabela)
        inflado = _inflar(linhas, campo_nome)
        client = _make_app({tabela: inflado})

        r = _get(client, f"/api/ana/{rota}")

        corpo = r.json()
        assert _tamanho_do_corpo(r) <= LIMITE
        assert len(corpo[chave]) == len(linhas) * 3


def _linhas_do_export(tabela: str) -> list[dict]:
    """O cadastro de hoje, como veio do export do NocoDB. Só as linhas ativas:
    são as que a API devolve."""
    caminho = os.path.join(os.path.dirname(__file__), "fixtures", f"export_nocodb_{tabela}.csv")
    linhas = (
        parse_export_consultas(caminho) if tabela == "consultas_particulares" else parse_export_tabelas(tabela, caminho)
    )
    return [linha for linha in linhas if linha.get("ativo")]
