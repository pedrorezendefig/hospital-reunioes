"""Lê as rotas do app FastAPI já montado e imprime JSON no stdout.

Roda dentro do venv do backend (chamado pelo snapshot.py, nunca direto): o
parser AST do snapshot só enxerga `@router.get("/literal")`, então rotas
criadas por factory (path em f-string, como as de taxonomia.py e
dados_atendimento.py) ficavam fora do ROTAS.md. O app montado já resolveu
todas elas, e traz de brinde as dependencies reais (as do router e as do
decorator, não só as da assinatura do handler).

Quem enumera é o schema OpenAPI, não `app.routes` (issue #542). Desde o
FastAPI 0.141 o `include_router` guarda o router incluído em vez de copiar as
rotas para cima, e varrer `app.routes` volta sem rota nenhuma de router: 192
viram 0. Não dá erro, dá lista vazia, e o snapshot carimbaria um ROTAS.md
mutilado a cada deploy sem ninguém ver. O schema é contrato público e devolve
as mesmas 192 operações nas duas versões.

Uso: python introspect_routes.py [modulo:atributo]   (default app.main:app)
Saída: {"api_prefix": str|null, "routes": [...]} em JSON no stdout.
Qualquer falha sai com código != 0 — quem chama cai no parser estático.
"""

import importlib
import json
import os
import sys

# O helper roda com cwd no diretório do backend; o venv chamado direto (sem
# `uv run`) não põe o cwd no sys.path, e daí `import app` falharia.
sys.path.insert(0, os.getcwd())

# Piso de sanidade da enumeração. A app tem ~190 rotas; qualquer número muito
# abaixo disso é sintoma de enumeração quebrada, não de app encolhido. Sem o
# piso, uma varredura que não acha nada passa calada, que é o modo de falha
# desta base (issue #542). Suba o piso só quando a app crescer de verdade.
PISO_ROTAS = 150

METODOS_HTTP = frozenset({"get", "post", "put", "patch", "delete"})


def _dependency_names(dependant, acc: set[str]) -> set[str]:
    """Nomes de todas as dependencies da rota, recursivamente."""
    for sub in getattr(dependant, "dependencies", []):
        nome = getattr(getattr(sub, "call", None), "__name__", None)
        if nome:
            acc.add(nome)
        _dependency_names(sub, acc)
    return acc


def _api_prefix() -> str | None:
    """Prefixo global da API, para o snapshot manter os paths relativos."""
    try:
        from app.config import settings  # type: ignore[import-not-found]

        prefixo = getattr(settings, "api_prefix", None)
        return prefixo or None
    except Exception:
        return None


def _tem_metadados(rota) -> bool:
    """Filtro por atributo, não por classe. No FastAPI 0.141 o achatamento
    devolve `RouteContext`, que anda como APIRoute mas não herda dele: um
    `isinstance(rota, APIRoute)` descartaria as 192 rotas em silêncio e o
    ROTAS.md sairia com a contagem certa e os metadados zerados."""
    return all(hasattr(rota, attr) for attr in ("path_format", "methods", "name", "endpoint", "dependant"))


def _api_routes_resolvidas(app) -> list:
    """As rotas do app com o path já resolvido, em qualquer versão do FastAPI.

    No <= 0.136 o `include_router` copia as rotas para `app.routes`, e filtrar
    por APIRoute basta. Do 0.141 em diante ele guarda um `_IncludedRouter`, e
    quem achata isso é o `iter_route_contexts`, o mesmo caminho que o
    `get_openapi` usa internamente. Serve só para os metadados (módulo,
    dependencies, docstring); quem enumera é o schema.
    """
    from fastapi import routing
    from fastapi.routing import APIRoute

    iter_contexts = getattr(routing, "iter_route_contexts", None)
    if iter_contexts is None:
        return [r for r in app.routes if isinstance(r, APIRoute)]

    from fastapi.openapi.utils import _get_api_route_for_openapi

    resolvidas = []
    for contexto in iter_contexts(app.routes):
        rota = _get_api_route_for_openapi(contexto)
        if rota is not None and _tem_metadados(rota):
            resolvidas.append(rota)
    return resolvidas


def _indice_por_operacao(app) -> dict[tuple[str, str], object]:
    """(MÉTODO, path) -> APIRoute, para enriquecer o que o schema enumerou."""
    indice: dict[tuple[str, str], object] = {}
    for rota in _api_routes_resolvidas(app):
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            indice[(metodo, rota.path_format)] = rota
    return indice


def _registro_da_rota(metodo: str, caminho: str, rota, operacao: dict) -> dict:
    """Um item do ROTAS.md. Sem a APIRoute casada, cai no que o schema tem:
    fica pobre, mas a rota não some da listagem."""
    if rota is None:
        return {
            "method": metodo,
            "path": caminho,
            "handler": operacao.get("operationId", ""),
            "module": "",
            "tags": [str(t) for t in operacao.get("tags", [])],
            "dependencies": [],
            "desc": (operacao.get("summary") or "")[:120],
        }

    doc = (rota.endpoint.__doc__ or "").strip()
    return {
        "method": metodo,
        "path": caminho,
        # rota.name = __name__ do handler, salvo quando a factory passa
        # name= explícito (aí vem "list_setores" no lugar de "_list").
        "handler": rota.name,
        "module": rota.endpoint.__module__,
        "tags": [str(t) for t in (rota.tags or [])],
        "dependencies": sorted(_dependency_names(rota.dependant, set())),
        "desc": doc.split("\n", 1)[0][:120] if doc else "",
    }


def enumerar_rotas(app) -> list[dict]:
    """Toda rota da app, enumerada pelo schema OpenAPI (ver docstring do módulo).

    Quem enumera é só o schema; o índice de APIRoute entra apenas para
    enriquecer o que ele já achou. Nunca como segunda fonte de enumeração: duas
    fontes se cobrem, e aí quebrar a principal deixa de aparecer em teste
    nenhum. O preço é que rota com `include_in_schema=False` fica de fora, e
    hoje não existe nenhuma (as 192 operações do schema batem com as 192
    APIRoute do app). O teste de paridade é quem vigia isso.
    """
    indice = _indice_por_operacao(app)
    rotas: list[dict] = []

    for caminho, item in app.openapi().get("paths", {}).items():
        for nome_metodo, operacao in item.items():
            if nome_metodo.lower() not in METODOS_HTTP:
                continue
            chave = (nome_metodo.upper(), caminho)
            rotas.append(_registro_da_rota(chave[0], caminho, indice.get(chave), operacao))

    return rotas


def validar_enumeracao(rotas: list[dict]) -> str | None:
    """Motivo pelo qual esta listagem não pode virar ROTAS.md, ou None.

    São dois pisos, porque são dois jeitos de a listagem sair quebrada sem dar
    erro. Contar rota certo e perder os metadados é o pior dos dois: o doc sai
    com o número de endpoints correto, "1 routers" e "0% exigem auth", ou seja,
    afirmando que a aplicação inteira é aberta. Acontece sempre que o índice de
    rotas volta vazio com o schema cheio, e o schema é público demais para
    quebrar junto.
    """
    if len(rotas) < PISO_ROTAS:
        return (
            f"enumeração devolveu {len(rotas)} rotas, abaixo do piso {PISO_ROTAS}: "
            "a listagem está quebrada, não a aplicação."
        )

    com_modulo = sum(1 for r in rotas if r["module"])
    if com_modulo < PISO_ROTAS:
        return (
            f"só {com_modulo} das {len(rotas)} rotas vieram com módulo, abaixo do piso "
            f"{PISO_ROTAS}: o ROTAS.md sairia com a contagem certa, sem router e sem "
            "gate de auth nenhum."
        )

    return None


def main() -> int:
    alvo = sys.argv[1] if len(sys.argv) > 1 else "app.main:app"
    nome_modulo, _, nome_attr = alvo.partition(":")
    app = getattr(importlib.import_module(nome_modulo), nome_attr or "app")

    rotas = enumerar_rotas(app)
    motivo = validar_enumeracao(rotas)
    if motivo is not None:
        print(f"[introspect_routes] {motivo}", file=sys.stderr)
        return 2

    json.dump({"api_prefix": _api_prefix(), "routes": rotas}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
