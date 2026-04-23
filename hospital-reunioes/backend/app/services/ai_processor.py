import json
import logging
import re
from datetime import datetime, timedelta

from openai import OpenAI

from app.config import settings
from app.services.prompt_loader import load_prompt, render_prompt

logger = logging.getLogger(__name__)


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
    local_reuniao: str = "",
    objetivo_agendado: str = "",
) -> dict:
    """
    Envia a transcrição para o GPT-4o-mini e retorna o json_ata estruturado.
    Em caso de falha, retorna dict com campo 'error'.
    """
    if not settings.openai_api_key or settings.openai_api_key == "your-openai-key":
        logger.warning("OPENAI_API_KEY não configurada ou default — ativando modo mock")
        return _mock_ata(reuniao_id, tipo_reuniao)

    # Debug log (mascarado)
    masked = f"{settings.openai_api_key[:8]}...{settings.openai_api_key[-4:]}"
    logger.info(f"Chamando OpenAI com chave: {masked}")

    client = OpenAI(api_key=settings.openai_api_key)

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
        local_reuniao=local_reuniao or "Não informado",
        objetivo_agendado=objetivo_agendado or "Não informado",
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _build_system_prompt(hoje_iso)},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
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
        parsed.setdefault("referencias_externas", [])
        parsed.setdefault("objetivo", parsed.get("objetivo") or "")
        parsed.setdefault("local", parsed.get("local") or local_reuniao or "")

        logger.info(
            f"[AI] OpenAI processou reuniao {reuniao_id} com "
            f"{len(parsed.get('quadro_atribuicoes', []))} acoes e "
            f"{len(parsed.get('discussao', []))} topicos de discussao."
        )
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"Erro ao parsear JSON da IA para reunião {reuniao_id}: {e}")
        return {"error": f"Resposta da IA inválida: {e}"}
    except Exception as e:
        logger.error(f"Erro ao chamar OpenAI para reunião {reuniao_id}: {e}")
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
        dict com schema HSM: titulo, tipo, data, hora_inicio, hora_fim, local,
        facilitador_nome, assunto, objetivo, participantes, referencias_externas,
        discussao, quadro_atribuicoes. Em caso de erro retorna {"error": str}.
    """
    data_reuniao = (estrutura.get("metadados_brutos") or {}).get("data") or ""

    if not settings.openai_api_key or settings.openai_api_key == "your-openai-key":
        logger.warning("OPENAI_API_KEY não configurada — ATA migrada em modo mock")
        return _mock_ata_migrada(estrutura)

    masked = f"{settings.openai_api_key[:8]}...{settings.openai_api_key[-4:]}"
    logger.info(f"[AI ata-migrada] Chamando OpenAI com chave: {masked}")

    client = OpenAI(api_key=settings.openai_api_key)

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
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": load_prompt("extracao_ata_migrada")},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
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
            f"[AI ata-migrada] OpenAI processou documento="
            f"{estrutura.get('documento_id_origem')!r} "
            f"participantes={len(parsed.get('participantes', []))} "
            f"atribuicoes={len(parsed.get('quadro_atribuicoes', []))}"
        )
        return parsed
    except json.JSONDecodeError as e:
        logger.error(f"[AI ata-migrada] Erro ao parsear JSON: {e}")
        return {"error": f"Resposta da IA inválida: {e}"}
    except Exception as e:
        logger.error(f"[AI ata-migrada] Erro ao chamar OpenAI: {e}")
        return {"error": str(e)}


def _mock_ata_migrada(estrutura: dict) -> dict:
    """Fallback determinístico para ambientes sem OpenAI key (testes locais).

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
                "[MOCK sem OpenAI] A reunião foi registrada de forma consolidada. "
                "Executar a importação com OPENAI_API_KEY configurada para gerar a "
                "estruturação completa em tópicos discretos."
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
        "local": meta.get("local"),
        "facilitador_nome": (meta.get("facilitador") or "").split(" — ")[0] or None,
        "assunto": meta.get("assunto"),
        "objetivo": None,
        "participantes": participantes,
        "referencias_externas": [],
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
    if not settings.openai_api_key or settings.openai_api_key == "your-openai-key":
        logger.warning("Modo MOCK ativo para correção")
        return json_ata_atual

    client = OpenAI(api_key=settings.openai_api_key)
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
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": load_prompt("correcao_ata")},
                {"role": "user", "content": user_content},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        logger.info(f"[AI] Correcao aplicada com sucesso na ata {reuniao_id}")
        return parsed
    except Exception as e:
        logger.error(f"Erro ao corrigir ata {reuniao_id}: {e}")
        return {"error": str(e)}


def chat_correcao(
    json_ata_atual: dict,
    messages: list[dict],
    section_context: str | None = None,
) -> dict:
    """
    Processa uma mensagem do chat de correção.
    Retorna { reply: str, correction_plan: list[dict] }.
    Leve e síncrono — NÃO dispara pipeline.
    """
    if not settings.openai_api_key or settings.openai_api_key == "your-openai-key":
        logger.warning("Modo MOCK ativo para chat correção")
        return {
            "reply": "[MOCK] Entendi sua correção. Clique em 'Aplicar' quando estiver pronto.",
            "correction_plan": [],
        }

    client = OpenAI(api_key=settings.openai_api_key)
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
    )

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": load_prompt("chat_correcao_system")},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content
        parsed = json.loads(raw)

        logger.info(f"[AI] Chat correcao: {len(parsed.get('correction_plan', []))} correcoes no plano")
        return {
            "reply": parsed.get("reply", ""),
            "correction_plan": parsed.get("correction_plan", []),
        }
    except Exception as e:
        logger.error(f"Erro no chat de correção: {e}")
        return {
            "reply": "Desculpe, houve um erro ao processar sua mensagem. Tente novamente.",
            "correction_plan": [],
        }


def _mock_ata(reuniao_id: str, tipo_reuniao: str) -> dict:
    """Retorna uma ata fictícia no formato HSM (6 seções) para testes sem OpenAI key."""
    logger.info(f"[AI] MOCK: Gerando ata ficticia para {reuniao_id} (sem OpenAI Key ou erro)")
    return {
        "hora_inicio": "14:00",
        "hora_fim": "15:30",
        "local": "Sala de Reuniões 3 — 2º andar",
        "objetivo": (
            f"[MOCK] Reunião de {tipo_reuniao} realizada para fins de teste. "
            "Discutir o planejamento do próximo trimestre e definir metas operacionais."
        ),
        "participantes": [
            {"nome": "Pedro Rezende", "cargo": "Diretor", "setor": "Diretoria", "presente": True},
            {"nome": "Ana Silva", "cargo": "Gerente de Enfermagem", "setor": "Enfermagem", "presente": True},
            {"nome": "Carlos Ferreira", "cargo": "Coordenador Financeiro", "setor": "Financeiro", "presente": True},
        ],
        "referencias_externas": [
            {"nome": "Empresa Fornecedora XYZ", "vinculo_organizacao": "Fornecedor de insumos hospitalares"}
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
