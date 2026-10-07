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
