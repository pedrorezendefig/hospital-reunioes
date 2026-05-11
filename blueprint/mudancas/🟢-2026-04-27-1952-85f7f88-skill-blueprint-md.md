# Skill `/blueprint` global (substitui `/blueprint-sync`, remove HTML)

## Contexto

Hoje o `blueprint/` de cada projeto tem 7+ docs em MD/HTML com responsabilidades sobrepostas:
`README.md`, `DEPLOY.md`, `dashboard.html` (128K, regerado a cada `/deploy ship`),
`deploy/{coolify,env-vars,secrets,gates}.md`. O HTML é cosmético — informação está nos JSONs.

Pedro quer:
1. **Eliminar o HTML** — tudo em MD.
2. **Um arquivo único `PROJETO.md` para leigo** — estado de prod, variáveis OK, conexões, alertas, próximas ações, planos, links pro histórico.
3. **Pasta `implementacoes/`** dentro do blueprint, gerada automaticamente — 1 MD por `/deploy ship` (sucesso ou falha).
4. **Skill `/blueprint` global** — funciona em qualquer projeto, cria/mantém estrutura, atualiza ao fim de cada deploy.
5. **`CLAUDE.md` global** alinhado: revoga proibição de `implementacoes/` (passa a ser usado dentro de `blueprint/`).

Resultado pretendido: leigo abre `blueprint/PROJETO.md`, entende em 2 minutos o que é o projeto, qual o estado de prod, o que monitorar.

---

## Estado-alvo

### Estrutura do `blueprint/` de qualquer projeto

```
blueprint/
├── PROJETO.md                              ← gerado por /blueprint update (idempotente)
├── deploy/
│   ├── project.json                        ← manual (ampliado: description, stack[], integrations[], next_actions[])
│   ├── state.json                          ← auto, /deploy ship escreve
│   └── history.json                        ← auto, /deploy ship escreve
├── implementacoes/
│   └── 2026-04-27-1527-d36f1de-healthy.md  ← auto, /deploy ship escreve pós-commit
└── historico/
    └── 2026-04.md                          ← gerado por /blueprint historico (manual)

planos/                                     ← continua na raiz do projeto, fora do blueprint
```

### Skills globais (em `~/.claude/skills/`)

| Skill | Estado |
|---|---|
| `blueprint/SKILL.md` | **Nova** — substitui `blueprint-sync/` |
| `blueprint-sync/SKILL.md` | **Apagada** após validar que `/blueprint historico` produz o mesmo output |
| `deploy/SKILL.md` | **Modificada** — remove geração de HTML do Passo 9.3, adiciona update inline + criação de implementação |
| `deploy/dashboard-template.html` | **Apagado** |

### Comandos da nova skill `/blueprint`

| Comando | Faz |
|---|---|
| `/blueprint` (default) | Se não há `blueprint/`: oferece init. Se há: imprime resumo curto + sugere `update`. |
| `/blueprint init` | Cria `blueprint/` em projeto novo (sem `deploy/project.json`: cria stub e direciona pra `/deploy setup`). |
| `/blueprint init --migrate` | Migração honesta: cria `PROJETO.md` a partir de `project.json` + estado, **não** apaga MDs antigos. Pedro deleta manualmente após revisar via `git diff`. |
| `/blueprint update` | Regenera `PROJETO.md` (idempotente). Se houver novo registro em `history.json` desde a última, **não** cria implementação aqui — quem cria é o ship. |
| `/blueprint historico` | Lê `git log` do mês corrente, regenera `historico/YYYY-MM.md`. Algoritmo idêntico ao `/blueprint-sync` atual. |
| `/blueprint status` | Read-only; imprime resumo do `PROJETO.md` no terminal. |

---

## Detalhamento

### 1. Anatomia do `PROJETO.md` — campos **estáveis** apenas (idempotência)

Fontes:
- `deploy/project.json` (manual, ampliado)
- `deploy/state.json` (auto)
- `deploy/history.json` (auto)
- `git log` (último mês)
- Listagem de `planos/*.md` da raiz do projeto

Regras de idempotência (críticas — `/blueprint update` rodado 2× sem mudança = `git diff` vazio):
- **Não embute** `latency_ms`, `state.updated_at` em segundos, `build_duration_seconds`.
- **Embute** SHA + data (granularidade dia, ex: "27/04") do último deploy, status (healthy/failed), serviços e domínios.
- Timestamp de geração no rodapé, granularidade **dia**.

Seções (ordem fixa):

```markdown
# {project.name}

> Atualizado em {YYYY-MM-DD} — Regere com `/blueprint update`

## O que é
{project.description}                 ← prosa, manual em project.json

## Estado de produção
| Serviço | URL | Status | Último deploy |
| backend | api.mala-ia.cloud | 🟢 healthy | d36f1de · 27/04 |
| frontend | app.mala-ia.cloud | 🟢 healthy | d36f1de · 27/04 |
| supabase | studio.mala-ia.cloud | 🟢 healthy | d36f1de · 27/04 |

(coluna "Última checagem" deliberadamente ausente — varia a cada update; quebra idempotência)

## Variáveis críticas
Backend (prod):
- ✅ ENVIRONMENT=production
- ✅ DEBUG=false
- ✅ OPENAI_API_KEY (presente)
- ❌ FOO_TOKEN (faltando!)            ← se project.json marca obrigatória e state.json não confirma

Frontend (build):
- ✅ NEXT_PUBLIC_SUPABASE_URL=https://...

## Integrações externas
- 🟢 OpenAI (configurada)
- 🟢 ClickSign (configurada, webhook /api/webhooks/clicksign)
- 🟢 Resend (configurada)

(declarativo — variável presente = configurado; sem probe ativo)

## Próximas ações & alertas
{project.next_actions[] + state.next_actions[]}

## Stack
- Backend: {project.stack.backend}
- Frontend: {project.stack.frontend}
- Banco: {project.stack.database}
- Infra: {project.stack.infra}

## Coolify
- VPS: {project.coolify.vps_ip} ({project.coolify.vps_label})
- Painel: {project.coolify.url}
- UUIDs: project={...}, server={...}, github_app={...}, services=[…]

## Histórico recente
**Últimos 5 deploys** (de history.json — sem campos voláteis tipo build_duration_seconds):
- 27/04 d36f1de — feat: lote de melhorias — healthy → [implementacoes/2026-04-27-1527-d36f1de-healthy.md]
- ...

**Commits do mês**: ver `historico/2026-04.md`

## Como mexer
- Deploy: `/deploy` | Status: `/deploy status` | Reverter: `/deploy rollback`
- Atualizar este doc: `/blueprint update`
- Atualizar histórico mensal: `/blueprint historico`

## Planos abertos
- planos/plano-26-04-23-1800h-foo.md — Foo
- planos/plano-26-04-25-1500h-bar.md — Bar
```

### 2. Trigger de implementação (cravado)

| Passo do `/deploy ship` | Gera `implementacoes/...md`? |
|---|---|
| Pre-flight (gates) falha **antes** do commit | **Não** — não houve tentativa real |
| Commit feito → push → build falha | **Sim** — `result: "build-failed"` |
| Build OK → health check falha → rollback automático | **Sim** — `result: "rolled-back"` |
| Migrations falham | **Sim** — `result: "migration-failed"` |
| Tudo OK | **Sim** — `result: "healthy"` |
| `/deploy rollback` manual | **Sim** — `result: "rollback-manual"` |

### 3. Nome de arquivo de implementação

Formato: `YYYY-MM-DD-HHMM-<sha7>-<resultado>.md`

Exemplos:
- `2026-04-27-1527-d36f1de-healthy.md`
- `2026-04-27-1706-c35c56a-rolled-back.md`

Conteúdo (campos estáveis):
- Cabeçalho: data, SHA, mensagem do commit, resultado.
- Serviços tocados (de `state.last_run.services_touched[]`).
- Migrations aplicadas (se houver).
- Variáveis adicionadas/removidas (diff de `project.json` vs anterior).
- Notas humanas (se Pedro adicionar manualmente depois).

### 4. Modificação no `/deploy` — update **inline**, sem recursão de Skill

Decisão arquitetural (do agente Plan, ponto bloqueante): `/deploy ship` **não** chama `/blueprint update` via Skill tool. Em vez disso:

- O Passo 9.3 do `~/.claude/skills/deploy/SKILL.md` é reescrito para conter o procedimento inline (regenerar PROJETO.md a partir dos JSONs).
- O Passo 9.3 do SKILL.md referencia explicitamente: "Procedimento documentado em `~/.claude/skills/blueprint/SKILL.md` seção `update` — fonte única de verdade do algoritmo".
- A skill `/blueprint update` lê o **mesmo** arquivo de seção quando chamada avulsa (DRY via referência, não via execução de skill aninhada).

Reescrita do Passo 9.3 (resumo):
1. Mantém: escrever `state.json` e `history.json` (essencial).
2. Remove: bloco Python que carrega `dashboard-template.html`, faz `.replace()` com placeholders, escreve `dashboard.html`. Apaga arquivo se existir.
3. Adiciona: bloco que regenera `PROJETO.md` a partir de `project.json + state.json + history.json`.
4. Adiciona: bloco que cria `implementacoes/<timestamp>-<sha>-<resultado>.md` com base em `state.last_run`.
5. Mantém: gate anti-vazamento de secrets (regex) — agora aplicado ao MD em vez do HTML.

Para falhas pós-commit (Passos 5-8), adicionar invocação curta do procedimento de implementação (escreve só o MD com `result: "..."` apropriado, sem mexer em PROJETO.md — esse só atualiza no 9.3 com sucesso ou no rollback).

### 5. Auto-extração **honesta** na migração

Decisão (do agente Plan): não tentar parsear mermaid, tabelas markdown ou seções livres do `README.md`. Em vez disso:

| Campo de `project.json` ampliado | Origem na migração |
|---|---|
| `description` | Primeiro parágrafo do `README.md` (prosa preservada literalmente, sem reescrita) |
| `stack` | Vazio inicial — Pedro preenche manualmente após revisar |
| `integrations[]` | Vazio inicial — Pedro preenche |
| `next_actions[]` | Vazio inicial |
| `coolify.vps_label`, `coolify.url` | Já existem no project.json atual — copiados |

Ou seja: a migração é segura mesmo sem revisão humana — não inventa dados. Pedro completa nos campos vazios depois, com calma.

### 6. Mudança no `~/.claude/CLAUDE.md` global

Remover seção atual:
```markdown
## Registro de implementações
Não manter pasta `implementacoes/` nem logs por tarefa. ...
```

Substituir por:
```markdown
## Blueprint do projeto

Projetos com deploy via `/deploy` mantêm pasta `blueprint/` na raiz com:
- `PROJETO.md` — visão consolidada para leigo (gerada por `/blueprint update`)
- `deploy/{project,state,history}.json` — config + estado de produção
- `implementacoes/` — 1 MD por `/deploy ship` (sucesso ou falha), gerado automaticamente
- `historico/` — changelog mensal de commits, regenerado por `/blueprint historico`

Planos seguem em `planos/` na raiz (fora do blueprint), conforme convenção do projeto.

Skills:
- `/blueprint` para inicializar/atualizar/inspecionar
- `/deploy` invoca o procedimento de `/blueprint update` automaticamente ao final do ship
```

Atualizar também o `CLAUDE.md` do projeto Hospital removendo a regra anti-`implementacoes/` (a regra global passa a ser positiva).

---

## Sequenciamento de execução (rollback fácil em cada passo)

| # | Passo | Rollback |
|---|---|---|
| 1 | Criar `~/.claude/skills/blueprint/SKILL.md` SEM tocar em `/deploy` nem nos projetos | `rm -rf ~/.claude/skills/blueprint/` |
| 2 | Testar `/blueprint historico` no Hospital — diff direto com output do `/blueprint-sync` (devem ser idênticos) | descartar diff em `blueprint/historico/` |
| 3 | Rodar `/blueprint init --migrate` no Hospital (gera `PROJETO.md`, **não** apaga MDs antigos) | `rm blueprint/PROJETO.md` |
| 4 | Rodar `/blueprint init --migrate` no SiteHospital | idem |
| 5 | Pedro revisa os 2 `PROJETO.md` via `git diff`. Preenche manualmente os campos `stack`, `integrations`, `next_actions` em `project.json` onde fazia sentido | manual |
| 6 | Modificar `~/.claude/skills/deploy/SKILL.md`: reescrever Passo 9.3 (update inline), adicionar criação de implementação, gate idempotente vs `dashboard.html` (apaga se existir) | `git checkout` em `~/.claude/skills/deploy/SKILL.md` |
| 7 | Checkpoint: rodar `/deploy ship` em **SiteHospital** (1 service, mais simples). Verificar: `PROJETO.md` regenerado idêntico, 1 implementação criada, `dashboard.html` ausente | `git checkout` no SiteHospital + reverter SKILL.md |
| 8 | Checkpoint: rodar `/deploy ship` em **Hospital** (3 services, com migrations). Verificar idem | idem |
| 9 | Apagar MDs antigos em ambos: `README.md`, `DEPLOY.md`, `DEPLOY.md.legacy`, `deploy/{coolify,env-vars,secrets,gates}.md`, `dashboard.html` | `git revert` |
| 10 | Apagar `~/.claude/skills/blueprint-sync/` e `~/.claude/skills/deploy/dashboard-template.html` | `git restore` |
| 11 | Atualizar `~/.claude/CLAUDE.md` global e `Hospital/CLAUDE.md` (remover regra anti-`implementacoes/`) | `git checkout` |

**Ordem crítica**: passos 7 e 8 são gates. Se um falhar, parar antes do 9. Não apagar MDs antigos antes de comprovar que `/deploy ship` funciona com a nova skill.

---

## Critérios de verificação E2E (mínimos antes de shippar)

1. `/blueprint historico` no Hospital produz output idêntico ao `/blueprint-sync` (diff direto). [Passo 2]
2. `/blueprint update` rodado 2× sem mudança real = `git diff` vazio em `PROJETO.md`. [Passos 3-4]
3. `/deploy ship` no SiteHospital com 1 commit trivial gera: `PROJETO.md` atualizado, 1 implementação nova, sem `dashboard.html`. [Passo 7]
4. `/deploy ship` no Hospital com 1 commit em backend gera: `PROJETO.md` atualizado, implementação inclui só `backend` em `services_touched`, sem `dashboard.html`. [Passo 8]
5. **Forçar falha pre-flight**: rodar `/deploy ship` com lint quebrado → não gera implementação (falha pré-commit).
6. **Forçar falha pós-commit**: simular health 503 → gera implementação com `result: "rolled-back"`.
7. `/deploy status` em ambos retorna sem erro.
8. `/deploy rollback` em SiteHospital roda e gera implementação com `result: "rollback-manual"`.
9. `find /Users/pedrorezende/PedroDev/{Hospital,SiteHospital}/blueprint -name "*.html" -o -name "DEPLOY.md*" -o -name "README.md"` = vazio depois do passo 9.
10. `git log --oneline` mostra que cada passo gerou commit nominal e nada inesperado.

Sem 1-3 cumpridos, não shippa.

---

## Arquivos críticos

| Caminho | Ação |
|---|---|
| `~/.claude/skills/blueprint/SKILL.md` | Criar |
| `~/.claude/skills/blueprint-sync/SKILL.md` | Apagar (passo 10) |
| `~/.claude/skills/deploy/SKILL.md` | Editar (passo 6) — reescrever Passo 9.3 |
| `~/.claude/skills/deploy/dashboard-template.html` | Apagar (passo 10) |
| `~/.claude/skills/deploy/references/project-schema.md` | Editar — adicionar campos `description`, `stack`, `integrations`, `next_actions` |
| `~/.claude/CLAUDE.md` | Editar (passo 11) |
| `/Users/pedrorezende/PedroDev/Hospital/CLAUDE.md` | Editar (passo 11) — remover regra anti-`implementacoes/` |
| `/Users/pedrorezende/PedroDev/Hospital/blueprint/` | Migrar (passos 3, 9) |
| `/Users/pedrorezende/PedroDev/Hospital/blueprint/deploy/project.json` | Ampliar com campos novos |
| `/Users/pedrorezende/PedroDev/SiteHospital/blueprint/` | Migrar (passos 4, 9) |
| `/Users/pedrorezende/PedroDev/SiteHospital/blueprint/deploy/project.json` | Ampliar |
| `/Users/pedrorezende/PedroDev/SiteHospital/CLAUDE.md` | **Criar** (não existe hoje) — convenções pt-BR + uso de `/blueprint` e `/deploy` |

---

## Referências reusáveis (não reinventar)

- **Algoritmo do `historico/YYYY-MM.md`**: copiar verbatim do `~/.claude/skills/blueprint-sync/SKILL.md` (linhas do pseudo-bash). Não "melhorar".
- **Gate anti-vazamento de secrets**: copiar a regex e o scan recursivo do Passo 9.3 atual de `~/.claude/skills/deploy/SKILL.md` (linhas ~424-438) — passa a se aplicar ao MD em vez do HTML.
- **Detecção de projeto**: `/blueprint init` usa o mesmo padrão de discovery que `/deploy` (procura `blueprint/deploy/project.json`; se ausente, oferece `/deploy setup`).
- **Estrutura de project.json v2**: já documentada em `~/.claude/skills/deploy/references/project-schema.md`. Ampliar (não substituir) com novos campos opcionais.

---

## Convenção de plano

Após `ExitPlanMode` aprovado, copiar este plano para `/Users/pedrorezende/PedroDev/Hospital/planos/plano-26-04-27-1730h-skill-blueprint-md.md` (regra do projeto Hospital — planos versionados em `planos/` com timestamp). O arquivo aqui em `~/.claude/plans/` é só o registro do plan mode.

---

## Deploy `85f7f88` — 🟢 healthy

- **Data**: 2026-04-27 19:52
- **SHA**: `85f7f88`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Migra blueprint para PROJETO.md (skill /blueprint global)

### Serviços tocados

- backend
- frontend

### Notas

Primeiro deploy registrado pela nova skill /blueprint integrada ao /deploy ship. Build sem mudanças de código (apenas blueprint/). Backend buildou em 2m03s, frontend em 4m09s. Health checks pós-deploy: api.mala-ia.cloud/api/health 200 ({status:healthy}, 79ms), app.mala-ia.cloud 200 (137ms).

---
_Gerado automaticamente pelo `/deploy ship` (Passo 9.4)._
