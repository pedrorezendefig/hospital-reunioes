---
name: montar-manual
description: Inventaria o passivo do Manual módulo por módulo (página, print, vídeo, Novidades) e entrega um prompt por terminal, um por módulo, teto de 3. Não executa. Sintaxe `/montar-manual [--max-sessoes N]`.
---

# Montar manual: plano de terminais por módulo

Planejador da `/manual`, como a `/montar-ondas` é da `/onda`. A `/manual` produz **um** módulo; esta skill decide **quantos** terminais abrir, **o que** cada um produz e **o que sobra para o humano**. Sai daqui um arquivo com um prompt por terminal. Nada roda: o Pedro abre os terminais e cola.

A meta é sair com **toda lacuna do manual em exatamente um lugar**: dentro do prompt de um módulo, ou na lista curta do que só o humano faz. Lacuna sem dono no fim do plano é falha do plano.

> **Por que um terminal por módulo:** o conflito do manual é de pasta, não de arquivo. Cada módulo mexe em `docs/manual/src/content/docs/<modulo>/`, `src/assets/<modulo>/`, `video/<modulo>/` e `prints/<modulo>.py`, e nada mais. Dois terminais no mesmo módulo brigam pelo `novidades.md` e pelo roteiro de prints; dois em módulos diferentes não se encontram. O teto de 3 é de CPU: render de vídeo do HyperFrames ocupa a máquina inteira (ADR 0057, decisão 9).

## Sintaxe

```
/montar-manual [--max-sessoes N]
```

| Argumento | Default | Efeito |
|---|---|---|
| `--max-sessoes N` | 3 | Teto de terminais simultâneos. Acima de 3, os renders de vídeo disputam a CPU e todos ficam lentos. Módulo que não couber entra na rodada seguinte, e o plano diz isso. |

## Fluxo

### 1. Inventário do que o repositório prova

Primeiro monte a lista de PRDs **já em produção** por módulo. Ela é o que separa "draft certo" (funcionalidade que ainda não subiu) de "draft esquecido":

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
gh issue list --state closed --limit 100 --json number,title,labels,closedAt \
  --jq '.[] | select(.title|startswith("PRD")) | "\(.number)\t\(.closedAt)\t\(.title)"'
python3 -c "import json;[print(d['at'][:10], d['app_version'], d['subject']) for d in json.load(open('docs/spec/deploy/history.json'))['deploys'][:20]]"
```

O PRD só entra se **subiu**: a data do deploy está no `history.json`, e é ela que vira a data da entrada de Novidades (nunca a data da issue nem a de hoje). Deploy registrado a partir da issue #735 traz o campo `prds` na entrada: leia dele, não do `notes` em prosa. Entrada antiga não tem o campo, e aí o PRD sai do `notes` mesmo, na mão. O que o `history.json` não diz é de que **módulo** é cada PRD: isso continua vindo da leitura do PRD. Grave o resultado no scratchpad:

```bash
cat > <scratchpad>/entregues.json <<'JSON'
{"primeiros-passos": [], "reunioes": [317, 706], "ouvidoria": [272, 731], "pops": [], "admin": []}
JSON
python3 tools/inventario_manual.py --dir docs/manual --entregues <scratchpad>/entregues.json
```

O inventário acusa, por módulo, quatro lacunas: `sem-video` (Página de tarefa sem Vídeo de tarefa), `print-faltando` (a página aponta para um print que não existe), `prd-sem-novidades` (PRD em produção cujo número não está no `prd:` do frontmatter do `novidades.md` do módulo, que é como o inventário conta a entrada) e `draft-entregue` (página em `draft` de PRD que já está no ar). Ele **sai com código 1** quando a conta não fecha: página fora dos cinco módulos (sem terminal que a feche) ou nenhuma página encontrada (varredura que não rodou não pode passar por manual pronto). Nesse caso conserte antes de planejar.

Sem `--entregues` o relatório sai, mas declara que dois dos quatro tipos não foram conferidos. Não planeje em cima disso: a lista de PRDs entregues é o passo 1, não um extra.

### 2. Inventário do que o repositório não prova: tela sem página

O script conta o que existe. Falta a pergunta que só a leitura responde: **que tela do app ainda não tem Página de tarefa?**

Para cada módulo, cruze três fontes e escreva a lista de páginas que faltam:

1. `docs/spec/snapshots/ROTAS.md` e `FLUXOGRAMAS.md`: as telas que existem de verdade e o caminho até elas.
2. O menu do app (`hospital-reunioes/frontend`, a sidebar): é a ordem que o manual imita, e é onde o módulo de cada rota fica explícito.
3. Os PRDs fechados do módulo: cada um entregou tela, e toda tela que a pessoa opera é candidata a uma tarefa.

Regras de recorte, para a lista não inchar: uma tarefa é **uma ação** ("Registrar uma manifestação"), tela sem ação de usuário vira página **Como funciona**, e tela aberta por link ou QR entra no módulo dela com o selo "Sem login" (nunca numa seção "Público" à parte). Tela da aba Tecnologia fica fora do manual.

### 3. Cada lacuna em exatamente um balde

| Balde | O que cai aqui | Destino |
|---|---|---|
| Terminal do módulo | tudo que tem módulo dono: página que falta, `sem-video`, `print-faltando`, `prd-sem-novidades`, `draft-entregue` | um prompt por módulo (passo 5) |
| Só você | OK nos drafts de vídeo, registro de DNS, troca do QR da apresentação, publicação na Vercel depois dos merges | lista "precisa de você" (passo 6) |

A regra de desempate é a pasta: a lacuna pertence ao módulo da página. Lacuna sem módulo não existe por construção, e é isso que o código de saída 1 do inventário garante.

**O que nunca entra num prompt de módulo:** publicar (`publicar.sh`, `/manual publicar`, `vercel deploy`), mexer no tema, no `astro.config.mjs`, na home ou em `tools/`, e tocar a pasta de outro módulo. A publicação é **um passo só, depois dos merges**: N terminais publicando geram N deploys do mesmo site e o último a subir apaga o trabalho dos outros.

### 4. Escolher os terminais

Um terminal por módulo, até `--max-sessoes` (3 por default). A ordem é: módulo com Fatia de módulo aberta e desbloqueada primeiro, depois o de maior passivo, depois o resto. Confira no GitHub quem já tem dono, para não mandar o Pedro abrir terminal de issue que outra sessão pegou:

```bash
gh issue list --state open --label ready-for-agent --json number,title,assignees \
  --jq '.[] | select(.title|contains("Manual:")) | "\(.number)\t\(.assignees|map(.login)|join(","))\t\(.title)"'
```

Módulo que não coube no teto entra na rodada seguinte; o plano diz qual é e por quê.

### 5. Escrever os prompts

Um prompt por terminal, gravado em `<scratchpad>/prompts-manual-<ddmm>.md` e impresso inteiro na resposta (o Pedro copia do celular).

Cada prompt tem um **cabeçalho de leitura fora do bloco** (o Pedro lê antes de colar; a sessão recebe só o bloco):

```markdown
### Terminal <letra>: módulo <modulo> (issue #<N>)

**O que este terminal produz:** <n> Páginas de tarefa, <n> prints, <n> Vídeos de tarefa, <n> entradas de Novidades.

**Por que vale a pena:** <2 ou 3 frases na língua do diretor: que dúvida do usuário do hospital para de chegar em você quando esta seção estiver no ar.>
```

O bloco **abre pelo worktree, nunca por um comando que cria branch**. `/pegar-issue` faz `git checkout -b`, e rodado na árvore principal, que é compartilhada, três terminais trocam a branch um debaixo do outro: é exatamente a colisão que esta skill existe para evitar. Por isso o worktree vem primeiro, e o claim, a branch e todo o resto acontecem **dentro** dele. Template:

```
Terminal do módulo <modulo>. Antes de tocar em qualquer arquivo, entre num worktree próprio:

git worktree add ../hospital-issue-<N> origin/main

Abra a sessão dentro de ../hospital-issue-<N> (ou use o EnterWorktree) e faça tudo lá. NÃO rode git checkout -b na árvore principal: outros terminais estão trabalhando nela agora.

Já dentro do worktree, nesta ordem:
1. /pegar-issue <N>   (claim atômico e branch, criados aqui dentro)
2. /manual <modulo>   (produz só o que está na lista abaixo)

Confira `git branch --show-current` antes de cada commit.

Pastas que você pode tocar, e nenhuma outra:
- docs/manual/src/content/docs/<modulo>/
- docs/manual/src/assets/<modulo>/
- docs/manual/video/<modulo>/
- docs/manual/prints/<modulo>.py

A produzir:
- Páginas de tarefa que faltam: <lista, uma por linha, com o título no infinitivo>
- Prints: <lista> (entram no Roteiro de prints do módulo, nunca recortados à mão)
- Vídeos de tarefa: <lista de slugs> (composição em docs/manual/video/<modulo>/<slug>/)
- Novidades: entrada do PRD #<N> com a data do deploy (history.json), não a de hoje, E o número no frontmatter do novidades.md (prd: [<N>, ...]), senão o inventário continua acusando a entrada que você acabou de escrever
- Draft a tirar: <páginas em draft cujo PRD já está em produção>

Regras:
- Página de coisa que já está no ar sai sem draft; página de PRD que ainda não subiu nasce em draft.
- NÃO publique: nada de publicar.sh, /manual publicar ou vercel deploy. A publicação é um passo só, meu, depois dos merges.
- Não toque no tema, no astro.config.mjs, na home, em tools/ nem na pasta de outro módulo. Outro terminal está mexendo neles agora.
- O site do manual é docs/manual/src/content/docs/. A pasta docs/manual/tecnologia/ é o manual antigo, de página única, e não é sua: não edite nada lá.
- Antes de abrir o PR, os quatro comandos do checklist da /manual:
  python3 tools/lint_manual.py --dir docs/manual/src/content/docs
  python3 tools/checar_video_manual.py --dir docs/manual
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
  python3 tools/checar_build_manual.py --dir docs/manual
- Pare no draft de cada vídeo e me mande o caminho do MP4: o OK é meu, e só depois vem o render final.
- Feche com /ship "docs: manual do módulo <modulo>" --issue <N> --no-deploy
```

A linha "Draft a tirar" só entra quando o inventário achou `draft-entregue` naquele módulo. A linha de Novidades repete o número do PRD e a data que você leu do `history.json`: o terminal não vai adivinhar isso sozinho.

### 6. Relatório

A resposta final, nesta ordem:

1. **Uma linha de contas:** "L lacunas no manual: X vão para os N terminais, Y são suas." Cite o arquivo do scratchpad.
2. **O inventário por módulo**, a tabela do passo 1 mais a lista de páginas que faltam do passo 2, módulo a módulo, com o total de cada um.
3. **As que ficam com você:** uma linha por item, com a ação concreta ("aprovar o draft do vídeo X", "criar o registro A de `manual` apontando para 76.76.21.21 na Hostinger", "trocar o QR do pptx da apresentação") e o que ela destrava.
4. **Os prompts**, inteiros, cada um com o cabeçalho de leitura em cima do bloco.
5. **Passo a passo:**
   1. Abrir os terminais (até `--max-sessoes`) e colar um prompt em cada.
   2. Aprovar os drafts de vídeo conforme chegarem: é o gate que segura cada PR.
   3. Mergear um módulo por vez, conferindo o CI do workflow `Manual` de cada PR.
   4. **Depois de todos os merges**, publicar uma vez: `/manual publicar`.
   5. Rodar o inventário de novo. O módulo entregue fecha em zero lacunas; é esse o critério de pronto.

## O que esta skill não faz

- Não escreve página, não tira print, não renderiza vídeo e não publica: quem produz é a `/manual` em cada terminal, e quem publica é o humano, uma vez, no fim.
- Não abre nem tria issue: as Fatias de módulo já nascem do `/to-issues`. Se um módulo não tem fatia, o plano diz isso e o prompt começa direto na `/manual <modulo>`.
- Não mergeia, não faz deploy e não roda `/onda`.
- Não planeja a aba Tecnologia (fora do manual, ADR 0057, decisão 1).
