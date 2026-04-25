# Segredos auto-gerados

Gerados pela skill `/deploy` via comando local, setados no Coolify via MCP, **nunca** persistidos em arquivo, log ou JSON.

| Var | Serviço | Gerador local |
|---|---|---|
| `SIGNUP_ENCRYPTION_KEY` | backend | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `CLICKSIGN_WEBHOOK_SECRET` | backend | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SIGNUP_PASSE` | backend | `python -c "import secrets; print(secrets.token_urlsafe(24))"` |

**Fallback** se `cryptography` não estiver disponível localmente: `docker exec hr-backend python -c "..."`.

## Como o dashboard mostra segredos

Em `blueprint/deploy/state.json` e `blueprint/dashboard.html`, segredos aparecem **apenas** como:

```json
{ "name": "SIGNUP_ENCRYPTION_KEY", "service": "backend", "present": true }
```

Sem `value`. O dashboard renderiza chip cinza com label "segredo · presente" ou vermelho "segredo · faltando".

A skill `/deploy` aborta o write do `state.json` se detectar regex de valor real (`(?:[a-zA-Z0-9+/]{40,}|sk-[a-zA-Z0-9]{20,})`) em qualquer campo.
