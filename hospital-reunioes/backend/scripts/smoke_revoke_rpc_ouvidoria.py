"""Fumaça: a anon_key não executa `ouvidoria_ultimo_movimento()` (issue #520).

Quem aplica migration nesta casa é o humano, à mão, no SQL Editor do Studio de
produção. Migration escrita no repositório não é migration aplicada, e foi
exatamente essa distância que deixou o furo da 092 aberto sem ninguém notar.
Este script é o que fecha a conta: rodado contra a produção depois de aplicar a
095, ele diz se a porta fechou de verdade.

Ele bate com a chave ANÔNIMA, a mesma que viaja no bundle do frontend. Duas
armadilhas moram aí, e o script recusa as duas:

* a chave errada. A service_role tem (e continua tendo) EXECUTE por GRANT
  explícito. Uma fumaça com ela devolveria 200 e culparia um conserto correto.
  Por isso o script lê o papel que a chave carrega e para se não for `anon`;
* a leitura errada. Antes do conserto a chamada anônima devolvia HTTP 200 com
  corpo VAZIO, porque o RLS default-deny da 064 segurou a trilha por baixo. Um
  script que se contentasse com o corpo vazio passaria com o furo escancarado.
  Por isso HTTP 200 reprova seja qual for o corpo.

A única resposta que aprova é a recusa NOMEADA: o SQLSTATE 42501 no corpo, com
401 ou 403 na linha de status (nesta instalação a negação de EXECUTE volta 401;
o 403 é o que a documentação do PostgREST descreve). Quem decide é o SQLSTATE,
e não o status, porque a chave inválida também responde 401, só que com o corpo
do gateway e sem SQLSTATE nenhum. Todo o resto reprova, o HTTP 404 do PostgREST
inclusive, que é ambíguo demais (a mesma resposta serve para URL errada e para
banco sem as migrations). Verde sem prova foi o que criou este bug, e um script
de fumaça que o repetisse não valeria o arquivo.

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

# A função da migration 092, e o alvo do conserto da 095. Sem argumento e só de
# leitura: chamá-la em produção não muda dado nenhum.
RPC = "ouvidoria_ultimo_movimento"

# `permission denied for function` do PostgreSQL. É a recusa que o conserto
# procura. A documentação do PostgREST a descreve como HTTP 403, mas nesta
# instalação ela chega com 401: por isso o veredito procura ESTE código no
# corpo, e não um status na linha de cima.
SQLSTATE_PERMISSAO = "42501"

# "Não achei a função". Sem EXECUTE, o PostgREST PODE responder isso em vez de
# responder que negou, porque o cache de schema dele filtra por permissão. Mas
# é a MESMA resposta de URL errada, de banco sem as migrations e de cache
# velho, então ela não prova nada sozinha: o script a trata como inconclusiva e
# manda conferir no catálogo. Verde sem prova é o que criou este bug.
CODIGO_FORA_DO_CACHE = "PGRST202"

CONSULTA_DO_CATALOGO = (
    "SELECT has_function_privilege('anon', p.oid, 'EXECUTE') FROM pg_proc p "
    "JOIN pg_namespace n ON n.oid = p.pronamespace "
    f"WHERE n.nspname = 'public' AND p.proname = '{RPC}';"
)

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


# O prefixo da chave secreta no formato novo do Supabase, sucessora da
# `service_role`. Ela NÃO é JWT, então não tem claim `role` para ler, e sem
# este nome escrito aqui ela passaria pela conferência como se fosse a do
# bundle. A publicável (`sb_publishable_`) é a anônima e pode passar.
PREFIXO_CHAVE_SECRETA = "sb_secret_"


def conferir_chave(chave: str) -> None:
    """Para o script se a chave não for a anônima.

    A fumaça só vale com a chave do bundle. Com a service_role o 200 é
    esperado, e interpretá-lo como falha mandaria alguém reabrir um furo que já
    estava fechado."""
    if chave.startswith(PREFIXO_CHAVE_SECRETA):
        sys.exit(
            f"A chave passada começa com `{PREFIXO_CHAVE_SECRETA}`: é a chave SECRETA do backend, "
            f"não a anônima. A fumaça precisa da chave que viaja no bundle do frontend."
        )
    papel = papel_da_chave(chave)
    if papel is not None and papel != "anon":
        sys.exit(
            f"A chave passada é da role `{papel}`, não `anon`. A fumaça precisa da chave "
            f"anônima (a que viaja no bundle do frontend); com outra ela não prova nada."
        )


def veredito(status: int, corpo: str) -> tuple[bool, str]:
    """Se a resposta prova que a anon_key não executa a função.

    **O que decide é o SQLSTATE, não o status.** A lição custou um falso
    negativo em produção: com a 095 já aplicada, a recusa voltou como

        HTTP 401 {"code":"42501","message":"permission denied for function ..."}

    e uma versão anterior deste script REPROVOU um conserto que estava certo,
    porque tinha fixado o 403 como o único status capaz de carregar a recusa.
    Nesta instalação (Supabase self-hosted, PostgREST atrás do gateway) a
    negação de EXECUTE volta com 401. O 403 segue aceito porque é o que a
    documentação do PostgREST descreve: são a mesma resposta.

    Isso NÃO afrouxa a guarda da chave inválida, que também responde 401. O que
    separa os dois casos nunca foi o status:

    * chave boa, função revogada: corpo do POSTGRES, com o `42501` dentro;
    * chave inválida: corpo do GATEWAY, `{"message":"Unauthorized"}`, sem
      SQLSTATE nenhum, porque a requisição não chegou ao banco.

    O `42501` só nasce depois que a chave foi aceita e o JWT foi resolvido para
    a role `anon`. Ele é, ao mesmo tempo, a prova de que a porta fechou e a
    prova de que a fumaça bateu na porta certa.

    HTTP 200 reprova sempre, corpo vazio inclusive: era esse o estado do furo, e
    o vazio vinha do RLS por baixo, não da recusa."""
    trecho = corpo.strip()[:200]
    # 2xx é a função tendo executado, e nenhum corpo redime isso.
    if 200 <= status < 300:
        return False, f"A anon_key EXECUTOU a função: HTTP {status}, corpo {trecho or '(vazio)'}."
    if SQLSTATE_PERMISSAO in corpo:
        return True, f"Recusado pelo Postgres com {SQLSTATE_PERMISSAO} (permission denied), HTTP {status}."
    if status in (401, 403):
        return False, (
            f"HTTP {status} SEM o SQLSTATE {SQLSTATE_PERMISSAO}: a recusa veio do gateway, e não do "
            f"banco, então a chave não foi aceita e a resposta não diz nada sobre o EXECUTE. {trecho}"
        )
    if status == 404 and CODIGO_FORA_DO_CACHE in corpo:
        return False, (
            f"HTTP {status} ({CODIGO_FORA_DO_CACHE}): o PostgREST diz que não conhece a função. "
            f"Pode ser o EXECUTE revogado, mas é a mesma resposta de URL errada, de banco sem as "
            f"migrations e de cache de schema velho. Confira no catálogo: {CONSULTA_DO_CATALOGO}"
        )
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
