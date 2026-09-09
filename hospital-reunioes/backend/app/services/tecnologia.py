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
    """True quando o Produto ficaria ativo e sem ninguem respondendo por ele."""
    return bool(ativo) and not dono_id
