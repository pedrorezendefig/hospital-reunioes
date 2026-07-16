---
status: accepted
---

# Dashboard desenha os diagramas com renderer próprio; mermaid.js sai do painel

A aba Mapa do workflow-dashboard renderizava os diagramas dos snapshots com mermaid.js carregado de CDN: o ER do `SCHEMA.md` (auto-gerado pelo `/snapshot`) e os 5 diagramas curados do `FLUXOGRAMAS.md` (2 máquinas de estado, 2 sequências, 1 flowchart). O resultado era o pior dos dois mundos: offline nada renderiza (fica o código cru), e online o Mermaid espalha as ~19 tabelas num grafo genérico ilegível, sem hierarquia, sem interação, encolhido na caixa.

A decisão: o dashboard passa a desenhar os diagramas com **renderers próprios em SVG**, e o mermaid.js sai do painel por completo. A mesma filosofia do ADR 0024 (estrutura, não sintaxe), aplicada à ferramenta: quem manda no desenho é o app, não a biblioteca.

Os `.md` dos snapshots **continuam em Mermaid**, porque renderizam nativo no GitHub e no GitHub Mobile; eles seguem como única fonte de verdade. Quem extrai a estrutura é o `collect.py`: parseia os subsets de linha usados (relações `A ||--o{ B` e blocos de tabela do `erDiagram`; transições `A --> B: rótulo` do `stateDiagram-v2`; mensagens `A->>B: texto` do `sequenceDiagram`; nós e arestas do `flowchart`) e entrega JSON estruturado no `/api/data`, com testes em `tools/workflow-dashboard/tests`. Bloco que não parsear (ou tipo desconhecido) cai no fallback de código cru que já existia.

O desenho, por família:

- **ER**: clusters por domínio (Pessoas, Reuniões, POPs, Infra) em layout determinístico, mapeamento tabela para cluster curado num dict no código com fallback "outras". Hover numa tabela acende as FKs dela com traço animado e esmaece o resto; clique expande as colunas completas; zoom/pan com botão de ajustar. O ER interativo vira a capa da aba Mapa, com as pills de documento abaixo.
- **Máquinas de estado e flowchart**: espinha do caminho feliz na vertical, desvios (ERRO, CORRIGINDO, ATRASADO, REPACTUADA) pendurados na lateral, retornos em curva. Layout fechado calculado em código, sem motor de grafo, viável porque os diagramas curados são ciclos de vida com happy path claro.
- **Sequência**: colunas de participantes + linhas de mensagem (layout trivialmente determinístico), com botão de play que percorre as mensagens em ordem descendo as lifelines.

Toda animação respeita o `reduceMotion` já existente no painel.

## Por que é surpreendente

Um leitor futuro vai perguntar por que o `collect.py` parseia Mermaid na mão se o mermaid.js existe e os arquivos já estão nessa sintaxe. A resposta é o teto visual e a dependência: o Mermaid decide formas, rotas e escala (e decide mal para 19 tabelas), e o painel local de trabalho dependia de CDN para a sua aba mais visual. Como o ER é gerado por máquina numa gramática fixa e os diagramas curados usam subsets pequenos e estáveis, o parse é um problema fechado e barato, não um parser de Mermaid geral.

## Alternativas descartadas

- **Vestir o mermaid.js no design system (theme + classDef) e vendorizar o script**: resolveria offline e melhoraria a estética, mas formas, proporções e roteamento continuariam decisão da biblioteca, exatamente o teto que o ADR 0024 já mediu no produto.
- **Inverter a fonte (FLUXOGRAMAS curado em JSON, Mermaid gerado para o GitHub)**: mais fiel ao 0024, porém muda o formato de curadoria humana e exige um gerador extra; o ganho não paga o custo numa ferramenta read-only.
- **Parsear no browser (JS)**: zero mudança no backend, mas lógica de parse sem teste unitário decente e misturada com render.
- **Motor de layout genérico (dagre/elk caseiro ou vendorizado)**: aguentaria grafos arbitrários que o painel não tem; os diagramas reais têm estrutura conhecida (clusters, happy path, lifelines) que layouts fechados desenham sempre limpo.

## Consequências

- `loadMermaid`/`mermaidify` e a dependência de CDN saem do `app.js`; o painel volta a funcionar 100% offline.
- `collect.py` ganha um módulo de parse de diagramas com testes; o `/api/data` passa a servir a estrutura junto dos snapshots.
- Tabela nova no schema aparece no cluster "outras" até alguém curar o dict de domínios.
- Mudança nos diagramas curados que sair dos subsets parseados degrada para código cru no painel (nunca quebra), e continua bonita no GitHub.
