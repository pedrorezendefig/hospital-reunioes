/**
 * @vitest-environment jsdom
 */

/**
 * Caixa alta na tela pública do aceite interno da ata (ADR 0080, issue #1454).
 *
 * Quem abre o link não tem senha, e a regra base vale aqui como em qualquer
 * tela. O título é o nome da reunião, digitado pela equipe, e a frase de
 * concordância é um rótulo com frase inteira: os dois saem como foram escritos.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apareceComoFoiEscrito } from "@/lib/caixa-alta";

import AceiteInternoPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "tok-aceite" }),
}));

const DADOS = {
  reuniao: { titulo: "Comitê de Ética de novembro", tipo: null, data: "2026-11-05", hora_inicio: null },
  signatario: { nome: "Maria da Silva" },
  ata: {},
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({ ok: true, status: 200, json: async () => DADOS }) as unknown as Response),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("aceite interno da ata, tela sem senha", () => {
  it("o nome da reunião no título aparece como foi escrito", async () => {
    render(<AceiteInternoPage />);

    const titulo = await screen.findByRole("heading", { name: "Comitê de Ética de novembro" });
    expect(apareceComoFoiEscrito(titulo)).toBe(true);
  });

  it("a frase de concordância do rótulo fica com maiúscula e minúscula", async () => {
    render(<AceiteInternoPage />);

    const frase = await screen.findByText(/Li a ata completa acima/);
    expect(frase.closest("label")).not.toBeNull();
    expect(apareceComoFoiEscrito(frase)).toBe(true);
  });
});
