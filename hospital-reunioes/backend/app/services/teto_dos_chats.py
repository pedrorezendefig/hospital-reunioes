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


def _milhar(numero: int) -> str:
    return f"{numero:,}".replace(",", ".")


MOTIVO_MUITAS_MENSAGENS = (
    f"A conversa passou de {LIMITE_DE_MENSAGENS} mensagens, o máximo que o chat aceita de uma vez."
)
MOTIVO_MENSAGEM_GRANDE = (
    f"A mensagem passou de {_milhar(LIMITE_DA_MENSAGEM)} caracteres, o tamanho que o chat aceita. "
    "Encurte o texto e mande de novo."
)


def motivo_corpo_grande(messages: list) -> str | None:
    """A frase de recusa quando o corpo do chat passa de um dos tetos, ou None."""
    if len(messages) > LIMITE_DE_MENSAGENS:
        return MOTIVO_MUITAS_MENSAGENS
    if any(len(m.content) > LIMITE_DA_MENSAGEM for m in messages):
        return MOTIVO_MENSAGEM_GRANDE
    return None
