"""O agente de triagem do Núcleo (issue #1990, PRD #1979, ADR 0095 e 0107).

Toda notificação, logo depois do registro, vai ao agente uma vez, em segundo
plano (`BackgroundTasks`, no executor da IA): quem notificou já recebeu o
protocolo quando o modelo é chamado. O agente só sugere; quem decide é a
Presidência, na tela de triagem.

A instrução de sistema é o prompt do Anexo B seguido da base do Anexo A, os
dois versionados em `app/prompts/` (a versão é a linha "Versão" de cada
arquivo), com a marca de cache no fim. A notificação entra pseudonimizada, no
formato `<notificacao>` (`triagem_do_agente`).

O que pode acontecer com a notificação:

- a resposta passa no validador: grava uma linha em `nsp_triagens`, com as
  versões do prompt e da base e o modelo;
- a resposta não passa: o agente é chamado de novo uma vez, com as violações;
  se falhar de novo, a notificação fica marcada "classificar manualmente"
  (`validacao`);
- o agente está desligado, sem chave ou não respondeu (`agente_fora`), ou a
  cota do dia acabou (`teto`): a notificação fica marcada do mesmo jeito,
  sem nunca ficar retida.

Cada chamada ao modelo, a refeita também, gasta uma das `TETO_DIARIO`
chamadas do dia, contadas no banco à parte da Ouvidoria (migration 188, ADR
0107, decisão 11). O SDK não repete (`max_retries=0`).

`classificar_pelo_agente_do_nucleo` é a mesma função que o comando manual do
teste de aceite usa (`scripts/nsp_teste_de_aceite.py`).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from app.config import settings
from app.services import ai_processor
from app.services.ia_chaves import ClienteDaAnthropic
from app.services.prompt_loader import load_prompt
from app.services.seguranca_do_paciente import esclarecimentos, triagem_do_agente
from app.utils.text_sanitizer import sanitizar_travessao

logger = logging.getLogger(__name__)

PROMPT = "nsp_agente_triagem"
BASE = "nsp_base_de_conhecimento"

TETO_DIARIO = 100
FUNCAO_DA_COTA = "nsp_agente_reservar_chamada"
TENTATIVAS = 2

AGENTE_FORA = "agente_fora"
TETO = "teto"
VALIDACAO = "validacao"
# Só da nova leitura com as respostas (issue #1991), que nunca marca a
# notificação: ela não grava quando a confirmação ou outra resposta chegou.
LEITURA_SUPERADA = "leitura_superada"

# A resposta é um JSON de umas 600 palavras; o resto é folga para o raciocínio.
MAX_TOKENS = 4096
TEMPO_LIMITE_S = 90.0
# O teto da coluna `nsp_triagens.assunto` (migration 188).
TAMANHO_DO_ASSUNTO = 300

_VERSAO = re.compile(r"^Versão (\d+(?:\.\d+)*)", re.MULTILINE)

_O_QUE_A_REGRA_DIZ = {
    "natureza_e_dano": (
        "circunstância de risco, quase erro e incidente sem dano exigem dano nenhum; "
        "evento adverso exige dano de leve a óbito"
    ),
    "faixa": (
        "a faixa não corresponde: A para óbito ou evento da lista com situação sim, B grave, C moderado, "
        "D leve ou incidente sem dano, E quase erro ou circunstância de risco"
    ),
    "revisao": (
        "a revisão é campo a campo nas faixas A e B, em qualquer menção a morte e quando a situação "
        "do evento da lista é possível"
    ),
    "canais": "canais contém NSP sempre que a natureza não é nao_e_do_nsp",
}


def versao(nome: str) -> str:
    """A versão de um dos dois textos, lida da linha "Versão" do arquivo."""
    achada = _VERSAO.search(load_prompt(nome))
    if not achada:
        raise ValueError(f"o texto {nome} não diz a versão")
    return achada.group(1)


def instrucao_de_sistema() -> list[dict]:
    """O prompt e a base, nessa ordem, com o cache no fim: os dois não mudam
    entre uma notificação e outra."""
    return [
        {"type": "text", "text": load_prompt(PROMPT)},
        {"type": "text", "text": load_prompt(BASE), "cache_control": {"type": "ephemeral"}},
    ]


@dataclass
class Triagem:
    """O que o agente devolveu para uma notificação: a sugestão validada, ou o
    motivo de ela ficar para classificar manualmente."""

    sugestao: dict | None = None
    motivo_manual: str | None = None
    tentativas: int = 0
    violacoes: list[str] = field(default_factory=list)


def _explicar(violacoes: list[str]) -> str:
    return "; ".join(
        _O_QUE_A_REGRA_DIZ.get(v, f"o campo {v.split(':', 1)[-1]} está fora do formato") for v in violacoes
    )


def _mensagem(texto: str, violacoes: list[str]) -> str:
    if not violacoes:
        return texto
    return (
        f"{texto}\n\nA resposta anterior a esta notificação foi recusada pela validação do sistema: "
        f"{_explicar(violacoes)}. Responda de novo com o objeto JSON completo, no formato e nas regras de coerência."
    )


def _perguntar_ao_agente_do_nucleo(cliente, modelo: str, mensagem: str):
    """Uma chamada ao modelo. Devolve o objeto da resposta, ou None quando ela
    não é um objeto JSON (conta como resposta inválida, e não como agente
    fora). Erro da API sobe."""
    resposta = cliente.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        system=instrucao_de_sistema(),
        messages=[{"role": "user", "content": mensagem}],
    )
    if resposta.stop_reason in ("refusal", "max_tokens"):
        return None
    bruto = "".join(bloco.text for bloco in resposta.content if bloco.type == "text")
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    try:
        objeto = json.loads(bruto[inicio : fim + 1] if 0 <= inicio < fim else bruto)
    except ValueError:
        return None
    return objeto if isinstance(objeto, dict) else None


def _sanitizada(valor):
    if isinstance(valor, str):
        return sanitizar_travessao(valor).strip()
    if isinstance(valor, list):
        return [_sanitizada(item) for item in valor]
    if isinstance(valor, dict):
        return {chave: _sanitizada(item) for chave, item in valor.items()}
    return valor


def _sugestao_final(saida: dict, relato: str) -> dict:
    """A saída validada, sanitizada, com o assunto numa linha e o alerta do
    sistema quando o relato traz instrução ao agente."""
    sugestao = _sanitizada(saida)
    sugestao["assunto"] = " ".join(sugestao["assunto"].split())[:TAMANHO_DO_ASSUNTO]
    if triagem_do_agente.tem_instrucao_ao_agente(relato):
        sugestao["alertas"] = [*sugestao["alertas"], triagem_do_agente.ALERTA_DE_INSTRUCAO]
    return sugestao


def classificar_pelo_agente_do_nucleo(
    cliente, entrada: dict, *, modelo: str, reservar: Callable[[], bool] = lambda: True
) -> Triagem:
    """A triagem de uma notificação já no formato de entrada do Anexo B. Cada
    tentativa pede uma vaga a `reservar` antes de chamar o modelo."""
    texto = triagem_do_agente.montar_notificacao(entrada)
    # As guardas do sistema (menção a morte, instrução ao agente) leem o que
    # o agente lê: o relato e as respostas de quem notificou (issue #1991).
    lido = "\n".join(parte for parte in (entrada["relato"], entrada.get("esclarecimentos")) if parte)
    triagem = Triagem()
    for _ in range(TENTATIVAS):
        if not reservar():
            triagem.motivo_manual = TETO
            return triagem
        triagem.tentativas += 1
        try:
            saida = _perguntar_ao_agente_do_nucleo(cliente, modelo, _mensagem(texto, triagem.violacoes))
        except Exception as exc:
            logger.warning("[NSP] Agente de triagem não respondeu (%s)", type(exc).__name__)
            triagem.motivo_manual = AGENTE_FORA
            return triagem
        triagem.violacoes = ["formato:objeto"] if saida is None else triagem_do_agente.validar_saida(saida, lido)
        if not triagem.violacoes:
            triagem.sugestao = _sugestao_final(saida, lido)
            return triagem
    triagem.motivo_manual = VALIDACAO
    return triagem


# ═══════════════════════════════════════════════════════════════════════════
# A triagem no app: a notificação recém-registrada
# ═══════════════════════════════════════════════════════════════════════════

_CAMPOS_DA_NOTIFICACAO = (
    "id, relato, setor_id, data_ocorrencia, turno, chegou_ao_paciente, grave_ou_morte, "
    "percebido_ou_reclamacao, notificante_nome, notificante_contato, estado"
)


def agente_ligado() -> bool:
    """Ligado na configuração e com chave: sem chave (ambiente local e CI) o
    agente fica fora, e a notificação entra para classificar manualmente."""
    return settings.nsp_agente_ligado and bool(settings.anthropic_api_key)


def _cliente_do_nucleo() -> ClienteDaAnthropic:
    return ClienteDaAnthropic(max_retries=0, timeout=TEMPO_LIMITE_S)


def agendar_triagem_do_nucleo(tarefas, supabase, notificacao_id: str) -> None:
    """Põe a triagem da notificação recém-registrada para depois da resposta."""
    tarefas.add_task(_triar_notificacao_do_nucleo_fora_do_loop, supabase, notificacao_id)


async def _triar_notificacao_do_nucleo_fora_do_loop(supabase, notificacao_id: str) -> None:
    await ai_processor.chamar_ia_fora_do_loop(triar_notificacao_do_nucleo, supabase, notificacao_id)


def _reservar_chamada_do_nucleo(supabase) -> bool:
    """Uma vaga da cota do Núcleo. Só um `true` explícito do banco libera."""
    dados = supabase.rpc(FUNCAO_DA_COTA, {"p_teto": TETO_DIARIO}).execute().data
    return isinstance(dados, list) and len(dados) == 1 and dados[0].get("reservada") is True


def _nome_do_setor(supabase, setor_id: str | None) -> str | None:
    if not setor_id:
        return None
    linhas = supabase.table("setores").select("nome").eq("id", setor_id).limit(1).execute().data
    return linhas[0]["nome"] if linhas else None


def _linha_de_triagem(notificacao_id: str, triagem: Triagem, modelo: str) -> dict:
    sugestao = triagem.sugestao
    evento = sugestao["evento_que_nunca_deveria_ocorrer"]
    return {
        "notificacao_id": notificacao_id,
        "autor_tipo": "agente",
        "assunto": sugestao["assunto"],
        "natureza": sugestao["natureza"],
        "grau_de_dano": sugestao["grau_de_dano"],
        "categoria": sugestao["categoria"],
        "incidente": sugestao["incidente"],
        "evento_situacao": evento["situacao"],
        "evento_item": evento["item"] if evento["situacao"] != "nao" else None,
        "evento_motivo": evento["motivo"],
        "iras": sugestao["iras"],
        "risco_de_imagem": sugestao["risco_de_imagem"],
        "protocolo_basico": sugestao["protocolo_basico"],
        "canais": sugestao["canais"],
        "motivo_do_encaminhamento": sugestao.get("motivo_do_encaminhamento") or None,
        "faixa": sugestao["faixa"],
        "revisao": sugestao["revisao"],
        "justificativa": sugestao["justificativa"],
        "confianca": sugestao["confianca"],
        "motivo_da_confianca": sugestao["motivo_da_confianca"],
        "alertas": sugestao["alertas"],
        "perguntas_ao_notificante": sugestao["perguntas_ao_notificante"],
        "prompt_versao": versao(PROMPT),
        "base_versao": versao(BASE),
        "modelo": modelo,
        "tentativas": triagem.tentativas,
    }


def _marcar_para_classificar_manualmente(supabase, notificacao_id: str, motivo: str) -> None:
    supabase.table("nsp_notificacoes").update(
        {"classificar_manualmente": True, "motivo_classificar_manualmente": motivo}
    ).eq("id", notificacao_id).execute()


def _ler_a_notificacao_do_nucleo(supabase, notificacao_id: str) -> dict | None:
    linhas = (
        supabase.table("nsp_notificacoes")
        .select(_CAMPOS_DA_NOTIFICACAO)
        .eq("id", notificacao_id)
        .limit(1)
        .execute()
        .data
    )
    return linhas[0] if linhas else None


def _rodar_o_agente_do_nucleo(
    supabase, linha: dict, texto_dos_esclarecimentos: str = "", ainda_vale: Callable[[], bool] = lambda: True
) -> str | None:
    """Roda o agente na notificação e grava a linha de triagem dele, se
    `ainda_vale()` depois da resposta do modelo. Devolve None quando gravou,
    ou o motivo de não ter gravado."""
    entrada = triagem_do_agente.entrada_da_notificacao(
        linha, setor=_nome_do_setor(supabase, linha.get("setor_id")), esclarecimentos=texto_dos_esclarecimentos
    )
    modelo = settings.nsp_agente_modelo
    triagem = classificar_pelo_agente_do_nucleo(
        _cliente_do_nucleo(), entrada, modelo=modelo, reservar=lambda: _reservar_chamada_do_nucleo(supabase)
    )
    if triagem.sugestao is None:
        return triagem.motivo_manual or AGENTE_FORA
    if not ainda_vale():
        return LEITURA_SUPERADA
    supabase.table("nsp_triagens").insert(_linha_de_triagem(linha["id"], triagem, modelo)).execute()
    return None


def triar_notificacao_do_nucleo(supabase, notificacao_id: str) -> None:
    """Triagem da notificação recém-registrada. Nunca levanta: a notificação
    já existe e já tem protocolo. Toda saída que não é a linha de triagem do
    agente deixa a notificação marcada "classificar manualmente"."""
    motivo = AGENTE_FORA
    try:
        linha = _ler_a_notificacao_do_nucleo(supabase, notificacao_id)
        if linha and agente_ligado():
            motivo = _rodar_o_agente_do_nucleo(supabase, linha)
            if motivo is None:
                return
            logger.warning("[NSP] Notificação %s para classificar manualmente (%s)", notificacao_id, motivo)
    except Exception as exc:
        logger.warning("[NSP] Triagem do agente falhou na notificação %s (%s)", notificacao_id, type(exc).__name__)
    try:
        _marcar_para_classificar_manualmente(supabase, notificacao_id, motivo)
    except Exception as exc:
        logger.error("[NSP] Falha ao marcar a notificação %s para classificar (%s)", notificacao_id, type(exc).__name__)


# ═══════════════════════════════════════════════════════════════════════════
# A resposta de quem notificou às perguntas de esclarecimento (issue #1991)
# ═══════════════════════════════════════════════════════════════════════════


def agendar_triagem_com_esclarecimentos(tarefas, supabase, notificacao_id: str) -> None:
    """Põe a nova leitura do agente, com as respostas, para depois da resposta."""
    tarefas.add_task(_triar_com_esclarecimentos_fora_do_loop, supabase, notificacao_id)


async def _triar_com_esclarecimentos_fora_do_loop(supabase, notificacao_id: str) -> None:
    await ai_processor.chamar_ia_fora_do_loop(triar_de_novo_com_esclarecimentos, supabase, notificacao_id)


def triar_de_novo_com_esclarecimentos(supabase, notificacao_id: str) -> None:
    """O agente lê a notificação de novo, com as respostas de quem notificou,
    e grava uma linha de triagem nova. Só antes da confirmação da triagem, e
    gasta a cota do dia como a primeira leitura. Nunca levanta, e a falha não
    marca "classificar manualmente": a sugestão anterior continua valendo."""
    try:
        linha = _ler_a_notificacao_do_nucleo(supabase, notificacao_id)
        if not linha or not agente_ligado() or esclarecimentos.triagem_confirmada(linha):
            return
        texto = esclarecimentos.texto_para_o_agente(supabase, notificacao_id)

        def _ainda_vale() -> bool:
            # O modelo leva até dois minutos: a triagem pode ter sido
            # confirmada, ou outra resposta ter chegado, e aí a leitura que
            # roda por causa dela é a que vale.
            atual = _ler_a_notificacao_do_nucleo(supabase, notificacao_id)
            return (
                atual is not None
                and not esclarecimentos.triagem_confirmada(atual)
                and esclarecimentos.texto_para_o_agente(supabase, notificacao_id) == texto
            )

        motivo = _rodar_o_agente_do_nucleo(supabase, linha, texto, _ainda_vale)
        if motivo is not None:
            logger.warning("[NSP] A nova leitura da notificação %s ficou sem sugestão (%s)", notificacao_id, motivo)
    except Exception as exc:
        logger.warning("[NSP] Nova leitura do agente falhou na notificação %s (%s)", notificacao_id, type(exc).__name__)
