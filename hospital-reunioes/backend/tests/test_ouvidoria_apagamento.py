"""Apagar pela Diretoria: a porta antecipada da Retenção (issue #595, PRD #591,
ADR 0047).

Apagar não é DELETE. É a mesma política de retenção dos cinco anos, feita hoje
por ato humano: o relato, a identificação, os anexos e o texto livre saem, e o
protocolo, a trilha e os números ficam. Por isso este arquivo exercita a ROTA
contra o serviço de verdade, e não contra um dublê dele: a porta nova e o cron
precisam terminar no mesmo estado, e um mock da retenção deixaria a rota verde
sobre uma anonimização que nunca aconteceu.

Três armadilhas de teste vazio moram aqui:

* provar que a rota grava o pedido é vazio se a requisição morreu antes (403,
  409, 422): todo teste de efeito confere o 200 antes de olhar o banco;
* provar que o gate barra o ouvidor é vazio se a requisição tivesse morrido por
  outro motivo (id inexistente, corpo inválido): o teste do 403 usa o MESMO
  caso e o MESMO corpo que passam com a Diretoria;
* provar a ordem ("o carimbo por último") pelo estado final não prova nada: o
  banco termina igual em qualquer ordem. Quem prova é a sequência de escritas
  propostas, que o Supabase falso registra na ordem.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from types import SimpleNamespace

import httpx
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
from app.services import ouvidoria_notificacoes, ouvidoria_retencao, ouvidoria_trilha  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": None,
    "perfil_ouvidoria": "diretoria_executiva",
}
# Papel nas Reuniões não concede nada na Ouvidoria (RN-40), e apagar é o ato em
# que isso mais pesa: o super admin administra o sistema, não o caso.
SUPER_ADMIN = {"id": "P99", "nome_completo": "Root", "access_profile": "super_admin", "perfil_ouvidoria": None}

# Terça-feira, 8 de setembro de 2026, 14h de Brasília.
INICIO = dt.datetime(2026, 9, 8, 17, 0, tzinfo=dt.UTC)

MOTIVO = "Pedido da paciente, com decisao da Diretoria em 08/09/2026."

# O que o PRÓPRIO ato escreve no caso: os três campos do pedido e o par do
# Arquivo. Eles estão na lista do que a anonimização preserva, e por isso a
# comparação campo a campo os trata à parte: nascem nulos e terminam
# preenchidos, e o que se prova sobre eles é que a varredura não os apaga.
GRAVADOS_PELO_PROPRIO_ATO = (
    "apagamento_pedido_em",
    "apagamento_pedido_por",
    "apagamento_motivo",
    "arquivada_em",
    "arquivada_por",
)

# O que o manifestante escreveu, espalhado pelos cinco lugares que a política
# varre. Nenhum deles pode sobreviver ao apagamento.
RELATO = "Joana da Silva, RG 12.345.678, esperou tres horas na recepcao."
RESPOSTA_DA_AREA = "Falamos com a paciente Joana da Silva no telefone 11 99999-0000."


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _nunca_envia_email_de_verdade(monkeypatch):
    """O pytest do backend carrega o .env real (Resend de produção). Apagar não
    manda email nenhum, e o mock existe para que um caminho novo não descubra
    isso disparando de verdade."""

    def _fake(destinatario, assunto, html_content, texto_fallback):
        raise AssertionError("Apagar não manda email")

    monkeypatch.setattr(ouvidoria_notificacoes, "_enviar_email", _fake)


def _caso(numero: int = 7, **overrides) -> dict:
    """Um caso encerrado ontem, com o Dossiê inteiro e o Arquivo vazio."""
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "encerrado",
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente Joana relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-1",
        "gravidade": "medio",
        "canal": "ana",
        "canal_setor": None,
        "canal_ponto": "Poltrona 12 do saguao",
        "contato_em": "2026-08-14T19:50:00+00:00",
        "prazo_area_em": None,
        "prazo_conclusivo_em": None,
        "prazo_rompido_em": None,
        "validada_em": None,
        "validada_por": None,
        "extrato_para_o_setor": None,
        "resposta_da_area": RESPOSTA_DA_AREA,
        "respondida_em": None,
        "respondida_por_nome": None,
        "encerrada_em": "2026-09-07T14:00:00+00:00",
        "desfecho": "procedente",
        "desfecho_descricao": "Escala ajustada apos o relato de Joana.",
        "minutos_pausados": 0,
        "pausada_em": None,
        "area_estourou_em": None,
        "reincidencia": 0,
        "reaberta_em": None,
        "relato_integral": RELATO,
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "natureza_informada": None,
        # Os marcos dos jobs de prazo e da escada de escalonamento. Preenchidos
        # de propósito, mesmo que um caso real não passe por todos de uma vez:
        # campo nulo antes e depois fica igual sendo apagado ou não, e a
        # afirmação de preservação ficaria sem dentes.
        "critico_avisado_em": "2026-08-15T13:00:00+00:00",
        "vespera_avisada_em": "2026-08-19T11:00:00+00:00",
        "escalonado_gestor_em": "2026-08-22T11:00:00+00:00",
        "escalonado_diretoria_em": "2026-08-23T11:00:00+00:00",
        "escalonamento_impossivel_em": "2026-08-24T11:00:00+00:00",
        "registrado_por": "P10",
        "acuse_recebimento_em": None,
        "acuse_sem_contato_em": None,
        "encerramento_avisado_em": None,
        "encerramento_sem_contato_em": None,
        "vista_pela_ouvidoria_em": None,
        "arquivada_em": None,
        "arquivada_por": None,
        "anonimizada_em": None,
        # Os três campos do pedido (migration 100). NULL é o normal: é assim
        # que todo caso existente entra nas colunas novas.
        "apagamento_pedido_em": None,
        "apagamento_pedido_por": None,
        "apagamento_motivo": None,
    }
    row.update(overrides)
    return row


def _movimento_de_resposta(numero: int = 7) -> dict:
    return {
        "id": "mov-resposta",
        "manifestacao_id": f"uuid-{numero}",
        "ocorrido_em": "2026-09-01T13:00:00+00:00",
        "estado_anterior": "aguardando_area",
        "estado_novo": "respondido",
        "autor_id": None,
        "autor_nome": "Carlos Titular",
        "observacao": RESPOSTA_DA_AREA,
    }


def _tentativa(numero: int = 7) -> dict:
    return {
        "id": "tent-1",
        "manifestacao_id": f"uuid-{numero}",
        "canal": "telefone",
        "tentada_em": "2026-08-20T13:00:00+00:00",
        "observacao": "Liguei para 11 99999-0000 e falei com Joana.",
    }


def _prorrogacao(numero: int = 7) -> dict:
    return {
        "id": "prorr-1",
        "manifestacao_id": f"uuid-{numero}",
        "dias": 3,
        "status": "aprovada",
        "justificativa": "Precisamos ouvir a equipe que atendeu Joana.",
        "decisao_justificativa": "Aprovado pelo caso de Joana.",
    }


def _notificacao(numero: int = 7) -> dict:
    return {
        "id": "notif-1",
        "manifestacao_id": f"uuid-{numero}",
        "gatilho": "encerramento",
        "status": "entregue",
        "papel_destinatario": "manifestante",
        "destinatario_nome": "Joana da Silva",
        "destinatario_email": "joana@exemplo.com",
        "detalhe": "Desfecho enviado a Joana da Silva.",
    }


def _anexo(numero: int = 7) -> dict:
    return {
        "id": "anexo-1",
        "manifestacao_id": f"uuid-{numero}",
        "storage_path": "2026/anexo-1.jpg",
        "filename": "foto.jpg",
        "content_type": "image/jpeg",
        "tamanho_bytes": 10,
        "enviado_por_nome": "Marta Ouvidora",
    }


class _StorageFake:
    """O Storage relata o resultado arquivo a arquivo no corpo, sem levantar
    exceção: é assim que `storage.delete_file` sabe se o binário saiu mesmo."""

    def __init__(self):
        self.arquivos: set[str] = set()
        self.removidos: list[str] = []

    def from_(self, _bucket: str):
        return self

    def remove(self, paths: list[str]):
        corpo = []
        for p in paths:
            if p not in self.arquivos:
                continue
            self.arquivos.discard(p)
            self.removidos.append(p)
            corpo.append({"name": p})
        return corpo


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta só as colunas
    pedidas, os filtros casam de verdade (igualdade, nulo e negação) e o insert
    devolve a linha com o id que o banco geraria.

    Registra no dono cada escrita PROPOSTA, na ordem e com o payload: é só por
    aí que se prova a ordem das operações, porque o estado final do banco é o
    mesmo em qualquer ordem."""

    def __init__(self, nome: str, rows: list[dict], dono: _SupabaseFake):
        self.nome = nome
        self.rows = rows
        self.dono = dono
        self.request = SimpleNamespace(params=httpx.QueryParams())
        self._filtros: list = []
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._delete = False
        self._colunas: tuple[str, ...] | None = None
        self._negar = False
        self._limite: int | None = None
        self._janela: tuple[int, int] | None = None

    @property
    def not_(self):
        self._negar = True
        return self

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict, count: str | None = None, **_kw):
        self._update = payload
        return self

    def delete(self):
        self._delete = True
        return self

    def _guardar(self, teste):
        negado = self._negar
        self._negar = False
        self._filtros.append((lambda row: not teste(row)) if negado else teste)
        return self

    def eq(self, col, value):
        return self._guardar(lambda row: row.get(col) == value)

    def neq(self, col, value):
        return self._guardar(lambda row: row.get(col) != value)

    def in_(self, col, values):
        return self._guardar(lambda row: row.get(col) in list(values))

    def is_(self, col, value):
        alvo = None if value in ("null", None) else value
        return self._guardar(lambda row: row.get(col) == alvo)

    def gte(self, col, value):
        return self._guardar(lambda row: str(row.get(col) or "") >= str(value))

    def lte(self, col, value):
        return self._guardar(lambda row: row.get(col) is not None and str(row.get(col)) <= str(value))

    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: str(r.get(col) or ""), reverse=desc)
        return self

    def limit(self, n):
        self._limite = n
        return self

    def range(self, inicio: int, fim: int):
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self._insert is not None:
            self.dono.registrar(self.nome, "insert", self._insert)
            self.dono.quebrar_se_pedido(self.nome, "insert")
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = []
            for n in novos:
                linha = dict(n)
                linha.setdefault("id", f"{self.nome}-{len(self.rows) + 1}")
                self.rows.append(linha)
                gravados.append(dict(linha))
            return type("R", (), {"data": gravados, "count": None})()

        if self._update is not None:
            self.dono.registrar(self.nome, "update", self._update)
            self.dono.quebrar_se_pedido(self.nome, "update")
        if self._delete:
            self.dono.registrar(self.nome, "delete", None)
            self.dono.quebrar_se_pedido(self.nome, "delete")

        casadas = [r for r in self.rows if all(teste(r) for teste in self._filtros)]
        if self._limite is not None:
            casadas = casadas[: self._limite]
        if self._janela is not None and self._update is None and not self._delete:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        if self._update is not None:
            for r in casadas:
                r.update(self._update)
            recorte = self.request.params.get("select")
            colunas = tuple(c.strip() for c in recorte.split(",")) if recorte else None
            gravadas = [{c: r.get(c) for c in colunas} if colunas else dict(r) for r in casadas]
            return type("R", (), {"data": gravadas, "count": None})()
        if self._delete:
            apagadas = [dict(r) for r in casadas]
            for r in casadas:
                self.rows.remove(r)
            return type("R", (), {"data": apagadas, "count": None})()
        return type("R", (), {"data": [self._projetar(r) for r in casadas], "count": None})()


class _SupabaseFake:
    def __init__(self, casos: list[dict] | None = None, **filhas):
        self.storage = _StorageFake()
        # (tabela, operação, payload) de toda escrita proposta, na ordem.
        self.escritas: list[tuple[str, str, dict | None]] = []
        self.quebrar: set[tuple[str, str]] = set()
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [_caso()],
            "ouvidoria_movimentos": filhas.get("movimentos") or [],
            "ouvidoria_tentativas_contato": filhas.get("tentativas") or [],
            "ouvidoria_prorrogacoes": filhas.get("prorrogacoes") or [],
            "ouvidoria_notificacoes": filhas.get("notificacoes") or [],
            "ouvidoria_anexos": filhas.get("anexos") or [],
            "ouvidoria_acessos": [],
            "ouvidoria_feriados": [],
            "ouvidoria_prazos": [],
            "participantes": [],
            "setores": [],
        }
        for anexo in self.tabelas["ouvidoria_anexos"]:
            if anexo.get("storage_path"):
                self.storage.arquivos.add(anexo["storage_path"])

    def table(self, nome: str):
        return _TabelaFake(nome, self.tabelas.setdefault(nome, []), self)

    def rpc(self, nome: str, params: dict | None = None):
        raise AssertionError(f"Apagar não passa por RPC nenhuma, e esta chegou: {nome}")

    def registrar(self, tabela: str, operacao: str, payload) -> None:
        self.escritas.append((tabela, operacao, payload if isinstance(payload, dict) else None))

    def quebrar_se_pedido(self, tabela: str, operacao: str) -> None:
        if (tabela, operacao) in self.quebrar:
            raise RuntimeError(f"{operacao} recusado em {tabela} (simulado)")

    def caso(self, numero: int = 7) -> dict:
        return next(c for c in self.tabelas["ouvidoria_protocolos"] if c["id"] == f"uuid-{numero}")

    def movimentos(self, numero: int = 7) -> list[dict]:
        return [m for m in self.tabelas["ouvidoria_movimentos"] if m["manifestacao_id"] == f"uuid-{numero}"]


def _caso_com_todos_os_registros(**overrides) -> _SupabaseFake:
    """O caso com registro em TODAS as tabelas que a política varre. Sem isso,
    um teste de varredura passaria pela porta errada: o passo que não rodou não
    teria o que apagar de qualquer jeito."""
    return _SupabaseFake(
        casos=[_caso(**overrides)],
        movimentos=[_movimento_de_resposta()],
        tentativas=[_tentativa()],
        prorrogacoes=[_prorrogacao()],
        notificacoes=[_notificacao()],
        anexos=[_anexo()],
    )


def _client(monkeypatch, supabase: _SupabaseFake | None = None, participante: dict | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()
    quem = participante if participante is not None else DIRETORIA

    async def _fake_participante(_user, _sb, fields=None):
        return quem

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: INICIO)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _apagar(client, numero: int = 7, motivo: str | None = MOTIVO):
    corpo = {} if motivo is None else {"motivo": motivo}
    return client.post(f"/api/ouvidoria/manifestacoes/uuid-{numero}/apagamento", json=corpo)


def _todo_o_texto(supabase: _SupabaseFake) -> str:
    partes = []
    for linhas in supabase.tabelas.values():
        for linha in linhas:
            partes.extend(str(v) for v in linha.values())
    return " ".join(partes)


def _movimento_do_apagamento(supabase: _SupabaseFake, numero: int = 7) -> dict:
    marcados = [
        m
        for m in supabase.movimentos(numero)
        if str(m.get("observacao") or "").startswith(ouvidoria_retencao.MARCA_DO_APAGAMENTO)
    ]
    assert len(marcados) == 1, f"esperava um movimento de apagamento, achei {len(marcados)}"
    return marcados[0]


class TestQuemApaga:
    """Só a Diretoria apaga (ADR 0047, decisão 3). Os três testes usam o MESMO
    caso e o MESMO corpo: o que muda entre eles é só quem está logado."""

    def test_diretoria_apaga(self, monkeypatch):
        client, _ = _client(monkeypatch, participante=DIRETORIA)

        assert _apagar(client).status_code == 200

    def test_ouvidor_recebe_403_e_o_caso_fica_inteiro(self, monkeypatch):
        client, supabase = _client(monkeypatch, participante=OUVIDOR)

        r = _apagar(client)

        assert r.status_code == 403, r.text
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.caso()["anonimizada_em"] is None
        assert supabase.escritas == []

    def test_super_admin_recebe_403_e_o_caso_fica_inteiro(self, monkeypatch):
        client, supabase = _client(monkeypatch, participante=SUPER_ADMIN)

        r = _apagar(client)

        assert r.status_code == 403, r.text
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.escritas == []


class TestPreCondicoes:
    """Quem pode apagar ainda precisa de um caso apagável: encerrado, com o
    marco do encerramento, e com motivo escrito."""

    @pytest.mark.parametrize("status", ["em_classificacao", "aguardando_area", "aguardando_manifestante", "respondido"])
    def test_caso_em_andamento_recebe_409(self, monkeypatch, status):
        supabase = _SupabaseFake(casos=[_caso(status=status)])
        client, _ = _client(monkeypatch, supabase)

        r = _apagar(client)

        assert r.status_code == 409, r.text
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.caso()["apagamento_pedido_em"] is None
        assert supabase.escritas == []

    def test_caso_encerrado_sem_o_marco_do_encerramento_recebe_409(self, monkeypatch):
        """O import histórico do NocoDB nasceu `encerrado` sem `encerrada_em`.
        Sem o marco não há como afirmar quando o caso fechou, e é o marco que a
        guarda do banco confere: apagar aqui deixaria a trilha barrada no meio
        da varredura."""
        supabase = _SupabaseFake(casos=[_caso(encerrada_em=None)])
        client, _ = _client(monkeypatch, supabase)

        r = _apagar(client)

        assert r.status_code == 409, r.text
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.escritas == []

    @pytest.mark.parametrize("motivo", ["", "   ", None])
    def test_motivo_vazio_ou_ausente_recebe_422(self, monkeypatch, motivo):
        supabase = _SupabaseFake()
        client, _ = _client(monkeypatch, supabase)

        r = _apagar(client, motivo=motivo)

        assert r.status_code == 422, r.text
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.escritas == []

    def test_caso_inexistente_recebe_404(self, monkeypatch):
        client, _ = _client(monkeypatch)

        assert _apagar(client, numero=99).status_code == 404


class TestOAtoDeApagar:
    def test_grava_quem_pediu_quando_e_por_que(self, monkeypatch):
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        caso = supabase.caso()
        assert caso["apagamento_pedido_por"] == DIRETORIA["id"]
        assert caso["apagamento_pedido_em"] == INICIO.isoformat()
        assert caso["apagamento_motivo"] == MOTIVO

    def test_o_caso_apagado_entra_no_arquivo_sozinho(self, monkeypatch):
        """ADR 0047, decisão 4: caso apagado sai da lista sem ninguém arquivar."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        assert supabase.caso()["arquivada_em"], "o caso apagado precisa entrar no arquivo"
        assert supabase.caso()["arquivada_por"] == DIRETORIA["id"]

    def test_o_movimento_leva_o_nome_de_quem_apagou_e_o_motivo(self, monkeypatch):
        """O ato entra na trilha, e é a única coisa que sobra para explicar o
        buraco: o nome sai da assinatura e o motivo do texto."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        movimento = _movimento_do_apagamento(supabase)
        assert movimento["autor_nome"] == DIRETORIA["nome_completo"]
        assert movimento["autor_id"] == DIRETORIA["id"]
        assert MOTIVO in movimento["observacao"]
        # O fato continua imutável: apagar não move o caso de estado.
        assert movimento["estado_anterior"] == "encerrado"
        assert movimento["estado_novo"] == "encerrado"
        assert supabase.caso()["status"] == "encerrado"

    def test_varre_os_cinco_lugares_onde_o_relato_mora(self, monkeypatch):
        """A manifestação, os anexos (com o binário), a `observacao` da trilha,
        as tentativas e prorrogações, e o `detalhe` das notificações."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        caso = supabase.caso()
        assert caso["relato_integral"] is None
        assert caso["manifestante_nome"] is None
        assert caso["manifestante_contato"] is None
        assert supabase.tabelas["ouvidoria_anexos"] == []
        assert supabase.storage.arquivos == set()
        assert next(m for m in supabase.movimentos() if m["id"] == "mov-resposta")["observacao"] is None
        assert supabase.tabelas["ouvidoria_tentativas_contato"][0]["observacao"] is None
        assert supabase.tabelas["ouvidoria_prorrogacoes"][0]["decisao_justificativa"] is None
        assert supabase.tabelas["ouvidoria_notificacoes"][0]["detalhe"] is None
        # E, olhando de fora: nenhum rastro de quem manifestou em tabela nenhuma.
        tudo = _todo_o_texto(supabase)
        assert "Joana" not in tudo
        assert "99999-0000" not in tudo

    def test_o_carimbo_do_apagamento_vem_por_ultimo(self, monkeypatch):
        """A ordem que sobrevive a uma falha no meio: o movimento da trilha
        primeiro, o carimbo `anonimizada_em` por último, e tudo o que destrói
        entre os dois. Provada pela sequência de escritas propostas, porque o
        banco termina igual em qualquer ordem."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        movimento = next(
            i
            for i, (tabela, op, _p) in enumerate(supabase.escritas)
            if tabela == "ouvidoria_movimentos" and op == "insert"
        )
        carimbo = next(
            i
            for i, (tabela, op, payload) in enumerate(supabase.escritas)
            if tabela == "ouvidoria_protocolos" and op == "update" and (payload or {}).get("anonimizada_em")
        )
        destrutivos = [
            i
            for i, (tabela, op, _p) in enumerate(supabase.escritas)
            if (tabela, op)
            in {
                ("ouvidoria_movimentos", "update"),
                ("ouvidoria_tentativas_contato", "update"),
                ("ouvidoria_prorrogacoes", "update"),
                ("ouvidoria_notificacoes", "update"),
                ("ouvidoria_anexos", "delete"),
            }
        ]
        assert destrutivos, "o teste ficaria vazio sem nenhum passo destrutivo entre os dois"
        assert movimento < min(destrutivos)
        assert carimbo > max(destrutivos)

    def test_a_resposta_devolve_o_dossie_apagado(self, monkeypatch):
        """A tela adota o corpo que a rota devolve. Devolver o caso de antes
        deixaria o relato na tela depois de ele já ter saído do banco."""
        client, _ = _client(monkeypatch, _caso_com_todos_os_registros())

        corpo = _apagar(client).json()

        assert corpo["anonimizada_em"]
        assert corpo["relato_integral"] is None
        assert corpo["apagamento_motivo"] == MOTIVO
        assert corpo["apagamento_pedido_por"] == DIRETORIA["id"]
        assert corpo["apagamento_pedido_em"] == INICIO.isoformat()

    def test_o_ato_entra_no_log_de_acesso(self, monkeypatch):
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        assert _apagar(client).status_code == 200
        assert [linha["acao"] for linha in supabase.tabelas["ouvidoria_acessos"]] == ["apagar"]


class TestOQueSobrevive:
    def test_os_tres_campos_do_pedido_sobrevivem_a_anonimizacao(self, monkeypatch):
        """Eles são o registro do ato, e ficam junto do protocolo e da trilha:
        apagados junto com o Dossiê, o caso apagado não saberia dizer quem
        mandou apagar nem por quê."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        r = _apagar(client)

        assert r.status_code == 200, r.text
        caso = supabase.caso()
        # O Dossiê saiu (senão a afirmação de sobrevivência não teria dentes).
        assert caso["relato_integral"] is None
        assert caso["anonimizada_em"]
        assert caso["apagamento_motivo"] == MOTIVO
        assert caso["apagamento_pedido_por"] == DIRETORIA["id"]
        assert caso["apagamento_pedido_em"] == INICIO.isoformat()

    def test_os_campos_estatisticos_ficam_iguais(self, monkeypatch):
        """Métricas e relatórios contam o caso apagado igual a antes."""
        supabase = _caso_com_todos_os_registros()
        antes = dict(supabase.caso())
        client, _ = _client(monkeypatch, supabase)

        r = _apagar(client)

        assert r.status_code == 200, r.text
        depois = supabase.caso()
        for campo in ouvidoria_retencao.CAMPOS_ESTATISTICOS:
            assert campo in antes, f"a fixture não cobre o campo estatístico {campo}"
            if campo in GRAVADOS_PELO_PROPRIO_ATO:
                # Estes cinco o ato ESCREVE (o pedido e o arquivo), e a
                # afirmação sobre eles é a de baixo: eles nascem aqui, e é a
                # anonimização que não pode apagá-los depois.
                assert antes[campo] is None and depois[campo] is not None, f"{campo} não foi gravado pelo ato"
                continue
            assert depois[campo] == antes[campo], f"o apagamento mexeu em {campo}"

    def test_a_politica_declara_por_escrito_que_o_pedido_fica(self):
        """As duas listas da retenção são o contrato do que sai e do que fica, e
        é por elas que uma coluna nova precisa de decisão consciente. Os três
        campos do pedido têm que estar do lado certo: a lista não muda o que o
        código faz hoje, e é justamente por isso que ela some sem barulho."""
        for campo in ("apagamento_pedido_em", "apagamento_pedido_por", "apagamento_motivo"):
            assert campo in ouvidoria_retencao.CAMPOS_ESTATISTICOS, f"{campo} sumiu da lista do que fica"
            assert campo not in ouvidoria_retencao.CAMPOS_DO_DOSSIE, f"{campo} entrou na lista do que sai"

    def test_o_movimento_do_apagamento_guarda_a_observacao(self, monkeypatch):
        """A limpeza da trilha preserva este movimento, como já faz com o da
        Retenção: sem ele o motivo escrito pela Diretoria morreria junto com o
        Dossiê que ele explica."""
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        assert _apagar(client).status_code == 200
        assert MOTIVO in _movimento_do_apagamento(supabase)["observacao"]


class TestSegundaChamada:
    def test_segunda_chamada_devolve_sucesso_e_nao_grava_segundo_movimento(self, monkeypatch):
        client, supabase = _client(monkeypatch, _caso_com_todos_os_registros())

        primeira = _apagar(client)
        pedido_em = supabase.caso()["apagamento_pedido_em"]
        segunda = _apagar(client, motivo="Outro motivo qualquer.")

        assert primeira.status_code == 200, primeira.text
        assert segunda.status_code == 200, segunda.text
        # Um movimento de apagamento, e um só (o helper falha se houver dois).
        _movimento_do_apagamento(supabase)
        # E o pedido gravado continua sendo o primeiro: o ato não se reescreve.
        assert supabase.caso()["apagamento_pedido_em"] == pedido_em
        assert supabase.caso()["apagamento_motivo"] == MOTIVO

    def test_a_retomada_termina_o_servico_depois_de_uma_falha_no_meio(self, monkeypatch):
        """A falha deixa o pedido gravado e o Dossiê em pé. A chamada seguinte
        reaproveita o movimento e conclui: sem isso, o caso ficaria com o
        pedido registrado e o relato vivo, para sempre."""
        supabase = _caso_com_todos_os_registros()
        # A falha entra no primeiro passo destrutivo depois do movimento, que é
        # retomável por natureza: nada foi destruído ainda. (O anexo é o único
        # passo cuja falha no meio pede humano, e o motivo está no
        # `_apagar_anexos`.)
        supabase.quebrar.add(("ouvidoria_tentativas_contato", "update"))
        client, _ = _client(monkeypatch, supabase)

        primeira = _apagar(client)

        # O que a falha deixou para trás: o pedido gravado, o Dossiê em pé.
        assert primeira.status_code == 503, primeira.text
        assert supabase.caso()["anonimizada_em"] is None
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.caso()["apagamento_pedido_em"] == INICIO.isoformat()

        supabase.quebrar.clear()
        # A segunda chamada chega com OUTRO motivo de propósito: o ato que vale
        # é o primeiro, e regravar o pedido trocaria a data e o motivo que a
        # trilha já registrou por outros, sem deixar rastro da troca.
        segunda = _apagar(client, motivo="Outro motivo, digitado na segunda tentativa.")

        assert segunda.status_code == 200, segunda.text
        assert supabase.caso()["relato_integral"] is None
        assert supabase.caso()["anonimizada_em"]
        assert supabase.caso()["apagamento_pedido_em"] == INICIO.isoformat()
        assert supabase.caso()["apagamento_motivo"] == MOTIVO
        _movimento_do_apagamento(supabase)


class TestCasoJaApagado:
    def test_caso_apagado_pelos_cinco_anos_devolve_sucesso_sem_refazer_nada(self, monkeypatch):
        """O carimbo já existe: refazer a varredura não muda nada e o segundo
        movimento mentiria sobre um ato que não aconteceu."""
        supabase = _SupabaseFake(casos=[_caso(anonimizada_em="2026-09-01T10:00:00+00:00", relato_integral=None)])
        client, _ = _client(monkeypatch, supabase)

        r = _apagar(client)

        assert r.status_code == 200, r.text
        assert supabase.escritas == []
        assert supabase.movimentos() == []
        # E o pedido não é gravado: quem apagou foi a política dos cinco anos.
        assert supabase.caso()["apagamento_motivo"] is None


class TestOCronNaoMuda:
    """A porta antecipada e o cron chamam a MESMA entrada. O cron assina com o
    autor de sistema e não escreve motivo nenhum."""

    def test_o_cron_apaga_com_autor_de_sistema_e_sem_motivo(self):
        seis_anos_atras = "2020-08-26T12:00:00+00:00"
        agora = dt.datetime(2026, 8, 26, 12, 0, tzinfo=dt.UTC)
        supabase = _SupabaseFake(
            casos=[_caso(encerrada_em=seis_anos_atras)],
            movimentos=[_movimento_de_resposta()],
        )

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, agora)

        assert anonimizadas == 1
        movimento = _movimento_do_apagamento(supabase)
        assert movimento["autor_nome"] == ouvidoria_retencao.AUTOR_DA_RETENCAO
        assert movimento["autor_id"] is None
        assert supabase.caso()["relato_integral"] is None
        assert supabase.caso()["anonimizada_em"]
        # Os três campos do pedido continuam vazios: ninguém pediu, o prazo venceu.
        assert supabase.caso()["apagamento_pedido_em"] is None
        assert supabase.caso()["apagamento_pedido_por"] is None
        assert supabase.caso()["apagamento_motivo"] is None

    def test_o_cron_nao_alcanca_o_caso_encerrado_ontem(self):
        """A porta antecipada é a única que apaga dentro dos cinco anos. Sem
        este par, o teste acima ficaria verde com o prazo apagado do código."""
        supabase = _SupabaseFake(casos=[_caso()])

        anonimizadas = ouvidoria_retencao.anonimizar_encerradas_antigas(supabase, INICIO)

        assert anonimizadas == 0
        assert supabase.caso()["relato_integral"] == RELATO
        assert supabase.escritas == []


class TestACreditoNaTrilha:
    """O aviso de caso apagado credita quem apagou, e o nome só existe na
    trilha. A régua tem que reconhecer as DUAS portas: com a Diretoria
    assinando com nome de pessoa, a marca por autor de sistema perderia o
    autor (aviso da fatia #593)."""

    def test_o_movimento_da_diretoria_e_marcado_como_apagamento(self):
        eventos = ouvidoria_trilha.linha_do_tempo(
            [
                {
                    "ocorrido_em": "2026-09-08T17:00:00+00:00",
                    "estado_anterior": "encerrado",
                    "estado_novo": "encerrado",
                    "autor_id": "P11",
                    "autor_nome": "Dr. Diretor",
                    "observacao": ouvidoria_retencao.observacao_do_apagamento(motivo=MOTIVO),
                }
            ],
            frozenset(),
        )

        assert [e["apagamento"] for e in eventos] == [True]
        assert eventos[0]["autor"] == "Dr. Diretor"

    def test_o_movimento_da_retencao_continua_marcado_como_apagamento(self):
        eventos = ouvidoria_trilha.linha_do_tempo(
            [
                {
                    "ocorrido_em": "2031-09-01T12:00:00+00:00",
                    "estado_anterior": "encerrado",
                    "estado_novo": "encerrado",
                    "autor_id": None,
                    "autor_nome": ouvidoria_retencao.AUTOR_DA_RETENCAO,
                    "observacao": ouvidoria_retencao.observacao_do_apagamento(motivo=None),
                }
            ],
            frozenset(),
        )

        assert [e["apagamento"] for e in eventos] == [True]
        assert eventos[0]["autor"] == ouvidoria_retencao.AUTOR_DA_RETENCAO

    def test_movimento_que_nao_apagou_nada_nao_e_marcado(self):
        """O par `encerrado` para `encerrado` também serve a atos de job que não
        apagaram nada: sem este par, marcar todo movimento sem transição
        passaria pelos dois testes acima."""
        eventos = ouvidoria_trilha.linha_do_tempo(
            [
                {
                    "ocorrido_em": "2026-09-08T17:00:00+00:00",
                    "estado_anterior": "encerrado",
                    "estado_novo": "encerrado",
                    "autor_id": None,
                    "autor_nome": "Sistema (prazos)",
                    "observacao": "Lembrete enviado ao setor.",
                }
            ],
            frozenset(),
        )

        assert [e["apagamento"] for e in eventos] == [False]


class TestMigration:
    """A 100 dá ao caso os três campos do pedido e a segunda chave da guarda de
    UPDATE da trilha. A guarda de DELETE não muda."""

    @pytest.fixture
    def ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "100_ouvidoria_apagamento_pela_diretoria.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    @pytest.fixture
    def comandos(self, ddl) -> str:
        """Só o SQL, sem os comentários: afirmar o que a migration NÃO faz
        exige olhar os comandos, e não a prosa que explica o porquê."""
        return "\n".join(linha for linha in ddl.splitlines() if not linha.strip().startswith("--"))

    def test_o_caso_ganha_os_tres_campos_do_pedido(self, ddl):
        for coluna in ("apagamento_pedido_em", "apagamento_pedido_por", "apagamento_motivo"):
            assert f"add column if not exists {coluna}" in ddl

    def test_migration_e_idempotente(self, ddl):
        assert "add column if not exists" in ddl
        assert "create or replace function" in ddl

    def test_a_guarda_de_update_ganha_a_segunda_chave(self, comandos):
        """A chave nova é o pedido gravado, e ela entra ao LADO dos cinco anos,
        não no lugar deles: o cron continua passando pela mesma porta."""
        assert "ouvidoria_movimento_anonimizavel" in comandos
        assert "interval '5 years'" in comandos
        assert "p.apagamento_pedido_em is not null" in comandos
        assert " or " in comandos, "as duas chaves precisam conviver"

    def test_a_guarda_continua_exigindo_caso_encerrado(self, comandos):
        """A segunda chave não afrouxa o resto: o gatilho continua conferindo
        na própria linha do caso que ele está encerrado e tem o marco."""
        assert "p.status = 'encerrado'" in comandos
        assert "p.encerrada_em is not null" in comandos

    def test_a_guarda_de_delete_fica_intocada(self, comandos):
        """Só a função de UPDATE é substituída. DELETE continua barrado sem
        exceção nenhuma, e o log de acesso não é tocado."""
        assert "before delete" not in comandos
        assert "ouvidoria_acessos" not in comandos
        assert "ouvidoria_movimento_imutavel" not in comandos

    def test_o_comentario_da_funcao_e_atualizado(self, ddl):
        assert "comment on function ouvidoria_movimento_anonimizavel" in ddl

    def test_nenhuma_tabela_nova_nasce_aqui(self, comandos):
        """Tabela nova exigiria RLS default-deny. Esta migration só acrescenta
        colunas, então não há policy a criar."""
        assert "create table" not in comandos
