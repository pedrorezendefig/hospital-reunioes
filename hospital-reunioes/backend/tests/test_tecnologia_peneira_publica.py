"""Dado pessoal nao sai para a issue publica (issue #772, ADR 0060).

Todo texto da Tecnologia que vai para o repositorio publico passa pelo
`pseudonimizar` da Ouvidoria antes de chegar ao GitHub: o titulo e a descricao
da issue que o "Levar para desenvolvimento" cria, e o texto do comentario
espelhado (envio e correcao). Desde o #730 a descricao pode ser a transcricao
de um print de sistema hospitalar, e o diretor tambem digita.

Duas seams:

* **As tres portas de escrita**, pela rota, com o cliente do GitHub dublado: o
  teste le o que CHEGOU ao duble, e nao a funcao de formatacao. E o que um
  mutante que tira a peneira da rota deixa vermelho.
* **O `texto_do_diretor`**, funcao pura, so para a ordem: a peneira roda sobre
  o texto cru e o escape vem depois, e nenhum marcador vira sintaxe de link.

Os dubles sao os do teste do Vinculo, importados de la, pelo mesmo motivo do
teste da Conversa espelhada: um duble proprio divergiria em silencio.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import (  # noqa: E402
    BASE,
    DIRETOR,
    PEDRO,
    _demanda,
    _fio,
    _montar,
)
from test_tecnologia_vinculo import _integracao_configurada as _integracao_configurada  # noqa: E402, F401
from test_tecnologia_vinculo import _reset_rate_limiter as _reset_rate_limiter  # noqa: E402, F401
from test_tecnologia_vinculo import _sem_email_de_verdade as _sem_email_de_verdade  # noqa: E402, F401
from test_tecnologia_vinculo import _sem_github_de_verdade as _sem_github_de_verdade  # noqa: E402, F401

from app.services.tecnologia_vinculo import texto_do_diretor  # noqa: E402

ROTA_LEVAR = f"{BASE}/demandas/d-1/levar-para-desenvolvimento"

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


class TestLevarParaDesenvolvimento:
    def test_a_descricao_chega_ao_github_com_marcadores_no_lugar_do_paciente(self, monkeypatch):
        demanda = _demanda("d-1", descricao=DESCRICAO_COM_PACIENTE)
        client, _, gh = _montar(logado=PEDRO, demandas=[demanda], monkeypatch=monkeypatch)

        assert client.post(ROTA_LEVAR).status_code == 200

        corpo = gh.criadas[0]["corpo"]
        assert _vazou(corpo) == []
        for marcador in ("[NOME]", "[CPF]", "[CNS]", "[TELEFONE]", "[EMAIL]", "[DATA_NASCIMENTO]"):
            assert marcador in corpo
        assert "O campo do prontuario corta o nome." in corpo

    def test_o_titulo_chega_ao_github_com_marcadores_no_titulo_e_no_corpo(self, monkeypatch):
        """O titulo vai para dois lugares publicos: o titulo da issue e, com a
        descricao vazia, o "O que muda" do corpo."""
        demanda = _demanda("d-1", titulo=f"Cadastro de {NOME} ({CPF}) some da fila", descricao=None)
        client, _, gh = _montar(logado=PEDRO, demandas=[demanda], monkeypatch=monkeypatch)

        assert client.post(ROTA_LEVAR).status_code == 200

        criada = gh.criadas[0]
        assert criada["titulo"] == "Cadastro de [NOME] ([CPF]) some da fila"
        assert _vazou(criada["corpo"]) == []
        assert "**O que muda:** Cadastro de [NOME] ([CPF]) some da fila" in criada["corpo"]

    def test_a_demanda_no_app_mantem_titulo_e_descricao_originais(self, monkeypatch):
        """A peneira age so no que sai para o GitHub. A Demanda e o card
        continuam com o texto de quem escreveu."""
        titulo = f"Cadastro de {NOME} some da fila"
        demanda = _demanda("d-1", titulo=titulo, descricao=DESCRICAO_COM_PACIENTE)
        client, sb, _ = _montar(logado=PEDRO, demandas=[demanda], monkeypatch=monkeypatch)

        resposta = client.post(ROTA_LEVAR)

        assert resposta.status_code == 200
        assert resposta.json()["titulo"] == titulo
        assert resposta.json()["descricao"] == DESCRICAO_COM_PACIENTE
        gravada = sb.tabelas["tecnologia_demandas"][0]
        assert gravada["titulo"] == titulo
        assert gravada["descricao"] == DESCRICAO_COM_PACIENTE


# ─── 2. O comentario espelhado ───────────────────────────────────────────────


def _vinculada() -> dict:
    return _demanda("d-1", github_issue_numero=673, etapa="planejada")


def _texto_do_comentario(corpo: str) -> str:
    """O texto do autor: tudo depois do cabecalho e da linha em branco."""
    return corpo.split("\n", 3)[3]


class TestComentarioEspelhado:
    def test_responder_publica_o_comentario_com_marcadores(self, monkeypatch):
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": DESCRICAO_COM_PACIENTE})

        assert resposta.status_code == 201
        texto = _texto_do_comentario(gh.comentarios_criados[0]["corpo"])
        assert _vazou(texto) == []
        for marcador in ("[NOME]", "[CPF]", "[CNS]", "[TELEFONE]", "[EMAIL]", "[DATA_NASCIMENTO]"):
            assert marcador in texto
        # A Conversa, que e de dentro, guarda o que a pessoa escreveu.
        assert _fio(sb)[0]["texto"] == DESCRICAO_COM_PACIENTE

    def test_corrigir_edita_o_comentario_com_marcadores(self, monkeypatch):
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)
        linha_id = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Versao com erro"}).json()["id"]
        _fio(sb)[0]["criado_em"] = datetime.now(UTC).isoformat()

        resposta = client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": DESCRICAO_COM_PACIENTE})

        assert resposta.status_code == 200
        texto = _texto_do_comentario(gh.comentarios_editados[0]["corpo"])
        assert _vazou(texto) == []
        assert "[CPF]" in texto
        assert "[NOME]" in texto

    def test_a_mencao_do_app_continua_virando_login_e_o_perfil_do_paciente_some(self, monkeypatch):
        """A peneira roda nos trechos ENTRE as mencoes do app: o `@login` que
        o app poe no lugar do "@Pedro Vitta" nao passa por ela, senao sairia
        como perfil de rede social. O `@` digitado a mao, esse sim, e perfil,
        e pode ser o do paciente."""
        client, _, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        client.post(
            f"{BASE}/demandas/d-1/conversa",
            json={"texto": f"@Pedro Vitta, {NOME} reclamou no perfil @maria.silva88", "mencoes": ["P1"]},
        )

        texto = _texto_do_comentario(gh.comentarios_criados[0]["corpo"])
        assert texto == "@pedrorezendefig, [NOME] reclamou no perfil [REDE_SOCIAL]"


# ─── 3. A ordem: peneira sobre o texto cru, escape depois ────────────────────


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
        """A rota passa o titulo pelo funil, e o `corpo_da_issue_nova` o passa
        de novo quando a descricao esta vazia. Uma segunda barra desligaria a
        primeira, e o link voltaria."""
        for bruto in (DESCRICAO_COM_PACIENTE, f"Maria Silva: {TELEFONE}", "ligar 11987654321(celular)", f"# {NOME}"):
            uma_vez = texto_do_diretor(bruto)
            assert texto_do_diretor(uma_vez) == uma_vez


# ─── 4. Ruido: texto tecnico sai intacto ─────────────────────────────────────


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
            "Na aba Minha vez e no Histórico o botão Levar para desenvolvimento some.",
            "Erro 404 em /api/admin/tecnologia/demandas, id 3f2a9c1e-7b4d-4e2a-9c1e-7b4d4e2a9c1e.",
            "Issue #772, PR #771, ADR 0054.",
            "Pediram no Hospital São Matheus, setor Centro Cirúrgico, pelo Pronto Socorro.",
        ],
    )
    def test_sai_como_entrou(self, texto):
        assert texto_do_diretor(texto) == texto

    def test_pela_rota_o_texto_tecnico_chega_intacto_ao_github(self, monkeypatch):
        descricao = "Depois do deploy da v0.156.0 a tela devolve HTTP 502 na porta 8000."
        client, _, gh = _montar(logado=PEDRO, demandas=[_demanda("d-1", descricao=descricao)], monkeypatch=monkeypatch)

        client.post(ROTA_LEVAR)

        assert f"**O que muda:** {descricao}" in gh.criadas[0]["corpo"]
