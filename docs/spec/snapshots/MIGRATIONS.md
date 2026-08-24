# MIGRATIONS.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-08-24T12:29-0300 -->

Ordem cronológica das migrations do Postgres do Hospital Reuniões.

| # | Arquivo | Resumo | C | A | I | D |
|---|---------|--------|---|---|---|---|
| 1 | `001_create_participantes.sql` | Tabela participantes | 1 | 0 | 4 | 0 |
| 2 | `002_create_reunioes.sql` | Tabelas reunioes e reuniao_participantes | 2 | 0 | 7 | 0 |
| 3 | `003_create_pendencias.sql` | Tabelas pendencias e agendamentos_email | 2 | 0 | 5 | 0 |
| 4 | `004_create_tokens_validacao.sql` | Tabela tokens_validacao | 1 | 0 | 2 | 0 |
| 5 | `005_create_signup_requests.sql` | Tabela signup_requests | 1 | 0 | 3 | 0 |
| 6 | `006_create_storage_buckets.sql` | Criação de Buckets no Storage (PRIVADOS) | 0 | 0 | 0 | 0 |
| 7 | `007_create_comentarios_pendencias.sql` | Tabela comentarios_pendencias | 1 | 0 | 3 | 0 |
| 8 | `008_create_notificacoes.sql` | Tabela notificacoes | 1 | 0 | 3 | 0 |
| 9 | `009_enable_rls.sql` | Habilitar RLS em todas as tabelas (default-deny) | 0 | 0 | 0 | 0 |
| 10 | `010_atomic_operations.sql` | RPCs atômicas para acoes_concluidas | 0 | 0 | 0 | 0 |
| 11 | `011_add_responsavel_atribuido.sql` | Adicionar RESPONSAVEL_ATRIBUIDO ao CHECK de notificacoes.tipo | 0 | 0 | 0 | 0 |
| 12 | `012_create_user_preferences.sql` | Tabela de preferências do usuário (notificações e emails) | 1 | 0 | 0 | 0 |
| 13 | `013_add_role_presidente.sql` | Adicionar role presidente ao enum user_role | 0 | 0 | 0 | 0 |
| 14 | `014_add_externo_co_responsavel.sql` | Flag is_externo em participantes + | 0 | 3 | 1 | 0 |
| 15 | `015_remove_email_triggers.sql` | remove infraestrutura dos triggers de email 4-8 | 0 | 0 | 0 | 2 |
| 16 | `016_importacao_ata_legada.sql` | Importação de ATAs antigas (migradas do sistema antigo) | 0 | 1 | 2 | 0 |
| 17 | `017_add_super_admin.sql` | Super admin layer: flag + seed 6 pessoas + cargo Pedro = Engenheiro de IA | 0 | 1 | 1 | 0 |
| 18 | `018_create_audit_log.sql` | Audit log de acoes destrutivas / administrativas | 1 | 0 | 4 | 0 |
| 19 | `019_create_bulk_jobs.sql` | Bulk jobs: tracking de acoes em massa administrativas executadas em background. | 1 | 0 | 3 | 0 |
| 20 | `020_historico_importacao.sql` | Histórico de importação de ATAs migradas | 0 | 1 | 1 | 0 |
| 23 | `023_enable_rls_audit_bulk.sql` | 023_enable_rls_audit_bulk.sql | 0 | 0 | 0 | 0 |
| 24 | `024_rpc_confirmar_importacao.sql` | RPC atômica para /importacao/confirmar | 0 | 0 | 0 | 0 |
| 25 | `025_expand_id_reuniao.sql` | 025_expand_id_reuniao.sql | 0 | 0 | 0 | 0 |
| 26 | `026_email_nullable_externo_stub.sql` | participantes.email pode ser NULL | 0 | 0 | 0 | 0 |
| 27 | `027_create_taxonomy_tables.sql` | Tabelas de taxonomia (setores, cargos, tipos_reuniao) | 3 | 0 | 3 | 1 |
| 28 | `028_add_taxonomy_fks.sql` | FKs de taxonomia em participantes e reunioes | 0 | 2 | 0 | 1 |
| 29 | `029_rpc_merge_participante_externo.sql` | RPC merge_participante_externo | 0 | 0 | 0 | 0 |
| 30 | `030_add_soft_delete.sql` | Soft delete em reunioes e pendencias | 0 | 2 | 2 | 1 |
| 31 | `031_drop_signup_requests.sql` | Drop signup_requests table — auto-cadastro publico via codigo passe foi removido | 0 | 0 | 0 | 1 |
| 32 | `032_drop_local_reuniao.sql` | Remove coluna `local` da tabela reunioes | 0 | 1 | 0 | 1 |
| 34 | `034_drop_facilitador_prompts.sql` | limpa tabelas experimentais de prompts | 0 | 0 | 0 | 2 |
| 35 | `035_add_lembrete_24h_reunioes.sql` | Coluna que marca quando o lembrete de 24h antes foi enviado. | 0 | 1 | 1 | 0 |
| 36 | `036_add_access_profile.sql` | Perfil de acesso (access_profile) + criada_por em reunioes | 0 | 2 | 2 | 0 |
| 37 | `037_cargo_nullable_for_secretaria.sql` | cargo nullable pra suportar perfil secretária | 0 | 0 | 0 | 0 |
| 38 | `038_fk_indexes.sql` | Indexes em foreign keys legadas | 0 | 0 | 5 | 0 |
| 39 | `039_add_envelope_id_clicksign.sql` | 039_add_envelope_id_clicksign.sql | 0 | 1 | 0 | 0 |
| 40 | `040_add_aprovada_status.sql` | Estado terminal APROVADA (aprovação sem ClickSign) | 0 | 0 | 0 | 0 |
| 41 | `041_create_notas.sql` | Tabela notas (entidade Nota — issue #32, ADR 0004) | 1 | 0 | 2 | 1 |
| 42 | `042_add_id_nota_pendencias.sql` | Pendência com origem Nota (issue #33, ADR 0004) | 0 | 2 | 1 | 1 |
| 43 | `043_create_nota_participantes.sql` | Roster da Nota (issue #34, ADR 0004) | 1 | 0 | 2 | 1 |
| 44 | `044_add_metodo_geracao_reunioes.sql` | metodo_geracao em reunioes (issue #48, ADR 0005) | 0 | 2 | 0 | 1 |
| 45 | `045_pops_fundacao_acesso.sql` | POPs L1 — fundação de acesso (issue #81, ADR 0007) | 2 | 1 | 4 | 0 |
| 46 | `046_pops_criar_pop.sql` | POPs L1 — criar POP (issue #82, PRD #76) | 2 | 0 | 4 | 0 |
| 47 | `047_pops_elaboracao.sql` | POPs L1 — elaboração (issue #83, PRD #76) | 0 | 1 | 0 | 0 |
| 48 | `048_pops_revisao_validacao.sql` | POPs L1 — revisão e validação (issue #85, PRD #76) | 1 | 0 | 1 | 0 |
| 49 | `049_pops_materiais_referencia.sql` | POPs L1 — Materiais de referência (issue #84, PRD #76) | 1 | 0 | 1 | 0 |
| 50 | `050_pops_clicksign_publicacao.sql` | POPs L1 — ClickSign e publicação (issue #87, PRD #76) | 0 | 1 | 1 | 0 |
| 51 | `051_pops_enable_rls.sql` | POPs L1 — RLS default-deny nas tabelas 045–048 (issue #112) | 0 | 0 | 0 | 0 |
| 52 | `052_descontinuar_notas.sql` | Descontinuar Notas (issue #127, ADR 0011) | 0 | 1 | 0 | 3 |
| 53 | `053_pops_natureza_setor.sql` | Natureza do Setor no contexto POPs (issue #170, ADR 0018) | 0 | 1 | 0 | 0 |
| 55 | `055_pops_natureza_drop.sql` | Remove a Natureza do Setor (issue #189, ADR 0021) | 0 | 1 | 0 | 2 |
| 56 | `056_add_falha_envio_assinatura.sql` | Issue #193: envio para assinatura falhava em silencio. | 0 | 1 | 0 | 0 |
| 57 | `057_registro_aceites_incremental.sql` | Registro de Aceites + nascimento incremental (ADR 0030, issue #274) | 1 | 1 | 6 | 0 |
| 58 | `058_finalizacao_envelope_contagem.sql` | contagem de assinaturas na finalizacao do Envelope | 0 | 1 | 0 | 0 |
| 59 | `059_modo_interno_reuniao.sql` | flag do modo interno da Reuniao (ADR 0030, issue #276) | 0 | 1 | 0 | 0 |
| 60 | `060_aceite_interno_tokens.sql` | tokens do Aceite interno + notificacao in-app (ADR 0030, issue #277) | 1 | 0 | 3 | 0 |
| 61 | `061_consultas_particulares_ana.sql` | consultas particulares (Dados do Atendimento da Ana) | 1 | 0 | 0 | 0 |
| 62 | `062_exames_cirurgias_convenios_ana.sql` | exames, cirurgias e convênios (Dados do Atendimento da Ana) | 3 | 0 | 0 | 0 |
| 63 | `063_ouvidoria_protocolos_ana.sql` | protocolos de ouvidoria (Dados do Atendimento da Ana) | 0 | 0 | 0 | 0 |
| 64 | `064_ouvidoria_manifestacao.sql` | Manifestacao nasce (issue #320, ADR 0034) | 2 | 2 | 3 | 0 |

**Legenda:** C = CREATE TABLE · A = ALTER TABLE · I = CREATE INDEX · D = DROP.
**Total:** 60 migrations.
