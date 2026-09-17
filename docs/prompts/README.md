# Prompts para colar

Prompts prontos para colar num terminal do Claude Code, um por sessão. Cada
arquivo tem o prompt inteiro num bloco de código: copie o bloco, cole e mande.

Não é doc de estado nem de processo. Aqui não se registra quem fez o quê, nem
quando: isso vive nas GitHub Issues e em `docs/spec/deploy/*.json`. Aqui mora só
a **instrução**, para não ser reescrita do zero toda vez.

## Os vídeos do Manual do usuário

O Manual está no ar em <https://manual-hsm.vercel.app> com 86 páginas e as cinco
seções escritas. O que falta são os **Vídeos de tarefa**: das 57 Páginas de
tarefa, 48 publicam com o aviso "Vídeo em produção".

| Arquivo | Módulos | Vídeos | Quando |
|---|---|---|---|
| [01-videos-reunioes.md](01-videos-reunioes.md) | Reuniões e metas | 11 | Etapa 2, em paralelo |
| [02-videos-pops-e-primeiros-passos.md](02-videos-pops-e-primeiros-passos.md) | POPs, Primeiros passos | 14 | Etapa 2, em paralelo |
| [03-videos-ouvidoria.md](03-videos-ouvidoria.md) | Ouvidoria | 12 | Etapa 2, em paralelo |
| [04-videos-admin.md](04-videos-admin.md) | Admin | 11 | Etapa 2, em paralelo |
| [05-videos-tecnologia.md](05-videos-tecnologia.md) | Tecnologia | a decidir | Fora da campanha |
| [06-enxugar-a-escrita.md](06-enxugar-a-escrita.md) | os cinco | nenhum | Etapa 4, sozinho |

Os quatro de vídeo rodam **em paralelo, um por terminal, cada um no seu
worktree**: cada um mexe só nas pastas do seu módulo e nenhum toca arquivo
compartilhado. A divisão é por esforço, não por contagem: a Ouvidoria já tem
sete composições prontas para reusar e o Admin tem cerca de quatro telas para
onze tarefas. Ouvidoria e Admin são terminais separados porque a auto-revisão de
frames olha imagem por imagem, e 23 vídeos numa sessão só estouram o contexto.

O 06 roda **depois** dos quatro mergeados, porque mexe no texto das mesmas
páginas. O 05 não faz parte da campanha: é uma decisão sua, explicada no arquivo.

## O passo a passo, do começo até o site no ar

### Etapa 0: uma vez só, antes de abrir qualquer terminal

1. Atualize a referência da main. A árvore principal costuma estar numa branch
   antiga; não precisa trocar de branch, só buscar:
   ```bash
   cd /Users/pedrorezende/PedroDev/Hospital && git fetch origin
   ```
2. Confira que os 9 vídeos que já existem estão nos masters, com a pasta por
   módulo (é de lá que a publicação vai tirar todos, os velhos e os novos):
   ```bash
   ls local/manual-video-masters/ouvidoria/ local/manual-video-masters/primeiros-passos/
   ```
   Esperado: `cap-1.mp4` a `cap-7.mp4` e `registrar-manifestacao-pelo-formulario.mp4`
   em `ouvidoria/`, `entrar-na-plataforma.mp4` em `primeiros-passos/`.
3. Confira que ffmpeg e o Node do manual estão na máquina (`ffmpeg -version`,
   `corepack pnpm@9 --version`). O `/setup-maquina` faz isso por você.

### Etapa 1: um worktree por terminal

Cada prompt trabalha numa cópia própria do repositório, numa branch própria.
Sem isso os quatro `/ship` trocariam a branch um do outro na mesma árvore. A
pasta `.worktrees/` fica dentro do repositório, ignorada pelo git, e sobrevive a
reinício da máquina (o `/tmp` não, e a campanha atravessa dias). Crie os quatro
de uma vez, da raiz do repositório:

```bash
cd /Users/pedrorezende/PedroDev/Hospital
git worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-reunioes -b docs/videos-reunioes origin/main
git worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-pops-e-primeiros-passos -b docs/videos-pops-e-primeiros-passos origin/main
git worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria -b docs/videos-ouvidoria origin/main
git worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-admin -b docs/videos-admin origin/main
```

O nome da branch é o que o prompt confere na primeira linha de trabalho, então
não troque. Se uma branch já existir de uma tentativa anterior, apague antes
(`git branch -D <branch>`) ou o `worktree add` recusa.

### Etapa 2: quatro terminais, um prompt em cada

Para cada um dos quatro, abra um terminal **dentro do worktree** e suba o
Claude Code ali:

```bash
cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-reunioes && claude
```

Cole o bloco do prompt correspondente (`01` em `videos-reunioes`, `02` em
`videos-pops-e-primeiros-passos`, `03` em `videos-ouvidoria`, `04` em
`videos-admin`) e mande. Pode abrir os quatro em sequência sem esperar: eles
não se tocam.

O que cada sessão faz sozinha: instala o node_modules do manual no worktree,
desenha as réplicas, monta e renderiza os vídeos um a um, olha os frames de
cada um, copia o MP4 final para `local/manual-video-masters/<modulo>/`, roda os
cinco gates, abre o PR com `/ship --no-merge` e para. Nenhuma publica, nenhuma
mergeia.

Duas coisas que a sessão vai perguntar e a resposta é sim: confirmar que está
numa branch que não é a main (é de propósito), e permissões de comando que o
seu modo exigir.

Se uma sessão parar dizendo que uma página afirma algo que o código não faz,
ela está certa em parar: corrija a página noutra sessão (ou anote para o 06) e
mande a sessão seguir com os outros vídeos.

### Etapa 3: revisar e mergear os quatro PRs

Quando os quatro reportarem, revise os vídeos. O MP4 de cada um está em
`local/manual-video-masters/<modulo>/<slug>.mp4` (abra no Finder ou no
QuickTime). O relatório final de cada sessão diz o que a auto-revisão de frames
pegou e corrigiu, e é o gate 3 que você dispensou no draft.

Aprovou? Mergeie os quatro na ordem que quiser, pelo GitHub ou por:
```bash
gh pr merge <N> --squash --delete-branch
```
Eles não conflitam: cada um só adiciona pastas em `docs/manual/video/<modulo>/`
e muda o frontmatter das páginas do seu módulo.

Depois do merge, feche os quatro terminais e apague os worktrees:
```bash
cd /Users/pedrorezende/PedroDev/Hospital
git worktree remove /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-reunioes
git worktree remove /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-pops-e-primeiros-passos
git worktree remove /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-ouvidoria
git worktree remove /Users/pedrorezende/PedroDev/Hospital/.worktrees/videos-admin
git fetch origin --prune
```
Os MP4 que estavam no `public/video/` de cada worktree somem junto: é por isso
que a cópia em `local/manual-video-masters/` é obrigatória no prompt.

### Etapa 4: o 06, sozinho, num worktree

Só depois dos quatro mergeados:
```bash
cd /Users/pedrorezende/PedroDev/Hospital && git fetch origin
git worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/enxugar-a-escrita -b docs/enxugar-a-escrita origin/main
cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/enxugar-a-escrita && claude
```
Cole o bloco do `06`. Ele não gera vídeo: enxuga o texto das 86 páginas e abre
um PR. Revise o diff (é texto, dá para ler no GitHub), mergeie e remova o
worktree como na etapa 3.

### Etapa 5: publicar, uma vez, de uma sessão só

Nenhuma sessão da campanha publica. N terminais rodando `publicar.sh` geram N
deploys do mesmo site e o último apaga o trabalho dos outros. A publicação é
um passo só, da árvore principal, com todos os PRs mergeados.

1. Ponha a árvore principal na main atualizada:
   ```bash
   cd /Users/pedrorezende/PedroDev/Hospital && git checkout main && git pull origin main
   ```
2. Traga os MP4 dos masters para onde o `publicar.sh` monta o site. Ele monta de
   `dist/`, que vem de `public/`, e `public/video/` é gitignorado, então esse
   passo é obrigatório e cobre os 9 velhos e os 48 novos:
   ```bash
   for m in reunioes pops primeiros-passos ouvidoria admin; do
     mkdir -p docs/manual/public/video/$m
     cp local/manual-video-masters/$m/*.mp4 docs/manual/public/video/$m/
   done
   ```
3. Confira antes de subir: o inventário tem que dar zero lacunas "sem-video" e
   o conferidor tem que passar:
   ```bash
   python3 tools/inventario_manual.py --dir docs/manual | tail -3
   python3 tools/checar_video_manual.py --dir docs/manual
   ```
4. Publique:
   ```bash
   bash docs/manual/publicar.sh
   ```
   Página publicada que exibe vídeo sem o arquivo trava a publicação de
   propósito: se travar, faltou MP4 no passo 2.
5. Abra <https://manual-hsm.vercel.app>, entre numa página de cada módulo e
   confira que o vídeo toca e o carimbo do fecho traz a versão certa.

## O que decide o custo

**A réplica de tela, não o vídeo.** Cada vídeo é uma composição HyperFrames que
redesenha a tela do app, fiel ao `globals.css` do frontend. O render é barato;
desenhar a tela é o trabalho. Várias tarefas do mesmo módulo acontecem na mesma
tela, então a ordem certa é desenhar a biblioteca de réplicas primeiro e montar
os vídeos reusando.

## A exceção que o Pedro autorizou

A receita em `.claude/skills/manual/references/video-de-tarefa.md` tem, como
gate 3, o **OK humano no draft** antes do render final. Para esta campanha isso
foi dispensado: os agentes renderizam direto em qualidade final e o Pedro revisa
o conjunto depois, na etapa 3, antes do merge.

Em troca, **a auto-revisão de frames vira a única barreira antes do ar**, e por
isso ela aparece reforçada em todos os prompts. Não é formalidade: foi ela que
pegou o único defeito real de vídeo da sessão que escreveu o manual, um marcador
apontando um campo acima do certo, com o `check` do HyperFrames passando nas
duas versões.

Se essa exceção virar a regra, a skill precisa ser atualizada, senão a próxima
sessão vai parar esperando um OK que ninguém vai dar.

## O carimbo e a versão

Todo vídeo leva no carimbo a versão do app que produção servia quando ele foi
gerado. Os prompts mandam a sessão ler essa versão do `/health` de produção na
hora, em vez de copiar um número: a campanha atravessa deploys e um número fixo
no prompt envelhece em dias.
