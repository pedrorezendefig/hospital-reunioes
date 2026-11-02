"""O agente da Tecnologia lê o código (issue #1385, PRD #1380, ADR 0077, decisão 5).

O chat ganha quatro ferramentas só de leitura sobre o repositório público, pela
API do GitHub e pelo cliente que já existe: ler um arquivo, buscar no código,
ler o `CONTEXT.md` ou uma ADR aceita e listar as issues abertas. Há um teto de
consultas por turno e de tamanho por arquivo; ao bater o teto, o turno segue com
o que tem. Tudo pela ROTA, com o modelo e o adapter do GitHub falsificados.
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_planejamento_demanda import _ia, _pergunta  # noqa: E402
from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _chamadas,
    _conversas,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import BASE  # noqa: E402

from app.config import settings  # noqa: E402
from app.services import github_client  # noqa: E402
from app.services.conhecimento import CONHECIMENTO_DIR  # noqa: E402

CHAT = f"{BASE}/chat"

ARQUIVO_DA_OUVIDORIA = "hospital-reunioes/frontend/src/app/ouvidoria/page.tsx"


def _uso(entrada: int = 100, saida: int = 10, lidos: int = 0, escritos: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=entrada,
        output_tokens=saida,
        cache_read_input_tokens=lidos,
        cache_creation_input_tokens=escritos,
    )


class _ModeloQueConsulta:
    """A Anthropic de mentira, com ferramentas: cada rodada é a lista de
    consultas que o modelo pede; depois delas, ou quando o pedido proíbe
    ferramenta (`tool_choice` none, como a API de verdade obedece), vem o
    texto final."""

    def __init__(self, rodadas: list[list[tuple[str, dict]]], final: str, usos: list | None = None):
        self.rodadas = rodadas
        self.final = final
        self.usos = usos or []
        self.chamadas: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        i = len(self.chamadas) - 1
        uso = self.usos[i] if i < len(self.usos) else _uso()
        proibiu = (kwargs.get("tool_choice") or {}).get("type") == "none"
        if proibiu or i >= len(self.rodadas):
            return SimpleNamespace(
                content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.final)],
                stop_reason="end_turn",
                usage=uso,
            )
        blocos = [
            SimpleNamespace(type="tool_use", id=f"consulta-{i}-{j}", name=nome, input=entrada)
            for j, (nome, entrada) in enumerate(self.rodadas[i])
        ]
        return SimpleNamespace(content=blocos, stop_reason="tool_use", usage=uso)


def _modelo(monkeypatch, rodadas, final: str, **kw) -> _ModeloQueConsulta:
    from app.services import ai_processor

    cliente = _ModeloQueConsulta(rodadas, final, **kw)
    monkeypatch.setattr(ai_processor, "_llm_provider", lambda: "anthropic")
    monkeypatch.setattr(ai_processor, "_get_llm", lambda: (cliente, "modelo-do-resto-do-app"))
    return cliente


class _RepositorioFalso:
    """O adapter do GitHub como o teste o quer: arquivos por caminho, pastas,
    resultados de busca e issues abertas, e o registro do que foi lido."""

    def __init__(self, *, arquivos=None, busca=None, issues=None):
        self.arquivos: dict[str, str] = arquivos or {}
        self.busca: list[str] = busca or []
        self.issues: list[dict] = issues or []
        self.lidos: list[str] = []
        self.buscas: list[str] = []

    def ler_do_repositorio(self, caminho: str):
        self.lidos.append(caminho)
        if caminho in self.arquivos:
            return self.arquivos[caminho]
        dentro = sorted({c[len(caminho) + 1 :].split("/")[0] for c in self.arquivos if c.startswith(f"{caminho}/")})
        if dentro:
            return dentro
        raise github_client.IssueNaoEncontradaError(caminho)

    def buscar_no_codigo(self, termo: str) -> list[str]:
        self.buscas.append(termo)
        return list(self.busca)

    def listar_issues_abertas(self) -> list[dict]:
        return [dict(i) for i in self.issues]


def _repositorio(monkeypatch, **kw) -> _RepositorioFalso:
    repo = _RepositorioFalso(**kw)
    monkeypatch.setattr(github_client, "ler_do_repositorio", repo.ler_do_repositorio)
    monkeypatch.setattr(github_client, "buscar_no_codigo", repo.buscar_no_codigo)
    monkeypatch.setattr(github_client, "listar_issues_abertas", repo.listar_issues_abertas)
    return repo


def _resultados(chamada: dict) -> list[dict]:
    """Os resultados de consulta que o turno devolveu ao modelo nesta chamada."""
    ultima = chamada["messages"][-1]
    assert ultima["role"] == "user"
    return [b for b in ultima["content"] if b.get("type") == "tool_result"]


# ═══════════════════════════════════════════════════════════════════════════
# 1. As quatro ferramentas, pelo adapter do GitHub
# ═══════════════════════════════════════════════════════════════════════════


class TestAsQuatroFerramentas:
    def test_o_modelo_recebe_as_quatro_ferramentas_e_o_turno_le_o_arquivo_pelo_adapter(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        repo = _repositorio(monkeypatch, arquivos={ARQUIVO_DA_OUVIDORIA: "export function Responder() {}"})
        modelo = _modelo(monkeypatch, [[("ler_arquivo", {"caminho": ARQUIVO_DA_OUVIDORIA})]], _turno())

        resposta = client.post(CHAT, json={"escolha": "bug"})

        assert resposta.status_code == 201, resposta.text
        assert sorted(f["name"] for f in modelo.chamadas[0]["tools"]) == [
            "buscar_no_codigo",
            "ler_arquivo",
            "ler_contexto_ou_adr",
            "listar_issues_abertas",
        ]
        assert repo.lidos == [ARQUIVO_DA_OUVIDORIA]
        [resultado] = _resultados(modelo.chamadas[1])
        assert resultado["tool_use_id"] == "consulta-0-0"
        assert "export function Responder() {}" in resultado["content"]
        assert resposta.json()["mensagens"][-1]["texto"] == "Onde isso aconteceu?"

    def test_buscar_ler_o_contexto_e_a_adr_aceita_chegam_ao_modelo(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        repo = _repositorio(
            monkeypatch,
            arquivos={
                "CONTEXT.md": "Demanda: o registro de cada conversa.",
                "docs/adr/0077-tecnologia-vira-o-chat.md": "---\nstatus: accepted\n---\n# O chat do agente",
                "docs/adr/0075-planejamento.md": "---\nstatus: superseded\n---\n# O planejamento antigo",
            },
            busca=["hospital-reunioes/backend/app/services/chat_tecnologia.py"],
        )
        modelo = _modelo(
            monkeypatch,
            [
                [
                    ("buscar_no_codigo", {"termo": "Roteiro do bug"}),
                    ("ler_contexto_ou_adr", {}),
                    ("ler_contexto_ou_adr", {"adr": 77}),
                    ("ler_contexto_ou_adr", {"adr": 75}),
                ]
            ],
            _turno(),
        )

        assert client.post(CHAT, json={"escolha": "bug"}).status_code == 201

        assert repo.buscas == ["Roteiro do bug"]
        busca, contexto, aceita, superada = (r["content"] for r in _resultados(modelo.chamadas[1]))
        assert "chat_tecnologia.py" in busca
        assert "Demanda: o registro de cada conversa." in contexto
        assert "# O chat do agente" in aceita
        # A ADR que não está aceita não vale como decisão da casa.
        assert "# O planejamento antigo" not in superada

    def test_o_github_fora_do_ar_nao_derruba_o_turno(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        repo = _repositorio(monkeypatch)

        def _fora(_caminho):
            raise github_client.GithubIndisponivelError("timeout")

        monkeypatch.setattr(github_client, "ler_do_repositorio", _fora)
        modelo = _modelo(monkeypatch, [[("ler_arquivo", {"caminho": "CONTEXT.md"})]], _turno())

        resposta = client.post(CHAT, json={"escolha": "bug"})

        assert resposta.status_code == 201, resposta.text
        [resultado] = _resultados(modelo.chamadas[1])
        assert resultado["is_error"] is True
        assert repo.lidos == []

    def test_sem_a_integracao_do_github_o_turno_roda_sem_ferramentas(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        monkeypatch.setattr(settings, "github_integracao_token", "")
        modelo = _modelo(monkeypatch, [], _turno())

        assert client.post(CHAT, json={"escolha": "bug"}).status_code == 201

        assert "tools" not in modelo.chamadas[0]


# ═══════════════════════════════════════════════════════════════════════════
# 2. Os tetos: consultas por turno e tamanho por arquivo
# ═══════════════════════════════════════════════════════════════════════════


class TestOsTetos:
    def test_o_turno_para_de_consultar_no_teto_e_responde_com_o_que_tem(self, monkeypatch):
        """O modelo quer consultar vinte vezes; o turno executa oito, e a
        rodada seguinte vai sem ferramenta, para ele responder."""
        client, _, _ = _cenario(monkeypatch)
        repo = _repositorio(monkeypatch, arquivos={"CONTEXT.md": "glossário"})
        modelo = _modelo(monkeypatch, [[("ler_arquivo", {"caminho": "CONTEXT.md"})]] * 20, _turno())

        resposta = client.post(CHAT, json={"escolha": "bug"})

        assert resposta.status_code == 201, resposta.text
        assert len(repo.lidos) == 8
        assert modelo.chamadas[-1]["tool_choice"] == {"type": "none"}
        assert resposta.json()["mensagens"][-1]["texto"] == "Onde isso aconteceu?"

    def test_o_arquivo_grande_chega_cortado_ao_modelo(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        _repositorio(monkeypatch, arquivos={ARQUIVO_DA_OUVIDORIA: "x" * 50_000})
        modelo = _modelo(monkeypatch, [[("ler_arquivo", {"caminho": ARQUIVO_DA_OUVIDORIA})]], _turno())

        assert client.post(CHAT, json={"escolha": "bug"}).status_code == 201

        [resultado] = _resultados(modelo.chamadas[1])
        assert resultado["content"].count("x") == 20_000
        assert "(arquivo cortado em 20000 caracteres)" in resultado["content"]


# ═══════════════════════════════════════════════════════════════════════════
# 3. Nenhuma ferramenta escreve no repositório
# ═══════════════════════════════════════════════════════════════════════════


def _em_base64(texto: str) -> dict:
    return {"encoding": "base64", "content": base64.b64encode(texto.encode()).decode()}


class _TransporteDoGithub:
    """O `httpx.request` do adapter, gravando método e URL de cada chamada:
    a prova de que nenhuma ferramenta escreve é o que sai pelo fio."""

    RESPOSTAS = {
        "/contents/CONTEXT.md?ref=main": _em_base64("glossário"),
        "/contents/docs/adr?ref=main": [{"name": "0077-o-chat.md"}],
        "/contents/docs/adr/0077-o-chat.md?ref=main": _em_base64("---\nstatus: accepted\n---\n# ADR"),
        "/contents/hospital-reunioes/README.md?ref=main": _em_base64("leia-me"),
        "/issues?state=open&per_page=100": [{"number": 42, "title": "Aviso da ata"}],
    }

    def __init__(self):
        self.pedidos: list[tuple[str, str]] = []

    def __call__(self, metodo, url, **_kw):
        self.pedidos.append((metodo, url))
        caminho = url.split("/repos/pedrorezendefig/hospital-reunioes", 1)[-1]
        if caminho.startswith("https://api.github.com/search/code"):
            dados = {"items": [{"path": "hospital-reunioes/README.md"}]}
        else:
            dados = self.RESPOSTAS[caminho]
        return SimpleNamespace(status_code=200, json=lambda: dados)


class TestNenhumaFerramentaEscreve:
    def test_as_quatro_ferramentas_so_fazem_get_no_github(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        transporte = _TransporteDoGithub()
        monkeypatch.setattr(github_client.httpx, "request", transporte)
        _modelo(
            monkeypatch,
            [
                [
                    ("ler_arquivo", {"caminho": "hospital-reunioes/README.md"}),
                    ("buscar_no_codigo", {"termo": "Roteiro"}),
                    ("ler_contexto_ou_adr", {}),
                    ("ler_contexto_ou_adr", {"adr": 77}),
                    ("listar_issues_abertas", {}),
                ]
            ],
            _turno(),
        )

        assert client.post(CHAT, json={"escolha": "bug"}).status_code == 201

        assert len(transporte.pedidos) == 6
        assert {metodo for metodo, _ in transporte.pedidos} == {"GET"}


# ═══════════════════════════════════════════════════════════════════════════
# 4. O custo gravado soma as rodadas de ferramenta
# ═══════════════════════════════════════════════════════════════════════════


class TestCusto:
    def test_o_custo_gravado_soma_as_rodadas_de_consulta(self, monkeypatch):
        client, sb, _ = _cenario(monkeypatch)
        monkeypatch.setattr(settings, "llm_model_planejamento", "claude-opus-5-5")
        _repositorio(monkeypatch, arquivos={"CONTEXT.md": "glossário"})
        _modelo(
            monkeypatch,
            [[("ler_arquivo", {"caminho": "CONTEXT.md"})]],
            _turno(),
            usos=[_uso(entrada=1000, saida=100), _uso(entrada=2000, saida=300)],
        )

        assert client.post(CHAT, json={"escolha": "bug"}).status_code == 201

        [chamada] = _chamadas(sb)
        assert chamada["tokens_entrada"] == 3000
        assert chamada["tokens_saida"] == 400
        # Opus 5.5: 3000 x US$ 4 + 400 x US$ 20, por milhão.
        assert chamada["custo_usd"] == 0.02


# ═══════════════════════════════════════════════════════════════════════════
# 5. Com uma issue aberta parecida, o agente avisa antes de criar o card
# ═══════════════════════════════════════════════════════════════════════════

PARECIDA = {"numero": 1290, "titulo": "Responder manifestação direto da lista da Ouvidoria"}
OUTRA = {"numero": 1301, "titulo": "Exportar a ata em Word"}

RESUMO_PRONTO = {
    "pronto": True,
    "mensagem": "Montei o resumo. Confira.",
    "campos": {"onde": "Ouvidoria", "o_que_aconteceu": "O botão sumiu", "o_que_esperava": "Ver o botão"},
}


def _bug_no_resumo(client, monkeypatch, *, parecida) -> dict:
    _ia(monkeypatch, _turno())
    demanda_id = client.post(CHAT, json={"escolha": "bug"}).json()["demanda_id"]
    _modelo(monkeypatch, [[("listar_issues_abertas", {})]], _turno(**RESUMO_PRONTO, parecida=parecida))
    resposta = client.post(f"{CHAT}/{demanda_id}", json={"texto": "O botão de responder sumiu"})
    assert resposta.status_code == 200, resposta.text
    return resposta.json()


class TestAPedidoParecido:
    def test_no_bug_o_agente_avisa_do_pedido_aberto_parecido_pelo_titulo(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        _repositorio(monkeypatch, issues=[OUTRA, PARECIDA])

        corpo = _bug_no_resumo(client, monkeypatch, parecida=1290)

        assert corpo["estado"] == "resumido"
        fala = corpo["mensagens"][-1]["texto"]
        assert fala.startswith("Montei o resumo. Confira.")
        assert f'"{PARECIDA["titulo"]}"' in fala
        # Com o diretor, sem número de issue.
        assert "1290" not in fala

    def test_numero_que_o_modelo_nao_viu_na_lista_nao_vira_aviso(self, monkeypatch):
        client, _, _ = _cenario(monkeypatch)
        _repositorio(monkeypatch, issues=[OUTRA])

        corpo = _bug_no_resumo(client, monkeypatch, parecida=1290)

        assert corpo["mensagens"][-1]["texto"] == "Montei o resumo. Confira."

    def test_na_melhoria_o_aviso_vem_com_o_resumo_antes_do_criar_o_card(self, monkeypatch):
        client, sb, gh = _cenario(monkeypatch)
        _repositorio(monkeypatch, issues=[PARECIDA])
        _ia(monkeypatch, _pergunta())
        demanda_id = client.post(CHAT, json={"escolha": "melhoria"}).json()["demanda_id"]
        _ia(monkeypatch, _pergunta(contexto="E quem confirma?"))
        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})
        _modelo(monkeypatch, [[("listar_issues_abertas", {})]], _resumo_da_melhoria(parecida=1290))

        resposta = client.post(f"{CHAT}/{demanda_id}/resumo")

        assert resposta.status_code == 200, resposta.text
        corpo = resposta.json()
        assert corpo["estado"] == "resumido"
        fala = corpo["mensagens"][-1]
        assert fala["autor"] == "ia"
        assert f'"{PARECIDA["titulo"]}"' in fala["texto"]
        assert gh.criadas == []
        # O "Não bateu" depois do aviso: o planejamento lê a fala da IA como fala.
        client.post(f"{CHAT}/{demanda_id}/nao-bateu", json={"texto": "Não é o mesmo pedido."})
        cliente = _ia(monkeypatch, _pergunta(contexto="Então o que muda?"))
        assert client.post(f"{CHAT}/{demanda_id}", json={}).status_code == 200
        assert "IA: Antes de criar o card" in cliente.chamadas[0]["messages"][0]["content"]
        assert len(_conversas(sb)) == 1


def _resumo_da_melhoria(**campos) -> str:
    base = {
        "titulo": "Responder direto da lista",
        "decisoes": [{"pergunta": 1, "porque": "A recepção responde."}],
        "em_aberto": [],
        "termos": [],
        "candidatas_a_adr": [],
        "decisoes_de_implementacao": [],
        "decisoes_de_teste": [],
        "parecida": None,
    }
    base.update(campos)
    return json.dumps(base, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════
# 6. O card de melhoria traz as Decisões de implementação e de teste
# ═══════════════════════════════════════════════════════════════════════════


class TestOCardDaMelhoria:
    def test_o_prd_do_diretor_leva_as_decisoes_lidas_do_codigo(self, monkeypatch):
        client, _, gh = _cenario(monkeypatch)
        _repositorio(monkeypatch, arquivos={ARQUIVO_DA_OUVIDORIA: "export function Lista() {}"})
        _ia(monkeypatch, _pergunta())
        demanda_id = client.post(CHAT, json={"escolha": "melhoria"}).json()["demanda_id"]
        _ia(monkeypatch, _pergunta(contexto="E quem confirma?"))
        client.post(f"{CHAT}/{demanda_id}", json={"opcao": "A"})
        _modelo(
            monkeypatch,
            [[("ler_arquivo", {"caminho": ARQUIVO_DA_OUVIDORIA})]],
            _resumo_da_melhoria(
                decisoes_de_implementacao=["A lista da Ouvidoria ganha o botão Responder em cada linha."],
                decisoes_de_teste=["Teste de rota: responder pela lista grava a resposta da manifestação."],
            ),
        )
        assert client.post(f"{CHAT}/{demanda_id}/resumo").status_code == 200

        assert client.post(f"{CHAT}/{demanda_id}/criar-card").status_code == 200

        corpo = gh.criadas[0]["corpo"]
        cabecalhos = re.findall(r"^## (.+)$", corpo, re.MULTILINE)
        assert cabecalhos[cabecalhos.index("Decisões de negócio") + 1 :][:2] == [
            "Decisões de implementação",
            "Decisões de teste",
        ]
        implementacao = corpo.split("## Decisões de implementação", 1)[1].split("\n## ", 1)[0]
        teste = corpo.split("## Decisões de teste", 1)[1].split("\n## ", 1)[0]
        assert "- A lista da Ouvidoria ganha o botão Responder em cada linha." in implementacao
        assert "- Teste de rota: responder pela lista grava a resposta da manifestação." in teste


# ═══════════════════════════════════════════════════════════════════════════
# 7. O Kit de conhecimento diz o comportamento novo
# ═══════════════════════════════════════════════════════════════════════════


class TestKitDaTecnologia:
    def test_o_texto_da_tecnologia_no_kit_diz_que_a_ia_consulta_a_plataforma_e_avisa_do_parecido(self):
        texto = (CONHECIMENTO_DIR / "tecnologia.md").read_text(encoding="utf-8")

        secao = texto.split("## A conversa com o Assistente", 1)[1].split("\n## ", 1)[0]
        for trecho in ("consulta o que já existe na plataforma", "pedido aberto parecido", "como fazer e como testar"):
            assert trecho in secao, trecho
