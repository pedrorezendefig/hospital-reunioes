# Plano — Remover campo "Local" e renomear "Objetivo" → "Pauta" (só UI)

## Context

Todas as reuniões do hospital acontecem na mesma sala, então o metadado `local` da reunião não agrega valor — vira ruído no formulário, na ATA gerada pela IA e na tabela do banco. Remoção total: UI, backend, prompts da IA, e DROP COLUMN via migration nova (banco ainda em uso inicial mocado, perda aceitável).

Em paralelo, o usuário pediu para chamar "Objetivo" de "Pauta" na UI. Decisão tomada: **só labels visíveis** — não tocar em coluna, schemas Pydantic, types TypeScript ou prompts da IA. O identificador `objetivo` permanece em todo o backend e DB, garantindo zero risco para o pipeline da IA já calibrado. A coluna `objetivo_meta` das pendências (campo diferente, "meta da ação") fica intocada.

> **Local do plano:** este arquivo está em `~/.claude/plans/` por restrição do plan mode. Ao iniciar a execução, copiá-lo para `planos/plano-26-04-27-XXXXh-remover-local-renomear-objetivo-pauta.md` conforme regra do CLAUDE.md do projeto.

---

## 1. Banco — DROP coluna `local`

**Criar:** `hospital-reunioes/supabase/migrations/003_drop_local_reuniao.sql`

```sql
-- Migration 003: Remove coluna `local` da tabela reunioes
-- Justificativa: todas as reuniões acontecem na mesma sala — campo deixou de agregar valor.

ALTER TABLE reunioes DROP COLUMN IF EXISTS local;
```

> Não atualizar `002_create_reunioes.sql` (migrations são imutáveis).
> Aplicar local com `supabase db reset` ou `supabase migration up` no fluxo de dev. Em produção: rodar via Supabase SQL editor.

---

## 2. Backend — remover `local` de schemas, routers, pipeline e IA

### 2.1 Schemas Pydantic
- `hospital-reunioes/backend/app/models/schemas.py`
  - Linha 100: remover `local: str | None = None` de `ReuniaoResponse`.
  - Linha 122: remover `local: str | None = Field(None, max_length=255)` de `AgendarReuniaoRequest`.
  - Linha 137: remover `local: str | None = Field(None, max_length=255)` de `EditarReuniaoRequest`.
- `hospital-reunioes/backend/app/models/admin_schemas.py`
  - Linha 249: remover `local: str | None = Field(None, max_length=255)` de `ReuniaoAdminUpdate`.

### 2.2 Routers
- `hospital-reunioes/backend/app/routers/reunioes.py`
  - Linha 76: remover `"local": req.local,` do dict de insert em `agendar_reuniao`.
  - Linha 129: remover `, local` do SELECT em `get_calendario`.
  - Conferir outros SELECTs/UPDATEs no arquivo (grep `local` no router) e remover.

### 2.3 Pipeline
- `hospital-reunioes/backend/app/pipeline/orchestrator.py`
  - Linhas 137-142: remover busca/extração de `local_reuniao` (manter só `objetivo`).
  - Linhas 154, 219, 273, 382: remover `local_reuniao=...` das chamadas a `ai_processor.process_reuniao_transcricao` e remover `local` dos SELECTs.

### 2.4 AI Processor
- `hospital-reunioes/backend/app/services/ai_processor.py`
  - Linha 74: remover parâmetro `local_reuniao: str = ""`.
  - Linha 114: remover `local_reuniao=local_reuniao or "Não informado"` do render do prompt.
  - Linha 143: remover `parsed.setdefault("local", parsed.get("local") or local_reuniao or "")`.
  - Linha 307: remover `"local": meta.get("local"),` do dict mock.
  - Linha 427: remover `"local": "Sala de Reuniões 3 — 2º andar",` do exemplo mock.

### 2.5 Parser de ATAs migradas (PDFs legados)
- `hospital-reunioes/backend/app/services/pdf_parser_ata_migrada.py`
  - Linhas 1-8 (docstring): remover menção a `local` na lista de metadados.
  - Linhas 53-58 (`_is_metadados_header`): atualizar comentário e a lógica que detecta a coluna "Local". O cabeçalho da tabela vira `Data | Início | Encerramento` (sem `Local`). **Verificar PDFs reais** — se ainda houver tabelas com 4 colunas, a função precisa ignorar a 4ª silenciosamente.
  - Linha 113: remover bloco `elif "local" in h: result["local"] = val`.

### 2.6 Ana Tools
- `hospital-reunioes/backend/app/services/ana_tools/mutacoes_leves.py`
  - Linhas 271 e 286: remover `local` da lista de "Campos aceitos" nas descrições da ferramenta `EDITAR_REUNIAO`.
- `hospital-reunioes/backend/app/services/ana_schema.py`
  - Linha 51: remover menção a `local TEXT` na doc de schema da Ana.

---

## 3. Prompts da IA — remover `local`

- `hospital-reunioes/backend/app/prompts/extracao_ata.md`
  - Linha 7 (cabeçalho): trocar `"...data, horário e local."` por `"...data e horário."`.
  - Linha 40: remover `"local": "local da reunião ou null",` do schema JSON.
- `hospital-reunioes/backend/app/prompts/user_extracao.md`
  - Linhas 3 e 6: remover linha `Local da reunião (se informado): {{local_reuniao}}` e a instrução "Se o `local` acima estiver preenchido, reutilize-o…".
- `hospital-reunioes/backend/app/prompts/correcao_ata.md`
  - Linha 18: remover `"local": "string ou null",`.
- `hospital-reunioes/backend/app/prompts/extracao_ata_migrada.md`
  - Verificar e remover qualquer chave `local` do JSON ou referência no texto.

> **Smoke após mudanças:** rodar `pytest backend/tests/test_ai_processor*.py` para garantir que mocks/asserts não referenciam mais `local`.

---

## 4. Frontend — remover campo `local` e renomear labels "Objetivo" → "Pauta"

### 4.1 Tipos
- `hospital-reunioes/frontend/src/types/index.ts`
  - Linha 192: remover `local?: string;` da interface `JsonAta` (HSM Cabeçalho).

### 4.2 Tela de detalhe da reunião — `src/app/reunioes/[id]/page.tsx`

**Remover Local:**
- Linha 28: remover `MapPin` do import `lucide-react` (verificar se usado em outros lugares — se sim, manter).
- Linhas 1209-1215: remover bloco `<InlineEditField label="Local" ...>`.
- Linhas 1429-1431: remover linha do card lateral com "Local".
- Linhas 1844-1849: remover bloco que renderiza `{(ata.local || reuniao.local) && ...}` na seção HSM.

**Renomear Objetivo → Pauta (só labels):**
- Linha 1227: `label="Objetivo"` → `label="Pauta"`.
- Linha 1731: `<Section title="Objetivo"` → `<Section title="Pauta"`.
- Linha 1825: `title="Objetivo da Reunião"` → `title="Pauta da Reunião"`.
- Linha 619: checklist `"Definir objetivo da reunião"` → `"Definir pauta da reunião"`.

> **NÃO mexer** em `reuniao.objetivo`, `handlePatch({ objetivo: ... })`, types — só strings vistas pelo usuário.

### 4.3 Tela de calendário — `src/app/reunioes/calendario/page.tsx`

**Remover Local:**
- Linha 13: remover `MapPin` do import.
- Linhas 38-50: remover `local: string | null;` da interface `EventoCalendario`.
- Linhas 56-65: remover constante `LOCAIS_MOCK` inteira.
- Linha 388: remover o `<select>` de Local + label associado.
- Linhas 703 e 1039: remover `<MapPin ... />` dos cards (e a string ao lado, se houver).
- Verificar `payload` enviado em `submit` — remover `local` se aparecer.

**Renomear Objetivo → Pauta:**
- Linha 415: label `"Objetivo (opcional)"` → `"Pauta (opcional)"`.
- Linha 419: placeholder `"Descreva o objetivo da reunião..."` → `"Descreva a pauta da reunião..."`.

### 4.4 Tela de criar reunião — `src/app/reunioes/page.tsx`
- Linha 289: label `"Objetivo (opcional)"` → `"Pauta (opcional)"`.
- Linha 294: placeholder `"Descreva o objetivo principal da reunião..."` → `"Descreva a pauta principal da reunião..."`.

### 4.5 Modal admin — `src/components/admin/ReuniaoEditModal.tsx`
**Remover Local:**
- Linha 16: remover `local: string | null;` da interface `ReuniaoEditable`.
- Linha 63: remover `const [local, setLocal] = useState(target.local ?? "");`.
- Linha 81: remover `maybeSet("local", local, target.local);`.
- Linhas 179-185: remover `<Field label="Local">…</Field>`.
- Linha 50 (comentário): atualizar a lista "(titulo, setor, tipo, facilitador, objetivo, local)" removendo `local`.

**Renomear Objetivo → Pauta:**
- Linha 204: `<Field label="Objetivo">` → `<Field label="Pauta">` (state e key continuam `objetivo`).

### 4.6 Tela de importar ATAs — `src/app/reunioes/importar/page.tsx`
- Linha 1258: label `"Objetivo"` → `"Pauta"`.
- Conferir se há campo de Local no formulário de importação — se sim, remover (input + payload).

### 4.7 Checklist de preparação — `src/components/reunioes/PreparacaoChecklist.tsx`
- Linha 20: `"Definir objetivo da reunião"` → `"Definir pauta da reunião"`.

### 4.8 Buscas no admin
- `src/app/admin/bulk/page.tsx` linha 464: placeholder `"Buscar por id, tipo ou objetivo"` → `"Buscar por id, tipo ou pauta"`.
- `src/app/admin/reunioes/page.tsx` linha 222: placeholder `"Buscar por título, ID ou objetivo..."` → `"Buscar por título, ID ou pauta..."`.

---

## 5. NÃO MEXER (intencional)

- **Identificadores `objetivo`** em qualquer lugar do código (chaves TS, names de form, props, payloads, schemas, coluna do banco, prompts da IA). A IA continua gerando `{"objetivo": ...}` e o backend continua persistindo em `reunioes.objetivo`.
- **`objetivo_meta`** das pendências e a coluna "Objetivo / Meta" da tabela em `[id]/page.tsx:1995`. Campo diferente (meta de ação).
- **Comentário em test_admin_usuarios.py:501** ("nao e objetivo do teste") — uso lexical, não relacionado.

---

## 6. Verificação end-to-end

### 6.1 Estática
1. `cd hospital-reunioes/frontend && npm run typecheck` — zero erros TS.
2. `cd hospital-reunioes/frontend && npm run lint` — sem novos warnings.
3. `cd hospital-reunioes/backend && python -m pytest -x` — todos verdes (especialmente `test_ai_processor_*` e `test_ana_foundation_smoke`).
4. `grep -rn "\\blocal\\b" hospital-reunioes/{frontend/src,backend/app}` filtrado — não pode haver mais referência a `local` como **campo de reunião** (variáveis locais de função são OK).

### 6.2 Pipeline da IA (smoke manual)
5. Subir stack via `/atualizar-app`.
6. Importar uma ATA mocada de teste (ou usar pasta `atas-migracao/` com `migrar-atas`) e conferir que o JSON de retorno **não tem** chave `local` e que o PDF gerado não exibe "Local: …".
7. Pedir à Ana via chat para "editar local da reunião X" e confirmar que ela responde que esse campo não existe mais (ou simplesmente não aceita).

### 6.3 UX
8. Acessar `/reunioes/[id]` de uma reunião existente — verificar:
   - Card "Detalhes da Reunião" não exibe linha "Local".
   - Label "Pauta" no lugar de "Objetivo".
   - Card lateral sem "Local".
   - Seção HSM da ATA sem rodapé "Local: …".
9. Acessar `/reunioes/calendario` — formulário de agendar não tem mais select de salas.
10. Acessar `/reunioes` — formulário usa "Pauta (opcional)".
11. Modal admin (`ReuniaoEditModal`) não tem campo Local; label "Pauta".

### 6.4 Banco
12. `\d reunioes` no Supabase: confirmar que `local` não está mais entre as colunas; `objetivo` continua presente.

---

## 7. Risco e rollback

- **Risco**: PDFs antigos no Supabase Storage que tinham `Local: …` vão continuar exibindo isso (são arquivos imutáveis). Aceitável — não geramos PDF retroativamente.
- **Risco**: registros antigos no `json_ata` JSONB ainda têm chave `local`. Aceitável — código novo simplesmente ignora.
- **Rollback**: reverter migration com `ALTER TABLE reunioes ADD COLUMN local TEXT;` e `git revert`.
