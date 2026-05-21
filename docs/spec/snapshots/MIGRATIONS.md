# MIGRATIONS.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Ordem cronológica das migrations do Postgres (Supabase self-hosted) do Hospital Reuniões. Mais antigas no topo. Aplicadas pelo `/deploy ship` quando rodadas em sequência.

| # | Arquivo                                          | Resumo                                                                    | C | A | I | D |
|---|--------------------------------------------------|---------------------------------------------------------------------------|---|---|---|---|
| 1 | `001_create_participantes.sql`                   | Tabela `participantes` + enum `user_role` + função gerador de IDs         | 1 | 0 | 1 | 0 |
| 2 | `002_create_reunioes.sql`                        | Tabelas `reunioes` + `reuniao_participantes` + indexes principais         | 2 | 0 | 3 | 0 |
| 3 | `003_create_pendencias.sql`                      | Tabelas `pendencias` + `agendamentos_email`                               | 2 | 0 | 1 | 0 |
| 4 | `004_create_tokens_validacao.sql`                | Tabela `tokens_validacao` para verificação de email                       | 1 | 0 | 0 | 0 |
| 5 | `005_create_signup_requests.sql`                 | Tabela `signup_requests` (depois removida em 031)                         | 1 | 0 | 0 | 0 |
| 6 | `006_create_storage_buckets.sql`                 | Buckets de storage: `audios`, `transcricoes`, `atas-pdf`                  | 0 | 0 | 0 | 0 |
| 7 | `007_create_comentarios_pendencias.sql`          | Tabela `comentarios_pendencias` com array `mencoes`                       | 1 | 0 | 1 | 0 |
| 8 | `008_create_notificacoes.sql`                    | Tabela `notificacoes` (MENCAO, STATUS_ALTERADO, COMENTARIO, PRAZO)        | 1 | 0 | 1 | 0 |
| 9 | `009_enable_rls.sql`                             | Habilita RLS em todas as tabelas + policies básicas                       | 0 | 0 | 0 | 0 |
| 10| `010_atomic_operations.sql`                      | Stored procedures para operações atômicas (concluir, repactuar)           | 0 | 0 | 0 | 0 |
| 11| `011_add_responsavel_atribuido.sql`              | Adiciona `co_responsavel_id` em `pendencias`                              | 0 | 1 | 0 | 0 |
| 12| `012_create_user_preferences.sql`                | Tabela `user_preferences` (notificacoes/emails JSONB)                     | 1 | 0 | 0 | 0 |
| 13| `013_add_role_presidente.sql`                    | Adiciona valor `presidente` ao enum `user_role`                           | 0 | 0 | 0 | 0 |
| 14| `014_add_externo_co_responsavel.sql`             | Adiciona `is_externo` em `participantes`                                  | 0 | 2 | 0 | 0 |
| 15| `015_remove_email_triggers.sql`                  | Remove triggers de email (lógica movida pro app)                          | 0 | 0 | 0 | 0 |
| 16| `016_importacao_ata_legada.sql`                  | Tabela `importacoes` para tracking de atas importadas                     | 1 | 0 | 0 | 0 |
| 17| `017_add_super_admin.sql`                        | Adiciona `is_super_admin` e `access_profile` em `participantes`           | 0 | 2 | 0 | 0 |
| 18| `018_create_audit_log.sql`                       | Tabela `audit_log` para rastreamento de ações administrativas             | 1 | 0 | 1 | 0 |
| 19| `019_create_bulk_jobs.sql`                       | Tabela `bulk_jobs` para tracking de operações em massa                    | 1 | 0 | 1 | 0 |
| 20| `020_historico_importacao.sql`                   | Tabela `historico_importacao` com status granular                         | 1 | 0 | 0 | 0 |
| 23| `023_enable_rls_audit_bulk.sql`                  | Habilita RLS em `audit_log` e `bulk_jobs`                                 | 0 | 0 | 0 | 0 |
| 24| `024_rpc_confirmar_importacao.sql`               | Procedure RPC para confirmar importação                                   | 0 | 0 | 0 | 0 |
| 25| `025_expand_id_reuniao.sql`                      | `id_reuniao` VARCHAR(15) → VARCHAR(20)                                    | 0 | 1 | 0 | 0 |
| 26| `026_email_nullable_externo_stub.sql`            | `email` nullable para participantes externos                              | 0 | 1 | 0 | 0 |
| 27| `027_create_taxonomy_tables.sql`                 | Tabelas `setores`, `cargos`, `tipos_reuniao` + seed inicial               | 3 | 0 | 0 | 0 |
| 28| `028_add_taxonomy_fks.sql`                       | FKs de `participantes`/`reunioes` pras taxonomy tables                    | 0 | 2 | 0 | 0 |
| 29| `029_rpc_merge_participante_externo.sql`         | Procedure RPC para mergear participante externo com interno               | 0 | 0 | 0 | 0 |
| 30| `030_add_soft_delete.sql`                        | `deleted_at` em `participantes`, `reunioes`, `pendencias`                 | 0 | 3 | 0 | 0 |
| 31| `031_drop_signup_requests.sql`                   | DROP da tabela `signup_requests` (substituída por admin/usuarios)         | 0 | 0 | 0 | 1 |
| 32| `032_drop_local_reuniao.sql`                     | DROP da coluna `local` em `reunioes` (em desuso)                          | 0 | 1 | 0 | 0 |
| 34| `034_drop_facilitador_prompts.sql`               | DROP da tabela `facilitador_prompts` (prompts movidos pro código)         | 0 | 0 | 0 | 1 |
| 35| `035_add_lembrete_24h_reunioes.sql`              | Adiciona `lembrete_24h_enviado` em `reunioes` pro cron job                | 0 | 1 | 0 | 0 |
| 36| `036_add_access_profile.sql`                     | Adiciona CHECK constraint em `access_profile`                             | 0 | 1 | 0 | 0 |
| 37| `037_cargo_nullable_for_secretaria.sql`          | `cargo` nullable para perfil secretaria                                   | 0 | 1 | 0 | 0 |
| 38| `038_fk_indexes.sql`                             | Adiciona indexes em FKs frequentes                                        | 0 | 0 | 3 | 0 |

**Legenda:**
- **C** = `CREATE TABLE` statements
- **A** = `ALTER TABLE` statements
- **I** = `CREATE INDEX` statements
- **D** = `DROP TABLE` ou `DROP COLUMN` statements

**Totalizadores:**
- 38 migrations no total · 14 tabelas operacionais vivas (após DROPs em 031, 032, 034)
- Última migration: `038_fk_indexes.sql`
- Gaps numéricos (21, 22, 33): migrations criadas e revertidas durante desenvolvimento

**Gates ativos:**
- `fk_index_warning` (warn): toda FK nova precisa ter index correspondente — ver `docs/spec/deploy/project.json`.
- Migrations destrutivas (DROP/TRUNCATE/DELETE-sem-WHERE) exigem confirmação explícita no `/deploy ship`.
