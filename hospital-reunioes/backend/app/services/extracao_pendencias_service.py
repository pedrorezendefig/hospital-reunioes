"""Extração de Pendências do corpo de uma Nota (issue #34, ADR 0004).

Módulo profundo com uma porta de entrada: `extrair(supabase, corpo, roster,
hoje) → propostas`. A IA **propõe** (descrição, responsável, prazo) e o
Facilitador confirma/edita/descarta — nada é persistido aqui; a criação reusa
`criar_pendencias_de_nota` (issue #33).

Reusa o passo de estruturação JSON do Pipeline (OpenRouter primário + fallback
OpenAI direto) e casa o responsável **primeiro contra o roster** da Nota,
depois contra o cadastro (`_find_participante`). Externo fica só como nome
(sem id, sem cobrança). Prazo relativo ("sexta", "semana que vem") vira data:
a IA converte com a DATA BASE injetada e, se devolver a expressão crua, o
parse determinístico daqui cobre.
"""

import json
import logging
import re
import unicodedata
from datetime import date, datetime, timedelta

from openai import OpenAI

from app.config import settings
from app.services.ai_processor import _get_llm, _llm_provider, _log_llm_call
from app.services.pendencia_service import _find_participante, _normalizar_prazo
from app.services.prompt_loader import load_prompt, render_prompt

logger = logging.getLogger(__name__)


class ExtracaoIndisponivelError(RuntimeError):
    """A IA não respondeu: provedores indisponíveis ou resposta ilegível."""


def extrair(supabase, corpo: str, roster: list[dict], hoje: date | str | None = None) -> list[dict]:
    """Propõe Pendências a partir do corpo de uma Nota.

    Args:
        supabase: client do banco (fallback de responsável no cadastro).
        corpo: texto livre da Nota. Vazio/branco → lista vazia sem chamar a IA.
        roster: saída de `_roster_da_nota` — itens com `participante_id`
            (Colaborador do cadastro) ou só `nome` (avulso/externo).
        hoje: data base para prazos relativos (default: data corrente).

    Returns:
        Propostas editáveis, não persistidas:
        `[{descricao_acao, responsavel_id, responsavel_nome, prazo}]`.

    Raises:
        ExtracaoIndisponivelError: primário e fallback de LLM falharam.
    """
    if not corpo or not str(corpo).strip():
        return []
    if isinstance(hoje, str):
        hoje = date.fromisoformat(hoje)
    hoje = hoje or datetime.now().date()
    roster = roster or []

    bruto = _chamar_llm(str(corpo), roster, hoje)

    propostas = []
    for item in bruto.get("pendencias") or []:
        descricao = str(item.get("descricao") or "").strip()
        if not descricao:
            continue
        responsavel_id, responsavel_nome = _casar_responsavel(supabase, item.get("responsavel"), roster)
        propostas.append(
            {
                "descricao_acao": descricao[:500],
                "responsavel_id": responsavel_id,
                "responsavel_nome": responsavel_nome,
                "prazo": _normalizar_prazo_proposta(item.get("prazo"), hoje),
            }
        )
    logger.info(f"[Extracao Nota] {len(propostas)} propostas extraídas do corpo ({len(str(corpo))} chars)")
    return propostas


# ─── Chamada LLM (passo de estruturação do Pipeline) ─────────────────────────


_DIA_SEMANA_PT = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo")


def _chamar_llm(corpo: str, roster: list[dict], hoje: date) -> dict:
    """Estruturação JSON via LLM — OpenRouter primário, fallback OpenAI direto.

    Sem chave configurada (provider 'mock'), devolve lista vazia: a extração
    não inventa Pendência sem IA. Testes substituem esta função inteira.
    """
    provider = _llm_provider()
    if provider == "mock":
        logger.warning("Nenhuma chave LLM configurada — extração de Pendências devolve lista vazia")
        return {"pendencias": []}

    client, model, extra = _get_llm()
    _log_llm_call("extracao-nota", provider, model)

    roster_txt = (
        "\n".join(
            f"- {e.get('nome')}" + (" (do cadastro)" if e.get("participante_id") else " (externo)")
            for e in roster
            if e.get("nome")
        )
        or "Ninguém marcado."
    )
    user_content = render_prompt(
        "user_extracao_pendencias_nota",
        hoje_str=hoje.strftime("%d/%m/%Y"),
        dia_semana_pt=_DIA_SEMANA_PT[hoje.weekday()],
        hoje_iso=hoje.isoformat(),
        roster_txt=roster_txt,
        corpo=corpo[:15000],
    )
    system_prompt = load_prompt("extracao_pendencias_nota")

    def _call(_client: OpenAI, _model: str, _extra: dict) -> dict:
        response = _client.chat.completions.create(
            model=_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            **_extra,
        )
        return json.loads(response.choices[0].message.content)

    try:
        return _call(client, model, extra)
    except Exception as e:
        has_openai_fallback = (
            provider == "openrouter" and settings.openai_api_key and settings.openai_api_key != "your-openai-key"
        )
        if not has_openai_fallback:
            logger.error(f"[Extracao Nota] Falha na chamada LLM via {provider}: {e}")
            raise ExtracaoIndisponivelError(str(e)) from e
        logger.warning(f"[Extracao Nota] OpenRouter falhou ({type(e).__name__}: {e}), tentando fallback OpenAI direto")
        try:
            fallback_client = OpenAI(api_key=settings.openai_api_key)
            _log_llm_call("extracao-nota", "openai-fallback", settings.llm_fallback_model)
            return _call(fallback_client, settings.llm_fallback_model, {})
        except Exception as e2:
            logger.error(f"[Extracao Nota] Fallback OpenAI também falhou: {e2}")
            raise ExtracaoIndisponivelError(str(e2)) from e2


# ─── Casamento do responsável (roster primeiro, depois cadastro) ─────────────


def _sem_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(ch for ch in decomposto if not unicodedata.combining(ch)).lower().strip()


def _casar_responsavel(supabase, nome, roster: list[dict]) -> tuple[str | None, str | None]:
    """Resolve o responsável proposto pela IA: roster primeiro (exato, depois
    parcial), então cadastro; sem match, fica externo — só o nome, sem id."""
    if not nome or str(nome).strip().lower() in {"null", "none", "n/a"}:
        return None, None
    alvo = _sem_acentos(str(nome))

    for entry in roster:  # exato
        if _sem_acentos(entry.get("nome") or "") == alvo:
            return entry.get("participante_id"), entry.get("nome")
    for entry in roster:  # parcial: "ana" ⊂ "ana lima" (ou o inverso)
        nome_entry = _sem_acentos(entry.get("nome") or "")
        if nome_entry and (alvo in nome_entry or nome_entry in alvo):
            return entry.get("participante_id"), entry.get("nome")

    achado = _find_participante(supabase, str(nome).strip())
    if achado and achado.get("id"):
        return achado["id"], achado.get("nome_completo") or str(nome).strip()

    return None, str(nome).strip()


# ─── Prazo: formatos estruturados + linguagem natural pt-BR ──────────────────


_DIAS_NATURAL = ("segunda", "terca", "quarta", "quinta", "sexta", "sabado", "domingo")
_PREFIXOS_PRAZO = re.compile(r"^(ate|para|pra|em|na|no|nesta|neste|proxima|proximo|a|o)\s+")


def _parse_prazo_natural(raw, hoje: date) -> str | None:
    """Converte expressão relativa pt-BR em YYYY-MM-DD a partir de `hoje`.

    Cobre o vocabulário do domínio: "hoje", "amanhã", dias da semana ("sexta",
    "sexta-feira" → a PRÓXIMA ocorrência, nunca o próprio dia) e "semana que
    vem" (+7). Fora disso, None — a proposta fica sem prazo, editável na UI.
    """
    if not raw or not isinstance(raw, str):
        return None
    texto = _sem_acentos(raw)
    anterior = None
    while anterior != texto:  # remove prefixos encadeados: "até a próxima sexta"
        anterior = texto
        texto = _PREFIXOS_PRAZO.sub("", texto)

    if texto == "hoje":
        return hoje.isoformat()
    if texto == "amanha":
        return (hoje + timedelta(days=1)).isoformat()
    if texto in {"semana que vem", "semana", "proxima semana"}:
        return (hoje + timedelta(days=7)).isoformat()
    for i, dia in enumerate(_DIAS_NATURAL):
        if texto.startswith(dia):
            delta = (i - hoje.weekday()) % 7
            return (hoje + timedelta(days=delta or 7)).isoformat()
    return None


def _normalizar_prazo_proposta(raw, hoje: date) -> str | None:
    """Linguagem natural primeiro (sem warning de formato), depois os formatos
    estruturados do Pipeline (`_normalizar_prazo`: ISO, DD/MM/YYYY…)."""
    return _parse_prazo_natural(raw, hoje) or _normalizar_prazo(raw)
