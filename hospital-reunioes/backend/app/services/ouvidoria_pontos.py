"""Ponto de escuta: o cartaz de QR da Ouvidoria (issue #378, ADR 0036).

Cada Ponto de escuta é um cartaz impresso. O que vai no papel é o `codigo`, e
não o nome do setor por extenso: QR com menos dados tem módulos maiores e a
câmera lê melhor de longe, renomear o ponto não obriga a reimprimir, e a origem
deixa de ser texto que qualquer pessoa monta na query string (ADR 0036,
decisão 2).
"""

from __future__ import annotations

import logging
import secrets

logger = logging.getLogger(__name__)

# Sem os pares que a leitura confunde: `0`/`O` e `1`/`I`. O código é lido em voz
# alta ao telefone e digitado à mão quando a câmera não coopera, então o
# alfabeto é escolhido para o olho humano, não para a entropia (decisão 3).
ALFABETO_DO_CODIGO = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# Seis caracteres deste alfabeto dão ~10^9 combinações. O cadastro de um
# hospital cabe em centenas de cartazes, então a colisão é rara; quando
# acontece, quem decide é o índice único do banco, e o cadastro sorteia de novo.
TAMANHO_DO_CODIGO = 6

# Quantas vezes o cadastro sorteia antes de desistir. Não é o número que evita
# colisão (o índice único é quem evita): é o teto que impede o insert de virar
# laço infinito se o banco recusar por outro motivo.
TENTATIVAS_DE_CODIGO = 5


def gerar_codigo() -> str:
    """Um código novo, sorteado. `secrets` e não `random`: o código é o que
    autoriza a origem de uma manifestação a dizer de onde veio, e um gerador
    previsível deixaria qualquer pessoa adivinhar cartazes que ainda nem foram
    impressos."""
    return "".join(secrets.choice(ALFABETO_DO_CODIGO) for _ in range(TAMANHO_DO_CODIGO))


# As colunas que a tela lê. `criado_por` fica de fora: quem cadastrou o cartaz
# não é informação da tela de cartazes, e a trilha de quem fez vive no banco.
CAMPOS_PONTO_TUPLA = ("id", "codigo", "setor", "ponto", "ativo", "criado_em")
CAMPOS_PONTO = ", ".join(CAMPOS_PONTO_TUPLA)

TABELA = "ouvidoria_pontos"

# Colisão do índice único do `codigo` (migration 085).
_CODIGO_DUPLICADO = "23505"


# O caminho que o cartaz carrega. Sem o prefixo `/api` de propósito: o
# `next.config.ts` tem um rewrite dedicado a ele, e o comentário de lá explica
# por quê ("é a única coisa impressa e colada na parede, então ela mora no
# domínio do app"). Passar pelo proxy genérico da API funcionaria hoje e
# amarraria todo cartaz impresso à forma daquele proxy.
CAMINHO_DO_QR = "/ouvidoria/qr"


def url_do_cartaz(codigo: str) -> str:
    """O que o QR carrega. Curta de propósito: QR com menos dados tem módulos
    maiores e a câmera lê melhor de longe (ADR 0036, decisão 2).

    O caminho é o que RESOLVE o código, e não o do formulário: é o servidor que
    decide para onde mandar. É isso que deixa o destino mudar (a Ana no
    WhatsApp oficial) sem reimprimir nenhum cartaz."""
    from app.config import settings

    return f"{settings.frontend_url.rstrip('/')}{CAMINHO_DO_QR}?p={codigo}"


def endereco_impresso(codigo: str) -> str:
    """O endereço em letra, para quem não conseguiu ler o QR.

    É a MESMA URL do QR, e não o caminho do formulário: `/manifestacao` não tem
    campo de código, então mandar a pessoa "informar o código" lá a deixaria
    numa tela sem onde digitar, e o caso entraria como se tivesse vindo do site.
    Aqui o endereço se resolve sozinho.

    Sem o esquema porque ninguém digita "https://" de um cartaz."""
    from app.config import settings

    host = settings.frontend_url.replace("https://", "").replace("http://", "").rstrip("/")
    return f"{host}{CAMINHO_DO_QR}?p={codigo}"


def png_do_qr(codigo: str, escala: int = 8) -> bytes:
    """O QR como PNG.

    `segno` é Python puro: não entra Pillow nem biblioteca de imagem nativa na
    imagem do backend (ADR 0036, decisão 9). A correção de erro fica no nível
    alto porque o cartaz vive numa parede de hospital, onde ele vai ser tocado,
    respingado e ter a quina dobrada: com `H` o código continua legível com boa
    parte da área danificada."""
    import io

    import segno

    buffer = io.BytesIO()
    segno.make(url_do_cartaz(codigo), error="h").save(buffer, kind="png", scale=escala, border=2)
    return buffer.getvalue()


def qr_data_uri(codigo: str, escala: int = 6) -> str:
    """O QR embutido, para a lista da tela.

    A imagem viaja dentro do JSON porque o front autentica por header
    `Authorization`, e `<img src>` não manda header: uma rota de imagem exigiria
    baixar o binário no JavaScript só para exibir."""
    import base64

    return "data:image/png;base64," + base64.b64encode(png_do_qr(codigo, escala)).decode("ascii")


def listar(supabase) -> list[dict]:
    """Todos os cartazes, ativos e aposentados, agrupáveis por setor na tela.

    O inativo fica na lista de propósito: o ouvidor precisa ver o cartaz
    aposentado para saber que aquele código já foi usado, e para reativá-lo se
    tirou da parede por engano."""
    result = supabase.table(TABELA).select(CAMPOS_PONTO).order("setor").execute()
    return [{campo: linha.get(campo) for campo in CAMPOS_PONTO_TUPLA} for linha in (result.data or [])]


def por_codigo(supabase, codigo: str | None) -> dict | None:
    """O Ponto de escuta ATIVO de um código, ou None.

    None cobre os três casos que a decisão 6 trata igual: código ausente,
    código que ninguém cadastrou e cartaz aposentado. Nos três, quem leu o QR
    cai no formulário normal, sem origem e nunca numa página de erro."""
    if not codigo:
        return None
    limpo = (codigo or "").strip().upper()
    if not limpo or len(limpo) != TAMANHO_DO_CODIGO or set(limpo) - set(ALFABETO_DO_CODIGO):
        # Fora do alfabeto nem chega ao banco: é ruído, não consulta.
        return None
    try:
        result = supabase.table(TABELA).select(CAMPOS_PONTO).eq("codigo", limpo).eq("ativo", True).execute()
    except Exception:
        logger.warning("[Ouvidoria] Falha ao resolver o código do cartaz")
        return None
    return dict(result.data[0]) if result.data else None


def criar(supabase, setor: str, ponto: str, criado_por: str | None) -> dict | None:
    """Cadastra o cartaz e devolve a linha, ou None se o código não fechou.

    Quem decide a colisão é o índice único do banco, e não uma consulta antes do
    insert: entre a consulta e a gravação cabe outro cadastro. O sorteio
    recomeça no `23505` e o teto de tentativas existe só para o insert não virar
    laço se o banco recusar por outro motivo."""
    from postgrest.exceptions import APIError

    for _ in range(TENTATIVAS_DE_CODIGO):
        linha = {
            "codigo": gerar_codigo(),
            "setor": setor,
            "ponto": ponto,
            "criado_por": criado_por,
        }
        try:
            result = supabase.table(TABELA).insert(linha).execute()
        except APIError as exc:
            if getattr(exc, "code", None) == _CODIGO_DUPLICADO:
                continue
            raise
        if not result.data:
            # Insert que não estourou e não devolveu representação: a linha
            # pode estar gravada. Sortear de novo aqui criaria um cartaz por
            # tentativa e ainda devolveria falha no fim (o `Prefer:
            # return=minimal` de um proxy é o caminho para cá). Falha seca.
            logger.error("[Ouvidoria] O insert do Ponto de escuta não devolveu a linha gravada")
            return None
        return {campo: result.data[0].get(campo) for campo in CAMPOS_PONTO_TUPLA}
    logger.error("[Ouvidoria] Não foi possível sortear um código livre para o Ponto de escuta")
    return None


def html_do_cartaz(ponto: dict) -> str:
    """O cartaz A5, como HTML, antes de virar PDF.

    Separado da geração do PDF de propósito: é o conteúdo que precisa ser
    testado (o convite, o setor, o código por extenso), e o weasyprint é lento
    demais para rodar em cada asserção."""
    from app.services.email_constants import get_logo_data_uri
    from app.services.email_service import jinja_env

    return jinja_env.get_template("ouvidoria_cartaz.html").render(
        codigo=ponto["codigo"],
        setor=ponto["setor"],
        ponto=ponto["ponto"],
        qr_base64=qr_data_uri(ponto["codigo"], escala=10),
        url_do_qr=url_do_cartaz(ponto["codigo"]),
        endereco=endereco_impresso(ponto["codigo"]),
        logo_base64=get_logo_data_uri(),
    )


def pdf_do_cartaz(ponto: dict) -> bytes:
    """O cartaz pronto para a gráfica. Weasyprint, o mesmo que já serve Ata,
    POP e o relatório da Ouvidoria."""
    from weasyprint import HTML

    return HTML(string=html_do_cartaz(ponto)).write_pdf()


def por_id(supabase, ponto_id: str) -> dict | None:
    """Um cartaz pelo id, ativo ou aposentado.

    Aposentado entra porque reimprimir um cartaz que voltou à parede é o caso
    de uso do reativar: exigir ponto ativo obrigaria a reativar antes de ver o
    que vai ser impresso."""
    from postgrest.exceptions import APIError

    try:
        result = supabase.table(TABELA).select(CAMPOS_PONTO).eq("id", ponto_id).execute()
    except APIError as exc:
        if getattr(exc, "code", None) == "22P02":
            # Id que não é UUID: para quem chamou, é o mesmo que não existir.
            return None
        raise
    return dict(result.data[0]) if result.data else None
