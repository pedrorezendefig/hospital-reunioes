"""Os montadores dos Objetivos: a galeria e a lente (issue #820, PRD #809).

Porte de `src/lib/objetivos/objetivo-screen.ts`, adaptado à Central em Python.
Um montador por Objetivo **reúne os números pelos provedores** (Google e
Instagram) e pelo cache com frescor; a rede vive só nos provedores, nunca aqui
(nada de httpx nem chamada de API direta no montador). Sobre os números, o motor
de regras roda e devolve as sugestões, cada uma com o porquê.

- A galeria (`ler_galeria`) traz o número de hoje (28 dias) dos quatro Objetivos
  com montador; os dois em construção vêm sem número e sem lente navegável.
  Os quatro montadores rodam sobre a mesma `Carga`, então a saúde da conta do
  Instagram é lida uma vez só por carga (issue #847).
- A lente (`ler_lente`) traz os números de um Objetivo, o período, as sugestões
  e o frescor. Objetivo inexistente ou em construção não tem lente: a rota
  responde 404 (o `tem_lente` decide).
- Os períodos de cada lente moram só em `PERIODOS_POR_OBJETIVO` e viajam no
  payload da galeria e da lente (issue #847): a tela desenha o seletor com eles,
  e Objetivo novo não exige tocar o front.

Como as telas da Central, a leitura passa pelo cache de 1 hora e é tudo ou nada
até a #821: uma falha da fonte sem número guardado sobe como exceção do provedor,
e a rota a traduz em 502 ou 503.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from functools import cached_property, partial

from app.services.central_de_comando import dados_do_google, provedor_google, provedor_instagram
from app.services.central_de_comando import periodo as periodos
from app.services.central_de_comando.cache import cache_da_central
from app.services.central_de_comando.objetivos.catalogo import OBJETIVOS, objetivo_por_id
from app.services.central_de_comando.objetivos.regras import rodar_regras
from app.services.central_de_comando.objetivos.tipos import (
    ContatoNaLente,
    Contexto,
    Extras,
    Numero,
    ObjetivoId,
    Sugestao,
)
from app.services.central_de_comando.periodo import (
    PERIODO_PADRAO,
    PERIODOS,
    Periodo,
    dias_do_periodo,
    intervalo_anterior,
    intervalo_atual,
)
from app.services.central_de_comando.telas import Fonte, PedidoDeTelaInvalidoError, fontes_no
from app.services.central_de_comando.variacao import variacao_relativa

# As duas fontes que, caídas com número guardado, viram o último valor bom.
_FALHAS: tuple[type[Exception], ...] = (provedor_google.GoogleError, provedor_instagram.InstagramError)

# A galeria mostra o número de hoje num período só: 28 dias, que as duas fontes
# têm (o Instagram não tem 90 dias). Não é um seletor, é o "de hoje".
PERIODO_DA_GALERIA: Periodo = PERIODO_PADRAO


@dataclass
class Carga:
    """Uma carga dos montadores: o período, o dia e as leituras das fontes que
    mais de um montador usa, cada uma feita uma vez só (issue #847).

    A galeria roda os quatro montadores sobre a mesma carga, então os dois
    Objetivos do Instagram dividem a leitura da saúde da conta, em vez de cada
    um ir ao Instagram por ela. A lente cria a dela. A carga não guarda falha:
    se a leitura levantar, a exceção sobe e a carga inteira cai (tudo ou nada)."""

    periodo: Periodo
    hoje: date

    @cached_property
    def saude_do_instagram(self) -> provedor_instagram.SaudeDaConta:
        return provedor_instagram.saude_da_conta(self.periodo, self.hoje)


# Um montador reúne os números e os extras de um Objetivo a partir das fontes.
Montador = Callable[[Carga], tuple[list[Numero], Extras]]


def _montar_instagram_seguidores(carga: Carga) -> tuple[list[Numero], Extras]:
    """Crescer no Instagram: Seguidores (estoque), Alcance e Visualizações."""
    saude = carga.saude_do_instagram
    numeros = [
        Numero(
            "followers",
            "Seguidores",
            saude.seguidores,
            crescimento=saude.crescimento,
            crescimento_anterior=saude.crescimento_anterior,
        ),
        Numero("reach", "Alcance", saude.alcance, anterior=saude.alcance_anterior),
        Numero("views", "Visualizações", saude.visualizacoes, anterior=saude.visualizacoes_anterior),
    ]
    return numeros, Extras()


def _montar_instagram_engajamento(carga: Carga) -> tuple[list[Numero], Extras]:
    """Aumentar o engajamento: Interações e Contas que engajaram, com o Alcance
    e as principais publicações nos extras (as regras leem os dois)."""
    saude = carga.saude_do_instagram
    publicacoes = provedor_instagram.principais_publicacoes(carga.periodo, carga.hoje)
    numeros = [
        Numero("interactions", "Interações", saude.interacoes, anterior=saude.interacoes_anterior),
        Numero(
            "accountsEngaged",
            "Contas que engajaram",
            saude.contas_engajadas,
            anterior=saude.contas_engajadas_anterior,
        ),
    ]
    extras = Extras(
        reach=Numero("reach", "Alcance", saude.alcance, anterior=saude.alcance_anterior),
        publicacoes=tuple(publicacoes),
    )
    return numeros, extras


def _montar_site_visitantes(carga: Carga) -> tuple[list[Numero], Extras]:
    """Atrair mais visitantes: Visitantes do período, com as visitas por
    dispositivo nos extras (a regra do celular lê)."""
    visitantes = provedor_google.visitantes_comparados(carga.periodo, carga.hoje)
    (dispositivos,) = provedor_google.perguntar(provedor_google.visitas_por_dispositivo(carga.periodo, carga.hoje))
    numeros = [Numero("visitors", "Visitantes", visitantes.atual, anterior=visitantes.anterior)]
    return numeros, Extras(dispositivos=dispositivos)


def _montar_contatos(carga: Carga) -> tuple[list[Numero], Extras]:
    """Gerar mais contatos: os Contatos medidos do período (a soma dos canais
    que a GA4 mede), com todos os canais e o estado de cada um nos extras.
    Canal medido sem clique no período conta 0, igual à tela Dados do Google:
    havendo canal medido, a lente e o card dizem "Contatos medidos 0" (decisão
    do dono na revisão do PR #872). Só sem canal medido nenhum não há número."""
    (cliques,) = provedor_google.perguntar(provedor_google.cliques_de_contato(carga.periodo, carga.hoje))
    canais = _canais_da_lente(cliques)
    medidos = [c.cliques for c in canais if c.estado == "medido" and c.cliques is not None]
    numeros = [Numero("contatos", "Contatos medidos", sum(medidos))] if medidos else []
    return numeros, Extras(canais=canais)


def _canais_da_lente(cliques: tuple[provedor_google.CliquesNoCanal, ...]) -> tuple[ContatoNaLente, ...]:
    """Os canais de contato com o estado honesto de cada um, reaproveitando a
    regra de estados da tela Dados do Google (`canais_de_contato`)."""
    canais = dados_do_google.canais_de_contato({c.canal: c.cliques for c in cliques})
    return tuple(
        ContatoNaLente(chave=c["chave"], rotulo=c["rotulo"], estado=c["estado"], cliques=c.get("cliques"))
        for c in canais
    )


# Um montador por Objetivo. As chaves são exatamente os Objetivos navegáveis: o
# que não está aqui é "em construção" no catálogo, e a lente responde 404.
MONTADORES: dict[ObjetivoId, Montador] = {
    "site-visitantes": _montar_site_visitantes,
    "instagram-seguidores": _montar_instagram_seguidores,
    "instagram-engajamento": _montar_instagram_engajamento,
    "contatos": _montar_contatos,
}

# Os períodos que cada lente tem, na ordem do seletor. O Instagram só tem 7 e
# 28 dias (a Graph API limita os insights a 30 dias); o site tem os três. É a
# fonte única (issue #847): os períodos viajam no payload da galeria e da lente,
# e a tela desenha o seletor com eles. O aquecimento do boot também itera aqui.
PERIODOS_POR_OBJETIVO: dict[ObjetivoId, tuple[Periodo, ...]] = {
    "site-visitantes": PERIODOS,
    "instagram-seguidores": ("7d", "28d"),
    "instagram-engajamento": ("7d", "28d"),
    "contatos": PERIODOS,
}


# De onde vêm os números de cada lente. O Atualizar agora de uma lente vence as
# telas vizinhas da mesma fonte e período, e o de uma vizinha vence a lente
# (issue #858): a lente, a galeria e a tela do Instagram mostram o mesmo número.
FONTES_POR_OBJETIVO: dict[ObjetivoId, tuple[Fonte, ...]] = {
    "site-visitantes": ("google",),
    "instagram-seguidores": ("instagram",),
    "instagram-engajamento": ("instagram",),
    "contatos": ("google",),
}

# A galeria lê todos os montadores, então lê das duas fontes.
FONTES_DA_GALERIA: tuple[Fonte, ...] = ("google", "instagram")


def tem_lente(identificador: str) -> bool:
    """O identificador é de um Objetivo navegável (existe e tem montador)?
    Objetivo inexistente ou em construção não tem lente: a rota responde 404."""
    return identificador in MONTADORES


# A recusa de um identificador sem lente. Genérica de propósito (issue #847):
# o valor digitado no endereço não volta na resposta.
LENTE_INEXISTENTE = "A Central não tem a lente desse Objetivo."


def montar_lente(identificador: str, periodo: Periodo) -> dict:
    """O payload da lente de um Objetivo navegável, sem o frescor (quem o
    acrescenta é a leitura pelo cache). Roda as regras sobre os números."""
    objetivo = objetivo_por_id(identificador)
    if objetivo is None or identificador not in MONTADORES:
        raise PedidoDeTelaInvalidoError(LENTE_INEXISTENTE)
    hoje = periodos.hoje_utc()
    numeros, extras = MONTADORES[objetivo.id](Carga(periodo, hoje))
    contexto = Contexto(numeros={n.chave: n for n in numeros}, extras=extras)
    sugestoes = rodar_regras(objetivo.id, contexto)
    return {
        "objetivo": {"id": objetivo.id, "nome": objetivo.nome, "descricao": objetivo.descricao},
        "periodo": _bloco_periodo(periodo, hoje),
        "periodos": list(PERIODOS_POR_OBJETIVO[objetivo.id]),
        "numeros": [_numero_como_dict(n) for n in numeros],
        "sugestoes": [_sugestao_como_dict(s) for s in sugestoes],
    }


def montar_galeria(periodo: Periodo) -> dict:
    """O payload da galeria: os seis Objetivos do catálogo, cada um com o número
    de hoje quando tem montador (o primeiro número da lente), ou nada quando está
    em construção, e os períodos que a lente dele tem (nenhum, em construção).

    Os montadores dividem a mesma carga: a saúde da conta do Instagram, que os
    dois Objetivos do Instagram leem, vai à fonte uma vez só."""
    hoje = periodos.hoje_utc()
    carga = Carga(periodo, hoje)
    destaques: dict[str, Numero] = {}
    for objetivo_id, montar in MONTADORES.items():
        numeros, _extras = montar(carga)
        if numeros:
            destaques[objetivo_id] = numeros[0]
    objetivos = [
        {
            "id": o.id,
            "nome": o.nome,
            "descricao": o.descricao,
            "em_construcao": o.em_construcao,
            "numero": _numero_como_dict(destaques[o.id]) if o.id in destaques else None,
            "periodos": list(PERIODOS_POR_OBJETIVO.get(o.id, ())),
        }
        for o in OBJETIVOS
    ]
    return {"periodo": _bloco_periodo(periodo, hoje), "objetivos": objetivos}


def ler_lente(identificador: str, periodo: Periodo, *, forcar: bool = False) -> dict:
    """A lente do Objetivo no período, com o frescor. Período que a lente não tem
    (90 dias no Instagram) é `PedidoDeTelaInvalidoError` (422 na rota), sem ir à
    fonte. Dentro da hora, sai do cache."""
    periodos_ok = PERIODOS_POR_OBJETIVO.get(identificador)
    if periodos_ok is None:
        raise PedidoDeTelaInvalidoError(LENTE_INEXISTENTE)
    if periodo not in periodos_ok:
        raise PedidoDeTelaInvalidoError(f"O Objetivo {identificador} não tem o período {periodo}.")
    leitura = cache_da_central.ler(
        ("objetivo", identificador, periodo),
        partial(montar_lente, identificador, periodo),
        forcar=forcar,
        falhas=_FALHAS,
        fontes=fontes_no(FONTES_POR_OBJETIVO[identificador], periodo),
    )
    return {**copy.deepcopy(leitura.valor), "frescor": leitura.frescor.como_dict()}


def ler_galeria(*, forcar: bool = False) -> dict:
    """A galeria com o frescor. Dentro da hora, sai do cache."""
    leitura = cache_da_central.ler(
        ("objetivo-galeria", PERIODO_DA_GALERIA),
        partial(montar_galeria, PERIODO_DA_GALERIA),
        forcar=forcar,
        falhas=_FALHAS,
        fontes=fontes_no(FONTES_DA_GALERIA, PERIODO_DA_GALERIA),
    )
    return {**copy.deepcopy(leitura.valor), "frescor": leitura.frescor.como_dict()}


def _bloco_periodo(periodo: Periodo, hoje: date) -> dict:
    return {
        "chave": periodo,
        "dias": dias_do_periodo(periodo),
        "atual": intervalo_atual(periodo, hoje).como_dict(),
        "anterior": intervalo_anterior(periodo, hoje).como_dict(),
    }


def _numero_como_dict(n: Numero) -> dict:
    """Um número pronto para a tela. Fluxo traz o anterior e a variação (a conta
    é do backend, PRD #809); estoque traz o crescimento, sem variação."""
    numero: dict = {"chave": n.chave, "rotulo": n.rotulo, "valor": n.valor}
    if n.anterior is not None:
        numero["anterior"] = n.anterior
        numero["variacao"] = variacao_relativa(n.valor, n.anterior)
    if n.crescimento is not None:
        numero["crescimento"] = n.crescimento
    if n.crescimento_anterior is not None:
        numero["crescimento_anterior"] = n.crescimento_anterior
    return numero


def _sugestao_como_dict(s: Sugestao) -> dict:
    return {"id": s.id, "titulo": s.titulo, "detalhe": s.detalhe, "porque": s.porque, "tom": s.tom}
