# Fluxogramas de caminho

Fonte dos fluxogramas do Manual (ADR 0057, emenda de 17/09/2026, decisão 13):
um arquivo Mermaid por desenho, em `<modulo>/<slug>.mmd`, e o SVG gerado pelo
script do site em `src/assets/<modulo>/fluxo-<slug>.svg`. O SVG commitado é
sempre o que o gerador produz: nunca editado à mão.

Só entra fluxograma em Visão geral (`index.md`, "O caminho de ponta a ponta")
e em Como funciona que descreve estados ou desvios. Nunca em Página de tarefa.

O gerador e o tema de cores (`tema.json`, cores do `globals.css` do app)
nascem no prompt `docs/prompts/07-tema-didatico.md`; os desenhos, no
`09-fluxogramas.md`.
