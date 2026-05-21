# Onboarding — Dev no Hospital Reuniões

Boas-vindas. Esta é a única página que você precisa pra começar.

## A regra de ouro

**Você decora uma palavra: `/start`.** O resto, a skill faz.

```
/start
```

Não memorize `/issue`, `/ship`, `/deploy`. Pode esquecer.

## Setup inicial (1 vez só)

1. Clone o repo.
2. Instale Docker Desktop (Mac).
3. Configure `gh auth login`.
4. Configure `git config user.name "Seu Nome"` e `git config user.email seu@email`.
5. `cd hospital-reunioes && docker compose up -d` (ou use `/atualizar-app` se já tá rodando algo).
6. Abra Claude Code no diretório do projeto.

## Como trabalhar

### Cenário 1 — Tô na branch `main`, ainda não fiz nada

```
/start
```

A skill pergunta o que você quer fazer. Conversa com você 1 a 1, propõe abordagens, cria um chronicle 🟡 com plano executável (com checkboxes pra você marcar conforme avança).

Depois você codifica. Quando terminar, digita `/start` de novo — ela vai detectar o diff e levar pra produção.

### Cenário 2 — Já codei, quero subir

```
/start
```

A skill detecta o diff, infere tipo (fix/feature/chore), cria branch + chronicle 🟡 com plano inferido, e encadeia o ciclo completo: commit → PR → 5 camadas de gate → merge → deploy.

### Cenário 3 — Tava trabalhando em algo, sessão fechou, abro novo terminal

```
git checkout feat/<sua-branch>
/start
```

A skill detecta o chronicle 🟡 da branch atual, conta quanto progresso já tem (X de Y tarefas concluídas), mostra a "tarefa atual" e oferece retomar de onde parou. Sem perda de contexto.

### Cenário 4 — Tem um bug feio que não sei resolver

```
/start debug
```

Invoca `systematic-debugging` do Superpowers. Investigação raiz antes de propor fix.

## O que acontece debaixo dos panos

```
/start
  └─ (a) brainstorming      — se working tree limpo, dialoga sobre abordagem
  └─ (b) chronicle 🟡       — plano com checkboxes salvo em docs/spec/chronicles/
  └─ (c) executing          — Claude executa o plano, marca [x] conforme avança
  └─ /ship                  — orquestrador
       ├─ commit            — conventional commits
       ├─ push              — branch nova
       ├─ PR aberto         — body padrão (5 seções) no GitHub
       ├─ 5 camadas de gate — review + security + requesting-review + CI + verification
       ├─ self-approve      — você aprova seu próprio PR (porque as 5 camadas validaram)
       ├─ merge squash      — mainline limpa
       └─ /deploy ship      — pre-flight gates + migrations + monitor Coolify + health
            └─ /snapshot    — regenera docs/spec/snapshots/ (rotas, entidades, schema, ...)
```

## Onde acho as coisas

| Pergunta | Olhar em |
|---|---|
| O que tô fazendo agora? | `ls docs/spec/chronicles/ \| grep 🟡` |
| Como a app funciona hoje? | `docs/spec/snapshots/` (7 arquivos) |
| O que tá em produção? | `docs/spec/deploy/state.json` |
| O que aconteceu desde X? | `docs/spec/CHANGELOG.md` |
| Quero ver rotas | `docs/spec/snapshots/ROTAS.md` |
| Quero ver schema do banco | `docs/spec/snapshots/SCHEMA.md` |
| Quero ver fluxograma | `docs/spec/snapshots/FLUXOGRAMAS.md` |

## Regras importantes

1. **Nunca commitar em `main` direto.** Sempre PR via `/ship` (ou `/start` que invoca `/ship`).
2. **Self-approval é OK** — as 5 camadas validam.
3. **Nunca pular `/security-review`** em mudanças que tocam auth, schema, ou env vars.
4. **Chronicle 🟡 obrigatório** — é a fonte da verdade do trabalho em progresso.
5. **Skills locais ficam em `.claude/skills/`** — não mexa sem confirmar comigo (Pedro). Mudanças aqui são "skills do time".

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
| `/start debug` | Investigação de bug |
| `/issue` | Criar/listar/pegar Issue GitHub |
| `/issue trabalhar <N>` | Pegar uma Issue específica |
| `/atualizar-app` | Rebuild docker-compose local (não toca produção) |
| `/deploy status` | Ver estado de produção (sem alterar) |
| `/snapshot` | Regenerar docs/spec/snapshots/ manual |
| `/snapshot --check` | Dry-run do snapshot |

## Quando algo dá errado

- Erro no `/ship`? Veja a mensagem específica. Tipicamente: lint, CI ou review reprovou. Corrija e rode `/start` de novo.
- Branch suja com conflito? `git pull --rebase origin main` na branch da feature, resolve conflitos, commit, rode `/start` de novo.
- Deploy falhou em produção? `/deploy` tem rollback automático. Veja `docs/spec/chronicles/🔴-*.md` mais recente pra entender o motivo.
- Snapshot não atualizou? Rode `/snapshot --force` manualmente.
- Esquecer tudo isso e perguntar pro Claude. Ele puxa o conhecimento daqui.

## Pra aprofundar

- Skills em `.claude/skills/` têm SKILL.md com documentação completa de cada uma.
- `CLAUDE.md` na raiz tem as regras gerais do projeto (deploy, chronicles, gates).
- `docs/spec/snapshots/` é o mapa vivo da aplicação.
- `docs/spec/chronicles/` é a história de mudanças passadas (🟢 sucessos, 🔴 falhas).

**Em caso de dúvida, pergunta pro Pedro ou cria uma Issue em "Dúvidas" no GitHub Discussions.**
