# Ana

A Ana é a agente de inteligência artificial de atendimento do hospital: ela conversa com o paciente por mensagem, responde sobre consultas, exames e valores particulares, e registra manifestações de ouvidoria. Foi feita para atender fora do horário comercial e para tirar da fila as perguntas que se repetem todo dia.

Ela é um produto à parte do aplicativo. O aplicativo é a casa dos dados que ela usa; a conversa em si acontece na plataforma dela.

## Onde ela atende hoje

Hoje a Ana atende num canal de teste, e não no número de WhatsApp que os pacientes já conhecem. O número principal do hospital continua atendido por pessoas, no sistema que a equipe usa hoje.

Levar a Ana para o número principal é uma entrega que ainda não aconteceu, e depende de outras peças ficarem prontas, entre elas a Integração Ana x MV. Enquanto isso, o que ela faz é provado em conversas de teste, cenário por cenário.

## O que ela sabe responder

A Ana lê ao vivo as tabelas que ficam dentro do aplicativo, na tela de Dados do Atendimento:

- o valor da consulta particular por especialidade, e o diferencial do hospital naquela especialidade;
- o preparo e o valor dos exames;
- a estimativa de valor de cirurgias.

Editou no aplicativo, vale na conversa seguinte. Não existe fila nem espera para a Ana enxergar a mudança, e é por isso que esse cadastro é trabalho do hospital, não da Vitta.

## O que ela resolve sozinha e o que passa para uma pessoa

A Ana responde sozinha, do começo ao fim e a qualquer hora, o que o paciente pergunta sobre consulta e exame particular: valor, preparo e diferencial. Marcar, não: quando chega a hora de agendar, ela entrega a conversa para uma pessoa do hospital concluir. A Ana marcar consulta já foi decidido e ainda não está construído, e depende da Integração Ana x MV. Cirurgia, procedimento e negociação de valor sempre passam para uma pessoa do hospital: ela explica o que sabe, junta o que já apurou na conversa e entrega o atendimento.

Quando ela não consegue resolver, ela também passa para uma pessoa, em vez de insistir ou inventar.

## Ouvidoria pela Ana

Quando o paciente reclama, elogia ou quer registrar alguma coisa, a Ana abre uma manifestação de ouvidoria e informa o número do protocolo na hora, no formato ano mais número (por exemplo, 2026-0007).

O número é gerado pelo aplicativo, nunca pela Ana: ela copia o que recebeu. Se o registro falhar, ela não cita número nenhum.

A Ana registra, mas não classifica. Quem decide o tipo, a gravidade e a área responsável é o ouvidor, depois. Por isso o caso que chega por ela nasce sem tipo e sem gravidade, e sem tipo ele é tratado como sigiloso até o ouvidor olhar. A área pode chegar preenchida, com o que a Ana escreveu: ali ela vale como sugestão, e é o ouvidor que a confere na validação.

## Dados do paciente

A Ana pede nome completo e CPF, numa mensagem só, e apenas nos momentos em que a conversa vai passar para uma pessoa. Data de nascimento, telefone e e-mail ela não pede: o telefone a equipe já tem pelo WhatsApp, e o cadastro completo quem faz é a equipe, ao confirmar.

O relato e os dados pessoais ficam na conversa, com a equipe. O que vai para o aplicativo é o índice do caso, não o dossiê.

## O que costuma virar Demanda

- Valor, preparo ou diferencial errado ou desatualizado (Defeito ou Ajuste).
- Especialidade, exame ou cirurgia que falta na tabela (Novo).
- A Ana respondendo diferente do combinado numa situação específica (Defeito; vale dizer o que o paciente escreveu e o que ela respondeu).
- Mudança no que ela pode resolver sozinha (Decisão).
