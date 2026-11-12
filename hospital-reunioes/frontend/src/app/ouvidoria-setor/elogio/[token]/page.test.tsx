/**
 * @vitest-environment jsdom
 */

/**
 * A tela do botão Elogio recebido (issue #1618, ADR 0088, decisão 2).
 *
 * O link do email abre esta tela, e só o botão dela confirma: leitor de email
 * que abre link sozinho para conferir se é seguro não pode gastar o uso único.
 * A régua do uso único é do backend (`test_ouvidoria_elogio_ciencia.py`); aqui
 * se prova que a tela não confirma nada ao abrir, chama a rota certa no clique
 * e diz ao responsável o que o servidor respondeu.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ElogioRecebidoPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "token-do-elogio" }),
}));

const fetchMock = vi.fn();

function resposta(status: number, corpo: unknown) {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo };
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("a tela do botão Elogio recebido", () => {
  it("abrir o link não confirma nada", () => {
    render(<ElogioRecebidoPage />);

    expect(screen.getByRole("button", { name: "Elogio recebido" })).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("o clique confirma pela rota do elogio, sem login", async () => {
    fetchMock.mockResolvedValue(
      resposta(200, { protocolo: "2026-0042", setor: "Enfermagem", confirmado_em: "2026-09-01T12:00:00Z" })
    );
    render(<ElogioRecebidoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Elogio recebido" }));

    await waitFor(() => expect(screen.getByTestId("elogio-confirmado")).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith("/api/ouvidoria-setor/elogio/token-do-elogio/recebido", {
      method: "POST",
    });
    expect(screen.getByText("2026-0042")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Elogio recebido" })).toBeNull();
  });

  it("o link já usado mostra a frase do servidor e some com o botão", async () => {
    fetchMock.mockResolvedValue(
      resposta(410, { detail: "Este elogio já foi confirmado. Obrigado por compartilhar com a equipe." })
    );
    render(<ElogioRecebidoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Elogio recebido" }));

    await waitFor(() =>
      expect(
        screen.getByText("Este elogio já foi confirmado. Obrigado por compartilhar com a equipe.")
      ).toBeTruthy()
    );
    expect(screen.queryByRole("button", { name: "Elogio recebido" })).toBeNull();
  });

  it("o link que não existe diz para conferir o endereço", async () => {
    fetchMock.mockResolvedValue(resposta(404, { detail: "Link inválido" }));
    render(<ElogioRecebidoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Elogio recebido" }));

    await waitFor(() =>
      expect(
        screen.getByText(
          "Este link não é válido. Confira se o endereço veio completo no email da Ouvidoria."
        )
      ).toBeTruthy()
    );
  });

  it("a instabilidade do sistema deixa o botão para tentar de novo", async () => {
    fetchMock.mockResolvedValue(resposta(503, { detail: "O sistema está instável agora." }));
    render(<ElogioRecebidoPage />);

    fireEvent.click(screen.getByRole("button", { name: "Elogio recebido" }));

    await waitFor(() => expect(screen.getByText("O sistema está instável agora.")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Elogio recebido" })).toBeTruthy();
  });
});
