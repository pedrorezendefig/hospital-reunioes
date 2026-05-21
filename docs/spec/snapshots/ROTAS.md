# ROTAS.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-05-21T15:58-03:00 -->

Endpoints HTTP expostos pelo backend FastAPI do Hospital Reuniões. Base path: `https://api.hospitalsaomatheus.cloud`.

## auth (`app/routers/auth.py`)

| Método | Rota                          | O que faz                                          | Auth |
|--------|-------------------------------|----------------------------------------------------|------|
| GET    | /auth/me                      | Retorna dados do usuário autenticado (JWT)         | ✅   |
| POST   | /auth/invite/{participante_id} | Envia email reset de senha (diretor/coordenador)   | ✅   |

## participantes (`app/routers/participantes.py`)

| Método | Rota                                       | O que faz                                          | Auth |
|--------|--------------------------------------------|----------------------------------------------------|------|
| GET    | /participantes                             | Lista participantes com filtros                    | ✅   |
| GET    | /participantes/cargos                      | Lista canônica de cargos                           | ✅   |
| GET    | /participantes/setores                     | Lista de setores ativos                            | ✅   |
| GET    | /participantes/facilitadores               | Lista de quem já foi facilitador                   | ✅   |
| GET    | /participantes/me                          | Participante do usuário autenticado                | ✅   |
| GET    | /participantes/{id}                        | Detalhe de um participante                         | ✅   |
| POST   | /participantes                             | Cria novo participante                             | ✅   |
| PATCH  | /participantes/{id}                        | Atualiza participante                              | ✅   |
| DELETE | /participantes/{id}                        | Soft delete de participante                        | ✅   |

## reunioes (`app/routers/reunioes.py`)

| Método | Rota                                                  | O que faz                                            | Auth |
|--------|-------------------------------------------------------|------------------------------------------------------|------|
| GET    | /reunioes                                             | Lista com filtros + paginação                        | ✅   |
| GET    | /reunioes/calendario                                  | Lista para calendário com participantes              | ✅   |
| GET    | /reunioes/{id}                                        | Detalhe da reunião                                   | ✅   |
| POST   | /reunioes/agendar                                     | Cria reunião PROGRAMADA                              | ✅   |
| PATCH  | /reunioes/{id}                                        | Edita campos de PROGRAMADA                           | ✅   |
| DELETE | /reunioes/{id}                                        | Deleta PROGRAMADA ou ERRO                            | ✅   |
| DELETE | /reunioes/grupo/{id_grupo_recorrencia}                | Deleta grupo de recorrência inteiro                  | ✅   |
| POST   | /reunioes/{id}/participantes                          | Adiciona participantes                               | ✅   |
| DELETE | /reunioes/{id}/participantes/{participante_id}        | Remove participante                                  | ✅   |
| POST   | /reunioes/{id}/anexar-transcricao                     | Anexa transcrição e dispara pipeline IA              | ✅   |
| POST   | /reunioes/upload-transcricao                          | Upload de arquivo de áudio                           | ✅   |
| POST   | /reunioes/{id}/resolver-participantes                 | Resolve nomes não reconhecidos pela IA               | ✅   |
| POST   | /reunioes/{id}/aprovar                                | Aprova ata (vai pra assinatura)                      | ✅   |
| POST   | /reunioes/{id}/aprovar-bypass                         | Aprova sem validação (debug/migrações)               | ✅   |
| POST   | /reunioes/{id}/chat-correcao                          | Chat iterativo de correção com IA                    | ✅   |
| POST   | /reunioes/{id}/corrigir                               | Aplica correções à ata                               | ✅   |
| POST   | /reunioes/{id}/pular-resolucao                        | Pula fase de resolução de nomes                      | ✅   |
| POST   | /reunioes/{id}/reprocessar                            | Reprocessa pipeline de IA                            | ✅   |
| POST   | /reunioes/{id}/simular-assinatura                     | Preview de envelope de assinatura                    | ✅   |
| POST   | /reunioes/{id}/transferir-facilitador                 | Transfere facilitador para outro participante        | ✅   |
| PATCH  | /reunioes/{id}/force                                  | Force edit (admin)                                   | 🔐   |
| PATCH  | /reunioes/{id}/force-status                           | Force status change (admin)                          | 🔐   |
| DELETE | /reunioes/{id}/force                                  | Force delete (admin)                                 | 🔐   |

## pendencias (`app/routers/pendencias.py`)

| Método | Rota                                  | O que faz                                       | Auth |
|--------|---------------------------------------|-------------------------------------------------|------|
| GET    | /pendencias                           | Lista com filtros                               | ✅   |
| GET    | /pendencias/stats                     | Contadores agrupados por status                 | ✅   |
| GET    | /pendencias/minhas                    | Lista do usuário logado                         | ✅   |
| GET    | /pendencias/{id_acao}                 | Detalhe da pendência                            | ✅   |
| PATCH  | /pendencias/{id_acao}                 | Atualiza status / responsável                   | ✅   |
| DELETE | /pendencias/{id_acao}                 | Soft delete                                     | ✅   |
| PATCH  | /pendencias/{id_acao}/force           | Force update (admin)                            | 🔐   |
| DELETE | /pendencias/{id_acao}/force           | Force delete (admin)                            | 🔐   |

## comentarios (`app/routers/comentarios.py`)

| Método | Rota                                                   | O que faz                                  | Auth |
|--------|--------------------------------------------------------|--------------------------------------------|------|
| GET    | /pendencias/{id_acao}/comentarios                      | Lista comentários                          | ✅   |
| POST   | /pendencias/{id_acao}/comentarios                      | Cria comentário (extrai menções @nome)     | ✅   |
| DELETE | /pendencias/{id_acao}/comentarios/{comentario_id}      | Deleta (apenas autor)                      | ✅   |

## notificacoes (`app/routers/notificacoes.py`)

| Método | Rota                                | O que faz                                | Auth |
|--------|-------------------------------------|------------------------------------------|------|
| GET    | /notificacoes                       | Lista (filtro `lida`)                    | ✅   |
| GET    | /notificacoes/count                 | Contagem de não-lidas                    | ✅   |
| PATCH  | /notificacoes/{id}/lida             | Marca como lida                          | ✅   |
| PATCH  | /notificacoes/ler-todas             | Marca todas como lidas                   | ✅   |

## configuracoes (`app/routers/configuracoes.py`)

| Método | Rota                  | O que faz                                          | Auth |
|--------|-----------------------|----------------------------------------------------|------|
| GET    | /configuracoes        | Preferências de notificação e email do usuário     | ✅   |
| PATCH  | /configuracoes        | Atualiza preferências                              | ✅   |

## perfil (`app/routers/perfil.py`)

| Método | Rota            | O que faz                                                       | Auth |
|--------|-----------------|-----------------------------------------------------------------|------|
| GET    | /perfil/stats   | Stats pessoais (reuniões, pendências ativas, % no prazo)        | ✅   |

## admin/usuarios (`app/routers/admin_usuarios.py`)

| Método | Rota                                          | O que faz                                                | Auth |
|--------|-----------------------------------------------|----------------------------------------------------------|------|
| GET    | /admin/usuarios                               | Lista participantes + audit logs                         | 🔐   |
| GET    | /admin/usuarios/{id}                          | Detalhe + últimos 20 logs                                | 🔐   |
| POST   | /admin/usuarios                               | Cria participante com provisionamento Supabase Auth      | 🔐   |
| PATCH  | /admin/usuarios/{id}                          | Atualiza participante                                    | 🔐   |
| DELETE | /admin/usuarios/{id}                          | Hard delete (motivo obrigatório)                         | 🔐   |
| POST   | /admin/usuarios/{id}/reset-password           | Reseta senha no Supabase Auth                            | 🔐   |
| POST   | /admin/usuarios/merge-externo                 | Merge participante externo com interno                   | 🔐   |
| POST   | /admin/usuarios/promote-externo               | Promove externo para interno                             | 🔐   |

## admin/super_admins (`app/routers/admin_super_admins.py`)

CRUD de super admins. Apenas Pedro hoje.

## admin/taxonomia (`app/routers/admin_taxonomia.py`)

CRUD de tabelas de lookup: `setores`, `cargos`, `tipos_reuniao`.

## admin/legacy (`app/routers/admin_legacy.py`)

Endpoints de compatibilidade/migração de dados antigos.

## importacao (`app/routers/importacao.py`)

| Método | Rota                       | O que faz                              | Auth |
|--------|----------------------------|----------------------------------------|------|
| GET    | /importacao/historico      | Histórico de importações               | ✅   |
| POST   | /importacao/preparar       | Preview de importação de ata legada    | ✅   |
| POST   | /importacao/confirmar      | Confirma importação                    | ✅   |

## webhooks (`app/routers/webhooks.py`)

| Método | Rota                                  | O que faz                                  | Auth          |
|--------|---------------------------------------|--------------------------------------------|---------------|
| POST   | /webhooks/clicksign                   | Webhook de assinatura (HMAC valida)        | 🔐 HMAC       |
| POST   | /webhooks/aprovar-bypass-todas        | Bulk approve bypass (debug)                | 🔐 super_admin|

## health (`app/routers/health.py`)

| Método | Rota              | O que faz                                                 | Auth |
|--------|-------------------|-----------------------------------------------------------|------|
| GET    | /api/health       | Health check (retorna `status` e `db` no body)            | ❌   |

---

**Legenda:** ✅ requer JWT do Supabase · 🔐 requer JWT + perfil específico (super_admin/diretor) · ❌ público

**Totais aproximados:** ~70 endpoints em 13 routers. Detalhamento exato via `/snapshot` quando rodado.
