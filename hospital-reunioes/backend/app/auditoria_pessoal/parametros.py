"""Parâmetros das Regras — defaults da CLT, calibráveis em sessão com o Auditor.

No app, estes valores virarão seeds de tabela (decisão do grilling de 12/06/2026);
na calibração local, edite aqui e re-rode o CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Parametros:
    # CLT art. 58 §1º — franquia diária de marcação (min)
    tolerancia_dia_min: int = 10
    # CLT art. 59 — teto de horas extras (estimativa mensal: 2h × 22 dias úteis)
    teto_he_dia_min: int = 120
    teto_he_mes_h: float = 44.0
    # CLT art. 66 — intervalo mínimo entre jornadas (min)
    interjornada_min: int = 11 * 60
    # CLT art. 67 — máximo de dias corridos sem descanso semanal
    max_dias_corridos: int = 6
    # Jornada diária acima disso é achado; acima de `jornada_critica_min` é crítico
    jornada_max_min: int = 12 * 60
    jornada_critica_min: int = 16 * 60
    # CLT art. 71 — jornada > 6h exige 1h de intervalo
    intervalo_obrigatorio_apos_min: int = 6 * 60
    # Adicional noturno (22h–5h): mínimo batido no mês p/ exigir rubrica (min)
    noturno_minimo_mes_min: int = 120
    # Conciliação de HE: divergência mensal tolerada entre pago e batido (h)
    conciliacao_he_tolerancia_h: float = 6.0
    # Atrasos: divergência tolerada entre descontado e batido (h)
    conciliacao_atraso_tolerancia_h: float = 1.0
    # Atraso acima disso (min) é tratado como falta parcial, não atraso
    atraso_max_min: int = 240
    # Vínculo: score mínimo do fuzzy e distância mínima para o 2º colocado
    fuzzy_score_min: float = 0.87
    fuzzy_gap_min: float = 0.04
    # Cargos isentos de ponto (CLT art. 62) — preencher na calibração
    cargos_isentos_ponto: list[str] = field(default_factory=list)
    # Situações da Folha que dispensam ponto no mês
    situacoes_sem_ponto: list[str] = field(
        default_factory=lambda: [
            "Doença",
            "Licença maternidade",
            "Licença sem direito",
            "Demitido",
        ]
    )
