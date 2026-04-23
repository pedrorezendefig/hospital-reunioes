import logging

logger = logging.getLogger(__name__)


def _generate_and_upload_pdf(
    supabase,
    id_reuniao: str,
    reuniao_dict: dict,
    json_ata: dict,
    settings,
    *,
    log_prefix: str = "[Pipeline]",
    raise_on_failure: bool = False,
) -> str | None:
    """
    Gera PDF via WeasyPrint e faz upload para o Storage.
    Retorna a URL publica do PDF em caso de sucesso, ou None em caso de falha.
    Em caso de erro, atualiza status_ata para ERRO (a menos que raise_on_failure=True,
    caso em que re-lanca a excecao para o caller tratar).
    """
    from app.services import pdf_generator, storage

    try:
        logger.info(f"{log_prefix} Gerando PDF profissional via WeasyPrint...")
        pdf_bytes = pdf_generator.gerar_pdf_ata(reuniao_dict, json_ata)

        logger.info(f"{log_prefix} Fazendo upload do PDF para bucket '{settings.supabase_storage_bucket_pdfs}'...")
        pdf_path = f"{id_reuniao}/ata_preliminar.pdf"
        url_pdf = storage.upload_file(
            supabase,
            bucket=settings.supabase_storage_bucket_pdfs,
            path=pdf_path,
            content=pdf_bytes,
            content_type="application/pdf",
        )
        if url_pdf:
            logger.info(f"{log_prefix} PDF armazenado na nuvem: {url_pdf}")
        return url_pdf
    except Exception as e_pdf:
        logger.error(f"{log_prefix} Falha na geracao do PDF para {id_reuniao}: {e_pdf}")
        if raise_on_failure:
            raise
        supabase.table("reunioes").update({"status_ata": "ERRO"}).eq("id_reuniao", id_reuniao).execute()
        return None


def run_pipeline(
    supabase,
    id_reuniao: str,
    transcricao_bytes: bytes,
    tipo_reuniao: str,
) -> None:
    """
    Orquestra o pipeline completo de uma reuniao:
    1.   Upload da transcricao para Storage
    1.5  Buscar participantes pre-vinculados para contexto da IA
    2.   Processamento com IA (com participantes_pre_cadastrados)
    2.5  Matching de participantes extraidos contra o banco
    2.7  Branch: AGUARDANDO_RESOLUCAO se houver nao reconhecidos
    3.   Gerar PDF
    4.   Upload do PDF + email de validacao
    """
    from app.config import settings
    from app.services import ai_processor, storage

    logger.info(f"[Pipeline] INICIANDO PIPELINE: Reuniao {id_reuniao}")

    try:
        # Etapa 1: Upload da transcricao
        logger.info(
            f"[Pipeline][Step 1] Upload da transcricao para bucket '{settings.supabase_storage_bucket_transcricoes}'"
        )
        storage_path = f"{id_reuniao}/transcricao.txt"
        url_transcricao = storage.upload_file(
            supabase,
            bucket=settings.supabase_storage_bucket_transcricoes,
            path=storage_path,
            content=transcricao_bytes,
            content_type="text/plain",
        )
        if not url_transcricao:
            logger.error(f"[Pipeline][Step 1] Upload da transcricao falhou para {id_reuniao}")
            supabase.table("reunioes").update({"status_ata": "ERRO"}).eq("id_reuniao", id_reuniao).execute()
            raise RuntimeError("Upload da transcricao falhou -- pipeline abortado")

        supabase.table("reunioes").update({"url_transcricao": url_transcricao}).eq("id_reuniao", id_reuniao).execute()

        # Etapa 1.5: Buscar participantes pre-vinculados para passar ao contexto da IA
        pre_linked_result = (
            supabase.table("reuniao_participantes")
            .select("participante_id, participantes(nome_completo, cargo, setor)")
            .eq("id_reuniao", id_reuniao)
            .execute()
        )

        participantes_texto = ""
        if pre_linked_result.data:
            linhas = []
            for row in pre_linked_result.data:
                p = row.get("participantes") or {}
                nome = p.get("nome_completo", "")
                cargo = p.get("cargo", "")
                setor = p.get("setor", "")
                if nome:
                    linha = f"- {nome} ({cargo})"
                    if setor:
                        linha += f" -- {setor}"
                    linhas.append(linha)
            participantes_texto = "\n".join(linhas)

        # Etapa 1.6: Buscar diretorio completo de ativos para a IA resolver primeiros-nomes.
        # Reutilizado em 2.5 pelo participant_matcher para evitar refetch.
        ativos_result = (
            supabase.table("participantes").select("id, nome_completo, cargo, setor, area").eq("ativo", True).execute()
        )
        ativos_rows = ativos_result.data or []
        dir_ativos_texto = ""
        if ativos_rows:
            linhas_dir = []
            for p in ativos_rows:
                nome = (p.get("nome_completo") or "").strip()
                if not nome:
                    continue
                cargo = (p.get("cargo") or "").strip()
                setor = (p.get("setor") or "").strip()
                area = (p.get("area") or "").strip()
                partes = [f"- {nome}"]
                if cargo:
                    partes.append(f"({cargo})")
                contexto = " / ".join(filter(None, [setor, area]))
                if contexto:
                    partes.append(f"-- {contexto}")
                linhas_dir.append(" ".join(partes))
            dir_ativos_texto = "\n".join(linhas_dir)

        # Etapa 1.7: Buscar local e objetivo do agendamento para contextualizar a IA
        reuniao_ctx = supabase.table("reunioes").select("local, objetivo").eq("id_reuniao", id_reuniao).execute()
        local_reuniao = ""
        objetivo_agendado = ""
        if reuniao_ctx.data:
            local_reuniao = (reuniao_ctx.data[0].get("local") or "").strip()
            objetivo_agendado = (reuniao_ctx.data[0].get("objetivo") or "").strip()

        # Etapa 2: Processamento com IA
        logger.info("[Pipeline][Step 2] Enviando transcricao para a OpenAI (Modelo: gpt-4o-mini)")
        transcricao_txt = transcricao_bytes.decode("utf-8", errors="replace")
        json_ata = ai_processor.process_transcricao(
            transcricao_txt,
            id_reuniao,
            tipo_reuniao,
            participantes_pre_cadastrados=participantes_texto,
            participantes_ativos_dir=dir_ativos_texto,
            local_reuniao=local_reuniao,
            objetivo_agendado=objetivo_agendado,
        )

        if "error" in json_ata:
            logger.error(f"[Pipeline][Step 2] IA retornou erro para {id_reuniao}: {json_ata['error']}")
            supabase.table("reunioes").update(
                {
                    "status_ata": "ERRO",
                    "json_ata": json_ata,
                }
            ).eq("id_reuniao", id_reuniao).execute()
            return

        # Etapa 2.5: Matching de participantes extraidos pela IA
        from app.services.participant_matcher import match_participants

        participantes_extraidos = json_ata.get("participantes", [])
        matched_ids, nao_reconhecidos = [], []
        if participantes_extraidos:
            logger.info(f"[Pipeline][Step 2.5] Fazendo matching de {len(participantes_extraidos)} participantes...")
            matched_ids, nao_reconhecidos = match_participants(
                supabase,
                id_reuniao,
                participantes_extraidos,
                ativos_rows=ativos_rows,
            )

        # Etapa 2.7: Branch -- pausar se houver nao reconhecidos
        if nao_reconhecidos:
            logger.info(
                f"[Pipeline][Step 2.7] {len(nao_reconhecidos)} participante(s) nao reconhecido(s) -- aguardando resolucao"  # noqa: E501
            )

            update_pause: dict = {
                "json_ata": json_ata,
                "participantes_nao_reconhecidos": nao_reconhecidos,
                "status_ata": "AGUARDANDO_RESOLUCAO",
                "total_acoes": len(json_ata.get("quadro_atribuicoes", [])),
            }
            if json_ata.get("hora_inicio") and json_ata["hora_inicio"] != "null":
                update_pause["hora_inicio"] = json_ata["hora_inicio"]
            if json_ata.get("hora_fim") and json_ata["hora_fim"] != "null":
                update_pause["hora_fim"] = json_ata["hora_fim"]

            supabase.table("reunioes").update(update_pause).eq("id_reuniao", id_reuniao).execute()

            logger.info(f"[Pipeline] Pipeline pausado em AGUARDANDO_RESOLUCAO para {id_reuniao}")
            return  # Pipeline pausa aqui

        # Etapa 3: Atualizar banco com resultado
        update_data: dict = {
            "json_ata": json_ata,
            "status_ata": "AGUARDANDO_VALIDACAO",
        }

        # Extrai hora_inicio e hora_fim se disponiveis
        if json_ata.get("hora_inicio") and json_ata["hora_inicio"] != "null":
            update_data["hora_inicio"] = json_ata["hora_inicio"]
        if json_ata.get("hora_fim") and json_ata["hora_fim"] != "null":
            update_data["hora_fim"] = json_ata["hora_fim"]

        # Recuperar informacoes basicas da reuniao para o PDF
        reuniao_record = (
            supabase.table("reunioes")
            .select("id_reuniao, data, tipo, local, objetivo, hora_inicio, hora_fim")
            .eq("id_reuniao", id_reuniao)
            .execute()
        )
        reuniao_dict = reuniao_record.data[0] if reuniao_record.data else {"id_reuniao": id_reuniao}

        # Etapa 3+4: Gerar PDF e fazer upload
        url_pdf = _generate_and_upload_pdf(
            supabase,
            id_reuniao,
            reuniao_dict,
            json_ata,
            settings,
            log_prefix="[Pipeline][Step 3]",
        )
        if url_pdf is None:
            return  # Aborta o pipeline -- nao envia email sem PDF
        update_data["url_pdf_preliminar"] = url_pdf

        # Conta acoes extraidas
        acoes = json_ata.get("quadro_atribuicoes", [])
        update_data["total_acoes"] = len(acoes)

        supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()

        logger.info(f"[Pipeline] PIPELINE CONCLUIDO COM SUCESSO: {id_reuniao}")

    except Exception as e:
        logger.error(f"[Pipeline] ERRO CRITICO NO PIPELINE ({id_reuniao}): {str(e)}", exc_info=True)
        try:
            supabase.table("reunioes").update(
                {
                    "status_ata": "ERRO",
                    "json_ata": {"error": str(e)},
                }
            ).eq("id_reuniao", id_reuniao).execute()
        except Exception:
            pass


def resume_pipeline_after_resolution(supabase, id_reuniao: str) -> None:
    """
    Retoma o pipeline apos o facilitador resolver participantes nao reconhecidos.
    Executa apenas as etapas de geracao de PDF e envio de email de validacao.
    Chamado como BackgroundTask apos POST /reunioes/{id}/resolver-participantes.
    """
    from app.config import settings

    logger.info(f"[ResumePipeline] RETOMANDO PIPELINE: Reuniao {id_reuniao}")

    try:
        # Buscar json_ata salvo + dados da reuniao
        reuniao_fetch = (
            supabase.table("reunioes")
            .select("id_reuniao, data, tipo, local, objetivo, hora_inicio, hora_fim, json_ata, facilitador_id")
            .eq("id_reuniao", id_reuniao)
            .execute()
        )

        if not reuniao_fetch.data:
            logger.error(f"[ResumePipeline] Reuniao {id_reuniao} nao encontrada")
            return

        reuniao_dict = reuniao_fetch.data[0]
        json_ata = reuniao_dict.get("json_ata", {})

        if not json_ata:
            logger.error(f"[ResumePipeline] json_ata nao encontrado para {id_reuniao}")
            supabase.table("reunioes").update({"status_ata": "ERRO"}).eq("id_reuniao", id_reuniao).execute()
            return

        # Gerar PDF e fazer upload
        url_pdf = _generate_and_upload_pdf(
            supabase,
            id_reuniao,
            reuniao_dict,
            json_ata,
            settings,
            log_prefix="[ResumePipeline]",
        )
        if url_pdf is None:
            return

        # Atualizar status para AGUARDANDO_VALIDACAO
        supabase.table("reunioes").update(
            {
                "status_ata": "AGUARDANDO_VALIDACAO",
                "url_pdf_preliminar": url_pdf,
            }
        ).eq("id_reuniao", id_reuniao).execute()

        logger.info(f"[ResumePipeline] PIPELINE RETOMADO COM SUCESSO: {id_reuniao}")

    except Exception as e:
        logger.error(f"[ResumePipeline] Erro critico para {id_reuniao}: {e}", exc_info=True)
        supabase.table("reunioes").update({"status_ata": "ERRO"}).eq("id_reuniao", id_reuniao).execute()


def run_correction_pipeline(
    supabase,
    id_reuniao: str,
    instrucao_correcao: str,
) -> None:
    """
    Pipeline de correcao de ata.
    """
    from app.config import settings
    from app.services import ai_processor, storage

    logger.info(f"[CorrectionPipeline] INICIANDO CORRECAO: Reuniao {id_reuniao}")

    try:
        # 1. Recuperar transcricao e ata atual
        reuniao_fetch = supabase.table("reunioes").select("json_ata, tipo").eq("id_reuniao", id_reuniao).execute()
        if not reuniao_fetch.data:
            return

        reuniao_data = reuniao_fetch.data[0]
        json_ata_atual = reuniao_data.get("json_ata")
        tipo_reuniao = reuniao_data.get("tipo", "Gerencial")

        transcricao_bytes = storage.download_file(
            supabase, settings.supabase_storage_bucket_transcricoes, f"{id_reuniao}/transcricao.txt"
        )
        transcricao_txt = transcricao_bytes.decode("utf-8", errors="replace") if transcricao_bytes else ""

        # 2. Chamar IA para correcao
        logger.info(f"[CorrectionPipeline] Aplicando correcao via IA com instrucao: '{instrucao_correcao[:50]}...'")
        json_ata_novo = ai_processor.process_correcao(
            transcricao_txt, json_ata_atual, instrucao_correcao, id_reuniao, tipo_reuniao
        )

        if "error" in json_ata_novo:
            logger.error(f"[CorrectionPipeline] Erro na correcao para {id_reuniao}: {json_ata_novo['error']}")
            supabase.table("reunioes").update({"status_ata": "AGUARDANDO_VALIDACAO"}).eq(
                "id_reuniao", id_reuniao
            ).execute()
            return

        # 3. Matching de participantes (pode ter mudado nomes ou quem estava presente)
        from app.services.participant_matcher import match_participants

        participantes_extraidos = json_ata_novo.get("participantes", [])
        if participantes_extraidos:
            matched_ids, nao_reconhecidos = match_participants(supabase, id_reuniao, participantes_extraidos)
            if nao_reconhecidos:
                # Log warning mas nao bloqueia o fluxo de correcao
                logger.warning(
                    f"[CorrectionPipeline] {len(nao_reconhecidos)} participantes nao reconhecidos na correcao: "
                    f"{[p['nome'] for p in nao_reconhecidos]}"
                )

        # 4. Atualizar banco e regerar PDF
        update_data = {
            "json_ata": json_ata_novo,
            "status_ata": "AGUARDANDO_VALIDACAO",
            "total_acoes": len(json_ata_novo.get("quadro_atribuicoes", [])),
        }

        # Regerar PDF (raise_on_failure=True: excecao propaga ao handler externo
        # que mantem status AGUARDANDO_VALIDACAO em vez de ERRO)
        reuniao_record = (
            supabase.table("reunioes")
            .select("id_reuniao, data, tipo, local, objetivo, hora_inicio, hora_fim")
            .eq("id_reuniao", id_reuniao)
            .execute()
        )
        reuniao_dict = reuniao_record.data[0] if reuniao_record.data else {"id_reuniao": id_reuniao}

        url_pdf = _generate_and_upload_pdf(
            supabase,
            id_reuniao,
            reuniao_dict,
            json_ata_novo,
            settings,
            log_prefix="[CorrectionPipeline]",
            raise_on_failure=True,
        )
        if url_pdf:
            update_data["url_pdf_preliminar"] = url_pdf

        supabase.table("reunioes").update(update_data).eq("id_reuniao", id_reuniao).execute()
        logger.info(f"[CorrectionPipeline] CORRECAO CONCLUIDA COM SUCESSO: {id_reuniao}")

    except Exception as e:
        logger.error(f"[CorrectionPipeline] Erro critico no pipeline de correcao ({id_reuniao}): {e}", exc_info=True)
        supabase.table("reunioes").update({"status_ata": "AGUARDANDO_VALIDACAO"}).eq("id_reuniao", id_reuniao).execute()
