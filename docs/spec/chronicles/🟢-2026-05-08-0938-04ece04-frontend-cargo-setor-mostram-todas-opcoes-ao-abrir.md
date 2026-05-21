# Deploy `04ece04` — 🟢 healthy

- **Data**: 2026-05-08 09:38 -0300
- **SHA**: `04ece04`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Combobox de cargo/setor agora mostra todas as opções ao abrir o dropdown.
- **Duração**: 140s

## Serviços tocados

- frontend

## Mudança

`AutocompleteInput` (componente compartilhado de combobox usado em Cargo e Setor):
- Antes filtrava sempre pelo `value` atual. Resultado: abrir dropdown com "Gerência" selecionado só listava opções contendo essa string.
- Agora introduz `isTyping`. Filtro só aplica quando `isTyping=true` (digitação ativa). Abrir dropdown (foco no input, clique no chevron, fechar e reabrir) reseta `isTyping=false` e mostra todas as opções. Selecionar uma opção também reseta.

`ResolverExternoModal` (resolver participante externo, tab Promote):
- Migrado de `<input list="..." />` + `<datalist>` HTML nativo pro `AutocompleteInput`. Cargo e Setor agora têm a mesma UX do `UsuarioFormModal` (Editar usuário).

## Health pós-deploy

- `app.hospitalsaomatheus.cloud`: HTTP 200, 99ms
- Coolify: `health.status = "healthy"`

## Pendência detectada

`mcp__coolify__diagnose_app` reporta `is_build_time=false` nas 4 NEXT_PUBLIC_* do frontend, mas `project.json` exige `true`. Build funcionou (Dockerfile passa via `ARG`), mas a flag deveria estar marcada no Coolify também. Não bloqueia.

---
_Gerado pelo `/deploy ship` (Passo 9.4)._
