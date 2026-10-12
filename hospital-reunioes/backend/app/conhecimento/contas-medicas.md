# Contas médicas

Contas médicas é o módulo que confere a conta hospitalar de internação antes de ela ir para a operadora. A faturista envia a conta e o prontuário completo exportados do MV; o módulo cruza os dois com a memória da operadora e devolve um Guia, a lista do que corrigir no MV, item por item. O que ela corrige vira indicador de onde a perda nasce: dispensação, regra automática, cadastro e preço, registro assistencial ou lançamento manual.

O módulo nasceu da especificação do Diretor Executivo e é entregue em três etapas. A primeira faz a conferência só por código, sem inteligência artificial: preço contra a tabela da operadora, diárias contadas pelas movimentações, prescrição contra o que foi lançado, item lançado sem registro no prontuário. A segunda traz a leitura do texto livre do prontuário por IA e o Painel com os indicadores. A terceira traz a gestão: memória editada pela tela, Validação, Conferência da coordenação, contratos e Habilitação.

Toda Demanda sobre uma tela de Contas médicas, uma conta mal lida, um preço ou uma diária que não bate pertence a este Produto.

## O que já está no ar

Por enquanto, a fundação do módulo e a carga das operadoras:

- o item **Contas médicas** no menu lateral, que aparece só para quem tem perfil no módulo;
- a tela de contas, que ainda abre vazia, com o aviso "Nenhuma conta enviada ainda";
- os perfis e as permissões de cada um, já gravados no banco;
- o lugar seguro onde os PDFs vão ficar guardados por sete dias;
- a tela Operadoras, aberta a partir da tela de contas para quem tem a permissão de regra contratual e tabelas (gestão de contas médicas e as duas diretorias).

Na tela Operadoras, a gestão envia o arquivo de memória de cada convênio, o mesmo que o diretor monta, e a memória passa a valer sem programador no meio. A tela mostra a versão, quantas regras vigentes e pendentes entraram e os parâmetros lidos do cabeçalho; os números têm de bater com o arquivo. Mandar uma versão nova aposenta a anterior. Parâmetro do cabeçalho que o sistema ainda não usa fica guardado, e a memória em vigor pode ser baixada de volta inteira. Arquivo com um número no formato de CPF é recusado, porque memória não pode ter dado de paciente. Na mesma tela a gestão cadastra os nomes de plano como o MV imprime, cada um com a operadora e a coluna de preço, e os setores do MV com a acomodação de cada um. As tabelas de preço ainda aparecem como não carregadas: a carga delas chega na próxima entrega.

Ainda não dá para enviar conta nem prontuário. O envio, a leitura da conta, a contagem de diárias, a conferência de preço e o Guia chegam nas próximas entregas da primeira etapa, uma de cada vez.

## Quem vê

O módulo tem perfis próprios, separados dos de Reuniões, POPs e Ouvidoria. São seis: faturista, coordenadora de faturamento, gestão de contas médicas, diretoria médica, diretoria executiva e credenciamento. Quem não tem nenhum deles não vê o item no menu e não consegue abrir a tela. O Super admin do aplicativo entra, como nos outros módulos.

Cada perfil vem com um conjunto inicial de permissões, tirado da especificação do diretor:

- **Faturista**: envia e corrige contas, e vê só as próprias.
- **Coordenadora de faturamento**: o mesmo da faturista, mais o Painel completo e a Conferência da coordenação. Incluir regra operacional está desligado para ela, em avaliação pelo diretor.
- **Gestão de contas médicas**: tudo, menos habilitar pessoas.
- **Diretoria médica** e **Diretoria executiva**: tudo.
- **Credenciamento**: só os contratos e o aviso de reajuste.

Hoje o perfil de cada pessoa é gravado pela equipe de tecnologia, a partir do e-mail que o diretor informa. A tela de Habilitação, que liga e desliga cada permissão por perfil, chega na terceira etapa.

## Dado de paciente

O módulo não guarda nome completo, CPF, carteira nem data de nascimento de paciente em lugar nenhum. Da paciente ficam só um rótulo curto, como "Maria S.", e a idade em anos. Os PDFs da conta e do prontuário ficam num depósito privado, que só o aplicativo alcança, e são apagados sete dias depois do envio.

## O que costuma virar Demanda

- Uma pessoa que deveria ver Contas médicas no menu e não vê, ou o contrário (Defeito, ou Informação se for dúvida sobre o perfil).
- Pedido para dar ou trocar o perfil de alguém no módulo (Informação).
- Memória recusada na tela Operadoras, ou contagem de regras que não bate com o arquivo do diretor (Defeito, ou Informação se a recusa explica o motivo, como o CPF).
- Dúvida sobre quando chega o envio de contas ou alguma das próximas entregas (Informação).
