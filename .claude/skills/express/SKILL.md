---
name: express
description: 'Fecha um grill em andamento em lote, com painel de aprovação. No meio de um `/grill-with-docs`, a pessoa diz "/express" e o agente responde todas as perguntas que faltam com a própria recomendação, entrega a tabela decisão por decisão (escolha, por quê, a outra opção) no terminal e num painel interativo publicado como Artifact (Concordo ou Discordo por linha, nota, botão de aprovar), e espera a aprovação antes de classificar a porta e chamar `/to-prd`. Com `--voz`, o painel agrupa as decisões em Pacotes de perguntas, cada um com uma Fala de até 30 segundos na voz B e um Sim ou Não que a pessoa responde pelo celular. Use quando o usuário disser "/express", "/express --voz", "fecha o grill com as suas recomendações", "responde o resto você e me mostra a tabela", "segue com todas as recomendações e me pede aprovação". Não implementa nada e não chama `/ship`: o grill de uma rodada que implementava a ponte mínima morreu em 01/11/2026 (ideia pequena vai para `/grill-with-docs --lote`).'
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

## Com voz (`/express --voz`)

Gatilho: `--voz`, "com voz" ou "fala para mim". Sem o gatilho nada desta seção vale, e o painel é o de `references/painel.html`.

O lote é o mesmo das Fases 1 e 2. Mudam o agrupamento, o painel e a aprovação. A pessoa ouve e responde pelo celular, longe do Mac.

1. **Pacote de perguntas.** Agrupe as decisões por tema em 3 a 5 Pacotes de perguntas, com até 7 decisões cada. A porta entra no último.
2. **Fala do pacote.** Para cada Pacote, um texto para o ouvido com teto de 30 segundos (uns 70 palavras; a voz B fala perto de 3 palavras por segundo). O alvo é sempre o menor texto que explica, não o teto. A Fala:
   - abre com "Pacote N." e fecha com "Segue com as recomendações?";
   - diz a escolha de cada decisão, e junta as óbvias numa frase só;
   - dá o motivo só onde houve troca de verdade, e cita a opção descartada só quando ela muda a decisão;
   - diz quantas perguntas do Pacote só a pessoa responde;
   - não tem sigla soletrada, barra nem símbolo (`/express --voz` vira "o express com voz").

   O teto não estica. O que não coube fica no texto da tela.
3. **Perguntas "[precisa de você]"** ficam fora do Sim ou Não. No painel elas são itens `tipo: "escolha"`: 2 a 4 opções em `opcoes`, o contexto mínimo em `c`, o rascunho do agente em `sugestao` (se houver) e um campo de resposta livre.
4. **Painel primeiro, áudio depois.** Publique o painel na hora, a partir de `references/painel-voz.html`, com as capacidades `db`, `user` e `comments`. Troque só o `<title>`, o `<h1>`, a frase de abertura, a constante `PACOTES` e o texto do rodapé. Cada Pacote aponta `audio: "falas/<id>.mp3"`; enquanto o arquivo não existe, o painel mostra o texto da Fala no lugar do play.
5. **Gerar as Falas.** Carregue a skill `narracao`. Uma Fala por vez, num parágrafo só: `python3 ~/.claude/voz/narrar.py --file k1.txt --output k1.wav` e depois `ffmpeg -y -loglevel error -i k1.wav -ac 1 -c:a libmp3lame -b:a 64k k1.mp3`. Cada Fala leva pouco mais de 1 minuto. A cada áudio pronto, republique o mesmo `file_path` com `files: {"falas/k1.mp3": "falas/k1.mp3"}` e `root` na pasta do painel. A pasta do painel fica dentro do diretório de trabalho e fora do git (não commite HTML nem áudio).
6. **VoiceStudio falhou.** O painel fica sem áudio (`audio: ""`), e você avisa no terminal. Nunca outra voz, nem a capacidade `tts` do painel.
7. **Aviso no celular.** Depois do primeiro publish, com `aviso_celular` ligado no `.claude/fluxo.json`, mande o link pelo `PushNotification` (ToolSearch `select:PushNotification`).
8. **Aprovação.** O botão final só acende com todos os Pacotes respondidos. Ele grava `aprovacao/final` e manda um comentário para o Claude (`comments.sendToClaude`), que acorda a sessão enquanto o watch do artefato diz "auto-replies armed" (confira com `ArtifactComments`, `action: "watch"`, logo depois do publish). Ao acordar, leia `aprovacao/final` e `respostas` com `ArtifactData`. Se o comentário não sair, o painel pede para a pessoa dizer "lê o painel" na sessão. O "ok" no terminal continua valendo.

O que o painel grava a mais no `db`:

- `respostas/<pN>` de um item `escolha`: `{resposta: "escolha", opcao, nota, at}`. Vale como resposta dada pela pessoa, nunca como "ok" na sugestão do agente.
- `sinais/<pacote>`: `{fonte, tocou, terminou, ua}`, para saber se o áudio tocou no aparelho dela.
- `sinais/acordar`: `{ok, codigo}`, o resultado do comentário que acorda a sessão.

Provado em 10/11/2026: o mp3 publicado junto do painel toca no app do Claude no iPhone. O comentário que acorda a sessão ainda não foi visto funcionando de ponta a ponta; se `sinais/acordar` vier com `ok: false`, registre o `codigo` e siga pelo "lê o painel".

## O que este skill não faz

- Não implementa nada e não chama `/ship` por conta própria: o produto é a decisão aprovada.
- Não grava `CONTEXT.md` nem ADR antes da aprovação.
- Não decide dinheiro, preferência de <leitor> nem texto na voz de quem assina: essas linhas ficam "[precisa de você]".
