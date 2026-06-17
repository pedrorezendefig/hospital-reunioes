"""Parser da Folha mensal (Domínio/Thomson Reuters, relatório EXTRATO MENSAL).

Recebe o texto de `pdftotext -layout`. O relatório é seccionado por C.Custo;
cada registro abre em `Empr.:` e fecha nas linhas de totais `ND:`/`NF:`.
Nomes longos fazem o cabeçalho transbordar para a linha seguinte — um buffer
de continuação junta até 2 linhas antes de desistir. Blocos "Resumo por
Rubricas do Centro de Custo" são ignorados. Cada registro é validado pelo
invariante impresso: Σ proventos/Σ descontos das Rubricas = totais do registro.
"""

from __future__ import annotations

import re
from datetime import date

from .modelos import FolhaRegistro, Rubrica

RE_CCUSTO = re.compile(r"^\s*C\.Custo:\s*(.+?)\s*$")
# nomes/cargos longos podem COLAR no rótulo seguinte ("SISTEMASC.B.O:"),
# por isso os separadores entre campo e rótulo são \s* e não \s+
RE_EMPR = re.compile(r"^\s*Empr\.:\s+(\d+)\s+(.+?)\s*Situação:\s*(.*?)\s*CPF:\s*([\d.\-]*)\s*Adm:\s*([\d/]*)\s*$")
RE_EMPR_INICIO = re.compile(r"^\s*Empr\.:\s+\d+\s+\S")
RE_VINCULO = re.compile(r"^\s*Vínculo:\s*(.*?)\s*CC:\s*(\S*)\s+Depto:\s*(\S*)\s+Horas Mês:\s*([\d.,]*)\s*$")
RE_VINCULO_INICIO = re.compile(r"^\s*Vínculo:")
RE_CARGO = re.compile(r"^\s*Cargo:\s*(\d*)\s*(.*?)C\.B\.O:\s*(\S*)\s+Filial:\s*(\S*)\s+Salário:\s*([\d.,]*)\s*$")
RE_CARGO_INICIO = re.compile(r"^\s*Cargo:")
RE_DEMITIDO = re.compile(r"^\s*DEMITIDO EM\s+(\d{2}/\d{2}/\d{4})")
RE_OBSERVACAO = re.compile(r"^\s*(FERIAS DE\b|Doença\b|Novo afast\.|Licença\b|Afast\b|Atestado\b)", re.IGNORECASE)
RE_ND = re.compile(
    r"^ND:\s*(\d+)\s+Proventos:\s*([\d.,]+)\s+Descontos:\s*([\d.,]+)"
    r"\s+Informativa:\s*([\d.,]+)\s+Informativa Dedutora:\s*([\d.,]+)\s+Líquido:\s*(-?[\d.,]+)\s*$"
)
RE_NF = re.compile(
    r"^NF:\s*(\d+)\s+Base INSS:\s*([\d.,]+)\s+Excedente INSS:\s*([\d.,]+)"
    r"\s+Base FGTS:\s*([\d.,]+)\s+Valor FGTS:\s*([\d.,]+)\s+Base IRRF:\s*(-?[\d.,]+)\s*$"
)
# célula de rubrica: código + descrição + referência + valor + P/D
# (valores monetários do Domínio têm sempre vírgula decimal, o que desambigua
# descrições terminadas em inteiro, ex. 'DEPENDENTE 1')
# lookbehind: o código não pode ser cauda de um número ('72' dentro de '872,72')
RE_CELULA = re.compile(r"(?<![\d,.])(\d{1,4})\s+(\S.*?)\s+([\d.]*\d,\d{2})\s+([\d.]*\d,\d{2})\s+([PD])(?=\s{2,}|\s*$)")
RE_PENDENTE = re.compile(r"^\s*(\d{1,4})\s+([^\d\s].*?\S)\s*$")
RE_VALORES_ORFAOS = re.compile(r"^\s*([\d.]*\d,\d{2})\s+([\d.]*\d,\d{2})\s+([PD])\s*$")
RE_COMPETENCIA = re.compile(r"^\s*Competência:\s*(\d{2}/\d{4})")

PREFIXOS_PAGINA = ("Empresa:", "CNPJ:", "Cálculo:", "Competência:", "Sistema licenciado")
MARCA_RESUMO = "Resumo por Rubricas"


def _num(s: str) -> float:
    s = s.strip().replace(".", "").replace(",", ".")
    return float(s) if s and s not in ("-",) else 0.0


def _data(s: str) -> date | None:
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if not m:
        return None
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))


def parse_folha(texto: str) -> tuple[list[FolhaRegistro], str | None, list[str]]:
    """Retorna (registros, competência 'MM/AAAA', avisos globais)."""
    registros: list[FolhaRegistro] = []
    avisos: list[str] = []
    competencia: str | None = None
    c_custo = ""
    atual: FolhaRegistro | None = None
    pendente: tuple[int, str] | None = None
    skip_resumo = False
    head_falta = 0  # linhas Vínculo/Cargo ainda esperadas do registro atual
    # cabeçalho transbordado: (linha parcial, regex alvo, linhas extras já juntadas)
    continuacao: tuple[str, str, int] | None = None

    for bruta in texto.split("\n"):
        linha = bruta.replace("\f", "").rstrip()
        if not linha.strip():
            continue
        if competencia is None:
            m = RE_COMPETENCIA.match(linha)
            if m:
                competencia = m.group(1)
        if linha.lstrip().startswith(PREFIXOS_PAGINA) or "EXTRATO MENSAL" in linha:
            continue

        if continuacao is not None:
            # nunca consumir uma linha que já parece rubrica/totais
            if RE_CELULA.search(linha) or RE_ND.match(linha.strip()):
                avisos.append(f"cabeçalho incompleto descartado: {continuacao[0][:90]!r}")
                continuacao = None
            else:
                juntada = continuacao[0] + "  " + linha.strip()
                alvo, extras = continuacao[1], continuacao[2]
                casou, head_falta = _tentar_header(juntada, alvo, registros, avisos, c_custo, head_falta)
                if casou:
                    atual = registros[-1] if alvo == "empr" else atual
                    pendente = None if alvo == "empr" else pendente
                    continuacao = None
                    continue
                if extras < 1:
                    continuacao = (juntada, alvo, extras + 1)
                    continue
                avisos.append(f"cabeçalho não montado após 3 linhas: {continuacao[0][:90]!r}")
                continuacao = None
                # segue processando a linha atual normalmente

        m = RE_CCUSTO.match(linha)
        if m and "C.Custo:" in linha:
            c_custo = m.group(1)
            skip_resumo = False
            continue
        if MARCA_RESUMO in linha:
            skip_resumo = True
            _fechar(atual, avisos)
            atual = None
            continue

        if RE_EMPR_INICIO.match(linha):
            skip_resumo = False
            _fechar(atual, avisos)
            atual = None
            casou, head_falta = _tentar_header(linha, "empr", registros, avisos, c_custo, head_falta)
            if casou:
                atual = registros[-1]
                pendente = None
            else:
                continuacao = (linha.strip(), "empr", 0)
            continue
        if skip_resumo or atual is None:
            continue

        if head_falta and RE_VINCULO_INICIO.match(linha):
            casou, head_falta = _tentar_header(linha, "vinculo", registros, avisos, c_custo, head_falta)
            if not casou:
                continuacao = (linha.strip(), "vinculo", 0)
            continue
        if head_falta and RE_CARGO_INICIO.match(linha):
            casou, head_falta = _tentar_header(linha, "cargo", registros, avisos, c_custo, head_falta)
            if not casou:
                continuacao = (linha.strip(), "cargo", 0)
            continue

        m = RE_DEMITIDO.match(linha)
        if m:
            atual.demissao = _data(m.group(1))
            continue
        if RE_OBSERVACAO.match(linha):
            atual.observacoes.append(linha.strip())
            continue

        m = RE_ND.match(linha.strip())
        if m:
            atual.nd = int(m.group(1))
            atual.proventos = _num(m.group(2))
            atual.descontos = _num(m.group(3))
            atual.informativa = _num(m.group(4))
            atual.liquido = _num(m.group(6))
            continue
        m = RE_NF.match(linha.strip())
        if m:
            atual.nf = int(m.group(1))
            atual.base_inss = _num(m.group(2))
            atual.base_fgts = _num(m.group(4))
            atual.valor_fgts = _num(m.group(5))
            atual.base_irrf = _num(m.group(6))
            continue

        # rubricas: valores órfãos fecham a descrição pendente da linha anterior.
        # Eles podem estar sozinhos na linha OU no prefixo, dividindo a linha
        # com uma célula completa à direita.
        celulas = list(RE_CELULA.finditer(linha))
        prefixo = linha[: celulas[0].start()] if celulas else linha
        if pendente is not None:
            m = RE_VALORES_ORFAOS.match(prefixo.strip())
            if m:
                atual.rubricas.append(Rubrica(pendente[0], pendente[1], _num(m.group(1)), _num(m.group(2)), m.group(3)))
                pendente = None
                if not celulas:
                    continue
        fim_ultimo = 0
        achou = False
        for cel in celulas:
            achou = True
            fim_ultimo = cel.end()
            atual.rubricas.append(
                Rubrica(
                    int(cel.group(1)),
                    re.sub(r"\s+", " ", cel.group(2)),
                    _num(cel.group(3)),
                    _num(cel.group(4)),
                    cel.group(5),
                )
            )
        resto = linha[fim_ultimo:].strip()
        if resto:
            mp = RE_PENDENTE.match(resto)
            if mp:
                pendente = (int(mp.group(1)), re.sub(r"\s+", " ", mp.group(2)))
            elif not achou:
                atual.avisos_parse.append(f"linha não reconhecida: {resto[:90]!r}")

    _fechar(atual, avisos)
    return registros, competencia, avisos


def _tentar_header(
    linha: str,
    alvo: str,
    registros: list[FolhaRegistro],
    avisos: list[str],
    c_custo: str,
    head_falta: int,
) -> tuple[bool, int]:
    """Tenta casar a linha (possivelmente juntada) com o cabeçalho `alvo`."""
    if alvo == "empr":
        m = RE_EMPR.match(linha)
        if not m:
            return False, head_falta
        registros.append(
            FolhaRegistro(
                empr=int(m.group(1)),
                nome=re.sub(r"\s+", " ", m.group(2)),
                situacao=m.group(3).strip(),
                cpf=re.sub(r"\D", "", m.group(4)),
                admissao=_data(m.group(5)),
                vinculo="",
                cc="",
                depto="",
                horas_mes=0.0,
                cargo="",
                cbo="",
                filial="",
                salario=0.0,
                c_custo=c_custo,
            )
        )
        return True, 2
    reg = registros[-1] if registros else None
    if reg is None:
        return False, head_falta
    if alvo == "vinculo":
        m = RE_VINCULO.match(linha)
        if not m:
            return False, head_falta
        reg.vinculo = m.group(1).strip()
        reg.cc, reg.depto = m.group(2), m.group(3)
        reg.horas_mes = _num(m.group(4))
        return True, head_falta - 1
    m = RE_CARGO.match(linha)
    if not m:
        return False, head_falta
    reg.cargo = m.group(2).strip()
    reg.cbo, reg.filial = m.group(3), m.group(4)
    reg.salario = _num(m.group(5))
    return True, head_falta - 1


def _fechar(reg: FolhaRegistro | None, avisos: list[str]) -> None:
    """Valida o invariante impresso do registro: Σ rubricas = totais."""
    if reg is None:
        return
    soma_p = sum(r.valor for r in reg.rubricas if r.tipo == "P")
    soma_d = sum(r.valor for r in reg.rubricas if r.tipo == "D")
    if abs(soma_p - reg.proventos) > 0.05 or abs(soma_d - reg.descontos) > 0.05:
        msg = (
            f"{reg.nome} (empr {reg.empr}): Σ rubricas P={soma_p:.2f}/D={soma_d:.2f} "
            f"≠ totais P={reg.proventos:.2f}/D={reg.descontos:.2f}"
        )
        reg.avisos_parse.append(msg)
        avisos.append(msg)
