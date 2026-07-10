"""Testes da estrutura dinâmica de seções do POP (issue #151, ADR 0016).

O rascunho de uma Versão deixa de ser um JSON de chaves fixas e vira uma lista
ordenada de seções `{ id, titulo, conteudo, tipo }`, com `tipo` em
`texto | fluxograma`. O `id` é estável e atribuído pelo sistema (não derivado
do título, que pode mudar).

Aqui testamos só o comportamento externo da fundação (M1), sem HTTP nem LLM:
- migração do rascunho legado (chaves fixas → lista de seções; Fluxograma → `fluxograma`);
- reconciliação de IDs entre turnos (preserva ao renomear/reordenar; ID novo só
  para seção inédita; seção removida some).
"""

from __future__ import annotations

from app.models.pops_schemas import SECOES_POP_CONTEUDO
from app.services.pops_secoes import (
    migrar_rascunho_legado,
    normalizar_secoes_do_agente,
)

CHAVES_LEGADAS = [chave for chave, _ in SECOES_POP_CONTEUDO]


# ─── Migração do rascunho legado ──────────────────────────────────────────────


class TestMigracaoRascunhoLegado:
    def test_legado_vira_lista_de_secoes_na_ordem_do_template(self):
        legado = {
            "objetivo": "Padronizar a higienização das mãos.",
            "abrangencia": "Aplica-se ao CTI.",
            "fluxograma": "1. Retirar adornos\n2. Molhar as mãos",
        }

        out = migrar_rascunho_legado(legado)

        assert isinstance(out, dict)
        secoes = out["secoes"]
        # Mantém a ordem canônica do template institucional.
        titulos = [s["titulo"] for s in secoes]
        assert titulos == ["Objetivo", "Abrangência", "Fluxograma"]
        objetivo = secoes[0]
        assert objetivo["conteudo"] == "Padronizar a higienização das mãos."
        assert objetivo["tipo"] == "texto"
        # Todo id é estável, único e não vazio.
        ids = [s["id"] for s in secoes]
        assert all(ids) and len(set(ids)) == len(ids)

    def test_fluxograma_legado_vira_secao_tipo_fluxograma(self):
        out = migrar_rascunho_legado({"fluxograma": "1. Passo único"})
        flux = out["secoes"][0]
        assert flux["titulo"] == "Fluxograma"
        assert flux["tipo"] == "fluxograma"

    def test_chave_em_branco_nao_vira_secao(self):
        """Seção legada vazia não polui a lista nova (esqueleto vazio some)."""
        out = migrar_rascunho_legado({"objetivo": "  ", "abrangencia": ""})
        assert out["secoes"] == []

    def test_rascunho_ja_novo_passa_intacto(self):
        novo = {"secoes": [{"id": "abc", "titulo": "Objetivo", "conteudo": "X.", "tipo": "texto"}]}
        out = migrar_rascunho_legado(novo)
        assert out["secoes"][0]["id"] == "abc"
        assert out["secoes"][0]["titulo"] == "Objetivo"

    def test_vazio_ou_none_vira_lista_vazia(self):
        assert migrar_rascunho_legado(None) == {"secoes": []}
        assert migrar_rascunho_legado({}) == {"secoes": []}


# ─── Reconciliação de IDs entre turnos ────────────────────────────────────────


def _secao(titulo: str, conteudo: str = "x", tipo: str = "texto", sid: str | None = None) -> dict:
    s = {"titulo": titulo, "conteudo": conteudo, "tipo": tipo}
    if sid is not None:
        s["id"] = sid
    return s


class TestReconciliacaoIds:
    def test_secao_inedita_recebe_id_novo(self):
        anteriores = []
        novas = [_secao("Objetivo")]
        out = normalizar_secoes_do_agente(novas, anteriores)
        assert len(out) == 1
        assert out[0]["id"]
        assert out[0]["titulo"] == "Objetivo"

    def test_renomear_preserva_id(self):
        """O agente devolve o id existente; renomear o título não troca o id —
        o apontar-seção (⌖) sobrevive ao rename."""
        anteriores = [{"id": "id-obj", "titulo": "Objetivo", "conteudo": "X.", "tipo": "texto"}]
        novas = [_secao("Objetivo geral", conteudo="X revisado.", sid="id-obj")]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert len(out) == 1
        assert out[0]["id"] == "id-obj"
        assert out[0]["titulo"] == "Objetivo geral"
        assert out[0]["conteudo"] == "X revisado."

    def test_reordenar_preserva_ids(self):
        anteriores = [
            {"id": "id-a", "titulo": "Objetivo", "conteudo": "A", "tipo": "texto"},
            {"id": "id-b", "titulo": "Abrangência", "conteudo": "B", "tipo": "texto"},
        ]
        # Agente devolve invertido, ecoando os ids.
        novas = [_secao("Abrangência", "B", sid="id-b"), _secao("Objetivo", "A", sid="id-a")]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert [s["id"] for s in out] == ["id-b", "id-a"]
        assert [s["titulo"] for s in out] == ["Abrangência", "Objetivo"]

    def test_secao_removida_some(self):
        anteriores = [
            {"id": "id-a", "titulo": "Objetivo", "conteudo": "A", "tipo": "texto"},
            {"id": "id-b", "titulo": "Abrangência", "conteudo": "B", "tipo": "texto"},
        ]
        # O agente devolve só a primeira: a segunda foi removida.
        novas = [_secao("Objetivo", "A", sid="id-a")]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert [s["id"] for s in out] == ["id-a"]

    def test_id_inventado_pelo_agente_nao_colide_com_existente(self):
        """Um id que o agente devolve mas que não existe na lista anterior é
        tratado como seção inédita: recebe id novo, distinto dos demais."""
        anteriores = [{"id": "id-a", "titulo": "Objetivo", "conteudo": "A", "tipo": "texto"}]
        novas = [
            _secao("Objetivo", "A", sid="id-a"),
            _secao("Seção nova", "N", sid="id-a"),  # id duplicado/forjado
        ]

        out = normalizar_secoes_do_agente(novas, anteriores)

        ids = [s["id"] for s in out]
        assert ids[0] == "id-a"
        assert len(set(ids)) == 2, "ids devem ser únicos mesmo com colisão forjada"

    def test_tipo_invalido_vira_texto(self):
        out = normalizar_secoes_do_agente([_secao("X", tipo="planilha")], [])
        assert out[0]["tipo"] == "texto"

    def test_secao_malformada_e_descartada(self):
        novas = ["não é dict", {"titulo": "Válida", "conteudo": "ok", "tipo": "texto"}, {"conteudo": "sem titulo"}]
        out = normalizar_secoes_do_agente(novas, [])
        assert len(out) == 1
        assert out[0]["titulo"] == "Válida"


# ─── SVG do fluxograma capturado no cliente (issue #153, ADR 0017) ────────────


class TestSvgFluxograma:
    def test_svg_persiste_atraves_de_turno_que_nao_muda_o_fluxo(self):
        """O SVG capturado no cliente (campo `svg` da seção de fluxograma) é
        carregado adiante quando o agente devolve a MESMA sintaxe Mermaid: o
        PDF segue embutindo o diagrama sem re-captura desnecessária."""
        anteriores = [
            {
                "id": "id-flux",
                "titulo": "Fluxograma",
                "conteudo": "flowchart TD\n  A[Início] --> B[Fim]",
                "tipo": "fluxograma",
                "svg": "<svg>diagrama</svg>",
            }
        ]
        # O agente ecoa a mesma seção, com a mesma sintaxe (sem reenviar o svg).
        novas = [_secao("Fluxograma", "flowchart TD\n  A[Início] --> B[Fim]", tipo="fluxograma", sid="id-flux")]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert out[0]["svg"] == "<svg>diagrama</svg>"

    def test_svg_e_descartado_quando_a_sintaxe_mermaid_muda(self):
        """Mermaid novo invalida o SVG antigo: ele cai, forçando re-captura no
        cliente para o PDF não embutir um diagrama defasado."""
        anteriores = [
            {
                "id": "id-flux",
                "titulo": "Fluxograma",
                "conteudo": "flowchart TD\n  A[Início] --> B[Fim]",
                "tipo": "fluxograma",
                "svg": "<svg>antigo</svg>",
            }
        ]
        novas = [
            _secao(
                "Fluxograma", "flowchart TD\n  A[Início] --> C[Conferir] --> B[Fim]", tipo="fluxograma", sid="id-flux"
            )
        ]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert "svg" not in out[0] or not out[0]["svg"]

    def test_secao_texto_nunca_carrega_svg(self):
        """Só a seção de fluxograma guarda SVG; uma seção de texto que por acaso
        tenha o campo no anterior não o propaga."""
        anteriores = [{"id": "id-o", "titulo": "Objetivo", "conteudo": "X", "tipo": "texto", "svg": "<svg>lixo</svg>"}]
        novas = [_secao("Objetivo", "X", tipo="texto", sid="id-o")]

        out = normalizar_secoes_do_agente(novas, anteriores)

        assert "svg" not in out[0]


# ─── Fluxograma como objeto JSON da gramática restrita (ADR 0024, #221) ───────

FLUX_OBJ = {
    "nos": [
        {"id": "n1", "tipo": "passo", "texto": "Higienizar as mãos"},
        {"id": "n2", "tipo": "passo", "texto": "Reunir o material"},
    ]
}

FLUX_OBJ_INVALIDO = {"nos": [{"id": "n1", "tipo": "decisao", "texto": "Conforme?", "ramos": [{"rotulo": "Sim"}]}]}


class TestFluxogramaObjetoJson:
    def test_objeto_valido_persiste_como_objeto(self):
        """O `conteudo` da seção de fluxograma passa a ser objeto JSON validado
        (ADR 0024): objeto que obedece à gramática atravessa a normalização
        intacto, como objeto."""
        novas = [_secao("Fluxograma", tipo="fluxograma", sid=None) | {"conteudo": FLUX_OBJ}]
        out = normalizar_secoes_do_agente(novas, [])
        assert out[0]["conteudo"] == FLUX_OBJ
        assert isinstance(out[0]["conteudo"], dict)

    def test_objeto_invalido_vira_string_json(self):
        """Objeto fora da gramática NÃO persiste como objeto (senão o request
        seguinte, que ecoa o rascunho, seria recusado): vira string JSON, que a
        tela mostra com o aviso de pedir a regeração no chat."""
        novas = [_secao("Fluxograma", tipo="fluxograma", sid=None) | {"conteudo": FLUX_OBJ_INVALIDO}]
        out = normalizar_secoes_do_agente(novas, [])
        assert isinstance(out[0]["conteudo"], str)
        assert "Conforme?" in out[0]["conteudo"]

    def test_string_mermaid_legada_atravessa_intacta(self):
        """Conteúdo legado (string Mermaid) segue passando durante a transição
        (a migração é a fatia #224)."""
        novas = [_secao("Fluxograma", "flowchart TD\n  A --> B", tipo="fluxograma")]
        out = normalizar_secoes_do_agente(novas, [])
        assert out[0]["conteudo"] == "flowchart TD\n  A --> B"

    def test_objeto_em_secao_texto_vira_string_vazia(self):
        """Só a seção de fluxograma aceita objeto; nas demais o contrato segue
        string (objeto espúrio não vaza)."""
        novas = [_secao("Objetivo", tipo="texto") | {"conteudo": {"nos": []}}]
        out = normalizar_secoes_do_agente(novas, [])
        assert out[0]["conteudo"] == ""

    def test_svg_persiste_quando_o_objeto_nao_muda(self):
        anteriores = [
            {"id": "id-flux", "titulo": "Fluxograma", "conteudo": FLUX_OBJ, "tipo": "fluxograma", "svg": "<svg>d</svg>"}
        ]
        novas = [_secao("Fluxograma", tipo="fluxograma", sid="id-flux") | {"conteudo": FLUX_OBJ}]
        out = normalizar_secoes_do_agente(novas, anteriores)
        assert out[0]["svg"] == "<svg>d</svg>"

    def test_svg_cai_quando_o_objeto_muda(self):
        anteriores = [
            {"id": "id-flux", "titulo": "Fluxograma", "conteudo": FLUX_OBJ, "tipo": "fluxograma", "svg": "<svg>d</svg>"}
        ]
        outro = {"nos": [{"id": "n1", "tipo": "passo", "texto": "Outro passo"}]}
        novas = [_secao("Fluxograma", tipo="fluxograma", sid="id-flux") | {"conteudo": outro}]
        out = normalizar_secoes_do_agente(novas, anteriores)
        assert "svg" not in out[0] or not out[0]["svg"]

    def test_svg_cai_na_troca_de_mermaid_para_objeto(self):
        anteriores = [
            {
                "id": "id-flux",
                "titulo": "Fluxograma",
                "conteudo": "flowchart TD\n  A --> B",
                "tipo": "fluxograma",
                "svg": "<svg>antigo</svg>",
            }
        ]
        novas = [_secao("Fluxograma", tipo="fluxograma", sid="id-flux") | {"conteudo": FLUX_OBJ}]
        out = normalizar_secoes_do_agente(novas, anteriores)
        assert "svg" not in out[0] or not out[0]["svg"]
