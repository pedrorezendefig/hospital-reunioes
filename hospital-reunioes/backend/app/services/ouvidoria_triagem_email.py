"""Triagem de e-mail da Ouvidoria (ADR 0051, PRD #646, issue #648).

O e-mail que chega em ouvidoria@ é copiado para o subdomínio de recebimento do
Resend, e o Resend chama o webhook do app. Aqui ele vira um **e-mail recebido**:
um item da Triagem de e-mail, que só o Perfil da Ouvidoria vê, e que não é
caso nenhum. Quem decide se vira manifestação, se junta a um caso ou se é
descartado é o ouvidor (as fatias seguintes do PRD); esta fatia faz o e-mail
chegar e aparecer.

Três garantias moram aqui, e cada uma tem teste:

1. **Um e-mail, um item.** A dedup é pelo identificador do e-mail no Resend,
   com a coluna única no banco atrás dela: a reentrega e a entrega concorrente
   respondem sucesso e não criam nada.
2. **O que veio não se perde.** Falha ao buscar corpo ou anexo grava o item
   com o que veio, marcado como incompleto, e o erro vai para o log. A
   reentrega do Resend completa o item em vez de duplicar.
3. **O binário do anexo nunca é público.** Ele vai para o bucket privado da
   Ouvidoria e é lido por URL assinada, como o anexo do caso (ADR 0034).
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr

from postgrest.exceptions import APIError

from app.config import settings
from app.services import email_service, storage
from app.services.ouvidoria_anexos import TIPOS_PERMITIDOS
from app.services.paginacao import ler_tudo

logger = logging.getLogger(__name__)

TABELA = "ouvidoria_emails_recebidos"
TABELA_ANEXOS = "ouvidoria_emails_recebidos_anexos"

# Os quatro estados da triagem (PRD #646). Só o primeiro nasce aqui; os outros
# três são as decisões do ouvidor, uma por fatia.
PENDENTE = "pendente"
ESTADOS = (PENDENTE, "virou_manifestacao", "juntado", "descartado")

# O que o webhook fez com a entrega.
CRIADO = "criado"
COMPLETADO = "completado"
DUPLICADO = "duplicado"

# O que a lista mostra: o cabeçalho, sem corpo. O corpo é dado pessoal e só sai
# quando o ouvidor abre o item, e é essa abertura que entra no log de acesso.
CAMPOS_DA_LISTA = (
    "id",
    "remetente_endereco",
    "remetente_nome",
    "assunto",
    "recebido_em",
    "estado",
    "incompleto",
    "interno",
    "decidido_em",
    "decidido_por_nome",
    "manifestacao_id",
)

# O item aberto. O `corpo_html` NÃO está aqui, e isso é a decisão: ele fica
# guardado e nunca sai para a tela, que desenha só o texto (issue #648).
CAMPOS_DO_ITEM = CAMPOS_DA_LISTA + ("destinatarios", "corpo_texto", "cabecalhos")

_CAMPOS_DO_ANEXO = ("id", "filename", "content_type", "tamanho_bytes", "storage_path")

# Quantos ids cabem num `in.(...)` sem a URL da consulta crescer demais.
_LOTE_DE_IDS = 100


@dataclass(frozen=True)
class Recebimento:
    """O desfecho da entrega: `criado`, `completado` ou `duplicado`, e se o
    item ficou incompleto (é o que faz o webhook pedir a reentrega)."""

    desfecho: str
    incompleto: bool


# ─── Remetente ──────────────────────────────────────────────────────────────


def remetente_do(campo_from: str | None) -> tuple[str, str | None]:
    """(endereço, nome) de um `From` como `Joana da Silva <joana@gmail.com>`.
    O endereço sai em minúsculas; o nome, quando não há, é None."""
    nome, endereco = parseaddr(campo_from or "")
    return endereco.strip().lower(), (nome.strip() or None)


def _dominios_internos() -> tuple[str, ...]:
    return tuple(
        dominio.strip().lower().lstrip("@").rstrip(".")
        for dominio in (settings.ouvidoria_dominio_interno or "").split(",")
        if dominio.strip()
    )


def e_interno(endereco: str) -> bool:
    """Se o remetente é do domínio do hospital (subdomínio conta).

    É marca de leitura, e não permissão: o `From` de um e-mail se forja, e por
    isso a marca só ajuda o ouvidor a reconhecer resposta de área. Nada no app
    decide acesso ou fluxo por ela."""
    _, arroba, dominio = (endereco or "").rpartition("@")
    if not arroba or not dominio:
        return False
    dominio = dominio.lower()
    return any(dominio == d or dominio.endswith(f".{d}") for d in _dominios_internos())


# ─── Webhook: receber o e-mail ──────────────────────────────────────────────


def _carregar_por_resend_id(supabase, resend_email_id: str) -> dict | None:
    resultado = (
        supabase.table(TABELA)
        .select("id, estado, incompleto, corpo_texto, corpo_html")
        .eq("resend_email_id", resend_email_id)
        .execute()
    )
    return resultado.data[0] if resultado.data else None


def _lista_de_texto(valor) -> list[str]:
    if isinstance(valor, list):
        return [str(v) for v in valor if v]
    return [str(valor)] if valor else []


def _linha_nova(dados: dict, lido: email_service.EmailDoResend | None) -> dict:
    endereco, nome = remetente_do(dados.get("from"))
    return {
        "resend_email_id": str(dados["email_id"]),
        "remetente_endereco": endereco,
        "remetente_nome": nome,
        "destinatarios": _lista_de_texto(dados.get("to")),
        "assunto": str(dados.get("subject") or ""),
        # A data de chegada é a do Resend, e não a do processamento: a
        # reentrega de amanhã não pode mudar quando o e-mail chegou.
        "recebido_em": dados.get("created_at") or datetime.now(UTC).isoformat(),
        "corpo_texto": lido.texto if lido else None,
        "corpo_html": lido.html if lido else None,
        "cabecalhos": lido.cabecalhos if lido else {},
        "estado": PENDENTE,
        "interno": e_interno(endereco),
        # Pessimista de propósito: o item nasce incompleto e só deixa de ser
        # depois de os anexos estarem guardados. Uma queda no meio deixa a marca
        # certa, e a reentrega completa.
        "incompleto": True,
    }


def _metas_do_evento(dados: dict) -> dict[str, dict]:
    metas = {}
    for meta in dados.get("attachments") or []:
        if isinstance(meta, dict) and meta.get("id"):
            metas[str(meta["id"])] = meta
    return metas


def _tipo_guardado(filename: str) -> tuple[str, str]:
    """(extensão, content-type) com que o binário vai para o bucket.

    O tipo declarado no e-mail é de quem mandou, e quem serve o arquivo depois é
    uma URL assinada do storage: um anexo `.html` servido como `text/html`
    abriria como página. Só os tipos que a Ouvidoria já aceita (o mesmo
    catálogo do anexo do caso) saem com o tipo deles; o resto sai como binário
    genérico, que o navegador baixa em vez de abrir."""
    extensao = os.path.splitext(filename or "")[1].lower()
    if extensao in TIPOS_PERMITIDOS:
        return extensao, TIPOS_PERMITIDOS[extensao]
    return "", "application/octet-stream"


def _guardar_anexos(
    supabase,
    email_recebido_id: str,
    metas: dict[str, dict],
    lido: email_service.EmailDoResend | None,
) -> int:
    """Guarda o binário de cada anexo que ainda não está no bucket e devolve
    quantos continuam faltando.

    Todo anexo que o e-mail anuncia ganha linha, com o binário ou sem ele: o
    ouvidor precisa saber que havia um arquivo, mesmo quando ele não veio. A
    linha sem `storage_path` é a que a reentrega vem completar."""
    existentes = {
        a["resend_anexo_id"]: a
        for a in (
            supabase.table(TABELA_ANEXOS)
            .select("id, resend_anexo_id, storage_path")
            .eq("email_recebido_id", email_recebido_id)
            .execute()
            .data
            or []
        )
    }
    binarios = {a.id: a for a in (lido.anexos if lido else ()) if a.id}
    ordem = list(dict.fromkeys([*metas, *binarios]))
    bucket = settings.supabase_storage_bucket_anexos_ouvidoria

    faltando = 0
    for anexo_id in ordem:
        atual = existentes.get(anexo_id)
        if atual and atual.get("storage_path"):
            continue
        anexo = binarios.get(anexo_id)
        meta = metas.get(anexo_id, {})
        filename = (anexo.filename if anexo else "") or str(meta.get("filename") or "") or "anexo"
        content_type = (anexo.content_type if anexo else "") or str(meta.get("content_type") or "")
        path = None
        tamanho = None
        if anexo is not None and anexo.conteudo is not None:
            extensao, tipo_guardado = _tipo_guardado(filename)
            # Caminho sorteado: o nome original pode trazer o nome de quem
            # escreveu, e não vira parte de caminho no storage.
            candidato = f"email-recebido-{email_recebido_id}/{uuid.uuid4().hex}{extensao}"
            if storage.upload_private(supabase, bucket, candidato, anexo.conteudo, content_type=tipo_guardado):
                path, tamanho = candidato, len(anexo.conteudo)
        else:
            motivo = anexo.erro if anexo is not None else "não lido"
            logger.error("Triagem de e-mail: anexo %s do e-mail %s não veio (%s)", anexo_id, email_recebido_id, motivo)

        campos = {
            "filename": filename,
            "content_type": content_type or "application/octet-stream",
            "storage_path": path,
            "tamanho_bytes": tamanho,
        }
        try:
            if atual:
                supabase.table(TABELA_ANEXOS).update(campos).eq("id", atual["id"]).execute()
            else:
                supabase.table(TABELA_ANEXOS).insert(
                    {"email_recebido_id": email_recebido_id, "resend_anexo_id": anexo_id} | campos
                ).execute()
        except APIError:
            # Sem a linha, o binário é órfão que ninguém alcança: sai agora, e se
            # não sair, o caminho fica no log, que é o único jeito de achá-lo.
            if path and not storage.delete_file(supabase, bucket, path):
                logger.error("Anexo órfão no bucket após falha de registro: %s", path)
            logger.error("Triagem de e-mail: falha ao registrar o anexo %s do e-mail %s", anexo_id, email_recebido_id)
            path = None
        if path is None:
            faltando += 1
    return faltando


def receber_email(supabase, dados: dict) -> Recebimento:
    """Grava o e-mail recebido do evento `email.received` (o `data` dele).

    Corpo, cabeçalhos e anexos são buscados no Resend no ato. O item que já
    existe completo, ou que já foi decidido, não é tocado: é a dedup, e é
    também o que impede a reentrega de devolver o corpo a um e-mail que o
    ouvidor descartou."""
    resend_email_id = str(dados["email_id"])
    existente = _carregar_por_resend_id(supabase, resend_email_id)
    if existente and (not existente.get("incompleto") or existente.get("estado") != PENDENTE):
        return Recebimento(DUPLICADO, bool(existente.get("incompleto")))

    lido = None
    try:
        lido = email_service.ler_email_recebido(resend_email_id)
    except Exception as exc:  # noqa: BLE001 (o item é gravado com o que veio, e a reentrega completa)
        # Só o tipo da falha vai para o log: a mensagem de uma exceção qualquer
        # pode ecoar remetente ou assunto. A da leitura já é só o tipo.
        motivo = exc if isinstance(exc, email_service.LeituraDoResendError) else type(exc).__name__
        logger.error("Triagem de e-mail: o corpo do e-mail %s não veio do Resend (%s)", resend_email_id, motivo)

    if existente is None:
        try:
            linha = supabase.table(TABELA).insert(_linha_nova(dados, lido)).execute().data[0]
        except APIError as exc:
            # A coluna única segurou a entrega concorrente do mesmo e-mail: a
            # outra está gravando, e esta não tem nada a fazer.
            if getattr(exc, "code", None) == "23505":
                return Recebimento(DUPLICADO, True)
            raise
        desfecho = CRIADO
        corpo_ja_lido = False
    else:
        linha = existente
        corpo_ja_lido = existente.get("corpo_texto") is not None or existente.get("corpo_html") is not None
        if lido is not None:
            supabase.table(TABELA).update(
                {"corpo_texto": lido.texto, "corpo_html": lido.html, "cabecalhos": lido.cabecalhos}
            ).eq("id", linha["id"]).execute()
        desfecho = COMPLETADO

    faltando = _guardar_anexos(supabase, linha["id"], _metas_do_evento(dados), lido)
    incompleto = (lido is None and not corpo_ja_lido) or faltando > 0
    supabase.table(TABELA).update({"incompleto": incompleto}).eq("id", linha["id"]).execute()
    return Recebimento(desfecho, incompleto)


# ─── Leitura da triagem ─────────────────────────────────────────────────────


def _contar_anexos(supabase, ids: list[str]) -> dict[str, int]:
    contagem: dict[str, int] = {}
    for inicio in range(0, len(ids), _LOTE_DE_IDS):
        lote = ids[inicio : inicio + _LOTE_DE_IDS]
        resultado = supabase.table(TABELA_ANEXOS).select("email_recebido_id").in_("email_recebido_id", lote).execute()
        for linha in resultado.data or []:
            chave = linha["email_recebido_id"]
            contagem[chave] = contagem.get(chave, 0) + 1
    return contagem


def listar(supabase) -> list[dict]:
    """Os e-mails recebidos, pendentes primeiro e, dentro de cada grupo, na
    ordem de chegada, o mais antigo primeiro: é a ordem em que a triagem se
    faz."""
    linhas = ler_tudo(
        lambda: supabase.table(TABELA).select(", ".join(CAMPOS_DA_LISTA)).order("recebido_em").order("id"),
        rotulo="e-mails recebidos da triagem",
    )
    # `sorted` é estável: dentro de cada grupo a ordem de chegada do banco fica.
    linhas = sorted(linhas, key=lambda linha: linha.get("estado") != PENDENTE)
    contagem = _contar_anexos(supabase, [linha["id"] for linha in linhas])
    return [
        {campo: linha.get(campo) for campo in CAMPOS_DA_LISTA} | {"quantidade_de_anexos": contagem.get(linha["id"], 0)}
        for linha in linhas
    ]


def carregar_item(supabase, email_id: str) -> dict | None:
    """O item aberto, com o corpo em texto e os anexos (sem caminho de
    storage: o binário só sai por URL assinada). None quando não existe."""
    try:
        resultado = supabase.table(TABELA).select(", ".join(CAMPOS_DO_ITEM)).eq("id", email_id).execute()
    except APIError:
        # Id que não é UUID faz o PostgREST recusar o filtro (22P02): do lado de
        # fora é o mesmo que item inexistente.
        return None
    if not resultado.data:
        return None
    linha = resultado.data[0]
    anexos = (
        supabase.table(TABELA_ANEXOS)
        .select(", ".join(_CAMPOS_DO_ANEXO))
        .eq("email_recebido_id", email_id)
        .order("created_at")
        .order("id")
        .execute()
        .data
        or []
    )
    return {campo: linha.get(campo) for campo in CAMPOS_DO_ITEM} | {
        "cabecalhos": linha.get("cabecalhos") or {},
        "destinatarios": linha.get("destinatarios") or [],
        "anexos": [
            {
                "id": a["id"],
                "filename": a.get("filename"),
                "content_type": a.get("content_type"),
                "tamanho_bytes": a.get("tamanho_bytes"),
                # Anexo sem binário é o que não veio do Resend: a tela mostra o
                # nome, e não oferece o link.
                "disponivel": bool(a.get("storage_path")),
            }
            for a in anexos
        ],
    }


def caminho_do_anexo(supabase, email_id: str, anexo_id: str) -> dict | None:
    """O anexo DESTE e-mail, com o caminho no storage. Sem o casamento dos dois
    ids, o id de um anexo viraria caminho lateral para o anexo de outro e-mail.
    None quando não existe ou quando o binário não está guardado."""
    try:
        resultado = (
            supabase.table(TABELA_ANEXOS)
            .select("id, filename, storage_path")
            .eq("id", anexo_id)
            .eq("email_recebido_id", email_id)
            .execute()
        )
    except APIError:
        return None
    if not resultado.data or not resultado.data[0].get("storage_path"):
        return None
    return resultado.data[0]


def registrar_acesso_ao_email(supabase, me: dict, email_id: str, acao: str) -> None:
    """O log de acesso do Perfil da Ouvidoria, com o e-mail recebido como alvo
    (migration 112). Falha aqui não derruba a leitura, pela mesma razão do log
    do caso: a trilha importa, mas deixar o ouvidor sem o e-mail seria pior."""
    try:
        supabase.table("ouvidoria_acessos").insert(
            {
                "email_recebido_id": email_id,
                "ator_id": me["id"],
                "ator_nome": me.get("nome_completo") or me["id"],
                "acao": acao,
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao registrar acesso ao e-mail recebido %s", email_id)
