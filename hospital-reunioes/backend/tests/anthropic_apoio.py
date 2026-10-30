"""A API da Anthropic de mentira, para os testes da IA de texto (issue #1302).

Dois jeitos de trocar a IA, conforme o que o teste precisa ler:

- `cliente_por_transporte(duble)`: o SDK `anthropic` de verdade, com só o
  transporte HTTP trocado (`httpx2.MockTransport`). O `duble` recebe o
  `httpx2.Request` e devolve um `httpx2.Response`; o teste lê o corpo JSON que
  sairia para a Anthropic. É o que os testes de Contas médicas usam.
- `ClienteFalso(texto)`: um objeto com `.messages.create(**kwargs)` que guarda
  os argumentos e devolve uma mensagem com o texto dado. É o que os testes dos
  chats (`ai_processor`, Assistente de Tecnologia) usam no lugar do `_get_llm`.

Nenhum dos dois chega à rede, e a trava da suíte (`conftest.py`) reprova quem
tentar.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2

MODELO = "claude-sonnet-5-5"


def uso(entrada: int = 1000, saida: int = 200, leitura_cache: int = 0, escrita_cache: int = 0) -> dict:
    """O `usage` da resposta da Anthropic: entrada sem cache, saída, leitura e
    escrita de cache, cada uma no seu campo."""
    return {
        "input_tokens": entrada,
        "output_tokens": saida,
        "cache_read_input_tokens": leitura_cache,
        "cache_creation_input_tokens": escrita_cache,
    }


def mensagem(texto: str, uso_da_resposta: dict | None = None, *, modelo: str = MODELO, numero: int = 1) -> dict:
    """O corpo JSON de uma resposta de `POST /v1/messages` com um bloco de texto."""
    return {
        "id": f"msg_{numero}",
        "type": "message",
        "role": "assistant",
        "model": modelo,
        "content": [{"type": "text", "text": texto}],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": uso_da_resposta or uso(),
    }


def erro(status: int, tipo: str, mensagem_do_erro: str) -> httpx2.Response:
    """A resposta de erro da API, no formato `{"type": "error", "error": {...}}`."""
    return httpx2.Response(status, json={"type": "error", "error": {"type": tipo, "message": mensagem_do_erro}})


def cliente_por_transporte(duble) -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key="chave-de-teste",
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(duble)),
        max_retries=0,
    )


def nomear_schemas(monkeypatch) -> dict[str, str]:
    """O nome do modelo Pydantic de cada schema que o adaptador de Contas
    médicas manda. A saída estruturada da Anthropic não leva nome (o OpenRouter
    levava), e os dublês respondem conforme o schema pedido: este registro
    devolve, pelo schema serializado, o nome da classe que o gerou. Use com
    `nome_do_schema(nomes, corpo)`."""
    from app.services.contas_medicas import ia

    nomes: dict[str, str] = {}
    original = ia._schema_estrito

    def gravar(modelo):
        schema = original(modelo)
        nomes[json.dumps(schema, sort_keys=True)] = modelo.__name__
        return schema

    monkeypatch.setattr(ia, "_schema_estrito", gravar)
    return nomes


def nome_do_schema(nomes: dict[str, str], corpo: dict) -> str:
    return nomes[json.dumps(corpo["output_config"]["format"]["schema"], sort_keys=True)]


class ClienteFalso:
    """`.messages.create(**kwargs)` que guarda a chamada e devolve `texto`.
    `texto` pode ser uma exceção, que a chamada levanta."""

    def __init__(self, texto: str | BaseException = "{}"):
        self.texto = texto
        self.chamadas: list[dict[str, Any]] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        if isinstance(self.texto, BaseException):
            raise self.texto
        return resposta_de_texto(self.texto)


def resposta_de_texto(texto: str, stop_reason: str = "end_turn"):
    """A mensagem já como objeto, com o mesmo formato que o SDK devolve."""
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=texto)],
        stop_reason=stop_reason,
        usage=SimpleNamespace(**uso()),
    )
