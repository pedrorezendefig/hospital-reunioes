# Plano — Cópia rápida do banco de produção para VPS novo

## Plano

### Contexto

Diretoras (4) vão começar a editar dados na produção atual (`mala-ia.cloud` em VPS Hostinger 16GB com Coolify + Supabase self-hosted). Em paralelo, Pedro vai contratar um VPS mais robusto e oficial, instalar Coolify e subir a mesma aplicação. Quando isso acontecer, o estado da produção atual (banco + arquivos do Storage) precisa ser **copiado** pro novo servidor — incluindo o que as diretoras editarem nesse meio-tempo.

A pergunta original foi: **qual a forma mais fácil e rápida de copiar tudo?** Pedro sugeriu "super query + JSON" ou "clone de alguma forma".

### Por que NÃO "super query + JSON"

Funciona pra dump simples de uma planilha — mas quebra com Supabase porque:

- **`auth.users`** guarda hashes de senha + metadata de sessão. JSON desserializa errado e diretoras perdem login.
- **Sequences** (próximo `id` autoincremento das pendências, reuniões, etc.) se perdem — risco de colisão de PK no novo banco.
- **Foreign keys** exigem ordem específica de INSERT (reuniões → participantes → pendências → comentários). Recriar essa ordem manualmente é trabalho que `pg_dump` já resolve.
- **`storage.objects`** é só o metadata — os bytes (áudio, PDF) ficam num volume Docker separado. JSON não pega isso.
- Tipos JSONb, timestamps com timezone, UUIDs e RLS policies precisam de codificação específica que `psql` já entende e `JSON.parse` não.

Resumindo: você reinventaria `pg_dump`, mal feito.

### Recomendação: `pg_dump`/`pg_restore` + cópia do volume Storage

Forma canônica do Postgres há 25 anos. Pra esse banco (5 facilitadores, dezenas de reuniões), o dump fica em poucos centenas de KB e leva **segundos** pra rodar.

**Parte 1 — Banco** (`pg_dump` no container Postgres do Supabase):

```bash
docker exec -i supabase-db-<UUID> \
  pg_dump -U postgres -Fc --no-owner --no-acl postgres \
  > hospital-prod-$(date +%F).dump
```

**Parte 2 — Storage** (volume com `supabase-storage` + `supabase-minio` compartilhado):

```bash
tar czf - -C /data/coolify/services/<UUID>/volumes storage \
  > hospital-storage-$(date +%F).tar.gz
```

### Pegadinhas do Supabase self-hosted

1. **JWT secret precisa ser o mesmo.** O `GOTRUE_JWT_SECRET` assina os tokens de sessão das diretoras. Se o Supabase novo gerar outro JWT, todos os logins caem. Solução: copiar o mesmo `JWT_SECRET` (e `ANON_KEY`/`SERVICE_ROLE_KEY` derivadas) do Coolify antigo pro novo, antes do primeiro deploy do Supabase.

2. **Storage tem volume físico separado** (4 buckets: `audios`, `transcricoes`, `pdfs`, `pdfs-assinados`). `pg_dump` só pega `storage.objects` (metadata). Os bytes ficam no volume bind-montado pelo Coolify em `/data/coolify/services/<UUID>/volumes/storage` (que `supabase-storage` enxerga em `/var/lib/storage` e `supabase-minio` em `/data`). Sem copiar esse volume, ATAs antigas mostram "PDF assinado" mas o download retorna 404.

3. **Versão do Postgres precisa bater.** Trave a mesma major do Postgres remoto no `docker-compose.yml` do Supabase novo. `pg_restore` falha se o destino for de major menor.

### Como deixar isso "fácil e rápido": script `scripts/clone-prod-db.sh`

Empacota a receita acima num script único. Lê IP/UUIDs do `blueprint/deploy/project.json`. Flags:

- `--snapshot-only` (default) — só baixa o dump+tar pra `~/snapshots/`, sem restaurar.
- `--restore-only` — assume que `~/snapshots/` já tem snapshot e só sobe pro VPS de destino.
- `--full` — snapshot + restore end-to-end.
- `--no-storage` — pula o volume do Storage.
- `--source-vps`, `--target-vps`, `--source-uuid`, `--target-uuid` — overrides explícitos (defaults vêm do `project.json`).
- `--source-user`, `--target-user`, `--snapshots-dir` — extras opcionais.

### Sequência sugerida

| Quando | O que fazer |
|---|---|
| **Agora (escopo deste plano)** | Criar `scripts/clone-prod-db.sh`, rodar 1× em modo `--snapshot-only` pra gerar o primeiro backup, e validar restaurando num Postgres descartável local. |
| **Enquanto diretoras editam** | Pedro roda `bash scripts/clone-prod-db.sh --snapshot-only` **manualmente** quando quiser (antes de mudanças grandes, semanalmente, ou na noite anterior ao cutover). Sem cron — controle total. |
| **Quando VPS novo pronto** | 1) Setup Coolify novo, **mesmo `JWT_SECRET`**, mesma versão Postgres. 2) Sobe Supabase, backend, frontend (sem dados). 3) Roda `clone-prod-db.sh --full --target-vps NOVO_IP --target-uuid NOVO_UUID`. 4) Smoke test. 5) Cutover de DNS. |

### Critérios de sucesso

1. Diretoras logam no novo servidor **sem precisar redefinir senha** (JWT preservado).
2. ATAs antigas aparecem com **mesmo conteúdo, anexos, participantes e pendências**.
3. PDFs assinados das ATAs **baixam normalmente** no novo (Storage migrado).
4. Sequences (`reuniao_id`, `pendencia_id`, etc.) continuam dali pra frente sem colisão.
5. ClickSign continua reconhecendo as atas em curso.
6. Smoke test: fazer login com diretora-teste, abrir 1 ATA antiga, gerar 1 pendência nova, baixar PDF assinado.

### Riscos & mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Storage não copiado → PDFs sumirem | Alta se esquecer | `--storage` ligado por default no script |
| JWT diferente → diretoras kickadas | Média | Copiar `GOTRUE_JWT_SECRET` antes do 1º deploy do Supabase novo |
| Postgres major mismatch | Baixa | Travar imagem `supabase/postgres:15.x` no compose do novo |
| Edição concorrente durante cutover | Baixa | Janela de manutenção de 15min, mensagem no grupo |
| Webhook ClickSign apontando pro IP antigo | Média | Atualizar `CLICKSIGN_WEBHOOK_URL` no painel da ClickSign |
| Cron de Fireflies puxar transcrição duplicada durante cutover | Baixa | Pausar webhook do Fireflies durante a janela |

### Arquivos a criar/modificar

- **`scripts/clone-prod-db.sh`** — novo, automatiza dump+restore+storage. Lê IPs/UUIDs do `blueprint/deploy/project.json`.
- **`blueprint/deploy/project.json`** — quando o VPS novo for contratado, anotar IP/UUID e referência ao script.
- **(opcional)** `~/snapshots/` no laptop do Pedro — fora do repo; só guardar local.

## Execução / Resultados

### 2026-04-28 12:30 — Pipeline implementado e primeiro snapshot validado

**Entregue:**

| Item | Local |
|---|---|
| Chave SSH dedicada (ED25519) | `~/.ssh/hospital_clone_db` |
| Alias SSH | `hospital-vps` em `~/.ssh/config` (User=root, IdentityFile=hospital_clone_db) |
| Public key autorizada no VPS | colada via Coolify Web Terminal em `~/.ssh/authorized_keys` (root) |
| Script de clonagem | `scripts/clone-prod-db.sh` (3 modos, --snapshot-only/restore-only/full, filtro por UUID) |
| Primeiro snapshot do banco | `~/snapshots/hospital-prod-2026-04-28-1227.dump` (388K) |
| Primeiro snapshot do Storage | `~/snapshots/hospital-storage-2026-04-28-1227.tar.gz` (328K) |

**Validação (Postgres 15-alpine descartável local vs produção):**

| Tabela | Local restaurado | Produção | Match |
|---|---:|---:|:---:|
| `auth.users` | 45 | 45 | ✅ |
| `public.reunioes` | 30 | 30 | ✅ |
| `public.pendencias` | 153 | 153 | ✅ |
| `public.participantes` | 60 | 60 | ✅ |
| `public.cargos` | 51 | 51 | ✅ |
| `public.setores` | 32 | 32 | ✅ |
| `public.tipos_reuniao` | 5 | 5 | ✅ |
| `public.audit_log` | 31 | 31 | ✅ |
| `storage.buckets` | 4 | 4 | ✅ |
| `storage.objects` | 4 | 4 | ✅ |

`pg_restore` reportou 14 erros ignorados — todos esperados (roles `authenticated`/`service_role` do Supabase não existem em Postgres vanilla). Dados foram inseridos integralmente porque os erros foram em CREATE POLICY (RLS), não em INSERT.

**Storage:** tar tem 115 entradas, mas só infraestrutura interna do MinIO (`.minio.sys/`). Nenhum bucket nomeado (`audios`, `transcricoes`, `pdfs`, `pdfs-assinados`) tem arquivos físicos ainda — confere com o blueprint que diz "Banco de desenvolvimento ainda mocado". Os bytes vão começar a aparecer quando as diretoras gerarem ATAs reais.

**Descobertas durante execução (refinaram o script):**

- **Versão do Postgres:** `supabase/postgres:15.8.1.085`. Anotar no setup do VPS novo.
- **Storage compartilha bind mount:** `supabase-storage` (`/var/lib/storage`) e `supabase-minio` (`/data`) apontam pro mesmo `/data/coolify/services/<UUID>/volumes/storage` no host. Mais limpo fazer `tar` do host direto que `--volumes-from` (script ajustado).
- **3 outros Postgres no VPS:** `coolify-db`, `postgres-31ey85oi92l8phsya80gf5wh` (Chatwoot), `postgresql-database-r6d64tckijn6s6fahg309qv5` (n8n standalone). Por isso o script filtra container pelo UUID do service Supabase, não por padrão genérico.
- **Postgres standalone exposto publicamente** (`r6d64tckijn6s6fahg309qv5`, `31.97.29.32:5432`) é do n8n, não do Hospital. Banco do Hospital fica interno ao service Supabase.

**Como usar daqui pra frente:**

```bash
# Snapshot manual antes de mudanças grandes ou semanalmente:
bash scripts/clone-prod-db.sh --snapshot-only

# Quando o VPS novo estiver pronto (Coolify + service Supabase deployado):
bash scripts/clone-prod-db.sh --full \
  --target-vps NOVO_IP \
  --target-uuid UUID_DO_SERVICE_SUPABASE_NOVO
```

**Próximos passos (cutover futuro, fora do escopo deste plano):**

- [ ] Contratar VPS novo (Hostinger ou outro provedor mais robusto).
- [ ] Instalar Coolify no VPS novo.
- [ ] Criar service Supabase no Coolify novo, com **mesmo `JWT_SECRET`/`ANON_KEY`/`SERVICE_ROLE_KEY`** do antigo.
- [ ] Travar imagem `supabase/postgres:15.8.x` no compose.
- [ ] Subir backend FastAPI + frontend Next.js apontando pro Supabase novo.
- [ ] Atualizar `blueprint/deploy/project.json` com IP/UUID do destino.
- [ ] Combinar janela de manutenção de 15min com as diretoras.
- [ ] Pausar webhook Fireflies durante a janela.
- [ ] Rodar `bash scripts/clone-prod-db.sh --full ...`.
- [ ] Atualizar `CLICKSIGN_WEBHOOK_URL` no painel ClickSign pro novo domínio.
- [ ] Cutover de DNS (`mala-ia.cloud` → novo IP).
- [ ] Smoke test com diretora-teste.
- [ ] Criar plano dedicado pra o cutover (`planos/plano-AA-MM-DD-HHMMh-cutover-vps-novo.md`).
