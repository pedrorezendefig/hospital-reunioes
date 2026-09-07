"""Devolução à Ouvidoria (issue #600, PRD #598, ADR 0048).

A área que recebeu um caso que não é dela o devolve ao ouvidor pelo próprio
link do email, com o motivo em texto livre. Este módulo é o único lugar que
sabe o que vale como motivo e como ele entra na trilha: quem escreve chama
`observacao_da_devolucao`, e o prefixo fixo é o que o Dossiê reconhece depois
para mostrar "Devolvido pela área <setor>".

Irmão de `ouvidoria_respostas`, com uma diferença de propósito: aqui não há
piso. "Não é do meu setor, é do Centro Médico" é curto por natureza, e exigir
tamanho empurraria o responsável a encher linguiça num campo que existe só
para o ouvidor saber para onde mandar.
"""

from __future__ import annotations

from app.utils.text_sanitizer import sanitizar_travessao, sem_invisiveis

# O rótulo que abre a observação do movimento, e o que a fatia do Dossiê vai
# reconhecer para separar esta volta de qualquer outra transição para
# `em_classificacao`.
_PREFIXO = "Devolvido pela área"
_SEPARADOR = ": "

# O mesmo teto dos outros textos da área (`ouvidoria_respostas` e a
# justificativa da prorrogação), pelo mesmo motivo: o texto vai para a trilha
# IMUTÁVEL, e um POST enorme deixaria o Dossiê daquele caso impossível de
# abrir. O teto do middleware de corpo é rede de segurança de 100 MB, não
# limite fino.
MAXIMO_DE_CARACTERES = 10_000

_MAXIMO_ESCRITO = f"{MAXIMO_DE_CARACTERES:,}".replace(",", ".")

RECUSA_VAZIA = "Diga por que este caso não é da sua área: sem o motivo, a Ouvidoria não sabe para onde encaminhar."

RECUSA_LONGA = f"O motivo passou de {_MAXIMO_ESCRITO} caracteres. Resuma por que o caso não é da sua área."


def texto_do_motivo(texto: str) -> str:
    """O motivo como ele fica gravado na trilha.

    Uma normalização só, usada pela validação e pela escrita, para o que foi
    medido ser exatamente o que fica gravado: sem invisível, sem travessão
    (ADR 0013) e aparado, na MESMA ordem e pela MESMA peneira da resposta da
    área. O invisível vem primeiro porque o `strip` não o enxerga, e um deles
    na ponta impediria o aparo de chegar ao espaço."""
    return sanitizar_travessao(sem_invisiveis(texto)).strip()


def motivo_de_recusa(texto: str) -> str | None:
    """Por que este texto não vale como motivo da devolução, ou None quando
    vale. O texto devolvido é o que o responsável lê na tela.

    O teto olha o texto COMO CHEGOU, antes de normalizar, pelo mesmo motivo de
    `ouvidoria_respostas.motivo_de_recusa`: normalizar dezenas de MB caractere
    a caractere só para depois recusá-los é o custo que o teto evita."""
    if len(texto) > MAXIMO_DE_CARACTERES:
        return RECUSA_LONGA
    if not texto_do_motivo(texto):
        return RECUSA_VAZIA
    return None


def observacao_da_devolucao(setor: str | None, motivo: str) -> str:
    """A observação do movimento que a trilha guarda.

    O setor entra na frase porque é ele que a Ouvidoria lê para saber quem
    devolveu, e o caso pode ser reacionado para outra área logo depois: lido
    meses adiante, o `setor` corrente do caso já não diria de onde a volta
    veio."""
    return f"{_PREFIXO} {setor or 'sem setor'}{_SEPARADOR}{motivo}"
