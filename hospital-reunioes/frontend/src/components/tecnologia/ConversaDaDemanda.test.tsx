/**
 * @vitest-environment jsdom
 */

/**
 * A Conversa da Demanda (issue #1537, PRD #1529, ADR 0083, decisão 8).
 *
 * A área própria, embaixo da conversa com a IA, em que o diretor e os
 * Desenvolvedores trocam mensagens. A menção é por nome, no formato dos
 * comentários de Pendência: "@" abre a lista de quem vê a Demanda, e o
 * clique escreve "@Nome Completo " no texto. Quem decide quem é avisado é o
 * servidor.
 */

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConversaDaDemanda } from "./ConversaDaDemanda";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const URL = "/api/admin/tecnologia/chat/d-1/conversa";

const GUARDADA = {
  mensagens: [
    { id: "m-1", autor: "Diretor do Hospital", texto: "O relatório sumiu de novo.", criado_em: "2026-11-10T10:00:00Z", minha: true },
  ],
  mencionaveis: [
    { id: "P2", nome: "Diretor do Hospital" },
    { id: "P4", nome: "Lucas Sampaio" },
    { id: "P1", nome: "Pedro Vitta" },
  ],
};

type Chamada = { url: string; metodo: string; corpo: unknown };

function montar() {
  const chamadas: Chamada[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const corpo = init?.body ? JSON.parse(String(init.body)) : null;
      chamadas.push({ url, metodo, corpo });
      const resposta =
        metodo === "POST"
          ? { id: "m-2", autor: "Diretor do Hospital", texto: corpo.texto, criado_em: "2026-11-10T10:05:00Z", minha: true }
          : GUARDADA;
      return { ok: true, status: metodo === "POST" ? 201 : 200, json: async () => resposta } as unknown as Response;
    }),
  );
  render(<ConversaDaDemanda demandaId="d-1" token="token-de-teste" />);
  return chamadas;
}

function area() {
  return screen.getByRole("region", { name: "Conversa da Demanda" });
}

describe("A Conversa da Demanda", () => {
  it("mostra as mensagens com quem escreveu e envia uma nova", async () => {
    const chamadas = montar();

    await within(area()).findByText("O relatório sumiu de novo.");
    expect(within(area()).getByText("Diretor do Hospital")).toBeTruthy();

    fireEvent.change(within(area()).getByRole("textbox", { name: "Mensagem para a Conversa" }), {
      target: { value: "Aconteceu de novo agora." },
    });
    fireEvent.click(within(area()).getByRole("button", { name: "Enviar na Conversa" }));

    await within(area()).findByText("Aconteceu de novo agora.");
    expect(chamadas.filter((c) => c.metodo === "POST")).toEqual([
      { url: URL, metodo: "POST", corpo: { texto: "Aconteceu de novo agora." } },
    ]);
  });

  it("o @ abre a lista de quem vê a Demanda e o clique escreve o nome inteiro", async () => {
    const chamadas = montar();
    await within(area()).findByText("O relatório sumiu de novo.");
    const caixa = within(area()).getByRole("textbox", { name: "Mensagem para a Conversa" }) as HTMLTextAreaElement;

    fireEvent.change(caixa, { target: { value: "Olha isso @luc", selectionStart: 14 } });
    fireEvent.click(await within(area()).findByRole("option", { name: "Lucas Sampaio" }));

    expect(caixa.value).toBe("Olha isso @Lucas Sampaio ");
    fireEvent.click(within(area()).getByRole("button", { name: "Enviar na Conversa" }));
    await waitFor(() =>
      expect(chamadas.filter((c) => c.metodo === "POST").map((c) => c.corpo)).toEqual([
        { texto: "Olha isso @Lucas Sampaio" },
      ]),
    );
  });
});
