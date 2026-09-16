// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";
// A home usa um componente para o cartão do módulo só virar link quando o
// módulo tem página publicada, e componente em página só existe com MDX.
import mdx from "@astrojs/mdx";

// Seções na ordem do menu do app (ADR 0057, decisão 1). A aba Tecnologia fica
// fora de propósito. Cada seção é gerada da árvore de pastas; a ordem dentro
// dela vem do `sidebar.order` do frontmatter de cada página.
const modulos = [
  { label: "Primeiros passos", pasta: "primeiros-passos" },
  { label: "Reuniões e metas", pasta: "reunioes" },
  { label: "Ouvidoria", pasta: "ouvidoria" },
  { label: "POPs", pasta: "pops" },
  { label: "Admin", pasta: "admin" },
];

export default defineConfig({
  site: "https://manual.hospitalsaomatheus.cloud",
  integrations: [
    starlight({
      title: "Manual da plataforma",
      description:
        "Como usar a plataforma do Hospital São Matheus, módulo por módulo.",
      // Locale raiz pt-BR, sem seletor de idioma (ADR 0057, decisão 2).
      defaultLocale: "root",
      locales: { root: { label: "Português", lang: "pt-BR" } },
      logo: {
        src: "./src/assets/logo-hsm.png",
        alt: "Hospital São Matheus",
        replacesTitle: false,
      },
      customCss: ["./src/styles/tema.css"],
      // O molde da Página de tarefa (selos e vídeo) é do tema, não do Markdown.
      components: {
        MarkdownContent: "./src/components/MarkdownContent.astro",
        // Modo claro como padrão; o seletor continua disponível.
        ThemeProvider: "./src/components/ThemeProvider.astro",
      },
      pagination: false,
      lastUpdated: false,
      social: [],
      sidebar: modulos.map(({ label, pasta }) => ({
        label,
        items: [{ autogenerate: { directory: pasta } }],
      })),
    }),
    mdx(),
  ],
});
