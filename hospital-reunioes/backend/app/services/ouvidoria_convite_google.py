"""O teste do convite ao Google no QR (issue #1625, PRD #1527, ADR 0089).

Quem dá nota 4 ou 5 no cartaz vê, na tela N3, o convite para avaliar o hospital
no Google. Só no QR, só com a chave geral (configuração da Ouvidoria) e a chave
do ponto ligadas, e as duas nascem desligadas (decisão 5). Só a diretoria
executiva liga e desliga, e cada mudança grava quem, quando, de e para
(decisão 6). O clique passa por uma rota do app que conta antes de redirecionar
ao link de avaliação da configuração (decisão 7).

O teste dura 60 dias, mas não se desliga sozinho: passado o prazo, a Central
mostra o aviso de reavaliar, e o convite continua até alguém desligar.
"""

from __future__ import annotations

import datetime as dt
import logging

from app.services.ouvidoria_avaliacoes import NOTA_QUE_PERGUNTA_RETORNO
from app.services.ouvidoria_avaliacoes import TABELA as TABELA_AVALIACOES

logger = logging.getLogger(__name__)

TABELA_CONFIG = "ouvidoria_config"
TABELA_AUDITORIA = "ouvidoria_convite_google_auditoria"
TABELA_PONTOS = "ouvidoria_pontos"

# O prazo do teste (seção 4.9 da especificação da Diretoria). Passado, a
# Central lembra de reavaliar; o convite não se desliga sozinho.
DIAS_DO_TESTE = 60


def nota_convida(nota: int) -> bool:
    """Só as notas 4 e 5 (ADR 0089, decisão 5): as que não perguntam retorno."""
    return nota > NOTA_QUE_PERGUNTA_RETORNO


def ler_config(supabase) -> dict:
    """A chave geral, a data em que foi ligada e o link de avaliação."""
    linhas = (
        supabase.table(TABELA_CONFIG)
        .select("google_teste_global, google_teste_ligado_em, google_review_url")
        .eq("id", True)
        .limit(1)
        .execute()
        .data
        or []
    )
    linha = linhas[0] if linhas else {}
    return {
        "global": bool(linha.get("google_teste_global")),
        "ligado_em": linha.get("google_teste_ligado_em"),
        "url": str(linha.get("google_review_url") or ""),
    }


def deve_convidar(supabase, ponto: dict, nota: int) -> bool:
    """O convite aparece para esta nota neste cartaz? A ordem poupa o banco: a
    nota baixa e o ponto desligado decidem sem ler a configuração. Falha de
    leitura vira "não": o convite é o que se perde, nunca a nota."""
    if not nota_convida(nota) or not ponto.get("google_teste_ativo"):
        return False
    try:
        config = ler_config(supabase)
    except Exception:
        logger.warning("[Ouvidoria] Falha ao ler a chave geral do convite ao Google; a nota segue sem convite")
        return False
    return config["global"] and config["url"].startswith("https://")


def registrar_clique(supabase, avaliacao_id: str) -> None:
    """Conta o clique no "Avaliar no Google". Só na nota que viu o convite: o
    id solto de uma nota sem convite não infla a taxa. Falha aqui não segura
    a pessoa: perder um clique é melhor que deixá-la sem o Google."""
    try:
        (
            supabase.table(TABELA_AVALIACOES)
            .update({"convite_google_clicado": True})
            .eq("id", avaliacao_id)
            .eq("convite_google_exibido", True)
            .execute()
        )
    except Exception:
        logger.warning("[Ouvidoria] Falha ao contar o clique no convite ao Google")


def link_de_avaliacao(supabase) -> str | None:
    """O link de avaliação da configuração, ou None quando não é um https (o
    destino do redirecionamento nunca sai do pedido)."""
    url = ler_config(supabase)["url"]
    return url if url.startswith("https://") else None
