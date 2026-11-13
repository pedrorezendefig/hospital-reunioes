---
status: accepted
amends: 0054, 0084, 0090, 0092
---

# Projeto na Tecnologia: Aplicativo do Hospital e Ana

Decisão do Pedro (13/11/2026, grill no terminal, rodadas 4 e 5, todas as recomendações aceitas). A Ana, agente de atendimento do mesmo hospital, tem repositório próprio e privado (`pedrorezendefig/programa-ana`), com o mesmo pacote do fluxo, as mesmas labels de triagem e PRDs com sub-issues. O Pedro quer que o diretor e os Desenvolvedores vejam, na aba Tecnologia, os cards da Ana ao lado dos do app, com um filtro por projeto. Os cards abertos da Ana entram agora; os já concluídos não são carregados, e daqui para frente o que for concluído aparece.

A aba inteira supunha um repositório só: uma variável de repo, um token que só lê o Hospital, um webhook que descarta outro repositório, a Demanda achada só pelo número da issue (índice único) e o espelho que exige labels que a Ana não usa.

## Decisões

1. **Projeto é a palavra.** Dois valores: Aplicativo do Hospital e Ana. Rejeitado: "Produto" (é o módulo do kit de conhecimento, e o Produto com dono foi aposentado na 0077); "Sistema".

2. **A Demanda ganha o Projeto, e a chave do Vínculo passa a ser projeto mais número da issue.** Emenda a decisão 1 da ADR 0054. A issue #50 da Ana e a #50 do Hospital são Demandas diferentes. Quadro, Entregas, Documento do card e Conversa da Demanda servem aos dois. Migration nova. Rejeitado: uma tabela separada para a Ana (duplica tela e código).

3. **Uma sequência só para o Número da Demanda.** "Demanda 42" nunca é ambígua, seja do Hospital ou da Ana. Rejeitado: sequência por projeto.

4. **Da Ana, só as raízes de produto viram card.** PRDs e issues soltas, sem as partes e sem as de ferramenta (`area:os`). Hoje são três cards, cada um com "X de Y partes". Toda Demanda da Ana é da Origem Vitta. O espelho ganha a regra da Ana ao lado da do Hospital (ADR 0084). Rejeitado: toda issue virar card, inclusive partes; só os PRDs.

5. **Os cards da Ana são só leitura neste passo.** Têm Etapa, Documento do card e Conversa da Demanda, mas o Assistente de Tecnologia continua criando card só no Aplicativo do Hospital. Criar card da Ana pelo Assistente fica para outra Demanda, com grill próprio. Rejeitado: o Assistente perguntar "Hospital ou Ana?" agora (traz um segundo repositório para o Assistente, o formato de card da Ana e as labels dela).

6. **Na Ana, a última Etapa é Entregue.** A Ana não tem Subida com versão: o prompt é aplicado à mão na plataforma. Sem "Em produção" até ela ganhar deploy pelo repositório, quando o carimbo vem sozinho. Rejeitado: marcar "Em produção" à mão no app (Etapa nunca é digitada, ADR 0054).

7. **Um token e um webhook a mais.** O token da integração passa a incluir o repositório da Ana, com leitura de conteúdo e de PRs além de Issues (emenda a decisão 8 da ADR 0054: deixa de ser "só este repositório"). O repositório da Ana ganha um webhook para o mesmo endereço, com o mesmo segredo, e o app aceita os dois repositórios; a conferência de hora em hora lê os dois. Cadastrar token e webhook é tarefa humana. Rejeitado: um segundo token (mesmo servidor, nenhuma proteção a mais); só a conferência de hora em hora para a Ana.

8. **Filtro Projeto no Quadro e nas Entregas.** Campo "Projeto" na barra de filtros (Todos, Aplicativo do Hospital, Ana) e um selo pequeno do projeto em cada card. Emenda a decisão 8 da ADR 0090 e a decisão 7 da 0092. Rejeitado: uma aba por projeto.

9. **O bloco para leigo da Ana se lê pelos dois títulos.** O O que muda vem do bloco "Para o diretor" ou, na Ana, "Para quem decide". Parte sem bloco mostra "Descrição em preparação". Rejeitado: renomear o bloco no repositório da Ana.

## Consequências

- O repositório da Ana é privado: nada do conteúdo dele vai para o repositório do Hospital, que é público. A Conversa da Demanda de um card da Ana fica só no app.
- A Ana segue sem deploy; o Tamanho da entrega e as Entregas funcionam igual, só sem versão.
