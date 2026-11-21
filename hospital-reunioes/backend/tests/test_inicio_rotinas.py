"""As Rotinas no Início (issue #1944, PRD #1932; ADR 0104 e ADR 0098, decisão 9).

O trilho mostra as Rotinas do ciclo corrente de quem é o responsável, com
quantas já têm Verificação. Realizada é um clique na Minha Fila; Não realizada
leva à tela da Rotina, que pede a Anotação. O ciclo que fechou sem marca fica
em Passou do prazo e ainda se marca. A Rotina a revisar (a revisão de 90 dias
do Facilitador, decisão 72 da #1757) entra na fila dele, e Manter é um clique.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# O banco de mentira das Rotinas (issue #1874) e os fixtures dele.
from test_rotina_verificacao import (  # noqa: E402, F401
    ADMIN,
    ANA,
    OUTRO,
    PEDRO,
    RT1,
    D,
    _sb_com_rotina,
    cliente_das_rotinas,
    fila,
    hoje,
)

RT2 = "00000000-0000-0000-0000-0000000000a2"


def _com_duas_rotinas_da_ana():
    """RT1 semanal (desde 23/11) e RT2 quinzenal (desde 16/11), as duas da Ana."""
    sb = _sb_com_rotina()
    sb.rotinas.append(
        {
            **sb.rotinas[0],
            "id": RT2,
            "quadro_pos": 2,
            "descricao": "Conferir o carrinho de parada",
            "frequencia": "QUINZENAL",
            "comeca_em": "2026-11-16",
        }
    )
    return sb


def _do_ciclo(resposta) -> list[tuple]:
    return [
        (r.titulo, r.ciclo_inicio.isoformat(), r.ciclo_fim.isoformat(), r.verificacao)
        for r in resposta.rotinas_do_ciclo
    ]


# ─── 1. O trilho: as Rotinas do ciclo corrente e o progresso ─────────────────


def test_o_trilho_mostra_as_rotinas_do_ciclo_com_quais_ja_tem_verificacao(fila, cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2026-11-25")
    sb = _com_duas_rotinas_da_ana()
    assert cliente_das_rotinas(sb, ANA).post(f"/api/rotinas/{RT1}/ciclos/2026-11-23/realizada").status_code == 201

    resposta = fila(sb, ANA, "2026-11-25")

    assert sorted(_do_ciclo(resposta)) == [
        ("Conferir o carrinho de parada", "2026-11-16", "2026-11-30", None),
        ("Reunir a equipe", "2026-11-23", "2026-11-29", "REALIZADA"),
    ]
    [rotina] = [r for r in resposta.rotinas_do_ciclo if r.id == RT1]
    assert rotina.destino == f"/rotinas#rotina-{RT1}"


# ─── 2. Realizada é um clique; Não realizada leva à tela da Rotina ───────────


def test_realizada_e_um_clique_e_nao_realizada_leva_a_tela_da_rotina(fila, cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2026-11-25")
    sb = _sb_com_rotina()

    [item] = [i for i in fila(sb, ANA, "2026-11-25").itens if i.tipo == "verificacao_da_rotina"]

    assert (item.acao_de_um_clique.rotulo, item.acao_de_um_clique.endpoint) == (
        "Realizada",
        f"/api/rotinas/{RT1}/ciclos/2026-11-23/realizada",
    )
    assert (item.acao_secundaria.rotulo, item.acao_secundaria.destino) == (
        "Não realizada",
        f"/rotinas#rotina-{RT1}",
    )
    # O clique grava a Verificação pela rota que o Início mandou.
    r = cliente_das_rotinas(sb, ANA).post(item.acao_de_um_clique.endpoint)
    assert r.status_code == 201, r.text
    assert [(v["resultado"], v["atrasada"]) for v in sb.rotina_verificacoes] == [("REALIZADA", False)]
    resposta = fila(sb, ANA, "2026-11-25")
    assert [i for i in resposta.itens if i.tipo == "verificacao_da_rotina"] == []
    assert [r.verificacao for r in resposta.rotinas_do_ciclo] == ["REALIZADA"]


# ─── 3. O ciclo encerrado sem marca: Passou do prazo, e ainda se marca ───────


def test_o_ciclo_encerrado_sem_marca_passou_do_prazo_e_ainda_se_marca_do_inicio(fila, cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2026-12-02")
    sb = _sb_com_rotina()

    resposta = fila(sb, ANA, "2026-12-02")
    [vencida] = [i for i in resposta.itens if i.tipo == "verificacao_da_rotina" and i.grupo == "passou_do_prazo"]
    assert (vencida.prazo.isoformat(), vencida.dias_de_atraso) == ("2026-11-29", 3)
    assert resposta.contadores.passou_do_prazo == 1

    r = cliente_das_rotinas(sb, ANA).post(vencida.acao_de_um_clique.endpoint)

    assert r.status_code == 201, r.text
    assert [(v["ciclo_inicio"], v["atrasada"]) for v in sb.rotina_verificacoes] == [("2026-11-23", True)]
    assert fila(sb, ANA, "2026-12-02").contadores.passou_do_prazo == 0


# ─── 5. Só o responsável vê e marca no Início, papel por papel ───────────────


@pytest.mark.parametrize(
    ("quem", "ve"),
    [
        (ANA, True),  # a responsável
        (PEDRO, False),  # o Facilitador da Reunião marca na tela das Rotinas, não no Início
        (ADMIN, False),  # o Super admin
        (OUTRO, False),  # quem não tem vínculo com a Rotina
    ],
    ids=["responsavel", "facilitador", "super_admin", "outro"],
)
def test_so_o_responsavel_ve_a_rotina_do_ciclo_no_inicio(fila, quem, ve):  # noqa: F811
    sb = _sb_com_rotina()

    resposta = fila(sb, quem, "2026-11-25")

    verificacoes = [i for i in resposta.itens if i.tipo == "verificacao_da_rotina"]
    assert (len(verificacoes), len(resposta.rotinas_do_ciclo)) == ((1, 1) if ve else (0, 0))


def test_quem_nao_tem_vinculo_nao_marca_pela_rota_do_inicio(fila, cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2026-11-25")
    sb = _sb_com_rotina()
    [item] = [i for i in fila(sb, ANA, "2026-11-25").itens if i.tipo == "verificacao_da_rotina"]

    r = cliente_das_rotinas(sb, OUTRO).post(item.acao_de_um_clique.endpoint)

    assert r.status_code == 404
    assert sb.rotina_verificacoes == []


# ─── 4. A Rotina a revisar, na fila do Facilitador ───────────────────────────


def _a_revisar(resposta) -> list[tuple]:
    return [(i.id, i.prazo.isoformat(), i.grupo) for i in resposta.itens if i.tipo == "rotina_a_revisar"]


def test_a_rotina_a_revisar_aparece_na_fila_do_facilitador_aos_90_dias(fila):  # noqa: F811
    # Nasceu no envio da Ata de 20/11/2026: a revisão vence 90 dias depois.
    sb = _sb_com_rotina(created_at="2026-11-20T14:00:00+00:00")

    assert _a_revisar(fila(sb, PEDRO, "2027-02-17")) == [(RT1, "2027-02-18", "ate_48_horas")]
    vencida = fila(sb, PEDRO, "2027-03-01")
    assert _a_revisar(vencida) == [(RT1, "2027-02-18", "passou_do_prazo")]
    [item] = [i for i in vencida.itens if i.tipo == "rotina_a_revisar"]
    assert item.titulo == "Reunir a equipe"
    assert (item.acao_de_um_clique.rotulo, item.acao_de_um_clique.endpoint) == ("Manter", f"/api/rotinas/{RT1}/manter")
    assert (item.acao_secundaria.rotulo, item.acao_secundaria.destino) == ("Encerrar", f"/rotinas#rotina-{RT1}")


@pytest.mark.parametrize("quem", [ANA, ADMIN, OUTRO], ids=["responsavel", "super_admin", "outro"])
def test_a_rotina_a_revisar_nao_aparece_para_quem_nao_e_o_facilitador(fila, quem):  # noqa: F811
    sb = _sb_com_rotina(created_at="2026-11-20T14:00:00+00:00")

    assert _a_revisar(fila(sb, quem, "2027-03-01")) == []


def test_rotina_encerrada_nao_pede_revisao(fila):  # noqa: F811
    sb = _sb_com_rotina(
        created_at="2026-11-20T14:00:00+00:00",
        status="ENCERRADA",
        encerrada_em="2026-12-10",
        anotacao_encerramento="Acabou.",
    )

    assert _a_revisar(fila(sb, PEDRO, "2027-03-01")) == []


def test_rotina_sem_frequencia_espera_a_escolha_e_nao_a_revisao(fila):  # noqa: F811
    # O fluxo contínuo convertido (issue #1877) tem a própria linha na fila.
    sb = _sb_com_rotina(created_at="2026-11-20T14:00:00+00:00", frequencia=None, comeca_em=None)

    resposta = fila(sb, PEDRO, "2027-03-01")

    assert _a_revisar(resposta) == []
    assert [i.tipo for i in resposta.itens] == ["frequencia_da_rotina"]


def test_manter_e_um_clique_do_facilitador_e_a_proxima_revisao_vem_90_dias_depois(fila, cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2027-03-01")
    sb = _sb_com_rotina(created_at="2026-11-20T14:00:00+00:00")

    r = cliente_das_rotinas(sb, PEDRO).post(f"/api/rotinas/{RT1}/manter")

    assert r.status_code == 200, r.text
    [rotina] = sb.rotinas
    assert (rotina["revisada_em"], rotina["revisada_por_nome"], rotina["status"]) == (
        "2027-03-01",
        "Pedro Rezende",
        "ATIVA",
    )
    # A revisão passa para 90 dias depois e sai dos grupos da fila.
    assert _a_revisar(fila(sb, PEDRO, "2027-03-01")) == [(RT1, "2027-05-30", None)]
    assert _a_revisar(fila(sb, PEDRO, "2027-05-29")) == [(RT1, "2027-05-30", "ate_48_horas")]


@pytest.mark.parametrize(
    ("quem", "status"),
    [(PEDRO, 200), (ADMIN, 200), (ANA, 403), (OUTRO, 404)],
    ids=["facilitador", "super_admin", "responsavel", "outro"],
)
def test_so_o_facilitador_e_o_super_admin_mantem_a_rotina(cliente_das_rotinas, hoje, quem, status):  # noqa: F811
    hoje["valor"] = D("2027-03-01")
    sb = _sb_com_rotina(created_at="2026-11-20T14:00:00+00:00")

    r = cliente_das_rotinas(sb, quem).post(f"/api/rotinas/{RT1}/manter")

    assert r.status_code == status, r.text
    assert (sb.rotinas[0].get("revisada_em") is not None) == (status == 200)


def test_rotina_encerrada_nao_se_mantem(cliente_das_rotinas, hoje):  # noqa: F811
    hoje["valor"] = D("2027-03-01")
    sb = _sb_com_rotina(status="ENCERRADA", encerrada_em="2026-12-10", anotacao_encerramento="Acabou.")

    r = cliente_das_rotinas(sb, PEDRO).post(f"/api/rotinas/{RT1}/manter")

    assert r.status_code == 409
    assert sb.rotinas[0].get("revisada_em") is None


# ─── 6. O kit de conhecimento ────────────────────────────────────────────────


def test_o_texto_de_reunioes_no_kit_diz_as_rotinas_no_inicio():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = (CONHECIMENTO_DIR / "reunioes.md").read_text(encoding="utf-8")
    assert "o trilho do Início mostra as rotinas do ciclo de agora" in texto
    assert "quantas já têm a verificação marcada" in texto
    assert "Não realizada leva à tela Rotinas, que pede a anotação" in texto
    assert "a revisão aparece no Início do facilitador" in texto
    assert "Manter é um clique" in texto
