"""Migração one-shot do Fluxograma legado (Mermaid) para a gramática JSON (issue #224).

Percorre `pops_versoes.rascunho`, converte as seções de fluxograma com Mermaid
do subset do prompt antigo (ADR 0017) para o objeto da gramática restrita
(ADR 0024) e relata o resultado por seção: convertida, pulada ou inconversível.
O inconversível permanece exatamente como estava (cai no fallback existente da
tela e do PDF); o SVG persistido com a Versão não muda um byte.

Idempotente: numa segunda execução tudo é pulado e nada é escrito.

Uso (no container do backend; sem flag é DRY-RUN, nada é gravado):

    python -m scripts.oneshot.migrar_fluxogramas_mermaid
    python -m scripts.oneshot.migrar_fluxogramas_mermaid --aplicar
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.append(os.getcwd())

from app.services.pops_fluxograma_migracao import migrar_rascunho_fluxogramas  # noqa: E402

PAGINA = 500


def executar(supabase, aplicar: bool) -> dict:
    """Roda a migração sobre todas as pops_versoes e devolve os totais.
    Com `aplicar=False` (dry-run) nada é escrito no banco."""
    totais = {"versoes": 0, "convertidas": 0, "puladas": 0, "inconversiveis": 0, "versoes_atualizadas": 0}
    plural = {"convertida": "convertidas", "pulada": "puladas", "inconversivel": "inconversiveis"}

    inicio = 0
    while True:
        resposta = (
            supabase.table("pops_versoes")
            .select("id, rascunho")
            .order("id")
            .range(inicio, inicio + PAGINA - 1)
            .execute()
        )
        versoes = resposta.data or []
        for versao in versoes:
            totais["versoes"] += 1
            rascunho = versao.get("rascunho")
            if not isinstance(rascunho, dict):
                continue

            novo, relatorios = migrar_rascunho_fluxogramas(rascunho)
            for relatorio in relatorios:
                totais[plural[relatorio["status"]]] += 1
                if relatorio["status"] != "pulada":
                    print(
                        f"  versao {versao['id']} secao '{relatorio['titulo']}': "
                        f"{relatorio['status']} ({relatorio['motivo']})"
                    )

            if novo != rascunho:
                totais["versoes_atualizadas"] += 1
                if aplicar:
                    supabase.table("pops_versoes").update({"rascunho": novo}).eq("id", versao["id"]).execute()

        if len(versoes) < PAGINA:
            break
        inicio += PAGINA

    return totais


def main() -> None:
    parser = argparse.ArgumentParser(description="Migra o Mermaid legado dos fluxogramas de POP para o JSON novo.")
    parser.add_argument(
        "--aplicar",
        action="store_true",
        help="grava as conversões no banco (sem esta flag, dry-run: só relata)",
    )
    args = parser.parse_args()

    from app.dependencies import get_supabase_client

    modo = "APLICAR (gravando no banco)" if args.aplicar else "DRY-RUN (nada será gravado)"
    print(f"--- Migração de fluxogramas Mermaid -> JSON | modo: {modo} ---")

    totais = executar(get_supabase_client(), aplicar=args.aplicar)

    print("\n--- Resumo ---")
    print(f"Versões lidas: {totais['versoes']}")
    print(f"Seções convertidas: {totais['convertidas']}")
    print(f"Seções puladas: {totais['puladas']}")
    print(f"Seções inconversíveis (intactas, no fallback): {totais['inconversiveis']}")
    destino = "gravadas" if args.aplicar else "a gravar (rode com --aplicar)"
    print(f"Versões {destino}: {totais['versoes_atualizadas']}")


if __name__ == "__main__":
    main()
