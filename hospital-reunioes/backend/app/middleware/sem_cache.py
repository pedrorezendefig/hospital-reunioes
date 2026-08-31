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

from app.config import settings

# As áreas cobertas, sem o prefixo da API. Fechado numa lista em vez de aplicar
# ao app inteiro: teto de cache é decisão por área, e apagar cache de tudo
# tiraria do resto do app uma escolha que ele nunca fez.
#
# O portal do setor está listado à parte de propósito. Ele cairia aqui de
# qualquer jeito, porque "/ouvidoria-setor" começa com "/ouvidoria", mas por
# acidente de nome: escrito assim, a cobertura dele é decisão. E ele precisa
# dela: a página que o gestor abre pelo link do email carrega a demanda e a
# resposta da área, e atravessa rede que não é nossa.
AREAS_SEM_CACHE = ("/ouvidoria", "/ouvidoria-setor")

_VALOR = b"no-store"


def prefixos_sem_cache() -> tuple[str, ...]:
    """As áreas já com o prefixo da API vigente.

    Derivado de `settings.api_prefix`, e não escrito à mão, porque é com ele
    que o `main` monta todo router: com "/api" cravado aqui, mudar o prefixo
    por env transformava esta peça em no-op silencioso, sem nenhum teste cair
    (issue #439).
    """
    return tuple(f"{settings.api_prefix}{area}" for area in AREAS_SEM_CACHE)


class SemCacheMiddleware:
    """ASGI puro, como o teto de corpo (issue #349): carimba o cabeçalho na
    resposta que sai das rotas da Ouvidoria, inclusive nas de erro tratada.

    "Tratada" é o limite exato, e é decisão registrada (issue #439). O 403 e o
    404 passam por aqui porque saem do `ExceptionMiddleware`, dentro da pilha.
    O 500 sem tratamento, não: o `@app.exception_handler(Exception)` do `main`
    é montado no `ServerErrorMiddleware`, que o Starlette põe fora de todo
    `user_middleware`. Trazê-lo para dentro exigiria embrulhar o app no
    entrypoint do uvicorn, e o corpo desse 500 é a frase genérica do
    `DETALHE_ERRO_GENERICO`, sem protocolo, setor nem resumo. Custo alto para
    nenhum dossiê a mais protegido.
    """

    def __init__(self, app, prefixos: tuple[str, ...] | None = None):
        self.app = app
        self.prefixos = prefixos if prefixos is not None else prefixos_sem_cache()

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
