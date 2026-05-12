# Regras do Projeto — Hospital Reuniões

## Deploy e blueprint

- **Toda operação de deploy passa por `/deploy`** (skill universal). Modos: `/deploy` (ship), `/deploy setup`, `/deploy status`, `/deploy rollback`.
- **Painel humano:** `blueprint/PROJETO.md` — visão consolidada para leigo (estado de prod, variáveis OK, integrações, alertas, planos abertos, histórico recente). Regerado pela skill `/blueprint update` (executada automaticamente ao final de cada `/deploy ship`).
- **Fonte da verdade da infra:** `blueprint/deploy/project.json` (manual; ampliado com `description`, `stack`, `integrations`, `next_actions`). `state.json` e `history.json` são auto-gerados pela `/deploy`.
- **Cronologia unificada de mudanças:** `blueprint/mudancas/` — 1 MD por mudança, com prefix de cor indicando estado:
  - **🟡** `🟡-YYYY-MM-DD-HHMM-<slug>.md` — plano sem deploy (criado manualmente).
  - **🟢** `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy healthy.
  - **🔴** `🔴-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` — plano + deploy failed / rolled-back.
  - Quando `/deploy ship` roda, ele procura um plano 🟡 com slug similar ao commit. Se acha, anexa seção `## Implementação / Deploy` no final do MD do plano e renomeia 🟡 → 🟢/🔴. Se não acha, cria novo 🟢/🔴 sem corpo de plano.
- **Histórico mensal:** `blueprint/historico/YYYY-MM.md` — gerado por `/blueprint historico` (changelog humano de commits, manual).
- **Não criar** `PRODUCAO.md`, `deploy-history.md`, `dashboard.html` — substituídos pelo `PROJETO.md`. Não criar pasta `planos/` na raiz nem `implementacoes/` solta — tudo passa por `blueprint/mudancas/`.

## Planos

Quando o usuário pedir planejamento, criar o plano em **`blueprint/mudancas/`**, com nome no formato:

```
🟡-YYYY-MM-DD-HHMM-<slug>.md
```

**Timestamp = última atualização do arquivo, não criação.** Ao editar um plano 🟡 existente, **renomear** com o novo timestamp:

```
mv "🟡-2026-05-11-1400-foo.md" "🟡-2026-05-12-0930-foo.md"
```

Assim a ordenação por nome no explorer (ASC) ou no PROJETO.md (DESC por mtime) reflete sempre o que foi mexido mais recente. Use o emoji 🟡 como prefix literal (não é codificado de outra forma). `<slug>` é uma descrição curta em kebab-case (lowercase, ascii, sem acentos).

> Para ver os mais recentes no topo do explorer, deixar o VS Code com `"explorer.sortOrder": "modified"` (sort por data de modificação, recente primeiro).

Cada arquivo tem **duas seções obrigatórias**:

- `## Plano` — escopo, passos, critérios de sucesso, riscos.
- `## Execução / Resultados` — registro do que foi feito, resultados, desvios, itens pendentes. Atualizar essa seção conforme o plano vai sendo executado.

Quando o plano é cumprido via `/deploy ship` e o slug bate por similaridade com o commit, o arquivo automaticamente vira 🟢 (ou 🔴 se falhou) e ganha uma seção `## Implementação / Deploy` no final. **O timestamp no nome do arquivo passa a ser a data/hora do deploy** (sobrescreve o do plano), e o nome ganha o `<sha7>` do commit:

```
🟡-2026-05-12-0930-foo.md  →  🟢-2026-05-12-1145-abc1234-foo.md
```

Não usar `.claude/plans/`. Não criar `.md` de plano na raiz do projeto nem em `planos/` (essa pasta não existe mais).
