# Roteiro: Quadro da Tecnologia por Etapa (PRD #1641)

Vídeo de percepção de valor do PRD #1641, "Quadro da Tecnologia por Etapa, com o card num painel e o agente na largura toda", com as fatias #1642, #1643 e #1644.

## Briefing (skill copy)

- **Quem vê:** o diretor do hospital, no computador da sala dele, querendo saber como andam os pedidos que fez à Tecnologia antes de cobrar alguém. Depois, quem usa a aba no dia a dia.
- **O que deve pensar no fim:** "abro a aba e vejo de uma vez onde está cada pedido".
- **A única ideia:** a aba Tecnologia virou um quadro, e cada pedido fica na coluna da etapa em que está.
- **A prova:** os critérios de aceite das fatias (cinco colunas com a contagem; a página rola e o cabeçalho fica no alto; o card curto com número, título, bug ou melhoria, iniciais, partes, versão, demonstração e envio falhou; Entregue com o último mês e o Ver todos nas Entregas; o painel à direita com o documento e a conversa, o Esc, o Ampliar e o link do aviso; o Novo pedido com o assistente na largura toda; o card registrado que retoma a conversa; o interruptor das que não serão feitas; a barra sem a etapa; o celular com a lista de sempre).

## Ganchos

1. **Situação (escolhido):** "Em que pé está cada pedido seu?" É a pergunta que o diretor faz antes de cobrar alguém, e a descrição de valor do PRD responde a ela. O primeiro quadro já mostra as cinco colunas se acendendo com a contagem, então funciona sem som.
2. Detalhe específico: "Vinte pedidos, cinco etapas, uma tela." Descartado: os números são dos dados de exemplo e não dizem nada ao diretor de verdade.
3. Antes e depois: "Achar um pedido era rolar uma lista apertada." Descartado como gancho: não há captura da tela antiga (o vídeo só mostra tela real), e abrir pela dor sem imagem enfraquece o primeiro quadro.

## Antes e depois

A issue descreve a situação anterior (lista de uma coluna estreita, com rolagem própria, e o chat ocupando metade da tela). Sem captura da versão antiga, ela fica fora do vídeo: o gancho já carrega a pergunta que a lista não respondia.

## Sem voz (decisão do Pedro, 13/11/2026)

Depois da folha de quadros, Pedro pediu o vídeo sem narração e com os sons de motion graphic. O texto abaixo continua sendo a mensagem do vídeo, agora só na tela, palavra por palavra, em HP Simplified. A leitura na voz B (`narracao.txt`) ficou só como metrônomo: o `tempos.json` vem dela e prende cada evento a uma palavra, mas o áudio dela não entra no MP4. O som é só de efeitos reais da biblioteca (skill `som`): whoosh nos cortes, clique no cursor, pop em cada destaque, o aviso do sino, um riser antes da assinatura e um hit na logo. Sem música.

## Texto na tela (copy + humanizer)

1. Em que pé está cada pedido seu? Agora dá pra ver tudo de uma vez.
2. A aba Tecnologia virou um quadro: cada um na coluna da sua etapa, de Registrada a Entregue.
3. Em cima, a contagem de cada coluna. Ninguém arrasta nada: a etapa muda sozinha.
4. O card é curto: número, título, bug ou melhoria, e as iniciais de quem cuida.
5. A barra verde conta as partes prontas. E, se o envio falhou, você fica sabendo ali mesmo.
6. Você rola a página, e o cabeçalho de cada coluna fica preso no alto.
7. Entregue guarda o último mês, com a versão de cada entrega e um selo quando já tem vídeo do que mudou.
8. O histórico inteiro está nas Entregas, a um clique.
9. Abra um card: o documento e a conversa com o responsável aparecem num painel à direita.
10. O quadro segue ali atrás. O Esc fecha, e o Ampliar leva pra tela inteira.
11. O aviso do sino também abre direto nesse painel.
12. Pra começar algo novo, tem o botão Novo pedido: o assistente ganha a largura toda.
13. Ficou pela metade? Clique no card registrado e a conversa volta de onde estava, com o documento se montando ao lado.
14. O que não será feito sai de vista. Um interruptor traz de volta quando você quiser.
15. No celular, a lista continua igual.
16. Uma olhada, e você sabe onde está cada pedido. (tom animado)

Nota da copy: gancho 2, uma ideia 2, ouvido 2, repetição 1 ("card", "etapa" e "coluna" repetem: termos do glossário e da tela, de propósito), cena casada 2, virada 2 (responde o gancho com a mesma pergunta resolvida), verdade 2. Total 13 de 14.

Gate anti-técnica: nenhuma palavra da lista no texto falado nem no escrito; sem travessão nem meia-risca.

## Dados de exemplo

Tudo fictício, no banco local: o diretor Augusto Medeiros pediu 22 coisas à Tecnologia; Tiago Lins e Beatriz Arantes cuidam delas. O pedido seguido de perto é a Demanda 20, "Assinatura da Ata pelo celular" (Em desenvolvimento, 2 de 4 partes), com a Conversa da Demanda entre o diretor e o Tiago. A conversa retomada é a Demanda 32, "Escala de plantão da UTI no celular" (Registrada).

## Critérios fora da tela

Os testes da regra do Quadro (entrada e saída, mutantes), o texto do kit de conhecimento do Assistente, a abertura sem movimento para quem pediu menos animação e o recorte do Desenvolvedor (Para mim, Minhas e Todas) não têm cena: ficam de fora do vídeo de propósito.

## Cenas

A tabela de cenas com tempos, tela, transição e critério de aceite fica no `cena/docs/shotlist.md` (cópia da lista de tomadas aprovada no Motion studio).
