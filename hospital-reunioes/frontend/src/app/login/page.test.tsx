/**
 * @vitest-environment jsdom
 */

/**
 * A fiação do destino na tela de login (issue #477, RN-54).
 *
 * A régua tem teste próprio em `lib/login/destino`. O que só existe aqui é a
 * ponte entre a query string da URL e o formulário: sem o campo escondido, o
 * `?redirect=` chegaria na tela e morreria nela, porque o server action só
 * enxerga o que o formulário mandar.
 *
 * A tela também não repassa destino de fora do site. Não é a defesa principal
 * (essa é a da action, que mede de novo), é higiene: não montar o campo evita
 * que o valor hostil viaje mais um trecho.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const parametros = { atual: new URLSearchParams() };

vi.mock("next/navigation", () => ({
  useSearchParams: () => parametros.atual,
}));

vi.mock("@/app/actions/auth", () => ({
  login: vi.fn(),
}));

import LoginPage from "./page";

function telaCom(query: string) {
  parametros.atual = new URLSearchParams(query);
  return render(<LoginPage />).container;
}

function campoDeDestino(container: HTMLElement): HTMLInputElement | null {
  return container.querySelector<HTMLInputElement>('input[name="redirect"]');
}

afterEach(() => {
  cleanup();
});

describe("o destino na tela de login", () => {
  it("carrega o destino interno para dentro do formulário", () => {
    const container = telaCom("redirect=%2Fouvidoria%2Fm%2F2026-0012");

    expect(campoDeDestino(container)?.value).toBe("/ouvidoria/m/2026-0012");
  });

  it("não carrega destino de fora do site", () => {
    expect(campoDeDestino(telaCom("redirect=https%3A%2F%2Fevil.com"))).toBeNull();
    cleanup();
    expect(campoDeDestino(telaCom("redirect=%2F%2Fevil.com"))).toBeNull();
  });

  it("não carrega campo nenhum quando a URL não traz destino", () => {
    expect(campoDeDestino(telaCom(""))).toBeNull();
  });

  it("continua sendo a tela de login", () => {
    // Controle positivo: se a renderização quebrasse, os testes de cima ficariam
    // verdes por motivo errado, já que "não achei o campo" é o esperado deles.
    const container = telaCom("");

    expect(container.querySelector('input[name="email"]')).not.toBeNull();
    expect(container.querySelector('input[name="password"]')).not.toBeNull();
  });
});

/**
 * A identidade na porta de entrada (issue #491, PRD #471, D-17).
 *
 * A tela de login é onde todo mundo passa, inclusive quem só usa POPs ou
 * Ouvidoria. Enquanto ela convidar para um "painel de gestão de reuniões", o
 * sistema se apresenta pelo nome do primeiro módulo que teve.
 */
describe("a identidade na tela de login", () => {
  it("convida para a plataforma de gestão do hospital", () => {
    expect(telaCom("").textContent).toContain(
      "Acesse a plataforma de gestão do hospital",
    );
  });

  it("apresenta a plataforma inteira, não só as atas", () => {
    const texto = telaCom("").textContent ?? "";

    expect(texto).toContain(
      "A plataforma de gestão do Hospital São Matheus: reuniões, POPs e Ouvidoria.",
    );
    expect(texto).not.toMatch(
      /Gestão de Atas|gestão de reuniões|gestão automatizada de atas|Hospital Reuniões/i,
    );
  });
});
