"""O processamento da fila de Contas médicas (issue #1124, PRD #1113, ADR 0070).

A fila vive em `cm_conta` (ADR 0070, decisão 5): o envio deixa a conta
`NA_FILA` e um job do APScheduler, a cada 10 segundos, devolve à fila o que
ficou preso, faz o claim e entrega a conta a um executor próprio com 2 vagas.
Tudo no processo do app: sobrevive a restart porque o estado está no banco.

O pipeline de uma conta, em etapas cronometradas:

1. o texto da conta e o do prontuário, lidos do bucket, onde o envio guardou o
   texto extraído ao lado do PDF (`chave_do_texto`). Só na falta dele o PDF é
   extraído de novo, e o texto fica guardado: o prontuário de um atendimento é
   extraído uma vez e serve a todas as parciais e ao reprocesso;
2. a leitura da conta, gravada em `cm_conta_item`;
3. a leitura do prontuário. A estrutura (`cm_eventos`, com o `prontuario_ate`
   que o aviso do envio usa, `cm_prescricao`, `cm_cirurgia`, `cm_glicemia_dia`,
   o rótulo e a idade em `cm_atendimento`) é gravada uma vez por arquivo de
   prontuário;
4. a conferência por código (as diárias são contadas dentro dela), com a
   memória vigente, as tabelas, os setores e o dicionário do banco;
5. o Guia: o reprocesso troca as linhas abertas e preserva as marcadas; a
   conta fica `A_FAZER` com nota, valores, parecer parcial e o tempo de cada
   etapa.

Leitura que não fecha (PDF sem texto, conta que não soma, prontuário
incompleto) vira `ERRO` com a frase da etapa, sem nova tentativa: o mesmo
arquivo daria o mesmo erro. Falha inesperada volta para a fila; na terceira
tentativa, `ERRO`.

O texto dos PDFs é prontuário: o log leva a etapa, a conta e o tipo do erro
com o lugar no código, nunca a mensagem da exceção, que pode citar o texto.
"""

from __future__ import annotations

import logging
import threading
import traceback
import weakref
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from app.services import storage
from app.services import transcricao_extractor as orcamento
from app.services.contas_medicas import dicionario_ia, passo_a, passo_b
from app.services.contas_medicas import prontuario as leitura_do_prontuario
from app.services.contas_medicas.conferencia import Conferencia, ProntuarioLido, conferir
from app.services.contas_medicas.conteudo import Conteudo, ler_conteudo
from app.services.contas_medicas.desidentificacao import desidentificar
from app.services.contas_medicas.dicionario import dicionario_do_banco
from app.services.contas_medicas.guia import nota_de_entrada
from app.services.contas_medicas.ia import ErroDaIA
from app.services.contas_medicas.memoria import MemoriaLida, RegraLida
from app.services.contas_medicas.operadoras import listar_setores, memoria_vigente
from app.services.contas_medicas.tabelas import pacote_pelo_tuss, preco
from app.services.contas_medicas_conta import Conta, ErroLeitura, ler_conta
from app.services.contas_medicas_extrator import (
    Pagina,
    extrair_paginas,
    paginas_do_texto_guardado,
    texto_para_guardar,
)
from app.services.contas_medicas_retencao import BUCKET, chave_do_texto

logger = logging.getLogger(__name__)

# Quantas contas da cabeça da fila o claim tenta antes de desistir: perder a
# primeira para a outra vaga não pode deixar a vaga parada até o próximo tique.
_CANDIDATAS = 5

# A conta em PROCESSANDO há mais que isto ficou para trás (restart do app no
# meio da análise): volta para a fila. A leitura de um prontuário de 900
# páginas tem prazo de 120 segundos, então 15 minutos não cortam análise viva.
PRAZO_DA_ANALISE = timedelta(minutes=15)
MAXIMO_DE_TENTATIVAS = 3

# Duas análises ao mesmo tempo, no máximo: as mesmas 2 vagas do extrator.
VAGAS = 2
_vagas = threading.BoundedSemaphore(VAGAS)
_executor = ThreadPoolExecutor(max_workers=VAGAS, thread_name_prefix="contas-medicas")

MENSAGEM_TENTATIVAS_ESGOTADAS = "A análise não terminou em três tentativas. Envie de novo."
MENSAGEM_PDF_SEM_TEXTO = "Este PDF não tem texto. Exporte de novo pelo MV"
MENSAGEM_ARQUIVO_FORA_DO_SISTEMA = "O arquivo já saiu do sistema. Envie de novo."
MENSAGEM_SEM_PRONTUARIO = "O prontuário deste atendimento não está no sistema. Envie o prontuário de novo."
MENSAGEM_SEM_MEMORIA = "A operadora desta conta está sem memória carregada."
# A IA fora do ar ou fora do formato depois das três tentativas do adaptador
# (spec 9.9): Erro na hora, e a faturista reprocessa pelo botão da conta.
MENSAGEM_IA_FORA_DO_AR = "Tente de novo em alguns minutos"

# A etapa como a faturista lê, na frase do Erro depois da terceira tentativa.
ETAPAS = {
    "texto_da_conta": "leitura do PDF da conta",
    "leitura_da_conta": "leitura da conta",
    "texto_do_prontuario": "leitura do PDF do prontuário",
    "leitura_do_prontuario": "leitura do prontuário",
    "dicionario": "consulta do dicionário",
    "conferencia": "conferência",
    "passo_a": "leitura do prontuário pela IA",
    "passo_b": "comparação com a memória pela IA",
    "gravacao": "gravação do guia",
}


def mensagem_da_etapa(etapa: str) -> str:
    return f"A análise parou na {ETAPAS.get(etapa, 'análise')}. Envie de novo."


class _Falha(Exception):  # noqa: N818, a leitura que não fecha, não um defeito
    """Leitura que não fecha: Erro na hora, com a frase para a faturista."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


# ----------------------------------------------------------------------------------
# A fila
# ----------------------------------------------------------------------------------


def pegar_da_fila(supabase, agora: datetime) -> dict | None:
    """Claim atômico da próxima conta `NA_FILA`, na ordem de envio.

    O PostgREST não dá `FOR UPDATE SKIP LOCKED` sem uma função no banco, e a
    116 é a única migration do PRD. O claim é o `UPDATE ... WHERE situacao =
    'NA_FILA'` da ADR: o Postgres reavalia o WHERE da segunda escrita depois
    da primeira, então duas chamadas que leram a mesma conta não a pegam as
    duas; a que perdeu tenta a seguinte.
    """
    candidatas = (
        supabase.table("cm_conta")
        .select("id, tentativas")
        .eq("situacao", "NA_FILA")
        .order("ordem_fila")
        .limit(_CANDIDATAS)
        .execute()
        .data
        or []
    )
    for candidata in candidatas:
        pegas = (
            supabase.table("cm_conta")
            .update(
                {
                    "situacao": "PROCESSANDO",
                    "processando_desde": agora.isoformat(),
                    "tentativas": (candidata.get("tentativas") or 0) + 1,
                }
            )
            .eq("id", candidata["id"])
            .eq("situacao", "NA_FILA")
            .execute()
            .data
            or []
        )
        if pegas:
            return pegas[0]
    return None


def _fechar_tentativa(supabase, conta: dict, campos: dict) -> None:
    """O UPDATE que só vale para esta tentativa: a conta que voltou para a fila
    e outra vaga já pegou de novo não é sobrescrita."""
    supabase.table("cm_conta").update(campos).eq("id", conta["id"]).eq("situacao", "PROCESSANDO").eq(
        "tentativas", conta.get("tentativas") or 0
    ).execute()


def _devolver(supabase, conta: dict, erro_motivo: str) -> None:
    """Fim de uma tentativa que não deu certo: volta para a fila, ou, na
    terceira, Erro com a frase."""
    if (conta.get("tentativas") or 0) >= MAXIMO_DE_TENTATIVAS:
        _fechar_tentativa(supabase, conta, {"situacao": "ERRO", "erro_motivo": erro_motivo, "processando_desde": None})
    else:
        _fechar_tentativa(supabase, conta, {"situacao": "NA_FILA", "processando_desde": None})


def devolver_presas(supabase, agora: datetime) -> int:
    """As contas em PROCESSANDO há mais de 15 minutos voltam para a fila; na
    terceira tentativa, Erro. Devolve quantas foram mexidas."""
    presas = (
        supabase.table("cm_conta")
        .select("id, tentativas")
        .eq("situacao", "PROCESSANDO")
        .lt("processando_desde", (agora - PRAZO_DA_ANALISE).isoformat())
        .execute()
        .data
        or []
    )
    for conta in presas:
        _devolver(supabase, conta, MENSAGEM_TENTATIVAS_ESGOTADAS)
    return len(presas)


def alimentar_fila(supabase, agora: datetime, executor=None) -> int:
    """O job do APScheduler: devolve as presas e entrega uma conta a cada vaga
    livre. Devolve quantas foram entregues."""
    devolver_presas(supabase, agora)
    executor = executor or _executor
    entregues = 0
    while _vagas.acquire(blocking=False):
        try:
            conta = pegar_da_fila(supabase, agora)
            if conta is not None:
                executor.submit(_na_vaga, supabase, conta)
        except Exception:
            _vagas.release()
            raise
        if conta is None:
            _vagas.release()
            break
        entregues += 1
    return entregues


def _na_vaga(supabase, conta: dict) -> None:
    try:
        processar(supabase, conta)
    finally:
        _vagas.release()


# ----------------------------------------------------------------------------------
# O pipeline
# ----------------------------------------------------------------------------------


class _Cronometro:
    """O tempo de cada etapa e a etapa em que a análise está (a do erro)."""

    def __init__(self):
        self.tempos: dict[str, float] = {}
        self.atual: str | None = None
        self._inicio = perf_counter()

    @contextmanager
    def etapa(self, nome: str) -> Iterator[None]:
        self.atual = nome
        inicio = perf_counter()
        yield
        self.tempos[nome] = round(perf_counter() - inicio, 3)

    def total(self) -> float:
        return round(perf_counter() - self._inicio, 3)


def _onde(erro: BaseException) -> str:
    """O arquivo e a linha onde o erro nasceu: o lugar, sem a mensagem."""
    quadros = traceback.extract_tb(erro.__traceback__)
    if not quadros:
        return "?"
    return f"{Path(quadros[-1].filename).name}:{quadros[-1].lineno}"


def processar(supabase, conta: dict) -> None:
    """O pipeline de uma conta que o claim pegou. Nunca levanta: o fim é
    `A_FAZER`, `ERRO` ou a volta para a fila."""
    cronometro = _Cronometro()
    try:
        try:
            _pipeline(supabase, conta, cronometro)
        except _Falha as falha:
            logger.warning("[ContasMedicas] Conta %s com erro de leitura na etapa %s", conta["id"], cronometro.atual)
            _fechar_tentativa(
                supabase, conta, {"situacao": "ERRO", "erro_motivo": falha.motivo, "processando_desde": None}
            )
        except ErroDaIA as erro:
            # O adaptador já tentou três vezes: a conta não volta para a fila.
            logger.warning("[ContasMedicas] Conta %s sem a IA na etapa %s: %s", conta["id"], cronometro.atual, erro)
            _fechar_tentativa(
                supabase, conta, {"situacao": "ERRO", "erro_motivo": MENSAGEM_IA_FORA_DO_AR, "processando_desde": None}
            )
        except Exception as erro:
            logger.error(
                "[ContasMedicas] Conta %s falhou na etapa %s, tentativa %s: %s em %s",
                conta["id"],
                cronometro.atual,
                conta.get("tentativas"),
                type(erro).__name__,
                _onde(erro),
            )
            _devolver(supabase, conta, mensagem_da_etapa(cronometro.atual or ""))
            if (conta.get("tentativas") or 0) < MAXIMO_DE_TENTATIVAS:
                return  # voltou para a fila: o envio ainda não terminou
        _avisar_se_o_envio_terminou(supabase, conta)
    except Exception as erro:
        # O banco falhou no fechamento: a conta fica PROCESSANDO e volta pela
        # devolução das presas, em 15 minutos.
        logger.error("[ContasMedicas] Conta %s sem fechamento: %s em %s", conta["id"], type(erro).__name__, _onde(erro))


def _primeira(consulta) -> dict | None:
    achados = consulta.limit(1).execute().data or []
    return achados[0] if achados else None


def _baixar(supabase, chave: str) -> bytes | None:
    """O arquivo do bucket, ou None. Sem log: a falta do texto guardado é o
    caso normal de arquivo enviado antes desta fatia."""
    try:
        conteudo = supabase.storage.from_(BUCKET).download(chave)
    except Exception:
        return None
    return conteudo if isinstance(conteudo, bytes | bytearray) else None


def _texto(supabase, arquivo: dict) -> list[Pagina]:
    """O texto do PDF por página: o guardado pelo envio ou, na falta, o
    extraído agora, que fica guardado para a próxima parcial."""
    chave = arquivo.get("chave_bucket")
    if not chave or arquivo.get("apagado_em"):
        raise _Falha(MENSAGEM_ARQUIVO_FORA_DO_SISTEMA)
    guardado = _baixar(supabase, chave_do_texto(chave))
    if guardado is not None:
        paginas = paginas_do_texto_guardado(guardado)
    else:
        pdf = _baixar(supabase, chave)
        if pdf is None:
            raise RuntimeError("PDF fora do alcance no bucket")
        paginas = extrair_paginas(bytes(pdf))
        if isinstance(paginas, ErroLeitura):
            if paginas.motivo == orcamento.MENSAGEM_FILA_CHEIA:
                raise RuntimeError("extrator sem vaga")
            raise _Falha(paginas.motivo)
        storage.upload_private(supabase, BUCKET, chave_do_texto(chave), texto_para_guardar(paginas), "text/plain")
    if all(pagina.sem_texto for pagina in paginas):
        raise _Falha(MENSAGEM_PDF_SEM_TEXTO)
    return paginas


def _pipeline(supabase, conta: dict, cronometro: _Cronometro) -> None:
    atendimento = _primeira(supabase.table("cm_atendimento").select("*").eq("id", conta["atendimento_id"])) or {}

    with cronometro.etapa("texto_da_conta"):
        arquivo_da_conta = _primeira(supabase.table("cm_arquivo").select("*").eq("id", conta.get("arquivo_id")))
        if arquivo_da_conta is None:
            raise _Falha(MENSAGEM_ARQUIVO_FORA_DO_SISTEMA)
        paginas_da_conta = _texto(supabase, arquivo_da_conta)

    with cronometro.etapa("leitura_da_conta"):
        lida = ler_conta([pagina.texto for pagina in paginas_da_conta])
        if isinstance(lida, ErroLeitura):
            raise _Falha(lida.motivo)
        _gravar_itens(supabase, conta["id"], lida)

    with cronometro.etapa("texto_do_prontuario"):
        arquivo_do_prontuario = _primeira(
            supabase.table("cm_arquivo")
            .select("*")
            .eq("atendimento_id", conta["atendimento_id"])
            .eq("tipo", "PRONTUARIO")
            .is_("apagado_em", "null")
            .order("criado_em", desc=True)
        )
        if arquivo_do_prontuario is None:
            raise _Falha(MENSAGEM_SEM_PRONTUARIO)
        textos = [pagina.texto for pagina in _texto(supabase, arquivo_do_prontuario)]

    with cronometro.etapa("leitura_do_prontuario"):
        try:
            estrutura = leitura_do_prontuario.ler_prontuario(textos, lida.atendimento)
        except leitura_do_prontuario.ErroLeitura as erro:
            raise _Falha(str(erro)) from None
        conteudo = ler_conteudo(textos, estrutura)
        prontuario = ProntuarioLido(estrutura, conteudo, textos)
        _gravar_prontuario(supabase, conta["atendimento_id"], arquivo_do_prontuario["id"], prontuario)

    with cronometro.etapa("dicionario"):
        # O termo de medicamento sem par vai uma vez à IA, antes da
        # conferência: a proposta já vale para esta conta.
        dicionario = dicionario_do_banco(supabase)
        if dicionario_ia.propor_termos(
            supabase, prontuario, lida, dicionario, conta_id=conta["id"], atendimento_id=conta["atendimento_id"]
        ):
            dicionario = dicionario_do_banco(supabase)

    with cronometro.etapa("conferencia"):
        operadora_id = atendimento.get("operadora_id")
        memoria = memoria_vigente(supabase, operadora_id) if operadora_id else None
        if memoria is None:
            raise _Falha(MENSAGEM_SEM_MEMORIA)
        busca_de_preco = _busca_de_preco(supabase, operadora_id)
        conferencia = conferir(
            lida,
            prontuario,
            _memoria_lida(memoria),
            busca_de_preco,
            setores={s["nome_mv"]: s["acomodacao"] for s in listar_setores(supabase) if s.get("acomodacao")},
            dicionario=dicionario,
            pacote_do_tuss=lambda tuss, data: pacote_pelo_tuss(supabase, operadora_id, tuss, data),
        )

    try:
        with cronometro.etapa("passo_a"), _trava_do_prontuario(conta["atendimento_id"]):
            # Depois das conferências: a IA recebe os achados do código, para não
            # repetir linha. A trava faz a parcial que chega junto esperar a
            # leitura da outra e reaproveitá-la.
            eventos = passo_a.eventos_do_atendimento(
                supabase,
                conta_id=conta["id"],
                atendimento_id=conta["atendimento_id"],
                arquivo_id=arquivo_do_prontuario["id"],
                prontuario=prontuario,
                achados=conferencia.linhas,
                regras=memoria["regras"],
            )

        with cronometro.etapa("passo_b"):
            da_ia = passo_b.comparar(
                supabase,
                conta_id=conta["id"],
                atendimento_id=conta["atendimento_id"],
                operadora_id=operadora_id,
                memoria=memoria,
                conta=lida,
                prontuario=prontuario,
                eventos=eventos,
                conferencia=conferencia,
                preco=busca_de_preco,
                dicionario=dicionario,
            )
    except ErroDaIA:
        # A IA não respondeu nas três tentativas: o que o código achou fica no
        # Guia, e a conta vai para Erro. O reprocesso troca as linhas abertas.
        _gravar_guia(supabase, conta["id"], conferencia)
        raise

    with cronometro.etapa("gravacao"):
        # As linhas da IA entram pelo mesmo ponto das do código, num Guia só.
        linhas = _gravar_guia(
            supabase, conta["id"], replace(conferencia, linhas=passo_b.juntar(conferencia.linhas, da_ia.linhas))
        )
        nota = nota_de_entrada(linhas, lida.total)

    # A 116 não tem coluna para o tempo das etapas, e o PRD tem migration única:
    # ele vai em `faltantes`, ao lado dos itens que o prontuário não trouxe.
    # O parecer junta o que a leitura por código não teve e o que a IA apontou.
    parecer = [*estrutura.parecer_parcial, *passo_a.parecer(eventos)]
    tempos = {**cronometro.tempos, "total": cronometro.total()}
    _fechar_tentativa(
        supabase,
        conta,
        {
            "situacao": "A_FAZER",
            "erro_motivo": None,
            "total_lancado": float(lida.total),
            "nota_bruta": nota.nota,
            "nota_entrada": nota.nota,
            "valor_apontado": float(nota.apontado),
            "valor_em_validacao": float(nota.em_validacao),
            "parecer_parcial": bool(parecer),
            # A linha da IA que as conferências derrubaram fica registrada, com o motivo.
            "faltantes": {"itens": parecer, "tempos_por_etapa_s": tempos, "descartadas_ia": list(da_ia.descartadas)},
            "memoria_versao_id": memoria["memoria_versao_id"],
            "pronta_em": datetime.now(UTC).isoformat(),
        },
    )
    logger.info("[ContasMedicas] Conta %s pronta em %ss", conta["id"], tempos["total"])


def _memoria_lida(memoria: dict) -> MemoriaLida:
    """A memória vigente como a conferência lê. Sigla e nome ela não usa."""
    return MemoriaLida(
        sigla="",
        nome="",
        versao=memoria["versao"],
        situacao="",
        parametros=memoria["parametros"],
        regras=tuple(
            RegraLida(
                codigo=r["codigo"],
                secao=r.get("secao"),
                texto=r.get("texto") or "",
                tipo=r.get("tipo"),
                origem=r.get("origem"),
                status=r.get("status") or "PENDENTE",
                validado_em=None,
            )
            for r in memoria["regras"]
        ),
    )


def _busca_de_preco(supabase, operadora_id: str):
    """A busca de preço do banco, com memória: a conferência pergunta o mesmo
    item mais de uma vez (cobrável, coluna do plano e a oposta)."""
    vistos: dict[tuple, Decimal | str] = {}

    def buscar(categoria: str, codigo: str, data: date, coluna: str | None) -> Decimal | str:
        chave = (categoria, codigo, data, coluna)
        if chave not in vistos:
            vistos[chave] = preco(supabase, operadora_id, categoria, codigo, data, coluna)
        return vistos[chave]

    return buscar


def _numero(valor: Decimal | None) -> float | None:
    return float(valor) if valor is not None else None


def _gravar_itens(supabase, conta_id: str, lida: Conta) -> None:
    supabase.table("cm_conta_item").delete().eq("conta_id", conta_id).execute()
    if not lida.itens:
        return
    supabase.table("cm_conta_item").insert(
        [
            {
                "conta_id": conta_id,
                "ordem": ordem,
                "data": item.data.isoformat(),
                "grupo_conta": item.grupo,
                "setor": item.setor,
                "grupo_procedimento": item.grupo_procedimento,
                "codigo": item.codigo,
                "descricao": item.descricao,
                "quantidade": _numero(item.quantidade),
                "unidade": item.unidade,
                "valor_unitario": _numero(item.unitario),
                "valor_total": _numero(item.total),
                "percentual": _numero(item.percentual),
            }
            for ordem, item in enumerate(lida.itens, start=1)
        ]
    ).execute()


def _chave_da_linha(linha: dict) -> tuple:
    return (linha.get("acao"), linha.get("codigo"), linha.get("data"), linha.get("data_fim"), linha.get("setor"))


def _gravar_guia(supabase, conta_id: str, conferencia: Conferencia) -> list[dict]:
    """O reprocesso troca as linhas abertas e preserva as marcadas. A linha
    nova igual a uma marcada não entra: a marcação dela já responde."""
    existentes = supabase.table("cm_guia_linha").select("*").eq("conta_id", conta_id).execute().data or []
    marcadas = [linha for linha in existentes if linha.get("estado") != "ABERTA"]
    supabase.table("cm_guia_linha").delete().eq("conta_id", conta_id).eq("estado", "ABERTA").execute()
    ja_marcadas = {_chave_da_linha(linha) for linha in marcadas}
    novas = [
        {**linha, "conta_id": conta_id} for linha in conferencia.linhas if _chave_da_linha(linha) not in ja_marcadas
    ]
    if not novas:
        return marcadas
    return marcadas + (supabase.table("cm_guia_linha").insert(novas).execute().data or [])


# ----------------------------------------------------------------------------------
# A estrutura do prontuário, gravada uma vez por arquivo
# ----------------------------------------------------------------------------------


def _iso(valor: date | datetime | None) -> str | None:
    return valor.isoformat() if valor else None


def _prontuario_ate(prontuario: ProntuarioLido) -> date | None:
    """A última data que o prontuário cobre: o documento mais recente ou a alta."""
    datas = [d.data for d in prontuario.estrutura.documentos if d.data]
    if prontuario.conteudo.internacao.alta:
        datas.append(prontuario.conteudo.internacao.alta.date())
    return max(datas) if datas else None


def _eventos_json(arquivo_id: str, prontuario: ProntuarioLido) -> dict[str, Any]:
    """Os eventos estruturados, sem texto livre do prontuário."""
    estrutura, conteudo = prontuario.estrutura, prontuario.conteudo
    internacao = conteudo.internacao
    return {
        "arquivo_id": arquivo_id,
        "total_paginas": estrutura.total_paginas,
        "tipo_impressao": estrutura.tipo_impressao,
        "grupos_da_capa": estrutura.grupos_da_capa,
        "parecer_parcial": list(estrutura.parecer_parcial),
        "paginas_sem_texto": list(estrutura.paginas_sem_texto),
        "internacao": {
            "entrada": _iso(internacao.entrada),
            "alta": _iso(internacao.alta),
            "motivo_alta": internacao.motivo_alta,
            "acomodacao_na_admissao": internacao.acomodacao_na_admissao,
        },
        "movimentacoes": [
            {"tipo": m.tipo, "data_hora": _iso(m.data_hora), "setor": m.setor} for m in conteudo.movimentacoes
        ],
        "setor_por_dia": {_iso(dia): list(setores) for dia, setores in conteudo.setor_por_dia.items()},
        "documentos": [
            {
                "familia": d.familia,
                "paginas": list(d.paginas),
                "data": _iso(d.data),
                "hora": d.hora.isoformat() if d.hora else None,
                "setor": d.setor,
                "subtipo": d.subtipo,
            }
            for d in estrutura.documentos
        ],
    }


# As duas vagas pegam juntas as parciais do mesmo atendimento (o caso normal
# de um envio): sem trava, as duas leem `cm_eventos` vazio e as duas gravam o
# prontuário. Uma trava por atendimento, que some quando ninguém a segura.
_travas_do_prontuario: weakref.WeakValueDictionary[str, threading.Lock] = weakref.WeakValueDictionary()
_trava_das_travas = threading.Lock()


def _trava_do_prontuario(atendimento_id: str) -> threading.Lock:
    with _trava_das_travas:
        trava = _travas_do_prontuario.get(atendimento_id)
        if trava is None:
            trava = _travas_do_prontuario[atendimento_id] = threading.Lock()
        return trava


def _gravar_prontuario(supabase, atendimento_id: str, arquivo_id: str, prontuario: ProntuarioLido) -> None:
    """A estrutura do prontuário no banco, uma vez por arquivo: a segunda
    parcial e o reprocesso acham o mesmo arquivo gravado e seguem. Prontuário
    novo (atualizado) troca o anterior inteiro."""
    with _trava_do_prontuario(atendimento_id):
        _gravar_prontuario_uma_vez(supabase, atendimento_id, arquivo_id, prontuario)


def _gravar_prontuario_uma_vez(supabase, atendimento_id: str, arquivo_id: str, prontuario: ProntuarioLido) -> None:
    ultimo = _primeira(
        supabase.table("cm_eventos").select("*").eq("atendimento_id", atendimento_id).order("criado_em", desc=True)
    )
    if ultimo and (ultimo.get("eventos_json") or {}).get("arquivo_id") == arquivo_id:
        return
    for tabela in ("cm_eventos", "cm_prescricao", "cm_cirurgia", "cm_glicemia_dia"):
        supabase.table(tabela).delete().eq("atendimento_id", atendimento_id).execute()

    supabase.table("cm_eventos").insert(
        {
            "atendimento_id": atendimento_id,
            "eventos_json": _eventos_json(arquivo_id, prontuario),
            "prontuario_ate": _iso(_prontuario_ate(prontuario)),
        }
    ).execute()
    _gravar_prescricoes(supabase, atendimento_id, prontuario)
    _gravar_cirurgias(supabase, atendimento_id, prontuario.conteudo)
    _gravar_glicemias(supabase, atendimento_id, prontuario.conteudo)
    supabase.table("cm_atendimento").update(
        {"paciente_rotulo": prontuario.estrutura.paciente_rotulo, "idade_anos": prontuario.estrutura.idade_anos}
    ).eq("id", atendimento_id).execute()


def _gravar_prescricoes(supabase, atendimento_id: str, prontuario: ProntuarioLido) -> None:
    # A observação é texto livre do prontuário: entra desidentificada.
    identificacao = leitura_do_prontuario._ler_capa(list(prontuario.texto_por_pagina)).identificacao
    for prescricao in prontuario.conteudo.prescricoes:
        gravada = (
            supabase.table("cm_prescricao")
            .insert(
                {
                    "atendimento_id": atendimento_id,
                    "data": _iso(prescricao.data),
                    "hora": prescricao.hora.isoformat() if prescricao.hora else None,
                    "subtipo": prescricao.subtipo,
                    "pagina": prescricao.paginas[0] if prescricao.paginas else None,
                }
            )
            .execute()
            .data[0]
        )
        if not prescricao.itens:
            continue
        supabase.table("cm_prescricao_item").insert(
            [
                {
                    "prescricao_id": gravada["id"],
                    "secao": item.secao,
                    "n": item.numero,
                    "nome": item.nome,
                    "generico": item.generico,
                    "colunas": {
                        "dose": item.dose,
                        "frequencia": item.frequencia,
                        "via": item.via,
                        "horarios": list(item.horarios),
                    },
                    "doses_por_dia": item.doses_por_dia,
                    "se_necessario": item.se_necessario,
                    "suspenso": item.suspenso,
                    "obs": desidentificar([item.obs], identificacao)[0] if item.obs else None,
                    "componentes_json": list(item.componentes),
                    "pedido": item.pedido,
                }
                for item in prescricao.itens
            ]
        ).execute()


def _na_data(dia: date | None, hora: time | None) -> str | None:
    return datetime.combine(dia, hora).isoformat() if dia and hora else None


def _gravar_cirurgias(supabase, atendimento_id: str, conteudo: Conteudo) -> None:
    """Uma linha por cirurgia: a descrição e a ficha anestésica na ordem da data."""
    descricoes = sorted(conteudo.descricoes_cirurgicas, key=lambda d: d.inicio or datetime.min)
    fichas = sorted(conteudo.fichas_anestesicas, key=lambda f: f.data or date.min)
    linhas = []
    for i in range(max(len(descricoes), len(fichas))):
        descricao = descricoes[i] if i < len(descricoes) else None
        ficha = fichas[i] if i < len(fichas) else None
        linha: dict[str, Any] = {"atendimento_id": atendimento_id}
        if descricao:
            linha |= {
                "procedimentos_json": [
                    {"codigo": p.codigo, "descricao": p.descricao, "principal": p.principal}
                    for p in descricao.procedimentos
                ],
                "inicio": _iso(descricao.inicio),
                "fim": _iso(descricao.fim),
            }
        if ficha:
            linha |= {
                "anestesia_inicio": _na_data(ficha.data, ficha.inicio),
                "anestesia_fim": _na_data(ficha.data, ficha.fim),
                "tecnica": ficha.tecnica,
                "gases_json": [
                    {"gas": g.gas, "litros_por_minuto": g.litros_por_minuto, "minutos": g.minutos} for g in ficha.gases
                ],
                "medicamentos_ficha_json": [
                    {"nome": m.nome, "quantidade": m.quantidade, "anotado": m.anotado} for m in ficha.medicamentos
                ],
            }
        linhas.append(linha)
    if linhas:
        supabase.table("cm_cirurgia").insert(linhas).execute()


def _gravar_glicemias(supabase, atendimento_id: str, conteudo: Conteudo) -> None:
    """Quantas glicemias o dia registra. A mesma glicemia pode estar na aferição
    e no balanço: vale a fonte que conta mais, nunca a soma das duas."""
    por_dia: dict[date, int] = {}
    for glicemia in conteudo.glicemias:
        por_dia[glicemia.data] = max(por_dia.get(glicemia.data, 0), glicemia.quantidade)
    if por_dia:
        supabase.table("cm_glicemia_dia").insert(
            [
                {"atendimento_id": atendimento_id, "data": dia.isoformat(), "quantidade": quantidade}
                for dia, quantidade in sorted(por_dia.items())
            ]
        ).execute()


# ----------------------------------------------------------------------------------
# O aviso no sino
# ----------------------------------------------------------------------------------


# As duas vagas podem terminar as duas últimas contas de um envio juntas: a
# trava do processo faz uma delas ver o aviso da outra e não repetir.
_trava_do_aviso = threading.Lock()

_ESPERANDO = ("NA_FILA", "PROCESSANDO")


def _contas(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _avisar_se_o_envio_terminou(supabase, conta: dict) -> None:
    """Quando a última conta do envio sai da fila, um aviso CONTAS_MEDICAS para
    a faturista no sino, um por envio. A conta à espera do prontuário não
    segura o aviso: ela não está na fila."""
    if not conta.get("arquivo_id") or not conta.get("faturista_id"):
        return
    with _trava_do_aviso:
        arquivo = _primeira(supabase.table("cm_arquivo").select("envio_id").eq("id", conta["arquivo_id"]))
        if arquivo is None:
            return
        envio_id = arquivo["envio_id"]
        do_envio = supabase.table("cm_arquivo").select("id").eq("envio_id", envio_id).eq("tipo", "CONTA").execute()
        ids = [a["id"] for a in do_envio.data or []]
        contas = supabase.table("cm_conta").select("situacao").in_("arquivo_id", ids).execute()
        situacoes = [c["situacao"] for c in contas.data or []]
        if any(situacao in _ESPERANDO for situacao in situacoes):
            return
        erros = situacoes.count("ERRO")
        prontas = sum(1 for situacao in situacoes if situacao not in ("ERRO", "AGUARDANDO_ARQUIVO"))
        if not prontas and not erros:
            return
        ja_avisado = _primeira(
            supabase.table("notificacoes")
            .select("id")
            .eq("destinatario_id", conta["faturista_id"])
            .eq("tipo", "CONTAS_MEDICAS")
            .eq("referencia_id", envio_id)
        )
        if ja_avisado:
            return
        com_erro = f" {_contas(erros, 'conta', 'contas')} com erro." if erros else ""
        if prontas:
            titulo = _contas(prontas, "conta pronta", "contas prontas")
            guias = "O guia está" if prontas == 1 else "Os guias estão"
            mensagem = f"{guias} na fila de Contas médicas.{com_erro}"
        else:
            titulo = f"{_contas(erros, 'conta', 'contas')} com erro"
            mensagem = "Veja o motivo na fila de Contas médicas."
        supabase.table("notificacoes").insert(
            {
                "destinatario_id": conta["faturista_id"],
                "tipo": "CONTAS_MEDICAS",
                "titulo": titulo,
                "mensagem": mensagem,
                "referencia_id": envio_id,
            }
        ).execute()
