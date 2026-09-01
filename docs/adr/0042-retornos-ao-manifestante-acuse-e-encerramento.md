---
status: accepted
---

> Emenda em prosa às decisões 2 e 5 do ADR 0039: o manifestante passa a receber email do sistema em dois caminhos fechados (decisão 5), e este ADR é a decisão explícita que a decisão 2 exige para os campos desses dois emails novos, o destinatário `manifestante_contato` e o corpo com protocolo e desfecho em linguagem simples. Sem ponteiro `amends` no frontmatter: o 0039 já é emendado pelo 0041 e o lint de ADR aceita um único ponteiro por campo, como o próprio 0037 fez com o 0034.

# Retornos ao manifestante: acuse em horas corridas e aviso de encerramento

O catálogo de notificações da Ouvidoria tem 12 gatilhos e todos são internos (setor, gestor, Diretoria). Depois de receber o protocolo na abertura, o manifestante nunca mais ouve do sistema: não há acuse de recebimento (D-07) e o encerramento no sistema não é encerramento para o paciente (RN-80). A migration 065 excluiu o marco `acusar_recebimento` do motor de prazos úteis de propósito, apontando que ele pertence ao catálogo de notificações; o catálogo nunca o recebeu.

## Decisões

1. **O marco `acusar_recebimento` entra na tabela de prazos em horas corridas** (RN-56): 24 horas para todas as gravidades, mesmo dia para `critico`. Fora do calendário útil: acuse é promessa ao paciente e corre em relógio de parede. Quem reclama sexta à noite recebe o aviso no sábado, não na terça. É o único marco da tabela fora do calendário útil, e a unidade fica explícita na linha.

2. **O acuse sai automático na abertura** quando o caso tem contato utilizável, por qualquer canal. Com isso o marco fica cumprido no segundo zero e o prazo de 24h vira rede de segurança para falha de envio, não meta de trabalho manual. O acuse ignora a janela comercial das notificações internas: segurar o acuse até a próxima abertura quebraria as 24 horas corridas.

3. **O aviso de encerramento (RN-80) dispara na transição de encerramento**, com protocolo, desfecho em linguagem simples e o canal para reabrir. Nasce como registro em `ouvidoria_notificacoes` antes do envio, como toda notificação da casa. O marco T3 continua sendo `encerrada_em`.

4. **v1 por email.** Caso anônimo ou sem email utilizável no contato é encerrado sem disparo, com marcação própria, e sai do denominador do indicador de resposta conclusiva (RN-81). O canal de origem completo (WhatsApp via plataforma da Ana, resposta pública no Google) é fase seguinte; a divergência com a letra da RN-80 fica registrada na resposta à Diretoria.

## Consequências

- Migration nova amplia os dois CHECKs de `ouvidoria_prazos`, travados desde a migration 065: o marco `acusar_recebimento` entra na lista de marcos, e a unidade de horas corridas entra na lista de unidades.
- Dois gatilhos novos no CHECK de `ouvidoria_notificacoes`: `acusar_recebimento` e `encerramento_manifestante`. São os primeiros com o manifestante como destinatário: a decisão 5 do ADR 0039 deixa de valer para esses dois caminhos, e `manifestante_contato` passa a ser usado como destinatário exclusivamente neles. O conteúdo desses emails é mínimo (protocolo, desfecho em linguagem simples, canal para reabrir), sem relato e sem identificação de terceiros; a lista `_CAMPOS_DO_EMAIL` dos emails internos não muda por este ADR.
- O contato do manifestante é texto livre; o envio depende de reconhecer um email nele. O caso sem email reconhecível segue o caminho da marcação própria da decisão 4.
- O detalhe do caso e a tabela de prazos exibem o marco novo (RN-56).
- Quando o caminho WhatsApp existir, as decisões 3 e 4 não mudam: muda só o transporte.
