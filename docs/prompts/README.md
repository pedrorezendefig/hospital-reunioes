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

| Arquivo | Módulos | Vídeos |
|---|---|---|
| [01-videos-reunioes.md](01-videos-reunioes.md) | Reuniões e metas | 11 |
| [02-videos-pops-e-primeiros-passos.md](02-videos-pops-e-primeiros-passos.md) | POPs, Primeiros passos | 14 |
| [03-videos-ouvidoria-e-admin.md](03-videos-ouvidoria-e-admin.md) | Ouvidoria, Admin | 23 |
| [04-videos-tecnologia.md](04-videos-tecnologia.md) | Tecnologia | a decidir |
| [05-enxugar-a-escrita.md](05-enxugar-a-escrita.md) | os cinco | nenhum |

Os três primeiros rodam **em paralelo**, um por terminal: cada um mexe só nas
pastas do seu módulo e nenhum toca arquivo compartilhado. A divisão é por
esforço, não por contagem: o 03 tem mais vídeos e é o mais barato, porque a
Ouvidoria já tem sete composições prontas para reusar e o Admin tem cerca de
quatro telas para onze tarefas.

O 05 roda **depois** dos três, porque mexe no texto das mesmas páginas.

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
o conjunto depois de publicado.

Em troca, **a auto-revisão de frames vira a única barreira antes do ar**, e por
isso ela aparece reforçada em todos os prompts. Não é formalidade: foi ela que
pegou o único defeito real de vídeo da sessão que escreveu o manual, um marcador
apontando um campo acima do certo, com o `check` do HyperFrames passando nas
duas versões.

Se essa exceção virar a regra, a skill precisa ser atualizada, senão a próxima
sessão vai parar esperando um OK que ninguém vai dar.

## A publicação é um passo só, no fim

Nenhuma sessão publica. N terminais rodando `publicar.sh` geram N deploys do
mesmo site e o último apaga o trabalho dos outros. Quando os PRs estiverem
mergeados, uma sessão só roda `bash docs/manual/publicar.sh`.

E antes de publicar, **os MP4 precisam estar na árvore de onde se publica**: o
`publicar.sh` monta de `dist/`, que vem de `public/`. Por isso todo prompt manda
copiar o MP4 final para `local/manual-video-masters/<modulo>/`, que fica fora do
git e é a cópia durável.
