"""A conversa da Operadora com o Auditor e o lote de propostas (issue #1490, PRD #1484, ADR 0081).

Quem tem "Regra contratual e tabelas" fala com o Auditor na Memória da
operadora. Uma interface só, `conversar`: a mensagem de quem decide é

- "ok": aplica o lote aberto numa versão nova da Memória, uma por lote, com
  as Regras vigentes no nome de quem deu o ok (decisões 1 e 5);
- "corrige o item N ...": o Auditor refaz só o item N, e a prova dele;
- qualquer outro texto: o Auditor devolve um lote novo de propostas tipadas
  (Regra nova, Regra alterada, parâmetro), cada uma com o motivo, os conflitos
  com as Regras da memória (decisão 8) e a Prova da regra (decisão 7). O lote
  aberto antes dele fica descartado.

A pergunta vai ao Auditor antes de qualquer gravação: se ele não responder,
nada fica pela metade. A prova roda depois que o lote está gravado; se ela
falhar, o item fica sem prova e o ok fica recusado até a correção provar de
novo (decisão 7).

A conversa é histórico, nunca memória (decisão 3): o Auditor recebe só a
mensagem desta vez, e nada daqui entra no prompt do Passo A nem do Passo B. A
mensagem que gerou o lote aplicado e as falas do ok apontam para a versão da
Memória que ele gerou.

Por dentro, reaproveita a regra candidata e o parâmetro da regra nova, a Prova
da regra e a gravação de versão da edição pela tela.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.services.contas_medicas import ia
from app.services.contas_medicas.contratos import (
    TETO_DO_TEXTO,
    confirmar_contrato,
    contrato_do_bloco,
    guardar_e_ler_contrato,
)
from app.services.contas_medicas.memoria import _CPF
from app.services.contas_medicas.memoria_edicao import (
    MudancaRecusadaError,
    _gravar_versao,
    _regras_da_versao,
)
from app.services.contas_medicas.memoria_texto import gerar_texto_memoria
from app.services.contas_medicas.prova_da_regra import provar_regra, resumo_da_prova
from app.services.contas_medicas.regra_nova import (
    _chave_valida,
    _com_parametro,
    _operadora_e_vigente,
    _proximo_codigo,
    _valor_do_parametro,
    _valor_json,
    contas_com_regra_nova,
)
from app.utils.text_sanitizer import sanitizar_estrutura

__all__ = ["LoteRecusadoError", "conversa_da_operadora", "conversar", "conversar_com_contrato"]

logger = logging.getLogger(__name__)

TIPOS_DE_REGRA = ("REGRA_NOVA", "REGRA_ALTERADA")

_OK = re.compile(r"ok[.!]*", re.IGNORECASE)
_CORRIGE = re.compile(r"corri[gj][ae]\s+o\s+item\s+(\d+)\b[\s:,.]*(.*)", re.IGNORECASE | re.DOTALL)


class LoteRecusadoError(ValueError):
    """O ok ou a correção não cabem no lote como ele está; a mensagem é para quem pediu."""


def _agora() -> str:
    return datetime.now(UTC).isoformat()


# ─── A conversa ─────────────────────────────────────────────────────────────


def _conversa(supabase, operadora_id: str) -> dict | None:
    achadas = (
        supabase.table("cm_conversa")
        .select("id")
        .eq("contexto", "OPERADORA")
        .eq("operadora_id", operadora_id)
        .order("criado_em")
        .limit(1)
        .execute()
        .data
        or []
    )
    return achadas[0] if achadas else None


def _conversa_ou_nova(supabase, operadora_id: str, autor_id: str | None) -> str:
    """A conversa da Operadora, uma só: quem volta continua a mesma."""
    achada = _conversa(supabase, operadora_id)
    if achada:
        return achada["id"]
    criada = (
        supabase.table("cm_conversa")
        .insert({"contexto": "OPERADORA", "operadora_id": operadora_id, "criado_por": autor_id})
        .execute()
    )
    return criada.data[0]["id"]


def _falar(
    supabase,
    conversa_id: str,
    autor: str,
    texto: str,
    autor_id: str | None = None,
    versao_id: str | None = None,
    anexo: str | None = None,
) -> dict:
    """Uma fala na conversa. Uma gravação por fala: a ordem é a do `criado_em`."""
    fala = {
        "conversa_id": conversa_id,
        "autor": autor,
        "autor_id": autor_id,
        "texto": texto,
        "memoria_versao_id": versao_id,
    }
    if anexo:
        fala["anexo_nome"] = anexo
    return supabase.table("cm_conversa_mensagem").insert(fala).execute().data[0]


def _lote_aberto(supabase, conversa_id: str) -> dict | None:
    abertos = (
        supabase.table("cm_lote")
        .select("*")
        .eq("conversa_id", conversa_id)
        .eq("estado", "PROPOSTO")
        .order("criado_em", desc=True)
        .execute()
        .data
        or []
    )
    return abertos[0] if abertos else None


def _itens(supabase, lote_id: str) -> list[dict[str, Any]]:
    return supabase.table("cm_lote_item").select("*").eq("lote_id", lote_id).order("numero").execute().data or []


# ─── O item do lote ─────────────────────────────────────────────────────────


def _item_do_auditor(proposta: ia.PropostaDoAuditor, vigente: dict, regras: dict[str, dict]) -> dict | None:
    """O item como o lote guarda: a proposta no formato da memória, o motivo e
    os conflitos com o texto da regra da memória. O "antes" vem da memória, não
    da IA. Regra alterada com código que a memória não tem vira regra nova;
    parâmetro com chave que não muda por regra e regra sem texto ficam de fora."""
    proposta = ia.PropostaDoAuditor.model_validate(sanitizar_estrutura(proposta.model_dump()))
    tipo = proposta.tipo
    codigo = proposta.regra_codigo.strip() or None
    if tipo == "PARAMETRO":
        chave = proposta.parametro.strip()
        if not _chave_valida(chave):
            return None
        dados: dict[str, Any] = {
            "chave": chave,
            "antes": _valor_do_parametro(vigente.get("parametros_json") or {}, chave),
            "depois": _valor_json(proposta.valor_json),
        }
        codigo = None
    else:
        if tipo == "REGRA_ALTERADA" and codigo not in regras:
            tipo, codigo = "REGRA_NOVA", None
        if tipo == "REGRA_NOVA":
            codigo = None
        if not proposta.texto.strip():
            return None
        dados = {
            "secao": (regras[codigo].get("secao") or proposta.secao) if codigo else proposta.secao,
            "texto": proposta.texto.strip(),
            "tipo": proposta.tipo_regra,
            "origem": proposta.origem.strip() or None,
        }
        if codigo:
            dados["texto_anterior"] = regras[codigo]["texto"]
    conflitos = {}
    for conflito in proposta.conflitos:
        # A regra alterada não conflita com ela mesma: o texto novo já a troca.
        if conflito.codigo in regras and conflito.codigo != codigo and conflito.codigo not in conflitos:
            conflitos[conflito.codigo] = {
                "codigo": conflito.codigo,
                "texto": regras[conflito.codigo]["texto"],
                "resolucao": conflito.resolucao,
            }
    return {
        "tipo": tipo,
        "regra_codigo": codigo,
        "proposta_json": dados,
        "motivo": proposta.motivo.strip() or None,
        "conflitos_json": list(conflitos.values()),
    }


def _em_conflito(item: dict) -> tuple[str, ...]:
    """As regras que o item junta ou substitui (ADR 0081, decisão 8): nos dois
    casos o texto do item fica e a regra em conflito sai, em vez de empilhar."""
    return tuple(c["codigo"] for c in item.get("conflitos_json") or [])


def _so_o_contrato_diz(item: dict) -> bool:
    """O item que só preenche o "o contrato diz" de uma Regra que existe: o
    texto fica como está e a análise não muda (issue #1495)."""
    dados = item.get("proposta_json") or {}
    return (
        item["tipo"] == "REGRA_ALTERADA"
        and "contrato_diz" in dados
        and dados.get("texto") == dados.get("texto_anterior")
    )


def _pede_prova(item: dict) -> bool:
    """A Prova da regra vale para o item que muda a análise (ADR 0081, decisão 7)."""
    return item["tipo"] in TIPOS_DE_REGRA and not _so_o_contrato_diz(item)


def _provar(supabase, sigla: str, item: dict, autor_id: str | None) -> None:
    """A Prova da regra do item, ligada a ele. Falha da prova não desfaz o lote:
    o item fica sem prova, e corrigir o item prova de novo."""
    if not _pede_prova(item):
        return
    regra = item["proposta_json"]
    try:
        provar_regra(
            supabase,
            sigla,
            secao=regra["secao"],
            texto=regra["texto"],
            tipo=regra["tipo"],
            origem=regra["origem"],
            parametro=None,
            autor_id=autor_id,
            codigo=item["regra_codigo"],
            lote_item_id=item["id"],
            sem=_em_conflito(item),
        )
    except (ia.ErroDaIA, MudancaRecusadaError) as erro:
        logger.warning("[ContasMedicas] Prova do item %s do lote sem resultado: %s", item["id"], type(erro).__name__)


# ─── As três mensagens ──────────────────────────────────────────────────────


def _novo_lote(supabase, sigla: str, texto: str, autor_id: str | None) -> None:
    sigla, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    memoria = gerar_texto_memoria(supabase, operadora_id, vigente["id"])
    resposta = ia.propor_lote(texto, memoria, supabase=supabase)

    regras = {r["codigo"]: r for r in _regras_da_versao(supabase, vigente["id"])}
    itens = [i for i in (_item_do_auditor(p, vigente, regras) for p in resposta.propostas) if i is not None]
    do_auditor = sanitizar_estrutura(resposta.resposta).strip()
    _gravar_lote(supabase, sigla, operadora_id, texto, itens, do_auditor, autor_id)


def _gravar_lote(
    supabase,
    sigla: str,
    operadora_id: str,
    fala: str,
    itens: list[dict[str, Any]],
    do_auditor: str,
    autor_id: str | None,
    *,
    fonte: str = "TEXTO",
    anexo: str | None = None,
) -> None:
    """A fala de quem pediu, o lote no lugar do aberto (quando há item), a fala
    do Auditor e a prova de cada item que muda a análise."""
    conversa_id = _conversa_ou_nova(supabase, operadora_id, autor_id)
    pessoa = _falar(supabase, conversa_id, "PESSOA", fala, autor_id, anexo=anexo)
    gravados: list[dict[str, Any]] = []
    if itens:
        # Um lote aberto por vez: o que estava aberto fica descartado.
        anterior = _lote_aberto(supabase, conversa_id)
        if anterior:
            supabase.table("cm_lote").update({"estado": "DESCARTADO"}).eq("id", anterior["id"]).execute()
            supabase.table("cm_lote_item").update({"estado": "DESCARTADO"}).eq("lote_id", anterior["id"]).execute()
        lote = (
            supabase.table("cm_lote")
            .insert(
                {
                    "operadora_id": operadora_id,
                    "conversa_id": conversa_id,
                    "mensagem_id": pessoa["id"],
                    "fonte": fonte,
                    "estado": "PROPOSTO",
                    "criado_por": autor_id,
                }
            )
            .execute()
            .data[0]
        )
        gravados = (
            supabase.table("cm_lote_item")
            .insert(
                [
                    {**item, "lote_id": lote["id"], "numero": n, "estado": "PROPOSTO"}
                    for n, item in enumerate(itens, start=1)
                ]
            )
            .execute()
            .data
        )
    _falar(supabase, conversa_id, "AUDITOR", do_auditor)
    for item in gravados:
        _provar(supabase, sigla, item, autor_id)


# ─── O contrato ─────────────────────────────────────────────────────────────

SEM_TEXTO = (
    "O arquivo não tem texto para ler (é imagem ou escaneado). Ele ficou guardado; as datas do aviso de reajuste "
    "se digitam na aba Contratos."
)
DATAS_NAO_LIDAS = "Não consegui ler as datas do contrato agora: digite as datas na aba Contratos."


def _item_das_datas(vigente: dict, campos: dict[str, Any], arquivo: str) -> dict | None:
    """As datas lidas do contrato, pela mesma leitura da aba Contratos, no
    bloco `contrato` do cabeçalho da memória. O ok confirma o contrato com
    elas, para o aviso de reajuste. Sem data lida, sem item."""
    if not any(valor for campo, valor in campos.items() if campo != "vencimento_calculado"):
        return None
    antes = (vigente.get("parametros_json") or {}).get("contrato")
    bloco = copy.deepcopy(antes) if isinstance(antes, dict) else {}
    if campos.get("data_assinatura"):
        bloco["assinatura"] = campos["data_assinatura"]
    if campos.get("vencimento_calculado"):
        # Vigência mais um ano: o bloco sem vencimento é lido assim.
        bloco.pop("vencimento", None)
    elif campos.get("vencimento"):
        bloco["vencimento"] = campos["vencimento"]
    aditivo = dict(bloco["ultimo_aditivo"]) if isinstance(bloco.get("ultimo_aditivo"), dict) else {}
    for chave, campo in (("numero", "aditivo_numero"), ("data", "aditivo_data"), ("inicio_vigencia", "vigencia_inicio")):
        if campos.get(campo):
            aditivo[chave] = campos[campo]
    if aditivo:
        bloco["ultimo_aditivo"] = aditivo
    return {
        "tipo": "PARAMETRO",
        "regra_codigo": None,
        "proposta_json": {"chave": "contrato", "antes": antes, "depois": bloco, "arquivo": arquivo},
        "motivo": "As datas do contrato, para o aviso de reajuste.",
        "conflitos_json": [],
    }


def _itens_do_contrato(resposta: ia.LoteDoContrato, vigente: dict, regras: dict[str, dict]) -> list[dict[str, Any]]:
    """As Regras por cláusula, com o trecho no "o contrato diz", e o "o
    contrato diz" das Regras que existem e que nenhum outro item toca."""
    itens = []
    for proposta in resposta.propostas:
        item = _item_do_auditor(
            ia.PropostaDoAuditor.model_validate(proposta.model_dump(exclude={"clausula"})), vigente, regras
        )
        # As datas do contrato vêm da leitura da aba Contratos, não daqui.
        if item is None or item["tipo"] == "PARAMETRO":
            continue
        clausula = sanitizar_estrutura(proposta.clausula).strip()
        if clausula:
            item["proposta_json"]["contrato_diz"] = clausula
        itens.append(item)
    tocadas = {i["regra_codigo"] for i in itens if i["regra_codigo"]} | {c for i in itens for c in _em_conflito(i)}
    for diz in resposta.o_contrato_diz:
        codigo, clausula = diz.regra_codigo.strip(), sanitizar_estrutura(diz.clausula).strip()
        if codigo not in regras or codigo in tocadas or not clausula:
            continue
        tocadas.add(codigo)
        regra = regras[codigo]
        itens.append(
            {
                "tipo": "REGRA_ALTERADA",
                "regra_codigo": codigo,
                "proposta_json": {
                    "secao": regra.get("secao"),
                    "texto": regra["texto"],
                    "tipo": regra.get("tipo"),
                    "origem": regra.get("origem"),
                    "texto_anterior": regra["texto"],
                    "contrato_diz": clausula,
                },
                "motivo": f"O contrato sustenta a regra {codigo}, para o recurso de glosa.",
                "conflitos_json": [],
            }
        )
    return itens


def conversar_com_contrato(supabase, sigla: str, nome: str, conteudo: bytes, autor_id: str | None) -> dict[str, Any]:
    """O contrato subido na conversa da Operadora (issue #1495, ADR 0081,
    decisão 9). Fica guardado como na aba Contratos, com as datas lidas do
    mesmo jeito, e o Auditor devolve o lote: as Regras por cláusula, o "o
    contrato diz" das Regras que existem e as datas do aviso de reajuste."""
    sigla, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    leitura, texto = guardar_e_ler_contrato(supabase, operadora_id, nome, conteudo)
    fala = f"Contrato enviado: {nome}"
    if not texto:
        conversa_id = _conversa_ou_nova(supabase, operadora_id, autor_id)
        _falar(supabase, conversa_id, "PESSOA", fala, autor_id, anexo=nome)
        _falar(supabase, conversa_id, "AUDITOR", SEM_TEXTO)
        return {**conversa_da_operadora(supabase, sigla), "aplicado": None}
    memoria = gerar_texto_memoria(supabase, operadora_id, vigente["id"])
    resposta = ia.propor_lote_do_contrato(texto[:TETO_DO_TEXTO], memoria, supabase=supabase)

    regras = {r["codigo"]: r for r in _regras_da_versao(supabase, vigente["id"])}
    itens = _itens_do_contrato(resposta, vigente, regras)
    datas = _item_das_datas(vigente, leitura["campos"], leitura["arquivo"])
    do_auditor = sanitizar_estrutura(resposta.resposta).strip()
    if datas:
        itens.append(datas)
    else:
        do_auditor = f"{do_auditor} {DATAS_NAO_LIDAS}".strip()
    _gravar_lote(supabase, sigla, operadora_id, fala, itens, do_auditor, autor_id, fonte="CONTRATO", anexo=nome)
    return {**conversa_da_operadora(supabase, sigla), "aplicado": None}


def _corrigir(supabase, sigla: str, numero: int, pedido: str, texto: str, autor_id: str | None) -> None:
    sigla, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    conversa = _conversa(supabase, operadora_id)
    lote = _lote_aberto(supabase, conversa["id"]) if conversa else None
    if lote is None:
        raise LoteRecusadoError("Não há lote aberto para corrigir. Escreva a regra que você quer ensinar.")
    alvo = next((i for i in _itens(supabase, lote["id"]) if i["numero"] == numero), None)
    if alvo is None:
        raise LoteRecusadoError(f"O lote não tem o item {numero}.")
    if not pedido.strip():
        raise LoteRecusadoError(f"Diga o que corrigir no item {numero}.")
    memoria = gerar_texto_memoria(supabase, operadora_id, vigente["id"])
    atual = {
        "tipo": alvo["tipo"],
        "regra_codigo": alvo.get("regra_codigo"),
        "proposta": alvo.get("proposta_json"),
        "motivo": alvo.get("motivo"),
        "conflitos": alvo.get("conflitos_json"),
    }
    resposta = ia.corrigir_item(memoria, json.dumps(atual, ensure_ascii=False), pedido.strip(), supabase=supabase)

    regras = {r["codigo"]: r for r in _regras_da_versao(supabase, vigente["id"])}
    refeito = _item_do_auditor(resposta.proposta, vigente, regras)
    if refeito is None:
        raise LoteRecusadoError(f"O Auditor não conseguiu refazer o item {numero}. Diga a correção de outro jeito.")
    # O que veio do contrato fica com o item corrigido: o trecho da cláusula e
    # o arquivo das datas (issue #1495).
    antes = alvo.get("proposta_json") or {}
    if refeito["tipo"] in TIPOS_DE_REGRA and antes.get("contrato_diz"):
        refeito["proposta_json"]["contrato_diz"] = antes["contrato_diz"]
    if refeito["tipo"] == "PARAMETRO" and antes.get("arquivo") and refeito["proposta_json"]["chave"] == antes.get("chave"):
        refeito["proposta_json"]["arquivo"] = antes["arquivo"]
    _falar(supabase, conversa["id"], "PESSOA", texto, autor_id)
    gravado = (
        supabase.table("cm_lote_item")
        .update({**refeito, "atualizado_em": _agora()})
        .eq("id", alvo["id"])
        .execute()
        .data[0]
    )
    # A prova do texto antigo se solta do item: se a nova falhar, ou se o item
    # virar parâmetro, a tela mostra o item sem prova, e não a de outra regra.
    supabase.table("cm_prova").update({"lote_item_id": None}).eq("lote_item_id", alvo["id"]).execute()
    _falar(supabase, conversa["id"], "AUDITOR", sanitizar_estrutura(resposta.resposta).strip())
    _provar(supabase, sigla, gravado, autor_id)


def _aplicar(supabase, sigla: str, texto: str, autor_id: str | None) -> dict[str, Any]:
    """O ok: o lote aberto inteiro numa versão nova da Memória, uma só."""
    sigla, operadora_id, vigente = _operadora_e_vigente(supabase, sigla)
    conversa = _conversa(supabase, operadora_id)
    lote = _lote_aberto(supabase, conversa["id"]) if conversa else None
    if lote is None:
        raise LoteRecusadoError("Não há lote aberto para aplicar.")
    itens = _itens(supabase, lote["id"])
    # Prova antes do ok (ADR 0081, decisão 7): item de regra sem prova não se aplica.
    provas = _provas(supabase, itens)
    for item in itens:
        if _pede_prova(item) and item["id"] not in provas:
            raise LoteRecusadoError(
                f"O item {item['numero']} está sem a prova da regra. "
                "Peça a correção do item para provar de novo antes do ok."
            )
    regras = _regras_da_versao(supabase, vigente["id"])
    por_codigo = {r["codigo"]: r for r in regras}
    agora = _agora()
    validacao = {"status": "VIGENTE", "validado_por": autor_id, "validado_em": agora}

    novas: list[dict[str, Any]] = []
    mudancas: dict[str, dict[str, Any]] = {}
    parametros: dict[str, Any] | None = None
    codigos: dict[str, str] = {}
    saem: dict[str, int] = {}
    so_diz: list[str] = []
    contrato: dict[str, Any] | None = None
    for item in itens:
        dados = item["proposta_json"]
        if item["tipo"] == "PARAMETRO":
            base = (vigente.get("parametros_json") or {}) if parametros is None else parametros
            parametros = _com_parametro(base, dados["chave"], dados["depois"])
            if lote.get("fonte") == "CONTRATO" and dados["chave"] == "contrato" and isinstance(dados["depois"], dict):
                contrato = dados
            continue
        if _CPF.search(f"{dados['texto']} {dados.get('contrato_diz') or ''}"):
            raise LoteRecusadoError(
                f"O item {item['numero']} tem um número no formato de CPF. A memória não pode ter dado de paciente: "
                "corrija o item."
            )
        if _so_o_contrato_diz(item):
            # Só o trecho do contrato: o texto, o tipo e a pendência da Regra ficam.
            if item["regra_codigo"] not in por_codigo:
                raise LoteRecusadoError(
                    f"A regra {item['regra_codigo']} do item {item['numero']} não está mais na memória: corrija o item."
                )
            mudancas[item["regra_codigo"]] = {"contrato_diz": dados["contrato_diz"]}
            codigos[item["id"]] = item["regra_codigo"]
            so_diz.append(item["regra_codigo"])
            continue
        campos = {"texto": dados["texto"], "tipo": dados["tipo"], "origem": dados.get("origem"), **validacao}
        if dados.get("contrato_diz"):
            campos["contrato_diz"] = dados["contrato_diz"]
        for conflito in _em_conflito(item):
            if conflito not in por_codigo:
                raise LoteRecusadoError(
                    f"A regra {conflito}, em conflito com o item {item['numero']}, não está mais na memória: "
                    "corrija o item."
                )
            saem.setdefault(conflito, item["numero"])
        if item["tipo"] == "REGRA_ALTERADA":
            if item["regra_codigo"] not in por_codigo:
                raise LoteRecusadoError(
                    f"A regra {item['regra_codigo']} do item {item['numero']} não está mais na memória: corrija o item."
                )
            mudancas[item["regra_codigo"]] = campos
            codigos[item["id"]] = item["regra_codigo"]
            continue
        codigo = _proximo_codigo(sigla, dados["secao"], [*regras, *novas])
        novas.append({"operadora_id": operadora_id, "codigo": codigo, "secao": dados["secao"], "ativa": True, **campos})
        codigos[item["id"]] = codigo

    for conflito, numero in saem.items():
        if conflito in mudancas:
            raise LoteRecusadoError(
                f"O item {numero} tira da memória a regra {conflito}, que outro item do lote altera: "
                "corrija um dos dois."
            )
    resumo = "Lote do Auditor: " + ", ".join(
        [f"{n['codigo']} incluída" for n in novas]
        + [f"{codigo} alterada" for codigo in mudancas if codigo not in so_diz]
        + [f"o contrato diz de {codigo}" for codigo in so_diz]
        + [f"{codigo} juntada ou substituída" for codigo in saem]
        + [f"parâmetro {i['proposta_json']['chave']}" for i in itens if i["tipo"] == "PARAMETRO"]
    )
    versao = _gravar_versao(
        supabase,
        operadora_id,
        vigente,
        regras,
        # A regra em conflito fica na versão nova, desligada: sai do Guia e da memória.
        {**mudancas, **{codigo: {"ativa": False} for codigo in saem}},
        autor_id,
        resumo,
        novas=novas,
        parametros=parametros,
    )
    if contrato is not None:
        # As datas do contrato valem como a confirmação da aba Contratos: o
        # contrato fica com o arquivo e o aviso de reajuste sai pela data nova.
        confirmar_contrato(
            supabase,
            operadora_id,
            {**contrato_do_bloco(contrato["depois"]), "arquivo": contrato.get("arquivo")},
            autor_id,
            datetime.now(UTC),
        )

    supabase.table("cm_lote").update(
        {"estado": "APLICADO", "memoria_versao_id": versao["id"], "aplicado_por": autor_id, "aplicado_em": agora}
    ).eq("id", lote["id"]).execute()
    for item in itens:
        supabase.table("cm_lote_item").update(
            {"estado": "APLICADO", "regra_codigo": codigos.get(item["id"], item.get("regra_codigo"))}
        ).eq("id", item["id"]).execute()
    # A mensagem que pediu o lote passa a apontar para a versão que ele gerou.
    if lote.get("mensagem_id"):
        supabase.table("cm_conversa_mensagem").update({"memoria_versao_id": versao["id"]}).eq(
            "id", lote["mensagem_id"]
        ).execute()
    _falar(supabase, conversa["id"], "PESSOA", texto, autor_id, versao["id"])
    contas = len(contas_com_regra_nova(supabase, sigla))
    _falar(
        supabase,
        conversa["id"],
        "AUDITOR",
        f"Lote aplicado: versão {versao['versao']} da memória, com {len(itens)} "
        + ("mudança." if len(itens) == 1 else "mudanças."),
        versao_id=versao["id"],
    )
    return {"versao": versao["versao"], "regras": list(codigos.values()), "contas_com_regra_nova": contas}


def conversar(supabase, sigla: str, texto: str, autor_id: str | None) -> dict[str, Any]:
    """A mensagem de quem decide: o ok, a correção de um item ou um texto que
    vira lote. Devolve a conversa como a tela mostra e, no ok, a versão nova."""
    texto = texto.strip()
    if not texto:
        raise LoteRecusadoError("Escreva a mensagem para o Auditor.")
    if _CPF.search(texto):
        raise LoteRecusadoError(
            "A mensagem tem um número no formato de CPF. A memória não pode ter dado de paciente: tire o número."
        )
    aplicado = None
    correcao = _CORRIGE.fullmatch(texto)
    if _OK.fullmatch(texto):
        aplicado = _aplicar(supabase, sigla, texto, autor_id)
    elif correcao:
        _corrigir(supabase, sigla, int(correcao.group(1)), correcao.group(2), texto, autor_id)
    else:
        _novo_lote(supabase, sigla, texto, autor_id)
    return {**conversa_da_operadora(supabase, sigla), "aplicado": aplicado}


# ─── A leitura para a tela ──────────────────────────────────────────────────


def _provas(supabase, itens: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A prova mais nova de cada item: a correção prova de novo."""
    if not itens:
        return {}
    provas = (
        supabase.table("cm_prova")
        .select("lote_item_id, resultado_json, criado_em")
        .in_("lote_item_id", [i["id"] for i in itens])
        .order("criado_em")
        .execute()
        .data
        or []
    )
    return {p["lote_item_id"]: p for p in provas}


def _prova_na_tela(prova: dict[str, Any] | None) -> dict[str, Any] | None:
    if prova is None:
        return None
    por_conta = prova.get("resultado_json") or []
    return {**resumo_da_prova(por_conta), "por_conta": por_conta}


def _nomes(supabase, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    pessoas = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute().data or []
    return {p["id"]: p.get("nome_completo") for p in pessoas}


def conversa_da_operadora(supabase, sigla: str) -> dict[str, Any]:
    """As falas da conversa, cada uma com a versão da Memória que gerou, e o
    lote aberto com os itens e a prova de cada um."""
    sigla, operadora_id, _vigente = _operadora_e_vigente(supabase, sigla)
    conversa = _conversa(supabase, operadora_id)
    if conversa is None:
        return {"mensagens": [], "lote": None}
    falas = (
        supabase.table("cm_conversa_mensagem")
        .select("*")
        .eq("conversa_id", conversa["id"])
        .order("criado_em")
        .execute()
        .data
        or []
    )
    ligadas = sorted({f["memoria_versao_id"] for f in falas if f.get("memoria_versao_id")})
    versoes = (
        {
            v["id"]: v["versao"]
            for v in supabase.table("cm_memoria_versao").select("id, versao").in_("id", ligadas).execute().data or []
        }
        if ligadas
        else {}
    )
    nomes = _nomes(supabase, {f["autor_id"] for f in falas if f.get("autor_id")})
    mensagens = [
        {
            "id": f["id"],
            "autor": f["autor"],
            "autor_nome": nomes.get(f.get("autor_id") or ""),
            "texto": f["texto"],
            "criado_em": f.get("criado_em"),
            "versao": versoes.get(f.get("memoria_versao_id") or ""),
        }
        for f in falas
    ]
    lote = _lote_aberto(supabase, conversa["id"])
    if lote is None:
        return {"mensagens": mensagens, "lote": None}
    itens = _itens(supabase, lote["id"])
    provas = _provas(supabase, itens)
    return {
        "mensagens": mensagens,
        "lote": {
            "id": lote["id"],
            "itens": [
                {
                    "numero": i["numero"],
                    "tipo": i["tipo"],
                    "regra_codigo": i.get("regra_codigo"),
                    "proposta": i.get("proposta_json") or {},
                    "motivo": i.get("motivo"),
                    "conflitos": i.get("conflitos_json") or [],
                    "pede_prova": _pede_prova(i),
                    "prova": _prova_na_tela(provas.get(i["id"])),
                }
                for i in itens
            ],
        },
    }
