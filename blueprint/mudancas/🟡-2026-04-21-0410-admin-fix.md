# Plano — Fix `/admin` + Padronização de Modais

## Context

No menu admin do Hospital Reuniões (Next.js 15 + React 19 + Tailwind 4 + FastAPI + Supabase) há dois problemas visíveis e uma oportunidade maior:

1. **`/admin/usuarios` mostra "Nenhum usuário encontrado"** mesmo logado como super_admin. A tela funde quatro cenários distintos (200 vazio, 401, 403, 5xx) num único empty state, então não dá pra saber se é banco sem dados, token expirado, permissão, ou erro de servidor.
2. **Modal "Editar setor" aparece afundado na parte de baixo da tela** (captura do usuário), sem backdrop escuro visível, sem animação de entrada. Causa raiz técnica: `TaxonomyFormModal` renderiza *inline* no fluxo da página sem `createPortal`, e `.modal-backdrop` em `globals.css` não tem `background-color` (só `backdrop-filter: blur(4px)`). Qualquer ancestor com `transform`/`filter` quebra o `position: fixed` e o modal "afunda" dentro do container.
3. **Inconsistência generalizada de modais no admin**: existem 7 implementações divergentes (5 em `components/admin/*Modal.tsx` + 2 inline em `app/admin/{reunioes,pendencias}/page.tsx`), nenhuma usa Portal, nenhuma tem animação. Apenas `PendenciaDetailModal` (fora do admin) faz tudo certo — é o padrão de referência que vamos replicar.

**Outcome alvo:** Menu admin com UX consistente (modais centralizados, com backdrop escuro + blur, animação `scale-in` suave, ESC/click-out funcionam) e tela de usuários diagnóstica (erros explícitos em vez de silencioso-vazio), validado no navegador.

---

## Frente B: `<AdminModal>` unificado (fazer PRIMEIRO, é pré-requisito dos refactors)

### B.1 Adicionar keyframes em `hospital-reunioes/frontend/src/app/globals.css`

Inserir logo após `.animate-fade-in-right` (linha ~97):

```css
/* ─── Modal animations ─────────────────────────────────────────────── */
@keyframes fade-in {
  from { opacity: 0; }
  to   { opacity: 1; }
}
.animate-fade-in {
  animation: fade-in 0.2s ease-out both;
}

@keyframes scale-in {
  from { opacity: 0; transform: scale(0.96) translateY(4px); }
  to   { opacity: 1; transform: scale(1)    translateY(0); }
}
.animate-scale-in {
  animation: scale-in 0.22s cubic-bezier(0.16, 1, 0.3, 1) both;
}
```

Estender o bloco `@media (prefers-reduced-motion: reduce)` (linha ~106) para listar as novas classes explicitamente (além do wildcard existente).

### B.2 Criar `hospital-reunioes/frontend/src/components/admin/AdminModal.tsx`

Componente cliente padronizado. Arquitetura:

- `createPortal(jsx, document.body)` — imune a `transform`/`filter` em ancestors.
- Duas camadas: backdrop (`fixed inset-0 bg-black/40 backdrop-blur-[2px] z-[200] animate-fade-in`) + container (`fixed inset-0 z-[210] flex items-center justify-center p-4 pointer-events-none`) + conteúdo (`pointer-events-auto animate-scale-in`, com `stopPropagation` no click).
- Acessibilidade: `role="dialog"`, `aria-modal`, `aria-labelledby`/`aria-describedby` via `useId()` (React 19), focus inicial no primeiro input após 50ms.
- Comportamento: ESC fecha (opcional via prop), click backdrop fecha (opcional via prop), body scroll-lock via **contador em módulo** (suporta múltiplos modais abertos em cascata).
- Header padronizado: ícone opcional + título + description opcional + botão X.
- `scrollable={true}` → conteúdo usa `max-h-[90vh] overflow-hidden flex flex-col` com body `overflow-auto`.
- Footer opcional via prop (recebe JSX livre).

**Interface TypeScript:**
```typescript
interface AdminModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  icon?: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl";          // max-w-sm | md | 2xl | 5xl
  scrollable?: boolean;
  footer?: React.ReactNode;
  children: React.ReactNode;
  closeOnBackdrop?: boolean;                   // default true
  closeOnEsc?: boolean;                        // default true
}
```

**Contrato de submit para forms:** consumidor envolve children em `<form id="xxx" onSubmit={...}>` e footer usa `<button type="submit" form="xxx">`. Padrão HTML — permite footer fora do form mantendo submit funcional.

### B.3 Refactor dos 7 modais (ordem simples → complexo)

Cada um perde: `<div className="modal-backdrop ...">` wrapper, botão X manual, header manual. Cada um ganha: `<AdminModal open onClose title footer>`.

1. **`components/admin/TaxonomyFormModal.tsx`** — `size="md"`, simples. Smoke test do AdminModal.
2. **`components/admin/NewPasswordModal.tsx`** — `size="md"`, sem form, ícone `KeyRound`.
3. **`components/admin/ReasonModal.tsx`** — `size="md"`, ícone `AlertTriangle`, description já existe na prop.
4. **`components/admin/UsuarioFormModal.tsx`** — `size="lg"`, `scrollable=true`. Remover `max-h-[90vh] overflow-hidden flex flex-col` antigo (vira responsabilidade do AdminModal). Manter `<style jsx>` com `.input` inline.
5. **`components/admin/ResolverExternoModal.tsx`** — `size="lg"`, `scrollable=true`. Tabs ficam no children; cada tab tem form próprio com botão de submit interno → footer do AdminModal fica `undefined` (menos cirurgia, preserva UX atual).
6. **Extract novo** `components/admin/ReuniaoEditModal.tsx` a partir das linhas 332-539 de `app/admin/reunioes/page.tsx`. `size="lg"`, `scrollable=true`. Preservar lógica de `BLOCKED_WHEN_SIGNED` e dirty-diff.
7. **Extract novo** `components/admin/PendenciaEditModal.tsx` a partir das linhas 331-546 de `app/admin/pendencias/page.tsx`. `size="lg"`, `scrollable=true`.

`PendenciaDetailModal` (fora do admin) **não é tocado** — já funciona corretamente, só tem leve divergência de timing nas keyframes (`0.3s` local vs `0.22s` global). Limpeza futura.

---

## Frente A: Fix "Nenhum usuário encontrado" em `/admin/usuarios/page.tsx`

### A.1 Melhorias no tratamento de erro (independem do diagnóstico)

Arquivo: `hospital-reunioes/frontend/src/app/admin/usuarios/page.tsx`.

**Novo estado tipado:**
```typescript
type FetchError =
  | { kind: "unauthorized" }                              // 401
  | { kind: "forbidden" }                                 // 403
  | { kind: "server"; status: number; message: string }   // outros 4xx/5xx
  | { kind: "network"; message: string };                 // fetch throw
```

**Reescrever `fetchRows` (linhas 69-94):**
- Ler body como texto primeiro (`const raw = await res.text()`).
- `console.error("[admin/usuarios]", { status, url, body: raw.slice(0, 500) })` em todo `!res.ok`.
- Switch por status → setar `error` tipado, manter `rows=[]`.
- Try/catch só para erros de rede.
- Em sucesso: `console.debug("[admin/usuarios] fetch", { status, count, filters })`.

**UI — substituir bloco ternário em `rows.length === 0` (linhas 355-363):**
- `error.kind === "unauthorized"` → banner vermelho "Sessão expirada" + botão "Fazer login" (chama `supabase.auth.signOut()` + `router.push("/login")`).
- `error.kind === "forbidden"` → banner âmbar "Acesso negado. Sua conta não tem permissão de super admin."
- `error.kind === "server"` → banner vermelho com `status` + mensagem truncada (200 chars) + botão "Tentar novamente" (chama `fetchRows()`) + `<details>` com body cru.
- `error.kind === "network"` → "Sem conexão com o servidor" + retry.
- `error === null && rows.length === 0` → mantém empty state atual.

**Fora do escopo desta fase:** replicar o mesmo shape em `/admin/reunioes`, `/admin/pendencias`, `TaxonomyPage`. Anotar como follow-up.

### A.2 Diagnóstico runtime (após deploy local)

Executar em ordem, parar no primeiro que revelar a causa:

1. **Banco real.** Preciso do nome do container Postgres — `docker ps | grep supabase`. Depois:
   ```bash
   docker exec <container_postgres> psql -U postgres -d postgres -c "
   SELECT COUNT(*) FILTER (WHERE ativo) AS ativos,
          COUNT(*) FILTER (WHERE is_super_admin) AS super_admins
   FROM participantes;"
   
   docker exec <container_postgres> psql -U postgres -d postgres -c "
   SELECT id, nome_completo, email, is_super_admin, ativo, deleted_at
   FROM participantes WHERE lower(email)='pmrdef@gmail.com';"
   ```
2. **Endpoint direto.** Copiar Bearer token do DevTools → Network:
   ```bash
   curl -s -i -H "Authorization: Bearer $TOKEN" \
     "http://localhost:8000/api/admin/usuarios?limit=50&offset=0"
   ```
3. **Logs backend** se passos 1-2 inconclusivos:
   ```bash
   docker compose -f hospital-reunioes/docker-compose.yml logs backend --tail 100 | grep -iE "admin.usuarios|403|500"
   ```

**Contingências operacionais por resultado:**

| Sintoma | Ação |
|---|---|
| Só 2 participantes no banco | `docker compose exec backend python -m scripts.bulk_seed` (popula 40 facilitadores) |
| Flag `is_super_admin=false` para pmrdef | UPDATE manual ou reaplicar migration 017 |
| 401 consistente | usuário relogar; verificar client Supabase local (porta 54351) |
| 403 apesar de layout ter liberado | investigar `get_participante_for_user` resolvendo 2 registros (auth_user_id vs email) |
| 500 | stack trace no log direciona |
| Banco + endpoint OK via curl | bug de rendering/filtro client — a nova UI tipada vai revelar |

A nova UI de erro (A.1) é rede de segurança: se o diagnóstico não encontrar nada, o próximo uso da tela já mostra a causa real.

---

## Ordem de execução (série, commits isolados)

1. `globals.css` — keyframes `fade-in` + `scale-in` + reduced-motion expandido. **Commit: `feat(admin): adiciona keyframes de modal (fade-in + scale-in)`**
2. `components/admin/AdminModal.tsx` — componente novo, zero consumidores. **Commit: `feat(admin): adiciona componente AdminModal unificado com portal e animações`**
3. Refactor `TaxonomyFormModal` (smoke test). **Commit: `refactor(admin): migra TaxonomyFormModal para AdminModal`**
4. Refactor `NewPasswordModal`. **Commit separado.**
5. Refactor `ReasonModal`. **Commit separado.**
6. Refactor `UsuarioFormModal` (scrollable). **Commit separado.**
7. Refactor `ResolverExternoModal` (tabs). **Commit separado.**
8. Extract + migrate `ReuniaoEditModal`. **Commit separado.**
9. Extract + migrate `PendenciaEditModal`. **Commit separado.**
10. Frente A — `/admin/usuarios/page.tsx` erro tipado + banners. **Commit: `feat(admin): tratamento granular de erros na tela de usuários`**
11. `/atualizar-app` (rebuild stack). Aguardar subida.
12. Diagnóstico runtime Frente A (SQL + curl + logs).
13. Aplicar contingência identificada (bulk_seed / UPDATE flag / etc).
14. Teste manual no navegador (checklist abaixo).

Cada commit passa por `.githooks/post-commit` que reroda `/blueprint-sync`.

---

## Verificação (teste manual no navegador)

Após `/atualizar-app`:

**Modais (Frente B):**
- [ ] `/admin/setores` → Novo / Editar: modal centralizado, backdrop escurece, animação scale-in suave, ESC fecha, click-out fecha.
- [ ] `/admin/cargos` → idem.
- [ ] `/admin/tipos-reuniao` → idem.
- [ ] `/admin/usuarios` → Novo, Editar (scroll interno com form grande), Deletar (Reason danger), Resetar senha (Reason warning → NewPassword), Tornar super (Reason primary), Revogar super (Reason danger), Resolver externo (tabs internas).
- [ ] `/admin/reunioes` → Editar (com ata ASSINADA: campos core bloqueados), Arquivar, Restaurar.
- [ ] `/admin/pendencias` → Editar, Arquivar, Restaurar.
- [ ] Em cada: scroll do body travado atrás do modal, restaura ao fechar.
- [ ] Mobile (DevTools 360×640): modal ocupa viewport com padding, scroll interno funcional.
- [ ] Reduced motion (DevTools → Rendering): modal aparece instantâneo sem animação.
- [ ] Foco inicial vai para primeiro input/textarea ao abrir.

**Usuários (Frente A):**
- [ ] Console mostra `[admin/usuarios] fetch {status, count, filters}` em cada carga.
- [ ] Desligar backend → banner "Sem conexão" + retry.
- [ ] Token expirado (editar cookie/localStorage) → banner "Sessão expirada" + botão login.
- [ ] Revogar flag super_admin no banco e recarregar → banner "Acesso negado".
- [ ] Com banco vazio de filtros → empty state "Nenhum usuário encontrado".
- [ ] Com banco populado (após bulk_seed se necessário) → lista aparece com paginação funcional.

---

## Critical Files

**Modificados/criados nesta fase:**
- `hospital-reunioes/frontend/src/app/globals.css` (keyframes)
- `hospital-reunioes/frontend/src/components/admin/AdminModal.tsx` (**novo**)
- `hospital-reunioes/frontend/src/components/admin/TaxonomyFormModal.tsx` (refactor)
- `hospital-reunioes/frontend/src/components/admin/NewPasswordModal.tsx` (refactor)
- `hospital-reunioes/frontend/src/components/admin/ReasonModal.tsx` (refactor)
- `hospital-reunioes/frontend/src/components/admin/UsuarioFormModal.tsx` (refactor)
- `hospital-reunioes/frontend/src/components/admin/ResolverExternoModal.tsx` (refactor)
- `hospital-reunioes/frontend/src/components/admin/ReuniaoEditModal.tsx` (**novo**, extraído)
- `hospital-reunioes/frontend/src/components/admin/PendenciaEditModal.tsx` (**novo**, extraído)
- `hospital-reunioes/frontend/src/app/admin/reunioes/page.tsx` (remove inline, importa novo)
- `hospital-reunioes/frontend/src/app/admin/pendencias/page.tsx` (remove inline, importa novo)
- `hospital-reunioes/frontend/src/app/admin/usuarios/page.tsx` (erro tipado + banners)

**Intocados:**
- `hospital-reunioes/frontend/src/components/pendencias/PendenciaDetailModal.tsx` (já é padrão ouro, não usa AdminModal só para evitar regressão no kanban de pendências).
- Backend `routers/admin/usuarios.py` — ainda não há evidência de bug lá; se o diagnóstico revelar, será fase separada.

---

## Riscos

1. **Conflito de keyframes** com `PendenciaDetailModal` (declara `fade-in`/`scale-in` inline via `<style jsx global>`). Timing diverge levemente (0.3s vs 0.22s). Comportamento final aceitável — alinhamento futuro.
2. **Body scroll-lock multi-modal** — contador em módulo é mandatório, senão unmount de um modal libera o lock do outro.
3. **`form` attribute em button** — funciona em browsers modernos, mas testar cross-modal.
4. **ResolverExternoModal com 2 forms aninhados** — decisão: footer=undefined, submit dentro de cada tab. Não tentar padronizar agora.
5. **Z-index** — confirmar que Toast fica acima (usualmente 250+); se não, ajustar.
6. **Diagnóstico Frente A pode dar "tudo OK"** — nesse caso o bug é mais profundo (rewrite Next? CORS? resolução de participante por auth_user_id vs email?). A nova UI de erro vai revelar no próximo refresh.

---

## Decisões fechadas (não mexer)

- **Sem lib de modal** (Radix/Headless/Framer). CSS puro + `createPortal` nativo.
- **Sem focus trap completo** na v1 (só focus inicial). ESC + click-out cobrem 95% dos casos.
- **Sem animação de saída** na v1 (unmount imediato). Evita timers de unmount problemáticos.
- **Sem padronização de tabelas/paginação/filtros** agora (escopo contido só nos modais + usuários).
- **Plano será copiado para raiz do projeto** (`plano-admin-fix.md`) no início da execução, conforme CLAUDE.md do projeto.
