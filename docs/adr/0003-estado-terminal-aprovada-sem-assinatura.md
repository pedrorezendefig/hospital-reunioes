---
status: accepted
---

# Estado terminal APROVADA: aprovação sem assinatura digital

Em reuniões operacionais / de acompanhamento, o valor está em **registrar a Ata e disparar as Pendências** — não na formalidade da assinatura. Hoje toda Ata só gera Pendências depois que todos os Signatários assinam no ClickSign, o que pode levar dias e obriga o Facilitador a passar pelo Envelope mesmo quando ninguém precisa assinar.

A decisão: na tela de validação (`AGUARDANDO_VALIDACAO`), o Facilitador passa a ter **dois caminhos**. O botão atual vira **"Enviar para assinatura"** (fluxo ClickSign inalterado) e ganha um irmão, **"Finalizar sem assinatura"**, que cria as Pendências na hora e leva a Reunião a um novo estado terminal, **`APROVADA`**, sem Envelope e sem aguardar assinaturas.

Só muda o **destino da aprovação**. O Pipeline de IA, a extração de ações e a revisão/correção da Ata são reusados sem alteração. O endpoint `POST /reunioes/{id}/aprovar-sem-assinatura` é irmão direto do `/aprovar`: mesmas guardas (Secretária 403, exige `AGUARDANDO_VALIDACAO` 400, Reunião inexistente 404, qualquer Facilitador pode), mas **síncrono** — retorna `total_pendencias` para a UI. Reusa o módulo `liberar_pendencias` (idempotente, independente do ClickSign). Ordem da operação: **criar as Pendências primeiro, marcar `APROVADA` depois** — se a criação falhar, o status permanece `AGUARDANDO_VALIDACAO` e a ação é re-tentável (a idempotência garante que não duplica). A ação fica registrada em `audit_log` (`APROVACAO_SEM_ASSINATURA`).

## Por que é surpreendente

A intuição do domínio era "Ata existe para ser assinada" — o gatilho da Pendência morava **dentro** do webhook do ClickSign. Agora a Pendência nasce de um estado terminal que pode ser **ASSINADA ou APROVADA**, e há um caminho de produção que nunca toca o ClickSign. Quem lê o código esperando que toda Pendência venha de uma assinatura precisa saber que existe essa segunda origem.

## Alternativas descartadas

- **Reusar o estado `ASSINADA`** (marcar como assinada sem assinatura): perderia a distinção entre uma Ata com formalidade digital e uma finalizada sem ela — confunde auditoria, badge e relatórios. Por isso `APROVADA` é um estado próprio, paralelo.
- **Caminho reversível** (enviar uma Ata `APROVADA` para assinatura depois): adiciona uma transição de saída de um estado terminal e o risco de duplicar Pendências. A escolha é definitiva; reabrir é trabalho do Super admin via `force-status`, se algum dia for preciso. Fora de escopo.
- **Regra de "sem assinatura" por tipo de Reunião** (ex.: toda reunião Gerencial dispensa assinatura): rígido demais. A escolha é sempre **pontual**, por Ata, decidida pelo Facilitador caso a caso.
- **Restringir a Super admin**: criaria fricção e dependência de privilégio. Qualquer Facilitador pode finalizar sem assinatura — espelha exatamente a permissão do `/aprovar`.

## Consequências

- O gatilho da Pendência passa a ter **duas origens** (`ASSINADA` e `APROVADA`); qualquer código que assuma "Pendência ⇒ assinatura" precisa ser revisto.
- `APROVADA` entra no enum `StatusAta` (backend), no CHECK de `status_ata` (migration 040) e no tipo `StatusAta` do frontend (duplicado em dois locais — não consolidado nesta fatia).
- A tela terminal de `APROVADA` tem badge próprio, resumo de Pendências com link para o painel e o PDF preliminar como documento de referência; **sem** card de Signatários (não há Envelope). _(A **cor** do badge foi revista pela issue #65 — ver **Revisão** abaixo.)_
- **Paridade mantida**: não há notificação por e-mail ao responsável quando a Pendência nasce — isso não existe em nenhum caminho hoje (o e-mail do ClickSign é sobre *assinar*, não sobre a Pendência). Melhoria futura, igual para ambos os caminhos.

## Revisão — cor unificada "concluído" (issue #65)

A decisão original deu a `APROVADA` uma **cor própria** (sky-blue), distinta do verde de `ASSINADA`, para auditoria/relatórios não confundirem "assinada digitalmente" com "finalizada sem assinatura". A issue #65 reviu **apenas a cor de exibição**: no calendário (mensal/semanal) e no banner do detalhe, `APROVADA` e `ASSINADA` passam a usar o **mesmo verde** — a cor comunica "estado terminal concluído", que ambas compartilham.

A distinção entre as duas **não se perde**: continua explícita no **texto** do banner ("Ata Aprovada" vs "Ata Assinada Digitalmente"), no **estado** (`StatusAta`), no `audit_log` (`APROVACAO_SEM_ASSINATURA`) e nos relatórios baseados em status. O que muda é só o sinal cromático — a separação de **estado** (alternativa "Reusar o estado `ASSINADA`", descartada acima) permanece válida e intacta.
