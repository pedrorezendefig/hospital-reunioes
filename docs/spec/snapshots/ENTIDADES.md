# ENTIDADES.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Modelo de dados Hospital Reuniões. Tabelas no Postgres (via Supabase self-hosted). Auth users vivem em `auth.users` (gerenciado pelo Supabase).

## participantes

> Pessoa cadastrada no sistema — pode ser facilitadora, responsável por pendência ou apenas participante de reunião. Origem: `001_create_participantes.sql`, alterada em 011, 014, 017, 026, 030, 036, 037.

| Campo               | Tipo                          | Obrigatório   | Default          | Descrição                                                  |
|---------------------|-------------------------------|---------------|------------------|------------------------------------------------------------|
| id                  | VARCHAR(10) PK                | sim           | auto (P001+)     | identificador único curto                                  |
| nome_completo       | TEXT                          | sim           | —                | nome completo                                              |
| cargo               | TEXT                          | depende       | —                | cargo (nullable para perfil secretaria)                    |
| email               | TEXT UNIQUE                   | depende       | —                | email único (nullable para externos)                       |
| area                | TEXT                          | não           | —                | área de atuação livre                                      |
| setor               | TEXT → FK setores.nome        | não           | —                | setor canonizado                                           |
| role                | enum user_role                | sim           | 'coordenador'    | papel: diretor / coordenador / gerente / presidente        |
| ativo               | BOOLEAN                       | sim           | TRUE             | flag soft-disable (não desliga acesso, só esconde)         |
| is_externo          | BOOLEAN                       | sim           | FALSE            | marca pessoa externa (sem login)                           |
| is_super_admin      | BOOLEAN                       | sim           | FALSE            | acesso administrativo total                                |
| access_profile      | TEXT (regular/secretaria/super_admin) | sim   | 'regular'        | perfil de acesso operacional                               |
| auth_user_id        | UUID → FK auth.users(id)      | não           | —                | ligação com Supabase Auth                                  |
| data_cadastro       | DATE                          | sim           | now()            | dia do cadastro                                            |
| created_at          | TIMESTAMPTZ                   | sim           | now()            | timestamp técnico                                          |
| updated_at          | TIMESTAMPTZ                   | sim           | now() (trigger)  | última edição                                              |
| deleted_at          | TIMESTAMPTZ                   | não           | —                | soft delete (migration 030)                                |

**Relacionamentos:**
- Referenciada por: `reunioes.facilitador_id`, `reunioes.criada_por`, `pendencias.responsavel_id`, `pendencias.co_responsavel_id`, `reuniao_participantes.participante_id`, `comentarios_pendencias.autor_id`, `notificacoes.destinatario_id`, `user_preferences.participante_id`, `audit_log.actor_id`, `bulk_jobs.actor_id`.

---

## reunioes

> Reunião corporativa do hospital — ciclo completo da pré-programação até a assinatura digital da ata. Origem: `002_create_reunioes.sql`, alterada em várias.

| Campo                          | Tipo                          | Obrigatório | Default       | Descrição                                              |
|--------------------------------|-------------------------------|-------------|---------------|--------------------------------------------------------|
| id_reuniao                     | VARCHAR(20) PK                | sim         | auto          | identificador único (R0001+)                           |
| data                           | DATE                          | sim         | —             | data da reunião                                        |
| hora_inicio                    | TIME                          | não         | —             | hora de início                                         |
| hora_fim                       | TIME                          | não         | —             | hora de término                                        |
| titulo                         | TEXT                          | sim         | —             | título descritivo                                      |
| tipo                           | TEXT → FK tipos_reuniao.nome  | não         | —             | tipo canonizado                                        |
| facilitador_id                 | VARCHAR(10) → FK participantes| não         | —             | quem facilitou                                         |
| criada_por                     | VARCHAR(10) → FK participantes| sim         | —             | criador no sistema                                     |
| setor                          | TEXT                          | não         | —             | setor (legado, em desuso após taxonomy)                |
| objetivo                       | TEXT                          | não         | —             | objetivo livre                                         |
| status_ata                     | TEXT                          | sim         | 'PROCESSANDO' | estado (11 valores — ver enum em FLUXOGRAMAS)          |
| total_acoes                    | INTEGER                       | sim         | 0             | contador denormalizado                                 |
| acoes_concluidas               | INTEGER                       | sim         | 0             | contador denormalizado                                 |
| data_assinatura                | DATE                          | não         | —             | data em que ata foi assinada                           |
| url_audio                      | TEXT                          | não         | —             | URL do áudio no storage                                |
| url_transcricao                | TEXT                          | não         | —             | URL da transcrição txt                                 |
| url_pdf_preliminar             | TEXT                          | não         | —             | PDF antes da assinatura                                |
| url_pdf_assinado               | TEXT                          | não         | —             | PDF assinado final                                     |
| envelope_key_clicksign         | TEXT                          | não         | —             | chave do envelope na ClickSign                         |
| json_ata                       | JSONB                         | não         | —             | conteúdo estruturado da ata (saída do pipeline)        |
| fireflies_meeting_id           | TEXT                          | não         | —             | ID se veio do Fireflies                                |
| fonte                          | TEXT (FIREFLIES/MOCK)         | sim         | 'MOCK'        | origem da transcrição                                  |
| ciclo_correcao                 | INTEGER                       | sim         | 0             | quantas iterações de correção rolaram                  |
| participantes_nao_reconhecidos | JSONB                         | sim         | '[]'          | nomes que a IA não casou                               |
| id_grupo_recorrencia           | TEXT                          | não         | —             | agrupa reuniões recorrentes                            |
| nome_grupo_recorrencia         | TEXT                          | não         | —             | título da série recorrente                             |
| lembrete_24h_enviado           | BOOLEAN                       | sim         | FALSE         | flag pro cron de lembrete                              |
| created_at                     | TIMESTAMPTZ                   | sim         | now()         |                                                        |
| updated_at                     | TIMESTAMPTZ                   | sim         | trigger       |                                                        |
| deleted_at                     | TIMESTAMPTZ                   | não         | —             | soft delete                                            |

**Relacionamentos:**
- Tem muitos: `reuniao_participantes`, `pendencias`, `comentarios_pendencias` (via pendência).
- Pertence a: `participantes` (facilitador), `tipos_reuniao` (tipo).

---

## reuniao_participantes (tabela de junção)

| Campo                | Tipo                          | Obrigatório | Default       | Descrição                                  |
|----------------------|-------------------------------|-------------|---------------|--------------------------------------------|
| id                   | UUID PK                       | sim         | gen_random_uuid() | id da junção                          |
| id_reuniao           | VARCHAR(20) → FK reunioes CASCADE | sim     | —             |                                            |
| participante_id      | VARCHAR(10) → FK participantes| sim         | —             |                                            |
| sequence_assinatura  | INTEGER                       | sim         | 2             | ordem em que assina o envelope             |

Constraint: `UNIQUE (id_reuniao, participante_id)`.

---

## pendencias

> Ação acordada numa reunião, com responsável e prazo. Origem: `003_create_pendencias.sql`.

| Campo               | Tipo                              | Obrigatório | Default     | Descrição                                |
|---------------------|-----------------------------------|-------------|-------------|------------------------------------------|
| id_acao             | VARCHAR(10) PK                    | sim         | auto (A001+)| identificador                            |
| id_reuniao          | VARCHAR(20) → FK reunioes CASCADE | sim         | —           | reunião de origem                        |
| descricao_acao      | TEXT                              | sim         | —           | o que foi acordado                       |
| responsavel_id      | VARCHAR(10) → FK participantes    | não         | —           | quem ficou de fazer                      |
| co_responsavel_id   | VARCHAR(10) → FK participantes    | não         | —           | parceiro (migration 011)                 |
| responsavel_nome    | TEXT                              | não         | —           | redundante pra histórico (legado)        |
| cargo               | TEXT                              | não         | —           | redundante                               |
| prazo               | DATE                              | não         | —           | data limite                              |
| meta_entregavel     | TEXT                              | não         | —           | critério de conclusão                    |
| status              | TEXT                              | sim         | 'PENDENTE'  | enum 6 estados                           |
| created_at          | TIMESTAMPTZ                       | sim         | now()       |                                          |
| updated_at          | TIMESTAMPTZ                       | sim         | trigger     |                                          |
| deleted_at          | TIMESTAMPTZ                       | não         | —           | soft delete                              |

**Estados de `status`:** PENDENTE · EM_PROGRESSO · CONCLUIDO · ATRASADO · CANCELADO · REPACTUADA

---

## comentarios_pendencias

> Comentários em pendências com menções @nome. Origem: `007_create_comentarios_pendencias.sql`.

| Campo        | Tipo                          | Obrigatório | Default            | Descrição                          |
|--------------|-------------------------------|-------------|--------------------|------------------------------------|
| id           | UUID PK                       | sim         | gen_random_uuid()  |                                    |
| id_acao      | VARCHAR(10) → FK pendencias CASCADE | sim   | —                  | pendência alvo                     |
| autor_id     | VARCHAR(10) → FK participantes| sim         | —                  | quem comentou                      |
| autor_nome   | TEXT                          | sim         | —                  | nome denormalizado pra histórico   |
| conteudo     | TEXT                          | sim         | —                  | texto do comentário                |
| mencoes      | VARCHAR(10)[]                 | sim         | '{}'               | IDs mencionados (@nome)            |
| created_at   | TIMESTAMPTZ                   | sim         | now()              |                                    |
| updated_at   | TIMESTAMPTZ                   | sim         | trigger            |                                    |

---

## notificacoes

> Notificação in-app para o sino do header. Origem: `008_create_notificacoes.sql`.

| Campo            | Tipo                              | Obrigatório | Default            | Descrição                          |
|------------------|-----------------------------------|-------------|--------------------|------------------------------------|
| id               | UUID PK                           | sim         | gen_random_uuid()  |                                    |
| destinatario_id  | VARCHAR(10) → FK participantes CASCADE | sim    | —                  | quem recebe                        |
| tipo             | TEXT                              | sim         | —                  | enum 4 valores (ver abaixo)        |
| titulo           | TEXT                              | sim         | —                  | título mostrado no sino            |
| mensagem         | TEXT                              | não         | —                  | corpo opcional                     |
| referencia_id    | VARCHAR(10)                       | não         | —                  | id_acao ou id_reuniao referenciado |
| lida             | BOOLEAN                           | sim         | FALSE              | flag de leitura                    |
| created_at       | TIMESTAMPTZ                       | sim         | now()              |                                    |

**Tipos:** MENCAO · STATUS_ALTERADO · COMENTARIO · PRAZO_PROXIMO

---

## user_preferences

> Preferências de notificação/email por usuário. Origem: `012_create_user_preferences.sql`.

| Campo            | Tipo                              | Obrigatório | Default                              | Descrição                          |
|------------------|-----------------------------------|-------------|--------------------------------------|------------------------------------|
| participante_id  | VARCHAR(10) PK → participantes CASCADE | sim    | —                                    | dono                               |
| notificacoes     | JSONB                             | sim         | `{mencao:true,prazo_proximo:true,...}` | flags de notificação in-app        |
| emails           | JSONB                             | sim         | `{validacao_ata:true,...}`           | flags de email                     |
| created_at       | TIMESTAMPTZ                       | sim         | now()                                |                                    |
| updated_at       | TIMESTAMPTZ                       | sim         | trigger                              |                                    |

---

## audit_log

> Rastreabilidade de ações administrativas (super_admin). Origem: `018_create_audit_log.sql`.

| Campo          | Tipo                                  | Obrigatório | Default            | Descrição                          |
|----------------|---------------------------------------|-------------|--------------------|------------------------------------|
| id             | UUID PK                               | sim         | gen_random_uuid()  |                                    |
| timestamp      | TIMESTAMPTZ                           | sim         | now()              |                                    |
| actor_id       | VARCHAR(10) → FK participantes SET NULL | não       | —                  | quem fez a ação                    |
| actor_email    | TEXT                                  | sim         | —                  | email no momento (snapshot)        |
| action         | TEXT                                  | sim         | —                  | create / update / delete / etc     |
| target_type    | TEXT                                  | sim         | —                  | participante / reuniao / pendencia |
| target_id      | TEXT                                  | sim         | —                  | id do alvo                         |
| metadata       | JSONB                                 | sim         | '{}'               | extras                             |
| ip_address     | INET                                  | não         | —                  |                                    |
| reason         | TEXT                                  | não         | —                  | motivo (obrigatório em DELETE)     |

---

## bulk_jobs

> Tracking de operações em massa (reenvios, reprocessamento). Origem: `019_create_bulk_jobs.sql`.

| Campo         | Tipo                                  | Obrigatório | Default            | Descrição                          |
|---------------|---------------------------------------|-------------|--------------------|------------------------------------|
| id            | UUID PK                               | sim         | gen_random_uuid()  |                                    |
| created_at    | TIMESTAMPTZ                           | sim         | now()              |                                    |
| updated_at    | TIMESTAMPTZ                           | sim         | trigger            |                                    |
| actor_id      | VARCHAR(10) → FK participantes SET NULL | não       | —                  | quem disparou                      |
| actor_email   | TEXT                                  | sim         | —                  |                                    |
| job_type      | TEXT                                  | sim         | —                  | reenviar_clicksign / reprocessar_ia/...|
| status        | TEXT                                  | sim         | 'pending'          | pending / running / completed / failed |
| target_ids    | JSONB                                 | sim         | —                  | lista de IDs alvo                  |
| total         | INTEGER                               | sim         | 0                  |                                    |
| sucessos      | INTEGER                               | sim         | 0                  |                                    |
| falhas        | JSONB                                 | sim         | '[]'               | `[{id, erro}]`                     |
| metadata      | JSONB                                 | sim         | '{}'               |                                    |
| reason        | TEXT                                  | não         | —                  | motivo livre                       |
| started_at    | TIMESTAMPTZ                           | não         | —                  |                                    |
| finished_at   | TIMESTAMPTZ                           | não         | —                  |                                    |

---

## setores · cargos · tipos_reuniao (tabelas de lookup)

Origem: `027_create_taxonomy_tables.sql`. Todas têm a mesma estrutura:

| Campo        | Tipo                | Obrigatório | Default            |
|--------------|---------------------|-------------|--------------------|
| id           | UUID PK             | sim         | gen_random_uuid()  |
| nome         | TEXT UNIQUE (case-insensitive) | sim | —              |
| ativo        | BOOLEAN             | sim         | TRUE               |
| created_at   | TIMESTAMPTZ         | sim         | now()              |
| updated_at   | TIMESTAMPTZ         | sim         | trigger            |

CRUD em `/admin/taxonomia`.

---

## Tabelas auxiliares / legadas

- **`tokens_validacao`** (`004_*`) — tokens para email verification.
- **`agendamentos_email`** (`003_*`) — fila de emails agendados.
- **`importacoes`** / **`historico_importacao`** (`016_*`, `020_*`) — tracking de importações de atas legadas.

---

## Enums no banco

- `user_role`: diretor · coordenador · gerente · presidente
- `status_ata` (TEXT, sem CHECK constraint): PROGRAMADA · PROCESSANDO · ERRO · AGUARDANDO_VALIDACAO · AGUARDANDO_ASSINATURA · ASSINADA · CANCELADA · CORRIGINDO · AGUARDANDO_RESOLUCAO · REVISADA · IMPORTADA
- `pendencia_status` (TEXT): PENDENTE · EM_PROGRESSO · CONCLUIDO · ATRASADO · CANCELADO · REPACTUADA
- `tipo_notificacao` (TEXT): MENCAO · STATUS_ALTERADO · COMENTARIO · PRAZO_PROXIMO
- `access_profile` (TEXT com CHECK): regular · secretaria · super_admin

---

**Resumo:** 12 tabelas vivas (após DROPs em 031, 032, 034). RLS habilitada em todas (`009_enable_rls.sql`). Soft delete em `participantes`, `reunioes`, `pendencias` (`030_add_soft_delete.sql`).
