"""A chamada à IA não roda no event loop (issue #773).

As rotas que conversam com a IA são `async def`, e o cliente do provedor é
síncrono. Chamado direto no corpo da rota, ele prende o worker inteiro enquanto
a resposta não chega (uma leitura de print leva dezenas de segundos): nem o
`/api/health` é atendido, e o `/deploy ship`, que faz health check com timeout,
desfaz um deploy bom porque alguém conversava com a IA naquela janela.

Duas provas aqui:

* **Por rota**, o cliente do provedor é dublado com uma função que anota o NOME
  da thread onde a chamada de fato correu. Ela tem que ser uma thread do
  executor da IA (`ia_*`). Na thread do loop o nome seria o da thread que o
  TestClient usa para o loop, e num `asyncio.to_thread` seria `asyncio_*`, o
  executor que o `/health` também usa.
* **Pela classe**, uma varredura estática de `app/` que reprova qualquer
  `async def` chamando, direto no corpo, uma função que chega ao provedor. É o
  que deixa o CI vermelho quando uma quinta rota nascer do jeito errado.
"""

from __future__ import annotations

import ast
import asyncio
import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_assistente_tecnologia import _corpo, _imagem, _montar, _pessoa  # noqa: E402
from test_ata_guiada import CURRENT_USER, FACILITADOR, _reuniao_programada, _SupabaseMock  # noqa: E402
from test_pops_elaboracao import ELABORADOR, _chat, _client_para, _sb  # noqa: E402

from app.dependencies import get_current_user, get_supabase_client  # noqa: E402
from app.limiter import limiter  # noqa: E402
from app.middleware.request_context import get_request_id, get_user_id, request_id_var, user_id_var  # noqa: E402
from app.routers import reunioes as reunioes_router  # noqa: E402
from app.services import ai_processor  # noqa: E402

CHAT_DO_ASSISTENTE = "/api/admin/tecnologia/assistente/chat"
LEITURA_DO_PRINT = "/api/admin/tecnologia/assistente/descrever-imagem"
CHAT_DE_CORRECAO = "/api/reunioes/R1/chat-correcao"
CHAT_DA_ATA_GUIADA = "/api/reunioes/R1/ata-guiada/chat"
MENSAGENS = {"messages": [{"role": "user", "content": "Corrige o resumo"}]}

# Uma resposta que serve às três rotas de JSON: cada uma lê só as chaves dela.
RESPOSTA_DO_MODELO = json.dumps({"reply": "Entendi.", "rascunho": {}, "correction_plan": []})


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    limiter._storage.reset()
    yield
    limiter._storage.reset()


class _ProvedorQueAnotaAThread:
    """Cliente OpenAI-like: guarda o nome da thread de cada chamada."""

    def __init__(self):
        self.threads: list[str] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **_kwargs):
        self.threads.append(threading.current_thread().name)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=RESPOSTA_DO_MODELO))])


@pytest.fixture
def provedor(monkeypatch) -> _ProvedorQueAnotaAThread:
    cliente = _ProvedorQueAnotaAThread()
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "openrouter")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (cliente, "modelo-teste", {}))
    return cliente


def _cliente_de_reunioes(monkeypatch, reuniao: dict) -> TestClient:
    """O router de Reuniões com um Facilitador comum que enxerga a Reunião.

    Espelha a fixture `make_client` de `test_ata_guiada.py` em vez de
    importá-la: fixture importada de outro arquivo de teste é redefinição de
    nome para o linter (mesma decisão de `test_ouvidoria_relatorio_mensal.py`).
    """
    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(reunioes_router.router, prefix="/api")
    sb = _SupabaseMock(reunioes=[reuniao])
    app.dependency_overrides[get_current_user] = lambda: CURRENT_USER
    app.dependency_overrides[get_supabase_client] = lambda: sb

    async def _facilitador(*_a, **_kw):
        return dict(FACILITADOR)

    async def _sem_restricao(*_a, **_kw):
        return None

    monkeypatch.setattr(reunioes_router, "get_participante_for_user", _facilitador)
    monkeypatch.setattr(reunioes_router, "get_allowed_reuniao_ids", _sem_restricao)
    return TestClient(app)


def _correu_no_executor_da_ia(provedor: _ProvedorQueAnotaAThread) -> None:
    assert provedor.threads, "a rota não chegou ao provedor"
    thread = provedor.threads[-1]
    assert thread.startswith("ia_"), f"a chamada à IA correu em {thread}, e não no executor da IA"


class TestPortaDaIa:
    def test_o_log_da_chamada_leva_o_request_id_e_o_user_id(self):
        """Mesmo log de antes: a linha da IA continua dizendo de que requisição veio.

        O `JsonFormatter` lê `request_id` e `user_id` de contextvars, e o
        `run_in_executor` sozinho NÃO os leva para a thread (o `to_thread` leva).
        Sem a cópia do contexto, o `_log_llm_call` e o log de erro do provedor
        saíam sem os dois campos, e não dava mais para ligar a falha à pessoa.
        """

        async def _turno():
            request_id_var.set("req-773")
            user_id_var.set("pessoa-773")
            return await ai_processor.chamar_ia_fora_do_loop(
                lambda: (get_request_id(), get_user_id(), threading.current_thread().name)
            )

        request_id, user_id, thread = asyncio.run(_turno())
        assert (request_id, user_id) == ("req-773", "pessoa-773")
        assert thread.startswith("ia_")


class TestRotasChamamAIaForaDoLoop:
    def test_chat_do_assistente_de_tecnologia(self, provedor):
        cliente = _montar(logado=_pessoa("p1"))
        resposta = cliente.post(CHAT_DO_ASSISTENTE, json=_corpo())
        assert resposta.status_code == 200, resposta.text
        _correu_no_executor_da_ia(provedor)

    def test_leitura_do_print_do_assistente(self, provedor):
        """A mais longa das quatro: visão leva dezenas de segundos."""
        cliente = _montar(logado=_pessoa("p1"))
        resposta = cliente.post(LEITURA_DO_PRINT, files=_imagem("tela.png"))
        assert resposta.status_code == 200, resposta.text
        _correu_no_executor_da_ia(provedor)

    def test_chat_de_correcao_da_ata(self, provedor, monkeypatch):
        reuniao = _reuniao_programada(
            status_ata="AGUARDANDO_VALIDACAO",
            json_ata={"resumo_executivo": "Resumo", "quadro_atribuicoes": []},
        )
        cliente = _cliente_de_reunioes(monkeypatch, reuniao)
        resposta = cliente.post(CHAT_DE_CORRECAO, json=MENSAGENS)
        assert resposta.status_code == 200, resposta.text
        _correu_no_executor_da_ia(provedor)

    def test_chat_da_ata_guiada(self, provedor, monkeypatch):
        """O fluxo principal do app, e por isso o que mais prendia o worker."""
        cliente = _cliente_de_reunioes(monkeypatch, _reuniao_programada())
        resposta = cliente.post(CHAT_DA_ATA_GUIADA, json={"rascunho": {}, **MENSAGENS})
        assert resposta.status_code == 200, resposta.text
        _correu_no_executor_da_ia(provedor)

    def test_chat_da_elaboracao_de_pop(self, provedor):
        """A quinta rota, que a triagem não listou e a trava da classe achou."""
        resposta = _chat(_client_para(ELABORADOR, _sb()))
        assert resposta.status_code == 200, resposta.text
        _correu_no_executor_da_ia(provedor)


# ═══════════════════════════════════════════════════════════════════════════
# A trava da classe: varredura estática de `app/`
# ═══════════════════════════════════════════════════════════════════════════

APP = Path(__file__).resolve().parent.parent / "app"


def _nome_chamado(chamada: ast.Call, apelidos: dict[str, str] | None = None) -> str | None:
    """`f(...)` e `modulo.f(...)` viram `f`. A varredura casa por nome.

    `apelidos` desfaz o `from x import f as g` do arquivo: `g(...)` vira `f`.
    """
    alvo = chamada.func
    if isinstance(alvo, ast.Name):
        return (apelidos or {}).get(alvo.id, alvo.id)
    if isinstance(alvo, ast.Attribute):
        return alvo.attr
    return None


def _apelidos(arvore: ast.AST) -> dict[str, str]:
    """`apelido -> nome de origem` de todo `import ... as ...` do arquivo."""
    return {
        nome.asname: nome.name.rsplit(".", 1)[-1]
        for no in ast.walk(arvore)
        if isinstance(no, ast.Import | ast.ImportFrom)
        for nome in no.names
        if nome.asname
    }


def _chama_o_provedor(chamada: ast.Call) -> bool:
    """`<qualquer coisa>.completions.create(...)` ou `_get_llm()`."""
    alvo = chamada.func
    if isinstance(alvo, ast.Attribute) and alvo.attr == "create":
        return isinstance(alvo.value, ast.Attribute) and alvo.value.attr == "completions"
    return _nome_chamado(chamada) == "_get_llm"


def _chamadas_do_corpo(funcao: ast.AST):
    """As chamadas que a função faz ELA MESMA.

    Função aninhada e lambda ficam de fora: o corpo delas roda quando alguém as
    chama, e não quando a função de fora passa por ali.
    """
    pendentes = list(ast.iter_child_nodes(funcao))
    while pendentes:
        no = pendentes.pop()
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(no, ast.Call):
            yield no
        pendentes.extend(ast.iter_child_nodes(no))


def _funcoes(raiz: Path):
    """`(arquivo, nó, apelidos do arquivo)` de toda função de todo `.py` debaixo de `raiz`."""
    for arquivo in sorted(raiz.rglob("*.py")):
        arvore = ast.parse(arquivo.read_text(encoding="utf-8"), filename=str(arquivo))
        apelidos = _apelidos(arvore)
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
                yield arquivo, no, apelidos


def funcoes_que_chegam_ao_provedor(raiz: Path) -> set[str]:
    """Nomes das funções SÍNCRONAS que, direto ou por outra, esperam o provedor.

    A lista não é escrita à mão: parte de quem chama o cliente e sobe por quem
    chama essas, até parar de crescer. Uma função nova de IA entra sozinha.
    `async def` não sobe: a rota assíncrona é justamente o que se confere.
    """
    sincronas = [(no, apelidos) for _, no, apelidos in _funcoes(raiz) if isinstance(no, ast.FunctionDef)]
    chegam = {no.name for no, _ in sincronas if any(_chama_o_provedor(c) for c in _chamadas_do_corpo(no))}
    cresceu = True
    while cresceu:
        cresceu = False
        for no, apelidos in sincronas:
            if no.name in chegam:
                continue
            if any(_nome_chamado(c, apelidos) in chegam for c in _chamadas_do_corpo(no)):
                chegam.add(no.name)
                cresceu = True
    return chegam


def async_que_chamam_a_ia_no_loop(raiz: Path) -> list[str]:
    """`arquivo:linha funcao -> chamada` de cada `async def` que espera o provedor no loop.

    Pega os dois jeitos: chamar uma função que chega ao provedor, e chamar o
    cliente ali mesmo (`_get_llm()` ou `.completions.create(...)` no corpo).
    """
    chegam = funcoes_que_chegam_ao_provedor(raiz)
    achados = []
    for arquivo, no, apelidos in _funcoes(raiz):
        if not isinstance(no, ast.AsyncFunctionDef):
            continue
        for chamada in _chamadas_do_corpo(no):
            nome = _nome_chamado(chamada, apelidos)
            if nome in chegam or _chama_o_provedor(chamada):
                relativo = arquivo.relative_to(raiz).as_posix()
                achados.append(f"{relativo}:{chamada.lineno} {no.name} -> {nome}")
    return sorted(achados)


SERVICO_DE_EXEMPLO = """
def _cliente():
    return None

def resumir(texto):
    return _cliente().chat.completions.create(model="m", messages=[])

def resumir_com_titulo(texto):
    return "Titulo: " + resumir(texto)
"""


class TestTravaDaClasse:
    def test_nenhuma_rota_async_do_app_chama_a_ia_no_loop(self):
        """Uma rota nova escrita do jeito errado deixa este teste vermelho.

        O jeito certo é `await ai_processor.chamar_ia_fora_do_loop(funcao, ...)`:
        a função vai como REFERÊNCIA, e quem a chama é o executor da IA.
        """
        achados = async_que_chamam_a_ia_no_loop(APP)
        assert achados == [], "rota async esperando a IA no event loop:\n" + "\n".join(achados)

    def test_a_varredura_enxerga_as_quatro_funcoes_da_issue(self):
        """Sem isto, uma varredura cega (conjunto vazio) passaria o teste acima."""
        chegam = funcoes_que_chegam_ao_provedor(APP)
        assert {"conversar", "descrever_imagem", "chat_correcao", "chat_ata_guiada"} <= chegam

    def test_rota_de_exemplo_escrita_do_jeito_errado_e_pega(self, tmp_path):
        (tmp_path / "servico.py").write_text(SERVICO_DE_EXEMPLO, encoding="utf-8")
        (tmp_path / "rota.py").write_text(
            "async def rota_nova(texto):\n    return servico.resumir_com_titulo(texto)\n",
            encoding="utf-8",
        )
        assert async_que_chamam_a_ia_no_loop(tmp_path) == ["rota.py:2 rota_nova -> resumir_com_titulo"]

    def test_rota_de_exemplo_escrita_do_jeito_certo_passa(self, tmp_path):
        (tmp_path / "servico.py").write_text(SERVICO_DE_EXEMPLO, encoding="utf-8")
        (tmp_path / "rota.py").write_text(
            "async def rota_nova(texto):\n    return await chamar_ia_fora_do_loop(servico.resumir_com_titulo, texto)\n",
            encoding="utf-8",
        )
        assert async_que_chamam_a_ia_no_loop(tmp_path) == []

    def test_rota_que_usa_o_cliente_direto_e_pega(self, tmp_path):
        """O jeito errado mais provável de uma rota nova: pegar o cliente e chamar ali mesmo."""
        (tmp_path / "rota.py").write_text(
            "async def rota_nova(texto):\n"
            "    cliente, modelo, extra = ai_processor._get_llm()\n"
            "    return cliente.chat.completions.create(model=modelo, messages=[])\n",
            encoding="utf-8",
        )
        assert async_que_chamam_a_ia_no_loop(tmp_path) == [
            "rota.py:2 rota_nova -> _get_llm",
            "rota.py:3 rota_nova -> create",
        ]

    def test_rota_que_chama_por_apelido_de_import_e_pega(self, tmp_path):
        """A varredura casa por nome, então o apelido volta ao nome de origem."""
        (tmp_path / "servico.py").write_text(SERVICO_DE_EXEMPLO, encoding="utf-8")
        (tmp_path / "rota.py").write_text(
            "from servico import resumir_com_titulo as resumir_rapido\n"
            "\n"
            "async def rota_nova(texto):\n"
            "    return resumir_rapido(texto)\n",
            encoding="utf-8",
        )
        assert async_que_chamam_a_ia_no_loop(tmp_path) == ["rota.py:4 rota_nova -> resumir_com_titulo"]
