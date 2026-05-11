# Plano — Refatorar /clone-banco para gerar SQLs numerados (clone manual assistido)

## Context

A skill atual (`/clone-banco`) usa `pg_dump -Fc` (formato custom binário) + `pg_restore --clean --if-exists` + tar.gz do volume Storage. Funciona, mas é "tudo ou nada" — você não vê o que está sendo aplicado, e qualquer falha no meio do `pg_restore` é difícil de inspecionar.

O usuário quer um modelo **explícito e granular**: a skill lê a prod, gera **arquivos `.sql` numerados** numa pasta da IDE, e o usuário roda **um por um manualmente** (no SQL Editor do Supabase do destino, ou onde preferir). Resultado final: clone exato do banco da origem.

**Decisões já tomadas pelo usuário:**
- **Schemas**: `public` + `auth` + `storage` (clone completo do banco).
- **Storage físico** (PDFs, áudios, transcrições): NÃO inclui — só metadata via SQL. Frontend pode ter links quebrados temporariamente.
- **Onde salvar**: `<repo>/clone-banco-sql/<timestamp>/` (no repo, gitignored).

## Estrutura final da skill

```
.claude/skills/clone-banco/
  SKILL.md                          ← reescrito do zero, ~3-4x menor
  scripts/
    generate-sql.sh                 ← lê prod via SSH, gera arquivos .sql numerados
    validate-counts.sh              ← roda contagem na origem (pra você comparar com destino)
```

**Remove** (não fazem mais sentido no modelo SQL-only):
- `scripts/clone-prod-db.sh` (raiz do repo)
- `.claude/skills/clone-banco/scripts/preview-snapshot.sh`
- `.claude/skills/clone-banco/scripts/preview-restore.sh`
- `.claude/skills/clone-banco/scripts/validate-snapshot.sh`
- `.claude/skills/clone-banco/scripts/validate-restore.sh`

## Estrutura dos arquivos SQL gerados

Pasta de saída: `<repo>/clone-banco-sql/AAAA-MM-DD-HHMM/`

```
00-INSTRUCOES.md                    ← guia humano: ordem, contexto, troubleshooting
01-pre-schema.sql                   ← extensions, types (enums), sequences, functions, CREATE TABLE
02-post-schema.sql                  ← FKs, indexes, triggers, RLS policies
03-data-auth-users.sql              ← auth.users (com hashes de senha)
04-data-auth-identities.sql         ← auth.identities (login social, se houver)
05-data-storage-buckets.sql         ← storage.buckets (4 buckets)
06-data-storage-objects.sql         ← storage.objects (metadata, sem bytes)
07-data-public-participantes.sql    ← em ordem topológica de FKs
08-data-public-setores.sql
09-data-public-cargos.sql
10-data-public-tipos_reuniao.sql
11-data-public-reunioes.sql
12-data-public-reuniao_participantes.sql
13-data-public-pendencias.sql
14-data-public-comentarios_pendencias.sql
15-data-public-agendamentos_email.sql
16-data-public-tokens_validacao.sql
17-data-public-notificacoes.sql
18-data-public-user_preferences.sql
19-data-public-audit_log.sql
20-data-public-bulk_jobs.sql
21-data-public-historico_importacao.sql
22-sequences-setval.sql             ← SELECT setval('participantes_id_seq', N) etc
99-validation.sql                   ← SELECT count(*) FROM cada tabela, pra comparar com origem
```

A ordem topológica (07 em diante) vem do mapeamento já feito — `participantes` e taxonomias antes de `reunioes`, `reunioes` antes de `reuniao_participantes` e `pendencias`, etc.

## Como `generate-sql.sh` funciona

Reaproveita autenticação SSH e descoberta de container do script atual (lê `blueprint/deploy/project.json`, conecta via `~/.ssh/hospital_clone_db`, encontra `supabase-db-<UUID>`).

**Comandos chave** (todos via `ssh hospital-vps "docker exec ..."`):

```bash
# 01-pre-schema.sql — DDL inicial
pg_dump -Fp --no-owner --no-acl --schema-only --section=pre-data \
  --schema=public --schema=auth --schema=storage postgres > 01-pre-schema.sql

# 02-post-schema.sql — DDL final (FKs, indexes, triggers, RLS)
pg_dump -Fp --no-owner --no-acl --schema-only --section=post-data \
  --schema=public --schema=auth --schema=storage postgres > 02-post-schema.sql

# Dados — uma tabela por arquivo, ordem topológica hardcoded no script
for entry in "${TABLE_ORDER[@]}"; do
  N="${entry%%:*}"; SCHEMA="${entry#*:}"; SCHEMA="${SCHEMA%%:*}"; TABLE="${entry##*:}"
  pg_dump -Fp --no-owner --no-acl --data-only --inserts --column-inserts \
    --table="$SCHEMA.$TABLE" postgres > "${N}-data-${SCHEMA}-${TABLE}.sql"
done

# 22-sequences-setval.sql — gera SETVAL pra cada sequence
psql -c "SELECT format('SELECT setval(''%s.%s'', %s);', schemaname, sequencename, last_value)
         FROM pg_sequences WHERE schemaname IN ('public','auth','storage');" \
  -At > 22-sequences-setval.sql

# 99-validation.sql — query única que retorna contagens
cat > 99-validation.sql <<EOF
SELECT 'auth.users' AS tabela, count(*) AS total FROM auth.users
UNION ALL SELECT 'storage.buckets', count(*) FROM storage.buckets
UNION ALL SELECT 'storage.objects', count(*) FROM storage.objects
UNION ALL SELECT 'public.participantes', count(*) FROM public.participantes
... (todas as tabelas)
ORDER BY tabela;
EOF
```

**Importante**: `pg_dump -Fp` (plain text) com `--inserts --column-inserts` gera SQL puro com `INSERT INTO` linha por linha — fácil de ler, fácil de rodar pedaço por pedaço, fácil de inspecionar diff.

**Flag `--no-owner --no-acl`** (mantida do script atual): evita conflitos com roles do Supabase (`authenticated`, `service_role`, etc) que o destino já cria automaticamente.

## Workflow novo da skill (5 fases)

1. **Preview** — Lê `project.json`, mostra: IP da origem, UUID, versão Postgres, contagem aproximada de linhas das tabelas principais (via SSH), nome da pasta que vai criar.
2. **Confirmação** — "Gerar SQLs em `clone-banco-sql/2026-05-01-1530/`? [s/N]". Não-destrutivo, mas confirma pra você ver onde vai parar.
3. **Geração** — Roda `generate-sql.sh`. Imprime cada arquivo conforme termina (com tamanho e contagem de INSERTs onde aplicável).
4. **Execução assistida** — Lista os arquivos em ordem com mini-checklist:
   ```
   [ ] 01-pre-schema.sql        — Cole no SQL Editor. Confirme com "rodei".
   [ ] 02-post-schema.sql       — ...
   ...
   ```
   Skill mostra cada arquivo, espera você dizer "rodei" / "ok" / "próximo", marca como done, vai pro próximo. Se algo falhar, você diz "erro" e cola a mensagem — ela ajuda a interpretar.
5. **Validação** — Você roda `99-validation.sql` no destino, cola o output. Skill compara com o output que ela rodou na origem (rodando `validate-counts.sh`) e mostra tabela lado-a-lado com ✓.

**Checklist pós-clone** (apresentado ao final, manual):
- [ ] `JWT_SECRET`, `ANON_KEY`, `SERVICE_ROLE_KEY` do Coolify novo idênticos aos do antigo.
- [ ] Reiniciar `supabase-storage-<UUID>` e `supabase-minio-<UUID>` no destino.
- [ ] `CLICKSIGN_WEBHOOK_URL` apontando pro novo domínio.
- [ ] Pausar webhook Fireflies durante cutover.
- [ ] Smoke test: login + abrir 1 ATA + gerar 1 pendência.

## Arquivos a modificar / criar / remover

**Criar:**
- `.claude/skills/clone-banco/scripts/generate-sql.sh` (~150 linhas, bash)
- `.claude/skills/clone-banco/scripts/validate-counts.sh` (~30 linhas, bash)
- `.claude/skills/clone-banco/templates/00-INSTRUCOES.md.tmpl` (template do guia que vai dentro da pasta de saída)

**Reescrever do zero:**
- `.claude/skills/clone-banco/SKILL.md` (~150-200 linhas, era ~360 linhas; descrição do frontmatter atualizada pra refletir "gera SQLs numerados pra clone manual" em vez de "snapshot/restore")

**Modificar:**
- `.gitignore` (raiz): adicionar `/clone-banco-sql/`

**Remover:**
- `scripts/clone-prod-db.sh` (raiz do repo)
- `.claude/skills/clone-banco/scripts/preview-snapshot.sh`
- `.claude/skills/clone-banco/scripts/preview-restore.sh`
- `.claude/skills/clone-banco/scripts/validate-snapshot.sh`
- `.claude/skills/clone-banco/scripts/validate-restore.sh`

**Não tocar:**
- `~/.ssh/hospital_clone_db` e `~/.ssh/config` (chave SSH e alias continuam servindo)
- `blueprint/deploy/project.json` (continua sendo a fonte da verdade da config da prod)

## Verificação end-to-end

1. **Geração funciona** — rodar `bash .claude/skills/clone-banco/scripts/generate-sql.sh` e ver se a pasta `clone-banco-sql/<timestamp>/` foi criada com os ~24 arquivos esperados (não-vazios).
2. **SQLs são válidos** — abrir 2-3 arquivos e conferir que são SQL plain (não binário), começam com `--` (comentário do pg_dump), e contêm `INSERT INTO` ou `CREATE TABLE` conforme esperado.
3. **Sequência roda em Postgres limpo** — opcional, pra ter mais confiança: subir um Postgres descartável local (`docker run --rm -d -p 5433:5432 -e POSTGRES_PASSWORD=test postgres:15-alpine`), rodar arquivos 01 → 99 com `psql -h localhost -p 5433 -U postgres -d postgres -f arquivo.sql`, verificar que `99-validation.sql` retorna contagens compatíveis. (Esse teste pode falhar em alguns objetos do schema `auth` que dependem de extensions/roles do Supabase — ver "riscos" abaixo.)
4. **SKILL.md ativa o workflow novo** — invocar `/clone-banco` na prática e confirmar que os 5 passos do workflow se executam corretamente em conversa.

## Riscos e considerações

- **Schema `auth` requer extensions e roles do Supabase** (`pgsodium`, `vault`, `supabase_auth_admin`). Ao rodar manualmente no destino, o container Supabase já provê isso — então `pg_dump --schema=auth --section=pre-data` pode pular `CREATE EXTENSION` e a aplicação do SQL no destino vai funcionar. Mas teste isolado em Postgres vanilla pode dar warnings ignoráveis (~14 warnings já documentados na skill atual).
- **`auth.users` traz hashes de senha** assinados com `JWT_SECRET` da origem. Sem copiar `JWT_SECRET` no Coolify novo, login das diretoras quebra — checklist pós-clone reforça isso.
- **`storage.objects` sem os bytes físicos**: ao abrir uma ATA antiga no destino, o frontend tenta baixar o PDF e dá 404. Comportamento esperado, listado nas INSTRUCOES.md.
- **Tabelas grandes podem estourar limite do SQL Editor do Supabase Studio** (~1MB por query). Workaround: rodar via `psql` diretamente, ou dividir o arquivo. A skill avisa quando um arquivo passa de 500KB.
- **Snapshot é instantâneo, mas não atômico**: se diretoras editam durante a geração, podem aparecer inconsistências leves entre arquivos. Pra cutover real, recomendar janela de manutenção.

## Observações

- O nome do arquivo deste plano (`me-explica-essa-skill-iterative-garden.md`) reflete a primeira pergunta do usuário, não o conteúdo final. Após `ExitPlanMode` aprovado, mover pra `<repo>/planos/plano-26-05-01-HHMMh-skill-clone-banco-sql.md` conforme regra do CLAUDE.md global.
- A skill antiga continua funcionando até a refatoração. Não há janela de transição complexa — é substituição direta dos arquivos.
