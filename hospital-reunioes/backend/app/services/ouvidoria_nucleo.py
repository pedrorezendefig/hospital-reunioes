"""O envio ao Núcleo de Segurança do Paciente (issue #1621, PRD #1527, ADR 0088).

O Núcleo (NSP) precisa ver todo incidente relacionado à assistência (RDC
36/2013). O caso vai a ele como acionamento de **ciência**, com motivo `nsp`: o
Núcleo só confirma que recebeu, pelo botão "Recebido pelo NSP" de um link sem
senha, e a investigação dele segue por fora até o módulo próprio existir.

Quem decide é o ouvidor (decisão 4). O agente de triagem pode apontar o caso
(`nsp_sugerido`, com uma justificativa simples para o ouvidor e uma técnica
para o Núcleo); com o apontamento, a validação só conclui depois de o ouvidor
confirmar o envio ou descartar com motivo. Sem apontamento, o ouvidor manda
quando quiser.

Três regras que só valem aqui:

- O link do Núcleo mostra o relato integral, a justificativa técnica, o
  paciente com a data de nascimento, os profissionais e o quarto, **mesmo no
  sigilo reforçado** (decisão 5, a única exceção à decisão 8 da ADR 0034). Quem
  manifestou só aparece quando o caso não é sigiloso nem anônimo.
- O email só avisa e traz o link (decisão 6): o relato e a justificativa ficam
  na tela, porque o email passa por um processador fora do Brasil.
- O prazo do Recebido é imediato no caso crítico e de 1 dia útil nos demais, e
  a cobrança sobe ao gestor do setor e depois à Diretoria Executiva (decisão
  8). A ciência corre em paralelo: não bloqueia a resposta nem o encerramento.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.services import ouvidoria_acionamentos
from app.services.ouvidoria_prazos import DIAS_UTEIS, Prazo, calcular_vencimento
from app.services.ouvidoria_responsaveis import Destinatario

logger = logging.getLogger(__name__)

MOTIVO_NSP = ouvidoria_acionamentos.MOTIVO_NSP

CONFIRMADO = "confirmado"
DESCARTADO = "descartado"

# O selo que o caso ganha quando o envio é confirmado (seção 4.8 do anexo).
SELO = "Em análise pelo NSP"

# O prazo do Recebido nos casos que não são críticos (ADR 0088, decisão 8). O
# crítico é avisado na hora.
PRAZO_DO_RECEBIDO = Prazo(1, DIAS_UTEIS)

_CAMPOS = (
    "id, manifestacao_id, setor, responsavel_nome, responsavel_email, tipo, motivo_ciencia, "
    "status, prazo, enviado_em, respondido_em, escalonado_gestor_em, escalonado_diretoria_em"
)


def setor_configurado(supabase) -> str:
    """O setor do Núcleo na configuração da Ouvidoria, ou "" quando ninguém o
    escolheu ainda."""
    result = supabase.table("ouvidoria_config").select("nsp_setor").eq("id", True).limit(1).execute()
    if not result.data:
        return ""
    return (result.data[0].get("nsp_setor") or "").strip()


def ciencia_do_caso(supabase, manifestacao_id: str) -> dict | None:
    """A ciência do Núcleo daquele caso, em qualquer estado, ou None. Um caso
    tem no máximo uma (índice único da migration 139)."""
    result = (
        supabase.table(ouvidoria_acionamentos.TABELA)
        .select(_CAMPOS)
        .eq("manifestacao_id", manifestacao_id)
        .eq("motivo_ciencia", MOTIVO_NSP)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def carregar_pelo_token(supabase, token: str) -> dict:
    """A ciência do Núcleo do link. Levanta `LinkInvalidoError` quando o token
    não existe ou é de outra ciência (o link do elogio não abre o relato
    integral), e `ForaDeUsoError` quando a ciência perdeu a vez."""
    result = (
        supabase.table(ouvidoria_acionamentos.TABELA)
        .select(_CAMPOS)
        .eq("token_hash", ouvidoria_acionamentos.hash_do_token(token))
        .limit(1)
        .execute()
    )
    if not result.data or result.data[0].get("motivo_ciencia") != MOTIVO_NSP:
        raise ouvidoria_acionamentos.LinkInvalidoError()
    ciencia = result.data[0]
    if ciencia.get("status") not in (ouvidoria_acionamentos.PENDENTE, ouvidoria_acionamentos.CIENTE):
        raise ouvidoria_acionamentos.ForaDeUsoError()
    return ciencia


# O que a tela do Núcleo lê do caso. Fechado campo a campo, como o portal do
# setor: o relato integral e o paciente vão mesmo no sigilo reforçado (ADR
# 0088, decisão 5), e quem manifestou só no caso que não é sigiloso nem anônimo.
CAMPOS_DA_TELA = (
    "id, protocolo, status, tipo_manifestacao, gravidade, sigilo_reforcado, anonimo, manifestante_nome, "
    "relato_integral, nsp_justificativa_tecnica, paciente_nome, paciente_nascimento, profissionais, quarto, "
    "data_ocorrencia, periodo, hora_aprox, local_informado, anonimizada_em, apagamento_pedido_em"
)


def tela_do_nucleo(caso: dict, ciencia: dict) -> dict:
    """O que o link do Núcleo mostra (ADR 0088, decisão 5).

    O relato integral, a justificativa técnica, o paciente com a data de
    nascimento, os profissionais e o quarto saem em qualquer caso, inclusive no
    sigilo reforçado: é a única exceção à decisão 8 da ADR 0034, e vale só
    aqui. O nome de quem manifestou só sai quando o caso não é sigiloso nem
    anônimo."""
    from app.services.ouvidoria_prazos import formatar_vencimento

    sigiloso = bool(caso.get("sigilo_reforcado"))
    anonimo = bool(caso.get("anonimo"))
    nome_do_paciente = (caso.get("paciente_nome") or "").strip() or None
    nascimento = caso.get("paciente_nascimento") or None
    recebido = ciencia.get("status") == ouvidoria_acionamentos.CIENTE
    return {
        "protocolo": caso.get("protocolo"),
        "tipo_manifestacao": caso.get("tipo_manifestacao"),
        "gravidade": caso.get("gravidade"),
        "sigiloso": sigiloso,
        "anonimo": anonimo,
        "relato_integral": (caso.get("relato_integral") or "").strip() or None,
        "justificativa_tecnica": (caso.get("nsp_justificativa_tecnica") or "").strip() or None,
        "paciente": {"nome": nome_do_paciente, "nascimento": nascimento} if nome_do_paciente or nascimento else None,
        "profissionais": caso.get("profissionais") or None,
        "quarto": caso.get("quarto") or None,
        "data_ocorrencia": caso.get("data_ocorrencia"),
        "periodo": caso.get("periodo"),
        "hora_aprox": caso.get("hora_aprox"),
        "local_informado": caso.get("local_informado"),
        "quem_manifestou": None if sigiloso or anonimo else (caso.get("manifestante_nome") or None),
        "destinatario_nome": ciencia.get("responsavel_nome"),
        "prazo": formatar_vencimento(ciencia.get("prazo")) if ciencia.get("prazo") else None,
        "recebido": recebido,
        "recebido_em": ciencia.get("respondido_em") if recebido else None,
    }


def registrar_o_recebido(supabase, caso: dict, ciencia: dict) -> None:
    """O Recebido entra na trilha do caso, com o nome de quem recebeu o link."""
    nome = ciencia.get("responsavel_nome") or "Núcleo de Segurança do Paciente"
    _registrar_na_trilha(
        supabase,
        caso,
        {"id": None, "nome_completo": nome},
        f"Recebido pelo NSP: {nome}, do setor {ciencia.get('setor')}, confirmou o recebimento.",
    )


def prazo_do_recebido(agora: dt.datetime, gravidade: str | None, feriados: frozenset[dt.date]) -> dt.datetime:
    """Até quando o Núcleo tem para clicar em Recebido. Crítico é na hora."""
    if gravidade == "critico":
        return agora
    vencimento = calcular_vencimento(agora, PRAZO_DO_RECEBIDO, feriados)
    assert vencimento is not None  # 1 dia útil sempre tem data
    return vencimento


def enviar(
    supabase,
    *,
    caso: dict,
    setor: str,
    destinatario: Destinatario,
    gravidade: str | None,
    autor: dict,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> dict | None:
    """Manda o caso ao Núcleo: grava a ciência, a decisão e o selo, deixa o
    fato na trilha e põe o email na fila. Devolve a ciência, ou None quando ela
    não gravou."""
    from app.services import ouvidoria_notificacoes

    prazo = prazo_do_recebido(agora, gravidade, feriados)
    result = (
        supabase.table(ouvidoria_acionamentos.TABELA)
        .insert(
            {
                "manifestacao_id": caso["id"],
                "setor": setor,
                "responsavel_nome": destinatario.nome,
                "responsavel_email": destinatario.email,
                "tipo": ouvidoria_acionamentos.CIENCIA,
                "motivo_ciencia": MOTIVO_NSP,
                "status": ouvidoria_acionamentos.PENDENTE,
                "prazo": prazo.isoformat(),
                "enviado_em": agora.isoformat(),
            }
        )
        .execute()
    )
    if not result.data:
        return None
    ciencia = result.data[0]
    _gravar_decisao(supabase, caso["id"], CONFIRMADO, None, autor, agora)
    _registrar_na_trilha(
        supabase,
        caso,
        autor,
        f"Enviado ao Núcleo de Segurança do Paciente (setor {setor}), para ciência. Selo: {SELO}.",
    )

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=caso["id"],
        gatilho=ouvidoria_notificacoes.GATILHO_CIENCIA_NSP,
        destinatario_nome=destinatario.nome,
        destinatario_email=destinatario.email,
        papel_destinatario=destinatario.papel,
        # Crítico sai na hora, a qualquer hora; o resto espera o expediente.
        enviar_a_partir_de=ouvidoria_notificacoes.quando_enviar(agora, gravidade, feriados),
        # O prazo do Recebido, que o email diz: é da ciência, e não do caso.
        detalhe=prazo.isoformat(),
    )
    if notificacao is None:
        logger.error("[Ouvidoria] Falha ao registrar o email do Núcleo do caso %s", caso["id"])
    else:
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, feriados)
    return ciencia


def descartar(supabase, *, caso: dict, motivo: str, autor: dict, agora: dt.datetime) -> None:
    """O ouvidor descarta o apontamento do agente, com o motivo de uma linha.
    Fica gravado no caso e na trilha, e o Núcleo não recebe nada."""
    _gravar_decisao(supabase, caso["id"], DESCARTADO, motivo, autor, agora)
    _registrar_na_trilha(supabase, caso, autor, f"Envio ao Núcleo de Segurança do Paciente descartado. Motivo: {motivo}")


def _gravar_decisao(supabase, manifestacao_id: str, decisao: str, motivo: str | None, autor: dict, agora) -> None:
    supabase.table("ouvidoria_protocolos").update(
        {
            "nsp_decisao": decisao,
            "nsp_decisao_motivo": motivo,
            "nsp_decidido_por": autor["id"],
            "nsp_decidido_em": agora.isoformat(),
        }
    ).eq("id", manifestacao_id).execute()


def _registrar_na_trilha(supabase, caso: dict, autor: dict, observacao: str) -> None:
    """O fato entra na trilha do caso. Não é transição de estado, então o
    insert é direto. Melhor esforço: a trilha não desfaz o ato."""
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": caso["id"],
                "estado_anterior": caso.get("status"),
                "estado_novo": caso.get("status"),
                "autor_id": autor.get("id"),
                "autor_nome": autor.get("nome_completo") or autor.get("id") or "Sistema",
                "observacao": observacao,
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao gravar o movimento do Núcleo na trilha do caso %s", caso.get("id"))
