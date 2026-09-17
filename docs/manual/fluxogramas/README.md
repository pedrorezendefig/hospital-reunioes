# Fluxogramas de caminho

Fonte dos fluxogramas do Manual (ADR 0057, emenda de 17/09/2026, decisão 13):
um arquivo Mermaid por desenho, em `<modulo>/<slug>.mmd`, e o SVG gerado pelo
script do site em `src/assets/<modulo>/fluxo-<slug>.svg`. O SVG commitado é
sempre o que o gerador produz: nunca editado à mão.

Só entra fluxograma em Visão geral (`index.md`, "O caminho de ponta a ponta")
e em Como funciona que descreve estados ou desvios. Nunca em Página de tarefa.

Para gerar, da raiz do repositório:

```bash
node docs/manual/scripts/gerar-fluxogramas.mjs
node docs/manual/scripts/gerar-fluxogramas.mjs --so <modulo>/<slug>
```

O gerador chama o mermaid-cli por `npx` com versão fixa (ele traz um navegador
inteiro e não entra no `package.json`), veste o desenho com o `tema.json`
(cores do `globals.css` do app) e recusa rótulo com travessão ou meia-risca. Os
desenhos em si nascem no prompt `docs/prompts/09-fluxogramas.md`.
