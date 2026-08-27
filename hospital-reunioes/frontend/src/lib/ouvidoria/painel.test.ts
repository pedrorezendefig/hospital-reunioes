/**
 * Painel em tempo real da Ouvidoria (issue #344, PRD #319).
 *
 * A régua do que o painel mostra, testada fora da tela: quem entra em cada
 * bloco, e o que o painel tem o direito de afirmar quando o módulo de métricas
 * avisa que uma leitura de apoio falhou.
 */

import { describe, expect, it } from "vitest";
import {
  areasComVencidas,
  avisosDeDegradacao,
  classificarJanela,
  contarPorStatus,
  criticosAbertos,
  diaNoHospital,
  atrasoFoiMedidoComCalendarioCerto,
  podeVerPainel,
  rotuloDoResponsavel,
  vencendoEm,
  type CasoDoPainel,
  type PendenciaDeArea,
} from "./painel";

// Quarta-feira, 26/08/2026. Os vencimentos são carimbados às 17h de Brasília
// (20h UTC), que é o fim do expediente do motor de prazos (RN-22).
const HOJE = "2026-08-26";

function caso(overrides: Partial<CasoDoPainel> = {}): CasoDoPainel {
  return {
    status: "aguardando_area",
    gravidade: "medio",
    prazo_area_em: `${HOJE}T20:00:00+00:00`,
    ...overrides,
  };
}

function pendencia(overrides: Partial<PendenciaDeArea> = {}): PendenciaDeArea {
  return {
    setor: "Recepcao",
    responsavel: "Carlos Titular",
    pendentes: 3,
    vencidas: 1,
    dias_uteis_de_atraso: 1.7,
    ...overrides,
  };
}

describe("quem abre o painel", () => {
  it("aceita os dois perfis da Ouvidoria", () => {
    expect(podeVerPainel("ouvidor")).toBe(true);
    expect(podeVerPainel("diretoria_executiva")).toBe(true);
  });

  it("recusa quem não tem perfil na Ouvidoria, super admin de Reuniões incluído", () => {
    // O gate da Ouvidoria não tem bypass de super admin (ADR 0034, decisão 8).
    // Aqui só chega o eixo `perfil_ouvidoria`: quem é super admin de Reuniões e
    // não tem papel na Ouvidoria chega exatamente como null.
    expect(podeVerPainel(null)).toBe(false);
    expect(podeVerPainel(undefined)).toBe(false);
    expect(podeVerPainel("")).toBe(false);
    expect(podeVerPainel("facilitador")).toBe(false);
  });
});

describe("o dia civil de um vencimento", () => {
  it("lê o vencimento no fuso do hospital, e não no do navegador", () => {
    // 26/08 às 23h de Brasília é 27/08 em UTC. Lido em UTC, um vencimento da
    // noite de hoje apareceria como "vence amanhã".
    expect(diaNoHospital("2026-08-27T02:00:00+00:00")).toBe("2026-08-26");
    expect(diaNoHospital("2026-08-26T20:00:00+00:00")).toBe("2026-08-26");
  });
});

describe("a janela de vencimento de um caso", () => {
  it("separa vencido, hoje, amanhã e o resto", () => {
    expect(classificarJanela(caso({ prazo_area_em: `${HOJE}T20:00:00+00:00` }), HOJE)).toBe("hoje");
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-27T20:00:00+00:00" }), HOJE)).toBe("amanha");
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-25T20:00:00+00:00" }), HOJE)).toBe("vencido");
    expect(classificarJanela(caso({ prazo_area_em: "2026-08-31T20:00:00+00:00" }), HOJE)).toBe("depois");
  });

  it("caso sem prazo despachado não entra em janela nenhuma", () => {
    expect(classificarJanela(caso({ prazo_area_em: null }), HOJE)).toBe("sem_prazo");
  });

  it("caso parado aguardando o manifestante fica fora da janela, com o relógio parado", () => {
    // O vencimento só é empurrado na retomada (issue #335). Anunciar "vence
    // hoje" num caso pausado cobraria o setor por uma espera que não é dele.
    expect(classificarJanela(caso({ status: "aguardando_manifestante" }), HOJE)).toBe("parado");
  });

  it("caso já respondido ou encerrado sai do radar de vencimento", () => {
    expect(classificarJanela(caso({ status: "respondido" }), HOJE)).toBe("parado");
    expect(classificarJanela(caso({ status: "encerrado" }), HOJE)).toBe("parado");
  });
});

describe("os casos que vencem numa janela", () => {
  it("devolve só os da janela pedida", () => {
    const vencemHoje = [caso({ prazo_area_em: `${HOJE}T13:00:00+00:00` }), caso()];
    const outros = [
      caso({ prazo_area_em: "2026-08-27T20:00:00+00:00" }),
      caso({ prazo_area_em: "2026-08-25T20:00:00+00:00" }),
      caso({ prazo_area_em: null }),
      caso({ status: "encerrado" }),
    ];

    expect(vencendoEm([...vencemHoje, ...outros], "hoje", HOJE)).toEqual(vencemHoje);
    expect(vencendoEm([...vencemHoje, ...outros], "amanha", HOJE)).toEqual([outros[0]]);
  });

  it("ordena do vencimento mais próximo para o mais distante", () => {
    const tarde = caso({ prazo_area_em: `${HOJE}T20:00:00+00:00` });
    const manha = caso({ prazo_area_em: `${HOJE}T11:00:00+00:00` });

    expect(vencendoEm([tarde, manha], "hoje", HOJE)).toEqual([manha, tarde]);
  });
});

describe("os críticos abertos", () => {
  it("traz o caso crítico que ainda não fechou, inclusive o já respondido pela área", () => {
    // A área respondeu, mas o caso grave só sai do radar da Diretoria quando a
    // Ouvidoria encerra.
    const emAndamento = caso({ gravidade: "critico" });
    const respondido = caso({ gravidade: "critico", status: "respondido" });

    expect(criticosAbertos([emAndamento, respondido])).toEqual([emAndamento, respondido]);
  });

  it("deixa de fora o crítico encerrado e o que não é crítico", () => {
    const encerrado = caso({ gravidade: "critico", status: "encerrado" });
    const alto = caso({ gravidade: "alto" });
    const semGravidade = caso({ gravidade: null });

    expect(criticosAbertos([encerrado, alto, semGravidade])).toEqual([]);
  });
});

describe("a fila por status", () => {
  it("conta na ordem do trabalho do ouvidor e não esconde estado vazio", () => {
    const contagem = contarPorStatus([
      caso({ status: "novo" }),
      caso({ status: "novo" }),
      caso({ status: "aguardando_area" }),
      caso({ status: "encerrado" }),
    ]);

    expect(contagem.map((linha) => [linha.status, linha.total])).toEqual([
      ["novo", 2],
      ["em_classificacao", 0],
      ["aguardando_area", 1],
      ["aguardando_manifestante", 0],
      ["respondido", 0],
      ["encerrado", 1],
    ]);
  });

  it("carrega o rótulo que a listagem já usa, para painel e fila falarem igual", () => {
    expect(contarPorStatus([]).map((linha) => linha.label)).toContain("Aguardando área");
  });
});

describe("as áreas com caso vencido", () => {
  it("deixa de fora a área que tem pendência mas nenhuma vencida", () => {
    const emDia = pendencia({ setor: "Farmacia", vencidas: 0, dias_uteis_de_atraso: 0 });
    const atrasada = pendencia();

    expect(areasComVencidas([atrasada, emDia])).toEqual([atrasada]);
  });

  it("preserva a ordem que o módulo de métricas já devolve, da mais atrasada para a menos", () => {
    const pior = pendencia({ setor: "Recepcao", dias_uteis_de_atraso: 4.2 });
    const menos = pendencia({ setor: "Farmacia", dias_uteis_de_atraso: 1.1 });

    expect(areasComVencidas([pior, menos]).map((linha) => linha.setor)).toEqual(["Recepcao", "Farmacia"]);
  });
});

describe("o que o painel pode afirmar quando uma leitura falhou", () => {
  it("sem degradação nenhuma, não inventa aviso", () => {
    expect(avisosDeDegradacao([])).toEqual([]);
  });

  it("avisa que o atraso saiu com calendário errado quando os feriados não foram lidos", () => {
    // O pior caso do contrato: nada vem nulo e o número sai com cara de bom.
    const avisos = avisosDeDegradacao(["feriados"]);

    expect(avisos.map((a) => a.leitura)).toEqual(["feriados"]);
    expect(avisos[0].texto).toContain("feriado");
    expect(atrasoFoiMedidoComCalendarioCerto(["feriados"])).toBe(false);
    expect(atrasoFoiMedidoComCalendarioCerto([])).toBe(true);
  });

  it("avisa que o nome do responsável não pôde ser lido", () => {
    expect(avisosDeDegradacao(["responsaveis"]).map((a) => a.leitura)).toEqual(["responsaveis"]);
  });

  it("cala sobre leitura que não mexe em número nenhum deste painel", () => {
    // `prorrogacoes` e `prazos` degradam a taxa de prorrogação e os trechos de
    // prazo, que são do relatório. Avisar aqui seria ruído sobre número que
    // esta tela nem mostra.
    expect(avisosDeDegradacao(["prorrogacoes", "prazos"])).toEqual([]);
  });
});

describe("o nome de quem responde pelo setor", () => {
  it("mostra o nome quando ele veio", () => {
    expect(rotuloDoResponsavel("Carlos Titular", [])).toBe("Carlos Titular");
  });

  it("diz que o setor está sem titular quando o cadastro FOI lido", () => {
    expect(rotuloDoResponsavel(null, [])).toBe("Sem titular vigente");
  });

  it("não acusa o setor de estar sem titular quando o cadastro não pôde ser lido", () => {
    // Nulo por falha de leitura é indistinguível de nulo por falta de titular
    // (contrato da #341). Sem esta separação, o painel acusaria de cadastro
    // vazio um setor que tem titular.
    const rotulo = rotuloDoResponsavel(null, ["responsaveis"]);

    expect(rotulo).not.toBe("Sem titular vigente");
    expect(rotulo).toBe("Cadastro não lido");
  });
});
