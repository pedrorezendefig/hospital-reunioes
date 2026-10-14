"""Testes da lista de cacoetes regexáveis (tools/tells_texto.py, ADR 0071).

Os casos vêm do `tools/tells_casos.json`, o mesmo arquivo que o teste da regra
do ESLint do front lê: se um lint muda e o outro não, um dos dois fica vermelho.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

import tells_texto  # noqa: E402

CASOS = json.loads(
    (Path(__file__).parent / "tells_casos.json").read_text(encoding="utf-8")
)["casos"]


def nomes(texto: str) -> list[str]:
    return sorted({o.cacoete for o in tells_texto.achar_tells(texto)})


@pytest.mark.parametrize("caso", CASOS, ids=[c["texto"][:50] for c in CASOS])
def test_cacoetes_do_caso_compartilhado(caso):
    assert nomes(caso["texto"]) == sorted(caso["tells"])


def test_o_json_tem_positivo_de_cada_cacoete_e_negativos():
    """Cacoete sem caso positivo seria um padrão que nenhum teste vigia."""
    positivos = {t for c in CASOS for t in c["tells"]}
    assert positivos == {c.nome for c in tells_texto.CACOETES}
    assert any(c["tells"] == [] for c in CASOS)


def test_ocorrencia_traz_nome_trecho_e_posicao():
    texto = "Clique em Salvar. A ata não é um resumo, é a memória."
    (achado,) = tells_texto.achar_tells(texto)
    assert achado.cacoete == "nao-e-x-e-y"
    assert achado.trecho == "não é um resumo, é"
    assert achado.posicao == texto.index("não é")


def test_fecho_repetido_aponta_o_segundo_fecho():
    texto = next(c["texto"] for c in CASOS if "Simples assim" in c["texto"])
    (achado,) = tells_texto.achar_tells(texto)
    assert achado.trecho == "Simples assim."
    assert achado.posicao == texto.rindex("Simples assim.")


@pytest.mark.parametrize("nome", [c.nome for c in tells_texto.CACOETES])
def test_tirar_um_cacoete_da_lista_faz_um_caso_falhar(nome, monkeypatch):
    """Prova por mutação: cada padrão da lista é vigiado por algum caso."""
    sem_ele = [c for c in tells_texto.CACOETES if c.nome != nome]
    monkeypatch.setattr(tells_texto, "CACOETES", sem_ele)
    falhas = [c for c in CASOS if nomes(c["texto"]) != sorted(c["tells"])]
    assert falhas, f"tirar '{nome}' não derrubou nenhum caso"
