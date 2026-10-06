---
status: superseded
amends: 0022, 0035
amended_by: 0062, 0063, 0064
superseded_by: 0068
---

# Um pipeline só, dono por PRD e `main` protegida: a esteira para três sócios em paralelo

Decisão do Pedro (01/out/2026, grilling na volta das férias). Entre 16 e 29/09 dois sócios trabalharam no repositório sem o Pedro, cada um pelo próprio clone, e a regra escrita não dizia quem sobe o que para produção. Um mergeou e deployou 44 PRs sozinho; o outro parou com 4 PRs verdes esperando, um deles com migration e webhook público. A `main` não tinha proteção. E existiam dois pipelines para a mesma coisa: a `/onda` + `/ship` originais (ADRs 0022, 0029, 0035) e a `/onda-enxuta` (PR #879), que entrou "sem mudar as originais". Esta ADR fixa um caminho só e diz quem é dono de quê.

## Contexto

Fatos que pesaram:

- O `dev.md` dizia "self-approval é OK, cada um aprova o próprio PR", mas nada travava o push direto na `main`, e a regra não dizia que migration de produção e `APP_VERSION` são de quem mergeia. Na prática, quem tinha o hábito subiu; quem não tinha, esperou.
- O `/ship` original faz o bump de versão **dentro do PR**. Com uma pessoa, isso funcionava. Com dois PRs verdes ao mesmo tempo é colisão garantida (bump fantasma, pilha de PRs sem CI, corrida de versão), já registrada nas notas do `history.json`.
- A `/onda-enxuta` tirou o bump do PR (`/ship --no-bump`) e concentrou merge, bump, `APP_VERSION` no Coolify, um push, um build, health com conferência de versão e registro num script só, o `fechar_onda.py`, rodado contra a `main`. Subiu 14 versões em produção nas férias (v0.143 a v0.156.6) sem incidente.
- O `issue-tracker.md` dizia que "o claim e o paralelismo acontecem nas fatias, não no PRD": o PRD não tinha dono. Resultado: a fila `ready-for-agent` é de quem chegar primeiro, e não há como ver quem está puxando o quê.
- O `tools/workflow-dashboard/` já lê issues, PRs e deploys pelo `gh` e é a única exceção permitida de "painel" no repositório (`CLAUDE.md`): é local, somente leitura, e cada sócio roda o seu.
- A ADR 0054 fixou que o GitHub é a única fonte do estado do desenvolvimento e o app é a porta do diretor. Visão de equipe dentro do app foi rejeitada neste grilling pela mesma razão: é necessidade interna da Vitta, não do hospital.
- Numeração de migration é sequencial (`110_`, `111_`, `112_`) e citada por número em ADRs, PRs e no `history.json`. Dois PRs nascem com o mesmo número, cada um passa no CI contra a `main` do seu momento, e o segundo merge entra repetido.

## Decisões

1. **Cada sócio mergeia e sobe para produção o próprio PR.** Não há fila humana única nem dono de PRD mergeando fatia alheia. Quem mergeia aplica a migration em produção (Studio) e cuida do `APP_VERSION`, e por isso todo sócio precisa de acesso ao Studio e ao Coolify. Rejeitado: só o Pedro mergeia (foi o gargalo das férias); dono do PRD mergeia as fatias dos outros (recria o gargalo por PRD).

2. **Um pipeline só, no molde enxuto.** O `/ship` para no PR verde (3 gates, sem bump). O único rabo de merge, bump, `APP_VERSION`, push, build, health e registro (`state.json`, `history.json`, `CHANGELOG`, snapshot) é o `fechar_onda.py`, tanto para um PR avulso quanto para o lote de uma onda. A `/onda` original (ADR 0022) se aposenta; a `/onda-enxuta` passa a ser **a** onda, e os invariantes da 0022, 0029 e 0035 (subir é decisão humana por lote citando os PR#, PR verde é CI + spec×diff + revisor independente, baixa em 3 tentativas, estado no GitHub) continuam valendo nela. O bump acontece **na hora do merge, na `main`**, nunca no PR. Rejeitado: dois pipelines com uma regra de merge (duas formas de chegar ao mesmo lugar para quem clona); deixar como está (é a ausência de definição que produziu as férias).

3. **`main` protegida, sem aprovação humana.** Ruleset do GitHub na `main`: PR obrigatório, CI (`ci.yml`) obrigatório e atualizado com a base, force push e delete bloqueados, regra valendo para admin. Zero aprovações exigidas: os gates continuam sendo o CI e os revisores agentes (revisor e revisor de segurança). Rejeitado: uma aprovação de outro sócio em caminho sensível (reintroduz a espera exatamente nos PRs mais demorados; volta a valer se entrar quarto sócio ou dev externo).

4. **Dono do PRD.** Todo PRD nasce com um assignee, quem fez o grilling, posto pelo `/to-prd`. Uma fatia sem claim pertence, para efeito de visão, ao dono do PRD; o claim de quem a pega é que muda o dono de fato. Pegar fatia de PRD alheio não é proibido, mas se combina antes com o dono. Issue avulsa (sem PRD) tem como dono quem a pegou, e só.

5. **Visão por responsável no painel local, não no app.** A aba Issues do `tools/workflow-dashboard/` ganha o modo **agrupar por responsável**, ligado por padrão, para abertas, fechadas e todas: um grupo por pessoa mais "sem responsável". Dentro do grupo, em andamento primeiro (com estado do PR: CI, mergeável, há quantos dias espera), depois planejadas; nas fechadas, a versão em que subiu. Sem aba nova, sem métrica por pessoa (lead time, volume): compara gente, não separa trabalho. Rejeitado: tela na aba Tecnologia do app atrás de `github_login` (código em produção para necessidade interna, e a ADR 0054 reserva o app ao diretor); GitHub Projects (terceira tela que ninguém abre).

6. **Guarda de migration em dois tempos.** No CI: o PR falha se o número da migration que ele adiciona já existe na `main`. No `fechar_onda.py`: antes do merge, a conferência se repete contra a `main` **atual**, e o script para com mensagem clara se colidiu; renumerar é do autor. Lockfile e arquivos de costura (`main.py`, `config.py`, `AdminSidebar.tsx`) ficam com o `git`: conflito real aparece no `mergeStateStatus` e a `/resolver-conflitos` resolve. Rejeitado: nome de migration com carimbo de data e hora (robusto, mas quebra o jeito de falar "migration 110 aplicada no Studio" que ADRs e `history.json` usam).

7. **Árvore principal sempre na `main`.** Todo trabalho, inclusive doc e ADR, acontece em worktree. A árvore principal de cada clone fica na `main` e só recebe `git pull`. É o que impede o "voltei e meu local está 11 dias atrás numa branch de issue com 4 worktrees órfãos".

## Emenda à ADR 0022

- O comando `/onda` e a forma do loop (sessão humana orquestrando, bump no PR, `/deploy ship` ao fim) deixam de ser o caminho. O que a 0022 fixou de **princípio** (ondas de issues desbloqueadas, 2-3 em paralelo, 1 worktree por issue, um checkpoint humano de merge por lote, um deploy por onda, reabastecer e repetir) continua valendo e é herdado pela `/onda-enxuta`.

## Emenda à ADR 0035

- Os gates de review continuam pertencendo ao orquestrador, como agentes frescos e independentes que comentam o veredito no PR. Na enxuta eles são o `hr-revisor` e o `hr-revisor-seguranca`, disparados assim que o PR abre, com no máximo 2 rodadas de correção. Nada do raciocínio da 0035 muda; muda só o nome dos agentes.

## Consequências

- Nasce um PRD com as fatias: ruleset da `main`; `/to-prd` põe o dono; painel com agrupar por responsável; `/ship` sem bump e `fechar_onda.py` como rabo único do PR avulso; guarda de migration no CI e no script; aposentadoria da `/onda` e da `/montar-ondas`; `/ask-pedro`, `CLAUDE.md`, `dev.md` e `issue-tracker.md` apontando para o caminho único (o `/ask-pedro` muda no mesmo commit que mexe nas skills, regra do `CLAUDE.md`).
- `dev.md` e `issue-tracker.md` já foram emendados em prosa com as regras de gente (decisões 1, 4 e 7), que valem desde já. O que depende de código (decisões 2, 3, 5 e 6) vale quando a fatia correspondente entrar.
- Promover alguém a colaborador `write` passa a significar: pode mergear e deployar o que fez, e precisa de Studio e Coolify.
- `CONTEXT.md` não muda: é glossário do hospital, não do time.

## Emenda de 02/10/2026: o rabo com a `main` protegida (issue #910)

A decisão 3 deixou em aberto como o `fechar_onda.py`, que mergeava localmente e dava um push direto na `main` com o bookkeeping junto, convive com um ruleset que exige pull request. Havia duas saídas: (a) tudo entra por PR e o merge sai pela API do GitHub; (b) ruleset com bypass para um ator de deploy, e o script segue como estava.

**Decisão: saída (a).** O bypass da (b) recria a dependência de uma pessoa, porque quem roda o rabo precisa ser o ator com bypass, e a forma sem pessoa (uma GitHub App própria) está fora do escopo do PRD #902. Com a (a), a regra vale para todos, admin inclusive, sem exceção. Rejeitado: (b), pelo mesmo motivo que a decisão 1 rejeitou "só o Pedro mergeia".

Como fica:

- **PR avulso.** O bump entra como commit na própria branch do PR. Se a `main` andou, ela vem antes, por merge, porque o ruleset exige a branch em dia com a base (emendado pela ADR 0064, decisão 2: o ruleset deixou de exigir, e o PR entra no head com o CI verde, sem a `main` trazida). O script espera o CI desse head ficar verde, põe o `APP_VERSION` no Coolify e mergeia pela API com squash, conferindo o `sha` do head. Squash porque é o único método que o repositório permite.
- **Onda.** Os PRs do lote entram por merge local `--no-ff` numa branch `onda/<sessao>`, com o bump em cima, e o script abre um **PR de entrega** com `Closes` de cada issue do lote, mergeado pela API como o avulso. Continua um merge de código na `main` e um build por onda; os PRs do lote fecham com comentário apontando o PR de entrega.
- **Registro.** `history.json`, `state.json`, `CHANGELOG`, snapshot e draft do Manual sobem **depois do health**, num PR só de docs que o script abre e mergeia pela API. O registro deixa de nascer com o resultado presumido e passa a gravar o que aconteceu.
- **Segundo build.** O merge do registro é um push na `main`, e o webhook do Coolify rebuilda os apps sem olhar o caminho (issue #851). Enquanto o Coolify não filtra caminho, o script cancela o deploy do commit do registro, e só dele.
- **CI que sempre reporta.** O `ci.yml` deixou de ter `paths-ignore` no `pull_request`: workflow pulado por filtro de caminho não reporta check, e o ruleset deixaria todo PR só de docs (o registro, ADR, skill) esperando para sempre. Um job `mudancas` decide se o PR mexe fora de `docs/`, `.claude/` e Markdown; os três jobs obrigatórios pulam por `if` (job pulado conta como verde) e rodam se o detector falhar.
- **Ruleset versionado** em `.github/rulesets/main.json`: PR obrigatório com zero aprovações, os três jobs do `ci.yml` obrigatórios (vindos do GitHub Actions) e em dia com a base (emendado pela ADR 0064, decisão 2: os checks valem no head do PR, sem exigir a branch em dia com a base), force push e delete bloqueados, sem bypass. Aplicar e conferir é do admin, à mão, com os comandos do `docs/onboarding/dev.md`. O `tools/test_ruleset_main.py` amarra o nome de cada check ao job do `ci.yml`.

Custo aceito: o commit de bump redispara o CI antes do merge (alguns minutos com o semáforo preso), e uma rodada que encontra a `main` andando no meio do CI para com código 2 e roda de novo, reaproveitando o bump que ficou na branch.

## Emenda de 02/10/2026: filtro por responsável no painel (decisão 5)

O agrupar por responsável não mostrou quem cuida de quê: a fatia sem claim aparecia no grupo do dono do PRD, e a lista ficava parecendo de gente que não estava trabalhando nela. O Pedro trocou a visão.

**Decisão:** a aba Issues do painel local filtra por **um** responsável de cada vez, em vez de agrupar. Responsável é quem está designado na issue (assignee), sem herdar o dono do PRD; "sem responsável" mostra as issues sem ninguém designado. Com o filtro ligado, um visor abaixo dos cards gerais mostra as contas da pessoa: abertas (e quantas em andamento), entregues (e quantas nos últimos 30 dias), lead time médio e prontas para agente. O coletor passa a trazer todas as issues e PRs, sem o teto de 200.

Revoga, na decisão 5, o agrupamento ligado por padrão, a herança do dono do PRD **na visão do painel** e o "sem métrica por pessoa": o Pedro quer ver quanto cada um entregou. O dono do PRD continua valendo como responsabilidade (decisão 2 e `issue-tracker.md`); só deixa de redistribuir as fatias no painel.

## Emenda de 05/10/2026: responsável cai em quem criou (decisão 5)

> **Revogada** pela emenda de 06/10/2026 da ADR 0062 (issue #942): no painel, responsável é só quem está designado; sem assignee, a issue é "ninguém assumiu", e o autor fica no card só como informação. O texto abaixo é histórico.

Com o filtro da emenda de 02/10, 120 issues apareciam "sem responsável", 32 delas abertas, embora toda issue nasça do Claude Code de alguém. O Pedro quer que nenhuma issue fique sem dono no painel.

**Decisão:** no painel, responsável é quem está designado (assignee) e, sem ninguém designado, quem criou a issue (author do GitHub). Quem assumiu manda sobre quem criou. Para não repetir o problema da emenda de 02/10 (fatia sem claim parecendo trabalho de quem rodou o `/to-issues`), a origem fica visível: o cartão mostra `👤 fulano` para quem assumiu e `✎ criada por fulano` para quem só criou, o visor da pessoa separa assumidas de só criadas, e o "em andamento" conta só issue com assignee. O "sem responsável" vira **"ninguém assumiu"**: as issues sem assignee, a fila sem claim. O PRD sem assignee segue marcado "sem dono", agora com quem o criou ao lado.

Nada muda no GitHub: o assignee continua sendo o claim do protocolo paralelo (`issue-tracker.md`), e o painel não designa ninguém. Limite conhecido: a issue aberta pela integração do app (Demanda vira issue) tem como autor o dono do token, e conta apagada vem do `gh` como `ghost`.
