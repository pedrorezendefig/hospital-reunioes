# SCHEMA.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Diagrama relacional do banco Hospital Reuniões (Postgres via Supabase). Renderiza nativo no GitHub.

## Diagrama ER (visão de domínio)

```mermaid
erDiagram
    auth_users ||--o| participantes : "auth_user_id"
    participantes ||--o{ reunioes : "facilitador_id / criada_por"
    participantes ||--o{ reuniao_participantes : "participante_id"
    participantes ||--o{ pendencias : "responsavel_id / co_responsavel_id"
    participantes ||--o{ comentarios_pendencias : "autor_id"
    participantes ||--o{ notificacoes : "destinatario_id"
    participantes ||--|| user_preferences : "participante_id"
    participantes ||--o{ audit_log : "actor_id"
    participantes ||--o{ bulk_jobs : "actor_id"

    reunioes ||--o{ reuniao_participantes : "id_reuniao"
    reunioes ||--o{ pendencias : "id_reuniao"

    pendencias ||--o{ comentarios_pendencias : "id_acao"

    setores ||--o{ participantes : "setor"
    cargos ||--o{ participantes : "cargo"
    tipos_reuniao ||--o{ reunioes : "tipo"

    participantes {
        VARCHAR id PK
        TEXT nome_completo
        TEXT email UK
        TEXT cargo
        user_role role
        BOOLEAN is_externo
        BOOLEAN is_super_admin
        TEXT access_profile
        UUID auth_user_id FK
        TIMESTAMPTZ deleted_at
    }

    reunioes {
        VARCHAR id_reuniao PK
        DATE data
        TEXT titulo
        TEXT tipo FK
        VARCHAR facilitador_id FK
        VARCHAR criada_por FK
        TEXT status_ata
        JSONB json_ata
        TEXT envelope_key_clicksign
        TEXT id_grupo_recorrencia
        BOOLEAN lembrete_24h_enviado
        TIMESTAMPTZ deleted_at
    }

    pendencias {
        VARCHAR id_acao PK
        VARCHAR id_reuniao FK
        TEXT descricao_acao
        VARCHAR responsavel_id FK
        VARCHAR co_responsavel_id FK
        DATE prazo
        TEXT status
        TIMESTAMPTZ deleted_at
    }

    comentarios_pendencias {
        UUID id PK
        VARCHAR id_acao FK
        VARCHAR autor_id FK
        TEXT conteudo
        VARCHAR mencoes "array"
    }

    notificacoes {
        UUID id PK
        VARCHAR destinatario_id FK
        TEXT tipo
        TEXT titulo
        BOOLEAN lida
    }
```

## Indexes críticos (migration `038_fk_indexes.sql` + outros)

| Tabela                  | Index                                                    | Pra que                                 |
|-------------------------|----------------------------------------------------------|-----------------------------------------|
| reunioes                | `idx_reunioes_data`                                      | listagem cronológica                    |
| reunioes                | `idx_reunioes_facilitador_id`                            | filtro por facilitador                  |
| reunioes                | `idx_reunioes_deleted_at`                                | esconder soft-deleted                   |
| reunioes                | `idx_reunioes_grupo_recorrencia`                         | navegar série recorrente                |
| pendencias              | `idx_pendencias_id_reuniao`                              | drill-down por reunião                  |
| pendencias              | `idx_pendencias_responsavel_id`                          | "minhas pendências"                     |
| pendencias              | `idx_pendencias_status_deleted_at`                       | dashboards                              |
| comentarios_pendencias  | `idx_comentarios_id_acao`                                | thread de comentários                   |
| notificacoes            | `idx_notificacoes_destinatario_lida`                     | contagem de não-lidas                   |
| audit_log               | `idx_audit_log_timestamp_desc`                           | últimos N logs                          |
| audit_log               | `idx_audit_log_actor_id`                                 | filtro por ator                         |

## RLS (Row Level Security)

Habilitada em todas as tabelas operacionais via `009_enable_rls.sql` e `023_enable_rls_audit_bulk.sql`.

Estratégia: o backend FastAPI usa `SUPABASE_SERVICE_ROLE_KEY` (bypass RLS) e aplica controle de acesso na camada de aplicação via `Depends(get_current_user)`. Frontend usa `SUPABASE_ANON_KEY` apenas para login/auth, não consulta dados diretamente.

## Storage Buckets (`006_create_storage_buckets.sql`)

| Bucket           | Pra que                                  |
|------------------|------------------------------------------|
| `audios`         | gravações de áudio de reuniões           |
| `transcricoes`   | TXT de transcrição                       |
| `atas-pdf`       | PDFs preliminares e assinados            |

---

**Resumo:** 12 tabelas operacionais · 1 schema (`public`) · RLS habilitada · Soft delete em participantes/reunioes/pendencias.
