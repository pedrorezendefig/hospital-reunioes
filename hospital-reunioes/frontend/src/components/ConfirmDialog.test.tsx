/**
 * @vitest-environment jsdom
 */

/**
 * Caixa alta no diálogo de confirmação (ADR 0080, issue #1454).
 *
 * O título e os botões são Texto curto e saem em caixa alta pela regra base.
 * A pergunta do diálogo é frase inteira e fica com maiúscula e minúscula.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { apareceComoFoiEscrito } from "@/lib/caixa-alta";

import { ConfirmDialog } from "./ConfirmDialog";

afterEach(cleanup);

describe("diálogo de confirmação", () => {
  it("título e botões em caixa alta, a pergunta corrida", async () => {
    render(
      <ConfirmDialog
        open
        onClose={() => {}}
        onConfirm={() => {}}
        title="Concluir assim mesmo?"
        description="A reunião ainda tem pendências sem responsável."
        confirmLabel="Concluir"
      />,
    );

    expect(apareceComoFoiEscrito(await screen.findByRole("heading", { name: "Concluir assim mesmo?" }))).toBe(false);
    expect(apareceComoFoiEscrito(screen.getByRole("button", { name: "Concluir" }))).toBe(false);
    expect(apareceComoFoiEscrito(screen.getByText("A reunião ainda tem pendências sem responsável."))).toBe(true);
  });
});
