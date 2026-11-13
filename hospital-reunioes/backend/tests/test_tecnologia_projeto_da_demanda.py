"""O Projeto na Demanda: Aplicativo do Hospital e Ana (issue #1713, PRD #1710,
ADR 0093, decisoes 2, 3 e 6).

A issue #50 da Ana e a #50 do Hospital sao Demandas diferentes: a chave do
Vinculo passa a ser projeto mais numero da issue. Os cenarios aqui poem as duas
lado a lado, com o MESMO numero, e olham qual delas cada caminho toca.

Os dubles sao os do webhook do GitHub (`test_tecnologia_webhook_github`), com
um GitHub falso que responde por projeto: a leitura que vai ao repositorio
errado aparece em `leituras`, e a issue que nao existe naquele repositorio
estoura.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_deploy import (  # noqa: E402
    _avisar,
    _corpo_do_deploy,
    _segredo_do_deploy_configurado,  # noqa: F401  (autouse)
)
from test_tecnologia_webhook_github import (  # noqa: E402
    REPO,
    _corpo,
    _demanda,
    _demandas,
    _entregar,
    _entregue,
    _issue,
    _montar,
    _pessoa,
    _pr_do_app,  # noqa: F401  (autouse)
    _reset_rate_limiter,  # noqa: F401  (autouse)
    _segredo_configurado,  # noqa: F401  (autouse)
    _sem_github_de_verdade,  # noqa: F401  (autouse)
    _sem_pr_aberto,  # noqa: F401  (autouse)
)

from app.config import settings  # noqa: E402
from app.services import github_client, tecnologia_sincronizacao  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    ETAPA_EM_ANALISE,
    ETAPA_EM_DESENVOLVIMENTO,
    ETAPA_EM_PRODUCAO,
    ETAPA_ENTREGUE,
)

REPO_ANA = "pedrorezendefig/programa-ana"

HOSPITAL = "hospital"
ANA = "ana"


@pytest.fixture(autouse=True)
def _ana_configurada(monkeypatch):
    """O repositorio da Ana de pe, como estara no Coolify depois da tarefa
    humana #1717. Quem prova a Ana desligada e o teste que APAGA a variavel."""
    monkeypatch.setattr(settings, "github_integracao_repo_ana", REPO_ANA)


class _GithubDosDoisProjetos:
    """O GitHub com um repositorio por Projeto: a issue e achada por (projeto,
    numero), e cada leitura fica registrada com o projeto que a pediu."""

    def __init__(self, issues: dict[tuple[str, int], dict]):
        self.issues = issues
        self.leituras: list[tuple[str, int]] = []

    def ler_issue(self, numero: int, *, projeto: str) -> dict:
        self.leituras.append((projeto, numero))
        if (projeto, numero) not in self.issues:
            raise github_client.IssueNaoEncontradaError(f"{projeto}#{numero}")
        return self.issues[(projeto, numero)]

    def ler_sub_issues(self, numero: int, *, projeto: str) -> list[dict]:
        return []


def _montar_dois(monkeypatch, demandas: list[dict], gh: _GithubDosDoisProjetos):
    cliente, sb, _ = _montar(demandas=demandas, participantes=[_pessoa()], monkeypatch=monkeypatch)
    monkeypatch.setattr(github_client, "ler_issue", gh.ler_issue)
    monkeypatch.setattr(github_client, "ler_sub_issues", gh.ler_sub_issues)
    return cliente, sb


def _por_id(sb) -> dict[str, dict]:
    return {d["id"]: d for d in _demandas(sb)}


# A issue #50 dos dois lados, cada uma levando a uma Etapa diferente: a do
# Hospital em desenvolvimento, a da Ana entregue. A Etapa que cada Demanda
# ganha diz de qual repositorio ela foi lida.
ISSUES_50 = {
    (HOSPITAL, 50): _issue(50, labels=("in-progress",)),
    (ANA, 50): {**_entregue(50), "html_url": f"https://github.com/{REPO_ANA}/issues/50"},
}


def _as_duas_demandas_50(*, ana_primeiro: bool) -> list[dict]:
    """A Demanda da Ana e a do Hospital, as duas na issue #50 e Em analise.
    A ordem conta: quem achasse a Demanda so pelo numero pegaria a primeira."""
    hospital = _demanda("DH", projeto=HOSPITAL, github_issue_numero=50, etapa=ETAPA_EM_ANALISE)
    ana = _demanda("DA", projeto=ANA, github_issue_numero=50, etapa=ETAPA_EM_ANALISE)
    return [ana, hospital] if ana_primeiro else [hospital, ana]


class TestAsDuasDemandas50ExistemJuntas:
    def test_o_espelho_cria_a_ana_50_com_a_hospital_50_ja_vinculada(self, monkeypatch):
        """Criterio de aceite: `hospital #50` e `ana #50` existem juntas. A
        issue-raiz #50 da Ana vira Demanda da Ana mesmo com a #50 do Hospital
        ja tendo a dela: a do Hospital nao e "a mesma issue"."""
        from app.services import tecnologia_espelho

        gh = _GithubDosDoisProjetos(
            {(ANA, 50): {**_issue(50, labels=("type:feature", "area:backend")), "user": {"login": "alguem"}}}
        )
        hospital = _demanda("DH", projeto=HOSPITAL, github_issue_numero=50)
        _, sb = _montar_dois(monkeypatch, [hospital], gh)
        sb.tabelas["tecnologia_produtos"] = [{"id": "prod-1", "ativo": True, "ordem": 1}]

        criada = tecnologia_espelho.espelhar(sb, ANA, 50)

        assert criada is not None
        assert (criada["projeto"], criada["github_issue_numero"]) == (ANA, 50)
        assert sorted((d["projeto"], d["github_issue_numero"]) for d in _demandas(sb)) == [(ANA, 50), (HOSPITAL, 50)]
        assert gh.leituras == [(ANA, 50)]


class TestOWebhookDoGithubPorProjeto:
    def test_evento_da_ana_na_issue_50_mexe_so_na_demanda_da_ana(self, monkeypatch):
        """Criterio de aceite: o evento do repositorio da Ana le a issue la e
        move so a Demanda da Ana; a do Hospital, com o mesmo numero, fica."""
        gh = _GithubDosDoisProjetos(ISSUES_50)
        cliente, sb = _montar_dois(monkeypatch, _as_duas_demandas_50(ana_primeiro=False), gh)

        resposta = _entregar(cliente, _corpo(50, repo=REPO_ANA))

        assert resposta.status_code == 200
        assert resposta.json()["sincronizada"] is True
        assert gh.leituras == [(ANA, 50)]
        demandas = _por_id(sb)
        assert demandas["DA"]["etapa"] == ETAPA_ENTREGUE
        assert demandas["DH"]["etapa"] == ETAPA_EM_ANALISE

    def test_evento_do_hospital_na_issue_50_mexe_so_na_demanda_do_hospital(self, monkeypatch):
        gh = _GithubDosDoisProjetos(ISSUES_50)
        cliente, sb = _montar_dois(monkeypatch, _as_duas_demandas_50(ana_primeiro=True), gh)

        resposta = _entregar(cliente, _corpo(50, repo=REPO))

        assert resposta.status_code == 200
        assert resposta.json()["sincronizada"] is True
        assert gh.leituras == [(HOSPITAL, 50)]
        demandas = _por_id(sb)
        assert demandas["DH"]["etapa"] == ETAPA_EM_DESENVOLVIMENTO
        assert demandas["DA"]["etapa"] == ETAPA_EM_ANALISE


class TestORepositorioDaEntrega:
    def test_entrega_de_um_terceiro_repositorio_e_descartada(self, monkeypatch):
        """Criterio de aceite: com o Hospital e a Ana de pe, um terceiro
        repositorio nao vira Projeto nenhum, e nada e lido nem escrito."""
        gh = _GithubDosDoisProjetos(ISSUES_50)
        demandas = _as_duas_demandas_50(ana_primeiro=False)
        cliente, sb = _montar_dois(monkeypatch, demandas, gh)

        resposta = _entregar(cliente, _corpo(50, repo="outra-pessoa/programa-ana"))

        assert resposta.status_code == 200
        assert resposta.json() == {"ignorado": "outro_repositorio"}
        assert gh.leituras == []
        assert _demandas(sb) == demandas

    def test_com_a_variavel_da_ana_vazia_a_entrega_da_ana_e_descartada(self, monkeypatch):
        """Criterio de aceite: a Ana desligada. A entrega do repositorio dela
        sai como de outro repositorio, e o Hospital segue sendo aceito."""
        monkeypatch.setattr(settings, "github_integracao_repo_ana", "")
        gh = _GithubDosDoisProjetos(ISSUES_50)
        demandas = _as_duas_demandas_50(ana_primeiro=False)
        cliente, sb = _montar_dois(monkeypatch, demandas, gh)

        resposta = _entregar(cliente, _corpo(50, repo=REPO_ANA))

        assert resposta.json() == {"ignorado": "outro_repositorio"}
        assert gh.leituras == []
        assert _demandas(sb) == demandas

        do_hospital = _entregar(cliente, _corpo(50, repo=REPO))

        assert do_hospital.json()["sincronizada"] is True
        assert gh.leituras == [(HOSPITAL, 50)]


# A subida que levou a issue #50 do Hospital, como o `history.json` da `main` a
# registra, e o fechamento de antes dela (13:00Z da subida contra 12:00Z).
SUBIDA_DA_50 = "2026-10-09T10:00:00-03:00"
HISTORICO_DA_50 = [
    {
        "app_version": "0.170.0",
        "at": SUBIDA_DA_50,
        "notes": "PR avulso: PR #1200, issue #50. Merge pela API do GitHub, um build.",
    }
]
FECHADA_ANTES_DA_SUBIDA = "2026-10-09T12:00:00Z"


def _as_duas_entregues_50(*, ana_primeiro: bool) -> list[dict]:
    """A Demanda da Ana e a do Hospital, as duas na issue #50 e Entregues: as
    duas estao onde o carimbo de Em producao age."""
    return [{**d, "etapa": ETAPA_ENTREGUE} for d in _as_duas_demandas_50(ana_primeiro=ana_primeiro)]


class TestOCarimboDeEmProducaoSoNoHospital:
    def test_o_webhook_de_deploy_com_a_issue_50_carimba_so_a_demanda_do_hospital(self, monkeypatch):
        """Criterio de aceite: a subida e do Hospital. A #50 que o PR do lote
        fecha e a #50 do Hospital, e a Demanda da Ana na #50 segue Entregue,
        que e a ultima Etapa dela (ADR 0093, decisao 6)."""
        gh = _GithubDosDoisProjetos({})
        cliente, sb = _montar_dois(monkeypatch, _as_duas_entregues_50(ana_primeiro=True), gh)

        resposta = _avisar(cliente, _corpo_do_deploy(prs=[{"numero": 1200, "fecha": [50]}]))

        assert resposta.json()["marcadas"] == 1
        demandas = _por_id(sb)
        assert (demandas["DH"]["etapa"], demandas["DH"]["versao_em_producao"]) == (ETAPA_EM_PRODUCAO, "v0.169.0")
        assert demandas["DA"]["etapa"] == ETAPA_ENTREGUE
        assert demandas["DA"].get("versao_em_producao") is None

    def test_o_plano_b_pelo_history_json_carimba_so_a_demanda_do_hospital(self, monkeypatch):
        """Criterio de aceite, pela passagem de hora em hora: o `history.json`
        lista a issue #50, e so a Demanda do Hospital a recebe. A da Ana nem
        entra no lote, mesmo com a issue dela fechada antes da subida."""
        gh = _GithubDosDoisProjetos(
            {
                (HOSPITAL, 50): {**_entregue(50), "closed_at": FECHADA_ANTES_DA_SUBIDA},
                (ANA, 50): {**_entregue(50), "closed_at": FECHADA_ANTES_DA_SUBIDA},
            }
        )
        _, sb = _montar_dois(monkeypatch, _as_duas_entregues_50(ana_primeiro=True), gh)
        monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: [dict(e) for e in HISTORICO_DA_50])

        resultado = tecnologia_sincronizacao.reconciliar_em_producao(sb)

        assert resultado == {"lidas": 1, "marcadas": 1, "falhas": 0}
        demandas = _por_id(sb)
        assert (demandas["DH"]["etapa"], demandas["DH"]["versao_em_producao"]) == (ETAPA_EM_PRODUCAO, "v0.170.0")
        assert demandas["DA"]["etapa"] == ETAPA_ENTREGUE
        assert gh.leituras == [(HOSPITAL, 50)]


# ─── A migration 145 ─────────────────────────────────────────────────────────

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "145_tecnologia_projeto_da_demanda.sql"


@pytest.fixture
def sql() -> str:
    """O SQL que o Studio roda, sem os comentarios: o cabecalho cita as mesmas
    palavras. A prova de que ele roda (as Demandas de hoje no Hospital, a #50
    dos dois lados, a terceira recusada, rodar duas vezes) foi feita num
    Postgres descartavel e esta no corpo do PR."""
    return re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))


class TestAMigracao:
    def test_as_demandas_de_hoje_ficam_no_hospital_e_o_projeto_e_obrigatorio(self, sql):
        assert re.search(
            r"ALTER TABLE tecnologia_demandas ADD COLUMN IF NOT EXISTS projeto TEXT NOT NULL DEFAULT 'hospital';", sql
        )

    def test_o_check_e_a_mesma_lista_de_projetos_do_cliente_do_github(self, sql):
        achado = re.search(r"CHECK \(projeto IN \(([^)]*)\)\)", sql)
        assert achado
        assert tuple(re.findall(r"'([a-z]+)'", achado.group(1))) == github_client.PROJETOS

    def test_o_indice_unico_do_vinculo_passa_a_ser_projeto_mais_numero(self, sql):
        """Criterio de aceite: `hospital #50` e `ana #50` existem juntas. O
        indice velho, so pelo numero, sai antes do novo entrar."""
        velho = re.search(r"DROP INDEX IF EXISTS tecnologia_demandas_github_issue_numero_idx;", sql)
        novo = re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS tecnologia_demandas_projeto_github_issue_numero_idx\s+"
            r"ON tecnologia_demandas \(projeto, github_issue_numero\)\s+"
            r"WHERE github_issue_numero IS NOT NULL;",
            sql,
        )
        assert velho and novo
        assert velho.start() < novo.start()

    def test_a_sequencia_do_numero_da_demanda_nao_muda(self, sql):
        """Uma sequencia so para o Numero da Demanda (ADR 0093, decisao 3)."""
        antes_do_recibo = sql.split("INSERT INTO migracoes_aplicadas", 1)[0]
        assert "tecnologia_demandas" in antes_do_recibo, "o caso perdeu o sentido: a migration nao mexe na Demanda"
        assert not re.search(r"\bnumero\b|numero_seq", antes_do_recibo)

    def test_a_migration_grava_o_recibo_145_por_ultimo(self, sql):
        instrucoes = [i.strip() for i in sql.split(";") if i.strip()]
        assert instrucoes[-1] == "INSERT INTO migracoes_aplicadas (numero) VALUES (145) ON CONFLICT (numero) DO NOTHING"
