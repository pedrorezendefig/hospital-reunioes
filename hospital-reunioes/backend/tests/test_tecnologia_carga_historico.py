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
from app.services.tecnologia_sincronizacao import sincronizar_demanda  # noqa: E402
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
#   #1610 na v0.160.0: fechada de novo em 08/10, a que conta e a v0.160.0.
# - A #1700 e um PRD: o `prds` a cita na v0.151.0 e na v0.170.0, e nenhum PR a
#   fecha.
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
# As datas e a versao batem com a primeira subida depois do fechamento
# ═══════════════════════════════════════════════════════════════════════════


class TestDatasDaPrimeiraSubida:
    """A subida que conta e a primeira de DEPOIS do fechamento atual da issue,
    a mesma regra da reconciliacao (`_subiu_depois_do_fechamento`, revisao do
    PR #1100): a de antes levou um fechamento anterior, ou uma fatia do PRD
    que ainda nao fechava a entrega."""

    def test_entrega_reaberta_fica_com_a_primeira_subida_depois_do_fechamento(self, monkeypatch):
        """A v0.150.0 levou o primeiro fechamento; o atual (08/10) subiu na v0.160.0."""
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["entregue_em"] == "2026-10-08T15:00:00Z"
        assert demanda["em_producao_em"] == "2026-10-10T10:00:00-03:00"
        assert demanda["versao_em_producao"] == "v0.160.0"
        assert demanda["etapa"] == ETAPA_EM_PRODUCAO

    def test_prd_sem_pr_que_o_feche_fica_com_a_primeira_subida_que_o_cita(self, monkeypatch):
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1700, fechada_em="2026-10-01T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1700)
        assert demanda["em_producao_em"] == "2026-10-02T10:00:00-03:00"
        assert demanda["versao_em_producao"] == "v0.151.0"

    def test_prd_fechado_depois_de_toda_subida_que_o_cita_fica_entregue(self, monkeypatch):
        """O `prds` cita o PRD desde a primeira fatia, e a ultima fatia foi
        mergeada sem build: nada prova que a entrega inteira subiu."""
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1700, fechada_em="2026-10-21T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1700)
        assert demanda["entregue_em"] == "2026-10-21T09:00:00Z"
        assert demanda.get("em_producao_em") is None
        assert demanda.get("versao_em_producao") is None
        assert demanda["etapa"] == ETAPA_ENTREGUE

    def test_a_primeira_vale_por_qualquer_das_duas_portas(self, monkeypatch):
        """Citada pelo `prds` antes de um PR a fechar: ganha a citacao."""
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1800, fechada_em="2026-09-19T09:00:00Z")])

        carregar(cenario.sb, dry_run=False)

        assert cenario.demanda(1800)["versao_em_producao"] == "v0.140.0"

    def test_versao_velha_com_a_etapa_entregue_nao_leva_a_em_producao(self, monkeypatch):
        """Reaberta para um ajuste, fechada de novo, o ajuste ainda sem subir:
        a versao que sobrou na coluna e da subida anterior."""
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE, versao_em_producao="v0.150.0")
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-25T09:00:00Z")], demandas=[existente]
        )

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["etapa"] == ETAPA_ENTREGUE
        assert demanda["versao_em_producao"] == "v0.150.0"
        assert demanda.get("em_producao_em") is None

    def test_versao_velha_da_lugar_a_subida_depois_do_fechamento(self, monkeypatch):
        """O mesmo caso com o ajuste ja no ar: a carga carimba como o webhook
        de deploy carimbaria, com a versao da subida certa."""
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE, versao_em_producao="v0.150.0")
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")], demandas=[existente]
        )

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["etapa"] == ETAPA_EM_PRODUCAO
        assert demanda["versao_em_producao"] == "v0.160.0"
        assert demanda["em_producao_em"] == "2026-10-10T10:00:00-03:00"

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
        assert demanda["versao_em_producao"] == "v0.160.0"
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
# A carga escreve so onde a sincronizacao e o webhook de deploy escreveriam
# ═══════════════════════════════════════════════════════════════════════════


class TestSoDemandaAbertaENaoMexida:
    def test_demanda_concluida_ou_cancelada_nao_e_tocada(self, monkeypatch):
        """O estado de antes da ADR 0077 fica congelado, como em
        `sincronizar_demanda` e em `_carimbar_em_producao`."""
        concluida = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE, estado="concluida")
        cancelada = _demanda("D2", github_issue_numero=1800, etapa=ETAPA_ENTREGUE, estado="cancelada")
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1800, fechada_em="2026-09-19T09:00:00Z"),
            ],
            demandas=[concluida, cancelada],
        )
        antes = [dict(d) for d in cenario.demandas]

        relatorio = carregar(cenario.sb, dry_run=False)

        assert relatorio.datas == {}
        assert cenario.demandas == antes

    def test_subida_carimbada_durante_a_carga_nao_e_sobrescrita(self, monkeypatch):
        """O retrato e lido no comeco; o webhook de deploy carimba a Demanda
        enquanto a carga ainda le o GitHub. O UPDATE da carga nao casa."""
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE)
        cenario = _Cenario(
            monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z")], demandas=[existente]
        )
        carimbo = {
            "etapa": ETAPA_EM_PRODUCAO,
            "versao_em_producao": "v0.170.0",
            "entregue_em": "2026-10-20T13:00:00+00:00",
            "em_producao_em": "2026-10-20T13:00:00+00:00",
        }

        def _webhook_passa_na_frente(nome, _update, linhas):
            if nome == "tecnologia_demandas" and linhas[0]["etapa"] == ETAPA_ENTREGUE:
                linhas[0].update(carimbo, atualizado_em="2026-10-20T13:00:01+00:00")

        cenario.sb.antes_do_update = _webhook_passa_na_frente

        relatorio = carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert {coluna: demanda[coluna] for coluna in carimbo} == carimbo
        assert 1600 not in relatorio.datas


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

    def test_carga_com_demonstracao_e_diretoria_cadastrada_nao_avisa(self, monkeypatch):
        """Issue #1560: a entrega antiga que a carga cria e promove a Em
        produção traz o link de Demonstração, e há diretoria para avisar no
        card da Vitta. Nem o sino nem o e-mail saem."""
        enviados: list[tuple] = []
        monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: enviados.append(a) or True)
        corpo = f"{CORPO_DE_RAIZ}\n\n<!-- demonstracao: https://youtu.be/demo-antiga -->"
        cenario = _Cenario(monkeypatch, fechadas=[_fechada(1600, fechada_em="2026-10-08T15:00:00Z", corpo=corpo)])
        cenario.sb.tabelas["participantes"].append(
            {
                "id": "P9",
                "nome_completo": "Diretor Geral",
                "email": "diretor@hsm.test",
                "ativo": True,
                "is_super_admin": True,
                "access_profile": "super_admin",
            }
        )

        carregar(cenario.sb, dry_run=False)

        demanda = cenario.demanda(1600)
        assert demanda["demonstracao_url"] == "https://youtu.be/demo-antiga"
        assert demanda["etapa"] == ETAPA_EM_PRODUCAO
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
        assert "versao_em_producao=v0.160.0" in impresso
        assert "preencheria na issue #1800:" in impresso
        assert "versao_em_producao=v0.155.0" in impresso
        assert cenario.demandas == antes

    def test_dry_run_conta_as_demandas_com_anexo_que_o_cron_apagaria(self, monkeypatch, capsys):
        """Promovida a Em producao com a entrega de mais de 30 dias, a Demanda
        tem os prints vencidos (`_print_venceu`), e a passada seguinte do cron
        apaga os binarios de vez. O `--dry-run` diz quais sao antes de gravar."""
        com_anexo = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE)
        sem_anexo = _demanda("D2", github_issue_numero=1800, etapa=ETAPA_ENTREGUE)
        cenario = _Cenario(
            monkeypatch,
            fechadas=[
                _fechada(1600, fechada_em="2026-10-08T15:00:00Z"),
                _fechada(1800, fechada_em="2026-09-19T09:00:00Z"),
            ],
            demandas=[com_anexo, sem_anexo],
        )
        cenario.sb.tabelas["tecnologia_anexos"] = [
            {"id": "A1", "demanda_id": "D1", "apagado_em": None},
            {"id": "A2", "demanda_id": "D2", "apagado_em": "2026-10-01T00:00:00Z"},
        ]
        monkeypatch.setattr("app.dependencies.get_supabase_client", lambda: cenario.sb)

        tecnologia_carga_historico.main(["--dry-run"])

        impresso = capsys.readouterr().out
        assert "issue #1600 tem anexo guardado: o cron apagaria os prints" in impresso
        assert "issue #1800 tem anexo" not in impresso
        assert "1 com anexo que o cron apagaria" in impresso


# ═══════════════════════════════════════════════════════════════════════════
# A data do pedido: `criada_em` na foto (issue #1702, PRD #1689)
# ═══════════════════════════════════════════════════════════════════════════

CRIADA_EM = "2026-08-03T11:20:00Z"


class TestDataDoPedido:
    """O pedido da Origem Vitta conta na semana em que a issue-raiz nasceu: a
    foto guarda a data de criacao dela, e a carga a preenche onde falta."""

    def test_sincronizacao_guarda_na_foto_a_criacao_da_issue_raiz(self, monkeypatch):
        issue = _fechada(1600, fechada_em="2026-10-08T15:00:00Z", created_at=CRIADA_EM)
        existente = _demanda("D1", github_issue_numero=1600, etapa=ETAPA_ENTREGUE, origem="vitta")
        cenario = _Cenario(monkeypatch, fechadas=[issue], demandas=[existente])

        sincronizar_demanda(cenario.sb, cenario.demanda(1600), avisar=False)

        assert cenario.demanda(1600)["github_foto"]["criada_em"] == CRIADA_EM

    def _cenario_da_carga(self, monkeypatch):
        """A #1600 e um pedido da Vitta aberto, sem marcador no corpo e com a
        foto de antes desta fatia; a #1800 ja tem `criada_em` na foto."""
        aberta = {
            **_fechada(1600, fechada_em=None, created_at=CRIADA_EM),
            "state": "open",
            "state_reason": None,
        }
        ja_tem = {**_fechada(1800, fechada_em=None, created_at="2026-09-01T08:00:00Z"), "state": "open"}
        vitta = _demanda(
            "D1",
            github_issue_numero=1600,
            origem="vitta",
            github_foto={"numero": 1600, "titulo": "Pedido da Vitta", "partes": []},
        )
        gravada = _demanda(
            "D2",
            github_issue_numero=1800,
            origem="vitta",
            github_foto={"numero": 1800, "criada_em": "2026-07-01T00:00:00Z"},
        )
        return _Cenario(monkeypatch, fechadas=[], demandas=[vitta, gravada], relidas=[aberta, ja_tem])

    def test_carga_preenche_criada_em_so_onde_falta_e_uma_vez_so(self, monkeypatch):
        cenario = self._cenario_da_carga(monkeypatch)
        fotos_gravadas: list[dict] = []
        cenario.sb.antes_do_update = lambda nome, update, _linhas: (
            fotos_gravadas.append(update["github_foto"]) if "github_foto" in update else None
        )

        primeira = carregar(cenario.sb, dry_run=False)
        segunda = carregar(cenario.sb, dry_run=False)

        assert cenario.demanda(1600)["github_foto"] == {
            "numero": 1600,
            "titulo": "Pedido da Vitta",
            "partes": [],
            "criada_em": CRIADA_EM,
        }
        assert cenario.demanda(1800)["github_foto"]["criada_em"] == "2026-07-01T00:00:00Z"
        assert primeira.criada_em == {1600: CRIADA_EM}
        assert segunda.criada_em == {}
        assert len(fotos_gravadas) == 1

    def test_dry_run_lista_a_data_do_pedido_e_nao_grava(self, monkeypatch, capsys):
        cenario = self._cenario_da_carga(monkeypatch)
        antes = [dict(d) for d in cenario.demandas]
        monkeypatch.setattr("app.dependencies.get_supabase_client", lambda: cenario.sb)

        saida = tecnologia_carga_historico.main(["--dry-run"])

        impresso = capsys.readouterr().out
        assert saida == 0
        assert f"preencheria a data do pedido na issue #1600: criada_em={CRIADA_EM}" in impresso
        assert "data do pedido na issue #1800" not in impresso
        assert "1 com a data do pedido" in impresso
        assert cenario.demandas == antes

    def test_carga_da_data_do_pedido_nao_avisa_ninguem(self, monkeypatch):
        """Com o autor e a diretoria cadastrados, ha para quem avisar: nem o
        sino nem o e-mail saem."""
        enviados: list[tuple] = []
        monkeypatch.setattr(email_service, "_enviar_email", lambda *a, **kw: enviados.append(a) or True)
        monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: enviados.append(a) or True)
        cenario = self._cenario_da_carga(monkeypatch)
        cenario.sb.tabelas["participantes"].extend(
            {
                "id": pid,
                "nome_completo": nome,
                "email": f"{pid.lower()}@hsm.test",
                "ativo": True,
                "is_super_admin": True,
                "access_profile": "super_admin",
            }
            for pid, nome in (("P1", "Autor do pedido"), ("P9", "Diretor Geral"))
        )

        relatorio = carregar(cenario.sb, dry_run=False)

        assert relatorio.criada_em == {1600: CRIADA_EM}
        assert cenario.sb.tabelas["notificacoes"] == []
        assert enviados == []


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
