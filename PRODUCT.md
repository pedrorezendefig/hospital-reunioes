# Product

## Register

product

## Users

Cinco facilitadoras de reuniões em um hospital de alta complexidade: um diretor e quatro diretoras. Trabalham entre reuniões, frequentemente com pouco tempo entre uma sala e a próxima. Acessam o sistema do desktop em escritórios bem iluminados durante o dia.

Os colaboradores que aparecem nas atas (médicos, enfermeiras, equipe administrativa) **não fazem login**. Recebem apenas dois tipos de contato: email da ClickSign para assinar a ata e link direto para marcar uma pendência atribuída a eles como resolvida. Para esse público, o sistema precisa funcionar como uma extensão natural do email, sem fricção, sem onboarding.

O power-user atual é o desenvolvedor solo (Pedro), que opera ferramentas internas como o dashboard de deploy. Esse perfil pede atalhos, densidade de informação e ritmo rápido.

## Product Purpose

Automatiza o ciclo de vida de reuniões corporativas hospitalares: gravação → transcrição por IA (OpenAI gpt-4o-mini) → geração de ata estruturada → assinatura digital pela ClickSign → acompanhamento de pendências até resolução.

A reunião pode durar uma hora; a digestão dela costuma roubar dias. O produto comprime esse atraso para minutos. Sucesso é a facilitadora sair de uma reunião e, antes da próxima, ter ata pronta, assinada e pendências encaminhadas.

## Brand Personality

**Quente, humano, organizado.**

- *Quente* nos detalhes: a paleta puxa para acentos saturados (verde menta, laranja-amarelo), as fontes Figtree e Noto Sans têm humor próprio, microcopy fala como pessoa.
- *Humano* nas decisões: nunca esconde o que está acontecendo, explica antes de pedir, perdoa erros sem culpar o usuário.
- *Organizado* na hierarquia: tudo tem lugar, espaço respira, dados densos não apertam.

O contrário (e que precisa ser evitado): clínico-frio, corporate-asséptico, governamental-burocrático.

## Anti-references

Quatro armadilhas que o produto não deve parecer:

1. **Hospital antiquado.** Prontuário eletrônico de plano de saúde, intranet hospitalar de 2008, azul-claro chapado em fundo branco estéril. Sem ícones de plus-redondo-azul. Sem stocks de médico-genérico-com-prancheta.
2. **SaaS clone Linear/Vercel.** A reflexo do training data: dark mode default, gradiente roxo no hero, fonte Inter, glow neon, hero-metric template (big number + small label + sparkline). Mesmo as boas referências (Linear, Raycast) ficam aqui se aplicadas como cópia direta.
3. **Burocrático governamental.** Formulários sem rhythm, navegação em árvore, serifas formais como Times, tabelas densas que ocupam a tela inteira sem hierarquia.
4. **Agência criativa.** Tipografia brutalista, fundo preto com texto branco que vibra, animações overkill que roubam a leitura, layouts assimétricos que servem ao designer e não ao usuário.

## Design Principles

1. **Calmo onde o hospital é caos.** A facilitadora chega no sistema entre uma reunião e outra. A interface é o oposto do dia dela: ritmo lento, foco claro, nenhuma cor gritando, nenhum modal interrompendo.
2. **Confiança via consistência.** Padrões previsíveis ganham de soluções clever. Se um botão de ação primária aparece em verde menta no canto inferior direito de um modal, todos aparecem igual em todos os modais. Surpresa de design quebra confiança em sistema que assina documentos legais.
3. **Texto pesa mais que ornamento.** Atas são longas. Pendências têm contexto. Microcopy explica. Tudo isso precisa ser legível antes de ser bonito. Largura de coluna ≤75ch, line-height respirando, hierarquia por escala+peso, nunca por glow ou gradiente.
4. **Atalhos para quem já sabe, mãos dadas para quem é novo.** O power-user (Pedro, no dashboard de deploy interno; facilitadoras experientes nas funções diárias) merece densidade e atalhos no estilo Linear/Raycast. O usuário externo (colaborador clicando em link de ClickSign) precisa de UX zero-onboarding.
5. **Calor sem infantilismo.** Humano não é fofo. Não usar emoji decorativo, não personificar a IA com avatar sorridente, não tratar erros como "Oops!". O calor vem da paleta, do espaçamento generoso, do tom direto e respeitoso da microcopy.

## Accessibility & Inclusion

- WCAG 2.1 AA como mínimo. Contraste ≥4.5:1 para texto normal, ≥3:1 para texto grande e elementos de UI.
- `prefers-reduced-motion` já é respeitado globalmente — qualquer motion novo precisa entrar nesse mesmo guard-rail.
- Focus rings de 3px com offset de 2px e cor que contrasta tanto em fundos claros quanto em superfícies coloridas.
- Targets mínimos de 44×44 pt em mobile (mesmo que o uso primário seja desktop).
- Cores nunca como única dimensão de informação: status combina cor + ícone + texto.
- Português pt-BR é o idioma único — sem `i18n` no MVP, mas todos os strings ficam em components/copy isoláveis para facilitar futuro.
