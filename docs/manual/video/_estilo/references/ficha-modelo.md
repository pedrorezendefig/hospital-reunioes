# Ficha de referência: <nome do vídeo>

Molde. Quando um vídeo de referência chega em `local/manual-video-referencias/`,
copie este arquivo para `references/<nome-do-mp4>.md`, preencha e cite a ficha
nova na tabela "Fichas de referência" do `DESIGN.md`. Uma ficha por vídeo.

- **Vídeo:** `local/manual-video-referencias/<arquivo>.mp4`
- **Gerado por:** Opus 5.5, em DD/MM/AAAA
- **Duração:** NN s
- **Quadros olhados:** os instantes que importam, tirados com
  `ffmpeg -ss <instante> -i <mp4> -frames:v 1 <saida>.png`

## O que copiar

Uma coisa por linha, com o instante e a medida, para a próxima sessão tirar a
mesma coisa da mesma referência.

- 0:07, transição com rastro entre telas: saída em 0,35 s com blur forte, entrada
  em 0,6 s, mesmo sentido dos dois lados.

## O que não copiar

Uma por linha, com o motivo.

- 0:00, abertura em fundo preto: o manual não usa canvas preto.

## Onde entra

O card, o token ou a regra da receita que esta ficha criou, mudou ou confirmou.

- `cards/legenda-de-passo`: a troca de texto sem a placa piscar.
