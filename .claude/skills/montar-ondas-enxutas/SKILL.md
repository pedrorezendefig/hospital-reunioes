---
name: montar-ondas-enxutas
description: Planeja sessões /onda-enxuta paralelas sem conflito, presta contas de toda issue aberta e entrega um comando de lançamento por sessão (sessão de fundo, zero MCP, Opus 5.5). Não executa. Sintaxe `/montar-ondas-enxutas [--exceto #PRD] [--max-sessoes N]`.
---

# Montar ondas enxutas: plano de sessões paralelas

Planejador da `/onda-enxuta` (cópia da `/montar-ondas`, com os passos 5 e 6 reescritos; a original não muda). A `/onda-enxuta` executa **uma** fila em **várias ondas**, uma sessão de fundo por onda; esta skill decide **quantas** filas abrir, **o que** vai em cada uma e **em que ordem** o humano aprova os merges. Sai daqui um arquivo de prompt por sessão e **um comando de lançamento** por sessão. Nada roda aqui: o Pedro roda os comandos num terminal, cada sessão nasce em segundo plano, faz a onda 1 até PR verde e para no checkpoint; ele entra com `claude attach` e escreve `vai`.

A meta é sair com **toda issue aberta em um de dois lugares**: dentro de um prompt (`ready-for-agent`) ou numa lista curta do que só o humano faz. Issue "esperando triagem" no fim do plano é falha do plano.

> **Por que não `/onda-enxuta --all` direto:** a fila geral mistura fatias de PRD que outra sessão já roda com avulsas que mexem no mesmo arquivo. Duas issues do mesmo arquivo na mesma onda viram conflito no merge, e duas sessões deployando ao mesmo tempo viram corrida de bump. O plano existe para separar antes de rodar.

## Sintaxe

```
/montar-ondas-enxutas [--exceto #PRD ...] [--max-sessoes N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `--exceto #PRD` | detectado | PRD cujas fatias outra sessão já está rodando. Sem o argumento, detecte: sub-issue com `in-progress` ou assignee, ou PR aberto da branch dela. |
| `--max-sessoes N` | 3 | Teto de filas (sessões) novas. Mais que 3 deployando concorre pelo mesmo Coolify e pelo mesmo humano aprovando. Cada fila vira uma cadeia de sessões de fundo, uma por onda. |

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
2. Comente na issue com o cabeçalho `## Triagem <data>`, o escopo cravado em 3 a 5 linhas (o que vira código, o que fica de fora, o cuidado herdado da revisão) e a frase "O humano pode reverter antes do merge". O implementador da `/onda-enxuta` lê a issue, não o seu prompt: a decisão precisa estar lá.
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

A `/onda-enxuta` para na largada se houver `revisor-comentou` de revisor humano. Leia o último comentário de cada issue com a label:

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

### 5. Escrever os prompts e os comandos de lançamento

Um arquivo de prompt por sessão, gravado em `%TEMP%\onda-enxuta\<nome>-onda1.md` (crie a pasta), e um comando de lançamento por sessão. Nomeie as sessões `onda-a`, `onda-b`, `onda-c`. O prompt inteiro também vai impresso na resposta, com um **cabeçalho de leitura** acima (o Pedro lê o cabeçalho para saber o que a sessão vai fazer; a sessão só recebe o arquivo). Formato do cabeçalho:

```markdown
### Sessão onda-a: <tema>

**Issues que ela toca:** #a, #b (onda 1) · #d (onda 2)

**O que cada uma faz:**
- #a: <uma linha, o que muda no código>
- #b: <uma linha>
- #d: <uma linha>

**Por que vale a pena:** <2 ou 3 frases, na língua do diretor: o que o usuário ganha ou o risco que fecha quando esta sessão terminar. Sem nome de arquivo.>

**Lançar:** `bash .claude/skills/onda-enxuta/scripts/lancar_sessao.sh onda-a-onda1 "$TEMP/onda-enxuta/onda-a-onda1.md"`
```

Depois do cabeçalho, o conteúdo do arquivo de prompt. A primeira linha precisa ser o comando, para a skill disparar. Template:

```
/onda-enxuta --sessao onda-a --onda 1 --paralelo <N>

Fila-alvo FIXA desta sessão. Não use a fila geral. Não toque nas issues #.., #.. (outra sessão está rodando).
- Onda 1: #a, #b, #c
- Onda 2: #d, #e
- Onda 3: #f
Ordem obrigatória: #a antes de #d (<arquivo em comum>). #b antes de #e e #f (<arquivo em comum>).

Auditorias de PRD desta sessão: quando #a e #b fecharem, audite o PRD #X contra produção. Quando #f fechar, audite o PRD #Y de novo (só a lacuna N estava aberta).

Decisões de triagem: comentadas nas issues (#.. em <data>; #.. em <data>).
- #<N>: <a decisão em uma linha, quando o corpo sozinho deixa dúvida: o item que fica de fora, o valor cravado, "só docs, nenhum código muda">.
- #<N> cria migration: o número é <0XX> (a <0XX-1> já existe em origin/main). O deploy não aplica: no checkpoint, lembre o humano de aplicar no Studio antes do "vai".

Outras sessões mergeiam e deployam em paralelo (onda-b, onda-c). O semáforo do fechar_onda.py ordena os deploys; prod hoje está em v<X.Y.Z>.
```

O que **não** entra mais no prompt, porque a skill ou o script já cuidam: "PARE e só comece quando eu escrever vai" (o lançamento é o vai), a regra do carimbo `revisor-comentou` (passo 0 da skill), o estado da árvore principal (o fechamento usa worktree próprio) e a instrução de reconferir `origin/main` antes do bump (o script faz).

A linha "Auditorias de PRD" entra quando a última sub-issue aberta de um PRD está nesta sessão. A linha por issue entra quando houver decisão que o corpo não traz sozinho. Cada sessão lista no "Não toque" as issues da outra, não só o PRD.

### 5b. Divulgação dos PRDs que fecham neste plano

PRD que fecha é entrega para o diretor e para quem opera o hospital, e eles só "veem" a funcionalidade pelo vídeo e pela página do `/divulgar`. Para **cada PRD cuja última fatia está nos prompts**, o plano traz também uma linha de divulgação. Sem ela, o PRD fecha no GitHub e ninguém fora do time fica sabendo.

Regras:

1. **Terminal próprio, nunca dentro da `/onda-enxuta`.** O `/divulgar` tem gate humano no draft do vídeo; a `/onda-enxuta` é AFK até o PR verde. Misturar os dois deixa a onda parada esperando um OK que não é de merge. O plano abre uma **sessão de divulgação** (uma só, sequencial: um PRD de cada vez) com um prompt por PRD.
2. **Quando cada vídeo pode começar** é decisão do plano, não do humano. Leia as fatias que faltam do PRD:
   - Se as fatias restantes **não mudam tela** (chore, teste, docs, manual): o vídeo começa **agora**, em paralelo com as ondas. O carimbo retrata a versão de prod de hoje e o PRD já está inteiro no app.
   - Se alguma fatia restante **muda tela**: o vídeo espera o deploy da última fatia visual (o carimbo "retrata o app em vX.Y.Z" precisa da versão que tem a tela) e roda em paralelo com o que sobrar (manual, docs).
3. **Saída padrão é vídeo e página** (o comando sem flag). `--so-video` só se o humano pedir. Contexto com página de módulo (`docs/comunicacao/ouvidoria/modulo/`): o prompt lembra de atualizar a cópia do MP4 lá.
4. O prompt de divulgação segue o mesmo formato do passo 5 (cabeçalho de leitura fora do bloco, comando na primeira linha do bloco) e diz **o que esperar antes de colar**: "cole depois do deploy verde da onda N da sessão A" ou "pode colar agora". Template:

```
/divulgar <PRD>

Contexto: o PRD #<PRD> fechou com as fatias #a, #b, #c (as visuais já estão em prod v<X.Y.Z>; a #d é só <chore/manual> e não muda tela).
O exemplo único da demonstração: <uma linha com o caso de uso ponta a ponta que a issue descreve, no vocabulário do CONTEXT.md>.
Fontes: o PRD e as filhas no GitHub, o código real do frontend (gh pr view <PR> --json files), ROTAS.md e o CONTEXT.md.
Pare no draft e me mostre os frames antes do render final. Depois da página publicada, registre o link no PRD com <!-- automacao --> na primeira linha do comentário.
<Se houver página de módulo: Atualize a cópia do MP4 em docs/comunicacao/<contexto>/modulo/ e republique a página de módulo.>
```

5. No passo a passo (6), a divulgação entra como item próprio: em qual momento colar cada prompt e a quem mandar o link depois (diretor, usuários do módulo). O envio do link é "precisa de você".

### 6. Relatório e ordem de comando

A resposta final tem esta forma, nesta ordem. É o que o Pedro lê do celular.

1. **Uma linha de contas:** "Das N abertas, X estão `ready-for-agent` e entram nos prompts. As outras Y não são trabalho de agente." Cite a pasta `%TEMP%\onda-enxuta\`.
2. **O que eu fiz:** issues triadas, decisões que o humano tomou e onde ficaram registradas, issue criada, PRD destravado, o que mudou no mundo durante o plano (sessão paralela, versão de prod, migration nova).
3. **As Y que ficam com você:** uma linha por issue, com a ação concreta e o que ela destrava. PRDs entram aqui como "fecham sozinhos quando as filhas fecharem".
4. **Tabela final** do passo 4.
5. **Os prompts**, inteiros, cada um com o cabeçalho de leitura (issues, resumo por issue, valor, comando de lançamento) em cima do bloco. Por último, os prompts de divulgação (5b), um por PRD que fecha.
6. **Passo a passo:**
   1. Num terminal na raiz do repositório, rodar o comando de lançamento de cada sessão (todos de uma vez, se quiser). Cada uma nasce em segundo plano, monta a fila, escreve o Mapa do terreno do PRD se ainda não existir e roda a onda 1 até PR verde. `claude agents` lista as sessões vivas; `claude logs <id>` mostra o andamento.
   2. Quando chegar a notificação de checkpoint: `claude attach <id>` e escrever `vai #a #b` (ou com condição, ou `abortar`). **Uma sessão por vez**: o semáforo enfileira os deploys sozinho, mas aprovar uma de cada vez evita corrida de versão na sua cabeça. Liste a sequência onda a onda, alternando sessões, e marque na linha certa "aplique a migration 0XX no Studio antes do vai" e "ela audita o PRD #X em seguida". Ordem: a sessão menor primeiro, a onda com migration quando o Pedro estiver perto do Studio, a fatia que reabre auditoria de PRD por último.
   3. Depois do "vai", a sessão fecha a onda (um push, um build), imprime a conta de tokens e lança sozinha a sessão da onda seguinte. Nada a fazer até a próxima notificação.
   4. **Divulgação:** para cada PRD que fecha, a linha "cole o prompt de `/divulgar #X` num terminal próprio" no momento certo (agora, ou logo após o deploy da onda que sobe a última tela) e, depois do link publicado, "mande o link ao diretor e aos usuários do módulo".
   5. "No tempo morto": as tarefas do item 3.

## O que esta skill não faz

- Não dispara sessão, não pega issue, não mergeia. Quem executa é a `/onda-enxuta`, uma sessão de fundo por onda, lançada pelo comando que este plano entrega.
- Não tria issue sem critério de aceite. Não decide sozinha uma decisão de domínio (ADR, RN do `CONTEXT.md`): ela pergunta ao humano (2b) e crava a resposta. Só vai para "precisa de você" a decisão sem saídas formuladas, ou a que vira PRD novo.
- Não faz ação operacional (cadastro em produção, envio de arquivo a terceiros, pedido a serviço externo). Isso é "precisa de você", com o passo escrito.
- Não substitui o `/triage` para issue nova sem critério; só move as que já nasceram prontas.
- Não gera vídeo nem página: escreve o prompt do `/divulgar` e diz quando colar. Quem roda é o terminal de divulgação, com o gate humano no draft.
