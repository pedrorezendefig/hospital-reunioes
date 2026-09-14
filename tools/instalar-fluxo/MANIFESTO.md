# Manifesto: o que vai, o que muda, o que fica

Caminhos relativos à raiz de **ORIGEM** (este repositório) e de **DESTINO** (o projeto que recebe o fluxo). Quatro ações:

- **copiar**: byte a byte, sem editar.
- **adaptar**: copiar e depois trocar o que depende do Hospital (nome, caminhos, stack, plataforma). A nota diz o quê.
- **gerar**: não copiar; escrever do zero para o DESTINO, usando o arquivo da ORIGEM como modelo de formato.
- **excluir**: não vai.

O agente lê esta tabela na Fase 3 do `ROTEIRO.md` e executa linha a linha. Um arquivo que já existe no DESTINO nunca é sobrescrito sem mostrar o diff e perguntar.

## Raiz

| Caminho | Ação | Nota de adaptação |
|---|---|---|
| `CLAUDE.md` | adaptar | Título do projeto; `/ask-pedro` vira `/ask-<nome>`; caminho do app (`hospital-reunioes/`) vira o do DESTINO; remover as linhas de `docs/manual/`, `docs/comunicacao/` e Vercel; manter as seções Idioma, Tipografia, Fluxo de trabalho, Agent skills, Desenvolvimento paralelo, Proibido criar, Docs vivos. Se o DESTINO já tem `CLAUDE.md`, fundir: as regras dele ficam, as do fluxo entram como seções novas. |
| `README.md` | gerar | Mapa de pastas no formato da ORIGEM (tabela "Pasta, O que é, Por que existe, O que tem, Quando abrir" e bloco `cobertura`), com as pastas do DESTINO. Se já existe README, acrescentar a seção "Mapa do repositório" no fim. |
| `CONTEXT.md` | gerar | Fase 5 do roteiro: glossário rascunho a partir do código do DESTINO, no formato de `.claude/skills/domain-modeling/CONTEXT-FORMAT.md`. |
| `CONTEXT-MAP.md` | excluir | Só existe porque o Hospital tem dois contextos. O DESTINO começa com um. |
| `skills-lock.json` | copiar | Proveniência das skills importadas do Matt Pocock. Não instala nada. |
| `.gitignore` | adaptar | Acrescentar as linhas do fluxo: `.claude/worktrees/`, `local/`, `tokens/.env`, `tools/workflow-dashboard/__pycache__/`. |

## `.claude/skills/`

Toda skill vai com a pasta inteira (`SKILL.md`, `references/`, `scripts/`, arquivos irmãos).

| Skill | Ação | Nota de adaptação |
|---|---|---|
| `ask-pedro` | adaptar | Renomear a pasta e o `name:` para `ask-<nome>`. Remover a linha de `/divulgar`. Em "Máquina nova", trocar 1Password e Coolify pelo cofre e pela plataforma do DESTINO. Trocar "Pedro" pelo nome de quem instala. |
| `grill-with-docs`, `domain-modeling`, `to-prd`, `to-issues`, `pegar-issue`, `tdd`, `triage`, `wayfinder`, `onda`, `montar-ondas`, `passagem`, `research`, `prototype`, `resolver-conflitos`, `diagnose`, `codebase-design`, `improve-codebase-architecture` | copiar | Neutras. Onde citam "Hospital Reuniões" no cabeçalho, trocar pelo nome do DESTINO (é texto de apresentação, não lógica). `domain-modeling/ADR-FORMAT.md` cita `docs/agents/domain.md`, que também vai. |
| `ship` | adaptar | Caminho do arquivo de versão (Passo "Ler versão atual" e o bump); Passo 8.5 (sync `APP_VERSION` no Coolify) vira o equivalente da plataforma do DESTINO ou sai; Passo de migrations (`hospital-reunioes/supabase/migrations/**`) vira o caminho de migrations do DESTINO ou sai; comandos dos 3 gates (lint, testes, build) viram os do DESTINO; "Default do time Hospital: sem Discord" fica como está. Os invariantes não mudam: 3 gates, merge só com OK humano citando o PR#, Passo 10.5 cria issue `ready-for-human`, chama `/deploy` no fim. |
| `deploy` | gerar | Reescrever para a plataforma do DESTINO mantendo: os modos `ship`, `status`, `rollback`, `setup`; leitura de `docs/spec/deploy/project.json`; escrita de `state.json` e `history.json` no mesmo esquema; `scripts/changelog_prepend.py` (copiar, e corrigir o título para não sair com travessão); chamada do `/snapshot` no fim. Sem plataforma ainda: versão stub que só registra versão, SHA e data no `history.json` e marca `result: "not-deployed"`. Ver Fase 4 do roteiro. |
| `snapshot` | gerar | Reescrever `scripts/snapshot.py` para a stack do DESTINO mantendo os **nomes e o formato** dos arquivos de saída em `docs/spec/snapshots/` (`ESTRUTURA.md`, `ROTAS.md`, `ENTIDADES.md`, `SCHEMA.md`, `MIGRATIONS.md`, `INTEGRACOES.md`, `FLUXOGRAMAS.md`). A aba Mapa lê esses arquivos por `tools/workflow-dashboard/areas.py` e `diagramas.py`: o formato que esses parsers esperam é o contrato. Diagramas no subset Mermaid da ADR 0025. Mínimo garantido em qualquer stack: `ESTRUTURA.md` (árvore) e `INTEGRACOES.md` (chaves de env). |
| `atualizar-app` | gerar | Como subir o app local no DESTINO (docker compose, `pnpm dev`, `uv run`, o que for), com `preview` antes de aplicar. Sem app local, sai e o `/ask-<nome>` não cita. |
| `setup-maquina` | adaptar | `scripts/diagnostico.sh` confere binários, `gh`, tokens e plataforma do DESTINO; `references/chaves.md` lista as chaves do DESTINO e de onde vêm (o cofre que a pessoa usar, sem citar 1Password se ela não usa). `--mapa` continua lendo o `README.md` da raiz. |
| `divulgar` | excluir | Entrega de vídeo e página para o diretor do hospital. Não é framework. |

## `docs/`

| Caminho | Ação | Nota de adaptação |
|---|---|---|
| `docs/agents/issue-tracker.md` | copiar | Neutro (claim, worktrees, bloqueio nativo, wayfinding). |
| `docs/agents/triage-labels.md` | adaptar | As labels `area:*` viram as áreas do DESTINO (decididas na entrevista). O resto é igual. |
| `docs/agents/domain.md` | adaptar | Uma citação ao Hospital no cabeçalho. Formato de ADR e de CONTEXT ficam. |
| `docs/adr/README.md` | gerar | Índice vazio, no formato da ORIGEM, com uma seção "Fluxo de trabalho" contendo a ADR 0001. |
| `docs/adr/0001-*.md` | gerar | Fase 5: a ADR da instalação (o que foi decidido, de onde veio, SHA da ORIGEM). |
| `docs/adr/00NN-*.md` da ORIGEM | excluir | São decisões do Hospital. As que explicam o fluxo (0020 ciclo de vida da issue e higiene, 0013 travessão, 0022 onda, 0025 diagramas, 0027 wayfinder, 0028 bloqueio nativo, 0043 skills locais, 0044 layout) viram um parágrafo de resumo cada dentro da ADR 0001 do DESTINO, com link para o arquivo da ORIGEM no GitHub. |
| `docs/spec/VERSIONING.md` | adaptar | Fonte da versão e nome do projeto. |
| `docs/spec/CHANGELOG.md` | gerar | Só o cabeçalho, no formato da ORIGEM, sem entradas. |
| `docs/spec/deploy/project.json` | gerar | Mesmo esquema (`schema_version`, `project`, `git`, plataforma, `services` com `health_check`), valores do DESTINO. Campos da plataforma que não existem ficam `null`. |
| `docs/spec/deploy/state.json` | gerar | Mesmo esquema, `services` com `status: "unknown"` até o primeiro `/deploy status`. |
| `docs/spec/deploy/history.json` | gerar | `{"schema_version": "1.0", "deploys": []}`. |
| `docs/spec/snapshots/*.md` | gerar | Saída do `/snapshot` adaptado, rodado uma vez na Fase 5. |
| `docs/onboarding/dev.md` | adaptar | Nome do projeto, `/ask-<nome>`, cenários A a D ficam. |
| `docs/onboarding/claude-setup.md` | adaptar | Pré-requisitos e acessos externos da plataforma do DESTINO. Seção do Coolify sai se não for Coolify. |
| `docs/manual/`, `docs/comunicacao/`, `docs/pops/` | excluir | Conteúdo do Hospital. |

## `.github/`

| Caminho | Ação | Nota de adaptação |
|---|---|---|
| `.github/workflows/lint-adr.yml` | copiar | Junto com `tools/lint_adr.py`. |
| `.github/workflows/higiene-issues.yml` | copiar | Neutro: limpa labels de estado no fechamento, fecha PRD pai, sinaliza `revisor-comentou`. |
| `.github/workflows/ci.yml` | gerar | Um job por gate do DESTINO (lint, testes, build), mais o passo "Lint travessão" apontado para a pasta de templates que o usuário final lê no DESTINO. Se o DESTINO já tem CI, acrescentar só o passo do travessão. Se o DESTINO não tem templates lidos por usuário, o passo cobre `docs/` e o `README.md`. |
| `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` | copiar | Se existirem na ORIGEM. Se o DESTINO já tem, perguntar. |
| Regra ESLint de travessão (`hospital-reunioes/frontend/eslint.config.mjs`, bloco `no-restricted-syntax` com `TRAVESSAO`) | adaptar | Só se o DESTINO usa ESLint. Portar o bloco para o config dele. |

## `tools/`

| Caminho | Ação | Nota de adaptação |
|---|---|---|
| `tools/lint_adr.py` | copiar | |
| `tools/workflow-dashboard/serve.py`, `collect.py`, `plano.py`, `areas.py`, `diagramas.py`, `static/app.js`, `static/ui.js`, `static/diagramas.js`, `static/vendor/` | copiar | O coração do painel. Não editar. `collect.py` usa o `gh` do diretório corrente, então lê o repositório do DESTINO sozinho. |
| `tools/workflow-dashboard/static/style.css` | adaptar | **Só o bloco `:root`** (paleta, tints, raios, status, fontes) e o comentário da linha 1. Nenhuma outra linha. |
| `tools/workflow-dashboard/static/index.html` | adaptar | `<title>`, o `<h1>` ("Aplicativo <span class="accent">Nome</span>"), o `eyebrow` se quiser, e as duas cores do favicon (fundo = `--navy`, círculo = `--brand-light` da paleta escolhida). |
| `tools/workflow-dashboard/static/areas.js` | adaptar | `ORDEM_DOM_ROTAS`, as descrições por área, os regex que classificam rota e entidade por área, e o nome do app no diagrama de contexto. Usar as áreas decididas na entrevista. |
| `tools/workflow-dashboard/static/content/glossary.js` | adaptar | Trocar "Pedro" pelo nome de quem instala. O resto é vocabulário do fluxo, fica. |
| `tools/workflow-dashboard/static/content/tabelas.js` | gerar | Resumos das tabelas do DESTINO (a aba Mapa usa como legenda). Sem banco, exportar `{}`. |
| `tools/workflow-dashboard/install-launchd.sh` | adaptar | Label do plist (`com.<slug>.workflow-dashboard`). macOS só. |
| `tools/workflow-dashboard/README.md` | adaptar | Nome do projeto e de quem cuida da fila humana. |
| `tools/workflow-dashboard/tests/` | adaptar | `test_front.py` afirma o título "Aplicativo Hospital": trocar pelo do DESTINO. `test_areas.py` e `test_plano.py` citam o Hospital em fixtures: trocar o texto, manter as asserções. |
| `tools/instalar-fluxo/` | excluir | O instalador não se instala. |

## Fora do git da ORIGEM (o roteiro cria no DESTINO)

| Item | Ação | Nota |
|---|---|---|
| Labels no GitHub | gerar | A lista completa vem de `docs/agents/triage-labels.md` e da seção de wayfinding de `docs/agents/issue-tracker.md`. Cores e descrições: `gh label list --repo pedrorezendefig/hospital-reunioes --json name,color,description`. As `area:*` são as do DESTINO. |
| `.claude/settings.local.json` | gerar | Sugerir allowlist mínima: `Bash(git:*)`, `Bash(gh:*)`, `Bash(python3:*)`. Fica fora do git. |
| `tokens/.env.example` | gerar | Só as chaves da plataforma do DESTINO. `tokens/.env` fica fora do git. |
