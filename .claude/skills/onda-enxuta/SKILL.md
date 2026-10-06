---
name: onda-enxuta
description: 'Executor AFK da fila de issues em ondas: sessão de fundo por onda, mapa por PRD, um push e um build por onda. Sintaxe `/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]`.'
---

# Onda enxuta

É a onda do pipeline (ADRs 0022, 0029, 0035, 0061 e 0063): esvazia uma fila de issues em ondas, mergeia sozinha os PRs verdes e limpos de cada lote (só a migration e o draft do vídeo da fatia de manual param no humano), um deploy por onda, auditoria do PRD no fim. Muda **a forma do loop**, não os gates. Nasceu da medição de três ondas de setembro de 2026 (1,05 bilhão de tokens para 11 issues, 94% releitura de contexto) e das decisões em [references/decisoes.md](references/decisoes.md). Tudo o que ela precisa vive em `.claude/skills/onda-enxuta/` e `.claude/agents/hr-*.md`. A `/onda` e a `/montar-ondas` originais foram aposentadas pela ADR 0061.

> **Invariantes herdados, sem exceção:** nada espera o humano antes de produção, exceto migration (ADR 0063) e o draft do vídeo da fatia de manual (ADR 0057): o gate é CI, revisores agentes, health e rollback automático. PR verde = CI verde + spec×diff + veredito limpo do revisor independente. Baixa em 3 tentativas. Fatia de manual para no draft do vídeo. Nada de doc de estado no repositório: o estado vive no GitHub, e o custo em `~/.claude/onda-enxuta/medicoes/`, fora do repositório.

## Sintaxe

```
/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `#PRD` / `--all` | `--all` | Escopo da fila. Normalmente o prompt já traz a **fila-alvo fixa** escrita pelo `/montar-ondas-enxutas`. |
| `--paralelo N` | 3 | Issues por onda. |
| `--sessao <nome>` | `onda-<letra>` | Nome da sessão (`--name` do `claude --bg`). É o prefixo das medições e, com `-onda<N>`, a chave do semáforo no rabo de cada onda (passo 6). |
| `--onda N` | 1 | Número desta onda dentro da sessão. Cresce a cada passagem. |

**Uma sessão de fundo = uma onda.** A sessão nasce pelo `scripts/lancar_sessao.sh` (ambiente limpo, zero MCP, Opus 5.5, esforço `high`), roda a onda e, assim que os PRs ficam verdes e limpos, escreve a passagem e lança a sessão da onda seguinte; depois roda o rabo, em paralelo com os implementadores novos, e só encerra quando comenta o resultado na onda (ADR 0064, decisão 6a). O caderno nunca atravessa duas ondas.

## Papéis (agentes em `.claude/agents/`)

| Agente | Esforço | Quando | Nasce com |
|---|---|---|---|
| `hr-mapeador` | high | 1 vez por PRD, antes da primeira onda; de novo só com `Estrutura mudou: sim` na passagem | número do PRD |
| `hr-implementador` / `hr-implementador-xhigh` | high / xhigh | 1 por issue, `isolation: worktree`; o label `fatia:*` escolhe (passo 3) | issue, PRD, URL do Mapa, mergeado na onda anterior |
| `hr-corretor` / `hr-corretor-max` | high / max | must-fix, CI vermelho, conflito, retomada | PR, issue, motivo, achado |
| `hr-revisor` | high | todo PR, assim que abre | PR, issue |
| `hr-revisor-seguranca` | high | PR que toca rota sem login ou migration, uma vez só | PR, issue, motivo |
| `hr-auditor-prd` | high | depois do último deploy do PRD, com a lente de segurança do diff acumulado; issue sem PRD, depois do deploy dela, só a lente, com `PR #<N>` no lugar do PRD. Detalhe de segurança que vier no relatório vai ao humano por `PushNotification`, nunca ao GitHub | PRD (ou PR), versão |

Você, orquestrador, **não lê código, diff, PRD nem spec**. Mantém a tabela da fila e o status por issue. Fato do código? Delegue. Os prompts de cada disparo estão em [references/prompts.md](references/prompts.md); use-os literalmente, preenchendo os campos.

## Fluxo

### 0. Nascimento (toda sessão)

1. Registre o início: `date -u +%Y-%m-%dT%H:%M:%SZ` (vai para o `medir_onda.py`).
2. Confira a bagagem em uma linha: esforço da sessão (`CLAUDE_EFFORT`), MCPs carregados (nenhum é o esperado). Se vier gordo, diga em uma linha e siga; não dá para desligar em pleno voo.
3. Se o prompt trouxe uma **passagem** (bloco `## Passagem`), ela é o estado: ondas fechadas, a onda anterior ainda em deploy (`Em deploy`), versão de prod, o que sobrou da fila. Não releia o que ela resume.
4. Loop do revisor (ADR 0020): `gh issue list --state open --label revisor-comentou`. Comentário de revisor humano pedindo mudança: pare e avise. Carimbo automático de comentário `<!-- automacao -->`: remova a label e siga.

### 1. Fila-alvo

Com fila fixa no prompt, use-a: confira só que cada issue está `ready-for-agent`, sem dono e sem bloqueio aberto (`gh issue view <N> --json labels,assignees` e `gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by`; bloqueio por issue da linha `Em deploy` da passagem não conta: a fatia fica na onda e espera a bloqueadora fechar, passo 3) e que o autor é de dentro do repositório (`gh api repos/{owner}/{repo}/issues/<N> --jq .author_association` em `OWNER`, `MEMBER` ou `COLLABORATOR`; o repositório é público). Issue de autor externo sai da fila, com uma linha no relatório. Sem fila fixa, monte (sub-issues do PRD, ou `gh issue list --label ready-for-agent --search "no:assignee -is:blocked"`), menores primeiro. Mostre a tabela desta onda em até 6 linhas e siga direto: o lançamento foi a ordem.

### 2. Mapa do terreno (1 vez por PRD)

Para cada PRD das issues desta onda: `gh issue view <PRD> --json comments --jq '[.comments[] | select(.authorAssociation == "OWNER" or .authorAssociation == "MEMBER" or .authorAssociation == "COLLABORATOR") | select(.body | startswith("<!-- automacao -->\n## Mapa do terreno"))] | last | .url'`. O filtro de autor é obrigatório (repositório público). Sem Mapa: dispare `hr-mapeador` e espere. Com Mapa, ele vale para o PRD inteiro: o que mudou depois dele vem na passagem (`Mergeado na onda anterior` e `Estrutura mudou`), e só `Estrutura mudou: sim` daquele PRD dispara o `hr-mapeador` de novo. Issue sem PRD não tem Mapa; o implementador explora sozinho e você diz isso no prompt dele.

### 3. Lote: implementadores em paralelo

Dispare os implementadores das fatias sem bloqueio aberto **na mesma mensagem**, um por issue, com o prompt de `references/prompts.md`; o label de tamanho da issue (passo 1) escolhe o agente: `fatia:G` no `hr-implementador-xhigh` (`xhigh`), `fatia:P`, `fatia:M` ou sem label no `hr-implementador` (`high`). O esforço vive no frontmatter do agente; o disparo não o muda por chamada. Cada um faz claim, TDD, PR (`/ship --skip-review`) e morre. Registre a hora do primeiro implementador (`date -u +%Y-%m-%dT%H:%M:%SZ` logo depois do disparo): vai para o comentário da onda (passo 7).

Fatia bloqueada por issue em deploy (passo 1) só é disparada depois que a bloqueadora fecha (o rabo da onda anterior a fecha no merge): na mesma mensagem do lote, um laço via Bash com `run_in_background: true` que termina quando `gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by --jq '[.[] | select(.state == "open")] | length'` dá `0`, com teto de 60 min. Na notificação, confira o bloqueio de novo e dispare o implementador dela: o worktree nasce da `origin/main` do momento, já com o squash da bloqueadora. Teto estourado (o rabo da onda anterior parou em migration, conflito ou rollback): a fatia sai desta onda sem contar tentativa e vai para a passagem como bloqueada.

A cada notificação de término, **confira o GitHub**, não o relatório (ADR 0029): `gh pr list --search "<N> in:title,body" --json number,url,headRefName --state open` ou `gh issue view <N> --json labels`. Estados possíveis:

- **PR aberto:** vá ao passo 4 para essa issue.
- **Sem PR, com branch e commits `wip:`** (agente morreu no teto de turnos ou falhou): dispare `hr-corretor` com motivo `retomar`. Conta como tentativa.
- **Sem PR nem branch:** conta como tentativa; redispare um implementador fresco (o mesmo agente, pelo label) com a linha "tentativa 2 de 3: o anterior não abriu PR, motivo desconhecido".

### 4. Por PR: CI, revisão, correção

Assim que o PR abre, **na mesma mensagem**:

1. Espera do CI em segundo plano, sem acordar por evento: `gh pr checks <PR> --watch --fail-fast` via Bash com `run_in_background: true`. Uma notificação no fim.
2. `uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py <PR>` (o script exige Python 3.12+; o `python3` do macOS é 3.9): imprime os arquivos de rota sem login e de migration tocados (lista em `revisao-sensivel.txt`, mais a varredura do head do PR: router com rota fora da cadeia de `get_current_user`, `route.ts` e `"use server"`); saída 0 = sensível, 1 = não sensível. Qualquer outra saída (2: erro do `gh`, do `git`, da varredura ou Python abaixo do 3.12) é erro, nunca "não sensível": rode de novo uma vez e, na segunda falha, a fatia é baixa (`ready-for-human`, comentário `<!-- automacao -->` com "classificação de segurança falhou").
3. Dispare `hr-revisor`. Se sensível, dispare também `hr-revisor-seguranca`, em paralelo, **uma vez só** por PR (ADR 0064, decisão 4).

Depois, por notificação:

- **Veredito do `hr-revisor`** (confirme com `gh pr view <PR> --json comments` que a última linha do comentário é `VEREDITO: ...`): `MUST-FIX` → `hr-corretor` motivo `revisao` com o comentário inteiro, sem esperar o veredito de segurança (com outro corretor no PR, vai quando ele terminar), e a rodada 2 só do `hr-revisor` vai **só quando não houver corretor no PR** (todo corretor terminou, o de segurança inclusive) e, com segurança no PR, com o `VEREDITO SEGURANCA:` já dado: ela confere as duas correções de uma vez e não há rodada 3. **Uma rodada de correção** (ADR 0064): rodada 2 com must-fix é baixa na hora, sem esperar a terceira tentativa: `gh issue edit <N> --remove-label in-progress --add-label ready-for-human` e comentário `<!-- automacao -->` com o que ficou (os must-fix da rodada 2 e o link do comentário); o lote segue sem ela.
- **Veredito de segurança** (última linha `VEREDITO SEGURANCA: ...`): o `hr-revisor-seguranca` não roda de novo depois da correção. `MUST-FIX` → `hr-corretor` motivo `revisao` com o comentário de segurança, uma rodada de correção a mais dentro do mesmo teto de 3 tentativas (com um corretor já no PR, este vai quando ele terminar); quem confere é a rodada 2 do `hr-revisor`, que espera este corretor terminar, com a linha `Veredito de segurança a conferir: <URL>` no prompt (cada must-fix dele vira spec da rodada), com a mesma regra da baixa.
- **CI vermelho:** antes de tudo, `python .claude/skills/onda-enxuta/scripts/ci_sem_runner.py <PR>`. Saída 0 = o GitHub cancelou o job por falta de runner (incidente do Actions, issue #953): o script já pediu o rerun, dispare outro `gh pr checks --watch` em segundo plano, **sem corretor e sem contar tentativa**. Na terceira vez seguida na mesma fatia, pare a fatia com `ready-for-human` e "GitHub Actions sem runner, ver githubstatus.com". Saída 1 = vermelho de código: `hr-corretor` motivo `ci` com o trecho de `gh run view <id> --log-failed | tail -60`. Segunda falha de CI na mesma fatia: `hr-corretor-max`. Depois da correção, novo `gh pr checks --watch` em segundo plano.
- **Notificação que não muda estado** (agente terminou mas você já conferiu, mensagem de progresso): responda em uma linha e não faça nada.

PR verde = `gh pr checks` verde + `VEREDITO: LIMPO` na última rodada do `hr-revisor`, depois de toda correção + com segurança no PR, o `VEREDITO SEGURANCA:` dado e, se `MUST-FIX`, corrigido antes dessa rodada + spec×diff declarado pelo implementador. Issue que não fecha em **3 tentativas** (implementação, correções e rodadas somadas): `gh issue edit <N> --remove-label in-progress --add-label ready-for-human` e comentário `<!-- automacao -->` com branch, gate que falhou e hipótese. A onda segue.

### 5. Lote pronto: a onda seguinte sai agora

Quando todos os PRs do lote estão verdes ou baixados, registre a hora dos **PRs verdes** (`date -u +%Y-%m-%dT%H:%M:%SZ`), imprima a tabela (issue · PR · status · fatia · migration (número) · MP4 do draft (fatia de manual)) e, sem esperar mensagem (ADR 0063), lance primeiro a onda seguinte e suba esta depois (ADR 0064, decisão 6a): o rabo leva de 5 a 8 min e roda em paralelo com os implementadores novos.

1. Fila ainda tem issue? Pegue a versão esperada: `python .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N> --dry-run` (segundos; não pega semáforo nem toca no Coolify) imprime a linha `plano:` com `v<antiga> -> v<nova>` (lote só de ferramenta: a versão segue).
2. Escreva a **passagem** (modelo em `references/prompts.md`, seção "Passagem"): é o prompt da próxima sessão, começando por `/onda-enxuta --sessao <nome> --onda <N+1>`, com a hora dos PRs verdes, a linha `Em deploy` (os PRs desta onda, as issues deles e a versão esperada), a fila que sobrou e as ondas fechadas. Sem PR verde no lote, `Em deploy: nenhum` e não há rabo. Salve em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md` e lance:

   ```bash
   bash .claude/skills/onda-enxuta/scripts/lancar_sessao.sh <nome>-onda<N+1> "<caminho da passagem>"
   ```

3. Imprima o id que ele devolve e, na mesma mensagem, siga para o fechamento (passo 6). Fila vazia: siga direto para o fechamento.

Fatia de manual (ADR 0057, decisões 4 e 8, que a ADR 0063 não emendou): o implementador para no draft de cada Vídeo de tarefa, o caminho do MP4 entra na tabela, e o PR fica fora do rabo da onda até o OK humano no draft. Mande `PushNotification` de uma linha: "Draft do vídeo da #<N> no PR #<PR>: <MP4>". Quem viu o vídeo sobe o PR com `fechar_onda.py --prs <PR>`; a fatia não conta tentativa nem vira baixa enquanto espera. Todo comentário do agente no PR leva `<!-- automacao -->` na primeira linha, senão a label `revisor-comentou` acusa a própria onda.

Não use `AskUserQuestion` nem encerre o turno esperando resposta: numa sessão de fundo ninguém a vê.

### 6. Fechamento da onda

Primeiro, a onda anterior (ADR 0064, decisão 6a). Sessão nascida de passagem com `Em deploy` diferente de `nenhum`: o rabo da onda anterior ainda pode parar ou voltar prod, e o seu mergearia por cima da `main` que ela deixou. Antes do item 3, espere no arquivo da sua passagem (`%TEMP%\onda-enxuta\<nome>-onda<N>.md`) a linha `Rabo da onda <N-1>:`, que a sessão anterior acrescenta assim que o rabo dela termina (passo 7, item 1): laço via Bash com `run_in_background: true`, teto de 25 h (o rabo anterior espera migration até 24 h). Trava de outra onda nunca se solta daqui: nunca rode `semaforo.sh soltar <chave> --forcar`, nem quando o `fechar_onda.py` mandar na linha `semaforo: trava velha`; essa saída vale como `parada`. Pela linha:
- `saída 0`, `2`, `5` ou `7`: siga para o item 1 (o que ficou de fora lá é da sessão anterior).
- `saída 6, revert no PR #<R>, issues <#x #y>`: prod voltou, mas a `main` ainda tem os squashes ruins. `gh pr checks <R> --watch` em segundo plano; verde, o revert entra primeiro e sem revisor no comando do item 3: `--prs <R> <a> <b>`. Fatia desta onda bloqueada por uma das issues da linha fica de fora, sem contar tentativa: `gh issue edit <N> --remove-label in-progress --add-label blocked`, comentário `<!-- automacao -->` no PR dela com a issue reaberta e uma linha no relatório (passo 7). CI do revert vermelho vale como `parada`.
- `parada` (saída 3 ou 4 da anterior, ou ela mesma parada), outra saída ou teto estourado: prod espera o rollback humano. Não rode o rabo: os PRs verdes desta onda ficam abertos, `PushNotification` de uma linha ("onda <N> não sobe: <a linha>") e siga para o passo 7, com a linha `Rabo da onda <N>: parada, a onda <N-1> não fechou` na passagem que você lançou.

1. Entram os PRs verdes do lote (`gh pr checks` verde e veredito `LIMPO`), todos num rabo só, na ordem da tabela; fatia baixada e fatia de manual (passo 5) ficam de fora.
2. Migration nova no lote: o script não aplica SQL, mas espera (issue #969). Ele imprime uma linha `migration: cole no Studio <arquivo>:1` por migration e só pega o semáforo quando o `/api/health` devolve o número da maior (toda migration termina gravando o próprio número em `migracoes_aplicadas`). Assim que a linha aparecer na saída do passo 3, repasse-a ao humano por `PushNotification`.
3. `python .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N>` via Bash **em segundo plano** (builds levam minutos). A chave é a da onda, não a da sessão: a onda seguinte já roda e, com a mesma chave, o rabo dela entraria na trava desta (o semáforo é reentrante pela chave) e apagaria o worktree dela no meio do deploy. Ele pega o semáforo, cria um worktree descartável em `~/wt-<nome>-onda<N>` (caminho curto, MAX_PATH), calcula a versão nova sem commit (issue #967; lote só de `docs/**`, `.claude/**` e `*.md` não muda a versão nem espera build), põe o `APP_VERSION` no backend e no frontend e mergeia PR a PR pela API, na ordem, cada um com squash no próprio número (a `main` é protegida, ADR 0061; ADR 0064, decisão 3): o PR que ficou atrás da `main` recebe a `origin/main` por merge e espera o CI dele antes do merge. Depois cancela o build de cada squash intermediário, cria a tag `vX.Y.Z` no squash do último, espera **um build**, confere health com version match, grava o registro num PR só de docs com `history.json` (todos os deploys, sem teto) e `state.json`, limpa worktrees de agente já mergeados e solta o semáforo. O rabo grava só a verdade do deploy: o snapshot e o draft do Manual dos PRDs que fecharam saem numa Action no push da `main`, depois do registro (ADR 0062). Saída de 10 linhas mais uma por PR; leia só ela.
   - Saída `2` (PR de fora): os PRs que entraram já subiram (build, health e registro) e cada PR que ficou de fora tem uma linha `de fora:`. Com a linha `conflito no merge de #N em: <arquivos>`, dispare o `hr-corretor` motivo `conflito` no #N com os arquivos da linha; ele rebaseia pela skill `resolver-conflitos`. Quando ele terminar, `gh pr checks <N> --watch` em segundo plano, para o CI rodar sobre o código combinado (vermelho segue o passo 4), e rode o script de novo só com os PRs de fora. Cada conflito conta uma tentativa da fatia; na terceira, `ready-for-human` como toda baixa (passo 4), com o diagnóstico (a linha do rabo, os arquivos e o que o corretor tentou), `PushNotification` de uma linha, e o script roda de novo sem o #N. Linha `de fora:` sem conflito (push rejeitado, CI vermelho, head que andou ou merge recusado): ela diz a causa; CI vermelho segue o passo 4, o resto roda o script de novo com aquele PR, e também conta tentativa.
   - Saída `3` ou `4` (build, ou health com o rollback automático que falhou): pare. Antes de tudo, acrescente à passagem lançada no passo 5 a linha `Rabo da onda <N>: saída <3|4>, parada, semáforo preso na chave <nome>-onda<N> até o rollback humano`: a sessão seguinte já roda e só sobe depois de lê-la (Primeiro, a onda anterior, no início deste passo). Semáforo fica preso com você; imprima a chave e a linha do script; o rollback segue o modo rollback da skill `/deploy` (única situação em que você lê aquele SKILL.md).
   - Saída `6` (rollback feito): o rabo já voltou cada app do lote à imagem anterior e ao `APP_VERSION` antigo, com health verde de novo, e o semáforo está solto; os squashes ruins seguem na `main`. Faça: (1) o PR de revert dos squashes que a linha `rollback:` imprime (`git revert --no-edit <sha> ...`, do mais novo para o mais velho, numa branch `revert/<nome>` a partir da `origin/main`, depois `gh pr create`), sem rebuild, porque a imagem no ar já é a anterior; logo depois do `gh pr create`, acrescente à passagem lançada no passo 5 a linha `Rabo da onda <N>: saída 6, revert no PR #<R>, issues <#x #y>` (as da linha `rollback:`): a sessão seguinte espera por ela e põe o revert primeiro no próprio rabo, para o próximo deploy não carregar o defeito (fila vazia, sem passagem lançada: o revert fica aberto para o próximo `fechar_onda.py` e entra no Sinal final); (2) para cada issue da linha `rollback:`, `gh issue reopen <N>`, `gh issue edit <N> --remove-label in-progress --add-label ready-for-agent` e um comentário `<!-- automacao -->` com a linha `health:` do rabo (o que o health respondeu); (3) conta uma tentativa de cada fatia (na terceira, `ready-for-human`, como toda baixa); (4) `PushNotification` de uma linha: "rollback disparado no PR #N, versão vX.Y.Z voltou". A onda segue para o passo 4.
   - Saída `7` (migration vencida): o `/api/health` não devolveu o número da migration em 24 h; nada entrou na main, o semáforo nem foi pego e os PRs seguem abertos. `PushNotification` com a linha `migration: vencida` e, depois que o humano colar, o mesmo comando do passo 3 de novo. Não conta tentativa.
4. `python .claude/skills/onda-enxuta/scripts/medir_onda.py --onda <N> --issues <...> --prs <...> --inicio <timestamp do passo 0>`: 10 linhas de conta, JSON em `~/.claude/onda-enxuta/medicoes/`.
5. Se a última fatia aberta de um PRD fechou nesta onda: dispare `hr-auditor-prd` e espere o veredito (reopen em falha é dele).

### 7. Resultado do rabo, comentário na onda e fim da sessão

Relatório de até 15 linhas: linha final do `fechar_onda.py`, tabela de issues (fechada · PR · versão), baixas, veredito do auditor se houve, as 10 linhas da medição, a hora dos PRs verdes desta onda e, se a sessão nasceu de uma passagem, o intervalo entre os PRs verdes da onda anterior (linha `Sessão ... com os PRs verdes em` da passagem) e o primeiro implementador desta (passo 3), em minutos e segundos. A meta é menos de 2 min.

1. Com passagem lançada no passo 5, ela registra o resultado assim que o rabo termina, antes de tratar a saída (nas saídas 3, 4 e 6, a linha que o passo 6 dá): acrescente ao arquivo dela (`%TEMP%\onda-enxuta\<nome>-onda<N+1>.md`) a linha `Rabo da onda <N>: saída <código>, <linha final do fechar_onda.py>`. A sessão seguinte espera por ela antes do próprio rabo (passo 6) e a leva para a própria passagem.
2. Comente o relatório na onda: em cada PRD das issues desta onda (issue sem PRD: no PR dela), com `<!-- automacao -->` na primeira linha e `## Onda <nome> <N>` na segunda.
3. Encerre só depois do comentário. Fila vazia: antes de encerrar, o **Sinal final** (fechadas e deployadas, ready-for-human, bloqueadas, deploys da sessão, veredito do PRD, tudo ocorreu bem ou parcial).

## Limites

- Só a migration (ADR 0063) e o draft do vídeo da fatia de manual (ADR 0057) a fazem esperar o humano; não mergeia PR que não está verde e `LIMPO`.
- Não modifica nada de `.claude/skills/` nem de `docs/` do repositório além do que o `fechar_onda.py` registra (`docs/spec/deploy/history.json` e `state.json`), que já era registro do `/deploy`.
- As medições de custo vivem em `~/.claude/onda-enxuta/medicoes/`, fora do repositório.
- Não usa Sonnet nem Haiku em papel nenhum (restrição do dono).

## Scripts

| Script | Faz | Saída |
|---|---|---|
| `scripts/lancar_sessao.sh <nome> <prompt.md> [--dry-run]` | Lança a sessão de fundo com ambiente limpo, zero MCP (`--strict-mcp-config --no-chrome`), plugins desligados (`--settings onda-settings.json`), `--model opus --effort high` | id da sessão (`claude logs <id>` mostra o andamento) |
| `scripts/sensivel.py <PR>` | Cruza os arquivos do PR com `revisao-sensivel.txt` | arquivos sensíveis; exit 0 se houver |
| `scripts/fechar_onda.py --prs ... --sessao ... [--dry-run]` | Integração da onda: um merge pela API por PR, em ordem, um build, registro só com `history.json` e `state.json` | 10 linhas mais uma por PR; exit 0 ok, 1 pré-condição, 2 PR de fora (conflito, CI vermelho, merge recusado), 3 build, 4 health com rollback que falhou, 6 rollback feito, 7 migration vencida |
| `scripts/medir_onda.py --onda N --issues a,b --prs c,d [--inicio ISO] [--modelo claude-opus-5-5]` | Conta da onda a partir dos JSONL da sessão e dos sub-agentes (papel pelo prefixo `[papel: ...]` do prompt) | 10 linhas; JSON em `~/.claude/onda-enxuta/medicoes/`. Sub-agente nunca retomado sai como estimado |

## Em máquina nova

Vem no clone do repositório: `.claude/skills/onda-enxuta/`, `.claude/skills/montar-ondas-enxutas/` e `.claude/agents/hr-*.md`. Confira `claude --version` (2.1.280 ou mais: `--bg`, `--strict-mcp-config`, `--effort`), `gh auth status`, `coolify` no PATH e `python` 3.
