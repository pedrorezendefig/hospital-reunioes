# Plano — Migração em massa de ATAs antigas + matcher com score

## Contexto

O projeto Hospital Reuniões já tem um fluxo de "importar ATA antiga" (endpoints `/importacao/preparar` e `/importacao/confirmar`, RPC atômica `confirmar_importacao_atomico`). A dor atual é prática: fazer isso **um PDF de cada vez pelo UI** é inviável quando existem dezenas de atas antigas a migrar, e o matcher de participantes ainda falha em casos de **nome+sobrenome não consecutivos** (ex: IA extrai "Maria Silva" e o banco tem "Maria Fernanda Silva Souza" — a cascata atual não resolve). O usuário também pediu para renomear o rótulo "importar ATA antiga" → "importar ATA".

**Outcome:** um script CLI em duas fases (`--dry-run` → `--apply`) que processa todos os PDFs de uma pasta e persiste em lote. Matcher expandido com **score 0–100** e nova estratégia "par nome+sobrenome". Tudo reusa o pipeline existente — zero duplicação de lógica.

## Escopo

**Inclui:**
1. Novo script `backend/scripts/bulk_import_atas.py` com dois modos: `dry-run` (gera JSON) e `apply` (persiste via RPC).
2. Nova estratégia no matcher: par nome+sobrenome com score.
3. Matcher retorna score 0–100 e estratégia usada (retrocompatível).
4. Rename "importar ATA antiga" → "importar ATA" no frontend.
5. Testes unitários novos em `test_participant_matcher.py`.

**Fora de escopo:**
- Mudar URL de endpoints ou nome de tabelas/enums (`status_ata='MIGRADA'` fica).
- Fluxo ao vivo (`pipeline.orchestrator.run_pipeline`) — não mexe.
- UI de bulk import no frontend (usa só script via CLI).
- Migração de dados em produção (este plano é para banco **local**).

## Decisões de comportamento (confirmadas com o usuário)

| Tópico | Decisão |
|---|---|
| Localização dos PDFs | `/Hospital/atas-migracao/*.pdf` (um nível, 10–50 arquivos) |
| Ambiente | Banco **local** Supabase; dry-run JSON antes do apply |
| Threshold auto-match | **≥ 80** (auto) / **60–79** (sugestão no JSON) / **< 60** (externo) |
| Não-reconhecidos | Cria externo automático (is_externo=true, email=null — stub migration 026) |
| Duplicatas (hash existente) | Pula silenciosamente, loga no relatório |
| Inativos | Não casam — viram externos |
| Rename label | Incluído |

## Design

### 1. Matcher com score — `participant_matcher.py`

**Nova função pública:**
```python
@dataclass
class MatchResult:
    participante_id: str | None   # ID casado (None se strategy="nenhum" ou ambiguidade)
    score: int                    # 0-100; quem decide auto vs sugestao é o caller
    strategy: str                 # "exato" | "invertido" | "prefixo_unico" |
                                  # "primeiro_nome" | "nome_sobrenome_pair" |
                                  # "fuzzy" | "nenhum"
    candidates_ambiguos: list[str]  # ids quando 2+ candidatos empatam (score=0, id=None)

def match_single_name_scored(
    nome_raw: str,
    rows: list[dict],
    *,
    cargo_ia: str = "",
    setor_ia: str = "",
) -> MatchResult
```

**Cascata (scores fixos por estratégia):**

| # | Estratégia | Score | Exemplo |
|---|---|---|---|
| 1 | Exato normalizado | **100** | "Caroline Soares" → "Caroline Soares" |
| 2 | Invertido "Sobrenome, Nome" | **100** | "Soares, Caroline" → idem |
| 3 | Prefixo único dos 2 primeiros tokens | **95** | "Gisele Nunes" → "Gisele Nunes de Vasconcellos" |
| 4a | Primeiro-nome único | **90** | "Gisele" único → id |
| 4b | Primeiro-nome + desambig. cargo+setor | **85** | 2 "Marias", uma com cargo/setor que casa |
| 4c | Primeiro-nome + desambig. só cargo | **75** | |
| 4d | Primeiro-nome + desambig. só setor | **70** | |
| 5 | **NOVO: par nome+sobrenome** | **85** | "Maria Silva" → "Maria Fernanda Silva Souza" (primeiro e último bate) |
| 6 | Fuzzy (SequenceMatcher) | `round(ratio × 100)` se ratio ≥ 0.60 | "Gizele Nunes" vs "Gisele Nunes" → 88 |

Ordem da cascata: 1 → 2 → 3 → 4 → 5 → 6. Para e devolve na primeira que resolve com candidato único. Se 2+ candidatos empatam, devolve `candidates_ambiguos` e score=0.

**Algoritmo da estratégia 5 (par nome+sobrenome):**
- Tokens do nome IA com ≥ 2 palavras.
- Para cada row: tokens normalizados do `nome_completo`.
- Match se: `tokens_ia[0] in tokens_row` E `tokens_ia[-1] in tokens_row`. Score 85.
- Se empate (2+ rows), devolve todos em `candidates_ambiguos`, score 0.

**Threshold fuzzy:** abaixa de 0.85 → **0.60** (antes não retornava nada abaixo de 0.85; agora retorna com score proporcional até 0.60; abaixo de 0.60 não retorna).

**Retrocompatibilidade:**
- `match_single_name(nome_raw, rows, ...)` (já existente) passa a delegar para `match_single_name_scored()` retornando só `.participante_id` **apenas se score ≥ 80**. Comportamento idêntico ao atual nas chamadas existentes.
- `match_participants(...)` idem — internamente usa a função com score, só considera como "matched" rows com score ≥ 80; abaixo disso fica em `nao_reconhecidos` (mantém API externa).

Nota: o threshold default (80) é constante no módulo e configurável via parâmetro opcional `auto_threshold: int = 80`.

### 2. Script CLI — `backend/scripts/bulk_import_atas.py`

Irmão de `bulk_seed.py`. Usa `argparse` (padrão do projeto), lê `.env` via `app.config.settings`.

**Comandos:**

```bash
# Fase 1 — extração (sem tocar no banco)
uv run python scripts/bulk_import_atas.py dry-run \
    --dir ../../atas-migracao/ \
    --out ../../atas-migracao-preview.json

# Fase 2 — persistência (lê JSON e persiste)
uv run python scripts/bulk_import_atas.py apply \
    --in ../../atas-migracao-preview.json \
    --importador-id P001
```

**Flags:**
- `--limit N` — processa só primeiros N PDFs (teste).
- `--auto-match-threshold 80` (default).
- `--review-threshold 60` (default).

**Fluxo dry-run** (por PDF, sequencial):
1. Calcular hash do arquivo.
2. Consultar Supabase: `reunioes.arquivo_hash == hash` → se existe, marca `status: "duplicado"` no JSON e **não** chama IA (economia de tokens).
3. Parse PDF via `pdf_parser` existente.
4. Chamar `ai_processor.process_ata_migrada(pdf_text, paginas, ...)` — mesma função usada pelo endpoint `/preparar`.
5. Carregar participantes ativos: `SELECT id, nome_completo, cargo, setor, area FROM participantes WHERE ativo = true`.
6. Para cada participante extraído pela IA: chamar `match_single_name_scored()` → decide `resolucao` (auto_match / sugestao_pendente / externo_automatico).
7. Para cada pendência: resolver responsável pela mesma função, **restrito aos matched_ids da reunião** (invariante atual preservada).
8. Montar objeto `AtaPreviewItem` (schema abaixo) e adicionar à lista.

No final: gerar JSON e gravar em `--out`. Relatório no stdout: `{lidos}/{processados}/{duplicados}/{erros_extracao}`.

**Fluxo apply** (por item do JSON):
1. Validar JSON contra schema Pydantic novo.
2. Ler PDF do disco (caminho registrado no JSON).
3. Para cada participante `externo_automatico` OU `sugestao_pendente` **sem** `participante_id` manual: criar externo via `supabase.from_("participantes").insert({...})` com `is_externo=true, ativo=false, email=null` (stub migration 026). Coletar IDs.
4. Para cada `sugestao_pendente` com `participante_id` informado no JSON (review humano): usar esse ID.
5. Montar payload JSONB nos 3 formatos esperados pela RPC (`p_reuniao`, `p_pendencias`, `p_externos_links`) — **extrair a lógica** hoje em `routers/importacao.py:465-690` para um módulo novo `backend/app/services/importacao_service.py`, expondo `build_rpc_payload(req, file_bytes, importador_id, supabase) -> tuple[reuniao_dict, pendencias_list, externos_links_list]`. Tanto o router quanto o script passam a consumir esse helper.
6. Chamar `supabase.rpc("confirmar_importacao_atomico", {...})` — mesma RPC.
7. Registrar sucesso/erro por PDF.

No final: relatório com `importados`, `pulados_duplicata`, `erros`.

### 3. Schema do `preview.json`

```jsonc
{
  "gerado_em": "2026-04-20T22:45:00Z",
  "importador_id_default": null,                    // opcional, pode vir no --apply
  "total_pdfs": 23,
  "atas": [
    {
      "arquivo": "atas-migracao/reuniao_callcenter_190326.pdf",
      "arquivo_hash": "sha256:abc123...",
      "status": "pronto",                           // "pronto" | "duplicado" | "erro_extracao"
      "duplicado_de": null,                         // id_reuniao existente se duplicado
      "paginas": 4,
      "metadados": {
        "titulo": "Reunião Call Center 19/03/2026",
        "tipo": "Coordenação",
        "data": "2026-03-19",
        "hora_inicio": "14:00",
        "hora_fim": "15:30",
        "facilitador_id": null,                     // preenche se extrair e matchear
        "assunto": "...",
        "objetivo": "..."
      },
      "participantes": [
        {
          "nome_ia": "Caroline Soares",
          "cargo_ia": "Gerente",
          "setor_ia": "Operações",
          "resolucao": "auto_match",
          "participante_id": "P012",
          "score": 100,
          "strategy": "exato",
          "candidates_ambiguos": []
        },
        {
          "nome_ia": "Maria Silva",
          "cargo_ia": "Analista",
          "setor_ia": "",
          "resolucao": "sugestao_pendente",
          "participante_id": null,                  // editar aqui pra confirmar
          "sugestao_participante_id": "P078",
          "score": 72,
          "strategy": "nome_sobrenome_pair",
          "candidates_ambiguos": [],
          "fallback_se_nao_confirmado": "externo"
        },
        {
          "nome_ia": "Pedro Ribeiro",
          "cargo_ia": "Analista TI",
          "setor_ia": "",
          "resolucao": "externo_automatico",
          "participante_id": null,
          "score": 0,
          "strategy": "nenhum"
        }
      ],
      "pendencias": [
        {
          "acao": "Enviar relatório mensal",
          "responsavel_nome_ia": "Gisele Nunes",
          "responsavel_resolucao": "auto_match",
          "responsavel_id": "P034",
          "responsavel_score": 95,
          "responsavel_strategy": "prefixo_unico",
          "cargo": "Coordenadora",
          "prazo": "2026-04-01",
          "prazo_original": "próxima sexta",
          "meta_entregavel": "...",
          "status": "PENDENTE"
        }
      ],
      "registro_narrativo": "...",
      "resumo_executivo": "...",
      "warnings": []
    }
  ]
}
```

**Edição manual esperada:**
- Trocar `resolucao: "sugestao_pendente"` → `resolucao: "auto_match"` + preencher `participante_id` com `sugestao_participante_id`, se concordar.
- Forçar um match manual em qualquer participante.
- Corrigir metadados (data, título, tipo).
- **Não editar:** `arquivo_hash`, `status`, `duplicado_de` (controle do dry-run).

### 4. Rename label "importar ATA antiga" → "importar ATA"

Apenas strings do frontend. URL/endpoint/status ficam.

**Arquivos a procurar e ajustar:**
- `frontend/src/app/reunioes/importar/page.tsx` — título `<h1>`, breadcrumbs, mensagens.
- `frontend/src/app/reunioes/page.tsx` — botão/link "Importar ATA antiga" se houver.
- `frontend/src/components/` — procurar string literal "antiga" relacionada a importação.

Fazer `grep` em `frontend/src/**/*.tsx` por `"Importar ATA"` e por `"ATA antiga"` antes de editar.

## Arquivos a modificar / criar

**Backend (criar):**
- `backend/scripts/bulk_import_atas.py` — script CLI novo (~350 linhas estimadas).
- `backend/app/services/importacao_service.py` — helper novo `build_rpc_payload(...)` extraído do router + `generate_reuniao_id(data)` extraído de `routers/importacao.py::_generate_reuniao_id`. Router e script passam a importar daqui.

**Backend (modificar):**
- `backend/app/services/participant_matcher.py`:
  - Adicionar `@dataclass MatchResult` (ou TypedDict).
  - Adicionar função interna `_match_nome_sobrenome_pair(tokens_ia, rows) → (id | None, candidatos)`.
  - Adicionar `match_single_name_scored(...)` com a cascata 1–6 retornando `MatchResult`.
  - Refatorar `match_single_name()` e `match_participants()` para delegarem a `match_single_name_scored()` e filtrarem por score ≥ threshold.
  - Abaixar `_FUZZY_THRESHOLD` de 0.85 → 0.60 (retorna score proporcional acima disso).
- `backend/app/routers/importacao.py`:
  - Substituir uso interno de `_generate_reuniao_id` pelo import em `services/importacao_service.py`.
  - Refatorar o bloco `routers/importacao.py:465-690` para delegar ao `build_rpc_payload()` do novo service (comportamento idêntico).

**Backend (testes):**
- `backend/tests/test_participant_matcher.py` — adicionar casos:
  - `test_match_result_score_exato_100`
  - `test_nome_sobrenome_pair_basico` ("Maria Silva" → "Maria Fernanda Silva Souza", score 85)
  - `test_nome_sobrenome_pair_ambiguo` (2 Marias Silva → retorna candidates_ambiguos)
  - `test_fuzzy_abaixo_60_retorna_nenhum`
  - `test_fuzzy_entre_60_e_80_retorna_sugestao` (score 70, resolucao='sugestao_pendente')
  - `test_backcompat_match_single_name_retorna_id_so_se_score_80`

**Frontend (modificar):**
- `frontend/src/app/reunioes/importar/page.tsx` — labels.
- `frontend/src/app/reunioes/page.tsx` — botão, se houver.
- Outros componentes — identificar via grep "ATA antiga".

**Não modificar:**
- `backend/app/pipeline/orchestrator.py` — fluxo ao vivo intacto.
- `backend/app/services/ai_processor.py` — reusa `process_ata_migrada` como está.
- Migrations SQL — não precisa de migration nova.

## Funções reutilizadas (não reescrever)

- `pdf_parser.calcular_hash(bytes)` e `pdf_parser.extract_pages()` — hash e extração.
- `ai_processor.process_ata_migrada(pdf_text, paginas, ...)` — chamada à OpenAI.
- `participant_matcher._normalize()`, `_clean_name()`, `_first_name()`, `_invert_surname_first()`, `_context_matches()` — auxiliares, permanecem como estão.
- `supabase.rpc("confirmar_importacao_atomico", ...)` — RPC atômica (migration 024) reutilizada pelo script de apply.
- `_check_duplicata(supabase, hash, documento_id)` em `routers/importacao.py:135-154` — verificação de duplicata compartilhada (extrair junto com `build_rpc_payload` para `services/importacao_service.py`).

## Verificação

### 1. Testes unitários do matcher
```bash
cd hospital-reunioes/backend
uv run pytest tests/test_participant_matcher.py -v
```
Esperado: todos os testes antigos continuam passando; novos testes passam.

### 2. Dry-run com fixtures controladas

Criar `atas-migracao/` na raiz com 2 PDFs (o que já está em `/Hospital/ATA_CallCenter_19032026 - Clicksign.pdf` + 1 de teste):

```bash
cd hospital-reunioes/backend
uv run python scripts/bulk_import_atas.py dry-run \
    --dir ../../atas-migracao/ \
    --out ../../preview-teste.json --limit 2
```

Validar manualmente:
- `preview-teste.json` tem 2 entradas em `atas[]`.
- Cada entrada tem `score` em participantes.
- Pelo menos 1 participante com `resolucao: "auto_match"`.

### 3. Apply em banco local
```bash
# com Supabase local rodando
uv run python scripts/bulk_import_atas.py apply \
    --in ../../preview-teste.json \
    --importador-id P001
```

Validar:
- Script termina sem erro.
- Abrir frontend `/reunioes` — 2 atas novas aparecem com label/status "MIGRADA".
- Abrir uma delas — pendências listadas, participantes vinculados com badges corretos (interno vs externo).

### 4. Idempotência
Rodar `apply` de novo com o mesmo JSON:
- Esperado: todas marcadas como "duplicado" e nada é inserido.
- Relatório mostra `importados: 0, pulados_duplicata: 2`.

### 5. Rename label (manual)
- Abrir frontend em `/reunioes/importar` → título agora "Importar ATA".
- Menu/sidebar/botão — mesma coisa.

### 6. Regressão do fluxo ao vivo
- Subir uma transcrição pelo fluxo normal (Fireflies ou upload manual).
- Confirmar que os participantes são matchados como antes (não deve haver nenhuma mudança perceptível — a refatoração preservou a API com threshold 80).

## Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Score da estratégia "nome_sobrenome_pair" muito permissivo (80+) gera falso-positivo | Score fixo em 85 — fica acima do threshold 80 mas testamos casos ambíguos; se falhar em review, pode ser reduzido para 75 sem mudança de estrutura |
| OpenAI gastar muito token nos 50 PDFs | Script loga tokens/PDF; usuário pode usar `--limit` para testar e pausar |
| Supabase local fora do ar durante dry-run (precisa ler participantes ativos) | Script faz fail-fast com mensagem clara antes de consumir OpenAI |
| JSON editado manualmente com inconsistência (ex: `participante_id` inexistente) | Apply valida cada ID antes de chamar RPC; erros reportados por item sem abortar o lote |
| Reunião com facilitador não identificado no PDF | `facilitador_id=null` é aceito pelo schema (FK opcional em migration 002) |

## Pós-implementação

Gerar arquivo em `implementacoes/YYYY-MM-DD_HHmm_bulk-import-atas-matcher-score.md` conforme CLAUDE.md, com:
- O que mudou (funcional)
- Por que mudou
- Arquivos alterados
- Ações necessárias (ex: colocar PDFs em `atas-migracao/`, rodar comandos)

Atualizar `hospital-reunioes/PRODUCAO.md` se ele voltar a existir — adicionar seção sobre o script bulk (§scripts).
