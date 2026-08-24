import { describe, expect, it } from "vitest";
import {
  classificarPrazo,
  classificarPrazoDaManifestacao,
  EM_ANDAMENTO,
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
  };

  it("caso com gravidade usa o veredito do motor, nao a data de 7 dias corridos", () => {
    const estourada = {
      ...base,
      prazo_area_em: "2026-08-21T20:00:00+00:00",
      prazo_estourado: true,
      rotulo_prazo: "vencido há 1 dia útil",
    };

    expect(classificarPrazoDaManifestacao(estourada, hoje)).toBe("estourado");
  });

  it("prazo do motor que vence em ate 2 dias fica perto", () => {
    const vencendo = { ...base, prazo_area_em: "2026-08-25T20:00:00+00:00", rotulo_prazo: "vence em 1 dia útil" };

    expect(classificarPrazoDaManifestacao(vencendo, hoje)).toBe("perto");
  });

  it("prazo do motor com folga fica normal", () => {
    const folgada = { ...base, prazo_area_em: "2026-09-10T20:00:00+00:00", rotulo_prazo: "vence em 12 dias úteis" };

    expect(classificarPrazoDaManifestacao(folgada, hoje)).toBe("normal");
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
