---
status: accepted
supersedes: 0075
amends: 0050, 0054, 0056, 0069, 0076
amended_by: 0078, 0079, 0083, 0084, 0090
---

# Tecnologia vira o chat do agente: bug ou melhoria, com Opus lendo o código, e o card nasce no GitHub

Decisão do Pedro (02/11/2026, grill fechado pelo `/express` e aprovado no terminal). A aba Tecnologia cresceu para um gestor de tarefas entre o hospital e a Vitta: sete tipos, Produto com dono, Responsável, Prioridade, Prazo, três raias, Painel, Conversa espelhada, e-mail, e por cima o Assistente de entrada e o Planejamento da Demanda (ADR 0075, em produção desde os PRs #1354 a #1361). Quem usa é o diretor, e o que ele faz de verdade é relatar um bug ou pedir uma melhoria. Esta ADR reduz a aba a isso: uma tela, o chat do agente, que conduz a conversa como o Pedro conduz o `/grill-with-docs` no terminal e termina num card no GitHub, sem ninguém da Vitta precisar assumir.

## Decisões

1. **A aba é uma tela só: o chat do agente**, com uma lista lateral das conversas passadas e a Etapa de cada uma lida do GitHub. Saem Quadro, Painel, os sete Tipos, Produto com dono, Responsável, Prioridade, Prazo, Estado, Conversa espelhada, menções, e-mail, formulário à mão e Vínculo por número. Ficam a Etapa derivada (webhook do GitHub), o Anexo e o Kit. Quem vê continua sendo só o Super admin (ADR 0050). Rejeitado: esconder o antigo atrás de um "modo antigo" (código vivo sem uso).

2. **A Demanda continua no banco como o registro de cada conversa**, sem os campos que saíram. Para o diretor ela é só uma linha na lista. Assim o planejamento persistido (migration 123), o Anexo, o Vínculo e a Etapa servem sem tabela nova. As Demandas abertas hoje o Pedro resolve com o diretor antes da subida; as colunas aposentadas ficam congeladas e o drop vem em PR posterior. Rejeitado: tabela nova de conversas (refaz o que a Demanda já carrega).

3. **Só um sentido: o diretor relata à Vitta.** Os pedidos da Vitta ao hospital (os antigos Decisão, Informação e Terceiro) voltam para o WhatsApp. Emenda a ADR 0050, que fez a aba nos dois sentidos. Risco aceito: metade da conversa que a aba tirou do WhatsApp volta para lá.

4. **O agente abre perguntando "bug ou melhoria?"**, com dois botões e um campo livre; se o diretor só descreve, ele classifica e confirma. Dúvida que o Kit responde é respondida ali, sem card. **Bug** segue um roteiro curto, uma pergunta por vez, no máximo cinco: onde, o que aconteceu, o que esperava, como repetir, o print. **Melhoria** segue o grill do terminal: uma pergunta por vez, contexto curto, duas opções com a recomendada destacada, campo livre, texto ou voz, teto de 12 perguntas e "Fechar e resumir" sempre à mão; o que não foi perguntado vira "ficou em aberto". Texto, voz e imagem entram em qualquer ponto. Substitui a ADR 0075 (o planejamento deixa de ser um botão no card de uma Demanda já criada e vira o caminho da melhoria dentro do chat).

5. **O agente lê o código.** Além do Kit, ele ganha ferramentas de leitura do repositório pela API do GitHub (ler arquivo, buscar no código, abrir `CONTEXT.md` e as ADRs aceitas, listar issues abertas). Fala com o diretor na língua do Kit e desafia o pedido contra o código e as ADRs por trás, como o terminal faz. Não roda teste, não sobe stack e não grava no repositório. Emenda a ADR 0056, que limitava o agente ao Kit. Rejeitado: só o Kit (conversa bem, mas não desafia contra o que está decidido); agente gerenciado com o repositório clonado num sandbox (infraestrutura e custo para rodar código, que um grill não precisa).

6. **O card só nasce no clique "Criar o card"**, depois do resumo; "Não bateu" volta à conversa. Antes de criar, o agente lista as issues abertas e avisa quando já existe uma parecida, e a peneira pública que já existe passa no texto. Rejeitado: criar sozinho no fim da conversa (card errado no repositório público sem ninguém ter lido).

7. **O que o card leva.** Bug: issue única `type:bug` com Onde, O que aconteceu, O que esperava, Como repetir e critérios de aceite, nascendo `ready-for-agent`, e a onda pega sozinho. Melhoria: o PRD inteiro, a metade de negócio da conversa e as Decisões de implementação e de teste lidas do código, mais uma seção "Para o glossário" com os termos e as decisões candidatas a ADR; nasce `needs-triage`, porque ainda passa pelo `/to-issues`, e quem grava `CONTEXT.md` e ADR é o terminal (o backend não faz commit na `main` protegida). Emenda a decisão 1 da ADR 0054. Risco aceito: um bug relatado pelo diretor chega a produção sem um humano ler a issue.

8. **O print fica no app** (ADR 0069): a issue diz "Anexos: N imagens" e a rota de automação entrega a imagem ao agente que pega a issue. Sem o "Concluir" humano, o binário é apagado 30 dias depois de Em produção ou quando a issue fecha como Não será feita. Emenda a ADR 0069 no gatilho de apagar.

9. **Modelo e custo.** A conversa inteira da tela roda no Opus 5.5 pela variável que já existe, `llm_model_planejamento`; o resto do app segue no Sonnet 5.5 (ADR 0074). `cache_control` no prefixo fixo, tokens e custo gravados por chamada, fora da tela do diretor. Falha do provedor é erro claro, conversa intacta, sem failover. A leitura de código encarece a sessão (estimativa de uns US$ 0,50 a mais); o custo gravado diz o número real.

10. **Manual e Kit.** O módulo Tecnologia do Manual (ADR 0076, decisão 5) é reescrito numa Fatia de manual do PRD, com o vídeo refeito (ADR 0076, decisão 4). O Kit `tecnologia.md` é reescrito no mesmo PR da tela. Emenda a decisão 5 da ADR 0076 no conteúdo, não na regra.

11. **Ordem.** Primeiro a tela nova no ar; a remoção do código antigo vem numa fatia própria, depois, para o diretor nunca ficar sem canal.

## Consequências

- O glossário da Tecnologia é reescrito: Demanda redefinida, Assistente de Tecnologia vira o chat inteiro, Roteiro do bug nasce, e Tipo, Produto com dono, Estado, Quadro, Painel, Conversa da Demanda e Roteiro por Tipo se aposentam.
- O agente precisa de ferramentas (tool use) no backend, primeira vez no app, com teto de chamadas por turno.
- O `/minhas-issues` e o `/grill-with-docs` deixam de precisar distinguir o "PRD do diretor" pela metade: o card de melhoria já vem com o PRD inteiro.
