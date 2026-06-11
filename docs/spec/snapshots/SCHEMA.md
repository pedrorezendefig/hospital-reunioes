# SCHEMA.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-06-11T01:02-0300 -->

Diagrama relacional do Hospital Reuniões. Renderiza nativo no GitHub.

## Diagrama ER (Mermaid)

```mermaid
erDiagram
    participantes ||--o{ audit_log : "actor_id"
    participantes ||--o{ bulk_jobs : "actor_id"
    participantes ||--o{ comentarios_pendencias : "autor_id"
    participantes ||--o{ notificacoes : "destinatario_id"
    participantes ||--o{ pendencias : "co_responsavel_id"
    participantes ||--o{ pendencias : "responsavel_id"
    participantes ||--o{ reuniao_participantes : "participante_id"
    participantes ||--o{ reunioes : "criada_por"
    participantes ||--o{ reunioes : "facilitador_id"
    participantes ||--o{ reunioes : "nome_arquivo_original"
    participantes ||--o{ user_preferences : "participante_id"
    pendencias ||--o{ agendamentos_email : "id_acao"
    pendencias ||--o{ comentarios_pendencias : "id_acao"
    reunioes ||--o{ pendencias : "id_reuniao"
    reunioes ||--o{ reuniao_participantes : "id_reuniao"
    reunioes ||--o{ tokens_validacao : "id_reuniao"
    tipos_reuniao ||--o{ reunioes : "tipo_id"

    participantes {
        VARCHAR id PK
        TEXT nome_completo
        TEXT cargo
        TEXT email
        TEXT area
        TEXT setor
        user_role role
        BOOLEAN ativo
        _ mais_colunas "+7"
    }
    reunioes {
        VARCHAR id_reuniao PK
        DATE data
        TIME hora_inicio
        TIME hora_fim
        TEXT titulo
        TEXT tipo
        VARCHAR facilitador_id FK
        TEXT setor
        _ mais_colunas "+26"
    }
    reuniao_participantes {
        UUID id PK
        VARCHAR id_reuniao FK
        VARCHAR participante_id FK
        INTEGER sequence_assinatura
    }
    pendencias {
        VARCHAR id_acao PK
        VARCHAR id_reuniao FK
        TEXT descricao_acao
        VARCHAR responsavel_id FK
        TEXT responsavel_nome
        TEXT cargo
        DATE prazo
        TEXT meta_entregavel
        _ mais_colunas "+6"
    }
    agendamentos_email {
        UUID id PK
        VARCHAR id_acao FK
        TEXT tipo
        DATE data_disparo
        BOOLEAN enviado
        TIMESTAMPTZ enviado_em
        TIMESTAMPTZ created_at
    }
    tokens_validacao {
        UUID token PK
        VARCHAR id_reuniao FK
        TEXT tipo
        BOOLEAN usado
        INTEGER ciclo_correcao
        TIMESTAMPTZ expires_at
        TIMESTAMPTZ created_at
    }
    comentarios_pendencias {
        UUID id PK
        VARCHAR id_acao FK
        VARCHAR autor_id FK
        TEXT autor_nome
        TEXT conteudo
        VARCHAR mencoes
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    notificacoes {
        UUID id PK
        VARCHAR destinatario_id FK
        TEXT tipo
        TEXT titulo
        TEXT mensagem
        VARCHAR referencia_id
        BOOLEAN lida
        TIMESTAMPTZ created_at
    }
    user_preferences {
        VARCHAR participante_id PK
        JSONB notificacoes
        JSONB emails
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    audit_log {
        UUID id PK
        TIMESTAMPTZ timestamp
        VARCHAR actor_id FK
        TEXT actor_email
        TEXT action
        TEXT target_type
        TEXT target_id
        JSONB metadata
        _ mais_colunas "+2"
    }
    bulk_jobs {
        UUID id PK
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
        VARCHAR actor_id FK
        TEXT actor_email
        TEXT job_type
        status reenviar_email
        target_ids failed
        _ mais_colunas "+4"
    }
    cargos {
        UUID id PK
        TEXT nome
        BOOLEAN ativo
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
    tipos_reuniao {
        UUID id PK
        TEXT nome
        BOOLEAN ativo
        TIMESTAMPTZ created_at
        TIMESTAMPTZ updated_at
    }
```

## Indexes principais

| Tabela | Index | Colunas | Origem |
|--------|-------|---------|--------|
| `participantes` | `idx_participantes_email` | `email` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_setor` | `setor` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_ativo` | `ativo` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_auth` | `auth_user_id` | `001_create_participantes.sql` |
| `participantes` | `idx_participantes_super_admin` | `is_super_admin` | `017_add_super_admin.sql` |
| `participantes` | `idx_participantes_access_profile` | `access_profile` | `036_add_access_profile.sql` |
| `participantes` | `idx_participantes_setor_id` | `setor_id` | `038_fk_indexes.sql` |
| `participantes` | `idx_participantes_cargo_id` | `cargo_id` | `038_fk_indexes.sql` |
| `reunioes` | `idx_reunioes_status` | `status_ata` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_data` | `data DESC` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_setor` | `setor` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_fireflies` | `fireflies_meeting_id` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_programada` | `data, status_ata` | `002_create_reunioes.sql` |
| `reunioes` | `idx_reunioes_documento_id_origem` | `documento_id_origem` | `016_importacao_ata_legada.sql` |
| `reunioes` | `idx_reunioes_arquivo_hash` | `arquivo_hash` | `016_importacao_ata_legada.sql` |
| `reunioes` | `idx_reunioes_importado_por` | `importado_por_id` | `020_historico_importacao.sql` |
| `reunioes` | `idx_reunioes_live` | `data DESC` | `030_add_soft_delete.sql` |
| `reunioes` | `idx_reunioes_lembrete_pendente` | `data, hora_inicio` | `035_add_lembrete_24h_reunioes.sql` |
| `reunioes` | `idx_reunioes_criada_por` | `criada_por` | `036_add_access_profile.sql` |
| `reunioes` | `idx_reunioes_facilitador` | `facilitador_id` | `038_fk_indexes.sql` |
| `reunioes` | `idx_reunioes_tipo_id` | `tipo_id` | `038_fk_indexes.sql` |
| `reuniao_participantes` | `idx_reuniao_part_reuniao` | `id_reuniao` | `002_create_reunioes.sql` |
| `reuniao_participantes` | `idx_reuniao_part_participante` | `participante_id` | `002_create_reunioes.sql` |
| `pendencias` | `idx_pendencias_reuniao` | `id_reuniao` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_responsavel` | `responsavel_id` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_status` | `status` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_prazo` | `prazo` | `003_create_pendencias.sql` |
| `pendencias` | `idx_pendencias_co_responsavel` | `co_responsavel_id` | `014_add_externo_co_responsavel.sql` |
| `pendencias` | `idx_pendencias_live` | `prazo` | `030_add_soft_delete.sql` |
| `pendencias` | `idx_pendencias_nota` | `id_nota` | `042_add_id_nota_pendencias.sql` |
| `agendamentos_email` | `idx_agendamentos_disparo` | `data_disparo, enviado` | `003_create_pendencias.sql` |
| `agendamentos_email` | `idx_agendamentos_email_id_acao` | `id_acao` | `038_fk_indexes.sql` |
| `tokens_validacao` | `idx_tokens_reuniao` | `id_reuniao` | `004_create_tokens_validacao.sql` |
| `tokens_validacao` | `idx_tokens_expires` | `expires_at` | `004_create_tokens_validacao.sql` |
| `comentarios_pendencias` | `idx_comentarios_id_acao` | `id_acao` | `007_create_comentarios_pendencias.sql` |
| `comentarios_pendencias` | `idx_comentarios_autor` | `autor_id` | `007_create_comentarios_pendencias.sql` |
| `comentarios_pendencias` | `idx_comentarios_created` | `created_at DESC` | `007_create_comentarios_pendencias.sql` |
| `notificacoes` | `idx_notificacoes_destinatario` | `destinatario_id, lida` | `008_create_notificacoes.sql` |
| `notificacoes` | `idx_notificacoes_created` | `created_at DESC` | `008_create_notificacoes.sql` |
| `notificacoes` | `idx_notificacoes_referencia` | `referencia_id` | `008_create_notificacoes.sql` |
| `audit_log` | `idx_audit_log_timestamp` | `timestamp DESC` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_actor` | `actor_id` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_target` | `target_type, target_id` | `018_create_audit_log.sql` |
| `audit_log` | `idx_audit_log_action` | `action` | `018_create_audit_log.sql` |
| `bulk_jobs` | `idx_bulk_jobs_actor` | `actor_id` | `019_create_bulk_jobs.sql` |
| `bulk_jobs` | `idx_bulk_jobs_status` | `status` | `019_create_bulk_jobs.sql` |
| `bulk_jobs` | `idx_bulk_jobs_created_at` | `created_at DESC` | `019_create_bulk_jobs.sql` |
| `cargos` | `cargos_nome_lower_idx` | `(lower(nome` | `027_create_taxonomy_tables.sql` |
| `tipos_reuniao` | `tipos_reuniao_nome_lower_idx` | `(lower(nome` | `027_create_taxonomy_tables.sql` |

---
**Resumo:** 13 tabelas · 17 relacionamentos FK detectados.
