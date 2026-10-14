---
status: accepted
amends: 0057
---

# Manual com um Vídeo de visão geral por módulo e orçamento de 40 MB

Decisão do Pedro (14/out/2026, PRD #1259). O Manual tinha 61 Vídeos de tarefa, um por Página de tarefa, mais sete vídeos de capítulo na abertura da Ouvidoria. Com o rerender no Estilo do manual, cada vídeo ficou maior, e o site inteiro encostou no teto de 90 MB que o `publicar.sh` impõe para caber nos 100 MB do plano grátis da Vercel. Pagar o plano Pro ou hospedar vídeo fora do site são decisões maiores do que o problema. A saída é ter menos vídeo e vídeo mais útil: um por módulo, mostrando o caminho principal de ponta a ponta.

## Decisões

1. **Um Vídeo de visão geral por módulo, na abertura.** Cada módulo abre com um vídeo de 90 a 120 s, mudo, com legendas, que mostra o caminho principal do módulo com dados de exemplo, no Estilo do manual (tokens, cards, gates por quadros, `VERIFY.md`, carimbo). O vídeo entra pelo campo `video:` do frontmatter da abertura (`<modulo>/index.md`), que o tema já sabia ler. "Conheça a plataforma" é o vídeo de Primeiros passos, e a página inicial do Manual mostra o mesmo arquivo. Emenda as decisões 3 e 4 da ADR 0057: a composição continua em `docs/manual/video/<modulo>/<slug>/`, e a unidade do vídeo passa a ser o módulo. Rejeitado: manter o vídeo por tarefa com compressão mais forte (a soma continua crescendo a cada tarefa nova); vídeo por capítulo (já rejeitado na 0057).

2. **O Vídeo de tarefa sai do Manual.** As 61 Páginas de tarefa perdem o vídeo e ficam com o texto e os prints. As composições dos Vídeos de tarefa e dos sete capítulos da Ouvidoria saem do repositório; o `_estilo/` fica, e as composições antigas continuam no histórico do git (o último commit com elas é `72a3781f`). Os masters em `local/manual-video-masters/` não são apagados: são a única cópia dos MP4 e vão servir a um link externo, fora do deploy, que é outro PRD. O tema só desenha vídeo na abertura e na página inicial, e o conferidor recusa `video:` em qualquer outra página.

3. **O Admin fica sem vídeo.** Quem usa são poucas pessoas, e o texto da página basta. O inventário da `/montar-manual` não cobra vídeo dele.

4. **Orçamento como trava no `publicar.sh`.** Depois do reencode 720p, três travas: a soma dos MP4 até **40 MB**, no máximo **um vídeo por módulo** (a página inicial usa o arquivo de Primeiros passos e conta uma vez só) e nenhum vídeo acima de **8 MB**. O teto de 90 MB do site inteiro continua. A recusa diz a regra que quebrou e o vídeo. Emenda a decisão 6 da ADR 0057. Rejeitado: só o teto de 90 MB (avisa tarde, quando o site já não cabe); orçamento só na receita da skill (ninguém trava).

5. **Novidades levam link, não vídeo.** O Vídeo de percepção de valor embutido nas Novidades de Ouvidoria, POPs e Reuniões vira link para a página de divulgação da entrega. Entrega sem página de divulgação perde o vídeo da página, sem link (o caso do PRD #210, dos POPs). Emenda a decisão 12 da ADR 0057. O conferidor do build passa a recusar `<video>` fora da abertura do módulo.

6. **A Fatia de manual só pede vídeo quando o caminho principal muda.** O `/to-issues` escreve na Fatia de manual se o PRD muda o caminho principal do módulo; só aí o Vídeo de visão geral é refeito. PRD que mexe numa tarefa do canto muda a página e não o vídeo. Emenda a decisão 8 da ADR 0057.

## Consequências

- O `checar_video_manual.py` olha as aberturas e para de exigir composição por tarefa; o `checar_build_manual.py` confere no HTML gerado que a abertura com `video:` mostra o player com a capa e que nenhuma outra página tem vídeo.
- A `/montar-manual` troca a lacuna `sem-video` por tarefa pela `sem-visao-geral` por módulo, com o Admin isento. A receita da `/manual` passa a ser `references/video-de-visao-geral.md`.
- O Manual fica sem vídeo até as cinco fatias de vídeo do PRD #1259 subirem, uma por módulo.
- O termo "Vídeo de tarefa" fica no `CONTEXT.md` marcado como fora do Manual; o vídeo do Manual de hoje é o "Vídeo de visão geral".
