"""O Vinculo da Demanda com a issue do GitHub (issue #674, PRD #673, ADR 0054).

Desde a ADR 0077 o Vinculo nasce de um jeito so, o "Criar o card" do chat
(testado pela rota em `test_tecnologia_chat.py`); o Vinculo por numero, o
desvincular e o "Levar para desenvolvimento" sairam na issue #1386. Ficam aqui:

* **A tabela de Etapas**, funcao pura, testada direto e sem HTTP. As sete
  saidas e a PRECEDENCIA entre elas sao escritas aqui a mao, a partir da issue;
  o caso que separa cada regra da seguinte tem o seu proprio teste, porque e na
  sobreposicao que a tabela erra (issue fechada com o `in-progress` preso e
  Entregue, e nao "em desenvolvimento para sempre").
* **O bloco "Para o diretor"**, as partes, o marcador e a peneira do texto que
  vai para a issue publica, tambem puros.
* **Os dubles** do Supabase e do GitHub que os testes do chat, da
  sincronizacao e dos anexos usam.

O cliente do GitHub NUNCA e chamado de verdade: a fixture `_sem_github_de_verdade`
troca o transporte por um que estoura, e a trava de rede do `conftest.py`
continua por baixo. As duas de proposito: a fixture aponta o arquivo culpado, a
trava derruba a sessao se a fixture algum dia sumir.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
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
from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPA_REGISTRADA,
    ETAPAS,
    LABEL_TRIAGEM,
    MOTIVO_LOGIN_INVALIDO,
    bloco_para_o_diretor,
    corpo_da_issue_do_bug,
    etapa_da_foto,
    labels_da_issue_nova,
    marcador_da_demanda,
    motivo_github_login_invalido,
    motivo_github_login_repetido,
    normalizar_github_login,
    partes_da_foto,
    partes_para_o_diretor,
    situacao_da_parte,
    texto_do_diretor,
)

BASE = "/api/admin/tecnologia"

# O `criar_issue` real, guardado antes de qualquer `_montar` troca-lo pelo duble.
_CRIAR_ISSUE_DE_VERDADE = github_client.criar_issue

MIGRATIONS = Path(__file__).resolve().parents[2] / "supabase" / "migrations"
MIGRATION = MIGRATIONS / "103_tecnologia_vinculo.sql"
# A fundacao do PRD #1056 (issue #1057): a ultima que redefine o CHECK da Etapa.
MIGRATION_FUNDACAO_1056 = MIGRATIONS / "115_tecnologia_anexos_e_em_producao.sql"


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
        teste sem rodar caso nenhum, e ele ficaria verde sobre nada.

        A setima Etapa (Em producao, ADR 0069) nao nasce de foto nenhuma: ela
        precisa da versao, que e fato do app. A cobertura dela mora em
        `TestEmProducaoEPrAberto`, e a uniao das duas tabelas fecha as sete."""
        assert len(ETAPAS) == 7
        assert len(LINHAS_DA_TABELA) == 13
        assert len(LINHAS_COM_FATOS_DO_APP) == 5
        saidas = {saida for _, _, saida in LINHAS_DA_TABELA} | {saida for _, _, _, saida in LINHAS_COM_FATOS_DO_APP}
        assert saidas == set(ETAPAS)

    @pytest.mark.parametrize("caso,foto,esperada", LINHAS_DA_TABELA, ids=lambda v: v if isinstance(v, str) else "")
    def test_cada_linha_da_tabela(self, caso, foto, esperada):
        assert etapa_da_foto(foto) == esperada

    def test_a_migration_conhece_as_mesmas_sete(self):
        """As duas pontas amarradas: o CHECK da ultima migration que o redefine
        (a 115) e a tupla do servico. Uma Etapa nova no Python que nao entrasse
        no CHECK viraria erro de banco na hora de gravar, em producao, e nao
        aqui. A lista e lida DE DENTRO do CHECK, e comparada inteira: achar o
        valor em qualquer lugar do arquivo (num comentario) nao conta."""
        sql = MIGRATION_FUNDACAO_1056.read_text(encoding="utf-8")
        check = re.search(r"CHECK \(etapa IN \(([^)]*)\)\)", sql)
        assert check, "a migration 115 nao redefine o CHECK da Etapa"
        valores = {v.strip().strip("'") for v in check.group(1).split(",")}
        assert valores == set(ETAPAS)


# Os dois fatos que a foto da issue nao traz (issue #1057, ADR 0069): a versao
# em que a Demanda subiu, gravada pela Action pos-merge, e o PR aberto que fecha
# a raiz, que vem do webhook `pull_request`. Nesta fatia ninguem os alimenta
# ainda; a funcao pura so os aceita.
LINHAS_COM_FATOS_DO_APP = [
    (
        "versao gravada e issue fechada como concluida",
        _foto(estado="closed", motivo="completed"),
        {"versao_em_producao": "v0.165.0"},
        ETAPA_EM_PRODUCAO,
    ),
    (
        "issue fechada como concluida sem versao gravada",
        _foto(estado="closed", motivo="completed"),
        {"versao_em_producao": None},
        ETAPA_ENTREGUE,
    ),
    (
        "versao gravada e issue fechada sem motivo declarado",
        _foto(estado="closed", motivo=None),
        {"versao_em_producao": "v0.165.0"},
        ETAPA_EM_PRODUCAO,
    ),
    (
        "issue aberta sem label com PR aberto que a fecha",
        _foto(),
        {"pr_aberto": True},
        ETAPA_EM_DESENVOLVIMENTO,
    ),
    (
        "issue aberta sem label e sem PR aberto",
        _foto(),
        {"pr_aberto": False},
        ETAPA_EM_ANALISE,
    ),
]


class TestEmProducaoEPrAberto:
    @pytest.mark.parametrize(
        "caso,foto,fatos,esperada", LINHAS_COM_FATOS_DO_APP, ids=lambda v: v if isinstance(v, str) else ""
    )
    def test_cada_linha_com_fato_do_app(self, caso, foto, fatos, esperada):
        assert etapa_da_foto(foto, **fatos) == esperada

    def test_a_ordem_das_sete_regras_em_escada(self):
        """Em produção > Entregue > Não será feita > Em desenvolvimento >
        Planejada > Em análise > Registrada (PRD #1056).

        Cada degrau tira SO o fato que fazia a regra de cima casar e mantem
        todos os de baixo presentes. Se duas regras vizinhas trocassem de
        lugar, o degrau delas daria a de baixo, e a escada quebra ali."""
        labels_de_baixo = ("in-progress", "ready-for-agent")
        escada = [
            (
                _foto(estado="closed", motivo="completed", labels=labels_de_baixo),
                {"versao_em_producao": "v0.165.0", "pr_aberto": True},
                ETAPA_EM_PRODUCAO,
            ),
            (
                _foto(estado="closed", motivo="completed", labels=labels_de_baixo),
                {"versao_em_producao": None, "pr_aberto": True},
                ETAPA_ENTREGUE,
            ),
            (
                _foto(estado="closed", motivo="not_planned", labels=labels_de_baixo),
                {"versao_em_producao": "v0.165.0", "pr_aberto": True},
                ETAPA_NAO_SERA_FEITA,
            ),
            (
                _foto(labels=labels_de_baixo),
                {"versao_em_producao": "v0.165.0", "pr_aberto": True},
                ETAPA_EM_DESENVOLVIMENTO,
            ),
            (_foto(labels=("ready-for-agent",)), {"versao_em_producao": "v0.165.0"}, ETAPA_PLANEJADA),
            (_foto(), {"versao_em_producao": "v0.165.0"}, ETAPA_EM_ANALISE),
            (None, {"versao_em_producao": "v0.165.0", "pr_aberto": True}, ETAPA_REGISTRADA),
        ]
        assert [esperada for _, _, esperada in escada] == [
            ETAPA_EM_PRODUCAO,
            ETAPA_ENTREGUE,
            ETAPA_NAO_SERA_FEITA,
            ETAPA_EM_DESENVOLVIMENTO,
            ETAPA_PLANEJADA,
            ETAPA_EM_ANALISE,
            ETAPA_REGISTRADA,
        ]
        assert [etapa_da_foto(foto, **fatos) for foto, fatos, _ in escada] == [esperada for _, _, esperada in escada]

    def test_wontfix_ganha_da_versao_gravada(self):
        """A recusa nao vira Em produção so porque uma versao foi gravada: a
        entrega e a mesma `_entregue` da regra Entregue (issue #701)."""
        foto = _foto(estado="closed", motivo="completed", labels=("wontfix",))
        assert etapa_da_foto(foto, versao_em_producao="v0.165.0") == ETAPA_NAO_SERA_FEITA

    def test_pr_aberto_nao_tira_a_recusa_de_issue_aberta(self):
        assert etapa_da_foto(_foto(labels=("wontfix",)), pr_aberto=True) == ETAPA_NAO_SERA_FEITA


class TestMigracaoDaFundacao:
    """A migration unica do PRD #1056 (issue #1057): uma parada humana so.

    O SQL e colado a mao no Studio, entao ele e lido aqui como texto: e o
    unico jeito de o CI ver o que o humano vai aplicar.
    """

    @pytest.fixture
    def sql(self) -> str:
        return MIGRATION_FUNDACAO_1056.read_text(encoding="utf-8")

    def test_cria_a_tabela_de_anexos_com_as_colunas_do_prd(self, sql):
        tabela = re.search(r"CREATE TABLE IF NOT EXISTS tecnologia_anexos \((.*?)\n\);", sql, re.DOTALL)
        assert tabela, "a migration nao cria a tabela tecnologia_anexos"
        linhas = [linha.strip() for linha in tabela.group(1).splitlines()]
        colunas = {linha.split()[0] for linha in linhas if linha and not linha.startswith(("--", "UNIQUE"))}
        assert colunas == {
            "id",
            "demanda_id",
            "ordem",
            "storage_path",
            "nome_original",
            "content_type",
            "tamanho_bytes",
            "anexado_por",
            "criado_em",
            "conversa_id",
            "apagado_em",
        }

    def test_a_tabela_de_anexos_nasce_com_rls_e_sem_policy_solta(self, sql):
        """Default-deny da casa: RLS ligado e nenhuma policy. Toda policy que
        aparecer e precedida do seu DROP, para a reaplicacao ser inofensiva."""
        assert "ALTER TABLE tecnologia_anexos ENABLE ROW LEVEL SECURITY;" in sql
        for criada in re.findall(r'CREATE POLICY "([^"]+)" ON ([\w.]+)', sql):
            nome, alvo = criada
            drop = sql.find(f'DROP POLICY IF EXISTS "{nome}" ON {alvo};')
            assert 0 <= drop < sql.find(f'CREATE POLICY "{nome}" ON {alvo}'), nome

    def test_cria_o_bucket_privado(self, sql):
        assert re.search(
            r"INSERT INTO storage\.buckets \(id, name, public\)\s*"
            r"VALUES \('anexos-tecnologia', 'anexos-tecnologia', false\)",
            sql,
        )

    def test_a_demanda_ganha_a_versao_e_a_data_da_entrega(self, sql):
        assert "ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS versao_em_producao TEXT;" in sql
        assert "ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS entregue_em TIMESTAMPTZ;" in sql

    def test_termina_gravando_o_proprio_numero(self, sql):
        assert sql.rstrip().endswith(
            "INSERT INTO migracoes_aplicadas (numero) VALUES (115) ON CONFLICT (numero) DO NOTHING;"
        )


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
        assert etapa_da_foto(_foto(estado="closed", motivo=None, labels=("wontfix",))) == ETAPA_NAO_SERA_FEITA

    def test_fechada_como_concluida_com_wontfix_e_recusa_e_nao_entrega(self):
        """Issue #701, achado da auditoria do PRD #673. O caminho que produz
        esta foto e o comum: o protocolo nao obriga ninguem a escolher o motivo
        "nao planejada", entao quem marca `wontfix` e clica no botao padrao do
        GitHub fecha como CONCLUIDA. A label e a decisao; o motivo do
        fechamento e so como o botao foi clicado.

        Nao para no selo: Entregue dispara a devolucao a quem pediu, manda a
        Demanda para Aguardando com o autor como responsavel e envia o e-mail
        "Entregue, confira e conclua". O diretor receberia aviso de entrega de
        um pedido que foi recusado."""
        foto = _foto(estado="closed", motivo="completed", labels=("wontfix",))

        assert etapa_da_foto(foto) == ETAPA_NAO_SERA_FEITA

    def test_wontfix_ganha_das_labels_de_andamento_e_de_fila(self):
        """A recusa e a palavra final, mesmo com o `in-progress` preso na issue
        (o caso comum: ninguem tira a label ao fechar) ou com a label da fila."""
        presa = _foto(estado="closed", motivo="completed", labels=("wontfix", "in-progress"))
        na_fila = _foto(estado="closed", motivo="completed", labels=("wontfix", "ready-for-agent"))

        assert etapa_da_foto(presa) == ETAPA_NAO_SERA_FEITA
        assert etapa_da_foto(na_fila) == ETAPA_NAO_SERA_FEITA

    def test_fechada_como_concluida_sem_wontfix_continua_entregue(self):
        """A guarda que nao pode cair junto: fechar e o desfecho normal de uma
        issue que foi feita, com motivo declarado ou sem. Se este teste ficar
        vermelho, a correcao da #701 passou do ponto e o diretor vai ler "Nao
        sera feita" sobre entrega que aconteceu."""
        assert etapa_da_foto(_foto(estado="closed", motivo="completed")) == ETAPA_ENTREGUE
        assert etapa_da_foto(_foto(estado="closed", motivo=None)) == ETAPA_ENTREGUE
        assert etapa_da_foto(_foto(estado="closed", motivo="completed", labels=("in-progress",))) == ETAPA_ENTREGUE

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

    def test_parte_recusada_nao_conta_como_entregue(self):
        """Issue #701, o mesmo defeito da Etapa visto na barra do diretor: uma
        fatia marcada `wontfix` e fechada pelo botao padrao (como concluida)
        entrava na conta de "X de Y partes entregues". A regra e uma so
        (`_entregue`), entao a correcao da raiz tem de aparecer aqui tambem."""
        partes = (
            _parte(674, estado="closed", motivo="completed"),
            _parte(675, estado="closed", motivo="completed", labels=("wontfix",)),
            _parte(676),
        )

        assert partes_da_foto(_foto(partes=partes)) == (1, 3)

        # E com o resumo do GitHub presente, que e o caminho de producao: o
        # `sub_issues_summary` conta a fatia recusada como concluida (o botao
        # padrao fecha como completed), entao o resumo diria 2 de 3 ao lado de
        # uma lista que mostra a parte como "Nao sera feita". Com parte
        # recusada, a conta propria manda.
        com_resumo = _foto(partes=partes, resumo={"total": 3, "entregues": 2})

        assert partes_da_foto(com_resumo) == (1, 3)

    def test_resumo_com_total_zero_conta_como_sem_partes(self):
        assert partes_da_foto(_foto(resumo={"total": 0, "entregues": 0})) == (None, None)


# ─── 1b. O bloco "Para o diretor" (issue #676) ───────────────────────────────

# O corpo de uma issue de verdade, como o `/to-issues` a escreve: cabecalho com
# emoji, o bloco, o separador e o que vem depois dele, que e tecnico.
CORPO_COM_BLOCO = """\
## 👔 Para o diretor

**O que muda:** o card passa a mostrar o que vai mudar para você.

**O que você precisa saber:**
- O texto vem do planejamento da Vitta.
- Ninguém reescreve no app.

---

## Pai

#673

## O que construir

A seção "O que muda", com o extrator do bloco e o cache na Demanda.
"""

BLOCO_ESPERADO = """\
**O que muda:** o card passa a mostrar o que vai mudar para você.

**O que você precisa saber:**
- O texto vem do planejamento da Vitta.
- Ninguém reescreve no app."""


class TestBlocoParaODiretor:
    """O unico texto do GitHub que chega ao diretor (ADR 0054, decisao 7).

    O corte importa dos dois lados: sobrar corpo tecnico coloca numero de issue
    e nome de label na tela dele, e cortar cedo demais o deixa sem o valor da
    entrega.
    """

    def test_o_bloco_sai_inteiro_e_o_tecnico_fica_de_fora(self):
        assert bloco_para_o_diretor(CORPO_COM_BLOCO) == BLOCO_ESPERADO

    def test_o_cabecalho_sem_emoji_tambem_e_reconhecido(self):
        corpo = CORPO_COM_BLOCO.replace("## 👔 Para o diretor", "## Para o diretor")
        assert bloco_para_o_diretor(corpo) == BLOCO_ESPERADO

    def test_sem_separador_o_bloco_vai_ate_o_proximo_cabecalho_de_nivel_2(self):
        """Issue escrita sem o `---`. Sem esta saida, o bloco engoliria o corpo
        tecnico inteiro e o diretor leria "#673" e "area:backend"."""
        corpo = CORPO_COM_BLOCO.replace("\n---\n", "")
        assert bloco_para_o_diretor(corpo) == BLOCO_ESPERADO

    def test_um_item_de_lista_nao_e_confundido_com_o_separador(self):
        """Par de presenca do corte acima: o `-` de um item tem que sobreviver,
        senao o bloco terminaria na primeira linha da lista."""
        bloco = bloco_para_o_diretor(CORPO_COM_BLOCO)
        assert "- O texto vem do planejamento da Vitta." in bloco
        assert "- Ninguém reescreve no app." in bloco

    def test_cabecalho_de_outro_nivel_tambem_serve(self):
        corpo = "### Para o diretor\n\nO card ganha a seção.\n\n## Pai\n\n#673"
        assert bloco_para_o_diretor(corpo) == "O card ganha a seção."

    def test_o_corpo_tecnico_tambem_fecha_o_bloco_em_cabecalho_de_nivel_1(self):
        """O nivel do cabecalho seguinte e convencao do `/to-issues`, e nao
        contrato. Se um dia o "## Pai" virar "# Pai", um recorte que so
        conhecesse o nivel 2 mandaria o corpo tecnico inteiro para a tela do
        diretor, e nada quebraria para avisar."""
        corpo = "## Para o diretor\n\nO card ganha a seção.\n\n# Pai\n\n#673\n\n# O que construir\n\nO extrator."

        assert bloco_para_o_diretor(corpo) == "O card ganha a seção."

    def test_um_subtitulo_dentro_do_bloco_continua_valendo(self):
        """O par de presenca do corte acima: `###` e subtitulo do diretor, e nao
        a volta do corpo tecnico. Fechar nele cortaria o bloco pela metade."""
        corpo = (
            "## Para o diretor\n\nO card ganha a seção.\n\n"
            "### O que você precisa saber\n\nO texto vem da Vitta.\n\n---\n"
        )

        bloco = bloco_para_o_diretor(corpo)

        assert "### O que você precisa saber" in bloco
        assert "O texto vem da Vitta." in bloco

    def test_issue_sem_o_bloco_devolve_nulo(self):
        """Criterio de aceite: e o nulo que a tela traduz em "Descrição em
        preparação", em vez de mostrar o corpo tecnico."""
        assert bloco_para_o_diretor("## O que construir\n\nO extrator do bloco.") is None

    @pytest.mark.parametrize("corpo", (None, "", "   \n  "))
    def test_corpo_vazio_devolve_nulo(self, corpo):
        assert bloco_para_o_diretor(corpo) is None

    def test_cabecalho_sem_nada_embaixo_devolve_nulo(self):
        """Bloco em branco e a mesma coisa que bloco ausente: uma seção vazia na
        tela seria pior do que a frase de "em preparação"."""
        assert bloco_para_o_diretor("## Para o diretor\n\n---\n\n## Pai\n\n#673") is None

    def test_o_marcador_oculto_nao_vaza_para_o_diretor(self):
        """A issue cujo corpo e SO o bloco tem o marcador do Vinculo no fim dele,
        dentro do recorte. Sem a limpeza, o diretor leria
        `<!-- demanda-vitta id="d-1" -->` na tela."""
        corpo = f"## Para o diretor\n\nO card ganha a seção.\n\n{marcador_da_demanda('d-1')}"

        bloco = bloco_para_o_diretor(corpo)

        assert bloco == "O card ganha a seção."
        assert "demanda-vitta" not in bloco

    def test_o_travessao_e_sanitizado_antes_de_gravar(self):
        """Criterio de aceite: o texto vem de fora do app e o diretor o le na
        tela. A regra da casa vale para ele igual."""
        corpo = f"## Para o diretor\n\nO card muda {chr(0x2014)} e o selo aparece.\n\n---\n"

        bloco = bloco_para_o_diretor(corpo)

        assert chr(0x2014) not in bloco
        assert chr(0x2013) not in bloco
        assert bloco == "O card muda, e o selo aparece."


class TestSituacaoDaParte:
    """A situacao de cada parte, que e o selo ao lado do texto dela."""

    @pytest.mark.parametrize(
        "caso,parte,esperada",
        (
            ("fechada como concluida", _parte(675, estado="closed", motivo="completed"), ETAPA_ENTREGUE),
            ("fechada sem motivo declarado", _parte(675, estado="closed", motivo=None), ETAPA_ENTREGUE),
            ("in-progress", _parte(675, labels=("in-progress",)), ETAPA_EM_DESENVOLVIMENTO),
            ("aberta na fila", _parte(675, labels=("ready-for-agent",)), ETAPA_PLANEJADA),
            ("aberta sem label", _parte(675), ETAPA_PLANEJADA),
            (
                "fechada como nao planejada",
                _parte(675, estado="closed", motivo="not_planned"),
                ETAPA_NAO_SERA_FEITA,
            ),
            ("wontfix", _parte(675, labels=("wontfix",)), ETAPA_NAO_SERA_FEITA),
        ),
        ids=lambda v: v if isinstance(v, str) else "",
    )
    def test_cada_situacao(self, caso, parte, esperada):
        assert situacao_da_parte(parte) == esperada

    def test_fechada_com_in_progress_presa_e_entregue(self):
        """A mesma precedencia da raiz: ninguem tira a label ao fechar."""
        parte = _parte(675, estado="closed", motivo="completed", labels=("in-progress",))
        assert situacao_da_parte(parte) == ETAPA_ENTREGUE

    def test_a_situacao_conta_a_mesma_historia_do_x_de_y_partes(self):
        """ "Entregue" nao pode significar duas coisas na mesma tela: a lista de
        partes e o "1 de 2 partes" do selo saem da MESMA regra."""
        partes = (_parte(674, estado="closed", motivo=None), _parte(675))
        foto = _foto(partes=partes)

        entregues, total = partes_da_foto(foto)

        assert (entregues, total) == (1, 2)
        assert [situacao_da_parte(p) for p in partes].count(ETAPA_ENTREGUE) == entregues

    def test_a_parte_recusada_conta_a_mesma_historia_nos_dois_lugares(self):
        """Issue #701, com a parte recusada no meio e o resumo do GitHub
        presente, que e como a foto chega em producao. O selo da parte e a
        conta do card tem de dizer a mesma coisa: se a lista mostra "Nao sera
        feita", a barra nao pode ter somado aquela parte como entregue."""
        partes = (
            _parte(674, estado="closed", motivo="completed"),
            _parte(675, estado="closed", motivo="completed", labels=("wontfix",)),
            _parte(676),
        )
        foto = _foto(partes=partes, resumo={"total": 3, "entregues": 2})

        entregues, total = partes_da_foto(foto)
        situacoes = [situacao_da_parte(p) for p in partes]

        assert (entregues, total) == (1, 3)
        assert situacoes == [ETAPA_ENTREGUE, ETAPA_NAO_SERA_FEITA, ETAPA_PLANEJADA]
        assert situacoes.count(ETAPA_ENTREGUE) == entregues

    def test_a_parte_fechada_como_nao_planejada_tambem_e_recusa(self):
        """As DUAS formas de recusa contam, nao so a label (ADR 0054, decisao
        3: "fechada como nao planejada ou `wontfix`"). A parte fechada com o
        motivo declarado ja aparece como "Nao sera feita" na lista, entao a
        barra tambem nao pode soma-la. Sem este caso, um criterio que lesse so
        a label passaria na suite inteira."""
        partes = (
            _parte(674, estado="closed", motivo="completed"),
            _parte(675, estado="closed", motivo="not_planned"),
            _parte(676),
        )
        foto = _foto(partes=partes, resumo={"total": 3, "entregues": 2})

        assert partes_da_foto(foto) == (1, 3)
        assert situacao_da_parte(partes[1]) == ETAPA_NAO_SERA_FEITA

    def test_a_parte_recusada_ainda_aberta_nao_descarta_o_resumo_do_github(self):
        """A recusa so diverge do GitHub depois que a issue fecha: enquanto ela
        esta aberta, o GitHub tambem nao a conta como concluida. Descartar o
        resumo nesse caso trocaria o numero que a tela do GitHub mostra por
        outro, sem corrigir divergencia nenhuma."""
        partes = (_parte(674, estado="closed", motivo="completed"), _parte(675, labels=("wontfix",)))
        foto = _foto(partes=partes, resumo={"total": 9, "entregues": 4})

        assert partes_da_foto(foto) == (4, 9)

    def test_a_parte_recusada_e_lida_sem_distinguir_maiusculas(self):
        """A guarda nova le a label pelo `_labels`, que normaliza. Trocada por
        um conjunto cru, uma label gravada "WONTFIX" voltaria a contar como
        entrega, e nada aqui ficaria vermelho sem este caso."""
        parte = _parte(675, estado="closed", motivo="completed", labels=("WONTFIX",))

        assert situacao_da_parte(parte) == ETAPA_NAO_SERA_FEITA
        assert partes_da_foto(_foto(partes=(parte,), resumo={"total": 1, "entregues": 1})) == (0, 1)


class TestPartesParaODiretor:
    def test_cada_parte_vira_texto_e_situacao(self):
        foto = _foto(
            partes=(
                dict(_parte(674, estado="closed", motivo="completed"), o_que_muda="O selo aparece no card."),
                dict(_parte(675, labels=("in-progress",)), o_que_muda="A seção mostra o que muda."),
            )
        )

        assert partes_para_o_diretor(foto) == [
            {"numero": 674, "o_que_muda": "O selo aparece no card.", "situacao": ETAPA_ENTREGUE},
            {"numero": 675, "o_que_muda": "A seção mostra o que muda.", "situacao": ETAPA_EM_DESENVOLVIMENTO},
        ]

    def test_parte_sem_bloco_entra_com_texto_nulo(self):
        """Ela nao some da lista: o diretor precisa saber que a parte existe e em
        que pe ela esta, mesmo sem o texto escrito ainda."""
        foto = _foto(partes=(_parte(675),))

        assert partes_para_o_diretor(foto) == [{"numero": 675, "o_que_muda": None, "situacao": ETAPA_PLANEJADA}]

    @pytest.mark.parametrize("foto", (None, _foto()))
    def test_sem_partes_a_lista_e_vazia(self, foto):
        assert partes_para_o_diretor(foto) == []


# ─── 2. O marcador oculto ────────────────────────────────────────────────────

CORPO_ORIGINAL = "## Para o diretor\n\nO selo passa a aparecer no card.\n\n## O que construir\n\nA espinha do Vínculo."


class TestMarcador:
    def test_o_marcador_e_comentario_html(self):
        """Ele vive no corpo de uma issue que gente le: precisa ser invisivel no
        renderizado, e e o `<!-- -->` que garante isso."""
        marcador = marcador_da_demanda("d-1")
        assert marcador.startswith("<!--") and marcador.endswith("-->")


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

    def test_a_frase_do_login_repetido_diz_de_quem_e(self):
        frase = motivo_github_login_repetido("pedro", "Pedro Vitta")
        assert "pedro" in frase
        assert "Pedro Vitta" in frase


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

    def __init__(self, rows: list[dict], nome: str, dono: _SupabaseMock | None = None):
        self._rows = rows
        self._nome = nome
        self._dono = dono
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._is_null: set[str] = set()
        self._insert: list[dict] | None = None
        self._update: dict | None = None
        self._delete = False
        self._order: list[tuple[str, bool]] = []
        self._range: tuple[int, int] | None = None

    def select(self, *_a, **_kw):
        return self

    def order(self, coluna, *, desc: bool = False, **_kw):
        self._order.append((coluna, desc))
        return self

    def range(self, inicio, fim):
        self._range = (inicio, fim)
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def is_(self, coluna, valor):
        """`.is_(coluna, "null")`, o unico jeito de casar NULL no PostgREST.

        O duble so conhece essa forma de proposito: `.eq(coluna, None)` NAO casa
        NULL no PostgREST de verdade, e um duble que aceitasse os dois deixaria
        passar um `.eq` que em producao nao acharia linha nenhuma.
        """
        assert str(valor).lower() == "null", "o dublê só conhece is_(coluna, 'null')"
        self._is_null.add(coluna)
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

    def delete(self):
        """O planejamento da Demanda sai ao encerrar (issue #1345)."""
        self._delete = True
        return self

    def _casa(self, linha: dict) -> bool:
        if not all(linha.get(c) == v for c, v in self._eq.items()):
            return False
        if not all(linha.get(c) is None for c in self._is_null):
            return False
        return all(linha.get(c) in v for c, v in self._in.items())

    def execute(self):
        if self._insert is not None:
            for i, linha in enumerate(self._insert):
                linha.setdefault("id", f"{self._nome}-{len(self._rows) + i + 1}")
                linha.setdefault("criado_em", f"2026-09-10T12:00:{len(self._rows) + i:02d}Z")
            self._rows.extend(self._insert)
            return _Result(data=[dict(linha) for linha in self._insert])

        if self._update is not None and self._dono is not None and self._dono.ao_atualizar is not None:
            # O gancho roda UMA vez, e no instante que interessa: entre a
            # leitura de quem chamou e a escrita dele. E ali que o segundo
            # pedido concorrente precisa entrar para a corrida ser a de verdade
            # (os dois leram antes de qualquer um escrever).
            gancho, self._dono.ao_atualizar = self._dono.ao_atualizar, None
            gancho()

        casadas = [linha for linha in self._rows if self._casa(linha)]

        if self._delete:
            self._rows[:] = [linha for linha in self._rows if not self._casa(linha)]
            return _Result(data=[dict(linha) for linha in casadas])

        if self._update is not None:
            for linha in casadas:
                linha.update(self._update)
            return _Result(data=[dict(linha) for linha in casadas])

        for coluna, desc in reversed(self._order):
            com_valor = [linha for linha in casadas if linha.get(coluna) is not None]
            sem_valor = [linha for linha in casadas if linha.get(coluna) is None]
            com_valor.sort(key=lambda linha, c=coluna: linha.get(c), reverse=desc)
            casadas = com_valor + sem_valor
        if self._range is not None:
            inicio, fim = self._range
            casadas = casadas[inicio : fim + 1]
        return _Result(data=[dict(linha) for linha in casadas])


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas
        # Gancho de uma vez so, disparado antes da PRIMEIRA escrita. Ver o
        # `execute` do `_TableQuery`.
        self.ao_atualizar = None

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []), nome, dono=self)


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

    def __init__(
        self,
        issues: dict[int, dict],
        *,
        sub_issues: dict[int, list[dict]] | None = None,
        erro=None,
        erro_ao_criar=None,
        proximo_numero: int = 900,
        resposta_sem_numero: bool = False,
    ):
        self.issues = issues
        self.sub_issues = sub_issues or {}
        self.erro = erro
        self.erro_ao_criar = erro_ao_criar
        self.proximo_numero = proximo_numero
        self.resposta_sem_numero = resposta_sem_numero
        self.leituras: list[int] = []
        self.criadas: list[dict] = []

    def ler_issue(self, numero: int) -> dict:
        if self.erro is not None:
            raise self.erro
        self.leituras.append(numero)
        if numero not in self.issues:
            raise github_client.IssueNaoEncontradaError(str(numero))
        return self.issues[numero]

    def ler_sub_issues(self, numero: int) -> list[dict]:
        return self.sub_issues.get(numero, [])

    def criar_issue(self, *, titulo: str, corpo: str, labels: list[str], assignees: list[str] | None = None) -> dict:
        """A issue nova, como o GitHub a devolve (issue #677).

        Devolve a issue INTEIRA, e nao so o numero: e dela que a foto e a Etapa
        saem, sem uma segunda leitura.
        """
        if self.erro_ao_criar is not None:
            raise self.erro_ao_criar
        self.criadas.append(
            {"titulo": titulo, "corpo": corpo, "labels": list(labels), "assignees": list(assignees or [])}
        )
        numero = self.proximo_numero
        self.proximo_numero += 1
        dados = _issue(numero, corpo=corpo, labels=tuple(labels))
        dados["title"] = titulo
        if self.resposta_sem_numero:
            dados.pop("number")
            return dados
        self.issues[numero] = dados
        return dados


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

    # `supabase` reaproveita o banco de outra montagem: e o que permite o duplo
    # clique de dois clientes sobre as MESMAS linhas.
    sb = supabase or _SupabaseMock(
        {
            "participantes": pessoas,
            "tecnologia_produtos": [{"id": "prod-1", "nome": "Reuniões", "ativo": True, "ordem": 1, "dono_id": "P1"}],
            "tecnologia_demandas": [dict(d) for d in (demandas or [])],
        }
    )

    gh = github or _GithubFalso({})
    if monkeypatch is not None:
        monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
        monkeypatch.setattr(github_client, "criar_issue", gh.criar_issue)

    async def _usuario() -> dict[str, Any]:
        return {"id": logado["auth_user_id"], "email": logado["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb
    return TestClient(app), sb, gh


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

    def test_criar_issue_esta_trancada(self):
        """O verbo mais caro de todos: um teste que esquecesse de dubla-lo
        abriria uma issue de verdade num repositorio PUBLICO (issue #677)."""
        with pytest.raises(AssertionError, match="chamado de verdade"):
            github_client.criar_issue(titulo="Teste", corpo="Teste", labels=[])


# ─── 4. O "O que muda" que a sincronizacao grava ─────────────────────────────


class TestOQueMudaNaSincronizacao:
    """O cache do "O que muda" (issue #676, ADR 0054, decisao 7).

    O texto vem do GitHub e nunca e digitado no app: quem sincroniza grava o
    bloco da raiz e o de cada parte, e a tela so le o que ficou guardado. A
    gravacao pela sincronizacao mora em `test_tecnologia_webhook_github.py`.
    """

    CORPO_DA_RAIZ = "## 👔 Para o diretor\n\nO card passa a mostrar o que muda.\n\n---\n\n## Pai\n\n#673"
    CORPO_DA_PARTE = "## 👔 Para o diretor\n\nO selo aparece no card.\n\n---\n\n## O que construir\n\nO selo."

    def test_o_corpo_tecnico_da_issue_nao_entra_no_cache(self):
        """O que fica guardado e o bloco, e nao o corpo inteiro: sem isto, o
        cache levaria "#673" e "## O que construir" junto."""
        assert "O que construir" not in self.CORPO_DA_RAIZ.split("---")[0]
        assert bloco_para_o_diretor(self.CORPO_DA_RAIZ) == "O card passa a mostrar o que muda."


# ─── 5. A issue que o "Criar o card" escreve (issues #677 e #1381) ───────────
#
# O caminho INVERSO do resto deste arquivo: aqui o texto que o diretor escreveu
# no app vira o corpo de uma issue de um repositorio PUBLICO. O que se cobra,
# entao, alem do fluxo, e que a primeira coluna do corpo continue sendo do
# backend: nada que o diretor digite pode virar marcador, cabecalho ou
# separador de secao dentro da issue.


class TestLabelsDaIssueNova:
    """A traducao do tipo da Demanda em label do repositorio (issue #677)."""

    def test_defeito_vira_type_fix(self):
        assert labels_da_issue_nova("defeito") == [LABEL_TRIAGEM, "type:fix"]

    @pytest.mark.parametrize("tipo", ("ajuste", "novo"))
    def test_ajuste_e_novo_viram_type_feature(self, tipo):
        assert labels_da_issue_nova(tipo) == [LABEL_TRIAGEM, "type:feature"]

    @pytest.mark.parametrize("tipo", ("decisao", "informacao", "terceiro", "consultoria"))
    def test_os_demais_tipos_nao_ganham_label_de_tipo(self, tipo):
        """Sem label de tipo, e nao com uma inventada: a triagem e humana, e um
        `type:feature` chutado num pedido de Decisao mentiria para quem cura."""
        assert labels_da_issue_nova(tipo) == [LABEL_TRIAGEM]

    def test_a_triagem_entra_sempre(self):
        """`needs-triage` e o contrato do protocolo de triagem: sem ela a issue
        nasce fora da fila de quem cura."""
        for tipo in ("defeito", "ajuste", "novo", "decisao", "consultoria", "tipo-que-nao-existe", ""):
            assert labels_da_issue_nova(tipo)[0] == LABEL_TRIAGEM


class _TransporteGithub:
    """O `httpx.request` do cliente trocado por um gravador (PR #1050).

    O `_GithubFalso` troca o `criar_issue` inteiro e por isso nao ve o JSON que
    sai para o GitHub. Este fica um degrau abaixo: o cliente roda de verdade e
    so a rede e falsa. O POST da issue responde 201; o PATCH que designa
    responde `status_da_designacao` (422 e o que o GitHub da para login que nao
    e assignable no repositorio).
    """

    def __init__(self, *, status_da_designacao: int = 200, numero: int = 900):
        self.status_da_designacao = status_da_designacao
        self.numero = numero
        self.chamadas: list[tuple[str, str, dict | None]] = []

    def __call__(self, metodo, url, *, headers, json, timeout):
        self.chamadas.append((metodo, url, json))
        pedido = httpx.Request(metodo, url)
        # O GitHub recusa o POST INTEIRO quando o assignee que veio nele nao
        # serve; so o POST limpo nasce.
        if metodo == "POST" and "assignees" not in json:
            return httpx.Response(201, json={**_issue(self.numero), "title": json["title"]}, request=pedido)
        return httpx.Response(
            self.status_da_designacao,
            json={"message": "Validation Failed", "errors": [{"field": "assignees"}]},
            request=pedido,
        )


class TestADesignacaoNaoDerrubaACriacao:
    """O assignee e conveniencia: login que o GitHub recusa nao pode virar
    "GitHub indisponivel" no botao (must-fix da revisao do PR #1050)."""

    URL = "https://api.github.com/repos/pedrorezendefig/hospital-reunioes"

    def test_com_login_a_issue_nasce_e_e_designada_pelo_patch(self, monkeypatch):
        transporte = _TransporteGithub()
        monkeypatch.setattr(github_client.httpx, "request", transporte)

        github_client.criar_issue(titulo="T", corpo="C", labels=["needs-triage"], assignees=["lucas-sampaio"])

        assert transporte.chamadas == [
            ("POST", f"{self.URL}/issues", {"title": "T", "body": "C", "labels": ["needs-triage"]}),
            ("PATCH", f"{self.URL}/issues/900", {"assignees": ["lucas-sampaio"]}),
        ]

    def test_sem_login_so_o_post_sai(self, monkeypatch):
        transporte = _TransporteGithub()
        monkeypatch.setattr(github_client.httpx, "request", transporte)

        github_client.criar_issue(titulo="T", corpo="C", labels=["needs-triage"], assignees=[])

        assert transporte.chamadas == [
            ("POST", f"{self.URL}/issues", {"title": "T", "body": "C", "labels": ["needs-triage"]}),
        ]

    def test_assignee_recusado_devolve_a_issue_criada(self, monkeypatch):
        transporte = _TransporteGithub(status_da_designacao=422, numero=901)
        monkeypatch.setattr(github_client.httpx, "request", transporte)

        dados = github_client.criar_issue(titulo="T", corpo="C", labels=[], assignees=["login-errado"])

        assert dados["number"] == 901
        assert [metodo for metodo, _, _ in transporte.chamadas] == ["POST", "PATCH"]


# ─── 6. A rodada de fix do PR #688 (issue #677) ──────────────────────────────


RESUMO_DO_BUG = {
    "titulo": "Rodapé do relatório sai cortado",
    "onde": "Relatório do mês",
    "o_que_aconteceu": "A última linha some",
    "o_que_esperava": "Ver a página inteira",
    "como_repetir": "Imprimir o relatório",
    "criterios": ["A última linha aparece na impressão"],
}


def _corpo_do_bug(**campos) -> str:
    return corpo_da_issue_do_bug(
        demanda_id="d-1",
        resumo={**RESUMO_DO_BUG, **campos},
        produto_nome="Reuniões",
        link="https://app.hsm.com/admin/tecnologia?demanda=d-1",
    )


def _demandas_do_marcador(corpo: str) -> list[str]:
    """Os ids de Demanda que os marcadores do corpo apontam, na ordem."""
    return re.findall(r'<!--\s*demanda-vitta id="([^"]*)"\s*-->', corpo)


class TestDelimitadorPicadoNaoSeRemonta:
    """A remocao COLA os vizinhos, e o que era inofensivo em duas partes vira
    sintaxe em uma.

    Este e o vetor que derrubou a primeira versao do `texto_do_diretor`: com
    "tire `<!--` e tire `-->`" numa passada so, a entrada abaixo saia como um
    marcador PERFEITO, e a issue nova nascia apontando para outra Demanda. O
    escape nao tem como remontar nada, porque a saida nao tem `<` nenhum.
    """

    PICADOS = (
        '<-->!-- demanda-vitta id="ROUBADA" --<!-->',
        "<-->!-- automacao --<!-->",
        '<-->!-- revisor-app autor="Falso" --<!-->',
    )

    @pytest.mark.parametrize("forjado", PICADOS, ids=("demanda-vitta", "automacao", "revisor-app"))
    def test_a_saida_nao_tem_como_abrir_comentario(self, forjado):
        saida = texto_do_diretor(forjado)

        # O marcador positivo: nao sobrou `<` nenhum. Sem ele nao existe
        # comentario HTML para remontar, e a asserção nao depende de eu ter
        # imaginado o formato certo do delimitador.
        assert "<" not in saida
        # E o texto continua legivel: escapar preserva as palavras de quem pediu.
        assert "demanda-vitta" in saida or "automacao" in saida or "revisor-app" in saida

    @pytest.mark.parametrize("forjado", PICADOS, ids=("demanda-vitta", "automacao", "revisor-app"))
    def test_o_corpo_da_issue_continua_apontando_para_esta_demanda(self, forjado):
        corpo = _corpo_do_bug(o_que_aconteceu=forjado)

        assert corpo.count("<!--") == 1
        assert _demandas_do_marcador(corpo) == ["d-1"]

    def test_o_par_de_presenca_o_ataque_montado_de_uma_vez_tambem_nao_passa(self):
        """Sem ele, uma defesa que so conhecesse a forma picada passaria por
        cima da forma direta."""
        corpo = _corpo_do_bug(o_que_aconteceu='<!-- demanda-vitta id="ROUBADA" -->')

        assert corpo.count("<!--") == 1
        assert _demandas_do_marcador(corpo) == ["d-1"]

    @pytest.mark.parametrize(
        "forjado",
        (
            "<!-- automacao -->",
            '<!-- revisor-app autor="Diretor" -->',
            "abre o comentário e nunca fecha <!--",
            "fecha um que ninguém abriu -->",
        ),
        ids=("automacao", "revisor-app", "so-abre", "so-fecha"),
    )
    def test_nenhum_comentario_html_do_diretor_sobrevive(self, forjado):
        """O unico comentario HTML do corpo e o marcador que o backend escreveu.
        Basta contar as ABERTURAS: comentario nenhum comeca sem `<!--`."""
        corpo = _corpo_do_bug(onde=f"Antes {forjado} depois")

        assert corpo.count("<!--") == 1
        assert _demandas_do_marcador(corpo) == ["d-1"]
        assert "Antes" in corpo and "depois" in corpo

    def test_escapar_e_idempotente(self):
        """Duas passadas dao o mesmo texto: `&lt;` nao tem `<` para escapar de
        novo, e a linha ja neutralizada comeca por barra invertida. Sem isto, o
        titulo (que passa pela peneira na rota e de novo dentro do corpo) sairia
        escapado duas vezes."""
        uma_vez = texto_do_diretor("Um <!-- teste --> e um ## título")

        assert texto_do_diretor(uma_vez) == uma_vez


class TestQuebraDeLinhaDeOutroSistema:
    """CRLF e o que chega de um e-mail ou de um Word colado no campo.

    O `_FIM_DO_BLOCO` da LEITURA aceita `\\s*$` (e `\\r` e espaco), entao um
    `---\\r\\n` seria separador para ele; a neutralizacao casa `[ \\t]*$` e nao
    o via. Os dois lados precisam enxergar a mesma linha.
    """

    def test_separador_com_crlf_sai_neutralizado(self):
        """O `---` na coluna zero fecharia o bloco do diretor na leitura de
        volta. Com CRLF ele tem que ser visto e desligado do mesmo jeito."""
        assert texto_do_diretor("Linha uma\r\n---\r\nLinha duas") == "Linha uma\n\\---\nLinha duas"

    def test_cabecalho_com_crlf_nao_fabrica_secao(self):
        """Um "## Origem" na coluna zero fabricaria uma segunda Origem."""
        assert texto_do_diretor("Some a linha.\r\n## Origem\r\nfim") == "Some a linha.\n\\## Origem\nfim"

    def test_cr_sozinho_tambem_vira_quebra_normal(self):
        """O `\\r` sozinho e o fim de linha do Mac antigo, e ainda sai de alguns
        editores. Deixar um `\\r` cru no corpo poria a linha seguinte por cima
        desta em qualquer terminal que leia a issue."""
        assert "\r" not in texto_do_diretor("Linha uma\r---\rLinha duas")
