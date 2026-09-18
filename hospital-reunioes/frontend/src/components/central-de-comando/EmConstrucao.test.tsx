/**
 * @vitest-environment jsdom
 */

/**
 * As telas da Central que ainda não chegaram (issue #814).
 *
 * Objetivos, Dados do Google e Instagram entram no menu desde já, para a
 * navegação da seção fechar; até a fatia de cada uma, o que abre é um aviso
 * simples de "em construção nesta migração", com o nome da tela, e nenhum
 * número inventado. A seção inteira está dormente em produção.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { Target } from "lucide-react";
import { afterEach, describe, expect, it } from "vitest";

import { EmConstrucao } from "./EmConstrucao";

afterEach(cleanup);

describe("EmConstrucao", () => {
  it("diz qual tela é e que ela está em construção nesta migração", () => {
    render(<EmConstrucao titulo="Objetivos" icone={Target} descricao="Os Objetivos da diretoria." />);

    expect(screen.getByRole("heading", { level: 1, name: "Objetivos" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/em construção nesta migração/i);
  });

  it("não mostra número nenhum", () => {
    render(<EmConstrucao titulo="Instagram" icone={Target} descricao="Seguidores e alcance." />);

    expect(screen.queryByText(/\d/)).toBeNull();
  });
});
