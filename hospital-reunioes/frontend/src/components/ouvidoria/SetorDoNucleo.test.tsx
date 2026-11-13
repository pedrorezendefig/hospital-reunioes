/**
 * @vitest-environment jsdom
 */

/**
 * Qual setor é o Núcleo de Segurança do Paciente (issue #1621, ADR 0088,
 * decisão 3). O Núcleo é um setor da taxonomia como os outros, e a
 * configuração da Ouvidoria só diz qual. Sem ele escolhido, o envio ao Núcleo
 * é recusado pelo servidor com a frase que manda escolher aqui.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SetorDoNucleo } from "./SetorDoNucleo";

const fetchMock = vi.fn();

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

function montar(atual: string) {
  fetchMock.mockImplementation(async (_url: string, init?: RequestInit) => {
    if (init?.method === "PUT") {
      const { setor } = JSON.parse(init.body as string);
      return { ok: true, json: async () => ({ setor }) };
    }
    return { ok: true, json: async () => ({ setor: atual }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<SetorDoNucleo token="t" setores={["Recepcao", "Nucleo de Seguranca do Paciente"]} />);
}

describe("o setor do Núcleo na configuração", () => {
  it("mostra o setor escolhido", async () => {
    montar("Nucleo de Seguranca do Paciente");

    await waitFor(() =>
      expect((screen.getByLabelText(/Setor do Núcleo/) as HTMLSelectElement).value).toBe(
        "Nucleo de Seguranca do Paciente"
      )
    );
  });

  it("sem setor escolhido, avisa que o envio ao Núcleo fica travado", async () => {
    montar("");

    await waitFor(() => expect(screen.getByText(/Enquanto nenhum setor for escolhido/)).toBeTruthy());
  });

  it("escolher e salvar grava pela rota da configuração", async () => {
    montar("");
    await waitFor(() => expect(screen.getByText(/Enquanto nenhum setor for escolhido/)).toBeTruthy());

    fireEvent.change(screen.getByLabelText(/Setor do Núcleo/), {
      target: { value: "Nucleo de Seguranca do Paciente" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar setor do Núcleo" }));

    await waitFor(() => expect(screen.getByText(/Setor do Núcleo salvo/)).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith("/api/ouvidoria/nucleo", {
      method: "PUT",
      headers: { Authorization: "Bearer t", "Content-Type": "application/json" },
      body: JSON.stringify({ setor: "Nucleo de Seguranca do Paciente" }),
    });
  });
});
