---
name: perceber
description: Gera um documento de Percepção de Valor de uma funcionalidade já entregue: HTML autocontido, enxuto, com simulação animada do caso de uso nas telas do app (réplica do design system real) e abas Antes/Agora. Zero técnica, feito pro diretor e pro usuário funcional. Use quando o usuário disser "perceber", "/perceber", "perceber valor", "percepção de valor da issue N", "documento de percepção de valor", "mostra o valor da funcionalidade X pro diretor". Sintaxe `/perceber <número-da-issue-ou-PRD>`. Saída em docs/percepcao/<contexto>/<PRD>-<slug>.html com carimbo de geração (data/hora, versão do app, meta JSON no head).
---

# Perceber valor

Transforma uma funcionalidade **já entregue** num documento de Percepção de Valor: uma página HTML que o diretor abre, dá play e **vê o sistema funcionando**, sem uma linha de jargão técnico. O coração do documento é uma simulação animada e fiel do caso de uso, vestida com o design system real do app.

**O que este documento NÃO é:** não é changelog, não é PRD, não é doc de arquitetura. Não existe "como foi implementado". Se sobrar migration, endpoint, PR, deploy ou RLS no texto, a skill falhou (ver gate anti-técnica).

## Entrada

`/perceber <N>` onde N é uma issue entregue ou um PRD (issue mãe). PRD agrega as fatias filhas numa simulação só: o caso de uso completo, não uma simulação por fatia.

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **A issue no GitHub**: `gh issue view <N> --comments`. Para PRD, também as filhas (`gh issue view` em cada uma). As user stories e critérios de aceite viram os passos da simulação, um a um. **Critério de aceite não coberto pela simulação = simulação incompleta.** Não inventar passo que a issue não aborda.
2. **O código real do frontend** da funcionalidade: componentes, textos de botão, labels, placeholders, ordem dos campos, cores, estados. A fidelidade visual sai daqui, nunca de memória. Ler os arquivos em `hospital-reunioes/frontend/` que a funcionalidade toca (o PR da issue lista os arquivos: `gh pr view --json files`).
3. **`docs/spec/snapshots/`** (ROTAS.md, FLUXOGRAMAS.md): confirma o caminho de navegação real até a tela.
4. **`CONTEXT.md` e o CONTEXT do contexto da funcionalidade** (ex.: `docs/pops/CONTEXT.md`): vocabulário canônico do domínio. Usar sempre o termo do glossário (Elaborador, Natureza, Biblioteca), nunca sinônimo inventado.

## Formato do documento

**Arquivo:** `docs/percepcao/<contexto>/<PRD>-<slug>.html`: um único HTML **autocontido** (CSS e JS inline, sem CDN, sem assets externos; fontes via Google Fonts são a única exceção tolerada, com fallback de sistema decente). O documento circula por email/pendrive/TV: precisa abrir sozinho.

**Organização da pasta:**
- Uma subpasta por **contexto de domínio** do app: `pops/`, `reunioes/` (novo contexto = nova subpasta, mesmo nome do CONTEXT correspondente). É o eixo de "onde o valor é percebido"; sem subpastas por tema fino.
- Nome do arquivo: `<PRD>-<slug>.html` (número do PRD na frente ordena por natureza e garante unicidade; slug curto em kebab-case). Documento que não nasce de um PRD (visão geral de um contexto) usa o prefixo fixo `panorama-<slug>.html`.
- **Sem data no nome** (regerar o documento não pode quebrar links já circulados) e **sem índice paralelo** (INDEX.md/galeria): pasta + nome + carimbo são o índice.

**Carimbo de geração (obrigatório, dois níveis):**
- **Visível, no rodapé** do documento, discreto: `PRD #<N> · retrata o app em v<X.Y.Z> · gerado em DD/MM/AAAA às HHhMM` (panorama usa `Panorama` no lugar do PRD). A versão vem de `hospital-reunioes/frontend/package.json` no momento da geração; é ela que diz de qual retrato do produto o documento fala.
- **Legível por máquina, no `<head>`**, para scripts e sessões futuras listarem percepções sem parsear o documento:
  ```html
  <script type="application/json" id="percepcao-meta">
  {"prd": 210, "issues": [221, 222, 223, 224], "contexto": "pops",
   "titulo": "<h1 do documento, texto puro>",
   "app_version": "0.43.0", "gerado_em": "<ISO-8601 com timezone>"}
  </script>
  ```
  Panorama: `"prd": null, "issues": []`.

**Estética híbrida, duas camadas:**
- **Moldura narrativa** (título, capítulos, texto de apoio): estilo editorial do projeto: serifada display (Fraunces), papel claro, tipografia generosa. Enxuto: título, um parágrafo do porquê, a simulação, fim. Cada seção a mais precisa se justificar.
- **Dentro da simulação:** as telas são **réplica do app real**, com as mesmas cores, botões, cards, sidebar, tipografia do frontend do Hospital Reuniões. O diretor tem que reconhecer o sistema que ele usa. Extrair os tokens do código (globals.css / tailwind config), não aproximar de cabeça.

**Idioma e tipografia:** pt-BR. **Proibido travessão (U+2014) e meia-risca (U+2013)** em qualquer texto visível (regra do projeto, ADR 0013). Vírgula ou hífen.

## A simulação

- **Stepper manual é o modo primário:** botões anterior/próximo, cada passo dispara a animação daquele momento (cursor fantasma se move, clica, campo digita sozinho, painel abre, a tela reage como o app reagiria). Quem apresenta controla o ritmo.
- **Play/pause** por cima: aperta play e os passos avançam sozinhos (para quem recebe o link sem apresentador). Espaço = play/pause, ← → = navegar. Barra de progresso com os passos nomeados e clicáveis.
- **Dados de exemplo realistas do hospital:** setor de verdade (CME, Farmácia, UTI), nome de POP plausível, nomes de pessoa fictícios mas verossímeis. Nada de "Lorem ipsum" ou "Teste 123".
- **Fiel ao que foi entregue:** cada passo corresponde a um comportamento que existe em produção. Na dúvida entre bonito e fiel, fiel vence.

## Abas Antes / Agora

- **"Agora"** é a aba padrão e carrega a simulação completa.
- **"Antes"** só existe quando a issue descreve uma situação anterior real (dor, processo manual, fluxo antigo). É deliberadamente mais pobre: 2 ou 3 quadros estáticos com anotações apontando a dor ("isso vivia num Word solto"). O contraste pobre-vs-rico comunica o valor sozinho.
- Sem antes real na issue, a aba não existe. **Nunca inventar dor fictícia.**

## Gate anti-técnica (obrigatório antes de finalizar)

Varrer o HTML gerado procurando vocabulário proibido em texto visível:

```
migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend,
frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt
```

Cada ocorrência é reescrita em linguagem funcional ou removida. ("O sistema passou a reconhecer a Natureza pelo nome do Setor", nunca "a migration 054 fez backfill".) Varrer também travessão/meia-risca. Só entregar com as duas varreduras limpas.

## Checklist de saída

1. Todos os critérios de aceite da(s) issue(s) têm passo correspondente na simulação.
2. Telas batem com o app real (labels e textos de botão conferidos no código).
3. Vocabulário do glossário, zero jargão técnico, zero travessão.
4. Play/pause + stepper + teclado funcionam (testar abrindo no navegador).
5. Arquivo único autocontido em `docs/percepcao/<contexto>/`, com nome no padrão e os dois carimbos (rodapé + `percepcao-meta`), versionado no git.
