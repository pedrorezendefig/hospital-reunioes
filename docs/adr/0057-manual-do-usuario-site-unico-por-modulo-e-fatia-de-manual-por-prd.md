---
status: accepted
amends: 0044, 0056
amended_by: 0058, 0062, 0071, 0072
---

# Manual do usuário: um site por módulo, vídeo por tarefa, fatia de manual por PRD

Decisão do Pedro (15/set/2026, grilling). O hospital tem um manual só, o da Ouvidoria (#563): uma página HTML feita à mão, com público declarado "Pedro e time interno", num projeto Vercel próprio, sem skill que o produza nem cadeia que o atualize. Cada PRD novo entrega código, vídeo de percepção e página de divulgação, e o manual fica para trás. Esta ADR fixa o que é o manual, onde mora, como se produz e como entra no pipeline.

## Decisões

1. **Um site, um endereço, por módulo.** O manual é um site único (`manual.hospitalsaomatheus.cloud`, projeto Vercel único), com seções na ordem do menu do app: Primeiros passos, Reuniões e metas, Ouvidoria, POPs, Admin. Papel não é estrutura, é selo na página ("Só admin", "Sem login"). A aba Tecnologia fica fora, e a Central de Comando também (emenda da ADR 0058, decisão 10: só Super admin vê, e é leitura, não tarefa). O manual da Ouvidoria é reescrito no molde novo e o endereço antigo redireciona. Rejeitado: um site por módulo (N deploys, usuário que erra o módulo cai fora); manual por papel (a mesma tela em três trilhas, envelhece rápido).

2. **Markdown por página, gerado com Astro Starlight.** Conteúdo em `docs/manual/src/content/docs/<modulo>/<tarefa>.md`, tema vestido com o design system do app (HP Simplified, navy, logo), busca, menu mobile e sumário de graça. Rejeitado: HTML à mão por página (cada página nova sai diferente e custa caro); gerador próprio em Python (busca e mobile são o que mais dá trabalho de manter).

3. **`docs/manual/` é o site e é dono dos vídeos de tarefa.** Composição HyperFrames de cada vídeo em `docs/manual/video/<modulo>/<slug>/` (versionada, `assets` para `_assets`), MP4 renderizado em `public/video/` (fora do git), prints em `src/assets/<modulo>/`, roteiro de prints em `prints/<modulo>.py`. Os sete vídeos de capítulo da Ouvidoria migram de `docs/comunicacao/ouvidoria/manual-cap-N/` para cá. `docs/comunicacao/` fica só com o que a `/divulgar` gera por PRD; o manual lê os MP4 de lá para Novidades. Fecha a pendência da decisão 3 do ADR 0044: o manual não entra em `docs/comunicacao/`, porque os ciclos de vida são outros (a divulgação é marco e envelhece de propósito; o manual é vivo).

4. **Página de tarefa, curta, com vídeo por tarefa.** A unidade é a ação ("Registrar uma manifestação"), no molde fixo do glossário (quando usar, quem faz, vídeo, até 6 passos, se der errado), "você" e imperativo, palavra da tela. Vídeo gerado (mesma receita da `/divulgar`, mudo, sem esperar OK humano desde a emenda de 14/10/2026), 30 a 60 s, regerável. Página publica sem vídeo, com aviso. Rejeitado: gravação de tela com voz (não regera quando a tela muda); vídeo por capítulo como unidade; vídeo obrigatório para publicar.

5. **Só produção no ar.** Página de funcionalidade não deployada nasce com `draft: true` (fora do build e da busca) e perde o draft no deploy do PRD. Sem selo "em desenvolvimento" para o usuário. Cada página traz `prd:` no frontmatter para o deploy saber o que liberar.

6. **MP4 no próprio site, comprimido, com trava.** A publicação reencoda cada vídeo para 720p H.264 e trava se a pasta passar de 90 MB (limite de 100 MB do plano Hobby). Rejeitado por ora: Supabase Storage de produção (exige chave de serviço fora do Coolify); Vercel Pro desde já (a trava avisa antes; subir de plano é a saída sem mudar nada).

7. **Prints são tela real, por roteiro.** Um script versionado por módulo abre o app local com dados de exemplo e captura os prints. Rejeitado: quadro do vídeo no lugar do print (é desenho da tela, não a tela).

8. **Fatia de manual por PRD, não mesmo PR.** O `/to-issues` cria em todo PRD com tela uma fatia final "docs: manual do PRD" (`type:docs`), bloqueada pelas fatias de código, que roda na `/onda` como qualquer issue e sobe como qualquer fatia (emendado em 14/10/2026: a fatia parava no merge até alguém ver o vídeo). O `/deploy ship` tira o draft das páginas dos PRDs que subiram e republica o manual. O `/to-prd` ganha a seção "Manual: páginas que nascem ou mudam". Isto emenda o ADR 0056, decisão 2 e consequência: a regra "mudou o comportamento, o arquivo muda no mesmo PR" vale para o kit de conhecimento (só texto) e **não** para o manual, cuja página precisa da tela pronta para print e vídeo. A regra compartilhada entre kit e manual é "no mesmo PRD". Rejeitado: manual no mesmo PR de código (página nasce sem print e sem vídeo, PR inflado); manual fora da fila (some da cobrança).

9. **Duas skills.** `/manual <módulo | #PRD | publicar>` produz (páginas, prints, vídeos, Novidades; `publicar` = build, lint, trava, deploy). `/montar-manual` planeja como a `/montar-ondas`: inventaria módulo por módulo o que falta (página, print, vídeo, Novidades por PRD), presta contas de tudo e entrega **um prompt por terminal, um terminal por módulo**, cada um em worktree próprio mexendo só nas pastas do seu módulo, teto de 3 (render de vídeo disputa a CPU). A fundação (Starlight, tema, home, `publicar.sh`, redirecionamento, item Ajuda) é uma issue sozinha, antes. Publicar na Vercel é um passo só, depois dos merges.

10. **Lint trava a publicação.** Travessão e meia-risca (ADR 0013), a lista de jargão da `/divulgar` (migration, endpoint, API, PR, deploy, RLS, backend, frontend...) e aviso para página de tarefa acima de 250 palavras.

11. **O app aponta para o manual.** Item "Ajuda" na sidebar abre, em nova aba, a seção do módulo em que a pessoa está (por módulo, não por tela: mapa por tela envelhece a cada rota).

12. **Novidades por PRD.** Uma entrada por PRD entregue, com o vídeo de percepção quando existe e links para as tarefas que mudaram. Não é changelog.

## Emenda a este ADR (16/set/2026, o domínio próprio foi abandonado)

**Decisão 1, o endereço do manual.** A decisão nomeia `manual.hospitalsaomatheus.cloud` como o endereço do site, e a seção de consequências trata o DNS como ato humano pendente. O Pedro decidiu abandonar o domínio próprio: o endereço definitivo do Manual do usuário passa a ser **`https://manual-hsm.vercel.app`**, o alias de produção do projeto Vercel, sem variável de ambiente e sem DNS pendente.

O que mudou desde a decisão original: o registro nunca foi criado. A zona de `hospitalsaomatheus.cloud` não é servida pela Hostinger, como a consequência supunha, e sim pela Cloudflare, então o ato humano não era o que estava escrito. Enquanto isso, o app já apontava para o domínio, que responde "endereço não encontrado", e o item Ajuda abria uma aba em branco para todo mundo. O custo do endereço bonito era o manual inacessível na tela, e o alias da Vercel já funciona. O `site:` do Astro, de onde saem as URLs canônicas e o mapa do site, passa a ser o mesmo endereço; ele apontava para um domínio que não resolve.

A variável `NEXT_PUBLIC_MANUAL_URL` continua existindo, com o mesmo papel de sempre: apontar um ambiente para uma prévia. Só o valor padrão mudou. Voltar a ter domínio próprio um dia é decisão nova, e o caminho é o mesmo de qualquer troca de endereço: o padrão no app, o `site:` do Astro e um redirecionamento.

**Decisão 11, por onde o app aponta.** A decisão diz "item Ajuda na sidebar", no singular, e a implementação pôs o item só na `Sidebar`. O app tem duas barras: a `AppShell` troca a `Sidebar` pela `AdminSidebar` quando a pessoa entra no /admin. A seção Admin do manual estava publicada e ninguém chegava nela pela barra, porque justamente lá a barra que tinha o item não é a que aparece. A decisão passa a valer para as duas barras, e cada uma abre a seção do lugar em que a pessoa está.

As demais decisões ficam intactas.

## Emenda a este ADR (17/set/2026, a camada didática: print de passo, fluxograma de caminho e aviso)

Decisão do Pedro (grilling de 17/09/2026, com a recomendação seguida em todas as perguntas). O Manual estava no ar com 86 páginas, o molde certo e o texto já humano, mas 39 das 57 Páginas de tarefa não tinham nenhuma imagem, 48 exibiam "Vídeo em produção" e nenhuma página tinha fluxograma nem aviso destacado. Quem lê no celular, sem som e com pressa, não dá play: olha a figura. Esta emenda acrescenta a camada visual que o leitor leigo precisa e fixa como ela se produz.

**Decisão 4, a Página de tarefa ganha uma segunda camada obrigatória.** O Vídeo de tarefa continua a unidade de "ver a fazer". Ao lado dele, toda Página de tarefa leva **um print por mudança de tela, com balão numerado igual ao número do passo**, colocado logo abaixo do passo que ele ilustra. Passos que acontecem na mesma tela dividem um print com vários balões; a regra é "por tela", não "por passo". O print continua sendo tela real do app (decisão 7): o balão é desenhado pelo próprio Roteiro de prints por cima da tela, antes da captura, nunca em editor de imagem. O aviso "Vídeo em produção" sai da tela do usuário; a página sem vídeo publica sem dizer nada, e a lacuna continua no inventário da `/montar-manual`. Rejeitado: print como camada principal e vídeo só para tarefa com movimento (o ADR já decidiu vídeo por tarefa e a campanha de 48 vídeos estava pronta; o que custa caro no vídeo, a réplica, não se aproveita no print, que é barato); balão desenhado à mão (envelhece e não regera); quadro do vídeo no lugar do print (já rejeitado na decisão 7).

**Decisão 13, fluxograma de caminho.** Fluxograma entra **só onde há caminho ou estado**: nas cinco Visões gerais, ilustrando "O caminho de ponta a ponta", e nas páginas de Como funciona que descrevem estados ou desvios. No máximo um por página, com as palavras da tela e do glossário. A fonte é texto versionado (`docs/manual/fluxogramas/<modulo>/<slug>.mmd`, sintaxe Mermaid), o SVG é gerado por script do site em `src/assets/<modulo>/fluxo-<slug>.svg` com as cores do app, e a página aponta para o SVG como aponta para um print. Não confundir com o fluxograma do POP, que é seção do documento gerado pelo app. Rejeitado: Mermaid renderizado no build (exige navegador no build da Vercel e muda o pipeline por causa de oito imagens); SVG desenhado à mão pelo agente (cada um sai diferente e não regera); fluxograma em Página de tarefa (a tarefa é linear, o print de passo cobre).

**Decisão 14, aviso destacado.** O aviso do que é irreversível ou do que a pessoa precisa saber antes de clicar ("Finalizar sem assinatura não tem volta", "a senha aparece uma vez só") vira um callout do Starlight (`:::caution[Título]`) no corpo da Página de tarefa, no máximo um por página, colocado antes do passo que dispara a ação. "Se der errado" continua lista, como está. Rejeitado: callout em toda ressalva (vira ruído e o leitor para de ler).

**Decisão 2, o tema desenha o passo.** O tema do site passa a numerar os passos das Páginas de tarefa com número grande e a acomodar a figura dentro do item da lista, e o vídeo ganha capa (`poster`) gerada pelo `publicar.sh` a partir do primeiro quadro do MP4. Nenhuma dessas mudanças toca o Markdown das páginas.

**Decisão 10, o lint.** O texto alternativo das imagens deixa de contar no teto de 250 palavras: ninguém lê o `alt`, e três prints por página empurrariam toda tarefa para o aviso.

**Produção.** A camada didática é uma segunda campanha de prompts em `docs/prompts/` (07 a 09), na mesma mecânica dos vídeos: um worktree por terminal, um terminal por módulo, teto de três terminais de print (o app local e o banco são compartilhados), o tema sozinho e antes de todos, os fluxogramas em paralelo com os prints porque não tocam Página de tarefa, e o 06 (enxugar a escrita) por último, porque mexe no texto de todas. Humanização separada foi rejeitada: o texto já é humano, e os três cacoetes encontrados ("é assim mesmo", "de propósito", "não é X: é Y") entram no 06.

As demais decisões ficam intactas.

## Emenda a este ADR (13/out/2026, o Vídeo de tarefa ganha estilo próprio e a campanha de rerender, ADR 0071)

Decisão do Pedro (grilling de 13/10/2026). Os 61 Vídeos de tarefa são réplicas fiéis do app, mas cada um saiu de uma sessão diferente, sem estilo compartilhado nem gate de verificação além do `check` e do olhar humano. O [HyperFrames Student Kit](https://github.com/nateherkai/hyperframes-student-kit) de Nate Herk traz o que faltava: um contrato de estilo (`DESIGN.md` + `tokens.css` + cards como sub-composições com slots nomeados), um vocabulário de movimento, gates de verificação por frames e o loop "nota do revisor vira regra na skill". A filosofia visual do kit (canvas preto, tipo cromado, 1,5 s por cena) é de reel, e não entra.

**Decisão 4, o Vídeo de tarefa ganha a disciplina do kit com a cara do hospital.** O corpo continua réplica fiel do app, mudo, 30 a 60 s ("na dúvida, fiel vence"). Entram do kit: (a) um **Estilo do manual** em `docs/manual/video/_estilo/`, no formato da style-library do kit, com `DESIGN.md`, `tokens.css` tirado do `globals.css` do frontend e cards reusáveis (legenda de passo, callout, lower-third, abertura, carimbo) como sub-composições com slots; (b) o vocabulário de movimento: push-in no elemento do passo, câmera que nunca para, transição com rastro entre telas, e a lei do timeline que preenche o slot inteiro (sem quadro preto); (c) os gates de verificação: strips de frames a cada corte, `VERIFY.md` por vídeo, além do carimbo e do gate anti-técnica que já existem; (d) o loop em que cada nota humana no draft vira regra na skill `/manual`, para a nota não se repetir. Rejeitado: visual do kit só na abertura e no fecho (dois mundos num vídeo de 45 s); adotar o kit inteiro (bonito e deixa de parecer o app).

**O kit mora fora do repositório.** Clone em `~/PedroDev/hyperframes-student-kit` como referência de leitura; o que o manual usa é adaptado à mão para `.claude/skills/manual/references/` e para o Estilo do manual. Nenhuma skill do kit é instalada globalmente (três têm o mesmo nome das skills globais de HyperFrames). O HyperFrames continua na versão do manual, não na do kit. Os vídeos de referência gerados pelo Opus 5.5 ficam em `local/manual-video-referencias/` (fora do git, como os masters) e cada um tem uma **Ficha de referência** em `_estilo/references/`: o que copiar dele e o que não copiar. O `DESIGN.md` cita as fichas.

**Gate da campanha de rerender dos 61 vídeos.** (Emendado em 14/10/2026: o OK humano por vídeo e por módulo caiu; a Folha de contato vai no corpo do PR como evidência, sem esperar resposta.) A regra pedia OK humano por vídeo no dia a dia e no piloto, e por módulo na campanha. Ordem: a fundação (estilo, cards, gates, skill) é uma issue sozinha; depois um piloto de dois vídeos com OK por vídeo e nota virando regra; depois um terminal por módulo, teto de três (render disputa CPU), cada um entregando uma **Folha de contato** (quadros-chave de todos os vídeos do módulo e um MP4 inteiro) para um OK por módulo. O texto que aparece no vídeo passa pelo humanizer (ADR 0071). Rejeitado: 61 OKs (campanha presa à agenda); sem OK humano (o primeiro vídeo errado vai ao ar sem ninguém ver).

A rejeição de "humanização separada" registrada na seção Produção abaixo deixa de valer: a ADR 0071 decide a reescrita.

## Emenda a este ADR (14/out/2026, o draft do Vídeo de tarefa deixa de esperar o humano)

Decisão do Pedro, depois do piloto de dois vídeos (#1231, PR #1246): "Eu não quero mais checar draft. Eu confio até o final. Eu não quero que você me pergunte." A Fatia de manual parava no PR verde, fora da subida, até alguém assistir ao draft e rodar o `fechar_onda.py`; a emenda de 13/10/2026 pedia o mesmo OK por vídeo no dia a dia e por módulo na campanha de rerender.

**Decisões 4 e 8, o vídeo sobe sem OK humano.** O agente faz o draft, passa pelos gates (`hyperframes check`, strips de cada corte, `tools/checar_video_manual.py`, `tools/anel_video_manual.py`, quadros olhados e `VERIFY.md`), faz o render final na própria fatia e abre o PR, que entra na subida como qualquer outro. Na campanha de rerender, a Folha de contato continua sendo feita e vai no corpo do PR como evidência, sem esperar resposta. O loop "nota vira regra" continua: a nota do Pedro chega depois, com o vídeo no ar, e o conserto e a regra saem num PR novo. Rejeitado: manter o OK só para vídeo novo (a nota do piloto, o anel fora do lugar, virou o gate `anel_video_manual.py`, e a espera segurava a fatia inteira). As paradas humanas da ADR 0068, regra 9, passam a ser três.

## Emenda a este ADR (14/out/2026, um vídeo por módulo e orçamento de 40 MB, ADR 0072)

Decisão do Pedro (PRD #1259). O vídeo do Manual deixa de ser por tarefa: cada módulo abre com um **Vídeo de visão geral** do caminho principal, "Conheça a plataforma" aparece também na página inicial, e o Admin fica sem vídeo (decisões 3 e 4). As 61 Páginas de tarefa perdem o vídeo, e as composições dos Vídeos de tarefa e dos capítulos da Ouvidoria saem do repositório; os masters ficam em `local/`. O `publicar.sh` ganha três travas depois do reencode: soma dos MP4 até 40 MB, um vídeo por módulo, nenhum acima de 8 MB, com o teto de 90 MB mantido (decisão 6). Novidades levam link para a página de divulgação no lugar do vídeo embutido (decisão 12), e a Fatia de manual só pede vídeo quando o PRD muda o caminho principal do módulo (decisão 8). O detalhe e os rejeitados estão na ADR 0072.

## Consequências

- `docs/manual/ouvidoria/` (página única) deixa de existir como está: vira a seção `ouvidoria/` do site, recortada em tarefas e "Como funciona". Nada do conteúdo se perde; o formato muda.
- `CLAUDE.md` ("Docs vivos") e `README.md` passam a descrever `docs/manual/` como o site do manual; o `/ask-pedro` ganha `/manual` e `/montar-manual` no mapa; a `/divulgar` não muda, só passa a ser lida pelo manual.
- Node >= 22.12 entra nos pré-requisitos de máquina (`/setup-maquina`). Busca só funciona no build, não no `dev`.
- O DNS de `manual.hospitalsaomatheus.cloud` é ato humano na Hostinger; até lá o alias `vercel.app` serve.
- O QR da apresentação em pptx e a página de módulo da divulgação apontam para o endereço antigo; o redirecionamento cobre, e os dois links são trocados na fundação.
