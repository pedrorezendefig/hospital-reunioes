"""Notificações da Ouvidoria: registro, janela de envio e retentativa (issue #325).

Toda notificação da Ouvidoria nasce como linha em `ouvidoria_notificacoes`
antes de virar email (ADR 0034, decisão 7): é o que prova a cobrança, é o que o
ouvidor reenvia e é o que sobra quando o Resend cai.

Duas regras de tempo moram aqui:

- **Janela comercial** (RN da spec): notificação não crítica gerada de
  madrugada, no fim de semana ou em feriado espera a próxima abertura do
  expediente. Caso crítico sai na hora, seja lá que horas forem.
- **Retentativa com backoff**: falha do provedor não perde a notificação, ela
  volta para a fila com espera crescente. Na terceira falha o caso vira alerta
  ao admin técnico do app, porque aí o problema é de infraestrutura.

O catálogo completo de gatilhos (escalonamento, cores) é do PRD de governança
de prazo (#318). Aqui existem o acionamento da área e os dois alertas que ele
pode gerar.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.config import settings
from app.services.email_service import _enviar_email, jinja_env
from app.services.ouvidoria_prazos import FUSO, inicio_da_contagem, rotular_vencimento

logger = logging.getLogger(__name__)

GATILHO_NOVA_DEMANDA = "nova_demanda"
GATILHO_ALERTA_SEM_TITULAR = "alerta_sem_titular"
GATILHOS = (GATILHO_NOVA_DEMANDA, GATILHO_ALERTA_SEM_TITULAR)

AGENDADA = "agendada"
# Linha em voo: reivindicada por quem vai chamar o provedor. O job periódico só
# lê `agendada`, então o mesmo email não sai duas vezes enquanto o Resend
# responde.
ENVIANDO = "enviando"
ENVIADA = "enviada"
FALHA = "falha"

# Três tentativas: depois disso o problema não é o pico de instabilidade que a
# espera resolve, e insistir só atrasa o alerta a quem pode consertar.
MAX_TENTATIVAS = 3
# Espera crescente entre tentativas, em minutos. O índice é a tentativa que
# acabou de falhar.
BACKOFF_MINUTOS = (5, 15, 45)

CAMPOS_NOTIFICACAO_TUPLA = (
    "id",
    "manifestacao_id",
    "gatilho",
    "destinatario_nome",
    "destinatario_email",
    "papel_destinatario",
    "status",
    "tentativas",
    "enviar_a_partir_de",
    "enviada_em",
    "ultimo_erro",
    "detalhe",
    "criada_em",
)
CAMPOS_NOTIFICACAO = ", ".join(CAMPOS_NOTIFICACAO_TUPLA)

# O que o email precisa saber do caso. Fechado campo a campo: coluna nova no
# Dossiê não vai parar num email do setor sem alguém decidir isso.
#
# `resumo` NÃO está aqui, de propósito. Ele guarda a palavra crua de quem
# manifestou (no canal aberto, os primeiros caracteres do que o cidadão
# digitou), e o responsável do setor é gente de fora da Ouvidoria. O que sai por
# email é `extrato_para_o_setor`, escrito pelo ouvidor na validação.
_CAMPOS_DO_EMAIL = (
    "id, protocolo, setor, categoria, extrato_para_o_setor, gravidade, prazo_area_em, "
    "sigilo_reforcado, anonimo, manifestante_nome"
)

# O que o setor lê quando, por algum caminho, o caso chegou ao email sem
# extrato. Melhor um email sem conteúdo do que um email com o relato cru.
_SEM_EXTRATO = "A Ouvidoria não registrou o extrato deste caso. Procure a Ouvidoria pelo protocolo antes de responder."

# Paleta da estratificação visual (RN-34). Os hex são os da spec da Diretoria,
# como default trocável: a paleta da casa ainda aguarda confirmação do DP, e
# quando ela vier a troca é aqui, num lugar só.
FAIXAS_GRAVIDADE = {
    "critico": {"cor": "#B3261E", "rotulo": "CRÍTICO"},
    "alto": {"cor": "#C77700", "rotulo": "ALTO"},
    "medio": {"cor": "#1F3864", "rotulo": "MÉDIO"},
    "baixo": {"cor": "#5F5E5A", "rotulo": "BAIXO"},
}


def faixa_da_gravidade(gravidade: str | None) -> dict | None:
    """Cor e rótulo da faixa do email. Gravidade fora do catálogo não inventa
    faixa: o email sai sem ela em vez de sair com cor errada."""
    return FAIXAS_GRAVIDADE.get(gravidade or "")


def quando_enviar(agora: dt.datetime, gravidade: str | None, feriados: frozenset[dt.date]) -> dt.datetime:
    """O instante em que a notificação pode sair.

    Crítico sai agora: é o caso que não espera o expediente abrir. O resto
    respeita a janela comercial, e o motor de prazos já sabe qual é o próximo
    instante de expediente."""
    if gravidade == "critico":
        return agora
    return inicio_da_contagem(agora, feriados)


def proxima_tentativa(agora: dt.datetime, tentativas: int) -> dt.datetime | None:
    """Quando tentar de novo depois de `tentativas` falhas. None quando o
    limite acabou e o caso vira alerta ao admin técnico."""
    if tentativas >= MAX_TENTATIVAS:
        return None
    return agora + dt.timedelta(minutes=BACKOFF_MINUTOS[min(tentativas - 1, len(BACKOFF_MINUTOS) - 1)])


def _formatar_vencimento(prazo_area_em: str | None) -> str:
    if not prazo_area_em:
        return "sem prazo definido"
    return dt.datetime.fromisoformat(str(prazo_area_em)).astimezone(FUSO).strftime("%d/%m/%Y às %Hh%M")


def _identificacao(manifestacao: dict) -> str | None:
    """Quem manifestou, quando o setor pode saber.

    Caso sigiloso e caso anônimo saem sem identificação: o setor recebe o
    extrato necessário para resolver, e nada além (ADR 0034, decisão 8)."""
    if manifestacao.get("sigilo_reforcado") or manifestacao.get("anonimo"):
        return None
    return manifestacao.get("manifestante_nome") or None


def _link_do_setor(manifestacao: dict) -> str:
    """O destino do email. O portal do setor com link tokenizado é a fatia
    seguinte do PRD; até lá o link abre a página de destino da Ouvidoria, que
    diz ao responsável como responder."""
    return f"{settings.frontend_url}/ouvidoria-setor?protocolo={manifestacao.get('protocolo', '')}"


def montar_nova_demanda(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> tuple[str, str, str]:
    """Assunto, HTML e texto do email de acionamento da área (NOVA_DEMANDA)."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    rotulo = rotular_vencimento(vencimento, agora, feriados)
    vencimento_formatado = _formatar_vencimento(bruto)
    protocolo = manifestacao.get("protocolo") or ""
    identificacao = _identificacao(manifestacao)
    extrato = (manifestacao.get("extrato_para_o_setor") or "").strip() or _SEM_EXTRATO

    html = jinja_env.get_template("email_ouvidoria_nova_demanda.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=manifestacao.get("setor") or "",
        categoria=manifestacao.get("categoria") or "",
        extrato=extrato,
        gravidade=manifestacao.get("gravidade") or "",
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=vencimento_formatado,
        rotulo_prazo=rotulo,
        identificacao=identificacao,
        sigiloso=bool(manifestacao.get("sigilo_reforcado")),
        link=_link_do_setor(manifestacao),
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A Ouvidoria acionou o setor {manifestacao.get('setor')} sobre a manifestacao {protocolo}.\n\n"
        f"O que aconteceu: {extrato}\n"
        f"Prazo de resposta: {vencimento_formatado} ({rotulo}).\n\n"
        f"Responda pela Ouvidoria: {_link_do_setor(manifestacao)}\n"
    )
    return (f"Ouvidoria {protocolo}: nova demanda para {manifestacao.get('setor')}", html, texto)


def montar_alerta_sem_titular(
    manifestacao: dict,
    destinatario_nome: str,
    gestor_nome: str,
) -> tuple[str, str, str]:
    """Assunto, HTML e texto do alerta à Diretoria quando o setor foi acionado
    sem titular vigente."""
    from app.services.email_constants import get_logo_data_uri

    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    html = jinja_env.get_template("email_ouvidoria_sem_titular.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        gestor_nome=gestor_nome,
        vencimento=_formatar_vencimento(manifestacao.get("prazo_area_em")),
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        rotulo_prazo=None,
        link=f"{settings.frontend_url}/ouvidoria",
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A manifestacao {protocolo} foi acionada no setor {setor}, que esta SEM TITULAR vigente.\n"
        f"A demanda subiu para {gestor_nome}, gestor da area.\n\n"
        f"Cadastre o titular do setor na Ouvidoria: {settings.frontend_url}/ouvidoria/responsaveis\n"
    )
    return (f"Ouvidoria {protocolo}: setor {setor} sem titular vigente", html, texto)


def registrar(
    supabase,
    *,
    manifestacao_id: str,
    gatilho: str,
    destinatario_nome: str,
    destinatario_email: str,
    papel_destinatario: str | None,
    enviar_a_partir_de: dt.datetime,
    detalhe: str | None = None,
) -> dict | None:
    """Grava a notificação antes de qualquer envio. Sem linha não há prova da
    cobrança nem botão de reenvio, então a linha vem primeiro."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .insert(
                {
                    "manifestacao_id": manifestacao_id,
                    "gatilho": gatilho,
                    "destinatario_nome": destinatario_nome,
                    "destinatario_email": destinatario_email,
                    "papel_destinatario": papel_destinatario,
                    "status": AGENDADA,
                    "detalhe": detalhe,
                    "tentativas": 0,
                    "enviar_a_partir_de": enviar_a_partir_de.isoformat(),
                }
            )
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        logger.error("Falha ao registrar notificação %s da manifestação %s", gatilho, manifestacao_id)
        return None


def _carregar_manifestacao(supabase, manifestacao_id: str) -> dict | None:
    result = (
        supabase.table("ouvidoria_protocolos").select(_CAMPOS_DO_EMAIL).eq("id", manifestacao_id).limit(1).execute()
    )
    return result.data[0] if result.data else None


def _montar(notificacao: dict, manifestacao: dict, agora: dt.datetime, feriados: frozenset[dt.date]):
    if notificacao["gatilho"] == GATILHO_ALERTA_SEM_TITULAR:
        return montar_alerta_sem_titular(
            manifestacao,
            notificacao["destinatario_nome"],
            notificacao.get("detalhe") or "o gestor da área",
        )
    return montar_nova_demanda(manifestacao, notificacao["destinatario_nome"], agora, feriados)


def _marcar(supabase, notificacao_id: str, mudanca: dict) -> bool:
    """Grava o desfecho da tentativa. Devolve se a gravação valeu: quem chama
    precisa saber, porque uma marcação perdida decide se o email sai de novo."""
    try:
        supabase.table("ouvidoria_notificacoes").update(mudanca).eq("id", notificacao_id).execute()
        return True
    except Exception:
        logger.error("Falha ao atualizar a notificação %s", notificacao_id)
        return False


def _reivindicar(supabase, notificacao_id: str) -> bool:
    """Toma a notificação para si antes de chamar o provedor.

    O update é condicional (`status = agendada`): quem chegar depois não acha
    linha para atualizar e desiste. Sem isso, o job de 10 em 10 minutos pode ler
    a mesma linha durante a chamada ao Resend e mandar a cobrança duas vezes ao
    responsável do setor."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .update({"status": ENVIANDO})
            .eq("id", notificacao_id)
            .eq("status", AGENDADA)
            .execute()
        )
    except Exception:
        logger.error("Falha ao reivindicar a notificação %s", notificacao_id)
        return False
    return bool(result.data)


def alertar_admin_tecnico(supabase, notificacao: dict) -> None:
    """Terceira falha seguida: o problema deixou de ser instabilidade e virou
    infraestrutura. Quem conserta é o admin técnico do app (super admin), e o
    alerta sai por fora da fila para não cair no mesmo buraco."""
    try:
        result = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("access_profile", "super_admin")
            .execute()
        )
        destinos = [p for p in (result.data or []) if (p.get("email") or "").strip()]
    except Exception:
        destinos = []

    assunto = f"Ouvidoria: falha no envio da notificação {notificacao.get('gatilho')}"
    texto = (
        "A notificacao abaixo falhou nas tres tentativas e nao foi entregue:\n\n"
        f"- Manifestacao: {notificacao.get('manifestacao_id')}\n"
        f"- Gatilho: {notificacao.get('gatilho')}\n"
        f"- Destinatario: {notificacao.get('destinatario_email')}\n"
        f"- Ultimo erro: {notificacao.get('ultimo_erro')}\n\n"
        "Reenvie pelo painel da Ouvidoria depois de resolver o provedor de email.\n"
    )
    if not destinos:
        logger.error("[Ouvidoria] %s | Sem super admin com email para alertar", texto)
        return

    # O alerta sai pelo mesmo canal que acabou de falhar três vezes, então ele
    # pode não chegar. Por isso o log vem sempre: é o rastro que sobra quando o
    # provedor de email está fora do ar, que é justamente o caso comum aqui.
    entregues = 0
    for admin in destinos:
        try:
            if _enviar_email(admin["email"], assunto, f"<pre>{texto}</pre>", texto):
                entregues += 1
        except Exception:  # noqa: BLE001
            logger.exception("[Ouvidoria] Falha ao alertar o admin técnico %s", admin.get("id"))
    if entregues:
        logger.error("[Ouvidoria] %s", texto)
    else:
        logger.error("[Ouvidoria] %s | O alerta ao admin técnico também não saiu", texto)


def despachar(supabase, notificacao: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> bool:
    """Tenta entregar uma notificação agendada. Devolve se saiu.

    Falha não perde a notificação: ela volta para a fila com espera crescente,
    até o limite de tentativas."""
    if not _reivindicar(supabase, notificacao["id"]):
        # Outro caminho já pegou esta linha (ou ela não está mais agendada).
        # Insistir aqui é o reenvio duplicado que o claim existe para evitar.
        return False

    manifestacao = _carregar_manifestacao(supabase, notificacao["manifestacao_id"])
    if manifestacao is None:
        _marcar(supabase, notificacao["id"], {"status": FALHA, "ultimo_erro": "Manifestação não encontrada"})
        return False

    try:
        assunto, html, texto = _montar(notificacao, manifestacao, agora, feriados)
        entregue = _enviar_email(notificacao["destinatario_email"], assunto, html, texto)
        erro = None if entregue else "O provedor de email recusou a mensagem"
    except Exception as exc:  # noqa: BLE001
        entregue = False
        erro = str(exc)[:300]

    if entregue:
        marcada = _marcar(
            supabase,
            notificacao["id"],
            {"status": ENVIADA, "enviada_em": agora.isoformat(), "tentativas": notificacao.get("tentativas", 0) + 1},
        )
        if not marcada:
            # O email saiu e a linha ficou em `enviando`. É de propósito que ela
            # não volte para `agendada`: o job a pegaria de novo e o setor
            # receberia a mesma cobrança. Fica visível no caso, com o botão de
            # reenvio, para a Ouvidoria decidir.
            logger.error(
                "[Ouvidoria] A notificação %s foi entregue mas ficou em %s: o registro não confirma o envio",
                notificacao["id"],
                ENVIANDO,
            )
        return True

    tentativas = notificacao.get("tentativas", 0) + 1
    proxima = proxima_tentativa(agora, tentativas)
    # A linha está reivindicada: devolver para a fila é explícito, e só acontece
    # enquanto há tentativa sobrando.
    mudanca = {"tentativas": tentativas, "ultimo_erro": erro, "status": FALHA if proxima is None else AGENDADA}
    if proxima is not None:
        mudanca["enviar_a_partir_de"] = proxima.isoformat()
    if not _marcar(supabase, notificacao["id"], mudanca):
        logger.error(
            "[Ouvidoria] A notificação %s falhou no envio e ficou em %s: reenvio manual pela Ouvidoria",
            notificacao["id"],
            ENVIANDO,
        )
    if proxima is None:
        alertar_admin_tecnico(supabase, {**notificacao, **mudanca})
    return False


def despachar_agora_se_puder(supabase, notificacao: dict | None, agora: dt.datetime, feriados) -> bool:
    """Entrega já, quando a janela permite. Fora dela a notificação fica na
    fila e o job periódico a leva no primeiro instante de expediente."""
    if not notificacao:
        return False
    quando = notificacao.get("enviar_a_partir_de")
    if quando and dt.datetime.fromisoformat(str(quando)) > agora:
        return False
    return despachar(supabase, notificacao, agora, feriados)


def despachar_pendentes(supabase, agora: dt.datetime, feriados: frozenset[dt.date]) -> int:
    """Varre a fila e entrega o que já pode sair. Idempotente: o que saiu está
    marcado como enviada e não é lido de novo."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .select(CAMPOS_NOTIFICACAO)
            .eq("status", AGENDADA)
            .lte("enviar_a_partir_de", agora.isoformat())
            .order("enviar_a_partir_de")
            .execute()
        )
    except Exception:
        logger.error("[Ouvidoria] Falha ao ler a fila de notificações")
        return 0

    return sum(1 for linha in (result.data or []) if despachar(supabase, linha, agora, feriados))
