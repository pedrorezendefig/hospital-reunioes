"""Os tetos do que os três chats de IA recebem (issue #893).

`chat-correcao`, `ata-guiada/chat` e `pops/{id}/elaboracao/chat` só tinham o
limite do corpo do app inteiro (100 MB). Com a IA fora do loop (#773), até 16
montagens de prompt correm juntas, e cada uma copia o texto várias vezes
(corpo, bloco do prompt, `render_prompt`, JSON do SDK): dez turnos de 100 MB
num minuto, dentro do rate limit, levavam o processo único a estourar a
memória, e o `/health` caía junto.

Os tetos são iguais nas três rotas e folgados para o uso de verdade (uma
Transcrição ou um Documento de apoio colado). O que fecham é o abuso de dezenas
de MB.

A recusa sai daqui, e não de `max_length` do pydantic, no molde do
`assistente_tecnologia.motivo_rascunho_grande`: o pydantic responde ANTES da
rota com `detail` em LISTA, que a tela mostraria como JSON cru. Devolvendo a
frase, a recusa chega legível.
"""

from __future__ import annotations

import json

LIMITE_DE_MENSAGENS = 40
LIMITE_DA_MENSAGEM = 8000
LIMITE_DO_CAMPO_DE_APOIO = 200_000


def _milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


MOTIVO_MUITAS_MENSAGENS = (
    f"A conversa passou de {LIMITE_DE_MENSAGENS} mensagens, o máximo que o chat aceita de uma vez."
)
MOTIVO_MENSAGEM_GRANDE = (
    f"A mensagem passou de {_milhar(LIMITE_DA_MENSAGEM)} caracteres, o tamanho que o chat aceita. "
    "Encurte o texto e mande de novo."
)

# Uma frase por campo, e não uma só, porque o código SABE qual estourou: a do
# Documento de apoio diz o que fazer; nos outros três, quem escreve é a tela ou
# o agente, e a frase só nomeia o campo.
_TAMANHO_DO_CHAT = f"passou de {_milhar(LIMITE_DO_CAMPO_DE_APOIO)} caracteres, o tamanho que o chat aceita."
MOTIVO_CAMPO_GRANDE = {
    "section_context": f"A seção apontada {_TAMANHO_DO_CHAT}",
    "documento_apoio": (
        f"O Documento de apoio {_TAMANHO_DO_CHAT} Remova o documento e anexe um menor, ou só o trecho que importa."
    ),
    "rascunho": f"O rascunho {_TAMANHO_DO_CHAT}",
    "current_plan": f"O plano de correção {_TAMANHO_DO_CHAT}",
}


def _tamanho(valor) -> int:
    """Texto conta o texto; campo estruturado conta o JSON que vai ao prompt."""
    return len(valor) if isinstance(valor, str) else len(json.dumps(valor, ensure_ascii=False))


def motivo_corpo_grande(messages: list, **campos_de_apoio) -> str | None:
    """A frase de recusa quando o corpo do chat passa de um dos tetos, ou None.

    `campos_de_apoio` leva os campos da rota pelo nome do corpo (as chaves de
    `MOTIVO_CAMPO_GRANDE`); campo ausente vem como None e não conta.
    """
    if len(messages) > LIMITE_DE_MENSAGENS:
        return MOTIVO_MUITAS_MENSAGENS
    if any(len(m.content) > LIMITE_DA_MENSAGEM for m in messages):
        return MOTIVO_MENSAGEM_GRANDE
    for campo, valor in campos_de_apoio.items():
        if valor is not None and _tamanho(valor) > LIMITE_DO_CAMPO_DE_APOIO:
            return MOTIVO_CAMPO_GRANDE[campo]
    return None
