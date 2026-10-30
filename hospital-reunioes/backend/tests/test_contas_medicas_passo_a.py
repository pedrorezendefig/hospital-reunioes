"""O Passo A de Contas médicas: os eventos do prontuário com página e trecho
(issue #1131, PRD #1128).

A IA lê só o texto livre que o código não estruturou, já desidentificado, mais
o que o código já leu (prescrições consolidadas, balanço, glicemias e os
achados das conferências). Os testes passam pelo adaptador de verdade e trocam
só o transporte HTTP: o que eles leem é o corpo que sairia para a Anthropic e
a resposta é a do Anexo A, montada à mão.

O prontuário é sintético, montado das fixtures de texto do MV
(`tests/fixtures/contas_medicas/`), com a paciente fictícia ANTÔNIA MELO FARIAS.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from types import SimpleNamespace

import httpx2
import pytest
from anthropic_apoio import cliente_por_transporte, mensagem, uso

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.contas_medicas import ia, passo_a  # noqa: E402
from app.services.contas_medicas.conferencia import ProntuarioLido  # noqa: E402
from app.services.contas_medicas.conteudo import ler_conteudo  # noqa: E402
from app.services.contas_medicas.prontuario import ler_prontuario  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "contas_medicas"
QUEBRA = "<<<QUEBRA DE PÁGINA>>>"
ATENDIMENTO = "31245"


# ═══════════════════════════════════════════════════════════════════════════
# O prontuário sintético
# ═══════════════════════════════════════════════════════════════════════════


def _fixture(nome: str) -> list[str]:
    return [p.strip("\n") for p in (FIXTURES / f"{nome}.txt").read_text(encoding="utf-8").split(QUEBRA)]


def _com_rodape(paginas: list[str]) -> list[str]:
    return [
        f"{texto}\n\n          Impressão de Prontuário - Página {n} de {len(paginas)}"
        for n, texto in enumerate(paginas, start=1)
    ]


def _lido(paginas: list[str]) -> ProntuarioLido:
    estrutura = ler_prontuario(paginas, ATENDIMENTO)
    return ProntuarioLido(estrutura, ler_conteudo(paginas, estrutura), paginas)


# A evolução médica vem antes no arquivo e é de 05/10: a entrada sai pela data.
EVOLUCAO_DE_05_10 = [p.replace("03/10/2026 09:12", "05/10/2026 08:00") for p in _fixture("prontuario/evolucao")]
PRESCRICAO_DE_03_10 = [
    p.replace("20/10/2026", "03/10/2026").replace("18/10/2026", "02/10/2026") for p in _fixture("conteudo/prescricao")
]


def _paginas() -> list[str]:
    """1 capa, 2 evolução (05/10), 3 admissão (02/10), 4 e 5 prescrição (03/10),
    6 anotação de enfermagem (03/10), 7 e 8 balanço (03/10), 9 resumo de alta (06/10)."""
    return _com_rodape(
        [
            *_fixture("prontuario/capa"),
            *EVOLUCAO_DE_05_10,
            *_fixture("prontuario/admissao_unidade"),
            *PRESCRICAO_DE_03_10,
            *_fixture("prontuario/anotacao_enf"),
            *_fixture("conteudo/balanco"),
            *_fixture("prontuario/resumo_alta"),
        ]
    )


# O que a capa imprime da paciente: nada disso pode sair para a IA.
VALORES_DA_CAPA = (
    "ANTONIA",
    "MELO FARIAS",
    "FARIAS",
    "JOSEFA",
    "RIBEIRO COSTA",
    "14/03/1951",
    "529.982.247-25",
    "52998224725",
    "20.481.337-6",
    "0817734",
)

# Uma linha que as conferências por código já puseram no guia.
ACHADO_DO_CODIGO = {
    "acao": "INCLUIR",
    "data": "2026-10-04",
    "data_fim": "2026-10-04",
    "setor": "CTI ADULTO",
    "codigo": "90030001",
    "descricao": "CLEXANE 40MG/0,4ML SER PREENCH",
    "quantidade_lancada": 0.0,
    "quantidade_devida": 1.0,
    "regra_codigo": "ALFA-PRI-07",
    "motivo": "Prescrito em 04/10 e não lançado.",
    "evidencia_pagina": 4,
    "nivel_evidencia": "PRESCRITO",
    "origem": "CODIGO",
}


def _regra(codigo: str, texto: str) -> dict:
    return {"codigo": codigo, "secao": codigo.split("-")[1], "texto": texto, "tipo": "CONTRATUAL", "status": "VIGENTE"}


REGRAS = [
    _regra("ALFA-PRI-01", "Leia o prontuário pelo atendimento."),
    _regra("ALFA-PRC-02", "Preço pela tabela vigente."),
    _regra("ALFA-DIA-01", "Diária vence às 10h."),
    _regra("ALFA-INS-04", "Equipo por bomba a cada 72 horas."),
]


# ═══════════════════════════════════════════════════════════════════════════
# O provedor e o banco de mentira
# ═══════════════════════════════════════════════════════════════════════════


def _resposta(**listas) -> dict:
    """Uma resposta no formato do Anexo A, com as listas pedidas."""
    return {
        "atendimento": ATENDIMENTO,
        "idade_anos": 75,
        "movimentacoes": [],
        "terapias": [],
        "prescricoes": [],
        "procedimentos": [],
        "cirurgias": [],
        "documentos_ausentes": [],
        "observacoes": [],
        **listas,
    }


class _Provedor:
    """A Anthropic do teste: guarda o corpo de cada requisição e devolve
    `respostas` na ordem; a última se repete."""

    def __init__(self):
        self.corpos: list[dict] = []
        self.respostas: list[dict] = [_resposta()]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.corpos.append(json.loads(request.content))
        resposta = self.respostas.pop(0) if len(self.respostas) > 1 else self.respostas[0]
        return httpx2.Response(200, json=mensagem(json.dumps(resposta), uso(entrada=900, saida=300)))

    def textos_do_prontuario(self) -> list[str]:
        """O bloco TEXTO DO PRONTUÁRIO de cada requisição."""
        return [corpo["messages"][0]["content"][1]["text"] for corpo in self.corpos]


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    duble = _Provedor()
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda: cliente_por_transporte(duble),
    )
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


class _Consulta:
    def __init__(self, banco: _Banco, nome: str):
        self._banco, self._nome = banco, nome
        self._filtros: list = []
        self._ordem: tuple[str, bool] | None = None
        self._limite: int | None = None
        self._insert = self._update = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append((coluna, valor))
        return self

    def order(self, coluna, desc=False):
        self._ordem = (coluna, desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def insert(self, linhas):
        self._insert = linhas
        return self

    def update(self, campos):
        self._update = campos
        return self

    def execute(self):
        tabela = self._banco.tabelas.setdefault(self._nome, [])
        if self._insert is not None:
            novas = [
                {"id": f"{self._nome}-{len(tabela) + i}", "criado_em": len(tabela) + i, **linha}
                for i, linha in enumerate(self._insert if isinstance(self._insert, list) else [self._insert])
            ]
            tabela.extend(novas)
            return SimpleNamespace(data=[dict(linha) for linha in novas])
        casam = [linha for linha in tabela if all(linha.get(c) == v for c, v in self._filtros)]
        if self._update is not None:
            for linha in casam:
                linha.update(json.loads(json.dumps(self._update)))
        if self._ordem:
            casam.sort(key=lambda linha: linha.get(self._ordem[0]), reverse=self._ordem[1])
        if self._limite is not None:
            casam = casam[: self._limite]
        return SimpleNamespace(data=[json.loads(json.dumps(linha)) for linha in casam])


class _Banco:
    """O banco do teste, com a estrutura do prontuário já gravada pelo pipeline."""

    def __init__(self):
        self.tabelas: dict[str, list[dict]] = {
            "cm_conta": [{"id": "c1", "atendimento_id": "at-1"}],
            "cm_eventos": [{"id": "ev-1", "atendimento_id": "at-1", "eventos_json": {"arquivo_id": "arq-1"}}],
            "cm_chamada_ia": [],
        }

    def table(self, nome: str):
        return _Consulta(self, nome)


def _passo_a(banco: _Banco, prontuario: ProntuarioLido, achados=(ACHADO_DO_CODIGO,)) -> dict:
    return passo_a.eventos_do_atendimento(
        banco,
        conta_id="c1",
        atendimento_id="at-1",
        arquivo_id="arq-1",
        prontuario=prontuario,
        achados=list(achados),
        regras=REGRAS,
    )


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _secao(texto: str, titulo: str) -> list[str]:
    """As linhas de uma seção do código no texto enviado, até a próxima seção."""
    depois = texto.split(f"[[{titulo}]]\n", 1)[1]
    return depois.split("\n[[", 1)[0].splitlines()


# ═══════════════════════════════════════════════════════════════════════════
# 1. A entrada
# ═══════════════════════════════════════════════════════════════════════════


class TestEntrada:
    def test_a_entrada_tem_os_marcadores_pela_data_sem_valor_da_capa_com_prescricoes_e_achados(self, provedor):
        _passo_a(_Banco(), _lido(_paginas()))

        (texto,) = provedor.textos_do_prontuario()
        # Um bloco por documento de texto livre, pela data e hora do documento,
        # com a página do PDF original. Prescrição e balanço não vão como bloco:
        # vão nas seções do código.
        assert re.findall(r"\[\[PÁG [^\]]*\]\]", texto) == [
            "[[PÁG 3 · ADMISSAO_UNIDADE · 02/10/2026 23:05 · CTI ADULTO]]",
            "[[PÁG 6 · ANOTACAO_ENF · 03/10/2026 14:30 · sem setor]]",
            "[[PÁG 2 · EVOLUÇÃO MEDICA · 05/10/2026 08:00 · sem setor]]",
            "[[PÁG 9 · RESUMO_ALTA · 06/10/2026 15:20 · sem setor]]",
        ]
        assert "Realizado curativo em região sacral com cobertura de hidrocoloide." in texto

        normalizado = _sem_acento(texto).upper()
        for valor in VALORES_DA_CAPA:
            assert valor not in normalizado, valor

        prescricoes = _secao(texto, "PRESCRIÇÕES CONSOLIDADAS")
        for item in (
            "PANTOCAL 40MG EV FR/AMP (PANTOPRAZOL)",
            "DIPIRONA SODICA 500MG/ML SOL INJ",
            "ONDANSETRONA 2MG/ML SOL INJ",
            "METOCLOPRAMIDA 5MG/ML SOL INJ",
            "SORO FISIOLOGICO 0,9% 500ML",
            "CEFTRIAXONA 1G FR/AMP",
        ):
            (linha,) = [linha for linha in prescricoes if item in linha]
            assert "03/10" in linha and "PÁG 4" in linha, linha
        (dipirona,) = [linha for linha in prescricoes if "DIPIRONA" in linha]
        assert "SE NECESSÁRIO" in dipirona and "EM CASO DE DOR OU FEBRE" in dipirona

        (achado,) = _secao(texto, "ACHADOS DO CÓDIGO")
        for parte in ("INCLUIR", "04/10/2026", "90030001", "CLEXANE 40MG/0,4ML SER PREENCH", "ALFA-PRI-07"):
            assert parte in achado, parte

        assert any("SORO FISIOLOGICO 0,9% EV" in linha for linha in _secao(texto, "BALANÇO HÍDRICO POR DIA"))
        assert _secao(texto, "GLICEMIAS POR DIA") == ["03/10/2026: 4"]

    def test_as_orientacoes_de_leitura_sao_as_secoes_1_3_e_8_da_memoria(self, provedor):
        _passo_a(_Banco(), _lido(_paginas()))

        orientacoes = provedor.corpos[0]["messages"][0]["content"][0]["text"]
        for codigo in ("ALFA-PRI-01", "ALFA-DIA-01", "ALFA-INS-04"):
            assert codigo in orientacoes, codigo
        assert "ALFA-PRC-02" not in orientacoes


# ═══════════════════════════════════════════════════════════════════════════
# 2. O prontuário acima do limite do modelo pequeno
# ═══════════════════════════════════════════════════════════════════════════

# 100 mil tokens a 3,5 caracteres por token (adendo v1.3, item 10).
LIMITE_EM_CARACTERES = 350_000


def _evolucao_longa(dia: int) -> str:
    """Uma evolução de uns 120 mil caracteres: quatro delas passam do limite."""
    corpo = [
        f"Dia {dia:02d}/10, registro {n:04d}: paciente estável no leito, sem queixas, sinais vitais estáveis."
        for n in range(1300)
    ]
    if dia == 2:
        corpo.append("Realizado curativo em região sacral com cobertura de hidrocoloide.")
    return "\n".join(
        [
            "HOSPITAL SÃO MATHEUS",
            "Relatório de Evolução",
            "EVOLUÇÃO MEDICA",
            f"Atendimento {ATENDIMENTO}   Leito: CTI-04",
            f"Data/Hora do Documento: {dia:02d}/10/2026 09:12",
            *corpo,
        ]
    )


def _curativo(dia: int, pagina: int) -> dict:
    return {
        "tipo": "CURATIVO",
        "data_hora": f"2026-10-{dia:02d}T09:12",
        "setor": "CTI ADULTO",
        "detalhe": "curativo em região sacral",
        "quantidade": 1,
        "pagina": pagina,
        "trecho": "Realizado curativo em região sacral com cobertura de hidrocoloide.",
    }


class TestJanelas:
    def test_acima_do_limite_vira_janelas_com_um_dia_de_sobreposicao_e_o_evento_repetido_vira_um(self, provedor):
        # Páginas: 1 capa, 2 a 5 as evoluções de 01 a 04/10.
        paginas = _com_rodape([*_fixture("prontuario/capa"), *(_evolucao_longa(dia) for dia in (1, 2, 3, 4))])
        # O curativo de 02/10 está nas duas primeiras janelas, e as duas o leem,
        # cada uma com as suas palavras e o seu formato de data. A bomba que a
        # primeira janela viu sem fim termina no dia 03, que só a segunda lê.
        curativo_relido = {
            **_curativo(2, 3),
            "detalhe": "curativo sacral com hidrocoloide",
            "data_hora": "2026-10-02 09:12",
        }
        bomba = {
            "tipo": "BOMBA_INFUSAO",
            "descricao": "noradrenalina em bomba",
            "setor": "CTI ADULTO",
            "inicio": "2026-10-02T09:12",
            "fim": None,
            "pagina": 3,
            "trecho": "Realizado curativo em região sacral com cobertura de hidrocoloide.",
        }
        bomba_relida = {**bomba, "descricao": "noradrenalina em BIC", "inicio": "2026-10-02", "fim": "2026-10-03T10:00"}
        provedor.respostas = [
            _resposta(procedimentos=[_curativo(2, 3)], terapias=[bomba]),
            _resposta(procedimentos=[curativo_relido], terapias=[bomba_relida]),
            _resposta(procedimentos=[_curativo(4, 5)]),
        ]

        eventos = _passo_a(_Banco(), _lido(paginas), achados=())

        textos = provedor.textos_do_prontuario()
        dias_por_janela = [re.findall(r"\[\[PÁG \d+ · [^·]+ · (\d\d/10)/2026", texto) for texto in textos]
        assert dias_por_janela == [["01/10", "02/10"], ["02/10", "03/10"], ["03/10", "04/10"]]
        for corpo in provedor.corpos:
            enviado = "".join(bloco["text"] for bloco in corpo["messages"][0]["content"])
            assert len(enviado) <= LIMITE_EM_CARACTERES
        # Cada janela leva as seções do código.
        assert all("[[PRESCRIÇÕES CONSOLIDADAS]]" in texto for texto in textos)

        assert [(p["tipo"], p["data_hora"]) for p in eventos["procedimentos"]] == [
            ("CURATIVO", "2026-10-02T09:12"),
            ("CURATIVO", "2026-10-04T09:12"),
        ]
        assert [(t["descricao"], t["fim"]) for t in eventos["terapias"]] == [
            ("noradrenalina em bomba", "2026-10-03T10:00"),
        ]

    def test_bombas_que_comecam_juntas_nao_viram_uma_e_cada_uma_ganha_o_seu_fim(self):
        def bomba(descricao: str, fim: str | None) -> dict:
            return {"tipo": "BOMBA_INFUSAO", "descricao": descricao, "inicio": "2026-10-02T09:12", "fim": fim}

        vazio = {lista: [] for lista in ("movimentacoes", "prescricoes", "procedimentos", "cirurgias")}
        partes = [
            {**vazio, "terapias": [bomba("noradrenalina", None), bomba("midazolam", None)]},
            {
                **vazio,
                "terapias": [
                    bomba("midazolam em BIC", "2026-10-03T08:00"),
                    bomba("noradrenalina BIC", None),
                    bomba("vasopressina", None),
                ],
            },
        ]

        terapias = passo_a.unir_eventos(partes)["terapias"]

        assert [(t["descricao"], t["fim"]) for t in terapias] == [
            ("noradrenalina", None),
            ("midazolam", "2026-10-03T08:00"),
            ("vasopressina", None),
        ]

    def test_abaixo_do_limite_e_uma_chamada_so(self, provedor):
        _passo_a(_Banco(), _lido(_paginas()))

        assert len(provedor.corpos) == 1


# ═══════════════════════════════════════════════════════════════════════════
# 3. A evidência de cada evento
# ═══════════════════════════════════════════════════════════════════════════


def _terapia(pagina: int, trecho: str) -> dict:
    return {
        "tipo": "OXIGENIO",
        "descricao": f"oxigênio, página {pagina}",
        "setor": "CTI ADULTO",
        "inicio": "2026-10-05T08:00",
        "fim": None,
        "pagina": pagina,
        "trecho": trecho,
    }


def _procedimento(pagina: int, trecho: str) -> dict:
    return {
        "tipo": "OUTRO",
        "data_hora": "2026-10-03T14:30",
        "setor": None,
        "detalhe": trecho,
        "quantidade": 1,
        "pagina": pagina,
        "trecho": trecho,
    }


def _prescricao(pagina: int, trecho: str) -> dict:
    return {
        "data": "2026-10-03",
        "setor": "CTI ADULTO",
        "item": trecho,
        "via": "EV",
        "doses_no_dia": 1,
        "se_necessario": False,
        "indicio_de_uso": None,
        "suspenso": False,
        "diluente": None,
        "em_bomba": True,
        "pagina": pagina,
        "trecho": trecho,
    }


# Páginas de `_paginas()`: 2 é a evolução, 3 a admissão, 4 a prescrição, 6 a
# anotação de enfermagem e 9 o resumo de alta.
CONFERE = "Iniciado MELOXICAM 15 MG por dor lombar."
NA_VIZINHA = "Mantida dieta por sonda nasoenteral."
DESIDENTIFICADO = "Paciente PACIENTE, 75 anos, segue em ventilação espontânea"
OUTRO_ACENTO_E_ESPACO = "Realizado  curativo em regiao sacral com   cobertura de hidrocolóide."
INEXISTENTE = "Noradrenalina 4 mg em bomba de infusão contínua."
LONGE_DA_PAGINA = "Plano: manter antibiótico, D03 de CVD em subclávia direita."


class TestEvidencia:
    def test_o_trecho_que_nao_existe_na_pagina_nem_na_vizinha_sai_com_a_etiqueta_e_confianca_baixa(self, provedor):
        provedor.respostas = [
            _resposta(
                terapias=[_terapia(2, CONFERE), _terapia(3, NA_VIZINHA)],
                procedimentos=[_procedimento(2, DESIDENTIFICADO), _procedimento(6, OUTRO_ACENTO_E_ESPACO)],
                prescricoes=[_prescricao(4, INEXISTENTE), _prescricao(9, LONGE_DA_PAGINA)],
            )
        ]
        banco = _Banco()

        eventos = _passo_a(banco, _lido(_paginas()))

        conferencia = {
            evento["trecho"]: (evento["etiquetas"], evento["confianca"])
            for lista in ("terapias", "procedimentos", "prescricoes")
            for evento in eventos[lista]
        }
        assert conferencia == {
            CONFERE: ([], None),
            NA_VIZINHA: ([], None),
            DESIDENTIFICADO: ([], None),
            OUTRO_ACENTO_E_ESPACO: ([], None),
            INEXISTENTE: (["conferir evidência"], "BAIXA"),
            LONGE_DA_PAGINA: (["conferir evidência"], "BAIXA"),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 4. As movimentações do código prevalecem
# ═══════════════════════════════════════════════════════════════════════════


def _movimentacao(tipo: str, data_hora: str, setor: str | None, pagina: int, trecho: str) -> dict:
    return {"tipo": tipo, "data_hora": data_hora, "setor": setor, "pagina": pagina, "trecho": trecho}


class TestMovimentacoes:
    def test_a_movimentacao_da_ia_que_diverge_da_do_codigo_cede_e_vira_observacao(self, provedor):
        # O código leu a internação em 02/10 22:40 e a alta em 06/10 15:20,
        # sem transferência (o CTI adulto em todos os documentos).
        provedor.respostas = [
            _resposta(
                movimentacoes=[
                    _movimentacao("INTERNACAO", "2026-10-02T22:40", "CTI ADULTO", 9, "02/10/2026 22:40"),
                    _movimentacao("TRANSFERENCIA_SETOR", "2026-10-04T10:00", "ENFERMARIA", 2, "segue em ventilação"),
                    _movimentacao("ALTA", "2026-10-06T18:00", "CTI ADULTO", 9, "DATA DA ALTA - 06/10/2026"),
                ]
            )
        ]

        eventos = _passo_a(_Banco(), _lido(_paginas()))

        assert [(m["tipo"], m["data_hora"], m["setor"], m["pagina"]) for m in eventos["movimentacoes"]] == [
            ("INTERNACAO", "2026-10-02T22:40", "CTI ADULTO", 9),
            ("ALTA", "2026-10-06T15:20", "CTI ADULTO", None),
        ]
        assert eventos["divergencias"] == [
            "Movimentação divergente: a IA leu transferência para ENFERMARIA em 04/10/2026 10:00 (página 2); "
            "vale a leitura do código, que não tem essa movimentação.",
            "Movimentação divergente: a IA leu alta em 06/10/2026 18:00 (página 9); "
            "vale a leitura do código, alta em 06/10/2026 15:20.",
        ]

    def test_a_movimentacao_da_ia_que_bate_com_a_do_codigo_nao_vira_observacao(self, provedor):
        provedor.respostas = [
            _resposta(
                movimentacoes=[
                    _movimentacao("INTERNACAO", "2026-10-02", "CTI ADULTO", 9, "02/10/2026 22:40"),
                    _movimentacao("ALTA", "2026-10-06T15:20", "CTI ADULTO", 9, "DATA DA ALTA - 06/10/2026"),
                ]
            )
        ]

        eventos = _passo_a(_Banco(), _lido(_paginas()))

        assert eventos["divergencias"] == []
        assert [m["pagina"] for m in eventos["movimentacoes"]] == [9, 9]


# ═══════════════════════════════════════════════════════════════════════════
# 5. Uma leitura por atendimento
# ═══════════════════════════════════════════════════════════════════════════


class TestUmaLeitura:
    def test_a_leitura_fica_em_cm_eventos_e_a_seguinte_reaproveita_sem_chamar_a_ia(self, provedor):
        banco = _Banco()
        provedor.respostas = [_resposta(observacoes=["Evolução de 05/10 sem assinatura."])]

        primeira = _passo_a(banco, _lido(_paginas()))
        segunda = _passo_a(banco, _lido(_paginas()))

        assert len(provedor.corpos) == 1
        assert segunda == primeira
        (gravados,) = banco.tabelas["cm_eventos"]
        assert gravados["eventos_json"]["arquivo_id"] == "arq-1"
        assert gravados["eventos_json"]["ia"]["observacoes"] == ["Evolução de 05/10 sem assinatura."]
        assert [(c["passo"], c["tokens_entrada"], c["tokens_saida"]) for c in banco.tabelas["cm_chamada_ia"]] == [
            ("A", 900, 300)
        ]

    def test_a_leitura_guarda_o_modelo_e_com_outro_modelo_a_ia_le_de_novo(self, provedor, monkeypatch):
        """Issue #1197: a leitura vale para o modelo que a fez."""
        banco = _banco_com_modelo(monkeypatch, "claude-modelo-antigo")
        provedor.respostas = [_resposta(observacoes=["Do antigo."]), _resposta(observacoes=["Do novo."])]
        _passo_a(banco, _lido(_paginas()))

        monkeypatch.setattr(ia.settings, "cm_ia_modelo_passo_a", "claude-modelo-novo")
        relida = _passo_a(banco, _lido(_paginas()))
        de_novo = _passo_a(banco, _lido(_paginas()))

        assert [corpo["model"] for corpo in provedor.corpos] == ["claude-modelo-antigo", "claude-modelo-novo"]
        assert relida["observacoes"] == de_novo["observacoes"] == ["Do novo."]
        (gravados,) = banco.tabelas["cm_eventos"]
        assert gravados["eventos_json"]["ia_modelo"] == "claude-modelo-novo"

    def test_leitura_guardada_sem_o_modelo_conta_como_de_outro_modelo(self, provedor, monkeypatch):
        banco = _banco_com_modelo(monkeypatch, "claude-modelo-atual")
        banco.tabelas["cm_eventos"][0]["eventos_json"]["ia"] = _resposta(observacoes=["De antes do #1197."])

        lida = _passo_a(banco, _lido(_paginas()))

        assert [corpo["model"] for corpo in provedor.corpos] == ["claude-modelo-atual"]
        assert lida["observacoes"] == []


def _banco_com_modelo(monkeypatch, modelo: str) -> _Banco:
    monkeypatch.setattr(ia.settings, "cm_ia_modelo_passo_a", modelo)
    return _Banco()


# ═══════════════════════════════════════════════════════════════════════════
# 6. Tipografia
# ═══════════════════════════════════════════════════════════════════════════

TRAVESSAO, MEIA_RISCA = chr(0x2014), chr(0x2013)
RAIZ_DO_APP = Path(__file__).resolve().parents[2]
ARQUIVOS_DA_FATIA = [
    RAIZ_DO_APP / "backend/app/services/contas_medicas/passo_a.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/evidencia.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/memoria_texto.py",
    RAIZ_DO_APP / "backend/app/services/contas_medicas/processamento.py",
    RAIZ_DO_APP / "backend/app/prompts/contas_medicas_passo_a.md",
    RAIZ_DO_APP / "backend/app/conhecimento/contas-medicas.md",
    Path(__file__),
]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DA_FATIA, ids=lambda a: a.name)
def test_sem_travessao_nem_meia_risca_nos_arquivos(arquivo):
    texto = arquivo.read_text(encoding="utf-8")
    assert TRAVESSAO not in texto
    assert MEIA_RISCA not in texto


def test_o_texto_que_a_ia_escreveu_sai_sem_travessao_nem_meia_risca(provedor):
    provedor.respostas = [
        _resposta(
            terapias=[_terapia(2, f"Iniciado MELOXICAM 15 MG {TRAVESSAO} por dor lombar.")],
            documentos_ausentes=[f"FICHA ANESTESICA {MEIA_RISCA} cirurgia de 04/10"],
            observacoes=[f"Evolução de 05/10 {TRAVESSAO} sem assinatura."],
        )
    ]

    eventos = _passo_a(_Banco(), _lido(_paginas()))

    gravado = json.dumps(eventos, ensure_ascii=False)
    assert TRAVESSAO not in gravado
    assert MEIA_RISCA not in gravado
    assert passo_a.parecer(eventos) == [
        "Documento ausente: FICHA ANESTESICA, cirurgia de 04/10.",
        "Observação da IA: Evolução de 05/10, sem assinatura.",
    ]
