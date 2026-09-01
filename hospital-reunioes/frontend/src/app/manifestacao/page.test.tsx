/**
 * @vitest-environment jsdom
 */

/**
 * O formulário público da Ouvidoria, na tela (issue #473, PRD #467).
 *
 * O que o cartaz do ponto de escuta promete só existe se estiver DESENHADO
 * aqui: as quatro naturezas, o elogio na frente e a escolha que não prende
 * ninguém (RN-88). A régua do envio já tem teste próprio em
 * `lib/ouvidoria/publico.ts`; o que só existe nesta página, e que hoje só um
 * humano olhando a tela pegaria se sumisse, é:
 *
 * * a ordem dos quatro botões, que é a promessa do papel;
 * * a escolha ser opcional E desmarcável, para quem clicou por engano não ficar
 *   preso a uma natureza que não é a dele;
 * * o protocolo continuar aparecendo na tela depois do envio, que é o recibo de
 *   quem manifestou.
 */

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ManifestacaoPage from "./page";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
}));

const RECIBO = {
  protocolo: "2026-0042",
  data_abertura: "2026-09-01",
  prazo_resposta: "2026-09-08",
  status: "em_classificacao",
};

let enviados: unknown[] = [];

beforeEach(() => {
  enviados = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      enviados.push(JSON.parse(String(init?.body ?? "{}")));
      return { ok: true, status: 201, json: async () => RECIBO } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function escrever(texto: string) {
  fireEvent.change(screen.getByLabelText("O que aconteceu?"), { target: { value: texto } });
}

/** Os botões de natureza, e só eles: o de enviar não é alternável. */
function botoesDeNatureza() {
  return screen
    .getAllByRole("button")
    .filter((botao) => botao.hasAttribute("aria-pressed"));
}

describe("o seletor de natureza do formulário público", () => {
  it("mostra as quatro naturezas do cartaz, com o elogio primeiro", () => {
    render(<ManifestacaoPage />);

    expect(botoesDeNatureza().map((b) => b.textContent)).toEqual([
      "Elogio",
      "Reclamação",
      "Sugestão",
      "Informação",
    ]);
  });

  it("deixa enviar sem escolher natureza nenhuma", async () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");

    const enviar = screen.getByRole("button", { name: /enviar manifestação/i }) as HTMLButtonElement;
    expect(enviar.disabled).toBe(false);

    fireEvent.click(enviar);

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).not.toHaveProperty("natureza_informada");
  });

  it("leva a natureza escolhida no envio", async () => {
    render(<ManifestacaoPage />);
    escrever("Fui muito bem atendida na recepção.");

    fireEvent.click(screen.getByRole("button", { name: "Elogio" }));
    expect(screen.getByRole("button", { name: "Elogio" }).getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(screen.getByRole("button", { name: /enviar manifestação/i }));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ natureza_informada: "elogio" });
  });

  it("desmarca a natureza quando a pessoa clica de novo na mesma", async () => {
    render(<ManifestacaoPage />);
    escrever("Esperei duas horas na recepção.");

    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));
    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));

    expect(screen.getByRole("button", { name: "Reclamação" }).getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: /enviar manifestação/i }));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).not.toHaveProperty("natureza_informada");
  });

  it("troca a escolha quando a pessoa clica em outra natureza", async () => {
    render(<ManifestacaoPage />);
    escrever("Sugiro senhas por ordem de chegada.");

    fireEvent.click(screen.getByRole("button", { name: "Reclamação" }));
    fireEvent.click(screen.getByRole("button", { name: "Sugestão" }));

    expect(screen.getByRole("button", { name: "Reclamação" }).getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: /enviar manifestação/i }));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ natureza_informada: "sugestao" });
  });

  it("continua mostrando o protocolo na tela depois do envio", async () => {
    render(<ManifestacaoPage />);
    escrever("Fui muito bem atendida na recepção.");

    fireEvent.click(screen.getByRole("button", { name: "Elogio" }));
    fireEvent.click(screen.getByRole("button", { name: /enviar manifestação/i }));

    expect(await screen.findByText("2026-0042")).toBeTruthy();
  });
});
