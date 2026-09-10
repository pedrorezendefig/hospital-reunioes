"""O Vinculo da Demanda com a issue do GitHub (issue #674, PRD #673, ADR 0054).

Tres seams, na ordem em que a regra existe:

* **A tabela de Etapas**, funcao pura, testada direto e sem HTTP. As seis
  saidas e a PRECEDENCIA entre elas sao escritas aqui a mao, a partir da issue;
  o caso que separa cada regra da seguinte tem o seu proprio teste, porque e na
  sobreposicao que a tabela erra (issue fechada com o `in-progress` preso e
  Entregue, e nao "em desenvolvimento para sempre").
* **O marcador**, tambem puro: ele e o lado da issue do par, e a idempotencia
  dele e criterio de aceite.
* **As duas portas**, pela ROTA de verdade, com o Supabase e o cliente do
  GitHub dublados. E o unico jeito de provar o gate do `github_login` (que nao
  e o gate de papel), a omissao do numero para quem nao e da Vitta, e as linhas
  automaticas que entram no fio depois da escrita.

O cliente do GitHub NUNCA e chamado de verdade: a fixture `_sem_github_de_verdade`
troca o transporte por um que estoura, e a trava de rede do `conftest.py`
continua por baixo. As duas de proposito: a fixture aponta o arquivo culpado, a
trava derruba a sessao se a fixture algum dia sumir.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from slowapi import _rate_limit_exceeded_handler  # noqa: E402
from slowapi.errors import RateLimitExceeded  # noqa: E402

from app.config import settings  # noqa: E402
from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
from app.services import github_client, tecnologia_email  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPA_REGISTRADA,
    ETAPA_ROTULO,
    ETAPAS,
    MOTIVO_INTEGRACAO_DESLIGADA,
    MOTIVO_LOGIN_INVALIDO,
    MOTIVO_SEM_GITHUB_LOGIN,
    MOTIVO_SEM_VINCULO_PARA_DESFAZER,
    TEXTO_VINCULO_CRIADO,
    TEXTO_VINCULO_DESFEITO,
    corpo_com_marcador,
    corpo_precisa_do_marcador,
    demanda_id_do_marcador,
    etapa_da_foto,
    foto_mudou,
    marcador_da_demanda,
    motivo_demanda_ja_vinculada,
    motivo_e_pull_request,
    motivo_github_login_invalido,
    motivo_github_login_repetido,
    motivo_issue_inexistente,
    motivo_numero_ja_usado,
    normalizar_github_login,
    partes_da_foto,
    tem_github_login,
    texto_movimento_etapa,
    texto_partes,
)

BASE = "/api/admin/tecnologia"

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "103_tecnologia_vinculo.sql"


# ─── Fixtures de seguranca ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi guarda a contagem num storage de PROCESSO: sem o reset, o 429
    de um arquivo anterior quebraria um teste daqui que nada tem com o teto."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_github_de_verdade(monkeypatch):
    """Nenhum teste deste arquivo fala com api.github.com.

    A troca e no TRANSPORTE (`httpx.request` dentro do modulo do cliente), e nao
    nas funcoes do cliente: assim ela vale mesmo nos testes que NAO dublam
    `ler_issue`, e uma rota nova que chamasse o GitHub por um caminho que
    ninguem dublou estoura aqui, com o nome do arquivo, em vez de sair para a
    rede.
    """

    def _proibido(*a, **kw):
        raise AssertionError("O cliente do GitHub foi chamado de verdade neste teste. Duble-o.")

    monkeypatch.setattr(github_client.httpx, "request", _proibido)


@pytest.fixture(autouse=True)
def _sem_email_de_verdade(monkeypatch):
    """Responder na Conversa dispara os gatilhos de e-mail (issue #642).

    Um teste daqui responde no fio para provar que a omissao do numero morde SO
    a linha do Vinculo, e o pytest carrega o `.env` REAL, com usuario e senha de
    SMTP do Gmail. Sem esta troca, esse teste abriria conexao para fora, e a
    trava de rede do `conftest.py` derrubaria a sessao (foi o que ela fez).

    O transporte devolve `True` porque nenhum teste daqui e sobre e-mail: quem
    prova gatilho e destinatario e o `test_tecnologia_email.py`.
    """
    monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: True)
    monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: True)


@pytest.fixture(autouse=True)
def _integracao_configurada(monkeypatch):
    """As duas variaveis de pe, como estarao no Coolify.

    O `.env` local nao as tem, e sem isto TODA rota do Vinculo responderia 503 e
    os testes de 422 ficariam verdes pelo motivo errado. Quem prova o 503 e o
    teste que APAGA a variavel, e nao a ausencia dela por acidente.
    """
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


# ─── 1. A tabela de Etapas ───────────────────────────────────────────────────


def _foto(
    *,
    numero: int = 673,
    estado: str = "open",
    motivo: str | None = None,
    labels: tuple[str, ...] = (),
    partes: tuple[dict, ...] = (),
    resumo: dict | None = None,
) -> dict[str, Any]:
    foto = {
        "numero": numero,
        "titulo": "PRD de teste",
        "url": f"https://github.com/pedrorezendefig/hospital-reunioes/issues/{numero}",
        "estado": estado,
        "motivo_do_fechamento": motivo,
        "labels": list(labels),
        "partes": list(partes),
    }
    if resumo is not None:
        foto["resumo_das_partes"] = resumo
    return foto


def _parte(numero: int, *, estado: str = "open", motivo: str | None = None, labels: tuple[str, ...] = ()) -> dict:
    return {
        "numero": numero,
        "titulo": "Fatia",
        "url": f"https://github.com/pedrorezendefig/hospital-reunioes/issues/{numero}",
        "estado": estado,
        "motivo_do_fechamento": motivo,
        "labels": list(labels),
    }


# Cada linha da tabela da issue, escrita a mao a partir dela. O nome do caso e a
# frase da issue; o dado e a foto que a produz.
LINHAS_DA_TABELA = [
    ("sem vinculo nao ha o que derivar", None, ETAPA_REGISTRADA),
    ("aberta sem label e sem partes", _foto(), ETAPA_EM_ANALISE),
    ("needs-triage", _foto(labels=("needs-triage",)), ETAPA_EM_ANALISE),
    ("needs-info", _foto(labels=("needs-info",)), ETAPA_EM_ANALISE),
    ("ready-for-agent", _foto(labels=("ready-for-agent",)), ETAPA_PLANEJADA),
    ("ready-for-human", _foto(labels=("ready-for-human",)), ETAPA_PLANEJADA),
    (
        "PRD com partes e nenhuma em andamento",
        _foto(partes=(_parte(674), _parte(675))),
        ETAPA_PLANEJADA,
    ),
    ("in-progress na raiz", _foto(labels=("in-progress",)), ETAPA_EM_DESENVOLVIMENTO),
    (
        "PRD com uma parte in-progress",
        _foto(partes=(_parte(674, labels=("in-progress",)), _parte(675))),
        ETAPA_EM_DESENVOLVIMENTO,
    ),
    ("fechada como concluida", _foto(estado="closed", motivo="completed"), ETAPA_ENTREGUE),
    ("fechada sem motivo declarado", _foto(estado="closed", motivo=None), ETAPA_ENTREGUE),
    ("fechada como nao planejada", _foto(estado="closed", motivo="not_planned"), ETAPA_NAO_SERA_FEITA),
    ("wontfix", _foto(labels=("wontfix",)), ETAPA_NAO_SERA_FEITA),
]


class TestTabelaDeEtapas:
    def test_o_piso_da_tabela(self):
        """Controle da lista abaixo: `parametrize` sobre lista vazia satisfaz o
        teste sem rodar caso nenhum, e ele ficaria verde sobre nada."""
        assert len(ETAPAS) == 6
        assert len(LINHAS_DA_TABELA) == 13
        assert {saida for _, _, saida in LINHAS_DA_TABELA} == set(ETAPAS)

    @pytest.mark.parametrize("caso,foto,esperada", LINHAS_DA_TABELA, ids=lambda v: v if isinstance(v, str) else "")
    def test_cada_linha_da_tabela(self, caso, foto, esperada):
        assert etapa_da_foto(foto) == esperada

    def test_a_migration_conhece_as_mesmas_seis(self):
        """As duas pontas amarradas: o CHECK da migration 103 e a tupla do
        servico. Uma Etapa nova no Python que nao entrasse no CHECK viraria erro
        de banco na hora de gravar, em producao, e nao aqui."""
        sql = MIGRATION.read_text(encoding="utf-8")
        for etapa in ETAPAS:
            assert f"'{etapa}'" in sql, f"a migration nao conhece a Etapa {etapa}"

    def test_cada_etapa_tem_rotulo_de_gente(self):
        assert set(ETAPA_ROTULO) == set(ETAPAS)
        assert all(ETAPA_ROTULO[e].strip() for e in ETAPAS)


class TestPrecedenciaEntreAsRegras:
    """Onde as regras se sobrepoem, que e onde a tabela erra."""

    def test_fechada_com_in_progress_presa_e_entregue(self):
        """O caso comum: ninguem tira a label ao fechar. Sem a precedencia, o
        PRD entregue ficaria "em desenvolvimento" para sempre."""
        foto = _foto(estado="closed", motivo="completed", labels=("in-progress",))
        assert etapa_da_foto(foto) == ETAPA_ENTREGUE

    def test_fechada_como_concluida_com_parte_em_andamento_e_entregue(self):
        foto = _foto(
            estado="closed",
            motivo="completed",
            partes=(_parte(674, labels=("in-progress",)),),
        )
        assert etapa_da_foto(foto) == ETAPA_ENTREGUE

    def test_fechada_sem_motivo_e_entrega_e_nao_recusa(self):
        """O GitHub devolve `state_reason: null` em varios caminhos de
        fechamento. Exigir `completed` faria o diretor ler "Não será feita"
        sobre algo entregue, que e a pior mentira que este selo pode contar."""
        assert etapa_da_foto(_foto(estado="closed", motivo=None)) == ETAPA_ENTREGUE
        assert etapa_da_foto(_foto(estado="closed", motivo="")) == ETAPA_ENTREGUE

    def test_fechada_sem_motivo_com_wontfix_ainda_e_nao_sera_feita(self):
        """A label e uma declaracao explicita, e ganha do fechamento mudo."""
        assert etapa_da_foto(_foto(estado="closed", motivo=None, labels=("wontfix",))) == ETAPA_ENTREGUE

    def test_nao_planejada_ganha_de_in_progress(self):
        foto = _foto(estado="closed", motivo="not_planned", labels=("in-progress",))
        assert etapa_da_foto(foto) == ETAPA_NAO_SERA_FEITA

    def test_in_progress_numa_parte_ganha_de_ready_for_agent_na_raiz(self):
        """O PRD continua com a label da fila enquanto a primeira fatia anda: o
        que vale para o diretor e que ALGUEM esta com a mao nisso."""
        foto = _foto(
            labels=("ready-for-agent",),
            partes=(_parte(674, labels=("in-progress",)), _parte(675, labels=("ready-for-agent",))),
        )
        assert etapa_da_foto(foto) == ETAPA_EM_DESENVOLVIMENTO

    def test_partes_todas_entregues_com_a_raiz_aberta_ainda_e_planejada(self):
        """A raiz aberta nao e entrega: Entregue e o fechamento DELA (ADR 0054,
        decisao 3). Sem isto, o app prometeria entrega antes do merge do ultimo
        PR."""
        foto = _foto(partes=(_parte(674, estado="closed", motivo="completed"),))
        assert etapa_da_foto(foto) == ETAPA_PLANEJADA

    def test_label_desconhecida_nao_muda_nada(self):
        assert etapa_da_foto(_foto(labels=("area:backend", "fatia:G"))) == ETAPA_EM_ANALISE

    def test_a_label_e_lida_sem_distinguir_maiusculas(self):
        assert etapa_da_foto(_foto(labels=("In-Progress",))) == ETAPA_EM_DESENVOLVIMENTO


class TestResumoDasPartes:
    def test_sem_sub_issues_os_dois_vem_nulos(self):
        """Nulo, e nao zero: "0 de 0 partes" e uma barra vazia onde nao ha
        barra, e o card precisa distinguir issue simples de PRD sem entrega."""
        assert partes_da_foto(_foto()) == (None, None)

    def test_sem_foto_os_dois_vem_nulos(self):
        assert partes_da_foto(None) == (None, None)

    def test_o_resumo_do_github_manda_quando_veio(self):
        foto = _foto(partes=(_parte(674),), resumo={"total": 7, "entregues": 3})
        assert partes_da_foto(foto) == (3, 7)

    def test_sem_resumo_a_conta_sai_da_lista_de_partes(self):
        foto = _foto(
            partes=(
                _parte(674, estado="closed", motivo="completed"),
                _parte(675, estado="closed", motivo="not_planned"),
                _parte(676),
            )
        )
        assert partes_da_foto(foto) == (1, 3)

    def test_parte_fechada_sem_motivo_conta_como_entregue(self):
        """ "Entregue" nao pode significar duas coisas no mesmo modulo: a raiz e
        as partes passam pela mesma regra (`_entregue`)."""
        foto = _foto(partes=(_parte(674, estado="closed", motivo=None), _parte(675)))
        assert partes_da_foto(foto) == (1, 2)

    def test_resumo_com_total_zero_conta_como_sem_partes(self):
        assert partes_da_foto(_foto(resumo={"total": 0, "entregues": 0})) == (None, None)


class TestTextoDasPartes:
    def test_o_texto_das_partes(self):
        assert texto_partes(3, 7) == "3 de 7 partes"

    @pytest.mark.parametrize("entregues,total", ((None, None), (3, None), (None, 7), (0, 0)))
    def test_sem_partes_o_texto_e_vazio(self, entregues, total):
        assert texto_partes(entregues, total) == ""


# ─── 2. O marcador oculto ────────────────────────────────────────────────────

CORPO_ORIGINAL = "## Para o diretor\n\nO selo passa a aparecer no card.\n\n## O que construir\n\nA espinha do Vínculo."


class TestMarcador:
    def test_entra_no_fim_sem_alterar_o_resto(self):
        novo = corpo_com_marcador(CORPO_ORIGINAL, "d-1")

        assert novo.startswith(CORPO_ORIGINAL)
        assert novo.endswith(marcador_da_demanda("d-1"))

    def test_marcar_de_novo_nao_duplica(self):
        """Criterio de aceite: vincular de novo o mesmo numero nao duplica o
        marcador. Provado pela CONTAGEM, e nao por `!= o dobro`: uma remocao que
        deixasse dois marcadores diferentes passaria por uma comparacao frouxa.
        """
        uma_vez = corpo_com_marcador(CORPO_ORIGINAL, "d-1")
        duas_vezes = corpo_com_marcador(uma_vez, "d-1")

        assert duas_vezes == uma_vez
        assert duas_vezes.count("demanda-vitta") == 1

    def test_marcador_de_outra_demanda_e_substituido_e_nao_somado(self):
        """A issue que sobrou marcada de uma Demanda desvinculada nao vira dona
        de duas: o marcador antigo sai antes de o novo entrar."""
        antigo = corpo_com_marcador(CORPO_ORIGINAL, "d-1")
        novo = corpo_com_marcador(antigo, "d-2")

        assert novo.count("demanda-vitta") == 1
        assert demanda_id_do_marcador(novo) == "d-2"

    def test_o_id_volta_do_corpo(self):
        assert demanda_id_do_marcador(corpo_com_marcador(CORPO_ORIGINAL, "d-42")) == "d-42"

    def test_corpo_sem_marcador_nao_tem_id(self):
        assert demanda_id_do_marcador(CORPO_ORIGINAL) is None
        assert demanda_id_do_marcador(None) is None

    def test_corpo_vazio_fica_so_com_o_marcador(self):
        """Issue sem corpo existe. Sem esta saida, o corpo comecaria com duas
        quebras de linha antes do marcador."""
        assert corpo_com_marcador(None, "d-1") == marcador_da_demanda("d-1")
        assert corpo_com_marcador("", "d-1") == marcador_da_demanda("d-1")

    def test_quem_ja_esta_marcado_nao_precisa_de_escrita(self):
        marcado = corpo_com_marcador(CORPO_ORIGINAL, "d-1")

        assert corpo_precisa_do_marcador(marcado, "d-1") is False
        assert corpo_precisa_do_marcador(CORPO_ORIGINAL, "d-1") is True
        assert corpo_precisa_do_marcador(marcado, "d-2") is True

    def test_o_marcador_e_comentario_html(self):
        """Ele vive no corpo de uma issue que gente le: precisa ser invisivel no
        renderizado, e e o `<!-- -->` que garante isso."""
        marcador = marcador_da_demanda("d-1")
        assert marcador.startswith("<!--") and marcador.endswith("-->")


class TestFotoMudou:
    def test_foto_igual_nao_mudou(self):
        assert foto_mudou(_foto(), _foto()) is False

    def test_label_nova_e_mudanca(self):
        assert foto_mudou(_foto(), _foto(labels=("in-progress",))) is True

    def test_parte_nova_e_mudanca(self):
        assert foto_mudou(_foto(), _foto(partes=(_parte(674),))) is True

    def test_sem_foto_guardada_qualquer_foto_e_mudanca(self):
        assert foto_mudou(None, _foto()) is True


# ─── 3. O login no GitHub ────────────────────────────────────────────────────


class TestGithubLogin:
    @pytest.mark.parametrize(
        "bruto,esperado",
        (
            ("Pedro", "pedro"),
            ("  PedroRezendeFig  ", "pedrorezendefig"),
            ("@pedro", "pedro"),
            ("", None),
            ("   ", None),
            (None, None),
        ),
    )
    def test_normalizacao(self, bruto, esperado):
        assert normalizar_github_login(bruto) == esperado

    @pytest.mark.parametrize("login", ("pedro", "pedro-rezende", "p", "a1", "1pedro"))
    def test_login_que_o_github_aceita(self, login):
        assert motivo_github_login_invalido(login) is None

    @pytest.mark.parametrize("login", ("-pedro", "pedro-", "pe dro", "pedro@vitta", "a" * 40, "pedro--rezende"))
    def test_login_que_o_github_recusa(self, login):
        assert motivo_github_login_invalido(login) == MOTIVO_LOGIN_INVALIDO

    def test_sem_login_nao_e_recusa(self):
        assert motivo_github_login_invalido(None) is None

    @pytest.mark.parametrize(
        "participante,esperado",
        (
            ({"github_login": "pedro"}, True),
            ({"github_login": ""}, False),
            ({"github_login": "   "}, False),
            ({"github_login": None}, False),
            # Backend que subiu antes da migration 103: a coluna nem vem no
            # dict, e o lado seguro e o Vinculo desligado.
            ({}, False),
            (None, False),
        ),
    )
    def test_quem_e_da_vitta(self, participante, esperado):
        assert tem_github_login(participante) is esperado

    def test_a_frase_do_login_repetido_diz_de_quem_e(self):
        frase = motivo_github_login_repetido("pedro", "Pedro Vitta")
        assert "pedro" in frase
        assert "Pedro Vitta" in frase


# ─── 4. Os textos das linhas automaticas ─────────────────────────────────────


class TestTextosDoFio:
    def test_a_linha_da_etapa(self):
        assert texto_movimento_etapa(para=ETAPA_EM_DESENVOLVIMENTO) == "Etapa: Em desenvolvimento"

    def test_a_linha_da_etapa_com_partes(self):
        assert texto_movimento_etapa(para=ETAPA_ENTREGUE, entregues=3, total=7) == "Etapa: Entregue (3 de 7 partes)"

    def test_a_linha_do_vinculo(self):
        assert TEXTO_VINCULO_CRIADO == "Vínculo com o desenvolvimento criado"

    def test_a_linha_do_vinculo_desfeito(self):
        assert TEXTO_VINCULO_DESFEITO == "Vínculo com o desenvolvimento desfeito"

    @pytest.mark.parametrize("texto", (TEXTO_VINCULO_CRIADO, TEXTO_VINCULO_DESFEITO))
    def test_nenhuma_das_duas_carrega_numero_de_issue(self, texto):
        """As duas sao lidas pelo DIRETOR e saem do app dentro do "Copiar para
        IA". Um numero de issue aqui furaria a decisao 9 do ADR 0054 pela porta
        dos fundos, longe do funil que omite o Vinculo.

        A asserção e sobre o MARCADOR positivo (nenhum digito, nenhum `#`), e
        nao sobre a ausencia da substring "673": esta ultima e cega a qualquer
        outra forma de escrever o numero.
        """
        assert not any(c.isdigit() for c in texto), texto
        assert "#" not in texto, texto

    def test_nenhum_texto_do_fio_tem_travessao(self):
        """Regra da casa: travessao e meia-risca sao marca de texto gerado por
        IA e nao entram em nada que o usuario ve. Estas linhas vao para o fio
        que o DIRETOR le."""
        textos = [
            *ETAPA_ROTULO.values(),
            texto_movimento_etapa(para=ETAPA_ENTREGUE, entregues=3, total=7),
            TEXTO_VINCULO_CRIADO,
            TEXTO_VINCULO_DESFEITO,
            MOTIVO_SEM_GITHUB_LOGIN,
            MOTIVO_INTEGRACAO_DESLIGADA,
            MOTIVO_SEM_VINCULO_PARA_DESFAZER,
            MOTIVO_LOGIN_INVALIDO,
            motivo_issue_inexistente(1),
            motivo_e_pull_request(1),
            motivo_numero_ja_usado(1, "Demanda"),
            motivo_demanda_ja_vinculada(1),
        ]
        # Os dois vem por `chr` porque o caractere literal nao entra nem no
        # teste que o caca: o repo inteiro fica sem ele, e nao so o que passa
        # pelo grep do CI.
        for texto in textos:
            assert chr(0x2014) not in texto, texto
            assert chr(0x2013) not in texto, texto


# ─── Supabase duble ──────────────────────────────────────────────────────────


@dataclass
class _Result:
    data: list
    count: int = 0


class _TableQuery:
    """PostgREST minimo: select/eq/in_/order/range/insert/update.

    O `range` entra porque as abas "Minha vez" e Historico leem pelo `ler_tudo`
    da casa, que pagina: sem ele, o teste da omissao nessas duas listas cairia
    por falta de metodo no dublê, e nao por defeito da regra.
    """

    def __init__(self, rows: list[dict], nome: str):
        self._rows = rows
        self._nome = nome
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._order: list[str] = []
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, **_kw):
        self._order.append(coluna)
        return self

    def range(self, inicio, fim):
        self._range = (inicio, fim)
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def in_(self, coluna, valores):
        self._in[coluna] = list(valores)
        return self

    def insert(self, payload):
        linhas = payload if isinstance(payload, list) else [payload]
        self._insert = [dict(linha) for linha in linhas]
        return self

    def update(self, payload: dict):
        self._update = dict(payload)
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        if self._insert is not None:
            for i, linha in enumerate(self._insert):
                linha.setdefault("id", f"{self._nome}-{len(self._rows) + i + 1}")
                linha.setdefault("criado_em", f"2026-09-10T12:00:{len(self._rows) + i:02d}Z")
            self._rows.extend(self._insert)
            return _Result(data=[dict(linha) for linha in self._insert])

        casadas = [linha for linha in self._rows if self._casa(linha)]

        if self._update is not None:
            for linha in casadas:
                linha.update(self._update)
            return _Result(data=[dict(linha) for linha in casadas])

        for coluna in reversed(self._order):
            casadas.sort(key=lambda linha, c=coluna: (linha.get(c) is None, linha.get(c)))
        if self._range is not None:
            inicio, fim = self._range
            casadas = casadas[inicio : fim + 1]
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []), nome)


# ─── Cenario ─────────────────────────────────────────────────────────────────


def _pessoa(
    pid: str, nome: str, *, github_login: str | None = None, access_profile: str | None = "super_admin"
) -> dict:
    return {
        "id": pid,
        "auth_user_id": f"auth-{pid}",
        "nome_completo": nome,
        "email": f"{pid}@hsm.com",
        "cargo": None,
        "area": None,
        "setor": None,
        "role": None,
        "ativo": True,
        "is_externo": False,
        "is_super_admin": access_profile == "super_admin",
        "access_profile": access_profile,
        "perfil_pop": None,
        "perfil_ouvidoria": None,
        "github_login": github_login,
        "data_cadastro": "2026-01-01",
    }


def _demanda(did: str, **campos) -> dict:
    base = {
        "id": did,
        "titulo": "Levar o selo de Etapa ao card",
        "descricao": None,
        "tipo": "novo",
        "produto_id": "prod-1",
        "estado": "nova",
        "responsavel_id": "P1",
        "autor_id": "P1",
        "prioridade": "normal",
        "prazo": None,
        "criado_em": "2026-09-01T09:00:00Z",
        "atualizado_em": "2026-09-01T09:00:00Z",
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
        "github_issue_numero": None,
        "etapa": ETAPA_REGISTRADA,
        "partes_entregues": None,
        "partes_total": None,
        "o_que_muda": None,
        "partes": None,
        "github_foto": None,
        "github_sincronizado_em": None,
        "vinculado_por": None,
    }
    base.update(campos)
    return base


# Da Vitta (tem login) e do hospital (nao tem). Os dois sao Super admin: e o que
# faz o gate do Vinculo ser um gate DIFERENTE do de papel.
PEDRO = _pessoa("P1", "Pedro Vitta", github_login="pedrorezendefig")
DIRETOR = _pessoa("P2", "Diretor do Hospital")


class _GithubFalso:
    """O GitHub como o teste o quer: uma issue por numero, e um registro do que
    foi escrito nela."""

    def __init__(self, issues: dict[int, dict], *, sub_issues: dict[int, list[dict]] | None = None, erro=None):
        self.issues = issues
        self.sub_issues = sub_issues or {}
        self.erro = erro
        self.corpos_escritos: list[tuple[int, str]] = []
        self.leituras: list[int] = []

    def ler_issue(self, numero: int) -> dict:
        if self.erro is not None:
            raise self.erro
        self.leituras.append(numero)
        if numero not in self.issues:
            raise github_client.IssueNaoEncontradaError(str(numero))
        return self.issues[numero]

    def ler_sub_issues(self, numero: int) -> list[dict]:
        return self.sub_issues.get(numero, [])

    def atualizar_corpo(self, numero: int, corpo: str) -> None:
        self.corpos_escritos.append((numero, corpo))
        self.issues[numero]["body"] = corpo


def _issue(
    numero: int, *, corpo: str | None = CORPO_ORIGINAL, estado: str = "open", motivo=None, labels=(), resumo=None
):
    dados = {
        "number": numero,
        "title": "Tecnologia: fundação do Vínculo",
        "html_url": f"https://github.com/pedrorezendefig/hospital-reunioes/issues/{numero}",
        "state": estado,
        "state_reason": motivo,
        "labels": [{"name": nome} for nome in labels],
        "body": corpo,
    }
    if resumo is not None:
        dados["sub_issues_summary"] = resumo
    return dados


def _montar(
    *,
    logado: dict = PEDRO,
    participantes: list[dict] | None = None,
    demandas: list[dict] | None = None,
    conversas: list[dict] | None = None,
    github: _GithubFalso | None = None,
    supabase: _SupabaseMock | None = None,
    monkeypatch=None,
) -> tuple[TestClient, _SupabaseMock, _GithubFalso]:
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(tecnologia_router.router, prefix="/api")

    pessoas = [dict(p) for p in (participantes if participantes is not None else [PEDRO, DIRETOR])]
    if all(p["id"] != logado["id"] for p in pessoas):
        pessoas.append(dict(logado))

    # `supabase` reaproveita o banco de outra montagem: e o que permite ESCREVER
    # como quem e da Vitta e LER como o diretor, sobre as MESMAS linhas. Fabricar
    # a linha do fio a mao no segundo cliente provaria a leitura sobre um dado
    # que o escritor talvez nem produza assim.
    sb = supabase or _SupabaseMock(
        {
            "participantes": pessoas,
            "tecnologia_produtos": [{"id": "prod-1", "nome": "Reuniões", "ativo": True, "ordem": 1, "dono_id": "P1"}],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
            "tecnologia_conversas": [dict(c) for c in (conversas or [])],
        }
    )

    gh = github or _GithubFalso({})
    if monkeypatch is not None:
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        monkeypatch.setattr(github_client, "atualizar_corpo", gh.atualizar_corpo)

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb, gh


def _fio(sb: _SupabaseMock) -> list[dict]:
    return sb.tabelas["tecnologia_conversas"]


class TestATravaDeRedeContinuaDePe:
    """A contraprova das guardas que impedem este arquivo de sair para a rede.

    Uma fixture que ninguem observa e uma fixture que pode sumir sem que nada
    acuse. Estes dois testes a tornam visivel: se a `_sem_github_de_verdade`
    virar no-op ou desaparecer, e AQUI que o vermelho aparece, e nao num teste
    de regra que nada tem com rede.
    """

    def test_chamar_o_cliente_sem_duble_estoura(self):
        """Sem duble, o cliente do GitHub NAO sai da maquina.

        O `.env` que o pytest carrega tem credencial de producao; um teste que
        esquecesse de dublar `ler_issue` conversaria com api.github.com de
        verdade, e ficaria verde. Aqui a tentativa e cobrada.
        """
        with pytest.raises(AssertionError, match="chamado de verdade"):
            github_client.ler_issue(673)

    def test_a_escrita_tambem_esta_trancada(self):
        """O verbo que MUDA a issue de outra pessoa merece a sua propria prova."""
        with pytest.raises(AssertionError, match="chamado de verdade"):
            github_client.atualizar_corpo(673, "corpo novo")


# ─── 5. O "eu" da aba e a lista de pessoas ───────────────────────────────────


class TestQuemSouEu:
    def test_quem_tem_login_e_da_vitta(self, monkeypatch):
        client, _, _ = _montar(logado=PEDRO, monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/eu").json()

        assert corpo["id"] == "P1"
        assert corpo["tem_github_login"] is True
        assert corpo["integracao_configurada"] is True

    def test_quem_nao_tem_login_nao_e(self, monkeypatch):
        client, _, _ = _montar(logado=DIRETOR, monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/eu").json()

        assert corpo["tem_github_login"] is False

    def test_sem_token_a_integracao_aparece_desligada(self, monkeypatch):
        """A tela precisa saber ANTES de desenhar o campo. Quem apaga a variavel
        e o teste; a guarda de verdade continua rodando."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, _, _ = _montar(logado=PEDRO, monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/eu").json()

        assert corpo["integracao_configurada"] is False
        # E quem tem login continua tendo: as duas perguntas sao independentes.
        assert corpo["tem_github_login"] is True

    def test_sem_repositorio_a_integracao_aparece_desligada(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_repo", "")
        client, _, _ = _montar(logado=PEDRO, monkeypatch=monkeypatch)

        assert client.get(f"{BASE}/eu").json()["integracao_configurada"] is False


class TestPessoasDizemSeTemLogin:
    def test_a_lista_diz_quem_e_da_vitta(self, monkeypatch):
        client, _, _ = _montar(monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/pessoas").json()
        por_id = {p["id"]: p for p in corpo}

        assert por_id["P1"]["tem_github_login"] is True
        assert por_id["P2"]["tem_github_login"] is False

    def test_a_lista_nao_devolve_o_login(self, monkeypatch):
        """Quem le esta lista e a escolha de dono, responsavel e @mencao: a
        identidade de ninguem no GitHub tem o que fazer ali."""
        client, _, _ = _montar(monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/pessoas").json()

        assert all("github_login" not in pessoa for pessoa in corpo)


# ─── 6. Vincular ─────────────────────────────────────────────────────────────


class TestGateDoVinculo:
    def test_quem_nao_tem_login_leva_403_mesmo_sendo_super_admin(self, monkeypatch):
        """O criterio da issue: 403 para quem nao tem `github_login`, MESMO
        sendo Super admin. E o que prova que este gate nao e o de papel."""
        client, sb, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == MOTIVO_SEM_GITHUB_LOGIN
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_desvincular_tambem_leva_403(self, monkeypatch):
        client, sb, _ = _montar(
            logado=DIRETOR,
            demandas=[_demanda("d-1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/desvincular")

        assert resposta.status_code == 403
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] == 673

    def test_sem_token_configurado_a_api_responde_503(self, monkeypatch):
        """Apaga a VARIAVEL, e nao a guarda: um monkeypatch em
        `_exigir_integracao` deixaria o teste verde sobre o proprio dublê."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, sb, _ = _montar(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == MOTIVO_INTEGRACAO_DESLIGADA
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_sem_repositorio_configurado_a_api_responde_503(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_repo", "")
        client, _, _ = _montar(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 503

    def test_o_login_e_conferido_antes_da_configuracao(self, monkeypatch):
        """Duas guardas, duas causas. Quem nao e da Vitta le "isto nao e seu", e
        nao "falta configurar", que o mandaria procurar um problema que nao e
        dele."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, _, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 403


class TestVincularRecusa:
    def test_numero_inexistente(self, monkeypatch):
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 999})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == motivo_issue_inexistente(999)
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_pull_request(self, monkeypatch):
        """A API de issues tambem responde por PR: o `pull_request` no corpo e o
        que os separa."""
        pr = _issue(700)
        pr["pull_request"] = {"url": "https://api.github.com/repos/x/y/pulls/700"}
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=_GithubFalso({700: pr}), monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 700})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == motivo_e_pull_request(700)
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_numero_ja_usado_por_outra_demanda(self, monkeypatch):
        client, sb, gh = _montar(
            demandas=[
                _demanda("d-1"),
                _demanda("d-2", titulo="O PRD antigo", github_issue_numero=673, etapa=ETAPA_PLANEJADA),
            ],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == motivo_numero_ja_usado(673, "O PRD antigo")
        # A recusa vem ANTES da ida ao GitHub: nao ha por que gastar cota para
        # descobrir algo que o banco de ca ja sabia.
        assert gh.leituras == []

    def test_cada_recusa_tem_a_sua_frase(self):
        """As tres nao podem colapsar numa mensagem so: as saidas sao
        diferentes (digitar outro numero, usar a issue-raiz, procurar a outra
        Demanda)."""
        frases = {motivo_issue_inexistente(1), motivo_e_pull_request(1), motivo_numero_ja_usado(1, "X")}
        assert len(frases) == 3

    def test_demanda_ja_vinculada_a_outro_numero(self, monkeypatch):
        client, _, _ = _montar(
            demandas=[_demanda("d-1", github_issue_numero=600, etapa=ETAPA_PLANEJADA)],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == motivo_demanda_ja_vinculada(600)

    @pytest.mark.parametrize("numero", (0, -1))
    def test_numero_que_nao_e_de_issue(self, numero, monkeypatch):
        client, _, gh = _montar(demandas=[_demanda("d-1")], github=_GithubFalso({}), monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": numero})

        assert resposta.status_code == 422
        assert gh.leituras == []

    def test_github_fora_do_ar_nao_vira_500(self, monkeypatch):
        """Falha de terceiro nao e defeito nosso, e a Demanda nao pode ficar
        vinculada pela metade."""
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({}, erro=github_client.GithubIndisponivelError("timeout")),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert resposta.status_code == 502
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None
        assert _fio(sb) == []


class TestVincularGrava:
    def test_o_marcador_entra_no_corpo_sem_alterar_o_resto(self, monkeypatch):
        client, _, gh = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).status_code == 200

        assert len(gh.corpos_escritos) == 1
        numero, corpo = gh.corpos_escritos[0]
        assert numero == 673
        assert corpo.startswith(CORPO_ORIGINAL)
        assert demanda_id_do_marcador(corpo) == "d-1"

    def test_vincular_de_novo_o_mesmo_numero_nao_duplica_o_marcador(self, monkeypatch):
        client, sb, gh = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        segunda = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert segunda.status_code == 200
        assert gh.issues[673]["body"].count("demanda-vitta") == 1
        # A segunda vez nem chega a escrever: o corpo ja estava como deveria.
        assert len(gh.corpos_escritos) == 1

    def test_sincroniza_na_hora(self, monkeypatch):
        """Criterio: a Demanda responde com Etapa, partes e ultima
        sincronizacao JA preenchidos. Sem isso o card ficaria sem selo ate a
        reconciliacao da fatia seguinte passar."""
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso(
                {673: _issue(673, labels=("ready-for-agent",), resumo={"total": 7, "completed": 3})},
                sub_issues={673: [_issue(674), _issue(675)]},
            ),
            monkeypatch=monkeypatch,
        )

        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["etapa"] == ETAPA_PLANEJADA
        assert corpo["partes_entregues"] == 3
        assert corpo["partes_total"] == 7
        assert corpo["github_sincronizado_em"]
        assert corpo["vinculo"] == {
            "numero": 673,
            "url": "https://github.com/pedrorezendefig/hospital-reunioes/issues/673",
        }
        gravada = sb.tabelas["tecnologia_demandas"][0]
        assert gravada["github_issue_numero"] == 673
        assert gravada["vinculado_por"] == "P1"
        assert gravada["github_foto"]["labels"] == ["ready-for-agent"]

    def test_sem_sub_issues_as_partes_vem_nulas(self, monkeypatch):
        client, _, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673)}),
            monkeypatch=monkeypatch,
        )

        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["partes_entregues"] is None
        assert corpo["partes_total"] is None

    def test_a_etapa_vem_da_foto_e_nao_de_um_default(self, monkeypatch):
        """Mutante do dublê: com uma issue `in-progress`, uma Etapa cravada em
        `em_analise` no router passaria por todos os testes de estrutura acima."""
        client, _, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673, labels=("in-progress",))}),
            monkeypatch=monkeypatch,
        )

        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["etapa"] == ETAPA_EM_DESENVOLVIMENTO


class TestLinhasAutomaticasDoVinculo:
    def test_vincular_grava_a_linha_do_vinculo_e_a_da_etapa(self, monkeypatch):
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673, labels=("ready-for-agent",))}),
            monkeypatch=monkeypatch,
        )

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        linhas = _fio(sb)
        assert [linha["movimento_campo"] for linha in linhas] == ["vinculo", "etapa"]
        assert linhas[0]["texto"] == TEXTO_VINCULO_CRIADO
        assert linhas[1]["texto"] == texto_movimento_etapa(para=ETAPA_PLANEJADA)
        # Linha automatica nao tem autor: quem mudou foi o GitHub.
        assert all(linha["autor_id"] is None for linha in linhas)
        assert all(linha["linha"] == "movimento" for linha in linhas)

    def test_a_linha_da_etapa_leva_as_partes(self, monkeypatch):
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso(
                {673: _issue(673, labels=("ready-for-agent",), resumo={"total": 7, "completed": 3})},
                sub_issues={673: [_issue(674)]},
            ),
            monkeypatch=monkeypatch,
        )

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert _fio(sb)[1]["texto"] == "Etapa: Planejada (3 de 7 partes)"

    def test_foto_igual_a_guardada_nao_grava_nada(self, monkeypatch):
        """Criterio de aceite. Sem esta guarda, a reconciliacao de hora em hora
        da fatia seguinte encheria o fio do diretor de linhas repetidas."""
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673, labels=("ready-for-agent",))}),
            monkeypatch=monkeypatch,
        )

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        quantas = len(_fio(sb))

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert len(_fio(sb)) == quantas

    def test_a_etapa_que_muda_grava_linha_nova(self, monkeypatch):
        """O par de presenca do teste acima: uma guarda cravada em "nao grava"
        passaria por ele sem provar nada."""
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        quantas = len(_fio(sb))

        gh.issues[673]["labels"] = [{"name": "in-progress"}]
        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        linhas = _fio(sb)
        assert len(linhas) == quantas + 1
        assert linhas[-1]["movimento_campo"] == "etapa"
        assert linhas[-1]["texto"] == texto_movimento_etapa(para=ETAPA_EM_DESENVOLVIMENTO)
        assert linhas[-1]["movimento_de"] == ETAPA_PLANEJADA
        assert linhas[-1]["movimento_para"] == ETAPA_EM_DESENVOLVIMENTO

    def test_foto_que_muda_sem_mudar_a_etapa_nao_grava_linha(self, monkeypatch):
        """Duas guardas empilhadas, e as duas precisam existir.

        A de cima (`foto_mudou`) cala a sincronizacao que nao trouxe novidade
        NENHUMA. Esta de baixo cala a que trouxe novidade que NAO e Etapa: uma
        label de area trocada muda a foto e nao muda em que ponto a Vitta esta.
        Sem ela, o fio do diretor ganharia "Etapa: Em analise" de novo a cada
        edicao de label no GitHub.
        """
        gh = _GithubFalso({673: _issue(673, labels=("area:backend",))})
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        quantas = len(_fio(sb))

        gh.issues[673]["labels"] = [{"name": "area:frontend"}]
        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        # A foto MUDOU (o par de presenca da guarda de cima)...
        assert sb.tabelas["tecnologia_demandas"][0]["github_foto"]["labels"] == ["area:frontend"]
        # ...e mesmo assim nenhuma linha nova entrou no fio.
        assert len(_fio(sb)) == quantas

    def test_vincular_de_novo_nao_repete_a_linha_do_vinculo(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        gh.issues[673]["labels"] = [{"name": "in-progress"}]
        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})

        assert [linha["movimento_campo"] for linha in _fio(sb)].count("vinculo") == 1


class TestOQueODiretorLeNoFio:
    """O numero da issue NAO chega ao diretor pela Conversa (ADR 0054, decisao 9).

    O fio e a superficie mais larga que existe: ele aparece na tela E sai do app
    dentro do "Copiar para IA", que o diretor cola numa ferramenta de fora. As
    duas rotas que o leem tem so `require_super_admin`, e o diretor E Super
    admin: o corte tem de estar no funil de leitura, e nao na porta.

    Os testes ESCREVEM como quem e da Vitta, pela rota de vincular, e LEEM como o
    diretor, pela rota da Conversa, sobre o mesmo banco. Fabricar a linha a mao
    provaria a leitura sobre um dado que o escritor talvez nem produza assim.
    """

    @staticmethod
    def _com_vinculo_gravado(monkeypatch):
        """Vincula de verdade e devolve o banco resultante."""
        client, sb, _ = _montar(
            logado=PEDRO,
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673, labels=("ready-for-agent",))}),
            monkeypatch=monkeypatch,
        )
        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).status_code == 200
        return sb

    @staticmethod
    def _linha_do_vinculo(corpo: list[dict]) -> dict:
        linhas = [linha for linha in corpo if linha.get("movimento_campo") == "vinculo"]
        assert len(linhas) == 1, f"esperava uma linha de vinculo no fio, achei {len(linhas)}"
        return linhas[0]

    def test_o_diretor_le_a_linha_do_vinculo_sem_numero(self, monkeypatch):
        sb = self._com_vinculo_gravado(monkeypatch)
        client, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas/d-1/conversa").json()
        linha = self._linha_do_vinculo(corpo)

        # Marcador POSITIVO: o texto e exatamente a frase sem numero. Asserir a
        # ausencia de "673" seria cego a qualquer outra forma de escrever o
        # numero (issue #673, GH-673, "673").
        assert linha["texto"] == TEXTO_VINCULO_CRIADO
        assert linha["movimento_de"] is None
        assert linha["movimento_para"] is None

    def test_quem_e_da_vitta_continua_lendo_o_numero_no_de_para(self, monkeypatch):
        """O par de presenca: uma omissao cravada passaria pelo teste acima sem
        provar nada, e o rastreio de quem trabalha no GitHub sumiria junto."""
        sb = self._com_vinculo_gravado(monkeypatch)
        client, _, _ = _montar(logado=PEDRO, supabase=sb, monkeypatch=monkeypatch)

        linha = self._linha_do_vinculo(client.get(f"{BASE}/demandas/d-1/conversa").json())

        assert linha["texto"] == TEXTO_VINCULO_CRIADO
        assert linha["movimento_para"] == "673"

    def test_a_linha_da_etapa_chega_inteira_aos_dois(self, monkeypatch):
        """So a linha do VINCULO carrega numero de issue. `etapa`, `estado` e
        `responsavel` guardam valores do dominio da propria Demanda, e cortar o
        de/para deles apagaria rastro sem proteger nada."""
        sb = self._com_vinculo_gravado(monkeypatch)
        client, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas/d-1/conversa").json()
        etapa = next(linha for linha in corpo if linha.get("movimento_campo") == "etapa")

        assert etapa["movimento_de"] == ETAPA_REGISTRADA
        assert etapa["movimento_para"] == ETAPA_PLANEJADA
        assert etapa["texto"] == texto_movimento_etapa(para=ETAPA_PLANEJADA)

    def test_o_texto_para_ia_do_diretor_nao_leva_o_numero(self, monkeypatch):
        """A pior superficie das duas: este texto SAI do app pelo clipboard."""
        sb = self._com_vinculo_gravado(monkeypatch)
        client, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)

        texto = client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

        assert TEXTO_VINCULO_CRIADO in texto
        # A linha do Vinculo, isolada do resto do texto (que tem datas e horas),
        # nao pode ter digito nenhum.
        linha = next(pedaco for pedaco in texto.splitlines() if TEXTO_VINCULO_CRIADO in pedaco)
        assert not any(c.isdigit() for c in linha.split(TEXTO_VINCULO_CRIADO[:8])[-1])

    def test_desvincular_tambem_nao_deixa_numero_no_fio_do_diretor(self, monkeypatch):
        sb = self._com_vinculo_gravado(monkeypatch)
        client_vitta, _, _ = _montar(logado=PEDRO, supabase=sb, monkeypatch=monkeypatch)
        assert client_vitta.post(f"{BASE}/demandas/d-1/desvincular").status_code == 200

        client, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)
        corpo = client.get(f"{BASE}/demandas/d-1/conversa").json()
        desfeito = [linha for linha in corpo if linha["texto"] == TEXTO_VINCULO_DESFEITO]

        assert len(desfeito) == 1
        assert desfeito[0]["movimento_de"] is None
        assert desfeito[0]["movimento_para"] is None

    def test_a_resposta_de_gente_atravessa_intacta(self, monkeypatch):
        """A omissao morde SO a linha do Vinculo: uma que apagasse o de/para de
        toda linha, ou que mexesse no texto das respostas, quebraria o fio."""
        sb = self._com_vinculo_gravado(monkeypatch)
        client, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)
        assert (
            client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Combinado, pode seguir."}).status_code == 201
        )

        corpo = client.get(f"{BASE}/demandas/d-1/conversa").json()
        resposta = next(linha for linha in corpo if linha["linha"] == "resposta")

        assert resposta["texto"] == "Combinado, pode seguir."
        assert resposta["autor_nome"] == "Diretor do Hospital"


# ─── 7. Desvincular ──────────────────────────────────────────────────────────


class TestDesvincular:
    def test_limpa_o_vinculo_e_o_cache_e_grava_a_linha(self, monkeypatch):
        client, sb, _ = _montar(
            demandas=[
                _demanda(
                    "d-1",
                    github_issue_numero=673,
                    etapa=ETAPA_EM_DESENVOLVIMENTO,
                    partes_entregues=3,
                    partes_total=7,
                    github_foto=_foto(),
                    github_sincronizado_em="2026-09-10T10:00:00Z",
                    vinculado_por="P1",
                )
            ],
            monkeypatch=monkeypatch,
        )

        resposta = client.post(f"{BASE}/demandas/d-1/desvincular")

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["etapa"] == ETAPA_REGISTRADA
        assert corpo["vinculo"] is None
        assert corpo["partes_entregues"] is None
        assert corpo["partes_total"] is None
        assert corpo["github_sincronizado_em"] is None

        gravada = sb.tabelas["tecnologia_demandas"][0]
        assert gravada["github_issue_numero"] is None
        assert gravada["github_foto"] is None
        assert gravada["vinculado_por"] is None

        linhas = _fio(sb)
        assert len(linhas) == 1
        assert linhas[0]["movimento_campo"] == "vinculo"
        assert linhas[0]["texto"] == TEXTO_VINCULO_DESFEITO
        assert linhas[0]["movimento_de"] == "673"
        assert linhas[0]["movimento_para"] is None

    def test_demanda_sem_vinculo_nao_tem_o_que_desfazer(self, monkeypatch):
        client, sb, _ = _montar(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/desvincular")

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_SEM_VINCULO_PARA_DESFAZER
        assert _fio(sb) == []

    def test_nao_depende_do_github(self, monkeypatch):
        """Integracao fora do ar nao pode prender a Demanda a uma issue errada:
        o que se limpa aqui e o lado de ca. A fixture `_sem_github_de_verdade`
        derruba o teste se alguem sair para a rede por este caminho."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, sb, _ = _montar(
            demandas=[_demanda("d-1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
            monkeypatch=monkeypatch,
        )

        assert client.post(f"{BASE}/demandas/d-1/desvincular").status_code == 200
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None


class TestTetoDasPortasDeEscrita:
    """O recurso escasso aqui e a cota da API do GitHub, que e UMA para o app
    inteiro (ADR 0054, decisao 8: um token pessoal). Cada `vincular` gasta duas
    leituras e ate uma escrita la; sem teto, um laco bobo numa conta de Super
    admin da Vitta derrubaria a integracao para todo mundo, inclusive para a
    reconciliacao da fatia seguinte."""

    def test_as_duas_portas_dividem_o_mesmo_balde(self):
        """`shared_limit` por NOME, e nao `limit`.

        O `Limiter` da casa nasce com `key_style="url"`: com `limit`, cada
        Demanda ganharia o proprio balde, e quem tem cem Demandas teria cem
        tetos. O teto viraria enfeite justo na porta em que ele foi pedido.
        """
        # O balde do Vinculo nao e o dos gatilhos de e-mail: sao recursos
        # externos diferentes (cota do GitHub e cota do Resend), e um laco num
        # deles nao pode consumir o teto do outro.
        assert tecnologia_router.ESCOPO_DO_VINCULO != tecnologia_router.ESCOPO_DO_GATILHO

    def test_o_teto_de_verdade_recusa_com_429(self, monkeypatch):
        """Prova pela ROTA, e nao pela presenca do decorador: um teto declarado
        e nao ligado (o `app.state.limiter` esquecido, por exemplo) passaria por
        qualquer asserção de atributo."""
        gh = _GithubFalso({673: _issue(673)})
        client, _, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        limite = int(tecnologia_router.LIMITE_DO_VINCULO.split("/")[0])
        respostas = [client.post(f"{BASE}/demandas/d-1/desvincular").status_code for _ in range(limite + 1)]

        assert respostas[-1] == 429, respostas[-3:]
        # E o teto e o unico motivo da recusa final: as anteriores passaram pela
        # regra (422 de "não tem Vínculo para desfazer"), e não por 429.
        assert 429 not in respostas[:limite]


# ─── 8. Quem ve o numero e quem ve so a Etapa ────────────────────────────────


class TestOmissaoDoVinculo:
    """ADR 0054, decisao 9: o que e da Vitta fica atras do `github_login`."""

    DEMANDA = dict(
        github_issue_numero=673,
        etapa=ETAPA_EM_DESENVOLVIMENTO,
        partes_entregues=3,
        partes_total=7,
        github_foto=_foto(),
    )

    def test_quem_tem_login_ve_o_numero_e_a_url(self, monkeypatch):
        client, _, _ = _montar(logado=PEDRO, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["vinculo"]["numero"] == 673
        assert corpo["vinculo"]["url"].endswith("/issues/673")

    def test_quem_nao_tem_login_nao_ve_numero_nem_url(self, monkeypatch):
        client, _, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["vinculo"] is None
        # E nao ha numero de issue vazando por nenhum outro campo da resposta.
        assert "673" not in str(corpo)

    def test_quem_nao_tem_login_continua_vendo_a_etapa(self, monkeypatch):
        """O diretor ve o SELO: a Etapa em palavras e o "3 de 7 partes". E so o
        numero e o link que ficam atras do login."""
        client, _, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert corpo["partes_entregues"] == 3
        assert corpo["partes_total"] == 7

    @staticmethod
    def _demanda_que_a_lista_mostra(caminho: str, quem: str) -> dict:
        """A Demanda no estado que CADA lista mostra.

        Uma so nao serve as tres: "Minha vez" traz apenas as abertas de quem
        esta logado, e o Historico apenas as fechadas. Uma Demanda concluida
        deixaria "Minha vez" vazia, e o teste da omissao passaria sobre uma
        lista sem nada dentro, que e o vacuo classico.
        """
        aberta = caminho != "/historico"
        campos = dict(TestOmissaoDoVinculo.DEMANDA, responsavel_id=quem)
        if aberta:
            return _demanda("d-1", estado="em_andamento", **campos)
        return _demanda("d-1", estado="concluida", concluida_em="2026-09-09T10:00:00Z", concluida_por=quem, **campos)

    @pytest.mark.parametrize("caminho", ("/demandas", "/minha-vez", "/historico"))
    def test_a_omissao_vale_em_toda_lista(self, caminho, monkeypatch):
        """A regra mora no funil por onde TODA Demanda sai da API. Uma lista que
        montasse a resposta por conta propria mostraria o numero ao diretor, e
        ninguem perceberia: a resposta continuaria bem formada."""
        client, _, _ = _montar(
            logado=DIRETOR,
            demandas=[self._demanda_que_a_lista_mostra(caminho, "P2")],
            monkeypatch=monkeypatch,
        )

        corpo = client.get(f"{BASE}{caminho}").json()

        assert corpo, f"{caminho} devolveu lista vazia: o teste ficaria verde sobre nada"
        for demanda in corpo:
            assert demanda["vinculo"] is None

    @pytest.mark.parametrize("caminho", ("/demandas", "/minha-vez", "/historico"))
    def test_o_par_de_presenca_da_omissao(self, caminho, monkeypatch):
        """Sem ele, uma resposta que NUNCA traz o objeto do Vinculo passaria por
        todos os testes acima."""
        client, _, _ = _montar(
            logado=PEDRO,
            demandas=[self._demanda_que_a_lista_mostra(caminho, "P1")],
            monkeypatch=monkeypatch,
        )

        corpo = client.get(f"{BASE}{caminho}").json()

        assert corpo, f"{caminho} devolveu lista vazia: o teste ficaria verde sobre nada"
        for demanda in corpo:
            assert demanda["vinculo"]["numero"] == 673

    def test_demanda_sem_vinculo_nao_tem_objeto_nem_para_quem_tem_login(self, monkeypatch):
        client, _, _ = _montar(logado=PEDRO, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["vinculo"] is None
        assert corpo["etapa"] == ETAPA_REGISTRADA


class TestEtapaNaoSeDigita:
    def test_o_patch_da_demanda_nao_aceita_a_etapa(self, monkeypatch):
        """ADR 0054, decisao 3: a Etapa e derivada e nunca editavel. Uma porta
        que a aceitasse a faria mentir na primeira vez que alguem a usasse."""
        client, sb, _ = _montar(
            demandas=[_demanda("d-1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
            monkeypatch=monkeypatch,
        )

        resposta = client.patch(f"{BASE}/demandas/d-1", json={"titulo": "Outro título", "etapa": ETAPA_ENTREGUE})

        assert resposta.status_code in (200, 422)
        assert sb.tabelas["tecnologia_demandas"][0]["etapa"] == ETAPA_PLANEJADA
        if resposta.status_code == 200:
            # O resto da edicao valeu: o campo foi IGNORADO, e nao engoliu a
            # requisicao inteira em silencio.
            assert resposta.json()["titulo"] == "Outro título"
            assert resposta.json()["etapa"] == ETAPA_PLANEJADA

    def test_o_patch_nao_aceita_o_numero_da_issue(self, monkeypatch):
        client, sb, _ = _montar(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        client.patch(f"{BASE}/demandas/d-1", json={"titulo": "Outro título", "github_issue_numero": 673})

        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None
