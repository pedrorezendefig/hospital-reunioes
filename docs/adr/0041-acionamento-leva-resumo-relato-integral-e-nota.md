---
status: accepted
amends: 0039
---

> Revoga a proibição do glossário de mandar o relato ou o resumo por email ao setor (verbete Extrato para o setor) e **emenda a decisão 2 do ADR 0039**: `resumo` e `relato_integral` entram na lista fechada `_CAMPOS_DO_EMAIL`, por decisão explícita da Diretoria (RN-78), exatamente pelo mecanismo que aquela decisão exige. O extrato continua obrigatório; o que cai é a exclusividade dele. A decisão 5 do 0039 é emendada à parte, pelo ADR 0042.

# O acionamento leva resumo, relato integral e nota da ouvidoria

Até aqui, o responsável de setor lia apenas o Extrato para o setor: o texto que o ouvidor escreve com as próprias palavras na validação. A regra existia para proteger a palavra do manifestante (nome, leito, detalhes) de viajar por email, superfície que encaminha e vaza.

O diagnóstico da Diretoria Executiva de 31/08/2026 (RN-78, RN-60) determinou o contrário, com fundamento operacional: quem lê só a interpretação da Ouvidoria responde à interpretação, não ao paciente. O resumo permite decidir em segundos se o caso é da área; o relato integral é o que permite responder ao manifestante; a nota separada evita que a área responda ao intermediário. A Diretoria conhece o risco do email e o aceitou; a decisão foi seguir a RN-78 integralmente.

## Decisões

1. **Três blocos, nos dois lugares.** O email de acionamento e a tela do responsável (`/ouvidoria-setor/{token}`) apresentam, nesta ordem e visualmente separados: RESUMO, RELATO INTEGRAL e NOTA DA OUVIDORIA (o Extrato para o setor). Os blocos nunca são fundidos nem formatados iguais (RN-60).

2. **O extrato continua obrigatório.** A validação segue recusada sem ele. O que muda é a companhia: ele deixa de ser o único conteúdo.

3. **Sigilo reforçado é a exceção (RN-79).** Caso sigiloso não leva identificação do manifestante em email nem na tela do token, e o relato integral é substituído pelo extrato. Vale nos dois lugares, sem exceção. **Ver a emenda de 01/09/2026 abaixo: a exceção é mais larga do que esta frase, e o código a aplica assim.**

4. **O reenvio manda os mesmos três blocos** gravados no caso, para provar o que a área recebeu.

## Emenda de 01/09/2026: o alcance real da exceção (issue #481)

A decisão 3 fala de sigilo reforçado e do relato integral. Quando a issue #481 implementou os três blocos, dois testes que já existiam no repositório (`TestExtratoParaOSetor`, decisão de 25/08/2026) mostraram que a frase era estreita demais para o que o próprio módulo já protegia. O código entregue faz o seguinte, e esta emenda registra isso de forma factual, para que ninguém leia a decisão 3 ao pé da letra e reabra o buraco:

1. **O caso anônimo recebe a mesma proteção do sigiloso.** Quem escolheu não se identificar costuma se identificar dentro do próprio texto ("sou a Maria Silva, do leito 302"). Mandar esse texto ao setor desfaria o anonimato que o canal prometeu. É a mesma porta por onde `_identificacao` já tratava os dois casos igual desde o ADR 0034, decisão 8.

2. **Na exceção, o resumo é cortado junto com o relato.** O resumo não é texto da Ouvidoria: no canal aberto são os primeiros caracteres do que o cidadão digitou, e no canal da Ana é texto gerado da conversa. Os dois carregam nome e leito. Mantê-lo entregaria justamente a identificação que a mesma frase da RN-79 manda tirar.

3. **Na exceção não há bloco de relato repetindo o extrato.** O extrato já é a nota da ouvidoria, e duas caixas com o mesmo texto seriam ruído na tela e no email. O que a área lê no lugar do relato é a nota, e um aviso explícito diz por que o resto do caso não veio (um texto para o sigilo, outro para o anonimato). Quem distingue as variantes lê a chave de cada bloco, nunca a posição.

### Questão aberta, pendente de ratificação da Diretoria

O item 1 tem um efeito que **não foi decidido por ninguém e não está ratificado**: hoje **todo caso anônimo** chega à área só com a nota da ouvidoria, o que estreita a RN-78 para uma classe inteira de casos, e o canal aberto produz muito caso anônimo. As duas saídas possíveis são deixar como está (o anonimato pesa mais que a RN-78) ou mandar resumo e relato de caso anônimo depois de uma pseudonimização, que hoje não existe nesse caminho. **A escolha é do diretor**, e até ela acontecer vale o comportamento descrito acima, que é o conservador. Quando a decisão vier, ela emenda este bloco.

## Consequências

- O relato do manifestante, em caso não sigiloso, passa a viajar por email, e email do sistema é entregue por processador externo com infraestrutura fora do Brasil (ADR 0039). Risco conhecido e aceito pela Diretoria; a mitigação permanente é o sigilo reforçado subir sempre que o tipo ou o ouvidor pedirem, e o aviso de privacidade do hospital (que o 0039 alimenta) deve refletir a mudança.
- O verbete Extrato para o setor do CONTEXT.md foi reescrito nesta data.
- A tela do responsável é reorganizada na ordem da RN-59, com o relato integral aberto por padrão.
- Pela emenda acima, o acionamento de caso anônimo sai só com a nota da ouvidoria enquanto a Diretoria não ratificar o alcance da RN-78 nesses casos.
