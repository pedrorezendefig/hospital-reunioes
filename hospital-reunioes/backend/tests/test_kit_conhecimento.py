"""O Kit de conhecimento do Assistente de Tecnologia (ADR 0056, decisao 2).

Este arquivo cuida do KIT: os nove `.md` de `app/conhecimento/`, o que pode e o
que nao pode estar escrito neles, e a prova de que os nove chegam ao prompt do
chat. O teste da ROTA (gate, tetos, normalizacao do rascunho, cerca) vive em
`test_assistente_tecnologia.py`.

Os dois ficam separados de proposito: o kit e um documento curado por gente e
muda por outro motivo que o codigo da rota, entao quem edita um texto do kit
sabe onde esta o teste que ele precisa ler.

A sanidade aqui e PURA no que da: o texto de cada arquivo lido do disco. So o
ultimo teste sobe a rota, porque "os nove chegam ao prompt" e uma afirmacao
sobre o prompt, nao sobre os arquivos.
"""

from __future__ import annotations

import os
import re
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


from app.limiter import limiter  # noqa: E402
from app.services import assistente_tecnologia  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR, carregar_kit  # noqa: E402

MIGRATIONS_DIR = Path(__file__).parent.parent.parent / "supabase" / "migrations"

# O arquivo do kit de cada Produto do seed. O mapa e escrito a mao, e nao
# derivado do nome por uma funcao de slug, porque "Integração Ana x MV" vira
# `integracao-ana-mv.md` (o "x" nao entra) e uma funcao que acertasse esse caso
# estaria escrita para ele.
ARQUIVO_POR_PRODUTO = {
    "Ana": "ana.md",
    "Integração Ana x MV": "integracao-ana-mv.md",
    "Reuniões": "reunioes.md",
    "Ouvidoria": "ouvidoria.md",
    "POPs": "pops.md",
    "Site": "site.md",
    "Infra": "infra.md",
    "Central de Comando": "central-de-comando.md",
    "Contas médicas": "contas-medicas.md",
}

# O arquivo que sobra nao e de Produto nenhum: e o da propria aba.
ARQUIVO_DA_ABA = "tecnologia.md"

ARQUIVOS_DO_KIT = (ARQUIVO_DA_ABA, *sorted(ARQUIVO_POR_PRODUTO.values()))


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """O slowapi conta por PROCESSO e o TestClient sempre chega do mesmo
    endereco: sem o reset, o teto vazado de outro arquivo cai aqui."""
    limiter._storage.reset()
    yield
    limiter._storage.reset()


@pytest.fixture(autouse=True)
def _llm_em_mock(monkeypatch):
    """O pytest carrega o `.env` real (chave de PROD). Sem isto, o teste que
    sobe a rota bateria no provedor de verdade."""
    from app.services import ai_processor

    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "mock")
    yield


def _texto(nome: str) -> str:
    return (CONHECIMENTO_DIR / nome).read_text(encoding="utf-8")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Existe um arquivo por Produto do seed
# ═══════════════════════════════════════════════════════════════════════════


def _produtos_do_seed() -> list[str]:
    """Os Produtos como o banco nasce, lidos da migration, nao decorados aqui.

    E o que faz este arquivo reprovar quando alguem acrescenta um Produto ao
    seed e esquece o texto dele: um `SETE_PRODUTOS` escrito a mao passaria
    verde sem nunca ter olhado para o seed.
    """
    sql = "\n".join(caminho.read_text(encoding="utf-8") for caminho in sorted(MIGRATIONS_DIR.glob("*.sql")))
    blocos = re.findall(
        r"INSERT INTO tecnologia_produtos\s*\([^)]*\)\s*VALUES(.*?);",
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    return [nome for bloco in blocos for nome in re.findall(r"\(\s*'([^']+)'", bloco)]


class TestUmArquivoPorProduto:
    def test_a_migration_de_fato_semeia_produtos(self):
        """Piso de sanidade do proprio detector: se a regex parar de casar, a
        lista volta vazia e TODO teste parametrizado por ela some em silencio,
        verde, sem ter olhado para nada."""
        assert len(_produtos_do_seed()) == 9

    def test_o_mapa_cobre_exatamente_o_seed(self):
        """Mutante: acrescentar um Produto ao seed sem escrever o texto dele."""
        assert sorted(ARQUIVO_POR_PRODUTO) == sorted(_produtos_do_seed())

    @pytest.mark.parametrize("produto", sorted(ARQUIVO_POR_PRODUTO))
    def test_o_produto_tem_arquivo_no_kit(self, produto):
        """Mutante: apagar um dos oito `.md` de Produto."""
        assert (CONHECIMENTO_DIR / ARQUIVO_POR_PRODUTO[produto]).is_file()

    @pytest.mark.parametrize("produto", sorted(ARQUIVO_POR_PRODUTO))
    def test_o_arquivo_abre_com_o_nome_do_produto(self, produto):
        """O titulo e o nome do Produto como o hospital o ve na tela, e nao o
        nome do arquivo: e por ele que o assistente diz de onde tirou."""
        assert _texto(ARQUIVO_POR_PRODUTO[produto]).splitlines()[0] == f"# {produto}"

    def test_a_pasta_nao_tem_arquivo_fora_do_kit(self):
        """A pasta nao e lugar de README nem de nota para quem programa: TODO
        `.md` la dentro vai inteiro para o prompt e seria citado ao diretor."""
        assert sorted(caminho.name for caminho in CONHECIMENTO_DIR.glob("*.md")) == sorted(ARQUIVOS_DO_KIT)


# ═══════════════════════════════════════════════════════════════════════════
# 2. O que nao pode estar escrito num texto do kit
# ═══════════════════════════════════════════════════════════════════════════

# As labels de processo do repositorio. Nenhuma delas tem o que fazer num texto
# escrito para o diretor (ADR 0054, decisao 9).
LABELS_DO_REPO = (
    "needs-triage",
    "needs-info",
    "ready-for-agent",
    "ready-for-human",
    "wontfix",
    "in-progress",
    "blocked",
    "revisor-comentou",
)

NUMERO_DE_ISSUE = re.compile(r"#\d")

# Um caminho de rota: duas pastas que comecam com letra. A exigencia de letra e
# o que separa `/admin/tecnologia` de uma data como 15/09/2026.
ROTA_DA_API = re.compile(r"/[a-z][a-z0-9-]*/[a-z][a-z0-9-]*")

NOME_DE_ARQUIVO_DO_CODIGO = re.compile(r"\b[\w-]+\.(?:py|tsx?|sql|md|ya?ml|json|css|sh)\b")

# Numero minimo de caracteres para um texto contar como escrito. Nao e uma
# medida de qualidade: e o piso que separa um arquivo de verdade de um arquivo
# que alguem criou vazio, ou com o titulo e mais nada, so para o teste do item
# 1 ficar verde.
PISO_DE_TAMANHO = 800


def _tabelas_do_banco() -> list[str]:
    """Os nomes de tabela que este teste sabe procurar num texto de gente.

    So as tabelas com `_` no nome. As de palavra unica (`pendencias`,
    `participantes`, `setores`, `pops`) sao palavras correntes em portugues, e
    procura-las aqui reprovaria a frase certa, nao o vocabulario errado. O
    detector reconhece o que e inconfundivelmente identificador de banco, e o
    que ele nao pega e a revisao humana que pega.
    """
    sql = "\n".join(caminho.read_text(encoding="utf-8") for caminho in sorted(MIGRATIONS_DIR.glob("*.sql")))
    nomes = re.findall(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(?:public\.)?([a-zA-Z_][a-zA-Z0-9_]*)", sql)
    return sorted({nome.lower() for nome in nomes if "_" in nome})


@pytest.mark.parametrize("arquivo", ARQUIVOS_DO_KIT)
class TestSanidadeDoTexto:
    def test_tem_texto_de_verdade(self, arquivo):
        """Mutante: esvaziar um dos arquivos."""
        assert len(_texto(arquivo).strip()) >= PISO_DE_TAMANHO

    def test_abre_com_um_titulo(self, arquivo):
        assert _texto(arquivo).lstrip().startswith("# ")

    def test_e_escrito_em_secoes_com_titulos(self, arquivo):
        """O assistente cita a secao de onde tirou a resposta ("esta no texto
        da Ouvidoria, em Encerramento"): sem titulo de secao ele nao tem o que
        citar."""
        secoes = [linha for linha in _texto(arquivo).splitlines() if linha.startswith("## ")]
        assert len(secoes) >= 3

    def test_sem_numero_de_issue(self, arquivo):
        """Mutante: escrever `#123` no meio de uma frase."""
        assert NUMERO_DE_ISSUE.search(_texto(arquivo)) is None

    @pytest.mark.parametrize("label", LABELS_DO_REPO)
    def test_sem_label_do_repositorio(self, arquivo, label):
        assert label not in _texto(arquivo)

    def test_sem_travessao_nem_meia_risca(self, arquivo):
        """Mutante: trocar uma virgula por travessao."""
        texto = _texto(arquivo)
        assert chr(0x2014) not in texto
        assert chr(0x2013) not in texto

    def test_sem_nome_de_tabela_do_banco(self, arquivo):
        texto = _texto(arquivo).lower()
        assert [tabela for tabela in _tabelas_do_banco() if tabela in texto] == []

    def test_sem_rota_da_api(self, arquivo):
        assert ROTA_DA_API.search(_texto(arquivo)) is None

    def test_sem_nome_de_arquivo_do_codigo(self, arquivo):
        assert NOME_DE_ARQUIVO_DO_CODIGO.search(_texto(arquivo)) is None


class TestOsDetectoresMordem:
    """O detector tambem e codigo, e um teste de ausencia passa verde quando a
    expressao regular para de casar. Aqui cada um deles ve uma frase que ele
    TEM que reprovar."""

    def test_numero_de_issue(self):
        assert NUMERO_DE_ISSUE.search("resolvido na #123 da semana passada") is not None

    def test_rota_da_api(self):
        assert ROTA_DA_API.search("chame /admin/tecnologia para isso") is not None

    def test_data_nao_e_rota(self):
        assert ROTA_DA_API.search("a mudança entrou em 15/09/2026") is None

    def test_nome_de_arquivo_do_codigo(self):
        assert NOME_DE_ARQUIVO_DO_CODIGO.search("o cálculo mora em conhecimento.py") is not None

    def test_tabela_do_banco(self):
        assert "tecnologia_demandas" in _tabelas_do_banco()


# ═══════════════════════════════════════════════════════════════════════════
# 3. Os nove arquivos chegam ao prompt do chat
# ═══════════════════════════════════════════════════════════════════════════


def _prompt_de_um_turno(monkeypatch) -> str:
    """Um turno de verdade pela rota do chat, com o cliente do LLM substituido.

    O kit vai no bloco fixo do sistema (ADR 0077, decisao 9, com o
    `cache_control`), e e de la que o teste o le.
    """
    from test_planejamento_demanda import _ia
    from test_tecnologia_chat import _turno
    from test_tecnologia_vinculo import DIRETOR, _montar

    cliente = _ia(monkeypatch, _turno())
    client, _, _ = _montar(logado=DIRETOR, monkeypatch=monkeypatch)

    resposta = client.post("/api/admin/tecnologia/chat", json={"escolha": "bug"})

    assert resposta.status_code == 201, resposta.text
    return "\n".join(bloco["text"] for bloco in cliente.chamadas[-1]["system"])


def _secoes_do_kit(prompt: str) -> dict[str, str]:
    """O prompt fatiado pelos cabecalhos que o carregador escreve.

    O corte na marca de FIM do kit nao e detalhe. `tecnologia.md` e o ultimo em
    ordem alfabetica, entao sem ele a fatia do ultimo arquivo engole tudo o que
    vem depois no prompt (as regras de leitura do codigo, por exemplo): seria
    uma asserção que passa a medir o resto do prompt sem ninguem ter mexido
    nela.
    """
    prompt = prompt.split(assistente_tecnologia.MARCA_FIM_KIT)[0]
    secoes: dict[str, str] = {}
    atual: str | None = None
    for linha in prompt.splitlines():
        cabecalho = re.fullmatch(r"\s*# ([a-z0-9-]+\.md)\s*", linha)
        if cabecalho:
            atual = cabecalho.group(1)
            secoes[atual] = ""
        elif atual is not None:
            secoes[atual] += linha + "\n"
    # Tira o recuo que o BACKEND pos, e so ele: `dedent` remove o branco comum
    # a todas as linhas, entao o recuo interno do proprio texto (uma lista
    # aninhada, por exemplo) sobrevive.
    #
    # Sem isto o piso mediria caractere que o arquivo nao tem. O recuo de
    # `recuar_continuacao` acrescenta quatro caracteres por linha, o que da de
    # +116 a +276 por arquivo neste kit: `site.md` cortado para 790 caracteres
    # reprovaria no teste de disco e passaria aqui, e o piso estaria medindo a
    # moldura em vez do material.
    return {nome: textwrap.dedent(corpo) for nome, corpo in secoes.items()}


class TestNoveArquivosNoPrompt:
    @pytest.fixture
    def secoes(self, monkeypatch) -> dict[str, str]:
        return _secoes_do_kit(_prompt_de_um_turno(monkeypatch))

    def test_o_carregador_ve_os_nove_arquivos(self):
        """Mutante: apagar um `.md` da pasta."""
        assert sorted(_secoes_do_kit(carregar_kit())) == sorted(ARQUIVOS_DO_KIT)

    @pytest.mark.parametrize("arquivo", ARQUIVOS_DO_KIT)
    def test_o_arquivo_chega_ao_prompt_com_o_cabecalho_e_com_o_texto(self, secoes, arquivo):
        """O cabecalho sozinho nao prova nada: um arquivo esvaziado entregaria
        os nove cabecalhos e zero material. A asserção e sobre o que veio
        DEPOIS do cabecalho.

        E nao ha vacuo de fixture aqui: o prompt e montado pelo backend a
        partir do disco dentro do turno, nao passado pelo teste."""
        assert arquivo in secoes
        assert len(secoes[arquivo].strip()) >= PISO_DE_TAMANHO

    def test_o_fatiador_para_na_marca_de_fim_do_kit(self):
        """Mutante no proprio detector: tirar o corte faz a fatia do ULTIMO
        arquivo engolir o resto do prompt, e a asserção de tamanho acima passa
        a medir o resto do prompt em vez do material."""
        prompt = "\n".join(
            [
                "    # tecnologia.md",
                "    material do arquivo",
                assistente_tecnologia.MARCA_FIM_KIT,
                "o que vem depois do kit no prompt",
            ]
        )
        assert "depois do kit" not in _secoes_do_kit(prompt)["tecnologia.md"]

    def test_o_fatiador_devolve_o_texto_sem_o_recuo_do_backend(self):
        """Mutante no proprio detector: tirar o `dedent` faz o piso contar
        quatro caracteres de moldura por linha, e um arquivo curto demais passa
        aqui por causa do recuo, nao do material."""
        prompt = "    # site.md\n    uma linha\n    outra linha\n"
        assert _secoes_do_kit(prompt)["site.md"] == "uma linha\noutra linha\n"

    def test_o_fatiador_nao_inventa_secao(self):
        """Mutante no proprio detector: se `_secoes_do_kit` casasse qualquer
        linha, o teste acima passaria com o prompt errado."""
        assert _secoes_do_kit("# titulo de gente\ntexto\n") == {}


# ═══════════════════════════════════════════════════════════════════════════
# 4. O texto da aba conta a aba como ela esta hoje (PRD #1056)
# ═══════════════════════════════════════════════════════════════════════════
#
# O assistente responde do kit e cita a secao. Se o texto da aba descreve a
# tela de antes (cinco colunas, "Minha vez", sem anexo), ele responde certo
# sobre uma tela que nao existe mais. As palavras procuradas aqui sao as da
# TELA (rotulos do frontend), nao as do glossario: e com elas que o diretor
# pergunta.


def _secao(texto: str, titulo: str) -> str:
    """O corpo da secao `## titulo`, ate a proxima secao de mesmo nivel.

    Devolve vazio quando a secao nao existe: a asserção de conteudo reprova
    com o termo que faltou, em vez de um KeyError sem contexto.
    """
    corpo: list[str] = []
    dentro = False
    for linha in texto.splitlines():
        if linha.startswith("## "):
            dentro = linha[3:].strip() == titulo
            continue
        if dentro:
            corpo.append(linha)
    return "\n".join(corpo)


# O que saiu da aba com a ADR 0077 (issue #1386), com as palavras da TELA de
# antes: e com elas que o diretor pergunta, e um kit que ainda as cita faz o
# Assistente descrever uma tela que nao existe mais.
APOSENTADOS_DA_ABA = (
    "Quadro",
    "Painel",
    "engrenagem",
    "formulário",
    "Nova Demanda",
    "Criar Demanda",
    "Copiar para IA",
    "Levar para desenvolvimento",
    "Minha vez",
    "Histórico",
    "Concluir",
    "Cancelar",
    "Mover",
    "raia",
    "esponsável",
    "rioridade",
    "menç",
    "mencion",
    "arroba",
    "e-mail",
    "Tipos",
    "Aguardando",
    "dono",
    "card aberto",
    "Planejar com a IA",
)


class TestOTextoDaAbaContaATelaDeHoje:
    @pytest.fixture
    def texto(self) -> str:
        return _texto(ARQUIVO_DA_ABA)

    @pytest.mark.parametrize("aposentado", APOSENTADOS_DA_ABA)
    def test_o_texto_da_aba_nao_cita_o_que_saiu(self, texto, aposentado):
        """Criterio 4 da issue #1386: o Quadro, o Painel, os Produtos, o
        formulario, a Conversa do card, as mencoes e o e-mail da aba sairam do
        codigo, e o texto que o Assistente le tambem nao os cita."""
        assert aposentado not in texto

    def test_o_detector_morde_a_tela_de_antes(self):
        """O detector tambem e codigo: o texto de antes desta fatia, com o
        Quadro e o Painel, tem que reprovar nele."""
        antes = "A aba tem o **Quadro**, o **Painel** e a Conversa do card aberto, com menção."
        assert [termo for termo in APOSENTADOS_DA_ABA if termo in antes] == ["Quadro", "Painel", "menç", "card aberto"]

    def test_os_anexos_dizem_a_porta_o_limite_e_o_apagamento(self, texto):
        anexos = _secao(texto, "Os anexos da Demanda")
        for termo in ("botão de imagem", "até 10", "apagad"):
            assert termo in anexos, termo

    def test_os_anexos_dizem_o_prazo_depois_de_em_producao(self, texto):
        """Issue #1382: o print sai 30 dias depois de Em produção, e logo
        quando a entrega fica Não será feita. É o que o diretor pergunta."""
        anexos = _secao(texto, "Os anexos da Demanda")
        for termo in ("30 dias depois", "**Em produção**", "**Não será feita**"):
            assert termo in anexos, termo
        decidido = _secao(texto, "O que já foi decidido")
        assert "30 dias depois de Em produção" in decidido

    def test_a_etapa_tem_as_sete_e_nunca_se_digita(self, texto):
        etapa = _secao(texto, "A Etapa")
        for termo in (
            "**Registrada**",
            "**Em análise**",
            "**Planejada**",
            "**Em desenvolvimento**",
            "**Entregue**",
            "**Em produção**",
            "**Não será feita**",
            "nunca é digitada",
        ):
            assert termo in etapa, termo

    def test_os_pedidos_ao_hospital_voltaram_para_o_whatsapp(self, texto):
        """ADR 0077, decisao 3: a aba e so de um sentido, o diretor relata."""
        assert "WhatsApp" in _secao(texto, "O que é uma Demanda")

    def test_o_planejamento_diz_o_que_e_quando_aparece_e_o_que_o_card_faz(self, texto):
        """ADR 0077, issue #1383. O planejamento e o caminho da melhoria dentro
        do chat: o teto, o fechar, o resumo com o que ficou em aberto, o Criar
        o card que leva ao desenvolvimento e o Nao bateu."""
        planejamento = _secao(texto, "O Planejamento da Demanda")
        termos = (
            "melhoria",
            "12 perguntas",
            "Fechar e resumir",
            "ficou em aberto",
            "**Criar o card**",
            "desenvolvimento",
            "**Não bateu**",
            "O que já foi decidido",
            "**Em análise**",
            "**O que muda**",
        )
        for termo in termos:
            assert termo in planejamento, termo
        for aposentado in ("Continuar planejamento", "Sim, mandar para os desenvolvedores"):
            assert aposentado not in texto, aposentado

    def test_o_planejamento_ja_esta_no_aplicativo(self, texto):
        """PRD #1344 entregue: a marca "ainda nao esta no aplicativo" das ondas
        anteriores sai do texto do planejamento e do "O que ja foi decidido"."""
        assert "ainda não está no aplicativo" not in _secao(texto, "O Planejamento da Demanda")
        decidido = _secao(texto, "O que já foi decidido")
        for item in decidido.splitlines():
            if "planejamento" in item:
                assert "ainda não está no aplicativo" not in item, item

    def test_o_texto_nao_manda_para_o_manual_que_saiu_do_ar(self, texto):
        """ADR 0078. O Manual do usuario saiu da plataforma: o assistente nao
        pode mandar o diretor para um endereco que nao existe mais."""
        assert "vercel.app" not in texto
        assert "Manual" not in texto

    @pytest.mark.parametrize("aposentado", ["Minha vez", "cinco colunas"])
    def test_sem_o_nome_da_tela_de_antes(self, texto, aposentado):
        assert aposentado not in texto


class TestOFatiadorDeSecao:
    """O detector acima: um `_secao` que devolvesse o texto inteiro deixaria
    toda asserção de conteudo verde lendo a secao vizinha."""

    def test_para_na_secao_seguinte(self):
        texto = "# Aba\n\n## O Quadro\nraias\n\n## O Painel\nnumeros\n"
        assert "numeros" not in _secao(texto, "O Quadro")
        assert "raias" in _secao(texto, "O Quadro")

    def test_secao_que_nao_existe_e_vazia(self):
        assert _secao("# Aba\n\n## O Quadro\nraias\n", "O Painel") == ""


# ═══════════════════════════════════════════════════════════════════════════
# 5. "O que já foi decidido" em cada arquivo (ADR 0075, decisao 4)
# ═══════════════════════════════════════════════════════════════════════════
#
# A secao e com o que o Planejamento da Demanda desafia o pedido do diretor:
# quando o pedido esbarra numa regra da casa, o agente recusa ou redireciona e
# cita esta secao. Sem ela em algum arquivo, o agente nao tem o que citar sobre
# aquele modulo e volta a concordar com tudo.

SECAO_DECIDIDO = "O que já foi decidido"

# Piso de decisoes por arquivo. Nao mede qualidade: separa uma secao escrita de
# uma secao criada com uma linha so para o teste ficar verde.
PISO_DE_DECISOES = 3

# Uma decisao por item de lista, em UMA frase: fim de frase no meio do item
# (ponto, interrogacao ou exclamacao seguidos de espaco e maiuscula) e a segunda
# frase que a regra proibe.
SEGUNDA_FRASE = re.compile(r"[.!?]\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]")

# O vocabulario de quem programa, que o diretor nao fala: o registro de decisao
# (com ou sem o numero de quatro digitos), o documento de produto, a issue e o
# que acontece com o codigo. Palavra inteira e sem caixa: "issues" e "Deploy"
# tambem sao.
VOCABULARIO_DO_REPOSITORIO = re.compile(
    r"\b(?:ADRs?|PRDs?|issues?|labels?|pull requests?|commits?|merges?|deploys?)\b|(?<![\d-])\b0\d{3}\b",
    flags=re.IGNORECASE,
)


def _decisoes(arquivo: str) -> list[str]:
    """Os itens de lista da secao. Texto corrido fora da lista nao conta como
    decisao: o agente cita a decisao, e a decisao e o item."""
    corpo = _secao(_texto(arquivo), SECAO_DECIDIDO)
    return [linha[2:].strip() for linha in corpo.splitlines() if linha.startswith("- ")]


@pytest.mark.parametrize("arquivo", ARQUIVOS_DO_KIT)
class TestOQueJaFoiDecidido:
    def test_o_arquivo_tem_a_secao_com_decisoes(self, arquivo):
        """Mutante: apagar a secao de um dos dez arquivos."""
        assert len(_decisoes(arquivo)) >= PISO_DE_DECISOES

    def test_cada_decisao_e_uma_frase_so(self, arquivo):
        """Mutante: emendar duas decisoes no mesmo item."""
        for decisao in _decisoes(arquivo):
            assert decisao.endswith("."), decisao
            assert SEGUNDA_FRASE.search(decisao) is None, decisao

    def test_a_secao_nao_fala_a_lingua_do_repositorio(self, arquivo):
        """A secao nasce das decisoes registradas para quem programa, e por isso
        e onde o numero da decisao, a issue e a tabela mais tentam vazar.

        Mutante: escrever "(ADR 0037)" no fim de uma decisao.
        """
        secao = _secao(_texto(arquivo), SECAO_DECIDIDO)
        assert secao.strip()
        assert VOCABULARIO_DO_REPOSITORIO.search(secao) is None
        assert NUMERO_DE_ISSUE.search(secao) is None
        assert [label for label in LABELS_DO_REPO if label in secao] == []
        assert [tabela for tabela in _tabelas_do_banco() if tabela in secao.lower()] == []
        assert ROTA_DA_API.search(secao) is None
        assert NOME_DE_ARQUIVO_DO_CODIGO.search(secao) is None


class TestODetectorDeFrase:
    """O detector de frase tambem e codigo: cego, ele deixaria passar o item
    com duas decisoes emendadas."""

    def test_pega_a_segunda_frase(self):
        assert SEGUNDA_FRASE.search("O caso nasce sem tipo. Quem classifica é o ouvidor.") is not None

    def test_numero_com_virgula_e_protocolo_nao_sao_fim_de_frase(self):
        assert SEGUNDA_FRASE.search("O protocolo é 2026-0007 e custa R$ 1,50 por conta.") is None

    @pytest.mark.parametrize(
        "frase",
        ["o tipo decide o sigilo (ADR 0037)", "como na decisão 0054", "veio do PRD da Ouvidoria", "virou Issue"],
    )
    def test_o_vocabulario_do_repositorio_e_pego(self, frase):
        assert VOCABULARIO_DO_REPOSITORIO.search(frase) is not None

    def test_o_protocolo_nao_e_numero_de_decisao(self):
        """O protocolo da Ouvidoria tem quatro digitos com zero na frente, mas
        colado ao ano por hifen: e texto de gente, nao vocabulario do repo."""
        assert VOCABULARIO_DO_REPOSITORIO.search("no formato ano mais número, como 2026-0007") is None
