"""O aviso de encerramento ao manifestante (issue #494, ADR 0042).

A segunda e última ponta do ADR 0042, e a irmã de `ouvidoria_acuse`: a #493 fez
o hospital dizer "chegou"; esta faz o hospital dizer "no que deu". Sem ela,
encerrar o caso no sistema não era encerrar para o paciente (RN-80): a fila do
ouvidor esvaziava e quem reclamou continuava esperando.

Quatro decisões moram aqui, e as três primeiras são as mesmas do acuse porque o
caminho é o mesmo:

* **Sai na transição de encerramento**, no ato, sem janela comercial. O
  encerramento é o ato do ouvidor, não um job noturno: segurar o email até a
  próxima abertura do expediente faria a pessoa esperar por um trabalho que já
  terminou.
* **Falhar aqui não desfaz o encerramento.** Esta função é chamada depois de a
  transição já ter acontecido e de o movimento já estar na trilha imutável.
  Perder o aviso é ruim; perder o ato do ouvidor é inaceitável. Por isso ela não
  levanta: nem por banco fora do ar, nem por provedor caído, nem por dado torto.
* **Quem não tem canal fica MARCADO, não esquecido.** Caso anônimo ou contato
  sem email reconhecível não gera aviso nenhum e recebe carimbo próprio
  (`encerramento_sem_contato_em`). Sem ele, o caso ficaria indistinguível de um
  em que o hospital simplesmente deixou de avisar, e o indicador de resposta
  conclusiva contaria no denominador quem nunca teve para onde ser avisado
  (ADR 0042, decisão 4; RN-81).
* **O texto do desfecho é congelado na LINHA da notificação**, e não lido do
  caso na hora do envio. A reabertura por reincidência zera
  `desfecho_descricao`: sem o congelamento, o reenvio manual de um aviso antigo
  mandaria o desfecho da tramitação seguinte, ou um email mudo.
"""

from __future__ import annotations

import datetime as dt
import logging

from fastapi import BackgroundTasks

from app.services import ouvidoria_notificacoes
from app.services.ouvidoria_contato import PAPEL_MANIFESTANTE, destinatario_do_caso

logger = logging.getLogger(__name__)

# O que a função devolve, para quem quiser registrar o desfecho. A rota de
# transição chama e segue: o resultado do aviso não pode mudar a resposta que o
# ouvidor recebe do encerramento.
REGISTRADO = "registrado"
SEM_CONTATO = "sem_contato"
SEM_DESFECHO = "sem_desfecho"
FALHOU = "falhou"

# A regra de para quem dá para escrever é a MESMA do acuse, e por isso é o mesmo
# objeto: `ouvidoria_contato` é a função única do app (critério de aceite da
# #493). Duas cópias fariam um caso receber o "chegou" e não receber o "no que
# deu", ou entrar no denominador de um indicador e sair do outro.
destinatario_do_aviso = destinatario_do_caso


def avisar_encerramento(
    supabase,
    caso: dict,
    desfecho_descricao: str | None,
    agora: dt.datetime,
    tarefas: BackgroundTasks,
) -> str:
    """Diz a quem manifestou no que deu. Nunca levanta.

    `caso` é a linha de `ouvidoria_protocolos` depois da transição, com `id`,
    `protocolo`, `anonimo` e `manifestante_contato`.

    `desfecho_descricao` é o que o ouvidor escreveu PARA A PESSOA (RN-64), e é
    ele que vai no corpo. O código do desfecho (`procedente` e companhia) não
    entra em lugar nenhum do email: é vocabulário de sistema.

    `tarefas` é por onde o EMAIL sai, depois da resposta. A chamada ao provedor
    é síncrona e tem timeout de 30 segundos, e o backend sobe com um event loop
    só (uvicorn sem `--workers`): despachar dentro da requisição faria cada
    encerramento poder segurar o loop inteiro por meio minuto, e junto com ele o
    painel, o login e o portal do setor.

    O registro e o carimbo continuam dentro da requisição: são duas escritas
    curtas no PostgREST, e é a linha gravada que faz o reenvio existir se o
    email não sair."""
    try:
        return _avisar(supabase, caso, desfecho_descricao, agora, tarefas)
    except Exception as exc:  # noqa: BLE001
        # Só o TIPO da exceção, nunca a mensagem e nunca o traceback. O
        # `APIError` do PostgREST carrega `details` com o "Failing row contains
        # (...)", ou seja, nome, contato e relato de quem manifestou, e o
        # formatador de log da casa serializa `exc_info` inteiro. Log é lido por
        # quem não tem perfil no módulo (issue #450).
        logger.error(
            "[Ouvidoria] Falha ao avisar o encerramento da manifestação %s (%s)",
            caso.get("id"),
            type(exc).__name__,
        )
        return FALHOU


def _avisar(
    supabase,
    caso: dict,
    desfecho_descricao: str | None,
    agora: dt.datetime,
    tarefas: BackgroundTasks,
) -> str:
    desfecho = (desfecho_descricao or "").strip()
    if not desfecho:
        # A máquina de estados exige a descrição para encerrar, então isto é
        # cinto de segurança para caminho novo. Um email dizendo só "concluímos"
        # é pior do que nenhum: ele encerra a conversa sem responder nada, e a
        # pessoa não tem como saber que faltou texto.
        logger.error(
            "[Ouvidoria] Encerramento da manifestação %s sem descrição do desfecho: aviso não enviado",
            caso.get("id"),
        )
        return SEM_DESFECHO

    email = destinatario_do_aviso(caso)
    if email is None:
        _carimbar(supabase, caso, {"encerramento_sem_contato_em": agora.isoformat()})
        return SEM_CONTATO

    notificacao = ouvidoria_notificacoes.registrar(
        supabase,
        manifestacao_id=caso["id"],
        gatilho=ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE,
        destinatario_nome=(caso.get("manifestante_nome") or "").strip() or ouvidoria_notificacoes.MANIFESTANTE_SEM_NOME,
        destinatario_email=email,
        # O papel de quem recebe, o mesmo do acuse: a fila do ouvidor precisa
        # mostrar que esta linha fala para FORA do hospital sem que alguém abra o
        # caso. Vem de `ouvidoria_contato`, e não é reescrito aqui, porque é ele
        # que decide se o endereço fica fora do log (issue #547).
        papel_destinatario=PAPEL_MANIFESTANTE,
        # O instante do encerramento, e não o próximo instante de expediente: o
        # ato acabou de acontecer e a pessoa está esperando desde a abertura.
        enviar_a_partir_de=agora,
        # O desfecho congelado no ato. Ver o docstring do módulo: a coluna do
        # caso é sobrescrita pela reabertura por reincidência.
        detalhe=desfecho,
    )
    if notificacao is None:
        # `registrar` já engoliu a exceção e gravou o erro no log. Sem linha não
        # há o que despachar nem o que carimbar: carimbar aqui diria que a
        # pessoa foi avisada quando nem a prova da tentativa existe.
        return FALHOU

    # O carimbo diz que o aviso foi GERADO, e é só isso que ele diz. Quem sabe
    # se o email chegou é o status da linha da notificação (agendada, enviando,
    # enviada, falha), e é dele que a página do caso tira a frase que mostra
    # (`ouvidoria_marcos.aviso_do_encerramento`). Carimbar só depois de o
    # provedor responder faria o caso na terceira tentativa parecer um caso que
    # ninguém tentou avisar, e o envio nem acontece mais nesta requisição.
    _carimbar(supabase, caso, {"encerramento_avisado_em": agora.isoformat()})

    tarefas.add_task(despachar_aviso, supabase, notificacao, agora)
    return REGISTRADO


def despachar_aviso(supabase, notificacao: dict, agora: dt.datetime) -> None:
    """Entrega o aviso, já fora da requisição. Nunca levanta: aqui não há mais
    ninguém para receber o erro, e a linha na fila é o que sobra para o job
    periódico e para o botão de reenvio.

    Feriados vazios de propósito: este email não consulta calendário útil em
    ponto nenhum do caminho (o montador dele não tem contagem regressiva), e ir
    ao banco buscar o que não vai ser usado só acrescentaria uma consulta."""
    try:
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, frozenset())
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[Ouvidoria] Falha ao despachar o aviso de encerramento da manifestação %s (%s)",
            notificacao.get("manifestacao_id"),
            type(exc).__name__,
        )


def _carimbar(supabase, caso: dict, mudanca: dict) -> None:
    """Grava o carimbo do aviso no caso, com guarda própria.

    A guarda existe porque o `APIError` do PostgREST traz a LINHA que falhou
    dentro de `details`, e um erro subindo daqui até o `except` de cima seria
    exatamente o dado do manifestante chegando ao log por outro caminho. Falhar
    o carimbo não desfaz nada: o registro da notificação já está no banco, e é
    ele que prova a tentativa.

    O carimbo também entra no `caso` que veio, e não só no banco. Quem chama é a
    rota de transição, que devolve esse mesmo dicionário como Dossiê na resposta
    do encerramento: sem esta linha a página do caso mostraria "ainda não
    aconteceu" no primeiro clique, e só descobriria a verdade num F5. É a mesma
    costura do carimbo do T3, logo acima dela na rota."""
    try:
        supabase.table("ouvidoria_protocolos").update(mudanca).eq("id", caso["id"]).execute()
        caso.update(mudanca)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[Ouvidoria] Falha ao carimbar o aviso de encerramento da manifestação %s (%s)",
            caso.get("id"),
            type(exc).__name__,
        )


def status_do_envio(supabase, manifestacao_id: str) -> tuple[str | None, bool]:
    """O status da notificação do aviso daquele caso, e se a leitura valeu.

    Delega à leitura genérica do catálogo, filtrada pelo gatilho: as duas pontas
    do ADR 0042 moram na mesma tabela e no mesmo caso, e ler sem o filtro faria
    o acuse entregue responder pelo aviso que nunca saiu."""
    return ouvidoria_notificacoes.status_da_ultima(
        supabase, manifestacao_id, ouvidoria_notificacoes.GATILHO_ENCERRAMENTO_MANIFESTANTE
    )
