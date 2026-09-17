# Fluxogramas de caminho: as cinco Visões gerais e o Como funciona com estados

**Até 10 fluxogramas, um terminal.** Roda em paralelo com os três de prints (08),
**depois** do 07 mergeado (é o 07 que cria o gerador). Não toca Página de
tarefa: só `index.md` e `como-funciona/` de cada módulo, que os 08 não tocam.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git. O [README](README.md) diz a ordem de tudo.

```
Produza os Fluxogramas de caminho do Manual do usuário, no repo pedrorezendefig/hospital-reunioes: um desenho por Visão geral de módulo e um por página de Como funciona que descreve estados ou desvios, com as palavras da tela.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal do repositório, /Users/pedrorezende/PedroDev/Hospital, que costuma estar numa branch antiga e é compartilhada com outros terminais abertos AO MESMO TEMPO. Você NÃO trabalha nela. Seu primeiro ato é criar um worktree próprio, a partir de origin/main, e entrar nele:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/fluxogramas -b docs/fluxogramas origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/fluxogramas
Se a branch ou a pasta já existirem de uma tentativa anterior deste mesmo prompt: veja com `gh pr list --head docs/fluxogramas --state all` se o PR dela já foi mergeado ou fechado. Se foi, remova os restos (git -C /Users/pedrorezende/PedroDev/Hospital worktree remove --force /Users/pedrorezende/PedroDev/Hospital/.worktrees/fluxogramas; git -C /Users/pedrorezende/PedroDev/Hospital branch -D docs/fluxogramas) e crie de novo. Se o PR ainda estiver aberto, PARE e reporte: alguém pode estar trabalhando nela.

A pasta de trabalho persiste entre os seus comandos, mas confira antes de cada commit:
  git branch --show-current      (tem que devolver docs/fluxogramas)
  git rev-parse --show-toplevel  (tem que devolver /Users/pedrorezende/PedroDev/Hospital/.worktrees/fluxogramas, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca edite arquivo fora do worktree, nunca toque na árvore principal. Ao terminar, não remova o worktree: a próxima rodada deste prompt sabe lidar com ele.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho dentro dele é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..
Depois confira que o gerador existe (ele veio do prompt 07; se não existir, PARE e reporte):
  ls docs/manual/scripts/gerar-fluxogramas.mjs docs/manual/fluxogramas/tema.json

LEIA PRIMEIRO, NESTA ORDEM
1. docs/adr/0057-*.md, a emenda de 17/09/2026, decisão 13: onde o fluxograma entra e onde não entra.
2. CONTEXT.md inteiro: é o glossário, e cada caixa do desenho usa a palavra dele ou a palavra da tela. A seção "Manual do usuário" tem o termo Fluxograma de caminho.
3. docs/manual/scripts/gerar-fluxogramas.mjs e docs/manual/fluxogramas/tema.json: como gerar e com que cores.
4. docs/spec/snapshots/FLUXOGRAMAS.md e ROTAS.md (LEITURA APENAS): os estados e as transições reais do app, gerados do código. É daqui que sai a verdade do desenho, não da sua memória.
5. As páginas que você vai ilustrar (lista abaixo), inteiras, antes de desenhar cada uma.

QUAL É O TRABALHO
Cinco obrigatórios, um por Visão geral, ilustrando a seção "O caminho de ponta a ponta" (ou o equivalente) de cada index.md:
  primeiros-passos/index.md   (o caminho do primeiro dia: conta criada, entrar, trocar senha, menu, avisos)
  reunioes/index.md           (o caminho de uma ata: Programada, transcrição ou Ata Guiada, Validação Necessária, os dois desfechos, Assinada ou Aprovada, e as pendências)
  ouvidoria/index.md          (o caminho de um caso: as quatro portas, a Ouvidoria lê e encaminha, o setor responde, a cobrança, o encerramento)
  pops/index.md               (o caminho de uma Versão: A Elaborar, Em Revisão, Em Validação, Em Assinatura, Publicado, e a devolução que volta ao Elaborador)
  admin/index.md              (o caminho de uma pessoa nova: cadastrar, entregar o acesso, conceder POPs ou Ouvidoria, desativar quando sai)

Até cinco em Como funciona, só onde a página descreve estados ou desvios. Candidatas, em ordem de valor; decida você quais valem desenho e diga no PR por que deixou alguma de fora:
  reunioes/como-funciona/quando-a-pendencia-nasce.md          (os quatro momentos e o caminho sem assinatura)
  ouvidoria/como-funciona/quando-o-caso-sai-do-caminho-reto.md (os seis desvios saindo do caminho reto)
  ouvidoria/como-funciona/quando-ninguem-responde.md           (a escada de cobrança, degrau a degrau)
  pops/como-funciona/da-assinatura-a-biblioteca.md            (validação, envio automático, as três assinaturas, Publicado)
  ouvidoria/como-funciona/como-o-prazo-e-contado.md           (só se um desenho de linha do tempo explicar melhor que o exemplo da sexta às 16h50; se não, deixe de fora)

Nunca em Página de tarefa (as que têm `papel`): a tarefa é linear, e o print de passo cobre.

COMO DESENHAR
- Fonte em docs/manual/fluxogramas/<modulo>/<slug>.mmd, um flowchart Mermaid (`flowchart TD` ou `LR`, o que couber melhor no celular: teste os dois no SVG gerado). O slug é o da página (`index` vira `caminho`: fluxo-caminho.svg).
- Caixa = estado ou passo com a PALAVRA DA TELA ou do glossário (Programada, Validação Necessária, Em Revisão, Aguardando o setor). Seta = quem faz ou o que dispara, em duas ou três palavras ("Facilitador aprova", "prazo vence"). Losango só para decisão real que a pessoa toma ("Enviar para assinatura?").
- Teto de 10 caixas por desenho. Passou disso, o desenho está contando duas histórias: corte para a principal e deixe o desvio para a página de Como funciona.
- Gere com `node docs/manual/scripts/gerar-fluxogramas.mjs` e OLHE cada SVG (abra com Read): texto legível, nada cortado, nada sobreposto, cores do app. Confira também no `pnpm dev` com o Chrome headless em 390 px de largura:
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --virtual-time-budget=20000 --screenshot=/tmp/fluxo.png --window-size=390,1600 http://localhost:4321/<modulo>/
  Desenho ilegível no celular é desenho errado: troque TD por LR ou corte caixas.
- A página aponta para o SVG como aponta para um print: `![<o que o desenho mostra, até 10 palavras>](../../../assets/<modulo>/fluxo-<slug>.svg)` (um nível a mais de `../` dentro de como-funciona/), logo abaixo do título da seção que ele ilustra. A lista numerada que já existe continua: o desenho é a visão, a lista é a leitura.
- Nada de travessão nem meia-risca nos rótulos: o CI varre. Nada de jargão da lista do lint.

FIDELIDADE
Cada seta é uma transição que o app faz. Confira em docs/spec/snapshots/FLUXOGRAMAS.md e, na dúvida, no código (hospital-reunioes/, LEITURA APENAS). Se a página que você ilustra descrever um caminho que o snapshot desmente, PARE nessa página, reporte, e siga com as outras. Não corrija o texto.

O QUE NÃO FAZER
- Não toque em Página de tarefa (arquivo com `papel` no frontmatter), nem em novidades.md: os terminais de prints (08) estão nelas agora.
- Não mexa no texto das páginas além de inserir a linha da imagem. O prompt 06 é quem enxuga.
- Não toque em docs/manual/scripts/, src/components/, src/styles/, astro.config.mjs, publicar.sh, .github/, tools/. Se o gerador tiver um defeito que impeça o trabalho, reporte com o diff proposto e pare.
- Não edite hospital-reunioes/.
- NÃO PUBLIQUE e não mergeie.

ANTES DO PR, TODOS EM 0
node docs/manual/scripts/gerar-fluxogramas.mjs      (regera tudo; o SVG commitado é o que o gerador produz, sem edição à mão)
git status --short docs/manual/src/assets/           (depois de regerar, nenhum SVG pode mudar: se mudar, você editou à mão)
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): fluxogramas de caminho nas visoes gerais e no como funciona" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/fluxogramas é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/fluxogramas.

REPORTE NO FIM
A lista dos desenhos (página, caixas, TD ou LR), os screenshots em 390 px de cada página ilustrada, quais candidatas de Como funciona ficaram de fora e por quê, e qualquer caminho de página que o snapshot desmentiu.
```
