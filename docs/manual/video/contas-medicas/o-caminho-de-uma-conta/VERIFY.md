# VERIFY: Contas médicas

- tsc: 0 erros no projeto de trabalho, e 0 erros num projeto refeito do zero
  pelo "Como refazer" do `roteiro.md` (modelo da skill motion +
  `cena/projeto/identidade.patch` + `cena/*.tsx` + `tempos.json` + o
  `video-alvos.json` do roteiro de prints).
- Stills e draft: folhas de contato do draft (meio de cada cena e cortes) e
  quadros avulsos; telas iguais ao app de produção (0.206.x) na faixa de id de
  Contas médicas, o destaque azul contorna o elemento que a fala cita (envio,
  cartão e os dois quadrados, Abrir, nota de entrada, verbo, Feito, Ver
  evidência, Não procede, Bloqueado, Concluir, Devolver à fila, Erro, Analisar
  de novo, Copiar para a TI, Validação, lembretes, Painel), fala legível
  palavra a palavra, logo inteira e parada só na assinatura.
- Copy: nota 13 de 14 (`roteiro.md`); humanizer e varredura anti-técnica
  (narração e texto de tela) sem achados; sem travessão nem meia-risca.
- gate-video.sh `--parada 139-141.9`: fps 30/1,30/1; sem congelamento fora da
  parada (parada medida de 139,33 s a 141,89 s); tocou no Chrome real
  (`duracao` 141.888, sem erro).
  - Primeiro render reprovou: 11 congelamentos de 0,5 a 1,1 s no fim de cada
    cena (o empurrão da câmera tinha easing e assentava antes da saída; na
    cena 1 a lista assentava parada). Consertado com o empurrão em velocidade
    constante até o fim da sequência (`pecas.tsx`) e na lista do gancho.
  - O passo de fps do `gate-video.sh` reprovava todo MP4 do Remotion: o
    `side_data` vazio deixa o csv do ffprobe em `30/1,30/1,`. O script agora
    corta nos dois primeiros campos (conferido: 25 fps continua reprovando).
- Orçamento (`bash docs/manual/publicar.sh --dry-run`): 5,5 MB depois do
  reencode (teto 10 MB); vídeos somam 21 MB (teto 60 MB); publicação 43 MB
  (teto 90 MB).
- Render final: ~/Videos/Hospital/Manual/contas-medicas/o-caminho-de-uma-conta.mp4,
  141,9 s, 63,6 MB, sha256 ae7f166faaed. O master de 14/10 foi para
  `anteriores/2026-10-14-o-caminho-de-uma-conta.mp4`.
- Ressalvas: o ok do Pedro no rascunho (parada humana da decisão 14 do grill)
  ainda não veio; o ajuste de estilo que ele pedir entra na receita e neste
  vídeo antes da subida.
