# Super Admin CRUD Completo — Plano Mestre

> **Para executores agentic:** após aprovação deste plano, executar fase-por-fase. A Fase 1 está detalhada em tarefas bite-sized com TDD e commits frequentes. Fases 2 e 3 têm specs de design — os planos executáveis delas são escritos em momentos separados, ao iniciarmos cada uma (evita que um spec fique obsoleto por 3+ semanas antes de virar código).

## Contexto

O projeto Hospital Reuniões já tem `/admin` funcional com 4 telas (Usuários, Super Admins, Logs, Ações em Massa). O super-admin hoje consegue operar o básico, mas o sistema tem lacunas críticas para "admin de sistema de verdade":

- **Setores e cargos são texto livre** em `participantes.setor`/`.cargo` — sem tabela, sem validação, sem dedup. "Administrativo", "administrativo" e "Adm" coexistem.
- **Tipos de reunião** são `CHECK` constraint no schema — não editáveis sem migration.
- **Participantes externos** (criados pelo resolver de STT quando não bate com interno conhecido) ficam invisíveis no fluxo admin — não há como corrigir uma atribuição errada nem promover um externo a interno.
- **Reuniões e pendências não têm CRUD admin** — correções de status/facilitador/responsável precisam de SQL direto.
- **Sem soft delete** em reuniões/pendências — contraria compliance de ata assinada.
- **Auditoria parcial**: `audit_log` só cobre mutações em `/admin/usuarios`. Bulk tem log separado. Demais mutações não logam.
- **UI fragmentada**: cada página monta sua própria tabela, sem DataTable compartilhado. Bulk usa `alert()` para erros.

Este plano entrega esse "pente fino" em 3 fases independentes, cada uma mergeável sozinha.

---

## Decisões Arquiteturais (fechadas no brainstorming)

1. **Setores e Cargos como entidades de primeira classe** (não taxonomy-over-text). Tabelas novas + FK em `participantes`. Tipos de Reunião idem.
2. **Internalização de externo** suporta dois cenários:
   - **Mesclar (M)**: externo é duplicata de interno existente → RPC atômica transfere FKs e deleta externo.
   - **Promover (P)**: externo é pessoa nova → marca `is_externo=false`, preenche dados. Envio de senha é ação posterior manual (reaproveita `NewPasswordModal`).
3. **Soft delete** em `reunioes` e `pendencias` (coluna `deleted_at`). Hard delete indisponível via UI.
4. **Edição de ata** bloqueada no núcleo quando status = `ASSINADA` (bloqueia `json_ata`, `url_pdf_assinado`, `data_assinatura`, `envelope_key_clicksign`, `status_ata`). Metadados periféricos (título, setor, facilitador, grupo de recorrência) continuam editáveis.
5. **Pendências** sempre editáveis — correção de atribuição é caso real.
6. **Status de reunião** editável manualmente por super-admin (para destravar pipeline).
7. **Sidebar agrupada por seção**: Pessoas / Taxonomia / Operações / Auditoria.
8. **Super Admins** sai como tela própria — vira ação inline no CRUD de Usuários.
9. **Participantes Externos** não vira tela própria — fica como badge + filtro em Usuários, com ação "Resolver" inline.
10. **Auditoria**: toda mutação feita via admin grava em `audit_log` (estender cobertura).
11. **Backend usa `service_role`** (bypassa RLS) — mantém padrão atual. Não criar policies novas para authenticated admin no frontend.

---

## Visão Geral — 3 Fases

### Fase 1 — Fundação & Taxonomia (detalhada abaixo em plano executável)
Construir o alicerce: `DataTable` reutilizável + migrations de taxonomia + CRUDs de Setores/Cargos/Tipos de Reunião + reorganização da sidebar. Entrega: admin consegue gerir taxonomia e demais telas ganham base visual consistente.

### Fase 2 — Pessoas (spec abaixo, plano executável será escrito ao iniciar a fase)
Expandir CRUD de Usuários com badge/filtro de externos, modal Resolver (M+P), RPC de merge atômico, CRUD de `signup_requests`, integração de Super Admins como ação inline, remoção de `/admin/super-admins`. Entrega: admin consegue resolver ambiguidades de identidade e aprovar solicitações.

### Fase 3 — Operações & Pente Fino (spec abaixo, plano executável será escrito ao iniciar a fase)
Soft delete em reuniões/pendências, CRUD admin de Reuniões (edição por status) e de Pendências (sempre editável), auditoria consolidada, correção dos bugs do Bulk (alert→toast, refetch após retry), revisão de todos os filtros existentes. Entrega: admin completo, consistente, auditado.

---

# Spec Detalhado — Fase 1 (Fundação & Taxonomia)

## Arquitetura

**Frontend**: novo componente `DataTable` em `frontend/src/components/admin/DataTable.tsx` com props tipadas para colunas, dados, paginação, filtros, ações por linha, empty state e loading skeleton. Todas as 3 novas telas de Fase 1 usam o DataTable. Telas existentes (Usuários, Logs, Bulk) migram no Pente Fino da Fase 3 — não nesta fase (minimiza risco de regressão de algo já funcional).

**Backend**: novo router `backend/app/routers/admin/taxonomia.py` com três sub-recursos (`/admin/setores`, `/admin/cargos`, `/admin/tipos-reuniao`) seguindo o mesmo padrão REST: GET list, GET detail, POST create, PATCH update, DELETE (soft via `ativo=false`). Schemas Pydantic em `backend/app/models/admin_schemas.py`.

**Banco**: duas migrations:
- `027_create_taxonomy_tables.sql`: cria `setores`, `cargos`, `tipos_reuniao` e faz seed a partir de distinct dos valores atuais (normalizado por `trim()` + `initcap()`).
- `028_add_taxonomy_fks.sql`: adiciona `setor_id`, `cargo_id` em `participantes` e `tipo_id` em `reunioes`, faz backfill matchando pelo nome normalizado. **Mantém** as colunas TEXT antigas (`setor`, `cargo`, `tipo`) como compat durante 1 ciclo de release — só dropa na Fase 3 depois de confirmar que nenhuma query legada usa.

## Componentes

### `DataTable<T>` (frontend)
```typescript
type DataTableProps<T> = {
  columns: Array<{
    key: string;
    header: string;
    render?: (row: T) => ReactNode;
    sortable?: boolean;
    width?: string;
  }>;
  data: T[];
  loading?: boolean;
  error?: string;
  pagination?: {
    page: number;
    pageSize: number;
    total?: number;
    onPageChange: (page: number) => void;
  };
  emptyState?: { title: string; hint?: string };
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
  toolbar?: ReactNode; // para filtros/busca/botão "novo"
};
```
- Estilo consistente com `AdminSidebar` atual (cores, spacing).
- Paginação com "Anterior / Próxima" + exibição de "Página N · M itens" quando `total` fornecido.
- Loading: skeleton de 5 linhas cinzas.
- Empty: centralizado com ícone + título + hint.

### Rotas Fase 1
- `/admin/setores` — lista, criar, editar, arquivar (soft)
- `/admin/cargos` — idem
- `/admin/tipos-reuniao` — idem

### Sidebar reorganizada
`AdminSidebar.tsx` recebe seções:
```
PESSOAS
  Usuários             /admin/usuarios
  (Solicitações — Fase 2)
TAXONOMIA
  Setores              /admin/setores
  Cargos               /admin/cargos
  Tipos de Reunião     /admin/tipos-reuniao
OPERAÇÕES
  (Reuniões — Fase 3)
  (Pendências — Fase 3)
  Ações em Massa       /admin/bulk
AUDITORIA
  Logs                 /admin/logs
```
Cabeçalhos de seção em maiúsculo, cinza, não-clicáveis. Itens com estado ativo igual ao atual. Remover item "Super Admins" (vira ação inline em Fase 2; ainda na sidebar na Fase 1 via comentário temporário — removido em Fase 2).

## Data Flow

1. Usuário abre `/admin/setores`.
2. Página chama `GET /api/admin/setores?ativo=todos&q=<busca>&page=1&limit=50`.
3. Backend valida super-admin, consulta Supabase com `service_role`, retorna `{data: Setor[], total: number}`.
4. Página renderiza `DataTable` com toolbar (busca + filtro ativo/arquivado + botão "Novo setor").
5. Clique em "Novo setor" abre modal com um campo (nome). Submit faz `POST /api/admin/setores`, fecha modal, recarrega lista, mostra toast.
6. Clique em linha abre modal de edição (nome + ativo). `PATCH`.
7. Clique em "Arquivar" (soft delete) pede motivo via `ReasonModal` existente, faz `DELETE` que na verdade é `UPDATE ativo=false`. Admin com toggle "Mostrar arquivados" vê e pode reativar.

## Error Handling

- Duplicata (nome case-insensitive já existe): backend retorna 409 com mensagem clara, front mostra toast e destaca campo.
- Delete de setor/cargo em uso: backend bloqueia com 409 e resposta `{ usage_count: N, sample: [...] }`. Front mostra modal "Este setor está em uso por N participantes. Arquivar mesmo assim manterá os vínculos; dropar exigiria reatribuir primeiro." Super-admin confirma arquivar (ativo=false) — nunca force-delete com vínculos vivos.
- Erros de rede: toast vermelho padronizado.

## Testing

- **Backend**: `pytest` cobrindo cada endpoint (list, create, patch, delete) com casos: happy path, duplicata case-insensitive, não-autorizado (usuário comum), filtros.
- **Frontend**: testes de componente do `DataTable` (render, paginação, empty, loading) + smoke test de cada nova página (Playwright ou integração via `/atualizar-app`).
- **Migrations**: teste de idempotência (aplicar 027 e 028 em DB dev; verificar que o dedup preserva todos os participantes; nenhum `setor_id` NULL após backfill a menos que `setor` original era NULL).

---

# Spec de Design — Fase 2 (Pessoas)

## Escopo

1. **Badge EXTERNO + filtro por tipo em Usuários**: nova coluna visual; filtro tri-state (Todos / Internos / Externos).
2. **Modal "Resolver" (M + P)**: botão "Resolver" aparece só em linhas com `is_externo=true`. Modal com tabs:
   - **Mesclar com interno existente**: busca auto-complete de internos (reusa `/api/admin/usuarios?tipo=interno&q=`), mostra preview do interno selecionado, campo motivo obrigatório, chama `POST /api/admin/usuarios/merge` que invoca a RPC.
   - **Promover a interno novo**: form com email (obrigatório, unique check), setor (select da tabela `setores`), cargo (select), role, ativo. Submit atualiza o próprio registro (`is_externo=false`, `ativo=true`, FKs preenchidas). Mostra lembrete "Para dar acesso, use o botão 'Resetar senha' depois."
3. **RPC `rpc_merge_participante_externo(externo_id, interno_id, motivo, actor_id)`**: transação PL/pgSQL atômica:
   - Valida que externo tem `is_externo=true` e interno tem `is_externo=false`.
   - UPDATE `reuniao_participantes` SET `participante_id = interno_id` WHERE `participante_id = externo_id` (respeitando UNIQUE — se interno já está na reunião, DELETE o vínculo do externo em vez de UPDATE).
   - UPDATE `pendencias` SET `responsavel_id = interno_id` (+ `responsavel_nome` atualizado).
   - UPDATE `pendencias` SET `co_responsavel_id = interno_id` (+ `co_responsavel_nome`).
   - UPDATE `comentarios_pendencias` SET `autor_id = interno_id` (+ `autor_nome`).
   - UPDATE `comentarios_pendencias` SET `mencoes = array_replace(mencoes, externo_id, interno_id)` — para todos que contenham.
   - UPDATE `notificacoes` SET `destinatario_id = interno_id`.
   - INSERT `audit_log` com `action='merge_participante'`, `target_id=externo_id`, metadata `{interno_id, counters: {reunioes: N, pendencias: N, ...}}`.
   - DELETE FROM `participantes` WHERE `id = externo_id`.
   - Retorna contadores para feedback na UI.
4. **CRUD de `signup_requests`** em `/admin/solicitacoes`: listagem filtrada (pendente / confirmado / expirado) com ações: "Aprovar manualmente" (confirma e cria participante), "Rejeitar" (deleta com motivo + log), "Reenviar email de confirmação", "Expirar agora".
5. **Integrar Super Admins como ação inline**: no CRUD de Usuários, botão "Tornar super admin" / "Revogar super admin" via `ReasonModal`. Remover rota `/admin/super-admins` e componente. Filtro na lista já permite isolar super admins (`?super_admin=true`).
6. **Auditoria** estendida: `merge_participante`, `promote_participante`, `signup_request_approve`, `signup_request_reject`, `signup_request_resend`, `signup_request_expire`, `super_admin_grant_inline`, `super_admin_revoke_inline`.

## Riscos e mitigações
- **Race em merge**: se dois super-admins resolvem o mesmo externo simultaneamente, segunda transação falha pela validação inicial. OK.
- **mencoes[] com interno já presente**: usar `array_replace` + dedup via `ARRAY(SELECT DISTINCT unnest(...))` para evitar duplicata.
- **Externo é facilitador de reunião**: adicionar no merge `UPDATE reunioes SET facilitador_id = interno_id WHERE facilitador_id = externo_id`. Idem `importado_por_id`. Verificar todas as FKs de `participantes.id` antes de escrever a RPC.

## Testing
- Teste pytest da RPC com dataset fake (externo com 3 reuniões, 5 pendências como responsável, 2 como co-resp, 4 comentários, 2 menções, 1 notificação). Assertar contadores batem, externo sumiu, interno herdou tudo, audit_log gravou.
- E2E: promover externo novo → virar interno → aparecer na lista com filtro "internos".

---

# Spec de Design — Fase 3 (Operações & Pente Fino)

## Escopo

### 3A — Soft delete e CRUD admin de Reuniões e Pendências
1. **Migration `029_add_soft_delete.sql`**: `ALTER TABLE reunioes ADD deleted_at TIMESTAMPTZ NULL`, idem `pendencias`. Index parcial `WHERE deleted_at IS NULL`. Todas as queries existentes que listam (dashboard, listagem de atas, etc.) passam a filtrar `deleted_at IS NULL` — **auditar todos os `SELECT FROM reunioes`/`pendencias` antes da migration ir pro PR**.
2. **`/admin/reunioes`**: DataTable com filtros (status_ata, setor, facilitador, data_de, data_ate, busca por título/id). Toggle "Mostrar arquivadas". Linha → modal de edição. Modal respeita bloqueio por status ASSINADA: se assinada, campos `json_ata`, `url_pdf_assinado`, `data_assinatura`, `envelope_key_clicksign`, `status_ata` ficam `disabled` com tooltip "Protegido por compliance — ata assinada é imutável." Demais campos editáveis. Para reuniões em outros status, todos os campos editáveis, incluindo status (força pipeline).
3. **`/admin/pendencias`**: DataTable com filtros (status, responsável, co-responsável, prazo_de, prazo_ate, reunião). Edição livre de todos os campos. Soft delete com restore.
4. **Endpoints**: `/admin/reunioes` e `/admin/pendencias` com GET/PATCH/DELETE/RESTORE. DELETE faz `UPDATE deleted_at = now()`. RESTORE faz `UPDATE deleted_at = NULL`.
5. **Auditoria** estendida: `update_reuniao`, `delete_reuniao` (soft), `restore_reuniao`, `update_pendencia`, `delete_pendencia`, `restore_pendencia`. Metadata inclui diff de campos alterados.

### 3B — Pente Fino
1. **Revisar filtros existentes**: para cada página (`/admin/usuarios`, `/admin/logs`, `/admin/bulk`), confirmar que cada filtro na UI realmente se propaga no request e no query SQL. Hoje o mapeamento indica que Usuários e Logs estão OK, mas reauditar após Fase 1 (quando filtro de setor virar FK) e Fase 2 (quando filtro de tipo for adicionado).
2. **Bulk**: trocar todos os `alert()` por toasts consistentes (`src/app/admin/bulk/page.tsx:405` e `:699`). Ao retry de job com falhas, manter seleção de filtros aplicados no refetch.
3. **Modais**: padronizar backdrop click-to-close e `Escape` key em todos os modais admin (`UsuarioFormModal`, `ReasonModal`, `NewPasswordModal`, modais de bulk, novos modais de Fase 1 e 2).
4. **Total na listagem de Usuários**: hoje paginação não mostra total. Adicionar count no response e exibir.
5. **Migrar telas antigas para `DataTable`**: `Usuários`, `Logs`, `Bulk`. Feito por último, como refactor não-funcional — commit separado.
6. **Drop das colunas TEXT antigas** (`participantes.setor`, `participantes.cargo`, `reunioes.tipo`) — só após garantir que nenhuma query legada referencia. Greps em todo o repo + teste smoke do app completo (`/atualizar-app`).

## Testing
- Smoke test manual completo: criar reunião mock, passar pelo pipeline, arquivar, restaurar, ver em logs.
- Pente fino: checklist com cada filtro de cada página listado e verificado.

---

# Plano Executável — Fase 1

**Pré-requisito:** trabalhar em worktree isolado. Criar via `git worktree add ../Hospital-fase1-taxonomia fase1-taxonomia`.

**Convenção de commit:** `feat(admin): <descrição>` para features, `chore(admin):` para setup, `test(admin):` para testes, `fix(admin):` para correções.

**Proibido em sub-agents** (lição aprendida): qualquer prompt que despache sub-agent deve incluir: "NÃO use `git checkout --`, `git reset --hard`, `git stash drop` ou qualquer comando git destrutivo em arquivos que não são objeto desta tarefa. Se detectar estado inesperado (arquivos não-familiares, branch diferente), PARE e pergunte."

---

### Task 1: DataTable — esqueleto e testes unitários

**Files:**
- Create: `frontend/src/components/admin/DataTable.tsx`
- Create: `frontend/src/components/admin/DataTable.test.tsx`
- Test: `frontend/src/components/admin/DataTable.test.tsx`

- [ ] **Step 1: Escrever teste falho — render básico**

```tsx
// DataTable.test.tsx
import { render, screen } from '@testing-library/react';
import { DataTable } from './DataTable';

test('renderiza headers e linhas', () => {
  render(
    <DataTable
      columns={[
        { key: 'nome', header: 'Nome' },
        { key: 'ativo', header: 'Ativo' },
      ]}
      data={[{ nome: 'Teste', ativo: true }]}
    />
  );
  expect(screen.getByText('Nome')).toBeInTheDocument();
  expect(screen.getByText('Teste')).toBeInTheDocument();
});
```

- [ ] **Step 2: Rodar teste para garantir falha**

Run: `cd frontend && npm test -- DataTable`
Expected: FAIL — "Cannot find module './DataTable'"

- [ ] **Step 3: Implementação mínima do DataTable**

```tsx
// DataTable.tsx
import { ReactNode } from 'react';

export type Column<T> = {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
  width?: string;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  data: T[];
  loading?: boolean;
  emptyState?: { title: string; hint?: string };
  onRowClick?: (row: T) => void;
  rowActions?: (row: T) => ReactNode;
  toolbar?: ReactNode;
  pagination?: {
    page: number;
    pageSize: number;
    total?: number;
    onPageChange: (p: number) => void;
  };
};

export function DataTable<T extends Record<string, any>>(props: DataTableProps<T>) {
  const { columns, data, loading, emptyState, onRowClick, rowActions, toolbar, pagination } = props;
  return (
    <div className="data-table">
      {toolbar && <div className="data-table__toolbar">{toolbar}</div>}
      <table>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={{ width: c.width }}>{c.header}</th>
            ))}
            {rowActions && <th>Ações</th>}
          </tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={columns.length + (rowActions ? 1 : 0)}>Carregando…</td></tr>}
          {!loading && data.length === 0 && emptyState && (
            <tr><td colSpan={columns.length + (rowActions ? 1 : 0)}>
              <strong>{emptyState.title}</strong>
              {emptyState.hint && <p>{emptyState.hint}</p>}
            </td></tr>
          )}
          {!loading && data.map((row, i) => (
            <tr key={i} onClick={() => onRowClick?.(row)}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(row) : String(row[c.key] ?? '')}</td>
              ))}
              {rowActions && <td>{rowActions(row)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
      {pagination && (
        <div className="data-table__pagination">
          <button disabled={pagination.page === 1} onClick={() => pagination.onPageChange(pagination.page - 1)}>Anterior</button>
          <span>Página {pagination.page}{pagination.total !== undefined ? ` · ${pagination.total} itens` : ''}</span>
          <button
            disabled={data.length < pagination.pageSize}
            onClick={() => pagination.onPageChange(pagination.page + 1)}
          >Próxima</button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Rodar teste para confirmar passa**

Run: `cd frontend && npm test -- DataTable`
Expected: PASS

- [ ] **Step 5: Adicionar testes de paginação, empty e loading**

```tsx
test('mostra empty state quando data vazia', () => {
  render(
    <DataTable
      columns={[{ key: 'a', header: 'A' }]}
      data={[]}
      emptyState={{ title: 'Nada aqui', hint: 'Crie o primeiro' }}
    />
  );
  expect(screen.getByText('Nada aqui')).toBeInTheDocument();
});

test('mostra loading', () => {
  render(<DataTable columns={[{key:'a',header:'A'}]} data={[]} loading />);
  expect(screen.getByText(/Carregando/)).toBeInTheDocument();
});

test('paginação navega', async () => {
  const onPageChange = jest.fn();
  render(
    <DataTable
      columns={[{key:'a',header:'A'}]}
      data={Array.from({length:50},(_,i)=>({a:i}))}
      pagination={{page:2, pageSize:50, total:200, onPageChange}}
    />
  );
  await userEvent.click(screen.getByText('Anterior'));
  expect(onPageChange).toHaveBeenCalledWith(1);
});
```

- [ ] **Step 6: Rodar suíte e confirmar tudo passa**

Run: `cd frontend && npm test -- DataTable`
Expected: PASS (3 testes)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/admin/DataTable.tsx frontend/src/components/admin/DataTable.test.tsx
git commit -m "feat(admin): adiciona DataTable reutilizável com paginação"
```

---

### Task 2: Migration 027 — criar tabelas de taxonomia

**Files:**
- Create: `hospital-reunioes/supabase/migrations/027_create_taxonomy_tables.sql`

- [ ] **Step 1: Escrever migration**

```sql
-- 027_create_taxonomy_tables.sql
-- Cria tabelas de taxonomia (setores, cargos, tipos_reuniao)
-- e faz seed inicial a partir dos valores atuais (distinct normalizado).

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS setores (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT setores_nome_unique_ci UNIQUE (nome)
);
CREATE UNIQUE INDEX setores_nome_lower_idx ON setores ((lower(nome)));

CREATE TABLE IF NOT EXISTS cargos (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX cargos_nome_lower_idx ON cargos ((lower(nome)));

CREATE TABLE IF NOT EXISTS tipos_reuniao (
  id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  nome TEXT NOT NULL,
  ativo BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX tipos_reuniao_nome_lower_idx ON tipos_reuniao ((lower(nome)));

-- Triggers de updated_at (reusa função existente update_updated_at)
CREATE TRIGGER trigger_setores_updated_at BEFORE UPDATE ON setores
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_cargos_updated_at BEFORE UPDATE ON cargos
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trigger_tipos_reuniao_updated_at BEFORE UPDATE ON tipos_reuniao
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- Seed: popular com distincts normalizados dos campos existentes.
INSERT INTO setores (nome)
SELECT DISTINCT initcap(trim(setor))
FROM participantes
WHERE setor IS NOT NULL AND trim(setor) <> ''
ON CONFLICT ON CONSTRAINT setores_nome_unique_ci DO NOTHING;

INSERT INTO cargos (nome)
SELECT DISTINCT initcap(trim(cargo))
FROM participantes
WHERE cargo IS NOT NULL AND trim(cargo) <> ''
ON CONFLICT DO NOTHING;

-- Tipos de reunião: começa com os valores fixos do CHECK atual
INSERT INTO tipos_reuniao (nome) VALUES
  ('Diretoria'), ('Gerencial'), ('Coordenação'), ('Mensal'), ('Extraordinária')
ON CONFLICT DO NOTHING;

-- E depois garante que qualquer tipo já usado em reunioes que não esteja listado também entre
INSERT INTO tipos_reuniao (nome)
SELECT DISTINCT initcap(trim(tipo))
FROM reunioes
WHERE tipo IS NOT NULL
ON CONFLICT DO NOTHING;

-- RLS: ativar e permitir leitura a super-admin
ALTER TABLE setores ENABLE ROW LEVEL SECURITY;
ALTER TABLE cargos ENABLE ROW LEVEL SECURITY;
ALTER TABLE tipos_reuniao ENABLE ROW LEVEL SECURITY;
-- Mutações vão via backend com service_role; sem policy para authenticated.
```

- [ ] **Step 2: Aplicar no Supabase local**

Run: `cd hospital-reunioes && supabase db reset` (ou `supabase migration up` se preferir incremental)
Expected: sem erros, tabelas criadas, seeds populados.

- [ ] **Step 3: Validar manualmente**

Run:
```bash
psql "$SUPABASE_DB_URL" -c "SELECT count(*) FROM setores; SELECT count(*) FROM cargos; SELECT count(*) FROM tipos_reuniao;"
```
Expected: counts > 0, tipos_reuniao >= 5.

- [ ] **Step 4: Commit**

```bash
git add hospital-reunioes/supabase/migrations/027_create_taxonomy_tables.sql
git commit -m "feat(db): cria tabelas setores, cargos, tipos_reuniao com seed"
```

---

### Task 3: Migration 028 — FKs em participantes e reuniões (backfill)

**Files:**
- Create: `hospital-reunioes/supabase/migrations/028_add_taxonomy_fks.sql`

- [ ] **Step 1: Escrever migration**

```sql
-- 028_add_taxonomy_fks.sql
-- Adiciona FKs para as tabelas de taxonomia criadas em 027.
-- Mantém colunas TEXT antigas (setor, cargo, tipo) temporariamente para compat.

ALTER TABLE participantes
  ADD COLUMN IF NOT EXISTS setor_id UUID REFERENCES setores(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS cargo_id UUID REFERENCES cargos(id) ON DELETE SET NULL;

ALTER TABLE reunioes
  ADD COLUMN IF NOT EXISTS tipo_id UUID REFERENCES tipos_reuniao(id) ON DELETE SET NULL;

-- Backfill participantes.setor_id
UPDATE participantes p
SET setor_id = s.id
FROM setores s
WHERE p.setor IS NOT NULL
  AND lower(trim(p.setor)) = lower(s.nome)
  AND p.setor_id IS NULL;

-- Backfill participantes.cargo_id
UPDATE participantes p
SET cargo_id = c.id
FROM cargos c
WHERE p.cargo IS NOT NULL
  AND lower(trim(p.cargo)) = lower(c.nome)
  AND p.cargo_id IS NULL;

-- Backfill reunioes.tipo_id
UPDATE reunioes r
SET tipo_id = t.id
FROM tipos_reuniao t
WHERE r.tipo IS NOT NULL
  AND lower(trim(r.tipo)) = lower(t.nome)
  AND r.tipo_id IS NULL;

-- Verificação: reportar rows sem match (log via RAISE NOTICE)
DO $$
DECLARE
  setor_orfaos INT;
  cargo_orfaos INT;
  tipo_orfaos INT;
BEGIN
  SELECT COUNT(*) INTO setor_orfaos FROM participantes WHERE setor IS NOT NULL AND setor_id IS NULL;
  SELECT COUNT(*) INTO cargo_orfaos FROM participantes WHERE cargo IS NOT NULL AND cargo_id IS NULL;
  SELECT COUNT(*) INTO tipo_orfaos FROM reunioes WHERE tipo IS NOT NULL AND tipo_id IS NULL;
  RAISE NOTICE 'Backfill taxonomia: setor_orfaos=%, cargo_orfaos=%, tipo_orfaos=%', setor_orfaos, cargo_orfaos, tipo_orfaos;
END $$;

-- NÃO dropar colunas antigas ainda — Fase 3 fará isso após auditar referências no código.
```

- [ ] **Step 2: Aplicar migration**

Run: `cd hospital-reunioes && supabase db reset`
Expected: NOTICE final com orfaos=0 (ou explicação se algum valor não foi normalizado).

- [ ] **Step 3: Validar backfill com query**

```bash
psql "$SUPABASE_DB_URL" -c "
SELECT
  (SELECT COUNT(*) FROM participantes WHERE setor IS NOT NULL AND setor_id IS NULL) AS setor_sem_fk,
  (SELECT COUNT(*) FROM participantes WHERE cargo IS NOT NULL AND cargo_id IS NULL) AS cargo_sem_fk,
  (SELECT COUNT(*) FROM reunioes WHERE tipo IS NOT NULL AND tipo_id IS NULL) AS tipo_sem_fk;
"
```
Expected: todos zero.

- [ ] **Step 4: Commit**

```bash
git add hospital-reunioes/supabase/migrations/028_add_taxonomy_fks.sql
git commit -m "feat(db): adiciona FKs de setor/cargo/tipo e faz backfill"
```

---

### Task 4: Schemas Pydantic para taxonomia

**Files:**
- Modify: `hospital-reunioes/backend/app/models/admin_schemas.py`

- [ ] **Step 1: Adicionar schemas**

```python
# Adicionar ao final de admin_schemas.py
from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class TaxonomyItem(BaseModel):
    id: UUID
    nome: str
    ativo: bool
    created_at: datetime
    updated_at: datetime


class TaxonomyCreatePayload(BaseModel):
    nome: str = Field(min_length=1, max_length=200)


class TaxonomyUpdatePayload(BaseModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=200)
    ativo: Optional[bool] = None


class TaxonomyListResponse(BaseModel):
    data: list[TaxonomyItem]
    total: int
    page: int
    limit: int
```

- [ ] **Step 2: Commit**

```bash
git add hospital-reunioes/backend/app/models/admin_schemas.py
git commit -m "feat(admin): schemas Pydantic para taxonomia"
```

---

### Task 5: Router `/admin/setores` — testes + implementação

**Files:**
- Create: `hospital-reunioes/backend/app/routers/admin/taxonomia.py`
- Create: `hospital-reunioes/backend/tests/routers/admin/test_taxonomia_setores.py`
- Modify: `hospital-reunioes/backend/app/main.py` (registrar router)

- [ ] **Step 1: Escrever testes falhos**

```python
# test_taxonomia_setores.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_list_setores_super_admin(client: AsyncClient, super_admin_headers):
    r = await client.get('/api/admin/setores', headers=super_admin_headers)
    assert r.status_code == 200
    body = r.json()
    assert 'data' in body and 'total' in body

@pytest.mark.asyncio
async def test_list_setores_nao_autorizado(client: AsyncClient, user_headers):
    r = await client.get('/api/admin/setores', headers=user_headers)
    assert r.status_code == 403

@pytest.mark.asyncio
async def test_criar_setor(client: AsyncClient, super_admin_headers):
    r = await client.post('/api/admin/setores', json={'nome': 'Novo Setor'}, headers=super_admin_headers)
    assert r.status_code == 201
    assert r.json()['nome'] == 'Novo Setor'

@pytest.mark.asyncio
async def test_criar_setor_duplicado_case_insensitive(client: AsyncClient, super_admin_headers):
    await client.post('/api/admin/setores', json={'nome': 'Financeiro'}, headers=super_admin_headers)
    r = await client.post('/api/admin/setores', json={'nome': 'FINANCEIRO'}, headers=super_admin_headers)
    assert r.status_code == 409

@pytest.mark.asyncio
async def test_arquivar_setor(client: AsyncClient, super_admin_headers):
    created = await client.post('/api/admin/setores', json={'nome': 'Temp'}, headers=super_admin_headers)
    setor_id = created.json()['id']
    r = await client.delete(f'/api/admin/setores/{setor_id}', headers=super_admin_headers)
    assert r.status_code == 200
    assert r.json()['ativo'] is False
```

- [ ] **Step 2: Rodar testes — FAIL**

Run: `cd hospital-reunioes/backend && pytest tests/routers/admin/test_taxonomia_setores.py -v`
Expected: 5 FAIL com 404 ou ImportError.

- [ ] **Step 3: Implementar router**

```python
# hospital-reunioes/backend/app/routers/admin/taxonomia.py
from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID
from app.dependencies import require_super_admin, get_supabase_admin
from app.models.admin_schemas import (
    TaxonomyItem,
    TaxonomyCreatePayload,
    TaxonomyUpdatePayload,
    TaxonomyListResponse,
)
from app.services.audit import log_admin_action

router = APIRouter(prefix='/admin', tags=['admin-taxonomia'])


def _make_crud(table: str, audit_prefix: str):
    sub = APIRouter(prefix=f'/{table.replace("_", "-")}')

    @sub.get('', response_model=TaxonomyListResponse)
    async def list_items(
        q: str | None = Query(default=None),
        ativo: str = Query(default='todos'),
        page: int = Query(default=1, ge=1),
        limit: int = Query(default=50, le=200),
        current=Depends(require_super_admin),
        sb=Depends(get_supabase_admin),
    ):
        query = sb.table(table).select('*', count='exact')
        if q:
            query = query.ilike('nome', f'%{q}%')
        if ativo == 'ativos':
            query = query.eq('ativo', True)
        elif ativo == 'arquivados':
            query = query.eq('ativo', False)
        query = query.order('nome').range((page - 1) * limit, page * limit - 1)
        res = query.execute()
        return {'data': res.data, 'total': res.count or 0, 'page': page, 'limit': limit}

    @sub.post('', response_model=TaxonomyItem, status_code=201)
    async def create_item(
        payload: TaxonomyCreatePayload,
        current=Depends(require_super_admin),
        sb=Depends(get_supabase_admin),
    ):
        existing = sb.table(table).select('id').ilike('nome', payload.nome).execute()
        if existing.data:
            raise HTTPException(status_code=409, detail='Nome já existe (case-insensitive)')
        res = sb.table(table).insert({'nome': payload.nome.strip()}).execute()
        item = res.data[0]
        await log_admin_action(sb, current, f'{audit_prefix}_create', table, item['id'], {'nome': item['nome']})
        return item

    @sub.patch('/{item_id}', response_model=TaxonomyItem)
    async def update_item(
        item_id: UUID,
        payload: TaxonomyUpdatePayload,
        current=Depends(require_super_admin),
        sb=Depends(get_supabase_admin),
    ):
        updates = {k: v for k, v in payload.model_dump(exclude_unset=True).items()}
        if 'nome' in updates:
            dup = sb.table(table).select('id').ilike('nome', updates['nome']).neq('id', str(item_id)).execute()
            if dup.data:
                raise HTTPException(status_code=409, detail='Nome já existe')
        res = sb.table(table).update(updates).eq('id', str(item_id)).execute()
        if not res.data:
            raise HTTPException(status_code=404)
        await log_admin_action(sb, current, f'{audit_prefix}_update', table, str(item_id), updates)
        return res.data[0]

    @sub.delete('/{item_id}', response_model=TaxonomyItem)
    async def archive_item(
        item_id: UUID,
        current=Depends(require_super_admin),
        sb=Depends(get_supabase_admin),
    ):
        res = sb.table(table).update({'ativo': False}).eq('id', str(item_id)).execute()
        if not res.data:
            raise HTTPException(status_code=404)
        await log_admin_action(sb, current, f'{audit_prefix}_archive', table, str(item_id), {})
        return res.data[0]

    return sub


router.include_router(_make_crud('setores', 'setor'))
router.include_router(_make_crud('cargos', 'cargo'))
router.include_router(_make_crud('tipos_reuniao', 'tipo_reuniao'))
```

- [ ] **Step 4: Registrar router em main.py**

```python
# main.py
from app.routers.admin import taxonomia as admin_taxonomia
app.include_router(admin_taxonomia.router, prefix='/api')
```

- [ ] **Step 5: Rodar testes — PASS**

Run: `cd hospital-reunioes/backend && pytest tests/routers/admin/test_taxonomia_setores.py -v`
Expected: 5 PASS.

- [ ] **Step 6: Commit**

```bash
git add hospital-reunioes/backend/app/routers/admin/taxonomia.py \
  hospital-reunioes/backend/tests/routers/admin/test_taxonomia_setores.py \
  hospital-reunioes/backend/app/main.py
git commit -m "feat(admin): CRUD REST de setores/cargos/tipos-reuniao"
```

---

### Task 6: Testes para cargos e tipos de reunião (reutilizando estrutura)

- [ ] **Step 1: Duplicar o arquivo de teste de setores** para `test_taxonomia_cargos.py` e `test_taxonomia_tipos_reuniao.py`, substituindo `setores`/`Setor` pelos nomes corretos, trocando nomes de exemplo.

- [ ] **Step 2: Rodar**

Run: `cd hospital-reunioes/backend && pytest tests/routers/admin/test_taxonomia_ -v`
Expected: 15 PASS.

- [ ] **Step 3: Commit**

```bash
git add hospital-reunioes/backend/tests/routers/admin/
git commit -m "test(admin): cobertura de cargos e tipos_reuniao"
```

---

### Task 7: Tela `/admin/setores`

**Files:**
- Create: `hospital-reunioes/frontend/src/app/admin/setores/page.tsx`
- Create: `hospital-reunioes/frontend/src/components/admin/TaxonomyFormModal.tsx`
- Modify: `hospital-reunioes/frontend/src/components/admin/types.ts` (adicionar tipo `Setor`)

- [ ] **Step 1: Tipo**

```ts
// types.ts (append)
export type TaxonomyItem = {
  id: string;
  nome: string;
  ativo: boolean;
  created_at: string;
  updated_at: string;
};
```

- [ ] **Step 2: Modal genérico**

```tsx
// TaxonomyFormModal.tsx
'use client';
import { useState, useEffect } from 'react';
import type { TaxonomyItem } from './types';

type Props = {
  open: boolean;
  onClose: () => void;
  onSave: (payload: { nome: string; ativo?: boolean }) => Promise<void>;
  initial?: TaxonomyItem | null;
  title: string;
};

export function TaxonomyFormModal({ open, onClose, onSave, initial, title }: Props) {
  const [nome, setNome] = useState('');
  const [ativo, setAtivo] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setNome(initial?.nome ?? '');
      setAtivo(initial?.ativo ?? true);
      setError(null);
    }
  }, [open, initial]);

  if (!open) return null;

  async function submit() {
    setSaving(true); setError(null);
    try {
      await onSave(initial ? { nome, ativo } : { nome });
      onClose();
    } catch (e: any) {
      setError(e?.message ?? 'Erro ao salvar');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        <label>Nome
          <input value={nome} onChange={(e) => setNome(e.target.value)} autoFocus />
        </label>
        {initial && (
          <label>
            <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
            Ativo
          </label>
        )}
        {error && <p className="error">{error}</p>}
        <div className="modal__actions">
          <button onClick={onClose} disabled={saving}>Cancelar</button>
          <button onClick={submit} disabled={saving || !nome.trim()}>Salvar</button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Página**

```tsx
// frontend/src/app/admin/setores/page.tsx
'use client';
import { useEffect, useState, useCallback } from 'react';
import { DataTable } from '@/components/admin/DataTable';
import { TaxonomyFormModal } from '@/components/admin/TaxonomyFormModal';
import type { TaxonomyItem } from '@/components/admin/types';
import { toast } from '@/lib/toast';

export default function SetoresPage() {
  const [rows, setRows] = useState<TaxonomyItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const [ativo, setAtivo] = useState<'todos'|'ativos'|'arquivados'>('ativos');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<TaxonomyItem | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const params = new URLSearchParams({ page: String(page), limit: '50', ativo });
    if (q) params.set('q', q);
    const r = await fetch(`/api/admin/setores?${params}`);
    const body = await r.json();
    setRows(body.data); setTotal(body.total);
    setLoading(false);
  }, [page, q, ativo]);

  useEffect(() => { load(); }, [load]);

  async function handleSave(payload: any) {
    const url = editing ? `/api/admin/setores/${editing.id}` : '/api/admin/setores';
    const method = editing ? 'PATCH' : 'POST';
    const r = await fetch(url, { method, headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if (!r.ok) throw new Error((await r.json()).detail ?? 'Erro');
    toast.success(editing ? 'Setor atualizado' : 'Setor criado');
    await load();
  }

  async function archive(row: TaxonomyItem) {
    if (!confirm(`Arquivar "${row.nome}"?`)) return;
    const r = await fetch(`/api/admin/setores/${row.id}`, { method: 'DELETE' });
    if (!r.ok) { toast.error('Falha ao arquivar'); return; }
    toast.success('Setor arquivado');
    await load();
  }

  return (
    <div>
      <h1>Setores</h1>
      <DataTable
        columns={[
          { key: 'nome', header: 'Nome' },
          { key: 'ativo', header: 'Status', render: (r) => r.ativo ? 'Ativo' : 'Arquivado' },
          { key: 'updated_at', header: 'Atualizado', render: (r) => new Date(r.updated_at).toLocaleString('pt-BR') },
        ]}
        data={rows}
        loading={loading}
        emptyState={{ title: 'Nenhum setor encontrado', hint: 'Use "Novo setor" para criar o primeiro.' }}
        toolbar={
          <div className="toolbar">
            <input placeholder="Buscar..." value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            <select value={ativo} onChange={(e) => { setAtivo(e.target.value as any); setPage(1); }}>
              <option value="ativos">Ativos</option>
              <option value="arquivados">Arquivados</option>
              <option value="todos">Todos</option>
            </select>
            <button onClick={() => { setEditing(null); setModalOpen(true); }}>Novo setor</button>
          </div>
        }
        pagination={{ page, pageSize: 50, total, onPageChange: setPage }}
        onRowClick={(r) => { setEditing(r); setModalOpen(true); }}
        rowActions={(r) => r.ativo ? <button onClick={(e) => { e.stopPropagation(); archive(r); }}>Arquivar</button> : null}
      />
      <TaxonomyFormModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSave={handleSave}
        initial={editing}
        title={editing ? 'Editar setor' : 'Novo setor'}
      />
    </div>
  );
}
```

- [ ] **Step 4: Subir o stack local e testar manualmente**

Run: `/atualizar-app`
Validar: acessar `/admin/setores` como super-admin, criar setor, editar, arquivar, filtrar, paginar.

- [ ] **Step 5: Commit**

```bash
git add hospital-reunioes/frontend/src/app/admin/setores \
  hospital-reunioes/frontend/src/components/admin/TaxonomyFormModal.tsx \
  hospital-reunioes/frontend/src/components/admin/types.ts
git commit -m "feat(admin): tela /admin/setores com DataTable"
```

---

### Task 8: Tela `/admin/cargos`

- [ ] **Step 1: Duplicar estrutura de setores** para `frontend/src/app/admin/cargos/page.tsx`, trocando endpoints, labels e copy.

- [ ] **Step 2: Testar manualmente** via `/atualizar-app` e navegar para `/admin/cargos`.

- [ ] **Step 3: Commit**

```bash
git add hospital-reunioes/frontend/src/app/admin/cargos
git commit -m "feat(admin): tela /admin/cargos"
```

---

### Task 9: Tela `/admin/tipos-reuniao`

- [ ] **Step 1: Duplicar estrutura** para `frontend/src/app/admin/tipos-reuniao/page.tsx`.

- [ ] **Step 2: Testar manualmente**.

- [ ] **Step 3: Commit**

```bash
git add hospital-reunioes/frontend/src/app/admin/tipos-reuniao
git commit -m "feat(admin): tela /admin/tipos-reuniao"
```

---

### Task 10: Reorganizar `AdminSidebar` com seções

**Files:**
- Modify: `hospital-reunioes/frontend/src/components/admin/AdminSidebar.tsx`

- [ ] **Step 1: Refatorar componente**

```tsx
const SECTIONS: { label: string; items: { href: string; label: string }[] }[] = [
  {
    label: 'PESSOAS',
    items: [
      { href: '/admin/usuarios', label: 'Usuários' },
      { href: '/admin/super-admins', label: 'Super Admins' }, // removido em Fase 2
    ],
  },
  {
    label: 'TAXONOMIA',
    items: [
      { href: '/admin/setores', label: 'Setores' },
      { href: '/admin/cargos', label: 'Cargos' },
      { href: '/admin/tipos-reuniao', label: 'Tipos de Reunião' },
    ],
  },
  {
    label: 'OPERAÇÕES',
    items: [
      { href: '/admin/bulk', label: 'Ações em Massa' },
    ],
  },
  {
    label: 'AUDITORIA',
    items: [
      { href: '/admin/logs', label: 'Logs' },
    ],
  },
];
```

Renderizar cada seção com cabeçalho (uppercase, gray) + lista de itens com estado ativo por `usePathname()`.

- [ ] **Step 2: Testar manualmente** — navegação entre todas as 7 rotas com estado ativo correto.

- [ ] **Step 3: Commit**

```bash
git add hospital-reunioes/frontend/src/components/admin/AdminSidebar.tsx
git commit -m "feat(admin): sidebar agrupada por seções"
```

---

### Task 11: Atualizar endpoint de setores/cargos de autocomplete para usar tabelas novas

**Files:**
- Modify: `hospital-reunioes/backend/app/routers/admin/usuarios.py` (endpoint `GET /admin/usuarios/setores`)

- [ ] **Step 1: Teste falho — verificar que setores vêm da tabela `setores` e não de distinct**

```python
# adicionar a test_usuarios.py
async def test_setores_endpoint_vem_da_tabela(client, super_admin_headers, sb):
    sb.table('setores').insert({'nome': 'Setor-Exclusivo-Para-Teste'}).execute()
    r = await client.get('/api/admin/usuarios/setores', headers=super_admin_headers)
    assert 'Setor-Exclusivo-Para-Teste' in r.json()
```

- [ ] **Step 2: Rodar teste — FAIL**

Expected: FAIL (endpoint ainda faz `SELECT DISTINCT setor FROM participantes`).

- [ ] **Step 3: Atualizar endpoint**

Trocar `SELECT DISTINCT setor FROM participantes` por `SELECT nome FROM setores WHERE ativo = true ORDER BY nome`. Adicionar endpoint irmão para cargos.

- [ ] **Step 4: Rodar teste — PASS**

- [ ] **Step 5: Commit**

```bash
git add hospital-reunioes/backend/app/routers/admin/usuarios.py hospital-reunioes/backend/tests/routers/admin/test_usuarios.py
git commit -m "refactor(admin): setores/cargos autocomplete da tabela canônica"
```

---

### Task 12: Form de usuário usa `setor_id` e `cargo_id` (mantém escrita em TEXT por compat)

**Files:**
- Modify: `hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx`
- Modify: `hospital-reunioes/backend/app/routers/admin/usuarios.py`

- [ ] **Step 1: Frontend — trocar input de setor para select populado de `/api/admin/setores?ativo=ativos`**, idem cargo. Valor do select = `nome` (continua enviando string; backend resolve FK).

- [ ] **Step 2: Backend** — ao receber POST/PATCH de usuário com `setor`, fazer lookup case-insensitive em `setores` e gravar `setor_id` junto com `setor` (TEXT). Se não achar, criar automaticamente? **Não** — retornar 422 "Setor não cadastrado. Crie em /admin/setores antes." Idem cargo.

- [ ] **Step 3: Testes** cobrindo: criar usuário com setor válido preenche `setor_id`, criar usuário com setor inexistente retorna 422, editar muda `setor_id`.

- [ ] **Step 4: Testar manualmente** via `/atualizar-app`: editar um usuário existente, mudar setor, verificar que linha no DB tem `setor_id` preenchido.

- [ ] **Step 5: Commit**

```bash
git add hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx \
  hospital-reunioes/backend/app/routers/admin/usuarios.py \
  hospital-reunioes/backend/tests/routers/admin/test_usuarios.py
git commit -m "feat(admin): form de usuário usa select de setor/cargo da taxonomia"
```

---

## Verificação — Fase 1 (end-to-end)

Após concluir todas as tasks:

1. **Reset DB e migrar do zero**:
   ```bash
   cd hospital-reunioes && supabase db reset
   ```
   Esperado: migrations 027 e 028 aplicam sem erro. `RAISE NOTICE` de backfill reporta zero órfãos.

2. **Rodar suíte de testes completa**:
   ```bash
   cd hospital-reunioes/backend && pytest
   cd hospital-reunioes/frontend && npm test
   ```
   Esperado: 0 falhas.

3. **Subir stack local**:
   ```bash
   /atualizar-app
   ```
   Acessar `http://localhost:3000/admin` como super-admin.

4. **Checklist de validação manual**:
   - [ ] Sidebar mostra 4 seções (Pessoas, Taxonomia, Operações, Auditoria) com cabeçalhos em maiúsculas.
   - [ ] `/admin/setores` lista setores existentes (populados pelo seed).
   - [ ] Criar novo setor "Pediatria" → aparece na lista → aparece no select do form de usuário.
   - [ ] Tentar criar setor "PEDIATRIA" → 409 "Nome já existe".
   - [ ] Editar setor → muda nome → reflete na lista.
   - [ ] Arquivar setor → desaparece do filtro "ativos", aparece em "arquivados".
   - [ ] Mesma validação em `/admin/cargos` e `/admin/tipos-reuniao`.
   - [ ] Editar um usuário existente: select de setor carrega da tabela, escolher outro setor → salvar → `psql` confirma que `setor_id` foi atualizado.
   - [ ] Verificar `audit_log`: entradas `setor_create`, `setor_archive`, `cargo_create`, `tipo_reuniao_create` aparecem.

5. **Smoke das telas legadas** (regressão):
   - [ ] `/admin/usuarios` ainda lista, filtra, cria, edita, deleta.
   - [ ] `/admin/super-admins` ainda funciona (remoção vem na Fase 2).
   - [ ] `/admin/logs` ainda filtra e exporta CSV.
   - [ ] `/admin/bulk` ainda processa jobs (sem regressão nos 3 tipos).

6. **Sincronizar blueprint**: o hook post-commit deve rodar `/blueprint-sync` automaticamente; verificar que `blueprint/ARQUITETURA.md` reconhece as tabelas novas. Se não, invocar manualmente.

## Rollback

Se a migration 028 falhar em produção:
- `supabase db reset` em dev não é reversível trivialmente; desenvolver e testar localmente primeiro.
- Em prod, ter migration reversa pronta: `DROP COLUMN setor_id, cargo_id, tipo_id`. As colunas TEXT originais continuam válidas, então nenhum dado operacional é perdido.

## Arquivos críticos a conhecer antes de começar

- `hospital-reunioes/supabase/migrations/` — ver numeração atual (última é 026) e padrão de naming.
- `hospital-reunioes/backend/app/dependencies.py` — `require_super_admin` e `get_supabase_admin`.
- `hospital-reunioes/backend/app/routers/admin/usuarios.py` — padrão de router admin existente (copiar estilo).
- `hospital-reunioes/backend/app/services/audit.py` (se existir — senão criar com `log_admin_action`).
- `hospital-reunioes/frontend/src/app/admin/layout.tsx` — gate de super-admin.
- `hospital-reunioes/frontend/src/components/admin/AdminSidebar.tsx` — componente atual, 4 itens flat.
- `hospital-reunioes/frontend/src/components/admin/types.ts` — tipos compartilhados.

## Observação final sobre o local deste plano

O plano foi salvo em `~/.claude/plans/` por exigência do plan mode. Ao sair do plan mode e iniciar execução, **mover para a raiz do projeto** como `plano-superadmin-crud.md` conforme regra do CLAUDE.md do projeto, e commitar — mantém o plano versionado junto do código e visível em VS Code/GitHub.
