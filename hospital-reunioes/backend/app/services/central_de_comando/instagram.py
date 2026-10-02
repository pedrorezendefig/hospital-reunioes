"""A tela do Instagram da Central de Comando: o payload inteiro que ela desenha
(issue #819, PRD #809).

O backend devolve um payload por tela, e a tela não compõe chamada nem faz
conta: a variação de Alcance e Visualizações já vem pronta, e Seguidores vem
como estoque, com o crescimento do período ao lado (sem variação percentual,
que não faz sentido sobre um estoque).

Um bloco da tela, uma chave do payload:

- `periodo`: o período escolhido (só 7 ou 28 dias), quantos dias tem e as datas
  do período e do anterior.
- `seguidores`: o total agora e o crescimento do período (ganhos menos perdas),
  com o crescimento do anterior para a tela desenhar a comparação.
- `alcance` e `visualizacoes`: pessoas e vezes, cada um com o anterior e a
  variação; a tela explica a diferença entre pessoas alcançadas e vezes vistas.
- `engajamento`: as Interações (curtidas, comentários, salvamentos,
  compartilhamentos, na ordem fixa da tela) e as Contas que engajaram (pessoas).
- `principais_publicacoes`: as do período, ordenadas por Interações, sem
  Stories, cada uma com o link para o Instagram.

O `frescor` não é bloco daqui: quem o acrescenta é a leitura pelo cache
(`telas.py`, issue #815). A tela é tudo ou nada: qualquer falha da fonte sobe
daqui como exceção do provedor, e a rota a traduz.
"""

from __future__ import annotations

from app.services.central_de_comando import periodo as periodos
from app.services.central_de_comando import provedor_instagram
from app.services.central_de_comando.periodo import (
    Periodo,
    dias_do_periodo,
    intervalo_anterior,
    intervalo_atual,
)
from app.services.central_de_comando.variacao import variacao_relativa

# O nome de cada tipo de mídia na tela.
ROTULO_DO_TIPO: dict[provedor_instagram.TipoDeMidia, str] = {
    "imagem": "Imagem",
    "carrossel": "Carrossel",
    "reel": "Reel",
    "video": "Vídeo",
}

# As quatro partes das Interações, na ordem fixa em que a tela as mostra, cada
# uma com a chave (o campo do domínio) e o rótulo. Ordem e rótulos da Central
# antiga (`BREAKDOWN_LABELS`).
PARTES_DO_ENGAJAMENTO: tuple[tuple[str, str], ...] = (
    ("curtidas", "Curtidas"),
    ("comentarios", "Comentários"),
    ("salvamentos", "Salvamentos"),
    ("compartilhamentos", "Compartilhamentos"),
)


def montar(periodo: Periodo) -> dict:
    """O payload do Instagram. Falha da fonte sobe como exceção do provedor, e a
    rota a traduz em 502 (fonte fora) ou 503 (não configurado): nunca um payload
    com zero no lugar."""
    hoje = periodos.hoje_utc()
    saude = provedor_instagram.saude_da_conta(periodo, hoje)
    publicacoes = provedor_instagram.principais_publicacoes(periodo, hoje)
    return {
        "periodo": _bloco_periodo(periodo, hoje),
        "seguidores": _bloco_seguidores(saude),
        "alcance": _bloco_numero(saude.alcance, saude.alcance_anterior),
        "visualizacoes": _bloco_numero(saude.visualizacoes, saude.visualizacoes_anterior),
        "engajamento": _bloco_engajamento(saude),
        "principais_publicacoes": [_bloco_publicacao(pub) for pub in publicacoes],
    }


def _bloco_periodo(periodo: Periodo, hoje) -> dict:
    return {
        "chave": periodo,
        "dias": dias_do_periodo(periodo),
        "atual": intervalo_atual(periodo, hoje).como_dict(),
        "anterior": intervalo_anterior(periodo, hoje).como_dict(),
    }


def _bloco_seguidores(saude: provedor_instagram.SaudeDaConta) -> dict:
    """Seguidores é estoque: o total agora e o crescimento do período (e o do
    anterior, para a tela comparar). Sem variação percentual de propósito."""
    return {
        "total": saude.seguidores,
        "crescimento": saude.crescimento,
        "crescimento_anterior": saude.crescimento_anterior,
        "ganhos": saude.seguidores_ganhos,
        "perdidos": saude.seguidores_perdidos,
    }


def _bloco_numero(atual: int, anterior: int) -> dict:
    """Um número de fluxo (Alcance, Visualizações): o do período, o do anterior
    e a variação (nula quando o anterior é zero, e a tela não desenha seta)."""
    return {"atual": atual, "anterior": anterior, "variacao": variacao_relativa(atual, anterior)}


def _bloco_engajamento(saude: provedor_instagram.SaudeDaConta) -> dict:
    """As Interações (a manchete) decompostas nas quatro partes, e as Contas que
    engajaram (pessoas): ações e pessoas, distintas."""
    return {
        "interacoes": saude.interacoes,
        "interacoes_anterior": saude.interacoes_anterior,
        "variacao": variacao_relativa(saude.interacoes, saude.interacoes_anterior),
        "partes": [
            {"chave": chave, "rotulo": rotulo, "valor": getattr(saude.partes, chave)}
            for chave, rotulo in PARTES_DO_ENGAJAMENTO
        ],
        "contas_engajadas": saude.contas_engajadas,
        "contas_engajadas_anterior": saude.contas_engajadas_anterior,
    }


def _bloco_publicacao(pub: provedor_instagram.Publicacao) -> dict:
    # `data` (o instante em que foi publicada) entra no payload da tela mesmo a
    # tela não a desenhando: é o cache que o conector MCP lê (#823), e é dali que
    # ele tira o "quando" de cada publicação, sem abrir leitura própria à fonte.
    return {
        "id": pub.id,
        "legenda": pub.legenda,
        "tipo": pub.tipo,
        "rotulo_tipo": ROTULO_DO_TIPO[pub.tipo],
        "miniatura": pub.miniatura,
        "link": pub.link,
        "data": pub.data,
        "interacoes": pub.interacoes,
    }
