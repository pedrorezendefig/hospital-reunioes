# Plano — PDF da ATA com fonte HP Simplified e visual refinado

## Plano

### Contexto
A geração de PDF de ATAs do Hospital Reuniões é feita server-side em **WeasyPrint** a partir de `backend/app/templates/ata_template.html`. Antes desta entrega:

- Usava Helvetica do sistema (sem fonte custom). O frontend já tinha adotado **HP Simplified** (`frontend/public/fonts/HPSimplified_Rg.ttf`) via `@font-face` em `globals.css`.
- Usava o navy legado `#232d69` em vez do navy oficial `#2B2E7E` definido em `DESIGN.md`.
- `font-size: 11px` no body (minúsculo para A4 impresso).
- Regras básicas de quebra de página, vulnerável a tópicos longos quebrarem feio, h2 órfão antes de assinaturas, badges quebrando em duas linhas.
- Cabeçalho como `<p><strong>` com `min-width` hack.

### Objetivo
Adotar HP Simplified em todo o PDF, formatar páginas certinhas (sem quebras feias), visual lindo e amigável alinhado com a identidade do app.

### Decisões-chave
- **Fonte**: 6 `@font-face` apontando para o mesmo `HPSimplified_Rg.ttf` (pesos 400/600/700, normal e italic) — WeasyPrint sintetiza bold e itálico, evitando fallback no Helvetica em `<strong>`/`<em>`.
- **Paleta** alinhada com `DESIGN.md`: `#2B2E7E` (primary-navy), `#3B6FB6` (primary-medium), `#FBFAFD` (surface-elevated), `#1E293B`/`#64748B` (texto), `#E2E8F0` (border-soft); badges com tints (`#FFF4DE`/`#DCEFFA`/`#D8F2DF`).
- **Tipografia**: body 10.5pt, h1 22pt, h2 14pt, h3 11.5pt, `.topico-titulo` 12pt, badge 8.5pt; line-height 1.55 (1.6 no objetivo).
- **Quebra de página em 3 níveis**:
  - Containers (`.topico`, `.footer-signatures`, `tr`) com `break-inside: avoid`
  - Listas internas (`.topico ul`, `.topico ol`, `tbody`) com `break-inside: auto`
  - Items individuais (`.topico li`, `tr`) com `break-inside: avoid`
  - Headings com `break-after: avoid` + `orphans: 2`
  - `widows: 3; orphans: 3` em parágrafos
- **Refinamentos**:
  - Cabeçalho como `<dl>` (definition list) em vez de `<p><strong>`
  - Tópicos outlined (`border-left: 3px solid #2B2E7E`) sem background
  - Badges full-pill com `white-space: nowrap` e `hyphens: none`
  - Zebra striping em `table.quadro tbody tr:nth-child(even)`
  - `lang="pt-BR"` no `<body>` + `hyphens: auto` (Pango hifeniza pt-BR)
  - Larguras explícitas nas colunas de assinatura
  - Margens `@page` 2cm/1.8cm/1.8cm/1.8cm
- **Logo**: NÃO mexer (escopo separado). Existe `LOGO HSM.png` na raiz que pode ser substituto futuro do `logo_hospital.png`, mas é decisão à parte.

### Arquivos modificados
- `hospital-reunioes/backend/app/services/pdf_generator.py` — passa `font_path` ao template com fallback elegante via `os.path.exists`.
- `hospital-reunioes/backend/app/templates/ata_template.html` — `@font-face` × 6, paleta, tipografia, quebras de página, `<dl>` no cabeçalho, badges nowrap, classe `quadro` na tabela de pendências.

### Arquivo criado
- `hospital-reunioes/backend/app/static/fonts/HPSimplified_Rg.ttf` (cópia, 122KB).

### Critérios de sucesso
- Fonte HP Simplified embutida no PDF gerado (`pdffonts` lista HP-Simplified, HP-Simplified-Bold, HP-Simplified-Semi-Bold, HP-Simplified-Italic).
- Cores no PDF batem com `DESIGN.md` (navy `#2B2E7E` em headers, badges em tint).
- Quebra de página: nenhum h2 órfão, tópicos preservam título com primeira linha, tabelas longas repetem cabeçalho, bloco de assinaturas não quebra entre header+intro.
- Hifenização pt-BR funciona (Vasconcellos → Vascon-cellos).
- `pytest` 168 testes passam.

---

## Execução / Resultados

### Implementação executada (2026-04-27 17:47–18:00)

1. **Fonte para o backend** (✓):
   ```bash
   mkdir -p hospital-reunioes/backend/app/static/fonts
   cp HPSimplified_Rg.ttf hospital-reunioes/backend/app/static/fonts/HPSimplified_Rg.ttf
   ```
   Resultado: 122412 bytes copiados. Dockerfile já cobre via `COPY app/ app/`.

2. **`pdf_generator.py` atualizado** (✓): adicionada resolução de `font_path` com `os.path.exists` + log warning se não existir + passagem de `font_path=f"file://{font_path}"` ao `template.render()`.

3. **Template reescrito** (✓): novo `<style>` com 6 `@font-face`, `@page` ajustado, paleta DESIGN.md, hierarquia tipográfica em pt, regras de quebra em 3 níveis, badges full-pill com nowrap, hifenização pt-BR, larguras explícitas em assinaturas.

### Validação (PDF gerado via WeasyPrint local)

Após instalar `pango` via `brew install pango` (libcairo já estava presente) — necessário só para validar local; em prod o Dockerfile já cobre tudo:

- **Fontes embutidas no PDF (`pdffonts /tmp/ata-final.pdf`)**:
  ```
  HP-Simplified-Semi-Bold     CID TrueType   embedded subset
  HP-Simplified                CID TrueType   embedded subset
  HP-Simplified-Bold           CID TrueType   embedded subset
  HP-Simplified-Italic         CID TrueType   embedded subset
  Helvetica                    CID TrueType   embedded subset  (← apenas para alguns glyphs especiais que HP Simplified não cobre)
  ```
  Bold e Italic funcionam via síntese do Pango. Helvetica regular ainda é usada como fallback automático para glyphs específicos não cobertos pela HP Simplified — comportamento aceito.

- **Visual conferido em 3 páginas**: header institucional limpo, cabeçalho em definition list, tabelas com zebra, tópicos outlined, decisões em caixa azul claro, divergências em vermelho, badges full-pill (Aberto amarelo, Em andamento azul, Concluído verde) — todos sem quebrar de linha.

- **Hifenização pt-BR ativa**: nomes longos como "Vasconcellos" são hifenizados quando precisam quebrar; em badges e `<th>` desabilitada via `hyphens: none` para evitar quebrar "ASSINATURA".

- **Quebra de página**: tópicos preservados como blocos atômicos; "6. Espaço para Assinaturas" (h2 + intro) flui junto, tabela de assinaturas pode quebrar entre signatários se necessário.

### Testes
- `pytest tests/ -x` → **168 passed** em 9.67s. Zero regressões.

### Próximos passos (fora do escopo)
- ~~**Logo HSM**: avaliar se `LOGO HSM.png` (raiz, Apr 27) deve substituir `backend/app/static/images/logo_hospital.png` (Mar 29, antigo).~~ **Feito** em follow-up imediato (2026-04-27 18:18): `LOGO HSM.png` copiada sobre `logo_hospital.png` mantendo o mesmo nome (template não precisou mudar). Mesmas dimensões 926×522, versão RGB com proporções mais limpas — espaçamento maior entre os arcos e o texto "HOSPITAL SÃO MATHEUS".
- **Em-dash em microcopy**: `DESIGN.md` proíbe `—` em microcopy; o template ainda usa em "Hospital São Matheus —", "Ata de Reunião — Tipo", "Cargo — Setor". Sweep separado.
- **PDF/A-1b** para arquivamento institucional pós-ClickSign (`pdf_variant='pdf/a-1b'` no `write_pdf()`).
- **Variantes Bold reais** da HP Simplified: se aparecer reclamação de h1/h2 "borrados" em impressão, buscar `HPSimplified_Bd.ttf` ou migrar para Figtree+Noto Sans (definidos como aspiracionais no `DESIGN.md`).

### Verificação em produção
Quando o usuário rodar `/atualizar-app` e regerar uma ATA já existente (endpoint `POST /{id}/reprocessar`), o novo PDF aparecerá com fonte HP Simplified, paleta atualizada e paginação refinada.
