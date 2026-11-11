"""A carga do historico de entregas desde o primeiro deploy (issue #1555, PRD #1548, ADR 0084, decisao 8).

Uma seam so: `carregar`, chamada direto com o banco duble do webhook e o GitHub
falso (as issues fechadas, as sub-issues e o `history.json`). E a mesma funcao
que o comando de uma vez roda, local ou no container de producao.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_webhook_github import (  # noqa: E402
    REPO,
    _demanda,
    _GithubFalso,
    _sem_github_de_verdade,  # noqa: F401 (fixture autouse: nenhuma chamada sai para a rede)
    _SupabaseMock,
)

from app.services import email_service, github_client, tecnologia_carga_historico, tecnologia_email  # noqa: E402
from app.services.tecnologia_carga_historico import carregar  # noqa: E402
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO, ETAPA_ENTREGUE  # noqa: E402

PRODUTO = {"id": "prod-1", "nome": "App do Hospital", "ativo": True, "ordem": 1}

CORPO_DE_RAIZ = "## 👔 Para o diretor\n\n**O que muda:** o prazo aparece por setor.\n\n---\n\n## Problema\n\nX."


def _fechada(numero: int, *, fechada_em: str, labels=("type:feature", "area:backend"), corpo=CORPO_DE_RAIZ, **campos):
    """Uma issue fechada como concluida, como a lista de issues do GitHub a manda."""
    dados = {
        "number": numero,
        "title": f"Entrega antiga #{numero}",
        "html_url": f"https://github.com/{REPO}/issues/{numero}",
        "state": "closed",
        "state_reason": "completed",
        "closed_at": fechada_em,
        "labels": [{"name": nome} for nome in labels],
        "body": corpo,
        "user": {"login": "pedrorezendefig"},
        "parent_issue_url": None,
    }
    dados.update(campos)
    return dados


def _subida(at: str, versao: str, *, notas: str = "", prds=()) -> dict:
    """Uma entrada do `history.json`, so com o que a carga le."""
    return {"at": at, "app_version": versao, "notes": notas, "prds": list(prds), "result": "healthy"}


# O `history.json` falso, a mais nova primeiro, como o arquivo de verdade.
#
# - A #1600 e fechada pelo PR #1601 na v0.150.0 e de novo (reaberta) pelo PR
#   #1610 na v0.160.0: a primeira e a v0.150.0.
# - A #1700 e um PRD: o `prds` a cita na v0.151.0 e na v0.170.0, e nenhum PR a
#   fecha: a primeira e a v0.151.0.
# - A #1800 e citada pelo `prds` na v0.140.0 e fechada por PR na v0.155.0: a
#   primeira entrada que a cita, por qualquer das duas portas, e a v0.140.0.
HISTORICO = [
    _subida("2026-10-20T10:00:00-03:00", "0.170.0", notas="Onda: PR #1720 (issue #1721).", prds=[1700]),
    _subida("2026-10-10T10:00:00-03:00", "0.160.0", notas="Onda: PR #1610 (issue #1600)."),
    _subida("2026-10-05T10:00:00-03:00", "0.155.0", notas="PR avulso: PR #1801, issue #1800."),
    _subida("2026-10-02T10:00:00-03:00", "0.151.0", notas="Onda: PR #1710 (issue #1711).", prds=[1700]),
    _subida("2026-10-01T10:00:00-03:00", "0.150.0", notas="Onda: PR #1601 (issue #1600) e PR #1602 (sem issue)."),
    _subida("2026-09-20T10:00:00-03:00", "0.140.0", notas="Registro antigo, texto livre.", prds=[1800]),
]


class _Cenario:
    def __init__(self, monkeypatch, *, fechadas: list[dict], demandas=(), historico=HISTORICO, relidas=None):
        """`relidas` e a issue como `ler_issue` a devolve, quando difere da
        lista: so a leitura da issue traz o pai nativo da parte."""
        self.sb = _SupabaseMock(
            {
                "tecnologia_demandas": [dict(d) for d in demandas],
                "tecnologia_produtos": [dict(PRODUTO)],
                "participantes": [],
                "notificacoes": [],
            }
        )
        self.gh = _GithubFalso({issue["number"]: issue for issue in [*fechadas, *(relidas or [])]})
        monkeypatch.setattr(github_client, "ler_issue", self.gh.ler_issue)
        monkeypatch.setattr(github_client, "ler_sub_issues", self.gh.ler_sub_issues)
        monkeypatch.setattr(github_client, "listar_issues_fechadas", lambda: [dict(i) for i in fechadas])
        monkeypatch.setattr(github_client, "ler_historico_de_deploys", lambda: [dict(e) for e in historico])

    @property
    def demandas(self) -> list[dict]:
        return self.sb.tabelas["tecnologia_demandas"]

    def demanda(self, numero: int) -> dict:
        (linha,) = [d for d in self.demandas if d.get("github_issue_numero") == numero]
        return linha


# ═══════════════════════════════════════════════════════════════════════════
# As datas e a versao batem com a primeira entrada certa
# ═══════════════════════════════════════════════════════════════════════════


class TestDatasDaPrimeiraSubida:
    def test_entrega_reaberta_fica_com_a_primeira_subida_que_a_fechou(self, monkeypatch):
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["entregue_em"] == "2026-10-08T15:00:00Z"
        assert demanda["em_producao_em"] == "2026-10-01T10:00:00-03:00"
        assert demanda["versao_em_producao"] == "v0.150.0"
        assert demanda["etapa"] == ETAPA_EM_PRODUCAO

    def test_prd_sem_pr_que_o_feche_fica_com_a_primeira_subida_que_o_cita(self, monkeypatch):
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1700, fechada_em="2026-10-21T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1700)
        assert demanda["em_producao_em"] == "2026-10-02T10:00:00-03:00"
        assert demanda["versao_em_producao"] == "v0.151.0"

    def test_a_primeira_vale_por_qualquer_das_duas_portas(self, monkeypatch):
        """Citada pelo `prds` antes de um PR a fechar: ganha a citacao."""
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1800, fechada_em="2026-10-05T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        assert cenario.demanda(1800)["versao_em_producao"] == "v0.140.0"

    def test_entrega_que_nenhuma_subida_cita_fica_entregue_sem_versao(self, monkeypatch):
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1900, fechada_em="2026-08-01T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1900)
        assert demanda["entregue_em"] == "2026-08-01T09:00:00Z"
        assert demanda.get("em_producao_em") is None
        assert demanda.get("versao_em_producao") is None
        assert demanda["etapa"] == ETAPA_ENTREGUE

    def test_demanda_do_chat_ja_existente_recebe_as_datas_sem_virar_outra(self, monkeypatch):
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE, origem="diretor")
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")], demandas=[existente]
        )

        carregar(cenario.sb, dry_run=False)

        assert len(cenario.demandas) == 1
        demanda = cenario.demanda(1600)
        assert demanda["origem"] == "diretor"
        assert demanda["versao_em_producao"] == "v0.150.0"
        assert demanda["entregue_em"] == "2026-10-08T15:00:00Z"

    def test_versao_ja_gravada_pelo_webhook_leva_a_data_da_propria_subida(self, monkeypatch):
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_EM_PRODUCAO, versao_em_producao="v0.160.0")
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")], demandas=[existente]
        )

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["versao_em_producao"] == "v0.160.0"
        assert demanda["em_producao_em"] == "2026-10-10T10:00:00-03:00"


# ═══════════════════════════════════════════════════════════════════════════
# Rodar duas vezes nao duplica nem muda data gravada
# ═══════════════════════════════════════════════════════════════════════════


class TestIdempotencia:
    def test_segunda_carga_nao_cria_nem_regrava_nada(self, monkeypatch):
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1700, fechada_em="2026-10-21T09:00:00Z"),
            ],
        )
        carregar(cenario.sb, dry_run=False)
        depois_da_primeira = [dict(d) for d in cenario.demandas]

        segunda = carregar(cenario.sb, dry_run=False)

        assert segunda.criadas == []
        assert segunda.datas == {}
        assert cenario.demandas == depois_da_primeira

    def test_data_ja_gravada_nao_muda(self, monkeypatch):
        existente = _demanda(
            "D1",
            github_issue_numero=1600,
            etapa=ETAPA_EM_PRODUCAO,
            versao_em_producao="v0.160.0",
            entregue_em="2026-10-10T13:00:00+00:00",
            em_producao_em="2026-10-10T13:00:00+00:00",
        )
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")], demandas=[existente]
        )

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["entregue_em"] == "2026-10-10T13:00:00+00:00"
        assert demanda["em_producao_em"] == "2026-10-10T13:00:00+00:00"
        assert demanda["versao_em_producao"] == "v0.160.0"


# ═══════════════════════════════════════════════════════════════════════════
# Ferramenta e parte nao viram Demanda
# ═══════════════════════════════════════════════════════════════════════════


class TestSoARaizDoApp:
    def test_ferramenta_e_parte_nao_viram_demanda(self, monkeypatch):
        pai_nativo = f"https://api.github.com/repos/{REPO}/issues/1700"
        parte_nativa = _fechada(1702, fechada_em="2026-10-02T09:00:00Z")
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1650, fechada_em="2026-10-08T15:00:00Z", labels=("type:feature", "area:skills")),
                _fechada(1651, fechada_em="2026-10-08T15:00:00Z", labels=("type:fix", "area:docs", "area:infra")),
                _fechada(1701, fechada_em="2026-10-02T09:00:00Z", corpo="## Pai\n\n#1700\n\n## O que construir\n\nY."),
                parte_nativa,
            ],
            relidas=[{**parte_nativa, "parent_issue_url": pai_nativo}],
        )

        relatorio = carregar(cenario.sb, dry_run=False)

        assert relatorio.criadas == [1600]
        assert [d["github_issue_numero"] for d in cenario.demandas] == [1600]

    def test_issue_fechada_como_nao_planejada_nao_vira_demanda(self, monkeypatch):
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z", state_reason="not_planned")]
        )

        carregar(cenario.sb, dry_run=False)

        assert cenario.demandas == []


# ═══════════════════════════════════════════════════════════════════════════
# Nenhuma notificacao e nenhum e-mail
# ═══════════════════════════════════════════════════════════════════════════


class TestSemAviso:
    def test_carga_nao_cria_notificacao_nem_manda_email(self, monkeypatch):
        enviados: list[tuple] = []
        monkeypatch.setattr(email_service, "_enviar_email", lambda *a, **kw: enviados.append(a) or True)
        monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: enviados.append(a) or True)
        existente = _demanda("D1", github_issue_numero=1800, etapa=ETAPA_ENTREGUE, autor_id="P1")
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1800, fechada_em="2026-10-05T09:00:00Z"),
            ],
            demandas=[existente],
        )

        relatorio = carregar(cenario.sb, dry_run=False)

        assert relatorio.datas.keys() == {1600, 1800}
        assert cenario.sb.tabelas["notificacoes"] == []
        assert enviados == []


# ═══════════════════════════════════════════════════════════════════════════
# --dry-run lista o que faria sem gravar
# ═══════════════════════════════════════════════════════════════════════════


class TestDryRun:
    def test_dry_run_lista_o_que_faria_e_nao_grava(self, monkeypatch, capsys):
        existente = _demanda("D1", github_issue_numero=1800, etapa=ETAPA_ENTREGUE)
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1800, fechada_em="2026-10-05T09:00:00Z"),
            ],
            demandas=[existente],
        )
        antes = [dict(d) for d in cenario.demandas]
        monkeypatch.setattr("app.dependencies.get_supabase_client", lambda: cenario.sb)

        saida = tecnologia_carga_historico.main(["--dry-run"])

        impresso = capsys.readouterr().out
        assert saida == 0
        assert "criaria a Demanda da issue #1600" in impresso
        assert "preencheria na issue #1600: entregue_em=2026-10-08T15:00:00Z" in impresso
        assert "versao_em_producao=v0.150.0" in impresso
        assert "preencheria na issue #1800:" in impresso
        assert "versao_em_producao=v0.140.0" in impresso
        assert cenario.demandas == antes


# ═══════════════════════════════════════════════════════════════════════════
# A lista de issues fechadas do cliente, pagina a pagina
# ═══════════════════════════════════════════════════════════════════════════


def test_lista_de_fechadas_le_todas_as_paginas_e_tira_os_prs(monkeypatch):
    paginas = {
        1: [{"number": n} for n in range(1, 100)] + [{"number": 100, "pull_request": {"url": "x"}}],
        2: [{"number": 101}],
    }
    pedidos: list[str] = []

    def _chamar(metodo, caminho, **_kw):
        pedidos.append(caminho)
        return paginas[int(caminho.rsplit("page=", 1)[1])]

    monkeypatch.setattr(github_client, "_chamar", _chamar)

    issues = github_client.listar_issues_fechadas()

    assert [i["number"] for i in issues] == [*range(1, 100), 101]
    assert all("state=closed" in p for p in pedidos)
    assert len(pedidos) == 2
