/**
 * Os textos do Guia da faturista (issue #1121, PRD #1113, ADR 0070).
 *
 * Cada linha começa pelo verbo e diz a quantidade e o período ("Incluir 180,
 * de 03/10 a 05/10"); o valor vai com sinal; a confirmação de concluir conta
 * os itens sem marcação. O esperado vem da spec do diretor (itens 4.3 e 10).
 */
import { describe, expect, it } from "vitest";

import {
  type LinhaGuia,
  perguntaDeConclusao,
  reais,
  rotuloDoGrupo,
  textoDaLinha,
  valorComSinal,
} from "./guia";

function linha(campos: Partial<LinhaGuia>): LinhaGuia {
  return {
    id: "l1",
    acao: "INCLUIR",
    data: "2026-10-03",
    data_fim: null,
    setor: "CTI",
    codigo: "70012345",
    descricao: "Luva de procedimento",
    quantidade_lancada: null,
    quantidade_devida: null,
    preco_lancado: null,
    preco_tabela: null,
    valor_diferenca: null,
    regra_codigo: null,
    motivo: null,
    evidencia_pagina: null,
    evidencia_trecho: null,
    nivel_evidencia: null,
    confianca: null,
    estado: "ABERTA",
    motivo_nao_procede: null,
    texto_nao_procede: null,
    nao_conferido: false,
    ...campos,
  };
}

describe("o texto da linha começa pelo verbo, com quantidade e período", () => {
  it("Incluir diz quanto falta e o período de vários dias", () => {
    const texto = textoDaLinha(
      linha({ quantidade_lancada: 0, quantidade_devida: 180, data_fim: "2026-10-05" }),
    );
    expect(texto).toBe("Incluir 180, de 03/10 a 05/10");
  });

  it("Ajustar quantidade diz de quanto para quanto, num dia", () => {
    const texto = textoDaLinha(
      linha({ acao: "AJUSTAR_QUANTIDADE", quantidade_lancada: 12, quantidade_devida: 9 }),
    );
    expect(texto).toBe("Ajustar quantidade de 12 para 9, em 03/10");
  });

  it("Retirar diz quanto sai", () => {
    const texto = textoDaLinha(linha({ acao: "RETIRAR", quantidade_lancada: 1, quantidade_devida: 0 }));
    expect(texto).toBe("Retirar 1, em 03/10");
  });

  it("Corrigir preço diz o lançado e o da tabela", () => {
    const texto = textoDaLinha(
      linha({ acao: "CORRIGIR_PRECO", preco_lancado: 4.95, preco_tabela: 11.31 }),
    );
    expect(texto).toBe("Corrigir preço de R$ 4,95 para R$ 11,31, em 03/10");
  });

  it("quantidade quebrada sai com vírgula", () => {
    const texto = textoDaLinha(
      linha({ acao: "AJUSTAR_QUANTIDADE", quantidade_lancada: 2.5, quantidade_devida: 3 }),
    );
    expect(texto).toBe("Ajustar quantidade de 2,5 para 3, em 03/10");
  });
});

describe("valores", () => {
  it("reais em pt-BR, com milhar e centavos", () => {
    expect(reais(1212)).toBe("1.212,00");
  });

  it("valor com sinal: positivo com mais, negativo com hífen", () => {
    expect(valorComSinal(68.4)).toBe("+R$ 68,40");
    expect(valorComSinal(-4.17)).toBe("-R$ 4,17");
  });
});

describe("o cabeçalho do grupo e a confirmação de concluir", () => {
  it("grupo por dia e setor", () => {
    expect(rotuloDoGrupo({ data: "2026-10-03", setor: "CTI", linhas: [] })).toBe("03/10 · CTI");
  });

  it("com itens sem marcação, pergunta antes de concluir", () => {
    expect(perguntaDeConclusao(3)).toBe("3 itens sem marcação. Concluir assim mesmo?");
    expect(perguntaDeConclusao(1)).toBe("1 item sem marcação. Concluir assim mesmo?");
  });

  it("sem item sem marcação, não pergunta nada", () => {
    expect(perguntaDeConclusao(0)).toBeNull();
  });
});
