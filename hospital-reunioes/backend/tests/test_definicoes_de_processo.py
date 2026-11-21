"""As Definições de processo do setor (ADR 0098, decisão 9; issue #1875).

No envio da Ata, a linha do tipo Processo entra na lista do setor da Reunião,
com o trecho da Ata copiado. Cuidam da lista os Facilitadores das Reuniões do
setor, até o organograma; o Super admin vê todas e a Secretária não vê. Tiram
um item o Facilitador da Reunião de onde ele saiu e o Super admin, sempre com
anotação: o item sai da lista e fica registrado.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O `make_client` importado registra a fábrica de TestClient do envio aqui.
from test_pendencia_nasce_no_envio import _sb, make_client  # noqa: E402, F401


@pytest.fixture
def cliente(request):
    return request.getfixturevalue("make_client")


def _sem_clicksign(monkeypatch):
    from app.services import clicksign_service

    monkeypatch.setattr(clicksign_service, "start_signature_flow", lambda *_a, **_kw: None)


QUADRO = [
    {"acao": "Comprar insumos", "responsavel": "Pedro Rezende", "prazo": "2026-12-10", "tipo": "ACAO"},
    {
        "acao": "Toda alta passa pelo checklist de medicação",
        "responsavel": None,
        "objetivo_meta": "Evitar erro de dose na alta",
        "tipo": "PROCESSO",
    },
    {"acao": "Ligar para o fornecedor", "responsavel": "Ana Lima"},
]


def _sb_com_quadro():
    sb = _sb(setor_id="S-ENF")
    sb.reunioes[0]["json_ata"] = {"quadro_atribuicoes": [dict(a) for a in QUADRO]}
    return sb


# ─── 1. O item nasce no envio da Ata ─────────────────────────────────────────


@pytest.mark.parametrize("rota", ["aprovar", "aprovar-sem-assinatura"])
def test_enviar_ata_com_linha_de_processo_cria_o_item_com_o_trecho_copiado(cliente, monkeypatch, rota):
    _sem_clicksign(monkeypatch)
    sb = _sb_com_quadro()

    r = cliente(sb).post(f"/api/reunioes/R1/{rota}")

    assert r.status_code == 200, r.text
    [item] = sb.definicoes_processo
    assert (item["id_reuniao"], item["quadro_pos"], item["trecho"], item["objetivo"], item["status"]) == (
        "R1",
        1,
        "Toda alta passa pelo checklist de medicação",
        "Evitar erro de dose na alta",
        "ATIVA",
    )
    # O Processo não vira Pendência (#1872).
    assert sorted(p["quadro_pos"] for p in sb.pendencias) == [0, 2]


def test_reenviar_nao_repete_o_item(cliente, monkeypatch):
    from app.services import pendencia_service

    _sem_clicksign(monkeypatch)
    sb = _sb_com_quadro()
    assert cliente(sb).post("/api/reunioes/R1/aprovar").status_code == 200

    pendencia_service.liberar_pendencias(sb, "R1", origem="RECONCILIACAO")

    assert len(sb.definicoes_processo) == 1


# ─── 2. Quem vê a lista ──────────────────────────────────────────────────────

PEDRO = {"id": "P1", "nome_completo": "Pedro Rezende", "email": "pedro@hsm.com", "access_profile": "regular"}
ANA = {"id": "P2", "nome_completo": "Ana Lima", "email": "ana@hsm.com", "access_profile": "regular"}
CARLOS = {"id": "P3", "nome_completo": "Carlos Souza", "email": "carlos@hsm.com", "access_profile": "regular"}
ADMIN = {"id": "P9", "nome_completo": "Diretoria", "email": "dir@hsm.com", "access_profile": "super_admin"}
SECRETARIA = {"id": "P8", "nome_completo": "Rita Sec", "email": "rita@hsm.com", "access_profile": "secretaria"}


def _reuniao(id_reuniao: str, titulo: str, setor_id: str | None, facilitador_id: str) -> dict:
    return {
        "id_reuniao": id_reuniao,
        "titulo": titulo,
        "data": "2026-11-10",
        "setor_id": setor_id,
        "facilitador_id": facilitador_id,
    }


# O nome curto do teste e o UUID que o banco guarda.
UUID_DE = {f"D{n}": f"00000000-0000-0000-0000-00000000000{n}" for n in range(1, 6)}
NOME_DE = {v: k for k, v in UUID_DE.items()}


def _rota_retirar(nome: str) -> str:
    return f"/api/definicoes-processo/{UUID_DE[nome]}/retirar"


def _item(id_: str, id_reuniao: str, trecho: str, status: str = "ATIVA") -> dict:
    return {
        "id": UUID_DE[id_],
        "id_reuniao": id_reuniao,
        "quadro_pos": 0,
        "trecho": trecho,
        "objetivo": None,
        "status": status,
        "created_at": "2026-11-14T12:00:00+00:00",
        "retirada_em": None,
        "retirada_por_id": None,
        "retirada_por_nome": None,
        "anotacao_retirada": None,
    }


def _sb_com_lista():
    """Duas Reuniões da Enfermagem (Pedro e Ana conduzem uma cada), uma do
    Faturamento (Carlos) e uma antiga sem setor (Pedro). D5 já saiu da lista."""
    sb = _sb()
    sb.setores = [{"id": "S-ENF", "nome": "Enfermagem"}, {"id": "S-FAT", "nome": "Faturamento"}]
    sb.reunioes = [
        _reuniao("R1", "Enfermagem semanal", "S-ENF", "P1"),
        _reuniao("R2", "Enfermagem mensal", "S-ENF", "P2"),
        _reuniao("R3", "Fechamento de contas", "S-FAT", "P3"),
        _reuniao("R4", "Reunião antiga", None, "P1"),
    ]
    sb.definicoes_processo = [
        _item("D1", "R1", "Toda alta passa pelo checklist"),
        _item("D2", "R2", "Passagem de plantão à beira do leito"),
        _item("D3", "R3", "Conta fecha em 48 horas"),
        _item("D4", "R4", "Escala sai na sexta"),
        _item("D5", "R2", "Regra que deixou de valer", status="RETIRADA"),
    ]
    return sb


@pytest.fixture
def cliente_da_lista(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.dependencies import get_current_user, get_supabase_client, require_acesso_reunioes
    from app.routers import definicoes_processo as rota

    def _factory(sb, quem: dict, ocultas: list[str] | None = None) -> TestClient:
        app = FastAPI()
        app.include_router(rota.router, prefix="/api")
        app.dependency_overrides[get_current_user] = lambda: {"id": "auth", "email": quem["email"]}
        app.dependency_overrides[get_supabase_client] = lambda: sb
        app.dependency_overrides[require_acesso_reunioes] = lambda: None

        async def _me(*_a, **_kw):
            return dict(quem)

        monkeypatch.setattr(rota, "get_participante_for_user", _me)
        monkeypatch.setattr(rota, "reunioes_ocultas", lambda *_a, **_kw: list(ocultas or []))
        return TestClient(app)

    return _factory


def _ids(resposta) -> list[str]:
    assert resposta.status_code == 200, resposta.text
    return sorted(NOME_DE[item["id"]] for item in resposta.json())


def test_facilitador_de_reuniao_do_setor_ve_a_lista_do_setor_e_nao_a_dos_outros(cliente_da_lista):
    sb = _sb_com_lista()

    # Ana conduz só a R2, e vê também o que saiu da R1, que é do mesmo setor.
    assert _ids(cliente_da_lista(sb, ANA).get("/api/definicoes-processo")) == ["D1", "D2"]
    # Pedro vê a Enfermagem e o item da Reunião antiga sem setor que ele conduziu.
    assert _ids(cliente_da_lista(sb, PEDRO).get("/api/definicoes-processo")) == ["D1", "D2", "D4"]
    assert _ids(cliente_da_lista(sb, CARLOS).get("/api/definicoes-processo")) == ["D3"]


def test_a_lista_traz_o_setor_a_reuniao_e_o_trecho(cliente_da_lista):
    r = cliente_da_lista(_sb_com_lista(), CARLOS).get("/api/definicoes-processo")

    [item] = r.json()
    assert (item["setor_nome"], item["reuniao_titulo"], item["trecho"]) == (
        "Faturamento",
        "Fechamento de contas",
        "Conta fecha em 48 horas",
    )


def test_super_admin_ve_todas_as_listas_menos_as_reunioes_ocultas(cliente_da_lista):
    sb = _sb_com_lista()

    assert _ids(cliente_da_lista(sb, ADMIN).get("/api/definicoes-processo")) == ["D1", "D2", "D3", "D4"]
    assert _ids(cliente_da_lista(sb, ADMIN, ocultas=["R3"]).get("/api/definicoes-processo")) == ["D1", "D2", "D4"]


def test_secretaria_recebe_403_na_lista_e_ao_tirar_item(cliente_da_lista):
    sb = _sb_com_lista()
    cliente = cliente_da_lista(sb, SECRETARIA)

    assert cliente.get("/api/definicoes-processo").status_code == 403
    assert cliente.post(_rota_retirar("D1"), json={"anotacao": "Repetido"}).status_code == 403
    assert sb.definicoes_processo[0]["status"] == "ATIVA"


# ─── 3. Tirar um item da lista ───────────────────────────────────────────────


@pytest.mark.parametrize("anotacao", [None, "", "   "])
def test_tirar_item_sem_anotacao_e_recusado(cliente_da_lista, anotacao):
    sb = _sb_com_lista()

    r = cliente_da_lista(sb, PEDRO).post(_rota_retirar("D1"), json={"anotacao": anotacao})

    assert r.status_code == 422
    assert sb.definicoes_processo[0]["status"] == "ATIVA"


def test_facilitador_da_reuniao_de_origem_tira_o_item_e_ele_fica_registrado(cliente_da_lista):
    sb = _sb_com_lista()
    cliente = cliente_da_lista(sb, PEDRO)

    r = cliente.post(_rota_retirar("D1"), json={"anotacao": "  Repetido da D2  "})

    assert r.status_code == 200, r.text
    d1 = sb.definicoes_processo[0]
    assert (d1["status"], d1["anotacao_retirada"], d1["retirada_por_id"], d1["retirada_por_nome"]) == (
        "RETIRADA",
        "Repetido da D2",
        "P1",
        "Pedro Rezende",
    )
    assert d1["retirada_em"]
    assert _ids(cliente.get("/api/definicoes-processo")) == ["D2", "D4"]


def test_facilitador_de_outra_reuniao_do_setor_ve_mas_nao_tira(cliente_da_lista):
    sb = _sb_com_lista()
    cliente = cliente_da_lista(sb, ANA)

    [d1] = [i for i in cliente.get("/api/definicoes-processo").json() if i["id"] == UUID_DE["D1"]]
    r = cliente.post(_rota_retirar("D1"), json={"anotacao": "Repetido"})

    assert d1["pode_retirar"] is False
    assert r.status_code == 403
    assert sb.definicoes_processo[0]["status"] == "ATIVA"


def test_super_admin_tira_item_de_qualquer_setor(cliente_da_lista):
    sb = _sb_com_lista()

    r = cliente_da_lista(sb, ADMIN).post(_rota_retirar("D3"), json={"anotacao": "Deixou de valer"})

    assert r.status_code == 200, r.text
    assert sb.definicoes_processo[2]["status"] == "RETIRADA"


def test_quem_nao_ve_o_item_recebe_404_e_o_retirado_nao_sai_duas_vezes(cliente_da_lista):
    sb = _sb_com_lista()

    fora = cliente_da_lista(sb, CARLOS).post(_rota_retirar("D1"), json={"anotacao": "x"})
    oculto = cliente_da_lista(sb, ADMIN, ocultas=["R3"]).post(_rota_retirar("D3"), json={"anotacao": "x"})
    de_novo = cliente_da_lista(sb, ADMIN).post(_rota_retirar("D5"), json={"anotacao": "x"})

    assert (fora.status_code, oculto.status_code, de_novo.status_code) == (404, 404, 409)
    assert sb.definicoes_processo[0]["status"] == "ATIVA"


# ─── 4. O kit de conhecimento ────────────────────────────────────────────────


def test_o_texto_de_reunioes_no_kit_diz_a_lista_de_definicoes_de_processo():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "reunioes.md").read_text(encoding="utf-8")
    secao = texto.split("## As definições de processo do setor", 1)[1].split("\n## ", 1)[0]
    assert "entra na lista de definições de processo do setor da reunião, com o trecho da ata copiado" in secao
    assert "cuidam da lista os facilitadores das reuniões do setor" in secao
    assert "os outros setores não aparecem para ele" in secao
    assert "Quem administra o aplicativo vê as listas de todos os setores" in secao
    assert "A Secretária não vê a lista." in secao
    assert "pede uma anotação" in secao
    assert "Só tiram o facilitador da reunião de onde o item saiu e quem administra o aplicativo." in secao
    assert "nem lembrete" in secao
