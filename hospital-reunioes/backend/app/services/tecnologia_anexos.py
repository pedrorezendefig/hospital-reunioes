"""O Anexo da Demanda (issue #1061, PRD #1056, ADR 0069).

O print de tela que vem junto da Demanda. Vive SO no app e nunca vai para o
GitHub: o repositorio e publico, e print do hospital carrega nome de paciente,
de colaborador, protocolo da Ouvidoria.

Desde a ADR 0077 o print entra por uma porta so, o chat da aba (decisao 8), e
um lugar so decide o que se faz com ele:

- **anexar**: a imagem passa pela regra do print (formatos e teto, com as
  mesmas frases de recusa), sobe ao bucket privado com caminho sorteado e so
  depois ganha a linha no banco;
- **para quem desenvolve**: a rota de automacao entrega a URL assinada de vida
  curta ao agente que pega a issue (issue #1063);
- **apagar os vencidos**: o cron tira os binarios 30 dias depois de a Etapa
  chegar a Em producao, e na rodada seguinte quando ela e Nao sera feita (ADR
  0077, issue #1382). Fica o registro (nome, quem, quando) marcado apagado.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from app.config import settings
from app.services import storage, transcricao_extractor
from app.services.assistente_tecnologia import (
    LIMITE_DA_IMAGEM,
    MOTIVO_IMAGEM_GRANDE,
    MOTIVO_TIPO_FORA_DA_LISTA,
    TIPOS_DE_ANEXO,
    TIPOS_DE_IMAGEM,
    motivo_documento_grande,
)
from app.services.tecnologia import ESTADOS_FECHADOS, instante_do_banco
from app.services.tecnologia_vinculo import ETAPA_EM_PRODUCAO, ETAPA_NAO_SERA_FEITA
from app.services.transcricao_extractor_filho import MENSAGEM_PDF_ESCANEADO

logger = logging.getLogger(__name__)

TABELA_ANEXOS = "tecnologia_anexos"

# Ate dez por Demanda (ADR 0069, decisao 1), somando imagens e documentos
# (emenda de 09/11/2026). O mesmo teto vive no CHECK da coluna `ordem`
# (migration 115): contornar a API nao contorna o teto.
LIMITE_DE_ANEXOS = 10
MOTIVO_ANEXOS_DEMAIS = (
    f"Esta Demanda já tem {LIMITE_DE_ANEXOS} anexos, somando prints e documentos, o máximo por Demanda. "
    "Escolha os que mais ajudam, ou escreva o resto na conversa."
)
MOTIVO_ARQUIVO_VAZIO = "O arquivo chegou vazio: não há o que anexar. Escolha o arquivo de novo."
MOTIVO_DEMANDA_ENCERRADA = "Esta Demanda está encerrada: imagem só entra em Demanda aberta. Reabra antes de anexar."
MOTIVO_NAO_GUARDOU = "Não foi possível guardar a imagem agora. Tente de novo em instantes."

# Dez minutos: o script de quem desenvolve baixa o print logo depois de pedir.
# Link colado fora do app morre antes de virar acesso permanente ao print.
EXPIRACAO_DA_URL_SEGUNDOS = 600

# Em producao, o diretor ainda confere a correcao com o print na mao: o binario
# so sai 30 dias depois da subida (ADR 0077). O relogio e o `entregue_em`, que a
# subida reescreve com a data dela (`tecnologia_sincronizacao`).
PRAZO_DEPOIS_DE_EM_PRODUCAO = timedelta(days=30)


class AnexoRecusadoError(Exception):
    """A recusa, com a frase que a pessoa le e o status HTTP que a rota devolve."""

    def __init__(self, motivo: str, status_code: int = 422):
        super().__init__(motivo)
        self.status_code = status_code


def _bucket() -> str:
    return settings.supabase_storage_bucket_anexos_tecnologia


def anexar(supabase, *, demanda: dict, nome: str, conteudo: bytes, quem_id: str) -> dict:
    """Guarda a imagem junto da Demanda e devolve a linha gravada.

    O binario sobe ANTES da linha: sem binario nao existe anexo, e uma linha que
    aponta para o vazio quebraria o card. Se a linha nao entrar, o binario sai
    na hora, porque nada mais o alcancaria depois.

    Toda recusa vem antes do bucket: arquivo recusado nao deixa rastro.
    """
    if str(demanda.get("estado") or "") in ESTADOS_FECHADOS:
        # O apagamento so roda no ato de encerrar: binario que entrasse depois
        # ficaria no bucket para sempre, dado pessoal sem dono.
        raise AnexoRecusadoError(MOTIVO_DEMANDA_ENCERRADA)
    extensao = os.path.splitext(nome or "")[1].lower()
    tipo = TIPOS_DE_ANEXO.get(extensao)
    if tipo is None:
        raise AnexoRecusadoError(MOTIVO_TIPO_FORA_DA_LISTA)
    if not conteudo:
        raise AnexoRecusadoError(MOTIVO_ARQUIVO_VAZIO)
    if len(conteudo) > tipo.teto_bytes:
        motivo = MOTIVO_IMAGEM_GRANDE if tipo.classe == "imagem" else motivo_documento_grande(extensao)
        raise AnexoRecusadoError(motivo, status_code=413)

    demanda_id = str(demanda["id"])
    existentes = supabase.table(TABELA_ANEXOS).select("ordem").eq("demanda_id", demanda_id).execute().data or []
    # A posicao seguinte a MAIOR, e nao a contagem: as linhas nunca saem do
    # banco (o apagado fica como registro), entao as duas dao o mesmo, mas a
    # maior nao repete posicao se um dia faltar uma no meio.
    ordem = max((int(linha.get("ordem") or 0) for linha in existentes), default=0) + 1
    if ordem > LIMITE_DE_ANEXOS:
        raise AnexoRecusadoError(MOTIVO_ANEXOS_DEMAIS)

    # Caminho sorteado, como na Ouvidoria: o nome original pode carregar dado
    # pessoal ("prontuario do Joao.png") e nao vira parte de caminho.
    path = f"demanda-{demanda_id}/{uuid.uuid4().hex}{extensao}"
    content_type = tipo.content_type
    if not storage.upload_private(supabase, bucket=_bucket(), path=path, content=conteudo, content_type=content_type):
        raise AnexoRecusadoError(MOTIVO_NAO_GUARDOU, status_code=503)

    linha = {
        "demanda_id": demanda_id,
        "ordem": ordem,
        "storage_path": path,
        "nome_original": nome,
        "content_type": content_type,
        "tamanho_bytes": len(conteudo),
        "anexado_por": quem_id,
        "apagado_em": None,
    }
    try:
        return supabase.table(TABELA_ANEXOS).insert(linha).execute().data[0]
    except Exception as exc:
        # Largo de proposito: `APIError`, o `httpx.HTTPError` cru do timeout e a
        # resposta sem linha (`IndexError`) tem o mesmo desfecho. Inclusive a
        # corrida de dois envios na mesma posicao, que o UNIQUE (demanda_id,
        # ordem) recusa. Sem a linha, o binario e orfao que ninguem alcanca:
        # limpar agora e a unica chance, e se falhar o caminho fica no log.
        if not storage.delete_file(supabase, _bucket(), path):
            logger.error("Anexo da Demanda %s órfão no bucket após falha de registro: %s", demanda_id, path)
        logger.exception("Falha ao registrar o anexo da Demanda %s", demanda_id)
        raise AnexoRecusadoError(MOTIVO_NAO_GUARDOU, status_code=503) from exc


def apagar_todos(supabase, demanda_id: str) -> int:
    """Tira do bucket os binarios da Demanda e marca cada registro apagado.

    Chamado pelo cron em `apagar_vencidos` (ADR 0077). A sincronizacao da
    Etapa nunca chega aqui: em Entregue o diretor ainda confere com o print na
    mao.

    A marca de cada anexo entra logo depois da confirmacao DELE, e nao todas no
    fim (a regra do `storage.delete_file`): uma falha no meio deixa marcados so
    os que sairam de verdade. O que o Storage nao confirmou fica sem a marca,
    com o caminho no log, e a passada seguinte tenta de novo.

    Nunca levanta: falha aqui vira log com o caminho do arquivo, e o cron segue
    para a Demanda seguinte.

    Devolve quantos binarios sairam.
    """
    try:
        guardados = [linha for linha in ler(supabase, demanda_id) if not linha.get("apagado_em")]
    except Exception:
        logger.exception("Falha ao ler os anexos da Demanda %s para apagar", demanda_id)
        return 0
    sairam = 0
    for linha in guardados:
        path = linha["storage_path"]
        if not storage.delete_file(supabase, _bucket(), path):
            logger.error("Anexo da Demanda %s não saiu do bucket ao apagar: %s", demanda_id, path)
            continue
        sairam += 1
        try:
            supabase.table(TABELA_ANEXOS).update({"apagado_em": datetime.now(UTC).isoformat()}).eq(
                "id", linha["id"]
            ).execute()
        except Exception:
            logger.exception(
                "Anexo %s da Demanda %s saiu do bucket, mas a marca de apagado não entrou: %s",
                linha["id"],
                demanda_id,
                path,
            )
    return sairam


def _print_venceu(demanda: dict, agora: datetime) -> bool:
    etapa = demanda.get("etapa")
    if etapa == ETAPA_NAO_SERA_FEITA:
        return True
    if etapa != ETAPA_EM_PRODUCAO:
        return False
    # Sem data legivel, fica: apagar e definitivo, e a duvida protege o print.
    subiu_em = instante_do_banco(demanda.get("entregue_em"))
    return subiu_em is not None and agora - subiu_em >= PRAZO_DEPOIS_DE_EM_PRODUCAO


def apagar_vencidos(supabase, agora: datetime | None = None) -> int:
    """A passada do cron: apaga os prints das Demandas em Em producao ha 30
    dias ou mais e das em Nao sera feita (ADR 0077, issue #1382).

    Parte dos anexos ainda guardados, e nao das Demandas: quase toda Demanda
    entregue ja nao tem o que apagar, e a passada de hora em hora fica do
    tamanho do que sobrou no bucket. Cada Demanda vencida passa pelo
    `apagar_todos`, com a mesma regra de marca e de log.

    Devolve quantos binarios sairam.
    """
    agora = agora or datetime.now(UTC)
    guardados = supabase.table(TABELA_ANEXOS).select("demanda_id").is_("apagado_em", "null").execute().data or []
    ids = sorted({str(linha["demanda_id"]) for linha in guardados})
    if not ids:
        return 0
    demandas = (
        supabase.table("tecnologia_demandas").select("id, etapa, entregue_em").in_("id", ids).execute().data or []
    )
    return sum(apagar_todos(supabase, str(d["id"])) for d in demandas if _print_venceu(d, agora))


def posicoes_livres(supabase, demanda_id: str) -> int:
    """Quantos anexos ainda cabem na Demanda, pela mesma conta do `anexar`: a
    posicao seguinte a maior ja usada, apagado ou nao."""
    existentes = supabase.table(TABELA_ANEXOS).select("ordem").eq("demanda_id", demanda_id).execute().data or []
    return LIMITE_DE_ANEXOS - max((int(linha.get("ordem") or 0) for linha in existentes), default=0)


def quantos_guardados(supabase, demanda_id: str) -> int:
    """Quantas imagens a Demanda ainda guarda: o N da frase "Anexos: N imagens
    na Demanda" da issue (issue #1062). O apagado nao conta: o binario saiu, e
    quem desenvolve nao teria o que buscar."""
    return sum(1 for linha in ler(supabase, demanda_id) if not linha.get("apagado_em"))


def ler(supabase, demanda_id: str) -> list[dict]:
    """As linhas dos anexos da Demanda, na ordem em que entraram."""
    result = supabase.table(TABELA_ANEXOS).select("*").eq("demanda_id", demanda_id).order("ordem").execute()
    return list(result.data or [])


def para_quem_desenvolve(supabase, demanda_id: str) -> list[dict]:
    """Os anexos que quem desenvolve baixa pela ponte (issue #1063): nome, tipo
    e URL assinada de vida curta de cada imagem ainda guardada.

    O apagado fica de fora: o binario saiu, e nao ha o que baixar. Quem anexou e
    quando ficam no app: o script so precisa do arquivo.
    """
    return [
        {
            "nome": linha.get("nome_original") or "",
            "tipo": linha.get("content_type") or "",
            "url": storage.signed_url(supabase, _bucket(), linha["storage_path"], EXPIRACAO_DA_URL_SEGUNDOS),
        }
        for linha in ler(supabase, demanda_id)
        if not linha.get("apagado_em")
    ]


# ─── O print do chat (issue #1062; ADR 0077, decisao 8) ──────────────────────
#
# A rota do print le a imagem e devolve a descricao; a imagem nao vira Anexo
# ali, porque a Demanda pode ainda nao existir (o primeiro turno a faz nascer).
# Ela fica guardada SO na memoria do processo, com um identificador efemero que
# a tela leva junto da fala, e vira Anexo quando a fala entra na conversa. Sem
# isso, nada persiste: nem linha, nem binario no bucket. O que sobra na memoria
# sai pelo prazo ou pelo teto, e um reinicio do backend tambem limpa.
#
# Memoria, e nao bucket com faxina: o diretor que descarta a conversa nao deixa
# print do hospital em lugar nenhum, nem por uma hora. O uvicorn deste app sobe
# com um worker so, entao a memoria e uma so.

PRAZO_DO_PRINT_SEGUNDOS = 2 * 60 * 60
# Teto de memoria: vinte prints no limite de 5 MB. O mais antigo sai primeiro.
TETO_DE_BYTES_DOS_PRINTS = 20 * LIMITE_DA_IMAGEM

_prints: OrderedDict[str, dict] = OrderedDict()
_trava_dos_prints = threading.Lock()


def _jogar_fora_vencidos(agora: float) -> None:
    for print_id in [p for p, guardado in _prints.items() if guardado["vence_em"] <= agora]:
        del _prints[print_id]
    while sum(len(g["conteudo"]) for g in _prints.values()) > TETO_DE_BYTES_DOS_PRINTS:
        _prints.popitem(last=False)


def guardar_print(*, quem_id: str, nome: str, conteudo: bytes) -> str:
    """Guarda na memoria o print que a rota acabou de descrever e devolve o
    identificador efemero que a tela leva junto da fala do chat."""
    return _guardar(quem_id=quem_id, nome=nome, conteudo=conteudo, texto=None)


def _guardar(*, quem_id: str, nome: str, conteudo: bytes, texto: str | None) -> str:
    guardado_id = uuid.uuid4().hex
    agora = time.monotonic()
    with _trava_dos_prints:
        _prints[guardado_id] = {
            "quem_id": str(quem_id),
            "nome": nome,
            "conteudo": conteudo,
            "texto": texto,
            "vence_em": agora + PRAZO_DO_PRINT_SEGUNDOS,
        }
        _jogar_fora_vencidos(agora)
    return guardado_id


def tirar_print(*, quem_id: str, print_id: str) -> dict | None:
    """O print guardado, que sai da memoria ao ser tirado: entra uma vez so.

    `None` quando ele venceu, saiu pelo teto, o backend reiniciou, ou e de outra
    pessoa (e ai ele fica onde esta: nao e de quem pediu)."""
    with _trava_dos_prints:
        _jogar_fora_vencidos(time.monotonic())
        guardado = _prints.get(print_id)
        if not guardado or guardado["quem_id"] != str(quem_id):
            return None
        del _prints[print_id]
    return guardado


def esquecer_prints() -> None:
    """Esvazia a memoria dos prints (testes)."""
    with _trava_dos_prints:
        _prints.clear()


def aviso_dos_prints(quantos: int) -> str | None:
    """A frase da fala do chat que entrou sem algum dos prints."""
    if quantos <= 0:
        return None
    sujeito = "Um print da conversa não entrou" if quantos == 1 else f"{quantos} prints da conversa não entraram"
    return f"{sujeito} como imagem. Mande o print de novo na conversa."


def anexar_prints(supabase, *, demanda: dict, print_ids: list[str], quem_id: str) -> str | None:
    """Grava como Anexo os prints que a fala do chat trouxe e devolve o aviso
    dos que nao entraram, ou `None`. Nunca levanta: a fala ja entrou."""
    return aviso_dos_prints(_anexar_guardados(supabase, demanda=demanda, ids=print_ids, quem_id=quem_id))


def _anexar_guardados(supabase, *, demanda: dict, ids: list[str], quem_id: str) -> int:
    """Tira da memoria e grava como Anexo cada arquivo guardado; devolve
    quantos nao entraram. Nunca levanta."""
    faltaram = 0
    for guardado_id in dict.fromkeys(ids):
        guardado = tirar_print(quem_id=quem_id, print_id=guardado_id)
        if guardado is None:
            faltaram += 1
            continue
        try:
            anexar(supabase, demanda=demanda, nome=guardado["nome"], conteudo=guardado["conteudo"], quem_id=quem_id)
        except AnexoRecusadoError:
            logger.warning("Anexo do chat recusado na Demanda %s", demanda.get("id"))
            faltaram += 1
        except Exception:
            # Largo de proposito, como o resto do modulo: o `APIError` e o
            # `httpx.HTTPError` cru do PostgREST virariam 500 com a fala ja
            # gravada, e a tela convidaria a manda-la de novo.
            logger.exception("Falha ao gravar o anexo do chat na Demanda %s", demanda.get("id"))
            faltaram += 1
    return faltaram


# ─── O documento do chat (issue #1520, ADR 0069, emenda de 09/11/2026) ───────
#
# A rota do documento le o arquivo e devolve o identificador, como a do print,
# mas sem IA: o texto sai do extrator da Ata Guiada, com o parser em processo
# separado (issue #758). Os bytes e o texto ficam na MESMA memoria do print, pela
# mesma razao: o documento so vira Anexo quando a fala que o traz entra na
# conversa. O texto extraido vai junto da fala, guardado nela (e nao no Anexo):
# o binario sai pelo cron, e o texto que o agente leu fica, como a descricao do
# print fica.

# O teto do texto que o agente le de uma vez (ADR 0069, emenda de 09/11/2026).
# Acima disso a recusa pede para dividir: resumir antes cortaria o que o
# planejamento precisa, e o que o resumo cortou nao volta.
LIMITE_DE_CARACTERES_DO_DOCUMENTO = 100_000

MOTIVO_TEXTO_GRANDE = (
    f"O texto desse documento passa de {LIMITE_DE_CARACTERES_DO_DOCUMENTO // 1000} mil caracteres, "
    "o máximo que o assistente lê de uma vez. Divida o documento em partes e mande uma de cada vez."
)
MOTIVO_PDF_SEM_TEXTO = (
    "Esse PDF é uma imagem de papel, sem texto para ler. Mande as páginas como print, pelo mesmo botão."
)
MOTIVO_DOCUMENTO_ILEGIVEL = (
    "Não deu para ler o texto desse arquivo. Confira se ele abre no computador e mande de novo, "
    "ou cole o texto na conversa."
)
MOTIVO_DOCUMENTO_SUMIU = (
    "O documento não está mais guardado: passou o prazo ou o sistema reiniciou. Anexe o arquivo de novo."
)


def extensao_do_documento(nome: str) -> str:
    """A extensao do documento, ou a recusa com a frase que diz o que entra.

    Pelo NOME, e nunca pelo `content-type` do cliente (ADR 0034). Vem antes de
    ler os bytes: nao ha por que trazer um video de 40 MB a memoria para
    recusa-lo pelo nome.
    """
    extensao = os.path.splitext(nome or "")[1].lower()
    tipo = TIPOS_DE_ANEXO.get(extensao)
    if tipo is None or tipo.classe != "documento":
        raise AnexoRecusadoError(MOTIVO_TIPO_FORA_DA_LISTA)
    return extensao


async def texto_do_documento(*, nome: str, conteudo: bytes) -> str:
    """O texto inteiro do documento, ou a recusa com frase e status.

    Toda recusa sai daqui como `AnexoRecusadoError`, que a rota so traduz: o
    tamanho pelo teto do tipo (413), o arquivo vazio, o PDF escaneado (que vai
    como print), o texto acima do teto de caracteres e a leitura que falhou.
    A fila cheia do extrator e 503: o arquivo esta bom, e quem tenta de novo
    daqui a pouco consegue.
    """
    extensao = extensao_do_documento(nome)
    if len(conteudo) > TIPOS_DE_ANEXO[extensao].teto_bytes:
        raise AnexoRecusadoError(motivo_documento_grande(extensao), status_code=413)
    if not conteudo:
        raise AnexoRecusadoError(MOTIVO_ARQUIVO_VAZIO)
    try:
        texto, _ = await transcricao_extractor.extrair_texto_async(nome, conteudo)
    except ValueError as erro:
        if str(erro) == MENSAGEM_PDF_ESCANEADO:
            raise AnexoRecusadoError(MOTIVO_PDF_SEM_TEXTO) from erro
        if str(erro) == transcricao_extractor.MENSAGEM_FILA_CHEIA:
            raise AnexoRecusadoError(transcricao_extractor.MENSAGEM_FILA_CHEIA, status_code=503) from erro
        raise AnexoRecusadoError(MOTIVO_DOCUMENTO_ILEGIVEL) from erro
    if len(texto) > LIMITE_DE_CARACTERES_DO_DOCUMENTO:
        raise AnexoRecusadoError(MOTIVO_TEXTO_GRANDE)
    return texto


def guardar_documento(*, quem_id: str, nome: str, conteudo: bytes, texto: str) -> str:
    """Guarda na memoria o documento lido, com o texto, e devolve o
    identificador efemero que a tela leva junto da fala do chat."""
    return _guardar(quem_id=quem_id, nome=nome, conteudo=conteudo, texto=texto)


def ver_documento(*, quem_id: str, documento_id: str) -> dict | None:
    """O documento guardado, SEM tira-lo da memoria: o turno ainda pode falhar,
    e o reenvio da mesma fala tem que achar o documento. Sai pelo
    `anexar_documentos`, depois que a fala entrou.

    `None` quando ele venceu, saiu pelo teto, o backend reiniciou, e de outra
    pessoa ou e um print (que nao tem texto)."""
    with _trava_dos_prints:
        _jogar_fora_vencidos(time.monotonic())
        guardado = _prints.get(documento_id)
        if not guardado or guardado["quem_id"] != str(quem_id) or guardado.get("texto") is None:
            return None
        return dict(guardado)


def aviso_dos_documentos(quantos: int) -> str | None:
    """A frase da fala do chat cujo documento nao virou Anexo. O agente leu o
    texto; o que faltou foi o original, que quem desenvolve baixaria."""
    if quantos <= 0:
        return None
    sujeito = "Um documento da conversa não ficou" if quantos == 1 else f"{quantos} documentos da conversa não ficaram"
    return f"{sujeito} guardado como anexo. O assistente leu o texto; anexe o arquivo de novo se quiser guardá-lo."


def anexar_documentos(supabase, *, demanda: dict, documento_ids: list[str], quem_id: str) -> str | None:
    """Grava como Anexo os documentos que a fala do chat trouxe e devolve o
    aviso dos que nao entraram, ou `None`. Nunca levanta: a fala ja entrou."""
    return aviso_dos_documentos(_anexar_guardados(supabase, demanda=demanda, ids=documento_ids, quem_id=quem_id))
