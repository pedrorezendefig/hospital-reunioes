"""Inferência da Natureza de um Setor a partir do nome (ADR 0018).

A Natureza (assistencial, administrativa, apoio) orienta qual corpo de normas
o agente de Elaboração evoca ao redigir os POPs de um Setor. Aqui vive a
heurística determinística por palavra-chave que SUGERE a Natureza no cadastro
(do mesmo jeito que a sigla é sugerida), consumida pelo endpoint de sugestão e,
via UI, pré-preenchida no formulário do Setor.

Este módulo é a fonte viva da verdade da heurística. A migration 054 congela um
retrato dela em SQL para o backfill dos Setores existentes; qualquer evolução
começa aqui. É um módulo raso de propósito: trocar a heurística por uma
classificação via IA no futuro não exige tocar em quem chama.

Por que não há lista de palavras "assistencial": num hospital, o Setor é
assistencial por padrão (cuidado ao paciente é o caso comum). A heurística só
DESVIA do assistencial quando o nome traz um sinal claro de administrativa
(faturamento, financeiro, RH, compras, recepção...) ou de apoio (higienização,
manutenção, almoxarifado, CME, esterilização, lavanderia, nutrição, TI...). Sem
esse sinal, cai no default explícito 'assistencial'. Um erro de inferência é
barato: o campo é editável e o agente ainda refina pelo objetivo (ADR 0018).
"""

from __future__ import annotations

import re
import unicodedata

from app.models.pops_schemas import NaturezaSetor

# Palavras-chave já sem acento e em minúsculas (o nome é normalizado do mesmo
# jeito antes de casar). Casamos como palavra inteira (fronteira \b) para os
# acrônimos curtos (rh, cme, ti) não baterem por dentro de outra palavra (o
# "ti" de "administrativo", por exemplo).
_ADMINISTRATIVA: tuple[str, ...] = (
    "faturamento",
    "cobranca",
    "financeiro",
    "financas",
    "contabilidade",
    "contabil",
    "tesouraria",
    "recursos humanos",
    "rh",
    "departamento de pessoal",
    "gestao de pessoas",
    "compras",
    "suprimentos",
    "recepcao",
    "administracao",
    "administrativo",
    "administrativa",
    "juridico",
    "comercial",
    "marketing",
    "ouvidoria",
)

_APOIO: tuple[str, ...] = (
    "higienizacao",
    "higiene",
    "limpeza",
    "zeladoria",
    "manutencao",
    "engenharia",
    "infraestrutura",
    "predial",
    "almoxarifado",
    "estoque",
    "logistica",
    "cme",
    "esterilizacao",
    "central de material",
    "lavanderia",
    "rouparia",
    "nutricao",
    "dietetica",
    "cozinha",
    "refeitorio",
    "ti",
    "tecnologia da informacao",
    "informatica",
    "transporte",
    "portaria",
)


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acento e espaços colapsados.

    Espelha o pré-tratamento do backfill SQL (unaccent + lower): é o que torna
    a inferência insensível a acento e maiúsculas ("Manutenção" casa "manutencao").
    """
    decomposto = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def _compilar(termos: tuple[str, ...]) -> re.Pattern[str]:
    """Um regex de alternância com fronteira de palavra para o conjunto de termos."""
    alternativas = "|".join(re.escape(termo) for termo in termos)
    return re.compile(rf"\b(?:{alternativas})\b")


_ADMINISTRATIVA_RE = _compilar(_ADMINISTRATIVA)
_APOIO_RE = _compilar(_APOIO)


def inferir_natureza(nome: str) -> NaturezaSetor:
    """Sugere a Natureza de um Setor a partir do nome (heurística por palavra-chave).

    Precedência determinística administrativa > apoio > assistencial: um sinal de
    administrativa vence um de apoio no nome (raro coexistirem; a escolha é fixa e
    o campo é editável). Sem nenhum sinal, retorna o default 'assistencial', o caso
    comum de um hospital (ADR 0018).
    """
    texto = _normalizar(nome)
    if _ADMINISTRATIVA_RE.search(texto):
        return "administrativa"
    if _APOIO_RE.search(texto):
        return "apoio"
    return "assistencial"
