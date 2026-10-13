"""Contratos e aviso de reajuste de Contas medicas (issue #1144, PRD #1129).

Cada operadora tem um contrato (`cm_contrato`) com assinatura, ultimo aditivo,
inicio da vigencia e vencimento. Ele nasce do bloco `contrato` da memoria da
operadora e muda pela tela: a pessoa envia o contrato ou o aditivo, a IA
propoe os quatro campos e nada vale antes de a pessoa confirmar. A rotina
diaria calcula os dias que faltam e, na data do aviso (vencimento menos a
antecedencia da memoria), manda um aviso CONTAS_MEDICAS ao sino de quem tem
"contratos e avisos", uma vez so (`cm_aviso`).

O duble do banco e o da carga da operadora (`test_contas_medicas_operadoras`),
com as restricoes da migration 118 que esta fatia pode ferir: um contrato por
operadora e um aviso por contrato e data.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openai import OpenAI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_contas_medicas_ia import USO_PADRAO, _Provedor  # noqa: E402
from test_contas_medicas_operadoras import (  # noqa: E402
    _Banco,
    _enviar_memoria,
    _erro,
    _matriz_da_migration,
    _memoria,
    _pessoa,
)
from test_contas_medicas_operadoras import _cliente as _cliente_da_carga  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import contas_medicas_contratos as contratos_router  # noqa: E402
from app.services.contas_medicas import ia  # noqa: E402

MEMORIA_ALFA = _memoria("MEMORIA-ALFA-v1.0.md")
BLOCO_ALFA = """contrato:
  assinatura: 2015-10-01
  ultimo_aditivo: { numero: 12, inicio_vigencia: 2026-05-01 }
  aviso_antecedencia_dias: 60
"""


@pytest.fixture
def provedor(monkeypatch) -> _Provedor:
    """O duble do provedor de IA do teste do adaptador (#1130): a chamada
    passa pelo adaptador de verdade (schema estrito, ZDR, custo) e para no HTTP."""
    duble = _Provedor()

    def cliente():
        return OpenAI(
            api_key="chave-de-teste",
            base_url="https://openrouter.ai/api/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(duble)),
            max_retries=0,
        )

    monkeypatch.setattr(ia, "_cliente", cliente)
    monkeypatch.setattr(ia, "_esperar", lambda _segundos: None)
    return duble


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _memoria_com_contrato(bloco: str) -> str:
    assert BLOCO_ALFA in MEMORIA_ALFA, "o bloco contrato da fixture ALFA mudou"
    return MEMORIA_ALFA.replace(BLOCO_ALFA, bloco)


class _BancoDosContratos(_Banco):
    """O duble da carga com os UNIQUE da migration 118."""

    def _validar(self, tabela: str, linha: dict, ignorar: dict | None = None) -> None:
        super()._validar(tabela, linha, ignorar)
        outras = [o for o in self.linhas(tabela) if o is not ignorar]
        if tabela == "cm_contrato" and any(o["operadora_id"] == linha["operadora_id"] for o in outras):
            raise _erro("23505", "duplicate key value violates unique constraint cm_contrato_operadora_id_key")
        if tabela == "cm_aviso" and any(
            (o["contrato_id"], o["data_prevista"]) == (linha["contrato_id"], linha["data_prevista"]) for o in outras
        ):
            raise _erro("23505", "duplicate key value violates unique constraint cm_aviso_unico")


class _Bucket:
    def __init__(self, arquivos: dict[str, bytes]):
        self._arquivos = arquivos

    def upload(self, caminho, conteudo, _opcoes):
        self._arquivos[caminho] = conteudo

    def download(self, caminho):
        if caminho not in self._arquivos:
            raise RuntimeError("Object not found")
        return self._arquivos[caminho]


class _Storage:
    def __init__(self):
        self.arquivos: dict[str, bytes] = {}
        self.buckets: set[str] = set()

    def from_(self, bucket):
        self.buckets.add(bucket)
        return _Bucket(self.arquivos)


GESTAO = _pessoa(perfil_contas_medicas="gestao_contas_medicas")


# ═══════════════════════════════════════════════════════════════════════════
# 1. O contrato nasce da memoria
# ═══════════════════════════════════════════════════════════════════════════


class TestContratoDaMemoria:
    def test_memoria_sem_vencimento_cria_o_contrato_com_vigencia_mais_um_ano_calculado(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        resposta = _enviar_memoria(cliente, MEMORIA_ALFA)

        assert resposta.status_code == 201, resposta.text
        [operadora] = banco.linhas("cm_operadora")
        [contrato] = banco.linhas("cm_contrato")
        assert contrato["operadora_id"] == operadora["id"]
        assert contrato["data_assinatura"] == "2015-10-01"
        assert contrato["aditivo_numero"] == "12"
        assert contrato["vigencia_inicio"] == "2026-05-01"
        assert contrato["vencimento"] == "2027-05-01"
        assert contrato["vencimento_calculado"] is True
        assert contrato["vencimento_e_negociacao"] is False
        assert contrato["aviso_dias"] == 60

    def test_comentario_que_diz_que_a_data_nao_e_vencimento_marca_a_negociacao(self):
        """O bloco da memoria da Unimed: o YAML joga o comentario fora, e e ele
        que diz que a data e o inicio do debate do reajuste."""
        unimed = _memoria_com_contrato(
            "contrato:\n"
            "  assinatura: null            # corpo do contrato nao disponivel\n"
            "  ultimo_aditivo: { numero: null, inicio_vigencia: 2026-04-15 }\n"
            "  vencimento: 2027-01-15      # NÃO é vencimento contratual. É a data do debate do reajuste\n"
            "  aviso_antecedencia_dias: 0  # alerta na propria data\n"
        )
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, unimed).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert contrato["vencimento"] == "2027-01-15"
        assert contrato["vencimento_calculado"] is False
        assert contrato["vencimento_e_negociacao"] is True
        assert contrato["aviso_dias"] == 0
        assert contrato["data_assinatura"] is None
        assert contrato["aditivo_numero"] is None

    def test_vencimento_escrito_e_marcado_calculado_no_comentario_fica_calculado(self):
        """O bloco da ASSIM: a data esta escrita, e o comentario diz que foi calculada."""
        assim = _memoria_com_contrato(
            "contrato:\n"
            "  assinatura: 2015-10-01\n"
            "  ultimo_aditivo: { numero: 110, inicio_vigencia: 2026-05-01 }\n"
            "  vencimento: 2027-05-01      # CALCULADO: 1 ano após a vigência do último aditivo. Confirmar.\n"
            "  aviso_antecedencia_dias: 60\n"
        )
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, assim).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2027-05-01", True)
        assert contrato["vencimento_e_negociacao"] is False

    def test_memoria_nova_nao_desfaz_o_que_a_pessoa_confirmou(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())
        assert _enviar_memoria(cliente, MEMORIA_ALFA).status_code == 201
        [contrato] = banco.linhas("cm_contrato")
        contrato.update({"vencimento": "2027-09-30", "vencimento_calculado": False, "confirmado_em": "2026-10-10"})
        nova = MEMORIA_ALFA.replace("aviso_antecedencia_dias: 60", "aviso_antecedencia_dias: 90")

        assert _enviar_memoria(cliente, nova).status_code == 201

        [contrato] = banco.linhas("cm_contrato")
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2027-09-30", False)
        assert contrato["aviso_dias"] == 90

    def test_memoria_sem_bloco_contrato_nao_cria_contrato(self):
        cliente, banco = _cliente_da_carga(GESTAO, _BancoDosContratos())

        assert _enviar_memoria(cliente, _memoria_com_contrato("")).status_code == 201

        assert banco.linhas("cm_contrato") == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. Dias que faltam e situacao
# ═══════════════════════════════════════════════════════════════════════════

HOJE = date(2027, 3, 2)


def _banco_com_contratos(*contratos: tuple[str, str | None, dict[str, Any]]) -> _BancoDosContratos:
    """Uma operadora por tupla `(sigla, vencimento, campos)`; vencimento `None` = sem contrato."""
    banco = _BancoDosContratos()
    for sigla, vencimento, campos in contratos:
        operadora = banco.inserir("cm_operadora", {"sigla": sigla, "nome": f"{sigla.title()} Saude"})
        if vencimento is not None:
            banco.inserir(
                "cm_contrato",
                {
                    "operadora_id": operadora["id"],
                    "vencimento": vencimento,
                    "vencimento_calculado": False,
                    "vencimento_e_negociacao": False,
                    "aviso_dias": 60,
                    **campos,
                },
            )
    return banco


class TestSituacaoDoContrato:
    def test_61_60_1_e_menos_1_dias_e_sem_contrato(self):
        from app.services.contas_medicas.contratos import listar_contratos

        banco = _banco_com_contratos(
            ("A61", "2027-05-02", {}),
            ("B60", "2027-05-01", {}),
            ("C01", "2027-03-03", {}),
            ("D00", "2027-03-01", {}),
            ("ESEM", None, {}),
        )

        linhas = {linha["sigla"]: linha for linha in listar_contratos(banco, HOJE)}

        assert {s: (linha["dias"], linha["situacao"]) for s, linha in linhas.items()} == {
            "A61": (61, "EM_DIA"),
            "B60": (60, "NEGOCIAR"),
            "C01": (1, "NEGOCIAR"),
            "D00": (-1, "VENCIDO"),
            "ESEM": (None, "SEM_CONTRATO"),
        }
        assert linhas["B60"]["contrato"]["vencimento"] == "2027-05-01"
        assert linhas["ESEM"]["contrato"] is None

    def test_contrato_sem_vencimento_e_sem_contrato(self):
        from app.services.contas_medicas.contratos import listar_contratos

        banco = _banco_com_contratos(("ALFA", "", {}))
        banco.linhas("cm_contrato")[0]["vencimento"] = None

        [linha] = listar_contratos(banco, HOJE)

        assert (linha["dias"], linha["situacao"]) == (None, "SEM_CONTRATO")


# ═══════════════════════════════════════════════════════════════════════════
# 3. O aviso no sino
# ═══════════════════════════════════════════════════════════════════════════

# Uma pessoa por perfil do modulo, mais uma desligada e uma fora do eixo.
EQUIPE = [
    _pessoa(id="FAT", perfil_contas_medicas="faturista"),
    _pessoa(id="COO", perfil_contas_medicas="coordenadora"),
    _pessoa(id="GES", perfil_contas_medicas="gestao_contas_medicas"),
    _pessoa(id="DME", perfil_contas_medicas="diretoria_medica"),
    _pessoa(id="DEX", perfil_contas_medicas="diretoria_executiva"),
    _pessoa(id="CRE", perfil_contas_medicas="credenciamento"),
    _pessoa(id="CR2", perfil_contas_medicas="credenciamento", ativo=False),
    _pessoa(id="FORA"),
]
COM_A_PERMISSAO = ["CRE", "DEX", "DME", "GES"]


def _banco_do_aviso(*contratos: tuple[str, str | None, dict[str, Any]]) -> _BancoDosContratos:
    banco = _banco_com_contratos(*contratos)
    banco.tabelas["participantes"] = [dict(p) for p in EQUIPE]
    banco.tabelas["cm_perfil_permissao"] = _matriz_da_migration()
    return banco


def _avisar(banco, hoje: date) -> int:
    from app.services.contas_medicas.contratos import avisar_contratos

    return avisar_contratos(banco, hoje)


class TestAvisoNoSino:
    def test_na_data_do_aviso_todos_com_a_permissao_recebem_o_texto_da_spec(self):
        banco = _banco_do_aviso(("ASSIM", "2027-05-01", {}))

        assert _avisar(banco, HOJE) == 1

        notificacoes = banco.linhas("notificacoes")
        assert sorted(n["destinatario_id"] for n in notificacoes) == COM_A_PERMISSAO
        assert {n["tipo"] for n in notificacoes} == {"CONTAS_MEDICAS"}
        assert {n["mensagem"] for n in notificacoes} == {
            "ASSIM: o contrato vence em 60 dias (01/05/2027). Iniciar a negociação do reajuste."
        }
        [aviso] = banco.linhas("cm_aviso")
        assert aviso["contrato_id"] == banco.linhas("cm_contrato")[0]["id"]
        assert aviso["data_prevista"] == "2027-03-02"
        assert aviso["enviado_em"]
        assert {n["referencia_id"] for n in notificacoes} == {f"contrato:{aviso['id']}"}

    def test_o_aviso_nao_se_repete_no_dia_seguinte(self):
        banco = _banco_do_aviso(("ASSIM", "2027-05-01", {}))
        _avisar(banco, HOJE)

        assert _avisar(banco, HOJE) == 0
        assert _avisar(banco, date(2027, 3, 3)) == 0

        assert len(banco.linhas("notificacoes")) == len(COM_A_PERMISSAO)
        assert len(banco.linhas("cm_aviso")) == 1

    def test_antes_da_data_do_aviso_nada_sai(self):
        banco = _banco_do_aviso(("ASSIM", "2027-05-02", {}))

        assert _avisar(banco, HOJE) == 0

        assert banco.linhas("notificacoes") == []
        assert banco.linhas("cm_aviso") == []

    def test_antecedencia_zero_avisa_na_propria_data_e_o_texto_da_unimed_diz_inicia_o_debate(self):
        banco = _banco_do_aviso(("UNIMED", "2027-01-15", {"aviso_dias": 0, "vencimento_e_negociacao": True}))

        assert _avisar(banco, date(2027, 1, 14)) == 0
        assert _avisar(banco, date(2027, 1, 15)) == 1

        assert {n["mensagem"] for n in banco.linhas("notificacoes")} == {
            "UNIMED: hoje (15/01/2027) inicia o debate do reajuste. A data não é o vencimento do contrato."
        }
        assert banco.linhas("cm_aviso")[0]["data_prevista"] == "2027-01-15"

    def test_antecedencia_ausente_e_60_dias_e_o_texto_de_negociacao_conta_os_dias(self):
        banco = _banco_do_aviso(("LEVE", "2027-05-01", {"aviso_dias": None, "vencimento_e_negociacao": True}))

        assert _avisar(banco, HOJE) == 1

        assert {n["mensagem"] for n in banco.linhas("notificacoes")} == {
            "LEVE: em 60 dias (01/05/2027) inicia o debate do reajuste. A data não é o vencimento do contrato."
        }

    def test_contrato_vencido_sem_aviso_nao_dispara_atrasado(self):
        """A rotina alcanca o dia perdido (container fora do ar na hora), mas
        nao avisa o contrato que ja venceu: o aviso e para negociar antes."""
        banco = _banco_do_aviso(("VELHO", "2027-03-01", {}))

        assert _avisar(banco, HOJE) == 0
        assert banco.linhas("notificacoes") == []


class TestRotinaNoScheduler:
    def test_a_rotina_roda_todo_dia_no_fuso_de_sao_paulo(self):
        from apscheduler.triggers.cron import CronTrigger

        from app.cron import scheduler as cron

        try:
            cron.start_scheduler()
            job = cron.scheduler.get_job("contratos_contas_medicas")
            assert job is not None
            assert job.func is cron.avisar_contratos_contas_medicas
            assert isinstance(job.trigger, CronTrigger)
            campos = {f.name: str(f) for f in job.trigger.fields}
            assert (campos["day"], campos["day_of_week"]) == ("*", "*")
            assert str(job.trigger.timezone) == "America/Sao_Paulo"
        finally:
            cron.stop_scheduler()

    def test_o_job_avisa_com_a_data_de_hoje_em_sao_paulo(self, monkeypatch):
        from app.cron import scheduler as cron

        banco = _banco_do_aviso(("ASSIM", "2027-05-01", {}))
        monkeypatch.setattr(cron, "_supabase", lambda: banco)
        monkeypatch.setattr(cron, "_hoje_em_sao_paulo", lambda: HOJE)

        cron.avisar_contratos_contas_medicas()

        assert len(banco.linhas("notificacoes")) == len(COM_A_PERMISSAO)


# ═══════════════════════════════════════════════════════════════════════════
# 4. A tela: lista, envio do contrato, confirmacao e quem pode
# ═══════════════════════════════════════════════════════════════════════════

ROTA = "/api/contas-medicas/contratos"
CREDENCIAMENTO = _pessoa(id="CRE", auth_user_id="auth-cre", perfil_contas_medicas="credenciamento")
GESTORA = _pessoa(id="GES", auth_user_id="auth-ges", perfil_contas_medicas="gestao_contas_medicas")
FATURISTA = _pessoa(id="FAT", auth_user_id="auth-fat", perfil_contas_medicas="faturista")

TEXTO_DO_CONTRATO = (
    "TERMO ADITIVO No 13 AO CONTRATO DE CREDENCIAMENTO firmado em 01/10/2015. "
    "Assinado em 20/04/2027. Vigencia a partir de 01/05/2027."
)
PROPOSTA_DA_IA = {
    "data_assinatura": "2015-10-01",
    "aditivo_numero": "13",
    "aditivo_data": "2027-04-20",
    "vigencia_inicio": "2027-05-01",
    "vencimento": None,
}


def _pdf(*paginas: str) -> bytes:
    from weasyprint import HTML

    corpo = "".join(f'<div style="page-break-before: always"><p>{texto}</p></div>' for texto in paginas)
    return HTML(string=f"<html><body>{corpo}</body></html>").write_pdf()


def _tela(pessoa: dict[str, Any], banco: _BancoDosContratos | None = None) -> tuple[TestClient, _BancoDosContratos]:
    banco = banco or _banco_com_contratos(("ALFA", "2027-05-01", {"aditivo_numero": "12"}), ("BETA", None, {}))
    banco.tabelas["participantes"] = [dict(pessoa)]
    banco.tabelas["cm_perfil_permissao"] = _matriz_da_migration()
    banco.storage = _Storage()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(contratos_router.router, prefix="/api")

    async def _usuario() -> dict[str, Any]:
        return {"id": pessoa["auth_user_id"], "email": pessoa["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app), banco


def _enviar(cliente: TestClient, conteudo: bytes, nome: str = "aditivo-13.pdf", tipo: str = "application/pdf"):
    return cliente.post(f"{ROTA}/ALFA/arquivo", files={"arquivo": (nome, conteudo, tipo)})


def _confirmar(cliente: TestClient, **campos):
    return cliente.post(f"{ROTA}/ALFA", json=campos)


class TestATelaDosContratos:
    def test_lista_uma_linha_por_operadora_com_a_situacao(self, monkeypatch):
        monkeypatch.setattr(contratos_router, "hoje_em_sao_paulo", lambda: HOJE)
        cliente, _ = _tela(CREDENCIAMENTO)

        resposta = cliente.get(ROTA)

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert [(c["sigla"], c["dias"], c["situacao"]) for c in corpo["contratos"]] == [
            ("ALFA", 60, "NEGOCIAR"),
            ("BETA", None, "SEM_CONTRATO"),
        ]
        assert corpo["pode_editar"] is False

    def test_a_gestao_pode_editar(self):
        cliente, _ = _tela(GESTORA)

        assert cliente.get(ROTA).json()["pode_editar"] is True

    def test_quem_nao_tem_contratos_e_avisos_recebe_403(self):
        cliente, _ = _tela(FATURISTA)

        assert cliente.get(ROTA).status_code == 403


class TestEnvioDoContrato:
    def test_contrato_com_texto_volta_com_os_campos_da_ia_e_nada_vale_antes_de_confirmar(self, provedor):
        provedor.responder((json.dumps(PROPOSTA_DA_IA), USO_PADRAO))
        cliente, banco = _tela(GESTORA)
        antes = [dict(c) for c in banco.linhas("cm_contrato")]

        resposta = _enviar(cliente, _pdf(TEXTO_DO_CONTRATO))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["tem_texto"] is True
        assert corpo["campos"] == {
            **PROPOSTA_DA_IA,
            "vencimento": "2028-05-01",
            "vencimento_calculado": True,
        }
        assert banco.linhas("cm_contrato") == antes
        [corpo_da_ia] = provedor.corpos
        assert "TERMO ADITIVO No 13" in corpo_da_ia["messages"][1]["content"][0]["text"]
        assert corpo_da_ia["provider"]["zdr"] is True
        assert corpo["arquivo"] in banco.storage.arquivos
        assert banco.storage.buckets == {"contas-medicas"}
        assert len(banco.linhas("cm_chamada_ia")) == 1

    def test_confirmado_vale_com_autor_e_data(self, provedor):
        provedor.responder((json.dumps(PROPOSTA_DA_IA), USO_PADRAO))
        cliente, banco = _tela(GESTORA)
        proposta = _enviar(cliente, _pdf(TEXTO_DO_CONTRATO)).json()

        resposta = _confirmar(cliente, **proposta["campos"], arquivo=proposta["arquivo"])

        assert resposta.status_code == 200, resposta.text
        [contrato] = banco.linhas("cm_contrato")
        assert {k: contrato[k] for k in (*PROPOSTA_DA_IA, "vencimento_calculado", "arquivo")} == {
            **PROPOSTA_DA_IA,
            "vencimento": "2028-05-01",
            "vencimento_calculado": True,
            "arquivo": proposta["arquivo"],
        }
        assert contrato["confirmado_por"] == "GES"
        assert contrato["confirmado_em"]

    def test_vencimento_digitado_pela_pessoa_nao_e_calculado(self):
        cliente, banco = _tela(GESTORA)

        resposta = _confirmar(cliente, vigencia_inicio="2027-05-01", vencimento="2028-03-31", vencimento_calculado=True)

        assert resposta.status_code == 200, resposta.text
        [contrato] = banco.linhas("cm_contrato")
        assert (contrato["vencimento"], contrato["vencimento_calculado"]) == ("2028-03-31", False)

    def test_operadora_sem_contrato_ganha_o_contrato_confirmado(self):
        cliente, banco = _tela(GESTORA)

        resposta = cliente.post(f"{ROTA}/BETA", json={"vencimento": "2027-12-31"})

        assert resposta.status_code == 200, resposta.text
        beta = next(o for o in banco.linhas("cm_operadora") if o["sigla"] == "BETA")
        [contrato] = [c for c in banco.linhas("cm_contrato") if c["operadora_id"] == beta["id"]]
        assert contrato["vencimento"] == "2027-12-31"

    def test_arquivo_sem_texto_deixa_os_campos_para_digitar_sem_chamar_a_ia(self, provedor):
        cliente, banco = _tela(GESTORA)

        resposta = _enviar(cliente, _pdf(""))

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["tem_texto"] is False
        assert set(corpo["campos"].values()) == {None, False}
        assert provedor.corpos == []
        assert corpo["arquivo"] in banco.storage.arquivos

    def test_imagem_entra_e_os_campos_ficam_para_digitar(self, provedor):
        cliente, _ = _tela(GESTORA)

        resposta = _enviar(cliente, b"\x89PNG\r\n\x1a\n", nome="contrato-2015.png", tipo="image/png")

        assert resposta.status_code == 200, resposta.text
        assert resposta.json()["tem_texto"] is False
        assert provedor.corpos == []

    def test_ia_fora_do_formato_deixa_os_campos_para_digitar(self, provedor):
        provedor.responder(("nao e json", USO_PADRAO))
        cliente, _ = _tela(GESTORA)

        resposta = _enviar(cliente, _pdf(TEXTO_DO_CONTRATO))

        assert resposta.status_code == 200, resposta.text
        assert set(resposta.json()["campos"].values()) == {None, False}
        assert (
            resposta.json()["aviso"] == "Não foi possível ler os campos do arquivo agora. Digite os campos e confirme."
        )

    def test_arquivo_de_outro_lugar_do_bucket_e_recusado(self):
        """Sem a cerca, a chave de um prontuario viraria o "contrato" e o
        download devolveria o PDF do paciente."""
        cliente, banco = _tela(GESTORA)

        resposta = _confirmar(cliente, vencimento="2028-05-01", arquivo="envio-1/arq-1.pdf")

        assert resposta.status_code == 422
        assert banco.linhas("cm_contrato")[0]["vencimento"] == "2027-05-01"

    def test_o_arquivo_confirmado_pode_ser_baixado(self, provedor):
        provedor.responder((json.dumps(PROPOSTA_DA_IA), USO_PADRAO))
        cliente, _ = _tela(GESTORA)
        conteudo = _pdf(TEXTO_DO_CONTRATO)
        proposta = _enviar(cliente, conteudo).json()
        _confirmar(cliente, **proposta["campos"], arquivo=proposta["arquivo"])

        resposta = cliente.get(f"{ROTA}/ALFA/arquivo")

        assert resposta.status_code == 200
        assert resposta.content == conteudo
        assert resposta.headers["content-type"] == "application/pdf"


class TestCredenciamentoSoVe:
    def test_credenciamento_ve_a_tela_mas_recebe_403_no_post(self, provedor):
        cliente, banco = _tela(CREDENCIAMENTO)
        antes = [dict(c) for c in banco.linhas("cm_contrato")]

        assert cliente.get(ROTA).status_code == 200
        assert _enviar(cliente, _pdf(TEXTO_DO_CONTRATO)).status_code == 403
        assert _confirmar(cliente, vencimento="2030-01-01").status_code == 403

        assert banco.linhas("cm_contrato") == antes
        assert banco.storage.arquivos == {}
        assert provedor.corpos == []

    def test_credenciamento_recebe_o_aviso(self):
        banco = _banco_do_aviso(("ASSIM", "2027-05-01", {}))

        _avisar(banco, HOJE)

        assert "CRE" in {n["destinatario_id"] for n in banco.linhas("notificacoes")}


class TestAsRotasEstaoNoApp:
    def test_o_app_de_verdade_registra_as_rotas_dos_contratos(self):
        from app.main import app

        caminhos = app.openapi()["paths"]
        assert len(caminhos) > 50, "piso de sanidade: o openapi voltou quase vazio"
        assert "get" in caminhos[ROTA]
        assert "post" in caminhos[f"{ROTA}/{{sigla}}"]
        assert "post" in caminhos[f"{ROTA}/{{sigla}}/arquivo"]
        assert "get" in caminhos[f"{ROTA}/{{sigla}}/arquivo"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O texto do Produto no Kit de conhecimento
# ═══════════════════════════════════════════════════════════════════════════

KIT = Path(__file__).resolve().parents[1] / "app" / "conhecimento" / "contas-medicas.md"


def _secao(titulo: str) -> str:
    return KIT.read_text(encoding="utf-8").split(f"## {titulo}")[1].split("\n## ")[0]


class TestOKitDizComoOAvisoFunciona:
    """O Assistente de Tecnologia responde Demanda com este texto: quem pergunta
    por que o aviso nao chegou precisa ouvir quando ele sai e para quem."""

    def test_a_secao_dos_contratos_diz_quando_e_para_quem_o_aviso_sai(self):
        secao = _secao("Contratos e aviso de reajuste")

        for trecho in (
            "vencimento menos a antecedência",
            "60 dias",
            "uma vez só",
            "na própria data",
            "credenciamento",
            "sino",
            "inicia o debate do reajuste",
            "calculado",
            "confirma",
            "digita",
        ):
            assert trecho in secao, trecho

    def test_o_que_ja_esta_no_ar_inclui_a_tela_contratos(self):
        assert "tela Contratos" in _secao("O que já está no ar")
