"""O Código de Conduta, publicado pela coordenação do Comitê, com versões
(issue #1841, PRD #1786, decisão 37 do diretor).

Cada publicação é um PDF e vira a versão seguinte, com data de vigência e
autor. Nenhuma versão sai: o banco (migration 194) recusa UPDATE, DELETE e
TRUNCATE. A que valia numa data é a de maior vigência até aquele dia; na mesma
vigência, a publicada depois. O caso usa isso para citar o item do Código que
valia na data do fato.

A vigência nunca fica no passado nem antes da última versão: retroativa, ela
trocaria a versão que valia numa data já julgada.

O PDF vai para o bucket privado `conduta-codigo` e sai só pelo backend: na
rota pública (a vigente) ou na da coordenação (qualquer versão).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from app.services import storage

TABELA = "conduta_codigo_versoes"
BUCKET = "conduta-codigo"
LIMITE_BYTES = 20 * 1024 * 1024

MOTIVO_NAO_E_PDF = "O Código de Conduta precisa ser um arquivo PDF."
MOTIVO_GRANDE = "O PDF passa de 20 MB. Mande um arquivo mais leve."
MOTIVO_VAZIO = "O arquivo chegou vazio. Escolha o arquivo de novo."
MOTIVO_PASSADO = "A vigência não pode ser antes de hoje."
MOTIVO_ANTES_DA_ULTIMA = "A vigência não pode ser antes da vigência da última versão publicada."
MOTIVO_NAO_GUARDOU = "Não foi possível guardar o PDF agora. Tente de novo em instantes."


class RecusaDoCodigo(Exception):  # noqa: N818, o nome do domínio
    """A recusa, com a frase que a pessoa lê e o status HTTP da rota."""

    def __init__(self, motivo: str, status_code: int = 422):
        super().__init__(motivo)
        self.motivo = motivo
        self.status_code = status_code


def _linhas(supabase) -> list[dict]:
    """Todas as versões, da mais nova para a mais antiga."""
    linhas = supabase.table(TABELA).select("*").execute().data or []
    return sorted(linhas, key=lambda linha: linha["versao"], reverse=True)


def _nomes(supabase, ids: set[str]) -> dict[str, str]:
    if not ids:
        return {}
    linhas = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute().data
    return {linha["id"]: linha.get("nome_completo") or "" for linha in linhas or []}


def _versao(linha: dict, nomes: dict[str, str]) -> dict[str, Any]:
    return {
        "id": linha["id"],
        "versao": linha["versao"],
        "vigente_desde": linha["vigente_desde"],
        "nome_arquivo": linha["nome_arquivo"],
        "tamanho_bytes": linha["tamanho_bytes"],
        "autor": nomes.get(linha["autor_id"], ""),
        "criado_em": linha["criado_em"],
    }


def versoes(supabase) -> list[dict[str, Any]]:
    """Todas as versões publicadas, a mais nova primeiro."""
    linhas = _linhas(supabase)
    nomes = _nomes(supabase, {linha["autor_id"] for linha in linhas})
    return [_versao(linha, nomes) for linha in linhas]


def _linha_em(linhas: list[dict], data: date) -> dict | None:
    valendo = [linha for linha in linhas if str(linha["vigente_desde"]) <= data.isoformat()]
    if not valendo:
        return None
    return max(valendo, key=lambda linha: (str(linha["vigente_desde"]), linha["versao"]))


def vigente_em(supabase, data: date) -> dict[str, Any] | None:
    """A versão que valia na data, ou None se nenhuma valia ainda."""
    linha = _linha_em(_linhas(supabase), data)
    if linha is None:
        return None
    return _versao(linha, _nomes(supabase, {linha["autor_id"]}))


def pdf_da_versao(supabase, numero: int) -> tuple[dict, bytes] | None:
    """A versão de número dado e o PDF dela, ou None se não existe."""
    linha = next((linha for linha in _linhas(supabase) if linha["versao"] == numero), None)
    return _com_o_pdf(supabase, linha)


def pdf_vigente_em(supabase, data: date) -> tuple[dict, bytes] | None:
    """A versão que valia na data e o PDF dela, ou None."""
    return _com_o_pdf(supabase, _linha_em(_linhas(supabase), data))


def _com_o_pdf(supabase, linha: dict | None) -> tuple[dict, bytes] | None:
    if linha is None:
        return None
    conteudo = storage.download_file(supabase, BUCKET, linha["storage_path"])
    if conteudo is None:
        raise RecusaDoCodigo("Não foi possível abrir o PDF agora. Tente de novo em instantes.", 503)
    return linha, conteudo


def _conferir(conteudo: bytes) -> None:
    if not conteudo:
        raise RecusaDoCodigo(MOTIVO_VAZIO)
    if len(conteudo) > LIMITE_BYTES:
        raise RecusaDoCodigo(MOTIVO_GRANDE, status_code=413)
    if not conteudo.startswith(b"%PDF-"):
        raise RecusaDoCodigo(MOTIVO_NAO_E_PDF)


def publicar(
    supabase,
    *,
    nome_arquivo: str,
    conteudo: bytes,
    vigente_desde: date,
    autor_id: str,
    hoje: date,
) -> dict[str, Any]:
    """Grava a versão seguinte. As anteriores não são tocadas. Toda recusa vem
    antes do bucket: PDF recusado não deixa rastro."""
    _conferir(conteudo)
    if vigente_desde < hoje:
        raise RecusaDoCodigo(MOTIVO_PASSADO)
    atuais = _linhas(supabase)
    if atuais and vigente_desde.isoformat() < str(atuais[0]["vigente_desde"]):
        raise RecusaDoCodigo(MOTIVO_ANTES_DA_ULTIMA)
    proxima = (atuais[0]["versao"] if atuais else 0) + 1

    # O nome original não vira caminho: pode carregar dado pessoal.
    caminho = f"v{proxima}-{uuid.uuid4().hex}.pdf"
    if not storage.upload_private(
        supabase, bucket=BUCKET, path=caminho, content=conteudo, content_type="application/pdf"
    ):
        raise RecusaDoCodigo(MOTIVO_NAO_GUARDOU, status_code=503)
    try:
        (linha,) = (
            supabase.table(TABELA)
            .insert(
                {
                    "versao": proxima,
                    "vigente_desde": vigente_desde.isoformat(),
                    "storage_path": caminho,
                    "nome_arquivo": (nome_arquivo or "codigo-de-conduta.pdf")[:255],
                    "tamanho_bytes": len(conteudo),
                    "autor_id": autor_id,
                    "criado_em": datetime.now(UTC).isoformat(),
                }
            )
            .execute()
            .data
        )
    except BaseException:
        # Sem a linha, o PDF é órfão que ninguém alcança: sai agora.
        storage.delete_file(supabase, BUCKET, caminho)
        raise
    return _versao(linha, _nomes(supabase, {autor_id}))
