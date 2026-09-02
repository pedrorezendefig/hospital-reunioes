"""Visto global da Ouvidoria e marcador de novidade na fila (issue #484, PRD #470).

O caso ganha um carimbo só, `vista_pela_ouvidoria_em`: não é "o Pedro viu", é
"a Ouvidoria viu" (decisão de grilling). Quem carimba é a abertura do Dossiê
por quem tem o Perfil da Ouvidoria, nas duas portas do Dossiê (pelo id e pelo
protocolo).

Novidade é derivada, e não guardada: o caso tem novidade quando a última
movimentação da trilha é mais recente que o carimbo, ou quando o carimbo é
nulo (RN-66). Caso que já existia nasce com o carimbo nulo, logo com novidade:
é o comportamento certo, porque ninguém pode afirmar que a Ouvidoria os viu.

O que estes testes protegem, e que passar despercebido custaria caro:

* a fila não pode devolver o carimbo em si para quem está fora da Ouvidoria
  (nem para quem está dentro: é dado de controle, não de caso);
* a trilha não pode ser lida para quem não tem o Perfil da Ouvidoria: a flag
  não significa nada para a secretária, e a leitura seria puro custo;
* a trilha fora do ar não pode derrubar a fila inteira: sem novidade é uma
  degradação aceitável, fila em branco não é.
"""

from __future__ import annotations

import datetime as dt
import os
import sys

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
from app.services import paginacao  # noqa: E402

OUVIDOR = {"id": "P10", "nome_completo": "Marta Ouvidora", "access_profile": None, "perfil_ouvidoria": "ouvidor"}
DIRETORIA = {
    "id": "P11",
    "nome_completo": "Dr. Diretor",
    "access_profile": "regular",
    "perfil_ouvidoria": "diretoria_executiva",
}
SECRETARIA = {"id": "P02", "nome_completo": "Sofia Secretaria", "access_profile": "secretaria"}
SUPER_ADMIN = {"id": "P03", "nome_completo": "Pedro Admin", "access_profile": "super_admin"}

AGORA = dt.datetime(2026, 9, 2, 14, 0, tzinfo=dt.UTC)
ONTEM = "2026-09-01T09:00:00+00:00"
HOJE_CEDO = "2026-09-02T08:00:00+00:00"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


def _caso(numero: int = 7, **overrides) -> dict:
    row = {
        "id": f"uuid-{numero}",
        "numero": numero,
        "protocolo": f"2026-{numero:04d}",
        "data_abertura": "2026-08-14",
        "prazo_resposta": "2026-08-21",
        "status": "aguardando_area",
        "tipo_manifestacao": "reclamacao",
        "sigilo_reforcado": False,
        "categoria": "Demora",
        "setor": "Recepcao",
        "resumo": "Paciente relata espera acima de duas horas na recepcao.",
        "conversa_id": "conv-1",
        "gravidade": None,
        "prazo_area_em": None,
        "respondida_em": None,
        "minutos_pausados": 0,
        "desfecho": None,
        "pausada_em": None,
        "area_estourou_em": None,
        "relato_integral": "Cheguei as 8h e so fui atendida as 10h30.",
        "manifestante_nome": "Joana da Silva",
        "manifestante_contato": "(31) 99999-0000",
        "manifestante_vinculo": "acompanhante",
        "anonimo": False,
        "dados_incompletos": False,
        "classificacao_ia": None,
        "natureza_informada": None,
        "desfecho_descricao": None,
        "canal": "ana",
        "canal_setor": None,
        "canal_ponto": None,
        "contato_em": None,
        "prazo_rompido_em": None,
        "validada_em": None,
        "validada_por": None,
        "resposta_da_area": None,
        "respondida_por_nome": None,
        "encerrada_em": None,
        "reincidencia": 0,
        "reaberta_em": None,
        "prazo_conclusivo_em": None,
        # O carimbo do visto: nulo é o normal para caso que ninguém abriu.
        "vista_pela_ouvidoria_em": None,
    }
    row.update(overrides)
    return row


class _TabelaFake:
    """Fake do PostgREST fiel no que importa: o select projeta as colunas
    pedidas, o filtro casa por igualdade e o update escreve na linha casada."""

    def __init__(
        self,
        nome: str,
        rows: list[dict],
        consultas: list,
        falhas: set[str],
        teto_de_linhas: int | None = None,
        ordens: list | None = None,
        ignora_recorte: bool = False,
    ):
        self.nome = nome
        # O servidor (ou um proxy no caminho) que descarta o `range`: toda
        # página volta igual e cheia, e o laço da paginação só para no teto de
        # voltas. O resultado sai incompleto com HTTP 200, que é a mesma mudez
        # do teto de linhas.
        self.ignora_recorte = ignora_recorte
        self.rows = rows
        self.consultas = consultas
        self.falhas = falhas
        self.ordens = ordens if ordens is not None else []
        # O mesmo `PGRST_DB_MAX_ROWS` que o fake da função de agregação já
        # simula: ele corta TODA resposta do servidor, e a tabela não é
        # exceção. Sem isso, uma leitura sem `range` na tabela passaria ilesa
        # pelo teste de paginação.
        self.teto_de_linhas = teto_de_linhas
        self._filters: dict = {}
        self._insert: dict | list | None = None
        self._update: dict | None = None
        self._colunas: tuple[str, ...] | None = None
        self._janela: tuple[int, int] | None = None
        self._ordem: tuple[str, bool] | None = None

    def select(self, colunas: str = "*", *_a, **_kw):
        if colunas.strip() != "*":
            self._colunas = tuple(c.strip() for c in colunas.split(","))
        return self

    def insert(self, payload):
        self._insert = payload
        return self

    def update(self, payload: dict):
        self._update = payload
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def order(self, col, desc=False):
        self._ordem = (col, desc)
        self.ordens.append(col)
        return self

    def limit(self, _quantas):
        return self

    def range(self, inicio: int, fim: int):
        if self.ignora_recorte:
            return self
        self._janela = (inicio, fim)
        return self

    def _projetar(self, row: dict) -> dict:
        if self._colunas is None:
            return dict(row)
        return {c: row.get(c) for c in self._colunas}

    def execute(self):
        if self.nome in self.falhas:
            raise httpx.ReadTimeout(f"o PostgREST nao respondeu por {self.nome}")
        if self._insert is not None:
            novos = self._insert if isinstance(self._insert, list) else [self._insert]
            gravados = [dict(n) for n in novos]
            self.rows.extend(gravados)
            return type("R", (), {"data": gravados})()
        casadas = [r for r in self.rows if all(r.get(c) == v for c, v in self._filters.items())]
        if self._update is not None:
            if f"{self.nome}_update" in self.falhas:
                raise httpx.ReadTimeout(f"o PostgREST nao respondeu ao update de {self.nome}")
            self.consultas.append((self.nome, "update", dict(self._filters), dict(self._update)))
            for r in casadas:
                r.update(self._update)
            return type("R", (), {"data": [dict(r) for r in casadas]})()
        self.consultas.append((self.nome, "select", dict(self._filters)))
        if self._ordem is not None:
            col, desc = self._ordem
            casadas = sorted(casadas, key=lambda r: r.get(col), reverse=desc)
        if self._janela is not None:
            inicio, fim = self._janela
            casadas = casadas[inicio : fim + 1]
        if self.teto_de_linhas is not None:
            casadas = casadas[: self.teto_de_linhas]
        return type("R", (), {"data": [self._projetar(r) for r in casadas]})()


class _RpcFake:
    """A função de agregação da trilha, servida como o PostgREST serve: em
    páginas, e só depois de a rota pedir uma ordem.

    O teto de linhas é o `PGRST_DB_MAX_ROWS`, e ele corta TODA resposta, com
    HTTP 200 e sem aviso nenhum: é essa mudez que faz a leitura de uma vez só
    perder metade da fila sem ninguém notar, e é por isso que a rota lê em
    páginas. O fake recorta de verdade para o laço de paginação ter fim."""

    def __init__(
        self,
        nome: str,
        linhas: list[dict],
        chamadas: list,
        falhas: set[str],
        teto_de_linhas: int | None = None,
        ordens: list | None = None,
        ignora_recorte: bool = False,
    ):
        self.nome = nome
        self.ignora_recorte = ignora_recorte
        self.linhas = linhas
        self.chamadas = chamadas
        self.falhas = falhas
        self.teto_de_linhas = teto_de_linhas
        self.ordens = ordens if ordens is not None else []
        self._ordenado = False
        self._janela: tuple[int, int] | None = None

    def order(self, coluna: str, *_a, **_kw):
        self.ordens.append(coluna)
        self._ordenado = True
        return self

    def range(self, inicio: int, fim: int):
        if self.ignora_recorte:
            return self
        self._janela = (inicio, fim)
        return self

    def execute(self):
        if self.nome in self.falhas:
            raise httpx.ReadTimeout(f"o PostgREST nao respondeu pela funcao {self.nome}")
        self.chamadas.append(self.nome)
        # Sem ordem, a janela de uma página pode repetir ou pular linha. O fake
        # recusa em vez de fingir estabilidade que o banco não daria.
        assert self._ordenado, "leitura em páginas sem ORDER BY: o recorte não seria estável"
        linhas = sorted(self.linhas, key=lambda linha: linha["manifestacao_id"])
        # A ordem das duas etapas é a do servidor, e é ela que dá sentido ao
        # teste: o recorte pedido acontece primeiro, e o teto corta o que sair
        # DEPOIS dele. Um fake que só aplicasse o teto dentro do `if` da janela
        # mediria a si mesmo: a leitura sem paginação nenhuma passaria ilesa,
        # justamente o caminho que o teste existe para reprovar.
        if self._janela is not None:
            inicio, fim = self._janela
            linhas = linhas[inicio : fim + 1]
        if self.teto_de_linhas is not None:
            linhas = linhas[: self.teto_de_linhas]
        return type("R", (), {"data": [dict(linha) for linha in linhas]})()


class _SupabaseFake:
    def __init__(
        self,
        casos: list[dict] | None = None,
        ultimos_movimentos: list[dict] | None = None,
        teto_de_linhas: int | None = None,
        recorte_ignorado: set[str] | None = None,
    ):
        # Os nomes das leituras em que o servidor descarta o `range`.
        self.recorte_ignorado = recorte_ignorado if recorte_ignorado is not None else set()
        self.tabelas: dict[str, list[dict]] = {
            "ouvidoria_protocolos": casos if casos is not None else [],
            "ouvidoria_acessos": [],
            "ouvidoria_feriados": [],
        }
        # O que a função de agregação da trilha devolve: um par por caso.
        self.ultimos_movimentos = ultimos_movimentos if ultimos_movimentos is not None else []
        # O `PGRST_DB_MAX_ROWS` do servidor, quando o teste quer provar que a
        # leitura em páginas sobrevive a ele.
        self.teto_de_linhas = teto_de_linhas
        self.consultas: list = []
        self.chamadas_rpc: list[str] = []
        self.ordens_pedidas: list[str] = []
        # A ordem pedida nas leituras de TABELA, guardada pelo mesmo motivo da
        # ordem do agregado: página sem ORDER BY repete ou pula linha, e num
        # contador a linha repetida vira caso contado duas vezes.
        self.ordens_de_tabela: list[str] = []
        self.falhas: set[str] = set()

    def table(self, nome: str):
        return _TabelaFake(
            nome,
            self.tabelas.setdefault(nome, []),
            self.consultas,
            self.falhas,
            self.teto_de_linhas,
            self.ordens_de_tabela,
            nome in self.recorte_ignorado,
        )

    def rpc(self, nome: str, _params: dict | None = None):
        return _RpcFake(
            nome,
            self.ultimos_movimentos,
            self.chamadas_rpc,
            self.falhas,
            self.teto_de_linhas,
            self.ordens_pedidas,
            nome in self.recorte_ignorado,
        )


_SESSAO: dict = {"participante": None}


def _client(monkeypatch, participante: dict | None, supabase: _SupabaseFake | None = None):
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(ouvidoria_router.router, prefix="/api")

    supabase = supabase if supabase is not None else _SupabaseFake()
    _SESSAO["participante"] = participante

    async def _fake_participante(_user, _sb, fields=None):
        return _SESSAO["participante"]

    monkeypatch.setattr(ouvidoria_router, "get_participante_for_user", _fake_participante)
    monkeypatch.setattr(ouvidoria_router, "agora_utc", lambda: AGORA)
    app.dependency_overrides[get_current_user] = lambda: {"id": "u1", "email": "u@hsm.br"}
    app.dependency_overrides[get_supabase_client] = lambda: supabase
    return TestClient(app), supabase


def _movimento(caso_id: str, quando: str) -> dict:
    return {"manifestacao_id": caso_id, "ultimo_movimento_em": quando}


def _corpo_da_fila(client) -> dict:
    r = client.get("/api/ouvidoria/protocolos")
    assert r.status_code == 200, r.text
    return r.json()


def _fila(client) -> list[dict]:
    return _corpo_da_fila(client)["protocolos"]


class TestNovidadeNaFila:
    """A flag que acende o ponto na linha (RN-66, RN-68)."""

    def test_carimbo_nulo_e_novidade(self, monkeypatch):
        """Caso que a Ouvidoria nunca abriu tem novidade, com trilha ou sem
        ela. É o estado em que todo caso já existente entra na migration."""
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is True

    def test_carimbo_nulo_sem_nenhum_movimento_ainda_e_novidade(self, monkeypatch):
        supabase = _SupabaseFake([_caso()], [])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is True

    def test_movimento_mais_novo_que_o_carimbo_e_novidade(self, monkeypatch):
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", HOJE_CEDO)],
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is True

    def test_carimbo_mais_novo_que_o_movimento_nao_e_novidade(self, monkeypatch):
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=HOJE_CEDO)],
            [_movimento("uuid-7", ONTEM)],
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is False

    def test_carimbo_no_mesmo_instante_do_movimento_nao_e_novidade(self, monkeypatch):
        """O empate é do lado de "já vi": quem abriu o caso no mesmo segundo do
        movimento leu o movimento. Do outro lado, o ponto nunca apagaria."""
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", ONTEM)],
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is False

    def test_caso_visto_sem_nenhum_movimento_na_trilha_nao_e_novidade(self, monkeypatch):
        supabase = _SupabaseFake([_caso(vista_pela_ouvidoria_em=ONTEM)], [])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is False

    def test_cada_caso_le_a_propria_trilha(self, monkeypatch):
        """O agregado chega em bloco, e casar o par errado marcaria o caso
        errado. Dois casos, dois destinos opostos, uma leitura só."""
        supabase = _SupabaseFake(
            [
                _caso(numero=7, vista_pela_ouvidoria_em=HOJE_CEDO),
                _caso(numero=8, vista_pela_ouvidoria_em=ONTEM),
            ],
            [_movimento("uuid-7", ONTEM), _movimento("uuid-8", HOJE_CEDO)],
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        por_id = {p["id"]: p["tem_novidade"] for p in _fila(client)}
        assert por_id == {"uuid-7": False, "uuid-8": True}

    def test_a_diretoria_executiva_tambem_recebe_a_flag(self, monkeypatch):
        supabase = _SupabaseFake([_caso()], [])
        client, _ = _client(monkeypatch, DIRETORIA, supabase)

        assert _fila(client)[0]["tem_novidade"] is True

    def test_o_carimbo_nao_vai_no_corpo_da_resposta(self, monkeypatch):
        """O visto é dado de controle da fila, não do caso: a tela precisa da
        flag, e nunca da hora em que a Ouvidoria abriu o caso."""
        supabase = _SupabaseFake([_caso(vista_pela_ouvidoria_em=ONTEM)], [])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert "vista_pela_ouvidoria_em" not in _fila(client)[0]


class TestNovidadeForaDaOuvidoria:
    """A flag só significa alguma coisa para quem tem o Perfil da Ouvidoria."""

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN])
    def test_quem_esta_fora_recebe_a_flag_desligada(self, monkeypatch, papel):
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", HOJE_CEDO)])
        client, _ = _client(monkeypatch, papel, supabase)

        assert _fila(client)[0]["tem_novidade"] is False

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN])
    def test_a_trilha_nem_e_consultada_para_quem_esta_fora(self, monkeypatch, papel):
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", HOJE_CEDO)])
        client, _ = _client(monkeypatch, papel, supabase)

        _fila(client)

        assert supabase.chamadas_rpc == []


class TestTrilhaForaDoAr:
    def test_falha_ao_ler_a_trilha_nao_derruba_a_fila(self, monkeypatch):
        """Sem novidade é degradação; fila em branco é o ouvidor sem trabalho.
        `httpx.ReadTimeout` porque timeout do PostgREST sobe cru, sem virar
        `APIError` (precedente do módulo)."""
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", HOJE_CEDO)],
        )
        supabase.falhas.add("ouvidoria_ultimo_movimento")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        protocolos = _fila(client)

        assert len(protocolos) == 1
        assert protocolos[0]["tem_novidade"] is False

    def test_a_trilha_que_nao_pode_ser_lida_chega_declarada_na_resposta(self, monkeypatch):
        """O achado que a review pegou: fila sem ponto nenhum desenha a mesma
        tela de uma fila sem novidade, e o ouvidor leria "nada mexeu" quando a
        verdade é "não consegui olhar". A falha viaja NOMEADA, no mesmo
        `degradado` que o calendário já usa (issue #449)."""
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", HOJE_CEDO)],
        )
        supabase.falhas.add("ouvidoria_ultimo_movimento")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _corpo_da_fila(client)["degradado"] == ["movimentos"]

    def test_trilha_lida_nao_declara_degradacao_nenhuma(self, monkeypatch):
        """A contraprova: `degradado` que acusasse sempre viraria ruído, e a
        tela aprenderia a ignorá-lo."""
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _corpo_da_fila(client)["degradado"] == []

    def test_quem_esta_fora_da_ouvidoria_nao_degrada_pela_trilha(self, monkeypatch):
        """A secretária não lê a trilha, então não pode acusar a queda dela: o
        aviso falaria de um marcador que a tela dela nem mostra."""
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", HOJE_CEDO)])
        supabase.falhas.add("ouvidoria_ultimo_movimento")
        client, _ = _client(monkeypatch, SECRETARIA, supabase)

        assert _corpo_da_fila(client)["degradado"] == []

    def test_o_caso_nunca_visto_segue_marcado_com_a_trilha_fora_do_ar(self, monkeypatch):
        """O carimbo nulo decide sozinho: o caso que ninguém da Ouvidoria abriu
        não depende da trilha para acender o ponto."""
        supabase = _SupabaseFake([_caso()], [])
        supabase.falhas.add("ouvidoria_ultimo_movimento")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is True


class TestLeituraEmPaginas:
    """O outro achado da review: a agregação da trilha lida de uma vez só é
    cortada em silêncio pelo `PGRST_DB_MAX_ROWS`, e o ponto some da parte da
    fila que ficou de fora, com HTTP 200 e nada na tela. A listagem ao lado já
    lê em páginas exatamente por isso (issue #430)."""

    def test_teto_de_linhas_do_servidor_nao_apaga_o_ponto_do_fim_da_fila(self, monkeypatch):
        casos = [_caso(numero=n, vista_pela_ouvidoria_em=ONTEM) for n in range(1, 8)]
        movimentos = [_movimento(f"uuid-{n}", HOJE_CEDO) for n in range(1, 8)]
        # O servidor devolve no máximo 2 linhas por ida, e não avisa que cortou.
        supabase = _SupabaseFake(casos, movimentos, teto_de_linhas=2)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        marcados = [p["protocolo"] for p in _fila(client) if p["tem_novidade"]]

        assert len(marcados) == 7, "o agregado saiu cortado no teto e parte da fila perdeu o ponto"

    def test_a_leitura_do_agregado_pede_ordem_estavel(self, monkeypatch):
        """Página sem ordem repete ou pula linha entre uma ida e outra. A chave
        do agregado é única por construção, então é ela que ordena."""
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        _fila(client)

        # Uma ida por página, e TODAS pela mesma chave: a ordem que muda no
        # meio da paginação é tão instável quanto a ausência dela.
        assert supabase.ordens_pedidas
        assert set(supabase.ordens_pedidas) == {"manifestacao_id"}


class TestCarimboDoVisto:
    """Abrir o Dossiê é o ato que apaga o ponto (RN-66)."""

    def test_abrir_pelo_protocolo_carimba_o_visto(self, monkeypatch):
        supabase = _SupabaseFake([_caso()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vista_pela_ouvidoria_em"] == AGORA.isoformat()

    def test_abrir_pelo_id_carimba_o_visto(self, monkeypatch):
        supabase = _SupabaseFake([_caso()])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.get("/api/ouvidoria/manifestacoes/uuid-7")

        assert r.status_code == 200, r.text
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vista_pela_ouvidoria_em"] == AGORA.isoformat()

    def test_o_carimbo_e_do_caso_aberto_e_nao_da_fila_toda(self, monkeypatch):
        supabase = _SupabaseFake([_caso(numero=7), _caso(numero=8)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        vistos = {c["numero"]: c["vista_pela_ouvidoria_em"] for c in supabase.tabelas["ouvidoria_protocolos"]}
        assert vistos == {7: AGORA.isoformat(), 8: None}

    def test_a_diretoria_executiva_tambem_carimba(self, monkeypatch):
        supabase = _SupabaseFake([_caso()])
        client, _ = _client(monkeypatch, DIRETORIA, supabase)

        client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert supabase.tabelas["ouvidoria_protocolos"][0]["vista_pela_ouvidoria_em"] == AGORA.isoformat()

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN, None])
    def test_quem_nao_tem_perfil_da_ouvidoria_nao_carimba(self, monkeypatch, papel):
        """A porta já recusa, e é ela que impede o carimbo. O teste existe para
        provar que a recusa acontece ANTES da escrita: um gate mais frouxo aqui
        apagaria o ponto do ouvidor sem que ninguém da Ouvidoria tivesse lido
        nada."""
        supabase = _SupabaseFake([_caso()])
        client, _ = _client(monkeypatch, papel, supabase)

        r = client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert r.status_code == 403
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vista_pela_ouvidoria_em"] is None

    def test_falha_ao_carimbar_nao_derruba_o_dossie(self, monkeypatch):
        """Mesma escolha do log de acesso: perder o carimbo custa um ponto que
        não apaga; perder o Dossiê é o ouvidor sem o caso na tela."""
        supabase = _SupabaseFake([_caso()])
        supabase.falhas.add("ouvidoria_protocolos_update")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        r = client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert r.status_code == 200, r.text
        assert r.json()["protocolo"] == "2026-0007"
        assert supabase.tabelas["ouvidoria_protocolos"][0]["vista_pela_ouvidoria_em"] is None


class TestCicloDoPonto:
    """O ciclo inteiro, que é o que o ouvidor vê: acende, apaga, reacende."""

    def test_abrir_o_caso_apaga_o_ponto_e_movimento_novo_reacende(self, monkeypatch):
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _fila(client)[0]["tem_novidade"] is True

        client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")
        assert _fila(client)[0]["tem_novidade"] is False

        # A área responde depois da leitura: a trilha ganha um movimento mais
        # novo que o carimbo, e o ponto volta sem ninguém mexer em coluna.
        supabase.ultimos_movimentos = [_movimento("uuid-7", "2026-09-02T18:00:00+00:00")]
        assert _fila(client)[0]["tem_novidade"] is True


def _contador(client):
    r = client.get("/api/ouvidoria/novidades")
    assert r.status_code == 200, r.text
    return r.json()


class TestContadorDeNovidades:
    """O total que vira distintivo no menu lateral e na barra inferior
    (issue #487, RN-69).

    O contador não pode inventar uma segunda definição de novidade: se a régua
    dele divergir da régua do ponto na linha, o menu anuncia um número que a
    fila não consegue explicar, e quem abrir a Ouvidoria procurando os casos
    novos não acha. Por isso o contador conta com a MESMA função e sobre o
    MESMO universo da fila, e há um teste aqui só para amarrar um número ao
    outro."""

    def test_conta_so_os_casos_com_novidade(self, monkeypatch):
        casos = [
            # Nunca visto: novidade.
            _caso(numero=1),
            # Visto ontem, movimento hoje: novidade.
            _caso(numero=2, vista_pela_ouvidoria_em=ONTEM),
            # Visto hoje, movimento de ontem: sem novidade.
            _caso(numero=3, vista_pela_ouvidoria_em="2026-09-02T12:00:00+00:00"),
        ]
        movimentos = [_movimento("uuid-2", HOJE_CEDO), _movimento("uuid-3", ONTEM)]
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(casos, movimentos))

        assert _contador(client)["total"] == 2

    def test_sem_novidade_nenhuma_o_total_e_zero(self, monkeypatch):
        """Zero é um número, e é o que faz o distintivo sumir da tela."""
        casos = [_caso(numero=1, vista_pela_ouvidoria_em="2026-09-02T12:00:00+00:00")]
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(casos, [_movimento("uuid-1", ONTEM)]))

        assert _contador(client)["total"] == 0

    def test_o_total_bate_com_a_flag_da_fila(self, monkeypatch):
        """A amarra entre as duas telas. Régua duplicada sai de sincronia no
        primeiro ajuste, e o menu passa a prometer um número que a fila não
        mostra."""
        casos = [
            _caso(numero=1),
            _caso(numero=2, vista_pela_ouvidoria_em=ONTEM),
            _caso(numero=3, vista_pela_ouvidoria_em="2026-09-02T12:00:00+00:00"),
            _caso(numero=4, vista_pela_ouvidoria_em=ONTEM),
        ]
        movimentos = [
            _movimento("uuid-2", HOJE_CEDO),
            _movimento("uuid-3", ONTEM),
            _movimento("uuid-4", ONTEM),
        ]
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(casos, movimentos))

        marcados = [p for p in _fila(client) if p["tem_novidade"]]

        assert _contador(client)["total"] == len(marcados)

    def test_abrir_o_caso_reduz_o_total(self, monkeypatch):
        """O critério do diretor: o número cai quando os casos são abertos."""
        casos = [_caso(numero=1), _caso(numero=7)]
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake(casos, []))

        assert _contador(client)["total"] == 2

        client.get("/api/ouvidoria/manifestacoes/por-protocolo/2026-0007")

        assert _contador(client)["total"] == 1

    def test_a_diretoria_executiva_tambem_recebe_o_total(self, monkeypatch):
        client, _ = _client(monkeypatch, DIRETORIA, _SupabaseFake([_caso()], []))

        assert _contador(client)["total"] == 1

    @pytest.mark.parametrize("papel", [SECRETARIA, SUPER_ADMIN], ids=["secretaria", "super_admin"])
    def test_quem_esta_fora_da_ouvidoria_nao_recebe_o_numero(self, monkeypatch, papel):
        """O distintivo diz "a Ouvidoria ainda não viu", o que não significa
        nada fora dela, e o total contaria para a secretária os casos
        sigilosos que a fila dela nem lista."""
        client, _ = _client(monkeypatch, papel, _SupabaseFake([_caso()], []))

        assert client.get("/api/ouvidoria/novidades").status_code == 403

    def test_sem_participante_o_contador_e_negado(self, monkeypatch):
        client, _ = _client(monkeypatch, None, _SupabaseFake([_caso()], []))

        assert client.get("/api/ouvidoria/novidades").status_code == 403


class TestContadorForaDoAr:
    """Contador que não carregou não é zero. São coisas diferentes na tela, e
    confundi-las é o pior erro possível nesta fatia: o menu diria "nada novo"
    justamente quando não conseguiu olhar."""

    def test_falha_na_trilha_nao_vira_zero(self, monkeypatch):
        supabase = _SupabaseFake([_caso(vista_pela_ouvidoria_em=ONTEM)], [_movimento("uuid-7", HOJE_CEDO)])
        supabase.falhas.add("ouvidoria_ultimo_movimento")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _contador(client)

        assert corpo["total"] is None
        assert corpo["degradado"] == ["movimentos"]

    def test_falha_ao_ler_os_casos_nao_vira_zero(self, monkeypatch):
        supabase = _SupabaseFake([_caso()], [])
        supabase.falhas.add("ouvidoria_protocolos")
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _contador(client)

        assert corpo["total"] is None
        assert corpo["degradado"] == ["casos"]

    def test_leitura_inteira_nao_declara_degradacao_nenhuma(self, monkeypatch):
        """A contraprova: aviso que aparece sempre vira ruído, e a tela aprende
        a ignorá-lo."""
        client, _ = _client(monkeypatch, OUVIDOR, _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)]))

        assert _contador(client)["degradado"] == []


class TestContadorEmPaginas:
    """O teto de linhas do PostgREST corta com HTTP 200 e sem aviso. Num
    contador esse corte é invisível: o número sai menor e continua com cara de
    contado."""

    def test_teto_de_linhas_nao_encolhe_o_total(self, monkeypatch):
        casos = [_caso(numero=n) for n in range(1, 8)]
        supabase = _SupabaseFake(casos, [], teto_de_linhas=2)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _contador(client)["total"] == 7, "a leitura dos casos saiu cortada no teto e o total mentiu"

    def test_teto_de_linhas_no_agregado_nao_apaga_novidade_do_total(self, monkeypatch):
        casos = [_caso(numero=n, vista_pela_ouvidoria_em=ONTEM) for n in range(1, 8)]
        movimentos = [_movimento(f"uuid-{n}", HOJE_CEDO) for n in range(1, 8)]
        supabase = _SupabaseFake(casos, movimentos, teto_de_linhas=2)
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _contador(client)["total"] == 7, "o agregado da trilha saiu cortado e o total mentiu"

    def test_a_leitura_dos_casos_pede_ordem_estavel(self, monkeypatch):
        """Página sem ordem repete ou pula linha entre uma ida e outra ao
        banco, e um caso repetido contaria duas vezes."""
        supabase = _SupabaseFake([_caso()], [])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        _contador(client)

        assert supabase.ordens_de_tabela, "a leitura dos casos foi ao banco sem ORDER BY"
        assert set(supabase.ordens_de_tabela) == {"numero"}


class TestContadorNoTetoDeLinhas:
    """O outro corte silencioso, e o que escapou na primeira rodada: quando o
    servidor descarta o `range`, o laço da paginação desiste no teto de LINHAS
    e devolve o que juntou até ali.

    O corte de linhas do `PGRST_DB_MAX_ROWS` a paginação resolve; o teto de
    segurança ela não resolve, só limita. O resultado é o mesmo defeito de sempre:
    um total menor, com cara de contado. Zero e "não sei" já eram coisas
    diferentes nesta rota, e leitura incompleta é o mesmo "não sei"."""

    def test_teto_de_linhas_nos_casos_nao_devolve_um_total_menor(self, monkeypatch):
        monkeypatch.setattr(paginacao, "MAX_LINHAS", 3)
        supabase = _SupabaseFake([_caso()], [], recorte_ignorado={"ouvidoria_protocolos"})
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _contador(client)

        assert corpo["total"] is None, "a leitura parou no teto de linhas e o total saiu como verdade"
        assert corpo["degradado"] == ["casos"]

    def test_teto_de_linhas_na_trilha_nao_devolve_um_total_menor(self, monkeypatch):
        monkeypatch.setattr(paginacao, "MAX_LINHAS", 3)
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", HOJE_CEDO)],
            recorte_ignorado={"ouvidoria_ultimo_movimento"},
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _contador(client)

        assert corpo["total"] is None
        assert corpo["degradado"] == ["movimentos"]

    def test_a_fila_tambem_declara_a_trilha_incompleta(self, monkeypatch):
        """O mesmo estouro do lado da fila: sem a declaração, os casos que
        ficaram de fora do agregado perdem o ponto e a lista diz "nada mexeu"
        para eles."""
        monkeypatch.setattr(paginacao, "MAX_LINHAS", 3)
        supabase = _SupabaseFake(
            [_caso(vista_pela_ouvidoria_em=ONTEM)],
            [_movimento("uuid-7", HOJE_CEDO)],
            recorte_ignorado={"ouvidoria_ultimo_movimento"},
        )
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        assert _corpo_da_fila(client)["degradado"] == ["movimentos"]

    def test_leitura_que_termina_sozinha_nao_declara_nada(self, monkeypatch):
        """A contraprova, para o aviso não virar ruído permanente."""
        monkeypatch.setattr(paginacao, "MAX_LINHAS", 3)
        supabase = _SupabaseFake([_caso()], [_movimento("uuid-7", ONTEM)])
        client, _ = _client(monkeypatch, OUVIDOR, supabase)

        corpo = _contador(client)

        assert corpo["total"] == 1
        assert corpo["degradado"] == []
