# Enxugar a escrita do Manual

**Depois dos três primeiros**, nunca em paralelo: este mexe no texto das mesmas
páginas que os outros estão ilustrando.

Nenhum vídeo, nenhuma página nova. É a passada de qualidade na escrita das 86
páginas, para o Manual ficar enxuto e soar como uma voz só.

Copie o bloco inteiro e cole num terminal do Claude Code, na raiz do repositório.

```
Enxugue a escrita do Manual do usuário do repo pedrorezendefig/hospital-reunioes. São 86 páginas em docs/manual/src/content/docs/, escritas por quatro sessões diferentes em paralelo. O trabalho é fazer soarem como uma voz só, sem perder informação.

NÃO É PARA REESCREVER. O conteúdo foi conferido contra o código, revisado em até três rodadas por página e auditado contra o site publicado. Toda afirmação que está lá foi verificada. Você está cortando gordura e alinhando voz, não repensando o que a página diz. Se achar que uma afirmação está errada, PARE e reporte em vez de corrigir: mudar fato exige conferir no código, e isso é outro trabalho.

LEIA PRIMEIRO
1. .claude/skills/manual/SKILL.md e as references, principalmente o molde da Página de tarefa.
2. docs/adr/0057-*.md.
3. CONTEXT.md, que é o glossário: os termos do produto vêm dele.
4. A skill /humanizer, que é a receita de tirar o som de texto gerado.

O QUE PROCURAR, em ordem de valor

1. VOZ DESIGUAL ENTRE SEÇÕES. Quatro autores, quatro ritmos. Escolha o melhor e alinhe os outros. As seções Ouvidoria e POPs passaram por mais rodadas e são a referência de tom.

2. APELIDOS DIFERENTES PARA A MESMA COISA. Já sabidos: o selo "Todo mundo" em Primeiros passos e "Qualquer pessoa" no formulário público; e o vídeo de percepção 272 chama de "tarefa" o que as páginas chamam de Pendência. Varra por mais. O glossário decide qual vence, e onde o glossário não decidir, escolha um e aplique nas 86.

3. GORDURA. Frase que repete o que a anterior disse, "Quando usar" que parafraseia o título, passo que descreve o óbvio da tela, ressalva que já está no "Se der errado". O teto do lint é 250 palavras por página e três já passam dele por bom motivo (carregam avisos que valem mais que o número): não corte aviso para caber no teto.

4. SOM DE TEXTO GERADO. Contraste "não é X, mas Y", fecho de uma linha resumindo o que acabou de ser dito, tríade forçada, abertura encenada, palavra inflada. A /humanizer tem a lista.

5. TÍTULO NO INFINITIVO nas Páginas de tarefa, e o mesmo título na página, na sidebar e no vídeo que a ilustra.

O QUE NÃO TOCAR
- Frontmatter: título, descrição, selos de papel, `video`, `draft`, `sidebar.order`. Mexer ali muda estrutura, não escrita.
- As entradas de Novidades: as datas foram lidas do CHANGELOG uma a uma e os números de PRD conferidos.
- Os rótulos de tela reproduzidos do app, mesmo os feios. "Concluido" sem acento no badge de Pendências e "Area" em /perfil estão assim NA TELA: o manual reproduz para a pessoa achar o que está vendo. Não "conserte".
- Os avisos de limite (o que o app não faz, o cadastro sem efeito, a tela sem botão). Eles custaram rodadas de revisão para nascer certos.
- hospital-reunioes/, tools/, astro.config.mjs, manual.yml, publicar.sh, rotulos-da-sidebar.ts.
- Os vídeos e as composições.

TIPOGRAFIA
Travessão (U+2014) e meia-risca (U+2013) são proibidos em tudo que o usuário vê. O CI varre a pasta inteira. Use vírgula, dois-pontos, parênteses ou ponto.

COMO TRABALHAR
Seção por seção, commitando por seção, para o diff ser legível. Ao terminar cada uma, releia as páginas vizinhas: o risco desta tarefa é criar contradição nova ao uniformizar duas frases que diziam coisas diferentes DE PROPÓSITO.

Depois de cada seção, confira os links internos contra o dist: enxugar texto quebra link quando o texto do link some.

ANTES DO PR, TODOS EM 0
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): enxugar a escrita e alinhar a voz das cinco secoes" --no-merge --skip-review

NÃO PUBLIQUE e não mergeie. Todo comentário em PR começa com <!-- automacao --> na primeira linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo alheio. Confira `git branch --show-current` antes de cada commit.

REPORTE NO FIM
Quantas palavras saíram por seção, quais apelidos você unificou e qual venceu, o que você quis mudar e não mudou por ser fato e não escrita, e qualquer contradição que apareceu ao uniformizar.
```
