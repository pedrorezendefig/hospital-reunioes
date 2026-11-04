"""O processamento da fila de Contas médicas (issue #1124, PRD #1113, ADR 0070).

A fila vive em `cm_conta` (ADR 0070, decisão 5): o envio deixa a conta
`NA_FILA` e um job do APScheduler, a cada 10 segundos, devolve à fila o que
ficou preso, faz o claim e entrega a conta a um executor próprio com
`CM_VAGAS` vagas (4 sem a variável).
Tudo no processo do app: sobrevive a restart porque o estado está no banco.

O pipeline de uma conta, em etapas cronometradas:

1. o texto da conta e o do prontuário, lidos do bucket, onde o envio guardou o
   texto extraído ao lado do PDF (`chave_do_texto`). Só na falta dele o PDF é
   extraído de novo, e o texto fica guardado: o prontuário de um atendimento é
   extraído uma vez e serve a todas as parciais e ao reprocesso;
2. a leitura da conta, gravada em `cm_conta_item`;
3. a leitura do prontuário, com a prescrição lida pela posição das colunas
   (as palavras das páginas dela vêm do PDF, #1133). A estrutura
   (`cm_eventos`, com o `prontuario_ate` que o aviso do envio usa,
   `cm_prescricao`, `cm_cirurgia`, `cm_glicemia_dia`, o rótulo e a idade em
   `cm_atendimento`) é gravada uma vez por arquivo de prontuário;
4. o dicionário: o medicamento da prescrição sem par na conta vai uma vez à
   IA, e a proposta já vale nesta conta (#1135);
5. a conferência por código (as diárias são contadas dentro dela), com a
   memória vigente, as tabelas, os setores e o dicionário do banco;
6. o Passo A (eventos do prontuário, uma vez por atendimento) e o Passo B (a
   conta comparada com a memória, com as conferências do código sobre cada
   linha da IA);
7. o Guia, com as linhas do código e as da IA: o reprocesso troca as linhas
   abertas e preserva as marcadas; a conta fica `A_FAZER` com nota, valores,
   parecer parcial e o tempo de cada etapa.

Leitura que não fecha (PDF sem texto, conta que não soma, prontuário
incompleto) vira `ERRO` na hora, sem nova tentativa: o mesmo arquivo daria o
mesmo erro. A IA que falhou no adaptador também vira `ERRO`, com o Guia do
código gravado. Falha inesperada volta para a fila; na terceira tentativa,
`ERRO`. Todo `ERRO` passa pelo classificador (`erro_da_conta`, issue #1337),
que dá o Código do erro, a frase e o detalhe técnico gravados na conta.

O texto dos PDFs é prontuário: o log leva a etapa, a conta e o tipo do erro
com o lugar no código, nunca a mensagem da exceção, que pode citar o texto.
"""

from __future__ import annotations

import logging
import threading
import traceback
import weakref
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import settings
from app.services import storage
from app.services import transcricao_extractor as orcamento
from app.services.contas_medicas import dicionario_ia, passo_a, passo_b, passo_c
from app.services.contas_medicas import prontuario as leitura_do_prontuario
from app.services.contas_medicas.conferencia import Conferencia, ProntuarioLido, conferir
from app.services.contas_medicas.conteudo import Conteudo, ler_conteudo
from app.services.contas_medicas.desidentificacao import desidentificar
from app.services.contas_medicas.dicionario import dicionario_do_banco
from app.services.contas_medicas.erro_da_conta import ErroDaConta, FalhaDeLeitura, classificar, tentativas_esgotadas
from app.services.contas_medicas.formulario import sem_formulario_em_branco
from app.services.contas_medicas.guia import nota_de_entrada
from app.services.contas_medicas.ia import ErroDaIA
from app.services.contas_medicas.memoria import MemoriaLida, RegraLida
from app.services.contas_medicas.operadoras import listar_setores, memoria_vigente
from app.services.contas_medicas.reanalise import MARCA_ASSIM_MESMO, marca_assim_mesmo, prontuario_da_analise
from app.services.contas_medicas.tabelas import pacote_pelo_tuss, preco
from app.services.contas_medicas.validacao import temas_das_linhas_validar
from app.services.contas_medicas_conta import (
    TOLERANCIA,
    Conta,
    ErroLeitura,
    item_que_nao_fecha,
    ler_cabecalho_da_conta,
    ler_conta,
    soma_e_total,
)
from app.services.contas_medicas_extrator import (
    MENSAGEM_PDF_GRANDE_DEMAIS,
    Pagina,
    Palavra,
    digitalizadas,
    extrair_paginas,
    extrair_palavras,
    ler_digitalizadas,
    paginas_do_texto_guardado,
    texto_para_guardar,
)
from app.services.contas_medicas_retencao import BUCKET, chave_do_texto

logger = logging.getLogger(__name__)

# Quantas contas da cabeça da fila o claim tenta antes de desistir: perder a
# primeira para a outra vaga não pode deixar a vaga parada até o próximo tique.
_CANDIDATAS = 5

# A conta em PROCESSANDO há mais que isto ficou para trás (restart do app no
# meio da análise): volta para a fila. Uma comparação de 57,6 mil tokens levou
# quase 8 minutos, e no teto de saída (128 mil) uma chamada passa de 15; com a
# leitura antes, 60 minutos não cortam análise viva.
PRAZO_DA_ANALISE = timedelta(minutes=60)
MAXIMO_DE_TENTATIVAS = 3

# Quantas análises ao mesmo tempo, no máximo (`CM_VAGAS`). A extração do PDF
# tem as próprias vagas: a análise que precisar extrair espera a vez dela.
VAGAS = settings.cm_vagas
_vagas = threading.BoundedSemaphore(VAGAS)
_executor = ThreadPoolExecutor(max_workers=VAGAS, thread_name_prefix="contas-medicas")

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


def _gravar_erro(supabase, conta: dict, erro: ErroDaConta) -> None:
    """A conta em Erro com a frase, o Código do erro e o detalhe técnico, que
    leva a hora do erro para a TI achar o momento no log."""
    _fechar_tentativa(
        supabase,
        conta,
        {
            "situacao": "ERRO",
            "erro_motivo": erro.frase,
            "erro_codigo": erro.codigo,
            "erro_detalhe": {**erro.detalhe, "em": datetime.now(UTC).isoformat()},
            "processando_desde": None,
        },
    )


def _devolver(supabase, conta: dict, erro: ErroDaConta) -> None:
    """Fim de uma tentativa que não deu certo: volta para a fila, ou, na
    terceira, Erro."""
    if (conta.get("tentativas") or 0) >= MAXIMO_DE_TENTATIVAS:
        _gravar_erro(supabase, conta, erro)
    else:
        _fechar_tentativa(supabase, conta, {"situacao": "NA_FILA", "processando_desde": None})


def devolver_presas(supabase, agora: datetime) -> int:
    """As contas em PROCESSANDO há mais de 60 minutos voltam para a fila; na
    terceira tentativa, Erro, com a etapa em que a análise estava quando o app
    reiniciou ou travou. Devolve quantas foram mexidas."""
    presas = (
        supabase.table("cm_conta")
        .select("id, tentativas, erro_detalhe")
        .eq("situacao", "PROCESSANDO")
        .lt("processando_desde", (agora - PRAZO_DA_ANALISE).isoformat())
        .execute()
        .data
        or []
    )
    for conta in presas:
        _devolver(supabase, conta, tentativas_esgotadas((conta.get("erro_detalhe") or {}).get("etapa")))
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
    """O tempo de cada etapa e a etapa em que a análise está (a do erro).
    `ao_entrar` recebe cada etapa que começa: o processamento a grava na conta,
    para a análise que o restart interrompeu dizer onde parou (#1337)."""

    def __init__(self, ao_entrar: Callable[[str], None] | None = None):
        self.tempos: dict[str, float] = {}
        self.atual: str | None = None
        # Quantas digitalizadas o OCR leu por faixa (#1398), depois do OCR: vai
        # para o detalhe técnico da conta, pronta ou em Erro.
        self.digitalizadas: dict[str, int] | None = None
        self._inicio = perf_counter()
        self._ao_entrar = ao_entrar

    @contextmanager
    def etapa(self, nome: str) -> Iterator[None]:
        self.atual = nome
        if self._ao_entrar:
            self._ao_entrar(nome)
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


def _com_digitalizadas(erro: ErroDaConta, cronometro: _Cronometro) -> ErroDaConta:
    """O erro com a contagem das digitalizadas no detalhe, quando o OCR já rodou (#1398)."""
    if cronometro.digitalizadas is None:
        return erro
    return replace(erro, detalhe={**erro.detalhe, "digitalizadas": cronometro.digitalizadas})


def _marcar_etapa(supabase, conta: dict, etapa: str) -> None:
    """A etapa que começa, no detalhe da conta em PROCESSANDO: se o app
    reiniciar no meio, a devolução das presas sabe onde a análise parou."""
    _fechar_tentativa(supabase, conta, {"erro_detalhe": {"etapa": etapa}})


def processar(supabase, conta: dict) -> None:
    """O pipeline de uma conta que o claim pegou. Nunca levanta: o fim é
    `A_FAZER`, `ERRO` ou a volta para a fila."""
    cronometro = _Cronometro(ao_entrar=lambda etapa: _marcar_etapa(supabase, conta, etapa))
    try:
        try:
            _pipeline(supabase, conta, cronometro)
        except FalhaDeLeitura as falha:
            logger.warning("[ContasMedicas] Conta %s com erro de leitura na etapa %s", conta["id"], cronometro.atual)
            _gravar_erro(supabase, conta, _com_digitalizadas(classificar(falha, cronometro.atual), cronometro))
        except ErroDaIA as erro:
            # O adaptador já tentou o que fazia sentido tentar (três vezes, ou
            # uma, nas falhas definitivas): a conta não volta para a fila.
            logger.warning("[ContasMedicas] Conta %s sem a IA na etapa %s: %s", conta["id"], cronometro.atual, erro)
            _gravar_erro(supabase, conta, _com_digitalizadas(classificar(erro, cronometro.atual), cronometro))
        except Exception as erro:
            logger.error(
                "[ContasMedicas] Conta %s falhou na etapa %s, tentativa %s: %s em %s",
                conta["id"],
                cronometro.atual,
                conta.get("tentativas"),
                type(erro).__name__,
                _onde(erro),
            )
            _devolver(supabase, conta, _com_digitalizadas(classificar(erro, cronometro.atual), cronometro))
            if (conta.get("tentativas") or 0) < MAXIMO_DE_TENTATIVAS:
                return  # voltou para a fila: o envio ainda não terminou
        _avisar_se_o_envio_terminou(supabase, conta)
    except Exception as erro:
        # O banco falhou no fechamento: a conta fica PROCESSANDO e volta pela
        # devolução das presas, em 60 minutos.
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
        raise FalhaDeLeitura("vencido")
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
            if paginas.motivo == MENSAGEM_PDF_GRANDE_DEMAIS:
                raise FalhaDeLeitura("grande", paginas=arquivo.get("paginas") or "muitas")
            raise FalhaDeLeitura("ilegivel")
        storage.upload_private(supabase, BUCKET, chave_do_texto(chave), texto_para_guardar(paginas), "text/plain")
    if all(pagina.sem_texto for pagina in paginas):
        raise FalhaDeLeitura("sem_texto")
    return paginas


def _com_ocr(supabase, arquivo: dict, paginas: list[Pagina], lida) -> list[Pagina]:
    """As páginas digitalizadas do Prontuário com o texto lido por OCR (#1191) e a
    qualidade da leitura (#1398). As do Atendimento e do período da conta vão
    primeiro: sob o prazo, o corte cai nas que não importam para ela. Roda aqui,
    na fila, e não no envio: o OCR de um prontuário real passa dos 30 s do proxy.
    O texto do OCR não vai para o texto guardado no bucket, que fica no formato
    que a versão anterior lê. Sem o PDF, seguem sem texto e não lidas."""
    pedidas = digitalizadas(paginas)
    if not pedidas:
        return paginas
    pdf = _baixar(supabase, arquivo["chave_bucket"])
    if pdf is None:
        logger.warning("[ContasMedicas] OCR sem o PDF no bucket: as paginas digitalizadas seguem sem texto")
        return [replace(p, qualidade=leitura_do_prontuario.NAO_LIDA) if p.numero in pedidas else p for p in paginas]
    primeiro = leitura_do_prontuario.digitalizadas_da_conta(
        [p.texto for p in paginas], lida.atendimento, lida.periodo_inicio, lida.periodo_fim
    )
    return ler_digitalizadas(bytes(pdf), paginas, primeiro=primeiro)


def _contagem_das_digitalizadas(qualidades: dict[int, str]) -> dict[str, int]:
    """Quantas digitalizadas saíram em cada faixa, para o detalhe técnico da conta
    (#1398): só números, nunca texto do prontuário."""
    return {faixa: sum(1 for q in qualidades.values() if q == faixa) for faixa in leitura_do_prontuario.QUALIDADES}


def _palavras_da_prescricao(supabase, arquivo: dict, estrutura) -> dict[int, list[Palavra]]:
    """As palavras com posição das páginas de prescrição, lidas do PDF (#1133).
    Sem o PDF ou sem a leitura, a prescrição fica com o leitor por linha."""
    paginas = {n for d in estrutura.documentos if d.familia == "PRESCRICAO" for n in d.paginas}
    if not paginas:
        return {}
    pdf = _baixar(supabase, arquivo["chave_bucket"])
    palavras = extrair_palavras(bytes(pdf), paginas) if pdf is not None else None
    if not isinstance(palavras, dict):
        logger.warning("[ContasMedicas] Prescricao lida por linha: as palavras do PDF nao vieram")
        return {}
    return palavras


def _pipeline(supabase, conta: dict, cronometro: _Cronometro) -> None:
    atendimento = _primeira(supabase.table("cm_atendimento").select("*").eq("id", conta["atendimento_id"])) or {}

    with cronometro.etapa("texto_da_conta"):
        arquivo_da_conta = _primeira(supabase.table("cm_arquivo").select("*").eq("id", conta.get("arquivo_id")))
        if arquivo_da_conta is None:
            raise FalhaDeLeitura("vencido")
        paginas_da_conta = _texto(supabase, arquivo_da_conta)

    with cronometro.etapa("leitura_da_conta"):
        textos_da_conta = [pagina.texto for pagina in paginas_da_conta]
        lida = ler_conta(textos_da_conta)
        if isinstance(lida, ErroLeitura):
            raise _leitura_da_conta_que_nao_fecha(textos_da_conta)
        _gravar_itens(supabase, conta["id"], lida)

    with cronometro.etapa("texto_do_prontuario"):
        arquivo_do_prontuario = prontuario_da_analise(supabase, conta["atendimento_id"])
        if arquivo_do_prontuario is None:
            raise FalhaDeLeitura("sem_prontuario")
        paginas_do_prontuario = _com_ocr(supabase, arquivo_do_prontuario, _texto(supabase, arquivo_do_prontuario), lida)
        textos = [pagina.texto for pagina in paginas_do_prontuario]
        qualidades = {p.numero: p.qualidade for p in paginas_do_prontuario if p.qualidade}
        # Prontuário sem digitalizada fica sem a contagem: zeros só poluiriam o detalhe.
        cronometro.digitalizadas = _contagem_das_digitalizadas(qualidades) if qualidades else None

    with cronometro.etapa("leitura_do_prontuario"):
        try:
            estrutura = leitura_do_prontuario.ler_prontuario(textos, lida.atendimento, qualidades)
        except leitura_do_prontuario.ErroLeitura as erro:
            raise FalhaDeLeitura("incompleto", declarado=erro.declarado, vieram=erro.vieram) from None
        # As folhas digitalizadas que sustentam a conta não deram para ler (#1400):
        # Erro antes do dicionário, sem gastar IA. É por conta, com o período dela.
        # "Analisar assim mesmo" (#1401) pula o bloqueio enquanto o prontuário
        # for o mesmo do clique; a ressalva "Confira à mão" sai no Parecer parcial.
        assim_mesmo = marca_assim_mesmo(conta) == arquivo_do_prontuario["id"]
        if not assim_mesmo and (
            bloqueio := leitura_do_prontuario.bloqueio_das_digitalizadas(
                estrutura, textos, lida.itens, lida.periodo_inicio, lida.periodo_fim
            )
        ):
            causa, dados = bloqueio
            raise FalhaDeLeitura(causa, **dados)
        palavras = _palavras_da_prescricao(supabase, arquivo_do_prontuario, estrutura)
        conteudo = ler_conteudo(textos, estrutura, palavras)
        prontuario = ProntuarioLido(estrutura, conteudo, textos)
        gravou = _gravar_prontuario(supabase, conta["atendimento_id"], arquivo_do_prontuario["id"], prontuario)
        # A contagem do formulário em branco é de prontuários: só o arquivo novo soma.
        estrutura = sem_formulario_em_branco(supabase, estrutura, aprender=gravou)
        prontuario = ProntuarioLido(estrutura, conteudo, textos)

    with cronometro.etapa("dicionario"), _trava_do_prontuario(conta["atendimento_id"]):
        # O termo de medicamento sem par vai uma vez à IA, antes da
        # conferência: a proposta já vale para esta conta. A trava faz a
        # parcial que chega junto esperar a proposta da outra e lê-la do
        # dicionário, sem perguntar de novo.
        dicionario = dicionario_do_banco(supabase)
        if dicionario_ia.propor_termos(
            supabase, prontuario, lida, dicionario, conta_id=conta["id"], atendimento_id=conta["atendimento_id"]
        ):
            dicionario = dicionario_do_banco(supabase)

    with cronometro.etapa("conferencia"):
        operadora_id = atendimento.get("operadora_id")
        memoria = memoria_vigente(supabase, operadora_id) if operadora_id else None
        if memoria is None:
            raise FalhaDeLeitura("sem_memoria", operadora=_sigla(supabase, operadora_id))
        memoria_lida = _memoria_lida(memoria)
        busca_de_preco = _busca_de_preco(supabase, operadora_id)
        buscas = {
            "setores": {s["nome_mv"]: s["acomodacao"] for s in listar_setores(supabase) if s.get("acomodacao")},
            "dicionario": dicionario,
            "pacote_do_tuss": lambda tuss, data: pacote_pelo_tuss(supabase, operadora_id, tuss, data),
        }
        conferencia = conferir(lida, prontuario, memoria_lida, busca_de_preco, **buscas)

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

        with cronometro.etapa("conferencia_com_eventos"):
            # As conferências que dependem do texto livre ("se necessário" e classe
            # de UTI do dia) rodam com os eventos que a IA leu (#1134).
            conferencia = conferir(lida, prontuario, memoria_lida, busca_de_preco, eventos=eventos, **buscas)

        with cronometro.etapa("passo_b"):
            da_ia = passo_b.comparar_com_a_ia(
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
    # O parecer junta o que a leitura por código não teve, as folhas digitalizadas
    # da conta a conferir à mão (#1399, pelo período desta parcial) e o que a IA apontou.
    parecer = [
        *estrutura.parecer_parcial,
        *leitura_do_prontuario.ressalva_das_digitalizadas(estrutura, lida.periodo_inicio, lida.periodo_fim),
        *passo_a.parecer(eventos),
    ]
    tempos = {**cronometro.tempos, "total": cronometro.total()}
    _fechar_tentativa(
        supabase,
        conta,
        {
            "situacao": "A_FAZER",
            "erro_motivo": None,
            "erro_codigo": None,
            "erro_detalhe": None,
            "total_lancado": float(lida.total),
            "nota_bruta": nota.nota,
            "nota_entrada": nota.nota,
            "valor_apontado": float(nota.apontado),
            "valor_em_validacao": float(nota.em_validacao),
            "parecer_parcial": bool(parecer),
            # A linha da IA que as conferências derrubaram fica registrada, com o motivo.
            "faltantes": {
                "itens": parecer,
                "tempos_por_etapa_s": tempos,
                "descartadas_ia": list(da_ia.descartadas),
                "digitalizadas": cronometro.digitalizadas,
                # A marca do "Analisar assim mesmo" segue com o mesmo prontuário (#1401).
                **({MARCA_ASSIM_MESMO: arquivo_do_prontuario["id"]} if assim_mesmo else {}),
            },
            "memoria_versao_id": memoria["memoria_versao_id"],
            "pronta_em": datetime.now(UTC).isoformat(),
        },
    )
    logger.info("[ContasMedicas] Conta %s pronta em %ss", conta["id"], tempos["total"])
    # Depois da conta pronta: o Passo C não atrasa o A fazer da faturista nem
    # entra no tempo das etapas, e a demora dele não conta no prazo da análise.
    _lembrar_a_coordenacao(
        supabase,
        conta,
        operadora_id=operadora_id,
        lida=lida,
        prontuario=prontuario,
        eventos=eventos,
        preco=busca_de_preco,
        coluna=conferencia.coluna,
    )


def _leitura_da_conta_que_nao_fecha(textos: list[str]) -> FalhaDeLeitura:
    """Por que a conta não foi lida: o cabeçalho sem atendimento e plano, a
    soma dos itens que não bate com o total (com os dois números) ou, com a
    soma certa, o item em que quantidade vezes unitário não dá o total da linha."""
    if isinstance(ler_cabecalho_da_conta(textos), ErroLeitura):
        return FalhaDeLeitura("cabecalho")
    soma, total = soma_e_total(textos)
    if total is None:
        return FalhaDeLeitura("sem_total", soma=soma)
    errado = item_que_nao_fecha(textos) if abs(soma - total) <= TOLERANCIA else None
    if errado:
        item, esperado = errado
        return FalhaDeLeitura("item", codigo=item.codigo, pagina=item.pagina, esperado=esperado, linha=item.total)
    return FalhaDeLeitura("soma", soma=soma, total=total)


def _sigla(supabase, operadora_id: str | None) -> str:
    """A sigla da operadora, para a frase da operadora sem memória."""
    operadora = (
        _primeira(supabase.table("cm_operadora").select("sigla").eq("id", operadora_id)) if operadora_id else None
    )
    return (operadora or {}).get("sigla") or "desta conta"


def _lembrar_a_coordenacao(
    supabase,
    conta: dict,
    *,
    operadora_id: str,
    lida: Conta,
    prontuario: ProntuarioLido,
    eventos: dict[str, Any],
    preco,
    coluna: str | None,
) -> None:
    """O Passo C (#1143): os lembretes da coordenação, depois do Passo A. A
    faturista não sabe que eles existem: fica fora do cronômetro (o tempo das
    etapas vai para a conta dela) e a falha só vai para o log, sem mudar a
    situação da conta."""
    try:
        passo_c.lembrar_a_coordenacao(
            supabase,
            conta_id=conta["id"],
            atendimento_id=conta["atendimento_id"],
            operadora_id=operadora_id,
            conta=lida,
            prontuario=prontuario,
            eventos=eventos,
            preco=preco,
            coluna=coluna,
        )
    except Exception as erro:
        logger.error("[ContasMedicas] Conta %s sem o Passo C: %s em %s", conta["id"], type(erro).__name__, _onde(erro))


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
    gravadas = supabase.table("cm_guia_linha").insert(novas).execute().data or []
    # A linha Validar entra na fila de Validação aqui, pela ação: o código e a
    # IA gravam por este mesmo ponto.
    temas_das_linhas_validar(supabase, conta_id, gravadas)
    return marcadas + gravadas


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


# As vagas pegam juntas as parciais do mesmo atendimento (o caso normal
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


def _gravar_prontuario(supabase, atendimento_id: str, arquivo_id: str, prontuario: ProntuarioLido) -> bool:
    """A estrutura do prontuário no banco, uma vez por arquivo: a segunda
    parcial e o reprocesso acham o mesmo arquivo gravado e seguem. Prontuário
    novo (atualizado) troca o anterior inteiro. Devolve se gravou."""
    with _trava_do_prontuario(atendimento_id):
        return _gravar_prontuario_uma_vez(supabase, atendimento_id, arquivo_id, prontuario)


def _gravar_prontuario_uma_vez(supabase, atendimento_id: str, arquivo_id: str, prontuario: ProntuarioLido) -> bool:
    ultimo = _primeira(
        supabase.table("cm_eventos").select("*").eq("atendimento_id", atendimento_id).order("criado_em", desc=True)
    )
    if ultimo and (ultimo.get("eventos_json") or {}).get("arquivo_id") == arquivo_id:
        return False
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
    return True


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


# Duas vagas podem terminar as duas últimas contas de um envio juntas: a
# trava do processo faz uma delas ver o aviso da outra e não repetir.
_trava_do_aviso = threading.Lock()

_ESPERANDO = ("NA_FILA", "PROCESSANDO")


def _contas(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def _avisar_se_o_envio_terminou(supabase, conta: dict) -> None:
    """Quando a última conta do envio sai da fila, um aviso CONTAS_MEDICAS para
    quem enviou (`cm_envio.usuario_id`), no sino, um por envio. A faturista da
    conta é quem a puxa da Fila depois (ADR 0073). A conta à espera do
    prontuário não segura o aviso: ela não está na fila."""
    if not conta.get("arquivo_id"):
        return
    with _trava_do_aviso:
        arquivo = _primeira(supabase.table("cm_arquivo").select("envio_id").eq("id", conta["arquivo_id"]))
        if arquivo is None:
            return
        envio_id = arquivo["envio_id"]
        envio = _primeira(supabase.table("cm_envio").select("usuario_id").eq("id", envio_id))
        quem_enviou = (envio or {}).get("usuario_id")
        if not quem_enviou:
            return
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
            .eq("destinatario_id", quem_enviou)
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
                "destinatario_id": quem_enviou,
                "tipo": "CONTAS_MEDICAS",
                "titulo": titulo,
                "mensagem": mensagem,
                "referencia_id": envio_id,
            }
        ).execute()
