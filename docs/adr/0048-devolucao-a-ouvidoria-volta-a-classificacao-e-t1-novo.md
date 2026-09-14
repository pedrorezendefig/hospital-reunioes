---
status: accepted
amends: 0034
---

# Devolução à Ouvidoria volta o caso à classificação, e o reacionamento carimba T1 novo

Decisão do Pedro (04/set/2026, grilling a partir do áudio do diretor): a área que recebe um caso que não é dela **devolve ao ouvidor**, com motivo obrigatório, pela própria tela do link. O caso volta a "em classificação", o ouvidor reaciona a área certa pela tela de validação já preenchida, e o reacionamento grava **T1 novo com prazo cheio**. O tempo perdido com a área errada fica na conta da Ouvidoria.

## Contexto

O ADR 0034 (decisão 4) fez do link tokenizado o portal do setor, e o PRD #318 fixou dois botões na tela do responsável (RN-62): responder e pedir prorrogação. A área não tinha como dizer "não é meu". O caminho hoje é torto: a Recepção escreve na resposta que o caso é do médico, o ouvidor encerra e abre outro protocolo. A trilha se parte em dois casos e o manifestante ganha dois números.

O diretor pediu: "a recepção percebe que não é dela, devolve, para o ouvidor encaminhar para outro destinatário". Quatro coisas do modelo pesaram na forma:

- A área nunca escolhe a área (glossário, Canal aberto e Validação e acionamento).
- T1 é o marco da validação e abre o prazo da área; o trecho T0 até T1 é a Triagem da Ouvidoria e T1 até T2 é o tempo da área (ouvidoria_marcos).
- A máquina de estados já tem o laço da devolução por insuficiência, na direção contrária (ouvidor devolve resposta fraca ao mesmo setor, meio prazo).
- A RN-59 fixa a ordem da tela do responsável, porque quem a abre é o usuário menos treinado do módulo.

## Decisões

1. **Volta a "em classificação", sem estado novo.** A transição `aguardando_area -> em_classificacao` entra no grafo. O caso devolvido é um caso a despachar de novo, e a fila, o Dossiê e o botão de validar já sabem lidar com isso. Rejeitado: estado próprio "devolvido pela área" (visível na fila, mas todo relatório, semáforo e contador teria que aprender o estado; a fila em classificação já é a fila de quem espera o ouvidor).

2. **T1 novo e prazo cheio no reacionamento.** Reacionar passa pela mesma porta da validação e carimba `validada_em` de novo; o motor calcula o prazo da área certa do zero. O trecho da Triagem passa a conter o desvio. Rejeitado: manter o T1 original e a área certa herdar o prazo restante (o relatório mostraria a área certa atrasada por culpa de quem despachou errado; a Ouvidoria, que errou o destino, sairia limpa). A primeira validação continua na trilha, então o histórico não se perde.

3. **A área não aponta destino.** Só o motivo, em texto livre. Se quiser, escreve ali "acho que é do Centro Médico". Rejeitado: campo com lista de setores na tela pública (expõe a taxonomia sem login e dá à área uma decisão que é do ouvidor).

4. **Reacionar é pré-preenchido.** O Dossiê mostra "Devolvido pela Recepção: motivo" e o botão de encaminhar abre a validação com tipo, gravidade e extrato do acionamento anterior. O ouvidor troca a área e confirma. Tudo continua editável.

5. **Link discreto, não terceiro botão.** "Este caso não é do meu setor?" abaixo dos dois botões, último elemento da RN-59, que passa a ter onze. Ao clicar, abre o campo do motivo e o botão de devolver. Rejeitado: botão do mesmo peso (aperta o celular e convida a devolver por preguiça).

6. **Motivo obrigatório, sem piso, teto de 10.000.** O motivo de "não é meu" é curto por natureza; o teto é o dos outros textos da área, porque ele vai para a trilha imutável. Devolver consome o link (uso único, como responder) e só vale em `aguardando_area`.

7. **Sem limite de devoluções, sem relatório nesta leva.** A cada volta há o ouvidor decidindo. A trilha guarda cada devolução com o motivo, e o Dossiê mostra a contagem. Linha no relatório mensal fica para quando houver histórico.

## Consequências

- Nasce um gatilho interno de notificação (a Ouvidoria é avisada da devolução) e um movimento novo na trilha. A área que devolveu não recebe nada.
- A guarda que separa acionamento de devolução por insuficiência na rota de validar continua valendo: o reacionamento chega de `em_classificacao`, então não é devolução.
- O teste "apenas os dois botões da RN-62" muda de propósito: passa a garantir dois botões mais o link discreto.
- Quem lê métricas de Triagem verá o trecho crescer nos casos devolvidos. É o efeito desejado: despacho errado é custo da Ouvidoria.
- Reincidência e devolução por insuficiência não mudam.
