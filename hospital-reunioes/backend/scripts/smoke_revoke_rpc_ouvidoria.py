"""Fumaça: a anon_key não executa `ouvidoria_ultimo_movimento()` (issue #520).

Quem aplica migration nesta casa é o humano, à mão, no SQL Editor do Studio de
produção. Migration escrita no repositório não é migration aplicada, e foi
exatamente essa distância que deixou o furo da 092 aberto sem ninguém notar.
Este script é o que fecha a conta: rodado contra a produção depois de aplicar a
094, ele diz se a porta fechou de verdade.

Ele bate com a chave ANÔNIMA, a mesma que viaja no bundle do frontend. Duas
armadilhas moram aí, e o script recusa as duas:

* a chave errada. A service_role tem (e continua tendo) EXECUTE por GRANT
  explícito. Uma fumaça com ela devolveria 200 e culparia um conserto correto.
  Por isso o script lê o papel que a chave carrega e para se não for `anon`;
* a leitura errada. Antes do conserto a chamada anônima devolvia HTTP 200 com
  corpo VAZIO, porque o RLS default-deny da 064 segurou a trilha por baixo. Um
  script que se contentasse com o corpo vazio passaria com o furo escancarado.
  Por isso o veredito olha o STATUS, e HTTP 200 reprova seja qual for o corpo.

A função é de leitura e não tem argumento: rodar isto contra a produção não
grava nada.

Executar:
    SUPABASE_URL=https://... SUPABASE_ANON_KEY=eyJ... \\
        uv run python -m scripts.smoke_revoke_rpc_ouvidoria

    ou: uv run python -m scripts.smoke_revoke_rpc_ouvidoria --url ... --anon-key ...
"""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import sys

import httpx

# A função da migration 092, e o alvo do conserto da 094. Sem argumento e só de
# leitura: chamá-la em produção não muda dado nenhum.
RPC = "ouvidoria_ultimo_movimento"

# `permission denied for function` do PostgreSQL. É a recusa que o conserto
# procura, e o PostgREST a devolve como HTTP 403.
SQLSTATE_PERMISSAO = "42501"

# Sem EXECUTE, o PostgREST pode responder que não achou a função em vez de
# responder que negou, porque o cache de schema dele filtra por permissão. A
# função existe desde a 092, então "não achei" aqui é o mesmo fechamento com
# outro nome.
CODIGO_FORA_DO_CACHE = "PGRST202"

TEMPO_LIMITE = 15.0


def papel_da_chave(chave: str) -> str | None:
    """O papel que a chave do Supabase carrega, ou None quando ela não é um JWT.

    As chaves clássicas (`eyJ...`) são JWT com a claim `role`. As publicáveis
    novas (`sb_publishable_...`) não são, e aí não há papel a conferir: devolver
    None é mais honesto do que devolver um palpite."""
    partes = chave.split(".")
    if len(partes) != 3:
        return None
    corpo = partes[1]
    try:
        bruto = base64.urlsafe_b64decode(corpo + "=" * (-len(corpo) % 4))
        return json.loads(bruto).get("role")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None


def conferir_chave(chave: str) -> None:
    """Para o script se a chave não for a anônima.

    A fumaça só vale com a chave do bundle. Com a service_role o 200 é
    esperado, e interpretá-lo como falha mandaria alguém reabrir um furo que já
    estava fechado."""
    papel = papel_da_chave(chave)
    if papel is not None and papel != "anon":
        sys.exit(
            f"A chave passada é da role `{papel}`, não `anon`. A fumaça precisa da chave "
            f"anônima (a que viaja no bundle do frontend); com outra ela não prova nada."
        )


def veredito(status: int, corpo: str) -> tuple[bool, str]:
    """Se a resposta prova que a anon_key não executa a função.

    HTTP 200 reprova sempre, corpo vazio inclusive: era esse o estado do furo,
    e o vazio vinha do RLS por baixo, não da recusa. HTTP 401 também reprova,
    porque significa que a chave nem foi aceita: é a porta errada, e porta
    errada não é prova de nada."""
    trecho = corpo.strip()[:200]
    if 200 <= status < 300:
        return False, f"A anon_key EXECUTOU a função: HTTP {status}, corpo {trecho or '(vazio)'}."
    if status == 401:
        return False, f"HTTP 401: a chave não foi aceita, então a resposta não diz nada sobre o EXECUTE. {trecho}"
    if status == 403 and SQLSTATE_PERMISSAO in corpo:
        return True, f"Recusado com {SQLSTATE_PERMISSAO} (permission denied), HTTP {status}."
    if status == 404 and CODIGO_FORA_DO_CACHE in corpo:
        return True, f"O PostgREST não expõe a função para a anon_key ({CODIGO_FORA_DO_CACHE}), HTTP {status}."
    return False, f"Resposta inesperada, HTTP {status}: {trecho}. Não dá para concluir que a porta fechou."


def chamar(url: str, chave: str) -> tuple[int, str]:
    resposta = httpx.post(
        f"{url.rstrip('/')}/rest/v1/rpc/{RPC}",
        headers={"apikey": chave, "Authorization": f"Bearer {chave}", "Content-Type": "application/json"},
        json={},
        timeout=TEMPO_LIMITE,
    )
    return resposta.status_code, resposta.text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=f"Fumaça do REVOKE de {RPC}() (issue #520).")
    parser.add_argument("--url", default=os.environ.get("SUPABASE_URL", ""))
    parser.add_argument(
        "--anon-key",
        default=os.environ.get("SUPABASE_ANON_KEY", os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "")),
    )
    args = parser.parse_args(argv)

    if not args.url or not args.anon_key:
        sys.exit("Faltou --url ou --anon-key (ou SUPABASE_URL / SUPABASE_ANON_KEY no ambiente).")
    conferir_chave(args.anon_key)

    status, corpo = chamar(args.url, args.anon_key)
    aprovado, motivo = veredito(status, corpo)
    print(f"{'APROVADO' if aprovado else 'REPROVADO'}: {motivo}")
    return 0 if aprovado else 1


if __name__ == "__main__":
    raise SystemExit(main())
