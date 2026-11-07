/**
 * @vitest-environment jsdom
 */

/**
 * O Resolver do participante externo e a Caixa alta (issue #1455, ADR 0080).
 *
 * As abas e os botões herdam a caixa alta da regra base. O que vem dentro
 * deles e não é texto curto fica corrido: a ajuda de cada aba e a pessoa que a
 * busca devolve, com nome e e-mail como estão no cadastro.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ToastProvider } from "@/components/ui/Toast";
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

import { ResolverExternoModal } from "./ResolverExternoModal";
import type { AdminUsuario } from "./types";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "token-de-teste", loading: false }),
}));

function pessoa(id: string, nome: string, extra: Partial<AdminUsuario> = {}): AdminUsuario {
  return {
    id,
    nome_completo: nome,
    email: `${id}@example.com`,
    ativo: true,
    is_externo: false,
    is_super_admin: false,
    access_profile: "regular",
    ...extra,
  };
}

const EXTERNO = pessoa("e-1", "João da Silva", { is_externo: true });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function abrir() {
  render(
    <ToastProvider>
      <ResolverExternoModal externo={EXTERNO} onClose={() => undefined} onResolved={() => undefined} />
    </ToastProvider>,
  );
}

describe("Caixa alta no Resolver", () => {
  it("a ajuda de cada aba fica corrida", () => {
    abrir();

    expect(caixaDoDado(screen.getByText("É a mesma pessoa que outro interno já cadastrado"))).toBe("normal-case");
  });

  it("a pessoa achada na busca aparece como está no cadastro", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([pessoa("i-1", "Maria de Souza")]), { status: 200 })),
    );
    abrir();

    fireEvent.change(screen.getByPlaceholderText(/Digite nome ou email/), { target: { value: "Maria" } });

    const achada = await screen.findByRole("button", { name: /Maria de Souza/ });
    expect(caixaDoDado(achada)).toBe("normal-case");
  });
});
