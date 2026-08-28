"""Backfill do `setor` das manifestações contra a taxonomia (issue #419).

A validação nova prende as escritas de hoje à lista de setores da casa. O
número errado, porém, já está no banco: manifestações antigas foram gravadas
com texto livre, e o relatório da Diretoria conta "Recepção" e "Recepçao" como
duas áreas.

Este script faz a outra metade, no caminho 2 da issue:

- o que casa com a taxonomia por chave normalizada (caixa, acento, espaço) é
  corrigido para a grafia canônica;
- o que NÃO casa não é tocado. Adivinhar aqui trocaria um número errado por
  outro sem ninguém saber, então essas linhas saem num relatório para o ouvidor
  resolver à mão, pela tela de sempre.

É idempotente: rodar duas vezes não muda nada na segunda.

Executar (dry-run, só mostra o que faria):
    docker compose exec backend python -m scripts.backfill_setor_manifestacoes

Executar aplicando de verdade:
    docker compose exec backend python -m scripts.backfill_setor_manifestacoes --aplicar
"""

from __future__ import annotations

import argparse
import sys

from supabase import create_client

from app.config import settings
from app.services.ouvidoria_taxonomia import PlanoBackfill, planejar_backfill


def carregar(supabase) -> tuple[list[dict], list[str]]:
    protocolos = supabase.table("ouvidoria_protocolos").select("id, protocolo, setor").execute()
    setores = supabase.table("setores").select("nome").eq("ativo", True).execute()
    return list(protocolos.data or []), [linha.get("nome") or "" for linha in (setores.data or [])]


def aplicar(supabase, plano: PlanoBackfill) -> int:
    """Uma linha por vez, de propósito: o volume é pequeno e um update em lote
    esconderia qual protocolo falhou."""
    gravadas = 0
    for correcao in plano.correcoes:
        supabase.table("ouvidoria_protocolos").update({"setor": correcao["para"]}).eq("id", correcao["id"]).execute()
        gravadas += 1
    return gravadas


def imprimir_relatorio(plano: PlanoBackfill, aplicado: bool) -> None:
    """O que o ouvidor precisa ler. As pendências vêm agrupadas por área
    escrita, com os protocolos, que é como ele vai abrir caso a caso."""
    verbo = "Corrigidas" if aplicado else "A corrigir"
    print(f"\n{verbo}: {len(plano.correcoes)} manifestações")
    for correcao in plano.correcoes:
        print(f"  {correcao['protocolo']}: {correcao['de']!r} -> {correcao['para']!r}")

    total_pendente = sum(len(linha["protocolos"]) for linha in plano.pendencias)
    print(f"\nFora da taxonomia (NÃO alteradas): {total_pendente} manifestações em {len(plano.pendencias)} áreas")
    for linha in plano.pendencias:
        print(f"  {linha['setor']!r}: {', '.join(linha['protocolos'])}")
    if plano.pendencias:
        print(
            "\nEstas áreas não existem na lista de setores ativos. Cadastre o setor que faltou, "
            "ou corrija a área da manifestação pelo painel da Ouvidoria."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill do setor das manifestações contra a taxonomia")
    parser.add_argument("--aplicar", action="store_true", help="grava as correções (sem isto, só mostra)")
    args = parser.parse_args()

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    protocolos, setores = carregar(supabase)
    if not setores:
        print("A taxonomia de setores está vazia: nada a comparar. Nenhuma linha foi tocada.")
        return 1

    plano = planejar_backfill(protocolos, setores)
    if args.aplicar:
        aplicar(supabase, plano)
    imprimir_relatorio(plano, aplicado=args.aplicar)
    if not args.aplicar and plano.correcoes:
        print("\nNada foi gravado. Rode de novo com --aplicar para valer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
