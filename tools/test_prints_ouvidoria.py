"""Testes das guardas do Roteiro de prints da Ouvidoria.

O roteiro (`docs/manual/prints/ouvidoria.py`) abre o app local, semeia
manifestações de exemplo e captura as telas que o Manual publica. Três coisas
dele podem virar problema num repositório público, e é sobre elas que estes
testes falam:

1. **Endereço local no print.** A guarda que já existia responde sobre
   endereço de máquina. O domínio das pessoas de exemplo (`exemplo.local`)
   passou a aparecer em toda tela que lista gente, e a guarda precisa deixá-lo
   passar sem deixar passar o `macbook.local` de quem capturou.
2. **A captura de um elemento.** `capturar` cobria `page.screenshot`. O recorte
   de um modal usa `elemento.screenshot`, que é outra porta: ela também tem
   que passar pela guarda.
3. **O banco compartilhado.** O roteiro repõe o estado das manifestações de
   exemplo antes de capturar. Um `PATCH` sem a marca do roteiro mexeria no
   trabalho de outra sessão.
"""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path

import pytest

ROTEIRO = (
    Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "ouvidoria.py"
)


def carregar_roteiro():
    spec = importlib.util.spec_from_file_location("roteiro_ouvidoria", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


# --------------------------------------------------------------------------
# 1. O domínio de exemplo passa; a máquina de quem capturou, não
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "marta.nogueira@exemplo.local",
        "Contato: iris.camargo@exemplo.local",
        "claudia.bastos@exemplo.local entrou na Ouvidoria",
    ],
)
def test_o_email_das_pessoas_de_exemplo_passa(texto):
    """Sem esta abertura, a guarda proibiria o dado de exemplo do manual.

    Toda tela do app que lista gente mostra o email, e o email de quem não
    existe termina em `exemplo.local`. Uma guarda que casasse `.local` inteiro
    travaria justamente o print que o manual precisa publicar.
    """
    roteiro = carregar_roteiro()

    roteiro.exigir_endereco_de_producao(texto, "print-qualquer")


@pytest.mark.parametrize(
    "endereco",
    ["macbook.local", "hospital.local", "MacBook-de-Pedro.local", "nas.local"],
)
def test_o_nome_de_maquina_continua_barrado(endereco):
    """A abertura é do domínio de exemplo, e não de `.local` inteiro.

    Este é o mutante que importa: trocar o padrão por um `.local` sem a
    exceção, ou apagar o padrão de vez, publicaria o nome da máquina de quem
    capturou num cartaz que vai para a parede do hospital.
    """
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.exigir_endereco_de_producao(
            f"Abra http://{endereco}:3000/manifestacao", "cartaz"
        )


# --------------------------------------------------------------------------
# 2. As duas portas de captura passam pela guarda
# --------------------------------------------------------------------------


class _ElementoFalso:
    def __init__(self, registro):
        self.registro = registro

    def screenshot(self, path=None, **kwargs):
        self.registro.append(str(path))


class _PaginaFalsa:
    def __init__(self, texto: str):
        self.texto = texto

    def inner_text(self, seletor):
        return self.texto

    def screenshot(self, path=None, **kwargs):
        raise AssertionError("a página não deveria ser fotografada aqui")


def test_o_recorte_de_um_elemento_tambem_passa_pela_guarda(tmp_path):
    """`capturar_elemento` é a segunda porta, e ela fecha igual à primeira."""
    roteiro = carregar_roteiro()
    gravados: list[str] = []
    pagina = _PaginaFalsa("Abra http://macbook.local:3000 para responder")

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.capturar_elemento(
            pagina, _ElementoFalso(gravados), tmp_path / "x.png", "modal"
        )

    assert gravados == [], "o recorte do modal foi gravado com endereço local"


def test_o_recorte_limpo_e_gravado(tmp_path):
    """O caminho bom continua gravando, senão a guarda seria só um bloqueio."""
    roteiro = carregar_roteiro()
    gravados: list[str] = []

    roteiro.capturar_elemento(
        _PaginaFalsa("Recepção, prazo de resposta em 2 dias úteis"),
        _ElementoFalso(gravados),
        tmp_path / "modal.png",
        "modal",
    )

    assert gravados == [str(tmp_path / "modal.png")]


def test_ninguem_fotografa_por_fora_das_duas_portas():
    """Print novo nasce protegido, inclusive o recorte de um elemento.

    A contagem é o que faz a trava valer para o print que ainda não existe: uma
    captura escrita direto na função do print não passaria por guarda nenhuma.
    """
    fonte = ROTEIRO.read_text(encoding="utf-8")

    assert fonte.count("page.screenshot(") == 1, (
        "alguém chamou `page.screenshot` fora de `capturar`"
    )
    assert fonte.count("elemento.screenshot(") == 1, (
        "alguém capturou um elemento fora de `capturar_elemento`"
    )
    assert fonte.count(".screenshot(path=") == 2, (
        "apareceu uma terceira captura, e ela não passa por guarda nenhuma"
    )
    corpo = fonte.split("def capturar_elemento(", 1)[1].split("\ndef ", 1)[0]
    assert "exigir_endereco_de_producao(" in corpo, (
        "`capturar_elemento` deixou de conferir o texto da tela"
    )


# --------------------------------------------------------------------------
# 3. O banco compartilhado
# --------------------------------------------------------------------------


def test_restaurar_so_toca_no_que_o_roteiro_semeou(monkeypatch):
    """O banco local é compartilhado com as outras sessões.

    Repor o estado é o que deixa o roteiro rodar duas vezes seguidas, e o
    filtro pela marca é o que impede que ele reponha o estado de uma
    manifestação que outra pessoa estava usando. Um `PATCH` sem a marca
    passaria por cima de todas.
    """
    roteiro = carregar_roteiro()
    caminhos: list[str] = []
    monkeypatch.setattr(
        roteiro, "_credenciais_locais", lambda: ("http://127.0.0.1:54351", "chave")
    )
    monkeypatch.setattr(
        roteiro,
        "_rest",
        lambda url, chave, caminho, metodo="GET", corpo=None, prefer=None: caminhos.append(
            (caminho, metodo)
        ),
    )

    roteiro.restaurar_os_casos()

    assert caminhos, "a reposição não tocou em manifestação nenhuma"
    for caminho, metodo in caminhos:
        assert metodo == "PATCH"
        assert f"conversa_id=eq.{roteiro.MARCA_DE_EXEMPLO}" in caminho, (
            f"'{caminho}' mexe em manifestação que não é deste roteiro"
        )
        assert "resumo=eq." in caminho, (
            f"'{caminho}' repõe o estado de todas as manifestações da marca de "
            "uma vez, e não o da linha que ele conhece"
        )


def test_todo_caso_de_exemplo_tem_gente_inventada():
    """Nenhum relato de gente de verdade entra no print.

    O contato de quem manifesta é o dado mais sensível do módulo, e o print da
    página do caso mostra ele por escrito. O domínio `exemplo.local` não existe
    e não é de ninguém.
    """
    roteiro = carregar_roteiro()

    assert roteiro.CASOS, "sem manifestação de exemplo não há print publicável"
    for apelido, receita in roteiro.CASOS.items():
        contato = receita.get("manifestante_contato")
        assert contato, f"{apelido} não diz quem manifestou"
        assert contato.endswith("@exemplo.local"), (
            f"{apelido} tem contato '{contato}', que não é endereço de exemplo"
        )


def test_o_banco_guarda_o_hash_do_link_do_portal():
    """O link do portal do setor é uma porta de escrita sem login.

    O app guarda o sha256 do token, e não o token
    (`app/services/ouvidoria_setor_tokens.py`). O roteiro emite o dele pela
    mesma conta: gravar o valor em claro deixaria a coluna com um segredo
    utilizável para quem lesse o banco.
    """
    roteiro = carregar_roteiro()
    fonte = ROTEIRO.read_text(encoding="utf-8")

    esperado = hashlib.sha256(roteiro.TOKEN_DO_PORTAL.encode()).hexdigest()
    assert len(esperado) == 64
    assert "hashlib.sha256(TOKEN_DO_PORTAL.encode()).hexdigest()" in fonte
    assert '"token_hash": TOKEN_DO_PORTAL' not in fonte


def test_o_roteiro_so_semeia_contra_o_banco_local(tmp_path, monkeypatch):
    """A semeadura escreve; contra produção ela não pode nem começar."""
    roteiro = carregar_roteiro()
    env = tmp_path / ".env"
    env.write_text(
        "SUPABASE_URL=https://supabase.hospitalsaomatheus.cloud\n"
        "SUPABASE_SERVICE_ROLE_KEY=chave\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(roteiro, "ENV_LOCAL", env)

    with pytest.raises(SystemExit):
        roteiro._credenciais_locais()
