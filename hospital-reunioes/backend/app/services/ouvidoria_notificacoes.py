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
from app.services.ouvidoria_blocos import (
    SEM_EXTRATO,
    aviso_do_caso,
    identificacao_do_caso,
    montar_blocos,
)
from app.services.ouvidoria_prazos import (
    formatar_vencimento,
    inicio_da_contagem,
    rotular_vencimento,
)
from app.utils.text_sanitizer import sanitizar_travessao

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
# O primeiro gatilho da casa cujo destinatário é o MANIFESTANTE, e não o setor,
# o gestor ou a Diretoria (issue #493, ADR 0042): o aviso de que a manifestação
# chegou, com o número do protocolo. Sai na abertura do caso, por qualquer
# canal, e o corpo dele é mínimo de propósito (protocolo e o que acontece
# agora), sem relato e sem identificação de terceiros.
GATILHO_ACUSAR_RECEBIMENTO = "acusar_recebimento"
# A outra ponta do ADR 0042 (issue #494, decisão 3): encerrar o caso no sistema
# passa a encerrar também para quem manifestou. Dispara na transição de
# encerramento e leva o protocolo, o desfecho em linguagem simples que o ouvidor
# escreveu para a pessoa e o canal para voltar. O texto do desfecho viaja no
# `detalhe` da linha, congelado no ato: a coluna do caso é sobrescrita pela
# reabertura por reincidência, e o reenvio meses depois mandaria o desfecho da
# tramitação seguinte, ou nada.
GATILHO_ENCERRAMENTO_MANIFESTANTE = "encerramento_manifestante"
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
    GATILHO_ACUSAR_RECEBIMENTO,
    GATILHO_ENCERRAMENTO_MANIFESTANTE,
)

# O que vai na coluna `destinatario_nome` (NOT NULL) quando quem manifestou não
# deixou nome, só um email. Fica na LINHA, que vive atrás do gate do Dossiê, e
# não no corpo do email: o acuse não tem saudação com nome (ver
# `montar_acuse_recebimento`). A fila da Ouvidoria continua legível em vez de
# mostrar uma linha em branco.
MANIFESTANTE_SEM_NOME = "Manifestante"

# Os gatilhos cujo destinatário é gente de FORA do hospital. Duas consequências,
# e as duas são de segurança: o endereço não entra no log da aplicação (o log
# corre em INFO e o assunto carrega o protocolo, então o par identificaria quem
# abriu cada caso) e o corpo do email não leva texto vindo de fora.
#
# A lista é escrita à MÃO, e é isso que a torna perigosa: gatilho novo para o
# manifestante nasce fora dela, ou seja, nasce vazando. Quem acrescentar o
# terceiro (o transporte por WhatsApp do ADR 0042, quando existir) acrescenta
# aqui no mesmo commit, e o teste de log do arquivo do gatilho é o que trava.
GATILHOS_DO_MANIFESTANTE = (GATILHO_ACUSAR_RECEBIMENTO, GATILHO_ENCERRAMENTO_MANIFESTANTE)

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
# `resumo` e `relato_integral` entraram por decisão explícita da Diretoria
# (RN-78, ADR 0041), pelo mecanismo que esta lista existe para exigir: quem lê
# só a interpretação da Ouvidoria responde à interpretação, não ao paciente. O
# caso com sigilo reforçado é a exceção, e quem a aplica é `ouvidoria_blocos`.
_CAMPOS_DO_EMAIL = (
    "id, protocolo, setor, categoria, resumo, relato_integral, extrato_para_o_setor, "
    "gravidade, prazo_area_em, sigilo_reforcado, anonimo, manifestante_nome, status"
)

# O que o setor lê quando, por algum caminho, o caso chegou ao email sem
# extrato. A frase mora no módulo dos blocos, que é quem monta o acionamento:
# os outros emails do caso a reaproveitam para dizer a mesma coisa.
_SEM_EXTRATO = SEM_EXTRATO

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
    instante de expediente.

    Quem NÃO passa por aqui: o acuse de recebimento ao manifestante, que sai no
    instante da abertura em qualquer gravidade (ADR 0042, decisão 2). A janela
    existe para não acordar quem trabalha no hospital; o acuse vai para quem
    está do lado de fora esperando saber se foi ouvido, e o prazo dele corre em
    horas CORRIDAS. Quem grava aquele instante é `ouvidoria_acuse`."""
    if gravidade == "critico":
        return agora
    return inicio_da_contagem(agora, feriados)


def proxima_tentativa(agora: dt.datetime, tentativas: int) -> dt.datetime | None:
    """Quando tentar de novo depois de `tentativas` falhas. None quando o
    limite acabou e o caso vira alerta ao admin técnico."""
    if tentativas >= MAX_TENTATIVAS:
        return None
    return agora + dt.timedelta(minutes=BACKOFF_MINUTOS[min(tentativas - 1, len(BACKOFF_MINUTOS) - 1)])


def _link_do_setor(manifestacao: dict) -> str:
    """Fallback sem token: a página de destino que diz ao responsável como
    responder. O caminho normal do acionamento passa o link tokenizado do
    portal (issue #326), emitido na hora do despacho."""
    return f"{settings.frontend_url}/ouvidoria-setor?protocolo={manifestacao.get('protocolo', '')}"


def _link_do_caso(manifestacao: dict) -> str:
    """Destino de quem TEM login no app (Diretoria Executiva, admin da
    Ouvidoria): o endereço próprio do caso (issue #476), e não a fila inteira,
    onde a pessoa ainda teria que procurar o protocolo na lista. Deslogado, o
    caminho é interno e volta pelo `?redirect=` da issue #477."""
    return f"{settings.frontend_url}/ouvidoria/m/{manifestacao.get('protocolo', '')}"


def montar_nova_demanda(
    manifestacao: dict,
    destinatario_nome: str,
    agora: dt.datetime,
    feriados: frozenset[dt.date],
    link: str | None = None,
) -> tuple[str, str, str]:
    """Assunto, HTML e texto do email de acionamento da área (NOVA_DEMANDA).

    O corpo carrega os três blocos do ADR 0041 (resumo, relato integral e nota
    da ouvidoria), montados pela mesma função que serve a tela do responsável:
    as duas superfícies dizem a mesma coisa sobre o mesmo caso, inclusive na
    variante sigilosa da RN-79."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    rotulo = rotular_vencimento(vencimento, agora, feriados)
    vencimento_formatado = formatar_vencimento(bruto)
    protocolo = manifestacao.get("protocolo") or ""
    identificacao = identificacao_do_caso(manifestacao)
    blocos = montar_blocos(manifestacao)
    aviso = aviso_do_caso(manifestacao)
    destino = link or _link_do_setor(manifestacao)

    html = jinja_env.get_template("email_ouvidoria_nova_demanda.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=manifestacao.get("setor") or "",
        categoria=manifestacao.get("categoria") or "",
        blocos=blocos,
        aviso=aviso,
        gravidade=manifestacao.get("gravidade") or "",
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=vencimento_formatado,
        rotulo_prazo=rotulo,
        identificacao=identificacao,
        link=destino,
        logo_base64=get_logo_data_uri(),
    )
    corpo_dos_blocos = "\n\n".join(f"{bloco['rotulo']}\n{bloco['texto']}" for bloco in blocos)
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A Ouvidoria acionou o setor {manifestacao.get('setor')} sobre a manifestacao {protocolo}.\n\n"
        + (f"{aviso}\n\n" if aviso else "")
        + f"{corpo_dos_blocos}\n\n"
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
        vencimento=formatar_vencimento(bruto),
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        rotulo_prazo=rotular_vencimento(vencimento, agora, feriados) if vencimento else None,
        link=_link_do_caso(manifestacao),
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"A manifestacao {protocolo} foi acionada no setor {setor}, que esta SEM TITULAR vigente.\n"
        f"A demanda subiu para {gestor_nome}, gestor da area.\n\n"
        f"Abra o caso na Ouvidoria: {_link_do_caso(manifestacao)}\n"
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
        vencimento=formatar_vencimento(bruto),
        rotulo_prazo=rotulo,
        sigiloso=bool(manifestacao.get("sigilo_reforcado")),
        link=destino,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"O prazo de resposta da manifestacao {protocolo} venceu e o setor {setor} ainda nao respondeu.\n"
        f"Prazo: {formatar_vencimento(bruto)} ({rotulo}).\n\n"
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
    vencimento_formatado = formatar_vencimento(bruto)

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
        link=link or _link_do_caso(manifestacao),
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
        link=link or _link_do_caso(manifestacao),
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
        link=link or _link_do_caso(manifestacao),
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
    prazo (issue #333). Quem recebe tem login, então o botão abre o caso no app
    (issue #515) e não um link tokenizado."""
    from app.services.email_constants import get_logo_data_uri

    bruto = manifestacao.get("prazo_area_em")
    vencimento = dt.datetime.fromisoformat(str(bruto)) if bruto else None
    protocolo = manifestacao.get("protocolo") or ""
    setor = manifestacao.get("setor") or ""
    dias = _dias_por_extenso(int(pedido.get("dias_uteis_pedidos") or 0))
    prazo_proposto = formatar_vencimento(pedido.get("prazo_novo"))
    justificativa = (pedido.get("justificativa") or "").strip()

    html = jinja_env.get_template("email_ouvidoria_prorrogacao_solicitada.html").render(
        destinatario_nome=destinatario_nome,
        protocolo=protocolo,
        setor=setor,
        faixa=faixa_da_gravidade(manifestacao.get("gravidade")),
        vencimento=formatar_vencimento(bruto),
        rotulo_prazo=rotular_vencimento(vencimento, agora, feriados),
        solicitante_nome=pedido.get("solicitante_nome") or "o responsável do setor",
        dias_pedidos=dias,
        prazo_proposto=prazo_proposto,
        justificativa=justificativa,
        link=_link_do_caso(manifestacao),
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        f"Ola {destinatario_nome},\n\n"
        f"O setor {setor} pediu prorrogacao de prazo na manifestacao {protocolo}.\n"
        f"Pedido: {dias}. Prazo proposto: {prazo_proposto}.\n\n"
        f"Justificativa da area: {justificativa}\n\n"
        f"Decida no caso da Ouvidoria: {_link_do_caso(manifestacao)}\n"
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
        vencimento=formatar_vencimento(bruto),
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
        f"Prazo de resposta: {formatar_vencimento(bruto)} ({rotular_vencimento(vencimento, agora, feriados)}).\n"
        + (f"\nMotivo da Ouvidoria: {motivo}\n" if motivo else "")
        + f"\nResponda pela Ouvidoria: {destino}\n"
    )
    return (f"Ouvidoria {protocolo}: prorrogacao {decisao}", html, texto)


def montar_acuse_recebimento(protocolo: str) -> tuple[str, str, str]:
    """Assunto, HTML e texto do acuse ao manifestante (issue #493, ADR 0042).

    O único email do módulo que sai do hospital, e o mais curto: protocolo e o
    que acontece a seguir. Nem gravidade, nem setor, nem prazo da área, nem
    extrato, **nem o nome de quem manifestou**.

    O nome saiu por segurança, e o motivo merece ficar escrito. O contato do
    canal aberto não tem confirmação de posse: quem manda o formulário escolhe
    o destinatário. Com o nome no corpo, escolhia junto o TEXTO da primeira
    linha do email, e o hospital entregava a frase de um estranho com a logo e
    a assinatura DKIM do próprio domínio. Sem nome não há texto de fora no
    corpo, e o abuso que sobra é só a entrega de um recibo de protocolo.

    Por isso a assinatura recebe o protocolo, e não a manifestação: a linha do
    caso traz relato, resumo e extrato para o setor, e passá-la inteira deixaria
    a porta encostada para o dia em que alguém quiser "ajudar a pessoa a
    reconhecer o caso".

    Também não recebe `agora` nem os feriados, ao contrário de todos os outros
    montadores: não há contagem regressiva a exibir. O prazo do acuse é rede de
    segurança da operação, e anunciá-lo a quem manifestou transformaria uma
    promessa cumprida no ato numa espera de 24 horas."""
    from app.services.email_constants import get_logo_data_uri

    protocolo = protocolo or ""
    html = jinja_env.get_template("email_ouvidoria_acuse.html").render(
        protocolo=protocolo,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        "Ola!\n\n"
        "Recebemos a sua manifestacao na Ouvidoria do Hospital Sao Matheus. "
        "Ela ja esta registrada e sera analisada pela nossa equipe.\n\n"
        f"Protocolo: {protocolo}\n\n"
        "Guarde este numero. E por ele que a Ouvidoria acompanha o seu caso.\n\n"
        "A Ouvidoria vai apurar o que voce relatou junto as areas responsaveis "
        "e entrar em contato com o desfecho.\n"
    )
    return (f"Ouvidoria {protocolo}: recebemos sua manifestacao", html, texto)


# Para onde a pessoa volta se o problema continuar (RN-80). É o formulário
# público, e não o portal do setor nem a página do caso: quem manifestou não tem
# login, e o protocolo é o que reata o retorno ao caso original dentro da janela
# de reincidência (issue #335).
def _canal_para_voltar() -> str:
    return f"{settings.frontend_url}/manifestacao"


def montar_encerramento_manifestante(protocolo: str, desfecho: str) -> tuple[str, str, str]:
    """Assunto, HTML e texto do aviso de encerramento (issue #494, ADR 0042).

    O segundo e último email do módulo que sai do hospital, e ele carrega
    exatamente três coisas: o protocolo, o desfecho em LINGUAGEM SIMPLES e o
    caminho para voltar. Nem gravidade, nem setor, nem prazo, nem extrato, nem o
    código interno do desfecho (`procedente` não é português), **nem o nome de
    quem manifestou**.

    O nome fica de fora pela mesma razão do acuse, e ela merece continuar
    escrita: o contato do canal aberto não tem confirmação de posse, então quem
    manda o formulário escolhe o destinatário. Com o nome no corpo, escolhia
    junto o TEXTO de um email assinado com o DKIM do domínio do hospital.

    `desfecho` é a única entrada de texto deste email, e ela vem de DENTRO: é o
    que o ouvidor autenticado escreveu para a pessoa (RN-64), o mesmo texto que
    a trilha imutável guardou. Passa pelo sanitizador de travessão porque campo
    livre é colado de qualquer lugar, e o Jinja escapa o HTML (`autoescape=True`).

    Por isso a assinatura recebe o protocolo e o texto, e não a manifestação: a
    linha do caso traz relato, resumo e extrato para o setor, e passá-la inteira
    deixaria a porta encostada para o dia em que alguém quiser "ajudar a pessoa
    a reconhecer o caso"."""
    from app.services.email_constants import get_logo_data_uri

    protocolo = protocolo or ""
    desfecho = sanitizar_travessao(desfecho or "").strip()
    voltar = _canal_para_voltar()
    html = jinja_env.get_template("email_ouvidoria_encerramento.html").render(
        protocolo=protocolo,
        desfecho=desfecho,
        canal_para_voltar=voltar,
        logo_base64=get_logo_data_uri(),
    )
    texto = (
        "Ola!\n\n"
        "A Ouvidoria do Hospital Sao Matheus concluiu a apuracao da sua manifestacao.\n\n"
        f"Protocolo: {protocolo}\n\n"
        f"O que foi apurado:\n{desfecho}\n\n"
        "Se o problema continuar ou se voce quiser falar de novo sobre este caso, "
        f"procure a Ouvidoria por {voltar} informando o numero do protocolo acima.\n"
    )
    return (f"Ouvidoria {protocolo}: sua manifestacao foi concluida", html, texto)


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


def status_da_ultima(supabase, manifestacao_id: str, gatilho: str) -> tuple[str | None, bool]:
    """O status da notificação MAIS RECENTE daquele gatilho naquele caso, e se a
    leitura valeu (issue #494).

    O status é None quando o caso não tem notificação daquele gatilho. O segundo
    valor separa esse None do outro, o da leitura que FALHOU, e existe porque os
    dois dão a mesma cara na tela: sem ele, banco fora do ar viraria "na fila de
    envio" num caso possivelmente já entregue, e nada denunciaria a diferença. É
    a mesma regra do calendário útil (issue #449): leitura que falhou chega
    marcada em vez de virar silêncio.

    A leitura pega a linha mais recente porque o reenvio manual pelo painel cria
    outra: o que vale é a última tentativa, não a primeira. E filtra pelo
    gatilho porque as duas pontas do ADR 0042 moram na mesma tabela e no mesmo
    caso: sem o filtro, o acuse entregue responderia pelo aviso que nunca saiu.

    Nasceu como o corpo de `ouvidoria_acuse.status_do_envio` e virou função de
    dois donos quando o aviso de encerramento pediu a mesma leitura."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .select("status, criada_em")
            .eq("manifestacao_id", manifestacao_id)
            .eq("gatilho", gatilho)
            .order("criada_em", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        # Só o TIPO da exceção: o `APIError` do PostgREST carrega `details` com
        # o "Failing row contains (...)", ou seja, nome, contato e relato de
        # quem manifestou. Log é lido por quem não tem perfil no módulo.
        logger.error(
            "[Ouvidoria] Falha ao ler o status de %s da manifestação %s (%s)",
            gatilho,
            manifestacao_id,
            type(exc).__name__,
        )
        return None, False
    linhas = result.data or []
    return (linhas[0].get("status") if linhas else None), True


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
        # Import DENTRO da função porque ele fecha um ciclo: este módulo é
        # importado por `ouvidoria_escalonamento`, que é importado por
        # `ouvidoria_prorrogacao`. Subir esta linha para o topo derruba o app
        # no startup, e não é o tipo de coisa que se descobre lendo o diff
        # (issue #375, item 20, decisão 7).
        #
        # O conteúdo vem da entidade própria, e não do `detalhe`: assim o
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
    if notificacao["gatilho"] == GATILHO_ACUSAR_RECEBIMENTO:
        # Fora do padrão dos outros de propósito: sem link, sem prazo, sem
        # calendário e sem nome, porque o email de quem manifestou não tem
        # contagem regressiva, nem porta do portal do setor, nem texto vindo de
        # fora (ver `montar_acuse_recebimento`).
        return montar_acuse_recebimento(manifestacao.get("protocolo") or "")
    if notificacao["gatilho"] == GATILHO_ENCERRAMENTO_MANIFESTANTE:
        # O desfecho vem do `detalhe` da LINHA, e não da coluna do caso, ao
        # contrário do que a prorrogação faz com o pedido dela. A diferença é a
        # reabertura por reincidência: ela zera `desfecho_descricao` no caso, e
        # o reenvio manual de um aviso antigo passaria a mandar o desfecho da
        # tramitação seguinte, ou um email mudo. A linha guarda o que foi dito
        # naquele ato, como a trilha imutável guarda (RN-64).
        return montar_encerramento_manifestante(manifestacao.get("protocolo") or "", notificacao.get("detalhe") or "")
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


def _aviso_para_o_log(assunto: str, texto: str) -> str:
    """O que do aviso pode ir para o log deste ambiente.

    O `texto` é o corpo do email, e ele carrega conteúdo de caso: protocolo,
    setor e degrau de cada caso travado na rodada de escalonamento, ou o id da
    manifestação, o email do destinatário e o erro do provedor. Imprimir isso
    no log do container põe conteúdo da Ouvidoria diante de quem tem acesso ao
    Coolify e não tem perfil nenhum no módulo: o gate do Dossiê deixaria de
    valer para aquele trecho (issue #466, o resto da #450).

    Mesma guarda do modo mock do `email_service`, e pelo mesmo motivo de sempre:
    só `development` imprime o corpo, porque na máquina do desenvolvedor o log é
    o único lugar em que se lê o aviso que se acabou de escrever. A regra é
    "só em development", e não "não é production": homologação roda com dado de
    verdade nesta casa.

    O que fica fora dele é o sinal de operação, que é o valor real deste log
    (diagnosticar um alerta que NÃO saiu): o assunto, que é onde já viaja a
    contagem de casos travados, mais o `request_id` que o `JsonFormatter` do
    middleware carimba sozinho. E o log DIZ que omitiu, senão quem lê conclui
    que o construtor gerou um aviso vazio.

    Os assuntos dos chamadores de aviso operacional são neutros, ao contrário
    dos assuntos das notificações de caso, cujo residual é pendência humana na
    decisão 7 do ADR 0039."""
    if settings.environment == "development":
        return f"{assunto}\n{texto}"
    return f"{assunto} | Corpo omitido: o aviso só entra no log quando ENVIRONMENT=development"


def avisar_admins_tecnicos(supabase, assunto: str, texto: str) -> int:
    """Manda um aviso operacional aos super admins do app, por fora da fila.

    Fora da fila de propósito: os dois motivos que chegam aqui (provedor de
    email caído, cadastro de setor incompleto) são justamente os que a fila não
    resolve sozinha. Devolve quantos receberam.

    O log vem sempre, entregue ou não: quando o canal de email é o problema, o
    log é o único rastro que sobra. O que vai nele fora do desenvolvimento é o
    assunto, e não o corpo (`_aviso_para_o_log`).

    Só super admin ATIVO, pelo mesmo motivo de `ler_diretoria_executiva`
    (issue #403): o corpo do alerta de cadastro carrega protocolo e setor de
    cada caso travado, e o desligamento do hospital não limpa
    `access_profile`. Aqui o filtro vale duas vezes, porque o retorno desta
    função é o que autoriza o carimbo `escalonamento_impossivel_em` (issue
    #373): entregue na caixa de quem já saiu, o caso sairia da varredura como
    avisado sem que ninguém do hospital soubesse."""
    try:
        result = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("access_profile", "super_admin")
            .eq("ativo", True)
            .execute()
        )
        destinos = [p for p in (result.data or []) if (p.get("email") or "").strip()]
    except Exception:
        destinos = []

    if not destinos:
        logger.error("[Ouvidoria] %s | Sem super admin com email para alertar", _aviso_para_o_log(assunto, texto))
        return 0

    # Template, e não f-string: o `texto` carrega a mensagem de exceção do
    # provedor de email e dados do caso, e o `f"<pre>{texto}</pre>"` de antes
    # era o único corpo do módulo montado fora do `autoescape=True` do
    # `jinja_env` (issue #375, item 1).
    from app.services.email_constants import get_logo_data_uri

    html = jinja_env.get_template("email_ouvidoria_aviso_admin.html").render(
        assunto=assunto,
        texto=texto,
        logo_base64=get_logo_data_uri(),
    )

    entregues = 0
    for admin in destinos:
        try:
            if _enviar_email(admin["email"], assunto, html, texto):
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
        logger.error("[Ouvidoria] %s | O alerta ao admin técnico não saiu", _aviso_para_o_log(assunto, texto))
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
        if notificacao["gatilho"] in GATILHOS_DO_MANIFESTANTE:
            # Endereço de gente de fora não entra no log da aplicação: ele sairia
            # ao lado do assunto, que carrega o protocolo, e o par diria a quem
            # lê o log do container QUEM abriu cada caso (issue #493).
            entregue = _enviar_email(notificacao["destinatario_email"], assunto, html, texto, endereco_fora_do_log=True)
        else:
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
