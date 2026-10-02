---
name: onda-enxuta
description: Executor AFK da fila de issues em ondas, versão enxuta da /onda: uma sessão de fundo por onda, mapa do terreno por PRD, implementador que morre no PR, corretor fresco, revisão por lista de arquivos, um push e um build por onda, medição automática. Sintaxe `/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]`.
---

# Onda enxuta

Faz o mesmo que a `/onda` (ADRs 0022, 0029 e 0035): esvazia uma fila de issues em ondas, para no seu OK de merge por lote, um deploy por onda, auditoria do PRD no fim. Muda **a forma do loop**, não os gates. Nasceu da medição de três ondas de setembro de 2026 (1,05 bilhão de tokens para 11 issues, 94% releitura de contexto) e das decisões em [references/decisoes.md](references/decisoes.md). Tudo o que ela precisa vive em `.claude/skills/onda-enxuta/` e `.claude/agents/hr-*.md`, arquivos próprios: a `/onda`, a `/montar-ondas` e o `/deploy` não mudam.

> **Invariantes herdados, sem exceção:** subir para produção é decisão humana por onda, citando os PR#. PR verde = CI verde + spec×diff + veredito limpo do revisor independente. Baixa em 3 tentativas. Fatia de manual para no draft do vídeo. Nada de doc de estado no repositório: o estado vive no GitHub, e o custo em `~/.claude/onda-enxuta/medicoes/`, fora do repositório.

## Sintaxe

```
/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `#PRD` / `--all` | `--all` | Escopo da fila, como na `/onda`. Normalmente o prompt já traz a **fila-alvo fixa** escrita pelo `/montar-ondas-enxutas`. |
| `--paralelo N` | 3 | Issues por onda. |
| `--sessao <nome>` | `onda-<letra>` | Nome da sessão (`--name` do `claude --bg`). É a chave do semáforo e o prefixo das medições. |
| `--onda N` | 1 | Número desta onda dentro da sessão. Cresce a cada passagem. |

**Uma sessão de fundo = uma onda.** A sessão nasce pelo `scripts/lancar_sessao.sh` (ambiente limpo, zero MCP, Opus 5.5, esforço `high`), roda a onda até o checkpoint, fecha a onda depois do seu "vai", escreve a passagem e lança a sessão da onda seguinte. O caderno nunca atravessa duas ondas.

## Papéis (agentes em `.claude/agents/`)

| Agente | Esforço | Quando | Nasce com |
|---|---|---|---|
| `hr-mapeador` | high | 1 vez por PRD, antes da primeira onda | número do PRD |
| `hr-implementador` | xhigh | 1 por issue, `isolation: worktree` | issue, PRD, URL do Mapa |
| `hr-corretor` / `hr-corretor-max` | high / max | must-fix, CI vermelho, conflito, retomada | PR, issue, motivo, achado |
| `hr-revisor` | high | todo PR, assim que abre | PR, issue |
| `hr-revisor-seguranca` | max | PR com caminho sensível, ou pedido do revisor | PR, issue, motivo |
| `hr-auditor-prd` | high | depois do último deploy do PRD | PRD, versão |

Você, orquestrador, **não lê código, diff, PRD nem spec**. Mantém a tabela da fila e o status por issue. Fato do código? Delegue. Os prompts de cada disparo estão em [references/prompts.md](references/prompts.md); use-os literalmente, preenchendo os campos.

## Fluxo

### 0. Nascimento (toda sessão)

1. Registre o início: `date -u +%Y-%m-%dT%H:%M:%SZ` (vai para o `medir_onda.py`).
2. Confira a bagagem em uma linha: esforço da sessão (`CLAUDE_EFFORT`), MCPs carregados (nenhum é o esperado). Se vier gordo, diga em uma linha e siga; não dá para desligar em pleno voo.
3. Se o prompt trouxe uma **passagem** (bloco `## Passagem`), ela é o estado: ondas fechadas, versão de prod, o que sobrou da fila. Não releia o que ela resume.
4. Loop do revisor (ADR 0020): `gh issue list --state open --label revisor-comentou`. Comentário de revisor humano pedindo mudança: pare e avise. Carimbo automático de comentário `<!-- automacao -->`: remova a label e siga.

### 1. Fila-alvo

Com fila fixa no prompt, use-a: confira só que cada issue está `ready-for-agent`, sem dono e sem bloqueio aberto (`gh issue view <N> --json labels,assignees` e `gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by`). Sem fila fixa, monte como a `/onda` (sub-issues do PRD, ou `gh issue list --label ready-for-agent --search "no:assignee -is:blocked"`), menores primeiro. Mostre a tabela desta onda em até 6 linhas e siga sem pedir confirmação: o lançamento foi o "vai".

### 2. Mapa do terreno (1 vez por PRD)

Para cada PRD das issues desta onda: `gh issue view <PRD> --json comments --jq '[.comments[] | select(.body | startswith("<!-- automacao -->\n## Mapa do terreno"))] | last | .url'`. Sem Mapa, ou com Mapa anterior ao último PR mergeado do PRD: dispare `hr-mapeador` e espere. Issue sem PRD não tem Mapa; o implementador explora sozinho e você diz isso no prompt dele.

### 3. Lote: implementadores em paralelo

Dispare os `N` `hr-implementador` **na mesma mensagem**, um por issue, com o prompt de `references/prompts.md`. Cada um faz claim, TDD, PR (`/ship --no-merge --skip-review --no-bump`) e morre.

A cada notificação de término, **confira o GitHub**, não o relatório (ADR 0029): `gh pr list --search "<N> in:title,body" --json number,url,headRefName --state open` ou `gh issue view <N> --json labels`. Estados possíveis:

- **PR aberto:** vá ao passo 4 para essa issue.
- **Sem PR, com branch e commits `wip:`** (agente morreu no teto de turnos ou falhou): dispare `hr-corretor` com motivo `retomar`. Conta como tentativa.
- **Sem PR nem branch:** conta como tentativa; redispare um `hr-implementador` fresco com a linha "tentativa 2 de 3: o anterior não abriu PR, motivo desconhecido".

### 4. Por PR: CI, revisão, correção

Assim que o PR abre, **na mesma mensagem**:

1. Espera do CI em segundo plano, sem acordar por evento: `gh pr checks <PR> --watch --fail-fast` via Bash com `run_in_background: true`. Uma notificação no fim.
2. `python .claude/skills/onda-enxuta/scripts/sensivel.py <PR>`: imprime os arquivos sensíveis tocados (lista em `revisao-sensivel.txt`); saída 0 = sensível.
3. Dispare `hr-revisor`. Se sensível, dispare também `hr-revisor-seguranca`, em paralelo.

Depois, por notificação:

- **Veredito** (confirme com `gh pr view <PR> --json comments` que a última linha do comentário é `VEREDITO: ...`): `MUST-FIX` → `hr-corretor` motivo `revisao` com o comentário inteiro; quando ele terminar, nova rodada de `hr-revisor` (e de segurança, se havia). **Máximo 2 rodadas.** `PEDE_REVISOR_SEGURANCA` no veredito → dispare `hr-revisor-seguranca` sem julgar.
- **CI vermelho:** `hr-corretor` motivo `ci` com o trecho de `gh run view <id> --log-failed | tail -60`. Segunda falha de CI na mesma fatia: `hr-corretor-max`. Depois da correção, novo `gh pr checks --watch` em segundo plano.
- **Notificação que não muda estado** (agente terminou mas você já conferiu, mensagem de progresso): responda em uma linha e não faça nada.

PR verde = `gh pr checks` verde + veredito(s) `LIMPO` + spec×diff declarado pelo implementador. Issue que não fecha em **3 tentativas** (implementação, correções e rodadas somadas): `gh issue edit <N> --remove-label in-progress --add-label ready-for-human` e comentário `<!-- automacao -->` com branch, gate que falhou e hipótese. A onda segue.

### 5. Checkpoint em duas metades

Quando todos os PRs do lote estão verdes ou baixados:

1. Imprima a tabela: issue · PR · status · fatia · should-fix pendentes (n) · migration (número) · MP4 do draft (fatia de manual).
2. Dispare a notificação push (ferramenta `PushNotification`, uma linha: "Onda <N> de <sessão> pronta: PRs #a #b. `claude attach <id>` e `vai`").
3. Imprima as instruções e **encerre o turno**: `claude attach <id da sessão>` e depois `vai #a #b` (todos), `vai #a` (subconjunto) ou `abortar`. Condição opcional na mesma linha: `vai #a #b, corrigir o should-fix da #b e mergear se voltar limpo`.

Não fique em `AskUserQuestion`: numa sessão de fundo ninguém a vê. A pergunta acontece quando você retoma a sessão, e aí a resposta chega como mensagem normal.

### 6. Fechamento da onda (depois do "vai")

1. Leia o "vai": PRs aprovados e condição. Sem condição, should-fix fica como comentário no PR e a fatia entra como está. Com condição de correção: `hr-corretor` (motivo `revisao`, com os itens pré-autorizados), nova revisão, `gh pr checks --watch`, e só então o fechamento, **sem novo checkpoint**. A condição vale só para este lote.
2. Migration nova no lote: lembre o humano no próprio "vai" de aplicar no Studio antes do fechamento (o script não aplica SQL); se ele já disse que aplicou, siga.
3. `python .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>` via Bash **em segundo plano** (builds levam minutos). Ele pega o semáforo, cria um worktree descartável em `~/wt-<nome>` (caminho curto, MAX_PATH), faz merge local `--no-ff` em ordem, bump (lote só de `docs/**`, `.claude/**` e `*.md` não bumpa nem espera build), changelog, `history.json`, `state.json`, snapshot (best-effort, #844), tira do `draft` as páginas do Manual dos PRDs que fecharam e roda o `publicar.sh` (ADR 0057), `APP_VERSION`, **um push**, espera **um build**, confere health com version match, limpa worktrees de agente já mergeados e solta o semáforo. Saída de 10 linhas; leia só ela.
   - Saída `2` (conflito ou main andou): `hr-corretor` motivo `conflito` no PR citado; rode o script de novo.
   - Saída `3` ou `4` (build ou health): pare. Semáforo fica com você; imprima a chave e a linha do script; o rollback segue o modo rollback da skill `/deploy` (única situação em que você lê aquele SKILL.md).
4. `python .claude/skills/onda-enxuta/scripts/medir_onda.py --onda <N> --issues <...> --prs <...> --inicio <timestamp do passo 0>`: 10 linhas de conta, JSON em `~/.claude/onda-enxuta/medicoes/`.
5. Se a última fatia aberta de um PRD fechou nesta onda: dispare `hr-auditor-prd` e espere o veredito (reopen em falha é dele).

### 7. Relatório da onda, passagem e próxima sessão

Relatório de até 15 linhas: linha final do `fechar_onda.py`, tabela de issues (fechada · PR · versão), baixas, veredito do auditor se houve, as 10 linhas da medição.

Fila ainda tem issue desbloqueada? Escreva a **passagem** (modelo em `references/prompts.md`, seção "Passagem"): é o prompt da próxima sessão, começando por `/onda-enxuta --sessao <nome> --onda <N+1>`, com a fila que sobrou, as ondas fechadas, a versão de prod e a chave do semáforo. Salve em `%TEMP%\onda-enxuta\<nome>-onda<N+1>.md` e lance:

```bash
bash .claude/skills/onda-enxuta/scripts/lancar_sessao.sh <nome>-onda<N+1> "<caminho da passagem>"
```

Imprima o id que ele devolve e encerre. Fila vazia: **Sinal final** como na `/onda` (fechadas e deployadas, ready-for-human, bloqueadas, deploys da sessão, veredito do PRD, tudo ocorreu bem ou parcial).

## Limites

- Não revoga o gate de merge, não roda sem checkpoint, não mergeia por conta própria depois de um "vai" que não citou o PR.
- Não modifica nada de `.claude/skills/` nem de `docs/` do repositório além do que o `fechar_onda.py` registra (`CHANGELOG.md`, `docs/spec/deploy/*.json`, snapshot), que já era registro do `/deploy`.
- Não substitui a `/onda`: as duas coexistem. Esta é a variante medida; a comparação vive em `~/.claude/onda-enxuta/medicoes/`.
- Não usa Sonnet nem Haiku em papel nenhum (restrição do dono).

## Scripts

| Script | Faz | Saída |
|---|---|---|
| `scripts/lancar_sessao.sh <nome> <prompt.md> [--dry-run]` | Lança a sessão de fundo com ambiente limpo, zero MCP (`--strict-mcp-config --no-chrome`), plugins desligados (`--settings onda-settings.json`), `--model opus --effort high` | id da sessão (`claude attach <id>`) |
| `scripts/sensivel.py <PR>` | Cruza os arquivos do PR com `revisao-sensivel.txt` | arquivos sensíveis; exit 0 se houver |
| `scripts/fechar_onda.py --prs ... --sessao ... [--dry-run] [--sem-snapshot]` | Integração da onda: um push, um build | 10 linhas; exit 0 ok, 1 pré-condição, 2 conflito, 3 build, 4 health |
| `scripts/medir_onda.py --onda N --issues a,b --prs c,d [--inicio ISO] [--modelo claude-opus-5-5]` | Conta da onda a partir dos JSONL da sessão e dos sub-agentes (papel pelo prefixo `[papel: ...]` do prompt) | 10 linhas; JSON em `~/.claude/onda-enxuta/medicoes/`. Sub-agente nunca retomado sai como estimado |

## Em máquina nova

Vem no clone do repositório: `.claude/skills/onda-enxuta/`, `.claude/skills/montar-ondas-enxutas/` e `.claude/agents/hr-*.md`. Confira `claude --version` (2.1.280 ou mais: `--bg`, `--strict-mcp-config`, `--effort`), `gh auth status`, `coolify` no PATH e `python` 3.
