"""O sexto tipo da manifestação: `informacao` (issue #490, PRD #471, ADR 0040).

O cartaz do ponto de escuta promete quatro naturezas a quem lê o QR, e uma
delas é informação (RN-88). A lista de tipos do ouvidor tinha cinco, e nenhum
deles era esse: o que o papel promete não existia na triagem, e o pedido de
informação acabava carimbado de reclamação.

Esta suíte cobre a lista fechada como função pura (é ela que os dois schemas do
router repetem) e o CHECK da migration que a espelha no banco. As duas portas
que classificam continuam cobertas nos seus próprios arquivos
(`test_ouvidoria_validacao_acionamento.py` e `test_ouvidoria_sigilo.py`).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.ouvidoria_taxonomia import (  # noqa: E402
    ROTULO_TIPO,
    TIPOS_MANIFESTACAO,
    TIPOS_SIGILOSOS,
    nasce_sigilosa,
    resolver_sigilo,
)


class TestListaFechadaDeSeisTipos:
    """ADR 0040, decisão 1: a lista do ADR 0037 passa de cinco para seis."""

    def test_informacao_e_o_sexto_tipo(self):
        assert TIPOS_MANIFESTACAO == (
            "denuncia",
            "reclamacao",
            "sugestao",
            "elogio",
            "relato_de_conduta",
            "informacao",
        )

    def test_relato_de_conduta_nao_e_renomeado(self):
        """ADR 0040, decisão 2: a RN-57 escreveu `relato_conduta`, mas o valor
        em uso em produção fica. Renomear seria migration de dado com risco e
        sem ganho funcional, e o histórico já gravado apontaria para um valor
        que o CHECK não aceita mais."""
        assert "relato_de_conduta" in TIPOS_MANIFESTACAO
        assert "relato_conduta" not in TIPOS_MANIFESTACAO

    def test_todo_tipo_tem_rotulo_humano_e_o_novo_e_informacao(self):
        """O rótulo é o que aparece na trilha do caso e na tela. Tipo sem
        rótulo faz `ROTULO_TIPO[...]` estourar KeyError dentro da rota de
        classificação, ou seja: o tipo entraria na lista e derrubaria a porta
        que o usa."""
        assert sorted(ROTULO_TIPO) == sorted(TIPOS_MANIFESTACAO)
        assert ROTULO_TIPO["informacao"] == "Informação"


class TestInformacaoNaoESigilosaPorNatureza:
    """ADR 0040, decisão 1: o tipo novo entra sem sigilo por natureza, e as
    regras do ADR 0037 para os demais não mudam em nada."""

    def test_caso_de_informacao_nao_nasce_sigiloso(self):
        assert nasce_sigilosa("informacao") is False

    def test_a_lista_de_sigilosos_continua_com_dois_valores(self):
        """A mutação que esta asserção pega: acrescentar `informacao` a
        `TIPOS_SIGILOSOS`. Sem ela, alguém "cuidadoso" prenderia o tipo novo e
        só a tela contaria a história, tarde demais."""
        assert TIPOS_SIGILOSOS == frozenset({"denuncia", "relato_de_conduta"})

    def test_denuncia_e_relato_de_conduta_seguem_sigilosos(self):
        """A mutação simétrica: tirar um dos dois da lista ao mexer nela para
        acomodar o sexto tipo."""
        assert nasce_sigilosa("denuncia") is True
        assert nasce_sigilosa("relato_de_conduta") is True

    def test_caso_sem_tipo_segue_fail_closed(self):
        """O canal aberto grava o caso sem tipo, e é assim que ele fica até o
        ouvidor classificar. Um tipo novo na lista não afrouxa a entrada."""
        assert nasce_sigilosa(None) is True

    def test_o_ouvidor_pode_retirar_o_sigilo_de_um_caso_de_informacao(self):
        """O caso do canal aberto nasce preso; classificar como informação é o
        que o devolve ao índice de quem está fora da Ouvidoria."""
        assert resolver_sigilo("informacao", sigilo_atual=True, sigilo_pedido=False) is False

    def test_sem_pedido_explicito_o_sigilo_de_hoje_e_mantido(self):
        """Descer o sigilo é ato consciente, não efeito colateral de
        classificar: vale para o tipo novo como vale para os outros."""
        assert resolver_sigilo("informacao", sigilo_atual=True, sigilo_pedido=None) is True


class TestMigration093:
    """O CHECK do banco espelha a lista da aplicação: a aplicação recusa antes,
    o banco recusa depois, e nenhuma das duas confia na outra."""

    def _ddl(self) -> str:
        caminho = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "supabase",
            "migrations",
            "093_ouvidoria_tipo_informacao.sql",
        )
        with open(caminho, encoding="utf-8") as f:
            return f.read().lower()

    def _comandos(self) -> str:
        """Só o SQL que roda, sem as linhas de comentário.

        A prosa do cabeçalho fala de `ADD CONSTRAINT` e de `UPDATE` para
        explicar por que a ordem é essa e por que não há backfill. Casar contra
        o arquivo inteiro faria as asserções lerem a explicação em vez do
        comando, e elas passariam (ou falhariam) pelo texto errado."""
        return "\n".join(linha for linha in self._ddl().splitlines() if not linha.lstrip().startswith("--"))

    def test_o_check_antigo_sai_antes_de_o_novo_entrar(self):
        """`ADD CONSTRAINT` com o nome de uma constraint que já existe é erro:
        sem o DROP antes, a migration não roda nem uma vez."""
        sql = self._comandos()
        assert "drop constraint if exists ouvidoria_protocolos_tipo_manifestacao_check" in sql
        assert sql.index("drop constraint") < sql.index("add constraint")

    def test_os_seis_tipos_entram_no_check(self):
        check = self._comandos().split("add constraint", 1)[1]
        for tipo in TIPOS_MANIFESTACAO:
            assert f"'{tipo}'" in check, f"o CHECK não aceita {tipo}"

    def test_o_check_continua_aceitando_o_caso_sem_tipo(self):
        """NULL é o estado "ainda não classificado", que é como o canal aberto
        entra. Um CHECK que o recusasse quebraria toda criação de caso."""
        assert "tipo_manifestacao is null or" in self._comandos().split("add constraint", 1)[1]

    def test_nenhuma_linha_ja_gravada_e_reclassificada(self):
        """A migration só abre a lista. Carimbar `informacao` em caso antigo
        seria gravar no banco uma decisão que ouvidor nenhum tomou."""
        assert "update ouvidoria_protocolos" not in self._comandos()

    def test_a_coluna_carrega_a_lista_nova_no_comentario(self):
        """Quem for mexer na coluna lê os seis valores ali, sem ter de achar
        esta issue nem a migration 077."""
        sql = self._comandos()
        assert "comment on column ouvidoria_protocolos.tipo_manifestacao" in sql
        assert "informacao" in sql.split("comment on column ouvidoria_protocolos.tipo_manifestacao", 1)[1]
