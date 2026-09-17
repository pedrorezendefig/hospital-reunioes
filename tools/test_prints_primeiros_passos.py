"""Testes das guardas do Roteiro de prints de Primeiros passos.

O roteiro do módulo Primeiros passos (`docs/manual/prints/primeiros-passos.py`)
não só lê tela: o `--semear` cria o login e o cadastro da pessoa de exemplo que
entra na plataforma. O que separa isso de um
banco que não é o de desenvolvimento são as três linhas de
`_credenciais_locais`, que leem o `.env` e recusam toda URL que não seja
`127.0.0.1` ou `localhost`. É essa recusa que estes testes provam, com o
`.env` apontado para um arquivo temporário.

A segunda guarda é a do endereço local: o manual é um site público, e o print
que mostra `localhost:3000` publica uma instrução que não abre para ninguém.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

MODULO = "primeiros-passos"
ROTEIRO = (
    Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "primeiros-passos.py"
)


def carregar_roteiro():
    """Importa o roteiro pelo caminho.

    Ele vive em `docs/manual/prints/`, fora de qualquer pacote, e não importa o
    Playwright no topo justamente para caber aqui.
    """
    spec = importlib.util.spec_from_file_location("roteiro_prints_primeiros_passos", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def escrever_env(tmp_path: Path, url: str) -> Path:
    env = tmp_path / ".env"
    linhas = ["# comentário que o leitor ignora", "SUPABASE_SERVICE_KEY=chave-de-teste"]
    if url is not None:
        linhas.append(f"SUPABASE_URL={url}")
    env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return env


# Endereços de mentira de propósito: o repositório é público, e o que o teste
# precisa provar é que a guarda recusa qualquer hostname que não seja o da
# máquina, não qual é o endereço de verdade. O TLD `.invalid` é reservado pela
# RFC 2606 para exemplo e nunca resolve.
@pytest.mark.parametrize(
    "url",
    [
        "https://db.exemplo.invalid",
        "https://projeto.exemplo.invalid",
        "http://192.168.0.10:54321",
    ],
)
def test_recusa_banco_que_nao_e_o_local(tmp_path, monkeypatch, url):
    """Qualquer endereço fora da máquina para o roteiro antes de gravar nada."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, url))

    with pytest.raises(SystemExit) as erro:
        roteiro._credenciais_locais()

    # A mensagem inteira, não um pedaço dela: asserir só "recusado" sobrevive a
    # trocar a frase por outra que não diz qual endereço foi barrado.
    assert str(erro.value) == f"recusado: '{url}' não é o Supabase local."


def test_recusa_env_sem_supabase_url(tmp_path, monkeypatch):
    """Falha fechada: `.env` sem a URL não vira permissão para gravar."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, None))

    with pytest.raises(SystemExit) as erro:
        roteiro._credenciais_locais()

    assert str(erro.value) == "recusado: '' não é o Supabase local."


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:54351", "http://localhost:54321", "http://127.0.0.1:8000"]
)
def test_aceita_o_banco_local_e_devolve_as_credenciais(tmp_path, monkeypatch, url):
    """O caminho bom continua passando, com URL e chave lidas do arquivo."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "ENV_LOCAL", escrever_env(tmp_path, url))

    assert roteiro._credenciais_locais() == (url, "chave-de-teste")


def test_semear_para_no_primeiro_passo_quando_o_banco_nao_e_local(tmp_path, monkeypatch):
    """A guarda roda antes de qualquer escrita: `_rest` nem chega a ser chamado."""
    roteiro = carregar_roteiro()
    monkeypatch.setattr(
        roteiro, "ENV_LOCAL", escrever_env(tmp_path, "https://db.exemplo.invalid")
    )

    def nao_deve_gravar(*args, **kwargs):
        raise AssertionError("o roteiro gravou no banco com a guarda recusando")

    monkeypatch.setattr(roteiro, "_rest", nao_deve_gravar)
    monkeypatch.setattr(roteiro, "_login_de_exemplo", nao_deve_gravar)

    with pytest.raises(SystemExit):
        roteiro.semear()


# --------------------------------------------------------------------------
# A guarda de endereço local e o caminho por onde todo print passa
# --------------------------------------------------------------------------
#
# Prova por mutação, com o mutante no caminho da captura e outro no detector:
#
# 1. `capturar` sem a chamada de `exigir_endereco_de_producao`:
#    `test_nao_grava_print_com_endereco_local` falha, porque o dublê registra o
#    screenshot que não devia ter acontecido.
# 2. `ENDERECOS_LOCAIS` sem `\b127\.0\.0\.1\b`: `test_recusa_cada_endereco_local`
#    falha só no caso do IP, que é o ponto do mutante.
# 3. No detector: `test_nao_grava_print_com_endereco_local` sem a asserção de
#    `dublê.chamadas`, guardando só o `pytest.raises`, continua verde com o
#    mutante 1, e é por isso que a asserção do comportamento está lá.


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

    def wait_for_timeout(self, _ms: int) -> None:
        pass


class AlvoDublê:
    """Um quadro da tela, com registro da folga aplicada e da captura."""

    def __init__(self) -> None:
        self.folga = None
        self.chamadas: list[dict] = []

    def evaluate(self, _script, valor=None):
        self.folga = valor

    def screenshot(self, **kwargs) -> None:
        self.chamadas.append({**kwargs, "folga_no_momento": self.folga})


def test_grava_print_quando_o_texto_esta_limpo(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê("Bem-vindo de volta · Acesse a plataforma")
    alvo = tmp_path / "tela-de-entrada.png"

    roteiro.capturar(pagina, alvo, "tela-de-entrada", clip={"x": 0})

    assert len(pagina.chamadas) == 1
    assert pagina.chamadas[0]["path"] == str(alvo)
    assert pagina.chamadas[0]["clip"] == {"x": 0}


def test_nao_grava_print_com_endereco_local(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê("Abra http://localhost:3000/login para entrar")

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.capturar(pagina, tmp_path / "tela-de-entrada.png", "tela-de-entrada")

    # O que importa não é a exceção, é o print não ter sido gravado.
    assert pagina.chamadas == []
    assert not (tmp_path / "tela-de-entrada.png").exists()


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
    ],
)
def test_recusa_cada_endereco_local(endereco):
    """A guarda responde sobre endereço local, não sobre três strings.

    Cada caso aqui passa batido quando a trava é uma lista de substrings em
    caixa baixa: o IPv6, a forma curta do loopback, as três faixas privadas e a
    mesma palavra em caixa alta.
    """
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint) as erro:
        roteiro.exigir_endereco_de_producao(
            f"o endereço da plataforma é http://{endereco}:3000", "qualquer-print"
        )

    # A mensagem diz o que fazer, não só o que houve.
    assert roteiro.BASE_DO_APP_EM_PRODUCAO in str(erro.value)


@pytest.mark.parametrize(
    "endereco",
    ["hospital.local:3000", "app.internal/pops", "manual.test/"],
)
def test_recusa_rede_interna_dentro_de_uma_url(endereco):
    """Rede interna com forma de endereço continua barrada."""
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.exigir_endereco_de_producao(f"abra {endereco} no navegador", "print")


@pytest.mark.parametrize(
    "texto",
    [
        # O caso que a campanha de prints trouxe: todo dado de exemplo do
        # manual é `@exemplo.local`, e travar nele pararia a captura certa.
        "paula.nogueira@exemplo.local",
        "Paula Nogueira · paula.nogueira@exemplo.local · Qualidade",
        "A resposta passou do limite de 10.000 caracteres.",
        "O prazo novo nunca passa de 30 dias úteis contados da entrada.",
        "https://app.hospitalsaomatheus.cloud/login",
    ],
)
def test_deixa_passar_o_que_so_parece_endereco(texto):
    """Falso positivo também quebra o roteiro, e de um jeito pior: a captura
    certa para de acontecer e ninguém entende por quê."""
    roteiro = carregar_roteiro()

    roteiro.exigir_endereco_de_producao(texto, "qualquer-print")


def test_a_base_de_producao_e_a_do_contrato_de_deploy():
    """A base não é digitada de memória: é a do `project.json`."""
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
    os de hoje.
    """
    fonte = ROTEIRO.read_text(encoding="utf-8")
    corpo = fonte.split("def capturar(", 1)[1].split("\ndef ", 1)[0]
    assert "page.screenshot(" in corpo, "a captura deixou de morar em `capturar`"
    assert "alvo.screenshot(" in corpo, "a captura de quadro saiu de `capturar`"
    assert fonte.count(".screenshot(") == 2, (
        "alguém chamou `screenshot` fora de `capturar`, e esse print não passa "
        "pela guarda de endereço local"
    )


def test_a_folga_do_quadro_e_aplicada_antes_da_captura(tmp_path):
    """O balão sai para fora do elemento, e a folga é o que o mantém na imagem.

    Aplicar a folga DEPOIS do screenshot deixaria o teste do valor verde e o
    print cortado, por isso o dublê registra o que valia no momento da captura.
    """
    roteiro = carregar_roteiro()
    pagina = PaginaDublê("Configurações · Segurança")
    alvo = AlvoDublê()

    roteiro.capturar(pagina, tmp_path / "meu-perfil.png", "meu-perfil", alvo=alvo)

    assert alvo.chamadas[0]["folga_no_momento"] == roteiro.FOLGA_DO_BALAO
    assert pagina.chamadas == [], "o quadro foi pedido e a janela inteira foi gravada"


def test_o_balao_acompanha_o_elemento_que_ele_marca():
    """O balão nasce dentro do elemento, e não colado na janela.

    Preso à janela (`position: fixed`), ele sai no lugar certo na captura de
    tela cheia e longe do botão em toda captura de quadro mais alto que o
    navegador, que o Playwright remonta. É um defeito que só a olhada na imagem
    pega, e esta trava é o que impede a volta dele.
    """
    roteiro = carregar_roteiro()

    assert "position: 'absolute'" in roteiro.BALAO_JS
    assert "hospedeiro.appendChild(b)" in roteiro.BALAO_JS
    assert "fixed" not in roteiro.BALAO_JS


def test_toda_imagem_das_paginas_do_modulo_vem_do_roteiro():
    """Print do manual é tela capturada por este arquivo, nunca recorte à mão.

    A trava é sobre o que a página publica: uma imagem nova em `assets/` que o
    roteiro não sabe refazer envelhece na primeira mudança de tela e ninguém
    descobre.
    """
    import re

    roteiro = carregar_roteiro()
    paginas = Path(__file__).resolve().parents[1] / "docs" / "manual" / "src" / "content" / "docs" / MODULO
    usadas = set()
    for pagina in sorted(paginas.rglob("*.md")):
        for caminho in re.findall(rf"assets/{MODULO}/([\w-]+)\.png", pagina.read_text(encoding="utf-8")):
            usadas.add(caminho)

    assert usadas, "nenhuma página do módulo aponta para print nenhum"
    assert usadas <= set(roteiro.PRINTS), (
        f"imagens que o roteiro não refaz: {sorted(usadas - set(roteiro.PRINTS))}"
    )


def test_todo_print_do_roteiro_esta_versionado():
    """O roteiro e a pasta de imagens não se separam.

    Print renomeado no roteiro e não regerado deixa a página apontando para um
    arquivo que não existe mais, e o site publica a lacuna.
    """
    roteiro = carregar_roteiro()
    assets = Path(__file__).resolve().parents[1] / "docs" / "manual" / "src" / "assets" / MODULO
    faltando = [nome for nome in roteiro.PRINTS if not (assets / f"{nome}.png").exists()]

    assert faltando == [], f"o roteiro promete prints que não estão no git: {faltando}"
