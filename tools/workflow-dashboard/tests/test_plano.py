"""Testes do módulo plano — o cérebro do Plano vivo do dashboard.

Comportamento externo apenas: issues (como o collect.py as produz) entram,
estrutura do Plano sai. Sem rede, sem gh, sem filesystem.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from plano import bloqueios_do_corpo, montar_plano  # noqa: E402


def _issue(
    number,
    *,
    title=None,
    state="OPEN",
    labels=(),
    blocked_by=(),
    parent=None,
    children=(),
    is_prd=False,
    created_at=None,
    closed_at=None,
    claimed_at=None,
    assignees=(),
    body="",
):
    """Issue no shape que o collect.py entrega ao módulo."""
    return {
        "number": number,
        "title": title or f"Fatia #{number}",
        "state": state,
        "labels": list(labels),
        "created_at": created_at,
        "closed_at": closed_at,
        "claimed_at": claimed_at,
        "assignees": list(assignees),
        "url": f"https://github.com/x/y/issues/{number}",
        "body": body,
        "blocked_by": sorted(blocked_by),
        "parent": parent,
        "children": sorted(children),
        "is_prd": is_prd,
        "criteria": {"done": 0, "total": 0},
    }


def test_sem_prd_ativo_devolve_estado_vazio():
    plano = montar_plano([])
    assert plano["levas"] == []


def test_cadeia_serial_vira_ondas_na_ordem_de_dependencia():
    issues = [
        _issue(10, title="PRD: leva X", is_prd=True, children=[11, 12]),
        _issue(11, parent=10),
        _issue(12, parent=10, blocked_by=[11]),
    ]
    plano = montar_plano(issues)

    assert len(plano["levas"]) == 1
    leva = plano["levas"][0]
    assert leva["prd"]["number"] == 10
    ondas = [[f["number"] for f in onda] for onda in leva["ondas"]]
    assert ondas == [[11], [12]]


def test_fatias_bloqueadas_pela_mesma_dependencia_compartilham_onda():
    issues = [
        _issue(20, is_prd=True, children=[21, 22, 23, 24, 25]),
        _issue(21, parent=20),
        _issue(22, parent=20, blocked_by=[21]),
        _issue(23, parent=20, blocked_by=[22]),
        _issue(24, parent=20, blocked_by=[22]),
        _issue(25, parent=20, blocked_by=[23, 24]),
    ]
    ondas = [[f["number"] for f in onda] for onda in montar_plano(issues)["levas"][0]["ondas"]]
    assert ondas == [[21], [22], [23, 24], [25]]


def test_dependencia_fechada_conta_como_satisfeita_e_vai_para_concluidas():
    issues = [
        _issue(30, is_prd=True, children=[31, 32]),
        _issue(31, parent=30, state="CLOSED", created_at="2026-06-01T10:00:00Z", closed_at="2026-06-01T13:00:00Z"),
        _issue(32, parent=30, blocked_by=[31]),
    ]
    leva = montar_plano(issues)["levas"][0]

    ondas = [[f["number"] for f in onda] for onda in leva["ondas"]]
    assert ondas == [[32]]
    assert [f["number"] for f in leva["concluidas"]] == [31]
    assert leva["concluidas"][0]["estado"] == "concluida"


def test_estado_distingue_pronta_bloqueada_e_em_andamento():
    issues = [
        _issue(40, is_prd=True, children=[41, 42, 43]),
        _issue(41, parent=40, labels=["in-progress"], assignees=["pedro"]),
        _issue(42, parent=40),
        _issue(43, parent=40, blocked_by=[41, 42]),
    ]
    leva = montar_plano(issues)["levas"][0]
    por_numero = {f["number"]: f for onda in leva["ondas"] for f in onda}

    assert por_numero[41]["estado"] == "em_andamento"
    assert por_numero[42]["estado"] == "pronta"
    assert por_numero[43]["estado"] == "bloqueada"
    assert por_numero[43]["bloqueada_por"] == [41, 42]
    assert por_numero[42]["bloqueada_por"] == []


def test_ciclo_de_dependencia_degrada_para_onda_residual_com_aviso():
    issues = [
        _issue(50, is_prd=True, children=[51, 52, 53]),
        _issue(51, parent=50),
        _issue(52, parent=50, blocked_by=[53]),
        _issue(53, parent=50, blocked_by=[52]),
    ]
    leva = montar_plano(issues)["levas"][0]

    ondas = [[f["number"] for f in onda] for onda in leva["ondas"]]
    assert ondas == [[51], [52, 53]]  # ciclo vira camada residual, nada some
    assert any("ciclo" in a.lower() for a in leva["avisos"])


def test_leva_saudavel_nao_tem_avisos():
    issues = [_issue(60, is_prd=True, children=[61]), _issue(61, parent=60)]
    assert montar_plano(issues)["levas"][0]["avisos"] == []


def _fechada(number, *, horas, tamanho="M"):
    return _issue(
        number,
        state="CLOSED",
        labels=[f"fatia:{tamanho}"],
        created_at="2026-06-01T08:00:00Z",
        closed_at=f"2026-06-01T{8 + horas:02d}:00:00Z",
    )


def test_tempo_tipico_e_mediana_do_bucket_com_3_ou_mais_amostras():
    issues = [
        _fechada(70, horas=2),
        _fechada(71, horas=3),
        _fechada(72, horas=10),
        _issue(80, is_prd=True, children=[81]),
        _issue(81, parent=80, labels=["fatia:M"]),
    ]
    leva = montar_plano(issues)["levas"][0]
    fatia = leva["ondas"][0][0]

    assert fatia["tamanho"] == "M"
    assert fatia["tempo_tipico"] == {"horas": 3.0, "fonte": "bucket", "amostras": 3}


def test_bucket_com_menos_de_3_amostras_cai_na_mediana_geral():
    issues = [
        _fechada(70, horas=2, tamanho="G"),  # única amostra G
        _fechada(71, horas=4, tamanho="M"),
        _fechada(72, horas=6, tamanho="M"),
        _fechada(73, horas=8, tamanho="M"),
        _issue(80, is_prd=True, children=[81, 82]),
        _issue(81, parent=80, labels=["fatia:G"]),  # bucket G insuficiente
        _issue(82, parent=80, labels=["fatia:M"]),  # bucket M suficiente
    ]
    fatias = {f["number"]: f for onda in montar_plano(issues)["levas"][0]["ondas"] for f in onda}

    assert fatias[81]["tempo_tipico"] == {"horas": 5.0, "fonte": "geral", "amostras": 4}
    assert fatias[82]["tempo_tipico"]["fonte"] == "bucket"


def test_sem_nenhuma_fatia_fechada_tempo_tipico_e_nulo():
    issues = [_issue(80, is_prd=True, children=[81]), _issue(81, parent=80)]
    fatia = montar_plano(issues)["levas"][0]["ondas"][0][0]
    assert fatia["tempo_tipico"] is None


def test_lead_time_usa_claim_quando_identificavel():
    issues = [
        # claim 4h depois da abertura; trabalho real = 2h
        _issue(
            70,
            state="CLOSED",
            labels=["fatia:P"],
            created_at="2026-06-01T08:00:00Z",
            claimed_at="2026-06-01T12:00:00Z",
            closed_at="2026-06-01T14:00:00Z",
        ),
        _issue(80, is_prd=True, children=[81]),
        _issue(81, parent=80),
    ]
    tempos = montar_plano(issues)["tempos_tipicos"]
    assert tempos["P"] == {"horas": 2.0, "amostras": 1}
    assert tempos["geral"] == {"horas": 2.0, "amostras": 1}


def test_caminho_critico_soma_o_caminho_mais_longo_das_abertas():
    historico = [_fechada(60 + k, horas=2, tamanho="M") for k in range(3)] + [
        _fechada(65 + k, horas=8, tamanho="G") for k in range(3)
    ]
    issues = historico + [
        _issue(90, is_prd=True, children=[91, 92, 93, 94]),
        _issue(91, parent=90, labels=["fatia:M"]),  # 2h
        _issue(92, parent=90, labels=["fatia:G"], blocked_by=[91]),  # 8h ← caminho longo
        _issue(93, parent=90, labels=["fatia:M"], blocked_by=[91]),  # 2h
        _issue(94, parent=90, labels=["fatia:M"], blocked_by=[92, 93]),  # 2h
    ]
    leva = montar_plano(issues)["levas"][0]
    assert leva["caminho_critico_horas"] == 12.0  # 91 → 92 → 94


def test_caminho_critico_e_nulo_sem_historico_de_tempos():
    issues = [_issue(90, is_prd=True, children=[91]), _issue(91, parent=90)]
    assert montar_plano(issues)["levas"][0]["caminho_critico_horas"] is None


def test_explicacao_vem_do_bloco_o_que_muda_do_corpo():
    body = (
        "## 👔 Para o diretor\n\n"
        "**O que muda:** o painel mostra o plano pronto.\n\n"
        "**O que você precisa saber:**\n- regra\n"
    )
    issues = [
        _issue(90, is_prd=True, children=[91, 92]),
        _issue(91, parent=90, body=body),
        _issue(92, parent=90, body="Sem bloco do diretor aqui."),
    ]
    fatias = {f["number"]: f for onda in montar_plano(issues)["levas"][0]["ondas"] for f in onda}

    assert fatias[91]["explicacao"] == "o painel mostra o plano pronto."
    assert fatias[92]["explicacao"] is None


def test_bloqueios_do_corpo_le_secao_com_bullets():
    body = (
        "## O que construir\nAlgo que cita #99 sem ser bloqueio.\n\n"
        "## Bloqueada por\n\n- #85 (revisão e validação)\n- #86 (PDF institucional)\n\n"
        "## Outra seção\n- #77 também não é bloqueio.\n"
    )
    assert bloqueios_do_corpo(body) == [85, 86]


def test_bloqueios_do_corpo_le_formato_inline_e_nenhuma():
    assert bloqueios_do_corpo("Bloqueada por: #81 e #82.") == [81, 82]
    assert bloqueios_do_corpo("## Bloqueada por\n\nNenhuma — pode começar já.\n") == []
    assert bloqueios_do_corpo("") == []


def test_bloqueios_do_corpo_aceita_header_com_dois_pontos():
    assert bloqueios_do_corpo("## Bloqueada por:\n\n- #85\n\n## Outra\n") == [85]


def test_bloqueador_externo_ao_prd_aberto_mantem_fatia_bloqueada():
    issues = [
        _issue(95, title="Issue de infra fora da leva"),  # aberta, não é fatia do PRD
        _issue(40, is_prd=True, children=[41]),
        _issue(41, parent=40, blocked_by=[95]),
    ]
    fatia = montar_plano(issues)["levas"][0]["ondas"][0][0]

    assert fatia["estado"] == "bloqueada"
    assert fatia["bloqueada_por"] == [95]


def test_bloqueador_externo_fechado_nao_bloqueia():
    issues = [
        _issue(95, state="CLOSED", created_at="2026-06-01T08:00:00Z", closed_at="2026-06-01T09:00:00Z"),
        _issue(40, is_prd=True, children=[41]),
        _issue(41, parent=40, blocked_by=[95]),
    ]
    fatia = montar_plano(issues)["levas"][0]["ondas"][0][0]
    assert fatia["estado"] == "pronta"


def test_mediana_geral_ignora_fechadas_descartadas():
    issues = [
        _fechada(70, horas=2),
        _fechada(71, horas=2),
        # bug antigo que apodreceu 3 semanas na fila e fechou como wontfix
        _issue(72, state="CLOSED", labels=["wontfix"],
               created_at="2026-05-01T08:00:00Z", closed_at="2026-05-22T08:00:00Z"),
        _issue(80, is_prd=True, children=[81]),
        _issue(81, parent=80),
    ]
    tempos = montar_plano(issues)["tempos_tipicos"]
    assert tempos["geral"] == {"horas": 2.0, "amostras": 2}
