/**
 * O Redirecionamento lido da trilha (issue #710, PRD #706, ADR 0055).
 *
 * O ponto destes testes é a fronteira entre os dois atos que escrevem na MESMA
 * coluna da MESMA trilha e chegam ao MESMO estado: a Devolução à Ouvidoria (a
 * área diz que o caso não é dela) e o Redirecionamento (o ouvidor tira o caso
 * da área). Se um passar pelo outro, a contagem de devoluções do Dossiê passa a
 * incluir os redirecionamentos da própria Ouvidoria, que é o que o ADR 0055
 * manda evitar.
 */

import { describe, expect, it } from "vitest";

import { devolucaoAOuvidoria, PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA } from "./devolucao-a-ouvidoria";
import {
  confirmacaoDoRedirecionamento,
  PREFIXO_DO_REDIRECIONAMENTO,
  redirecionamentoDoEvento,
  rotuloDoRedirecionamento,
} from "./redirecionamento";
import type { EventoDaTrilha } from "./trilha";

/**
 * O movimento de saída que o servidor escreve, palavra por palavra o
 * `observacao_do_redirecionamento` de
 * `app/services/ouvidoria_redirecionamento.py`.
 */
function redirecionamento(overrides: Partial<EventoDaTrilha> = {}): EventoDaTrilha {
  return {
    ocorrido_em: "2026-09-15T13:00:00+00:00",
    autor: "Ana Ouvidora",
    // O ouvidor está LOGADO: o `autor_id` do movimento não é nulo, e é isso que
    // separa este ato da devolução, que chega pelo link do email.
    sistema: false,
    apagamento: false,
    marco: null,
    marco_rotulo: null,
    descricao: "Caso em classificação",
    texto: `${PREFIXO_DO_REDIRECIONAMENTO} (de Recepcao): O caso é de conduta médica.`,
    desde_marco: null,
    desde_marco_rotulo: null,
    minutos_uteis: null,
    ...overrides,
  };
}

describe("o redirecionamento lido da trilha (issue #710)", () => {
  it("lê a área de onde o caso saiu e o motivo", () => {
    expect(redirecionamentoDoEvento(redirecionamento())).toEqual({
      setor: "Recepcao",
      motivo: "O caso é de conduta médica.",
    });
  });

  it("guarda o motivo inteiro quando ele tem o separador dentro", () => {
    // O motivo é texto livre de até 10.000 caracteres, e o ouvidor escreve
    // dois pontos à vontade. Cortar em toda ocorrência perderia o resto.
    const lido = redirecionamentoDoEvento(
      redirecionamento({
        texto: `${PREFIXO_DO_REDIRECIONAMENTO} (de Recepcao): Motivo: a área não apura conduta): e nem deve.`,
      })
    );

    expect(lido?.setor).toBe("Recepcao");
    expect(lido?.motivo).toBe("Motivo: a área não apura conduta): e nem deve.");
  });

  it("o caso sem setor gravado sai com a palavra que o servidor escreveu", () => {
    // O backend escreve "de sem setor" quando a coluna está nula. A tela
    // mostra o que ele escreveu, em vez de inventar um nome de área.
    const lido = redirecionamentoDoEvento(
      redirecionamento({ texto: `${PREFIXO_DO_REDIRECIONAMENTO} (de sem setor): Sem área gravada.` })
    );

    expect(lido?.setor).toBe("sem setor");
  });

  it("a devolução da área não passa por redirecionamento", () => {
    // O ato irmão, que chega ao MESMO estado e escreve na MESMA coluna.
    const devolucao = redirecionamento({
      sistema: true,
      autor: "Carlos Titular",
      texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} Recepcao: Este caso é do Centro Médico.`,
    });

    expect(redirecionamentoDoEvento(devolucao)).toBeNull();
  });

  it("a resposta da área com a frase copiada não passa", () => {
    // O titular que não achou o botão escreve o que quiser no campo do que foi
    // feito, e a frase sozinha não prova ato nenhum. Quem elimina este caso é
    // `sistema`: quem responde pelo link do email não tem login.
    const respostaCopiada = redirecionamento({ sistema: true, autor: "Carlos Titular" });

    expect(redirecionamentoDoEvento(respostaCopiada)).toBeNull();
  });

  it("movimento que não é a volta para a classificação não passa", () => {
    // A descrição nomeia a transição no grafo. Sem ela, uma observação de
    // encerramento escrita à mão com a mesma abertura passaria por
    // redirecionamento.
    expect(redirecionamentoDoEvento(redirecionamento({ descricao: "Caso encerrado" }))).toBeNull();
  });

  it("movimento sem texto e com a frase truncada não passa", () => {
    expect(redirecionamentoDoEvento(redirecionamento({ texto: null }))).toBeNull();
    // A Retenção zera a observação depois de cinco anos: o rótulo some, e o
    // movimento volta a ser a transição genérica em vez de quebrar a tela.
    expect(redirecionamentoDoEvento(redirecionamento({ texto: "" }))).toBeNull();
    // Prefixo sem o fecho do setor: nada a desmontar.
    expect(
      redirecionamentoDoEvento(redirecionamento({ texto: `${PREFIXO_DO_REDIRECIONAMENTO} (de Recepcao` }))
    ).toBeNull();
  });
});

describe("o redirecionamento não conta como devolução (ADR 0055)", () => {
  it("o caso que ficou em classificação depois de um redirecionamento não mostra bloco de devolução", () => {
    // Este é o cenário de verdade, e não um caso de laboratório: quando o
    // acionamento da área nova falha DEPOIS da saída, o caso fica em
    // "em classificação" com o movimento do redirecionamento na trilha. É
    // exatamente o estado em que o bloco da devolução aparece.
    expect(devolucaoAOuvidoria([redirecionamento()], "em_classificacao")).toBeNull();
  });

  it("a devolução continua contando ao lado do redirecionamento", () => {
    // A contraprova: o módulo irmão não pode ter parado de enxergar o ato dele.
    const devolucao = redirecionamento({
      sistema: true,
      autor: "Carlos Titular",
      texto: `${PREFIXO_DA_DEVOLUCAO_A_OUVIDORIA} Recepcao: Este caso é do Centro Médico.`,
    });

    const lido = devolucaoAOuvidoria([redirecionamento(), devolucao], "em_classificacao");

    expect(lido?.setor).toBe("Recepcao");
    expect(lido?.vezes).toBe(1);
  });
});

describe("as frases do redirecionamento", () => {
  it("o rótulo da trilha nomeia o ato e a área de onde o caso saiu", () => {
    expect(rotuloDoRedirecionamento("Recepcao")).toBe("Redirecionado pelo ouvidor (de Recepcao)");
  });

  it("a confirmação diz a área nova e que a anterior foi avisada", () => {
    expect(confirmacaoDoRedirecionamento("Centro Medico")).toBe(
      "Caso redirecionado para Centro Medico. A área anterior foi avisada."
    );
  });
});
