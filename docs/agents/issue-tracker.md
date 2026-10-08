# Issue tracker: GitHub

As issues e PRDs deste repositório vivem como **GitHub Issues**. Use o `gh` CLI para tudo — o repositório é inferido do `git remote` automaticamente quando rodado dentro do clone.

> **Idioma:** todo conteúdo de issue voltado ao time é em **pt-BR** (título, corpo, user stories, critérios de aceite, comentários). Veja a regra de idioma no `CLAUDE.md`.

## Comandos essenciais

- **Criar issue:** `gh issue create --title "..." --body "..."` (use heredoc para corpo multilinha).
- **Ler issue:** `gh issue view <N> --comments`.
- **Listar issues:** `gh issue list --state open --json number,title,labels,assignees`.
- **Comentar:** `gh issue comment <N> --body "..."`.
- **Aplicar/remover label:** `gh issue edit <N> --add-label "..." --remove-label "..."`.
- **Fechar:** `gh issue close <N> --comment "..."` — ou automático via `Closes #N` no merge do PR.

Quando uma skill disser **"publicar no issue tracker"** → criar uma GitHub Issue.
Quando disser **"buscar o ticket"** → `gh issue view <N> --comments`.

## Hierarquia: PRD → fatias (sub-issues nativas)

O `/to-prd` cria a issue grande (o **PRD**); o `/to-issues` quebra em fatias e registra cada uma como **sub-issue nativa** do PRD — não só a menção `Pai: #N` no corpo, mas o vínculo estrutural do GitHub (barra de progresso "X de Y concluídas" no PRD + navegação pai↔filha na UI).

- **Vincular uma fatia ao PRD** (o `sub_issue_id` é o *database id* da filha, **não** o número):
  ```bash
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  CHILD_ID=$(gh api "repos/$REPO/issues/<fatia>" --jq '.id')
  gh api --method POST "repos/$REPO/issues/<PRD>/sub_issues" -F sub_issue_id="$CHILD_ID"
  ```
- **Listar as fatias de um PRD:** `gh api "repos/$REPO/issues/<PRD>/sub_issues" --jq '.[].number'`.
- **De que PRD veio uma fatia:** a seção `Pai: #N` no corpo, ou o painel de sub-issues na UI da própria fatia.
- Quando a **última fatia aberta** fecha, a [Action de higiene](#higiene-de-fechamento-github-action) fecha o PRD sozinha, com um comentário. O **claim e o paralelismo (abaixo) acontecem nas fatias**, não no PRD.
- **Emenda (ADR 0068): o PRD tem dono.** O `/to-prd` põe como assignee do PRD quem fez o grilling. Isso não é claim (ninguém "trabalha o PRD"), é responsabilidade: fatia ainda sem claim conta, para efeito de visão, como do dono do PRD. O Hospital OS (painel local) filtra a aba Issues por quem está designado (assignee), sem herdar o dono do PRD (ADR 0068).
- **Issue nascida de uma Demanda (botão "Levar para desenvolvimento", ADR 0054) nasce designada ao responsável do card.** Em `needs-triage` esse assignee é responsabilidade, não claim, pela mesma leitura do dono do PRD. A `/triage` tira o assignee ao mover para `ready-for-agent`, porque o pool é `no:assignee`. O Hospital OS marca essas issues com o chip "Demanda".

## Higiene de fechamento (GitHub Action)

A Action `.github/workflows/higiene-issues.yml` dispara no evento `issues.closed`, para **qualquer** fechamento (merge com `Closes #N`, web, ou manual), e garante que o status nunca minta (ADR 0068):

1. Remove as labels de estado (`in-progress`, `ready-for-agent`, `blocked`) da issue fechada.
2. Se ela era a **última sub-issue aberta** de um PRD, fecha o PRD com um comentário — limpando as labels do PRD na mesma run (o fechamento via `GITHUB_TOKEN` não re-dispara a Action).

Nenhuma skill ou passo manual cuida disso — a higiene é event-driven de propósito.

## Snapshot e draft do Manual (GitHub Action)

A Action `.github/workflows/pos-merge.yml` dispara em todo push na `main` e faz o que saiu da subida (ADR 0068): o `fechar_onda.py` grava só `history.json` e `state.json`, e o resto é dela.

1. Tira do `draft` as páginas do Manual dos PRDs do último deploy do `history.json` (`tools/tirar_draft_manual.py`). Deploy sem PRD (PR avulso) pula o passo; página com Vídeo de tarefa fica em draft com um aviso no run, porque o MP4 não vem no clone (issue #951).
2. Regenera o mapa factual (`docs/spec/snapshots/` e os blocos AUTO do `docs/ARQUITETURA.md`) com o backend montado como no CI, sem o modo parcial da máquina local.
3. Com diff, commita direto na `main` como `github-actions[bot]`, com `[skip ci]`. Quem empurra é a deploy key da Action, num job separado que não instala nada; o ruleset da `main` dá bypass a ela e a mais ninguém (`.github/rulesets/main.json`, ADR 0068).

O `[skip ci]` impede o push do bot de redisparar workflow, e o filtro de caminhos da Action ignora o que ela mesma escreve. Nenhuma skill nem a subida roda snapshot ou draft.

## Loop do revisor (ADR 0068)

O **revisor** (papel; o **diretor** é o caso canônico) acompanha as issues pelo GitHub web/mobile e comenta. O mecanismo **independe da pessoa** — o que dispara o loop é o comentário e o contexto que ele adiciona:

1. **Acesso:** o revisor entra como colaborador com papel **Triage** (vê, comenta e rotula; não toca em código):
   ```bash
   REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
   gh api -X PUT "repos/$REPO/collaborators/<login>" -f permission=triage
   ```
   Ele recebe o convite por email/GitHub e precisa aceitar. (O revisor de teste atual, `pedrorezendefig`, é o dono do repo — o acesso já existe.)
2. **Quem é revisor é configuração:** a repository variable `REVIEWER_LOGINS` (lista separada por vírgula; default `pedrorezendefig` definido no workflow). Trocar o revisor é trocar a variable — sem commit:
   ```bash
   gh variable set REVIEWER_LOGINS --body "login1,login2"
   ```
3. **Detecção (dois gatilhos):** a mesma Action de higiene dispara em `issue_comment.created` e acende `revisor-comentou` numa **issue** quando o autor é um login da lista, **ou** quando o corpo do comentário traz o marcador `<!-- revisor-app` (ADR 0054, decisão 4). O marcador vale antes de `REVIEWER_LOGINS` e independe do login: é a assinatura do revisor que não tem conta no GitHub e responde na Conversa da Demanda, com o app espelhando o comentário aqui pelo token da integração. Não é "qualquer um com o marcador acende a label": no caminho do marcador quem segura a porta é o `if:` do job, pelo `author_association` (OWNER, MEMBER, COLLABORATOR), e o comentário espelhado sai justamente pelo token de um colaborador. Comentário de terceiro num repositório público nem chega ao script. A Action **só sinaliza**, nunca reabre nem edita.
4. **Automação não dispara o loop:** a Action ignora comentários em PRs e comentários com marcador de automação: o disclaimer do `/triage` ou `<!-- automacao -->`. Skill ou script que comente numa issue usando a mesma conta do revisor deve incluir um dos dois no corpo. Esse corte vale só para comentário **sem** `<!-- revisor-app`: quem carrega o marcador é voz de revisor e acende a label de qualquer jeito. Por isso o app espelha com `<!-- automacao -->` a resposta de quem tem `github_login` e com `<!-- revisor-app ... -->` a de quem não tem (o que a Action olha é o prefixo `<!-- revisor-app`; os atributos dentro do marcador podem variar).
5. **Curadoria (HITL):** `/triage` e `/pegar-issue` listam as issues `revisor-comentou` no topo. O agente lê o comentário, extrai o contexto, classifica (pedido de mudança vs. elogio/observação) e age sob aprovação humana — protocolo completo na skill `/triage`. Issue **fechada** + pedido de mudança → reabre com o critério novo **desmarcado** (contagem honesta, ex. 6/7); o refazer é um ship de follow-up.

## Desenvolvimento paralelo (N sessões Claude Code, sem Docker)

O `/to-issues` gera issues vertical-slice **independentes**. Várias sessões Claude Code (cada uma rodando Opus, em terminais diferentes) podem trabalhar em paralelo — **uma issue por sessão**. Para não haver colisão, siga o protocolo:

### 1. Ver a fila disponível
```bash
gh issue list --label ready-for-agent --search "no:assignee -is:blocked" \
  --json number,title,labels --jq '.[] | {number, title}'
```
Só aparecem issues **prontas para agente**, **sem dono** e **sem bloqueio aberto** (o `-is:blocked` filtra server-side pelas dependências nativas; veja abaixo).

### 2. Claim atômico (o "lock")
Ao escolher a issue `<N>`, marque-a sua imediatamente:
```bash
gh issue edit <N> --remove-label ready-for-agent --add-label in-progress --add-assignee @me
```
O `--remove-label ready-for-agent` é o lock: a issue **some da fila** para qualquer outra sessão.

### 3. Verificação anti-corrida (defensiva)
Logo após o claim, releia os donos:
```bash
gh issue view <N> --json assignees --jq '.assignees[].login'
```
Se aparecer **mais de um dono** (duas sessões pegaram quase ao mesmo tempo), abra mão e pegue a próxima:
```bash
gh issue edit <N> --remove-assignee @me   # devolve para quem chegou primeiro
```

### 4. Isolar o filesystem: 1 worktree por issue
Para rodar em paralelo de verdade na mesma máquina, cada sessão trabalha num **git worktree** próprio (branches isoladas, mesmo `.git`, sem Docker), nascido da `origin/main` recém-buscada, e não do HEAD da árvore principal, que pode estar atrasado (issue #1081):
```bash
git fetch origin && git worktree add ../hospital-issue-<N> -b <type>/<slug>-<N> origin/main
```
Abra a sessão Claude Code dentro de `../hospital-issue-<N>`. O `EnterWorktree` nativo do Claude Code também resolve isso; nesse caso confira com `git log --oneline -1 origin/main` que a branch nasceu da ponta.

### 5. Trabalhar e fechar
- Branch determinística por número da issue: `<type>/<slug>-<N>` → nunca colide com outra.
- O `/tdd` usa os **critérios de aceite** da issue como a lista de testes.
- `/ship` abre o PR com `Closes #N` no corpo → ao mergear, o GitHub **fecha a issue**, e a [Action de higiene](#higiene-de-fechamento-github-action) remove o `in-progress` automaticamente.
- Abandonou? Devolva ao pool: `gh issue edit <N> --remove-assignee @me --remove-label in-progress --add-label ready-for-agent`.
- **Fatia de PRD alheio (ADR 0068):** pode pegar, mas combine antes com o dono do PRD (assignee da issue-raiz). O claim muda o responsável da fatia; o PRD continua do dono.
- **Quem mergeia e deploya é o autor do PR (ADR 0068):** migration em produção e `APP_VERSION` são de quem mergeia. A versão não entra no PR nem vira commit: a subida (`fechar_onda.py`) a define pelo tipo dos commits, em `APP_VERSION` no Coolify e na tag.

## Bloqueios entre issues (dependências nativas)

Dependência entre issues usa o recurso nativo de **issue dependencies** do GitHub ("blocked by"), não texto no corpo (ADR 0068). O formato antigo (`Bloqueada por: #X` no corpo + label `blocked` + varredura manual de destravamento) foi aposentado; o texto remanescente em issues antigas é histórico, a fonte da verdade é a relação nativa.

- **Criar a dependência** (a issue `<N>` é bloqueada pela `<X>`): o endpoint exige o *id global* da bloqueadora, não o número. Com `gh` >= 2.94.0 existe `gh issue edit <N> --add-blocked-by <X>`; com o `gh` atual:
  ```bash
  REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
  BLOCKER_ID=$(gh api "repos/$REPO/issues/<X>" --jq '.id')
  gh api --method POST "repos/$REPO/issues/<N>/dependencies/blocked_by" -F issue_id="$BLOCKER_ID"
  ```
- **Consultar os bloqueios de uma issue:** `gh api "repos/$REPO/issues/<N>/dependencies/blocked_by" --jq '.[].number'` (o `gh` local ainda não expõe `blockedBy` em `--json`).
- **Regra da fila:** a busca resolve tudo server-side; issue bloqueada nem aparece:
  ```bash
  gh issue list --label ready-for-agent --search "no:assignee -is:blocked"
  ```
- **Destravamento é automático:** quando a última bloqueadora fecha, `is:blocked` deixa de casar e a issue reaparece na fila sozinha. Não há varredura manual nem label para flipar; a fatia bloqueada já nasce com `ready-for-agent`.
- **Atenção (REST legado):** automação que use `GET /search/issues` precisa de `advanced_search=true`, senão `is:blocked` é ignorado em silêncio. O `gh issue list --search` já usa a busca certa.
- **Slices realmente independentes** (sem dependência) podem rodar todas ao mesmo tempo. É o caminho mais rápido: prefira "muitas fatias finas independentes" no `/to-issues`.

## Wayfinding operations

Protocolo para a skill `/wayfinder` (planejamento multi-sessão de esforços com névoa; instalada **sob demanda**, ADR 0027). O wayfinder atua **antes** de existir PRD, quando ainda não dá para escrever a spec; quando o mapa limpa (nada mais a decidir), o handoff é para `/to-prd` + `/to-issues`.

- **Mapa** = uma issue com a label `wayfinder:map`. O corpo guarda a *destination* (o que encerra o mapa: uma spec, uma decisão, uma mudança), a seção **Not yet specified** (a névoa) e **Decisions so far** (índice de uma linha por decisão; a decisão vive no ticket, o mapa é índice, não depósito).
- **Tickets** = sub-issues nativas do mapa (mesmo `gh api .../sub_issues` do vínculo PRD → fatias). Cada ticket resolve **uma** decisão ou investigação, com label `wayfinder:<type>` (`research` AFK, `prototype`/`grilling` HITL, `task` conforme marcado).
- **Bloqueio entre tickets** = dependência nativa "blocked by" (mesma mecânica da seção acima).
- **Frontier** (o que está pegável) = filhas abertas, desbloqueadas e **sem assignee**. Liste as filhas com `gh api "repos/$REPO/issues/<mapa>/sub_issues"` e filtre por estado aberto, sem assignee e sem bloqueio nativo aberto.
- **Claim** = assignee apenas (a atribuição é o lock; mesma verificação anti-corrida do protocolo de paralelismo).
- **Tickets wayfinder NUNCA recebem `ready-for-agent`** nem entram na máquina de estados do `/triage`: a fila de execução (`/pegar-issue`, `/onda-enxuta`) enxerga só issues de build. As duas filas não colidem.
- **Resolução:** a resposta vira comentário no ticket, o ticket fecha, e o mapa ganha uma linha em "Decisions so far". Tickets tipo `grilling` usam `/grill-with-docs` (decisões atualizam `CONTEXT.md`/ADR inline).
- **Idioma:** corpo e comentários em pt-BR; os labels técnicos (`wayfinder:map`, `wayfinder:<type>`) ficam em inglês, como commit e merge.
