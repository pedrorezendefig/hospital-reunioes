"""O Anexo da Demanda (issue #1061, PRD #1056, ADR 0069).

O print de tela que vem junto da Demanda. Vive SO no app e nunca vai para o
GitHub: o repositorio e publico, e print do hospital carrega nome de paciente,
de colaborador, protocolo da Ouvidoria.

Um lugar so decide as tres coisas que as portas fazem com ele (o formulario
nesta fatia; o Assistente e a resposta da Conversa nas seguintes):

- **anexar**: a imagem passa pela regra do Assistente (formatos e teto, com as
  mesmas frases de recusa), sobe ao bucket privado com caminho sorteado e so
  depois ganha a linha no banco;
- **listar**: o que o card mostra, com URL assinada de vida curta para o que
  ainda esta guardado;
- **apagar todos**: Concluir e Cancelar tiram os binarios do bucket e deixam o
  registro (nome, quem, quando) marcado apagado. Mudanca de Etapa nunca chega
  aqui (ADR 0069, decisao 3).
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from app.config import settings
from app.services import storage
from app.services.assistente_tecnologia import (
    LIMITE_DA_IMAGEM,
    MOTIVO_IMAGEM_FORA_DA_LISTA,
    MOTIVO_IMAGEM_GRANDE,
    TIPOS_DE_IMAGEM,
)
from app.services.tecnologia import ESTADOS_FECHADOS

logger = logging.getLogger(__name__)

TABELA_ANEXOS = "tecnologia_anexos"

# Ate dez por Demanda (ADR 0069, decisao 1). O mesmo teto vive no CHECK da
# coluna `ordem` (migration 115): contornar a API nao contorna o teto.
LIMITE_DE_ANEXOS = 10
MOTIVO_ANEXOS_DEMAIS = (
    f"Esta Demanda já tem {LIMITE_DE_ANEXOS} imagens, o máximo por Demanda. "
    "Escolha as que mais ajudam, ou descreva o resto no texto."
)
MOTIVO_ARQUIVO_VAZIO = "A imagem chegou vazia: não há o que anexar. Escolha o arquivo de novo."
MOTIVO_DEMANDA_ENCERRADA = "Esta Demanda está encerrada: imagem só entra em Demanda aberta. Reabra antes de anexar."
MOTIVO_NAO_GUARDOU = "Não foi possível guardar a imagem agora. Tente de novo em instantes."
MOTIVO_IMAGEM_DA_RESPOSTA = (
    "A imagem desta resposta não foi encontrada nesta Demanda. Escolha a imagem de novo e responda outra vez."
)

# Dez minutos: o card abre, a miniatura carrega, quem quer ver em tamanho real
# clica. Link colado fora do app morre antes de virar acesso permanente ao
# print. A tela pede a lista de novo a cada vez que o card abre.
EXPIRACAO_DA_URL_SEGUNDOS = 600


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
    if extensao not in TIPOS_DE_IMAGEM:
        raise AnexoRecusadoError(MOTIVO_IMAGEM_FORA_DA_LISTA)
    if not conteudo:
        raise AnexoRecusadoError(MOTIVO_ARQUIVO_VAZIO)
    if len(conteudo) > LIMITE_DA_IMAGEM:
        raise AnexoRecusadoError(MOTIVO_IMAGEM_GRANDE, status_code=413)

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
    content_type = TIPOS_DE_IMAGEM[extensao]
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

    Chamado SO por Concluir e Cancelar, o ato humano que encerra (ADR 0069,
    decisao 3). Mudanca de Etapa nunca chega aqui: em Entregue o diretor ainda
    confere com o print na mao.

    A marca de cada anexo entra logo depois da confirmacao DELE, e nao todas no
    fim (a regra do `storage.delete_file`): uma falha no meio deixa marcados so
    os que sairam de verdade. O que o Storage nao confirmou fica sem a marca,
    com o caminho no log, e o card continua honesto sobre ele.

    Nunca levanta: quem chama ja encerrou a Demanda, e o encerramento vale com
    ou sem o bucket respondendo. Falha aqui vira log com o caminho do arquivo.

    Devolve quantos binarios sairam: com zero, a contagem da issue vinculada
    (issue #1062) nao mudou e nao ha o que reescrever la.
    """
    try:
        guardados = [linha for linha in ler(supabase, demanda_id) if not linha.get("apagado_em")]
    except Exception:
        logger.exception("Falha ao ler os anexos da Demanda %s para apagar ao encerrar", demanda_id)
        return 0
    sairam = 0
    for linha in guardados:
        path = linha["storage_path"]
        if not storage.delete_file(supabase, _bucket(), path):
            logger.error("Anexo da Demanda %s não saiu do bucket ao encerrar: %s", demanda_id, path)
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


def quantos_guardados(supabase, demanda_id: str) -> int:
    """Quantas imagens a Demanda ainda guarda: o N da frase "Anexos: N imagens
    na Demanda" da issue (issue #1062). O apagado nao conta: o binario saiu, e
    quem desenvolve nao teria o que buscar."""
    return sum(1 for linha in ler(supabase, demanda_id) if not linha.get("apagado_em"))


def ler(supabase, demanda_id: str) -> list[dict]:
    """As linhas dos anexos da Demanda, na ordem em que entraram."""
    result = supabase.table(TABELA_ANEXOS).select("*").eq("demanda_id", demanda_id).order("ordem").execute()
    return list(result.data or [])


def listar(supabase, demanda_id: str) -> list[dict]:
    """Os anexos como o card os mostra: nome, quem, quando, e a URL assinada.

    O anexo apagado vem sem URL e com `apagado_em`: o binario ja saiu do bucket,
    e o card mostra que ele existiu. O caminho no storage nunca sai daqui.
    """
    return _para_o_card(supabase, ler(supabase, demanda_id))


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


# ─── A imagem da resposta da Conversa (issue #1062) ─────────────────────────
#
# A imagem sobe ANTES, pela mesma porta do formulario (`anexar`): formatos,
# teto e o maximo de dez valem igual, com as mesmas frases, e a recusa chega a
# quem responde antes de o texto entrar no fio. A resposta leva o id do anexo,
# e so entao ele ganha a `conversa_id`.


def imagem_para_a_resposta(supabase, *, demanda_id: str, anexo_id: str, quem_id: str) -> dict:
    """O anexo que a resposta quer levar, se ele pode ir com ela.

    Pode quando e DESTA Demanda, ainda nao esta ligado a outra resposta, nao
    foi apagado e foi anexado por quem responde. Qualquer outro caso e a mesma
    recusa: quem esta respondendo so precisa saber que precisa escolher de novo.
    """
    achados = supabase.table(TABELA_ANEXOS).select("*").eq("id", anexo_id).eq("demanda_id", demanda_id).execute()
    linha = (achados.data or [None])[0]
    if (
        not linha
        or linha.get("conversa_id")
        or linha.get("apagado_em")
        or str(linha.get("anexado_por") or "") != str(quem_id)
    ):
        raise AnexoRecusadoError(MOTIVO_IMAGEM_DA_RESPOSTA)
    return linha


def ligar_a_resposta(supabase, *, anexo_id: str, conversa_id: str) -> None:
    """Liga a imagem a resposta que acabou de entrar no fio.

    Nunca levanta: a resposta ja entrou. Sem a ligacao, a imagem continua na
    Demanda (na lista do card), so nao aparece junto da resposta; o log diz qual.
    """
    try:
        supabase.table(TABELA_ANEXOS).update({"conversa_id": conversa_id}).eq("id", anexo_id).is_(
            "conversa_id", "null"
        ).execute()
    except Exception:
        logger.exception("A imagem %s nao foi ligada a resposta %s", anexo_id, conversa_id)


def imagens_das_respostas(supabase, demanda_id: str) -> dict[str, dict]:
    """A imagem de cada resposta da Demanda, como o card a mostra, por id da linha
    do fio. So as ligadas a uma resposta sao assinadas."""
    linhas = [linha for linha in ler(supabase, demanda_id) if linha.get("conversa_id")]
    return {str(anexo["conversa_id"]): anexo for anexo in _para_o_card(supabase, linhas)}


def quantas_da_resposta(supabase, conversa_id: str) -> int:
    """Quantas imagens a resposta levou: o "(1 imagem na Demanda)" do comentario
    espelhado (issue #1062), inclusive na correcao, que remonta o corpo."""
    result = supabase.table(TABELA_ANEXOS).select("id").eq("conversa_id", conversa_id).execute()
    return len(result.data or [])


def _para_o_card(supabase, linhas: list[dict]) -> list[dict]:
    quem = {linha["anexado_por"] for linha in linhas if linha.get("anexado_por")}
    nomes: dict[str, str] = {}
    if quem:
        result = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(quem)).execute()
        nomes = {p["id"]: p.get("nome_completo") for p in (result.data or [])}
    return [
        {
            "id": linha["id"],
            "nome": linha.get("nome_original") or "",
            "anexado_por_nome": nomes.get(linha.get("anexado_por")),
            "criado_em": linha.get("criado_em"),
            "apagado_em": linha.get("apagado_em"),
            "conversa_id": linha.get("conversa_id"),
            "url": None
            if linha.get("apagado_em")
            else storage.signed_url(supabase, _bucket(), linha["storage_path"], EXPIRACAO_DA_URL_SEGUNDOS),
        }
        for linha in linhas
    ]


# ─── O print do Assistente (issue #1062) ─────────────────────────────────────
#
# O Assistente le o print e devolve a descricao; a imagem nao vira Anexo ali,
# porque a Demanda ainda nao existe e pode nunca existir. Ela fica guardada SO
# na memoria do processo, com um identificador efemero que a tela leva junto da
# conversa, e vira Anexo no clique de "Criar Demanda", na mesma chamada que cria.
# Sem o clique, nada persiste: nem linha, nem binario no bucket. O que sobra na
# memoria sai pelo prazo ou pelo teto, e um reinicio do backend tambem limpa.
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
    """Guarda na memoria o print que o Assistente acabou de descrever e devolve
    o identificador efemero que a tela leva ate "Criar Demanda"."""
    print_id = uuid.uuid4().hex
    agora = time.monotonic()
    with _trava_dos_prints:
        _prints[print_id] = {
            "quem_id": str(quem_id),
            "nome": nome,
            "conteudo": conteudo,
            "vence_em": agora + PRAZO_DO_PRINT_SEGUNDOS,
        }
        _jogar_fora_vencidos(agora)
    return print_id


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
    """A frase da Demanda que nasceu sem algum dos prints do Assistente."""
    if quantos <= 0:
        return None
    sujeito = "um print da conversa não entrou" if quantos == 1 else f"{quantos} prints da conversa não entraram"
    return f"A Demanda foi aberta, mas {sujeito} como imagem. Abra a Demanda e anexe de novo."


def anexar_prints(supabase, *, demanda: dict, print_ids: list[str], quem_id: str) -> str | None:
    """Grava como Anexo os prints que "Criar Demanda" trouxe e devolve o aviso
    dos que nao entraram, ou `None`. Nunca levanta: a Demanda ja nasceu."""
    faltaram = 0
    for print_id in dict.fromkeys(print_ids):
        guardado = tirar_print(quem_id=quem_id, print_id=print_id)
        if guardado is None:
            faltaram += 1
            continue
        try:
            anexar(supabase, demanda=demanda, nome=guardado["nome"], conteudo=guardado["conteudo"], quem_id=quem_id)
        except AnexoRecusadoError:
            logger.warning("Print do Assistente recusado ao criar a Demanda %s", demanda.get("id"))
            faltaram += 1
        except Exception:
            # Largo de proposito, como o resto do modulo: o `APIError` e o
            # `httpx.HTTPError` cru do PostgREST virariam 500 com a Demanda ja
            # gravada, e a tela convidaria a cria-la de novo.
            logger.exception("Falha ao gravar o print do Assistente na Demanda %s", demanda.get("id"))
            faltaram += 1
    return aviso_dos_prints(faltaram)
