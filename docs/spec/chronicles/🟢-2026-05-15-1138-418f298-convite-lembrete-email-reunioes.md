# Convite e lembrete por email aos participantes de reunião

## Plano

### Escopo

Adicionar três comportamentos de notificação por email no fluxo de reuniões programadas:

1. **Convite na criação.** Ao salvar uma nova reunião com participantes, todos os participantes selecionados recebem um email convite. A UI mostra um aviso pré-submit (texto inline abaixo das tags) e o banner pós-submit menciona que os participantes foram notificados.
2. **Convite incremental.** Ao adicionar um participante a uma reunião já existente, apenas o recém-adicionado recebe email. Quem já estava na reunião não é reenviado. Toast pós-submit confirma o envio.
3. **Lembrete 24h antes.** Job recorrente envia email lembrete aos participantes 24 horas antes do horário marcado. Reuniões marcadas com menos de 24h de antecedência não disparam lembrete (a janela já passou quando o job avalia). Se a data ou hora for editada depois, a flag é resetada e o lembrete é reavaliado.

### Decisões de produto

- Email **compacto**: título, data formatada em pt-BR com dia da semana, hora, tipo, facilitador (nome), objetivo se preenchido, botão "Ver reunião na plataforma". Sem lista de outros participantes.
- **Facilitador não recebe** convite nem lembrete. Quem cria já sabe.
- **Editar data ou hora reseta** a flag `lembrete_24h_enviado_at` em `editar_reuniao` e `force_editar_reuniao`. O job reavalia no próximo tick.
- **Best-effort.** Falha individual de envio fica em log, não interrompe lote nem afeta a resposta HTTP da criação (background tasks).

### Passos técnicos

1. Coluna `lembrete_24h_enviado_at TIMESTAMPTZ NULL` em `reunioes` + index parcial cobrindo o filtro do job.
2. Service `app/services/reuniao_email_service.py` reusando `_enviar_email` (Resend → SMTP → mock) e `get_logo_data_uri` da infra existente.
3. Templates Jinja em `app/templates/`: `email_convite_reuniao.html` (badge azul) e `email_lembrete_reuniao.html` (badge âmbar). Ambos herdam de `email_base.html`.
4. Routers: `agendar_reuniao` e `adicionar_participantes` recebem `BackgroundTasks` e enfileiram `enviar_convites`. `editar_reuniao` e `force_editar_reuniao` resetam a flag quando `data` ou `hora_inicio` mudam. `adicionar_participantes` calcula delta (só os realmente novos).
5. Scheduler: novo job `enviar_lembretes_24h` rodando a cada 15 minutos com pré-filtro no Supabase e cálculo da janela de 24h em Python.
6. Frontend: aviso inline condicional após as tags de participantes selecionados (calendário) e microtexto perto do botão "Adicionar participante" (detalhe). Banner do calendário pós-submit menciona notificação. Toast de sucesso/erro no fluxo de adicionar depois.

### Critérios de sucesso

- Criar reunião com 2 participantes dispara 2 logs `[convite]` (mock) ou 2 emails reais.
- Adicionar 1 participante a uma reunião existente com 3 dispara apenas 1 log `[convite]`, não 4.
- Editar `data` ou `hora_inicio` zera `lembrete_24h_enviado_at` no banco.
- Job invocado manualmente no container envia lembrete e marca a flag; segunda invocação não reenviá.
- Reuniões marcadas para menos de 24h não disparam lembrete em nenhum tick.

### Riscos

- Resend e SMTP em prod precisam estar configurados; em dev local cai no mock log automaticamente.
- Lembretes 24h dependem de tempo do servidor estar em sync com o real (Coolify usa UTC, timezone `America/Sao_Paulo` está hardcoded no scheduler).
- Reset do lembrete em edição de data: se o usuário ajustar a hora minutos antes da reunião, o job ainda pode tentar enviar e marcar a flag (mas a condição `ponto_24h <= agora < inicio` cobre).

## Execução / Resultados

### Implementado em 2026-05-15

Branch isolada: `worktree-email-convites-reunioes`. Sem deploy ainda.

**Backend**

- `hospital-reunioes/backend/app/services/reuniao_email_service.py` (novo, 230 linhas). Expõe `enviar_convites(supabase, id_reuniao, participante_ids)` e `enviar_lembrete_24h(supabase, id_reuniao)`. Helpers `_formatar_data_ptbr` (com dicionário pt-BR de dias da semana), `_formatar_hora`, `_buscar_destinatarios` (filtra facilitador, inativos e sem email).
- `hospital-reunioes/backend/app/templates/email_convite_reuniao.html` (novo). Badge azul "Convite para Reunião", título destacado, grid 2x2 (data/hora + tipo/facilitador), objetivo condicional, CTA.
- `hospital-reunioes/backend/app/templates/email_lembrete_reuniao.html` (novo). Badge âmbar "Lembrete &mdash; faltam 24 horas", restante idêntico.
- `hospital-reunioes/supabase/migrations/035_add_lembrete_24h_reunioes.sql` (nova). `ALTER TABLE` + index parcial `idx_reunioes_lembrete_pendente`.
- `hospital-reunioes/backend/app/routers/reunioes.py`. Cinco edits: import do service, `BackgroundTasks` em `agendar_reuniao`, dispatch dos convites, idem em `adicionar_participantes` com cálculo de delta, reset da flag em `editar_reuniao` e `force_editar_reuniao` quando `data` ou `hora_inicio` mudam.
- `hospital-reunioes/backend/app/cron/scheduler.py`. Reescrito com novo job `enviar_lembretes_24h` rodando `interval=15min`, usando `ZoneInfo("America/Sao_Paulo")` pra calcular janela.

**Frontend**

- `hospital-reunioes/frontend/src/app/reunioes/calendario/page.tsx`. Aviso inline condicional logo abaixo das tags de selecionados. Banner `successMsg` do `handleAgendarSuccess` atualizado pra "Reunião agendada com sucesso. Os participantes foram notificados por email." com 5s de timeout.
- `hospital-reunioes/frontend/src/app/reunioes/[id]/page.tsx`. `handleAddParticipante` agora checa `res.ok`, mostra toast de sucesso ("Participante adicionado. Um convite por email foi enviado.") ou de erro com `detail` do backend. Microtexto inline ("Novos participantes recebem um email de convite na hora.") abaixo do botão "Adicionar participante".

**Validações executadas**

- `uv run ruff check` nos 3 arquivos backend mexidos: All checks passed.
- Smoke test de import e helpers (`_formatar_data_ptbr(date(2026,5,15))` retorna "15/05/2026 (sexta-feira)").
- Render dos dois templates Jinja com contexto sintético: HTML de ~7KB cada, CTA com link correto, badge correto, objetivo condicional aparece.
- `pnpm tsc --noEmit`: limpo.
- `pnpm lint`: nenhum warning novo nos arquivos editados (warnings pré-existentes em outros arquivos).

### Pendente para o deploy

- Aplicar migration `035` no Supabase de prod (Studio ou `supabase db push`).
- `RESEND_API_KEY` em prod já existe (`blueprint/deploy/project.json`), sem ação adicional.
- Rebuild dos containers via `/atualizar-app` em dev pra validar end-to-end com Mailpit antes do ship.

---

## Implementação / Deploy

**Envio de convites e lembrete 24h por email aos participantes de reuniões programadas**

- **Data**: 2026-05-15 11:38 -03:00
- **SHA**: `418f298`
- **Modo**: ship
- **Resultado**: 🟢 healthy
- **Commit raw**: `feat(reunioes): envio de convites e lembrete 24h por email aos participantes`

### Serviços tocados

- backend (FastAPI)
- frontend (Next.js)

### Migrations aplicadas

- `035_add_lembrete_24h_reunioes.sql` (via `supabase_admin` no container supabase-db-* da VPS)

### Health pós-deploy

- backend: 200 em 79ms (https://api.hospitalsaomatheus.cloud/api/health)
- frontend: 200 em 152ms (https://app.hospitalsaomatheus.cloud)

### Notas

Logo embutido nos emails foi trocado de data URI base64 (que o Gmail filtra por ser >10 KB) para URL absoluta servida pelo frontend Next.js (`{frontend_url}/logo-hsm.png`). Em produção o proxy do Gmail consegue baixar normalmente; em dev local o logo continua quebrado porque o proxy não acessa `localhost`. Header subtitle duplicado dos templates foi removido durante teste interativo.

---
_Atualizado automaticamente pelo `/deploy ship` em 2026-05-15._
