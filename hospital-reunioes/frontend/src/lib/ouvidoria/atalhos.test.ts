/**
 * Os atalhos do topo da Ouvidoria (issue #496, PRD #471, RN-77, D-16).
 *
 * O topo quebrava em três linhas porque cada porta era uma pílula com o nome
 * inteiro dentro. Aqui a lista deixa de ser JSX espalhado e vira dado: quem
 * pode ver o quê, o rótulo curto da pílula e o nome inteiro que o leitor de
 * tela e o menu do celular usam.
 */

import { describe, expect, it } from "vitest";

import { atalhosDoPerfil } from "./atalhos";

function chaves(perfil: string | null | undefined) {
  return atalhosDoPerfil(perfil).map((a) => a.chave);
}

describe("quem vê cada atalho", () => {
  it("o ouvidor vê o painel, a nota externa e os pontos de escuta", () => {
    expect(chaves("ouvidor")).toEqual(["painel", "nota_externa", "pontos"]);
  });

  it("a diretoria executiva vê os cinco, na ordem do trabalho", () => {
    expect(chaves("diretoria_executiva")).toEqual([
      "painel",
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

    expect(rotulos).toEqual(["Painel", "Nota externa", "Pontos", "Responsáveis", "Prazos"]);
  });

  it("o nome inteiro continua existindo, para o leitor de tela e para o menu", () => {
    const nomes = atalhosDoPerfil("diretoria_executiva").map((a) => a.nome);

    expect(nomes).toEqual([
      "Painel em tempo real",
      "Nota externa",
      "Pontos de escuta",
      "Responsáveis por setor",
      "Tabela de prazos",
    ]);
  });

  it("nenhum rótulo tem palavra suficiente para quebrar a pílula em duas linhas", () => {
    // O que fazia o topo quebrar era o nome inteiro dentro da pílula. Duas
    // palavras é o teto: com três, a barra volta a não caber numa linha só.
    for (const atalho of atalhosDoPerfil("diretoria_executiva")) {
      expect(atalho.rotulo.split(" ").length).toBeLessThanOrEqual(2);
    }
  });

  it("cada atalho aponta para a tela dele", () => {
    const destinos = Object.fromEntries(
      atalhosDoPerfil("diretoria_executiva").map((a) => [a.chave, a.href])
    );

    expect(destinos).toEqual({
      painel: "/ouvidoria/painel",
      nota_externa: "/ouvidoria/nota-externa",
      pontos: "/ouvidoria/pontos",
      responsaveis: "/ouvidoria/responsaveis",
      prazos: "/ouvidoria/prazos",
    });
  });
});
