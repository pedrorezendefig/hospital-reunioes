---
status: accepted
amends: 0048
---

# O ouvidor redireciona o caso para outra área num ato só, e passa a manter o cadastro de responsáveis

Decisão do Pedro (14/set/2026, grilling a partir da pergunta do diretor: "o ouvidor ou o superadmin consegue, de forma fácil, alterar o responsável pela resposta ou a área responsável?"). A resposta era "em parte": a área conseguia devolver (ADR 0048), mas o ouvidor não conseguia tirar o caso de uma área e mandar para outra, e a pessoa que responde só mudava pela mão da Diretoria. Esta ADR fecha as duas pontas.

## Contexto

- A troca de área existia só no sentido área -> ouvidor (ADR 0048). Com o caso em `aguardando_area`, a rota de validar recusa ("Este caso já está com a área") e o Dossiê não oferece caminho. A transição genérica `aguardando_area -> em_classificacao` aceitava um POST direto sem motivo, mas era porta de fundo: não consumia o link da área antiga nem parava o relógio.
- Quando a área errada responde "isso é do Centro Médico" em vez de devolver pelo link, o caso chega `respondido` e a única saída era devolver por insuficiência ao mesmo setor ou encerrar e abrir outro protocolo, o cenário torto que o ADR 0048 quis matar.
- O acionamento vai ao titular vigente do [Responsável do setor], cadastro mantido só pela `diretoria_executiva`. Desde a issue #536, Cobrar manda para o vigente, decidido no servidor. Ou seja, trocar a pessoa já tinha metade do caminho; faltava quem opera a Ouvidoria poder mexer no cadastro.

## Decisões

1. **Nasce o Redirecionamento, ato do ouvidor.** Botão "Redirecionar" no Dossiê e no menu secundário da linha da fila, para caso em `aguardando_area` ou `respondido`. Abre a [Validação e acionamento] pré-preenchida (tipo, gravidade, extrato) com a área em branco e um **motivo obrigatório**. Numa requisição só, o servidor tira o caso da área antiga (consome o link, para o relógio, zera os carimbos de cobrança e escalonamento, grava o movimento "Redirecionado pelo ouvidor (de <setor>): motivo") e aciona a área nova pela mesma porta de sempre. Se a área nova não tem titular nem gestor vigente, nada acontece e o caso continua com a área antiga. Rejeitado: dois atos ("Retirar da área" e depois validar), porque deixa o caso parado em classificação sem ninguém cobrando; pausa e devolução por insuficiência já cobrem quem precisa de tempo.

2. **Mesma conta de prazo da devolução (ADR 0048, decisão 2).** T1 novo, prazo cheio para a área nova, o tempo perdido com a área errada entra na Triagem da Ouvidoria. Rejeitado: a área nova herdar o prazo restante. O erro de despacho é o mesmo fato, só que percebido pelo ouvidor em vez da área, e o relatório não pode mostrar a área certa atrasada por culpa de quem despachou errado. O prazo conclusivo com o manifestante não se move.

3. **Caso pausado não redireciona.** Em `aguardando_manifestante` o ouvidor retoma primeiro. Rejeitado: aceitar a pausa como origem, porque o relógio parado da pausa e o prazo cheio da área nova se embolam na mesma requisição.

4. **A área antiga é avisada.** Email curto ao mesmo destinatário do acionamento: a demanda daquele protocolo foi encaminhada a outra área e não é preciso responder. Sem motivo, sem dizer qual área. Gatilho novo `redirecionamento_area` na [Notificação da Ouvidoria], registrado e reenviável. Rejeitado: silêncio, como na devolução. Lá a própria área abriu mão; aqui ela pode estar no meio de apurar, e descobrir só quando o link falhar é desperdiçar trabalho e criar ruído com a Ouvidoria.

5. **O `ouvidor` passa a manter o cadastro de Responsável do setor**, ao lado da `diretoria_executiva`. Trocar a pessoa que responde é encerrar a vigência do titular e cadastrar o novo; um Cobrar em seguida leva o caso ao novo (issue #536). Vale para todos os casos do setor, presentes e futuros. Rejeitado: destinatário por caso (o ouvidor escolher titular, substituto ou gestor ao acionar). Responsável é atributo do setor, não do caso, e a cadeia de cobrança e escalonamento inteira (véspera ao titular, vencimento ao substituto, +24h gestor) parte do cadastro; um destinatário por caso teria que carregar a cadeia junto, ou a cobrança iria para uma pessoa e o escalonamento para outra. A [Tabela de prazos] continua só da Diretoria.

6. **Sem limite de redirecionamentos, sem relatório nesta leva.** Mesma regra da devolução: a cada volta há o ouvidor decidindo, e a trilha guarda cada redirecionamento com o motivo.

## Consequências

- A trilha ganha dois movimentos na mesma requisição (retirada e acionamento), e o Dossiê passa a distinguir "Devolvido pela área" de "Redirecionado pelo ouvidor" pelo prefixo da observação; a contagem de devoluções não muda.
- A resposta da área errada, quando existir, fica na trilha como está (imutável) e não viaja para a área nova.
- A área antiga já recebeu o relato integral por email e nada desfaz isso; o aviso apenas encerra a demanda dela. Em caso sigiloso o aviso continua sem detalhe algum, como a decisão 4 já fixa.
- Trocar o titular no cadastro não invalida o link que o antigo recebeu: ele expira ou é consumido como hoje. Se o caso precisa sair das mãos do antigo na hora, o ouvidor cobra (o link novo vai ao vigente) ou redireciona.
- Quem lê métricas de Triagem verá o trecho crescer também nos casos redirecionados. É o efeito desejado, o mesmo do ADR 0048.
- A tela `/ouvidoria/responsaveis` e as rotas de escrita de `/responsaveis` passam a aceitar o [Perfil da Ouvidoria] inteiro; o histórico de vigência já registra quem mexeu.
