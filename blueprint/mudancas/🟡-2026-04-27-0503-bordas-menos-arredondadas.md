# Bordas menos arredondadas — sistema todo

## Plano

### Contexto

O diretor do hospital pediu uma mudança de **identidade visual global**: o sistema está com aparência muito arredondada (cards, modais, botões, inputs, dropdowns) e ele quer um visual menos "fofo", mais corporativo e sério, mantendo coerência em toda a UI.

Mapeamento atual:

- **544 ocorrências** de classes `rounded-*` no frontend.
- Distribuição dominante: `rounded-lg` (33,6%), `rounded-xl` (32,2%), `rounded-2xl` (13,6%), `rounded-full` (17,8%).
- O projeto usa **Tailwind v4** via `@tailwindcss/postcss` (sem `tailwind.config.ts`). Já existe um bloco `@theme` em `globals.css` (linhas 30–48) onde tokens de cor e sombra são centralizados.
- **Não há** tokens `--radius-*` definidos hoje — as classes `rounded-*` usam os defaults do Tailwind v4.

Decisões do usuário:

- Intensidade **média / corporativa** — reduzir todos os tokens em ~50%.
- **Manter** `rounded-full` (badges, status pills e avatares continuam circulares).
- **Não** mexer em `backend/app/templates/ata_template.html` (PDF/email isolado).

### Estratégia: ponto único via `@theme`

Tailwind v4 lê os tokens `--radius-*` declarados em `@theme` e aplica em **todas** as classes `rounded-{tamanho}` automaticamente. Uma única edição em `globals.css` cobre as 544 ocorrências sem touch em componente algum. `rounded-full` continua em 9999px (não é redefinido).

Tabela de mudança:

| Classe Tailwind | Default v4 | Novo valor | Uso típico no projeto |
|---|---|---|---|
| `rounded-xs` | 2 px | 1 px | (sem uso atual) |
| `rounded-sm` | 4 px | 2 px | edge cases |
| `rounded-md` | 6 px | 3 px | edge cases |
| `rounded-lg` | 8 px | **4 px** | botões, inputs, dropdowns |
| `rounded-xl` | 12 px | **6 px** | inputs grandes, nav items |
| `rounded-2xl` | 16 px | **8 px** | cards, modais, toasts |
| `rounded-3xl` | 24 px | 12 px | decorativo (login) |
| `rounded-full` | 9999 px | **9999 px** (mantido) | badges, avatares |

### Arquivos a modificar

**Edição central (1 arquivo):**

- `hospital-reunioes/frontend/src/app/globals.css` — adicionar tokens `--radius-*` no bloco `@theme` existente (após linha 47, antes do `}` da linha 48). Também ajustar o focus ring na linha 173 (`border-radius: 8px` → `border-radius: 4px`).

**Ajustes hardcoded fora do alcance do `@theme` (3 arquivos):**

- `hospital-reunioes/frontend/src/components/pendencias/PendenciaDetailModal.tsx:790` — scrollbar custom: `border-radius: 10px` → `border-radius: 5px`.
- `hospital-reunioes/frontend/src/components/dashboard/StatusPieChart.tsx:95` — tooltip recharts: `borderRadius: "12px"` → `borderRadius: "6px"`.
- `hospital-reunioes/frontend/src/components/dashboard/SetorBarChart.tsx:100` — tooltip recharts: `borderRadius: "12px"` → `borderRadius: "6px"`.

**Não tocar:**

- `globals.css` linha 162 (scrollbar thumb global, `border-radius: 999px`) — é fino e ficaria estranho quadrado.
- `backend/app/templates/ata_template.html` (4px e 12px no PDF da ATA) — decisão do usuário.

### Diff conceitual (para referência)

Em `globals.css`, dentro do bloco `@theme` existente:

```css
@theme {
  /* …tokens de cor e sombra existentes… */

  /* Border radius — corporativo, ~50% menor que defaults v4 */
  --radius-xs: 1px;
  --radius-sm: 2px;
  --radius-md: 3px;
  --radius-lg: 4px;
  --radius-xl: 6px;
  --radius-2xl: 8px;
  --radius-3xl: 12px;
  /* rounded-full mantém 9999px (não redefinido) */
}
```

E o focus ring (fora do `@theme`):

```css
*:focus-visible {
  outline: 3px solid var(--color-primary-light);
  outline-offset: 2px;
  border-radius: 4px; /* era 8px */
}
```

### Critérios de sucesso

- Cards, modais e botões com cantos visivelmente menos arredondados em todas as páginas.
- Avatares e status pills (badges) **mantêm** forma circular/pílula.
- Tooltips dos gráficos do dashboard acompanham a nova linguagem (cantos de 6px).
- Focus ring de teclado também menos arredondado.
- Nenhuma quebra de layout (overflow, alinhamento, sombra projetada).
- Build e lint do frontend continuam verdes.

### Verificação end-to-end

1. **Subir o app local** com a skill `/atualizar-app` (rebuild da stack docker-compose).
2. **Tour visual** abrindo `http://localhost:3000` e percorrendo:
   - `/` (home) — cards de KPI no dashboard, sidebar, header.
   - `/reunioes` (lista) e `/reunioes/[id]` (detalhe — arquivo com mais ocorrências).
   - `/reunioes/calendario` e `/reunioes/importar`.
   - `/pendencias`, `/pendencias/kanban`, abrir `PendenciaDetailModal` (testa scrollbar custom).
   - `/admin/usuarios`, `/admin/bulk` — abrir `AdminModal` derivados (`UsuarioFormModal`, `ReuniaoEditModal`, etc).
   - `/login` — inputs e botão CTA.
   - Disparar Toast (criar/editar algo) para validar `rounded-2xl` reduzido.
   - Hover/focus em inputs para validar focus ring.
3. **Comparar antes/depois** em pelo menos 3 superfícies-chave (card KPI, modal de edição, botão primário do upload de transcrição da imagem original).
4. **Build de produção**: `pnpm build` no frontend para garantir que nenhum token quebrou.
5. **Não regenerar** ATAs em PDF (template não foi tocado).

### Riscos e mitigações

- **Risco**: algum componente depende visualmente do tamanho default (ex.: composição de cantos com sombra/borda). **Mitigação**: tour visual cobre os 10 arquivos com mais ocorrências.
- **Risco**: Tailwind v4 muda nome do token internamente em alguma minor. **Mitigação**: package.json fixa `^4.0.0`; tokens `--radius-*` são parte da spec pública v4.
- **Risco**: usuário achar que ficou *agressivo demais* depois de ver no app real. **Mitigação**: como tudo está em 1 arquivo central, ajustar a escala (ex.: subir para 5/8/12) é mudança de 1 linha por token.

## Execução / Resultados

### 2026-04-27 — aplicação inicial

**Edições realizadas:**

1. `hospital-reunioes/frontend/src/app/globals.css`
   - Adicionados tokens `--radius-{xs,sm,md,lg,xl,2xl,3xl}` no bloco `@theme` existente, valores corporativos (1/2/3/4/6/8/12 px). `rounded-full` mantido em 9999px (não redefinido).
   - Focus ring (`*:focus-visible`) reduzido de `border-radius: 8px` → `4px`.
2. `hospital-reunioes/frontend/src/components/pendencias/PendenciaDetailModal.tsx:790` — scrollbar custom: `border-radius: 10px` → `5px`.
3. `hospital-reunioes/frontend/src/components/dashboard/StatusPieChart.tsx:95` — tooltip recharts: `borderRadius: "12px"` → `"6px"`.
4. `hospital-reunioes/frontend/src/components/dashboard/SetorBarChart.tsx:100` — tooltip recharts: `borderRadius: "12px"` → `"6px"`.

**Cobertura via `@theme`:** todas as 544 ocorrências de `rounded-{lg,xl,2xl,...}` agora consultam os novos tokens e renderizam ~50% menos arredondadas, sem necessidade de tocar em componente individual.

**Pendente — validação visual:**

- [ ] Subir o app local com `/atualizar-app` e percorrer o tour da seção "Verificação end-to-end" (home, reuniões, pendências, admin, login, modais, toasts).
- [ ] Comparar antes/depois nos 3 pontos-chave: card KPI, modal de edição, botão CTA do upload de transcrição.
- [ ] Rodar `pnpm build` no frontend para garantir nenhum token quebrou.
- [ ] Confirmar com o diretor se a intensidade ficou na medida ou se quer ajustar (basta mexer 1 token no `@theme`).
