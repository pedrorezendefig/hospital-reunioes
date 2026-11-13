/**
 * @vitest-environment jsdom
 */

/**
 * A guarda do layout do `/admin` sem sessão (issue #1587, PRD #1584).
 *
 * O middleware é a primeira porta; esta é a segunda, para quando a sessão cai
 * entre um e outro. Ela troca o `redirect("/login")` do servidor pelo mesmo
 * encaminhador da Ouvidoria, que lê o endereço no navegador e deixa o link de
 * um pedido da aba Tecnologia voltar a ele depois do login.
 *
 * O que não pode afrouxar: sem sessão, nada do admin chega ao navegador. O
 * layout devolve o encaminhador no LUGAR dos filhos.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getUser = vi.fn();
const getSession = vi.fn();
const redirect = vi.fn();
const replace = vi.fn();

vi.mock("next/navigation", () => ({
  redirect: (destino: string) => redirect(destino),
  useRouter: () => ({ replace }),
}));

vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({ auth: { getUser, getSession } }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import AdminLayout from "./layout";

const SEGREDO = "a lista de pedidos da Tecnologia";

async function montarEm(url: string) {
  window.history.replaceState({}, "", url);
  render(await AdminLayout({ children: <p>{SEGREDO}</p> }));
}

beforeEach(() => {
  getUser.mockReset();
  getSession.mockReset();
  redirect.mockReset();
  replace.mockReset();
  vi.unstubAllGlobals();
});

afterEach(() => {
  cleanup();
});

describe("o admin sem sessão", () => {
  beforeEach(() => {
    getUser.mockResolvedValue({ data: { user: null } });
  });

  it("não entrega o conteúdo e leva o link do pedido ao login com o retorno", async () => {
    await montarEm("/admin/tecnologia?demanda=8f2c");

    expect(screen.queryByText(SEGREDO)).toBeNull();
    expect(replace).toHaveBeenCalledWith(
      "/login?redirect=%2Fadmin%2Ftecnologia%3Fdemanda%3D8f2c"
    );
  });

  it("manda o resto do admin para o login sem retorno", async () => {
    await montarEm("/admin/usuarios");

    expect(screen.queryByText(SEGREDO)).toBeNull();
    expect(replace).toHaveBeenCalledWith("/login");
  });
});

describe("o admin com sessão", () => {
  it("monta a área normalmente", async () => {
    // Controle positivo: uma guarda quebrada para o lado restritivo deixaria
    // os testes de cima verdes por motivo errado.
    getUser.mockResolvedValue({
      data: { user: { email: "diretor@hsm.test", user_metadata: { nome: "Ana" } } },
    });
    getSession.mockResolvedValue({ data: { session: { access_token: "t" } } });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, json: async () => ({ access_profile: "super_admin" }) }))
    );

    await montarEm("/admin/tecnologia");

    expect(screen.getByText(SEGREDO)).not.toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
