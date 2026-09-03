## Passo 12 — Notificação (Discord opcional)

**Default do time Hospital: sem Discord.** Notificações são nativas via GitHub Mobile (push notifications de PR aberto/mergeado, CI passou/falhou, review request, comentários). Cada membro instala o app e marca o repo como Watching.

A skill **procura** webhook URL nessa ordem e **só posta se achar**:
1. `docs/spec/deploy/project.json` → `project.integrations[].discord_webhook` (se houver).
2. `$REPO_ROOT/.env` → `DISCORD_WEBHOOK_URL` (não versionado).
3. `~/.config/hospital/discord-webhook.url`.

Se **nenhuma das 3 fontes** retornar URL válida:
- Log: `[ship] Discord webhook não configurado, pulando notificação (default do time é GitHub Mobile + Discussions).`
- Continue sem erro. **Não bloqueia o ship.**

Se uma das fontes retornar URL válida, postar:

```bash
curl -X POST "$DISCORD_WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "$(cat <<EOF
{
  "username": "ship-bot",
  "embeds": [{
    "title": "$RESULT_EMOJI $SUBJECT",
    "description": "Mergeado e em produção.",
    "color": $COLOR_DEC,
    "fields": [
      {"name": "Autor", "value": "$(git config user.name)", "inline": true},
      {"name": "SHA", "value": "\`$SHA\`", "inline": true},
      {"name": "Duração", "value": "${DURATION_DEPLOY_s}s deploy", "inline": true},
      {"name": "PR", "value": "[#$PR_NUMBER]($PR_URL)", "inline": true},
      {"name": "Commit", "value": "[ver](https://github.com/$REPO/commit/$SHA)", "inline": true}
    ],
    "timestamp": "$(date -Iseconds)"
  }]
}
EOF
)"
```

**Decisão importante grande?** Pra "deploy notable" (ex: mudança de arquitetura, breaking change, primeiro release de uma feature), criar uma thread em **GitHub Discussions** categoria "Decisões" via:

```bash
# Discussions API só permite criar discussion via GraphQL, não REST.
# Variação simples: comentar na Issue + linkar do CHANGELOG.
# Ou: criar Issue tipo "release-notes" com label release.
```

Não automatizado por enquanto — fica como ação manual de quem rodou o ship, se o ship for "notable".

---
