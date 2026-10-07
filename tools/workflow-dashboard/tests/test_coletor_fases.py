"""Coletor do Hospital OS: campos novos do PR, timeline em lote, branches remotas e fases.

`gh` e `git` mockados em collect._run (molde de test_filtro_responsavel.py): o
teste afirma o que o coletor pede e o que ele entrega normalizado, sem rede.
"""

import json
import sys
import threading
import urllib.request
from pathlib import Path

DASH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DASH))

import collect  # noqa: E402

MARCADOR = "<!-- automacao -->\n"

PR_BASE = [
    {
        "number": 10,
        "title": "aberto",
        "state": "OPEN",
        "mergedAt": None,
        "headRefName": "feat/x-1",
        "closingIssuesReferences": [{"number": 1}],
        "url": "u10",
        "createdAt": "2026-10-03T10:00:00Z",
        "closedAt": None,
        "author": {"login": "bia"},
        "isDraft": True,
    },
    {
        "number": 11,
        "title": "mergeado",
        "state": "MERGED",
        "mergedAt": "2026-10-02T10:00:00Z",
        "headRefName": "feat/y-2",
        "closingIssuesReferences": [{"number": 2}],
        "url": "u11",
        "createdAt": "2026-10-01T10:00:00Z",
        "closedAt": "2026-10-02T10:00:00Z",
        "author": {"login": "caio"},
        "isDraft": False,
    },
]

PR_ABERTOS = [
    {
        "number": 10,
        "mergeStateStatus": "DIRTY",
        "statusCheckRollup": [
            {
                "__typename": "CheckRun",
                "name": "Backend",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "startedAt": "2026-10-03T10:05:00Z",
                "completedAt": "2026-10-03T10:20:00Z",
            },
            {
                "__typename": "StatusContext",
                "context": "vercel",
                "state": "PENDING",
                "startedAt": "2026-10-03T10:06:00Z",
            },
        ],
        "reviews": [{"author": {"login": "rib"}, "state": "APPROVED", "submittedAt": "2026-10-03T11:00:00Z"}],
        "comments": [
            {
                "author": {"login": "pedro"},
                "createdAt": "2026-10-03T12:00:00Z",
                "body": MARCADOR + "## Veredito da revisão\n\nVEREDITO: MUST-FIX (1)",
            },
            {"author": {"login": "rib"}, "createdAt": "2026-10-03T13:00:00Z", "body": "olhei"},
        ],
    }
]


def _fake_gh(chamadas, *, abertos=PR_ABERTOS, falha=None):
    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        if falha and falha(cmd):
            raise RuntimeError("HTTP 504: We couldn't respond to your request in time")
        if cmd[:3] == ["gh", "pr", "list"]:
            return json.dumps(abertos if "open" in cmd else PR_BASE)
        raise AssertionError(f"chamada inesperada: {cmd}")

    return run


def test_pr_traz_os_campos_novos_normalizados(monkeypatch):
    chamadas = []
    monkeypatch.setattr(collect, "_run", _fake_gh(chamadas))
    prs = collect._gh_prs(DASH)
    collect._enriquecer_prs_abertos(DASH, prs)
    aberto, mergeado = prs

    assert aberto["created_at"] == "2026-10-03T10:00:00Z"
    assert aberto["author"] == "bia"
    assert aberto["is_draft"] is True
    assert aberto["merge_state"] == "DIRTY"
    assert aberto["checks"] == [
        {
            "nome": "Backend",
            "status": "COMPLETED",
            "conclusao": "FAILURE",
            "inicio": "2026-10-03T10:05:00Z",
            "fim": "2026-10-03T10:20:00Z",
        },
        {"nome": "vercel", "status": "PENDING", "conclusao": "PENDING", "inicio": "2026-10-03T10:06:00Z", "fim": None},
    ]
    assert aberto["reviews"] == [{"autor": "rib", "estado": "APPROVED", "em": "2026-10-03T11:00:00Z"}]
    assert aberto["comentarios"] == 2
    assert aberto["vereditos"] == [{"tipo": "revisao", "valor": "must_fix", "em": "2026-10-03T12:00:00Z"}]

    assert mergeado["closed_at"] == "2026-10-02T10:00:00Z"
    assert mergeado["author"] == "caio"
    assert (mergeado["checks"], mergeado["merge_state"], mergeado["comentarios"]) == ([], None, None)


def test_campos_pesados_so_sao_pedidos_para_os_prs_abertos(monkeypatch):
    # statusCheckRollup, reviews e comments da lista inteira estouram o GraphQL do GitHub (HTTP 504)
    chamadas = []
    monkeypatch.setattr(collect, "_run", _fake_gh(chamadas))
    collect._enriquecer_prs_abertos(DASH, collect._gh_prs(DASH))
    todos, abertos = chamadas
    assert todos[todos.index("--state") + 1] == "all"
    assert not {"statusCheckRollup", "reviews", "comments"} & set(todos[-1].split(","))
    assert abertos[abertos.index("--state") + 1] == "open"
    assert {"statusCheckRollup", "mergeStateStatus", "reviews", "comments"} <= set(abertos[-1].split(","))


def test_falha_na_consulta_dos_abertos_mantem_os_prs_sem_os_campos_pesados(monkeypatch):
    chamadas = []
    monkeypatch.setattr(collect, "_run", _fake_gh(chamadas, falha=lambda cmd: "open" in cmd))
    prs = collect._gh_prs(DASH)
    collect._enriquecer_prs_abertos(DASH, prs)
    assert [p["number"] for p in prs] == [10, 11]
    assert prs[0]["checks"] == [] and prs[0]["vereditos"] == []


# ---------- timeline em lote ----------


def _no_issue(number, *, eventos=(), prs=()):
    return {
        "number": number,
        "createdAt": "2026-10-01T10:00:00Z",
        "timelineItems": {"nodes": list(eventos)},
        "closedByPullRequestsReferences": {"nodes": list(prs)},
    }


def _no_pr(number, *, state="OPEN", rollups=(), comentarios=()):
    return {
        "number": number,
        "state": state,
        "createdAt": "2026-10-02T10:00:00Z",
        "closedAt": None,
        "mergedAt": None,
        "headRefName": f"feat/x-{number}",
        "commits": {
            "nodes": [
                {"commit": {"committedDate": em, "statusCheckRollup": {"state": s} if s else None}} for em, s in rollups
            ]
        },
        "comments": {"nodes": [{"createdAt": em, "body": b} for em, b in comentarios]},
    }


def _pagina(nodes, proxima=None):
    return json.dumps(
        {
            "data": {
                "repository": {
                    "issues": {"pageInfo": {"hasNextPage": bool(proxima), "endCursor": proxima}, "nodes": nodes}
                }
            }
        }
    )


def test_timeline_vem_em_lote_so_das_issues_abertas_e_normalizada(monkeypatch):
    chamadas = []
    pr = _no_pr(
        20,
        rollups=[
            ("2026-10-02T11:00:00Z", "FAILURE"),
            ("2026-10-02T12:00:00Z", None),
            ("2026-10-02T13:00:00Z", "ERROR"),
            ("2026-10-02T14:00:00Z", "SUCCESS"),
        ],
        comentarios=[("2026-10-02T15:00:00Z", MARCADOR + "VEREDITO: LIMPO")],
    )
    paginas = [
        _pagina(
            [
                _no_issue(
                    1,
                    eventos=[
                        {
                            "__typename": "AssignedEvent",
                            "createdAt": "2026-10-01T11:00:00Z",
                            "assignee": {"login": "bia"},
                        },
                        {"__typename": "ReopenedEvent", "createdAt": "2026-10-01T12:00:00Z"},
                    ],
                    prs=[pr],
                )
            ],
            proxima="CUR1",
        ),
        _pagina([_no_issue(2)]),
    ]

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return paginas[len(chamadas) - 1]

    monkeypatch.setattr(collect, "_run", run)
    linhas = collect._gh_timelines(DASH, "dono/repo")

    query = chamadas[0][chamadas[0].index("-f") + 1]
    assert "states:[OPEN]" in query
    assert "after=CUR1" in chamadas[1]
    assert set(linhas) == {1, 2}
    assert linhas[1]["eventos"] == [
        {"tipo": "designada", "em": "2026-10-01T11:00:00Z", "quem": "bia"},
        {"tipo": "reaberta", "em": "2026-10-01T12:00:00Z"},
    ]
    assert linhas[1]["prs"] == [
        {
            "number": 20,
            "state": "OPEN",
            "created_at": "2026-10-02T10:00:00Z",
            "closed_at": None,
            "merged_at": None,
            "head_ref": "feat/x-20",
            "ci_vermelho": 2,
            "ci_vermelho_em": "2026-10-02T13:00:00Z",
            "vereditos": [{"tipo": "revisao", "valor": "limpo", "em": "2026-10-02T15:00:00Z"}],
        }
    ]
    assert linhas[2] == {"eventos": [], "prs": []}


def test_branches_remotas_vem_do_ls_remote(monkeypatch):
    chamadas = []

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return "abc123\trefs/heads/main\ndef456\trefs/heads/feat/fases-941\n"

    monkeypatch.setattr(collect, "_run", run)
    assert collect._branches_remotas(DASH) == ["main", "feat/fases-941"]
    assert chamadas == [["git", "ls-remote", "--heads", "origin"]]


def test_ls_remote_falhando_devolve_lista_vazia(monkeypatch):
    def run(cmd, cwd, timeout=None):
        raise RuntimeError("offline")

    monkeypatch.setattr(collect, "_run", run)
    assert collect._branches_remotas(DASH) == []


def test_classe_do_pr_vem_dos_arquivos_do_squash_na_origin_main(monkeypatch):
    chamadas = []
    saida = (
        "\x00feat(ouvidoria): tela nova (#90)\n\nhospital-reunioes/frontend/a.tsx\ntools/x.py\n"
        "\x00chore(os): painel (#91)\n\ntools/workflow-dashboard/fases.py\nCONTEXT.md\n"
        "\x00refactor: tira do app (#92)\n\nhospital-reunioes/velho.py\nscripts/novo.py\n"
        "\x00chore: commit sem PR\n\nhospital-reunioes/b.py\n"
    )

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return saida

    monkeypatch.setattr(collect, "_run", run)
    assert collect._classes_dos_prs(DASH) == {90: "app", 91: "ferramenta", 92: "app"}
    assert chamadas[0][:2] == ["git", "log"] and "origin/main" in chamadas[0] and "--no-renames" in chamadas[0]


def test_git_log_falhando_deixa_a_classe_desconhecida(monkeypatch):
    def run(cmd, cwd, timeout=None):
        raise RuntimeError("sem git")

    monkeypatch.setattr(collect, "_run", run)
    assert collect._classes_dos_prs(DASH) == {}


# ---------- resumo funcional do PR (o hover do quadro) ----------

CORPO_NOVO = """## 💬 Resumo funcional

<!-- duas frases para quem não é dev -->
**O que é:** a Ata sai em PDF com um clique.
**Valor:** o secretário não precisa mais copiar para o Word.

## 🎯 Contexto

Pedido da diretoria.
"""

CORPO_ANTIGO = """<!-- template -->
## 🎯 Contexto

Decisão registrada neste PR: o `quadro` ganha uma coluna **Entregue**.

Por quê: o resto do texto longo.

## ✅ Critérios de aceite
"""


def test_resumo_funcional_le_o_que_e_e_valor_da_secao():
    assert collect.resumo_funcional(CORPO_NOVO) == {
        "o_que": "a Ata sai em PDF com um clique.",
        "valor": "o secretário não precisa mais copiar para o Word.",
        "contexto": None,
    }


def test_pr_antigo_sem_a_secao_cai_no_primeiro_paragrafo_do_contexto():
    assert collect.resumo_funcional(CORPO_ANTIGO) == {
        "o_que": None,
        "valor": None,
        "contexto": "Decisão registrada neste PR: o quadro ganha uma coluna Entregue.",
    }


def test_contexto_longo_e_cortado_e_corpo_vazio_nao_tem_resumo():
    longo = collect.resumo_funcional("## Contexto\n\n" + "palavra " * 80)
    assert len(longo["contexto"]) <= 241 and longo["contexto"].endswith("…")
    assert collect.resumo_funcional("") is None
    assert collect.resumo_funcional("<!-- só comentário -->") is None


def test_resumo_vem_dos_prs_recentes_numa_chamada_so(monkeypatch):
    chamadas = []

    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        return json.dumps([{"number": 11, "body": CORPO_NOVO}, {"number": 10, "body": ""}])

    monkeypatch.setattr(collect, "_run", run)
    prs = [{"number": 10}, {"number": 11}, {"number": 3}]
    collect._resumir_prs_recentes(DASH, prs)
    assert prs[1]["resumo"]["o_que"] == "a Ata sai em PDF com um clique."
    assert prs[0]["resumo"] is None and "resumo" not in prs[2]
    assert chamadas == [["gh", "pr", "list", "--state", "all", "--limit", "200", "--json", "number,body"]]


def test_falha_no_resumo_nao_derruba_os_prs(monkeypatch):
    def run(cmd, cwd, timeout=None):
        raise RuntimeError("HTTP 504")

    monkeypatch.setattr(collect, "_run", run)
    prs = [{"number": 10}]
    collect._resumir_prs_recentes(DASH, prs)
    assert prs == [{"number": 10}]


# ---------- coleta inteira ----------

ISSUES = [
    {
        "number": 1,
        "title": "Fatia",
        "state": "OPEN",
        "labels": [{"name": "in-progress"}],
        "createdAt": "2026-10-01T10:00:00Z",
        "closedAt": None,
        "assignees": [{"login": "bia"}],
        "author": {"login": "ana"},
        "body": "",
        "url": "i1",
    },
    {
        "number": 2,
        "title": "Outra",
        "state": "CLOSED",
        "labels": [],
        "createdAt": "2026-09-01T10:00:00Z",
        "closedAt": "2026-10-02T10:00:00Z",
        "assignees": [],
        "author": {"login": "ana"},
        "body": "",
        "url": "i2",
    },
]


def _fake_coleta(*, falha_gh=False, falha_timeline=False, git_log=None):
    def run(cmd, cwd, timeout=None):
        if cmd[0] == "git":
            if cmd[1] == "ls-remote":
                return "abc\trefs/heads/feat/x-1\n"
            if cmd[1] == "log" and git_log is not None:
                return git_log
            raise RuntimeError("sem origin")
        if falha_gh:
            raise RuntimeError("gh: To get started with GitHub CLI, please run:  gh auth login")
        if cmd[:3] == ["gh", "issue", "list"]:
            return json.dumps(ISSUES)
        if cmd[:3] == ["gh", "pr", "list"]:
            return json.dumps(PR_ABERTOS if "open" in cmd else PR_BASE)
        query = cmd[cmd.index("-f") + 1]
        if "closedByPullRequestsReferences" in query:
            if falha_timeline:
                raise RuntimeError("HTTP 502")
            return _pagina([_no_issue(1)])
        if "subIssues" in query or "blockedBy" in query:
            return _pagina([])
        return json.dumps({"data": {"repository": {"issues": {"nodes": []}}}})

    return run


def test_coleta_entrega_as_fases_no_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_run", _fake_coleta())
    data = collect.collect(tmp_path)
    fases = data["fases"]
    assert fases["issues"][1]["fase"] == "pr_aberto"
    assert fases["issues"][2]["fase"] == "mergeada"  # sem history.json no tmp, nenhuma versão
    assert fases["prs"][10]["fase"] == "ci_vermelho"
    assert fases["prs"][10]["conflito"] is True
    assert list(fases["timelines"]) == [1]
    assert fases["funil"]["total"]["pr_aberto"] == 1
    assert "plano" not in data  # o Plano saiu com a aba Issues nova (#942)
    json.dumps(data)  # o /api/data serializa o payload inteiro


def test_coleta_marca_a_classe_do_pr_mergeado_e_ferramenta_fica_entregue(monkeypatch, tmp_path):
    git_log = "\x00chore(os): painel (#11)\n\ntools/workflow-dashboard/app.js\n"
    monkeypatch.setattr(collect, "_run", _fake_coleta(git_log=git_log))
    data = collect.collect(tmp_path)
    classes = {p["number"]: p.get("classe") for p in data["github"]["prs"]}
    assert classes == {10: None, 11: "ferramenta"}
    assert data["fases"]["prs"][11]["fase"] == "entregue"


def test_erro_do_gh_degrada_sem_derrubar_o_payload(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_run", _fake_coleta(falha_gh=True))
    data = collect.collect(tmp_path)
    assert data["github"]["error_kind"] == "unauth"
    assert data["fases"] is None


def test_timeline_falhando_nao_derruba_as_fases(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_run", _fake_coleta(falha_timeline=True))
    fases = collect.collect(tmp_path)["fases"]
    assert fases["issues"][1]["fase"] == "pr_aberto"
    assert fases["timelines"] == {}


def test_resumo_do_coletor_imprime_as_contagens_do_funil():
    fases = {"funil": {"total": {"triagem": 3, "fila": 2, "em_producao": 40}}}
    linhas = collect._linhas_do_funil(fases)
    assert linhas == ["funil       triagem 3 · fila 2 · em_producao 40"]
    assert collect._linhas_do_funil(None) == ["funil       indisponível (gh)"]


# ---------- timeline sob demanda ----------


def _fake_timeline_issue(chamadas, *, erro=None):
    def run(cmd, cwd, timeout=None):
        chamadas.append(cmd)
        if cmd[0] == "git":
            raise RuntimeError("sem origin")
        if erro:
            raise RuntimeError(erro)
        no = _no_issue(5, prs=[_no_pr(55, rollups=[("2026-10-02T11:00:00Z", "FAILURE")])])
        no["closedAt"] = "2026-10-03T10:00:00Z"
        return json.dumps({"data": {"repository": {"issue": no}}})

    return run


def test_timeline_de_issue_fechada_sai_sob_demanda(monkeypatch, tmp_path):
    chamadas = []
    monkeypatch.setattr(collect, "_run", _fake_timeline_issue(chamadas))
    out = collect.issue_timeline(tmp_path, 5)
    assert out["error"] is None
    assert [e["tipo"] for e in out["timeline"]] == ["criada", "pr_aberto", "ci_vermelho"]
    gh = [c for c in chamadas if c[0] == "gh"]
    assert len(gh) == 1 and "number=5" in gh[0]


def test_timeline_sob_demanda_com_erro_amigavel(monkeypatch, tmp_path):
    monkeypatch.setattr(collect, "_run", _fake_timeline_issue([], erro="gh: not logged in, run gh auth login"))
    out = collect.issue_timeline(tmp_path, 5)
    assert out["timeline"] == []
    assert out["error"].startswith("gh não autenticado")


def test_rota_da_timeline_responde_pelo_servidor(monkeypatch):
    import serve

    monkeypatch.setattr(
        serve.collector,
        "issue_timeline",
        lambda root, n: {"number": n, "error": None, "timeline": [{"tipo": "criada"}]},
    )
    servidor = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{servidor.server_address[1]}/api/issue/77/timeline"
        with urllib.request.urlopen(url, timeout=5) as resp:
            corpo = json.loads(resp.read())
    finally:
        servidor.shutdown()
    assert corpo == {"number": 77, "error": None, "timeline": [{"tipo": "criada"}]}
