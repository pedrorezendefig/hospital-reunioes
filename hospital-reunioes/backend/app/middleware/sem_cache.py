"""`Cache-Control: no-store` nas respostas que carregam dossiê (issue #344).

As rotas da Ouvidoria devolvem protocolo, setor e resumo do relato, e o painel
em tempo real repete o par de leituras de minuto em minuto. Sem cabeçalho e sem
validador, o que garante hoje que nada disso fica guardado no caminho é
comportamento de terceiro (navegador que não reaproveita resposta sem validador,
cache compartilhado que não guarda requisição com `Authorization`), e não
decisão deste código: basta um proxy no caminho para virar outra coisa.

O canal público entra junto de propósito. O formulário aberto carrega o relato
que a pessoa acabou de escrever e o protocolo devolvido, e é o caminho que mais
atravessa rede que não é nossa.
"""

from __future__ import annotations

# Os prefixos, já com o prefixo da API. Fechado numa lista em vez de aplicar ao
# app inteiro: teto de cache é decisão por área, e apagar cache de tudo tiraria
# do resto do app uma escolha que ele nunca fez.
#
# O portal do setor está listado à parte de propósito. Ele cairia aqui de
# qualquer jeito, porque "/api/ouvidoria-setor" começa com "/api/ouvidoria",
# mas por acidente de nome: escrito assim, a cobertura dele é decisão. E ele
# precisa dela: a página que o gestor abre pelo link do email carrega a demanda
# e a resposta da área, e atravessa rede que não é nossa.
PREFIXOS_SEM_CACHE = ("/api/ouvidoria", "/api/ouvidoria-setor")

_VALOR = b"no-store"


class SemCacheMiddleware:
    """ASGI puro, como o teto de corpo (issue #349): carimba o cabeçalho na
    resposta que sai das rotas da Ouvidoria, inclusive nas de erro."""

    def __init__(self, app, prefixos: tuple[str, ...] = PREFIXOS_SEM_CACHE):
        self.app = app
        self.prefixos = prefixos

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith(self.prefixos):
            await self.app(scope, receive, send)
            return

        async def enviar_sem_cache(mensagem):
            if mensagem["type"] == "http.response.start":
                # Sem duplicar: se a rota já decidiu o próprio cabeçalho, a
                # decisão dela vale, e este middleware não briga com ela.
                cabecalhos = [(nome, valor) for nome, valor in mensagem.get("headers") or []]
                if not any(nome.lower() == b"cache-control" for nome, _ in cabecalhos):
                    cabecalhos.append((b"cache-control", _VALOR))
                mensagem = {**mensagem, "headers": cabecalhos}
            await send(mensagem)

        await self.app(scope, receive, enviar_sem_cache)
