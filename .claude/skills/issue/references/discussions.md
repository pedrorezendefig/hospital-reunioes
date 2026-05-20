# GitHub Discussions via gh CLI + GraphQL

GitHub Discussions é fórum dentro do repo, alternativa a Issue pra coisas que **não são acionáveis** (dúvidas, ideias, decisões). A skill `/issue` sugere Discussions quando o conteúdo do usuário cabe melhor lá.

O `gh` CLI **não tem comandos diretos** pra Discussions (até v2.88, abr/2026). Tudo passa por GraphQL via `gh api graphql`.

---

## Operações básicas

### Listar categorias do repo

```bash
gh api graphql -f query='
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussionCategories(first: 25) {
      nodes { id name slug emoji description }
    }
  }
}' -f owner=pmrdef -f name=hospital | jq '.data.repository.discussionCategories.nodes'
```

Retorna algo como:

```json
[
  { "id": "DIC_kwDOAbc123", "name": "Anúncios", "slug": "announcements", ... },
  { "id": "DIC_kwDOAbc456", "name": "Ideias", "slug": "ideas", ... },
  { "id": "DIC_kwDOAbc789", "name": "Dúvidas", "slug": "q-a", ... },
  { "id": "DIC_kwDOAbc012", "name": "Decisões", "slug": "decisions", ... }
]
```

Cacheia os IDs — não muda.

### Pegar ID do repo

```bash
gh repo view pmrdef/hospital --json id --jq .id
# Retorna: R_kgDOAbc...
```

Cacheia o ID — não muda.

### Criar Discussion

```bash
REPO_ID="R_kgDOAbc..."
CATEGORY_ID="DIC_kwDOAbc456"  # Ideias

gh api graphql -f query='
mutation CreateDiscussion($repoId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
  createDiscussion(input: { repositoryId: $repoId, categoryId: $categoryId, title: $title, body: $body }) {
    discussion { id url number }
  }
}' \
  -f repoId="$REPO_ID" \
  -f categoryId="$CATEGORY_ID" \
  -f title="Repensar arquitetura do webhook" \
  -f body="$BODY_MARKDOWN" | jq '.data.createDiscussion.discussion'
```

Retorna `{id, url, number}` — usa o `url` pra mostrar pro usuário e o `number` pra referenciar depois.

### Listar Discussions abertas

```bash
gh api graphql -f query='
query($owner: String!, $name: String!) {
  repository(owner: $owner, name: $name) {
    discussions(first: 30, orderBy: {field: UPDATED_AT, direction: DESC}) {
      nodes {
        number title category { name } author { login } createdAt updatedAt
        url comments { totalCount }
      }
    }
  }
}' -f owner=pmrdef -f name=hospital | jq '.data.repository.discussions.nodes'
```

### Pegar Discussion específica (com comentários)

```bash
gh api graphql -f query='
query($owner: String!, $name: String!, $number: Int!) {
  repository(owner: $owner, name: $name) {
    discussion(number: $number) {
      title body category { name } author { login } createdAt url
      comments(first: 50) {
        nodes { body author { login } createdAt }
      }
    }
  }
}' -f owner=pmrdef -f name=hospital -F number=42 | jq '.data.repository.discussion'
```

### Comentar em Discussion

```bash
gh api graphql -f query='
mutation AddComment($discussionId: ID!, $body: String!) {
  addDiscussionComment(input: {discussionId: $discussionId, body: $body}) {
    comment { id url }
  }
}' -f discussionId="$DISCUSSION_ID" -f body="$COMMENT"
```

---

## Quando sugerir Discussions em vez de Issue

A skill `/issue` deve sugerir Discussions quando:

1. **Não tem ação clara** ("o que vocês acham de migrar pra X?", "tô considerando Y").
2. **É dúvida técnica genérica** ("como funciona o flow de auth?").
3. **É decisão arquitetural** que precisa registro ("decidimos não usar Redis").
4. **É anúncio** ("subi versão nova", "breaking change na próxima semana").

Categorias do repo:

| Categoria | Quando usar | Formato |
|---|---|---|
| **Anúncios** | Comunicado importante, deploy notable | Announcement (só admin posta) |
| **Ideias** | Brainstorm, "estou pensando em..." | Open-ended |
| **Dúvidas** | Pergunta técnica com resposta marcável | Q&A |
| **Decisões** | ADR leve, registrando decisão tomada | Announcement |

A skill mapeia o conteúdo do usuário pra categoria automaticamente, mas pergunta antes de criar.

---

## Bootstrap: descobrir IDs uma vez

A skill faz cache local dos IDs (repo + categorias). Pode salvar em `~/.cache/hospital-skill/discussions.json`:

```json
{
  "repo_id": "R_kgDOAbc...",
  "categories": {
    "Anúncios": "DIC_kwDOAbc123",
    "Ideias": "DIC_kwDOAbc456",
    "Dúvidas": "DIC_kwDOAbc789",
    "Decisões": "DIC_kwDOAbc012"
  },
  "cached_at": "2026-05-20T14:30:00Z"
}
```

Se cache > 7 dias, re-busca. Se categorias mudarem (renomear via UI), invalida cache na próxima execução com erro "Categoria X não encontrada — recarregando cache".
