---
status: accepted
amended_by: 0024
---

# Fluxograma de POP em Mermaid: interativo na tela, SVG no PDF

O Fluxograma do POP era texto estruturado (linhas numeradas; decisão escrita como `Pergunta? Sim: ação. Não: ação.`) convertido por um parser determinístico em nós e renderizado como **CSS puro** no PDF via WeasyPrint. Essa escolha (PRD #76) veio do fato de o WeasyPrint não rodar JavaScript. O preview na tela nem chegava a renderizar o fluxograma. O dono quer um fluxograma rico: bonito, com zoom, preview e download em PNG ou SVG com legenda. E o LLM gera diagramas com naturalidade.

A decisão: o Fluxograma passa a ser **Mermaid**. O agente emite sintaxe Mermaid na seção de fluxograma. Na tela, o `mermaid.js` renderiza com zoom e pan e oferece export em PNG e SVG (preview e download). No PDF, como o WeasyPrint não roda JS, embute-se o **SVG que o `mermaid.js` já rendeu no cliente**: o SVG é capturado no frontend e persistido com a Versão, e o template do PDF o embute (o WeasyPrint suporta SVG). Não entra Chromium nem headless no backend, e nenhum serviço externo de render, para o conteúdo de POP não sair do ambiente self-hosted, coerente com a postura de privacidade. Se o agente emitir Mermaid inválido, a tela cai num fallback (texto bruto e opção de regerar) sem quebrar a Versão.

## Por que é surpreendente

Um dev encontra uma biblioteca de diagrama em JavaScript no meio de um pipeline de PDF deliberadamente sem JS (WeasyPrint), e um SVG que viaja do frontend para o backend. Sem este registro parece inversão de arquitetura. O ponto é que o render acontece onde existe JS (o cliente) e o backend apenas embute o SVG pronto.

## Alternativas descartadas

- **Manter texto e CSS puro (PRD #76)**: consistente e leve, mas limitado a fluxo linear com decisão simples, sem interatividade, zoom ou export. Não entrega o "rico" pedido.
- **Mermaid na tela e CSS no PDF**: evita a captura de SVG, mas a tela e o PDF divergem (o download não bate com o preview) e dobra a manutenção.
- **Render no servidor com mermaid-cli ou Chromium headless**: server-authoritative, mas adiciona Chromium pesado à imagem do backend. A captura no cliente entrega o mesmo SVG sem esse peso.
- **Serviço externo (por exemplo kroki.io)**: trivial, mas manda conteúdo de POP para fora do self-hosted. Descartado por privacidade.

## Consequências

- Nova dependência `mermaid` no frontend, mais um wrapper de zoom e pan e o export PNG/SVG.
- Caminho de captura do SVG no cliente e persistência do SVG com a Versão, com re-captura quando o fluxograma muda.
- O template do PDF passa a embutir o SVG no lugar dos nós CSS; saem o parser determinístico e o CSS de fluxograma.
- Fallback para Mermaid inválido.
- Reverte a decisão de render do fluxograma do PRD #76.
