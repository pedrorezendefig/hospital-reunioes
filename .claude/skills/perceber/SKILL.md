---
name: perceber
description: Gera a Percepção de Valor de uma funcionalidade já entregue em VÍDEO (MP4): apresentação do que melhorou + demonstração atuada ponta a ponta nas telas do app (réplica do design system real), renderizada com HyperFrames a partir de uma composição HTML versionada. Zero técnica, feito pro diretor e pro usuário funcional. Use quando o usuário disser "perceber", "/perceber", "perceber valor", "percepção de valor da issue N", "vídeo de percepção de valor", "mostra o valor da funcionalidade X pro diretor". Sintaxe `/perceber <número-da-issue-ou-PRD>`. Saída em docs/comunicacao/percepcao/<contexto>/<PRD>-<slug>/ (composição no git, MP4 git-ignored) com carimbo de geração (data/hora, versão do app, meta JSON no head).
---

# Perceber valor

Transforma uma funcionalidade **já entregue** num vídeo de Percepção de Valor: um MP4 que o diretor assiste e **vê o sistema funcionando**, sem uma linha de jargão técnico. O vídeo É a demonstração: um exemplo único, com dados mocados, seguido de ponta a ponta nas telas do app (réplica do design system real). Tudo que não é demonstração (abertura, antes/depois) é um slide rápido, nunca um bloco explicativo.

**O que este vídeo NÃO é:** não é changelog, não é PRD, não é doc de arquitetura. Não existe "como foi implementado". Se sobrar migration, endpoint, PR, deploy ou RLS no texto visível, a skill falhou (ver gate anti-técnica).

**Formato decidido na ADR 0026:** a simulação é escrita como composição HyperFrames (HTML + timeline determinística), versionada como fonte; o MP4 renderizado é o entregável que circula (email, WhatsApp, TV) e fica fora do git. O HTML interativo com stepper foi o formato anterior; percepções antigas em `.html` são retratos históricos válidos, não migrar sem pedido. Quando uma percepção antiga FOR migrada para vídeo, o `.html` dela muda para dentro da pasta da percepção (ver Formato do entregável).

## Entrada

`/perceber <N>` onde N é uma issue entregue ou um PRD (issue mãe). PRD agrega as fatias filhas numa demonstração só: o caso de uso completo, não uma demonstração por fatia.

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **A issue no GitHub**: `gh issue view <N> --comments`. Para PRD, também as filhas (`gh issue view` em cada uma). As user stories e critérios de aceite viram os passos da demonstração, um a um. **Critério de aceite não coberto pela demonstração = vídeo incompleto.** Não inventar passo que a issue não aborda.
2. **O código real do frontend** da funcionalidade: componentes, textos de botão, labels, placeholders, ordem dos campos, cores, estados. A fidelidade visual sai daqui, nunca de memória. Ler os arquivos em `hospital-reunioes/frontend/` que a funcionalidade toca (o PR da issue lista os arquivos: `gh pr view --json files`).
3. **`docs/spec/snapshots/`** (ROTAS.md, FLUXOGRAMAS.md): confirma o caminho de navegação real até a tela.
4. **`CONTEXT.md` e o CONTEXT do contexto da funcionalidade** (ex.: `docs/pops/CONTEXT.md`): vocabulário canônico do domínio. Usar sempre o termo do glossário (Elaborador, Natureza, Biblioteca), nunca sinônimo inventado.

## Formato do entregável

**Pasta:** `docs/comunicacao/percepcao/<contexto>/<PRD>-<slug>/`, **a casa única de TODOS os artefatos daquela percepção**. Nada dela vive solto fora da pasta:
- `index.html`: a composição HyperFrames, **fonte do vídeo** (o render abre esse HTML em navegador invisível e fotografa frame a frame). Versionada no git com os assets (`*.motion.json`, imagens): é o que permite editar e regerar o vídeo.
- `<PRD>-<slug>.mp4`: o vídeo renderizado, o entregável que circula. Fica na pasta mas está no `.gitignore` (render determinístico: a mesma fonte reproduz o mesmo vídeo).
- O HTML interativo do formato antigo (`<PRD>-<slug>.html`), quando aquela percepção tiver um: entra na pasta junto, como artefato histórico da mesma percepção.

**Organização da pasta mãe:**
- Uma subpasta por **contexto de domínio** do app: `pops/`, `reunioes/` (novo contexto = nova subpasta, mesmo nome do CONTEXT correspondente).
- Nome da pasta: `<PRD>-<slug>` (número do PRD na frente ordena e garante unicidade; slug curto em kebab-case). Percepção que não nasce de um PRD (visão geral de um contexto) usa o prefixo fixo `panorama-<slug>`.
- **Sem data no nome** e **sem índice paralelo** (INDEX.md/galeria): pasta + nome + carimbo são o índice.

**Especificação técnica:** 1920x1080 (16:9), 30fps, duração alvo de 45 a 90s, **com a demonstração ocupando quase todo o tempo**. **Sem narração de voz na v1**: toda a comunicação é em tela, o vídeo funciona no mudo.

**Carimbo de geração (obrigatório, dois níveis):**
- **Visível, no fecho do vídeo**, discreto: `PRD #<N> · retrata o app em v<X.Y.Z> · gerado em DD/MM/AAAA` (panorama usa `Panorama` no lugar do PRD). A versão vem de `hospital-reunioes/frontend/package.json` no momento da geração.
- **Legível por máquina, no `<head>` da composição**, para scripts e sessões futuras listarem percepções sem parsear:
  ```html
  <script type="application/json" id="percepcao-meta">
  {"prd": 210, "issues": [221, 222, 223, 224], "contexto": "pops",
   "titulo": "<título do vídeo, texto puro>",
   "app_version": "0.43.0", "gerado_em": "<ISO-8601 com timezone>"}
  </script>
  ```
  Panorama: `"prd": null, "issues": []`.

## Roteiro (estrutura fixa)

**O foco do vídeo é a usabilidade**: um exemplo com dados mocados, seguido de ponta a ponta. Nada de blocos explicando "como era antes" ou "como ficou": se o contraste ajudar, ele cabe num único slide rápido.

1. **Abertura (um quadro, 3 a 6s)**: título da funcionalidade + uma linha do que melhorou, na tipografia do sistema. Um quadro só, sem sequência de cards.
2. **Antes vs depois (condicional, um slide, 3 a 5s)**: só existe quando a issue descreve uma situação anterior real (dor, processo manual, fluxo antigo). Um único slide estático com os dois lados ("antes | depois"), sem narrativa, sem sequência de quadros. Sem antes real na issue, o slide não existe. **Nunca inventar dor fictícia.**
3. **Demonstração ponta a ponta (o vídeo é isso)**: um exemplo único e mocado, do primeiro clique ao resultado final. Cursor fantasma se move, clica, campo digita sozinho, painel abre, a tela reage como o app reagiria. Cobre **todos** os critérios de aceite, na ordem do caso de uso real. Legendas curtas de apoio quando o gesto sozinho não conta a história.
4. **Fecho**: carimbo de geração (acima).

**Dentro da demonstração:** as telas são **réplica do app real**, com as mesmas cores, botões, cards, sidebar, tipografia do frontend do Hospital Reuniões. O diretor tem que reconhecer o sistema que ele usa. Extrair os tokens do código (globals.css / tailwind config), não aproximar de cabeça.

**Dados de exemplo realistas do hospital:** setor de verdade (CME, Farmácia, UTI), nome de POP plausível, nomes de pessoa fictícios mas verossímeis. Nada de "Lorem ipsum" ou "Teste 123". **Fiel ao que foi entregue:** cada passo corresponde a um comportamento que existe em produção. Na dúvida entre bonito e fiel, fiel vence.

**Idioma e tipografia:** pt-BR. **Todo texto visível (HTML e vídeo) usa HP Simplified**, a fonte do sistema, inclusive na abertura e nos slides: declarar `@font-face` na composição apontando para `../../../_assets/fonts/HPSimplified_Rg.ttf` (cópia única versionada em `docs/comunicacao/_assets/fonts/`; não duplicar o TTF por percepção). Fallback `system-ui, sans-serif`, igual ao `globals.css` do app. **Proibido travessão (U+2014) e meia-risca (U+2013)** em qualquer texto visível (regra do projeto, ADR 0013). Vírgula ou hífen.

## Produção (HyperFrames)

Antes de compor, ler as skills globais na ordem: `/hyperframes` (router) → `/hyperframes-core` (contrato da composição) → `/hyperframes-animation` (motion seek-safe). Loop de trabalho:

1. `npx hyperframes init` na pasta da percepção (ou copiar a estrutura de uma percepção anterior em vídeo).
2. Compor as cenas (roteiro acima) com timing declarado em `data-*`.
3. `npx hyperframes lint` cedo e sempre; `npx hyperframes check --snapshots` como gate de correção (layout, contraste, motion).
4. Render de iteração: `npx hyperframes render --quality draft` para a auto-revisão de frames.
5. Render final `--quality high` **só depois do OK humano** (gate abaixo).

## Gate anti-técnica (obrigatório antes de renderizar)

Varrer todo texto visível da composição procurando vocabulário proibido:

```
migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend,
frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt
```

Cada ocorrência é reescrita em linguagem funcional ou removida. ("O sistema passou a reconhecer a Natureza pelo nome do Setor", nunca "a migration 054 fez backfill".) Varrer também travessão/meia-risca. Só seguir com as duas varreduras limpas.

## Gate de qualidade (duas camadas, obrigatório)

1. **Auto-revisão de frames**: extrair quadros do render draft (`ffmpeg -i <mp4> -vf fps=1 frames/%03d.png`) e conferir olhando os frames: telas batem com o app real (labels e botões conferidos no código), todos os critérios de aceite aparecem, texto legível no tempo em tela, zero jargão, zero travessão. Corrigir e re-renderizar até passar.
2. **OK humano**: entregar o MP4 draft para o usuário assistir (ritmo e sensação de apresentação são julgamento dele). Só depois do OK explícito, renderizar o final em `--quality high`. Ajuste pedido = novo draft, novo OK.

## Checklist de saída

1. Todos os critérios de aceite da(s) issue(s) têm passo correspondente na demonstração.
2. Telas batem com o app real (labels e textos de botão conferidos no código).
3. Vocabulário do glossário, zero jargão técnico, zero travessão.
4. Todo texto na fonte HP Simplified (via `docs/comunicacao/_assets/fonts/`); abertura e antes/depois são no máximo um slide rápido cada, a demonstração domina a duração.
5. `npx hyperframes check` limpo; auto-revisão de frames feita; OK humano dado no draft.
6. Pasta no padrão `docs/comunicacao/percepcao/<contexto>/<PRD>-<slug>/` com os dois carimbos (fecho do vídeo + `percepcao-meta`); composição commitada, MP4 fora do git.

## Depois da percepção: divulgação

O MP4 aprovado alimenta a documentação de divulgação da seção: a `/divulgar <PRD>` gera a página enxuta com abas Funcionalidade + Demonstração por Vídeo e embute uma cópia deste vídeo (`demonstracao.mp4`, git-ignored). Se a divulgação do PRD já existir em `docs/comunicacao/divulgacao/`, atualizar a cópia do vídeo lá ao regerar o MP4.
