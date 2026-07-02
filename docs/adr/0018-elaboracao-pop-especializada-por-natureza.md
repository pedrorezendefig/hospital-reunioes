---
status: accepted
---

# Elaboração de POP especializada por Natureza, com seleção automática

O agente de Elaboração de POP era um system prompt único (`chat_elaboracao_pop_system.md`) que se declara "consultor sênior de qualidade hospitalar, especialista em ONA Nível 3 e JCI" e lista só normas assistenciais (RDC ANVISA, CFM, COFEN, ONA, JCI, ABNT). O Setor entrava no prompt apenas como o nome (string). Na prática, o agente "geral" era assistencial: um POP administrativo (DP, Faturamento) ou de apoio (higienização, manutenção) saía enviesado, redigido sob a lente da acreditação assistencial.

Duas saídas estavam na mesa. Especializar deixando o Elaborador **escolher** o prompt por Setor ou tema (mais barreira para quem está na ponta, e risco de escolher errado). Ou manter um único agente "geral" e confiar que a IA evoca sozinha o corpo certo de normas conforme o tema (o que o código desmente: o prompt único não evoca trabalhista para o DP, ele impõe acreditação a tudo).

A decisão une as duas: especialização **real** por **Natureza** (assistencial, administrativa, de apoio), com **seleção sempre automática, nunca do usuário final**.

1. **A Natureza é atributo do Setor, inferida no cadastro.** Uma coluna em `pops_setores`, com o valor sugerido a partir do nome do Setor (como a sigla já é), pré-preenchido, editável e persistido. O POP herda a Natureza do seu Setor; o Elaborador não ganha campo novo nem escolhe nada.
2. **O system prompt é composto, não único.** Núcleo comum (o que é um POP, estrutura dinâmica do ADR 0016, rede de acreditação, formato JSON, tipografia do ADR 0013) + bloco detalhado da Natureza do Setor (persona e corpo de normas) + índice compacto das outras duas Naturezas. A persona fica focada no caso comum sem cegar a IA para as demais.
3. **A IA refina pelo objetivo e sinaliza.** Quando o objetivo do procedimento destoa da Natureza do Setor (uma higienização de superfície num Setor assistencial), o agente adapta a abordagem ao objetivo real e avisa o Elaborador, sem bloquear. A Natureza herdada é a âncora; o refino cobre o caso de borda.

## Por que é surpreendente

Parece que "um prompt só" seria mais simples, e foi o que a Diretoria defendeu. O registro deixa claro que único, na prática, virou enviesado: a persona assistencial estava hardcoded e servia mal metade do hospital. A composição dá foco (persona certa por Natureza) sem reintroduzir a barreira que a Diretoria com razão rejeitou (o usuário na ponta não escolhe nada sobre IA). E a Natureza ser inferida, não preenchida, segue o padrão que a sigla do Setor já estabeleceu.

## Alternativas descartadas

- **Elaborador escolhe o prompt/agente** (por Setor ou tema): barreira cognitiva para quem está na ponta e risco de escolha errada. Era a tentação inicial; a Diretoria a vetou e o veto procede.
- **Um perfil por Setor ou por Tema**: explode a matriz de manutenção, e o Tema ainda exige classificar o procedimento (a IA classifica, sem ganho sobre hoje; ou alguém taggeia, a barreira de novo). A Natureza (3 valores) captura a diferença que importa, o corpo de normas, com custo baixo.
- **Agente único "geral" melhorado**: dilui a persona (especialista em tudo, especialista em nada) e mantém o viés. É o status quo que motivou a mudança.
- **Blob com as três Naturezas detalhadas sempre presentes**: o refino usaria a curadoria completa, mas dilui a persona primária e é o maior prompt. O índice compacto das outras duas dá o ponteiro necessário sem o peso.
- **Re-roteamento dinâmico** (classificar a Natureza real e trocar o bloco): poderoso, mas adiciona classificação, recomposição e a ambiguidade "Setor ou classificador, quem manda". Over-engineering; o refino do agente cobre o caso de borda sem isso.
- **Natureza só em runtime, sem persistir**: economiza a coluna, mas a classificação fica invisível e um Setor classificado errado gera POPs enviesados em silêncio. Num sistema de acreditação, a auditabilidade do campo persistido vale a coluna.

## Consequências

- Nova coluna `natureza` em `pops_setores` (enum: assistencial | administrativa | apoio), com migration e backfill por inferência nos Setores existentes. O gating segue o do Setor (Superadmin POPs); o verbete Natureza do `docs/pops/CONTEXT.md`, que dizia "o Gestor de Qualidade a define", é corrigido.
- `chat_elaboracao_pop_system.md` deixa de ser monolítico: extrai-se o núcleo comum e o bloco assistencial (hoje embutido), e escrevem-se os blocos administrativo e de apoio mais o índice. A composição por `setor.natureza` entra na montagem do prompt (`ai_processor.py`).
- A inferência da Natureza entra no cadastro de Setor (`SetoresManager`), espelhando a sugestão de sigla. Inferir Natureza é semântico (mais difícil que as iniciais da sigla); o campo editável e o refino do agente são as duas redes que tornam um erro de inferência barato.
- O sanitizador determinístico e a convenção "sem travessão" (ADR 0013) seguem no núcleo, valendo para os três blocos. O espelhamento de estrutura por Material de referência (ADR 0016) é ortogonal e não muda.
- O conteúdo normativo de cada bloco parte do que o CONTEXT.md já lista por Natureza; o detalhamento vai para o PRD e a implementação.
