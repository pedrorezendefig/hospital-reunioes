# Notas do fluxo: Hospital

O que só o Hospital tem, por cima do pacote do fluxo. Cada seção `## <skill>` é lida por `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas <skill>`. Fonte: PedroOS, `projetos/hospital/fluxo-notas.md`; o instalador copia para `.claude/fluxo-notas.md`. Edite lá, não aqui.

Vocabulário do domínio: Reunião, Ata, Pendência, Facilitador, Colaborador, Envelope (o `CONTEXT.md` é a referência de tom).

## onda-enxuta

**Fatia de manual:** entra na subida como qualquer PR verde, com o render final já feito na fatia; o vídeo não espera OK humano (emenda de 14/10/2026 à ADR 0068). A tabela do passo 4 ganha a coluna "MP4 do vídeo".

**Migration:** a linha da subida é `migration: cole no Studio <arquivo>:1`. Repasse pelo evento `pronto-para-voce` assim que aparecer.

## onda-implementador

- **Anexos da Demanda:** se o corpo da issue diz "Anexos" (os prints da Demanda, que vivem só no app), rode no seu worktree `python3 .claude/skills/pegar-issue/scripts/anexos.py <N>` e leia com a Read tool cada caminho que ele imprimir; saída 1 não bloqueia: siga sem as imagens e ponha o motivo em `atritos`.
- **Migration ou policy nova:** antes do TDD, leia a Skill `supabase-postgres-best-practices`, seção Security & RLS.
- **Fatia de manual** (`docs: manual do PRD #N`): no lugar do TDD, chame a Skill tool com `manual` (argumento `#<PRD>`) e, quando a issue pede o Vídeo de visão geral do módulo, leve-o até o render final, sem esperar OK humano; o caminho do MP4 vai no corpo do PR. Página de tarefa não tem vídeo (ADR 0072).

## onda-corretor

Se o corpo da issue diz "Anexos" (os prints da Demanda, que vivem só no app), rode no seu worktree `python3 .claude/skills/pegar-issue/scripts/anexos.py <N>` e leia com a Read tool cada caminho que ele imprimir; saída 1 não bloqueia, vai em `pendente`.

## onda-revisor

Com `Sensível:` no prompt, leia antes `.claude/skills/supabase-postgres-best-practices/references/security-rls-performance.md` (checklist de RLS e índice da Supabase, fora do nosso viés). Dado sensível aqui é dado de paciente e de outro Facilitador.

## pegar-issue

**Anexos da Demanda.** Se o corpo da issue diz "Anexos" (a frase "Anexos: N imagens na Demanda"), baixe os prints, já dentro do worktree da issue:

```bash
python3 .claude/skills/pegar-issue/scripts/anexos.py <N>
```

É a boca única (ADR 0069, decisão 2): o print vive só no app, nunca na issue (o repositório é público), e o script busca pela rota de automação com a `TECNOLOGIA_AUTOMACAO_API_KEY` do `tokens/.env`. Ele grava em `local/anexos/<N>/` (fora do git) e imprime um caminho por linha: leia cada um com a Read tool. Saída `sem anexos` é normal. Saída 1 traz o motivo (chave ausente, ponte desligada no Coolify): repasse a linha e siga sem as imagens. O `/ship` apaga a pasta ao abrir o PR.

## ship

- **Valor entregue:** é o que o hover do card do PR mostra no painel, sozinho; escreva como quem explica a um colega do hospital.
- **Anexos:** aberto o PR com `--issue N`, apague os prints da Demanda que o `anexos.py` baixou: `rm -rf local/anexos/<N>` na raiz do clone (ADR 0069, decisão 3: print do hospital não fica parado na máquina; sem a pasta, o comando não faz nada).
- **Migration:** quem aplica é o humano, no SQL Editor do Studio de produção. Quando o humano disser "apliquei a migration N" (ou `/ondas aplicada N`), o mod hr-ondas grava em `~/.claude/hr-ondas/aplicadas` e o painel para de cobrar; a subida continua esperando o `/api/health`.
- **Fatia de manual** (ADR 0057): sobe como qualquer outra, com o render final feito na fatia e o caminho do MP4 no corpo do PR. Nada de `PushNotification` pedindo OK no vídeo (emenda de 14/10/2026 à ADR 0068).
- **Pendência só humana** inclui o import na virada.

## tdd

Backend = `pytest` (TestClient e endpoints reais); frontend segue o padrão já existente no repo. Linters com regularidade: backend `ruff check` e `ruff format --check`; frontend `tsc` e lint. Exemplo de nome de teste: `test_facilitador_ve_status_de_assinatura`.

## to-prd

- **Nunca cite número de issue ou de PR dentro do bloco "👔 Para o diretor"** (nada de "o PRD #469", "a #430 entregou"). O bloco é a única parte do corpo que o app lê e mostra ao diretor na aba Tecnologia, e a ADR 0054, decisão 9, diz que ele não vê número de issue. Precisa referenciar outro trabalho? Descreva pelo nome ("o PRD da Ouvidoria"), ou deixe a referência na parte técnica, abaixo do bloco.
- O template ganha, depois das Decisões, a seção:

```md
## Manual: páginas que nascem ou mudam

As páginas do Manual do usuário (`docs/manual/`) que esta entrega cria ou altera. É desta seção que a Fatia de manual tira o trabalho dela, então ela é lista, não promessa:

- **Páginas de tarefa** (uma ação cada, título no infinitivo): qual nasce, qual muda e em que módulo (`primeiros-passos`, `reunioes`, `ouvidoria`, `pops`, `contas-medicas`, `admin`).
- **Como funciona**: o que a entrega muda no comportamento que não é ação de ninguém (como o prazo é contado, o que o sistema apaga sozinho).
- **Novidades**: a entrada que este PRD gera no `novidades.md` do módulo, na língua do usuário.

PRD que não toca tela nenhuma escreve **"Nenhuma: este PRD não muda tela"**. É o que diz ao `/to-issues` para não criar a Fatia de manual (ADR 0057, decisão 8).
```

- A conversa veio de um `/grill-with-docs #N` sobre um PRD do diretor? Não crie issue: siga a nota abaixo.

### PRD do diretor: completar a mesma issue

Quando a conversa veio de um `/grill-with-docs #N` sobre um **PRD do diretor** (a issue que o "sim" do Planejamento da Demanda cria, ADR 0075; `prd_do_diretor.py ler <N>` confirma), a issue já existe com a metade de negócio. Nesse caso, sem `gh issue create`:

1. Escreva só as seções técnicas do template num arquivo do scratchpad: `## Decisões de implementação` e `## Decisões de teste` (obrigatórias), mais `## Manual: páginas que nascem ou mudam`, `## Fora de escopo` e `## Notas adicionais`. Cada item de "Ficou em aberto" que o grill fechou entra em Decisões de implementação, dizendo de qual item veio.
2. Não reescreva o bloco "Para o diretor", Problema, Solução, Histórias, Decisões de negócio nem "Ficou em aberto": é o texto que o diretor aprovou no app, palavra por palavra. O script recusa arquivo que traga o bloco.
3. Passe o arquivo pela Skill tool com `humanizer` em modo embutido, como o corpo de sempre.
4. Complete a issue:

   ```bash
   python3 .claude/skills/to-prd/scripts/prd_do_diretor.py completar <N> <arquivo>
   ```

   O script insere as seções antes da Origem, deixa o resto do corpo byte a byte (o marcador da Demanda, que sustenta o Vínculo, inclusive) e troca `needs-triage` por `ready-for-agent`. O dono já vem do app (`GITHUB_LOGIN_DONO`); não mexa no assignee.
5. Anuncie: _"PRD do diretor **#N** completado"_. O `#N` é o pai das fatias do `/to-issues`.

## to-issues

- **Nunca cite número de issue ou de PR dentro do bloco "👔 Para o diretor"** (a mesma regra do `/to-prd`, ADR 0054, decisão 9). A referência a outra issue vive na parte técnica, onde "Bloqueada por: #X" e o "Pai" já moram.
- **O arquivo do kit.** O Kit de conhecimento (`hospital-reunioes/backend/app/conhecimento/`) é o que o Assistente de Tecnologia lê inteiro a cada conversa. Toda fatia que muda comportamento visível de um módulo lista, nos critérios de aceite, o arquivo do kit a atualizar no mesmo PR (ADR 0056, decisão 2): `- [ ] O texto do Produto <Ouvidoria> no kit de conhecimento diz o comportamento novo.` Escreva o nome do Produto, não o caminho. Regra completa em `docs/agents/domain.md`.

### A Fatia de manual (todo PRD com tela)

O PRD traz a seção "Manual: páginas que nascem ou mudam". Quando ela lista alguma página, a **última** fatia é a Fatia de manual, e ela não é opcional (ADR 0057, decisão 8): título `docs: manual do PRD #<PRD>`; labels `type:docs` e `area:docs`, além de `ready-for-agent` e do tamanho; bloqueada nativamente por todas as fatias de código do PRD (a página precisa da tela pronta para o print); o corpo manda rodar `/manual #<PRD>`, cita a seção "Manual" do PRD como a lista do que escrever e lembra que tudo nasce em `draft: true`, porque quem tira o draft é a Action do push da `main`. PRD com "Nenhuma: este PRD não muda tela" não ganha esta fatia.

**Vídeo do módulo, sempre que o PRD muda página dele** (ADR 0076, que emenda a 0072): para cada módulo que tem página na seção "Manual" do PRD, o corpo da Fatia de manual traz a linha "Refazer o vídeo do módulo `<modulo>`" e um critério de aceite com o PRD nos `prds_cobertos` do `meta.json` do vídeo. A exceção é escrita na própria fatia, na linha do módulo: "O vídeo do módulo `<modulo>` segue válido porque ...", com o motivo (o PRD só corrige um texto que o vídeo não mostra, por exemplo); aí o PRD entra nos `prds_cobertos` sem render novo e o revisor confere o motivo. O Admin e a Central de Comando não têm vídeo, e Página de tarefa não tem vídeo.

## triage

**Issue born from a Demanda (aba Tecnologia).** An issue whose body carries `<!-- demanda-vitta id="..." -->` was created by the app's **Levar para desenvolvimento** button (ADR 0054). Treat it differently in two places:

- **Context.** The "Para o diretor" block is the director's own words, already PII-filtered (ADR 0060); the Origem line links to the Demanda in the app, where the full Conversa lives. Say upfront "veio da Demanda, responsável @login" so the maintainer knows who owns it on the app side. Reply to the director through the Demanda's Conversa, never by GitHub comment (comments don't flow back to the app).
- **Assignee.** The issue is born assigned to the Demanda's responsável. In `needs-triage` that assignee is **responsibility, not claim** (same reading as the PRD owner, ADR 0068). When you move it to `ready-for-agent`, **remove the assignee** (`gh issue edit <N> --remove-assignee <login>`): the pool is `no:assignee`, and a kept assignee hides the issue from `/pegar-issue` and the `/onda`. `ready-for-human` keeps it.

The port (A/B/C) is still the triage's call: the button only opens the door.

## montar-ondas-enxutas

- **Health de produção:** `curl -s https://api.hospitalsaomatheus.cloud/api/health` no inventário do passo 1.
- **Plataforma:** Coolify. Env var ou segredo criado no Coolify só entra no container no próximo deploy. Bucket que nasce por SQL (`INSERT INTO storage.buckets`, molde das migrations 049 e 066) não é parada extra: entra na migration. Migration: o Pedro cola no Studio; lance a sessão com migration quando ele estiver perto do Studio.
- **Divulgação:** o passo 5b abaixo entra depois do passo 5, e o relatório (passo 6) ganha os prompts de divulgação no item 5 e o item 6.4 (quando colar cada um e a quem mandar o link).

**Passo 5b.** Divulgação dos PRDs que fecham neste plano

PRD que fecha é entrega para o diretor e para quem opera o hospital, e eles só "veem" a funcionalidade pelo vídeo e pela página do `/divulgar`. Para **cada PRD cuja última fatia está nos prompts**, o plano traz também uma linha de divulgação. Sem ela, o PRD fecha no GitHub e ninguém fora do time fica sabendo.

Regras:

1. **Terminal próprio, nunca dentro da `/onda-enxuta`.** O `/divulgar` tem gate humano no draft do vídeo; a `/onda-enxuta` é AFK até produção. Misturar os dois deixa a onda parada esperando um OK que não é de merge. O plano abre uma **sessão de divulgação** (uma só, sequencial: um PRD de cada vez) com um prompt por PRD.
2. **Quando cada vídeo pode começar** é decisão do plano, não do humano. Leia as fatias que faltam do PRD:
   - Se as fatias restantes **não mudam tela** (chore, teste, docs, manual): o vídeo começa **agora**, em paralelo com as ondas. O carimbo retrata a versão de prod de hoje e o PRD já está inteiro no app.
   - Se alguma fatia restante **muda tela**: o vídeo espera o deploy da última fatia visual (o carimbo "retrata o app em vX.Y.Z" precisa da versão que tem a tela) e roda em paralelo com o que sobrar (manual, docs).
3. **Saída padrão é vídeo e página** (o comando sem flag). `--so-video` só se o humano pedir. Contexto com página de módulo (`docs/comunicacao/ouvidoria/modulo/`): o prompt lembra de republicar a página de módulo com o MP4 novo de `~/Videos/Hospital/`.
4. O prompt de divulgação segue o mesmo formato do passo 5 (cabeçalho de leitura fora do bloco, comando na primeira linha do bloco) e diz **o que esperar antes de colar**: "cole depois do deploy verde da onda N da sessão A" ou "pode colar agora". Template:

```
/divulgar <PRD>

Contexto: o PRD #<PRD> fechou com as fatias #a, #b, #c (as visuais já estão em prod v<X.Y.Z>; a #d é só <chore/manual> e não muda tela).
O exemplo único da demonstração: <uma linha com o caso de uso ponta a ponta que a issue descreve, no vocabulário do CONTEXT.md>.
Fontes: o PRD e as filhas no GitHub, o código real do frontend (gh pr view <PR> --json files), ROTAS.md e o CONTEXT.md.
Pare no draft e me mostre os frames antes do render final. Depois da página publicada, registre o link no PRD com <!-- automacao --> na primeira linha do comentário.
<Se houver página de módulo: Atualize a cópia do MP4 em docs/comunicacao/<contexto>/modulo/ e republique a página de módulo.>
```

5. No passo a passo (6), a divulgação entra como item próprio: em qual momento colar cada prompt e a quem mandar o link depois (diretor, usuários do módulo). O envio do link é "precisa de você".
6. **Mensagem de WhatsApp** junto do vídeo: para o mesmo PRD, o plano traz também a linha `/mensagem-prd #<PRD>`, a colar no mesmo terminal de divulgação depois do deploy da última tela (a skill confere o que está em produção). O texto sai pronto para o Pedro copiar e mandar ao diretor e aos usuários do módulo, com o link da página quando ela já existir.

## minhas-issues

- *conta pessoal*: projeto Vercel do Manual (`docs/manual/.vercel/project.json`).
- *decisão de domínio*: o insumo externo costuma ser organograma, número ou resposta do diretor.
- O PRD do leitor aqui é o **PRD do diretor** (o "sim" do Planejamento da Demanda, ADR 0075), reconhecido pelo marcador da Demanda (`prd_do_leitor` no `fluxo.json`).
- *divulgação* (`type:divulgacao`): a pessoa aprova vídeo e página; o resto é `/divulgar`.
- *as três paradas*: migration pelo caminho clicável no Studio, segredo só na tela do Coolify.

## grill-with-docs

Porta A também quando o diretor precisa saber ou quando nasce ou muda página do Manual. Porta B só sem diretor e sem Manual. Dúvida de documentação de serviço externo (ClickSign, Supabase e PostgREST, Coolify, WeasyPrint) vai para a skill `research` em segundo plano. O "porta" é o mesmo do `/ask-pedro` ("Qual porta?").

### PRD do diretor (`/grill-with-docs #N`)

Quando o argumento é uma issue, rode antes da primeira pergunta:

```bash
python3 .claude/skills/to-prd/scripts/prd_do_diretor.py ler <N>
```

O script reconhece o **PRD do diretor** (ADR 0075): a issue que o "sim" do Planejamento da Demanda cria na aba Tecnologia, com o marcador da Demanda e a seção "Ficou em aberto". Se a saída diz "Não é PRD do diretor", leia a issue e siga o grill normal. Se é PRD do diretor:

1. Mostre as Decisões de negócio como **já tomadas pelo diretor**, do jeito que o script imprime, e não repergunte nenhuma delas, nem para confirmar, nem com outra redação. Elas entram no grill como premissa.
2. Comece pelos itens de "Ficou em aberto", um por pergunta, no formato de sempre. Item técnico: você recomenda e o Pedro decide. Item de negócio, que só o diretor sabe: sai marcado "[precisa do diretor]" com a sua sugestão, e o Pedro escolhe entre responder ou levar para a Conversa da Demanda.
3. Depois, só o técnico: módulos, seams, schema e migration, contrato de API, testes, Manual. Problema, Solução e Histórias já estão na issue.
4. Se uma decisão técnica contradiz uma decisão do diretor, pare e diga qual, em uma linha. A decisão dele não se reescreve por conta própria.

Fechamento: a porta já é A e a issue já existe, então não classifique a porta de novo nem crie issue nova. O próximo passo é o `/to-prd`, que completa esta mesma issue (nota "PRD do diretor: completar a mesma issue" do `/to-prd`), e depois o `/to-issues #N`.
