# Perfil Secretária via `access_profile` enum

## Plano

### Contexto

Hoje o RBAC tem duas camadas: `role` (cargo hospitalar: diretor/presidente/gerente/coordenador) e `is_super_admin` (flag boolean, migration 017, hardcoded por email pra 6 pessoas). Visibilidade é filtrada por `get_allowed_reuniao_ids()` em `backend/app/dependencies.py:128`. Super_admin vê tudo; demais só veem reuniões em que aparecem em `reuniao_participantes`.

Precisamos adicionar um terceiro perfil: **Secretária**. Função exclusivamente operacional. Marca reuniões, aloca facilitador, escreve pauta/objetivo, define participantes. Não vê pendências, atas, transcrições nem conteúdo de reuniões alheias. Mutuamente exclusiva com super_admin.

Como `is_super_admin` e `is_secretaria` seriam exclusivos, modelamos com **enum único** `access_profile` (`regular | secretaria | super_admin`). Mutuamente exclusivo por construção. Migração em fases, sem quebrar prod.

### Escopo (decisões consolidadas em brainstorm)

| Decisão | Escolha |
|---|---|
| Modelagem | Enum único `access_profile` (substitui `is_super_admin` na fase 2). |
| Visibilidade da secretária | Só vê reuniões que ela criou e que ainda não aconteceram. |
| Form de criação | Preparação completa: data/hora/título + facilitador + participantes + pauta/objetivo. |
| Tela de entrada | Rota dedicada `/secretaria` + acesso ao `/calendario` (redacted). |
| Cadastro | Via `/admin/usuarios` (radio "Perfil de acesso"). |
| Notificação | Email automático pro facilitador alocado. |
| Calendário pra secretária | Todas as reuniões em metadata (data/hora/título/facilitador). Sem pauta/participantes/conteúdo das alheias. |

### Passos

1. **Migration 036_add_access_profile.sql**
   - `participantes.access_profile TEXT CHECK (... in regular/secretaria/super_admin)` nullable, backfill, depois NOT NULL DEFAULT 'regular'.
   - `participantes.role DROP NOT NULL` (secretária não tem cargo hospitalar).
   - `reunioes.criada_por VARCHAR(10) REFERENCES participantes(id)`, backfill com `facilitador_id`.
   - Indexes.
   - `is_super_admin` (coluna antiga) fica intacta na fase 1.

2. **Backend `dependencies.py`**
   - `is_super_admin(p)` agora lê `p.get("access_profile") == "super_admin"` mantendo fallback pra `is_super_admin` antiga (zero quebra). Assinatura preservada.
   - Novos `is_secretaria(p)`, `is_regular(p)`, `require_secretaria()`.
   - `get_allowed_reuniao_ids()` ganha caso secretária: retorna IDs de reuniões com `criada_por=self.id AND data>=hoje`.

3. **Backend `routers/reunioes.py`**
   - `POST /reunioes/agendar`: aceita `facilitador_id` no payload. Se vier, valida e usa; senão, mantém fallback por email. Popula `criada_por` com o id do participante autenticado.
   - `PATCH /{id}`: secretária só edita se `criada_por=self.id`.
   - `DELETE /{id}`: secretária pode cancelar reuniões dela (não só diretor/presidente/gerente).
   - `GET /calendario`: pra secretária, retorna metadata reduzida (sem pauta, sem lista de participantes detalhada) das reuniões alheias.

4. **Backend `routers/admin/usuarios.py`**
   - `AdminUsuarioCreate` e `AdminUsuarioUpdate` ganham `access_profile`.
   - Setar `access_profile = 'secretaria'` zera `role` automaticamente.
   - Setar `access_profile = 'super_admin'` espelha em `is_super_admin = true` (compat fase 1).
   - GET retorna `access_profile`.

5. **Backend `routers/pendencias.py`**
   - Garantir que secretária retorna lista vazia (já cai naturalmente porque ela não aparece em `reuniao_participantes` nem como co-responsável).

6. **Email pro facilitador**
   - Novo `send_meeting_scheduled_notification()` em `email_service.py`. Template Jinja2 novo `meeting_scheduled.html`.
   - Disparado em `agendar_reuniao` quando `criada_por != facilitador_id`.

7. **Frontend `types/index.ts`**
   - Adiciona `AccessProfile`. `Participante.role` vira nullable. `Participante.access_profile` obrigatório.

8. **Frontend `lib/auth.ts`**
   - `isSuperAdmin(user)` lê de `access_profile` com fallback pra `is_super_admin` (compat). Novos `isSecretaria`, `isRegular`.

9. **Frontend rotas `/secretaria/*`**
   - `app/secretaria/layout.tsx`: guard.
   - `app/secretaria/page.tsx`: home (reuniões futuras criadas por ela, lista + ações).
   - `app/secretaria/nova/page.tsx`: form completo.

10. **Frontend `/admin/usuarios`**
    - Form ganha radio "Perfil de acesso: Regular / Secretária / Super Admin".
    - Lista ganha badge do perfil.

11. **Frontend redirect pós-login + calendário**
    - Redirect: secretária cai em `/secretaria`, super_admin/regular em `/dashboard`.
    - Calendário esconde detalhes pra secretária em reuniões alheias.

### Critérios de sucesso

- Super_admin atual continua funcionando 100% (sem regressão).
- Secretária loga, marca reunião, escolhe facilitador, define participantes, escreve pauta.
- Email chega no inbox do facilitador.
- Secretária não acessa /pendencias nem /admin/*.
- Calendário mostra horários ocupados sem vazar pauta.

### Riscos

- **Espelhamento incorreto entre `access_profile` e `is_super_admin`**: mitigação via update síncrono em ambos os campos no PATCH `/admin/usuarios`.
- **Vazamento de dados pra secretária**: `get_allowed_reuniao_ids()` é o ponto único, alterado de forma cirúrgica.
- **Quebrar /admin/usuarios em prod**: PATCH aceita campos opcionais, espelhamento explícito.

## Execução / Resultados

### Migrations criadas e aplicadas localmente

- `supabase/migrations/036_add_access_profile.sql`: cria `participantes.access_profile`, backfill (`is_super_admin=true → 'super_admin'`, resto `'regular'`), torna `role` nullable, adiciona `reunioes.criada_por` com backfill via `facilitador_id`, indexes.
- `supabase/migrations/037_cargo_nullable_for_secretaria.sql`: torna `cargo` nullable (descoberto em teste: secretária não tem cargo hospitalar).

Verificado via psql local: os 6 super admins (`pmrdef@gmail.com`, `felipemalafaia@yahoo.com.br`, ...) ficaram com `access_profile='super_admin'`; o resto com `'regular'`. `is_super_admin` legada preservada (compat fase 1).

### Backend

- `backend/app/dependencies.py`: `is_super_admin()` agora lê de `access_profile` (com fallback pra flag legada). Novos `is_secretaria()`, `is_regular()`, `require_secretaria()`. `get_allowed_reuniao_ids()` ganhou caso secretária: retorna IDs onde `criada_por = self.id AND data >= hoje`.
- `backend/app/routers/reunioes.py`:
  - `POST /agendar`: aceita `facilitador_id` no payload + popula `criada_por` com participante autenticado; dispara email pro facilitador quando criada_por ≠ facilitador_id.
  - `PATCH /{id}`: secretária só pode editar reuniões com `criada_por = self.id`.
  - `DELETE /{id}`: removeu `require_role(...)` fixo. Agora super_admin/diretor/presidente/gerente sempre podem; secretária só pra reuniões dela.
  - `GET /calendario`: secretária vê todas (sem filtro de allowed_ids), mas com redact em reuniões alheias (sem participantes, sem objetivo).
- `backend/app/routers/admin/usuarios.py`: filtros e create/update aceitam `access_profile`; helper `_normalize_access_profile_fields()` aplica exclusão mútua (espelhamento em `is_super_admin` + zera `role` se secretária). Endpoints inline `grant-super-admin` e `revoke-super-admin` também atualizam `access_profile`.
- `backend/app/models/schemas.py`: `AgendarReuniaoRequest` ganha `facilitador_id` e `hora_fim`. `EditarReuniaoRequest` ganha `facilitador_id`. `ParticipanteResponse` redesenhado pra permitir `cargo` e `role` nulos.
- `backend/app/models/admin_schemas.py`: `AccessProfile = Literal[...]`. `AdminUsuarioCreate/Update/Response` ganharam `access_profile`; `role` e `cargo` viraram opcionais no create.
- `backend/app/services/email_service.py`: nova função `send_meeting_scheduled_notification(supabase, id_reuniao, facilitador_id, criador_id)`. Template novo em `backend/app/templates/email_reuniao_agendada.html`. Reaproveita `_enviar_email` (Resend → SMTP → mock).

### Frontend

- `frontend/src/types/index.ts`: tipos `AccessProfile` e `ACCESS_PROFILE_LABELS`. `Participante.role` virou nullable, `Participante.cargo` virou opcional/nullable, `Participante.access_profile` adicionado.
- `frontend/src/lib/auth.ts`: `isSuperAdmin()` lê de `access_profile` (fallback em `is_super_admin`). Novos `isSecretaria()`, `isRegular()`.
- `frontend/src/hooks/useCurrentParticipante.ts`: tipo ganhou `access_profile` e relaxou nullability de `cargo`/`role`.
- `frontend/src/components/admin/types.ts`: `AdminUsuario.access_profile` e `AdminUsuarioPayload.access_profile` adicionados. `ACCESS_PROFILE_OPTIONS` exportado.
- `frontend/src/components/admin/UsuarioFormModal.tsx`: radio "Perfil de acesso" (Regular/Secretária/Super Admin) com descrição contextual; secretária esconde campo Role; payload envia null/role corretamente.
- `frontend/src/app/admin/usuarios/page.tsx`: coluna "Super Admin" virou "Perfil" com badge colorido (Super Admin / Secretária / Regular).
- `frontend/src/app/dashboard/layout.tsx`: redireciona pra `/secretaria` quando `access_profile = 'secretaria'`.
- `frontend/src/components/layout/AppShell.tsx`: aceita `variant="secretaria"`.
- `frontend/src/components/layout/Sidebar.tsx`: pra secretária, mostra só Início (`/secretaria`), Nova reunião e Calendário. Logo aponta pra `/secretaria`.
- `frontend/src/app/secretaria/layout.tsx`: guard (403 → `/dashboard` se não for secretária).
- `frontend/src/app/secretaria/page.tsx`: home com lista das reuniões futuras criadas por ela, ações editar/cancelar, botão "Marcar nova reunião".
- `frontend/src/app/secretaria/nova/page.tsx`: form completo (titulo, data, hora_inicio/fim, tipo, facilitador, participantes, objetivo). Suporta modo edit via `?edit=<id_reuniao>`.

### Verificações

- `npx tsc --noEmit` no frontend: zero erros.
- `python -m ast` em arquivos modificados: OK.
- `supabase migration up --local`: 035 e 036 aplicadas.
- `docker compose up -d --build` (via `/atualizar-app`): stack subiu em 39s. Backend `/api/health` retorna 200, frontend `:3000` responde 200.
- OpenAPI exposta tem `access_profile` em `AdminUsuarioCreate/Update/Response` e `facilitador_id` em `AgendarReuniaoRequest`.
- `/secretaria` e `/secretaria/nova` existem (307 → `/login` quando deslogado).

### Pendências / próximos passos

- Testar fluxo end-to-end no browser logando como super_admin existente (`pmrdef@gmail.com`), criar uma secretária via `/admin/usuarios`, logar com ela e marcar uma reunião pra outro facilitador. Validar que o email chega.
- Validar que o super_admin existente continua funcionando 100% (`/admin/*`, `/pendencias`, calendário com todas as reuniões, etc.).
- Fase 2 do plano (não bloqueia esse deploy): após validação em prod, criar migration 037 dropando `is_super_admin` e removendo o código de compatibilidade.

---

## Implementação / Deploy

**feat(secretaria): perfil access_profile + email pro facilitador + módulo /secretaria**

- **Data**: 2026-05-15 20:35 -0300
- **SHA**: `a98e3d5` (HEAD do deploy unificado; commit da feat é `807dcce`)
- **Modo**: ship
- **Resultado**: 🟢 healthy
- **Commit raw**: `feat(secretaria): perfil access_profile + email pro facilitador + módulo /secretaria`

### Serviços tocados
- backend (dependencies, routers/reunioes, routers/admin/usuarios, models, email_service)
- frontend (módulo /secretaria, /admin/usuarios, sidebar, dashboard layout, auth)

### Migrations aplicadas (renumeradas durante o deploy)
- `036_add_access_profile.sql` (antes 035; remote já tinha 035_add_lembrete_24h_reunioes.sql)
- `037_cargo_nullable_for_secretaria.sql` (antes 036)

Aplicadas manualmente via Coolify Terminal como `supabase_admin` (porque o user `postgres` no Supabase self-hosted não é dono das tabelas). Backfill resultou em:
- 55 participantes com `access_profile` (6 super_admin + 49 regular)
- 37 reuniões com `criada_por = facilitador_id`

### Notas
- MCP Coolify ficou 403 durante o deploy todo (token expirado). Operação feita via curl direto contra o app + Coolify Terminal manual. Token novo `4|fF3...` salvo em `/tokens/.env` (ignorado pelo git). Próximo deploy via MCP exige atualizar `~/.claude.json` linha ~1596 e reiniciar Claude Code.
- Health pós-deploy: backend 200 em 89ms, frontend 200 em 90ms.

---
_Atualizado automaticamente pelo `/deploy ship` em 2026-05-15._
