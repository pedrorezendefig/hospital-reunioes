"""O texto de ajuda do Extrato para o setor contra a regra que monta o
acionamento (issue #769).

A tela de validação diz ao ouvidor o que vai à área além do extrato, e muda a
frase conforme o caso: comum, anônimo ou sigilo reforçado. A regra mora aqui no
backend (`montar_blocos`, `identificacao_do_caso`, `paciente_do_caso`), e a
tela espelha as três variantes porque a marca de sigilo muda ao vivo no modal,
antes de qualquer ida ao servidor.

O espelho é o contrato em `frontend/src/lib/ouvidoria/o-que-viaja-ao-setor.json`:
este teste prova que ele diz o que a regra faz, e o teste do front prova que a
frase de cada variante diz o que o contrato manda. Mudou a regra, este teste
fica vermelho até o contrato mudar; mudou o contrato, o do front fica vermelho
até a frase mudar.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.services.ouvidoria_blocos import (
    CHAVE_NOTA,
    identificacao_do_caso,
    montar_blocos,
    paciente_do_caso,
)

CONTRATO = (
    pathlib.Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "ouvidoria" / "o-que-viaja-ao-setor.json"
)


def _contrato() -> dict:
    return json.loads(CONTRATO.read_text(encoding="utf-8"))


def _o_que_viaja_alem_do_extrato(manifestacao: dict) -> set[str]:
    """O que a área recebe além da nota, lido das funções que montam o email e
    a tela do responsável, e não de uma cópia da regra."""
    viaja = {bloco["chave"] for bloco in montar_blocos(manifestacao) if bloco["chave"] != CHAVE_NOTA}
    if identificacao_do_caso(manifestacao):
        viaja.add("identificacao")
    if paciente_do_caso(manifestacao):
        viaja.add("paciente")
    return viaja


def _caso_completo(sigilo_reforcado: bool, anonimo: bool) -> dict:
    """Tudo preenchido: o que não viaja fica de fora pela regra, e não por
    faltar o dado."""
    return {
        "sigilo_reforcado": sigilo_reforcado,
        "anonimo": anonimo,
        "resumo": "Espera de duas horas na recepção.",
        "relato_integral": "Cheguei às 8h e só fui atendida às 10h30.",
        "extrato_para_o_setor": "Apurar a demora da recepção no turno da manhã.",
        "manifestante_nome": "Joana da Silva",
        "paciente_nome": "Maria da Silva",
        "paciente_referencia": "Prontuário 123",
    }


def test_o_contrato_cobre_as_quatro_combinacoes_e_tres_variantes():
    """Âncora: um contrato que sumisse ou encolhesse deixaria o teste abaixo
    verde sobre nada."""
    contrato = _contrato()
    assert set(contrato["variantes"]) == {"comum", "anonimo", "sigilo"}
    combinacoes = {(caso["sigilo_reforcado"], caso["anonimo"]) for caso in contrato["casos"]}
    assert combinacoes == {(False, False), (False, True), (True, False), (True, True)}


@pytest.mark.parametrize(
    "combinacao",
    [(False, False), (False, True), (True, False), (True, True)],
    ids=["comum", "anonimo", "sigilo", "sigilo_e_anonimo"],
)
def test_cada_variante_do_contrato_diz_o_que_a_regra_manda_a_area(combinacao):
    sigilo_reforcado, anonimo = combinacao
    contrato = _contrato()
    (caso,) = [c for c in contrato["casos"] if (c["sigilo_reforcado"], c["anonimo"]) == combinacao]

    esperado = set(contrato["variantes"][caso["variante"]])

    assert _o_que_viaja_alem_do_extrato(_caso_completo(sigilo_reforcado, anonimo)) == esperado
