/**
 * @vitest-environment jsdom
 */

/**
 * A Página de acompanhamento (issue #1623, PRD #1527, ADR 0086 decisão 7).
 *
 * O manifestante informa protocolo e código (anônimo) ou protocolo e o
 * telefone ou e-mail que deixou (identificado), e vê só o estado em palavras
 * simples, a data da última movimentação e a resposta institucional. A régua
 * do que pode sair (nada de setor, responsável ou anotação) é do servidor, e
 * tem teste em `backend/tests/test_ouvidoria_acompanhamento.py`.
 */

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AcompanharPage from "./page";

let enviados: Record<string, unknown>[] = [];

function servidor(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (_url: string, init?: RequestInit) => {
      enviados.push(JSON.parse(String(init?.body ?? "{}")));
      return { ok: status < 300, status, json: async () => corpo } as Response;
    })
  );
}

beforeEach(() => {
  enviados = [];
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function botao(nome: string | RegExp) {
  return screen.getByRole("button", { name: nome }) as HTMLButtonElement;
}

function escrever(rotulo: string | RegExp, valor: string) {
  fireEvent.change(screen.getByLabelText(rotulo), { target: { value: valor } });
}

describe("o anônimo entra com protocolo e código", () => {
  it("manda o protocolo e o código, e mostra o estado, a data e a resposta", async () => {
    servidor(200, {
      protocolo: "2026-0042",
      estado: "Encerrada",
      ultima_movimentacao: "2026-11-12T15:00:00+00:00",
      resposta: "Conversamos com a equipe e reforçamos o atendimento.",
    });
    render(<AcompanharPage />);

    fireEvent.click(botao(/Fiz anônimo/));
    escrever("Protocolo", " 2026-0042 ");
    escrever("Código de acompanhamento", "K7M2P-Q9RX4");
    fireEvent.click(botao("Consultar"));

    expect(await screen.findByText("Conversamos com a equipe e reforçamos o atendimento.")).toBeTruthy();
    expect(enviados[0]).toEqual({ protocolo: "2026-0042", codigo: "K7M2P-Q9RX4" });
    expect(screen.getByRole("status").textContent).toContain("Encerrada");
    expect(screen.getByText(/12 de novembro de 2026/)).toBeTruthy();
  });
});

describe("o identificado entra com protocolo e contato", () => {
  it("manda o telefone ou e-mail no lugar do código", async () => {
    servidor(200, {
      protocolo: "2026-0042",
      estado: "Em análise",
      ultima_movimentacao: "2026-11-10",
      resposta: null,
    });
    render(<AcompanharPage />);

    fireEvent.click(botao(/Me identifiquei/));
    escrever("Protocolo", "2026-0042");
    escrever("Telefone ou e-mail", "maria@exemplo.com");
    fireEvent.click(botao("Consultar"));

    expect(await screen.findByText(/A resposta aparece aqui quando o caso for encerrado/)).toBeTruthy();
    expect(enviados[0]).toEqual({ protocolo: "2026-0042", contato: "maria@exemplo.com" });
    expect(screen.getByRole("status").textContent).toContain("Em análise");
  });
});

describe("as recusas", () => {
  it("dado que não confere mostra a mensagem do servidor, igual para tudo", async () => {
    servidor(404, { detail: "Não encontramos uma manifestação com esses dados." });
    render(<AcompanharPage />);

    fireEvent.click(botao(/Fiz anônimo/));
    escrever("Protocolo", "2026-9999");
    escrever("Código de acompanhamento", "AAAAA-AAAAA");
    fireEvent.click(botao("Consultar"));

    expect(await screen.findByText("Não encontramos uma manifestação com esses dados.")).toBeTruthy();
  });

  it("tentativas demais pedem para esperar", async () => {
    servidor(429, {});
    render(<AcompanharPage />);

    fireEvent.click(botao(/Fiz anônimo/));
    escrever("Protocolo", "2026-9999");
    escrever("Código de acompanhamento", "AAAAA-AAAAA");
    fireEvent.click(botao("Consultar"));

    expect(await screen.findByText(/Muitas tentativas/)).toBeTruthy();
  });

  it("sem escolher o caminho e sem os dois campos, não consulta", () => {
    servidor(200, {});
    render(<AcompanharPage />);

    expect(botao("Consultar").disabled).toBe(true);
    fireEvent.click(botao(/Fiz anônimo/));
    escrever("Protocolo", "2026-0042");
    expect(botao("Consultar").disabled).toBe(true);
  });
});

describe("a tela explica os estados (regra T8)", () => {
  it("tem a legenda dos quatro estados com o significado", () => {
    render(<AcompanharPage />);

    for (const estado of ["Recebida", "Em análise", "Respondida", "Encerrada"]) {
      expect(screen.getByText(estado)).toBeTruthy();
    }
  });
});
