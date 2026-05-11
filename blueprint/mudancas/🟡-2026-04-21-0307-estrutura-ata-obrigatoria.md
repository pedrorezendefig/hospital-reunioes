# Plano — Adaptar ATA à Estrutura Obrigatória HSM

> Observação: conforme `CLAUDE.md` do projeto ("Quando o usuário pedir planejamento, criar o plano como `.md` na raiz do projeto"), este arquivo será copiado para `/Users/pedrorezende/PedroDev/Hospital/plano-estrutura-ata-obrigatoria.md` ao sair do Plan Mode.

---

## 1. Contexto

Você enviou a **estrutura obrigatória** do modelo oficial de ATA do Hospital São Matheus, com 6 seções numeradas:

1. **Cabeçalho** (Instituição fixa "Hospital São Matheus", Tipo de documento, Data, Horário, Local)
2. **Participantes** (internos + "Referências externas mencionadas" em tabela separada)
3. **Objetivo da Reunião** (parágrafo único ≤ 5 linhas)
4. **Discussão dos Pontos** (4.1, 4.2, 4.3… cada um com descrição, contribuições por função, divergências, decisão, responsável)
5. **Quadro de Pendências, Decisões e Responsáveis** (tabela: ação | responsável | objetivo/meta | prazo | status; suporta "Fluxo contínuo")
6. **Espaço para Assinaturas** (tabela: nome | cargo | assinatura | data)

### Diagnóstico da base atual

Mapeamento executado mostrou que o projeto **já está ~85% alinhado** com essa estrutura:

- **JSON schema (`json_ata`)** já comporta as 6 seções: `participantes[]`, `referencias_externas[]`, `objetivo`, `discussao[]` (com `contribuicoes`, `divergencias`, `decisao`, `responsavel`), `quadro_atribuicoes[]`.
- **Template PDF** (`ata_template.html` + WeasyPrint) já renderiza todas as 6 seções.
- **Prompts de extração** já mencionam "modelo HSM com 6 seções".

O que **não está alinhado** (divergências que este plano fecha):

- Seções extras não previstas no modelo obrigatório: `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas`.
- PDF **sem numeração visual** das seções (os `<h2>` atuais são "Participantes", "Objetivo da Reunião" — sem "1.", "2.", "3.").
- Cabeçalho dividido em dois blocos (branding + metadados em grid) em vez de um bloco único "1. Cabeçalho" com lista formal de 5 campos.
- Campo "Instituição: Hospital São Matheus" não existe como campo nomeado — está apenas na tagline.
- "Tipo de Reunião" precisa virar "Tipo de documento" conforme modelo.
- "Status: Aguardando Validação" no cabeçalho não faz parte da estrutura obrigatória.
- Prompt de **importação legada** (`extracao_ata_migrada.md`) produz `registro_narrativo` em prosa contínua em vez de `discussao[]` estruturado — viola a seção 4.
- Template tem fallback que renderiza `registro_narrativo` quando `discussao` está vazio — mais uma violação.

### Decisões aprovadas (via AskUserQuestion)

| Ponto | Decisão |
|---|---|
| Seções extras (Resumo Executivo, Próxima Reunião, Lacunas Identificadas) | **Remover completamente** do prompt e do PDF. |
| ATAs legadas importadas | **Estruturar em `discussao[]` (4.1, 4.2…)** — reescrever prompt de importação para extrair tópicos discretos. |
| Frontend (editor de tópicos/referências) | **Não nesta rodada.** Edição continua via chat de correção IA. |
| Cabeçalho | **Logo + tagline preservados no topo** + seção "1. Cabeçalho" com lista formal; ID e "Gerado em" vão para rodapé. |

### Resultado esperado

Toda ATA gerada pelo sistema (nova ou importada) respeita a estrutura oficial HSM de 6 seções numeradas, sem informação extra fora do contrato. Design visual do PDF (cores #232d69, tipografia Helvetica, badges, quebras de página) **preservado**.

---

## 2. Arquivos a modificar

Todos os caminhos são relativos à raiz `/Users/pedrorezende/PedroDev/Hospital/`.

### Backend — Prompts (6 arquivos)

| # | Arquivo | Tipo de mudança |
|---|---------|-----------------|
| 1 | `hospital-reunioes/backend/app/prompts/extracao_ata.md` | **Média**: reforçar estrutura obrigatória; remover `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas` do schema. |
| 2 | `hospital-reunioes/backend/app/prompts/user_extracao.md` | Pequena: ajustar se referenciar campos removidos. |
| 3 | `hospital-reunioes/backend/app/prompts/correcao_ata.md` | Média: mesmo alinhamento do #1; cuidar da cláusula de retrocompatibilidade `registro_narrativo`. |
| 4 | `hospital-reunioes/backend/app/prompts/user_correcao.md` | Pequena: idem. |
| 5 | `hospital-reunioes/backend/app/prompts/extracao_ata_migrada.md` | **Grande**: substituir `registro_narrativo` por `discussao[]` estruturado; remover `resumo_executivo`, `proxima_reuniao`; adicionar instruções para a IA organizar a prosa legada em tópicos discretos. |
| 6 | `hospital-reunioes/backend/app/prompts/user_extracao_ata_migrada.md` | Pequena: reforçar intenção de estruturar, não só narrar. |
| 7 | `hospital-reunioes/backend/app/prompts/chat_correcao_system.md` | Pequena: remover referências aos 3 campos excluídos, se houver. |

### Backend — Código Python (2 arquivos)

| # | Arquivo | Tipo de mudança |
|---|---------|-----------------|
| 8 | `hospital-reunioes/backend/app/services/ai_processor.py` | Pequena: atualizar mocks `_mock_ata()` (linhas ~408–434) e `_mock_ata_migrada()` (linhas ~243–300) para refletir o novo schema (sem campos removidos; com `discussao[]` em ambos). |
| 9 | `hospital-reunioes/backend/app/services/pdf_generator.py` | Pequena: formatação de data/horário para o novo bloco "1. Cabeçalho" (se necessário). |

### Backend — Template PDF (1 arquivo, mudança grande)

| # | Arquivo | Tipo de mudança |
|---|---------|-----------------|
| 10 | `hospital-reunioes/backend/app/templates/ata_template.html` | **Grande reestruturação visual do layout** (design preservado). Ver §3.3. |

### Frontend — Tipos (1 arquivo)

| # | Arquivo | Tipo de mudança |
|---|---------|-----------------|
| 11 | `hospital-reunioes/frontend/src/types/index.ts` | Pequena: no tipo `JsonAta` (linhas 182–198), marcar `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas`, `registro_narrativo` como opcionais com comentário `/** @deprecated — pré-migração HSM */` para tolerar ATAs antigas no banco sem quebrar TS. **Não remover** — ATAs legadas no banco ainda têm esses campos. |

### Banco de dados

**Nada a mudar.** A coluna `reunioes.json_ata` é `JSONB` sem schema constraint. JSONs antigos com os campos removidos continuam válidos.

### Não mexer (escopo futuro)

- `frontend/src/app/reunioes/[id]/page.tsx` — página de detalhe, sem editor de tópicos/referências.
- Componentes `ChatCorrecao.tsx`, `InlineEditField.tsx`, etc.
- Tabelas Supabase (`reunioes`, `pendencias`, `participantes`, `reuniao_participantes`).
- Skill `/migrar-atas` e script `bulk_import_atas.py` — continuam funcionando porque o schema do JSON de preview permanece compatível (só muda o conteúdo do campo `json_ata`, que a skill já trata como opaco).

---

## 3. Mudanças detalhadas

### 3.1 Prompt `extracao_ata.md`

**Remover do schema JSON (linhas 22–65):**

```json
// REMOVER estas três linhas:
"resumo_executivo": "2-3 frases resumindo os pontos mais importantes",
"proxima_reuniao": "data/hora da próxima reunião ou null",
"lacunas_identificadas": [...]
```

**Reforçar a estrutura obrigatória na abertura (linha 3):**

Substituir o parágrafo atual por algo equivalente a:

> "O resultado deve sair em JSON estruturado conforme o schema abaixo. Ele será renderizado em PDF no modelo oficial do Hospital São Matheus, composto por **exatamente 6 seções obrigatórias e somente estas**: (1) Cabeçalho, (2) Participantes + Referências externas mencionadas, (3) Objetivo da Reunião, (4) Discussão dos Pontos (numerada 4.1, 4.2…), (5) Quadro de Pendências/Decisões/Responsáveis, (6) Espaço para Assinaturas. Nenhuma seção extra deve ser produzida."

**Remover seções correspondentes:** qualquer bloco de regras sobre os 3 campos removidos.

### 3.2 Prompt `extracao_ata_migrada.md` (mudança grande)

**Antes (linha 23):** `"registro_narrativo": "resumo objetivo do que foi discutido, em prosa"`

**Depois:** substituir por `discussao[]` estruturado idêntico ao de `extracao_ata.md`:

```json
"discussao": [
  {
    "titulo": "título do tema (IA deve segmentar a prosa em tópicos discretos)",
    "descricao": "descrição objetiva do que foi apresentado/debatido",
    "contribuicoes": [
      {"funcao": "cargo/função", "conteudo": "essência da fala, se identificável"}
    ],
    "divergencias": ["se houver ressalvas registradas no texto legado"],
    "decisao": "decisão tomada ou 'A definir'",
    "responsavel": "nome civil ou null"
  }
]
```

**Adicionar bloco de regras sobre estruturação legada:**

> "## Como estruturar a prosa legada em tópicos (4.1, 4.2…)
> A ATA original está em prosa contínua (seções 'ABERTURA E CONTEXTO', 'DISCUSSÕES', 'DECISÕES FORMAIS'). Sua tarefa é **segmentar essa prosa em tópicos discretos** para `discussao[]`, **sem inventar informação**:
>
> - Cada parágrafo ou sub-bloco sobre um assunto distinto vira um item de `discussao[]`.
> - Use os títulos ou marcadores presentes no texto original como `titulo`. Se não houver título explícito, crie um descritivo de 2-5 palavras (ex: 'Alinhamento sobre turnover', 'Retorno do Call Center').
> - `descricao` recebe o parágrafo resumido em 2-4 frases, fiel ao texto original.
> - `contribuicoes[]` só recebe itens se o texto legado atribuir claramente uma fala a um participante por cargo/função. Quando não for identificável, use array vazio.
> - `divergencias[]` só recebe itens se o texto legado registrar ressalvas ou alertas. Quando não mencionado, array vazio.
> - `decisao` recebe a decisão explícita do texto, ou 'A definir' se não houver.
> - Não invente tópicos; se o PDF só tem uma breve conclusão, pode haver apenas 1-2 itens em `discussao[]`."

**Remover:** `resumo_executivo`, `proxima_reuniao` do schema.

**Manter:** `prazo_original` em `quadro_atribuicoes` (é info útil para auditoria de migração, não faz parte do modelo mas não polui o PDF).

### 3.3 Template `ata_template.html` (mudança grande — layout)

**Design preservado:** cores (#232d69, #475569, #e2e8f0, badges), tipografia Helvetica Neue, tamanhos (h1 20pt, h2 14pt, body 11px), CSS de quebra de página, estilo de `.topico`, `.objetivo-box`, `.sig-table`.

**Estrutura nova do `<body>`:**

```jinja2
<body>

  {# ============ TOPO — branding (sem campos formais) ============ #}
  <div class="header">
    <div class="header-logo">
      <img src="{{ logo_path }}" alt="Logo Hospital São Matheus">
    </div>
    <div class="header-title">
      <h1>Ata de Reunião</h1>
      <p>Hospital São Matheus — Cuidar bem. Agir certo. Crescer juntos.</p>
    </div>
    {# header-meta (ID + Gerado em) REMOVIDO — movidos para rodapé #}
  </div>

  {# ============ 1. CABEÇALHO ============ #}
  <h2>1. Cabeçalho</h2>
  <div class="cabecalho-lista">
    <p><strong>Instituição:</strong> Hospital São Matheus</p>
    <p><strong>Tipo de documento:</strong> Ata de Reunião{% if reuniao.tipo %} — {{ reuniao.tipo }}{% endif %}</p>
    <p><strong>Data:</strong> {{ reuniao.data }}</p>
    <p><strong>Horário:</strong>
      {% if reuniao.hora_inicio or ata.hora_inicio %}
        {{ reuniao.hora_inicio or ata.hora_inicio }}
        {% if reuniao.hora_fim or ata.hora_fim %} às {{ reuniao.hora_fim or ata.hora_fim }}{% endif %}
      {% else %}—{% endif %}
    </p>
    <p><strong>Local:</strong> {{ reuniao.local or ata.local or '—' }}</p>
  </div>

  {# ============ 2. PARTICIPANTES ============ #}
  <h2>2. Participantes</h2>
  {% if ata.participantes %}
    <table>
      <thead><tr><th>Nome</th><th>Cargo / Função</th></tr></thead>
      <tbody>
        {% for p in ata.participantes if p.presente %}
          <tr>
            <td style="font-weight:bold;">{{ p.nome }}</td>
            <td>{{ p.cargo }}{% if p.setor %} — {{ p.setor }}{% endif %}</td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# ------ 2.1 Referências externas mencionadas ------ #}
  {% if ata.referencias_externas and ata.referencias_externas|length > 0 %}
    <h3>2.1 Referências externas mencionadas</h3>
    <table>
      <thead><tr><th>Nome</th><th>Vínculo / Organização</th></tr></thead>
      <tbody>
        {% for ref in ata.referencias_externas %}
          <tr><td>{{ ref.nome }}</td><td>{{ ref.vinculo_organizacao or '—' }}</td></tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# ============ 3. OBJETIVO DA REUNIÃO ============ #}
  {% set objetivo_txt = ata.objetivo or reuniao.objetivo %}
  {% if objetivo_txt %}
    <h2>3. Objetivo da Reunião</h2>
    <p class="objetivo-box">{{ objetivo_txt }}</p>
  {% endif %}

  {# ============ 4. DISCUSSÃO DOS PONTOS ============ #}
  {% if ata.discussao and ata.discussao|length > 0 %}
    <h2>4. Discussão dos Pontos</h2>
    {% for topico in ata.discussao %}
      <div class="topico">
        <p class="topico-titulo">4.{{ loop.index }} {{ topico.titulo }}</p>
        {% if topico.descricao %}<p class="topico-descricao">{{ topico.descricao }}</p>{% endif %}
        {% if topico.contribuicoes and topico.contribuicoes|length > 0 %}
          <span class="topico-label">Contribuições</span>
          <ul>
            {% for c in topico.contribuicoes %}
              <li><strong>{{ c.funcao or 'Participante' }}:</strong> {{ c.conteudo }}</li>
            {% endfor %}
          </ul>
        {% endif %}
        {% if topico.divergencias and topico.divergencias|length > 0 %}
          <span class="topico-label">Divergências, ressalvas e alertas</span>
          <ul>{% for d in topico.divergencias %}<li class="topico-divergencia">{{ d }}</li>{% endfor %}</ul>
        {% endif %}
        {% if topico.decisao %}
          <div class="topico-decisao">
            <strong>Decisão / Encaminhamento:</strong> {{ topico.decisao }}
            {% if topico.responsavel %}<br><em>Responsável: {{ topico.responsavel }}</em>{% endif %}
          </div>
        {% endif %}
      </div>
    {% endfor %}
  {% endif %}
  {# fallback registro_narrativo REMOVIDO — todas as ATAs passam pela estrutura 4.x #}

  {# ============ 5. QUADRO DE PENDÊNCIAS, DECISÕES E RESPONSÁVEIS ============ #}
  {% if ata.quadro_atribuicoes and ata.quadro_atribuicoes|length > 0 %}
    <h2>5. Quadro de Pendências, Decisões e Responsáveis</h2>
    <table>
      <thead>
        <tr><th>Ação / Encaminhamento</th><th>Responsável</th><th>Objetivo / Meta</th><th>Prazo</th><th>Status</th></tr>
      </thead>
      <tbody>
        {% for acao in ata.quadro_atribuicoes %}
          <tr>
            <td style="font-weight:500;">{{ acao.acao }}</td>
            <td>{{ acao.responsavel }}<br><span style="font-size:8pt;color:#64748b;">{{ acao.cargo }}</span></td>
            <td>{{ acao.objetivo_meta or acao.entregavel or '—' }}</td>
            <td>{{ acao.prazo or 'A definir' }}</td>
            <td>
              {% set st = (acao.status or 'ABERTO')|upper %}
              {% if st == 'CONCLUIDO' %}<span class="badge badge-concluido">Concluído</span>
              {% elif st == 'EM_ANDAMENTO' %}<span class="badge badge-andamento">Em andamento</span>
              {% else %}<span class="badge badge-aberto">Aberto</span>{% endif %}
            </td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}

  {# ============ 6. ESPAÇO PARA ASSINATURAS ============ #}
  <div class="footer-signatures">
    <h2>6. Espaço para Assinaturas</h2>
    <p class="note-disclaimer">
      Documento gerado automaticamente pelo sistema Hospital Reuniões. Aguardando validação e assinatura digital dos participantes presentes.
    </p>
    {% set presentes = (ata.participantes or [])|selectattr('presente')|list %}
    {% if presentes|length > 0 %}
      <table class="sig-table">
        <thead><tr><th>Nome</th><th>Cargo / Função</th><th>Assinatura</th><th class="sig-data">Data</th></tr></thead>
        <tbody>
          {% for p in presentes %}
            <tr>
              <td style="font-weight:bold;">{{ p.nome }}</td>
              <td>{{ p.cargo }}{% if p.setor %} — {{ p.setor }}{% endif %}</td>
              <td><div class="sig-line"></div></td>
              <td><div class="sig-line"></div></td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
    {% else %}
      <p style="color:#64748b; font-size:9pt;">Nenhum participante presente foi registrado nesta ata.</p>
    {% endif %}
  </div>

  {# BLOCOS REMOVIDOS:
     - Resumo Executivo
     - Próxima Reunião
     - Pontos para Esclarecimento (lacunas_identificadas)
     - Meta-grid com "Status: Aguardando Validação"
     - Fallback registro_narrativo
  #}

</body>
```

**CSS a adicionar** (dentro do `<style>` existente):

```css
.cabecalho-lista {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #f8fafc;
  border-left: 3px solid #232d69;
  border-radius: 4px;
}
.cabecalho-lista p {
  margin: 4px 0;
  font-size: 11pt;
  color: #0f172a;
}
.cabecalho-lista strong {
  color: #232d69;
  font-weight: 600;
  display: inline-block;
  min-width: 140px;
}
```

**CSS a adicionar ao `@page`** para mover ID + data para rodapé:

```css
@page {
  size: A4;
  margin: 2.5cm;
  @bottom-right {
    content: "Página " counter(page) " de " counter(pages);
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 9pt;
    color: #475569;
  }
  @bottom-left {
    content: "ID: {{ reuniao_id_curto }} · Gerado em: {{ data_geracao }}";
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    font-size: 8pt;
    color: #64748b;
  }
}
```

> **Nota técnica:** o WeasyPrint não interpola Jinja dentro de `@bottom-left content`. A solução é **ou** (a) renderizar o rodapé como um `<div>` fixo no final do body e usar `position: running()` via `@page`, **ou** (b) passar como variável CSS custom property gerada antes do render. A alternativa mais simples é interpolar o Jinja *no próprio `<style>`* (WeasyPrint permite isso desde que o `<style>` seja interpretado pelo Jinja antes). **Verificar durante execução**; se não funcionar, cair para `<div class="footer-meta">` dentro do body no final (quebra página no rodapé visual final).

### 3.4 Mocks em `ai_processor.py`

Atualizar `_mock_ata()` e `_mock_ata_migrada()` para refletir novo schema:
- Remover `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas`.
- Em `_mock_ata_migrada()`, substituir `registro_narrativo` por um `discussao[]` de exemplo.

### 3.5 Tipos TS em `frontend/src/types/index.ts`

No `interface JsonAta`:

```typescript
// Campos obrigatórios (novo schema)
hora_inicio?: string;
hora_fim?: string;
local?: string;
objetivo?: string;
participantes?: Array<{...}>;
referencias_externas?: Array<{...}>;
discussao?: Array<{...}>;
quadro_atribuicoes?: Array<{...}>;

/** @deprecated — pré-migração HSM. Ainda existe em ATAs antigas no banco. */
resumo_executivo?: string;
/** @deprecated — pré-migração HSM. */
proxima_reuniao?: string | null;
/** @deprecated — pré-migração HSM. */
lacunas_identificadas?: string[];
/** @deprecated — substituído por discussao[] estruturado. */
registro_narrativo?: string;
```

Mantemos os campos como opcionais com `@deprecated` para não quebrar leituras de ATAs antigas já persistidas no Supabase.

---

## 4. Pontos de atenção

1. **ATAs em produção (legadas ou pré-mudança)**: seus JSONs no banco ainda contêm `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas`, `registro_narrativo`. O novo template **ignora** esses campos ao renderizar, então ATAs antigas renderizam com as seções vazias que sumiram — **o que é o comportamento desejado** (mesmas 6 seções obrigatórias). Nenhum dado é perdido; só deixa de ser exibido.

2. **ATAs antigas com `discussao=[]` e apenas `registro_narrativo`**: essas ficarão com a seção 4 vazia no PDF. Para corrigir, será preciso re-rodar a importação legada com o novo prompt (escopo futuro — "rebuild retroativo do json_ata das atas migradas"). Não é bloqueador desta rodada.

3. **Rodapé do PDF com Jinja dentro de `@page`**: interpolação precisa ser validada no WeasyPrint. Fallback já previsto em §3.3.

4. **Chat de correção**: se o usuário pedir "adicione um resumo executivo", o prompt deve responder que esse campo não faz parte do modelo HSM atual. Reforçar isso no `chat_correcao_system.md`.

5. **Teste mock primeiro**: antes de bater na OpenAI, validar o template usando `_mock_ata()` (basta rodar o pipeline com `OPENAI_API_KEY` vazio). Assim separa-se bug de prompt de bug de template.

6. **Commit atômico**: as mudanças em prompts + template + mocks estão acopladas — melhor um único commit com mensagem tipo `refactor(ata): conformar geração de ATA à estrutura obrigatória HSM (6 seções)`.

7. **Hook `post-commit` do blueprint**: a skill `/blueprint-sync` rodará automaticamente após o commit. Pode ser necessário verificar se ela atualiza corretamente `blueprint/FLUXOS.md` refletindo o novo contrato do PDF.

---

## 5. Verificação (end-to-end)

Executar na seguinte ordem:

### 5.1 Template (isolado, com mock)

```bash
cd hospital-reunioes/backend
# Com OPENAI_API_KEY vazio, o ai_processor cai em _mock_ata()
uv run python -c "
from app.services.pdf_generator import gerar_pdf_ata
from app.services.ai_processor import _mock_ata
reuniao = {'id_reuniao': 'RD_TEST_001', 'data': '2026-04-21', 'hora_inicio': '14:00', 'hora_fim': '15:30', 'tipo': 'Coordenação', 'local': 'Sala 3', 'objetivo': 'Teste'}
pdf = gerar_pdf_ata(reuniao, _mock_ata())
open('/tmp/ata_teste.pdf', 'wb').write(pdf)
print('OK /tmp/ata_teste.pdf')
"
open /tmp/ata_teste.pdf
```

**Checar visualmente:**
- [ ] Topo: logo + título + tagline (sem ID/Gerado em)
- [ ] "1. Cabeçalho" com 5 campos (Instituição, Tipo, Data, Horário, Local)
- [ ] "2. Participantes" (tabela)
- [ ] "2.1 Referências externas mencionadas" (se houver dados no mock)
- [ ] "3. Objetivo da Reunião"
- [ ] "4. Discussão dos Pontos" com 4.1, 4.2, …
- [ ] "5. Quadro de Pendências, Decisões e Responsáveis"
- [ ] "6. Espaço para Assinaturas"
- [ ] **Nenhuma** seção de Resumo Executivo / Próxima Reunião / Lacunas
- [ ] Rodapé de página com ID + "Gerado em"
- [ ] Cores HSM (#232d69) preservadas
- [ ] Tipografia e quebras de página intactas

### 5.2 Pipeline completo com IA real (uma reunião nova)

- Subir localmente com `/atualizar-app`
- Agendar reunião teste pelo frontend; enviar transcrição mock/texto
- Baixar o PDF preliminar
- Verificar visualmente (mesma checklist acima)
- Inspecionar o `json_ata` no Supabase: não deve ter `resumo_executivo`, `proxima_reuniao`, `lacunas_identificadas`

### 5.3 Importação legada (dry-run)

```bash
cd hospital-reunioes/backend
uv run python -m scripts.bulk_import_atas dry-run \
  --dir ../../atas-migracao/ \
  --out /tmp/preview.json \
  --limit 2
```

- Abrir `/tmp/preview.json`
- Conferir que cada ATA tem `discussao` com itens (não mais `registro_narrativo` como campo principal)
- Rodar `apply` para 1 ATA teste e gerar o PDF para validar

### 5.4 Chat de correção

- Abrir ATA já gerada; pedir "adicione uma referência externa: João da Empresa X"
- Conferir que o `correction_plan` aponta para `referencias_externas[]`, não para campos removidos
- Confirmar regeração do PDF com a nova referência

### 5.5 Regressão — ATA antiga no banco

- Abrir no frontend uma ATA existente (pré-mudança) que tenha `resumo_executivo` e `registro_narrativo` no `json_ata`
- Re-gerar o PDF (se houver botão) ou só conferir que o rendering falha graciosamente
- Resultado esperado: PDF renderiza com as 6 seções; campos antigos simplesmente não aparecem; **sem erro**

---

## 6. Rollout

1. Implementar todas as mudanças (prompts + template + mocks + tipos) em um branch local.
2. Testar §5.1 e §5.2 localmente com `/atualizar-app`.
3. Commitar como `refactor(ata): conformar geração à estrutura obrigatória HSM (6 seções)`.
4. Rodar `/deploy` (skill unificada) para ship em produção.
5. Monitorar a primeira ATA gerada em produção (smoke test).
6. Se tudo OK, considerar em rodada futura: re-importação em massa das ATAs legadas para atualizar seus `json_ata` ao novo formato estruturado (não é requisito desta rodada).
