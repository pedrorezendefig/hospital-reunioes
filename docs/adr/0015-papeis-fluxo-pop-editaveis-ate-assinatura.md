---
status: accepted
---

# Papéis do fluxo de POP editáveis até a assinatura

Elaborador, Revisor e Validador são designados na criação do POP e vivem na tabela-mãe `pops`. Até aqui eram imutáveis por design: não existe endpoint de edição, e um teste-guarda (`test_codigo_e_imutavel_nenhum_endpoint_o_altera`) quebra se alguém criar um `PATCH`/`PUT` em `/pops/{id}`, blindando o Código travado. Só que pessoas saem e trocam de função: um Revisor designado pode estar fora quando a Versão chega à Revisão. Travar os papéis para sempre obrigaria a recriar o POP (perdendo o Código, que é referência institucional, e o histórico de Versões) só para trocar um nome.

A decisão: passa a existir edição de Elaborador, Revisor e Validador depois da criação, enquanto a **Versão ativa** (a mais recente) estiver antes da assinatura, ou seja nos estados `A_ELABORAR`, `EM_ELABORACAO`, `EM_REVISAO` ou `EM_VALIDACAO`. A edição trava quando o envelope ClickSign nasce (`EM_ASSINATURA`) e em `PUBLICADO`, porque aí os Signatários já estão no envelope e o PDF assinado registra quem assinou; mexer desincronizaria a assinatura. Se um designado precisa mudar num POP já publicado, isso acontece ao iniciar a próxima Revisão periódica: a nova Versão volta a `A_ELABORAR` e destrava. Quem pode editar é o mesmo escopo de quem cria o POP (Superadmin POP e Gestor de Qualidade no escopo institucional; Gerente e Coordenador nos seus Setores). Ao trocar, a pessoa nova da etapa ativa é notificada. O Código continua imutável: o endpoint edita apenas os três campos de papel.

## Por que é surpreendente

O teste-guarda existente afirma "nenhum endpoint altera o POP". Um dev que adicionar o `PATCH` de papéis vai quebrá-lo e pode achar que está ferindo o Código travado. Precisa ficar claro que a imutabilidade vale para o Código, não para os papéis, e que a trava por estado (livre antes da assinatura, travada a partir dela) é deliberada.

## Alternativas descartadas

- **Manter imutável e recriar o POP para trocar de pessoa**: perde o Código (presente em treinamentos e na Biblioteca) e o histórico de Versões. Pesado demais para uma troca de nome.
- **Editável em qualquer estado, inclusive após assinar**: desincroniza o envelope ClickSign e contradiz o PDF assinado, que registra quem assinou. Quebra a cadeia de assinatura.
- **Editável até `PUBLICADO`, inclusive num POP estável sem Versão em fluxo**: conveniência marginal a troco de editar um POP que já foi assinado. Preferimos a regra limpa "antes da assinatura".

## Consequências

- Novo endpoint `PATCH /pops/{id}` restrito aos campos `elaborador_id`, `revisor_id` e `validador_id`, com a trava pelo estado da Versão ativa, mais a UI de edição na gestão do POP.
- O teste-guarda muda de "não existe `PATCH`/`PUT`" para "o `PATCH` existe, mas rejeita `codigo` e qualquer campo fora dos papéis".
- Notificação à pessoa nova da etapa ativa ao trocar.
- A trava depende do estado da Versão mais recente: um POP com Versão vigente Publicada e nenhuma em fluxo fica travado até começar a próxima Revisão periódica.
