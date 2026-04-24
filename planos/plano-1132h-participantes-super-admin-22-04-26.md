# Plano — Mover gestão de participantes para exclusivo de super admin + corrigir 500

> Nota de escopo: pelo `CLAUDE.md` do projeto, planos devem viver como `.md` na raiz do repo. O plan mode só permite editar este arquivo enquanto a revisão está em curso; após aprovação, ele será copiado para `/Users/pedrorezende/PedroDev/Hospital/plano-participantes-super-admin.md` e este arquivo em `.claude/plans/` fica apenas como rastro da revisão.

## Contexto

Na tela `/admin/usuarios` (print enviado), o backend está respondendo **HTTP 500** com
`ResponseValidationError: 12 validation errors` — todos apontando para campos tipo `string_type` vindo `None` (primeiro erro é `('response', 0, 'email')`). O schema Pydantic exige `email: str`, mas existem participantes no banco (externos, criados a partir de ATAs, sem email real) com `email = NULL`. Resultado: a lista inteira falha e o admin vê zero usuários.

Ao mesmo tempo, o produto hoje tem **duas telas** para a mesma responsabilidade:

- `/participantes` — aberta a qualquer usuário logado, permite ver, criar e desativar participantes (`/src/app/participantes/page.tsx`). Nenhum filtro, sem controle de acesso.
- `/admin/usuarios` — só super admin, completo: filtros, CRUD, reset de senha, promoção/revogação, auditoria, resolver externos, etc. (`/src/app/admin/usuarios/page.tsx`).

O usuário quer:

1. **Corrigir** a 500 do `/admin/usuarios` (causa: `email` nulo em externos).
2. **Remover** o item "Participantes" do menu lateral.
3. **Remover** a página pública `/participantes`.
4. Deixar a gestão de participantes (internos **e** externos) **exclusiva do super admin** via `/admin/usuarios`.

Bom saber para escopar:
- Infra de super admin já está pronta (flag `is_super_admin`, dependency `require_super_admin`, `admin/layout.tsx` com redirect silencioso — ver memória `feedback_agent_git_safety.md`, Fase 04).
- `/admin/usuarios` **já contempla tudo** que a página `/participantes` fazia (criar via `AdminUsuarioCreate`, editar, deletar, listar incluindo externos com filtro `is_externo`).
- O endpoint **`GET /api/participantes`** é usado em pelo menos 8 lugares como fonte de dropdowns (`dashboard`, `pendencias`, `pendencias/kanban`, `reunioes/[id]`, `reunioes/calendario`, `reunioes/importar`, `admin/bulk`, `configuracoes/UsersSection`) — **não pode ser removido**, apenas a UI `/participantes`.

---

## Arquivos críticos a alterar

### Backend
- `hospital-reunioes/backend/app/models/admin_schemas.py:137-155` — schema `AdminUsuarioResponse`.

### Frontend
- `hospital-reunioes/frontend/src/components/layout/Sidebar.tsx:50` — item "Participantes".
- `hospital-reunioes/frontend/src/app/participantes/page.tsx` — página a deletar (pasta inteira `src/app/participantes/`).
- `hospital-reunioes/frontend/src/middleware.ts:51,70` — `protectedPaths` e `matcher`.
- `hospital-reunioes/frontend/src/components/configuracoes/UsersSection.tsx:84` — botão que apontava para `/participantes`.

---

## Fase 1 — Fix do 500 em `GET /admin/usuarios`

### O que fazer

Tornar os campos que podem estar nulos no banco `Optional` no `AdminUsuarioResponse`.

Da análise do erro (`12 validation errors`, começando por `email`) e do schema atual, o único campo realmente obrigatório que o Postgres retorna como `NULL` é **`email`**. `nome_completo` é `NOT NULL` em migrations. Ainda assim, para robustez e evitar a próxima 500 do mesmo tipo, também tornar `nome_completo` tolerante.

**Edit em `admin_schemas.py:144-146`**:

```python
# antes
id: str
nome_completo: str
email: str

# depois
id: str
nome_completo: Optional[str] = None
email: Optional[str] = None
```

Os demais campos (`cargo`, `area`, `setor`, `role`, `auth_user_id`, `data_cadastro`) já são `Optional`. `ativo`, `is_externo`, `is_super_admin` têm default `bool`, ok.

### Reflexo no frontend

A tipagem `AdminUsuario` em `src/app/admin/usuarios/page.tsx` já trata `email` como campo exibível que pode estar vazio (a tabela mostra `—` se faltar) — verificar linha onde renderiza `email` e, se necessário, fazer fallback `{u.email ?? "—"}`. Mesmo para `nome_completo` — conferir o render e adicionar fallback.

### Por que não filtrar `email IS NOT NULL` no query?

Seria esconder externos do painel que foi feito justamente para gerenciá-los. `/admin/usuarios` é a tela certa para "resolver externo" (promover/mesclar), então ela precisa listar exatamente esses registros.

### Verificação

- Com o usuário logado como super admin (ex: `pmrdef@gmail.com`), abrir `/admin/usuarios` → deve listar todos os participantes, inclusive externos sem email.
- Filtro "Tipo: Externos" deve voltar pelo menos os 12 registros que hoje quebram a resposta.
- Colunas `Email` e `Nome` devem mostrar `—` (ou vazio) para registros sem valor.

---

## Fase 2 — Remover "Participantes" do menu e da navegação pública

### 2.1 Remover item do Sidebar

**Edit em `src/components/layout/Sidebar.tsx:50`**: remover a linha

```tsx
{ href: "/participantes", label: "Participantes", icon: Users },
```

E remover `Users` do import `lucide-react` (linha 11) se não for usado em outro lugar do arquivo. Conferir antes — pelo que vi no arquivo, `Users` só aparece como ícone desse item.

### 2.2 Deletar a página pública `/participantes`

- `rm -rf hospital-reunioes/frontend/src/app/participantes/` (pasta com `page.tsx` e, se existir, arquivos auxiliares).
- Next.js vai servir 404 nativo para quem acessar `/participantes` direto. Como a rota some do menu, isso é o comportamento desejado.

### 2.3 Tirar `/participantes` do middleware

**Edit em `src/middleware.ts:51`** — remover da lista `protectedPaths`:
```ts
const protectedPaths = ["/dashboard", "/reunioes", "/pendencias", "/perfil", "/configuracoes", "/admin"];
```

**Edit em `src/middleware.ts:70`** — remover `"/participantes/:path*"` do array de matcher.

Sem isso, o middleware continua tentando proteger uma rota que não existe mais (não quebra, mas vira lixo).

### 2.4 Corrigir botão em `UsersSection.tsx`

**Edit em `src/components/configuracoes/UsersSection.tsx:84`**:
- Trocar `router.push("/participantes")` por `router.push("/admin/usuarios")`.
- **Porém**, `UsersSection` é renderizado em `/configuracoes` para qualquer usuário — redirecionar não-super-admin para `/admin/usuarios` resulta em redirect silencioso para `/dashboard` (o guard do admin layout). Feio.
- **Solução**: esconder o botão para quem não é super admin usando `useCurrentParticipante()` + `isSuperAdmin()`. Se o componente já for só para super admin, ajustar; se não, condicionar o render do botão.

Ler primeiro o componente inteiro para ver o contexto antes de decidir entre esconder botão vs esconder seção inteira.

### Verificação

- Logado como facilitador (não super admin):
  - Sidebar **não** mostra "Participantes".
  - `/participantes` retorna 404.
  - `/configuracoes` não mostra botão/seção que leve a gestão de usuários.
- Logado como super admin:
  - `/admin/usuarios` acessível e funcional (Fase 1 aplicada).
  - Se `UsersSection` tem botão, ele aponta para `/admin/usuarios`.

---

## Fase 3 — (opcional, decidir) Proteger mutações em `/api/participantes`

Depois da Fase 2, os únicos consumidores de `POST /api/participantes` e `DELETE /api/participantes/{id}` eram:
- a própria página `/participantes` (**deletada**)
- o fluxo `reunioes/importar` que cria participantes no ato da importação de ATA (já restrito a super admin no frontend)

`GET /api/participantes` continua essencial (dropdowns de autocomplete em toda a aplicação).

**Proposta**: adicionar `Depends(require_super_admin)` em `POST` e `DELETE` de `/api/participantes` (router público) para fechar a superfície de ataque. Isso **não é pré-requisito** para o pedido do usuário — é higiene.

**Risco**: se algum fluxo interno (ex: criação de externo via ATA) depende de `POST /api/participantes` **sem** estar no contexto de um super admin, quebra. Precisa checar caso a caso antes de mexer.

**Recomendação**: deixar Fase 3 como follow-up separado, não entregar no mesmo PR. Marcar como pendência pós-auditoria (memória `project_pendencias_pos_audit.md`).

---

## Ordem de execução sugerida

1. **Fase 1** primeiro (fix do 500) — é bug, independe do resto e destrava o admin. 1 edit, 2 linhas.
2. **Fase 2.1** e **2.3** (Sidebar + middleware) — remove o item visível e a proteção morta.
3. **Fase 2.2** (deletar pasta `/participantes`) — só depois de 2.1 para evitar navegar e ver 404 no meio da limpeza.
4. **Fase 2.4** (UsersSection) — ler o componente, decidir entre esconder o botão ou a seção, aplicar.
5. Subir local via `/atualizar-app` (docker compose), testar manualmente.
6. Commit único: `refactor(participantes): remove menu publico, fixa 500 em /admin/usuarios, gestao exclusiva super admin`.

Fase 3 fica para depois, com PR próprio se decidido.

---

## Verificação end-to-end

Executar após aplicar Fases 1 e 2:

1. **Local**: `/atualizar-app` (rebuilda docker compose com código atual).
2. **Como super admin** (`pmrdef@gmail.com`):
   - Sidebar não mostra "Participantes" (mostra "Admin" no lugar).
   - `/admin/usuarios` carrega lista completa, inclui externos sem email (colunas com `—`).
   - Criar/editar/deletar funciona.
3. **Como facilitador comum**:
   - Sidebar sem "Participantes" e sem "Admin".
   - Acesso direto a `/participantes` → 404.
   - Acesso direto a `/admin/usuarios` → redirect silencioso para `/dashboard`.
   - Dropdowns de participantes em pendências, reuniões, dashboard continuam populando (comprova `GET /api/participantes` ainda funcional).
4. **Logs backend**: nenhum `ResponseValidationError` em `admin/usuarios` nos logs do container.

---

## Resumo de impacto

- **1 edit** no backend (schema Pydantic, 2 campos Optional).
- **1 remove + 1 edit** no Sidebar.
- **1 pasta deletada** em `src/app/participantes/`.
- **2 edits** no middleware.
- **1 edit** em `UsersSection.tsx`.
- Nenhuma migration, nenhum novo endpoint, nenhuma nova dependência.
