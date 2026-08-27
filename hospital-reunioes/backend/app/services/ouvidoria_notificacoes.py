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

O catálogo de gatilhos vive aqui inteiro: o acionamento da área e seus alertas
(issue #325), o degrau do vencimento (#327) e a escada de escalonamento com o
aviso de caso crítico (#336). Quem decide QUANDO cada um nasce são os módulos
de cobrança e escalonamento; este aqui sabe montar, guardar e entregar.
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
# O degrau do vencimento (issue #327): prazo da área estourou e a cobrança sai
# ao titular e ao substituto. Os demais degraus da escada são do PRD #318.
GATILHO_PRAZO_ROMPIDO = "prazo_rompido"
# Os degraus restantes da escada de escalonamento (issue #336, PRD #318).
GATILHO_VESPERA_VENCIMENTO = "vespera_vencimento"
GATILHO_ESCALONAMENTO_GESTOR = "escalonamento_gestor"
GATILHO_ESCALONAMENTO_DIRETORIA = "escalonamento_diretoria"
# O degrau de +24h úteis de um setor SEM gestor cadastrado, que vira alerta à
# Diretoria. Gatilho separado do degrau real de 48h de propósito (issue #373,
# defeito 3): os dois iam à Diretoria pelo mesmo gatilho, e a guarda de
# retenção descartava os dois quando a área respondia a tempo. Descartar o
# degrau está certo (não há mais o que cobrar); descartar este está errado, e o
# buraco de cadastro ficava invisível caso após caso.
GATILHO_ALERTA_CADASTRO_SETOR = "alerta_cadastro_setor"
# Fora da escada de prazo: caso crítico validado avisa a Diretoria na hora,
# sem esperar vencimento nenhum.
GATILHO_CRITICO_IMEDIATO = "critico_imediato"
# Prorrogação de prazo (issue #333): o pedido avisa a Ouvidoria, a decisão
# volta ao responsável do setor.
GATILHO_PRORROGACAO_SOLICITADA = "prorrogacao_solicitada"
GATILHO_PRORROGACAO_DECIDIDA = "prorrogacao_decidida"
# Devolução por insuficiência (issue #334): o ouvidor recusou a resposta e o
# caso voltou à área com meio prazo. O motivo viaja em `detalhe`.
GATILHO_RESPOSTA_DEVOLVIDA = "resposta_devolvida"
# Reabertura por reincidência (issue #335): o manifestante voltou dentro de 30
# dias e o caso original saiu do encerramento de volta para a área. O motivo
# escrito pelo ouvidor viaja em `detalhe`.
GATILHO_CASO_REABERTO = "caso_reaberto"
GATILHOS = (
    GATILHO_NOVA_DEMANDA,
    GATILHO_ALERTA_SEM_TITULAR,
    GATILHO_PRAZO_ROMPIDO,
    GATILHO_VESPERA_VENCIMENTO,
    GATILHO_ESCALONAMENTO_GESTOR,
    GATILHO_ESCALONAMENTO_DIRETORIA,
    GATILHO_ALERTA_CADASTRO_SETOR,
    GATILHO_CRITICO_IMEDIATO,
    GATILHO_PRORROGACAO_SOLICITADA,
    GATILHO_PRORROGACAO_DECIDIDA,
    GATILHO_RESPOSTA_DEVOLVIDA,
    GATILHO_CASO_REABERTO,
)

# Quem leva link tokenizado do portal do setor (issue #326): os emails que vão
# ao responsável do setor, que responde sem login. Os que vão à Ouvidoria ou à
# Diretoria ficam de fora porque quem os recebe tem acesso ao painel.
GATILHOS_COM_PORTAL = (
    GATILHO_NOVA_DEMANDA,
    GATILHO_PRAZO_ROMPIDO,
    GATILHO_VESPERA_VENCIMENTO,
    GATILHO_ESCALONAMENTO_GESTOR,
    GATILHO_PRORROGACAO_DECIDIDA,
    # A devolução pede resposta nova, e o link do acionamento já foi consumido
    # pela resposta que voltou: sem token novo a área não tem por onde responder.
    GATILHO_RESPOSTA_DEVOLVIDA,
    # A reabertura pede resposta de um caso que já tinha fechado: qualquer link
    # antigo daquele caso já foi consumido ou perdeu a validade (issue #335).
    GATILHO_CASO_REABERTO,
)

# Os gatilhos que só fazem sentido enquanto a área não respondeu. Uma cobrança
# retida pela janela comercial durante a noite não pode acusar de manhã quem
# respondeu de madrugada. O aviso de caso crítico fica de fora: a Diretoria
# precisa saber do grave mesmo que a área já tenha respondido. A decisão da
# prorrogação também: quem pediu prazo tem direito de saber a resposta, mesmo
# que o caso já tenha andado (issue #333).
GATILHOS_QUE_COBRAM_A_AREA = (
    GATILHO_PRAZO_ROMPIDO,
    GATILHO_VESPERA_VENCIMENTO,
    GATILHO_ESCALONAMENTO_GESTOR,
    GATILHO_ESCALONAMENTO_DIRETORIA,
    # A devolução também pede resposta: se o caso saiu de aguardando a área
    # entre a fila e a entrega (encerrado pelo ouvidor, por exemplo), mandar a
    # devolução seria pedir trabalho de um caso que já fechou (issue #334).
    GATILHO_RESPOSTA_DEVOLVIDA,
    # Pelo mesmo motivo: caso reaberto que fecha de novo antes de o email sair
    # não deve cobrar resposta de ninguém (issue #335).
    GATILHO_CASO_REABERTO,
)

# Gatilhos cujo email precisa do pedido de prorrogação do caso, não só do
# caso: justificativa, dias pedidos e prazo proposto vivem na entidade própria.
GATILHOS_DA_PRORROGACAO = (GATILHO_PRORROGACAO_SOLICITADA, GATILHO_PRORROGACAO_DECIDIDA)

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
    "sigilo_reforcado, anonimo, manifestante_nome, status"
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


# Tons do quadro de aviso dos degraus da escada (issue #336). A faixa de cor do
# cabeçalho continua sendo a da GRAVIDADE (RN-34); estes dois tons dizem outra
# coisa, o quanto a cobrança já subiu. Âmbar é o lembrete antes de vencer;
# vermelho é o caso que já estourou e não foi respondido.
AVISO_ATENCAO = {"fundo": "#fffbeb", "borda": "#fde68a", "texto": "#92400e"}
AVISO_URGENTE = {"fundo": "#fef2f2", "borda": "#fecaca", "texto": "#991b1b"}


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
    """Fallback sem token: a página de destino que diz ao responsável como
    responder. O caminho normal do acionamento passa o link tokenizado do
    portal (issue #326), emitido na hora do despacho."""
    return f"{settings.frontend_url}/ouvidoria-setor?protocolo={manifestacao.get('protocolo', '')}"


def montar_nova_demanda(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
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
    destino = link or _link_do_setor(manifestacao)

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
        link=destino,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A Ouvidoria acionou o setor {manifestacao.get('setor')} sobre a manifestacao {protocolo}.\n\n"
        f"O que aconteceu: {extrato}\n"
        f"Prazo de resposta: {vencimento_formatado} ({rotulo}).\n\n"
        f"Responda pela Ouvidoria: {destino}\n"
    )
    return (f"Ouvidoria {protocolo}: nova demanda para {manifestacao.get('setor')}", html, texto)


def montar_alerta_sem_titular(
    manifestacao: dict,
    destinatario_nome: str,
    gestor_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> tuple[str, str, str]:
    """Assunto, HTML e texto do alerta à Diretoria quando o setor foi acionado
    sem titular vigente."""
    from app.services.email_constants import get_logo_data_uri

    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    html = jinja_env.get_template("email_ouvidoria_sem_titular.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        gestor_nome=gestor_nome,
        vencimento=_formatar_vencimento(bruto),
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        rotulo_prazo=rotular_vencimento(vencimento, agora, feriados) if vencimento else None,
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


def montar_prazo_rompido(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
) -> tuple[str, str, str]:
    """Assunto, HTML e texto da cobrança de prazo rompido (issue #327).

    A faixa de contexto (protocolo, setor e desde quando venceu) vem do mesmo
    cabeçalho estratificado dos demais emails do caso (RN-34/RN-35), com o
    rótulo saindo do motor de prazos que o painel usa. O botão leva ao portal
    do setor pelo mesmo link tokenizado do acionamento (issue #326): quem é
    cobrado precisa responder ali mesmo, sem login."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    rotulo = rotular_vencimento(vencimento, agora, feriados)
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    extrato = (manifestacao.get("extrato_para_o_setor") or "").strip() or _SEM_EXTRATO
    destino = link or _link_do_setor(manifestacao)

    html = jinja_env.get_template("email_ouvidoria_prazo_rompido.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        categoria=manifestacao.get("categoria") or "",
        extrato=extrato,
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=_formatar_vencimento(bruto),
        rotulo_prazo=rotulo,
        sigiloso=bool(manifestacao.get("sigilo_reforcado")),
        link=destino,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"O prazo de resposta da manifestacao {protocolo} venceu e o setor {setor} ainda nao respondeu.\n"
        f"Prazo: {_formatar_vencimento(bruto)} ({rotulo}).\n\n"
        f"O que aconteceu: {extrato}\n\n"
        f"Responda pela Ouvidoria: {destino}\n"
    )
    return (f"Ouvidoria {protocolo}: prazo rompido no setor {setor}", html, texto)


def _montar_do_caso(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    *,
    assunto: str,
    abertura: str,
    link: str,
    rotulo_botao: str,
    aviso: dict,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """Assunto, HTML e texto de um email do caso no cabeçalho estratificado.

    Os degraus da escada (issue #336) dizem coisas diferentes sobre o mesmo
    caso, e todos precisam da mesma faixa de gravidade, do mesmo protocolo e da
    mesma contagem regressiva (RN-34/RN-35). O que varia é o parágrafo de
    abertura, o contexto extra (`detalhe`), o tom do quadro de aviso e o rótulo
    do botão.

    O `assunto` vai junto para o template porque o `<title>` da mensagem sai
    dele: assunto e título não podem contar histórias diferentes."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    rotulo = rotular_vencimento(vencimento, agora, feriados)
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    extrato = (manifestacao.get("extrato_para_o_setor") or "").strip() or _SEM_EXTRATO
    vencimento_formatado = _formatar_vencimento(bruto)

    html = jinja_env.get_template("email_ouvidoria_degrau.html").render(
        assunto=assunto,
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        extrato=extrato,
        gravidade=manifestacao.get("gravidade") or "",
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=vencimento_formatado,
        rotulo_prazo=rotulo,
        abertura=abertura,
        detalhe=detalhe,
        aviso=aviso,
        rotulo_botao=rotulo_botao,
        sigiloso=bool(manifestacao.get("sigilo_reforcado")),
        link=link,
        logo_base64=get_logo_data_uri(),
    )
    linhas = [
        f"Ola {destinatario_nome},",
        "",
        abertura,
    ]
    if detalhe:
        linhas.append(detalhe)
    linhas += [
        "",
        f"Protocolo: {protocolo} | Setor: {setor}",
        f"Prazo: {vencimento_formatado} ({rotulo})",
        "",
        f"O que aconteceu: {extrato}",
        "",
        f"{rotulo_botao}: {link}",
        "",
    ]
    return (assunto, html, "\n".join(linhas))


def montar_vespera_vencimento(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """Degrau 1 da escada: a véspera do vencimento lembra o titular do setor.

    O assunto NÃO promete "vence amanhã". Na configuração real de produção o
    prazo em dias úteis vence às 17h, a véspera cai às 17h do dia útil anterior
    e a janela comercial segura o email até as 08h seguintes, que é o próprio
    dia do vencimento. Quem diz quanto tempo sobra é a contagem regressiva do
    motor, no corpo, que está sempre certa."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: o prazo do setor {setor} está perto do fim",
        abertura=(
            f"O prazo de resposta desta manifestacao esta perto do fim e o setor {setor} "
            "ainda nao respondeu a Ouvidoria. Responder agora evita o estouro."
        ),
        link=link or _link_do_setor(manifestacao),
        rotulo_botao="Responder pela Ouvidoria",
        aviso=AVISO_ATENCAO,
        detalhe=detalhe,
    )


def montar_resposta_devolvida(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """A devolução por insuficiência, de volta ao responsável do setor (issue
    #334).

    O motivo escrito pelo ouvidor chega em `detalhe` e é o conteúdo principal:
    sem ele a área recebe uma recusa sem saber o que refazer. O prazo do
    cabeçalho já é o meio prazo novo, porque o caso foi carimbado antes de o
    email sair."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    motivo = (detalhe or "").strip()
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: a resposta do setor {setor} foi devolvida",
        abertura=(
            "A Ouvidoria leu a resposta enviada e a considerou insuficiente. A manifestacao "
            "voltou para o setor com prazo reduzido, e a contagem ja esta correndo."
        ),
        link=link or _link_do_setor(manifestacao),
        rotulo_botao="Responder pela Ouvidoria",
        aviso=AVISO_ATENCAO,
        detalhe=f"Motivo da devolucao: {motivo}" if motivo else None,
    )


def montar_caso_reaberto(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """A reabertura por reincidência, de volta ao responsável do setor (issue
    #335).

    O que a área precisa entender é que o problema voltou: o caso não é novo,
    já foi tratado antes e o manifestante reclamou de novo dentro de trinta
    dias. O motivo escrito pelo ouvidor chega em `detalhe`, e o prazo do
    cabeçalho já é o prazo inteiro novo, carimbado antes de o email sair."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    motivo = (detalhe or "").strip()
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: o caso do setor {setor} foi reaberto",
        abertura=(
            "O manifestante voltou a procurar a Ouvidoria sobre este mesmo caso, que ja tinha sido "
            "encerrado. A manifestacao foi reaberta e o setor tem prazo novo para responder."
        ),
        link=link or _link_do_setor(manifestacao),
        rotulo_botao="Responder pela Ouvidoria",
        aviso=AVISO_ATENCAO,
        detalhe=f"Motivo da reabertura: {motivo}" if motivo else None,
    )


def montar_escalonamento_gestor(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """Degrau 3 da escada: 24h úteis depois do vencimento, o gestor da área."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: o setor {setor} segue sem responder",
        abertura=(
            f"O prazo de resposta desta manifestacao venceu e o setor {setor} nao respondeu "
            "a cobranca da Ouvidoria. O caso subiu para a gestao da area."
        ),
        link=link or _link_do_setor(manifestacao),
        rotulo_botao="Abrir a demanda da Ouvidoria",
        aviso=AVISO_URGENTE,
        detalhe=detalhe,
    )


def montar_escalonamento_diretoria(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """Degrau 4 da escada: 48h úteis depois do vencimento, a Diretoria
    Executiva. Cobra o silêncio da área, e por isso o texto fala dele."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: caso sem resposta escalado para a Diretoria",
        abertura=(
            f"O prazo de resposta desta manifestacao venceu e o setor {setor} nao respondeu "
            "as cobrancas da Ouvidoria. O caso chegou a Diretoria Executiva."
        ),
        link=link or f"{settings.frontend_url}/ouvidoria",
        rotulo_botao="Abrir a Ouvidoria",
        aviso=AVISO_URGENTE,
        detalhe=detalhe,
    )


def montar_alerta_cadastro_setor(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """O degrau de +24h úteis de um setor SEM gestor cadastrado.

    Texto próprio, e não o do degrau de 48h (issue #373): este alerta atravessa
    a guarda de retenção justamente para chegar quando a área RESPONDEU a
    tempo, e o texto do degrau acusaria de silêncio quem respondeu. O que ele
    denuncia é o buraco de cadastro, que continua lá em qualquer dos casos.

    O assunto também é próprio: os dois emails caem na Diretoria com um dia
    útil de intervalo, e assunto idêntico os deixaria indistinguíveis."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: setor {setor} sem gestor cadastrado",
        abertura=(
            f"O setor {setor} nao tem gestor cadastrado na Ouvidoria. A cobranca de 24 horas "
            "uteis deste caso, que deveria ter ido ao gestor, veio para a Diretoria Executiva. "
            "O aviso vale mesmo que o setor ja tenha respondido: o cadastro continua incompleto "
            "e o proximo caso deste setor vai repetir o desvio."
        ),
        link=link or f"{settings.frontend_url}/ouvidoria",
        rotulo_botao="Abrir a Ouvidoria",
        aviso=AVISO_URGENTE,
        detalhe=detalhe,
    )


def montar_critico_imediato(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
    detalhe: str | None = None,
) -> tuple[str, str, str]:
    """Caso crítico validado: a Diretoria Executiva sabe na hora, sem esperar
    prazo nenhum (PRD #318, história 18)."""
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    return _montar_do_caso(
        manifestacao,
        destinatario_nome,
        agora,
        feriados,
        assunto=f"Ouvidoria {protocolo}: caso CRITICO validado no setor {setor}",
        abertura=(
            "A Ouvidoria acabou de validar esta manifestacao como CRITICA. "
            f"O setor {setor} foi acionado e a Diretoria Executiva esta sendo avisada na hora, "
            "sem esperar o prazo de resposta."
        ),
        link=link or f"{settings.frontend_url}/ouvidoria",
        rotulo_botao="Abrir a Ouvidoria",
        aviso=AVISO_URGENTE,
        detalhe=detalhe,
    )


def ler_diretoria_executiva(supabase) -> list[dict] | None:
    """Quem é a Diretoria Executiva ATIVA hoje, com email, distinguindo o silêncio.

    None significa que a LEITURA falhou. Lista vazia significa que ninguém tem
    o perfil. A diferença importa para quem decide tirar um caso da fila por
    falta de destinatário (issue #373): um timeout não pode virar caso
    carimbado sem cobrança.

    O filtro por `ativo` existe porque o desligamento do hospital é soft delete
    e NÃO limpa `perfil_ouvidoria` (`participantes.py`, DELETE só faz
    `ativo: False`). Sem ele, quem saiu continuaria recebendo, caso a caso e
    para sempre, o escalonamento à Diretoria, o aviso de caso crítico e o
    alerta de setor sem titular, todos com o número do protocolo na linha de
    assunto, numa caixa de email que já não é do hospital, e a pessoa nem
    aparece mais na tela de Usuários para alguém notar (issue #403)."""
    try:
        result = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("perfil_ouvidoria", "diretoria_executiva")
            .eq("ativo", True)
            .execute()
        )
    except Exception:
        logger.warning("[Ouvidoria] Falha ao buscar a Diretoria Executiva")
        return None
    return [d for d in (result.data or []) if (d.get("email") or "").strip()]


def carregar_diretoria_executiva(supabase) -> list[dict]:
    """Quem é a Diretoria Executiva hoje, com email.

    Lista vazia significa que ninguém tem o perfil (ou que a leitura falhou):
    quem chama decide o que fazer com o silêncio, porque um alerta perdido não
    pode virar caso carimbado sem cobrança. Quem precisa separar os dois usa
    `ler_diretoria_executiva`."""
    return ler_diretoria_executiva(supabase) or []


def _dias_por_extenso(dias: int) -> str:
    return f"{dias} dia útil" if dias == 1 else f"{dias} dias úteis"


def montar_prorrogacao_solicitada(
    manifestacao: dict,
    destinatario_nome: str,
    pedido: dict,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
) -> tuple[str, str, str]:
    """Assunto, HTML e texto do aviso à Ouvidoria de que a área pediu mais
    prazo (issue #333). Quem recebe tem painel, então o botão leva ao painel e
    não a um link tokenizado."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    dias = _dias_por_extenso(int(pedido.get("dias_uteis_pedidos") or 0))
    prazo_proposto = _formatar_vencimento(pedido.get("prazo_novo"))
    justificativa = (pedido.get("justificativa") or "").strip()

    html = jinja_env.get_template("email_ouvidoria_prorrogacao_solicitada.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=_formatar_vencimento(bruto),
        rotulo_prazo=rotular_vencimento(vencimento, agora, feriados),
        solicitante_nome=pedido.get("solicitante_nome") or "o responsável do setor",
        dias_pedidos=dias,
        prazo_proposto=prazo_proposto,
        justificativa=justificativa,
        link=f"{settings.frontend_url}/ouvidoria",
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"O setor {setor} pediu prorrogacao de prazo na manifestacao {protocolo}.\n"
        f"Pedido: {dias}. Prazo proposto: {prazo_proposto}.\n\n"
        f"Justificativa da area: {justificativa}\n\n"
        f"Decida no painel da Ouvidoria: {settings.frontend_url}/ouvidoria\n"
    )
    return (f"Ouvidoria {protocolo}: o setor {setor} pediu prorrogacao de prazo", html, texto)


def montar_prorrogacao_decidida(
    manifestacao: dict,
    destinatario_nome: str,
    pedido: dict,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
) -> tuple[str, str, str]:
    """Assunto, HTML e texto da decisão da Ouvidoria sobre a prorrogação, de
    volta ao responsável do setor (issue #333).

    O prazo do cabeçalho é o VIGENTE do caso: aprovada, ele já é o prazo novo;
    negada, ele continua sendo o de antes. Quem lê precisa saber até quando
    responder, não qual número estava na tela ontem."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    aprovada = pedido.get("status") == "aprovada"
    decisao = "aprovada" if aprovada else "negada"
    motivo = (pedido.get("decisao_justificativa") or "").strip()
    destino = link or _link_do_setor(manifestacao)

    html = jinja_env.get_template("email_ouvidoria_prorrogacao_decidida.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=_formatar_vencimento(bruto),
        rotulo_prazo=rotular_vencimento(vencimento, agora, feriados),
        aprovada=aprovada,
        decidida_por_nome=pedido.get("decidida_por_nome") or "a Ouvidoria",
        motivo=motivo,
        link=destino,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A Ouvidoria {decisao} o pedido de prorrogacao da manifestacao {protocolo}.\n"
        f"Prazo de resposta: {_formatar_vencimento(bruto)} ({rotular_vencimento(vencimento, agora, feriados)}).\n"
        + (f"\nMotivo da Ouvidoria: {motivo}\n" if motivo else "")
        + f"\nResponda pela Ouvidoria: {destino}\n"
    )
    return (f"Ouvidoria {protocolo}: prorrogacao {decisao}", html, texto)


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


_MONTADORES_DA_ESCADA = {
    GATILHO_RESPOSTA_DEVOLVIDA: montar_resposta_devolvida,
    GATILHO_CASO_REABERTO: montar_caso_reaberto,
    GATILHO_VESPERA_VENCIMENTO: montar_vespera_vencimento,
    GATILHO_ESCALONAMENTO_GESTOR: montar_escalonamento_gestor,
    GATILHO_ESCALONAMENTO_DIRETORIA: montar_escalonamento_diretoria,
    GATILHO_ALERTA_CADASTRO_SETOR: montar_alerta_cadastro_setor,
    GATILHO_CRITICO_IMEDIATO: montar_critico_imediato,
}


def _montar(
    supabase,
    notificacao: dict,
    manifestacao: dict,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
):
    if notificacao["gatilho"] in GATILHOS_DA_PRORROGACAO:
        # O conteúdo vem da entidade própria, não do `detalhe`: assim o
        # reenvio manda a mesma coisa, sem duplicar o pedido dentro da
        # notificação.
        from app.services.ouvidoria_prorrogacao import carregar_pedido

        pedido = carregar_pedido(supabase, notificacao["manifestacao_id"])
        if pedido is None:
            raise ValueError("Notificação de prorrogação sem pedido no caso")
        if notificacao["gatilho"] == GATILHO_PRORROGACAO_SOLICITADA:
            return montar_prorrogacao_solicitada(
                manifestacao, notificacao["destinatario_nome"], pedido, agora, feriados
            )
        return montar_prorrogacao_decidida(
            manifestacao, notificacao["destinatario_nome"], pedido, agora, feriados, link=link
        )
    if notificacao["gatilho"] == GATILHO_ALERTA_SEM_TITULAR:
        return montar_alerta_sem_titular(
            manifestacao,
            notificacao["destinatario_nome"],
            notificacao.get("detalhe") or "o gestor da área",
            agora,
            feriados,
        )
    if notificacao["gatilho"] == GATILHO_PRAZO_ROMPIDO:
        return montar_prazo_rompido(manifestacao, notificacao["destinatario_nome"], agora, feriados, link=link)
    if notificacao["gatilho"] == GATILHO_NOVA_DEMANDA:
        return montar_nova_demanda(manifestacao, notificacao["destinatario_nome"], agora, feriados, link=link)
    montador = _MONTADORES_DA_ESCADA.get(notificacao["gatilho"])
    if montador is not None:
        return montador(
            manifestacao,
            notificacao["destinatario_nome"],
            agora,
            feriados,
            link=link,
            detalhe=notificacao.get("detalhe"),
        )
    # Gatilho novo sem montador é erro de programação, não email de "nova
    # demanda" na caixa de quem não devia recebê-lo. O despachar marca a falha.
    raise ValueError(f"Gatilho sem montador de email: {notificacao['gatilho']}")


def _link_tokenizado(supabase, notificacao: dict) -> str:
    """O link do portal do setor (issue #326): token restrito à manifestação e
    ao destinatário, emitido na hora do despacho. Reenvio emite token novo e o
    link antigo não usado morre junto."""
    from app.services import ouvidoria_setor_tokens

    token = ouvidoria_setor_tokens.emitir(
        supabase,
        manifestacao_id=notificacao["manifestacao_id"],
        destinatario_nome=notificacao["destinatario_nome"],
        destinatario_email=notificacao["destinatario_email"],
    )
    return f"{settings.frontend_url}/ouvidoria-setor/{token}"


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


def avisar_admins_tecnicos(supabase, assunto: str, texto: str) -> int:
    """Manda um aviso operacional aos super admins do app, por fora da fila.

    Fora da fila de propósito: os dois motivos que chegam aqui (provedor de
    email caído, cadastro de setor incompleto) são justamente os que a fila não
    resolve sozinha. Devolve quantos receberam.

    O log vem sempre, entregue ou não: quando o canal de email é o problema, o
    log é o único rastro que sobra."""
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

    if not destinos:
        logger.error("[Ouvidoria] %s | Sem super admin com email para alertar", texto)
        return 0

    entregues = 0
    for admin in destinos:
        try:
            if _enviar_email(admin["email"], assunto, f"<pre>{texto}</pre>", texto):
                entregues += 1
        except Exception:  # noqa: BLE001
            logger.exception("[Ouvidoria] Falha ao alertar o admin técnico %s", admin.get("id"))
    if entregues:
        # Entregue: o email é o sinal, e o log fica em INFO. Gritar ERROR no
        # caminho saudável seria o ruído que a issue #373 veio tirar do log.
        logger.info("[Ouvidoria] Aviso ao admin técnico entregue a %d destinatário(s)", entregues)
    else:
        # Não entregue: aqui o log é o único rastro que sobra, e o caso comum é
        # justamente o provedor de email fora do ar.
        logger.error("[Ouvidoria] %s | O alerta ao admin técnico não saiu", texto)
    return entregues


def alertar_admin_tecnico(supabase, notificacao: dict) -> None:
    """Terceira falha seguida: o problema deixou de ser instabilidade e virou
    infraestrutura. Quem conserta é o admin técnico do app (super admin), e o
    alerta sai por fora da fila para não cair no mesmo buraco."""
    avisar_admins_tecnicos(
        supabase,
        f"Ouvidoria: falha no envio da notificação {notificacao.get('gatilho')}",
        (
            "A notificacao abaixo falhou nas tres tentativas e nao foi entregue:\n\n"
            f"- Manifestacao: {notificacao.get('manifestacao_id')}\n"
            f"- Gatilho: {notificacao.get('gatilho')}\n"
            f"- Destinatario: {notificacao.get('destinatario_email')}\n"
            f"- Ultimo erro: {notificacao.get('ultimo_erro')}\n\n"
            "Reenvie pelo painel da Ouvidoria depois de resolver o provedor de email.\n"
        ),
    )


def despachar(supabase, notificacao: dict, agora: dt.datetime, feriados: frozenset[dt.date]) -> bool:
    """Tenta entregar uma notificação agendada. Devolve se saiu.

    Falha não perde a notificação: ela volta para a fila com espera crescente,
    até o limite de tentativas."""
    if not _reivindicar(supabase, notificacao["id"]):
        # Outro caminho já pegou esta linha (ou ela não está mais agendada).
        # Insistir aqui é o reenvio duplicado que o claim existe para evitar.
        return False

    try:
        # A leitura fica dentro do try: uma falha aqui devolve a notificação à
        # fila com backoff, em vez de prendê-la em `enviando` e derrubar o
        # resto do lote do job.
        manifestacao = _carregar_manifestacao(supabase, notificacao["manifestacao_id"])
        if manifestacao is None:
            _marcar(supabase, notificacao["id"], {"status": FALHA, "ultimo_erro": "Manifestação não encontrada"})
            return False
        if notificacao["gatilho"] in GATILHOS_QUE_COBRAM_A_AREA and manifestacao.get("status") != "aguardando_area":
            # A área respondeu entre a fila e a entrega (ex.: cobrança retida
            # pela janela comercial durante a madrugada). Cobrar agora seria
            # acusar quem já respondeu.
            _marcar(
                supabase,
                notificacao["id"],
                {"status": FALHA, "ultimo_erro": "A área respondeu antes do envio; cobrança não enviada"},
            )
            return False
        link = _link_tokenizado(supabase, notificacao) if notificacao["gatilho"] in GATILHOS_COM_PORTAL else None
        assunto, html, texto = _montar(supabase, notificacao, manifestacao, agora, feriados, link=link)
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
