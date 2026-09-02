/**
 * @vitest-environment jsdom
 */

/**
 * O 406 que sujava o console (issue #492, PRD #471).
 *
 * A tela inicial lia a tabela `participantes` direto no PostgREST, do
 * navegador, com a chave anônima. Só que a `participantes` tem RLS
 * default-deny desde a migration 009 e nunca ganhou policy de SELECT: a
 * leitura do navegador volta SEMPRE com zero linha. Com `.single()`, o
 * postgrest-js manda `Accept: application/vnd.pgrst.object+json` e zero linha
 * vira `406 Not Acceptable` (PGRST116) gritando no console de toda sessão,
 * inclusive enquanto se navega pela Ouvidoria, que entra por aqui.
 *
 * O papel do usuário vem do backend (`GET /api/participantes/me`, o
 * `useCurrentParticipante`), que lê com service_role. Esta suíte trava a
 * invariante: a tela inicial não fala com o PostgREST. Sem ela, alguém
 * reintroduz a leitura direta e o 406 volta calado.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "./page";

// Toda tabela que a tela pedir ao PostgREST fica registrada aqui.
const postgrest = vi.hoisted(() => ({ tabelasLidas: [] as string[] }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/participantes", () => ({
  fetchParticipantesAtivos: async () => [],
}));

// Os gráficos não são o assunto desta suíte, e o recharts não roda em jsdom.
vi.mock("@/components/dashboard/KpiCards", () => ({ default: () => null }));
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
    // Réplica do PostgREST com a tabela em default-deny: zero linha, e o
    // `.single()` devolvendo o 406 que aparecia no console.
    from: (tabela: string) => {
      postgrest.tabelasLidas.push(tabela);
      const resposta = {
        data: null,
        error: {
          code: "PGRST116",
          details: "The result contains 0 rows",
          hint: null,
          message: "JSON object requested, multiple (or no) rows returned",
        },
        status: 406,
        statusText: "Not Acceptable",
      };
      const cadeia = {
        select: () => cadeia,
        eq: () => cadeia,
        single: () => cadeia,
        maybeSingle: () => cadeia,
        then: (cb: (r: typeof resposta) => unknown) => Promise.resolve(cb(resposta)),
      };
      return cadeia;
    },
  }),
}));

beforeEach(() => {
  postgrest.tabelasLidas = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response)
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("tela inicial e o PostgREST", () => {
  it("não lê tabela nenhuma direto do navegador (o 406 da issue #492)", async () => {
    render(<DashboardPage />);

    // Espera a inicialização terminar: sem isto, a asserção passaria só por
    // chegar antes da consulta.
    await waitFor(() => {
      expect(vi.mocked(fetch)).toHaveBeenCalled();
    });

    expect(postgrest.tabelasLidas).toEqual([]);
  });

  it("monta a tela inteira mesmo com o PostgREST devolvendo zero linha", async () => {
    render(<DashboardPage />);

    // O `from` mockado responde zero linha em qualquer tabela, que é o que a
    // chave anônima recebe de uma tabela em default-deny. A tela precisa
    // chegar ao fim da inicialização assim mesmo, porque não depende dela.
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Olá, marta" })).toBeTruthy();
    });
    expect(postgrest.tabelasLidas).toEqual([]);
  });
});
