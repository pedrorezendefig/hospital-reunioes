"""A guarda do Roteiro de prints: print publicado não mostra endereço local.

A auditoria do PRD #731 achou dois prints no ar com `localhost:3000`, um deles
no cartaz que vai impresso para a parede do hospital. O conserto foi montar o
cartaz e o e-mail com a base de produção; esta é a trava que impede a volta.

O teste mede **comportamento**, não a existência do código: ele passa um dublê
de página pela função que todo print atravessa e confere que a imagem não é
gravada quando o texto visível traz endereço local.

Prova por mutação, com o mutante no caminho da captura e outro no detector:

1. `capturar` sem a chamada de `exigir_endereco_de_producao` (a guarda
   desligada): `test_nao_grava_print_com_endereco_local` falha, porque o dublê
   registra o screenshot que não devia ter acontecido.
2. `ENDERECOS_LOCAIS` sem `"127.0.0.1"`: `test_recusa_cada_endereco_local`
   falha só no caso do IP, que é o ponto do mutante.
3. No detector: `test_nao_grava_print_com_endereco_local` sem a asserção de
   `dublê.chamadas`, ou seja, guardando só o `pytest.raises`, continua verde com
   o mutante 1, e é por isso que a asserção do comportamento está lá.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROTEIRO = Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "ouvidoria.py"


def carregar_roteiro():
    """O roteiro como módulo, sem depender do Playwright estar instalado.

    O `sync_playwright` é importado dentro do `main()` justamente para isto: a
    trava roda no CI, onde o navegador não existe.
    """
    spec = importlib.util.spec_from_file_location("prints_ouvidoria", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class PaginaDublê:
    """O mínimo da página que `capturar` usa, com registro do que foi chamado."""

    def __init__(self, texto_visivel: str) -> None:
        self.texto_visivel = texto_visivel
        self.chamadas: list[dict] = []

    def inner_text(self, seletor: str) -> str:
        assert seletor == "body"
        return self.texto_visivel

    def screenshot(self, **kwargs) -> None:
        self.chamadas.append(kwargs)


def test_grava_print_quando_o_texto_esta_limpo(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê(
        "Se a câmera não ler, digite este endereço no navegador: "
        "app.hospitalsaomatheus.cloud/ouvidoria/qr?p=QWQK8Q"
    )
    alvo = tmp_path / "cartaz-pa.png"

    roteiro.capturar(pagina, alvo, "cartaz-pa", full_page=True)

    assert len(pagina.chamadas) == 1
    assert pagina.chamadas[0]["path"] == str(alvo)
    assert pagina.chamadas[0]["full_page"] is True


def test_nao_grava_print_com_endereco_local(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê(
        "Se a câmera não ler, digite este endereço no navegador: "
        "localhost:3000/ouvidoria/qr?p=QWQK8Q"
    )

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.capturar(pagina, tmp_path / "cartaz-pa.png", "cartaz-pa")

    # O que importa não é a exceção, é o print não ter sido gravado.
    assert pagina.chamadas == []
    assert not (tmp_path / "cartaz-pa.png").exists()


@pytest.mark.parametrize(
    "endereco",
    [
        "localhost",
        "LOCALHOST",
        "127.0.0.1",
        "127.1",
        "0.0.0.0",
        "[::1]",
        "192.168.0.14",
        "10.1.2.3",
        "172.20.10.2",
        "hospital.local",
        "app.internal",
        "app.test",
    ],
)
def test_recusa_cada_endereco_local(endereco):
    """A guarda responde sobre endereço local, não sobre três strings.

    Cada caso aqui passava batido quando a trava era uma lista de substrings em
    caixa baixa: o IPv6, a forma curta do loopback, as três faixas privadas, os
    domínios de rede interna e a mesma palavra em caixa alta.
    """
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint) as erro:
        roteiro.exigir_endereco_de_producao(
            f"procure a Ouvidoria por http://{endereco}:3000/manifestacao", "email"
        )

    # A mensagem diz o que fazer, não só o que houve.
    assert roteiro.BASE_DO_APP_EM_PRODUCAO in str(erro.value)


@pytest.mark.parametrize(
    "texto",
    [
        "A resposta passou do limite de 10.000 caracteres. Resuma o que foi feito.",
        "Consulta particular por R$ 10.000,00 no plano da casa.",
        "app.hospitalsaomatheus.cloud/ouvidoria/qr?p=QWQK8Q",
        "O prazo novo nunca passa de 30 dias úteis contados da entrada.",
    ],
)
def test_deixa_passar_o_que_so_parece_endereco(texto):
    """Falso positivo também quebra o roteiro, e de um jeito pior: a captura
    certa para de acontecer e ninguém entende por quê. Faixa privada só casa
    com os quatro octetos, e é isso que deixa "10.000 caracteres" em paz."""
    roteiro = carregar_roteiro()

    roteiro.exigir_endereco_de_producao(texto, "qualquer-print")


def test_a_base_de_producao_e_a_do_contrato_de_deploy():
    """A base não é digitada de memória: é a do `project.json`.

    Sem esta asserção, trocar a constante por um endereço parecido (o do manual,
    por exemplo, que é outro site) passaria por todos os outros testes.
    """
    import json

    roteiro = carregar_roteiro()
    contrato = json.loads(
        (Path(__file__).resolve().parents[1] / "docs" / "spec" / "deploy" / "project.json").read_text(
            encoding="utf-8"
        )
    )
    fqdns = [
        servico.get("deploy", {}).get("fqdn")
        for servico in contrato.get("services", [])
        if isinstance(servico, dict)
    ]
    assert roteiro.BASE_DO_APP_EM_PRODUCAO in [f for f in fqdns if f]


def test_todo_print_do_roteiro_passa_pela_guarda():
    """Print novo nasce protegido: ninguém chama `screenshot` por fora.

    É o que faz a trava valer para o print que ainda não existe, e não só para
    os três de hoje.
    """
    fonte = ROTEIRO.read_text(encoding="utf-8")
    corpo = fonte.split("def capturar(", 1)[1].split("\ndef ", 1)[0]
    assert "page.screenshot(" in corpo, "a captura deixou de morar em `capturar`"
    assert fonte.count("page.screenshot(") == 1, (
        "alguém chamou `page.screenshot` fora de `capturar`, e esse print não "
        "passa pela guarda de endereço local"
    )
