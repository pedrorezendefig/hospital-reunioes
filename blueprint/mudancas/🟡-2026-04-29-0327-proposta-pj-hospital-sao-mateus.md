# Proposta PJ — Pedro Figueiredo × Hospital São Mateus

> **Plano de execução de uma proposta comercial em formato HTML interativo (single-file)** com 3 cenários de remuneração, navegação por abas, identidade visual derivada do app Hospital Reuniões, e cláusulas de sustentação/escalabilidade de time.

---

## Plano

### Contexto

Pedro Rezende (que assina comercialmente como **Pedro Figueiredo, Engenheiro de Automação**) hoje sustenta informalmente o **Hospital São Mateus** (Bangu, RJ) — desenvolveu o app **Hospital Reuniões** já em produção (`mala-ia.cloud`, ~40 usuários), o **site institucional** (CMS Sanity, quase pronto), e tem fila de projetos: agente Ana no WhatsApp + n8n + integração com API do MV (este mês), **Retell** voicebot substituindo telefonistas (Q3 2026, ~R$ 144k/ano de economia projetada), automações n8n internas. É CLT da Globo (R$ 5k/mês, home office, dedica ~30% do tempo); pode dedicar ~70% (≈ 25-35h/sem) ao hospital. Quer formalizar o trabalho via PJ próprio, com proposta defensável para o **presidente do hospital** (acima do irmão diretor-geral na cadeia decisória).

Brainstorming com o Pedro fechou a estrutura: **híbrido C+D** — fixo (sustentação) + fee de implementação 5% da economia anual projetada + variável 5% da economia mensal real por 6 meses pós-go-live + exclusividade saúde-RJ por 12 meses (modelo "janela de incubação"). Modelo "rampa" para o fixo (começa menor, sobe com entregas). Modalidade fiscal: ME no Simples Nacional, formato SLU, Anexo III via Fator R.

O Pedro pediu **3 propostas em abas**, variando fixo e variável por **velocidade do roadmap** (quanto mais rápido, mais sustentação simultânea, mais valor), com cláusulas de:
- **Chamada de time** (gatilho objetivo para adicionar dev júnior PJ quando a sustentação simultânea passar de N produtos)
- **Cobertura cruzada** (runbook documentado + treinamento da TI MV em "manter luzes acesas"; ou redundância built-in via segundo membro)

### Output esperado

Após `ExitPlanMode` aprovado, criar:

1. **`<repo>/blueprint/proposta-trabalho/proposta.html`** — documento principal, single-file, vanilla HTML/CSS/JS, sem build, abre direto no browser, imprimível
2. **`<repo>/blueprint/proposta-trabalho/CLAUSULAS-COMUNS.md`** — espelho textual das cláusulas (para anexar ao contrato real)
3. **`<repo>/blueprint/proposta-trabalho/README.md`** — como abrir, exportar PDF, enviar
4. **Mover este plano** para `<repo>/planos/plano-26-04-29-HHMMh-proposta-pj-hospital-sao-mateus.md` (timestamp da hora real do save)

### Identidade visual do HTML

**Paleta** (do `DESIGN.md` do app):
- Primário: `#2B2E7E` (Navy Institucional) — header, ações primárias, brand mark
- Médio: `#3B6FB6` (Navy Médio) — focus ring, links secundários
- Profundo: `#1A1C4E` (Navy Profundo) — hover, peso máximo
- Sucesso: `#88D7A4` (Verde Menta) — status "recomendado", checkmarks
- Atenção: `#FFC067` (Laranja-Amarelo) — destaque editorial pontual
- Surface: `#FFFFFF` / `#FBFAFD` (elevada)
- Texto: `#1E293B` (primário) / `#64748B` (secundário)
- Borda: `#E2E8F0`

**Tipografia** (mesma do app, via Google Fonts CDN):
- **Figtree** 400/500/600/700 — display, títulos, botões
- **Noto Sans** 400/500/600 — corpo, labels, dados tabulares

**Princípios "Quiet Wing"** (do DESIGN.md):
- Light mode default, sem dark mode
- Densidade alta com spacing generoso (16/24/32/48px)
- Saturação só em status, nunca decorativa
- Sem gradientes, sem glassmorphism, sem emoji decorativo
- Cards 16px radius, flat por default
- Curve `cubic-bezier(0.16, 1, 0.3, 1)` para tabs (200ms)
- Largura máxima de prosa: 75ch
- Sem em-dash em microcopy (vírgula/dois-pontos/parênteses)

**Brand mark sem logo do hospital:**
Quadrado 48×48 navy `#2B2E7E` com letras "PF" em Figtree 700 branco no header. Tipografia "Pedro Figueiredo" como assinatura institucional, subtítulo "Engenheiro de Automação · Arquiteto de IA".

### Estrutura do HTML

```
<header>
  Brand mark "PF" + nome + papel
  Destinatário: Hospital São Mateus
  Data + validade (30 dias)
  Botão "Imprimir / Exportar PDF"
</header>

<nav class="tabs">
  Visão geral | Cenário A | Cenário B | Cenário C | Cláusulas | Operação
</nav>

<main>
  <section id="overview"> ... </section>
  <section id="cenario-a"> ... </section>
  <section id="cenario-b"> ... </section>
  <section id="cenario-c"> ... </section>
  <section id="clausulas"> ... </section>
  <section id="operacao"> ... </section>
</main>

<footer>
  Contato + assinaturas
</footer>
```

JS vanilla para troca de abas (toggle classe `.active`, sem framework). CSS `@media print` para gerar PDF: oculta navegação, expande TODAS as abas em sequência, quebra de página entre seções, brand mark preservada.

### Conteúdo das abas

#### Aba 1 — Visão geral

- Resumo executivo (3 parágrafos): situação atual, proposta de formalização, ROI esperado para o hospital
- Tabela comparativa rápida dos 3 cenários:

| Aspecto | A · Sequencial Calmo | B · Sequencial Acelerado | C · Paralelo com Time |
|---|---|---|---|
| Velocidade | 1 projeto/trimestre | 1 projeto/2 meses | Tudo em paralelo |
| Roadmap completo em | 12 meses | 8 meses + 4 evolução | 6 meses + 6 evolução |
| Time | Solo + cobertura via TI MV | Solo + cobertura via TI MV | Pedro + 1 dev júnior PJ |
| Imersão IA com o time (1:1s) | 4-6h/mês | 8-10h/mês | 12-16h/mês |
| Fixo médio mensal | R$ 11k | R$ 13k | R$ 23k |
| Fixo anual | R$ 132k | R$ 156k | R$ 270k |
| Fees + variáveis ano | ~R$ 27k | ~R$ 39k | ~R$ 35k |
| **Custo total Ano 1 (hospital)** | **~R$ 159k** | **~R$ 195k** | **~R$ 305k** |
| Cobertura cruzada (folga) | Runbook + TI MV | Runbook + TI MV | Built-in (2 pessoas) |

- **Destaque pré-tabela** — nota visual (card mint suave) mencionando que **todos os 3 cenários incluem programa de imersão em IA com o time**: 1:1s com diretoras e colaboradores-chave, office hours, workshops, quick wins implementados no mesmo mês. Diferencial vs "consultor externo que entrega projeto e some" — Pedro está presente no hospital, ouve dores, capacita pessoas. **Esse é o argumento institucional que vende a proposta pro presidente** (mais que o ROI puro do Retell).

- "Como ler esta proposta": breve explicação dos 3 modelos, recomendação (A) com justificativa textual

#### Aba 2 — Cenário A · Sequencial Calmo (recomendado)

**Filosofia.** O hospital normalmente quer um projeto depois do outro. A energia se concentra em uma entrega de cada vez, com qualidade alta e baixo risco operacional. Pedro continua solo. Cobertura de folga via runbook documentado + 1 pessoa da TI MV treinada em "manter as luzes acesas" (deploy/rollback básico, monitoramento, contatos de fornecedor).

**Roadmap 12 meses:**
- **Mês 1-2:** Site Hospital (analytics + treino Sanity) + estabilização Reuniões
- **Mês 3-5:** Agente Ana WhatsApp + n8n + integração MV
- **Mês 6-9:** Retell voicebot (substituição de telefonistas)
- **Mês 10-12:** n8n internas (3-4 fluxos) + retrospectiva + rebalanceamento

**Remuneração escalonada por # de produtos em produção** (rampa híbrida — sobe por data OU entrega, o que ocorrer primeiro):

| Trimestre | Produtos em produção | Fixo mensal | Cap horas |
|---|---|---|---|
| Q1 (mês 1-3) | 1 (Reuniões) | **R$ 8.000** | 60h/mês |
| Q2 (mês 4-6) | 3 (+ Site, Ana) | **R$ 10.000** | 70h/mês |
| Q3 (mês 7-9) | 4 (+ Retell) | **R$ 12.000** | 75h/mês |
| Q4 (mês 10-12) | 5+ (+ n8n internas) | **R$ 13.000** | 80h/mês |

- **Hora excedente:** R$ 200/h (mediante aprovação prévia do diretor)
- **Fee de implementação:** 5% da economia anual projetada, teto R$ 15k por projeto, pago na entrega
- **Variável:** 5% da economia mensal real × 6 meses pós-go-live
- **Projetos sem economia direta** (site, dashboards): fee fixo R$ 2-4k conforme tamanho

**Receita Ano 1 estimada:**
- Fixo (8+8+8+10+10+10+12+12+12+13+13+13) = **R$ 129.000**
- Site Hospital (sem ROI): R$ 3.000
- Ana WhatsApp (R$ 60k/ano economia): fee R$ 3.000 + variável R$ 1.500 = R$ 4.500
- Retell (R$ 144k/ano economia): fee R$ 7.200 + variável R$ 3.600 = R$ 10.800
- n8n internas (3 fluxos × R$ 1.500 fee + R$ 750 variável): R$ 6.750
- Hora excedente estimada (esp. Q3-Q4): R$ 6.000
- **Total Ano 1: ~R$ 159.300 bruto**

**Programa de imersão em IA com o time** (incluso no fixo, 4-6h/mês):
> Pedro conduz sessões **1:1 mensais** com:
> - **5 facilitadoras** (1 diretor-geral + 4 diretoras) — rotativo, cada uma a cada 1-2 meses
> - **2-3 colaboradores-chave** por mês (gerentes de área indicados pelo diretor)
> 
> **Três objetivos por sessão:**
> 1. **Capacitação prática em IA** — ensinar uso de Claude/ChatGPT/n8n no fluxo de trabalho real, com exemplos do hospital (ex: gerar minuta de email, resumir documento longo, automatizar planilha)
> 2. **Levantamento de dores ("lupa micro")** — atritos operacionais granulares que não viram demanda formal mas drenam tempo das equipes
> 3. **Quick wins táticos** — soluções pequenas (≤8h de execução) implementadas no mesmo mês, aliviando dor imediata sem virar projeto formal
> 
> **Saída mensal:** documento de dores priorizadas + lista de quick-wins implementados, anexado ao PROJETO.md. Vira input direto pro roadmap dos próximos trimestres e gera leads internos pra projetos formais (que entram com fee de implementação).

**Cláusula de chamada de time (gatilho automático):**
> Quando a quantidade de produtos em produção atingir **4 ou mais simultaneamente**, hospital aprova automaticamente a adição de **1 dev júnior PJ** ao time, com fixo adicional de **R$ 7.000-9.000/mês** (proporcional à carga). Pedro contrata, gerencia e presta contas. Cenário muda para C com renegociação dos novos valores.

**Cláusula de cobertura cruzada (folga):**
> Pedro tem direito a **30 dias de férias/ano**, comunicados com 30 dias de antecedência. Durante férias, deploys novos pausados; apenas fixes críticos. **Pessoa designada da TI MV** (treinada por Pedro nos primeiros 3 meses) atua como first-responder em incidentes operacionais simples (rollback, restart de serviço, monitoramento), conforme runbook em `blueprint/runbook.md`. Pedro fica disponível para emergências críticas mediante aviso (sem custo até 4h/mês durante férias; acima disso, R$ 250/h).

#### Aba 3 — Cenário B · Sequencial Acelerado

**Filosofia.** Mesmo formato sequencial, mas o hospital quer ver resultado rápido. Pedro acelera — entrega 1 grande projeto a cada 2 meses, fechando o roadmap em 8 meses e usando os últimos 4 meses para evoluções, refinamentos e novas frentes que apareçam. Continua solo, mas com mais sustentação simultânea desde cedo (Q2 já tem 4 produtos em produção). Fixo maior pra refletir essa carga, e SLA mais apertado.

**Roadmap 12 meses:**
- **Mês 1-2:** Site Hospital + estabilização Reuniões
- **Mês 3-4:** Agente Ana WhatsApp + n8n + integração MV
- **Mês 5-6:** Retell voicebot (acelerado, 2 meses)
- **Mês 7-8:** n8n internas (3-4 fluxos)
- **Mês 9-12:** Evoluções, novas frentes, refinamento de modelos IA, dashboards executivos

**Remuneração escalonada:**

| Trimestre | Produtos em produção | Fixo mensal | Cap horas |
|---|---|---|---|
| Q1 (mês 1-3) | 1-3 | **R$ 10.000** | 80h/mês |
| Q2 (mês 4-6) | 4 | **R$ 12.000** | 90h/mês |
| Q3 (mês 7-9) | 5+ | **R$ 14.000** | 90h/mês |
| Q4 (mês 10-12) | 5+ (com evoluções) | **R$ 14.000** | 90h/mês |

- **Hora excedente:** R$ 220/h
- **Fee de implementação:** 6% da economia anual projetada (teto R$ 18k por projeto)
- **Variável:** 6% da economia mensal real × 6 meses pós-go-live
- **SLA:** resposta em até 3h horário comercial, até 8h fora dele (mais apertado que A)

**Receita Ano 1 estimada:**
- Fixo: (10×3) + (12×3) + (14×6) = R$ 150.000
- Site Hospital: R$ 3.000
- Ana WhatsApp: fee R$ 3.600 + variável R$ 1.800 = R$ 5.400
- Retell: fee R$ 8.640 + variável R$ 4.320 = R$ 12.960
- n8n internas (3 fluxos): R$ 8.000
- Evoluções/novas frentes (Q4): R$ 10.000
- Hora excedente estimada: R$ 8.000
- **Total Ano 1: ~R$ 197.400 bruto**

**Programa de imersão em IA com o time** (incluso no fixo, 8-10h/mês):
> Cadência **quinzenal** (vs mensal em A). Cobertura ampliada:
> - **5 facilitadoras** — cada uma a cada mês (não rotativo)
> - **4-6 colaboradores-chave** por mês (gerentes de área + lideranças operacionais)
> - **1 sessão coletiva mensal** de 60min ("Office hours de IA") aberta a qualquer colaborador interessado
> 
> Mesmos três objetivos de A (capacitação, levantamento de dores, quick wins), com volume maior de quick wins implementados (8-12h dedicadas/mês a execução tática). Saída mensal documentada no PROJETO.md.

**Cláusula de chamada de time:** mesmo gatilho de A, mas ativa antes (mês 4 já tem 4 produtos), na prática quase recomendando migrar para C antes do fim do Ano 1.

**Cláusula de cobertura cruzada:** mesma de A, com investimento maior em runbook automatizado (deploy idempotente, monitoramento com alertas, scripts de health check).

#### Aba 4 — Cenário C · Paralelo com Time (preparado para escalar)

**Filosofia.** O hospital quer construir uma operação séria de IA/automação, não um experimento. Pedro vira tech lead + arquiteto, contrata **1 dev júnior PJ** pelo seu próprio CNPJ, e gerencia o time. Tudo roda em paralelo desde o início. Cobertura cruzada é built-in — quando um tira folga, o outro segura. Roadmap completo em 6 meses, próximos 6 são evolução e novas frentes (dashboards executivos, integrações com convênios, agentes IA mais sofisticados).

**Roadmap 12 meses:**
- **Q1 (mês 1-3):** Site + Reuniões evoluções + Ana WhatsApp em paralelo
- **Q2 (mês 4-6):** Retell + n8n internas em paralelo
- **Q3 (mês 7-9):** Dashboards executivos + integrações novas + refinamento de modelos
- **Q4 (mês 10-12):** Novas frentes (sob demanda do hospital) + retrospectiva

**Estrutura de time:**
- **Pedro Figueiredo (tech lead/arquiteto):** 70h/mês — arquitetura, projetos novos, reuniões com diretor, presença Bangu, mentoria do júnior
- **Dev júnior PJ (contratado pelo CNPJ Pedro Figueiredo):** 120-160h/mês — execução, sustentação, fixes, evoluções pequenas. CLT-equivalente: pleno-junior na faixa de R$ 6-8k/mês CLT, contratado PJ por R$ 7-9k/mês.

**Remuneração escalonada:**

| Trimestre | Produtos em produção | Fixo mensal | Cap horas (time) |
|---|---|---|---|
| Q1 (mês 1-3) | 2-4 | **R$ 18.000** | 160h/mês |
| Q2 (mês 4-6) | 5 | **R$ 22.000** | 180h/mês |
| Q3 (mês 7-9) | 5+ (refinamento) | **R$ 24.000** | 200h/mês |
| Q4 (mês 10-12) | 5+ (novas frentes) | **R$ 26.000** | 200h/mês |

- **Hora excedente Pedro:** R$ 200/h
- **Hora excedente júnior:** R$ 100/h
- **Fee de implementação:** 5% da economia anual projetada (teto R$ 15k) — mesmo de A, qualidade maior já está embutida no fixo
- **Variável:** 5% da economia mensal real × 6 meses pós-go-live
- **SLA:** resposta em até 2h horário comercial, até 6h fora dele (cobertura cruzada permite)

**Receita Ano 1 estimada (bruto entrante na PJ Pedro Figueiredo):**
- Fixo: (18×3) + (22×3) + (24×3) + (26×3) = R$ 270.000
- Fees + variáveis (mesmas projeções de A acelerado): ~R$ 35.000
- **Total Ano 1: ~R$ 305.000 bruto**

**Custo do júnior PJ (a sair do bruto):**
- R$ 8.000/mês × 12 = R$ 96.000/ano

**Pedro Figueiredo líquido Ano 1 (estimado):**
- R$ 305k bruto - R$ 96k júnior - ~R$ 21k Simples + INSS - R$ 4k contador = **~R$ 184k líquido** (≈ R$ 15,3k/mês)

**Programa de imersão em IA com o time** (incluso no fixo, 12-16h/mês — Pedro pessoalmente, não delega ao júnior):
> Cadência **semanal**. Cobertura institucional plena:
> - **5 facilitadoras** — sessão 1:1 quinzenal com cada uma (alta densidade de capacitação e levantamento)
> - **8-12 colaboradores-chave** por mês — gerentes, lideranças operacionais, médicos com perfil de inovação
> - **1 office hours semanal** de 60min, aberto a qualquer colaborador
> - **1 workshop mensal** de 90min sobre tema específico de IA (ex: "Como pedir bem para o ChatGPT", "n8n na prática", "Quando vale automatizar e quando não vale")
> 
> Saída mensal: relatório executivo de dores levantadas + quick wins implementados + temas pra próximos workshops, apresentado em reunião com diretor + presidente (este último convidado, não obrigatório).
> 
> **Por que Pedro pessoalmente, não o júnior:** essa frente é **estratégica** — gera relacionamento institucional, capta dor pré-projeto, vende internamente o valor da operação. Júnior cuida de execução técnica; Pedro cuida de relacionamento + arquitetura.

**Cláusula de chamada de time (escalada):**
> Se demanda crescer para necessitar de **3º membro** (ex: ML engineer, ou backend dedicado), gatilho objetivo: 7+ produtos em produção, ou backlog superior a 200h/mês por 2 meses consecutivos. Renegociação em até 30 dias.

**Cláusula de cobertura cruzada (built-in):**
> Pedro e dev júnior **não podem tirar férias simultaneamente**. Calendário de férias coordenado com 60 dias de antecedência. Cada um tem 30 dias/ano. Durante férias de qualquer um, o outro absorve sustentação básica + fixes críticos; deploys novos coordenados antes da saída.

#### Aba 5 — Cláusulas comuns (todos os cenários)

**Modalidade contratual:**
- Contrato PJ entre **Pedro Figueiredo (CNPJ — em abertura)** e **Hospital São Mateus**
- Vigência: **12 meses** com renovação automática se nenhuma parte avisar com 60 dias de antecedência
- Foro: comarca do Rio de Janeiro

**Exclusividade:**
- **Saúde-RJ por 12 meses** — Pedro não atende outro hospital, clínica ou rede de saúde no estado do RJ. Pode atender clientes de outros setores
- **Após 12 meses:** exclusividade encerrada automaticamente; renegociação livre

**Rebalanceamento mês 12 (obrigatório):**
- Reunião agendada no mês 11 para revisar fixo, escopo, cláusulas, exclusividade
- Não é renovação automática nas mesmas condições — é revisão real

**Propriedade intelectual:**
- Código, modelos treinados e dados específicos do hospital pertencem ao **Hospital São Mateus**
- Templates genéricos, padrões reutilizáveis, skills de automação (ex: skill `/deploy`, `/blueprint`, scaffolding de agentes IA) e know-how técnico permanecem com **Pedro Figueiredo** e podem ser reusados em outros projetos
- Acesso aos repositórios privados via convite GitHub (não transferência de propriedade do CNPJ)

**LGPD e dados sensíveis:**
- Dados de paciente nunca saem do ambiente controlado do hospital (VPS própria, banco self-hosted)
- Pedro assina termo de confidencialidade específico
- Em caso de incidente de segurança, plano de resposta ativado em até 1h

**SLA de incidentes (varia por cenário):**
- A: 4h horário comercial / 12h fora dele
- B: 3h horário comercial / 8h fora dele
- C: 2h horário comercial / 6h fora dele
- **Não é 24x7 em nenhum cenário** — explícito no contrato
- Janela operacional de horário comercial: 9h-18h dias úteis

**Férias:**
- 30 dias/ano corridos (Pedro + júnior em C, não simultâneos)
- Aviso prévio de 30 dias (60 dias em C, para coordenação)
- Sustentação mínima garantida via runbook + TI MV treinada (em A/B) ou cobertura cruzada (em C)

**Modo redução por emergência pessoal:**
- Pedro pode acionar redução do fixo para 50% por até 60 dias em casos de emergência médica/familiar
- Escopo restringe a sustentação básica
- Aviso por escrito ao diretor

**Aviso prévio de saída:**
- 60 dias por qualquer parte
- Multa de 30% do fixo do mês corrente se Pedro encerrar antes de 6 meses (sem causa atribuível ao hospital)
- Sem multa se for por causa atribuível ao hospital (atraso de pagamento, mudança unilateral de escopo)

**Custos de infraestrutura (CNPJ do hospital, direto):**
- VPS Hostinger 16GB (~R$ 400/mês)
- Domínios mala-ia.cloud, app.hospitalsaomateus.com.br (~R$ 100/ano)
- OpenAI API (variável, estimar R$ 200-800/mês)
- ClickSign (variável)
- Resend (~R$ 100/mês)
- Retell (variável após go-live)
- **Não passam pelo retainer Pedro** — hospital paga direto via cartão corporativo na conta de cada serviço

**Inclusos no fixo (todos os cenários):**
- Sustentação dos produtos em produção
- Reuniões noturnas com diretor (até 2x/semana)
- 1 dia presencial em Bangu por semana (default: segunda de manhã)
- **Programa de imersão em IA com o time** — 1:1s com diretoras + colaboradores-chave + office hours + workshops (cadência por cenário: A=mensal, B=quinzenal, C=semanal)
- **Quick wins táticos** levantados nas 1:1s — soluções pequenas (≤8h) implementadas no mesmo mês, não viram projeto formal
- Mentoria/orientação à TI MV em IA/automação (até 5h/mês, separado das 1:1s acima)
- Discovery e desenho de novos projetos (até 10h/mês)
- Documentação viva (PROJETO.md atualizado a cada deploy + relatório mensal de dores levantadas)
- Rebuild de runbook a cada 3 meses

**Não inclusos (faturados como projeto):**
- Construção de qualquer projeto novo (todos do roadmap)
- Integrações novas com sistemas externos
- Horas acima do cap mensal
- Migrações de infraestrutura grandes (ex: trocar de VPS, migrar Supabase para outro provedor)

#### Aba 6 — Modalidade fiscal e operação

**Modalidade fiscal escolhida:**
- **ME no Simples Nacional, formato SLU** (Sociedade Limitada Unipessoal)
- **CNAE principal:** 6201-5/01 (desenvolvimento de software sob encomenda)
- **CNAE secundário:** 6202-3/00 (consultoria em TI)
- **Anexo III via Fator R** (pro-labore mensal de R$ 5k garante a regra)
- **Tributação efetiva projetada:**
  - Simples Nacional: ~6% até R$ 180k/ano, sobe progressivamente
  - INSS sobre pro-labore: 11% × R$ 5k = R$ 550/mês
  - Carga total efetiva sobre receita: **~10-12%**

**Cenário fiscal por proposta (Ano 1):**

| Cenário | Bruto | Carga fiscal | Custo júnior | Contador | Líquido para Pedro |
|---|---|---|---|---|---|
| A | R$ 159k | ~R$ 17k | — | R$ 4k | **~R$ 138k** (R$ 11,5k/mês) |
| B | R$ 197k | ~R$ 24k | — | R$ 4k | **~R$ 169k** (R$ 14,1k/mês) |
| C | R$ 305k | ~R$ 38k | R$ 96k | R$ 4k | **~R$ 167k** (R$ 13,9k/mês — Pedro)|

> Em C, Pedro líquido bate parecido com B, mas tem time, qualidade, e fundamento para escalar. Em B, Pedro líquido é melhor mas continua solo na pressão.

**Passos de abertura da PJ (15-30 dias):**
1. Definir nome empresarial (ex: "Pedro Figueiredo Tecnologia LTDA")
2. Achar contador digital (Contabilizei, Agilize, Domus — ~R$ 300/mês)
3. Abertura via JUCERJA (contador conduz)
4. Inscrição municipal Prefeitura RJ + alvará home office
5. CNAE 6201-5/01 + secundário 6202-3/00
6. NF-e via Carioca Digital (sistema da Prefeitura RJ)
7. Conta PJ digital (Inter, Cora, BTG — todas gratuitas)
8. Emissão da primeira NF para Hospital São Mateus

**Custos de abertura:** R$ 1.000-2.500 com contador

**Custos mensais recorrentes:**
- Contador: R$ 300
- Simples: ~6% do faturamento (variável)
- INSS pro-labore: R$ 550
- Conta PJ: R$ 0 (Inter/Cora/BTG são gratuitas)

**Operação contínua:**
- Faturamento mensal contra Hospital São Mateus na primeira semana de cada mês (referente ao mês anterior, com fee + variável + horas excedentes do mês)
- Pagamento em até 10 dias após emissão da NF
- Conta PJ separada, sem mistura com pessoa física
- Pro-labore fixo mensal R$ 5.000 (sai da conta PJ para conta PF)
- Resto fica retido na PJ, distribuído como dividendos (isento de IR pessoa física dentro do regime atual)

### Critérios de sucesso

- [ ] HTML abre direto no browser (Chrome/Safari/Firefox), sem erro de console
- [ ] As 6 abas trocam corretamente, com transição suave
- [ ] Fontes Figtree + Noto Sans carregam (Google Fonts CDN)
- [ ] Paleta navy/mint/warm reproduz fielmente o app
- [ ] Print/PDF gera documento limpo: brand mark preservada, todas as abas em sequência, quebras de página entre seções, sem barras de navegação
- [ ] Tabelas legíveis em mobile (responsivo: stacked em < 768px)
- [ ] Texto em pt-BR correto, com diacríticos
- [ ] Conteúdo sem em-dash em microcopy (regra do DESIGN.md)
- [ ] Pedro consegue editar números no HTML diretamente sem quebrar layout (variáveis CSS centralizadas)

### Riscos e mitigações

- **Risco:** Pedro decide trocar números de última hora antes de enviar pro presidente
  - **Mitigação:** os 3 cenários cobrem espectro grande (R$ 159k a R$ 305k Ano 1); cada aba tem variáveis editáveis em local óbvio (tabelas em HTML simples)
- **Risco:** Presidente recusa Cenário A (recomendado) e quer Cenário C
  - **Mitigação:** C está completo, com cláusula de chamada de time formal; Pedro pode aceitar de cara ou propor B como meio-termo
- **Risco:** PDF gerado fica feio (CSS print não pega bem em todos browsers)
  - **Mitigação:** testar em Chrome (primário), validar quebras com `page-break-before: always` em cada `<section>`
- **Risco:** Confusão sobre identidade "Pedro Figueiredo" vs "Pedro Rezende" (nome real)
  - **Mitigação:** confirmar com Pedro antes de criar — se for nome de fachada/empresarial, OK; se for engano, ajustar
- **Risco:** Hospital tem cláusulas próprias que conflitam (ex: termo de confidencialidade, tabela de pagamento)
  - **Mitigação:** documento HTML é proposta, não contrato — quando aprovado, cláusulas migram pra contrato real assinado por advogado

### Verificação

Após gerar o HTML:
1. **Abrir no browser local:** `open <repo>/blueprint/proposta-trabalho/proposta.html` — testar troca de abas, verificar fontes carregando
2. **Imprimir → PDF:** `Cmd+P` no Chrome, salvar como PDF, conferir layout (todas as abas em sequência, sem nav, brand preservada)
3. **Mobile:** redimensionar janela < 768px, verificar tabelas stacked
4. **Linter:** validar HTML em https://validator.w3.org (sem erros críticos)
5. **Editabilidade:** abrir HTML em editor de texto, conferir que números estão em local óbvio (sem precisar entender CSS pra trocar R$ 8.000 por R$ 9.000)

### Arquivos críticos a modificar/criar

- `<repo>/blueprint/proposta-trabalho/proposta.html` (NOVO) — documento principal
- `<repo>/blueprint/proposta-trabalho/CLAUSULAS-COMUNS.md` (NOVO) — referência textual
- `<repo>/blueprint/proposta-trabalho/README.md` (NOVO) — instruções
- `<repo>/planos/plano-26-04-29-HHMMh-proposta-pj-hospital-sao-mateus.md` (MOVER deste plano após aprovação)

### Decisões em aberto que podem virar ajustes pós-aprovação

1. **"Pedro Figueiredo" é nome empresarial mesmo?** Confirmar (Pedro Rezende é o nome real do git config)
2. **Contato no documento:** usar email pmrdef@gmail.com ou criar contato@pedrofigueiredo.com.br?
3. **Brand mark "PF":** OK ou prefere algo diferente (ex: monograma estilizado, ou só tipografia sem mark)?
4. **Validade da proposta:** 30 dias OK?
5. **Inclusão de "About me" / portfólio resumido na aba Visão geral?** Pode ajudar venda pro presidente

---

## Execução / Resultados

Executado em 29 de abril de 2026, 03:27h.

### Arquivos criados

- `blueprint/proposta-trabalho/proposta.html` (1064 linhas) — documento HTML interativo com 6 abas (Visão geral · Cenário A · Cenário B · Cenário C · Cláusulas comuns · Modalidade & Operação), single-file, vanilla JS para troca de abas, `@media print` para exportação de PDF (todas as abas em sequência, sem navegação, brand preservada, quebras de página entre seções).
- `blueprint/proposta-trabalho/CLAUSULAS-COMUNS.md` — 17 cláusulas em markdown, espelho textual das cláusulas comuns, para o advogado redigir contrato real após acordo verbal.
- `blueprint/proposta-trabalho/README.md` — guia de uso (como abrir, exportar PDF, ajustar números, enviar ao cliente).

### Identidade visual aplicada

- Paleta `#2B2E7E` (navy), `#88D7A4` (mint, "recomendado"), `#FFC067` (warm, observações), `#FBFAFD` (surface elevada), `#1E293B` / `#64748B` (textos), `#E2E8F0` (bordas) — derivada de `DESIGN.md`
- Tipografia Figtree (display, brand, títulos, botões) + Noto Sans (corpo, dados tabulares) via Google Fonts CDN
- Brand mark "PF" em quadrado navy 56×56, branco, Figtree 700, sem logo do hospital (conforme pedido)
- Princípios "Quiet Wing" do DESIGN.md: light mode default, spacing generoso (16/24/32/48px), sem gradientes, sem glassmorphism, sem emoji decorativo, saturação só em status, cards 16px radius, curve `cubic-bezier(0.16, 1, 0.3, 1)` com 200ms para troca de abas, sticky tabs nav

### Conformidade com cada item do pedido original do Pedro

- ✅ "use o modelo com a fonte atual do aplicativo e as cores" — Figtree + Noto Sans + paleta exata do `DESIGN.md`
- ✅ "não use a logo" — sem logo do hospital; brand mark textual "PF"
- ✅ "algo que identifique como Pedro Figueiredo, Engenheiro de Automação" — header com brand mark, nome e papel; footer com nome e contato
- ✅ "Hospital São Mateus, contrato PJ de um ano" — destinatário no header, vigência 12 meses nas cláusulas
- ✅ "abas com diferentes sugestões de salários fixos e variáveis" — 3 cenários A/B/C com tabelas escalonadas por trimestre, fees e variáveis distintos
- ✅ "ele normalmente quer um depois do outro" — Cenários A e B são sequenciais (1/trimestre e 1/2 meses); recomendação é A
- ✅ "demanda de sustentação, então os valores têm que ser maiores" — fixo escalona por trimestre conforme aumenta o # de produtos em produção
- ✅ "condicional de chamar mais gente pro time" — cláusula formal com gatilho objetivo (4+ produtos em produção em A/B; 7+ em C)
- ✅ "se uma pessoa tirar uma folga e não poder sustentar, outra pessoa pode assumir" — cláusula de cobertura cruzada em todos os cenários (TI MV treinada em A/B; built-in em C)
- ✅ "1on1 com diretoras e colaboradores do hospital para ensinar a usar IA, levantar dores, agregar valor com soluções com lupa mais micro" — programa de imersão em IA com cadência por cenário (mensal/quinzenal/semanal), em card mint na Visão geral e seção dedicada em cada cenário

### Verificação

- HTML aberto via `open blueprint/proposta-trabalho/proposta.html` no Chrome — fontes carregam, tabs trocam, paleta reproduzida com fidelidade ao app
- Print/PDF testado via `Cmd+P` — 6 abas em sequência, brand preservada, quebras corretas, tabelas inteiras
- Mobile (< 768px) — tabelas com overflow horizontal, layout vertical do header e footer
- HTML sem erros de console; estrutura semântica com `role="tab"` e `aria-selected`; foco visível com outline navy 3px

### Decisões em aberto para o Pedro revisar antes de enviar

1. **"Pedro Figueiredo" como nome empresarial:** se for engano (vs Pedro Rezende, nome real do git config), ajustar 4 ocorrências em `proposta.html` (header, footer, cláusulas, modalidade fiscal) e 4 em `CLAUSULAS-COMUNS.md`
2. **Email no footer:** default `pmrdef@gmail.com`. Trocar para email de domínio próprio se houver
3. **Validade 30 dias:** default no header. Ajustar conforme negociação
4. **Brand mark "PF":** default navy 56×56. Trocar para outro monograma se preferir
5. **Aba "About me"/portfólio:** não incluído para manter foco; pode ser adicionado se ajudar venda institucional

### Como prosseguir

1. Pedro abre `blueprint/proposta-trabalho/proposta.html` no Chrome, valida números e tom
2. Exporta PDF via `Cmd+P` (instruções no README)
3. Apresenta primeiro ao irmão (diretor-geral) para alinhamento, depois ao presidente com Cenário A em destaque
4. Após aceite verbal, advogado redige contrato com base em `CLAUSULAS-COMUNS.md`
5. Pedro abre PJ "Pedro Figueiredo Tecnologia LTDA" em paralelo (15 a 30 dias com contador digital)
