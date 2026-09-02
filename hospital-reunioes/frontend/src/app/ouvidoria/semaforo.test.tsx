/**
 * @vitest-environment jsdom
 */

/**
 * O semáforo de prazo na fila da Ouvidoria (issue #488, PRD #471, RN-58).
 *
 * A régua de quem acende qual cor vive em `lib/ouvidoria/prazo` e tem suíte
 * própria. Este arquivo trava a FIAÇÃO: que a linha pinta o que a régua diz.
 * Sem ele, alguém deixaria o "vence hoje" caindo no ramo neutro do `PrazoCell`
 * e a suíte da régua seguiria verde, com a tela mostrando cinza no caso que
 * precisa de resposta ainda hoje.
 */

import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OuvidoriaPage from "./page";

/** Uma terça qualquer, às 10h de Brasília. */
const AGORA = new Date("2026-08-25T13:00:00Z");

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
      perfil_ouvidoria: "ouvidor",
    },
    loading: false,
  }),
}));

const BASE = {
  data_abertura: "2026-08-20",
  prazo_resposta: "2026-09-30",
  status: "aguardando_area",
  tipo_manifestacao: "reclamacao",
  sigilo_reforcado: false,
  categoria: "Atendimento",
  setor: "Recepção",
  resumo: "Paciente relata espera acima de duas horas.",
  conversa_id: "",
  gravidade: "media",
  prazo_estourado: false,
  minutos_uteis_restantes: 180,
  tem_novidade: false,
};

const INDICE = {
  protocolos: [
    {
      ...BASE,
      id: "uuid-1",
      numero: 1,
      protocolo: "2026-0001",
      prazo_area_em: "2026-08-24T20:00:00+00:00",
      prazo_estourado: true,
      rotulo_prazo: "vencido há 1 dia útil",
      minutos_uteis_restantes: 0,
    },
    {
      ...BASE,
      id: "uuid-2",
      numero: 2,
      protocolo: "2026-0002",
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 7 horas úteis",
    },
    {
      ...BASE,
      id: "uuid-3",
      numero: 3,
      protocolo: "2026-0003",
      prazo_area_em: "2026-08-26T20:00:00+00:00",
      rotulo_prazo: "vence em 1 dia útil",
      minutos_uteis_restantes: 540,
    },
    {
      ...BASE,
      id: "uuid-4",
      numero: 4,
      protocolo: "2026-0004",
      prazo_area_em: "2026-08-28T20:00:00+00:00",
      rotulo_prazo: "vence em 3 dias úteis",
      minutos_uteis_restantes: 3 * 540,
    },
    {
      ...BASE,
      id: "uuid-5",
      numero: 5,
      protocolo: "2026-0005",
      status: "encerrado",
      prazo_area_em: "2026-08-25T20:00:00+00:00",
      rotulo_prazo: "vence em 7 horas úteis",
    },
  ],
};

/** A linha inteira do protocolo, que é onde a cor de fundo do caso urgente mora. */
async function linhaDe(protocolo: string): Promise<HTMLElement> {
  const celula = await screen.findByText(protocolo);
  const linha = celula.closest("tr");
  if (!linha) throw new Error(`sem linha para o protocolo ${protocolo}`);
  return linha;
}

describe("o semáforo de prazo da fila (issue #488, RN-58)", () => {
  beforeEach(() => {
    // `shouldAdvanceTime` mantém o relógio andando sob o tempo falso: sem ele
    // o `findBy` do testing-library espera para sempre um timer que nunca corre.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.setSystemTime(AGORA);
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => INDICE }) as Response)
    );
    render(<OuvidoriaPage />);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("caso vencido aparece em vermelho, com o carimbo de estourado", async () => {
    const linha = await linhaDe("2026-0001");

    expect(within(linha).getByText("Estourado")).toBeTruthy();
    expect(within(linha).getByText(/vencido há 1 dia útil/).className).toContain("text-red");
    expect(linha.className).toContain("bg-red-50");
  });

  it("caso que vence hoje aparece no mesmo vermelho, dito com outro carimbo", async () => {
    const linha = await linhaDe("2026-0002");

    expect(within(linha).getByText("Vence hoje")).toBeTruthy();
    expect(within(linha).queryByText("Estourado")).toBeNull();
    expect(within(linha).getByText(/vence em 7 horas úteis/).className).toContain("text-red");
    expect(linha.className).toContain("bg-red-50");
  });

  it("caso com um dia útil de folga aparece em âmbar, sem carimbo e sem fundo", async () => {
    const linha = await linhaDe("2026-0003");

    expect(within(linha).getByText(/vence em 1 dia útil/).className).toContain("text-amber");
    expect(within(linha).queryByText("Vence hoje")).toBeNull();
    expect(linha.className || "").not.toContain("bg-red-50");
  });

  it("caso com folga acima de um dia útil fica neutro, sem cor de alerta", async () => {
    const linha = await linhaDe("2026-0004");
    const prazo = within(linha).getByText(/vence em 3 dias úteis/).className;

    expect(prazo).not.toContain("text-red");
    expect(prazo).not.toContain("text-amber");
  });

  it("caso encerrado que venceria hoje segue sem semáforo: o relógio parou", async () => {
    const linha = await linhaDe("2026-0005");

    expect(within(linha).queryByText("Vence hoje")).toBeNull();
    expect(within(linha).queryByText("Estourado")).toBeNull();
    expect(linha.className || "").not.toContain("bg-red-50");
  });

  it("o contador do topo conta só o que rompeu, e não o que vence hoje", async () => {
    expect(await screen.findByText("1 com prazo estourado")).toBeTruthy();
  });
});
