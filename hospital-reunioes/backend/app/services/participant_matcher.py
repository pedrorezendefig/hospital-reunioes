"""
Service de matching de participantes.

Após a IA extrair os participantes de uma transcrição, este módulo tenta
resolver cada um contra a tabela `participantes` usando uma cascata de
estratégias (da mais estrita à mais tolerante), agora com score 0-100:

1. exato             (100)  -- nome_completo normalizado idêntico
2. invertido         (100)  -- "Sobrenome, Nome" → "Nome Sobrenome"
3. prefixo_unico     (95)   -- "Gisele Nunes" bate com único "Gisele Nunes ..."
4. primeiro_nome     (90/85/75/70) -- 1 token só; desambig. por cargo/setor
5. nome_sobrenome_pair (85) -- par primeiro+último bate em nome com tokens internos
6. fuzzy             (60-100) -- SequenceMatcher ratio >= 0.60, candidato único

O caller decide se um score é suficiente para auto-match (default >= 80).

Não cria participantes novos: se nenhuma estratégia bate, o participante
vai para `nao_reconhecidos` e o pipeline aguarda resolução manual.
"""

import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Prefixos honoríficos e profissionais a remover
# IMPORTANTE: Dra. e Sra. devem vir ANTES de Dr. e Sr. para não conflictàr
_PREFIXES_PATTERN = re.compile(
    r"^(Dra\.?|Dr\.?|Enf\.?|Eng\.?|Prof\.?a?|Sra\.?|Sr\.?|Té?cn\.?|Coord\.?|Dir\.?)\s+",
    flags=re.IGNORECASE,
)

# Threshold mínimo para o fuzzy considerar um candidato válido.
# Abaixo disso, a estratégia devolve "nenhum" e não faz sugestão.
_FUZZY_MIN_RATIO = 0.60

# Threshold default para auto-match. Matches com score >= este valor são
# persistidos automaticamente; abaixo disso viram sugestão ou não-reconhecido.
DEFAULT_AUTO_THRESHOLD = 80


@dataclass
class MatchResult:
    """Resultado de uma tentativa de matching por nome."""

    participante_id: str | None = None
    score: int = 0
    strategy: str = "nenhum"
    candidates_ambiguos: list[str] = field(default_factory=list)


def _normalize(name: str) -> str:
    """Remove prefixos e converte para minúsculas para comparação."""
    cleaned = _PREFIXES_PATTERN.sub("", name.strip())
    return cleaned.strip().lower()


def _clean_name(name: str) -> str:
    """Remove prefixos e retorna o nome capitalizado para armazenamento."""
    cleaned = _PREFIXES_PATTERN.sub("", name.strip())
    return " ".join(word.capitalize() for word in cleaned.split())


def _first_name(normalized: str) -> str:
    """Extrai o primeiro token de um nome já normalizado."""
    parts = normalized.split()
    return parts[0] if parts else ""


def _invert_surname_first(normalized: str) -> str | None:
    """Converte 'sobrenome, nome' em 'nome sobrenome'. Retorna None se não aplicável."""
    if "," not in normalized:
        return None
    left, _, right = normalized.partition(",")
    left, right = left.strip(), right.strip()
    if not left or not right:
        return None
    return f"{right} {left}"


def _context_matches(ia_value: str | None, db_value: str | None) -> bool:
    """
    Compara campos contextuais (cargo ou setor) de forma tolerante.
    Match se ambos são não-vazios e um contém o outro (após lowercase).
    """
    if not ia_value or not db_value:
        return False
    a, b = ia_value.strip().lower(), db_value.strip().lower()
    if not a or not b:
        return False
    return a in b or b in a


def _build_indices(
    rows: list[dict],
) -> tuple[dict[str, str], dict[str, list[dict]], list[tuple[list[str], str]]]:
    """Constrói os três índices consumidos pela cascata a partir das rows."""
    exact_map: dict[str, str] = {}
    by_first: dict[str, list[dict]] = {}
    token_rows: list[tuple[list[str], str]] = []

    for p in rows:
        normalized = _normalize(p["nome_completo"])
        if not normalized:
            continue
        exact_map[normalized] = p["id"]
        first = _first_name(normalized)
        if first:
            by_first.setdefault(first, []).append(p)
        token_rows.append((normalized.split(), p["id"]))

    return exact_map, by_first, token_rows


def _match_nome_sobrenome_pair(
    tokens_ia: list[str],
    token_rows: list[tuple[list[str], str]],
) -> tuple[str | None, list[str]]:
    """
    Estratégia 5 — par nome+sobrenome.
    Casa quando o primeiro token e o último token do nome extraído aparecem
    em qualquer posição nos tokens do participante cadastrado (o nome do meio
    pode diferir). Ex: "Maria Silva" → "Maria Fernanda Silva Souza".

    Requer tokens_ia com pelo menos 2 palavras distintas e a estratégia só
    dispara quando primeiro != último (evita colapsar nomes de 1 token
    repetido).

    Retorna (id_match_unico, candidates_ambiguos). Se houver 2+ rows que
    batem, id=None e candidates contém os ids ambíguos.
    """
    if len(tokens_ia) < 2:
        return None, []
    first, last = tokens_ia[0], tokens_ia[-1]
    if first == last:
        return None, []

    hits: list[str] = []
    for db_tokens, pid in token_rows:
        db_set = set(db_tokens)
        if first in db_set and last in db_set:
            if pid not in hits:
                hits.append(pid)

    if len(hits) == 1:
        return hits[0], []
    if len(hits) > 1:
        return None, hits
    return None, []


def _match_one_scored(
    normalized: str,
    tokens: list[str],
    cargo_ia: str,
    setor_ia: str,
    exact_map: dict[str, str],
    by_first: dict[str, list[dict]],
    token_rows: list[tuple[list[str], str]],
) -> MatchResult:
    """
    Aplica a cascata de 6 estratégias a um nome já normalizado/tokenizado e
    devolve MatchResult com score e estratégia vencedora.
    """
    # 1) Match exato — 100
    if normalized in exact_map:
        return MatchResult(exact_map[normalized], 100, "exato")

    # 2) Match por "sobrenome, nome" invertido — 100
    inverted = _invert_surname_first(normalized)
    if inverted and inverted in exact_map:
        return MatchResult(exact_map[inverted], 100, "invertido")

    # 3) Prefix único: nome com 2+ tokens é prefixo exato dos tokens
    # iniciais de exatamente UM participante do banco — 95
    if len(tokens) >= 2:
        prefix_hits: list[str] = []
        for db_tokens, pid in token_rows:
            if len(db_tokens) > len(tokens) and db_tokens[: len(tokens)] == tokens:
                if pid not in prefix_hits:
                    prefix_hits.append(pid)
        if len(prefix_hits) == 1:
            return MatchResult(prefix_hits[0], 95, "prefixo_unico")
        if len(prefix_hits) > 1:
            return MatchResult(None, 0, "nenhum", candidates_ambiguos=prefix_hits)

    # 4) Primeiro nome único (só quando o nome extraído é 1 token).
    #    Scores ficam em ≥ 80 para preservar o comportamento legado do pipeline
    #    ao vivo, onde desambiguação por cargo/setor já era match definitivo.
    if len(tokens) == 1:
        first = _first_name(normalized)
        candidates = by_first.get(first, []) if first else []
        if len(candidates) == 1:
            return MatchResult(candidates[0]["id"], 90, "primeiro_nome")
        if len(candidates) > 1:
            both = [
                c
                for c in candidates
                if _context_matches(cargo_ia, c.get("cargo")) and _context_matches(setor_ia, c.get("setor"))
            ]
            if len(both) == 1:
                return MatchResult(both[0]["id"], 85, "primeiro_nome+cargo+setor")

            by_cargo = [c for c in candidates if _context_matches(cargo_ia, c.get("cargo"))]
            if len(by_cargo) == 1:
                return MatchResult(by_cargo[0]["id"], 82, "primeiro_nome+cargo")

            by_setor = [c for c in candidates if _context_matches(setor_ia, c.get("setor"))]
            if len(by_setor) == 1:
                return MatchResult(by_setor[0]["id"], 80, "primeiro_nome+setor")

            # Múltiplos sem contexto suficiente — reporta ambiguidade
            ambiguos = [c["id"] for c in candidates]
            return MatchResult(None, 0, "nenhum", candidates_ambiguos=ambiguos)

    # 5) NOVA: par nome+sobrenome (tokens internos diferentes) — 85
    pair_id, pair_ambig = _match_nome_sobrenome_pair(tokens, token_rows)
    if pair_id:
        return MatchResult(pair_id, 85, "nome_sobrenome_pair")
    if pair_ambig:
        return MatchResult(None, 0, "nenhum", candidates_ambiguos=pair_ambig)

    # 6) Fuzzy match global (candidato único acima do threshold) — round(ratio*100)
    if normalized:
        best: tuple[float, str] | None = None
        ambiguous = False
        for key, pid in exact_map.items():
            ratio = SequenceMatcher(None, normalized, key).ratio()
            if ratio >= _FUZZY_MIN_RATIO:
                if best is None or ratio > best[0]:
                    ambiguous = False
                    best = (ratio, pid)
                elif ratio == best[0] and pid != best[1]:
                    ambiguous = True
        if best and not ambiguous:
            score = round(best[0] * 100)
            return MatchResult(best[1], score, "fuzzy")

    return MatchResult(None, 0, "nenhum")


def match_single_name_scored(
    nome_raw: str,
    rows: list[dict],
    *,
    cargo_ia: str = "",
    setor_ia: str = "",
) -> MatchResult:
    """
    Aplica a cascata de matching a um nome avulso contra as rows fornecidas
    e devolve MatchResult com id, score 0-100 e estratégia usada.

    O caller decide o que fazer com o score (auto vs sugestão vs externo).
    """
    if not nome_raw or not nome_raw.strip():
        return MatchResult()
    if not rows:
        return MatchResult()

    normalized = _normalize(nome_raw)
    if not normalized:
        return MatchResult()

    exact_map, by_first, token_rows = _build_indices(rows)
    tokens = normalized.split()
    return _match_one_scored(normalized, tokens, cargo_ia, setor_ia, exact_map, by_first, token_rows)


def match_single_name(
    nome_raw: str,
    rows: list[dict],
    *,
    cargo_ia: str = "",
    setor_ia: str = "",
    auto_threshold: int = DEFAULT_AUTO_THRESHOLD,
) -> str | None:
    """
    Versão retrocompatível: retorna apenas participante_id quando o score
    da cascata for >= auto_threshold (default 80). Caso contrário None.

    Usado fora do pipeline principal (ex.: resolver o responsável de uma ação
    extraída pela IA durante importação de ATA).
    """
    result = match_single_name_scored(nome_raw, rows, cargo_ia=cargo_ia, setor_ia=setor_ia)
    if result.participante_id and result.score >= auto_threshold:
        return result.participante_id
    return None


def match_participants(
    supabase,
    id_reuniao: str,
    participantes_json: list[dict],
    link_on_match: bool = True,
    *,
    ativos_rows: list[dict] | None = None,
    auto_threshold: int = DEFAULT_AUTO_THRESHOLD,
) -> tuple[list[str], list[dict]]:
    """
    Faz matching dos participantes extraídos pela IA contra o banco.
    NÃO cria participantes novos.

    Considera match apenas quando score >= auto_threshold. Abaixo disso,
    o participante vai para `nao_reconhecidos`.

    Args:
        supabase: Cliente Supabase (service_role).
        id_reuniao: ID da reunião (não usado se link_on_match=False).
        participantes_json: Lista de dicts {nome, cargo, setor, presente}.
        link_on_match: Se True (default), faz UPSERT em reuniao_participantes
            para cada match (comportamento do pipeline normal). Se False,
            apenas retorna os IDs sem criar vínculos — usado pelo fluxo de
            importação de ATAs antigas (preview stateless, antes da reunião
            existir no banco).
        ativos_rows: Lista pré-carregada de participantes ativos (deve conter
            id, nome_completo, cargo, setor). Evita refetch quando o caller
            já consultou a tabela.
        auto_threshold: Score mínimo para considerar matched. Default 80.

    Returns:
        (matched_ids, nao_reconhecidos)
    """
    if not participantes_json:
        logger.warning(f"[ParticipantMatcher] Nenhum participante extraído para {id_reuniao}")
        return ([], [])

    logger.info(
        f"[ParticipantMatcher] Iniciando matching de {len(participantes_json)} "
        f"participantes para {id_reuniao} (threshold={auto_threshold})"
    )

    if ativos_rows is not None:
        rows = ativos_rows
    else:
        existing = supabase.table("participantes").select("id, nome_completo, cargo, setor").eq("ativo", True).execute()
        rows = existing.data or []

    exact_map, by_first, token_rows = _build_indices(rows)

    # Carrega participantes já vinculados a esta reunião (pré-vinculados).
    # Skipa quando link_on_match=False (fluxo de importação de ATA antiga —
    # a reunião ainda não existe no banco).
    if link_on_match:
        pre_linked_result = (
            supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute()
        )
        pre_linked_ids: set[str] = {row["participante_id"] for row in (pre_linked_result.data or [])}
    else:
        pre_linked_ids = set()

    matched_ids: list[str] = []
    nao_reconhecidos: list[dict] = []

    for p in participantes_json:
        nome_raw = (p.get("nome") or "").strip()
        if not nome_raw:
            continue

        cargo_ia = p.get("cargo") or ""
        setor_ia = p.get("setor") or ""
        normalized = _normalize(nome_raw)
        tokens = normalized.split()
        result = _match_one_scored(normalized, tokens, cargo_ia, setor_ia, exact_map, by_first, token_rows)

        if result.participante_id and result.score >= auto_threshold:
            pid = result.participante_id
            if pid not in pre_linked_ids and pid not in matched_ids:
                matched_ids.append(pid)
            logger.info(
                f"[ParticipantMatcher] Match [{result.strategy} score={result.score}]: "
                f"'{_clean_name(nome_raw)}' → {pid}"
            )
        else:
            nao_reconhecidos.append(
                {
                    "nome": _clean_name(nome_raw),
                    "cargo": cargo_ia,
                    "setor": setor_ia or None,
                }
            )
            logger.info(
                f"[ParticipantMatcher] Não reconhecido (score={result.score} strategy={result.strategy}): '{nome_raw}'"
            )

    # UPSERT apenas dos novos matches (pré-vinculados já existem).
    # Skipa quando link_on_match=False — caller decidirá sobre o vínculo.
    if link_on_match:
        for pid in matched_ids:
            try:
                supabase.table("reuniao_participantes").upsert(
                    {"id_reuniao": id_reuniao, "participante_id": pid},
                    on_conflict="id_reuniao,participante_id",
                ).execute()
            except Exception as e:
                logger.error(f"[ParticipantMatcher] Erro ao vincular {pid}: {e}")

        all_linked_ids = list(pre_linked_ids) + [pid for pid in matched_ids if pid not in pre_linked_ids]
    else:
        # Preview stateless: só os matches realmente encontrados.
        all_linked_ids = list(matched_ids)

    logger.info(
        f"[ParticipantMatcher] Resultado para {id_reuniao}: "
        f"{len(matched_ids)} novos matches, "
        f"{len(pre_linked_ids)} pré-vinculados, "
        f"{len(nao_reconhecidos)} não reconhecidos"
    )

    return (all_linked_ids, nao_reconhecidos)
