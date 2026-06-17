"""Relatório de calibração em Markdown — consumo local (Pedro + diretor).

Linguagem de verificação, não de acusação: tudo aqui é candidato a Achado,
para validar regras e parâmetros antes do módulo no app.
"""

from __future__ import annotations

from .modelos import Achado
from .parametros import Parametros

SEVERIDADES = ["CRITICA", "ALTA", "MEDIA", "INFO"]
MAX_POR_REGRA = 14

NOMES_REGRAS = {
    "R1": "Conciliação de HE — pago × batido",
    "R2": "Horas extras acima do teto legal",
    "R3": "Pago sem ponto",
    "R4": "Atrasos e faltas × descontos",
    "R5": "Adicional noturno",
    "R6": "Interjornada mínima (11h)",
    "R7": "Mais de 6 dias corridos",
    "R8": "Jornada diária excessiva",
    "R9": "Intervalo suprimido/fabricado",
    "R10": "Qualidade de cadastro",
}


def _brl(v: float) -> str:
    return (f"R$ {v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _classificar_grade(grade_min) -> str:
    if grade_min is None:
        return "sem grade?"
    h = grade_min / 60.0
    if h >= 20:
        return "⚠️ plantão ~24h — confirmar amparo"
    if 11 <= h <= 13:
        return "12x36?"
    if h <= 7:
        return "parcial/administrativa curta"
    return "diurna comum"


def gerar_markdown(
    competencia: str,
    parse_info: dict[str, str],
    vinculo_stats: dict[str, int],
    fila_revisao: list[str],
    achados: list[Achado],
    stats: dict,
    params: Parametros,
) -> str:
    linhas: list[str] = []
    linhas.append(f"# Auditoria de Pessoal — calibração da competência {competencia}")
    linhas.append("")
    linhas.append(
        "> **Relatório de calibração** (Passo 0). Os itens abaixo são *candidatos* a Achado: "
        "servem para validar regras, parâmetros e classificação de escalas com o Auditor — "
        "não são conclusões. Documento com dados sensíveis: não versionar, não circular."
    )
    linhas.append("")

    linhas.append("## Cobertura de parse (confiabilidade dos números)")
    linhas.append("")
    for k, vtxt in parse_info.items():
        linhas.append(f"- **{k}**: {vtxt}")
    linhas.append("")

    linhas.append("## Vínculo ponto ↔ folha")
    linhas.append("")
    linhas.append(
        f"- Automático por CPF: **{vinculo_stats['cpf']}** · por nome: **{vinculo_stats['nome']}** · "
        f"fuzzy (confirmar): **{vinculo_stats['fuzzy']}**"
    )
    linhas.append(
        f"- Órfãos: **{vinculo_stats['so_espelho']}** só no ponto · **{vinculo_stats['so_folha']}** só na folha"
    )
    linhas.append("")

    # Sumário por regra
    linhas.append("## Sumário por Regra")
    linhas.append("")
    linhas.append("| Regra | Candidatos | Críticos | Altos | R$ estimado |")
    linhas.append("|---|---:|---:|---:|---:|")
    total_valor = 0.0
    for rid in sorted(NOMES_REGRAS, key=lambda r: int(r[1:])):
        grupo = [a for a in achados if a.regra == rid]
        if not grupo:
            continue
        valor = sum(a.valor_estimado or 0 for a in grupo)
        total_valor += valor
        criticos = sum(1 for a in grupo if a.severidade == "CRITICA")
        altos = sum(1 for a in grupo if a.severidade == "ALTA")
        linhas.append(
            f"| {rid} — {NOMES_REGRAS[rid]} | {len(grupo)} | {criticos} | {altos} | {_brl(valor) if valor else '—'} |"
        )
    linhas.append("")
    linhas.append(f"_Valores estimados pelo salário-hora; somatório bruto {_brl(total_valor)} — régua, não passivo._")
    linhas.append("")

    # Detalhe por regra
    for rid in sorted(NOMES_REGRAS, key=lambda r: int(r[1:])):
        grupo = [a for a in achados if a.regra == rid]
        if not grupo:
            continue
        linhas.append(f"## {rid} — {NOMES_REGRAS[rid]} ({len(grupo)})")
        linhas.append("")
        for a in grupo[:MAX_POR_REGRA]:
            valor = f" · ~{_brl(a.valor_estimado)}" if a.valor_estimado else ""
            linhas.append(f"- **[{a.severidade}] {a.pessoa}** — {a.descricao}{valor}")
            linhas.append(f"  - {a.evidencia}")
        if len(grupo) > MAX_POR_REGRA:
            linhas.append(f"- _… e mais {len(grupo) - MAX_POR_REGRA} candidato(s) (ver JSON)._")
        linhas.append("")

    # Calibração
    linhas.append("## Para a sessão de calibração com o Auditor")
    linhas.append("")
    linhas.append("### Escalas (CH) a classificar")
    linhas.append("")
    linhas.append("| CH | usos no mês | grade | leitura sugerida |")
    linhas.append("|---|---:|---|---|")
    for ch, info in sorted(stats["escalas"].items(), key=lambda kv: -kv[1]["usos"]):
        g = info["grade_min"]
        grade_txt = f"{g // 60}h{g % 60:02d}" if g else "?"
        linhas.append(f"| {ch} | {info['usos']} | {grade_txt} | {_classificar_grade(g)} |")
    linhas.append("")

    if stats["cargos_sem_ponto"]:
        linhas.append("### Cargos que apareceram sem ponto (candidatos a isentos — art. 62)")
        linhas.append("")
        for cargo, n in sorted(stats["cargos_sem_ponto"].items(), key=lambda kv: -kv[1]):
            linhas.append(f"- {cargo or '(sem cargo)'}: {n}")
        linhas.append("")

    auto = stats["automaticas_por_depto"]
    if auto:
        linhas.append("### Batidas automáticas por departamento (insumo da reparametrização do RH iD)")
        linhas.append("")
        linhas.append("| Departamento | pré-assinaladas | marcações reais |")
        linhas.append("|---|---:|---:|")
        for depto, (p_, reais) in sorted(auto.items(), key=lambda kv: -kv[1][0])[:15]:
            linhas.append(f"| {depto} | {p_} | {reais} |")
        linhas.append("")

    if fila_revisao:
        linhas.append("### Fila de revisão de Vínculo")
        linhas.append("")
        for item in fila_revisao:
            linhas.append(f"- {item}")
        linhas.append("")

    linhas.append("### Parâmetros usados")
    linhas.append("")
    linhas.append(
        f"- Tolerância diária: {params.tolerancia_dia_min} min · teto HE: {params.teto_he_dia_min // 60}h/dia, "
        f"{params.teto_he_mes_h:.0f}h/mês · interjornada: {params.interjornada_min // 60}h · "
        f"jornada máxima: {params.jornada_max_min // 60}h · conciliação HE ±{params.conciliacao_he_tolerancia_h:.0f}h"
    )
    linhas.append(f"- Cargos isentos de ponto: {params.cargos_isentos_ponto or '(nenhum — preencher na calibração)'}")
    linhas.append("")
    return "\n".join(linhas)
