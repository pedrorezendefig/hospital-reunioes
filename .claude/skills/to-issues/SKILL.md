---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker using tracer-bullet vertical slices. Use when user wants to convert a plan into issues, create implementation tickets, or break down work into issues.
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

> **Idioma (Hospital Reuniões):** título e corpo de cada issue em **pt-BR** (O que construir, Critérios de aceite, Bloqueada por). Use a terminologia de `CONTEXT.md`. Veja `CLAUDE.md`.

Issue tracker = **GitHub Issues** via `gh` (veja `docs/agents/issue-tracker.md`). Triage label = `ready-for-agent` (veja `docs/agents/triage-labels.md`). Se faltar esse contexto, leia os dois arquivos de `docs/agents/`.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes an issue reference (number, URL, or path) as an argument, fetch it (`gh issue view <N> --comments`) and read its full body and comments.

### 2. Explore the codebase (optional)

If you have not already, explore the codebase to understand its current state. Issue titles and descriptions should use the domain glossary (`CONTEXT.md`) vocabulary, and respect ADRs (`docs/adr/`) in the area you're touching.

Look for opportunities to **prefactor** the code to make the implementation easier: "Make the change easy, then make the easy change." Any prefactoring becomes the first slice, blocking the ones that need it.

### 3. Draft vertical slices

Break the plan into **tracer bullet** issues. Each issue is a thin vertical slice that cuts through ALL integration layers end-to-end, NOT a horizontal slice of one layer.

Slices may be **HITL** or **AFK**. HITL slices require human interaction (architectural decision, design review). AFK slices can be implemented and merged without human interaction. Prefer AFK over HITL where possible.

<vertical-slice-rules>
- Each slice delivers a narrow but COMPLETE path through every layer (schema, API, UI, tests)
- A completed slice is demoable or verifiable on its own
- Prefer many thin slices over few thick ones
- Each slice is sized to fit in a single fresh context window
</vertical-slice-rules>

**Wide refactors são a exceção ao fatiamento vertical.** Um **wide refactor** é uma mudança mecânica única (renomear uma coluna, retipar um símbolo compartilhado) cujo **blast radius** se espalha pelo codebase inteiro: um único edit quebra milhares de call sites de uma vez e nenhuma fatia vertical fecha verde. Não force um tracer bullet; sequencie como **expand-contract**:

1. **Expand:** adicione a forma nova ao lado da velha, sem quebrar nada.
2. **Migrate:** migre os call sites em lotes dimensionados pelo blast radius (por pacote, por diretório), cada lote uma issue bloqueada pelo expand; o CI fica verde lote a lote porque a forma velha ainda existe.
3. **Contract:** apague a forma velha quando não restar caller, numa issue bloqueada por todos os lotes de migração.

Se nem os lotes conseguem fechar verde sozinhos, mantenha a sequência mas use uma integration branch compartilhada, com todas as issues bloqueando uma issue final de integrate-and-verify: o verde só é prometido lá.

### 4. Quiz the user

Apresente a divisão como uma **lista numerada em pt-BR**. Para cada fatia, mostre:

- **Título**: nome curto e descritivo
- **Tipo**: HITL / AFK
- **O que entrega**: o comportamento ponta-a-ponta que esta fatia faz funcionar
- **Bloqueada por**: quais outras fatias (se houver) precisam terminar antes
- **Histórias cobertas**: quais histórias de usuário esta fatia atende (se a fonte tiver)

Pergunte ao usuário: a granularidade está boa (grossa/fina demais)? As dependências estão corretas? Alguma fatia deve ser unida ou dividida? As marcações HITL/AFK estão certas? Itere até aprovar.

### 5. Publish the issues

Antes de publicar, determine o **número da issue-PRD pai** (`$PRD`): a issue criada pelo `/to-prd` nesta conversa, ou a issue passada como argumento no passo 1. Se realmente não houver pai (fatia avulsa), pule o vínculo de sub-issue abaixo.

Para cada fatia aprovada, publique uma issue com `gh issue create`, usando o template de corpo abaixo (**em pt-BR**), com a label `ready-for-agent` salvo instrução em contrário. Publique em ordem de dependência (bloqueadores primeiro) pra poder referenciar números reais em "Bloqueada por".

**Classifique o tamanho de cada fatia** e aplique o label `fatia:P`, `fatia:M` ou `fatia:G` junto com `ready-for-agent` (uma por fatia; nunca no PRD pai). Critério: **P** = poucas horas, escopo contido, 1 camada dominante; **M** = fatia vertical completa de escopo conhecido (meio período); **G** = dia cheio ou mais (muitas camadas, UI nova ou integração externa). Labels e critério vivem em `docs/agents/triage-labels.md`; o dashboard usa esses labels pra medir lead time real por tamanho: classifique pelo escopo, não pela pressa.

**Toda issue abre com o bloco "Para o diretor"** (ADR 0020, decisão 7): um resumo em linguagem simples, no topo do corpo, antes da parte técnica. É a porta de entrada do revisor não-técnico, que lê as issues direto no GitHub — sem ele, a parte técnica é só ruído pra essa pessoa. Formato fixo, mínimo de palavras, zero jargão:

- **O que muda:** uma frase de valor, não-técnica — o que o sistema passa a fazer pelo hospital.
- **O que você precisa saber:** 2–3 regras simples que deixem o revisor reconhecer a feature funcionando.

**Vincule cada fatia como sub-issue nativa do PRD** — dá barra de progresso (ex.: "2 de 4 concluídas") e navegação pai↔filha na UI do GitHub. Logo após criar a fatia:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
URL=$(gh issue create --title "<título pt-BR>" --body "<corpo>" --label ready-for-agent --label "fatia:<P|M|G>")
CHILD=${URL##*/}                                           # número da fatia recém-criada
CHILD_ID=$(gh api "repos/$REPO/issues/$CHILD" --jq '.id')  # database id (≠ número da issue)
gh api --method POST "repos/$REPO/issues/$PRD/sub_issues" -F sub_issue_id="$CHILD_ID"
```

Se o endpoint de sub-issues falhar (feature indisponível ou permissão), **não trave**: a seção `Pai: #$PRD` no corpo (abaixo) garante a referência cruzada. Reporte o erro e siga.

<issue-template>
## 👔 Para o diretor

**O que muda:** uma frase de valor, não-técnica.

**O que você precisa saber:**
- 2–3 regras simples, sem jargão, que deixem o revisor reconhecer a feature.

---

## Pai

`#$PRD` — a issue-PRD de onde esta fatia saiu. **Sempre preencha** quando houver um PRD pai; use "Nenhum" só para fatia avulsa. Além desta menção, a fatia é registrada como **sub-issue nativa** do PRD (passo 5).

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

Não feche nem edite o corpo/labels do PRD pai — apenas vincule as fatias como sub-issues. Quando a última sub-issue aberta fechar, a Action de higiene (`.github/workflows/higiene-issues.yml`) fecha o PRD sozinha, com um comentário.

### Paralelismo

Estas fatias são independentes — várias sessões Claude Code podem pegá-las em paralelo (uma por sessão). Marque **"Bloqueada por"** sempre que houver dependência real: o pool paralelo só oferece issues sem bloqueio aberto. Protocolo de claim em `docs/agents/issue-tracker.md`.
