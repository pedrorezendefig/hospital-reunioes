"""O bloco `supabase` do state.json regravado a cada deploy pelo health do backend.

O supabase não faz deploy nem tem HTTP próprio: o rabo nunca o tocava e o
semáforo do painel ficava âmbar para sempre. O `/api/health` do backend só
responde ok com o banco respondendo e diz como ele está no campo `db`: é dele
que o `montar_registro` deriva o status do supabase, mantendo `last_deploy_*`
como estão. A entrada nova leva `etapas` (o que o rabo mediu) e `responsavel`
(quem o rodou), e o esquema do `tools/aplicar_registro.py` tem que aceitá-la.

Mutante que fica vermelho aqui: quem esquece de regravar o bloco (o state de
partida vem sempre com o status oposto ao esperado).
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SCRIPTS = RAIZ / ".claude" / "skills" / "onda-enxuta" / "scripts"
TOOLS = RAIZ / "tools"

CHECK_VELHO = {"at": "2026-09-23T13:21:42-03:00", "latency_ms": None, "http_status": None, "body_ok": False}
PR = {"number": 7, "title": "fix(x): prazo", "closingIssuesReferences": [{"number": 5}]}
ETAPAS = {"merge_s": 3, "build_s": {"backend": 34}, "health_s": 1}


def carregar(nome: str, pasta: Path):
    sys.path.insert(0, str(pasta))
    try:
        sys.modules.pop(nome, None)
        return __import__(nome)
    finally:
        sys.path.remove(str(pasta))


def state_com_supabase(status: str) -> dict:
    return {
        "last_app_version": "0.10.0",
        "services": [
            {"id": "backend", "last_deploy_sha": "9" * 40},
            {"id": "frontend"},
            {
                "id": "supabase",
                "status": status,
                "last_deploy_sha": "93870744",
                "last_deploy_at": "2026-09-23T13:21:42-03:00",
                "last_health_check": dict(CHECK_VELHO),
            },
        ],
    }


def montar(fo, state: dict, backend: dict) -> dict:
    return fo.montar_registro(
        state,
        "pr-7",
        [PR],
        "0.10.1",
        "a" * 40,
        [],
        [],
        ["backend"],
        {"backend": 34},
        {"backend": backend},
        "healthy",
        ["backend"],
        avulso=True,
        etapas=ETAPAS,
        responsavel="ana",
    )


def supabase(registro: dict) -> dict:
    return next(s for s in registro["state"]["services"] if s["id"] == "supabase")


@pytest.mark.parametrize(
    "backend",
    [
        {"ok": True, "status": 200, "latency_ms": 148, "db": "healthy"},
        {"ok": True, "status": 200, "latency_ms": 148},  # health antigo, sem o campo `db`: o ok basta
    ],
    ids=["db-healthy", "sem-campo-db"],
)
def test_backend_ok_deixa_o_supabase_healthy_com_o_check_do_mesmo_instante(backend):
    fo = carregar("fechar_onda", SCRIPTS)
    state = state_com_supabase("warning")

    registro = montar(fo, state, backend)

    sb = supabase(registro)
    assert sb["status"] == "healthy"
    assert sb["last_health_check"] == {
        "at": registro["entrada"]["at"],
        "latency_ms": None,
        "http_status": None,
        "body_ok": True,
    }
    # o supabase não faz deploy: o rastro do último fica
    assert (sb["last_deploy_sha"], sb["last_deploy_at"]) == ("93870744", "2026-09-23T13:21:42-03:00")


@pytest.mark.parametrize(
    "backend",
    [
        {"ok": False, "status": 503, "latency_ms": 5, "db": "degraded"},
        {"ok": True, "status": 200, "latency_ms": 5, "db": "degraded"},  # o campo explícito manda
    ],
    ids=["health-ruim", "db-degraded"],
)
def test_banco_ruim_no_health_do_backend_deixa_o_supabase_warning(backend):
    fo = carregar("fechar_onda", SCRIPTS)
    state = state_com_supabase("healthy")

    registro = montar(fo, state, backend)

    sb = supabase(registro)
    assert sb["status"] == "warning"
    assert sb["last_health_check"]["body_ok"] is False
    assert sb["last_health_check"]["at"] == registro["entrada"]["at"]


def test_bloco_do_supabase_nao_ganha_chave_nova_e_os_outros_apps_ficam_como_antes():
    """O `aplicar_registro.py` confere as chaves do state: o bloco regravado tem
    as mesmas chaves do que estava na main."""
    fo = carregar("fechar_onda", SCRIPTS)
    state = state_com_supabase("warning")
    antes = copy.deepcopy(state)

    registro = montar(fo, state, {"ok": True, "status": 200, "latency_ms": 148, "db": "healthy"})

    assert set(supabase(registro)) == set(supabase({"state": antes}))
    frontend = next(s for s in registro["state"]["services"] if s["id"] == "frontend")
    assert frontend == {"id": "frontend"}  # fora do lote e sem health: intocado


def test_entrada_leva_etapas_e_responsavel_e_passa_no_esquema_da_action():
    fo = carregar("fechar_onda", SCRIPTS)
    ar = carregar("aplicar_registro", TOOLS)

    registro = montar(fo, state_com_supabase("warning"), {"ok": True, "status": 200, "latency_ms": 148})

    entrada = registro["entrada"]
    assert entrada["etapas"] == ETAPAS and entrada["responsavel"] == "ana"
    assert ar.validar_entrada(entrada) is entrada
    assert set(ar.ENTRADA) == set(entrada)


def test_checar_health_le_o_campo_db_do_corpo(monkeypatch):
    fo = carregar("fechar_onda", SCRIPTS)
    corpo = b'{"status":"healthy","db":"healthy","app":"a","version":"0.10.1","migracao":114}'

    class Resposta:
        status = 200

        def __init__(self, b):
            self.b = b

        def read(self):
            return self.b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(fo.urllib.request, "urlopen", lambda req, timeout: Resposta(corpo))
    service = {
        "deploy": {
            "health_check": {
                "url": "https://exemplo.invalid/api/health",
                "expected_status": 200,
                "expected_body_regex": r'^\{"status":"(healthy|degraded)","db":"(healthy|degraded)".*\}$',
            }
        }
    }

    h = fo.checar_health(service, "0.10.1")

    assert h["ok"] is True and h["db"] == "healthy"


def test_quem_roda_vem_do_gh_api_user_e_degrada_para_um_nome_que_o_esquema_aceita(monkeypatch):
    fo = carregar("fechar_onda", SCRIPTS)
    ar = carregar("aplicar_registro", TOOLS)

    monkeypatch.setattr(fo, "gh_json", lambda args, cwd=None: {"login": "pedrorezendefig"})
    assert fo.quem_roda(RAIZ) == "pedrorezendefig"

    def falha(args, cwd=None):
        raise RuntimeError("gh: 502")

    monkeypatch.setattr(fo, "gh_json", falha)
    assert ar.ENTRADA["responsavel"](fo.quem_roda(RAIZ))
