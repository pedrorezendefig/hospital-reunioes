## Modo `rollback`

Invocação: `/deploy rollback [--dry-run]`.

1. Bootstrap.
2. Ler `history.json`. Identificar 2º deploy mais recente com `result == "healthy"` (o mais recente pode estar danificado). Se só houver 1 → reportar e parar.
3. Mostrar candidato:
   ```
   Rollback candidato:
     De: <sha-atual> (<data> — <subject>)
     Para: <sha-alvo> (<data> — <subject>)
   Reverter? [y/n]
   ```
4. `n` → abortar.
5. `y`, pra cada service afetado naquele deploy, conforme o `build.build_pack` dele no `project.json`:
   - **Build do git** (`dockerfile`, `nixpacks`, `static`): `coolify app rollback images <uuid>` → confirmar que a imagem do SHA-alvo ainda existe. Pedir ao humano rodar `! coolify app rollback run <uuid> --commit <SHA-alvo>`.
   - **Modo imagem** (`dockerimage`, issue #1001): o rollback é por tag. A imagem de cada deploy segue no GHCR com a tag do sha do squash (`<build.image>:<SHA-alvo>`), e o `rollback images` do Coolify não serve (é de imagem construída do git). Rodar `coolify app update <uuid> --docker-tag <SHA-alvo>` e pedir ao humano `! coolify deploy uuid <uuid>`: o Coolify só puxa a tag e reinicia, sem build. Se a tag não existir no GHCR, publique antes com `gh workflow run <build.publish_workflow> --ref main -f sha=<SHA-alvo>` (constrói do commit).
   - Monitorar (Passo 5 do ship).
   - Health check (Passo 7).
6. Reescrever `state.json` (9.1) com `last_run.mode = "rollback"`. Prepend em `history.json` (9.2) com `rollback_target_sha = <sha-alvo>` e `result = "rollback-manual"`.

Dry-run: mostrar alvo e deployments, sem executar.

---
