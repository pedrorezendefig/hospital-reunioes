---
name: pegar-issue
description: Pega uma issue ready-for-agent do GitHub para desenvolver — faz o "claim" atômico (label + assignee), cria a branch e carrega a spec (pt-BR) no contexto para o /tdd. Sem argumento, lista a fila de issues disponíveis. Use quando o usuário disser "pegar issue", "/pegar-issue", "trabalhar na issue N", "qual issue pego", "o que tem pra fazer", "lista a fila", "pega a próxima", ou quiser começar a desenvolver. Coordena sessões paralelas — cada terminal pega uma issue distinta sem colisão.
---

# Pegar issue

Entry point de **desenvolvimento**. Pega uma issue da fila `ready-for-agent`, dá "claim" para evitar colisão entre sessões paralelas, cria a branch e carrega a spec no contexto. Protocolo completo em `docs/agents/issue-tracker.md`.

## Sem argumento — listar a fila

**Antes da fila, o loop do revisor (ADR 0020).** Issues com `revisor-comentou` vêm **no topo** — inclusive fechadas (um pedido de mudança do revisor reabre trabalho entregue):

```bash
gh issue list --label revisor-comentou --state all \
  --json number,title,state --jq '.[] | {number, title, state}'
```

Se houver alguma, mostre num bloco separado ("🔔 Revisor comentou — curadoria pendente") e recomende tratá-las antes de pegar issue nova. A curadoria (ler o comentário, classificar, reabrir/editar critérios sob aprovação humana) segue o protocolo do `/triage`.

Depois, mostre as issues disponíveis (prontas e sem dono):

```bash
gh issue list --label ready-for-agent --search "no:assignee" \
  --json number,title,labels --jq '.[] | {number, title, labels: [.labels[].name]}'
```

Apresente como tabela em pt-BR (número · título · tipo AFK/HITL, se marcado). **Não** ofereça issues com label `blocked`. Pergunte qual número pegar — ou, se o usuário disser "pega a próxima", pegue a primeira AFK e siga.

## Com argumento `<N>` — pegar a issue

### 1. Ler a issue
```bash
gh issue view <N> --comments
```
Leia o corpo completo (**O que construir**, **Critérios de aceite**, **Bloqueada por**) e os comentários.

### 2. Checar bloqueio
Se houver "Bloqueada por: #X" e a `#X` ainda estiver **aberta**, avise e **não pegue** — sugira pegar outra issue desbloqueada.

### 3. Claim atômico (o "lock")
```bash
gh issue edit <N> --remove-label ready-for-agent --add-label in-progress --add-assignee @me
```
Se o `--remove-label` falhar porque `ready-for-agent` já não estava lá, **outra sessão pegou primeiro** — avise e pare.

### 4. Verificação anti-corrida
```bash
gh issue view <N> --json assignees --jq '.assignees[].login'
```
Se aparecer **mais de um dono**, abra mão e pegue a próxima:
```bash
gh issue edit <N> --remove-assignee @me
```

### 5. Criar a branch
Derive o tipo do label `type:*` (feature→`feat`, fix→`fix`, etc.) e um slug curto do título. Branch determinística por número (nunca colide):
```bash
git checkout -b <type>/<slug>-<N>
```

### 6. Carregar contexto e ir para o TDD
Carregue no contexto **O que construir** + **Critérios de aceite** (cada critério vira um teste). Leia `CONTEXT.md` e os ADRs relevantes em `docs/adr/`. Então invoque **`/tdd`** — cada critério de aceite é um teste RED.

## Sessões paralelas (worktree)

Para rodar várias issues ao mesmo tempo na mesma máquina, cada sessão usa um **git worktree** próprio (sem Docker):
```bash
git worktree add ../hospital-issue-<N> -b <type>/<slug>-<N>
```
Abra o Claude Code dentro de `../hospital-issue-<N>`. Veja `docs/agents/issue-tracker.md`.

## Fechar o loop

Terminado o `/tdd` (testes verdes), invoque **`/ship`** — abre o PR com `Closes #N`, roda os gates, mergeia e faz o deploy. Ao mergear, a issue fecha e a Action de higiene (`.github/workflows/higiene-issues.yml`) remove o `in-progress` sozinha.

Abandonou? Devolva ao pool:
```bash
gh issue edit <N> --remove-assignee @me --remove-label in-progress --add-label ready-for-agent
```
