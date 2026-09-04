---
name: divulgar
description: Vídeo de percepção de valor (MP4) e página de divulgação na Vercel de um PRD entregue, numa pasta só. Sintaxe `/divulgar <PRD> [--so-video | --so-pagina]`. Saída em docs/comunicacao/<contexto>/.
---

# Divulgar

Fecha uma entrega para o diretor e para o usuário funcional em **dois passos, um comando**:

1. **Vídeo de Percepção de Valor** (MP4): o diretor assiste e **vê o sistema funcionando**, sem jargão. Um exemplo único, com dados mocados, seguido de ponta a ponta nas telas do app (réplica do design system real).
2. **Página de divulgação** (HTML na Vercel): uma explicada leve no que mudou, com o vídeo embutido. Um link compartilhável.

**Divisão de trabalho fixa:** o vídeo demonstra, a página explica. A página não tem passo a passo, stepper, réplica de tela nem simulação. Se a explicação precisar "mostrar", ela aponta para a aba do vídeo.

**O que isto NÃO é:** changelog, PRD, doc de arquitetura. Não existe "como foi implementado". Se sobrar migration, endpoint, PR, deploy ou RLS em texto visível, a skill falhou (gate anti-técnica).

## Entrada

`/divulgar <N> [--so-video | --so-pagina]`. N é uma issue entregue ou um PRD (issue mãe). PRD agrega as fatias filhas numa demonstração só: o caso de uso completo, não uma demonstração por fatia.

- Sem flag: os dois passos, com o gate humano do vídeo entre eles.
- `--so-video`: só o passo 1 (para WhatsApp, e-mail, TV).
- `--so-pagina`: só o passo 2, quando o MP4 já existe na pasta.

## Uma pasta por PRD (ADR 0045)

`docs/comunicacao/<contexto>/<PRD>-<slug>/`, a casa única de tudo daquela entrega:

- `video/`: a composição HyperFrames, **fonte do vídeo** (`index.html`, `hyperframes.json`, `package.json`, `meta.json`, assets da cena). Versionada. `video/assets` é link simbólico para `../../../_assets` (fonte e logo únicos, ADR 0044).
- `<PRD>-<slug>.mp4`: o vídeo renderizado, na raiz da pasta. **Fora do git** (regerável). A página embute este arquivo por caminho relativo.
- `index.html`: a página de divulgação. Versionada. Referencia `logo-hsm.png` e `HPSimplified_Rg.ttf` relativos, que **não ficam na pasta**: o deploy copia os dois de `_assets/`.
- `.vercel/`: vínculo com o projeto da Vercel. Fora do git.

Regras da pasta mãe: uma subpasta por contexto de domínio (`reunioes/`, `pops/`, `ouvidoria/`), nome `<PRD>-<slug>` (número na frente ordena e garante unicidade; slug curto em kebab-case). **Sem data no nome e sem índice paralelo**: pasta, nome e carimbo são o índice.

**Página de módulo** (vários PRDs numa vitrine só, caso `ouvidoria/modulo/`): só `index.html`, embutindo cópias git-ignored dos MP4s dos PRDs (`fase-1.mp4`, `fase-2.mp4`). Ao regerar o vídeo de um PRD, atualizar a cópia na página de módulo.

## Fontes da verdade (nesta ordem, todas obrigatórias)

1. **A issue no GitHub**: `gh issue view <N> --comments`. Para PRD, também as filhas. As user stories e os critérios de aceite viram os passos da demonstração, um a um. **Critério de aceite não coberto = vídeo incompleto.** Não inventar passo que a issue não aborda.
2. **O código real do frontend** da funcionalidade: componentes, textos de botão, labels, placeholders, ordem dos campos, cores, estados. A fidelidade visual sai daqui, nunca de memória (`gh pr view --json files` lista os arquivos).
3. **`docs/spec/snapshots/`** (ROTAS.md, FLUXOGRAMAS.md): o caminho de navegação real até a tela.
4. **`CONTEXT.md` e o CONTEXT do contexto** (ex.: `docs/pops/CONTEXT.md`): vocabulário canônico. Sempre o termo do glossário, nunca sinônimo inventado.

## Passo 1: o vídeo

**Especificação:** 1920x1080, 30fps, 45 a 90s, **a demonstração ocupa quase todo o tempo**. Sem narração de voz: o vídeo funciona no mudo.

**Roteiro fixo:**
1. **Abertura (um quadro, 3 a 6s)**: título da funcionalidade + uma linha do que melhorou, na tipografia do sistema.
2. **Antes vs depois (condicional, um slide, 3 a 5s)**: só quando a issue descreve uma situação anterior real. Um único slide estático com os dois lados. **Nunca inventar dor fictícia.**
3. **Demonstração ponta a ponta (o vídeo é isso)**: um exemplo único e mocado, do primeiro clique ao resultado. Cursor fantasma clica, campo digita sozinho, painel abre, a tela reage como o app reagiria. Cobre **todos** os critérios de aceite, na ordem do caso de uso real. Legendas curtas quando o gesto sozinho não conta a história.
4. **Fecho**: carimbo de geração.

**Réplica do app real:** mesmas cores, botões, cards, sidebar e tipografia do frontend. Extrair os tokens do código (`globals.css`, tailwind config), não aproximar de cabeça. Dados de exemplo realistas do hospital (CME, Farmácia, UTI; nomes fictícios verossímeis). Na dúvida entre bonito e fiel, fiel vence.

**Tipografia:** todo texto visível usa HP Simplified via `@font-face` apontando para `assets/fonts/HPSimplified_Rg.ttf` (o link simbólico da pasta `video/`). Fallback `system-ui, sans-serif`. **Proibido travessão e meia-risca** em qualquer texto (ADR 0013).

**Carimbo de geração (obrigatório, dois níveis):**
- Visível, no fecho, discreto: `PRD #<N> · retrata o app em v<X.Y.Z> · gerado em DD/MM/AAAA`. Versão de `hospital-reunioes/frontend/package.json` no momento da geração.
- Legível por máquina, no `<head>` da composição:
  ```html
  <script type="application/json" id="percepcao-meta">
  {"prd": 210, "issues": [221, 222], "contexto": "pops", "titulo": "<texto puro>",
   "app_version": "0.43.0", "gerado_em": "<ISO-8601 com timezone>"}
  </script>
  ```

**Produção (HyperFrames):** ler as skills globais na ordem `/hyperframes` → `/hyperframes-core` → `/hyperframes-animation`. Loop: `npx hyperframes init` em `video/` (ou copiar a estrutura de uma entrega anterior) → compor as cenas com timing em `data-*` → `npx hyperframes lint` cedo e sempre, `npx hyperframes check --snapshots` como gate → render de iteração `--quality draft` → render final `--quality high` **só depois do OK humano**. O MP4 final vai para a raiz da pasta do PRD como `<PRD>-<slug>.mp4`.

**Gate anti-técnica (antes de renderizar):** varrer todo texto visível procurando `migration, endpoint, API, PR, pull request, deploy, RLS, schema, backend, frontend, commit, branch, merge, token, env, SQL, Supabase, Coolify, prompt`. Cada ocorrência vira linguagem funcional ou sai. Varrer também travessão e meia-risca.

**Gate de qualidade (duas camadas):**
1. **Auto-revisão de frames**: `ffmpeg -i <mp4> -vf fps=1 frames/%03d.png` e conferir olhando: telas batem com o app real, todos os critérios de aceite aparecem, texto legível no tempo em tela, zero jargão, zero travessão.
2. **OK humano** no draft. Só depois, o render final. Ajuste pedido = novo draft, novo OK.

## Passo 2: a página

**Referência de implementação:** `docs/comunicacao/reunioes/272-pendencia-nasce-na-assinatura/index.html`. Página nova = copiar essa como base e trocar o conteúdo, mantendo estrutura e design.

**Design system: o do app, sempre.** A página replica o `globals.css` do frontend, não inventa identidade:
- Fonte **HP Simplified** em tudo (fallback `system-ui, -apple-system, sans-serif`), `html { font-size: 17px }`.
- Tokens copiados do `globals.css`: `--color-primary #2B2E7E`, `--color-primary-light #3B6FB6`, `--color-primary-dark #1A1C4E`, texto `#1E293B`, secundário `#64748B`, borda `#E2E8F0`, fundo branco, `--shadow-premium`, radius corporativo (xl 6px, 2xl 8px, 3xl 12px; pill 9999px).
- Antes de compor, conferir o `globals.css` atual: se os tokens mudaram no app, a página segue o app.

**Estrutura fixa:**
1. **Cabeçalho:** logo real do hospital + nome do contexto + selo "em produção".
2. **Hero:** uma frase de título com o valor da entrega + um parágrafo de resumo.
3. **Abas em barra flutuante no rodapé (liquid glass):** `Funcionalidade` e `Demonstração por Vídeo` numa barra pill fixa na parte de baixo da viewport, centralizada (`position: fixed; bottom: ~22px; left: 50%`). Receita do `.glass-card` do app: `background: rgba(255,255,255,.8)`, `backdrop-filter: blur(12px) saturate(160%)`, borda `rgba(255,255,255,.5)`, `--shadow-premium-strong`. Aba ativa = pill navy com texto branco. `padding-bottom` no body; aba ativa no hash da URL (`#funcionalidade` / `#video`). **Nunca** como linha de tabs no topo.
4. **Aba Funcionalidade** (a explicação leve, nada além): *O problema* em um parágrafo; *O que mudou* em cards compactos (título + 1 a 2 frases), um por mudança; *Na prática*, checklist de até 5 itens; CTA para a aba do vídeo.
5. **Aba Demonstração por Vídeo:** um parágrafo de contexto (o exemplo seguido e o aviso de que o vídeo é mudo) + `<video controls>` com `<PRD>-<slug>.mp4` + linha de carimbo (`duração · PRD #N · retrata o app em vX.Y.Z · gerado em DD/MM/AAAA`, dados do carimbo do próprio vídeo).
6. **Rodapé:** contexto, mês/ano e versão do app.

**Regras de conteúdo:** linguagem de negócio, vocabulário do `CONTEXT.md`, mesmo gate anti-técnica do vídeo. Enxuto de verdade: seção da aba Funcionalidade que passa de uma tela de leitura, cortar. pt-BR, sem travessão nem meia-risca (`grep -Pn "\x{2013}|\x{2014}" index.html`). Verificar com Chrome headless (screenshot das duas abas) antes de publicar.

**Publicação (pela CLI, sem pedir ao humano).** Deploy de dentro do repo é BLOQUEADO pela Vercel (`TEAM_ACCESS_REQUIRED`: a CLI anexa o autor git, que não é membro do time). Sempre de uma cópia FORA do repo, só com o que a página precisa:

```bash
P=docs/comunicacao/<contexto>/<PRD>-<slug>; D=$(mktemp -d)
cp "$P"/index.html "$P"/*.mp4 "$D"/ && cp -R "$P"/.vercel "$D"/ 2>/dev/null
cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$D"/
cd "$D" && npx vercel@latest deploy --prod --yes
```

O link compartilhável é o **alias de produção** (`https://<projeto>.vercel.app`, sem hash): URLs de deployment com hash caem no SSO da Vercel. Entregar o link e registrá-lo em comentário no PRD. Ajuste depois = editar no repo, recopiar, redeployar.

## Checklist de saída

1. Todos os critérios de aceite têm passo na demonstração; telas batem com o app real.
2. Vocabulário do glossário, zero jargão, zero travessão, tudo em HP Simplified.
3. `npx hyperframes check` limpo; auto-revisão de frames feita; OK humano no draft.
4. Pasta `docs/comunicacao/<contexto>/<PRD>-<slug>/` com `video/` commitado, MP4 na raiz fora do git, `index.html` da página commitado.
5. Página publicada, link no PRD. Se existe página de módulo do contexto, cópia do MP4 atualizada lá.
