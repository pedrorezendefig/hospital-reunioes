import { defineCollection, z } from "astro:content";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";

// O frontmatter da Página de tarefa (ADR 0057, decisão 4). O tema desenha os
// selos e o vídeo a partir daqui, para o Markdown não repetir estrutura.
export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        // PRDs que criaram ou mudaram a página. O deploy usa para tirar o draft.
        prd: z.array(z.number()).optional(),
        // Quem faz a tarefa: Ouvidoria, Gestor do setor, Facilitador,
        // Secretária, Só admin.
        papel: z.array(z.string()).optional(),
        // `false` na tela que a pessoa abre por link ou QR, sem entrar no app.
        login: z.boolean().optional(),
        // Slug do Vídeo de tarefa. Ausente = vídeo ainda em produção.
        video: z.string().optional(),
      }),
    }),
  }),
};
