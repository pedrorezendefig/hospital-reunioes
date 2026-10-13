"""O passo A de Contas médicas: os eventos do prontuário (issue #1131, PRD #1128).

A IA lê só o que o código não estruturou: os blocos de texto livre de cada
documento (evoluções, anotações, formulários, SAE só com o que mudou, resumo
de alta, descrição cirúrgica, admissão), já desidentificados pela leitura do
prontuário, cada um com o marcador `[[PÁG n · FAMÍLIA · data hora · setor]]`
e na ordem da data. Depois deles vai o que o código já leu, para a IA não
refazer: as prescrições consolidadas (uma linha por item), o balanço por dia,
as glicemias por dia e os achados das conferências por código.

Uma leitura por atendimento: o resultado fica em `cm_eventos` e serve a todas
as parciais e ao reenvio.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, time
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas import prontuario as leitura_do_prontuario
from app.services.contas_medicas.conferencia import ProntuarioLido
from app.services.contas_medicas.desidentificacao import Identificacao, desidentificar
from app.services.contas_medicas.evidencia import normalizar
from app.services.contas_medicas.memoria_texto import orientacoes_de_leitura
from app.services.contas_medicas.prescricao import ItemConsolidado
from app.services.prompt_loader import load_prompt

__all__ = ["eventos_do_atendimento", "montar_entradas", "unir_eventos"]

SEPARADOR = " · "

# O modelo pequeno cobra por faixa até 100 mil tokens de entrada (adendo v1.3,
# item 10). A estimativa é a do diretor: 3,5 caracteres por token.
LIMITE_DE_TOKENS = 100_000
CARACTERES_POR_TOKEN = 3.5
# Folga para a linha que abre cada janela e para os rótulos que o adaptador
# põe antes das orientações e do texto.
_CABECALHO_DA_JANELA = 200
_ROTULOS_DOS_BLOCOS = 100


# ----------------------------------------------------------------------------------
# A entrada
# ----------------------------------------------------------------------------------


def _data(dia: date | None, hora: time | None = None) -> str:
    if dia is None:
        return "sem data"
    return f"{dia:%d/%m/%Y}" + (f" {hora:%H:%M}" if hora else "")


def _data_iso(valor: str | None) -> str:
    return _data(date.fromisoformat(valor[:10])) if valor else "sem data"


def _paginas(paginas: Sequence[int]) -> str:
    return f"{paginas[0]}-{paginas[-1]}" if len(paginas) > 1 else str(paginas[0])


def _blocos(prontuario: ProntuarioLido) -> list[tuple[date | None, str]]:
    """Um bloco por documento com texto para a IA, com o dia dele. A leitura
    do prontuário já ordenou pela data e desidentificou as linhas."""
    blocos = []
    for documento in prontuario.estrutura.documentos:
        if not documento.linhas:
            continue
        marcador = SEPARADOR.join(
            [
                f"[[PÁG {_paginas(documento.paginas)}",
                documento.subtipo or documento.familia,
                _data(documento.data, documento.hora),
                f"{documento.setor or 'sem setor'}]]",
            ]
        )
        blocos.append((documento.data, "\n".join([marcador, *documento.linhas])))
    return blocos


def _linha_da_prescricao(item: ItemConsolidado) -> str:
    dias = ", ".join(
        f"{dia:%d/%m}" + (f" ({doses})" if doses else "") for dia, doses in sorted(item.doses_por_dia.items())
    )
    partes = [item.subtipo, item.secao or "", item.nome, item.colunas, f"dias: {dias}"]
    if item.se_necessario:
        partes.append("SE NECESSÁRIO")
    if item.obs:
        partes.append(f"obs: {item.obs}")
    if item.componentes:
        partes.append("componentes: " + ", ".join(item.componentes))
    if item.pedidos:
        partes.append("pedidos: " + ", ".join(item.pedidos))
    partes.append("PÁG " + ", ".join(str(p) for p in item.paginas))
    return SEPARADOR.join(parte for parte in partes if parte)


def _numero(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def _linhas_do_balanco(prontuario: ProntuarioLido) -> list[str]:
    linhas = []
    for balanco in prontuario.conteudo.balancos:
        onde = f"{_data(balanco.data)} {balanco.setor or 'sem setor'}"
        pagina = f"PÁG {balanco.paginas[0]}" if balanco.paginas else ""
        for ganho in balanco.ganhos:
            item = f"GANHO: {ganho.item}" + (f" {ganho.via}" if ganho.via else "")
            linhas.append(
                SEPARADOR.join([onde, item, f"{ganho.lancamentos} lançamentos", f"{_numero(ganho.total)} mL", pagina])
            )
        for perda in balanco.perdas:
            linhas.append(SEPARADOR.join([onde, f"PERDA: {perda.item}", _numero(perda.total), pagina]))
    return linhas


def _linhas_das_glicemias(prontuario: ProntuarioLido) -> list[str]:
    """Quantas glicemias o dia registra: a mesma glicemia pode estar na
    aferição e no balanço, e vale a fonte que conta mais."""
    por_dia: dict[date, int] = {}
    for glicemia in prontuario.conteudo.glicemias:
        por_dia[glicemia.data] = max(por_dia.get(glicemia.data, 0), glicemia.quantidade)
    return [f"{_data(dia)}: {quantidade}" for dia, quantidade in sorted(por_dia.items()) if quantidade]


def _linha_do_achado(achado: Mapping[str, Any], identificacao: Identificacao) -> str:
    """O código do item e a regra vão como estão: a desidentificação trocaria
    o código de 8 dígitos por telefone. O texto passa por ela."""
    periodo = _data_iso(achado.get("data"))
    if achado.get("data_fim") and achado.get("data_fim") != achado.get("data"):
        periodo += f" a {_data_iso(achado.get('data_fim'))}"
    descricao, motivo = desidentificar([achado.get("descricao") or "", achado.get("motivo") or ""], identificacao)
    partes = [
        achado.get("acao") or "",
        periodo,
        achado.get("setor") or "",
        achado.get("codigo") or "",
        descricao,
        f"regra {achado['regra_codigo']}" if achado.get("regra_codigo") else "",
        motivo,
    ]
    return SEPARADOR.join(parte for parte in partes if parte)


def _secao(titulo: str, linhas: list[str]) -> str:
    return "\n".join([f"[[{titulo}]]", *(linhas or ["(nada)"])])


def _secoes_do_codigo(
    prontuario: ProntuarioLido, achados: Sequence[Mapping[str, Any]], identificacao: Identificacao
) -> str:
    """O que o código já leu, depois dos blocos. A observação da prescrição e
    os nomes dos itens vêm do prontuário cru: passam pela desidentificação."""
    do_prontuario = [
        _secao(
            "PRESCRIÇÕES CONSOLIDADAS",
            [_linha_da_prescricao(item) for item in prontuario.conteudo.prescricao_consolidada],
        ),
        _secao("BALANÇO HÍDRICO POR DIA", _linhas_do_balanco(prontuario)),
        _secao("GLICEMIAS POR DIA", _linhas_das_glicemias(prontuario)),
    ]
    desidentificadas = "\n".join(desidentificar("\n\n".join(do_prontuario).split("\n"), identificacao))
    achados_ = _secao("ACHADOS DO CÓDIGO", [_linha_do_achado(achado, identificacao) for achado in achados])
    return f"{desidentificadas}\n\n{achados_}"


def _identificacao(prontuario: ProntuarioLido) -> Identificacao:
    return leitura_do_prontuario._ler_capa(list(prontuario.texto_por_pagina)).identificacao


def _janelas(tamanhos: Sequence[int], orcamento: int) -> list[tuple[int, int]]:
    """Os dias de cada janela (primeiro e último, pela posição), cada uma até
    o orçamento, e a seguinte começando no último dia da anterior. A janela
    tem ao menos dois dias, ou a sobreposição não andaria."""
    janelas = []
    inicio = 0
    while True:
        fim, tamanho = inicio, tamanhos[inicio]
        while fim + 1 < len(tamanhos) and (fim == inicio or tamanho + tamanhos[fim + 1] <= orcamento):
            fim += 1
            tamanho += tamanhos[fim]
        janelas.append((inicio, fim))
        if fim >= len(tamanhos) - 1:
            return janelas
        inicio = fim


def montar_entradas(prontuario: ProntuarioLido, achados: Sequence[Mapping[str, Any]], *, reserva: int = 0) -> list[str]:
    """O texto do prontuário para o passo A: os blocos e as seções do código.
    Acima do limite do modelo pequeno, uma entrada por janela de dias, com um
    dia de sobreposição e as seções do código em todas. `reserva` é o que vai
    junto na mesma chamada (as orientações de leitura)."""
    blocos = _blocos(prontuario)
    secoes = _secoes_do_codigo(prontuario, achados, _identificacao(prontuario))
    inteiro = "\n\n".join([*(texto for _, texto in blocos), secoes])
    orcamento = int(LIMITE_DE_TOKENS * CARACTERES_POR_TOKEN) - reserva
    if len(inteiro) <= orcamento or not blocos:
        return [inteiro]

    por_dia: list[tuple[date | None, list[str]]] = []
    for dia, texto in blocos:
        if por_dia and por_dia[-1][0] == dia:
            por_dia[-1][1].append(texto)
        else:
            por_dia.append((dia, [texto]))
    tamanhos = [sum(len(texto) + 2 for texto in textos) for _, textos in por_dia]
    janelas = _janelas(tamanhos, orcamento - len(secoes) - _CABECALHO_DA_JANELA)
    entradas = []
    for numero, (inicio, fim) in enumerate(janelas, start=1):
        cabecalho = (
            f"[[PARTE {numero} DE {len(janelas)} DO PRONTUÁRIO: de {_data(por_dia[inicio][0])} "
            f"a {_data(por_dia[fim][0])}. As outras partes vão em chamadas separadas.]]"
        )
        textos = [texto for _, do_dia in por_dia[inicio : fim + 1] for texto in do_dia]
        entradas.append("\n\n".join([cabecalho, *textos, secoes]))
    return entradas


# ----------------------------------------------------------------------------------
# A união das janelas
# ----------------------------------------------------------------------------------


def _chave(valor: Any) -> str:
    return normalizar(str(valor or ""))


# O mesmo evento em duas janelas: mesmo tipo e mesmo início. O texto que diz
# qual é o evento entra na chave, para duas bombas que começam juntas (ou dois
# curativos no mesmo dia) não virarem uma.
_MESMO_EVENTO = {
    "movimentacoes": lambda e: (e["tipo"], e["data_hora"]),
    "terapias": lambda e: (e["tipo"], e["inicio"], _chave(e["descricao"])),
    "prescricoes": lambda e: (_chave(e["item"]), e["data"]),
    "procedimentos": lambda e: (e["tipo"], e["data_hora"], _chave(e["detalhe"])),
    "cirurgias": lambda e: (e["data"], e["inicio"], _chave(e["procedimento"])),
}


def unir_eventos(partes: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Os eventos de todas as janelas, sem repetir o que duas janelas vizinhas
    leram do dia em comum. A terapia que a janela anterior viu sem fim ganha o
    fim que a seguinte leu."""
    unido: dict[str, Any] = {
        "atendimento": next((p["atendimento"] for p in partes if p.get("atendimento")), None),
        "idade_anos": next((p["idade_anos"] for p in partes if p.get("idade_anos") is not None), None),
    }
    for lista, mesmo_evento in _MESMO_EVENTO.items():
        vistos: dict[Any, dict[str, Any]] = {}
        for parte in partes:
            for evento in parte.get(lista) or []:
                chave = mesmo_evento(evento)
                if chave not in vistos:
                    vistos[chave] = dict(evento)
                elif lista == "terapias" and not vistos[chave].get("fim"):
                    vistos[chave]["fim"] = evento.get("fim")
        unido[lista] = list(vistos.values())
    for lista in ("documentos_ausentes", "observacoes"):
        textos: dict[str, str] = {}
        for parte in partes:
            for texto in parte.get(lista) or []:
                textos.setdefault(_chave(texto), texto)
        unido[lista] = list(textos.values())
    return unido


# ----------------------------------------------------------------------------------
# A leitura, uma vez por atendimento
# ----------------------------------------------------------------------------------


def eventos_do_atendimento(
    supabase,
    *,
    conta_id: str,
    atendimento_id: str,
    arquivo_id: str,
    prontuario: ProntuarioLido,
    achados: Sequence[Mapping[str, Any]],
    regras: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Os eventos do prontuário do atendimento: os guardados em `cm_eventos`
    para este arquivo ou, na primeira parcial, a leitura pela IA."""
    orientacoes = orientacoes_de_leitura(list(regras))
    # A instrução, as orientações e os rótulos dos blocos vão em toda chamada.
    reserva = len(load_prompt("contas_medicas_passo_a")) + len(orientacoes) + _ROTULOS_DOS_BLOCOS
    partes = [
        ia.extrair_eventos(
            entrada, orientacoes, supabase=supabase, conta_id=conta_id, atendimento_id=atendimento_id
        ).model_dump()
        for entrada in montar_entradas(prontuario, achados, reserva=reserva)
    ]
    return unir_eventos(partes)
