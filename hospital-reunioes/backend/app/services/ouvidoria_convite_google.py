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


def _auditar(supabase, me: dict, chave: str, ponto_id: str | None, anterior: bool, novo: bool) -> None:
    """A linha de quem mudou a chave (decisão 6). Escrita depois da mudança
    valer, para não registrar mudança que não aconteceu (como nos prazos)."""
    supabase.table(TABELA_AUDITORIA).insert(
        {
            "chave": chave,
            "ponto_id": ponto_id,
            "valor_anterior": anterior,
            "valor_novo": novo,
            "alterado_por": me["id"],
            "alterado_por_nome": me.get("nome_completo") or me["id"],
        }
    ).execute()


def mudar_chave_geral(supabase, ligado: bool, me: dict, agora: dt.datetime) -> dict:
    """Liga ou desliga a chave geral e devolve o estado. Ligar marca o começo
    dos 60 dias; salvar o mesmo valor não é mudança, não audita e não
    recomeça o prazo."""
    anterior = ler_config(supabase)
    if anterior["global"] == ligado:
        return {"global": anterior["global"], "ligado_em": anterior["ligado_em"]}
    mudanca: dict = {"google_teste_global": ligado}
    if ligado:
        mudanca["google_teste_ligado_em"] = agora.isoformat()
    supabase.table(TABELA_CONFIG).update(mudanca).eq("id", True).execute()
    _auditar(supabase, me, "global", None, anterior["global"], ligado)
    return {"global": ligado, "ligado_em": mudanca.get("google_teste_ligado_em", anterior["ligado_em"])}


def mudar_chave_do_ponto(supabase, ponto: dict, ligado: bool, me: dict) -> bool:
    """Liga ou desliga a chave de um cartaz e devolve o valor novo."""
    anterior = bool(ponto.get("google_teste_ativo"))
    if anterior == ligado:
        return ligado
    supabase.table(TABELA_PONTOS).update({"google_teste_ativo": ligado}).eq("id", ponto["id"]).execute()
    _auditar(supabase, me, "ponto", ponto["id"], anterior, ligado)
    return ligado


def link_de_avaliacao(supabase) -> str | None:
    """O link de avaliação da configuração, ou None quando não é um https (o
    destino do redirecionamento nunca sai do pedido)."""
    url = ler_config(supabase)["url"]
    return url if url.startswith("https://") else None
