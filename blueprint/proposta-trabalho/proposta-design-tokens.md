# Proposta PJ · Design Tokens

Documento de referência única dos tokens visuais da proposta. Toda skill de geração (`imagegen-frontend-web`, `image-to-code`, `redesign-existing-projects`, `impeccable`) deve consumir esses valores. Versão atual: redesign editorial minimalista quente, plano `planos/plano-26-05-01-1955h-redesign-proposta-pj.md`.

## Voz visual

Vibe: New Yorker conhece Linear. Documento editorial impresso, com momentos de drama controlado nos pontos de leitura crítica (hero, rampa, saída livre, encerramento).

Skills em camada:
1. Baseline: `design-taste-frontend` + `full-output-enforcement`.
2. Voz dominante: `minimalist-ui`.
3. Drama pontual: `high-end-visual-design` (4 momentos).
4. Geração de referências: `imagegen-frontend-web` + `image-to-code`.
5. Refinamento: `redesign-existing-projects` + `impeccable`.

Banidos: Inter, ícones Lucide aleatórios, gradientes preguiçosos, shadows pesadas, card-dentro-de-card, paleta purple/blue de SaaS AI, neon glow, 3-column card spam, copy em inglês, números em fonte sans (rampa e valores são sempre mono).

## Paleta

| Token              | Valor       | Uso                                                             |
| ------------------ | ----------- | --------------------------------------------------------------- |
| `--surface`        | `#FAFAF7`   | Background principal, creme quente                              |
| `--surface-2`      | `#F4F2EC`   | Cards de destaque, painéis sutis                                |
| `--ink`            | `#1A1A1A`   | Tinta principal, charcoal (não preto puro)                      |
| `--ink-soft`       | `#2F3437`   | Headings em peso médio                                          |
| `--text`           | `#1A1A1A`   | Corpo de texto                                                  |
| `--text-2`         | `#44403C`   | Texto secundário, hierarquia                                    |
| `--muted`          | `#78716C`   | Labels, captions, metadados                                     |
| `--border`         | `#EAEAEA`   | Bordas 1px nos cards                                            |
| `--border-strong`  | `#D6D3D1`   | Divisores em pontos editoriais                                  |
| `--accent`         | `#EA580C`   | Laranja queimado, único accent (calor da proposta)              |
| `--accent-soft`    | `#FDF1E8`   | Background de pill/highlight do accent                          |
| `--accent-ink`     | `#9A3412`   | Accent escurecido pra hover/destaque secundário                 |

Regra: 1 accent só. Se algum elemento pedir uma segunda cor, usar `--ink-soft` ou `--muted`, nunca uma terceira hue.

## Tipografia

Stack via Google Fonts (mantém restrição "sem libs externas/custos"):

| Token        | Família             | Uso                                                     |
| ------------ | ------------------- | ------------------------------------------------------- |
| `--font-display` | `Fraunces`     | H1/H2 editoriais (serif variável, opsz 144 nos grandes) |
| `--font-sans`    | `Geist`        | Corpo, lead, navegação, labels                          |
| `--font-mono`    | `Geist Mono`   | Números (rampa, valores), códigos, eyebrow              |

Pesos:
- Display: 300-500 (light a medium, nunca 900 pra evitar o efeito "Inter Black")
- Sans: 400 corpo, 500 ênfase, 600 botões/CTAs
- Mono: 400 corpo, 500 destaques numéricos

Tracking:
- Display grande: `letter-spacing: -0.035em` a `-0.045em`
- Display médio: `letter-spacing: -0.02em`
- Labels uppercase: `letter-spacing: 0.16em`
- Mono: `letter-spacing: -0.01em`

Escala (clamp pra responsivo):
- `--fs-display`: `clamp(3rem, 1.4rem + 7vw, 6.5rem)` (hero gigante)
- `--fs-h1`: `clamp(2.4rem, 1.6rem + 3.2vw, 3.6rem)`
- `--fs-h2`: `clamp(1.6rem, 1.2rem + 1.4vw, 2.1rem)`
- `--fs-h3`: `1.125rem`
- `--fs-body`: `1rem`
- `--fs-lead`: `1.0625rem`
- `--fs-small`: `0.8125rem`
- `--fs-mono-big`: `clamp(2.5rem, 1.2rem + 5vw, 4.5rem)` (números da rampa)

Combinações canônicas:
- Hero: Fraunces 300 + Geist 400 (lead) + Geist Mono 500 (número-âncora).
- Section heading: Fraunces 400 + eyebrow Geist Mono uppercase.
- Rampa: Geist Mono 500 (valor) + Geist 400 (label entrega).
- Cláusula curta: Fraunces 400 italic (statement) + Geist 400 (corpo).

## Layout

| Token             | Valor       | Uso                                                  |
| ----------------- | ----------- | ---------------------------------------------------- |
| `--max`           | `880px`     | Max-width do container principal (não 1080px)        |
| `--max-narrow`    | `680px`     | Container de leitura editorial (cláusulas, lead)     |
| `--max-wide`      | `1120px`    | Hero, rampa, encerramento                            |
| `--pad`           | `32px`      | Padding lateral mínimo                               |
| `--pad-section-y` | `clamp(72px, 8vw, 128px)` | Padding vertical entre seções               |
| `--pad-block`     | `40px`      | Padding interno de cards/blocos                      |
| `--gap-grid`      | `clamp(24px, 3vw, 48px)` | Gap em bento grids                          |

Estrutura base:
- Bento asimétrico calmo, sem 3 colunas iguais.
- Padding generoso vertical (72-128px entre seções).
- Cards com `border: 1px solid var(--border)`, sem shadows.
- 1 grid visível como assinatura na rampa (linha conectora 1px `--border-strong`).
- Scroll do documento contínuo (single-page), sem abas.

## Border radius

| Token     | Valor   | Uso                                |
| --------- | ------- | ---------------------------------- |
| `--r-xs`  | `2px`   | Pills, tags pequenas               |
| `--r-sm`  | `4px`   | Inputs, botões pequenos            |
| `--r-md`  | `8px`   | Cards padrão                       |
| `--r-lg`  | `14px`  | Painéis grandes (rampa)            |

Sem `border-radius: 50%` em cards. Avatares circulares OK em assinatura.

## Motion

Restrição mantida do plano 26-05-01: zero libs externas. Apenas CSS + IntersectionObserver.

Easings:
- `--ease`: `cubic-bezier(0.22, 1, 0.36, 1)` (default snappy)
- `--ease-out`: `cubic-bezier(0.16, 1, 0.3, 1)` (entradas)
- `--ease-spring`: `cubic-bezier(0.34, 1.56, 0.64, 1)` (overshoot leve, só no hero/rampa)

Durations:
- Reveal de seção: `600ms`
- Stagger entre items: `80ms` por elemento
- Hover sutil: `220ms`
- Counter animado: `1000ms`
- Linha da rampa (stroke-dasharray): `800ms`

Padrões:
- Reveal: `opacity 0 → 1` + `translateY(12px → 0)` ao entrar viewport (IntersectionObserver, threshold 0.2).
- Hero: stagger 80ms entre eyebrow → display → lead → CTA.
- Rampa: linha conecta esquerda → direita com `stroke-dasharray`, depois marcos aparecem com stagger 120ms, depois counters animam 0 → valor (requestAnimationFrame).
- Hover em card: `translateY(-1px)` + `border-color: var(--border-strong)`, transition 220ms.
- `prefers-reduced-motion: reduce` desativa todos os transforms e transitions.

Anti-padrões: parallax pesado, scrub-scroll de hero, magnetic hover em CTA principal (deixa "Awwwards SaaS"), float infinito em background.

## Iconografia

Sem ícones de biblioteca (Lucide/Feather/Heroicons). Quando precisar de marcador visual:
- Bullet: `·` (mid-dot) em mono, color `--muted`.
- Divisor de marco: linha 1px `--border-strong`, comprimento 24-48px.
- Status: pill texto-only com `--accent-soft` e text `--accent-ink`.
- Avatar: tipografia (iniciais) em circle 40px com border 1px.

## Print / PDF

Documento precisa imprimir bem. Regras:
- `@media print`: remover background colors fortes, manter `--surface` como white.
- Page break antes da rampa e antes da assinatura final.
- Animações off em print (já garantido por `prefers-reduced-motion` em alguns navegadores; explicitar com `@media print` em transitions).
- Footer com URL/data/versão em todas as páginas printadas.
