import { LayoutTemplate, type LucideIcon, Megaphone, MousePointerClick, PenLine } from "lucide-react";

/**
 * O "O que vem por aí" da Visão Geral da Central de Comando (issue #821, ADR 0058).
 *
 * O único lugar onde funcionalidade futura aparece: o menu só lista o que
 * funciona (decisão 5). Cada item conta, em linguagem de leigo, o que ainda vai
 * nascer na Central, SEM data prometida e SEM item de menu correspondente. Os
 * textos são o porte de `src/lib/pages.ts` do repositório antigo, com a
 * tipografia da casa (sem travessão, aspas retas).
 */

export type ItemDoRoteiro = {
  /** Só para a chave de lista; não é rota (o item não navega para lugar nenhum). */
  id: string;
  titulo: string;
  descricao: string;
  icone: LucideIcon;
};

/**
 * Na ordem do CONTEXT.md: Blog, Editor do Site, Mapa de Calor, Google Ads.
 * Nenhum texto promete data (o compromisso é qualitativo, não um prazo).
 */
export const ROTEIRO: readonly ItemDoRoteiro[] = [
  {
    id: "blog",
    titulo: "Blog",
    descricao:
      "O blog quase no automático: a inteligência artificial sugere e redige as publicações, e você só aprova antes de ir ao ar. Menos trabalho manual, mais constância.",
    icone: PenLine,
  },
  {
    id: "editor-do-site",
    titulo: "Editor do Site",
    descricao:
      "Edite textos e seções do site novo por aqui, em tempo real, sem depender de programador. As mudanças aparecem no site assim que você confirma.",
    icone: LayoutTemplate,
  },
  {
    id: "mapa-de-calor",
    titulo: "Mapa de Calor",
    descricao:
      "Onde as pessoas clicam, até onde rolam cada página e onde desistem, para enxergar o que trava a navegação.",
    icone: MousePointerClick,
  },
  {
    id: "google-ads",
    titulo: "Google Ads",
    descricao:
      "Quanto foi investido, quantos cliques e contatos os anúncios trouxeram, e quais campanhas rendem mais, em linguagem simples.",
    icone: Megaphone,
  },
];
