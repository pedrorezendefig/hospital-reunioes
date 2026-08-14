---
status: accepted
amends: 0003
---

# Pendência nasce por assinatura: gatilho incremental e Aceite interno

O ADR 0003 fixou que Pendência nasce de estado terminal (ASSINADA ou APROVADA). No caminho com ClickSign isso significava esperar o Envelope fechar com todas as assinaturas, e a prática expôs dois problemas. Primeiro, a ClickSign finaliza o documento sozinha após o deadline (30 dias) mesmo com assinaturas faltando, e esse evento caía no ramo "sem ação definida" do webhook: a Reunião ficava presa em `AGUARDANDO_ASSINATURA` para sempre e as Pendências nunca nasciam. Segundo, quem assinava cedo já tinha se comprometido com as ações dele, mas as Pendências só apareciam dias depois, quando o último signatário (ou o deadline) fechava o documento.

## Decisões

**1. Gatilho incremental por assinatura.** A Pendência nasce assim que o compromisso do responsável se firma, sem esperar o estado terminal:

- Signatário assina no ClickSign: nascem na hora todas as Pendências cujo responsável é ele. A Pendência é **plena** desde o primeiro segundo (painel, prazo correndo, cobrança, pode virar ATRASADO), indistinguível das demais.
- O Facilitador da Reunião assina: nascem também as Pendências de responsáveis que **não** são Signatários do Envelope (a assinatura de quem conduziu autoriza os demais). Se o Facilitador não estiver no Envelope, essas ficam para a finalização.
- Documento finaliza: nasce todo o resto, e a Reunião vai a `ASSINADA`.

**2. Deadline é finalização, não morte.** Quando o prazo da ClickSign estoura, o documento fecha com as assinaturas que tiver. O sistema trata esse evento como fechamento normal: cria as Pendências restantes, avança a Reunião para `ASSINADA` e registra quem não assinou. O banner terminal ganha um selo **discreto** "N de M assinaram" apenas quando houve faltantes ou Aceites internos; com 100% de assinaturas ClickSign, o visual atual permanece intacto. Nuance da doc oficial (evento `deadline`, comportamento default `deadline_partial_signature_action: closed`): a ClickSign só finaliza se houver **ao menos uma** assinatura; com zero assinaturas ela **cancela** o documento, e aí vale a decisão 3 (modo de Aceite interno).

**3. Recusa ou cancelamento abrem o modo de Aceite interno.** O Envelope morre de verdade e **não há reenvio ao ClickSign**. A Reunião permanece em `AGUARDANDO_ASSINATURA` num sub-modo interno (flag no banco, sem estado novo na máquina):

- As Pendências já nascidas são mantidas; as ações correspondentes ficam travadas para edição. Só ações sem Pendência seguem editáveis.
- Cada Signatário pendente com ações recebe email do próprio sistema com link público tokenizado para o **Aceite interno**: a página mostra a ata completa e um botão único "Li e aceito"; o aceite faz nascer todas as Pendências dele de uma vez e conta como o "assinou" dele no desfecho. Signatário sem ação não recebe link e não trava nada.
- O Super admin pode **registrar o aceite em nome de um signatário** pendente, por signatário, com registro em `audit_log` (quem forçou, quando) e origem marcada.
- Terminal: quando toda ação do quadro tem Pendência nascida, a Reunião vira `ASSINADA` com o selo de assinaturas mistas.

**4. Reconciliação ativa.** Além de tratar o evento de deadline no webhook, um cron diário varre as Reuniões em `AGUARDANDO_ASSINATURA` com Envelope e consulta a ClickSign: documento já fechado aplica o mesmo fluxo do webhook (idempotente). O card de Signatários ganha um "Sincronizar" manual como atalho. Isso resolve o passivo de atas já travadas e protege contra webhook perdido.

**5. Persistência do aceite por signatário.** Passa a existir registro por signatário com a origem do compromisso (`clicksign`, `aceite_interno`, `super_admin`) e timestamp. Hoje nada disso é persistido: o status de assinatura é consultado ao vivo na API, o que impede selo, desfecho e auditoria.

**6. Idempotência por ação.** `liberar_pendencias` ganha modo incremental: a guarda deixa de ser "já existe alguma Pendência desta Reunião" e passa a ser por ação do quadro. A numeração `A###` precisa aguentar criação concorrente (webhooks de assinatura chegam em paralelo).

## Por que é surpreendente

- Pendência agora nasce **antes** do estado terminal: quem lê o código (ou o ADR 0003) esperando "Pendência implica Reunião encerrada" quebra. `AGUARDANDO_ASSINATURA` passa a conviver com Pendências plenas e ativas.
- Recusa e cancelamento **não devolvem mais** a Reunião para `AGUARDANDO_VALIDACAO`. O retorno com ata editável deixa de existir nesse caso; o caminho é seguir em frente colhendo Aceites internos.
- `ASSINADA` deixa de garantir "todos assinaram digitalmente": pode conter aceites internos, aceites forçados e faltantes de deadline. A verdade fina vive no registro por signatário.

## Alternativas descartadas

- **Pendência provisória até a finalização** (nasce marcada, prazo não corre): criaria um sub-estado novo na máquina da Pendência e a pergunta "o que o Colaborador pode fazer com ela". A assinatura do responsável já é o compromisso; a Pendência nasce plena.
- **Criar as Pendências de não-signatários na primeira assinatura de qualquer um**: o compromisso dos outros nasceria da assinatura de alguém sem papel de condução. O gatilho é a assinatura do Facilitador; sem ela, finalização.
- **Estado novo `ASSINATURA_INTERNA` na máquina**: mais claro na leitura, porém mexe em migration, tipos duplicados de StatusAta no frontend, calendário, filtros e relatórios. A flag de sub-modo dentro de `AGUARDANDO_ASSINATURA` entrega o mesmo com menos superfície.
- **Terminal `APROVADA` para o caso misto**: esconderia que houve assinaturas digitais reais. `ASSINADA` com origem registrada por signatário preserva a auditoria.
- **Cancelar as Pendências nascidas quando o Envelope morre**: jogaria fora compromissos já firmados por quem assinou. Elas são mantidas, e a edição da ata fica limitada às ações ainda sem Pendência.
- **Permitir reenvio ao ClickSign após recusa/cancelamento**: reabriria o risco de Envelopes duplicados e de Pendências duplicadas entre envios. O caminho pós-morte do Envelope é interno.

## Consequências

- O ADR 0003 fica **amendado**: cai o invariante "Pendência nasce somente de estado terminal". O caminho sem assinatura (`APROVADA`) permanece intacto: lá as Pendências continuam nascendo todas na aprovação.
- O webhook passa a tratar os eventos de assinatura individual e de fechamento por deadline (hoje ignorados); o ramo que devolvia expiração para `AGUARDANDO_VALIDACAO` está errado e sai.
- Tabela nova de aceites por signatário; `SignatariosCard` ganha a linha "Pendências criadas: X de Y" (Y = ações do quadro) pelo polling existente.
- Surge edição **parcial** de ata em `AGUARDANDO_ASSINATURA` (modo interno, só ações sem Pendência), coisa que hoje não existe em nenhum estado pós-validação.
- O glossário ganha o termo **Aceite interno**; "assinar" continua reservado ao ClickSign.
