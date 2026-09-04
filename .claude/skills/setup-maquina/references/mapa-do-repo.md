# Mapa do repositório: o que é cada pasta, por quê, e como se conectar a cada serviço

Este mapa explica o **porquê** e o **para quê**. A árvore de verdade é o disco: antes de responder sobre uma pasta, rode `ls` nela e confira. Pasta no disco que não está aqui, ou linha aqui sem pasta no disco, é sinal de que o mapa envelheceu: avise e proponha a correção neste arquivo. A regra do layout é o ADR 0044 (e a emenda 0045). O detalhe do app (rotas, tabelas, integrações) é gerado a cada deploy em `docs/spec/snapshots/` e não se repete aqui.

## A regra de uma frase

Tudo que está na árvore é código, doc viva, decisão ou material de comunicação. Insumo humano fica em `local/`, fora do git. Estado de trabalho fica nas GitHub Issues e em `docs/spec/deploy/*.json`, nunca em documento paralelo.

## Raiz

| Pasta ou arquivo | O que é | Por que existe | O que você acha dentro | Para que serve no dia a dia |
|---|---|---|---|---|
| `CLAUDE.md` | Regras do repo para o agente | Mínimo que toda sessão precisa saber | Idioma, tipografia, pipeline, o que é proibido criar | Leia uma vez. O roteamento fino está no `/ask-pedro` |
| `CONTEXT.md` | Glossário do contexto Reuniões (e, por ora, da Ouvidoria) | O agente e o time falam a mesma língua | Termos com definição e "evitar" | Consultar antes de nomear qualquer coisa nova |
| `CONTEXT-MAP.md` | Mapa dos contextos de domínio | Termos homônimos (Setor, Versão) mudam de sentido entre contextos | Tabela contexto x glossário | Saber qual glossário abrir |
| `skills-lock.json` | Origem e hash das 8 skills importadas do Matt Pocock | Rastreabilidade, não instalação | Repo de origem e caminho | Nada a rodar; as skills já vêm no clone |
| `.claude/skills/` | As skills do time, versionadas | Quem clona recebe o workflow inteiro (ADR 0043) | 23 pastas, uma por skill, com `SKILL.md`, `references/` e `scripts/` | `/ask-pedro` diz qual usar |
| `.github/` | CI e templates | Gates automáticos do `/ship` | `ci.yml` (ruff, pytest, lint, tsc, build), `lint-adr.yml`, `higiene-issues.yml`, templates de issue e PR | Não se edita no dia a dia |
| `docs/` | Documentação viva | Ver seção abaixo | | |
| `hospital-reunioes/` | O app | Ver seção abaixo | `backend/`, `frontend/`, `supabase/` | Onde o código mora |
| `local/` | **Fora do git.** Insumo humano | PDFs, transcrições e dumps não podem ir para o GitHub | `insumos/<assunto>/` que cada máquina cria | Colocar aqui o que o hospital manda |
| `tokens/` | Tokens da **máquina**, não do app | O `/deploy` e o `/ship` falam com o Coolify | `.env.example` (versionado) e `.env` (fora do git, permissão 600) | Preencher uma vez por máquina |
| `tools/` | Ferramentas de repo | Gate de ADR no CI e painel local | `lint_adr.py`; `workflow-dashboard/` (painel read-only das issues e do deploy) | `python3 tools/workflow-dashboard/serve.py` |

## `docs/`

| Pasta | O que é | Por que existe | O que tem | Quando abrir |
|---|---|---|---|---|
| `adr/` | Decisões de arquitetura e domínio | Decisão sem registro é re-litigada | `README.md` (índice por tema) e um `.md` por decisão, com `status` no frontmatter | Antes de propor mudança de regra. Só `accepted` vale |
| `agents/` | Protocolo do agente | Sessões paralelas precisam do mesmo contrato | `issue-tracker.md` (claim, labels, revisor), `triage-labels.md`, `domain.md` | Ao pegar issue ou triar |
| `onboarding/` | Setup humano | Máquina nova | `claude-setup.md` (setup), `dev.md` (dia a dia) | Primeiro dia. `/setup-maquina` confere o mesmo conteúdo |
| `spec/deploy/` | Contrato e estado do deploy | O `/deploy` lê daqui, nunca de memória | `project.json` (contrato: serviços, chaves, gates), `state.json` (versão em prod agora), `history.json` (todos os deploys, com notas) | `/deploy status`; ler as notas antes de planejar |
| `spec/snapshots/` | Mapa factual do app, gerado | O código muda, o mapa acompanha sozinho | `ROTAS.md`, `ENTIDADES.md`, `SCHEMA.md`, `MIGRATIONS.md`, `INTEGRACOES.md`, `ESTRUTURA.md` | Para saber o que existe hoje sem abrir o código |
| `spec/CHANGELOG.md`, `spec/VERSIONING.md` | Linha do tempo dos deploys e regra de versão | Cada ship tem entrada | Versão, data, PR, ADRs | Ver o que subiu quando |
| `pops/` | Glossário do contexto POPs | Segundo contexto de domínio (ADR 0007) | `CONTEXT.md` e `materiais-reais/` (POPs reais como referência) | Trabalhando em POPs |
| `comunicacao/` | Material para o diretor e o usuário funcional | Vídeo e página nascem juntos por PRD (ADR 0045) | `<contexto>/<PRD>-<slug>/video/` (composição) e `index.html` (página); `_assets/` (uma fonte, um logo) | `/divulgar <PRD>`. MP4 fica fora do git |
| `manual/` | Manual do usuário por módulo | Publicado na Vercel para o time interno | `ouvidoria/index.html`, `img/`, `README.md` (como publicar) | Ao entregar módulo novo |
| `ARQUITETURA.md` | Visão de arquitetura | Um lugar para o desenho geral | Os 3 contextos, fluxos, blocos gerados pelo `/snapshot` | Primeira leitura técnica |

## `hospital-reunioes/` (o app)

| Pasta | O que é | Como se organiza | Onde as coisas ficam |
|---|---|---|---|
| `backend/` | FastAPI, Python 3.12, `uv` | `app/routers/` (HTTP, um arquivo ou subpacote por área), `app/services/` (regra de negócio), `app/models/` (schemas por contexto), `app/pipeline/` (IA da transcrição), `app/cron/` (jobs), `app/middleware/`, `app/utils/`, `app/templates/` (emails), `app/prompts/` (prompts da IA), `app/static/` (fonte e logo dos PDFs) | `tests/` (pytest), `scripts/` (operação, fora da imagem; `scripts/oneshot/` já rodou), `.env.example` (espelho da classe `Settings`) |
| `frontend/` | Next.js 15, App Router, pnpm 9, Tailwind 4 | `src/app/` (rotas por domínio com `layout.tsx` que aplica o gate), `src/components/<dominio>/`, `src/components/ui/` (genéricos), `src/lib/<dominio>/` (regra sem React, com teste ao lado), `src/hooks/` | `public/` (ícones PWA, fonte, logo; `email-templates/` gerados para o Supabase), `.env.example` (para `pnpm dev` sem Docker) |
| `supabase/` | Banco self-hosted, Postgres 17 | `migrations/NNN_nome.sql` (numeração contínua; toda tabela nova liga RLS), `seed.sql` (dois usuários locais), `templates/` (emails do Auth), `config.toml` (portas locais 5435x) | Migration em produção é humana, no Studio |
| `.env.example` | Molde do `.env` que o backend lê | Uma só cópia para `docker-compose` e `uvicorn` | O `/setup-maquina` diz o mínimo a preencher |
| `docker-compose.yml`, `README.md` | Stack local (opcional) e porta de entrada do app | Hoje ninguém roda o app local: sobe para produção e testa lá | |

## Variáveis de ambiente: onde cada uma mora

| Arquivo | Quem lê | O que vai nele | Fonte dos valores |
|---|---|---|---|
| `tokens/.env` | `/deploy`, `/ship`, `/onda` (CLI do Coolify) | `COOLIFY_ACCESS_TOKEN` (seu), `COOLIFY_BASE_URL`, `ANA_API_KEY` (opcional) | `chaves.md` |
| `hospital-reunioes/.env` | backend local e o snapshot do `/deploy ship` | Mínimo: `ENVIRONMENT`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` (fictícios) | `chaves.md` |
| `hospital-reunioes/frontend/.env.local` | `pnpm dev` (opcional) | `NEXT_PUBLIC_*` do Supabase local | `supabase status` |
| Coolify (produção) | os containers | Todas as chaves reais | Só o Pedro. Nunca no clone |
| GitHub Actions | CI | Nenhum secret: valores fictícios no próprio `ci.yml` | Nada a fazer |

## Como se conectar a cada serviço

| Serviço | Para quê | O que você precisa | Como conseguir |
|---|---|---|---|
| **GitHub** (`pedrorezendefig/hospital-reunioes`) | Issues, PRs, CI, merge | Permissão WRITE e `gh auth login` | O Pedro adiciona você como colaborador. Depois `gh auth login` no terminal |
| **Coolify** (`https://coolify.hospitalsaomatheus.cloud`) | Deploy, status, rollback, env de produção | Conta na instância e um token seu | O Pedro cria a conta. Você gera o token em Keys & Tokens, grava em `tokens/.env` e cria o contexto `hsm` (`claude-setup.md` seção 4.1) |
| **Supabase de produção** (`https://studio.hospitalsaomatheus.cloud`) | Aplicar migration, conferir tabela | Acesso ao Studio | Hoje só o Pedro tem. O `/ship` entrega o SQL e espera o humano aplicar |
| **App em produção** (`https://app.hospitalsaomatheus.cloud`, API em `api.hospitalsaomatheus.cloud`) | Testar o que subiu | Um usuário no app | O Pedro cria pelo admin. `/api/health` mostra a versão no ar |
| **Resend** | Email transacional | Nada na sua máquina | A chave vive só no Coolify. Se precisar ver logs de envio, peça acesso ao painel do Resend |
| **ClickSign** | Assinatura de Ata e POP | Nada na sua máquina para o fluxo normal | Produção no Coolify; sandbox só se for rodar o app local (`chaves.md`) |
| **OpenRouter** | LLM das Atas, POPs e Ouvidoria | Nada na sua máquina para o fluxo normal | Chave só no Coolify; local usa mock com chave vazia |
| **Global Health** | Espelho da agenda | Nada | Token de homologação só no Coolify (é do fornecedor, não do GitHub) |
| **Ana** (agente de IA externa) | Consome a API da Ouvidoria | `ANA_API_KEY` só para smoke test contra produção | Item do 1Password (`chaves.md`) |
| **Vercel** | Publicar divulgação e manual | Membro do time na Vercel | O Pedro convida. Sem isso a CLI recusa com `TEAM_ACCESS_REQUIRED` |
| **1Password** (cofre VITTA TECH) | Onde as chaves compartilhadas moram | Acesso ao cofre | O Pedro compartilha. Você copia à mão; nenhuma skill acessa o cofre |

## O fluxo, em uma linha por etapa

1. Ideia: `/grill-with-docs` afia contra `CONTEXT.md` e ADRs. 2. `/to-prd` e `/to-issues` viram issues. 3. `/pegar-issue N` faz o claim e abre a branch. 4. `/tdd` escreve o teste primeiro. 5. `/ship` abre o PR, roda os 3 gates e pede o OK de merge. 6. O merge dispara o build no Coolify; `/deploy ship` acompanha e registra em `docs/spec/deploy/`. 7. Testa em produção. 8. `/divulgar` conta a entrega ao diretor.
