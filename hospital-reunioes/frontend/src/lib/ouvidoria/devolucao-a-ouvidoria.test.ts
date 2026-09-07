import { describe, expect, it } from "vitest";

import { devolucaoAOuvidoria, PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA } from "./devolucao-a-ouvidoria";
import type { EventoDaTrilha } from "./trilha";

/** O movimento que a Devolução à Ouvidoria escreve na trilha (issue #600). */
function devolucao(overrides: Partial<EventoDaTrilha> = {}): EventoDaTrilha {
  return {
    ocorrido_em: "2026-08-26T17:00:00+00:00",
    autor: "Carlos Titular",
    // A devolução chega pelo link do email: ninguém logado por trás.
    sistema: true,
    marco: null,
    marco_rotulo: null,
    descricao: "Caso em classificação",
    texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} Recepcao: Este caso é do Centro Médico, não nosso.`,
    desde_marco: null,
    desde_marco_rotulo: null,
    minutos_uteis: null,
    ...overrides,
  };
}

function outroEvento(overrides: Partial<EventoDaTrilha> = {}): EventoDaTrilha {
  return { ...devolucao(), descricao: "Caso validado e área acionada", texto: null, ...overrides };
}

describe("a devolução à Ouvidoria lida da trilha (issue #601)", () => {
  it("lê o setor que devolveu, o motivo, quem devolveu e quando", () => {
    const lido = devolucaoAOuvidoria([devolucao()], "em_classificacao");

    expect(lido).toEqual({
      setor: "Recepcao",
      motivo: "Este caso é do Centro Médico, não nosso.",
      autor: "Carlos Titular",
      ocorrido_em: "2026-08-26T17:00:00+00:00",
      vezes: 1,
    });
  });

  it("caso que nunca foi devolvido não tem bloco nenhum", () => {
    expect(devolucaoAOuvidoria([outroEvento()], "em_classificacao")).toBeNull();
  });

  it("conta as devoluções e mostra a última, que é de onde o caso acabou de voltar", () => {
    // A trilha chega do mais novo para o mais antigo, como o servidor a
    // entrega. Pegar a primeira da lista é pegar a devolução corrente: no
    // pingue-pongue, mostrar a mais antiga mandaria o ouvidor para a área
    // errada de novo.
    const lido = devolucaoAOuvidoria(
      [
        devolucao({
          ocorrido_em: "2026-09-02T14:00:00+00:00",
          autor: "Dra. Bianca",
          texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} Centro Medico: O caso é da Recepção.`,
        }),
        outroEvento(),
        devolucao(),
      ],
      "em_classificacao"
    );

    expect(lido?.vezes).toBe(2);
    expect(lido?.setor).toBe("Centro Medico");
    expect(lido?.autor).toBe("Dra. Bianca");
  });

  it("caso que o ouvidor já reacionou não mostra mais o bloco", () => {
    // O bloco é o convite a despachar de novo, não um histórico: com o caso
    // já na área certa, ele cobraria uma ação que ninguém tem a fazer. O que
    // aconteceu continua na linha do tempo.
    expect(devolucaoAOuvidoria([devolucao()], "aguardando_area")).toBeNull();
  });

  it("motivo escrito pelo ouvidor não vira devolução da área, mesmo copiando a frase", () => {
    // O motivo da devolução por insuficiência é texto livre do ouvidor e chega
    // à trilha sem rótulo interno. Só a frase não separa os dois atos: quem
    // separa é ter alguém logado por trás.
    const doOuvidor = devolucao({ sistema: false, autor: "Marta Ouvidora" });

    expect(devolucaoAOuvidoria([doOuvidor], "em_classificacao")).toBeNull();
  });

  it("motivo com dois-pontos no meio chega inteiro", () => {
    const lido = devolucaoAOuvidoria(
      [
        devolucao({
          texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} Recepcao: Falei com a chefia: é do Centro Médico.`,
        }),
      ],
      "em_classificacao"
    );

    expect(lido?.motivo).toBe("Falei com a chefia: é do Centro Médico.");
  });
});
