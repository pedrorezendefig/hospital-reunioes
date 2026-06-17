"""Parser do Espelho de Ponto Eletrônico (RH iD, PDFsharp — 1 funcionário/página).

Recebe o texto extraído com `pdftotext -layout`. As colunas variam de posição
entre páginas; cada página é fatiada usando a própria linha de cabeçalho da
tabela como âncora, e cada token é atribuído à coluna de centro mais próximo.
"""

from __future__ import annotations

import re
from datetime import date

from .modelos import DiaPonto, EspelhoFuncionario, Tratamento

RE_DIA = re.compile(r"^\s*(\d{2})/(\d{2})/(\d{2}) - (SEG|TER|QUA|QUI|SEX|SAB|DOM)\b")
RE_HHMM = re.compile(r"^(\d{1,2}):(\d{2})$")
RE_CH = re.compile(r"^\d{5}$")
RE_GRADE = re.compile(r"^\s*(\d{5})\s+(\d{2}:\d{2})\s+(\d{2}:\d{2})(?:\s+(\d{2}:\d{2})\s+(\d{2}:\d{2}))?\s*$")

COLUNAS = ["ENT. 1", "SAÍ. 1", "ENT. 2", "SAÍ. 2", "ENT. 3", "SAÍ. 3", "DURAÇÃO", "CH", "HORÁRIO", "OCORR"]
FIM_TABELA = "(I)=Incluído"


def _min(hhmm: str) -> int | None:
    m = RE_HHMM.match(hhmm)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _data(dd: str, mm: str, yy: str) -> date:
    return date(2000 + int(yy), int(mm), int(dd))


def _entre(linha: str, label: str, stops: list[str]) -> str:
    """Trecho da linha após `label`, parando no primeiro stop presente."""
    i = linha.find(label)
    if i < 0:
        return ""
    trecho = linha[i + len(label) :]
    corte = len(trecho)
    for stop in stops:
        j = trecho.find(stop)
        if 0 <= j < corte:
            corte = j
    return trecho[:corte].strip()


def _posicoes_colunas(header: str) -> dict[str, tuple[int, float]]:
    """label -> (início, centro) na linha de cabeçalho da tabela."""
    pos: dict[str, tuple[int, float]] = {}
    for label in COLUNAS + ["MOTIVO"]:
        i = header.find(label)
        if i >= 0:
            pos[label] = (i, i + len(label) / 2.0)
    return pos


def parse_espelho(texto: str) -> tuple[list[EspelhoFuncionario], list[str]]:
    """Retorna (funcionários, avisos globais). Texto = saída de pdftotext -layout."""
    funcionarios: list[EspelhoFuncionario] = []
    avisos: list[str] = []
    paginas = texto.split("\f")
    for n_pag, pagina in enumerate(paginas, start=1):
        if "NOME:" not in pagina:
            if pagina.strip():
                avisos.append(f"página {n_pag}: sem bloco de funcionário — ignorada")
            continue
        func = _parse_pagina(n_pag, pagina.splitlines())
        if func is not None:
            funcionarios.append(func)
        else:
            avisos.append(f"página {n_pag}: falha ao montar funcionário")
    return funcionarios, avisos


def _parse_pagina(n_pag: int, linhas: list[str]) -> EspelhoFuncionario | None:
    nome = pis = cpf = matricula = centro_custo = departamento = cargo = ""
    admissao: date | None = None
    pos: dict[str, tuple[int, float]] = {}
    func: EspelhoFuncionario | None = None
    dia_atual: DiaPonto | None = None
    em_tabela = False
    em_grade = False

    for linha in linhas:
        if "NOME:" in linha:
            nome = re.sub(r"\s+", " ", _entre(linha, "NOME:", ["PIS/PASEP:"]))
            pis = _entre(linha, "PIS/PASEP:", ["ADMISSÃO:"])
            adm = _entre(linha, "ADMISSÃO:", [])
            m = re.match(r"(\d{2})/(\d{2})/(\d{4})", adm)
            if m:
                admissao = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            continue
        if "MATRÍCULA:" in linha and "CPF:" in linha:
            centro_custo = _entre(linha, "CENTRO DE CUSTO:", ["CPF:"])
            cpf = _entre(linha, "CPF:", ["MATRÍCULA:"])
            matricula = _entre(linha, "MATRÍCULA:", [])
            continue
        if "DEPARTAMENTO:" in linha:
            departamento = _entre(linha, "DEPARTAMENTO:", ["CARGO:"])
            cargo = _entre(linha, "CARGO:", [])
            continue
        if "DURAÇÃO" in linha and "DIA" not in linha and not em_tabela:
            # linha B do cabeçalho da tabela (a linha A tem 'MARCAÇÕES REGISTRADAS')
            pass
        if "ENT. 1" in linha and "DURAÇÃO" in linha:
            pos = _posicoes_colunas(linha)
            func = EspelhoFuncionario(
                pagina=n_pag,
                nome=nome,
                pis=pis,
                cpf=cpf,
                matricula=matricula,
                admissao=admissao,
                centro_custo=centro_custo,
                departamento=departamento,
                cargo=cargo,
            )
            em_tabela = True
            continue
        if em_tabela and FIM_TABELA in linha:
            em_tabela = False
            continue
        if em_tabela and func is not None:
            dia_atual = _parse_linha_tabela(linha, pos, func, dia_atual)
            continue
        if "CÓDIGO DO HORÁRIO" in linha:
            em_grade = True
            continue
        if em_grade and func is not None:
            m = RE_GRADE.match(linha)
            if m:
                pares = [(_min(m.group(2)), _min(m.group(3)))]
                if m.group(4):
                    pares.append((_min(m.group(4)), _min(m.group(5))))
                func.grades[m.group(1)] = [(e, s) for e, s in pares if e is not None and s is not None]
    return func


def _parse_linha_tabela(
    linha: str,
    pos: dict[str, tuple[int, float]],
    func: EspelhoFuncionario,
    dia_atual: DiaPonto | None,
) -> DiaPonto | None:
    m_dia = RE_DIA.match(linha)
    if m_dia:
        dia = DiaPonto(data=_data(m_dia.group(1), m_dia.group(2), m_dia.group(3)), dow=m_dia.group(4))
        func.dias.append(dia)
        _atribuir_tokens(linha, m_dia.end(), pos, dia, func)
        return dia
    # linha de continuação: só tratamentos (ou vazia)
    if not linha.strip():
        return dia_atual
    inicio_trat = pos.get("HORÁRIO", (10**6, 0))[0] - 6
    tokens = [(t.group(0), t.start()) for t in re.finditer(r"\S+", linha)]
    if tokens and all(start >= inicio_trat for _, start in tokens) and dia_atual is not None:
        _atribuir_tratamento(linha, pos, dia_atual)
        return dia_atual
    if tokens:
        func.avisos_parse.append(f"linha não reconhecida na tabela: {linha.strip()[:80]!r}")
    return dia_atual


def _atribuir_tokens(
    linha: str, fim_data: int, pos: dict[str, tuple[int, float]], dia: DiaPonto, func: EspelhoFuncionario
) -> None:
    limite_marcacoes = pos["ENT. 1"][0] - 4
    inicio_trat = pos.get("HORÁRIO", (10**6, 0))[0] - 6
    jornada_labels = COLUNAS[:6]
    for t in re.finditer(r"\S+", linha):
        token, start = t.group(0), t.start()
        if start < fim_data:
            continue
        if start >= inicio_trat:
            _atribuir_tratamento(linha, pos, dia)
            break
        centro = start + len(token) / 2.0
        if start < limite_marcacoes:
            v = _min(token)
            if v is not None:
                dia.marcacoes.append(v)
            else:
                func.avisos_parse.append(f"{dia.data}: marcação inválida {token!r}")
            continue
        # coluna de centro mais próximo entre ENT/SAÍ 1-3, DURAÇÃO e CH
        label = min(
            jornada_labels + ["DURAÇÃO", "CH"],
            key=lambda lb: abs(pos[lb][1] - centro) if lb in pos else 10**6,
        )
        if label == "DURAÇÃO":
            m = re.match(r"^(\d{1,2}):(\d{2})$", token)
            if m:
                dia.duracao = int(m.group(1)) * 60 + int(m.group(2))
            else:
                func.avisos_parse.append(f"{dia.data}: duração inválida {token!r}")
        elif label == "CH":
            if RE_CH.match(token):
                dia.ch = token
            else:
                func.avisos_parse.append(f"{dia.data}: CH inválido {token!r}")
        else:
            v = _min(token)
            if v is None:
                func.avisos_parse.append(f"{dia.data}: jornada inválida {token!r} em {label}")
            else:
                dia.jornada[jornada_labels.index(label)] = v


def _atribuir_tratamento(linha: str, pos: dict[str, tuple[int, float]], dia: DiaPonto) -> None:
    i_horario = pos.get("HORÁRIO", (0, 0))[0] - 6
    i_motivo = pos.get("MOTIVO", (len(linha), 0))[0] - 4
    trecho = linha[max(i_horario, 0) : max(i_motivo, 0)]
    motivo = linha[max(i_motivo, 0) :].strip()
    horario: int | None = None
    ocorr = ""
    for t in re.finditer(r"\S+", trecho):
        token = t.group(0)
        v = _min(token)
        if v is not None and horario is None:
            horario = v
        elif token in ("I", "P", "D"):
            ocorr = token
    if horario is None and not ocorr and not motivo:
        return
    dia.tratamentos.append(Tratamento(horario=horario, ocorr=ocorr, motivo=motivo))


def validar_duracoes(funcionarios: list[EspelhoFuncionario]) -> tuple[int, int, list[str]]:
    """Confere a DURAÇÃO impressa vs as leituras possíveis dos pares de jornada.

    Conta como OK: líquida recalculada (±2 min), presença bruta (±10 min — o
    RH iD imprime bruta em plantões overnight) ou overnight de batida dupla.
    O resto é dado podre do RH iD (vira candidato R10) ou parse a revisar.
    """
    total = bate = 0
    avisos: list[str] = []
    for f in funcionarios:
        for dia in f.dias:
            if dia.duracao is None:
                continue
            pares = dia.pares_jornada()
            if not pares:
                continue
            total += 1
            recalc = sum(s - e for e, s in pares)
            bruta = dia.presenca_bruta() or 0
            liquida = dia.duracao_liquida()
            if abs(recalc - dia.duracao) <= 2 or abs(bruta - dia.duracao) <= 10 or abs(liquida - dia.duracao) <= 70:
                bate += 1
            else:
                avisos.append(
                    f"{f.nome} (mat {f.matricula}) {dia.data}: duração impressa "
                    f"{dia.duracao // 60:02d}:{dia.duracao % 60:02d} vs recalculada "
                    f"{recalc // 60:02d}:{recalc % 60:02d}"
                )
    return total, bate, avisos
