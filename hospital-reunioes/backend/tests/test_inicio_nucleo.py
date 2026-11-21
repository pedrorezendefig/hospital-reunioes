"""O que o Núcleo espera da pessoa, no Início (issue #1939, PRD #1932, ADR 0104).

A fonte do Núcleo traz o que a Fase 1 tem: o Termo de Adesão pendente, o
documento do Núcleo esperando a assinatura da pessoa e a capacitação em que
falta confirmar a presença, esta com a ação de um clique. O acesso segue a
ADR 0095: a regra de verdade (`recursos_nsp`, lida da Participação vigente)
roda aqui sobre o banco de mentira, e o super admin sem acesso ao Núcleo não
recebe nada do Núcleo.
"""

from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers import inicio as inicio_router  # noqa: E402
from app.routers import seguranca_do_paciente_capacitacoes as capacitacoes_router  # noqa: E402
from app.services.inicio import fonte_nucleo  # noqa: E402
from app.services.seguranca_do_paciente import permissao  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)
HOJE = AGORA.date()


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int | None = None


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list = []
        self._limite: int | None = None

    def select(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) == valor)
        return self

    def neq(self, coluna, valor):
        self._filtros.append(lambda linha: linha.get(coluna) is not None and linha.get(coluna) != valor)
        return self

    def in_(self, coluna, valores):
        valores = set(valores)
        self._filtros.append(lambda linha: linha.get(coluna) in valores)
        return self

    def is_(self, coluna, valor):
        assert valor == "null"
        self._filtros.append(lambda linha: linha.get(coluna) is None)
        return self

    def lte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) <= valor)
        return self

    def gte(self, coluna, valor):
        self._filtros.append(lambda linha: str(linha.get(coluna)) >= valor)
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, *_a, **_kw):
        return self

    def update(self, campos):
        self._campos = campos
        return self

    def limit(self, n):
        self._limite = n
        return self

    def execute(self):
        if getattr(self, "_campos", None) is not None:
            for linha in self._linhas:
                if all(f(linha) for f in self._filtros):
                    linha.update(self._campos)
        linhas = [dict(linha) for linha in self._linhas if all(f(linha) for f in self._filtros)]
        return _Result(linhas[: self._limite] if self._limite is not None else linhas)


NUCLEO_ID = "C_NSP"


@dataclass
class _Banco:
    colegiados: list = field(default_factory=lambda: [{"id": NUCLEO_ID, "slug": "nsp"}])
    participacoes: list = field(default_factory=list)
    pendencias: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    nsp_termos_envios: list = field(default_factory=list)
    nsp_documentos: list = field(default_factory=list)
    nsp_documentos_envios: list = field(default_factory=list)
    nsp_documentos_signatarios: list = field(default_factory=list)
    nsp_capacitacoes: list = field(default_factory=list)
    nsp_capacitacao_participantes: list = field(default_factory=list)
    # As Atas, o trilho (#1936) e a Ouvidoria (#1937) também leem o banco; vazios aqui.
    reuniao_participantes: list = field(default_factory=list)
    reuniao_aceites: list = field(default_factory=list)
    ouvidoria_setor_responsaveis: list = field(default_factory=list)
    ouvidoria_protocolos: list = field(default_factory=list)
    ouvidoria_prorrogacoes: list = field(default_factory=list)
    # A fonte das Rotinas (#1874) também lê o banco; vazia aqui.
    rotinas: list = field(default_factory=list)
    # Contas médicas (#1940) também lê o banco para o Super admin; vazia aqui.
    cm_conta: list = field(default_factory=list)
    cm_atendimento: list = field(default_factory=list)
    # A fonte das Contestações (#1870) lê o histórico; vazio aqui.
    pendencia_historico: list = field(default_factory=list)

    def table(self, nome):
        return _Consulta(getattr(self, nome))


def _pessoa(pid: str, nome: str, **campos) -> dict:
    return {"id": pid, "nome_completo": nome, "access_profile": "regular", "role": "colaborador", **campos}


PRESIDENTE = _pessoa("P_PRES", "Paula Prado")
MEMBRO_COM_TERMO = _pessoa("P_COM", "Marcos Melo")
MEMBRO_SEM_TERMO = _pessoa("P_SEM", "Sara Souza")
ACESSO_PLENO = _pessoa("P_PLENO", "Davi Dias", perfil_nsp="acesso_pleno")
DE_FORA = _pessoa("P_FORA", "Fábio Faria")
SUPER_ADMIN = _pessoa("P_ADMIN", "Alice Alves", access_profile="super_admin")


def _participacao(pid: str, pessoa: dict, papel: str = "membro", termo: str | None = "2026-10-01T12:00:00+00:00"):
    return {
        "id": pid,
        "colegiado_id": NUCLEO_ID,
        "participante_id": pessoa["id"],
        "papel": papel,
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": "2027-12-31",
        "termo_assinado_em": termo,
    }


def _banco_do_nucleo(**tabelas) -> _Banco:
    """O Núcleo com a Presidência e o membro com Termo assinados e o membro
    sem Termo ainda pendente."""
    participacoes = [
        _participacao("PA_PRES", PRESIDENTE, papel="presidencia"),
        _participacao("PA_COM", MEMBRO_COM_TERMO),
        _participacao("PA_SEM", MEMBRO_SEM_TERMO, termo=None),
    ]
    return _Banco(participacoes=participacoes, **tabelas)


@pytest.fixture(autouse=True)
def _hoje(monkeypatch):
    monkeypatch.setattr(permissao, "hoje_em_sao_paulo", lambda: HOJE)
    monkeypatch.setattr(fonte_nucleo, "hoje_em_sao_paulo", lambda: HOJE)


def _rota(monkeypatch, me: dict, banco: _Banco):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: AGORA)
    return asyncio.run(inicio_router.get_inicio(current_user={"id": "u1"}, supabase=banco))


def _do_nucleo(resposta) -> list:
    return [item for item in resposta.itens if item.area == "Segurança do Paciente"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O Termo de Adesão pendente
# ═══════════════════════════════════════════════════════════════════════════


class TestTermoDeAdesao:
    def test_membro_sem_termo_ve_o_item_com_o_botao_que_abre_o_termo(self, monkeypatch):
        banco = _banco_do_nucleo(
            nsp_termos_envios=[
                {
                    "id": "T1",
                    "participacao_id": "PA_SEM",
                    "situacao": "enviado",
                    "enviado_em": "2026-11-10T13:00:00+00:00",
                    "created_at": "2026-11-10T13:00:00+00:00",
                }
            ]
        )

        resposta = _rota(monkeypatch, MEMBRO_SEM_TERMO, banco)

        itens = _do_nucleo(resposta)
        assert [item.tipo for item in itens] == ["termo_de_adesao"]
        termo = itens[0]
        assert termo.titulo == "Assinar o Termo de Adesão ao Núcleo"
        assert termo.acao == "Abrir o Termo de Adesão"
        assert termo.destino == "/seguranca-do-paciente/documentos"
        # Sem prazo no módulo: fica no grupo Sem prazo, com há quantos dias espera.
        assert termo.grupo == "sem_prazo"
        assert termo.dias_esperando == 8
        assert resposta.contadores.passou_do_prazo == 0

    def test_termo_novo_da_renovacao_aparece_para_quem_ja_tinha_assinado(self, monkeypatch):
        """A renovação e a mudança de papel carimbam `termo_gerado_em` depois da
        assinatura (issue #1769): a ficha mostra "Termo pendente" e o Início
        também. O acesso segue liberado, sem a faixa, e o link foi pelo e-mail."""
        banco = _banco_do_nucleo(
            nsp_termos_envios=[
                {
                    "id": "T_NOVO",
                    "participacao_id": "PA_COM",
                    "situacao": "enviado",
                    "enviado_em": "2026-11-15T13:00:00+00:00",
                    "created_at": "2026-11-15T13:00:00+00:00",
                }
            ]
        )
        banco.participacoes[1]["termo_gerado_em"] = "2026-11-15T12:59:00+00:00"

        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, banco)

        [termo] = _do_nucleo(resposta)
        assert termo.tipo == "termo_de_adesao"
        assert termo.titulo == "Assinar o Termo de Adesão ao Núcleo"
        assert termo.origem == "Termo de Adesão novo esperando a sua assinatura. O link foi para o seu e-mail."
        # Sem a faixa (o acesso segue liberado), o botão leva ao Núcleo.
        assert termo.destino == "/seguranca-do-paciente"
        assert termo.grupo == "sem_prazo"
        assert termo.dias_esperando == 3

    def test_revisao_material_do_regimento_pede_o_termo_de_novo(self, monkeypatch):
        """Quem assinou antes da última revisão material do Regimento tem Termo
        novo pendente; sem envio novo, ele espera desde a revisão."""
        banco = _banco_do_nucleo(
            nsp_documentos=[
                {
                    "id": "D_REG4",
                    "tipo": "regimento",
                    "versao": 4,
                    "natureza_revisao": "material",
                    "publicado_em": "2026-11-11T01:00:00+00:00",
                }
            ]
        )

        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, banco)

        [termo] = _do_nucleo(resposta)
        assert termo.tipo == "termo_de_adesao"
        assert termo.origem == "Termo de Adesão novo esperando a sua assinatura. O link foi para o seu e-mail."
        # 01h UTC de 11/11 ainda é 10/11 em Brasília.
        assert termo.dias_esperando == 8

    def test_termo_assinado_depois_do_ultimo_pedido_nao_aparece(self, monkeypatch):
        banco = _banco_do_nucleo()
        banco.participacoes[1]["termo_gerado_em"] = "2026-09-01T12:00:00+00:00"

        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, banco)

        assert _do_nucleo(resposta) == []

    def test_envio_a_noite_em_brasilia_conta_o_dia_de_brasilia(self, monkeypatch):
        """`enviado_em` chega em UTC: o envio às 22h de 10/11 em Brasília é
        01h de 11/11 em UTC, e espera desde 10/11, não desde 11/11."""
        banco = _banco_do_nucleo(
            nsp_termos_envios=[
                {
                    "id": "T1",
                    "participacao_id": "PA_SEM",
                    "situacao": "enviado",
                    "enviado_em": "2026-11-11T01:00:00+00:00",
                    "created_at": "2026-11-11T01:00:00+00:00",
                }
            ]
        )

        [termo] = _do_nucleo(_rota(monkeypatch, MEMBRO_SEM_TERMO, banco))

        assert termo.dias_esperando == 8


# ═══════════════════════════════════════════════════════════════════════════
# 2. O documento do Núcleo esperando a assinatura da pessoa
# ═══════════════════════════════════════════════════════════════════════════

REGIMENTO = {"id": "D_REG", "tipo": "regimento", "titulo": "Regimento Interno do NSP", "versao": 3}


def _documento_esperando(**signatario) -> dict:
    """O Regimento v3 enviado para a Diretoria Executiva e a Presidência."""
    base = {"id": "S_PRES", "envio_id": "E1", "participante_id": PRESIDENTE["id"], "assinado_em": None}
    return {
        "nsp_documentos": [REGIMENTO],
        "nsp_documentos_envios": [
            {"id": "E1", "documento_id": "D_REG", "situacao": "enviado", "enviado_em": "2026-11-16T12:00:00+00:00"}
        ],
        "nsp_documentos_signatarios": [
            {**base, **signatario},
            {"id": "S_PLENO", "envio_id": "E1", "participante_id": ACESSO_PLENO["id"], "assinado_em": None},
        ],
    }


class TestDocumentoAAssinar:
    def test_documento_esperando_a_assinatura_aparece_na_fila_de_quem_assina(self, monkeypatch):
        banco = _banco_do_nucleo(**_documento_esperando())

        resposta = _rota(monkeypatch, PRESIDENTE, banco)

        itens = _do_nucleo(resposta)
        assert [item.tipo for item in itens] == ["documento_do_nucleo"]
        documento = itens[0]
        assert documento.titulo == "Assinar o Regimento Interno, versão 3"
        assert documento.origem == "Documento do Núcleo esperando a sua assinatura. O link foi para o seu e-mail."
        assert documento.destino == "/seguranca-do-paciente/documentos"
        assert documento.grupo == "sem_prazo"
        assert documento.dias_esperando == 2

    def test_documento_enviado_a_noite_em_brasilia_conta_o_dia_de_brasilia(self, monkeypatch):
        tabelas = _documento_esperando()
        # 22h30 de 15/11 em Brasília.
        tabelas["nsp_documentos_envios"][0]["enviado_em"] = "2026-11-16T01:30:00+00:00"

        [documento] = _do_nucleo(_rota(monkeypatch, PRESIDENTE, _banco_do_nucleo(**tabelas)))

        assert documento.dias_esperando == 3

    def test_o_documento_sai_da_fila_depois_da_assinatura(self, monkeypatch):
        banco = _banco_do_nucleo(**_documento_esperando(assinado_em="2026-11-17T15:00:00+00:00"))

        resposta = _rota(monkeypatch, PRESIDENTE, banco)

        assert _do_nucleo(resposta) == []

    def test_o_documento_de_envio_cancelado_nao_aparece(self, monkeypatch):
        tabelas = _documento_esperando()
        tabelas["nsp_documentos_envios"][0]["situacao"] = "cancelado"

        resposta = _rota(monkeypatch, PRESIDENTE, _banco_do_nucleo(**tabelas))

        assert _do_nucleo(resposta) == []

    def test_quem_nao_assina_o_documento_nao_o_recebe(self, monkeypatch):
        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, _banco_do_nucleo(**_documento_esperando()))

        assert _do_nucleo(resposta) == []


# ═══════════════════════════════════════════════════════════════════════════
# 3. A capacitação com presença a confirmar, resolvida no Início
# ═══════════════════════════════════════════════════════════════════════════


def _capacitacao(cid: str, data: str, titulo: str = "Higiene das mãos") -> dict:
    return {"id": cid, "titulo": titulo, "data": data}


def _na_lista(cid: str, pessoa: dict, confirmada: str | None = None) -> dict:
    return {
        "id": f"{cid}-{pessoa['id']}",
        "capacitacao_id": cid,
        "participante_id": pessoa["id"],
        "presenca_confirmada_em": confirmada,
    }


def _cliente(monkeypatch, me: dict, banco: _Banco) -> TestClient:
    """O Início e a rota de presença de verdade, sobre o mesmo banco: o
    clique do Início chama o endpoint que a fonte devolveu."""

    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: AGORA)
    monkeypatch.setattr(capacitacoes_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(capacitacoes_router, "hoje_em_sao_paulo", lambda: HOJE)
    limiter._storage.reset()
    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(inicio_router.router, prefix="/api")
    app.include_router(capacitacoes_router.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "x@hsm", "metadata": {}}
    app.dependency_overrides[get_supabase_client] = lambda: banco
    return TestClient(app)


class TestCapacitacaoComPresencaAConfirmar:
    def test_a_capacitacao_aparece_com_o_botao_confirmar_presenca(self, monkeypatch):
        banco = _banco_do_nucleo(
            nsp_capacitacoes=[_capacitacao("CAP1", "2026-11-12")],
            nsp_capacitacao_participantes=[_na_lista("CAP1", MEMBRO_COM_TERMO)],
        )

        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, banco)

        itens = _do_nucleo(resposta)
        assert [item.tipo for item in itens] == ["capacitacao"]
        capacitacao = itens[0]
        assert capacitacao.titulo == "Confirmar a presença na capacitação Higiene das mãos"
        assert capacitacao.origem == "Capacitação do Núcleo de 12/11/2026."
        assert capacitacao.destino == "/seguranca-do-paciente/capacitacoes"
        assert capacitacao.acao_de_um_clique is not None
        assert capacitacao.acao_de_um_clique.rotulo == "Confirmar presença"
        assert capacitacao.acao_de_um_clique.endpoint == "/api/nsp/capacitacoes/CAP1/presenca"
        assert capacitacao.grupo == "sem_prazo"
        assert capacitacao.dias_esperando == 6

    def test_capacitacao_futura_ou_ja_confirmada_nao_aparece(self, monkeypatch):
        banco = _banco_do_nucleo(
            nsp_capacitacoes=[_capacitacao("FUTURA", "2026-11-19"), _capacitacao("FEITA", "2026-11-02")],
            nsp_capacitacao_participantes=[
                _na_lista("FUTURA", MEMBRO_COM_TERMO),
                _na_lista("FEITA", MEMBRO_COM_TERMO, confirmada="2026-11-02T18:00:00+00:00"),
            ],
        )

        resposta = _rota(monkeypatch, MEMBRO_COM_TERMO, banco)

        assert _do_nucleo(resposta) == []

    def test_confirmar_presenca_resolve_sem_sair_do_inicio(self, monkeypatch):
        banco = _banco_do_nucleo(
            nsp_capacitacoes=[_capacitacao("CAP1", "2026-11-18")],
            nsp_capacitacao_participantes=[_na_lista("CAP1", MEMBRO_COM_TERMO)],
        )
        cliente = _cliente(monkeypatch, MEMBRO_COM_TERMO, banco)

        antes = cliente.get("/api/inicio").json()
        [item] = [i for i in antes["itens"] if i["tipo"] == "capacitacao"]
        clique = cliente.post(item["acao_de_um_clique"]["endpoint"])
        depois = cliente.get("/api/inicio").json()

        assert clique.status_code == 200, clique.text
        assert [i for i in depois["itens"] if i["tipo"] == "capacitacao"] == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. Um teste por papel (ADR 0095): ninguém recebe o que o módulo não mostraria
# ═══════════════════════════════════════════════════════════════════════════


def _banco_completo() -> _Banco:
    """Um Termo pendente, o Regimento esperando a Presidência e o Acesso
    pleno, e uma capacitação com todo mundo na lista, inclusive quem é de fora
    do Núcleo e o super admin."""
    pessoas = (PRESIDENTE, MEMBRO_COM_TERMO, MEMBRO_SEM_TERMO, ACESSO_PLENO, DE_FORA, SUPER_ADMIN)
    return _banco_do_nucleo(
        nsp_termos_envios=[
            {"id": "T1", "participacao_id": "PA_SEM", "situacao": "enviado", "enviado_em": "2026-11-10T13:00:00+00:00"}
        ],
        **_documento_esperando(),
        nsp_capacitacoes=[_capacitacao("CAP1", "2026-11-12")],
        nsp_capacitacao_participantes=[_na_lista("CAP1", pessoa) for pessoa in pessoas],
    )


@pytest.mark.parametrize(
    ("pessoa", "esperado"),
    [
        pytest.param(PRESIDENTE, ["documento_do_nucleo", "capacitacao"], id="presidencia"),
        pytest.param(MEMBRO_COM_TERMO, ["capacitacao"], id="membro_com_termo"),
        pytest.param(MEMBRO_SEM_TERMO, ["termo_de_adesao"], id="membro_sem_termo"),
        pytest.param(ACESSO_PLENO, ["documento_do_nucleo", "capacitacao"], id="acesso_pleno"),
        pytest.param(DE_FORA, [], id="de_fora_do_nucleo"),
        pytest.param(SUPER_ADMIN, [], id="super_admin_sem_acesso_ao_nucleo"),
    ],
)
def test_cada_papel_recebe_so_o_que_o_nucleo_espera_dele(monkeypatch, pessoa, esperado):
    resposta = _rota(monkeypatch, pessoa, _banco_completo())

    assert sorted(item.tipo for item in _do_nucleo(resposta)) == sorted(esperado)
    assert resposta.avisos == []


def test_super_admin_nao_recebe_item_do_nucleo_nem_sendo_signatario(monkeypatch):
    """O super admin só alcança a configuração técnica (ADR 0095, decisão 4):
    nem um envio que o nomeie por engano põe o Núcleo na fila dele."""
    tabelas = _documento_esperando(participante_id=SUPER_ADMIN["id"])

    resposta = _rota(monkeypatch, SUPER_ADMIN, _banco_do_nucleo(**tabelas))

    assert resposta.itens == []


# ═══════════════════════════════════════════════════════════════════════════
# 5. O kit de conhecimento do Produto Segurança do Paciente
# ═══════════════════════════════════════════════════════════════════════════


def test_o_kit_de_conhecimento_diz_o_que_o_nucleo_poe_no_inicio():
    caminho = Path(fonte_nucleo.__file__).parents[2] / "conhecimento" / "seguranca-do-paciente.md"
    texto = " ".join(caminho.read_text(encoding="utf-8").split())

    assert "O Núcleo no Início:" in texto
    assert "o Termo de Adesão que falta assinar" in texto
    assert "a capacitação em que falta confirmar a presença, a partir do dia da capacitação" in texto
    assert "ficam no grupo Sem prazo" in texto
    assert "pelo botão **Confirmar presença**, sem abrir outra tela" in texto
    assert "a linha sai e a frase e os números do topo se refazem" in texto
    assert "o super admin sem o Acesso pleno também não vê nada do Núcleo no Início" in texto
    assert chr(0x2014) not in texto
    assert chr(0x2013) not in texto
