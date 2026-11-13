---
name: to-issues
description: Quebra um plano ou PRD em fatias verticais independentes (tracer bullets) como issues do GitHub, sub-issues do PRD. Use para transformar um plano em tickets.
---

# To Issues

Break a plan into independently-grabbable issues using vertical slices (tracer bullets).

> **Idioma:** título e corpo de cada issue em **pt-BR** (O que construir, Critérios de aceite). Use a terminologia de `CONTEXT.md`. Veja `CLAUDE.md`.

> **Projeto:** esta skill é a mesma em todo Projeto. Use a terminologia do `CONTEXT.md` do Projeto e rode `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas to-issues`: o que ele imprimir vale por cima desta skill. O `bloco` e o `leitor` do `fluxo.py` dizem o título do bloco leigo (`<bloco>` abaixo) e para quem ele é escrito.

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

#### Paralelismo real (decisão do fluxo)

A `/onda-enxuta` roda juntas todas as fatias desbloqueadas. O único separador de ondas é a dependência, não o arquivo (decisão do fluxo): a subida mergeia PR a PR, e conflito tira só aquele PR, que o `onda-corretor` rebaseia. Fatie para que elas andem juntas de verdade:

- **Arquivo de costura:** o arquivo onde várias funcionalidades se registram (`main.py`, `config.py`, `AdminSidebar.tsx`, `fechar_onda.py` e afins). Fatias que só compartilham o arquivo andam na mesma onda. Só a dependência real separa, e o mesmo ponto é a mesma entrada: as duas fatias editam a mesma rota, o mesmo item de menu ou a mesma função, ou uma usa o que a outra cria. Cada fatia acrescentar a própria linha de `include_router` no `main.py` ou o próprio item no `AdminSidebar.tsx` não é mesmo ponto: as duas rodam juntas, e a subida PR a PR resolve o conflito de texto. Exemplo: as fatias 1 e 2 criam as rotas `/pedidos` e `/clientes`, cada uma com o próprio `include_router` no `main.py`, e andam na mesma onda; a fatia 3 muda a rota `/pedidos` que a 1 cria e anda depois da 1, com o `blocked_by` dela. Quando é mesmo ponto, a de depois ganha o `blocked_by` nativo da de antes (passo 5). Confira o ponto de registro antes de propor a divisão: no Mapa do terreno do PRD (comentário `## Mapa do terreno` de autor `OWNER`, `MEMBER` ou `COLLABORATOR`) ou, sem Mapa, no código (`git grep` do ponto de registro: rota, item de menu, setting).
- **G sem bloqueio:** fatia G que não bloqueia ninguém vira duas M.
- **Ondas previstas:** agrupe as fatias pelo grafo de dependência (onda 1 é toda fatia sem bloqueio; a seguinte, as que dependem só das anteriores) e leve o agrupamento à lista do passo 4 e ao corpo do PRD (passo 5).

### 4. Quiz the user

Apresente a divisão como uma **lista numerada em pt-BR**. Para cada fatia, mostre:

- **Título**: nome curto e descritivo
- **Tipo**: HITL / AFK
- **O que entrega**: o comportamento ponta-a-ponta que esta fatia faz funcionar
- **Bloqueada por**: quais outras fatias (se houver) precisam terminar antes
- **Histórias cobertas**: quais histórias de usuário esta fatia atende (se a fonte tiver)
- **Arquivo de costura**: os que ela toca e o ponto de registro que edita, ou "nenhum"; só o mesmo ponto de outra fatia vira "Bloqueada por"

Depois da lista, as **ondas previstas**: uma linha por onda com as fatias que andam juntas e, para cada fatia fora da onda 1, a dependência que a segura (ex.: "Onda 1: fatias 1 e 2, cada uma com o próprio `include_router` no `main.py`. Onda 2: fatia 3, depois da 1, muda a rota `/pedidos` que a 1 cria"). Arquivo de costura em comum não é motivo de onda.

Pergunte ao usuário: a granularidade está boa (grossa/fina demais)? As dependências estão corretas? Alguma fatia deve ser unida ou dividida? As marcações HITL/AFK estão certas? As ondas previstas fazem sentido? Itere até aprovar.

### 5. Publish the issues

Antes de publicar, determine o **número da issue-PRD pai** (`$PRD`): a issue criada pelo `/to-prd` nesta conversa, ou a issue passada como argumento no passo 1. Se realmente não houver pai (fatia avulsa), pule o vínculo de sub-issue abaixo.

Para cada fatia aprovada, publique uma issue com `gh issue create`, usando o template de corpo abaixo (**em pt-BR**), com a label `ready-for-agent` salvo instrução em contrário. Publique em ordem de dependência (bloqueadores primeiro) pra poder criar as **dependências nativas** com números reais.

**Classifique o tamanho de cada fatia** e aplique o label `fatia:P`, `fatia:M` ou `fatia:G` junto com `ready-for-agent` (uma por fatia; nunca no PRD pai). Critério: **P** = poucas horas, escopo contido, 1 camada dominante; **M** = fatia vertical completa de escopo conhecido (meio período); **G** = dia cheio ou mais (muitas camadas, UI nova ou integração externa). Labels e critério vivem em `docs/agents/triage-labels.md`; o PedroOS filtra por eles (chips `fatia:` da aba Issues), e a `/onda-enxuta` escolhe por eles o esforço do implementador (`xhigh` na G, `high` na P e na M): classifique pelo escopo, não pela pressa.

**Toda issue abre com o bloco "<bloco>"** (decisão do fluxo): um resumo em linguagem simples, no topo do corpo, antes da parte técnica. É a porta de entrada de quem lê as issues direto no GitHub sem abrir o código; sem ele, a parte técnica é só ruído pra essa pessoa. Formato fixo, mínimo de palavras, zero jargão:

- **O que muda:** uma frase de valor, não-técnica: o que o sistema passa a fazer por <leitor>.
- **Por que vale:** uma frase só: para que a mudança serve para <leitor>. É a Descrição de valor da Fatia, que o PedroOS mostra no hover dela.
- **O que você precisa saber:** de 2 a 3 regras simples que deixem o leitor reconhecer a feature funcionando.

**Humanizer antes de cada `gh issue create`** (ADR 0071 da origem do fluxo): passe o corpo da fatia pela Skill tool com `humanizer` em modo embutido, com atenção ao bloco "<bloco>". A amostra de voz é o bloco "<bloco>" do próprio PRD pai: ele manda no tom, o humanizer só tira os cacoetes. O resto do corpo fica neutro e direto; critérios de aceite continuam verificáveis e termos do `CONTEXT.md` não mudam.

**Vincule cada fatia como sub-issue nativa do PRD**: dá barra de progresso (ex.: "2 de 4 concluídas") e navegação pai↔filha na UI do GitHub. Logo após criar a fatia:

```bash
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
DONO=$(gh issue view "$PRD" --json assignees -q '.assignees[0].login // empty')  # a fatia nasce com o dono do PRD
URL=$(gh issue create --title "<título pt-BR>" --body "<corpo>" --label ready-for-agent --label "fatia:<P|M|G>" --assignee "${DONO:-@me}")
CHILD=${URL##*/}                                           # número da fatia recém-criada
CHILD_ID=$(gh api "repos/$REPO/issues/$CHILD" --jq '.id')  # database id (≠ número da issue)
gh api --method POST "repos/$REPO/issues/$PRD/sub_issues" -F sub_issue_id="$CHILD_ID"

# Fatia depende de outra? Registre a dependência NATIVA (blocked by), uma por bloqueadora <X>:
BLOCKER_ID=$(gh api "repos/$REPO/issues/<X>" --jq '.id')
gh api --method POST "repos/$REPO/issues/$CHILD/dependencies/blocked_by" -F issue_id="$BLOCKER_ID"
```

A dependência nativa é a **única** fonte de bloqueio (decisão do fluxo): a fatia bloqueada nasce com `ready-for-agent` mesmo assim, porque a fila filtra com `-is:blocked` e ela reaparece sozinha quando a bloqueadora fecha. Não escreva "Bloqueada por: #X" no corpo nem use label `blocked`.

Se o endpoint de sub-issues falhar (feature indisponível ou permissão), **não trave**: a seção `Pai: #$PRD` no corpo (abaixo) garante a referência cruzada. Reporte o erro e siga.

<issue-template>
## <bloco>

**O que muda:** uma frase de valor, não-técnica.

**Por que vale:** uma frase: para que a mudança serve para o leitor do Projeto.

**O que você precisa saber:**
- De 2 a 3 regras simples, sem jargão, que deixem o leitor reconhecer a feature.

---

## Pai

`#$PRD`: a issue-PRD de onde esta fatia saiu. **Sempre preencha** quando houver um PRD pai; use "Nenhum" só para fatia avulsa. Além desta menção, a fatia é registrada como **sub-issue nativa** do PRD (passo 5).

## O que construir

Descrição concisa desta fatia vertical. Descreva o **comportamento ponta-a-ponta**, não a implementação camada a camada.

Evite caminhos de arquivo e trechos de código: envelhecem rápido. Exceção: se um protótipo produziu um trecho que codifica uma decisão melhor que prosa (máquina de estados, reducer, schema, shape de tipo), inclua só a parte essencial e diga que veio de um protótipo.

## Critérios de aceite

- [ ] Critério 1
- [ ] Critério 2
- [ ] Critério 3

</issue-template>

**Ondas previstas no PRD.** Com todas as fatias publicadas, acrescente ao fim do corpo do PRD a seção `## Ondas previstas` aprovada no passo 4, agora com os números reais:

```bash
gh issue view "$PRD" --json body --jq .body > "${TMPDIR:-/tmp}/prd-$PRD.md"
cat >> "${TMPDIR:-/tmp}/prd-$PRD.md" <<'EOF'

## Ondas previstas

- Onda 1: #<a>, #<b>
- Onda 2: #<c>, depois da #<a> (usa a rota que a #<a> cria)
EOF
gh issue edit "$PRD" --body-file "${TMPDIR:-/tmp}/prd-$PRD.md"
```

Fora essa seção, não feche o PRD pai nem mexa no corpo e nos labels dele: só vincule as fatias como sub-issues. Quando a última sub-issue aberta fechar, a Action de higiene (`.github/workflows/higiene-issues.yml`) fecha o PRD sozinha, com um comentário.

### Paralelismo

As fatias de uma mesma onda prevista são independentes: várias sessões Claude Code podem pegá-las em paralelo (uma por sessão). Registre a **dependência nativa** (blocked by) sempre que houver dependência real: o pool paralelo filtra com `-is:blocked` e só oferece issues sem bloqueio aberto. Protocolo de claim em `docs/agents/issue-tracker.md`.
