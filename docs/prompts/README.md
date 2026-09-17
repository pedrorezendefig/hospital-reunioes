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
| [06-enxugar-a-escrita.md](06-enxugar-a-escrita.md) | os cinco | nenhum | Por último, sozinho (Etapa C da segunda campanha) |
| [07-tema-didatico.md](07-tema-didatico.md) | o site (tema, capa, gerador de fluxograma, lint) | nenhum | Segunda campanha, Etapa A, sozinho |
| [08-prints-reunioes.md](08-prints-reunioes.md) | Reuniões e metas | 11 páginas com print | Etapa B, em paralelo |
| [08-prints-pops-e-primeiros-passos.md](08-prints-pops-e-primeiros-passos.md) | POPs, Primeiros passos | 15 páginas com print | Etapa B, em paralelo |
| [08-prints-ouvidoria-e-admin.md](08-prints-ouvidoria-e-admin.md) | Ouvidoria, Admin | 31 páginas com print | Etapa B, em paralelo |
| [09-fluxogramas.md](09-fluxogramas.md) | os cinco (Visão geral e Como funciona) | até 10 fluxogramas | Etapa B, em paralelo |
| [10-publicar.md](10-publicar.md) | o site inteiro | nenhum | Etapa 5, sozinho, por último, na árvore principal |

Os quatro de vídeo rodam **em paralelo, um por terminal, cada um no seu
worktree**: cada um mexe só nas pastas do seu módulo e nenhum toca arquivo
compartilhado. A divisão é por esforço, não por contagem: a Ouvidoria já tem
sete composições prontas para reusar e o Admin tem cerca de quatro telas para
onze tarefas. Ouvidoria e Admin são terminais separados porque a auto-revisão de
frames olha imagem por imagem, e 23 vídeos numa sessão só estouram o contexto.

O 06 roda **por último**, depois de tudo mergeado, porque mexe no texto das
mesmas páginas. O 05 não faz parte da campanha: é uma decisão sua, explicada no
arquivo. Os prompts 07 a 09 são a **segunda campanha**, a camada didática
(print de passo com balão, fluxograma, aviso, capa), descrita mais abaixo.

## O passo a passo, do começo até o site no ar

Você não roda git. Cada prompt manda a sessão criar o próprio worktree em
`.worktrees/<nome>` a partir de `origin/main`, entrar nele e conferir a
branch antes de cada commit. O que sobra para você é abrir terminais, colar,
revisar PRs e mergear.

**Como abrir uma sessão, sempre igual:**

```bash
cd /Users/pedrorezende/PedroDev/Hospital && claude
```

Cole o bloco do prompt e mande. A sessão vai perguntar duas coisas e a
resposta é sim: confirmar que a branch não é a main (é de propósito) e as
permissões de comando que o seu modo exigir. Ela termina abrindo um PR com
`/ship --no-merge` e para. Nenhuma publica, nenhuma mergeia.

### Etapa 0: uma vez só, antes de qualquer terminal

Confira que ffmpeg e o Node do manual estão na máquina (`ffmpeg -version`,
`corepack pnpm@9 --version`); o `/setup-maquina` faz isso por você. Os 9
vídeos que já existem têm que estar em `local/manual-video-masters/` (pasta
por módulo): `ouvidoria/cap-1.mp4` a `cap-7.mp4`,
`ouvidoria/registrar-manifestacao-pelo-formulario.mp4` e
`primeiros-passos/entrar-na-plataforma.mp4`.

### Etapa 1: quatro terminais, um prompt de vídeo em cada

Abra quatro terminais na raiz do repositório e cole `01` no primeiro, `02` no
segundo, `03` no terceiro e `04` no quarto. Pode abrir os quatro em sequência
sem esperar: eles não se tocam. Cada um cria o seu worktree, instala o
node_modules do manual, desenha as réplicas, renderiza os vídeos um a um,
olha os frames, copia o MP4 final para `local/manual-video-masters/<modulo>/`
e abre o PR.

Se uma sessão parar dizendo que uma página afirma algo que o código não faz,
ela está certa em parar: anote para o 06 e mande a sessão seguir com os
outros vídeos.

### Etapa 2: revisar e mergear os quatro PRs

O MP4 de cada vídeo está em `local/manual-video-masters/<modulo>/<slug>.mp4`
(abra no Finder ou no QuickTime). O relatório de cada sessão diz o que a
auto-revisão de frames pegou e corrigiu: é o gate 3 que você dispensou no
draft.

Aprovou? Mergeie os quatro na ordem que quiser, pelo GitHub ou por
`gh pr merge <N> --squash --delete-branch`. Eles não conflitam. Feche os
terminais. Os worktrees em `.worktrees/` podem ficar: a próxima rodada de
cada prompt sabe limpar os restos do anterior, e você limpa tudo de uma vez
quando quiser com `git worktree prune` depois de apagar as pastas.

### Etapa 3: a segunda campanha (07, depois 08 e 09)

Está descrita na seção seguinte, com a mesma mecânica: terminal na raiz,
colar, revisar, mergear.

### Etapa 4: o 06, sozinho, por último

Só depois de tudo mergeado. Um terminal na raiz, cole o `06`. Ele não gera
vídeo: enxuga o texto das 86 páginas e abre um PR. Revise o diff (é texto, dá
para ler no GitHub) e mergeie.

### Etapa 5: publicar, uma vez, de uma sessão só

Nenhuma sessão da campanha publica: N terminais rodando `publicar.sh` geram N
deploys do mesmo site e o último apaga o trabalho dos outros. A publicação é
um passo só, com todos os PRs mergeados, e também é um prompt: um terminal
na raiz, cole o [10-publicar.md](10-publicar.md). Ele põe a árvore principal
na main, traz os MP4 dos masters, confere o inventário e o conferidor de
vídeo, publica e abre uma página de cada módulo para conferir. É o único
prompt que mexe na árvore principal, por isso roda sozinho e por último.

## A segunda campanha: a camada didática

Decisão de 17/09/2026 (emenda ao ADR 0057): o Manual tinha o molde certo e o
texto já humano, mas 39 das 57 Páginas de tarefa não tinham nenhuma imagem e
nenhuma página tinha fluxograma. Quem lê no celular, sem som, não dá play: olha
a figura. A segunda campanha põe **um print por mudança de tela, com balão
numerado igual ao passo**, em toda Página de tarefa; um **fluxograma de
caminho** em cada Visão geral e no Como funciona que descreve estados; um
**aviso destacado** onde a ação não tem volta; e a **capa** do vídeo.

O que cada prompt toca, para os paralelos não colidirem:

| Prompt | Toca | Não toca |
|---|---|---|
| 07 | tema, componente da página, `publicar.sh`, lint, gerador de fluxograma | qualquer página |
| 08 (x3) | Páginas de tarefa do seu módulo (corpo), `prints/<modulo>.py`, `src/assets/<modulo>/` | frontmatter, `index.md`, `como-funciona/`, `novidades.md` |
| 09 | `index.md` e `como-funciona/` dos cinco, `fluxogramas/`, `src/assets/*/fluxo-*.svg` | Páginas de tarefa |
| 06 | texto de todas | imagens, callouts, frontmatter |

### Etapa A: o 07, sozinho

Pode rodar enquanto os quatro de vídeo (01 a 04) ainda estão abertos: nenhum
deles toca tema, componente, `publicar.sh` ou `tools/`. Não pode rodar junto
com 08, 09 ou 06. Um terminal na raiz, cole o `07`. Revise o PR (dois
screenshots e um SVG de prova vêm no relatório) e mergeie.

### Etapa B: três de prints e o de fluxogramas, em paralelo

**Só depois** do 07 e dos quatro de vídeo mergeados (os 08 inserem imagem nas
mesmas páginas em que os vídeos preencheram o frontmatter; com os dois
mergeados antes, ninguém pisa em ninguém).

Quatro terminais na raiz: cole `08-prints-reunioes` no primeiro,
`08-prints-pops-e-primeiros-passos` no segundo, `08-prints-ouvidoria-e-admin`
no terceiro e `09-fluxogramas` no quarto. Os três de prints capturam contra o
mesmo app local: o primeiro que achar o app fora do ar sobe a stack (Supabase
local e `apply.sh`) e os outros esperam por uma trava em `/tmp`; ninguém
reinicia o que já está no ar. Cada um semeia os dados de exemplo do seu
módulo no mesmo banco, sem apagar os dos outros. O de Reuniões é o mais caro:
o roteiro dele nasce do zero.

Revise os quatro PRs (as imagens aparecem no diff do GitHub) e mergeie na ordem
que quiser. Se dois PRs conflitarem, é porque um deles
tocou arquivo que não era dele: o relatório de cada um diz o que tocou.

### Etapa C: o 06, sozinho, por último

Igual à Etapa 4 acima. Ele ganhou os três cacoetes que a leitura das 86
páginas encontrou e a instrução de não mexer nas imagens e nos callouts.

### Etapa D: publicar

Igual à Etapa 5 acima: cole o `10`. O `publicar.sh` passou a gerar a capa de cada vídeo
junto do reencode; o passo 2 (trazer os MP4 dos masters) continua obrigatório.

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
