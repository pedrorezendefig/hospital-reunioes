"""Testes da gramática restrita do Fluxograma de POP (ADR 0024, issue #221).

O `conteudo` da seção de tipo `fluxograma` deixa de ser sintaxe Mermaid e
passa a ser um objeto JSON validado por schema: a lista `nos` é a coluna
principal (Início e Fim implícitos), decisões binárias têm exatamente 2 ramos
rotulados e um ramo pode desviar para um card lateral que retorna a um nó
(`retorna_para`) ou segue o fluxo. Decisões com 3+ ramos e saltos (`vai_para`)
ficam para a fatia #222.

Testa comportamento externo: a gramática válida passa, a inválida é recusada
com mensagem legível; o fallback de texto (PDF sem SVG) deriva uma lista
numerada do objeto sem quebrar.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.models.pops_fluxograma import (  # noqa: E402
    FluxogramaInvalidoError,
    fluxograma_texto_fallback,
    fluxograma_valido,
    validar_fluxograma,
)

# Exemplo canônico do PRD #210 (punção venosa reduzida).
FLUXOGRAMA_VALIDO = {
    "nos": [
        {"id": "n1", "tipo": "passo", "texto": "Higienizar as mãos"},
        {"id": "n2", "tipo": "passo", "texto": "Reunir o material de punção"},
        {
            "id": "n3",
            "tipo": "decisao",
            "texto": "Material completo?",
            "ramos": [
                {
                    "rotulo": "Não",
                    "desvio": {"texto": "Solicitar reposição ao almoxarifado", "retorna_para": "n2"},
                },
                {"rotulo": "Sim"},
            ],
        },
        {"id": "n4", "tipo": "passo", "texto": "Realizar a punção venosa"},
    ]
}


class TestGramaticaValida:
    def test_exemplo_canonico_passa(self):
        estrutura = validar_fluxograma(FLUXOGRAMA_VALIDO)
        assert [no.id for no in estrutura.nos] == ["n1", "n2", "n3", "n4"]

    def test_fluxo_linear_sem_decisao_passa(self):
        assert fluxograma_valido({"nos": [{"id": "a", "tipo": "passo", "texto": "Passo único"}]})

    def test_desvio_sem_retorna_para_segue_o_fluxo(self):
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "Preparar"},
                {
                    "id": "n2",
                    "tipo": "decisao",
                    "texto": "Conforme?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Ajustar e registrar"}},
                        {"rotulo": "Sim"},
                    ],
                },
                {"id": "n3", "tipo": "passo", "texto": "Concluir"},
            ]
        }
        assert fluxograma_valido(obj)


class TestGramaticaInvalida:
    def test_nao_dict_e_recusado(self):
        for invalido in (None, "flowchart TD", 42, ["nos"]):
            with pytest.raises(FluxogramaInvalidoError):
                validar_fluxograma(invalido)
            assert not fluxograma_valido(invalido)

    def test_lista_de_nos_vazia_e_recusada(self):
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma({"nos": []})

    def test_no_sem_texto_e_recusado(self):
        for texto in ("", "   "):
            obj = {"nos": [{"id": "n1", "tipo": "passo", "texto": texto}]}
            with pytest.raises(FluxogramaInvalidoError):
                validar_fluxograma(obj)

    def test_decisao_com_menos_de_2_ramos_e_recusada(self):
        obj = {
            "nos": [
                {"id": "n1", "tipo": "decisao", "texto": "Conforme?", "ramos": [{"rotulo": "Sim"}]},
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_decisao_sem_ramos_e_recusada(self):
        obj = {"nos": [{"id": "n1", "tipo": "decisao", "texto": "Conforme?"}]}
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_decisao_com_3_ramos_fica_para_a_fatia_seguinte(self):
        # Decisões N-árias são a fatia #222: nesta, o schema trava em 2 ramos.
        obj = {
            "nos": [
                {
                    "id": "n1",
                    "tipo": "decisao",
                    "texto": "Classificação de risco?",
                    "ramos": [{"rotulo": "Verde"}, {"rotulo": "Amarelo"}, {"rotulo": "Vermelho"}],
                }
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_retorna_para_id_inexistente_e_recusado(self):
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "Preparar"},
                {
                    "id": "n2",
                    "tipo": "decisao",
                    "texto": "Conforme?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Refazer", "retorna_para": "fantasma"}},
                        {"rotulo": "Sim"},
                    ],
                },
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_ids_duplicados_sao_recusados(self):
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "A"},
                {"id": "n1", "tipo": "passo", "texto": "B"},
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_passo_com_ramos_e_recusado(self):
        obj = {"nos": [{"id": "n1", "tipo": "passo", "texto": "A", "ramos": [{"rotulo": "Sim"}]}]}
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_tipo_desconhecido_e_recusado(self):
        obj = {"nos": [{"id": "n1", "tipo": "raia", "texto": "A"}]}
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_vai_para_fica_para_a_fatia_seguinte(self):
        # Saltos (`vai_para`) são a fatia #222: campo desconhecido é recusado.
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "A"},
                {
                    "id": "n2",
                    "tipo": "decisao",
                    "texto": "Grave?",
                    "ramos": [{"rotulo": "Sim", "vai_para": "fim"}, {"rotulo": "Não"}],
                },
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_dois_desvios_na_mesma_decisao_sao_recusados(self):
        # Layout fechado da fatia: coluna principal + no máximo 1 desvio lateral
        # por decisão (o outro ramo segue o fluxo).
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "A"},
                {
                    "id": "n2",
                    "tipo": "decisao",
                    "texto": "Conforme?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Refazer", "retorna_para": "n1"}},
                        {"rotulo": "Sim", "desvio": {"texto": "Registrar exceção"}},
                    ],
                },
            ]
        }
        with pytest.raises(FluxogramaInvalidoError):
            validar_fluxograma(obj)

    def test_mensagem_de_erro_e_legivel(self):
        try:
            validar_fluxograma({"nos": [{"id": "n1", "tipo": "passo", "texto": ""}]})
        except FluxogramaInvalidoError as e:
            assert str(e).strip(), "mensagem de erro vazia"


class TestFallbackTexto:
    """PDF sem SVG capturado: lista numerada derivada do objeto (PRD #210)."""

    def test_lista_numerada_dos_passos(self):
        texto = fluxograma_texto_fallback(FLUXOGRAMA_VALIDO)
        assert "1. Higienizar as mãos" in texto
        assert "2. Reunir o material de punção" in texto
        assert "Material completo?" in texto
        assert "Solicitar reposição ao almoxarifado" in texto
        assert "Sim" in texto and "Não" in texto

    def test_tolerante_a_objeto_fora_da_gramatica(self):
        # Defensivo: não valida, deriva o que der (nunca quebra o PDF).
        assert fluxograma_texto_fallback({"qualquer": "coisa"}) != ""
        assert "Passo" not in fluxograma_texto_fallback({})

    def test_desvio_com_retorno_legivel(self):
        # Issue #223: o retorno do desvio (`retorna_para`) aparece em texto
        # claro, apontando o número do passo de destino.
        texto = fluxograma_texto_fallback(FLUXOGRAMA_VALIDO)
        assert "Não: Solicitar reposição ao almoxarifado; retorna ao passo 2" in texto

    def test_desvio_sem_retorno_segue_o_fluxo(self):
        obj = {
            "nos": [
                {"id": "n1", "tipo": "passo", "texto": "Preparar o material"},
                {
                    "id": "n2",
                    "tipo": "decisao",
                    "texto": "Material completo?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Repor material"}},
                        {"rotulo": "Sim"},
                    ],
                },
            ]
        }
        texto = fluxograma_texto_fallback(obj)
        # Sem `retorna_para`, o desvio segue o fluxo: nada de "retorna ao passo".
        assert "Não: Repor material" in texto
        assert "retorna ao passo" not in texto

    def test_retorno_para_no_que_nao_e_passo_usa_o_texto_do_alvo(self):
        # Tolerante: alvo que não é passo numerado (ou id desconhecido) não
        # pode virar "passo None"; usa o texto do alvo ou omite o retorno.
        obj = {
            "nos": [
                {
                    "id": "d1",
                    "tipo": "decisao",
                    "texto": "Primeira decisão?",
                    "ramos": [{"rotulo": "Sim"}, {"rotulo": "Não"}],
                },
                {"id": "p1", "tipo": "passo", "texto": "Executar"},
                {
                    "id": "d2",
                    "tipo": "decisao",
                    "texto": "Deu certo?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Reavaliar", "retorna_para": "d1"}},
                        {"rotulo": "Sim"},
                    ],
                },
            ]
        }
        texto = fluxograma_texto_fallback(obj)
        assert 'Não: Reavaliar; retorna a "Primeira decisão?"' in texto
        assert "None" not in texto

    def test_retorno_para_id_desconhecido_nao_quebra(self):
        obj = {
            "nos": [
                {"id": "p1", "tipo": "passo", "texto": "Executar"},
                {
                    "id": "d1",
                    "tipo": "decisao",
                    "texto": "Deu certo?",
                    "ramos": [
                        {"rotulo": "Não", "desvio": {"texto": "Reavaliar", "retorna_para": "fantasma"}},
                        {"rotulo": "Sim"},
                    ],
                },
            ]
        }
        texto = fluxograma_texto_fallback(obj)
        assert "Não: Reavaliar" in texto
        assert "None" not in texto
