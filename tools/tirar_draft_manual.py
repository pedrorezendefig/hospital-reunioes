#!/usr/bin/env python3
"""Tira o `draft` das páginas do Manual dos PRDs que subiram para produção.

O `draft` é o único mecanismo de invisibilidade do manual (ADR 0057, decisão
5): página de funcionalidade que ainda não está no ar fica fora do build e da
busca. Quem apaga essa marca não é gente: é o `/deploy ship`, logo depois do
bookkeeping, para cada PRD daquele deploy.

Tirar o draft só vale se a publicação for possível **em seguida**: draft tirado
e commitado com a publicação falhando deixa a página no repositório e fora do
ar, que é o pior dos dois mundos. Por isso o script confere antes de escrever
(MP4 de cada Vídeo de tarefa e ferramentas que o `publicar.sh` usa) e, se algo
falta, não toca em arquivo nenhum.

Uso:
    python3 tools/tirar_draft_manual.py --prd 731 [--prd 740]
                                        [--dir docs/manual] [--dry-run]

Códigos de saída:
    0  tirou o draft, ou não havia nada a tirar (o passo é silencioso)
    1  uso errado: a pasta não é o site do manual
    2  bloqueado antes de escrever, com o que falta na saída de erro
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from inventario_manual import prds_da_pagina, valor_do_campo  # noqa: E402
from lint_manual import ler_frontmatter  # noqa: E402

# A leitura do frontmatter é a mesma do inventário de propósito: se as duas
# divergirem, o inventário da `/montar-manual` acusa `draft-entregue` numa
# página que este passo jura ter publicado.

# O `publicar.sh` builda o site (Starlight 0.42 exige Node >= 22.12, por
# `corepack pnpm@9`) e reencoda cada MP4 com ffmpeg. O mesmo mínimo está no
# diagnóstico do `/setup-maquina`.
NODE_MIN = (22, 12)


def paginas_em_draft(conteudo: Path, prds: list[int]) -> list[Path]:
    """As páginas em draft cujos PRDs **todos** já subiram, em ordem.

    A regra é subconjunto, não interseção: página escrita por dois PRDs só vai
    ao ar quando o segundo sobe, senão o deploy de um põe no ar a tela do outro.
    """
    achadas = []
    for arquivo in sorted(conteudo.rglob("*.md*")):
        if arquivo.suffix not in (".md", ".mdx"):
            continue
        campos = ler_frontmatter(arquivo.read_text(encoding="utf-8"))
        if valor_do_campo(campos, "draft") != "true":
            continue
        da_pagina = set(prds_da_pagina(campos))
        if da_pagina and da_pagina <= set(prds):
            achadas.append(arquivo)
    return achadas


def sem_draft(texto: str) -> str | None:
    """O texto da página com o draft desligado, ou `None` se não achou a linha.

    Só o bloco do frontmatter: `draft:` no corpo da página é texto que a pessoa
    lê. A caixa da chave é a que estiver no arquivo (o frontmatter é lido em
    minúscula, e comparar com caixa exata na hora de escrever deixaria um
    `Draft: true` passar por publicado sem nenhuma troca).
    """
    linhas = texto.splitlines(keepends=True)
    if not linhas or linhas[0].strip() != "---":
        return None
    for i, linha in enumerate(linhas[1:], start=1):
        if linha.strip() == "---":
            return None
        if linha.lower().startswith("draft:"):
            return "".join(
                linhas[:i]
                + [re.sub("true", "false", linha, count=1, flags=re.I)]
                + linhas[i + 1 :]
            )
    return None


def video_sem_mp4(raiz: Path, conteudo: Path, paginas: list[Path]) -> list[str]:
    """Páginas que exibem vídeo cujo MP4 não existe nesta árvore.

    O MP4 é regerável e fica fora do controle de versão, então não vem no
    clone. O `publicar.sh` sai com erro quando a página aponta para um vídeo
    que ele não acha, e aí o draft já teria sido tirado.
    """
    faltando = []
    for arquivo in paginas:
        relativo = arquivo.relative_to(conteudo)
        slug = ler_frontmatter(arquivo.read_text(encoding="utf-8")).get("video", "")
        if not slug:
            continue
        modulo = relativo.parts[0]
        if not (raiz / "public" / "video" / modulo / f"{slug}.mp4").is_file():
            faltando.append(
                f"{relativo}: exibe o vídeo '{slug}' e o MP4 não existe em "
                f"public/video/{modulo}/{slug}.mp4. Renderize a composição de "
                f"video/{modulo}/{slug}/ antes de publicar (a receita está em "
                ".claude/skills/manual/references/video-de-tarefa.md)."
            )
    return faltando


def versao_do_node() -> tuple[int, ...] | None:
    """A versão do `node` do PATH, ou `None` quando não há node nenhum."""
    if not shutil.which("node"):
        return None
    saida = subprocess.run(
        ["node", "-v"], capture_output=True, text=True
    ).stdout.strip()
    numeros = re.findall(r"\d+", saida)
    return tuple(int(n) for n in numeros[:3]) if numeros else ()


def ferramentas_faltando() -> list[str]:
    """O que o `publicar.sh` precisa e esta máquina não tem."""
    faltando = []
    minima = ".".join(str(n) for n in NODE_MIN)
    node = versao_do_node()
    if node is None:
        faltando.append(
            f"node: o site do Manual é Starlight e exige >= {minima}. "
            "Instale com brew install node@22 (o /setup-maquina confere)."
        )
    elif node < NODE_MIN:
        atual = ".".join(str(n) for n in node)
        faltando.append(
            f"node: esta máquina tem v{atual} e o site do Manual exige "
            f">= {minima}. Instale com brew install node@22."
        )
    if not shutil.which("corepack"):
        faltando.append(
            "corepack: a publicação builda o site com corepack pnpm@9. "
            "Instale com npm i -g corepack."
        )
    if not shutil.which("ffmpeg"):
        faltando.append(
            "ffmpeg: a publicação reencoda cada vídeo para 720p. "
            "Instale com brew install ffmpeg."
        )
    return faltando


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs/manual")
    ap.add_argument(
        "--prd",
        type=int,
        action="append",
        required=True,
        help="número do PRD que subiu; repita para vários",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raiz = Path(args.dir)
    conteudo = raiz / "src" / "content" / "docs"
    if not conteudo.is_dir():
        print(
            f"Manual: '{raiz}' não tem src/content/docs. "
            "O site do manual é docs/manual/.",
            file=sys.stderr,
        )
        return 1

    numeros = ", ".join(f"#{n}" for n in args.prd)
    achadas = paginas_em_draft(conteudo, args.prd)
    if not achadas:
        print(f"Manual: nenhuma página em draft do PRD {numeros}.")
        return 0

    # Tudo o que impede a publicação é levantado antes da primeira escrita: ou
    # o PRD inteiro sai do draft, ou nada sai.
    impedimentos = video_sem_mp4(raiz, conteudo, achadas) + ferramentas_faltando()
    novos = []
    for arquivo in achadas:
        novo = sem_draft(arquivo.read_text(encoding="utf-8"))
        if novo is None:
            impedimentos.append(
                f"{arquivo.relative_to(conteudo)}: o frontmatter diz draft, mas "
                "não há linha 'draft:' para desligar. Conserte o frontmatter."
            )
        novos.append((arquivo, novo))

    if impedimentos:
        print(
            f"Manual: o draft do PRD {numeros} fica como está. Sem isto, a "
            "página sai do draft e a publicação falha, e o manual fica no "
            "repositório e fora do ar:\n" + "\n".join(f"  - {i}" for i in impedimentos),
            file=sys.stderr,
        )
        return 2

    for arquivo, novo in novos:
        if not args.dry_run:
            arquivo.write_text(novo, encoding="utf-8")
        print(f"Manual: {arquivo.relative_to(conteudo)} sai do draft.")
    if args.dry_run:
        print(f"(--dry-run: {len(novos)} página(s) continuam em draft.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
