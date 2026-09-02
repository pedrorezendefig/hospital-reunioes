/**
 * @vitest-environment jsdom
 */

/**
 * O marcador de novidade na linha da fila (issue #484, PRD #470, RN-68).
 *
 * O ouvidor abria caso a caso para descobrir o que tinha mexido. A linha passa
 * a dizer isso sozinha: ponto sólido na cor de acento à esquerda do protocolo,
 * e resumo em peso médio. Nada pisca, o sinal fica até o caso ser aberto.
 *
 * O ponto é desenho, e desenho some do teste. Por isso ele anda com um rótulo
 * em `sr-only`: é o que o leitor de tela anuncia e o que esta suíte pega. Sem
 * o rótulo, alguém trocaria o ponto por nada e a suíte seguiria verde, com a
 * lista muda para quem não enxerga a cor.
 *
 * O layout final da linha chega no PRD da lista nova (#471). Aqui a
 * apresentação é a mais simples que cumpre a regra.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "./page";

const sessao = vi.hoisted(() => ({ perfilOuvidoria: null as string | null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({ data: { session: { access_token: "token-de-teste" } } }),
    },
  }),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: {
      id: "p1",
      nome_completo: "Marta Ouvidora",
      email: "marta@hsm",
      perfil_ouvidoria: sessao.perfilOuvidoria,
    },
    loading: false,
  }),
}));

const RESUMO_SETE = "Paciente relata espera acima de duas horas na recepção.";
const RESUMO_OITO = "Acompanhante relata falta de cadeiras na sala de espera.";

function linha(numero: number, resumo: string, temNovidade: boolean) {
  return {
    id: `uuid-${numero}`,
    numero,
    protocolo: `2026-${String(numero).padStart(4, "0")}`,
    data_abertura: "2026-08-14",
    prazo_resposta: "2026-08-21",
    status: "aguardando_area",
    tipo_manifestacao: "reclamacao",
    sigilo_reforcado: false,
    categoria: "Demora",
    setor: "Recepcao",
    resumo,
    conversa_id: "",
    gravidade: null,
    prazo_area_em: null,
    prazo_estourado: false,
    rotulo_prazo: "",
    minutos_uteis_restantes: null,
    tem_novidade: temNovidade,
  };
}

function montar(protocolos: ReturnType<typeof linha>[], degradado: string[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({ ok: true, status: 200, json: async () => ({ protocolos, degradado }) }) as Response
    )
  );
  render(<OuvidoriaPage />);
}

describe("o ponto de novidade na fila (issue #484)", () => {
  beforeEach(() => {
    sessao.perfilOuvidoria = "ouvidor";
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("a linha com novidade anuncia a movimentação nova", async () => {
    montar([linha(7, RESUMO_SETE, true)]);

    expect(await screen.findByText("Movimentação nova")).toBeTruthy();
  });

  it("a linha sem novidade não anuncia nada", async () => {
    montar([linha(7, RESUMO_SETE, false)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByText("Movimentação nova")).toBeNull();
  });

  it("o ponto é da linha que tem novidade, e não da lista inteira", async () => {
    montar([linha(7, RESUMO_SETE, false), linha(8, RESUMO_OITO, true)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.getAllByText("Movimentação nova")).toHaveLength(1);
  });

  it("o resumo do caso com novidade vem em peso médio, e o dos outros não", async () => {
    montar([linha(7, RESUMO_SETE, false), linha(8, RESUMO_OITO, true)]);

    const comNovidade = await screen.findByText(RESUMO_OITO);
    const semNovidade = screen.getByText(RESUMO_SETE);

    expect(comNovidade.className).toContain("font-medium");
    expect(semNovidade.className).not.toContain("font-medium");
  });

  it("o ponto sai na cor de acento, e não numa cor solta", async () => {
    montar([linha(7, RESUMO_SETE, true)]);

    const rotulo = await screen.findByText("Movimentação nova");
    const ponto = rotulo.parentElement?.querySelector("[aria-hidden='true']");

    expect(ponto?.className).toContain("bg-primary");
  });

  it("a trilha fora do ar é dita na tela, e não vira fila sem novidade", async () => {
    // Sem esta frase o ouvidor olha uma lista sem ponto nenhum e conclui que
    // nada mexeu, quando a verdade é que o servidor não conseguiu olhar.
    montar([linha(7, RESUMO_SETE, false)], ["movimentos"]);

    expect(await screen.findByText(/trilha de movimentos não pôde ser lida/i)).toBeTruthy();
  });

  it("carga sem degradação não mostra aviso nenhum", async () => {
    montar([linha(7, RESUMO_SETE, false)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByText(/não pôde ser lid/i)).toBeNull();
  });

  it("quem está fora da Ouvidoria não recebe novidade e não vê ponto nenhum", async () => {
    // O backend já desliga a flag para esse público (issue #484). A tela não
    // pode inventar o ponto a partir de outra coisa.
    sessao.perfilOuvidoria = null;
    montar([linha(7, RESUMO_SETE, false)]);

    expect(await screen.findByText("2026-0007")).toBeTruthy();
    expect(screen.queryByText("Movimentação nova")).toBeNull();
  });
});
