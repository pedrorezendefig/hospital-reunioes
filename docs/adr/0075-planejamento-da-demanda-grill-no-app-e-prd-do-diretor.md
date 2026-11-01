---
status: accepted
amends: 0054, 0056
---

# Planejamento da Demanda: o grill de negócio roda no app, e o "sim" do diretor cria o PRD do diretor

Decisão do Pedro (01/11/2026, grilling fechado em lote pelo `/express` e aprovado no painel). O planejamento de uma melhoria hoje é todo no terminal: o Pedro roda o `/grill-with-docs`, responde pelo diretor o que é de negócio, e só depois o PRD chega à aba Tecnologia pelo Vínculo. Esta ADR leva a metade de negócio desse grill para dentro do app, na mão do diretor, e deixa no terminal só o que depende de código.

## Contexto

- O Assistente de Tecnologia (ADR 0056) já é um chat sem estado na API da Anthropic, com rascunho vivo, kit de conhecimento embarcado e nada gravado até o clique. O botão "Levar para desenvolvimento" (ADR 0054) já cria a issue-raiz com o bloco "Para o diretor", o marcador e o tipo mapeado.
- O grill do terminal tem duas metades. A de negócio (problema, quem usa, regras, o que fica de fora, o que é "pronto") o diretor decide melhor que o Pedro. A técnica (módulo, seam, schema, teste) exige o repositório, que o backend em produção não tem.
- A ADR 0054, decisão 1, rejeitou "só criação pelo app" dizendo que "o grilling continua sendo a porta de qualidade do PRD". A ADR 0056, decisão 4, fez toda conversa do assistente efêmera. As duas dizem o contrário do que este plano faz.
- Custo medido no catálogo de 01/11/2026 (Opus 5.5: US$ 4 entrada, US$ 20 saída, US$ 0,20 leitura de cache por milhão de tokens): um planejamento de 15 perguntas com o prefixo fixo em cache sai por volta de US$ 1,50; sem cache, por volta de US$ 3. Custo não é o critério; o desenho é.

## Decisões

1. **O que sai é o PRD do diretor**, não o PRD inteiro. Bloco "Para o diretor", Problema, Solução, Histórias de usuário e Decisões de negócio, mais a seção "Ficou em aberto" com o que o grill não perguntou. As seções técnicas (Decisões de implementação e de teste) continuam nascendo no terminal: `/grill-with-docs #N` lê a issue, pula o que o diretor decidiu, pergunta só o técnico, e o `/to-prd` completa a mesma issue, sem criar outra. Emenda a decisão 1 da ADR 0054: o app passa a criar PRD, mas só a metade que o diretor decide; a porta de qualidade do técnico continua no terminal. Rejeitado: o PRD inteiro com o modelo chutando as decisões técnicas a partir do kit (inventaria módulo e seam sem ver o código).

2. **O planejamento começa numa Demanda que já existe**, pelo botão "Planejar com a IA" no card aberto de uma Demanda de tipo Novo ou Ajuste ainda sem Vínculo. O agente parte do título e da descrição já registrados no Roteiro por Tipo. Rejeitado: emendar o grill na conversa do assistente de "Nova Demanda" (puxa o diretor para 15 perguntas quando ele só queria registrar).

3. **A conversa do planejamento persiste na Demanda**, um planejamento por Demanda, retomável de onde parou, e segue a regra de vida do Anexo (ADR 0069): some quando a Demanda chega a Concluída ou Cancelada. Emenda a decisão 4 da ADR 0056 só para este modo; a conversa do assistente de entrada continua efêmera. Rejeitado: efêmera (um grill longo com o diretor interrompido perde 10 respostas ao fechar a aba).

4. **O agente conhece a casa só pelo kit**, e cada arquivo de Produto ganha uma seção "O que já foi decidido", em linguagem de diretor, mantida pela mesma regra de sincronia do kit (mudou o módulo, muda o kit no mesmo PR). É com ela que o agente desafia o pedido. Rejeitado de novo: ADRs peneiradas por script no deploy (ADR 0056: um filtro em que ninguém confia).

5. **Quem decide o fim é o modelo, com teto de 12 perguntas**, e o diretor tem sempre o botão "Fechar e resumir". O que não foi perguntado sai no resumo como "ficou em aberto", nunca como decisão inventada (mesmo princípio do Roteiro por Tipo). Cada pergunta traz uma ou duas frases de contexto, duas opções clicáveis com a recomendada destacada e um campo livre. O diretor responde por texto ou voz; imagem continua entrando pelo Anexo da Demanda. Rejeitado: roteiro fixo de perguntas por tipo (pergunta o que o diretor já respondeu na descrição); imagem no chat do planejamento.

6. **O "sim" do resumo cria a issue pelo mesmo caminho do "Levar para desenvolvimento"** (`needs-triage`, `type:feature`, marcador, bloco "Para o diretor"), com o PRD do diretor no corpo. Sem label nova: o marcador e a seção "Ficou em aberto" já dizem de onde a issue veio. O "não" abre um campo "o que não bateu", devolve a resposta à conversa e o resumo é refeito. Rejeitado: label `planejado-no-app` (uma label a mais para manter); editar o resumo à mão (descola o resumo da conversa que o justifica).

7. **Modelo e custo.** O planejamento roda no `claude-opus-5-5`, por uma variável própria (`LLM_MODEL_PLANEJAMENTO`), com o effort padrão; o resto da IA de texto fica no `claude-sonnet-5-5` (ADR 0074). O bloco fixo do prompt (instrução de sistema mais kit) vai com `cache_control`, primeira vez no assistente; o acerto se confere por `cache_read_input_tokens`. Tokens e custo são gravados por chamada, no molde de Contas médicas (ADR 0074, decisão 3), e nunca aparecem na tela do diretor. Falha do provedor é erro claro com a conversa intacta, sem failover. Rejeitado: Opus em tudo (dobra o custo do volume de Contas médicas sem ganho medido); failover para Sonnet (troca o julgamento no meio do grill).

8. **O que não muda.** Qualquer Super admin da aba pode planejar, sem papel novo (ADR 0050). O card fechado não ganha selo; no card aberto o botão vira "Continuar planejamento" quando há conversa e some quando há Vínculo. O teto de taxa é o dos outros chats. Tecnologia continua fora do Manual (ADR 0057): o que o agente faz está no kit `tecnologia.md`.

## Consequências

- O glossário ganha Planejamento da Demanda e PRD do diretor; o Kit de conhecimento ganha a seção "O que já foi decidido" por Produto, que é uma rodada de escrita nos 10 arquivos e entra como fatia do PRD.
- Nasce persistência nova no app (a conversa do planejamento na Demanda), portanto migration e parada humana da regra 9 da ADR 0068.
- O `/grill-with-docs` precisa aprender a ler uma issue com PRD do diretor e pular o que já foi decidido; o `/to-prd`, a completar uma issue em vez de criar. O `/minhas-issues` precisa distinguir uma `needs-triage` com PRD do diretor de uma comum (é o risco aceito da decisão 6).
- Risco aceito da decisão 7: se as perguntas saírem rasas no effort padrão, o ajuste é subir para `high`, não trocar de modelo.
