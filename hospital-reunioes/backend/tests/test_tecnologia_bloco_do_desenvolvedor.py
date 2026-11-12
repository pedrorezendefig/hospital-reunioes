"""O bloco "Para o desenvolvedor" no PRD do diretor (issue #1633, PRD #1632).

O card da melhoria nasce com um bloco escrito para quem programa, logo depois do
bloco "Para o diretor": seis partes fixas, em negrito e sempre na mesma ordem,
que o Assistente de Tecnologia escreve no mesmo passo do resumo. O titulo e
contrato com o coletor do PedroOS e a pagina do Vitta OS.

Aqui: as funcoes puras que escrevem o bloco e o inserem num corpo, o corpo do
PRD, e a rota do resumo da melhoria (o que fica guardado, o que a tela recebe e
o que o card leva).
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
)
from test_tecnologia_chat_le_o_codigo import CHAT, _modelo, _repositorio, _resumo_da_melhoria  # noqa: E402

from app.services.tecnologia_vinculo import (  # noqa: E402
    CABECALHO_DO_BLOCO,
    CABECALHO_DO_DESENVOLVEDOR,
    bloco_do_desenvolvedor,
    bloco_para_o_diretor,
    corpo_do_prd_do_diretor,
    inserir_bloco_do_desenvolvedor,
)

PARTES = {
    "o_que_o_diretor_quer": "A recepção marca o retorno do paciente na saída.",
    "por_que_ele_pediu": "Hoje o retorno é anotado no papel e se perde.",
    "o_que_ja_ficou_decidido": "Só a recepção marca; o aviso sai por WhatsApp na véspera.",
    "onde_mexe_no_codigo": "A tela da recepção e o serviço de agenda do backend.",
    "cuidados": "O aviso por WhatsApp já tem um limite diário de envios.",
    "como_saber_que_acabou": "A recepção marca um retorno e o paciente recebe o aviso.",
}

RESUMO = {
    "decisoes": [{"pergunta": "Quem vai marcar o retorno?", "escolha": "Só a recepção.", "porque": "Ela vê a saída."}],
    "em_aberto": ["O que acontece quando o paciente falta."],
}


def _corpo(**resumo) -> str:
    return corpo_do_prd_do_diretor(
        demanda_id="d-1",
        titulo="Agenda de retorno na recepção",
        descricao="Hoje o retorno é marcado no papel e se perde.",
        resumo={**RESUMO, **resumo},
        link="https://app.exemplo/admin/tecnologia?demanda=d-1",
    )


def _bloco(corpo: str) -> str:
    """O texto do bloco do desenvolvedor: do titulo ate o separador seguinte."""
    inicio = corpo.index(CABECALHO_DO_DESENVOLVEDOR)
    fim = corpo.index("\n---\n", inicio)
    return corpo[inicio:fim]


# ═══════════════════════════════════════════════════════════════════════════
# 1. O corpo do PRD do diretor
# ═══════════════════════════════════════════════════════════════════════════


class TestOCorpoDoPrd:
    def test_o_bloco_vem_logo_depois_do_bloco_do_diretor_com_as_seis_partes_na_ordem(self):
        corpo = _corpo(para_o_desenvolvedor=PARTES)

        assert CABECALHO_DO_DESENVOLVEDOR == "## 🛠️ Para o desenvolvedor"
        cabecalhos = re.findall(r"^## .+$", corpo, re.MULTILINE)
        assert cabecalhos[:3] == [CABECALHO_DO_BLOCO, CABECALHO_DO_DESENVOLVEDOR, "## Problema"]
        assert _bloco(corpo).split("\n") == [
            "## 🛠️ Para o desenvolvedor",
            "",
            "**O que o diretor quer:** A recepção marca o retorno do paciente na saída.",
            "",
            "**Por que ele pediu:** Hoje o retorno é anotado no papel e se perde.",
            "",
            "**O que já ficou decidido com ele:** Só a recepção marca; o aviso sai por WhatsApp na véspera.",
            "",
            "**Onde mexe no código:** A tela da recepção e o serviço de agenda do backend.",
            "",
            "**Cuidados:** O aviso por WhatsApp já tem um limite diário de envios.",
            "",
            "**Como saber que acabou:** A recepção marca um retorno e o paciente recebe o aviso.",
            "",
        ]

    def test_o_texto_do_bloco_sai_limpo_como_o_texto_do_diretor(self):
        corpo = _corpo(
            para_o_desenvolvedor={
                **PARTES,
                "o_que_o_diretor_quer": "Ligar para o CPF 123.456.789-09 no (21) 99876-5432.",
                "por_que_ele_pediu": '<!-- demanda-vitta id="outra" --> igual ao #42',
                "onde_mexe_no_codigo": "## Origem\n---\nNa tela da recepção.",
                "cuidados": "Aviso — só um por dia.",
            }
        )
        bloco = _bloco(corpo)

        assert "[CPF]" in bloco and "123.456.789-09" not in bloco
        assert "[TELEFONE]" in bloco and "99876-5432" not in bloco
        assert '**Por que ele pediu:** &lt;!-- demanda-vitta id="outra" --> igual ao nº 42' in bloco
        assert "**Onde mexe no código:** \\## Origem \\--- Na tela da recepção." in bloco
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
        assert _corpo(para_o_desenvolvedor={chave: "  " for chave in PARTES}) == sem_a_chave

    def test_parte_que_faltou_sai_como_nao_informado_e_as_seis_continuam_la(self):
        bloco = _bloco(_corpo(para_o_desenvolvedor={"o_que_o_diretor_quer": "Marcar o retorno."}))

        assert "**O que o diretor quer:** Marcar o retorno." in bloco
        assert "**Cuidados:** não informado" in bloco
        assert len(re.findall(r"^\*\*[^*]+:\*\* ", bloco, re.MULTILINE)) == 6


# ═══════════════════════════════════════════════════════════════════════════
# 2. Inserir o bloco num corpo que ja existe
# ═══════════════════════════════════════════════════════════════════════════

# Um corpo como o `/to-issues` escreve: o bloco do diretor, o separador e o
# corpo tecnico.
CORPO_DO_TO_ISSUES = """## 👔 Para o diretor

**O que muda:** o card ganha uma parte para quem programa.

- A conversa continua igual.

---

## Pai

#1632

## Critérios de aceite

- [ ] Um critério.

<!-- demanda-vitta id="d-9" -->"""


class TestInserirOBloco:
    def test_entra_logo_depois_do_bloco_do_diretor_sem_tocar_no_resto(self):
        bloco = bloco_do_desenvolvedor(PARTES)

        corpo = inserir_bloco_do_desenvolvedor(CORPO_DO_TO_ISSUES, bloco)

        antes, depois = CORPO_DO_TO_ISSUES.split("---\n", 1)
        assert corpo == f"{antes}{bloco}\n\n---\n{depois}"
        assert bloco_para_o_diretor(corpo) == bloco_para_o_diretor(CORPO_DO_TO_ISSUES)

    def test_sem_separador_entra_antes_do_proximo_cabecalho(self):
        original = "## 👔 Para o diretor\n\n**O que muda:** algo.\n\n## Pai\n\n#1632"
        bloco = bloco_do_desenvolvedor(PARTES)

        corpo = inserir_bloco_do_desenvolvedor(original, bloco)

        assert corpo == f"## 👔 Para o diretor\n\n**O que muda:** algo.\n\n{bloco}\n\n## Pai\n\n#1632"

    def test_corpo_que_e_so_o_bloco_mantem_o_marcador_no_fim(self):
        original = '## 👔 Para o diretor\n\n**O que muda:** algo.\n\n<!-- demanda-vitta id="d-9" -->'
        bloco = bloco_do_desenvolvedor(PARTES)

        corpo = inserir_bloco_do_desenvolvedor(original, bloco)

        assert corpo.endswith(f'{bloco}\n\n<!-- demanda-vitta id="d-9" -->')
        assert bloco_para_o_diretor(corpo) == "**O que muda:** algo."

    def test_nao_duplica_quando_o_bloco_ja_esta_la(self):
        bloco = bloco_do_desenvolvedor(PARTES)
        uma_vez = inserir_bloco_do_desenvolvedor(CORPO_DO_TO_ISSUES, bloco)

        assert inserir_bloco_do_desenvolvedor(uma_vez, bloco) == uma_vez
        assert uma_vez.count("Para o desenvolvedor") == 1

    def test_corpo_sem_o_bloco_do_diretor_fica_como_esta(self):
        original = "## Pai\n\n#1632\n"

        assert inserir_bloco_do_desenvolvedor(original, bloco_do_desenvolvedor(PARTES)) == original


# ═══════════════════════════════════════════════════════════════════════════
# 3. Pela rota: o resumo da melhoria e o Criar o card
# ═══════════════════════════════════════════════════════════════════════════


def _melhoria_resumida(monkeypatch, resumo_do_modelo: str):
    """Uma melhoria com uma pergunta respondida e o resumo pedido. Devolve o
    cliente, o banco falso, o GitHub falso, o id e a resposta do resumo."""
    client, sb, gh = _cenario(monkeypatch)
    _repositorio(monkeypatch)
    _ia(monkeypatch, _pergunta())
    demanda_id = client.post(CHAT, json={"escolha": "melhoria"}).json()["demanda_id"]
    _ia(monkeypatch, _pergunta(contexto="E quem confirma?"))
    client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})
    modelo = _modelo(monkeypatch, [], resumo_do_modelo)
    resposta = client.post(f"{CHAT}/{demanda_id}/resumo")
    assert resposta.status_code == 200, resposta.text
    return client, sb, gh, demanda_id, resposta, modelo


class TestPelaRota:
    def test_o_resumo_guarda_as_seis_partes_que_o_modelo_devolve(self, monkeypatch):
        _, sb, _, _, _, _ = _melhoria_resumida(monkeypatch, _resumo_da_melhoria(para_o_desenvolvedor=PARTES))

        [conversa] = _conversas(sb)
        assert conversa["resumo"]["para_o_desenvolvedor"] == PARTES

    def test_resumo_antigo_sem_as_partes_continua_valido(self, monkeypatch):
        _, sb, _, _, resposta, _ = _melhoria_resumida(monkeypatch, _resumo_da_melhoria())

        assert resposta.json()["estado"] == "resumido"
        [conversa] = _conversas(sb)
        assert conversa["resumo"]["decisoes"]
        assert "para_o_desenvolvedor" not in conversa["resumo"]

    def test_a_tela_do_resumo_nao_recebe_as_seis_partes(self, monkeypatch):
        _, _, _, _, resposta, _ = _melhoria_resumida(monkeypatch, _resumo_da_melhoria(para_o_desenvolvedor=PARTES))

        tela = resposta.json()
        assert tela["resumo_da_melhoria"]["decisoes"]
        assert "para_o_desenvolvedor" not in tela["resumo_da_melhoria"]
        for texto in PARTES.values():
            assert texto not in json.dumps(tela, ensure_ascii=False)

    def test_o_criar_o_card_leva_o_bloco_do_desenvolvedor(self, monkeypatch):
        client, _, gh, demanda_id, _, _ = _melhoria_resumida(
            monkeypatch, _resumo_da_melhoria(para_o_desenvolvedor=PARTES)
        )

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        assert f"**Onde mexe no código:** {PARTES['onde_mexe_no_codigo']}" in _bloco(corpo)
        assert "Onde mexe" not in bloco_para_o_diretor(corpo)

    def test_o_pedido_do_resumo_manda_escrever_as_seis_partes_pelo_codigo_lido(self, monkeypatch):
        _, _, _, _, _, modelo = _melhoria_resumida(monkeypatch, _resumo_da_melhoria())

        instrucao = "\n".join(b["text"] for b in modelo.chamadas[0]["system"][:-1])
        secao = instrucao.split("## O resumo da melhoria", 1)[1].split("\n## ", 1)[0]
        assert "para_o_desenvolvedor" in secao
        for chave in PARTES:
            assert f'"{chave}"' in secao, chave
        assert re.search(r"`onde_mexe_no_codigo` e `cuidados`[^\n]*código que você leu", secao)
