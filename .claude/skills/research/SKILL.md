---
name: research
description: Investiga uma dúvida factual em fontes primárias (docs oficiais, código, specs) com agente em background e responde citado na Issue/PRD. Use em "pesquisa isso", "confirma na fonte".
---

# Research

Dispare um **background agent** (Agent tool) para fazer a leitura, e continue trabalhando enquanto ele lê. Research é legwork que se delega, não pensamento que se terceiriza.

O trabalho do agente:

1. Investigar a pergunta contra **primary sources**: docs oficiais, código fonte, specs, APIs first-party. Nunca resenha de terceiros. Siga cada afirmação até a fonte que a possui.
2. Fetchers preferidos, nesta ordem: `context7` (query-docs) para docs de bibliotecas; `WebFetch` ou `firecrawl-scrape` para docs oficiais fora do context7.
3. Escrever as descobertas num único Markdown, citando a fonte primária de cada claim (URL ou path de código). Rascunho no scratchpad da sessão.
4. **Destino**: comentário na GitHub Issue ou PRD relacionado, via `gh issue comment <N> --body-file <rascunho>`. O trabalho vive nas Issues (regra do `CLAUDE.md`): **nunca** crie pasta nova de notas no repo. Sem issue relacionada, entregue o resultado no chat e deixe o rascunho no scratchpad.

## Divisão de trabalho

- `/research`: fatos de docs oficiais e código fonte durante o desenvolvimento (comportamento de API, o que a spec diz).
- `deep-research`: investigação web ampla, multi-fonte, com verificação adversarial e relatório citado.
- `firecrawl-scrape`: captura bruta de páginas (URL para markdown), sem loop de investigação.

## Limites

Não use para decisões de domínio: decisões continuam no grilling com o humano e nas ADRs. Facts são pesquisáveis; decisions são do usuário.
