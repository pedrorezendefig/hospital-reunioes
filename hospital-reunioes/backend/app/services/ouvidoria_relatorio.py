"""Relatórios da Ouvidoria em PDF, por email (issues #345 e #346, PRD #319).

Duas edições saem daqui, e a diferença entre elas é só o que cada uma mostra:
o QUINZENAL (dias 1 e 16) traz os números do período; o MENSAL (dia 1) traz os
mesmos números mais a tendência de três meses, a evolução da nota externa e uma
seção de sugestões de ação corretiva escrita por IA.

**A única chamada de IA externa do módulo Ouvidoria nasce aqui**, e o que sai
do hospital nela é decidido por `resumo_para_a_ia`, que é o portão do ADR 0034.
Leia o docstring dela antes de acrescentar qualquer campo ao prompt.

Três coisas moram aqui, e a ordem entre elas é o desenho:

  1. **Qual janela** o dia de hoje fecha (`quinzena_encerrada`, `mes_encerrado`).
     As duas são funções totais:
     responde para qualquer data. QUANDO ela é chamada é decisão do
     agendamento, não desta função, e por isso não há aqui nenhuma checagem de
     "hoje é dia 1 ou 16": duas guardas para a mesma coisa deixam o teste verde
     com uma delas desligada.
  2. **Os números**, que vêm de `ouvidoria_metricas.metricas_do_periodo` DIRETO,
     sem passar por HTTP. É a mesma função que a rota do painel chama, e é isso
     que impede o número do PDF de divergir do número da tela.
  3. **A apresentação** (`apresentar`), função pura que traduz o objeto de
     métricas para o que o PDF imprime. Ela é o lugar onde a convenção do
     contrato vira texto: percentual `null` é "sem dados", nunca "0%"; leitura
     degradada vira aviso no topo em vez de número com cara de medido; e os
     tops saem com o denominador ao lado, porque "Recepção (3)" ao lado de "43
     manifestações" apresenta ausência de medição como medição.

**Os números são congelados na geração.** O registro guarda a resposta inteira
do módulo de métricas, e o PDF (inclusive o do reenvio) é montado a partir
dela. Dois motivos: o reenvio precisa mostrar o mesmo retrato do original, e
`pendencias_por_area` é fila VIVA, sem recorte de data. Sem congelar, um
relatório de julho reenviado em setembro carregaria a fila de setembro embaixo
do título de julho. Congelado, ele carrega a fila de julho, e `medido_em` diz
de quando ela é.

**Nenhum caso é identificado.** O objeto de métricas não carrega protocolo em
campo nenhum, de propósito (RN-40, ADR 0034 decisão 8), e este módulo não vai
buscar nenhum: o PDF sai do hospital por email, e protocolo de denúncia
sigilosa cruzado com o email de acionamento identificaria o caso. A seção de
"críticos abertos listados nominalmente" que a issue previa NÃO existe aqui
por esse motivo: o contrato de métricas não expõe crítico nenhum, e inventar o
campo aqui seria decidir sozinho o que a #399 registrou como decisão a tomar.
"""

from __future__ import annotations

import datetime as dt
import io
import logging
import os
from dataclasses import dataclass

from jinja2 import Environment, FileSystemLoader
from postgrest.exceptions import APIError
from weasyprint import HTML

from app.services import ai_processor, ouvidoria_metricas, ouvidoria_nota_externa
from app.services.email_service import enviar_com_anexo
from app.services.ouvidoria_metricas import Periodo
from app.services.ouvidoria_prazos import FUSO as FUSO_HOSPITAL
from app.services.ouvidoria_pseudonimizacao import pseudonimizar
from app.services.ouvidoria_taxonomia import ROTULO_TIPO

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

QUINZENAL = "quinzenal"
MENSAL = "mensal"
TABELA = "ouvidoria_relatorios"

# As colunas do registro que a listagem devolve. `dados` fica de fora: é o
# objeto inteiro de métricas, e quem lista quer a prateleira, não o conteúdo.
CAMPOS_DO_REGISTRO = (
    "id, tipo, competencia, periodo_inicio, periodo_fim, medido_em, gerado_em, "
    "enviado_em, reenviado_em, reenvios, destinatarios, ultimo_erro"
)

SEM_DADOS = "sem dados"
SEM_COMPARACAO = "sem base de comparação"
# A nota externa que ninguém digitou. Nunca "0,0", que leria como a pior nota.
SEM_REGISTRO = "sem registro"

# O que cada leitura que falha estraga, na linguagem de quem lê o relatório.
# O mapa é o do contrato do módulo de métricas (issue #341).
EFEITO_DA_DEGRADACAO: dict[str, str] = {
    "prorrogacoes": ("A taxa de prorrogação do período e a de cada área não puderam ser medidas nesta edição."),
    "prazos": (
        "A tabela de prazos não pôde ser lida: o percentual de prazo cumprido dos três trechos ficou sem medição."
    ),
    "responsaveis": (
        "O cadastro de responsáveis não pôde ser lido: as pendências saem sem o nome de quem responde pelo setor."
    ),
    "nota_externa": (
        "A nota externa (Google e Reclame Aqui) não pôde ser lida: o retrato externo sai sem os números desta edição."
    ),
    # As duas chaves abaixo não vêm do módulo de métricas: são injetadas por
    # este módulo no relatório mensal. Entram no mesmo mapa porque o leitor não
    # tem por que saber de onde veio a leitura que falhou, e sem entrada aqui
    # elas cairiam no texto genérico "os números que dependem dela não valem",
    # que seria FALSO: nenhum outro número do relatório depende destas duas.
    "tendencia": (
        "A comparação com os dois meses anteriores não pôde ser feita: a leitura de um deles falhou. "
        "Os números deste mês foram medidos normalmente."
    ),
    "evolucao_externa": (
        "A série de notas do Google e do Reclame Aqui dos últimos meses não pôde ser lida. "
        "Isso NÃO significa que ninguém digitou nota no período."
    ),
    "feriados": (
        "O calendário de feriados não pôde ser lido. Este é o aviso mais importante desta lista: "
        "os tempos médios, os dias de atraso e os vencimentos foram calculados sem ele, "
        "e podem estar diferentes do real, mesmo tendo cara de número bom."
    ),
}

_ROTULO_TRECHO = {"triagem": "Triagem", "area": "Área", "conclusiva": "Conclusiva"}
_ROTULO_RESPONSAVEL = {"ouvidoria": "Ouvidoria", "area": "Área", "caso": "Caso inteiro"}
_ROTULO_CANAL = {
    "ana": "Ana",
    "telefone": "Telefone",
    "presencial": "Presencial",
    "email": "Email",
    "site": "Site",
    "qr": "QR code",
}


# ───────────────────────────── qual quinzena ─────────────────────────────


def quinzena_encerrada(hoje: dt.date) -> Periodo:
    """A quinzena que o dia de hoje fecha.

    Do dia 16 em diante, a primeira quinzena do mês corrente (1 a 15). Até o dia
    15, a segunda quinzena do mês anterior (16 ao último dia). O relatório
    sempre olha para trás: uma janela fechada, nunca uma em andamento."""
    if hoje.day >= 16:
        return Periodo(inicio=hoje.replace(day=1), fim=hoje.replace(day=15))
    fim_anterior = hoje.replace(day=1) - dt.timedelta(days=1)
    return Periodo(inicio=fim_anterior.replace(day=16), fim=fim_anterior)


def mes_encerrado(hoje: dt.date) -> Periodo:
    """O mês que o dia de hoje fecha: sempre o mês ANTERIOR, inteiro.

    Total como `quinzena_encerrada`, e pelo mesmo motivo: responde para
    qualquer data, e QUANDO ela é chamada é decisão do agendamento. Não há aqui
    checagem de "hoje é dia 1", porque duas guardas para a mesma coisa deixam o
    teste verde com uma delas desligada.

    Nunca o mês corrente: o relatório olha para uma janela fechada, e o mês em
    andamento sairia com o número pela metade e com cara de número inteiro."""
    primeiro_do_corrente = hoje.replace(day=1)
    fim = primeiro_do_corrente - dt.timedelta(days=1)
    return Periodo(inicio=fim.replace(day=1), fim=fim)


def competencia_de(tipo: str, periodo: Periodo) -> str:
    """A identidade da edição. É por ela que a segunda rodada reconhece a
    primeira, e é ela que o índice UNIQUE da migration 080 guarda."""
    return f"{tipo}-{periodo.inicio.isoformat()}-{periodo.fim.isoformat()}"


# ───────────────────────────── apresentação ─────────────────────────────


def _inteiro(valor) -> str:
    return SEM_DADOS if valor is None else f"{int(valor)}"


def _decimal(valor, casas: int = 1) -> str:
    if valor is None:
        return SEM_DADOS
    return f"{float(valor):.{casas}f}".replace(".", ",")


def _pct(valor) -> str:
    """Percentual, ou a admissão de que não houve o que medir.

    `null` NUNCA vira "0%": zero é uma afirmação, e "0% de prorrogação" lê como
    "nenhuma área precisou de mais tempo" (contrato do módulo, item 4)."""
    return SEM_DADOS if valor is None else f"{_decimal(valor)}%"


def _variacao(valor) -> str:
    """A variação contra o período anterior. Sem período anterior com o que
    comparar, o contrato manda `null`, e aqui isso vira texto, não seta."""
    if valor is None:
        return SEM_COMPARACAO
    sinal = "+" if float(valor) > 0 else ""
    return f"{sinal}{_decimal(valor)}%"


def _instante(bruto) -> str:
    if not bruto:
        return SEM_DADOS
    quando = bruto if isinstance(bruto, dt.datetime) else dt.datetime.fromisoformat(str(bruto))
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=dt.UTC)
    return quando.astimezone(FUSO_HOSPITAL).strftime("%d/%m/%Y às %Hh%M")


def _data(bruto) -> str:
    if not bruto:
        return SEM_DADOS
    dia = bruto if isinstance(bruto, dt.date) else dt.date.fromisoformat(str(bruto))
    return dia.strftime("%d/%m/%Y")


def _dia_do_instante(bruto) -> str:
    """Só o dia de um instante, no relógio do hospital. A nota externa é um ato
    de uma vez por quinzena: a hora em que o ouvidor digitou não diz nada a
    quem lê, e a data diz de quando é aquele retrato."""
    if not bruto:
        return ""
    quando = bruto if isinstance(bruto, dt.datetime) else dt.datetime.fromisoformat(str(bruto))
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=dt.UTC)
    return quando.astimezone(FUSO_HOSPITAL).strftime("%d/%m/%Y")


# A chave que nunca foi gravada, distinta de uma leitura que devolveu nada. Um
# `None` no lugar dela faria as duas parecerem a mesma coisa.
_NAO_GRAVADO = object()


def _retrato_externo(notas) -> dict | None:
    """O bloco das notas de fora, com a régua colada em cada número.

    "4,3" e "7,8" um ao lado do outro fazem o leitor concluir que o hospital
    vai melhor no Reclame Aqui, quando 4,3 de 5 é 86% e 7,8 de 10 é 78%. A
    escala sai junto do número por isso, e não por capricho de formatação.

    Três estados, e os três são coisas diferentes. A CHAVE AUSENTE é a edição
    congelada antes de esta fatia existir, e reenviá-la é caminho vivo: ali não
    houve leitura nenhuma, então o bloco não sai (devolve `None`, e o template
    pula a seção). Dizer "não pôde ser lida" num relatório de agosto reenviado
    hoje acusaria uma falha de sistema que nunca houve, e ainda contradiria o
    corpo do email, cujos avisos vêm do `degradado` congelado. `None` é a
    leitura que FALHOU, e nota nula é a que ninguém digitou: a primeira não
    sabe, a segunda sabe que não há. Nenhuma das três vira zero."""
    if notas is _NAO_GRAVADO:
        return None
    if notas is None:
        return {"frase": EFEITO_DA_DEGRADACAO["nota_externa"], "itens": []}
    return {
        "frase": (
            "Nota lida pelo ouvidor nas páginas do Google e do Reclame Aqui, e digitada no sistema. "
            "As duas escalas são diferentes, e por isso cada nota sai com a sua."
        ),
        "itens": [_item_de_nota(linha) for linha in notas],
    }


def _item_de_nota(linha: dict) -> dict:
    """Uma nota externa como o PDF a imprime, com a régua colada no número.

    Os dois blocos de nota do documento (o retrato do quinzenal e a evolução do
    mensal) passam por aqui de propósito. O módulo de nota externa chama de "a
    armadilha da fatia" justamente o risco de 4,3 de 5 e 7,8 de 10 saírem lado
    a lado sem a escala; duas cópias desta formatação no mesmo arquivo seriam
    duas chances de as seções do MESMO PDF divergirem na régua."""
    return {
        "fonte": ouvidoria_nota_externa.ROTULO_FONTE.get(str(linha.get("fonte")), str(linha.get("fonte"))),
        "valor": (
            SEM_REGISTRO if linha.get("nota") is None else f"{_decimal(linha.get('nota'))} de {linha.get('escala')}"
        ),
        "quando": _dia_do_instante(linha.get("registrada_em")),
    }


def _linhas_com_variacao(linhas: list[dict], rotulos: dict[str, str]) -> list[dict]:
    return [
        {
            "chave": rotulos.get(str(linha.get("chave")), str(linha.get("chave") or "Sem informação")),
            "total": _inteiro(linha.get("total")),
            "anterior": _inteiro(linha.get("anterior")),
            "variacao": _variacao(linha.get("variacao_pct")),
        }
        for linha in linhas
    ]


def _frase_do_topo(topo: dict, assunto: str) -> str:
    """O denominador ao lado do ranking.

    Sem ele, uma quinzena de 43 casos com 3 classificados imprimiria
    "Recepção (3)" logo abaixo de "43 manifestações", e o leitor entenderia que
    Recepção teve 3 de 43. Teve 3 de 3."""
    classificados = topo.get("classificados") or 0
    nao = topo.get("nao_classificados") or 0
    total = classificados + nao
    if not topo.get("itens"):
        if classificados:
            return f"Nenhum {assunto} registrado entre os {classificados} casos já classificados de {total}."
        return f"Nada foi classificado ainda: os {total} casos do período seguem na triagem."
    quantos = len(topo["itens"])
    ranking = f"1 {assunto} mais frequente" if quantos == 1 else f"{quantos} {assunto}s mais frequentes"
    return f"{ranking} entre os {classificados} casos já classificados de {total}. {nao} ainda sem classificação."


def _frase_da_prorrogacao(prorrogacao: dict) -> str:
    """A prosa da prorrogação, escrita aqui porque encaixar "sem dados" no meio
    de uma frase pronta produz texto que não se lê."""
    com_a_area = prorrogacao.get("com_a_area") or 0
    passaram = "1 caso passou" if com_a_area == 1 else f"{com_a_area} casos passaram"
    if prorrogacao.get("casos") is None:
        return f"A taxa de prorrogação não pôde ser medida nesta edição. {passaram} pela área no período."
    if not com_a_area:
        return "Nenhum caso passou pela área no período."
    casos = prorrogacao["casos"]
    pediram = "nenhum pediu" if not casos else ("1 pediu" if casos == 1 else f"{casos} pediram")
    return f"{passaram} pela área no período, {pediram} mais prazo. Taxa geral de {_pct(prorrogacao.get('taxa_pct'))}."


def _apoio(prefixo: str, valor: str, sufixo: str = "") -> str:
    """A linha de apoio de um número em destaque. Sem medição, ela admite isso
    em vez de encaixar "sem dados" no meio da frase."""
    if valor in (SEM_DADOS, SEM_COMPARACAO):
        return valor
    return f"{prefixo}{valor}{sufixo}"


def apresentar(registro: dict) -> dict:
    """Traduz o registro congelado para o que o PDF imprime. Função pura."""
    dados = registro["dados"]
    volume = dados["volume"]
    prorrogacao = dados["prorrogacao"]
    degradado = dados.get("degradado") or []
    medido_em = _instante(registro.get("medido_em"))
    # As datas da comparação viajam junto do número em destaque, e não só na
    # linha do cabeçalho. O período anterior é uma janela deslizante do mesmo
    # tamanho (contrato da #341), que NÃO coincide com a quinzena passada: para
    # 01 a 15/08 ele é 17 a 31/07, e o dia 16/07 não entra em comparação
    # nenhuma. Quem lê "+50,0%" em corpo 17 tem que ler ao lado contra o quê.
    anterior = f"{_data(dados['periodo_anterior']['inicio'])} a {_data(dados['periodo_anterior']['fim'])}"

    mensal = registro.get("tipo") == MENSAL
    return {
        "mensal": mensal,
        "titulo": "Relatório mensal da Ouvidoria" if mensal else "Relatório quinzenal da Ouvidoria",
        "periodo": f"{_data(dados['periodo']['inicio'])} a {_data(dados['periodo']['fim'])}",
        "periodo_anterior": anterior,
        "medido_em": medido_em,
        "avisos": [
            EFEITO_DA_DEGRADACAO.get(leitura, f"A leitura de {leitura} falhou: os números que dependem dela não valem.")
            for leitura in degradado
        ],
        "volume": {
            "total": _inteiro(volume.get("total")),
            "anterior": _inteiro(volume.get("anterior")),
            "variacao": _apoio("", _variacao(volume.get("variacao_pct")), f" sobre {anterior}"),
            "novos": _inteiro(volume.get("novos")),
            "novos_variacao": _apoio("", _variacao(volume.get("novos_variacao_pct")), f" sobre {anterior}"),
            "reincidentes": _inteiro(volume.get("reincidentes")),
            # `por_tipo` fica de fora de propósito: tema É `tipo_manifestacao`
            # (ADR 0037), e ele já sai no ranking de temas logo abaixo.
            "por_canal": _linhas_com_variacao(volume.get("por_canal") or [], _ROTULO_CANAL),
        },
        "externo": _retrato_externo(dados.get("nota_externa", _NAO_GRAVADO)),
        "temas": {
            "frase": _frase_do_topo(dados["top_temas"], "tema"),
            "itens": _linhas_com_variacao(dados["top_temas"].get("itens") or [], ROTULO_TIPO),
        },
        "areas": {
            "frase": _frase_do_topo(dados["top_areas"], "área"),
            "itens": _linhas_com_variacao(dados["top_areas"].get("itens") or [], {}),
        },
        "prazo": [
            {
                "trecho": _ROTULO_TRECHO.get(str(t.get("trecho")), str(t.get("trecho") or "")),
                "de": str(t.get("de") or ""),
                "ate": str(t.get("ate") or ""),
                "responsavel": _ROTULO_RESPONSAVEL.get(str(t.get("responsavel")), str(t.get("responsavel") or "")),
                "medidos": _inteiro(t.get("medidos")),
                "cumpridos": _inteiro(t.get("cumpridos")),
                "estourados": _inteiro(t.get("estourados")),
                "em_andamento": _inteiro(t.get("em_andamento")),
                "sem_prazo": _inteiro(t.get("sem_prazo")),
                "percentual": _pct(t.get("percentual_cumprido")),
            }
            for t in dados["prazo"]["trechos"]
        ],
        "pendencias": {
            # O carimbo que a fila viva exige: ela não tem recorte de período.
            "nota": (
                f"Fila medida em {medido_em}. Este bloco responde o que estava pendente naquele instante, "
                "e não o que entrou na quinzena: os dois universos são diferentes, e por isso o total daqui "
                "não se soma ao volume do período."
            ),
            "itens": [
                {
                    "setor": str(linha.get("setor") or "Sem setor"),
                    "responsavel": str(linha.get("responsavel") or "Sem titular cadastrado"),
                    "pendentes": _inteiro(linha.get("pendentes")),
                    "vencidas": _inteiro(linha.get("vencidas")),
                    "atraso": _decimal(linha.get("dias_uteis_de_atraso")),
                }
                for linha in dados["pendencias_por_area"]
            ],
        },
        "prorrogacao": {
            "frase": _frase_da_prorrogacao(prorrogacao),
            "por_area": [
                {
                    "setor": str(linha.get("setor") or "Sem setor"),
                    "casos": _inteiro(linha.get("casos")),
                    "prorrogados": _inteiro(linha.get("prorrogados")),
                    "taxa": _pct(linha.get("taxa_pct")),
                }
                for linha in (prorrogacao.get("por_area") or [])
            ],
        },
        "reincidencia": {
            "casos": _inteiro(dados["reincidencia"].get("casos")),
            "taxa": _apoio("taxa de ", _pct(dados["reincidencia"].get("taxa_pct"))),
        },
        "tempo_pausado": {
            "casos": _inteiro(dados["tempo_pausado"].get("casos_com_pausa")),
            "dias_medios": _apoio(
                "", _decimal(dados["tempo_pausado"].get("dias_uteis_medios")), " dias úteis em média"
            ),
        },
        "ranking": [
            {
                "setor": str(linha.get("setor") or "Sem setor"),
                "respondidas": _inteiro(linha.get("respondidas")),
                "dias_medios": _decimal(linha.get("dias_uteis_medios")),
            }
            for linha in dados["ranking_areas"]
        ],
        # Os três blocos do mensal. No quinzenal saem vazios, e o template pula.
        "tendencia": _apresentar_tendencia(dados) if mensal else None,
        "evolucao_externa": _apresentar_evolucao(dados) if mensal else None,
        "sugestoes": _apresentar_sugestoes(registro) if mensal else None,
    }


def _apresentar_tendencia(dados: dict) -> dict:
    """A série dos meses fechados, ou o aviso de que ela não pôde ser medida."""
    linhas = dados.get("tendencia") or []
    if not linhas:
        return {
            "aviso": (
                f"A tendência dos últimos {MESES_DA_TENDENCIA} meses não pôde ser medida nesta edição: "
                "a leitura de um dos meses falhou, e meia série leria como mês sem manifestação."
            ),
            "itens": [],
        }
    return {
        "aviso": "",
        "itens": [
            {
                "mes": str(linha.get("rotulo") or ""),
                "total": _inteiro(linha.get("total")),
                "reincidencia": _pct(linha.get("reincidencia_pct")),
                "prazo": _pct(linha.get("prazo_area_pct")),
            }
            for linha in linhas
        ],
    }


def _apresentar_evolucao(dados: dict) -> dict:
    """A série das notas externas do período da tendência.

    Três estados, os mesmos de `_retrato_externo`, e a distinção é o ponto:
    leitura que FALHOU não pode sair com a cara de "ninguém digitou". Um PDF
    assinado pelo hospital afirmando que o ouvidor não trabalhou em três meses,
    por causa de um timeout, é pior que não ter a seção."""
    serie = dados.get("evolucao_externa", _NAO_GRAVADO)
    if serie is _NAO_GRAVADO:
        # Edição mensal congelada antes desta fatia existir. Não houve leitura
        # nenhuma ali, então dizer "não pôde ser lida" acusaria uma falha que
        # nunca houve, e a seção simplesmente não sai.
        return {"frase": "", "itens": []}
    if serie is None:
        return {"frase": EFEITO_DA_DEGRADACAO["evolucao_externa"], "itens": []}
    if not serie:
        return {
            "frase": (
                "Nenhuma nota do Google ou do Reclame Aqui foi digitada nos meses deste relatório. "
                "A nota não é medida pelo sistema, ela é lida nas páginas e digitada pelo ouvidor."
            ),
            "itens": [],
        }
    return {
        "frase": (
            "As notas digitadas pelo ouvidor no período, da mais antiga para a mais recente. "
            "As duas escalas são diferentes, e por isso cada nota sai com a sua."
        ),
        "itens": [_item_de_nota(linha) for linha in serie],
    }


def _apresentar_sugestoes(registro: dict) -> dict:
    """As sugestões da IA, ou o aviso no lugar delas.

    A frase de origem é obrigatória e não é decoração: a Diretoria lê o resto
    do documento como medição, e este bloco é a única parte escrita por uma
    máquina que opina. Sem dizer isso, uma sugestão errada passa por número."""
    itens = (registro.get("sugestoes") or {}).get("itens") or []
    if not itens:
        return {
            "origem": "",
            "aviso": registro.get("sugestoes_aviso")
            or (
                "As sugestões de ação corretiva não puderam ser geradas nesta edição. "
                "Os números acima foram medidos normalmente."
            ),
            "itens": [],
        }
    return {
        "origem": (
            "Escritas por inteligência artificial a partir dos números agregados acima, e não dos casos. "
            "Nenhum relato, nome ou protocolo saiu do hospital nesta análise. "
            "São sugestões para a Diretoria avaliar, não decisões tomadas."
        ),
        "aviso": "",
        "itens": [
            {
                "titulo": str(item.get("titulo") or ""),
                "porque": str(item.get("porque") or ""),
                "acao": str(item.get("acao") or ""),
            }
            for item in itens
        ],
    }


# ───────────────────────────── o PDF ─────────────────────────────


def montar_html(registro: dict) -> str:
    """O HTML que vira PDF. Separado do render para o teste poder ler o que
    seria impresso sem depender dos bytes do PDF."""
    logo = os.path.join(os.path.dirname(__file__), "..", "static", "images", "logo_hospital.png")
    fonte = os.path.join(os.path.dirname(__file__), "..", "static", "fonts", "HPSimplified_Rg.ttf")
    return _jinja.get_template("ouvidoria_relatorio_template.html").render(
        r=apresentar(registro),
        logo_path=f"file://{logo}",
        font_path=f"file://{fonte}" if os.path.exists(fonte) else None,
    )


def renderizar_pdf(registro: dict) -> bytes:
    """Os bytes do PDF, pelo mesmo caminho da Ata: Jinja2 mais WeasyPrint."""
    saida = io.BytesIO()
    HTML(string=montar_html(registro)).write_pdf(target=saida)
    return saida.getvalue()


def nome_do_arquivo(registro: dict) -> str:
    return f"relatorio-ouvidoria-{registro['competencia']}.pdf"


# ───────────────────────────── geração e envio ─────────────────────────────


# ────────────────── o que sai do hospital para a IA ──────────────────

# Quantos meses fechados entram na tendência do relatório mensal.
MESES_DA_TENDENCIA = 3

# O que a IA NUNCA vê, mesmo estando no objeto de métricas. `responsavel` é o
# nome do titular de cada setor (o único nome próprio que o agregado carrega,
# como a migration 080 anota), e ele não ajuda numa sugestão de ação corretiva:
# a sugestão nomeia o papel, não a pessoa.
# `responsavel` é o titular do setor em `pendencias_por_area`;
# `registrada_por_nome` é o ouvidor que digitou a nota externa, e ele entrou no
# agregado por esta fatia. São os dois únicos nomes de funcionário que o objeto
# congelado carrega, e os dois param aqui.
FORA_DO_PROMPT = frozenset({"responsavel", "registrada_por_nome"})


def _numero(valor) -> str:
    """O formatador do PROMPT, não do PDF.

    Existe ao lado de `_inteiro` e `_decimal` porque o destino é outro: aqui
    quem lê é um modelo de linguagem, que precisa do número cru e da mesma
    convenção de ausência do documento (`SEM_DADOS`, nunca zero)."""
    if valor is None:
        return SEM_DADOS
    if isinstance(valor, float):
        return f"{valor:.1f}".replace(".", ",")
    return str(valor)


# Teto de um rótulo no prompt. `setor` da manifestação é texto livre sem
# validação de taxonomia (achado da review de segurança, follow-up aberto), e
# sem teto uma área com nome de dez mil caracteres inflaria a chamada sozinha.
TETO_DO_ROTULO = 200


def _rotulo_seguro(rotulo: str) -> str:
    """Um rótulo vira UMA linha do prompt, sempre.

    Colapsa todo espaço em branco antes de pseudonimizar. Sem isso, um `setor`
    com quebra de linha dentro (o campo é texto livre) quebraria a linha em
    duas e o que viesse depois da quebra leria como instrução nova para a IA,
    e não como o nome de uma área. É a diferença entre um dado esquisito e um
    prompt sequestrado."""
    return pseudonimizar(" ".join(str(rotulo).split())[:TETO_DO_ROTULO])


def _linha_do_prompt(rotulo: str, valor) -> str:
    return f"- {_rotulo_seguro(rotulo)}: {_numero(valor)}"


def resumo_para_a_ia(dados: dict) -> str:
    """O texto que sai do hospital na chamada de IA. Função pura.

    Este é O PORTÃO (ADR 0034), e ele é estreito de propósito. Três regras, e
    as três existem porque a alternativa vaza:

    1. **Só agregado.** Nenhum relato, nenhum resumo de caso, nenhum protocolo.
       O objeto de métricas nem lê `relato_integral` (`ouvidoria_metricas.
       CAMPOS_TUPLA`), e ir buscar o texto só para alimentar a IA abriria uma
       leitura que este módulo nunca fez, para mandar a palavra de quem
       manifestou para FORA do hospital. O domínio já decidiu isso no verbete
       "Texto do acionamento" do CONTEXT.md: nem o relato nem o resumo saem da
       Ouvidoria, porque os dois carregam a palavra de quem manifestou. Se o
       responsável do setor, que é pessoa da casa, não recebe, o OpenRouter
       também não.
    2. **`FORA_DO_PROMPT`.** O nome do titular do setor para aqui.
    3. **Todo rótulo passa por `_rotulo_seguro`, ainda assim.** Ele colapsa o
       espaço em branco (uma quebra de linha num rótulo viraria linha nova do
       prompt, e a IA leria o que vem depois como instrução), corta em
       `TETO_DO_ROTULO` e pseudonimiza. O portão é cinto de segurança sobre a
       regra 1, NÃO a defesa principal: ele tem furo conhecido de NOME (leia
       "Limites conhecidos" em `ouvidoria_pseudonimizacao`, e a issue #412). A
       defesa principal é não mandar texto livre nenhum.

    O único campo do agregado que carrega string de origem humana é `setor`, e
    ele é texto livre no banco: a validação não o confere contra a taxonomia
    (issue #419). É por isso que a regra 3 existe mesmo com a regra 1 de pé.
    `categoria`, que seria o pior candidato, é lida por `ouvidoria_metricas`
    mas nunca agregada, então não tem por onde chegar aqui.

    LIMITE CONSCIENTE: célula pequena de caso sigiloso sai daqui. `TEMAS MAIS
    FREQUENTES` é `tipo_manifestacao`, então num mês magro o prompt conta
    "Denúncia: 1", o que revela ao provedor que houve uma denúncia no hospital
    naquele mês. Fica assim porque o agregado NÃO é cruzado: tipo e área são
    contagens separadas, nenhum bloco liga tipo a área, data ou gravidade, e a
    tupla que identificaria um caso nunca sai. Mudar isso muda o significado
    do número e é decisão de domínio, não de implementação.

    Pura porque isso é auditável: dá para ler o que sairia sem subir banco,
    rede nem aplicação, e é assim que o teste do portão olha para ele.
    """
    volume = dados.get("volume") or {}
    reincidencia = dados.get("reincidencia") or {}
    linhas = [
        f"PERÍODO: {(dados.get('periodo') or {}).get('inicio')} a {(dados.get('periodo') or {}).get('fim')}",
        "",
        "VOLUME",
        _linha_do_prompt("manifestações no período", volume.get("total")),
        _linha_do_prompt("no período anterior", volume.get("anterior")),
        _linha_do_prompt("variação percentual", volume.get("variacao_pct")),
        _linha_do_prompt("novas (sem contar reincidentes)", volume.get("novos")),
        _linha_do_prompt("reincidentes", volume.get("reincidentes")),
        _linha_do_prompt("taxa de reincidência (%)", reincidencia.get("taxa_pct")),
    ]

    linhas += _bloco_de_contagem("CANAIS DE ENTRADA", volume.get("por_canal"), _ROTULO_CANAL)
    linhas += _bloco_de_contagem("TEMAS MAIS FREQUENTES", (dados.get("top_temas") or {}).get("itens"), ROTULO_TIPO)
    linhas += _bloco_de_contagem("ÁREAS MAIS FREQUENTES", (dados.get("top_areas") or {}).get("itens"), {})
    linhas += _bloco_de_prazo(dados.get("prazo") or {})
    linhas += _bloco_de_pendencias(dados.get("pendencias_por_area"))
    linhas += _bloco_de_ranking(dados.get("ranking_areas"))
    linhas += _bloco_de_prorrogacao(dados.get("prorrogacao") or {})
    linhas += _bloco_de_tendencia(dados.get("tendencia"))
    linhas += _bloco_de_nota_externa(dados.get("evolucao_externa"))

    degradado = dados.get("degradado") or []
    if degradado:
        linhas += [
            "",
            "NÃO MEDIDO NESTE PERÍODO (não invente causa para estes):",
            *[f"- {_rotulo_seguro(leitura)}" for leitura in degradado],
        ]
    return "\n".join(linhas)


def _bloco_de_contagem(titulo: str, itens, rotulos: dict[str, str]) -> list[str]:
    if not itens:
        return ["", titulo, f"- {SEM_DADOS}"]
    return [
        "",
        titulo,
        *[_linha_do_prompt(rotulos.get(str(i.get("chave")), str(i.get("chave") or "")), i.get("total")) for i in itens],
    ]


def _bloco_de_prazo(prazo: dict) -> list[str]:
    trechos = prazo.get("trechos") or []
    if not trechos:
        return ["", "PRAZO CUMPRIDO POR TRECHO", f"- {SEM_DADOS}"]
    return [
        "",
        "PRAZO CUMPRIDO POR TRECHO (% dos casos medidos)",
        *[
            _linha_do_prompt(
                f"{_ROTULO_TRECHO.get(str(t.get('trecho')), str(t.get('trecho') or ''))} "
                f"(responsável: {_ROTULO_RESPONSAVEL.get(str(t.get('responsavel')), '')}, "
                f"{t.get('medidos')} medidos, {t.get('estourados')} estourados)",
                t.get("percentual_cumprido"),
            )
            for t in trechos
        ],
    ]


def _podar(itens) -> list[dict]:
    """Tira `FORA_DO_PROMPT` de cada linha ANTES de a linha ser formatada.

    A guarda é mecânica de propósito. "Lembrar de não usar o campo" funciona
    até alguém acrescentar uma coluna ao bloco daqui a seis meses; podar o
    dicionário na entrada faz o nome do titular simplesmente não existir para
    quem monta o texto."""
    return [{chave: valor for chave, valor in item.items() if chave not in FORA_DO_PROMPT} for item in (itens or [])]


def _bloco_de_pendencias(itens) -> list[str]:
    """A fila viva por área, SEM o nome de quem responde por ela."""
    podados = _podar(itens)
    if not podados:
        return ["", "PENDÊNCIAS ABERTAS POR ÁREA", "- nenhuma"]
    return [
        "",
        "PENDÊNCIAS ABERTAS POR ÁREA (fila de agora, sem recorte de período)",
        *[
            _linha_do_prompt(
                f"{i.get('setor') or 'Sem setor'} ({i.get('vencidas')} vencidas, "
                f"{_numero(i.get('dias_uteis_de_atraso'))} dias úteis de atraso médio)",
                i.get("pendentes"),
            )
            for i in podados
        ],
    ]


def _bloco_de_ranking(itens) -> list[str]:
    if not itens:
        return ["", "TEMPO MÉDIO DE RESPOSTA POR ÁREA", f"- {SEM_DADOS}"]
    return [
        "",
        "TEMPO MÉDIO DE RESPOSTA POR ÁREA (dias úteis, da mais lenta para a mais rápida)",
        *[
            _linha_do_prompt(
                f"{i.get('setor') or 'Sem setor'} ({i.get('respondidas')} respondidas)", i.get("dias_uteis_medios")
            )
            for i in itens
        ],
    ]


def _bloco_de_prorrogacao(prorrogacao: dict) -> list[str]:
    por_area = prorrogacao.get("por_area") or []
    if not por_area:
        return []
    return [
        "",
        "PRORROGAÇÃO POR ÁREA (% dos casos da área que pediram mais prazo)",
        *[_linha_do_prompt(str(i.get("setor") or "Sem setor"), i.get("taxa_pct")) for i in por_area],
    ]


def _bloco_de_tendencia(itens) -> list[str]:
    if not itens:
        return []
    return [
        "",
        f"TENDÊNCIA DOS ÚLTIMOS {MESES_DA_TENDENCIA} MESES FECHADOS",
        *[
            f"- {_rotulo_seguro(i.get('rotulo') or '')}: {_numero(i.get('total'))} manifestações, "
            f"reincidência {_numero(i.get('reincidencia_pct'))}%, "
            f"prazo da área cumprido {_numero(i.get('prazo_area_pct'))}%"
            for i in itens
        ],
    ]


def _bloco_de_nota_externa(serie) -> list[str]:
    """A série de notas, SEM o nome de quem digitou cada uma.

    Passa por `_podar` pelo mesmo motivo que as pendências: a guarda tem que
    ser mecânica, não "lembrar de não formatar o campo"."""
    podadas = _podar(serie)
    if not podadas:
        return []
    return [
        "",
        "NOTA EXTERNA DO HOSPITAL (escalas diferentes: Google vai a 5, Reclame Aqui vai a 10)",
        *[
            f"- {_rotulo_seguro(ouvidoria_nota_externa.ROTULO_FONTE.get(str(i.get('fonte')), str(i.get('fonte'))))} "
            f"em {_dia_do_instante(i.get('registrada_em'))}: "
            f"{_numero(i.get('nota'))} de {i.get('escala')}"
            for i in podadas
        ],
    ]


def _buscar(supabase, competencia: str) -> dict | None:
    resultado = supabase.table(TABELA).select("*").eq("competencia", competencia).limit(1).execute()
    linhas = resultado.data or []
    return linhas[0] if linhas else None


def _registrar(supabase, tipo: str, periodo: Periodo, agora: dt.datetime) -> dict:
    """Mede e congela. A leitura das métricas é a mesma do painel."""
    dados = ouvidoria_metricas.metricas_do_periodo(supabase, periodo, agora)
    # A nota externa congela junto, pelo mesmo motivo da fila de pendências: ela
    # é o retrato de HOJE, sem recorte de período, e o reenvio de uma edição
    # velha tem que mostrar a nota daquela quinzena.
    dados["nota_externa"] = _ler_nota_externa(supabase)
    if dados["nota_externa"] is None:
        dados["degradado"] = sorted([*dados.get("degradado", []), "nota_externa"])

    # Os blocos que só o mensal tem. Eles entram ANTES da chamada de IA, porque
    # a tendência e a evolução da nota são parte do que a sugestão precisa ler.
    sugestoes: dict = {}
    if tipo == MENSAL:
        dados["tendencia"] = _tendencia(supabase, periodo, agora, dados)
        if not dados["tendencia"]:
            dados["degradado"] = sorted([*dados.get("degradado", []), "tendencia"])
        dados["evolucao_externa"] = _evolucao_externa(supabase, periodo)
        if dados["evolucao_externa"] is None:
            dados["degradado"] = sorted([*dados.get("degradado", []), "evolucao_externa"])
        sugestoes = _sugestoes_de_acao(dados)

    registro = {
        "tipo": tipo,
        "competencia": competencia_de(tipo, periodo),
        "periodo_inicio": periodo.inicio.isoformat(),
        "periodo_fim": periodo.fim.isoformat(),
        "medido_em": agora.isoformat(),
        "dados": dados,
    }
    registro.update(sugestoes)
    resultado = supabase.table(TABELA).insert(registro).execute()
    return (resultado.data or [{}])[0]


def _tendencia(supabase, periodo: Periodo, agora: dt.datetime, do_mes: dict) -> list[dict]:
    """Volume, reincidência e prazo da área dos últimos meses fechados.

    Os meses anteriores são medidos pela MESMA `metricas_do_periodo` que mede o
    mês do relatório. Custa duas leituras a mais, uma vez por mês, e é o que
    impede a linha de junho de sair por uma régua e a de agosto por outra:
    métrica com régua própria é métrica que discorda da operação.

    Falha de leitura devolve lista VAZIA, e o bloco inteiro cai com aviso. Meia
    tendência (dois meses de três) seria pior que nenhuma: a linha que falta
    lê como mês sem manifestação."""
    linhas = []
    mes = periodo
    for passo in range(MESES_DA_TENDENCIA):
        try:
            dados = do_mes if passo == 0 else ouvidoria_metricas.metricas_do_periodo(supabase, mes, agora)
        except Exception:
            # `exception` e não `warning`: sem o traceback, um bug de shape que
            # só aparece em mês antigo apaga a tendência todo mês para sempre,
            # e o operador não distingue "banco fora do ar" de "defeito".
            logger.exception("[Ouvidoria] Falha ao medir %s para a tendência do relatório mensal", mes.inicio)
            return []
        linhas.append(
            {
                "rotulo": f"{mes.inicio.month:02d}/{mes.inicio.year}",
                "inicio": mes.inicio.isoformat(),
                "fim": mes.fim.isoformat(),
                "total": (dados.get("volume") or {}).get("total"),
                "reincidencia_pct": (dados.get("reincidencia") or {}).get("taxa_pct"),
                "prazo_area_pct": _percentual_do_trecho(dados, "area"),
            }
        )
        mes = mes_encerrado(mes.inicio)
    # Do mais antigo para o mais novo: tendência se lê da esquerda para a
    # direita, e a linha do mês do relatório é o fim da história, não o começo.
    return list(reversed(linhas))


def _percentual_do_trecho(dados: dict, trecho: str):
    for linha in (dados.get("prazo") or {}).get("trechos") or []:
        if linha.get("trecho") == trecho:
            return linha.get("percentual_cumprido")
    return None


def _evolucao_externa(supabase, periodo: Periodo) -> list[dict] | None:
    """As notas registradas na janela da tendência, da mais antiga à mais nova.

    Três estados, e os três são coisas diferentes, exatamente como
    `_retrato_externo` já exigia do bloco irmão: `None` é a leitura que FALHOU,
    `[]` é o silêncio (ninguém digitou nota no período) e a lista cheia é o
    dado. A primeira não sabe, a segunda sabe que não há.

    Colapsar os dois primeiros em `[]` faria o PDF afirmar que o ouvidor não
    digitou nota nenhuma em três meses, num documento assinado pelo hospital,
    por causa de um timeout de banco. E como os números são congelados, o erro
    seria permanente: o reenvio o reproduziria."""
    desde = periodo.inicio
    for _ in range(MESES_DA_TENDENCIA - 1):
        desde = mes_encerrado(desde).inicio
    try:
        return ouvidoria_nota_externa.serie(supabase, desde, periodo.fim)
    except Exception:
        logger.exception("[Ouvidoria] Falha ao ler a evolução da nota externa")
        return None


def _sugestoes_de_acao(dados: dict) -> dict:
    """Chama a IA com o AGREGADO e devolve o que vai para as colunas.

    O texto do prompt não volta daqui e não é gravado em lugar nenhum: o que
    fica no banco é a resposta, porque o reenvio precisa entregar o mesmo PDF
    do original. Gravar o envio duplicaria, num campo que nenhuma política de
    retenção varre, o mesmo conteúdo que já mora na manifestação.

    Falha nunca sobe: a análise do mês vale sem a sugestão, e o aviso ocupa o
    lugar da seção para ninguém ler a ausência como "não havia o que sugerir"."""
    resposta = ai_processor.sugerir_acoes_ouvidoria(resumo_para_a_ia(dados))
    itens = resposta.get("sugestoes") or []
    if itens:
        return {"sugestoes": {"itens": itens}, "sugestoes_aviso": None}
    return {
        "sugestoes": None,
        "sugestoes_aviso": (
            "As sugestões de ação corretiva não puderam ser geradas nesta edição. "
            "Os números acima foram medidos normalmente."
        ),
    }


def _ler_nota_externa(supabase) -> list[dict] | None:
    """A última nota de cada fonte, ou `None` quando a leitura falhou.

    A tabela fora do ar não pode derrubar o relatório inteiro: o retrato da
    quinzena vale sem ela. Mas o buraco tem que aparecer, e por isso a falha
    vira `degradado`, e não uma lista vazia com cara de "ninguém digitou"."""
    try:
        return ouvidoria_nota_externa.ultimas(supabase)
    except Exception:
        logger.warning("[Ouvidoria] Falha ao ler a nota externa para o relatório")
        return None


def _diretoria_ativa(supabase) -> list[dict] | None:
    """Quem é a Diretoria Executiva ATIVA hoje, com email.

    `None` é a leitura que falhou; `[]` é o silêncio (ninguém com o perfil).
    A diferença importa: um timeout não pode virar edição carimbada como
    entregue.

    O filtro por `ativo` existe porque o desligamento do hospital é soft delete
    e NÃO limpa `perfil_ouvidoria` (`participantes.py`, DELETE só faz
    `ativo: False`). Sem ele, a diretora desligada continuaria recebendo, duas
    vezes por mês e para sempre, um PDF com o retrato inteiro da Ouvidoria numa
    caixa de email que já não é do hospital, e ela nem aparece mais na tela de
    Usuários para alguém notar. `ouvidoria_notificacoes.ler_diretoria_executiva`
    tem o mesmo buraco e serve o escalonamento (#373): a correção de lá está na
    #399, e por isso este módulo lê por conta própria em vez de mudar o
    comportamento de outra fatia por tabela."""
    try:
        resultado = (
            supabase.table("participantes")
            .select("id, nome_completo, email")
            .eq("perfil_ouvidoria", "diretoria_executiva")
            .eq("ativo", True)
            .execute()
        )
    except Exception:
        logger.warning("[Ouvidoria] Falha ao buscar a Diretoria Executiva para o relatório")
        return None
    return [pessoa for pessoa in (resultado.data or []) if (pessoa.get("email") or "").strip()]


@dataclass(frozen=True)
class Entrega:
    """O resultado de UMA tentativa de entrega.

    `registro` é a linha como ficou no banco, e `entregues` é quem recebeu
    NESTA tentativa, que não é a mesma coisa que a coluna `destinatarios`: ela
    acumula o histórico e nunca encolhe. Quem responde ao ouvidor precisa da
    tentativa ("reenviado para quem?"), e o arquivo precisa do histórico."""

    registro: dict
    entregues: tuple[str, ...]
    erro: str | None

    @property
    def saiu(self) -> bool:
        return bool(self.entregues)


def _acumular(anteriores, novos: list[str]) -> list[str]:
    """A lista de quem recebeu, sem perder ninguém e sem repetir."""
    acumulada = list(anteriores or [])
    for email in novos:
        if email not in acumulada:
            acumulada.append(email)
    return acumulada


def _falha(supabase, registro: dict, motivo: str, liberar: bool = False) -> Entrega:
    """A tentativa não entregou. `destinatarios` fica intacto: ninguém recebeu
    AGORA, e apagar o histórico da primeira entrega seria dizer que quem
    recebeu não recebeu.

    `liberar` devolve a edição à fila de recuperação: quem reivindicou e não
    entregou tem que soltar o carimbo, senão a edição sairia da varredura sem
    nunca ter saído por email."""
    mudanca: dict = {"ultimo_erro": motivo}
    if liberar:
        mudanca["enviado_em"] = None
    return Entrega(registro=_marcar(supabase, registro, mudanca), entregues=(), erro=motivo)


def _reivindicar(supabase, registro: dict, agora: dt.datetime) -> bool:
    """Carimba a edição como entregue ANTES de entregar, e diz se este processo
    foi quem conseguiu carimbar.

    É a guarda de envio único, e ela precisa ser atômica: o UNIQUE de
    `competencia` protege o INSERT, mas o ENVIO ficaria aberto. Duas réplicas do
    backend às 07h (ou o container órfão que já aconteceu nesta casa) leem a
    mesma linha ainda não enviada, rendem o PDF e mandam dois emails iguais para
    a Diretoria. O `is_("enviado_em", "null")` no UPDATE resolve isso no banco:
    quem chega depois não recebe linha nenhuma de volta e não manda nada. A
    varredura das atrasadas depende disto ainda mais, porque ela nem passa pelo
    INSERT.

    Quem reivindica e falha devolve o carimbo (`_falha(liberar=True)`)."""
    resultado = (
        supabase.table(TABELA)
        .update({"enviado_em": agora.isoformat()})
        .eq("id", registro["id"])
        .is_("enviado_em", "null")
        .execute()
    )
    return bool(resultado.data)


def _enviar(supabase, registro: dict, agora: dt.datetime, primeira_entrega: bool = False) -> Entrega | None:
    """Manda o PDF à Diretoria Executiva e escreve no registro o que aconteceu.

    Um destinatário por email: é o padrão do módulo, e evita que a lista de
    quem recebeu circule dentro do próprio email.

    `primeira_entrega` marca o caminho AUTOMÁTICO (job e varredura), o único que
    não pode repetir email: ele reivindica a edição antes de qualquer trabalho e
    devolve `None` quando outra rodada chegou primeiro, sem render e sem envio.
    O reenvio do ouvidor entra com `False` de propósito: quem aperta aquele
    botão está pedindo o segundo email.

    O render e o envio ficam dentro do `try` de propósito. Sem ele, WeasyPrint
    levantando deixaria na tabela uma linha com `enviado_em` NULL e
    `ultimo_erro` NULL, que na listagem lê como "gerado, aguardando", sem
    ninguém saber que houve falha."""
    reivindicado = False
    if primeira_entrega:
        if not _reivindicar(supabase, registro, agora):
            logger.info(
                "[Ouvidoria] Relatório %s já entregue ou reivindicado por outra rodada; nada a fazer.",
                registro.get("competencia"),
            )
            return None
        reivindicado = True
        registro = {**registro, "enviado_em": agora.isoformat()}

    diretoria = _diretoria_ativa(supabase)
    if diretoria is None:
        return _falha(supabase, registro, "Não foi possível ler quem é a Diretoria Executiva", liberar=reivindicado)
    if not diretoria:
        return _falha(
            supabase,
            registro,
            "Ninguém ativo com perfil de Diretoria Executiva para receber o relatório",
            liberar=reivindicado,
        )

    try:
        pdf = renderizar_pdf(registro)
        apresentacao = apresentar(registro)
        assunto = f"{apresentacao['titulo']}, {apresentacao['periodo']}"
        html = _jinja.get_template("email_ouvidoria_relatorio.html").render(
            periodo=apresentacao["periodo"],
            total=apresentacao["volume"]["total"],
            avisos=apresentacao["avisos"],
            logo_base64=_logo_do_email(),
        )
        texto = (
            f"Segue em anexo o relatório da Ouvidoria do período de {apresentacao['periodo']}.\n"
            f"Manifestações no período: {apresentacao['volume']['total']}.\n"
        )
        entregues = [
            pessoa["email"]
            for pessoa in diretoria
            if enviar_com_anexo(
                destinatario=pessoa["email"],
                assunto=assunto,
                html_content=html,
                texto_fallback=texto,
                anexos=[(nome_do_arquivo(registro), pdf)],
            )
        ]
    except Exception as exc:  # noqa: BLE001
        logger.exception("[Ouvidoria] Falha ao montar ou enviar o relatório %s", registro.get("competencia"))
        return _falha(supabase, registro, f"Falha ao montar ou enviar o relatório: {exc}"[:300], liberar=reivindicado)

    if not entregues:
        return _falha(supabase, registro, "O provedor de email recusou a mensagem", liberar=reivindicado)

    # Entrega parcial NÃO é sucesso silencioso. Com três diretores e um email
    # aceito, "entregue" sem ressalva afirma que os outros dois receberam, e o
    # carimbo tira a edição da varredura: ninguém mais olharia para ela.
    faltaram = [pessoa["email"] for pessoa in diretoria if pessoa["email"] not in entregues]
    mudanca: dict = {
        # A lista ACUMULA. Quem recebeu a primeira entrega continua no registro
        # depois de um reenvio para outra Diretoria: numa distribuição de dado
        # da Ouvidoria para fora do sistema, quem recebeu é evidência.
        "destinatarios": _acumular(registro.get("destinatarios"), entregues),
        "ultimo_erro": (
            None if not faltaram else "Entrega parcial: o provedor recusou a mensagem para " + ", ".join(faltaram)
        ),
    }
    if reivindicado:
        # O carimbo já é o da reivindicação, e é ele que responde "esta edição
        # saiu?".
        pass
    elif registro.get("enviado_em"):
        # Um reenvio em setembro que reescrevesse o carimbo faria o histórico
        # dizer que o relatório de agosto saiu em setembro. O reenvio tem
        # carimbo próprio.
        mudanca["reenviado_em"] = agora.isoformat()
        mudanca["reenvios"] = (registro.get("reenvios") or 0) + 1
    else:
        mudanca["enviado_em"] = agora.isoformat()
    return Entrega(
        registro=_marcar(supabase, registro, mudanca), entregues=tuple(entregues), erro=mudanca["ultimo_erro"]
    )


def _logo_do_email() -> str:
    from app.services.email_constants import get_logo_data_uri

    try:
        return get_logo_data_uri()
    except OSError:
        return ""


def _marcar(supabase, registro: dict, mudanca: dict) -> dict:
    supabase.table(TABELA).update(mudanca).eq("id", registro["id"]).execute()
    return {**registro, **mudanca}


def gerar_e_enviar(supabase, periodo: Periodo, agora: dt.datetime, tipo: str = QUINZENAL) -> Entrega | None:
    """Gera o relatório do período e manda por email. Devolve a tentativa, ou
    `None` quando não houve tentativa nenhuma.

    A guarda de envio único é UMA só, e vive no banco: o UPDATE condicional de
    `_reivindicar`. Rodar de novo (todo dia, ou em duas réplicas ao mesmo
    tempo) não repete email porque a segunda rodada não consegue reivindicar.
    Não há aqui nenhuma checagem de "já enviou?" antes disso: duas guardas para
    a mesma coisa deixariam o teste verde com uma delas desligada.

    Quando o registro existe mas o email não saiu (provedor fora do ar, por
    exemplo), a rodada seguinte tenta entregar de novo os MESMOS números, sem
    remedir: o retrato é do instante em que foi tirado."""
    existente = _buscar(supabase, competencia_de(tipo, periodo))
    registro = existente or _registrar(supabase, tipo, periodo, agora)
    return _enviar(supabase, registro, agora, primeira_entrega=True)


# Quantas edições atrasadas uma rodada tenta. O job roda todo dia; a fila só
# passa de uma quando o email falha por mais de uma quinzena inteira.
LOTE_DE_ATRASADOS = 3


def entregar_atrasados(supabase, agora: dt.datetime, exceto: str = "") -> list[Entrega]:
    """Tenta de novo as edições que foram geradas e nunca saíram.

    Sem esta varredura, uma edição que falhou no envio ficaria parada até
    alguém abrir a listagem e reenviar à mão, porque a rodada seguinte já
    calcula outra competência. `exceto` deixa de fora a edição que a própria
    rodada vai tratar, para a mesma competência não ser tentada duas vezes no
    mesmo minuto."""
    resultado = (
        supabase.table(TABELA)
        .select("*")
        .is_("enviado_em", "null")
        .order("periodo_fim", desc=True)
        .limit(LOTE_DE_ATRASADOS)
        .execute()
    )
    atrasados = [linha for linha in (resultado.data or []) if linha.get("competencia") != exceto]
    tentativas = [_enviar(supabase, linha, agora, primeira_entrega=True) for linha in atrasados]
    return [tentativa for tentativa in tentativas if tentativa is not None]


def reenviar(supabase, relatorio_id: str, agora: dt.datetime) -> Entrega | None:
    """Manda de novo um relatório já gerado, com os números congelados dele.

    É ação humana do ouvidor, para recuperar email perdido. Não passa pela
    guarda do job de propósito: quem pede o reenvio está pedindo o segundo
    email."""
    try:
        resultado = supabase.table(TABELA).select("*").eq("id", relatorio_id).limit(1).execute()
    except APIError as exc:
        # Id que não é UUID faz o PostgREST recusar o filtro (22P02). Do lado
        # de fora isso é o mesmo que relatório inexistente.
        logger.info("[Ouvidoria] Reenvio pedido com id inválido: %s", exc)
        return None
    linhas = resultado.data or []
    if not linhas:
        return None
    return _enviar(supabase, linhas[0], agora)


def listar(supabase, limite: int = 50) -> list[dict]:
    """Os relatórios registrados, do mais recente para o mais antigo."""
    resultado = (
        supabase.table(TABELA).select(CAMPOS_DO_REGISTRO).order("periodo_fim", desc=True).limit(limite).execute()
    )
    return resultado.data or []
