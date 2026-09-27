/**
 * @vitest-environment jsdom
 */

/**
 * O Calendário leva a Secretária para a tela Nova reunião (issue #761).
 *
 * O modal "Agendar Reunião" não pergunta quem facilita, e o backend fazia de
 * quem agenda o facilitador: a Secretária criava reunião que ela mesma não
 * conduz. Para ela, todo gesto de CRIAR (o botão, o clique no dia e o clique no
 * slot da semana) vai para `/secretaria/nova` com a data e a hora. Para os
 * outros perfis o modal continua, e ver os eventos não muda para ninguém.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";

import CalendarioPage from "./page";

const perfil = vi.hoisted(() => ({ participante: null as Record<string, unknown> | null }));
const navegacao = vi.hoisted(() => ({ empurrou: [] as string[] }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: (url: string) => navegacao.empurrou.push(url), replace: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({ participante: perfil.participante, loading: false, error: null }),
}));

vi.mock("@/hooks/useFacilitadores", () => ({
  useFacilitadores: () => ({ facilitadores: [], loading: false }),
}));

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({
    auth: { getSession: async () => ({ data: { session: { access_token: "tok" } } }) },
  }),
}));

const SECRETARIA = { id: "P_SECRE", nome_completo: "Secretária", email: "s@hsm.com", access_profile: "secretaria" };
const FACILITADOR = { id: "P_FACIL", nome_completo: "Facilitador", email: "f@hsm.com", access_profile: "regular" };

// Terça, 10 de novembro de 2026: a semana vai de 8 a 14.
const HOJE = new Date(2026, 10, 10, 8, 0, 0);

function montar() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => [] }) as unknown as Response),
  );
  return render(
    <ToastProvider>
      <CalendarioPage />
    </ToastProvider>,
  );
}

function modalAberto() {
  return screen.queryByRole("heading", { name: "Agendar Reunião" }) !== null;
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(HOJE);
  navegacao.empurrou = [];
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("Secretária no Calendário", () => {
  beforeEach(() => {
    perfil.participante = SECRETARIA;
  });

  it("o botão Agendar Reunião leva para a Nova reunião com a data de hoje", async () => {
    montar();

    fireEvent.click(screen.getByRole("button", { name: /Agendar Reunião/ }));

    expect(navegacao.empurrou).toEqual(["/secretaria/nova?data=2026-11-10"]);
    expect(modalAberto()).toBe(false);
  });

  it("o clique no dia leva para a Nova reunião com aquela data", async () => {
    montar();

    fireEvent.click(screen.getByTestId("dia-2026-11-20"));

    expect(navegacao.empurrou).toEqual(["/secretaria/nova?data=2026-11-20"]);
    expect(modalAberto()).toBe(false);
  });

  it("o clique no slot da semana leva a data e a hora", async () => {
    montar();
    fireEvent.click(screen.getByRole("button", { name: /Semanal/ }));

    fireEvent.click(await screen.findByTestId("slot-2026-11-12-14:00"));

    expect(navegacao.empurrou).toEqual(["/secretaria/nova?data=2026-11-12&hora=14%3A00"]);
    expect(modalAberto()).toBe(false);
  });
});

describe("Outros perfis no Calendário", () => {
  beforeEach(() => {
    perfil.participante = FACILITADOR;
  });

  it("o botão abre o modal como sempre", async () => {
    montar();

    fireEvent.click(screen.getByRole("button", { name: /Agendar Reunião/ }));

    await waitFor(() => expect(modalAberto()).toBe(true));
    expect(navegacao.empurrou).toEqual([]);
  });

  it("o clique no dia abre o modal como sempre", async () => {
    montar();

    fireEvent.click(screen.getByTestId("dia-2026-11-20"));

    await waitFor(() => expect(modalAberto()).toBe(true));
    expect(navegacao.empurrou).toEqual([]);
  });

  it("o clique no slot abre o modal como sempre", async () => {
    montar();
    fireEvent.click(screen.getByRole("button", { name: /Semanal/ }));

    fireEvent.click(await screen.findByTestId("slot-2026-11-12-14:00"));

    await waitFor(() => expect(modalAberto()).toBe(true));
    expect(navegacao.empurrou).toEqual([]);
  });
});
