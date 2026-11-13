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

from app.services import ouvidoria_pontos
from app.services.ouvidoria_avaliacoes import NOTA_QUE_PERGUNTA_RETORNO
from app.services.ouvidoria_avaliacoes import TABELA as TABELA_AVALIACOES
from app.services.paginacao import ler_tudo

logger = logging.getLogger(__name__)

TABELA_CONFIG = "ouvidoria_config"
TABELA_AUDITORIA = "ouvidoria_convite_google_auditoria"

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
    supabase.table(ouvidoria_pontos.TABELA).update({"google_teste_ativo": ligado}).eq("id", ponto["id"]).execute()
    _auditar(supabase, me, "ponto", ponto["id"], anterior, ligado)
    return ligado


def _instante(valor) -> dt.datetime:
    return valor if isinstance(valor, dt.datetime) else dt.datetime.fromisoformat(str(valor))


def _taxa(convites: int, cliques: int) -> float | None:
    return round(cliques / convites, 4) if convites else None


def numeros_do_teste(supabase, inicio: dt.date, fim: dt.date, hoje: dt.date, fuso: dt.tzinfo) -> dict:
    """O que a Central mostra do teste (ADR 0089, decisão 7): o estado da chave
    geral, há quantos dias está ligada, o aviso de reavaliar passados os 60
    dias e, por cartaz, os convites exibidos, os cliques e a taxa de clique
    entre `inicio` e `fim` (dias inteiros no fuso do hospital).

    Entram os cartazes com a chave ligada e os que mostraram convite no
    período, mesmo que a chave já tenha sido desligada."""
    config = ler_config(supabase)
    dias_ligado = None
    if config["global"] and config["ligado_em"]:
        dias_ligado = (hoje - _instante(config["ligado_em"]).astimezone(fuso).date()).days

    comeco = dt.datetime.combine(inicio, dt.time.min, tzinfo=fuso)
    depois_do_fim = dt.datetime.combine(fim + dt.timedelta(days=1), dt.time.min, tzinfo=fuso)
    exibidos = ler_tudo(
        lambda: (
            supabase.table(TABELA_AVALIACOES)
            .select("id, ponto_id, criada_em, convite_google_clicado")
            .eq("convite_google_exibido", True)
            .gte("criada_em", comeco.astimezone(dt.UTC).isoformat())
            .order("criada_em")
            .order("id")
        ),
        rotulo="convites ao Google",
    )
    contagem: dict[str, list[int]] = {}
    for linha in exibidos:
        if _instante(linha["criada_em"]) >= depois_do_fim:
            continue
        conta = contagem.setdefault(linha.get("ponto_id"), [0, 0])
        conta[0] += 1
        conta[1] += 1 if linha.get("convite_google_clicado") else 0

    pontos = []
    for ponto in ouvidoria_pontos.listar(supabase):
        convites, cliques = contagem.get(ponto["id"], [0, 0])
        if not ponto.get("google_teste_ativo") and not convites:
            continue
        pontos.append(
            {
                "ponto_id": ponto["id"],
                "nome": ouvidoria_pontos.nome_exibido(ponto),
                "ligado": bool(ponto.get("google_teste_ativo")),
                "convites": convites,
                "cliques": cliques,
                "taxa": _taxa(convites, cliques),
            }
        )
    total_convites = sum(c for c, _ in contagem.values())
    total_cliques = sum(c for _, c in contagem.values())
    return {
        "ligado": config["global"],
        "ligado_em": config["ligado_em"] if config["global"] else None,
        "dias_ligado": dias_ligado,
        "dias_do_teste": DIAS_DO_TESTE,
        "reavaliar": dias_ligado is not None and dias_ligado >= DIAS_DO_TESTE,
        "intervalo": {"inicio": inicio.isoformat(), "fim": fim.isoformat()},
        "pontos": pontos,
        "total": {"convites": total_convites, "cliques": total_cliques, "taxa": _taxa(total_convites, total_cliques)},
    }


def link_de_avaliacao(supabase) -> str | None:
    """O link de avaliação da configuração, ou None quando não é um https (o
    destino do redirecionamento nunca sai do pedido)."""
    url = ler_config(supabase)["url"]
    return url if url.startswith("https://") else None
