"""O Kit de conhecimento do Assistente de Tecnologia (ADR 0056, decisao 2).

Este arquivo cuida do KIT: os oito `.md` de `app/conhecimento/`, o que pode e o
que nao pode estar escrito neles, e a prova de que os oito chegam ao prompt do
chat. O teste da ROTA (gate, tetos, normalizacao do rascunho, cerca) vive em
`test_assistente_tecnologia.py`.

Os dois ficam separados de proposito: o kit e um documento curado por gente e
muda por outro motivo que o codigo da rota, entao quem edita um texto do kit
sabe onde esta o teste que ele precisa ler.

A sanidade aqui e PURA no que da: o texto de cada arquivo lido do disco. So o
ultimo teste sobe a rota, porque "os oito chegam ao prompt" e uma afirmacao
sobre o prompt, nao sobre os arquivos.
"""

from __future__ import annotations

import json
import os
import re
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.routers.admin import tecnologia as tecnologia_router  # noqa: E402
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
}

# O nono arquivo nao e de Produto nenhum: e o da propria aba.
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
        assert len(_produtos_do_seed()) == 7

    def test_o_mapa_cobre_exatamente_o_seed(self):
        """Mutante: acrescentar um Produto ao seed sem escrever o texto dele."""
        assert sorted(ARQUIVO_POR_PRODUTO) == sorted(_produtos_do_seed())

    @pytest.mark.parametrize("produto", sorted(ARQUIVO_POR_PRODUTO))
    def test_o_produto_tem_arquivo_no_kit(self, produto):
        """Mutante: apagar um dos sete `.md`."""
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
# 3. Os oito arquivos chegam ao prompt do chat
# ═══════════════════════════════════════════════════════════════════════════

ROTA = "/api/admin/tecnologia/assistente/chat"

PRODUTO_ATIVO = {"id": "prod-ouvidoria", "nome": "Ouvidoria", "ativo": True, "ordem": 1, "dono_id": "p1"}

PESSOA = {
    "id": "p1",
    "auth_user_id": "auth-p1",
    "nome_completo": "p1",
    "email": "p1@hsm.com",
    "cargo": None,
    "area": None,
    "setor": None,
    "role": None,
    "ativo": True,
    "is_externo": False,
    "is_super_admin": True,
    "access_profile": "super_admin",
    "perfil_pop": None,
    "perfil_ouvidoria": None,
    "github_login": None,
    "data_cadastro": "2026-01-01",
}


class _TableQuery:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._eq: dict[str, Any] = {}

    def select(self, *_a, **_kw):
        return self

    def order(self, *_a, **_kw):
        return self

    def eq(self, coluna, valor):
        self._eq[coluna] = valor
        return self

    def execute(self):
        casam = [dict(linha) for linha in self._rows if all(linha.get(c) == v for c, v in self._eq.items())]
        return SimpleNamespace(data=casam)


class _SupabaseMock:
    def __init__(self, tabelas: dict[str, list[dict]]):
        self.tabelas = tabelas

    def table(self, nome: str):
        return _TableQuery(self.tabelas.setdefault(nome, []))


class _FakeLLMClient:
    """Cliente OpenAI-like que devolve um `content` fixo e guarda os kwargs de
    cada chamada, para olhar o prompt que o backend montou."""

    def __init__(self, content: str):
        self.calls: list[dict] = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    @property
    def prompt_de_usuario(self) -> str:
        return self.calls[-1]["messages"][1]["content"]


def _prompt_de_um_turno(monkeypatch) -> str:
    """Um turno de verdade pela rota, com o cliente do LLM substituido."""
    from app.services import ai_processor

    resposta = json.dumps(
        {"reply": "Entendi.", "rascunho": {"titulo": "", "tipo": None, "produto_id": None, "descricao": ""}},
        ensure_ascii=False,
    )
    cliente = _FakeLLMClient(resposta)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (cliente, "modelo-teste", {}))

    app = FastAPI()
    app.state.limiter = limiter
    app.include_router(tecnologia_router.router, prefix="/api")

    sb = _SupabaseMock(tabelas={"participantes": [PESSOA], "tecnologia_produtos": [PRODUTO_ATIVO]})

    async def _usuario() -> dict[str, Any]:
        return {"id": PESSOA["auth_user_id"], "email": PESSOA["email"], "metadata": {}}

    app.dependency_overrides[get_current_user] = _usuario
    app.dependency_overrides[get_supabase_client] = lambda: sb

    resposta_http = TestClient(app).post(
        ROTA, json={"rascunho": {}, "messages": [{"role": "user", "content": "como funciona a Ouvidoria?"}]}
    )
    assert resposta_http.status_code == 200
    return cliente.prompt_de_usuario


def _secoes_do_kit(prompt: str) -> dict[str, str]:
    """O prompt fatiado pelos cabecalhos que o carregador escreve.

    O corte na marca de FIM do kit nao e detalhe. `tecnologia.md` e o ultimo em
    ordem alfabetica, entao sem ele a fatia do ultimo arquivo engole tudo o que
    vem depois no prompt (a cerca, os Produtos, as Demandas abertas, o rascunho,
    a conversa e a data). Hoje isso ainda daria menos que o piso, mas a margem
    cresce sozinha a cada Produto ativo e a cada Demanda aberta: seria uma
    asserção que passa a medir o resto do prompt sem ninguem ter mexido nela.
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


class TestOitoArquivosNoPrompt:
    @pytest.fixture
    def secoes(self, monkeypatch) -> dict[str, str]:
        return _secoes_do_kit(_prompt_de_um_turno(monkeypatch))

    def test_o_carregador_ve_os_oito_arquivos(self):
        """Mutante: apagar um `.md` da pasta."""
        assert sorted(_secoes_do_kit(carregar_kit())) == sorted(ARQUIVOS_DO_KIT)

    @pytest.mark.parametrize("arquivo", ARQUIVOS_DO_KIT)
    def test_o_arquivo_chega_ao_prompt_com_o_cabecalho_e_com_o_texto(self, secoes, arquivo):
        """O cabecalho sozinho nao prova nada: um arquivo esvaziado entregaria
        os oito cabecalhos e zero material. A asserção e sobre o que veio
        DEPOIS do cabecalho.

        E nao ha vacuo de fixture aqui: o prompt e montado pelo backend a
        partir do disco dentro do turno, nao passado pelo teste."""
        assert arquivo in secoes
        assert len(secoes[arquivo].strip()) >= PISO_DE_TAMANHO

    def test_o_fatiador_para_na_marca_de_fim_do_kit(self):
        """Mutante no proprio detector: tirar o corte faz a fatia do ULTIMO
        arquivo engolir o resto do prompt, e a asserção de tamanho acima passa
        a medir a cerca, os Produtos e as Demandas em vez do material."""
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
