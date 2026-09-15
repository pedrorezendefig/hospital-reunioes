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
  lerAFalhaDoRedirecionamento,
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

/**
 * As respostas do backend, palavra por palavra, de `app/routers/ouvidoria.py`
 * (`origin/main`). Cada uma existe num caminho real da rota.
 */
const SAIU_DA_AREA_NO_MEIO =
  "Este caso saiu da fila da área durante o envio, então o redirecionamento não valeu por ele. " +
  "Confira a manifestação no painel antes de tentar de novo.";
const FALHA_DEPOIS_DA_SAIDA =
  "O caso saiu da área anterior e está em classificação, mas a área nova não foi acionada. " +
  "Use Validar e acionar para despachá-lo, sem redirecionar de novo.";
const FALHA_DE_ESTADO_INDETERMINADO =
  "O redirecionamento não terminou. Confira a manifestação no painel antes de agir: " +
  "o caso pode já estar com a área nova.";

describe("o que a tela faz com a falha do redirecionamento (issue #710)", () => {
  it("409 do `restaurar` que não casou linha: o relógio parou e não voltou, então a tela relê", () => {
    // Caminho (a): o `parar` JÁ GRAVOU (prazo, respondida_em e quem respondeu
    // foram limpos), a RPC de saída falhou e o `restaurar` não casou linha. O
    // backend responde 409, e derivar "o caso se moveu" da FAIXA do status
    // deixaria este caso de fora: o Dossiê seguiria desenhando um prazo que já
    // não existe.
    expect(lerAFalhaDoRedirecionamento(409, SAIU_DA_AREA_NO_MEIO)).toEqual({
      releiaOCaso: true,
      atoConsumido: true,
    });
  });

  it("409 com o prefixo da falha DEPOIS da saída: o caso já saiu da área", () => {
    // Caminho (b): o 23514 da transição de ENTRADA, dentro de `acionar_a_area`,
    // que no redirecionamento só roda depois do ponto sem volta. O orquestrador
    // preserva o `status_code`, então existe um 409 cujo texto começa com a
    // frase da falha depois da saída.
    const detail = `${FALHA_DEPOIS_DA_SAIDA} O acionamento respondeu: Transição recusada`;

    expect(lerAFalhaDoRedirecionamento(409, detail)).toEqual({
      releiaOCaso: true,
      atoConsumido: true,
    });
  });

  it("503 com o mesmo prefixo (a tabela de prazos fora do ar) também", () => {
    // O código de quem falhou é preservado: um 503 não pode virar 500 nem
    // deixar de ser lido como ponto sem volta.
    const detail = `${FALHA_DEPOIS_DA_SAIDA} O acionamento respondeu: tabela de prazos indisponível`;

    expect(lerAFalhaDoRedirecionamento(503, detail)).toEqual({
      releiaOCaso: true,
      atoConsumido: true,
    });
  });

  it("a frase que não afirma estado nenhum: relê e não convida a repetir", () => {
    expect(lerAFalhaDoRedirecionamento(500, FALHA_DE_ESTADO_INDETERMINADO)).toEqual({
      releiaOCaso: true,
      atoConsumido: true,
    });
  });

  it("CONTRAPROVA: as recusas decididas ANTES de qualquer escrita fecham sem releitura", () => {
    // Sem esta, a régua poderia virar "relê sempre" sem ninguém notar, e o
    // ouvidor levaria uma leitura a cada caractere errado no motivo.
    const antesDeQualquerEfeito: [number, string][] = [
      [
        409,
        "Este caso está pausado à espera do manifestante. Retome o caso antes de redirecionar: " +
          "o relógio parado da pausa e o prazo cheio da área nova não se misturam na mesma ação.",
      ],
      [
        409,
        "Este caso já está com essa área, então não há para onde redirecioná-lo. " +
          "Escolha outra área, ou use a devolução por insuficiência para cobrar de novo a mesma, " +
          "que recalcula o prazo em vez de dar um novo por inteiro.",
      ],
      [
        409,
        "O setor Centro Medico não tem titular nem gestor vigente cadastrado. " +
          "Cadastre o responsável antes de acionar.",
      ],
      [
        409,
        "Este caso não está com nenhuma área: ele espera o despacho da Ouvidoria. " +
          "Use Validar e acionar para escolher a área.",
      ],
      [
        422,
        "Diga por que este caso vai para outra área: sem o motivo, a trilha não conta por que ele saiu de onde estava.",
      ],
      [422, "O motivo passou de 10.000 caracteres. Resuma por que o caso vai para outra área."],
      [403, "Acesso restrito ao Perfil da Ouvidoria"],
      [404, "Manifestação não encontrada"],
    ];

    for (const [status, detail] of antesDeQualquerEfeito) {
      expect(lerAFalhaDoRedirecionamento(status, detail)).toEqual({
        releiaOCaso: false,
        atoConsumido: false,
      });
    }
  });

  it("o 23514 da RPC de SAÍDA fecha sem releitura, porque o prazo voltou", () => {
    // Nesse ramo o `restaurar` CASOU linha: o prazo da área foi restaurado e o
    // caso continua onde estava. A frase do servidor já manda recarregar a
    // página, e quem faz isso é o ouvidor, não esta régua.
    expect(
      lerAFalhaDoRedirecionamento(409, "O caso foi movimentado agora mesmo por outra porta: recarregue a página.")
    ).toEqual({ releiaOCaso: false, atoConsumido: false });
  });

  it("5xx sem marca nenhuma: relê, mas continua podendo tentar de novo", () => {
    // "O prazo da área anterior não foi encerrado, então nada foi
    // redirecionado. O caso continua com ela. Tente de novo em instantes." O
    // servidor CONVIDA a repetir: travar o botão aqui contradiria a resposta.
    const falhaDoRelogio =
      "O prazo da área anterior não foi encerrado, então nada foi redirecionado. " +
      "O caso continua com ela. Tente de novo em instantes.";

    expect(lerAFalhaDoRedirecionamento(500, falhaDoRelogio)).toEqual({
      releiaOCaso: true,
      atoConsumido: false,
    });
  });

  it("resposta sem texto legível e requisição sem resposta caem no lado seguro", () => {
    // Não saber conta como "pode ter mudado", e não como "está tudo bem": a
    // leitura a mais custa um GET, e a tela velha custa um despacho errado.
    expect(lerAFalhaDoRedirecionamento(500, null)).toEqual({
      releiaOCaso: true,
      atoConsumido: false,
    });
    expect(lerAFalhaDoRedirecionamento(null, null)).toEqual({
      releiaOCaso: true,
      atoConsumido: false,
    });
  });

  it("o 429 do limite de taxa não manda ninguém conferir o painel", () => {
    // O handler do slowapi responde sem `detail` e nada aconteceu no servidor.
    expect(lerAFalhaDoRedirecionamento(429, null)).toEqual({
      releiaOCaso: false,
      atoConsumido: false,
    });
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
