"""O catálogo fechado dos Objetivos da Central de Comando (issue #820, ADR 0058).

Porte de `src/lib/objetivos/catalogo.ts`, adaptado ao domínio: adicionar um
Objetivo é adicionar um item aqui. O ícone é escolha de tela e mora no front; o
backend cuida do que a tela não compõe (nome, descrição, estado e números).

Dois Objetivos ainda não têm dado e nascem **em construção** (sem destino
navegável): a Área do site (o nome novo da ADR 0058, decisão 7) e a nota no
Google.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.central_de_comando.objetivos.tipos import ObjetivoId


@dataclass(frozen=True)
class Objetivo:
    """A entrada declarativa do catálogo: o que a galeria mostra de cada
    Objetivo. `em_construcao` é o Objetivo sem dado ainda, sem lente navegável."""

    id: ObjetivoId
    nome: str
    descricao: str
    em_construcao: bool = False


# O catálogo, na ordem do design. Os dois `em_construcao` são os sem montador.
OBJETIVOS: tuple[Objetivo, ...] = (
    Objetivo(
        id="site-visitantes",
        nome="Atrair mais visitantes pro site",
        descricao="Mais gente conhecendo o hospital pelo site.",
    ),
    Objetivo(
        id="instagram-seguidores",
        nome="Crescer no Instagram",
        descricao="Aumentar o número de seguidores da conta.",
    ),
    Objetivo(
        id="instagram-engajamento",
        nome="Aumentar o engajamento no Instagram",
        descricao="Mais gente curtindo, comentando e salvando.",
    ),
    Objetivo(
        id="site-area",
        nome="Levar mais gente para uma Área do site",
        descricao="Aumentar as visitas de uma área específica do site.",
        em_construcao=True,
    ),
    Objetivo(
        id="contatos",
        nome="Gerar mais contatos",
        descricao="Mais pessoas agendando e entrando em contato.",
    ),
    Objetivo(
        id="google-reputacao",
        nome="Melhorar a nota no Google",
        descricao="Melhorar a reputação e as avaliações no Google Meu Negócio.",
        em_construcao=True,
    ),
)


def objetivo_por_id(objetivo_id: str) -> Objetivo | None:
    """O Objetivo do catálogo pelo id, ou `None` se não existir."""
    return next((o for o in OBJETIVOS if o.id == objetivo_id), None)
