# Coolify — UUIDs, domínios, repositório

> Doc humana, raramente editada. Os UUIDs vivem aqui em formato legível; em forma estruturada (consumida pela skill `/deploy`) eles também estão em `state.json`.

## Infraestrutura

<!-- blueprint:section:config-coolify -->

**VPS:** Hostinger 16GB — `31.97.29.32`
**Coolify:** https://coolify.mala-ia.cloud
**Projeto Coolify UUID:** `gvkd16jzoq8dzlpep2txqgo3` (Hospital São Matheus)
**Server UUID:** `uy6j3f0nmevsvwkknmmpfgqc` (localhost / `host.docker.internal`)
**GitHub App UUID:** `r10gjb55dd6zamdx0vquuau4` (hospital-reunioes, privado)
**Supabase Service UUID:** `o10ajq7525ch5vsa0a3yzoxt` (hospital-supabase, env=production)

| App | UUID | Porta | Domínio | Health check |
|---|---|---|---|---|
| backend | `jo6zt7h4chu7w38s4ojyuepu` | 8000 | api.mala-ia.cloud | `/api/health` |
| frontend | `okt237kwgu5x48qqbd57ntvz` | 3000 | app.mala-ia.cloud | (sem path custom) |
| supabase-kong | (parte do service) | 8000 → 443 | studio.mala-ia.cloud | (sem path custom) |

**Repo:** `pedrorezendefig/hospital-reunioes` (privado, GitHub App `hospital-reunioes`)
**Branch de deploy:** `main`
**Tempo médio de build:** backend ~1min30s, frontend ~2min30s
