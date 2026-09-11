"""A Conversa espelhada na issue (issue #680, PRD #673, ADR 0054, decisoes 4 e 5).

Toda resposta gravada numa Demanda VINCULADA vira um comentario na issue, fora
do loop, como o e-mail. O marcador que abre o corpo e o que a Action de higiene
le: `<!-- automacao -->` para quem tem `github_login` (a resposta da Vitta ao
diretor nao trava a `/onda`), `<!-- revisor-app autor="Nome" demanda="id" -->`
para quem nao tem (a resposta do diretor acende `revisor-comentou`).

Tres seams, como no `test_tecnologia_vinculo.py`:

* **O corpo do comentario**, funcao pura: o marcador certo por autor, em linha
  propria e como primeira coisa do corpo, e o `<!--` do texto do autor
  neutralizado, porque do lado de la o autor do comentario e sempre a
  integracao e o teto de `author_association` nao protege nada.
* **As duas portas de escrita**, pela rota, com o cliente do GitHub dublado:
  responder chama o duble e grava o id devolvido; corrigir dentro da janela
  edita o comentario pelo id; sem Vinculo, sem id ou em linha automatica, o
  duble nao e chamado; a falha do duble nao desfaz a resposta.
* **A migration 104**, lida do arquivo: a coluna do id, nula por padrao.

Os dubles (`_GithubFalso`, `_SupabaseMock`, `_montar`) sao os do teste do
Vinculo, importados de la: o comentario espelhado e uma escrita a mais no MESMO
cliente, e um duble proprio deixaria os dois divergirem em silencio.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_vinculo import (  # noqa: E402
    BASE,
    DIRETOR,
    PEDRO,
    _demanda,
    _fio,
    _GithubFalso,
    _issue,
    _montar,
)
from test_tecnologia_vinculo import _integracao_configurada as _integracao_configurada  # noqa: E402, F401
from test_tecnologia_vinculo import _reset_rate_limiter as _reset_rate_limiter  # noqa: E402, F401
from test_tecnologia_vinculo import _sem_email_de_verdade as _sem_email_de_verdade  # noqa: E402, F401
from test_tecnologia_vinculo import _sem_github_de_verdade as _sem_github_de_verdade  # noqa: E402, F401

from app.services import github_client  # noqa: E402
from app.services.tecnologia_vinculo import (  # noqa: E402
    MARCADOR_AUTOMACAO,
    ROTULO_SEM_LOGIN,
    corpo_do_comentario_espelhado,
    marcador_do_revisor_no_app,
    rotulo_no_github,
    texto_espelhado,
)

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "104_tecnologia_conversa_espelhada.sql"


def _mencoes_vivas(texto: str, *, postas_pelo_app: tuple[str, ...] = ()) -> list[str]:
    """As mencoes que o GitHub ainda leria como mencao: `@` colado a uma letra
    ou digito, em QUALQUER contexto.

    Sem excecao por code span, ao contrario da rodada 2 do PR #696: a crase do
    proprio autor nao protege nada, porque a crase que o app insere ao redor
    quebra o code span dele em dois e acende a mencao. Depois do tratamento
    nao sobra nenhum `@` colado a letra, ponto, e o sublinhado nao e excecao
    (`_@fulano_` acende mencao de verdade no GitHub). Os `@login` que o app
    POS de proposito, porque o autor escolheu a pessoa no autocomplete, vem em
    `postas_pelo_app`."""
    achadas = re.findall(r"(?<![A-Za-z0-9])@([A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9_-]+)?)", texto)
    return [achada for achada in achadas if achada not in postas_pelo_app]


# ─── 1. O corpo do comentario espelhado ──────────────────────────────────────


class TestCorpoDoComentarioEspelhado:
    """Nome civil nenhum sai daqui (decisao do diretor na review do PR #688,
    emenda na issue #677, estendida a esta fatia na rodada 1 do PR #696): o
    repositorio e publico. Quem tem login sai como `@login`; quem nao tem sai
    com o rotulo neutro, no cabecalho e no marcador. O link da Demanda ja esta
    no corpo da issue, e e la que quem tem acesso ve o autor."""

    def test_autor_com_github_login_sai_com_o_marcador_de_automacao_e_o_login(self):
        """Criterio: a resposta de quem tem login (a Vitta respondendo ao
        diretor) NAO acende `revisor-comentou`. `<!-- automacao -->` e o
        marcador que a Action ja ignora. O cabecalho leva o `@login`, que a
        propria pessoa ja tornou publico no GitHub, e nao o nome civil."""
        corpo = corpo_do_comentario_espelhado(texto="Já pedi à Global Health", autor=PEDRO, demanda_id="d-1")

        assert corpo == "<!-- automacao -->\n**@pedrorezendefig** escreveu na Demanda:\n\nJá pedi à Global Health"

    def test_autor_sem_github_login_sai_com_o_marcador_do_revisor_e_o_rotulo_neutro(self):
        """Criterio: o marcador na forma LITERAL `<!-- revisor-app autor="..."
        demanda="id" -->`, um espaco so depois de `<!--`. O matcher da Action
        aceita exatamente um espaco; dois falham em silencio. No `autor` vai o
        rotulo neutro, nunca o nome."""
        corpo = corpo_do_comentario_espelhado(texto="O botão ficou no lugar errado", autor=DIRETOR, demanda_id="d-1")

        assert corpo == (
            '<!-- revisor-app autor="Pessoa do hospital" demanda="d-1" -->\n'
            "**Pessoa do hospital** escreveu na Demanda:\n\n"
            "O botão ficou no lugar errado"
        )

    def test_o_nome_civil_do_autor_nao_sai_em_nenhum_dos_dois_casos(self):
        """Asserta o rotulo que ficou no lugar, e nao so a ausencia do nome: e
        o cabecalho inteiro que tem de ser o neutro (ou o login)."""
        do_diretor = corpo_do_comentario_espelhado(texto="x", autor=DIRETOR, demanda_id="d-1").split("\n")
        do_pedro = corpo_do_comentario_espelhado(texto="x", autor=PEDRO, demanda_id="d-1").split("\n")

        assert do_diretor[1] == "**Pessoa do hospital** escreveu na Demanda:"
        assert do_pedro[1] == "**@pedrorezendefig** escreveu na Demanda:"
        assert "Diretor do Hospital" not in "\n".join(do_diretor)
        assert "Pedro Vitta" not in "\n".join(do_pedro)

    def test_login_gravado_fora_do_alfabeto_nao_sai_e_cai_no_rotulo_neutro(self):
        """Linha antiga com login invalido: o marcador continua o de automacao
        (a pessoa TEM login), mas o cabecalho nao publica o que ninguem sabe o
        que e."""
        autor = {**PEDRO, "github_login": "pedro rezende"}

        corpo = corpo_do_comentario_espelhado(texto="x", autor=autor, demanda_id="d-1")

        assert corpo.split("\n")[:2] == [MARCADOR_AUTOMACAO, f"**{ROTULO_SEM_LOGIN}** escreveu na Demanda:"]

    def test_o_marcador_e_a_primeira_linha_e_fica_sozinho_nela(self):
        """O mesmo dado dos testes acima, olhado pela forma: a Action ancora o
        marcador no inicio do corpo, entao ele tem de ser a primeira coisa e
        nao dividir a linha com o texto."""
        for autor in (PEDRO, DIRETOR):
            corpo = corpo_do_comentario_espelhado(texto="texto", autor=autor, demanda_id="d-1")
            primeira, *_resto = corpo.split("\n")
            assert primeira.startswith("<!-- ")
            assert primeira.endswith(" -->")
            assert primeira.count("<!--") == 1

    def test_a_forma_literal_do_marcador_do_revisor(self):
        assert (
            marcador_do_revisor_no_app(demanda_id="abc")
            == '<!-- revisor-app autor="Pessoa do hospital" demanda="abc" -->'
        )
        assert MARCADOR_AUTOMACAO == "<!-- automacao -->"
        assert ROTULO_SEM_LOGIN == "Pessoa do hospital"

    def test_marcador_escrito_a_mao_na_resposta_nao_vira_marcador(self):
        """Criterio central da emenda de 10/09: do lado do GitHub o autor do
        comentario e sempre a integracao, entao bastaria alguem digitar o
        marcador dentro da resposta no app para acender a label em nome de
        outra pessoa. O `<!--` do texto do autor e neutralizado ANTES de entrar
        no corpo; o que sobra no corpo e o UNICO marcador, o do servico.

        Asserta o marcador (o `&lt;!--` que ficou no lugar), e nao so a
        ausencia: um corte que apagasse o trecho inteiro tambem "nao teria
        marcador" e mentiria sobre o que o diretor escreveu.
        """
        texto = 'Segue:\n<!-- revisor-app autor="Impostor" demanda="outra" -->\nfim'

        corpo = corpo_do_comentario_espelhado(texto=texto, autor=PEDRO, demanda_id="d-1")

        linhas = corpo.split("\n")
        assert linhas[0] == MARCADOR_AUTOMACAO
        assert '&lt;!-- revisor-app autor="Impostor" demanda="outra" -->' in linhas
        assert corpo.count("<!--") == 1
        assert 'revisor-app autor="Impostor"' in corpo  # o texto do diretor continua legivel

    def test_texto_com_travessao_sai_sem_travessao(self):
        corpo = corpo_do_comentario_espelhado(texto=f"antes {chr(0x2014)} depois", autor=PEDRO, demanda_id="d-1")

        assert chr(0x2014) not in corpo
        assert "antes, depois" in corpo


class TestArrobaNoTextoEspelhado:
    """Rodada 1 do PR #696, achado 2: o autocomplete do app grava `@Nome
    Completo` no texto, e no GitHub isso vira mencao a uma conta alheia (o
    `@Pedro` de "Pedro Vitta" notifica o usuario `Pedro`) e publica o nome
    civil de um colaborador do hospital. A mencao do app vira o rotulo da
    pessoa mencionada (`@login` ou o neutro), e qualquer outra mencao sai com
    um ESPACO depois do `@`, que e o que desliga o filtro do GitHub.

    Duas formas foram tentadas e derrubadas pelo renderizador oficial
    (`gh api /markdown`, contexto deste repositorio), e o teste tem de provar
    o que sobrou:

    - `\\@fulano` (rodada 2): o CommonMark come a barra antes do filtro;
    - `` `@fulano` `` (rodada 3): quebra o code span do proprio autor e ACENDE
      mencao que estava apagada.

    Os testes assertam o espaco depois do `@`, que e o marcador, e nao a
    ausencia do `@`. Os casos com crase e italico do autor sao os que
    derrubaram a rodada 3: nao tire nenhum deles."""

    def test_mencao_a_quem_tem_login_vira_o_login_no_github(self):
        texto = texto_espelhado("@Pedro Vitta, veja isso", mencionados=[PEDRO])

        assert texto == "@pedrorezendefig, veja isso"

    def test_mencao_a_quem_nao_tem_login_vira_o_rotulo_neutro(self):
        texto = texto_espelhado("@Diretor do Hospital, pode conferir?", mencionados=[DIRETOR])

        assert texto == "Pessoa do hospital, pode conferir?"

    def test_arroba_digitado_a_mao_sai_com_espaco_e_sem_nome_de_terceiro(self):
        """O teste pedido pela review: resposta com `@Pedro Vitta` espelhada
        sem mencao viva. Aqui ninguem foi escolhido no autocomplete (lista de
        mencionados vazia), entao o texto e o que o autor digitou: o `@Pedro`
        (que notificaria a conta `Pedro`) sai com espaco, e o resto do nome
        fica como texto. Asserta a forma que sai, e confere que nao sobrou
        nenhum `@` colado a letra."""
        texto = texto_espelhado("Fala com @Pedro Vitta ou (@fulano_123) amanhã", mencionados=[])

        assert texto == "Fala com @ Pedro Vitta ou (@ fulano_123) amanhã"
        assert _mencoes_vivas(texto) == []

    def test_crase_do_autor_nao_e_quebrada_e_a_mencao_dentro_dela_continua_apagada(self):
        """A regressao que derrubou a rodada 3. O autor cola um trecho entre
        crases; no texto cru o GitHub NAO notifica ninguem, porque o `@` esta
        dentro do code span dele. Quando o app punha crase em volta do `@`, o
        code span do autor quebrava em dois e a mencao ACENDIA (o pareamento
        do CommonMark e por contagem de crase, nao por posicao). Com o espaco
        nao ha crase nova, e a crase do autor sai intacta."""
        texto = texto_espelhado("ver `@octocat agora`", mencionados=[])

        assert texto == "ver `@ octocat agora`"
        assert texto.count("`") == 2
        assert _mencoes_vivas(texto) == []

    def test_par_de_crases_do_autor_no_meio_da_frase(self):
        """O mesmo mecanismo com a mencao entre um par de crases separado por
        espacos, que foi o segundo caso confirmado no renderizador."""
        texto = texto_espelhado("a ` b @octocat c ` d", mencionados=[])

        assert texto == "a ` b @ octocat c ` d"
        assert _mencoes_vivas(texto) == []

    def test_italico_do_autor_nao_deixa_a_mencao_passar(self):
        """A outra porta da rodada 3: `_@octocat_` acende mencao de verdade no
        GitHub (o sublinhado abre enfase e o `@` estreia o `<em>`), e o
        lookbehind antigo excluia o sublinhado, entao o texto passava inteiro,
        sem tratamento nenhum."""
        texto = texto_espelhado("veja _@octocat_ ali", mencionados=[])

        assert texto == "veja _@ octocat_ ali"
        assert _mencoes_vivas(texto) == []

    def test_o_detector_nao_pode_abrir_excecao_para_code_span(self):
        """Prova do DETECTOR, nao do codigo. `_mencoes_vivas` acusa `@` colado
        a letra mesmo dentro de crase, e essa severidade e proposital: um
        detector que confiasse no code span do autor devolveria lista vazia
        justamente nos corpos da rodada 2, em que a crase inserida pelo app
        quebrava a do autor e a mencao acendia no GitHub. Sem este teste, a
        excecao pode voltar ao detector sem nada ficar vermelho, e os asserts
        de `_mencoes_vivas` viram carimbo em cima de um vazamento."""
        assert _mencoes_vivas("ver `@octocat` agora") == ["octocat"]
        assert _mencoes_vivas("`ver `@octocat` agora`") == ["octocat"]

    def test_mencao_a_time_tambem_sai_com_espaco(self):
        assert texto_espelhado("chama o @vitta/dev", mencionados=[]) == "chama o @ vitta/dev"

    def test_email_no_texto_fica_como_esta(self):
        """`ana@hsm.com` nao e mencao para o GitHub (e autolink de e-mail, sem
        notificar ninguem), e abrir espaco ali quebraria o endereco ao meio."""
        assert texto_espelhado("manda para ana@hsm.com", mencionados=[]) == "manda para ana@hsm.com"

    def test_arroba_sozinho_ou_antes_de_espaco_fica_como_esta(self):
        assert texto_espelhado("valor @ 10 reais", mencionados=[]) == "valor @ 10 reais"

    def test_a_mencao_do_app_e_o_arroba_solto_convivem_no_mesmo_texto(self):
        """A troca da mencao nao pode ser desfeita pelo escape que vem depois:
        o `@pedrorezendefig` que o app pos e mencao de verdade, e fica."""
        texto = texto_espelhado("@Pedro Vitta e @Diretor do Hospital, e @alguem", mencionados=[PEDRO, DIRETOR])

        assert texto == "@pedrorezendefig e Pessoa do hospital, e @ alguem"
        assert _mencoes_vivas(texto, postas_pelo_app=("pedrorezendefig",)) == []

    def test_o_nome_mais_longo_ganha_quando_um_e_prefixo_do_outro(self):
        ana = {**DIRETOR, "id": "P3", "nome_completo": "Ana", "github_login": "ana-hsm"}
        ana_paula = {**DIRETOR, "id": "P4", "nome_completo": "Ana Paula", "github_login": None}

        texto = texto_espelhado("@Ana Paula e @Ana", mencionados=[ana, ana_paula])

        assert texto == "Pessoa do hospital e @ana-hsm"

    def test_o_nome_mencionado_nao_casa_o_comeco_de_outra_palavra(self):
        """ "Ana" mencionada e `@Anastácia` no texto: sem fronteira, sairia
        `@ana-hsmstácia`. Sai com espaco, como mencao digitada a mao."""
        ana = {**DIRETOR, "id": "P3", "nome_completo": "Ana", "github_login": "ana-hsm"}

        texto = texto_espelhado("@Anastácia e @Ana", mencionados=[ana])

        assert texto == "@ Anastácia e @ana-hsm"

    def test_nome_de_cadastro_com_sinal_de_menor_ainda_casa(self):
        """A troca roda sobre o texto BRUTO: o funil do `texto_do_diretor`
        transforma o texto (`<` vira `&lt;`) e nao o nome do cadastro."""
        estranha = {**DIRETOR, "id": "P3", "nome_completo": "Ana <Silva>", "github_login": None}

        texto = texto_espelhado("@Ana <Silva>, veja", mencionados=[estranha])

        assert texto == "Pessoa do hospital, veja"

    def test_o_rotulo_de_cada_pessoa(self):
        assert rotulo_no_github(PEDRO) == "@pedrorezendefig"
        assert rotulo_no_github(DIRETOR) == ROTULO_SEM_LOGIN
        assert rotulo_no_github({"github_login": "Nao Vale"}) == ROTULO_SEM_LOGIN
        assert rotulo_no_github(None) == ROTULO_SEM_LOGIN

    def test_o_corpo_espelhado_passa_o_texto_pelo_mesmo_funil(self):
        corpo = corpo_do_comentario_espelhado(
            texto="@Pedro Vitta, e @outro", autor=DIRETOR, demanda_id="d-1", mencionados=[PEDRO]
        )

        assert corpo.split("\n")[-1] == "@pedrorezendefig, e @ outro"


# ─── 2. Responder numa Demanda vinculada ─────────────────────────────────────


def _vinculada(did: str = "d-1", **campos) -> dict:
    campos.setdefault("etapa", "planejada")
    return _demanda(did, github_issue_numero=673, **campos)


class TestResponderEspelha:
    def test_responder_numa_demanda_vinculada_publica_o_comentario_e_grava_o_id(self, monkeypatch):
        """Criterio: chama o duble com o corpo esperado e grava o id devolvido
        na linha da Conversa. O corpo e o do servico puro, com o marcador de
        automacao porque o Pedro tem `github_login`."""
        client, sb, gh = _montar(logado=PEDRO, demandas=[_vinculada()], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Já pedi à Global Health"})

        assert resposta.status_code == 201
        assert gh.comentarios_criados == [
            {
                "numero": 673,
                "corpo": "<!-- automacao -->\n**@pedrorezendefig** escreveu na Demanda:\n\nJá pedi à Global Health",
                "id": 3_000_000_001,
            }
        ]
        assert _fio(sb)[0]["github_comentario_id"] == 3_000_000_001

    def test_o_diretor_sem_github_login_sai_com_o_marcador_do_revisor_e_o_rotulo_neutro(self, monkeypatch):
        """E o que acende `revisor-comentou` (ADR 0054, decisao 4). O rotulo
        neutro e o id da Demanda viajam no marcador; o nome civil nao sai e o
        login da integracao nao diz nada."""
        client, _, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "O botão ficou no lugar errado"})

        assert gh.comentarios_criados[0]["corpo"].split("\n")[0] == (
            '<!-- revisor-app autor="Pessoa do hospital" demanda="d-1" -->'
        )
        assert "Diretor do Hospital" not in gh.comentarios_criados[0]["corpo"]

    def test_a_mencao_do_app_chega_ao_github_como_login_e_o_arroba_solto_com_espaco(self, monkeypatch):
        """Pela rota: os mencionados vem de `mencoes` (ids), e e o router que
        resolve nome e login de cada um para o funil do texto."""
        client, _, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        resposta = client.post(
            f"{BASE}/demandas/d-1/conversa",
            json={"texto": "@Pedro Vitta, veja; e avisa o @fulano", "mencoes": ["P1"]},
        )

        assert resposta.status_code == 201
        assert gh.comentarios_criados[0]["corpo"].split("\n")[-1] == "@pedrorezendefig, veja; e avisa o @ fulano"
        assert "Pedro Vitta" not in gh.comentarios_criados[0]["corpo"]

    def test_demanda_sem_vinculo_nao_chama_o_github(self, monkeypatch):
        client, sb, gh = _montar(logado=PEDRO, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        resposta = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Anotado"})

        assert resposta.status_code == 201
        assert gh.comentarios_criados == []
        assert _fio(sb)[0]["texto"] == "Anotado"
        assert _fio(sb)[0].get("github_comentario_id") is None

    def test_vale_em_issue_fechada(self, monkeypatch):
        """ADR 0054, decisao 6: a resposta do diretor numa Demanda Entregue
        chega a issue fechada, e e o que reabre o trabalho (ADR 0020, decisao
        4). Nenhuma guarda de estado antes de espelhar."""
        entregue = _vinculada(
            etapa="entregue",
            estado="aguardando",
            github_foto={"estado": "closed", "motivo_do_fechamento": "completed", "labels": [], "partes": []},
        )
        client, _, gh = _montar(logado=DIRETOR, demandas=[entregue], monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Não ficou bom"})

        assert [c["numero"] for c in gh.comentarios_criados] == [673]

    def test_falha_do_github_mantem_a_resposta_responde_201_e_loga(self, monkeypatch, caplog):
        gh = _GithubFalso({}, erro_ao_comentar=github_client.GithubIndisponivelError("timeout"))
        client, sb, _ = _montar(logado=PEDRO, demandas=[_vinculada()], github=gh, monkeypatch=monkeypatch)

        with caplog.at_level("ERROR"):
            resposta = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Anotado"})

        assert resposta.status_code == 201
        assert resposta.json()["texto"] == "Anotado"
        assert _fio(sb)[0]["texto"] == "Anotado"
        assert _fio(sb)[0].get("github_comentario_id") is None
        assert any("espelhar" in r.getMessage() and "d-1" in r.getMessage() for r in caplog.records)

    def test_o_log_da_falha_nao_leva_o_texto_da_resposta(self, monkeypatch, caplog):
        gh = _GithubFalso({}, erro_ao_comentar=github_client.GithubIndisponivelError("timeout"))
        client, _, _ = _montar(logado=PEDRO, demandas=[_vinculada()], github=gh, monkeypatch=monkeypatch)

        with caplog.at_level("ERROR"):
            client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Segredo do paciente"})

        assert not any("Segredo do paciente" in r.getMessage() for r in caplog.records)

    def test_o_id_do_comentario_nao_sai_na_resposta_da_api(self, monkeypatch):
        """ADR 0054, decisao 9: nada tecnico chega a tela, e o id do comentario
        e tao tecnico quanto o numero da issue. As chaves da linha sao as do
        schema, nem uma a mais, tanto no 201 quanto na leitura do fio."""
        client, _, _ = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        enviada = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Anotado"}).json()
        lida = client.get(f"{BASE}/demandas/d-1/conversa").json()[0]

        esperadas = {
            "id",
            "demanda_id",
            "autor_id",
            "autor_nome",
            "linha",
            "texto",
            "mencoes",
            "movimento_campo",
            "movimento_de",
            "movimento_para",
            "criado_em",
            "editado_em",
            "editavel_ate",
            "aviso_por_email",
        }
        assert set(enviada) == esperadas
        assert set(lida) == esperadas


# ─── 2b. Linha automatica nunca espelha ──────────────────────────────────────


class TestLinhaAutomaticaNaoEspelha:
    """Criterio: movimento, responsavel, Etapa e Vinculo entram no fio e a
    issue nao recebe nada. Cada caso escreve a linha automatica de verdade
    (o par de presenca) e confere que o duble ficou quieto."""

    def test_mover_grava_a_linha_de_estado_e_nao_comenta(self, monkeypatch):
        client, sb, gh = _montar(logado=PEDRO, demandas=[_vinculada()], monkeypatch=monkeypatch)

        assert client.post(f"{BASE}/demandas/d-1/mover", json={"estado": "em_andamento"}).status_code == 200

        assert [linha["movimento_campo"] for linha in _fio(sb)] == ["estado"]
        assert gh.comentarios_criados == []

    def test_atribuir_grava_a_linha_de_responsavel_e_nao_comenta(self, monkeypatch):
        client, sb, gh = _montar(logado=PEDRO, demandas=[_vinculada()], monkeypatch=monkeypatch)

        assert client.post(f"{BASE}/demandas/d-1/atribuir", json={"responsavel_id": "P2"}).status_code == 200

        assert [linha["movimento_campo"] for linha in _fio(sb)] == ["responsavel"]
        assert gh.comentarios_criados == []

    def test_vincular_grava_vinculo_e_etapa_e_nao_comenta(self, monkeypatch):
        gh = _GithubFalso({673: _issue(673, labels=("ready-for-agent",))})
        client, sb, gh = _montar(logado=PEDRO, demandas=[_demanda("d-1")], github=gh, monkeypatch=monkeypatch)

        assert client.post(f"{BASE}/demandas/d-1/vincular", json={"numero": 673}).status_code == 200

        assert sorted(linha["movimento_campo"] for linha in _fio(sb)) == ["etapa", "vinculo"]
        assert gh.comentarios_criados == []

    def test_levar_para_desenvolvimento_grava_as_linhas_e_nao_comenta(self, monkeypatch):
        client, sb, gh = _montar(logado=PEDRO, demandas=[_demanda("d-1")], monkeypatch=monkeypatch)

        assert client.post(f"{BASE}/demandas/d-1/levar-para-desenvolvimento").status_code == 200

        assert {linha["movimento_campo"] for linha in _fio(sb)} >= {"vinculo"}
        assert gh.comentarios_criados == []


# ─── 3. Corrigir a resposta ──────────────────────────────────────────────────


class TestCorrigirEspelha:
    """Envio e correcao na MESMA montagem, sobre a mesma linha: e o id que o
    envio gravou que a correcao tem de usar, e uma linha fabricada a mao com o
    id ja dentro nao provaria essa ponte."""

    def _responder(self, client, sb):
        linha_id = client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Versao com erro"}).json()["id"]
        # O duble carimba `criado_em` numa data fixa; a janela de correcao e
        # de 10 minutos a partir do relogio de verdade.
        _fio(sb)[0]["criado_em"] = datetime.now(UTC).isoformat()
        return linha_id

    def test_corrigir_dentro_da_janela_edita_o_comentario_pelo_id_gravado(self, monkeypatch):
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)
        linha_id = self._responder(client, sb)

        resposta = client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": "Versão corrigida"})

        assert resposta.status_code == 200
        assert gh.comentarios_editados == [
            {
                "id": 3_000_000_001,
                "corpo": (
                    '<!-- revisor-app autor="Pessoa do hospital" demanda="d-1" -->\n'
                    "**Pessoa do hospital** escreveu na Demanda:\n\n"
                    "Versão corrigida"
                ),
            }
        ]
        # Editou, e nao publicou outro: o comentario do envio continua sendo o unico.
        assert len(gh.comentarios_criados) == 1

    def test_a_correcao_com_mencao_tambem_resolve_o_login_e_poe_espaco_no_arroba_solto(self, monkeypatch):
        """A correcao passa pelo mesmo funil do envio, com as mencoes DA
        CORRECAO: sem isso, corrigir para "@Pedro Vitta" publicaria o nome."""
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)
        linha_id = self._responder(client, sb)

        resposta = client.patch(
            f"{BASE}/demandas/d-1/conversa/{linha_id}",
            json={"texto": "@Pedro Vitta, corrigido; e o @fulano", "mencoes": ["P1"]},
        )

        assert resposta.status_code == 200
        assert gh.comentarios_editados[0]["corpo"].split("\n")[-1] == "@pedrorezendefig, corrigido; e o @ fulano"
        assert "Pedro Vitta" not in gh.comentarios_editados[0]["corpo"]

    def test_sem_id_gravado_a_correcao_nao_chama_nada(self, monkeypatch):
        """A resposta que nasceu com o GitHub fora do ar ficou sem id. Corrigir
        nao publica um comentario novo (a issue guardaria a correcao sem o
        original) nem tenta editar o nada."""
        gh = _GithubFalso({}, erro_ao_comentar=github_client.GithubIndisponivelError("timeout"))
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], github=gh, monkeypatch=monkeypatch)
        linha_id = self._responder(client, sb)
        assert _fio(sb)[0].get("github_comentario_id") is None
        gh.erro_ao_comentar = None  # o GitHub voltou; mesmo assim nao ha o que editar

        resposta = client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": "Versão corrigida"})

        assert resposta.status_code == 200
        assert gh.comentarios_editados == []
        assert gh.comentarios_criados == []

    def test_falha_ao_editar_mantem_a_correcao_e_loga(self, monkeypatch, caplog):
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)
        linha_id = self._responder(client, sb)
        gh.erro_ao_comentar = github_client.GithubIndisponivelError("timeout")

        with caplog.at_level("ERROR"):
            resposta = client.patch(f"{BASE}/demandas/d-1/conversa/{linha_id}", json={"texto": "Versão corrigida"})

        assert resposta.status_code == 200
        assert _fio(sb)[0]["texto"] == "Versão corrigida"
        assert any("3000000001" in r.getMessage() for r in caplog.records)


# ─── 3b. Nada do GitHub volta para a Conversa ────────────────────────────────


class TestNadaVoltaDoGithub:
    def test_o_cliente_nao_tem_verbo_de_ler_comentario(self):
        """ADR 0054, decisao 5: nenhuma rota le comentarios do GitHub para
        dentro da Conversa. O cliente e a unica porta para a API, entao sem
        verbo de leitura ali nao ha rota que consiga."""
        verbos = [nome for nome in dir(github_client) if "comentario" in nome and not nome.startswith("_")]

        assert sorted(verbos) == ["criar_comentario", "editar_comentario"]

    def test_o_fio_depois_de_espelhar_tem_so_o_que_o_app_escreveu(self, monkeypatch):
        client, sb, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "Anotado"})
        fio = client.get(f"{BASE}/demandas/d-1/conversa").json()

        assert len(gh.comentarios_criados) == 1  # par de presenca: o espelho aconteceu
        assert [(linha["linha"], linha["texto"]) for linha in fio] == [("resposta", "Anotado")]


# ─── 4. A migration ──────────────────────────────────────────────────────────


class TestMigration:
    def test_acrescenta_a_coluna_do_comentario_nula_por_padrao(self):
        sql = MIGRATION.read_text(encoding="utf-8")

        assert "ALTER TABLE tecnologia_conversas ADD COLUMN IF NOT EXISTS github_comentario_id BIGINT;" in sql
        assert "NOT NULL" not in sql.split("github_comentario_id BIGINT")[1].split(";")[0]

    def test_nao_cria_tabela_nova(self):
        """Sem CREATE TABLE nao ha superficie nova de RLS para ligar; se um dia
        houver, este teste e o lembrete."""
        comandos = [linha for linha in MIGRATION.read_text(encoding="utf-8").splitlines() if not linha.startswith("--")]

        assert "CREATE TABLE" not in "\n".join(comandos).upper()

    def test_sem_travessao(self):
        sql = MIGRATION.read_text(encoding="utf-8")

        assert chr(0x2014) not in sql
        assert chr(0x2013) not in sql


@pytest.mark.parametrize("tem_login", [True, False])
def test_nenhum_texto_novo_tem_travessao(tem_login):
    corpo = corpo_do_comentario_espelhado(texto="x", autor=PEDRO if tem_login else DIRETOR, demanda_id="d")

    assert chr(0x2014) not in corpo
    assert chr(0x2013) not in corpo
