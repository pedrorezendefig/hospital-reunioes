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

Sem parada humana, nada na máquina pode deixar o agente desligar a proteção da `main` nem publicar segredo sem olhar. Três decisões, revistas depois da revisão de segurança do PR #973:

- **A trava do ruleset é do servidor.** As sessões de agente de quem é admin do repositório (hoje só o Pedro, dono) usam um token fine-grained do GitHub sem a permissão Administration, na variável `GH_TOKEN` do `tokens/.env`, e saem da máquina o login guardado no `gh` com Administration e qualquer outro token do GitHub que o agente alcance (o PAT clássico que o `tokens/.env` guardava, exportado inteiro para a sessão). Sem Administration, o GitHub recusa mudar ou apagar ruleset, proteção de branch, colaborador ou webhook, venha o pedido de onde vier. A regra de deny do Claude Code não serve para isso: ela casa pelo começo do texto do comando, e o mesmo endpoint se alcança com `-X DELETE`, `-XPUT`, `--method=PUT`, flag depois do caminho, `gh api graphql` (`updateRepositoryRuleset`) ou `curl`. Por isso não existe deny para o ruleset, nem como alarme. Colaborador com WRITE não tem Administration e não precisa do token; mudar o ruleset passa a ser pela tela do GitHub. As permissões do token, tiradas do que o pipeline chama, estão na seção 5.1 do `docs/onboarding/claude-setup.md`: Actions, Contents, Issues, Pull requests e Workflows em escrita, Checks, Commit statuses e Metadata em leitura.
- **A `main` é travada pelo ruleset** (sem force push, sem apagar, sem bypass), que o token não consegue desligar. O deny de force push no `~/.claude/settings.json` mira só a `main` e pega as formas comuns (`--force`, `-f`, `--force-with-lease`, refspec `+main`), não `git -C <pasta> push` nem `--mirror`: é alarme a mais; a branch do próprio PR segue recebendo `--force-with-lease` depois de rebase.
- **Nada que publica texto, mexe em produção ou roda código do repositório fica em `permissions.allow`**, nem no settings do usuário nem no `.claude/settings.json` e `settings.local.json` do projeto (o allow de lá também vale). Ali a regra pula o classificador do modo auto. Allow de Bash com curinga só para leitura (`git status`, `gh pr view`, `jq`, `grep` e afins); os amplos do guia (`git`, `gh`, `coolify`, `curl`, `uv`, `pnpm`, `npx`, `docker`, `python3`, `find`) saem, e no modo auto o classificador libera esses comandos olhando cada um. O repositório é público e qualquer conta comenta em issue e PR, então `gh issue create`, `comment` e `edit` e `gh pr create` e `comment` vão em `autoMode.allow`, em prosa, restritos a `pedrorezendefig/hospital-reunioes` e a texto do próprio fluxo, para o classificador seguir olhando destino e conteúdo. O `fechar_onda.py` e a `/minhas-issues` também: o allow por caminho relativo rodaria, num worktree, a versão que o agente acabou de editar. O `autoMode` vai no settings do usuário porque o modo auto não lê `autoMode` do settings do projeto.

O `/setup-maquina` (nível 2) confere regra por regra e confere que nem o `gh` da sessão nem o do chaveiro administram o repositório (pergunta ao GitHub pelas deploy keys, que só respondem com Administration). Diz o que falta e por quê, nunca grava o arquivo e nunca lê nem imprime o token.

## Alternativas descartadas

- **Aplicar a migration automaticamente.** O Postgres de produção não é exposto; o SQL segue colado no Studio pelo humano, e por isso a migration é a única parada.
- **Quebra de vidro do ruleset ou runner próprio para incidente do GitHub Actions** (#958 e #955, wontfix). Num incidente, espera-se o Actions voltar.
- **Manter o commit de bump no PR.** É ele que redispara o CI antes de todo merge.

## Consequências

- O PRD #963 entrega as decisões em fatias: esta ADR e o `/setup-maquina` (#964), PR de ferramenta só faz merge (#965), CI por pasta (#966), versão sem commit (#967), rollback automático (#968), migration com recibo (#969), fluxo sem parada nas skills (#970) e backend em paralelo (#971). Cada decisão vale quando a fatia dela entrar; até lá segue o fluxo da ADR 0061.
- "Ferramenta" é a mesma palavra no `fechar_onda.py` e no detector do CI: as duas regras precisam bater.
- Meta medida em 05/10: PR de ferramenta em 1 a 2 minutos, PR do app em 6 a 7.
