import logging

logger = logging.getLogger(__name__)


def upload_file(
    supabase,
    bucket: str,
    path: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> str | None:
    """Faz upload de um arquivo para o Supabase Storage e retorna a URL pública."""
    try:
        supabase.storage.from_(bucket).upload(
            path,
            content,
            {"content-type": content_type, "upsert": "true"},
        )
        url = supabase.storage.from_(bucket).get_public_url(path)
        if "host.docker.internal" in url:
            url = url.replace("host.docker.internal", "localhost")
        return url
    except Exception as e:
        logger.error(f"Erro ao fazer upload para {bucket}/{path}: {e}")
        return None


def delete_file(supabase, bucket: str, path: str) -> bool:
    """Remove um arquivo do Supabase Storage (best-effort)."""
    try:
        supabase.storage.from_(bucket).remove([path])
        return True
    except Exception as e:
        logger.error(f"Erro ao remover {bucket}/{path}: {e}")
        return False


def download_file(supabase, bucket: str, path: str) -> bytes | None:
    """Faz download de um arquivo do Supabase Storage."""
    try:
        response = supabase.storage.from_(bucket).download(path)
        return response
    except Exception as e:
        logger.error(f"Erro ao baixar {bucket}/{path}: {e}")
        return None
