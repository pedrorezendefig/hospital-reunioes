# ENTIDADES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-10-13T03:17+0000 -->

Modelo de dados do Hospital Reuniões. Tabelas no Postgres (via Supabase).

## participantes

> Origem: `001_create_participantes.sql` (alterada em: 014_add_externo_co_responsavel.sql, 017_add_super_admin.sql, 028_add_taxonomy_fks.sql, 036_add_access_profile.sql, 045_pops_fundacao_acesso.sql, 064_ouvidoria_manifestacao.sql, 103_tecnologia_vinculo.sql, 116_contas_medicas_fundacao.sql)

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
| `github_login` | `TEXT` | — | — | — |
| `perfil_contas_medicas` | `TEXT` | — | — | — |

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
- `participantes_github_login_lower_idx` em `((lower(github_login)` (de `103_tecnologia_vinculo.sql`)
- `idx_participantes_perfil_contas_medicas` em `(perfil_contas_medicas)` (de `116_contas_medicas_fundacao.sql`)

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

> Origem: `064_ouvidoria_manifestacao.sql` (alterada em: 112_ouvidoria_triagem_email.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `manifestacao_id` | `UUID` | NOT NULL | — | `ouvidoria_protocolos.id` |
| `ocorrido_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `ator_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `ator_nome` | `TEXT` | NOT NULL | — | — |
| `acao` | `TEXT` | NOT NULL | — | — |
| `email_recebido_id` | `UUID` | — | — | `ouvidoria_emails_recebidos.id` |

**Indexes:**
- `idx_ouvidoria_acessos_manifestacao` em `(manifestacao_id, ocorrido_em DESC)` (de `064_ouvidoria_manifestacao.sql`)
- `idx_ouvidoria_acessos_email_recebido` em `(email_recebido_id, ocorrido_em DESC)` (de `112_ouvidoria_triagem_email.sql`)

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

> Origem: `069_ouvidoria_portal_setor.sql` (alterada em: 106_ouvidoria_token_do_setor_revogado.sql)

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
| `revogado_em` | `TIMESTAMPTZ` | — | — | — |

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

## ouvidoria_relatorios

> Origem: `080_ouvidoria_relatorios.sql` (alterada em: 080_ouvidoria_relatorios.sql, 083_ouvidoria_relatorio_sugestoes_ia.sql, 087_ouvidoria_relatorio_fila_recuperacao.sql, 088_ouvidoria_relatorio_entregas.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `e` | `o` | UNIQUE, NOT NULL | — | — |
| `periodo_inicio` | `DATE` | NOT NULL | — | — |
| `periodo_fim` | `DATE` | NOT NULL | — | — |
| `no` | `relogio` | NOT NULL | — | — |
| `gerado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `sem` | `nunca` | — | — | — |
| `quem` | `recebeu` | — | — | — |
| `os` | `destinatarios` | NOT NULL | `'{}'` | — |
| `e` | `quantas` | — | — | — |
| `um` | `documento` | — | — | — |
| `reenvios` | `INTEGER` | NOT NULL | `0` | — |
| `ou` | `o` | — | — | — |
| `reenviado_em` | `TIMESTAMPTZ` | — | — | — |
| `quando` | `e` | — | — | — |
| `e` | `so` | — | — | — |
| `sugestoes` | `JSONB` | — | — | — |
| `sugestoes_aviso` | `TEXT` | — | — | — |
| `tentativas` | `INTEGER` | NOT NULL | `0` | — |
| `desistido_em` | `TIMESTAMPTZ` | — | — | — |
| `entregas` | `JSONB` | NOT NULL | `'[]'::jsonb` | — |

**Indexes:**
- `idx_ouvidoria_relatorios_competencia` em `(competencia)` (de `080_ouvidoria_relatorios.sql`)
- `idx_ouvidoria_relatorios_nao_enviados` em `(periodo_fim DESC)` (de `080_ouvidoria_relatorios.sql`)
- `idx_ouvidoria_relatorios_periodo` em `(periodo_fim DESC)` (de `080_ouvidoria_relatorios.sql`)
- `idx_ouvidoria_relatorios_fila_recuperacao` em `(tentativas ASC, periodo_fim ASC)` (de `087_ouvidoria_relatorio_fila_recuperacao.sql`)

## ouvidoria_nota_externa

> Origem: `082_ouvidoria_nota_externa.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `fonte` | `TEXT` | NOT NULL | — | — |
| `nota` | `NUMERIC(4,2)` | NOT NULL | — | — |
| `no` | `banco` | — | — | — |
| `um` | `script` | — | — | — |
| `no` | `relogio` | — | — | — |
| `e` | `e` | NOT NULL | — | — |
| `e` | `o` | — | — | `participantes.id` |
| `registrada_por_nome` | `TEXT` | NOT NULL | `''` | — |
| `criada_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_ouvidoria_nota_externa_fonte` em `(fonte, registrada_em DESC)` (de `082_ouvidoria_nota_externa.sql`)

## ouvidoria_pontos

> Origem: `085_ouvidoria_pontos_de_escuta.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `setor` | `TEXT` | NOT NULL | — | — |
| `ponto` | `TEXT` | NOT NULL | — | — |
| `ativo` | `BOOLEAN` | NOT NULL | `TRUE` | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `criado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `e` | `nao` | — | — | — |
| `e` | `o` | — | — | — |

**Indexes:**
- `idx_ouvidoria_pontos_codigo` em `(codigo)` (de `085_ouvidoria_pontos_de_escuta.sql`)
- `idx_ouvidoria_pontos_setor` em `(setor, ponto)` (de `085_ouvidoria_pontos_de_escuta.sql`)

## tecnologia_produtos

> Origem: `102_tecnologia_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `ativo` | `BOOLEAN` | NOT NULL | `true` | — |
| `dono_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `ordem` | `INTEGER` | NOT NULL | `0` | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `atualizado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `tecnologia_produtos_nome_lower_idx` em `((lower(nome)` (de `102_tecnologia_fundacao.sql`)

## tecnologia_demandas

> Origem: `102_tecnologia_fundacao.sql` (alterada em: 103_tecnologia_vinculo.sql, 115_tecnologia_anexos_e_em_producao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `titulo` | `TEXT` | NOT NULL | — | — |
| `descricao` | `TEXT` | — | — | — |
| `tipo` | `TEXT` | NOT NULL | — | — |
| `produto_id` | `UUID` | NOT NULL | — | `tecnologia_produtos.id` |
| `estado` | `TEXT` | NOT NULL | `'nova'` | — |
| `responsavel_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `prioridade` | `TEXT` | NOT NULL | `'normal'` | — |
| `prazo` | `DATE` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `atualizado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `concluida_em` | `TIMESTAMPTZ` | — | — | — |
| `concluida_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `cancelada_em` | `TIMESTAMPTZ` | — | — | — |
| `cancelada_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `github_issue_numero` | `INTEGER` | — | — | — |
| `etapa` | `TEXT` | NOT NULL | `'registrada'` | — |
| `partes_entregues` | `INTEGER` | — | — | — |
| `partes_total` | `INTEGER` | — | — | — |
| `o_que_muda` | `JSONB` | — | — | — |
| `partes` | `JSONB` | — | — | — |
| `github_foto` | `JSONB` | — | — | — |
| `github_sincronizado_em` | `TIMESTAMPTZ` | — | — | — |
| `vinculado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `versao_em_producao` | `TEXT` | — | — | — |
| `entregue_em` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `idx_tecnologia_demandas_estado` em `(estado)` (de `102_tecnologia_fundacao.sql`)
- `idx_tecnologia_demandas_responsavel` em `(responsavel_id)` (de `102_tecnologia_fundacao.sql`)
- `idx_tecnologia_demandas_produto` em `(produto_id)` (de `102_tecnologia_fundacao.sql`)
- `tecnologia_demandas_github_issue_numero_idx` em `(github_issue_numero)` (de `103_tecnologia_vinculo.sql`)

## tecnologia_conversas

> Origem: `102_tecnologia_fundacao.sql` (alterada em: 104_tecnologia_conversa_espelhada.sql, 105_tecnologia_mencoes_da_correcao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `demanda_id` | `UUID` | NOT NULL | — | `tecnologia_demandas.id` |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `linha` | `TEXT` | NOT NULL | `'resposta'` | — |
| `texto` | `TEXT` | NOT NULL | — | — |
| `mencoes` | `VARCHAR(10)[]` | NOT NULL | `'{}'` | — |
| `movimento_campo` | `TEXT` | — | — | — |
| `movimento_de` | `TEXT` | — | — | — |
| `movimento_para` | `TEXT` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `editado_em` | `TIMESTAMPTZ` | — | — | — |
| `github_comentario_id` | `BIGINT` | — | — | — |
| `mencoes_da_correcao` | `VARCHAR(10)[]` | — | — | — |

**Indexes:**
- `idx_tecnologia_conversas_demanda` em `(demanda_id, criado_em)` (de `102_tecnologia_fundacao.sql`)

## ouvidoria_emails_recebidos_anexos

> Origem: `112_ouvidoria_triagem_email.sql` (alterada em: 112_ouvidoria_triagem_email.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `email_recebido_id` | `UUID` | NOT NULL | — | `ouvidoria_emails_recebidos.id` |
| `resend_anexo_id` | `TEXT` | NOT NULL | — | — |
| `filename` | `TEXT` | NOT NULL | — | — |
| `content_type` | `TEXT` | NOT NULL | — | — |
| `tamanho_bytes` | `BIGINT` | — | — | — |
| `storage_path` | `TEXT` | — | — | — |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `motivo_sem_binario` | `TEXT` | — | — | — |

## migracoes_aplicadas

> Origem: `114_migracoes_aplicadas.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `numero` | `INTEGER` | PK | — | — |
| `aplicada_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## tecnologia_anexos

> Origem: `115_tecnologia_anexos_e_em_producao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `demanda_id` | `UUID` | NOT NULL | — | `tecnologia_demandas.id` |
| `ordem` | `INTEGER` | NOT NULL | — | — |
| `storage_path` | `TEXT` | NOT NULL | — | — |
| `nome_original` | `TEXT` | NOT NULL | — | — |
| `content_type` | `TEXT` | NOT NULL | — | — |
| `tamanho_bytes` | `BIGINT` | NOT NULL | — | — |
| `anexado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `conversa_id` | `UUID` | — | — | `tecnologia_conversas.id` |
| `apagado_em` | `TIMESTAMPTZ` | — | — | — |

**Indexes:**
- `idx_tecnologia_anexos_conversa` em `(conversa_id)` (de `115_tecnologia_anexos_e_em_producao.sql`)

## cm_perfil_permissao

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `perfil` | `TEXT` | NOT NULL | — | — |
| `permissao` | `TEXT` | NOT NULL | — | — |
| `ligada` | `BOOLEAN` | NOT NULL | `false` | — |

## cm_operadora

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `sigla` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `situacao` | `TEXT` | NOT NULL | `'SEM_MEMORIA'` | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## cm_operadora_plano

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | NOT NULL | — | `cm_operadora.id` |
| `nome_mv` | `TEXT` | NOT NULL | — | — |
| `coluna_preco` | `TEXT` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_operadora_plano_nome_mv` em `((lower(nome_mv)` (de `116_contas_medicas_fundacao.sql`)

## cm_memoria_versao

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | NOT NULL | — | `cm_operadora.id` |
| `versao` | `TEXT` | NOT NULL | — | — |
| `parametros_json` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |
| `texto_md` | `TEXT` | — | — | — |
| `vigente` | `BOOLEAN` | NOT NULL | `false` | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `resumo` | `TEXT` | — | — | — |

**Indexes:**
- `idx_cm_memoria_versao_vigente` em `(operadora_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_regra

> Origem: `116_contas_medicas_fundacao.sql` (alterada em: 118_contas_medicas_gestao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | NOT NULL | — | `cm_operadora.id` |
| `memoria_versao_id` | `UUID` | — | — | `cm_memoria_versao.id` |
| `codigo` | `TEXT` | NOT NULL | — | — |
| `secao` | `TEXT` | — | — | — |
| `texto` | `TEXT` | NOT NULL | — | — |
| `tipo` | `TEXT` | — | — | — |
| `origem` | `TEXT` | — | — | — |
| `status` | `TEXT` | NOT NULL | `'PENDENTE'` | — |
| `contrato_diz` | `TEXT` | — | — | — |
| `validado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `validado_em` | `TIMESTAMPTZ` | — | — | — |
| `ativa` | `BOOLEAN` | NOT NULL | `true` | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `modelo_id` | `TEXT` | — | — | — |

**Indexes:**
- `idx_cm_regra_operadora_codigo` em `(operadora_id, codigo)` (de `116_contas_medicas_fundacao.sql`)
- `idx_cm_regra_modelo` em `(modelo_id)` (de `118_contas_medicas_gestao.sql`)

## cm_tabela_preco

> Origem: `116_contas_medicas_fundacao.sql` (alterada em: 118_contas_medicas_gestao.sql)

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `tipo` | `TEXT` | — | — | — |
| `versao` | `TEXT` | — | — | — |
| `vigencia_inicio` | `DATE` | — | — | — |
| `vigencia_fim` | `DATE` | — | — | — |
| `situacao` | `TEXT` | — | — | — |
| `arquivo_nome` | `TEXT` | — | — | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `mapeamento_json` | `JSONB` | — | — | — |
| `arquivo_original` | `TEXT` | — | — | — |

## cm_tabela_preco_item

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `tabela_id` | `UUID` | NOT NULL | — | `cm_tabela_preco.id` |
| `codigo` | `TEXT` | NOT NULL | — | — |
| `codigo_alternativo` | `TEXT` | — | — | — |
| `descricao` | `TEXT` | — | — | — |
| `grupo` | `TEXT` | — | — | — |
| `unidade` | `TEXT` | — | — | — |
| `precos_json` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |
| `extra_json` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |

**Indexes:**
- `idx_cm_tabela_preco_item_tabela_codigo` em `(tabela_id, codigo)` (de `116_contas_medicas_fundacao.sql`)

## cm_operadora_tabela

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | NOT NULL | — | `cm_operadora.id` |
| `categoria` | `TEXT` | NOT NULL | — | — |
| `tabela_id` | `UUID` | NOT NULL | — | `cm_tabela_preco.id` |
| `regra_uso_json` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_operadora_tabela_operadora` em `(operadora_id, categoria)` (de `116_contas_medicas_fundacao.sql`)

## cm_setor

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `nome_mv` | `TEXT` | NOT NULL | — | — |
| `acomodacao` | `TEXT` | — | — | — |
| `grupo_gases` | `TEXT` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_setor_nome_mv` em `((lower(nome_mv)` (de `116_contas_medicas_fundacao.sql`)

## cm_item_dicionario

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `termo` | `TEXT` | NOT NULL | — | — |
| `codigo_conta` | `TEXT` | — | — | — |
| `descricao_conta` | `TEXT` | — | — | — |
| `unidade_cobranca` | `TEXT` | — | — | — |
| `conteudo_por_unidade` | `TEXT` | — | — | — |
| `origem` | `TEXT` | NOT NULL | `'GESTAO'` | — |
| `situacao` | `TEXT` | NOT NULL | `'PROPOSTO'` | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_item_dicionario_termo` em `((lower(termo)` (de `116_contas_medicas_fundacao.sql`)

## cm_envio

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `usuario_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## cm_atendimento

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `numero_atendimento` | `TEXT` | NOT NULL | — | — |
| `paciente_rotulo` | `TEXT` | — | — | — |
| `idade_anos` | `INTEGER` | — | — | — |
| `operadora_id` | `UUID` | — | — | `cm_operadora.id` |
| `plano` | `TEXT` | — | — | — |
| `coluna_preco` | `TEXT` | — | — | — |
| `acomodacao_contratada` | `TEXT` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_atendimento_numero` em `(numero_atendimento)` (de `116_contas_medicas_fundacao.sql`)

## cm_arquivo

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `envio_id` | `UUID` | NOT NULL | — | `cm_envio.id` |
| `tipo` | `TEXT` | NOT NULL | — | — |
| `atendimento_id` | `UUID` | — | — | `cm_atendimento.id` |
| `numero_atendimento` | `TEXT` | — | — | — |
| `paginas` | `INTEGER` | — | — | — |
| `chave_bucket` | `TEXT` | — | — | — |
| `hash` | `TEXT` | — | — | — |
| `apagar_em` | `TIMESTAMPTZ` | — | — | — |
| `apagado_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_arquivo_apagar_em` em `(apagar_em)` (de `116_contas_medicas_fundacao.sql`)

## cm_eventos

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `atendimento_id` | `UUID` | NOT NULL | — | `cm_atendimento.id` |
| `eventos_json` | `JSONB` | NOT NULL | `'{}'::jsonb` | — |
| `prontuario_ate` | `DATE` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_eventos_atendimento` em `(atendimento_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_prescricao

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `atendimento_id` | `UUID` | NOT NULL | — | `cm_atendimento.id` |
| `data` | `DATE` | — | — | — |
| `hora` | `TIME` | — | — | — |
| `subtipo` | `TEXT` | — | — | — |
| `pagina` | `INTEGER` | — | — | — |

**Indexes:**
- `idx_cm_prescricao_atendimento` em `(atendimento_id, data)` (de `116_contas_medicas_fundacao.sql`)

## cm_prescricao_item

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `prescricao_id` | `UUID` | NOT NULL | — | `cm_prescricao.id` |
| `secao` | `TEXT` | — | — | — |
| `n` | `INTEGER` | — | — | — |
| `nome` | `TEXT` | — | — | — |
| `generico` | `TEXT` | — | — | — |
| `colunas` | `JSONB` | — | — | — |
| `doses_por_dia` | `NUMERIC(10, 2)` | — | — | — |
| `se_necessario` | `BOOLEAN` | NOT NULL | `false` | — |
| `suspenso` | `BOOLEAN` | NOT NULL | `false` | — |
| `obs` | `TEXT` | — | — | — |
| `componentes_json` | `JSONB` | — | — | — |
| `pedido` | `TEXT` | — | — | — |

**Indexes:**
- `idx_cm_prescricao_item_prescricao` em `(prescricao_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_cirurgia

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `atendimento_id` | `UUID` | NOT NULL | — | `cm_atendimento.id` |
| `procedimentos_json` | `JSONB` | — | — | — |
| `inicio` | `TIMESTAMPTZ` | — | — | — |
| `fim` | `TIMESTAMPTZ` | — | — | — |
| `anestesia_inicio` | `TIMESTAMPTZ` | — | — | — |
| `anestesia_fim` | `TIMESTAMPTZ` | — | — | — |
| `tecnica` | `TEXT` | — | — | — |
| `gases_json` | `JSONB` | — | — | — |
| `medicamentos_ficha_json` | `JSONB` | — | — | — |

**Indexes:**
- `idx_cm_cirurgia_atendimento` em `(atendimento_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_glicemia_dia

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `atendimento_id` | `UUID` | NOT NULL | — | `cm_atendimento.id` |
| `data` | `DATE` | NOT NULL | — | — |
| `quantidade` | `INTEGER` | NOT NULL | — | — |

## cm_conta

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `atendimento_id` | `UUID` | NOT NULL | — | `cm_atendimento.id` |
| `arquivo_id` | `UUID` | — | — | `cm_arquivo.id` |
| `numero_conta` | `TEXT` | — | — | — |
| `parcial_ordem` | `INTEGER` | — | — | — |
| `periodo_inicio` | `DATE` | — | — | — |
| `periodo_fim` | `DATE` | — | — | — |
| `total_lancado` | `NUMERIC(14, 2)` | — | — | — |
| `situacao` | `TEXT` | NOT NULL | `'AGUARDANDO_ARQUIVO'` | — |
| `erro_motivo` | `TEXT` | — | — | — |
| `processando_desde` | `TIMESTAMPTZ` | — | — | — |
| `tentativas` | `INTEGER` | NOT NULL | `0` | — |
| `parecer_parcial` | `BOOLEAN` | NOT NULL | `false` | — |
| `faltantes` | `JSONB` | — | — | — |
| `nota_bruta` | `NUMERIC(6, 2)` | — | — | — |
| `nota_entrada` | `NUMERIC(6, 2)` | — | — | — |
| `valor_apontado` | `NUMERIC(14, 2)` | — | — | — |
| `valor_em_validacao` | `NUMERIC(14, 2)` | — | — | — |
| `faturista_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `ordem_fila` | `BIGINT` | — | — | — |
| `enviada_em` | `TIMESTAMPTZ` | — | — | — |
| `pronta_em` | `TIMESTAMPTZ` | — | — | — |
| `aberta_em` | `TIMESTAMPTZ` | — | — | — |
| `concluida_em` | `TIMESTAMPTZ` | — | — | — |
| `memoria_versao_id` | `UUID` | — | — | `cm_memoria_versao.id` |
| `modelo_ia` | `TEXT` | — | — | — |
| `tokens_entrada` | `INTEGER` | — | — | — |
| `tokens_saida` | `INTEGER` | — | — | — |
| `tokens_cache` | `INTEGER` | — | — | — |
| `custo_usd` | `NUMERIC(10, 4)` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_conta_faturista_situacao_ordem` em `(faturista_id, situacao, ordem_fila)` (de `116_contas_medicas_fundacao.sql`)
- `idx_cm_conta_atendimento` em `(atendimento_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_conta_item

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `conta_id` | `UUID` | NOT NULL | — | `cm_conta.id` |
| `ordem` | `INTEGER` | — | — | — |
| `data` | `DATE` | — | — | — |
| `grupo_conta` | `TEXT` | — | — | — |
| `setor` | `TEXT` | — | — | — |
| `grupo_procedimento` | `TEXT` | — | — | — |
| `codigo` | `TEXT` | — | — | — |
| `descricao` | `TEXT` | — | — | — |
| `quantidade` | `NUMERIC(14, 4)` | — | — | — |
| `unidade` | `TEXT` | — | — | — |
| `valor_unitario` | `NUMERIC(14, 4)` | — | — | — |
| `valor_total` | `NUMERIC(14, 2)` | — | — | — |
| `percentual` | `NUMERIC(7, 2)` | — | — | — |
| `preco_tabela` | `NUMERIC(14, 4)` | — | — | — |
| `situacao_preco` | `TEXT` | — | — | — |

**Indexes:**
- `idx_cm_conta_item_conta` em `(conta_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_guia_linha

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `conta_id` | `UUID` | NOT NULL | — | `cm_conta.id` |
| `ordem` | `INTEGER` | — | — | — |
| `acao` | `TEXT` | NOT NULL | — | — |
| `data` | `DATE` | — | — | — |
| `data_fim` | `DATE` | — | — | — |
| `setor` | `TEXT` | — | — | — |
| `codigo` | `TEXT` | — | — | — |
| `descricao` | `TEXT` | — | — | — |
| `quantidade_lancada` | `NUMERIC(14, 4)` | — | — | — |
| `quantidade_devida` | `NUMERIC(14, 4)` | — | — | — |
| `preco_lancado` | `NUMERIC(14, 4)` | — | — | — |
| `preco_tabela` | `NUMERIC(14, 4)` | — | — | — |
| `valor_diferenca` | `NUMERIC(14, 2)` | — | — | — |
| `regra_codigo` | `TEXT` | — | — | — |
| `motivo` | `TEXT` | — | — | — |
| `evidencia_pagina` | `INTEGER` | — | — | — |
| `evidencia_trecho` | `TEXT` | — | — | — |
| `nivel_evidencia` | `TEXT` | — | — | — |
| `causa_raiz` | `TEXT` | — | — | — |
| `confianca` | `TEXT` | — | — | — |
| `origem` | `TEXT` | NOT NULL | `'CODIGO'` | — |
| `estado` | `TEXT` | NOT NULL | `'ABERTA'` | — |
| `motivo_nao_procede` | `TEXT` | — | — | — |
| `texto_nao_procede` | `TEXT` | — | — | — |
| `marcado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `marcado_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_guia_linha_conta` em `(conta_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_observacao

> Origem: `116_contas_medicas_fundacao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `conta_id` | `UUID` | NOT NULL | — | `cm_conta.id` |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `texto` | `TEXT` | NOT NULL | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_observacao_conta` em `(conta_id)` (de `116_contas_medicas_fundacao.sql`)

## cm_registro

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `data` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |
| `entidade` | `TEXT` | NOT NULL | — | — |
| `entidade_id` | `TEXT` | NOT NULL | — | — |
| `antes_json` | `JSONB` | — | — | — |
| `depois_json` | `JSONB` | — | — | — |

**Indexes:**
- `idx_cm_registro_entidade` em `(entidade, entidade_id, data DESC)` (de `118_contas_medicas_gestao.sql`)

## cm_regra_historico

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `regra_id` | `UUID` | NOT NULL | — | `cm_regra.id` |
| `memoria_versao_id` | `UUID` | — | — | `cm_memoria_versao.id` |
| `texto_anterior` | `TEXT` | — | — | — |
| `texto_novo` | `TEXT` | NOT NULL | — | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_regra_historico_regra` em `(regra_id, criado_em DESC)` (de `118_contas_medicas_gestao.sql`)

## cm_validacao_tema

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | — | — | `cm_operadora.id` |
| `tipo` | `TEXT` | NOT NULL | — | — |
| `regra_codigo` | `TEXT` | — | — | — |
| `codigo_item` | `TEXT` | — | — | — |
| `item_dicionario_id` | `UUID` | — | — | `cm_item_dicionario.id` |
| `titulo` | `TEXT` | NOT NULL | — | — |
| `estado` | `TEXT` | NOT NULL | `'ABERTO'` | — |
| `decisao` | `TEXT` | — | — | — |
| `resposta` | `TEXT` | — | — | — |
| `leitura_ia` | `TEXT` | — | — | — |
| `decidido_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `decidido_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_validacao_tema_estado` em `(estado, tipo)` (de `118_contas_medicas_gestao.sql`)

## cm_validacao_tema_linha

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `tema_id` | `UUID` | NOT NULL | — | `cm_validacao_tema.id` |
| `guia_linha_id` | `UUID` | — | — | `cm_guia_linha.id` |
| `observacao_id` | `UUID` | — | — | `cm_observacao.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_validacao_tema_linha_tema` em `(tema_id)` (de `118_contas_medicas_gestao.sql`)
- `idx_cm_validacao_tema_linha_guia` em `(tema_id, guia_linha_id)` (de `118_contas_medicas_gestao.sql`)

## cm_cenario

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `codigo` | `TEXT` | UNIQUE, NOT NULL | — | — |
| `nome` | `TEXT` | NOT NULL | — | — |
| `operadora_id` | `UUID` | — | — | `cm_operadora.id` |
| `gatilho_texto` | `TEXT` | NOT NULL | — | — |
| `orientacao` | `TEXT` | — | — | — |
| `ativo` | `BOOLEAN` | NOT NULL | `true` | — |
| `autor_id` | `VARCHAR(10)` | — | — | `participantes.id` |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## cm_cenario_item

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `cenario_id` | `UUID` | NOT NULL | — | `cm_cenario.id` |
| `codigo` | `TEXT` | NOT NULL | — | — |
| `descricao` | `TEXT` | — | — | — |
| `quantidade` | `NUMERIC(14, 4)` | NOT NULL | `1` | — |

**Indexes:**
- `idx_cm_cenario_item_cenario` em `(cenario_id)` (de `118_contas_medicas_gestao.sql`)

## cm_lembrete

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `conta_id` | `UUID` | NOT NULL | — | `cm_conta.id` |
| `cenario_id` | `UUID` | NOT NULL | — | `cm_cenario.id` |
| `data` | `DATE` | — | — | — |
| `setor` | `TEXT` | — | — | — |
| `evidencia_pagina` | `INTEGER` | — | — | — |
| `evidencia_trecho` | `TEXT` | — | — | — |
| `estado` | `TEXT` | NOT NULL | `'ABERTO'` | — |
| `observacao` | `TEXT` | — | — | — |
| `marcado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `marcado_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

**Indexes:**
- `idx_cm_lembrete_conta` em `(conta_id)` (de `118_contas_medicas_gestao.sql`)
- `idx_cm_lembrete_estado` em `(estado, criado_em)` (de `118_contas_medicas_gestao.sql`)

## cm_lembrete_item

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `lembrete_id` | `UUID` | NOT NULL | — | `cm_lembrete.id` |
| `codigo` | `TEXT` | NOT NULL | — | — |
| `descricao` | `TEXT` | — | — | — |
| `quantidade` | `NUMERIC(14, 4)` | — | — | — |
| `preco_tabela` | `NUMERIC(14, 4)` | — | — | — |
| `valor` | `NUMERIC(14, 2)` | — | — | — |

**Indexes:**
- `idx_cm_lembrete_item_lembrete` em `(lembrete_id)` (de `118_contas_medicas_gestao.sql`)

## cm_contrato

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `operadora_id` | `UUID` | UNIQUE, NOT NULL | — | `cm_operadora.id` |
| `data_assinatura` | `DATE` | — | — | — |
| `aditivo_numero` | `TEXT` | — | — | — |
| `aditivo_data` | `DATE` | — | — | — |
| `vigencia_inicio` | `DATE` | — | — | — |
| `vencimento` | `DATE` | — | — | — |
| `vencimento_calculado` | `BOOLEAN` | NOT NULL | `false` | — |
| `vencimento_e_negociacao` | `BOOLEAN` | NOT NULL | `false` | — |
| `aviso_dias` | `INTEGER` | — | — | — |
| `arquivo` | `TEXT` | — | — | — |
| `confirmado_por` | `VARCHAR(10)` | — | — | `participantes.id` |
| `confirmado_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

## cm_aviso

> Origem: `118_contas_medicas_gestao.sql`

| Campo | Tipo | Constraints | Default | FK |
|-------|------|-------------|---------|-----|
| `id` | `UUID` | PK | `gen_random_uuid()` | — |
| `contrato_id` | `UUID` | NOT NULL | — | `cm_contrato.id` |
| `data_prevista` | `DATE` | NOT NULL | — | — |
| `enviado_em` | `TIMESTAMPTZ` | — | — | — |
| `criado_em` | `TIMESTAMPTZ` | NOT NULL | `now()` | — |

---

**Resumo:** 76 tabelas vivas.
