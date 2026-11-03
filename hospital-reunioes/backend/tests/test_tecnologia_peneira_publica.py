"""Dado pessoal nao sai para a issue publica (issue #772, ADR 0060).

Todo texto da Tecnologia que vai para o repositorio publico passa pelo
`pseudonimizar` da Ouvidoria antes de chegar ao GitHub: o titulo e o corpo da
issue que o "Criar o card" do chat cria (ADR 0077). Desde o #730 o texto pode
ser a transcricao de um print de sistema hospitalar, e o diretor tambem digita.

Duas seams:

* **O corpo e o titulo da issue**, pelas funcoes puras que o "Criar o card"
  usa (`corpo_da_issue_do_bug`, `titulo_da_issue`). A porta pela rota mora em
  `test_tecnologia_chat.py`, no teste da peneira publica.
* **O `texto_do_diretor`**, funcao pura, so para a ordem: a peneira roda sobre
  o texto cru e o escape vem depois, e nenhum marcador vira sintaxe de link.

O comentario espelhado e o "Levar para desenvolvimento" sairam na issue #1386.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.tecnologia_vinculo import corpo_da_issue_do_bug, texto_do_diretor, titulo_da_issue  # noqa: E402

# Um dado de cada tipo que a issue #772 lista, no desenho em que um print de
# sistema hospitalar os traria. O nome esta todo em minusculas e sem pista: so
# a base de nomes o pega, e e ela que fecha o texto transcrito de print.
CPF = "529.982.247-25"
CNS = "7005 0831 6586 452"
TELEFONE = "(11) 98765-4321"
EMAIL = "joana.pereira@gmail.com"
NASCIMENTO = "12/08/1975"
NOME = "maria aparecida ferreira"

DESCRICAO_COM_PACIENTE = (
    f"O leito 12 mostra {NOME} com CPF {CPF}, CNS {CNS}, "
    f"telefone {TELEFONE}, e-mail {EMAIL} e data de nascimento: {NASCIMENTO}. "
    "O campo do prontuario corta o nome."
)
DADOS = (CPF, CNS, TELEFONE, EMAIL, NASCIMENTO, NOME, "maria", "ferreira", "98765", "4321", "joana")


def _vazou(texto: str) -> list[str]:
    return [dado for dado in DADOS if dado in texto.lower()]


RESUMO_DO_BUG = {
    "titulo": "Ficha some da fila",
    "onde": "Recepção",
    "o_que_aconteceu": "A ficha some",
    "o_que_esperava": "Ver a ficha na fila",
    "como_repetir": "Abrir a fila",
    "criterios": ["A ficha aparece na fila"],
}


def _corpo_do_bug(**campos) -> str:
    return corpo_da_issue_do_bug(
        demanda_id="d-1",
        resumo={**RESUMO_DO_BUG, **campos},
        produto_nome="Reuniões",
        link="https://app.hsm.com/admin/tecnologia?demanda=d-1",
    )


class TestAIssueDoBug:
    def test_o_que_o_diretor_contou_chega_com_marcadores_no_lugar_do_paciente(self):
        corpo = _corpo_do_bug(o_que_aconteceu=DESCRICAO_COM_PACIENTE)

        assert _vazou(corpo) == []
        for marcador in ("[NOME]", "[CPF]", "[CNS]", "[TELEFONE]", "[EMAIL]", "[DATA_NASCIMENTO]"):
            assert marcador in corpo
        assert "O campo do prontuario corta o nome." in corpo

    def test_o_titulo_da_issue_sai_com_marcadores(self):
        assert titulo_da_issue(f"Cadastro de {NOME} ({CPF}) some da fila") == "Cadastro de [NOME] ([CPF]) some da fila"

    def test_o_titulo_da_issue_nao_leva_a_barra_do_marcador(self):
        """O titulo da issue no GitHub e texto puro, e nao Markdown: la a barra
        que desliga o link apareceria ("\\[NOME]: leito 12"). Ela so vale no
        corpo."""
        assert titulo_da_issue("Maria Silva: leito 12") == "[NOME]: leito 12"
        assert texto_do_diretor("Maria Silva: leito 12") == "\\[NOME]: leito 12"

    def test_arroba_seguido_de_digito_sai_sem_mencao_viva(self):
        """Issue #888: a peneira troca o `@` seguido de letra, mas `@1abc`
        notificava a conta `1abc`. Corpo e titulo ganham um espaco depois do
        `@`."""
        assert texto_do_diretor("Fala com @1abc amanha") == "Fala com @ 1abc amanha"
        assert titulo_da_issue("Avisar @2fulano") == "Avisar @ 2fulano"


# ─── 2. A ordem da peneira e do escape ───────────────────────────────────────


class TestAOrdemDaPeneiraEDoEscape:
    """A peneira roda sobre o texto CRU, e o escape vem por ultimo.

    Nessa ordem o escape e a ultima palavra sobre a saida: nenhum `<` e
    nenhuma estrutura em coluna zero sobrevive, venha do autor ou da peneira.
    E a peneira le o texto como o fuzz das issues #412 e #441 o testou, sem o
    `&lt;` e as barras que o escape poe no meio.

    O marcador e texto entre colchetes, e colchete e sintaxe de link no
    Markdown. Dois desenhos o transformam: `[NOME]: [TELEFONE]` na coluna zero
    e uma definicao de link de referencia, e o GitHub SOME com a linha; e
    `[TELEFONE](celular)` vira link. O escape desliga o colchete do marcador
    nesses dois casos."""

    def test_dado_colado_em_sinal_de_menor_e_pego_e_o_sinal_escapado(self):
        texto = texto_do_diretor(f"<{NOME}> tem CPF <{CPF}>")

        assert texto == "&lt;[NOME]> tem CPF &lt;[CPF]>"

    def test_dado_em_cabecalho_e_separador_digitados(self):
        assert texto_do_diretor(f"# {NOME}\n---") == "\\# [NOME]\n\\---"

    def test_marcador_na_coluna_zero_nao_vira_definicao_de_link(self):
        """Sem o escape, o GitHub le a linha como `[rotulo]: destino` e nao a
        mostra: quem cura a issue perderia a linha inteira sem saber."""
        assert texto_do_diretor(f"Maria Silva: {TELEFONE}") == "\\[NOME]: [TELEFONE]"

    def test_marcador_colado_em_parentese_nao_vira_link(self):
        assert texto_do_diretor("ligar 11987654321(celular)") == "ligar \\[TELEFONE](celular)"

    def test_marcador_colado_em_colchete_nao_vira_link(self):
        assert texto_do_diretor(f"{NOME}[1]") == "\\[NOME][1]"

    def test_aplicar_duas_vezes_da_o_mesmo_texto(self):
        """O mesmo texto pode passar pelo funil duas vezes (o titulo e o "O que
        muda" que o repete). Uma segunda barra desligaria a primeira, e o link
        voltaria."""
        for bruto in (DESCRICAO_COM_PACIENTE, f"Maria Silva: {TELEFONE}", "ligar 11987654321(celular)", f"# {NOME}"):
            uma_vez = texto_do_diretor(bruto)
            assert texto_do_diretor(uma_vez) == uma_vez


# ─── 3. Ruido: texto tecnico sai intacto ─────────────────────────────────────


class TestTextoTecnicoSaiIntacto:
    """O pedido de tecnologia fala de versao, codigo de erro, porta, stack
    trace e tela do app, e nada disso e pessoa.

    Limites conhecidos, registrados no PR em vez de afrouxar o modulo da
    Ouvidoria (quem mais o usa nao pode mudar de comportamento por causa desta
    fatia): a regra de desenho le duas palavras capitalizadas seguidas como
    nome, e "Painel de Reuniões", "Assistente de Tecnologia" e o fornecedor
    "Global Health" saem como `[NOME]`. Perde contexto, nao vaza pessoa."""

    @pytest.mark.parametrize(
        "texto",
        [
            "Depois do deploy da v0.156.0 a tela devolve HTTP 502.",
            "O backend na porta 8000 caiu às 14:32 de 26/09/2026.",
            (
                "Traceback (most recent call last):\n"
                '  File "/app/app/routers/admin/tecnologia.py", line 1457, in levar_para_desenvolvimento\n'
                "    dados = github_client.criar_issue(titulo=titulo)\n"
                "httpx.ReadTimeout: timed out"
            ),
            "Na conversa do Assistente o botão Criar o card some.",
            "Erro 404 em /api/admin/tecnologia/demandas, id 3f2a9c1e-7b4d-4e2a-9c1e-7b4d4e2a9c1e.",
            "Issue #772, PR #771, ADR 0054.",
            "Pediram no Hospital São Matheus, setor Centro Cirúrgico, pelo Pronto Socorro.",
        ],
    )
    def test_sai_como_entrou(self, texto):
        assert texto_do_diretor(texto) == texto

    def test_no_corpo_do_bug_o_texto_tecnico_chega_intacto(self):
        descricao = "Depois do deploy da v0.156.0 a tela devolve HTTP 502 na porta 8000."

        assert f"- **O que aconteceu:** {descricao}" in _corpo_do_bug(o_que_aconteceu=descricao)
