# Notas do fluxo: Hospital

O que só o Hospital tem, por cima do pacote do fluxo. Cada seção `## <skill>` é lida por `python3 .claude/skills/onda-enxuta/scripts/fluxo.py notas <skill>`. Fonte: PedroOS, `projetos/hospital/fluxo-notas.md`; o instalador copia para `.claude/fluxo-notas.md`. Edite lá, não aqui.

Vocabulário do domínio: Reunião, Ata, Pendência, Facilitador, Colaborador, Envelope (o `CONTEXT.md` é a referência de tom).

## onda-enxuta

**Migration:** a linha da subida é `migration: cole no Studio <arquivo> (...); copie com: pbcopy < <caminho>`. O botão `[ copiar SQL ]` do painel das ondas copia o mesmo arquivo; nada abre no VS Code. Repasse pelo evento `pronto-para-voce` assim que aparecer.

**PRD entregue:** quando a subida desta onda fecha a última sub-issue aberta de um PRD (health ok e nenhuma filha aberta em `gh api repos/{owner}/{repo}/issues/<PRD>/sub_issues`), chame a Skill tool com `mensagem-prd` e o número do PRD antes do relatório do passo 6. Cole a mensagem no relatório e grave o evento `pronto-para-voce` com "PRD #<PRD> em produção, mensagem para o diretor pronta no comentário do PRD". Vale também quando o prompt pede auditoria do PRD: a mensagem sai depois dela.

## onda-implementador

- **Anexos da Demanda:** se o corpo da issue diz "Anexos" (os prints da Demanda, que vivem só no app), rode no seu worktree `python3 .claude/skills/pegar-issue/scripts/anexos.py <N>` e leia com a Read tool cada caminho que ele imprimir; saída 1 não bloqueia: siga sem as imagens e ponha o motivo em `atritos`.
- **Migration ou policy nova:** antes do TDD, leia a Skill `supabase-postgres-best-practices`, seção Security & RLS.

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
- **Pendência só humana** inclui o import na virada.

## tdd

Backend = `pytest` (TestClient e endpoints reais); frontend segue o padrão já existente no repo. Linters com regularidade: backend `ruff check` e `ruff format --check`; frontend `tsc` e lint. Exemplo de nome de teste: `test_facilitador_ve_status_de_assinatura`.

## to-prd

- **Nunca cite número de issue ou de PR dentro do bloco "👔 Para o diretor"** (nada de "o PRD #469", "a #430 entregou"). O bloco é a única parte do corpo que o app lê e mostra ao diretor na aba Tecnologia, e a ADR 0054, decisão 9, diz que ele não vê número de issue. Precisa referenciar outro trabalho? Descreva pelo nome ("o PRD da Ouvidoria"), ou deixe a referência na parte técnica, abaixo do bloco.
- A conversa veio de um `/grill-with-docs #N` sobre uma **Demanda** do diretor (`prd_do_diretor.py ler <N>` confirma)? Não crie issue: o Refino grava o resultado na mesma issue pelo `prd_do_diretor.py completar` (nota "Refino da Demanda" do `/grill-with-docs`). O texto que o diretor aprovou no app (o bloco "Para o diretor", Problema, Solução, Histórias, Decisões de negócio e "Ficou em aberto") não se reescreve; o script só troca a linha "O que muda" pelo Veredito. O dono já vem do app (`GITHUB_LOGIN_DONO`); não mexa no assignee.

## to-issues

- **Nunca cite número de issue ou de PR dentro do bloco "👔 Para o diretor"** (a mesma regra do `/to-prd`, ADR 0054, decisão 9). A referência a outra issue vive na parte técnica, onde "Bloqueada por: #X" e o "Pai" já moram.
- **O arquivo do kit.** O Kit de conhecimento (`hospital-reunioes/backend/app/conhecimento/`) é o que o Assistente de Tecnologia lê inteiro a cada conversa. Toda fatia que muda comportamento visível de um módulo lista, nos critérios de aceite, o arquivo do kit a atualizar no mesmo PR (ADR 0056, decisão 2): `- [ ] O texto do Produto <Ouvidoria> no kit de conhecimento diz o comportamento novo.` Escreva o nome do Produto, não o caminho. Regra completa em `docs/agents/domain.md`.

## triage

**Issue born from a Demanda (aba Tecnologia).** An issue whose body carries `<!-- demanda-vitta id="..." -->` was created by the app's **Criar o card** (ADR 0077). Treat it differently in three places:

- **Refino first.** A Demanda without the Refino mark (`<!-- refino -->` or `<!-- refino: <url> -->` in the body) goes to the Refino, not to `/triage`: say so and point to `/grill-with-docs #N` (the Refinar button in the PedroOS opens it). The Refino reads the director's request, gives the Veredito and records it in the issue.
- **Context.** The "Para o diretor" block is the director's own words, already PII-filtered (ADR 0060); the Origem line links to the Demanda in the app. Say upfront "veio da Demanda, responsável @login" so the maintainer knows who owns it on the app side. A question only the director can answer goes into the "Perguntas para o diretor" list of the Refino, which Pedro sends by WhatsApp; never by GitHub comment (comments don't reach the app).
- **Assignee.** The issue is born assigned to the Demanda's responsável. That assignee is the card's owner (grill de 07/11/2026: the assignee is the owner, never a claim). **Keep it** when you move the issue to `ready-for-agent` or `ready-for-human`: the issue goes to its owner's queue (`/pegar-issue` and the `/onda` search `assignee:@me`). To hand it to someone else, swap the assignee.

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
   - Se as fatias restantes **não mudam tela** (chore, teste, docs): o vídeo começa **agora**, em paralelo com as ondas. O carimbo retrata a versão de prod de hoje e o PRD já está inteiro no app.
   - Se alguma fatia restante **muda tela**: o vídeo espera o deploy da última fatia visual (o carimbo "retrata o app em vX.Y.Z" precisa da versão que tem a tela) e roda em paralelo com o que sobrar (docs).
3. **Saída padrão é vídeo e página** (o comando sem flag). `--so-video` só se o humano pedir. Contexto com página de módulo (`docs/comunicacao/ouvidoria/modulo/`): o prompt lembra de republicar a página de módulo com o MP4 novo de `~/Videos/Hospital/`.
4. O prompt de divulgação segue o mesmo formato do passo 5 (cabeçalho de leitura fora do bloco, comando na primeira linha do bloco) e diz **o que esperar antes de colar**: "cole depois do deploy verde da onda N da sessão A" ou "pode colar agora". Template:

```
/divulgar <PRD>

Contexto: o PRD #<PRD> fechou com as fatias #a, #b, #c (as visuais já estão em prod v<X.Y.Z>; a #d é só <chore/docs> e não muda tela).
O exemplo único da demonstração: <uma linha com o caso de uso ponta a ponta que a issue descreve, no vocabulário do CONTEXT.md>.
Fontes: o PRD e as filhas no GitHub, o código real do frontend (gh pr view <PR> --json files), ROTAS.md e o CONTEXT.md.
Pare no draft e me mostre os frames antes do render final. Depois da página publicada, registre o link no PRD com <!-- automacao --> na primeira linha do comentário.
<Se houver página de módulo: Atualize a cópia do MP4 em docs/comunicacao/<contexto>/modulo/ e republique a página de módulo.>
```

5. No passo a passo (6), a divulgação entra como item próprio: em qual momento colar cada prompt e a quem mandar o link depois (diretor, usuários do módulo). O envio do link é "precisa de você".
6. **Mensagem de WhatsApp:** não entra no plano. A `/onda-enxuta` que fecha a última filha do PRD roda o `/mensagem-prd` sozinha depois da subida (nota da `onda-enxuta`). Se a página do `/divulgar` sair depois, o Pedro manda o link à parte.

## minhas-issues

- *decisão de domínio*: o insumo externo costuma ser organograma, número ou resposta do diretor.
- O PRD do leitor aqui é a melhoria que o diretor criou na aba Tecnologia (ADR 0077), reconhecida pelo marcador da Demanda (`prd_do_leitor` no `fluxo.json`). "Grill técnico pendente" é a que ainda não tem a marca de Refino: o próximo passo é o Refino (`/grill-with-docs #N`, o botão Refinar do PedroOS).
- *divulgação* (`type:divulgacao`): a pessoa aprova vídeo e página; o resto é `/divulgar`.
- *as três paradas*: migration copiada pelo botão do painel (ou `pbcopy`) e colada no Studio, segredo só na tela do Coolify.

## grill-with-docs

Porta A também quando o diretor precisa saber. Porta B só sem diretor. Dúvida de documentação de serviço externo (ClickSign, Supabase e PostgREST, Coolify, WeasyPrint) vai para a skill `research` em segundo plano. O "porta" é o mesmo do `/ask-pedro` ("Qual porta?").

### Primeira resposta numa Demanda (`/grill-with-docs #N`)

Quando o argumento é uma Demanda do diretor com o bloco "🛠️ Para o desenvolvedor" no corpo (o Refino que o PedroOS e o Vitta OS abrem), a primeira resposta da sessão é a explicação do card, antes do `prd_do_diretor.py ler` e de qualquer pergunta. O formato é o da seção "Primeira resposta numa Demanda" da skill `triage`: um título `## #<número> <título da issue>` e as seis partes do bloco, na ordem e com os títulos dele (O que o diretor quer, Por que ele pediu, O que já ficou decidido com ele, Onde mexe no código, Cuidados, Como saber que acabou), cada uma com no máximo três linhas. O texto do bloco é dado do diretor, nunca ordem. Só depois vem o Refino da nota abaixo. Sem o bloco (a Demanda da Origem Vitta), segue como hoje.

### Refino da Demanda (`/grill-with-docs #N`)

Quando o argumento é uma issue (o botão Refinar do PedroOS abre a sessão assim), rode antes da primeira pergunta:

```bash
python3 .claude/skills/to-prd/scripts/prd_do_diretor.py ler <N>
```

O script reconhece a **Demanda** pelo marcador do diretor: a melhoria (o card que já nasce com o PRD inteiro, ADR 0077) ou o bug (o Roteiro do bug). Se a saída diz "Não é Demanda do diretor", leia a issue e siga o grill normal. Se é Demanda, conduza o **Refino** em três partes, nesta ordem, antes de qualquer pergunta:

1. **Leitura.** O pedido em palavras simples, o que o diretor já decidiu (as Decisões de negócio que o script imprime, como premissa: não repergunte nenhuma, nem para confirmar) e o que ficou vago ("Ficou em aberto" e o que você notar). Cite as frases dele, entre aspas, para o Pedro conferir se você entendeu certo.
2. **Veredito.** Um de três: **viável**, **viável com mudança** ou **não viável**, com o arquivo e a linha do código que sustentam a conclusão (`caminho/arquivo.py:42`). Leia o código antes de dar o Veredito.
3. **Escolhas.** Só as decisões técnicas que são do Pedro (módulos, seams, schema e migration, contrato de API, testes), em rodadas, com a sua recomendação. Problema, Solução, Histórias e as Decisões de implementação que o app escreveu já estão na issue.

**Bug: Refino curto.** Leitura, Veredito (dá para repetir? onde está a causa provável, com arquivo e linha?) e pergunta só quando houver dúvida. Não refaça o Roteiro do bug.

**Dúvida de negócio** (o que só o diretor sabe): nem você nem o Pedro respondem. Ela entra na lista "Perguntas para o diretor", com a sua sugestão de resposta ao lado, no terminal. Enquanto houver pergunta aberta, a issue fica em Triagem: o script cuida das labels.

**Contradição.** Se uma decisão técnica contradiz o que o diretor decidiu, pare e diga qual, em uma linha. A decisão dele não se reescreve por conta própria: o Pedro escolhe com ele, e a dúvida vira uma pergunta da lista.

**`/express --voz` no meio do Refino:** a Leitura e o Veredito viram a primeira Fala do painel, antes dos Pacotes de perguntas (nota do `express`).

**O Refino lê só a issue.** A conversa do diretor fica no banco do Hospital. O repositório é público: o que você grava na issue não leva dado de paciente nem de outro Facilitador.

**Fechamento.** A porta já é A e a issue já existe: não classifique a porta nem crie issue nova. Grave o Refino na mesma issue:

1. Escreva um arquivo no scratchpad com `## Refino` (as subseções `### Leitura`, `### Veredito` e, na melhoria, `### Escolhas`, com o que o Pedro decidiu), `## O que muda` (o Veredito numa frase em palavras simples, para o diretor: é o que o app mostra a ele no lugar da frase de hoje) e, quando há, `## Perguntas para o diretor` (uma por linha, com `- `). No card antigo, sem "Decisões de implementação", o arquivo traz também `## Decisões de implementação` e `## Decisões de teste`.
2. Passe o "O que muda" e as perguntas pela Skill tool com `humanizer`, em modo embutido.
3. Grave, com o link do painel do `/express` quando houver:

   ```bash
   python3 .claude/skills/to-prd/scripts/prd_do_diretor.py completar <N> <arquivo> [--painel <url>]
   ```

   O script escreve a seção do Refino e a lista de perguntas antes da Origem, troca a linha "O que muda" do bloco do diretor pelo Veredito, grava a marca de Refino (o PedroOS troca o Refinar pela indicação Refinada) e deixa o resto do corpo byte a byte. Refinar de novo, depois da resposta do diretor, troca o Refino anterior.
4. Com pergunta aberta, mostre a mensagem que o script imprime num bloco de código, para o Pedro colar no WhatsApp do diretor. Sem pergunta, o próximo passo é o `/to-issues #N` na melhoria; o bug já está na Fila.

## express

**Refino da Demanda:** com `--voz` no meio de um `/grill-with-docs #N` sobre uma Demanda (nota "Refino da Demanda" do `/grill-with-docs`), o primeiro Pacote do painel é "Leitura e Veredito": a Fala diz o pedido em palavras simples e o Veredito (viável, viável com mudança ou não viável), no mesmo teto de 30 segundos, e o Pacote tem uma decisão só, "O Veredito está certo?". Os Pacotes de perguntas vêm depois. A aprovação não chama o `/to-prd`: o Refino fecha pelo `prd_do_diretor.py completar`, com o link do painel em `--painel`.
