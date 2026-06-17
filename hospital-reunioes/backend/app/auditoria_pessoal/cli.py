"""CLI de calibração: roda o motor sobre os 2 PDFs e gera o relatório local.

Uso:
    python3 -m app.auditoria_pessoal.cli "ESPELHO.PDF" "FOLHA.pdf" [--out DIR]

Requer `pdftotext` (poppler) no PATH; aceita também .txt já extraído.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from .parametros import Parametros
from .parser_espelho import parse_espelho, validar_duracoes
from .parser_folha import parse_folha
from .regras import rodar_regras
from .relatorio import gerar_markdown
from .vinculo import vincular


def _texto(caminho: str) -> str:
    p = Path(caminho)
    if p.suffix.lower() == ".txt":
        return p.read_text(encoding="utf-8")
    res = subprocess.run(
        ["pdftotext", "-layout", str(p), "-"],
        capture_output=True,
        text=True,
        check=True,
    )
    return res.stdout


def main() -> int:
    ap = argparse.ArgumentParser(description="Auditoria de Pessoal — calibração local")
    ap.add_argument("espelho", help="PDF do Espelho de Ponto (RH iD)")
    ap.add_argument("folha", help="PDF da Folha (Domínio)")
    ap.add_argument("--out", default="auditoria-pessoal-local", help="diretório de saída")
    args = ap.parse_args()

    espelhos, avisos_esp = parse_espelho(_texto(args.espelho))
    registros, competencia, avisos_folha = parse_folha(_texto(args.folha))
    competencia = competencia or "?"

    total_dur, dur_ok, avisos_dur = validar_duracoes(espelhos)
    folha_ok = sum(1 for r in registros if not r.avisos_parse)
    avisos_parse_esp = [a for f in espelhos for a in f.avisos_parse]

    params = Parametros()
    vinculos, vinculo_stats, fila_revisao = vincular(espelhos, registros, params)
    achados, stats = rodar_regras(vinculos, params)

    parse_info = {
        "Espelho": f"{len(espelhos)} funcionário(s) lidos; {len(avisos_esp)} página(s) com problema; "
        f"{len(avisos_parse_esp)} aviso(s) de linha",
        "Espelho — durações": f"{dur_ok}/{total_dur} dias batem com a duração impressa "
        f"(±2 min); {len(avisos_dur)} divergência(s) — dado podre do RH iD ou parse a revisar",
        "Folha": f"{len(registros)} registro(s) lidos (competência {competencia}); "
        f"{folha_ok}/{len(registros)} fecham o invariante Σ rubricas = totais impressos",
    }

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    md = gerar_markdown(competencia, parse_info, vinculo_stats, fila_revisao, achados, stats, params)
    comp_slug = competencia.replace("/", "-")
    md_path = out / f"calibracao-{comp_slug}.md"
    md_path.write_text(md, encoding="utf-8")
    (out / f"achados-{comp_slug}.json").write_text(
        json.dumps([asdict(a) for a in achados], ensure_ascii=False, indent=1, default=str),
        encoding="utf-8",
    )
    (out / f"avisos-parse-{comp_slug}.txt").write_text(
        "\n".join(
            ["== espelho: páginas =="]
            + avisos_esp
            + ["", "== espelho: linhas =="]
            + avisos_parse_esp
            + ["", "== espelho: durações divergentes =="]
            + avisos_dur
            + ["", "== folha =="]
            + avisos_folha
        ),
        encoding="utf-8",
    )

    print(f"Competência {competencia}")
    print(f"Espelho: {len(espelhos)} funcionários | Folha: {len(registros)} registros")
    print(f"Validação folha: {folha_ok}/{len(registros)} invariantes OK | durações espelho: {dur_ok}/{total_dur} OK")
    print(
        f"Vínculo: cpf={vinculo_stats['cpf']} nome={vinculo_stats['nome']} fuzzy={vinculo_stats['fuzzy']} "
        f"| órfãos ponto={vinculo_stats['so_espelho']} folha={vinculo_stats['so_folha']}"
    )
    por_sev = {}
    for a in achados:
        por_sev[a.severidade] = por_sev.get(a.severidade, 0) + 1
    print(f"Achados (candidatos): {len(achados)} — {por_sev}")
    print(f"Relatório: {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
