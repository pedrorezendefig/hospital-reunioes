# Onboarding — Dev no Hospital Reuniões

Boas-vindas. Esta é a única página que você precisa pra começar.

## A regra de ouro

**Você decora uma palavra: `/start`.** O resto, a skill faz.

```
/start
```

Não memorize `/issue`, `/ship`, `/deploy`. Pode esquecer.

## Setup inicial (1 vez só)

**Faça o setup completo do Claude Code seguindo [`claude-setup.md`](./claude-setup.md)** — esse guia cobre tudo (CLI, plugins essenciais, MCP Coolify, hook auto-import de planos, permissions). Tempo: 15–30min.

Depois disso, sobe o app local:
```bash
cd hospital-reunioes && docker compose up -d   # ou use /atualizar-app
```

Pré-requisitos básicos antes do `claude-setup.md`:
- Docker Desktop instalado
- `gh auth login` feito
- `git config user.name "Seu Nome"` + `git config user.email "seu@email"`
- Acesso `WRITE` ao repo (peça pro Pedro adicionar)

## Como trabalhar

### Cenário 1 — Tô na branch `main`, ainda não fiz nada

```
/start
```

A skill pergunta o que você quer fazer. Invoca `superpowers:brainstorming` automaticamente, conversa com você 1 a 1, propõe abordagens, fecha um design. Em seguida `superpowers:writing-plans` cria um **plano executável** em `docs/planejamento/em-andamento/superpowers/` (com checkboxes pra você marcar conforme avança e header de progresso "Fase X de Y · A%" no topo).

Depois você codifica. Quando terminar, digita `/start` de novo — ela vai detectar o diff e levar pra produção.

**Variação:** se você prefere planejar no plan mode nativo (`Shift+Tab+Tab`), faça isso — o hook `PostToolUse:ExitPlanMode` (configurado em `claude-setup.md` passo 5) importa o plano automaticamente pra `docs/planejamento/em-andamento/plan-mode/` quando você aceita.

### Cenário 2 — Já codei, quero subir

```
/start
```

A skill detecta o diff, infere tipo (fix/feature/chore), cria branch + plano em `docs/planejamento/em-andamento/manual/` (3 frases curtas suas + contexto inferido do diff), e encadeia o ciclo completo: commit → PR → 5 camadas de gate → merge → deploy.

### Cenário 3 — Tava trabalhando em algo, sessão fechou, abro novo terminal

```
git checkout feat/<sua-branch>
/start
```

A skill detecta o plano em `docs/planejamento/em-andamento/*/` cujo `branch:` no frontmatter casa com a branch atual, recalcula o header de progresso (X de Y tarefas, % concluído), mostra "Tarefa atual" + "Próximo passo" do §5, e oferece retomar de onde parou via `superpowers:executing-plans`. Sem perda de contexto.

**Alternativa standalone:** `/planejamento status` lista todos os planos abertos (em qualquer branch) com %. Útil pra responder "o que tem aberto pra mim?".

### Cenário 4 — Tem um bug feio que não sei resolver

```
/start debug
```

Invoca `systematic-debugging` do Superpowers. Investigação raiz antes de propor fix.

## O que acontece debaixo dos panos

```
/start
  └─ (a) brainstorming         — se working tree limpo, dialoga sobre abordagem (superpowers)
  └─ (b) writing-plans         — gera plano com checkboxes em docs/planejamento/em-andamento/superpowers/
  └─ (c) recalc_progress.sh    — insere header "Progresso 0% · Fase 1 de N" no topo
  └─ (d) executing-plans       — Claude executa o plano, marca [x] conforme avança
  └─ /ship                     — orquestrador
       ├─ commit               — conventional commits
       ├─ push                 — branch nova
       ├─ recalc_progress.sh   — header do plano sobe % a cada commit
       ├─ chronicle 🟡         — índice enxuto criado em docs/spec/chronicles/
       ├─ PR aberto            — body padrão (5 seções) no GitHub
       ├─ 5 camadas de gate    — review + security + requesting-review + CI + verification
       ├─ self-approve         — você aprova seu próprio PR (porque as 5 camadas validaram)
       ├─ merge squash         — mainline limpa
       └─ /deploy ship         — pre-flight gates + migrations + monitor Coolify + health
            ├─ git mv plano    — em-andamento/<source>/ → finalizado/<source>/ (status: finalizado)
            ├─ chronicle 🟢/🔴 — rename do 🟡 com SHA + data do deploy
            └─ /snapshot       — regenera docs/spec/snapshots/ (rotas, entidades, schema, ...)
```

## Onde acho as coisas

| Pergunta | Olhar em |
|---|---|
| O que tô fazendo agora (plano de trabalho)? | `/planejamento status` ou `ls docs/planejamento/em-andamento/*/` |
| O que mergeou recentemente (índice por PR)? | `ls docs/spec/chronicles/ \| grep 🟢 \| tail -10` |
| Como a app funciona hoje? | `docs/spec/snapshots/` (7 arquivos) |
| O que tá em produção? | `docs/spec/deploy/state.json` |
| O que aconteceu desde X? | `docs/spec/CHANGELOG.md` |
| Quero ver rotas | `docs/spec/snapshots/ROTAS.md` |
| Quero ver schema do banco | `docs/spec/snapshots/SCHEMA.md` |
| Quero ver fluxograma | `docs/spec/snapshots/FLUXOGRAMAS.md` |
| Onde mora o plano detalhado deste trabalho? | `docs/planejamento/em-andamento/<source>/<slug>.md` (3 subpastas: plan-mode, superpowers, manual) |
| Plano legado já finalizado? | `docs/planejamento/finalizado/<source>/<slug>.md` |

## Regras importantes

1. **Nunca commitar em `main` direto.** Sempre PR via `/ship` (ou `/start` que invoca `/ship`).
2. **Self-approval é OK** — as 5 camadas validam.
3. **Nunca pular `/security-review`** em mudanças que tocam auth, schema, ou env vars.
4. **Plano em `docs/planejamento/em-andamento/<source>/` é obrigatório** — fonte da verdade do trabalho em progresso. Chronicle 🟡 é índice pós-fato (1 por PR), não substitui plano.
5. **Skills locais ficam em `.claude/skills/`** — não mexa sem confirmar comigo (Pedro). Mudanças aqui são "skills do time".
6. **Header de progresso é derivado** — não edite o bloco `> ## Progresso:` à mão. Marque `[x]` no body, rode `/planejamento progresso` (ou deixe `/ship` chamar). Frontmatter de progresso também é derivado.

## Notificações

GitHub Mobile (app no celular) é o canal de notificação. Marca o repo como "Watching" pra receber pushes:
- PR aberto / aprovado / mergeado
- CI passou / falhou
- Review pedida / recebida
- Comentário em PR ou Issue

Sem Discord, sem Slack.

## Atalhos úteis

| Comando | Pra que |
|---|---|
| `/start` | Entry point único |
| `/start --rapido` | Pula brainstorming, vai direto |
| `/start --rigoroso` | Força brainstorming mesmo com diff |
| `/start debug` | Investigação de bug (invoca `superpowers:systematic-debugging`) |
| `/issue` | Criar/listar/pegar Issue GitHub |
| `/issue trabalhar <N>` | Pegar uma Issue específica |
| `/atualizar-app` | Rebuild docker-compose local (não toca produção) |
| `/deploy status` | Ver estado de produção (sem alterar) |
| `/deploy rollback` | Reverte produção pro deploy anterior |
| `/snapshot` | Regenerar `docs/spec/snapshots/` manual |
| `/snapshot --check` | Dry-run do snapshot |
| `/planejamento status` | Lista planos abertos com `% progresso` |
| `/planejamento progresso` | Recalcula header do plano da branch atual |
| `/planejamento importar` | Importa plano externo (default: mais recente em `~/.claude/plans/`) |
| `/planejamento finalizar [--abort]` | Move plano pra `finalizado/<source>/` (ou deleta) |

## Quando algo dá errado

- Erro no `/ship`? Veja a mensagem específica. Tipicamente: lint, CI ou review reprovou. Corrija e rode `/start` de novo.
- Branch suja com conflito? `git pull --rebase origin main` na branch da feature, resolve conflitos, commit, rode `/start` de novo.
- Deploy falhou em produção? `/deploy` tem rollback automático. Veja `docs/spec/chronicles/🔴-*.md` mais recente pra entender o motivo.
- Snapshot não atualizou? Rode `/snapshot --force` manualmente.
- Esquecer tudo isso e perguntar pro Claude. Ele puxa o conhecimento daqui.

## Pra aprofundar

- **[`claude-setup.md`](./claude-setup.md)** — guia de setup completo do Claude Code pra este projeto (plugins, MCP, hooks, permissions). Faça uma vez.
- Skills em `.claude/skills/` têm SKILL.md com documentação completa de cada uma.
- `CLAUDE.md` na raiz tem as regras gerais do projeto (deploy, planos, gates).
- `docs/planejamento/README.md` — schema completo do plano (frontmatter + header de progresso + 8 seções) + documentação da skill `/planejamento`.
- `docs/spec/snapshots/` — mapa vivo da aplicação (7 arquivos auto + curados).
- `docs/spec/chronicles/` — índice de mudanças passadas (🟢 sucessos, 🔴 falhas, 1 por PR).

**Em caso de dúvida, pergunta pro Pedro ou cria uma Issue em "Dúvidas" no GitHub Discussions.**
