/**
 * @vitest-environment jsdom
 */

/**
 * A guarda da área da Ouvidoria, agora carregando o destino (issue #477).
 *
 * Duas coisas precisam continuar verdadeiras ao mesmo tempo, e é a tensão entre
 * elas que este arquivo fixa:
 *
 * * sem sessão, nada da tela protegida chega ao navegador. O layout devolve o
 *   encaminhador no LUGAR dos filhos, e não junto deles.
 * * com sessão, a área segue montando normalmente.
 *
 * O primeiro caso é o que impede a troca do `redirect("/login")` do servidor
 * pelo encaminhador de virar um afrouxamento silencioso da guarda.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getUser = vi.fn();
const redirect = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => redirect(destino),
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({ auth: { getUser } }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import OuvidoriaLayout from "./layout";

const SEGREDO = "a fila de manifestações";

async function montar() {
  render(await OuvidoriaLayout({ children: <p>{SEGREDO}</p> }));
}

beforeEach(() => {
  getUser.mockReset();
  redirect.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("a área da Ouvidoria sem sessão", () => {
  it("não entrega o conteúdo protegido, entrega o encaminhamento para o login", async () => {
    getUser.mockResolvedValue({ data: { user: null } });

    await montar();

    expect(screen.queryByText(SEGREDO)).toBeNull();
    expect(screen.getByRole("link", { name: /login/i }).getAttribute("href")).toBe("/login");
  });
});

describe("a área da Ouvidoria com sessão", () => {
  it("monta a área normalmente", async () => {
    // Controle positivo: sem ele, uma guarda quebrada para o lado restritivo
    // deixaria o teste de cima verde por motivo errado.
    getUser.mockResolvedValue({
      data: { user: { email: "ouvidor@hsm.test", user_metadata: { nome: "Ana" } } },
    });

    await montar();

    expect(screen.getByText(SEGREDO)).not.toBeNull();
  });
});
