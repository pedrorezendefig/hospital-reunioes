"""Backfill do `setor` contra a taxonomia (issue #419).

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

Duas tabelas, e as duas juntas: `ouvidoria_protocolos` e
`ouvidoria_setor_responsaveis`. `carregar_responsaveis` casa string EXATA, então
corrigir só a manifestação deixaria o caso sem destinatário, e a varredura o
carimbaria como impossível de escalonar.

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

# O PostgREST corta a resposta num teto de linhas (1000 por default). Ler sem
# paginar faria o script planejar só a primeira página e imprimir o relatório
# como se tivesse visto o banco inteiro, que é o pior resultado possível: o
# ouvidor confia num número parcial.
PAGINA = 500


def ler_paginado(supabase, tabela: str, colunas: str) -> list[dict]:
    """Todas as linhas da tabela, em páginas, até vir uma página curta."""
    linhas: list[dict] = []
    inicio = 0
    while True:
        pagina = supabase.table(tabela).select(colunas).order("id").range(inicio, inicio + PAGINA - 1).execute()
        recebidas = list(pagina.data or [])
        linhas.extend(recebidas)
        if len(recebidas) < PAGINA:
            return linhas
        inicio += PAGINA


def carregar_setores(supabase) -> list[str]:
    setores = supabase.table("setores").select("nome").eq("ativo", True).order("nome").execute()
    return [linha.get("nome") or "" for linha in (setores.data or [])]


def aplicar(supabase, tabela: str, plano: PlanoBackfill) -> int:
    """Uma linha por vez, de propósito: o volume é pequeno e um update em lote
    esconderia qual linha falhou.

    Conta o que o BANCO aceitou, não o tamanho do plano: relatório de correção
    que conta a intenção mente quando o update não pega."""
    gravadas = 0
    for correcao in plano.correcoes:
        result = supabase.table(tabela).update({"setor": correcao["para"]}).eq("id", correcao["id"]).execute()
        if result.data:
            gravadas += 1
    return gravadas


def imprimir_relatorio(titulo: str, plano: PlanoBackfill, gravadas: int | None) -> None:
    """O que o ouvidor precisa ler. As pendências vêm agrupadas por área
    escrita, com quem está nelas, que é como ele vai abrir caso a caso."""
    print(f"\n=== {titulo} ===")
    if gravadas is None:
        print(f"A corrigir: {len(plano.correcoes)}")
    else:
        print(f"Corrigidas: {gravadas} de {len(plano.correcoes)} planejadas")
    for correcao in plano.correcoes:
        print(f"  {correcao['protocolo']}: {correcao['de']!r} -> {correcao['para']!r}")

    total_pendente = sum(len(linha["protocolos"]) for linha in plano.pendencias)
    print(f"Fora da taxonomia (NÃO alteradas): {total_pendente} em {len(plano.pendencias)} áreas")
    for linha in plano.pendencias:
        print(f"  {linha['setor']!r}: {', '.join(linha['protocolos'])}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill do setor contra a taxonomia")
    parser.add_argument("--aplicar", action="store_true", help="grava as correções (sem isto, só mostra)")
    args = parser.parse_args()

    supabase = create_client(settings.supabase_url, settings.supabase_service_role_key)
    setores = carregar_setores(supabase)
    if not setores:
        print("A taxonomia de setores está vazia: nada a comparar. Nenhuma linha foi tocada.")
        return 1

    alvos = [
        ("Manifestações", "ouvidoria_protocolos", "id, protocolo, setor", "protocolo"),
        ("Responsáveis de setor", "ouvidoria_setor_responsaveis", "id, nome, setor", "nome"),
    ]
    pendencias_totais = 0
    for titulo, tabela, colunas, identificador in alvos:
        plano = planejar_backfill(ler_paginado(supabase, tabela, colunas), setores, identificador)
        gravadas = aplicar(supabase, tabela, plano) if args.aplicar else None
        imprimir_relatorio(titulo, plano, gravadas)
        pendencias_totais += len(plano.pendencias)

    if not args.aplicar:
        print("\nNada foi gravado. Rode de novo com --aplicar para valer.")
    if pendencias_totais:
        print(
            "\nAs áreas fora da taxonomia não existem na lista de setores ativos. Cadastre o setor que "
            "faltou, ou corrija a área pelo painel da Ouvidoria."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
