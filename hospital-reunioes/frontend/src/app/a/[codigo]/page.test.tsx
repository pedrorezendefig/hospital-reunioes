/**
 * @vitest-environment jsdom
 */

/**
 * O endereço curto do cartaz, `/a/{código}` (issue #1617, ADR 0086 decisão 5).
 *
 * É o que o cartaz A4 imprime e o que o QR carrega. Hoje ele abre a
 * Manifestação guiada com o ponto (issue #1620); a fatia da tela de nota troca
 * o destino. O que só existe aqui, e que a suíte do backend não vê:
 *
 * * o código da URL é o que vai no envio, e é com ele que o servidor grava a
 *   origem do caso (ponto ativo) ou o deixa sem origem (ponto aposentado);
 * * o lugar do passo "Quando e onde" chega preenchido com o nome público do
 *   ponto, que o servidor devolve, e nunca com o nome interno do setor.
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

const LOCAIS = [
  { nome: "Centro Médico", ala_internacao: false },
  { nome: "Emergência adulta", ala_internacao: false },
];

let consultas: string[] = [];
let enviados: Record<string, unknown>[] = [];

/** O servidor: a rota pública do ponto responde `cartaz` (ou 404, quando o
 *  ponto está aposentado), a de locais devolve a lista, e a de manifestações
 *  devolve o recibo. */
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
      if (url.includes("/publico/locais")) {
        return { ok: true, status: 200, json: async () => ({ locais: LOCAIS }) } as Response;
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

function botao(nome: string | RegExp) {
  return screen.getByRole("button", { name: nome }) as HTMLButtonElement;
}

/** Do passo 1 até o "Quando e onde", de quem pediu anonimato. */
function ateOQuandoEOnde() {
  fireEvent.click(botao(/Anônimo/));
  fireEvent.click(botao("Continuar"));
  fireEvent.click(botao("Sobre mim"));
  fireEvent.click(botao("Continuar"));
}

function onde() {
  return screen.getByLabelText("Onde foi?") as HTMLSelectElement;
}

describe("o endereço curto do cartaz (critério 4)", () => {
  it("de ponto ativo, o lugar chega preenchido com o nome público e o código vai no envio", async () => {
    servidor({ nome_publico: "Emergência adulta" });
    render(<EnderecoCurtoDoCartaz />);
    await waitFor(() => expect(consultas).toEqual(["/api/ouvidoria/publico/pontos/AB2CD3"]));

    ateOQuandoEOnde();

    await waitFor(() => expect(onde().value).toBe("Emergência adulta"));
    fireEvent.click(botao("Tarde"));
    fireEvent.click(botao("Continuar"));
    fireEvent.change(screen.getByLabelText("Seu relato"), {
      target: { value: "Esperei duas horas." },
    });
    fireEvent.click(botao("Uma resposta"));
    fireEvent.click(botao("Continuar"));
    fireEvent.click(botao(/Enviar manifestação/));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ p: "AB2CD3", local_informado: "Emergência adulta" });
  });

  it("o lugar preenchido pelo cartaz pode ser trocado", async () => {
    servidor({ nome_publico: "Emergência adulta" });
    render(<EnderecoCurtoDoCartaz />);
    ateOQuandoEOnde();
    await waitFor(() => expect(onde().value).toBe("Emergência adulta"));

    fireEvent.change(onde(), { target: { value: "Centro Médico" } });

    expect(onde().value).toBe("Centro Médico");
  });

  it("de ponto aposentado, o lugar chega em branco e o formulário segue", async () => {
    servidor(null);
    render(<EnderecoCurtoDoCartaz />);
    await waitFor(() => expect(consultas).toHaveLength(1));

    ateOQuandoEOnde();

    expect(onde().value).toBe("");
  });

  it("de cartaz sem nome público, não oferece nem escolhe o rótulo do ponto", async () => {
    // Sem nome público, o servidor devolve o rótulo do ponto, que não está na
    // lista de locais. No anônimo, "Poltrona 12" reidentifica (issue #375,
    // item 12): o lugar fica para a pessoa escolher.
    servidor({ nome_publico: "Poltrona 12" });
    render(<EnderecoCurtoDoCartaz />);
    await waitFor(() => expect(consultas).toHaveLength(1));

    ateOQuandoEOnde();
    await screen.findByRole("option", { name: "Centro Médico" });

    expect(onde().value).toBe("");
    expect(screen.queryByRole("option", { name: "Poltrona 12" })).toBeNull();
    // O select em branco não basta: o estado escondido por trás dele é o que
    // vai no envio. Com data e período, só falta o lugar que a pessoa escolhe.
    fireEvent.click(botao("Tarde"));
    expect(botao("Continuar").disabled).toBe(true);
    fireEvent.change(onde(), { target: { value: "Centro Médico" } });
    fireEvent.click(botao("Continuar"));
    fireEvent.change(screen.getByLabelText("Seu relato"), {
      target: { value: "Esperei duas horas." },
    });
    fireEvent.click(botao("Uma resposta"));
    fireEvent.click(botao("Continuar"));
    fireEvent.click(botao(/Enviar manifestação/));

    await waitFor(() => expect(enviados).toHaveLength(1));
    expect(enviados[0]).toMatchObject({ local_informado: "Centro Médico" });
  });

  it("nunca preenche com o nome do setor", async () => {
    // Um servidor antigo devolvia o setor. A página só lê o nome público:
    // sem ele, o lugar fica para a pessoa escolher.
    servidor({ setor: "Recepção", ponto: "Poltrona 12" });
    render(<EnderecoCurtoDoCartaz />);
    await waitFor(() => expect(consultas).toHaveLength(1));

    ateOQuandoEOnde();

    expect(onde().value).toBe("");
    expect(screen.queryByText("Recepção")).toBeNull();
  });
});
