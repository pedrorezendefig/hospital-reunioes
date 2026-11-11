"""O PRD do diretor, o corpo da issue da melhoria (issue #1349, PRD #1344; ADR 0077).

O "Criar o card" da melhoria no chat manda a Demanda para o desenvolvimento com
o PRD do diretor no corpo: a issue com marcador, `needs-triage`, `type:feature`
e o bloco "Para o diretor". Aqui o corpo, direto na funcao pura: as secoes, o
sanitizador de travessao e a peneira de dado pessoal. A rota mora em
`test_tecnologia_chat_melhoria.py`; a rota "enviar" da tela antiga do
Planejamento saiu na issue #1386.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from app.services.tecnologia_vinculo import (  # noqa: E402
    CABECALHO_DO_BLOCO,
    bloco_para_o_diretor,
    corpo_do_prd_do_diretor,
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


def _demandas_do_marcador(corpo: str) -> list[str]:
    """Os ids de Demanda que os marcadores do corpo apontam, na ordem."""
    return re.findall(r'<!--\s*demanda-vitta id="([^"]*)"\s*-->', corpo)


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

        # O formato fixo da ADR 0084 (issue #1553): a frase de "O que muda" e
        # a do resumo, ou o titulo; a descricao inteira fica no Problema.
        assert "**O que muda:** Agenda de retorno na recepção" in bloco
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

        assert _demandas_do_marcador(corpo) == ["d-1"]
        assert corpo.rstrip().endswith('<!-- demanda-vitta id="d-1" -->')

    def test_o_numero_de_issue_que_o_diretor_escreve_sai_como_numero_sem_cerquilha(self):
        """ADR 0054, decisao 9: o bloco volta ao card do diretor, e numero de
        issue fica atras do `github_login`. No GitHub, `#42` ainda viraria link
        para outra issue do repositorio publico. A prova e o marcador `nº 42`
        no lugar, e nao so a ausencia do `#42`."""
        corpo = _corpo(
            descricao="Igual ao pedido #42, mas para a recepção.",
            resumo={
                "frase": "Igual ao pedido #42, mas para a recepção.",
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
            descricao="Retorno \u2014 hoje no papel",
            resumo={
                "decisoes": [{"pergunta": "Quem \u2013 marca?", "escolha": "Recepção \u2014 só ela.", "porque": "Ok."}],
                "em_aberto": ["Faltas \u2014 depois."],
            },
        )

        assert "\u2014" not in corpo
        assert "\u2013" not in corpo
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

        assert _demandas_do_marcador(corpo) == ["d-1"]
        assert "\n## Origem\n<!--" not in corpo
