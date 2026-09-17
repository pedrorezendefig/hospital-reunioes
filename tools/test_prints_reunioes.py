"""Testes das guardas do Roteiro de prints de Reuniões e metas.

O roteiro (`docs/manual/prints/reunioes.py`) carrega três riscos:

1. O `--semear` grava: cria login no Supabase Auth, insere pessoas, reuniões e
   pendências. O que separa isso de um banco que não é o de desenvolvimento
   são as linhas de `_credenciais_locais`, que leem o `.env` e recusam toda
   URL que não seja `127.0.0.1` ou `localhost`.
2. As telas deste módulo mostram nome de gente o tempo todo, e o repositório é
   público. A guarda de endereço local é a última barreira antes de gravar um
   `.png` com o endereço da máquina de quem capturou.
3. O roteiro muda o estado da reunião de exemplo entre um print e outro. Se
   `por_reuniao` alcançasse outra reunião, ele estragaria trabalho alheio no
   banco local, que é compartilhado entre as sessões.

É isso que estes testes provam.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROTEIRO = (
    Path(__file__).resolve().parents[1] / "docs" / "manual" / "prints" / "reunioes.py"
)


def carregar_roteiro():
    """Importa o roteiro pelo caminho.

    Ele vive em `docs/manual/prints/`, fora de qualquer pacote, e não importa o
    Playwright no topo justamente para caber aqui: a trava roda no CI, onde o
    navegador não existe.
    """
    spec = importlib.util.spec_from_file_location("roteiro_prints_reunioes", ROTEIRO)
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


# --------------------------------------------------------------------------
# O banco que o `--semear` alcança
# --------------------------------------------------------------------------


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
# O endereço local no print
# --------------------------------------------------------------------------


def test_grava_print_quando_o_texto_esta_limpo(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê("Coordenação, 18 de setembro de 2026 · Validação Necessária")
    alvo = tmp_path / "validacao-necessaria.png"

    roteiro.capturar(pagina, alvo, "validacao-necessaria", full_page=True)

    assert len(pagina.chamadas) == 1
    assert pagina.chamadas[0]["path"] == str(alvo)
    assert pagina.chamadas[0]["full_page"] is True


def test_nao_grava_print_com_endereco_local(tmp_path):
    roteiro = carregar_roteiro()
    pagina = PaginaDublê("Abra a reunião em http://localhost:3000/reunioes/MANREU01")

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.capturar(pagina, tmp_path / "validacao-necessaria.png", "validacao")

    # O que importa não é a exceção, é o print não ter sido gravado.
    assert pagina.chamadas == []
    assert not (tmp_path / "validacao-necessaria.png").exists()


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
    """A guarda responde sobre endereço local, não sobre três strings."""
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint) as erro:
        roteiro.exigir_endereco_de_producao(
            f"abra http://{endereco}:3000/reunioes", "uma-tela"
        )

    # A mensagem diz o que fazer, não só o que houve.
    assert roteiro.BASE_DO_APP_EM_PRODUCAO in str(erro.value)


def test_o_dominio_das_pessoas_de_exemplo_nao_trava_a_captura():
    """Toda tela deste módulo mostra o e-mail de quem está logado no canto.

    Esse e-mail termina em `.local`, que é padrão de rede interna e é por isso
    que a guarda o persegue. Sem a exceção do domínio de exemplo, nenhum print
    deste módulo seria gravado.
    """
    roteiro = carregar_roteiro()

    roteiro.exigir_endereco_de_producao(
        f"Renata Fontes renata.fontes@{roteiro.DOMINIO_DE_EXEMPLO}", "dashboard"
    )


def test_a_excecao_do_dominio_de_exemplo_nao_abre_a_porta_para_outro_local():
    """O mutante que importa: trocar a exceção pelo sufixo `.local` inteiro.

    Com `re.sub(r"\\S*\\.local", ...)` no lugar do domínio exato, este caso
    passaria verde e o print com a máquina de quem capturou iria para o ar.
    """
    roteiro = carregar_roteiro()

    with pytest.raises(roteiro.EnderecoLocalNoPrint):
        roteiro.exigir_endereco_de_producao(
            f"renata.fontes@{roteiro.DOMINIO_DE_EXEMPLO} abriu http://hospital.local",
            "dashboard",
        )


def test_o_dominio_de_exemplo_e_o_termo_exato():
    """O valor inteiro, e não um pedaço dele.

    Com `DOMINIO_DE_EXEMPLO = ".local"` a guarda pararia de recusar qualquer
    endereço de rede interna, e um teste que só procurasse a constante no
    código passaria verde nesse mutante.
    """
    roteiro = carregar_roteiro()

    assert roteiro.DOMINIO_DE_EXEMPLO == "exemplo.local"


def test_todo_print_do_roteiro_passa_pela_guarda():
    """Print novo nasce protegido: ninguém chama `screenshot` por fora.

    É o que faz a trava valer para o print que ainda não existe, e não só para
    os de hoje. Vale também para a captura de um bloco recortado, que é um
    `screenshot` com `clip` e passa pelo mesmo caminho.
    """
    fonte = ROTEIRO.read_text(encoding="utf-8")
    corpo = fonte.split("def capturar(", 1)[1].split("\ndef ", 1)[0]
    assert ".screenshot(" in corpo, "a captura deixou de morar em `capturar`"
    assert fonte.count(".screenshot(") == 1, (
        "alguém chamou `screenshot` fora de `capturar`, e esse print não passa "
        "pela guarda de endereço local"
    )


# --------------------------------------------------------------------------
# O estado da reunião de exemplo
# --------------------------------------------------------------------------


def test_por_reuniao_so_alcanca_a_reuniao_de_exemplo(monkeypatch):
    """O banco local é compartilhado: mudar o estado de outra reunião estraga
    a captura de quem está trabalhando ao lado."""
    roteiro = carregar_roteiro()
    chamadas: list[tuple] = []
    monkeypatch.setattr(
        roteiro, "_rest", lambda *args, **kwargs: chamadas.append(args) or None
    )

    roteiro.por_reuniao(status_ata="PROCESSANDO")

    assert chamadas == [
        (f"reunioes?id_reuniao=eq.{roteiro.REUNIAO}", "PATCH", {"status_ata": "PROCESSANDO"})
    ]


def test_as_pessoas_de_exemplo_usam_so_o_dominio_inventado():
    """Nenhum e-mail de gente de verdade entra no `--semear`.

    O `--semear` grava no banco que as telas fotografam: um e-mail real aqui
    sai no print da tela de participantes e vai para um repositório público.
    """
    roteiro = carregar_roteiro()

    emails = [pessoa[2] for pessoa in roteiro.PESSOAS]
    assert emails, "o roteiro deixou de ter pessoas de exemplo"
    for email in emails:
        assert email.endswith(f"@{roteiro.DOMINIO_DE_EXEMPLO}"), email


# --------------------------------------------------------------------------
# A lista da arroba e a gente de verdade do banco local
# --------------------------------------------------------------------------


class ListaDaArroba:
    """A lista de nomes que a arroba abre, no mínimo que a guarda consulta."""

    def __init__(self, texto: str | None) -> None:
        self.texto = texto

    # `page.locator(...)` devolve isto, e a guarda usa `count`, `first` e
    # `inner_text`.
    def locator(self, seletor: str):
        return self

    def count(self) -> int:
        return 0 if self.texto is None else 1

    @property
    def first(self):
        return self

    def inner_text(self) -> str:
        return self.texto


def test_a_guarda_da_arroba_barra_quem_nao_e_pessoa_de_exemplo():
    """Mencionável é todo super admin do banco, e o banco local tem as contas
    de gente de verdade. Um nome desses no print vai para um site público."""
    roteiro = carregar_roteiro()
    lista = ListaDaArroba("LS\nLucas Sampaio\nVitta")

    with pytest.raises(SystemExit) as erro:
        roteiro._exigir_so_pessoas_de_exemplo(lista, "mencao-na-pendencia")

    assert "Lucas Sampaio" in str(erro.value)


def test_a_guarda_da_arroba_deixa_passar_so_gente_de_exemplo():
    """As iniciais do avatar saem no mesmo texto e não identificam ninguém."""
    roteiro = carregar_roteiro()
    _, nome, _, cargo, setor, _, _ = roteiro.PESSOAS[3]
    lista = ListaDaArroba(f"LB\n{nome}\n{setor}")

    roteiro._exigir_so_pessoas_de_exemplo(lista, "mencao-na-pendencia")


def test_a_guarda_da_arroba_para_quando_a_lista_nao_abriu():
    """Sem lista na tela o balão sairia solto, apontando o nada."""
    roteiro = carregar_roteiro()

    with pytest.raises(SystemExit) as erro:
        roteiro._exigir_so_pessoas_de_exemplo(ListaDaArroba(None), "mencao-na-pendencia")

    assert "não abriu" in str(erro.value)


# --------------------------------------------------------------------------
# O comentário de exemplo e o aviso do sino
# --------------------------------------------------------------------------


def semear_registrando(monkeypatch) -> list[tuple]:
    """Roda o `--semear` com o banco dublado e devolve o que ele chamaria."""
    roteiro = carregar_roteiro()
    chamadas: list[tuple] = []

    def rest(caminho, metodo="GET", corpo=None, prefer=None):
        chamadas.append((caminho, metodo, corpo))
        return []

    monkeypatch.setattr(roteiro, "_credenciais_locais", lambda: ("http://127.0.0.1", "k"))
    monkeypatch.setattr(roteiro, "_login_de_exemplo", lambda email, nome: "auth-" + email)
    monkeypatch.setattr(roteiro, "_rest", rest)

    roteiro.semear()
    return chamadas


def test_o_semear_apaga_o_comentario_de_exemplo_antes_de_criar(monkeypatch):
    """Sem apagar, o histórico cresce uma linha por rodada e o sino acumula
    avisos: os dois prints mudariam sozinhos de uma captura para a outra."""
    chamadas = semear_registrando(monkeypatch)

    apagou = [i for i, (c, m, _) in enumerate(chamadas) if m == "DELETE" and "comentarios_pendencias" in c]
    criou = [i for i, (c, m, _) in enumerate(chamadas) if m == "POST" and c == "comentarios_pendencias"]
    assert apagou and criou, "o comentário de exemplo saiu do --semear"
    assert max(apagou) < min(criou), "o --semear cria o comentário sem apagar o da rodada anterior"


def test_o_semear_apaga_o_aviso_do_sino_antes_de_criar(monkeypatch):
    chamadas = semear_registrando(monkeypatch)

    apagou = [i for i, (c, m, _) in enumerate(chamadas) if m == "DELETE" and c.startswith("notificacoes?")]
    criou = [i for i, (c, m, _) in enumerate(chamadas) if m == "POST" and c == "notificacoes"]
    assert apagou and criou, "o aviso do sino saiu do --semear"
    assert max(apagou) < min(criou), "o --semear acende um aviso novo sem apagar o da rodada anterior"


def test_a_pendencia_do_historico_vazio_nao_recebe_comentario(monkeypatch):
    """O print do passo que mostra 'Sem rastros de atividade.' só existe
    enquanto essa pendência não tiver comentário nenhum."""
    roteiro = carregar_roteiro()
    chamadas = semear_registrando(monkeypatch)

    assert roteiro.PENDENCIA_COM_COMENTARIO != roteiro.PENDENCIA_SEM_COMENTARIO
    for caminho, metodo, corpo in chamadas:
        if metodo == "POST" and caminho == "comentarios_pendencias":
            for linha in corpo:
                assert linha["id_acao"] != roteiro.PENDENCIA_SEM_COMENTARIO


def test_o_comentario_de_exemplo_menciona_quem_o_print_do_sino_mostra(monkeypatch):
    """O aviso do sino é da conta que os prints usam: sem isso, o print do
    passo 6 sairia com o sino vazio."""
    roteiro = carregar_roteiro()
    chamadas = semear_registrando(monkeypatch)

    comentario = next(c for cam, m, c in chamadas if m == "POST" and cam == "comentarios_pendencias")
    aviso = next(c for cam, m, c in chamadas if m == "POST" and cam == "notificacoes")
    assert comentario[0]["mencoes"] == [roteiro.FACILITADORA[0]]
    assert aviso[0]["destinatario_id"] == roteiro.FACILITADORA[0]
    assert aviso[0]["tipo"] == "MENCAO"
