---
name: onda-enxuta
description: 'Executor AFK da fila de issues em ondas: sessão de fundo por onda, merge PR a PR pela API e um deploy por onda (quando o Projeto tem deploy). Grava o estado da Onda para o PedroOS e avisa no celular, com o comando para entrar na sessão, quando quebra ou quando algo espera o humano. Sintaxe `/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]`.'
---

# Onda enxuta

Esvazia uma fila de issues em ondas: implementa em paralelo, revisa uma vez, mergeia sozinha os PRs verdes e sobe um deploy por onda. Só a migration espera o humano no caminho feliz (decisão do fluxo, regra 9). Baixa em 3 tentativas. Estado no GitHub e em `~/.pedroos/ondas/` (para o PedroOS); custo em `~/.claude/onda-enxuta/medicoes/`.

## O Projeto

Esta skill é a mesma em todo Projeto (fonte única no PedroOS, `skills/fluxo/`). O que muda de um para outro está em `.claude/fluxo.json`:

```bash
python3 .claude/skills/onda-enxuta/scripts/fluxo.py            # a configuração inteira
python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas onda-enxuta
```

O que o `notas` imprimir vale por cima desta skill. A "decisão do fluxo" citada aqui é o documento em `decisoes.fluxo` do `fluxo.json`.

## Sintaxe

```
/onda-enxuta [#PRD | --all] [--paralelo N] [--sessao <nome>] [--onda N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `#PRD` / `--all` | `--all` | Escopo. Normalmente o prompt já traz a **fila-alvo fixa** do `/montar-ondas-enxutas`. |
| `--paralelo N` | 3 | Issues por onda. |
| `--sessao <nome>` | `onda-<letra>` | Nome da sessão; com `-onda<N>`, a chave do semáforo da subida e o nome do `claude attach`. |
| `--onda N` | 1 | Número desta onda na sessão. |

**Uma sessão de fundo = uma onda.** Nasce pelo `scripts/lancar_sessao.sh`, roda o lote e, com os PRs verdes, lança a sessão da onda seguinte antes de rodar a própria subida. Depois do lançamento as duas só se falam pelo semáforo e pelo GitHub.

## Papéis (`.claude/agents/`)

| Agente | Esforço | Quando |
|---|---|---|
| `onda-implementador` | xhigh | 1 por issue, `isolation: worktree` |
| `onda-revisor` | xhigh | PR do app (`fluxo.py classe` diz `app`), uma vez só |
| `onda-corretor` | xhigh (`effort: max` na segunda falha de CI) | must-fix, CI vermelho, conflito, retomada |

Você, orquestrador, **não lê código, diff, PRD nem spec**: mantém a tabela da fila e delega. Prompts em [references/prompts.md](references/prompts.md), literais.

**Nunca pare para perguntar** (decisão do fluxo). Dúvida ou impasse: a fatia é baixa e o lote segue. Sem `AskUserQuestion`: numa sessão de fundo ninguém vê. Todo comentário do agente no GitHub leva `<!-- automacao -->` na primeira linha.

**Baixa:** `gh issue edit <N> --remove-label in-progress --add-label ready-for-human`, comentário com branch, gate que falhou e hipótese, e o evento `pronto-para-voce` (abaixo) com "#<N> ficou com você: <gate>" e `--espera-issue <N>` (mais `--espera-pr <PR>`, se há PR).

## Estado da Onda e aviso no celular

A Onda grava o que faz num arquivo que o PedroOS lê (formato em `docs/estado-da-onda.md` do PedroOS). Todo comando roda da raiz do repositório; `E` abaixo é a função `E() { python3 .claude/skills/onda-enxuta/scripts/estado_onda.py "$@"; }` (no zsh, uma variável com o comando não separa as palavras e falha).

- **Nascimento:** `E iniciar --sessao <nome> --onda <N> [--prd <PRD>] --issues <fila desta onda> --descricao-valor "<frase>"`. A frase é a Descrição de valor da Onda: o que ela entrega, numa frase só, para quem não é dev. Escreva a partir do "Por que vale:" de cada Fatia da onda (ou do "O que muda:", na Fatia sem ele), que você tira do corpo sem ler o resto (`gh issue view <I> --json body --jq .body | grep -E '^\*\*(Por que vale|O que muda):\*\*'`), e passe pelo `humanizer` antes de gravar. Sem nenhuma das duas linhas nas Fatias, omita `--descricao-valor`.
- **Cada issue:** `E issue --sessao <nome> --onda <N> --numero <I> [--pr <PR>] --status <fila|implementando|revisao|correcao|verde|baixa|mergeado>` quando o status muda.
- **Eventos:** `E evento --sessao <nome> --onda <N> --tipo <tipo> --texto "<uma frase>" [--pr <PR>]`. Tipos: `checkpoint` (lote verde, passo 4), `pr-pronto` (PR verde), `erro` (subida 3, 4 ou 6; sessão que não consegue seguir), `pronto-para-voce` (baixa, migration para aplicar, saídas 7 e 8, Sinal final com issue `ready-for-human`). O `revert`, o `erro` das saídas 9 e 10 e o `instavel` (Teste instável: o teste da main falhou e passou ao rodar de novo; sem `push:`, a onda segue) quem grava é a própria subida.
- **O que espera você:** no `pronto-para-voce` que espera uma issue ou um PR, junte `--espera-issue <N> [...]` e `--espera-pr <PR> [...]` (`--espera-repo dono/repo` quando é de outro repo). Quando tudo isso fecha no GitHub, o PedroOS tira o "espera você" sozinho. Pendência sem issue nem PR (migration, saídas 7 e 8, mensagem para alguém) vai sem as opções e esvazia a lista: essa só sai com `resolvido`.
- **Fim:** `E fim --sessao <nome> --onda <N> --retro "<a linha retro:>"`.
- **Resolvido:** `E resolvido --sessao <nome> --onda <N> --texto "<o que acabou>"` quando o que esperava o humano acabou (migration aplicada, saída 7 ou 8 que passou, pedido do passo 4 atendido). A onda sai do "espera você"; issue ainda em `baixa` mantém o selo. Sem nada pendente, não muda nada. A baixa que o humano resolve depois, em outra sessão, sai sozinha: a subida que mergeia o PR dela roda `estado_onda.py mergeadas`.

**Aviso no celular.** Quando o `evento` imprime uma linha `push: <mensagem>`, carregue o `PushNotification` (ToolSearch `select:PushNotification`) e mande a mensagem **literal**: ela já traz o Projeto, a onda e o comando para entrar na sessão (`claude attach <sessao>-onda<N>`). Só `erro`, `pronto-para-voce` e `revert` geram `push:`, e evento repetido não gera de novo. A linha `push:` que aparece na saída da subida é a mesma coisa: mande do mesmo jeito. Nunca escreva outra mensagem de push à mão: se o script falhar, mande "<Projeto>, <sessao>-onda<N>: <a frase>. Entrar: claude attach <sessao>-onda<N>". O PedroOS fala no Mac; o celular é só por aqui.

## Fluxo

### 0. Nascimento

1. `date -u +%Y-%m-%dT%H:%M:%SZ` (início, vai para o `medir_onda.py`).
2. Se o prompt traz `## Passagem`, ela é o estado; não releia o que ela resume.
3. `python3 .claude/skills/onda-enxuta/scripts/fluxo.py` e `fluxo.py notas onda-enxuta`: guarde `app`, `designado_tira_da_fila` e as notas.
4. `gh issue list --state open --label revisor-comentou`: comentário de humano pedindo mudança, pare e avise (evento `pronto-para-voce`); carimbo `<!-- automacao -->`, remova a label e siga.

### 1. Fila

A onda é toda issue da fila fixa já desbloqueada (`blocked_by` todo fechado), até `--paralelo`; o único separador de ondas é a dependência (decisão do fluxo). A bloqueada fica para a próxima sessão. Confira em cada uma: `ready-for-agent`, sem bloqueio aberto (`gh api repos/{owner}/{repo}/issues/<N>/dependencies/blocked_by`) e autor de dentro (`gh api repos/{owner}/{repo}/issues/<N> --jq .author_association` em `OWNER`, `MEMBER` ou `COLLABORATOR`; o mesmo filtro vale para todo comentário que um agente lê). Com `designado_tira_da_fila: true`, o assignee é o dono do card e a issue também precisa estar designada a quem roda (card de outro dono fica na fila dele). Sem fila fixa: sub-issues do PRD, ou `gh issue list --label ready-for-agent --search "-is:blocked"` (com `assignee:@me` quando `designado_tira_da_fila`), menores primeiro. Tabela em até 6 linhas, `E iniciar` com a fila e siga.

### 2. Lote

Dispare os implementadores **na mesma mensagem**, um por issue (`E issue ... --status implementando`). Registre a hora do primeiro disparo. A cada término, **confira o GitHub**, não o relatório (`gh pr list --search "<N> in:title,body" --state open`):

- **PR aberto:** `git worktree remove --force <worktreePath>` (o da notificação) e passo 3. O worktree preso na branch do PR barra o `gh pr checkout` do corretor e escapa da limpeza da subida. Vale também para o corretor que terminou com push.
- **Branch com commits `wip:`, sem PR:** `onda-corretor` motivo `retomar`. Conta tentativa.
- **Nada:** implementador fresco com "tentativa k de 3". Conta tentativa.

### 3. Por PR

Assim que o PR abre, na mesma mensagem:

1. `gh pr checks <PR> --watch --fail-fast` em segundo plano.
2. `python3 .claude/skills/onda-enxuta/scripts/fluxo.py classe --pr <PR>` diz `ferramenta` = **PR de ferramenta: só o CI**, pule 3 e 4 (decisão do fluxo).
3. `uv run --no-project --python ">=3.12" python .claude/skills/onda-enxuta/scripts/sensivel.py <PR>`: saída 0 = sensível, 1 = não; outra saída, rode de novo e, na segunda falha, baixa.
4. `onda-revisor` uma vez (`E issue ... --pr <PR> --status revisao`); se sensível, com `Sensível: <arquivos>` no prompt.

Por notificação:

- **`VEREDITO: MUST-FIX`** → `onda-corretor` motivo `revisao` com o comentário inteiro (`--status correcao`). Sem re-revisão: depois do corretor, quem confere é o CI. Corretor com `pendente`: baixa.
- **Revisor sem veredito:** baixa.
- **CI vermelho:** `python3 .claude/skills/onda-enxuta/scripts/ci_sem_runner.py <PR>`. Saída 0 = falta de runner, o script já pediu o rerun: outro `--watch`, sem tentativa. Saída 1 = `onda-corretor` motivo `ci` com `gh run view <id> --log-failed | tail -60`; na segunda falha, `effort: max`. Depois, `--watch` de novo.

PR verde = CI verde e, no app, `VEREDITO: LIMPO` ou corretor sem `pendente` (`--status verde`, evento `pr-pronto`). Issue que não fecha em **3 tentativas** (somadas): baixa.

### 4. Lote pronto: lance a onda seguinte

Com todos os PRs verdes ou baixados, registre a hora dos PRs verdes, grave o evento `checkpoint` ("lote verde: <n> PRs, <m> baixas") e imprima a tabela (issue · PR · status · migration). Sobrou fila (se toda ela depende desta onda, lance só depois da subida):

1. `python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N> --dry-run`: a linha `plano:` dá a versão esperada.
2. Escreva a **passagem** (modelo em `references/prompts.md`) em `$TMPDIR/onda-enxuta/<nome>-onda<N+1>.md` e lance: `bash .claude/skills/onda-enxuta/scripts/lancar_sessao.sh <nome>-onda<N+1> "<caminho>"`.

### 5. Subida

**Antes, a conferência do lote** (com dois ou mais PRs verdes): `python3 .claude/skills/onda-enxuta/scripts/conferir_lote.py --prs <a> <b>`, na ordem da tabela. Ela diz em segundos, sem agente, se os PRs cabem juntos na main: o conflito da subida vem de um PR irmão da mesma onda que entrou antes. Saída 0: suba. Saída 1: pegue só a primeira linha `conflito: #B bate em #A em: <arquivos>. Base do corretor: <base>` e dispare o `onda-corretor` motivo `conflito` com os arquivos e a base (`--status correcao`); quando ele terminar, rode a conferência de novo, até a saída 0. Depois, `--watch` em cada PR corrigido e a subida com todos, na mesma ordem. O PR rebaseado sobre a branch do irmão carrega os commits dele e entra logo depois dele, na mesma subida: depois do squash do irmão, a subida o tira de cima dele com `rebase --onto`, faz o push com `--force-with-lease` e espera o CI do head novo, sem corretor. Linha `Sem base única`: o PR vai por último na subida e segue o caminho do conflito abaixo. Conflito com PR irmão não conta tentativa, aqui nem na subida; corretor com `pendente`, ou o mesmo PR na terceira correção de conflito: baixa.

`python3 .claude/skills/onda-enxuta/scripts/fechar_onda.py --prs <a> <b> --sessao <nome>-onda<N>` em segundo plano, com os PRs verdes na ordem da tabela. A chave é a da onda, não a da sessão (a onda seguinte já roda). Leia só a saída; o que cada código significa está na docstring do script. Sem serviço no `docs/spec/deploy/project.json` (`/deploy status`), a subida termina no merge: sem versão, build, health nem espera de migration, e as saídas 3, 4, 6 e 7 não acontecem. Com o `teste_da_main` no `fluxo.json`, o lote sem deploy ainda passa pelo teste da main depois do merge (saídas 9 e 10). Cabe a você:

- **`migration: <como aplicar> <arquivo> (...); copie com: pbcopy < <caminho>`:** evento `pronto-para-voce` com "migration <número> para aplicar: <arquivo>" assim que aparecer.
- **2 com `conflito no merge de #N em: <arquivos>`:** `onda-corretor` motivo `conflito` com os arquivos e a base `origin/main`, `--watch` de novo e a subida só com os de fora. Dois ou mais de fora com arquivo em comum: um corretor de cada vez, na ordem da tabela, e a subida de um antes do rebase do próximo (o rebase em paralelo conflita de novo). Sem tentativa; o limite é o da conferência. Outra `de fora:` (CI vermelho, merge recusado): passo 3 ou subida de novo, e conta tentativa. `de fora: #<PR> bloqueada por #<X>`: issue em `blocked`, sem tentativa. `de fora: #<PR> sem volta (<motivo>)` (só na Noite e na Sesta: migration que apaga dado, segredo ou caminho `protegidos` do `fluxo.json`): a subida já comentou o motivo no PR, pôs a issue na Etapa Humana e gravou a `baixa` e o `pronto-para-voce`; mande o `push:` e siga, sem tentativa e sem corretor. Fora da Noite, a mesma conferência só imprime `aviso:` e o PR entra. `de fora: PR #<B>, empilhado sobre o #<A>`: o B entra na subida seguinte do A, depois dele, sem tentativa; se o A virar baixa, o B também, com esse motivo.
- **3 ou 4:** pare; evento `erro` com a linha do script; imprima a chave e a linha. Rollback pelo `/deploy rollback`.
- **6:** uma tentativa por fatia e evento `erro` "rollback disparado no PR #N, versão vX.Y.Z voltou".
- **7 e 8:** evento `pronto-para-voce` com a linha do script; o mesmo comando de novo depois do humano. Sem tentativa.
- **9:** a main ficou vermelha depois do merge e a subida desfez o PR que a quebrou (linha `revert:`). O Estado da Onda já tem o evento `revert` e a issue já voltou para `ready-for-agent`: mande o `push:`, `E issue ... --status fila` na issue revertida (as outras do lote viram `mergeado`) e conte uma tentativa dela. A onda segue.
- **10:** a main ficou vermelha e nada foi desfeito (linha `quebrada:`). O Estado da Onda já está em `erro`: mande o `push:`, pare e vá para o Fim. Os PRs do lote seguem na main.

Cada PR que entrou: `E issue ... --status mergeado`. Saída 0 depois de um `pronto-para-voce` desta onda (a migration apareceu no health, 7 ou 8 resolvidas): `E resolvido ... --texto "migration <número> aplicada"` (ou a pendência que acabou). Depois: `python3 .claude/skills/onda-enxuta/scripts/medir_onda.py --onda <N> --issues <a,b,c> --prs <x,y,z> --inicio <passo 0>` (listas com vírgula, sem espaço).

### 6. Fim

Relatório de até 15 linhas (linha final da subida, issue · PR · versão, baixas, medição, intervalo entre os PRs verdes da onda anterior e o primeiro implementador desta; meta: menos de 2 min; última linha `retro: recomendada (<motivo>)` se houve baixa, rollback, revert, conflito na subida ou corretor em `effort: max`, senão `retro: dispensável`; quem roda é o humano, com `/retro-onda <nome>-onda<N>`), comentado em cada PRD da onda (issue sem PRD: no PR) com `<!-- automacao -->` e `## Onda <nome> <N>`. Passagem que ficou para depois da subida (passo 4): lance agora. Fila vazia: **Sinal final** (fechadas, ready-for-human, bloqueadas, deploys); com issue `ready-for-human` sobrando, evento `pronto-para-voce` "fila vazia, <n> issues com você" com `--espera-issue` dessas issues. Por último, `E fim ... --proxima <N+1> --retro "<a linha retro:>"` quando a onda seguinte foi lançada, ou `--ultima` no lugar de `--proxima` com a fila vazia (o PedroOS fala qual dos dois). Encerre depois do comentário.

## Scripts

| Script | Faz |
|---|---|
| `scripts/fluxo.py [chave \| classe \| notas <skill>]` | A configuração do Projeto (`.claude/fluxo.json`), a classe de um PR e as notas de uma skill. |
| `scripts/estado_onda.py iniciar\|issue\|evento\|fim\|resolvido\|mergeadas\|ler` | O estado da Onda em `~/.pedroos/ondas/<slug>/<sessao>-onda<N>.json` e a linha `push:` do celular. `resolvido` tira o "espera você"; `mergeadas` (chamado pela subida) tira a baixa da issue mergeada em qualquer onda do Projeto. |
| `scripts/lancar_sessao.sh <nome> <prompt.md>` | Sessão de fundo limpa: zero MCP, plugins desligados, Opus, `xhigh`. |
| `scripts/sensivel.py <PR>` | Arquivo sensível no PR (lista do Projeto em `revisao-sensivel.txt`, mais a varredura de `varredura` no `fluxo.json`); exit 0 se houver. |
| `scripts/lentes.py --pr <N>` | As Lentes que o `onda-revisor` lê no PR (`lentes/seguranca.md` quando toca login, permissão, rota ou segredo; `lentes/banco.md` quando tem migration; `lentes/design.md` quando o Projeto tem `design.guia` no `fluxo.json` e o PR muda tela) e a linha `Lentes:` do veredito. Quem roda é o revisor. |
| `scripts/design.py subir\|descer --pr <N>`, `achados --pr <N> <arquivo>` | A Lente de design: sobe o app do PR numa pasta temporária para os prints (ou diz por que não subiu), desce depois e separa os achados: P0 e P1 para o must-fix, P2 e P3 numa issue `needs-triage` e num comentário no PR. Quem roda é o revisor. |
| `scripts/conferir_lote.py --prs ...` | A conferência do lote, antes da subida: simula em memória os PRs entrando na main, na ordem, e imprime uma linha `conflito:` por PR que não cabe, com os arquivos e a base do corretor. Exit 0 se todos cabem, 1 se algum bate, 2 em erro. |
| `scripts/fechar_onda.py --prs ... [--sessao ...] [--dry-run]` | A subida: merge PR a PR pela API, caixas da issue marcadas, um build, health, rollback, registro (sem deploy, para no merge) e, no lote sem deploy, o teste da main. Códigos na docstring. |
| `scripts/sem_volta.py` | A conferência sem volta, chamada pela subida antes de cada merge: na Noite e na Sesta, o PR com migration que apaga dado, arquivo de segredo ou caminho `protegidos` fica de fora, com o motivo no PR, a issue na Etapa Humana e a Fatia em "espera você". Fora delas, só avisa. |
| `scripts/teste_da_main.py` | O passo depois do merge, chamado pela subida (com o `teste_da_main` do `fluxo.json`): testa a ponta da main, acha o primeiro merge do lote que quebra, desfaz por PR de revert, reabre a issue e grava o evento. |
| `scripts/medir_onda.py --onda N --issues ... --prs ...` | Conta da onda pelos JSONL (papel pelo `[papel: ...]` do prompt). |
| `scripts/ci_sem_runner.py <PR>` | Distingue falta de runner de CI vermelho; pede o rerun. |
