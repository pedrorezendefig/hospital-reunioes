"""O registro de acionamento e o elogio como ciência (issue #1618, ADR 0088).

O acionamento é o envio de um caso a um setor, com tipo decidido pelo sistema e
nunca pelo ouvidor: **resposta** (a área responde no prazo) ou **ciência** (a
área só confirma que recebeu). Nesta fase o registro guarda só as ciências; o
acionamento de resposta continua no caso e passa para cá na fase 2, quando um
caso puder ir a até três setores (ADR 0088, decisão 1).

A primeira ciência é o elogio (decisão 2): sem prazo de área, sem cobrança, com
o botão "Elogio recebido" no email, que abre sem senha e vale uma vez. Sem o
clique em 5 dias úteis, o email sai de novo uma única vez.

O link segue o padrão do portal do setor (`ouvidoria_setor_tokens`): o token em
claro vive só no email, e o banco guarda o hash. A diferença é que o hash mora
na linha do acionamento, e cada envio emite um token novo por cima do anterior:
o link que vale é o do email mais recente. O uso único não depende do token,
depende do acionamento: a confirmação só passa de `pendente` para `ciente` uma
vez, então nenhum link confirma duas vezes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import secrets

from app.config import settings
from app.services.ouvidoria_prazos import DIAS_UTEIS, Prazo, calcular_vencimento, esta_vencido

logger = logging.getLogger(__name__)

TABELA = "ouvidoria_acionamentos"

RESPOSTA = "resposta"
CIENCIA = "ciencia"
MOTIVO_ELOGIO = "elogio"

PENDENTE = "pendente"
CIENTE = "ciente"
# O acionamento que perdeu a vez: o caso voltou à Ouvidoria e foi mandado de
# novo, e a ciência antiga não confirma mais nada.
DEVOLVIDO = "devolvido"

# Quanto o elogio espera o clique antes do reenvio único (ADR 0088, decisão 2).
ESPERA_DO_REENVIO = Prazo(5, DIAS_UTEIS)

# O que a trilha diz quando o setor confirma. A marca "Pronto para encerrar" vai
# escrita na trilha, e é a mesma frase que a fila do ouvidor mostra.
PRONTO_PARA_ENCERRAR = "Pronto para encerrar"

_CAMPOS = (
    "id, manifestacao_id, setor, responsavel_nome, responsavel_email, tipo, motivo_ciencia, "
    "status, enviado_em, respondido_em, reenviado_em"
)


class LinkInvalidoError(Exception):
    """Token que não existe: link adulterado, de outro sistema ou substituído
    por um envio mais novo."""


class JaConfirmadoError(Exception):
    """O setor já confirmou o elogio: o link não vale de novo."""


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def criar_ciencia_do_elogio(
    supabase,
    *,
    manifestacao_id: str,
    setor: str,
    responsavel_nome: str,
    responsavel_email: str,
    agora: dt.datetime,
) -> dict | None:
    """Grava a ciência do elogio e devolve a linha, ou None quando não gravou.

    A ciência anterior do mesmo caso que ainda esperava o clique perde a vez
    (vira `devolvido`): o caso voltou à Ouvidoria e está sendo mandado de novo,
    talvez a outro setor, e o link antigo não pode confirmar o envio novo.

    `enviado_em` é o instante do acionamento, e é dele que os 5 dias úteis do
    reenvio contam. O email retido pela janela comercial sai na abertura
    seguinte, e a contagem em dias úteis também só começa ali."""
    (
        supabase.table(TABELA)
        .update({"status": DEVOLVIDO})
        .eq("manifestacao_id", manifestacao_id)
        .eq("tipo", CIENCIA)
        .eq("status", PENDENTE)
        .execute()
    )
    result = (
        supabase.table(TABELA)
        .insert(
            {
                "manifestacao_id": manifestacao_id,
                "setor": setor,
                "responsavel_nome": responsavel_nome,
                "responsavel_email": responsavel_email,
                "tipo": CIENCIA,
                "motivo_ciencia": MOTIVO_ELOGIO,
                "status": PENDENTE,
                "prazo": None,
                "enviado_em": agora.isoformat(),
            }
        )
        .execute()
    )
    return result.data[0] if result.data else None


def ciencia_pendente(supabase, manifestacao_id: str) -> dict | None:
    """A ciência do elogio que ainda espera o clique naquele caso, ou None."""
    result = (
        supabase.table(TABELA)
        .select(_CAMPOS)
        .eq("manifestacao_id", manifestacao_id)
        .eq("tipo", CIENCIA)
        .eq("motivo_ciencia", MOTIVO_ELOGIO)
        .eq("status", PENDENTE)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def emitir_link(supabase, acionamento: dict) -> str:
    """O link do botão "Elogio recebido", com token novo, e o hash dele gravado
    no acionamento. Chamado na hora do envio do email: o reenvio emite outro, e
    o link anterior deixa de abrir."""
    token = secrets.token_urlsafe(32)
    supabase.table(TABELA).update({"token_hash": _hash(token)}).eq("id", acionamento["id"]).execute()
    return f"{settings.frontend_url}/ouvidoria-setor/elogio/{token}"


def carregar_pelo_token(supabase, token: str) -> dict:
    """Acha o acionamento do link. Levanta `LinkInvalidoError` quando não há
    nenhum e `JaConfirmadoError` quando ele já não espera o clique."""
    result = supabase.table(TABELA).select(_CAMPOS).eq("token_hash", _hash(token)).limit(1).execute()
    if not result.data:
        raise LinkInvalidoError()
    acionamento = result.data[0]
    if acionamento.get("status") != PENDENTE:
        raise JaConfirmadoError()
    return acionamento


def confirmar(supabase, acionamento: dict, agora: dt.datetime) -> bool:
    """O clique: `pendente` vira `ciente`, uma vez só. Devolve False quando
    outra requisição chegou antes (o segundo clique não confirma nada)."""
    result = (
        supabase.table(TABELA)
        .update({"status": CIENTE, "respondido_em": agora.isoformat()})
        .eq("id", acionamento["id"])
        .eq("status", PENDENTE)
        .execute()
    )
    return bool(result.data)


def desfazer_confirmacao(supabase, acionamento: dict, carimbo: str) -> None:
    """Devolve o acionamento a `pendente` quando o caso não andou depois do
    clique, para o responsável poder clicar de novo. Só desfaz o clique DESTA
    requisição (o `respondido_em` dela)."""
    (
        supabase.table(TABELA)
        .update({"status": PENDENTE, "respondido_em": None})
        .eq("id", acionamento["id"])
        .eq("respondido_em", carimbo)
        .execute()
    )


def esqueceu_de_confirmar(acionamento: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> bool:
    """Se o elogio já esperou os 5 dias úteis sem clique e ainda não foi
    reenviado."""
    if acionamento.get("status") != PENDENTE or acionamento.get("reenviado_em"):
        return False
    enviado = acionamento.get("enviado_em")
    if not enviado:
        return False
    limite = calcular_vencimento(dt.datetime.fromisoformat(str(enviado)), ESPERA_DO_REENVIO, feriados)
    return esta_vencido(limite, agora)
