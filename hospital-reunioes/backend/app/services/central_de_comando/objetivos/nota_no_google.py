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
from app.services import ouvidoria_nota_google
from app.services.central_de_comando import periodo
from app.services.central_de_comando.objetivos.catalogo import objetivo_por_id

IDENTIFICADOR = "google-reputacao"


def ler(supabase) -> dict:
    """O payload da lente: o Objetivo e o resumo do mês. Sem a chave da Places
    API, o resumo diz que a nota não está sendo medida, sem número."""
    objetivo = objetivo_por_id(IDENTIFICADOR)
    return {
        "objetivo": {"id": objetivo.id, "nome": objetivo.nome, "descricao": objetivo.descricao},
        "reputacao": ouvidoria_nota_google.resumo_do_mes(
            supabase, periodo.hoje_utc(), medida=bool(settings.google_places_api_key)
        ),
    }
