#!/usr/bin/env python3
"""Inventário do Manual do usuário: o que falta em cada módulo.

É a conta que a `/montar-manual` presta antes de dividir o passivo em um
terminal por módulo (ADR 0057, decisão 9). Cada lacuna cai em exatamente um
balde, e o balde é o módulo dono da página: é isso que deixa cada terminal
mexer só nas pastas do seu módulo sem pisar no vizinho.

Uso:
    python3 tools/inventario_manual.py [--dir docs/manual] [--entregues <json>]

O arquivo de `--entregues` é `{"<modulo>": [<PRD>, ...]}`, os PRDs daquele
módulo que já estão em produção. A skill monta esse arquivo do GitHub e do
`docs/spec/deploy/history.json`; sem ele, dois dos quatro tipos de lacuna não
são conferidos e o relatório diz isso.

Sai com código 1 quando a conta não fecha: página fora dos cinco módulos, ou
nenhum módulo encontrado (inventário vazio é varredura que não rodou, não
manual pronto).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from lint_manual import e_pagina_de_tarefa, ler_frontmatter  # noqa: E402

# A ordem é a do menu do app (ADR 0057, decisão 1). A aba Tecnologia fica fora.
MODULOS = ["primeiros-passos", "reunioes", "ouvidoria", "pops", "admin"]

RE_IMAGEM = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")
RE_NUMERO = re.compile(r"\d+")


@dataclass(frozen=True)
class Lacuna:
    """Um buraco do manual, com o módulo que o fecha e o que fazer."""

    modulo: str
    tipo: str
    detalhe: str


@dataclass
class Inventario:
    modulos: dict[str, list[Lacuna]] = field(default_factory=dict)
    paginas: dict[str, int] = field(default_factory=dict)
    fora_de_balde: list[str] = field(default_factory=list)
    # Chave de `--entregues` que não é módulo (acento, singular, nome antigo).
    # Ignorar em silêncio esconderia os PRDs entregues que ela carrega.
    entregues_desconhecidos: list[str] = field(default_factory=list)
    entregues_informados: bool = True

    @property
    def lacunas(self) -> list[Lacuna]:
        return [lacuna for modulo in MODULOS for lacuna in self.modulos[modulo]]


def _valor(campos: dict[str, str], chave: str) -> str:
    """O valor do campo, sem o comentário que o molde da `/manual` põe na linha.

    O molde escreve `draft: true   # sai quando o PRD sobe para produção`. Ler a
    linha crua faria o `draft` nunca bater com "true" e o `prd` colher os
    números do comentário ("ADR 0057" virando PRD #57).
    """
    return re.sub(r"\s+#.*$", "", campos.get(chave, "")).strip()


def _prds(campos: dict[str, str]) -> list[int]:
    return [int(n) for n in RE_NUMERO.findall(_valor(campos, "prd"))]


def inventariar(
    raiz: Path, entregues: dict[str, list[int]] | None = None
) -> Inventario:
    """Varre o site e devolve as lacunas de cada módulo."""
    conteudo = raiz / "src" / "content" / "docs"
    inventario = Inventario(
        modulos={modulo: [] for modulo in MODULOS},
        paginas={modulo: 0 for modulo in MODULOS},
        entregues_informados=entregues is not None,
    )
    entregues = entregues or {}
    inventario.entregues_desconhecidos = [
        modulo for modulo in entregues if modulo not in MODULOS
    ]
    novidades: dict[str, list[int]] = {}

    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        relativo = arquivo.relative_to(conteudo)
        if len(relativo.parts) < 2:
            continue  # a home do site não é de módulo nenhum
        modulo = relativo.parts[0]
        if modulo not in MODULOS:
            inventario.fora_de_balde.append(str(relativo))
            continue

        texto = arquivo.read_text(encoding="utf-8")
        campos = ler_frontmatter(texto)
        inventario.paginas[modulo] += 1

        if relativo.stem == "novidades":
            novidades[modulo] = _prds(campos)

        if e_pagina_de_tarefa(relativo) and not campos.get("video"):
            inventario.modulos[modulo].append(
                Lacuna(
                    modulo,
                    "sem-video",
                    f"{relativo}: Página de tarefa sem Vídeo de tarefa. A página "
                    "publica com o aviso 'vídeo em produção' até ele sair.",
                )
            )

        for alvo in RE_IMAGEM.findall(texto):
            if alvo.startswith(("http://", "https://", "/")):
                continue
            if not (arquivo.parent / alvo).resolve().is_file():
                inventario.modulos[modulo].append(
                    Lacuna(
                        modulo,
                        "print-faltando",
                        f"{relativo}: aponta para o print '{alvo}', que não "
                        "existe. Acrescente a tela ao Roteiro de prints do "
                        f"módulo (docs/manual/prints/{modulo}.py) e rode.",
                    )
                )

        for prd in _prds(campos):
            if _valor(campos, "draft") == "true" and prd in entregues.get(modulo, []):
                inventario.modulos[modulo].append(
                    Lacuna(
                        modulo,
                        "draft-entregue",
                        f"{relativo}: em draft, e o PRD #{prd} já está em "
                        "produção. Página de coisa no ar que fica em draft some "
                        "do site e da busca (ADR 0057, decisão 5).",
                    )
                )

    for modulo in MODULOS:
        for prd in entregues.get(modulo, []):
            if prd not in novidades.get(modulo, []):
                inventario.modulos[modulo].append(
                    Lacuna(
                        modulo,
                        "prd-sem-novidades",
                        f"PRD #{prd} entregue e sem entrada em "
                        f"{modulo}/novidades.md. Quem já usa o módulo não fica "
                        "sabendo do que mudou. A entrada conta quando o número "
                        "está no `prd:` do frontmatter da página.",
                    )
                )

    return inventario


def _plural(quantos: int, singular: str) -> str:
    return f"{quantos} {singular}" + ("" if quantos == 1 else "s")


def formatar(inventario: Inventario, raiz: Path) -> str:
    linhas = [f"Inventário do Manual ({raiz})", ""]
    if not inventario.entregues_informados:
        linhas += [
            "sem --entregues: as lacunas 'prd-sem-novidades' e 'draft-entregue' "
            "NÃO foram conferidas.",
            "",
        ]
    for modulo in MODULOS:
        lacunas = inventario.modulos[modulo]
        linhas.append(
            f"## {modulo}: {_plural(inventario.paginas[modulo], 'página')}, "
            f"{_plural(len(lacunas), 'lacuna')}"
        )
        for lacuna in lacunas:
            linhas.append(f"  - {lacuna.tipo}: {lacuna.detalhe}")
        linhas.append("")

    conta = " + ".join(
        f"{modulo} {len(inventario.modulos[modulo])}" for modulo in MODULOS
    )
    linhas += [
        "## Contas",
        f"  {len(MODULOS)} módulos, "
        f"{_plural(sum(inventario.paginas.values()), 'página')}, "
        f"{_plural(len(inventario.lacunas), 'lacuna')}",
        f"  {conta} = {len(inventario.lacunas)} (cada lacuna em um balde só)",
    ]
    return "\n".join(linhas)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual")
    ap.add_argument("--entregues", help="JSON {<modulo>: [<PRD>, ...]} dos PRDs no ar")
    args = ap.parse_args()

    raiz = Path(args.dir)
    if not (raiz / "src" / "content" / "docs").is_dir():
        print(
            f"Inventário do Manual: '{raiz}' não tem src/content/docs.",
            file=sys.stderr,
        )
        return 1

    entregues = None
    if args.entregues:
        try:
            lido = json.loads(Path(args.entregues).read_text(encoding="utf-8"))
            entregues = {
                modulo: [int(prd) for prd in prds] for modulo, prds in lido.items()
            }
        except (OSError, ValueError, AttributeError, TypeError) as erro:
            print(
                f"Inventário do Manual: não consegui ler '{args.entregues}' "
                f'({erro}). O formato é {{"<modulo>": [<PRD>, ...]}}, com os '
                f"módulos {', '.join(MODULOS)}.",
                file=sys.stderr,
            )
            return 1

    inventario = inventariar(raiz, entregues)
    print(formatar(inventario, raiz))

    if not sum(inventario.paginas.values()):
        print(
            "Inventário do Manual: nenhuma página de módulo encontrada. "
            "Inventário vazio é varredura que não rodou, não manual pronto.",
            file=sys.stderr,
        )
        return 1
    if inventario.fora_de_balde:
        print(
            "Inventário do Manual: página fora dos cinco módulos, sem terminal "
            "que a feche:\n"
            + "\n".join(f"  - {p}" for p in inventario.fora_de_balde)
            + f"\nOs módulos são {', '.join(MODULOS)} (ADR 0057, decisão 1).",
            file=sys.stderr,
        )
        return 1
    if inventario.entregues_desconhecidos:
        print(
            "Inventário do Manual: --entregues traz módulo que não existe:\n"
            + "\n".join(f"  - {m}" for m in inventario.entregues_desconhecidos)
            + "\nOs PRDs dessa chave não foram conferidos contra página nenhuma. "
            f"Os módulos são {', '.join(MODULOS)} (ADR 0057, decisão 1).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
