# Templates por situação

Estes são templates de body de Issue que a skill `/issue` usa de acordo com o tipo identificado. Ajuste o tom mas mantenha a estrutura — o time se acostuma a procurar info nas mesmas seções.

---

## Bug genérico

```markdown
## O que tá rolando
[1-3 frases descrevendo o sintoma]

## Como reproduzir
1. ...
2. ...
3. ...

## Resultado esperado
[o que deveria acontecer]

## Resultado atual
[o que tá acontecendo]

## Ambiente
- Local / Produção: [qual]
- Browser / Device (se frontend): [se aplicável]
- Versão / commit: [se souber]

## Notas extras
[print, log, link, ou trecho de código relevante]

---
_Criada via `/issue new`._
```

---

## Bug com stack trace

Quando o usuário cola um stack trace ou log de erro:

```markdown
## O que tá rolando
[contexto]

## Como reproduzir
1. ...

## Erro
```
[stack trace ou log completo, em bloco de código]
```

## Arquivo / linha (se identificável)
`<path>:<linha>`

## Hipótese inicial (opcional)
[se o usuário deu opinião sobre causa]

---
_Criada via `/issue new`._
```

---

## Bug visual

Quando há print de tela:

```markdown
## O que tá rolando
[descrição]

## Screenshot
![screenshot](URL_OU_PATH)

## Como reproduzir
1. ...

## Resultado esperado
[descrição ou referência a mockup]

## Páginas afetadas
- [ ] `/reunioes/calendario`
- [ ] `/atas/<id>`
- [ ] Outra: ...

---
_Criada via `/issue new`._
```

> Nota: pra anexar print, usar `gh issue create --body-file` apontando pra arquivo que tenha o markdown com a imagem em URL pública. Ou subir a imagem como anexo do GitHub via UI (gh CLI ainda não suporta isso bem). Por enquanto, peça pro usuário colar o link da imagem ou descrição textual.

---

## Feature nova

```markdown
## Cenário / Quem precisa disso
[em qual fluxo de uso isso é útil. Persona: facilitador / diretor / colaborador]

## O que seria
[descrição da funcionalidade — comportamento esperado]

## Por que (valor)
[impacto pro usuário ou pro negócio. "Hoje o facilitador precisa fazer X manualmente" → "com isso, ele faz só Y"]

## Critério de sucesso
- [ ] Critério 1
- [ ] Critério 2

## Notas técnicas (opcional)
[mockups, referências, sugestões de implementação]

---
_Criada via `/issue new`._
```

---

## Melhoria / refactor

```markdown
## O que existe hoje
[1-3 frases descrevendo o comportamento atual]

## O que precisa mudar
[1-3 frases descrevendo o comportamento desejado]

## Por que
[motivação: UX ruim, performance, dívida técnica, novo requisito]

## Compatibilidade
- [ ] Funciona pra uso existente sem regressão
- [ ] Precisa migration de dados? [sim/não]
- [ ] Precisa coordenação com outro time? [sim/não]

---
_Criada via `/issue new`._
```

---

## Documentação faltando

```markdown
## O que falta documentar
[seção / fluxo / API endpoint / componente]

## Onde a doc deveria viver
- [ ] `docs/spec/...`
- [ ] `README.md`
- [ ] `CLAUDE.md`
- [ ] Comentário no código
- [ ] Outro: ...

## Por que importa
[quem se beneficia: novo dev, contratado, time futuro, agent IA]

## Escopo
[só essa seção / fluxo todo / API completa]

---
_Criada via `/issue new`._
```

---

## Discussão exploratória (sugerir Discussions em vez)

Quando o usuário descreve algo do tipo "estou pensando em mudar arquitetura de X" ou "será que vale a pena adotar Y", a skill **deve sugerir GitHub Discussions** em vez de Issue:

> "Isso parece uma discussão exploratória (não tem ação clara ainda). GitHub Discussions é melhor pra esse tipo de coisa — vira uma thread, pessoal comenta, e quando vira decisão, aí vira Issue/PR. Categoria sugerida: Ideias ou Decisões. Quer eu abrir lá em vez de Issue?"

Se o usuário aceitar, usar:

```bash
# GitHub CLI não suporta criar Discussions direto.
# Usa GraphQL via gh api:

REPO_ID=$(gh repo view --json id --jq .id)
CATEGORY_ID=$(gh api graphql -f query='{ repository(owner: "pmrdef", name: "hospital") { discussionCategories(first: 10) { nodes { id name } } } }' | jq -r '.data.repository.discussionCategories.nodes[] | select(.name=="Ideias") | .id')

gh api graphql -f query='
mutation CreateDiscussion($repoId: ID!, $categoryId: ID!, $title: String!, $body: String!) {
  createDiscussion(input: {repositoryId: $repoId, categoryId: $categoryId, title: $title, body: $body}) {
    discussion { url number }
  }
}' -f repoId="$REPO_ID" -f categoryId="$CATEGORY_ID" -f title="$TITULO" -f body="$BODY"
```

Mais detalhes em `references/discussions.md`.

---

## Quando NÃO criar Issue

Coisas que **não** devem virar Issue:

| Situação | Onde vai |
|---|---|
| Pergunta técnica rápida ("como rodo o backend local?") | Discussions categoria "Dúvidas" |
| Discussão de arquitetura sem ação clara ("vamos migrar pra X?") | Discussions categoria "Ideias" ou "Decisões" |
| Decisão já tomada que precisa registro | Discussions categoria "Decisões" |
| Anúncio (deploy notable, breaking change) | Discussions categoria "Anúncios" |
| Bug que já tem PR aberto resolvendo | Comentar no PR, não criar Issue duplicada |
| Reclamação geral / pedido pra refatorar tudo | Conversar antes; pode virar Discussions "Ideias" |
| Tarefa pessoal não-codigo ("comprar domínio") | Fora do GitHub. Vai pro Obsidian/Notion do usuário |

A skill `/issue` deve perguntar antes se não tiver certeza.
