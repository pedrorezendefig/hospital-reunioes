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

from fastapi import BackgroundTasks

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
REGISTRADO = "registrado"
SEM_CONTATO = "sem_contato"
FALHOU = "falhou"


def acusar_recebimento(supabase, caso: dict, agora: dt.datetime, tarefas: BackgroundTasks) -> str:
    """Avisa quem manifestou de que a manifestação chegou. Nunca levanta.

    `caso` é a linha recém-inserida em `ouvidoria_protocolos`, com `id`,
    `protocolo`, `anonimo` e `manifestante_contato`.

    `tarefas` é por onde o EMAIL sai, depois da resposta. A chamada ao provedor
    é síncrona e tem timeout de 30 segundos, e o backend sobe com um event loop
    só (uvicorn sem `--workers`): despachar dentro da requisição faria cada POST
    do formulário público poder segurar o loop inteiro por meio minuto, e junto
    com ele o painel, o login e o portal do setor. O `BackgroundTasks` do
    Starlette roda função síncrona no threadpool, então o loop segue livre.

    O registro e o carimbo continuam dentro da requisição: são duas escritas
    curtas no PostgREST, no mesmo padrão do resto do módulo, e é a linha
    gravada que faz o reenvio existir se o email não sair."""
    try:
        return _acusar(supabase, caso, agora, tarefas)
    except Exception as exc:  # noqa: BLE001
        # Só o TIPO da exceção, nunca a mensagem e nunca o traceback. O
        # `APIError` do PostgREST carrega `details` com o `Failing row contains
        # (...)`, ou seja, nome, contato e relato de quem manifestou, e o
        # formatador de log serializa `exc_info` inteiro. Log é lido por quem
        # não tem perfil no módulo.
        logger.error(
            "[Ouvidoria] Falha ao acusar o recebimento da manifestação %s (%s)",
            caso.get("id"),
            type(exc).__name__,
        )
        return FALHOU


def _acusar(supabase, caso: dict, agora: dt.datetime, tarefas: BackgroundTasks) -> str:
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

    # O carimbo diz que o acuse foi GERADO, e é só isso que ele diz. Quem sabe
    # se o email chegou é o status da linha da notificação (agendada, enviando,
    # enviada, falha), e é dele que a página do caso tira a frase que mostra
    # (`ouvidoria_marcos.acuse_do_caso`). Carimbar só depois do provedor
    # responder faria o caso na terceira tentativa parecer um caso que ninguém
    # tentou avisar, e o envio nem acontece mais nesta requisição.
    _carimbar(supabase, caso, {"acuse_recebimento_em": agora.isoformat()})

    tarefas.add_task(despachar_acuse, supabase, notificacao, agora)
    return REGISTRADO


def despachar_acuse(supabase, notificacao: dict, agora: dt.datetime) -> None:
    """Entrega o acuse, já fora da requisição. Nunca levanta: aqui não há mais
    ninguém para receber o erro, e a linha na fila é o que sobra para o job
    periódico e para o botão de reenvio.

    Feriados vazios de propósito: o acuse não consulta calendário útil em ponto
    nenhum do caminho (o montador dele não tem contagem regressiva), e ir ao
    banco buscar o que não vai ser usado só acrescentaria uma consulta."""
    try:
        ouvidoria_notificacoes.despachar_agora_se_puder(supabase, notificacao, agora, frozenset())
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[Ouvidoria] Falha ao despachar o acuse da manifestação %s (%s)",
            notificacao.get("manifestacao_id"),
            type(exc).__name__,
        )


def destinatario_do_acuse(caso: dict) -> str | None:
    """Para quem o acuse vai, ou None quando não há para quem.

    O pedido de anonimato vence qualquer dado que tenha sobrado no corpo do
    registro: a tela prometeu que não haveria identificação, e escrever para
    aquele endereço quebraria a promessa mesmo com o email ali à mão."""
    if caso.get("anonimo"):
        return None
    return email_utilizavel(caso.get("manifestante_contato"))


def _carimbar(supabase, caso: dict, mudanca: dict) -> None:
    """Grava o carimbo do acuse no caso, com guarda própria.

    A guarda existe porque o `APIError` do PostgREST traz a LINHA que falhou
    dentro de `details`, e um erro subindo daqui até o `except` de cima seria
    exatamente o dado do manifestante chegando ao log por outro caminho. Falhar
    o carimbo não desfaz nada: o registro da notificação já está no banco, e é
    ele que prova a tentativa."""
    try:
        supabase.table("ouvidoria_protocolos").update(mudanca).eq("id", caso["id"]).execute()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[Ouvidoria] Falha ao carimbar o acuse da manifestação %s (%s)",
            caso.get("id"),
            type(exc).__name__,
        )


def status_do_envio(supabase, manifestacao_id: str) -> tuple[str | None, bool]:
    """O status da notificação do acuse daquele caso, e se a leitura valeu.

    O status é None quando o caso não tem acuse gerado. O segundo valor separa
    esse None do outro, o da leitura que FALHOU, e existe porque os dois dão a
    mesma cara na tela: sem ele, banco fora do ar viraria "na fila de envio"
    num caso possivelmente já entregue, e nada denunciaria a diferença. É a
    mesma regra do calendário útil (issue #449): leitura que falhou chega
    marcada em vez de virar silêncio.

    A leitura pega a linha MAIS RECENTE porque o reenvio manual pelo painel
    cria outra: o que vale é a última tentativa, não a primeira."""
    try:
        result = (
            supabase.table("ouvidoria_notificacoes")
            .select("status, criada_em")
            .eq("manifestacao_id", manifestacao_id)
            .eq("gatilho", ouvidoria_notificacoes.GATILHO_ACUSAR_RECEBIMENTO)
            .order("criada_em", desc=True)
            .limit(1)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[Ouvidoria] Falha ao ler o status do acuse da manifestação %s (%s)",
            manifestacao_id,
            type(exc).__name__,
        )
        return None, False
    linhas = result.data or []
    return (linhas[0].get("status") if linhas else None), True
