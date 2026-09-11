---
status: accepted
amends: 0041
---

> Emenda a exceção do ADR 0041 (decisão 3 e emenda de 01/09/2026): o **caso anônimo** continua sem identificação de quem manifestou e sem relato integral, mas passa a levar para a área o nome e a referência do Paciente do caso. O sigilo reforçado não muda: ali nada do paciente viaja fora do extrato do ouvidor.

# O Paciente do caso viaja para a área, inclusive no caso anônimo

A Diretoria observou em 09/09/2026 que quem reclama pelo QR setorial muitas vezes é acompanhante (mãe, pai, cônjuge) em nome de um paciente, assina o relato e não diz de quem fala. O caso chega, o ouvidor aciona, e a área devolve porque não acha o atendimento. O formulário do canal aberto não perguntava nada sobre o paciente, e o caso não tinha onde guardar isso.

## Decisões

1. **O caso ganha dois dados opcionais do paciente**: nome e referência do atendimento (texto curto: data, setor ou leito). Nascem no formulário público e no registro manual do ouvidor; a Ana fica para leva própria. Não são editáveis depois, como o resto da identificação.

2. **O formulário pergunta "Este relato é sobre quem?"** logo depois do relato, com resposta obrigatória de um toque: "Sobre mim" grava o vínculo `paciente`; "Sobre outra pessoa" grava `acompanhante` e abre os dois campos. Os campos são opcionais: o canal aberto nunca barra o envio por dado faltando.

3. **Os campos ficam visíveis com "anônimo" marcado.** O anonimato protege quem manifesta. O paciente é outra pessoa, e sem ele o caso anônimo do acompanhante não serve para nada.

4. **O paciente viaja para a área no caso comum e no caso anônimo.** Email de acionamento e tela do responsável levam o paciente onde levam "quem manifestou", e no caso anônimo levam o paciente mesmo com "Sem identificação" na linha do manifestante. **Não viaja no sigilo reforçado** (denúncia e relato de conduta): o paciente pode ser a vítima, e quem decide o que sai é o ouvidor, pelo extrato.

5. **Relato em nome de outra pessoa sem nome do paciente acende um aviso no Dossiê**, antes do acionamento, sem travar. É o ponto mais barato de pegar o caso: antes de a área descobrir e devolver.

6. **A Retenção passa a varrer o paciente.** Nome e referência são dado pessoal de terceiro e saem junto com os cinco lugares de hoje.

## Alternativas rejeitadas

- **Só uma frase de instrução no relato.** Não força nada, some ao digitar, e o dado continua não vindo.
- **Colar o nome dentro do relato.** O relato é integral e sem edição; Retenção e pseudonimização passariam a depender de achar texto.
- **Paciente seguir a mesma guarda de "quem manifestou".** Mais simples de explicar, mas o acompanhante anônimo volta a gerar caso que a área não acha, que é o problema que motivou a decisão.

## Consequências

- "Acompanhante da Maria, leito 12" às vezes entrega quem falou. O formulário diz isso à pessoa no aviso do campo, e a escolha é dela.
- A guarda do caso protegido deixa de ser uma regra só: identificação do manifestante e relato integral seguem a regra do 0041; o paciente segue a regra deste ADR.
