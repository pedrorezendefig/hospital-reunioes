/**
 * As páginas do manual, aba Aplicativo do Hospital (issue #1718, ADR 0094).
 *
 * Cada página é um Markdown em `public/manual/<pasta>/pagina.md`, com os prints
 * ao lado, e abre com um cabeçalho que declara o módulo dela:
 *
 *     ---
 *     modulo: pops
 *     titulo: POPs
 *     ---
 *
 * Quem vê a página é quem tem o módulo no menu (decisão 2): a conta é a do
 * próprio menu, lida de `itensDoMenu` e `secoesDoMenuAdmin`, e não refeita
 * aqui.
 */

import { secoesDoMenuAdmin } from "@/components/admin/AdminSidebar";
import { itensDoMenu, type NavItem } from "@/components/layout/Sidebar";
import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";

export interface PaginaDoManual {
  /** A pasta da página em `public/manual/`, onde moram também os prints. */
  pasta: string;
  modulo: string;
  titulo: string;
  corpo: string;
}

/**
 * Os módulos que uma página pode declarar, na ordem da lista do manual. Cada
 * um vale pelos endereços que ele tem no menu: basta um deles estar no menu da
 * pessoa. Reuniões tem vários porque a Secretária e o Facilitador chegam ao
 * módulo por itens diferentes.
 */
export const MODULOS_DO_MANUAL: readonly { id: string; destinos: readonly string[] }[] = [
  {
    id: "reunioes-e-pendencias",
    destinos: ["/dashboard", "/secretaria", "/reunioes/calendario", "/pendencias"],
  },
  { id: "pops", destinos: ["/pops"] },
  { id: "ouvidoria", destinos: ["/ouvidoria"] },
  { id: "contas-medicas", destinos: ["/contas-medicas"] },
  { id: "central-de-comando", destinos: ["/admin/central-de-comando/visao-geral"] },
  { id: "dados-do-atendimento", destinos: ["/admin/dados-atendimento"] },
  { id: "tecnologia", destinos: ["/admin/tecnologia"] },
];

/** Os endereços de todos os links do menu da pessoa, o do app e o do Admin. */
function linksDoMenu(participante: CurrentParticipante): string[] {
  const folhas = (item: NavItem): string[] =>
    item.subItems?.length ? item.subItems.flatMap(folhas) : [item.href];
  const doApp = itensDoMenu(participante).flatMap(folhas);
  const doAdmin = doApp.includes("/admin")
    ? secoesDoMenuAdmin(participante).flatMap((secao) => secao.items.map((i) => i.href))
    : [];
  return [...doApp, ...doAdmin];
}

/** O módulo existe e está no menu desta pessoa? */
export function moduloEstaNoMenu(modulo: string, participante: CurrentParticipante): boolean {
  const destinos = MODULOS_DO_MANUAL.find((m) => m.id === modulo)?.destinos ?? [];
  const links = linksDoMenu(participante);
  return destinos.some((destino) => links.includes(destino));
}

/**
 * As páginas que a pessoa vê, na ordem dos módulos. Sem participante (a sessão
 * ainda carregando), nenhuma: melhor a lista vazia por um instante do que uma
 * página de módulo que a pessoa não tem.
 */
export function paginasVisiveis(
  paginas: readonly PaginaDoManual[],
  participante: CurrentParticipante | null
): PaginaDoManual[] {
  if (!participante) return [];
  const ordem = (p: PaginaDoManual) => MODULOS_DO_MANUAL.findIndex((m) => m.id === p.modulo);
  return paginas
    .filter((pagina) => moduloEstaNoMenu(pagina.modulo, participante))
    .sort((a, b) => ordem(a) - ordem(b));
}

const CABECALHO = /^---\n([\s\S]*?)\n---\n?/;

/** Lê o texto de uma página. Sem o módulo declarado, recusa. */
export function lerPagina(pasta: string, texto: string): PaginaDoManual {
  const normalizado = texto.replace(/\r\n/g, "\n");
  const cabecalho = CABECALHO.exec(normalizado);
  const campos: Record<string, string> = {};
  for (const linha of cabecalho?.[1].split("\n") ?? []) {
    const [chave, ...resto] = linha.split(":");
    if (resto.length) campos[chave.trim()] = resto.join(":").trim();
  }
  if (!campos.modulo) {
    throw new Error(`A página do manual "${pasta}" não declara o módulo no cabeçalho.`);
  }
  return {
    pasta,
    modulo: campos.modulo,
    titulo: campos.titulo || pasta,
    corpo: normalizado.slice(cabecalho![0].length).trim(),
  };
}

const IMAGEM = /!\[[^\]]*\]\(\s*([^)\s]+)(?:\s+"[^"]*")?\s*\)/g;

/** O `src` de cada imagem citada no Markdown, como foi escrito. */
export function imagensCitadas(corpo: string): string[] {
  return Array.from(corpo.matchAll(IMAGEM), (m) => m[1]);
}

const FLUXOGRAMA = /^```fluxograma[^\n]*\n([\s\S]*?)^```/gm;

/** O texto de cada bloco ```fluxograma do Markdown, na ordem da página. */
export function fluxogramasCitados(corpo: string): string[] {
  return Array.from(corpo.matchAll(FLUXOGRAMA), (m) => m[1]);
}

/**
 * O endereço de uma imagem da página: o print ao lado do Markdown vira
 * `/manual/<pasta>/<arquivo>`; endereço que já começa por `/` fica como está.
 */
export function enderecoDaImagem(pasta: string, src: string): string {
  if (src.startsWith("/") || /^[a-z]+:/i.test(src)) return src;
  return `/manual/${pasta}/${src.replace(/^\.\//, "")}`;
}
