# Central de Comando

A Central de Comando é o lugar da diretoria para acompanhar como o hospital aparece na internet: os números do Site e do Instagram, lado a lado, com a comparação com o período anterior. Ela é uma seção da Administração do aplicativo, entre Atendimento e Tecnologia, e serve para ler, não para mudar nada: nenhuma tela da Central escreve no Site nem publica no Instagram.

Antes ela era um painel separado, com endereço e senha próprios. Agora mora dentro do aplicativo, com o mesmo login de sempre.

Toda Demanda sobre um número da Central, sobre uma tela dela ou sobre o conector com o Claude pertence a este Produto. Conteúdo do Site é do Produto Site.

## Quem vê

Só quem é Super admin no aplicativo. Secretária e facilitador não veem a seção no menu e, se abrirem o endereço de uma tela, não recebem número nenhum. Não existe lista à parte de quem pode ver: promover alguém a Super admin passa a mostrar a Central para essa pessoa, e deixar de ser Super admin tira o acesso na hora.

## As quatro telas

- **Visão Geral**: o resumo em uma tela só. Mostra os Visitantes do Site no período, o Instagram num relance, os Objetivos em foco, atalhos para as outras telas e, no pé, o bloco O que vem por aí, com o que ainda vai nascer (o menu só lista o que já funciona).
- **Objetivos**: as direções da diretoria, cada uma vista por uma lente própria, com os números que importam para ela e sugestões que dizem o porquê. Hoje são seis Objetivos: atrair mais visitantes para o Site, crescer no Instagram, aumentar o engajamento no Instagram, gerar mais contatos, levar mais gente para uma Área do site e melhorar a nota no Google. Os dois últimos ainda aparecem como em construção, porque o dado deles ainda não chega.
- **Dados do Google**: o Site em detalhe, com números do Google Analytics. Visitantes e Visitas, o movimento dia a dia, as Áreas do site mais procuradas, a Origem do público (busca, direto, redes, indicação), os dispositivos e os Contatos gerados, que são os cliques para falar com o hospital por canal (agendar, WhatsApp, Fale Conosco e telefone).
- **Instagram**: a conta do hospital, só o orgânico. Seguidores, com o crescimento no período, Alcance, Visualizações, Interações e as Principais publicações.

O período se escolhe na tela: 7, 28 ou 90 dias, sempre terminando ontem, porque o dia de hoje ainda está pela metade. No Instagram, e nos Objetivos do Instagram, só existem 7 ou 28 dias, porque a fonte não entrega mais que 30 dias de números. Quando um número ainda não é medido, a tela diz que não é medido, em vez de mostrar zero.

## Ao vivo e Atualizar agora

**Ao vivo** é quantas pessoas estão no Site neste momento. É o único número em tempo real da Central: aparece na Visão Geral, se renova sozinho a cada 30 segundos enquanto a tela está aberta e nunca é guardado. Se a consulta falha, o último número fica na tela em vez de virar zero.

Os outros números são guardados por uma hora, para a tela abrir rápido sem pedir tudo de novo ao Google e ao Instagram a cada visita. Cada tela mostra de quando é o número que está sendo exibido. **Atualizar agora** busca números novos na hora, sem esperar a hora vencer. Se a fonte falha nesse momento, a tela mantém o último número bom e avisa que a atualização não deu certo, com o motivo, em vez de apagar o que já estava ali.

Logo depois de uma atualização do aplicativo, a primeira abertura de cada tela vai direto à fonte e pode demorar um pouco mais.

## Ligar a Central ao Claude

Quem é Super admin pode conectar a Central ao próprio Claude e perguntar em português como estão o Site e o Instagram, com os mesmos números das telas. O conector só lê, roda na assinatura do Claude da própria pessoa e não custa nada ao hospital.

Para ligar, a pessoa adiciona um conector personalizado nas configurações do Claude e entra com o mesmo e-mail do cadastro no aplicativo: é por ele que a Central reconhece quem é Super admin. O passo a passo está no guia do conector; quem não tiver o guia pede à Vitta por uma Demanda neste Produto. Entrar com outro e-mail não passa, e perder o papel de Super admin corta o conector na hora.

## O que costuma virar Demanda

- Um número que não bate com o que a pessoa vê no Google Analytics ou no Instagram (Defeito).
- Uma tela que não abre, ou que fica avisando que a atualização falhou (Defeito).
- O conector que parou de responder no Claude (Defeito).
- Um Objetivo novo, um número novo numa tela ou um item de O que vem por aí que chegou a hora de fazer (Novo).
- Dúvida sobre de onde vem um número ou o que ele conta (Informação).
