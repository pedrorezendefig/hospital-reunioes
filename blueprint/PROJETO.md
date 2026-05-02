# Hospital Reuniões

> Atualizado em 2026-05-01. Regere com `/blueprint update`.

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação, transcrição por IA, geração de ata, assinatura digital e acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam. Recebem só emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `mala-ia.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.mala-ia.cloud | 🟢 healthy | 3c627ee · 01/05 |
| frontend | app.mala-ia.cloud | 🟢 healthy | 85f7f88 · 27/04 |
| supabase | studio.mala-ia.cloud | 🟢 healthy | n/a · 27/04 |

## Variáveis críticas

**backend** (FastAPI):
- ✅ ENVIRONMENT=`production`
- ✅ DEBUG=`false`
- ✅ ENABLE_BYPASS_ENDPOINTS=`false`
- ✅ CLICKSIGN_BASE_URL=`https://app.clicksign.com`
- ✅ SUPABASE_URL (presente)
- ✅ SUPABASE_SERVICE_ROLE_KEY (presente)
- ✅ SUPABASE_ANON_KEY (presente)
- ✅ OPENROUTER_API_KEY (presente, LLM primário)
- ✅ LLM_MODEL=`openai/gpt-5.4-mini`
- ✅ OPENAI_API_KEY (presente, fallback)
- ✅ LLM_FALLBACK_MODEL=`gpt-4o-mini`
- ✅ CLICKSIGN_API_KEY (presente)
- ✅ CLICKSIGN_WEBHOOK_SECRET (presente, auto-gerado)
- ✅ RESEND_API_KEY (presente)
- ✅ RESEND_FROM_EMAIL (presente)
- ✅ SIGNUP_ENCRYPTION_KEY (presente, auto-gerado)
- ✅ SIGNUP_PASSE (presente, auto-gerado)

**frontend** (Next.js, build-time):
- ✅ NEXT_PUBLIC_SUPABASE_URL (presente)
- ✅ NEXT_PUBLIC_SUPABASE_ANON_KEY (presente)
- ✅ NEXT_PUBLIC_API_URL (presente)
- ✅ NEXT_PUBLIC_ENVIRONMENT (presente)

**supabase** (mailer/SMTP, 16 vars):
- ✅ Todas as 16 presentes (GOTRUE_SITE_URL, ADDITIONAL_REDIRECT_URLS, API_EXTERNAL_URL, SMTP_*, MAILER_*)

## Integrações externas

- 🟢 **OpenRouter** (LLM primário): geração de ata e correções via `openai/gpt-5.4-mini` (configurável via `LLM_MODEL`)
- 🟢 **OpenAI** (LLM fallback): usado se `OPENROUTER_API_KEY` ficar vazia. Modelo `gpt-4o-mini` via `LLM_FALLBACK_MODEL`
- 🟢 **ClickSign**: assinatura digital de atas (sandbox em dev, app em prod)
- 🟢 **Resend**: emails transacionais e SMTP do Supabase Auth
- 🟢 **Fireflies**: sync de transcrições via webhook

## Próximas ações & alertas

- ✅ Migração LLM concluída. Backend roda gpt-5.4-mini via OpenRouter (build 1m53s, health 88ms)
- 🔵 Validar ATA real em produção. Subir uma reunião em app.mala-ia.cloud e conferir qualidade do output (prompts foram afinados pra gpt-4o-mini, pode haver variações sutis)
- 🔵 Acompanhar custo no painel da OpenRouter. gpt-5.4-mini custa cerca de 5x mais que gpt-4o-mini (US$0,75/M input + US$4,50/M output)
- 🟡 Ajustar `expected_body_regex` em project.json (espera `^{"status":"ok"}$` mas `/api/health` retorna `{"status":"healthy",...}`)

## Stack

- **Backend**: FastAPI (Python 3.12) + uv + Uvicorn
- **Frontend**: Next.js 15 (App Router) + pnpm
- **Database**: Supabase self-hosted
- **Infra**: Coolify em VPS Hostinger 16GB + Traefik/Let's Encrypt
- **PDF**: WeasyPrint + Jinja2
- **LLM**: OpenRouter (`openai/gpt-5.4-mini`) com fallback para OpenAI direto (`gpt-4o-mini`)

## Coolify

- **VPS**: 31.97.29.32 (Hostinger 16GB)
- **Painel**: https://coolify.mala-ia.cloud
- **Domínio raiz**: mala-ia.cloud
- **UUIDs**: project=`gvkd16jzoq8dzlpep2txqgo3`, server=`uy6j3f0nmevsvwkknmmpfgqc`, github_app=`r10gjb55dd6zamdx0vquuau4`

## Histórico recente

**Últimos 5 deploys** (de `history.json`, sem campos voláteis):

- 01/05 `3c627ee`: Migra LLM de OpenAI direto para OpenRouter (gpt-5.4-mini). 🟢 healthy. [implementacoes/2026-05-01-1941-3c627ee-healthy.md](implementacoes/2026-05-01-1941-3c627ee-healthy.md)
- 27/04 `85f7f88`: Migra blueprint para PROJETO.md (skill /blueprint global). 🟢 healthy. [implementacoes/2026-04-27-1952-85f7f88-healthy.md](implementacoes/2026-04-27-1952-85f7f88-healthy.md)
- 27/04 `890b149`: Data-fix de revisão ortográfica em massa replicada em PROD (147 UPDATEs). 🟢 healthy
- 27/04 `890b149`: PDF de ATA com fonte HP Simplified e paleta refinada + revisão ortográfica do banco. 🟢 healthy
- 27/04 `d36f1de`: Lote de melhorias (transcrição multi-formato, drop coluna `local`, filtro por facilitador). 🟢 healthy

**Commits do mês**: ver [`historico/2026-04.md`](historico/2026-04.md)

## Como mexer

- Deploy: `/deploy`. Status: `/deploy status`. Reverter: `/deploy rollback`.
- Atualizar este doc: `/blueprint update`.
- Atualizar histórico mensal: `/blueprint historico`.

## Planos abertos

- [`planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md`](../planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md): Migração LLM para OpenRouter (concluída, deploy 3c627ee)
- [`planos/plano-26-04-27-1929h-revisao-ortografica-banco.md`](../planos/plano-26-04-27-1929h-revisao-ortografica-banco.md): Revisão ortográfica em massa do banco
- [`planos/plano-26-04-27-1730h-skill-blueprint-md.md`](../planos/plano-26-04-27-1730h-skill-blueprint-md.md): Skill `/blueprint` global (substitui `/blueprint-sync`, remove HTML)
- [`planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md`](../planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md): PDF da ATA com fonte HP Simplified e visual refinado
- [`planos/plano-26-04-27-0506h-filtro-por-facilitador.md`](../planos/plano-26-04-27-0506h-filtro-por-facilitador.md): Filtro por Facilitador (Calendário, Pendências Lista e Kanban)
- [`planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md`](../planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md): Bordas menos arredondadas no sistema todo
- [`planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md`](../planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md): Reversão completa do agente Ana (versão beta sem resquício)
- [`planos/plano-26-04-27-0227h-redesign-lista-pendencias.md`](../planos/plano-26-04-27-0227h-redesign-lista-pendencias.md): Redesign da lista de Ações/Tarefas (Pendências)
- [`planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md`](../planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md): Remover campo "Local" e renomear "Objetivo" para "Pauta" (só UI)
- [`planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md`](../planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md): Calendário como página única de Reuniões + Transcrição multi-formato
- [`planos/plano-26-04-25-0210h-template-email-pt-br.md`](../planos/plano-26-04-25-0210h-template-email-pt-br.md): Email de auth em produção (template pt-BR servido pelo frontend)
