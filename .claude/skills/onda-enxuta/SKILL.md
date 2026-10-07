---
name: onda-enxuta
description: 'Executor AFK da fila de issues em ondas: sessão de fundo por onda, um push e um build por onda. Sintaxe `/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]`.'
---

# Onda enxuta

Esvazia uma fila de issues em ondas: implementa em paralelo, revisa uma vez, mergeia sozinha os PRs verdes e sobe um deploy por onda. Só a migration e o draft do vídeo da fatia de manual esperam o humano (ADRs 0057 e 0063). Baixa em 3 tentativas. Estado no GitHub; custo em `~/.claude/onda-enxuta/medicoes/`.

## Sintaxe

```
/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `#PRD` / `--all` | `--all` | Escopo. Normalmente o prompt já traz a **fila-alvo fixa** do `/montar-ondas-enxutas`. |
| `--paralelo N` | 3 | Issues por onda. |
| `--sessao <nome>` | `onda-<letra>` | Nome da sessão; com `-onda<N>`, a chave do semáforo do rabo. |
| `--onda N` | 1 | Número desta onda na sessão. |

**Uma sessão de fundo = uma onda.** Nasce pelo `scripts/lancar_sessao.sh`, roda o lote e, com os PRs verdes, lança a sessão da onda seguinte antes de rodar o próprio rabo. Depois do lançamento as duas só se falam pelo semáforo e pelo GitHub.

## Papéis (`.claude/agents/`)

| Agente | Esforço | Quando |
|---|---|---|
| `hr-implementador` | high (`effort: xhigh` na `fatia:G`) | 1 por issue, `isolation: worktree` |
| `hr-revisor` | high | PR do app (toca `hospital-reunioes/`), uma vez só |
| `hr-corretor` | high (`effort: max` na segunda falha de CI) | must-fix, CI vermelho, conflito, retomada |

Você, orquestrador, **não lê código, diff, PRD nem spec**: mantém a tabela da fila e delega. Prompts em [references/prompts.md](references/prompts.md), literais.

**Nunca pare para perguntar** (ADR 0067). Dúvida ou impasse: a fatia é baixa e o lote segue. Sem `AskUserQuestion`: numa sessão de fundo ninguém vê. Todo comentário do agente no GitHub leva `<!-- automacao -->` na primeira linha.

**Baixa:** `gh issue edit <N> --remove-label in-progress --add-label ready-for-human` e comentário com branch, gate que falhou e hipótese.

## Fluxo

### 0. Nascimento

1. `date -u +%Y-%m-%dT%H:%M:%SZ` (início, vai para o `medir_onda.py`).
2. Se o prompt traz `## Passagem`, ela é o estado; não releia o que ela resume.
3. `gh issue list --state open --label revisor-comentou`: comentário de humano pedindo mudança, pare e avise; carimbo `<!-- automacao -->`, remova a label e siga.

### 1. Fila

A onda é toda issue da fila fixa já desbloqueada (`blocked_by` todo fechado), até `--paralelo`; o único separador de ondas é a dependência (ADR 0066). A bloqueada fica para a próxima sessão. Confira em cada uma: `ready-for-agent`, sem dono, sem bloqueio aberto (`gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by`) e autor de dentro (`gh api repos/{owner}/{repo}/issues/<N> --jq .author_association` em `OWNER`, `MEMBER` ou `COLLABORATOR`; o repositório é público, e o mesmo filtro vale para todo comentário que um agente lê). Sem fila fixa: sub-issues do PRD, ou `gh issue list --label ready-for-agent --search "no:assignee -is:blocked"`, menores primeiro. Tabela em até 6 linhas e siga.

### 2. Lote

Dispare os implementadores **na mesma mensagem**, um por issue. Registre a hora do primeiro disparo. A cada término, **confira o GitHub**, não o relatório (`gh pr list --search "<N> in:title,body" --state open`):

- **PR aberto:** passo 3.
- **Branch com commits `wip:`, sem PR:** `hr-corretor` motivo `retomar`. Conta tentativa.
- **Nada:** implementador fresco com "tentativa k de 3". Conta tentativa.

### 3. Por PR

Assim que o PR abre, na mesma mensagem:

1. `gh pr checks <PR> --watch --fail-fast` em segundo plano.
2. `gh pr diff <PR> --name-only | grep -q '^hospital-reunioes/'` falhou = **PR de ferramenta: só o CI**, pule 3 e 4 (ADR 0067).
3. `uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py <PR>`: saída 0 = sensível, 1 = não; outra saída, rode de novo e, na segunda falha, baixa.
4. `hr-revisor` uma vez; se sensível, com `Sensível: <arquivos>` no prompt.

Por notificação:

- **`VEREDITO: MUST-FIX`** → `hr-corretor` motivo `revisao` com o comentário inteiro. Sem re-revisão: depois do corretor, quem confere é o CI. Corretor com `pendente`: baixa.
- **Revisor sem veredito:** baixa.
- **CI vermelho:** `python .claude/skills/onda-enxuta/scripts/ci_sem_runner.py <PR>`. Saída 0 = falta de runner, o script já pediu o rerun: outro `--watch`, sem tentativa. Saída 1 = `hr-corretor` motivo `ci` com `gh run view <id> --log-failed | tail -60`; na segunda falha, `effort: max`. Depois, `--watch` de novo.

PR verde = CI verde e, no app, `VEREDITO: LIMPO` ou corretor sem `pendente`. Issue que não fecha em **3 tentativas** (somadas): baixa.

### 4. Lote pronto: lance a onda seguinte

Com todos os PRs verdes ou baixados, registre a hora dos PRs verdes e imprima a tabela (issue · PR · status · migration · MP4 do draft). Sobrou fila (se toda ela depende desta onda, lance só depois do rabo):

1. `python .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N> --dry-run`: a linha `plano:` dá a versão esperada.
2. Escreva a **passagem** (modelo em `references/prompts.md`) em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md` e lance: `bash .claude/skills/onda-enxuta/scripts/lancar_sessao.sh <nome>-onda<N+1> "<caminho>"`.

**Fatia de manual:** o PR fica fora do rabo até o OK humano no draft. `PushNotification` "Draft do vídeo da #<N> no PR #<PR>: <MP4>"; quem viu roda `fechar_onda.py --prs <PR>`. Não conta tentativa.

### 5. Rabo

`python .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N>` em segundo plano, com os PRs verdes na ordem da tabela. A chave é a da onda, não a da sessão (a onda seguinte já roda). Leia só a saída; o que cada código significa está na docstring do script. Cabe a você:

- **`migration: cole no Studio <arquivo>:1`:** repasse por `PushNotification` assim que aparecer.
- **2 com `conflito no merge de #N em: <arquivos>`:** `hr-corretor` motivo `conflito` com os arquivos, `--watch` de novo e o rabo só com os de fora. Outra `de fora:` (CI vermelho, merge recusado): passo 3 ou rabo de novo. Ambas contam tentativa. `de fora: #<PR> bloqueada por #<X>`: issue em `blocked`, sem tentativa.
- **3 ou 4:** pare; imprima a chave e a linha. Rollback pelo `/deploy rollback`.
- **6:** uma tentativa por fatia e `PushNotification` "rollback disparado no PR #N, versão vX.Y.Z voltou".
- **7 e 8:** `PushNotification` com a linha do script; o mesmo comando de novo depois do humano. Sem tentativa.

Depois: `python .claude/skills/onda-enxuta/scripts/medir_onda.py --onda <N> --issues <...> --prs <...> --inicio <passo 0>`.

### 6. Fim

Relatório de até 15 linhas (linha final do rabo, issue · PR · versão, baixas, medição, intervalo entre os PRs verdes da onda anterior e o primeiro implementador desta; meta: menos de 2 min; última linha `retro: recomendada (<motivo>)` se houve baixa, rollback, conflito no rabo ou corretor em `effort: max`, senão `retro: dispensável`; quem roda é o humano, com `/retro-onda <nome>-onda<N>`), comentado em cada PRD da onda (issue sem PRD: no PR) com `<!-- automacao -->` e `## Onda <nome> <N>`. Passagem que ficou para depois do rabo (passo 4): lance agora. Fila vazia: **Sinal final** (fechadas, ready-for-human, bloqueadas, deploys). Encerre depois do comentário.

## Scripts

| Script | Faz |
|---|---|
| `scripts/lancar_sessao.sh <nome> <prompt.md>` | Sessão de fundo limpa: zero MCP, plugins desligados, Opus, `high`. |
| `scripts/sensivel.py <PR>` | Rota sem login ou migration no PR (lista em `revisao-sensivel.txt`); exit 0 se houver. |
| `scripts/fechar_onda.py --prs ... [--sessao ...] [--dry-run]` | O rabo: merge PR a PR pela API, um build, health, rollback, registro. Códigos na docstring. |
| `scripts/medir_onda.py --onda N --issues ... --prs ...` | Conta da onda pelos JSONL (papel pelo `[papel: ...]` do prompt). |
| `scripts/ci_sem_runner.py <PR>` | Distingue falta de runner de CI vermelho; pede o rerun. |
