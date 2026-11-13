/**
 * @vitest-environment jsdom
 */

/**
 * A tela do link do Núcleo de Segurança do Paciente (issue #1621, ADR 0088).
 *
 * O link do email abre sem senha e mostra o caso inteiro ao Núcleo; o botão
 * Recebido pelo NSP confirma, uma vez. O que a resposta carrega em cada caso
 * (o relato no sigiloso, quem manifestou só fora do sigilo e do anonimato) é
 * régua do backend; aqui se prova que a tela mostra o que veio, que abrir não
 * confirma nada e que o clique chama a rota certa.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NucleoPage from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ token: "token-do-nucleo" }),
}));

const RELATO = "Minha mae caiu da cama no quarto 412 e ninguem veio ajudar por meia hora.";

function tela(overrides: Record<string, unknown> = {}) {
  return {
    protocolo: "2026-0007",
    tipo_manifestacao: "denuncia",
    gravidade: "alto",
    sigiloso: true,
    anonimo: false,
    relato_integral: RELATO,
    justificativa_tecnica: "Queda do leito, internacao, madrugada de 24/08.",
    paciente: { nome: "Ana Maria Souza", nascimento: "1948-03-02" },
    profissionais: "Enfermeiro do plantao noturno",
    quarto: "412",
    data_ocorrencia: "2026-08-24",
    periodo: "madrugada",
    hora_aprox: null,
    local_informado: "Internação, Ala 4",
    quem_manifestou: null,
    destinatario_nome: "Dra. Helena",
    prazo: "26/08/2026 às 17:00",
    recebido: false,
    recebido_em: null,
    ...overrides,
  };
}

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

describe("a tela do link do Núcleo", () => {
  it("mostra o relato, a justificativa técnica e o paciente com o nascimento", async () => {
    fetchMock.mockResolvedValue(resposta(200, tela()));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByText(RELATO)).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledWith("/api/ouvidoria-setor/nsp/token-do-nucleo");
    expect(screen.getByText("Queda do leito, internacao, madrugada de 24/08.")).toBeTruthy();
    expect(screen.getByText("Ana Maria Souza")).toBeTruthy();
    expect(screen.getByText("02/03/1948")).toBeTruthy();
    expect(screen.getByText("Enfermeiro do plantao noturno")).toBeTruthy();
    expect(screen.getByText("Internação, Ala 4, quarto 412")).toBeTruthy();
  });

  it("no caso sigiloso diz que quem manifestou não é identificado", async () => {
    fetchMock.mockResolvedValue(resposta(200, tela()));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByText(/Quem manifestou não é identificado/)).toBeTruthy());
  });

  it("no caso comum mostra quem manifestou", async () => {
    fetchMock.mockResolvedValue(resposta(200, tela({ sigiloso: false, quem_manifestou: "Joana da Silva" })));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByText("Joana da Silva")).toBeTruthy());
  });

  it("abrir o link não confirma nada", async () => {
    fetchMock.mockResolvedValue(resposta(200, tela()));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByRole("button", { name: "Recebido pelo NSP" })).toBeTruthy());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("o clique confirma pela rota do Núcleo, sem login", async () => {
    fetchMock
      .mockResolvedValueOnce(resposta(200, tela()))
      .mockResolvedValueOnce(resposta(200, { protocolo: "2026-0007", recebido_em: "2026-08-25T17:00:00+00:00" }));
    render(<NucleoPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Recebido pelo NSP" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Recebido pelo NSP" }));

    await waitFor(() => expect(screen.getByTestId("nucleo-recebido")).toBeTruthy());
    expect(fetchMock).toHaveBeenLastCalledWith("/api/ouvidoria-setor/nsp/token-do-nucleo/recebido", {
      method: "POST",
    });
    expect(screen.queryByRole("button", { name: "Recebido pelo NSP" })).toBeNull();
  });

  it("o caso já recebido não oferece o botão de novo", async () => {
    fetchMock.mockResolvedValue(resposta(200, tela({ recebido: true, recebido_em: "2026-08-25T17:00:00+00:00" })));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByTestId("nucleo-recebido")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Recebido pelo NSP" })).toBeNull();
  });

  it("o segundo clique diz que o Núcleo já confirmou", async () => {
    fetchMock
      .mockResolvedValueOnce(resposta(200, tela()))
      .mockResolvedValueOnce(resposta(410, { detail: "O Núcleo já confirmou o recebimento deste caso." }));
    render(<NucleoPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Recebido pelo NSP" })).toBeTruthy());

    fireEvent.click(screen.getByRole("button", { name: "Recebido pelo NSP" }));

    await waitFor(() => expect(screen.getByText("O Núcleo já confirmou o recebimento deste caso.")).toBeTruthy());
  });

  it("link inválido não mostra caso nenhum", async () => {
    fetchMock.mockResolvedValue(resposta(404, { detail: "Link inválido" }));
    render(<NucleoPage />);

    await waitFor(() => expect(screen.getByText(/Este link não é válido/)).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Recebido pelo NSP" })).toBeNull();
  });
});
