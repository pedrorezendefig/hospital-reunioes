"""O acuse de recebimento na abertura da manifestação (issue #493, ADR 0042).

Depois de receber o protocolo na tela, o manifestante nunca mais ouvia do
sistema (D-07). Esta é a primeira das duas pontas que o ADR 0042 fecha: todo
caso com email utilizável recebe, no ato da abertura, o aviso de que a
manifestação chegou, com o número do protocolo.

Três decisões moram aqui, e nenhuma é detalhe:

* **Sai na hora, por qualquer canal.** Não há janela comercial e não há job
  esperando: quem manifesta às 3h de um sábado recebe às 3h de um sábado. O
  prazo de 24 horas CORRIDAS da tabela é rede de segurança para falha de envio,
  e não meta de trabalho manual (ADR 0042, decisões 1 e 2).
* **Falhar aqui não desfaz a manifestação.** Esta função é chamada depois de o
  caso já existir e de o protocolo já ter sido dito a quem manifestou. Perder o
  aviso é ruim; perder o caso é inaceitável. Por isso ela não levanta: nem por
  banco fora do ar, nem por provedor de email caído, nem por dado torto. Quem
  chama não precisa de `try`, e o dia em que precisar é porque esta guarda foi
  removida por engano.
* **Quem não tem canal fica MARCADO, não esquecido.** Caso anônimo ou contato
  sem email reconhecível não gera acuse nenhum e recebe carimbo próprio
  (`acuse_sem_contato_em`). Sem ele, o caso ficaria indistinguível de um em que
  o hospital simplesmente deixou de avisar, e o indicador de retorno ao
  manifestante contaria no denominador quem nunca teve para onde ser avisado
  (ADR 0042, decisão 4; RN-81).
"""

from __future__ import annotations

import datetime as dt
import logging

from app.services import ouvidoria_notificacoes
from app.services.ouvidoria_contato import email_utilizavel

logger = logging.getLogger(__name__)

# O papel de quem recebe. Os outros doze gatilhos do catálogo escrevem para
# dentro do hospital (titular, gestor, Diretoria); este escreve para fora, e a
# fila do ouvidor precisa mostrar isso sem que alguém abra o caso.
PAPEL_MANIFESTANTE = "manifestante"

# O que a função devolve, para quem quiser registrar o desfecho. Ninguém
# depende disso hoje: as três rotas de criação chamam e seguem, porque o
# resultado do acuse não pode mudar a resposta que quem manifestou recebe.
ENVIADO = "enviado"
SEM_CONTATO = "sem_contato"
FALHOU = "falhou"


def acusar_recebimento(supabase, caso: dict, agora: dt.datetime) -> str:
    """Avisa quem manifestou de que a manifestação chegou. Nunca levanta.

    `caso` é a linha recém-inserida em `ouvidoria_protocolos`, com `id`,
    `protocolo`, `anonimo`, `manifestante_nome` e `manifestante_contato`."""
    try:
        return _acusar(supabase, caso, agora)
    except Exception:  # noqa: BLE001
        # Sem `exc_info` e sem o caso no texto: o que sobra no log é o
        # identificador, e não o contato nem o relato de quem manifestou.
        logger.exception("[Ouvidoria] Falha ao acusar o recebimento da manifestação %s", caso.get("id"))
        return FALHOU


def _acusar(supabase, caso: dict, agora: dt.datetime) -> str:
    email = destinatario_do_acuse(caso)
    if email is None:
        _carimbar(supabase, caso, {"acuse_sem_contato_em": agora.isoformat()})
        return SEM_CONTATO

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=caso["id"],
        gatilho=ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO,
        destinatario_nome=(caso.get("manifestante_nome") or "").strip() or ouvidoria_notificacoes.MANIFESTANTE_SEM_NOME,
        destinatario_email=email,
        papel_destinatario=PAPEL_MANIFESTANTE,
        # O instante da abertura, e não o próximo instante de expediente: é a
        # decisão 2 do ADR 0042 escrita em uma linha.
        enviar_a_partir_de=agora,
    )
    if notificacao is None:
        # `registrar` já engoliu a exceção e gravou o erro no log. Sem linha não
        # há o que despachar nem o que carimbar: carimbar aqui diria que o
        # manifestante foi avisado quando nem a prova da tentativa existe.
        return FALHOU

    # O carimbo vem ANTES do envio, e é isso que ele significa: o acuse foi
    # gerado. O envio em si tem estado próprio na linha da notificação
    # (agendada, enviando, enviada, falha), com retentativa e botão de reenvio.
    # Carimbar só depois do provedor responder faria o caso cujo email está na
    # terceira tentativa parecer um caso que ninguém tentou avisar.
    _carimbar(supabase, caso, {"acuse_recebimento_em": agora.isoformat()})

    # Feriados vazios de propósito: o acuse não consulta calendário útil em
    # nenhum ponto do caminho (o montador dele não tem contagem regressiva), e
    # ir ao banco buscar o que não vai ser usado só acrescentaria uma consulta
    # ao caminho de quem está com o formulário aberto esperando o protocolo.
    ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, frozenset())
    return ENVIADO


def destinatario_do_acuse(caso: dict) -> str | None:
    """Para quem o acuse vai, ou None quando não há para quem.

    O pedido de anonimato vence qualquer dado que tenha sobrado no corpo do
    registro: a tela prometeu que não haveria identificação, e escrever para
    aquele endereço quebraria a promessa mesmo com o email ali à mão."""
    if caso.get("anonimo"):
        return None
    return email_utilizavel(caso.get("manifestante_contato"))


def _carimbar(supabase, caso: dict, mudanca: dict) -> None:
    supabase.table("ouvidoria_protocolos").update(mudanca).eq("id", caso["id"]).execute()
