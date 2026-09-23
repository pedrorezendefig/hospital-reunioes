"""A tela Visão Geral da Central de Comando: o payload inteiro, por bloco (#821).

O backend devolve um payload por tela, e a tela não compõe chamada nem faz conta
(PRD #809): a variação já vem calculada, e cada número vem com a janela de datas
a que se refere.

**Status por bloco (issue #821).** Até a #814/#815 a Visão Geral era tudo ou
nada: qualquer falha do Google subia como exceção e virava 502/503 da tela
inteira. Agora cada bloco de fonte degrada sozinho. A tela é a soma de blocos
independentes, cada um lido pela sua própria chave de cache, e a leitura NUNCA
levanta por falha de fonte: o erro mora dentro do bloco (`estado`), e os outros
seguem. NENHUM bloco derruba a tela.

Os blocos:

- `periodo`: o período escolhido e as datas dele e do anterior. Não tem fonte,
  está sempre presente.
- `visitantes`: o número-manchete (Visitantes), a variação e o **contexto** dele
  (a Área do site que mais atrai, a principal Origem do público e o dispositivo
  mais usado). Vem do Google, reaproveitando os Dados do Google (#818).
- `instagram`: o Instagram num relance, quatro números (Seguidores, Alcance,
  Visualizações, Interações). Vem do Instagram (#819), capado a 28 dias (a Graph
  API entrega no máximo 30 dias por consulta).
- `objetivos`: os três Objetivos em foco, com o número vivo **reaproveitado** dos
  dois blocos acima, sem nenhuma ida extra à fonte. Objetivo cuja fonte falhou
  fica sem número, mas o card continua.

Cada bloco de fonte tem `estado`: `ok` (com os números, mesmo que sejam o último
valor bom da #815), `sem-dado` (a fonte caiu e não havia número guardado) ou
`nao-configurado` (falta a credencial). O `frescor` da tela é a soma do frescor
dos blocos guardados (`cache.frescor`): a hora do mais velho, e falhou se a de
qualquer um falhou.

Os atalhos e o "O que vem por aí" são conteúdo fixo da tela (front), não do
payload: o menu só lista o que funciona, e o roadmap é texto, não dado (ADR 0058,
decisão 5).
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from datetime import date

from app.services.central_de_comando import dados_do_google, provedor_google, provedor_instagram
from app.services.central_de_comando import periodo as periodos
from app.services.central_de_comando.cache import cache_da_central
from app.services.central_de_comando.objetivos.catalogo import objetivo_por_id
from app.services.central_de_comando.periodo import Periodo, dias_do_periodo, intervalo_anterior, intervalo_atual
from app.services.central_de_comando.telas import Fonte
from app.services.central_de_comando.variacao import variacao_relativa

# Os três Objetivos com número vivo no próprio painel: cada um reaproveita um
# número já buscado (o de site vem dos Visitantes; os de Instagram, do relance).
# Constante fixa, como o `OBJETIVOS_EM_FOCO` da Central antiga.
OBJETIVOS_EM_FOCO: tuple[str, ...] = ("site-visitantes", "instagram-seguidores", "instagram-engajamento")

# Os períodos que o relance do Instagram tem: a Graph API entrega no máximo 30
# dias por consulta, então 90 dias mostra os 28 (mesma regra do registro de
# telas e da lente de Objetivos).
PERIODOS_DO_INSTAGRAM: tuple[Periodo, ...] = ("7d", "28d")


def ler(periodo: Periodo, *, forcar: bool = False) -> dict:
    """O payload inteiro da Visão Geral no período, por bloco. Nunca levanta por
    falha de fonte: cada bloco traz o seu `estado`. `forcar` é o Atualizar agora,
    que renova todos os blocos de fonte."""
    hoje = periodos.hoje_utc()
    visitantes, chave_visitantes = _bloco_visitantes(periodo, forcar)
    instagram, chave_instagram = _bloco_instagram(periodo, forcar)
    frescor = cache_da_central.frescor(*[c for c in (chave_visitantes, chave_instagram) if c is not None])
    return {
        "periodo": _bloco_periodo(periodo, hoje),
        "visitantes": visitantes,
        "instagram": instagram,
        "objetivos": _bloco_objetivos_em_foco(visitantes, instagram),
        "frescor": frescor.como_dict(),
    }


def _bloco_visitantes(periodo: Periodo, forcar: bool) -> tuple[dict, tuple | None]:
    """O número-manchete e o contexto dele, do Google. Devolve o bloco e a chave
    de cache dele (ou `None` quando não há número guardado: nada para o frescor)."""
    return _bloco_de_fonte(
        ("visao-geral:visitantes", periodo),
        lambda: _buscar_visitantes(periodo),
        forcar=forcar,
        fonte=("google", periodo),
        falha=provedor_google.GoogleError,
        nao_configurado=provedor_google.GoogleNaoConfiguradoError,
    )


def ler_visitantes(periodo: Periodo, *, forcar: bool = False) -> tuple[dict, tuple | None]:
    """O bloco de Visitantes (o número-manchete do Site e o contexto dele) e a
    chave de cache dele, lidos do MESMO cache do painel. Existe para o conector
    MCP (#823) reusar o número-manchete e ancorar o frescor do Site na mesma
    chave, do mesmo jeito que o painel combina o frescor por `cache.frescor`. É o
    `_bloco_visitantes` exposto: o `estado` viaja no bloco (`ok`, `sem-dado` ou
    `nao-configurado`), e a chave é `None` quando não há número guardado (nada
    para o frescor). Nunca levanta por falha de fonte."""
    return _bloco_visitantes(periodo, forcar)


def _buscar_visitantes(periodo: Periodo) -> dict:
    """O número-manchete e o contexto numa leitura só, reaproveitando os Dados do
    Google (#818): a Área que mais atrai, a principal Origem e o dispositivo mais
    usado saem do topo de cada ranking, já com a conta pronta."""
    hoje = periodos.hoje_utc()
    visitantes = provedor_google.visitantes_comparados(periodo, hoje)
    dados = dados_do_google.montar(periodo)
    return {
        "atual": visitantes.atual,
        "anterior": visitantes.anterior,
        "variacao": variacao_relativa(visitantes.atual, visitantes.anterior),
        "contexto": {
            "area": _area_que_mais_atrai(dados["areas_do_site"]),
            "origem": _principal_origem(dados["origem_do_publico"]),
            "dispositivo": _dispositivo_mais_usado(dados["dispositivos"]),
        },
    }


def _area_que_mais_atrai(areas: list[dict]) -> dict | None:
    """A Área do site do topo do ranking (já ordenado maior→menor). Sem visita
    nenhuma, não há Área que atraia: nulo, nunca um zero (ADR 0003 de lá)."""
    lider = areas[0] if areas else None
    if lider is None or lider["visitas"] <= 0:
        return None
    return {"chave": lider["chave"], "nome": lider["nome"], "visitas": lider["visitas"]}


def _principal_origem(origens: list[dict]) -> dict | None:
    """A maior Origem identificada (Outros e Não identificado ficam de fora do
    fato principal). As origens já vêm ordenadas, com essas duas no fim."""
    for origem in origens:
        if origem["chave"] not in ("outros", "nao-identificado"):
            return {"chave": origem["chave"], "rotulo": origem["rotulo"], "percentual": origem["percentual"]}
    return None


def _dispositivo_mais_usado(dispositivos: list[dict]) -> dict | None:
    """O dispositivo do topo (já ordenado, líder primeiro). Sem dado, nulo."""
    lider = dispositivos[0] if dispositivos else None
    if lider is None:
        return None
    return {"chave": lider["chave"], "rotulo": lider["rotulo"], "percentual": lider["percentual"]}


def _bloco_instagram(periodo: Periodo, forcar: bool) -> tuple[dict, tuple | None]:
    """O Instagram num relance. Capado a 28 dias: 90 dias mostra os 28 (a Graph
    API entrega no máximo 30 dias), como a Central antiga fazia na home."""
    periodo_ig = periodo if periodo in PERIODOS_DO_INSTAGRAM else "28d"
    return _bloco_de_fonte(
        ("visao-geral:instagram", periodo_ig),
        lambda: _buscar_instagram(periodo_ig),
        forcar=forcar,
        fonte=("instagram", periodo_ig),
        falha=provedor_instagram.InstagramError,
        nao_configurado=provedor_instagram.InstagramNaoConfiguradoError,
    )


def _buscar_instagram(periodo_ig: Periodo) -> dict:
    """Os quatro números de relance, da saúde da conta (sem as publicações, que
    são da tela cheia): Seguidores (estoque), Alcance, Visualizações, Interações."""
    saude = provedor_instagram.saude_da_conta(periodo_ig, periodos.hoje_utc())
    return {
        "seguidores": {"total": saude.seguidores, "crescimento": saude.crescimento},
        "alcance": {"atual": saude.alcance, "variacao": variacao_relativa(saude.alcance, saude.alcance_anterior)},
        "visualizacoes": {
            "atual": saude.visualizacoes,
            "variacao": variacao_relativa(saude.visualizacoes, saude.visualizacoes_anterior),
        },
        "interacoes": {
            "atual": saude.interacoes,
            "variacao": variacao_relativa(saude.interacoes, saude.interacoes_anterior),
        },
    }


def _bloco_objetivos_em_foco(visitantes: dict, instagram: dict) -> dict:
    """Os três Objetivos em foco, com o número vivo reaproveitado dos blocos já
    montados: o card sempre aparece (nome, descrição, destino); o número só
    quando a fonte dele respondeu, senão fica nulo, sem derrubar o card."""
    numeros: dict[str, dict] = {}
    if visitantes["estado"] == "ok":
        numeros["site-visitantes"] = {"rotulo": "Visitantes", "valor": visitantes["atual"]}
    if instagram["estado"] == "ok":
        numeros["instagram-seguidores"] = {"rotulo": "Seguidores", "valor": instagram["seguidores"]["total"]}
        numeros["instagram-engajamento"] = {"rotulo": "Interações", "valor": instagram["interacoes"]["atual"]}
    em_foco = []
    for identificador in OBJETIVOS_EM_FOCO:
        objetivo = objetivo_por_id(identificador)
        assert objetivo is not None, f"Objetivo em foco fora do catálogo: {identificador}"
        em_foco.append(
            {
                "id": objetivo.id,
                "nome": objetivo.nome,
                "descricao": objetivo.descricao,
                "numero": numeros.get(identificador),
            }
        )
    return {"em_foco": em_foco}


def _bloco_de_fonte(
    chave: tuple,
    buscar: Callable[[], dict],
    *,
    forcar: bool,
    fonte: tuple[Fonte, Periodo],
    falha: type[Exception],
    nao_configurado: type[Exception],
) -> tuple[dict, tuple | None]:
    """Lê um bloco pela sua chave de cache e traduz a falha da fonte em `estado`,
    sem levantar: `ok` (com os números, ou o último valor bom da #815),
    `sem-dado` (a fonte caiu e não havia número guardado) ou `nao-configurado`
    (falta a credencial, que nunca vira último valor bom). Devolve o bloco e a
    chave (ou `None` quando o bloco não tem número guardado, para ficar fora do
    frescor)."""
    try:
        leitura = cache_da_central.ler(chave, buscar, forcar=forcar, falhas=(falha,), fontes={fonte})
    except nao_configurado as exc:
        return {"estado": "nao-configurado", "motivo": str(exc)}, None
    except falha as exc:
        return {"estado": "sem-dado", "motivo": str(exc)}, None
    return {"estado": "ok", **copy.deepcopy(leitura.valor)}, chave


def _bloco_periodo(periodo: Periodo, hoje: date) -> dict:
    return {
        "chave": periodo,
        "dias": dias_do_periodo(periodo),
        "atual": intervalo_atual(periodo, hoje).como_dict(),
        "anterior": intervalo_anterior(periodo, hoje).como_dict(),
    }
