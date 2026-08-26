---
status: accepted
amends: 0032
---

# Convênios por especialidade sai do app: cobertura vem da agenda online e o Espelho da Global Health entra no lugar

Decisão do Pedro (26/ago/2026, grilling neste repo, par do ADR-0025 do repo da Ana). A tabela curada `convenios_especialidade` (ADR 0031, migration 062) se aposenta. A cobertura de convênio por especialidade passa a ter uma fonte única: a agenda online da Global Health (GH). No lugar da tabela, a tela `/admin/dados-atendimento` ganha o **Espelho da Global Health**, uma seção somente leitura que mostra ao vivo o que a GH publica. Este ADR emenda o 0032 (o endpoint de convênios deixa de existir, com seus filtros e degraus) e, em prosa, o 0031 (o módulo passa de 4 tabelas de valores para 3; o campo `amended_by` dele já está ocupado pelo 0032).

## Contexto

- Em 26/ago/2026 ficou provado (repo da Ana, ADR-0025) que `GET /convenios?idItemAgendamento=` da GH responde cobertura por especialidade, direto da fonte que decide se o agendamento acontece.
- As duas fontes já divergiam: a tabela local tinha Amil, Golden Cross e Hapvida; a agenda de Cardiologia da GH não tem nenhum dos três. Cópia local de dado que a plataforma sabe envelhece e vira mentira.
- Do lado da Ana o corte já foi feito: a tool 4 saiu do grant e a Seção 3.2 do prompt verifica cobertura pela cadeia da agenda (3 casos: na lista, fora da lista, especialidade não publicada). Nenhuma menção à tabela sobrou no prompt.
- A anotação por especialidade (diferenciais, instruções de conversa) já existe e fica: colunas `descricao_servico`, `diferencial_1..3` e `observacoes_ana` de `consultas_particulares`.

## Decisões

1. **A tabela `convenios_especialidade` sai inteira**, em camadas de fora para dentro: seção da tela, rotas admin (`GET/POST/PATCH /api/admin/dados-atendimento/convenios-especialidade`), endpoint `GET /api/ana/convenios-especialidade`, spec da factory, testes e fixture. A migration de drop vem por último, em commit separado, reversível sozinha.
2. **Sem dump de produção.** O conteúdo será refeito depois (decisão do Pedro). O seed de março/2026 (20 linhas, com os textos de `observacao`) permanece preservado no git dentro da migration 062; edições feitas em produção depois disso se perdem, conscientemente.
3. **Sem camada de anotações de convênio nesta passada.** Os 20 textos existentes são frases de cobertura, exatamente o dado que a GH agora responde. Vale a regra do ADR-0025 da Ana: se um aviso humano (ex.: "sujeito a autorização prévia") fizer falta real na conversa, a tabela de anotações nasce num PRD próprio, com texto novo. Guardar por precaução é o caminho de volta para a divergência.
4. **Mapa da verdade entre GH e Dados do Atendimento.** A GH é dona da agenda: o que existe, quem atende, quem é aceito, quando. As tabelas locais são donas do que a GH não tem: preço particular e diferenciais (consultas), preço e preparo (exames), estimativa e aviso obrigatório (cirurgias). As 3 tabelas restantes e as tools 1-3 da Ana ficam até a GH publicar esses dados; quando publicar, revisita-se tabela a tabela.
5. **Espelho da Global Health**: seção somente leitura na tela `/admin/dados-atendimento`, onde ficava a tabela de convênios. Botão "Atualizar" dispara a chamada; nada é gravado no banco (espelho, não cópia). Quatro elos: especialidades publicadas, convênios aceitos + profissionais (em paralelo, ao clicar na especialidade), planos (ao clicar no convênio), horários livres. Blocos de exames e instruções de horário são fatia opcional, fora do núcleo.
6. **Segurança e ambiente**: o backend é o único que fala com a GH (proxy; o token jamais chega ao navegador). Token em env var `GH_TOKEN_HOMOLOG`, no mesmo lugar do `ANA_API_KEY`. Base fixa em constante única comentada, apontando homologação (`dem.agenda.globalhealth.mv`); produção jamais é chamada por este código, e trocar a base exige commit consciente. Só leitura: nenhum POST/PUT/DELETE contra a GH.
7. **Honestidade da tela**: timeout curto por chamada; falha de rede aparece como falha, nunca como lista vazia; cada bloco vazio diz por quê. `GET /agendas/v2` só é chamado com os três ids vindos dos elos anteriores (id errado devolve 200 com `agendas: []`, indistinguível de "sem horário"; faltando id, HTTP 500).
8. **Público**: o mesmo da tela, super admin, secretária e facilitador, tudo leitura.

## Considered options

- **Camada de anotações de convênio já nesta entrega**: rejeitada depois de ler os 20 textos reais (todos frases de cobertura) e o ADR-0025 da Ana, que manda esperar a falta real.
- **Dump fiel de produção antes do drop** (psql via Coolify Terminal): rejeitado pelo Pedro; o conteúdo será refeito e o seed de março já vive no git.
- **Base da GH em env var com guarda contra produção**: rejeitada; constante fixa é mais simples e a troca vira revisão de código.
- **Ana 100% GH já (desligar também as tools 1-3)**: rejeitada por fato: a GH hoje não publica preço nenhum (`/consultas` devolve só `id`, `nome`, `bloqueado`), e o fluxo particular da Ana vive de preço.

## Consequences

- Morre a segunda verdade de cobertura; a divergência deixa de existir por construção.
- A tela admin passa a depender da disponibilidade da GH de homologação para o Espelho (as 3 tabelas curadas não dependem).
- O endpoint da antiga tool 4 morre; no repo da Ana a definição da tool fica preservada sem grant (ADR-0025) e passa a apontar para rota inexistente, o que é aceitável e documentado.
- Pautas registradas para o repo da Ana, fora desta entrega: cirurgia sempre transborda a humano (inclinação do diretor, a amadurecer) e a dúvida do `idPlano` na disponibilidade.
- Nasce o primeiro consumo de API externa por tela admin (padrão proxy backend + botão Atualizar), reutilizável para futuros espelhos.
