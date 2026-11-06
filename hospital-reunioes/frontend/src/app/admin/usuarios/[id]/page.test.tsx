/**
 * @vitest-environment jsdom
 */

/**
 * O detalhe do usuário na Administração e a Caixa alta (issue #1455, ADR 0080).
 *
 * O título da página é o nome da pessoa, que vem do cadastro: ele aparece como
 * foi escrito, e a etiqueta Super Admin ao lado segue a regra dos textos curtos.
 */

import { Suspense } from "react";
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AdminUsuarioDetalhe } from "@/components/admin/types";
import { ToastProvider } from "@/components/ui/Toast";
import { caixaDoDado } from "@/lib/testes/caixaDoDado";

vi.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({ token: "token-de-teste", loading: false }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

import AdminUsuarioDetailPage from "./page";

const DETALHE: AdminUsuarioDetalhe = {
  usuario: {
    id: "u-1",
    nome_completo: "Ana de Souza Lima",
    email: "ana@example.com",
    cargo: "Enfermeira",
    setor: "CTI Adulto",
    role: "facilitador",
    ativo: true,
    is_externo: false,
    is_super_admin: true,
    access_profile: "padrao",
  } as AdminUsuarioDetalhe["usuario"],
  audit_logs: [],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Caixa alta no detalhe do usuário", () => {
  it("o nome da pessoa no título aparece como foi escrito", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify(DETALHE), { status: 200 })),
    );

    const params = Promise.resolve({ id: "u-1" });
    await act(async () => {
      render(
        <ToastProvider>
          <Suspense fallback={null}>
            <AdminUsuarioDetailPage params={params} />
          </Suspense>
        </ToastProvider>,
      );
    });

    const titulo = await screen.findByRole("heading", { level: 1 });
    expect(caixaDoDado(screen.getByText("Ana de Souza Lima"))).toBe("normal-case");
    expect(titulo.textContent).toContain("Super Admin");
  });
});
