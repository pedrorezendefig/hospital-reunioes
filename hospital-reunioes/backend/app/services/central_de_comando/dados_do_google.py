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

Todos os números da tela saem de UMA ida à GA4 (`provedor_google.perguntar`,
pelo `batchRunReports`). A #818 acrescenta os blocos dela (Áreas do site,
Origem do público e Contatos gerados) aqui mesmo: uma pergunta a mais no
`perguntar` e uma chave a mais no payload, na mesma chave de cache.

O `frescor` não é bloco daqui: quem o acrescenta é a leitura pelo cache
(`telas.py`, issue #815), porque ele diz de quando é o payload inteiro. E a
tela é tudo ou nada, como a Visão Geral até a #821: qualquer falha do Google
sobe daqui como exceção do provedor.
"""

from __future__ import annotations

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
    movimento, dispositivos = provedor_google.perguntar(
        provedor_google.movimento_diario(periodo, hoje),
        provedor_google.visitas_por_dispositivo(periodo, hoje),
    )
    return {
        "periodo": _bloco_periodo(periodo, movimento),
        "movimento": _bloco_movimento(movimento),
        "dispositivos": _bloco_dispositivos(dispositivos),
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
