"""O caso da Ouvidoria do setor e a fila do ouvidor no Início (issue #1937,
PRD #1932, ADR 0099 e ADR 0104, decisão 6).

Titular, substituto e gestor vigentes veem na Minha Fila o caso acionado para o
setor deles que ainda espera a área, com o prazo do setor, e o botão abre a
Tela do responsável pela porta do login. O item não carrega relato nem
identificação: o título é o Assunto, ou o protocolo no caso sem Assunto e no
sigiloso. Quem tem Perfil da Ouvidoria vê uma linha de resumo da fila, fora da
frase e dos contadores.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.routers import inicio as inicio_router  # noqa: E402

BRT = ZoneInfo("America/Sao_Paulo")
# Quarta-feira, 18/11/2026, 10h em Brasília.
AGORA = datetime(2026, 11, 18, 10, 0, tzinfo=BRT)


# ─── O banco de mentira ───────────────────────────────────────────────────


@dataclass
class _Result:
    data: list


class _Consulta:
    def __init__(self, linhas: list[dict]):
        self._linhas = linhas
        self._filtros: list = []
        self._negar = False
        self._recorte: tuple[int, int] | None = None

    @property
    def not_(self):
        self._negar = True
        return self

    def _filtro(self, f):
        if self._negar:
            self._negar = False
            self._filtros.append(lambda linha: not f(linha))
        else:
            self._filtros.append(f)
        return self

    def select(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def range(self, inicio, fim):
        self._recorte = (inicio, fim + 1)
        return self

    def limit(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        return self._filtro(lambda linha: linha.get(coluna) == valor)

    def neq(self, coluna, valor):
        return self._filtro(lambda linha: linha.get(coluna) is not None and linha.get(coluna) != valor)

    def gte(self, coluna, valor):
        return self._filtro(lambda linha: linha.get(coluna) is not None and str(linha.get(coluna)) >= str(valor))

    def in_(self, coluna, valores):
        valores = set(valores)
        return self._filtro(lambda linha: linha.get(coluna) in valores)

    def is_(self, coluna, valor):
        assert valor == "null"
        return self._filtro(lambda linha: linha.get(coluna) is None)

    def ilike(self, coluna, padrao):
        assert "%" not in padrao and "_" not in padrao.replace("\\_", "")
        alvo = padrao.replace("\\", "").lower()
        return self._filtro(lambda linha: (linha.get(coluna) or "").lower() == alvo)

    def execute(self):
        linhas = [dict(linha) for linha in self._linhas if all(f(linha) for f in self._filtros)]
        return _Result(linhas[slice(*self._recorte)] if self._recorte else linhas)


@dataclass
class _Banco:
    pendencias: list = field(default_factory=list)
    reunioes: list = field(default_factory=list)
    ouvidoria_setor_responsaveis: list = field(default_factory=list)
    ouvidoria_protocolos: list = field(default_factory=list)
    ouvidoria_prorrogacoes: list = field(default_factory=list)
    # A fonte das Rotinas (#1874) também lê o banco; vazia aqui.
    rotinas: list = field(default_factory=list)
    # A fonte das Atas e o trilho (#1936) também leem o banco; vazios aqui.
    reuniao_participantes: list = field(default_factory=list)
    reuniao_aceites: list = field(default_factory=list)
    # A fonte do Núcleo (#1939) também lê o banco; sem o Núcleo aqui.
    colegiados: list = field(default_factory=list)
    # A fonte das Contestações (#1870) lê o histórico; vazio aqui.
    pendencia_historico: list = field(default_factory=list)

    def table(self, nome):
        return _Consulta(getattr(self, nome))


def _responsavel(email: str, setor: str = "Recepção", papel: str = "titular", **campos) -> dict:
    base = {
        "setor": setor,
        "papel": papel,
        "email": email,
        "vigencia_inicio": "2026-01-01",
        "vigencia_fim": None,
    }
    return {**base, **campos}


def _caso(id_: str, setor: str = "Recepção", **campos) -> dict:
    base = {
        "id": id_,
        "numero": int(id_.strip("C") or 0),
        "protocolo": f"OUV-2026-{id_}",
        "setor": setor,
        "status": "aguardando_area",
        "validada_em": "2026-11-10T13:00:00+00:00",
        "prazo_area_em": "2026-11-19T20:00:00+00:00",
        "prazo_resposta": "2026-11-25",
        "assunto": f"Demora no atendimento {id_}",
        "resumo": "Resumo literal do relato",
        "relato_integral": "Relato integral de quem manifestou",
        "manifestante_nome": "Maria Manifestante",
        "sigilo_reforcado": False,
        "anonimo": False,
        "tipo_manifestacao": "reclamacao",
        "arquivada_em": None,
    }
    return {**base, **campos}


TITULAR = {"id": "P_TIT", "nome_completo": "Tânia Titular", "email": "tania@hsm.com.br", "access_profile": None}


def _rota(monkeypatch, me: dict | None, banco: _Banco, agora: datetime = AGORA):
    async def _participante(_user, _sb, fields=None):
        return me

    monkeypatch.setattr(inicio_router, "get_participante_for_user", _participante)
    monkeypatch.setattr(inicio_router, "agora_em_brasilia", lambda: agora)

    import asyncio

    return asyncio.run(inicio_router.get_inicio(current_user={"id": "u1"}, supabase=banco))


def _da_ouvidoria(resposta) -> list:
    return [item for item in resposta.itens if item.tipo == "caso_da_ouvidoria"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O caso acionado para o setor de quem é responsável vigente
# ═══════════════════════════════════════════════════════════════════════════


class TestCasoDoSetor:
    def test_titular_ve_o_caso_do_setor_com_o_prazo_e_o_botao_da_tela_do_responsavel(self, monkeypatch):
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("Tania@HSM.com.br")],
            ouvidoria_protocolos=[_caso("C1")],
        )

        resposta = _rota(monkeypatch, TITULAR, banco)

        [item] = _da_ouvidoria(resposta)
        assert item.id == "C1"
        assert item.prazo == date(2026, 11, 19)
        assert item.grupo == "ate_48_horas"
        assert item.area == "Ouvidoria"
        assert item.destino == "/ouvidoria/responder/C1"
        assert item.acao == "Responder"

    def test_substituto_ve_o_caso_do_setor(self, monkeypatch):
        substituto = {**TITULAR, "id": "P_SUB", "email": "sergio@hsm.com.br"}
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("sergio@hsm.com.br", papel="substituto")],
            ouvidoria_protocolos=[_caso("C2")],
        )

        assert [item.id for item in _da_ouvidoria(_rota(monkeypatch, substituto, banco))] == ["C2"]

    def test_gestor_ve_o_caso_do_setor(self, monkeypatch):
        gestor = {**TITULAR, "id": "P_GES", "email": "gilda@hsm.com.br"}
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("gilda@hsm.com.br", papel="gestor")],
            ouvidoria_protocolos=[_caso("C3")],
        )

        assert [item.id for item in _da_ouvidoria(_rota(monkeypatch, gestor, banco))] == ["C3"]

    def test_responsavel_de_outro_setor_nao_ve_o_caso(self, monkeypatch):
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("tania@hsm.com.br", setor="Recepção")],
            ouvidoria_protocolos=[_caso("C4", setor="Recepção"), _caso("C5", setor="Farmácia")],
        )

        assert [item.id for item in _da_ouvidoria(_rota(monkeypatch, TITULAR, banco))] == ["C4"]

    def test_quem_teve_a_vigencia_encerrada_deixa_de_ver(self, monkeypatch):
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("tania@hsm.com.br", vigencia_fim="2026-11-17")],
            ouvidoria_protocolos=[_caso("C6")],
        )

        resposta = _rota(monkeypatch, TITULAR, banco)

        assert _da_ouvidoria(resposta) == []
        assert resposta.avisos == []


# ═══════════════════════════════════════════════════════════════════════════
# 2. O item mostra o Assunto e nada de quem manifestou
# ═══════════════════════════════════════════════════════════════════════════


class TestSigiloDoItem:
    def _item(self, monkeypatch, caso: dict):
        banco = _Banco(ouvidoria_setor_responsaveis=[_responsavel("tania@hsm.com.br")], ouvidoria_protocolos=[caso])
        [item] = _da_ouvidoria(_rota(monkeypatch, TITULAR, banco))
        return item

    def test_o_titulo_e_o_assunto_e_o_item_nao_leva_relato_resumo_nem_manifestante(self, monkeypatch):
        item = self._item(monkeypatch, _caso("C10", assunto="Demora na recepção do pronto-socorro"))

        assert item.titulo == "Demora na recepção do pronto-socorro"
        texto = item.model_dump_json()
        assert "Resumo literal" not in texto
        assert "Relato integral" not in texto
        assert "Maria Manifestante" not in texto

    def test_caso_sem_assunto_mostra_o_protocolo(self, monkeypatch):
        item = self._item(monkeypatch, _caso("C11", assunto=None))

        assert item.titulo == "Manifestação OUV-2026-C11"

    def test_caso_sigiloso_mostra_o_protocolo_e_nao_o_assunto(self, monkeypatch):
        item = self._item(monkeypatch, _caso("C12", assunto="Denúncia sobre a chefia", sigilo_reforcado=True))

        assert item.titulo == "Manifestação OUV-2026-C12"
        assert "Denúncia" not in item.model_dump_json()


# ═══════════════════════════════════════════════════════════════════════════
# 3. O caso que já não espera a área sai da fila
# ═══════════════════════════════════════════════════════════════════════════


class TestSaiDaFila:
    def _ids(self, monkeypatch, casos: list[dict], prorrogacoes: list[dict] | None = None) -> list[str]:
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("tania@hsm.com.br")],
            ouvidoria_protocolos=casos,
            ouvidoria_prorrogacoes=prorrogacoes or [],
        )
        return sorted(item.id for item in _da_ouvidoria(_rota(monkeypatch, TITULAR, banco)))

    def test_caso_respondido_sai_da_fila(self, monkeypatch):
        assert self._ids(monkeypatch, [_caso("C20"), _caso("C21", status="respondido")]) == ["C20"]

    def test_caso_devolvido_a_ouvidoria_sai_da_fila(self, monkeypatch):
        assert self._ids(monkeypatch, [_caso("C22"), _caso("C23", status="em_classificacao")]) == ["C22"]

    def test_caso_com_prorrogacao_pedida_sai_da_fila(self, monkeypatch):
        prorrogacoes = [
            {"manifestacao_id": "C25", "status": "pendente"},
            {"manifestacao_id": "C26", "status": "aprovada"},
        ]

        assert self._ids(monkeypatch, [_caso("C24"), _caso("C25"), _caso("C26")], prorrogacoes) == ["C24", "C26"]

    def test_caso_ainda_nao_acionado_nao_entra(self, monkeypatch):
        assert self._ids(monkeypatch, [_caso("C27"), _caso("C28", validada_em=None)]) == ["C27"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. A Fila do papel: a linha de resumo da fila da Ouvidoria
# ═══════════════════════════════════════════════════════════════════════════

OUVIDOR = {
    "id": "P_OUV",
    "nome_completo": "Otávio Ouvidor",
    "email": "ouvidor@hsm.com.br",
    "access_profile": None,
    "perfil_ouvidoria": "ouvidor",
}
SEM_PAPEL = {"id": "P_NADA", "nome_completo": "Nina Neutra", "email": "nina@hsm.com.br", "access_profile": "regular"}


def _fila_do_hospital() -> list[dict]:
    """Seis esperam e três estão vencidas."""
    sem_prazo_da_area = {"prazo_area_em": None, "validada_em": None}
    return [
        _caso("C30", status="novo", prazo_resposta="2026-11-25", **sem_prazo_da_area),
        _caso("C31", status="em_classificacao", prazo_resposta="2026-11-15", **sem_prazo_da_area),
        _caso("C32", prazo_area_em="2026-11-17T20:00:00+00:00"),
        _caso("C33", prazo_area_em="2026-11-19T20:00:00+00:00"),
        # O elogio nunca vence (ADR 0088).
        _caso("C34", tipo_manifestacao="elogio", prazo_resposta="2026-11-01", prazo_area_em=None),
        _caso("C35", status="novo", sigilo_reforcado=True, prazo_resposta="2026-11-10", **sem_prazo_da_area),
        # Fora da fila: respondido, parado esperando o manifestante e arquivado.
        _caso("C36", status="respondido", prazo_area_em="2026-11-01T20:00:00+00:00"),
        _caso("C37", status="aguardando_manifestante", prazo_area_em="2026-11-01T20:00:00+00:00"),
        _caso("C38", status="novo", prazo_resposta="2026-11-01", arquivada_em="2026-11-02T10:00:00+00:00"),
    ]


class TestFilaDoPapel:
    def test_ouvidor_ve_a_linha_da_fila_fora_da_frase_e_dos_contadores(self, monkeypatch):
        banco = _Banco(ouvidoria_protocolos=_fila_do_hospital())

        resposta = _rota(monkeypatch, OUVIDOR, banco)

        [linha] = resposta.filas_do_papel
        assert (linha.fila, linha.esperam, linha.vencidas, linha.destino) == ("ouvidoria", 6, 3, "/ouvidoria")
        assert linha.resumo == "6 manifestações esperam, 3 vencidas."
        assert resposta.itens == []
        assert resposta.frase.titulo == "Otávio, você está em dia."
        assert resposta.contadores.passou_do_prazo == 0

    def test_diretoria_executiva_tambem_ve_a_linha(self, monkeypatch):
        diretoria = {**OUVIDOR, "perfil_ouvidoria": "diretoria_executiva"}

        resposta = _rota(monkeypatch, diretoria, _Banco(ouvidoria_protocolos=_fila_do_hospital()))

        assert [linha.fila for linha in resposta.filas_do_papel] == ["ouvidoria"]

    def test_resumo_no_singular(self, monkeypatch):
        banco = _Banco(ouvidoria_protocolos=[_caso("C39", prazo_area_em="2026-11-17T20:00:00+00:00")])

        [linha] = _rota(monkeypatch, OUVIDOR, banco).filas_do_papel

        assert linha.resumo == "1 manifestação espera, 1 vencida."

    def test_responsavel_do_setor_nao_ve_a_fila_do_papel(self, monkeypatch):
        banco = _Banco(
            ouvidoria_setor_responsaveis=[_responsavel("tania@hsm.com.br")],
            ouvidoria_protocolos=_fila_do_hospital(),
        )

        assert _rota(monkeypatch, TITULAR, banco).filas_do_papel == []

    def test_pessoa_sem_papel_na_ouvidoria_nao_ve_caso_nem_fila(self, monkeypatch):
        banco = _Banco(ouvidoria_protocolos=[_caso("C40"), *_fila_do_hospital()])

        resposta = _rota(monkeypatch, SEM_PAPEL, banco)

        assert _da_ouvidoria(resposta) == []
        assert resposta.filas_do_papel == []
        assert resposta.avisos == []

    def test_fila_que_falha_vira_aviso(self, monkeypatch):
        class _BancoQuebrado(_Banco):
            def table(self, nome):
                if nome == "ouvidoria_protocolos":
                    raise RuntimeError("timeout")
                return super().table(nome)

        resposta = _rota(monkeypatch, OUVIDOR, _BancoQuebrado())

        assert resposta.filas_do_papel == []
        assert [a.fonte for a in resposta.avisos] == ["fila_da_ouvidoria"]


# ═══════════════════════════════════════════════════════════════════════════
# 5. O kit de conhecimento do Produto Ouvidoria diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDeConhecimento:
    def test_o_texto_da_ouvidoria_explica_o_inicio(self):
        caminho = Path(inicio_router.__file__).parents[1] / "conhecimento" / "ouvidoria.md"
        texto = " ".join(caminho.read_text(encoding="utf-8").split())

        assert "## O Início" in texto
        assert "O titular, o substituto e o gestor vigentes de um setor veem no Início" in texto
        assert "caso de outro setor não aparece, e quem teve a vigência encerrada deixa de ver" in texto
        assert "nunca o relato, o resumo ou o nome de quem manifestou" in texto
        assert "o caso sem assunto e o caso sigiloso aparecem pelo número do protocolo" in texto
        assert "quando pede prorrogação e o pedido espera a decisão do ouvidor" in texto
        assert "Essa linha não entra na frase do topo nem nos contadores de prazo" in texto
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto
