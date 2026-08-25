# ENTIDADES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-08-25T16:59-0300 -->

Modelo de dados do Hospital Reuniões. Tabelas no Postgres (via Supabase).

## participantes

> Origem: `001_create_participantes.sql` (alterada em: 014_add_externo_co_responsavel.sql, 017_add_super_admin.sql, 028_add_taxonomy_fks.sql, 036_add_access_profile.sql, 045_pops_fundacao_acesso.sql, 064_ouvidoria_manifestacao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `VARCHAR(10)` | PK | `generate_participant_id()` | — |
| `nome_completo` | `TEXT` | NOT NULL | — | — |
| `cargo` | `TEXT` | NOT NULL | — | — |
| `email` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `area` | `TEXT` | — | — | — |
| `setor` | `TEXT` | — | — | — |
| `role` | `user_role` | NOT NULL | `'coordenador'` | — |
| `ativo` | `BOOLEAN` | — | `TRUE` | — |
| `auth_user_id` | `UUID` | — | — | — |
| `data_cadastro` | `DATE` | — | `now()` | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `is_externo` | `BOOLEAN` | NOT NULL | `false` | — |
| `is_super_admin` | `BOOLEAN` | NOT NULL | `false` | — |
| `setor_id` | `UUID` | — | — | `setores.id` |
| `access_profile` | `TEXT` | — | — | — |
| `perfil_pop` | `TEXT` | — | — | — |
| `perfil_ouvidoria` | `TEXT` | — | — | — |

**Indexes:**
- `idx_participantes_email` em `(email)` (de `001_create_participantes.sql`)
- `idx_participantes_setor` em `(setor)` (de `001_create_participantes.sql`)
- `idx_participantes_ativo` em `(ativo)` (de `001_create_participantes.sql`)
- `idx_participantes_auth` em `(auth_user_id)` (de `001_create_participantes.sql`)
- `idx_participantes_super_admin` em `(is_super_admin)` (de `017_add_super_admin.sql`)
- `idx_participantes_access_profile` em `(access_profile)` (de `036_add_access_profile.sql`)
- `idx_participantes_setor_id` em `(setor_id)` (de `038_fk_indexes.sql`)
- `idx_participantes_cargo_id` em `(cargo_id)` (de `038_fk_indexes.sql`)
- `idx_participantes_perfil_pop` em `(perfil_pop)` (de `045_pops_fundacao_acesso.sql`)
- `idx_participantes_perfil_ouvidoria` em `(perfil_ouvidoria)` (de `064_ouvidoria_manifestacao.sql`)

## reunioes

> Origem: `002_create_reunioes.sql` (alterada em: 016_importacao_ata_legada.sql, 020_historico_importacao.sql, 028_add_taxonomy_fks.sql, 030_add_soft_delete.sql, 032_drop_local_reuniao.sql, 035_add_lembrete_24h_reunioes.sql, 036_add_access_profile.sql, 039_add_envelope_id_clicksign.sql, 044_add_metodo_geracao_reunioes.sql, 056_add_falha_envio_assinatura.sql, 058_finalizacao_envelope_contagem.sql, 059_modo_interno_reuniao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id_reuniao` | `VARCHAR(20)` | PK | — | — |
| `data` | `DATE` | NOT NULL | — | — |
| `hora_inicio` | `TIME` | — | — | — |
| `hora_fim` | `TIME` | — | — | — |
| `titulo` | `TEXT` | — | — | — |
| `tipo` | `TEXT` | — | — | — |
| `facilitador_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `setor` | `TEXT` | — | — | — |
| `objetivo` | `TEXT` | — | — | — |
| `status_ata` | `TEXT` | — | `'PROCESSANDO'` | — |
| `total_acoes` | `INTEGER` | — | `0` | — |
| `acoes_concluidas` | `INTEGER` | — | `0` | — |
| `data_assinatura` | `DATE` | — | — | — |
| `url_audio` | `TEXT` | — | — | — |
| `url_transcricao` | `TEXT` | — | — | — |
| `url_pdf_preliminar` | `TEXT` | — | — | — |
| `url_pdf_assinado` | `TEXT` | — | — | — |
| `envelope_key_clicksign` | `TEXT` | — | — | — |
| `json_ata` | `JSONB` | — | — | — |
| `fireflies_meeting_id` | `TEXT` | — | — | — |
| `fonte` | `TEXT` | — | `'MOCK'` | — |
| `ciclo_correcao` | `INTEGER` | — | `0` | — |
| `participantes_nao_reconhecidos` | `JSONB` | — | `'[]'::jsonb` | — |
| `id_grupo_recorrencia` | `TEXT` | — | — | — |
| `nome_grupo_recorrencia` | `TEXT` | — | — | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `documento_id_origem` | `TEXT` | — | — | — |
| `nome_arquivo_original` | `TEXT` | — | — | `participantes.id` |
| `tipo_id` | `UUID` | — | — | `tipos_reuniao.id` |
| `deleted_at` | `TIMESTAMPTZ` | — | — | — |
| `lembrete_24h_enviado_at` | `TIMESTAMPTZ` | — | — | — |
| `criada_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `envelope_id_clicksign` | `TEXT` | — | — | — |
| `falha_envio_assinatura` | `JSONB` | — | — | — |
| `signatarios_total` | `INTEGER` | — | — | — |
| `modo_interno_desde` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `idx_reunioes_status` em `(status_ata)` (de `002_create_reunioes.sql`)
- `idx_reunioes_data` em `(data DESC)` (de `002_create_reunioes.sql`)
- `idx_reunioes_setor` em `(setor)` (de `002_create_reunioes.sql`)
- `idx_reunioes_fireflies` em `(fireflies_meeting_id)` (de `002_create_reunioes.sql`)
- `idx_reunioes_programada` em `(data, status_ata)` (de `002_create_reunioes.sql`)
- `idx_reunioes_documento_id_origem` em `(documento_id_origem)` (de `016_importacao_ata_legada.sql`)
- `idx_reunioes_arquivo_hash` em `(arquivo_hash)` (de `016_importacao_ata_legada.sql`)
- `idx_reunioes_importado_por` em `(importado_por_id)` (de `020_historico_importacao.sql`)
- `idx_reunioes_live` em `(data DESC)` (de `030_add_soft_delete.sql`)
- `idx_reunioes_lembrete_pendente` em `(data, hora_inicio)` (de `035_add_lembrete_24h_reunioes.sql`)
- `idx_reunioes_criada_por` em `(criada_por)` (de `036_add_access_profile.sql`)
- `idx_reunioes_facilitador` em `(facilitador_id)` (de `038_fk_indexes.sql`)
- `idx_reunioes_tipo_id` em `(tipo_id)` (de `038_fk_indexes.sql`)

## reuniao_participantes

> Origem: `002_create_reunioes.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `id_reuniao` | `VARCHAR(20)` | — | — | `reunioes.id_reuniao` |
| `participante_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `sequence_assinatura` | `INTEGER` | — | `2` | — |

**Indexes:**
- `idx_reuniao_part_reuniao` em `(id_reuniao)` (de `002_create_reunioes.sql`)
- `idx_reuniao_part_participante` em `(participante_id)` (de `002_create_reunioes.sql`)

## pendencias

> Origem: `003_create_pendencias.sql` (alterada em: 014_add_externo_co_responsavel.sql, 030_add_soft_delete.sql, 042_add_id_nota_pendencias.sql, 052_descontinuar_notas.sql, 057_registro_aceites_incremental.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id_acao` | `VARCHAR(10)` | PK | — | — |
| `id_reuniao` | `VARCHAR(20)` | — | — | `reunioes.id_reuniao` |
| `descricao_acao` | `TEXT` | NOT NULL | — | — |
| `responsavel_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `responsavel_nome` | `TEXT` | — | — | — |
| `cargo` | `TEXT` | — | — | — |
| `prazo` | `DATE` | — | — | — |
| `meta_entregavel` | `TEXT` | — | — | — |
| `status` | `TEXT` | — | `'PENDENTE'` | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `co_responsavel_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `co_responsavel_nome` | `TEXT` | — | — | — |
| `deleted_at` | `TIMESTAMPTZ` | — | — | — |
| `quadro_pos` | `INTEGER` | — | — | — |

**Indexes:**
- `idx_pendencias_reuniao` em `(id_reuniao)` (de `003_create_pendencias.sql`)
- `idx_pendencias_responsavel` em `(responsavel_id)` (de `003_create_pendencias.sql`)
- `idx_pendencias_status` em `(status)` (de `003_create_pendencias.sql`)
- `idx_pendencias_prazo` em `(prazo)` (de `003_create_pendencias.sql`)
- `idx_pendencias_co_responsavel` em `(co_responsavel_id)` (de `014_add_externo_co_responsavel.sql`)
- `idx_pendencias_live` em `(prazo)` (de `030_add_soft_delete.sql`)
- `idx_pendencias_nota` em `(id_nota)` (de `042_add_id_nota_pendencias.sql`)
- `ux_pendencias_reuniao_quadro_pos` em `(id_reuniao, quadro_pos)` (de `057_registro_aceites_incremental.sql`)

## agendamentos_email

> Origem: `003_create_pendencias.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `id_acao` | `VARCHAR(10)` | — | — | `pendencias.id_acao` |
| `tipo` | `TEXT` | — | — | — |
| `data_disparo` | `DATE` | NOT NULL | — | — |
| `enviado` | `BOOLEAN` | — | `FALSE` | — |
| `enviado_em` | `TIMESTAMPTZ` | — | — | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |

**Indexes:**
- `idx_agendamentos_disparo` em `(data_disparo, enviado)` (de `003_create_pendencias.sql`)
- `idx_agendamentos_email_id_acao` em `(id_acao)` (de `038_fk_indexes.sql`)

## tokens_validacao

> Origem: `004_create_tokens_validacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `token` | `UUID` | PK | `gen_random_uuid()` | — |
| `id_reuniao` | `VARCHAR(20)` | — | — | `reunioes.id_reuniao` |
| `tipo` | `TEXT` | — | — | — |
| `usado` | `BOOLEAN` | — | `FALSE` | — |
| `ciclo_correcao` | `INTEGER` | — | `0` | — |
| `expires_at` | `TIMESTAMPTZ` | NOT NULL | — | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |

**Indexes:**
- `idx_tokens_reuniao` em `(id_reuniao)` (de `004_create_tokens_validacao.sql`)
- `idx_tokens_expires` em `(expires_at)` (de `004_create_tokens_validacao.sql`)

## comentarios_pendencias

> Origem: `007_create_comentarios_pendencias.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `id_acao` | `VARCHAR(10)` | NOT NULL | — | `pendencias.id_acao` |
| `autor_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `autor_nome` | `TEXT` | NOT NULL | — | — |
| `conteudo` | `TEXT` | NOT NULL | — | — |
| `mencoes` | `VARCHAR(10)[]` | — | `'{}'` | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | — | `now()` | — |

**Indexes:**
- `idx_comentarios_id_acao` em `(id_acao)` (de `007_create_comentarios_pendencias.sql`)
- `idx_comentarios_autor` em `(autor_id)` (de `007_create_comentarios_pendencias.sql`)
- `idx_comentarios_created` em `(created_at DESC)` (de `007_create_comentarios_pendencias.sql`)

## notificacoes

> Origem: `008_create_notificacoes.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `destinatario_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `tipo` | `TEXT` | NOT NULL | — | — |
| `titulo` | `TEXT` | NOT NULL | — | — |
| `mensagem` | `TEXT` | — | — | — |
| `referencia_id` | `VARCHAR(10)` | — | — | — |
| `lida` | `BOOLEAN` | — | `FALSE` | — |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |

**Indexes:**
- `idx_notificacoes_destinatario` em `(destinatario_id, lida)` (de `008_create_notificacoes.sql`)
- `idx_notificacoes_created` em `(created_at DESC)` (de `008_create_notificacoes.sql`)
- `idx_notificacoes_referencia` em `(referencia_id)` (de `008_create_notificacoes.sql`)

## user_preferences

> Origem: `012_create_user_preferences.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `participante_id` | `VARCHAR(10)` | PK | — | `participantes.id` |
| `notificacoes` | `JSONB` | NOT NULL | `'{
        "mencao": true` | — |
| `emails` | `JSONB` | NOT NULL | `'{
        "validacao_ata": true` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## audit_log

> Origem: `018_create_audit_log.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `timestamp` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |
| `actor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `actor_email` | `TEXT` | NOT NULL | — | — |
| `action` | `TEXT` | NOT NULL | — | — |
| `target_type` | `TEXT` | NOT NULL | — | — |
| `target_id` | `TEXT` | NOT NULL | — | — |
| `metadata` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |
| `ip_address` | `INET` | — | — | — |
| `reason` | `TEXT` | — | — | — |

**Indexes:**
- `idx_audit_log_timestamp` em `(timestamp DESC)` (de `018_create_audit_log.sql`)
- `idx_audit_log_actor` em `(actor_id)` (de `018_create_audit_log.sql`)
- `idx_audit_log_target` em `(target_type, target_id)` (de `018_create_audit_log.sql`)
- `idx_audit_log_action` em `(action)` (de `018_create_audit_log.sql`)

## bulk_jobs

> Origem: `019_create_bulk_jobs.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |
| `actor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `actor_email` | `TEXT` | NOT NULL | — | — |
| `job_type` | `TEXT` | NOT NULL | — | — |
| `reenviar_email` | `status` | NOT NULL | — | — |
| `failed` | `target_ids` | NOT NULL | — | — |
| `sucessos` | `INTEGER` | NOT NULL | `0` | — |
| `falhas` | `JSONB` | NOT NULL | `'[]'::jsonb` | — |
| `started_at` | `TIMESTAMPTZ` | — | — | — |
| `finished_at` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `idx_bulk_jobs_actor` em `(actor_id)` (de `019_create_bulk_jobs.sql`)
- `idx_bulk_jobs_status` em `(status)` (de `019_create_bulk_jobs.sql`)
- `idx_bulk_jobs_created_at` em `(created_at DESC)` (de `019_create_bulk_jobs.sql`)

## cargos

> Origem: `027_create_taxonomy_tables.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `uuid_generate_v4()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |

**Indexes:**
- `cargos_nome_lower_idx` em `((lower(nome)` (de `027_create_taxonomy_tables.sql`)

## tipos_reuniao

> Origem: `027_create_taxonomy_tables.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `uuid_generate_v4()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `NOW()` | — |

**Indexes:**
- `tipos_reuniao_nome_lower_idx` em `((lower(nome)` (de `027_create_taxonomy_tables.sql`)

## pops_setores

> Origem: `045_pops_fundacao_acesso.sql` (alterada em: 053_pops_natureza_setor.sql, 055_pops_natureza_drop.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `sigla` | `TEXT` | NOT NULL | — | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `pops_setores_nome_lower_idx` em `((lower(nome)` (de `045_pops_fundacao_acesso.sql`)
- `pops_setores_sigla_lower_idx` em `((lower(sigla)` (de `045_pops_fundacao_acesso.sql`)

## pops_setores_participantes

> Origem: `045_pops_fundacao_acesso.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `setor_id` | `UUID` | NOT NULL | — | `pops_setores.id` |
| `participante_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_pops_setores_participantes_participante` em `(participante_id)` (de `045_pops_fundacao_acesso.sql`)

## pops

> Origem: `046_pops_criar_pop.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `setor_id` | `UUID` | NOT NULL | — | `pops_setores.id` |
| `numero` | `INT` | NOT NULL | — | — |
| `codigo` | `TEXT` | NOT NULL | — | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `criticidade` | `TEXT` | NOT NULL | — | — |
| `base_normativa` | `TEXT` | — | — | — |
| `periodicidade_revisao` | `TEXT` | NOT NULL | — | — |
| `prazo_elaboracao_dias` | `INT` | NOT NULL | `15` | — |
| `prazo_revisao_dias` | `INT` | NOT NULL | `30` | — |
| `elaborador_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `revisor_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `validador_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `criado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_pops_setor` em `(setor_id)` (de `046_pops_criar_pop.sql`)
- `idx_pops_elaborador` em `(elaborador_id)` (de `046_pops_criar_pop.sql`)

## pops_versoes

> Origem: `046_pops_criar_pop.sql` (alterada em: 047_pops_elaboracao.sql, 050_pops_clicksign_publicacao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `pop_id` | `UUID` | NOT NULL | — | `pops.id` |
| `numero_versao` | `TEXT` | NOT NULL | `'1.0'` | — |
| `estado` | `TEXT` | NOT NULL | `'A_ELABORAR'` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `rascunho` | `JSONB` | — | — | — |
| `envelope_id_clicksign` | `TEXT` | — | — | — |

**Indexes:**
- `idx_pops_versoes_pop` em `(pop_id)` (de `046_pops_criar_pop.sql`)
- `idx_pops_versoes_estado` em `(estado)` (de `046_pops_criar_pop.sql`)
- `idx_pops_versoes_envelope_key` em `(envelope_key_clicksign)` (de `050_pops_clicksign_publicacao.sql`)

## pops_devolucoes

> Origem: `048_pops_revisao_validacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `versao_id` | `UUID` | NOT NULL | — | `pops_versoes.id` |
| `autor_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `etapa_retorno` | `TEXT` | NOT NULL | — | — |
| `comentarios` | `TEXT` | NOT NULL | — | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_pops_devolucoes_versao` em `(versao_id)` (de `048_pops_revisao_validacao.sql`)

## pops_materiais_referencia

> Origem: `049_pops_materiais_referencia.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `versao_id` | `UUID` | NOT NULL | — | `pops_versoes.id` |
| `filename` | `TEXT` | NOT NULL | — | — |
| `extensao` | `TEXT` | NOT NULL | — | — |
| `tamanho_bytes` | `INTEGER` | NOT NULL | — | — |
| `storage_path` | `TEXT` | — | — | — |
| `texto` | `TEXT` | NOT NULL | — | — |
| `criado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `created_at` | `TIMESTAMPTZ` | — | `now()` | — |

**Indexes:**
- `idx_pops_materiais_versao` em `(versao_id)` (de `049_pops_materiais_referencia.sql`)

## reuniao_aceites

> Origem: `057_registro_aceites_incremental.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `participante_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `signer_key` | `TEXT` | — | — | — |
| `email` | `TEXT` | — | — | — |
| `origem` | `TEXT` | NOT NULL | — | — |
| `aceito_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `ux_reuniao_aceites_signer_key` em `(id_reuniao, signer_key)` (de `057_registro_aceites_incremental.sql`)
- `ux_reuniao_aceites_email` em `(id_reuniao, email)` (de `057_registro_aceites_incremental.sql`)
- `ux_reuniao_aceites_participante` em `(id_reuniao, participante_id)` (de `057_registro_aceites_incremental.sql`)
- `idx_reuniao_aceites_reuniao` em `(id_reuniao)` (de `057_registro_aceites_incremental.sql`)
- `idx_reuniao_aceites_participante` em `(participante_id)` (de `057_registro_aceites_incremental.sql`)

## reuniao_aceite_tokens

> Origem: `060_aceite_interno_tokens.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `participante_id` | `VARCHAR(10)` | NOT NULL | — | `participantes.id` |
| `token_hash` | `TEXT` | NOT NULL | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `usado_em` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `ux_reuniao_aceite_tokens_hash` em `(token_hash)` (de `060_aceite_interno_tokens.sql`)
- `ux_reuniao_aceite_tokens_participante` em `(id_reuniao, participante_id)` (de `060_aceite_interno_tokens.sql`)
- `idx_reuniao_aceite_tokens_reuniao` em `(id_reuniao)` (de `060_aceite_interno_tokens.sql`)

## consultas_particulares

> Origem: `061_consultas_particulares_ana.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `especialidade` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `valor_rs` | `NUMERIC(10, 2)` | NOT NULL | — | — |
| `descricao_servico` | `TEXT` | NOT NULL | — | — |
| `diferencial_1` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_2` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_3` | `TEXT` | NOT NULL | `''` | — |
| `alta_demanda` | `BOOLEAN` | NOT NULL | `FALSE` | — |
| `observacoes_ana` | `TEXT` | NOT NULL | `''` | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `ultima_atualizacao` | `DATE` | NOT NULL | `CURRENT_DATE` | — |

## exames

> Origem: `062_exames_cirurgias_convenios_ana.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `nome_exame` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `tipo_exame` | `TEXT` | NOT NULL | — | — |
| `convenio_aceito` | `BOOLEAN` | NOT NULL | `FALSE` | — |
| `valor_particular_rs` | `NUMERIC(10, 2)` | NOT NULL | — | — |
| `requer_pedido_medico` | `BOOLEAN` | NOT NULL | `FALSE` | — |
| `preparo_necessario` | `BOOLEAN` | NOT NULL | `FALSE` | — |
| `instrucoes_preparo_completas` | `TEXT` | NOT NULL | `''` | — |
| `tempo_resultado` | `TEXT` | NOT NULL | `''` | — |
| `local_realizacao` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_1` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_2` | `TEXT` | NOT NULL | `''` | — |
| `observacoes_ana` | `TEXT` | NOT NULL | `''` | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `ultima_atualizacao` | `DATE` | NOT NULL | `CURRENT_DATE` | — |

## cirurgias_estimativas

> Origem: `062_exames_cirurgias_convenios_ana.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `procedimento` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `descricao_procedimento` | `TEXT` | NOT NULL | — | — |
| `honorarios_equipe_rs` | `NUMERIC(10, 2)` | NOT NULL | — | — |
| `valor_internacao_rs` | `NUMERIC(10, 2)` | NOT NULL | — | — |
| `estimativa_total_rs` | `NUMERIC(10, 2)` | NOT NULL | — | — |
| `o_que_inclui_honorarios` | `TEXT` | NOT NULL | `''` | — |
| `o_que_inclui_internacao` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_1` | `TEXT` | NOT NULL | `''` | — |
| `diferencial_2` | `TEXT` | NOT NULL | `''` | — |
| `caveat_obrigatorio_ana` | `TEXT` | NOT NULL | — | — |
| `observacoes_ana` | `TEXT` | NOT NULL | `''` | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `ultima_atualizacao` | `DATE` | NOT NULL | `CURRENT_DATE` | — |

## convenios_especialidade

> Origem: `062_exames_cirurgias_convenios_ana.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `convenio` | `TEXT` | NOT NULL | — | — |
| `especialidade` | `TEXT` | NOT NULL | — | — |
| `cobre` | `BOOLEAN` | NOT NULL | — | — |
| `observacao` | `TEXT` | NOT NULL | `''` | — |
| `ultima_atualizacao` | `DATE` | NOT NULL | `CURRENT_DATE` | — |

## ouvidoria_movimentos

> Origem: `064_ouvidoria_manifestacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `ocorrido_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `estado_anterior` | `TEXT` | — | — | — |
| `estado_novo` | `TEXT` | NOT NULL | — | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `autor_nome` | `TEXT` | NOT NULL | — | — |
| `observacao` | `TEXT` | — | — | — |

**Indexes:**
- `idx_ouvidoria_movimentos_manifestacao` em `(manifestacao_id, ocorrido_em)` (de `064_ouvidoria_manifestacao.sql`)

## ouvidoria_acessos

> Origem: `064_ouvidoria_manifestacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `ocorrido_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `ator_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `ator_nome` | `TEXT` | NOT NULL | — | — |
| `acao` | `TEXT` | NOT NULL | — | — |

**Indexes:**
- `idx_ouvidoria_acessos_manifestacao` em `(manifestacao_id, ocorrido_em DESC)` (de `064_ouvidoria_manifestacao.sql`)

## ouvidoria_prazos

> Origem: `065_ouvidoria_prazos_calendario.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `gravidade` | `TEXT` | NOT NULL | — | — |
| `marco` | `TEXT` | NOT NULL | — | — |
| `valor` | `INTEGER` | — | — | — |
| `unidade` | `TEXT` | NOT NULL | — | — |
| `atualizado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## ouvidoria_prazos_historico

> Origem: `065_ouvidoria_prazos_calendario.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `gravidade` | `TEXT` | NOT NULL | — | — |
| `marco` | `TEXT` | NOT NULL | — | — |
| `valor_anterior` | `INTEGER` | — | — | — |
| `unidade_anterior` | `TEXT` | — | — | — |
| `valor_novo` | `INTEGER` | — | — | — |
| `unidade_nova` | `TEXT` | NOT NULL | — | — |
| `qualquer` | `acao` | — | — | — |
| `e` | `a` | — | — | — |
| `apagar` | `quem` | — | — | — |
| `autor_nome` | `TEXT` | NOT NULL | — | — |
| `ocorrido_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_ouvidoria_prazos_historico_celula` em `(gravidade, marco, ocorrido_em DESC)` (de `065_ouvidoria_prazos_calendario.sql`)

## ouvidoria_feriados

> Origem: `065_ouvidoria_prazos_calendario.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `data` | `DATE` | PK | — | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `abrangencia` | `TEXT` | NOT NULL | — | — |

## ouvidoria_anexos

> Origem: `066_ouvidoria_registro_manual_anexos.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `filename` | `TEXT` | NOT NULL | — | — |
| `content_type` | `TEXT` | NOT NULL | — | — |
| `o` | `mesmo` | NOT NULL | — | — |
| `storage_path` | `TEXT` | NOT NULL | — | — |
| `enviado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `enviado_por_nome` | `TEXT` | NOT NULL | — | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_ouvidoria_anexos_manifestacao` em `(manifestacao_id, created_at)` (de `066_ouvidoria_registro_manual_anexos.sql`)

## ouvidoria_setor_responsaveis

> Origem: `068_ouvidoria_responsaveis_notificacoes.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `setor` | `TEXT` | NOT NULL | — | — |
| `papel` | `TEXT` | NOT NULL | — | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `email` | `TEXT` | NOT NULL | — | — |
| `com` | `data` | — | — | — |
| `o` | `titular` | NOT NULL | `CURRENT_DATE` | — |
| `vigencia_fim` | `DATE` | — | — | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `updated_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_ouvidoria_setor_responsaveis_setor` em `(setor, papel)` (de `068_ouvidoria_responsaveis_notificacoes.sql`)

## ouvidoria_notificacoes

> Origem: `068_ouvidoria_responsaveis_notificacoes.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `gatilho` | `TEXT` | NOT NULL | — | — |
| `destinatario_nome` | `TEXT` | NOT NULL | — | — |
| `destinatario_email` | `TEXT` | NOT NULL | — | — |
| `papel_destinatario` | `TEXT` | — | — | — |
| `para` | `o` | NOT NULL | `'agendada'` | — |
| `tentativas` | `INTEGER` | NOT NULL | `0` | — |
| `e` | `falha` | NOT NULL | `now()` | — |
| `enviada_em` | `TIMESTAMPTZ` | — | — | — |
| `ultimo_erro` | `TEXT` | — | — | — |
| `detalhe` | `TEXT` | — | — | — |
| `criada_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_ouvidoria_notificacoes_fila` em `(enviar_a_partir_de)` (de `068_ouvidoria_responsaveis_notificacoes.sql`)
- `idx_ouvidoria_notificacoes_manifestacao` em `(manifestacao_id, criada_em DESC)` (de `068_ouvidoria_responsaveis_notificacoes.sql`)

## ouvidoria_setor_tokens

> Origem: `069_ouvidoria_portal_setor.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `destinatario_nome` | `TEXT` | NOT NULL | — | — |
| `destinatario_email` | `TEXT` | NOT NULL | — | — |
| `token_hash` | `TEXT` | NOT NULL | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `expira_em` | `TIMESTAMPTZ` | NOT NULL | `now() + interval '30 days'` | — |
| `usado_em` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `idx_ouvidoria_setor_tokens_hash` em `(token_hash)` (de `069_ouvidoria_portal_setor.sql`)
- `idx_ouvidoria_setor_tokens_vigente` em `(manifestacao_id, destinatario_email)` (de `069_ouvidoria_portal_setor.sql`)
- `idx_ouvidoria_setor_tokens_destinatario` em `(manifestacao_id, destinatario_email)` (de `070_ouvidoria_setor_tokens_multiplos.sql`)

## ouvidoria_prorrogacoes

> Origem: `073_ouvidoria_prorrogacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `justificativa` | `TEXT` | NOT NULL | — | — |
| `dias_uteis_pedidos` | `INTEGER` | NOT NULL | — | — |
| `e` | `sem` | — | — | — |
| `prazo_novo` | `TIMESTAMPTZ` | — | — | — |
| `status` | `TEXT` | NOT NULL | `'pendente'` | — |
| `solicitada_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `solicitante_nome` | `TEXT` | NOT NULL | — | — |
| `solicitante_email` | `TEXT` | — | — | — |
| `decidida_em` | `TIMESTAMPTZ` | — | — | — |
| `decidida_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `decidida_por_nome` | `TEXT` | — | — | — |
| `decisao_justificativa` | `TEXT` | — | — | — |

**Indexes:**
- `idx_ouvidoria_prorrogacoes_unica` em `(manifestacao_id)` (de `073_ouvidoria_prorrogacao.sql`)

## ouvidoria_tentativas_contato

> Origem: `075_ouvidoria_aguardando_manifestante.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `tentada_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `canal` | `TEXT` | NOT NULL | — | — |
| `observacao` | `TEXT` | — | — | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `autor_nome` | `TEXT` | NOT NULL | — | — |

**Indexes:**
- `idx_ouvidoria_tentativas_manifestacao` em `(manifestacao_id, tentada_em)` (de `075_ouvidoria_aguardando_manifestante.sql`)

---

**Resumo:** 36 tabelas vivas.
