---
name: pegar-issue
description: Faz o claim atômico de uma issue ready-for-agent (label + assignee), cria a branch e carrega a spec para o /tdd. Sem argumento, lista a fila. Sintaxe `/pegar-issue [N]`.
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
gh issue list --label ready-for-agent --search "no:assignee -is:blocked" \
  --json number,title,labels --jq '.[] | {number, title, labels: [.labels[].name]}'
```

O `-is:blocked` já exclui as bloqueadas server-side (dependências nativas, ADR 0028). Apresente como tabela em pt-BR (número · título · tipo AFK/HITL, se marcado). Pergunte qual número pegar; se o usuário disser "pega a próxima", pegue a primeira AFK e siga.

## Com argumento `<N>` — pegar a issue

### 1. Ler a issue
```bash
gh issue view <N> --comments
```
Leia o corpo completo (**O que construir**, **Critérios de aceite**) e os comentários.

### 2. Checar bloqueio (dependências nativas)
```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api "repos/$REPO/issues/<N>/dependencies/blocked_by" --jq '.[] | select(.state == "open") | .number'
```
Se retornar alguma bloqueadora **aberta**, avise e **não pegue**; sugira pegar outra issue desbloqueada. (Texto "Bloqueada por: #X" em corpo de issue antiga é histórico; a fonte da verdade é a relação nativa.)

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
