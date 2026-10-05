---
status: accepted
amends: 0061
---

# Fluxo automático até produção: só a migration para no humano

Decisão do Pedro (05/out/2026, grill do PRD #963). Em 05/10 cada PR levou de 13 a 16 minutos do merge à produção, e um conflito subiu isso para 25. Três PRs de ferramenta interna (#950, #954, #949), que não mudavam nada no app do hospital, pagaram o ciclo inteiro: CI repetido depois do commit de bump (cerca de 8 min), build de backend e frontend no Coolify (cerca de 5 min) e um PR de registro. Além do tempo, o fluxo parava o Pedro em vários pontos: o `/ship` no PR verde esperando alguém rodar o rabo, a `/onda-enxuta` esperando o `vai #a #b`, a migration esperando o "apliquei", e o modo auto do Claude Code barrando o deploy sem o número do PR citado no turno. Esta ADR fixa as quatro decisões do PRD #963 que mudam a regra da ADR 0061: quem para o fluxo, de onde vem a versão, o que é app e quem dispara o rabo.

## Decisões

1. **Sem olho humano antes de produção, exceto migration.** A proteção passa a ser CI, revisores agentes (`hr-revisor` e, em caminho sensível, `hr-revisor-seguranca`), health e rollback automático. Login e permissões não ganham parada própria: o revisor de segurança é o gate deles. O humano só é acionado, por notificação, em migration (colar o SQL no Studio), em fatia que esgotou as 3 tentativas e em rollback disparado.

2. **Versão sem commit.** O rabo calcula a versão pelo tipo dos commits (como hoje), grava `APP_VERSION` nos dois serviços do Coolify antes do merge e cria a tag `vX.Y.Z` no commit do squash. O `next.config` do frontend lê `APP_VERSION` e só cai no `package.json` se ela faltar; o `package.json` fica congelado. A verdade da versão é `history.json`, `state.json` e a tag. Sem commit de bump, não há segundo CI antes do merge.

3. **App é `hospital-reunioes/`.** Qualquer arquivo ali torna o PR "app": versão, build, health e registro. O resto (`tools/`, `.claude/`, `.github/`, `docs/`, o painel) é "ferramenta": só merge, sem versão, build ou PR de registro. PR misto conta como app. Substitui a regra de "docs-only" do `fechar_onda.py`.

4. **Rabo automático.** O `/ship` roda o `fechar_onda.py` quando os gates ficam verdes; a `/onda-enxuta` perde o checkpoint humano e mergeia os PRs verdes e limpos da onda num rabo só; o `/pegar-issue` encadeia `/tdd`, `/ship` e rabo. Ficam o semáforo de deploy e o teto de 3 tentativas por fatia. O rabo é script e não chama agente: devolve um código de saída (conflito, rollback feito, migration pendente vencida), e a skill que o chamou aciona o agente, reabre a issue ou notifica.

## Emenda à ADR 0061

- **Decisão 2 (um pipeline só).** O invariante herdado da 0022, "subir é decisão humana por lote citando os PR#", deixa de valer: o gate passa a ser CI, revisores agentes, health e rollback. Continuam valendo PR verde como CI, spec×diff e revisor independente, a baixa em 3 tentativas e o estado no GitHub. "O bump acontece na hora do merge, na `main`" passa a ser: a versão é calculada na hora do merge e vive na tag e no Coolify, sem commit.
- **Emenda de 02/10 (o rabo com a `main` protegida).** Sai o bump como commit na branch do PR, com o CI redisparado antes do merge. O resto continua: merge pela API com squash conferindo o `sha` do head, PR de entrega na onda, ruleset sem bypass. PR de registro e cancelamento do segundo build só existem em PR de app.
- **Decisões 1 e 3 continuam.** Cada sócio sobe o próprio PR, agora sem precisar estar presente fora da migration, e a `main` segue protegida pelo mesmo ruleset.

## Permissões na máquina de quem roda

Sem parada humana, o modo auto do Claude Code não pode parar no meio do rabo nem exigir o número do PR no turno. Cada pessoa põe no próprio `~/.claude/settings.json`, porque o modo auto ignora regra ampla de interpretador (como `Bash(python3:*)`) e não lê `autoMode` do settings do projeto:

- allow específico do `fechar_onda.py`, da `/minhas-issues` e da escrituração em issue e PR (`gh issue edit`, `comment` e `create`; `gh pr create` e `comment`);
- deny de force push e de `PUT` no ruleset do repositório: é a trava que fica no lugar do olho humano nas duas ações que o fluxo nunca faz;
- `autoMode.environment` descrevendo o repositório, o Coolify e a Vercel.

O `/setup-maquina` (nível 2) confere regra por regra e diz o que falta e por quê. Nunca grava o arquivo e nunca imprime o que ele guarda.

## Alternativas descartadas

- **Aplicar a migration automaticamente.** O Postgres de produção não é exposto; o SQL segue colado no Studio pelo humano, e por isso a migration é a única parada.
- **Quebra de vidro do ruleset ou runner próprio para incidente do GitHub Actions** (#958 e #955, wontfix). Num incidente, espera-se o Actions voltar.
- **Manter o commit de bump no PR.** É ele que redispara o CI antes de todo merge.

## Consequências

- O PRD #963 entrega as decisões em fatias: esta ADR e o `/setup-maquina` (#964), PR de ferramenta só faz merge (#965), CI por pasta (#966), versão sem commit (#967), rollback automático (#968), migration com recibo (#969), fluxo sem parada nas skills (#970) e backend em paralelo (#971). Cada decisão vale quando a fatia dela entrar; até lá segue o fluxo da ADR 0061.
- "Ferramenta" é a mesma palavra no `fechar_onda.py` e no detector do CI: as duas regras precisam bater.
- Meta medida em 05/10: PR de ferramenta em 1 a 2 minutos, PR do app em 6 a 7.
