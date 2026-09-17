# Integração Ana x MV

O MV é o sistema hospitalar do hospital: é nele que vivem o cadastro do paciente, a agenda dos médicos e o agendamento de verdade. A Integração Ana x MV é o caminho que liga a Ana a esse sistema, para ela poder ver horário livre e marcar consulta sem ninguém digitar no meio.

A ligação não é direta com o MV: ela passa pela Global Health, a empresa que publica a agenda online do hospital. É com a Global Health que a Ana e o aplicativo conversam.

## Em que pé está

A integração ainda não está em operação. Hoje ela existe em ambiente de teste: as chamadas são feitas contra o ambiente de homologação da Global Health, nunca contra o ambiente de verdade dos pacientes.

O circuito já foi percorrido ponta a ponta no teste: encontrar o paciente pelo CPF ou pelo telefone, cadastrar paciente novo, ler convênio e plano, listar especialidade, profissional e horário livre, e listar, remarcar e cancelar o que já está agendado. O que falta é o conteúdo real do lado da Global Health e do MV, e isso depende de gente de fora da Vitta.

Enquanto a integração não entra, a Ana não marca consulta no sistema do hospital: ela vai até onde consegue e entrega a conversa para uma pessoa concluir.

## Quem é dono de qual informação

Esta é a regra que organiza o assunto inteiro, e ela vale mesmo depois de a integração entrar:

- A **Global Health** é dona da agenda: quais especialidades existem, quem atende, qual convênio é aceito e que horário está livre.
- O **aplicativo** é dono do que a agenda não tem: o valor da consulta particular, o preparo do exame, a estimativa de cirurgia.

Quando a resposta é "não achei horário", a causa costuma ser uma destas quatro: a especialidade não está publicada, o convênio não está na lista aceita, o profissional foi desligado no painel, ou a agenda não tem horário livre.

## O espelho dentro do aplicativo

Dentro do aplicativo existe uma seção que mostra, ao vivo, o que a agenda online da Global Health está publicando: especialidades, convênios aceitos, profissionais, planos e horários livres. Um botão atualiza, e o que aparece é o que a agenda respondeu naquele instante.

Ela é só leitura. O aplicativo não grava, não corrige e não marca nada na agenda: o espelho existe para conferir por que a Ana não achou horário, sem precisar abrir o portal. Quando a agenda está fora do ar, a tela diz que falhou em vez de mostrar uma lista vazia como se fosse resposta.

## O que ela não faz

- Não agenda nada pelo aplicativo: o espelho mostra, quem marca é a agenda online.
- Não copia a agenda para dentro do aplicativo, então não existe versão desatualizada guardada aqui.
- Não toca o ambiente de verdade dos pacientes enquanto estiver em teste.

## O que costuma virar Demanda

- Especialidade, profissional ou convênio que devia aparecer e não aparece (Terceiro, quando depende da Global Health ou do MV).
- Agenda publicada sem horário livre (Terceiro).
- Dúvida sobre em que pé está a integração (Informação).
- Decisão sobre o que a Ana poderá marcar sozinha quando a integração entrar (Decisão).
