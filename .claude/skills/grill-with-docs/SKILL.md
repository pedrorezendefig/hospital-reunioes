---
name: grill-with-docs
description: 'Entrevista em rodadas que testa um plano contra o CONTEXT.md e as ADRs do repositório e grava o glossário e as decisões enquanto elas fecham. Modo lote (`/grill-with-docs --lote`, "responde tudo" ou "modo lote"): todas as lacunas de uma vez, já decididas, com um "ok" ou "N: correção" no fim. Use quando a pessoa disser "grill with docs", "/grill-with-docs", "grill", "vamos debater o plano" dentro de um repositório, ou antes de um PRD. Para uma entrevista que não grava nada, use grill-me.'
model: fable
effort: medium
---

Entreviste a pessoa sem dar trégua até chegar a um entendimento comum. Conduza em **pt-BR**. Durante a entrevista, mantenha o modelo de domínio do repositório: o glossário em `CONTEXT.md` e as decisões em `docs/adr/`. Se a pessoa não quiser nada gravado, troque para `grill-me`.

Antes da primeira rodada, leia o `CONTEXT.md`, o `CONTEXT-MAP.md` (se existir) e as ADRs que tocam o assunto. Use o vocabulário deles nas perguntas. Se o `CLAUDE.md` do repositório aponta outro lugar para o glossário e as ADRs (por exemplo `local/CONTEXT.md` e `local/docs/adr/`), use o lugar que ele aponta.

Num Projeto com o pacote do fluxo (existe `.claude/fluxo.json`), rode também `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas grill-with-docs` antes da primeira rodada: o que ele imprimir vale por cima desta skill, inclusive o que fazer quando o argumento é uma issue (`/grill-with-docs #N`).

## Árvore de decisões

Monte o assunto como uma **árvore de decisões**: cada decisão abre as decisões que dependem dela.

Trabalhe a árvore em **rodadas**. A **fronteira** é o conjunto de decisões cujos pré-requisitos já estão fechados: as perguntas que dá para fazer _agora_ sem chutar respostas que você ainda não ouviu. Faça a fronteira inteira em uma rodada, com cada pergunta numerada e a sua recomendação. Depois espere as respostas.

Cada rodada respondida muda a árvore. Decisões fechadas empurram a fronteira para frente e liberam as perguntas que dependiam delas. Recalcule a fronteira e faça a próxima rodada. Uma pergunta que depende de outra ainda aberta nesta rodada fica para a rodada seguinte.

## Fatos são seus, decisões são da pessoa

Achar _fatos_ é trabalho seu, nunca da pessoa. Se uma pergunta precisa de um fato do ambiente (arquivos, código, ferramentas, documentação oficial), mande um subagente buscar. Não pergunte à pessoa nada que você consegue descobrir sozinho. Não trave a rodada por isso: só as perguntas que dependem daquele fato esperam. Faça o resto da fronteira agora.

As _decisões_ são da pessoa. Ponha cada uma para ela e espere.

## Formato da rodada

Regras fixas:

- Sem emoji. Sem travessão (nem o longo, nem o médio). Use vírgula, dois-pontos, parênteses ou ponto.
- Cada opção numa linha própria, uma embaixo da outra. Nunca duas opções na mesma linha.
- Toda pergunta fecha com uma linha "Recomendo:".
- Uma pergunta de sim ou não também lista duas opções: (a) a recomendada e (b) o contrário. Assim toda pergunta tem a mesma forma.
- Cada opção cabe em uma linha. O custo e o ganho vão no contexto, não dentro da opção.
- Escreva a pergunta de modo que "sim" aceite a recomendação.

Modelo de uma rodada:

```
**Rodada 1**

**P1. <título da pergunta>**

<uma ou duas frases de contexto: o que está em jogo e por que importa>

- **(a)** <primeira opção, o que ela quer dizer na prática>
- **(b)** <segunda opção>

**Recomendo:** (a). <uma frase com o motivo>

**P2. <título da pergunta>**

<contexto>

- **(a)** <opção>
- **(b)** <opção>
- **(c)** <opção, se houver>

**Recomendo:** (b). <motivo>

Responda só os números que quer mudar. O resto eu aceito como recomendado.
```

A numeração das perguntas continua entre as rodadas (P1 a P6 na rodada 1, P7 em diante na rodada 2). Assim "P4" aponta sempre para a mesma pergunta.

## Modo lote

Gatilho: `/grill-with-docs --lote` ou as frases "responde tudo" e "modo lote". Sem o gatilho, valem as rodadas de cima. No meio de um grill, `/express` (skill `express`, do pacote do fluxo) é o lote do que ainda falta, com as respostas já dadas preservadas e um painel de aprovação no fim.

1. Levante os fatos primeiro, como nas rodadas.
2. Liste **todas** as lacunas de uma vez, mesmo que sejam 20, numeradas na sequência da sessão e agrupadas por tema. Cada uma: a escolha em **negrito**, o porquê em uma ou duas frases e a alternativa descartada, quando houver.
3. Não chute preferência de negócio, o que quem decide quer, dinheiro nem texto com a voz de quem assina: essas linhas saem marcadas "[precisa de você]", com no máximo uma sugestão de rascunho, sem fingir decisão.
4. No fim, um quadro `# | decisão | escolha | por quê` e a linha "Onde eu mais posso estar errado:" com as 2 escolhas mais arriscadas. Feche com a pergunta única: "ok" ou "N: correção"?
5. "ok" aceita tudo. "N: correção" corrige só aquela linha; reajuste as decisões que dependem dela e mostre só as linhas que mudaram, antes de fechar.
6. `CONTEXT.md` e ADR só mudam depois do "ok", nunca no meio do lote.

## Documentação durante a entrevista

Chame a skill `domain-modeling` e siga as regras dela. Em resumo:

- **Confronte o glossário.** Se a pessoa usa um termo que conflita com o `CONTEXT.md`, aponte na hora.
- **Afie termos vagos.** Proponha um termo canônico quando a palavra tem dois sentidos.
- **Teste com cenários concretos.** Invente casos de borda que obrigam a definir os limites entre conceitos.
- **Confira com o código.** Se a pessoa descreve um comportamento que o código contradiz, mostre a contradição.
- **Grave o termo quando ele fecha.** Atualize o `CONTEXT.md` na hora, no formato que a skill `domain-modeling` indica. O `CONTEXT.md` é só glossário, sem detalhe de implementação.
- **Ofereça ADR com parcimônia.** Só quando a decisão é difícil de desfazer, surpreende quem chega sem contexto e veio de uma troca real entre alternativas. Use o formato de ADR que a skill `domain-modeling` indica.

Crie os arquivos só quando tiver algo para escrever. Os arquivos de documentação seguem as mesmas regras de escrita da rodada: sem emoji e sem travessão.

## Fim

A sessão termina quando a fronteira fica vazia: todo galho da árvore visitado, nada assumido em silêncio. Mostre um resumo curto das decisões, uma por linha, e liste os arquivos de documentação que você criou ou mudou. Não execute o plano até a pessoa confirmar que vocês chegaram a um entendimento comum.

**Num Projeto com o pacote do fluxo** (existe `.claude/fluxo.json`), nem todo grill termina em PRD. Quando o entendimento fechar, classifique o trabalho numa das três portas e diga, em uma linha, o motivo e o comando que vem a seguir, com a recomendada destacada. O que `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas grill-with-docs` imprimir entra nos critérios:

- **A, PRD + fatias** (`/to-prd` e depois `/to-issues`): muda comportamento visível em mais de uma fatia, ou tem migration, ou quem decide precisa saber, ou não cabe numa sessão.
- **B, issue única** (`/triage` ou `gh issue create` com critérios de aceite, depois `/pegar-issue`): uma fatia vertical no app, cabe numa sessão. O `onda-revisor` e o `/tdd` precisam dos critérios escritos.
- **C, PR direto** (`/ship "<descrição>" --from-diff`): ferramenta (`.claude/`, `tools/`, `.github/`, `docs/`) ou chore do app que não muda comportamento. A decisão vai no corpo do PR. Pode ser feita nesta mesma sessão, agora.

Não invoque `/to-prd` sem a porta A confirmada.
