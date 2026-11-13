/**
 * @vitest-environment jsdom
 */

/**
 * A rota do manual (issue #1718, ADR 0094, decisão 1): o item Manual leva a
 * `/manual`, e é aqui que ele abre. A página lê os Markdown de verdade em
 * `public/manual/`, então a página de exemplo que prova a casca tem que
 * aparecer; sem sessão, o layout manda para o login e nada do manual sai.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CurrentParticipante } from "@/hooks/useCurrentParticipante";

const getUser = vi.fn();
const redirect = vi.fn((destino: string) => {
  throw new Error(`redirect ${destino}`);
});

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => redirect(destino),
  usePathname: () => "/manual",
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({ auth: { getUser } }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

const sessao = vi.hoisted(() => ({
  participante: null as CurrentParticipante | null,
}));

vi.mock("@/hooks/useCurrentParticipante", () => ({
  useCurrentParticipante: () => ({
    participante: sessao.participante,
    loading: false,
    error: null,
  }),
}));

import ManualLayout from "./layout";
import ManualPage from "./page";

beforeEach(() => {
  getUser.mockReset();
  redirect.mockClear();
});

afterEach(() => {
  cleanup();
  sessao.participante = null;
});

describe("a rota /manual", () => {
  it("com sessão, abre o manual com a página de Reuniões e Pendências", async () => {
    getUser.mockResolvedValue({ data: { user: { email: "fulana@hsm", user_metadata: {} } } });
    sessao.participante = {
      id: "p1",
      nome_completo: "Fulana de Tal",
      email: "fulana@hsm",
      access_profile: "regular",
    };

    render(await ManualLayout({ children: await ManualPage() }));

    expect(screen.getByRole("heading", { level: 1, name: "Manual" })).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Aplicativo do Hospital" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Reuniões e Pendências" })).toBeTruthy();
  });

  it("sem sessão, vai para o login e o manual não sai", async () => {
    getUser.mockResolvedValue({ data: { user: null } });

    await expect(ManualLayout({ children: <p>o manual</p> })).rejects.toThrow("redirect /login");
    expect(redirect).toHaveBeenCalledWith("/login");
  });
});
