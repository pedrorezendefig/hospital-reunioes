"""O roteiro dos prints da página de Reuniões e Pendências (issue #1721).

O roteiro refaz todas as imagens da página, a partir de um seed fictício numa
faixa de ids só dele, e recusa o print que mostre dado de fora do seed. Estes
testes rodam sem navegador e sem banco: leem o Markdown da página de verdade e
chamam as guardas do roteiro direto.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import prints_manual_reunioes as roteiro  # noqa: E402

PAGINA = (
    Path(__file__).resolve().parent.parent
    / "hospital-reunioes/frontend/public/manual/reunioes-e-pendencias/pagina.md"
)


def imagens_da_pagina() -> list[str]:
    return re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", PAGINA.read_text(encoding="utf-8"))


def test_o_roteiro_refaz_todas_as_imagens_da_pagina():
    citadas = imagens_da_pagina()
    assert len(citadas) >= 6
    assert sorted(f"{nome}.png" for nome in roteiro.PRINTS) == sorted(citadas)


def test_o_roteiro_grava_os_prints_ao_lado_do_markdown():
    assert roteiro.PASTA_DA_PAGINA == PAGINA.parent


def test_o_seed_so_tem_gente_de_exemplo_numa_faixa_propria():
    ids = [pid for pid, *_ in roteiro.PESSOAS]
    emails = [roteiro.email_de(nome) for _, nome, *_ in roteiro.PESSOAS]

    assert all(e.endswith("@exemplo.local") for e in emails)
    assert all(re.fullmatch(r"P1721\d", pid) for pid in ids)
    # As faixas dos outros roteiros de print: P900 a P989 (inclusive a P980 da casca).
    assert not any(re.fullmatch(r"P9[0-8]\d", pid) for pid in ids)
    assert len(set(ids)) == len(ids)


def test_print_com_nome_de_fora_do_seed_nao_sai():
    tela = "Pendências\nCalibrar as bombas\nFábio Guimarães\nMarcos Teixeira Lopes\n"

    with pytest.raises(roteiro.DadoRealNoPrint, match="Marcos Teixeira Lopes"):
        roteiro.exigir_so_dado_de_exemplo(tela, ["Marcos Teixeira Lopes", "Ana"], "pendencias")


def test_print_com_nome_de_fora_em_caixa_alta_nao_sai():
    # O CSS põe botão, cabeçalho e etiqueta em caixa alta, e o innerText
    # devolve o texto já transformado.
    tela = "PENDÊNCIAS\nMARCOS TEIXEIRA LOPES\nCOMISSÃO DE ÉTICA MÉDICA\n"

    with pytest.raises(roteiro.DadoRealNoPrint, match="Marcos Teixeira Lopes"):
        roteiro.exigir_so_dado_de_exemplo(tela, ["Marcos Teixeira Lopes"], "pendencias")
    with pytest.raises(roteiro.DadoRealNoPrint, match="Comissão de Ética Médica"):
        roteiro.exigir_so_dado_de_exemplo(tela, ["Comissão de Ética Médica"], "pendencias")


def test_a_lista_de_fora_do_seed_le_o_banco_alem_do_teto_do_postgrest(monkeypatch):
    # O PostgREST local corta cada resposta em max_rows = 1000.
    teto = 1000
    participantes = [{"id": f"X{i}", "nome_completo": f"Pessoa Real {i}"} for i in range(2500)]
    reunioes = [{"id_reuniao": f"R{i}", "titulo": f"Reunião Real {i}"} for i in range(1200)]

    def rest_com_teto(caminho, metodo="GET", corpo=None, prefer=None):
        tabela = participantes if caminho.startswith("participantes") else reunioes
        params = dict(p.split("=", 1) for p in caminho.split("?", 1)[1].split("&"))
        inicio = int(params.get("offset", 0))
        limite = min(int(params.get("limit", teto)), teto)
        return tabela[inicio : inicio + limite]

    monkeypatch.setattr(roteiro, "_rest", rest_com_teto)

    de_fora = roteiro.nomes_de_fora_do_seed()

    assert "Pessoa Real 2499" in de_fora
    assert "Reunião Real 1199" in de_fora
    assert len(de_fora) == 3700


def test_print_so_com_dado_de_exemplo_sai():
    tela = "Pendências\nCalibrar as bombas\nFábio Guimarães\nAnalisar o estoque\n"

    roteiro.exigir_so_dado_de_exemplo(tela, ["Marcos Teixeira Lopes", "Ana"], "pendencias")


def test_o_seed_recusa_banco_que_nao_e_o_local(tmp_path):
    env = tmp_path / ".env"
    env.write_text("SUPABASE_URL=https://supabase.hospitalsaomatheus.cloud\nSUPABASE_SERVICE_KEY=x\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="não é o Supabase local"):
        roteiro.credenciais_locais(env)
