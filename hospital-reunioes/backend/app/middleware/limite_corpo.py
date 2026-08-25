"""Teto de tamanho do corpo de requisição, para o app inteiro (issue #349).

Sem isto, qualquer POST era lido inteiro para a memória antes de o pydantic
dizer não. O teto vive no app, e não só no proxy, porque o rewrite interno do
Next chega ao backend sem passar pelo Traefik.

O valor default fica acima do maior upload legítimo do app (o áudio de 25 MB
da transcrição); os limites finos, por tipo de arquivo, continuam nas rotas.
"""

from __future__ import annotations

import json

LIMITE_CORPO_BYTES = 30 * 1024 * 1024

_DETALHE = "Corpo da requisição acima do limite de {mb} MB."


class _CorpoAcimaDoTetoError(Exception):
    pass


class LimiteDeCorpoMiddleware:
    """ASGI puro: recusa pelo Content-Length quando ele existe e, quando não
    existe (corpo em pedaços), conta os bytes e corta ao passar do teto."""

    def __init__(self, app, limite_bytes: int = LIMITE_CORPO_BYTES):
        self.app = app
        self.limite_bytes = limite_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.limite_bytes:
                    await self._recusar(send)
                    return
            except ValueError:
                # Content-Length ilegível: o servidor HTTP recusa antes de nós;
                # se chegou aqui, quem decide é a contagem real abaixo.
                pass

        recebido = 0
        resposta_comecou = False

        async def receber_contando():
            nonlocal recebido
            mensagem = await receive()
            if mensagem["type"] == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > self.limite_bytes:
                    raise _CorpoAcimaDoTetoError
            return mensagem

        async def enviar_marcando(mensagem):
            nonlocal resposta_comecou
            if mensagem["type"] == "http.response.start":
                resposta_comecou = True
            await send(mensagem)

        try:
            await self.app(scope, receber_contando, enviar_marcando)
        except _CorpoAcimaDoTetoError:
            # O corpo estoura durante o parse, antes de qualquer resposta; se
            # por alguma rota a resposta já começou, só resta interromper.
            if resposta_comecou:
                raise
            await self._recusar(send)

    async def _recusar(self, send):
        corpo = json.dumps(
            {"detail": _DETALHE.format(mb=self.limite_bytes // (1024 * 1024))},
            ensure_ascii=False,
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(corpo)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": corpo})
