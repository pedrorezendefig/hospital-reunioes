"""Regras puras da aba Tecnologia (PRD #634, ADR 0050).

Sem I/O: quem fala com o Supabase e o router. O que mora aqui e o que precisa
ser verdade independentemente de onde a linha veio, e por isso pode ser testado
direto, sem dubles.

Nesta fatia (issue #636) sao duas regras, as duas sobre Produto:

- quem tem acesso a aba (participante ativo com Super admin). E a MESMA lista
  para dono de Produto, responsavel de Demanda e @mencao, entao ela nasce como
  funcao unica em vez de repetir o filtro em cada endpoint;
- Produto ativo nao fica sem dono. Sem dono, toda Demanda daquele Produto
  nasceria sem ninguem (ADR 0050, decisao 4).
"""

from __future__ import annotations

from typing import Any

from app.dependencies import is_super_admin

# O motivo que a tela mostra quando a API recusa. Uma frase so, no lugar de
# uma por endpoint: e ela que o Super admin le no toast.
MOTIVO_PRODUTO_ATIVO_SEM_DONO = "Produto ativo precisa de dono. Escolha um dono ou desative o Produto."
MOTIVO_DONO_SEM_ACESSO = "O dono precisa ser um participante ativo com Super admin."


def e_pessoa_da_aba(participante: dict[str, Any] | None) -> bool:
    """True se este participante tem acesso a aba Tecnologia.

    Ativo E Super admin (ADR 0050, decisao 2: o eixo de permissao e o
    `is_super_admin` que ja existe, sem perfil proprio).

    `ativo` ausente ou NULL conta como ativo: a coluna nasceu com DEFAULT TRUE
    na migration 001 e linhas antigas podem nao ter valor. Tratar NULL como
    inativo esconderia da lista gente que usa o app todo dia.
    """
    if not participante:
        return False
    if participante.get("ativo") is False:
        return False
    return is_super_admin(participante)


def produto_ativo_sem_dono(*, ativo: bool, dono_id: str | None) -> bool:
    """True quando o Produto fica ativo e sem ninguem respondendo por ele."""
    return bool(ativo) and not dono_id


def edicao_deixa_produto_ativo_sem_dono(
    *,
    antes_ativo: bool,
    antes_dono: str | None,
    depois_ativo: bool,
    depois_dono: str | None,
) -> bool:
    """True quando a edicao CRIA o estado ruim, e nao quando ela o herda.

    O criterio da issue #636 e "recusa DEIXAR um Produto ativo sem dono". Isso
    e diferente de "recusa qualquer edicao em Produto ativo sem dono", e a
    diferenca nao e teorica: os sete Produtos do seed nascem ativos e SEM dono,
    porque e a propria migration que manda cria-los assim. Uma guarda que
    olhasse so o estado final devolveria 422 ao renomear "Ana" na primeira
    abertura, culpando o Super admin por uma falta de dono que ele nao causou,
    e travaria o criterio "cria, renomeia e desativa um Produto pela tela"
    justo no estado inicial do sistema.

    Quem cobra o dono desses sete e a tela, que marca o Produto ativo sem dono.
    """
    if not produto_ativo_sem_dono(ativo=depois_ativo, dono_id=depois_dono):
        return False
    return not produto_ativo_sem_dono(ativo=antes_ativo, dono_id=antes_dono)


# ─── A maquina de estados da Demanda (issue #637) ────────────────────────────

MOTIVO_PRODUTO_SEM_DONO = (
    "Produto sem dono nao recebe Demanda nova: ela nasceria sem responsavel. Defina o dono do Produto e tente de novo."
)
MOTIVO_PRODUTO_INATIVO = "Produto inativo nao recebe Demanda nova. Escolha outro Produto ou reative este."
MOTIVO_RESPONSAVEL_SEM_ACESSO = "O responsavel precisa ser um participante ativo com Super admin."

ESTADOS: tuple[str, ...] = ("nova", "em_andamento", "aguardando", "concluida", "cancelada")

# O rotulo que a gente le, na tela e no texto da linha de movimento. O banco
# guarda o valor sem acento (CHECK da migration 102); a pessoa le "Concluída".
ESTADO_ROTULO: dict[str, str] = {
    "nova": "Nova",
    "em_andamento": "Em andamento",
    "aguardando": "Aguardando",
    "concluida": "Concluída",
    "cancelada": "Cancelada",
}

TIPOS: tuple[str, ...] = (
    "decisao",
    "informacao",
    "terceiro",
    "ajuste",
    "novo",
    "defeito",
    "consultoria",
)

PRIORIDADES: tuple[str, ...] = ("baixa", "normal", "alta")

# Quem pode ir para onde (PRD #634, ADR 0050, decisao 5). O que NAO esta aqui e
# recusado com 422, e a lista de proibidas do teste e o complemento desta.
#
# Tres coisas que a tabela diz de proposito:
#
# - ninguem volta para `nova`: a coluna e o comeco, nao um lugar para onde se
#   retrocede. A Demanda que voltou atras cai em `em_andamento`;
# - nenhum estado leva a si mesmo: mover para a coluna onde a Demanda ja esta
#   nao e movimento, e clique repetido, e gravaria uma linha de movimento
#   dizendo que algo mudou quando nada mudou;
# - de `concluida` nao se pula para `cancelada` (nem o contrario) sem reabrir:
#   trocar o desfecho e uma decisao, e passa por `em_andamento`.
TRANSICOES: dict[str, frozenset[str]] = {
    "nova": frozenset({"em_andamento", "aguardando", "concluida", "cancelada"}),
    "em_andamento": frozenset({"aguardando", "concluida", "cancelada"}),
    "aguardando": frozenset({"em_andamento", "concluida", "cancelada"}),
    "concluida": frozenset({"em_andamento"}),
    "cancelada": frozenset({"em_andamento"}),
}


def transicao_permitida(de: str, para: str) -> bool:
    """True se a Demanda pode andar de `de` para `para`."""
    return para in TRANSICOES.get(de, frozenset())


def motivo_transicao_invalida(de: str, para: str) -> str:
    """A frase que a tela mostra quando a API recusa o movimento.

    Duas causas, porque sao duas e o codigo as distingue: clicar na coluna onde
    a Demanda ja esta, e pedir um caminho que a maquina nao tem. Uma frase so
    para as duas mandaria quem clicou duas vezes procurar defeito onde nao ha.
    """
    aqui = ESTADO_ROTULO.get(de, de)
    if de == para:
        return f"A Demanda já está em {aqui}."
    la = ESTADO_ROTULO.get(para, para)
    destinos = sorted(ESTADO_ROTULO[d] for d in TRANSICOES.get(de, frozenset()))
    return f"De {aqui} não dá para ir direto a {la}. De {aqui}, os destinos são: {', '.join(destinos)}."


def carimbos_da_transicao(*, para: str, ator_id: str, agora: str) -> dict[str, str | None]:
    """Os quatro campos de desfecho depois do movimento.

    Concluir e cancelar carimbam data e pessoa; qualquer outro destino limpa os
    quatro. Devolver sempre os quatro (e nao so o que mudou) e o que faz reabrir
    apagar o carimbo antigo: um update parcial deixaria `concluida_em`
    preenchido numa Demanda que voltou para `em_andamento`, e o Historico diria
    que ela foi concluida numa data em que nao foi.
    """
    vazio: dict[str, str | None] = {
        "concluida_em": None,
        "concluida_por": None,
        "cancelada_em": None,
        "cancelada_por": None,
    }
    if para == "concluida":
        return {**vazio, "concluida_em": agora, "concluida_por": ator_id}
    if para == "cancelada":
        return {**vazio, "cancelada_em": agora, "cancelada_por": ator_id}
    return vazio


def texto_movimento_estado(*, autor_nome: str, para: str) -> str:
    """O texto legivel da linha de movimento de coluna.

    Montado aqui, e nao na tela: o de/para estruturado fica gravado na linha,
    mas quem escreve a frase e o backend, para o fio ser o mesmo em qualquer
    lugar que o leia (tela, e-mail e o "Copiar para IA" das fatias seguintes).
    """
    return f"{autor_nome} moveu para {ESTADO_ROTULO.get(para, para)}"


def texto_movimento_responsavel(*, autor_nome: str, para_nome: str) -> str:
    """O texto legivel da linha de movimento de responsavel."""
    return f"{autor_nome} atribuiu a {para_nome}"
