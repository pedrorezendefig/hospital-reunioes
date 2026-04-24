# Plano — Simplificar skill `blueprint-sync` + docs do blueprint

## Contexto

A skill `blueprint-sync` atual é complexa demais para o estado real do projeto:

- Dispara automaticamente em todo commit via `.githooks/post-commit` (confuso pra iniciante em git; exige `git config core.hooksPath .githooks` depois de clonar; amenda commits silenciosamente; tem lock file pra evitar loop).
- Mantém 4 docs densos (`README`, `ARQUITETURA`, `FLUXOS`, `AMBIENTES`) somando ~800 linhas, com redundância entre si.
- Lógica interna de "mapeamento arquivo crítico → doc afetado" pesada e sujeita a bugs.

Decisão alinhada: **zerar a complexidade**. A skill vira 100% manual, tem um único propósito (escrever changelog humano a partir de commits), e os docs do blueprint fundem-se num único `README.md` enxuto.

**Objetivo:** qualquer pessoa que clonar o repo entende o sistema em 5 minutos lendo um único doc, e tem um changelog narrado em português quando invocar a skill.

---

## Estado final desejado

```
blueprint/
├── README.md              (~100 linhas, fundido: stack + fluxo + ambientes + convenções)
├── DEPLOY.md              (intacto — domínio da skill /deploy)
└── historico/
    └── 2026-04.md         (criado na 1ª execução da skill)

.githooks/                 (deletado)
```

```
~/.claude/skills/blueprint-sync/SKILL.md  (rescrito — só modo manual, só histórico)
```

---

## Arquivos a modificar

### Criar
- `blueprint/README.md` — versão fundida dos 4 docs (detalhes na §3)
- `blueprint/historico/.gitkeep` — pra commitar a pasta vazia

### Sobrescrever
- `/Users/pedrorezende/.claude/skills/blueprint-sync/SKILL.md` — rewrite completo

### Deletar
- `.githooks/post-commit` (e a pasta `.githooks/` se ficar vazia)
- `blueprint/ARQUITETURA.md`
- `blueprint/FLUXOS.md`
- `blueprint/AMBIENTES.md`

### Atualizar
- `CLAUDE.md` (raiz) — remover seção do hook, simplificar referência ao blueprint-sync

---

## 1. Nova `SKILL.md` — comportamento

**Invocação:** só manual, via `/blueprint-sync`. Sem argumentos.

**Execução (passo a passo):**

1. Determinar o **último SHA já registrado** no histórico:
   - Listar `blueprint/historico/*.md` (ordem reversa).
   - No arquivo mais recente, procurar a primeira linha `- \`<sha>\`` — esse é o último SHA logado.
   - Se não existe nenhum arquivo ainda: pegar os últimos 10 commits como ponto de partida.
2. Coletar commits novos:
   ```
   git log <ultimo_sha>..HEAD --pretty=format:"%H|%h|%ai|%an|%s|%b||END||"
   ```
3. Se lista vazia → sair silencioso ("sem commits novos desde `<sha>`").
4. Pra cada commit:
   - Extrair mês do `%ai` → `YYYY-MM`.
   - Gerar resumo em pt-BR (1-2 frases) explicando o *porquê*/*o quê* — não apenas repetir o subject. Usar o corpo (`%b`) se existir; senão, inferir do subject + diff resumido (`git show --stat <sha>`).
   - Agrupar commits por dia (`YYYY-MM-DD`).
5. Pra cada `YYYY-MM` com commits novos:
   - Abrir ou criar `blueprint/historico/YYYY-MM.md`.
   - Se o arquivo não existir, começar com header `# Histórico — YYYY-MM`.
   - Inserir entradas **no topo** (ordem reversa), agrupadas por dia, no formato:
     ```markdown
     ## 2026-04-23
     - `38a9a9a` chore(scripts): ajuste em bulk_import_atas
       Normaliza documento_id para evitar falso dedup quando departamento está ausente.
     - `b3909e2` refactor(admin): campos opcionais nos schemas
       Remove obrigatoriedade de campos admin que travavam cadastros parciais.
     ```
6. Report final ao usuário:
   - `blueprint/historico/2026-04.md — 3 commits adicionados`
   - Ou `sem commits novos` se nada.

**Regras:**
- **Idempotente** — invocar 2x sem commits novos = zero diff.
- **Não amenda nada, não commita nada** — apenas edita o arquivo. Usuário decide se commita o histórico.
- **Nunca toca** em `blueprint/README.md` ou `blueprint/DEPLOY.md`.
- **Nunca toca** no código.
- Sai **gracefully** em rebase/merge/cherry-pick.

---

## 2. Novo `blueprint/README.md` — estrutura

~100 linhas, 7 seções:

1. **O que é** (30s) — 5 facilitadores, ciclo reunião→ata→assinatura, estado atual (aguardando deploy).
2. **Stack** — tabela 3 linhas: backend (FastAPI + uv), frontend (Next.js 15 + pnpm), infra (Supabase self-hosted + Coolify/Hostinger). Integrações: OpenAI, ClickSign, Resend, Fireflies.
3. **Fluxo principal** — 1 `mermaid sequenceDiagram` condensado (áudio → transcrição → ata → ClickSign → pendências).
4. **Ambientes** — tabela LOCAL vs PRODUÇÃO com 6 linhas: backend URL, frontend URL, Supabase host, ClickSign base URL, email, SSL. Matriz de vars críticas de produção (5 linhas).
5. **Rotas e estrutura** — só os grupos: frontend (públicas/autenticadas/admin), backend (lista de routers). Sem detalhar endpoints.
6. **Slash commands** — tabela curta: `/deploy` (+ setup/status/rollback), `/blueprint-sync`, `/atualizar-app`, `/migrar-atas`, `/resetsupa`.
7. **Convenções e docs irmãos** — pt-BR, planos na raiz, commits convencionais. Ponteiros: `DEPLOY.md` (prod, skill /deploy) e `historico/` (changelog, skill /blueprint-sync).

**Fora:** detalhes de cada env var, lista exaustiva de buckets, diagramas de pipeline IA, lista de prompts, webhooks detalhados, decisões arquiteturais extensas, "o que NÃO existe". Essas coisas vivem no código.

---

## 3. Atualizar `CLAUDE.md` (raiz)

Mudanças:

- **Remover** toda a seção `## Hook post-commit (.githooks/post-commit)`.
- **Atualizar** a seção `## Deploy e blueprint`:
  - Remover "são atualizados após cada commit pelo hook post-commit que invoca /blueprint-sync".
  - Substituir por: "Demais docs do blueprint (`README`) são editados manualmente. `/blueprint-sync` é manual e só atualiza `blueprint/historico/` (changelog humano dos commits)."

---

## 4. Ordem de execução

1. Escrever novo `blueprint/README.md` (fundindo conteúdo dos 4 atuais).
2. Criar `blueprint/historico/.gitkeep`.
3. Deletar `blueprint/ARQUITETURA.md`, `blueprint/FLUXOS.md`, `blueprint/AMBIENTES.md`.
4. Deletar `.githooks/post-commit` e a pasta se ficar vazia.
5. Rescrever `~/.claude/skills/blueprint-sync/SKILL.md`.
6. Atualizar `CLAUDE.md` (raiz).
7. Commit único: `refactor(blueprint): simplifica skill para modo manual + funde docs`.
8. Testar: invocar `/blueprint-sync` → confirmar que `blueprint/historico/2026-04.md` é criado com os commits recentes.

---

## Verificação end-to-end

- [ ] `ls blueprint/` → só `README.md`, `DEPLOY.md`, `historico/`.
- [ ] `.githooks/` não existe.
- [ ] Fazer commit qualquer → nada dispara automaticamente.
- [ ] `/blueprint-sync` → cria `blueprint/historico/2026-04.md` com commits recentes, cada um com resumo em pt-BR.
- [ ] `/blueprint-sync` de novo sem novos commits → output "sem commits novos".
- [ ] Fazer 1 commit, `/blueprint-sync` → acrescenta só 1 entrada, no topo do dia atual.
- [ ] Ler só `blueprint/README.md` → entender o sistema sem abrir mais nada.
- [ ] `CLAUDE.md` não menciona hook nem sincronização automática.

---

## Arquivos críticos de referência

- `/Users/pedrorezende/.claude/skills/blueprint-sync/SKILL.md` — skill atual (alvo do rewrite)
- `/Users/pedrorezende/PedroDev/Hospital/.githooks/post-commit` — hook a deletar
- `/Users/pedrorezende/PedroDev/Hospital/blueprint/{README,ARQUITETURA,FLUXOS,AMBIENTES}.md` — 4 docs a fundir
- `/Users/pedrorezende/PedroDev/Hospital/CLAUDE.md` — instruções do projeto a atualizar
