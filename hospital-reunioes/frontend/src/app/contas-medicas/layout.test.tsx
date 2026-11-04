/**
 * @vitest-environment jsdom
 */

/**
 * O layout da área /contas-medicas põe títulos e subtítulos em caixa alta, a
 * pedido do diretor (PR #1411). A regra vive num contêiner com variantes do
 * Tailwind que miram os h1, h2 e h3 descendentes; o que se trava aqui é que
 * cada título da página renderizada fica DENTRO desse contêiner, e não só que
 * a classe existe solta em algum lugar.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/contas-medicas/guard", () => ({
  requireContasMedicasAccess: async () => ({
    user: { email: "faturista@hsm.test", user_metadata: { nome: "Ana" } },
  }),
}));

vi.mock("@/components/layout/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

import ContasMedicasLayout from "./layout";

afterEach(() => {
  cleanup();
});

/** O ancestral mais próximo do elemento que leva a variante, ou null. */
function contemComVariante(elemento: HTMLElement, variante: string): HTMLElement | null {
  let atual = elemento.parentElement;
  while (atual) {
    if (atual.className.split(" ").includes(variante)) return atual;
    atual = atual.parentElement;
  }
  return null;
}

describe("o layout de Contas médicas", () => {
  it("põe o h1, o h2 e o h3 da página dentro do contêiner que os deixa em caixa alta", async () => {
    render(
      await ContasMedicasLayout({
        children: (
          <>
            <h1>Contas médicas</h1>
            <h2>Último envio</h2>
            <h3>Pendências</h3>
          </>
        ),
      }),
    );

    for (const nivel of [1, 2, 3] as const) {
      const titulo = screen.getByRole("heading", { level: nivel });
      expect(contemComVariante(titulo, `[&_h${nivel}]:uppercase`)).not.toBeNull();
    }
  });
});
