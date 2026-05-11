# Deploy `c5abfde` — 🟢 healthy

- **Data**: 2026-05-08 16:22 -03:00
- **SHA**: `c5abfde`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Sidebar com Calendário top-level e Importar ATA embaixo do Admin.

## Serviços tocados

- frontend

## Mudança

Removido o submenu expansível "Reuniões" do `Sidebar.tsx`. Agora:

- **Calendário** vira link direto no nível principal do menu lateral (no lugar onde antes ficava o item "Reuniões" expansível).
- **Importar ATA** aparece embaixo do **Admin** (continua restrito a super-admin).
- Estrutura final: Dashboard → Calendário → Pendências (Lista/Kanban) → Admin → Importar ATA.

`BottomNav` (mobile) intocado. Type check passou sem erros, build de produção limpo (only legacy ESLint warnings).

## Health pós-deploy

- Frontend: HTTP 200 em 149ms (`https://app.hospitalsaomatheus.cloud`)
- Backend: HTTP 200 em 82ms (`https://api.hospitalsaomatheus.cloud/api/health`)
- Supabase Studio: intocado.

Build do frontend levou 142s. Backend e Supabase não foram afetados pelo diff.

## Notas

Rebuild local (`/atualizar-app`) feito antes do ship pra validar visualmente. Apenas o `Sidebar.tsx` entrou no commit — outros arquivos modificados/untracked do working tree (proposta PJ, planos novos, fonte HP Simplified, logo HSM, transcrição teste ClickSign) ficam para deploys posteriores quando estiverem prontos.

---
_Gerado pelo `/deploy ship` (Passo 9.4)._
