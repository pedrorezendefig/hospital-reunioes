"""Lê as rotas do app FastAPI já montado e imprime JSON no stdout.

Roda dentro do venv do backend (chamado pelo snapshot.py, nunca direto): o
parser AST do snapshot só enxerga `@router.get("/literal")`, então rotas
criadas por factory (path em f-string, como as de taxonomia.py e
dados_atendimento.py) ficavam fora do ROTAS.md. O app montado já resolveu
todas elas, e traz de brinde as dependencies reais (as do router e as do
decorator, não só as da assinatura do handler).

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


def main() -> int:
    from fastapi.routing import APIRoute

    alvo = sys.argv[1] if len(sys.argv) > 1 else "app.main:app"
    nome_modulo, _, nome_attr = alvo.partition(":")
    app = getattr(importlib.import_module(nome_modulo), nome_attr or "app")

    rotas = []
    for rota in app.routes:
        if not isinstance(rota, APIRoute):
            continue
        doc = (rota.endpoint.__doc__ or "").strip()
        deps = sorted(_dependency_names(rota.dependant, set()))
        for metodo in sorted(rota.methods - {"HEAD", "OPTIONS"}):
            rotas.append({
                "method": metodo,
                "path": rota.path,
                # rota.name = __name__ do handler, salvo quando a factory passa
                # name= explícito (aí vem "list_setores" no lugar de "_list").
                "handler": rota.name,
                "module": rota.endpoint.__module__,
                "tags": [str(t) for t in (rota.tags or [])],
                "dependencies": deps,
                "desc": doc.split("\n", 1)[0][:120] if doc else "",
            })

    json.dump({"api_prefix": _api_prefix(), "routes": rotas}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
