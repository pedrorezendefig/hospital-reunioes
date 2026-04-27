# Plano — Filtro por Facilitador (Calendário, Pendências Lista e Kanban)

## Contexto

Hoje qualquer usuário consegue ver reuniões e pendências, mas não há como recortar a visão por facilitador da reunião. O usuário (qualquer perfil, não só super admin) precisa poder filtrar:

- **Calendário** (`/reunioes/calendario`) — mostrar só os eventos cuja reunião tem facilitador X.
- **Pendências Lista** (`/pendencias`) — mostrar só pendências cuja reunião tem facilitador X.
- **Pendências Kanban** (`/pendencias/kanban`) — idem, contadores por coluna refletem o filtro.

Regra de negócio: a relação é via `pendencias.id_reuniao → reunioes.facilitador_id`. A pendência **não tem** facilitador próprio; ela herda do facilitador da reunião onde foi criada.

A infraestrutura está quase toda pronta: o campo `reunioes.facilitador_id` já existe (FK para `participantes.id`), o componente `MultiSelect` é genérico e reutilizável, o padrão de filtros via URL params já está estabelecido em pendências, e o padrão de "lookup → IDs → `.in_()`" já existe no filtro por setor (template ideal a copiar).

### Decisões alinhadas com o usuário

| Pergunta | Resposta |
|---|---|
| Multi vs single select | **Multi** (consistente com Status/Responsável/Setor) |
| Lista do dropdown | **Apenas quem já facilitou** (DISTINCT `facilitador_id` de reuniões vivas) — lista enxuta |
| Permissão | **Qualquer usuário logado** (a visibilidade já restringe; filtro é só uma view) |
| UI Calendário | **Barra de filtros nova** acima do grid (consistente com pendências) |

### Decisão arquitetural adicional (não perguntada — explicar no plano)

- **Pendências (lista e kanban)**: filtro **server-side** via novo query param `facilitador_id` (mesmo padrão de `responsavel_id`, `setor`, `prazo`). Justificativa: lista grande, paginada, faz sentido reduzir payload no backend.
- **Calendário**: filtro **client-side** (filter sobre os eventos já carregados do mês). Justificativa: o endpoint `/api/reunioes/calendario` carrega um range fechado por mês/semana e o volume é pequeno; aplicar filtro client-side é instantâneo (sem refetch ao mudar seleção) e evita tocar no endpoint de calendário (que tem sua própria lógica de range/cache). A barra ainda usa o mesmo hook `useFacilitadores`.

---

## Mudanças no Backend

### 1. Novo endpoint `GET /api/participantes/facilitadores`

**Arquivo:** `hospital-reunioes/backend/app/routers/participantes.py` (após o handler `list_participantes` em `participantes.py:30-52`).

**Lógica:**
1. Buscar `DISTINCT facilitador_id` de `reunioes` WHERE `deleted_at IS NULL` AND `facilitador_id IS NOT NULL`. Como Supabase-py não tem `DISTINCT` direto via builder, fazer `select("facilitador_id")` + dedup em Python.
2. Resolver participantes: `participantes.select("id, nome_completo, setor, is_externo, ativo").in_("id", facilitator_ids).order("nome_completo")`.
3. Sem filtro por `role` (qualquer participante pode ser facilitador).
4. Sem necessidade de `require_super_admin` — depende só de `get_current_user`.

**Resposta:** lista de objetos enxutos `{ id, nome_completo, setor, is_externo, ativo }`. Criar `FacilitadorResponse` (Pydantic) em `app/models/schemas.py` ou reusar `ParticipanteResponse` (mais pesado, mas evita schema novo). Recomendação: **criar `FacilitadorOption` enxuto** para esse caso de uso — mais leve no payload e na semântica.

```python
# app/models/schemas.py
class FacilitadorOption(BaseModel):
    id: str
    nome_completo: str
    setor: str | None = None
    is_externo: bool = False
    ativo: bool = True
```

### 2. Filtro `facilitador_id` em `GET /api/reunioes`

**Arquivo:** `hospital-reunioes/backend/app/routers/reunioes.py:178-215` (handler `list_reunioes`).

**Mudança:** adicionar query param e filtro, copiando o padrão exato dos outros params CSV.

```python
facilitador_id: str | None = Query(None, description="Facilitadores separados por vírgula"),
# ...
facilitadores = parse_csv_param(facilitador_id)
if facilitadores:
    if len(facilitadores) == 1:
        query = query.eq("facilitador_id", facilitadores[0])
    else:
        query = query.in_("facilitador_id", facilitadores)
```

(Esse endpoint não é o que o calendário consome — calendário usa `/reunioes/calendario`. Mas é o que aparece em qualquer outra listagem de reuniões e é trivial adicionar.)

### 3. Filtro `facilitador_id` em `GET /api/pendencias` e `GET /api/pendencias/stats`

**Arquivo:** `hospital-reunioes/backend/app/routers/pendencias.py`.

Adicionar query param em ambos os handlers (`get_pendencias_stats` em `pendencias.py:73-160` e `list_pendencias` em `pendencias.py:189-268`).

**Padrão:** lookup → IDs → `.in_("id_reuniao", ...)`. Idêntico ao filtro de setor (que faz lookup em `participantes`), mas dessa vez fazendo lookup em `reunioes`.

```python
facilitadores = parse_csv_param(facilitador_id)
if facilitadores:
    rq = supabase.table("reunioes").select("id_reuniao").is_("deleted_at", "null")
    if len(facilitadores) == 1:
        rq = rq.eq("facilitador_id", facilitadores[0])
    else:
        rq = rq.in_("facilitador_id", facilitadores)
    rq_res = rq.execute()
    facilitator_meeting_ids = [r["id_reuniao"] for r in (rq_res.data or [])]

    if not facilitator_meeting_ids:
        return []  # ou PendenciaStats() para o /stats — nenhuma reunião com esses facilitadores

    # Interseção com allowed_reuniao_ids (visibilidade) ANTES de aplicar à query
    if allowed_reuniao_ids is not None:
        # super user (None) já viu tudo; não-super: intersectar
        facilitator_meeting_ids = [m for m in facilitator_meeting_ids if m in set(allowed_reuniao_ids)]
        if not facilitator_meeting_ids and not my_participante_id:
            return []  # interseção vazia E sem co-resp → vazio

    query = query.in_("id_reuniao", facilitator_meeting_ids)
```

**Atenção crítica — interação com a visibilidade existente:** o handler atual aplica visibilidade via OR (`id_reuniao IN allowed OR co_responsavel_id = me`). Se eu simplesmente adicionar outro `.in_("id_reuniao", facilitator_meeting_ids)`, o `co_responsavel_id` do OR continuaria valendo, podendo retornar pendências fora do filtro de facilitador. **Decisão:** quando `facilitador_id` está presente, a semântica do filtro é "só pendências dessas reuniões", então o OR de co-responsável **deve ser ignorado** (ou seja: o filtro de facilitador é mais restritivo). Refatorar a aplicação: se há filtro de facilitador, **não** aplicar o `.or_(...)` de co-responsável; usar apenas `.in_("id_reuniao", facilitator_meeting_ids)` (já intersectado com allowed).

### 4. Sem migrations

Nenhuma migration de banco — todos os campos necessários já existem.

---

## Mudanças no Frontend

### 1. Novo tipo `FacilitadorOption`

**Arquivo:** `hospital-reunioes/frontend/src/types/index.ts`.

```typescript
export interface FacilitadorOption {
  id: string;
  nome_completo: string;
  setor?: string | null;
  is_externo?: boolean;
  ativo?: boolean;
}
```

### 2. Novo hook `useFacilitadores`

**Arquivo novo:** `hospital-reunioes/frontend/src/hooks/useFacilitadores.ts`.

Padrão idêntico ao `useCurrentParticipante.ts:62-104`: vanilla `fetch` + `useState` + `useEffect`, sem React Query (consistente com o resto do app). Cache simples em módulo (singleton in-memory) para evitar refetch nas 3 telas. Retorna `{ facilitadores: FacilitadorOption[], loading, error }`.

### 3. Pendências Lista — `app/pendencias/page.tsx`

Mudanças:

1. **Estado**: adicionar `filtroFacilitadores: string[]` (padrão: vazio = "Todos").
2. **Init via URL**: ler `searchParams.get("facilitador")` e fazer `split(",")` (junto com os outros params já em `pendencias/page.tsx:442-452`).
3. **Hook**: chamar `const { facilitadores } = useFacilitadores()`.
4. **MultiSelect novo**: adicionar na grid de filtros (`pendencias/page.tsx:632-717`), entre "Setor"/"Responsável" e os campos de prazo. Layout `lg:grid-cols-6` já tem espaço.
5. **Visibilidade do filtro**: mostrar para **qualquer usuário** (sem o `if (isSuperAdmin)` que envolve "Setor" e "Responsável").
6. **Fetch**: anexar `facilitador_id=...` à query string (junto com `responsavel_id`, `setor`, `prazo_de`, `prazo_ate` em `pendencias/page.tsx:503-507`).
7. **URL replace**: ao mudar o filtro, fazer `router.replace` com o novo param (mesmo padrão dos outros).
8. **"Limpar Filtros"**: o botão em `pendencias/page.tsx:709` deve resetar `filtroFacilitadores` também.

### 4. Pendências Kanban — `app/pendencias/kanban/page.tsx`

Mudanças idênticas às da Lista (mesmo estado, mesmo MultiSelect, mesmo fetch). Pontos:
- Estado em `filtroFacilitadores`.
- MultiSelect dentro da grid de filtros existente (`pendencias/kanban/page.tsx:485-533`).
- Fetch passa `facilitador_id=...` (junto com `responsavel_id`, `prazo_de`, `prazo_ate` em `pendencias/kanban/page.tsx:287-312`).
- URL params em `pendencias/kanban/page.tsx:242-249`.

Nota: as colunas do kanban (PENDENTE, EM_PROGRESSO, etc.) e suas contagens já refletem o resultado do fetch — o filtro server-side se propaga naturalmente.

### 5. Calendário — `app/reunioes/calendario/page.tsx`

Mudanças:

1. **Nova barra de filtros** entre o header e o grid (próximo a `calendario/page.tsx:1206`). Layout fino, uma linha:
   ```
   ┌──────────────────────────────────────────────┐
   │ 🔎 Facilitador: [Selecionar pessoas ▼]       │
   └──────────────────────────────────────────────┘
   ```
2. **Estado**: `filtroFacilitadores: string[]`.
3. **Init via URL**: ler `searchParams.get("facilitador")` (próximo às leituras de `year`/`month`/`view` em `calendario/page.tsx:1060-1075`).
4. **Hook**: `useFacilitadores()`.
5. **MultiSelect** com o array de facilitadores como options.
6. **Filtro CLIENT-SIDE**: aplicar `Array.filter` sobre os eventos retornados antes de renderizar — `eventos.filter(ev => filtroFacilitadores.length === 0 || filtroFacilitadores.includes(ev.facilitador_id))`. (Confirmar que o evento do calendário já carrega `facilitador_id` — pelos exploradores, `Reuniao.facilitador_id` está no schema; se o endpoint `/reunioes/calendario` projetar o campo, está pronto. Caso contrário, ajustar o `select(...)` lá.)
7. **URL replace** ao mudar.

---

## Arquivos críticos a modificar

### Backend
- `hospital-reunioes/backend/app/models/schemas.py` — adicionar `FacilitadorOption`.
- `hospital-reunioes/backend/app/routers/participantes.py` — novo endpoint `GET /facilitadores`.
- `hospital-reunioes/backend/app/routers/reunioes.py:178-215` — filtro `facilitador_id` em `list_reunioes`.
- `hospital-reunioes/backend/app/routers/pendencias.py:73-160` (stats) e `:189-268` (lista) — filtro `facilitador_id` com lookup + interseção com visibilidade.

### Frontend
- `hospital-reunioes/frontend/src/types/index.ts` — `FacilitadorOption`.
- `hospital-reunioes/frontend/src/hooks/useFacilitadores.ts` — **novo** hook.
- `hospital-reunioes/frontend/src/app/pendencias/page.tsx` — estado, MultiSelect novo, URL params, fetch.
- `hospital-reunioes/frontend/src/app/pendencias/kanban/page.tsx` — idem.
- `hospital-reunioes/frontend/src/app/reunioes/calendario/page.tsx` — barra nova, estado, MultiSelect, filter client-side.

### Componentes reutilizados (sem modificar)
- `hospital-reunioes/frontend/src/components/ui/MultiSelect.tsx` — props `options`, `selected`, `onChange`, `label`, `placeholder`, `allLabel="Todos"`.
- `hospital-reunioes/backend/app/utils/query_params.py::parse_csv_param` — já usado em todos os filtros CSV.

---

## Verificação (end-to-end)

### 1. Subir o app local
```
/atualizar-app
```

### 2. Backend — testes manuais via API
- `curl http://localhost:8000/api/participantes/facilitadores -H "Authorization: Bearer ..."` → lista enxuta de quem já facilitou.
- `curl 'http://localhost:8000/api/reunioes?facilitador_id=P001'` → só reuniões do P001.
- `curl 'http://localhost:8000/api/pendencias?facilitador_id=P001'` → só pendências cujas reuniões têm P001 como facilitador.
- `curl 'http://localhost:8000/api/pendencias?facilitador_id=P001,P003'` → multi-facilitador (OR).
- `curl 'http://localhost:8000/api/pendencias?facilitador_id=P999'` → vazio (facilitador inexistente).

### 3. Frontend — testes manuais nas 3 telas
- Abrir `/reunioes/calendario`, ver barra de filtros nova, selecionar 1 facilitador → grid mostra só os eventos dele. Selecionar 2 → união. Limpar → tudo.
- Abrir `/pendencias`, abrir o MultiSelect "Facilitador" (visível pra qualquer perfil), selecionar 1 → tabela filtra. Combinar com filtro de Status → ambos se aplicam (AND). URL reflete `?facilitador=P001&status=PENDENTE`.
- Abrir `/pendencias/kanban`, mesmas verificações; conferir que as contagens das colunas refletem o filtro.
- Atualizar (F5) com filtro aplicado → estado restaurado da URL.
- Compartilhar a URL com filtro → outra sessão abre com o mesmo filtro.

### 4. Backend — testes automáticos (opcional, mas recomendado)
- Adicionar 1 teste em `hospital-reunioes/backend/tests/` para `GET /api/pendencias?facilitador_id=X` (1 cenário de match, 1 sem match, 1 com interseção com `allowed_reuniao_ids` vazia).

### 5. Regressão
- Verificar que o fetch existente continua funcionando sem `facilitador_id` (parâmetro opcional, default vazio).
- Verificar que filtros já existentes (Status, Responsável, Setor, Prazo, "Críticas") não regridem.

---

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Interação errada entre filtro de facilitador e OR de co-responsável (visibilidade) | Decisão explícita: quando `facilitador_id` está presente, **ignorar** o OR de co-responsável (filtro de facilitador é mais restritivo). Cobrir com teste. |
| Lista de facilitadores vazia em ambiente de dev/teste | Endpoint retorna `[]`; UI mostra MultiSelect com "Nenhuma opção encontrada" (já é o comportamento atual do componente). |
| Endpoint `/reunioes/calendario` não projeta `facilitador_id` | Verificar antes de implementar; se faltar, adicionar ao `select()` desse endpoint (1 linha). |
| Cache do hook `useFacilitadores` ficando stale após criar nova reunião | Aceitar — cache é por sessão; refresh resolve. Não vale a pena invalidar agora. |
| Pendências importadas/migradas sem `facilitador_id` na reunião | Já tratado: lookup ignora `facilitador_id IS NULL`. Esses casos simplesmente não aparecem ao filtrar. |

---

## Observação sobre localização do plano

O sistema do plan-mode forçou o caminho `~/.claude/plans/eu-preciso-de-um-golden-cook.md`. Após aprovação e ao iniciar execução, copiar para `planos/plano-26-04-27-XXXXh-filtro-por-facilitador.md` (padrão do CLAUDE.md do projeto), com a seção `## Execução / Resultados` para registro contínuo.

---

## Execução / Resultados

Iniciado e concluído em 2026-04-27 (~04:56–05:05). Branch: `feat/ana-fase1-foundation`.

### Backend — implementado

1. **`app/models/schemas.py`** — adicionado `FacilitadorOption` (id, nome_completo, setor, is_externo, ativo). Payload enxuto pra alimentar o filtro.
2. **`app/routers/participantes.py`** — novo handler `GET /facilitadores` (logo antes do `POST /` pra ordem de path matching). Faz `select("facilitador_id")` em `reunioes` (vivas + facilitador_id não-nulo), dedup em Python, e resolve nomes via `participantes.in_("id", ...)` ordenado por nome. Sem `require_super_admin` — qualquer logado.
3. **`app/routers/reunioes.py`** — `list_reunioes` agora aceita `facilitador_id` (CSV via `parse_csv_param`), aplicado com `.eq()` ou `.in_()` mantendo o padrão dos outros params.
4. **`app/routers/pendencias.py`** — `list_pendencias` e `get_pendencias_stats` agora aceitam `facilitador_id`. Implementação:
   - Resolve `facilitator_meeting_ids` cedo via lookup em `reunioes` (dead path retorna `[]`/`PendenciaStats()` com `X-Total-Count=0`).
   - Quando o filtro está presente, **ignora o OR de co-responsável** da visibilidade (decisão tomada no plano para não vazar pendências fora do facilitador escolhido). Faz interseção com `allowed_reuniao_ids` antes de aplicar o `.in_("id_reuniao", ...)`.
   - Quando o filtro está ausente, mantém a lógica original de visibilidade intacta.

### Frontend — implementado

1. **`src/types/index.ts`** — adicionado `FacilitadorOption`.
2. **`src/hooks/useFacilitadores.ts`** (novo) — hook com cache singleton em módulo (idêntico ao `useCurrentParticipante`), Promise deduplicada, expõe `invalidateFacilitadores()`.
3. **`src/app/pendencias/page.tsx`** — estado `filtroFacilitadores` com init via `searchParams.get("facilitador")`, MultiSelect novo na grid (visível pra **qualquer** usuário, não só super admin), `facilitador_id` na query string do fetch, dependências do `useCallback`/`useEffect` atualizadas, indicador "Ativos" considera o novo filtro, botão "Limpar Filtros" reseta também.
4. **`src/app/pendencias/kanban/page.tsx`** — mesmas mudanças, MultiSelect entre Responsável e Prazos, fetch com `facilitador_id`, limpar reseta também.
5. **`src/app/reunioes/calendario/page.tsx`** — barra nova entre o banner de sucesso e o card do calendário (com ícone Filter + chip "Ativos" + MultiSelect + botão Limpar condicional). Filtro **client-side** via `useMemo` sobre `eventos` antes de agrupar por dia. O endpoint `/api/reunioes/calendario` já projetava `facilitador_id` (linha 128 de `reunioes.py`), nada a mudar lá.

### Verificações executadas

- **Sintaxe Python** dos 4 arquivos do backend: OK (`ast.parse`).
- **`tsc --noEmit`** no frontend: OK (exit code 0, zero erros de tipo).
- **`/atualizar-app`** subiu a stack em 38s (build+up 35s, backend 200 em 4s, frontend 200 em 1s).
  - **Detalhe do build:** o primeiro `apply.sh` quebrou em `pnpm install --frozen-lockfile` por divergência preexistente (zustand removido do `package.json` mas ainda presente no `pnpm-lock.yaml`). Resolvido rodando `corepack pnpm install` local pra regenerar o lockfile (mudança não relacionada ao filtro; o lockfile já estava com `M` no git desde antes desta sessão).
- **Smoke test dos endpoints** (sem token):
  - `GET /api/participantes/facilitadores` → 401 (✅ existe + auth obrigatório)
  - `GET /api/reunioes?facilitador_id=P001` → 401 (✅ param aceito)
  - `GET /api/pendencias?facilitador_id=P001` → 401 (✅ idem)
  - `GET /api/pendencias/stats?facilitador_id=P001` → 401 (✅ idem)
- **OpenAPI** (`/api/openapi.json`) confirma:
  - `/api/participantes/facilitadores` está roteado.
  - `facilitador_id` é parameter declarado em `/api/reunioes`, `/api/pendencias` e `/api/pendencias/stats`.

### Pendente — testes manuais no browser

Pedro precisa abrir `http://localhost:3000` (já está rodando) e validar:

1. **`/reunioes/calendario`** — barra de filtros aparece, MultiSelect "Facilitador" lista os nomes; ao selecionar, eventos do mês filtram em tempo real (sem refetch).
2. **`/pendencias`** — MultiSelect "Facilitador" aparece pra qualquer perfil; combina com Status/Responsável/Prazo (AND); F5 com `?facilitador=P001` mantém o filtro.
3. **`/pendencias/kanban`** — idem, contagens das colunas refletem o filtro.
4. **Regressão** — Status/Responsável/Setor/Prazo/Críticas continuam funcionando como antes.

### Itens não executados (de propósito)

- Testes automáticos backend (`tests/`) — listados como opcional no plano. Se quiser, abrir uma sub-tarefa pra cobrir os 3 cenários (match / sem match / interseção com allowed vazia).
- Commit — Pedro decide quando fazer.
