---
status: accepted
amends: 0058
---

> Emenda em prosa à ADR 0034 (Consequências: "pseudonimização antes de IA externa") e às regras de saída do caso anônimo e sigiloso das ADRs 0041 e 0052. Sem ponteiro `amends` para elas no frontmatter: o lint aceita um único ponteiro por campo, e o ponteiro fica com a 0058, que é a decisão de onde o Conector mora.

# O Conector lê Reuniões e Ouvidoria para a diretoria executiva, com o mesmo acesso que a tela dela tem

Decisão do Pedro (11/11/2026), na triagem da issue #1571, a partir das decisões do diretor na Demanda da aba Tecnologia. O diretor deixou com a Vitta a escolha técnica e respondeu as de negócio; aqui ficam as duas coisas, e o único ponto em que a Vitta recomenda diferente do que ele pediu (decisão 5).

## Contexto

- O Conector do Claude já existe desde a ADR 0058: transporte em `/api/mcp`, OAuth pelo WorkOS AuthKit, três ferramentas da Central de Comando (Ao vivo, Site e Instagram), todas globais. O `autorizar` exige participante ativo e Super admin, e o transporte descarta o participante que ele devolve.
- O diretor quer perguntar ao próprio Claude, no celular e no computador, sobre pendências, prazos, atas e casos da Ouvidoria, sem que o Claude leia a tela do navegador. Ele decidiu que o Claude só consulta, que o acesso é só de quem tem `diretoria_executiva` no Perfil da Ouvidoria (hoje, ele), que outros Super admins ficam de fora, que POPs e Contas médicas ficam fora, e que "metas" são as próprias pendências.
- Na Ouvidoria ele pediu tudo: relato, trilha, respostas, casos sigilosos, nome e contato de quem manifestou e do paciente, e que a consulta pelo Claude não fique registrada no caso.
- A `diretoria_executiva` já abre tudo isso na tela (ADR 0034, decisão 8; Perfil da Ouvidoria no `CONTEXT.md`). O que muda é o dado sair do app para a conta pessoal dele no Claude, que é um serviço fora do hospital.

## Decisões

1. **Princípio: o Conector entrega o que a tela de quem conectou entrega.** Nem mais, nem menos. Toda regra abaixo sai daqui: o Claude é outro jeito de a mesma pessoa, com o mesmo acesso, ler o mesmo dado. Quem não abre o Dossiê na tela não o recebe pelo Claude.

2. **Um Conector só, com gate por ferramenta.** As ferramentas de Reuniões e Ouvidoria entram no mesmo Conector da Central. O `autorizar` passa a aceitar participante ativo que seja Super admin ou tenha `diretoria_executiva`, e cada ferramenta tem o próprio gate: as da Central seguem para Super admin; as de Reuniões e as da Ouvidoria são só de quem tem `diretoria_executiva`, Super admin ou não (decisão 11 do diretor). O `tools/list` mostra só o que a pessoa pode chamar. Quem não tem acesso a nenhuma ferramenta recebe 401, como hoje; quem chama uma ferramenta fora do próprio gate recebe erro de ferramenta, sem dado. O transporte guarda o participante que o `autorizar` devolve e o passa às ferramentas; quem é nunca vem do corpo do pedido.
   - Por quê: o diretor já tem o Conector ligado no Claude. Um segundo Conector seria outra ligação para ele fazer no celular e no computador, outro Resource Indicator no WorkOS e outra página de guia, para o mesmo login e o mesmo OAuth.
   - Perder `diretoria_executiva`, ou ser desligado, corta as ferramentas na chamada seguinte, porque o gate é lido no banco a cada chamada (como na decisão 4 da ADR 0058).

3. **Só leitura, com a regra da tela.** Quatro ferramentas, nenhuma escreve:
   - **Pendências:** filtro por situação (atrasada inclusive), responsável e prazo. Atrasada é a mesma regra que a tela de Pendências usa.
   - **Reuniões:** reuniões por período ou termo, com a Ata, os participantes e as pendências que saíram dela.
   - **Casos da Ouvidoria:** a fila com protocolo, setor, situação, gravidade e prazo, com filtro de prazo estourado e de setor. Prazo estourado é o mesmo cálculo que a fila da Ouvidoria mostra (Tabela de prazos e Calendário útil).
   - **Caso da Ouvidoria:** o Dossiê de um protocolo, com a trilha.
   As ferramentas chamam o mesmo código que as rotas das telas usam; um segundo cálculo de atraso ou de prazo faria o Claude discordar da tela, e bater com a tela é o teste de aceite do diretor. Lista longa volta cortada num teto, com o total e o aviso de que há mais, para o Claude refinar o filtro.

4. **Na Ouvidoria, o Claude recebe o Dossiê como a `diretoria_executiva` o vê.** Relato integral, trilha, respostas das áreas, casos com sigilo reforçado e a identificação que o caso gravou (quem manifestou e o Paciente do caso). No caso anônimo vai o que o Dossiê mostra: o app não inventa identificação que o caso não tem. Caso apagado ou retido chega com o aviso no lugar do relato, como na tela.
   - Isto é exceção consciente à regra da ADR 0034 de pseudonimizar antes de IA externa e às regras de saída das ADRs 0041 e 0052. Aquelas regras valem para o que o **app** manda a terceiros (a IA do relatório, o e-mail e a tela da área). Aqui quem lê é a pessoa autorizada, pela ferramenta dela, e pseudonimizar esconderia dela o que a tela já mostra.
   - Pseudonimizar foi rejeitado também por outro motivo: a remoção automática de nome em texto livre erra, e a Ouvidoria não teria como saber que errou (ADR 0041, ratificação de 03/09/2026). Entregar o Dossiê inteiro a quem já o vê é mais honesto do que entregar um Dossiê que parece limpo.

5. **A consulta pelo Claude fica registrada, ao contrário do que o diretor pediu.** Abrir o Dossiê pela ferramenta do caso grava uma linha em `ouvidoria_acessos` com a ação `consulta_conector`, como abrir o Dossiê na tela grava `abrir_dossie`. As listas não gravam, como a fila na tela não grava.
   - Por quê: o diretor disse que não precisa registrar, não que não pode. O registro não aparece para ele, não pede nada a ele e não deixa a resposta mais lenta (falha no registro não derruba a leitura). E é a única prova do que saiu do hospital para uma conta pessoal se essa conta um dia vazar. A regra "todo acesso à Manifestação gera registro" fica inteira.
   - O diretor fica sabendo pela Conversa da Demanda. Se ele insistir em não registrar, isso vira emenda a esta ADR.

6. **O guia do Conector ganha a parte da diretoria executiva.** O guia em `docs/comunicacao/central/guia-conector/` passa a dizer quais ferramentas cada perfil vê e, para a diretoria executiva, a pedir que ela confira nas configurações de privacidade da conta do Claude se as conversas podem ser usadas para melhorar os modelos, e desligue essa opção.

7. **O limite de 60 chamadas por minuto continua.** Uma conversa junta poucas chamadas (uma por ferramenta usada); o teto sobra. Se aparecer 429 no log do Conector, revisita.

## Alternativas rejeitadas

- **Conector separado para Reuniões e Ouvidoria.** Isolaria o gate, mas o diretor faria duas ligações no Claude para o mesmo login, e o WorkOS ganharia outro Resource Indicator. O gate por ferramenta dá o mesmo isolamento.
- **Super admin para Reuniões.** Era a primeira resposta do diretor; ele mesmo a trocou na decisão 11.
- **Não registrar a consulta.** Ver decisão 5.
- **Mandar ao Claude só o índice da Ouvidoria.** Não responderia o que o diretor quer perguntar (o relato e a resposta da área), e ele já vê tudo isso na tela.

## Consequências

- Dado pessoal e por vezes sensível de manifestante e de paciente sai do hospital para a conta pessoal do diretor no Claude, e fica sob as regras de retenção dessa conta. O registro da decisão 5 e a configuração de privacidade da decisão 6 são o que limita o dano.
- O acesso ao Conector deixa de ser "só Super admin": a Central continua assim, Reuniões e Ouvidoria seguem a `diretoria_executiva`. Quem concede esse perfil na tela de Usuários concede também essa saída pelo Claude.
- Ferramenta nova de Reuniões ou Ouvidoria no Conector segue o princípio da decisão 1. Abrir o Conector para outro perfil (ouvidor, facilitador) é outra decisão.
- POPs e Contas médicas continuam fora do Conector.
