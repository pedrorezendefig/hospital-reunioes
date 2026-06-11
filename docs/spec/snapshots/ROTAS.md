# ROTAS.md
<!-- gerado automaticamente por /snapshot — não editar -->
<!-- last_update: 2026-06-11T01:02-0300 -->

Endpoints HTTP expostos pelo backend FastAPI do Hospital Reuniões.

## auth (`app/routers/auth.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/auth/invite/{participante_id}` | Envia e-mail de redefinição de senha para um participante. | ❌ |
| GET | `/auth/me` | Retorna dados do usuário autenticado via JWT. | ✅ |

## comentarios (`app/routers/comentarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pendencias/{id_acao}/comentarios` | Lista comentários de uma pendência, ordenados do mais antigo ao mais recente. | ✅ |
| POST | `/pendencias/{id_acao}/comentarios` | Cria um comentário na pendência e gera notificações de menção. | ✅ |
| DELETE | `/pendencias/{id_acao}/comentarios/{comentario_id}` | Exclui um comentário. Apenas o autor pode excluir. | ✅ |

## health (`app/routers/health.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/health` | Health check | ❌ |

## importacao (`app/routers/importacao.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/reunioes/importacao/check-duplicata` | Consulta se uma ATA já foi importada. Chamado pelo frontend antes do upload completo. | ✅ |
| POST | `/reunioes/importacao/confirmar` | Persiste a ATA migrada. Recebe o PDF re-uploadado + JSON editado no preview. | ✅ |
| GET | `/reunioes/importacao/historico` | Retorna as últimas ATAs importadas (status_ata='MIGRADA'), mais recentes primeiro. | ✅ |
| POST | `/reunioes/importacao/preparar` | Parseia PDF, chama IA e matcher, retorna preview (stateless — não persiste). | ✅ |

## admin (`app/routers/admin/legacy.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/admin/email/status` | Get email status | ❌ |
| POST | `/admin/email/test` | Send test email | ❌ |
| GET | `/admin/integracoes` | Get integracoes | ❌ |
| POST | `/admin/integracoes/{nome}/test` | Test integracao | ❌ |

## notas (`app/routers/notas.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/notas/transcrever` | Comando por voz da Nota (issue #35): recebe o áudio ditado e devolve o | ✅ |
| DELETE | `/notas/{id_nota}` | Arquiva uma Nota — soft-delete via `deleted_at`, sem hard-delete. | ✅ |
| GET | `/notas/{id_nota}` | Abre uma Nota pelo id (se visível ao usuário). | ✅ |
| PATCH | `/notas/{id_nota}` | Edita o corpo de uma Nota — autor ou Super admin. | ✅ |
| POST | `/notas/{id_nota}/extrair-pendencias` | A mágica central da Nota (issue #34): a IA propõe Pendências a partir | ✅ |
| GET | `/notas/{id_nota}/participantes` | Roster da Nota (issue #34): quem entrou na conversa. Visível a quem vê a Nota. | ✅ |
| PUT | `/notas/{id_nota}/participantes` | Define o roster da Nota (replace-all): cada Participante é um Colaborador | ✅ |
| POST | `/notas/{id_nota}/pendencias` | Adiciona Pendências manuais a uma Nota (issue #33). | ✅ |

## notificacoes (`app/routers/notificacoes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/notificacoes/count` | Retorna a contagem de notificações não lidas. | ✅ |
| PATCH | `/notificacoes/ler-todas` | Marca todas as notificações do usuário como lidas. | ✅ |
| PATCH | `/notificacoes/{notificacao_id}/lida` | Marca uma notificação como lida. | ✅ |

## participantes (`app/routers/participantes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/participantes/cargos` | Retorna a lista canônica de cargos do organograma hospitalar. | ✅ |
| GET | `/participantes/facilitadores` | Lista participantes que já foram facilitadores de alguma reunião viva. | ✅ |
| GET | `/participantes/me` | Retorna o participante do usuario autenticado. | ✅ |
| GET | `/participantes/setores` | Retorna a lista canonica de setores ativos. | ✅ |
| DELETE | `/participantes/{participante_id}` | Soft delete participante | ❌ |
| GET | `/participantes/{participante_id}` | Get participante | ✅ |
| PATCH | `/participantes/{participante_id}` | Update participante | ✅ |

## pendencias (`app/routers/pendencias.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/pendencias/minhas` | Lista apenas as pendências atreladas diretamente ao usuário autenticado. | ✅ |
| GET | `/pendencias/stats` | Retorna contadores de pendências agrupados por status para o dashboard. | ✅ |
| GET | `/pendencias/{id_acao}` | Retorna uma pendência específica. | ✅ |
| PATCH | `/pendencias/{id_acao}` | Atualiza campos de uma pendência. Quando concluída, incrementa acoes_concluidas na reunião. | ✅ |
| DELETE | `/pendencias/{id_acao}/force` | Super admin only: deleta uma pendencia em qualquer status. Motivo obrigatorio. | ✅ |
| PATCH | `/pendencias/{id_acao}/force` | Super admin only: edita qualquer campo da pendencia em qualquer status. | ✅ |

## perfil (`app/routers/perfil.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| GET | `/perfil/stats` | Get stats | ✅ |

## reunioes (`app/routers/reunioes.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/reunioes/agendar` | Cria uma reunião programada no calendário (sem transcrição). | ✅ |
| GET | `/reunioes/calendario` | Lista reuniões para exibição no calendário, com participantes vinculados. | ✅ |
| DELETE | `/reunioes/grupo/{id_grupo_recorrencia}` | Deleta permanentemente todas as reuniões PROGRAMADAS ou em ERRO de um mesmo grupo de recorrência. | ❌ |
| POST | `/reunioes/upload-transcricao` | Upload transcricao | ✅ |
| DELETE | `/reunioes/{id_reuniao}` | Deleta permanentemente uma reunião PROGRAMADA ou em ERRO. | ✅ |
| GET | `/reunioes/{id_reuniao}` | Get reuniao | ✅ |
| PATCH | `/reunioes/{id_reuniao}` | Edita campos de uma reunião PROGRAMADA. | ✅ |
| POST | `/reunioes/{id_reuniao}/anexar-transcricao` | Anexa uma transcrição a uma reunião PROGRAMADA existente e dispara o pipeline de IA. | ✅ |
| POST | `/reunioes/{id_reuniao}/aprovar` | Aprovar reuniao | ✅ |
| POST | `/reunioes/{id_reuniao}/aprovar-sem-assinatura` | Finaliza a Ata sem assinatura digital: cria as Pendências na hora e leva a | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-guiada/chat` | Chat da Ata Guiada — stateless, síncrono, sem pipeline. Recebe o rascunho | ✅ |
| POST | `/reunioes/{id_reuniao}/ata-guiada/concluir` | Persiste a Ata Guiada: grava o `json_ata` enxuto (resumo + quadro), marca | ✅ |
| POST | `/reunioes/{id_reuniao}/chat-correcao` | Chat conversacional para correção de ATA. Leve, síncrono, sem pipeline. | ✅ |
| POST | `/reunioes/{id_reuniao}/corrigir` | Corrigir reuniao | ✅ |
| DELETE | `/reunioes/{id_reuniao}/force` | Super admin only: deleta uma reuniao em QUALQUER status. Motivo obrigatorio. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/force` | Super admin only: edita qualquer campo de uma reuniao em qualquer status. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/force-status` | Super admin only: forca qualquer transicao de status (mesmo invalidas). Motivo obrigatorio. | ✅ |
| POST | `/reunioes/{id_reuniao}/participantes` | Adiciona participantes a uma reunião PROGRAMADA. | ✅ |
| DELETE | `/reunioes/{id_reuniao}/participantes/{participante_id}` | Remove um participante de uma reunião PROGRAMADA. | ✅ |
| POST | `/reunioes/{id_reuniao}/pular-resolucao` | Ignora participantes não reconhecidos e retoma o pipeline sem cadastrá-los. | ✅ |
| PATCH | `/reunioes/{id_reuniao}/quadro-atribuicoes/{index}` | Edita um item do `json_ata.quadro_atribuicoes` antes da liberação de pendências. | ✅ |
| POST | `/reunioes/{id_reuniao}/reprocessar` | Reprocessar reuniao | ✅ |
| POST | `/reunioes/{id_reuniao}/resolver-participantes` | Resolve participantes não reconhecidos pela IA e retoma o pipeline. | ✅ |
| GET | `/reunioes/{id_reuniao}/signatarios/status` | Retorna lista live de signatarios do ClickSign pra essa reuniao. | ✅ |
| POST | `/reunioes/{id_reuniao}/signatarios/{signer_id}/lembrar` | Reenvia o email de assinatura para um signatário pendente. | ✅ |
| POST | `/reunioes/{id_reuniao}/transferir-facilitador` | Super admin troca o facilitador de uma reuniao por outro super admin. | ✅ |

## admin (`app/routers/admin/super_admins.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/admin/super-admins/{participante_id}/demote` | Rebaixa um participante de super admin. Motivo obrigatorio. Loga em audit_log. | ✅ |
| POST | `/admin/super-admins/{participante_id}/promote` | Promove um participante a super admin. Motivo obrigatorio. Loga em audit_log. | ✅ |

## admin (`app/routers/admin/usuarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/admin/usuarios/{externo_id}/merge` | Mescla participante externo com interno existente via RPC atomica. | ✅ |
| PATCH | `/admin/usuarios/{externo_id}/promote` | Promove participante externo a interno. | ✅ |
| DELETE | `/admin/usuarios/{participante_id}` | Hard delete. Motivo obrigatorio. Bloqueia auto-delete. | ✅ |
| GET | `/admin/usuarios/{participante_id}` | Detalhe + ultimos 20 audit logs em que o participante e actor ou target. | ✅ |
| PATCH | `/admin/usuarios/{participante_id}` | Atualizacao parcial. Loga EDIT_USUARIO com antes/depois por campo. | ✅ |
| POST | `/admin/usuarios/{participante_id}/grant-super-admin` | Concede flag is_super_admin=true. Motivo obrigatorio. | ✅ |
| POST | `/admin/usuarios/{participante_id}/reset-password` | Reseta senha no Supabase Auth. Motivo obrigatorio. | ✅ |
| POST | `/admin/usuarios/{participante_id}/revoke-super-admin` | Revoga flag is_super_admin=false. Motivo obrigatorio. | ✅ |

## admin (`app/routers/admin/utilitarios.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/admin/utilitarios/converter-markdown` | Converte um PDF ou DOCX em Markdown localmente, sem consumo de IA. | ✅ |

## webhooks (`app/routers/webhooks.py`)

| Método | Rota | O que faz | Auth |
|--------|------|-----------|------|
| POST | `/webhooks/clicksign` | Recebe notificações da ClickSign sobre fechamento de documentos. | ❌ |

---

**Totais:** 77 endpoints em 15 routers · 88% exigem auth.
