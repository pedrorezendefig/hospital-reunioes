"""Service de Resolução de responsável (ADR 0008, verbete em CONTEXT.md).

Módulo profundo com duas portas:

- `montar_candidatos(supabase, id_reuniao)`: os candidatos à Resolução de uma
  Reunião — cadastro de participantes ativos (com cargo/setor), anotados com
  quem está no roster da Reunião (`na_reuniao`), roster na frente.
- `resolver_quadro(quadro, candidatos)`: anota em cada item do Quadro de
  Atribuições o `responsavel_id` + nome/cargo canônicos do cadastro.

Esconde a cascata de matching do Pipeline de Transcrição
(`participant_matcher`), o threshold de auto-match, a prioridade roster →
cadastro (a mesma da extração de Pendências da Nota) e a revalidação de ids.
Puro nos dados: não persiste nada e não muta o quadro recebido —
determinístico e idempotente. Nome ambíguo ou não encontrado fica **sem
vínculo** (`responsavel_id=None`), com o nome livre preservado; o LLM nunca
decide FK.
"""

from difflib import SequenceMatcher

from app.services.participant_matcher import DEFAULT_AUTO_THRESHOLD, _normalize, match_single_name_scored

# Plausibilidade mínima entre o nome falado (1 token) e o PRIMEIRO nome de um
# candidato. 0.85 aceita variação de grafia ("luca" ~ "lucas" = 0.89) mas
# barra nomes parecidos de pessoas distintas ("mario" ~ "maria" = 0.80) —
# vínculo errado é pior que sem vínculo.
_FUZZY_PRIMEIRO_NOME_MIN = 0.85


def montar_candidatos(supabase, id_reuniao: str) -> list[dict]:
    """Candidatos à Resolução: cadastro ativo anotado com o roster da Reunião.

    Retorna `[{id, nome_completo, cargo, setor, na_reuniao}]`, com os
    Participantes do roster na frente. Inativo não é candidato — nem quando
    ainda vinculado à Reunião (Pendência só nasce para gente ativa).
    """
    ativos = supabase.table("participantes").select("id, nome_completo, cargo, setor").eq("ativo", True).execute()
    vinculos = supabase.table("reuniao_participantes").select("participante_id").eq("id_reuniao", id_reuniao).execute()
    roster_ids = {v["participante_id"] for v in (vinculos.data or [])}

    candidatos = [
        {
            "id": row["id"],
            "nome_completo": row["nome_completo"],
            "cargo": row.get("cargo"),
            "setor": row.get("setor"),
            "na_reuniao": row["id"] in roster_ids,
        }
        for row in (ativos.data or [])
    ]
    candidatos.sort(key=lambda c: not c["na_reuniao"])
    return candidatos


def resolver_quadro(quadro: list[dict], candidatos: list[dict]) -> list[dict]:
    """Resolve o responsável de cada item do Quadro de Atribuições.

    Devolve um quadro novo (a entrada não é mutada) em que todo item carrega
    `responsavel_id` — o id do Participante quando a Resolução casa, `None`
    quando o nome fica sem vínculo (ambíguo, desconhecido ou vazio). Quando
    casa, `responsavel` e `cargo` viram os canônicos do cadastro.

    Id pré-existente válido é honrado (o vínculo já feito na conversa vence o
    nome reescrito); id forjado ou de inativo é descartado e o item volta à
    Resolução pelo nome.
    """
    por_id = {c["id"]: c for c in candidatos}
    resolvidos = []
    for item in quadro or []:
        novo = dict(item)
        pid = novo.get("responsavel_id")
        if pid not in por_id:
            pid = None
            nome = str(novo.get("responsavel") or "").strip()
            if nome:
                pid = _resolver_nome(nome, str(novo.get("cargo") or ""), candidatos)
        novo["responsavel_id"] = pid
        if pid:
            canonico = por_id[pid]
            novo["responsavel"] = canonico["nome_completo"]
            novo["cargo"] = canonico.get("cargo")
        resolvidos.append(novo)
    return resolvidos


def _resolver_nome(nome: str, cargo_item: str, candidatos: list[dict]) -> str | None:
    """Roster primeiro: a cascata só desce ao cadastro se a Reunião não casar."""
    roster = [c for c in candidatos if c.get("na_reuniao")]
    nome_normalizado = _normalize(nome)
    for grupo in (roster, candidatos):
        resultado = match_single_name_scored(nome, grupo, cargo_ia=cargo_item)
        if resultado.participante_id and resultado.score >= DEFAULT_AUTO_THRESHOLD:
            return resultado.participante_id
        pid = _fuzzy_primeiro_nome(nome_normalizado, grupo)
        if pid:
            return pid
    return None


def _fuzzy_primeiro_nome(nome_normalizado: str, grupo: list[dict]) -> str | None:
    """Cobre o gap da cascata para a transcrição de voz: "luca" não bate exato
    em "lucas" e o fuzzy global compara contra o nome COMPLETO ("lucas silva"),
    longe demais. Compara o token único falado com o primeiro nome de cada
    candidato; só casa quando exatamente um é plausível — dois plausíveis é
    ambiguidade real, e ambiguidade fica sem vínculo."""
    tokens = nome_normalizado.split()
    if len(tokens) != 1:
        return None
    hits: list[str] = []
    for candidato in grupo:
        primeiros = _normalize(candidato["nome_completo"]).split()
        if not primeiros:
            continue
        if SequenceMatcher(None, tokens[0], primeiros[0]).ratio() >= _FUZZY_PRIMEIRO_NOME_MIN:
            if candidato["id"] not in hits:
                hits.append(candidato["id"])
    return hits[0] if len(hits) == 1 else None
