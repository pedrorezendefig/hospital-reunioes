# Plano: Auditoria de tipagem TypeScript do frontend

## Plano

### Contexto

Auditoria solicitada para mapear fraquezas no sistema de tipos do frontend (Next.js 15 + React 19 + TS strict) do Hospital Reuniões. Foco do trabalho: uso excessivo de `any`, props de componentes sem tipos, inconsistência interface vs type, e tipos que poderiam ser mais específicos. Escopo combinado: só diagnóstico, sem alterar código. As recomendações ficam priorizadas (P0/P1/P2) pra virar trabalho real depois.

Base auditada: `hospital-reunioes/frontend/` (126 arquivos `.ts`/`.tsx`, ~20k LOC). Backend Python (FastAPI + Pydantic) referenciado quando relevante pra sincronização de tipos.

### Veredito geral

O frontend está em boa forma de tipagem. `strict: true` ativado, zero `@ts-ignore`, zero `any` em props, zero `useState` mal tipado. As fraquezas estão concentradas em pontos específicos (não espalhadas), o que torna o trabalho de correção pequeno e dirigido. O problema mais sério é o **drift entre backend e frontend no enum `UserRole`** (item 8). Os outros achados são higiene.

### 1. Configuração TypeScript

Único `tsconfig.json` em `hospital-reunioes/frontend/`:

```json
"strict": true,        // ON (cobre noImplicitAny, strictNullChecks, ...)
"allowJs": true,
"isolatedModules": true,
```

Flags faltando (risco médio):

| Flag | Efeito de ligar |
|---|---|
| `noUncheckedIndexedAccess` | `arr[0]` vira `T \| undefined`. Hoje mascara bugs em acesso por index. |
| `noImplicitReturns` | Pega `if/else` onde só um branch retorna. |
| `exactOptionalPropertyTypes` | Diferencia `foo?: T` (omitido) de `foo: T \| undefined` (explícito). Hoje colapsam. |

Severidade: média. Ligar as três disparará dezenas de erros legítimos. Não recomendo ativar todas de uma vez.

### 2. Uso de `any` explícito

Total confirmado: **3 ocorrências**, todas no mesmo arquivo (`src/app/reunioes/[id]/page.tsx`).

| Path:linha | Trecho | Diagnóstico |
|---|---|---|
| `src/app/reunioes/[id]/page.tsx:421` | `tipo: (reuniao.tipo as any) \|\| null` | Cast pra escapar de incompatibilidade entre `TipoReuniao` do frontend e o payload do POST `/api/reunioes/agendar`. Solução: `reuniao.tipo ?? null` com tipo do payload alinhado. |
| `src/app/reunioes/[id]/page.tsx:846` | `} catch (err: any) {` | `err.message` acessado abaixo. Solução: helper `getErrorMessage(err: unknown)`. |
| `src/app/reunioes/[id]/page.tsx:864` | `} catch (err: any) {` | Idem 846. |

Patterns relacionados (todos zerados, ponto forte):
- ZERO `// @ts-ignore`, `// @ts-expect-error`, `// @ts-nocheck`.
- ZERO `<any>`, `any[]`, `Array<any>`, `Promise<any>`, `Record<string, any>`.
- ZERO tipo `Function` solto.
- ZERO `useState()`, `useState(null)`, `useState(undefined)` sem genérico.
- ZERO `useRef<any>` ou refs sem genérico.

Observação metodológica: os agents exploratórios reportaram "zero `any`" na primeira passada. A reauditoria manual com `grep` direto encontrou os 3. Vigilância em revisões de PR é importante.

### 3. Catch handlers sem `: unknown`

9 ocorrências de `catch (e)` ou `catch (err)` sem anotação explícita. Em `strict: true`, TS 4.4+ infere `unknown` por padrão, então tecnicamente OK. Porém:

- 2 das 9 usam `: any` explícito (item 2 acima).
- Outras 3 (em `[id]/page.tsx:864` e `importar/page.tsx:305, 435, 663`) acessam `err.message` sem narrowing. Provavelmente quebram em build se `useUnknownInCatchVariables` ficar explicitamente true.

Lista completa:
- `src/app/pendencias/page.tsx:109, 526`
- `src/app/pendencias/kanban/page.tsx:311, 397`
- `src/app/admin/usuarios/page.tsx:113, 159`
- `src/app/admin/usuarios/[id]/page.tsx:57`
- `src/app/perfil/page.tsx:188`
- `src/app/reunioes/importar/page.tsx:305, 435, 663`
- `src/app/reunioes/[id]/page.tsx:846, 864` (com `: any`)

Ações sugeridas:
1. Criar `lib/errors.ts` com `getErrorMessage(err: unknown): string`.
2. Substituir `err.message` por `getErrorMessage(err)` em todos os 9 catches.
3. Remover os 2 `catch (err: any)`.

Severidade: média. Risco real de runtime error se o backend retornar payload diferente do esperado.

### 4. Componentes e props

Inventário:
- 75 arquivos `.tsx`.
- 38 componentes com Props tipados via interface/type dedicado (~59% dos que recebem props).
- 11 sem `interface Props` ou `type Props`. Validação manual confirmou que a maioria desses 11 não recebe props (componentes stateful com fetch interno). Não é problema real.
- ZERO uso de `any`, `Function`, `object` em handlers.
- ZERO `children: any` (todos usam `ReactNode`).

#### 4.1 Anti-pattern `null as string | null`

Em `src/components/dashboard/KpiCards.tsx`:
- Linhas 34, 58: `sublabel: null as string | null`
- Linha 46: `sublabel: "> 3 dias" as string | null`

Causa: o array literal `kpis` mistura objetos com `sublabel: string` e outros com `sublabel: null`, e o TS infere o tipo baseado no primeiro item. Solução: tipar o array explicitamente.

```typescript
// Hoje
function buildKpis(stats: Stats | null) {
  return [
    { id: "vencem-3dias", sublabel: null as string | null, ... },
    ...
  ];
}

// Sugestão
interface KpiDefinition {
  id: string;
  label: string;
  sublabel: string | null;
  value: number;
  icon: LucideIcon;
  // ...
}
function buildKpis(stats: Stats | null): KpiDefinition[] {
  return [
    { id: "vencem-3dias", sublabel: null, ... },
    ...
  ];
}
```

#### 4.2 Export de Props

6 de 38 (16%) exportam o tipo Props: `ConfirmDialog`, `DeleteButton`, e os 4 do `dashboard/`. Os outros 32 mantêm `interface Props` privada. Padrão coerente (utilitários reusados exportam, privados encapsulam). Manter.

#### 4.3 Forms sem schema library

4 modais grandes fazem validação manual com `useState` + `handleSubmit`:
- `UsuarioFormModal` (237 LOC)
- `ResolverExternoModal` (520 LOC)
- `TaxonomyFormModal` (117 LOC)
- `RecorrenciaPanel` (266 LOC)

Sem react-hook-form, Zod, Yup, Valibot. Tipos duplicados entre state local e payload. Funcional, mas refactor com Zod (item 9) eliminaria a duplicação.

### 5. Interface vs Type

Distribuição:
- 144 definições totais.
- 103 `interface` (~72%).
- 41 `type` (~28%).
- Sem convenção documentada em CLAUDE.md, AGENTS.md ou .eslintrc.

Padrão observado, válido, manter:
- `type` para **unions literais**: `StatusAta`, `UserRole`, `TipoReuniao`, `TipoNotificacao`, `StatusAtribuicao`, `StatusPendencia`.
- `interface` para **shapes de objeto**: `Participante`, `Reuniao`, `Pendencia`, `Comentario`.

Esse split é a convenção do TS Handbook moderno. Recomendado documentar no CLAUDE.md pra explicitar.

Inconsistências reais (~10 arquivos):

- `src/app/reunioes/calendario/page.tsx`: define `interface EventoCalendario` + `interface ReuniaoCalendario` localmente em vez de derivar de `Reuniao` em `@/types`.
- `src/app/reunioes/importar/page.tsx`: define `type MetadadosImportacao` e `type ParticipanteMatchedPreview` localmente. Esses já existem como `BaseModel` no backend (`schemas.py:398, 411`). Deveriam ser importados de um lugar comum ou derivados via codegen.
- `src/app/reunioes/[id]/page.tsx`: redefine `Atribuicao.status?: "ABERTO" | "EM_ANDAMENTO" | "CONCLUIDO"` quando `StatusAtribuicao` já existe em `@/types/index.ts:160`.

Severidade: baixa-média. Mais higiene do que bug.

### 6. Tipos que deveriam ser mais específicos

#### 6.1 `string` que deveria ser union literal

| Local | Hoje | Sugestão |
|---|---|---|
| `src/types/index.ts:253` (`HealthResponse.status`) | `string` | `"ok" \| "error"` |
| `src/components/admin/types.ts:25` (`AuditLogRow.action`) | `string` | `"create" \| "update" \| "delete" \| "soft_delete"` |
| `src/components/admin/types.ts:26` (`AuditLogRow.target_type`) | `string` | `"participante" \| "reuniao" \| "pendencia"` |
| `src/app/reunioes/calendario/page.tsx:121` `getStatusColor(status: string)` | `string` | `StatusAta` |
| `src/app/reunioes/calendario/page.tsx:140` `getStatusColorWeek(status: string)` | `string` | `StatusAta` |
| `src/app/reunioes/calendario/page.tsx:159` `formatStatus(status: string)` | `string` | `StatusAta` |
| `src/lib/auth.ts:28` `isSuperUser(_role: string)` | `string` | Deprecated, retorna sempre `false`. Remover. |

Por que importa: o tipo `string` permite passar qualquer coisa. Tipar como `StatusAta` faz o TS rejeitar typos (`"AGUARDANDO_VAIDACAO"` em vez de `"AGUARDANDO_VALIDACAO"`) e força exhaustiveness checks nos switches.

#### 6.2 Padrão `?: T | null` inconsistente

57 ocorrências misturando opcional e nullable na mesma definição. Exemplo concreto em `src/types/index.ts:59`:

```typescript
interface FacilitadorOption {
  setor?: string | null;  // pode ser undefined OU null. Que diferença faz?
}
```

Recomendação: padronizar por origem do dado.
- **Vindo do DB / API:** sempre `T | null` (campo obrigatório no tipo, mas nullable).
- **Vindo de form em construção:** sempre `T?` (omitido enquanto user não preencheu).
- **Patches PATCH:** `Partial<T>` ou `T?` sem null.

#### 6.3 Utility types pouco usados

Hoje:
- `Partial<>`: 11 usos. Bom.
- `Omit<>`: 1 uso.
- `Pick<>`, `Required<>`, `Readonly<>`, `ReadonlyArray<>`: ZERO uso.

Oportunidades:
- `ParticipanteFormDraft = Partial<Participante>` em modais de criação.
- `Pick<Reuniao, "id_reuniao" \| "data" \| "tipo">` para listagens.
- `ReadonlyArray<UserRole>` para constantes como `ROLE_OPTIONS`.

#### 6.4 Discriminated unions

ZERO no projeto. Oportunidade clara em `Reuniao`:

```typescript
// Hoje
interface Reuniao {
  status_ata: StatusAta;
  url_pdf_preliminar?: string;
  url_pdf_assinado?: string;
  json_ata?: Record<string, unknown>;
}
// Permite: ASSINADA sem url_pdf_assinado. Bug latente.

// Sugestão
type Reuniao = ReuniaoBase & (
  | { status_ata: "PROGRAMADA"; json_ata?: undefined; url_pdf_assinado?: undefined }
  | { status_ata: "AGUARDANDO_ASSINATURA"; json_ata: JsonAta; url_pdf_preliminar: string }
  | { status_ata: "ASSINADA"; json_ata: JsonAta; url_pdf_assinado: string }
  | { status_ata: "ERRO" | "ERRO_UPLOAD_TRANSCRICAO" | ...; error?: string }
);
```

Custo: alto (refactor amplo, narrowing em todas as telas). Benefício: impede estados inválidos em compile time. Severidade: baixa em urgência, alta em payoff. Adicionar à lista de débito técnico.

### 7. Type assertions e non-null assertions

#### 7.1 `as string` (14 ocorrências)

| Origem | Justificativa | Ação |
|---|---|---|
| 6× `user.user_metadata?.nome as string` (layouts) | Supabase tipa `user_metadata` como `Record<string, any>`. Cast inevitável sem schema. | Aceitar ou criar helper `getUserName(user)`. |
| 5× `formData.get("email") as string` | `FormData.get` retorna `FormDataEntryValue \| null`. | Aceitar ou criar `getFormString(fd, key, fallback)`. |
| 1× `params.id as string` | Next.js dynamic route. | Aceitar. |
| 2× `kpi-array as string` em KpiCards | Anti-pattern item 4.1. | Tipar array explicitamente. |

#### 7.2 Non-null assertions `!` (14 ocorrências)

| Origem | Status |
|---|---|
| 5× `searchParams.get(key)!.split(",")` | OK. Precedido de check `searchParams.get(key) ? ... : []`. |
| 4× `reuniao!.id_reuniao` em `[id]/page.tsx:833, 858, 1261, 1272` | **PROBLEMA.** `reuniao` é state que começa null. Em vez de assertir, handler deveria fazer `if (!reuniao) return;` no topo. |
| 1× `item.preview!` em `importar/page.tsx:1183` | Provavelmente OK (lista filtrada antes). Revisar. |
| 4× `item.subItems!.map`, `reuniao.participantes_programada!` | Mascarando opcionalidade real. Sugestão: guard explícito. |

Severidade: média. Os 4 `reuniao!.id_reuniao` são bugs latentes em condição de corrida.

### 8. Sincronização backend ↔ frontend

#### 8.1 Diagnóstico

Backend (`backend/app/models/schemas.py`):
- `UserRole(StrEnum)`: **4 valores** (DIRETOR, PRESIDENTE, GERENTE, COORDENADOR).
- `StatusAta(StrEnum)`: 12 valores.
- `StatusPendencia(StrEnum)`: 6 valores.
- `TipoReuniao(StrEnum)`: 5 valores.
- `TipoNotificacao(StrEnum)`: 5 valores.

Frontend (`src/types/index.ts`):
- `type UserRole`: **3 valores** (diretor, gerente, coordenador). **FALTANDO `presidente`.**
- Demais enums: ✓ sincronizados.

#### 8.2 Bug crítico de drift

Se o backend retornar `role: "presidente"`, o frontend aceita via cast mas a UI trata como string desconhecida. `ROLE_LABELS` em `src/lib/onboarding-data.ts:379` também está incompleto. Ação manual aprovada:

1. Editar `src/types/index.ts:3`:
   ```typescript
   export type UserRole = "diretor" | "presidente" | "gerente" | "coordenador";
   ```
2. Adicionar entrada `presidente` em `ROLE_LABELS` (`src/lib/onboarding-data.ts:379`).
3. Adicionar `"presidente"` em `ROLE_OPTIONS` (`src/components/admin/types.ts:52`).
4. Verificar switch/match em `UserRole` (cargo, role guard em rotas).

#### 8.3 DTOs duplicados

`MetadadosImportacao`, `ParticipanteMatchedPreview`, `ParticipanteExternoPreview` existem identicamente em backend (Pydantic) e frontend (TS). Duplicação manual.

Soluções possíveis (não implementar agora):
- **Curto prazo:** documentar regra "ao mudar `schemas.py`, atualizar `src/types/`".
- **Médio prazo:** rodar `openapi-typescript` contra `/openapi.json` do FastAPI pra gerar `src/types/api.ts`. Roda em CI.
- **Longo prazo:** monorepo com types compartilhados. Não vale o overhead pra esse projeto.

Severidade: alta (UserRole) + média (drift contínuo).

### 9. Validação runtime

Hoje: ZERO bibliotecas (sem Zod, Yup, Valibot, io-ts). Boundary externa entra como `T` (cast), sem checar formato.

Pontos de boundary:
1. `fetch("/api/...")` responses em ~40 telas.
2. `JSON.parse(localStorage.getItem(...))` em `importar/page.tsx:211` e `admin/usuarios/page.tsx:152`.
3. `formData.get(...) as string` em server actions.
4. Payload Supabase `user.user_metadata` (já `Record<string, any>` pelo SDK).
5. Chat-correcao response com `correction_plan: CorrectionItem[]`.
6. ATA JSON parsing (`json_ata: Record<string, unknown>`).

**Recomendação:** Zod nas boundaries críticas + forms grandes. Justificativa:
- Backend já valida via Pydantic. Boundary backend→frontend é defesa em profundidade, não primária. Risco principal: backend muda e frontend não percebe em compile time.
- Zod nos 4 forms manuais grandes elimina duplicação tipo/state e padroniza erros.
- Custo: 1 lib (12KB gzipped), 1 arquivo `lib/schemas.ts` com ~6 schemas críticos.
- Tipos derivam do schema via `z.infer<typeof schema>`, eliminando duplicação interna.

Escopo sugerido (item P2 abaixo):
1. `lib/schemas.ts` com schemas Zod para: `Reuniao`, `Pendencia`, `Participante`, `AdminUsuario`, `ChatCorrecaoResponse`, `JsonAta`.
2. Helper `parseResponse<T>(schema, response)` que faz fetch + zod parse + erro tipado.
3. Migrar os 4 forms grandes para `useForm` (react-hook-form) com `zodResolver`.
4. Substituir `JSON.parse(raw) as ItemFila[]` por `z.array(itemFilaSchema).parse(JSON.parse(raw))`.

Alternativa mais barata: type guards manuais (`isStatusAta(s: string): s is StatusAta`) pros 4-5 boundaries mais sensíveis. Não escala, mas resolve 80% sem dependência nova.

### 10. Recomendações priorizadas

#### P0 (impacto alto, custo baixo)

1. **Sincronizar UserRole com backend.** Adicionar `"presidente"` em `src/types/index.ts:3`, `src/lib/onboarding-data.ts:379`, `src/components/admin/types.ts:52`. ~10 min.
2. **Remover 2× `catch (err: any)`** em `reunioes/[id]/page.tsx:846, 864`. Criar helper `lib/errors.ts` com `getErrorMessage(err: unknown): string` e aplicar nos 9 catches.
3. **Remover `as any` em `[id]/page.tsx:421`.** Trocar por `reuniao.tipo ?? null` e alinhar tipo do payload.
4. **Trocar `reuniao!.id_reuniao`** (linhas 833, 858, 1261, 1272) por guard explícito no topo dos handlers.

#### P1 (higiene, payoff médio)

5. **Tipar `getStatusColor`, `getStatusColorWeek`, `formatStatus`** em `calendario/page.tsx` com `status: StatusAta`.
6. **Tipar `KpiDefinition` explicitamente** em `KpiCards.tsx` pra eliminar os 3 `null as string | null`.
7. **Deletar `isSuperUser` em `lib/auth.ts:28`** (deprecated, sempre retorna false). Remover chamadas.
8. **Documentar convenção interface vs type no CLAUDE.md.** Pattern atual já é bom, só falta explicitar.
9. **Padronizar `?: T | null`.** Decidir caso a caso por origem do dado. Começar pelas ocorrências em `src/types/index.ts`.

#### P2 (refactor maior)

10. **Discriminated union pra `Reuniao` por `status_ata`.** Impede estados inválidos. ~1 dia.
11. **Zod em boundaries críticas** (item 9). ~2 dias.
12. **Codegen via openapi-typescript** contra FastAPI. ~1 dia + ajustes em CI.
13. **Ativar `noUncheckedIndexedAccess`** no tsconfig. ~1 dia.
14. **Refatorar 4 forms grandes** para react-hook-form + Zod. ~3 dias.

### 11. Pontos fortes (manter, não regredir)

- `strict: true` ativado.
- ZERO `@ts-ignore`, `@ts-expect-error`, `@ts-nocheck`.
- ZERO `useState` sem tipo claro.
- ZERO `useRef<any>` ou refs sem genérico.
- ZERO uso de `Function`, `object`, `{}` em props.
- Tipos centralizados em `src/types/index.ts`.
- Convenção `interface` para objetos / `type` para union literals seguida na maioria dos arquivos.
- Uso correto de `Partial<>` em forms de patch.
- StatusAta, StatusPendencia, TipoReuniao, TipoNotificacao todos sincronizados com backend.

### Riscos / observações

- Os agents exploratórios da primeira passada perderam 3 `any` reais. Lições: vale rodar `grep` direto pra confirmar contagem em qualquer auditoria futura.
- Ativar flags do tsconfig (P2 item 13) em um único PR vai gerar dezenas de erros simultâneos. Recomendo abrir flag por flag.
- Adicionar `"presidente"` em `UserRole` (P0 item 1) pode disparar erros TS em switches que cobrem `UserRole` sem `default`. Trabalho de seguir o compilador.

## Execução / Resultados

### 2026-05-12, 23h. P0.1 a P0.4 fechados em uma única passada (pré-commit, sem deploy).

Type-check final: `./node_modules/.bin/tsc --noEmit` exit 0, zero erros. Lint: `next lint` exit 0, só warnings pré-existentes (exhaustive-deps em hooks de fetch, `_role` não usado em `isSuperUser` que ainda vai sair no P1.7, ARIA em combobox de importação).

#### P0.1: UserRole sincronizado (concluído)

Bug pior do que o diagnóstico inicial mostrava: havia **duas declarações de `UserRole`** no projeto. A de `src/lib/onboarding-data.ts:11` tinha os 4 valores corretos (`presidente` incluso), a de `src/types/index.ts:3` só tinha 3. Quem importava de `@/types` (a maioria do app) usava o tipo errado, mas o type-check passava porque `ROLE_LABELS` referenciava o tipo local.

Resolvido em 3 arquivos:
- `src/types/index.ts:3`: adicionado `"presidente"` na union. Agora é fonte única.
- `src/lib/onboarding-data.ts:11`: removida a redeclaração; agora faz `import type { UserRole } from "@/types"` + `export type { UserRole } from "@/types"` (preserva re-export pra não quebrar imports existentes).
- `src/components/admin/types.ts:52`: adicionado `"presidente"` em `ROLE_OPTIONS`.

Efeito colateral imediato detectado pelo tsc: dois `Record<UserRole, string>` em `src/app/perfil/page.tsx:42, 48` (ROLE_BADGE e ROLE_LABEL) ficaram incompletos. Adicionada a chave `presidente` em ambos (mesmo estilo visual do `diretor`, gradient primary).

#### P0.2: Helper `getErrorMessage` + remoção dos `catch (err: any)` (concluído)

Criado `src/lib/errors.ts` com helper único:

```typescript
export function getErrorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try { return JSON.stringify(err); } catch { return "Erro desconhecido"; }
}
```

Aplicado em 6 catches que precisavam de string:
- `src/app/reunioes/[id]/page.tsx:846, 864`: removido `: any`, agora usa `getErrorMessage(err)`. Eram os 2 únicos `catch (... : any)` do projeto.
- `src/app/admin/usuarios/page.tsx:113, 159`: trocado o pattern manual `e instanceof Error ? e.message : String(e)` (repetido em 2 lugares) pelo helper.
- `src/app/reunioes/importar/page.tsx:435, 663`: idem.

Os outros 7 catches que só passam pro `console.error(unknown)` ficaram como estão (não tem ganho, console aceita unknown).

#### P0.3: `as any` removido em payload de agendamento recorrente (concluído)

`src/app/reunioes/[id]/page.tsx:421`: `tipo: (reuniao.tipo as any) || null` virou `tipo: reuniao.tipo ?? null`. O `??` é mais correto que `||` semanticamente (só cai pra null em null/undefined, não em string vazia). Backend já aceitava `TipoReuniao | None` no schema, então não houve drift.

#### P0.4: Guards explícitos no lugar de `reuniao!` (concluído)

Os 4 non-null assertions em `src/app/reunioes/[id]/page.tsx` resolvidos:

- Linhas 833, 858 (handlers `handleResolverParticipantes` e `handlePularResolucao`): adicionado `if (!reuniao) return` no topo de cada handler. Os fetches agora usam `reuniao.id_reuniao` sem o `!`.
- Linhas 1261, 1272 (JSX dentro do render PROGRAMADA): trocado `reuniao.participantes_programada!` por optional chaining + fallback (`?.length ?? 0` no count, `?? []` antes do `.map`). O early return de `if (error || !reuniao) return ...` na linha 1077 já existia, mas TS não narrow campo opcional só com check em `length`.

Resultado: zero `!` non-null em `[id]/page.tsx`. `grep -rn "reuniao!" src/` retorna vazio em todo o projeto.

#### Sanity checks finais

```
=== any explícito ===
(zero)
=== reuniao! ===
(zero)
=== UserRole declarations ===
src/types/index.ts:3:export type UserRole = "diretor" | "presidente" | "gerente" | "coordenador";
=== tsc final ===
TSC EXIT: 0
=== lint ===
LINT EXIT: 0 (só warnings pré-existentes)
```

#### Arquivos tocados

- `src/types/index.ts` (P0.1)
- `src/lib/onboarding-data.ts` (P0.1)
- `src/components/admin/types.ts` (P0.1)
- `src/app/perfil/page.tsx` (P0.1, efeito colateral)
- `src/lib/errors.ts` (P0.2, novo)
- `src/app/reunioes/[id]/page.tsx` (P0.2 + P0.3 + P0.4)
- `src/app/admin/usuarios/page.tsx` (P0.2)
- `src/app/reunioes/importar/page.tsx` (P0.2)

8 arquivos no total, 1 novo. Próximo passo seria revisar visualmente as telas afetadas (admin/usuarios, perfil, importar/page, reuniao/[id]) e depois decidir se sobe pra produção. Os itens P1 e P2 do plano continuam abertos pra ataques futuros.
