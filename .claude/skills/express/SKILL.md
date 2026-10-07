---
name: express
description: 'Grill rápido de uma ideia ou possibilidade ("dá pra fazer X?", "discute comigo Y", print de tela com uma vontade). Em vez de entrevista longa, faz uma rodada só: olha o código, diz o que já existe, propõe a ponte mínima, entrega uma decisão com no máximo 2 opções e uma recomendação. Quando o usuário diz "siga suas recomendações", implementa, verifica de verdade (navegador, teste, comando) e fecha com um resumo organizado por tema das questões que apareceram. Use quando o usuário disser "/express", "discute comigo a possibilidade de", "dá pra ter", "queria um link/botão/atalho que", "faz sentido X?", ou mandar um print e uma vontade. Não é o grill-with-docs (esse é longo, uma pergunta por vez, e não implementa).'
---

# Express grill

Grill de uma rodada. Termina em código, não em ata.

> **Idioma:** o do `CLAUDE.md` do projeto (default pt-BR). Sem travessão nem meia-risca.

## Fase 1: olhar antes de falar

Antes de responder qualquer coisa, procure no código o que a ideia precisa. Fatos vêm do repositório, não do usuário.

Procure três coisas:

1. **O que já existe** que faz metade do caminho (um campo já guardado, uma chave que os dois lados compartilham, uma página que já sabe abrir aquilo).
2. **O que falta**, a ponte mínima entre o que existe e o que o usuário quer.
3. **O que pode quebrar** (um filtro que esconde o alvo, uma rota que não existe sem servidor, um estado que não sobrevive à navegação).

Não pergunte o que dá para descobrir com `grep`.

## Fase 2: responder curto

Uma resposta só, nesta ordem:

- **Dá ou não dá**, na primeira linha. Se dá, diga se é barato.
- **O que já existe**, com `arquivo:linha` de cada peça.
- **Como seria a ponte**, em passos numerados. No máximo 5.
- **Uma decisão do usuário**, só se houver escolha de verdade. No máximo 2 opções, uma linha de contexto para cada, e qual você escolheria. Se não houver escolha, não invente uma.

Termine com uma pergunta só: "Quer que eu faça a A?".

Não implemente nada nesta fase.

## Fase 3: quando ele disser "siga"

"Siga suas recomendações", "faz a A", "vai" liberam a execução inteira. Não pergunte de novo.

1. Implemente a ponte mínima. Nada especulativo. Toque só o que a ideia pede.
2. **Verifique de verdade**, não por leitura. Se é tela, abra no navegador e clique. Se é comando, rode. Se é dado, olhe o arquivo gerado. Uma aba de navegador em segundo plano congela rolagem e animação; traga para a frente antes de julgar.
3. Se algo saiu diferente do esperado no teste, corrija e teste de novo antes de reportar.
4. Se o projeto tem página de Ajuda ou doc de uso e a mudança cria um botão, link ou gesto novo, acrescente uma linha lá.
5. Feche recursos que abriu (abas, servidores de teste).

## Fase 4: resumo por tema

Feche com um resumo organizado por **categoria de tema** das questões que apareceram no grill. Os temas nascem da conversa, não de um molde fixo. Exemplos de temas que costumam aparecer:

- **Dados**: o que já era guardado, o que precisou ser guardado a mais.
- **Navegação / ligação**: como um lado acha o outro.
- **Tela**: o que o usuário vê e clica.
- **Casos de borda**: filtro escondendo o alvo, alvo inexistente, estado perdido.
- **Verificação**: o que foi testado, como, e o que não foi.
- **Fora do escopo**: o que ficou de fora de propósito e por quê.

Regras do resumo:

- Cada tema: título em negrito e 1 a 3 frases, ou uma lista curta.
- Diga o que funcionou e o que não foi testado. Sem enfeite.
- Termine com "o que você faz agora": um ou dois comandos exatos, ou "nada".

## O que este skill não faz

- Não faz entrevista longa. Se a ideia precisa de 5 decisões encadeadas, diga isso e sugira `/grill-with-docs`.
- Não escreve ADR nem mexe em `CONTEXT.md` por conta própria. Se uma decisão merecer ADR, diga em uma linha e deixe o usuário pedir.
- Commit e PR saem pela Skill `ship`, sem perguntar: no Hospital Reuniões, depois do "siga" e da verificação, a entrega é a porta C do `/ask-pedro`, e o Pedro já disse que confia (06/10/2026). Chame a Skill tool com `ship` (argumentos `"<descrição>" --from-diff`), que abre o PR e roda o rabo; o "o que você faz agora" do resumo vira o resultado do ship. Única parada: se a ponte mudou comportamento do app que alguém precisa conferir antes, diga que é porta B e pare na proposta da issue.
