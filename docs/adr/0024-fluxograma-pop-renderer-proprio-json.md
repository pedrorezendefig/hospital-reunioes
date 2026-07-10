---
status: accepted
amends: 0017
---

# Fluxograma de POP: o agente emite estrutura JSON e o app desenha o SVG

O ADR 0017 tornou o Fluxograma uma seção em sintaxe Mermaid: o agente emite `flowchart TD`, o mermaid.js desenha na tela e o SVG capturado no cliente é persistido com a Versão para o PDF embutir. A arquitetura entregou o pipeline certo, mas o desenho parou no tema de fábrica: nós todos iguais, sem hierarquia entre passo, decisão e terminal; losangos desproporcionais; roteamento do dagre; fonte genérica. Vestir o Mermaid no design system (themeVariables + classDef) foi prototipado e melhora bastante, mas esbarra no teto da biblioteca: formas, proporções e rotas continuam decisão do Mermaid, não do app.

A decisão: o Fluxograma passa a ser **estrutura, não sintaxe**. O agente emite a seção como **JSON de uma gramática restrita ao domínio**: sequência de passos, decisões com 2 ou mais ramos rotulados (default Sim e Não), retornos a passos anteriores e terminais de início e fim. Um renderer próprio do app desenha o SVG com as peças do design system (cards com badge numerado, decisões em âmbar, chips de ramo, terminais navy e verde, roteamento ortogonal em coluna principal com desvios laterais), num layout determinístico calculado em código, sem motor de layout externo. Paralelismo e raias por papel ficam fora da gramática; quando o procedimento os tiver, o texto da Descrição os cobre.

Tudo o que o 0017 decidiu de arquitetura permanece: render no cliente, captura do SVG persistida com a Versão, sanitização na entrada, PDF (WeasyPrint) embutindo o mesmo desenho, nenhum render fora do self-hosted.

O legado converte de uma vez: uma migração parseia o Mermaid persistido (as convenções do prompt eram um subset pequeno: terminais, passos, decisões binárias, retornos) para o JSON novo, e a dependência `mermaid` sai do frontend. PDFs assinados não mudam um byte (usam o SVG persistido); apenas a tela viva passa a desenhar no renderer novo. Conteúdo que não parsear mantém o fallback de texto bruto que já existia para sintaxe inválida.

## Por que é surpreendente

O 0017 escolheu Mermaid justamente porque "o LLM gera diagramas com naturalidade", e este ADR o remove pouco depois. O dado novo é que a naturalidade da sintaxe cobra caro na saída: o desenho tem teto visual baixo e a sintaxe livre produz erros de parse que a tela precisa tratar. Com uma gramática restrita, o JSON validado por schema é tão natural quanto para o agente (que já emite as demais seções em JSON), erra menos, e devolve ao app o controle total do desenho. Também surpreende um layout escrito à mão em vez de um motor: só é viável porque a gramática restrita faz do layout um problema fechado (coluna principal + desvios + retornos), não um grafo arbitrário.

## Alternativas descartadas

- **Vestir o Mermaid no design system (tema + classDef, opcionalmente layout ELK)**: 1 issue, ganho real da ordem de 80%, arquitetura intacta. Descartado porque o objetivo é o teto visual do documento oficial, e o teto do Mermaid são as suas formas e o seu roteamento. Essa rota não jogaria nada fora: as convenções por tipo de nó são as mesmas que o JSON formaliza.
- **React Flow (xyflow)**: interatividade de produto, mas nós em HTML quebram o caminho vetorial do PDF: raster borrado no A4, ou um segundo render só para impressão (a dupla manutenção que o 0017 já rejeitou). Só se justificaria se o Elaborador precisasse editar o diagrama arrastando nós.
- **Grafo livre com elkjs**: cobre topologias arbitrárias, mas troca a garantia de desenho sempre limpo por um motor de ~100KB e devolve ao agente a liberdade de gerar estruturas estranhas, o problema que o JSON veio resolver.
- **D2, Graphviz, serviços externos (Kroki, Mermaid Chart)**: peso de compilador WASM no cliente, estética datada, ou conteúdo de POP saindo do self-hosted (vetado desde o 0017).

## Consequências

- O `conteudo` da seção `fluxograma` deixa de ser string Mermaid e vira objeto JSON validado (pydantic no backend, types no frontend), eliminando escaping duplo no prompt.
- Novo componente de desenho substitui `FluxogramaMermaid.tsx`, reusando a barra de zoom/pan/export, a legenda e a captura de SVG existentes.
- O prompt da Elaboração troca as convenções Mermaid pela gramática JSON com exemplo.
- Migração converte o Mermaid persistido e remove a dependência `mermaid` (o bundle do frontend encolhe centenas de KB).
- Os números dos passos são referência visual do fluxo, sem promessa de correspondência com a numeração da Descrição do procedimento.
- Sombras aparecem na tela e são ignoradas pelo WeasyPrint no PDF, sem prejuízo de leitura.
