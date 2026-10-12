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

Na tela Operadoras, a gestão envia o arquivo de memória de cada convênio, o mesmo que o diretor monta, e a memória passa a valer sem programador no meio. A tela mostra a versão, quantas regras vigentes e pendentes entraram e os parâmetros lidos do cabeçalho; os números têm de bater com o arquivo. Mandar uma versão nova aposenta a anterior. Parâmetro do cabeçalho que o sistema ainda não usa fica guardado, e a memória em vigor pode ser baixada de volta inteira. Arquivo com um número no formato de CPF é recusado, porque memória não pode ter dado de paciente. Na mesma tela a gestão cadastra os nomes de plano como o MV imprime, cada um com a operadora e a coluna de preço, e os setores do MV com a acomodação de cada um.

Também na tela Operadoras entram as tabelas de preço de cada convênio. A gestão escolhe a operadora e a categoria (materiais, medicamentos, diárias e taxas ou pacotes), informa o início da vigência e, se houver, o fim, e envia a tabela de preço no arquivo de planilha separado por ponto e vírgula que o diretor entrega. O sistema reconhece sozinho o tipo da tabela pelas colunas da primeira linha e diz quantos itens entraram; arquivo com colunas que ele não conhece é recusado, e a mensagem lista as colunas esperadas. Uma versão nova não apaga a anterior: as duas ficam lado a lado, e a conta de um atendimento antigo usa a tabela que valia na data do atendimento. Para cada operadora, a tela mostra cada categoria com a tabela, a versão, a vigência e a situação (carregada ou não carregada). Honorário aparece sempre como não carregado, porque a tabela de honorários ainda não chegou; categorias que só a memória de uma operadora traz, como SADT e porte anestésico, aparecem do mesmo jeito. Preço que a memória da operadora dá como validado vale mais que a tabela.

Na mesma tela entra o dicionário de itens do hospital: o nome do produto na prescrição e na ficha anestésica, com os sinônimos, ligado ao código da conta (por exemplo, rocurônio e Esmeron caem no mesmo código). Termo que já existe é atualizado. Quando o nome não está no dicionário, o sistema tenta casar pela marca e pela concentração; só pela marca, o casamento sai com confiança média.

Na conferência, um preço que não pode ser comparado com a tabela sai como "Não conferido", e nunca como erro de preço: tabela não carregada para a categoria, nenhuma versão vigente na data do atendimento, preço zero na tabela, item que a tabela marca como pacote, código que aparece repetido na tabela sem a especialidade que desempata, e honorário.

Ainda não dá para enviar conta nem prontuário. O envio, a leitura da conta, a contagem de diárias e a conferência de preço chegam nas próximas entregas da primeira etapa, uma de cada vez. A tela do Guia já existe e é descrita abaixo; ela passa a ter linhas quando o envio e a conferência entrarem no ar.

## O Guia

O Guia é a tela de uma conta com a lista do que corrigir no MV. Foi feito para caber em meia tela, ao lado do MV, e vira lista em telas estreitas.

No topo ficam o número do atendimento, o rótulo da paciente, a conta, a operadora, a coluna de preço, o período da parcial e a situação. Quando o prontuário veio incompleto, aparece a faixa "PARECER PARCIAL" com a lista do que faltou. Logo abaixo, três números: a **Nota de entrada** (de 0 a 100, quanto a conta estava certa antes da correção), o **R$ a ajustar** (com quantos itens e quanto mais está em validação) e os **Itens feitos** (quantos a faturista já marcou, de quantos).

As linhas vêm agrupadas por dia e setor, como "03/10 · CTI". Cada linha começa pelo verbo (Incluir, Ajustar quantidade, Corrigir preço, Retirar ou Validar) e traz a quantidade, o período, o valor com sinal e o código, que copia com um clique. "Ver evidência" abre a página do prontuário e o trecho que sustenta a linha. A etiqueta cinza "Não conferido" marca o valor que não pôde ser conferido contra a tabela da operadora: ele fica fora da nota e do R$ a ajustar.

Em cada linha, três botões:

- **Feito**: a faturista corrigiu no MV. Um clique, e a linha recolhe em verde.
- **Não procede**: a linha está errada. Pede um de quatro motivos (já está na conta, sem evidência no prontuário, a regra é outra, outro); o texto é opcional, menos em "outro". Vai para a gestão como observação.
- **Bloqueado**: o MV não deixou lançar, por falta de cadastro ou de preço. Um clique.

Enquanto a conta não foi concluída, toda marcação tem "Desfazer". "Marcar o dia como feito" marca de uma vez as linhas abertas do grupo. A linha Validar não tem botão: o item já foi para a validação da gestão, e a faturista não precisa decidir.

No rodapé ficam a observação opcional para a gestão e o botão "Concluir e abrir a próxima", sempre habilitado. Com item sem marcação, o app pergunta "Concluir assim mesmo?". Concluir abre a próxima conta A fazer da faturista, na ordem de envio. A conta fica Concluída quando tudo foi resolvido, ou Concluída com pendência quando sobrou linha sem marcação, bloqueada ou em validação. Na conclusão a nota de entrada é refeita sem as linhas Não procede; a nota original fica guardada.

Abrir o Guia pela primeira vez muda a conta de A fazer para Em correção. A faturista só abre as próprias contas; quem tem o Painel completo abre a de qualquer uma.

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
- Tabela de preço recusada, contagem de itens que não bate com o arquivo, ou preço "Não conferido" onde a tabela tem valor (Defeito, ou Informação se a recusa lista as colunas esperadas ou se o motivo é um dos casos de "Não conferido").
- Um botão do Guia que não marca, uma conta que não conclui ou uma nota que não bate com as linhas (Defeito).
- Dúvida sobre quando chega o envio de contas ou alguma das próximas entregas (Informação).
