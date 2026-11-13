"""O agente de triagem da Ouvidoria (issue #1624, PRD #1527, ADR 0087).

Logo depois da chegada de toda manifestação (qualquer canal) e de toda
avaliação do QR com comentário, o texto passa pela pseudonimização da
Ouvidoria e vai ao modelo, uma vez. O agente devolve:

- no caso, o **assunto** de uma linha e, quando o relato descreve incidente
  com o paciente, o **apontamento ao Núcleo** com as duas justificativas (a
  simples, para o ouvidor, e a técnica, para o Núcleo);
- na avaliação, a marca **Para revisar** com o motivo.

Só sugere (decisão 2). O que ele escreve passa por uma lista fechada de
colunas: tipo, gravidade, sigilo e área nunca saem daqui, venha o que vier na
resposta do modelo.

É a exceção da decisão 1 à ADR 0082: quem dispara é o envio, não um relógio.
Uma tentativa (o SDK não repete, `max_retries=0`), sem job e sem retentativa,
e no máximo `TETO_DIARIO` chamadas por dia no app inteiro, contadas no banco
(`ouvidoria_agente_reservar_chamada`, migration 143) para valer entre
processos e reinícios. Falha ou teto: o caso entra sem assunto e sem alerta,
com log e com um movimento na trilha dizendo por quê (decisão 3). A avaliação
não tem trilha: fica o log.

Roda depois da resposta (`BackgroundTasks`), no executor da IA
(`chamar_ia_fora_do_loop`): o envio público já respondeu quando o modelo é
chamado, e nada daqui volta para quem preencheu o formulário.
"""

from __future__ import annotations

import json
import logging

import anthropic

from app.config import settings
from app.services import ai_processor
from app.services.ouvidoria_pseudonimizacao import pseudonimizar
from app.services.prompt_loader import load_prompt
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

TETO_DIARIO = 300
FUNCAO_DA_COTA = "ouvidoria_agente_reservar_chamada"

# Quem assina o movimento da trilha quando o agente não escreveu o assunto.
# Não é participante: `autor_id` fica nulo, como no canal aberto.
AUTOR_DO_MOVIMENTO = "Agente de triagem"
MOTIVO_TETO = f"o limite de {TETO_DIARIO} leituras por dia foi atingido"
MOTIVO_FALHA = "o agente de triagem não respondeu"

# A resposta é um JSON curto: o teto é folga, não orçamento.
MAX_TOKENS = 1024
TEMPO_LIMITE_S = 60.0
TAMANHO_DO_ASSUNTO = 120


def _cliente() -> anthropic.Anthropic | None:
    """O cliente da Anthropic, ou None sem chave (ambiente local e CI): sem
    chave o agente fica desligado e o caso entra como sempre entrou."""
    if not settings.anthropic_api_key:
        return None
    return anthropic.Anthropic(api_key=settings.anthropic_api_key, max_retries=0, timeout=TEMPO_LIMITE_S)


def agendar_caso(tarefas, supabase, caso: dict) -> None:
    """Põe a triagem do caso recém-criado para depois da resposta."""
    tarefas.add_task(_triar_caso_fora_do_loop, supabase, caso)


def agendar_avaliacao(tarefas, supabase, avaliacao: dict) -> None:
    """Põe a leitura da avaliação para depois da resposta. Sem comentário não
    há o que ler, e o agente não é chamado."""
    if not (avaliacao.get("comentario") or "").strip():
        return
    tarefas.add_task(_triar_avaliacao_fora_do_loop, supabase, avaliacao)


async def _triar_caso_fora_do_loop(supabase, caso: dict) -> None:
    await ai_processor.chamar_ia_fora_do_loop(triar_caso, supabase, caso)


async def _triar_avaliacao_fora_do_loop(supabase, avaliacao: dict) -> None:
    await ai_processor.chamar_ia_fora_do_loop(triar_avaliacao, supabase, avaliacao)


def triar_caso(supabase, caso: dict) -> None:
    """Lê o relato do caso e grava o assunto e o apontamento ao Núcleo. Nunca
    levanta: o caso já existe e já tem protocolo."""
    relato = caso.get("relato_integral") or caso.get("resumo") or ""
    if not relato.strip():
        return
    cliente = _cliente()
    if cliente is None:
        return
    try:
        if not _reservar(supabase):
            logger.warning("[Ouvidoria] Agente de triagem: teto diário atingido, caso %s sem assunto", caso.get("id"))
            _registrar_na_trilha(supabase, caso, MOTIVO_TETO)
            return
        resposta = _perguntar(cliente, "ouvidoria_agente_triagem_caso", pseudonimizar(relato))
        sugestao = _sugestao_do_caso(resposta)
        supabase.table("ouvidoria_protocolos").update(sugestao).eq("id", caso["id"]).execute()
    except Exception as exc:
        logger.warning("[Ouvidoria] Agente de triagem falhou no caso %s (%s)", caso.get("id"), type(exc).__name__)
        _registrar_na_trilha(supabase, caso, MOTIVO_FALHA)


def triar_avaliacao(supabase, avaliacao: dict) -> None:
    """Lê o comentário da avaliação e marca Para revisar quando ele sugere
    gravidade. Nunca levanta: a nota já foi gravada."""
    comentario = (avaliacao.get("comentario") or "").strip()
    if not comentario:
        return
    cliente = _cliente()
    if cliente is None:
        return
    try:
        if not _reservar(supabase):
            logger.warning(
                "[Ouvidoria] Agente de triagem: teto diário atingido, avaliação %s não lida", avaliacao.get("id")
            )
            return
        resposta = _perguntar(cliente, "ouvidoria_agente_triagem_avaliacao", pseudonimizar(comentario))
        marca = _marca_da_avaliacao(resposta)
        if marca:
            supabase.table("ouvidoria_avaliacoes").update(marca).eq("id", avaliacao["id"]).execute()
    except Exception as exc:
        logger.warning(
            "[Ouvidoria] Agente de triagem falhou na avaliação %s (%s)", avaliacao.get("id"), type(exc).__name__
        )


def _reservar(supabase) -> bool:
    """Reserva uma das chamadas do dia. Só um `true` explícito do banco libera:
    resposta em qualquer outro formato conta como teto, que é o lado seguro."""
    dados = supabase.rpc(FUNCAO_DA_COTA, {"p_teto": TETO_DIARIO}).execute().data
    return isinstance(dados, list) and len(dados) == 1 and dados[0].get("reservada") is True


def _perguntar(cliente, prompt: str, texto: str) -> dict:
    """Uma chamada ao modelo. Devolve o objeto JSON da resposta; recusa,
    resposta cortada ou texto que não é objeto viram erro."""
    resposta = cliente.messages.create(
        model=settings.ouvidoria_agente_modelo,
        max_tokens=MAX_TOKENS,
        system=load_prompt(prompt),
        messages=[{"role": "user", "content": texto}],
    )
    if resposta.stop_reason in ("refusal", "max_tokens"):
        raise ValueError(f"resposta interrompida ({resposta.stop_reason})")
    bruto = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    objeto = json.loads(bruto[inicio : fim + 1] if 0 <= inicio < fim else bruto)
    if not isinstance(objeto, dict):
        raise ValueError("a resposta não é um objeto")
    return objeto


def _linha(valor) -> str | None:
    """Texto de uma linha, sanitizado, ou None quando não sobra nada."""
    if not isinstance(valor, str):
        return None
    texto = " ".join(sanitizar_travessao(valor).split())
    return texto or None


def _sugestao_do_caso(resposta: dict) -> dict:
    """As colunas que o agente pode escrever no caso, e só elas (ADR 0087,
    decisão 2). O assunto passa pela pseudonimização de novo: se o modelo
    escrever um nome, ele sai como marcador, e não na fila."""
    assunto = _linha(resposta.get("assunto"))
    if assunto:
        assunto = _linha(pseudonimizar(assunto))
    if not assunto:
        raise ValueError("a resposta veio sem assunto")
    sugestao: dict = {"assunto": assunto[:TAMANHO_DO_ASSUNTO]}
    simples = _texto(resposta.get("nsp_justificativa_simples"))
    tecnica = _texto(resposta.get("nsp_justificativa_tecnica"))
    if resposta.get("nsp_sugerido") is True and simples and tecnica:
        sugestao |= {
            "nsp_sugerido": True,
            "nsp_justificativa_simples": simples,
            "nsp_justificativa_tecnica": tecnica,
        }
    return sugestao


def _marca_da_avaliacao(resposta: dict) -> dict | None:
    """A marca Para revisar com o motivo, ou None quando o agente não marcou.
    Sem motivo não há marca: o ouvidor precisa saber por quê."""
    motivo = _linha(resposta.get("revisar_motivo"))
    if resposta.get("revisar") is not True or not motivo:
        return None
    return {"revisar": True, "revisar_motivo": motivo}


def _texto(valor) -> str | None:
    if not isinstance(valor, str):
        return None
    texto = sanitizar_travessao(valor).strip()
    return texto or None


def _registrar_na_trilha(supabase, caso: dict, motivo: str) -> None:
    """O movimento que explica o caso sem assunto (ADR 0087, decisão 3). Sem
    mudança de estado: a observação já é a descrição de uma linha."""
    estado = caso.get("status") or "em_classificacao"
    try:
        supabase.table("ouvidoria_movimentos").insert(
            {
                "manifestacao_id": caso["id"],
                "estado_anterior": estado,
                "estado_novo": estado,
                "autor_id": None,
                "autor_nome": AUTOR_DO_MOVIMENTO,
                "observacao": f"Assunto não gerado: {motivo}.",
            }
        ).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao gravar na trilha o assunto não gerado do caso %s", caso.get("id"))
