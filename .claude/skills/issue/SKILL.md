---
name: issue
description: Skill conversacional e educativa pra trabalhar com GitHub Issues. Cobre 4 modos. `/issue new` ou `/issue` sem args inicia diálogo guiado pra criar Issue (pergunta uma coisa por vez, estrutura título + body + labels + assignee, mostra preview antes de criar). `/issue listar` mostra Issues abertas em tabela. `/issue pegar <N>` importa Issue #N pro contexto (body + comentários) e oferece próximos passos. `/issue trabalhar <N>` importa e encadeia automaticamente `/ship` com a Issue. Use SEMPRE que o usuário disser "criar uma issue", "abrir issue", "registrar bug", "registrar problema", "anotar bug", "quero documentar isso", "tem um problema...", "pega a issue 42", "trabalhar na issue 42", "ver issues abertas", "listar issues", "começar a trabalhar nessa task", "essa task aqui", "issue", "/issue", ou quando descrever qualquer problema/bug/melhoria que precisa virar registro persistente. Aciona também em pedidos vagos tipo "preciso anotar isso pra não esquecer", "isso aqui dá pra automatizar?", "tem uma melhoria que queria propor". A skill é INTERATIVA e FASEADA — pergunta uma coisa por vez, explica o que tá fazendo nos bastidores, e nunca cria Issue sem mostrar preview. Substitui o fluxo manual de "ir pra github.com no browser, abrir new issue, escrever direto no campo". Pensada pra time iniciante em GitHub workflow (Pedro + 2 contratados no projeto Hospital), portanto explica o "porquê" de cada passo.
---

# issue — workflow conversacional de GitHub Issues

Uma skill amigável pra registrar problemas, ideias e melhorias no GitHub via diálogo. Não exige saber `gh` CLI nem markdown — a skill faz tudo, você só conversa.

## Princípio: interativa e faseada

Esta skill **sempre conversa primeiro, age depois**. Cada interação:

1. **Uma pergunta por vez.** Nunca dispara uma série de perguntas em sequência. Espera resposta, processa, faz a próxima.
2. **Explica o que tá fazendo.** Ex: "vou rodar `gh issue list` que é o CLI do GitHub. Isso lista as Issues abertas sem abrir browser. Isso ajuda porque..."
3. **Mostra preview antes de commitar.** Issue só vai pro GitHub depois que o usuário confirma. Edit livre antes.
4. **Aceita "voltar" e "cancelar".** A qualquer momento o usuário pode pedir pra desfazer um passo.

Não force o usuário a saber jargão de Git/GitHub. Quando termos técnicos aparecem inevitavelmente (PR, branch, label, assignee), explique brevemente na primeira menção.

---

## Sintaxe e modos

```bash
/issue                    # menu interativo
/issue new                # criar Issue nova guiada
/issue listar             # listar Issues abertas
/issue pegar <N>          # importar Issue #N pro contexto (sem agir)
/issue trabalhar <N>      # pegar Issue #N + encadear /ship
/issue comentar <N>       # adicionar comentário guiado em Issue existente
/issue fechar <N>         # fechar Issue com comentário de motivo
```

Sem args, mostre o menu interativo: "O que você quer fazer? Criar nova / Listar abertas / Pegar uma específica / Trabalhar em uma".

---

## Bootstrap

Toda execução começa por:

1. **Validar `gh` CLI**: `gh --version` deve retornar OK. `gh auth status` autenticado. Se não → reportar erro educativo:
   > "Hmm, o GitHub CLI (`gh`) não tá autenticado. Roda `gh auth login` no terminal (precisa de browser pra primeira vez). Depois volta aqui."
2. **Descobrir repo**: `gh repo view --json nameWithOwner --jq .nameWithOwner` (ex: `pedrorezendefig/hospital-reunioes`). Se não estiver num repo → "Pra usar essa skill, precisamos estar num repo GitHub. Cd pra pasta do projeto."
3. **Cachear contexto**: nome do repo, branches relevantes, labels disponíveis (`gh label list --limit 100`). Não precisa expor pro usuário — usa internamente.

---

## Modo 1 — `/issue new` (criar Issue guiada)

Este é o modo de uso principal. Pensa numa conversa de café, não num formulário.

### Diálogo guiado

**Passo 1 — Abertura**

Abrir com pergunta aberta, sem estrutura:

> "Beleza, vamos registrar isso. Me conta o que tá rolando — pode ser bem informal, eu organizo depois."

Esperar resposta. Não interrompa com perguntas.

**Passo 2 — Categorizar**

Depois que o usuário descreveu, faça **uma** pergunta pra categorizar:

> "Entendi. Isso parece mais um (a) **bug** — algo que tava funcionando e quebrou; (b) **funcionalidade nova** — algo que ainda não existe e seria útil; (c) **melhoria** — refinar algo que já existe; (d) **dúvida/discussão** — precisa pensar antes de decidir o que fazer?"

Aceitar as letras OU palavras livres ("bug", "feature", etc.). Mapear pra:
- `(a)` → `type:fix` + sufixo "Bug: " no título.
- `(b)` → `type:feature` + sufixo "Feature: ".
- `(c)` → `type:feature` ou `type:refactor` dependendo do tom (pergunta de novo se ambíguo).
- `(d)` → sugerir **Discussions** em vez de Issue:
  > "Pra discussão/dúvida sem ação clara, GitHub Discussions é melhor que Issue (Issue é pra coisa acionável). Posso abrir uma thread em Discussions pra você? Categoria sugerida: Dúvidas."
  > Se sim → usar `gh api graphql` com `createDiscussion` (ver `references/discussions.md`).
  > Se não → segue com Issue normal.

**Passo 3 — Onde acontece (área)**

> "Em qual parte do sistema? Backend / Frontend / Supabase (banco) / Infra/Deploy / Docs / Outro?"

Mapear pra labels `area:backend|frontend|supabase|infra|docs|skills|spec`.

**Passo 4 — Detalhes específicos por tipo**

Pra **bug**:
> "Como dá pra reproduzir? Vai uma sequência tipo:
> 1. Logar como usuário X
> 2. Clicar em Y
> 3. Esperar Z, mas acontece W."

Pra **feature/melhoria**:
> "Qual o cenário onde isso seria útil? Ex: 'quando o facilitador termina uma reunião, gostaria que aparecesse um botão pra...'"

Pra ambos, depois:
> "Tem algum print, log, ou trecho de código que ajuda? Pode colar aqui. (Se não tem, pula.)"

Aceitar conteúdo livre.

**Passo 5 — Prioridade**

> "Qual a urgência? (a) **Alta** — bloqueia uso do sistema agora; (b) **Média** — incomoda mas tem workaround; (c) **Baixa** — quando der tempo."

Mapear pra `priority:high|medium|low`.

**Passo 6 — Quem pega**

> "Quem vai trabalhar nisso? (a) eu mesmo; (b) pedroribbe; (c) outro contratado (quando entrar); (d) deixa pra alguém pegar depois."

Mapear pra assignee. Validar que o handle existe via `gh api /users/<handle>` antes de assignar.

**Passo 7 — Preview**

Mostrar tudo organizado:

```
═══ Preview da Issue ═══

Título:  [Bug] Webhook ClickSign retorna 500 em assinatura múltipla

Body:
## O que tá rolando
[descrição do usuário, formatada]

## Como reproduzir
1. ...
2. ...

## Resultado esperado
[se mencionado, ou inferir]

## Resultado atual
[se mencionado]

## Notas extras
[print/log/código se colado]

Labels:    type:fix, area:backend, priority:high
Assignee:  @pedroribbe
Repo:      pedrorezendefig/hospital-reunioes
```

Perguntar:
> "Tá bom assim? (a) Sim, cria; (b) Quero editar X; (c) Cancelar."

**Passo 8 — Criar**

Se aprovado:

```bash
gh issue create \
  --title "$TITULO" \
  --body "$BODY" \
  --label "type:$TIPO,area:$AREA,priority:$PRIORIDADE" \
  --assignee "$ASSIGNEE"
```

Capturar URL e número da Issue. Mostrar:

> "✅ Issue #67 criada: <URL>
>
> Os outros membros do time já receberam push notification no GitHub Mobile (se tiverem com Watching ativado). Próximo passo? (a) Trabalhar nela agora via `/ship`; (b) Deixar pra depois."

Se (a) → encadear `/ship "<titulo da issue>" --issue 67 --type <tipo>` direto.

---

## Modo 2 — `/issue listar`

Mostrar Issues abertas em tabela compacta.

```bash
gh issue list --state open --limit 30 \
  --json number,title,labels,assignees,createdAt,author \
  --template '{{range .}}#{{.number}} | {{.title}} | {{range .labels}}{{.name}} {{end}}| {{range .assignees}}@{{.login}} {{end}}| {{.author.login}} | {{timeago .createdAt}}{{"\n"}}{{end}}'
```

Renderizar como tabela markdown. Exemplo:

| # | Título | Labels | Assignee | Autor | Aberta há |
|---|---|---|---|---|---|
| 67 | Bug: webhook X retorna 500 | type:fix · area:backend · priority:high | @pedroribbe | @pmrdef | 2 dias |
| 65 | Feature: exportar atas em CSV | type:feature · area:frontend | — | @pedroribbe | 5 dias |

Perguntar:
> "Qual quer abrir? Digita o número, ou 'voltar' pra sair."

Se número → fluir pra `/issue pegar <N>` automaticamente.

**Filtros opcionais** (se usuário pedir):
- `--label type:fix` (só bugs)
- `--assignee @me` (só minhas)
- `--state closed` (fechadas recentes)

Aceitar pedidos em PT: "só os bugs" → adiciona `--label type:fix`. "só os meus" → `--assignee @me`.

---

## Modo 3 — `/issue pegar <N>`

Importar Issue #N pro contexto da conversa, **sem agir**.

```bash
gh issue view <N> --json number,title,body,labels,assignees,author,createdAt,comments,state
```

Renderizar de forma clara:

```
═══ Issue #67 ═══

Título:    Bug: webhook X retorna 500 em assinatura múltipla
Estado:    open
Aberta:    2 dias atrás, por @pedroribbe
Labels:    type:fix, area:backend, priority:high
Assignee:  @pedroribbe

────── Body ──────

[body markdown formatado, indentado pra leitura]

────── Comentários (2) ──────

@pmrdef · 1 dia atrás:
> Consegui reproduzir aqui. Acho que é no handler `/webhooks/clicksign`...

@pedroribbe · 8 horas atrás:
> Vou investigar amanhã. Beleza.

─────────────────────
```

Perguntar:
> "O que fazer agora? (a) **Trabalhar nela** — invoca `/ship`; (b) **Comentar** — adicionar uma resposta; (c) **Fechar** — se já tá resolvido; (d) **Só ler** — sair e deixar como tá."

Encaminhar pra modo correspondente baseado na resposta.

---

## Modo 4 — `/issue trabalhar <N>`

Fluxo encadeado: pega Issue + invoca `/ship`.

1. Roda `/issue pegar <N>` internamente (importa Issue pro contexto).
2. Mostra resumo curto:
   > "Issue #67 importada. Vou rodar `/ship` pra começar a trabalhar nela."
3. Sugere tipo baseado em labels (`type:fix` → `--type fix`).
4. Pergunta confirmação:
   > "Tipo da mudança: **fix** (peguei do label). Repo: pedrorezendefig/hospital-reunioes. Vai criar branch `fix/<slug>-67`. Confirma?"
5. Se sim → invoca `/ship "<titulo>" --issue <N> --type <tipo>`.

A skill `/ship` (em `.claude/skills/ship/SKILL.md`) toma conta dali em diante.

---

## Modo 5 — `/issue comentar <N>`

Adicionar comentário em Issue existente.

1. `gh issue view <N>` pra contextualizar.
2. Pergunta:
   > "O que você quer comentar na Issue #67?"
3. User digita livre.
4. Preview:
   > "Vou postar o seguinte comentário em #67:
   > ───
   > [texto]
   > ───
   > Confirma? (sim/editar/cancelar)"
5. Se sim:
   ```bash
   gh issue comment <N> --body "<texto>"
   ```

---

## Modo 6 — `/issue fechar <N>`

Fechar Issue com motivo registrado.

1. `gh issue view <N>` pra contextualizar.
2. Pergunta:
   > "Por que fechar a Issue #67? (a) Resolvida; (b) Não vai fazer (won't fix); (c) Duplicada; (d) Outro motivo."
3. Pra (d), pede o motivo livre.
4. Preview:
   > "Vou fechar #67 com comentário: 'Resolvida pelo PR #42 — webhook agora trata array de signatários corretamente.' Confirma?"
5. Se sim:
   ```bash
   gh issue close <N> --comment "<motivo>"
   ```

---

## Diretrizes de comunicação

A skill é **conversacional, paciente, didática**. O time tá começando em GitHub workflow, então:

### Faça

- ✅ **Explique brevemente termos técnicos na primeira menção**: "PR (pull request) = pedido pra mergear mudanças de uma branch pra main".
- ✅ **Comente o que tá fazendo nos bastidores quando relevante**: "agora vou rodar `gh issue create` — é o comando do GitHub CLI que abre uma Issue sem precisar de browser".
- ✅ **Pergunte uma coisa por vez**, espere resposta antes da próxima.
- ✅ **Mostre preview** de toda ação que vai pro GitHub (Issues, comments, close). Editar antes é livre.
- ✅ **Aceite "voltar" e "cancelar"** a qualquer momento — não force fluxo linear.
- ✅ **Use pt-BR** em toda interação (a menos que o usuário escreva em outro idioma).

### Evite

- ❌ Sequência de 5 perguntas seguidas — sobrecarrega.
- ❌ Jargão sem explicação (PR, fork, rebase, cherry-pick, upstream, etc.).
- ❌ Markdown rebuscado nas perguntas — texto limpo é melhor.
- ❌ Criar Issue sem preview, mesmo se o usuário "tem certeza".
- ❌ Sugerir mudar branch protection, force push, ou outras ações destrutivas.

---

## Estrutura de uma Issue bem formada

Quando estruturar Body de Issue (modo `new`), use este template:

```markdown
## O que tá rolando
[1-3 frases, contexto pra quem não tava na conversa]

## Como reproduzir
1. ...
2. ...
3. ...

## Resultado esperado
[o que deveria acontecer]

## Resultado atual
[o que tá acontecendo]

## Notas extras
[print, log, link, ou trecho de código relevante]

## Sugestão (opcional)
[se o usuário deu opinião sobre como resolver]

---
_Criada via `/issue new` em $(date)._
```

Pra **feature/melhoria**:

```markdown
## Cenário / Quem precisa disso
[em qual fluxo de uso isso é útil]

## O que seria
[descrição da funcionalidade]

## Por que (valor)
[impacto pro usuário ou pro negócio]

## Critério de sucesso
[como saber que tá feito]

## Notas extras
[mockups, referências, sugestões técnicas]

---
_Criada via `/issue new` em $(date)._
```

---

## Templates por situação

Ver `references/templates.md` pra:
- Bug com stack trace
- Bug visual (com screenshot)
- Feature com mockup
- Discussão exploratória

Ver `references/workflow.md` pra:
- Fluxo completo Issue → /ship → PR → deploy (com analogias e desenhos ASCII pra time iniciante)
- Como Issue se relaciona com Discussions
- Quando NÃO criar Issue (coisas que devem virar Discussions ou conversa de chat)

---

## Encadeamento com outras skills

- **`/ship`**: chamada por `/issue trabalhar <N>`. Carrega Issue como contexto + cria branch + plano 🟡.
- **`/spec`**: não chamada diretamente. Mas se a Issue for sobre arquitetura/spec, sugerir abrir em GitHub Discussions categoria "Decisões" em vez de Issue.
- **`/deploy`**: nunca chamada por `/issue`. Deploy só roda no fim do `/ship`.

---

## Falhas e recuperação

| Cenário | Ação |
|---|---|
| `gh` não autenticado | Mostrar instrução `gh auth login`, parar. |
| Repo não acessível (404) | "Você tem acesso ao repo `pedrorezendefig/hospital-reunioes`? Confere com o admin." |
| Label não existe (Passo 7 cria com label que não tá no repo) | Cair pra "outras" sem label, avisar usuário. |
| Assignee não é collaborator | Avisar, deixar sem assignee, prosseguir. |
| Rede caída | Erro com mensagem clara, sugerir tentar de novo. |
| User cancela meio do fluxo | Confirmar "Cancelado, nada foi salvo no GitHub. Voltando." |

---

## Anti-padrões

- ❌ "Vou criar a Issue direto, sem preview, porque o usuário tem pressa." — Não. Preview é princípio. Pressa = explicar mais rápido, não pular safety net.
- ❌ "Vou abrir um formulário enorme pedindo título, body, labels, assignee, prioridade tudo de uma vez." — Não. Uma pergunta por vez.
- ❌ "Vou inferir o tipo a partir das primeiras palavras do usuário." — Não. Pergunte explicitamente. Inferir errado faz Issue mal categorizada.
- ❌ "Vou abrir Discussions pra qualquer dúvida sem perguntar." — Não. Ofereça, deixe o usuário escolher.
- ❌ "Vou ofuscar o `gh` CLI pra parecer mais clean." — Não. Mostrar o comando que vai rodar ensina o time. É educativo.

---

## Exemplos

### Exemplo 1 — Bug simples

```
Usuário: /issue new

Skill: Beleza, vamos registrar isso. Me conta o que tá rolando — pode ser bem informal, eu organizo depois.

Usuário: o webhook da clicksign tá quebrando quando tem mais de uma assinatura

Skill: Entendi. Isso parece mais um (a) bug — algo que tava funcionando e quebrou; (b) funcionalidade nova; (c) melhoria; (d) dúvida/discussão?

Usuário: a

Skill: Bug então. Em qual parte? Backend / Frontend / Supabase / Infra/Deploy / Docs?

Usuário: backend, é o handler do webhook

Skill: Backend, anotado. Como dá pra reproduzir? Tenta listar uns passos tipo "1. ato X, 2. acontece Y...".

Usuário: 1. cria reunião com 3 facilitadores 2. envia ata pra assinatura 3. o webhook retorna 500 na callback da clicksign

Skill: Tem algum print, log, ou trecho de código que ajuda? Pode colar aqui. (Se não tem, pula.)

Usuário: o log diz "TypeError: 'NoneType' object is not iterable" na linha 142 do webhooks.py

Skill: Stack trace registrado. Qual a urgência? (a) Alta — bloqueia uso; (b) Média — incomoda com workaround; (c) Baixa — quando der tempo.

Usuário: alta, prod tá fazendo isso agora

Skill: Quem vai trabalhar nisso? (a) eu mesmo; (b) pedroribbe; (c) deixa pra alguém pegar.

Usuário: pedroribbe

Skill:
═══ Preview da Issue ═══

Título:    [Bug] Webhook ClickSign retorna 500 em assinatura múltipla
Labels:    type:fix, area:backend, priority:high
Assignee:  @pedroribbe

Body:
## O que tá rolando
Webhook da ClickSign tá quebrando quando a ata tem mais de uma assinatura.

## Como reproduzir
1. Criar reunião com 3 facilitadores.
2. Enviar ata pra assinatura.
3. Webhook retorna 500 na callback da ClickSign.

## Notas extras
Log: `TypeError: 'NoneType' object is not iterable` na linha 142 de `webhooks.py`.

────────

Tá bom assim? (a) Sim, cria; (b) Quero editar X; (c) Cancelar.

Usuário: a

Skill: [executa gh issue create] ✅ Issue #67 criada: https://github.com/pedrorezendefig/hospital-reunioes/issues/67

pedroribbe vai receber push notification no GitHub Mobile já já. Próximo passo? (a) Trabalhar nela agora via /ship; (b) Deixar pra depois.

Usuário: deixa pra depois

Skill: Beleza. Issue tá registrada, pedroribbe ou outro membro pode pegar quando quiser via /issue trabalhar 67. Tchau!
```

### Exemplo 2 — Pegar Issue existente e trabalhar

```
Usuário: /issue trabalhar 67

Skill: Vou puxar a Issue #67.

[gh issue view 67]

Skill:
═══ Issue #67 ═══

Título:    [Bug] Webhook ClickSign retorna 500 em assinatura múltipla
Estado:    open · aberta 2 dias atrás por @pmrdef
Labels:    type:fix, area:backend, priority:high
Assignee:  @pedroribbe

Body:
[body completo formatado]

Comentários (1):
@pmrdef · 1 dia atrás: "Consegui reproduzir aqui. Acho que é no handler /webhooks/clicksign..."

────────

Issue importada pro contexto. Tipo da mudança: fix (peguei do label `type:fix`). Vou criar branch `fix/webhook-clicksign-500-67` e rodar /ship. Confirma?

Usuário: confirma

Skill: [invoca /ship "Webhook ClickSign retorna 500 em assinatura múltipla" --issue 67 --type fix]
```

---

## Por que essa skill existe

Time pequeno (3 pessoas) com 2 contratados que tão começando com GitHub workflow. Sem essa skill, eles teriam que:

1. Abrir browser, ir pra github.com/pedrorezendefig/hospital-reunioes/issues.
2. Clicar "New issue", saber escolher template (se houver).
3. Saber markdown pra estruturar body.
4. Saber qual label aplicar, qual assignee.
5. Saber clicar nos lugares certos.

Com essa skill, é **uma conversa**. O assistant pergunta, o usuário responde em português normal, o assistant estrutura e cria.

E pra Issues existentes, em vez de abrir browser → buscar → ler → copiar tudo pro Claude pra pedir ajuda, é só `/issue pegar 67` ou direto `/issue trabalhar 67` que importa contexto + começa trabalhar.

Resultado: time iniciante consegue manter Issues bem documentadas (futuro grato) e o workflow fica rápido (presente grato).
