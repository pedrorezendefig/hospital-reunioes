---
title: "feat(reunioes,secretaria): dropdown responsável + visão global da secretária com gate em ata/pendência"
author: Pedro Rezende <pmrdef@gmail.com>
type: feature
issue: null
pr: 10
date_planned: 2026-05-22T14:28:00-03:00
date_deployed: 2026-05-22T16:28:03-03:00
sha: 805daa0
branch: feat/dropdown-responsavel-correcao-ata
result: healthy
status: done
last_touched: 2026-05-22T16:28:03-03:00
plan_source: plan-mode
duration_deploy_s: 223
services_touched:
  - backend
  - frontend
migrations_applied: 0
app_version: "0.3.0"
---

## Contexto

Hoje, quando o usuário corrige o **responsável** de uma atribuição/pendência via "Solicitar Correção" na tela de ATA (`/reunioes/[id]`), o cargo exibido em cinza embaixo do nome **não acompanha** a troca. Exemplo real (que motivou esta mudança): trocou-se o nome para "Josiane Alves" mas o cargo continuou "Coordenadora Operacional" — a Josiane real é "Diretora".

Raiz:
- `pendencias.cargo` e `json_ata.quadro_atribuicoes[].cargo` são **texto livre** (`TEXT`), sem FK que os derive do responsável.
- A correção atual é via chat livre → IA reescreve `json_ata`. A IA não atualiza `cargo` ao mudar `responsavel`.
- `reuniao.participantes_programada` já carrega `id + nome + cargo + email + area` — fonte canônica de quem pode ser responsável já está no objeto, mas não é usada nesse momento.

Objetivo: substituir a edição implícita por chat por um **combobox inline de participantes da reunião** na coluna RESPONSÁVEL, que troque nome **e** cargo simultaneamente. Em paralelo, fechar a raiz no backend para que, em qualquer caminho de edição (chat, dropdown, force, criação inicial), o cargo seja sempre derivado do participante quando houver vínculo.

## Plano

**Tarefa atual:** verificação manual em `localhost:3000` (pendente).

- [x] 1. Schema `QuadroAtribuicaoUpdate` em `backend/app/models/schemas.py`
- [x] 2. Endpoint `PATCH /reunioes/{id_reuniao}/quadro-atribuicoes/{index}` em `backend/app/routers/reunioes.py`
- [x] 3. Refatorar `_find_participante_id` → `_find_participante` em `backend/app/services/pendencia_service.py` (retorna `{id, cargo}` e `liberar_pendencias` popula `pendencias.cargo` canônico)
- [x] 4. Derivar cargo no PATCH `/pendencias/{id_acao}` e `/force` em `backend/app/routers/pendencias.py` (respeita override explícito)
- [x] 5. Helper `_canonicalize_cargos_quadro` em `app/pipeline/orchestrator.py` chamado em `run_correction_pipeline` pós-IA
- [x] 6. Componente `ResponsavelInlineCombobox` em `frontend/src/components/reunioes/ResponsavelInlineCombobox.tsx`
- [x] 7. Integrar combobox na coluna RESPONSÁVEL da tabela de atribuições em `frontend/src/app/reunioes/[id]/page.tsx` + handler `handleAtribuicaoResponsavelAtualizado` (otimista + reload)
- [x] ~~8. Método HTTP separado~~ — descartado, projeto usa `fetch("/api/...")` direto. Chamada feita no próprio componente.
- [ ] 9. Verificação local — gates automáticos ✅ (ruff, ruff format, pytest 177/177, next lint, tsc, next build). Verificação visual no navegador pendente, depende do usuário rodar `/atualizar-app`.

## Execução / Resultados

### Mudanças além do plano

- **`GET /reunioes/{id_reuniao}` agora enriquece `participantes_programada` em qualquer status**, não só em `PROGRAMADA`. Era necessário pra alimentar o dropdown do combobox em ATA `AGUARDANDO_VALIDACAO`. Payload extra é pequeno (lista de até ~30 participantes com 5 campos cada).
- **Item editado manualmente é marcado** com `editado_manualmente: true` no `quadro_atribuicoes[index]`. Hoje serve só como auditoria — futuramente pode evitar sobrescrita por IA.
- **`pendencias.cargo` agora é populado em `liberar_pendencias`**: era uma omissão antiga (a inserção em lote nem mencionava `cargo`, deixando NULL). Agora vem do participante quando o nome resolve, ou do texto LLM quando não.

### Gates automáticos

| Gate | Comando | Resultado |
|---|---|---|
| Backend ruff lint | `uv run --extra dev ruff check .` | All checks passed |
| Backend ruff format | `uv run --extra dev ruff format --check .` | 74 files already formatted |
| Backend testes | `uv run --extra dev pytest` | 177 passed, 0 failed |
| Frontend lint | `npm run lint` | Só warnings pré-existentes (nada do código novo) |
| Frontend tsc | `npx tsc --noEmit` | exit 0, sem erros |
| Frontend build | `npm run build` | ✓ Compiled successfully, 23/23 páginas geradas |

### Cenários a testar manualmente

1. **Bug original (Josiane)** — ATA em `AGUARDANDO_VALIDACAO`, clicar "Solicitar Correção", clicar na célula RESPONSÁVEL de uma linha, escolher participante no dropdown. Esperado: nome **e** cargo trocam juntos, instantâneo.
2. **Fallback texto livre** — última opção "Digitar livremente", preencher nome + cargo, clicar Aplicar. Esperado: salva como texto.
3. **Keyboard nav** — abrir dropdown, ↑↓ navega, Enter seleciona, Esc fecha.
4. **Click fora** — abrir dropdown, clicar fora. Esperado: fecha.
5. **Reset chat** — chat de correção continua funcional (não foi mexido). Outras células da linha continuam roteando `sectionContext` pro chat.
6. **Regressão correção via chat** — pedir pro chat trocar responsável de uma linha. Esperado: cargo é canonicalizado pós-IA, fica correto mesmo via chat.

### Próximos passos

- Usuário roda `/atualizar-app` e testa cenários acima.
- Se OK, abrir PR via `/ship` (squash merge faz parte do fluxo do projeto).

---

## Escopo adicional — Expansão do papel "secretária" (mesclado nesta branch)

### Contexto

Antes desta mudança, secretária só enxergava reuniões com `status_ata == PROGRAMADA` E `data >= hoje`. O efeito colateral era: ata/pendência/comentário invisíveis porque "se ela não vê a reunião, não vê o conteúdo". Pedro pediu que ela passe a ter **visão de calendário do hospital inteiro** (todas as reuniões, qualquer status, qualquer data) + **gerenciar participantes** em reuniões PROGRAMADAS, mas continue **sem acesso a atas, pendências, comentários e quadro de atribuições**.

Como o filtro de visibilidade de reunião deixa de ser o gate, foi necessário **gate explícito 403** nos endpoints de ata/pendência/comentário (defense-in-depth) + **gating de UI** no detalhe da reunião pra esconder seções correspondentes. Ordem importa: gates 403 ANTES de afrouxar `get_allowed_reuniao_ids` (caso contrário, secretária passaria a ver todas as pendências do hospital — regressão grave).

### Decisões (brainstorming)

1. Secretária vê **todas** as reuniões, qualquer status, qualquer data.
2. Acessa via calendário público existente (`/reunioes/calendario`, sem rota nova).
3. Detalhe abre `/reunioes/[id]` com ata e pendências escondidas, sem componente novo.
4. Add/remove participantes só em PROGRAMADAS. Em PROCESSANDO/VALIDANDO/ASSINADA, read-only.
5. Em PROGRAMADAS alheias, pode editar tudo (dados básicos + participantes + cancelar).
6. Listagem de usuários só no autocomplete (`/api/participantes`, já existia).
7. Gate técnico = `if is_secretaria(me): raise HTTPException(403)` explícito em cada endpoint.

### Mudanças aplicadas

- **`app/dependencies.py:154-172`** — `get_allowed_reuniao_ids` retorna `None` (sem filtro) pra secretária, igual super_admin. Docstring atualizado.
- **`app/routers/reunioes.py`** — 12 gates 403 nos endpoints de ata (anexar-transcricao, upload-transcricao, resolver-participantes, pular-resolucao, reprocessar, aprovar, aprovar-bypass, aprovar-bypass-todas, corrigir, chat-correcao, patch-quadro-atribuicoes, simular-assinatura). Limpou docstring obsoleto do `PATCH /reunioes/{id}` (gate `criada_por` já tinha sido removido em migration anterior). Renomeou `_:` → `current_user:` em 9 endpoints pra usar no fetch do participante.
- **`app/routers/pendencias.py`** — 5 gates 403 em `/stats`, `/minhas`, `GET /`, `GET /{id}`, `PATCH /{id}`. Import de `is_secretaria` adicionado.
- **`app/routers/comentarios.py`** — 3 gates 403 em GET/POST/DELETE de comentários. Reaproveitou fetch de `me` que já existia. Import de `is_secretaria`.
- **`tests/test_resolver_participantes.py`** — 10 chamadas atualizadas pra usar `current_user=...` em vez de `_=None` (regressão detectada e corrigida).
- **`frontend/src/app/reunioes/[id]/page.tsx`** — Import `isSecretaria`, flag `hideAtaSections`, condicional `!hideAtaSections` em 7 pontos do bloco STANDARD FLOW (botão PDF preliminar, banners de assinatura/ATA assinada, bloco Resolução, bloco Ações de Validação, ChatCorrecao, bloco Erro), filtro do card "Ações" no meta info, e wrap único cobrindo 8 sections de conteúdo da ata (Resumo Executivo, Participantes da ata, Pauta da Reunião HSM, Discussão dos Pontos, Registro Narrativo, Quadro de Atribuições, Pontos para Esclarecimento, Próxima Reunião). Bloco PROGRAMADA (linhas 1129-1496) intacto.

### Gates automáticos

| Gate | Comando | Resultado |
|---|---|---|
| Backend ruff lint | `.venv/bin/ruff check ...` | All checks passed |
| Backend ruff format | `.venv/bin/ruff format --check ...` | 5 files already formatted |
| Backend testes | `.venv/bin/pytest` | 177 passed, 0 failed |
| Frontend tsc | `node_modules/.bin/tsc --noEmit` | exit 0 |
| Frontend lint | `next lint` | Sem warnings novos (4 warnings pré-existentes intocados) |

### Cenários a testar manualmente (Pedro)

1. **Visão global** — login como secretária → `/reunioes/calendario` mostra reuniões em todos os status (ASSINADA, PROCESSANDO, CANCELADA, passadas).
2. **Detalhe ASSINADA** — clica em reunião assinada → vê só dados básicos + participantes; **nenhuma seção de ata renderizada**.
3. **Detalhe PROGRAMADA alheia** — clica em PROGRAMADA criada por outra pessoa → bloco completo, adiciona participante, remove, edita data/hora/facilitador, cancela.
4. **Endpoint 403** — `curl` em `/api/pendencias` com token de secretária → 403.
5. **Regressão admin** — login como admin, detalhe de reunião ASSINADA renderiza todas as seções de ata.
6. **Regressão regular** — login como regular, ata visível nas reuniões dele.

### Decisão de processo

Pedro autorizou misturar este escopo com o do dropdown-responsável na mesma branch + PR. Squash merge fará 1 commit com os dois escopos no histórico.

### Iteração após review (3 camadas)

**Camada 2 (security) — 🔴 critical:** `GET /reunioes/{id}` retornava `json_ata` cru pra secretária via curl direto (frontend só esconde UI; backend continuava servindo o conteúdo da ata).
- **Fix:** helper `_redact_ata_fields(row)` em `routers/reunioes.py` zera `json_ata`, `participantes_nao_reconhecidos`, `url_pdf_preliminar`, `url_pdf_assinado` quando `is_secretaria(me)`. Aplicado tanto em `get_reuniao` quanto em `list_reunioes` (defesa adicional, mesmo o response_model do list já filtrando `json_ata`).

**Camada 3 (superpowers) — 🛑 must-fix:** `PATCH /reunioes/{id}/quadro-atribuicoes/{index}` (endpoint novo) não checava visibilidade da reunião — qualquer autenticado podia editar quadro de qualquer reunião conhecendo só o id.
- **Fix:** adicionado check `if allowed_ids is not None and id_reuniao not in allowed_ids: raise 404` antes da query.

**Camada 3 (superpowers) — 🛑 must-fix:** Gates 403 sem cobertura de teste.
- **Fix:** novo arquivo `tests/test_secretaria_gates.py` com 9 testes cobrindo:
  - 3 routers (reunioes + pendencias + comentarios) com endpoints representativos sem `@limiter` (`aprovar-bypass`, `pular-resolucao`, `patch-quadro-atribuicoes`, `list/get/stats pendências`, `list/create comentários`).
  - Edge case `me=None` (token órfão pós-delete) — confirma que `is_secretaria(None) = False`.

**Camada 1 (code-review) — 🛑 must-fix:** Botão "Desmarcar" no header do STANDARD FLOW visível pra secretária (backend recusa 400 em status não-cancelável, mas UI confundia).
- **Fix:** wrap em `!hideAtaSections` em `page.tsx`.

**Camada 1 (code-review) — ⚠️ should-fix:** Bloco "Anexar Transcrição" no PROGRAMADA visível pra secretária (backend gateado 403, mas UI clicável).
- **Fix:** wrap em `!hideAtaSections` em `page.tsx`.

**Camada 3 (superpowers) — ⚠️ should-fix:** Docstring stale em `list_reunioes_calendario`.
- **Fix:** atualizado descrevendo novo comportamento (super_admin e secretária veem tudo).

### Gates após fixes

| Gate | Resultado |
|---|---|
| Backend ruff check | All checks passed |
| Backend ruff format | All files formatted |
| Backend pytest | **186 passed** (177 + 9 novos) |
| Frontend tsc | exit 0 |
| Camada 1 (code-review) | ✅ aprovado |
| Camada 2 (security-review) | ✅ critical resolvido |
| Camada 3 (superpowers review) | ✅ must-fix resolvidos |
| Camada 4 (CI Actions) | ✅ verde (3/3 jobs) |
| Camada 5 (verification-before-completion) | ✅ pytest+ruff+tsc rodados, output literal lido |

---

## Implementação / Deploy

**Deploy 805daa0 — 2026-05-22 16:28 — 🟢 healthy**

- **SHA**: `805daa0` (squash do PR #10)
- **Versão**: v0.2.1 → v0.3.0 (feat = minor bump automático pelo `/ship` Passo 5.5)
- **Duração**: 223s total (backend 2m42s + frontend 3m43s)
- **Modo**: ship via `/ship` → `/deploy ship`

### Serviços tocados

- backend (api.hospitalsaomatheus.cloud) — v0.3.0, health 200, body `status:healthy, db:healthy`
- frontend (app.hospitalsaomatheus.cloud) — 200, build 3m43s
- supabase — intocado

### Mudanças de variáveis

- backend: `APP_VERSION` atualizado pra `0.3.0` no Coolify (Passo 8.5 pré-merge da `/ship`)

### Iteração de gates de review

3 reviewers independentes rodaram em paralelo. Achados consolidados e corrigidos antes do merge:

| Camada | Achado | Status |
|---|---|---|
| 2 (security) | 🔴 critical: `GET /reunioes/{id}` vazava `json_ata` pra secretária via curl | ✅ helper `_redact_ata_fields` |
| 3 (superpowers) | 🛑 must: `PATCH /quadro-atribuicoes/{index}` sem checagem de visibilidade | ✅ check `allowed_ids` |
| 3 (superpowers) | 🛑 must: 20 gates 403 sem teste | ✅ `tests/test_secretaria_gates.py` 9/9 |
| 1 (code-review) | 🛑 must: botão "Desmarcar" no STANDARD FLOW visível pra secretária | ✅ gate UI |
| 1 (code-review) | ⚠ should: botão "Anexar Transcrição" no PROGRAMADA visível pra secretária | ✅ gate UI |
| 3 (superpowers) | ⚠ should: docstring stale em `list_reunioes_calendario` | ✅ atualizado |

### Pontos a verificar manualmente em prod

1. Login como secretária → `/reunioes/calendario` mostra reuniões em todos os status (ASSINADA, PROCESSANDO, CANCELADA, passadas).
2. Clica em reunião ASSINADA → só dados básicos + lista de participantes; nenhuma seção de ata renderizada.
3. Clica em PROGRAMADA alheia → bloco completo, adiciona/remove participantes, edita data/hora/facilitador, cancela.
4. Curl direto em `/api/pendencias` com token de secretária → 403.
5. Admin/regular: detalhe de ASSINADA renderiza ata completa (regressão zero).
6. Bug Josiane: ATA em AGUARDANDO_VALIDACAO → trocar responsável via dropdown → cargo acompanha.

---
_Atualizado automaticamente pelo `/deploy ship` em 2026-05-22._
