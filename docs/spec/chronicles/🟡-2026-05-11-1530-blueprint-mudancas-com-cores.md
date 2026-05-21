# Plano: Unificar blueprint/mudancas/ com cores 🟡 / 🟢 / 🔴

## Plano

### Contexto

A organização anterior tinha duas pastas separadas: `planos/` na raiz (manual, 30 arquivos) e `blueprint/implementacoes/` (auto-gerado pelo /deploy, 9 arquivos). Cada mudança no projeto vivia em dois lugares com nomes diferentes, e a relação plano → deploy era implícita. Pedro pediu pra unificar em uma pasta única dentro do blueprint, com indicador visual de estado por cor.

### Decisões

1. **Nome da pasta**: `blueprint/mudancas/`. Renomeio de `blueprint/implementacoes/`, agrega também o que era `planos/`. Pasta `planos/` na raiz some.
2. **3 estados visuais**: 🟡 plano sem deploy / 🟢 plano + deploy healthy / 🔴 plano + deploy failed ou rolled-back. Prefix no nome do arquivo.
3. **Naming**:
   - `🟡-YYYY-MM-DD-HHMM-<slug>.md` (plano puro)
   - `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` (plano + deploy OK)
   - `🔴-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` (plano + deploy falhou)
4. **Conteúdo**: o MD começa com o plano (## Plano / ## Execução). Quando vira 🟢/🔴, o `/deploy ship` anexa uma seção `## Implementação / Deploy` no final com sha, data, serviços, notas (todo conteúdo que hoje fica em `blueprint/implementacoes/<file>.md`).
5. **Migração retroativa**: Pra cada plano antigo, tentar match com deploy em `history.json` (slug similar + data ±7d). Match sólido → vira 🟢 com sha do deploy + conteúdo do MD original anexado. Sem match → vira 🟡.

### Arquivos modificados / criados

**Globais (no `~/.claude/`, fora do repo):**
- `~/.claude/skills/deploy/SKILL.md` — Passo 9.4 passa a gerar em `blueprint/mudancas/` com prefix 🟢/🔴, e procura plano 🟡 com slug similar antes de criar novo.
- `~/.claude/skills/blueprint/SKILL.md` — algoritmo `update` lê `blueprint/mudancas/` (não mais `implementacoes/`), filtra 🟡 vs 🟢 pra "histórico recente" e "planos abertos".
- `~/.claude/CLAUDE.md` — bloco "Blueprint do projeto" documenta nova estrutura.

**No repo Hospital:**
- `CLAUDE.md` — seção "Deploy e blueprint" idem.
- `blueprint/mudancas/` (nova pasta, 38 arquivos).
- `blueprint/sql/` (movido de `planos/sql/`).
- `blueprint/implementacoes/` removida (vazia).
- `planos/` removida (vazia).

### Migração executada

Pra cada um dos 30 planos antigos, tentei match retroativo via tokens em comum (threshold ≥60% overlap, com stopwords removidas: fix, data, chore, feat etc).

Resultado: 3 matches sólidos (viraram 🟢 com sha do deploy), 27 sem match (ficaram 🟡 puros).

- `🟢-2026-04-25-0128-9b2a55f-fix-reset-senha-resend.md` — plano `fix-reset-senha-resend` ↔ deploy `9b2a55f` (Reset de senha com fluxo seguro). Tokens-comum: reset, senha.
- `🟢-2026-04-27-1952-85f7f88-skill-blueprint-md.md` — plano `skill-blueprint-md` ↔ deploy `85f7f88` (Migra blueprint para PROJETO.md skill /blueprint global). Tokens-comum: skill, blueprint (overlap 100%).
- `🟢-2026-04-27-1828-890b149-revisao-ortografica-banco.md` — plano `revisao-ortografica-banco` ↔ deploy `890b149` (revisão ortográfica em massa). Tokens-comum: revisao, ortografica, banco.

Os 8 MDs que já existiam em `blueprint/implementacoes/` foram movidos pra `blueprint/mudancas/` como 🟢 (resultado="healthy" cai pro prefix). 1 deles foi absorvido pelo plano `skill-blueprint-md` (sha 85f7f88) — conteúdo anexado no final do MD do plano.

### Verificação

1. `blueprint/mudancas/` tem 38 arquivos: 27 🟡 + 11 🟢. Conferir contagem.
2. Pasta `planos/` removida (não existe mais na raiz).
3. Pasta `blueprint/implementacoes/` removida.
4. Próximo `/deploy ship`: deve criar novo MD em `blueprint/mudancas/` com prefix 🟢, e tentar match com plano 🟡 existente cujo slug bata por similaridade.

---

## Execução / Resultados

### O que foi feito (2026-05-11)

1. **Pasta `blueprint/mudancas/` criada** com 38 arquivos. Pasta `planos/` removida. Pasta `blueprint/implementacoes/` removida. Arquivos SQL legados movidos de `planos/sql/` pra `blueprint/sql/`.

2. **Renames preservando histórico git**:
   - 26 planos migrados via `git mv` (estavam tracked).
   - 4 planos via `mv` simples (estavam untracked).
   - 9 implementações migradas via `git mv` (8 viraram 🟢 standalone, 1 foi absorvida pelo plano 🟢 correspondente).

3. **Skill `/deploy` Passo 9.4** atualizada:
   - Pasta destino: `blueprint/mudancas/` (não mais `blueprint/implementacoes/`).
   - Filename: `🟢-YYYY-MM-DD-HHMM-<sha7>-<slug>.md` (healthy) ou `🔴-...` (failed).
   - Antes de criar novo, procura plano 🟡 com slug similar (tokens em comum). Se acha, anexa seção `## Implementação / Deploy` no MD do plano e renomeia pro novo prefix.

4. **Skill `/blueprint` algoritmo `update`** atualizada:
   - Lê `blueprint/mudancas/` em vez de `blueprint/implementacoes/`.
   - Seção "Planos abertos" do PROJETO.md filtra arquivos 🟡 da nova pasta.
   - Histórico recente filtra 🟢 e 🔴 desc.

5. **CLAUDE.mds** atualizados (global e do projeto) com a nova estrutura.

### Pendentes

- Push pro main. CI deve continuar verde (sem mudança de código de produção).
