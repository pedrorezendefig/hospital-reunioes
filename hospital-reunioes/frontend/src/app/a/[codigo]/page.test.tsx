/**
 * @vitest-environment jsdom
 */

/**
 * O endereço curto do cartaz, `/a/{código}` (issue #1617, ADR 0086 decisão 5).
 *
 * É o que o cartaz A4 imprime e o que o QR carrega. Nesta fatia ele abre o
 * formulário público com o ponto; a fatia da tela de nota troca o destino. O
 * que só existe aqui, e que a suíte do backend não vê:
 *
 * * o código da URL é o que vai no envio, e é com ele que o servidor grava a
 *   origem do caso (ponto ativo) ou o deixa sem origem (ponto aposentado);
 * * a página mostra o nome público do ponto, que o servidor devolve, e nunca o
 *   nome interno do setor.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import EnderecoCurtoDoCartaz from "./page";

vi.mock("next/navigation", () => ({
  useParams: () => ({ codigo: "AB2CD3" }),
  useSearchParams: () => new URLSearchParams(),
}));

const RECIBO = {
  protocolo: "2026-0042",
  data_abertura: "2026-09-01",
  prazo_resposta: "2026-09-08",
  status: "em_classificacao",
};

let consultas: string[] = [];
let enviados: Record<string, unknown>[] = [];

/** O servidor: a rota pública do ponto responde `cartaz` (ou 404, quando o
 *  ponto está aposentado), e a de manifestações devolve o recibo. */
function servidor(cartaz: Record<string, unknown> | null) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes("/publico/pontos/")) {
        consultas.push(url);
        return (cartaz
          ? { ok: true, status: 200, json: async () => cartaz }
          : { ok: false, status: 404, json: async () => ({}) }) as Response;
      }
      enviados.push(JSON.parse(String(init?.body ?? "{}")));
      return { ok: true, status: 201, json: async () => RECIBO } as Response;
    })
  );
}

beforeEach(() => {
  consultas = [];
  enviados = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function enviarUmRelato() {
  fireEvent.change(screen.getByLabelText("O que aconteceu?"), {
    target: { value: "Esperei duas horas na recepção." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sobre mim" }));
  fireEvent.click(screen.getByRole("button", { name: /enviar manifestação/i }));
  await waitFor(() => expect(enviados).toHaveLength(1));
}

describe("o endereço curto do cartaz", () => {
  it("de ponto ativo, abre o formulário com o nome público do ponto e leva o código no envio", async () => {
    servidor({ nome_publico: "Emergência adulta" });

    render(<EnderecoCurtoDoCartaz />);

    expect(await screen.findByText("Emergência adulta")).toBeTruthy();
    expect(consultas).toEqual(["/api/ouvidoria/publico/pontos/AB2CD3"]);

    await enviarUmRelato();
    expect(enviados[0]).toMatchObject({ p: "AB2CD3" });
  });

  it("de ponto aposentado, abre o formulário sem origem nenhuma na tela", async () => {
    servidor(null);

    render(<EnderecoCurtoDoCartaz />);

    await waitFor(() => expect(consultas).toHaveLength(1));
    expect(screen.queryByText(/Você leu o QR/)).toBeNull();
    // O formulário continua de pé: ninguém parado na frente de um cartaz fica
    // sem canal (ADR 0036, decisão 6).
    await enviarUmRelato();
    expect(screen.queryByText(/Você leu o QR/)).toBeNull();
  });

  it("mostra o nome que o servidor devolve, e não o nome do setor", async () => {
    // Um servidor antigo devolvia o setor. A página só lê o nome público:
    // sem ele, não mostra origem nenhuma.
    servidor({ setor: "Recepção", ponto: "Poltrona 12" });

    render(<EnderecoCurtoDoCartaz />);

    await waitFor(() => expect(consultas).toHaveLength(1));
    expect(screen.queryByText("Recepção")).toBeNull();
    expect(screen.queryByText(/Você leu o QR/)).toBeNull();
  });
});
