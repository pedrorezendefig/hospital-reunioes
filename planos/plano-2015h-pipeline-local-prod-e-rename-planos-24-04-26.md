# Plano — Ajuste da regra de nomes de planos + pipeline local→prod

## Context

Duas frentes solicitadas pelo usuário, em ordem:

1. **Ajustar a regra de nomes da pasta `planos/`**: hoje o `CLAUDE.md` do projeto exige `nome-do-plano-DD-MM-AAAA-HHMM.md` (ano com 4 dígitos, horário no final). O usuário quer encurtar: ano com 2 dígitos, horário reposicionado para a esquerda logo após o prefixo `plano-`, com sufixo `h` como identificador visual. Formato escolhido: `plano-HHMMh-nome-DD-MM-AA.md`.

2. **Enxugar a camada de migrations e desenhar o caminho de levar tudo que está em local (schema + dados) para produção**. Hoje existe um arquivo órfão `migrations-producao.sql` na raiz (bundle de 4 de abril, 24 migrations, stale — faltam 6 migrations novas e a numeração foi refatorada). O usuário confirmou que "teste" = ambiente local atual (não há staging), e quer que prod seja uma **cópia** do estado local: schema + `seed.sql` + `bulk_seed.py` + ATAs migradas + storage.

Resultado esperado:
- Convenção de nomes mais legível e consistente (horário visível).
- Bundle stale removido, fonte única de verdade = pasta `hospital-reunioes/supabase/migrations/`.
- Runbook claro do que levar para produção (schema → dados → storage), usando a skill `/deploy` já existente.

---

## Parte 1 — Nova regra de nomes de planos

### 1.1 Editar `CLAUDE.md` do projeto

Arquivo: `/Users/pedrorezende/PedroDev/Hospital/CLAUDE.md`

Trecho atual (linhas 14-23):
```
Quando o usuário pedir planejamento, criar o plano em **`planos/`** (pasta versionada na raiz do projeto), com nome no formato:

```
nome-do-plano-DD-MM-AAAA-HHMM.md
```

O timestamp reflete a **última atualização** do arquivo. Ao editar um plano existente, **renomear** para refletir o novo timestamp — fluxo:

1. `Edit` / `Write` no arquivo atual.
2. `mv planos/plano-foo-23-04-2026-1800.md planos/plano-foo-23-04-2026-1900.md` (com a data/hora do momento do save).
```

Trecho novo:
```
Quando o usuário pedir planejamento, criar o plano em **`planos/`** (pasta versionada na raiz do projeto), com nome no formato:

```
plano-HHMMh-nome-do-plano-DD-MM-AA.md
```

O horário (`HHMM` + sufixo `h`) aparece logo após o prefixo `plano-` para ficar visualmente evidente. O ano usa 2 dígitos. O timestamp reflete a **última atualização** do arquivo. Ao editar um plano existente, **renomear** para refletir o novo timestamp — fluxo:

1. `Edit` / `Write` no arquivo atual.
2. `mv planos/plano-1800h-foo-23-04-26.md planos/plano-1900h-foo-23-04-26.md` (com a data/hora do momento do save).
```

### 1.2 Renomear os 11 planos existentes

Usar `git mv` para preservar o histórico. Mapeamento (`DD-MM-AAAA-HHMM` → `HHMMh-DD-MM-AA`):

| Atual | Novo |
|-------|------|
| `dropdown-setor-cargo-23-04-2026-2149.md` | `plano-2149h-dropdown-setor-cargo-23-04-26.md` |
| `plano-admin-fix-21-04-2026-0410.md` | `plano-0410h-admin-fix-21-04-26.md` |
| `plano-correcao-participantes-ia-23-04-2026-2128.md` | `plano-2128h-correcao-participantes-ia-23-04-26.md` |
| `plano-deploy-unificado-20-04-2026-2330.md` | `plano-2330h-deploy-unificado-20-04-26.md` |
| `plano-estrutura-ata-obrigatoria-21-04-2026-0307.md` | `plano-0307h-estrutura-ata-obrigatoria-21-04-26.md` |
| `plano-importacao-ata-migracao-em-massa-20-04-2026-2255.md` | `plano-2255h-importacao-ata-migracao-em-massa-20-04-26.md` |
| `plano-match-responsavel-importacao-20-04-2026-2003.md` | `plano-2003h-match-responsavel-importacao-20-04-26.md` |
| `plano-participantes-super-admin-22-04-2026-1132.md` | `plano-1132h-participantes-super-admin-22-04-26.md` |
| `plano-pente-fino-pre-deploy-23-04-2026-0133.md` | `plano-0133h-pente-fino-pre-deploy-23-04-26.md` |
| `plano-simplificar-blueprint-23-04-2026-0301.md` | `plano-0301h-simplificar-blueprint-23-04-26.md` |
| `plano-superadmin-crud-21-04-2026-0308.md` | `plano-0308h-superadmin-crud-21-04-26.md` |

Observações:
- `dropdown-setor-cargo-23-04-2026-2149.md` não tinha prefixo `plano-` no nome antigo; o renome adiciona para padronizar.
- O comentário legado no topo de `plano-estrutura-ata-obrigatoria-*.md` falando sobre "copiar pra raiz" está obsoleto; pode ser removido na mesma passada (opcional, não bloqueante).

---

## Parte 2 — Pipeline local → produção

### 2.1 Destino do `migrations-producao.sql`

**Decisão: deletar.** O arquivo:
- Foi congelado em 4 de abril (24 migrations até `021_remove_onboarding_policies`).
- Tem numeração e conteúdo incompatíveis com a pasta atual (a pasta foi refatorada: migrations renumeradas, gap intencional em 021-022, 6 migrations novas 023-030).
- Não é referenciado por nenhuma skill, script, hook ou documento (`blueprint/`, `docs/`, `.github/`, `.claude/skills/`).
- Git preserva o histórico; deletar não perde informação.

Ação: `git rm migrations-producao.sql` (na execução, não aqui).

**Fonte única de verdade de schema após a limpeza:** `hospital-reunioes/supabase/migrations/` (28 arquivos, 001-030 com gap em 021-022, tudo aplicado via Supabase CLI em `supabase start`, `supabase db reset` e `supabase db push`).

### 2.2 Schema — o que precisa ir para produção

As 28 migrations da pasta cobrem tudo. Categorizadas:

**Estrutura (tabelas + enums + sequences):**
- 001-008: participantes, reunioes, pendencias, tokens_validacao, signup_requests, storage_buckets, comentarios_pendencias, notificacoes
- 012: user_preferences
- 014: colunas `is_externo`, `co_responsavel_*`
- 016, 020: metadados de importação de ATAs
- 017: `is_super_admin`
- 018: `audit_log`
- 019: `bulk_jobs`
- 025, 026: ajustes de tipo (id_reuniao VARCHAR(30), email NULL)
- 027, 028: taxonomia (setores, cargos, tipos_reuniao + FKs)
- 030: soft delete em reunioes/pendencias

**Segurança (RLS):**
- 009: ENABLE RLS default-deny nas 9 tabelas principais
- 023: ENABLE RLS em `audit_log` e `bulk_jobs`

**Lógica atômica (RPCs — críticas):**
- 001: `generate_participant_id()`
- 002: `update_updated_at()` (trigger function)
- 010: `incrementar_acoes_concluidas()`, `decrementar_acoes_concluidas()`
- 024: `confirmar_importacao_atomico()` (usada pelo backend durante `/migrar-atas`)
- 029: `merge_participante_externo()` (super-admin)

**Alterações pontuais:**
- 011, 013: expansões de enums/checks
- 015: remove triggers de email legados

Gap 021-022 é cosmético (intencional). Supabase CLI ordena lexicograficamente e aplica em ordem sem exigir sequência contínua.

Aplicação em prod: via **skill `/deploy`** (já instalada globalmente, referenciada em `blueprint/DEPLOY.md`). A skill valida env vars, dispara o deploy no Coolify, e as migrations são aplicadas pelo Supabase CLI contra o banco configurado.

### 2.3 Dados — o que copiar de local para produção

Usuário escolheu: `seed.sql` + `bulk_seed.py` + ATAs migradas + **tudo que está em local** (cópia exata).

Como o banco local já contém o resultado combinado disso tudo (seed + bulk_seed rodaram; `/migrar-atas` já ingeriu as 24 ATAs), a estratégia mais simples é **`pg_dump --data-only` do local + restore em prod**, em vez de re-rodar cada script individual.

Escopo do dump:

| Conjunto | Comando | Observação |
|---|---|---|
| `public` (aplicação) | `pg_dump -h 127.0.0.1 -p 54352 -U postgres --data-only --schema=public -f public-data.sql postgres` | Porta do Supabase CLI local (ver `config.toml`). Contém participantes, reuniões, pendências, comentários, notificações, audit_log, bulk_jobs, taxonomia. |
| `auth.users` + `auth.identities` | `supabase db dump --data-only --schema=auth` (ou equivalente via psql) | Só os usuários reais. Os 2 users demo do `seed.sql` (admin@hospital.com, pmrdef@gmail.com) são placeholders de dev — **remover ou resetar senha em prod** (ver 2.5). |
| `storage.objects` + arquivos físicos | `supabase storage` CLI ou script que baixa local e faz upload em prod | Buckets: `audios`, `transcricoes`, `pdfs`, `pdfs-assinados`. |

Depois do restore, **resetar sequences** (`SELECT setval('participantes_id_seq', (SELECT MAX(id::int) FROM ...))`) para evitar colisão de IDs futuros.

**Alternativa (se o dump for problemático)**: rodar `seed.sql` + `bulk_seed.py` em prod, e repetir a importação de ATAs via `/migrar-atas` com os PDFs em `atas-migracao/`. Mais determinístico em termos de schema, mas `/migrar-atas` depende de IA para parsing (resultado não-bit-exact). Só adotar se o dump tiver complicações com `auth.*`.

### 2.4 Storage — buckets privados

Migrations 006 + 014 criam 4 buckets privados. Os arquivos físicos (uploads reais em dev) **não** estão no `pg_dump`; precisam de sincronização separada:

- Opção A: script Python curto que lista `storage.objects` local, baixa via Supabase Storage API local, faz upload via Storage API prod.
- Opção B: `rclone` se os backends de storage forem acessíveis diretamente (S3-compatible).

Detalhar na execução; o volume/tamanho real dos buckets decide qual caminho.

### 2.5 Ressalvas antes de executar

Itens que precisam decisão na hora do ship, não agora:

1. **Usuários seed do `seed.sql`**: `admin@hospital.com` e `pmrdef@gmail.com` com senha demo hashed. Em prod: (a) remover ambos, ou (b) trocar senha, ou (c) manter só `pmrdef@gmail.com` como super-admin. Não commitar senha nova em `seed.sql`.
2. **Secrets hardcoded no `.env` local** (OpenAI, ClickSign, Resend): **não** viajam no pg_dump. São setados via Coolify/skill `/deploy` com valores de prod separados. Confirmar inventário contra `blueprint/DEPLOY.md` seção `config-env`.
3. **URL do Supabase em prod** ≠ local. `NEXT_PUBLIC_SUPABASE_URL` e `SUPABASE_URL` apontam para a instância Supabase do Coolify (`studio.mala-ia.cloud` ou equivalente). Confirmar no blueprint.
4. **ATAs migradas como "dados reais"**: confirmar com o usuário na execução se as 24 ATAs e 136 pendências devem aparecer em prod desde o dia 1 (ele disse que sim — é a "cópia" — mas vale confirmar antes do restore).

---

## Arquivos que serão modificados na execução

1. `/Users/pedrorezende/PedroDev/Hospital/CLAUDE.md` — atualizar seção "Planos" (linhas 14-23).
2. `/Users/pedrorezende/PedroDev/Hospital/planos/*.md` — renomear os 11 arquivos via `git mv`.
3. `/Users/pedrorezende/PedroDev/Hospital/migrations-producao.sql` — `git rm`.
4. (Opcional) Comentário no topo de `plano-estrutura-ata-obrigatoria-*.md` (legado obsoleto).

## Arquivos que NÃO mudam nesta fase

- `hospital-reunioes/supabase/migrations/*.sql` — fonte de verdade, fica como está.
- `hospital-reunioes/supabase/seed.sql` — não muda agora; revisão acontece no ship (ressalva 2.5.1).
- `blueprint/DEPLOY.md` e `blueprint/README.md` — a skill `/deploy` cuida disso quando o ship for feito.

---

## Verificação

1. **Regra de nomes**:
   - `cat CLAUDE.md | grep -A 10 "planos/"` mostra o novo formato.
   - `ls planos/` lista 11 arquivos no padrão `plano-HHMMh-nome-DD-MM-AA.md`.
   - `git log --diff-filter=R --name-status` mostra os renames preservando histórico.

2. **Bundle removido**:
   - `ls /Users/pedrorezende/PedroDev/Hospital/migrations-producao.sql` retorna "No such file or directory".
   - `git log --all -- migrations-producao.sql` ainda mostra os commits antigos (histórico preservado).
   - `grep -r "migrations-producao" blueprint/ docs/ .claude/ 2>/dev/null` retorna vazio (sem referências quebradas).

3. **Schema em prod** (quando o ship acontecer):
   - Conectar no Supabase prod e rodar: `SELECT version, name FROM supabase_migrations.schema_migrations ORDER BY version;` — deve listar 001 até 030 (com gap 021-022).
   - Sanity queries: `SELECT COUNT(*) FROM participantes;`, `SELECT COUNT(*) FROM reunioes;`, `SELECT COUNT(*) FROM pendencias;` — comparar com os mesmos counts em local.

4. **Dados em prod** (quando o ship acontecer):
   - Login com `pmrdef@gmail.com` funciona.
   - Página de reuniões lista as ATAs migradas.
   - Storage: abrir uma ata com PDF assinado e confirmar que o arquivo carrega.

---

## Execução / Resultados

(A ser preenchido durante a execução com desvios, comandos exatos rodados, counts antes/depois, e itens pendentes.)
