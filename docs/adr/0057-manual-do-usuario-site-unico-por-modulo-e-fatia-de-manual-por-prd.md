---
status: accepted
amends: 0044, 0056
---

# Manual do usuário: um site por módulo, vídeo por tarefa, fatia de manual por PRD

Decisão do Pedro (15/set/2026, grilling). O hospital tem um manual só, o da Ouvidoria (#563): uma página HTML feita à mão, com público declarado "Pedro e time interno", num projeto Vercel próprio, sem skill que o produza nem cadeia que o atualize. Cada PRD novo entrega código, vídeo de percepção e página de divulgação, e o manual fica para trás. Esta ADR fixa o que é o manual, onde mora, como se produz e como entra no pipeline.

## Decisões

1. **Um site, um endereço, por módulo.** O manual é um site único (`manual.hospitalsaomatheus.cloud`, projeto Vercel único), com seções na ordem do menu do app: Primeiros passos, Reuniões e metas, Ouvidoria, POPs, Admin. Papel não é estrutura, é selo na página ("Só admin", "Sem login"). A aba Tecnologia fica fora. O manual da Ouvidoria é reescrito no molde novo e o endereço antigo redireciona. Rejeitado: um site por módulo (N deploys, usuário que erra o módulo cai fora); manual por papel (a mesma tela em três trilhas, envelhece rápido).

2. **Markdown por página, gerado com Astro Starlight.** Conteúdo em `docs/manual/src/content/docs/<modulo>/<tarefa>.md`, tema vestido com o design system do app (HP Simplified, navy, logo), busca, menu mobile e sumário de graça. Rejeitado: HTML à mão por página (cada página nova sai diferente e custa caro); gerador próprio em Python (busca e mobile são o que mais dá trabalho de manter).

3. **`docs/manual/` é o site e é dono dos vídeos de tarefa.** Composição HyperFrames de cada vídeo em `docs/manual/video/<modulo>/<slug>/` (versionada, `assets` para `_assets`), MP4 renderizado em `public/video/` (fora do git), prints em `src/assets/<modulo>/`, roteiro de prints em `prints/<modulo>.py`. Os sete vídeos de capítulo da Ouvidoria migram de `docs/comunicacao/ouvidoria/manual-cap-N/` para cá. `docs/comunicacao/` fica só com o que a `/divulgar` gera por PRD; o manual lê os MP4 de lá para Novidades. Fecha a pendência da decisão 3 do ADR 0044: o manual não entra em `docs/comunicacao/`, porque os ciclos de vida são outros (a divulgação é marco e envelhece de propósito; o manual é vivo).

4. **Página de tarefa, curta, com vídeo por tarefa.** A unidade é a ação ("Registrar uma manifestação"), no molde fixo do glossário (quando usar, quem faz, vídeo, até 6 passos, se der errado), "você" e imperativo, palavra da tela. Vídeo gerado (mesma receita da `/divulgar`, mudo, OK humano no draft), 30 a 60 s, regerável. Página publica sem vídeo, com aviso. Rejeitado: gravação de tela com voz (não regera quando a tela muda); vídeo por capítulo como unidade; vídeo obrigatório para publicar.

5. **Só produção no ar.** Página de funcionalidade não deployada nasce com `draft: true` (fora do build e da busca) e perde o draft no deploy do PRD. Sem selo "em desenvolvimento" para o usuário. Cada página traz `prd:` no frontmatter para o deploy saber o que liberar.

6. **MP4 no próprio site, comprimido, com trava.** A publicação reencoda cada vídeo para 720p H.264 e trava se a pasta passar de 90 MB (limite de 100 MB do plano Hobby). Rejeitado por ora: Supabase Storage de produção (exige chave de serviço fora do Coolify); Vercel Pro desde já (a trava avisa antes; subir de plano é a saída sem mudar nada).

7. **Prints são tela real, por roteiro.** Um script versionado por módulo abre o app local com dados de exemplo e captura os prints. Rejeitado: quadro do vídeo no lugar do print (é desenho da tela, não a tela).

8. **Fatia de manual por PRD, não mesmo PR.** O `/to-issues` cria em todo PRD com tela uma fatia final "docs: manual do PRD" (`type:docs`), bloqueada pelas fatias de código, que roda na `/onda` como qualquer issue e para no checkpoint de merge com o draft do vídeo. O `/deploy ship` tira o draft das páginas dos PRDs que subiram e republica o manual. O `/to-prd` ganha a seção "Manual: páginas que nascem ou mudam". Isto emenda o ADR 0056, decisão 2 e consequência: a regra "mudou o comportamento, o arquivo muda no mesmo PR" vale para o kit de conhecimento (só texto) e **não** para o manual, cuja página precisa da tela pronta para print e vídeo. A regra compartilhada entre kit e manual é "no mesmo PRD". Rejeitado: manual no mesmo PR de código (página nasce sem print e sem vídeo, PR inflado); manual fora da fila (some da cobrança).

9. **Duas skills.** `/manual <módulo | #PRD | publicar>` produz (páginas, prints, vídeos, Novidades; `publicar` = build, lint, trava, deploy). `/montar-manual` planeja como a `/montar-ondas`: inventaria módulo por módulo o que falta (página, print, vídeo, Novidades por PRD), presta contas de tudo e entrega **um prompt por terminal, um terminal por módulo**, cada um em worktree próprio mexendo só nas pastas do seu módulo, teto de 3 (render de vídeo disputa a CPU). A fundação (Starlight, tema, home, `publicar.sh`, redirecionamento, item Ajuda) é uma issue sozinha, antes. Publicar na Vercel é um passo só, depois dos merges.

10. **Lint trava a publicação.** Travessão e meia-risca (ADR 0013), a lista de jargão da `/divulgar` (migration, endpoint, API, PR, deploy, RLS, backend, frontend...) e aviso para página de tarefa acima de 250 palavras.

11. **O app aponta para o manual.** Item "Ajuda" na sidebar abre, em nova aba, a seção do módulo em que a pessoa está (por módulo, não por tela: mapa por tela envelhece a cada rota).

12. **Novidades por PRD.** Uma entrada por PRD entregue, com o vídeo de percepção quando existe e links para as tarefas que mudaram. Não é changelog.

## Consequências

- `docs/manual/ouvidoria/` (página única) deixa de existir como está: vira a seção `ouvidoria/` do site, recortada em tarefas e "Como funciona". Nada do conteúdo se perde; o formato muda.
- `CLAUDE.md` ("Docs vivos") e `README.md` passam a descrever `docs/manual/` como o site do manual; o `/ask-pedro` ganha `/manual` e `/montar-manual` no mapa; a `/divulgar` não muda, só passa a ser lida pelo manual.
- Node >= 22.12 entra nos pré-requisitos de máquina (`/setup-maquina`). Busca só funciona no build, não no `dev`.
- O DNS de `manual.hospitalsaomatheus.cloud` é ato humano na Hostinger; até lá o alias `vercel.app` serve.
- O QR da apresentação em pptx e a página de módulo da divulgação apontam para o endereço antigo; o redirecionamento cobre, e os dois links são trocados na fundação.
