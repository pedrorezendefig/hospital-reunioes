---
name: montar-ondas
description: Planeja sessões /onda paralelas sem conflito, presta contas de toda issue aberta e entrega um prompt por sessão. Não executa. Sintaxe `/montar-ondas [--exceto #PRD] [--max-sessoes N]`.
---

# Montar ondas: plano de sessões paralelas

Planejador da `/onda`. A `/onda` executa **uma** fila; esta skill decide **quantas** `/onda` abrir, **o que** vai em cada uma e **em que ordem** o humano aprova os merges. Sai daqui um arquivo com um prompt por sessão. Nada roda: o Pedro abre os terminais, cola os prompts, e cada sessão fica parada até ele escrever `vai`.

A meta é sair com **toda issue aberta em um de dois lugares**: dentro de um prompt (`ready-for-agent`) ou numa lista curta do que só o humano faz. Issue "esperando triagem" no fim do plano é falha do plano.

> **Por que não `/onda --all` direto:** a fila geral mistura fatias de PRD que outra sessão já roda com avulsas que mexem no mesmo arquivo. Duas issues do mesmo arquivo na mesma onda viram conflito no merge, e duas sessões deployando ao mesmo tempo viram corrida de bump. O plano existe para separar antes de rodar.

## Sintaxe

```
/montar-ondas [--exceto #PRD ...] [--max-sessoes N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `--exceto #PRD` | detectado | PRD cujas fatias outra sessão já está rodando. Sem o argumento, detecte: sub-issue com `in-progress` ou assignee, ou PR aberto da branch dela. |
| `--max-sessoes N` | 3 | Teto de sessões novas. Mais que 3 sessões deployando concorre pelo mesmo Coolify e pelo mesmo humano aprovando. |

## Fluxo

### 1. Inventário

Liste tudo que está aberto, com labels, dono e bloqueio nativo:

```bash
gh issue list --state open --limit 100 \
  --json number,title,labels,assignees \
  --jq '.[] | "\(.number)\t\(.labels|map(.name)|join(","))\t\(.assignees|map(.login)|join(","))\t\(.title)"' | sort -n

REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh api graphql -f query="{ repository(owner:\"${REPO%/*}\", name:\"${REPO#*/}\") { issues(states:OPEN, first:100) { nodes { number blockedBy(first:10){ nodes { number state } } } } } }" \
  --jq '.data.repository.issues.nodes[] | select(.blockedBy.nodes|length>0) | "\(.number) bloqueada por: \(.blockedBy.nodes|map("#\(.number)(\(.state))")|join(", "))"'

gh pr list --state open --json number,headRefName,title
git worktree list | grep -v detached | tail -40
git fetch -q origin && git rev-list --left-right --count origin/main...HEAD
git ls-tree --name-only origin/main hospital-reunioes/supabase/migrations/ | tail -3
curl -s https://reunioes.hospitalsaomatheus.cloud/api/health
```

Para cada PRD aberto, pegue as sub-issues (`gh api "repos/$REPO/issues/<PRD>/sub_issues"`) e o **último comentário inteiro** (a auditoria de conclusão diz se o PRD só espera trabalho humano, ou se foi REPROVADO com lacuna que pede decisão).

Leia o corpo de toda issue candidata. É dele que saem os arquivos (passo 4) e as decisões (passo 2).

Classifique **cada** issue aberta em exatamente um balde. Conte: `N abertas = agente + decisão + PRD + só humano`. Esse somatório aparece no relatório.

| Balde | Regra | Destino |
|---|---|---|
| Outra sessão | sub-issue de PRD em `--exceto`, ou já com `in-progress`/assignee, ou PR aberto | fora, citar no relatório |
| Pronta | `ready-for-agent`, sem dono, bloqueio só por issue fechada | entra |
| Sem triagem | `needs-triage` com critérios de aceite escritos e sem decisão de domínio | triagem rápida (passo 2a) |
| Decisão | `needs-triage` ou `ready-for-human` cujo corpo traz **duas saídas escritas** (A/B, 1/2) | pergunta ao humano (passo 2b), depois entra |
| PRD | issue-mãe com sub-issues | não é trabalho; fecha sozinho quando as filhas fecham e a auditoria passa. Se a auditoria REPROVOU: passo 2c |
| Só humano | ação operacional (cadastro na tela, mandar arquivo para alguém), `needs-info` que depende de terceiro, `wontfix` | fora, listar como "precisa de você" com o que exatamente fazer |
| Bloqueada | bloqueio nativo por issue ainda aberta | entra na onda seguinte à da bloqueadora, na mesma sessão |

### 2. Deixar tudo `ready-for-agent`

#### 2a. Triagem rápida das `needs-triage`

Só tria quem já traz critérios de aceite (as issues que os revisores independentes abrem vêm com "Critérios de aceite (rascunho, a triagem confirma)"). Issue sem critério fica no balde "precisa de você".

Para cada uma:

1. Se a issue tem "Decisão pendente" com recomendação, **crave a recomendação que a própria issue traz**. Sem recomendação escrita e sem duas saídas nomeadas, escolha a opção mais conservadora (fecha a porta, não redesenha) e deixe o redesenho como follow-up.
2. Comente na issue com o cabeçalho `## Triagem <data>`, o escopo cravado em 3 a 5 linhas (o que vira código, o que fica de fora, o cuidado herdado da revisão) e a frase "O humano pode reverter antes do merge". O sub-agente da `/onda` lê a issue, não o seu prompt: a decisão precisa estar lá.
3. Mova a label: `gh issue edit <N> --remove-label needs-triage --add-label ready-for-agent`.

O classifier pode negar um script com vários `gh issue comment` de uma vez. Comente uma issue por comando (várias chamadas independentes na mesma resposta podem).

#### 2b. Decisões de domínio: perguntar, não devolver

Issue que a própria auditoria marcou como "decisão do diretor" (o que a área vê no caso anônimo, quem pode apagar série alheia, se a ação do ouvidor carimba o visto) **não vai para "precisa de você"** se o corpo já traz as duas saídas. O Pedro está na sessão: pergunte.

1. Uma chamada de `AskUserQuestion` com até 4 perguntas, **2 opções cada**, a recomendada primeiro com "(Recomendado)". Cada opção diz em uma linha o que vira depois: "vira issue de docs", "vira issue de código com teste X", "vira PRD novo, fica fora de hoje".
2. Com a resposta, comente na issue `## Triagem <data>` começando por "**Decisão registrada: saída X.**", o motivo em uma frase, e o escopo cravado (o que carimba, qual status de recusa, o que fica fora).
3. Mova a label: `--remove-label ready-for-human` (ou `needs-triage`) `--add-label ready-for-agent`. Decisão que vira só docs (emenda de ADR, RN no `CONTEXT.md`, comentário de migration antiga) também é issue de agente: `fatia:P`, e o prompt diz "só docs, nenhum código muda".

Fica em "precisa de você" só a issue **sem saídas nomeadas** (a pergunta ainda não está formulada) ou cuja resposta é um PRD novo.

#### 2c. PRD reprovado na auditoria

Se o último comentário do PRD é `VEREDITO: REPROVADO` com lacuna que pede decisão (a, b, c):

1. Pergunte no mesmo `AskUserQuestion` do 2b.
2. Abra a fatia com `gh issue create` (seção "Para o diretor", "## Pai #PRD", "O que construir", critérios de aceite com o **valor cravado no critério**, não no corpo: foi assim que a lacuna escapou). Labels `type:feature,ready-for-agent,fatia:P`.
3. Pendure no PRD: `gh api -X POST repos/$REPO/issues/<PRD>/sub_issues -F sub_issue_id=$(gh api repos/$REPO/issues/<N> --jq .id)`.
4. Comente a decisão no PRD (`## Decisão <data> sobre a lacuna N`) e devolva o PRD para `ready-for-agent`. O prompt da sessão que roda a fatia manda auditar o PRD de novo quando ela fechar.

### 3. Ruído de `revisor-comentou`

A `/onda` para na largada se houver `revisor-comentou`. Leia o último comentário de cada issue com a label:

- Comentário do próprio Pedro (decisão registrada) ou do sub-agente da onda (a Action aplica a label ao comentário do próprio sub-agente) → remova a label.
- Comentário de revisor de verdade pedindo mudança → a issue fica fora do plano e vai para "precisa de você".

**A Action carimba os SEUS comentários também.** Cada `## Triagem` e cada `## Decisão` que você escrever recebe `revisor-comentou` segundos depois, inclusive no PRD. Depois do último comentário, rode em segundo plano um `until` que remove a label e só termina quando `gh issue list --state open --label revisor-comentou` vier vazio por 30 segundos. Confira o vazio antes de entregar os prompts. Não use `sleep` encadeado em primeiro plano.

### 4. Reinventariar, depois agrupar por arquivo tocado

**Antes de montar a tabela, rode o inventário de novo** (o bloco do passo 1 inteiro). Enquanto você triava, outra sessão pode ter mergeado (issue que estava no plano fechou, prod mudou de versão, a numeração de migration andou) e revisores podem ter aberto issue nova. Nesta skill o mundo muda no meio: em 03/09/2026 a #489 fechou, a 096 apareceu e nasceram #546 e #547 entre o primeiro e o segundo inventário. Issue nova com critério passa pelo passo 2.

O corpo das issues cita os arquivos (`ouvidoria_setor.py:102`, `page.tsx:278`). Quando cita de forma vaga ("a tupla", "a rota de reenvio"), `grep` no repo antes de agrupar. Monte a tabela issue × arquivos e aplique:

1. **Mesma sessão, ondas diferentes**: issues que tocam o mesmo arquivo. Dentro da sessão a ordem é: quem a issue diz que vem antes ("fechar as duas em conjunto", "rodar depois da #N"), depois bloqueio nativo, depois `fatia:P` antes de `M`/`G`. Varredura de módulo inteiro (tipografia, lint) vai na última onda da sessão dona daquele módulo.
2. **Sessões diferentes**: grupos de arquivos disjuntos. Nomeie cada sessão pelo tema (segurança e logs, portal do setor, ouvidoria backend). Issue de docs (`CONTEXT.md`, ADR) conta como arquivo: duas que mexem no `CONTEXT.md` não vão na mesma onda.
3. **Paralelo por onda**: até 3. Sessão com 2 issues por onda roda `--paralelo 2`. Equilibre o número de ondas entre as sessões: cada onda é um deploy e um checkpoint do humano.
4. Conflito **entre** sessões (dois grupos tocando `ouvidoria_notificacoes.py` em funções diferentes) é aceitável: resolve no merge sequencial. Conflito **dentro** da onda não é.
5. Issue que cria migration: **calcule o número** pelo `ls` de `origin/main` e escreva no prompt ("o número é 097; a 096 já existe"). O deploy não aplica migration; o Pedro aplica no Studio.

Mostre a tabela final: sessão · onda · issues · arquivo em comum dentro da sessão (o motivo de a onda ser essa).

### 5. Escrever os prompts

Um prompt por sessão, gravado em `<scratchpad>/prompts-sessoes-<ddmm>.md` e impresso inteiro na resposta (o Pedro copia do celular). Template:

```
/onda --paralelo <N>

Fila-alvo FIXA desta sessão. Não use a fila geral. Não toque nas issues #.., #.. (outra sessão está rodando).
- Onda 1: #a, #b, #c
- Onda 2: #d, #e
- Onda 3: #f
Ordem obrigatória: #a antes de #d (<arquivo em comum>). #b antes de #e e #f (<arquivo em comum>).

Auditorias de PRD desta sessão: quando #a e #b fecharem, audite o PRD #X contra produção (como no ADR 0029). Quando #f fechar, audite o PRD #Y de novo (só a lacuna N estava aberta).

Regras extras:
- NÃO dispare o lote agora. Monte a tabela da fila, confira o estado das issues no GitHub e PARE. Só comece quando eu escrever "vai".
- Se a label revisor-comentou aparecer no PRD #X ou #Y, é o carimbo automático do comentário de triagem ou auditoria. Remova e siga; não pare a onda por isso.
- As decisões de triagem estão comentadas nas issues (#.. em <data>; #.. em <data>).
- #<N>: <a decisão em uma linha, quando o corpo sozinho deixa dúvida: o item que fica de fora, o valor cravado, "só docs, nenhum código muda">.
- #<N> cria migration: o número é <0XX> (a <0XX-1> já existe em origin/main). O deploy não aplica. No checkpoint, me lembre que eu aplico no Studio e rodo a fumaça.
- A árvore principal está na branch <git branch --show-current> com <estado: limpa | N commits não pushados e pasta X não commitada>. Bookkeeping do deploy via worktree detached de origin/main. Nunca reset na principal.
- Outras sessões mergeiam e deployam em paralelo. Antes de cada bump e antes do /deploy ship, confira origin/main (package.json + ls hospital-reunioes/supabase/migrations) e o version do /api/health de prod (hoje v<X.Y.Z>). Se houver deploy de outra sessão em andamento no Coolify, espere terminar.
```

A linha "Auditorias de PRD" entra quando a última sub-issue aberta de um PRD está nesta sessão. A linha por issue entra quando houver decisão que o corpo não traz sozinho (escopo reduzido aceitável, item recusado, valor cravado, o que fica como follow-up). Cada sessão lista no "Não toque" as issues da outra, não só o PRD.

### 6. Relatório e ordem de comando

A resposta final tem esta forma, nesta ordem. É o que o Pedro lê do celular.

1. **Uma linha de contas:** "Das N abertas, X estão `ready-for-agent` e entram nos prompts. As outras Y não são trabalho de agente." Cite o arquivo do scratchpad.
2. **O que eu fiz:** issues triadas, decisões que o humano tomou e onde ficaram registradas, issue criada, PRD destravado, o que mudou no mundo durante o plano (sessão paralela, versão de prod, migration nova).
3. **As Y que ficam com você:** uma linha por issue, com a ação concreta ("cadastrar os 4 pontos na tela e mandar os PNGs", "disparar o pedido de API ao Google") e o que ela destrava. PRDs entram aqui como "fecham sozinhos quando as filhas fecharem".
4. **Tabela final** do passo 4.
5. **Os prompts**, inteiros, um bloco de código por sessão.
6. **Passo a passo:**
   1. Abrir os terminais na árvore principal e colar um prompt em cada. Cada sessão monta a fila e para.
   2. Escrever `vai` em todas. Elas rodam até PR verde sem chamar.
   3. Checkpoints de merge, **uma sessão por vez**, esperando o deploy verde antes do próximo. Liste a sequência onda a onda, alternando sessões, e marque na linha certa "aplique a migration 0XX no Studio" e "ela audita o PRD #X em seguida". Ordem: a sessão menor primeiro, a onda com migration quando o Pedro estiver perto do Studio, a fatia que reabre auditoria de PRD por último. É isso que dissolve a corrida de bump.
   4. "No tempo morto": as tarefas do item 3.

## O que esta skill não faz

- Não dispara sessão, não pega issue, não mergeia. Quem executa é a `/onda` em cada terminal.
- Não tria issue sem critério de aceite. Não decide sozinha uma decisão de domínio (ADR, RN do `CONTEXT.md`): ela pergunta ao humano (2b) e crava a resposta. Só vai para "precisa de você" a decisão sem saídas formuladas, ou a que vira PRD novo.
- Não faz ação operacional (cadastro em produção, envio de arquivo a terceiros, pedido a serviço externo). Isso é "precisa de você", com o passo escrito.
- Não substitui o `/triage` para issue nova sem critério; só move as que já nasceram prontas.
