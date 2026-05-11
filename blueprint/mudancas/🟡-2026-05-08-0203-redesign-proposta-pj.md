# Redesign da proposta PJ — Pedro Figueiredo × Hospital São Mateus

> Reescrita completa do `blueprint/proposta-trabalho/proposta.html` (965 linhas, 6 abas, A/B/C com fees variáveis e cálculo de ROI) para um documento single-page, editorial e enxuto, em estilo "Editorial Bold". Substitui também `CLAUSULAS-COMUNS.md` (encolhido) e atualiza `README.md`.

---

## Contexto

A proposta atual foi gerada em 29-04-2026 com 3 cenários (A/B/C), 6 abas, programa de imersão IA detalhado, modalidade fiscal completa (Simples/Anexo III/Fator R/JUCERJA), tabelas de fees variáveis (5% economia anual, 6% mensal por 6 meses), ROI projetado por projeto e 17 cláusulas. Pedro pediu reescrita com 3 mudanças centrais:

1. **Mais enxuta, mais visual, com animações** — sair do estilo "Quiet Wing" do app, abandonar abas, abandonar tabelas de cifrão, abandonar discurso de ROI.
2. **Modelo PJ-PJ direto** — sem tom institucional pesado de prestador de serviço; sem fees variáveis; só serviço + preço.
3. **Estrutura de remuneração nova** — rampa por entrega com **dois atores** (Pedro + Lucas, sócios em Pedro Figueiredo Tecnologia LTDA) e cláusula de saída livre simétrica.

A proposta vai ser apresentada ao presidente do Hospital São Mateus, com defesa antecipada do irmão diretor-geral. A audiência primária portanto é institucional, mas o tom escolhido com Pedro é "documento sério em terceira pessoa", não "papelada".

---

## Decisões consolidadas no brainstorming

### Atores
- **CNPJ:** Pedro Figueiredo Tecnologia LTDA (em abertura)
- **Sócios visíveis ao hospital:** Pedro (engenharia de IA) + Lucas (design, contribuição com expertise Adobe/Photoshop e ideação)
- **Sobrenome do Lucas:** **TBD** — usar placeholder `[Lucas SOBRENOME]` no HTML; Pedro substitui antes de enviar
- **NF única** emitida pelo CNPJ Pedro Figueiredo Tec; Lucas recebe via dividendos/distribuição interna (transparente para o hospital, opaco no documento — não detalha)

### Rampa de remuneração (estrutura central)

A rampa avança **por entrega/marco**, não por calendário. Cada marco destrava um incremento sobre o fixo mensal vigente.

| Marco | Δ Pedro | Pedro (acum) | Δ Lucas | Lucas (acum) | **Total mensal** |
|---|---|---|---|---|---|
| Início — presença, alinhamento, setup | +6.000 | 6.000 | — | 0 | **R$ 6.000** |
| Hospital Reuniões em produção | +1.000 | 7.000 | +1.000 | 1.000 | **R$ 8.000** |
| Site institucional no ar | +1.000 | 8.000 | +1.500 | 2.500 | **R$ 10.500** |
| Ana WhatsApp + integração MV | +2.500 | 10.500 | +2.000 | 4.500 | **R$ 15.000** |

**Estado terminal (sem Retell):** R$ 15.000/mês fixos.

### Trava da rampa (condicionamento)

Cada marco destrava **somente se**:
1. As entregas planejadas para o ciclo foram concluídas
2. Zero incidente crítico em produção nos últimos 30 dias
3. Validação em reunião curta com a Diretoria

Se algum critério falha, o degrau fica suspenso até a próxima reunião.

### Saída livre (cláusula central)

- **Aviso de 15 dias por escrito**, sem multa, simétrica
- Vale para Hospital, Pedro Figueiredo Tec, e qualquer prestador subcontratado pelo CNPJ Pedro Figueiredo Tec
- Janela de 15 dias usada para handoff: passar acessos, atualizar runbook, fechar pendências críticas

### Fase 2 — Retell (condicional, fora da rampa principal)

- Posiciona como projeto futuro, dependente de estudo técnico e disponibilidade
- **Implementação:** R$ 1.000 (Pedro) + R$ 1.000 (Lucas) — fee único de incentivo
- **Sustentação:** +R$ 2.000 (Pedro) + R$ 2.000 (Lucas) ao fixo mensal vigente
- Incidência: a partir do go-live e estabilização

### Inclusos no fixo (4 bullets)

1. **Sustentação de tudo em produção** — uptime, fixes, monitoramento, runbook
2. **Presença em Bangu** — 1 dia/semana presencial; reuniões de alinhamento, apresentações, treinamentos com IA, interações com TI
3. **Programa de imersão em IA** — 1:1s com Diretoria e colaboradores-chave; capacitação prática; levantamento de dores; quick wins táticos
4. **Stack de IA viva** — Claude Code Max para Pedro e Lucas, agentes próprios, runbooks documentados, mentoria à TI MV

### Cláusulas (4 cards densos, sem letrinha pequena)

1. **Saída livre** — 15 dias, sem multa, simétrica; estende-se a prestadores sob CNPJ Pedro Figueiredo Tec
2. **Condicionamento da rampa** — critérios objetivos (entregas + zero incidente crítico em 30 dias) validados em reunião mensal
3. **Propriedade intelectual** — código e dados específicos do hospital pertencem ao Hospital São Mateus; skills genéricas, agentes reutilizáveis e know-how técnico permanecem com Pedro Figueiredo Tec
4. **Confidencialidade & LGPD** — dados de paciente nunca saem do ambiente controlado; termo de confidencialidade dedicado

### O que **sai** da proposta atual

- 6 abas → single-page com scroll
- 3 cenários A/B/C → 1 cenário só
- Tabelas de fixo escalonado por trimestre (Q1/Q2/Q3/Q4)
- Fees de implementação 5%/6% sobre economia anual
- Variável 5%/6% × 6 meses pós-go-live
- Tabela de ROI (R$ 144k/ano Retell, R$ 60k/ano Ana, etc.)
- Modalidade fiscal completa (Simples/Anexo III/Fator R/JUCERJA/CNAE/abertura PJ)
- Cláusula de "chamada de time" detalhada (substituída pela menção implícita aos dois sócios)
- Programa de imersão com cadência (mensal/quinzenal/semanal) e contagem de horas — substituído por bullet curto
- Custos de infraestrutura listados (VPS, OpenAI, Resend, etc.) — não pertencem ao retainer
- Modo redução por emergência pessoal — extinto (saída livre cobre)
- Cláusula de exclusividade saúde-RJ — não aparece nessa primeira versão (decisão pode ser revisitada)
- Custos do júnior detalhados — substituído pela transparência da rampa de Lucas

---

## Identidade visual — Editorial Bold

### Paleta
- **Tinta primária:** `#0c0a09` (preto editorial)
- **Surface:** `#fafaf7` (creme quase branco)
- **Surface elevada:** `#ffffff`
- **Acento único:** `#ea580c` (laranja queimado)
- **Texto secundário:** `#44403c` (warm gray 700)
- **Muted:** `#78716c` (warm gray 500)
- **Borda:** `#e7e5e4` (warm gray 200)

### Tipografia
- **Display + corpo:** Inter (400, 500, 600, 700, 800, 900) via Google Fonts
- **Display:** font-weight 800-900, letter-spacing -0.04em, line-height 0.96-1.0
- **Eyebrows:** uppercase, letter-spacing 0.14em, color laranja, font-weight 700, font-size 0.7rem
- **Corpo:** font-weight 400-500, line-height 1.6, max-width 60-65ch
- Abandona Figtree + Noto Sans do app

### Brand mark
- Quadrado 40-48px preto `#0c0a09` com letras "PF" em Inter 900 branco
- Letter-spacing -0.05em, border-radius 4px
- À direita do mark: nome "Pedro Figueiredo Tecnologia" em Inter 800 + subtítulo "Engenharia de IA · com [Lucas SOBRENOME], Design" em warm gray 500
- Decisão sobre "PF · LM" como brand mark composta: **PF mantém-se** — CNPJ é Pedro Figueiredo Tec; Lucas aparece no subtítulo

### Tom de voz
- **Terceira pessoa institucional**
- Headings sentenciais com ponto final, curtos, declarativos
- Exemplos:
  - "Operação condicionada. Saída livre."
  - "Rampa por entrega. Sustentação que paga."
  - "Cada degrau exige produtividade e estabilidade comprovadas."

---

## Estrutura do documento (ordem de scroll)

```
[1] HEADER fixo (não sticky)
    Brand "PF" + Pedro Figueiredo Tecnologia + subtítulo (com Lucas)
    À direita: "Para: Hospital São Mateus" + Data + Validade 30 dias + botão "Imprimir / Salvar PDF"

[2] HERO
    Eyebrow: "PROPOSTA DE PRESTAÇÃO DE SERVIÇOS"
    H1 grande (≈ 3rem): "Operação condicionada.\nSaída livre."
    Lead 1 parágrafo: objeto, vigência 12 meses, regime PJ-PJ

[3] RAMPA (timeline horizontal — VARIANTE B aprovada)
    Eyebrow: "REMUNERAÇÃO"
    H2: "Rampa por entrega. Sustentação que paga."
    Sub-lead 1 frase: "O fixo mensal cresce conforme cada solução entra em produção e estabiliza por 30 dias."
    Timeline de 4 pontos (Início · Reuniões · Site · Ana), com:
      — Marco (título + 1 frase)
      — Linha "Pedro X · Lucas Y"
      — Total grande (Inter 900, ~1.4rem)
      — Último ponto destaca em laranja
    Legenda mínima: "Valores mensais · NF única emitida pelo CNPJ Pedro Figueiredo Tecnologia LTDA."

[4] INCLUSOS
    Eyebrow: "INCLUSO NO FIXO"
    H2: "O que vem junto."
    4 cartões em grid 2×2 (mobile: stack vertical):
      — Sustentação em produção
      — Presença em Bangu
      — Programa de imersão em IA
      — Stack de IA viva (Claude Code Max)
    Cada cartão: ícone (svg minimalista) + título + 1 frase de explicação

[5] FASE 2 — RETELL
    Eyebrow: "FASE 2 · CONDICIONAL"
    H2: "Retell entra quando fizer sentido."
    Parágrafo curto: dependências, riscos, estudo
    Mini-tabela inline:
      — Implementação: R$ 1.000 (Pedro) + R$ 1.000 (Lucas) — fee único
      — Sustentação: +R$ 2.000 (Pedro) + R$ 2.000 (Lucas) — somam ao fixo vigente
    Frase final: "Pré-requisito: estudo técnico assinado pelas partes."

[6] CLÁUSULAS
    Eyebrow: "CLÁUSULAS"
    H2: "As regras do jogo."
    4 cards densos em grid 2×2 (mobile: stack):
      — Saída livre (15 dias, simétrica)
      — Condicionamento da rampa
      — Propriedade intelectual
      — Confidencialidade & LGPD
    Cada card: número grande (01/02/03/04 em Inter 900 laranja) + título + 2-3 linhas

[7] FOOTER
    Vigência 12 meses · Foro RJ · Contato (email pmrdef@gmail.com — TBD)
    Linha de assinatura: 2 caixas (Pedro Figueiredo Tec / Hospital São Mateus)
    Data + cidade
```

### Animações orquestradas

Vanilla JS + IntersectionObserver + CSS transitions. Sem libraries externas.

| Elemento | Trigger | Animação |
|---|---|---|
| Hero brand + H1 | Page load | `fadeUp` 600ms ease-out, stagger 80ms |
| Rampa (timeline) | 30% no viewport | Linha desenha de esquerda pra direita (`stroke-dasharray` 800ms); pontos aparecem com stagger 120ms; counters dos totais animam de 0 ao valor (1.0s ease-out) |
| Inclusos / Cláusulas / Fase 2 | 30% no viewport | `fadeUp` 500ms ease-out por card, stagger 80ms |
| Cards (hover) | mouseenter | `translateY(-2px)` + sombra 220ms |
| Botão Imprimir | hover/active | feedback tátil sutil |

**Acessibilidade:** todas as animações desligadas via `@media (prefers-reduced-motion: reduce)`.

**Print/PDF:** todas as animações desligadas, layout flui em sequência, header reaparece em cada página, rampa e cards renderizam estado final imediatamente.

---

## Arquivos críticos a modificar

| Arquivo | Ação | Notas |
|---|---|---|
| `blueprint/proposta-trabalho/proposta.html` | **Sobrescreve** (965 → ~500 linhas) | Single-file vanilla, Google Fonts CDN (Inter), `@media print` |
| `blueprint/proposta-trabalho/CLAUSULAS-COMUNS.md` | **Encolhe drasticamente** (300 linhas → ~80) | Mantém só as 4 cláusulas que aparecem no HTML, em texto longo, para o advogado |
| `blueprint/proposta-trabalho/README.md` | **Atualiza** | Refletir estrutura nova (sem abas, sem 3 cenários, fonte Inter, rampa por marco) |

### Decisões em aberto a registrar no HTML como placeholders/comentários

1. **`[Lucas SOBRENOME]`** — substituir antes de enviar
2. **Email no footer** — default `pmrdef@gmail.com`; trocar se Pedro tiver email de domínio próprio
3. **Cidade da assinatura** — default "Rio de Janeiro"
4. **Data da proposta** — default "Maio de 2026" no header; trocar para data exata no envio

Comentários HTML `<!-- TROCAR ANTES DE ENVIAR: ... -->` em volta dos placeholders.

---

## Verificação

1. **Abrir no Chrome:** `open blueprint/proposta-trabalho/proposta.html` — checar fontes Inter carregadas, animações da rampa entrando suaves, hover dos cards
2. **Print/PDF:** `Cmd+P` → "Salvar como PDF" — conferir layout limpo, sem barras de animação, header preservado, totais da rampa renderizados em estado final
3. **Reduced motion:** DevTools → "Emulate CSS media feature: prefers-reduced-motion: reduce" — animações sumiriam, layout permanece
4. **Mobile < 768px:** redimensionar janela — timeline da rampa empilha em vertical, cards 2×2 viram stack, header empilha vertical
5. **Substituir placeholder Lucas:** Pedro substitui `[Lucas SOBRENOME]` em ≤2 lugares (header + cláusulas)
6. **Comparar peso:** novo HTML deve estar ~50% menor que o atual em linhas

---

## Critérios de sucesso

- [ ] HTML abre direto no browser (Chrome/Safari/Firefox), sem erro de console
- [ ] Fonte Inter carrega via Google Fonts CDN
- [ ] Paleta preto/creme/laranja reproduz com fidelidade ao mockup aprovado
- [ ] Rampa horizontal renderiza com Pedro/Lucas nominais (após substituição do placeholder), totais R$ 6k → R$ 8k → R$ 10,5k → R$ 15k
- [ ] Animações ativas no scroll (rampa, cards, hero)
- [ ] `prefers-reduced-motion: reduce` desliga animações
- [ ] PDF exportado preserva layout em sequência única, sem cortes em cards/cláusulas
- [ ] Mobile < 768px responsivo (rampa stackeia, cards stackeiam)
- [ ] Pedro consegue editar valores diretamente no HTML (números em local óbvio)
- [ ] CLAUSULAS-COMUNS.md reflete só as 4 cláusulas centrais
- [ ] README.md atualizado pra refletir nova estrutura

---

## Riscos e mitigações

- **Risco:** Pedro acha que tirou demais (sem ROI, sem fees variáveis, sem modalidade fiscal) e o presidente do hospital sente falta de defesa institucional
  **Mitigação:** Manter `proposta-old.html` como backup local antes de sobrescrever (Pedro decide se descarta)
- **Risco:** O laranja `#ea580c` parecer agressivo demais para audiência institucional
  **Mitigação:** Variável CSS `--accent` central em `:root`; trocar pra outro tom é 1 linha de edição
- **Risco:** Animações na rampa atrapalhem a leitura no PDF
  **Mitigação:** `@media print` força estado final imediato; testar antes de declarar pronto
- **Risco:** Sobrenome do Lucas + nomes finais vazarem como placeholder na exportação
  **Mitigação:** Comentários `<!-- TROCAR ... -->` ao redor; checklist de "trocar antes de enviar" no README

---

## Execução / Resultados

### 2026-05-08 — Redesign editorial minimalista quente aplicado

Reescrita executada via combinação de skills do pacote Leonxlnx/taste-skill (`design-taste-frontend` baseline + `minimalist-ui` voz dominante + `high-end-visual-design` highlights + `redesign-existing-projects` auditoria), seguindo o plano `~/.claude/plans/como-eu-posso-utiliza-las-stateful-comet.md`.

**Mudanças aplicadas no `blueprint/proposta-trabalho/proposta.html`:**

1. **Tipografia trocada.** Saiu Inter, entraram Fraunces (display serif editorial, opsz variável 9-144), Geist (sans), Geist Mono (números/labels). Pesos abandonaram 800/900 (gritão) e foram pra 300-600 (editorial calmo).
2. **Paleta refinada.** Charcoal `#1A1A1A` no lugar do preto absoluto `#0c0a09`. Border `#EAEAEA` mais limpo. Accent laranja queimado `#EA580C` mantido como única hue.
3. **Layout reescalado.** Max-width 880px (corpo) e 1120px (rampa+header+footer). Padding seção generoso `clamp(72px, 8vw, 128px)`. Whitespace dominante.
4. **Hero reformatado.** Grid assimétrico 1.6fr/1fr. À esquerda eyebrow mono + H1 Fraunces 2 linhas (segunda linha em italic accent). À direita coluna estreita com número-âncora "15 dias" em Fraunces light + label mono "AVISO DE SAÍDA, SIMÉTRICO".
5. **Rampa reescrita.** Stepper horizontal com linha 1px conectando, dots 11px (laranja no peak), totais em Geist Mono. Numeração "Marco 01/02/03" + "Próxima fase" no Retell.AI. Breakdown e tasks mantêm conteúdo factual.
6. **Inclusos sem ícones.** Removidos os 4 SVGs Lucide-style. Substituídos por `item-num` mono ("01 · Sustentação", etc) + h3 Fraunces. Cards com border-top 1px (não 4 lados).
7. **Cláusulas com hierarquia editorial.** `clause-num` em mono accent, h3 Fraunces grande com palavra-chave em italic warm gray (`<span class="em">livre</span>`). Border-top 1px charcoal forte (não border completa).
8. **Banner "Lembrete" reformulado.** Sumiu o fundo verde `#f0fdf4` e o `∞` decorativo. Virou linha 1px + tag mono accent + statement Fraunces 1.25rem com palavra em italic accent.
9. **Footer reorganizado.** `foot-statement` Fraunces light "Pronto pra começar juntos." + 3 colunas meta + foot-end com data em mono uppercase + nota em Fraunces italic small.
10. **A11y/print polidos.** Skip-to-content link, focus-visible global em `<a>`, `prefers-reduced-motion` respeitado, `@media print` força stack vertical da rampa pra caber em A4 com sizes em pt.

**Conteúdo factual preservado:**
- Marcos: Kick off (R$ 8.400) → Site (R$ 9.400) → Ana N8N (R$ 15.400, peak) → Retell.AI (futuro)
- Breakdown: Pedro/Lucas + Claude · Pedro/Lucas + Servidor
- Inclusos: Sustentação, Presença em Bangu, Imersão em IA, Stack de IA viva
- Cláusulas: Saída livre, Rampa condicionada, Código fica com o hospital
- Brand: Flowtech Soluções, mark "FT", placeholder `[Lucas SOBRENOME]`
- Email: pmrdef@gmail.com
- Contato: Rio de Janeiro · maio · 2026 · vigência 12 meses

**Backup:** `blueprint/proposta-trabalho/proposta-pre-redesign.html` (snapshot pré-Fase 1).
**Tokens:** `blueprint/proposta-trabalho/proposta-design-tokens.md` (referência única pras skills).

**Pendências (não aplicadas, decisão do Pedro):**
- Substituir `[Lucas SOBRENOME]` antes de enviar (header + footer).
- Considerar 4ª cláusula explicitando LGPD/confidencialidade (atualmente fundida na cláusula 03).
- Avaliar se número-âncora "15 dias" do hero deveria ir pra Mono (consistência) ou ficar em Fraunces (drama editorial). Decidiu-se manter em Fraunces como exceção editorial consciente.
- Revisar manualmente `CLAUSULAS-COMUNS.md` e `README.md` pra refletir a estrutura nova (continuam com conteúdo da versão anterior).

**Verificação executada:**
- Tags HTML balanceadas (validador heurístico Python).
- Zero `style=""` inline.
- Zero referências à fonte Inter (3 ocorrências de "Inter" remanescentes são `IntersectionObserver`).
- Arquivo aberto no Chrome via `open` — render OK.

---

## Pós-aprovação

Depois do `ExitPlanMode` aprovado, mover este arquivo para:
```
<repo>/planos/plano-26-05-01-HHMMh-redesign-proposta-pj-hospital-sao-mateus.md
```
(timestamp da hora real do save), conforme regra do `CLAUDE.md` global. Apagar o original em `~/.claude/plans/`.
