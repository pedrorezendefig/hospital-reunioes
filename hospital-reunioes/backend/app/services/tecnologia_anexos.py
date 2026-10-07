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
import uuid
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
    linhas = ler(supabase, demanda_id)
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
            "url": None
            if linha.get("apagado_em")
            else storage.signed_url(supabase, _bucket(), linha["storage_path"], EXPIRACAO_DA_URL_SEGUNDOS),
        }
        for linha in linhas
    ]
