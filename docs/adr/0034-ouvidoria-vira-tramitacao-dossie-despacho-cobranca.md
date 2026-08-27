---
status: accepted
amended_by: 0036
---

> Emenda em prosa ao ADR 0031 (decisão 3, "índice, não dossiê"). Sem ponteiro `amends` no frontmatter: o 0031 já está emendado pelo 0032 e o lint de ADR aceita um único ponteiro por campo.

# Ouvidoria vira tramitação: dossiê no app, despacho por link tokenizado e cobrança com escalonamento

Decisão do Pedro (20/ago/2026, grilling a partir do áudio do diretor e da especificação funcional dele, `Especificacao_Modulo_Ouvidoria.md` v1.0 de 19/ago): a ouvidoria deixa de ser um índice passivo e vira o **centralizador de manifestações** do hospital. A manifestação completa passa a viver neste app, tramita por setores com prazo por gravidade em calendário útil, e o sistema cobra sozinho com escalonamento progressivo. Este ADR emenda a decisão 3 do ADR 0031 (invariante "índice, não dossiê"), que deixa de valer.

## Contexto

- O ouvidor hoje trabalha com papel, planilha manual e cobrança por email à mão. Manifestações chegam por muitos canais sem registro único; há caso aberto 13 dias sem retorno.
- A especificação do diretor é a **fonte funcional** (princípios, regras RN-xx, prazos, papéis). A adequação técnica parte da stack existente: nomes de campo, formato de protocolo e mecanismos seguem o app, não a letra da spec.
- O que já existe (ADR 0031, prod v0.58.1): tabela `ouvidoria_protocolos` com número `ANO-NNNN` por sequence, API `/api/ana/ouvidoria/*`, painel `/ouvidoria`, e a Ana registrando protocolo em produção. É a fundação; nada disso se perde.
- A Ana ainda não está no WhatsApp oficial (que segue no Kommo, com humanos); o canal vivo dela é o Telegram de teste.

## Decisões

1. **Dossiê no app** (emenda o ADR 0031, decisão 3): a manifestação completa (relato integral sem edição, nome e contato do manifestante, anexos) é gravada neste banco. Aceita manifestação anônima. Denúncia e relato de conduta nascem com sigilo reforçado.
2. **Protocolo mantém `ANO-NNNN`** contínuo por sequence (ADR 0031, decisão 5), rejeitando o formato `OUV-ANO-NNNNN` com reinício anual da spec: números já foram comunicados a pacientes e reiniciar numeração é proibido. Prefixo "OUV-" pode virar exibição, nunca dado.
3. **Validação antes do despacho**: toda manifestação nasce aguardando classificação; só `ouvidor` ou `diretoria_executiva` valida e aciona a área; nenhum processo automático despacha. O manifestante recebe o protocolo na hora do registro.
4. **O link tokenizado É o portal do setor**: o titular recebe email com link seguro, sem login, que abre a manifestação e permite responder, anexar e pedir prorrogação, inclusive no celular. Mesmo padrão do Aceite interno (ADR 0030). Login de `responsavel_setor` foi rejeitado nesta leva: a função da spec é atendida sem gestão de contas.
5. **Setor ganha responsáveis nomeados**: titular e ao menos um substituto, com vigência (`setor_responsavel`). Setor sem titular vigente não é acionável: a demanda sobe ao gestor da área com alerta à Diretoria. Conduta médica roteia ao coordenador da especialidade, nunca ao médico; queixa de call center vai direto à Diretoria.
6. **Prazo por gravidade, configurável, em calendário útil**: tabela de prazos em banco (editável pela `diretoria_executiva`, com histórico), 4 níveis (crítico, alto, médio, baixo), contagem em horas/dias úteis com feriados administráveis, e os 4 marcos de tempo (T0 entrada, T1 validação, T2 resposta da área, T3 conclusiva), medindo ouvidoria e área separadamente. Prazo hardcoded foi rejeitado: a tabela do diretor ainda muda em 28/08.
7. **Cobrança com escalonamento progressivo**: véspera avisa o titular; vencimento, titular + substituto; +24h, gestor da área; +48h, Diretoria Executiva. Crítico notifica a Diretoria já na validação. Emails via Resend, registrados e reenviáveis. A versão simples (setor + cópia ao ouvidor) foi substituída pela cadeia da spec: o próprio diretor pediu para entrar no circuito.
8. **Acesso**: nascem os perfis `ouvidor` e `diretoria_executiva`. Dossiê completo: só os dois. Sigilo reforçado: só os dois, e o Super admin técnico fica **fora** (RN-40; precedente da área Controle, mais estreita que Super admin). Demais papéis de Reuniões veem apenas o índice. O setor recebe só o extrato necessário, sem identificação quando sigiloso.
9. **Canais da primeira leva**: registro manual pelo ouvidor (telefone, balcão, email, com data retroativa e anexos) + **formulário público** sem login com rate limit e protocolo na tela. **QR code setorial** imprime URL própria parametrizada (`/ouvidoria/qr?setor=X&ponto=Y`): hoje ela abre o formulário pré-preenchido; quando a Ana entrar no WhatsApp oficial, o servidor passa a oferecer a conversa primeiro, sem reimprimir cartaz. Deep link direto do WhatsApp foi rejeitado enquanto lá atende humano do Kommo. Instagram/Facebook/email/Google/Reclame Aqui: fases seguintes.
10. **Sem IA de triagem própria nesta leva**: entrada por formulário ou manual chega sem classificação e o ouvidor classifica na validação. A classificação sugerida que já vem da Ana é persistida à parte (`classificacao_ia`) e nunca sobrescreve a validada.
11. **O POST da Ana cresce**: campos opcionais de dossiê (nome, contato, relato integral, gravidade sugerida com confiança) para não quebrar a Ana atual; depois o prompt dela (repo `~/PedroDev/Ana`) passa a preenchê-los. Entregas casadas, uma por repo.
12. **Fatiamento em 3 PRDs sequenciais**: (1) Núcleo + entrada: modelo, estados, registro manual, validação, despacho por link, prazos configuráveis em calendário útil, notificações básicas, formulário + QR, API da Ana adaptada; (2) Governança de prazo: prorrogação única pré-vencimento, devolução por insuficiência com meio prazo, pausa aguardando manifestante, cadeia completa de escalonamento, emails com estratificação de cor; (3) Inteligência: relatórios quinzenal/mensal automáticos, painel da Diretoria, reincidência.

## Considered options

- **Manter "índice, não dossiê" e o setor ler no Chatwoot:** rejeitado. Setores não têm Chatwoot e a maioria dos canais não gera conversa lá.
- **Login para responsável de setor (portal com conta):** rejeitado nesta leva; o link tokenizado entrega as mesmas funções sem gestão de senha. Revisita se o uso provar necessidade.
- **Prazo fixo no código, dias corridos:** rejeitado; contraria RN-21/22 e a tabela ainda em validação.
- **Super admin vê tudo:** rejeitado; RN-40 exige sigilo de denúncia restrito a ouvidor e diretoria.
- **Protocolo `OUV-` com reinício anual:** rejeitado; quebraria continuidade já pública (ADR 0031).
- **Google Forms como paliativo:** desnecessário; a fundação já está em produção.

## Consequences

- O app passa a guardar dado pessoal e por vezes sensível (LGPD): acesso mínimo por perfil, trilha imutável de movimentos, log de acesso, pseudonimização antes de IA externa, retenção de 5 anos com anonimização.
- **O texto da resposta do setor é dado imutável** (a partir da issue #374): a resposta viaja inteira para `ouvidoria_movimentos.observacao`, uma cópia por ciclo de resposta. A trilha é append-only por gatilho (migration 064): DELETE é recusado sem exceção, inclusive para o super admin, e a manifestação tem `ON DELETE RESTRICT`. O único UPDATE aceito é o da retenção (migration 064, revista pela 079): zerar a coluna `observacao` de manifestação encerrada há mais de cinco anos, e nada além disso. Consequência prática: **esse texto não tem caminho de redação sob demanda**. A retenção não substitui um: ela é automática, por prazo, e apaga o caso inteiro, sem escolher trecho nem titular. Se o relato do manifestante trouxer detalhe identificador de paciente, ele fica no banco até o prazo vencer.
- Nasce o segundo link público tokenizado do sistema (padrão do Aceite interno) e o primeiro conjunto de jobs de SLA (cálculo periódico, calendário útil, escalonamento).
- O Setor deixa de ser só taxonomia: ganha titular, substituto e gestor como destinatários operacionais.
- A máquina de estados atual (aberto/respondido/encerrado) é substituída pela da spec (novo, em classificação, aguardando área, aguardando manifestante, respondido, encerrado), com mapeamento dos registros existentes; o detalhe vive nos PRDs.
- O lado Ana ganha entrega casada (prompt preenchendo o dossiê); enquanto não sobe, protocolos da Ana chegam resumidos e o ouvidor completa na validação.
- A expansão da Ana como primeira camada de TODO o atendimento (seção 3 da spec) é assunto do programa da Ana, no repo dela, não destes PRDs.

## Em aberto

- **Caminho de redação para pedido de titular (LGPD, artigo 18).** Não existe hoje, e a decisão acima o descarta por construção. A consequência é aceita nesta leva porque a trilha já guardava texto livre antes da issue #374 (motivo da devolução, motivo da pausa), então a mudança foi de volume, não de natureza. Fica registrado como item aberto, não como decisão de que nunca será preciso: se o hospital receber pedido de eliminação ou anonimização de titular sobre manifestação viva, hoje só há como responder que o dado permanece até a retenção. O desenho de saída (por exemplo, guardar o texto em coluna apagável e deixar no movimento apenas a referência ao ciclo) sai em issue própria quando o hospital pedir.
