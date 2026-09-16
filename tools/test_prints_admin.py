"""Testes das duas guardas do Roteiro de prints do Admin.

O roteiro do módulo Admin (`docs/manual/prints/admin.py`) tem dois riscos que
nenhum outro módulo tem juntos:

1. O `--semear` grava: cria login no Supabase Auth e insere pessoas. O que
   separa isso de um banco que não é o de desenvolvimento são as três linhas
   de `_credenciais_locais`, que leem o `.env` e recusam toda URL que não seja
   `127.0.0.1` ou `localhost`.
2. A tela que ele fotografa é a lista de nome e email de gente real, e o
   repositório é público. O que separa o print de um vazamento é o filtro que
   o roteiro digita na busca antes de capturar.

É isso que estes testes provam.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROTEIRO = (
    Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "admin.py"
)


def carregar_roteiro():
    """Importa o roteiro pelo caminho.

    Ele vive em `docs/manual/prints/`, fora de qualquer pacote, e não importa o
    Playwright no topo justamente para caber aqui.
    """
    spec = importlib.util.spec_from_file_location("roteiro_prints_admin", ROTEIRO)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


def escrever_env(tmp_path: Path, url: str | None) -> Path:
    env = tmp_path / ".env"
    linhas = ["# comentário que o leitor ignora", "SUPABASE_SERVICE_KEY=chave-de-teste"]
    if url is not None:
        linhas.append(f"SUPABASE_URL={url}")
    env.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return env


# Endereços de mentira de propósito: o TLD `.invalid` é reservado pela RFC 2606
# e nunca resolve. O que o teste prova é que a guarda recusa qualquer hostname
# que não seja o da máquina, não qual é o endereço de verdade.
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


def test_o_filtro_da_busca_e_o_termo_exato_que_so_casa_pessoa_de_exemplo():
    """O valor do filtro, inteiro, e não um pedaço dele.

    Este é o mutante que importa: com `FILTRO_DE_EXEMPLO = ""` a busca da tela
    devolve a lista inteira e o print sai com nome e email de gente do
    hospital. Um teste que só pergunte `FILTRO_DE_EXEMPLO in email`, ou que
    procure o nome da constante no código, passa verde nesse mutante, porque
    string vazia está contida em tudo e o nome continua escrito. Asserir o
    valor inteiro é o que mata `""`, `"a"` e qualquer outro termo frouxo de
    uma vez: trocar a peneira passa a exigir trocar esta linha, de propósito.
    """
    roteiro = carregar_roteiro()

    assert roteiro.FILTRO_DE_EXEMPLO == "exemplo"


@pytest.mark.parametrize("termo", ["", "   ", "a", "ex"])
def test_a_guarda_recusa_capturar_com_filtro_frouxo(monkeypatch, termo):
    """A defesa de execução, não só a de teste.

    O teste acima trava o valor de hoje; esta guarda é o que protege quem
    mexer no roteiro amanhã sem rodar a suíte. Ela roda antes de abrir a tela,
    porque o dano é um arquivo gravado em disco.
    """
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "FILTRO_DE_EXEMPLO", termo)

    with pytest.raises(SystemExit) as erro:
        roteiro._conferir_o_filtro()

    # A mensagem inteira, não um pedaço dela: asserir uma substring sobrevive a
    # trocar a frase por outra que não diga qual termo foi barrado.
    assert str(erro.value) == (
        f"recusado: o filtro da busca é '{termo}', com menos de "
        f"{roteiro.MINIMO_DO_FILTRO} letras. Termo curto casa gente de verdade, "
        "e o print da lista de Usuários sairia com nome e email reais."
    )


def test_a_guarda_deixa_passar_o_filtro_de_verdade():
    """O caminho bom continua passando, senão a guarda seria só um bloqueio."""
    roteiro = carregar_roteiro()

    roteiro._conferir_o_filtro()


# --------------------------------------------------------------------------
# A tela de mentira
#
# Ler o código-fonte da função prova que uma linha existe, não que ela roda, e
# foi exatamente por aí que a primeira versão destes testes passou verde sobre
# uma guarda desligada: asserir o NOME da constante não é asserir o USO dela.
# Esta tela falsa registra o que o roteiro faz com ela, na ordem, e as
# asserções passam a ser sobre comportamento.
# --------------------------------------------------------------------------


class _CampoFalso:
    """Um elemento da tela falsa: anota o que recebe e devolve outro igual."""

    def __init__(self, pagina: "_PaginaFalsa", quem: str):
        self.pagina = pagina
        self.quem = quem

    def wait_for(self, **kwargs):
        return self

    def fill(self, valor):
        self.pagina.passos.append(("digitou", self.quem, valor))

    def click(self, **kwargs):
        self.pagina.passos.append(("clicou", self.quem))

    def locator(self, seletor):
        return _CampoFalso(self.pagina, seletor)

    def screenshot(self, path=None, **kwargs):
        self.pagina.passos.append(("fotografou", str(path)))

    def scroll_into_view_if_needed(self):
        return self

    @property
    def first(self):
        return self

    @property
    def last(self):
        return self


class _PaginaFalsa:
    """A tela que o roteiro pensa estar dirigindo."""

    def __init__(self, url: str = ""):
        self.url = url
        self.passos: list[tuple] = []

    def goto(self, url, **kwargs):
        self.passos.append(("abriu", url))
        self.url = url

    def get_by_placeholder(self, texto):
        return _CampoFalso(self, texto)

    def get_by_role(self, papel, name=None, **kwargs):
        return _CampoFalso(self, f"{papel}:{name}")

    def get_by_text(self, texto, **kwargs):
        return _CampoFalso(self, texto)

    def locator(self, seletor):
        return _CampoFalso(self, seletor)

    def wait_for_timeout(self, ms):
        return None

    def screenshot(self, path=None, **kwargs):
        self.passos.append(("fotografou", str(path)))

    def tipos(self) -> list[str]:
        return [p[0] for p in self.passos]


BASE_FALSA = "http://localhost:3000"


def test_a_busca_recebe_o_filtro_de_exemplo_e_nao_outra_coisa():
    """O que a busca recebe, e não o nome da constante escrito no arquivo.

    Este é o mutante que sobreviveu à rodada anterior: trocar o uso por
    `busca.fill("")` mantendo `FILTRO_DE_EXEMPLO` escrito em algum lugar do
    arquivo passava verde, porque a asserção procurava o nome no código. Aqui
    a asserção é sobre o valor que chegou ao campo.
    """
    roteiro = carregar_roteiro()
    pagina = _PaginaFalsa()

    roteiro._usuarios_filtrados(pagina, BASE_FALSA)

    digitados = [passo for passo in pagina.passos if passo[0] == "digitou"]
    assert digitados == [("digitou", "Buscar por nome ou email…", "exemplo")]


def test_a_tela_nem_chega_a_abrir_com_filtro_frouxo(monkeypatch):
    """A guarda roda antes do `goto`, e a prova é que nada aconteceu.

    Guarda que existe e ninguém chama protege tanto quanto guarda que não
    existe. Com a lista de passos vazia, a tela não foi aberta nem preenchida:
    não houve instante nenhum com a lista real renderizada.
    """
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "FILTRO_DE_EXEMPLO", "")
    pagina = _PaginaFalsa()

    with pytest.raises(SystemExit):
        roteiro._usuarios_filtrados(pagina, BASE_FALSA)

    assert pagina.passos == [], (
        "a tela foi mexida antes de a guarda recusar o filtro"
    )


def test_o_painel_so_e_fotografado_depois_de_a_busca_ser_preenchida(tmp_path):
    """A ordem que importa, medida no caminho inteiro da captura.

    Entre abrir a tela e filtrar existe um instante com a lista real, e é esse
    instante que não pode virar arquivo.
    """
    roteiro = carregar_roteiro()
    pagina = _PaginaFalsa(url=BASE_FALSA)

    roteiro.painel_de_administracao(pagina, BASE_FALSA, tmp_path)

    tipos = pagina.tipos()
    assert "fotografou" in tipos, "o painel não chegou a ser capturado"
    assert tipos.index("digitou") < tipos.index("fotografou"), (
        "o painel é fotografado antes de a busca ser preenchida: o print "
        "sairia com nome e email de gente real"
    )


@pytest.mark.parametrize("captura", ["painel_de_administracao", "novo_usuario"])
def test_toda_captura_passa_pelo_filtro(monkeypatch, tmp_path, captura):
    """As duas funções de captura, e não só a que alguém lembrou de testar.

    Uma captura nova que pule `_usuarios_filtrados` é a porta pela qual o
    problema volta, e este teste a fecha para todas as que existem hoje.
    """
    roteiro = carregar_roteiro()
    monkeypatch.setattr(roteiro, "FILTRO_DE_EXEMPLO", "")
    pagina = _PaginaFalsa(url=BASE_FALSA)

    with pytest.raises(SystemExit):
        getattr(roteiro, captura)(pagina, BASE_FALSA, tmp_path)

    assert "fotografou" not in pagina.tipos(), (
        f"{captura} gravou um arquivo com o filtro da busca desligado"
    )


def test_toda_pessoa_de_exemplo_casa_com_o_filtro_da_busca():
    """A peneira que mantém gente real fora do print.

    O print da tela de Usuários só é publicável porque a busca é preenchida
    antes da captura, e a busca casa nome OU email. Se alguém acrescentar uma
    pessoa de exemplo com email fora de `exemplo.local`, ela continuaria
    aparecendo, mas o filtro deixaria de ser o que garante que TODAS as linhas
    do print são inventadas: a lista real voltaria junto na primeira pessoa de
    verdade cujo nome contivesse o termo. Este teste trava esse par.
    """
    roteiro = carregar_roteiro()

    assert roteiro.PESSOAS, "sem pessoa de exemplo não há print publicável"
    for pessoa in roteiro.PESSOAS:
        email = pessoa[2]
        assert email.endswith("@exemplo.local"), (
            f"{email} não é um endereço de exemplo: o print da lista de "
            "Usuários passaria a depender de sorte"
        )
        assert roteiro.FILTRO_DE_EXEMPLO in email, (
            f"{email} não casa com o filtro '{roteiro.FILTRO_DE_EXEMPLO}': a "
            "pessoa sumiria do print, ou o filtro teria de ser afrouxado"
        )
