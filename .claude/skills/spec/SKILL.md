---
name: spec
description: Skill universal de spec-driven development via REVERSA. Mantém docs/spec/ gerado por agents IA do framework REVERSA (sandeco/reversa). Subcomandos. /spec init instala REVERSA, configura output.folder=docs/spec/, ajusta .gitignore, cria diretórios. /spec update dispara o pipeline fullstack (Reversa+Scout+Architect+Writer+Reviewer+Visor+Data Master+Design System) e regenera docs/spec/ ~10-12 min. /spec status mostra SHA do último spec, idade, drift detectado via manifesto SHA-256. /spec historico regenera docs/spec/historico/YYYY-MM.md (algoritmo herdado de /blueprint historico, agrupado por tipo, com autor de cada commit). /spec migrate-blueprint move blueprint/deploy → docs/spec/deploy, blueprint/mudancas → docs/spec/chronicles, blueprint/sql e blueprint/proposta-trabalho → docs/operacional/, deleta blueprint/, atualiza CLAUDE.md. Substitui a skill /blueprint integralmente. Funciona em qualquer projeto que tenha (ou possa criar) docs/spec/deploy/project.json.
---

# spec — spec-driven development via REVERSA

Esta skill mantém a especificação executável do projeto em `docs/spec/`, gerada continuamente pelos agents IA do framework REVERSA (https://github.com/sandeco/reversa). Substitui integralmente a skill antiga `/blueprint`.

## Comandos

| Comando | Faz |
|---|---|
| `/spec` (sem args) | Se não há `docs/spec/`: oferece `init`. Se há: roteia pra `status`. |
| `/spec init` | Instala REVERSA via `npx reversa install`, configura `.reversa/config.toml` com `output.folder = "docs/spec"`, ajusta `.gitignore`, cria diretórios essenciais. |
| `/spec update` | Dispara o pipeline fullstack do REVERSA. ~10-12 min. Regenera `docs/spec/` (arquitetura, C4, ERD, UI, schema). |
| `/spec status` | Read-only. Mostra SHA do último spec gerado, idade, drift detectado, agents pendentes. |
| `/spec historico` | Gera/atualiza `docs/spec/historico/YYYY-MM.md` agregando commits do mês. Algoritmo herdado de `/blueprint historico`. |
| `/spec migrate-blueprint` | Migra a estrutura `blueprint/` antiga (caseira) pra `docs/spec/`. 1× por projeto. Idempotente. |

---

## Princípio arquitetural

**Esta skill é metodologia pura.** Zero conhecimento sobre projetos específicos — nada de "Hospital", "mala-ia.cloud", "OPENAI_API_KEY" hardcoded. Tudo varia conforme `docs/spec/deploy/project.json` do repo.

Relação com outras skills:
- **`/deploy`**: lê `docs/spec/deploy/project.json` e escreve `docs/spec/deploy/state.json` + `history.json`. Ao final do ship, invoca `/spec update` como Passo 9 (substitui o antigo `/blueprint update`).
- **`/ship`** (orquestrador do workflow de time): chama `/spec` pra criar chronicle 🟡 antes do trabalho e renomear pra 🟢/🔴 depois do deploy.
- **`/blueprint`**: substituída por esta skill. Deve ser apagada de `~/.claude/skills/blueprint/` após migração.

---

## Bootstrap (executado em todo modo, antes de qualquer outra coisa)

1. **Descobrir raiz do repo:**
   ```bash
   REPO_ROOT=$(git -C "$PWD" rev-parse --show-toplevel)
   ```
   Se falhar → reportar "Não é um repositório git." e PARAR.

2. **Detectar paths:**
   - `SPEC_DIR="$REPO_ROOT/docs/spec"`
   - `PROJECT_JSON="$SPEC_DIR/deploy/project.json"` (preferencial)
   - `LEGACY_PROJECT_JSON="$REPO_ROOT/blueprint/deploy/project.json"` (fallback durante migração)
   - `STATE_JSON="$SPEC_DIR/deploy/state.json"`
   - `HISTORY_JSON="$SPEC_DIR/deploy/history.json"`
   - `CHANGELOG_MD="$SPEC_DIR/CHANGELOG.md"`
   - `REVERSA_CONFIG="$REPO_ROOT/.reversa/config.toml"`
   - `REVERSA_STATE="$REPO_ROOT/.reversa/state.json"`
   - `REVERSA_MANIFEST="$REPO_ROOT/.reversa/_config/files-manifest.json"`

3. **Roteamento por modo + estado:**

| Modo | `SPEC_DIR` existe | `PROJECT_JSON` existe | Ação |
|---|---|---|---|
| sem args | não | — | reportar "Sem `docs/spec/`. Roda `/spec init` ou `/spec migrate-blueprint`." e PARAR |
| sem args | sim | sim | rotear pra `status` |
| sem args | sim | não | reportar "Estrutura incompleta. Roda `/spec init` ou `/deploy setup`." e PARAR |
| `init` | qualquer | qualquer | seguir pra modo `init` |
| `update` | sim | sim | seguir pra modo `update` |
| `update` | qualquer outro | — | reportar "Sem `docs/spec/`. Roda `/spec init` primeiro." e PARAR |
| `status` | sim | sim | seguir pra modo `status` |
| `historico` | qualquer | qualquer | seguir pra modo `historico` (não exige project.json) |
| `migrate-blueprint` | qualquer | qualquer | seguir pra modo `migrate-blueprint` |

4. **Validar Node 18+** (só no `init` e `update`):
   ```bash
   NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)
   if [ "$NODE_VERSION" -lt 18 ]; then
     echo "REVERSA exige Node 18+. Detectado: $(node --version). Atualize Node antes de continuar."
     exit 1
   fi
   ```

---

## Modo: init

Instala o REVERSA no repo, configura `output.folder` e cria diretórios essenciais. Idempotente.

### Passos

1. **Pré-condições**:
   - `node --version` >= 18 (já validado no bootstrap).
   - Repo limpo de modificações não commitadas em `.reversa/` (se já existir).

2. **Rodar `npx reversa install`**:
   ```bash
   cd "$REPO_ROOT"
   npx reversa install
   ```

   - Cria `.reversa/`, `.agents/skills/reversa-*`, `.claude/skills/reversa-*`.
   - Pergunta sobre engine (responder "claude-code" ou pular se já configurado).
   - **Se `.reversa/` já existe**: REVERSA pergunta "Reinstall?". Responder "no" pra preservar config.

3. **Editar `.reversa/config.toml`** (criar se REVERSA não criou):
   ```toml
   [output]
   folder = "docs/spec"

   [agents]
   installed = [
     "reversa",
     "reversa-scout",
     "reversa-archaeologist",
     "reversa-architect",
     "reversa-writer",
     "reversa-reviewer",
     "reversa-visor",
     "reversa-data-master",
     "reversa-design-system"
   ]
   ```

   Se o agent `reversa-chronicler` existir no upstream (verificar com `ls .agents/skills/ | grep chronicler`), adicionar ao array.

4. **Garantir `.gitignore`**:
   ```bash
   for pattern in ".reversa/" ".agents/" "_reversa_sdd/"; do
     grep -qxF "$pattern" "$REPO_ROOT/.gitignore" || echo "$pattern" >> "$REPO_ROOT/.gitignore"
   done
   ```

5. **Criar estrutura `docs/spec/`**:
   ```bash
   mkdir -p "$SPEC_DIR/deploy" "$SPEC_DIR/chronicles" "$SPEC_DIR/historico" "$REPO_ROOT/docs/operacional"
   ```

6. **Criar `docs/spec/README.md`** (se ausente) explicando humano vs auto-gerado:
   ```markdown
   # docs/spec — Especificação executável via REVERSA

   Esta pasta mistura conteúdo gerado automaticamente pelo REVERSA com
   conteúdo curado por humanos. Quem pode editar o quê:

   ## Auto-gerado pelo `/spec update` (NÃO editar à mão)
   - `sdd/`, `architecture.md`, `c4-*.md`, `erd-complete.md`
   - `domain.md`, `data-dictionary.md`, `state-machines.md`
   - `permissions.md`, `gaps.md`, `confidence-report.md`
   - `traceability/`, `inventory.md`

   ## Humano (editar livremente)
   - `deploy/project.json` (config de deploy/Coolify)
   - `chronicles/🟡-*.md` (planos abertos)
   - `historico/YYYY-MM.md` (resumo mensal de commits)
   - `CHANGELOG.md` (cronologia flat, append-only pelo /ship)
   - `README.md` (este arquivo)

   ## Auto-gerado mas semântica humana
   - `chronicles/🟢-*.md` e `chronicles/🔴-*.md` (criados/renomeados
     pelo /deploy ship com base no plano 🟡 correspondente)
   - `deploy/state.json` e `deploy/history.json` (escritos pelo /deploy)
   ```

7. **Criar `docs/spec/CHANGELOG.md`** (se ausente):
   ```markdown
   # Changelog Hospital Reuniões

   Cronologia de deploys em ordem reversa (mais recente no topo).
   Cada entrada é prepended pelo `/ship` ao final do `/deploy ship`.

   ---

   _(sem deploys registrados ainda)_
   ```

8. **Reportar**:
   ```
   /spec init concluído.
   - REVERSA instalado em $REPO_ROOT/.reversa/
   - Agents em $REPO_ROOT/.agents/skills/
   - Saída configurada pra docs/spec/
   - Estrutura criada: docs/spec/{deploy,chronicles,historico}, docs/operacional/
   - .gitignore atualizado

   Próximo passo: /spec migrate-blueprint (se vindo de blueprint/) ou /spec update.
   ```

---

## Modo: update

Dispara o pipeline fullstack do REVERSA pra regenerar `docs/spec/`. ~10-12 min.

### Passos

1. **Pré-condições**:
   - `npx reversa --version` retorna OK.
   - `.reversa/config.toml` existe.
   - `docs/spec/deploy/project.json` existe.

2. **Verificar drift do código** (rápido):
   ```bash
   git diff --stat HEAD  # mostra escopo de mudança
   ```
   Se diff vazio E `.reversa/state.json` indica spec recente (<24h) → sugerir pular (`--force` pra rodar mesmo assim).

3. **Disparar pipeline em sequência** (cada agent é uma chamada `Skill` tool):
   - `Skill` invoke `reversa-scout` (descoberta + inventário)
   - `Skill` invoke `reversa-archaeologist` (dependências + camadas)
   - `Skill` invoke `reversa-architect` (C4 + ERD)
   - `Skill` invoke `reversa-data-master` (schema DB completo)
   - `Skill` invoke `reversa-visor` (UI/telas)
   - `Skill` invoke `reversa-design-system` (tokens + componentes)
   - `Skill` invoke `reversa-writer` (gera MDs do SDD)
   - `Skill` invoke `reversa-reviewer` (valida, marca 🟢🟡🔴)
   - `Skill` invoke `reversa-chronicler` (se existir no install)

   Pra cada agent, capturar saída resumida (não logar tudo).

4. **Verificar saída**:
   - `docs/spec/` deve ter os arquivos atualizados.
   - `.reversa/state.json` deve ter `phase: completed`.

5. **Atualizar manifesto SHA-256** (delegado ao próprio REVERSA, mas validar):
   ```bash
   ls -la "$REVERSA_MANIFEST" 2>/dev/null && \
     echo "Manifesto atualizado: $(jq 'keys | length' "$REVERSA_MANIFEST") arquivos rastreados"
   ```

6. **Reportar**:
   ```
   /spec update concluído em <duração>.
   Arquivos gerados/atualizados:
     - docs/spec/architecture.md
     - docs/spec/c4-context.md
     - docs/spec/c4-containers.md
     - docs/spec/c4-components.md
     - docs/spec/erd-complete.md
     - docs/spec/sdd/...
     - docs/spec/gaps.md
     - docs/spec/confidence-report.md
     - docs/spec/traceability/...

   Lacunas (🔴) detectadas: <N> (ver docs/spec/gaps.md)
   ```

7. **Tratamento de erro**:
   - Se algum agent falhar: reportar qual, mostrar últimas 20 linhas de output.
   - Pipeline NÃO faz rollback automático. Spec parcial fica como está.
   - Próximo `/spec update` retoma.

---

## Modo: status

Read-only. Imprime resumo curto. Não escreve nada.

### Passos

1. **Ler `.reversa/state.json`** (se existir):
   - `phase` (last completed)
   - `completed` (lista de agents finalizados)
   - `pending` (lista de agents pendentes)
   - `updated_at`

2. **Ler `docs/spec/deploy/state.json`** (se existir):
   - SHA da última geração de deploy
   - Idade

3. **Calcular drift**:
   ```bash
   SPEC_LAST_SHA=$(jq -r '.last_run.sha // empty' "$STATE_JSON" 2>/dev/null)
   CURRENT_SHA=$(git -C "$REPO_ROOT" rev-parse --short HEAD)
   if [ -n "$SPEC_LAST_SHA" ] && [ "$SPEC_LAST_SHA" != "$CURRENT_SHA" ]; then
     COMMITS_AHEAD=$(git rev-list --count "$SPEC_LAST_SHA..HEAD" 2>/dev/null || echo "?")
     echo "Spec STALE: $COMMITS_AHEAD commit(s) à frente"
   else
     echo "Spec ATUAL"
   fi
   ```

4. **Detectar modificações no manifesto** (custom edits humanos):
   ```bash
   if [ -f "$REVERSA_MANIFEST" ]; then
     # Itera entries, compara SHA atual com armazenado
     # Lista arquivos 'modified' (humano editou) e 'missing' (apagado)
     :
   fi
   ```

5. **Output**:
   ```
   ═══ Spec — <project.name> ═══

   Última geração:
     SHA: <spec_last_sha> (<idade>)
     Status: <ATUAL | STALE <N> commits>

   Pipeline:
     Phase: <completed|in_progress>
     Agents completados: <N>/<total>
     Pendentes: <lista se houver>

   Customizações humanas (preservadas):
     - <arquivo1> (modificado)
     - <arquivo2> (modificado)

   Chronicles em aberto (🟡):
     - <arquivo1>
     - <arquivo2>

   Último deploy (de docs/spec/deploy/state.json):
     <data> · <sha> · <result>

   Para regenerar: /spec update
   ```

---

## Modo: historico

Gera `docs/spec/historico/YYYY-MM.md` agregando commits do mês a partir de `git log`. **Algoritmo herdado verbatim de `/blueprint historico` antigo**, com pequenas adaptações (paths, autor).

### 1. Guards

Sair silencioso se:
- `.git/rebase-merge/` ou `.git/rebase-apply/` existe.
- `.git/MERGE_HEAD` ou `.git/CHERRY_PICK_HEAD` existe.
- Working tree com conflitos não resolvidos.

### 2. Determinar último SHA já registrado

- `ls docs/spec/historico/*.md` ordenado reverso (pega mês mais recente).
- Se nenhum arquivo: `RANGE="HEAD~10..HEAD"` (últimos 10 commits).
- Se existe: extrair **primeiro** SHA curto do padrão `- \`<sha>\``. Esse é `ultimo_sha`. `RANGE="<ultimo_sha>..HEAD"`.

### 3. Coletar commits novos

```bash
git log $RANGE --reverse --pretty=format:"%H%x09%h%x09%ai%x09%an%x09%ae%x09%s%x09%b%x1E"
```

Campos: SHA full, SHA curto, autor data ISO, autor nome, autor email, subject, body, RS.

Diferença vs `/blueprint historico` antigo: adiciona `%an` (nome) e `%ae` (email).

### 4. Resumir cada commit

Pra cada commit, linha no formato:
```
- `<sha_curto>` <subject> — @<autor>
  <resumo em pt-BR explicando o porquê — 1 frase, max 2>
```

- Resumo: usar `%b` se houver; senão inferir de `%s` + `git show --stat <sha>`.
- Autor: extrair handle do email (`@<local-part>`) ou nome.

### 5. Agrupar por dia e mês

- Dia = primeiros 10 chars de `%ai` (`YYYY-MM-DD`).
- Mês = primeiros 7 chars de `%ai` (`YYYY-MM`).

### 6. Inserir no arquivo do mês

**Se `docs/spec/historico/<YYYY-MM>.md` não existe:** criar com header:
```markdown
# Histórico — <YYYY-MM>

```

**Inserir no topo** (logo após o header), em ordem reversa, agrupado por dia:
```markdown
## <YYYY-MM-DD>
- `<sha>` <subject> — @<autor>
  <resumo>
```

### 7. Reportar

- Sucesso: `docs/spec/historico/2026-05.md — 3 commits adicionados`
- Nada novo: `sem commits novos desde <sha>`

---

## Modo: migrate-blueprint

Migra a estrutura `blueprint/` antiga (caseira do Pedro) pra `docs/spec/` + `docs/operacional/`. **1× por projeto**. Idempotente.

### Detecção

- Existe `blueprint/`? Senão: reportar "Nada a migrar." e parar.
- Existe `docs/spec/deploy/project.json` (já migrado)? → reportar "Já migrado" e parar.

### Passos

1. **Backup defensivo** (recomendado):
   ```bash
   git checkout -b backup/pre-spec-migration-$(date +%Y%m%d) 2>/dev/null || echo "branch backup já existe"
   git checkout -    # volta pra branch original
   ```

2. **Garantir `docs/spec/` existe** (executar `/spec init` se ausente, mas sem rodar `npx reversa install` ainda):
   ```bash
   mkdir -p "$SPEC_DIR/deploy" "$SPEC_DIR/chronicles" "$SPEC_DIR/historico" "$REPO_ROOT/docs/operacional"
   ```

3. **Mover JSONs de deploy** (preserva nomes):
   ```bash
   for f in project.json state.json history.json; do
     if [ -f "$REPO_ROOT/blueprint/deploy/$f" ]; then
       git mv "$REPO_ROOT/blueprint/deploy/$f" "$SPEC_DIR/deploy/$f"
     fi
   done
   ```

4. **Mover chronicles** (preserva nomes com prefixos 🟡🟢🔴):
   ```bash
   if [ -d "$REPO_ROOT/blueprint/mudancas" ]; then
     # mv preserva nomes UTF-8 corretamente
     for f in "$REPO_ROOT/blueprint/mudancas/"*; do
       [ -f "$f" ] && git mv "$f" "$SPEC_DIR/chronicles/$(basename "$f")"
     done
   fi
   ```

5. **Mover historico mensal** (se existir):
   ```bash
   if [ -d "$REPO_ROOT/blueprint/historico" ]; then
     for f in "$REPO_ROOT/blueprint/historico/"*.md; do
       [ -f "$f" ] && git mv "$f" "$SPEC_DIR/historico/$(basename "$f")"
     done
   fi
   ```

6. **Mover implementacoes antigas** (se existirem, vão pra chronicles também):
   ```bash
   if [ -d "$REPO_ROOT/blueprint/implementacoes" ]; then
     for f in "$REPO_ROOT/blueprint/implementacoes/"*.md; do
       [ -f "$f" ] && git mv "$f" "$SPEC_DIR/chronicles/$(basename "$f")"
     done
   fi
   ```

7. **Mover artefatos não-spec pra `docs/operacional/`**:
   ```bash
   if [ -d "$REPO_ROOT/blueprint/proposta-trabalho" ]; then
     git mv "$REPO_ROOT/blueprint/proposta-trabalho" "$REPO_ROOT/docs/operacional/proposta-trabalho"
   fi
   if [ -d "$REPO_ROOT/blueprint/sql" ]; then
     git mv "$REPO_ROOT/blueprint/sql" "$REPO_ROOT/docs/operacional/sql"
   fi
   ```

8. **Deletar `blueprint/PROJETO.md`** (substituído pelo spec REVERSA):
   ```bash
   [ -f "$REPO_ROOT/blueprint/PROJETO.md" ] && git rm "$REPO_ROOT/blueprint/PROJETO.md"
   ```

9. **Deletar `blueprint/` se vazio**:
   ```bash
   if [ -d "$REPO_ROOT/blueprint" ] && [ -z "$(ls -A "$REPO_ROOT/blueprint")" ]; then
     rmdir "$REPO_ROOT/blueprint"
   fi
   ```

10. **Atualizar `CLAUDE.md` do projeto** (substituir referências `blueprint/` por `docs/spec/`):
    - Procurar bloco com header `## Deploy e blueprint` → renomear pra `## Deploy e spec`.
    - Substituir `blueprint/PROJETO.md` por `docs/spec/` (mais N referências, o spec não tem 1 MD único).
    - Substituir `blueprint/deploy/` por `docs/spec/deploy/`.
    - Substituir `blueprint/mudancas/` por `docs/spec/chronicles/`.
    - Substituir `blueprint/historico/` por `docs/spec/historico/`.
    - Substituir todas menções a `/blueprint` (skill) por `/spec`.
    - **Não** apagar instrução do sistema 🟡🟢🔴 (preservada).
    - Mostrar diff antes de salvar.

11. **Reportar**:
    ```
    Migração blueprint → docs/spec concluída:

    Movidos:
    - blueprint/deploy/*.json → docs/spec/deploy/
    - blueprint/mudancas/* → docs/spec/chronicles/
    - blueprint/historico/* → docs/spec/historico/
    - blueprint/implementacoes/* → docs/spec/chronicles/ (consolidado)
    - blueprint/proposta-trabalho/ → docs/operacional/
    - blueprint/sql/ → docs/operacional/

    Deletados:
    - blueprint/PROJETO.md (substituído pelo spec REVERSA)
    - blueprint/ (vazio)

    Modificado:
    - CLAUDE.md (paths blueprint → docs/spec, /blueprint → /spec)

    Próximos passos:
    1. Revise CLAUDE.md (git diff CLAUDE.md)
    2. Rode /spec init (se ainda não rodou) pra instalar REVERSA
    3. Rode /spec update pra gerar a primeira versão do spec
    4. Commit: "chore(spec): migrar blueprint pra docs/spec via REVERSA"
    5. Apague ~/.claude/skills/blueprint/ manualmente (skill antiga)
    ```

---

## Pontos de atenção

### Customizações humanas vs auto-gerado

O REVERSA usa manifesto SHA-256 (`.reversa/_config/files-manifest.json`) pra preservar arquivos modificados manualmente. Mas isso só vale pra `npx reversa update` upstream. Quando os agents rodam dentro do `/spec update`, eles podem regenerar arquivos sem checar manifesto.

**Regra**: arquivos "humanos" ficam FORA do que os agents tocam:
- `docs/spec/historico/YYYY-MM.md` (gerado pelo `/spec historico`, não pelos agents).
- `docs/spec/chronicles/*.md` (criados/renomeados pelo `/ship` e `/deploy`).
- `docs/spec/CHANGELOG.md` (prepended pelo `/ship`).
- `docs/spec/deploy/{project,state,history}.json` (manual + `/deploy`).
- `docs/spec/README.md` (manual).

Os agents do REVERSA escrevem nas raízes do `docs/spec/` (`architecture.md`, `sdd/`, `c4-*`, `erd-complete.md`, `gaps.md`, etc.). Estes arquivos podem ser editados depois, mas a próxima `/spec update` PODE sobrescrever. Pra forçar preservação: rodar `npx reversa update` (não `/spec update`).

### Lacuna conhecida: `reversa-chronicler`

O agent `reversa-chronicler` é mencionado no README do upstream mas a pesquisa não localizou ele no pacote `sandeco/reversa@1.2.40`. O pipeline funciona sem ele. O sistema 🟡🟢🔴 dos chronicles continua sendo a única cronologia humana. Verificar a cada `npx reversa update` se o agent surgiu.

### Drift entre código e spec

Mesmo com `/deploy ship` invocando `/spec update` automático, alguma operação manual pode deixar o spec desatualizado:
- `git pull` que traz commits de outra máquina sem rodar deploy.
- Edição rápida sem `/ship` nem `/deploy`.

Solução: `/spec status` detecta drift via comparação de SHA. Quando detectado, rodar `/spec update` manual.

---

## Regras

- ❌ **Nunca** edite código fora de `docs/spec/`, `docs/operacional/`, `.reversa/config.toml`, `.gitignore` (no `init`), e `CLAUDE.md` (no `migrate-blueprint`).
- ❌ **Nunca** faça commit ou amend — só edita arquivos. Pedro/contratado decide quando commitar.
- ❌ **Nunca** apague `blueprint/` antes de mover tudo no `migrate-blueprint`.
- ❌ **Nunca** rode `/spec update` em paralelo (uma instância de cada vez — manifesto fica inconsistente).
- ❌ **Nunca** loga conteúdo de arquivos no console — só nomes e contagens.
- ✅ Seja **silencioso** quando não há nada pra fazer.
- ✅ **Idempotente**: rodar `init` 2× sem mudança = sem efeito. Rodar `migrate-blueprint` 2× = "já migrado".
- ✅ Em modo `update`, captura output dos agents pra reportar resumo (não scroll de log).
- ✅ Quando chamada pelo `/deploy ship` Passo 9: comporta-se como `/spec update` avulso (foreground, bloqueia até concluir).

---

## Anti-padrões

- ❌ "Vou aproveitar e atualizar `architecture.md` à mão." — Não. Use o pipeline. Edição manual será sobrescrita.
- ❌ "Vou rodar todos os agents em paralelo pra ser mais rápido." — Não. Cada agent depende do anterior (state.json + manifesto).
- ❌ "O `/spec update` falhou, vou rodar `npx reversa install` pra resetar." — Não. Reinstall apaga estado e força reaprendizado. Investigue o erro do agent específico.
- ❌ "`/spec migrate-blueprint` parece intrusivo, vou pular e mover na mão." — Não. A skill garante atomicidade (tudo ou nada) e idempotência. Mover na mão deixa estado inconsistente.

---

## Referências

- `references/project-schema.md` — schema do `docs/spec/deploy/project.json` (idêntico ao da `/deploy`).
- `references/chronicle-frontmatter.md` — schema do YAML frontmatter dos chronicles 🟡🟢🔴.
- `references/agents-roles.md` — papel de cada agent do pipeline.
- `https://github.com/sandeco/reversa` — upstream do framework.
