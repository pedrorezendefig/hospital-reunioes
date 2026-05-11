# Plano — Matching de responsável de ação na importação de ATA antiga

## Contexto

Na tela de importação de ATA migrada, a IA extrai uma ação cujo responsável é "Gisele Nunes". No banco existe "Gisele Nunes de Vasconcellos" cadastrada e ativa. A UI exibe a mensagem vermelha **"A IA sugeriu 'Gisele Nunes', mas este nome não está cadastrado. Escolha uma pessoa ou crie como externo."** Enquanto isso, o autocomplete do mesmo campo consegue encontrar "Gisele Nunes de Vasconcellos" quando o usuário digita — ou seja, a pessoa está cadastrada, mas o auto-match falhou.

**Causa raiz:** em `hospital-reunioes/backend/app/routers/importacao.py:260-273`, a resolução do responsável da pendência é um `dict.get()` por **nome inteiro normalizado** no `matched_by_norm`, que só contém a forma completa ("gisele nunes de vasconcellos"). O matcher de participantes em `participant_matcher.py` já tem uma cascata de 6 estratégias (incluindo **prefixo único** na linha 190-198, que casaria o caso), mas essa cascata é aplicada apenas ao matching de participantes da reunião — não ao responsável de cada ação.

**Resultado esperado:** o responsável da ação passar pela mesma cascata do matcher, casando "Gisele Nunes" → "Gisele Nunes de Vasconcellos" via a estratégia de prefixo único. Se a busca ficar ambígua (2+ candidatos), o responsável continua como não identificado e a mensagem vermelha é mantida (comportamento conservador).

## Escopo

- Somente o fluxo de **importação** de ATA antiga (`POST /api/reunioes/importacao/preparar`).
- Fluxo ao vivo (`pendencia_service._find_participante_id`) fica como está — não mexe.
- Frontend não precisa de alteração: o mesmo endpoint continua devolvendo `responsavel_id` ou `responsavel_externo_idx`; quando o responsável casar pela cascata, a mensagem vermelha some automaticamente.

## Design

### 1. Extrair função de resolução unitária em `participant_matcher.py`

Extrair a cascata atual do loop em `match_participants` para uma função pública reutilizável:

```python
def match_single_name(
    nome_raw: str,
    rows: list[dict],
    *,
    cargo_ia: str = "",
    setor_ia: str = "",
) -> str | None:
    """
    Aplica a cascata de 6 estratégias a um nome avulso e retorna o
    participante_id ou None se não houver match único.
    """
```

A função constrói os índices (`exact_map`, `by_first`, `token_rows`) a partir de `rows` e executa as mesmas 6 estratégias: exato, invertido, prefixo-único, primeiro-nome, cargo/setor, fuzzy. Retorna `None` em caso de ambiguidade ou nenhum match — respeitando a escolha do usuário de manter a mensagem vermelha em casos ambíguos.

Refatorar `match_participants` para construir os índices uma única vez e delegar cada nome à nova função (ou uma variante interna que recebe índices pré-construídos, para evitar rebuild por chamada). Proposta:

- Extrair uma função privada `_match_one(normalized, tokens, cargo_ia, setor_ia, exact_map, by_first, token_rows) -> str | None` com a cascata pura.
- A pública `match_single_name` é um wrapper que monta os índices e chama `_match_one`.
- `match_participants` monta índices uma vez e chama `_match_one` em loop.

Resultado: zero duplicação, comportamento idêntico ao atual para participantes.

### 2. Usar a cascata para resolver responsável de cada pendência em `importacao.py`

Na seção "8. Resolução responsável → matched_id ou externo_idx" (linhas 260-273), substituir o `matched_by_norm.get(nome_norm)` por:

1. Primeiro tentar casar o responsável contra os **participantes internos ativos já carregados** (`participantes_ativos` da linha 219), via `match_single_name`. Passa cargo da ação (`q.get("cargo")`) apenas como fallback informativo — a desambiguação por cargo/setor já está dentro da cascata.
2. Restringir o resultado: o responsável só pode casar em participantes que **também** apareceram em `matched_ids` (ou seja, foram identificados como participantes da reunião). Isso mantém a invariante atual (o responsável de uma ação é alguém que esteve na reunião) e evita atribuir uma ação a uma pessoa aleatória do banco que não participou.
3. Se `match_single_name` retornar `None` (sem match ou ambíguo), cai para o fallback atual de `externo_by_norm` (exact match em não reconhecidos).
4. Se nenhum dos dois resolver, fica como antes: `responsavel_id=None`, `responsavel_externo_idx=None`, UI exibe a mensagem vermelha.

### 3. Sem mudanças no frontend

O componente `PendenciaCard` (`frontend/src/app/reunioes/importar/page.tsx:1938-1989`) continua renderizando a mensagem vermelha apenas quando `responsavel_id` e `responsavel_externo_idx` são ambos nulos. Quando o backend casar via cascata, a UI já vem com `responsavel_id` preenchido e o card inicia em estado verde. Nada a tocar.

## Arquivos a modificar

- `hospital-reunioes/backend/app/services/participant_matcher.py` — extrair `_match_one` + `match_single_name`; refatorar `match_participants` para usar `_match_one`.
- `hospital-reunioes/backend/app/routers/importacao.py` — usar `match_single_name` na resolução do responsável da pendência (linhas ~260-273), restrito aos matched_ids.

Nenhum outro arquivo afetado. `pendencia_service.py` fica intacto.

## Funções reutilizadas

- `participant_matcher._normalize(name)` (linha 34) — normalização honorífica + lowercase, já consumida em importacao.py.
- `participant_matcher._clean_name(name)` (linha 40) — só usada em logging no matcher, não muda.
- `participant_matcher._invert_surname_first`, `_first_name`, `_context_matches` — usadas internamente na cascata, ficam como estão.

## Verificação

1. **Teste manual (caminho feliz do bug):**
   - Subir o backend (`cd hospital-reunioes/backend && uvicorn app.main:app --reload`) e o frontend (`cd hospital-reunioes/frontend && npm run dev`).
   - Ir em `Reuniões → Importar ATA antiga` e subir o mesmo PDF que reproduziu o problema.
   - Confirmar que a pendência de "Gisele Nunes" aparece já vinculada a **Gisele Nunes de Vasconcellos** (sem mensagem vermelha), o card abre em estado verde.
2. **Teste manual (ambiguidade):**
   - Cadastrar temporariamente uma segunda pessoa cujo prefixo bata (ex.: "Gisele Nunes Silva").
   - Importar a mesma ATA. A pendência deve continuar **não identificada** (mensagem vermelha preservada), confirmando que ambiguidade não resolve automaticamente.
3. **Teste manual (não regressão do matcher de participantes):**
   - Reprocessar qualquer ATA ao vivo (gravação → geração). O matcher de participantes deve continuar identificando a mesma quantidade de pessoas de antes (refatoração sem mudança de comportamento).
4. **Teste unitário opcional:** adicionar um caso em `participant_matcher_test` (se existir) chamando `match_single_name("Gisele Nunes", rows_com_gisele_completa)` e esperar o id retornado. Caso exista `tests/` no backend, adicionar também caso ambíguo retornando `None`.

## Fora de escopo

- Relaxar threshold de fuzzy (0.85 hoje).
- Mudar `_find_participante_id` do fluxo ao vivo.
- Alterar autocomplete do frontend para normalização por acento/tokenização.
- Expor cargo/setor da ação como canal de desambiguação adicional (a cascata já faz quando houver dados).
