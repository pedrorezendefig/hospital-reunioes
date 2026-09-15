"""Redirecionamento pelo ouvidor (issue #708, PRD #706, ADR 0055).

O ouvidor tira a manifestação de uma área e a aciona em outra numa requisição
só, com motivo obrigatório. Este módulo é o único lugar que sabe o que vale
como motivo, como ele entra na trilha e de quais estados o ato pode partir:
quem escreve chama `observacao_do_redirecionamento`, e o prefixo fixo é o que o
Dossiê vai reconhecer depois para mostrar "Redirecionado pelo ouvidor (de
<setor>)".

Irmão de `ouvidoria_devolucao_a_ouvidoria`, com a mesma peneira de texto e o
mesmo teto, por uma razão de simetria que vale escrever: o motivo dos dois vai
para a MESMA coluna da MESMA trilha imutável, e é o prefixo (não o tamanho, não
a origem) que separa o ato da área do ato do ouvidor. A diferença é quem
escreve e para onde o caso vai: lá a área diz que o caso não é dela e o caso
volta para a fila do ouvidor; aqui o ouvidor diz para onde o caso vai e o caso
sai da área na mesma requisição em que entra na outra.
"""

from __future__ import annotations

from app.services.ouvidoria_estados import ORIGENS_DO_REDIRECIONAMENTO
from app.utils.text_sanitizer import sanitizar_travessao, sem_invisiveis

# O rótulo que abre a observação do movimento de saída. É por ele que o Dossiê
# separa esta volta da Devolução à Ouvidoria, que escreve "Devolvido pela área
# <setor>" na mesma coluna: sem prefixos distintos, a contagem de devoluções
# passaria a incluir os redirecionamentos do próprio ouvidor (ADR 0055).
_PREFIXO = "Redirecionado pelo ouvidor"
_SEPARADOR = ": "

# O mesmo teto dos textos da área (`ouvidoria_respostas`, a justificativa da
# prorrogação e o motivo da Devolução à Ouvidoria), pelo mesmo motivo: o texto
# vai para a trilha IMUTÁVEL, e um POST enorme deixaria o Dossiê daquele caso
# impossível de abrir.
MAXIMO_DE_CARACTERES = 10_000

_MAXIMO_ESCRITO = f"{MAXIMO_DE_CARACTERES:,}".replace(",", ".")

RECUSA_VAZIA = (
    "Diga por que este caso vai para outra área: sem o motivo, a trilha não conta por que ele saiu de onde estava."
)

RECUSA_LONGA = f"O motivo passou de {_MAXIMO_ESCRITO} caracteres. Resuma por que o caso vai para outra área."

# As recusas por estado. Cada uma diz o que fazer ANTES de redirecionar, porque
# a tela oferece o botão a partir da fila e o estado pode ter mudado entre o
# desenho da lista e o clique.
RECUSA_PAUSADO = (
    "Este caso está pausado à espera do manifestante. Retome o caso antes de redirecionar: "
    "o relógio parado da pausa e o prazo cheio da área nova não se misturam na mesma ação."
)
RECUSA_EM_CLASSIFICACAO = (
    "Este caso não está com nenhuma área: ele espera o despacho da Ouvidoria. "
    "Use Validar e acionar para escolher a área."
)
RECUSA_ENCERRADO = "Este caso está encerrado e não pode ser redirecionado. Para voltar à tramitação, use a reabertura."
RECUSA_SEM_AREA = (
    "Este caso ainda não foi para nenhuma área, então não há de onde redirecioná-lo. "
    "Use Validar e acionar para escolher a área."
)

_RECUSA_POR_ESTADO = {
    "aguardando_manifestante": RECUSA_PAUSADO,
    "em_classificacao": RECUSA_EM_CLASSIFICACAO,
    "encerrado": RECUSA_ENCERRADO,
    "novo": RECUSA_SEM_AREA,
}


def texto_do_motivo(texto: str) -> str:
    """O motivo como ele fica gravado na trilha.

    Uma normalização só, usada pela validação e pela escrita, para o que foi
    medido ser exatamente o que fica gravado: sem invisível, sem travessão
    (ADR 0013) e aparado, na MESMA ordem e pela MESMA peneira do motivo da
    Devolução à Ouvidoria. O invisível vem primeiro porque o `strip` não o
    enxerga, e um deles na ponta impediria o aparo de chegar ao espaço."""
    return sanitizar_travessao(sem_invisiveis(texto)).strip()


def motivo_de_recusa(texto: str) -> str | None:
    """Por que este texto não vale como motivo do redirecionamento, ou None
    quando vale. O texto devolvido é o que o ouvidor lê na tela.

    O teto olha o texto COMO CHEGOU, antes de normalizar, pelo mesmo motivo do
    módulo irmão: normalizar dezenas de MB caractere a caractere só para depois
    recusá-los é o custo que o teto evita."""
    if len(texto) > MAXIMO_DE_CARACTERES:
        return RECUSA_LONGA
    if not texto_do_motivo(texto):
        return RECUSA_VAZIA
    return None


def recusa_do_estado(estado: str | None) -> str | None:
    """Por que este caso não pode ser redirecionado agora, ou None quando pode.

    A régua é a lista de origens da máquina de estados, e não esta tabela de
    frases: estado que não está entre as origens é recusado mesmo sem frase
    própria, e a frase própria é só o que o ouvidor lê. Invertido (liberar o
    que a tabela não nomeia), um estado novo na máquina nasceria redirecionável
    sem ninguém decidir isso."""
    if estado in ORIGENS_DO_REDIRECIONAMENTO:
        return None
    return _RECUSA_POR_ESTADO.get(estado or "", RECUSA_SEM_AREA)


def observacao_do_redirecionamento(setor: str | None, motivo: str) -> str:
    """A observação do movimento de saída que a trilha guarda.

    O setor entra na frase porque o acionamento da área nova, na MESMA
    requisição, sobrescreve `setor` no caso: lido meses adiante, o setor
    corrente já não diria de onde o caso saiu. É a mesma razão pela qual a
    Devolução à Ouvidoria congela o setor na observação dela."""
    return f"{_PREFIXO} (de {setor or 'sem setor'}){_SEPARADOR}{motivo}"


# O `detalhe` da notificação que avisa a área ANTIGA (issue #709, ADR 0055,
# decisão 4). Ele guarda duas coisas e só: o protocolo e o setor de onde o caso
# saiu. O motivo NÃO entra, e a ausência é a decisão: o aviso diz que a demanda
# saiu, não por quê.
#
# O setor está aqui pela razão que decide a fatia inteira: o acionamento da área
# nova, na MESMA requisição, sobrescreve `setor` no caso. Lido do caso na hora
# do envio, o aviso diria à área antiga o nome da área NOVA, que é justamente o
# que o ADR 0055 manda não dizer ("sem motivo, sem dizer qual área"). Congelado
# aqui, o reenvio meses adiante manda a mesma frase que saiu no ato.
#
# O protocolo entra junto para a linha se bastar: é dela que o montador do email
# lê tudo o que mostra, e é ela que o ouvidor vê no Dossiê.
_PREFIXO_DO_AVISO = "Redirecionamento do protocolo"
_SEPARADOR_DO_AVISO = ", setor "


def detalhe_do_aviso(protocolo: str | None, setor: str | None) -> str:
    """O `detalhe` da notificação `redirecionamento_area`, congelado no ato."""
    return f"{_PREFIXO_DO_AVISO} {protocolo or ''}{_SEPARADOR_DO_AVISO}{setor or 'sem setor'}"


def protocolo_e_setor(detalhe: str | None) -> tuple[str | None, str | None]:
    """A frase acima de volta em duas partes, para o email mostrar cada uma no
    campo dela. `(None, None)` quando o texto não é um `detalhe` desta fatia.

    Texto que não começa pelo prefixo NÃO volta como setor, ao contrário do que
    o módulo irmão faz com o motivo: aqui o segundo valor vira o nome de uma
    área DENTRO de um email, e linha antiga (ou `detalhe` escrito por outro
    caminho) não pode virar área inventada na caixa de entrada de quem acabou de
    perder o caso. Quem chama trata o par vazio como erro, e a notificação fica
    visível em falha em vez de sair errada."""
    texto = (detalhe or "").strip()
    if not texto.startswith(f"{_PREFIXO_DO_AVISO} "):
        return None, None
    protocolo, separador, setor = texto[len(_PREFIXO_DO_AVISO) + 1 :].partition(_SEPARADOR_DO_AVISO)
    if not separador:
        return None, None
    return protocolo.strip() or None, setor.strip() or None
