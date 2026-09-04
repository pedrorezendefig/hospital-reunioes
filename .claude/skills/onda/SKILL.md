---
name: onda
description: Executor AFK da fila de issues em ondas: pegar-issue, tdd e ship em paralelo até PR verde, checkpoint humano de merge, um deploy por onda, auditoria do PRD. Sintaxe `/onda [#PRD | --all]`.
---

# Onda — execução autônoma da fila em ondas

Modo AFK do pipeline. Em vez de uma sessão humana por issue, esta sessão vira **orquestrador**: seleciona issues desbloqueadas, dispara o ciclo de desenvolvimento em paralelo (1 worktree por issue) até cada uma virar um PR verde (CI + spec×diff + revisor independente), para **uma vez** no seu OK de merge, mergeia sequencial e faz **um** deploy no fim da onda. Depois reabastece e repete até a fila esvaziar. Racional, alternativas rejeitadas e consequências no **ADR 0022** (refinado pelo **ADR 0029**: goal de conclusão do PRD, fonte de verdade no GitHub, orquestrador magro; e pelo **ADR 0035**: os gates de review pertencem ao orquestrador).

> **Invariante inegociável:** subir para produção é **decisão** humana (merge = deploy em prod). A `/onda` é autônoma **até o PR verde**; o merge e o deploy só acontecem depois do seu OK explícito por onda. Nunca mergeie sem passar pelo checkpoint.
>
> **O gate é a decisão, não a digitação.** Dado o OK, o orquestrador **executa** o ciclo inteiro sem devolver tarefa: merge, deploy, bookkeeping e push do registro na main. Não entregue comando para o humano digitar por suposição de bloqueio; rode e deixe falhar. Só peça `! <comando>` depois de ver a negativa de verdade naquele turno, dizendo qual comando foi negado. O único passo que segue sendo trabalho manual do humano por limitação real de acesso é **aplicar migration no Studio de produção** (o Postgres não é exposto e o CLI do Coolify não executa SQL).

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

A onda é um **loop com goal**: o estado final desejado é **fila-alvo vazia, tudo mergeado e um deploy verde por onda**, ou uma lista honesta do que não fechou. Escopada com `#PRD`, o goal sobe um degrau: **PRD concluído**, com auditoria ponta a ponta pós-fechamento e reopen em falha (ADR 0029). A skill só termina quando não há mais issue desbloqueada para pegar e, com `#PRD`, o passo 7 (Conclusão do PRD) rodou. No fim, sinaliza sucesso ou falha (ver [Sinal final](#8-sinal-final-o-goal)).

> **Orquestrador magro (ADR 0029):** o orquestrador não lê código, diff nem spec inteira; mantém só a tabela da fila e o status por issue. Toda leitura pesada (PRD, critérios de aceite, diffs) acontece dentro dos sub-agentes, que nascem com contexto fresco. Precisou de um fato do código? Delegue a leitura a um sub-agente.

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
  gh issue list --label ready-for-agent --search "no:assignee -is:blocked" \
    --json number,title,labels --jq '.[] | {number, title, labels: [.labels[].name]}'
  ```

O `-is:blocked` já exclui server-side as issues com dependência nativa aberta (ADR 0028; regra da fila em `docs/agents/issue-tracker.md`). No escopo por `#PRD` (sub-issues via API), confira o bloqueio de cada filha com `gh api "repos/$REPO/issues/<N>/dependencies/blocked_by"`. Ordene fatias menores primeiro (`fatia:P` antes de `fatia:M`/`fatia:G`) para o lote fechar mais rápido.

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
4. **PR sem review interna (ADR 0035)**: roda `/ship "<desc>" --issue <N> --no-merge --skip-review` (abre o PR com `Closes #N`, aguarda o CI). O sub-agente **não** invoca `/code-review` nem `/security-review`: essas skills fazem fan-out de review-agents cujas notificações chegam no orquestrador, e o sub-agente ficaria esperando um veredito que nunca chega (o JSON do fan-out nunca chega ao sub-agente). A review é do orquestrador (passo 2.5). O **Gate 1.5 (spec × diff)** continua com o sub-agente: sem fan-out, funciona em worktree.
5. Retorna um **status estruturado**: `{issue, pr, verde: bool, tentativas, notas}`.

**O status retornado é dica, não contrato (ADR 0029).** A fonte de verdade é o GitHub: a cada notificação de término, o orquestrador confere o estado real via `gh` (PR aberto? CI verde? labels corretas?) antes de dar a issue por concluída. Sub-agente que notificou "completed" mas o estado real não bate é re-engajado via `SendMessage(nome)` para terminar o ciclo. **Nunca** espere gate interno do sub-agente com Monitor nem dispare revisores "v2" por timeout: o único wait de review é a task-notification do revisor do passo 2.5.

**Regras de segurança do sub-agente** (obrigatórias no prompt): proibido `git checkout --`, `git reset --hard`, `git stash drop` ou qualquer comando destrutivo em arquivos que não sejam os da própria issue. Cada sessão confere `git branch --show-current` antes de commitar (o working tree é compartilhado e outra sessão pode trocar a branch). Conflito de merge/rebase no worktree → seguir a skill `resolver-conflitos` (o "nunca `--abort`" dela não revoga estas regras de git safety).

### 2.5. Gate de review do orquestrador (ADR 0035)

Assim que o PR de uma issue abre (CI pode ainda estar rodando), o **orquestrador** dispara **1 revisor independente**: `Agent` fresco, **sem** `isolation: worktree`, contexto limpo, prompt só-leitura ("ache problemas, não aprove, não edite código") com **2 lentes no mesmo prompt**: código e segurança. O revisor lê o diff do PR via `gh pr diff <N>` (nunca a working tree: em worktree a review leria o diff da árvore principal) e **comenta o veredito no PR**.

- **Área sensível** (diff toca auth, permissions, migrations, endpoint público ou env vars): dispare em paralelo um **segundo revisor** dedicado só a segurança.
- **Loop de fix:** achado must-fix volta ao sub-agente da issue via `SendMessage` (worktree ainda vivo); ele corrige e pusha, e o orquestrador dispara nova rodada de revisão. Máximo **2 rodadas**; sem veredito limpo, aplica a política de falha do passo 3.
- "PR verde" para o checkpoint = CI verde + spec×diff verde + veredito limpo do revisor.

### 3. Política de falha: marcar e seguir

Issue que não fecha os gates (CI, spec×diff, revisor independente) em **3 tentativas** não trava a onda. O sub-agente:
```bash
gh issue edit <N> --remove-label in-progress --add-label ready-for-human
gh issue comment <N> --body "Onda parou aqui após 3 tentativas. Branch: <branch>. Falhou em: <gate>. Hipótese: <...>"
```
A onda registra a baixa e continua. As baixas aparecem no checkpoint. A fila nunca trava por uma issue ruim.

### 4. Checkpoint humano do lote (o único toque)

Quando todos os `N` do lote viraram PR verde (ou baixa), **pare** e apresente o lote:

- Tabela: issue · PR# · status (verde / ready-for-human) · fatia.
- Para os verdes, os PRs prontos para merge.

Peça o OK de merge com **AskUserQuestion citando os PR#** explicitamente — "pode seguir" genérico não basta, o gate é real. Ofereça: mergear o lote todo, um subconjunto, ou abortar a onda.

### 5. Merge sequencial + deploy único

Aprovado, mergeie **um a um** (nunca em lote paralelo) seguindo o playbook manual (APP_VERSION no Coolify antes do merge, com a versão final; um serviço por vez, o frontend dá OOM em build concorrente; duas sessões deployando juntas viram corrida de bump):

- **Semáforo primeiro.** Outras `/onda` podem estar no mesmo ponto. Antes do primeiro merge, pegue a trava de deploy (script da skill `/deploy`, seção "Semáforo de deploy"); chave = basename do scratchpad desta sessão, descrição = os PR# do lote:
  ```bash
  .claude/skills/deploy/scripts/semaforo.sh pegar <chave> "onda N: PRs #a, #b, #c"
  ```
  Saída `3` = outra sessão está mergeando ou deployando: chame de novo até pegar, sem devolver nada ao humano (é a fila funcionando). Saída `2` = trava velha: siga a regra da seção. Com a trava na mão, o humano pode ter dado o OK em várias sessões de uma vez; elas se organizam sozinhas.

- **Bump de versão um a um**, re-conferindo `origin/main` (package.json + `ls` de migrations) **antes de cada push** — rebase pode engolir o commit de bump; re-bumpar/renumerar se colidiu.
- `APP_VERSION` atualizado **antes** do merge (o `/health` lê no startup).
- Conflito na integração (lockfile, bump, migration, PR `CONFLICTING`) → siga a skill `resolver-conflitos` (triagem por tipo de arquivo: lockfile se regenera com `git checkout --ours`, nunca hunk a hunk).
- Merge via `gh pr merge` (ou fallback `gh api -X PUT .../pulls/N/merge -f merge_method=squash` se der 401: o `gh pr merge` falha em worktree detached).

Feitos todos os merges do lote, **um único** `/deploy ship` no fim da onda (evita N rebuilds do Coolify, que rebuilda tudo a cada push com `watch_paths=null`). O `/deploy` roda health + rollback e regenera o snapshot. Passe a mesma chave: o `/deploy` reconhece a trava como sua e a solta no fim (Passo 10). Depois que ele voltar, confirme com `semaforo.sh soltar <chave>` (idempotente): a trava nunca pode ficar presa numa sessão que já terminou.

### 6. Reabastecer e repetir

Deploy verde: as issues bloqueadas por dependências recém-fechadas se destravam **sozinhas** (a dependência é nativa; quando a última bloqueadora fecha, `is:blocked` deixa de casar e a issue reaparece na busca da fila). Volte ao passo 1 e remonte a fila. Repita até a fila-alvo esvaziar.

### 7. Conclusão do PRD (só com `#PRD`)

Quando a última fatia fecha, a Action de higiene (ADR 0020) fecha o PRD sozinha, mas fechado não é **verificado** (ADR 0029). Antes do Sinal final, dispare um **sub-agente fresco** que audita:

1. Lê o PRD e extrai os critérios de aceite **do PRD** (não os das fatias, que o `/tdd` já cobriu).
2. Verifica ponta a ponta contra o app deployado: smoke via API/UI, incluindo a **integração entre fatias**.
3. Comenta o resultado no PRD (o que passou, o que não passou, com evidência).
4. Tudo verde: o comentário encerra a auditoria (o PRD já está fechado pela Action). Qualquer falha: **reabre** o PRD com `ready-for-human`.

A autonomia nova é comentar/reabrir a issue do PRD (reversível), não push na main; o invariante do merge continua intacto.

### 8. Sinal final (o goal)

Quando não houver mais issue desbloqueada (e, com `#PRD`, depois que o passo 7 rodou), encerre com um **relatório único**, sem tom de babá:

- ✅ **Fechadas e deployadas:** issue · PR · versão de deploy.
- ⚠️ **ready-for-human:** issue · onde parou · hipótese (as baixas).
- ⛔ **Ainda bloqueadas:** issue · por qual dependência.
- **Deploys da sessão:** versões e status de health de cada onda.
- **Veredito do PRD** (quando escopada com `#PRD`): verificado com evidência comentada, ou reaberto `ready-for-human` com o que falhou.
- Veredito: **tudo ocorreu bem** (fila-alvo vazia, todos os deploys verdes, PRD concluído quando escopada) ou **parcial/falha** (com o quê e por quê).

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
Ela lista as sub-issues do PRD #200, monta a fila com as fatias prontas (#201-#204), toca as ondas até o deploy final parando só no seu OK de merge por lote, e encerra com a auditoria do PRD (reopen se a verificação falhar, ADR 0029).
