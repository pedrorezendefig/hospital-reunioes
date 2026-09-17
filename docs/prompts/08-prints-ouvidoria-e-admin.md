# Prints de passo: Ouvidoria e Admin

**31 Páginas de tarefa.** A Ouvidoria já tem 20 prints e o roteiro mais maduro; o Admin tem 2 prints para 11 tarefas. O trabalho aqui é ampliar os dois roteiros e pôr balão em tudo.

Roda em paralelo com os outros dois de prints e com o 09, **depois** do 07 mergeado
e dos quatro de vídeo mergeados. Cada um no seu worktree, todos contra o mesmo
app local: o README diz o que subir antes.

Copie o bloco inteiro e cole num terminal do Claude Code aberto DENTRO do worktree deste prompt. O [README](README.md) ensina a criar o worktree e a ordem de tudo.

```
Produza os Prints de passo das Páginas de tarefa das seções "Ouvidoria" e "Admin" do Manual do usuário, no repo pedrorezendefig/hospital-reunioes: em toda Página de tarefa, um print por mudança de tela, com balão numerado igual ao passo, tirado pelo Roteiro de prints do módulo.

ONDE VOCÊ ESTÁ
Você está num git worktree próprio, na branch docs/prints-ouvidoria-e-admin, criado a partir de origin/main. Outros terminais trabalham AO MESMO TEMPO em worktrees irmãos, contra o MESMO app local e o MESMO banco local. Antes de qualquer coisa, confira:
  git branch --show-current      (tem que devolver docs/prints-ouvidoria-e-admin)
  git rev-parse --show-toplevel  (tem que ser a pasta deste worktree, NUNCA /Users/pedrorezende/PedroDev/Hospital)
Se qualquer um dos dois devolver outra coisa, PARE e reporte. Nunca mude de branch, nunca saia deste worktree, nunca toque na árvore principal.

O worktree nasce sem node_modules. Seu primeiro comando de trabalho é:
  cd docs/manual && corepack pnpm@9 install --frozen-lockfile && cd ../..
Depois confira que o app local responde (o Pedro subiu a stack antes de abrir os terminais):
  curl -s http://localhost:3000 -o /dev/null -w "%{http_code}\n"
Se não responder 200, PARE e reporte. NÃO rode apply.sh, supabase stop/start nem docker: a stack é compartilhada com os outros terminais, e reiniciar derruba o roteiro deles no meio.

LEIA PRIMEIRO, NESTA ORDEM
1. .claude/skills/manual/SKILL.md e references/prints.md: o molde da Página de tarefa (o print fica DENTRO do item da lista, recuado três espaços) e a receita do balão numerado.
2. docs/adr/0057-*.md, a emenda de 17/09/2026 (decisões 4, 13 e 14): print por mudança de tela, aviso destacado no máximo um por página.
3. CONTEXT.md, seção "Manual do usuário": Print de passo, Aviso destacado.
4. docs/manual/prints/ouvidoria.py e docs/manual/prints/admin.py, que são os seus e já rodam (o do Admin é o molde da função entrar; o da Ouvidoria tem a regra do endereço impresso no cartaz e no e-mail).
5. tools/test_prints_manual.py e tools/test_prints_admin.py: todo print do roteiro passa pela guarda de endereço local, e o roteiro tem teste.

QUAL É O TRABALHO
As Páginas de tarefa estão em docs/manual/src/content/docs/ouvidoria/ (20 páginas com `papel`) e docs/manual/src/content/docs/admin/ (11 páginas com `papel`); index, novidades e como-funciona/ ficam de fora. São 31 tarefas. Para cada uma:
1. Leia os passos e decida quantas telas distintas eles atravessam. Um print por tela, com os balões dos passos que acontecem nela. Passo 1 "No menu, clique em X" e passo 2 "clique em Novo" costumam ser a mesma tela com dois balões; a janela que abre no passo 3 é outro print.
2. Escreva (ou amplie) a função do print no roteiro do módulo, com o helper `balao(page, seletor, numero)` da referência. O balão fica no elemento que o passo cita, pelo texto de tela do botão ou do campo, nunca por posição fixa.
3. Rode o roteiro e OLHE cada imagem gerada (abra com Read): balão em cima do elemento certo, número certo, texto legível, sem anel de foco, sem dado real. Balão em cima do elemento errado é o mesmo defeito do marcador errado no vídeo, e só a olhada pega.
4. Insira o print no Markdown, dentro do item do passo, com texto alternativo curto (até 10 palavras, o que a imagem mostra). Print que já existia na página e continua certo fica; se ele estava solto entre seções, mova para dentro do passo que ilustra e acrescente os balões.
5. Se a página tem uma ação sem volta ou algo que a pessoa precisa saber ANTES de clicar, ponha UM `:::caution[Título curto]` antes do passo que dispara. Um por página no máximo, e só se for irreversível ou custoso. Nem toda página tem: a maioria não tem.

FATOS DO SEU MÓDULO QUE FAZEM PRINT NASCER ERRADO
- Ouvidoria: o roteiro semeia casos em cada situação que as páginas citam (Nova, Em classificação, Aguardando o setor, Aguardando manifestante, Respondido, Encerrado, arquivado), com gravidades diferentes, sem nunca usar relato real. O e-mail de acionamento e o cartaz são montados fora do navegador com a base de produção, como o roteiro já faz: não capture cartaz nem e-mail com localhost.
- Ouvidoria: as telas do portal do setor (responder, pedir prazo, devolver) são sem login e nascem de um link único por caso; o roteiro obtém o link pela API local ou pelo banco local, nunca à mão. Saem em celular (390x844).
- Ouvidoria: caso sigiloso não aparece na lista de quem não é da Ouvidoria; o print de "O que é sigiloso" não é seu (é Como funciona), mas o de "Classificar e acionar" mostra a caixa de sigilo, e o balão vai nela quando o passo a cita.
- Admin: as telas de Usuários, Setores, Cargos e Tipos de Reunião saem logado como admin (Super Admin). "Dados do Atendimento" e "Espelho da Global Health" saem como admin também; o Espelho consulta um serviço de fora, e se o app local não tiver a chave a seção mostra o estado de erro: capture o que a tela mostra de verdade e diga no PR.
- Admin: "Entregar o acesso a uma pessoa" mostra a senha gerada numa janela; o print mostra a janela com uma senha GERADA PELO APP LOCAL para uma pessoa de exemplo, nunca a de uma conta real, e a pessoa de exemplo é desativada pelo roteiro no fim.
- Candidatos a Aviso destacado (um por página no máximo): "Encerrar um caso e avisar a pessoa" (o texto do desfecho sai por e-mail para quem manifestou), "Entregar o acesso a uma pessoa" (a senha aparece uma vez só), "Tirar o acesso de quem saiu" e, na Ouvidoria, o apagamento antes do prazo de guarda se houver página de tarefa para ele.

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
- Não toque em docs/manual/astro.config.mjs, src/components/, src/styles/, publicar.sh, .github/, tools/*.py (exceto criar/ampliar o teste do SEU roteiro, tools/test_prints_admin.py e, se criar, tools/test_prints_ouvidoria.py).
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
/ship "docs(manual): prints de passo com balao nas secoes Ouvidoria e Admin" --no-merge --skip-review --no-bump

Quando o /ship avisar que a branch atual não é a main, confirme e siga: a branch docs/prints-ouvidoria-e-admin é a sua, criada de propósito para este terminal. Não use --from-diff, não crie branch a partir de outra coisa que não seja a atual.

Todo comentário seu em issue ou PR começa com <!-- automacao --> na PRIMEIRA linha.

GIT SAFETY
Proibido git checkout --, git reset --hard e git stash drop em arquivo que não seja seu. Confira `git branch --show-current` antes de cada commit: tem que devolver docs/prints-ouvidoria-e-admin.

REPORTE NO FIM
Quantos prints por página (uma tabela: página, telas, balões), quantos avisos destacados você pôs e em quais páginas, o que a olhada nas imagens pegou e você corrigiu, o que ficou sem print e por quê, e qualquer afirmação de página que a tela desmentiu.
```
