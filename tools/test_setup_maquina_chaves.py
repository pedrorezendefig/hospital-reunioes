"""As chaves da Central de Comando local têm origem escrita no /setup-maquina.

Quem roda `/setup-maquina --env` para ver a Central na própria máquina precisa
ouvir "peça ao Pedro" para as chaves do GA4 e do Instagram, com o item do
1Password onde elas vivem, e saber que a credencial do Google entra como JSON
inteiro, não como o caminho de arquivo que o app antigo usa (issue #860).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
SKILL_DIR = RAIZ / ".claude" / "skills" / "setup-maquina"
CHAVES = (SKILL_DIR / "references" / "chaves.md").read_text(encoding="utf-8")
SKILL = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
ENV_EXEMPLO = (RAIZ / "hospital-reunioes" / ".env.example").read_text(encoding="utf-8")

# Os nomes que o backend lê para ligar a Central (ADR 0058).
CHAVES_DA_CENTRAL = [
    "GA4_PROPERTY_ID",
    "GOOGLE_APPLICATION_CREDENTIALS_JSON",
    "INSTAGRAM_ACCESS_TOKEN",
    "INSTAGRAM_BUSINESS_ACCOUNT_ID",
]


def secao(texto: str, titulo: str) -> str:
    """O corpo de uma seção `## ` do markdown, até a próxima."""
    achado = re.search(
        rf"^## {re.escape(titulo)}[^\n]*\n(.*?)(?=^## |\Z)", texto, re.S | re.M
    )
    assert achado, f"sumiu a seção que começa com '## {titulo}'"
    return achado.group(1)


NIVEL_3 = secao(CHAVES, "hospital-reunioes/.env (nível 3")


def linha_do_nivel_3(chave: str) -> list[str]:
    """As colunas (chave, tipo, origem) da linha da tabela do nível 3."""
    linhas = [
        li
        for li in NIVEL_3.splitlines()
        if li.startswith("|") and f"`{chave}`" in li.split("|")[1]
    ]
    assert len(linhas) == 1, f"esperava uma linha de {chave} no nível 3: {linhas}"
    return [c.strip() for c in linhas[0].strip().strip("|").split("|")]


@pytest.mark.parametrize("chave", CHAVES_DA_CENTRAL)
def test_a_chave_pedida_e_a_que_o_app_le(chave):
    """Nome na skill que o `.env.example` não tem é pedido que não liga nada."""
    assert re.search(rf"^{chave}=", ENV_EXEMPLO, re.M)


@pytest.mark.parametrize("chave", CHAVES_DA_CENTRAL)
def test_o_nivel_3_diz_tipo_origem_e_o_pedido_ao_pedro(chave):
    _, tipo, origem = linha_do_nivel_3(chave)

    assert tipo == "compartilhada"
    assert "1Password, VITTA TECH" in origem
    assert "(criar)" in origem, "o item ainda não existe no cofre"
    assert re.search(
        rf"peça ao Pedro: `{chave}`, serve para \w", origem, re.I
    ), "falta a frase de pedido"


def test_a_credencial_do_google_e_o_json_inteiro_nao_o_caminho():
    """No app antigo o nome é outro e guarda um caminho: copiar falha calado."""
    antigo = re.search(r"`GOOGLE_APPLICATION_CREDENTIALS`[^\n]*", NIVEL_3)
    assert antigo, "o nível 3 não cita o nome antigo, sem o _JSON"

    nota = antigo.group(0)
    assert "caminho" in nota
    assert "JSON inteiro" in nota
    assert "`GOOGLE_APPLICATION_CREDENTIALS_JSON`" in nota


def item_do_env() -> str:
    """O passo `--env` da lista "O que fazer com o resultado" do SKILL.md."""
    achado = re.search(r"^4\. Com `--env`.*?(?=^\d+\. )", SKILL, re.S | re.M)
    assert achado, "sumiu o passo `--env` do SKILL.md"
    return achado.group(0)


def test_o_env_manda_pedir_ao_pedro_as_chaves_da_central():
    item = item_do_env()

    assert "Central de Comando" in item
    for chave in CHAVES_DA_CENTRAL:
        assert f"`{chave}`" in item, f"o --env não cita {chave}"
    assert re.search(r"peça ao Pedro", item, re.I)
    assert "references/chaves.md" in item
