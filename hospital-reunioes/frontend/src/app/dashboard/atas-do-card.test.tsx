/**
 * @vitest-environment jsdom
 */

/**
 * Os cards "Atas Paradas" e "Aguardam Assinatura" abrem a lista (issue #1055).
 *
 * Antes, os dois cards levavam ao calendário, onde o facilitador não via quais
 * atas o número contava. Agora cada card abre um modal no próprio dashboard com
 * exatamente as atas da contagem, cada uma com link para a página da reunião.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./page";

const roteador = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => roteador,
}));

vi.mock("@/lib/participantes", () => ({
  fetchParticipantesAtivos: async () => [],
}));

// Os gráficos não são o assunto desta suíte, e o recharts não roda em jsdom.
vi.mock("@/components/dashboard/DashboardFilters", () => ({ default: () => null }));
vi.mock("@/components/dashboard/StatusPieChart", () => ({ default: () => null }));
vi.mock("@/components/dashboard/SetorBarChart", () => ({ default: () => null }));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: {
      getSession: async () => ({
        data: {
          session: {
            access_token: "token-de-teste",
            user: { id: "auth-user-1", email: "marta@hsm", user_metadata: {} },
          },
        },
      }),
      onAuthStateChange: () => ({
        data: { subscription: { unsubscribe: () => {} } },
      }),
    },
  }),
}));

const DIA = 24 * 60 * 60 * 1000;
const haDias = (n: number) => new Date(Date.now() - n * DIA).toISOString();

const REUNIOES = [
  {
    id_reuniao: "parada-1",
    data: "2026-09-20",
    tipo: "Gerencial",
    objetivo: "Fechar escala de outubro",
    status_ata: "AGUARDANDO_VALIDACAO",
    updated_at: haDias(10),
  },
  {
    id_reuniao: "recente-1",
    data: "2026-10-06",
    tipo: "Diretoria",
    objetivo: "Orçamento do trimestre",
    status_ata: "AGUARDANDO_VALIDACAO",
    updated_at: haDias(0),
  },
  {
    id_reuniao: "assinatura-1",
    data: "2026-09-30",
    tipo: "Mensal",
    objetivo: "Indicadores de setembro",
    status_ata: "AGUARDANDO_ASSINATURA",
    updated_at: haDias(5),
  },
];

beforeEach(() => {
  roteador.push.mockClear();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const corpo = url.startsWith("/api/reunioes")
        ? REUNIOES
        : url.startsWith("/api/pendencias/stats")
          ? {}
          : [];
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function linksDoModal(nome: string) {
  const modal = screen.getByRole("dialog", { name: nome });
  return within(modal)
    .queryAllByRole("link")
    .map((a) => a.getAttribute("href"));
}

async function abrirCard(id: string) {
  render(<DashboardPage />);
  const card = document.getElementById(id) as HTMLElement;
  // Espera o número do card chegar: abrir antes listaria nada por acaso.
  await waitFor(() => {
    expect(within(card).getByText("1")).toBeTruthy();
  });
  fireEvent.click(card);
}

describe("card Atas Paradas", () => {
  it("abre o modal com só a ata parada, e não a recente", async () => {
    await abrirCard("atas-paradas");

    expect(linksDoModal("Atas Paradas")).toEqual(["/reunioes/parada-1"]);
    const modal = screen.getByRole("dialog", { name: "Atas Paradas" });
    expect(within(modal).getByText("há 10 dias")).toBeTruthy();
    expect(roteador.push).not.toHaveBeenCalled();
  });
});

describe("card Aguardam Assinatura", () => {
  it("abre o modal com só a ata que aguarda assinatura", async () => {
    await abrirCard("aguardam-assinatura");

    expect(linksDoModal("Aguardam Assinatura")).toEqual(["/reunioes/assinatura-1"]);
    expect(roteador.push).not.toHaveBeenCalled();
  });
});
