---
status: accepted
amends: 0020
---

# Demanda vinculada a issue do GitHub: Etapa derivada, comentário do diretor espelhado e a bola volta a quem pediu

Decisão do Pedro (10/set/2026, grilling). A aba Tecnologia (ADR 0050) está em produção, mas a Demanda não sabe nada do que acontece no GitHub, onde o trabalho de fato é planejado, desenvolvido e entregue. O diretor não entra no GitHub e não deve entrar: nada técnico no app, nada de leigo no repositório. Este ADR liga os dois mundos por um vínculo explícito, com o GitHub como única fonte do estado do desenvolvimento e o app como única porta do diretor.

## Contexto

- O ADR 0020 previa o diretor como revisor canônico **usando o GitHub web** (decisão 3) e a label `revisor-comentou` acesa pelo **login** do autor (decisão 5, `REVIEWER_LOGINS`). Na prática o único login configurado sempre foi o do Pedro; o diretor nunca comentou no GitHub.
- Todo PRD e toda fatia abrem com o bloco **"Para o diretor"** (ADR 0020, decisão 7), escrito para leitor não técnico e curado pelo `/to-prd` e `/to-issues`. Esse texto existe e não chega ao diretor.
- O backend já tem o molde: router de webhooks com HMAC (ClickSign, Fireflies) e cron APScheduler que reconcilia a ClickSign de tempos em tempos.
- Fatos da API do GitHub, conferidos na doc oficial em 10/09/2026: comentário criado com PAT dispara `issue_comment.created` nas Actions (só o `GITHUB_TOKEN` é filtrado); o GitHub não reentrega webhook que falhou e exige resposta em 10 s; a API de sub-issues está GA e o objeto da issue traz `parent_issue_url` e `sub_issues_summary`; marcador HTML `<!-- -->` sobrevive no `body` e não aparece renderizado; a permissão mínima do token fine-grained é Issues: write.

## Decisões

1. **Vínculo: 1 Demanda para 1 issue-raiz** (o PRD, ou uma issue simples de fix). As fatias são as sub-issues dessa raiz, nunca vinculadas uma a uma. O par é guardado nos dois lados: a Demanda guarda o número da issue, a issue guarda o id da Demanda num marcador oculto no corpo. Criado de duas formas: **vincular por número** (o caso comum, quando o PRD nasceu do grilling) ou **"Levar para desenvolvimento"** (o app cria a issue com `needs-triage`, o bloco "Para o diretor" preenchido com título e descrição da Demanda, o marcador, e o tipo mapeado: Defeito vira `type:fix`, Ajuste e Novo viram `type:feature`). Rejeitado: só vínculo manual (o app ficaria cego) e só criação pelo app (o grilling continua sendo a porta de qualidade do PRD).

2. **O app aprende do GitHub por webhook mais reconciliação no cron**, o molde da ClickSign. Webhook `issues` (só esse evento) com HMAC no router de webhooks; cron de hora em hora relê as issues vinculadas abertas e corrige o que o webhook perdeu. Rejeitado: só webhook (o GitHub não reentrega, a Etapa mentiria para sempre); só cron (atraso e consulta o dia inteiro); as skills empurrarem para o app (cada skill vira ponto de falha e um `gh issue close` na mão nunca chegaria).

3. **Etapa é um segundo eixo, derivado, nunca editável**, ao lado do Kanban. Seis valores, cada um lido de labels, sub-issues e fechamento: Registrada (sem vínculo), Em análise (`needs-triage` ou `needs-info`), Planejada (`ready-for-agent`, `ready-for-human`, ou PRD com sub-issues e nenhuma em andamento), Em desenvolvimento (`in-progress` na raiz ou em alguma sub-issue, ou PR aberto), Entregue (issue fechada como concluída), Não será feita (fechada como não planejada ou `wontfix`). PRD mostra ainda "X de Y partes entregues" do `sub_issues_summary`. Escolhas dentro disso: Entregue é o fechamento da issue (no merge), não o deploy confirmado, para não acoplar o app ao `state.json`; `needs-info` fica dentro de Em análise, a pergunta chega ao diretor pela Conversa. Rejeitado: Etapa digitada à mão (voltaria a mentir) e sétima Etapa "Aguardando o hospital".

4. **Toda resposta da Conversa de uma Demanda vinculada é espelhada na issue**, para o agente que curar ler o fio inteiro. A label `revisor-comentou` acende só para resposta de quem **não tem login no GitHub**: `participantes` ganha o campo opcional `github_login`; a resposta de quem tem login sai com `<!-- automacao -->` (a Action já ignora), a de quem não tem sai com `<!-- revisor-app autor="Nome" -->`, que a Action passa a reconhecer além de `REVIEWER_LOGINS`. Rejeitado: acender em toda resposta espelhada (a resposta "vou ver" do Pedro travaria a `/onda`, o falso positivo conhecido) e botão "Encaminhar" por linha (volta a depender de alguém lembrar). Nota sobre o ADR 0050, decisão 2: `github_login` é um fato, não um lado; a decisão de não modelar o lado continua valendo.

5. **Nenhum comentário do GitHub volta para a Conversa.** O que volta é só a mudança de Etapa, como linha automática ("Entrou em desenvolvimento", "Voltou para desenvolvimento", "Entregue: 3 de 7 partes"). O diretor fica sabendo o resultado da curadoria pela Etapa; pergunta dele na Conversa é respondida por gente. Rejeitado: bloco `<!-- para-o-diretor -->` no comentário de curadoria espelhado como linha "Equipe Vitta" (fura a regra e depende de o agente escrever para leigo toda vez; pode entrar depois como fatia sem desfazer nada).

6. **A Entrega devolve a bola a quem pediu.** É a única regra automática de movimento do Kanban: quando a Etapa chega a Entregue, a Demanda vai para Aguardando com o autor como responsável, dispara o e-mail de atribuição que já existe e cai na Minha vez dele com o recado "Entregue, confira e conclua". Quem conclui é o diretor. Se não estiver bom, a resposta dele na Conversa acende `revisor-comentou` na issue fechada, que é o loop de reabrir do ADR 0020, decisão 4. "Não será feita" só informa; a Vitta explica na Conversa e cancela à mão. Rejeitado: concluir sozinho (rouba o momento em que o diretor vê o valor) e só informar (a bola morre na Vitta).

7. **"O que muda" é lido do GitHub, nunca digitado no app.** O card ganha uma seção com o bloco "Para o diretor" da issue-raiz e, embaixo, a lista das partes (sub-issues), cada uma com o próprio "Para o diretor" e a situação (planejada, em desenvolvimento, entregue). O título da fatia não aparece (é técnico). Issue sem o bloco mostra "Descrição em preparação", nunca o corpo técnico. Rejeitado: só Etapa e barra (o diretor não vê por que cada parte agrega) e o Pedro reescrever o valor na descrição da Demanda (duplica e apodrece).

8. **Identidade: token pessoal fine-grained do Pedro**, só neste repositório, só Issues: write, na variável `GITHUB_INTEGRACAO_TOKEN` do Coolify (nunca `GITHUB_TOKEN`, reservado das Actions). Tudo que o app publica aparece como `pedrorezendefig`; o marcador carrega o autor verdadeiro. Rejeitado por ora: GitHub App própria (`aplicativo-hospital[bot]`, JWT, token de instalação renovado a cada hora), uma engrenagem a mais para cinco pessoas. A troca pela App não mexe no resto, porque o marcador é igual nas duas.

9. **O que é da Vitta fica atrás de `github_login`.** O botão "Levar para desenvolvimento", o campo "Vincular issue" e o link "Abrir no GitHub" só aparecem para quem tem o login preenchido. O diretor não vê número de issue, link nem label. O selo de Etapa só aparece no card quando há vínculo; Registrada é a ausência do selo.

## Emenda ao ADR 0020

- **Decisão 3** (o revisor usa o GitHub nativo): o revisor canônico passa a comentar **no app**, na Conversa da Demanda vinculada; o app leva o comentário ao GitHub. O acesso Triage no repositório deixa de ser necessário para o diretor.
- **Decisão 5** (a Action acende pelo login): a Action acende `revisor-comentou` também pelo marcador `<!-- revisor-app -->`, independente do login do autor no GitHub. `REVIEWER_LOGINS` continua valendo para quem comenta direto no GitHub.
- As decisões 1, 2, 4, 6 e 7 ficam intactas. A 7 (bloco "Para o diretor") passa a ser a **fonte** do que o app mostra ao diretor: quem editar um corpo de issue precisa preservar o bloco, ou a Demanda mostra "Descrição em preparação".

## Emenda a este ADR (10/set/2026, descoberta na implementação)

**Decisão 6, borda das Demandas fechadas.** A decisão diz que a Entrega devolve a bola a quem pediu. Na implementação (issues #678 e #679) ficou claro que ela não pode valer para Demanda já Concluída ou Cancelada, e a fatia #678 decidiu que a sincronização **sai antes de ler o GitHub** quando a Demanda está fechada, pelos dois gatilhos (o webhook e o lote de hora em hora). A #679 herdou essa guarda.

A consequência, consciente e aceita: **o selo de Etapa de uma Demanda fechada congela no dia do fechamento.** Se a issue vinculada for entregue depois, o card no Histórico não fica calado sobre isso, ele continua afirmando a Etapa velha ("Em desenvolvimento"), junto com o "O que muda" e o resumo de partes daquele momento. Quem quiser o selo atualizado **reabre a Demanda**: aí a foto volta a ser lida e a linha automática sai.

A alternativa seria pôr as Demandas fechadas de volta no filtro do lote de hora em hora. Foi rejeitada: contradiz a história 49 do PRD #673 por escrito e paga cota da API do GitHub, de hora em hora, sobre um Histórico que só cresce e nunca esvazia.

O critério de aceite da #679 foi reescrito para dizer o que de fato existe. As decisões 1 a 5 e 7 a 9 ficam intactas.

## Consequências

- `tecnologia_demandas` ganha as colunas do vínculo (número da issue, Etapa, resumo de partes, "O que muda" em cache, última sincronização). `participantes` ganha `github_login`. Migration com o próximo número livre na hora da fatia.
- Backend: cliente GitHub mínimo (criar issue, comentar, ler issue e sub-issues), endpoint de webhook `issues` com HMAC e o segredo `GITHUB_WEBHOOK_SECRET`, job de reconciliação no cron existente, serviço puro que traduz labels e fechamento em Etapa. Cadastro do webhook no repositório é passo humano do deploy.
- Action de higiene: reconhecer `<!-- revisor-app -->`; `/triage` e `/pegar-issue` já lidam com a label, sem mudança de protocolo.
- O glossário (CONTEXT.md, seção Tecnologia) ganha Vínculo com o desenvolvimento, Etapa e O que muda, e a Conversa da Demanda ganha o espelhamento.
- Sem travessão em nada que o usuário vê, inclusive nas linhas automáticas e no "O que muda" trazido do GitHub (o sanitizador cobre o que a IA gera; o bloco "Para o diretor" já nasce sob o lint do CI).
