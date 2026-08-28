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


def upload_private(
    supabase,
    bucket: str,
    path: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> bool:
    """Sobe um arquivo para bucket privado e diz apenas se deu certo.

    Diferente de `upload_file`, não devolve URL: em bucket privado a URL
    pública não abre nada, e prometer uma seria enganar quem chama. A leitura
    depois é por `signed_url`."""
    try:
        supabase.storage.from_(bucket).upload(
            path,
            content,
            {"content-type": content_type, "upsert": "true"},
        )
        return True
    except Exception as e:
        logger.error(f"Erro ao fazer upload privado para {bucket}/{path}: {e}")
        return False


def signed_url(supabase, bucket: str, path: str, expires_in: int) -> str | None:
    """URL temporária para um arquivo de bucket privado.

    Usada onde o arquivo não pode ficar em bucket público (anexo de ouvidoria,
    por exemplo): o link vale por `expires_in` segundos e depois morre."""
    try:
        resposta = supabase.storage.from_(bucket).create_signed_url(path, expires_in)
    except Exception as e:
        logger.error(f"Erro ao assinar URL de {bucket}/{path}: {e}")
        return None
    # A biblioteca já mudou a caixa da chave entre versões; aceitar as duas
    # evita quebra silenciosa (URL None) num upgrade de dependência.
    url = resposta.get("signedURL") or resposta.get("signedUrl") if isinstance(resposta, dict) else None
    if not url:
        logger.error(f"Storage não devolveu URL assinada para {bucket}/{path}")
        return None
    if "host.docker.internal" in url:
        url = url.replace("host.docker.internal", "localhost")
    return url


def delete_file(supabase, bucket: str, path: str) -> bool:
    """Remove um arquivo do Supabase Storage e diz se ele realmente saiu.

    O Storage relata o resultado arquivo a arquivo no corpo da resposta, e uma
    remoção pode falhar sem levantar exceção nenhuma. Quem chama apaga em
    seguida o ponteiro para o binário (a linha do anexo, do material do POP):
    um `True` de mentira aqui vira arquivo órfão no bucket, sem ponteiro para
    ninguém achar depois. Por isso só conta como sucesso a resposta que traz o
    arquivo e não traz erro; qualquer outra coisa é falha, inclusive o corpo
    vazio (o Storage não confirmou remoção nenhuma) e a forma que não dá para
    ler, item a item.

    Atenção de quem chama: o Storage responde 200 com lista vazia quando nada
    casou, então arquivo que JÁ SAIU do bucket é indistinguível de recusa, e os
    dois vêm como False. Quem apaga vários ponteiros de uma vez tem que apagar
    o de cada arquivo logo após a confirmação dele, e não todos no fim: senão
    uma falha no meio deixa ponteiro apontando para binário que já saiu, e a
    tentativa seguinte trava nesse arquivo para sempre."""
    try:
        resposta = supabase.storage.from_(bucket).remove([path])
    except Exception as e:
        logger.error(f"Erro ao remover {bucket}/{path}: {e}")
        return False

    if not isinstance(resposta, list):
        logger.error(f"Storage devolveu resposta em formato inesperado ao remover {bucket}/{path}: {resposta!r}")
        return False
    if not resposta:
        logger.error(f"Storage não confirmou a remoção de {bucket}/{path}; o arquivo pode continuar no bucket")
        return False
    for item in resposta:
        if not isinstance(item, dict):
            logger.error(f"Storage devolveu item ilegível ao remover {bucket}/{path}: {item!r}")
            return False
        erro = item.get("error")
        if erro:
            logger.error(f"Storage recusou remover {bucket}/{path}: {erro}")
            return False
    return True


def download_file(supabase, bucket: str, path: str) -> bytes | None:
    """Faz download de um arquivo do Supabase Storage."""
    try:
        response = supabase.storage.from_(bucket).download(path)
        return response
    except Exception as e:
        logger.error(f"Erro ao baixar {bucket}/{path}: {e}")
        return None
