"""
Parser de PDFs de ATAs antigas geradas pelo sistema legado.

Extrai:
- documento_id_origem (ex: ATA-ALIN-HSM-190326)
- metadados do cabeçalho (data, hora_inicio, hora_encerramento, local, facilitador, assunto)
- tabela de participantes (nome, cargo, organizacao)
- quadro de atribuicoes (num, acao, responsavel, cargo, prazo_original, meta, status)
- texto completo (fallback para a IA)

O formato das ATAs do sistema antigo segue o padrao observado em
`ATA_CallCenter_19032026`: cabecalho tabular, Secao 1 com tabela de
participantes e discussoes em prosa, Secao 2 resumo executivo e Secao 3
com o QUADRO DE ATRIBUICOES em tabela. Rodape ClickSign em todas paginas.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from io import BytesIO

import pdfplumber

logger = logging.getLogger(__name__)

# ID do documento no cabecalho (ex: ATA-ALIN-HSM-190326)
_DOCUMENTO_ID_REGEX = re.compile(r"ATA-[A-Z]{2,}-[A-Z]{2,}-\d{4,}", re.IGNORECASE)

# Data DD/MM/YYYY
_DATA_REGEX = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")

# Hora HH:MM ou HHhMM (ex: 08h12, 10:24)
_HORA_REGEX = re.compile(r"\b(\d{1,2})[h:](\d{2})\b")


def calcular_hash(arquivo_bytes: bytes) -> str:
    """Retorna SHA-256 hexdigest do arquivo."""
    return hashlib.sha256(arquivo_bytes).hexdigest()


def _normalize_cell(s: str | None) -> str:
    """Remove acentos, normaliza whitespace e lowercase para comparacao de headers."""
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    cleaned = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(cleaned.strip().lower().split())


def _is_metadados_header(row: list[str | None]) -> bool:
    """Cabecalho da tabela de metadados (Data | Inicio | Encerramento | Local)."""
    cells = [_normalize_cell(c) for c in row]
    has_data = any(c == "data" for c in cells)
    has_inicio = any("inicio" in c for c in cells)
    return has_data and has_inicio


def _is_participantes_header(row: list[str | None]) -> bool:
    cells = [_normalize_cell(c) for c in row]
    has_nome = any("nome" == c for c in cells)
    has_cargo = any("cargo" == c for c in cells)
    has_org = any("organi" in c for c in cells)
    return has_nome and has_cargo and has_org


def _is_atribuicoes_header(row: list[str | None]) -> bool:
    cells = [_normalize_cell(c) for c in row]
    has_num = any(c in {"#", "num", "n", "no"} for c in cells)
    has_acao = any("acao" in c for c in cells)
    has_resp = any(c.startswith("resp") for c in cells)
    return has_num and has_acao and has_resp


def _parse_data(text: str | None) -> str | None:
    """DD/MM/YYYY -> YYYY-MM-DD (primeira ocorrencia)."""
    if not text:
        return None
    m = _DATA_REGEX.search(text)
    if not m:
        return None
    d, mo, a = m.group(1).zfill(2), m.group(2).zfill(2), m.group(3)
    return f"{a}-{mo}-{d}"


def _parse_hora(text: str | None) -> str | None:
    """08h12 ou 14:30 -> 08:12 / 14:30."""
    if not text:
        return None
    m = _HORA_REGEX.search(text)
    if not m:
        return None
    return f"{m.group(1).zfill(2)}:{m.group(2)}"


def _extract_documento_id(text: str) -> str | None:
    m = _DOCUMENTO_ID_REGEX.search(text or "")
    return m.group(0).upper() if m else None


def _parse_metadados_from_table(table: list[list[str | None]]) -> dict:
    """
    Tabela esperada:
      header: [Data, Inicio, Encerramento, Local]
      row1:   [19/03/2026, 08h12, 10h24, Hospital ...]
    Retorna dict com chaves: data, hora_inicio, hora_encerramento, local.
    """
    result: dict = {}
    if len(table) < 2:
        return result
    header = [_normalize_cell(c) for c in table[0]]
    row = table[1] or []
    for idx, h in enumerate(header):
        val = row[idx] if idx < len(row) else None
        if not val:
            continue
        val = val.strip()
        if h == "data":
            result["data"] = _parse_data(val) or val
        elif "inicio" in h:
            result["hora_inicio"] = _parse_hora(val) or val
        elif "encerramento" in h:
            result["hora_encerramento"] = _parse_hora(val) or val
        elif "local" in h:
            result["local"] = val
    return result


def _parse_participantes_from_table(table: list[list[str | None]]) -> list[dict]:
    """Tabela: [Nome | Cargo | Organizacao] + rows. Retorna lista de dicts."""
    result: list[dict] = []
    if len(table) < 2:
        return result
    header = [_normalize_cell(c) for c in table[0]]
    idx_nome = next((i for i, c in enumerate(header) if "nome" in c), 0)
    idx_cargo = next((i for i, c in enumerate(header) if "cargo" in c), 1)
    idx_org = next((i for i, c in enumerate(header) if "organi" in c), 2)
    for row in table[1:]:
        if not row:
            continue
        def cell(i: int) -> str:
            return (row[i] or "").strip() if i < len(row) else ""
        nome = cell(idx_nome)
        if not nome:
            continue
        result.append({
            "nome": nome,
            "cargo": cell(idx_cargo),
            "organizacao": cell(idx_org),
        })
    return result


def _parse_atribuicoes_from_table(table: list[list[str | None]]) -> list[dict]:
    """
    Tabela: [# | ACAO | RESP. | CARGO | PRAZO | META/ENTREGAVEL | STATUS].
    O PDF pode renderizar celulas com quebras de linha; substituimos por espaco.
    """
    result: list[dict] = []
    if len(table) < 2:
        return result
    header = [_normalize_cell(c) for c in table[0]]
    idx_num = next((i for i, c in enumerate(header) if c in {"#", "num", "n", "no"}), 0)
    idx_acao = next((i for i, c in enumerate(header) if "acao" in c), 1)
    idx_resp = next((i for i, c in enumerate(header) if c.startswith("resp")), 2)
    idx_cargo = next((i for i, c in enumerate(header) if "cargo" in c), 3)
    idx_prazo = next((i for i, c in enumerate(header) if "prazo" in c), 4)
    idx_meta = next(
        (i for i, c in enumerate(header) if "meta" in c or "entreg" in c), 5
    )
    idx_status = next((i for i, c in enumerate(header) if "status" in c), 6)

    def cell(row: list[str | None], i: int) -> str:
        if i >= len(row):
            return ""
        val = row[i] or ""
        # pdfplumber mantem newlines dentro de celulas; achatar em espaco
        return " ".join(val.split()).strip()

    for row in table[1:]:
        if not row:
            continue
        acao = cell(row, idx_acao)
        if not acao:
            continue
        num_str = cell(row, idx_num)
        try:
            num: int | None = int(num_str) if num_str.isdigit() else None
        except ValueError:
            num = None
        # pdfplumber as vezes quebra digitos de uma data em celulas estreitas
        # ("27/03/2\n026" -> "27/03/2 026"). Recolar digitos adjacentes.
        prazo_raw = cell(row, idx_prazo)
        prazo_clean = re.sub(r"(\d)\s+(\d)", r"\1\2", prazo_raw)
        result.append({
            "num": num,
            "acao": acao,
            "responsavel": cell(row, idx_resp),
            "cargo": cell(row, idx_cargo),
            "prazo_original": prazo_clean,
            "meta": cell(row, idx_meta),
            "status": cell(row, idx_status) or "PENDENTE",
        })
    return result


def extrair_estrutura(arquivo_bytes: bytes) -> dict:
    """
    Parseia um PDF de ATA antiga e retorna dict estruturado.

    Returns:
        {
          "documento_id_origem": str | None,
          "metadados_brutos": {
            "data": str | None,                # ISO YYYY-MM-DD
            "hora_inicio": str | None,         # HH:MM
            "hora_encerramento": str | None,
            "local": str | None,
            "facilitador": str | None,
            "assunto": str | None,
            "titulo_ata": str | None,
          },
          "tabela_participantes": list[dict],
          "tabela_atribuicoes": list[dict],
          "texto_completo": str,
          "paginas": int,
        }

    Pode lancar excecoes de pdfplumber em arquivos corrompidos. O chamador
    deve tratar como 400 no endpoint.
    """
    result: dict = {
        "documento_id_origem": None,
        "metadados_brutos": {},
        "tabela_participantes": [],
        "tabela_atribuicoes": [],
        "texto_completo": "",
        "paginas": 0,
    }

    texto_paginas: list[str] = []
    tabelas_encontradas: list[list[list[str | None]]] = []

    with pdfplumber.open(BytesIO(arquivo_bytes)) as pdf:
        for page in pdf.pages:
            texto_paginas.append(page.extract_text() or "")
            for tbl in (page.extract_tables() or []):
                cleaned = [
                    [(c.strip() if isinstance(c, str) else None) for c in row]
                    for row in tbl
                ]
                tabelas_encontradas.append(cleaned)
        result["paginas"] = len(pdf.pages)

    result["texto_completo"] = "\n\n".join(texto_paginas)

    # documento_id busca em todo o texto
    result["documento_id_origem"] = _extract_documento_id(result["texto_completo"])

    # Classifica tabelas por heuristica de header
    for table in tabelas_encontradas:
        if not table or not table[0]:
            continue
        header = table[0]
        if _is_metadados_header(header):
            meta = _parse_metadados_from_table(table)
            result["metadados_brutos"].update(meta)
        elif _is_participantes_header(header):
            result["tabela_participantes"] = _parse_participantes_from_table(table)
        elif _is_atribuicoes_header(header):
            result["tabela_atribuicoes"] = _parse_atribuicoes_from_table(table)

    # Regex auxiliar para facilitador / assunto / titulo
    texto = result["texto_completo"]
    m = re.search(r"Facilitador\(?a?\)?\s*:?\s*([^\n]+)", texto, re.IGNORECASE)
    if m:
        result["metadados_brutos"]["facilitador"] = m.group(1).strip()

    m = re.search(r"Assunto\s*:\s*([^\n]+)", texto, re.IGNORECASE)
    if m:
        result["metadados_brutos"]["assunto"] = m.group(1).strip()

    # Titulo da ata: linha tipo "REUNIAO DE ALINHAMENTO OPERACIONAL" no inicio
    for linha in [l.strip() for l in texto.splitlines() if l.strip()][:15]:
        if re.match(r"^REUNI[AÃ]O\s+DE\s+", linha, re.IGNORECASE):
            result["metadados_brutos"]["titulo_ata"] = linha
            break

    # Fallback: se pdfplumber nao reconheceu a tabela de metadados (cabecalho
    # sem bordas, por exemplo), extrair data/horas do texto do inicio do doc.
    meta = result["metadados_brutos"]
    texto_inicio = texto[:3000]
    if not meta.get("data"):
        d = _parse_data(texto_inicio)
        if d:
            meta["data"] = d
    if not meta.get("hora_inicio") or not meta.get("hora_encerramento"):
        horas = _HORA_REGEX.findall(texto_inicio)
        if horas and not meta.get("hora_inicio"):
            hh, mm = horas[0]
            meta["hora_inicio"] = f"{hh.zfill(2)}:{mm}"
        if len(horas) >= 2 and not meta.get("hora_encerramento"):
            hh, mm = horas[1]
            meta["hora_encerramento"] = f"{hh.zfill(2)}:{mm}"

    logger.info(
        f"[pdf_parser_ata_migrada] documento_id={result['documento_id_origem']!r} "
        f"participantes={len(result['tabela_participantes'])} "
        f"atribuicoes={len(result['tabela_atribuicoes'])} "
        f"paginas={result['paginas']}"
    )

    return result
