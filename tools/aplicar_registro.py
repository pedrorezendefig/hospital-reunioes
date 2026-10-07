#!/usr/bin/env python3
"""O registro do deploy na `main` pela Action pós-merge (ADR 0064, decisão 6b; issue #1000).

O `fechar_onda.py` termina no health e dispara o `pos-merge.yml` na `main` com o
registro no input `registro`: `{"entrada": <a entrada nova do history.json>,
"state": <o state.json inteiro>}`. O job `gerar` roda este script antes do draft
do Manual e do snapshot, que leem a versão nova no `history.json`. O input chega
pela variável `REGISTRO`, nunca interpolado no `run` do YAML.

A entrada vai para o topo de `deploys` (o mais novo primeiro, como o rabo sempre
gravou) e as antigas ficam como estão; o `state.json` passa a ser o do registro.
Registro fora do esquema sai com 1 sem escrever nada: o passo do draft põe os
`prds` e a `app_version` da entrada no `GITHUB_OUTPUT`. O `commitar` confere de
novo que os dois arquivos são exatamente o que o registro diz.

Saída: 0 aplicado, ou a entrada já estava no history.json; 1 registro recusado.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

HISTORY = Path("docs/spec/deploy/history.json")
STATE = Path("docs/spec/deploy/state.json")

SHA = re.compile(r"[0-9a-f]{40}")
VERSAO = re.compile(r"\d+\.\d+\.\d+")
ID = re.compile(r"[a-z][a-z0-9_-]*")
CHAVE_DE_ENV = re.compile(r"[A-Z][A-Z0-9_]*")
MIGRATION = re.compile(r"\d+_[A-Za-z0-9_.-]+\.sql")
LOGIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*")  # login do GitHub de quem rodou o rabo
CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


class RegistroRecusado(Exception):
    pass


def _texto(v) -> bool:
    return isinstance(v, str) and not CONTROLE.search(v)


def _casa(regex: re.Pattern):
    return lambda v: isinstance(v, str) and regex.fullmatch(v) is not None


def _lista(teste):
    return lambda v: isinstance(v, list) and all(teste(x) for x in v)


def _inteiro(v) -> bool:
    return type(v) is int and v >= 0


def _prd(v) -> bool:
    return type(v) is int and v > 0


def _data(v) -> bool:
    if not isinstance(v, str):
        return False
    try:
        return datetime.fromisoformat(v).tzinfo is not None
    except ValueError:
        return False


def _mudanca_de_env(v) -> bool:
    return (isinstance(v, dict) and set(v) == {"service", "action", "keys"} and _casa(ID)(v["service"])
            and _casa(ID)(v["action"]) and _lista(_casa(CHAVE_DE_ENV))(v["keys"]))


def _etapas(v) -> bool:
    """O que o rabo mediu: merge e health em segundos, build por app (None para o
    app sem build, como o backend em modo imagem)."""
    return (isinstance(v, dict) and set(v) == {"merge_s", "build_s", "health_s"}
            and _inteiro(v["merge_s"]) and _inteiro(v["health_s"]) and isinstance(v["build_s"], dict)
            and all(_casa(ID)(k) and (x is None or _inteiro(x)) for k, x in v["build_s"].items()))


# Os campos que o `montar_registro` do rabo grava, nem um a mais. As entradas
# antigas do history.json não têm `etapas` nem `responsavel`: o esquema vale
# para a entrada nova, nunca para o arquivo inteiro.
ENTRADA = {
    "at": _data,
    "sha": _casa(SHA),
    "app_version": _casa(VERSAO),
    "subject": _texto,
    "raw_subject": _texto,
    "scope": _lista(_casa(ID)),
    "prds": _lista(_prd),
    "result": _casa(ID),
    "duration_seconds": _inteiro,
    "services_touched": _lista(_casa(ID)),
    "env_changes": _lista(_mudanca_de_env),
    "migrations_applied": _lista(_casa(MIGRATION)),
    "rollback_target_sha": lambda v: v is None or _casa(SHA)(v),
    "notes": _texto,
    "etapas": _etapas,
    "responsavel": _casa(LOGIN),
}
# O que o rabo muda no state.json, além dos serviços: o resto vem da main.
DO_RABO = {"updated_at", "updated_by", "last_app_version", "last_run"}


def validar_entrada(entrada) -> dict:
    if not isinstance(entrada, dict):
        raise RegistroRecusado("a entrada não é um objeto")
    if set(entrada) != set(ENTRADA):
        faltam, sobram = sorted(set(ENTRADA) - set(entrada)), sorted(set(entrada) - set(ENTRADA))
        raise RegistroRecusado(f"campos da entrada: faltam {json.dumps(faltam)}, sobram {json.dumps(sobram)}")
    ruins = [campo for campo, valido in ENTRADA.items() if not valido(entrada[campo])]
    if ruins:
        raise RegistroRecusado(f"campos da entrada fora do esquema: {json.dumps(ruins)}")
    return entrada


def _ids(state: dict) -> list:
    return [s.get("id") if isinstance(s, dict) else None for s in state.get("services") or []]


def validar_state(state, atual: dict, entrada: dict) -> dict:
    """O state.json do registro tem as chaves do da main (menos `next_actions`,
    que o rabo apaga) mais as que o rabo grava, os mesmos serviços na mesma
    ordem, e bate com a entrada."""
    if not isinstance(state, dict):
        raise RegistroRecusado("o state não é um objeto")
    if set(state) != (set(atual) - {"next_actions"}) | DO_RABO:
        raise RegistroRecusado("as chaves do state não são as do state.json da main")
    if not isinstance(state.get("services"), list) or _ids(state) != _ids(atual):
        raise RegistroRecusado("os serviços do state não são os do state.json da main")
    run = state["last_run"]
    if (state["last_app_version"] != entrada["app_version"] or state["updated_at"] != entrada["at"]
            or not _texto(state["updated_by"]) or not isinstance(run, dict) or run.get("sha") != entrada["sha"]):
        raise RegistroRecusado("o state não bate com a entrada (versão, data ou sha)")
    return state


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _escrever(caminho: Path, dado) -> None:
    # o mesmo formato do `escrever_json` do rabo: o diff do history.json é só a entrada nova
    caminho.write_text(json.dumps(dado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def aplicar(valor: str, raiz: Path) -> bool:
    """Valida o registro e grava os dois arquivos. Devolve False se a entrada já
    estava no history.json (o rabo disparou de novo um run que já tinha entrado)."""
    try:
        registro = json.loads(valor)
    except json.JSONDecodeError as e:
        raise RegistroRecusado(f"o registro não é JSON ({e.msg})") from e
    if not isinstance(registro, dict) or set(registro) != {"entrada", "state"}:
        raise RegistroRecusado('o registro é um objeto só com "entrada" e "state"')
    history, atual = _ler(raiz / HISTORY), _ler(raiz / STATE)
    entrada = validar_entrada(registro["entrada"])
    state = validar_state(registro["state"], atual, entrada)
    if entrada in history["deploys"]:
        return False
    history["deploys"] = [entrada, *history["deploys"]]
    _escrever(raiz / HISTORY, history)
    _escrever(raiz / STATE, state)
    return True


def main() -> int:
    try:
        novo = aplicar(os.environ.get("REGISTRO", ""), Path.cwd())
    except RegistroRecusado as e:
        print(f"::error::Registro do deploy recusado: {e}.")
        return 1
    print("Registro do deploy aplicado ao history.json e ao state.json." if novo
          else "A entrada do registro já está no history.json: nada a aplicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
