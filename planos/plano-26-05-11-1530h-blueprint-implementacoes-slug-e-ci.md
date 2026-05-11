# Plano: Slug nos arquivos de implementação + conserto do CI

## Plano

### Contexto

O painel do projeto é o `blueprint/PROJETO.md`, mas os arquivos em `blueprint/implementacoes/<timestamp>-<sha>-<resultado>.md` listavam só SHA + status no nome, sem indicar o assunto do deploy, o que dificultava enxergar o que cada deploy mudou direto no explorer do VS Code. Junto disso, o workflow CI do GitHub Actions (`.github/workflows/ci.yml`) falhava em todo push (100% de falha desde 20/04/2026) e gerava email "All jobs have failed" a cada deploy.

> **Nota:** Esse plano inicialmente incluía também a geração de um `blueprint/PROJETO.html` visual com fonte HP Simplified e paleta navy. Depois de ver o resultado, decidimos não seguir com o HTML. Toda a infra de geração de HTML, assets/, e referências em CLAUDE.md foi revertida. O painel continua sendo apenas o `PROJETO.md`.

### Escopo final

1. **Slug do commit no nome do MD da implementação**: `YYYY-MM-DD-HHMM-<sha7>-<resultado>-<slug>.md`. Slug derivado do `raw_subject` (lowercase, sem acentos, máx 50 chars no último hífen, sem `<type>` do Conventional Commit). Backfill dos 8 MDs existentes via `git mv`.
2. **Conserto do CI**: Node 22 no frontend (pnpm 11 exige ≥ 22.13) + env vars dummy no backend (Pydantic Settings exige `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY`).

### Arquivos modificados / criados

**Globais (fora do repo Hospital, no `~/.claude/`):**
- `~/.claude/skills/deploy/SKILL.md` — Passo 9.4 passa a gerar slug e h1 com subject.
- `~/.claude/CLAUDE.md` — bloco "Blueprint do projeto" cita o novo pattern de naming com slug em `implementacoes/`.

**No repo Hospital:**
- `.github/workflows/ci.yml` — Node 22 + env vars dummy.
- `CLAUDE.md` — seção "Deploy e blueprint" cita o novo pattern de naming.
- `blueprint/implementacoes/*.md` × 8 — renomeados via `git mv` (preserva histórico).
- `planos/plano-26-05-11-1530h-blueprint-implementacoes-slug-e-ci.md` — este plano.

### Verificação

1. CI verde após o push (esperar runs do GitHub Actions). Pendente push.
2. Próximo `/deploy ship` deve gerar MD novo com slug e h1 com subject — comportamento embutido na skill `/deploy` Passo 9.4.

---

## Execução / Resultados

### O que foi feito (2026-05-11)

1. **CI consertado** (`.github/workflows/ci.yml`):
   - Frontend: `node-version: "20"` → `"22"`.
   - Backend: bloco `env:` adicionado com `SUPABASE_URL=http://localhost:54321` e `SUPABASE_SERVICE_ROLE_KEY=dummy-key-for-ci`. Auditoria do `app/config.py` confirmou que **só esses 2 campos** são obrigatórios sem default no Pydantic Settings; os outros (`openrouter_api_key`, `resend_api_key`, etc) têm default `""`.

2. **Skill `/deploy` Passo 9.4** (`~/.claude/skills/deploy/SKILL.md`):
   - Adicionada função `make_slug()` que parseia Conventional Commit, normaliza (NFKD + ascii + lowercase) e trunca em 50 chars no último hífen.
   - Filename agora vira `YYYY-MM-DD-HHMM-<sha7>-<resultado>-<slug>.md`.
   - H1 do MD passa a incluir o `subject` em bold logo abaixo do título.
   - Gate de idempotência migra automaticamente arquivo legado (sem slug) → nome novo via `Path.rename()`.

3. **Backfill (renames `git mv`)**:
   - 8 MDs renomeados em `blueprint/implementacoes/`. Exemplos:
     - `2026-05-11-1226-09d948b-healthy.md` → `…-healthy-ata-chat-correcao-colapsavel-refresh-automatico-e.md`
     - `2026-05-08-1635-44c53c8-healthy.md` → `…-healthy-reunioes-super-admin-troca-facilitador-da-reuniao.md`
     - `2026-04-27-1952-85f7f88-healthy.md` → `…-healthy-blueprint-migra-para-projeto-md-skill-blueprint.md`

4. **CLAUDE.mds** atualizados:
   - `~/.claude/CLAUDE.md`: bloco "Blueprint do projeto" cita o novo pattern de naming com slug.
   - `CLAUDE.md` do projeto: idem na seção "Deploy e blueprint".

### Reversões (PROJETO.html descartado)

- `blueprint/PROJETO.html` chegou a ser gerado e aberto no navegador. Pedro avaliou e não gostou do design.
- Arquivos físicos removidos: `blueprint/PROJETO.html`, `blueprint/assets/HPSimplified_Rg.ttf`, `blueprint/assets/logo-hsm.png`, pasta `blueprint/assets/`.
- Skill `/blueprint` revertida ao algoritmo original (gera apenas `PROJETO.md`).
- CLAUDE.mds revertidos pra não mencionar PROJETO.html nem `assets/`.
- `blueprint/PROJETO.md` restaurado ao estado committed (`git checkout HEAD --`).

### Pendentes

- Push para `main` (CI tem que ficar verde no próximo run; emails param de chegar).
