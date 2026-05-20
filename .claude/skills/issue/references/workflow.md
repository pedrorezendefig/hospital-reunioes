# Workflow GitHub explicado pra quem tá começando

Este doc é pro time iniciante (3 pessoas) entender o ciclo completo da Issue ao deploy. A skill `/issue` referencia este arquivo quando o usuário pergunta "como funciona isso?" ou "o que vai acontecer depois?".

---

## O ciclo end-to-end em uma imagem

```
       você fala                a Issue vira         o /ship faz                  Coolify
       o problema               registro             tudo de uma vez              entrega
          │                        │                      │                          │
          v                        v                      v                          v
    ┌──────────┐  /issue new  ┌─────────┐  /ship   ┌──────────┐  /deploy ship  ┌─────────┐
    │ conversa │ ───────────> │ Issue   │ ───────> │ PR + CI  │ ─────────────> │ produção│
    │ informal │              │ no repo │          │ + review │                │ healthy │
    └──────────┘              └─────────┘          └──────────┘                └─────────┘
          │                        │                      │                          │
          └────────────────────────┴──────────────────────┴──────────────────────────┘
                            push notification no GitHub Mobile
                            chega pros 3 do time em cada passo
```

---

## Vocabulário básico (pra não se perder)

| Termo | O que é | Analogia |
|---|---|---|
| **Repo** | O projeto inteiro versionado no GitHub | Uma pasta gigante na nuvem com histórico de tudo |
| **Branch** | Uma cópia paralela do código pra mexer sem afetar a versão "oficial" | Um caderno de rascunho. A versão oficial é a "main". |
| **Commit** | Uma versão salva das mudanças com mensagem explicativa | Um ponto de salvamento num jogo |
| **Push** | Mandar os commits locais pro GitHub remoto | Sincronizar com a nuvem |
| **PR (Pull Request)** | Pedido formal pra mergear (fundir) uma branch na main | "Olha, terminei esse pedaço. Posso colar no oficial?" |
| **Merge** | Aceitar o PR e juntar o código na main | Apertar o "OK" do PR |
| **Issue** | Registro persistente de bug, feature ou tarefa | Post-it que não some |
| **Discussions** | Fórum dentro do repo pra discussões longas | WhatsApp group, mas indexado e pesquisável |
| **Label** | Etiqueta colorida em Issue/PR | Tag pra filtrar (tipo "alta prioridade") |
| **Assignee** | Pessoa responsável pela Issue/PR | Quem vai fazer |
| **CI** | Continuous Integration. Roda testes automaticamente em cada PR | Robô que confere se nada quebrou |
| **Squash merge** | Junta todos os commits da branch em 1 só ao mergear | "Resumir a história desse caderno em 1 parágrafo" |
| **Self-approval** | Aprovar o próprio PR (que o time decidiu permitir) | "Eu confio em mim mesmo, libera" |

---

## Quando usar cada coisa

```
╔══════════════════════════════════════════════════════════════╗
║  TIPO DE CONTEÚDO              →  ONDE COLOCAR               ║
╠══════════════════════════════════════════════════════════════╣
║  Bug específico, acionável     →  Issue (`/issue new`)       ║
║  Feature nova, acionável        →  Issue (`/issue new`)       ║
║  Dúvida técnica rápida          →  Discussions "Dúvidas"     ║
║  Discussão arquitetura          →  Discussions "Ideias"      ║
║  Decisão registrada             →  Discussions "Decisões"    ║
║  Anúncio (deploy notable)       →  Discussions "Anúncios"    ║
║  Tarefa pessoal não-código      →  Obsidian/Notion           ║
║  Conversa de "tô fazendo X"     →  Comentário no PR aberto   ║
║  Documentação que falta         →  Issue "type:docs"          ║
╚══════════════════════════════════════════════════════════════╝
```

A skill `/issue` ajuda a decidir. Se você descreve algo e a skill achar que cabe melhor em Discussions, ela sugere.

---

## Fluxo completo (com analogia)

**Imagine uma cozinha de restaurante.** O ciclo do GitHub é parecido com o ciclo de um pedido:

### 1. Cliente faz pedido → `/issue new`

> "Tem um problema no webhook, tá quebrando quando manda 3 facilitadores."

Você (cliente) fala com o atendente (skill `/issue`). O atendente faz perguntas pra entender direito (tipo, área, prioridade). O atendente anota o pedido formalmente (Issue criada com título, body, labels). O pedido vai pro mural da cozinha (Issues abertas do repo).

### 2. Cozinheiro pega o pedido → `/issue trabalhar 67`

Alguém do time (pode ser você mesmo ou outro) vê o pedido no mural e diz "eu pego". Roda `/issue trabalhar 67` que:
- Importa o pedido pra contexto (a skill lê a Issue inteira pro Claude saber o que precisa fazer).
- Aciona o cozinheiro (skill `/ship`) automaticamente.

### 3. Cozinheiro cozinha → `/ship` faz tudo

O cozinheiro (`/ship`) faz, sequencialmente:

a. **Pega utensílios novos** (cria branch separada do main pra mexer)
b. **Planeja o prato** (cria chronicle 🟡 com plano detalhado, e pausa pra você editar)
c. **Cozinha** (você escreve o código que resolve o problema)
d. **Empacota** (commit das mudanças com mensagem clara)
e. **Manda pra entrega** (push pra GitHub e abre PR)
f. **Gerente prova** (rodas `/code-review` + `/security-review` automaticamente)
g. **Aprova ou rejeita** (se review passa, aprova sozinho — self-approval)
h. **Cola no cardápio oficial** (mergea o PR na main, squash)
i. **Entrega ao cliente** (deploy via Coolify pra produção)
j. **Atualiza o livro de receitas** (regenera `docs/spec/` via `/spec update`)

Tudo isso dura **~25 minutos** wall-clock. Você fica preso só nos passos b/c (planejamento + código).

### 4. Cliente recebe → push notification no GitHub Mobile

Em cada passo, **todos os 3 do time** recebem push notification no GitHub Mobile:
- "pmrdef/hospital · PR #42 opened by pedroribbe"
- "pmrdef/hospital · CI passed on PR #42"
- "pmrdef/hospital · PR #42 merged into main"
- "pmrdef/hospital · Deploy 890b149 healthy" (notificação custom do /ship, se Discord/webhook configurado)

### 5. Cliente faz feedback → Comentários em PR ou Discussions

Se você ou outro do time quer revisar **depois do deploy** (porque com self-approval ninguém precisa aprovar antes), abre o PR pelo GitHub Mobile e comenta. Pode ser "tava ok" ou "Vamos revisitar isso na próxima sprint".

Se a mudança gerar uma discussão maior ("acho que precisa repensar essa arquitetura"), aí cria thread em Discussions "Ideias" linkando o PR.

---

## "Eu tô perdido, e agora?"

Se em qualquer momento você não souber o que fazer:

1. **Pergunta pro Claude direto na conversa**. Tipo "tô na branch X, não sei se commito ou se faço outra coisa". Ele lê o estado, te orienta.
2. **Roda `/issue listar`** pra ver o que tá aberto. Se algo te chama atenção, `/issue pegar <N>`.
3. **Lê o último PR mergeado** pra ver o padrão: `gh pr list --state merged --limit 1`.
4. **Vai pro `docs/spec/`** que tem o sistema todo documentado em prosa (gerado automaticamente pelo REVERSA).
5. **Pergunta no Discussions** categoria "Dúvidas" — outros do time podem responder, e fica registrado pro futuro.

---

## "Onde tudo isso vive?"

```
~/PedroDev/Hospital/
├── .claude/skills/
│   ├── issue/          ← essa skill aqui
│   ├── ship/           ← orquestrador do ciclo completo
│   ├── deploy/         ← deploy Coolify
│   ├── spec/           ← regenerar docs/spec/
│   └── atualizar-app/  ← dev local
│
├── docs/spec/          ← especificação executável (auto-gerada)
│   ├── architecture.md
│   ├── chronicles/     ← 1 MD por mudança (🟡 = plano, 🟢 = healthy, 🔴 = falha)
│   ├── CHANGELOG.md    ← cronologia flat
│   └── deploy/         ← project.json, state.json (estado da prod)
│
├── hospital-reunioes/
│   ├── backend/        ← FastAPI
│   ├── frontend/       ← Next.js 15
│   └── supabase/       ← migrations + schema
│
└── CLAUDE.md           ← regras do projeto, lidas em toda conversa
```

E no GitHub:

```
github.com/pmrdef/hospital/
├── /issues             ← Issues abertas e fechadas
├── /pulls              ← PRs abertos, mergeados, fechados
├── /discussions        ← Anúncios, Ideias, Dúvidas, Decisões
├── /actions            ← Logs do CI (rodas de testes em cada PR)
└── /projects/...       ← Board "Hospital Sprint" (Backlog → A fazer → ...)
```

Tudo isso espelhado offline no clone local. `git pull` sincroniza.

---

## Erros comuns de iniciante (com solução)

| Sintoma | Causa | Solução |
|---|---|---|
| "Não consigo dar push" | Branch protection na main, push direto bloqueado | Trabalhar em branch separada, abrir PR. `/ship` faz isso |
| "Merge conflict" | Outra pessoa mexeu no mesmo arquivo | `git pull origin main` antes de continuar; se conflito, pedir ajuda |
| "Issue não fechou sozinha" | PR não tinha "Closes #N" no body | Editar PR e adicionar; ou fechar manual via `gh issue close N` |
| "CI tá vermelho" | Testes quebraram ou lint falhou | Olhar log no Actions, corrigir, commitar de novo na mesma branch |
| "Não vi notificação no celular" | Não tá com repo em Watching | Abrir repo no GitHub Mobile, clicar 🔔 → All Activity |
| "Discord não posta mais nada" | Webhook não configurado (default do time agora) | É esperado. Time usa GitHub Mobile + Discussions |

---

## TLDR pro time iniciante

1. **Bug ou feature?** → `/issue new`. Skill faz perguntas, cria Issue.
2. **Vai trabalhar?** → `/issue trabalhar <N>`. Skill importa contexto, chama `/ship`.
3. **Dúvida ou discussão?** → GitHub Discussions (no celular ou no site).
4. **Recebeu notificação?** → Clica, vai pro GitHub Mobile, vê o que rolou.
5. **Tudo no GitHub Mobile + Claude Code.** Sem Discord, sem Slack.

Resto a skill ensina conforme acontece.
