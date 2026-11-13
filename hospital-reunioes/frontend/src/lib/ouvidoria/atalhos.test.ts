/**
 * Os atalhos do topo da Ouvidoria (issue #496, PRD #471, RN-77, D-16).
 *
 * O topo quebrava em três linhas porque cada porta era uma pílula com o nome
 * inteiro dentro. Aqui a lista deixa de ser JSX espalhado e vira dado: quem
 * pode ver o quê, o rótulo curto da pílula e o nome inteiro que o leitor de
 * tela e o menu do celular usam.
 */

import { describe, expect, it } from "vitest";

import {
  BREAKPOINT_DA_BARRA,
  LARGURA_DA_LINHA_DA_BARRA,
  LARGURA_MINIMA_COM_BARRA,
  atalhosDoPerfil,
  larguraDaBarra,
} from "./atalhos";

function chaves(perfil: string | null | undefined) {
  return atalhosDoPerfil(perfil).map((a) => a.chave);
}

describe("quem vê cada atalho", () => {
  it("o ouvidor vê também a porta dos responsáveis por setor (issue #711)", () => {
    expect(chaves("ouvidor")).toEqual(["painel", "avaliacoes", "nota_externa", "pontos", "responsaveis"]);
  });

  it("a aba Avaliações é dos dois perfis da Ouvidoria e de mais ninguém (issue #1626)", () => {
    // ADR 0086, decisão 8: o comentário não é classificado, e o super admin
    // fica de fora como no Dossiê.
    expect(chaves("ouvidor")).toContain("avaliacoes");
    expect(chaves("diretoria_executiva")).toContain("avaliacoes");
    expect(chaves("secretaria")).not.toContain("avaliacoes");
    expect(chaves(null)).not.toContain("avaliacoes");
  });

  it("a tabela de prazos continua sendo a porta que só a diretoria vê", () => {
    // RN-21: o ouvidor trabalha com o prazo, quem o define é a Diretoria. A
    // decisão 5 do ADR 0055 abriu uma porta, não as duas.
    expect(chaves("ouvidor")).not.toContain("prazos");
  });

  it("a diretoria executiva vê os seis, na ordem do trabalho", () => {
    expect(chaves("diretoria_executiva")).toEqual([
      "painel",
      "avaliacoes",
      "nota_externa",
      "pontos",
      "responsaveis",
      "prazos",
    ]);
  });

  it("quem está fora da Ouvidoria não vê porta nenhuma", () => {
    // O índice da fila é da equipe de Reuniões inteira, e a barra de atalhos
    // não pode oferecer caminho que termina em 403.
    expect(chaves(null)).toEqual([]);
    expect(chaves(undefined)).toEqual([]);
    expect(chaves("secretaria")).toEqual([]);
  });
});

describe("o rótulo curto e o nome inteiro são coisas diferentes (RN-77)", () => {
  it("a pílula do desktop leva o rótulo curto", () => {
    const rotulos = atalhosDoPerfil("diretoria_executiva").map((a) => a.rotulo);

    expect(rotulos).toEqual(["Painel", "Avaliações", "Nota externa", "Pontos", "Responsáveis", "Prazos"]);
  });

  it("o nome inteiro continua existindo, para o leitor de tela e para o menu", () => {
    const nomes = atalhosDoPerfil("diretoria_executiva").map((a) => a.nome);

    expect(nomes).toEqual([
      "Painel em tempo real",
      "Avaliações do QR",
      "Nota externa",
      "Pontos de escuta",
      "Responsáveis por setor",
      "Tabela de prazos",
    ]);
  });

  it("a barra inteira cabe na linha da tela mais estreita em que ela aparece", () => {
    // O perfil que vê as seis portas é o pior caso da barra. Ela é uma linha
    // só, `whitespace-nowrap` e sem `flex-wrap`: o que não couber transborda,
    // e nenhum teste de contagem de palavras enxerga isso.
    const barra = larguraDaBarra(atalhosDoPerfil("diretoria_executiva"));

    expect(barra).toBeLessThanOrEqual(LARGURA_DA_LINHA_DA_BARRA);
  });

  it("o nome inteiro dentro da pílula não caberia, que foi o que derrubou o topo", () => {
    // O mesmo cálculo com os nomes por extenso, que é como a barra era antes
    // da issue #496. Sem este caso o orçamento acima passaria por qualquer
    // conta frouxa, inclusive uma que nunca reprovasse nada.
    const porExtenso = atalhosDoPerfil("diretoria_executiva").map((a) => ({
      ...a,
      rotulo: a.nome,
    }));

    expect(larguraDaBarra(porExtenso)).toBeGreaterThan(LARGURA_DA_LINHA_DA_BARRA);
  });

  it("a sexta pílula não caberia a 1024px, e a barra subiu para o xl (issue #1626)", () => {
    // A 1024px sobram 640px de linha, e as cinco pílulas de antes já ocupavam
    // 581px: nenhuma sexta porta cabia ali. A barra passou a aparecer do `xl`
    // (1280px) para cima, e abaixo dele quem atende é o menu.
    expect(BREAKPOINT_DA_BARRA).toBe("xl");
    expect(LARGURA_MINIMA_COM_BARRA).toBe(1280);
    const seis = atalhosDoPerfil("diretoria_executiva");
    expect(seis).toHaveLength(6);
    expect(larguraDaBarra(seis)).toBeGreaterThan(1024 - 256 - 4 * 32);
  });

  it("cada atalho aponta para a tela dele", () => {
    const destinos = Object.fromEntries(
      atalhosDoPerfil("diretoria_executiva").map((a) => [a.chave, a.href])
    );

    expect(destinos).toEqual({
      painel: "/ouvidoria/painel",
      avaliacoes: "/ouvidoria/avaliacoes",
      nota_externa: "/ouvidoria/nota-externa",
      pontos: "/ouvidoria/pontos",
      responsaveis: "/ouvidoria/responsaveis",
      prazos: "/ouvidoria/prazos",
    });
  });
});
