---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker using tracer-bullet vertical slices. Use when user wants to convert a plan into issues, create implementation tickets, or break down work into issues.
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

> **Idioma (Hospital Reuniões):** título e corpo de cada issue em **pt-BR** (O que construir, Critérios de aceite, Bloqueada por). Use a terminologia de `CONTEXT.md`. Veja `CLAUDE.md`.

Issue tracker = **GitHub Issues** via `gh` (veja `docs/agents/issue-tracker.md`). Triage label = `ready-for-agent` (veja `docs/agents/triage-labels.md`). Rode `/setup-matt-pocock-skills` se faltar esse contexto.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes an issue reference (number, URL, or path) as an argument, fetch it (`gh issue view <N> --comments`) and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already, explore the codebase to understand its current state. Issue titles and descriptions should use the domain glossary (`CONTEXT.md`) vocabulary, and respect ADRs (`docs/adr/`) in the area you're touching.

### 3. Draft vertical slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Slices may be **HITL** or **AFK**. HITL slices require human interaction (architectural decision, design review). AFK slices can be implemented and merged without human interaction. Prefer AFK over HITL where possible.

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
</vertical-slice-rules>

### 4. Quiz the user

Apresente a divisão como uma **lista numerada em pt-BR**. Para cada fatia, mostre:

- **Título**: nome curto e descritivo
- **Tipo**: HITL / AFK
- **Bloqueada por**: quais outras fatias (se houver) precisam terminar antes
- **Histórias cobertas**: quais histórias de usuário esta fatia atende (se a fonte tiver)

Pergunte ao usuário: a granularidade está boa (grossa/fina demais)? As dependências estão corretas? Alguma fatia deve ser unida ou dividida? As marcações HITL/AFK estão certas? Itere até aprovar.

### 5. Publish the issues

For each approved slice, publish a new issue with `gh issue create`, using the body template below (**em pt-BR**). Publish them with the `ready-for-agent` label unless instructed otherwise.

Publish in dependency order (blockers first) so you can reference real issue numbers in "Bloqueada por".

<issue-template>
## Pai

Referência à issue pai no tracker (se a fonte foi uma issue existente; senão, omita esta seção).

## O que construir

Descrição concisa desta fatia vertical. Descreva o **comportamento ponta-a-ponta**, não a implementação camada a camada.

Evite caminhos de arquivo e trechos de código — envelhecem rápido. Exceção: se um protótipo produziu um trecho que codifica uma decisão melhor que prosa (máquina de estados, reducer, schema, shape de tipo), inclua só a parte essencial e diga que veio de um protótipo.

## Critérios de aceite

- [ ] Critério 1
- [ ] Critério 2
- [ ] Critério 3

## Bloqueada por

- Referência à(s) issue(s) que bloqueiam (se houver).

Ou "Nenhuma — pode começar já" se não há bloqueio.

</issue-template>

Do NOT close or modify any parent issue.

### Paralelismo

Estas fatias são independentes — várias sessões Claude Code podem pegá-las em paralelo (uma por sessão). Marque **"Bloqueada por"** sempre que houver dependência real: o pool paralelo só oferece issues sem bloqueio aberto. Protocolo de claim em `docs/agents/issue-tracker.md`.
