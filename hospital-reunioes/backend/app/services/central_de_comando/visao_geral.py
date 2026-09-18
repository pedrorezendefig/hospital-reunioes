"""A tela Visão Geral da Central de Comando: o payload inteiro que ela desenha.

O backend devolve um payload por tela, e a tela não compõe chamada nem faz
conta (PRD #809): a variação já vem calculada, e cada número vem com a janela
de datas a que se refere.

Um bloco da tela, uma chave do payload. Nesta fatia (#814) são dois:

- `periodo`: o período escolhido, quantos dias ele tem e as datas do período e
  do anterior. É o que a tela usa para dizer "últimos 28 dias" e o que quem
  confere com o Google usa para comparar o mesmo intervalo.
- `visitantes`: o número-manchete, o do período anterior e a variação.

As fatias seguintes acrescentam as suas chaves (o frescor, o contexto do
número-manchete, o Instagram num relance, os Objetivos em foco e "O que vem por
aí"), cada uma com a sua função `_bloco_*`, sem mexer nas que já existem.
"""

from __future__ import annotations

from app.services.central_de_comando import periodo as periodos
from app.services.central_de_comando import provedor_google
from app.services.central_de_comando.periodo import Periodo, dias_do_periodo
from app.services.central_de_comando.variacao import variacao_relativa


def montar(periodo: Periodo) -> dict:
    """O payload da Visão Geral. Falha da fonte sobe como exceção do provedor,
    e a rota a traduz em 502 ou 503: nunca um payload com zero no lugar."""
    visitantes = provedor_google.visitantes_comparados(periodo, periodos.hoje_utc())
    return {
        "periodo": _bloco_periodo(periodo, visitantes),
        "visitantes": _bloco_visitantes(visitantes),
    }


def _bloco_periodo(periodo: Periodo, visitantes: provedor_google.VisitantesComparados) -> dict:
    return {
        "chave": periodo,
        "dias": dias_do_periodo(periodo),
        "atual": visitantes.intervalo_atual.como_dict(),
        "anterior": visitantes.intervalo_anterior.como_dict(),
    }


def _bloco_visitantes(visitantes: provedor_google.VisitantesComparados) -> dict:
    return {
        "atual": visitantes.atual,
        "anterior": visitantes.anterior,
        "variacao": variacao_relativa(visitantes.atual, visitantes.anterior),
    }
