# Reuniões

O módulo de Reuniões é o que o aplicativo faz desde o começo: transforma uma reunião em ata, e a ata em tarefas com dono e prazo. É onde a diretoria registra o que foi decidido e acompanha o que ficou combinado.

Quem conduz uma reunião e responde pela ata é o facilitador, e é ele quem entra no aplicativo. Quem só foi citado numa reunião, ou ficou responsável por alguma coisa, não entra: recebe e-mail e links diretos para o que é dele.

## Os dois jeitos de montar a ata

**Por transcrição.** O facilitador traz o texto da reunião e a inteligência artificial monta a ata: tópicos, decisões e ações. Essa ata vira PDF e pode ir para assinatura digital.

**Ata guiada.** Para a reunião operacional que não teve transcrição, o facilitador monta a ata conversando numa tela própria, por escrito ou por voz: de um lado o chat, do outro a ata tomando forma, já com o visual da ata final. O agente pergunta o que falta, principalmente quem faz e até quando, e o facilitador pode apontar uma seção e corrigi-la pela conversa. Essa ata não gera PDF e não vai para assinatura.

Uma reunião tem no máximo uma ata, por um dos dois caminhos.

## Quem faz o quê, e até quando

Os nomes citados na reunião são casados com o cadastro de pessoas do hospital. Quem está no cadastro vira responsável de verdade e passa a ser cobrado; quem é de fora fica só como nome, sem cobrança. Quando o agente não tem certeza de quem é, ele pergunta.

Cada ação combinada vira uma pendência, com responsável e prazo, e desde o primeiro segundo ela é cobrada de verdade: aparece no painel, vence e atrasa. Prazo estourado vira atrasado, e o caminho normal é repactuar: nasce uma pendência nova com prazo novo, e a antiga fica no histórico, em vez de sumir.

## Assinar ou finalizar sem assinar

Depois de revisar a ata, o facilitador escolhe um de dois caminhos, e os dois são definitivos:

- **Enviar para assinatura.** A ata vira PDF e segue para assinatura digital, na ClickSign, que é quem manda o e-mail para cada pessoa assinar. As pendências vão nascendo conforme as pessoas assinam.
- **Finalizar sem assinatura.** As pendências nascem na hora e a ata fica aprovada, sem passar pela assinatura.

Não existe "assinar depois": escolhido o caminho, ele vale.

Quando a assinatura não se completa (alguém recusa, ou o processo é cancelado), quem faltava recebe um e-mail com link, lê a ata inteira e clica em "li e aceito". Esse aceite vale como o "assinou" dele e faz nascer as pendências dele, mas não é assinatura digital: a formalidade continua sendo só do caminho da assinatura.

## O que ele não faz

- Não grava a reunião: o aplicativo não capta o que se fala na sala. O áudio que ele recebe é o ditado, quando o facilitador prefere falar a digitar na ata guiada: esse áudio sobe, é transcrito ali mesmo e descartado. Áudio nenhum fica guardado.
- Não gera PDF da ata guiada, e não a manda para assinatura.
- Não desfaz uma ata finalizada.

## O que costuma virar Demanda

- Ata saindo com erro de conteúdo, ou perdendo uma decisão que foi tomada (Defeito).
- Nome citado que casou com a pessoa errada, ou não casou com ninguém (Defeito).
- Campo novo na ata, ou mudança no texto do e-mail de cobrança (Ajuste).
- Mudança em quem assina, ou na ordem das assinaturas (Decisão).
