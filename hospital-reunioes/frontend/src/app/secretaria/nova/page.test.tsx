/**
 * @vitest-environment jsdom
 */

/**
 * A tela Nova reunião da Secretária pré-preenchida pelo link (issue #761).
 *
 * O Calendário deixou de abrir o modal para a Secretária e a traz para cá com a
 * data e a hora do dia ou do slot clicado. A tela lê as duas da URL, ignora
 * valor inválido e não quebra o `?edit=`, que carrega a reunião do banco.
 */

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import NovaReuniaoSecretaria from "./page";

const url = vi.hoisted(() => ({ params: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useSearchParams: () => url.params,
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) },
  }),
}));

const REUNIAO_EXISTENTE = {
  id_reuniao: "RD_1",
  titulo: "Diretoria de outubro",
  data: "2026-10-15",
  hora_inicio: "09:00:00",
  hora_fim: null,
  tipo: "Diretoria",
  objetivo: null,
  facilitador_id: "P_FACIL",
  participantes_programada: [],
};

function montar(query: string) {
  url.params = new URLSearchParams(query);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (endereco: string) => {
      const corpo = endereco.startsWith("/api/reunioes/") ? REUNIAO_EXISTENTE : [];
      return { ok: true, status: 200, json: async () => corpo } as unknown as Response;
    }),
  );
  return render(
    <ToastProvider>
      <NovaReuniaoSecretaria />
    </ToastProvider>,
  );
}

function campoData() {
  return screen.getByLabelText(/^Data/) as HTMLInputElement;
}

function campoInicio() {
  return screen.getByLabelText(/^Início/) as HTMLInputElement;
}

beforeEach(() => {
  url.params = new URLSearchParams();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Nova reunião pré-preenchida pelo link", () => {
  it("abre com a data e a hora que vieram do Calendário", async () => {
    montar("data=2026-11-20&hora=14:30");

    await waitFor(() => expect(campoData().value).toBe("2026-11-20"));
    expect(campoInicio().value).toBe("14:30");
  });

  it("só com a data, o início fica vazio", async () => {
    montar("data=2026-11-20");

    await waitFor(() => expect(campoData().value).toBe("2026-11-20"));
    expect(campoInicio().value).toBe("");
  });

  it.each([
    ["data=20/11/2026&hora=14:30", "", "14:30"],
    ["data=2026-13-45&hora=14:30", "", "14:30"],
    ["data=2026-11-20&hora=25:00", "2026-11-20", ""],
    ["data=2026-11-20&hora=abc", "2026-11-20", ""],
  ])("ignora valor inválido na URL (%s)", async (query, dataEsperada, horaEsperada) => {
    montar(query);

    expect(campoData().value).toBe(dataEsperada);
    expect(campoInicio().value).toBe(horaEsperada);
  });

  it("o ?edit= continua carregando a reunião do banco", async () => {
    montar("edit=RD_1");

    await waitFor(() => expect(campoData().value).toBe("2026-10-15"));
    expect(campoInicio().value).toBe("09:00");
    expect((screen.getByDisplayValue("Diretoria de outubro") as HTMLInputElement).value).toBe("Diretoria de outubro");
  });
});
