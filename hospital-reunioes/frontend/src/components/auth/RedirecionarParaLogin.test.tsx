/**
 * @vitest-environment jsdom
 */

/**
 * O encaminhamento do destino original para o login (issue #477, RN-54).
 *
 * A régua tem teste próprio em `lib/login/destino`. O que se prova aqui é que
 * o componente lê a URL de VERDADE em que a pessoa estava, e não um caminho
 * fixo: trocar a chamada por `router.replace("/login")` apagaria a
 * funcionalidade inteira sem derrubar nenhum outro teste da casa.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
}));

import { RedirecionarParaLogin } from "./RedirecionarParaLogin";

function estandoEm(url: string) {
  window.history.replaceState({}, "", url);
  render(<RedirecionarParaLogin />);
}

beforeEach(() => {
  replace.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("para onde manda quem caiu deslogado numa tela da Ouvidoria", () => {
  it("manda para o login carregando o caminho em que a pessoa estava", () => {
    estandoEm("/ouvidoria/m/2026-0012");

    expect(replace).toHaveBeenCalledWith("/login?redirect=%2Fouvidoria%2Fm%2F2026-0012");
  });

  it("leva junto a query string da tela", () => {
    estandoEm("/ouvidoria?status=em_classificacao");

    expect(replace).toHaveBeenCalledWith(
      "/login?redirect=%2Fouvidoria%3Fstatus%3Dem_classificacao"
    );
  });

  it("oferece o caminho do login por escrito, para quem não tem o script", () => {
    // A navegação é do cliente. Sem uma saída visível, uma falha de script
    // deixaria a pessoa numa tela em branco sem nada para clicar.
    estandoEm("/ouvidoria/painel");

    expect(screen.getByRole("link", { name: /login/i }).getAttribute("href")).toBe("/login");
  });
});
