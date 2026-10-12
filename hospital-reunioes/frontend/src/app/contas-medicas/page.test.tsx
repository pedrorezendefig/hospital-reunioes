/**
 * @vitest-environment jsdom
 */

/**
 * A tela de contas de Contas médicas, na fundação do módulo (issue #1114).
 *
 * Ainda não existe envio: a fila abre vazia e diz isso com todas as letras, em
 * vez de uma tela em branco que pareceria defeito.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import ContasMedicasPage from "./page";

afterEach(() => {
  cleanup();
});

describe("a tela de contas sem nenhuma conta", () => {
  it("abre com o título do módulo e a fila vazia", () => {
    render(<ContasMedicasPage />);

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Contas médicas");
    const fila = screen.getByRole("region", { name: "Fila de contas" });
    expect(fila.textContent).toContain("Nenhuma conta enviada ainda");
  });
});
