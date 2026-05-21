# ENTIDADES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T20:24-0300 -->

Modelo de dados do Hospital Reuniões. Tabelas no Postgres (via Supabase).

## participantes

> Origem: `001_create_participantes.sql` (alterada em: 014_add_externo_co_responsavel.sql, 017_add_super_admin.sql, 028_add_taxonomy_fks.sql, 036_add_access_profile.sql)

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

**Indexes:**
- `idx_participantes_email` em `(email)` (de `001_create_participantes.sql`)
- `idx_participantes_setor` em `(setor)` (de `001_create_participantes.sql`)
- `idx_participantes_ativo` em `(ativo)` (de `001_create_participantes.sql`)
- `idx_participantes_auth` em `(auth_user_id)` (de `001_create_participantes.sql`)
- `idx_participantes_super_admin` em `(is_super_admin)` (de `017_add_super_admin.sql`)
- `idx_participantes_access_profile` em `(access_profile)` (de `036_add_access_profile.sql`)
- `idx_participantes_setor_id` em `(setor_id)` (de `038_fk_indexes.sql`)
- `idx_participantes_cargo_id` em `(cargo_id)` (de `038_fk_indexes.sql`)

## reunioes

> Origem: `002_create_reunioes.sql` (alterada em: 016_importacao_ata_legada.sql, 020_historico_importacao.sql, 028_add_taxonomy_fks.sql, 030_add_soft_delete.sql, 032_drop_local_reuniao.sql, 035_add_lembrete_24h_reunioes.sql, 036_add_access_profile.sql)

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

> Origem: `003_create_pendencias.sql` (alterada em: 014_add_externo_co_responsavel.sql, 030_add_soft_delete.sql)

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

**Indexes:**
- `idx_pendencias_reuniao` em `(id_reuniao)` (de `003_create_pendencias.sql`)
- `idx_pendencias_responsavel` em `(responsavel_id)` (de `003_create_pendencias.sql`)
- `idx_pendencias_status` em `(status)` (de `003_create_pendencias.sql`)
- `idx_pendencias_prazo` em `(prazo)` (de `003_create_pendencias.sql`)
- `idx_pendencias_co_responsavel` em `(co_responsavel_id)` (de `014_add_externo_co_responsavel.sql`)
- `idx_pendencias_live` em `(prazo)` (de `030_add_soft_delete.sql`)

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
| `prazo_proximo":` | `true` | — | — | — |
| `comentario":` | `true` | — | — | — |
| `responsavel_atribuido":` | `true` | — | — | — |
| `emails` | `JSONB` | NOT NULL | `'{
        "validacao_ata": true` | — |
| `lembrete_prazo":` | `true` | — | — | — |
| `resumo_semanal":` | `false` | — | — | — |
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
| `--` | `reenviar_clicksign` | — | — | — |
| `reenviar_email` | `status` | NOT NULL | — | — |
| `--` | `pending` | — | — | — |
| `failed` | `target_ids` | NOT NULL | — | — |
| `--` | `IDs` | NOT NULL | `0` | — |
| `sucessos` | `INTEGER` | NOT NULL | `0` | — |
| `falhas` | `JSONB` | NOT NULL | `'[]'::jsonb` | — |
| `--` | `[{id` | — | — | — |
| `erro}]` | `metadata` | NOT NULL | `'{}'::jsonb` | — |
| `--` | `extras` | — | — | — |
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

---

**Resumo:** 13 tabelas vivas.
