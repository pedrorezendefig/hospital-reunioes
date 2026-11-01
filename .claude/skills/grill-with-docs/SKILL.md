---
name: grill-with-docs
description: 'Entrevista que desafia o plano contra CONTEXT.md e ADRs, uma pergunta por vez com recomendação, e atualiza a documentação conforme as decisões fecham. Modo lote (`/grill-with-docs --lote`, "responde tudo" ou "modo lote"): todas as lacunas de uma vez, já decididas, com um "ok" ou "N: correção" no fim. Use para testar um plano antes do PRD.'
---

> **Idioma (Hospital Reuniões):** conduza o grilling e escreva `CONTEXT.md`/ADRs em **pt-BR**. O `CONTEXT.md` atual (Reunião, Ata, Pendência, Facilitador, Colaborador…) é a referência de tom e vocabulário. Veja `CLAUDE.md`.

<what-to-do>

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering.

**Formato da pergunta (Hospital Reuniões):** vale para o modo normal e para o lote.

- Sem emoji. Sem travessão nem meia-risca: use vírgula, dois-pontos, parênteses ou ponto.
- Cada opção numa linha própria, uma embaixo da outra. Nunca duas opções na mesma linha.
- Toda pergunta fecha com uma linha "Recomendo:". Pergunta de sim ou não também lista duas opções: (a) a recomendada e (b) o contrário.
- Cada opção cabe em uma linha. O custo e o ganho vão no contexto, não dentro da opção.

```
**P1. <título da pergunta>**

<uma ou duas frases de contexto: o que está em jogo e por que importa>

- **(a)** <primeira opção, o que ela quer dizer na prática>
- **(b)** <segunda opção>

**Recomendo:** (a). <uma frase com o motivo>
```

A numeração continua na sessão inteira (P1, P2, P3...), para "P4" apontar sempre para a mesma pergunta.

If a *fact* can be found by exploring the codebase, look it up rather than asking me. If the fact lives in the official docs of an external service or library the project uses (ClickSign, Supabase/PostgREST, Coolify, WeasyPrint...), fire the `research` skill as a background agent and keep the grilling moving; fold the cited answer in when it arrives. The *decisions*, though, are mine: put each one to me and wait for my answer.

Do not enact the plan until I confirm we have reached a shared understanding.

**Modo lote (Hospital Reuniões):** gatilho `/grill-with-docs --lote` ou as frases "responde tudo" / "modo lote". Sem o gatilho, vale o de cima: uma pergunta por vez. No meio de um grill, `/express` (skill `express`) é o lote do que ainda falta, com as respostas já dadas preservadas e um painel interativo de aprovação no fim.

1. Levante os fatos no código primeiro, como no modo normal.
2. Liste **todas** as lacunas de uma vez, mesmo que sejam 20, numeradas e agrupadas por tema. Cada uma: a escolha em **negrito**, o porquê em 1 a 2 frases e a alternativa descartada, quando houver.
3. Não chute preferência de negócio, o que o diretor quer, dinheiro nem texto com a voz do Pedro: essas linhas saem marcadas "[precisa de você]", com no máximo uma sugestão de rascunho, sem fingir decisão.
4. No fim, um quadro `# | decisão | escolha | por quê` e a linha "Onde eu mais posso estar errado:" com as 2 escolhas mais arriscadas. Feche com a pergunta única: "ok" ou "N: correção"?
5. "ok" aceita tudo. "N: correção" corrige só aquela linha; reajuste as decisões que dependem dela e mostre só as linhas que mudaram, antes de fechar.
6. `CONTEXT.md` e ADR só mudam depois do "ok", nunca no meio do lote. O fechamento é o mesmo de baixo.

**Fechamento (Hospital Reuniões):** nem todo grill termina em PRD. Quando o entendimento fechar, classifique o trabalho numa das três portas do `/ask-pedro` ("Qual porta?") e diga, em uma linha, o motivo e o comando que vem a seguir, com a recomendada destacada:

- **A, PRD + fatias** (`/to-prd` → `/to-issues`): muda comportamento visível em mais de uma fatia, ou tem migration, ou o diretor precisa saber, ou nasce ou muda página do Manual, ou não cabe numa sessão.
- **B, issue única** (`/triage` ou `gh issue create` com critérios de aceite → `/pegar-issue`): uma fatia vertical no app, cabe numa sessão, sem diretor e sem Manual. O `hr-revisor` e o `/tdd` precisam dos critérios escritos.
- **C, PR direto** (`/ship "<descrição>" --from-diff`): ferramenta (`.claude/`, `tools/`, `.github/`, `docs/`) ou chore do app que não muda comportamento. A decisão vai no corpo do PR (ADR 0068, regra 12). Pode ser feita nesta mesma sessão, agora.

Não invoque `/to-prd` sem a porta A confirmada.

## PRD do diretor (`/grill-with-docs #N`)

Quando o argumento é uma issue, rode antes da primeira pergunta:

```bash
python3 .claude/skills/to-prd/scripts/prd_do_diretor.py ler <N>
```

O script reconhece o **PRD do diretor** (ADR 0075): a issue que o "sim" do Planejamento da Demanda cria na aba Tecnologia, com o marcador da Demanda e a seção "Ficou em aberto". Se a saída diz "Não é PRD do diretor", leia a issue e siga o grill normal. Se é PRD do diretor:

1. Mostre as Decisões de negócio como **já tomadas pelo diretor**, do jeito que o script imprime, e não repergunte nenhuma delas, nem para confirmar, nem com outra redação. Elas entram no grill como premissa.
2. Comece pelos itens de "Ficou em aberto", um por pergunta, no formato de sempre. Item técnico: você recomenda e o Pedro decide. Item de negócio, que só o diretor sabe: sai marcado "[precisa do diretor]" com a sua sugestão, e o Pedro escolhe entre responder ou levar para a Conversa da Demanda.
3. Depois, só o técnico: módulos, seams, schema e migration, contrato de API, testes, Manual. Problema, Solução e Histórias já estão na issue.
4. Se uma decisão técnica contradiz uma decisão do diretor, pare e diga qual, em uma linha. A decisão dele não se reescreve por conta própria.

Fechamento: a porta já é A e a issue já existe, então não classifique a porta de novo nem crie issue nova. O próximo passo é o `/to-prd`, que completa esta mesma issue (seção "PRD do diretor: completar a mesma issue" da skill), e depois o `/to-issues #N`.

</what-to-do>

<supporting-info>

## Domain model

Build and sharpen the domain model inline via the `domain-modeling` skill. It covers the file structure (`CONTEXT.md`, `docs/adr/`, multi-context repos via `CONTEXT-MAP.md`, lazy file creation), challenging terms against the glossary, sharpening fuzzy language, stress-testing with concrete scenarios, cross-referencing claims with code, updating `CONTEXT.md` the moment a term is resolved, the three-part test for offering an ADR, and the `CONTEXT-FORMAT.md`/`ADR-FORMAT.md` templates.

</supporting-info>
