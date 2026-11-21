---
status: accepted
amends: 0047
---

# Limpeza dos testes da Ouvidoria: exclusão única, por fora do app

Decisão do diretor na Demanda #1913 e do Lucas no Refino (18/11/2026). As cinco Avaliações de teste e os casos abertos no mesmo período distorciam a aba Avaliações, a fila e o Painel, com prazo correndo em caso falso. O diretor pediu que sumissem por completo, sem protocolo nem trilha. A ADR 0047 diz que apagar nunca é DELETE, sem exceção. Esta ADR registra a única exceção e os limites dela. A limpeza roda pela issue #1913; até lá, nada foi apagado.

## Decisões

1. **Uma exclusão de verdade, uma vez só.** As Avaliações e as Manifestações de teste da janela saem inteiras: o caso, o protocolo, a trilha, o log de acesso, os anexos (linha e arquivo), os links do setor, as notificações, as prorrogações, as tentativas de contato e os acionamentos. Emenda as decisões 1 e 2 da ADR 0047 só para esta operação.

2. **A regra do app não muda.** O aplicativo continua sem botão, rota ou função que apague linha. A Retenção e a porta antecipada da Diretoria seguem como estão, e os gatilhos que recusam DELETE na trilha e no log de acesso continuam de pé depois da limpeza.

3. **A janela é fixa.** De 19/10/2026 à 0h até 17/11/2026 às 18h31, hora de Brasília, o instante em que o pedido nasceu. O caso conta pelo T0 e a Avaliação pela data em que foi criada. O que entrou depois fica, porque a afirmação do diretor de que tudo era teste só cobre o que existia naquela hora.

4. **A limpeza roda por fora do app, pela mão de uma pessoa.** Um script único confere a janela, lista o que sai e tira os arquivos do bucket. Um SQL avulso, rodado à mão numa transação só, apaga as linhas com os gatilhos de DELETE desligados apenas dentro dela. Não nasce migration nem função no banco.

5. **O SQL mira a lista conferida, não a janela.** Sai exatamente o que a conferência mostrou. O arquivo gerado com os ids fica fora do git.

6. **Duas travas antes de apagar.** Se a conferência não achar exatamente cinco Avaliações, o script para e a diferença vira pergunta ao diretor. Caso fora do padrão de teste (que não veio do QR nem do site, que tem e-mail recebido ligado, ou que já foi enviado a um setor ou ao Núcleo de Segurança do Paciente) espera a resposta dele na Conversa da Demanda.

7. **Sem cópia de segurança extra.** A conferência mostra só protocolo, canal, datas e estado, sem relato nem nome. Uma cópia do Dossiê na máquina de quem roda contraria o sigilo da Ouvidoria e o pedido do diretor.

8. **O registro que fica mora fora do banco.** São dois: a lista que a Vitta manda ao diretor na Conversa da Demanda, com quantas Avaliações e quais protocolos saíram, e esta ADR. A sequência de protocolos não é tocada, então os números apagados ficam como buracos.

9. **Nenhum termo novo no glossário.** A operação é única. "Nota do QR", como o pedido chama, é a Avaliação.

## Por que é surpreendente

- O glossário e a ADR 0047 dizem que linha de trilha nunca se apaga, e aqui se apagou. Quem achar um buraco na sequência de protocolos de outubro e novembro de 2026 encontra a explicação só nesta ADR e na Conversa da Demanda #1913.
- Um relatório já enviado que contou esses casos deixa de bater com o banco. O diretor aceitou.
- Os anônimos saíram junto sem ninguém conferir um por um, porque o caso anônimo não fica ligado à Avaliação e o diretor afirmou que todo caso da janela era teste.

## Alternativas descartadas

- **Usar a Retenção antecipada.** Mantém protocolo e trilha, e o caso de teste continuaria contando nos números.
- **Migration numerada com o DELETE.** Rodaria também em desenvolvimento e em todo ambiente refeito, mistura dado com schema e não alcança o bucket.
- **Função no banco chamada pelo script.** Deixaria aberta para sempre a porta de DELETE que a ADR 0047 fechou.
- **Apagar pela janela de datas direto no SQL.** Um registro manual com T0 retroativo, feito entre a conferência e a execução, sairia sem ninguém ter visto.
- **Botão de apagar Avaliação na tela.** O diretor quis uma limpeza só, e a aba Avaliações segue sem exclusão.
