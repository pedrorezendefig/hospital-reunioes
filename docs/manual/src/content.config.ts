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
        // Palavras do dia a dia que acham a página na busca, mesmo fora do
        // texto ("boleto" acha a página que fala "guia"). Issue #1221.
        busca: z.array(z.string()).optional(),
        // Até três tarefas do mesmo módulo que costumam vir depois, pelo nome
        // do arquivo sem extensão. O tema desenha "Tarefas próximas" no fim;
        // o lint do Manual reprova slug fora do módulo.
        proximas: z.array(z.string()).max(3).optional(),
      }),
    }),
  }),
};
