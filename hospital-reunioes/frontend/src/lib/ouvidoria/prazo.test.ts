import { describe, expect, it } from "vitest";
import {
  classificarPrazo,
  classificarPrazoDaManifestacao,
  diaNoHospital,
  EM_ANDAMENTO,
  formatarEsperaUtil,
  hojeNoHospital,
  podeEditarPrazos,
} from "./prazo";

describe("classificarPrazo (destaque do painel de ouvidoria, issues #292 e #320)", () => {
  const hoje = "2026-08-14";

  it("manifestacao em classificacao com prazo estourado e destacada", () => {
    expect(classificarPrazo("2026-08-13", "em_classificacao", hoje)).toBe("estourado");
  });

  it("manifestacao que vence hoje entra no vermelho, junto do vencido (issue #488)", () => {
    expect(classificarPrazo("2026-08-14", "aguardando_area", hoje)).toBe("vence_hoje");
  });

  it("manifestacao que vence amanha fica em ambar, e nao em vermelho (issue #488)", () => {
    expect(classificarPrazo("2026-08-15", "aguardando_area", hoje)).toBe("perto");
  });

  it("a fronteira do ambar e o dia seguinte: depois dele a linha fica neutra", () => {
    // O alerta acendia com 2 dias de folga (D-13). Quando tudo é urgente, nada
    // é urgente: 16/08 está a 2 dias de 14/08 e agora sai da cor.
    expect(classificarPrazo("2026-08-16", "aguardando_area", hoje)).toBe("normal");
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

  it("prazo do motor que vence em ate 1 dia util fica perto", () => {
    const vencendo = {
      ...base,
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 1 dia útil",
      minutos_uteis_restantes: 540,
    };

    expect(classificarPrazoDaManifestacao(vencendo, hoje)).toBe("perto");
  });

  it("vencimento de hoje e vermelho, e nao ambar (issue #488)", () => {
    // A fronteira que o semáforo recalibrado precisa acertar: a MESMA folga de
    // um dia útil, num vencimento de hoje e num de amanhã, tem urgências
    // diferentes. Só o de hoje acende vermelho.
    const venceHoje = {
      ...base,
      prazo_area_em: "2026-08-24T20:00:00+00:00",
      rotulo_prazo: "vence em 3 horas úteis",
      minutos_uteis_restantes: 180,
    };
    const venceAmanha = { ...venceHoje, prazo_area_em: "2026-08-25T20:00:00+00:00" };

    expect(classificarPrazoDaManifestacao(venceHoje, hoje)).toBe("vence_hoje");
    expect(classificarPrazoDaManifestacao(venceAmanha, hoje)).toBe("perto");
  });

  it("vencimento das 23h de hoje ainda e de hoje, e nao de amanha em UTC", () => {
    // 02h UTC do dia 25 são 23h do dia 24 em Brasília. Ler o dia em UTC
    // empurraria para amanhã justamente o caso que vence hoje.
    const hojeANoite = {
      ...base,
      prazo_area_em: "2026-08-25T02:00:00+00:00",
      rotulo_prazo: "vence hoje",
      minutos_uteis_restantes: 60,
    };

    expect(classificarPrazoDaManifestacao(hojeANoite, hoje)).toBe("vence_hoje");
  });

  it("dia de vencimento ja passado e vermelho mesmo sem o carimbo do motor", () => {
    // A fila e o painel precisam dizer a mesma coisa do mesmo caso: o painel já
    // lê o dia vencido como vencido quando o carimbo do motor está atrasado.
    const ontem = {
      ...base,
      prazo_area_em: "2026-08-23T20:00:00+00:00",
      prazo_estourado: false,
      minutos_uteis_restantes: 0,
    };

    expect(classificarPrazoDaManifestacao(ontem, hoje)).toBe("estourado");
  });

  it("folga acima de um dia util sai da cor de alerta (issue #488)", () => {
    // Vence depois de amanhã com dois dias úteis de folga: a escala antiga
    // pintava de âmbar (D-13), a nova deixa neutro.
    const doisDiasUteis = {
      ...base,
      prazo_area_em: "2026-08-26T20:00:00+00:00",
      rotulo_prazo: "vence em 2 dias úteis",
      minutos_uteis_restantes: 2 * 540,
    };
    const umDiaUtilCheio = { ...doisDiasUteis, minutos_uteis_restantes: 540 };

    expect(classificarPrazoDaManifestacao(doisDiasUteis, hoje)).toBe("normal");
    expect(classificarPrazoDaManifestacao(umDiaUtilCheio, hoje)).toBe("perto");
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
    expect(classificarPrazoDaManifestacao({ ...respondida, status: "encerrado" }, hoje)).toBe(
      "respondido"
    );
  });

  it("caso encerrado que venceria hoje segue sem semaforo: o relogio parou", () => {
    const encerrada = {
      ...base,
      status: "encerrado" as const,
      prazo_area_em: "2026-08-24T20:00:00+00:00",
      minutos_uteis_restantes: 180,
    };

    expect(classificarPrazoDaManifestacao(encerrada, hoje)).toBe("respondido");
  });
});

describe("o dia civil no fuso do hospital (issue #488)", () => {
  it("le o dia do vencimento em Brasilia, e nao em UTC", () => {
    expect(diaNoHospital("2026-08-27T02:00:00+00:00")).toBe("2026-08-26");
    expect(diaNoHospital("2026-08-26T20:00:00+00:00")).toBe("2026-08-26");
  });

  it("hoje sai da mesma regua", () => {
    expect(hojeNoHospital(new Date("2026-08-27T02:00:00Z"))).toBe("2026-08-26");
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
