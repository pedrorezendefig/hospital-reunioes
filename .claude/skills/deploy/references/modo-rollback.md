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
5. `y`:
   - Pra cada service afetado naquele deploy: `coolify app rollback images <uuid>` → confirmar que a imagem do SHA-alvo ainda existe.
   - Pedir ao humano rodar `! coolify app rollback run <uuid> --commit <SHA-alvo>`.
   - Monitorar (Passo 5 do ship).
   - Health check (Passo 7).
6. Reescrever `state.json` (9.1) com `last_run.mode = "rollback"`. Prepend em `history.json` (9.2) com `rollback_target_sha = <sha-alvo>` e `result = "rollback-manual"`. Prepend em CHANGELOG (9.5).

Dry-run: mostrar alvo e deployments, sem executar.

---
