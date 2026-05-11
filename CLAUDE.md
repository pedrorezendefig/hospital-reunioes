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

`YYYY-MM-DD-HHMM` é o timestamp da criação. `<slug>` é uma descrição curta em kebab-case (lowercase, ascii, sem acentos). Ao editar um plano existente, **não renomear** — o timestamp original fica preservado e refletir histórico real de criação. Use o emoji 🟡 como prefix literal (não é codificado de outra forma).

> Para ver os mais recentes no topo do explorer, deixar o VS Code com `"explorer.sortOrder": "modified"` (sort por data de modificação, recente primeiro).

Cada arquivo tem **duas seções obrigatórias**:

- `## Plano` — escopo, passos, critérios de sucesso, riscos.
- `## Execução / Resultados` — registro do que foi feito, resultados, desvios, itens pendentes. Atualizar essa seção conforme o plano vai sendo executado.

Quando o plano é cumprido via `/deploy ship` e o slug bate por similaridade com o commit, o arquivo automaticamente vira 🟢 (ou 🔴 se falhou) e ganha uma seção `## Implementação / Deploy` no final com sha, data, serviços, notas.

Não usar `.claude/plans/`. Não criar `.md` de plano na raiz do projeto nem em `planos/` (essa pasta não existe mais).
