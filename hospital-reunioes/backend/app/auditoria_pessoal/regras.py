"""Catálogo de Regras da v1 (grilling de 12/06/2026): R1–R10.

Cada Regra recebe os Vínculos e os Parâmetros e devolve Achados com evidência.
Tudo aqui é régua de CALIBRAÇÃO: thresholds conservadores, linguagem de
verificação (não acusação). Valores em R$ são estimativas pelo salário-hora.
"""

from __future__ import annotations

from datetime import date

from .modelos import Achado, DiaPonto, EspelhoFuncionario, FolhaRegistro, Vinculo
from .parametros import Parametros
from .vinculo import cpf_valido, normalizar_nome


def _grade_min(func: EspelhoFuncionario, ch: str | None) -> int | None:
    """Duração (min) da grade contratual do CH, com overnight normalizado."""
    if ch is None or ch not in func.grades:
        return None
    total = 0
    for ent, sai in func.grades[ch]:
        if sai <= ent:
            sai += 1440
        total += sai - ent
    return total


def _dur_liq(dia: DiaPonto) -> int:
    return dia.duracao_liquida()


def _duracao_suspeita(dia: DiaPonto) -> bool:
    """DURAÇÃO impressa que não fecha com nenhuma leitura do dia (dado podre)."""
    if dia.duracao is None:
        return False
    if abs(dia.duracao_liquida() - dia.duracao) <= 10:
        return False
    bruta = dia.presenca_bruta()
    if bruta is not None and abs(bruta - dia.duracao) <= 10:
        return False  # RH iD imprime presença bruta em plantões overnight
    return True


def _he_estimada_dia(func: EspelhoFuncionario, dia: DiaPonto, p: Parametros) -> tuple[int, bool]:
    """(minutos extras estimados no dia, dia fora de escala?)."""
    dur = _dur_liq(dia)
    if dur == 0:
        return 0, False
    grade = _grade_min(func, dia.ch)
    if grade is None:
        return dur, True  # trabalhou sem CH: dia inteiro fora da escala
    return max(0, dur - grade - p.tolerancia_dia_min), False


def _he_paga_h(folha: FolhaRegistro) -> float:
    return sum(r.referencia for r in folha.rubricas_por_descricao("HORAS EXTRAS") if r.tipo == "P")


def _tem_ferias_ou_afastamento(folha: FolhaRegistro) -> bool:
    if folha.rubricas_por_descricao("FERIAS", "FÉRIAS", "AFAST"):
        return True
    return bool(folha.observacoes)


def _abs_min(dia: DiaPonto, minuto: int) -> int:
    return dia.data.toordinal() * 1440 + minuto


def _brl(v: float) -> str:
    return (f"R$ {v:,.2f}").replace(",", "X").replace(".", ",").replace("X", ".")


def _h(minutos: int) -> str:
    return f"{minutos // 60}h{minutos % 60:02d}"


def rodar_regras(vinculos: list[Vinculo], p: Parametros) -> tuple[list[Achado], dict]:
    achados: list[Achado] = []
    stats: dict = {
        "automaticas_por_depto": {},  # depto -> [batidas P, marcações reais]
        "escalas": {},  # ch -> {"usos": n, "grade_min": x}
        "cargos_sem_ponto": {},
    }
    for v in vinculos:
        if v.espelho is not None:
            _acumular_stats(v.espelho, stats)
        achados += _r1_conciliacao_he(v, p)
        achados += _r2_teto_he(v, p)
        achados += _r4_atrasos_faltas(v, p)
        achados += _r5_noturno(v, p)
        achados += _r6_interjornada(v, p)
        achados += _r7_dias_corridos(v, p)
        achados += _r8_jornada_longa(v, p)
        achados += _r9_intervalo(v, p)
    achados += _r3_pago_sem_ponto(vinculos, p, stats)
    achados += _r10_cadastro(vinculos, p)
    ordem = {"CRITICA": 0, "ALTA": 1, "MEDIA": 2, "INFO": 3}
    achados.sort(key=lambda a: (a.regra, ordem.get(a.severidade, 9), -(a.valor_estimado or 0)))
    return achados, stats


def _acumular_stats(e: EspelhoFuncionario, stats: dict) -> None:
    auto = stats["automaticas_por_depto"].setdefault(e.departamento or "(sem depto)", [0, 0])
    for dia in e.dias:
        auto[0] += sum(1 for t in dia.tratamentos if t.ocorr == "P")
        auto[1] += len(dia.marcacoes)
        if dia.ch:
            esc = stats["escalas"].setdefault(dia.ch, {"usos": 0, "grade_min": _grade_min(e, dia.ch)})
            esc["usos"] += 1


# R1 — Conciliação de horas extras: pago vs batido -------------------------
def _r1_conciliacao_he(v: Vinculo, p: Parametros) -> list[Achado]:
    if v.espelho is None or v.folha is None:
        return []
    he_paga = _he_paga_h(v.folha)
    he_min = 0
    fora_escala_min = 0
    dias_fora = 0
    for dia in v.espelho.dias:
        extra, fora = _he_estimada_dia(v.espelho, dia, p)
        if fora:
            fora_escala_min += extra
            dias_fora += 1
        else:
            he_min += extra
    he_batida = (he_min + fora_escala_min) / 60.0
    delta = he_paga - he_batida
    if abs(delta) <= p.conciliacao_he_tolerancia_h:
        return []
    extra_info = f" ({dias_fora} dia(s) fora de escala = {_h(fora_escala_min)})" if dias_fora else ""
    if delta > 0:
        return [
            Achado(
                "R1",
                "Conciliação ponto×folha",
                "ALTA",
                v.rotulo,
                f"HE paga ({he_paga:.1f}h) excede a estimada pelo ponto ({he_batida:.1f}h) em {delta:.1f}h",
                f"rubricas HE={he_paga:.1f}h; espelho estima {he_batida:.1f}h{extra_info}",
                valor_estimado=delta * v.folha.valor_hora * 1.5,
            )
        ]
    return [
        Achado(
            "R1",
            "Conciliação ponto×folha",
            "MEDIA",
            v.rotulo,
            f"Ponto registra {-delta:.1f}h além da HE paga (banco de horas? passivo?)",
            f"espelho estima {he_batida:.1f}h{extra_info}; rubricas HE={he_paga:.1f}h",
            valor_estimado=-delta * v.folha.valor_hora * 1.5,
        )
    ]


# R2 — Horas extras acima do teto legal ------------------------------------
def _r2_teto_he(v: Vinculo, p: Parametros) -> list[Achado]:
    achados: list[Achado] = []
    if v.folha is not None:
        he_paga = _he_paga_h(v.folha)
        if he_paga > p.teto_he_mes_h:
            sev = "CRITICA" if he_paga > p.teto_he_mes_h * 1.5 else "ALTA"
            valor = sum(r.valor for r in v.folha.rubricas_por_descricao("HORAS EXTRAS") if r.tipo == "P")
            achados.append(
                Achado(
                    "R2",
                    "HE acima do teto",
                    sev,
                    v.rotulo,
                    f"{he_paga:.1f}h extras pagas no mês (referência legal ≈ {p.teto_he_mes_h:.0f}h; CLT art. 59)",
                    f"rubricas de HE somam {_brl(valor)}",
                    valor_estimado=valor,
                )
            )
    if v.espelho is not None:
        dias_estouro = []
        for dia in v.espelho.dias:
            extra, fora = _he_estimada_dia(v.espelho, dia, p)
            if not fora and extra > p.teto_he_dia_min:
                dias_estouro.append((dia.data, extra))
        if len(dias_estouro) >= 3:
            pior = max(dias_estouro, key=lambda d: d[1])
            achados.append(
                Achado(
                    "R2",
                    "HE acima do teto",
                    "MEDIA",
                    v.rotulo,
                    f"{len(dias_estouro)} dia(s) com mais de {p.teto_he_dia_min // 60}h extras pelo ponto",
                    f"pior dia {pior[0].strftime('%d/%m')}: {_h(pior[1])} além da grade",
                )
            )
    return achados


# R3 — Pago sem ponto -------------------------------------------------------
def _r3_pago_sem_ponto(vinculos: list[Vinculo], p: Parametros, stats: dict) -> list[Achado]:
    achados: list[Achado] = []
    for v in vinculos:
        f = v.folha
        if f is None:
            continue
        situacao_ok = f.situacao and any(s.lower() in f.situacao.lower() for s in p.situacoes_sem_ponto)
        isento = any(c.upper() in f.cargo.upper() for c in p.cargos_isentos_ponto if c)
        if situacao_ok or isento:
            continue
        sem_espelho = v.espelho is None
        sem_marcacao = v.espelho is not None and not any(d.trabalhou for d in v.espelho.dias)
        if not (sem_espelho or sem_marcacao):
            continue
        if _tem_ferias_ou_afastamento(f):
            continue
        rotulo_tipo = "sem espelho no mês" if sem_espelho else "espelho sem nenhuma marcação"
        sev = "INFO" if f.vinculo.lower() != "celetista" else "ALTA"
        achados.append(
            Achado(
                "R3",
                "Pago sem ponto",
                sev,
                v.rotulo,
                f"Recebeu {_brl(f.proventos)} ({rotulo_tipo})",
                f"situação='{f.situacao}', vínculo={f.vinculo}, cargo={f.cargo} "
                "— confirmar se isento de ponto (art. 62)",
                valor_estimado=f.proventos,
            )
        )
        stats["cargos_sem_ponto"][f.cargo] = stats["cargos_sem_ponto"].get(f.cargo, 0) + 1
    return achados


# R4 — Atrasos e faltas vs descontos ---------------------------------------
def _r4_atrasos_faltas(v: Vinculo, p: Parametros) -> list[Achado]:
    if v.espelho is None or v.folha is None:
        return []
    f = v.folha
    if f.situacao and any(s.lower() in f.situacao.lower() for s in p.situacoes_sem_ponto):
        return []
    achados: list[Achado] = []
    atraso_min = 0
    faltas_dias = 0
    for dia in v.espelho.dias:
        if v.espelho.admissao and dia.data < v.espelho.admissao:
            continue
        if dia.escala_prevista and not dia.trabalhou:
            faltas_dias += 1
            continue
        if not dia.trabalhou or dia.ch not in v.espelho.grades:
            continue
        ent_grade = v.espelho.grades[dia.ch][0][0]
        ent_real = dia.jornada[0]
        if ent_real is None:
            continue
        atraso = ent_real - ent_grade
        if p.tolerancia_dia_min < atraso <= p.atraso_max_min:
            atraso_min += atraso
    atrasos_h = atraso_min / 60.0
    desc_atraso = sum(r.referencia for r in f.rubricas_por_descricao("ATRASO") if r.tipo == "D")
    delta = atrasos_h - desc_atraso
    if abs(delta) > p.conciliacao_atraso_tolerancia_h:
        if delta > 0:
            achados.append(
                Achado(
                    "R4",
                    "Atrasos/faltas vs desconto",
                    "MEDIA",
                    v.rotulo,
                    f"{atrasos_h:.1f}h de atraso no ponto, só {desc_atraso:.1f}h descontadas (leniência?)",
                    f"diferença {delta:.1f}h ≈ {_brl(delta * f.valor_hora)}",
                    valor_estimado=delta * f.valor_hora,
                )
            )
        else:
            achados.append(
                Achado(
                    "R4",
                    "Atrasos/faltas vs desconto",
                    "ALTA",
                    v.rotulo,
                    f"Desconto de atraso ({desc_atraso:.1f}h) maior que o atraso batido ({atrasos_h:.1f}h)",
                    f"diferença {-delta:.1f}h ≈ {_brl(-delta * f.valor_hora)} descontados a mais",
                    valor_estimado=-delta * f.valor_hora,
                )
            )
    if not _tem_ferias_ou_afastamento(f):
        faltas_folha = sum(
            r.referencia
            for r in f.rubricas
            if r.tipo == "D" and "DIAS FALTAS" in r.descricao.upper() and "DSR" not in r.descricao.upper()
        )
        if abs(faltas_dias - faltas_folha) >= 1:
            # muitos dias de "escala sem marcação" = provável folga de escala
            # alternada (12x36) que o RH iD imprime com CH — calibrar, não cobrar
            escala_alternada = faltas_dias >= 8
            sev = "INFO" if escala_alternada else "MEDIA"
            nota = (
                " — padrão sugere folga de escala alternada (12x36?); validar na calibração"
                if escala_alternada
                else "; conferir abonos/atestados"
            )
            sentido = "não descontada(s)" if faltas_dias > faltas_folha else "descontada(s) sem lastro no ponto"
            achados.append(
                Achado(
                    "R4",
                    "Atrasos/faltas vs desconto",
                    sev,
                    v.rotulo,
                    f"Faltas: {faltas_dias} dia(s) de escala sem marcação vs {faltas_folha:.0f} "
                    f"descontado(s) — {abs(faltas_dias - faltas_folha):.0f} {sentido}",
                    f"dias com CH impresso e nenhuma batida{nota}",
                )
            )
    return achados


# R5 — Adicional noturno ----------------------------------------------------
def _r5_noturno(v: Vinculo, p: Parametros) -> list[Achado]:
    if v.espelho is None or v.folha is None:
        return []
    noturno_min = 0
    for dia in v.espelho.dias:
        for ent, sai in dia.pares_jornada():
            noturno_min += max(0, min(sai, 1740) - max(ent, 1320))  # 22:00–05:00 (+1d)
            noturno_min += max(0, min(sai, 300) - max(ent, 0))  # 00:00–05:00 do próprio dia
    tem_rubrica = bool(v.folha.rubricas_por_descricao("NOTURNO"))
    if noturno_min > p.noturno_minimo_mes_min and not tem_rubrica:
        valor = (noturno_min / 60.0) * v.folha.valor_hora * 0.2
        return [
            Achado(
                "R5",
                "Adicional noturno",
                "ALTA",
                v.rotulo,
                f"{_h(noturno_min)} batidas entre 22h–5h sem rubrica de adicional noturno",
                f"estimativa do adicional (20%): {_brl(valor)}",
                valor_estimado=valor,
            )
        ]
    if tem_rubrica and noturno_min < 30:
        valor = sum(r.valor for r in v.folha.rubricas_por_descricao("NOTURNO") if r.tipo == "P")
        return [
            Achado(
                "R5",
                "Adicional noturno",
                "MEDIA",
                v.rotulo,
                f"Recebe adicional noturno ({_brl(valor)}) com {_h(noturno_min)} noturnos batidos no mês",
                "conferir escala contratual noturna vs ponto",
                valor_estimado=valor,
            )
        ]
    return []


# R6 — Interjornada mínima --------------------------------------------------
def _r6_interjornada(v: Vinculo, p: Parametros) -> list[Achado]:
    e = v.espelho
    if e is None:
        return []
    eventos: list[tuple[int, int]] = []  # (início_abs, fim_abs) por dia trabalhado
    for dia in e.dias:
        pares = dia.pares_jornada()
        if not pares:
            continue
        eventos.append((_abs_min(dia, pares[0][0]), _abs_min(dia, max(s for _, s in pares))))
    eventos.sort()
    violacoes: list[str] = []
    pior = 10**6
    for (_, fim), (ini_seg, _) in zip(eventos, eventos[1:]):
        gap = ini_seg - fim
        # plantão noturno partido na virada (19h→23:59 + 00:00→07h no RH iD):
        # mesmo plantão, não violação de interjornada
        if gap < 120 and (fim % 1440) >= 1380:
            continue
        if 0 < gap < p.interjornada_min:
            dia_seg = date.fromordinal(ini_seg // 1440)
            violacoes.append(f"{dia_seg.strftime('%d/%m')}: {_h(gap)}")
            pior = min(pior, gap)
    if not violacoes:
        return []
    sev = "CRITICA" if pior < 6 * 60 else "ALTA"
    return [
        Achado(
            "R6",
            "Interjornada < 11h",
            sev,
            v.rotulo,
            f"{len(violacoes)} intervalo(s) entre jornadas abaixo de 11h (CLT art. 66)",
            f"menor descanso: {_h(pior)}; ocorrências: {', '.join(violacoes[:6])}",
        )
    ]


# R7 — Mais de 6 dias corridos ----------------------------------------------
def _r7_dias_corridos(v: Vinculo, p: Parametros) -> list[Achado]:
    e = v.espelho
    if e is None:
        return []
    dias_trab = sorted({d.data.toordinal() for d in e.dias if d.trabalhou})
    melhor_seq = seq = 1 if dias_trab else 0
    for a, b in zip(dias_trab, dias_trab[1:]):
        seq = seq + 1 if b == a + 1 else 1
        melhor_seq = max(melhor_seq, seq)
    if melhor_seq <= p.max_dias_corridos:
        return []
    sev = "CRITICA" if melhor_seq >= 10 else "ALTA"
    return [
        Achado(
            "R7",
            "Dias corridos sem descanso",
            sev,
            v.rotulo,
            f"{melhor_seq} dias consecutivos trabalhados (CLT art. 67 prevê descanso semanal)",
            f"{len(dias_trab)} dias trabalhados no mês",
        )
    ]


# R8 — Jornada diária excessiva ----------------------------------------------
def _r8_jornada_longa(v: Vinculo, p: Parametros) -> list[Achado]:
    e = v.espelho
    if e is None:
        return []
    longas = [(d.data, _dur_liq(d), d.ch) for d in e.dias if _dur_liq(d) > p.jornada_max_min]
    if not longas:
        return []
    pior = max(longas, key=lambda x: x[1])
    sev = "CRITICA" if pior[1] > p.jornada_critica_min else "ALTA"
    return [
        Achado(
            "R8",
            "Jornada diária excessiva",
            sev,
            v.rotulo,
            f"{len(longas)} dia(s) acima de {p.jornada_max_min // 60}h de jornada",
            f"pior dia {pior[0].strftime('%d/%m')}: {_h(pior[1])} (CH={pior[2] or 'sem escala'}) "
            "— plantão 24h exige parecer (art. 59-A cobre 12x36)",
        )
    ]


# R9 — Intervalo fabricado/suprimido ------------------------------------------
def _r9_intervalo(v: Vinculo, p: Parametros) -> list[Achado]:
    e = v.espelho
    if e is None:
        return []
    dias_sem_intervalo = []
    for d in e.dias:
        dur = _dur_liq(d)
        if dur <= p.intervalo_obrigatorio_apos_min:
            continue
        pares = d.pares_jornada()
        sem_pausa = len(pares) == 1
        fabricado = any(t.ocorr == "P" for t in d.tratamentos)
        if sem_pausa and not fabricado:
            dias_sem_intervalo.append((d.data, dur))
    if not dias_sem_intervalo:
        return []
    valor = None
    if v.folha is not None:
        valor = len(dias_sem_intervalo) * v.folha.valor_hora * 1.5  # art. 71 §4º: 1h indenizada +50%
    sev = "ALTA" if len(dias_sem_intervalo) >= 3 else "MEDIA"
    pior = max(dias_sem_intervalo, key=lambda x: x[1])
    return [
        Achado(
            "R9",
            "Intervalo suprimido",
            sev,
            v.rotulo,
            f"{len(dias_sem_intervalo)} dia(s) com mais de 6h sem nenhum intervalo (nem batido nem pré-assinalado)",
            f"pior dia {pior[0].strftime('%d/%m')}: {_h(pior[1])} corridas; passivo potencial (art. 71 §4º)",
            valor_estimado=valor,
        )
    ]


# R10 — Qualidade de cadastro -------------------------------------------------
def _r10_cadastro(vinculos: list[Vinculo], p: Parametros) -> list[Achado]:
    achados: list[Achado] = []
    cpf_igual_pis = []
    cpf_invalido = []
    sem_situacao = []
    nome_divergente = []
    for v in vinculos:
        e, f = v.espelho, v.folha
        if e is not None:
            dig_cpf = "".join(filter(str.isdigit, e.cpf or ""))
            dig_pis = "".join(filter(str.isdigit, e.pis or ""))
            if dig_cpf and dig_cpf == dig_pis:
                cpf_igual_pis.append(f"{e.nome} (mat {e.matricula})")
            elif dig_cpf and not cpf_valido(dig_cpf):
                cpf_invalido.append(f"{e.nome} (mat {e.matricula}): {e.cpf}")
        if f is not None:
            if not f.situacao:
                sem_situacao.append(f"{f.nome} (empr {f.empr})")
            dig = "".join(filter(str.isdigit, f.cpf or ""))
            if dig and not cpf_valido(dig):
                cpf_invalido.append(f"{f.nome} (empr {f.empr}, folha): {f.cpf}")
        if e is not None and f is not None and v.metodo in ("cpf",):
            if normalizar_nome(e.nome) != normalizar_nome(f.nome):
                nome_divergente.append(f"{e.nome} (ponto) ≠ {f.nome} (folha)")
    if cpf_igual_pis:
        achados.append(
            Achado(
                "R10",
                "Qualidade de cadastro",
                "ALTA",
                f"{len(cpf_igual_pis)} funcionário(s)",
                f"Campo CPF do RH iD preenchido com o PIS em {len(cpf_igual_pis)} cadastro(s) "
                "— quebra o cruzamento com o Domínio",
                "; ".join(cpf_igual_pis[:8]) + (" …" if len(cpf_igual_pis) > 8 else ""),
            )
        )
    if cpf_invalido:
        achados.append(
            Achado(
                "R10",
                "Qualidade de cadastro",
                "MEDIA",
                f"{len(cpf_invalido)} cadastro(s)",
                "CPF com dígito verificador inválido",
                "; ".join(cpf_invalido[:8]) + (" …" if len(cpf_invalido) > 8 else ""),
            )
        )
    if sem_situacao:
        achados.append(
            Achado(
                "R10",
                "Qualidade de cadastro",
                "INFO",
                f"{len(sem_situacao)} registro(s)",
                "Registro da Folha sem situação preenchida",
                "; ".join(sem_situacao[:8]),
            )
        )
    if nome_divergente:
        achados.append(
            Achado(
                "R10",
                "Qualidade de cadastro",
                "INFO",
                f"{len(nome_divergente)} caso(s)",
                "Nome divergente entre RH iD e Domínio (mesmo CPF)",
                "; ".join(nome_divergente[:6]) + (" …" if len(nome_divergente) > 6 else ""),
            )
        )
    implausiveis = []
    for v in vinculos:
        if v.espelho is None:
            continue
        for d in v.espelho.dias:
            if _duracao_suspeita(d):
                implausiveis.append(
                    f"{v.espelho.nome} (mat {v.espelho.matricula}) {d.data.strftime('%d/%m')}: "
                    f"impresso {(d.duracao or 0) // 60}h{(d.duracao or 0) % 60:02d}"
                )
    if implausiveis:
        achados.append(
            Achado(
                "R10",
                "Qualidade de cadastro",
                "MEDIA",
                f"{len(implausiveis)} dia(s)",
                "DURAÇÃO impressa pelo RH iD não fecha com as marcações do dia (batida perdida/tratamento incorreto)",
                "; ".join(implausiveis[:6]) + (" …" if len(implausiveis) > 6 else ""),
            )
        )
    return achados
