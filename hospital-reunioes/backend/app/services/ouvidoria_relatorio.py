"""Relatório quinzenal da Ouvidoria em PDF, por email (issue #345, PRD #319).

Três coisas moram aqui, e a ordem entre elas é o desenho:

  1. **Qual quinzena** o dia de hoje fecha (`quinzena_encerrada`). Função total:
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

from app.services import ouvidoria_metricas
from app.services.email_service import enviar_com_anexo
from app.services.ouvidoria_metricas import Periodo
from app.services.ouvidoria_prazos import FUSO as FUSO_HOSPITAL
from app.services.ouvidoria_taxonomia import ROTULO_TIPO

logger = logging.getLogger(__name__)

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=True)

QUINZENAL = "quinzenal"
TABELA = "ouvidoria_relatorios"

# As colunas do registro que a listagem devolve. `dados` fica de fora: é o
# objeto inteiro de métricas, e quem lista quer a prateleira, não o conteúdo.
CAMPOS_DO_REGISTRO = (
    "id, tipo, competencia, periodo_inicio, periodo_fim, medido_em, gerado_em, "
    "enviado_em, reenviado_em, reenvios, destinatarios, ultimo_erro"
)

SEM_DADOS = "sem dados"
SEM_COMPARACAO = "sem base de comparação"

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

    return {
        "titulo": "Relatório quinzenal da Ouvidoria",
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


def _buscar(supabase, competencia: str) -> dict | None:
    resultado = supabase.table(TABELA).select("*").eq("competencia", competencia).limit(1).execute()
    linhas = resultado.data or []
    return linhas[0] if linhas else None


def _registrar(supabase, tipo: str, periodo: Periodo, agora: dt.datetime) -> dict:
    """Mede e congela. A leitura das métricas é a mesma do painel."""
    dados = ouvidoria_metricas.metricas_do_periodo(supabase, periodo, agora)
    resultado = (
        supabase.table(TABELA)
        .insert(
            {
                "tipo": tipo,
                "competencia": competencia_de(tipo, periodo),
                "periodo_inicio": periodo.inicio.isoformat(),
                "periodo_fim": periodo.fim.isoformat(),
                "medido_em": agora.isoformat(),
                "dados": dados,
            }
        )
        .execute()
    )
    return (resultado.data or [{}])[0]


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
