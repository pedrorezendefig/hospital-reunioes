---
status: accepted
amends: 0054
---

# Anexo da Demanda fica no app, quem desenvolve busca; Em produção é a Etapa que devolve ao diretor

Decisão do Pedro (07/out/2026, grilling). A aba Tecnologia (ADRs 0050, 0054, 0056) está em produção e cumpre o papel, mas duas pontas continuam fora dela: o diretor não tem como anexar um print à Demanda (o Assistente lê a imagem e joga fora), e a Etapa para em "Entregue" no merge, quando o que o diretor quer saber é se já pode usar. Esta ADR fecha as duas pontas. O redesenho da aba decidido na mesma sessão (três raias vivas, card de duas linhas, Produtos em tela própria, Painel no lugar de "Minha vez" e "Histórico") é vocabulário, está no `CONTEXT.md` e não precisa de ADR.

## Contexto

- O repositório é **público** (decisão de 09/2026). A ADR 0060 já passa pela peneira de dado pessoal todo texto que o app manda para a issue. Um print de tela do hospital carrega nome de paciente, de colaborador, protocolo da Ouvidoria.
- O GitHub não tem API para anexar imagem a issue: o que a tela faz ao arrastar um arquivo é um endpoint não documentado de `user-attachments`, e o resultado é uma URL pública.
- O app já tem o molde dos dois lados: bucket privado com URL assinada (anexos da Ouvidoria, migration 066) e token de serviço por `X-API-Key` (API da Ana, ADR 0031).
- A Action pós-merge (`pos-merge.yml`) já recebe o registro do deploy por `workflow_dispatch` (versão, PRs do lote) e é o único lugar que sabe, com certeza, que uma versão subiu.
- O webhook `issues` já grava a Etapa em segundos; a tela relê a cada 30 s. A latência não é o problema, a cobertura é: PR aberto e deploy não geram evento nenhum.
- Quem pega a issue hoje é o `/pegar-issue` no terminal ou o `hr-implementador` na `/onda-enxuta`, e os dois leem a issue pelo `gh`.

## Decisões

1. **O Anexo da Demanda vive no app e nunca vai para o GitHub.** Imagem (png, jpg, webp, mesmo teto do Assistente), até dez por Demanda, por três portas: formulário, Assistente (o print que ele descreve vira Anexo se o diretor clicar "Criar Demanda") e resposta da Conversa. Bucket privado próprio (`anexos-tecnologia`), tela abre por URL assinada. A issue vinculada ganha só a frase "Anexos: N imagens na Demanda"; o comentário espelhado de uma resposta com imagem sai como texto mais "(1 imagem na Demanda)". Rejeitado: `![](url assinada)` na issue (expira, e enquanto vale é pública), base64 no corpo (teto de 65k caracteres), commitar a imagem no repositório (público).

2. **Quem desenvolve busca o Anexo pelo app, por uma boca só.** Rota de leitura dos anexos de uma Demanda protegida por chave de automação própria (`TECNOLOGIA_AUTOMACAO_API_KEY`, molde do `require_ana_api_key`; vive no Coolify e no `tokens/.env` de cada sócio). Um script na skill (`pegar-issue/scripts/anexos.py <issue>`) lê o id da Demanda no marcador que o corpo da issue já carrega, baixa as imagens para `local/anexos/<issue>/` (fora do git) e o agente as lê como arquivo. Três chamadores: `/pegar-issue`, o prompt do `hr-implementador` (no passo "leia a issue", quando o corpo diz "Anexos") e o `hr-corretor`. Rejeitado: cada skill chamar a API do seu jeito (três implementações para divergir) e o orquestrador da onda baixar e passar os caminhos (o implementador roda em worktree próprio e o corretor é outro agente).

3. **O binário é apagado quando a Demanda chega a Concluída ou Cancelada**, o ato humano que encerra, nunca pela Etapa: em "Em produção" o diretor ainda confere com o print na mão. Fica o registro (nome, quem anexou, quando), marcado apagado, para a Conversa não quebrar. Mesmo motivo da Ouvidoria (#631): binário parado em bucket privado de assunto encerrado é dado pessoal permanente. Na máquina do sócio, o `/ship` apaga `local/anexos/<issue>/` ao abrir o PR. Rejeitado: retenção por tempo (quem decide que acabou é quem conclui) e apagar na Etapa Entregue (o diretor ainda não conferiu).

4. **Nasce a sétima Etapa, Em produção, gravada pela Action pós-merge.** O passo que aplica o registro do deploy chama `POST /webhooks/deploy` no app, com HMAC (segredo próprio), versão e PRs do lote; o app marca Em produção, com a versão, as Demandas cujas issues foram fechadas por aqueles PRs, e grava a linha automática "Em produção na vX.Y.Z" na Conversa. Entregue continua sendo o fechamento da issue (decisão 3 da ADR 0054 fica de pé nisso): entre o merge e a subida o card diz Entregue, depois "Em produção desde vX.Y.Z". O cron de reconciliação cobre o que a Action não entregou, lendo o `history.json` da `main`. Rejeitado: o `fechar_onda.py` chamar o app da máquina do sócio (mais um passo que falha em silêncio num laptop; a Action tem o segredo e roda depois do registro) e o app ler o `state.json` (a ADR 0054 recusou acoplar ao arquivo, e continua recusado: o acoplamento é por evento, e o arquivo é só a reconciliação).

5. **A devolução a quem pediu passa de Entregue para Em produção** quando a issue fechou por PR. O diretor não tem como conferir o que ainda não subiu; devolver no merge era pedir que ele testasse o que não existia. Issue fechada à mão, sem PR (decisão, consultoria, correção fora do código), devolve em Entregue como hoje. O e-mail de atribuição é o mesmo. Isso emenda a decisão 6 da ADR 0054.

6. **O webhook passa a tratar `pull_request`.** PR aberto que fecha a issue (`closingIssuesReferences`) vira Em desenvolvimento na hora, sem depender de alguém pôr a label `in-progress`. PR fechado sem merge não mexe na Etapa (a label e as sub-issues continuam dizendo o que vale).

## Alternativas descartadas

- **Guardar a imagem no GitHub como asset de Release ou em branch órfã.** Continua público.
- **Mandar a descrição da imagem (o texto que o Assistente já gera) em vez da imagem.** Útil para o diretor, cego para quem corrige um defeito visual; vai junto, não no lugar.
- **Etapa Em produção lida do `/health` do backend pelo app.** O app saberia a versão no ar, não quais issues subiram nela.

## Consequências

- Migration: tabela de anexos da Demanda (Demanda, caminho, nome, quem, quando, apagado em) e a Etapa `em_producao` com a versão na Demanda. Bucket `anexos-tecnologia` privado, RLS default-deny.
- Backend: upload e leitura assinada de anexos, rota de automação por `X-API-Key`, apagamento no Concluir/Cancelar, webhook `pull_request` e `deploy`, reconciliação de Em produção pelo `history.json`.
- Action pós-merge: um passo a mais, depois do registro, com `TECNOLOGIA_DEPLOY_WEBHOOK_SECRET` nos secrets do repositório. Cadastro do segredo no Coolify é passo humano.
- Skills: `pegar-issue/scripts/anexos.py`; `/pegar-issue`, `hr-implementador` e `hr-corretor` chamam o script; `/ship` apaga a pasta local; `/ask-pedro` cita a boca única.
- Glossário: Anexo da Demanda, Etapa com Em produção, Quadro, Painel (já escritos).
- Kit de conhecimento (arquivo da aba Tecnologia) e manual da aba (página HTML própria) mudam no mesmo PRD.

## Emenda a este ADR (07/out/2026, auditoria do PRD #1056)

**Decisão 2, o que a rota de automação responde quando recusa.** A rota de leitura dos anexos (`GET /api/automacao/tecnologia/demandas/{id}/anexos`) segue o molde da API da Ana em quase tudo: chave ausente, vazia ou errada responde **401**, igual. A diferença é deliberada e vem da fatia #1063: quando `TECNOLOGIA_AUTOMACAO_API_KEY` **não está configurada no servidor**, a rota responde **503** ("ponte desligada"), enquanto a Ana responde 401 (`require_tecnologia_automacao_api_key` em `backend/app/dependencies.py`). O motivo é quem chama: o `anexos.py` roda na máquina do sócio e precisa distinguir os dois casos, porque o conserto é outro. No 503 ele diz que falta criar a chave na tela do Coolify; no 401, que a chave do `tokens/.env` está errada. Não é desvio a corrigir: trocar o 503 por 401 faria o sócio trocar de chave à toa quando o que falta é o cadastro no servidor.
