# Onboarding — Dev no Hospital Reuniões

Boas-vindas. Esta é a única página que você precisa pra começar.

## A regra de ouro

O trabalho é **GitHub-issue-centric**: toda mudança nasce de uma Issue e morre num PR que fecha essa Issue. Você decora **duas entradas**:

- **Tem uma ideia ou melhoria nova?** → `/grill-with-docs` (lapida a ideia, vira PRD, vira issues).
- **Vai pegar trabalho que já está na fila?** → `/pegar-issue` (sem nada lista a fila; com um número pega a issue).

O resto do caminho — `/tdd` → `/ship` → `/deploy` — as skills encadeiam.

## Setup inicial (1 vez só)

**Faça o setup completo do Claude Code seguindo [`claude-setup.md`](./claude-setup.md)** — cobre tudo (CLI, plugins, CLI do Coolify, permissions). Tempo: 15–30min.

Depois disso, sobe o app local:
```bash
cd hospital-reunioes && docker compose up -d   # ou use /atualizar-app
```

Pré-requisitos básicos antes do `claude-setup.md`:
- Docker Desktop instalado
- `gh auth login` feito
- `git config user.name "Seu Nome"` + `git config user.email "seu@email"`
- Acesso `WRITE` ao repo (peça pro Pedro adicionar)

## Como trabalhar

### Cenário A — Tenho uma ideia nova (feature, melhoria)

```
/grill-with-docs
```

A skill **desafia** sua ideia contra o domínio (`CONTEXT.md` + `docs/adr/`), afia a terminologia e, conforme as decisões fecham, atualiza `CONTEXT.md`/ADR ali mesmo. Quando o plano está redondo:

```
/to-prd      # vira um PRD = 1 Issue ready-for-agent no GitHub
/to-issues   # quebra o PRD em fatias verticais independentes (1 issue cada)
```

Agora há issues na fila pra qualquer um pegar.

### Cenário B — Vou pegar trabalho da fila

```
/pegar-issue          # lista as issues ready-for-agent sem dono
/pegar-issue 42       # dá o "claim" (vira sua), cria a branch e carrega a spec
/tdd                  # red → green → refactor: critérios de aceite viram testes
/ship                 # 3 gates → merge → deploy (fecha a issue com Closes #42)
```

### Cenário C — Estava trabalhando, sessão fechou, abro outro terminal

O contexto **não vive em arquivo de plano — vive na Issue**. Então:

```
git checkout <tipo>/<slug>-42     # a branch é determinística pelo nº da issue
gh issue view 42                  # relê a spec e os critérios de aceite
/tdd                              # continua do teste onde parou
```

Sem perda de contexto: a Issue é a fonte da verdade.

### Cenário D — Tem um bug feio que não sei resolver

```
/diagnose
```

Loop disciplinado: reproduz → minimiza → hipótese → instrumenta → corrige → teste de regressão.

## O que acontece debaixo dos panos

```
/grill-with-docs   desafia a ideia contra CONTEXT.md + ADRs; atualiza docs inline
   ▼
/to-prd            PRD (problema, solução, user stories, decisões) → Issue ready-for-agent
   ▼
/to-issues         quebra em fatias verticais independentes (1 issue cada)
   ▼
/pegar-issue <N>   claim atômico (label + assignee) + branch <tipo>/<slug>-<N> + carrega a spec
   ▼
/tdd               red → green → refactor; critérios de aceite = testes de integração
   ▼
/ship              Gate 1 — code-review (sempre)
                   Gate 2 — security-review (se toca auth/RLS/migrations/env/webhook)
                   Gate 3 — CI verde (GitHub Actions)
                   → bump de versão → self-approve → squash merge (Closes #N)
                   ▼
/deploy ship       Coolify + migrations + health + version-match + rollback
                   → state.json + history.json + CHANGELOG + snapshot/ARQUITETURA
```

## Onde acho as coisas

| Pergunta | Olhar em |
|---|---|
| O que tem pra fazer / o que tô fazendo? | GitHub Issues (`/pegar-issue` lista a fila) |
| Qual o contexto deste trabalho? | A própria Issue (`gh issue view <N>`) — é a fonte da verdade |
| Glossário do domínio (Ata, Pendência, Envelope…)? | `CONTEXT.md` |
| Por que decidimos X (decisão arquitetural)? | `docs/adr/` |
| Como o time trabalha (claim, labels, paralelismo)? | `docs/agents/` |
| Como a app funciona hoje (visão geral)? | `docs/ARQUITETURA.md` |
| Mapa factual detalhado (rotas, schema, integrações)? | `docs/spec/snapshots/` |
| O que está em produção? | `docs/spec/deploy/state.json` |
| Timeline de deploys (o que mudou desde quando)? | `docs/spec/CHANGELOG.md` |

## Regras importantes

1. **Nunca commitar em `main` direto.** Sempre PR via `/ship`.
2. **Self-approval é OK** — os 3 gates (code-review + security-review + CI) validam. Cada um aprova o próprio PR.
3. **Nunca pular `/security-review`** em mudanças que tocam auth, RLS, migrations, env vars ou webhooks.
4. **O contexto do trabalho vive na Issue**, não em arquivo de plano. Os critérios de aceite da Issue viram os seus testes no `/tdd`.
5. **Uma Issue por vez, uma branch por Issue.** Em paralelo (vários terminais), use **1 git worktree por issue** — o claim atômico evita que duas sessões peguem a mesma. Protocolo em `docs/agents/issue-tracker.md`.
6. **Skills locais ficam em `.claude/skills/`** — não mexa sem confirmar comigo (Pedro). Mudanças aqui são "skills do time".

## Notificações

GitHub Mobile (app no celular) é o canal de notificação. Marca o repo como "Watching" pra receber:
- PR aberto / aprovado / mergeado
- CI passou / falhou
- Review pedida / recebida
- Comentário em PR ou Issue

Sem Discord, sem Slack.

## Atalhos úteis

| Comando | Pra que |
|---|---|
| `/grill-with-docs` | Lapida uma ideia nova contra o domínio (entry de ideação) |
| `/to-prd` | Vira a conversa num PRD = 1 Issue `ready-for-agent` |
| `/to-issues` | Quebra o PRD em fatias verticais (1 issue cada) |
| `/pegar-issue` | Sem arg: lista a fila. Com `<N>`: claim + branch + spec |
| `/tdd` | Red → green → refactor (testes a partir dos critérios de aceite) |
| `/ship` | Commit → PR → 3 gates → merge → deploy |
| `/deploy status` | Ver estado de produção (sem alterar) |
| `/deploy rollback` | Reverte produção pro deploy anterior |
| `/diagnose` | Investigação raiz de bug |
| `/snapshot --check` | Dry-run do mapa da app |
| `/atualizar-app` | Rebuild docker-compose local (não toca produção) |
| `/passagem` | Passa o contexto desta sessão pra outra (quando a janela enche) |

## Quando algo dá errado

- **`/tdd` vermelho e não fecha?** O teste é a spec — confira o critério de aceite na Issue. Se o critério está errado, ajuste a Issue primeiro.
- **`/ship` reprovou num gate?** A saída diz qual (code-review, security-review ou CI). Corrija e rode `/ship` de novo — ele retoma.
- **Conflito com a `main`?** `git pull --rebase origin main` na sua branch, resolve os conflitos, segue.
- **Deploy falhou em produção?** `/deploy` tem rollback automático; `/deploy status` mostra o estado. O motivo fica em `docs/spec/deploy/history.json`.
- **Snapshot desatualizado?** `/snapshot --force`.
- Na dúvida, pergunta pro Claude — ele puxa o conhecimento daqui.

## Pra aprofundar

- **[`claude-setup.md`](./claude-setup.md)** — setup do Claude Code pra este projeto (plugins, CLI do Coolify, permissions). Faça uma vez.
- **Painel do workflow** — guia visual do fluxo + dados vivos: `python3 tools/workflow-dashboard/serve.py` (abre em http://localhost:8765).
- `CLAUDE.md` (raiz) — regras gerais do projeto.
- `CONTEXT.md` + `docs/adr/` — domínio e decisões.
- `docs/agents/` — `issue-tracker.md` (claim/paralelismo), `triage-labels.md`, `domain.md`.
- `docs/ARQUITETURA.md` + `docs/spec/snapshots/` — como a app funciona hoje.

**Em caso de dúvida, pergunta pro Pedro ou abre uma Issue (`/grill-with-docs` pra ideias; templates de bug/feature no GitHub).**
