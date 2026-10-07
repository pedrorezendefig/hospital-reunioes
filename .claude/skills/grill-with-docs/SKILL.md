---
name: grill-with-docs
description: Entrevista que desafia o plano contra CONTEXT.md e ADRs, uma pergunta por vez com recomendação, e atualiza a documentação conforme as decisões fecham. Use para testar um plano antes do PRD.
---

> **Idioma (Hospital Reuniões):** conduza o grilling e escreva `CONTEXT.md`/ADRs em **pt-BR**. O `CONTEXT.md` atual (Reunião, Ata, Pendência, Facilitador, Colaborador…) é a referência de tom e vocabulário. Veja `CLAUDE.md`.

<what-to-do>

Interview me relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time, waiting for feedback on each question before continuing. Asking multiple questions at once is bewildering.

If a *fact* can be found by exploring the codebase, look it up rather than asking me. If the fact lives in the official docs of an external service or library the project uses (ClickSign, Supabase/PostgREST, Coolify, WeasyPrint...), fire the `research` skill as a background agent and keep the grilling moving; fold the cited answer in when it arrives. The *decisions*, though, are mine: put each one to me and wait for my answer.

Do not enact the plan until I confirm we have reached a shared understanding.

**Fechamento (Hospital Reuniões):** nem todo grill termina em PRD. Quando o entendimento fechar, classifique o trabalho numa das três portas do `/ask-pedro` ("Qual porta?") e diga, em uma linha, o motivo e o comando que vem a seguir, com a recomendada destacada:

- **A, PRD + fatias** (`/to-prd` → `/to-issues`): muda comportamento visível em mais de uma fatia, ou tem migration, ou o diretor precisa saber, ou nasce ou muda página do Manual, ou não cabe numa sessão.
- **B, issue única** (`/triage` ou `gh issue create` com critérios de aceite → `/pegar-issue`): uma fatia vertical no app, cabe numa sessão, sem diretor e sem Manual. O `hr-revisor` e o `/tdd` precisam dos critérios escritos.
- **C, PR direto** (`/ship "<descrição>" --from-diff`): ferramenta (`.claude/`, `tools/`, `.github/`, `docs/`) ou chore do app que não muda comportamento. A decisão vai no corpo do PR (ADR 0068, regra 12). Pode ser feita nesta mesma sessão, agora.

Não invoque `/to-prd` sem a porta A confirmada.

</what-to-do>

<supporting-info>

## Domain model

Build and sharpen the domain model inline via the `domain-modeling` skill. It covers the file structure (`CONTEXT.md`, `docs/adr/`, multi-context repos via `CONTEXT-MAP.md`, lazy file creation), challenging terms against the glossary, sharpening fuzzy language, stress-testing with concrete scenarios, cross-referencing claims with code, updating `CONTEXT.md` the moment a term is resolved, the three-part test for offering an ADR, and the `CONTEXT-FORMAT.md`/`ADR-FORMAT.md` templates.

</supporting-info>
