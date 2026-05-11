# Deploy `c64f290` — 🟢 healthy

**Limpeza de código morto (frontend + backend) e arquivos órfãos da raiz**

- **Data**: 2026-05-11 15:22 -03:00
- **SHA**: `c64f290`
- **Modo**: ship
- **Resultado**: healthy
- **Subject**: Limpeza de código morto (frontend + backend) e arquivos órfãos da raiz
- **Commit raw**: `chore(cleanup): remove código morto, unused imports e arquivos órfãos da raiz`

## Serviços tocados

- backend
- frontend

## Mudanças no código

Série de 5 commits granulares aplicados juntos no mesmo deploy:

1. `ffbe32d` — `chore(frontend): remove componentes duplicados em src/components/reunioes/`
   - Deletados 6 arquivos (578 linhas): `StatusTimeline.tsx`, `InlineEditField.tsx`, `RecorrenciaPanel.tsx`, `PreparacaoChecklist.tsx`, `SectionCard.tsx`, `DesmarcarModal.tsx`. Versões inline em `app/reunioes/[id]/page.tsx` permanecem.
2. `64fe616` — `chore(frontend): remove imports e variaveis nao usados`
   - Limpa 10 warnings de unused-vars em 8 arquivos (`useRef`, `updatingId`, `ConfirmDialog`, `DIAS_SEMANA_FULL`, `year`, `totalCols`, `Check`, `currentUserId`, `nomeResponsavel`, `jsonAta` + interface `JsonAta`). Ajusta call site do `ChatCorrecao` para não passar mais `jsonAta`.
3. `706d92c` — `chore(backend): remove is_super_user deprecated e schema RegistrarParticipanteRequest`
   - Remove função deprecated nunca chamada e classe Pydantic nunca instanciada. Limpa import de `warnings`.
4. `8776307` — `chore(backend): remove testes manuais legados da raiz`
   - Deleta `test_calendario.py`, `test_recorrencia.py`, `test_supabase.py` (smoke manuais fora de `tests/`).
5. `c64f290` — `chore(backend): remove keys SIGNUP_* obsoletas do .env.example`
   - Tira `SIGNUP_PASSE` e `SIGNUP_ENCRYPTION_KEY` do exemplo (foram removidas do `Settings` quando o fluxo signup_requests saiu na migration 031).

## Reorganização da raiz do projeto (não versionada)

Também foram removidos da raiz local (não estavam no repo, eram gitignored ou untracked):

- `restore-1-auth-prod.sql`, `restore-2-public-prod.sql`, `migrations-bundle-prod-inicial.sql` (dumps históricos já aplicados em prod).
- `HPSimplified_Rg.ttf`, `LOGO HSM.png` (duplicatas idênticas das versões em `backend/app/static/fonts/` e `frontend/public/`).
- `transcricao-teste-clicksign.txt`, `proposta.pdf` (mocks e saída regerável).

## Verificações

- `next lint`: 13 warnings de unused-vars → 3 (todos prefixados com `_` por convenção intencional).
- `npm run build`: ✅ 21 rotas geradas.
- `ruff check`: ✅ all checks passed.
- `pytest`: ✅ 177 passed.
- `/atualizar-app` local: ✅ stack subiu em 43s, build em 38s.
- Health prod backend: `200` em 1530ms, body `{"status":"healthy",...}`.
- Health prod frontend: `200` em 1621ms.

## Pendência pós-deploy

- Cadastros `SIGNUP_ENCRYPTION_KEY` e `SIGNUP_PASSE` no Coolify do backend seguem existindo, mesmo que a aplicação não use mais. Vale deletar pelo painel para reduzir superfície de secrets e tirar do `project.json` (`runtime_required` + `secrets_auto_generated`).

---
_Gerado automaticamente pelo `/deploy ship` (Passo 9.4)._
