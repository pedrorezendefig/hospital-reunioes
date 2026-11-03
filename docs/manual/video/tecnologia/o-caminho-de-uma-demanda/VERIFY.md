# VERIFY: Tecnologia

Refeito na Fatia de manual do PRD #1380 (issue #1387): a aba virou o chat do
Assistente de Tecnologia (ADR 0077), e o vídeo segue um bug e uma melhoria da
pergunta inicial ao Criar o card, e depois a lista com a Etapa.

- tsc: 0 erros no projeto de trabalho (`npx tsc --noEmit`), depois de cada
  mudança nas cenas.
- Stills e draft: 49 stills (um a cada 3 s e o começo de cada cena, cinco
  quadros depois do corte) e um draft em meia escala. Telas iguais ao app
  local com o código da produção (v0.210.1), a lista e a conversa trocadas no
  navegador pelo roteiro de prints, sem falar com a IA. O destaque azul
  contorna o que a fala cita: a pergunta, Nova conversa, Bug e Melhoria, a
  caixa de mensagem, o microfone, o botão de imagem, as perguntas do bug, o
  resumo e o Como saber que foi resolvido, Não bateu, Criar o card, o recado
  da fila, a pergunta da melhoria, as opções, a Recomendada, Fechar e resumir,
  as Decisões e o porquê, Ficou em aberto, a lista, o Registrada, as Etapas
  Em análise, Em desenvolvimento e Em produção, a Etapa e O que muda do pedido
  aberto. Fala legível palavra a palavra; logo inteira e parada só na
  assinatura. A conversa (cenas 2 a 6) ocupa de 3,0 s a 91,7 s dos 121,7 s.
  - Os stills acharam a virada vazia no primeiro segundo (só a legenda
    "Começou" no fundo azul): a fala da IA entrava na palavra "pergunta". Ela
    passou a entrar no primeiro quadro da cena e acende na palavra.
  - O draft deu um congelamento de 0,6 s no começo da virada (113,9 s), antes
    de a fala da IA mexer. A cena da virada ganhou o empurrão lento até a
    logo, como as cenas de tela; no render final não há mais congelamento fora
    da assinatura.
- Copy: nota 13 de 14 (`roteiro.md`); humanizer e varredura anti-técnica
  (narração e texto de tela) sem achados; sem travessão nem meia-risca.
- gate-video.sh `--parada 118.8-121.8`: fps 30/1,30/1; um congelamento só, de
  119,17 s ao fim (a assinatura, dentro da parada); tocou no Chrome real
  (`duracao` 121.728, sem erro). `GATE OK`.
- Orçamento: 4,9 MB depois do reencode do `publicar.sh` (mesmo comando
  `ffmpeg`, teto 10 MB), 1,3 MB a menos que o vídeo anterior (6,2 MB). A soma
  dos vídeos cai na mesma medida em relação à conta do render anterior
  (23,6 MB, teto 60 MB). O `publicar.sh --dry-run` não foi rodado inteiro: ele
  para antes da conta porque o master de `reunioes/visao-geral.mp4` não está
  nesta máquina (lacuna anterior a esta fatia, já anotada no render anterior).
- Strips: o `tools/strips_video_manual.py` lê os cortes de uma composição
  HyperFrames (`index.html`); esta é Remotion, e os cortes foram conferidos
  nos stills do começo de cada cena.
- Render final: ~/Videos/Hospital/Manual/tecnologia/o-caminho-de-uma-demanda.mp4,
  121,7 s, 53,6 MB, sha256 8c33981fe4b6. O master anterior foi para
  `anteriores/2026-11-02-o-caminho-de-uma-demanda.mp4`.
- Ressalvas: o vídeo não tem efeito sonoro nem música, como o anterior; só a
  narração da voz A.
