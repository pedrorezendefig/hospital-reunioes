// Seções na ordem do menu do app (ADR 0057, decisão 1). A aba Tecnologia fica
// fora de propósito. Uma lista só para o menu (`astro.config.mjs`) e para o
// módulo que o resultado da busca mostra (`MarkdownContent.astro`): o nome que
// a pessoa lê no resultado é o mesmo do menu.
export const modulos = [
  { label: "Primeiros passos", pasta: "primeiros-passos" },
  { label: "Reuniões e metas", pasta: "reunioes" },
  { label: "Ouvidoria", pasta: "ouvidoria" },
  { label: "POPs", pasta: "pops" },
  { label: "Contas médicas", pasta: "contas-medicas" },
  { label: "Admin", pasta: "admin" },
];
