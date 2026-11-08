"""O contrato subido na conversa da Operadora vira Regras (issue #1495, PRD #1484, ADR 0081, decisão 9).

Quem tem "Regra contratual e tabelas" sobe o contrato (PDF ou imagem, como na
aba Contratos) na conversa da Operadora. O Auditor devolve um lote: as Regras
novas cláusula a cláusula, cada uma com a Prova da regra, e o "o contrato diz"
das Regras que já existem, que não muda a análise e por isso vai sem prova.
As datas do contrato entram no mesmo lote, para o aviso de reajuste. O "ok"
aplica tudo numa versão nova da Memória e confirma o contrato.

Tudo pela rota de verdade, com o dublê do banco e o provedor da IA dublado no
transporte HTTP, como os testes da conversa da Operadora (#1490).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx2
import pytest
from anthropic_apoio import mensagem
from test_contas_medicas_contratos import _pdf, _Storage
from test_contas_medicas_conversa_da_operadora import ROTA, _item, _proposta, _Provedor, _regras_vigentes, _vigente
from test_contas_medicas_conversa_da_operadora import cenario as cenario  # noqa: F401
from test_contas_medicas_memoria_tela import _versoes
from test_contas_medicas_operadoras import GESTAO
from test_contas_medicas_revisar_pendentes import _tema

from app.services.contas_medicas.contratos import avisar_contratos

ROTA_DO_CONTRATO = f"{ROTA}/contrato"

CLAUSULA_7 = "Cláusula 7: a taxa de sala cirúrgica é paga por porte anestésico, pela tabela própria da operadora."
CLAUSULA_9 = "Cláusula 9: o Brasíndice usado é a edição vigente na data do atendimento."
TEXTO_DO_CONTRATO = (
    "TERMO ADITIVO No 13 AO CONTRATO DE CREDENCIAMENTO firmado em 01/10/2015. "
    f"Assinado em 20/04/2027. Vigencia a partir de 01/05/2027. {CLAUSULA_7} {CLAUSULA_9}"
)
BRASINDICE = "Edição do Brasíndice usada pela operadora."
TAXA_DE_SALA = "Taxa de sala cirúrgica paga por porte anestésico, pela tabela própria da operadora."

CAMPOS_DO_CONTRATO = {
    "data_assinatura": "2015-10-01",
    "aditivo_numero": "13",
    "aditivo_data": "2027-04-20",
    "vigencia_inicio": "2027-05-01",
    "vencimento": None,
}

LOTE_DO_CONTRATO = {
    "resposta": "Li o contrato: uma regra nova e o que o contrato diz sobre uma que já existe.",
    "propostas": [
        {
            **_proposta(
                secao="TAX",
                texto=TAXA_DE_SALA,
                origem="ADITIVO",
                motivo="A taxa de sala passa a ser conferida pelo porte anestésico.",
            ),
            "clausula": CLAUSULA_7,
        }
    ],
    "o_contrato_diz": [
        {"regra_codigo": "ALFA-PRI-03", "clausula": CLAUSULA_9},
        # A IA inventou o código: fica de fora.
        {"regra_codigo": "ALFA-PRI-99", "clausula": CLAUSULA_7},
    ],
}


class _ProvedorDoContrato(_Provedor):
    """O provedor da conversa, que também lê as datas e o lote do contrato."""

    def __init__(self, nomes: dict[str, str]):
        super().__init__(nomes)
        self.campos: dict = CAMPOS_DO_CONTRATO
        self.lote_do_contrato: dict = LOTE_DO_CONTRATO

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        from anthropic_apoio import nome_do_schema

        corpo = json.loads(request.content)
        formato = nome_do_schema(self.nomes, corpo)
        if formato not in ("CamposDoContrato", "LoteDoContrato"):
            return super().__call__(request)
        texto = "\n".join(bloco["text"] for m in corpo["messages"] for bloco in m["content"])
        self.pedidos.append((formato, texto))
        resposta = self.campos if formato == "CamposDoContrato" else self.lote_do_contrato
        return httpx2.Response(200, json=mensagem(json.dumps(resposta)))


@pytest.fixture
def provedor(monkeypatch) -> _ProvedorDoContrato:
    from anthropic_apoio import cliente_por_transporte, nomear_schemas

    from app.services.contas_medicas import ia

    duble = _ProvedorDoContrato(nomear_schemas(monkeypatch))
    monkeypatch.setattr(ia, "_cliente", lambda: cliente_por_transporte(duble))
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


@pytest.fixture
def com_storage(cenario):  # noqa: F811
    cliente, banco, provedor = cenario
    banco.storage = _Storage()
    return cliente, banco, provedor


def _subir(cliente, conteudo: bytes, nome: str = "aditivo-13.pdf", tipo: str = "application/pdf"):
    return cliente.post(ROTA_DO_CONTRATO, files={"arquivo": (nome, conteudo, tipo)})


def _contrato_da_alfa(banco) -> dict[str, Any]:
    oid = next(o["id"] for o in banco.linhas("cm_operadora") if o["sigla"] == "ALFA")
    return next(c for c in banco.linhas("cm_contrato") if c["operadora_id"] == oid)


# ═══════════════════════════════════════════════════════════════════════════
# 1. O contrato vira um lote: Regras por cláusula e o "o contrato diz"
# ═══════════════════════════════════════════════════════════════════════════


class TestOContratoViraLote:
    def test_o_contrato_em_texto_vira_regras_por_clausula_e_o_contrato_diz_das_regras_existentes(self, com_storage):
        cliente, banco, provedor = com_storage

        resposta = _subir(cliente, _pdf(TEXTO_DO_CONTRATO))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [(i["numero"], i["tipo"], i["regra_codigo"]) for i in corpo["lote"]["itens"]] == [
            (1, "REGRA_NOVA", None),
            (2, "REGRA_ALTERADA", "ALFA-PRI-03"),
            (3, "PARAMETRO", None),
        ]

        # A cláusula vira Regra nova, com o trecho do contrato e a prova.
        nova = _item(corpo, 1)
        assert nova["proposta"] == {
            "secao": "TAX",
            "texto": TAXA_DE_SALA,
            "tipo": "CONTRATUAL",
            "origem": "ADITIVO",
            "contrato_diz": CLAUSULA_7,
        }
        assert (nova["pede_prova"], nova["prova"]["contas"]) == (True, 10)

        # A Regra que já existe ganha só o "o contrato diz": o texto não muda,
        # a análise não muda, e o item vai sem prova.
        diz = _item(corpo, 2)
        assert diz["proposta"]["contrato_diz"] == CLAUSULA_9
        assert diz["proposta"]["texto"] == diz["proposta"]["texto_anterior"] == BRASINDICE
        assert (diz["pede_prova"], diz["prova"]) == (False, None)

        # As datas do aviso de reajuste entram no mesmo lote.
        datas = _item(corpo, 3)
        assert datas["proposta"]["chave"] == "contrato"
        assert datas["proposta"]["depois"] == {
            "assinatura": "2015-10-01",
            "ultimo_aditivo": {"numero": "13", "data": "2027-04-20", "inicio_vigencia": "2027-05-01"},
            "aviso_antecedencia_dias": 60,
        }
        assert datas["pede_prova"] is False

        # O Auditor recebeu o texto do contrato e a memória.
        [(_, pedido)] = [p for p in provedor.pedidos if p[0] == "LoteDoContrato"]
        assert "TERMO ADITIVO No 13" in pedido and "| ALFA-PRI-03 |" in pedido
        (lote,) = banco.linhas("cm_lote")
        assert lote["fonte"] == "CONTRATO"
        assert [(m["autor"], m["texto"]) for m in corpo["mensagens"]] == [
            ("PESSOA", "Contrato enviado: aditivo-13.pdf"),
            ("AUDITOR", LOTE_DO_CONTRATO["resposta"]),
        ]
        # Nada vale antes do ok.
        assert _versoes(banco, "ALFA") == {"1.0": True}
        # Uma prova, só da Regra nova.
        assert len(provedor.da_prova()) == 10


# ═══════════════════════════════════════════════════════════════════════════
# 2. O ok aplica o lote do contrato numa versão da Memória
# ═══════════════════════════════════════════════════════════════════════════


class TestOOkDoContrato:
    def test_o_ok_aplica_o_lote_do_contrato_numa_versao_so_da_memoria(self, com_storage):
        cliente, banco, _provedor = com_storage
        assert _subir(cliente, _pdf(TEXTO_DO_CONTRATO)).status_code == 200

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 200, resposta.text
        assert _versoes(banco, "ALFA") == {"1.0": False, "1.1": True}
        regras = _regras_vigentes(banco)
        # A Regra da cláusula nasce vigente, com o trecho do contrato.
        assert (regras["ALFA-TAX-01"]["texto"], regras["ALFA-TAX-01"]["status"]) == (TAXA_DE_SALA, "VIGENTE")
        assert regras["ALFA-TAX-01"]["contrato_diz"] == CLAUSULA_7
        # A Regra que existia ganha o "o contrato diz" e fica como estava: o
        # texto e a pendência são de quem decide a regra, não do contrato.
        pri_03 = regras["ALFA-PRI-03"]
        assert (pri_03["texto"], pri_03["status"], pri_03["contrato_diz"]) == (BRASINDICE, "PENDENTE", CLAUSULA_9)
        assert _vigente(banco)["parametros_json"]["contrato"]["ultimo_aditivo"]["numero"] == "13"
        (lote,) = banco.linhas("cm_lote")
        assert (lote["estado"], lote["memoria_versao_id"]) == ("APLICADO", _vigente(banco)["id"])

    def test_o_contrato_diz_de_uma_pendente_deixa_o_tema_dela_aberto(self, com_storage):
        """O "o contrato diz" não decide a Regra pendente (#1494 com #1495): ela
        segue pendente, e o cartão dela continua na fila de Validação."""
        cliente, banco, _provedor = com_storage
        _tema(banco, "t-pri-03", "ALFA", "ALFA-PRI-03", [])
        assert _subir(cliente, _pdf(TEXTO_DO_CONTRATO)).status_code == 200

        resposta = cliente.post(ROTA, json={"texto": "ok"})

        assert resposta.status_code == 200, resposta.text
        (tema,) = banco.linhas("cm_validacao_tema")
        assert (tema["estado"], tema["decisao"]) == ("ABERTO", None)


# ═══════════════════════════════════════════════════════════════════════════
# 3. O contrato fica gravado e o aviso de reajuste continua saindo
# ═══════════════════════════════════════════════════════════════════════════


class TestOContratoEOAviso:
    def test_o_contrato_fica_gravado_e_o_aviso_de_reajuste_sai_depois_do_ok(self, com_storage):
        cliente, banco, _provedor = com_storage
        antes = dict(_contrato_da_alfa(banco))

        arquivo = _item(_subir(cliente, _pdf(TEXTO_DO_CONTRATO)).json(), 3)["proposta"]["arquivo"]

        # O arquivo fica guardado já no envio, como na aba Contratos; as datas
        # só valem com o ok.
        assert arquivo.startswith("contratos/") and arquivo in banco.storage.arquivos
        assert _contrato_da_alfa(banco) == antes

        assert cliente.post(ROTA, json={"texto": "ok"}).status_code == 200

        contrato = _contrato_da_alfa(banco)
        assert {k: contrato[k] for k in ("arquivo", "aditivo_numero", "aditivo_data", "vigencia_inicio")} == {
            "arquivo": arquivo,
            "aditivo_numero": "13",
            "aditivo_data": "2027-04-20",
            "vigencia_inicio": "2027-05-01",
        }
        # Vigência mais um ano, calculado, como a aba Contratos faz.
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2028-05-01", True)
        assert (contrato["confirmado_por"], bool(contrato["confirmado_em"])) == (GESTAO["id"], True)
        # A rotina diária avisa 60 dias antes do vencimento novo, uma vez só.
        assert avisar_contratos(banco, date(2028, 3, 2)) == 1
        assert avisar_contratos(banco, date(2028, 3, 3)) == 0

    def test_a_imagem_fica_guardada_sem_lote_e_o_auditor_diz_por_que(self, com_storage):
        cliente, banco, provedor = com_storage

        resposta = _subir(cliente, b"\x89PNG\r\n\x1a\n", nome="contrato-2015.png", tipo="image/png")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["lote"] is None
        assert corpo["mensagens"][-1]["texto"].startswith("O arquivo não tem texto para ler")
        assert [k for k in banco.storage.arquivos if k.endswith(".png")]
        assert provedor.pedidos == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. O kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


class TestOKit:
    def test_o_kit_diz_que_o_contrato_subido_na_conversa_vira_regras_por_clausula(self):
        no_ar = KIT.read_text(encoding="utf-8").split("## O que já está no ar")[1].split("\n## ")[0]

        for termo in (
            "Enviar contrato",
            "cláusula a cláusula",
            '"o contrato diz"',
            "recurso de glosa",
            "sem prova",
            "aviso de reajuste",
            "aba Contratos",
        ):
            assert termo in no_ar, termo
