"""A lente do Objetivo "Melhorar a nota no Google" (issue #1619, ADR 0089).

Diferente das outras lentes, os números não vêm do Google Analytics nem do
Instagram, e não passam pelo cache de 1 hora: vêm do diário de Nota externa da
Ouvidoria, que o job semanal da Places API alimenta. É uma leitura do banco,
barata, e a tela mostra a data da última leitura em vez do frescor do cache.

O Objetivo é mensal e não tem seletor de período: a nota, as avaliações novas
do mês (diferença do total entre a primeira e a última leitura do mês) e a
tendência contra o fim do mês anterior.
"""

from __future__ import annotations

from app.config import settings
from app.services import ouvidoria_convite_google, ouvidoria_nota_google
from app.services.central_de_comando import periodo
from app.services.central_de_comando.objetivos.catalogo import objetivo_por_id
from app.services.central_de_comando.periodo import PERIODO_PADRAO, Periodo

IDENTIFICADOR = "google-reputacao"


def ler(supabase, periodo_escolhido: Periodo = PERIODO_PADRAO) -> dict:
    """O payload da lente: o Objetivo, o resumo do mês e o teste do convite ao
    Google (issue #1625). Sem a chave da Places API, o resumo diz que a nota
    não está sendo medida, sem número.

    O resumo é mensal; o teste do convite é por período, o mesmo seletor das
    outras lentes: convites, cliques e taxa por cartaz ao lado da nota, e o
    aviso de reavaliar depois de 60 dias (ADR 0089, decisão 7)."""
    objetivo = objetivo_por_id(IDENTIFICADOR)
    hoje = periodo.hoje_utc()
    intervalo = periodo.intervalo_atual(periodo_escolhido, hoje)
    return {
        "objetivo": {"id": objetivo.id, "nome": objetivo.nome, "descricao": objetivo.descricao},
        "reputacao": ouvidoria_nota_google.resumo_do_mes(supabase, hoje, medida=bool(settings.google_places_api_key)),
        "convite": {
            "periodo": periodo_escolhido,
            **ouvidoria_convite_google.numeros_do_teste(
                supabase, intervalo.inicio, intervalo.fim, hoje, periodo.FUSO_DO_HOSPITAL
            ),
        },
    }
