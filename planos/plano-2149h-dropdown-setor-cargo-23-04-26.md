# Plano — Dropdown de Setor/Cargo no modal "Editar usuário"

## Plano

### Contexto

No modal **Editar usuário** (`UsuarioFormModal`), os campos **Setor** e **Cargo** usavam `<input list="…">` + `<datalist>` HTML nativo para sugerir valores da taxonomia (tabelas `setores`/`cargos`, migration 028). O browser renderizava esse dropdown com tema próprio do SO/navegador — no screenshot:

- Dropdown aparecia **fora do modal**, ancorado na lateral direita da tela (longe da barra do input)
- **Fundo preto/escuro**, ignorando o design claro (`bg-white`, `slate-*`) do restante da UI

Como `<datalist>` fica fora do DOM controlado pelo React, **nenhum CSS do projeto alcança esse popup**. A solução foi substituir por um combobox React com dropdown renderizado e estilizado pela aplicação — mesmo padrão já usado em `MultiSelectFilter`, `ParticipanteCombobox` e `ui/MultiSelect`.

**Escopo:** apenas o `UsuarioFormModal` (campos Setor e Cargo — resolver um só deixaria o outro inconsistente visualmente). O `ResolverExternoModal.tsx` tem o mesmo padrão (linhas 451-470) e pode adotar o mesmo componente em seguida — fica fora desta iteração.

### Abordagem

Criar um componente reutilizável `AutocompleteInput` em `components/ui/` (irmão de `MultiSelect.tsx`) e substituir os dois `<datalist>` por ele no `UsuarioFormModal`. Componente é **single-select, aceita texto livre** (preserva valores legacy), filtra opções conforme digita, e usa o mesmo vocabulário visual do `MultiSelectFilter` (fundo branco, borda slate-200, shadow-lg, `z-20`, `mt-1`).

### Passos

1. Criar `hospital-reunioes/frontend/src/components/ui/AutocompleteInput.tsx`.
2. Editar `hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx`: importar o novo componente e substituir os `<input>` + `<datalist>` dos campos Cargo e Setor.
3. Rodar `npx tsc --noEmit` e `npx eslint` para validar.
4. Verificar UI local via `/atualizar-app` e smoke-test manual do modal.

### Critérios de sucesso

- Dropdown abre imediatamente abaixo do input (`mt-1`), largura igual ao input.
- Fundo branco, borda slate-200, shadow-lg.
- Filtra opções conforme o usuário digita.
- Aceita valor livre (não-listado) — preserva legacy.
- Navegação por teclado (`ArrowUp`/`Down`/`Enter`/`Escape`).
- Submit continua salvando setor/cargo no backend (lookup silencioso da migration 028).
- `tsc --noEmit` e `eslint` passam limpos.

### Riscos

- **Foco em modal com portal:** o `AdminModal` usa `createPortal`. O dropdown via `absolute` dentro do input já funciona em outros modais (`ParticipanteCombobox` usado em `/reunioes/[id]`). Baixo risco.
- **Valor livre:** comportamento legacy preservado — `onChange` sempre recebe string, seja digitada ou clicada.

## Execução / Resultados

Executado em 23/04/2026 21:49.

### O que foi feito

1. **Criado** `hospital-reunioes/frontend/src/components/ui/AutocompleteInput.tsx`:
   - Single-select com texto livre, filtro case-insensitive via `includes`
   - Dropdown `absolute z-20 mt-1 w-full max-h-60 overflow-y-auto bg-white border border-slate-200 rounded-lg shadow-lg`
   - Clique fora (listener `mousedown` condicional a `open`) e `Escape` fecham
   - Navegação por teclado: `ArrowDown`/`ArrowUp`/`Enter`/`Escape`
   - ChevronDown clicável à direita (rotaciona 180° quando aberto)
   - `aria-expanded`/`aria-controls`/`role="combobox"`/`role="listbox"`/`role="option"` presentes
   - Se `options` vazio, degrada para `<input>` simples (sem dropdown)

2. **Editado** `hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx`:
   - Import do `AutocompleteInput`
   - Campo Cargo: `<input>` + `<datalist>` → `<AutocompleteInput>` (com `required`)
   - Campo Setor: idem (sem `required`)
   - Comentário do prop `setoresDisponiveis/cargosDisponiveis` atualizado (sai "datalist", entra "combobox custom")

### Validação

- `npx tsc --noEmit` — **sem erros**
- `npx eslint src/components/ui/AutocompleteInput.tsx src/components/admin/UsuarioFormModal.tsx` — **sem warnings/errors**

### Itens pendentes / follow-ups

- Smoke-test visual no localhost via `/atualizar-app` (não executado automaticamente — fica pro usuário validar na UI quando rodar).
- `ResolverExternoModal.tsx` (linhas 451-470) tem os mesmos `<datalist>` para cargo/setor — pode migrar para `AutocompleteInput` em iteração futura.

### Arquivos tocados

- **Criado:** `hospital-reunioes/frontend/src/components/ui/AutocompleteInput.tsx`
- **Editado:** `hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx`
