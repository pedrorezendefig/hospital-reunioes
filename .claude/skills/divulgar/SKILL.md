---
name: divulgar
description: Página de divulgação de um PRD entregue (abas Funcionalidade + Demonstração por Vídeo), com a logo do hospital, publicada na Vercel. Sintaxe `/divulgar <PRD>`. Saída em docs/comunicacao/divulgacao/.
---

# Divulgar

Fecha uma seção entregue com **um link compartilhável**: uma página que dá uma explicada leve no que mudou e embute o vídeo de Percepção de Valor. A página e o vídeo se fundem num documento só, com duas abas.

**Divisão de trabalho fixa:** a escrita explica, o vídeo demonstra. A página **não tem** passo a passo, stepper, réplica de tela nem simulação: tudo isso vive no vídeo da `/perceber`. Se a explicação precisar "mostrar", ela aponta para a aba do vídeo.

## Pré-requisito

O PRD precisa ter uma percepção em vídeo pronta (`docs/comunicacao/percepcao/<contexto>/<PRD>-<slug>/*.mp4`). Se não tiver, rode `/perceber <PRD>` antes (com o gate HITL dele).

## Formato do entregável

**Pasta:** `docs/comunicacao/divulgacao/<PRD>-<slug>/`, autossuficiente (o deploy da Vercel sobe a pasta inteira):
- `index.html`: a página, versionada no git.
- `logo-hsm.png` e `HPSimplified_Rg.ttf`: a página referencia os dois **relativos** (`src="logo-hsm.png"`, `url("HPSimplified_Rg.ttf")`), mas eles **não ficam nesta pasta no git**: a cópia única vive em `docs/comunicacao/_assets/` (ADR 0044) e o passo de deploy copia os dois para a pasta temporária antes de publicar.
- `demonstracao.mp4`: cópia do MP4 da percepção do PRD. **Fora do git** (`docs/comunicacao/divulgacao/**/*.mp4` no `.gitignore`), regerável pela composição da percepção.

**Referência de implementação:** `docs/comunicacao/divulgacao/272-aceites-e-pendencias-por-assinatura/index.html`. Nova divulgação = copiar essa página como base e trocar o conteúdo, mantendo estrutura e design.

**Design system: o do app, sempre.** A página replica o `globals.css` do frontend do Hospital Reuniões, não inventa identidade própria:
- Fonte **HP Simplified** em tudo (fallback `system-ui, -apple-system, sans-serif`), `html { font-size: 17px }`.
- Tokens copiados do `globals.css`: `--color-primary #2B2E7E`, `--color-primary-light #3B6FB6`, `--color-primary-dark #1A1C4E`, texto `#1E293B`, secundário `#64748B`, borda `#E2E8F0`, fundo branco, `--shadow-premium`, radius corporativo (xl 6px, 2xl 8px, 3xl 12px; pill 9999px).
- Antes de compor, conferir o `globals.css` atual: se os tokens mudaram no app, a página segue o app.

## Estrutura da página (fixa)

1. **Cabeçalho:** logo real do hospital + "Reuniões" + selo "em produção".
2. **Hero:** uma frase de título com o valor da seção + um parágrafo de resumo.
3. **Abas em barra flutuante no rodapé (liquid glass):** `Funcionalidade` e `Demonstração por Vídeo` ficam numa barra pill **fixa na parte de baixo da viewport, centralizada** (`position: fixed; bottom: ~22px; left: 50%`), flutuando sobre o conteúdo. Efeito liquid glass na receita do `.glass-card` do app: `background: rgba(255,255,255,.8)`, `backdrop-filter: blur(12px) saturate(160%)`, borda `rgba(255,255,255,.5)`, `--shadow-premium-strong`. Aba ativa = pill navy (`--color-primary`) com texto branco. `padding-bottom` no body para a barra não cobrir o fim do conteúdo; aba ativa no hash da URL (`#funcionalidade` / `#video`). **Nunca** como linha de tabs no topo do conteúdo.
4. **Aba Funcionalidade** (a explicação leve, nada além disto):
   - *O problema*: **um parágrafo** com a dor antiga. Sem cards de dor, sem narrativa longa.
   - *O que mudou*: cards compactos (título + 1 a 2 frases), um por mudança da seção.
   - *Na prática*: checklist curto de como reconhecer a mudança funcionando (até 5 itens).
   - CTA apontando para a aba do vídeo.
5. **Aba Demonstração por Vídeo:** um parágrafo de contexto (o exemplo seguido e o aviso de que o vídeo é mudo) + `<video controls>` com `demonstracao.mp4` + linha de carimbo (`duração · PRD #N · retrata o app em vX.Y.Z · gerado em DD/MM/AAAA`, os dados vêm do carimbo do próprio vídeo).
6. **Rodapé:** contexto, mês/ano e versão do app.

## Regras de conteúdo

- **Linguagem de negócio**, vocabulário do `CONTEXT.md`; zero jargão técnico (mesmo gate anti-técnica da `/perceber`).
- **Enxuto de verdade:** se uma seção da aba Funcionalidade passar de uma tela de leitura, cortar. Detalhe que só faz sentido vendo = vídeo.
- pt-BR; **proibido travessão (U+2014) e meia-risca (U+2013)** em qualquer texto (ADR 0013). Conferir com `grep -Pn "\x{2013}|\x{2014}" index.html`.
- Verificar o resultado com Chrome headless (screenshot das duas abas) antes de entregar.

## Publicação (automática, pela CLI)

O deploy é do agente, direto pela Vercel CLI (a sessão já está logada; não pedir para o humano executar). **Gotcha obrigatório:** deploy de dentro do repo é BLOQUEADO pela Vercel (`TEAM_ACCESS_REQUIRED`: a CLI anexa o autor git `pmrdef@gmail.com`, que não é membro do time `pedrocloserj-3582`). Sempre deployar de uma cópia da pasta FORA do repo (sem metadados git):
```bash
D=$(mktemp -d) && cp -R docs/comunicacao/divulgacao/<PRD>-<slug>/. "$D/" && cp docs/comunicacao/_assets/logo-hsm.png docs/comunicacao/_assets/fonts/HPSimplified_Rg.ttf "$D/" && cd "$D" && npx vercel@latest deploy --prod --yes
```
A cópia leva o `.vercel/` junto (mantém o vínculo com o projeto; ele fica fora do git). O link compartilhável é o **alias de produção** (`https://<projeto>.vercel.app`, sem hash): as URLs de deployment com hash redirecionam pro SSO da Vercel. Entregar o link ao usuário e registrá-lo em comentário no PRD. Ajuste pedido depois = editar a página no repo, recopiar e redeployar.
