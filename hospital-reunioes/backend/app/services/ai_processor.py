import json
import logging
import re
from datetime import datetime, timedelta

from openai import OpenAI

from app.config import settings
from app.services.prompt_loader import load_prompt, render_prompt

logger = logging.getLogger(__name__)


_OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://hospitalsaomatheus.cloud",
    "X-Title": "Hospital Reunioes",
}


def _llm_provider() -> str:
    """Retorna 'openrouter' ou 'mock' conforme a chave do OpenRouter."""
    if settings.openrouter_api_key and settings.openrouter_api_key != "your-openrouter-key":
        return "openrouter"
    return "mock"


def _get_llm() -> tuple[OpenAI, str, dict]:
    """Retorna (client, model, extra_kwargs) do OpenRouter.

    O cliente é o SDK `openai` apontado para o OpenRouter (mesma superfície de
    API). Caller deve checar _llm_provider() == 'mock' antes para evitar
    instanciar cliente sem chave.
    """
    client = OpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.openrouter_base_url,
    )
    return client, settings.llm_model, {"extra_headers": _OPENROUTER_HEADERS}


def _log_llm_call(reuniao_id: str, provider: str, model: str) -> None:
    """Loga chamada LLM com a chave do OpenRouter mascarada."""
    key_used = settings.openrouter_api_key
    masked = f"{key_used[:8]}...{key_used[-4:]}" if len(key_used) >= 12 else "***"
    logger.info(f"[AI] Chamando LLM via {provider} (modelo={model}, chave={masked}, reuniao={reuniao_id})")


def _build_system_prompt(data_reuniao: str) -> str:
    """Carrega o system prompt de extração e injeta a data base."""
    base = load_prompt("extracao_ata")
    return base + f"\nDATA BASE DESTA REUNIÃO: {data_reuniao} (use esta data para calcular todos os prazos relativos)"


_STATUS_VALIDOS = {"ABERTO", "EM_ANDAMENTO", "CONCLUIDO"}
_STATUS_ALIAS = {
    "ABERTO": "ABERTO",
    "EM ABERTO": "ABERTO",
    "PENDENTE": "ABERTO",
    "NOVO": "ABERTO",
    "EM ANDAMENTO": "EM_ANDAMENTO",
    "EM_ANDAMENTO": "EM_ANDAMENTO",
    "EM PROGRESSO": "EM_ANDAMENTO",
    "EM_PROGRESSO": "EM_ANDAMENTO",
    "CONCLUIDO": "CONCLUIDO",
    "CONCLUÍDO": "CONCLUIDO",
    "FINALIZADO": "CONCLUIDO",
    "COMPLETO": "CONCLUIDO",
}


def _normalizar_status_atribuicao(raw: str | None) -> str:
    if not raw or not isinstance(raw, str):
        return "ABERTO"
    key = raw.strip().upper()
    return _STATUS_ALIAS.get(key, "ABERTO")


def _normalizar_prazo(raw) -> str | None:
    """Converte prazo para YYYY-MM-DD; preserva 'Fluxo contínuo'; null caso contrário."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    valor = raw.strip()
    if not valor:
        return None
    # Aceita variações de 'Fluxo contínuo' (case-insensitive, com/sem acento)
    normalizado_lower = valor.lower().replace("í", "i").replace("ú", "u")
    if normalizado_lower in {"fluxo continuo", "fluxo contínuo"}:
        return "Fluxo contínuo"
    # Tenta converter DD/MM/YYYY -> YYYY-MM-DD
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", valor)
    if m:
        d, mes, ano = m.group(1), m.group(2), m.group(3)
        return f"{ano}-{mes.zfill(2)}-{d.zfill(2)}"
    # Já no formato YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", valor):
        return valor
    # Qualquer outra string é considerada inválida como prazo estruturado
    return None


def process_transcricao(
    transcricao_txt: str,
    reuniao_id: str,
    tipo_reuniao: str = "Reunião",
    participantes_pre_cadastrados: str = "",
    participantes_ativos_dir: str = "",
    objetivo_agendado: str = "",
) -> dict:
    """
    Envia a transcrição para o GPT-4o-mini e retorna o json_ata estruturado.
    Em caso de falha, retorna dict com campo 'error'.
    """
    provider = _llm_provider()
    if provider == "mock":
        logger.warning("Nenhuma chave do OpenRouter (OPENROUTER_API_KEY) configurada — ativando modo mock")
        return _mock_ata(reuniao_id, tipo_reuniao)

    client, model, extra = _get_llm()
    _log_llm_call(reuniao_id, provider, model)

    # Data atual injetada para que a IA calcule prazos relativos corretamente
    hoje_str = datetime.now().strftime("%d/%m/%Y")
    hoje_iso = datetime.now().strftime("%Y-%m-%d")
    dia_semana = datetime.now().strftime("%A")  # Monday, Tuesday, etc.
    dias_pt = {
        "Monday": "segunda-feira",
        "Tuesday": "terça-feira",
        "Wednesday": "quarta-feira",
        "Thursday": "quinta-feira",
        "Friday": "sexta-feira",
        "Saturday": "sábado",
        "Sunday": "domingo",
    }
    dia_semana_pt = dias_pt.get(dia_semana, dia_semana)

    user_content = render_prompt(
        "user_extracao",
        tipo_reuniao=tipo_reuniao,
        reuniao_id=reuniao_id,
        hoje_str=hoje_str,
        dia_semana_pt=dia_semana_pt,
        hoje_iso=hoje_iso,
        transcricao_txt=transcricao_txt,
        participantes_pre_cadastrados=participantes_pre_cadastrados or "Nenhum participante pré-cadastrado",
        participantes_ativos_dir=participantes_ativos_dir or "Nenhum participante ativo cadastrado",
        objetivo_agendado=objetivo_agendado or "Não informado",
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_system_prompt(hoje_iso)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
            **extra,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        # Normalização defensiva de prazos e status do quadro_atribuicoes
        if "quadro_atribuicoes" in parsed:
            for item in parsed["quadro_atribuicoes"]:
                item["prazo"] = _normalizar_prazo(item.get("prazo"))
                item["status"] = _normalizar_status_atribuicao(item.get("status"))
                # Garantir existência dos novos campos opcionais para evitar KeyError no template
                item.setdefault("objetivo_meta", item.get("objetivo_meta") or "")

        # Garantir arrays HSM para compat com templates (6 seções oficiais)
        parsed.setdefault("discussao", [])
        parsed.setdefault("objetivo", parsed.get("objetivo") or "")

        logger.info(
            f"[AI] LLM ({provider}) processou reuniao {reuniao_id} com "
            f"{len(parsed.get('quadro_atribuicoes', []))} acoes e "
            f"{len(parsed.get('discussao', []))} topicos de discussao."
        )
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON da IA para reunião {reuniao_id}: {e}")
        return {"error": f"Resposta da IA inválida: {e}"}
    except Exception as e:
        logger.error(f"Erro ao chamar LLM ({provider}) para reunião {reuniao_id}: {e}")
        return {"error": str(e)}


def process_ata_migrada(
    estrutura: dict,
    participantes_ativos_dir: str = "",
) -> dict:
    """
    Normaliza uma ATA antiga (migrada do sistema legado) em JSON compatível com
    o schema do pipeline normal. Não persiste nada; o caller decide.

    Args:
        estrutura: dict retornado por pdf_parser_ata_migrada.extrair_estrutura().
        participantes_ativos_dir: listagem dos participantes cadastrados no
            sistema para a IA conseguir resolver nomes parciais.

    Returns:
        dict com schema HSM: titulo, tipo, data, hora_inicio, hora_fim,
        facilitador_nome, assunto, objetivo, participantes, discussao,
        quadro_atribuicoes. Em caso de erro retorna {"error": str}.
    """
    data_reuniao = (estrutura.get("metadados_brutos") or {}).get("data") or ""

    provider = _llm_provider()
    if provider == "mock":
        logger.warning("Nenhuma chave LLM configurada — ATA migrada em modo mock")
        return _mock_ata_migrada(estrutura)

    client, model, extra = _get_llm()
    _log_llm_call(f"ata-migrada/{estrutura.get('documento_id_origem') or '?'}", provider, model)

    user_content = render_prompt(
        "user_extracao_ata_migrada",
        data_reuniao=data_reuniao or "desconhecida",
        participantes_ativos_dir=participantes_ativos_dir or "Nenhum participante ativo cadastrado",
        documento_id_origem=estrutura.get("documento_id_origem") or "desconhecido",
        metadados_brutos_json=json.dumps(estrutura.get("metadados_brutos") or {}, ensure_ascii=False, indent=2),
        tabela_participantes_json=json.dumps(estrutura.get("tabela_participantes") or [], ensure_ascii=False, indent=2),
        tabela_atribuicoes_json=json.dumps(estrutura.get("tabela_atribuicoes") or [], ensure_ascii=False, indent=2),
        texto_completo=(estrutura.get("texto_completo") or "")[:15000],
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": load_prompt("extracao_ata_migrada")},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            **extra,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        # Normalização defensiva de prazos no formato YYYY-MM-DD
        for item in parsed.get("quadro_atribuicoes", []) or []:
            prazo_raw = item.get("prazo")
            if prazo_raw and isinstance(prazo_raw, str):
                m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", prazo_raw.strip())
                if m:
                    d, mes, ano = m.group(1), m.group(2), m.group(3)
                    item["prazo"] = f"{ano}-{mes.zfill(2)}-{d.zfill(2)}"

        logger.info(
            f"[AI ata-migrada] LLM ({provider}) processou documento="
            f"{estrutura.get('documento_id_origem')!r} "
            f"participantes={len(parsed.get('participantes', []))} "
            f"atribuicoes={len(parsed.get('quadro_atribuicoes', []))}"
        )
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"[AI ata-migrada] Erro ao parsear JSON: {e}")
        return {"error": f"Resposta da IA inválida: {e}"}
    except Exception as e:
        logger.error(f"[AI ata-migrada] Erro ao chamar LLM ({provider}): {e}")
        return {"error": str(e)}


def _mock_ata_migrada(estrutura: dict) -> dict:
    """Fallback determinístico para ambientes sem chave do OpenRouter (testes locais).

    Retorna JSON no formato HSM oficial (6 seções, sem campos legados).
    """
    meta = estrutura.get("metadados_brutos") or {}
    logger.info("[AI ata-migrada] MOCK: usando estrutura parseada sem IA")

    participantes = [
        {
            "nome": p.get("nome", ""),
            "cargo": p.get("cargo", ""),
            "setor": None,
            "presente": True,
        }
        for p in (estrutura.get("tabela_participantes") or [])
    ]

    atribuicoes = []
    data_reuniao = meta.get("data")
    for a in estrutura.get("tabela_atribuicoes") or []:
        prazo_orig = a.get("prazo_original", "") or ""
        prazo_iso: str | None = None
        m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", prazo_orig.strip())
        if m:
            d, mes, ano = m.group(1), m.group(2), m.group(3)
            prazo_iso = f"{ano}-{mes.zfill(2)}-{d.zfill(2)}"
        elif data_reuniao and re.match(r"^\d+\s*dias?$", prazo_orig.strip(), re.IGNORECASE):
            from datetime import datetime as _dt
            from datetime import timedelta as _td

            try:
                dias = int(prazo_orig.strip().split()[0])
                base = _dt.strptime(data_reuniao, "%Y-%m-%d")
                prazo_iso = (base + _td(days=dias)).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                prazo_iso = None
        atribuicoes.append(
            {
                "acao": a.get("acao", ""),
                "responsavel": a.get("responsavel", ""),
                "cargo": a.get("cargo", ""),
                "objetivo_meta": a.get("meta", "") or "",
                "prazo": prazo_iso,
                "prazo_original": prazo_orig,
                "entregavel": a.get("meta", "") or "A definir",
                "status": a.get("status", "PENDENTE"),
            }
        )

    # discussao[] mínima: um único tópico de preenchimento para ATAs mockadas —
    # o pipeline real substituirá isso pelo resultado estruturado do LLM.
    discussao_mock = [
        {
            "titulo": "Registro consolidado da reunião",
            "descricao": (
                "[MOCK sem LLM] A reunião foi registrada de forma consolidada. "
                "Executar a importação com OPENROUTER_API_KEY "
                "configurada para gerar a estruturação completa em tópicos discretos."
            ),
            "contribuicoes": [],
            "divergencias": [],
            "decisao": "A definir",
            "responsavel": None,
        }
    ]

    return {
        "titulo": meta.get("titulo_ata", "ATA migrada"),
        "tipo": "Coordenação",
        "data": data_reuniao,
        "hora_inicio": meta.get("hora_inicio"),
        "hora_fim": meta.get("hora_encerramento"),
        "facilitador_nome": (meta.get("facilitador") or "").split(" — ")[0] or None,
        "assunto": meta.get("assunto"),
        "objetivo": None,
        "participantes": participantes,
        "discussao": discussao_mock,
        "quadro_atribuicoes": atribuicoes,
        "_mock": True,
    }


def process_correcao(
    transcricao_txt: str,
    json_ata_atual: dict,
    instrucao_correcao: str,
    reuniao_id: str,
    tipo_reuniao: str = "Reunião",
) -> dict:
    """
    Aplica uma instrução de correção sobre uma ata já gerada.
    """
    provider = _llm_provider()
    if provider == "mock":
        logger.warning("Modo MOCK ativo para correção (sem chave LLM)")
        return json_ata_atual

    client, model, extra = _get_llm()
    _log_llm_call(f"correcao/{reuniao_id}", provider, model)
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    user_content = render_prompt(
        "user_correcao",
        json_ata_atual=json.dumps(json_ata_atual, indent=2, ensure_ascii=False),
        instrucao_correcao=instrucao_correcao,
        transcricao_txt=transcricao_txt[:5000],
        hoje_iso=hoje_iso,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": load_prompt("correcao_ata")},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
            **extra,
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        logger.info(f"[AI] Correcao aplicada com sucesso na ata {reuniao_id} via {provider}")
        return parsed
    except Exception as e:
        logger.error(f"Erro ao corrigir ata {reuniao_id} via {provider}: {e}")
        return {"error": str(e)}


def chat_correcao(
    json_ata_atual: dict,
    messages: list[dict],
    section_context: str | None = None,
    current_plan: list[dict] | None = None,
) -> dict:
    """
    Processa uma mensagem do chat de correção.
    Retorna { reply: str, correction_plan: list[dict] }.
    Leve e síncrono — NÃO dispara pipeline.

    `current_plan` é a lista de correções pendentes hoje na UI (fonte da verdade
    no frontend, já considerando remoções manuais). A IA recebe ela como ponto
    de partida e retorna a lista atualizada, em vez de reconstruir tudo do
    chat history a cada turno.

    Se a chamada ao OpenRouter falha (auth, rate limit, indisponibilidade),
    devolve um erro claro ao usuário — sem failover automático.
    """
    provider = _llm_provider()
    plan_in = current_plan or []
    if provider == "mock":
        logger.warning("Modo MOCK ativo para chat correção (sem chave LLM)")
        return {
            "reply": "[MOCK] Entendi sua correção. Clique em 'Aplicar' quando estiver pronto.",
            "correction_plan": plan_in,
        }

    client, model, extra = _get_llm()
    _log_llm_call("chat-correcao", provider, model)
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    # Formatar histórico do chat
    chat_history = "\n".join(
        f"{'Facilitador' if m['role'] == 'user' else 'Assistente'}: {m['content']}" for m in messages
    )

    user_content = render_prompt(
        "chat_correcao_user",
        json_ata_atual=json.dumps(json_ata_atual, indent=2, ensure_ascii=False),
        section_context=section_context or "Nenhuma seção específica selecionada",
        chat_history=chat_history,
        hoje_iso=hoje_iso,
        current_plan=json.dumps(plan_in, indent=2, ensure_ascii=False),
    )
    system_prompt = load_prompt("chat_correcao_system")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            **extra,
        )
        parsed = json.loads(response.choices[0].message.content)
    except Exception as e:
        logger.error(f"Erro no chat de correção via {provider}: {e}")
        return {
            "reply": "Desculpe, houve um erro ao processar sua mensagem. Tente novamente.",
            "correction_plan": [],
        }

    logger.info(f"[AI] Chat correcao via {provider}: {len(parsed.get('correction_plan', []))} correcoes no plano")
    return {
        "reply": parsed.get("reply", ""),
        "correction_plan": parsed.get("correction_plan", []),
    }


def chat_ata_guiada(
    rascunho: dict,
    messages: list[dict],
    section_context: str | None = None,
    documento_apoio: str | None = None,
    candidatos: list[dict] | None = None,
) -> dict:
    """Agente da Ata Guiada (ADR 0005): a cada turno organiza o relato do
    Facilitador num `json_ata` enxuto (`resumo_executivo` + `quadro_atribuicoes`)
    e faz a próxima pergunta de lacuna, priorizando responsável e prazo. Stateless
    — recebe o rascunho atual + o histórico da conversa e devolve `{ reply, rascunho }`.

    `section_context` (ADR 0006, #58): a seção que o Facilitador apontou (⌖) — o
    Resumo ou uma ação específica. Quando presente, o agente concentra a correção
    nela e preserva o resto do rascunho. Opera sobre o rascunho em memória pelo
    próprio chat da Guiada — não usa o `/corrigir` (que baixa Transcrição e regenera
    PDF, inexistentes aqui).

    `documento_apoio` (ADR 0006) é o texto opcional de um Documento de apoio anexado,
    reenviado a cada turno como **contexto sob demanda**: vai ao prompt, mas o agente
    só o usa quando o Facilitador referencia — nunca despeja na ata sozinho.

    `candidatos` (ADR 0008, #79): a lista do serviço de Resolução
    (`montar_candidatos`) — entra no prompt para o agente conversar com os nomes
    canônicos e perguntar no ambíguo; após a resposta, o quadro é re-resolvido
    deterministicamente (`resolver_quadro`) — o LLM nunca decide FK.

    Espelha o `chat_correcao` (síncrono, request/response, OpenRouter-only, sem
    failover). Sem chave de IA configurada, cai no caminho MOCK — não quebra o
    endpoint.
    """
    rascunho = dict(rascunho or {})
    rascunho.setdefault("resumo_executivo", "")
    rascunho.setdefault("quadro_atribuicoes", [])

    provider = _llm_provider()
    if provider == "mock":
        # MOCK (sem chave): acumula o relato do Facilitador no resumo — dá sinal de
        # vida e habilita o "Concluir". Organizar o relato e extrair ações exige IA.
        relato = " ".join(m.get("content", "").strip() for m in messages if m.get("role") == "user").strip()
        if relato:
            rascunho["resumo_executivo"] = relato
        logger.warning("Modo MOCK ativo para chat da Ata Guiada (sem chave LLM)")
        return {
            "reply": "[MOCK] Anotei o relato no resumo. A organização e a extração de ações exigem a IA configurada.",
            "rascunho": rascunho,
        }

    client, model, extra = _get_llm()
    _log_llm_call("chat-ata-guiada", provider, model)
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    chat_history = "\n".join(
        f"{'Facilitador' if m['role'] == 'user' else 'Assistente'}: {m['content']}" for m in messages
    )
    bloco_documento = ""
    if documento_apoio and documento_apoio.strip():
        bloco_documento = (
            "\nDOCUMENTO DE APOIO (contexto sob demanda — use SÓ quando o Facilitador "
            "referenciar; NUNCA despeje seu conteúdo na ata por conta própria):\n"
            f"{documento_apoio.strip()}\n"
        )
    user_content = render_prompt(
        "chat_ata_guiada_user",
        rascunho_atual=json.dumps(rascunho, indent=2, ensure_ascii=False),
        section_context=section_context or "Nenhuma seção específica selecionada",
        chat_history=chat_history,
        hoje_iso=hoje_iso,
        candidatos=_bloco_candidatos(candidatos),
        documento_apoio=bloco_documento,
    )
    system_prompt = load_prompt("chat_ata_guiada_system")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            **extra,
        )
        parsed = json.loads(response.choices[0].message.content)
        # response_format=json_object é só um hint — nem todo modelo garante objeto
        # top-level. Um array/string/null aqui viraria AttributeError fora do try; trata
        # como erro pra cair no caminho gracioso abaixo (CA5: nada de 500 cru).
        if not isinstance(parsed, dict):
            raise ValueError("resposta da IA não é um objeto JSON")
    except Exception as e:
        # Mesma postura do chat_correcao: sem failover, erro claro ao Facilitador.
        # Mas o rascunho é acumulativo — preserva o atual em vez de zerar (não perde
        # o que ele já montou nem força um 500 cru no endpoint).
        logger.error(f"Erro no chat da Ata Guiada via {provider}: {e}")
        return {
            "reply": "Desculpe, houve um erro ao processar sua mensagem. Tente novamente.",
            "rascunho": rascunho,
        }

    rascunho_out = _normalizar_rascunho_guiado(parsed.get("rascunho"), rascunho)
    if candidatos is not None:
        # ADR 0008: o LLM conversa, o backend vincula. Qualquer `responsavel_id`
        # devolvido pelo modelo é descartado e o quadro inteiro é re-resolvido
        # deterministicamente — FK nunca vem de modelo generativo.
        from app.services.resolucao_service import resolver_quadro

        sem_id_do_llm = [
            {k: v for k, v in item.items() if k != "responsavel_id"} for item in rascunho_out["quadro_atribuicoes"]
        ]
        rascunho_out["quadro_atribuicoes"] = resolver_quadro(sem_id_do_llm, candidatos)
    logger.info(f"[AI] Chat ata guiada via {provider}: {len(rascunho_out['quadro_atribuicoes'])} ação(ões) no quadro")
    return {"reply": parsed.get("reply", ""), "rascunho": rascunho_out}


def _bloco_candidatos(candidatos: list[dict] | None) -> str:
    """Formata a lista de candidatos do serviço de Resolução para o prompt
    (ADR 0008): nome canônico + cargo/setor, com os Participantes da Reunião
    marcados. Sem candidatos, o bloco some — o prompt segue como antes."""
    if not candidatos:
        return ""
    linhas = []
    for c in candidatos:
        cargo_setor = " — ".join(p for p in [c.get("cargo"), c.get("setor")] if p)
        linha = f"- {c['nome_completo']}" + (f" ({cargo_setor})" if cargo_setor else "")
        if c.get("na_reuniao"):
            linha += " [participante desta reunião]"
        linhas.append(linha)
    return (
        "\nCANDIDATOS A RESPONSÁVEL (o cadastro oficial — converse usando estes nomes "
        "canônicos; priorize os participantes desta reunião):\n" + "\n".join(linhas) + "\n"
    )


def _normalizar_rascunho_guiado(novo: dict | None, atual: dict) -> dict:
    """Garante o shape enxuto (`resumo_executivo` str + `quadro_atribuicoes` lista
    de dicts) que `liberar_pendencias` consome. Descarta itens malformados do
    quadro (espelha o filtro do `concluir_ata_guiada`); em dúvida, preserva o atual."""
    novo = novo if isinstance(novo, dict) else {}
    resumo = novo.get("resumo_executivo")
    quadro = novo.get("quadro_atribuicoes")
    return {
        "resumo_executivo": resumo if isinstance(resumo, str) else atual["resumo_executivo"],
        "quadro_atribuicoes": (
            [a for a in quadro if isinstance(a, dict)] if isinstance(quadro, list) else atual["quadro_atribuicoes"]
        ),
    }


def chat_elaboracao_pop(
    rascunho: dict,
    messages: list[dict],
    section_context: str | None = None,
    pop_contexto: dict | None = None,
    devolucoes: list[dict] | None = None,
) -> dict:
    """Agente de elaboração de POP (PRD #76, issue #83): consultor ONA/JCI que
    transforma o relato do Elaborador nas seções de conteúdo do template
    institucional (DRF §4.2) — a Identificação (seção 1) é do sistema, nunca do
    agente. Stateless no padrão da Ata Guiada: recebe rascunho + conversa e
    devolve `{ reply, rascunho, periodicidade_sugerida }`; quem persiste o
    rascunho na Versão é o endpoint (diferença deliberada da Guiada).

    Boas práticas ONA/JCI vêm da memória do modelo — sem RAG, sem corpus
    (os Materiais de referência chegam na fatia #84). `section_context` é a
    seção apontada (⌖) para correção dirigida, mesmo padrão da Guiada.

    Em erro do provedor, devolve o rascunho intacto com a flag interna
    `_erro` — o endpoint não persiste nem transiciona (a interação não
    aconteceu). Sem chave de IA, cai no caminho MOCK sem quebrar a tela.
    """
    from app.models.pops_schemas import CHAVES_RASCUNHO_POP

    rascunho = {k: v for k, v in (rascunho or {}).items() if k in CHAVES_RASCUNHO_POP}

    provider = _llm_provider()
    if provider == "mock":
        logger.warning("Modo MOCK ativo para chat de elaboração de POP (sem chave LLM)")
        return {
            "reply": "[MOCK] Recebi seu relato. A elaboração das seções do POP exige a IA configurada.",
            "rascunho": rascunho,
            "periodicidade_sugerida": None,
        }

    client, model, extra = _get_llm()
    _log_llm_call("chat-elaboracao-pop", provider, model)
    hoje_iso = datetime.now().strftime("%Y-%m-%d")

    chat_history = "\n".join(
        f"{'Elaborador' if m['role'] == 'user' else 'Consultor'}: {m['content']}" for m in messages
    )
    user_content = render_prompt(
        "chat_elaboracao_pop_user",
        pop_contexto=_bloco_pop_contexto(pop_contexto),
        rascunho_atual=json.dumps(rascunho, indent=2, ensure_ascii=False),
        section_context=section_context or "Nenhuma seção específica selecionada",
        devolucoes=_bloco_devolucoes(devolucoes),
        chat_history=chat_history,
        hoje_iso=hoje_iso,
    )
    system_prompt = load_prompt("chat_elaboracao_pop_system")

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
            **extra,
        )
        parsed = json.loads(response.choices[0].message.content)
        if not isinstance(parsed, dict):
            raise ValueError("resposta da IA não é um objeto JSON")
    except Exception as e:
        # Mesma postura da Guiada: sem failover, erro claro, rascunho preservado.
        # A flag interna `_erro` impede o endpoint de persistir/transicionar.
        logger.error(f"Erro no chat de elaboração de POP via {provider}: {e}")
        return {
            "reply": "Desculpe, houve um erro ao processar sua mensagem. Tente novamente.",
            "rascunho": rascunho,
            "periodicidade_sugerida": None,
            "_erro": True,
        }

    rascunho_out = _normalizar_rascunho_pop(parsed.get("rascunho"), rascunho)
    sugerida = parsed.get("periodicidade_sugerida")
    if sugerida not in ("3_meses", "6_meses", "1_ano", "2_anos"):
        sugerida = None
    secoes_preenchidas = sum(1 for v in rascunho_out.values() if (v or "").strip())
    logger.info(f"[AI] Chat elaboracao POP via {provider}: {secoes_preenchidas} seção(ões) com conteúdo")
    return {"reply": parsed.get("reply", ""), "rascunho": rascunho_out, "periodicidade_sugerida": sugerida}


def _bloco_devolucoes(devolucoes: list[dict] | None) -> str:
    """Formata as Devoluções para o prompt (issue #85): os comentários de
    Revisor/Validador entram no contexto do agente — autor, etapa e texto,
    a mais recente primeiro (é a prioridade da correção)."""
    if not devolucoes:
        return "Nenhuma Devolução até agora — elaboração em fluxo normal."
    etapa_label = {"EM_REVISAO": "Revisão", "EM_VALIDACAO": "Validação"}
    linhas = []
    for d in devolucoes:
        data = (d.get("created_at") or "")[:10]
        autor = d.get("autor_nome") or d.get("autor_id") or "responsável pela etapa"
        etapa = etapa_label.get(d.get("etapa_retorno"), d.get("etapa_retorno") or "etapa")
        linhas.append(f"- Devolução da {etapa} por {autor} em {data}: {d.get('comentarios', '')}")
    return "\n".join(linhas)


def _bloco_pop_contexto(pop_contexto: dict | None) -> str:
    """Formata o cadastro do POP para o prompt — o agente sabe o que está
    elaborando (código travado, nome, setor, criticidade, base normativa)."""
    if not pop_contexto:
        return "(sem dados do cadastro)"
    linhas = [
        f"- Código: {pop_contexto.get('codigo', '—')}",
        f"- Nome: {pop_contexto.get('nome', '—')}",
        f"- Setor: {pop_contexto.get('setor_nome', '—')}",
        f"- Criticidade: {pop_contexto.get('criticidade', '—')}",
        f"- Versão: {pop_contexto.get('numero_versao', '1.0')}",
    ]
    if pop_contexto.get("base_normativa"):
        linhas.append(f"- Base normativa declarada no cadastro: {pop_contexto['base_normativa']}")
    return "\n".join(linhas)


def _normalizar_rascunho_pop(novo: dict | None, atual: dict) -> dict:
    """Aceita só as seções de conteúdo do template (strings); chave estranha ou
    valor não-string é descartado e a seção atual é preservada — o agente nunca
    corrompe o shape que a Versão persiste."""
    from app.models.pops_schemas import CHAVES_RASCUNHO_POP

    novo = novo if isinstance(novo, dict) else {}
    out = dict(atual)
    for chave in CHAVES_RASCUNHO_POP:
        valor = novo.get(chave)
        if isinstance(valor, str):
            out[chave] = valor
    return out


def _mock_ata(reuniao_id: str, tipo_reuniao: str) -> dict:
    """Retorna uma ata fictícia no formato HSM (6 seções) para testes sem chave do OpenRouter."""
    logger.info(f"[AI] MOCK: Gerando ata ficticia para {reuniao_id} (sem chave do OpenRouter ou erro)")
    return {
        "hora_inicio": "14:00",
        "hora_fim": "15:30",
        "objetivo": (
            f"[MOCK] Reunião de {tipo_reuniao} realizada para fins de teste. "
            "Discutir o planejamento do próximo trimestre e definir metas operacionais."
        ),
        "participantes": [
            {"nome": "Pedro Rezende", "cargo": "Diretor", "setor": "Diretoria", "presente": True},
            {"nome": "Ana Silva", "cargo": "Gerente de Enfermagem", "setor": "Enfermagem", "presente": True},
            {"nome": "Carlos Ferreira", "cargo": "Coordenador Financeiro", "setor": "Financeiro", "presente": True},
        ],
        "discussao": [
            {
                "titulo": "Planejamento orçamentário do próximo trimestre",
                "descricao": (
                    "Apresentação das previsões de receita e despesa, com foco em otimização de custos "
                    "sem comprometer qualidade assistencial."
                ),
                "contribuicoes": [
                    {
                        "nome": "Carlos Ferreira",
                        "funcao": "Coordenador Financeiro — Financeiro",
                        "conteudo": "Apresentou projeção com redução de 8% em custos operacionais mantendo o mesmo nível de serviço.",  # noqa: E501
                    },
                    {
                        "nome": "Ana Silva",
                        "funcao": "Gerente de Enfermagem — Enfermagem",
                        "conteudo": "Alertou que a redução não pode afetar a escala mínima de enfermagem no turno noturno.",  # noqa: E501
                    },
                ],
                "divergencias": [
                    "Ana Silva (Gerente de Enfermagem) ressalvou risco assistencial se a meta de 8% incluir corte em pessoal clínico."  # noqa: E501
                ],
                "decisao": "Aprovar meta de 8% de redução com a condição de preservar escala clínica integral.",
                "responsavel": "Carlos Ferreira",
            },
            {
                "titulo": "Renovação do contrato com fornecedor XYZ",
                "descricao": "Análise das condições da nova proposta da Empresa Fornecedora XYZ, com reajuste de 4% e novo SLA.",  # noqa: E501
                "contribuicoes": [
                    {
                        "nome": "Pedro Rezende",
                        "funcao": "Diretor — Diretoria",
                        "conteudo": "Recomendou renovar por mais 12 meses se SLA for mantido em 99% de disponibilidade.",  # noqa: E501
                    },
                ],
                "divergencias": [],
                "decisao": "Renovar por 12 meses condicionado ao SLA de 99%.",
                "responsavel": "Pedro Rezende",
            },
        ],
        "quadro_atribuicoes": [
            {
                "acao": "Elaborar relatório consolidado de indicadores do trimestre",
                "responsavel": "Pedro Rezende",
                "cargo": "Diretor",
                "objetivo_meta": "Dar visibilidade ao desempenho financeiro e assistencial",
                "prazo": (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d"),
                "entregavel": "Relatório em PDF",
                "status": "ABERTO",
            },
            {
                "acao": "Revisar escalas de enfermagem do turno noturno",
                "responsavel": "Ana Silva",
                "cargo": "Gerente de Enfermagem",
                "objetivo_meta": "Garantir cobertura assistencial mínima durante a meta de corte de custos",
                "prazo": "Fluxo contínuo",
                "entregavel": "Escala atualizada semanalmente",
                "status": "ABERTO",
            },
        ],
        "_mock": True,
    }
