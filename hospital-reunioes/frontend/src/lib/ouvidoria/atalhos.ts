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
 * o que não couber não quebra, transborda. Quem garante que ela cabe é o
 * tamanho dos rótulos, e "cabe" é largura, não contagem de palavras: dois
 * rótulos compridos estouram a linha que cinco curtos não estouram.
 *
 * jsdom não tem layout, então a conta é estimada, a partir do que o CSS fixa
 * (as medidas abaixo saem direto das classes de `AtalhosDaOuvidoria` e do
 * contêiner da fila). O que ela pega com folga é a mudança grande, que é a
 * mesma que já derrubou o topo uma vez: rótulo comprido dentro da pílula.
 */

/** `px-3` dos dois lados (24px), ícone `w-4` (16px) e o `gap-1.5` (6px). */
const MOLDURA_DA_PILULA = 46;

/** O `gap-2` entre as pílulas da `nav`. */
const GAP_ENTRE_PILULAS = 8;

/**
 * O avanço médio de um caractere em `text-sm` (14px) na fonte da casa (HP
 * Simplified, humanista de avanço próximo a 0,54em). É média, e por isso a
 * conta serve para orçamento e não para pixel: o teto abaixo tem folga para
 * absorver o erro dela.
 */
const AVANCO_DO_CARACTERE = 7.6;

/**
 * A largura que sobra para a barra na tela mais estreita em que ela aparece.
 *
 * A `nav` só existe do `md` para cima (768px), e a fila mora num contêiner com
 * `md:p-8`, que come 32px de cada lado. O contêiner do topo tem `flex-wrap`,
 * então a barra desce inteira para uma linha só dela antes de disputar espaço
 * com o título: o que ela não pode é transbordar essa linha.
 */
export const LARGURA_DA_LINHA_DA_BARRA = 768 - 2 * 32;

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
