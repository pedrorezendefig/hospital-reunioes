import { describe, expect, it } from "vitest";
import {
  classificarPrazo,
  classificarPrazoDaManifestacao,
  EM_ANDAMENTO,
  formatarEsperaUtil,
  podeEditarPrazos,
} from "./prazo";

describe("classificarPrazo (destaque do painel de ouvidoria, issues #292 e #320)", () => {
  const hoje = "2026-08-14";

  it("manifestacao em classificacao com prazo estourado e destacada", () => {
    expect(classificarPrazo("2026-08-13", "em_classificacao", hoje)).toBe("estourado");
  });

  it("manifestacao aguardando a area vencendo em ate 2 dias fica perto do prazo", () => {
    expect(classificarPrazo("2026-08-14", "aguardando_area", hoje)).toBe("perto");
    expect(classificarPrazo("2026-08-16", "aguardando_area", hoje)).toBe("perto");
  });

  it("manifestacao com folga fica normal", () => {
    expect(classificarPrazo("2026-08-17", "em_classificacao", hoje)).toBe("normal");
  });

  it("manifestacao nova ainda conta prazo: o relogio corre desde a entrada", () => {
    expect(classificarPrazo("2026-08-13", "novo", hoje)).toBe("estourado");
  });

  it("respondida e encerrada nao recebem destaque, mesmo com prazo passado", () => {
    expect(classificarPrazo("2026-08-01", "respondido", hoje)).toBe("respondido");
    expect(classificarPrazo("2026-08-01", "encerrado", hoje)).toBe("respondido");
  });

  it("os estados em andamento sao os tres antes da resposta da area", () => {
    expect([...EM_ANDAMENTO].sort()).toEqual(["aguardando_area", "em_classificacao", "novo"]);
  });
});

describe("classificarPrazoDaManifestacao (motor de prazos, issue #322)", () => {
  const hoje = "2026-08-24";

  const base = {
    status: "aguardando_area" as const,
    prazo_resposta: "2026-09-30",
    prazo_area_em: null as string | null,
    prazo_estourado: false,
    rotulo_prazo: "sem prazo definido",
    minutos_uteis_restantes: null as number | null,
  };

  it("caso com gravidade usa o veredito do motor, nao a data de 7 dias corridos", () => {
    const estourada = {
      ...base,
      prazo_area_em: "2026-08-21T20:00:00+00:00",
      prazo_estourado: true,
      rotulo_prazo: "vencido há 1 dia útil",
      minutos_uteis_restantes: 0,
    };

    expect(classificarPrazoDaManifestacao(estourada, hoje)).toBe("estourado");
  });

  it("prazo do motor que vence em ate 2 dias uteis fica perto", () => {
    const vencendo = {
      ...base,
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 1 dia útil",
      minutos_uteis_restantes: 540,
    };

    expect(classificarPrazoDaManifestacao(vencendo, hoje)).toBe("perto");
  });

  it("prazo do motor com folga fica normal", () => {
    const folgada = {
      ...base,
      prazo_area_em: "2026-09-10T20:00:00+00:00",
      rotulo_prazo: "vence em 12 dias úteis",
      minutos_uteis_restantes: 12 * 540,
    };

    expect(classificarPrazoDaManifestacao(folgada, hoje)).toBe("normal");
  });

  it("vencimento logo depois do fim de semana fica perto, e nao normal", () => {
    // Sexta olhando um vencimento de segunda 17h: 3 dias corridos, mas 1 dia
    // útil. Medir em dias corridos apagaria o destaque justamente aqui.
    const naSegunda = {
      ...base,
      prazo_area_em: "2026-08-24T20:00:00+00:00",
      rotulo_prazo: "vence em 1 dia útil",
      minutos_uteis_restantes: 540,
    };

    expect(classificarPrazoDaManifestacao(naSegunda, "2026-08-21")).toBe("perto");
  });

  it("caso ainda sem gravidade cai no prazo da fundacao, sem inventar estouro", () => {
    const semClassificacao = { ...base, status: "em_classificacao" as const, prazo_resposta: "2026-08-20" };

    expect(classificarPrazoDaManifestacao(semClassificacao, hoje)).toBe("estourado");
  });

  it("respondida e encerrada nao recebem destaque nem com prazo do motor vencido", () => {
    const respondida = {
      ...base,
      status: "respondido" as const,
      prazo_area_em: "2026-08-21T20:00:00+00:00",
      prazo_estourado: true,
      minutos_uteis_restantes: 0,
    };

    expect(classificarPrazoDaManifestacao(respondida, hoje)).toBe("respondido");
  });
});

describe("podeEditarPrazos (RN-21, issue #322)", () => {
  it("diretoria executiva edita a tabela de prazos", () => {
    expect(podeEditarPrazos("diretoria_executiva")).toBe(true);
  });

  it("ouvidor usa o prazo mas nao o define", () => {
    expect(podeEditarPrazos("ouvidor")).toBe(false);
  });

  it("quem nao tem perfil de ouvidoria nem ve a tela", () => {
    expect(podeEditarPrazos(null)).toBe(false);
    expect(podeEditarPrazos(undefined)).toBe(false);
  });
});

describe("formatarEsperaUtil (issue #335)", () => {
  it("conta o dia útil como nove horas", () => {
    expect(formatarEsperaUtil(9 * 60)).toBe("1 dia útil");
    expect(formatarEsperaUtil(18 * 60)).toBe("2 dias úteis");
  });

  it("junta dias e horas quando sobra tempo", () => {
    expect(formatarEsperaUtil(12 * 60)).toBe("1 dia útil e 3 horas úteis");
    expect(formatarEsperaUtil(60)).toBe("1 hora útil");
  });

  it("nunca deixa as horas alcançarem um dia inteiro", () => {
    // Achado do code review: arredondar o resto por conta própria fazia
    // 535 min virar "9 horas úteis" (um dia útil escrito como horas) e
    // 1074 min virar "1 dia útil e 9 horas úteis".
    expect(formatarEsperaUtil(535)).toBe("1 dia útil");
    expect(formatarEsperaUtil(1074)).toBe("2 dias úteis");
  });

  it("diz que a espera foi curta em vez de mostrar zero", () => {
    expect(formatarEsperaUtil(0)).toBe("menos de uma hora útil");
    expect(formatarEsperaUtil(20)).toBe("menos de uma hora útil");
  });
});
