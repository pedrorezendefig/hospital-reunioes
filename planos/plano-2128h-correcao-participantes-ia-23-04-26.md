# Plano — Apontar interno existente ao resolver participantes não reconhecidos

## Context

Hoje, quando uma transcrição (.txt) é processada pela IA no fluxo de reunião nova, a IA extrai os nomes mencionados e um **matcher por nome** tenta casar cada um com a tabela `participantes` (internos ativos). Os que batem entram como participantes internos da reunião; os que não batem caem no JSONB `reunioes.participantes_nao_reconhecidos` e aparecem na UI em `AGUARDANDO_RESOLUCAO`, seção "Participantes Não Cadastrados" (`frontend/src/app/reunioes/[id]/page.tsx` linhas 1627-1689).

A UI atual só oferece **cadastrar como externo** ou **ignorar**. Quando o matcher falha por similaridade insuficiente (ex: transcrição "João Silva" vs. banco "João Carlos Silva"), o facilitador é forçado a cadastrar como externo alguém que **já existe como interno** — gera duplicatas.

**Objetivo:** permitir que o facilitador, naquele mesmo ponto, **aponte um participante já existente no banco** (interno ativo ou externo já cadastrado) em vez de ser obrigado a cadastrar um novo registro. Escopo: só `AGUARDANDO_RESOLUCAO`.

---

## Decisões de produto (confirmadas com o usuário)

1. **Momento:** só em `AGUARDANDO_RESOLUCAO` (seção "Participantes Não Cadastrados").
2. **UX:** combobox unificado de busca por linha — digita, lista internos ativos + externos cadastrados como resultados; rodapé fixo permite "Cadastrar como externo" com o texto digitado.
3. **Escopo da busca:** internos ativos + externos já cadastrados (inativos ficam de fora).
4. **Texto da ata:** permanece como a IA escreveu — só muda a lista de participantes da reunião.
5. **Email no cadastro de externo:** vira opcional (banco já suporta `email NULL` desde migration 026).
6. **Botão "Ignorar" permanece** (caso de nome fantasma da transcrição).

---

## Passo 0 — Validação pré-implementação (obrigatório)

Antes de qualquer mudança de código, confirmar:

1. **Endpoint `GET /api/participantes`** (`backend/app/routers/participantes.py:26-48`) aceita retornar externos? Se não, adicionar query param `incluir_externos: bool = False` (default mantém comportamento atual das outras telas).
2. **Endpoint de resolução dos não reconhecidos hoje** — qual é o nome exato, onde fica (router + service), e qual o schema de input atual. Procurar em `backend/app/routers/reunioes.py`, `backend/app/services/` por termos `nao_reconhecido`, `resolver`, `AGUARDANDO_RESOLUCAO`. Esse é o endpoint que vamos estender.
3. **JSONB `participantes_nao_reconhecidos`** — formato exato das entradas (só `nome_identificado` ou tem mais campos como `cargo`, `confianca`?). Afeta o payload que o frontend envia de volta.

---

## Passo 1 — Backend: schemas e endpoint

**Arquivos:**
- `backend/app/models/schemas.py` — adicionar novos Pydantic models
- `backend/app/routers/reunioes.py` (ou router equivalente de resolução) — estender endpoint existente
- `backend/app/services/<service_de_resolucao>.py` — estender lógica de resolução

**Mudanças em `schemas.py`:**

```python
class NovoExternoDados(BaseModel):
    nome_completo: str
    email: Optional[EmailStr] = None  # opcional — alinhado com migration 026
    cargo: Optional[str] = None

class ResolverNaoReconhecidoItem(BaseModel):
    nome_identificado: str  # chave de correspondência no JSONB
    acao: Literal["vincular", "cadastrar_externo", "ignorar"]
    participante_id: Optional[str] = None      # obrigatório quando acao="vincular"
    novo_externo: Optional[NovoExternoDados] = None  # obrigatório quando acao="cadastrar_externo"

    @model_validator(mode="after")
    def validar_payload_por_acao(self):
        if self.acao == "vincular" and not self.participante_id:
            raise ValueError("participante_id obrigatório para acao='vincular'")
        if self.acao == "cadastrar_externo" and not self.novo_externo:
            raise ValueError("novo_externo obrigatório para acao='cadastrar_externo'")
        return self
```

**Schema do endpoint:** usa `list[ResolverNaoReconhecidoItem]`. Se o endpoint atual já recebe lista (provável — hoje há form em lote na UI), só trocar o item type.

**Lógica no service (transação única por request):**

- `acao="vincular"`:
  - `SELECT id, ativo, is_externo FROM participantes WHERE id = :participante_id`
  - Se não existe → 404. Se `ativo=false` → 400 "participante inativo".
  - `INSERT INTO reuniao_participantes (id_reuniao, participante_id) VALUES (...) ON CONFLICT (id_reuniao, participante_id) DO NOTHING`
  - Remover `nome_identificado` do JSONB `participantes_nao_reconhecidos`.
- `acao="cadastrar_externo"`:
  - Criar `participantes` com `is_externo=true, ativo=true, email` (nullable).
  - Gerar `id` via função existente `generate_participant_id()` (migration 001).
  - INSERT em `reuniao_participantes` como acima.
  - Remover do JSONB.
- `acao="ignorar"`:
  - Só remover do JSONB.

Tudo numa transação por request (atomicidade total ou rollback).

**Endpoint `GET /api/participantes`:** se não aceitar hoje, adicionar:
```python
@router.get("")
def listar_participantes(..., incluir_externos: bool = False):
    query = ...
    if not incluir_externos:
        query = query.filter(Participante.is_externo == False)
    # resto igual
```
Default `False` garante que nenhuma tela existente muda comportamento.

---

## Passo 2 — Frontend: componente compartilhado

**Novo arquivo:** `frontend/src/components/participantes/ParticipanteCombobox.tsx`

**Props:**
```ts
type ParticipanteComboboxProps = {
  nomeSugerido: string;          // texto inicial (nome que a IA ouviu)
  onSelecionarExistente: (p: ParticipanteResponse) => void;
  onCadastrarExterno: (dados: { nome_completo: string; email?: string; cargo?: string }) => void;
  onIgnorar: () => void;
  estado: "pendente" | "vinculado" | "cadastrado" | "ignorado";
  resumo?: string;               // texto exibido quando já tem estado definido
};
```

**Comportamento:**
- Input de busca com valor inicial = `nomeSugerido`, debounce 250ms.
- Fetch `GET /api/participantes?q={termo}&ativo=true&incluir_externos=true&limit=10`.
- Dropdown com 2 grupos:
  - **Internos** (badge emerald)
  - **Externos cadastrados** (badge amber)
- Rodapé fixo: `+ Cadastrar "<termo>" como externo` → expande mini-form inline com email (opcional) e cargo (opcional).
- Após selecionar/cadastrar/ignorar: linha colapsa e mostra `resumo` com botão "Alterar" pra revisar.
- Acessibilidade: ArrowUp/Down navega, Enter seleciona, Esc fecha.
- Padrão visual: segue `AdminModal` e cores do design system existente.

**Hook de busca reusável:** `frontend/src/hooks/useBuscaParticipantes.ts` — encapsula debounce + fetch + cache local. Pequeno, testável.

---

## Passo 3 — Integração na tela `/reunioes/[id]`

**Arquivo:** `frontend/src/app/reunioes/[id]/page.tsx` (linhas 1627-1689 hoje).

**Mudanças:**
- Substituir o bloco atual `[Nome completo][Email *][Cargo]` pela linha `ParticipanteCombobox`.
- Estado local: `const [resolucoes, setResolucoes] = useState<Record<string, ResolverNaoReconhecidoItem>>({})`, chaveado por `nome_identificado`.
- Botão "Confirmar e Continuar":
  - Valida que todas as linhas têm `acao` definida.
  - Chama `POST /api/reunioes/{id}/<endpoint_de_resolucao>` com o array.
  - Em sucesso: reload da reunião (status passa a `AGUARDANDO_VALIDACAO`).
- Botão "Ignorar e Continuar" globalmente: marca todas as pendentes como `ignorar` e envia.

---

## Passo 4 — Testes

**Backend (`pytest`):**
- `tests/services/test_resolver_nao_reconhecidos.py`:
  - `test_vincular_interno_ativo_adiciona_em_reuniao_participantes`
  - `test_vincular_interno_inexistente_retorna_404`
  - `test_vincular_interno_inativo_retorna_400`
  - `test_vincular_duplicado_nao_falha` (ON CONFLICT DO NOTHING)
  - `test_cadastrar_externo_sem_email_ok` (migration 026)
  - `test_cadastrar_externo_com_email_duplicado_retorna_400` (UNIQUE email)
  - `test_ignorar_remove_do_jsonb_sem_criar_participante`
  - `test_mix_resolucoes_transacao_atomica` (vincular + cadastrar + ignorar num request)

**Frontend (Vitest + Testing Library):**
- `__tests__/ParticipanteCombobox.test.tsx`:
  - render com `nomeSugerido` preenchido
  - busca chama endpoint com debounce
  - seleção de interno dispara `onSelecionarExistente`
  - clique em "Cadastrar como externo" expande mini-form e dispara `onCadastrarExterno`
  - "Ignorar" dispara `onIgnorar`

---

## Passo 5 — Verificação end-to-end (manual, antes de commitar)

1. Subir stack com `/atualizar-app`.
2. Login como facilitador.
3. Criar reunião nova, subir transcrição .txt com menção a um interno existente usando nome parcial/diferente (ex: "João Silva" pro "João Carlos Silva" do banco).
4. Aguardar IA processar (status vira `AGUARDANDO_RESOLUCAO`).
5. Na seção "Participantes Não Cadastrados", verificar:
   - Combobox aparece com "João Silva" já digitado.
   - Buscar mostra o "João Carlos Silva" interno + qualquer externo cadastrado com nome similar.
   - Selecionar o interno → linha colapsa com "Vinculado: João Carlos Silva".
6. Confirmar → checar no banco:
   - `reuniao_participantes` tem o `participante_id` correto.
   - `reunioes.participantes_nao_reconhecidos` foi limpo dessa entrada.
   - Nenhum participante novo foi criado.
7. Repetir com: nome novo real (cadastrar como externo, com e sem email), nome fantasma (ignorar).
8. Checar que status transitou pra `AGUARDANDO_VALIDACAO` e ata ficou intacta em texto.

---

## Arquivos críticos (resumo)

**Modificar:**
- `backend/app/models/schemas.py`
- `backend/app/routers/<router_de_resolucao>.py` (confirmar no passo 0)
- `backend/app/services/<service_de_resolucao>.py` (confirmar no passo 0)
- `backend/app/routers/participantes.py` (só se `incluir_externos` não existir hoje)
- `frontend/src/app/reunioes/[id]/page.tsx` (linhas 1627-1689)

**Criar:**
- `frontend/src/components/participantes/ParticipanteCombobox.tsx`
- `frontend/src/hooks/useBuscaParticipantes.ts`
- `backend/tests/services/test_resolver_nao_reconhecidos.py`
- `frontend/src/components/participantes/__tests__/ParticipanteCombobox.test.tsx`

**Reusar (não modificar):**
- `generate_participant_id()` (SQL function, migration 001)
- `GET /api/participantes` (estender só se necessário)
- `AdminModal` e padrões visuais do design system

---

## Fora de escopo (deixar pra depois se comprovada demanda)

- Reclassificar participantes em `AGUARDANDO_VALIDACAO` ou depois de aprovada.
- Cadastrar novo interno inline (continua via super-admin).
- Substituir menções ao nome no texto da ata.
- Migrar `ResponsavelCombobox` da tela `/reunioes/importar` para usar o novo `ParticipanteCombobox` compartilhado (possível ganho de DRY, zero bloqueio agora).
