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
import re
import threading
from datetime import UTC, date, datetime
from typing import Any

from app.services import github_client
from app.services.contas_medicas import auditor, ia
from app.services.contas_medicas.desidentificacao import Identificacao, desidentificar
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.passo_b import eventos_do_periodo
from app.services.ouvidoria_pseudonimizacao import pseudonimizar
from app.services.tecnologia_vinculo import CABECALHO_DO_BLOCO, LABELS_DO_BUG, texto_do_diretor, titulo_da_issue
from app.utils.text_sanitizer import sanitizar_travessao

# As listas datadas da leitura do prontuário pela IA (Anexo A). O número do
# atendimento e a idade, que a mesma leitura devolve, não vão ao Auditor.
_LISTAS_DO_DIA = ("movimentacoes", "terapias", "prescricoes", "procedimentos", "cirurgias")
# O que o Auditor lê de cada linha do Guia e de cada item lançado no dia: sem
# preço, que é do código (ADR 0070).
_CAMPOS_DA_LINHA = (
    "acao",
    "codigo",
    "descricao",
    "quantidade_lancada",
    "quantidade_devida",
    "regra_codigo",
    "motivo",
    "estado",
    "evidencia_pagina",
)
_CAMPOS_DO_ITEM = ("setor", "codigo", "descricao", "quantidade")


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
        "linhas_do_guia": [{c: linha.get(c) for c in _CAMPOS_DA_LINHA} for linha in linhas if _do_dia(linha, iso)],
        "itens_da_conta": [{c: item.get(c) for c in _CAMPOS_DO_ITEM} for item in itens if item.get("data") == iso],
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


def _pedido_de_regra(dia: date, item: str, explicacao: str, esperado: str) -> str:
    """A mensagem que leva o Faltou isto por falta de regra ao lote do Auditor."""
    return "\n".join(
        [
            f"Faltou isto no Guia de uma conta desta operadora, em {_dia_curto(dia)}: {item}.",
            f"O Auditor viu que falta regra: {explicacao}",
            f"{ROTULO_DO_ESPERADO}{esperado or 'o Auditor não disse.'}",
            "Proponha a Regra nova que faz o Guia apontar isto nas próximas contas.",
        ]
    )


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
    decide: bool = False,
) -> dict[str, Any]:
    """O Faltou isto de uma pessoa: o Auditor explica e classifica e, quando
    falta regra, propõe a Regra (issue #1496); só então o apontamento, a
    conversa e as falas são gravados. `ia.ErroDaIA` sobe sem nada gravado.

    `decide` é quem tem "Regra contratual e tabelas": a proposta espera o "ok"
    na conversa da Operadora. Sem a permissão, a Regra entra pendente e vai
    para a Validação."""
    operadora_id = atendimento.get("operadora_id")
    memoria = gerar_texto_memoria(supabase, operadora_id, conta.get("memoria_versao_id"))
    # O que a pessoa escreveu vai ao Auditor sem identificação, como o texto do
    # prontuário vai ao Passo A (ADR 0070, decisão 8).
    pergunta = "\n".join(
        [
            f"Dia: {dia.strftime('%d/%m/%Y')}",
            f"Item: {_sem_identificacao(item, conta, atendimento)}",
            f"Página do prontuário: {pagina if pagina else 'não informada'}",
            f"Mensagem de quem apontou: {_sem_identificacao(texto, conta, atendimento) or '(sem mensagem)'}",
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
    item_sem_identificacao = _sem_identificacao(item, conta, atendimento)
    proposta = None
    if diagnostico.classificacao == "REGRA":
        proposta = auditor.propor_regra_do_faltou_isto(
            supabase,
            operadora_id,
            _pedido_de_regra(dia, item_sem_identificacao, *separar(explicacao)),
        )

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
        .data[0]
    )
    if proposta is None:
        return gravado
    fala = f"Faltou isto no Guia, em {_dia_curto(dia)}: {item_sem_identificacao}."
    do_lote = auditor.gravar_regra_do_faltou_isto(
        supabase,
        proposta,
        fala=fala,
        autor_id=autor_id,
        decide=decide,
        conversa_da_conta=conversa_id,
    )
    ligado = supabase.table("cm_faltou_isto").update({"lote_item_id": do_lote["id"]}).eq("id", gravado["id"]).execute()
    return {**(ligado.data or [{**gravado, "lote_item_id": do_lote["id"]}])[0], "lote_item": do_lote}


def proposta_de_regra(item: dict[str, Any] | None) -> str | None:
    """O que a tela diz da Regra que o apontamento gerou (issue #1496), pelo
    item do lote ligado a ele."""
    if not item:
        return None
    if item.get("estado") == "PROPOSTO":
        return 'A proposta de Regra está na conversa da Operadora, esperando o "ok".'
    if item.get("estado") == "DESCARTADO":
        return "A proposta de Regra foi descartada na conversa da Operadora."
    if (item.get("proposta_json") or {}).get("status") == "PENDENTE":
        return f"A Regra {item.get('regra_codigo')} entrou na memória como pendente e foi para a Validação."
    return f"A Regra {item.get('regra_codigo')} entrou na memória."


def para_a_tela(apontamento: dict[str, Any], me_id: str | None) -> dict[str, Any]:
    """O apontamento como o Guia mostra. O número da issue não sai: na tela,
    o pedido só está aberto ou não (ADR 0054, decisão 9)."""
    campos = ("id", "data", "item", "pagina", "texto", "origem", "classificacao", "explicacao", "criado_em")
    aberto = bool(apontamento.get("issue_numero"))
    return {
        **{chave: apontamento.get(chave) for chave in campos},
        "proposta_de_regra": proposta_de_regra(apontamento.get("lote_item")),
        "pedido_aberto": aberto,
        "pode_abrir_pedido": vira_pedido(apontamento) and not aberto and apontamento.get("apontado_por") == me_id,
    }


def da_conta(supabase, conta_id: str) -> list[dict[str, Any]]:
    """Os Faltou isto da Conta, do mais antigo ao mais novo, cada um com o item
    do lote da Regra que gerou (`lote_item`), quando gerou."""
    apontamentos = (
        supabase.table("cm_faltou_isto").select("*").eq("conta_id", conta_id).order("criado_em").execute().data or []
    )
    ids = sorted({a["lote_item_id"] for a in apontamentos if a.get("lote_item_id")})
    itens = (
        {i["id"]: i for i in supabase.table("cm_lote_item").select("*").in_("id", ids).execute().data or []}
        if ids
        else {}
    )
    return [{**a, "lote_item": itens.get(a.get("lote_item_id"))} for a in apontamentos]


# ─── O pedido para a Tecnologia (ADR 0081, decisão 4) ─────────────────────────
#
# LEITURA e DEFEITO viram issue `ready-for-agent` num repositório PÚBLICO. O
# corpo sai daqui, e a regra é a da peneira da Tecnologia: perder contexto,
# nunca vazar pessoa. A Conta vai pelo código (o id), nunca pelo número do
# atendimento, da conta ou pelo plano que a capa imprime; o texto do
# prontuário vai só no trecho do evento da página, que a leitura já
# desidentificou, e com até 300 caracteres.

VIRAM_PEDIDO = frozenset({"LEITURA", "DEFEITO"})
TRECHO_MAX = 300

ROTULO_DA_ORIGEM = {"LEITURA": "leitura da página", "DEFEITO": "defeito do sistema"}

MARCADOR_NUMERO = "[NUMERO]"
MARCADOR_DATA = "[DATA]"
MARCADOR_PLANO = "[PLANO]"

# Data completa digitada ou citada: a da internação, a de nascimento. O dia do
# apontamento não precisa dela, e o Guia escreve o dia sem o ano.
_DATA_COMPLETA = re.compile(r"(?<!\d)(?:\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|\d{4}-\d{2}-\d{2})(?!\d)")
# Número de cinco dígitos ou mais: carteira, guia, atendimento, conta. A
# quantidade e a página têm menos.
_NUMERO_LONGO = re.compile(r"(?<!\d)\d{5,}(?!\d)")
# `#42` no GitHub vira link para outra issue do repositório.
_NUMERO_DE_ISSUE = re.compile(r"(?<!&)(?:#|\bGH-)(\d+)", re.IGNORECASE)


class PedidoRecusadoError(Exception):
    """O ok não vale para este apontamento; a mensagem diz por quê."""


def vira_pedido(apontamento: dict[str, Any]) -> bool:
    return apontamento.get("classificacao") in VIRAM_PEDIDO


def _sem_identificacao(texto: str | None, conta: dict[str, Any], atendimento: dict[str, Any]) -> str:
    """O texto de quem apontou, do Auditor ou do trecho, pronto para o corpo
    público: o nome do rótulo da paciente, os valores da capa que a Conta
    guarda, as datas completas, a peneira da Ouvidoria e os números longos."""
    texto = desidentificar([texto or ""], Identificacao(nome=atendimento.get("paciente_rotulo")))[0]
    for valor, marcador in (
        (atendimento.get("numero_atendimento"), MARCADOR_NUMERO),
        (conta.get("numero_conta"), MARCADOR_NUMERO),
        (atendimento.get("plano"), MARCADOR_PLANO),
    ):
        if valor and str(valor).strip():
            texto = re.sub(rf"(?<!\w){re.escape(str(valor).strip())}(?!\w)", marcador, texto, flags=re.IGNORECASE)
    texto = _DATA_COMPLETA.sub(MARCADOR_DATA, texto)
    texto = _NUMERO_LONGO.sub(MARCADOR_NUMERO, pseudonimizar(texto))
    return texto


def _linha_publica(texto: str | None, conta: dict[str, Any], atendimento: dict[str, Any]) -> str:
    """Numa linha só, com o escape do corpo de issue da Tecnologia."""
    linha = " ".join(texto_do_diretor(_sem_identificacao(texto, conta, atendimento)).split())
    return _NUMERO_DE_ISSUE.sub(r"nº \1", linha)


def trecho_da_pagina(supabase, conta: dict[str, Any], apontamento: dict[str, Any]) -> str | None:
    """O trecho do primeiro evento do dia na página apontada, como a leitura do
    prontuário o guardou. Sem página, ou sem evento nela, não há trecho."""
    pagina = apontamento.get("pagina")
    if not pagina:
        return None
    dia = date.fromisoformat(apontamento["data"])
    do_dia = eventos_do_periodo(_eventos_guardados(supabase, conta["atendimento_id"]).get("ia") or {}, dia, dia)
    for lista in _LISTAS_DO_DIA:
        for evento in do_dia.get(lista) or []:
            if evento.get("pagina") == pagina and evento.get("trecho"):
                return evento["trecho"]
    return None


def _criterios(origem: str, pagina: int | None, esperado: str) -> list[str]:
    na_pagina = f"a página {pagina}" if pagina else "a página do dia apontado"
    if origem == "LEITURA":
        especificos = [
            f"A leitura do prontuário de uma conta como esta lê {na_pagina}, e o fato do trecho entra nos "
            "eventos do dia.",
            f"Com a leitura corrigida, o Guia aponta: {esperado}",
        ]
    else:
        especificos = [f"Com os eventos guardados de uma conta como esta, o Guia aponta: {esperado}"]
    return [
        *especificos,
        "Um teste com fixture sintética em texto reproduz a omissão: falha antes da correção e passa depois.",
        "Nenhum dado de prontuário real entra no teste, na fixture nem no PR.",
    ]


def titulo_do_pedido(apontamento: dict[str, Any], conta: dict[str, Any], atendimento: dict[str, Any]) -> str:
    item = _sem_identificacao(apontamento.get("item"), conta, atendimento)
    origem = ROTULO_DA_ORIGEM[apontamento["classificacao"]]
    return titulo_da_issue(f"Contas médicas: o Guia não apontou {item} ({origem})")


def corpo_do_pedido(
    apontamento: dict[str, Any], conta: dict[str, Any], atendimento: dict[str, Any], trecho: str | None
) -> str:
    """O corpo da issue: o bloco do diretor, a Conta de exemplo, os critérios de
    aceite e o marcador de origem do Auditor. Todo texto passa por
    `_linha_publica`; o código da Conta e o do apontamento são ids."""

    def publico(texto: str | None) -> str:
        return _linha_publica(texto, conta, atendimento)

    explicacao, esperado = separar(apontamento.get("explicacao"))
    esperado = publico(esperado) or "o Auditor não disse."
    pagina = apontamento.get("pagina")
    trecho_publico = publico(trecho)[:TRECHO_MAX].rstrip() or "nenhum evento lido nesta página."
    origem = ROTULO_DA_ORIGEM[apontamento["classificacao"]]
    return "\n".join(
        [
            CABECALHO_DO_BLOCO,
            "",
            f"**O que muda:** o Guia de Contas médicas passa a apontar o que faltou nesta conta. {esperado}",
            "",
            "**O que você precisa saber:**",
            f"- Pedido aberto pelo Auditor a partir de um Faltou isto no Guia, com origem em {origem}.",
            "- Quem apontou deu o ok antes de o pedido sair do app.",
            "",
            "---",
            "",
            "## A Conta de exemplo",
            "",
            f"- **Código da Conta:** `{conta['id']}`",
            f"- **Página do prontuário:** {pagina or 'não informada'}",
            f"- **Item que faltou:** {publico(apontamento.get('item'))}",
            f"- **Trecho da página (desidentificado):** {trecho_publico}",
            f"- **O esperado:** {esperado}",
            f"- **Explicação do Auditor:** {publico(explicacao)}",
            f"- **Mensagem de quem apontou:** {publico(apontamento.get('texto')) or 'sem mensagem.'}",
            "",
            "## Critérios de aceite",
            "",
            *[f"- [ ] {criterio}" for criterio in _criterios(apontamento["classificacao"], pagina, esperado)],
            "",
            "## Origem",
            "",
            "Faltou isto apontado no Guia de Contas médicas e classificado pelo Auditor (ADR 0081, decisão 4). "
            "O código da Conta acha no banco o apontamento, os eventos guardados e o Guia; o prontuário não sai "
            "do app.",
            "",
            f'<!-- auditor-contas-medicas faltou-isto="{apontamento["id"]}" -->',
        ]
    )


# O ok que está abrindo a issue agora, por apontamento: o segundo clique, de
# outra aba, não abre a segunda issue. Um processo só no servidor.
_abrindo: set[str] = set()
_trava_do_abrindo = threading.Lock()


def abrir_pedido(supabase, *, conta: dict[str, Any], atendimento: dict[str, Any], apontamento: dict[str, Any]) -> dict:
    """Abre a issue e grava o número no apontamento. A falha do GitHub sobe
    como `GithubIndisponivelError`, sem nada gravado: o ok vale de novo."""
    with _trava_do_abrindo:
        if apontamento["id"] in _abrindo:
            raise PedidoRecusadoError(MENSAGEM_PEDIDO_EM_ANDAMENTO)
        _abrindo.add(apontamento["id"])
    try:
        # O ok que terminou entre a leitura da rota e esta vez já gravou o número.
        relido = supabase.table("cm_faltou_isto").select("issue_numero").eq("id", apontamento["id"]).execute().data
        if relido and relido[0].get("issue_numero"):
            raise PedidoRecusadoError(MENSAGEM_PEDIDO_JA_ABERTO)
        dados = github_client.criar_issue(
            titulo=titulo_do_pedido(apontamento, conta, atendimento),
            corpo=corpo_do_pedido(apontamento, conta, atendimento, trecho_da_pagina(supabase, conta, apontamento)),
            labels=LABELS_DO_BUG,
        )
        numero = dados.get("number") if isinstance(dados, dict) else None
        if not isinstance(numero, int):
            raise github_client.GithubIndisponivelError("A criação da issue voltou sem número")
        gravado = (
            supabase.table("cm_faltou_isto").update({"issue_numero": numero}).eq("id", apontamento["id"]).execute().data
            or []
        )
        return gravado[0] if gravado else {**apontamento, "issue_numero": numero}
    finally:
        with _trava_do_abrindo:
            _abrindo.discard(apontamento["id"])


MENSAGEM_PEDIDO_EM_ANDAMENTO = "O pedido já está sendo aberto. Espere alguns segundos e recarregue a página."
MENSAGEM_PEDIDO_JA_ABERTO = "O pedido para a Tecnologia já foi aberto."
MENSAGEM_SO_LEITURA_OU_DEFEITO = "Só a página não lida ou o defeito do sistema viram pedido para a Tecnologia."
MENSAGEM_SO_QUEM_APONTOU = "Só quem apontou dá o ok do pedido para a Tecnologia."
MENSAGEM_GITHUB_FORA = "O GitHub não respondeu agora. O pedido não foi aberto: tente de novo em alguns instantes."
