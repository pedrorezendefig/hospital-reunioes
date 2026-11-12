---
status: accepted
amends: 0036
---

# O QR da Ouvidoria vira Avaliação com funil para a manifestação guiada

Decisão do diretor no Planejamento da Demanda (PRD #1527, 27 decisões de negócio) e do Pedro no grill técnico de 11/11/2026, sobre a especificação "Escuta por QR, Avaliações, NSP e Painel" da Diretoria Executiva (10/11/2026). Hoje o cartaz abre direto o formulário público, e toda leitura vira protocolo com prazo. Em setores com muita insatisfação, como a emergência e o centro médico, isso produziria mais casos do que a Ouvidoria consegue tratar, e transformaria em fila o que na maior parte é uma avaliação rápida.

## Decisões

1. **O QR abre a Avaliação, que não gera protocolo.** A pessoa dá uma nota de 1 a 5, escolhe se quiser os motivos (lista fechada de oito: atenção da equipe, tempo de espera, informação recebida, limpeza, conforto, atendimento médico, atendimento de enfermagem, recepção) e deixa um comentário opcional de até 500 caracteres. A avaliação é gravada no envio, antes de qualquer escolha seguinte, e vira dado de gestão, não caso.

2. **A avaliação não guarda nada de quem avaliou.** Sem IP, sem identificador do aparelho, sem contato. O abuso é contido por limite de envios (3 a cada 10 minutos por endereço e cartaz; decisão técnica do Pedro no grill, a diretoria pode rever na Conversa da Demanda), contado só na memória do limitador e nunca gravado.

3. **O funil depois da nota.** Notas 1, 2 e 3 perguntam se a pessoa quer retorno; o "sim" leva à manifestação guiada. Notas 4 e 5 agradecem e oferecem deixar um elogio (e o convite ao Google, ADR 0089). Quem segue para a manifestação a partir da nota fica com o caso ligado à avaliação e ao cartaz, **exceto quando escolhe o anonimato**: aí o caso guarda o local que a pessoa confirmou e não guarda o código do cartaz nem a ligação com a nota, como já é hoje.

4. **A avaliação convertida pelo ouvidor guarda o cartaz e a ligação.** Converter em manifestação é ato do ouvidor na aba Avaliações: o caso nasce com canal `qr`, o setor e o ponto do cartaz, o comentário como relato, tipo vazio (logo sigiloso até a classificação) e T0 igual à hora da avaliação, como no e-mail recebido (ADR 0051). A pessoa não pediu anonimato, e o local ajuda a apurar.

5. **A URL impressa passa a ser curta: `/a/{código}` (emenda a decisão 2 da ADR 0036).** As URLs antigas (`/ouvidoria/qr?p=` e `/manifestacao?p=`) redirecionam para ela. O código continua o mesmo e continua sendo a única coisa que o cartaz carrega (decisão 4 da ADR 0036 segue). Ponto inativo leva à manifestação guiada sem origem, nunca a uma página de erro (decisão 6 segue). Quem chega pelo site vai direto à manifestação guiada, sem tela de nota, porque a nota é sempre de um cartaz.

6. **A manifestação guiada tem cinco passos**: identificação (com identificação ou anônimo, escolhido primeiro), sobre o quê, quando e onde, o que aconteceu e contato. Os dados novos do caso são a data e o período da ocorrência, a hora aproximada, o local informado (o setor que o manifestante escolheu, que não é a área responsável), o quarto (só em ala de internação), os profissionais citados, a data de nascimento do paciente e o que a pessoa espera (resposta, providência ou só registrar). Quem se identifica deixa telefone ou e-mail, ao menos um, e quem deixa só telefone vê o aviso de que as respostas saem por e-mail.

7. **O anônimo ganha código de acompanhamento e a página pública de acompanhamento.** O código é mostrado uma vez e só o hash é guardado. A página recebe protocolo e código (anônimo) ou protocolo e contato (identificado), e mostra só o estado em linguagem simples, a data da última movimentação e a resposta institucional. Nunca setor interno, responsável ou anotação.

8. **Só o Perfil da Ouvidoria vê a aba Avaliações**, porque o comentário não é classificado e pode trazer coisa séria. O Super admin fica de fora, como no Dossiê.

9. **Retenção.** O comentário da avaliação é apagado cinco anos depois de criado; a nota e os motivos ficam para os números. Os dados novos do caso (paciente atendido, data de nascimento, profissionais, quarto) saem junto com o relato, pelos cinco anos ou pela porta antecipada da diretoria executiva (ADR 0047).

10. **O Ponto de escuta ganha os campos do cartaz**: nome público (o que o paciente vê, nunca o nome interno do setor), descrição do local, título do cartaz (dois modelos), código de controle impresso fora da moldura, marca de ala de internação e a chave do teste do Google. O cartaz passa a A4 em PDF vetorial, no layout aprovado pela Diretoria.

## Alternativas consideradas

- **Manter o QR abrindo o formulário**: rejeitada. Todo descontentamento rápido viraria protocolo com prazo.
- **Guardar o IP para conter abuso**: rejeitada. A avaliação promete não identificar ninguém; o limite em memória basta para uma pessoa não mexer na média.
- **Um campo `origem` novo no caso**: rejeitado. O canal de origem que já existe, mais a ligação com a avaliação, já distinguem o caso que veio pela nota do que veio direto.

## Consequências

- A Ouvidoria passa a ter dois volumes: avaliações (sem fila, sem prazo) e manifestações (com fila). Os números da avaliação vivem na aba Avaliações.
- Os cartazes só vão para a parede com a fase 1 inteira em produção (decisão 15 do diretor).
