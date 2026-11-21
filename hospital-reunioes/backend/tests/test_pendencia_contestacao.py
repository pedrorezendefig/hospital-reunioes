"""A Contestação do item da Ata na assinatura (issue #1870, PRD #1757).

Decisões 1, 2, 12, 17, 22, 32, 38 e 51 do diretor: só o responsável pelo item
contesta, e só enquanto a Ata está em assinatura; contestar não impede assinar
a Ata; o item contestado segue cobrado; a Contestação aparece na hora na Minha
Fila do Facilitador; o Facilitador (ou o Super admin) ajusta ou recusa, sempre
com anotação, e a Ata não volta para assinatura.

Os valores esperados saem da issue, não do código.
"""

from __future__ import annotations

import os
import sys
from datetime import date

import pytest

from app.services.inicio import fonte_contestacoes
from app.services.pendencia_ciclo import AcaoRecusada, Comando, Papel, acoes_disponiveis, decidir

# O banco de mentira e o cliente da API são os de `test_pendencia_acoes.py`;
# o Início, os de `test_inicio_reunioes.py`.
sys.path.insert(0, os.path.dirname(__file__))

from test_inicio_reunioes import AURORA, FACILITADOR, _reuniao, _rota, nucleo  # noqa: E402, F401
from test_inicio_reunioes import _Banco as _BancoDoInicio  # noqa: E402
from test_pendencia_acoes import _banco, cliente  # noqa: E402, F401

HOJE = date(2026, 11, 19)
ONTEM = date(2026, 11, 18)
AMANHA = date(2026, 11, 20)
DAQUI_A_UMA_SEMANA = date(2026, 11, 26)

PAPEIS = {
    "responsavel": {Papel.RESPONSAVEL},
    "co_responsavel": {Papel.CO_RESPONSAVEL},
    "facilitador": {Papel.FACILITADOR},
    "super_admin": {Papel.SUPER_ADMIN},
    "outro": set(),
}


def _decidir(
    comando, papeis, *, status="PENDENTE", prazo=AMANHA, prazo_novo=None, anotacao="o prazo está errado", **ctx
):
    return decidir(
        comando, papeis, status=status, prazo=prazo, hoje=HOJE, anotacao=anotacao, prazo_novo=prazo_novo, **ctx
    )


# ── Só o responsável contesta, e só com a Ata em assinatura ─────────────────


@pytest.mark.parametrize(
    "papel,pode",
    [
        ("responsavel", True),
        ("co_responsavel", False),
        ("facilitador", False),
        ("super_admin", False),
        ("outro", False),
    ],
)
def test_so_o_responsavel_pelo_item_contesta(papel, pode):
    if pode:
        mudanca = _decidir(Comando.CONTESTAR, PAPEIS[papel], ata_em_assinatura=True)
        assert mudanca.status == "PENDENTE"
    else:
        with pytest.raises(AcaoRecusada) as erro:
            _decidir(Comando.CONTESTAR, PAPEIS[papel], ata_em_assinatura=True)
        assert erro.value.tipo == "permissao"


def test_contestar_fora_da_assinatura_e_recusado():
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.CONTESTAR, PAPEIS["responsavel"], ata_em_assinatura=False)
    assert erro.value.tipo == "transicao"


@pytest.mark.parametrize("status", ["CONCLUIDO", "CANCELADO"])
def test_item_fechado_nao_se_contesta(status):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.CONTESTAR, PAPEIS["responsavel"], status=status, ata_em_assinatura=True)
    assert erro.value.tipo == "transicao"


def test_item_ja_contestado_nao_se_contesta_de_novo_ate_o_facilitador_responder():
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.CONTESTAR, PAPEIS["responsavel"], ata_em_assinatura=True, contestada=True)
    assert erro.value.tipo == "transicao"


def test_o_botao_contestar_so_aparece_ao_responsavel_com_a_ata_em_assinatura():
    resp = PAPEIS["responsavel"]
    assert Comando.CONTESTAR in acoes_disponiveis(resp, "PENDENTE", ata_em_assinatura=True)
    assert Comando.CONTESTAR not in acoes_disponiveis(resp, "PENDENTE", ata_em_assinatura=False)
    assert Comando.CONTESTAR not in acoes_disponiveis(PAPEIS["co_responsavel"], "PENDENTE", ata_em_assinatura=True)


# ── O item contestado segue cobrado ─────────────────────────────────────────


def test_contestar_nao_muda_estado_nem_prazo_e_nao_conta_atraso():
    mudanca = _decidir(
        Comando.CONTESTAR, PAPEIS["responsavel"], status="EM_PROGRESSO", prazo=ONTEM, ata_em_assinatura=True
    )
    assert (mudanca.status, mudanca.prazo, mudanca.concluida, mudanca.conta_atraso) == (
        "EM_PROGRESSO",
        ONTEM,
        None,
        False,
    )


# ── Ajustar e recusar: Facilitador e Super admin, com anotação ──────────────


@pytest.mark.parametrize("comando", [Comando.AJUSTAR, Comando.RECUSAR])
@pytest.mark.parametrize(
    "papel,pode",
    [
        ("facilitador", True),
        ("super_admin", True),
        ("responsavel", False),
        ("co_responsavel", False),
        ("outro", False),
    ],
)
def test_ajustar_e_recusar_sao_do_facilitador_e_do_super_admin(comando, papel, pode):
    if pode:
        assert _decidir(comando, PAPEIS[papel], contestada=True) is not None
    else:
        with pytest.raises(AcaoRecusada) as erro:
            _decidir(comando, PAPEIS[papel], contestada=True)
        assert erro.value.tipo == "permissao"


@pytest.mark.parametrize("comando", [Comando.AJUSTAR, Comando.RECUSAR])
@pytest.mark.parametrize("anotacao", ["", "   ", None])
def test_ajustar_e_recusar_exigem_anotacao(comando, anotacao):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(comando, PAPEIS["facilitador"], contestada=True, anotacao=anotacao)
    assert erro.value.tipo == "dados"


@pytest.mark.parametrize("comando", [Comando.AJUSTAR, Comando.RECUSAR])
def test_ajustar_e_recusar_so_respondem_a_uma_contestacao_aberta(comando):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(comando, PAPEIS["facilitador"], contestada=False)
    assert erro.value.tipo == "transicao"
    assert comando not in acoes_disponiveis(PAPEIS["facilitador"], "PENDENTE", contestada=False)
    assert comando in acoes_disponiveis(PAPEIS["facilitador"], "PENDENTE", contestada=True)


def test_ajustar_muda_o_prazo_na_pendencia_sem_contar_atraso():
    mudanca = _decidir(
        Comando.AJUSTAR, PAPEIS["facilitador"], prazo=ONTEM, prazo_novo=DAQUI_A_UMA_SEMANA, contestada=True
    )
    assert (mudanca.status, mudanca.prazo, mudanca.conta_atraso) == ("PENDENTE", DAQUI_A_UMA_SEMANA, False)


def test_ajustar_sem_prazo_novo_mantem_o_prazo():
    mudanca = _decidir(Comando.AJUSTAR, PAPEIS["facilitador"], contestada=True)
    assert mudanca.prazo == AMANHA


def test_ajustar_para_um_prazo_no_passado_e_recusado():
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.AJUSTAR, PAPEIS["facilitador"], prazo_novo=ONTEM, contestada=True)
    assert erro.value.tipo == "dados"


def test_ajustar_troca_o_responsavel_errado_da_pendencia():
    """Erro de responsável na ata também se corrige no ajuste (issue #1870;
    decisão 17 do PRD #1757: o ajuste do item contestado vai para a pendência)."""
    mudanca = _decidir(Comando.AJUSTAR, PAPEIS["facilitador"], responsavel_novo="P_CERTO", contestada=True)
    assert (mudanca.status, mudanca.prazo, mudanca.responsavel_id) == ("PENDENTE", AMANHA, "P_CERTO")


def test_ajustar_sem_responsavel_novo_nao_mexe_no_responsavel():
    assert _decidir(Comando.AJUSTAR, PAPEIS["facilitador"], contestada=True).responsavel_id is None


@pytest.mark.parametrize("comando", [Comando.RECUSAR, Comando.REPACTUAR, Comando.ANOTAR])
def test_so_ajustar_troca_o_responsavel(comando):
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(
            comando,
            PAPEIS["facilitador"] | PAPEIS["responsavel"],
            prazo_novo=DAQUI_A_UMA_SEMANA if comando is Comando.REPACTUAR else None,
            responsavel_novo="P_CERTO",
            contestada=True,
        )
    assert erro.value.tipo == "dados"


def test_recusar_mantem_a_pendencia_como_esta():
    mudanca = _decidir(Comando.RECUSAR, PAPEIS["facilitador"], contestada=True)
    assert (mudanca.status, mudanca.prazo, mudanca.concluida, mudanca.conta_atraso) == ("PENDENTE", AMANHA, None, False)
    with pytest.raises(AcaoRecusada) as erro:
        _decidir(Comando.RECUSAR, PAPEIS["facilitador"], prazo_novo=DAQUI_A_UMA_SEMANA, contestada=True)
    assert erro.value.tipo == "dados"


# ── Pela API: `POST /pendencias/{id}/acoes` ─────────────────────────────────


def _em_assinatura(estado, status_ata="AGUARDANDO_ASSINATURA"):
    estado["banco"].reunioes[0]["status_ata"] = status_ata
    return estado


def _evento(id_evento=10, comando="contestar", criado_em="2026-11-19T09:00:00+00:00"):
    return {
        "id": id_evento,
        "id_acao": "A001",
        "comando": comando,
        "anotacao": "o prazo combinado era outro",
        "autor_nome": "Rita Responsável",
        "criado_em": criado_em,
        "conta_atraso": False,
    }


@pytest.mark.parametrize(
    "quem,status_ata,esperado",
    [
        ("resp", "AGUARDANDO_ASSINATURA", 200),
        ("resp", "ASSINADA", 409),
        ("resp", "AGUARDANDO_VALIDACAO", 409),
        ("coresp", "AGUARDANDO_ASSINATURA", 403),
        ("facil", "AGUARDANDO_ASSINATURA", 403),
        ("admin", "AGUARDANDO_ASSINATURA", 403),
        ("outro", "AGUARDANDO_ASSINATURA", 404),
    ],
)
def test_contestar_pela_api_por_papel_e_por_estado_da_ata(cliente, quem, status_ata, esperado):  # noqa: F811
    client, estado = cliente
    _em_assinatura(estado, status_ata)
    estado["quem"] = quem
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "contestar", "anotacao": "prazo errado"})
    assert r.status_code == esperado, r.text
    if esperado != 200:
        assert estado["banco"].chamadas == []


def test_contestar_grava_o_evento_e_o_item_segue_cobrado(cliente):  # noqa: F811
    client, estado = cliente
    estado["banco"] = _banco(prazo=ONTEM)
    _em_assinatura(estado)
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "contestar", "anotacao": "o prazo era março"})

    assert r.status_code == 200, r.text
    corpo = r.json()
    # Segue na cobrança e no cálculo de atraso, com o prazo de antes.
    assert (corpo["status"], corpo["prazo"], corpo["atrasada"]) == ("PENDENTE", ONTEM.isoformat(), True)
    params = estado["banco"].chamadas[0][1]
    assert (params["p_comando"], params["p_anotacao"], params["p_prazo_novo"]) == (
        "contestar",
        "o prazo era março",
        None,
    )


def test_contestar_nao_impede_assinar_a_ata(cliente):  # noqa: F811
    """A Contestação é do item; a assinatura é a ciência da Ata inteira
    (decisão 32). Quem já assinou ainda contesta, e contestar não mexe na
    Reunião: a Ata segue em assinatura, e a única gravação é o evento."""
    client, estado = cliente
    _em_assinatura(estado)
    estado["banco"].reuniao_aceites = [{"id_reuniao": "R1", "participante_id": "P_RESP"}]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "contestar", "anotacao": "responsável errado"})

    assert r.status_code == 200, r.text
    assert estado["banco"].reunioes[0]["status_ata"] == "AGUARDANDO_ASSINATURA"
    assert [nome for nome, _ in estado["banco"].chamadas] == ["registrar_acao_da_pendencia"]


def test_item_ja_contestado_nao_se_contesta_de_novo_pela_api(cliente):  # noqa: F811
    client, estado = cliente
    _em_assinatura(estado)
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "contestar", "anotacao": "de novo"})
    assert r.status_code == 409


@pytest.mark.parametrize("comando", ["ajustar", "recusar"])
def test_ajustar_e_recusar_exigem_anotacao_pela_api(cliente, comando):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": comando, "anotacao": "  "})
    assert r.status_code == 422
    assert estado["banco"].chamadas == []


def test_facilitador_ajusta_o_prazo_e_o_evento_vai_para_o_historico(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    # A Ata já foi assinada: o ajuste vale depois, e ela não volta a assinar.
    _em_assinatura(estado, "ASSINADA")
    estado["banco"].pendencia_historico = [_evento()]
    novo = DAQUI_A_UMA_SEMANA.isoformat()
    r = client.post(
        "/api/pendencias/A001/acoes", json={"comando": "ajustar", "anotacao": "combinado em março", "prazo": novo}
    )

    assert r.status_code == 200, r.text
    assert r.json()["prazo"] == novo
    params = estado["banco"].chamadas[0][1]
    assert (params["p_comando"], params["p_anotacao"], params["p_prazo_novo"]) == (
        "ajustar",
        "combinado em março",
        novo,
    )
    assert estado["banco"].reunioes[0]["status_ata"] == "ASSINADA"


_CERTO = {"id": "P_CERTO", "nome_completo": "Carla Certa", "cargo": "Enfermeira", "ativo": True}


def test_facilitador_ajusta_o_responsavel_errado_e_a_troca_vai_para_a_gravacao(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    estado["banco"].participantes.append(dict(_CERTO))
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post(
        "/api/pendencias/A001/acoes",
        json={"comando": "ajustar", "anotacao": "a luva é com a Carla", "responsavel_id": "P_CERTO"},
    )

    assert r.status_code == 200, r.text
    params = estado["banco"].chamadas[0][1]
    assert (params["p_comando"], params["p_responsavel_id"], params["p_responsavel_nome"], params["p_cargo"]) == (
        "ajustar",
        "P_CERTO",
        "Carla Certa",
        "Enfermeira",
    )


def test_ajustar_sem_responsavel_novo_nao_manda_troca_de_responsavel(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "ajustar", "anotacao": "o erro era outro"})

    assert r.status_code == 200, r.text
    assert estado["banco"].chamadas[0][1].get("p_responsavel_id") is None


@pytest.mark.parametrize("pessoa", [None, {**_CERTO, "ativo": False}])
def test_ajustar_para_quem_nao_esta_ativo_no_cadastro_e_recusado(cliente, pessoa):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    if pessoa:
        estado["banco"].participantes.append(pessoa)
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post(
        "/api/pendencias/A001/acoes",
        json={"comando": "ajustar", "anotacao": "a luva é com a Carla", "responsavel_id": "P_CERTO"},
    )

    assert r.status_code == 422, r.text
    assert estado["banco"].chamadas == []


def test_o_responsavel_nao_troca_o_proprio_nome_pela_contestacao(cliente):  # noqa: F811
    client, estado = cliente
    _em_assinatura(estado)
    estado["banco"].participantes.append(dict(_CERTO))
    r = client.post(
        "/api/pendencias/A001/acoes",
        json={"comando": "contestar", "anotacao": "não é comigo", "responsavel_id": "P_CERTO"},
    )

    assert r.status_code == 422, r.text
    assert estado["banco"].chamadas == []


def test_facilitador_recusa_e_a_pendencia_fica_como_esta(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    estado["banco"].pendencia_historico = [_evento()]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "recusar", "anotacao": "o prazo foi esse mesmo"})

    assert r.status_code == 200, r.text
    assert (r.json()["status"], r.json()["prazo"]) == ("PENDENTE", AMANHA.isoformat())
    assert estado["banco"].chamadas[0][1]["p_comando"] == "recusar"


def test_depois_da_resposta_a_contestacao_esta_fechada(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    # O id e a hora contam a ordem, não a posição na lista.
    estado["banco"].pendencia_historico = [
        _evento(11, "recusar", "2026-11-19T11:00:00+00:00"),
        _evento(),
    ]
    r = client.post("/api/pendencias/A001/acoes", json={"comando": "ajustar", "anotacao": "mudei de ideia"})
    assert r.status_code == 409


def test_historico_mostra_ao_facilitador_ajustar_e_recusar_so_com_contestacao_aberta(cliente):  # noqa: F811
    client, estado = cliente
    estado["quem"] = "facil"
    assert client.get("/api/pendencias/A001/historico").json()["acoes_permitidas"] == ["repactuar", "cancelar"]
    estado["banco"].pendencia_historico = [_evento()]
    assert client.get("/api/pendencias/A001/historico").json()["acoes_permitidas"] == [
        "repactuar",
        "cancelar",
        "ajustar",
        "recusar",
    ]


def test_historico_mostra_ao_responsavel_contestar_com_a_ata_em_assinatura(cliente):  # noqa: F811
    client, estado = cliente
    assert "contestar" not in client.get("/api/pendencias/A001/historico").json()["acoes_permitidas"]
    _em_assinatura(estado)
    assert "contestar" in client.get("/api/pendencias/A001/historico").json()["acoes_permitidas"]


# ── A Contestação na Minha Fila do Facilitador, sem esperar job ─────────────
# O Início e o banco de mentira são os de `test_inicio_reunioes.py`; a
# Contestação sai do histórico na hora em que a pessoa abre o Início.


@pytest.fixture
def ocultas(monkeypatch, nucleo):  # noqa: F811
    """As reuniões do Núcleo que a pessoa não alcança, também para a fonte
    das Contestações."""
    monkeypatch.setattr(fonte_contestacoes, "reunioes_ocultas", lambda _sb, _me: list(nucleo["ocultas"]))
    return nucleo


def _cenario_da_fila(*eventos: dict, status="PENDENTE", facilitador="P_FACI") -> _BancoDoInicio:
    return _BancoDoInicio(
        reunioes=[_reuniao("R50", status_ata="AGUARDANDO_ASSINATURA", facilitador_id=facilitador)],
        pendencias=[
            {
                "id_acao": "A050",
                "id_reuniao": "R50",
                "descricao_acao": "Comprar luvas",
                "responsavel_id": "P_AURORA",
                "responsavel_nome": "Aurora Lima",
                "co_responsavel_id": None,
                "prazo": "2026-12-10",
                "status": status,
                "deleted_at": None,
                "created_at": "2026-11-17T12:00:00+00:00",
            }
        ],
        pendencia_historico=[{**e, "id_acao": "A050"} for e in eventos],
    )


_CONTESTOU_HOJE = _evento(20, "contestar", "2026-11-18T12:30:00+00:00")


def _contestacoes(resposta) -> list[tuple[str, str, str | None]]:
    return [(item.tipo, item.id, item.grupo) for item in resposta.itens if item.tipo == "contestacao"]


def test_a_contestacao_aparece_na_hora_no_alerta_e_na_minha_fila_do_facilitador(monkeypatch, ocultas):
    resposta = _rota(monkeypatch, FACILITADOR, _cenario_da_fila(_CONTESTOU_HOJE))

    assert _contestacoes(resposta) == [("contestacao", "A050", "ate_48_horas")]
    assert resposta.contadores.ate_48_horas == 1
    item = next(i for i in resposta.itens if i.tipo == "contestacao")
    assert "Comprar luvas" in item.titulo
    assert item.destino == "/pendencias/kanban?highlight=A050"
    assert "o prazo combinado era outro" in (item.contexto or "")


def test_a_contestacao_nao_vai_para_a_fila_do_responsavel_nem_de_outro_facilitador(monkeypatch, ocultas):
    assert _contestacoes(_rota(monkeypatch, AURORA, _cenario_da_fila(_CONTESTOU_HOJE))) == []
    assert (
        _contestacoes(_rota(monkeypatch, FACILITADOR, _cenario_da_fila(_CONTESTOU_HOJE, facilitador="P_OUTRO"))) == []
    )


@pytest.mark.parametrize("resposta_do_facilitador", ["ajustar", "recusar"])
def test_depois_de_ajustar_ou_recusar_a_contestacao_sai_da_fila(monkeypatch, ocultas, resposta_do_facilitador):
    respondida = _evento(21, resposta_do_facilitador, "2026-11-18T13:00:00+00:00")
    assert _contestacoes(_rota(monkeypatch, FACILITADOR, _cenario_da_fila(_CONTESTOU_HOJE, respondida))) == []


def test_contestacao_de_pendencia_fechada_nao_vai_para_a_fila(monkeypatch, ocultas):
    banco = _cenario_da_fila(_CONTESTOU_HOJE, status="CONCLUIDO")
    assert _contestacoes(_rota(monkeypatch, FACILITADOR, banco)) == []


def test_contestacao_de_reuniao_do_nucleo_fora_do_alcance_nao_aparece(monkeypatch, ocultas):
    ocultas["ocultas"] = ["R50"]
    assert _contestacoes(_rota(monkeypatch, FACILITADOR, _cenario_da_fila(_CONTESTOU_HOJE))) == []


# ── O kit de conhecimento diz o comportamento novo ──────────────────────────


def test_o_texto_de_reunioes_no_kit_diz_como_funciona_a_contestacao():
    from app.services.conhecimento import CONHECIMENTO_DIR

    texto = " ".join((CONHECIMENTO_DIR / "reunioes.md").read_text(encoding="utf-8").split())
    secao = texto.split("## Contestar um item da ata", 1)[1].split(" ## ", 1)[0]
    assert "Só o responsável pelo item contesta, e só enquanto a ata está em assinatura" in secao
    assert "contesta o item e assina a ata mesmo assim" in secao
    assert "continua sendo cobrado, com o mesmo prazo, e conta atraso" in secao
    assert "aparece na hora no Início do facilitador" in secao
    assert "ajustar ou recusar, sempre com uma anotação" in secao
    assert "a ata não volta para assinatura" in secao
    assert "Se o erro era o responsável, ele escolhe a pessoa certa no cadastro" in secao
    # Quem administra o aplicativo faz tudo, menos contestar.
    assert "faz tudo, menos contestar" in texto
    assert chr(0x2014) not in secao
    assert chr(0x2013) not in secao
