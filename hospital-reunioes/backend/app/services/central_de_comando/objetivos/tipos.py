"""Os tipos dos Objetivos da Central de Comando (issue #820, PRD #809).

Porte de `src/lib/objetivos/types.ts` do repositório antigo, adaptado ao
backend em Python e ao vocabulário do domínio (ADR 0058): a direção que a
diretoria quer é um **Objetivo**, sem alvo numérico, e o antigo objetivo de
encher uma unidade do hospital agora fala da **Área do site**.

Um Objetivo tem uma lente: os **numeros** que importam para ele e as
**sugestoes**, que sempre dizem o porque (o dado que as disparou). As regras de
sugestao sao funcoes puras que leem um `Contexto` (os numeros por chave e os
dados crus dos extras) e devolvem uma `Sugestao` ou nada.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal

from app.services.central_de_comando import provedor_google, provedor_instagram

# A chave canônica de cada Objetivo do catálogo (v1). O Objetivo da Área do site
# usa "site-area" (ADR 0058, decisão 7).
ObjetivoId = Literal[
    "site-visitantes",
    "instagram-seguidores",
    "instagram-engajamento",
    "site-area",
    "contatos",
    "google-reputacao",
]

# A chave canonica de cada regra de sugestao (v1).
RegraId = Literal[
    "queda-de-alcance",
    "queda-de-interacoes",
    "reels-rendem-mais",
    "dispositivo-celular-domina",
    "contatos-instrumentar",
]

# O tom de uma sugestao: atencao (algo caiu), positivo (algo rende) ou neutro.
Tom = Literal["atencao", "positivo", "neutro"]


@dataclass(frozen=True)
class Numero:
    """Um numero da lente de um Objetivo.

    - fluxo (Alcance, Visualizacoes, Visitantes): preencha `anterior`, e a tela
      desenha a variacao.
    - estoque (Seguidores): preencha `crescimento` (e `crescimento_anterior`), e
      a tela mostra "+N no periodo", sem variacao percentual.
    """

    chave: str
    rotulo: str
    valor: int
    anterior: int | None = None
    crescimento: int | None = None
    crescimento_anterior: int | None = None


@dataclass(frozen=True)
class Sugestao:
    """Uma sugestao pronta para a tela, sempre com o `porque` (o dado que a
    disparou): sugestao sem o dado que a justifica e proibida (ADR 0058)."""

    id: RegraId
    titulo: str
    detalhe: str
    porque: str
    tom: Tom


@dataclass(frozen=True)
class ContatoNaLente:
    """Um canal de contato com o estado honesto dele (medido, em construcao ou
    nao medido), como a tela Dados do Google ja o mostra. So o medido traz
    numero."""

    chave: str
    rotulo: str
    estado: str
    cliques: int | None = None


@dataclass(frozen=True)
class Extras:
    """Os dados crus que algumas regras leem alem dos numeros da lente: o
    Alcance (para cruzar com as Interacoes), as principais publicacoes, as
    visitas por dispositivo e os canais de contato."""

    reach: Numero | None = None
    publicacoes: tuple[provedor_instagram.Publicacao, ...] = ()
    dispositivos: tuple[provedor_google.VisitasNoDispositivo, ...] = ()
    canais: tuple[ContatoNaLente, ...] = ()


@dataclass(frozen=True)
class Contexto:
    """O que uma regra le: os numeros indexados por chave e os extras crus."""

    numeros: dict[str, Numero]
    extras: Extras = field(default_factory=Extras)


# Uma regra e uma funcao pura: le o contexto, devolve uma sugestao ou nada.
Regra = Callable[[Contexto], "Sugestao | None"]
