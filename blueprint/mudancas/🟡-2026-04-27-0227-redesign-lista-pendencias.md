# Plano — Redesign da lista de Ações/Tarefas (Pendências)

## Plano

### Contexto

A lista atual em `hospital-reunioes/frontend/src/app/pendencias/page.tsx` mostra cada pendência numa linha de tabela com `descricao_acao` e `meta_entregavel` truncados via `line-clamp-2`. Isso esconde o conteúdo essencial — os dois textos que descrevem **o que precisa ser feito** (`descricao_acao`) e **qual é o entregável esperado** (`meta_entregavel`) — e força o usuário a abrir o modal pra ler em completude.

Pior: a linha não dá nenhum sinal visual de que há um modal por trás dela. O Kanban faz a coisa certa (card inteiro clicável → abre `PendenciaDetailModal` com chat de comentários). Na lista, o caminho pra esse mesmo modal não existe — e nem se sabe que ele existe.

O modal em si está completo e segue sendo reusado como está: `components/pendencias/PendenciaDetailModal.tsx` tem painel esquerdo (edição inline de todos os campos) e direito (chat de comentários com `@menções`).

**Nota sobre o vocabulário**: no schema do backend não existe distinção `Ação vs Tarefa` — tudo é uma única entidade `Pendencia` com `descricao_acao` (a ação) e `meta_entregavel` (o entregável/tarefa). O cabeçalho `AÇÃO / TAREFA` da coluna se refere ao par dos dois textos visíveis na célula.

### Objetivo

Permitir que cada pendência da lista seja lida em completude (descrição + entregável) sem sair da página, e ao mesmo tempo dar acesso direto, sinalizado, ao modal completo (onde está o chat).

### Abordagem — Linha expansível inline com atalho pro modal

A tabela continua compacta no estado padrão pra preservar o scan vertical (importante: usuários gerenciam dezenas de pendências). Mas:

- A **linha inteira é clicável** e alterna entre estado colapsado e expandido.
- Um **chevron** `▶ / ▼` na primeira coluna sinaliza o estado (visual apenas — não é um botão separado, o click vem da linha).
- No estado **expandido**, surge um mini-painel inline logo abaixo da linha, mostrando `descricao_acao` e `meta_entregavel` **em completude** (sem `line-clamp`), com tipografia mais respirada e o atalho explícito `↗ Abrir detalhes / chat`.
- Em todas as linhas (colapsadas e expandidas), no canto direito, fica:
  - Um **chip `💬 N`** discreto quando `total_comentarios > 0`. Não aparece quando zero.
  - Um **ícone `↗`** (external-link) que abre o `PendenciaDetailModal` direto, sem expandir a linha.
- **Múltiplas linhas podem ficar expandidas simultaneamente** (estado `Set<id_acao>`), permitindo comparar ações lado a lado.

Decisões de interação confirmadas com o usuário:
- Gatilho: linha inteira clicável (chevron é só visual).
- Sinal modal: ícone `↗` + chip `💬 N` quando há comentários.

### Arquivos a modificar

#### Backend

**1. `hospital-reunioes/backend/app/models/schemas.py`** (classe `PendenciaResponse`)
- Adicionar campo `total_comentarios: int = 0`.

**2. `hospital-reunioes/backend/app/routers/pendencias.py`** (handler `GET /pendencias`)
- Criar função `_enrich_comentarios_count(supabase, rows)` análoga ao `_enrich_externo_flag`: faz uma segunda query em `comentarios_pendencias` filtrando por `id_acao IN (…)`, conta no Python.
- Aplicar essa função após `_enrich_externo_flag` no handler `list_pendencias`.

#### Frontend — tipos e página

**3. `hospital-reunioes/frontend/src/types/index.ts`** (interface `Pendencia`)
- Adicionar `total_comentarios?: number`.

**4. `hospital-reunioes/frontend/src/app/pendencias/page.tsx`** — mudança principal
- Importar `PendenciaDetailModal`, `MessageSquare`, `ChevronRight`.
- Estado `expandedRows: Set<string>` e `selectedPendencia: Pendencia | null`.
- Função `toggleExpand(id)` que cria novo Set imutável.
- `useEffect` que reseta `expandedRows` quando filtros mudam.
- Reorganizar `<tbody>`: cada item vira um `<Fragment>` com dois `<tr>` (principal + painel expandido condicional, `colSpan={7}`).
- Linha principal:
  - Primeira coluna ganha chevron (16px) ao lado do título.
  - Nova última coluna `<td>` com chip `💬 N` (só se `total_comentarios > 0`) + ícone `↗`.
  - `role="button"`, `tabIndex={0}`, `aria-expanded`, `onClick`/`onKeyDown` (Enter/Space).
- Linha expandida: painel com labels "Ação" e "Entregável", textos completos, e botão `↗ Abrir detalhes / chat`.
- `e.stopPropagation()` em todos elementos interativos internos (link da reunião, chip, ícone modal, status dropdown).
- Render do `PendenciaDetailModal` quando `selectedPendencia` está setado.
- `handleStatusUpdated`/`handlePendenciaUpdated` pra reagir a edits no modal.

#### Reuso (sem alteração)
- `components/pendencias/PendenciaDetailModal.tsx`
- `components/pendencias/StatusBadge.tsx`
- Tokens em `globals.css`
- Lucide React

### Pontos de atenção
- **Acessibilidade**: `aria-expanded`, foco visível, suporte teclado, `aria-label` nos ícones.
- **Mobile**: tabela já tem `overflow-x-auto`. Painel expandido precisa caber.
- **Performance**: enrichment de comentários faz +1 query Supabase. Aceitável até ~500 pendências; se ficar lento, criar VIEW SQL.
- **Não-regressão Kanban**: `PendenciaDetailModal` continua funcionando como antes.
- **Filtros**: ao mudar filtros, resetar `expandedRows` (IDs podem sumir).

### Verificação (end-to-end)

1. **Backend**: `uv run pytest tests/`; chamar `GET /pendencias` e confirmar `total_comentarios` em cada item.
2. **Frontend**: `/atualizar-app`; testar expansão (click linha), atalho modal (click ícone `↗`), chip de comentários, navegação por teclado, mobile.
3. **Não-regressão Kanban**: abrir card no Kanban, modal funciona como antes.

## Execução / Resultados

### O que foi feito (2026-04-27, 0227h–0250h)

**Backend**
- `hospital-reunioes/backend/app/models/schemas.py`: campo `total_comentarios: int = 0` adicionado em `PendenciaResponse`.
- `hospital-reunioes/backend/app/routers/pendencias.py`: nova função `_enrich_comentarios_count` (análoga a `_enrich_externo_flag`) faz uma segunda query batch em `comentarios_pendencias` agrupando por `id_acao`, e é aplicada no handler `list_pendencias` (`GET /pendencias`).

**Frontend tipos**
- `hospital-reunioes/frontend/src/types/index.ts`: campo opcional `total_comentarios?: number` adicionado em `Pendencia`.

**Frontend lista de pendências (`hospital-reunioes/frontend/src/app/pendencias/page.tsx`)**
- Imports ampliados: `Fragment`, `ChevronRight`, `MessageSquare`, `PendenciaDetailModal`.
- Estado `expandedRows: Set<string>` controla quais linhas estão expandidas; `selectedPendencia: Pendencia | null` controla o modal.
- `useEffect` reseta `expandedRows` quando os filtros mudam (IDs visíveis podem sumir).
- Tabela: thead ganhou 7ª coluna (cabeçalho `sr-only` "Ações"). tbody agora renderiza `<Fragment>` com duas `<tr>` por pendência:
  - Linha principal: `role="button"`, `aria-expanded`, `tabIndex={0}`, `onKeyDown` Enter/Space, click toggle. Chevron ▶/▼ no início da coluna "Ação / Tarefa". Última coluna mostra chip `MessageSquare + N` quando `total_comentarios > 0` e ícone `ExternalLink` que abre o modal.
  - Linha expandida (condicional): `colSpan={7}`, painel branco com labels "Ação" e "Entregável esperado" mostrando texto completo (sem `line-clamp`), e botão `↗ Abrir detalhes / chat`.
- `e.stopPropagation()` aplicado nas células sensíveis (link da reunião MIG_xxx, dropdown de status, célula de ações) pra que clicks nesses elementos não expandam a linha acidentalmente.
- Modal `PendenciaDetailModal` renderizado condicionalmente quando `selectedPendencia` está setado, com callbacks `handleStatusUpdated`, `handlePendenciaUpdated`, `handlePendenciaDeleted` cuidando de propagar mudanças de volta pra lista (preservando `total_comentarios` no merge — backend não enriquece o PATCH).

**Plan & docs**
- Plan inicial em `/Users/pedrorezende/.claude/plans/image-1-sinto-que-swift-babbage.md`.
- Plano canônico em `planos/plano-26-04-27-0227h-redesign-lista-pendencias.md` (este arquivo) seguindo a convenção do projeto.

### Verificação automatizada
- Typecheck (`npx tsc --noEmit`): sem erros.
- Lint (`next lint`): apenas 2 warnings pré-existentes em `page.tsx` (linhas 239 e 273, missing/unnecessary deps no `useEffect`/`useCallback`), não introduzidos por esta mudança.
- Build de produção do Next dentro do Docker: passou em 27.9s, todas as 25 páginas geradas.
- Stack local subiu via `/atualizar-app`: frontend respondeu 200 em 1s, backend `/api/health` em 4s.

### Pendente de validação humana (golden path no navegador, http://localhost:3000/pendencias)
- [ ] Estado colapsado: chevron `▶` à esquerda do título, descrição com `line-clamp-2`, entregável com `line-clamp-1`, status à direita, ícone `↗` no canto, chip `💬 N` aparece quando há comentários e some quando não há.
- [ ] Click em qualquer área neutra da linha alterna expansão (chevron vira `▼`); painel mostra descrição e entregável completos com tipografia respirada e rodapé com contador + botão "Abrir detalhes / chat".
- [ ] Click no ícone `↗` (canto direito) abre o `PendenciaDetailModal` direto, sem expandir a linha.
- [ ] Click no link `MIG_xxx` da coluna Reunião segue funcionando e não dispara expansão.
- [ ] Click no dropdown de status segue funcionando e não dispara expansão.
- [ ] Múltiplas linhas podem ficar expandidas ao mesmo tempo.
- [ ] Mudar filtros reseta as expansões.
- [ ] Tab navega entre linhas com foco visível; Enter/Space alterna expansão.
- [ ] Mobile (resize <768px): painel expandido cabe e o grid `md:grid-cols-2` colapsa para uma coluna.
- [ ] Não-regressão Kanban: card abre o mesmo modal como antes.

### Pontos discutidos mas não implementados (follow-ups)
- Enriquecer `PATCH /pendencias/{id}` e `GET /pendencias/{id}` com `total_comentarios` (hoje só `GET /pendencias` enriquece). Por isso o frontend preserva o valor anterior no merge de update — sem essa preservação, o chip sumiria após qualquer edit.
- Atualização incremental do contador quando um comentário é criado/excluído dentro do modal (hoje só atualiza após refetch da lista).
- Possível VIEW SQL `pendencias_with_comentarios_count` se a segunda query do enrichment ficar lenta em volumes grandes.

### Iteração 2 — feedback do Pedro (0250h–0310h)

Pedro rejeitou a abordagem com chevron + linha expansível inline. Razões: queria mais prático (estilo mouseover), sem setas/chevrons, e com a meta_entregavel destacada por cor própria. Pediu que o redesign seguisse o mesmo padrão do calendário (`app/reunioes/calendario/page.tsx` linhas 639-768), e que eu usasse a skill `/frontend-design:frontend-design`.

**Refatoração aplicada em `pendencias/page.tsx`:**
- Removido: `expandedRows: Set<string>`, `toggleExpand`, `useEffect` de reset, chevrons (`ChevronRight`/`ChevronDown` do início da linha), expansão inline via `<Fragment>` com `colSpan={7}`.
- Novo componente interno `PendenciaRow` encapsula uma `<tr>` com seu próprio estado de hover (`showTooltip`, `tooltipPos`).
- Tooltip via `createPortal` em `document.body` (`position: fixed`, z-index 60), com cálculo dinâmico de `getBoundingClientRect()` pra abrir abaixo da linha por padrão e flipar pra cima quando perto da borda inferior; alinhamento à direita quando perto da borda direita. Isso resolve clipping causado pelo `overflow-x-auto` da tabela.
- Delay de 120ms no fechamento (cleanup com `setTimeout`/`clearTimeout`) pra dar tempo do mouse atravessar entre linha e tooltip sem piscar — `onMouseEnter` no tooltip cancela o close.
- Acessibilidade: `tabIndex={0}` na `<tr>` e `onFocus`/`onBlur` espelhando o hover (Tab abre o tooltip também), `role="tooltip"` no painel.
- Inline na tabela: `meta_entregavel` agora é renderizada em **`text-emerald-700`** (sem o `→`), apenas cor + tipografia distinguem da `descricao_acao` (slate-800, font-medium). Sem chevrons/indicadores gráficos.
- Conteúdo do tooltip (espelhando o do calendário em estrutura, adaptado pro contexto de pendência):
  - Header: `id_acao` em chip mono cinza + `StatusBadge` à direita.
  - Bloco "Ação · Tarefa": label uppercase pequeno (slate-400) + texto completo em slate-900 semibold.
  - Bloco "Meta · Entregável": ícone `Target`, label uppercase em emerald-700, texto em emerald-900/90, fundo `bg-emerald-50/50` com borda esquerda `border-l-[3px] border-emerald-400`. Quando ausente, placeholder dashed em slate-400 italic "Não definido".
  - Meta-info: ícones (`User`, `Setor` chip "S", `CalendarDays`, `MessageSquare`) com responsável + cargo, setor, prazo formatado, contagem de comentários.
  - Footer: botão `Abrir detalhes / chat` em `bg-primary text-white` que abre o `PendenciaDetailModal`.
- Coluna de ações (chip 💬N + ícone ↗) mantida do design anterior.

**Bug pré-existente desbloqueado durante o build**: o commit `49553ab chore(frontend): adiciona zustand para gestao de estado da Ana` adicionou `zustand@^5.0.12` no `package.json` mas não regenerou o `pnpm-lock.yaml`, fazendo o build do Docker quebrar com `ERR_PNPM_OUTDATED_LOCKFILE`. Regeneraei o lockfile via `npx pnpm@latest install --lockfile-only` (1.4s, sem alterar `node_modules` no host). O diff em `pnpm-lock.yaml` é independente do redesign — vale commitar separado pra preservar atribuição.

### Verificação automatizada (iteração 2)
- `tsc --noEmit`: sem erros.
- `next lint`: apenas os 2 warnings pré-existentes em `page.tsx` (linhas 478 e 512), agora deslocadas pelas linhas novas, mesma natureza.
- Build de produção do Next dentro do Docker: passou.
- Stack local subiu em 54s, frontend respondendo 200.

### Pendente de validação humana (iteração 2, http://localhost:3000/pendencias)
- [ ] Cada linha mostra título da ação (preto) e logo abaixo a meta entregável em verde discreto (sem `→`, sem chevron).
- [ ] Passar mouse sobre a linha → após hover, tooltip flutuante aparece próximo da linha com header + bloco Ação + bloco Meta verde + meta-info + botão "Abrir detalhes / chat". Pattern equivale visualmente ao tooltip do calendário.
- [ ] Tooltip flipa pra cima quando linha está perto do fim da viewport.
- [ ] Mover mouse da linha pro tooltip não fecha (delay de 120ms permite atravessar).
- [ ] Tab navega pelas linhas; Enter no tooltip não tem ação obrigatória, mas o foco visual fica acessível.
- [ ] Click no ícone `↗` da última coluna abre o `PendenciaDetailModal` direto.
- [ ] Click no botão "Abrir detalhes / chat" do tooltip também abre o modal e fecha o tooltip.
- [ ] Click no link `MIG_xxx` ou no dropdown de status funciona normal sem efeitos colaterais.
- [ ] Não-regressão Kanban: card abre o mesmo modal como antes.
