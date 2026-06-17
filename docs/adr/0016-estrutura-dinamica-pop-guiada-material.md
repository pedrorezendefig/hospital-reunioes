---
status: accepted
---

# Estrutura dinâmica do POP guiada pelo material de referência

O conteúdo de uma Versão de POP era um JSON de chaves fixas (`objetivo`, `abrangencia`, e mais oito seções), e o agente de Elaboração era obrigado a devolver exatamente essas seções: o template institucional de onze seções (Identificação preenchida pelo sistema, mais dez do agente), alinhado a ONA Nível 3 e JCI. Na prática a estrutura real varia por procedimento, e em quase todos os casos o Elaborador anexa um modelo de POP (Material de referência) e espera que o resultado siga aquela estrutura. O template fixo forçava seções irrelevantes e ignorava a estrutura pedida.

A decisão: a estrutura do POP passa a ser **dinâmica**. O rascunho deixa de ser um JSON de chaves fixas e vira uma **lista ordenada de seções** (`id`, `título`, `conteúdo`). O agente cria, renomeia, reordena e remove seções livremente. Com um Material de referência que traz um modelo, o agente **espelha a estrutura dele**; sem modelo, propõe o template institucional como ponto de partida editável. Nenhuma seção é forçada, exceto a Identificação, que segue preenchida pelo sistema e fora da lista. A rede de segurança de acreditação é o próprio agente, consultor de ONA e JCI: ele **sinaliza** quando falta uma seção que um auditor esperaria (Objetivo, Responsabilidades, Descrição do procedimento, Referências normativas), mas não trava o fluxo. Cada seção carrega um **ID estável**, não o título, para o apontar-seção (⌖) e a atualização ao vivo sobreviverem a renomear e reordenar.

## Por que é surpreendente

Acreditação costuma implicar estrutura padronizada, então um POP sem template fixo pode parecer regresso de conformidade. O registro deixa claro que a padronização migrou do código (chaves fixas) para o agente (sugestão mais sinalização de lacuna) e para o modelo anexado, e que isso é decisão da Diretoria, dona do padrão institucional.

## Alternativas descartadas

- **Manter as chaves fixas e só relaxar o prompt**: não permite criar nem renomear seções, nem espelhar um modelo arbitrário. Resolve metade do problema.
- **Núcleo mínimo obrigatório mais resto dinâmico**: garante acreditação, mas viola "o modelo anexado manda" quando o modelo omite uma seção do núcleo. Preferimos sugerir a forçar.
- **Estrutura totalmente livre sem rede**: arrisca POPs incompletos com um Elaborador descuidado. A sinalização do agente é barata e mitiga.

## Consequências

- Reescreve o shape persistido do rascunho (JSONB: de objeto de chaves para lista de seções com ID), o schema de resposta do agente e os prompts de sistema e de usuário da Elaboração.
- O render na tela (`PopVivoView`) e no PDF (`pop_template.html`) passam a iterar seções dinâmicas e a renderizar markdown (negrito, listas, blocos) na linguagem visual da Ata, no lugar do `pre-wrap` atual.
- O apontar-seção (⌖) passa a referenciar IDs de seção.
- Exige migração dos rascunhos existentes (de chaves fixas para lista de seções).
- O Fluxograma deixa de ser uma chave fixa e vira uma seção como as outras, com tipo próprio (ver [ADR 0017](0017-fluxograma-pop-mermaid-svg-no-pdf.md)).
