# Plano — Calendário como página única de Reuniões + Transcrição multi-formato

## Plano

### Contexto

A página **Lista de Reuniões** (`/reunioes`) hoje duplica funcionalidade do **Calendário** (`/reunioes/calendario`) e gera ambiguidade no menu (a sidebar tem "Lista" e "Calendário" como sub-itens irmãos). O usuário decidiu que **todo o gerenciamento de reuniões acontece pelo Calendário** — a Lista deve sumir.

Em paralelo, o botão **"Anexar Transcrição e Processar com IA"** (no detalhe da reunião) hoje aceita apenas `.txt`. Vai passar a aceitar `.txt`, `.md`, `.pdf` e `.docx` (decisão tomada: **não suportar `.doc`** legado — formato binário pré-2007 que exige libs pesadas e binários do sistema; mensagem amigável pedirá `.docx` ou PDF).

O `UploadModal` da Lista (que cria reunião nova já com transcrição via `POST /upload-transcricao`) **migra para o Calendário** como botão **"Importar Transcrição"** no header (só para *criar* reunião nova; *anexar* a uma existente continua sendo só pelo detalhe).

Filtros (Status/Tipo) e botões super-admin ("Aprovar Todas Bypass", "Importar ATA" duplicado) **não migram** — somem da UI. "Importar ATA" continua acessível pela sidebar; "Aprovar Todas Bypass" deixa de ter UI (rota backend permanece para uso administrativo via API).

**Resultado esperado**:
- `/reunioes` redireciona para `/reunioes/calendario`
- Sidebar fica com "Reuniões" → [Calendário, Importar ATA(super admin)]
- Calendário ganha botão "Importar Transcrição" no header (lado a lado com "Agendar Reunião")
- Botão "Anexar Transcrição" e "Importar Transcrição" aceitam `.txt`, `.md`, `.pdf`, `.docx` com extração de texto centralizada no backend

---

### Arquivos críticos a modificar

#### Frontend — remoção da Lista e redirects

| Arquivo | Mudança |
|---|---|
| `hospital-reunioes/frontend/src/app/reunioes/page.tsx` | **Substituir conteúdo** (era 814 linhas) por server component mínimo: `import { redirect } from "next/navigation"; export default function Page() { redirect("/reunioes/calendario"); }` |
| `hospital-reunioes/frontend/src/components/layout/Sidebar.tsx` | Linha 47: remover entry `{ href: "/reunioes", label: "Lista", icon: ListTodo }`. Manter o pai "Reuniões" como dropdown com [Calendário, Importar ATA]. Considerar remover o import `ListTodo` se ficar órfão. |
| `hospital-reunioes/frontend/src/components/layout/BottomNav.tsx` | Linha 31: `href: "/reunioes"` → `href: "/reunioes/calendario"`. Manter `match: (p) => p.startsWith("/reunioes")` na linha 34. |
| `hospital-reunioes/frontend/src/components/dashboard/KpiCards.tsx` | Linhas 53 e 65: `href: "/reunioes"` → `href: "/reunioes/calendario"` (KPIs "Atas Paradas" e "Aguardam Assinatura"). |
| `hospital-reunioes/frontend/src/app/reunioes/importar/page.tsx` | Linha 319: `router.replace("/reunioes")` → `router.replace("/reunioes/calendario")`. Linha 837: breadcrumb `href="/reunioes"` → `/reunioes/calendario`. |
| `hospital-reunioes/frontend/src/app/reunioes/[id]/page.tsx` | Linha 677: fallback do botão "Voltar" `return "/reunioes"` → `return "/reunioes/calendario"`. Linha 1070: error fallback `href="/reunioes"` → `/reunioes/calendario`. |

> **Middleware (`middleware.ts`)** não precisa mudar — `/reunioes/:path*` continua protegido e cobre `/reunioes/calendario`.

#### Frontend — migração do UploadModal para o Calendário

1. **Extrair** o `UploadModal` (atualmente linhas 144–393 de `app/reunioes/page.tsx`) para componente próprio:
   - Novo arquivo: `hospital-reunioes/frontend/src/components/reunioes/UploadTranscricaoModal.tsx`
   - Mesma assinatura: `{ onClose, onSuccess }`
   - Reusar tipos e estilos atuais
2. **Atualizar** o componente extraído para os novos formatos:
   - `accept=".txt,.md,.pdf,.docx"` no `<input type="file">`
   - Drop zone copy: "Solte arquivos `.txt`, `.md`, `.pdf` ou `.docx`"
   - Regex de basename ao montar título múltiplo: `f.name.replace(/\.txt$/i, '')` → `f.name.replace(/\.(txt|md|pdf|docx)$/i, '')`
   - Tratamento de erro 422 do backend mostra mensagem retornada (ex: PDF escaneado, formato inválido)
3. **Wirar** no Calendário:
   - `app/reunioes/calendario/page.tsx`: importar `UploadTranscricaoModal`
   - Adicionar estado `showUploadModal` e botão **"Importar Transcrição"** no header (linha ~1245), à esquerda de "Agendar Reunião". Ícone `Upload` da `lucide-react`
   - `onSuccess` chama o mesmo `fetchEventos()` que o calendário já tem para refrescar o range visível (lembrar: a reunião criada pode cair fora do range — informar via toast: "Reunião criada para `dd/mm/aaaa`. Clique para visualizar." → ação muda mês/semana)

#### Frontend — botão "Anexar Transcrição" no detalhe da reunião

| Arquivo | Mudança |
|---|---|
| `hospital-reunioes/frontend/src/app/reunioes/[id]/page.tsx` (linhas ~1353–1391, seção "Transcrição") | `accept=".txt"` → `accept=".txt,.md,.pdf,.docx"`. Copy: "Após a reunião, anexe o arquivo de transcrição (`.txt`, `.md`, `.pdf` ou `.docx`) para que a IA processe e gere a ata automaticamente." |

#### Backend — extrator multi-formato

1. **Adicionar dependência** em `hospital-reunioes/backend/pyproject.toml` (linha 21, junto de `pdfplumber`):
   ```
   "docx2txt>=0.8",
   ```
   - Lib pure-Python, ~8 KB, sem deps externas. Função única: `docx2txt.process(file_or_bytes)` retorna texto plano.
   - `pdfplumber>=0.11.0` já está instalado.

2. **Criar** `hospital-reunioes/backend/app/services/transcricao_extractor.py` — módulo único de extração:
   ```python
   SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
   MAX_BYTES_TEXT = 5 * 1024 * 1024     # 5 MB para .txt/.md
   MAX_BYTES_BINARY = 15 * 1024 * 1024  # 15 MB para .pdf/.docx (alinhado com bulk_import_atas)
   MIN_PDF_TEXT_BYTES = 200             # mesmo limite do importador de ATAs

   def extrair_texto(filename: str, file_bytes: bytes) -> tuple[str, str]:
       """Retorna (texto_extraido, extensao_normalizada). Levanta ValueError com mensagem em pt-BR."""
   ```
   Lógica por extensão:
   - `.txt` / `.md` → `bytes.decode("utf-8", errors="replace")`
   - `.pdf` → `pdfplumber.open(io.BytesIO(bytes))` → concatena `page.extract_text()` de todas as páginas. Se < `MIN_PDF_TEXT_BYTES`, levantar erro: "PDF parece ser escaneado (sem texto extraível). Faça OCR antes ou envie a transcrição em texto."
   - `.docx` → `docx2txt.process(io.BytesIO(bytes))`
   - `.doc` (legado) → erro explícito: "Formato `.doc` não suportado. Salve como `.docx` ou PDF."
   - Outras → erro: "Formato não suportado. Aceitos: `.txt`, `.md`, `.pdf`, `.docx`."

3. **Atualizar** `hospital-reunioes/backend/app/routers/reunioes.py`:
   - **Endpoint `/anexar-transcricao`** (linhas 386–422): trocar bloco da linha 397 por chamada a `extrair_texto()`. Capturar `ValueError` → `HTTPException(422, detail=str(e))`.
   - **Endpoint `/upload-transcricao`** (linhas 424+): mesma mudança.
   - Refinar assinatura de `run_pipeline`: `(supabase, id_reuniao, file_bytes, texto_extraido, extensao, tipo)`.

4. **Atualizar** `hospital-reunioes/backend/app/pipeline/orchestrator.py` (linhas 48–80):
   - Salvar arquivo original no Storage como `{id_reuniao}/transcricao{extensao}` com `content_type` correto por extensão.
   - Pipeline IA recebe a string já extraída — `ai_processor.py` não muda.

#### Backend — testes (recomendado)

- `hospital-reunioes/backend/tests/services/test_transcricao_extractor.py` com fixtures para cada formato (válido + casos de erro).

---

### Verificação end-to-end

#### Frontend (rodar `/atualizar-app`)

1. **Redirect raiz**: `http://localhost:3000/reunioes` → `/reunioes/calendario`.
2. **Sidebar**: sem sub-item "Lista". Calendário e Importar ATA presentes.
3. **BottomNav (mobile)**: "Reuniões" leva para Calendário.
4. **Dashboard KPIs**: cards levam para Calendário.
5. **Detalhe → voltar**: volta para Calendário no mês/semana correto.
6. **Importar ATA → não-super-admin**: redirect para Calendário.
7. **"Importar Transcrição" no Calendário**: testar `.txt` / `.md` / `.pdf` válido / `.pdf` escaneado / `.docx` / `.doc` (rejeitado) / >15 MB (rejeitado).
8. **"Anexar Transcrição" no detalhe**: idem.
9. **Storage Supabase**: arquivos com extensão correta.
10. **Auditoria DB**: `url_transcricao` aponta para arquivo com extensão preservada.

#### Backend

11. `pytest tests/services/test_transcricao_extractor.py -v` (se testes adicionados).
12. Logs do pipeline OK para cada formato.

#### Pós-execução

13. `/api/reunioes/aprovar-bypass-todas` ainda responde a chamadas autorizadas (rota órfã, sem UI).
14. `/api/reunioes` (lista com filtros) continua funcionando para o Dashboard.
15. `bulk_import_atas` continua intacto (`pdf_parser_ata_migrada.py` não foi alterado).

---

### Riscos e notas

- **Endpoint `/aprovar-bypass-todas` fica sem caller no frontend.** Mantido para uso administrativo. Documentar no `blueprint/DEPLOY.md`.
- **Storage path muda** de `{id}/transcricao.txt` para `{id}/transcricao.{ext}`. Sem migração de dados antigos.
- **Schema DB não muda** — `url_transcricao` permanece `TEXT`.
- **PDF escaneado** rejeitado com mensagem amigável (sem OCR — fora de escopo).
- **Markdown** entra bruto na IA (GPT-4o-mini entende sintaxe).
- **`docx2txt` é minimalista** — só texto. Se aparecer caso real onde isso falha, avaliar `mammoth`.

---

### Ordem de execução sugerida

1. Backend (dep + extrator + endpoints + orchestrator).
2. Frontend redirects e sidebar.
3. Frontend `[id]/page.tsx` (estender `accept`).
4. Frontend extração de Modal + wire no Calendário.
5. Substituir `app/reunioes/page.tsx` por redirect.
6. Smoke test E2E.
7. Atualizar `blueprint/DEPLOY.md` se relevante.

---

## Execução / Resultados

_Será preenchido conforme cada etapa for concluída._
