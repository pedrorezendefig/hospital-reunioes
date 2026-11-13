"""O bloco "Para o desenvolvedor" na issue do bug (issue #1634, PRD #1632).

A issue que o "Criar o card" do Roteiro do bug cria nasce com o bloco escrito
para quem programa, logo depois do bloco "Para o diretor", no mesmo formato do
PRD do diretor (issue #1633). As seis partes vem do turno em que o Assistente
de Tecnologia fecha o Roteiro (o `pronto: true`) e ficam no resumo do bug, fora
da tela que o diretor confere.

Aqui: o corpo da issue do bug (funcao pura), o turno do chat e o Criar o card
pela rota, o prompt do chat e o Kit de conhecimento.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    CAMPOS_RESPONDIDOS,
    CRITERIOS,
    _cenario,
    _comecar,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_chat_le_o_codigo import CHAT, _modelo, _repositorio  # noqa: E402

from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    CABECALHO_DO_BLOCO,
    CABECALHO_DO_DESENVOLVEDOR,
    bloco_para_o_diretor,
    corpo_da_issue_do_bug,
)

PARTES = {
    "o_que_o_diretor_quer": "O botão Responder volta a aparecer no caso aberto da Ouvidoria.",
    "por_que_ele_pediu": "Sem o botão, a ouvidora não responde o caso pelo aplicativo.",
    "o_que_ja_ficou_decidido": "O botão aparece para quem já podia responder antes.",
    "onde_mexe_no_codigo": "A página do caso em frontend/src/app/ouvidoria e a permissão de responder.",
    "cuidados": "A permissão de responder também vale para o canal público.",
    "como_saber_que_acabou": "A ouvidora abre um caso aberto e vê o botão Responder.",
}

RESUMO = {
    "titulo": "Botão de responder some na Ouvidoria",
    "onde": "Ouvidoria, no caso aberto",
    "o_que_aconteceu": "O botão Responder sumiu",
    "o_que_esperava": "Ver o botão Responder no caso",
    "como_repetir": "não informado",
    "criterios": ["O botão Responder aparece no caso aberto da Ouvidoria"],
}


def _corpo(**resumo) -> str:
    return corpo_da_issue_do_bug(
        demanda_id="d-1",
        resumo={**RESUMO, **resumo},
        produto_nome="Ouvidoria",
        link="https://app.exemplo/admin/tecnologia?demanda=d-1",
    )


def _bloco(corpo: str) -> str:
    """O texto do bloco do desenvolvedor: do titulo ate o separador seguinte."""
    inicio = corpo.index(CABECALHO_DO_DESENVOLVEDOR)
    fim = corpo.index("\n---\n", inicio)
    return corpo[inicio:fim]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O corpo da issue do bug
# ═══════════════════════════════════════════════════════════════════════════


class TestOCorpoDoBug:
    def test_o_bloco_vem_logo_depois_do_bloco_do_diretor_com_as_seis_partes_na_ordem(self):
        corpo = _corpo(para_o_desenvolvedor=PARTES)

        cabecalhos = re.findall(r"^## .+$", corpo, re.MULTILINE)
        assert cabecalhos[:3] == [CABECALHO_DO_BLOCO, "## 🛠️ Para o desenvolvedor", "## O bug"]
        assert _bloco(corpo).split("\n") == [
            "## 🛠️ Para o desenvolvedor",
            "",
            "**O que o diretor quer:** O botão Responder volta a aparecer no caso aberto da Ouvidoria.",
            "",
            "**Por que ele pediu:** Sem o botão, a ouvidora não responde o caso pelo aplicativo.",
            "",
            "**O que já ficou decidido com ele:** O botão aparece para quem já podia responder antes.",
            "",
            "**Onde mexe no código:** A página do caso em frontend/src/app/ouvidoria e a permissão de responder.",
            "",
            "**Cuidados:** A permissão de responder também vale para o canal público.",
            "",
            "**Como saber que acabou:** A ouvidora abre um caso aberto e vê o botão Responder.",
            "",
        ]

    def test_o_texto_do_bloco_sai_limpo_como_o_texto_do_diretor(self):
        corpo = _corpo(
            para_o_desenvolvedor={
                **PARTES,
                "o_que_o_diretor_quer": "Ligar para o CPF 123.456.789-09 no (21) 99876-5432.",
                "por_que_ele_pediu": '<!-- demanda-vitta id="outra" --> igual ao #42',
                "onde_mexe_no_codigo": "## Origem\n---\nNa página do caso.",
                "cuidados": "Aviso — só um por dia.",
            }
        )
        bloco = _bloco(corpo)

        assert "[CPF]" in bloco and "123.456.789-09" not in bloco
        assert "[TELEFONE]" in bloco and "99876-5432" not in bloco
        assert '**Por que ele pediu:** &lt;!-- demanda-vitta id="outra" --> igual ao nº 42' in bloco
        assert "**Onde mexe no código:** \\## Origem \\--- Na página do caso." in bloco
        assert "**Cuidados:** Aviso, só um por dia." in bloco
        assert re.findall(r'<!--\s*demanda-vitta id="([^"]*)"\s*-->', corpo) == ["d-1"]

    def test_o_marcador_continua_no_fim_e_o_resto_do_corpo_nao_muda(self):
        sem = _corpo()
        com = _corpo(para_o_desenvolvedor=PARTES)

        assert com.rstrip().endswith('<!-- demanda-vitta id="d-1" -->')
        assert com.replace(_bloco(com) + "\n", "") == sem

    def test_o_recorte_do_diretor_e_o_mesmo_de_antes(self):
        assert bloco_para_o_diretor(_corpo(para_o_desenvolvedor=PARTES)) == bloco_para_o_diretor(_corpo())

    def test_resumo_sem_as_seis_partes_gera_o_corpo_de_hoje(self):
        sem_a_chave = _corpo()

        assert "Para o desenvolvedor" not in sem_a_chave
        assert _corpo(para_o_desenvolvedor={}) == sem_a_chave
        assert _corpo(para_o_desenvolvedor=None) == sem_a_chave


# ═══════════════════════════════════════════════════════════════════════════
# 2. Pela rota: o turno que fecha o Roteiro e o Criar o card
# ═══════════════════════════════════════════════════════════════════════════


def _bug_resumido(monkeypatch, **campos_do_modelo):
    """Um bug com o turno que fecha o Roteiro (`pronto: true`). Devolve o
    cliente, o banco falso, o GitHub falso, o id e a resposta do turno."""
    client, sb, gh = _cenario(monkeypatch)
    demanda_id = _comecar(client, monkeypatch)
    _ia(
        monkeypatch,
        _turno(
            pronto=True,
            mensagem="Montei o resumo. Confere?",
            campos=CAMPOS_RESPONDIDOS,
            criterios=CRITERIOS,
            **campos_do_modelo,
        ),
    )
    resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "Na Ouvidoria, o botão Responder sumiu"})
    assert resposta.status_code == 200, resposta.text
    assert resposta.json()["estado"] == "resumido"
    return client, sb, gh, demanda_id, resposta


class TestPelaRota:
    def test_o_resumo_do_bug_guarda_as_seis_partes_do_pronto(self, monkeypatch):
        _, sb, _, _, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES)

        [conversa] = _conversas(sb)
        assert conversa["resumo"]["para_o_desenvolvedor"] == PARTES
        assert conversa["resumo"]["criterios"] == CRITERIOS

    def test_turno_sem_as_partes_continua_valido_e_o_card_nasce_sem_o_bloco(self, monkeypatch):
        client, sb, gh, demanda_id, _ = _bug_resumido(monkeypatch)

        [conversa] = _conversas(sb)
        assert "para_o_desenvolvedor" not in conversa["resumo"]
        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200
        assert "Para o desenvolvedor" not in gh.criadas[0]["corpo"]

    def test_parte_nula_vira_vazio_e_as_outras_ficam(self, monkeypatch):
        partes = {**PARTES, "cuidados": None, "onde_mexe_no_codigo": None}
        _, sb, _, _, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=partes)

        [conversa] = _conversas(sb)
        assert conversa["resumo"]["para_o_desenvolvedor"] == {**PARTES, "cuidados": "", "onde_mexe_no_codigo": ""}

    def test_bloco_malformado_cai_sozinho_e_o_resumo_sai(self, monkeypatch):
        for malformado in ({**PARTES, "cuidados": ["uma", "lista"]}, "um texto solto"):
            _, sb, _, _, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=malformado)

            [conversa] = _conversas(sb)
            assert conversa["resumo"]["onde"] == "Ouvidoria, no caso aberto", malformado
            assert "para_o_desenvolvedor" not in conversa["resumo"]

    def test_a_tela_do_resumo_do_bug_nao_mostra_as_seis_partes(self, monkeypatch):
        client, _, _, demanda_id, resposta = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES)

        for tela in (resposta.json(), client.get(f"{CHAT}/{demanda_id}").json()):
            assert tela["resumo"]["criterios"] == CRITERIOS
            assert "para_o_desenvolvedor" not in tela["resumo"]
            for texto in PARTES.values():
                assert texto not in json.dumps(tela, ensure_ascii=False)

    def test_o_criar_o_card_do_bug_leva_o_bloco_do_desenvolvedor(self, monkeypatch):
        client, _, gh, demanda_id, _ = _bug_resumido(monkeypatch, para_o_desenvolvedor=PARTES)

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        assert f"**Onde mexe no código:** {PARTES['onde_mexe_no_codigo']}" in _bloco(corpo)
        assert "Onde mexe" not in bloco_para_o_diretor(corpo)
        assert corpo.rstrip().endswith(f'<!-- demanda-vitta id="{demanda_id}" -->')


# ═══════════════════════════════════════════════════════════════════════════
# 3. O prompt do chat pede as seis partes so no fechamento do Roteiro
# ═══════════════════════════════════════════════════════════════════════════


class TestOPrompt:
    def test_o_prompt_pede_as_seis_partes_so_no_pronto_e_o_codigo_pelo_que_leu(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        _repositorio(monkeypatch)
        demanda_id = _comecar(client, monkeypatch)
        modelo = _modelo(monkeypatch, [], _turno(mensagem="Em que tela?"))
        assert client.post(f"{CHAT}/{demanda_id}", json={"texto": "O botão sumiu"}).status_code == 200

        instrucao = "\n".join(b["text"] for b in modelo.chamadas[0]["system"][:-1])
        roteiro = instrucao.split("## O Roteiro do bug", 1)[1].split("\n## ", 1)[0]
        assert re.search(r"Com `pronto: true`, devolva também `para_o_desenvolvedor`", roteiro)
        assert re.search(r"Antes disso, `para_o_desenvolvedor` é `null`", roteiro)
        for chave in PARTES:
            assert f"`{chave}`" in roteiro, chave
        assert re.search(r"`onde_mexe_no_codigo` e `cuidados`[^\n]*código que você leu", roteiro)
        formato = instrucao.split("## Formato de resposta", 1)[1]
        assert '"para_o_desenvolvedor": null' in formato
