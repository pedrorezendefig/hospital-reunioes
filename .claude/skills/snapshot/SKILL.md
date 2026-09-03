---
name: snapshot
description: Mantém docs/spec/snapshots/ (rotas, entidades, schema, migrations, integrações) gerado do código; roda no fim do /deploy ship. Manual: `python3 .claude/skills/snapshot/scripts/snapshot.py [--check]`.
---

# snapshot — manter `docs/spec/snapshots/` fresco

Uma skill, sete arquivos vivos. O time tem sempre um **mapa atualizado** da aplicação sem precisar manter nada à mão (exceto o que naturalmente exige curadoria humana: fluxogramas e descrições semânticas da estrutura de pastas).

> **Implementação real:** [`scripts/snapshot.py`](scripts/snapshot.py) (Python stdlib, ~1000 linhas, self-contained).
> O pseudocódigo nas seções abaixo é a **especificação executável** — descreve o que o script faz, na ordem em que faz. Quando este SKILL.md e o script divergem, o script é a fonte da verdade.

## Princípio arquitetural

**Esta skill é metodologia pura.** Lê config de `docs/spec/deploy/project.json` (compartilhada com `/deploy` e `/ship`). Não tem conhecimento hardcoded sobre projetos específicos.

A skill executa sempre o mesmo algoritmo (detectar mudança → parsear → gerar → comparar → commit se mudou). Cada gerador é parametrizado pelo `project.json` do repo atual.

Relação com outras skills:
- **`/deploy ship`**: chama `/snapshot` no Passo 9.4 (pós-health verde, antes de fechar). Snapshot regenerado é commitado em commit separado `chore(spec): snapshot pós deploy <sha7>`.
- **`/ship`**: usa `/snapshot --diff <base>..HEAD` no Passo 7 pra gerar a seção "Mudanças" do PR body.

## Sintaxe

Invocação direta do script (forma canônica):

```bash
python3 .claude/skills/snapshot/scripts/snapshot.py [flags]
```

Flags suportadas pelo script:

| Flag | Efeito |
|------|--------|
| (sem flag) | Regenera 5 MDs auto-gerados (ROTAS, ENTIDADES, SCHEMA, MIGRATIONS, INTEGRACOES) se algo mudou. Cria commit separado `chore(spec): atualizar snapshot pós deploy <sha>`. |
| `--check` | Dry-run: mostra que arquivos mudariam, não escreve nem commita. |
| `--diff <base>..HEAD` | Markdown comparando snapshot esperado com o que teria depois das mudanças entre `<base>` e `HEAD`. Usado pelo `/ship` no Passo 7 pra preencher seção "Mudanças" do PR body. Não escreve em `docs/spec/snapshots/`. |
| `--force` | Regenera tudo ignorando idempotência (útil pra debug). |
| `--only <ARQUIVO>` | Regenera só 1 dos 5 auto-gerados (ROTAS / ENTIDADES / SCHEMA / MIGRATIONS / INTEGRACOES). **Não aceita** FLUXOGRAMAS ou ESTRUTURA (são curados humano). |
| `--no-commit` | Não cria commit automático (default: commita). Mudanças ficam no working tree. |
| `--root <path>` | Raiz do repo (default: cwd). |

Observação: `FLUXOGRAMAS.md` e `ESTRUTURA.md` são **curados humano** (blocos `<!-- curated -->`). O script só alerta de gaps (rotas/estados novos sem fluxograma correspondente), nunca sobrescreve.

Flag relacionada (no `/deploy ship`): `--skip-snapshot` pula a invocação do script no Passo 9.4 do deploy (só pra emergência). Ver `.claude/skills/deploy/SKILL.md`.

---

## Bootstrap (toda invocação)

1. **Descobrir raiz do repo:**
   ```bash
   REPO_ROOT=$(git -C "$PWD" rev-parse --show-toplevel)
   ```
   Se falhar → "Não é um repositório git." e PARAR.

2. **Ler `project.json`:** `$REPO_ROOT/docs/spec/deploy/project.json`. Se ausente → PARAR com mensagem "Rode `/deploy setup` primeiro".

3. **Garantir pasta:** `mkdir -p $REPO_ROOT/docs/spec/snapshots/`.

4. **Capturar paths críticos** do `project.json`:
   - `routers_dir`: derivar dos `services[].diff_routing.trigger_paths` que contém `routers/` (default Hospital: `hospital-reunioes/backend/app/routers/`)
   - `migrations_dir`: `project.migrations.dir` (Hospital: `hospital-reunioes/supabase/migrations`)
   - `backend_app_dir`: derivar pra estrutura (Hospital: `hospital-reunioes/backend/app/`)
   - `frontend_src_dir`: derivar pra estrutura (Hospital: `hospital-reunioes/frontend/src/`)
   - `supabase_dir`: derivar (Hospital: `hospital-reunioes/supabase/`)
   - `integrations`: `project.project.integrations[]`

---

## Algoritmo principal

Detectar mudança → parsear (app FastAPI montado, migrations, `project.json`) → gerar os 5 MDs → comparar → commit `chore(spec):` só se mudou. A implementação é `scripts/snapshot.py`, que é a fonte da verdade. A especificação passo a passo, com o pseudocódigo de cada gerador e o exemplo de saída dos 7 documentos, está em `references/algoritmo-e-exemplos.md`: leia só para mudar a geração.

---

## Modo `--diff <base>..HEAD`

Caso de uso: o `/ship` invoca `/snapshot --diff main..HEAD` no Passo 7 pra preencher a seção "Mudanças" do PR body.

```bash
/snapshot --diff main..HEAD
```

Comportamento:
1. Roda algoritmo principal mas escreve buffer numa pasta temporária `/tmp/snapshots-diff-<sha>/`.
2. Compara `/tmp/snapshots-diff-<sha>/*.md` com `docs/spec/snapshots/*.md` atual.
3. Gera markdown:

```markdown
## 📊 Mudanças no snapshot

### Rotas
- ✨ Nova: `POST /pendencias/{id}/repactuar`
- 🔧 Modificada: `GET /reunioes` agora aceita `?status_ata=ASSINADA`
- ❌ Removida: `GET /admin/legacy/*`

### Entidades
- 🆕 Tabela nova: `pendencias_repactuacoes`
- ➕ Coluna nova em `pendencias`: `repactuada_em` (TIMESTAMPTZ)

### Migrations
- ➕ `039_pendencias_repactuacoes.sql`: criar tabela de histórico de repactuação

### Integrações
- (sem mudanças)
```

4. Imprime no stdout. **Não commita.** Não escreve nada em `docs/spec/snapshots/`.

Esse markdown é o que vai pra dentro do PR body do `/ship`.

---

## Modo `--check` (dry-run)

```bash
/snapshot --check
```

Roda algoritmo principal, mostra que arquivos mudariam e o diff resumido, mas **não escreve nem commita**.

Output:

```
═══ /snapshot --check ═══

Arquivos que mudariam:
  ROTAS.md (12 linhas adicionadas, 3 removidas)
  ENTIDADES.md (5 linhas adicionadas)
  MIGRATIONS.md (1 linha adicionada)

Sem mudanças:
  SCHEMA.md, INTEGRACOES.md, FLUXOGRAMAS.md, ESTRUTURA.md

Alertas:
  ⚠ Rota nova `/pendencias/repactuar` sem fluxograma

Rode `/snapshot` (sem --check) pra aplicar as mudanças.
```

---

## Modo `--only <arquivo>`

```bash
/snapshot --only ROTAS
```

Regenera só 1 arquivo (útil em desenvolvimento da skill ou pra testar geradores individualmente). Aceita: `ROTAS`, `ENTIDADES`, `SCHEMA`, `MIGRATIONS`, `INTEGRACOES`, `ESTRUTURA`. **Não aceita `FLUXOGRAMAS`** (esse não é regenerado, só alertado).

---

## Anti-padrões críticos

- ❌ Hardcodar paths como `hospital-reunioes/backend/...` na skill. Tudo vem de `project.json`.
- ❌ Regenerar `FLUXOGRAMAS.md` automaticamente. Esse arquivo é curado por humano.
- ❌ Sobrescrever blocos `<!-- curated:start -->...<!-- curated:end -->`. **Sempre preservar.**
- ❌ Commitar se nada mudou. Idempotência é regra.
- ❌ Disparar `/deploy ship` em loop. Scope map em `project.json` garante que `chore(spec):` não vira deploy.
- ❌ Ler valores de secrets (mesmo só nomes) pra escrever em INTEGRACOES.md como valor. **Só o `env_key` (nome da variável)**, nunca o valor.

---

## Relação com outras skills

| Skill | Quando interage |
|---|---|
| **`/deploy ship`** | Invoca `/snapshot` no Passo 9.4 (pós health verde). Commit separado entra antes do prepend do CHANGELOG.md. |
| **`/ship`** | Invoca `/snapshot --diff <base>..HEAD` no Passo 7 pra preencher "Mudanças" do PR body. |

---

## Verificação manual

```bash
# Rodar dry-run
python3 .claude/skills/snapshot/scripts/snapshot.py --check

# Aplicar de verdade (com commit automático)
python3 .claude/skills/snapshot/scripts/snapshot.py

# Aplicar sem commitar (deixa no working tree pra inspecionar)
python3 .claude/skills/snapshot/scripts/snapshot.py --no-commit

# Conferir
ls -la docs/spec/snapshots/
git log --oneline -5 docs/spec/snapshots/

# Regenerar 1 só
python3 .claude/skills/snapshot/scripts/snapshot.py --force --only ROTAS

# Gerar markdown pra PR body
python3 .claude/skills/snapshot/scripts/snapshot.py --diff main..feat/minha-branch
```

### Stats típicas (repo Hospital Reuniões)

- 78 endpoints em 13 routers detectados via AST
- 13 tabelas reconstruídas cumulativamente das 36 migrations
- ~18 relacionamentos FK detectados (vão pro Mermaid ER)
- 5 integrações externas mapeadas (OpenRouter, OpenAI, ClickSign, Resend, Fireflies)

Esses números crescem/diminuem conforme o código evolui — o script reflete sempre o estado atual.

---

## Falhas e recuperação

| Cenário | Ação |
|---|---|
| `project.json` ausente | PARAR com "Rode `/deploy setup` primeiro" |
| Routers Python com sintaxe inválida | Skipa o arquivo, adiciona warning no output, continua. Não bloqueia. |
| Migration SQL malformada | Skipa, warning, continua. ENTIDADES.md tenta reconstruir do que conseguiu parsear. |
| Bloco `<!-- curated -->` mal-fechado | Preserva tudo entre `<!-- curated:start -->` e fim do arquivo, warning, segue. |
| Commit falha (working tree sujo) | Reporta erro, NÃO força. Usuário decide. |
