---
status: accepted
amends: 0044, 0026
---

# Vídeo de percepção e página de divulgação são uma entrega só, numa pasta só por PRD

Até aqui a entrega para o diretor era feita por duas skills e duas pastas: `/perceber` gerava o vídeo em `docs/comunicacao/percepcao/<contexto>/<PRD>-<slug>/` e `/divulgar` gerava a página em `docs/comunicacao/divulgacao/<PRD>-<slug>/`, copiando o MP4 de uma pasta para a outra. Uma entrega, dois comandos, uma cópia que envelhece.

## Decisões

1. **Uma skill: `/divulgar <PRD> [--so-video | --so-pagina]`.** O passo 1 gera o vídeo (todo o conteúdo do antigo `/perceber`, incluindo o gate humano no draft). O passo 2 gera a página e publica na Vercel. `--so-video` cobre o caso WhatsApp. O `/perceber` deixa de existir.

2. **Uma pasta por PRD: `docs/comunicacao/<contexto>/<PRD>-<slug>/`.** Dentro: `video/` (composição HyperFrames, versionada, com `assets` apontando para `../../../_assets`), `<PRD>-<slug>.mp4` na raiz (gerado, fora do git) e `index.html` (a página, versionada). Isto substitui a decisão 3 do ADR 0044, que separava `percepcao/` e `divulgacao/`: a separação era por tipo de artefato, e o que o leitor procura é a entrega.

3. **O deploy copia só o que a página precisa.** A Vercel recebe `index.html`, o MP4, `.vercel/` e os dois assets de `_assets/`. A composição não sobe.

4. **Página de módulo é o caso especial, não a regra.** Quando um contexto quer uma vitrine com vários vídeos (hoje `ouvidoria/modulo/`), ela é só uma página que embute cópias git-ignored dos MP4s dos PRDs. Regerou o vídeo de um PRD, atualiza a cópia lá.

## Consequências

- O ADR 0026 (percepção em vídeo) continua valendo no que decide: composição versionada, MP4 fora do git, gate humano. Muda só o endereço.
- As quatro entregas existentes (317, 318, 210, 272) e a página da Ouvidoria foram movidas; nada foi regerado. A página do 272 passa a embutir `272-pendencia-nasce-na-assinatura.mp4` no lugar de `demonstracao.mp4`.
- A cópia local dos MP4s nas pastas antigas fica órfã na máquina de quem tinha; são regeráveis.
