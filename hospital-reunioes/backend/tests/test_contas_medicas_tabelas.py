"""Tabelas de preço, busca de preço e dicionário de itens (issue #1120, PRD #1113, ADR 0070).

A gestão envia, pela tela Operadoras, o CSV de cada tabela de preço com a
categoria e a vigência, e o dicionário de itens do hospital. A busca
`preco(operadora, categoria, código, data, coluna)` devolve o valor da versão
vigente na data, `NAO_CONFERIDO` quando não há como conferir, ou `PACOTE`.

As fixtures são sintéticas, com o cabeçalho de cada formato e só as linhas que
a conferência da carga do diretor pede (spec v1.0, item 21.2; pacote da
Unimed, item 3; memória da Leve): os CSVs reais vivem em
`local/contas-medicas/`, fora do git. O dublê do banco é o da carga da
operadora, com os CHECKs da migration 116.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_contas_medicas_operadoras import (
    FATURISTA,
    GESTAO,
    _Banco,
    _cliente,
    _com_operadoras,
    _enviar_memoria,
)

from app.limiter import limiter
from app.services.contas_medicas.tabelas import NAO_CONFERIDO, PACOTE, preco

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "contas_medicas" / "tabelas"

DIA = date(2026, 10, 5)


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _rota(sigla: str) -> str:
    return f"/api/contas-medicas/operadoras/{sigla}/tabelas"


def _enviar_tabela(
    cliente: TestClient,
    sigla: str,
    categoria: str,
    arquivo: str,
    *,
    inicio: str = "2026-05-01",
    fim: str | None = None,
    texto: str | None = None,
):
    conteudo = texto if texto is not None else (FIXTURES / arquivo).read_text(encoding="utf-8")
    dados = {"categoria": categoria, "vigencia_inicio": inicio}
    if fim:
        dados["vigencia_fim"] = fim
    return cliente.post(
        _rota(sigla), data=dados, files={"arquivo": (arquivo, conteudo.encode("utf-8"), "text/csv")}
    )


def _id(banco: _Banco, sigla: str) -> str:
    return next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == sigla)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O envio do CSV, formato reconhecido pelo cabeçalho
# ═══════════════════════════════════════════════════════════════════════════


class TestEnvioDaTabela:
    def test_csv_de_materiais_com_duas_colunas_cria_a_tabela_os_itens_e_devolve_a_contagem(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ASSIM"))

        resposta = _enviar_tabela(cliente, "ASSIM", "MATERIAL", "assim-materiais.csv")

        assert resposta.status_code == 201, resposta.text
        corpo = resposta.json()
        assert (corpo["operadora"], corpo["categoria"], corpo["itens"]) == ("ASSIM", "MATERIAL", 5)
        [tabela] = banco.linhas("cm_tabela_preco")
        assert (tabela["vigencia_inicio"], tabela["vigencia_fim"]) == ("2026-05-01", None)
        assert tabela["arquivo_nome"] == "assim-materiais.csv"
        assert tabela["autor_id"] == "P1"
        assert len(banco.linhas("cm_tabela_preco_item")) == 5
        [ligacao] = banco.linhas("cm_operadora_tabela")
        assert (ligacao["operadora_id"], ligacao["categoria"], ligacao["tabela_id"]) == (
            "op-ASSIM",
            "MATERIAL",
            tabela["id"],
        )
        assert preco(banco, "op-ASSIM", "MATERIAL", "70802726", DIA, "CARIOCA") == Decimal("0.38")
        assert preco(banco, "op-ASSIM", "MATERIAL", "70802726", DIA, "COMUM") == Decimal("0.44")

    @pytest.mark.parametrize(
        ("arquivo", "categoria", "formato", "itens"),
        [
            ("assim-materiais.csv", "MATERIAL", "MATERIAIS_COMUM_CARIOCA", 5),
            ("assim-diarias-taxas.csv", "DIARIA_TAXA", "DIARIAS_TAXAS_COMUM_CARIOCA", 8),
            ("assim-pacotes.csv", "PACOTE", "PACOTES", 2),
            ("unimed-diarias-taxas.csv", "DIARIA_TAXA", "DIARIAS_TAXAS_VALOR", 5),
            ("unimed-lpm-medicamentos.csv", "MEDICAMENTO", "LPM", 3),
            # O pacote da Unimed e o da Leve trazem `escopo` e `fonte` a mais.
            ("unimed-pacotes.csv", "PACOTE", "PACOTES", 1),
            ("leve-pacotes.csv", "PACOTE", "PACOTES", 2),
        ],
    )
    def test_cada_formato_e_reconhecido_pelo_cabecalho(self, arquivo, categoria, formato, itens):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ALFA"))

        resposta = _enviar_tabela(cliente, "ALFA", categoria, arquivo)

        assert resposta.status_code == 201, resposta.text
        assert (resposta.json()["formato"], resposta.json()["itens"]) == (formato, itens)
        assert len(banco.linhas("cm_tabela_preco_item")) == itens
        [ligacao] = banco.linhas("cm_operadora_tabela")
        assert ligacao["categoria"] == categoria

    def test_cabecalho_desconhecido_e_recusado_com_as_colunas_esperadas_e_nada_e_gravado(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ALFA"))

        resposta = _enviar_tabela(
            cliente, "ALFA", "MATERIAL", "outro.csv", texto="codigo;nome;preco\n70802726;LUVA;0.44\n"
        )

        assert resposta.status_code == 422
        detalhe = resposta.json()["detail"]
        for colunas in (
            "codigo_assim;codigo_tuss;grupo;descricao;preco_comum;preco_carioca",
            "secao_aditivo;codigo;descricao;cbo;preco_carioca;preco_comum",
            "grupo;codigo;acomodacao;codigo_tuss;porte;descricao;permanencia;valor;observacao",
            "secao;codigo;descricao;valor",
            "codigo;codigo_tiss;descricao;preco_lpm;taxa_custos;inicio_vigencia;fim_vigencia",
        ):
            assert colunas in detalhe, colunas
        assert banco.linhas("cm_tabela_preco") == []
        assert banco.linhas("cm_tabela_preco_item") == []

    def test_preco_que_nao_e_numero_recusa_com_a_linha(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ALFA"))
        texto = "secao;codigo;descricao;valor\nDIARIA;60000090;Diária;1.050,00\n"

        resposta = _enviar_tabela(cliente, "ALFA", "DIARIA_TAXA", "diarias.csv", texto=texto)

        assert resposta.status_code == 422
        assert "Linha 2" in resposta.json()["detail"]
        assert banco.linhas("cm_tabela_preco") == []

    def test_quem_nao_tem_regra_contratual_e_tabelas_recebe_403_e_nada_e_gravado(self):
        cliente, banco = _cliente(FATURISTA, _com_operadoras("ALFA"))

        resposta = _enviar_tabela(cliente, "ALFA", "MATERIAL", "assim-materiais.csv")

        assert resposta.status_code == 403
        assert banco.linhas("cm_tabela_preco") == []
        assert banco.linhas("cm_operadora_tabela") == []

    def test_operadora_sem_cadastro_recebe_404(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("ALFA"))

        resposta = _enviar_tabela(cliente, "BETA", "MATERIAL", "assim-materiais.csv")

        assert resposta.status_code == 404
        assert banco.linhas("cm_tabela_preco") == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. A conferência da carga do diretor: os preços que têm de sair da busca
# ═══════════════════════════════════════════════════════════════════════════


def _carregado(sigla: str, *tabelas: tuple[str, str]) -> _Banco:
    cliente, banco = _cliente(GESTAO, _com_operadoras(sigla))
    for categoria, arquivo in tabelas:
        resposta = _enviar_tabela(cliente, sigla, categoria, arquivo)
        assert resposta.status_code == 201, resposta.text
    return banco


class TestConferenciaDaCarga:
    def test_os_nove_precos_da_assim_saem_nas_duas_colunas(self):
        """Spec v1.0, item 21.2: código, Carioca, Comum."""
        banco = _carregado("ASSIM", ("MATERIAL", "assim-materiais.csv"), ("DIARIA_TAXA", "assim-diarias-taxas.csv"))
        esperados = [
            ("MATERIAL", "70802726", "0.38", "0.44"),
            ("MATERIAL", "70224889", "70.95", "83.47"),
            ("MATERIAL", "70223769", "11.31", "13.30"),
            ("MATERIAL", "70704333", "1.39", "1.63"),
            ("MATERIAL", "70176388", "0.46", "0.54"),
            ("DIARIA_TAXA", "60025662", "28.63", "35.81"),
            ("DIARIA_TAXA", "60000805", "186.01", "218.84"),
            ("DIARIA_TAXA", "60034017", "7.34", "9.18"),
            ("DIARIA_TAXA", "60033568", "19.97", "24.95"),
        ]

        for categoria, codigo, carioca, comum in esperados:
            assert preco(banco, "op-ASSIM", categoria, codigo, DIA, "CARIOCA") == Decimal(carioca), codigo
            assert preco(banco, "op-ASSIM", categoria, codigo, DIA, "COMUM") == Decimal(comum), codigo

    def test_os_oito_valores_da_unimed_saem_da_busca(self):
        """Pacote da Unimed, item 3. Coluna única: o plano não escolhe coluna."""
        banco = _carregado(
            "UNIMED",
            ("DIARIA_TAXA", "unimed-diarias-taxas.csv"),
            ("PACOTE", "unimed-pacotes.csv"),
            ("MEDICAMENTO", "unimed-lpm-medicamentos.csv"),
            ("MATERIAL", "unimed-lpm-materiais.csv"),
        )
        esperados = [
            ("DIARIA_TAXA", "60000090", "1050.00"),
            ("DIARIA_TAXA", "60000260", "4831.55"),
            ("DIARIA_TAXA", "60023120", "800.74"),
            ("DIARIA_TAXA", "10102019", "65.00"),
            ("PACOTE", "89450171", "3300.00"),
            ("MEDICAMENTO", "90458125", "30.9600"),
            ("MEDICAMENTO", "90008596", "22.1400"),
            ("MATERIAL", "03330109", "3.6000"),
        ]

        for categoria, codigo, valor in esperados:
            assert preco(banco, "op-UNIMED", categoria, codigo, DIA) == Decimal(valor), codigo

    def test_os_oito_valores_da_leve_saem_da_busca_e_o_pacote_acha_por_qualquer_tuss(self):
        """Memória da Leve v1.0: diárias e taxas no mesmo formato da Unimed, e
        pacote com mais de um TUSS na mesma célula."""
        banco = _carregado("LEVE", ("DIARIA_TAXA", "leve-diarias-taxas.csv"), ("PACOTE", "leve-pacotes.csv"))
        esperados = [
            ("DIARIA_TAXA", "60034068", "1100.00"),
            ("DIARIA_TAXA", "60000090", "900.00"),
            ("DIARIA_TAXA", "60034424", "480.00"),
            ("DIARIA_TAXA", "60034599", "1850.00"),
            ("DIARIA_TAXA", "60034602", "2650.00"),
            ("DIARIA_TAXA", "60029080", "100.00"),
            ("PACOTE", "98009062", "890.00"),
            ("PACOTE", "31309062", "890.00"),
            ("PACOTE", "31309020", "890.00"),
            ("PACOTE", "31303013", "890.00"),
        ]

        for categoria, codigo, valor in esperados:
            assert preco(banco, "op-LEVE", categoria, codigo, DIA) == Decimal(valor), codigo
        pacote = next(i for i in banco.linhas("cm_tabela_preco_item") if i["codigo"] == "98003013")
        assert pacote["extra_json"]["codigos_tuss"] == ["31309020", "31303013"]
        assert pacote["extra_json"]["permanencia"] == "0"
        assert "acomodacao" not in pacote["extra_json"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. A versão pela data do atendimento
# ═══════════════════════════════════════════════════════════════════════════


class TestVersaoPelaData:
    def test_duas_versoes_da_lpm_a_data_escolhe_a_certa_e_sem_versao_nao_confere(self):
        """A LPM de setembro fecha em 30/09 e a de outubro começa em 01/10. A
        anterior continua lá: a conta de setembro usa o preço de setembro."""
        cliente, banco = _cliente(GESTAO, _com_operadoras("UNIMED"))
        setembro = _enviar_tabela(
            cliente, "UNIMED", "MEDICAMENTO", "unimed-lpm-medicamentos.csv", inicio="2026-09-01", fim="2026-09-30"
        )
        outubro = _enviar_tabela(
            cliente, "UNIMED", "MEDICAMENTO", "unimed-lpm-medicamentos-v2.csv", inicio="2026-10-01"
        )
        assert (setembro.status_code, outubro.status_code) == (201, 201)
        assert len(banco.linhas("cm_operadora_tabela")) == 2

        def clexane(dia: date):
            return preco(banco, "op-UNIMED", "MEDICAMENTO", "90458125", dia)

        assert clexane(date(2026, 9, 15)) == Decimal("30.96")
        assert clexane(date(2026, 9, 30)) == Decimal("30.96")
        assert clexane(date(2026, 10, 1)) == Decimal("32.50")
        assert clexane(date(2027, 3, 1)) == Decimal("32.50")
        assert clexane(date(2026, 8, 31)) == NAO_CONFERIDO

    def test_versao_nova_sem_fim_ganha_da_anterior_sem_fim_a_partir_do_inicio_dela(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("UNIMED"))
        _enviar_tabela(cliente, "UNIMED", "MEDICAMENTO", "unimed-lpm-medicamentos.csv", inicio="2026-09-01")
        _enviar_tabela(cliente, "UNIMED", "MEDICAMENTO", "unimed-lpm-medicamentos-v2.csv", inicio="2026-10-01")

        assert preco(banco, "op-UNIMED", "MEDICAMENTO", "90458125", date(2026, 9, 20)) == Decimal("30.96")
        assert preco(banco, "op-UNIMED", "MEDICAMENTO", "90458125", date(2026, 10, 20)) == Decimal("32.50")

    def test_fim_antes_do_inicio_e_recusado(self):
        cliente, banco = _cliente(GESTAO, _com_operadoras("UNIMED"))

        resposta = _enviar_tabela(
            cliente, "UNIMED", "MEDICAMENTO", "unimed-lpm-medicamentos.csv", inicio="2026-10-01", fim="2026-09-01"
        )

        assert resposta.status_code == 422
        assert banco.linhas("cm_tabela_preco") == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. Quando não há como conferir: NAO_CONFERIDO e PACOTE, nunca erro de preço
# ═══════════════════════════════════════════════════════════════════════════


class TestNaoConferido:
    def test_valor_pacote_na_coluna_sai_como_pacote(self):
        banco = _carregado("ASSIM", ("DIARIA_TAXA", "assim-diarias-taxas.csv"))

        assert preco(banco, "op-ASSIM", "DIARIA_TAXA", "60001062", DIA, "CARIOCA") == PACOTE

    def test_preco_zero_na_lpm_nao_e_conferido(self):
        banco = _carregado(
            "UNIMED", ("MEDICAMENTO", "unimed-lpm-medicamentos.csv"), ("MATERIAL", "unimed-lpm-materiais.csv")
        )

        assert preco(banco, "op-UNIMED", "MEDICAMENTO", "90000001", DIA) == NAO_CONFERIDO
        assert preco(banco, "op-UNIMED", "MATERIAL", "03137112", DIA) == NAO_CONFERIDO

    def test_codigo_repetido_desempata_pelo_cbo_e_sem_cbo_nao_e_conferido(self):
        """10101012 aparece três vezes nas diárias e taxas da ASSIM: sem
        especialidade, Pediatria (225124) e Pneumologia (225127)."""
        banco = _carregado("ASSIM", ("DIARIA_TAXA", "assim-diarias-taxas.csv"))

        assert preco(banco, "op-ASSIM", "DIARIA_TAXA", "10101012", DIA, "COMUM", cbo="225124") == Decimal("117.03")
        assert preco(banco, "op-ASSIM", "DIARIA_TAXA", "10101012", DIA, "COMUM", cbo="225127") == Decimal("90.50")
        assert preco(banco, "op-ASSIM", "DIARIA_TAXA", "10101012", DIA, "COMUM") == NAO_CONFERIDO
        assert preco(banco, "op-ASSIM", "DIARIA_TAXA", "10101012", DIA, "COMUM", cbo="999999") == NAO_CONFERIDO

    def test_honorario_nao_e_conferido(self):
        """O código de visita está na tabela de diárias e taxas da Unimed, mas
        a categoria honorário não tem tabela: a CBHPM não chegou."""
        banco = _carregado("UNIMED", ("DIARIA_TAXA", "unimed-diarias-taxas.csv"))

        assert preco(banco, "op-UNIMED", "HONORARIO", "10102019", DIA) == NAO_CONFERIDO

    def test_categoria_desconhecida_codigo_fora_da_tabela_e_celula_vazia_nao_sao_conferidos(self):
        banco = _carregado("UNIMED", ("DIARIA_TAXA", "unimed-diarias-taxas.csv"))

        assert preco(banco, "op-UNIMED", "sadt", "10102019", DIA) == NAO_CONFERIDO
        assert preco(banco, "op-UNIMED", "DIARIA_TAXA", "99999999", DIA) == NAO_CONFERIDO
        # A taxa de OPME é percentual: a célula do valor vem vazia.
        assert preco(banco, "op-UNIMED", "DIARIA_TAXA", "60033487", DIA) == NAO_CONFERIDO

    def test_tabela_de_duas_colunas_sem_a_coluna_do_plano_nao_e_conferida(self):
        banco = _carregado("ASSIM", ("MATERIAL", "assim-materiais.csv"))

        assert preco(banco, "op-ASSIM", "MATERIAL", "70802726", DIA) == NAO_CONFERIDO


# ═══════════════════════════════════════════════════════════════════════════
# 5. A memória da operadora: preço validado e regra de uso de cada categoria
# ═══════════════════════════════════════════════════════════════════════════


def _memoria(sigla: str, cabecalho: str) -> str:
    """Memória sintética mínima, só com o cabeçalho que o teste precisa."""
    return (
        f'---\noperadora: {sigla}\nnome: {sigla} Saúde\nversao_memoria: "1.0"\nsituacao: PARCIAL\n'
        f"{cabecalho}---\n\n# MEMÓRIA SINTÉTICA\n"
    )


VALIDADOS = """precos:
  validados:
    - { item: "Luva de procedimento", codigo: "70802726", valor: 0.50, unidade: par }
    - { item: "Clexane 40 mg", valor: 67.99, unidade: seringa }
"""

# O bloco `tabelas` da memória da Leve v1.0: categorias e tipos que a ASSIM
# e a Unimed não tinham, nenhum deles carregado.
TABELAS_DA_LEVE = """tabelas:
  materiais:     { tipo: SIMPRO, versao: "mais atualizada", arquivo: null, chave: null, deflator_percentual: 20, situacao: NAO_CARREGADA }
  diarias_taxas: { tipo: ADITIVO, versao: "Adendo 012, vigência 01/08/2026", chave: codigo, situacao: CARREGADA }
  medicamentos:  { tipo: BRASINDICE, regra_preco: PF, restrito_hospitalar: { regra: PF_MAIS_PERCENTUAL, percentual: 20 }, situacao: NAO_CARREGADA }
  honorarios:    { tipo: AMB92, ch: 0.40, situacao: NAO_CARREGADA }
  sadt:          { tipo: AMB92, ch: 0.30, situacao: NAO_CARREGADA }
  porte_anestesico: { tipo: CBHPM, versao: "5ª edição", situacao: NAO_CARREGADA }
"""


class TestMemoriaDaOperadora:
    def test_preco_validado_na_memoria_ganha_da_tabela(self):
        cliente, banco = _cliente(GESTAO)
        assert _enviar_memoria(cliente, _memoria("ASSIM", VALIDADOS)).status_code == 201
        assert _enviar_tabela(cliente, "ASSIM", "MATERIAL", "assim-materiais.csv").status_code == 201
        assimid = _id(banco, "ASSIM")

        assert preco(banco, assimid, "MATERIAL", "70802726", DIA, "CARIOCA") == Decimal("0.50")
        assert preco(banco, assimid, "MATERIAL", "70802726", DIA, "COMUM") == Decimal("0.50")
        # O que não está validado segue a tabela.
        assert preco(banco, assimid, "MATERIAL", "70224889", DIA, "CARIOCA") == Decimal("70.95")

    def test_regra_de_uso_vem_do_bloco_tabelas_da_memoria_e_tabela_de_referencia_nao_confere(self):
        """Medicamento da Leve é Brasíndice pelo PF: um CSV enviado nessa
        categoria guarda a regra da memória e não confere, porque o Brasíndice
        não é carregado nesta etapa."""
        cliente, banco = _cliente(GESTAO)
        assert _enviar_memoria(cliente, _memoria("LEVE", TABELAS_DA_LEVE)).status_code == 201
        leve = _id(banco, "LEVE")
        assert _enviar_tabela(cliente, "LEVE", "MEDICAMENTO", "unimed-lpm-medicamentos.csv").status_code == 201
        assert _enviar_tabela(cliente, "LEVE", "MATERIAL", "unimed-lpm-materiais.csv").status_code == 201
        assert _enviar_tabela(cliente, "LEVE", "DIARIA_TAXA", "leve-diarias-taxas.csv").status_code == 201

        regras = {r["categoria"]: r["regra_uso_json"] for r in banco.linhas("cm_operadora_tabela")}
        assert regras["MEDICAMENTO"]["regra_preco"] == "PF"
        assert regras["MEDICAMENTO"]["restrito_hospitalar"] == {"regra": "PF_MAIS_PERCENTUAL", "percentual": 20}
        assert (regras["MATERIAL"]["regra_preco"], regras["MATERIAL"]["percentual"]) == ("SIMPRO", -20)
        assert (regras["DIARIA_TAXA"]["regra_preco"], regras["DIARIA_TAXA"]["chave"]) == ("COLUNA", "codigo")
        tipos = {t["tipo"] for t in banco.linhas("cm_tabela_preco")}
        assert tipos == {"BRASINDICE", "SIMPRO", "ADITIVO"}

        assert preco(banco, leve, "MEDICAMENTO", "90458125", DIA) == NAO_CONFERIDO
        assert preco(banco, leve, "MATERIAL", "03330109", DIA) == NAO_CONFERIDO
        assert preco(banco, leve, "DIARIA_TAXA", "60034068", DIA) == Decimal("1100.00")
        assert preco(banco, leve, "SADT", "40301010", DIA) == NAO_CONFERIDO
        assert preco(banco, leve, "PORTE_ANESTESICO", "31309062", DIA) == NAO_CONFERIDO


# ═══════════════════════════════════════════════════════════════════════════
# 6. A lista das operadoras: cada categoria com tabela, versão, vigência e situação
# ═══════════════════════════════════════════════════════════════════════════


class TestTabelasNaLista:
    def test_cada_categoria_vem_com_as_versoes_e_a_situacao_inclusive_as_que_so_a_memoria_conhece(self):
        cliente, banco = _cliente(GESTAO)
        _enviar_memoria(cliente, _memoria("LEVE", TABELAS_DA_LEVE))
        _enviar_tabela(cliente, "LEVE", "DIARIA_TAXA", "leve-diarias-taxas.csv", inicio="2026-08-01")
        _enviar_tabela(
            cliente, "LEVE", "PACOTE", "leve-pacotes.csv", inicio="2026-01-01", fim="2026-07-31"
        )
        segundo = cliente.post(
            _rota("LEVE"),
            data={"categoria": "PACOTE", "vigencia_inicio": "2026-08-01", "versao": "Adendo 012"},
            files={"arquivo": ("leve-pacotes-012.csv", (FIXTURES / "leve-pacotes.csv").read_bytes(), "text/csv")},
        )
        assert segundo.status_code == 201, segundo.text

        [leve] = cliente.get("/api/contas-medicas/operadoras").json()["operadoras"]

        assert leve["tabelas"] == [
            {"categoria": "MATERIAL", "tipo": "SIMPRO", "situacao": "NAO_CARREGADA", "versoes": []},
            {"categoria": "MEDICAMENTO", "tipo": "BRASINDICE", "situacao": "NAO_CARREGADA", "versoes": []},
            {
                "categoria": "DIARIA_TAXA",
                "tipo": "ADITIVO",
                "situacao": "CARREGADA",
                "versoes": [
                    {
                        "tabela": "leve-diarias-taxas.csv",
                        "versao": "Adendo 012, vigência 01/08/2026",
                        "vigencia_inicio": "2026-08-01",
                        "vigencia_fim": None,
                    }
                ],
            },
            {
                "categoria": "PACOTE",
                "tipo": "PACOTES",
                "situacao": "CARREGADA",
                "versoes": [
                    {
                        "tabela": "leve-pacotes-012.csv",
                        "versao": "Adendo 012",
                        "vigencia_inicio": "2026-08-01",
                        "vigencia_fim": None,
                    },
                    {
                        "tabela": "leve-pacotes.csv",
                        "versao": None,
                        "vigencia_inicio": "2026-01-01",
                        "vigencia_fim": "2026-07-31",
                    },
                ],
            },
            {"categoria": "HONORARIO", "tipo": "AMB92", "situacao": "NAO_CARREGADA", "versoes": []},
            {"categoria": "SADT", "tipo": "AMB92", "situacao": "NAO_CARREGADA", "versoes": []},
            {"categoria": "PORTE_ANESTESICO", "tipo": "CBHPM", "situacao": "NAO_CARREGADA", "versoes": []},
        ]

    def test_operadora_sem_memoria_mostra_as_cinco_categorias_nao_carregadas(self):
        cliente, _ = _cliente(GESTAO, _com_operadoras("GAMA"))

        [gama] = cliente.get("/api/contas-medicas/operadoras").json()["operadoras"]

        assert [(t["categoria"], t["situacao"]) for t in gama["tabelas"]] == [
            ("MATERIAL", "NAO_CARREGADA"),
            ("MEDICAMENTO", "NAO_CARREGADA"),
            ("DIARIA_TAXA", "NAO_CARREGADA"),
            ("PACOTE", "NAO_CARREGADA"),
            ("HONORARIO", "NAO_CARREGADA"),
        ]
