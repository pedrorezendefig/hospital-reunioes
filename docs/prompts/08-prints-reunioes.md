# Prints de passo: Reuniões e metas

**11 Páginas de tarefa.** O único módulo que **não tem roteiro de prints**: `docs/manual/prints/reunioes.py` nasce aqui, e é o terminal mais caro dos três, porque as telas exigem reunião, ata e pendência de exemplo no banco local.

Roda em paralelo com os outros dois de prints e com o 09, **depois** do 07 mergeado
e dos quatro de vídeo mergeados. Cada um no seu worktree, todos contra o mesmo
app local: o README diz o que subir antes.

Copie o bloco inteiro e cole num terminal do Claude Code aberto na raiz do repositório (`/Users/pedrorezende/PedroDev/Hospital`). A sessão cria o worktree sozinha; você não roda git. O [README](README.md) diz a ordem de tudo.

```
Produza os Prints de passo das Páginas de tarefa da seção "Reuniões e metas" do Manual do usuário, no repo pedrorezendefig/hospital-reunioes: em toda Página de tarefa, um print por mudança de tela, com balão numerado igual ao passo, tirado pelo Roteiro de prints do módulo.

ONDE VOCÊ ESTÁ E ONDE VAI TRABALHAR
Você foi aberto na árvore principal do repositório, /Users/pedrorezende/PedroDev/Hospital, que costuma estar numa branch antiga e é compartilhada com outros terminais abertos AO MESMO TEMPO. Você NÃO trabalha nela. Seu primeiro ato é criar um worktree próprio, a partir de origin/main, e entrar nele:
  git -C /Users/pedrorezende/PedroDev/Hospital fetch origin --prune
  git -C /Users/pedrorezende/PedroDev/Hospital worktree add /Users/pedrorezende/PedroDev/Hospital/.worktrees/prints-reunioes -b docs/prints-reunioes origin/main
  cd /Users/pedrorezende/PedroDev/Hospital/.worktrees/prints-reunioes
Se a branch ou a pasta já existirem de uma tentativa anterior deste mesmo prompt: veja com `gh pr list --head docs/prints-reunioes --state all` se o PR dela já foi mergeado ou fechado. Se foi, remova os restos (git -C /Users/pedrorezende/PedroDev/Hospital worktree remove --force /Users/pedrorezende/PedroDev/Hospital/.worktrees/prints-reunioes; git -C /Users/pedrorezende/PedroDev/Hospital branch -D docs/prints-reunioes) e crie de novo. Se o PR ainda estiver aberto, PARE e reporte: alguém pode estar trabalhando nela.

A pasta de trabalho persiste entre os seus comandos, mas confira antes de cada commit:
  git branch --show-current      (tem que devolver docs/prints-reunioes)
  git rev-parse --show-toplevel  (tem que devolver /Users/pedrorezende/PedroDev/Hospital/.worktrees/prints-reunioes, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca edite arquivo fora do worktree, nunca toque na árvore principal. Ao terminar, não remova o worktree: a próxima rodada deste prompt sabe lidar com ele.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho dentro dele é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..
O worktree também nasce sem o .env local do app, que é gitignorado e mora na árvore principal. Copie (é leitura da árvore principal, não edição):
  cp /Users/pedrorezende/PedroDev/Hospital/hospital-reunioes/.env hospital-reunioes/.env
Depois confira que o app local responde:
  curl -s http://localhost:3000 -o /dev/null -w "%{http_code}\n"
Se responder 200, NÃO toque na stack: ela é compartilhada com os outros terminais, e reiniciar derruba o roteiro deles no meio. Se NÃO responder, quem sobe é o primeiro terminal que pegar a trava, e só ele:
  mkdir /tmp/hospital-app-subindo
Se o mkdir falhar porque a pasta já existe, outro terminal está subindo: espere, testando o curl a cada 30 segundos, até dar 200, e siga sem subir nada. Se o mkdir passou, a trava é sua: rode `(cd /Users/pedrorezende/PedroDev/Hospital/hospital-reunioes && supabase start)` (o banco local é um só, e mora na árvore principal) e depois `bash .claude/skills/atualizar-app/scripts/apply.sh` de dentro do SEU worktree (o script constrói a stack com o código de onde ele está, e o seu worktree é a origin/main atual). Espere o curl dar 200 e remova a trava com `rmdir /tmp/hospital-app-subindo`. Se passar de 15 minutos sem o app subir, reporte em vez de forçar.

LEIA PRIMEIRO, NESTA ORDEM
1. .claude/skills/manual/SKILL.md e references/prints.md: o molde da Página de tarefa (o print fica DENTRO do item da lista, recuado três espaços) e a receita do balão numerado.
2. docs/adr/0057-*.md, a emenda de 17/09/2026 (decisões 4, 13 e 14): print por mudança de tela, aviso destacado no máximo um por página.
3. CONTEXT.md, seção "Manual do usuário": Print de passo, Aviso destacado.
4. docs/manual/prints/admin.py (o molde: dicionário PRINTS, função entrar, guarda de endereço local, viewport COMPUTADOR 1440x900) e docs/manual/prints/ouvidoria.py. O módulo Reuniões NÃO tem roteiro: crie docs/manual/prints/reunioes.py no mesmo molde, com tools/test_prints_reunioes.py no molde de tools/test_prints_admin.py.
5. tools/test_prints_manual.py e tools/test_prints_admin.py: todo print do roteiro passa pela guarda de endereço local, e o roteiro tem teste.

QUAL É O TRABALHO
As Páginas de tarefa estão em docs/manual/src/content/docs/reunioes/ (as 11 páginas com `papel`; index, novidades e como-funciona/ ficam de fora). São 11 tarefas. Para cada uma:
1. Leia os passos e decida quantas telas distintas eles atravessam. Um print por tela, com os balões dos passos que acontecem nela. Passo 1 "No menu, clique em X" e passo 2 "clique em Novo" costumam ser a mesma tela com dois balões; a janela que abre no passo 3 é outro print.
2. Escreva (ou amplie) a função do print no roteiro do módulo, com o helper `balao(page, seletor, numero)` da referência. O balão fica no elemento que o passo cita, pelo texto de tela do botão ou do campo, nunca por posição fixa.
3. Rode o roteiro e OLHE cada imagem gerada (abra com Read): balão em cima do elemento certo, número certo, texto legível, sem anel de foco, sem dado real. Balão em cima do elemento errado é o mesmo defeito do marcador errado no vídeo, e só a olhada pega.
4. Insira o print no Markdown, dentro do item do passo, com texto alternativo curto (até 10 palavras, o que a imagem mostra). Print que já existia na página e continua certo fica; se ele estava solto entre seções, mova para dentro do passo que ilustra e acrescente os balões.
5. Se a página tem uma ação sem volta ou algo que a pessoa precisa saber ANTES de clicar, ponha UM `:::caution[Título curto]` antes do passo que dispara. Um por página no máximo, e só se for irreversível ou custoso. Nem toda página tem: a maioria não tem.

FATOS DO SEU MÓDULO QUE FAZEM PRINT NASCER ERRADO
- O que o roteiro precisa semear, nesta ordem: um Facilitador e uma Secretária de exemplo (o admin cria pela tela de Usuários ou pela API local), uma reunião Programada com participantes, uma reunião em Validação Necessária (exige transcrição processada: se o assistente local não responder, capture a tela de anexar com o arquivo escolhido e reporte), pendências nos estados Pendente, Em Progresso, Concluido, Atrasado e Repactuada (para Lista, Kanban e Dashboard terem o que mostrar).
- A Secretária NÃO vê Pendências, Dashboard nem Ata Guiada: os prints da tela dela (Marcar a reunião de um facilitador) saem logado como a Secretária de exemplo, nunca como admin.
- "Aceitar a ata pelo link" é tela sem login que só nasce quando a assinatura digital é recusada ou cancelada; se não houver como chegar nela pelo app local, capture nada, e diga no PR. Não desenhe a tela.
- O badge da Lista e a coluna do Kanban mostram "Concluido" sem acento; o gráfico do Dashboard mostra "Concluído" com acento. Reproduza cada tela como ela é.
- O Kanban mostra "Solte aqui" só durante o arrasto: o print do Kanban é o quadro parado, com o balão no cartão que o passo manda arrastar.
- Candidatos a Aviso destacado (decida você, um por página no máximo): "Revisar e aprovar a ata" (Finalizar sem assinatura não tem volta) e "Marcar uma reunião no calendário" (a Secretária que marca por aqui vira a facilitadora).

DADOS DE EXEMPLO E O BANCO COMPARTILHADO
- O roteiro cria o que precisa pela própria tela ou pela API local, com nomes fictícios e verossímeis do hospital (setores como CME, Farmácia, UTI; pessoas que não existem; e-mails @exemplo.local). Nunca dado real: o repositório e o site são públicos, e numa onda anterior cinco prints e três vídeos foram ao ar com e-mail e telefone de terceiro.
- O roteiro é idempotente: rodar duas vezes acha o que criou na primeira em vez de duplicar.
- Não apague nem edite registro que você não criou: outro terminal pode estar capturando em cima dele. Não reset no banco.
- Login de dentro do app: admin@hospital.com com a senha do DEFAULT_USER_PASSWORD do hospital-reunioes/.env LOCAL, como o roteiro do Admin já faz (função entrar). Nunca credencial de produção.
- Tela que só nasce de e-mail, de assinatura externa ou de chamada a serviço de fora (link de aceite que chega por e-mail, documento assinado, resposta do assistente): capture o estado imediatamente anterior que a tela mostra de verdade (campo preenchido, botão pronto) e diga no PR o que ficou sem print e por quê. Não invente tela.

FIDELIDADE
O print mostra o que o app faz. Se ao capturar você descobrir que a página afirma algo que a tela não faz (botão com outro nome, passo que não existe, campo que sumiu), PARE nessa página, reporte no fim, e siga com as outras. Não corrija a afirmação: mudar fato é outro trabalho (o prompt 06 e o Pedro). Rótulo feio da tela ("Concluido" sem acento) é reproduzido como está.

O QUE NÃO FAZER
- Não toque em página de módulo que não seja o seu, nem em index.md, novidades.md ou como-funciona/ do seu módulo (esses são do prompt 09 e do 06).
- Não mexa no frontmatter das páginas (título, papel, video, draft, order): o campo `video` pode ter acabado de ser preenchido pela campanha de vídeos.
- Não reescreva os passos. Você insere imagem e, quando couber, um aviso. Ajuste de uma palavra no passo só se o balão exigir citar o nome exato do elemento e a página citava outro: nesse caso reporte.
- Não toque em docs/manual/astro.config.mjs, src/components/, src/styles/, publicar.sh, .github/, tools/*.py (exceto criar/ampliar o teste do SEU roteiro, tools/test_prints_reunioes.py).
- Não edite hospital-reunioes/. Ler é obrigatório para achar seletor e rótulo; editar é proibido.
- NÃO PUBLIQUE e não mergeie.

TIPOGRAFIA E JARGÃO
Travessão (U+2014) e meia-risca (U+2013) são proibidos em texto alternativo, em rótulo de callout e em qualquer texto que apareça na tela. Jargão da lista do lint (endpoint, API, deploy, backend...) também.

ANTES DO PR, TODOS EM 0
python3 docs/manual/prints/<modulo>.py    (roda de ponta a ponta, para cada módulo seu)
python3 tools/lint_manual.py --dir docs/manual/src/content/docs
python3 tools/inventario_manual.py --dir docs/manual   (zero lacunas print-faltando no seu módulo)
python3 tools/checar_video_manual.py --dir docs/manual
cd docs/manual && corepack pnpm@9 install --frozen-lockfile && corepack pnpm@9 build
python3 tools/checar_build_manual.py --dir docs/manual
python3 -m pytest tools/ -q --ignore=tools/workflow-dashboard

O PR
/ship "docs(manual): prints de passo com balao na secao Reunioes e metas" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/prints-reunioes é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/prints-reunioes.

REPORTE NO FIM
Quantos prints por página (uma tabela: página, telas, balões), quantos avisos destacados você pôs e em quais páginas, o que a olhada nas imagens pegou e você corrigiu, o que ficou sem print e por quê, e qualquer afirmação de página que a tela desmentiu.
```
