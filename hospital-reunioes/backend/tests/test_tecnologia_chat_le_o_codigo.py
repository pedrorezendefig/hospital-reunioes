"""O agente da Tecnologia lê o código (issue #1385, PRD #1380, ADR 0077, decisão 5).

O chat ganha quatro ferramentas só de leitura sobre o repositório público, pela
API do GitHub e pelo cliente que já existe: ler um arquivo, buscar no código,
ler o `CONTEXT.md` ou uma ADR aceita e listar as issues abertas. Há um teto de
consultas por turno e de tamanho por arquivo; ao bater o teto, o turno segue com
o que tem. Tudo pela ROTA, com o modelo e o adapter do GitHub falsificados.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from test_tecnologia_chat import (  # noqa: E402
    _cenario,
    _integracao_configurada,  # noqa: F401
    _llm_em_mock,  # noqa: F401
    _reset_rate_limiter,  # noqa: F401
    _turno,
)
from test_tecnologia_vinculo import BASE  # noqa: E402

from app.services import github_client  # noqa: E402

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
