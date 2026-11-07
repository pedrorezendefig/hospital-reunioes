---
name: express
description: 'Fecha um grill em andamento em lote, com painel de aprovação. No meio de um `/grill-with-docs`, a pessoa diz "/express" e o agente responde todas as perguntas que faltam com a própria recomendação, entrega a tabela decisão por decisão (escolha, por quê, a outra opção) no terminal e num painel interativo publicado como Artifact (Concordo ou Discordo por linha, nota, botão de aprovar), e espera a aprovação antes de classificar a porta e chamar `/to-prd`. Use quando o usuário disser "/express", "fecha o grill com as suas recomendações", "responde o resto você e me mostra a tabela", "segue com todas as recomendações e me pede aprovação". Não implementa nada e não chama `/ship`: o grill de uma rodada que implementava a ponte mínima morreu em 01/11/2026 (ideia pequena vai para `/grill-with-docs --lote`).'
---

# Express: fechar o grill em lote, com painel

O `/grill-with-docs` pergunta uma coisa por vez. O `/express` é o atalho para quando a pessoa já viu o rumo e quer o resto fechado com a recomendação do agente, revisado numa tela só, e aprovado em um clique.

> **Idioma:** o do `CLAUDE.md` do projeto (default pt-BR). Sem travessão nem meia-risca, no terminal e no painel.

> **Projeto:** `<leitor>` é o `leitor` de `python3 .claude/skills/onda-enxuta/scripts/fluxo.py leitor`. O que `fluxo.py notas express` imprimir vale por cima desta skill.

## Quando entra

- No meio de um `/grill-with-docs`, depois de uma ou mais perguntas respondidas. As respostas que a pessoa já deu valem como dadas; o `/express` fecha só o que falta.
- Sem grill em andamento, o `/express` faz o levantamento de fatos e o lote inteiro (é o `/grill-with-docs --lote` com o painel no fim).

## Fase 1: fechar o lote

As regras são as do modo lote do `grill-with-docs` (seção "Modo lote"). O que importa aqui:

1. **Fatos vêm do código, não da pessoa.** Antes de decidir, procure o que já existe (`CONTEXT.md`, ADRs aceitas, `history.json`, o serviço ou a tela que a ideia toca). Dúvida de serviço externo vai para o `/research` em background.
2. **Liste todas as lacunas**, numeradas na mesma sequência do grill (se a pessoa respondeu P1 a P5, o lote começa em P6), agrupadas por tema. Cada lacuna: a escolha, o porquê em uma ou duas frases, e a alternativa descartada com o que ela custaria.
3. **Não chute preferência de negócio, o que <leitor> quer, dinheiro nem texto com a voz de quem assina.** Essas linhas saem marcadas "[precisa de você]", com no máximo uma sugestão de rascunho.
4. As decisões que a pessoa já tomou entram na tabela marcadas "você escolheu", para o painel mostrar o conjunto inteiro.
5. Classifique a porta (A, B ou C) como uma das decisões, com o motivo.

## Fase 2: a tabela no terminal

Uma tabela `# | decisão | escolha | por quê`, agrupada por tema, seguida de:

- "Onde eu mais posso estar errado:" com as 2 escolhas mais arriscadas e o porquê.
- A porta recomendada e o comando que vem depois.
- O link do painel (Fase 3) e a frase: aprovar no painel ou responder "ok" / "N: correção" aqui.

## Fase 3: o painel (Artifact)

O painel é a mesma tabela, em HTML interativo, publicada pela ferramenta `Artifact` com as capacidades `db` e `user`. O molde está em `references/painel.html` (o do grill do agente de planejamento, 01/11/2026): copie a estrutura e troque só o `<title>`, a frase de abertura, a constante `DECISOES` e o texto do rodapé (porta e próximo comando).

O que o painel tem, e por quê (visão ampla: o Pedro pediu em 01/11/2026 "ver tudo de uma vez, em miniatura", e não questão por questão):

- **Cabeçalho fixo** com o nome do plano, o placar ("N de M avaliadas", barra) e o botão **"Concordar com tudo"**, que marca só o que ainda não foi avaliado e nunca mexe num Discordo.
- **Uma faixa por tema** com o nome, "N de M" e o botão **"Concordar com o tema"**.
- **Grade de miniaturas** (3 a 4 por linha no desktop, 2 no celular): número, "você escolheu" quando a pessoa respondeu no terminal, chip "risco" nas duas arriscadas, título e a escolha inteira (sem reticências: o Pedro quer ler a decisão sem abrir o card). A borda esquerda diz o estado (verde aceita, vermelha em revisão). O painel inteiro cabe em uma ou duas telas.
- **Gaveta lateral** ao clicar na miniatura: escolha destacada, por quê, a outra opção, "onde posso estar errado", Concordo / Discordo, campo "O que não bateu?" com "Guardar nota", e anterior / próxima para percorrer sem fechar. Esc fecha.
- **Rodapé** com a porta recomendada, o próximo comando e dois botões: "Aprovar e seguir para o PRD" e "Mandar para revisão".
- **Sem agente dentro da tela.** A capacidade `sample` permitiria um chat na página, mas ele não lê o repositório nem a conversa; quem responde pergunta é o terminal. Fica fora até fazer falta.

Onde o painel guarda o que a pessoa marca (coleções do `db`):

- `respostas/<pN>`: `{resposta: "ok" | "nao", nota, at}`.
- `aprovacao/final`: `{status: "aprovado" | "revisar", at, avaliadas}`.

Antes de escrever o HTML, carregue as skills `artifact-design` e `artifact-capabilities` (regra da ferramenta). Depois do primeiro publish, uma leitura com `ArtifactData` (`list` em `respostas`) prova que o armazenamento responde; diga em uma linha o que foi exercitado. O artefato nasce privado; quem está no grill é o dono e o único que escreve.

## Fase 4: a aprovação

Espere. A aprovação chega por um dos dois caminhos, e os dois valem igual:

- **No terminal:** "ok" aceita tudo; "N: correção" corrige só aquela linha.
- **No painel:** leia `aprovacao/final` e `respostas` com `ArtifactData` quando a pessoa disser que marcou (ou "lê o painel"). `status: "aprovado"` é o "ok"; cada `respostas/<pN>` com `resposta: "nao"` é um "N: correção" com a nota como texto da correção.

Com correções: reajuste as decisões que dependem delas, mostre no terminal só as linhas que mudaram, republique o painel com as linhas novas (mesmo `file_path`, mesma URL) e espere de novo.

Com o "ok" (ou `aprovado`): o fechamento é o do `grill-with-docs`. `CONTEXT.md` e ADR só mudam agora, nunca no meio do lote. Classifique a porta e diga o comando:

- **A** → `/to-prd` → `/to-issues`. Só invoque o `/to-prd` com a porta A confirmada.
- **B** → `/triage` ou `gh issue create` com critérios de aceite → `/pegar-issue`.
- **C** → `/ship "<descrição>" --from-diff`, feito nesta sessão.

## O que este skill não faz

- Não implementa nada e não chama `/ship` por conta própria: o produto é a decisão aprovada.
- Não grava `CONTEXT.md` nem ADR antes da aprovação.
- Não decide dinheiro, preferência de <leitor> nem texto na voz de quem assina: essas linhas ficam "[precisa de você]".
