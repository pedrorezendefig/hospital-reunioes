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

logger = logging.getLogger(__name__)

TABELA_ANEXOS = "tecnologia_anexos"


class AnexoRecusadoError(Exception):
    """A recusa, com a frase que a pessoa le e o status HTTP que a rota devolve."""

    def __init__(self, motivo: str, status_code: int = 422):
        super().__init__(motivo)
        self.status_code = status_code


def _bucket() -> str:
    return settings.supabase_storage_bucket_anexos_tecnologia


def anexar(supabase, *, demanda_id: str, nome: str, conteudo: bytes, quem_id: str) -> dict:
    """Guarda a imagem junto da Demanda e devolve a linha gravada.

    O binario sobe ANTES da linha: sem binario nao existe anexo, e uma linha que
    aponta para o vazio quebraria o card. Se a linha nao entrar, o binario sai
    na hora, porque nada mais o alcancaria depois.
    """
    extensao = os.path.splitext(nome or "")[1].lower()
    if extensao not in TIPOS_DE_IMAGEM:
        raise AnexoRecusadoError(MOTIVO_IMAGEM_FORA_DA_LISTA)
    if len(conteudo) > LIMITE_DA_IMAGEM:
        raise AnexoRecusadoError(MOTIVO_IMAGEM_GRANDE, status_code=413)

    existentes = supabase.table(TABELA_ANEXOS).select("ordem").eq("demanda_id", demanda_id).execute().data or []
    ordem = max((int(linha.get("ordem") or 0) for linha in existentes), default=0) + 1

    # Caminho sorteado, como na Ouvidoria: o nome original pode carregar dado
    # pessoal ("prontuario do Joao.png") e nao vira parte de caminho.
    path = f"demanda-{demanda_id}/{uuid.uuid4().hex}{extensao}"
    if not storage.upload_private(
        supabase, bucket=_bucket(), path=path, content=conteudo, content_type=TIPOS_DE_IMAGEM[extensao]
    ):
        raise AnexoRecusadoError("Não foi possível guardar a imagem agora. Tente de novo em instantes.", 503)

    linha = {
        "demanda_id": demanda_id,
        "ordem": ordem,
        "storage_path": path,
        "nome_original": nome,
        "content_type": TIPOS_DE_IMAGEM[extensao],
        "tamanho_bytes": len(conteudo),
        "anexado_por": quem_id,
        "apagado_em": None,
    }
    inserido = supabase.table(TABELA_ANEXOS).insert(linha).execute()
    return inserido.data[0]
