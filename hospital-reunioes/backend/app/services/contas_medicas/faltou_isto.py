"""O Faltou isto no Guia e a conversa da Conta (issue #1489, PRD #1484, ADR 0081).

Quem vê o Guia aponta, num dia da Conta, o item e a página que o módulo não
achou (decisão 4). O Auditor recebe o que a análise guardou daquele dia (os
eventos com página e trecho, os documentos e as páginas que a leitura não
conseguiu ler, as linhas do Guia e os itens da conta), explica por que não
achou e classifica a origem: REGRA, LEITURA ou DEFEITO.

A conversa da Conta é histórico, nunca memória (decisão 3): nada daqui entra
no prompt do Passo A nem do Passo B. A pergunta vai ao Auditor antes de
qualquer gravação: se ele não responder, nada fica pela metade e quem apontou
manda de novo.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.passo_b import eventos_do_periodo
from app.utils.text_sanitizer import sanitizar_travessao

# As listas datadas da leitura do prontuário pela IA (Anexo A). O número do
# atendimento e a idade, que a mesma leitura devolve, não vão ao Auditor.
_LISTAS_DO_DIA = ("movimentacoes", "terapias", "prescricoes", "procedimentos", "cirurgias")


# O que o Guia deveria ter apontado vai junto da explicação, numa linha própria:
# a migration 126 não tem coluna para ele, e é o "esperado" do pedido para a
# Tecnologia, que sai daqui depois do ok de quem apontou.
ROTULO_DO_ESPERADO = "O Guia deveria ter apontado: "

MENSAGEM_AUDITOR_FORA = "O Auditor não respondeu agora. Nada foi gravado: tente de novo em alguns minutos."


def _juntar(explicacao: str, esperado: str) -> str:
    explicacao, esperado = sanitizar_travessao(explicacao).strip(), sanitizar_travessao(esperado).strip()
    return f"{explicacao}\n\n{ROTULO_DO_ESPERADO}{esperado}" if esperado else explicacao


def separar(texto: str | None) -> tuple[str, str]:
    """A explicação e o esperado, como `_juntar` os gravou."""
    explicacao, _, esperado = (texto or "").partition(f"\n\n{ROTULO_DO_ESPERADO}")
    return explicacao.strip(), esperado.strip()


def _agora() -> str:
    return datetime.now(UTC).isoformat()


def _eventos_guardados(supabase, atendimento_id: str) -> dict[str, Any]:
    """Os eventos do atendimento que a última análise guardou: a estrutura que
    o código leu e, em `ia`, a leitura do Passo A."""
    linhas = (
        supabase.table("cm_eventos")
        .select("eventos_json")
        .eq("atendimento_id", atendimento_id)
        .order("criado_em", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    return (linhas[0].get("eventos_json") or {}) if linhas else {}


def _do_dia(linha: dict[str, Any], iso: str) -> bool:
    inicio = linha.get("data")
    return inicio == iso or (bool(inicio) and inicio <= iso <= (linha.get("data_fim") or inicio))


def contexto_do_dia(supabase, conta: dict[str, Any], dia: date) -> dict[str, Any]:
    """O que o Auditor lê do dia apontado, sem texto livre do prontuário além
    do trecho de cada evento, que a leitura já desidentificou."""
    eventos = _eventos_guardados(supabase, conta["atendimento_id"])
    iso = dia.isoformat()
    da_ia = eventos_do_periodo(eventos.get("ia") or {}, dia, dia)
    linhas = supabase.table("cm_guia_linha").select("*").eq("conta_id", conta["id"]).execute().data or []
    itens = supabase.table("cm_conta_item").select("*").eq("conta_id", conta["id"]).execute().data or []
    return {
        "paginas_do_prontuario": eventos.get("total_paginas"),
        "paginas_sem_texto": eventos.get("paginas_sem_texto") or [],
        "documentos_do_dia": [d for d in eventos.get("documentos") or [] if d.get("data") == iso],
        "eventos_do_dia": {lista: da_ia.get(lista) or [] for lista in _LISTAS_DO_DIA},
        "linhas_do_guia": [
            {
                chave: linha.get(chave)
                for chave in ("acao", "codigo", "descricao", "quantidade_lancada", "quantidade_devida")
                + ("regra_codigo", "motivo", "estado", "evidencia_pagina")
            }
            for linha in linhas
            if _do_dia(linha, iso)
        ],
        "itens_da_conta": [
            {chave: item.get(chave) for chave in ("setor", "codigo", "descricao", "quantidade")}
            for item in itens
            if item.get("data") == iso
        ],
    }


def _dia_curto(dia: date) -> str:
    return dia.strftime("%d/%m")


def fora_do_periodo(conta: dict[str, Any], dia: date) -> str | None:
    """A frase da recusa quando o dia não é da Conta. Sem período gravado, todo
    dia vale."""
    inicio, fim = conta.get("periodo_inicio"), conta.get("periodo_fim")
    if not inicio or not fim or inicio <= dia.isoformat() <= fim:
        return None
    de, ate = date.fromisoformat(inicio), date.fromisoformat(fim)
    return f"Escolha um dia do período da conta, de {_dia_curto(de)} a {_dia_curto(ate)}."


def _mensagem_de_quem_apontou(dia: date, item: str, pagina: int | None, texto: str | None) -> str:
    """O que fica na conversa como a fala da pessoa."""
    onde = f", página {pagina}" if pagina else ""
    return f"Faltou isto em {_dia_curto(dia)}{onde}: {item}." + (f" {texto}" if texto else "")


def _conversa_da_conta(supabase, conta: dict[str, Any], operadora_id: str | None, autor_id: str | None) -> str:
    """A conversa da Conta, uma só: o segundo Faltou isto continua a primeira."""
    achadas = (
        supabase.table("cm_conversa")
        .select("id")
        .eq("contexto", "CONTA")
        .eq("conta_id", conta["id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if achadas:
        return achadas[0]["id"]
    criada = (
        supabase.table("cm_conversa")
        .insert({"contexto": "CONTA", "conta_id": conta["id"], "operadora_id": operadora_id, "criado_por": autor_id})
        .execute()
    )
    return criada.data[0]["id"]


def apontar(
    supabase,
    *,
    conta: dict[str, Any],
    atendimento: dict[str, Any],
    autor_id: str | None,
    dia: date,
    item: str,
    pagina: int | None,
    texto: str | None,
) -> dict[str, Any]:
    """O Faltou isto de uma pessoa: o Auditor explica e classifica, e só então
    o apontamento, a conversa e as duas falas são gravados. `ia.ErroDaIA` sobe
    sem nada gravado."""
    operadora_id = atendimento.get("operadora_id")
    memoria = gerar_texto_memoria(supabase, operadora_id, conta.get("memoria_versao_id"))
    pergunta = "\n".join(
        [
            f"Dia: {dia.strftime('%d/%m/%Y')}",
            f"Item: {item}",
            f"Página do prontuário: {pagina if pagina else 'não informada'}",
            f"Mensagem de quem apontou: {texto or '(sem mensagem)'}",
        ]
    )
    diagnostico = ia.explicar_faltou_isto(
        memoria,
        json.dumps(contexto_do_dia(supabase, conta, dia), ensure_ascii=False, default=str),
        pergunta,
        supabase=supabase,
        conta_id=conta["id"],
        atendimento_id=conta.get("atendimento_id"),
    )
    explicacao = _juntar(diagnostico.explicacao, diagnostico.esperado)

    conversa_id = _conversa_da_conta(supabase, conta, operadora_id, autor_id)
    supabase.table("cm_conversa_mensagem").insert(
        [
            {
                "conversa_id": conversa_id,
                "autor": "PESSOA",
                "autor_id": autor_id,
                "texto": _mensagem_de_quem_apontou(dia, item, pagina, texto),
            },
            {"conversa_id": conversa_id, "autor": "AUDITOR", "texto": explicacao},
        ]
    ).execute()
    gravado = (
        supabase.table("cm_faltou_isto")
        .insert(
            {
                "conta_id": conta["id"],
                "data": dia.isoformat(),
                "item": item,
                "pagina": pagina,
                "texto": texto,
                "origem": "PESSOA",
                "apontado_por": autor_id,
                "conversa_id": conversa_id,
                "classificacao": diagnostico.classificacao,
                "explicacao": explicacao,
                "classificado_em": _agora(),
            }
        )
        .execute()
    )
    return gravado.data[0]


def para_a_tela(apontamento: dict[str, Any], me_id: str | None) -> dict[str, Any]:
    """O apontamento como o Guia mostra."""
    return {
        chave: apontamento.get(chave)
        for chave in ("id", "data", "item", "pagina", "texto", "origem", "classificacao", "explicacao", "criado_em")
    }
