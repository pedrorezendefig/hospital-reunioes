# GitHub Remote Setup — passo a passo guiado

Este documento cobre o **setup remoto no GitHub** pra o workflow do time de 3 (você + 2 contratados). Tudo aqui é feito uma única vez, após a migração local pra `docs/spec/` já estar concluída e mergeada na main.

Pré-requisitos:
- `gh` CLI instalado (`gh --version` >= 2.0)
- `gh auth status` retorna autenticado como você
- Você é o admin do repo
- Branch `spec-and-workflow-migration` já mergeada na `main` (ou pelo menos com PR aberto)
- Username GitHub dos 2 contratados em mãos (`pedroribbe` confirmado, segundo a definir)
- **App "GitHub" instalado no celular** (iOS App Store ou Android Play Store, free, oficial) — vai receber push notifications de PRs, reviews, CI, Discussions.

Tempo estimado: **30-45 minutos**, fazendo com calma.

---

## Passo 1 — Convidar collaborators

Você precisa do username GitHub dos 2 contratados. Pergunta pra eles antes de começar.

```bash
# Substitua <USERNAME1> e <USERNAME2> pelos handles GitHub deles
gh api -X PUT "/repos/pmrdef/hospital/collaborators/<USERNAME1>" \
  --raw-field permission=push

gh api -X PUT "/repos/pmrdef/hospital/collaborators/<USERNAME2>" \
  --raw-field permission=push
```

> `permission=push` dá acesso de write (cria branches, abre PRs, comenta). Não dá admin (não muda settings do repo). É o nível certo pra contratado.

Conferir:

```bash
gh api "/repos/pmrdef/hospital/collaborators" --jq '.[].login'
```

Cada contratado vai receber email com o convite. Eles precisam aceitar antes de conseguir clonar/push.

---

## Passo 2 — Criar labels

Labels padronizados pros PRs/Issues. O `/ship` aplica automaticamente.

```bash
# Type labels (tipo de mudança)
gh label create "type:fix"      --color "d73a4a" --description "Bug fix"
gh label create "type:feature"  --color "0e8a16" --description "Nova funcionalidade ou melhoria"
gh label create "type:chore"    --color "fbca04" --description "Manutenção (deps, build, lint, doc)"
gh label create "type:refactor" --color "1d76db" --description "Refactor sem mudança comportamental"
gh label create "type:docs"     --color "0075ca" --description "Documentação"
gh label create "type:test"     --color "5319e7" --description "Testes"
gh label create "type:spec"     --color "a370f7" --description "Mudança em docs/spec/ ou skills"

# Area labels (parte do sistema)
gh label create "area:backend"   --color "ededed" --description "hospital-reunioes/backend/"
gh label create "area:frontend"  --color "ededed" --description "hospital-reunioes/frontend/"
gh label create "area:supabase"  --color "ededed" --description "Migrations, schema, RLS"
gh label create "area:infra"     --color "ededed" --description "Coolify, .github/, deploy"
gh label create "area:spec"      --color "ededed" --description "docs/spec/"
gh label create "area:skills"    --color "ededed" --description ".claude/skills/"
gh label create "area:docs"      --color "ededed" --description "docs/ não-spec, README, CLAUDE.md"

# Priority labels
gh label create "priority:high"   --color "b60205" --description "Bloqueador, fazer agora"
gh label create "priority:medium" --color "fbca04" --description "Próxima sprint"
gh label create "priority:low"    --color "0e8a16" --description "Quando der tempo"

# Workflow labels
gh label create "status:wip"      --color "fbca04" --description "Em progresso, não mergeable ainda"
gh label create "status:blocked"  --color "b60205" --description "Aguardando algo externo"
gh label create "needs:review"    --color "0e8a16" --description "Pronto pra review humana"
```

Conferir:

```bash
gh label list --limit 100
```

---

## Passo 3 — Branch protection na `main`

A regra principal: tudo entra via PR, com 1 approval (self ou outro), CI verde, squash merge.

```bash
gh api -X PUT "/repos/pmrdef/hospital/branches/main/protection" \
  --raw-field "required_status_checks[strict]=true" \
  --raw-field "required_status_checks[contexts][]=Backend Lint, Format & Tests" \
  --raw-field "required_status_checks[contexts][]=Frontend Lint & Type Check" \
  --raw-field "enforce_admins=false" \
  --raw-field "required_pull_request_reviews[required_approving_review_count]=1" \
  --raw-field "required_pull_request_reviews[dismiss_stale_reviews]=true" \
  --raw-field "required_pull_request_reviews[require_code_owner_reviews]=false" \
  --raw-field "restrictions=null" \
  --raw-field "allow_force_pushes=false" \
  --raw-field "allow_deletions=false" \
  --raw-field "required_linear_history=true" \
  --raw-field "block_creations=false" \
  --raw-field "required_conversation_resolution=true"
```

> `enforce_admins=false`: você (admin) pode bypassar em emergência. Mude pra `true` se quiser ser estrito consigo mesmo.

> `required_status_checks.contexts`: nomes EXATOS dos jobs no `.github/workflows/ci.yml`. Hoje são "Backend Lint, Format & Tests" e "Frontend Lint & Type Check". Se você renomear os jobs, atualize aqui.

> `required_linear_history=true`: força squash merge. Sem merge commits poluindo o histórico.

> `required_approving_review_count=1`: 1 approval. Self-approval é permitido por default (o GitHub não distingue entre self e outro user nesse setting).

Conferir:

```bash
gh api "/repos/pmrdef/hospital/branches/main/protection" --jq '.required_pull_request_reviews.required_approving_review_count'
# Deve retornar: 1
```

---

## Passo 4 — Habilitar squash merge default

```bash
gh api -X PATCH "/repos/pmrdef/hospital" \
  --raw-field allow_squash_merge=true \
  --raw-field allow_merge_commit=false \
  --raw-field allow_rebase_merge=false \
  --raw-field delete_branch_on_merge=true \
  --raw-field squash_merge_commit_title="PR_TITLE" \
  --raw-field squash_merge_commit_message="COMMIT_MESSAGES"
```

Isso garante:
- Só squash merge (1 commit por PR na main).
- Branch deletada automaticamente depois do merge.
- Título do commit final = título do PR.

---

## Passo 5 — GitHub Discussions + GitHub Mobile (notificações)

Sem Discord. O time usa **GitHub Mobile app** pra push notifications nativas (PR aberto, CI verde, comentário em PR, Discussions) e **GitHub Discussions** como canal de "chat persistente" dentro do próprio repo. Identificação por projeto sai de graça (cada notificação chega com nome do repo).

### 5.1 Habilitar Discussions no repo

```bash
gh api -X PATCH "/repos/pmrdef/hospital" --raw-field has_discussions=true
```

Conferir:
```bash
gh api "/repos/pmrdef/hospital" --jq '.has_discussions'
# Deve retornar: true
```

### 5.2 Criar categorias iniciais

O `gh` CLI **não** suporta criar Discussion categories ainda (só GraphQL, que é mais chato). Mais simples via UI uma vez:

1. Abrir `https://github.com/pmrdef/hospital/discussions`.
2. Clicar no ⚙ "Manage categories" (canto superior direito).
3. As 4 categorias default vêm como `Announcements`, `General`, `Ideas`, `Polls`, `Q&A`, `Show and tell`. **Apagar** as que não vai usar, e renomear pra:
   - **Anúncios** (formato: announcement, só admin posta) — deploy notable, breaking change, nova versão.
   - **Ideias** (formato: open-ended) — "estou pensando em X, alguma objeção?".
   - **Dúvidas** (formato: Q&A) — perguntas técnicas com resposta marcada.
   - **Decisões** (formato: announcement, qualquer um posta) — ADRs leves, decisões de arquitetura registradas.

> Tempo: ~3 minutos. Tem que fazer pela UI mesmo. A boa notícia: depois nunca mais precisa mexer.

### 5.3 Cada um instala GitHub Mobile + Watch

Cada membro do time (você + `pedroribbe` + outro):

1. Instalar **GitHub** no celular:
   - iOS: https://apps.apple.com/app/github/id1477376905
   - Android: https://play.google.com/store/apps/details?id=com.github.android
2. Login com a conta GitHub deles.
3. Abrir o repo `pmrdef/hospital` no app.
4. Clicar no **🔔 Watch** (canto superior direito) → escolher **All Activity** (recebe push de tudo) ou **Custom** (escolhe os eventos).
   - Recomendado: **Custom** com pelo menos: Issues, Pull requests, Releases, Discussions.
5. Em Profile → Settings → Notifications → ✅ Push notifications.

Resultado: cada notificação chega no celular com prefixo `pmrdef/hospital · ...` (PR aberto, mergeado, CI falhou, novo comentário, Discussion criada). Pra múltiplos projetos futuros, mesmo padrão — cada repo identificado pelo nome no header da notificação.

### 5.4 Testar end-to-end

```bash
gh issue create --title "Teste GitHub Mobile" \
                --body "Issue só pra confirmar que push notification chega no celular dos 3 membros do time."
```

Se aparecer push notification no celular **dos 3** em ~30s: ✅ setup OK.

```bash
gh issue close <NUMERO> --comment "Notif OK, fechando."
```

### 5.5 (Opcional) Discord webhook

Se um dia quiser adicionar Discord também (paralelo, não substitui GitHub Mobile), o `/ship` já suporta nativo. Setup completo no Apêndice no final desse documento.

> Por enquanto: pula. Time decidiu GitHub Mobile + Discussions como default.

---

## Passo 6 — GitHub Project board

Hoje o `gh` CLI não suporta criar Projects v2 (novo formato) facilmente via API. Mais simples fazer via UI uma vez:

1. Abre https://github.com/users/pmrdef/projects/new
2. Template: **Board**.
3. Nome: "Hospital Sprint".
4. Linka com o repo Hospital (Settings → Manage access → Repositories).
5. Default columns: `Todo`, `In Progress`, `Done`. Renomeie pra:
   - `Backlog` (idéias, sem prioridade)
   - `A fazer` (priorizada, sem assignee)
   - `Em progresso` (alguém pegou)
   - `Em review` (PR aberto)
   - `Concluído` (mergeado + deploy)
6. Em "Workflows", habilite:
   - **Item closed** → move pra `Concluído`
   - **Pull request merged** → move pra `Concluído`
   - **Pull request opened** → move pra `Em review`

Quando uma Issue novinha for criada com `gh issue create`, ela cai em `Backlog` por default. Você arrasta pra `A fazer` quando priorizar.

---

## Passo 7 — Validação end-to-end

Antes de declarar setup feito, valida o fluxo completo:

### 7.1 Issue + PR de teste

```bash
# Cria uma Issue dummy
ISSUE_NUM=$(gh issue create \
  --title "chore: testar workflow end-to-end" \
  --body "Issue de teste pra validar fluxo Issue → PR → review → merge." \
  --label "type:chore,area:docs,priority:low" \
  --assignee @me \
  | grep -oE '[0-9]+$')

echo "Issue criada: #$ISSUE_NUM"

# Roda o /ship pra criar branch + PR + merge automaticamente
# (no Claude Code, na pasta Hospital)
/ship "testar workflow end-to-end" --issue $ISSUE_NUM --type chore --no-deploy
```

Observar:
- ✅ Branch `chore/testar-workflow-end-to-end-$ISSUE_NUM` criada
- ✅ Chronicle 🟡 criado em `docs/spec/chronicles/`
- ✅ PR aberto com template preenchido
- ✅ `/code-review` e `/security-review` rodaram
- ✅ PR aprovado (self) e mergeado
- ✅ Issue fechada automaticamente (closes)
- ✅ Discord recebeu notificação no `#hospital-dev`

### 7.2 Branch protection ativa

Tenta push direto na main (deve falhar):

```bash
git checkout main
echo "teste" > _teste_protection.txt
git add _teste_protection.txt
git commit -m "teste protection"
git push origin main
# Deve retornar: "remote rejected" / "protected branch"
git reset --hard HEAD~1  # desfaz commit local
```

### 7.3 Convidados acessam

Cada contratado:
1. Aceita convite por email do GitHub.
2. `gh repo clone pmrdef/hospital`.
3. `cd hospital && /spec status` (deve retornar OK).
4. Instala GitHub Mobile no celular e marca o repo como Watching (Passo 5.3 acima).
5. Abre uma Issue dummy via `gh issue create`.
6. Confere que recebe push notification no celular em ~30s.
7. Abre Discussions → cria thread teste na categoria "Dúvidas" → confere que os outros 2 recebem notificação.

---

## Apêndice — Como reverter

Se algo der errado e quiser desfazer tudo:

```bash
# Remover collaborators
gh api -X DELETE "/repos/pmrdef/hospital/collaborators/<USERNAME>"

# Remover branch protection
gh api -X DELETE "/repos/pmrdef/hospital/branches/main/protection"

# Desabilitar Discussions (preserva threads existentes, só esconde a aba)
gh api -X PATCH "/repos/pmrdef/hospital" --raw-field has_discussions=false

# Apagar labels
for label in $(gh label list --limit 100 --json name --jq '.[].name'); do
  gh label delete "$label" --yes
done

# Deletar Project board: via UI (Settings → Delete project)
```

---

## Checklist final

Marque conforme conclui:

- [ ] Passo 1: collaborators adicionados (`pedroribbe` + segundo), aceitos
- [ ] Passo 2: ~17 labels criados
- [ ] Passo 3: branch protection ativa na main (1 approval, status checks, linear, no force push)
- [ ] Passo 4: squash merge default + delete branch on merge
- [ ] Passo 5.1: Discussions habilitado no repo (`has_discussions=true`)
- [ ] Passo 5.2: 4 categorias criadas (Anúncios, Ideias, Dúvidas, Decisões)
- [ ] Passo 5.3: cada membro instalou GitHub Mobile e marcou Watching
- [ ] Passo 5.4: teste de push notification passou
- [ ] Passo 6: GitHub Project "Hospital Sprint" criado com 5 colunas
- [ ] Passo 7.1: `/ship` end-to-end funcionou (Issue → PR → merge → push notif no Mobile dos 3)
- [ ] Passo 7.2: push direto na main bloqueado
- [ ] Passo 7.3: cada contratado clonou + rodou `/spec status` OK + recebeu notif de Discussion teste

Depois disso, o time tá pronto pra trabalhar. Cada um abre Issues no GitHub Project ou via `gh issue create`, pega assigning pra si, roda `/ship "descrição" --issue <N>`, e o resto é automatizado.

---

## Quem mexe em quê (resumo)

| Pessoa | Pode | Não pode |
|---|---|---|
| Você (admin) | Tudo. Inclusive bypassar branch protection em emergência. | Nada (você é dono). |
| Contratado A/B | Criar Issues, criar branches, abrir PRs, aprovar PRs (incluindo self), mergear depois de approval+CI, rodar /deploy. | Mudar settings do repo, deletar branches protegidas, force push na main. |

---

## Apêndice — Discord opcional (não recomendado por enquanto)

Se um dia o time decidir que GitHub Mobile + Discussions não basta e quiser adicionar Discord também:

```bash
# 1. No Discord: criar canal #hospital-dev, abrir Settings → Integrations → Webhooks → New Webhook.
#    Copiar URL.

# 2. Registrar webhook no GitHub (adiciona "/github" no fim pra Discord parsear).
DISCORD_URL_WITH_GITHUB="<DISCORD_WEBHOOK_URL>/github"

gh api -X POST "/repos/pmrdef/hospital/hooks" \
  --raw-field "name=web" \
  --raw-field "active=true" \
  --raw-field "events[]=push" \
  --raw-field "events[]=pull_request" \
  --raw-field "events[]=pull_request_review" \
  --raw-field "events[]=issues" \
  --raw-field "events[]=issue_comment" \
  --raw-field "events[]=workflow_run" \
  --raw-field "events[]=release" \
  --raw-field "config[url]=$DISCORD_URL_WITH_GITHUB" \
  --raw-field "config[content_type]=json" \
  --raw-field "config[insecure_ssl]=0"

# 3. Guardar URL pro /ship usar:
mkdir -p ~/.config/hospital
echo "<DISCORD_WEBHOOK_URL>" > ~/.config/hospital/discord-webhook.url
chmod 600 ~/.config/hospital/discord-webhook.url
```

> ⚠️ URL não tem auth — qualquer um com ela pode postar no canal. Não commitar nunca. Compartilhar via password manager.

Os contratados repetem o passo 3 nas máquinas deles. O `/ship` detecta automaticamente e passa a postar resumos no Discord ao final de cada deploy. Sem essa URL, ele faz skip silencioso (sem erro).

---

Boa sorte! Quando terminar esses 7 passos, deleta este arquivo (`rm GITHUB-SETUP.md`) ou move pra `docs/operacional/historico/` se quiser preservar.
