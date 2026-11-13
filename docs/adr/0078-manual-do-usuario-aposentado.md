---
status: accepted
supersedes: 0057, 0072, 0076
amends: 0068, 0071, 0077
amended_by: 0094
---

# Manual do usuário aposentado

Decisão do Pedro (05/11/2026). O Manual do usuário sai da plataforma inteiro, para ser refeito depois com outra abordagem. Até aqui ele era um site Astro Starlight na Vercel (`manual-hsm.vercel.app`), com uma seção por módulo, Página de tarefa, Vídeo de visão geral por módulo e uma Fatia de manual no fim de todo PRD com tela (ADRs 0057, 0072 e 0076).

## Decisões

1. **O site sai do ar e do repositório.** Os projetos `manual-hsm`, `manual-ouvidoria-hsm` e `manual-tecnologia-hsm` foram apagados da Vercel. A pasta `docs/manual/`, os prompts de produção em `docs/prompts/`, as skills `/manual` e `/montar-manual` e os scripts e testes próprios dele em `tools/` saem do repositório. O histórico fica no git.

2. **O app perde o item Ajuda.** O item do menu (no app e no Admin) apontava para o site apagado; sai junto com a variável `NEXT_PUBLIC_MANUAL_URL`. O kit de conhecimento da Tecnologia deixa de indicar o endereço.

3. **O fluxo deixa de pedir manual.** O `/to-prd` não tem mais a seção "Manual: páginas que nascem ou mudam", o `/to-issues` não cria a Fatia de manual, e o `/grill-with-docs` e o `/ask-pedro` não usam o Manual para escolher a porta. A Action pós-merge para de tirar draft e de avisar no PRD; fica com o snapshot e o registro do deploy. O workflow `manual.yml` vira `ferramentas.yml` e roda só os testes de `tools/`, que continuam valendo.

4. **Os vídeos ficam no Mac.** Em `~/Videos/Hospital/Manual/` ficam os seis Vídeos de visão geral e os Vídeos de tarefa, como material para a abordagem nova; as cópias antigas, os rascunhos e as versões anteriores foram apagados.

5. **As issues "docs: manual do PRD" foram apagadas**, inclusive a aberta do PRD de acompanhamento do processamento de Contas médicas. Os PRs de manual já mergeados ficam no histórico (o GitHub não apaga PR).

## Consequências

- As ADRs 0057, 0072 e 0076 passam a `superseded`. O que a 0076 decidiu sobre a Tecnologia (decisão 5) era sobre a Tecnologia dentro do Manual e cai junto; o kit de conhecimento continua sendo o que o Assistente de Tecnologia lê.
- A régua de texto da ADR 0071 continua valendo para todo texto para fora (tela, PDF, mensagem, PR, página de divulgação); o lint dela que morava no Manual sai, e ficam o ESLint do front e o teste dos templates do backend.
- Emenda a 0068 (a Fatia de manual some do fluxo e da lista do que sobe sem parada humana), a 0071 (o lint do Manual sai da régua) e a 0077 (a decisão 10, de reescrever o módulo Tecnologia do Manual, cai).
- Cada máquina tira `manual-hsm.vercel.app` do `autoMode.environment` do próprio `~/.claude/settings.json`: com o projeto apagado, o subdomínio ficou livre para qualquer conta registrar e não pode seguir confiável para o modo auto. O `/setup-maquina` acusa no nível 2 enquanto o host estiver lá.
- O Manual novo, quando vier, é decisão nova, com ADR própria.
