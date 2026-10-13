"""Candidatas ao esqueleto fixo dos formulários do MV (issue #1132).

Lê prontuários reais pelo caminho da fila (extração com as marcações e
`ler_prontuario`) e imprime, por chave de `formulario._chave`, as linhas que
estão em 80% ou mais dos documentos da Família em TODOS os prontuários dados,
sem o título e sem linha marcada. O resultado vai, conferido à mão, para
`app/services/contas_medicas/esqueleto_formulario.py`: tire a linha que traz
resposta igual por acaso nos pacientes, e confira que nenhuma tem nome, data,
profissional ou número de paciente (o repo é público).

Este script NÃO roda em produção nem em teste, e os PDFs nunca entram no repo.
A saída tem só linhas de formulário; não a cole em issue nem em PR sem conferir.

Uso (de prontuários de pacientes diferentes):

    uv run python scripts/gerar_esqueleto_formulario.py um.pdf outro.pdf
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.contas_medicas import formulario  # noqa: E402
from app.services.contas_medicas.marcacoes import MARCADA  # noqa: E402
from app.services.contas_medicas.prontuario import ler_prontuario  # noqa: E402
from app.services.contas_medicas_extrator import ErroLeitura, extrair_paginas  # noqa: E402


def _modelo_do_prontuario(caminho: str) -> dict[str, set[str]]:
    paginas = extrair_paginas(Path(caminho).read_bytes())
    if isinstance(paginas, ErroLeitura):
        sys.exit(f"{caminho}: {paginas.motivo}")
    textos = [pagina.texto for pagina in paginas]
    atendimentos = Counter(m for texto in textos for m in re.findall(r"Atendimento:?\s*(\d{4,})", texto, re.I))
    prontuario = ler_prontuario(textos, atendimentos.most_common(1)[0][0])
    por_chave: dict[str, list] = {}
    for documento in prontuario.documentos:
        if chave := formulario._chave(documento):
            por_chave.setdefault(chave, []).append(documento)
    modelo = {}
    for chave, documentos in por_chave.items():
        vezes = Counter(linha for d in documentos for linha in set(d.linhas[1:]) if MARCADA not in linha)
        modelo[chave] = {linha for linha, n in vezes.items() if n >= formulario.FRACAO_DO_MODELO * len(documentos)}
    return modelo


def main(caminhos: list[str]) -> None:
    if len(caminhos) < 2:
        sys.exit("Dê ao menos dois prontuários, de pacientes diferentes.")
    modelos = [_modelo_do_prontuario(caminho) for caminho in caminhos]
    for chave in sorted(set.intersection(*(set(m) for m in modelos))):
        linhas = set.intersection(*(m[chave] for m in modelos))
        print(f"{chave!r}: {len(linhas)} linhas")
        for linha in sorted(linhas):
            print(f"    {linha!r},")


if __name__ == "__main__":
    main(sys.argv[1:])
