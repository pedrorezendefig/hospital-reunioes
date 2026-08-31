---
status: accepted
---

# O email da Ouvidoria sai por processador externo (Resend, fora do Brasil)

Registro de uma decisão que já vale em produção desde o primeiro email do app e nunca foi escrita (issue #435, achado da review do PR #401). Todo email do sistema, inclusive os do módulo Ouvidoria, é entregue pelo **Resend**, um serviço de terceiro cuja infraestrutura fica fora do Brasil. O conteúdo de cada mensagem (assunto, corpo, anexos e endereço do destinatário) passa pelos servidores dele para ser entregue. Este ADR registra a decisão, delimita o que sai e prende as regras que já existem no código para que o que sai continue sendo só isso.

## Contexto

- O módulo Ouvidoria trata a manifestação como dado sensível: sigilo por tipo (ADR 0037), Dossiê separado da estatística, retenção de cinco anos com anonimização (ADR 0034), acesso registrado. Nada disso vale para o trecho do caminho que sai do hospital, e email sai do hospital por definição.
- O transporte é escolhido em `app/services/email_service.py`: Resend quando há `RESEND_API_KEY`, SMTP quando há `SMTP_USER`, e modo mock (log local, nada sai) quando não há nenhum dos dois. Em produção é o Resend.
- O remetente é `noreply@hospitalsaomatheus.cloud`; o hospital não opera servidor de email próprio, e não há intenção de operar.
- Sete tipos de email do módulo saem hoje: nova demanda ao setor, cobrança, prazo rompido, degrau de escalonamento, prorrogação (pedida e decidida), setor sem titular, aviso ao admin técnico e o relatório quinzenal/mensal à Diretoria Executiva.
- A decisão nunca foi registrada. Sem registro, a próxima pessoa a acrescentar um campo a um template não tem onde ler que aquele texto atravessa uma fronteira.

## Decisões

1. **O processador externo fica.** Entregar email por serviço de terceiro é a prática do mercado e a alternativa (servidor próprio) troca um risco de processamento por um risco de operação (reputação de IP, fila, disponibilidade) que este hospital não tem como sustentar. Resend continua sendo o primário e SMTP a reserva.
2. **O que pode sair está fechado campo a campo, e é o extrato, nunca o relato.** `_CAMPOS_DO_EMAIL` em `ouvidoria_notificacoes.py` é a lista fechada do que um email do caso pode carregar. `resumo` e `relato_integral` ficam de fora de propósito: o que viaja é `extrato_para_o_setor`, escrito pelo ouvidor na validação. Caso sem extrato manda o setor procurar a Ouvidoria pelo protocolo, e não o relato cru. Coluna nova no Dossiê não entra em email sem uma decisão explícita nessa lista.
3. **O relatório que sai por email é agregado.** O PDF do relatório quinzenal e do mensal não carrega protocolo de manifestação nenhuma (RN-40, ADR 0034 decisão 8, migration 080). O único nome próprio nele é o do responsável por cada setor, que é gente do hospital. O mesmo vale para o que a IA do relatório mensal recebe: agregado, nunca o relato.
4. **O endereço do destinatário é dado do hospital.** Todo email do módulo vai para gente do hospital (responsável de setor, gestor, Diretoria Executiva, admin técnico). O manifestante não recebe email do sistema, e o contato dele (`manifestante_contato`) não é usado como destinatário em caminho nenhum.
5. **O carimbo de entrega só nasce de envio real.** O modo mock devolve sucesso sem nada ter saído, e quem persiste estado a partir do envio pergunta antes por `email_service.transporte_configurado()` (issue #435). Uma chave rotacionada para vazio em produção passa a aparecer como falha honesta, com motivo próprio, em vez de "enviado".
6. **A chave do processador é secret de ambiente.** `RESEND_API_KEY` vive só no Coolify, nunca no repositório, e o modo mock é o comportamento do desenvolvimento local, onde nenhum email real sai da máquina de ninguém.

## Considered options

- **Servidor SMTP próprio do hospital**: rejeitado. Elimina o processador externo e cria operação contínua de reputação de IP e entregabilidade; um relatório que não chega à Diretoria porque o IP caiu em lista é pior do que o risco que se quis evitar. O caminho SMTP continua no código como reserva configurável, não como plano.
- **Provedor com processamento no Brasil**: não descartado por mérito, e sim por custo de troca hoje. A decisão fica revisitável: o ponto de troca é único (`email_service.py`), e nenhum chamador conhece o provedor.
- **Cifrar o corpo dos emails**: rejeitado. O destinatário é gente do hospital lendo em cliente comum de email; cifra ponta a ponta exigiria chave em cada leitor e derrubaria o uso real.
- **Não registrar (seguir como estava)**: rejeitado. É justamente a decisão invisível que faz um campo novo atravessar a fronteira sem ninguém notar.

## Consequences

- Assunto, corpo, anexo e endereço de destino de todo email do app passam por um processador fora do Brasil. Isso é fato do sistema, e agora é fato escrito.
- Acrescentar campo a template de email da Ouvidoria passa a ser mudança com este ADR do lado: se o campo não está em `_CAMPOS_DO_EMAIL`, a pergunta é se ele pode sair, não como fazê-lo caber.
- O caminho para trocar de provedor continua estreito de propósito: um arquivo, nenhum chamador acoplado.
- Fica pendente para o humano, fora do escopo desta issue: conferir se o contrato com o Resend e o aviso de privacidade do hospital refletem o que está escrito aqui.
