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
    corpo_do_comentario_espelhado,
    marcador_do_revisor_no_app,
)

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "104_tecnologia_conversa_espelhada.sql"


# ─── 1. O corpo do comentario espelhado ──────────────────────────────────────


class TestCorpoDoComentarioEspelhado:
    def test_autor_com_github_login_sai_com_o_marcador_de_automacao(self):
        """Criterio: a resposta de quem tem login (a Vitta respondendo ao
        diretor) NAO acende `revisor-comentou`. `<!-- automacao -->` e o
        marcador que a Action ja ignora."""
        corpo = corpo_do_comentario_espelhado(
            texto="Já pedi à Global Health",
            autor_nome="Pedro Vitta",
            demanda_id="d-1",
            tem_github_login=True,
        )

        assert corpo == "<!-- automacao -->\n**Pedro Vitta** escreveu na Demanda:\n\nJá pedi à Global Health"

    def test_autor_sem_github_login_sai_com_o_marcador_do_revisor(self):
        """Criterio: o marcador na forma LITERAL `<!-- revisor-app autor="Nome"
        demanda="id" -->`, um espaco so depois de `<!--`. O matcher da Action
        aceita exatamente um espaco; dois falham em silencio."""
        corpo = corpo_do_comentario_espelhado(
            texto="O botão ficou no lugar errado",
            autor_nome="Diretor do Hospital",
            demanda_id="d-1",
            tem_github_login=False,
        )

        assert corpo == (
            '<!-- revisor-app autor="Diretor do Hospital" demanda="d-1" -->\n'
            "**Diretor do Hospital** escreveu na Demanda:\n\n"
            "O botão ficou no lugar errado"
        )

    def test_o_marcador_e_a_primeira_linha_e_fica_sozinho_nela(self):
        """O mesmo dado dos dois testes acima, olhado pela forma: a Action
        ancora o marcador no inicio do corpo, entao ele tem de ser a primeira
        coisa e nao dividir a linha com o texto."""
        for tem_login in (True, False):
            corpo = corpo_do_comentario_espelhado(
                texto="texto", autor_nome="Alguém", demanda_id="d-1", tem_github_login=tem_login
            )
            primeira, *_resto = corpo.split("\n")
            assert primeira.startswith("<!-- ")
            assert primeira.endswith(" -->")
            assert primeira.count("<!--") == 1

    def test_a_forma_literal_do_marcador_do_revisor(self):
        assert marcador_do_revisor_no_app(autor_nome="Ana", demanda_id="abc") == (
            '<!-- revisor-app autor="Ana" demanda="abc" -->'
        )
        assert MARCADOR_AUTOMACAO == "<!-- automacao -->"

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

        corpo = corpo_do_comentario_espelhado(
            texto=texto, autor_nome="Pedro Vitta", demanda_id="d-1", tem_github_login=True
        )

        linhas = corpo.split("\n")
        assert linhas[0] == MARCADOR_AUTOMACAO
        assert '&lt;!-- revisor-app autor="Impostor" demanda="outra" -->' in linhas
        assert corpo.count("<!--") == 1
        assert 'revisor-app autor="Impostor"' in corpo  # o texto do diretor continua legivel

    def test_o_nome_do_autor_nao_fecha_o_marcador_antes_da_hora(self):
        """O nome vem do cadastro, e `"` ou `-->` nele quebrariam o atributo ou
        fechariam o comentario HTML no meio. O marcador continua inteiro e
        literal, com o nome limpo."""
        corpo = corpo_do_comentario_espelhado(
            texto="texto", autor_nome='Ana "A" --> <b>', demanda_id="d-1", tem_github_login=False
        )

        primeira = corpo.split("\n")[0]
        assert primeira == '<!-- revisor-app autor="Ana \'A\' -- b" demanda="d-1" -->'

    def test_texto_com_travessao_sai_sem_travessao(self):
        corpo = corpo_do_comentario_espelhado(
            texto=f"antes {chr(0x2014)} depois", autor_nome="Ana", demanda_id="d-1", tem_github_login=True
        )

        assert chr(0x2014) not in corpo
        assert "antes, depois" in corpo


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
                "corpo": "<!-- automacao -->\n**Pedro Vitta** escreveu na Demanda:\n\nJá pedi à Global Health",
                "id": 3_000_000_001,
            }
        ]
        assert _fio(sb)[0]["github_comentario_id"] == 3_000_000_001

    def test_o_diretor_sem_github_login_sai_com_o_marcador_do_revisor_e_o_nome_dele(self, monkeypatch):
        """E o que acende `revisor-comentou` (ADR 0054, decisao 4). O nome e o
        id da Demanda viajam no marcador; o login da integracao nao diz nada."""
        client, _, gh = _montar(logado=DIRETOR, demandas=[_vinculada()], monkeypatch=monkeypatch)

        client.post(f"{BASE}/demandas/d-1/conversa", json={"texto": "O botão ficou no lugar errado"})

        assert gh.comentarios_criados[0]["corpo"].split("\n")[0] == (
            '<!-- revisor-app autor="Diretor do Hospital" demanda="d-1" -->'
        )

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
                    '<!-- revisor-app autor="Diretor do Hospital" demanda="d-1" -->\n'
                    "**Diretor do Hospital** escreveu na Demanda:\n\n"
                    "Versão corrigida"
                ),
            }
        ]
        # Editou, e nao publicou outro: o comentario do envio continua sendo o unico.
        assert len(gh.comentarios_criados) == 1

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
    corpo = corpo_do_comentario_espelhado(texto="x", autor_nome="A", demanda_id="d", tem_github_login=tem_login)

    assert chr(0x2014) not in corpo
    assert chr(0x2013) not in corpo
