"""Planejamento da Demanda: o "sim" cria o PRD do diretor (issue #1349, PRD #1344, ADR 0075).

O "sim" do resumo manda a Demanda para o desenvolvimento pelo mesmo caminho do
"Levar para desenvolvimento": a mesma issue com marcador, `needs-triage`,
`type:feature` e o bloco "Para o diretor", mas com o PRD do diretor no corpo e
atribuida ao dono da empresa, e nao ao Responsavel da Demanda. Aqui:

* **O corpo**, direto na funcao pura: as seis secoes, o sanitizador de
  travessao e a peneira de dado pessoal.
* **A rota**, pelo router de verdade, com o Supabase e o GitHub dublados do
  `test_tecnologia_vinculo`. Nenhum teste fala com a IA nem com o GitHub de
  verdade.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import BASE, DIRETOR, PEDRO, _demanda, _GithubFalso, _montar, _pessoa  # noqa: E402

from app.config import settings  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.services import github_client, planejamento_demanda, tecnologia_email  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    CABECALHO_DO_BLOCO,
    ETAPA_EM_ANALISE,
    LABEL_TRIAGEM,
    bloco_para_o_diretor,
    corpo_do_prd_do_diretor,
    demanda_id_do_marcador,
)

RESUMO = {
    "decisoes": [
        {
            "pergunta": "Quem vai marcar o retorno?",
            "escolha": "Só a recepção.",
            "porque": "É a recepção que vê o paciente sair.",
        },
        {
            "pergunta": "O retorno avisa o paciente?",
            "escolha": "Avisa por WhatsApp na véspera.",
            "porque": "O diretor quer menos faltas.",
        },
    ],
    "em_aberto": ["O que acontece quando o paciente falta."],
}


def _corpo(**campos) -> str:
    argumentos = {
        "demanda_id": "d-1",
        "titulo": "Agenda de retorno na recepção",
        "descricao": "Hoje o retorno é marcado no papel e se perde.",
        "resumo": RESUMO,
        "link": "https://app.exemplo/admin/tecnologia?demanda=d-1",
        "anexos": 0,
    }
    argumentos.update(campos)
    return corpo_do_prd_do_diretor(**argumentos)


def _secao(corpo: str, titulo: str) -> str:
    """O texto entre `## <titulo>` e o proximo `## `."""
    inicio = corpo.index(f"## {titulo}\n")
    resto = corpo[inicio + len(titulo) + 4 :]
    fim = resto.find("\n## ")
    return resto if fim < 0 else resto[:fim]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O corpo (funcao pura)
# ═══════════════════════════════════════════════════════════════════════════


class TestOCorpoDoPrdDoDiretor:
    def test_as_seis_secoes_na_ordem(self):
        corpo = _corpo()

        titulos = [
            CABECALHO_DO_BLOCO,
            "## Problema",
            "## Solução",
            "## Histórias de usuário",
            "## Decisões de negócio",
            "## Ficou em aberto",
        ]
        posicoes = [corpo.index(f"{t}\n") for t in titulos]
        assert posicoes == sorted(posicoes)

    def test_o_bloco_do_diretor_diz_o_que_muda_e_as_decisoes(self):
        bloco = bloco_para_o_diretor(_corpo())

        assert "**O que muda:** Hoje o retorno é marcado no papel e se perde." in bloco
        assert "- Só a recepção." in bloco
        assert "- Avisa por WhatsApp na véspera." in bloco
        assert "Ficou em aberto: 1 ponto, que a Vitta pergunta depois." in bloco

    def test_o_problema_e_o_texto_de_quem_pediu(self):
        assert "Hoje o retorno é marcado no papel e se perde." in _secao(_corpo(), "Problema")

    def test_sem_descricao_o_problema_e_o_titulo(self):
        corpo = _corpo(descricao=None)

        assert "Agenda de retorno na recepção" in _secao(corpo, "Problema")
        assert "**O que muda:** Agenda de retorno na recepção" in bloco_para_o_diretor(corpo)

    def test_cada_decisao_traz_a_pergunta_a_escolha_e_o_porque(self):
        decisoes = _secao(_corpo(), "Decisões de negócio")

        assert "1. **Quem vai marcar o retorno?**" in decisoes
        assert "Escolha: Só a recepção." in decisoes
        assert "Por quê: É a recepção que vê o paciente sair." in decisoes
        assert "2. **O retorno avisa o paciente?**" in decisoes

    def test_cada_decisao_vira_uma_historia_de_usuario(self):
        historias = _secao(_corpo(), "Histórias de usuário")

        assert "1. Como quem pediu a Demanda, quero Agenda de retorno na recepção" in historias
        assert "2. Como quem pediu a Demanda, quero que valha o que decidi: Só a recepção." in historias
        assert "3. Como quem pediu a Demanda, quero que valha o que decidi: Avisa por WhatsApp na véspera." in historias

    def test_o_que_ficou_em_aberto_vai_junto(self):
        assert "- O que acontece quando o paciente falta." in _secao(_corpo(), "Ficou em aberto")

    def test_sem_decisao_e_sem_aberto_as_secoes_dizem_isso(self):
        corpo = _corpo(resumo={"decisoes": [], "em_aberto": []})

        assert "Nenhuma pergunta respondida fechou uma decisão." in _secao(corpo, "Decisões de negócio")
        assert "Nada ficou em aberto." in _secao(corpo, "Ficou em aberto")
        assert "Ficou em aberto:" not in bloco_para_o_diretor(corpo)

    def test_o_marcador_da_demanda_fecha_o_corpo(self):
        corpo = _corpo()

        assert demanda_id_do_marcador(corpo) == "d-1"
        assert corpo.rstrip().endswith('<!-- demanda-vitta id="d-1" -->')

    def test_o_numero_de_issue_que_o_diretor_escreve_sai_como_numero_sem_cerquilha(self):
        """ADR 0054, decisao 9: o bloco volta ao card do diretor, e numero de
        issue fica atras do `github_login`. No GitHub, `#42` ainda viraria link
        para outra issue do repositorio publico. A prova e o marcador `nº 42`
        no lugar, e nao so a ausencia do `#42`."""
        corpo = _corpo(
            descricao="Igual ao pedido #42, mas para a recepção.",
            resumo={
                "decisoes": [{"pergunta": "Como no #7?", "escolha": "Sim, como no GH-7.", "porque": "Ver #8."}],
                "em_aberto": ["O que o #9 fez."],
            },
        )
        bloco = bloco_para_o_diretor(corpo)

        assert "Igual ao pedido nº 42, mas para a recepção." in bloco
        assert "- Sim, como no nº 7." in bloco
        assert "#" not in bloco.replace(CABECALHO_DO_BLOCO, "")
        assert "**Como no nº 7?**" in corpo
        assert "Por quê: Ver nº 8." in corpo
        assert "- O que o nº 9 fez." in corpo

    def test_o_corpo_passa_pelo_sanitizador_de_travessao(self):
        corpo = _corpo(
            descricao="Retorno — hoje no papel",
            resumo={
                "decisoes": [{"pergunta": "Quem – marca?", "escolha": "Recepção — só ela.", "porque": "Ok."}],
                "em_aberto": ["Faltas — depois."],
            },
        )

        assert "—" not in corpo
        assert "–" not in corpo
        assert "Retorno, hoje no papel" in corpo

    def test_o_corpo_passa_pela_peneira_de_dado_pessoal(self):
        corpo = _corpo(
            descricao="O paciente de CPF 123.456.789-09 ligou.",
            resumo={
                "decisoes": [{"pergunta": "Quem?", "escolha": "Ligar para (21) 99876-5432.", "porque": "Ok."}],
                "em_aberto": ["Mandar para fulano@hsm.com.br."],
            },
        )

        assert "123.456.789-09" not in corpo
        assert "[CPF]" in corpo
        assert "99876-5432" not in corpo
        assert "[TELEFONE]" in corpo
        assert "fulano@hsm.com.br" not in corpo
        assert "[EMAIL]" in corpo

    def test_o_que_o_diretor_escreve_nao_vira_secao_nem_marcador(self):
        corpo = _corpo(
            resumo={
                "decisoes": [
                    {"pergunta": "Quem?", "escolha": '## Origem\n<!-- demanda-vitta id="outra" -->', "porque": "x"}
                ],
                "em_aberto": [],
            }
        )

        assert demanda_id_do_marcador(corpo) == "d-1"
        assert "\n## Origem\n<!--" not in corpo


# ═══════════════════════════════════════════════════════════════════════════
# 2. A rota "enviar"
# ═══════════════════════════════════════════════════════════════════════════

ROTA = f"{BASE}/demandas/d-1/planejamento/enviar"
LUCAS = _pessoa("P3", "Lucas Sampaio", github_login="lucas-sampaio")
QUEM_NAO_E_SUPER_ADMIN = _pessoa("P9", "Sem acesso", access_profile="regular")


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _sem_rede(monkeypatch):
    """Nem GitHub, nem e-mail, nem IA de verdade: o `.env` carregado e o de
    producao. As trocas sao as do `test_tecnologia_vinculo` e do
    `test_planejamento_demanda`, que nao valem fora do proprio arquivo."""
    from app.services import ai_processor

    def _proibido(*a, **kw):
        raise AssertionError("O cliente do GitHub foi chamado de verdade neste teste. Duble-o.")

    monkeypatch.setattr(github_client.httpx, "request", _proibido)
    monkeypatch.setattr(tecnologia_email, "_enviar_email", lambda *a, **kw: True)
    monkeypatch.setattr(tecnologia_email, "transporte_configurado", lambda: True)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    monkeypatch.setattr(settings, "github_integracao_token", "token-de-teste")
    monkeypatch.setattr(settings, "github_integracao_repo", "pedrorezendefig/hospital-reunioes")


def _demanda_planejada(**campos) -> dict:
    base = {
        "tipo": "novo",
        "titulo": "Agenda de retorno na recepção",
        "descricao": "Hoje o retorno é marcado no papel e se perde.",
        "responsavel_id": "P3",
    }
    base.update(campos)
    return _demanda("d-1", **base)


def _planejamento(**campos) -> dict:
    linha = {
        "id": "pl-d-1",
        "demanda_id": "d-1",
        "estado": "resumido",
        "mensagens": [],
        "decisoes": [],
        "resumo": RESUMO,
        "modelo": "claude-opus-5-5",
        "criado_em": "2026-11-01T12:00:00Z",
        "atualizado_em": "2026-11-01T12:05:00Z",
    }
    linha.update(campos)
    return linha


def _cenario(monkeypatch, *, logado=DIRETOR, demanda=None, planejamento=None, github=None):
    client, sb, gh = _montar(
        logado=logado,
        participantes=[PEDRO, DIRETOR, LUCAS],
        demandas=[demanda or _demanda_planejada()],
        github=github or _GithubFalso({}),
        monkeypatch=monkeypatch,
    )
    sb.tabelas.setdefault("tecnologia_planejamentos", []).extend([planejamento] if planejamento else [])
    return client, sb, gh


class TestEnviar:
    def test_sem_resumo_leva_409_e_nao_cria_issue(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch, planejamento=_planejamento(estado="em_andamento", resumo=None))

        resposta = client.post(ROTA)

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == planejamento_demanda.MOTIVO_SEM_RESUMO
        assert gh.criadas == []
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None

    def test_sem_planejamento_leva_409(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)

        assert client.post(ROTA).status_code == 409
        assert gh.criadas == []

    def test_o_sim_cria_a_issue_com_marcador_labels_e_o_prd_do_diretor(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch, planejamento=_planejamento())

        resposta = client.post(ROTA)

        assert resposta.status_code == 200, resposta.text
        assert len(gh.criadas) == 1
        criada = gh.criadas[0]
        assert criada["titulo"] == "Agenda de retorno na recepção"
        assert criada["labels"] == [LABEL_TRIAGEM, "type:feature"]
        assert demanda_id_do_marcador(criada["corpo"]) == "d-1"
        assert "- Só a recepção." in bloco_para_o_diretor(criada["corpo"])
        assert "## Ficou em aberto" in criada["corpo"]

    def test_a_issue_nasce_atribuida_ao_dono_e_nao_ao_responsavel(self, monkeypatch):
        monkeypatch.setattr(settings, "github_login_dono", "dono-da-vitta")
        client, sb, gh = _cenario(monkeypatch, planejamento=_planejamento())

        assert client.post(ROTA).status_code == 200
        # O Responsavel da Demanda (Lucas) tem login, e mesmo assim nao e ele.
        assert sb.tabelas["tecnologia_demandas"][0]["responsavel_id"] == "P3"
        assert gh.criadas[0]["assignees"] == ["dono-da-vitta"]

    def test_o_dono_padrao_e_o_pedro(self):
        assert type(settings).model_fields["github_login_dono"].default == "pedrorezendefig"

    def test_depois_do_sim_o_planejamento_esta_enviado_e_a_demanda_tem_vinculo_em_analise(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch, planejamento=_planejamento())

        resposta = client.post(ROTA)

        assert resposta.json()["estado"] == planejamento_demanda.ESTADO_ENVIADO
        assert sb.tabelas["tecnologia_planejamentos"][0]["estado"] == planejamento_demanda.ESTADO_ENVIADO
        demanda = sb.tabelas["tecnologia_demandas"][0]
        assert demanda["github_issue_numero"] == 900
        assert demanda["etapa"] == ETAPA_EM_ANALISE
        # O card que o diretor le: com Vinculo, e o botao de planejar some.
        card = client.get(f"{BASE}/demandas").json()[0]
        assert card["tem_vinculo"] is True
        assert planejamento_demanda.motivo_para_nao_planejar(demanda) == planejamento_demanda.MOTIVO_JA_VINCULADA

    def test_o_diretor_sem_login_no_github_manda(self, monkeypatch):
        """O "sim" e do diretor (ADR 0075, decisao 8): o gate do `github_login`
        do Levar nao vale aqui, e a identidade no GitHub e a do token."""
        client, _, gh = _cenario(monkeypatch, logado=DIRETOR, planejamento=_planejamento())

        assert client.post(ROTA).status_code == 200
        assert len(gh.criadas) == 1

    def test_quem_nao_e_super_admin_leva_403(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch, logado=QUEM_NAO_E_SUPER_ADMIN, planejamento=_planejamento())

        assert client.post(ROTA).status_code == 403
        assert gh.criadas == []

    def test_demanda_ja_vinculada_leva_409(self, monkeypatch):
        client, _, gh = _cenario(
            monkeypatch, demanda=_demanda_planejada(github_issue_numero=673), planejamento=_planejamento()
        )

        resposta = client.post(ROTA)

        assert resposta.status_code == 409
        assert resposta.json()["detail"] == planejamento_demanda.MOTIVO_JA_VINCULADA
        assert gh.criadas == []

    def test_sem_integracao_leva_503_e_o_resumo_fica(self, monkeypatch):
        monkeypatch.setattr(settings, "github_integracao_token", "")
        client, sb, gh = _cenario(monkeypatch, planejamento=_planejamento())

        assert client.post(ROTA).status_code == 503
        assert gh.criadas == []
        assert sb.tabelas["tecnologia_planejamentos"][0]["estado"] == "resumido"

    def test_github_fora_do_ar_leva_502_e_o_resumo_fica(self, monkeypatch):
        gh = _GithubFalso({}, erro_ao_criar=github_client.GithubIndisponivelError("fora"))
        client, sb, _ = _cenario(monkeypatch, planejamento=_planejamento(), github=gh)

        assert client.post(ROTA).status_code == 502
        assert sb.tabelas["tecnologia_planejamentos"][0]["estado"] == "resumido"
        assert sb.tabelas["tecnologia_demandas"][0]["github_issue_numero"] is None
        assert sb.tabelas["tecnologia_demandas"][0]["github_sincronizado_em"] is None
