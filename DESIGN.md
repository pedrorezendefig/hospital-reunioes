---
name: Hospital Reuniões
description: Sistema de gestão do ciclo de vida de reuniões corporativas hospitalares
colors:
  primary-navy: "#2B2E7E"
  primary-medium: "#3B6FB6"
  primary-deep: "#1A1C4E"
  secondary-mint: "#88D7A4"
  accent-warm: "#FFC067"
  surface: "#FFFFFF"
  surface-elevated: "#FBFAFD"
  text-primary: "#1E293B"
  text-secondary: "#64748B"
  border-soft: "#E2E8F0"
  status-success: "#88D7A4"
  status-warning: "#FFC067"
  status-error: "#FC9D9D"
  status-info: "#7CC2F2"
typography:
  display:
    fontFamily: "Figtree, system-ui, -apple-system, sans-serif"
    fontSize: "clamp(1.875rem, 1.5rem + 1.5vw, 2.5rem)"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.01em"
  headline:
    fontFamily: "Figtree, system-ui, -apple-system, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.005em"
  title:
    fontFamily: "Figtree, system-ui, -apple-system, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "normal"
  body:
    fontFamily: "Noto Sans, system-ui, -apple-system, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  label:
    fontFamily: "Noto Sans, system-ui, -apple-system, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    letterSpacing: "0.01em"
rounded:
  sm: "8px"
  md: "12px"
  lg: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  2xl: "48px"
  3xl: "64px"
components:
  button-primary:
    backgroundColor: "{colors.primary-navy}"
    textColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-primary-hover:
    backgroundColor: "{colors.primary-deep}"
    textColor: "{colors.surface}"
  button-secondary:
    backgroundColor: "{colors.secondary-mint}"
    textColor: "{colors.primary-deep}"
    rounded: "{rounded.md}"
    padding: "10px 18px"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.primary-navy}"
    rounded: "{rounded.md}"
    padding: "8px 14px"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.lg}"
    padding: "20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "10px 14px"
  chip-status:
    backgroundColor: "{colors.surface-elevated}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.pill}"
    padding: "4px 10px"
---

# Design System: Hospital Reuniões

## 1. Overview

**Creative North Star: "The Quiet Wing"**

Um hospital de alta complexidade é caos. Reuniões corridas, equipes trocando de sala, prazos legais em cima, atas que precisam virar pendência antes do almoço. A interface do Hospital Reuniões é a ala silenciosa desse prédio: porta fechada, luz boa, ritmo lento, espaço entre as decisões. A facilitadora entra entre uma reunião e outra, encontra o que precisa em três cliques, sai pronta. O sistema absorve a pressão dela; não a devolve em forma de ruído visual.

Essa calma se equilibra com calor humano: a paleta puxa para acentos saturados e quentes (verde menta, laranja-amarelo) ao invés do azul-clínico-chapado. Tipografia mistura Figtree (titulada, com personalidade nas letras) e Noto Sans (corpo legível para textos longos como atas). Cards quando faz sentido, sem aninhar; gradientes nunca; modais raros. O sistema serve a tarefa, não a si mesmo.

Rejeita explicitamente: prontuário eletrônico de 2008 com azul-claro chapado, SaaS clone Linear/Vercel com dark mode + gradiente roxo + Inter, formulário governamental serifado e burocrático, portfolio de agência com tipografia brutalista. As referências positivas (Linear, Raycast) entram pela precisão e atalhos, não pelo dark-neon-default.

**Key Characteristics:**
- Light mode é a postura padrão. Facilitadora trabalha de dia em escritório iluminado.
- Densidade alta sem pressão visual: spacing generoso, hierarquia por escala+peso.
- Saturação chega na hora de falar de status (sucesso, alerta, erro). O resto é tintado-neutro.
- Motion sutil, com curva exponential ease-out (cubic-bezier(0.16, 1, 0.3, 1)), nunca bouncy nem elastic.
- Foco visível em 3px porque a facilitadora navega muito por teclado.

## 2. Colors

A paleta tem uma base navy profunda (vinda do logo) sustentando uma família de neutros, e três acentos quentes e saturados que carregam status e identidade. Restrained na maior parte das telas, com a saturação reservada para chamar atenção quando importa.

### Primary
- **Navy Institucional** (`#2B2E7E`, oklch 26% 0.18 270): cor da marca. Ações primárias, headers de seção, links importantes, brand mark. Carrega autoridade sem gritar.
- **Navy Médio** (`#3B6FB6`, oklch 53% 0.13 252): focus rings, hovers de link, iconografia secundária. Bridge entre o navy profundo e o branco.
- **Navy Profundo** (`#1A1C4E`, oklch 18% 0.13 268): hover do botão primário, texto sobre superfícies claras quando precisa peso máximo.

### Secondary
- **Verde Menta Salutar** (`#88D7A4`, oklch 80% 0.13 152): status de sucesso, ações afirmativas (assinar, aprovar, marcar resolvida), pulse de saúde no dashboard de deploy. Nunca decorativo.

### Tertiary
- **Laranja-Amarelo Quente** (`#FFC067`, oklch 84% 0.14 75): alerta brando, destaque editorial em microcopy, accent ocasional. Aparece pouco; quando aparece, importa.

### Neutral
- **Surface** (`#FFFFFF`): fundo principal das telas. Atenção (Don't documentado abaixo): ainda é branco puro hoje, deveria migrar para off-white tintado.
- **Surface Elevada** (`#FBFAFD`): fundo de chips, badges, áreas levemente destacadas. Quase branco, com tom levemente roxo-frio.
- **Texto Primário** (`#1E293B`, oklch 28% 0.025 256): corpo de texto, títulos. Slate dark com calor frio, contraste 13:1 sobre branco.
- **Texto Secundário** (`#64748B`, oklch 53% 0.025 256): metadata, labels, timestamps. Contraste 4.7:1 sobre branco (passa AA).
- **Borda Soft** (`#E2E8F0`, oklch 92% 0.011 256): divisórias, inputs, bordas de card. Quase invisível por design.

### Status
- **Sucesso** = Verde Menta Salutar (`#88D7A4`).
- **Alerta** = Laranja-Amarelo Quente (`#FFC067`).
- **Erro** = Coral Suave (`#FC9D9D`, oklch 79% 0.097 24): erros brando, sem dramatizar.
- **Info** = Azul Céu (`#7CC2F2`, oklch 79% 0.094 232): notificações neutras.

### Named Rules

**The One Voice Rule.** Navy Institucional carrega ≤10% da pintura de qualquer tela. É o cor de comando. Quando aparece, manda.

**The Salutary Mint Rule.** Verde Menta só significa "saúde, sucesso, aprovado, resolvido". Decoração nessa cor está proibida; ela perde o vocabulário se virar background.

**The Quiet Wing Rule.** Nenhuma cor satura mais de 60% de saturação visual em uma tela ao mesmo tempo. Saturação é gasto; orçamento limitado.

## 3. Typography

**Display Font:** Figtree (com fallback `system-ui, -apple-system, sans-serif`)
**Body Font:** Noto Sans (com fallback `system-ui, -apple-system, sans-serif`)

**Character:** Figtree é uma sans humanista geométrica, com pequenas excentricidades nas terminações que dão personalidade aos títulos sem virar display performático. Noto Sans é a workhorse: legibilidade total em corpo longo (atas têm parágrafos densos), suporta diacríticos pt-BR sem rasura, mantém ritmo em tabelas. A combinação evita o reflexo training-data de Inter+Inter; tem calor de família tipográfica humana, mantém compostura de produto.

### Hierarchy
- **Display** (700, clamp(1.875rem, 1.5rem + 1.5vw, 2.5rem), 1.15, -0.01em): hero do dashboard, título de página principal. Aparece poucas vezes por sessão.
- **Headline** (700, 1.5rem, 1.25, -0.005em): seção dentro de página, abertura de card grande.
- **Title** (600, 1.125rem, 1.35): título de card pequeno, header de tabela, label de seção compacta.
- **Body** (400, 1rem, 1.6): corpo de ata, descrição de pendência, texto de modal. Largura ≤75ch.
- **Label** (500, 0.8125rem, +0.01em letter-spacing): chips, badges, metadata, footer de card. Levemente expandido para legibilidade em tamanho pequeno.

### Named Rules

**The Two-Family Rule.** Figtree para tudo que é título e botão. Noto Sans para tudo que é corpo, label, dado tabular. Não atravessar. A clareza dessa divisão é o sistema.

**The 75ch Rule.** Largura máxima de coluna de prosa = 75 caracteres. Atas, descrições de pendência, anotações: nunca espalham até a borda do viewport.

**The Hierarchy Without Color Rule.** Hierarquia de títulos é resolvida por escala (≥1.25 ratio entre passos) e peso (400 → 600 → 700). Cor só entra para distinguir status. Mudar a cor de um H2 para "destacar" é prática proibida.

## 4. Elevation

Sistema de elevação suave, com duas sombras nomeadas que conferem peso sem ostentação. A maior parte das superfícies fica flat por default; sombras aparecem em resposta a estado (hover, focus, modal aberto, drawer). Não usar shadow para chamar atenção; usar para indicar elevação real.

### Shadow Vocabulary
- **Premium** (`box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.08), 0 8px 10px -6px rgba(0, 0, 0, 0.08)`): cards interativos em hover, drawers, dropdowns. Difusa, sem direção dominante.
- **Premium Strong** (`box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.12), 0 8px 10px -6px rgba(0, 0, 0, 0.12)`): modais ativos, command palette, tooltips em foreground importante.

### Named Rules

**The Flat-By-Default Rule.** Cards em estado de repouso não têm sombra. Sombra é resposta a hover, foco, ou camada acima do conteúdo (modal, drawer, tooltip).

**The No-Inner-Shadow Rule.** Sombras internas (`inset`) são proibidas para sugerir profundidade decorativa. Profundidade vem de spacing e cor de borda, não de inset.

## 5. Components

### Buttons
- **Shape:** cantos médios (12px radius).
- **Primary** (Navy Institucional `#2B2E7E` em texto Surface `#FFFFFF`, padding 10px 18px, Figtree 600 0.9rem): ação dominante de uma tela. No máximo um por seção. Hover desce para Navy Profundo (`#1A1C4E`) com transition 200ms cubic-bezier(0.16, 1, 0.3, 1).
- **Secondary** (Verde Menta `#88D7A4` em texto Navy Profundo `#1A1C4E`, mesma forma): ação afirmativa de fluxo (assinar, aprovar). Não usar como variação visual de Primary.
- **Ghost** (transparente, texto Navy Institucional, sem border): ação terciária. Hover ganha background `rgba(43, 46, 126, 0.06)`.
- **Estados:** todos têm `default`, `hover`, `focus-visible` (outline 3px Navy Médio + offset 2px), `active`, `disabled` (opacity 0.5, cursor not-allowed), `loading` (spinner inline + texto preserved).

### Chips
- **Status Chip:** background Surface Elevada, texto Texto Primário, padding 4px 10px, radius pill (999px). Quando carrega cor de status, prefixo um dot 8px da cor + texto ainda em Texto Primário (cor + ícone + texto, nunca cor sozinha).

### Cards
- **Corner Style:** 16px radius (large), suave o bastante para parecer humano sem virar bolha.
- **Background:** Surface (`#FFFFFF`) por default; Surface Elevada (`#FBFAFD`) quando o card está dentro de outro layout colorido.
- **Shadow Strategy:** flat por default, ganha sombra Premium em hover ou quando interativo (clicável).
- **Border:** 1px Borda Soft (`#E2E8F0`). Single source of separation.
- **Internal Padding:** 20px (lg). Para cards densos (tabela compacta), 12px.
- **Cards aninhados são proibidos.** Se a hierarquia pede, usar background diferenciado e padding, não outro card.

### Inputs
- **Style:** stroke 1px Borda Soft, background Surface, radius 8px, padding 10px 14px. Tipografia Body.
- **Focus:** stroke vira Navy Médio (2px), outline acrescido 3px Navy Médio com offset 2px.
- **Error:** stroke vira Coral Suave (`#FC9D9D`), microcopy de erro abaixo em Texto Secundário com ícone leading.
- **Disabled:** opacity 0.5, cursor not-allowed, background `#F8FAFC`.

### Navigation
- Top bar quando estamos no app principal; sem side nav densa para o caso de 5 facilitadoras com fluxo linear.
- Tipografia Label, espaçamento generoso entre itens (24px+ horizontal).
- Estado ativo: underline 2px Navy Institucional offset 6px (não pill colorido).
- Mobile: hambúrguer com drawer que entra com fade-in-right (cubic-bezier exponential, 300ms).

### Dialog (Modal)
- Use raramente. A skill `impeccable` proíbe modal-as-first-thought; nesse sistema, modal é só para confirmação destrutiva (apagar usuário, encerrar reunião) ou criação compulsória (envelope ClickSign).
- Background Surface, radius 16px, padding 24px, shadow Premium Strong.
- Backdrop `rgba(0, 0, 0, 0.4)` com `backdrop-filter: blur(4px)` (uso pontual de blur, não decorativo).
- Animação: scale-in 220ms cubic-bezier(0.16, 1, 0.3, 1).

### Pulse (Signature)
- Status dot animado para indicar saúde de serviço no dashboard de deploy.
- Círculo 10px da cor de status (success/warning/error), com pulse externa que escala 1.0→1.6 com opacity 0.5→0 em 1.6s loop.
- Uso pontual: 1 por tela, no hero do dashboard. Nunca em listagens.

## 6. Do's and Don'ts

### Do:
- **Do** usar Navy Institucional (`#2B2E7E`) como única voz para ação primária, brand, links importantes. Máximo 10% da tela.
- **Do** reservar Verde Menta (`#88D7A4`) só para sucesso/saúde/aprovação. Nunca decorativo.
- **Do** par Figtree (títulos, botões) com Noto Sans (corpo, dados). Nunca atravessar.
- **Do** respeitar `prefers-reduced-motion` em qualquer animação nova: o `globals.css` já tem o guard-rail; respeite-o.
- **Do** usar curve exponential `cubic-bezier(0.16, 1, 0.3, 1)` para entrada/saída. Durations 150-300ms.
- **Do** focus-ring 3px Navy Médio com offset 2px, em qualquer interativo.
- **Do** combinar cor + ícone + texto em status. Cor sozinha falha em daltônicos.
- **Do** aplicar largura ≤75ch a qualquer prosa (atas, descrições, parágrafos de modal).

### Don't:
- **Don't** usar dark mode como default. A facilitadora trabalha de dia, em escritório iluminado, em desktop. Light mode é a postura.
- **Don't** clonar Linear/Vercel com dark + gradiente roxo + Inter + glow neon. Mesmo as referências positivas viram cliché se aplicadas tal qual.
- **Don't** parecer prontuário eletrônico de 2008: azul-claro chapado em fundo branco estéril, ícones plus-redondo-azul, formulários sem rhythm.
- **Don't** parecer governamental burocrático: serifas formais, formulários em árvore, tabelas densas sem hierarquia.
- **Don't** parecer agência criativa: tipografia brutalista, animações overkill, fundo preto com texto branco que vibra.
- **Don't** usar `border-left` ou `border-right` >1px como stripe colorido em card, alerta, list item. Use background tint, ícone leading, ou nada.
- **Don't** usar gradient text (`background-clip: text`). Use peso ou tamanho para hierarquia.
- **Don't** usar glassmorphism (backdrop-filter blur) decorativamente. Existe em `.glass-card` e `.modal-backdrop` no `globals.css`; reservar a esses dois usos pontuais.
- **Don't** aninhar card dentro de card. Sempre errado. Reorganize com background diferenciado.
- **Don't** usar `#FFFFFF` puro como surface de longo prazo. A regra impeccable pede tintar neutros toward brand hue (chroma 0.005-0.01). Migrar gradualmente para `#FBFAFD` ou OKLCH equivalente.
- **Don't** usar emoji decorativo em UI institucional do Hospital. Calor vem da paleta e do espaçamento, não de 🎉 e 👋.
- **Don't** personificar a IA com avatar sorridente nem tratar erro como "Oops!". Tom direto e respeitoso, sempre.
- **Don't** usar em-dash (`—`) em microcopy: prefira vírgula, dois-pontos, ponto-e-vírgula, parênteses.
- **Don't** ship animações de entrada de página inteira. Stagger de 50ms apart para um conjunto de 3-5 elementos é o teto.
