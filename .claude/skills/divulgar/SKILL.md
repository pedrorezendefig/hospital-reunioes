---
name: divulgar
description: Gera a documentação de divulgação de uma seção/PRD já entregue, um HTML único e ENXUTO com duas abas (Funcionalidade = explicação leve por escrito; Demonstração por Vídeo = o MP4 da /perceber embutido), com a logo real do hospital, publicado na Vercel. A explicação não simula nada, o vídeo é a demonstração. Use quando o usuário disser "divulgar", "/divulgar", "documentação de divulgação", "doc da seção pra Vercel", "documentação visual da seção", ou quando uma issue pedir a documentação de encerramento de um PRD. Sintaxe `/divulgar <número-do-PRD>`. Saída em docs/divulgacao/<PRD>-<slug>/ (HTML + logo no git, MP4 git-ignored).
---

# Divulgar

Fecha uma seção entregue com **um link compartilhável**: uma página que dá uma explicada leve no que mudou e embute o vídeo de Percepção de Valor. A página e o vídeo se fundem num documento só, com duas abas.

**Divisão de trabalho fixa:** a escrita explica, o vídeo demonstra. A página **não tem** passo a passo, stepper, réplica de tela nem simulação: tudo isso vive no vídeo da `/perceber`. Se a explicação precisar "mostrar", ela aponta para a aba do vídeo.

## Pré-requisito

O PRD precisa ter uma percepção em vídeo pronta (`docs/percepcao/<contexto>/<PRD>-<slug>/*.mp4`). Se não tiver, rode `/perceber <PRD>` antes (com o gate HITL dele).

## Formato do entregável

**Pasta:** `docs/divulgacao/<PRD>-<slug>/`, autossuficiente (o deploy da Vercel sobe a pasta inteira):
- `index.html`: a página, versionada no git.
- `logo-hsm.png`: cópia de `hospital-reunioes/frontend/public/logo-hsm.png` (a logo real do sistema, obrigatória no cabeçalho).
- `demonstracao.mp4`: cópia do MP4 da percepção do PRD. **Fora do git** (`docs/divulgacao/**/*.mp4` no `.gitignore`), regerável pela composição da percepção.

**Referência de implementação:** `docs/divulgacao/272-aceites-e-pendencias-por-assinatura/index.html`. Nova divulgação = copiar essa página como base e trocar o conteúdo, mantendo a estrutura e o design (papel claro, Fraunces + Instrument Sans, navy do app).

## Estrutura da página (fixa)

1. **Cabeçalho:** logo real do hospital + "Reuniões" + selo "em produção".
2. **Hero:** uma frase de título com o valor da seção + um parágrafo de resumo.
3. **Abas:** `Funcionalidade` e `Demonstração por Vídeo` (a aba ativa vai no hash da URL: `#funcionalidade` / `#video`).
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
D=$(mktemp -d) && cp -R docs/divulgacao/<PRD>-<slug>/. "$D/" && cd "$D" && npx vercel@latest deploy --prod --yes
```
A cópia leva o `.vercel/` junto (mantém o vínculo com o projeto; ele fica fora do git). O link compartilhável é o **alias de produção** (`https://<projeto>.vercel.app`, sem hash): as URLs de deployment com hash redirecionam pro SSO da Vercel. Entregar o link ao usuário e registrá-lo em comentário no PRD. Ajuste pedido depois = editar a página no repo, recopiar e redeployar.
