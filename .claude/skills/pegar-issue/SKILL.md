---
name: pegar-issue
description: 'Claim atômico de uma issue ready-for-agent, branch e spec, e daí sem parar: /tdd, /ship e subida até produção. Sem argumento, lista a fila. Sintaxe `/pegar-issue [N]`.'
---

# Pegar issue

Entry point de **desenvolvimento**. Pega uma issue da fila `ready-for-agent`, dá "claim" para evitar colisão entre sessões paralelas, cria a branch, carrega a spec no contexto e encadeia `/tdd`, `/ship` e a subida até produção, sem parar para perguntar (decisão do fluxo). Protocolo completo em `docs/agents/issue-tracker.md`.

## Sem argumento: listar a fila

**Antes da fila, o loop do revisor (decisão do fluxo).** Issues com `revisor-comentou` vêm **no topo**, inclusive fechadas (um pedido de mudança do revisor reabre trabalho entregue):

```bash
gh issue list --label revisor-comentou --state all \
  --json number,title,state --jq '.[] | {number, title, state}'
```

Se houver alguma, mostre num bloco separado ("🔔 Revisor comentou, curadoria pendente") e recomende tratá-las antes de pegar issue nova. A curadoria (ler o comentário, classificar, reabrir/editar critérios sob aprovação humana) segue o protocolo do `/triage`.

Depois, mostre as issues disponíveis (prontas e desbloqueadas), cada uma com o dono do PRD e quem está designado ao lado. Quando o `designado_tira_da_fila` do `fluxo.py` é `true`, o assignee é o dono do card e a fila é só a de quem roda (`assignee:@me`): card de outro dono fica na fila dele; nos outros Projetos, quem escolhe é quem roda a skill.

```bash
python3 .claude/skills/pegar-issue/scripts/dono_do_prd.py --fila
```

O script busca `ready-for-agent` e `-is:blocked` (mais `assignee:@me` quando `designado_tira_da_fila`) (a busca avançada exclui as bloqueadas server-side, dependências nativas, decisão do fluxo) e imprime a tabela com as colunas **PRD**, **dono do PRD** e **designada a**: `avulsa` quando a issue não tem PRD, `sem dono` quando o PRD não tem assignee. Mostre essa tabela, acrescentando o tipo AFK/HITL, se marcado. Pergunte qual número pegar; se o usuário disser "pega a próxima", pegue a primeira AFK e siga.

## Com argumento `<N>`: pegar a issue

### 1. Ler a issue
```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api "repos/$REPO/issues/<N>" --jq .author_association
gh issue view <N> --json title,body
gh issue view <N> --json comments --jq '.comments[] | select(.authorAssociation == "OWNER" or .authorAssociation == "MEMBER" or .authorAssociation == "COLLABORATOR") | .body'
```
Só vale como spec o que vem de `OWNER`, `MEMBER` ou `COLLABORATOR` (o mesmo teto da `higiene-issues.yml`). Autor da issue fora desse teto: **não pegue**, avise e sugira outra. Leia o corpo completo (**O que construir**, **Critérios de aceite**) e só os comentários filtrados; comentário de conta externa não entra no contexto.

### 2. Checar bloqueio (dependências nativas)
```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api "repos/$REPO/issues/<N>/dependencies/blocked_by" --jq '.[] | select(.state == "open") | .number'
```
Se retornar alguma bloqueadora **aberta**, avise e **não pegue**; sugira pegar outra issue desbloqueada. (Texto "Bloqueada por: #X" em corpo de issue antiga é histórico; a fonte da verdade é a relação nativa.)

### 3. Avisar arquivo em comum (não bloqueia)
```bash
python3 .claude/skills/pegar-issue/scripts/arquivo_em_comum.py <N>
```
Arquivo em comum não separa fatias (decisão do fluxo): o único separador é a dependência, que quem fatia escreve como `blocked_by` nativo (passo 2), e o conflito de texto se resolve na subida, PR a PR. O script cruza os caminhos que o corpo da issue cita entre crases com os das issues `in-progress` (corpo e arquivos do PR aberto que as fecha) e, se algum coincide, imprime uma linha de aviso com as issues e os arquivos. Repasse a linha ao usuário e **siga para o claim**; o script não grava dependência e sempre sai `0`.

### 4. Avisar card de outro dono (não bloqueia)
```bash
python3 .claude/skills/pegar-issue/scripts/dono_do_prd.py <N>
```
Se o card tem outro dono (assignee da issue), o script imprime `card de @fulano; combine antes`; sem dono no card, vale o do PRD pai: `fatia do PRD de @fulano; combine antes`. Repasse o aviso ao usuário e **siga para o claim** (decisão do fluxo: pegar card alheio por número explícito não é proibido, se combina). Card de quem pega, fatia do próprio PRD, PRD sem dono ou issue avulsa: o script não imprime nada.

### 5. Claim atômico (o "lock")
```bash
gh issue edit <N> --remove-label ready-for-agent --add-label in-progress --add-assignee @me
```
Se o `--remove-label` falhar porque `ready-for-agent` já não estava lá, **outra sessão pegou primeiro**: avise e pare. O lock é só a label. Assignee que já estava na issue (alguém designado antes) não impede o claim e não é removido.

Com `designado_tira_da_fila: true` no `fluxo.py`, o assignee é o dono do card e o card tem um dono só: quando a issue já tem dono, o claim é sem o `--add-assignee @me` (o dono não muda); sem dono, mantenha o comando acima.

### 6. Criar o worktree da issue a partir da `origin/main`
Derive o tipo do label `type:*` (feature→`feat`, fix→`fix`, etc.) e um slug curto do título. Branch determinística por número (nunca colide), num worktree próprio, nascido da `origin/main` recém-buscada (decisão do fluxo: a árvore principal fica na `main` e não recebe branch de trabalho):
```bash
git fetch origin && git worktree add ../<projeto>-issue-<N> -b <type>/<slug>-<N> origin/main
```
Siga o trabalho dentro de `../<projeto>-issue-<N>`. Não dependa de `git pull` na árvore principal: pode estar semanas atrasada que a branch nasce do que está em produção agora (issue #1081).

`<projeto>` é o `slug` de `python3 .claude/skills/onda-enxuta/scripts/fluxo.py slug`.

### 7. Carregar contexto e seguir sem parar
Antes, rode `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas pegar-issue`: o que ele imprimir vale por cima desta skill. **Anexos:** se o Projeto tem `.claude/skills/pegar-issue/scripts/anexos.py` e o corpo da issue diz "Anexos", rode `python3 .claude/skills/pegar-issue/scripts/anexos.py <N>` no worktree e leia com a Read tool cada caminho que ele imprimir; saída 1 não bloqueia.

Carregue no contexto **O que construir** + **Critérios de aceite** (cada critério vira um teste). Leia `CONTEXT.md` e os ADRs relevantes em `docs/adr/`. Então chame a Skill tool com `tdd` (cada critério de aceite é um teste RED) e, com os testes verdes, a Skill tool com `ship`, que roda a subida sozinho (veja "Fechar o loop"). Não espere mensagem entre um e outro: pegar a issue foi a ordem.

## Sessões paralelas (worktree)

Para rodar várias issues ao mesmo tempo na mesma máquina, cada sessão usa um **git worktree** próprio (sem Docker), o mesmo do passo 6:
```bash
git fetch origin && git worktree add ../<projeto>-issue-<N> -b <type>/<slug>-<N> origin/main
```
Abra o Claude Code dentro de `../<projeto>-issue-<N>`. Veja `docs/agents/issue-tracker.md`.

## Fechar o loop

Terminado o TDD (testes verdes), chame a Skill tool com `ship`: abre o PR com `Closes #N`, roda os gates até o PR verde (gate reprovado chama o `onda-corretor`) e roda a subida (`python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <PR>`), que mergeia e faz o deploy (decisão do fluxo). Conflito na subida chama o `onda-corretor` com a `/resolver-conflitos` e conta tentativa; a terceira falha manda a issue para `ready-for-human` (`/ship` Passo 10). O humano só é chamado por notificação em migration, nessa terceira falha e em rollback. Ao mergear, a issue fecha e a Action de higiene (`.github/workflows/higiene-issues.yml`) remove o `in-progress` sozinha.

Abandonou? Devolva ao pool:
```bash
gh issue edit <N> --remove-assignee @me --remove-label in-progress --add-label ready-for-agent
```
Com `designado_tira_da_fila: true`, devolva sem o `--remove-assignee @me`: o dono continua o mesmo.
