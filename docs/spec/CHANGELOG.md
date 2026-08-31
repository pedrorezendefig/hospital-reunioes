# Changelog Hospital Reuniões

Cronologia de deploys e mudanças importantes em ordem reversa (mais recente no topo).
Prepended pelo `/deploy ship` ao final do ciclo (ou manualmente quando o PR é meta — só skills/docs).

A partir de **v0.2.0** as entradas seguem o formato `## v0.X.Y — DATA — tipo(escopo): descrição`, com bump automático decidido pelo `/ship` (BREAKING > feat > fix/chore). Entradas mais antigas usam o formato `## YYYY-MM-DD HH:MM - tipo(escopo): descrição` — preservadas como histórico, sem retrofit de versão. Esquema completo descrito em [VERSIONING.md](VERSIONING.md).

---

> **Nota de reconstrução (28/08/2026).** As sete entradas abaixo, da v0.80.1 à v0.81.4, foram escritas em lote **depois** dos deploys. Todos subiram por auto-deploy de webhook, sem passar pelo Passo 9 do `/deploy ship`, então o registro ficou parado na v0.80.0 enquanto produção já rodava a v0.81.4. Os dados vêm do git (commit, data, `package.json`) e do GitHub (PR e issue). São entradas curtas e factuais de propósito: a narrativa longa das outras versões não existia para reconstruir, e inventá-la seria pior que a falta.

---

## v0.87.0 - 2026-08-31 18:21 - Onda de três fatias: gate de dono no cadastro de participantes, críticos por área no relatório da Ouvidoria e endurecimento da pseudonimização
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4cc7dac`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.87.0, `db: healthy`; `app.hospitalsaomatheus.cloud` em 200)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4cc7dac
- Issues: [#440](https://github.com/pedrorezendefig/hospital-reunioes/issues/440) · PR [#456](https://github.com/pedrorezendefig/hospital-reunioes/pull/456) / [#441](https://github.com/pedrorezendefig/hospital-reunioes/issues/441) · PR [#458](https://github.com/pedrorezendefig/hospital-reunioes/pull/458) / [#432](https://github.com/pedrorezendefig/hospital-reunioes/issues/432) · PR [#457](https://github.com/pedrorezendefig/hospital-reunioes/pull/457)
- Migration: nenhuma. A última na main continua a `088_ouvidoria_relatorio_entregas.sql`.
- Env var: só o `APP_VERSION` do backend, atualizado para 0.87.0 no Coolify.
- Merge sequencial: v0.86.1 (#456) → v0.86.2 (#458) → v0.87.0 (#457). Um deploy no fim.

Onda AFK de três issues em paralelo, uma por worktree, com checkpoint humano único de merge. A composição foi pedida na mão, não puxada da fila.

**#440, a tomada de conta pelo email.** O `PATCH /participantes/{id}` não tinha gate de router: qualquer pessoa logada trocava o email de qualquer conta, e o email é sincronizado no Supabase Auth, então dava para assumir o Super Admin. O gate ficou por rota, e não como dependency do router inteiro, porque POPs e Ouvidoria consomem `/participantes/me` e `/participantes/setores` com `access_profile = NULL` (ADR 0007): uma dependency de router deixaria as duas áreas sem tela. O PATCH passou a exigir dono da linha ou Super Admin, o `POST` passou a exigir diretor ou gerente (ele provisiona conta de login, mesma autoridade do `DELETE`), e `/aceite/meu-link` ganhou `barrar_desligado`. As rotas abertas de propósito ficaram com o porquê escrito no corpo.

**#432, quantos casos críticos cada área ainda deve.** Cada linha de `pendencias_por_area` ganhou `criticos`, e o PDF quinzenal ganhou a seção "Casos críticos aguardando resposta da área". A decisão de domínio é o universo: `criticos` nasce dentro de `pendentes`, a fila viva, não num terceiro universo de "todo caso crítico não encerrado". Crítico já respondido, ou ainda na triagem sem área decidida, não é cobrança de área nenhuma, e um terceiro universo na mesma resposta daria um número que não casa com a coluna ao lado. Só contagem, nunca lista nominal: o PDF sai do hospital por email, e email é encaminhável (RN-40, ADR 0034 decisão 8). Área com zero crítico não vira linha; zero em todas é impresso por extenso; edição congelada antes desta fatia não ganha a seção, porque ali crítico não foi medido.

**#441, endurecer a pseudonimização gerando grafia em vez de reler código.** Fuzz diferencial contra a main, mais mutação. Cinco raízes de vazamento reproduzidas e fechadas: data de nascimento sem separador depois do conector, protocolo com sequencial que parece ano, protocolo mordendo o meio do CNS, separador de um caractere só em CPF e telefone, e CPF em pontuação torta. Na main vazavam cerca de 1.900 de 40 mil entradas geradas; no fim da issue, zero, com sete residuais que são o limite declarado do intervalo de anos.

**O que a review independente pegou em dois dos três PRs.** Gate do orquestrador (ADR 0035), com o revisor lendo o diff pelo PR e rodando o ataque em vez de só ler. No #456, o gate novo fechou a escrita mas deixou a leitura: `require_acesso_reunioes` solta `me=None`, então um token válido sem linha em `participantes` (alcançável por hard delete) recebia 200 com o diretório inteiro e o email do Super Admin no corpo. Fechado trocando as três leituras pelo gate estrito que já existia. No #458 havia REGRESSÃO: a troca da classe `[.\s/-]` por listas literais perdeu todo espaço não-ASCII, e CPF e telefone escritos com NBSP, que é o caractere que Word e PDF colam, passavam inteiros onde a main mascarava, cerca de 2.900 casos piores por semente. A correção também revelou o mesmo defeito no separador de bloco numérico, anterior à issue, onde o CNS voltava pela metade. Nenhum dos dois aparecia com a suíte verde.

**O que ficou aberto.** [#459](https://github.com/pedrorezendefig/hospital-reunioes/issues/459): qualquer pessoa com papel nas Reuniões, e até token órfão, adiciona ou remove participante de reunião de que não participa, e o `POST` dispara convite por email pelo domínio do hospital. Reproduzido com efeito pelo revisor de segurança, fora do escopo do #456. [#460](https://github.com/pedrorezendefig/hospital-reunioes/issues/460): três traços de teclado CJK ainda deixam identificador atravessar a pseudonimização, mesma família da #441, risco baixo.

**Operação.** Os três PRs bumparam a mesma linha do `package.json` a partir da 0.86.0, então os dois últimos precisaram de merge da main na branch: trocar o número não desfaz o conflito, porque o conflito é a linha ter mudado dos dois lados. O webhook subiu o código novo nos três merges, mas o `APP_VERSION` só entra no `/health` no startup, então o backend precisou de um deploy manual no fim. Durante o ciclo o `fail2ban` da VPS baniu o IP da sessão por uma janela, derrubando produção, Coolify e Studio ao mesmo tempo; passou sozinho.

## v0.86.0 - 2026-08-31 15:12 - Onda de duas fatias: contrato honesto das métricas da Ouvidoria e peças globais de cache, portal do setor e rotas protegidas
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e0a704d`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.86.0, `db: healthy`; `app.hospitalsaomatheus.cloud` em 200 servindo a v0.86.0)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/e0a704d
- Issues: [#431](https://github.com/pedrorezendefig/hospital-reunioes/issues/431) · PR [#455](https://github.com/pedrorezendefig/hospital-reunioes/pull/455) / [#439](https://github.com/pedrorezendefig/hospital-reunioes/issues/439) · PR [#454](https://github.com/pedrorezendefig/hospital-reunioes/pull/454)
- Migration: nenhuma. A última na main continua a `088_ouvidoria_relatorio_entregas.sql`.
- Env var: nenhuma nova. Só o `APP_VERSION` do backend, setado no Coolify **antes** do merge do #455.
- Merge sequencial: v0.85.4 (#454) → v0.86.0 (#455). Um deploy por auto-deploy de webhook.

Onda AFK de duas issues em paralelo, uma por worktree, com checkpoint humano único de merge no fim. As duas são fatias de contrato e de infraestrutura: nada muda na tela do usuário.

**#431, contrato honesto das métricas da Ouvidoria.** Quatro acabamentos aditivos no `GET /ouvidoria/metricas`, todos vindos das reviews do PR #396 e da triagem de 28/08 registrada na #399. O bloco `pendencias_por_area` ganhou `medido_em`, porque ele é sempre a fila de HOJE mesmo quando o período pedido é outro, e um relatório antigo não pode ser confundido com a foto de agora. O carimbo foi para a LINHA e não para um invólucro em volta da lista, porque os relatórios já arquivados guardam esse bloco como lista congelada em `dados` (#345): trocar a forma quebraria a reemissão do PDF deles. Um `fim` no futuro passou a devolver 422, e a guarda ficou depois das estruturais, senão um pedido de dez anos até 2036 responderia "futuro" em vez de "período grande demais". Entrou o bloco `devolucoes: {casos, total}`, lendo `ouvidoria_movimentos` em lotes de 100 ids e só as três colunas de estado, deixando a `observacao` de fora de propósito porque ela carrega a resposta inteira do setor; a leitura degrada para `null`, nunca para zero. E as duas ressalvas foram escritas no contrato: a leitura agregada não registra em `ouvidoria_acessos` (decisão consciente, alinhada à ADR 0034), e o universo é por data de entrada, então o mesmo período responde números diferentes conforme o dia em que é pedido.

**#439, peças globais de cache, portal do setor e rotas protegidas.** O `PREFIXOS_SEM_CACHE` passou a derivar de `settings.api_prefix` em vez de fixar `/api` na mão, porque um prefixo trocado por env transformava o middleware em no-op silencioso. O portal do setor ganhou teste real, em vez de estar coberto só por herança de prefixo. A promessa "inclusive nas de erro" ficou honesta: o `@app.exception_handler(Exception)` mora no `ServerErrorMiddleware`, fora de todo `user_middleware`, então o 500 sem tratamento nunca passa pelo `SemCacheMiddleware`. A decisão foi corrigir a docstring, não carimbar o 500, porque trazê-lo para dentro exigiria embrulhar o app no entrypoint do uvicorn e o corpo desse 500 é a frase genérica do `DETALHE_ERRO_GENERICO`, sem dossiê a proteger. E o `isProtected` do `middleware.ts` passou a casar área e não prefixo de texto: o `startsWith` protegia `/admin-publico` sem ninguém pedir.

**O que a review independente pegou, e que teste verde não pegava.** Os dois PRs passaram por duas rodadas de review do orquestrador (ADR 0035), cada rodada com duas lentes, código e segurança. Cada PR levou um must-fix, e os dois eram testes que provavam menos do que aparentavam.

No #454, trocar a linha 74 do `middleware.ts` por `const isProtected = false;` deixava os 226 testes do frontend **verdes**. A suíte testava a função `isProtectedPath` e nunca a fiação dela dentro do `middleware()` montado: é o padrão "testar a função em vez da fiação" que já apareceu outras vezes neste repo. O custo declarado para consertar ("faltaria mockar o `@supabase/ssr`") estava superestimado, porque a #438 já tinha trazido jsdom e testing-library na onda anterior. O conserto foi um `vi.mock` de umas quinze linhas mais três chamadas ao middleware montado, e o revisor confirmou por três provas independentes que o mock é mesmo consultado. Junto foram embora um `assert` sobre prosa de docstring e o app sintético do teste do 500, que passou a rodar contra o `app.main` prendendo as duas pernas da decisão, o cabeçalho ausente e o corpo genérico.

No #455, o marcador de degradação novo `devolucoes` não tinha entrada em `EFEITO_DA_DEGRADACAO`. Com a trilha indisponível na geração do quinzenal, o PDF que vai à diretoria abriria dizendo "os números que dependem dela não valem", desqualificando números corretos, e o prompt da IA listaria `devolucoes` sob "não medido neste período". **Os dois revisores acharam esse mesmo defeito de forma independente**, um pela lente de código e outro pela de segurança.

**Sobre os testes existentes alterados no #455.** A guarda nova do fim no futuro tornou impossível pedir "agosto inteiro" com o relógio de teste em 26/08, então as duas suítes de métricas tiveram a janela padrão mudada. Isso é exatamente o movimento que costuma esconder regressão, e foi verificado: o revisor comparou mutação base contra PR e provou que nenhuma asserção foi removida ou afrouxada, e que as quatro reescritas mantêm os mesmos números. Onde o mês fechado era o objeto do teste, ele passou a medir depois da virada, com o relógio em setembro.

**Duas ressalvas que ficam abertas, escritas para não se perderem.** A régua compartilhada `DESTINO_DA_DEVOLUCAO` fecha divergência por renomeação do destino, não por mudança da regra: o revisor rodou o mutante de `e_devolucao` ganhando um segundo destino válido no grafo e os 2610 testes ficaram verdes, porque o `.eq` corta antes. O número está certo hoje, mas o comentário em `ouvidoria_estados.py:71-78` promete mais do que a construção entrega. A segunda é a assimetria entre o matcher do Next, case-insensitive, e o `isProtectedPath`, case-sensitive; é pré-existente e o 404 do App Router fecha o buraco hoje. As duas merecem follow-up.

**Correção de registro.** O gate de segurança do #455 afirmou rate limit de `60/minute` na rota `/metricas`. É `15/minute` desde a #429 (`routers/ouvidoria.py:3145`), conferido na fonte antes de repassar. O raciocínio de fundo, de que a sexta leitura agrava o custo por chamada, continua valendo; o número não.

**A corrida de bump aconteceu, e foi resolvida.** O #454 pediu 0.85.4 e o #455 pediu 0.86.0. Mergeado o #454 primeiro, o #455 ficou CONFLICTING no `package.json`. O conflito foi resolvido mergeando `origin/main` dentro da branch e mantendo 0.86.0, com o CI reexecutado e verde antes do merge final. Verificação em produção depois do deploy: `/admin` devolve 307 para `/login` e `/admin-publico` devolve 404, que é o comportamento novo do #439 valendo de verdade.

---

## v0.85.3 - 2026-08-31 13:50 - Onda de três fatias da Ouvidoria: harness de teste de componente, endurecimento das métricas e apresentação do PDF quinzenal
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `ec76191`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.85.3, `db: healthy`; `app.hospitalsaomatheus.cloud` em 200)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/ec76191
- Issues: [#438](https://github.com/pedrorezendefig/hospital-reunioes/issues/438) · PR [#451](https://github.com/pedrorezendefig/hospital-reunioes/pull/451) / [#433](https://github.com/pedrorezendefig/hospital-reunioes/issues/433) · PR [#452](https://github.com/pedrorezendefig/hospital-reunioes/pull/452) / [#436](https://github.com/pedrorezendefig/hospital-reunioes/issues/436) · PR [#453](https://github.com/pedrorezendefig/hospital-reunioes/pull/453)
- Migration: nenhuma. A última na main continua a `088_ouvidoria_relatorio_entregas.sql`.
- Env var: nenhuma nova. Só o `APP_VERSION` do backend, setado no Coolify **antes** do container subir.
- Merge sequencial: v0.85.1 (#451) → v0.85.2 (#452) → v0.85.3 (#453). Um deploy só, por auto-deploy de webhook.

Onda AFK de três issues em paralelo, uma por worktree, com checkpoint humano único de merge no fim. As três são fatias de qualidade: nenhuma muda o que o usuário vê no dia a dia, e duas delas existem para tapar buraco de teste.

**#438, harness de teste de componente no frontend.** O frontend não tinha como testar componente nenhum. Entrou o trio vitest, testing-library e jsdom, e com ele três coisas que só o DOM prova: a marca de sigilo aparecendo na linha do painel da Ouvidoria, o reset do backoff, e a recarga quando a aba volta ao foco. Junto vieram os testes de virada de mês e de ano para o `diaSeguinte`, que travam a versão UTC contra a variante local (a local erra na virada por causa do fuso). O `diaSeguinte` passou a ser exportado de `lib/ouvidoria/painel.ts` para o teste alcançar a função em vez de testar a fiação em volta dela.

**#433, endurecimento das métricas da Ouvidoria.** Três fontes do painel podem degradar sozinhas, `prazos`, `feriados` e `responsaveis`, e nenhuma tinha teste que provasse a degradação isolada. Agora cada uma tem o seu, mais o caso de cascata (as três caindo juntas). O `NAO_CLASSIFICADO`, que era um marcador só para dois campos diferentes, virou `CATEGORIA_NAO_CLASSIFICADA` e `SETOR_NAO_CLASSIFICADO`, com despacho por campo: um marcador preso ao campo dele não pode mais vazar de um ranking para o outro. Fecharam também os dois testes diretos do ramo `minutos_uteis <= 0` de `adiar_vencimento`.

O achado da review independente merece registro, porque muda a leitura da issue. O defeito descrito no item 2 da #433, um "A definir" em `categoria` sumindo do ranking de temas, **já tinha morrido na issue #429**, quando os temas passaram a sair de `tipo_manifestacao`. O ramo `categoria` entregue aqui é código morto preparado, não correção de bug vivo. A única mudança de comportamento viva do #452 é outra: área escrita exatamente "A classificar" deixa de ser descartada. **Nenhum número do relatório do diretor muda hoje.**

**#436, apresentação do PDF quinzenal.** As três tabelas comparativas diziam "Anterior" sem dizer de que janela, então o leitor não tinha como saber o que estava comparando: agora a coluna carrega as datas da janela anterior. A ressalva da fila viva saiu do meio do texto e ganhou caixa própria. O responsável degradado passou a sair como célula "sem dados" em vez de linha vazia. E o `_rotulo_do_setor` traduz `nao_informado` para "Não informado" no PDF e no prompt da IA, na mesma régua do `rotuloDoSetor` do painel: esse era o achado curado pelo humano, e fecha a pendência que estava anotada no `state.json` desde a v0.85.0. Junto foram embora uma fixture com formato impossível, dois testes vácuo refeitos e o gap do `_variacao`.

**A corrida de bump aconteceu, e foi resolvida.** Os três PRs pediram versão colidindo: o #451 e o #453 pediram os dois a v0.85.1. A saída foi mergear um a um e re-numerar em 0.85.1, 0.85.2 e 0.85.3. Os PRs #452 e #453 ficaram CONFLICTING e foram rebasados à mão, escrevendo a versão nova direto no conflito. O merge saiu por `gh api -X PUT .../merge`, porque a árvore principal está em detached HEAD e o `gh pr merge` recusa nessa condição.

**O #452 e o #453 tocaram os dois o mesmo `ouvidoria_metricas.py`**, e os hunks eram disjuntos: aplicou limpo no rebase, e a suíte subiu de 2584 para 2592 testes passando com as duas mudanças juntas.

---

## v0.85.0 - 2026-08-31 11:12 - Onda de tres fatias da Ouvidoria: paginacao, proximos vencimentos e envio honesto do relatorio
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `11240c1`
- Servicos: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.85.0, `db: healthy`)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/11240c1
- Issues: [#430](https://github.com/pedrorezendefig/hospital-reunioes/issues/430) · PR [#446](https://github.com/pedrorezendefig/hospital-reunioes/pull/446) — [#437](https://github.com/pedrorezendefig/hospital-reunioes/issues/437) · PR [#445](https://github.com/pedrorezendefig/hospital-reunioes/pull/445) — [#435](https://github.com/pedrorezendefig/hospital-reunioes/issues/435) · PR [#447](https://github.com/pedrorezendefig/hospital-reunioes/pull/447)
- Migration: `088_ouvidoria_relatorio_entregas.sql`, aplicada a mao no Studio **antes** do merge do #447.
- Merge sequencial: v0.83.1 (#446) → v0.84.0 (#445) → v0.85.0 (#447). Um deploy so, no fim.

Onda AFK de tres issues em paralelo, uma por worktree, com revisao independente do orquestrador em duas lentes e duas rodadas (ADR 0035). **As tres voltaram com must-fix real.** Nenhuma passou de primeira, e nenhum dos achados era ruido.

**#430, paginacao contra o teto do PostgREST.** As leituras integrais do modulo viravam silenciosamente incompletas quando batiam no `PGRST_DB_MAX_ROWS`: numero errado no painel, sem erro na tela. `ler_tudo` le em paginas de 1000 avancando pelo tamanho do lote **recebido**, que e onde o teto age, com a query entrando como fabrica (um builder reaproveitado sairia com dois offsets grudados) e ordenacao por chave unica em cada leitura.

O must-fix da review: `carregar_feriados` ficou de fora, e ela roda **dentro** da propria `listar_protocolos` que o PR acabara de paginar. Com o teto agindo, a listagem saia completa e o calendario voltava cortado, entao o rotulo de prazo de cada linha saia errado, de novo sem erro na tela. O PR consertava o numero e estragava o rotulo no mesmo caminho. Os testes nao pegaram porque o caso da listagem tinha `prazo_area_em: None`.

Duas coisas boas cairam junto. A primeira: **nenhuma das duas camadas do sigilo era provada sozinha**. Remover so o `.eq("sigilo_reforcado", False)` da query, ou so o refiltro em Python, deixava a suite inteira verde, porque uma camada cobria a outra na resposta HTTP. Agora cada uma tem teste proprio, com contraprova, e mutar uma derruba exatamente um teste. A segunda: o `except Exception` largo de `carregar_feriados` engolia o `AttributeError` dos fakes sem `range`, e **quatro arquivos de teste ficavam verdes rodando com o calendario vazio**. O autor achou instalando uma sonda temporaria que re-erguia a excecao.

**#437, proximos vencimentos no painel.** O bloco "Vence amanha" era dia civil, entao vivia vazio toda sexta. Virou "Proximos vencimentos", com os casos mais proximos de vencer em qualquer dia. Junto: o rodape que explica por que "Ja venceu" nao bate com a coluna "Vencidas", o `nao_informado` virando "Nao informado" so na tela, e `calendarioUtilFoiLido` aceitando `null` para a tela parar de presumir que os feriados foram lidos quando as metricas cairam.

O must-fix da review: o titulo do bloco novo saia como `(5)` porque a lista ja chegava cortada, enquanto nos blocos vizinhos o mesmo parentese e o total real. Numa sexta com quinze casos futuros a tela dizia "Proximos vencimentos (5)", e o contador ficaria preso em cinco para sempre. Agora o total e contado antes do corte e o rotulo diz "5 de 15", ou so o total quando nao houve corte. Junto veio o desempate: o caso em triagem nao tem hora, virava texto vazio e subia na frente de quem tem hora no mesmo dia, e com o corte em cinco isso empurrava para fora da tela o caso mais urgente do dia.

**#435, envio honesto do relatorio.** `enviado_em` so nasce de envio real: sem transporte de email configurado, o carimbo nao sai e o motivo gravado e proprio, distinguivel de "o provedor recusou". A coluna `entregas` guarda uma linha por entrega que aconteceu, porque `destinatarios` e um conjunto acumulado e nao diz em qual entrega cada endereco entrou, o que nao responde nada sobre um documento reemitido.

O must-fix da review foi o mais grave da onda, e e o buraco da issue reaparecendo pelo avesso: **o aviso de que o job desistiu de enviar saia pelo proprio email quebrado**. Em producao com a chave do Resend vazia, cinco rodadas batiam o teto, a edicao virava terminal, saia da fila para sempre, e o unico sinal previsto era um email que nao podia sair. Consertar a variavel nao recuperava a edicao. O PR trocava um "enviado" falso por um "desistido" silencioso, e o alvo da issue era justamente o silencio. A raiz era a classificacao: falta de transporte **passa sozinha** no minuto em que a variavel volta, ao contrario da falha que o teto existe para pegar. Agora ela nao consome tentativa, o sinal vivo e `logger.error` mais trilha no `audit_log`, e a edicao entrega sozinha quando a chave voltar.

**ADR 0039**, o Resend como processador externo fora do Brasil. A review de seguranca o reprovou por **subdeclarar**: o texto dizia "sai o extrato, nunca o relato", mas o **nome de quem manifestou** tambem atravessa a fronteira quando o caso nao e anonimo nem sigiloso; o documento chamava o modo mock de "desenvolvimento local", quando basta a chave vazia para producao cair nele e despejar o corpo do email no log do container; e o inventario dizia "sete tipos" com oito na lista, quando os reais sao quatorze. Um ADR que vira base do aviso de privacidade do hospital nao pode errar isso.

**A pegadinha do bump.** O #447 foi rebasado depois que o #445 mergeou, e o rebase **descartou o commit de bump sozinho** (`patch contents already upstream`): as duas branches escreviam a mesma versao final. O GitHub reportava `MERGEABLE / CLEAN`, sem conflito nenhum, e o PR teria entrado mudando zero na versao. Foi preciso re-bumpar a mao para a v0.85.0.

**A pegadinha do APP_VERSION.** O webhook rebuilda no push, mas o backend le `APP_VERSION` **no startup**. Os tres builds automaticos subiram antes da variavel ser atualizada, entao o `/api/health` reportava a v0.83.0 com o codigo da v0.85.0 rodando. Exigiu um redeploy manual do backend depois de sincronizar a env.

---

## v0.83.0 - 2026-08-31 09:17 - Fila de recuperação do relatório quinzenal por estado, com teto, trilha e aviso
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `d863090`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.83.0, `db: healthy`)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/d863090
- Issue: [#434](https://github.com/pedrorezendefig/hospital-reunioes/issues/434) · PR [#444](https://github.com/pedrorezendefig/hospital-reunioes/pull/444)
- Migration: `087_ouvidoria_relatorio_fila_recuperacao.sql`, aplicada à mão no Studio **antes** do merge.

Terceira e última fatia da onda de 28/08. As duas primeiras subiram na v0.82.2; esta ficou segurada três dias por decisão no checkpoint, e o motivo era o schema. Sem as colunas novas, `GET /ouvidoria/relatorios` daria 500, a varredura diária morreria calada, e uma falha de envio quebraria o `_falha` na coluna inexistente, perdendo a edição em silêncio. Ou seja: subir o código antes da migration reproduziria, com gatilho garantido, exatamente o buraco que esta fatia veio fechar.

A fila tinha três furos do mesmo tipo, todos porque ela era varrida por **janela de data** em vez de por **estado**. `ORDER BY periodo_fim DESC LIMIT 3` fazia a quarta edição não enviada sair da janela para sempre: toda rodada relia as mesmas três. Uma edição morta ocupava vaga do lote e empurrava uma viva para fora. E o "exceto a edição do dia" rodava em Python depois do `LIMIT 3` do banco, então nos dias 1 e 16 o lote efetivo caía para 2. Agora a ordenação é `tentativas ASC, periodo_fim ASC` com índice parcial próprio, o filtro do dia foi empurrado para o banco, e a fila gira.

Teto de tentativas com `desistido_em` como estado terminal. O reenvio manual do ouvidor não gasta o teto (é ação humana com o resultado na tela) e continua entregando a edição depois da desistência. Falha e recuperação do job entram no `audit_log`, no mesmo formato que o reenvio manual já usava, sem relato e sem nome.

**Os dois must-fix que a review independente pegou.** O primeiro é o buraco da issue reaparecendo pelo avesso: o aviso de "sem Diretoria ativa" rodava fora de qualquer `try`, entre o `_reivindicar` (que já gravou `enviado_em`) e o `_falha` (que devolve o carimbo). `get_logo_data_uri` levanta `FileNotFoundError` se o PNG faltar na imagem, e nesse caso a edição ficava marcada como entregue sem nunca ter saído por email, sumindo da fila para sempre, sem trilha e sem contador.

O segundo é o preço escondido do teto. Ao bater o limite, o job parava e **nenhum aviso saía para ninguém**; o aviso do item 5, que era o único sinal vivo, calava junto com a desistência. Pior, os textos mandavam usar "o reenvio pelo painel", e essa tela não existe: a rota `GET /ouvidoria/relatorios` não tem consumidor no frontend. Uma quinzena inteira deixaria de chegar à Diretoria em definitivo, por uma porta sem maçaneta. Antes desta fatia o estado era feio (tentava todo dia, para sempre) mas se curava sozinho quando o provedor voltasse. Trocar barulho eterno por silêncio definitivo seria pior. Agora a desistência avisa os admins técnicos no momento em que acontece.

Mais três acertos da mesma review: a instrução do estado terminal parou de ser cortada pelo truncamento em 300 caracteres, o aviso deixou de sair até cinco vezes por manhã (era uma vez por linha reivindicada), e o reenvio manual bem sucedido limpa `desistido_em` e `tentativas`, que antes deixavam a listagem dizendo "entregue" e "desistida" sobre a mesma edição.

Decisão mantida e escrita junto do job: a estreia manda a quinzena já fechada no primeiro 07h após o deploy. É relatório verdadeiro de período fechado, chega uma vez fora do calendário e está tudo bem.

Follow-up conhecido: o estado terminal só é visível pela API enquanto `GET /ouvidoria/relatorios` não tiver tela.

---

## v0.82.2 - 2026-08-28 21:16 - Retenção da Ouvidoria confirma a remoção no Storage e reconfere o estado do caso
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `7a826ef`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.82.2, `db: healthy`)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/7a826ef
- Issue: [#397](https://github.com/pedrorezendefig/hospital-reunioes/issues/397) · PR [#443](https://github.com/pedrorezendefig/hospital-reunioes/pull/443)
- Sem migration.
- Este deploy carregou junto a v0.82.0 (PR [#428](https://github.com/pedrorezendefig/hospital-reunioes/pull/428), sessão paralela), que estava mergeada na main sem ter subido.

Quatro dos nove follow-ups da review do PR #394, a fatia que apaga e anonimiza uma manifestação cinco anos depois do encerramento. `delete_file` devolvia `True` para qualquer `remove()` que não levantasse exceção, mas o Storage relata o resultado arquivo a arquivo no corpo: uma remoção que falhasse em silêncio levava os metadados embora e deixava o binário órfão no bucket, sem ponteiro para ninguém achar depois. `CAMPOS_ESTATISTICOS` cobria metade das colunas da tabela, e os quatro passos destrutivos anteriores ao Dossiê filtravam só por `manifestacao_id`, sem reconferir se o caso continuava encerrado.

**Os dois must-fix que a review independente pegou, ambos regressão do próprio PR.** O primeiro: a lib devolve lista vazia quando o objeto já não está no bucket, então "arquivo ausente" virou indistinguível de "recusa". Um binário que sumisse em qualquer ponto dos cinco anos travava aquele caso para sempre, em toda rodada, e o relato integral, o nome e o contato de quem manifestou ficavam no banco além do prazo. A retenção passaria a falhar em reter menos do que devia, que é o avesso do objetivo. O conserto pareia a remoção do binário com o `delete` da própria linha, anexo a anexo: a ordem "binário primeiro, porque a linha é o único ponteiro" continua valendo dentro de cada anexo, e a rodada seguinte só enxerga anexo cujo binário ainda está lá. O teste roda o passo duas vezes e prova que o caso agora termina.

O segundo: `canal_ponto` tinha entrado na lista do que sobrevive à anonimização, com um comentário citando a migration 067. A migration 084, posterior, diz o contrário com todas as letras, que o ponto do cartaz cruzado com o registro de atendimento reidentifica quem pediu anonimato (issue #375, decisão 5). O campo foi para `CAMPOS_DO_DOSSIE` e agora vai a NULL com o resto. Os outros doze campos preservados foram conferidos um a um e estão certos: `registrado_por` e `validada_por` são o ouvidor, `respondida_por_nome` é gente do hospital, o resto são marcos de relógio.

Mais dois acertos da mesma review: as guardas passaram a conferir `encerrada_em <= corte` e não só o estado (sem isso, um caso reaberto e reencerrado entre a varredura e o passo destrutivo tinha o Dossiê triturado dentro do prazo), e `delete_file` passou a recusar item ilegível dentro da lista, não só lista ilegível.

Os itens 3, 4, 8 e 9 da #397 ficaram como follow-up documentado na própria issue: são decisão de produto (a conversa da Ana que fica órfã quando o ponteiro é apagado) ou infra de teste nova (aplicar o DDL num Postgres de verdade, hoje as migrations são aferidas por grep no texto do SQL).

---

## v0.82.1 - 2026-08-28 21:16 - Métricas da Ouvidoria leem só o que usam e a porta limita em 15/minute
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fa8360d`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (subiu no mesmo build da v0.82.2)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fa8360d
- Issue: [#429](https://github.com/pedrorezendefig/hospital-reunioes/issues/429) · PR [#442](https://github.com/pedrorezendefig/hospital-reunioes/pull/442)
- Sem migration.

Dois acabamentos de proteção de dado e custo saídos da review do PR #396. A leitura de responsáveis pedia `email` e não usava, e `categoria` seguia em `CAMPOS_TUPLA` sem nenhum consumidor desde que os temas passaram a sair de `tipo_manifestacao`. Dado que ninguém lê não tem por que entrar no processo, ainda mais num módulo que trata manifestação de Ouvidoria. `GET /ouvidoria/metricas` tinha herdado `60/minute` dos GETs vizinhos, mas faz cinco idas ao banco e carrega o período inteiro em memória: caiu para `15/minute`. O relatório quinzenal não passa por HTTP, então nada quebrou. Nenhum número dos agregados mudou.

Duas notas que ficaram registradas no PR e não foram alteradas. Tirar o `email` mudou quem o painel de pendências nomeia num caso de borda: um titular vigente cadastrado sem email agora aparece no painel em vez de o painel pular para o gestor, porque o painel não manda nada a ninguém e passou a usar uma função sem o descarte de quem não tem para onde escrever. E `15/minute` é por IP, não por usuário: o hospital sai por NAT e o painel faz polling de 60s, então vale medir depois se a Ouvidoria abrir o painel em muitas máquinas.

Prova por mutação, oito mutantes, um de cada vez, incluindo limite em 16 e em 14 para provar que é 15 e não só que existe um limite. Suíte completa em 2511 verdes.

---

## v0.81.5 — 2026-08-28 09:57 — Desligamento fecha a conta de login e o alerta sem Diretoria acha dono
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `5b472e3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.81.5)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/5b472e3
- Issue: [#415](https://github.com/pedrorezendefig/hospital-reunioes/issues/415) · PR [#427](https://github.com/pedrorezendefig/hospital-reunioes/pull/427)
- Sem migration.

O desligamento era só `ativo = false` na tabela. A conta do Supabase Auth seguia viva, e com ela o refresh token: quem saía do hospital renovava sessão sozinho, para sempre. O PR #414 já barrava essa pessoa nos 11 gates de papel, mas gate é a rede de segurança, não a tranca. A tranca é a conta morrer, e ela não existia.

Agora existe, e gira nos dois sentidos: `definir_login_liberado` bane no Auth e reabre pelo inverso. Ligada nas três portas que escrevem `ativo` **e** no provisionamento, porque nascer desligado também deixava conta viva, que é o mesmo buraco pelo avesso. A falha do Auth não desfaz o desligamento (o vínculo na tabela é a fonte de verdade e já está gravado), mas deixou de morrer no log: avisa o admin técnico, pelo mesmo canal que o segundo achado passou a usar.

Esse segundo achado: `alertar_diretoria_sem_titular` degradava para uma linha de `logger.warning` quando a Diretoria vinha vazia, e o ramo ficou alcançável pelo filtro de `ativo` da issue #403. Num hospital cuja única diretora foi desligada, o alerta de setor sem titular sumia por inteiro. Agora cai no admin técnico, que é quem conserta cadastro.

**O que este ciclo descobriu e não consertou.** Como o autor do diff era o mesmo que rodaria os gates, os três (spec × diff, code review adversarial e segurança) foram para revisores independentes, seguindo o ADR 0035. O de segurança varreu todas as rotas e achou que `participantes.py` e `aceite.py` não têm gate de router: `PATCH /participantes/{id}` grava em **qualquer** participante sem conferir dono e sincroniza o email no Supabase Auth, o que é cadeia de tomada de conta do Super Admin pelo "esqueci minha senha". Alcançável por todo usuário autenticado, não só pelo desligado, e anterior a esta issue. Virou a [#440](https://github.com/pedrorezendefig/hospital-reunioes/issues/440). O que mudou aqui foi o docstring de `barrar_desligado`, que afirmava que essas rotas não expunham dado de terceiros: era falso, e documentar risco aceito pela metade é pior que não documentar.

10 mutantes, 10 mortos. Suíte em 2378 verdes.

---

## v0.81.4 — 2026-08-28 07:12 — Setor da manifestação preso à taxonomia, com backfill do histórico
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `2e78a81`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (`/api/health` confirmou a v0.81.4)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/2e78a81
- Issue: [#419](https://github.com/pedrorezendefig/hospital-reunioes/issues/419) · PR [#424](https://github.com/pedrorezendefig/hospital-reunioes/pull/424)
- Sem migration de schema. Traz o script `backfill_setor_manifestacoes.py` (dry-run por default), **ainda não rodado em produção**.

O `setor` era texto livre nas portas que o gravam, e todo relatório da Ouvidoria agrupa por ele: um erro de digitação partia a mesma área em duas linhas do número que a Diretoria lê. Agora o setor é casado contra a taxonomia e gravado na grafia canônica.

Dois percalços do ciclo, registrados porque custam tempo quando se repetem: os PRs #423 e #424 pediam a **mesma** versão 0.81.3, então o #424 foi re-bumpado para 0.81.4 e a main foi mergeada dentro da branch para resolver o conflito do `package.json`. E o `APP_VERSION` do Coolify precisou ser setado à mão antes do merge, porque merge manual não passa pelo Passo 8.5 do `/ship`.

---

## v0.81.3 — 2026-08-28 06:56 — Pseudonimização apaga nome completo pela base de nomes próprios
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `63b1940`
- Serviços: backend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/63b1940
- Issue: [#412](https://github.com/pedrorezendefig/hospital-reunioes/issues/412) · PR [#423](https://github.com/pedrorezendefig/hospital-reunioes/pull/423)
- Sem migration.

Fecha a lacuna que a v0.79.0 tinha assumido por escrito: nome completo digitado em minúsculas atravessava a pseudonimização inteiro, que é exatamente como a pessoa escreve no celular lendo o QR do cartaz. Era também o motivo pelo qual a IA do relatório mensal só recebe o agregado.

Nota do ciclo: entre esta versão e a anterior subiu o commit `b9ec3b4` (PR [#422](https://github.com/pedrorezendefig/hospital-reunioes/pull/422), issue [#410](https://github.com/pedrorezendefig/hospital-reunioes/issues/410)), que traduziu as skills `/deploy` e `/ship` do MCP morto do Coolify para o CLI. Só skills e docs, sem bump.

---

## v0.81.2 — 2026-08-28 00:30 — Token de aceite sai da notificação do sino
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `86bdfbc`
- Serviços: backend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/86bdfbc
- Issue: [#295](https://github.com/pedrorezendefig/hospital-reunioes/issues/295) · PR [#416](https://github.com/pedrorezendefig/hospital-reunioes/pull/416)
- Migration: `086_aceite_notificacao_sem_token.sql` (UPDATE de dado, corrige `referencia_id` das notificações de aceite). **Aplicação no Studio de produção não confirmada.**

---

## v0.81.1 — 2026-08-28 00:23 — Gates de papel recusam quem foi desligado
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `b77c016`
- Serviços: backend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/b77c016
- Issue: [#309](https://github.com/pedrorezendefig/hospital-reunioes/issues/309) · PR [#414](https://github.com/pedrorezendefig/hospital-reunioes/pull/414)
- Sem migration.

---

## v0.81.0 — 2026-08-27 23:15 — Ponto de escuta: a tela que gera e gere os QR codes dos cartazes
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `66c289e`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/66c289e
- Issue: [#378](https://github.com/pedrorezendefig/hospital-reunioes/issues/378) · PR [#421](https://github.com/pedrorezendefig/hospital-reunioes/pull/421)
- Migration: `085_ouvidoria_pontos_de_escuta.sql` (CREATE TABLE `ouvidoria_pontos`). **Confirmada aplicada** em 28/08: a rota pública `/api/ouvidoria/publico/pontos/{{codigo}}` respondeu do banco.
- ADR [0036](../adr/0036-qr-da-ouvidoria-vira-ponto-de-escuta-cadastrado.md)

---

## v0.80.2 — 2026-08-27 23:08 — Leva de acabamento das portas públicas da Ouvidoria
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `385ce63`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/385ce63
- Issue: [#375](https://github.com/pedrorezendefig/hospital-reunioes/issues/375) · PR [#420](https://github.com/pedrorezendefig/hospital-reunioes/pull/420)
- Migration: `084_ouvidoria_ponto_do_cartaz_anonimo.sql` (UPDATE de dado: apaga `canal_ponto` de manifestação anônima, porque o ponto do cartaz cruzado com o registro de atendimento reidentifica quem pediu anonimato). **Aplicação no Studio de produção não confirmada.**

---

## v0.80.1 — 2026-08-27 22:57 — Quem foi desligado do hospital para de receber alerta com protocolo
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `27db833`
- Serviços: backend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/27db833
- Issue: [#403](https://github.com/pedrorezendefig/hospital-reunioes/issues/403) · PR [#413](https://github.com/pedrorezendefig/hospital-reunioes/pull/413)
- Sem migration.

---

## v0.80.0 — 2026-08-27 22:28 — A Ouvidoria passa a sugerir o que corrigir, e o PRD da inteligência fecha
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `089d7e3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/089d7e3
- Issue: [#346](https://github.com/pedrorezendefig/hospital-reunioes/issues/346) · PR [#417](https://github.com/pedrorezendefig/hospital-reunioes/pull/417), do PRD [#319](https://github.com/pedrorezendefig/hospital-reunioes/issues/319), que **fecha com 7 de 7 fatias**
- Migration: `083_ouvidoria_relatorio_sugestoes_ia.sql` (duas colunas aditivas em `ouvidoria_relatorios`; aplicada no Studio antes do merge)
- Follow-ups abertos: [#412](https://github.com/pedrorezendefig/hospital-reunioes/issues/412), [#418](https://github.com/pedrorezendefig/hospital-reunioes/issues/418), [#419](https://github.com/pedrorezendefig/hospital-reunioes/issues/419)
- ADR [0034](../adr/0034-ouvidoria-centralizador.md) · ADR [0036](../adr/0036-qr-da-ouvidoria-vira-ponto-de-escuta-cadastrado.md) · ADR [0037](../adr/0037-tipo-da-manifestacao-e-lista-fechada-e-decide-o-sigilo.md) · ADR [0013](../adr/0013-tipografia-sem-travessao.md)

**O que mudou.** O relatório do dia 1 deixa de ser uma foto do mês e passa a ser uma análise. Além dos números que o quinzenal já trazia, ele ganha a tendência dos três meses fechados, a evolução das notas do Google e do Reclame Aqui, e uma seção final com três sugestões de ação corretiva escritas por inteligência artificial.

**A decisão que deu trabalho foi o que mandar para a IA.** A issue pedia "resumos dos casos do período". Não foi isso que entrou: a IA recebe o **agregado**, e nenhum relato de manifestante sai do hospital.

Três razões, e a primeira é a que pesa. A fatia anterior (v0.79.0) entregou a pseudonimização com uma lacuna consciente: nome completo digitado em minúsculas atravessa inteiro, e é exatamente como a pessoa escreve no celular lendo o QR do cartaz. Mandar o relato de quarenta casos multiplicaria essa exposição por quarenta. A segunda razão é que o módulo de relatório já tinha decidido isso sozinho: ele declara no próprio código que nenhum caso é identificado, e o módulo de métricas nem lê a coluna do relato. A terceira está escrita no glossário do projeto desde o ADR 0034: nem o relato nem o resumo saem da Ouvidoria, porque os dois carregam a palavra de quem manifestou. Se o responsável do setor, que é gente da casa, não recebe o relato, o provedor de IA também não.

O portão tem três camadas, e a ordem importa: primeiro não mandar texto livre nenhum; depois uma poda mecânica que tira os dois únicos nomes de funcionário do agregado (o titular do setor e o ouvidor que digitou a nota); e só então a pseudonimização, como cinto de segurança, nunca como defesa principal.

**O trade-off, dito na cara:** as sugestões são de gestão, não de caso. A IA não vai apontar um caso específico. Fazer isso exigiria a lacuna de nome resolvida antes.

**A conta.** Uma chamada por mês, cerca de 2.200 tokens, algo como US$ 0,0014 mensais no gemini-3.7-flash. Mandar os relatos custaria vinte vezes mais e traria o risco junto.

**Se a IA estiver fora do ar, o relatório sai mesmo assim**, sem a seção e com um aviso no lugar dela. Seção que some em silêncio lê como "não havia o que sugerir", que é diferente de "não deu para sugerir".

**O que a review pegou.** Dois revisores independentes leram o diff, com o alvo apontado à mão porque a branch vivia num worktree e o gate automático lê a árvore errada. A revisão de segurança liberou depois de tentar refutar o portão campo a campo. A de código bloqueou com um defeito sério: uma falha de leitura da nota externa faria o PDF, assinado pelo hospital e enviado à Diretoria, afirmar que o ouvidor não digitou nota nenhuma em três meses, sem aviso e de forma permanente, tudo por causa de um tempo esgotado de banco. Corrigido, junto de mais seis achados e de cinco testes que passavam sem provar nada.

---

## v0.79.0 — 2026-08-27 22:17 — Pseudonimização entra em produção com os limites dela escritos, não escondidos
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `adcd408`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/adcd408
- Issue: [#342](https://github.com/pedrorezendefig/hospital-reunioes/issues/342) · PR [#395](https://github.com/pedrorezendefig/hospital-reunioes/pull/395), do PRD [#319](https://github.com/pedrorezendefig/hospital-reunioes/issues/319)
- Migration: nenhuma
- Follow-ups: [#412](https://github.com/pedrorezendefig/hospital-reunioes/issues/412) (a lacuna de nome) e [#398](https://github.com/pedrorezendefig/hospital-reunioes/issues/398) (RG, CEP, data de nascimento, placa, CNS, handle)
- ADR [0034](../adr/0034-ouvidoria-centralizador.md) · ADR [0036](../adr/0036-qr-da-ouvidoria-vira-ponto-de-escuta-cadastrado.md)

**O que mudou.** Entrou a rotina que apaga dado pessoal do texto da Ouvidoria antes de qualquer envio a uma inteligência artificial de fora. CPF, telefone, email e número de protocolo saem trocados por marcadores, e essa parte passou por dois ataques independentes sem que nenhum achasse saída.

**Nome é outra história, e é por isso que este deploy vale ser lido.** A regra de nome não cumpre o que a issue pediu. Depois de duas rodadas de revisão mostrarem o mesmo padrão, que cada heurística nova de expressão regular troca um conjunto de furos por outro, a decisão foi parar de iterar e **mergear sendo honesto**, em vez de segurar a parte que funciona esperando uma solução que a ferramenta não dá.

Quatro vazamentos foram medidos e estão escritos no próprio código, com o exemplo de cada um. O pior deles: nome completo em minúsculas, sem a pessoa se apresentar, sobrevive em vinte de vinte casos testados. É exatamente o formato que chega pelo cartaz com QR, onde alguém digita no celular sem maiúscula nenhuma.

Cada um dos quatro ganhou um teste que afirma o comportamento **real de hoje**, ou seja, o nome sobrevivendo, com um comentário explicando que isso é limite conhecido e não o que se deseja. Quem melhorar a regra no futuro vê os quatro ficarem vermelhos, lê o comentário e entende que o vermelho é o sinal certo. Nada de marcar como falha esperada e sumir do relatório: teste que ninguém vê não avisa ninguém.

---

## v0.74.0 — 2026-08-27 00:55 — Ouvidoria ganha os números do período e a retenção de cinco anos
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `0b89cfe`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/0b89cfe
- Issues: [#341](https://github.com/pedrorezendefig/hospital-reunioes/issues/341) · PR [#396](https://github.com/pedrorezendefig/hospital-reunioes/pull/396) e [#343](https://github.com/pedrorezendefig/hospital-reunioes/issues/343) · PR [#394](https://github.com/pedrorezendefig/hospital-reunioes/pull/394), do PRD [#319](https://github.com/pedrorezendefig/hospital-reunioes/issues/319)
- Carona de outra sessão: PR [#393](https://github.com/pedrorezendefig/hospital-reunioes/pull/393) (Espelho da Global Health, elo 1, PRD [#385](https://github.com/pedrorezendefig/hospital-reunioes/issues/385)) e PR [#392](https://github.com/pedrorezendefig/hospital-reunioes/pull/392) (poda dos convênios por especialidade)
- Migration: `079_ouvidoria_retencao_anonimizacao.sql` (carimbo `anonimizada_em`, índice parcial da varredura e o caminho estreito de UPDATE na trilha; aplicada no Studio antes do deploy)
- ADR [0034](../adr/0034-ouvidoria-centralizador.md) · Onda AFK (ADRs 0022, 0029 e 0035)

**O que mudou.** Duas fatias do PRD 319 entraram, as duas de infraestrutura da Ouvidoria: nenhuma tem tela, as duas existem para o que vem depois.

A primeira é o módulo de métricas do período. Ele responde os números de gestão de qualquer intervalo de datas: volume, prazo cumprido por trecho, pendências por área, ranking de tempo de resposta, prorrogação, reincidência, tempo pausado e os cinco temas e áreas mais frequentes. O painel em tempo real e o relatório em PDF consomem essa mesma função, e é isso, não a disciplina de quem escreve as telas, que impede o número do painel de divergir do número do relatório.

A segunda é a retenção. Manifestação encerrada há mais de cinco anos perde os dados pessoais às 04:00 e mantém a estatística. O robô nasce dormindo, porque nenhum caso tem cinco anos ainda, mas a política existe desde o primeiro dia.

**O que a revisão independente pegou.** Onze achados no módulo de métricas e cinco na retenção, em duas rodadas cada. Nenhum quebrava nada: todos saíam como número plausível ou como conformidade aparente.

Os dois piores das métricas erravam a favor da casa. O percentual de triagem subia quanto pior a Ouvidoria fosse, porque caso não triado não tem gravidade, e sem gravidade não tem prazo, e sem prazo saía do denominador: dez casos com três triados no prazo e sete parados sem ninguém olhar liam 100%. E prorrogação aprovada pela Diretoria virava estouro no relatório, porque o prazo conclusivo era recalculado do zero e ignorava o que a operação já tinha concedido. Um terceiro achado era de privacidade: a lista de casos vencidos levava o número de protocolo de denúncia sigilosa para dentro do PDF que vai por email a gestor de área.

Na retenção, o achado central foi que anonimizar o caso não anonimizava nada: o texto da resposta da área continuava vivo na trilha imutável e era servido por rota. Fechar isso exigiu decidir o cruzamento entre "trilha imutável" e "retenção de cinco anos", que a ADR 0034 lista no mesmo parágrafo sem resolver. A saída foi um caminho estreito no banco: o gatilho de UPDATE passa a aceitar zerar apenas a coluna `observacao`, apenas para NULL, e apenas em caso que a política já alcança. O DELETE continua barrado e nenhum usuário autenticado chega lá. O custo declarado é que o histórico de respostas do caso anonimizado fica vazio.

**O freio.** A retenção destrói dado em definitivo, sozinha, de madrugada, sem backup. Ganhou `OUVIDORIA_RETENCAO_ATIVA`, declarada no contrato de deploy e no `.env.example`, porque a guarda do banco usa o relógio do banco e o corte do serviço usa o relógio do container, ambos do mesmo host: relógio adiantado move as duas metades da guarda juntas, e nesse dia o freio é a única defesa que sobra.

**O que não entrou.** A fatia [#342](https://github.com/pedrorezendefig/hospital-reunioes/issues/342) (pseudonimização, a peneira que tira dado pessoal antes do texto ir para a IA externa) parou em `ready-for-human` depois de duas rodadas sem veredito limpo. O PR [#395](https://github.com/pedrorezendefig/hospital-reunioes/pull/395) segue aberto e verde: CPF, telefone, email e protocolo passaram por dois ataques independentes e seguraram. O que não fecha é o nome. Numa matriz de vinte nomes brasileiros reais, dez vazam inteiros no formato mais fácil que existe, e o dano cresce com o dado pessoal do próprio relato. Não é um bug: é a abordagem de reconhecer nome por desenho de texto, que troca um conjunto de furos por outro a cada rodada.

**Nota de operação.** Duas sessões paralelas mergearam na mesma janela. O bump 0.72.0 desta onda foi superado pelo 0.74.0 da outra sessão antes do deploy, e o deploy pegou o topo da main com os quatro PRs juntos. Auto-deploy segue quebrado (o repositório não tem webhook), então os dois deploys foram manuais.

---

## v0.71.1 — 2026-08-26 20:05 — Ouvidoria: a escada de prazo para de mentir e de entupir
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `ab4fa5c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/ab4fa5c
- Issue: [#373](https://github.com/pedrorezendefig/hospital-reunioes/issues/373) · PR: [#384](https://github.com/pedrorezendefig/hospital-reunioes/pull/384) · PRD [#318](https://github.com/pedrorezendefig/hospital-reunioes/issues/318)
- Origem: agrupa e substitui [#366](https://github.com/pedrorezendefig/hospital-reunioes/issues/366), [#364](https://github.com/pedrorezendefig/hospital-reunioes/issues/364) e [#365](https://github.com/pedrorezendefig/hospital-reunioes/issues/365)
- Migration: `078_ouvidoria_escada_de_prazo.sql` (coluna `escalonamento_impossivel_em`, gatilho novo no CHECK, índice parcial da varredura; aplicada no Studio antes do merge)
- ADR [0034](../adr/0034-ouvidoria-centralizador.md), decisão 12

**O que mudou.** A cobrança automática de prazo tinha três defeitos que apareciam em produção, todos na mesma escada. Nenhum deles perdia caso: o que quebrava era a cobrança, não o registro.

O primeiro: a Ouvidoria podia aprovar uma prorrogação muito depois do vencimento, e o prazo novo já nascia no passado. O motor soma dias úteis sobre o prazo vigente, nunca sobre agora, porque o teto de 30 dias úteis é medido da entrada da manifestação. As duas coisas estão certas; faltava a guarda do caso tardio. O setor recebia "prorrogação aprovada" e, minutos depois, "prazo rompido", com gestor e Diretoria subindo na mesma rodada. Agora a aprovação que não concederia prazo nenhum é recusada, e o painel avisa o ouvidor antes de ele confirmar, com o mesmo texto da recusa.

O segundo: um caso cujo setor não tem ninguém cadastrado e cuja Diretoria Executiva está vazia nunca ganhava carimbo. Ele voltava em toda rodada da varredura e, por ser o mais antigo, vinha primeiro. Passando de 200 casos assim, nenhum caso novo entrava na janela de leitura e o escalonamento parava para o hospital inteiro. Agora esse caso ganha carimbo próprio, que o tira da varredura sem queimar degrau nenhum, e o admin técnico é avisado por email. Corrigido o cadastro, a escada volta a subir do degrau em que parou.

O terceiro: quando um setor não tem gestor, o degrau de 24 horas úteis vira um alerta à Diretoria. Esse alerta usava o mesmo gatilho do degrau real de 48 horas, e a guarda de retenção cancela esse conjunto inteiro quando a área responde a tempo. Resultado: a área respondia, o alerta era descartado, e o buraco de cadastro ficava invisível, voltando no próximo caso daquele setor. O alerta agora tem gatilho próprio e texto próprio, que denuncia o cadastro em vez de acusar de silêncio quem respondeu.

**Como foi revisado.** Quatro rodadas de gates, 32 achados corrigidos, cinco deles testes que passavam por vácuo. Três bloqueadores, todos introduzidos pela primeira versão e pegos pela revisão independente: (1) na véspera, o caso era carimbado e saía da varredura mesmo com a Diretoria cheia, matando o escalonamento que subiria um dia depois pelo fallback do gestor; a pergunta certa é sobre os degraus que o caso ainda pode subir, não sobre o que venceu agora. (2) O email mandava o admin cadastrar responsável de setor, rota que exige perfil de Diretoria Executiva, e o caso só trava quando ninguém tem esse perfil: quem recebia o email levava 403. (3) O caso era carimbado mesmo quando o alerta ao admin não era entregue, e saía da varredura para sempre, sem cobrança e sem sinal.

**Trade-off consciente.** Com o provedor de email fora do ar, nenhum caso é carimbado e o entupimento da fila volta enquanto durar a queda. Foi escolha deliberada: a alternativa deixa o caso sem cobrança e sem sinal para sempre. O comportamento atual se cura sozinho na rodada seguinte, e não é regressão contra o que havia antes, onde o entupimento já era permanente.

**Nota de operação.** O auto-deploy por webhook segue quebrado desde a troca de FQDN do Coolify: o repositório não tem webhook nenhum e o GitHub App aponta para o endereço antigo. Os dois deploys foram manuais.

---

## v0.71.0 — 2026-08-26 17:20 — Ouvidoria: a porta do sigilo (taxonomia fechada, elevar, abaixar e a Ana)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a0ff925`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1080s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a0ff925
- Issue: [#372](https://github.com/pedrorezendefig/hospital-reunioes/issues/372) · PR: [#379](https://github.com/pedrorezendefig/hospital-reunioes/pull/379) · PRD [#317](https://github.com/pedrorezendefig/hospital-reunioes/issues/317)
- Migration: `077_ouvidoria_tipo_manifestacao.sql` (coluna `tipo_manifestacao` com lista fechada, backfill que levanta o sigilo junto, aplicada no Studio antes do merge)
- ADR [0037](../adr/0037-tipo-da-manifestacao-e-lista-fechada-e-decide-o-sigilo.md), emenda em prosa ao 0034

**O que mudou.** O sigilo de um caso dependia da palavra que o ouvidor digitava: a regra procurava "denúncia" e "relato de conduta" dentro de texto livre. Um caso classificado como "Assédio moral" não casava com termo nenhum, não elevava o sigilo, e o email de acionamento chegava ao setor acusado com o nome de quem reclamou. Agora o tipo é lista fechada e é ele que decide. O texto livre continua como rótulo humano e não decide nada.

Sem tipo significa não classificado, e o caso não classificado é sigiloso. Isso passou a valer também para o canal da Ana, que antes entrava aberto com um resumo que frequentemente já identificava quem relatou. A saída é a classificação, que ganhou porta própria: sobe e desce o sigilo no mesmo lugar, com movimento na trilha e registro no log de acesso. Denúncia e relato de conduta não aceitam ter o sigilo retirado. Manifestação vinda do QR, que ficava invisível para sempre, volta ao painel de todos quando o ouvidor diz que é elogio. E a consulta de protocolo da API da Ana passou a devolver, de caso sigiloso, só protocolo, estado e data.

**Decisões da execução.** `categoria` não foi renomeada para `categoria_detalhe` como o plano pedia: renomear obrigaria app e banco a subirem no mesmo instante, e o ganho seria só o nome. A Ana não manda o tipo: seria a IA decidindo quem enxerga o caso, contra a decisão 10 do ADR 0034.

**Duas colisões pelo caminho.** Uma sessão paralela criou um ADR 0036 no mesmo dia, também emendando o 0034; como o lint aceita um único `amended_by`, esta fatia cedeu o número e virou 0037, com emenda em prosa (o mesmo que o 0034 fez com o 0031). E o code review independente achou 6 bugs, 2 graves, ambos da mesma raiz: coluna nova faltando numa lista fechada de campos. A reabertura por reincidência escondia qualquer caso reaberto do painel de todo mundo, e a tela de validação apagava o sigilo sozinha. Corrigidos antes do merge, com o contra-teste que faltava.

## v0.70.0 — 2026-08-26 12:45 — Ouvidoria: memória dos ciclos de resposta (histórico e indicador honesto)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a6847d3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1080s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a6847d3
- Issue: [#374](https://github.com/pedrorezendefig/hospital-reunioes/issues/374) · PR: [#376](https://github.com/pedrorezendefig/hospital-reunioes/pull/376)
- Migration: `076_ouvidoria_memoria_ciclos.sql` (coluna `area_estourou_em`, aplicada no Studio antes do merge)
- Pendência humana: [#377](https://github.com/pedrorezendefig/hospital-reunioes/issues/377) (registrar no ADR 0034 que a resposta do setor virou dado imutável)

## v0.69.0 — 2026-08-25 16:52 — Ouvidoria: aguardando manifestante, sem retorno e reincidência
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `7efdcd4`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (900s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/7efdcd4
- Issue #335 · PR #371 · **fecha o PRD #318** (6 de 6 fatias)
- Migration `075_ouvidoria_aguardando_manifestante.sql` aplicada em produção antes do merge

**O que mudou.** Falta dado de quem reclamou, o relógio da área para: o caso vai para `aguardando_manifestante` e, na volta, o vencimento anda para frente exatamente o expediente que ficou parado. O tempo parado fica registrado à parte, para o desconto não esconder lentidão real. Manifestante que some de vez fecha o caso por "sem retorno", depois de duas tentativas de contato registradas e cinco dias úteis de espera, num desfecho que fica neutro no indicador. Manifestante que volta em até 30 dias reabre o caso original marcado como reincidência, sem gerar protocolo novo.

**Decisões que ficam registradas.** Empurrar o vencimento, em vez de descontar só na hora de medir, é o que faz a escada de cobrança parar de cobrar: todo degrau lê `prazo_area_em`. `encerrada_em` NÃO é zerado na reabertura (é o marco T3 do ciclo anterior, que os relatórios do PRD 3 leem). A leitura de "2 tentativas em 5 dias úteis" exige as duas tentativas E cinco dias úteis desde a PRIMEIRA: sem a espera, duas ligações no mesmo minuto liberariam o encerramento.

**As revisões independentes reprovaram o gate e valeram 3 commits de correção.** Dez achados reais, entre eles: a pausa não parava os indicadores da API (só a escada de cobrança escapava, porque filtra status); a pausa aberta não era liquidada no encerramento por "sem retorno", que é justamente de onde ele sai, zerando o relato na espera mais longa do caso; pausar depois do estouro apagava `prazo_rompido_em`, o que fazia de pausar um jeito de limpar a ficha; a reabertura herdava as tentativas do ciclo anterior, deixava o desfecho velho no caso aberto, e despachava ao setor sem reaplicar a elevação de sigilo por categoria (vazando o nome de quem fez uma denúncia). A própria correção introduziu uma regressão, pega na segunda passada: apagar `resposta_da_area`, a única cópia do texto que o setor escreveu.

**Nota de operação.** O webhook do Coolify segue quebrado desde 30/07: o merge na main não rebuilda. Backend e frontend foram disparados à mão, em sequência (build concorrente estoura a memória da VPS).

## 2026-08-25 15:43 — Ouvidoria: devolução por insuficiência com meio prazo
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `bbf1a6b`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1020s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/bbf1a6b

## 2026-08-25 17:26 — Ouvidoria: escada de escalonamento e prorrogação de prazo ponta a ponta
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fe3ca91`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1260s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fe3ca91

## v0.65.1 — 2026-08-25 12:31 — fix(backend): rate limit por IP real atrás do proxy da casa
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `150ef1a`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/150ef1a
- Issue #349 · PR #358 · follow-up #360
- Nota: o backend não enxergava quem visita. Sem `--proxy-headers`, o uvicorn via o IP do container do proxy em toda requisição, e todo limite por IP do app virava um balde único: um cartaz de QR em corredor movimentado fecharia a ouvidoria na sexta pessoa do dia, e o mesmo valia para `/api/aceite/*`. Agora o uvicorn confia no `X-Forwarded-For` vindo só das faixas privadas da rede do Docker (nunca `*`, que faria qualquer cliente escolher o próprio IP). A ouvidoria pública volta ao `get_remote_address` da casa: saem a `key_func` local e o teto agregado do PR #348. Entrou também um teto de tamanho de corpo de requisição para o app inteiro, que antes não existia em POST nenhum.
- Nota de descoberta: o remendo do PR #348 provavelmente **nunca valeu em produção**. O caminho do formulário passava pelo Traefik duas vezes (navegador → Traefik → Next → Traefik → backend) e, na segunda passada, o Traefik reescrevia o `X-Forwarded-For` com o IP do container do Next. O "primeiro salto" que a `key_func` lia já era o container, não a pessoa. A correção real foi tirar o segundo salto: o rewrite do `/api` do Next passa a falar com o backend pela rede interna do Docker (`API_PROXY_URL`, build arg do frontend, com fallback na URL pública).
- Nota de processo: o gate interno de `/code-review` morreu por limite de sessão, mas um dos revisores devolveu 3 achados reais, corrigidos antes do merge. O `docker-compose.yml` sobrescrevia o `CMD` do Dockerfile (por causa do `--reload`) e deixaria o dev local sem as flags, com o defeito reaparecendo só fora de produção. O teto de corpo de 30 MB recusava o lote de Materiais de POP (vários arquivos de até 15 MB num request só), quebrando o contrato daquela rota, que promete recusar arquivo a arquivo; subiu para 100 MB, porque é rede de segurança contra corpo sem fim, não o limite fino. E o piso do uvicorn permitia versão que ignora CIDR em `--forwarded-allow-ips` **em silêncio**, colapsando todos os baldes sem erro de startup; subiu para 0.44.0.
- Nota de infra: o endereço interno só é estável porque o app backend ganhou **Consistent Container Names** na tela do Coolify. Sem isso, o container ganha sufixo novo a cada deploy e o rewrite para de resolver, derrubando todas as chamadas de `/api` do app. Esse toggle e o Custom Internal Name **não são editáveis pela API** do Coolify (422 "field is not allowed"), só pela tela.
- Nota de incidente: ao ligar o toggle, o Coolify criou o container com o nome novo e **não matou o antigo**. Ficaram dois backends saudáveis e o Traefik alternava entre eles, então metade das respostas vinha do código velho (visível pela versão oscilando entre 0.65.0 e 0.65.1 no `/api/health`). Resolvido removendo o órfão à mão, sem downtime. Conferir container duplicado sempre que esse toggle mudar.
- Prova em produção: o endereço interno aparece em `/app/.next/routes-manifest.json` dentro do container do frontend, que é onde o Next grava os rewrites. Suíte: 1469 testes de backend verdes.

## v0.65.0 — 2026-08-25 11:27 — feat(ouvidoria): job de estouro e cobrança PRAZO_ROMPIDO
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `be3c5bf`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (330s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/be3c5bf
- Issue #327 (F6 do PRD #317) · PR #357 · ADR 0034 decisão 7
- Nota: quando o prazo do setor estoura, o sistema cobra sozinho. O job `cobranca_prazos_ouvidoria` roda de 10 em 10 minutos, varre os casos aguardando área, acha os vencidos pelo motor de prazos (calendário útil) e dispara PRAZO_ROMPIDO ao titular e ao substituto vigentes, com o cabeçalho estratificado por gravidade e o link tokenizado do portal do setor (#326): quem é cobrado responde ali mesmo, sem senha. O movimento entra na trilha uma vez por caso, a notificação nasce na fila padrão (janela comercial, retentativa com backoff, botão de reenvio) e a cobrança não sai se a área respondeu entre a fila e a entrega. Registro confirmado no log de startup de produção. Este é só o degrau do vencimento; a escada completa (véspera, gestor, Diretoria) é do PRD #318. Migration 071 aplicada no Studio de produção antes do merge.
- Nota de processo: o `/code-review` levantou 10 achados e o pior era de perder cobrança em silêncio. O carimbo de idempotência (`prazo_rompido_em`) era gravado ANTES de o job saber se havia quem cobrar e se a notificação tinha gravado: setor sem titular vigente, ou deploy do código antes da migration, queimava o caso para sempre, invisível na UI. O carimbo passou para depois e é desfeito quando nenhuma notificação grava. Junto: a varredura filtra o vencimento no banco e cobra em lotes de 25 por rodada (o estouro histórico não vira rajada no Resend), com leitura de 200 para que caso sem responsável, que volta em toda rodada e é sempre o mais antigo, não prenda a fila dos cobráveis; gatilho sem montador levanta erro em vez de virar email de "nova demanda" para quem não devia recebê-lo. A revisão de segurança passou sem achado crítico.
- Nota de corrida: a migration nasceu 069 e foi renumerada para 071 porque o portal do setor (#326) mergeou primeiro e ocupou 069 e 070; o conteúdo não mudou e o SQL já havia sido aplicado. O bump colidiu duas vezes com sessões paralelas (v0.62.0 e v0.64.0 já usadas), e a branch precisou de um rebase e um merge da main. Suíte: 1478 testes de backend verdes.

## v0.64.0 — 2026-08-25 11:35 — feat(ouvidoria): portal do setor por link tokenizado
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e30c325`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (840s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/e30c325
- Issue #326 (F5 do PRD #317) · PR #359 · ADR 0034 decisão 4
- Nota: o responsável do setor passa a abrir a manifestação pelo link do email, no celular, sem senha, e responder ali mesmo. O link segue o padrão do Aceite interno (ADR 0030): token aleatório de 32 bytes, só o hash SHA-256 no banco, preso a uma manifestação e a um destinatário, de uso único e com validade de 30 dias. A página mostra o extrato escrito pelo ouvidor (nunca o relato cru), o prazo em "vence em X dias úteis" e colhe o que a área FEZ para corrigir, com anexos nas mesmas regras do registro manual. A resposta grava o marco T2 e leva o caso a "respondido". No painel, o ouvidor encerra com desfecho e descrição obrigatória, gravando o T3. Migrations 069 (tabela de tokens + colunas T2/T3) e 070 (índice) aplicadas no Studio de produção antes do merge.
- Nota de processo: os três revisores independentes acharam coisas que a auto-revisão não pegaria. O gate spec × diff viu que o T2 era gravado DEPOIS da transição, como best-effort: uma falha na segunda escrita deixaria o caso "respondido" sem a resposta da área, e o titular veria sucesso; a ordem foi invertida, e a página passou a avisar quando um anexo não entrou. O `/code-review` achou o pior: `emitir` apagava o token não usado do mesmo destinatário, e o despacho emite token a cada TENTATIVA de envio, então um retry após entrega não confirmada matava o link que o titular já tinha na caixa de entrada, que passava a responder "link inválido". Corrigido com a migration 070 (o índice único parcial vira índice de busca) e dois testes do caminho de erro. O `/security-review` passou sem achado: lista fechada de campos, sigiloso e anônimo sem identificação, claim atômico sem janela de resposta dupla.
- Nota de corrida: o bump colidiu com a sessão paralela (as duas branches saíram da v0.62.0 e escreveram 0.63.0, e a v0.63.0 já estava deployada sem esta fatia); renumerado para v0.64.0 depois do merge. O build do backend pegou `be3c5bf`, que já trazia a fatia F6 (#357) mergeada um minuto antes, então o código da F6 subiu junto e a sessão paralela levou o `APP_VERSION` para 0.65.0. O frontend desta entrega ficou na v0.64.0. Suíte: 1442 testes de backend e 83 de frontend verdes.

## v0.63.0 — 2026-08-25 05:35 — feat(ouvidoria): motor de prazos com pausa, meio prazo, teto e gatilhos
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `121fb57`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (900s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/121fb57
- Issue #331 (G1 do PRD #318) · PR #356 · ADR 0034
- Nota: primeira fatia do PRD #318 (governança de prazo). O motor de prazos, que é função pura, aprendeu quatro regras: o tempo em que o caso espera o manifestante acumula e é descontado do prazo da área; resposta devolvida por insuficiência dá metade do prazo original contada da devolução, sem zerar o relógio; prorrogação além de 30 dias úteis da entrada é recusada pelo próprio cálculo; e os 4 gatilhos de escalonamento (véspera, vencimento, +24h, +48h) caem no dia útil certo, pulando feriado e fim de semana. Só cálculo: as telas, transições e emails que consomem esses números vêm nas fatias G2 a G6. Sem migration.
- Nota de processo: o gate de spec × diff e o `/code-review` rodaram como revisores independentes e acharam 3 bugs reais que a auto-revisão não pegaria: (1) pausas sobrepostas descontavam o mesmo tempo duas vezes, sempre a favor da área; (2) a escada de cobrança quebrava em gravidade sem prazo (`prazo_area_em` é nullable), o que derrubaria a varredura inteira no primeiro caso crítico do dia; (3) a véspera de um prazo de 4 horas úteis caía dias antes do caso existir. Os três corrigidos com teste antes do merge.
- Nota de corrida: a sessão paralela da issue #326 mergeou o PR #355 antes e levou a v0.62.0. Esta fatia foi re-bumpada para v0.63.0 depois de integrar a main. O deploy da v0.62.0 não tem entrada neste changelog nem no `history.json`: quem o fez é dono desse registro.

## v0.62.0 — 2026-08-25 02:35 — feat(ouvidoria): template de email estratificado por gravidade e sigilo
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `0a546bf`
- Serviços: backend
- Resultado: 🟢 healthy (900s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/0a546bf
- Issue #332 (G5 do PRD #318) · PR #355 · ADR 0034 · spec da Diretoria RN-34 a RN-36
- Nota: todo email da ouvidoria passa a abrir com uma faixa de cor pela gravidade (crítico vermelho, alto âmbar, médio azul institucional, baixo cinza) e com o essencial antes da dobra: protocolo, setor, prazo em data e hora e "vence em X dias úteis". Um único botão de ação por email. Caso sob sigilo reforçado viaja sem o nome de quem manifestou e sem dado clínico. Os hex vieram da spec da Diretoria como default trocável num lugar só, porque a paleta da casa ainda aguarda confirmação do DP. Os dois emails do catálogo (acionamento da área e alerta de setor sem titular) passaram a estender o template novo. Sem migration.
- Nota de corrida: o backend chegou a rodar a v0.62.0 em produção (health verde, `version` 0.62.0) e o build do frontend ainda estava em voo quando a sessão paralela da issue #331 subiu a v0.63.0 por cima. O código desta fatia está em produção dentro da v0.63.0. Este registro foi escrito depois, para a cronologia não ficar com buraco.
- Nota de processo: o revisor independente aprovou sem achado de segurança e apontou 1 médio, o bloco essencial sumia junto com a faixa quando a gravidade vinha fora do catálogo; o gate spec × diff passou apontando que a contagem regressiva não saía no alerta à Diretoria. Os dois corrigidos com teste antes do merge. Suíte do backend: 1425 testes verdes.

## v0.61.0 — 2026-08-25 01:45 — feat(ouvidoria): formulário público com QR setorial e validação com acionamento da área por email
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `554cc57`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1200s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/554cc57
- Issues #323, #325 (PRD #317) · PRs #348, #351 · ADR 0034
- Nota: onda 2 do PRD #317. O cidadão passa a registrar manifestação por um formulário público, sem login, com QR por setor que marca a origem do cartaz. O ouvidor valida, classifica, o prazo é calculado em calendário útil e o responsável do setor recebe email de acionamento com retentativa em 5, 15 e 45 minutos. Migrations 067 e 068 aplicadas no Studio antes do merge.
- Nota de processo: os gates internos de `/code-review` e `/security-review` travaram nas duas fatias (4 de 4 na onda inteira). Cinco revisões independentes foram disparadas por fora e acharam 3 ALTOS que a auto-revisão do autor não pegou: (1) manifestação do canal aberto nascia sem sigilo, e o resumo de uma denúncia apareceria no índice de quem está fora da Ouvidoria; (2) a chave do rate limit confiava no `X-Forwarded-For`, e o teto agregado de 60/min deixava um único cliente fechar o formulário público para o hospital inteiro (subiu para 600); (3) o email do setor levava o relato cru do manifestante, e uma denúncia classificada na validação chegava ao setor denunciado com o nome de quem denunciou. Todos corrigidos e provados com teste antes do merge. O extrato para o setor passou a ser escrito pelo ouvidor, obrigatório em todo acionamento.
- Pendência humana: cadastrar o titular de cada setor, senão nenhum setor fica acionável.
- Follow-ups: #350, #352, #353, #354.

## v0.60.0 — 2026-08-24 23:49 — feat(ouvidoria): registro manual com anexos, motor de prazos em calendário útil e campos de dossiê na API da Ana
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `1294913`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (900s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/1294913
- Issues #321, #322, #324 (PRD #317) · PRs #339, #340, #337 · ADR 0034
- Nota: onda 1 do PRD #317, três fatias em paralelo mergeadas em sequência. O ouvidor passa a registrar pelo app o que chega por telefone, balcão e email, com anexos em bucket privado e URL assinada de 30 minutos; o prazo de cada caso passa a ser contado em calendário útil configurável pela Diretoria Executiva (expediente 08h-17h, feriados cadastrados); a API da Ana aceita os campos opcionais de Dossiê. Migrations 065 e 066 aplicadas no Studio antes do merge. As duas fatias criaram uma migration 065 cada, colisão resolvida renumerando a do #339 para 066. A F7 (#323, PR #348, formulário público com QR) ficou de fora: os gates de spec e segurança dela não foram independentes e aguardam revisão.

## v0.59.0 — 2026-08-24 12:30 — feat(ouvidoria): Manifestação nasce com dossiê, estados, perfis e trilha (F1 do PRD #317, ADR 0034)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `2ec1772`
- Serviços: backend, frontend, supabase (migration)
- Resultado: 🟢 healthy (300s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/2ec1772
- Issue #320 (PRD #317) · PR #328 · ADR 0034
- Nota: protocolos viram Manifestação com Dossiê completo, máquina de estados (RPC transacional), perfis ouvidor/diretoria_executiva, trilha imutável e log de acesso (RLS default-deny). Migrations 055 (pendência antiga do #187) e 064 aplicadas no Studio antes do merge. Review rendeu 7 correções no próprio PR e os follow-ups #329/#330.

## v0.58.2 — 2026-08-20 22:45 — fix(perfil): o badge de role sai da pagina Meu Perfil (ADR 0033)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `b7d29e4`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (270s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/b7d29e4

## v0.58.1 — 2026-08-19 10:44 — A resposta da API da Ana cabe no teto de leitura do cliente
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4f30baf`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (380s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4f30baf
- Issue #314 (PRD #287) · PR #315 · ADR 0032
- Nota: corretiva das fatias #288/#289. Filtro por termo nos quatro GETs e três degraus de resposta escolhidos pelo tamanho, com o degrau declarado no corpo. No degrau `indice` a lista sai como nomes em texto, não objetos: repetir o nome do campo em cada linha fazia convênios a 3x do cadastro estourar. O aviso obrigatório das cirurgias só sobe ao envelope quando há um texto só; com textos diferentes ele volta para a linha.

## v0.58.0 — 2026-08-17 16:34 — Módulo Dados do Atendimento na área admin
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4aa8673`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (740s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4aa8673
- Issue #291 (PRD #287) · PR #308 (módulo, `4b58a82`) · PR #310 (re-bump)
- Nota: a corrida de bump com o ciclo do #307 consumiu o v0.57.0; o módulo só chegou a produção neste v0.58.0.

## 2026-08-14 18:38 — Painel de ouvidoria: lista, prazos e mudança de status
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `d15f51c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (420s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/d15f51c

## 2026-08-14 17:55 — Ouvidoria ponta a ponta na API da Ana (protocolo por sequence)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `bc3b791`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (300s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/bc3b791

## 2026-08-14 17:47 — Exames, cirurgias e convênios na API da Ana
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `ba8b3ad`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (420s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/ba8b3ad

## 2026-08-14 15:55 — Fundação da API da Ana: API key de serviço + consultas particulares ponta a ponta
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `0463a87`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (420s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/0463a87

## 2026-08-14 14:17 — Aceite manual do Super admin no modo interno (onda 4 do PRD #272)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `21e8326`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1100s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/21e8326

## 2026-08-14 13:20 — Aceite interno ponta-a-ponta + reconciliacao com a ClickSign (onda 3 do PRD #272)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e20b37c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1400s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/e20b37c

## 2026-08-14 11:51 — Finalizacao real do Envelope + modo interno de aceites (onda 2 do PRD #272)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `d8543ec`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (1500s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/d8543ec

## 2026-08-14 04:09 — Espinha do nascimento incremental: Registro de Aceites + Pendencias no evento sign (onda 1 do PRD #272)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `b89c4f3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (900s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/b89c4f3

## v0.47.2 — 2026-08-05 23:08 — fix(notificacoes): clique abre o card certo, automenção notifica e menção restrita a quem enxerga (#270)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `6bc03d1`
- Serviços: backend, frontend
- Resultado: 🟢 healthy
- Nota: webhook de auto-deploy quebrado desde 30/07 (troca de FQDN); deploys disparados manualmente via API neste ship
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/6bc03d1


## 2026-07-29 12:52 — Reskin completo do workflow-dashboard com identidade Baseline (navy/Onest): tokens e casca, Producao, Plano/Issues, Mapa, Dominio/Guia (#258-#262)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `dba3ea1`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (6800s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/dba3ea1

## 2026-07-17 15:39 — Onda 3 de bugs avulsos: falha no envio para assinatura vira estado visivel com reenvio (#193) + sincronizar auth ao trocar email do participante (#195)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a67d1cd`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (480s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a67d1cd

## 2026-07-17 14:57 — Onda 2 de bugs avulsos: Pendencia nasce com responsavel resolvido pela Resolucao canonica (#192) + gate de visibilidade nas acoes da Ata (#194)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `598d32d`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (300s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/598d32d

## 2026-07-17 14:32 — Onda 1 de bugs avulsos: webhook ClickSign libera Pendencias antes de ASSINADA (#190) + endpoint legado de super admin escreve access_profile (#191)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `6bfbaa2`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (270s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/6bfbaa2

## 2026-07-17 13:14 — Re-elaboracao de legado: invariantes de qualidade no agente (correcao de portugues + cobertura integral) e botao de arranque na tela de elaboracao
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4af0a49`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (175s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4af0a49

## 2026-07-17 12:44 — Fluxograma do POP abre enquadrado (fit-to-content), palco em destaque e botao ajustar a tela
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `2c3480f`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (380s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/2c3480f

## 2026-07-16 15:54 — Lixeira discreta de novo nos cards do calendario (mensal e semanal)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fdadc89`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (300s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fdadc89

## 2026-07-10 21:21 — Fluxograma de POP: gramática N-ária, fallback do PDF legível e migração do Mermaid (fecha o PRD #210)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `071f572`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (2100s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/071f572

## 2026-07-10 20:02 — Fluxograma de POP com renderer próprio a partir de JSON (ADR 0024)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fa47aad`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (760s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fa47aad

## 2026-07-10 09:56 - v0.41.1 - "Ignorar" no passo de resolução remove o nome da lista exibida da Ata
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `9a684cc`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (backend e frontend em 0.41.1)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/9a684cc
- Nota: Onda 2 do PRD #200 (ADR 0023), fecha o PRD. #203 (fix, PR #208): a ação "ignorar" no passo de resolução passa a remover o nome também de `json_ata.participantes`, reusando o helper `remover_da_lista` de #201. `vincular` e `cadastrar_externo` seguem inalterados. Closes #203.

## 2026-07-10 04:06 - v0.41.0 - Governança da lista de participantes da Ata: editor manual, correção determinística e prompt de extração
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `65a2521`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (backend e frontend em 0.41.0)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/65a2521
- Nota: Onda 1 do PRD #200 (ADR 0023), ciclo /onda com agentes paralelos em worktrees. #201 (feat, PR #207) editor manual determinístico de participantes na validação da Ata (excluir/adicionar espelhando `json_ata.participantes` e `reuniao_participantes`, guard do responsável do ADR 0008, helper `participantes_ata_service.py`); #202 (fix, PR #206) correção por IA deixa de reescrever a lista (remove `prune_missing` do `run_correction_pipeline`); #204 (fix, PR #205) prompt de extração não inclui citados. Closes #201/#202/#204. Falta a Onda 2 (#203, ignorar efetivo).

## 2026-07-07 13:40 - v0.40.1 - POPs: Natureza do Setor removida por inteiro (coluna, inferência, endpoint e UI)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `5ed2b4a`
- Serviços: backend, frontend
- Migration: `055_pops_natureza_drop.sql` (PENDENTE de aplicar no Studio de produção; a `054_pops_natureza_backfill.sql` foi deletada do repo sem nunca ser aplicada)
- Resultado: 🟢 healthy (backend e frontend em 0.40.1)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/5ed2b4a
- Nota: fecha o PRD #187 (ADR 0021). Saem services/natureza.py, o endpoint sugerir-natureza, os campos nos schemas/CRUD e toda a UI no SetoresManager. PR #199, Closes #189.

## 2026-07-07 13:13 - v0.40.0 - POPs: Superadmin exclui POP pré-assinatura (cascata com storage e audit log)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `ffc703d`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (backend e frontend em 0.40.0)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/ffc703d
- Nota: DELETE /api/pops/{pop_id} restrito ao Superadmin POPs, permitido só em estados pré-assinatura (409 caso contrário, fail-safe para estado desconhecido); cascata de Versões, Materiais (registros + arquivos no storage) e Devoluções; audit POPS_EXCLUIR_POP; botão lixeira + modal de confirmação sobre AdminModal. PR #198, Closes #185.

## 2026-07-07 13:07 - v0.39.0 - POPs: Elaboração com prompt único ancorado no Material anexado (fim da composição por Natureza)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `bf30e6e`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (backend e frontend em 0.39.0)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/bf30e6e
- Nota: implementa o ADR 0021 (fatia #188 do PRD #187, rollback do ADR 0018). Prompt único com 4 reforços: referência compacta das 3 áreas, interpretação do Setor pelo nome, fidelidade forte ao modelo anexado e Fluxograma obrigatório. A composição por Natureza morre no serviço de IA; a coluna vira inerte até a fatia #189. PR #197, Closes #188.

## 2026-07-07 13:01 - v0.38.1 - POPs: modais no padrão AdminModal (backdrop com blur e fade, sem cinza chapado)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `273cc58`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (backend e frontend em 0.38.1)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/273cc58
- Nota: os 7 modais de POPs ganham o acabamento do AdminModal (blur sutil + fade-in), refactor puramente visual sem tocar handlers. PR #196, Closes #186.

## 2026-07-04 15:08 - v0.38.0 - POPs: Natureza inferida pelo nome do Setor, pré-preenchendo o cadastro como a sigla
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `cc1f867`
- Serviços: backend, frontend
- Migration: `054_pops_natureza_backfill.sql` (a aplicar no Studio; re-infere os Setores existentes, o código não depende dela)
- Resultado: 🟢 healthy (backend e frontend em 0.38.0, 222ms; deploy via webhook, MCP Coolify autenticado; frontend de primeira)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/cc1f867
- Nota: fecha o PRD #167 (ADR 0018). Deep module `inferir_natureza` (heurística por palavra-chave, casamento por palavra inteira) mais endpoint de sugestão e pré-preenchimento com debounce e guarda de resposta fora de ordem. PR #179, Closes #173.

## 2026-07-03 18:18 - v0.37.0 - POPs: bloco de apoio da Elaboração (biossegurança, RDC sanitária, ABNT, resíduos)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `ca22757`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (0.37.0; deploy via webhook; frontend de primeira, sem OOM)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/ca22757
- Nota: o bloco de apoio deixa de ser esboço e ganha o corpo de normas (sanitárias da ANVISA, biossegurança e EPI, ABNT, gerenciamento de resíduos, interface com a CCIH). PR #177, Closes #172.

## 2026-07-03 18:08 - v0.36.0 - POPs: bloco administrativo da Elaboração (CLT, eSocial, faturamento, compras)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `576f06b`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (0.36.0; o frontend subiu no retry após OOM de build concorrente na VPS)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/576f06b
- Nota: o bloco administrativo ganha o corpo de normas (CLT e DP, eSocial, convenções coletivas, ciclo de faturamento e glosa, compras com segregação de funções e alçada). PR #178, Closes #171.

## 2026-07-02 21:46 - v0.35.0 - POPs: Natureza no Setor e Elaboração com prompt composto por Natureza (assistencial idêntico)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `bceb720`
- Serviços: backend, frontend
- Migration: `053_pops_natureza_setor.sql` (aplicada no Studio de produção antes do merge)
- Resultado: 🟢 healthy (deploy via webhook; MCP Coolify off, APP_VERSION pendente em 0.34.4)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/bceb720
- Nota: verificação de versão por HTTP limitada (openapi off, APP_VERSION defasado); confirmação positiva da feature depende de login. PR #176, Closes #170.

## 2026-06-26 18:56 — Seletor de participantes do calendario volta a achar Colaborador sem login (corrige exclude_self que sumia com auth_user_id NULL)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `bba0d6c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (248s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/bba0d6c

## 2026-06-26 15:33 — Os 3 modais inline restantes deixam de afundar: portados pro body via <ModalPortal> compartilhado
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `7412aff`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (284s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/7412aff

## 2026-06-25 15:58 — Modal de confirmação deixa de afundar no meio da página: centraliza na viewport via portal e sobe pra z-[300]
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `1961fa7`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (225s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/1961fa7

## 2026-06-19 16:53 — Ata sem assinatura (APROVADA) em verde clarinho no calendario e no detalhe, distinta do verde da assinada
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `0b4bfbe`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (310s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/0b4bfbe

## 2026-06-17 16:52 — Leva de 6 features: POPs com seções dinâmicas, markdown e fluxograma Mermaid, papéis editáveis, voz na correção de Ata e menu Reuniões e metas
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `5909aac`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (340s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/5909aac

## v0.32.0 (2026-06-15): acesso aos POPs pela tela de Usuários

- Conceder/revogar o acesso aos POPs (`perfil_pop`) agora acontece na edição do usuário, na tela de Usuários: o Super Admin de Reuniões administra os dois eixos de acesso num lugar só. (#148)
- Autoridade de concessão unificada (ADR 0014): o endpoint de `perfil_pop` passa a aceitar Super Admin de Reuniões OU Superadmin POP, preservando a ortogonalidade de acesso do ADR 0007 (administrar ≠ acessar).
- Aposenta o bootstrap manual do primeiro Superadmin POP (#128): nasce pela própria UI.
- Deploy: backend + frontend, healthy.

## v0.31.0 (2026-06-15): sem travessão + DS Select

- Tipografia: removido o travessão de toda superfície que o usuário vê e gera (UI, PDFs de Ata e POP, emails) e da saída da IA (sanitizador determinístico + regra nos prompts); lint no CI trava regressão. (#136, #137, #138, #139)
- DS Select: novo dropdown de seleção única com fundo branco e acessibilidade de teclado; os selects nativos foram trocados por ele. (#140, #141)
- Decisões: ADR 0012 (DS Select sem select nativo), ADR 0013 (saída da IA sem travessão).
- Deploy: backend + frontend, healthy. PRDs #134 e #135.

## 2026-06-15 15:13 — Autocomplete de Setor e sigla pré-preenchida ao criar Setor (POPs) (#132)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4384d63`
- Serviços: frontend, backend
- Resultado: 🟢 healthy (205s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4384d63

## 2026-06-12 17:10 — RLS default-deny nas tabelas POPs das migrations 045–048 (#112)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `c21a031`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (186s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/c21a031

## 2026-06-12 16:07 — POPs L1: ClickSign, publicação e Biblioteca — fim do ciclo (#87)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e10d63f`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (540s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/e10d63f

## 2026-06-12 15:28 — Materiais de referência na elaboração de POP: upload múltiplo lido ativamente pelo agente.
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fff93fb`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (215s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fff93fb

## 2026-06-12 14:44 — Revisão e Validação de POP: aprovar/devolver com comentários e retorno direto a quem devolveu.
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `89d1db9`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (170s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/89d1db9

## 2026-06-12 14:28 — POPs L1: PDF institucional — 11 seções com fluxograma CSS (#86)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `cf251ae`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (180s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/cf251ae

## 2026-06-12 12:44 — POPs L1 — elaboração: tela POP vivo com chat do agente e rascunho persistente (#83)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `35ac48b`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (207s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/35ac48b

## 2026-06-12 09:47 — POPs L1 — criar POP: formulário institucional, código travado e lista por estado (#82)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `fee2157`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (223s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/fee2157

## 2026-06-12 00:04 — POPs L1 — fundação de acesso: Setores, perfil POP e área /pops (#81)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `7fd3159`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (142s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/7fd3159

## 2026-06-11 23:46 — Conclusão da Ata Guiada: revalidação server-side dos vínculos + upsert do roster (#80)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e55a353`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (176s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/e55a353

## 2026-06-11 22:58 — Resolução ao vivo no chat da Ata Guiada: agente enxerga candidatos, quadro mostra vínculo (✓) (#79)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `3fd4995`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (135s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/3fd4995

## 2026-06-11 22:01 — Serviço de Resolução de responsável: roster primeiro, vínculo determinístico (#77)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `58a2795`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (167s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/58a2795

## 2026-06-11 21:41 — Vínculo do responsável honrado fim a fim: dropdown da validação grava, liberação respeita
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `43bc069`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (163s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/43bc069

## 2026-06-11 17:57 — Calendário: verde consistente de concluído + lixeira discreta no hover
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `9adfa62`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (176s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/9adfa62

## 2026-06-11 17:38 — Ata Guiada conclui e gera pendências num clique
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `2e84450`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (210s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/2e84450

## 2026-06-11 14:56 — documento de apoio na Ata Guiada (contexto sob demanda)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `21906cb`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (206s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/21906cb

## 2026-06-11 14:31 — correção por apontar seção (⌖) na Ata Guiada
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `4b42056`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (269s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/4b42056

## v0.16.0 — 2026-06-11 — feat(reunioes): Ata Guiada em tela dedicada (ata viva + chat texto/voz)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `9bb9dd3`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (174s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/9bb9dd3
- PR: https://github.com/pedrorezendefig/hospital-reunioes/pull/60 (Closes #57)

## 2026-06-11 03:30 — Ata Guiada F4 - distincao visual (badge metodo_geracao) + esconder acoes por Transcricao
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `d078493`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (152s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/d078493

## 2026-06-11 02:59 — Ata Guiada F3 - ditar o relato por voz (hook useGravacaoVoz)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a99319c`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (177s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a99319c

## 2026-06-11 01:46 — Ata Guiada F2 - IA hibrida real do agente (OpenRouter)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `f11ce59`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (136s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/f11ce59

## 2026-06-11 01:00 — Ata Guiada — esqueleto + persistência (IA mock)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `18c3454`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (159s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/18c3454

## v0.11.0 — 2026-06-10 — feat(notas): multi-select estilizado de participantes

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#46](https://github.com/pedrorezendefig/hospital-reunioes/pull/46) · Issue: [#43](https://github.com/pedrorezendefig/hospital-reunioes/issues/43)
- Commit: `25a670b`
- Resultado: 🟢 healthy (backend 42s, frontend 214s)

**Resumo:** Segunda fatia das correções da **Nota** (PRD #42) — troca o `<select>` nativo de "Adicionar do cadastro…" (dropdown preto do SO) por um **dropdown estilizado com busca + multi-seleção**, alinhado ao design. Novo componente `RosterCadastroSelect` (picker controlado: reusa o vocabulário visual do `MultiSelect`, **não** guarda chips — a fonte da verdade segue sendo o roster acima; marca vários com ✓ e o dropdown fica aberto; fecha por clique-fora/Escape). No `notas/page.tsx` o `<select>` vira o componente, com `toggleRosterCadastro` reusando `adicionarRosterCadastro`/`removerRoster`; o fetch de participantes sobe pra `limit=200` (antes cortava em 50, escondendo parte do cadastro da busca). Campo "Ou nome avulso (externo)…" e chips âmbar **intactos**. Só **frontend** (backend rebuildou no-op por `watch_paths=null`). **Gates:** code-review high (sem achados — `tsc --noEmit` + `next build` verdes; sem `overflow-hidden` no card → dropdown não clipa), security-review N/A (não toca auth/permissões/schema/env), CI 3/3. `APP_VERSION` 0.10.1→0.11.0. Health pós: backend 200 `version:0.11.0` (`db:healthy`, 120ms), frontend 200 (100ms). **Verificação visual manual pendente** (fatia visual — conferir logado no app).

## v0.10.1 — 2026-06-10 — fix(backend): transcrição da Nota via OpenRouter + OpenRouter-only

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#45](https://github.com/pedrorezendefig/hospital-reunioes/pull/45) · Issue: [#44](https://github.com/pedrorezendefig/hospital-reunioes/issues/44)
- Commit: `c6896bf`
- Resultado: 🟢 healthy (backend 127s, frontend 181s)

**Resumo:** Conserta o **"Gravar voz"** da Nota (#35), que falhava 100% com **502** — a transcrição era enviada como multipart do SDK OpenAI, mas o OpenRouter espera um corpo **JSON com o áudio em base64**. Agora `transcricao_service.transcrever` chama `POST {OPENROUTER_BASE_URL}/audio/transcriptions` via **httpx** com `{model, input_audio:{data:<base64>, format}, language:"pt"}`, autenticado com a `OPENROUTER_API_KEY`, e lê o texto do campo `text` (áudio segue **não persistido**; interface `transcrever(audio, formato) → texto` inalterada; falha real → `TranscricaoIndisponivelError` → 502 com aviso de digitação). De quebra, torna o projeto **100% OpenRouter**: remove a chave e o **fallback automático da OpenAI** dos serviços de IA (ata, chat de correção, extração, transcrição) — `_llm_provider` vira `openrouter`/`mock` e `chat_correcao`/`_chamar_llm` perdem o failover (erro claro, sem fallback); no painel admin a integração "OpenAI" vira **"OpenRouter"** (status pela chave + teste de conexão no endpoint autenticado `/key`); `OPENAI_API_KEY`/`LLM_FALLBACK_MODEL` saem de `config.py`, `.env.example`, `supabase/config.toml`, `project.json` e do **Coolify** (deletadas via MCP — 2 ocorrências cada). O **pacote pip `openai` permanece** (é o cliente usado pra falar com o OpenRouter em chat). **Testes:** `test_transcricao_voz_nota` reescrito p/ o contrato base64 (mock de `httpx.post`, valida endpoint/payload/headers/erros); testes de IA ajustados (sem chave/fallback OpenAI) — **315 passam**. **Gates:** code-review high (1 achado refutado — `parsed` só é lido após o `return` do `except`), security-review (sem vulnerabilidade; PR reduz superfície de ataque), CI 3/3. `APP_VERSION` 0.10.0→0.10.1. Health pós: backend 200 `version:0.10.1` (`db:healthy`, 126ms), frontend 200 (185ms).

## v0.10.0 — 2026-06-09 — feat(notas): comando por voz na Nota

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#41](https://github.com/pedrorezendefig/hospital-reunioes/pull/41) · Issue: [#35](https://github.com/pedrorezendefig/hospital-reunioes/issues/35)
- Commit: `71c7325`
- Resultado: 🟢 healthy (backend 50s, frontend 170s)

**Resumo:** Quarta fatia da **Nota** (#31) — ditar a Nota por **voz**, o uso-canônico. No editor, o Facilitador grava um áudio (MediaRecorder), ele é transcrito e o **texto cai editável no corpo** para revisar antes de salvar (não cria a Nota sozinho). **Backend:** módulo profundo `transcricao_service.transcrever(audio, formato) → texto` reusa a chave/billing do Pipeline (`_get_llm`) chamando `/audio/transcriptions` do OpenRouter com `gpt-4o-mini-transcribe` (default `openai/gpt-4o-mini-transcribe`, `language=pt`); endpoint `POST /notas/transcrever` (UploadFile, autenticado) — áudio **não é persistido** (bytes em memória → texto), teto de 25 MB (413), `anyio.to_thread` pra não bloquear o event loop, falha → 502 com aviso de fallback. **Frontend:** botão "Gravar voz" no editor (estados gravando/transcrevendo, microfone liberado no cancelar, `AbortController` cancela transcrição em voo ao fechar). **Testes:** 11 novos com OpenRouter 100% mockado (299 total). **Gates:** code-review (6 achados corrigidos pré-merge — MIME `;codecs`, prefixo do modelo, vazamento de microfone, limite/anyio, race), security-review (sem achados), CI 3/3. `APP_VERSION` 0.9.0→0.10.0. Health pós: backend 200 `version:0.10.0` (`db:healthy`), frontend 200 (1.2s).

## v0.9.0 — 2026-06-09 — feat(notas): Extração de Pendências por IA (propõe-confirma) + roster

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#40](https://github.com/pedrorezendefig/hospital-reunioes/pull/40) · Issue: [#34](https://github.com/pedrorezendefig/hospital-reunioes/issues/34)
- Commit: `60d6fc9`
- Resultado: 🟢 healthy (backend 187s, frontend 340s)

**Resumo:** Terceira fatia da **Nota** (ADR 0004) — a mágica central: a partir do corpo, a **IA propõe** Pendências que o Facilitador revisa e **confirma** antes de criar (a confirmação é a guarda contra alucinação). **Backend:** migration `043` cria `nota_participantes` (roster: Colaborador do cadastro **ou** nome avulso, CHECK de origem única + unique por Nota) — aplicada manualmente no Studio **antes do merge**; endpoints `GET/PUT /notas/{id}/participantes` (acesso herda a Nota) e `POST /notas/{id}/extrair-pendencias` (propõe sem persistir; Secretária 403, alheia/arquivada 404, IA fora → 502); módulo profundo `extracao_pendencias_service` reusa o passo de estruturação JSON do Pipeline (OpenRouter + fallback OpenAI), casa responsável **roster-first** → cadastro (externo fica só como nome) e converte prazo de linguagem natural ("sexta", "semana que vem") com DATA BASE injetada + parse determinístico; 2 prompts novos; `_find_participante` passa a devolver `nome_completo` (aditivo). **Frontend:** editor da Nota com "Quem participou" (chips cadastro/avulso), botão ✨ de extrair e painel de propostas editáveis (descartar individual, confirmar em lote via endpoint da fatia #33). **Testes:** 16 novos com LLM 100% mockado (288 total). **Gates:** code-review (1 achado corrigido — docstring desatualizada, reincidência do PR #37), security-review (nenhuma vulnerabilidade), CI 3/3. `APP_VERSION` 0.8.0→0.9.0. Este deploy substituiu o `a105587` (PR #39, conversor PDF/DOCX, sessão paralela) minutos depois — leva as duas features. Health pós: backend 200 `version:0.9.0` (`db:healthy`, 104ms), frontend 200 (122ms).

## 2026-06-09 18:12 — Conversor PDF/DOCX → Markdown para Super Admins (sem tokens de IA)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `a105587`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (231s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/a105587

## v0.8.0 — 2026-06-09 — feat(pendencias): Pendência com origem Nota (add manual)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#37](https://github.com/pedrorezendefig/hospital-reunioes/pull/37) · Issue: [#33](https://github.com/pedrorezendefig/hospital-reunioes/issues/33)
- Commit: `28a6347`
- Resultado: 🟢 healthy (backend ~48s, frontend ~221s)

**Resumo:** Segunda fatia da **Nota** (ADR 0004) — a **Pendência** passa oficialmente a ter **duas origens**: Reunião terminal (ASSINADA/APROVADA) ou **Nota**, via add manual do Facilitador (descrição, responsável escolhido do cadastro, prazo). **Backend:** migration `042` adiciona `pendencias.id_nota` (FK → notas, ON DELETE CASCADE) + CHECK de origem única `(id_reuniao IS NOT NULL) <> (id_nota IS NOT NULL)` + índice do FK — aplicada manualmente no Studio de produção **antes do merge**. `pendencia_service` refatorado: núcleo compartilhado `_inserir_pendencias` (IDs `A###` na sequência global) usado por `liberar_pendencias` e pelo novo `criar_pendencias_de_nota` (idempotente por conteúdo; responsável resolvido da fonte canônica). Endpoint `POST /notas/{id}/pendencias` (autor ou Super admin; Secretária 403; 404 anti-enumeration; Nota arquivada não aceita). Visibilidade origem Nota nos pontos que assumiam `id_reuniao`: GET/PATCH/list/stats de pendências e os 3 endpoints de comentários (helper `nota_pertence_ao_participante`); contador `acoes_concluidas` só com Reunião de origem. **Frontend:** form de add manual na página de Notas (descrição + responsável do cadastro + prazo); painel, kanban e modal exibem a origem Nota graciosamente. **Testes:** 15 novos (272 total). **Gates:** code-review (1 achado corrigido — docstring desatualizada), security-review (1 MEDIUM corrigido — gate uniforme da Secretária no add manual), CI 3/3. `APP_VERSION` 0.7.0→0.8.0. Health pós: backend 200 `version:0.8.0` (`db:healthy`, 168ms), frontend 200 (1.9s).

## v0.7.0 — 2026-06-09 — feat(notas): CRUD, histórico e acesso da Nota

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#36](https://github.com/pedrorezendefig/hospital-reunioes/pull/36) · Issue: [#32](https://github.com/pedrorezendefig/hospital-reunioes/issues/32)
- Commit: `b96b57a`
- Resultado: 🟢 healthy (backend ~179s, frontend ~249s)

**Resumo:** Fatia fundadora da **Nota** (ADR 0004) — entidade leve e **paralela** à Reunião, para registrar conversas, feedbacks e eventos sem a cerimônia Reunião → Transcrição → Ata → ClickSign. Esta fatia entrega o núcleo: **CRUD + histórico + acesso** (sem roster de Participantes, Pendências ou voz — fatias seguintes). **Backend:** migration `041` cria a tabela `notas` (`id` UUID, `corpo`, `autor_id` → participantes, `created_at`/`updated_at`, `deleted_at`; índice parcial das vivas; RLS default-deny) — aplicada manualmente no SQL Editor do Supabase Studio de produção **antes do merge** (Postgres self-hosted não exposto; gate de migration agora nas skills). Router `/notas` (`POST`, `GET` histórico ordenado por mais recente, `GET/PATCH/DELETE {id}`) com acesso **espelhando a Reunião**: autor vê só as suas, Secretária e Super admin veem todas; editar/arquivar por autor ou Super admin; `404` anti-enumeration para quem não pode ver; arquivar é **soft-delete** (`deleted_at`), sem hard-delete. **Frontend:** rota `/notas` (histórico + editor de corpo + arquivar) + link na Sidebar. **Testes:** 8 cobrindo os 6 critérios de aceite (257 total). **Gates:** code-review (5 finders + verificação; 2 fixes aplicados — fecha janela de race no `UPDATE` e cobre `DELETE` da Secretária), security-review (limpo — sem SQL injection, authz/IDOR correto, RLS ok, sem XSS), CI 3/3. `APP_VERSION` 0.6.2→0.7.0. Auto-deploy via webhook no merge (`watch_paths=null` rebuilda os dois). Health pós: backend 200 `version:0.7.0` (`db:healthy`), `/api/notas` 401 sem auth (rota viva), frontend 200 e `/notas` 307 (redirect login).

## 2026-06-05 20:11 — Email editado pelo admin agora vale para o login (sincroniza Supabase Auth)
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `94b2288`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (144s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/94b2288

## v0.6.1 — 2026-06-05 — fix(frontend): crash na busca de participante com cargo nulo

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#28](https://github.com/pedrorezendefig/hospital-reunioes/pull/28)
- Commit: `b0ec2bf`
- Resultado: 🟢 healthy (frontend ~181s, backend ~151s)

**Resumo:** Correção de crash client-side ao adicionar participante. Ao abrir **"Adicionar participante"** numa reunião existente e começar a digitar no campo "Buscar por nome ou cargo...", o app quebrava com *"Application error: a client-side exception has occurred"*. Causa: o filtro de busca em `reunioes/[id]/page.tsx` chamava `.toLowerCase()` direto em `cargo`, que é nullable no backend desde a migration `037` (secretárias não têm cargo hospitalar). Com o campo vazio o short-circuit do `||` (`nome_completo.includes("")` é sempre `true`) escondia o problema; ao digitar um termo que **não casava o nome** de um colaborador com `cargo` nulo, o JS avaliava `null.toLowerCase()` → `TypeError`. Fix mínimo (2 linhas): null-coalescing `(p.cargo ?? "")` no filtro + tipo da interface `ParticipanteCadastrado` alinhado ao backend (`cargo: string | null`), que com `strict:true` passa a exigir o null-check — fechando a defasagem aberta desde a `037`. Sem migration. Gates: code-review (4 revisores independentes, sem issues), CI 3/3 (backend tests, frontend lint+tsc, docker build), security-review N/A (diff só `.tsx`, não-sensível). `APP_VERSION` 0.6.0→0.6.1. Auto-deploy via webhook no merge (`watch_paths=null` rebuilda os dois): frontend ~181s, backend ~151s (rebuild sem mudança de código). Health pós: backend 200 em 117ms (`status:healthy`, `db:healthy`, `version:0.6.1` → version match ok), frontend 200 em 142ms.

## v0.6.0 — 2026-06-02 — feat(aprovacao): finalizar Ata sem assinatura (estado APROVADA)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#27](https://github.com/pedrorezendefig/hospital-reunioes/pull/27) · Issue: [#26](https://github.com/pedrorezendefig/hospital-reunioes/issues/26)
- Commit: `2e9652c`
- Resultado: 🟢 healthy (backend ~215s, frontend ~288s, migration 040 aplicada via Studio)

**Resumo:** Novo caminho terminal na validação da Ata. Além de **"Enviar para assinatura"** (fluxo ClickSign inalterado), o Facilitador agora tem **"Finalizar sem assinatura"**: as Pendências nascem na hora e a Reunião vai direto para o estado terminal **`APROVADA`**, sem Envelope e sem aguardar assinaturas — pensado para reuniões operacionais, onde o valor está em registrar a Ata e disparar as tarefas. Endpoint `POST /reunioes/{id}/aprovar-sem-assinatura` (irmão do `/aprovar`, mesmas guardas: Secretária 403, status 400, 404), **síncrono** (retorna `total_pendencias`), reusando `liberar_pendencias` (idempotente) e gravando auditoria `APROVACAO_SEM_ASSINATURA`. Schema: `StatusAta.APROVADA` no enum + migration `040` (CHECK) + tipo `StatusAta` no frontend (2 locais). UX: `ConfirmDialog` com contagem e aviso de ausência de assinatura, timeline no ramo "Aprovada", banner próprio (distinto do verde "Assinada") com link para Pendências, sem card de Signatários. Glossário e máquina de estados em `CONTEXT.md` + decisão em `ADR 0003` (gatilho da Pendência = `ASSINADA` **ou** `APROVADA`). 8 testes novos (suíte backend 241 verde); 3 gates verdes (code-review com 2 correções aplicadas, security-review sem achados, CI 3/3). `APP_VERSION` 0.5.1→0.6.0. Health pós: backend 200 em 83ms (`db:healthy`, `version:0.6.0`), frontend 200 em 123ms. A migration 040 foi aplicada manualmente no Supabase Studio (SSH temporariamente no fail2ban) e confirmada (`'APROVADA'` no CHECK).

## 2026-05-28 11:12 — Status real de assinatura: card passa a refletir quem realmente assinou no ClickSign
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `b471893`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (212s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/b471893

## 2026-05-27 19:05 — Fallback de assinatura: aviso humano + link pro painel ClickSign quando o Envelope não é recuperável
- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `655a5a6`
- Serviços: backend, frontend
- Resultado: 🟢 healthy (224s)
- Commit: https://github.com/pedrorezendefig/hospital-reunioes/commit/655a5a6

## v0.4.0 — 2026-05-27 — feat(backend): self-heal do Envelope ClickSign (status real pré-039)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#22](https://github.com/pedrorezendefig/hospital-reunioes/pull/22) · Issue: [#20](https://github.com/pedrorezendefig/hospital-reunioes/issues/20)
- Commit: `ed87233`
- Resultado: 🟢 healthy (backend auto-deploy ~140s + redeploy 109s p/ aplicar APP_VERSION, frontend ~182s)

**Resumo:** Recuperação automática do `envelope_id` ClickSign + status real por signatário em Atas **pré-039** (criadas antes da migration `039_add_envelope_id_clicksign`, que não tinham `envelope_id_clicksign` gravado). Quando o card de signatários consulta uma Ata legada, o backend agora faz self-heal: descobre o envelope a partir dos dados disponíveis, persiste o `envelope_id` e passa a exibir o status live (assinou / pendente) em vez da faixa amarela "legacy". Mudança em `routers/reunioes.py` (+45) e `services/clicksign_service.py` (+74), com 356 linhas novas de teste em `test_signatarios_status.py`. **Efetivação da v0.4.0 em prod:** a entrada v0.4.0 de 22/05 (bc2f8ab) era um bump aspiracional — o `package.json` do frontend já estava em 0.4.0, mas o `APP_VERSION` do backend no Coolify ficou em `0.3.1`, então o `/api/health` mentia a versão. Este deploy fecha isso: o auto-deploy via webhook rodou no merge (ainda com 0.3.1, pois o sync do `/ship` falhou na sessão anterior por MCP Coolify em 403 — restrição de IP no token), e nesta sessão, com token/IP liberados no `coolify.mala-ia.cloud`, o `APP_VERSION` foi setado `0.3.1 → 0.4.0` (runtime) + redeploy do backend (`f5tqsd2`, force, 109s, sem OOM). Agora `/api/health` retorna `version:0.4.0`, batendo com o rodapé do frontend. Sem migration nova (039 já aplicada no PR #16). Health pós-deploy: backend 200 em 78ms (`status:healthy`, `db:healthy`), frontend 200 em 155ms.

---

## v0.4.0 — 2026-05-22 — feat(clicksign): card de signatários com status + lembrete; remove modo sandbox

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#16](https://github.com/pedrorezendefig/hospital-reunioes/pull/16) · Issue: —
- Commit: `bc2f8ab`
- Resultado: 🟢 healthy (backend 29s, frontend 120s, migration 039 aplicada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Substitui o card "Aguardando Assinatura Digital" (parágrafo genérico + bloco DEV laranja "Simular Sandbox" — dead-code em prod por causa de `ENABLE_BYPASS_ENDPOINTS=false`) pelo novo **`SignatariosCard`** com lista live de signatários. Cada linha mostra avatar + nome + email + badge verde com timestamp ("Assinou em DD/MM HH:MM") ou amarelo com botão "✉ Lembrar" pra signatários pendentes. Contador "X de Y assinaram", botão "⟳ Atualizar" (refresh manual com spin) e auto-poll a cada 30s via `usePolling`. Botão "Lembrar" envia POST que chama ClickSign pra reenviar email de assinatura com template PT-BR custom (cooldown visual de 60s pós-click). **Backend:** 2 endpoints novos — `GET /reunioes/{id}/signatarios/status` (rate-limit 60/min, consulta ClickSign v3 + enriquece com nome local + modo degradado pra reuniões pré-migration) e `POST /reunioes/{id}/signatarios/{signer_id}/lembrar` (rate-limit 10/min, template em PT-BR via mensagem custom no notification do ClickSign). 2 métodos novos em `clicksign_service`: `list_signers(envelope_id)` (`GET /api/v3/envelopes/{id}/signers` com normalização) e `remind_signer(envelope_id, signer_id, message)`. `start_signature_flow` agora grava `envelope_id_clicksign` no banco (separado de `envelope_key_clicksign` que continua sendo o `document_id` usado pelo webhook — nomes legados v1). **Sandbox eliminado:** 4 endpoints removidos (`/aprovar-bypass`, `/aprovar-bypass-todas`, `/simular-assinatura`, helper `_executar_simulacao`), flag `enable_bypass_endpoints` + validator `validate_bypass_prod` em `config.py`, teste `test_secretaria_403_em_aprovar_bypass`, linha `ENABLE_BYPASS_ENDPOINTS=false` em `.env.example`, entrada em `runtime_required` + `prod_only_assertions` em `docs/spec/deploy/project.json`. **Migration 039:** `ALTER TABLE reunioes ADD COLUMN IF NOT EXISTS envelope_id_clicksign TEXT` — aditiva, idempotente, executada como `supabase_admin` (user `postgres` não era owner da tabela; documentado no chronicle). Reuniões pré-deploy ficam com coluna NULL e a UI exibe faixa amarela "legacy" + desabilita botão Lembrar. **Cobertura:** `test_signatarios_status.py` novo com 19 testes (7 endpoint status, 6 endpoint lembrar, 3 service list_signers, 3 service remind_signer) cobrindo paths felizes + 4xx/5xx + cenários legacy. 203/203 testes verdes (incluindo o hotfix do PR1). CI 3/3 SUCCESS (Backend Lint 26s, Frontend Lint+TSC 41s, Docker 2m24s). Self-approval/merge direto via `gh pr merge 16 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend 29s + frontend 120s. Health backend 97ms, frontend 115ms. **APP_VERSION mantido em 0.3.1 no Coolify** — bump aspiracional pra v0.4.0 registrado neste CHANGELOG mas o `/api/health` e o rodapé do frontend continuam exibindo `0.3.1` até o próximo deploy real que rebuilde frontend com `NEXT_PUBLIC_APP_VERSION` atualizado.

---

## v0.3.2 — 2026-05-22 — fix(matcher): sincronizar reuniao_participantes na correção de ata (bug 7→4 ClickSign)

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#15](https://github.com/pedrorezendefig/hospital-reunioes/pull/15) · Issue: —
- Commit: `385d9c7`
- Resultado: 🟢 healthy (backend 37s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Hotfix do bug "7→4" relatado pelo diretor: quando ele corrigia o número de participantes via Chat de Correção (ex: IA extraía 7 nomes, ele removia 3 → 4), o ClickSign recebia o envelope com **os 7 emails originais** (incluindo os 3 removidos), em vez dos 4 corrigidos. Causa raiz em `backend/app/services/participant_matcher.py:292-411` — `match_participants()` fazia apenas UPSERT em `reuniao_participantes`, nunca DELETE. Era correto pro fluxo de extração inicial (pré-vinculados que a IA não cita continuam válidos como "convidados que não falaram"), mas no fluxo de correção a tabela junção ficava corrompida. Fix cirúrgico: kwarg novo `prune_missing: bool = False` (default = comportamento legado preservado). `run_correction_pipeline:411` opta-in com `prune_missing=True` (modo SYNC: delete + upsert). Adicionado `all_matched_this_pass: set[str]` que coleta TODOS os matches (inclusive pré-vinculados re-confirmados), permitindo distinguir "pré-vinculado confirmado" de "pré-vinculado removido pelo diretor". Mock `_Query` em `test_participant_matcher.py` estendido com `.delete().eq().in_().execute()`. 7 testes novos em `TestSyncPruneMissing` (canônico 7→4, regressão off, idempotente, lista vazia, renomeação, `link_on_match=False`, isolamento por id_reuniao) + arquivo novo `test_correction_pipeline_sync.py` com 2 testes de integração (run_correction_pipeline → 4 rows persistem; start_signature_flow → add_signer chamado 4× com emails corretos). 203/203 testes verdes. CI 3/3 SUCCESS (Backend Lint+Tests 24s, Docker 41s, Frontend Lint+TSC 32s). Self-approval/merge direto via `gh pr merge 15 --squash --delete-branch` autorizado por Pedro. Webhook Coolify auto-deploy backend em 37s. Health `https://api.hospitalsaomatheus.cloud/api/health` 200 em 1.15s. **APP_VERSION mantido em 0.3.1** (sem bump no Coolify; PR2 sequencial bump pra 0.4.0). **Pendência manual pós-deploy:** reuniões hoje em `AGUARDANDO_ASSINATURA` com envelope errado precisam tratamento caso a caso (cancel ClickSign + force-status + reaprovar).

---

## v0.3.1 — 2026-05-22 — fix(secretaria): habilitar edição de participantes na tela Editar reunião

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#11](https://github.com/pedrorezendefig/hospital-reunioes/pull/11) · Issue: —
- Commit: `2e745ab`
- Resultado: 🟢 healthy (backend 36s, frontend 169s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Bug reportado pelo Pedro — a tela "Editar reunião" (rota `/secretaria/nova?edit=`) escondia o `<MultiSelect />` de participantes em modo edição. A secretária ficava sem visão pra adicionar/remover quem participa de uma reunião futura. Fix em 1 arquivo TSX (`hospital-reunioes/frontend/src/app/secretaria/nova/page.tsx`, +101 −18): MultiSelect agora aparece também em edição, populado com snapshot inicial de `participantes_programada`. `handleSubmit` calcula diff (`toAdd = atual − iniciais`, `toRemove = iniciais − atual − [facilitadorId]`) e chama `POST/DELETE /api/reunioes/:id/participantes` em paralelo via `Promise.allSettled` (originalmente `Promise.all`, ajustado pelo `/code-review` pra não mascarar o sucesso do PATCH em erro de rede). `useEffect` re-injeta o facilitador automaticamente caso seja desmarcado. Backend já aceitava a operação pela secretária — endpoints sem gate de role, só exigem `status_ata == PROGRAMADA`. 5 camadas de gate verdes (`/code-review`, `/security-review` sem findings, `superpowers:requesting-code-review` aprovou com follow-ups arquiteturais registrados, CI 3/3 SUCCESS, `verification-before-completion` com tsc+lint+build local exit=0). Bump patch automático 0.3.0 → 0.3.1. Self-approval bloqueado pelo GitHub free; merge segue direto via `--admin`. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`).

---

## v0.3.0 — 2026-05-22 — feat(reunioes,secretaria): dropdown responsável + visão global da secretária com gate em ata/pendência

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#10](https://github.com/pedrorezendefig/hospital-reunioes/pull/10) · Issue: —
- Commit: `805daa0`
- Resultado: 🟢 healthy (backend 2m42s, frontend 3m43s)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Mescla dois escopos numa única release. **(1) Dropdown responsável na correção da ATA** — substitui edição implícita via chat por combobox inline de participantes na coluna RESPONSÁVEL do quadro de atribuições; resolve bug "Josiane" (nome trocava mas cargo continuava stale). Endpoint novo `PATCH /reunioes/{id}/quadro-atribuicoes/{index}`, helper `_canonicalize_cargos_quadro` no orchestrator pós-IA, `pendencias.cargo` agora populado em `liberar_pendencias` (era NULL antes), componente `ResponsavelInlineCombobox.tsx`. **(2) Expansão do papel secretária** — antes só via PROGRAMADAS futuras, agora vê o calendário do hospital inteiro (qualquer status, qualquer data) e gerencia participantes em reuniões PROGRAMADAS (inclusive alheias). Defense-in-depth: **20 gates 403 explícitos** nos endpoints de ata/pendência/comentário (12 reuniões + 5 pendências + 3 comentários), `get_allowed_reuniao_ids` retorna `None` pra secretária, `_redact_ata_fields` redacta `json_ata`/`url_pdf_*` nos endpoints de leitura, gate de visibilidade adicionado em `PATCH /quadro-atribuicoes/{index}`. Frontend: flag `hideAtaSections` em 14 pontos do detalhe da reunião + esconde botão "Desmarcar" e "Anexar Transcrição" pra secretária. Bump 0.2.1 → 0.3.0 (feat=minor). 3 reviewers automatizados (code-review + security-review + superpowers:requesting-code-review) detectaram 3 must-fix em iteração — todos resolvidos antes do merge: critical de `json_ata` leak em `GET /reunioes/{id}`, must-fix de visibilidade no PATCH quadro e ausência de teste de gates. Novo arquivo `tests/test_secretaria_gates.py` com 9 testes cobrindo os 3 routers + edge case `me=None`. Suite final: 186/186 passa. CI 3/3 verde. APP_VERSION sincronizada no Coolify backend pré-merge (Passo 8.5 do `/ship`). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.1 — 2026-05-22 — fix(frontend): mover versão pro canto inferior direito e remover link pro GitHub

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#9](https://github.com/pedrorezendefig/hospital-reunioes/pull/9) · Issue: —
- Commit: `d3cc4a1`
- Resultado: 🟢 healthy (build frontend 169s; backend não redeployado, só env APP_VERSION sincronizada)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** Footer.tsx perde o wrapper `<a target=_blank>` que apontava pro CHANGELOG no GitHub e muda de `text-center` pra `text-right pr-4`. Versão agora é texto puro alinhado ao canto inferior direito (padrão visual de apps profissionais — não compete com conteúdo). Aria-label mantido pra screen readers. Bump patch automático `0.2.0 → 0.2.1` (tipo dominante: fix). APP_VERSION sincronizada no backend Coolify (`mcp__coolify__env_vars update`, runtime-only) pré-merge — backend NÃO foi redeployado, só o env mudou e o `/api/health` já reflete `version:0.2.1`. Frontend rebuild Docker em 169s (cache quente). Gates: code-review max-effort (3 agents, 1 nit aplicado `px-4` → `pr-4`), security e requesting-code-review pulados (mudança cosmética de 4 linhas em 1 arquivo de UI), CI verde, verification verde (tsc + lint). Self-approval bloqueado pelo GitHub free; merge segue direto.

---

## v0.2.0 — 2026-05-22 — feat(app): acrescentar versionamento visível na aplicação

- Autor: Pedro Rezende <pmrdef@gmail.com>
- PR: [#8](https://github.com/pedrorezendefig/hospital-reunioes/pull/8) · Issue: —
- Commit: `1efd175`
- Resultado: 🟢 healthy (build backend 198s, frontend 255s, health ok com version match)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** primeiro PR de versionamento. Rodapé `v0.2.0` clicável em todas as páginas do AppShell (link → CHANGELOG.md no GitHub). Backend `/api/health` retorna `version` lido de env `APP_VERSION` (default `0.1.0`). Footer.tsx novo lê `NEXT_PUBLIC_APP_VERSION` inlined em build-time pelo `next.config.ts` a partir de `package.json` (bumpado 0.1.0 → 0.2.0 manualmente neste PR; nos próximos é automático via /ship Passo 5.5). Skill `/ship` ganha bump automático de semver por tipo de commit (BREAKING > feat > fix/chore) + Passo 8.5 que sincroniza APP_VERSION no Coolify pré-merge (evita race com webhook). Skill `/deploy` ganha Passo 3.5 defensivo idempotente + Passo 7.2 version match check (rollback automático se /api/health não retorna versão esperada). Docs novos: `VERSIONING.md` (esquema completo) + header explicativo no CHANGELOG.md. 5 camadas de gate verdes antes do merge — 4 issues do code-review e 2 do requesting-code-review corrigidos em-band nos commits 3136a5c e 4a5fc8d.

---

## 2026-05-21 20:39 - feat(skills): automatizar /snapshot via script Python

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `70bac46`
- PR: [#7](https://github.com/pedrorezendefig/hospital-reunioes/pull/7) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** implementa o gerador real do `/snapshot` que estava só documentado no PR #6. Script Python self-contained (993 linhas, stdlib only) em `.claude/skills/snapshot/scripts/snapshot.py` com parser AST de routers FastAPI (78 endpoints em 13 routers), parser SQL cumulativo de migrations (13 tabelas das 36 migrations), 5 geradores de MD, idempotência via comparação de buffer e flags CLI (`--check`, `--force`, `--only`, `--diff`, `--no-commit`). Code-review pegou 1 bug score 100 (JSONB DEFAULT corrompendo parser de colunas) + 3 issues score 75, todas corrigidas antes do merge.

---

## 2026-05-21 18:58 - feat(workflow): integrar Superpowers + /snapshot vivo + 5 camadas de gate

- Autor: Pedro Rezende <pmrdef@gmail.com>
- SHA: `e9f64ee`
- PR: [#6](https://github.com/pedrorezendefig/hospital-reunioes/pull/6) · Issue: —
- Resultado: 🟢 merged (sem deploy de prod — PR só toca skills + docs)
- Detalhe: chronicle arquivado (recuperável via `git show pre-pocock-migration:docs/spec/chronicles/`)

**Resumo:** integra plugin Superpowers v5.1.0 no workflow do time. Cria skill `/snapshot` (gera 7 MDs vivos em `docs/spec/snapshots/` regenerados a cada deploy via `/deploy ship`). `/start` ganha Modo D (retomar trabalho parado de outra sessão) + invocação de `brainstorming` por default no Modo A. `/ship` ganha 5 camadas independentes de gate antes do self-approval (code-review, security-review, requesting-code-review, CI Actions, verification-before-completion). `CLAUDE.md` reescrito com 5 seções novas. CI Actions ganha job `build` (docker sanity). Cleanup de 150+ skills `reversa-*` absorvido no mesmo PR (-26338 linhas).
