# VERIFY: Tecnologia

- tsc: 0 erros no projeto de trabalho (`npx tsc --noEmit`), depois de cada
  mudança nas cenas e no patch.
- Stills e draft: 50 stills (meio de cada cena, cada corte e dois quadros
  depois de cada palavra-chave) e um draft em meia escala. Telas iguais ao app
  local (0.206.x) na faixa de id da Tecnologia, com a Demanda de exemplo do
  cartaz do QR do assistente ao sim; o destaque azul contorna o que a fala
  cita (Nova Demanda, a caixa de mensagem, o microfone, o print, o Rascunho,
  Criar Demanda, a raia Nova e o dono, as três raias, a Conversa e a menção,
  Planejar com a IA, a pergunta, as opções, a Recomendada, o microfone, O que
  já decidimos, Fechar e resumir, as decisões, Ficou em aberto, o Não, o sim,
  Mandado para os desenvolvedores, o selo Em análise, O que muda, o Vínculo,
  Levar para desenvolvimento, os selos Planejada, Em desenvolvimento e Em
  produção, Com você e Entregue, confira e conclua, Concluir, a caixa de
  resposta); fala legível palavra a palavra; logo inteira e parada só na
  assinatura. O Planejamento da Demanda (cenas 6 a 9) ocupa 52 s dos 142 s.
  - Os stills acharam a tela da Conversa e a da Etapa inteiras claras, sem as
    bordas, a data das respostas e o véu do destaque. Causa: fora da janela da
    transição o `TransitionSeries` embrulha a cena que sai com progresso 0, e
    o `flash` (q = 0 é o quadro do clarão quando k = 2) e o `pulsoJanela` (o
    pulso de luz de q = 0) clareavam a cena inteira. Consertado no
    `identidade.patch` com a guarda de progresso; a data da Conversa voltou
    (o mesmo recorte foi de 255 para 148 no cinza).
  - O primeiro draft deu seis congelamentos de 0,5 a 0,6 s nas cenas longas
    (a pergunta do Planejamento tem 22 s): o empurrão da câmera era 5% por
    cena. Passou a 0,8% por segundo, e o foco cabe na janela já com o
    empurrão do fim da cena.
- Copy: nota 13 de 14 (`roteiro.md`); humanizer e varredura anti-técnica
  (narração e texto de tela) sem achados; sem travessão nem meia-risca.
- gate-video.sh `--parada 139.2-142.1`: fps 30/1,30/1; um congelamento só, de
  139,53 s ao fim (a assinatura, dentro da parada); tocou no Chrome real
  (`duracao` 142.08, sem erro). `GATE OK`.
- Orçamento: 6,2 MB depois do reencode do `publicar.sh` (teto 10 MB). Com os
  outros masters desta máquina os vídeos somam 23,6 MB (teto 60 MB) e a
  publicação, 46 MB (teto 90 MB). O `publicar.sh --dry-run` para antes da
  conta porque o master de `reunioes/visao-geral.mp4` não está nesta máquina
  (lacuna anterior a esta fatia); a medida acima repete o reencode dele.
- Render final: ~/Videos/Hospital/Manual/tecnologia/o-caminho-de-uma-demanda.mp4,
  142,1 s, 64,2 MB, sha256 68c614b378db.
- Ressalvas: o vídeo de Contas médicas (piloto) usa o patch antigo e tem o
  mesmo clarão nas cenas que saem por `flash` e por `pulsoJanela`; fica para
  o próximo render dele.
