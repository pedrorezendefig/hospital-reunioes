/**
 * O Markdown simples do "O que muda", do lado da tela (issue #676, ADR 0054).
 *
 * As contas da Conversa e das menções saíram com a Conversa da Demanda na
 * issue #1386 (ADR 0077).
 */

import { describe, expect, it } from "vitest";

import { blocosDoTextoSimples, colunasDoQuadro, Demanda, iniciais, rotuloDaEtapa, textoDaAbertura } from "./demandas";

describe("As colunas do Quadro (issue #1642, ADR 0090)", () => {
  // Meio-dia de 12/11 em Brasília.
  const HOJE = new Date("2026-11-12T15:00:00Z");

  function d(id: string, extra: Partial<Demanda> = {}): Demanda {
    return { id, titulo: `Pedido ${id}`, criado_em: "2026-11-01T13:00:00Z", ...extra };
  }

  const ids = (demandas: Demanda[]) => demandas.map((x) => x.id);
  const coluna = (colunas: ReturnType<typeof colunasDoQuadro>, etapa: string) => {
    const achada = colunas.find((c) => c.etapa === etapa);
    if (!achada) throw new Error(`sem a coluna ${etapa}`);
    return achada;
  };

  it("são cinco, na ordem do fluxo, com o nome da Etapa, e cada Etapa cai na sua", () => {
    const colunas = colunasDoQuadro(
      [
        d("reg", { etapa: "registrada" }),
        d("ana", { etapa: "em_analise" }),
        d("pla", { etapa: "planejada" }),
        d("dev", { etapa: "em_desenvolvimento" }),
        d("ent", { etapa: "entregue", fechada_em: "2026-11-10T12:00:00Z" }),
      ],
      false,
      HOJE,
    );

    expect(colunas.map((c) => [c.etapa, c.rotulo])).toEqual([
      ["registrada", "Registrada"],
      ["em_analise", "Em análise"],
      ["planejada", "Planejada"],
      ["em_desenvolvimento", "Em desenvolvimento"],
      ["entregue", "Entregue"],
    ]);
    expect(colunas.map((c) => ids(c.cards))).toEqual([["reg"], ["ana"], ["pla"], ["dev"], ["ent"]]);
    expect(colunas.map((c) => c.contagem)).toEqual([1, 1, 1, 1, 1]);
  });

  it("a Demanda sem Etapa fica em Registrada", () => {
    const colunas = colunasDoQuadro([d("sem"), d("reg", { etapa: "registrada" })], false, HOJE);

    expect(ids(coluna(colunas, "registrada").cards)).toEqual(["sem", "reg"]);
  });

  it("Entregue junta Entregue e Em produção", () => {
    const colunas = colunasDoQuadro(
      [
        d("ent", { etapa: "entregue", fechada_em: "2026-11-10T12:00:00Z" }),
        d("prod", { etapa: "em_producao", versao: "v0.260.0", em_producao_em: "2026-11-11T12:00:00Z" }),
      ],
      false,
      HOJE,
    );

    expect(ids(coluna(colunas, "entregue").cards)).toEqual(["ent", "prod"]);
    expect(coluna(colunas, "entregue").contagem).toBe(2);
    expect(colunas.map((c) => c.etapa)).not.toContain("em_producao");
  });

  it("corta pelos 30 dias do calendário do hospital, pela entrada Em produção", () => {
    const colunas = colunasDoQuadro(
      [
        // 13/10 é há 30 dias: fica.
        d("trinta", { etapa: "em_producao", em_producao_em: "2026-10-13T12:00:00Z" }),
        // 02h de 13/10 em Greenwich ainda é 12/10 em Brasília, há 31 dias: sai.
        d("virada", { etapa: "em_producao", em_producao_em: "2026-10-13T02:00:00Z" }),
        // A entrada Em produção manda, mesmo com a entrega recente.
        d("velha", {
          etapa: "em_producao",
          fechada_em: "2026-11-10T12:00:00Z",
          em_producao_em: "2026-09-01T12:00:00Z",
        }),
      ],
      false,
      HOJE,
    );

    expect(ids(coluna(colunas, "entregue").cards)).toEqual(["trinta"]);
    expect(coluna(colunas, "entregue").contagem).toBe(1);
  });

  it("sem a entrada Em produção, corta pela entrega; sem data nenhuma, fica", () => {
    const colunas = colunasDoQuadro(
      [
        d("recente", { etapa: "entregue", fechada_em: "2026-11-01T12:00:00Z" }),
        d("antiga", { etapa: "entregue", fechada_em: "2026-10-01T12:00:00Z" }),
        d("sem-data", { etapa: "entregue" }),
      ],
      false,
      HOJE,
    );

    expect(ids(coluna(colunas, "entregue").cards)).toEqual(["recente", "sem-data"]);
  });

  it("Entregue mostra no máximo 8, os mais novos, e conta o total", () => {
    const entregues = Array.from({ length: 10 }, (_, i) =>
      d(`e${i + 1}`, {
        etapa: "entregue",
        fechada_em: "2026-11-10T12:00:00Z",
        criado_em: `2026-11-${String(i + 1).padStart(2, "0")}T12:00:00Z`,
      }),
    );

    const entregue = coluna(colunasDoQuadro(entregues, false, HOJE), "entregue");

    expect(ids(entregue.cards)).toEqual(["e10", "e9", "e8", "e7", "e6", "e5", "e4", "e3"]);
    expect(entregue.contagem).toBe(10);
    expect(entregue.deFora).toBe(2);
  });

  it("cada coluna vem com a mais nova primeiro pela abertura", () => {
    const colunas = colunasDoQuadro(
      [
        d("antiga", { etapa: "planejada", criado_em: "2026-10-01T12:00:00Z" }),
        d("nova", { etapa: "planejada", criado_em: "2026-11-11T12:00:00Z" }),
        d("meio", { etapa: "planejada", criado_em: "2026-10-20T12:00:00Z" }),
      ],
      false,
      HOJE,
    );

    expect(ids(coluna(colunas, "planejada").cards)).toEqual(["nova", "meio", "antiga"]);
    expect(coluna(colunas, "planejada").deFora).toBe(0);
  });

  it("Não será feita fica fora sem o interruptor, e vira a sexta coluna, no fim, com ele", () => {
    const demandas = [d("nao", { etapa: "nao_sera_feita" }), d("reg", { etapa: "registrada" })];

    const sem = colunasDoQuadro(demandas, false, HOJE);
    expect(sem.map((c) => c.etapa)).not.toContain("nao_sera_feita");
    expect(sem.flatMap((c) => ids(c.cards))).toEqual(["reg"]);

    const com = colunasDoQuadro(demandas, true, HOJE);
    expect(com.map((c) => c.etapa)).toEqual([
      "registrada",
      "em_analise",
      "planejada",
      "em_desenvolvimento",
      "entregue",
      "nao_sera_feita",
    ]);
    expect(com[5].rotulo).toBe("Não será feita");
    expect(ids(com[5].cards)).toEqual(["nao"]);
  });
});

describe("A data de abertura do card (issues #1578 e #1580)", () => {
  const AGORA = new Date("2026-11-11T15:00:00Z");

  it("conta os dias pelo calendário do hospital, com a hora de Brasília", () => {
    expect(textoDaAbertura("2026-11-01T13:00:00Z", AGORA)).toBe("Aberto em 01/11 às 10:00, há 10 dias");
  });

  it("hoje e ontem têm nome, e também a hora", () => {
    expect(textoDaAbertura("2026-11-11T12:05:00Z", AGORA)).toBe("Aberto hoje às 09:05");
    expect(textoDaAbertura("2026-11-10T17:32:00Z", AGORA)).toBe("Aberto ontem às 14:32");
  });

  it("a virada do dia e a hora são as de Brasília, e não as de Greenwich", () => {
    // 01h30 em Greenwich no dia 11 ainda é 22h30 do dia 10 em Brasília.
    expect(textoDaAbertura("2026-11-11T01:30:00Z", AGORA)).toBe("Aberto ontem às 22:30");
  });

  it("sem data, ou com data inválida, não escreve nada", () => {
    expect(textoDaAbertura(null, AGORA)).toBe("");
    expect(textoDaAbertura("ontem", AGORA)).toBe("");
  });
});

describe("As iniciais de quem pediu e de quem cuida (issue #1578)", () => {
  it("são a primeira letra do primeiro e do último nome", () => {
    expect(iniciais("Felipe Malafaia")).toBe("FM");
    expect(iniciais("Ana de Souza Lima")).toBe("AL");
  });

  it("nome único vira uma letra, e espaço sobrando não conta", () => {
    expect(iniciais("  pedro  ")).toBe("P");
    expect(iniciais("")).toBe("");
  });
});

describe("O rótulo da Etapa no card (issue #1578)", () => {
  it("é o selo sem a contagem de partes, que o card mostra na barra", () => {
    expect(
      rotuloDaEtapa({ id: "d", titulo: "t", etapa: "em_desenvolvimento", partes_entregues: 2, partes_total: 5 }),
    ).toBe("Em desenvolvimento");
    expect(rotuloDaEtapa({ id: "d", titulo: "t", etapa: "em_producao", versao: "v0.223.0" })).toBe(
      "Em produção desde v0.223.0",
    );
  });

  it("a conversa sem card é Registrada", () => {
    expect(rotuloDaEtapa({ id: "d", titulo: "t", etapa: "registrada" })).toBe("Registrada");
    expect(rotuloDaEtapa({ id: "d", titulo: "t" })).toBe("Registrada");
  });
});

describe("O Markdown simples do O que muda", () => {
  it("separa parágrafo de lista", () => {
    const blocos = blocosDoTextoSimples("O card ganha a seção.\n\n- Vem do planejamento.\n- Ninguém reescreve.");

    expect(blocos.map((b) => b.lista)).toEqual([false, true]);
    expect(blocos[1].linhas.map((linha) => linha[0].texto)).toEqual(["Vem do planejamento.", "Ninguém reescreve."]);
  });

  it("linha em branco fecha o parágrafo", () => {
    // Sem isso os dois parágrafos virariam um só, e o texto sairia grudado.
    const blocos = blocosDoTextoSimples("Primeiro.\n\nSegundo.");

    expect(blocos).toHaveLength(2);
    expect(blocos.every((b) => b.linhas.length === 1)).toBe(true);
  });

  it("o negrito vira pedaço forte e o asterisco some", () => {
    const pedacos = blocosDoTextoSimples("**O que muda:** o card ganha a seção.")[0].linhas[0];

    expect(pedacos).toEqual([
      { texto: "O que muda:", forte: true },
      { texto: " o card ganha a seção.", forte: false },
    ]);
  });

  it("link do Markdown continua sendo texto", () => {
    // Nada que venha do GitHub vira elemento clicável na tela do diretor: o que
    // o parser não conhece fica como está, e não como um link.
    const pedacos = blocosDoTextoSimples("Veja [a issue](https://exemplo).")[0].linhas[0];

    expect(pedacos).toEqual([{ texto: "Veja [a issue](https://exemplo).", forte: false }]);
  });

  it("texto vazio ou nulo não vira bloco nenhum", () => {
    expect(blocosDoTextoSimples(null)).toEqual([]);
    expect(blocosDoTextoSimples("   \n  ")).toEqual([]);
  });
});
