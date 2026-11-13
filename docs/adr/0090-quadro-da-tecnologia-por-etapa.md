---
status: accepted
amends: 0077, 0083, 0084
amended_by: 0091, 0092, 0093
---

# Quadro da Tecnologia por Etapa

Decisão do Pedro (12/11/2026, grill no terminal em duas rodadas, todas as recomendações aceitas). Depois da emenda de 11/11 da ADR 0084, a aba Conversas ficou com a barra de filtros em cima e, embaixo, a lista de cards numa coluna de 24rem com rolagem própria, ao lado do chat do Assistente, que ocupa a direita o tempo todo. O Pedro achou a lista apertada e a rolagem cansativa, e pediu uma página só dos cards, em colunas pelas Etapas, com os filtros em cima e o agente aparecendo só quando um card é escolhido. A tela vale para o diretor e para o Desenvolvedor.

A ADR 0077 aposentou o Quadro, e a 0083 rejeitou "Painel ou Quadro com raias por pessoa". O Quadro que saiu tinha colunas de Estado manual, cartão arrastado à mão, Prioridade e Prazo: era o gestor de tarefas que a 0077 desmontou. Esta ADR traz a palavra de volta com outro sentido.

## Decisões

1. **O Quadro volta, redefinido.** As colunas são as Etapas, lidas do GitHub. Ninguém arrasta card nem muda Etapa no app (ADR 0054, decisão 3). A aba Conversas passa a se chamar Quadro; Entregas continua como está. Rejeitado: o mesmo desenho com outro nome na tela (o diretor já chama de quadro); só alargar a lista de hoje (o aperto continua).

2. **Cinco colunas.** Registrada, Em análise, Planejada, Em desenvolvimento e Entregue. A coluna Entregue junta Entregue e Em produção dos últimos 30 dias, com o selo da versão, e mostra os 8 mais recentes com "Ver todos nas Entregas", que abre a aba Entregas. Não será feita fica fora das colunas e aparece por um interruptor na barra. Rejeitado: as sete Etapas com rolagem lateral (a 1300px cada coluna fica com 185px); colunas estreitas que abrem no clique.

3. **A página rola inteira.** As colunas não têm rolagem própria e o cabeçalho de cada uma, com o nome da Etapa e a contagem, fica fixo no topo. Dentro da coluna, o card mais novo vem primeiro, pela data de abertura, a ordem que a lista já usa. Rejeitado: rolagem por coluna (repete o aperto cinco vezes); ordem pela última movimentação (pede campo novo no backend).

4. **Card compacto.** Número da Demanda, título, selo Bug ou Melhoria, iniciais do Responsável, barra de partes no PRD e os selos "Tem demonstração" e "Envio falhou". Data por extenso, quem pediu e o botão "Conversar" vão para o painel. Rejeitado: o card completo da emenda de 11/11 dentro da coluna (alonga e traz a rolagem de volta).

5. **O card abre num painel à direita, por cima do Quadro.** O painel tem o Documento do card e a Conversa da Demanda, a URL acompanha o card aberto e o "Ampliar" leva à largura toda. Painel lateral não é o modal que a emenda de 11/11 da 0084 rejeitou: o Quadro continua visível e o link do sino abre o card direto. Rejeitado: o card sempre na largura toda.

6. **O Assistente sai da tela inicial.** O botão "Novo pedido" e o clique num card Registrada abrem a conversa com o agente na largura toda, com o Documento do card montando ao vivo ao lado. Rejeitado: o chat no painel lateral (estreito para o documento ao vivo); um botão flutuante com o chat numa janela pequena.

7. **O agente só mexe no card pelos caminhos que já existem.** Continuar a conversa antes do "Criar o card" e o "Revisar com o código de hoje" (ADR 0084, decisão 3), com o botão certo no painel conforme a Etapa. Rejeitado: chat livre com o agente em qualquer card e em qualquer Etapa (backend, prompt e custo de IA novos; se vier, é outra Demanda).

8. **Barra de filtros sem Etapa.** Ficam Busca, Tipo, Origem, Responsável, o recorte do Desenvolvedor (Para mim, Minhas, Todas), "Só envio falhou" e o interruptor de Não será feita. A Etapa já é a coluna. Rejeitado: o campo de Etapa escolhendo quais colunas aparecem.

9. **No celular fica a lista de hoje**, com o filtro de Etapa. O Quadro é da tela larga. Rejeitado: uma coluna por vez com abas de Etapa.

## Consequências

- O verbete Quadro sai da lista de aposentados do `CONTEXT.md` e volta com a definição nova.
- O trabalho é só de tela: nenhuma rota, migration ou prompt muda.
- As fatias nascem bloqueadas pelas issues #1585 (Número da Demanda no card) e #1586 (a URL acompanha o card aberto), que mexem nos mesmos componentes. A #1588 (Copiar link) segue como está.
- A aba Entregas segue com os chips, como a emenda de 11/11 da 0084 deixou.
