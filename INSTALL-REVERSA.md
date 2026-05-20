# Instalar REVERSA — passo a passo

Este documento cobre a instalação do framework REVERSA no projeto Hospital. Roda **uma única vez**, e cria `.reversa/`, `.agents/skills/reversa-*` na raiz (tudo no `.gitignore`).

Tempo estimado: **5-10 minutos** (depende do tempo de download).

## Pré-requisitos

- Node 18+ instalado (`node --version` >= 18). Você já tem v24.14.
- Você está em `/Users/pedrorezende/PedroDev/Hospital` (ou onde quer instalar).
- A branch `spec-and-workflow-migration` (ou main após merge) está checked out.

## Passo 1 — Rodar o install interativo

```bash
cd /Users/pedrorezende/PedroDev/Hospital
npx reversa install
```

O install vai abrir um wizard com 3-5 perguntas. **Responda assim**:

### 1.1 "Engines Harness to support"

Use **espaço** pra marcar/desmarcar, **Enter** pra confirmar. Marque pelo menos:

- ☑ Claude Code (recommended)

Marque também se vocês usam:
- ☐ Codex
- ☐ Cursor
- ☐ Gemini CLI

Recomendado: só Claude Code, pra manter simples.

### 1.2 "Agents teams to install"

- ☑ Reversa Agents Core (já vem marcado, obrigatório)
- ☑ Migration Agents (opcional, útil pra migração futura de stack)
- ☑ Code Forward Agents (precisa pra Code New Project)
- ☐ Code New Project Agents
- ☑ Documentation Agents (HTML mini-site) — gera doc visual em `.reversa/documentation/`
- ☐ Pricing and Size Agents (não usamos)
- ☐ Translators N8N→Specs→Python (não usamos)

Recomendado mínimo: **Reversa Agents Core + Documentation Agents**. Resto opcional.

### 1.3 Outras perguntas

Aceite o default em todas (Enter).

### 1.4 Aguarde a instalação

Vai baixar agents do npm registry, criar `.reversa/`, `.agents/skills/`, e adicionar entradas em `.claude/skills/` (com a sub-skill `reversa-*` específica).

Output esperado no final:
```
✓ REVERSA installed
✓ Agents: <N> teams installed
✓ Engines: Claude Code
✓ State initialized: .reversa/state.json
```

## Passo 2 — Configurar `output.folder` pra `docs/spec/`

O REVERSA por default salva em `_reversa_sdd/`. Você quer em `docs/spec/`.

```bash
# Edite manualmente ou via sed
sed -i.bak 's|folder = "_reversa_sdd"|folder = "docs/spec"|' .reversa/config.toml
rm .reversa/config.toml.bak

# Confere
grep -n "folder" .reversa/config.toml
# Deve mostrar: folder = "docs/spec"
```

## Passo 3 — Conferir que `.gitignore` está OK

O `.gitignore` já tem `.reversa/`, `.agents/`, `_reversa_sdd/` ignorados. Confere:

```bash
grep -E "\.reversa|\.agents|_reversa_sdd" .gitignore
```

## Passo 4 — Rodar a primeira geração

Dentro do Claude Code, na pasta Hospital:

```
/spec update
```

Ou, manualmente via npx (mais demorado, sem agents interativos):

```bash
npx reversa update
```

Isso vai disparar o pipeline de agents (Scout, Architect, Writer, Reviewer, Visor, Data Master, Design System, Chronicler se houver). Cada agent roda um por um e gera arquivos em `docs/spec/`.

Tempo: **~10-15 minutos** primeira vez (ele lê todo o código backend + frontend + Supabase).

Output esperado:
```
docs/spec/
├── architecture.md          (Architect)
├── inventory.md             (Scout)
├── domain.md                (Writer)
├── data-dictionary.md       (Writer)
├── erd-complete.md          (Data Master)
├── c4-context.md            (Architect)
├── c4-containers.md         (Architect)
├── c4-components.md         (Architect)
├── state-machines.md        (Writer)
├── permissions.md           (Writer)
├── gaps.md                  (Reviewer)
├── confidence-report.md     (Reviewer)
├── sdd/<unit>/...           (Writer, por unidade do sistema)
├── traceability/
│   ├── code-spec-matrix.md
│   └── spec-impact-matrix.md
├── ui/                      (Visor)
├── database/                (Data Master)
└── design-system/           (Design System)
```

Pode ter algum agent que não existe na versão atual (ex: `reversa-chronicler` mencionado no README mas pesquisado sem sucesso). Tudo bem, o pipeline pula.

## Passo 5 — Validar e commitar

```bash
ls docs/spec/
git status docs/spec/
git add docs/spec/
git commit -m "docs(spec): primeira geração via REVERSA"
git push
```

## Tratamento de erro

### "REVERSA não detectou stack"

Se o REVERSA não conseguir identificar a stack (FastAPI + Next.js + Supabase), confere se você está na raiz do repo (onde tem `hospital-reunioes/backend/`, `hospital-reunioes/frontend/`, `hospital-reunioes/supabase/`).

### "Agent X falhou"

Pipeline para no agent que falha. Olha o log, corrige (geralmente é env var ou path) e roda `/spec update` de novo. O estado é preservado em `.reversa/state.json`.

### "Quero recomeçar do zero"

```bash
rm -rf .reversa .agents
# E rode o install de novo do Passo 1
```

## Checklist final

- [ ] `npx reversa install` rodou sem erro
- [ ] `.reversa/config.toml` tem `folder = "docs/spec"`
- [ ] `.gitignore` ignora `.reversa/`, `.agents/`, `_reversa_sdd/`
- [ ] `/spec update` (ou `npx reversa update`) rodou pela primeira vez
- [ ] `docs/spec/` tem arquivos gerados (architecture, c4-*, erd, sdd/)
- [ ] Commit `docs(spec): primeira geração via REVERSA` feito

## Passo 6 — (opcional) Apagar a skill `/blueprint` global

A skill `/blueprint` antiga continua em `~/.claude/skills/blueprint/` (não foi apagada porque pode afetar outros projetos seus). Quando você tiver certeza que nenhum outro projeto seu usa, pode apagar:

```bash
# Backup primeiro (segurança)
tar czf /tmp/backup-blueprint-skill-$(date +%Y%m%d).tar.gz \
  -C ~/.claude/skills blueprint
ls -la /tmp/backup-blueprint-skill-*.tar.gz

# Apagar
rm -rf ~/.claude/skills/blueprint

# Confere
ls ~/.claude/skills/ | grep -i blueprint
# Não deve retornar nada
```

## Passo 7 — (opcional) Atualizar `~/.claude/CLAUDE.md` global

Seu CLAUDE.md global (`~/.claude/CLAUDE.md`) tem uma seção "Blueprint do projeto" com instruções pra `blueprint/`. Quando os outros projetos seus migrarem pra `docs/spec/` (ou aceitar que essa skill é só legacy), atualize a seção:

```bash
# Abre no editor
$EDITOR ~/.claude/CLAUDE.md
```

Procure por:
- `## Blueprint do projeto` → renomeia pra `## Spec do projeto`
- `/blueprint` → `/spec` (referências de comandos)
- `blueprint/` paths → `docs/spec/` (paths de exemplo)

Hospital tem o CLAUDE.md já atualizado com esse padrão. Pode copiar a estrutura de lá.

Quando terminar (passos 1-7), **delete este arquivo** (`rm INSTALL-REVERSA.md`) — ele tem propósito one-time só.

---

## Por que isso não foi automatizado

Tentei rodar `npx reversa install` em modo não-interativo (com `printf '\n\n\n...' | npx reversa install`) mas o wizard usa `inquirer` com checkboxes que precisam de `<space>` pra marcar/desmarcar opções. Não é possível scriptar sem ferramenta tipo `expect`. Por isso o passo precisa ser feito por você manualmente, com calma.

Se quiser tentar não-interativo numa máquina futura, ferramenta `expect` (`brew install expect`) ou `bash` com tty manual pode automatizar. Mas pra uso pontual, fazer manual é mais simples.
