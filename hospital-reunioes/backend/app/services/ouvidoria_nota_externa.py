"""A nota que o hospital tem FORA dele: Google e Reclame Aqui (issue #347).

Este número não é medido pelo sistema, e não dá para calculá-lo aqui: quem o
sabe é o ouvidor, que abre as duas páginas e digita o que leu. A integração
automática com o Google Business Profile e com o Reclame Aqui é fase seguinte
(PRD #319, fora de escopo), e por isso a porta desta fatia é a mão do ouvidor.

**Cada registro é uma linha nova, nunca um UPDATE.** A tabela é um diário, e a
leitura devolve a última linha de cada fonte. Sobrescrever seria mais curto e
apagaria a série: a evolução da satisfação é história 8 do PRD, e ela só existe
se as notas antigas continuarem no banco. Guardar também dá ao relatório de
julho, reenviado em setembro, o direito de mostrar a nota de julho.

**As duas escalas são diferentes, e essa é a armadilha da fatia.** O Google vai
de 0 a 5 estrelas, o Reclame Aqui de 0 a 10. Um relatório que imprime "4,3" e
"7,8" um ao lado do outro faz o leitor concluir que o hospital vai melhor no
Reclame Aqui, quando 4,3 de 5 é 86% e 7,8 de 10 é 78%. Por isso a escala mora
aqui, junto da fonte, e sai junto do número em todo lugar que o mostra.
"""

from __future__ import annotations

import datetime as dt
import logging

logger = logging.getLogger(__name__)

TABELA = "ouvidoria_nota_externa"

# A fonte e o teto da régua dela. NÃO é a fonte única da lista de fontes: a
# mesma lista está no `Literal` da rota, no CHECK da migration 082 e no
# `lib/ouvidoria/nota-externa.ts` do front. Acrescentar uma terceira fonte é
# mexer nos quatro; só aqui, a leitura devolveria a fonte nova e o PDF a
# imprimiria, enquanto o POST responderia 422 e o banco recusaria.
ESCALA: dict[str, int] = {"google": 5, "reclame_aqui": 10}

ROTULO_FONTE: dict[str, str] = {"google": "Google", "reclame_aqui": "Reclame Aqui"}

CAMPOS = "fonte, nota, registrada_em, registrada_por_nome"


def registrar(supabase, fonte: str, nota: float, quem: dict, agora: dt.datetime) -> dict:
    """Grava a leitura de hoje. Linha nova, sempre."""
    linha = {
        "fonte": fonte,
        "nota": nota,
        "registrada_em": agora.isoformat(),
        "registrada_por": quem.get("id"),
        "registrada_por_nome": quem.get("nome_completo") or "",
    }
    resultado = supabase.table(TABELA).insert(linha).execute()
    gravada = (resultado.data or [linha])[0]
    return _publico(gravada)


def _publico(linha: dict) -> dict:
    """O que sai pela API: o número, a régua dele e o rastro de quem digitou."""
    fonte = str(linha.get("fonte") or "")
    return {
        "fonte": fonte,
        "nota": float(linha["nota"]) if linha.get("nota") is not None else None,
        "escala": ESCALA.get(fonte),
        "registrada_em": linha.get("registrada_em"),
        "registrada_por_nome": linha.get("registrada_por_nome") or "",
    }


def ultimas(supabase) -> list[dict]:
    """A última nota de cada fonte, sempre com as duas fontes na lista.

    Fonte nunca registrada sai com `nota` nula, e não fora da lista: quem
    mostra precisa dizer "sem registro", e uma lista curta viraria omissão
    silenciosa na tela e no PDF. Nula também nunca pode virar 0, que leria como
    nota zero, a pior nota possível."""
    return [_ultima_da_fonte(supabase, fonte) for fonte in ESCALA]


def _ultima_da_fonte(supabase, fonte: str) -> dict:
    resultado = (
        supabase.table(TABELA).select(CAMPOS).eq("fonte", fonte).order("registrada_em", desc=True).limit(1).execute()
    )
    linhas = resultado.data or []
    if not linhas:
        return {"fonte": fonte, "nota": None, "escala": ESCALA[fonte], "registrada_em": None, "registrada_por_nome": ""}
    return _publico(linhas[0])


def serie(supabase, desde: dt.date) -> list[dict]:
    """Todas as leituras registradas a partir de `desde`, da mais antiga para a
    mais nova (issue #346, história 8 do PRD #319).

    `ultimas` responde "quanto é hoje"; esta responde "como andou". O relatório
    mensal precisa da segunda pergunta: uma nota isolada não diz se o hospital
    está melhorando, e é a evolução que a Diretoria lê.

    Devolve lista vazia quando ninguém digitou nada no intervalo. Não completa
    com as duas fontes como `ultimas` faz, porque aqui a ausência de linha é a
    resposta certa: não houve leitura naquele período, e inventar uma linha
    nula por fonte encheria o gráfico de buraco com cara de dado."""
    resultado = (
        supabase.table(TABELA)
        .select(CAMPOS)
        .gte("registrada_em", desde.isoformat())
        .order("registrada_em", desc=False)
        .execute()
    )
    return [_publico(linha) for linha in (resultado.data or [])]
