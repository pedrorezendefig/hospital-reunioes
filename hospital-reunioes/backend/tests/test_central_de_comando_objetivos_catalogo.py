"""O catálogo dos Objetivos, testado direto (issue #820, PRD #809).

Porte de `src/lib/objetivos/catalogo.test.ts`, com o vocabulário da ADR 0058:
seis Objetivos na ordem do design, dois em construção (a Área do site e a nota
no Google), e nenhuma tela chamando um Objetivo de "meta" nem falando em
"braço".
"""

from __future__ import annotations

import re

from app.services.central_de_comando.objetivos.catalogo import OBJETIVOS, objetivo_por_id


class TestCatalogo:
    def test_tem_os_seis_objetivos_na_ordem_do_design(self):
        assert [o.id for o in OBJETIVOS] == [
            "site-visitantes",
            "instagram-seguidores",
            "instagram-engajamento",
            "site-area",
            "contatos",
            "google-reputacao",
        ]

    def test_todo_objetivo_tem_nome_e_descricao(self):
        for o in OBJETIVOS:
            assert o.nome.strip(), o.id
            assert o.descricao.strip(), o.id

    def test_os_dois_em_construcao_sao_a_area_do_site_e_a_nota_no_google(self):
        em_construcao = [o.id for o in OBJETIVOS if o.em_construcao]
        assert em_construcao == ["site-area", "google-reputacao"]

    def test_quatro_objetivos_tem_dado_e_dois_estao_em_construcao(self):
        com_dado = [o.id for o in OBJETIVOS if not o.em_construcao]
        assert len(com_dado) == 4
        assert len([o for o in OBJETIVOS if o.em_construcao]) == 2

    def test_objetivo_por_id_acha_e_devolve_none_para_id_desconhecido(self):
        achado = objetivo_por_id("contatos")
        assert achado is not None
        assert achado.nome == "Gerar mais contatos"
        assert objetivo_por_id("inexistente") is None


class TestVocabulario:
    """ADR 0058: a palavra "meta" e a palavra "braço" não aparecem em nada que
    a diretoria lê. O catálogo alimenta a galeria, então o texto dele é tela."""

    _META = re.compile(r"\bmeta\b", re.IGNORECASE)
    _NOME_ANTIGO = re.compile(r"bra[cç]os?\b", re.IGNORECASE)

    def _texto_da_tela(self) -> str:
        return " ".join(f"{o.id} {o.nome} {o.descricao}" for o in OBJETIVOS)

    def test_nenhum_objetivo_e_chamado_de_meta(self):
        assert not self._META.search(self._texto_da_tela())

    def test_o_nome_antigo_do_braco_nao_aparece_e_virou_area_do_site(self):
        texto = self._texto_da_tela()
        assert not self._NOME_ANTIGO.search(texto)
        assert "Área do site" in texto
