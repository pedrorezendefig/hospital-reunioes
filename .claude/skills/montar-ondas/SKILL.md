---
name: montar-ondas
description: Monta o plano de sessões paralelas para esvaziar a fila de issues do GitHub (avulsas e fatias de PRD) sem conflito entre sessões, e entrega um prompt pronto de /onda por sessão, que fica parado aguardando a ordem "vai". Faz o inventário das issues abertas, a triagem rápida das needs-triage com decisão cravada, o agrupamento por arquivo tocado e a ordem de aprovação dos checkpoints. Não executa nada. Use quando o usuário disser "montar ondas", "/montar-ondas", "quantas sessões eu abro", "organiza a fila em sessões", "me manda os prompts das sessões", "o que dá pra rodar em paralelo", ou quiser sair (academia, viagem) e deixar sessões prontas para disparar do celular. Sintaxe `/montar-ondas [--exceto #PRD ...] [--max-sessoes N]`.
---

# Montar ondas: plano de sessões paralelas

Planejador da `/onda`. A `/onda` executa **uma** fila; esta skill decide **quantas** `/onda` abrir, **o que** vai em cada uma e **em que ordem** o humano aprova os merges. Sai daqui um arquivo com um prompt por sessão. Nada roda: o Pedro abre os terminais, cola os prompts, e cada sessão fica parada até ele escrever `vai`.

> **Por que não `/onda --all` direto:** a fila geral mistura fatias de PRD que outra sessão já roda com avulsas que mexem no mesmo arquivo. Duas issues do mesmo arquivo na mesma onda viram conflito no merge, e duas sessões deployando ao mesmo tempo viram corrida de bump ([[project_bump_race_sessoes_paralelas]]). O plano existe para separar antes de rodar.

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
```

Para cada PRD aberto, pegue as sub-issues (`gh api "repos/$REPO/issues/<PRD>/sub_issues"`) e o último comentário (a auditoria de conclusão diz se o PRD só espera trabalho humano).

Classifique cada issue aberta em um balde:

| Balde | Regra | Destino |
|---|---|---|
| Outra sessão | sub-issue de PRD em `--exceto`, ou já com `in-progress`/assignee | fora, citar no relatório |
| Pronta | `ready-for-agent`, sem dono, bloqueio só por issue fechada | entra |
| Sem triagem | `needs-triage` com critérios de aceite escritos | triagem rápida (passo 2) |
| Só humano | `ready-for-human`, `needs-info`, `wontfix` | fora, listar como "precisa de você" |
| Bloqueada | bloqueio nativo por issue ainda aberta | entra na onda seguinte à da bloqueadora, na mesma sessão |

### 2. Triagem rápida das `needs-triage`

Só tria quem já traz critérios de aceite (as issues que os revisores independentes abrem vêm com "Critérios de aceite (rascunho, a triagem confirma)"). Issue sem critério fica no balde "precisa de você".

Para cada uma:

1. Se a issue tem "Decisão pendente", **crave a recomendação que a própria issue traz**. Sem recomendação escrita, escolha a opção mais conservadora (fecha a porta, não redesenha) e deixe o redesenho como follow-up.
2. Comente na issue com o cabeçalho `## Triagem <data>`, a decisão cravada e a frase "o humano pode reverter antes do merge". O sub-agente da `/onda` lê a issue, não o seu prompt: a decisão precisa estar lá.
3. Mova a label: `gh issue edit <N> --remove-label needs-triage --add-label ready-for-agent`.

O classifier pode negar um script com vários `gh issue comment` de uma vez. Comente uma issue por comando.

### 3. Ruído de `revisor-comentou`

A `/onda` para na largada se houver `revisor-comentou`. Leia o último comentário de cada issue com a label:

- Comentário do próprio Pedro (decisão registrada) ou do sub-agente da onda ([[project_revisor_comentou_falso_positivo]]) → remova a label.
- Comentário de revisor de verdade pedindo mudança → a issue fica fora do plano e vai para "precisa de você".
- PRD `ready-for-human` com a label → não mexa; o prompt de cada sessão manda ignorar.

### 4. Agrupar por arquivo tocado

O corpo das issues cita os arquivos (`ouvidoria_setor.py:102`, `page.tsx:278`). Monte a tabela issue × arquivos e aplique:

1. **Mesma sessão, ondas diferentes**: issues que tocam o mesmo arquivo. Dentro da sessão a ordem é: quem a issue diz que vem antes ("fechar as duas em conjunto", "rodar depois da #N"), depois bloqueio nativo, depois `fatia:P` antes de `M`/`G`.
2. **Sessões diferentes**: grupos de arquivos disjuntos. Nomeie cada sessão pelo tema (segurança e logs, portal do setor, ouvidoria backend).
3. **Paralelo por onda**: até 3. Sessão com 2 issues roda `--paralelo 2`.
4. Conflito **entre** sessões (dois grupos tocando `ouvidoria_notificacoes.py` em funções diferentes) é aceitável: resolve no merge sequencial. Conflito **dentro** da onda não é.
5. Issue que cria migration: marque no prompt. O deploy não aplica migration; o Pedro aplica no Studio ([[project_deploy_ops_manual_ship]]).

Mostre a tabela final: sessão · onda · issues · fatia · arquivos em comum.

### 5. Escrever os prompts

Um prompt por sessão, gravado em `<scratchpad>/prompts-sessoes-<ddmm>.md` e impresso inteiro na resposta (o Pedro copia do celular). Template:

```
/onda --paralelo <N>

Fila-alvo FIXA desta sessão. Não use a fila geral. Não toque nas sub-issues do PRD #<X> (outra sessão está rodando).
- Onda 1: #a, #b, #c
- Onda 2: #d, #e
Ordem obrigatória: #a antes de #d (<motivo em uma linha>).

Regras extras:
- NÃO dispare o lote agora. Monte a tabela da fila, confira o estado das issues no GitHub e PARE. Só comece quando eu escrever "vai".
- Ignore a label revisor-comentou do PRD #<Y> (é ready-for-human, curadoria minha).
- As decisões de triagem estão comentadas nas issues #.. (<data>).
- A árvore principal está na branch <git branch --show-current> com <estado: limpa | arquivo não commitado>. Bookkeeping do deploy via worktree detached de origin/main. Nunca reset na principal.
- Outras sessões mergeiam e deployam em paralelo. Antes de cada bump e antes do /deploy ship, confira origin/main (package.json + ls migrations) e o version do /api/health de prod. Se houver deploy de outra sessão em andamento no Coolify, espere terminar.
- #<N> cria migration: o deploy não aplica. No checkpoint, me lembre que eu aplico no Studio.
```

Acrescente uma linha por issue só quando houver decisão que o corpo não traz (escopo reduzido aceitável, o que fica como follow-up).

### 6. Ordem de comando

Feche a resposta com a sequência que o Pedro executa do celular:

1. Abrir os terminais na árvore principal e colar um prompt em cada. Cada sessão monta a fila e para.
2. Escrever `vai` em todas. Elas rodam até PR verde sem chamar.
3. Checkpoints de merge: aprovar **uma sessão por vez** e esperar o deploy dela ficar verde antes da próxima. Ordem: a sessão menor primeiro, o PRD de outra sessão por último. É isso que dissolve a corrida de bump.
4. Migrations pendentes no Studio, se houver.

## O que esta skill não faz

- Não dispara sessão, não pega issue, não mergeia. Quem executa é a `/onda` em cada terminal.
- Não tria issue sem critério de aceite nem decide o que a issue marca como decisão de domínio (ADR, RN do `CONTEXT.md`) sem recomendação escrita. Isso vai para "precisa de você".
- Não substitui o `/triage` para issue nova; só move as que já nasceram prontas.
