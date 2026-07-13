---
name: to-prd
description: Turn the current conversation context into a PRD and publish it to the project issue tracker. Use when user wants to create a PRD from the current context.
disable-model-invocation: true
---

This skill takes the current conversation context and codebase understanding and produces a PRD. Do NOT interview the user — just synthesize what you already know.

> **Idioma (Hospital Reuniões):** o PRD inteiro é escrito em **pt-BR** — título da issue, problema, solução, histórias de usuário, decisões. Use a terminologia de `CONTEXT.md` (Reunião, Ata, Pendência, Facilitador, Colaborador, Envelope…). Veja a regra de idioma no `CLAUDE.md`.

Issue tracker = **GitHub Issues** via `gh` (veja `docs/agents/issue-tracker.md`). Triage label = `ready-for-agent` (veja `docs/agents/triage-labels.md`). Se faltar esse contexto, leia os dois arquivos de `docs/agents/`.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary (`CONTEXT.md`) vocabulary throughout the PRD, and respect any ADRs (`docs/adr/`) in the area you're touching.

2. Sketch out the major modules you will need to build or modify. Look for opportunities to extract **deep modules**: a deep module encapsulates a lot of functionality behind a simple, testable interface that rarely changes (as opposed to a shallow module).

   Then sketch the **seams** at which the feature will be tested: the public boundaries where behavior is observed. Prefer existing seams to new ones, and use the highest seam possible; if a new seam is needed, propose it at the highest point you can. The fewer seams across the codebase, the better: the ideal number is one per change.

   Check with the user that these modules and seams match their expectations before writing the PRD.

3. Write the PRD using the template below (**in pt-BR**), then publish it with `gh issue create`. Apply the `ready-for-agent` label — no need for additional triage.

   **Todo PRD abre com o bloco "Para o diretor"** (ADR 0020, decisão 7): um resumo em linguagem simples, no topo do corpo, antes da parte técnica. É a porta de entrada do revisor não-técnico, que lê as issues direto no GitHub. Formato fixo, mínimo de palavras, zero jargão:

   - **O que muda:** uma frase de valor, não-técnica — o que o sistema passa a fazer pelo hospital.
   - **O que você precisa saber:** 2–3 regras simples que deixem o revisor reconhecer a feature funcionando.

   Capture e **anuncie o número** da issue-PRD criada (o `gh issue create` devolve a URL; o número é o último segmento — ex.: `URL=$(gh issue create …); PRD=${URL##*/}`). Diga ao usuário, ex.: _"PRD publicado como **#41**"_. Esse número é o **pai** das fatias: o `/to-issues` o usa pra vincular cada fatia como **sub-issue** nativa. Rodando `/to-issues` em seguida nesta mesma conversa, ele já tem o `#41` no contexto.

<prd-template>

## 👔 Para o diretor

**O que muda:** uma frase de valor, não-técnica.

**O que você precisa saber:**
- 2–3 regras simples, sem jargão, que deixem o revisor reconhecer a feature.

---

## Problema

O problema que o usuário enfrenta, da perspectiva dele.

## Solução

A solução para o problema, da perspectiva do usuário.

## Histórias de usuário

Uma lista LONGA e numerada de histórias de usuário, cada uma no formato:

1. Como `<ator>`, quero `<funcionalidade>`, para `<benefício>`

<exemplo>
1. Como facilitador, quero ver o status de assinatura de cada participante, para saber quem ainda não assinou a ata e cobrar só essa pessoa.
</exemplo>

A lista deve ser bem extensa e cobrir todos os aspectos da funcionalidade.

## Decisões de implementação

Lista de decisões tomadas. Pode incluir: módulos a construir/modificar, as interfaces desses módulos, esclarecimentos técnicos do desenvolvedor, decisões arquiteturais, mudanças de schema, contratos de API, interações específicas.

NÃO inclua caminhos de arquivo nem trechos de código — envelhecem rápido. Exceção: se um protótipo produziu um trecho que codifica uma decisão melhor que prosa (máquina de estados, reducer, schema, shape de tipo), inclua só a parte essencial e diga brevemente que veio de um protótipo.

## Decisões de teste

Lista de decisões de teste. Inclua: o que faz um bom teste (testar só comportamento externo, não detalhes de implementação), em quais **seams** os testes observam o comportamento (os acordados no passo 2), quais módulos serão testados, e exemplos análogos já existentes no código.

## Fora de escopo

O que está fora de escopo deste PRD.

## Notas adicionais

Qualquer nota adicional sobre a funcionalidade.

</prd-template>
