/**
 * Os atalhos do topo da Ouvidoria (issue #496, PRD #471, RN-77, D-16).
 *
 * Eram cinco pílulas escritas à mão no JSX da fila, cada uma com o nome
 * inteiro dentro e o gate do perfil ao lado. Com o contador de volume no mesmo
 * contêiner, o topo quebrava em três linhas.
 *
 * A lista virou dado por dois motivos. O primeiro é que ela é desenhada em
 * dois lugares agora, a barra do computador e o menu do celular, e lista
 * copiada é lista que diverge: a porta nova de amanhã nasceria só num deles. O
 * segundo é o rótulo: a pílula precisa de um nome curto para caber numa linha
 * só, e o leitor de tela precisa do nome inteiro. Com os dois no mesmo lugar,
 * ninguém encurta um sem responder pelo outro.
 */

import { podeRegistrarNotaExterna } from "./nota-externa";
import { podeVerPainel } from "./painel";
import { podeGerirPontos } from "./pontos";
import { podeEditarPrazos } from "./prazo";
import { podeGerirResponsaveis } from "./validacao";

export type ChaveDeAtalho = "painel" | "nota_externa" | "pontos" | "responsaveis" | "prazos";

export interface Atalho {
  chave: ChaveDeAtalho;
  href: string;
  /** O que a pílula do computador mostra: curto o bastante para não quebrar. */
  rotulo: string;
  /** O nome inteiro: nome acessível da pílula e texto do menu do celular. */
  nome: string;
}

/**
 * Na ordem do trabalho: o retrato de agora, o que entra de fora, os lugares de
 * escuta e, por último, os dois cadastros que a Diretoria mantém.
 */
const ATALHOS: (Atalho & { permitido: (perfil: string | null | undefined) => boolean })[] = [
  {
    // O retrato de agora, restrito aos dois perfis da Ouvidoria (issue #344):
    // o painel mostra o caso sigiloso junto dos demais.
    chave: "painel",
    href: "/ouvidoria/painel",
    rotulo: "Painel",
    nome: "Painel em tempo real",
    permitido: podeVerPainel,
  },
  {
    // A nota de fora entra pela mão do ouvidor, e é a Ouvidoria inteira que
    // responde por ela (issue #347).
    chave: "nota_externa",
    href: "/ouvidoria/nota-externa",
    rotulo: "Nota externa",
    nome: "Nota externa",
    permitido: podeRegistrarNotaExterna,
  },
  {
    chave: "pontos",
    href: "/ouvidoria/pontos",
    rotulo: "Pontos",
    nome: "Pontos de escuta",
    permitido: podeGerirPontos,
  },
  {
    chave: "responsaveis",
    href: "/ouvidoria/responsaveis",
    rotulo: "Responsáveis",
    nome: "Responsáveis por setor",
    permitido: podeGerirResponsaveis,
  },
  {
    // RN-21: quem define o prazo é a Diretoria Executiva. Os demais perfis não
    // veem sequer a porta da tela.
    chave: "prazos",
    href: "/ouvidoria/prazos",
    rotulo: "Prazos",
    nome: "Tabela de prazos",
    permitido: podeEditarPrazos,
  },
];

/**
 * As portas que este perfil pode abrir. O gate de verdade é do servidor, que
 * recusa cada uma dessas telas a quem não pode: aqui só não se oferece o
 * caminho que terminaria em 403.
 */
export function atalhosDoPerfil(perfil: string | null | undefined): Atalho[] {
  return ATALHOS.filter(({ permitido }) => permitido(perfil)).map(
    ({ chave, href, rotulo, nome }) => ({ chave, href, rotulo, nome })
  );
}

/*
 * O orçamento de largura da barra (RN-77, D-16).
 *
 * A `nav` do computador é uma linha só, `whitespace-nowrap` e sem `flex-wrap`:
 * o que não couber não quebra, transborda, e o `main` do AppShell tem
 * `overflow-auto`, então o transbordo vira a rolagem horizontal que a RN-73
 * proíbe. Quem garante que ela cabe é o tamanho dos rótulos, e "cabe" é
 * largura, não contagem de palavras: dois rótulos compridos estouram a linha
 * que cinco curtos não estouram.
 *
 * jsdom não tem layout, então a conta é estimada, a partir do que o CSS fixa.
 * As medidas abaixo saem direto das classes de `AtalhosDaOuvidoria`, do
 * `AppShell` e do contêiner da fila, e é por isso que elas vêm em parcelas
 * nomeadas: a primeira versão desta conta esqueceu o sidebar e afirmou que
 * cabia, na largura errada, uma barra que transbordava 200px.
 */

/** `px-3` dos dois lados (24px), ícone `w-4` (16px) e o `gap-1.5` (6px). */
const MOLDURA_DA_PILULA = 46;

/** O `gap-2` entre as pílulas da `nav`. */
const GAP_ENTRE_PILULAS = 8;

/**
 * O avanço médio de um caractere em `text-sm` (14px) na fonte da casa (HP
 * Simplified, humanista de avanço próximo a 0,54em). É média, e por isso a
 * conta serve para orçamento e não para pixel.
 *
 * Vale para CAIXA MISTA, que é como a barra é escrita. Maiúscula alarga o
 * avanço em cerca de 10% (o número vira ~8,4), e o `tracking-wide` que a
 * acompanha soma outros 0,35px por caractere. Quem um dia revir a decisão de
 * manter a barra em caixa mista (`lib/ouvidoria/tipografia`) precisa aplicar
 * esse fator aqui antes de olhar o resultado: com ele, a barra de hoje passa
 * de 581px para cerca de 623px contra os 640px da linha, e a folga que sobra
 * fica menor que o erro do próprio modelo.
 */
const AVANCO_DO_CARACTERE = 7.6;

/** O `w-64` do sidebar do AppShell, que divide a tela com a área de conteúdo. */
const SIDEBAR = 256;

/**
 * O `md:p-8` do `main` do AppShell mais o `md:p-8` do contêiner da fila, dos
 * dois lados de cada um. O `max-w-6xl` da fila não entra: nas larguras de que
 * este orçamento trata, é a tela que aperta, não o teto do contêiner.
 */
const PADDING_ATE_A_BARRA = 4 * 32;

/**
 * A tela mais estreita em que a barra do computador aparece: o `lg` do
 * Tailwind, e não o `md`.
 *
 * O `md` era o ponto original, e nele a barra não cabia. O sidebar do AppShell
 * é `hidden md:flex w-64`, ou seja, aparece no MESMO ponto que a barra: a
 * 768px sobram 384px de linha para uma barra de 581px. A barra fica no `lg`
 * porque é onde a conta fecha; abaixo dele quem atende é o menu que a issue
 * #496 já construiu, que é a saída projetada para quando a linha não cabe.
 */
export const BREAKPOINT_DA_BARRA = "lg";

/** Os pontos do Tailwind que o módulo usa, em pixels. */
const LARGURA_DO_BREAKPOINT: Record<string, number> = { md: 768, lg: 1024 };

export const LARGURA_MINIMA_COM_BARRA = LARGURA_DO_BREAKPOINT[BREAKPOINT_DA_BARRA];

/** A largura que sobra para a barra na tela mais estreita em que ela aparece. */
export const LARGURA_DA_LINHA_DA_BARRA =
  LARGURA_MINIMA_COM_BARRA - SIDEBAR - PADDING_ATE_A_BARRA;

/** A largura estimada da barra de atalhos, em pixels. */
export function larguraDaBarra(atalhos: Atalho[]): number {
  if (atalhos.length === 0) return 0;
  const caracteres = atalhos.reduce((total, { rotulo }) => total + rotulo.length, 0);
  return (
    atalhos.length * MOLDURA_DA_PILULA +
    (atalhos.length - 1) * GAP_ENTRE_PILULAS +
    caracteres * AVANCO_DO_CARACTERE
  );
}
