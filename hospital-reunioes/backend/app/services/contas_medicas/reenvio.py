"""O reenvio da conta corrigida e a nota de saída (issue #1136, PRD #1128, ADR 0070).

Depois de corrigir no MV, a faturista pode reenviar só o PDF da conta de uma
conta concluída, pelo botão do Guia ou arrastando na tela Contas. É opcional: a
conta concluída sem reenvio vale igual para a produção dela.

A conta nova é lida pelo leitor de sempre e os itens dela são comparados com
as linhas Feito do Guia: o Incluir corrigido é o item que entrou, o Retirar
corrigido é o que sumiu, o Ajustar quantidade é a quantidade que bate com a
devida e o Corrigir preço é o unitário igual ao da tabela. O que não pegou fica
"ainda na conta". A nota de saída sai do mesmo helper da nota de entrada, só
com as linhas Feito que continuam e com o total da conta corrigida.

O prontuário não é lido de novo e a IA não é chamada: os eventos do
atendimento e o Guia ficam como estão.

O resultado por linha fica em `faltantes`, ao lado do que o processamento já
guarda ali (os itens que o prontuário não trouxe e o tempo de cada etapa): a
migration 117 deu à conta só `nota_saida` e `reenviada_em`.

O texto da conta tem dado do paciente: nada daqui vai para log.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal

from app.services.contas_medicas.guia import nota_de_entrada
from app.services.contas_medicas_conta import Conta, ErroLeitura, ItemConta, detectar_tipo_do_arquivo, ler_conta
from app.services.contas_medicas_extrator import extrair_paginas

CORRIGIDA = "CORRIGIDA"
AINDA_NA_CONTA = "AINDA_NA_CONTA"
CONCLUIDAS = ("CONCLUIDA", "CONCLUIDA_COM_PENDENCIA")

MENSAGEM_NAO_CONCLUIDA = "Só a conta concluída pode ser reenviada."
MENSAGEM_NAO_E_CONTA = "Este PDF não é a conta do MV. Envie só a conta corrigida."
TOLERANCIA_DE_PRECO = Decimal("0.01")


def mensagem_outra_conta(numero_atendimento: str | None, numero_conta: str | None) -> str:
    return f"Este PDF é de outra conta. Envie a conta {numero_conta} do atendimento {numero_atendimento}, corrigida."


def ler_conta_reenviada(conteudo: bytes) -> Conta | ErroLeitura:
    """O PDF do botão do Guia: tem de ser a conta, lida inteira."""
    paginas = extrair_paginas(conteudo)
    if isinstance(paginas, ErroLeitura):
        return paginas
    textos = [pagina.texto for pagina in paginas]
    if detectar_tipo_do_arquivo(textos[0] if textos else "") != "CONTA":
        return ErroLeitura(MENSAGEM_NAO_E_CONTA)
    return ler_conta(textos)


def e_a_mesma_conta(conta: dict, numero_atendimento: str | None, lida: Conta) -> bool:
    """A conta corrigida é do mesmo atendimento e tem o mesmo número."""
    if lida.atendimento != numero_atendimento:
        return False
    return not conta.get("numero_conta") or lida.conta == conta.get("numero_conta")


def _decimal(valor) -> Decimal | None:
    return None if valor is None else Decimal(str(valor))


def _do_item(linha: dict, item: ItemConta) -> bool:
    """O item da conta de que a linha fala: mesmo código, no dia (ou no período) dela."""
    if item.codigo != linha.get("codigo"):
        return False
    inicio = linha.get("data")
    if not inicio:
        return True
    fim = linha.get("data_fim") or inicio
    return str(inicio)[:10] <= item.data.isoformat() <= str(fim)[:10]


def _corrigida(linha: dict, itens: Iterable[ItemConta]) -> bool:
    do_item = [item for item in itens if _do_item(linha, item)]
    quantidade = sum((item.quantidade for item in do_item), Decimal(0))
    devida = _decimal(linha.get("quantidade_devida"))
    acao = linha.get("acao")
    if acao == "INCLUIR":
        return quantidade > 0 if devida is None else quantidade >= devida
    if acao == "RETIRAR":
        return quantidade <= (devida or 0)
    if acao == "AJUSTAR_QUANTIDADE":
        if devida is None:
            return quantidade != (_decimal(linha.get("quantidade_lancada")) or 0)
        return quantidade == devida
    if acao == "CORRIGIR_PRECO":
        tabela = _decimal(linha.get("preco_tabela"))
        if tabela is None or not do_item:
            return False
        return all(abs(item.unitario - tabela) <= TOLERANCIA_DE_PRECO for item in do_item)
    return False


def comparar(linhas: Iterable[dict], conta: Conta) -> dict[str, str]:
    """Cada linha Feito: corrigida no MV ou ainda na conta."""
    return {
        linha["id"]: CORRIGIDA if _corrigida(linha, conta.itens) else AINDA_NA_CONTA
        for linha in linhas
        if linha.get("estado") == "FEITO"
    }


def nota_de_saida(linhas: Iterable[dict], resultado: dict[str, str], total) -> int:
    """O helper da nota de entrada, só com as linhas Feito que continuam."""
    continuam = [linha for linha in linhas if resultado.get(linha["id"]) == AINDA_NA_CONTA]
    return nota_de_entrada(continuam, total).nota


def resumo(conta: dict) -> dict | None:
    """O reenvio como a tela mostra; nulo quando a conta não foi reenviada."""
    if conta.get("reenviada_em") is None:
        return None
    faltantes = conta.get("faltantes")
    guardado = faltantes.get("reenvio") if isinstance(faltantes, dict) else None
    linhas = (guardado or {}).get("linhas") or {}
    nota = conta.get("nota_saida")
    return {
        "nota_saida": None if nota is None else int(Decimal(str(nota))),
        "reenviada_em": conta.get("reenviada_em"),
        "corrigidas": sum(1 for marca in linhas.values() if marca == CORRIGIDA),
        "ainda_na_conta": sum(1 for marca in linhas.values() if marca == AINDA_NA_CONTA),
        "linhas": linhas,
    }


def frase(conta: dict) -> str:
    """O "Último envio" da conta reenviada."""
    dados = resumo(conta)
    corrigidas = dados["corrigidas"]
    plural = "corrigida" if corrigidas == 1 else "corrigidas"
    return (
        f"reenvio da conta {conta.get('numero_conta')}: {corrigidas} {plural} no MV, "
        f"{dados['ainda_na_conta']} ainda na conta, nota de saída {dados['nota_saida']}"
    )


def reenviar(supabase, conta: dict, lida: Conta, agora: datetime, arquivo_id: str | None = None) -> dict:
    """Compara, calcula a nota de saída e grava. A conta continua concluída."""
    linhas = supabase.table("cm_guia_linha").select("*").eq("conta_id", conta["id"]).execute().data or []
    resultado = comparar(linhas, lida)
    faltantes = conta.get("faltantes")
    guardado = dict(faltantes) if isinstance(faltantes, dict) else {"itens": faltantes or []}
    guardado["reenvio"] = {"linhas": resultado}
    campos = {
        "nota_saida": nota_de_saida(linhas, resultado, lida.total),
        "reenviada_em": agora.isoformat(),
        "faltantes": guardado,
    }
    if arquivo_id:
        # A conta passa a apontar para o PDF corrigido: é por ele que o
        # "Último envio" acha a conta deste envio.
        campos["arquivo_id"] = arquivo_id
    supabase.table("cm_conta").update(campos).eq("id", conta["id"]).execute()
    return resumo({**conta, **campos})
