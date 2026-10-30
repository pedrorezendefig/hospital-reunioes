---
status: accepted
amends: 0070
---

# Contas médicas: IA na API da Anthropic, com a retenção padrão e sem ZDR

A decisão 9 da ADR 0070 pôs a IA do módulo no OpenRouter e mandou toda requisição com `provider.zdr: true` e `data_collection: "deny"`, para que o prontuário desidentificado só fosse a provedor sem retenção. Em 30/10/2026 o crédito do OpenRouter acabou, a fila parou com `402 Payment Required` em todas as chamadas, e o Pedro decidiu tirar a IA de texto do OpenRouter (issue #1302).

Decisão do Pedro (30/10/2026):

1. **A IA de texto do app vai para a API da Anthropic**, toda no `claude-sonnet-5-5`, com a chave da org do Pedro e o crédito mensal dela. Isso vale para Contas médicas (Passo A, Passo B e o resto de `contas_medicas/ia.py`), para Atas, POP e Ouvidoria (`ai_processor.py`) e para o assistente de Tecnologia. A transcrição de áudio fica no OpenRouter, porque a API da Anthropic não transcreve.
2. **Sem ZDR.** Vale a retenção padrão da API da Anthropic: o que o app envia e o que a IA responde fica guardado por até 30 dias, para controle de abuso, e não é usado para treino. O Pedro decidiu não pedir ZDR à Anthropic. O módulo continua obrigado a desidentificar antes de enviar (decisão 8 da ADR 0070), e é isso que limita o que chega à Anthropic: rótulo e idade, nunca nome, CPF ou carteira.
3. **O resto da decisão 9 continua**, agora no SDK `anthropic`: saída estruturada validada por Pydantic, instrução e memória da operadora em bloco com `cache_control`, tokens e custo gravados por chamada. Como a Anthropic não devolve o custo pronto, o custo sai dos tokens com uma tabela de preço no código. A única mudança nas tentativas é a falta de crédito, que deixa de ser repetida e vai direto para Erro com uma frase que diz o que fazer.

## Consequências

- Até 30 dias de retenção do texto desidentificado de prontuário fora do hospital. Se o diretor ou o jurídico pedirem retenção zero, o caminho é pedir ZDR à Anthropic, sem mudar código.
- Registrar a Anthropic como operadora de dados continua sendo decisão do diretor com o jurídico, como a ADR 0070 já dizia para o provedor anterior.
- Um fornecedor e um saldo para toda a IA de texto. O OpenRouter fica só com o áudio e precisa de crédito próprio para a transcrição das Atas.
