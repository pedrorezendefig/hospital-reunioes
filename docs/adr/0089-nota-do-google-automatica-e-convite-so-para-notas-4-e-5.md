---
status: accepted
---

# Nota do Google buscada toda semana e convite ao Google só para as notas 4 e 5

Decisão do diretor no Planejamento da Demanda (PRD #1527, decisões 2, 3, 4, 17 e 21) e do Pedro no grill técnico de 11/11/2026. Hoje o ouvidor digita a nota do Google à mão no diário de Nota externa, e o Objetivo da Central de Comando "melhorar a nota no Google" aparece como em construção. Em 09/11/2026 o Google mostrava 2,5 com 1.629 avaliações.

## Decisões

1. **A nota do Google é buscada uma vez por semana pela Places API (New).** O pedido de detalhes do lugar devolve a nota (`rating`) e o total de avaliações (`userRatingCount`). O Place ID e o link de avaliação ficam na configuração da Ouvidoria; a chave da API é segredo de ambiente, criada na tela do Coolify. A busca é um job sem IA e grava no diário de Nota externa com o total de avaliações e a marca de leitura automática.

2. **A digitação à mão da nota do Google sai.** O histórico digitado fica. O Reclame Aqui continua digitado à mão, e o relatório da Diretoria continua usando o último valor de cada fonte.

3. **A Central de Comando mostra a nota.** O Objetivo "melhorar a nota no Google" deixa de estar em construção (decisão técnica do Pedro no grill; a diretoria pode rever na Conversa da Demanda). A tela mostra a nota, o número de avaliações novas do mês e se a nota melhorou ou piorou frente ao mês anterior. Como a API não entrega a avaliação de cada mês, "avaliações do mês" é a diferença do total entre a primeira e a última leitura do mês, e a tela diz isso. A tendência compara a nota geral no fim do mês com a do fim do mês anterior.

4. **A Ouvidoria repete a nota, só para leitura.** O ouvidor não vê a Central, então a tela de Nota externa mostra a nota do Google, sem edição. **Pendente da diretoria:** repetir ali também os números do teste do convite, para quem não é Super admin, é sugestão ainda sem resposta da diretoria, não decisão. Até ela responder na Conversa da Demanda, os números do teste ficam só na Central.

5. **O convite ao Google aparece só para as notas 4 e 5.** A política do Google para empresas proíbe pedir avaliação só a quem ficou satisfeito, e quem desobedece pode ter avaliações removidas ou o perfil punido. **A diretoria aceita esse risco.** O convite aparece só no QR, só quando a chave geral e a chave do ponto estão ligadas, e as duas nascem desligadas.

6. **Quem liga e desliga é a diretoria executiva**, na tela de Pontos de escuta, e toda mudança grava quem, quando, o valor anterior e o novo. A Central de Comando só lê.

7. **O teste dura 60 dias, mas não se desliga sozinho.** No fim do prazo, a Central mostra um aviso lembrando de reavaliar, e o convite continua aparecendo até alguém desligar. A Central mostra, por ponto e por período, os convites exibidos, os cliques e a taxa de clique, ao lado da série da nota. O clique é registrado antes do redirecionamento ao Google.

8. **Proibido no convite**: oferecer incentivo, pedir conteúdo específico, pedir menção a profissional e dar meta de avaliações à equipe.

## Alternativas consideradas

- **Business Profile API**: rejeitada para a fase 1. Entrega cada avaliação com data e daria a média exata do mês, mas exige OAuth do dono do perfil e aprovação de acesso pelo Google.
- **Busca diária, como pedia a especificação**: o diretor escolheu semanal.
- **Convite a todas as notas, como recomenda o Google**: rejeitada pela diretoria.

## Consequências

- A tendência do mês anda devagar: com mais de 1.600 avaliações, a nota geral muda pouco de um mês para outro.
- Se o Google punir o perfil, o caminho é desligar a chave geral; o histórico do teste fica para explicar o que aconteceu.
