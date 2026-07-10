---
name: onda
description: Executor autônomo (AFK) da fila de issues em ondas, com checkpoint humano por lote e deploy único no fim de cada onda. Orquestra o pipeline pegar-issue → tdd → ship em paralelo (2-3 issues por vez, 1 worktree por issue), para UMA vez no seu OK de merge, mergeia sequencial e faz um deploy, depois reabastece com as issues recém-destravadas até a fila esvaziar. Sinaliza no fim o que fechou e o que virou ready-for-human. Implementa o ADR 0022. Use quando o usuário disser "onda", "/onda", "esvazia a fila", "roda as issues sozinho", "modo AFK", "toca o backlog", "pega todas as issues prontas", "roda o PRD N", ou quando terminou de planejar as issues no GitHub e quer que os agentes toquem daqui. Sintaxe `/onda [#PRD | --all] [--paralelo N]`. NÃO revoga o gate humano de merge (push na main é ação humana).
---

# Onda — execução autônoma da fila em ondas

Modo AFK do pipeline. Em vez de uma sessão humana por issue, esta sessão vira **orquestrador**: seleciona issues desbloqueadas, dispara o ciclo de desenvolvimento em paralelo (1 worktree por issue) até cada uma virar um PR com os 3 gates verdes, para **uma vez** no seu OK de merge, mergeia sequencial e faz **um** deploy no fim da onda. Depois reabastece e repete até a fila esvaziar. Racional, alternativas rejeitadas e consequências no **ADR 0022**.

> **Invariante inegociável:** push na main é ação humana (merge = deploy em prod). A `/onda` é autônoma **até o PR verde**; o merge e o deploy só acontecem depois do seu OK explícito por onda. Nunca mergeie sem passar pelo checkpoint.

## Sintaxe

```
/onda [#PRD | --all] [--paralelo N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `#PRD` | (nenhum) | Escopa a fila às sub-issues **desse PRD** (ex.: `/onda #200`). Só entram fatias do PRD que estejam prontas e desbloqueadas. |
| `--all` | (implícito se sem arg) | Toda a fila `ready-for-agent` sem dono e sem bloqueio, de qualquer PRD. |
| `--paralelo N` | `3` | Quantas issues rodam em paralelo por onda. Teto recomendado 3 (ADR 0022: 2-3 dá paralelismo real sem concentrar as corridas de migration/lockfile/bump). |

## O objetivo (goal)

A onda é um **loop com goal**: o estado final desejado é **fila-alvo vazia, tudo mergeado e um deploy verde por onda**, ou uma lista honesta do que não fechou. A skill só termina quando não há mais issue desbloqueada para pegar. No fim, sinaliza sucesso ou falha (ver [Sinal final](#7-sinal-final-o-goal)).

## Fluxo

### 1. Montar a fila-alvo

Antes de tudo, o **loop do revisor (ADR 0020)**: se houver issues `revisor-comentou`, pare e avise — curadoria humana vem antes de qualquer onda (protocolo no `/triage`). Não inicie a onda por cima de pedido de revisor pendente.

Depois monte a fila:

- Com `#PRD`: liste as sub-issues do PRD e filtre as prontas/sem dono.
  ```bash
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  gh api "repos/$REPO/issues/<PRD>/sub_issues" --jq '.[].number'
  ```
- Com `--all` (ou sem arg): a fila padrão do protocolo.
  ```bash
  gh issue list --label ready-for-agent --search "no:assignee" \
    --json number,title,labels --jq '.[] | {number, title, labels: [.labels[].name]}'
  ```

**Descarte** as que têm label `blocked` ou `Bloqueada por: #X` com `#X` ainda aberta. Só entram issues sem bloqueio aberto (regra da fila em `docs/agents/issue-tracker.md`). Ordene fatias menores primeiro (`fatia:P` antes de `fatia:M`/`fatia:G`) para o lote fechar mais rápido.

Mostre a fila-alvo em tabela e diga quantas ondas prevê (fila ÷ paralelo). Isso é AFK: siga sem pedir confirmação de arranque; o primeiro toque humano é o checkpoint de merge.

### 2. Disparar o lote em paralelo (até PR verde)

Pegue as próximas `N` issues desbloqueadas. Para cada uma, dispare um **sub-agente isolado em worktree** (Agent tool com `isolation: worktree`, ou `EnterWorktree`) que executa o ciclo completo até o PR ficar verde, **sem mergear**. Dispare os `N` na mesma mensagem para rodarem de verdade em paralelo.

Cada sub-agente recebe como goal a issue e seus **critérios de aceite** (viram a lista de testes do `/tdd`), e executa:

1. **Claim atômico** (o lock, evita colisão com outra sessão):
   ```bash
   gh issue edit <N> --remove-label ready-for-agent --add-label in-progress --add-assignee @me
   ```
   Releia os donos logo após; se houver mais de um, abra mão e pule (verificação anti-corrida do protocolo).
2. **Worktree próprio**: branch determinística `<type>/<slug>-<N>`, isolada.
3. **`/tdd`**: red → green → refactor até os critérios de aceite passarem.
4. **Gates + PR**: roda `/ship "<desc>" --issue <N> --no-merge` (abre o PR com `Closes #N`, roda os 3 gates: `/code-review`, `/security-review`, testes). **Atenção ao gate de segurança em worktree**: a `/security-review` lê o diff da árvore principal, não do worktree ([[project_security_review_diff_errado]]) — o sub-agente precisa escopar o diff explicitamente e sinalizar se não conseguiu confirmar o escopo.
5. Retorna um **status estruturado**: `{issue, pr, verde: bool, tentativas, notas}`.

**Regras de segurança do sub-agente** (obrigatórias no prompt): proibido `git checkout --`, `git reset --hard`, `git stash drop` ou qualquer comando destrutivo em arquivos que não sejam os da própria issue ([[feedback_agent_git_safety]]). Cada sessão confere `git branch --show-current` antes de commitar ([[feedback_verificar_branch_antes_commit]]).

### 3. Política de falha: marcar e seguir

Issue que não fecha os 3 gates em **3 tentativas** não trava a onda. O sub-agente:
```bash
gh issue edit <N> --remove-label in-progress --add-label ready-for-human
gh issue comment <N> --body "Onda parou aqui após 3 tentativas. Branch: <branch>. Falhou em: <gate>. Hipótese: <...>"
```
A onda registra a baixa e continua. As baixas aparecem no checkpoint. A fila nunca trava por uma issue ruim.

### 4. Checkpoint humano do lote (o único toque)

Quando todos os `N` do lote viraram PR verde (ou baixa), **pare** e apresente o lote:

- Tabela: issue · PR# · status (verde / ready-for-human) · fatia.
- Para os verdes, os PRs prontos para merge.

Peça o OK de merge com **AskUserQuestion citando os PR#** explicitamente ([[feedback_push_main_humano]]) — "pode seguir" genérico não basta, o gate é real. Ofereça: mergear o lote todo, um subconjunto, ou abortar a onda.

### 5. Merge sequencial + deploy único

Aprovado, mergeie **um a um** (nunca em lote paralelo) seguindo o playbook manual ([[project_deploy_ops_manual_ship]], [[project_bump_race_sessoes_paralelas]]):

- **Bump de versão um a um**, re-conferindo `origin/main` (package.json + `ls` de migrations) **antes de cada push** — rebase pode engolir o commit de bump; re-bumpar/renumerar se colidiu.
- `APP_VERSION` atualizado **antes** do merge (o `/health` lê no startup).
- Conflito de lockfile entre branches → `git checkout --ours` + regenerar (`uv lock`; `pnpm@9 install --no-frozen-lockfile`) ([[project_lockfile_merge_integracao]]).
- Merge via `gh pr merge` (ou fallback `gh api -X PUT .../pulls/N/merge -f merge_method=squash` se der 401 — [[project_gh_pr_merge_401]]).

Feitos todos os merges do lote, **um único** `/deploy ship` no fim da onda (evita N rebuilds do Coolify, que rebuilda tudo a cada push com `watch_paths=null`). O `/deploy` roda health + rollback e regenera o snapshot.

### 6. Reabastecer e repetir

Deploy verde: as issues que estavam `blocked` por dependências recém-fechadas se destravam. Faça a varredura (remover `blocked`, adicionar `ready-for-agent` nas que ficaram sem dependência aberta) e volte ao passo 1. Repita até a fila-alvo esvaziar.

### 7. Sinal final (o goal)

Quando não houver mais issue desbloqueada, encerre com um **relatório único**, sem tom de babá:

- ✅ **Fechadas e deployadas:** issue · PR · versão de deploy.
- ⚠️ **ready-for-human:** issue · onde parou · hipótese (as baixas).
- ⛔ **Ainda bloqueadas:** issue · por qual dependência.
- **Deploys da sessão:** versões e status de health de cada onda.
- Veredito: **tudo ocorreu bem** (fila-alvo vazia, todos os deploys verdes) ou **parcial/falha** (com o quê e por quê).

Notifique proativamente (o usuário está AFK) via `SendUserFile`/push se houver artefato, ou mensagem clara de conclusão.

## Limites (o que a /onda NÃO faz)

- **Não revoga o gate de merge.** Autonomia total até prod foi rejeitada no ADR 0022 (rollback nunca exercitado em prod; security-review frágil em worktree). Se o usuário pedir "sem checkpoint", recuse e explique o ADR.
- **Não substitui** o fluxo interativo. `/pegar-issue` + `/tdd` em terminais separados continua válido para trabalho que quer acompanhamento fino. A `/onda` é o modo de esvaziar a fila.
- **Não inventa doc de estado.** O registro vive na Issue/PR + `history.json` (regra do `CLAUDE.md`). A onda não escreve chronicles nem dashboards.

## Uso em sessão fresca

Numa sessão nova, com esta skill carregada, basta:
```
/onda #200
```
Ela lê o PRD #200, monta a fila com as fatias prontas (#201-#204), e toca as ondas até o deploy final, parando só no seu OK de merge por lote.
