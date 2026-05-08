# Hospital Reuniões

> Atualizado em 2026-05-08. Regere com `/blueprint update`.

## O que é

Hospital Reuniões automatiza o ciclo de vida de reuniões corporativas de hospital de alta complexidade: gravação, transcrição por IA, geração de ata, assinatura digital e acompanhamento de pendências.

**Quem usa:** 5 facilitadores (1 diretor + 4 diretoras). Colaboradores não logam. Recebem só emails da ClickSign e links diretos pra pendências.

**Estado:** Em produção em `hospitalsaomatheus.cloud`. Banco de desenvolvimento ainda mocado para fluxo dual (LOCAL × PRODUÇÃO).

## Estado de produção

| Serviço | URL | Status | Último deploy |
|---|---|---|---|
| backend | api.hospitalsaomatheus.cloud | 🟢 healthy | 7457c69 · 08/05 |
| frontend | app.hospitalsaomatheus.cloud | 🟢 healthy | 003ed6f · 08/05 |
| supabase | studio.hospitalsaomatheus.cloud | 🟢 healthy | n/a · 27/04 |

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
- ✅ NEXT_PUBLIC_API_URL (presente, aponta pra api.hospitalsaomatheus.cloud)
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

- ⚠️ **Token Coolify revogado.** MCP retorna 401. Pedro precisa gerar novo token em https://coolify.mala-ia.cloud/security/api-tokens e atualizar via `claude mcp remove coolify -s user && claude mcp add coolify -s user -- npx -y @masonator/coolify-mcp -e COOLIFY_ACCESS_TOKEN=<novo> -e COOLIFY_BASE_URL=https://coolify.mala-ia.cloud`.
- ⚠️ **CI vermelho por motivos não bloqueantes** (Coolify usa Dockerfile, não CI):
  - Backend pytest falha por `Settings` exigir `SUPABASE_URL`/`SERVICE_ROLE_KEY`. Fix: criar `tests/conftest.py` com `os.environ.setdefault` ou adicionar secrets no GitHub Actions.
  - Frontend lint falha porque `.github/workflows/ci.yml` usa `node-version: 20` + `pnpm version: latest` (11.0.8 requer node 22.13+). Fix: alinhar com Dockerfile (node 22, pnpm 9).
- 🔵 **DNS coolify.hospitalsaomatheus.cloud não criado**: UI continua acessível em coolify.mala-ia.cloud (DNS legado). Criar registro A se quiser migrar painel também.
- 🟡 **expected_body_regex desatualizado** em project.json (espera `^{"status":"ok"}$` mas API retorna `{"status":"healthy",...}`).
- 🔵 Validar PDF de ATA com nova tipografia HP Simplified e paleta DESIGN.md (#2B2E7E).
- 🔵 Acompanhar custo no painel da OpenRouter. gpt-5.4-mini custa cerca de 5x mais que gpt-4o-mini.

## Stack

- **Backend**: FastAPI (Python 3.12) + uv + Uvicorn
- **Frontend**: Next.js 15 (App Router) + pnpm
- **Database**: Supabase self-hosted
- **Infra**: Coolify em VPS Hostinger 16GB + Traefik/Let's Encrypt
- **PDF**: WeasyPrint + Jinja2
- **LLM**: OpenRouter (`openai/gpt-5.4-mini`) com fallback para OpenAI direto (`gpt-4o-mini`)

## Coolify

- **VPS**: 31.97.29.32 (Hostinger 16GB)
- **Painel**: https://coolify.mala-ia.cloud (DNS hospitalsaomatheus.cloud para coolify ainda não criado)
- **Domínio raiz**: hospitalsaomatheus.cloud
- **UUIDs**: project=`gvkd16jzoq8dzlpep2txqgo3`, server=`uy6j3f0nmevsvwkknmmpfgqc`, github_app=`r10gjb55dd6zamdx0vquuau4`

## Histórico recente

**Últimos 5 deploys** (de `history.json`, sem campos voláteis):

- 08/05 `7457c69`: Aplica ruff format em pdf_generator.py + ship dos 5 commits da migração de domínio. 🟢 healthy. [implementacoes/2026-05-08-0143-7457c69-healthy.md](implementacoes/2026-05-08-0143-7457c69-healthy.md)
- 01/05 `3c627ee`: Migra LLM de OpenAI direto para OpenRouter (gpt-5.4-mini). 🟢 healthy. [implementacoes/2026-05-01-1941-3c627ee-healthy.md](implementacoes/2026-05-01-1941-3c627ee-healthy.md)
- 27/04 `85f7f88`: Migra blueprint para PROJETO.md (skill /blueprint global). 🟢 healthy. [implementacoes/2026-04-27-1952-85f7f88-healthy.md](implementacoes/2026-04-27-1952-85f7f88-healthy.md)
- 27/04 `890b149`: Data-fix de revisão ortográfica em massa replicada em PROD (147 UPDATEs). 🟢 healthy
- 27/04 `890b149`: PDF de ATA com fonte HP Simplified e paleta refinada + revisão ortográfica do banco. 🟢 healthy

**Commits do mês**: ver [`historico/2026-05.md`](historico/2026-05.md) (regerar com `/blueprint historico`).

## Como mexer

- Deploy: `/deploy`. Status: `/deploy status`. Reverter: `/deploy rollback`.
- Atualizar este doc: `/blueprint update`.
- Atualizar histórico mensal: `/blueprint historico`.

## Planos abertos

- [`planos/plano-26-05-01-1955h-redesign-proposta-pj.md`](../planos/plano-26-05-01-1955h-redesign-proposta-pj.md): Redesign da proposta PJ
- [`planos/plano-26-05-01-1939h-skill-clone-banco-sql.md`](../planos/plano-26-05-01-1939h-skill-clone-banco-sql.md): Skill `/clone-banco` (gera SQLs pra restore manual)
- [`planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md`](../planos/plano-26-04-29-0327h-proposta-pj-hospital-sao-mateus.md): Proposta PJ Hospital São Mateus
- [`planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md`](../planos/plano-26-04-28-1230h-clonagem-banco-vps-novo.md): Clonagem do banco pro VPS novo
- [`planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md`](../planos/plano-26-04-29-1515h-migracao-openrouter-gpt54mini.md): Migração LLM para OpenRouter (concluída, deploy 3c627ee)
- [`planos/plano-26-04-27-1929h-revisao-ortografica-banco.md`](../planos/plano-26-04-27-1929h-revisao-ortografica-banco.md): Revisão ortográfica em massa do banco
- [`planos/plano-26-04-27-1730h-skill-blueprint-md.md`](../planos/plano-26-04-27-1730h-skill-blueprint-md.md): Skill `/blueprint` global
- [`planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md`](../planos/plano-26-04-27-1800h-pdf-fonte-hp-simplified.md): PDF da ATA com fonte HP Simplified
- [`planos/plano-26-04-27-0506h-filtro-por-facilitador.md`](../planos/plano-26-04-27-0506h-filtro-por-facilitador.md): Filtro por Facilitador
- [`planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md`](../planos/plano-26-04-27-0503h-bordas-menos-arredondadas.md): Bordas menos arredondadas no sistema todo
- [`planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md`](../planos/plano-26-04-27-0437h-reversao-ana-versao-beta-limpa.md): Reversão completa do agente Ana
- [`planos/plano-26-04-27-0227h-redesign-lista-pendencias.md`](../planos/plano-26-04-27-0227h-redesign-lista-pendencias.md): Redesign da lista de Ações/Tarefas
- [`planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md`](../planos/plano-26-04-27-0421h-remover-local-renomear-objetivo-pauta.md): Remover campo "Local" e renomear "Objetivo" para "Pauta"
- [`planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md`](../planos/plano-26-04-27-0410h-fim-lista-multi-formato-transcricao.md): Calendário como página única + Transcrição multi-formato
- [`planos/plano-26-04-25-0210h-template-email-pt-br.md`](../planos/plano-26-04-25-0210h-template-email-pt-br.md): Email de auth em produção (template pt-BR)
