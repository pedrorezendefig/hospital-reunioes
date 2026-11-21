"""O depoimento do Canal de Conduta (issue #1830; especificação, seções 7.1 e
7.2; ADR 0097, decisão 2).

Na etapa Apuração, cada pessoa ouvida ganha um cartão (nome, cargo e papel),
que recebe a transcrição, o áudio e o termo assinado, cada um pelo seu botão.
Nome e cargo entram cifrados. Os arquivos entram cifrados no bucket privado do
Canal, sem nome original e sem URL: o arquivo só sai pela rota que confere o
acesso e decifra. Uma versão nova não apaga a anterior.

"CONCLUIR DEPOIMENTO" só vale com os sete itens da lista de conferência: três
automáticos (os arquivos) e quatro declarações de quem conduziu, com quem
marcou e quando. Sem gravação, os pontos digitados fazem as vezes da
transcrição e os itens de transcrição e áudio ficam "Não se aplica", com o
motivo.

Toda ação grava a sua linha na trilha antes de mudar qualquer coisa. A trilha
não leva nome de pessoa ouvida.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from postgrest.exceptions import APIError

from app.services import storage
from app.services.conduta import cifra, trilha
from app.services.conduta.portao import CasoAberto
from app.services.conduta.ritos import agora_utc

logger = logging.getLogger(__name__)

TABELA = "conduta_depoimentos"
ARQUIVOS = "conduta_depoimento_arquivos"
# O bucket privado do Canal (migration 175), sem policy e sem URL.
BUCKET = "conduta-arquivos"

PAPEIS = {"acusado": "Acusado", "testemunha": "Testemunha", "denunciante": "Denunciante identificado"}

_TAMANHO_DO_NOME = 200
_MB = 1024 * 1024


@dataclass(frozen=True)
class TipoDeArquivo:
    rotulo: str
    content_types: dict[str, str]
    limite_bytes: int
    recusa: str
    paginas: int = 1


TIPOS = {
    "transcricao": TipoDeArquivo(
        "a transcrição do depoimento",
        {
            ".txt": "text/plain; charset=utf-8",
            ".vtt": "text/vtt; charset=utf-8",
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        },
        20 * _MB,
        "Envie a transcrição em TXT, VTT, DOCX ou PDF.",
    ),
    # Um depoimento de duas horas cabe com folga (ADR 0097, decisão 2).
    "audio": TipoDeArquivo(
        "o áudio do depoimento",
        {".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".ogg": "audio/ogg"},
        300 * _MB,
        "Envie o áudio em MP3, M4A ou OGG.",
    ),
    # Arquivo ou câmera do celular: uma foto por página.
    "termo_assinado": TipoDeArquivo(
        "o termo assinado",
        {
            ".pdf": "application/pdf",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".heic": "image/heic",
            ".heif": "image/heif",
        },
        30 * _MB,
        "Envie o termo assinado em PDF ou foto (JPG, PNG, WEBP ou HEIC).",
        paginas=5,
    ),
}
LIMITE_DO_AUDIO = TIPOS["audio"].limite_bytes


class DepoimentoRecusadoError(Exception):
    """A ação não pode acontecer agora. `status` vai para a resposta, e a
    mensagem diz o motivo numa linha."""

    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status = status
        self.mensagem = mensagem


@dataclass(frozen=True)
class ArquivoRecebido:
    nome: str
    conteudo: bytes


# ── Regras ──────────────────────────────────────────────────────────────────


def conferir_arquivo(tipo: str, nome: str, tamanho: int) -> str:
    """O content-type do arquivo aceito, pela extensão (nunca pelo que o
    navegador declarou), ou a recusa com a mensagem da tela."""
    regra = TIPOS[tipo]
    nome = (nome or "").strip()
    extensao = nome[nome.rfind(".") :].lower() if "." in nome else ""
    if extensao not in regra.content_types:
        raise DepoimentoRecusadoError(422, regra.recusa)
    if tamanho <= 0:
        raise DepoimentoRecusadoError(422, "O arquivo está vazio.")
    if tamanho > regra.limite_bytes:
        raise DepoimentoRecusadoError(413, f"O arquivo passa de {regra.limite_bytes // _MB} MB.")
    return regra.content_types[extensao]


def situacao(depoimento: dict) -> str:
    if depoimento.get("concluido_em"):
        return "Concluído"
    return "Aguardando assinatura"


# ── Leituras ────────────────────────────────────────────────────────────────


def _do_caso(supabase, caso_id: str) -> list[dict]:
    linhas = supabase.table(TABELA).select("*").eq("caso_id", caso_id).execute().data or []
    return sorted(linhas, key=lambda d: str(d.get("criado_em") or ""))


def _depoimento(supabase, caso_id: str, depoimento_id: str) -> dict:
    """O depoimento DESTE caso. Sem o casamento com o caso, o id de um
    depoimento viraria caminho lateral para outro caso."""
    linhas = (
        supabase.table(TABELA).select("*").eq("id", depoimento_id).eq("caso_id", caso_id).limit(1).execute().data
        or []
    )
    if not linhas:
        raise DepoimentoRecusadoError(404, "Depoimento não encontrado neste caso.")
    return linhas[0]


def _arquivos(supabase, depoimento_ids: list[str]) -> list[dict]:
    if not depoimento_ids:
        return []
    return supabase.table(ARQUIVOS).select("*").in_("depoimento_id", depoimento_ids).execute().data or []


def _nomes(supabase, ids: set[str]) -> dict[str, str]:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    linhas = supabase.table("participantes").select("id, nome_completo").in_("id", sorted(ids)).execute().data or []
    return {linha["id"]: linha.get("nome_completo") or "" for linha in linhas}


def _versoes(arquivos: list[dict], nomes: dict[str, str]) -> dict[str, list[dict]]:
    """Por botão, as versões da mais nova para a mais antiga, cada uma com as
    suas páginas. Sem caminho no bucket: o arquivo só sai pela rota."""
    saida: dict[str, list[dict]] = {tipo: [] for tipo in TIPOS}
    por_versao: dict[tuple[str, int], list[dict]] = {}
    for arquivo in arquivos:
        por_versao.setdefault((arquivo["tipo"], arquivo["versao"]), []).append(arquivo)
    for (tipo, versao), paginas in sorted(por_versao.items(), key=lambda x: -x[0][1]):
        paginas.sort(key=lambda a: a.get("pagina") or 1)
        saida[tipo].append(
            {
                "versao": versao,
                "enviado_em": paginas[0]["enviado_em"],
                "enviado_por": nomes.get(paginas[0]["enviado_por"], ""),
                "paginas": [
                    {"id": a["id"], "content_type": a["content_type"], "tamanho_bytes": a["tamanho_bytes"]}
                    for a in paginas
                ],
            }
        )
    return saida


def para_a_tela(supabase, caso: dict) -> dict[str, Any]:
    """Os cartões do caso, decifrados. Levanta `CifraIndisponivelError` se a
    chave não abre."""
    lista = _do_caso(supabase, caso["id"])
    arquivos = _arquivos(supabase, [d["id"] for d in lista])
    nomes = _nomes(supabase, {a["enviado_por"] for a in arquivos})
    cartoes = [
        {
            "id": d["id"],
            "nome": cifra.decifrar_texto(d["nome_cifrado"]),
            "cargo": cifra.decifrar_texto(d["cargo_cifrado"]),
            "papel": d["papel"],
            "situacao": situacao(d),
            "arquivos": _versoes([a for a in arquivos if a["depoimento_id"] == d["id"]], nomes),
        }
        for d in lista
    ]
    return {"depoimentos": cartoes}


# ── Ações ───────────────────────────────────────────────────────────────────


def _exigir_apuracao(caso: dict) -> None:
    if caso.get("etapa") != "apuracao" or caso.get("encerrado_em"):
        raise DepoimentoRecusadoError(409, "Os depoimentos são da etapa Apuração.")


def _exigir_aberto(caso: dict, depoimento: dict) -> None:
    _exigir_apuracao(caso)
    if depoimento.get("concluido_em"):
        raise DepoimentoRecusadoError(409, "Este depoimento já foi concluído.")


def adicionar_pessoa(supabase, aberto: CasoAberto, *, nome: str, cargo: str, papel: str) -> dict:
    _exigir_apuracao(aberto.caso)
    nome, cargo = (nome or "").strip(), (cargo or "").strip()
    if not nome or not cargo:
        raise DepoimentoRecusadoError(422, "Diga o nome e o cargo da pessoa a ouvir.")
    if len(nome) > _TAMANHO_DO_NOME or len(cargo) > _TAMANHO_DO_NOME:
        raise DepoimentoRecusadoError(422, "O nome e o cargo cabem em uma linha.")
    if papel not in PAPEIS:
        raise DepoimentoRecusadoError(422, "Escolha o papel: acusado, testemunha ou denunciante identificado.")
    nome_cifrado, cargo_cifrado = cifra.cifrar_texto(nome), cifra.cifrar_texto(cargo)
    trilha.registrar(
        supabase, aberto.caso["id"], aberto.autor_id, "adicionou_pessoa_a_ouvir", f"pessoa a ouvir: {PAPEIS[papel]}"
    )
    return (
        supabase.table(TABELA)
        .insert(
            {
                "caso_id": aberto.caso["id"],
                "nome_cifrado": nome_cifrado,
                "cargo_cifrado": cargo_cifrado,
                "papel": papel,
                "criado_por": aberto.autor_id,
                "criado_em": agora_utc().isoformat(),
            }
        )
        .execute()
        .data[0]
    )


def _tirar_do_bucket(supabase, caminhos: list[str]) -> None:
    for caminho in caminhos:
        if not storage.delete_file(supabase, BUCKET, caminho):
            logger.error("Arquivo de depoimento órfão no bucket do Canal: %s", caminho)


def anexar(supabase, aberto: CasoAberto, depoimento_id: str, tipo: str, recebidos: list[ArquivoRecebido]) -> dict:
    """Uma versão nova do arquivo do botão `tipo`. A anterior fica."""
    caso = aberto.caso
    depoimento = _depoimento(supabase, caso["id"], depoimento_id)
    _exigir_aberto(caso, depoimento)
    regra = TIPOS[tipo]
    if tipo != "termo_assinado" and depoimento.get("sem_gravacao_em"):
        raise DepoimentoRecusadoError(409, "Este depoimento foi registrado sem gravação.")
    if not recebidos or len(recebidos) > regra.paginas:
        raise DepoimentoRecusadoError(
            422, "Envie um arquivo." if regra.paginas == 1 else f"Envie de 1 a {regra.paginas} páginas."
        )
    content_types = [conferir_arquivo(tipo, r.nome, len(r.conteudo)) for r in recebidos]
    cifrados = [cifra.cifrar_arquivo(r.conteudo) for r in recebidos]
    anteriores = [a for a in _arquivos(supabase, [depoimento["id"]]) if a["tipo"] == tipo]
    versao = max((a["versao"] for a in anteriores), default=0) + 1
    trilha.registrar(supabase, caso["id"], aberto.autor_id, "anexou_arquivo", f"anexou {regra.rotulo}, versão {versao}")
    caminhos: list[str] = []
    for conteudo in cifrados:
        caminho = f"depoimentos/{uuid.uuid4().hex}"
        if not storage.upload_private(supabase, BUCKET, caminho, conteudo):
            _tirar_do_bucket(supabase, caminhos)
            raise DepoimentoRecusadoError(503, "O arquivo não foi guardado. Tente de novo.")
        caminhos.append(caminho)
    agora = agora_utc().isoformat()
    linhas = [
        {
            "depoimento_id": depoimento["id"],
            "tipo": tipo,
            "versao": versao,
            "pagina": pagina,
            "storage_path": caminho,
            "content_type": content_type,
            "tamanho_bytes": len(recebido.conteudo),
            "enviado_por": aberto.autor_id,
            "enviado_em": agora,
        }
        for pagina, (caminho, content_type, recebido) in enumerate(
            zip(caminhos, content_types, recebidos, strict=True), 1
        )
    ]
    try:
        supabase.table(ARQUIVOS).insert(linhas).execute()
    except APIError:
        _tirar_do_bucket(supabase, caminhos)
        raise
    return {"tipo": tipo, "versao": versao}


def abrir_arquivo(supabase, aberto: CasoAberto, depoimento_id: str, arquivo_id: str) -> tuple[bytes, str]:
    """O arquivo decifrado e o content-type, depois de gravada a abertura na
    trilha. Só o arquivo DESTE depoimento, deste caso; nunca uma URL."""
    caso = aberto.caso
    depoimento = _depoimento(supabase, caso["id"], depoimento_id)
    linhas = (
        supabase.table(ARQUIVOS)
        .select("*")
        .eq("id", arquivo_id)
        .eq("depoimento_id", depoimento["id"])
        .limit(1)
        .execute()
        .data
        or []
    )
    if not linhas:
        raise DepoimentoRecusadoError(404, "Arquivo não encontrado neste depoimento.")
    arquivo = linhas[0]
    trilha.registrar(
        supabase,
        caso["id"],
        aberto.autor_id,
        "abriu_arquivo",
        f"abriu {TIPOS[arquivo['tipo']].rotulo}, versão {arquivo['versao']}",
    )
    cifrado = storage.download_file(supabase, BUCKET, arquivo["storage_path"])
    if cifrado is None:
        raise DepoimentoRecusadoError(503, "O arquivo não pôde ser aberto agora. Tente de novo.")
    return cifra.decifrar_arquivo(cifrado), arquivo["content_type"]
