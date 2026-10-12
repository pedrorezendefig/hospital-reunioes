"""Contador de diárias (issue #1115, PRD #1113, ADR 0070).

Port do `referencia-diarias.mjs` do diretor, parametrizado pelo bloco `diaria` da
memória da operadora em vez de constante. Entram as movimentações que a leitura do
conteúdo devolve (`conteudo.Movimentacao`, sem conversão) e saem os segmentos, um
por setor ocupado, com as diárias devidas, a data de lançamento de cada uma e as
pendências que viram Validar.

A diária e a pendência não citam o ID da regra (`ASSIM-DIA-06`): o ID é de cada
memória. Saem com uma chave fixa (`regra`, `motivo`) que a conferência traduz para
a regra da operadora. O código da diária (pela acomodação do setor e pela
`diaria_global`) também é da conferência. Módulo puro: sem banco e sem rota.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from app.services.contas_medicas.conteudo import Movimentacao

UM_DIA = timedelta(days=1)

# A memória escreve o tipo de saída com "DE"; a movimentação, sem.
_SAIDA_DA_MEMORIA = {
    "TRANSFERENCIA_DE_SETOR": "TRANSFERENCIA_SETOR",
    "TRANSFERENCIA_DE_HOSPITAL": "TRANSFERENCIA_HOSPITAL",
    "OBITO": "OBITO",
}


# Parâmetros com um só valor validado (o das memórias da ASSIM, da Unimed e da Leve).
_VALOR_VALIDADO = {
    "sempre_integral": True,
    "saida_antes_do_vencimento_paga_diaria_em_curso": True,
    "alta_depois_do_vencimento_paga_o_dia": False,
    "destino_inicia_na_hora_da_transferencia": True,
}


@dataclass(frozen=True)
class ParametrosDiaria:
    """O bloco `diaria` da memória. Sem a chave, vale a diretriz geral do HSM."""

    hora_vencimento: time = time(10, 0)
    limite_madrugada: time = time(5, 0)
    sempre_integral: bool = True
    saida_antes_do_vencimento_paga_diaria_em_curso: bool = True
    alta_depois_do_vencimento_paga_o_dia: bool = False
    # Tipos de movimentação de saída (`TRANSFERENCIA_SETOR`, ...), já traduzidos.
    diaria_extra_na_origem_apos_vencimento: frozenset[str] = frozenset(_SAIDA_DA_MEMORIA.values())
    transferencia_antes_do_vencimento_gera_extra: bool | Literal["PENDENTE"] = "PENDENTE"
    destino_inicia_na_hora_da_transferencia: bool = True
    # `None`: acompanhante incluso na diária, sem cobrança (Unimed, Leve).
    acompanhante_segue_a_regra_do_paciente: bool | None = True

    @classmethod
    def da_memoria(cls, parametros: Mapping[str, Any]) -> "ParametrosDiaria":
        bloco = parametros.get("diaria") or {}
        valores: dict[str, Any] = {
            nome: bloco[nome]
            for nome in (
                *_VALOR_VALIDADO,
                "transferencia_antes_do_vencimento_gera_extra",
                "acompanhante_segue_a_regra_do_paciente",
            )
            if nome in bloco
        }
        for nome in ("hora_vencimento", "limite_madrugada"):
            if nome in bloco:
                valores[nome] = time.fromisoformat(bloco[nome])
        if "diaria_extra_na_origem_apos_vencimento" in bloco:
            valores["diaria_extra_na_origem_apos_vencimento"] = frozenset(
                _SAIDA_DA_MEMORIA.get(tipo, tipo) for tipo in bloco["diaria_extra_na_origem_apos_vencimento"] or ()
            )
        return cls(**valores)


@dataclass(frozen=True)
class Diaria:
    # Data de lançamento: a 1ª na hora da entrada no setor, as seguintes às 10h.
    inicio: datetime
    fim: datetime
    extra: bool
    # VENCIMENTO, MADRUGADA, DESTINO ou EXTRA_NA_ORIGEM.
    regra: str


@dataclass(frozen=True)
class Pendencia:
    # TRANSFERENCIA_ANTES_DO_VENCIMENTO, MADRUGADA_NO_DESTINO, SEM_VENCIMENTO,
    # JANELA_ATRAVESSA_O_VENCIMENTO ou PARAMETRO_NAO_SUPORTADO.
    motivo: str
    texto: str
    sugestao: int | None = None


@dataclass(frozen=True)
class Segmento:
    setor: str | None
    inicio: datetime
    fim: datetime
    entrada: str
    saida: str
    diarias: tuple[Diaria, ...]
    validar: tuple[Pendencia, ...]
    # O acompanhante tem as mesmas diárias do paciente.
    acompanhante: bool


def _vencimento(dia: date, p: ParametrosDiaria) -> datetime:
    return datetime.combine(dia, p.hora_vencimento)


def _segmento(entrada: Movimentacao, saida: Movimentacao, p: ParametrosDiaria, acompanhante: bool) -> Segmento:
    ini, fim = entrada.data_hora, saida.data_hora
    if fim < ini:
        raise ValueError(f"Movimentações fora de ordem em {fim:%d/%m/%Y %H:%M}.")
    validar: list[Pendencia] = []
    diarias: list[Diaria] = []
    internacao = entrada.tipo == "INTERNACAO"

    # 1) primeiro vencimento do segmento
    de_madrugada = ini.time() <= p.limite_madrugada
    if internacao and de_madrugada:
        primeiro = _vencimento(ini.date(), p)
    else:
        primeiro = _vencimento(ini.date() + UM_DIA, p)
        if not internacao and de_madrugada:
            validar.append(
                Pendencia(
                    "MADRUGADA_NO_DESTINO",
                    "Transferência de madrugada: falta definir se o limite da madrugada vale para o setor de destino.",
                )
            )

    # 2) vencimentos até o do dia da saída, inclusive com saída antes dele (diária em curso)
    saiu_depois = fim.time() >= p.hora_vencimento
    ultimo = _vencimento(fim.date(), p)
    v, k = primeiro, 0
    while v <= ultimo:
        regra = "DESTINO" if k == 0 and not internacao else "MADRUGADA" if k == 0 and de_madrugada else "VENCIMENTO"
        diarias.append(Diaria(ini if k == 0 else v - UM_DIA, v, False, regra))
        v, k = v + UM_DIA, k + 1

    # 3) diária extra integral na origem; antes do vencimento, só na transferência e
    # conforme `transferencia_antes_do_vencimento_gera_extra` (true, false ou PENDENTE;
    # valor fora desses vale PENDENTE, e `contar_diarias` avisa)
    tipo_com_extra = saida.tipo in p.diaria_extra_na_origem_apos_vencimento
    transferencia = saida.tipo.startswith("TRANSFERENCIA")
    antes = p.transferencia_antes_do_vencimento_gera_extra
    if tipo_com_extra and (saiu_depois or (transferencia and antes is True)):
        diarias.append(Diaria(ultimo, ultimo + UM_DIA, True, "EXTRA_NA_ORIGEM"))
    elif tipo_com_extra and transferencia and antes is not False:
        validar.append(
            Pendencia(
                "TRANSFERENCIA_ANTES_DO_VENCIMENTO",
                "Transferência antes do vencimento: falta definir se há diária extra no setor de origem. "
                "Calculado sem a extra.",
            )
        )

    # 4) permanência sem nenhum vencimento: regra não definida
    if not diarias and saida.tipo != "EM_CURSO":
        validar.append(
            Pendencia(
                "SEM_VENCIMENTO",
                "Entrada e saída sem nenhum vencimento no setor: regra não definida.",
                1 if internacao else 0,
            )
        )

    return Segmento(entrada.setor, ini, fim, entrada.tipo, saida.tipo, tuple(diarias), tuple(validar), acompanhante)


def contar_diarias(
    movimentacoes: Sequence[Movimentacao], parametros: ParametrosDiaria, idade_anos: int | None = None
) -> list[Segmento]:
    """`movimentacoes` em ordem: a INTERNACAO, zero ou mais TRANSFERENCIA_SETOR e a saída
    (ALTA, OBITO, TRANSFERENCIA_HOSPITAL ou, se o paciente segue internado, EM_CURSO com
    o fim do período analisado). O setor de cada uma é o de destino."""
    if not movimentacoes or movimentacoes[0].tipo != "INTERNACAO":
        raise ValueError("A primeira movimentação deve ser INTERNACAO.")
    # Acompanhante: paciente com 60 anos ou mais ou menor de 18 (ASSIM-DIA-10).
    acompanhante = (
        parametros.acompanhante_segue_a_regra_do_paciente is True
        and idade_anos is not None
        and (idade_anos >= 60 or idade_anos < 18)
    )
    segmentos = [
        _segmento(entrada, saida, parametros, acompanhante)
        for entrada, saida in zip(movimentacoes, movimentacoes[1:], strict=False)
    ]

    # Transferência sem hora exata: o cálculo usou o fim da janela. Se a transferência no
    # começo dela muda a conta da origem ou do destino (atravessa as 10h, passa da
    # meia-noite, sai da madrugada), a janela não diz de que lado caiu: vira Validar.
    # Cada segmento só cresce ou só encolhe com a hora, então bastam as duas pontas.
    for i in range(1, len(movimentacoes)):
        transferencia = movimentacoes[i]
        if not transferencia.janela:
            continue
        de, ate = transferencia.janela
        no_comeco = replace(transferencia, data_hora=max(de, movimentacoes[i - 1].data_hora))
        afetados = movimentacoes[i - 1 : i + 2]
        com_o_comeco = [no_comeco if m is transferencia else m for m in afetados]
        no_fim = [_assinatura(s) for s in segmentos[i - 1 : i + 1]]
        if [
            _assinatura(_segmento(a, b, parametros, acompanhante))
            for a, b in zip(com_o_comeco, com_o_comeco[1:], strict=False)
        ] != no_fim:
            segmentos[i - 1] = replace(
                segmentos[i - 1],
                validar=segmentos[i - 1].validar
                + (
                    Pendencia(
                        "JANELA_ATRAVESSA_O_VENCIMENTO",
                        f"Transferência de setor sem hora exata, entre {de:%d/%m %H:%M} e {ate:%d/%m %H:%M}: "
                        "a conta muda conforme a hora da transferência dentro da janela. "
                        "Calculado com a transferência no fim da janela.",
                    ),
                ),
            )

    # O contador só conhece o valor que as memórias validaram para estes parâmetros; o
    # outro nenhuma memória definiu. Uma pendência por conta, no primeiro segmento.
    pendencias = [
        Pendencia(
            "PARAMETRO_NAO_SUPORTADO",
            f"A memória traz {nome}: {getattr(parametros, nome)}, valor que o contador não sabe aplicar. "
            "Calculado como se fosse o valor validado.",
        )
        for nome, validado in _VALOR_VALIDADO.items()
        if getattr(parametros, nome) is not validado
    ]
    antes = parametros.transferencia_antes_do_vencimento_gera_extra
    if not (antes is True or antes is False or antes == "PENDENTE"):
        pendencias.append(
            Pendencia(
                "PARAMETRO_NAO_SUPORTADO",
                f"A memória traz transferencia_antes_do_vencimento_gera_extra: {antes}, valor que o contador "
                "não sabe aplicar. Calculado como PENDENTE.",
            )
        )
    if segmentos and pendencias:
        segmentos[0] = replace(segmentos[0], validar=segmentos[0].validar + tuple(pendencias))
    return segmentos


def _assinatura(s: Segmento) -> tuple[tuple[tuple[datetime, bool, str], ...], tuple[str, ...]]:
    """O que a conta cobra do segmento, sem o início da 1ª diária (que é a própria hora
    da transferência e por isso sempre muda dentro da janela)."""
    return tuple((d.fim, d.extra, d.regra) for d in s.diarias), tuple(p.motivo for p in s.validar)


def diarias_do_periodo(segmentos: Sequence[Segmento], inicio: date, fim: date) -> list[Segmento]:
    """Diárias de uma conta parcial: as que começam dentro do período, datas inclusive."""
    return [replace(s, diarias=tuple(d for d in s.diarias if inicio <= d.inicio.date() <= fim)) for s in segmentos]
