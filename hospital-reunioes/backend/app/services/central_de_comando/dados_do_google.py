"""A tela Dados do Google da Central de Comando: o payload inteiro que ela
desenha (issue #817, PRD #809).

O backend devolve um payload por tela, e a tela não compõe chamada nem faz
conta: a variação de cada dia já vem pronta, e cada número vem com a janela de
datas a que se refere.

Um bloco da tela, uma chave do payload:

- `periodo`: o período escolhido, quantos dias ele tem e as datas do período e
  do anterior, no mesmo formato da Visão Geral.
- `movimento`: os Visitantes por dia, um item por dia do período, sem buraco,
  cada um ao lado do dia correspondente do período anterior.
- `dispositivos`: as Visitas por dispositivo (celular, computador, tablet), com
  o rótulo da tela e a fatia de cada um em pontos percentuais que somam 100.
- `areas_do_site` (#818): o ranking das cinco Áreas do site por Visitas, com o
  nome, o que cada uma reúne e a comparação com o período anterior.
- `origem_do_publico` (#818): as Visitas por Origem do público, com o rótulo
  gentil e a fatia de cada uma; Outros e Não identificado sempre no fim.
- `contatos_gerados` (#818): os quatro canais de contato, cada um com o estado
  honesto (medido, em construção, não medido); só o medido traz número.

Todos os números da tela saem de UMA ida à GA4 (`provedor_google.perguntar`,
pelo `batchRunReports`). A #818 acrescenta os blocos dela (Áreas do site,
Origem do público e Contatos gerados) aqui mesmo: uma pergunta a mais no
`perguntar` e uma chave a mais no payload, na mesma chave de cache.
Com eles, a tela pede 7 relatórios, que vão em dois lotes ao mesmo tempo (a
GA4 leva até 5 por lote): a tela continua esperando a GA4 uma vez só.

O `frescor` não é bloco daqui: quem o acrescenta é a leitura pelo cache
(`telas.py`, issue #815), porque ele diz de quando é o payload inteiro. E a
tela é tudo ou nada, como a Visão Geral até a #821: qualquer falha do Google
sobe daqui como exceção do provedor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.services.central_de_comando import periodo as periodos
from app.services.central_de_comando import provedor_google
from app.services.central_de_comando.periodo import Periodo, dias_do_periodo
from app.services.central_de_comando.variacao import variacao_relativa

# O nome de cada dispositivo na tela.
ROTULO_DO_DISPOSITIVO: dict[provedor_google.Dispositivo, str] = {
    "celular": "Celular",
    "computador": "Computador",
    "tablet": "Tablet",
}


def montar(periodo: Periodo) -> dict:
    """O payload de Dados do Google. Falha da fonte sobe como exceção do
    provedor, e a rota a traduz em 502 ou 503: nunca um payload com zero no
    lugar."""
    hoje = periodos.hoje_utc()
    movimento, dispositivos, areas, origens, contatos = provedor_google.perguntar(
        provedor_google.movimento_diario(periodo, hoje),
        provedor_google.visitas_por_dispositivo(periodo, hoje),
        provedor_google.visitas_por_area_do_site(periodo, hoje),
        provedor_google.visitas_por_origem(periodo, hoje),
        provedor_google.cliques_de_contato(periodo, hoje),
    )
    return {
        "periodo": _bloco_periodo(periodo, movimento),
        "movimento": _bloco_movimento(movimento),
        "dispositivos": _bloco_dispositivos(dispositivos),
        "areas_do_site": _bloco_areas_do_site(areas),
        "origem_do_publico": _bloco_origem_do_publico(origens),
        "contatos_gerados": canais_de_contato({contato.canal: contato.cliques for contato in contatos}),
    }


def _bloco_periodo(periodo: Periodo, movimento: provedor_google.MovimentoDiario) -> dict:
    return {
        "chave": periodo,
        "dias": dias_do_periodo(periodo),
        "atual": movimento.intervalo_atual.como_dict(),
        "anterior": movimento.intervalo_anterior.como_dict(),
    }


def _bloco_movimento(movimento: provedor_google.MovimentoDiario) -> list[dict]:
    """Um item por dia do período: o dia, os Visitantes, o dia correspondente
    do período anterior com os Visitantes dele, e a variação de um para o
    outro (nula quando o anterior não teve visita)."""
    return [
        {
            "data": atual.dia.isoformat(),
            "visitantes": atual.visitantes,
            "data_anterior": anterior.dia.isoformat(),
            "visitantes_anterior": anterior.visitantes,
            "variacao": variacao_relativa(atual.visitantes, anterior.visitantes),
        }
        for atual, anterior in zip(movimento.atual, movimento.anterior, strict=True)
    ]


def _bloco_dispositivos(dispositivos: tuple[provedor_google.VisitasNoDispositivo, ...]) -> list[dict]:
    """As fatias da rosca: só os dispositivos com Visita no período, do mais
    usado para o menos usado (o líder vai para o centro), cada um com o rótulo
    da tela e a fatia em pontos percentuais que, juntos, somam 100."""
    com_visita = sorted((d for d in dispositivos if d.visitas > 0), key=lambda d: d.visitas, reverse=True)
    fatias = percentuais_que_somam_100([d.visitas for d in com_visita])
    return [
        {
            "chave": d.dispositivo,
            "rotulo": ROTULO_DO_DISPOSITIVO[d.dispositivo],
            "visitas": d.visitas,
            "percentual": fatia,
        }
        for d, fatia in zip(com_visita, fatias, strict=True)
    ]


def percentuais_que_somam_100(valores: list[int]) -> list[int]:
    """Cada valor como pontos percentuais inteiros do total, somando 100.

    Arredondar cada fatia sozinha não fecha: três terços dão 33 + 33 + 33 = 99.
    Aqui cada fatia fica com a parte inteira, e os pontos que faltam vão, um a
    um, para as que mais perto ficaram de subir (o maior resto); no empate, a
    que vem antes na lista. A conta é inteira, sem erro de ponto flutuante.

    Uma fatia de menos de 1% pode ficar com 0 ponto: a tela a escreve "<1%",
    e não zero. Sem total (lista vazia ou só zeros), tudo é zero.
    """
    total = sum(valores)
    if total <= 0:
        return [0] * len(valores)
    inteiros = [100 * valor // total for valor in valores]
    faltam = 100 - sum(inteiros)
    por_resto = sorted(range(len(valores)), key=lambda i: (-(100 * valores[i] % total), i))
    for i in por_resto[:faltam]:
        inteiros[i] += 1
    return inteiros


# ─── Áreas do site, Origem do público e Contatos gerados (issue #818) ────────


@dataclass(frozen=True)
class AreaNaTela:
    """Como a tela apresenta uma Área do site: o nome e o que ela reúne."""

    nome: str
    descricao: str


# O catálogo das Áreas do site, na ordem do catálogo. Fechado: só entra serviço
# do hospital com página própria no Site. É interpretação da Central, sem
# vínculo com a taxonomia de Setores: nome igual ao de um Setor é coincidência.
AREAS_DO_SITE: dict[provedor_google.AreaDoSite, AreaNaTela] = {
    "maternidade": AreaNaTela("Maternidade", "Estrutura, preparativos, amamentação"),
    "emergencia": AreaNaTela("Emergência 24h", "Adulto, pediátrica, obstétrica, ortopédica"),
    "centro-de-imagem": AreaNaTela("Centro de Imagem", "Diagnóstico por imagem"),
    "centro-medico": AreaNaTela("Centro Médico", "Especialidades e consultas"),
    "laboratorio": AreaNaTela("Laboratório", "Exames e resultados"),
}


def _bloco_areas_do_site(areas: tuple[provedor_google.VisitasNaArea, ...]) -> list[dict]:
    """O ranking das Áreas do site: as cinco, da mais visitada para a menos
    (no empate, a ordem do catálogo, como o ranking da Central antiga), cada
    uma com o nome, o que reúne, as Visitas do período e do anterior e a
    variação de um para o outro (nula quando o anterior não teve visita)."""
    ranking = sorted(areas, key=lambda area: area.visitas, reverse=True)
    return [
        {
            "chave": area.area,
            "nome": AREAS_DO_SITE[area.area].nome,
            "descricao": AREAS_DO_SITE[area.area].descricao,
            "visitas": area.visitas,
            "visitas_anterior": area.visitas_anterior,
            "variacao": variacao_relativa(area.visitas, area.visitas_anterior),
        }
        for area in ranking
    ]


# O nome de cada Origem do público na tela: os da Central antiga e a Indicação
# (quem chegou por um link em outro site), que lá caía em Outros. Os dois do fim
# são os rótulos gentis das fatias pequenas somadas e do que o Google não
# classificou: a tela nunca mostra o termo cru da fonte.
ROTULO_DA_ORIGEM: dict[provedor_google.OrigemDoPublico, str] = {
    "busca": "Busca no Google",
    "direto": "Direto",
    "redes": "Redes sociais",
    "anuncios": "Anúncios",
    "indicacao": "Indicação",
    "outros": "Outros",
    "nao-identificado": "Não identificado",
}

# O resto: sempre no fim da lista, nesta ordem, qualquer que seja o tamanho.
_RESTO: tuple[provedor_google.OrigemDoPublico, ...] = ("outros", "nao-identificado")


def ordenar_origens(origens: list[provedor_google.VisitasNaOrigem]) -> list[provedor_google.VisitasNaOrigem]:
    """A ordem da Origem do público na tela. Porte do `orderSources` da
    Central antiga: as origens da mais visitada para a menos (no empate, a
    ordem em que chegaram) e o resto sempre no fim, Outros e depois Não
    identificado, mesmo quando é maior que uma origem."""

    def lugar(origem: provedor_google.VisitasNaOrigem) -> tuple[int, int]:
        if origem.origem in _RESTO:
            return 1 + _RESTO.index(origem.origem), -origem.visitas
        return 0, -origem.visitas

    return sorted(origens, key=lugar)


def _bloco_origem_do_publico(origens: tuple[provedor_google.VisitasNaOrigem, ...]) -> list[dict]:
    """As barras da Origem do público: só as origens com Visita no período, na
    ordem da tela, cada uma com o rótulo e a fatia do total, arredondada como
    a Central antiga arredondava (`fatia_como_na_central_antiga`)."""
    com_visita = ordenar_origens([origem for origem in origens if origem.visitas > 0])
    total = sum(origem.visitas for origem in com_visita)
    return [
        {
            "chave": origem.origem,
            "rotulo": ROTULO_DA_ORIGEM[origem.origem],
            "visitas": origem.visitas,
            "percentual": fatia_como_na_central_antiga(origem.visitas, total),
        }
        for origem in com_visita
    ]


def fatia_como_na_central_antiga(visitas: int, total: int) -> int:
    """A fatia de uma origem em pontos percentuais inteiros, arredondada
    sozinha, como a barra da Origem da Central antiga (`formatShare`), para a
    tela bater lado a lado com ela.

    Abaixo de 1% do total é 0 ponto, que a tela escreve "<1%" (e não o 1% que
    o arredondamento daria a 0,5%). Do resto, o arredondamento é o de sempre,
    meio ponto para cima: 8,5% é 9. A conta é inteira, sem erro de ponto
    flutuante. As fatias arredondadas uma a uma podem somar 99 ou 101, como
    lá; o Por dispositivo, que fecha em 100, usa o `percentuais_que_somam_100`.
    """
    if total <= 0 or 100 * visitas < total:
        return 0
    return (200 * visitas + total) // (2 * total)


# Os canais de contato, na ordem da tela, com o nome de cada um: os da Central
# antiga (lá o Fale Conosco se chamava "leads" por dentro).
ROTULO_DO_CONTATO: dict[provedor_google.CanalDeContato, str] = {
    "agendar": "Cliques para agendar",
    "whatsapp": "WhatsApp",
    "fale-conosco": "Fale Conosco",
    "telefone": "Telefone",
}


def canais_de_contato(medidos: Mapping[provedor_google.CanalDeContato, int]) -> list[dict]:
    """Os Contatos gerados, um item por canal, na ordem da tela, cada um com
    o estado honesto dele. Porte do `montarCanais` da Central antiga:

    - canal que a GA4 não mede (ausente de `medidos`) é **não medido**;
    - canal medido com zero clique é **em construção**: o Site ainda não avisa
      a GA4 quando ele acontece, e o zero não é resultado;
    - canal com clique é **medido**, e só ele traz `cliques`.

    Em construção e não medido nunca trazem número, nem zero.
    """
    canais: list[dict] = []
    for canal, rotulo in ROTULO_DO_CONTATO.items():
        cliques = medidos.get(canal)
        if cliques is None:
            canais.append({"chave": canal, "rotulo": rotulo, "estado": "nao-medido"})
        elif cliques == 0:
            canais.append({"chave": canal, "rotulo": rotulo, "estado": "em-construcao"})
        else:
            canais.append({"chave": canal, "rotulo": rotulo, "estado": "medido", "cliques": cliques})
    return canais
