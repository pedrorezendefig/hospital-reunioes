# Changelog Hospital Reuniões

Cronologia de deploys e mudanças importantes em ordem reversa (mais recente no topo).
Prepended pelo `/deploy ship` ao final do ciclo (ou manualmente quando o PR é meta — só skills/docs).

A partir de **v0.2.0** as entradas seguem o formato `## v0.X.Y — DATA — tipo(escopo): descrição`, com bump automático decidido pelo `/ship` (BREAKING > feat > fix/chore). Entradas mais antigas usam o formato `## YYYY-MM-DD HH:MM - tipo(escopo): descrição` — preservadas como histórico, sem retrofit de versão. Esquema completo descrito em [VERSIONING.md](VERSIONING.md).

---

## 2026-05-21 20:39 - feat(skills): automatizar /snapshot via script Python

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `70bac46`
- PR: [#7](https://github.com/pedrorezendefig/hospital-reunioes/pull/7) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — só toca skills + docs)
- Detalhe: [chronicles/🟢-2026-05-21-2039-70bac46-snapshot-parser-automation.md](chronicles/🟢-2026-05-21-2039-70bac46-snapshot-parser-automation.md)

**Resumo:** implementa o gerador real do `/snapshot` que estava só documentado no PR #6. Script Python self-contained (993 linhas, stdlib only) em `.claude/skills/snapshot/scripts/snapshot.py` com parser AST de routers FastAPI (78 endpoints em 13 routers), parser SQL cumulativo de migrations (13 tabelas das 36 migrations), 5 geradores de MD, idempotência via comparação de buffer e flags CLI (`--check`, `--force`, `--only`, `--diff`, `--no-commit`). Code-review pegou 1 bug score 100 (JSONB DEFAULT corrompendo parser de colunas) + 3 issues score 75, todas corrigidas antes do merge.

---

## 2026-05-21 18:58 - feat(workflow): integrar Superpowers + /snapshot vivo + 5 camadas de gate

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e9f64ee`
- PR: [#6](https://github.com/pedrorezendefig/hospital-reunioes/pull/6) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — PR só toca skills + docs)
- Detalhe: [chronicles/🟢-2026-05-21-1858-e9f64ee-superpowers-integration-v1.md](chronicles/🟢-2026-05-21-1858-e9f64ee-superpowers-integration-v1.md)

**Resumo:** integra plugin Superpowers v5.1.0 no workflow do time. Cria skill `/snapshot` (gera 7 MDs vivos em `docs/spec/snapshots/` regenerados a cada deploy via `/deploy ship`). `/start` ganha Modo D (retomar trabalho parado de outra sessão) + invocação de `brainstorming` por default no Modo A. `/ship` ganha 5 camadas independentes de gate antes do self-approval (code-review, security-review, requesting-code-review, CI Actions, verification-before-completion). `CLAUDE.md` reescrito com 5 seções novas. CI Actions ganha job `build` (docker sanity). Cleanup de 150+ skills `reversa-*` absorvido no mesmo PR (-26338 linhas).
