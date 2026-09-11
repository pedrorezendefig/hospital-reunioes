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
from datetime import UTC, datetime
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
from app.services.tecnologia import (  # noqa: E402
    MARCA_FIM_CONVERSA,
    MARCA_INICIO_CONVERSA,
    RECUO_DA_CONTINUACAO,
)
from app.services.tecnologia_email import link_da_demanda  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_ENTREGUE,
    ETAPA_NAO_SERA_FEITA,
    ETAPA_PLANEJADA,
    ETAPA_REGISTRADA,
    ETAPA_ROTULO,
    ETAPAS,
    LABEL_TRIAGEM,
    MOTIVO_CRIACAO_EM_ANDAMENTO,
    MOTIVO_GITHUB_INDISPONIVEL,
    MOTIVO_INTEGRACAO_DESLIGADA,
    MOTIVO_LOGIN_INVALIDO,
    MOTIVO_NUMERO_INVALIDO,
    MOTIVO_SEM_GITHUB_LOGIN,
    MOTIVO_SEM_VINCULO_PARA_DESFAZER,
    TEXTO_VINCULO_CRIADO,
    TEXTO_VINCULO_DESFEITO,
    bloco_para_o_diretor,
    corpo_com_marcador,
    corpo_da_issue_nova,
    corpo_precisa_do_marcador,
    demanda_id_do_marcador,
    etapa_da_foto,
    foto_mudou,
    labels_da_issue_nova,
    marcador_da_demanda,
    motivo_demanda_ja_vinculada,
    motivo_e_pull_request,
    motivo_github_login_invalido,
    motivo_github_login_repetido,
    motivo_issue_inexistente,
    motivo_ja_vinculada_para_levar,
    motivo_numero_ja_usado,
    normalizar_github_login,
    partes_da_foto,
    partes_para_o_diretor,
    situacao_da_parte,
    tem_github_login,
    texto_do_diretor,
    texto_levou_para_desenvolvimento,
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


class TestTextoDasPartes:
    def test_o_texto_das_partes(self):
        assert texto_partes(3, 7) == "3 de 7 partes"

    @pytest.mark.parametrize("entregues,total", ((None, None), (3, None), (None, 7), (0, 0)))
    def test_sem_partes_o_texto_e_vazio(self, entregues, total):
        assert texto_partes(entregues, total) == ""


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
        """A issue cujo corpo e SO o bloco recebe o marcador do Vinculo no fim
        dele (`corpo_com_marcador`), dentro do recorte. Sem a limpeza, o diretor
        leria `<!-- demanda-vitta id="d-1" -->` na tela."""
        corpo = corpo_com_marcador("## Para o diretor\n\nO card ganha a seção.", "d-1")

        bloco = bloco_para_o_diretor(corpo)

        assert bloco == "O card ganha a seção."
        assert "demanda-vitta" not in bloco

    def test_o_travessao_e_sanitizado_antes_de_gravar(self):
        """Criterio de aceite: o texto vem de fora do app e o diretor o le na
        tela e no "Copiar para IA". A regra da casa vale para ele igual."""
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

    def __init__(self, rows: list[dict], nome: str, dono: _SupabaseMock | None = None):
        self._rows = rows
        self._nome = nome
        self._dono = dono
        self._eq: dict[str, Any] = {}
        self._in: dict[str, list] = {}
        self._is_null: set[str] = set()
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
        erro_ao_comentar=None,
    ):
        self.issues = issues
        self.sub_issues = sub_issues or {}
        self.erro = erro
        self.erro_ao_criar = erro_ao_criar
        self.erro_ao_comentar = erro_ao_comentar
        self.proximo_numero = proximo_numero
        self.resposta_sem_numero = resposta_sem_numero
        self.corpos_escritos: list[tuple[int, str]] = []
        self.leituras: list[int] = []
        self.criadas: list[dict] = []
        # Os comentarios espelhados (issue #680): o que foi publicado e o que
        # foi editado, com o id que o GitHub "deu" a cada um.
        self.comentarios_criados: list[dict] = []
        self.comentarios_editados: list[dict] = []
        self.proximo_comentario_id = 3_000_000_001

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

    def criar_issue(self, *, titulo: str, corpo: str, labels: list[str]) -> dict:
        """A issue nova, como o GitHub a devolve (issue #677).

        Devolve a issue INTEIRA, e nao so o numero: e dela que a foto e a Etapa
        saem, sem uma segunda leitura.
        """
        if self.erro_ao_criar is not None:
            raise self.erro_ao_criar
        self.criadas.append({"titulo": titulo, "corpo": corpo, "labels": list(labels)})
        numero = self.proximo_numero
        self.proximo_numero += 1
        dados = _issue(numero, corpo=corpo, labels=tuple(labels))
        dados["title"] = titulo
        if self.resposta_sem_numero:
            dados.pop("number")
            return dados
        self.issues[numero] = dados
        return dados

    def criar_comentario(self, numero: int, corpo: str) -> int:
        """Publica o comentario e devolve o id, como o GitHub (issue #680).

        Ids acima de 2^31 de proposito: e o tamanho real do id de comentario
        do GitHub hoje, e um `INTEGER` no banco o recusaria.
        """
        if self.erro_ao_comentar is not None:
            raise self.erro_ao_comentar
        comentario_id = self.proximo_comentario_id
        self.proximo_comentario_id += 1
        self.comentarios_criados.append({"numero": numero, "corpo": corpo, "id": comentario_id})
        return comentario_id

    def editar_comentario(self, comentario_id: int, corpo: str) -> None:
        if self.erro_ao_comentar is not None:
            raise self.erro_ao_comentar
        self.comentarios_editados.append({"id": comentario_id, "corpo": corpo})


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
        monkeypatch.setattr(github_client, "criar_issue", gh.criar_issue)
        monkeypatch.setattr(github_client, "criar_comentario", gh.criar_comentario)
        monkeypatch.setattr(github_client, "editar_comentario", gh.editar_comentario)

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

    def test_criar_issue_esta_trancada(self):
        """O verbo mais caro de todos: um teste que esquecesse de dubla-lo
        abriria uma issue de verdade num repositorio PUBLICO (issue #677)."""
        with pytest.raises(AssertionError, match="chamado de verdade"):
            github_client.criar_issue(titulo="Teste", corpo="Teste", labels=[])


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


class TestOQueMudaNaSincronizacao:
    """O cache do "O que muda" (issue #676, ADR 0054, decisao 7).

    O texto vem do GitHub e nunca e digitado no app: quem sincroniza grava o
    bloco da raiz e o de cada parte, e a tela so le o que ficou guardado.
    """

    CORPO_DA_RAIZ = "## 👔 Para o diretor\n\nO card passa a mostrar o que muda.\n\n---\n\n## Pai\n\n#673"
    CORPO_DA_PARTE = "## 👔 Para o diretor\n\nO selo aparece no card.\n\n---\n\n## O que construir\n\nO selo."

    def _github(self):
        return _GithubFalso(
            {673: _issue(673, corpo=self.CORPO_DA_RAIZ, labels=("ready-for-agent",))},
            sub_issues={
                673: [
                    _issue(674, corpo=self.CORPO_DA_PARTE, estado="closed", motivo="completed"),
                    _issue(675, corpo=None, labels=("in-progress",)),
                ]
            },
        )

    def test_sincronizar_grava_o_bloco_da_raiz_e_a_lista_de_partes(self, monkeypatch):
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=self._github(), monkeypatch=monkeypatch)

        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["o_que_muda"] == "O card passa a mostrar o que muda."
        assert corpo["partes"] == [
            {"numero": 674, "o_que_muda": "O selo aparece no card.", "situacao": ETAPA_ENTREGUE},
            {"numero": 675, "o_que_muda": None, "situacao": ETAPA_EM_DESENVOLVIMENTO},
        ]
        gravada = sb.tabelas["tecnologia_demandas"][0]
        assert gravada["o_que_muda"] == "O card passa a mostrar o que muda."
        assert [parte["situacao"] for parte in gravada["partes"]] == [ETAPA_ENTREGUE, ETAPA_EM_DESENVOLVIMENTO]

    def test_o_corpo_tecnico_da_issue_nao_entra_no_cache(self):
        """O par negativo do teste acima, no MESMO dado: o que fica guardado e o
        bloco, e nao o corpo inteiro. Sem ele, "grava o texto" ficaria verde
        sobre uma gravacao que leva "#673" e "## O que construir" junto."""
        assert "O que construir" not in self.CORPO_DA_RAIZ.split("---")[0]
        assert bloco_para_o_diretor(self.CORPO_DA_RAIZ) == "O card passa a mostrar o que muda."

    def test_issue_sem_o_bloco_grava_nulo(self, monkeypatch):
        """Criterio de aceite: nulo, e nao o corpo tecnico. E o nulo que a tela
        traduz em "Descrição em preparação"."""
        client, sb, _ = _montar(
            demandas=[_demanda("d-1")],
            github=_GithubFalso({673: _issue(673, corpo="## O que construir\n\nA seção O que muda.")}),
            monkeypatch=monkeypatch,
        )

        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["o_que_muda"] is None
        assert sb.tabelas["tecnologia_demandas"][0]["o_que_muda"] is None
        # Par de presenca: o resto da sincronizacao aconteceu, entao o nulo e
        # sobre o bloco ausente, e nao sobre uma rota que nao gravou nada.
        assert corpo["etapa"] == ETAPA_EM_ANALISE

    def test_editar_o_bloco_no_github_muda_o_cache_na_sincronizacao_seguinte(self, monkeypatch):
        """Criterio de aceite: a foto guardada tem que ENXERGAR a edicao do
        bloco. Uma foto que so olhasse label e fechamento acharia que nada mudou
        e deixaria o diretor lendo o texto velho para sempre."""
        gh = self._github()
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673})
        foto_antiga = dict(sb.tabelas["tecnologia_demandas"][0]["github_foto"])

        gh.issues[673]["body"] = self.CORPO_DA_RAIZ.replace(
            "O card passa a mostrar o que muda.", "O card mostra também as partes."
        )
        corpo = client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).json()

        assert corpo["o_que_muda"] == "O card mostra também as partes."
        nova = sb.tabelas["tecnologia_demandas"][0]["github_foto"]
        assert foto_mudou(foto_antiga, nova) is True


class TestOQueMudaEODiretor:
    """A superficie mais larga do app: o texto sai dele e vai para uma IA de
    fora (ADR 0054, decisao 9). O numero interno da parte fica atras do login.
    """

    DEMANDA = dict(
        github_issue_numero=673,
        etapa=ETAPA_EM_DESENVOLVIMENTO,
        partes_entregues=1,
        partes_total=2,
        o_que_muda="O card passa a mostrar o que muda.",
        partes=[
            {"numero": 674, "o_que_muda": "O selo aparece no card.", "situacao": ETAPA_ENTREGUE},
            {"numero": 675, "o_que_muda": "A seção mostra as partes.", "situacao": ETAPA_EM_DESENVOLVIMENTO},
        ],
        github_foto=_foto(),
    )

    def test_quem_e_da_vitta_ve_o_numero_interno_da_parte(self, monkeypatch):
        client, _, _ = _montar(logado=PEDRO, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert [parte["numero"] for parte in corpo["partes"]] == [674, 675]

    def test_o_diretor_nao_ve_o_numero_da_parte(self, monkeypatch):
        """A asserção e sobre o MARCADOR: o campo veio nulo. "674 nao esta na
        resposta" seria cega a qualquer outra forma de escrever o numero."""
        client, _, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert [parte["numero"] for parte in corpo["partes"]] == [None, None]

    def test_o_diretor_continua_vendo_o_texto_e_a_situacao_de_cada_parte(self, monkeypatch):
        """O par de presenca da omissao acima: sem ele, uma resposta que nao
        mandasse parte NENHUMA passaria pelo teste do numero nulo."""
        client, _, _ = _montar(logado=DIRETOR, demandas=[_demanda("d-1", **self.DEMANDA)], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["o_que_muda"] == "O card passa a mostrar o que muda."
        assert [parte["o_que_muda"] for parte in corpo["partes"]] == [
            "O selo aparece no card.",
            "A seção mostra as partes.",
        ]
        assert [parte["situacao"] for parte in corpo["partes"]] == [ETAPA_ENTREGUE, ETAPA_EM_DESENVOLVIMENTO]

    @classmethod
    def _demanda_que_a_lista_mostra(cls, caminho: str, quem: str) -> dict:
        """A Demanda no estado que CADA lista mostra.

        Uma so nao serve as tres: "Minha vez" traz apenas as abertas de quem
        esta logado, e o Historico apenas as fechadas. Sem isto, a varredura
        passaria sobre uma lista vazia, que e o vacuo classico.
        """
        campos = dict(cls.DEMANDA, responsavel_id=quem)
        if caminho != "/historico":
            return _demanda("d-1", estado="em_andamento", **campos)
        return _demanda("d-1", estado="concluida", concluida_em="2026-09-09T10:00:00Z", concluida_por=quem, **campos)

    @pytest.mark.parametrize("caminho", ("/demandas", "/minha-vez", "/historico"))
    def test_a_omissao_do_numero_da_parte_vale_em_toda_lista(self, caminho, monkeypatch):
        """A regra mora no funil por onde TODA Demanda sai da API, e nao na rota
        que este teste chama. As tres listas, porque sao tres rotas."""
        client, _, _ = _montar(
            logado=DIRETOR,
            demandas=[self._demanda_que_a_lista_mostra(caminho, "P2")],
            monkeypatch=monkeypatch,
        )

        corpo = client.get(f"{BASE}{caminho}").json()

        assert corpo, f"{caminho} devolveu lista vazia: o teste ficaria verde sobre nada"
        for demanda in corpo:
            assert [parte["numero"] for parte in demanda["partes"]] == [None, None]
            # O par de presenca dentro da varredura: a parte chegou inteira,
            # so sem o numero.
            assert [parte["situacao"] for parte in demanda["partes"]] == [
                ETAPA_ENTREGUE,
                ETAPA_EM_DESENVOLVIMENTO,
            ]

    @pytest.mark.parametrize("caminho", ("/demandas", "/minha-vez", "/historico"))
    def test_o_par_de_presenca_da_omissao_em_toda_lista(self, caminho, monkeypatch):
        """Sem ele, uma resposta que NUNCA trouxesse o numero passaria pela
        varredura acima nas tres rotas."""
        client, _, _ = _montar(
            logado=PEDRO,
            demandas=[self._demanda_que_a_lista_mostra(caminho, "P1")],
            monkeypatch=monkeypatch,
        )

        corpo = client.get(f"{BASE}{caminho}").json()

        assert corpo, f"{caminho} devolveu lista vazia: o teste ficaria verde sobre nada"
        for demanda in corpo:
            assert [parte["numero"] for parte in demanda["partes"]] == [674, 675]

    def test_demanda_sem_vinculo_nao_tem_o_que_muda_nem_partes(self, monkeypatch):
        client, _, _ = _montar(logado=PEDRO, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        corpo = client.get(f"{BASE}/demandas").json()[0]

        assert corpo["o_que_muda"] is None
        assert corpo["partes"] == []


class TestOQueMudaNoTextoParaIa:
    """O "Copiar para IA" leva a Etapa e o "O que muda" (issue #676).

    Ele e a superficie que SAI do app: o diretor cola o texto numa ferramenta de
    fora. Nada de numero de issue, link ou label pode viajar junto.
    """

    def _texto(self, quem: dict, monkeypatch, **campos) -> str:
        client, _, _ = _montar(
            logado=quem,
            demandas=[_demanda("d-1", **dict(TestOQueMudaEODiretor.DEMANDA, **campos))],
            monkeypatch=monkeypatch,
        )
        return client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

    def test_a_etapa_e_o_que_muda_entram_entre_a_descricao_e_a_conversa(self, monkeypatch):
        texto = self._texto(DIRETOR, monkeypatch)

        assert "Etapa: Em desenvolvimento (1 de 2 partes)" in texto
        assert "O card passa a mostrar o que muda." in texto
        assert texto.index("Descrição:") < texto.index("Etapa:") < texto.index("Conversa:")

    def test_cada_parte_entra_com_a_situacao_dela(self, monkeypatch):
        texto = self._texto(DIRETOR, monkeypatch)

        assert "- (Entregue) O selo aparece no card." in texto
        assert "- (Em desenvolvimento) A seção mostra as partes." in texto

    def test_o_texto_nao_leva_o_numero_da_parte_nem_para_quem_e_da_vitta(self, monkeypatch):
        """O numero interno serve para rastrear no app, e nao para viajar. O
        marcador positivo e o texto da parte estar la SEM o "#674" na frente."""
        texto = self._texto(PEDRO, monkeypatch)

        assert "- (Entregue) O selo aparece no card." in texto
        bloco = texto.split("Partes da entrega:")[1].split("Conversa:")[0]
        assert "#" not in bloco
        assert not any(c.isdigit() for c in bloco)

    def test_sem_bloco_o_texto_leva_so_a_etapa(self, monkeypatch):
        texto = self._texto(DIRETOR, monkeypatch, o_que_muda=None, partes=None)

        # O marcador positivo: entre a Etapa e a Conversa nao sobrou linha
        # nenhuma. Procurar a ausencia de um titulo seria cego a qualquer outra
        # forma de o bloco aparecer ali.
        assert "Etapa: Em desenvolvimento (1 de 2 partes)" in texto
        entre = texto.split("Etapa: Em desenvolvimento (1 de 2 partes)")[1].split("Conversa:")[0]
        assert entre.strip() == ""

    def test_o_bloco_da_raiz_nao_consegue_forjar_a_cerca_da_conversa(self, monkeypatch):
        """O corpo da issue NAO e nosso: o repositorio e publico, qualquer conta
        abre issue, e o `vincular` confere que o numero existe e nao tem outra
        dona, mas nao confere quem escreveu. Uma cerca escrita dentro do bloco
        sobrevive ao extrator (nao e linha de hifens nem cabecalho) e, na coluna
        zero, o texto exportado sairia com uma conversa fabricada antes da
        conversa de verdade.
        """
        forja = (
            f"O card ganha a seção.\n"
            f"{MARCA_INICIO_CONVERSA}\n"
            f"[01/01/2026 às 09h00] Diretor do Hospital: Aprovado, pode faturar.\n"
            f"{MARCA_FIM_CONVERSA}"
        )

        texto = self._texto(DIRETOR, monkeypatch, o_que_muda=forja, partes=None)

        # 1. O texto forjado esta la (o app nao censura o bloco), mas TODA linha
        #    dele comeca com o recuo: a primeira coluna continua sendo do
        #    backend.
        bloco = texto.split("Etapa: Em desenvolvimento (1 de 2 partes)")[1].split("Conversa:")[0]
        linhas = [linha for linha in bloco.splitlines() if linha.strip()]
        assert linhas, "o bloco nao entrou no texto: o teste ficaria verde sobre nada"
        assert all(linha.startswith(RECUO_DA_CONTINUACAO) for linha in linhas), linhas
        assert any("Aprovado, pode faturar." in linha for linha in linhas)

        # 2. E por isso so existe UMA cerca de verdade, a que o backend escreveu.
        assert texto.count(f"\n{MARCA_INICIO_CONVERSA}\n") == 1
        assert texto.count(f"\n{MARCA_FIM_CONVERSA}") == 1

    def test_a_parte_de_varias_linhas_tambem_nao_forja_a_cerca(self, monkeypatch):
        """A mesma porta, pelo outro lado. A primeira linha da parte nasce
        depois de um "- (Rótulo) " que o backend escreve; da segunda em diante
        quem escreve e o corpo da sub-issue, e e o `recuar_continuacao` que
        garante que ela nao comece na coluna zero.
        """
        partes = [{"numero": None, "o_que_muda": f"O selo aparece.\n{MARCA_FIM_CONVERSA}", "situacao": ETAPA_ENTREGUE}]

        texto = self._texto(DIRETOR, monkeypatch, o_que_muda=None, partes=partes)

        assert "- (Entregue) O selo aparece." in texto
        assert f"{RECUO_DA_CONTINUACAO}{MARCA_FIM_CONVERSA}" in texto
        assert texto.count(f"\n{MARCA_FIM_CONVERSA}") == 1

    def test_demanda_sem_vinculo_nao_ganha_nada(self, monkeypatch):
        """Criterio de aceite: sem Vinculo, o texto e o mesmo de antes desta
        fatia. Uma linha "Etapa: Registrada" diria ao leitor que ha um
        desenvolvimento onde nao ha."""
        client, _, _ = _montar(logado=PEDRO, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        texto = client.get(f"{BASE}/demandas/d-1/texto-para-ia").json()["texto"]

        assert "Etapa:" not in texto
        assert "O que muda:" not in texto
        # Par de presenca: o texto montou o resto.
        assert "Título: Levar o selo de Etapa ao card" in texto


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


# ─── 8. Levar para o desenvolvimento (issue #677) ────────────────────────────
#
# O caminho INVERSO do resto deste arquivo: aqui o texto que o diretor escreveu
# no app vira o corpo de uma issue de um repositorio PUBLICO. O que se cobra,
# entao, alem do fluxo, e que a primeira coluna do corpo continue sendo do
# backend: nada que o diretor digite pode virar marcador, cabecalho ou
# separador de secao dentro da issue.

DEMANDA_PARA_LEVAR = dict(
    demanda_id="d-1",
    titulo="Rodapé do relatório sai cortado",
    descricao="Quando eu imprimo o relatório do mês, a última linha some.",
    tipo_rotulo="Defeito",
    produto_nome="Ana",
    levado_por_login="pedrorezendefig",
    link="https://app.hsm.com/admin/tecnologia?demanda=d-1",
)

# A secao Origem inteira, como ela tem que sair. Escrita a mao, e comparada por
# IGUALDADE: o criterio desta rodada e o que a issue publica NAO pode carregar,
# e "o nome nao aparece" e cego a variacao de forma (sobrenome sozinho, nome no
# meio de uma frase, nome dentro do link). Comparar a secao inteira diz o que
# pode estar la, que e a unica forma de dizer que o resto nao pode.
ORIGEM_ESPERADA = (
    "## Origem\n"
    "\n"
    "Pedido registrado na aba Tecnologia do aplicativo do hospital, "
    "levado para o desenvolvimento por @pedrorezendefig.\n"
    "Abrir a Demanda: https://app.hsm.com/admin/tecnologia?demanda=d-1"
)


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


class TestCorpoDaIssueNova:
    def test_o_bloco_do_diretor_traz_a_descricao_dele(self):
        corpo = corpo_da_issue_nova(**DEMANDA_PARA_LEVAR)

        bloco = bloco_para_o_diretor(corpo)
        assert "a última linha some" in bloco
        # O bloco vai INTEIRO ate o separador: o tipo e o Produto sao as duas
        # linhas do "O que voce precisa saber" que a issue pede.
        assert "Defeito" in bloco
        assert "Ana" in bloco

    def test_sem_descricao_o_titulo_ocupa_o_lugar(self):
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": None})

        assert "Rodapé do relatório sai cortado" in bloco_para_o_diretor(corpo)

    @pytest.mark.parametrize("vazia", ("", "   ", "\n\n"))
    def test_descricao_em_branco_tambem_cai_no_titulo(self, vazia):
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": vazia})

        assert "Rodapé do relatório sai cortado" in bloco_para_o_diretor(corpo)

    def test_a_origem_e_o_link_mais_o_login_de_quem_levou(self):
        """A secao inteira, por igualdade: e assim que se diz o que PODE estar
        la, e portanto que nome civil nenhum esta."""
        corpo = corpo_da_issue_nova(**DEMANDA_PARA_LEVAR)

        assert ORIGEM_ESPERADA in corpo

    def test_sem_login_valido_a_origem_fica_so_com_o_link(self):
        """Linha antiga, cadastro anterior a validacao: um `@` grudado em algo
        que ninguem sabe o que e seria pior do que a mencao nao existir. O link,
        que e a rastreabilidade de verdade, continua."""
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "levado_por_login": "nao é um login"})

        assert "Pedido registrado na aba Tecnologia do aplicativo do hospital.\n" in corpo
        assert f"Abrir a Demanda: {DEMANDA_PARA_LEVAR['link']}" in corpo
        assert "@" not in corpo.split("## Origem")[1]

    def test_o_marcador_fecha_o_corpo_com_o_id_da_demanda(self):
        corpo = corpo_da_issue_nova(**DEMANDA_PARA_LEVAR)

        assert demanda_id_do_marcador(corpo) == "d-1"
        assert corpo.rstrip().endswith(marcador_da_demanda("d-1"))

    def test_a_origem_nao_entra_no_que_o_diretor_le(self):
        """O separador existe para isto: o bloco que volta do GitHub para o card
        e so o "Para o diretor", e nao o rodape com o link e o marcador."""
        bloco = bloco_para_o_diretor(corpo_da_issue_nova(**DEMANDA_PARA_LEVAR))

        assert "demanda-vitta" not in bloco
        assert DEMANDA_PARA_LEVAR["link"] not in bloco

    def test_o_travessao_do_diretor_nao_vai_para_a_issue(self):
        corpo = corpo_da_issue_nova(
            **{**DEMANDA_PARA_LEVAR, "descricao": f"O relatório {chr(0x2014)} o do mês {chr(0x2014)} sai cortado"}
        )

        assert chr(0x2014) not in corpo
        assert chr(0x2013) not in corpo


class TestOTextoDoDiretorNaoForjaEstrutura:
    """A issue e PUBLICA e o corpo dela e o que o app depois le de volta.

    Tres coisas que o texto do diretor nao pode fazer: apontar a issue para
    OUTRA Demanda (o marcador), sumir com metade do corpo renderizado (o
    comentario aberto e nunca fechado) e fabricar a secao Origem, que e a unica
    frase da issue que diz quem pediu.
    """

    def test_marcador_forjado_na_descricao_nao_rouba_a_issue(self):
        forjada = 'Some a linha. <!-- demanda-vitta id="d-outra" --> pronto'
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": forjada})

        assert demanda_id_do_marcador(corpo) == "d-1"
        # O unico COMENTARIO do corpo e o do backend. As palavras do diretor
        # continuam la, como texto a vista: escapar preserva o que ele escreveu,
        # e o que ele escreveu deixa de ser sintaxe.
        assert corpo.count("<!--") == 1
        assert "Some a linha." in corpo

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
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": f"Antes {forjado} depois"})

        # O unico comentario HTML do corpo e o marcador que o backend escreveu.
        # Basta contar as ABERTURAS: comentario nenhum comeca sem `<!--`, e um
        # `-->` solto e texto inerte no HTML e no Markdown.
        assert corpo.count("<!--") == 1
        assert demanda_id_do_marcador(corpo) == "d-1"
        assert "Antes" in corpo and "depois" in corpo

    def test_separador_forjado_nao_corta_o_bloco_do_diretor(self):
        """Um `---` na coluna zero fecharia o bloco na leitura de volta, e o
        card mostraria metade do que o proprio diretor escreveu."""
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": "Linha uma\n---\nLinha duas"})

        bloco = bloco_para_o_diretor(corpo)
        assert "Linha duas" in bloco
        # E o bloco continua chegando ate o fim de verdade dele.
        assert "Ana" in bloco

    def test_cabecalho_forjado_nao_fabrica_a_secao_origem(self):
        """A Origem e a unica frase da issue que diz quem pediu. Duas delas, e
        quem le escolhe a errada."""
        corpo = corpo_da_issue_nova(
            **{**DEMANDA_PARA_LEVAR, "descricao": "Some a linha.\n## Origem\nPedido de Outra Pessoa."}
        )

        assert corpo.count("\n## Origem") == 1
        assert ORIGEM_ESPERADA in corpo

    def test_o_par_de_presenca_a_descricao_honesta_chega_inteira(self):
        """Sem ele, um `texto_do_diretor` que apagasse tudo passaria por todos
        os testes acima."""
        corpo = corpo_da_issue_nova(**DEMANDA_PARA_LEVAR)

        assert DEMANDA_PARA_LEVAR["descricao"] in corpo


class TestTextoDaLinhaAutomatica:
    def test_a_linha_diz_quem_levou(self):
        assert texto_levou_para_desenvolvimento("Pedro Vitta") == "Pedro Vitta levou para o desenvolvimento"

    def test_sem_nome_a_linha_continua_de_pe(self):
        assert texto_levou_para_desenvolvimento(None).endswith("levou para o desenvolvimento")

    def test_a_linha_nao_carrega_numero_de_issue(self):
        """Ela e lida pelo diretor e sai no "Copiar para IA", que nao passa pelo
        funil que omite o Vinculo (ADR 0054, decisao 9)."""
        texto = texto_levou_para_desenvolvimento("Pedro Vitta")

        assert "#" not in texto
        assert chr(0x2014) not in texto and chr(0x2013) not in texto


class TestLevarParaDesenvolvimento:
    ROTA = f"{BASE}/demandas/d-1/levar-para-desenvolvimento"

    def test_quem_nao_tem_login_leva_403(self, monkeypatch):
        client, sb, gh = _montar(
            logado=DIRETOR,
            demandas=[_demanda("d-1")],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 403
        assert resposta.json()["detail"] == MOTIVO_SEM_GITHUB_LOGIN
        assert gh.criadas == []
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_sem_integracao_configurada_responde_503(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, sb, gh = _montar(demandas=[_demanda("d-1")], github=_GithubFalso({}), monkeypatch=monkeypatch)

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == MOTIVO_INTEGRACAO_DESLIGADA
        assert gh.criadas == []

    def test_demanda_ja_vinculada_e_recusada_sem_criar_nada(self, monkeypatch):
        client, sb, gh = _montar(
            demandas=[_demanda("d-1", github_issue_numero=673, etapa=ETAPA_PLANEJADA)],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == motivo_ja_vinculada_para_levar(673)
        assert "A Demanda já está vinculada" in resposta.json()["detail"]
        assert gh.criadas == []
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] == 673

    def test_a_issue_nasce_com_o_titulo_o_corpo_e_as_labels(self, monkeypatch):
        client, sb, gh = _montar(
            demandas=[
                _demanda(
                    "d-1",
                    titulo="Rodapé do relatório sai cortado",
                    descricao="A última linha some quando imprimo.",
                    tipo="defeito",
                    autor_id="P2",
                )
            ],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 200, resposta.text
        assert len(gh.criadas) == 1
        criada = gh.criadas[0]
        assert criada["titulo"] == "Rodapé do relatório sai cortado"
        assert criada["labels"] == [LABEL_TRIAGEM, "type:fix"]
        assert "A última linha some quando imprimo." in criada["corpo"]
        # O par dos dois lados: a issue carrega o id da Demanda.
        assert demanda_id_do_marcador(criada["corpo"]) == "d-1"
        # E a Origem sai com o login de quem levou, sem nome de gente.
        assert "levado para o desenvolvimento por @pedrorezendefig." in criada["corpo"]

    def test_a_demanda_fica_vinculada_ao_numero_devolvido(self, monkeypatch):
        gh = _GithubFalso({}, proximo_numero=901)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        corpo = client.post(self.ROTA).json()

        assert corpo["vinculo"]["numero"] == 901
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] == 901

    def test_a_etapa_nasce_em_analise(self, monkeypatch):
        """Derivada da label `needs-triage` que a issue acabou de ganhar, e nao
        escrita a mao: e a mesma tabela de Etapas do resto do app."""
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=_GithubFalso({}), monkeypatch=monkeypatch)

        corpo = client.post(self.ROTA).json()

        assert corpo["etapa"] == ETAPA_EM_ANALISE
        assert sb.tabelas["tecnologia_demandas"][0]["etapa"] == ETAPA_EM_ANALISE

    def test_o_que_muda_volta_do_corpo_que_o_app_escreveu(self, monkeypatch):
        """A volta completa: o texto do diretor virou corpo de issue e voltou
        pelo mesmo extrator que le as issues escritas a mao."""
        client, _, _ = _montar(
            demandas=[_demanda("d-1", descricao="A última linha some quando imprimo.")],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        corpo = client.post(self.ROTA).json()

        assert "A última linha some quando imprimo." in corpo["o_que_muda"]

    def test_a_linha_automatica_entra_no_fio(self, monkeypatch):
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=_GithubFalso({}), monkeypatch=monkeypatch)

        client.post(self.ROTA)

        textos = [linha["texto"] for linha in _fio(sb)]
        assert texto_levou_para_desenvolvimento("Pedro Vitta") in textos
        # E a Etapa nova tambem vira linha: e o que o diretor le do movimento.
        assert texto_movimento_etapa(para=ETAPA_EM_ANALISE) in textos

    def test_nenhuma_linha_do_fio_carrega_o_numero_da_issue(self, monkeypatch):
        """O fio inteiro sai do app no "Copiar para IA", que nao passa pelo
        funil da decisao 9."""
        gh = _GithubFalso({}, proximo_numero=901)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        client.post(self.ROTA)

        for linha in _fio(sb):
            assert "901" not in str(linha["texto"])

    def test_o_diretor_nao_recebe_o_numero_da_issue_que_a_vitta_criou(self, monkeypatch):
        """O funil da decisao 9 vale para a Demanda que ACABOU de ser levada: a
        Vitta clica, e o diretor continua vendo so a Etapa."""
        gh = _GithubFalso({}, proximo_numero=901)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        client.post(self.ROTA)

        do_diretor, _, _ = _montar(logado=DIRETOR, supabase=sb, monkeypatch=monkeypatch)
        vista = do_diretor.get(f"{BASE}/demandas").json()[0]

        assert vista["etapa"] == ETAPA_EM_ANALISE
        assert vista["vinculo"] is None

    def test_falha_ao_criar_devolve_502_e_nao_grava_vinculo(self, monkeypatch):
        gh = _GithubFalso({}, erro_ao_criar=github_client.GithubIndisponivelError("timeout"))
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 502
        assert resposta.json()["detail"] == MOTIVO_GITHUB_INDISPONIVEL
        demanda = sb.tabelas["tecnologia_demandas"][0]
        assert demanda["github_issue_numero"] is None
        assert demanda["etapa"] == ETAPA_REGISTRADA
        assert demanda["o_que_muda"] is None
        # E o fio nao ganha linha nenhuma: nada aconteceu.
        assert _fio(sb) == []

    def test_resposta_sem_numero_tambem_e_falha(self, monkeypatch):
        """O GitHub respondeu 201 com um corpo que nao traz `number`. Gravar
        `None` no lugar do numero deixaria o Vinculo pela metade, que e
        exatamente o que a issue proibe."""
        gh = _GithubFalso({}, resposta_sem_numero=True)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 502
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None


# ─── 9. A rodada de fix do PR #688 (issue #677) ──────────────────────────────


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
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": forjado})

        assert corpo.count("<!--") == 1
        assert demanda_id_do_marcador(corpo) == "d-1"

    def test_o_par_de_presenca_o_ataque_montado_de_uma_vez_tambem_nao_passa(self):
        """Sem ele, uma defesa que so conhecesse a forma picada passaria por
        cima da forma direta."""
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": '<!-- demanda-vitta id="ROUBADA" -->'})

        assert corpo.count("<!--") == 1
        assert demanda_id_do_marcador(corpo) == "d-1"

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

    def test_separador_com_crlf_nao_corta_o_bloco(self):
        corpo = corpo_da_issue_nova(**{**DEMANDA_PARA_LEVAR, "descricao": "Linha uma\r\n---\r\nLinha duas"})

        bloco = bloco_para_o_diretor(corpo)
        assert "Linha duas" in bloco
        assert "Ana" in bloco

    def test_cabecalho_com_crlf_nao_fabrica_a_origem(self):
        corpo = corpo_da_issue_nova(
            **{**DEMANDA_PARA_LEVAR, "descricao": "Some a linha.\r\n## Origem\r\nPedido de Outra Pessoa."}
        )

        assert corpo.count("\n## Origem") == 1

    def test_cr_sozinho_tambem_vira_quebra_normal(self):
        """O `\\r` sozinho e o fim de linha do Mac antigo, e ainda sai de alguns
        editores. Deixar um `\\r` cru no corpo poria a linha seguinte por cima
        desta em qualquer terminal que leia a issue."""
        assert "\r" not in texto_do_diretor("Linha uma\r---\rLinha duas")


class TestOTituloTambemVaiParaORepositorioPublico:
    def test_o_titulo_passa_pela_mesma_peneira(self, monkeypatch):
        """Ele e o `title` da issue publica, e nao so o "O que muda" da Demanda
        sem descricao: sem a peneira, o unico campo cru do fluxo seria ele."""
        client, _, gh = _montar(
            demandas=[
                _demanda(
                    "d-1",
                    titulo='Erro no <!-- demanda-vitta id="ROUBADA" --> relatório',
                    descricao="A última linha some.",
                )
            ],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        assert client.post(f"{BASE}/demandas/d-1/levar-para-desenvolvimento").status_code == 200

        criada = gh.criadas[0]
        assert "<" not in criada["titulo"]
        # E o titulo continua sendo o titulo: a peneira escapa, nao corta.
        assert "relatório" in criada["titulo"]
        assert demanda_id_do_marcador(criada["corpo"]) == "d-1"

    def test_o_par_de_presenca_o_titulo_honesto_chega_igual(self, monkeypatch):
        client, _, gh = _montar(
            demandas=[_demanda("d-1", titulo="Rodapé do relatório sai cortado")],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        client.post(f"{BASE}/demandas/d-1/levar-para-desenvolvimento")

        assert gh.criadas[0]["titulo"] == "Rodapé do relatório sai cortado"


class TestDuploCliqueCriaUmaIssueSo:
    """Duas issues publicas e o dano que ninguem desfaz sozinho: a segunda
    nasce orfa, com o marcador apontando para uma Demanda que ja aponta para a
    primeira."""

    ROTA = f"{BASE}/demandas/d-1/levar-para-desenvolvimento"

    def test_o_segundo_pedido_concorrente_nao_cria_a_segunda_issue(self, monkeypatch):
        """O caminho CONCORRENTE de verdade: o segundo pedido roda enquanto o
        primeiro ainda esta dentro do `criar_issue`, que e exatamente a janela
        que a leitura do `github_issue_numero` nao pega (nenhum dos dois tem
        numero ainda)."""
        gh = _GithubFalso({}, proximo_numero=901)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        segunda_resposta = []

        criar_de_verdade = gh.criar_issue

        def criar_com_o_segundo_clique_no_meio(**kwargs):
            # O segundo cliente fala com o MESMO banco: e o duplo clique.
            outro, _, _ = _montar(supabase=sb, github=gh, monkeypatch=monkeypatch)
            segunda_resposta.append(outro.post(self.ROTA))
            return criar_de_verdade(**kwargs)

        monkeypatch.setattr(github_client, "criar_issue", criar_com_o_segundo_clique_no_meio)

        primeira = client.post(self.ROTA)

        assert primeira.status_code == 200, primeira.text
        assert segunda_resposta[0].status_code == 422
        assert segunda_resposta[0].json()["detail"] == MOTIVO_CRIACAO_EM_ANDAMENTO
        # O que de fato importa: UMA issue publica.
        assert len(gh.criadas) == 1
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] == 901

    def test_os_dois_leram_antes_de_qualquer_carimbo_e_ainda_assim_nasce_uma_issue(self, monkeypatch):
        """A corrida mais apertada: o segundo pedido entra ANTES de o primeiro
        carimbar, entao os dois passam pela guarda do "ja esta indo" (nao ha
        carimbo nenhum para nenhum dos dois ver).

        Quem fecha esta e o UPDATE condicionado: o segundo carimba, e o
        primeiro, ao tentar carimbar sobre o valor que LEU, nao acha linha e
        para. O teste nao diz qual dos dois ganha, e nao deve dizer: o que
        importa e que ganhe UM.
        """
        gh = _GithubFalso({}, proximo_numero=901)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)
        segunda_resposta = []

        def o_segundo_pedido_entra_aqui():
            outro, _, _ = _montar(supabase=sb, github=gh, monkeypatch=monkeypatch)
            segunda_resposta.append(outro.post(self.ROTA))

        sb.ao_atualizar = o_segundo_pedido_entra_aqui

        primeira = client.post(self.ROTA)

        codigos = sorted([primeira.status_code, segunda_resposta[0].status_code])
        assert codigos == [200, 422], f"{codigos}: um dos dois tinha que ser recusado"
        assert len(gh.criadas) == 1, "duas issues publicas nasceram do mesmo pedido"
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] == 901

    def test_a_falha_devolve_a_vez_na_hora(self, monkeypatch):
        """A frase do 502 manda tentar de novo em alguns instantes. Se o claim
        nao fosse desfeito, tentar de novo levaria a recusa de "ja esta indo"
        pela janela inteira, e a frase seria mentira."""
        gh = _GithubFalso({}, erro_ao_criar=github_client.GithubIndisponivelError("timeout"))
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        assert client.post(self.ROTA).status_code == 502
        assert sb.tabelas["tecnologia_demandas"][0]["github_sincronizado_em"] is None

        # E a segunda tentativa passa, com o GitHub de volta.
        gh.erro_ao_criar = None
        assert client.post(self.ROTA).status_code == 200
        assert len(gh.criadas) == 1

    def test_resposta_sem_numero_tambem_devolve_a_vez(self, monkeypatch):
        gh = _GithubFalso({}, resposta_sem_numero=True)
        client, sb, _ = _montar(demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        assert client.post(self.ROTA).status_code == 502
        assert sb.tabelas["tecnologia_demandas"][0]["github_sincronizado_em"] is None

    def test_carimbo_velho_nao_tranca_a_demanda_para_sempre(self, monkeypatch):
        """O processo pode morrer no meio da criacao, e ai nao ha quem devolva a
        vez. A janela expira sozinha, senao a Demanda ficaria sem saida nenhuma
        pela tela."""
        antigo = "2026-09-10T00:00:00Z"
        client, sb, gh = _montar(
            demandas=[_demanda("d-1", github_sincronizado_em=antigo)],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        assert client.post(self.ROTA).status_code == 200
        assert len(gh.criadas) == 1

    def test_carimbo_de_agora_segura_a_porta(self, monkeypatch):
        """O par de presenca do teste acima: uma janela que nunca segura nada
        passaria por ele."""
        agora = datetime.now(UTC).isoformat()
        client, sb, gh = _montar(
            demandas=[_demanda("d-1", github_sincronizado_em=agora)],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )

        resposta = client.post(self.ROTA)

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_CRIACAO_EM_ANDAMENTO
        assert gh.criadas == []


class TestAOrdemDasGuardasEDoDominio:
    """A ordem das guardas nas duas portas que falam com o GitHub.

    Ela nasceu de um teste (`test_super_admin_passa_em_todas` exige `< 500`, e
    o CI nao configura a integracao), e teste nenhum a travava: dava para
    trocar as linhas de volta com a suite inteira verde. Estes testes sao a
    trava, e o criterio agora e do dominio: quem sou eu (403), o que eu pedi
    existe (404) e so entao o ambiente (503).

    As duas portas dizem a MESMA coisa no caso combinado. Divergir aqui faria a
    mesma pergunta ("por que nao consigo?") ter duas respostas conforme o botao
    clicado.
    """

    SEM_INTEGRACAO_E_SEM_DEMANDA = (
        ("levar", f"{BASE}/demandas/nao-existe/levar-para-desenvolvimento", None),
        ("vincular", f"{BASE}/demandas/nao-existe/vincular", {"numero": 673}),
    )

    @pytest.mark.parametrize("porta,rota,corpo", SEM_INTEGRACAO_E_SEM_DEMANDA, ids=("levar", "vincular"))
    def test_demanda_inexistente_ganha_404_mesmo_sem_integracao(self, porta, rota, corpo, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, _, _ = _montar(demandas=[], monkeypatch=monkeypatch)

        resposta = client.post(rota, json=corpo)

        assert resposta.status_code == 404, f"{porta} respondeu {resposta.status_code}: {resposta.text}"

    @pytest.mark.parametrize(
        "porta,rota,corpo",
        (
            ("levar", f"{BASE}/demandas/d-1/levar-para-desenvolvimento", None),
            ("vincular", f"{BASE}/demandas/d-1/vincular", {"numero": 673}),
        ),
        ids=("levar", "vincular"),
    )
    def test_com_a_demanda_de_pe_a_configuracao_volta_a_falar(self, porta, rota, corpo, monkeypatch):
        """O par de presenca: sem ele, uma rota que NUNCA respondesse 503
        passaria pelo teste acima."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, _, _ = _montar(demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(rota, json=corpo)

        assert resposta.status_code == 503
        assert resposta.json()["detail"] == MOTIVO_INTEGRACAO_DESLIGADA

    def test_o_login_continua_antes_de_tudo(self, monkeypatch):
        """Quem nao e da Vitta nao chega nem a saber se a Demanda existe."""
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, _, _ = _montar(logado=DIRETOR, demandas=[], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/nao-existe/levar-para-desenvolvimento")

        assert resposta.status_code == 403

    def test_o_numero_sem_sentido_vem_antes_da_demanda(self, monkeypatch):
        """No `vincular` o payload e conferido antes da busca: ele e o pedido em
        si, e um numero zero nao vira consulta ao banco."""
        client, _, _ = _montar(demandas=[], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/nao-existe/vincular", json={"numero": 0})

        assert resposta.status_code == 422
        assert resposta.json()["detail"] == MOTIVO_NUMERO_INVALIDO


# ─── 10. Nome civil nao sai para o repositorio publico (rodada 2) ────────────


class TestNomeCivilNaoVaiParaAIssuePublica:
    """Decisao do diretor, vinda da review de seguranca do PR #688.

    A issue #677 pedia a Origem "com o autor", e a Origem publicava o nome
    completo de quem pediu num repositorio PUBLICO a cada clique. O ADR 0054
    nunca registrou isso, e a decisao passou a ser nao publicar.

    O que ficou responde a mesma pergunta sem publicar pessoa: o LINK da
    Demanda (quem le a issue tem acesso ao app, e la esta o autor e o fio
    inteiro) e o `@login` de quem LEVOU, que e identificador que a propria
    pessoa ja tornou publico no GitHub.
    """

    ROTA = f"{BASE}/demandas/d-1/levar-para-desenvolvimento"

    def _levar(self, monkeypatch):
        # Quem PEDE e o diretor (P2, sem login); quem LEVA e o Pedro (P1, com
        # login). E o caso real: nome civil dos dois no banco, nenhum dos dois
        # na issue.
        client, sb, gh = _montar(
            logado=PEDRO,
            demandas=[_demanda("d-1", autor_id="P2", responsavel_id="P1")],
            github=_GithubFalso({}),
            monkeypatch=monkeypatch,
        )
        assert client.post(self.ROTA).status_code == 200
        return sb, gh

    def test_a_origem_publicada_e_exatamente_o_link_mais_o_login(self, monkeypatch):
        """O marcador POSITIVO: a secao inteira, por igualdade. Dizer o que pode
        estar la e a unica forma de dizer que o resto nao pode, e ela nao e cega
        a variacao de forma (so o sobrenome, o nome no meio de uma frase, o nome
        dentro do link)."""
        _, gh = self._levar(monkeypatch)

        esperada = (
            "## Origem\n"
            "\n"
            "Pedido registrado na aba Tecnologia do aplicativo do hospital, "
            "levado para o desenvolvimento por @pedrorezendefig.\n"
            f"Abrir a Demanda: {link_da_demanda('d-1')}"
        )
        assert esperada in gh.criadas[0]["corpo"]

    def test_nem_o_nome_de_quem_pediu_nem_o_de_quem_levou_saem_daqui(self, monkeypatch):
        """O complemento do teste acima, e nao o teste: ele sozinho seria a
        asserção de ausencia que a rodada proibiu."""
        _, gh = self._levar(monkeypatch)

        corpo = gh.criadas[0]["corpo"]
        assert "Diretor do Hospital" not in corpo
        assert "Pedro Vitta" not in corpo

    def test_o_par_de_presenca_o_link_e_o_login_continuam_la(self, monkeypatch):
        """Sem ele, um corpo que perdesse a Origem inteira passaria pelo teste de
        cima: a rastreabilidade morreria junto com o nome."""
        _, gh = self._levar(monkeypatch)

        corpo = gh.criadas[0]["corpo"]
        assert link_da_demanda("d-1") in corpo
        assert "@pedrorezendefig" in corpo

    def test_por_dentro_o_nome_continua(self, monkeypatch):
        """A omissao vale para o que SAI para o GitHub. A Conversa e de dentro,
        e la o diretor precisa ler quem agiu, com nome de gente."""
        sb, _ = self._levar(monkeypatch)

        textos = [linha["texto"] for linha in _fio(sb)]
        assert texto_levou_para_desenvolvimento("Pedro Vitta") in textos
