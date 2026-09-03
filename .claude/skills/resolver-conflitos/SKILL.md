---
name: resolver-conflitos
description: Resolve merge ou rebase em andamento preservando a intenção de cada lado, com triagem por tipo de arquivo (lockfile, bump, migration). Use em conflito ou PR CONFLICTING sem checks.
---

# Resolver conflitos

Resolver é entender a intenção antes de tocar no hunk. Nunca invente comportamento novo na resolução.

1. **Veja o estado atual** do merge/rebase: `git status`, histórico e arquivos em conflito.

2. **Ache as fontes primárias** de cada conflito. Entenda por que cada mudança foi feita e qual era a intenção original: commit messages, PRs e issues de origem (`gh pr view`, `gh issue view`).

3. **Triagem por tipo de arquivo**, antes de resolver hunk a hunk:
   - `pnpm-lock.yaml` / `uv.lock`: **nunca** resolva hunk a hunk. `git checkout --ours <lockfile>` + regenerar (`uv lock`; `echo y | corepack pnpm@9 install --no-frozen-lockfile`). Atenção: `CI=true` força frozen-lockfile e quebra a regeneração.
   - Bump de versão (`package.json`) e numeração de migration: confira `origin/main` (package.json + `ls` de migrations) antes do push final; outra issue pode ter mergeado antes, e rebase pode engolir o commit de bump silenciosamente. Re-bumpar e renumerar se colidiu.
   - PR `CONFLICTING` sem checks: commit vazio e close/reopen não resolvem; o caminho é rebase + `git push --force-with-lease`.

4. **Resolva cada hunk restante.** Preserve as duas intenções quando possível. Se incompatíveis, escolha a que casa com o objetivo declarado do merge e anote o trade-off. Não invente comportamento novo. Sempre resolva; nunca `--abort`.
   - O "nunca `--abort`" vale para a sessão orquestradora. Sub-agentes seguem as regras de git safety do próprio prompt: proibido `git checkout --`, `git reset --hard`, `git stash drop` e afins em arquivos fora da própria issue.

5. **Descubra e rode os checks do projeto**: typecheck, testes, format/lint (backend `ruff check` + `ruff format --check`; frontend `tsc`/lint). Conserte o que o merge quebrou.

6. **Termine o merge/rebase.** Stage tudo e commite. Se for rebase, continue até todos os commits serem rebaseados.
