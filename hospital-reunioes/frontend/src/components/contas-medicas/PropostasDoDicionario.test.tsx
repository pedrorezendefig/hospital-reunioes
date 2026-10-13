/**
 * @vitest-environment jsdom
 */

/**
 * As propostas da IA para o dicionário de itens (issue #1135): o termo da
 * prescrição sem par na conta foi uma vez à IA, que propôs o código. A gestão
 * confirma ou rejeita na tela Operadoras. O backend é um dublê por rota; o que
 * se confere é a fiação: o que a tela mostra e o que ela manda.
 */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PropostasDoDicionario } from "./PropostasDoDicionario";

const ROTA = "/api/contas-medicas/dicionario/propostas";

const PROPOSTAS = [
  { id: "p-1", termo: "ENOXAPARINA 40MG/0,4ML SER", codigo_conta: "90030001", descricao_conta: "CLEXANE 40MG/0,4ML" },
  { id: "p-2", termo: "ROCURONIO 10MG/ML", codigo_conta: "90040001", descricao_conta: "ESMERON 10MG/ML" },
];

type Chamada = { url: string; metodo: string; autorizacao: string | undefined };

let chamadas: Chamada[];
let respostaDaDecisao: { status: number; corpo: unknown };

function resposta(status: number, corpo: unknown): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => corpo } as Response;
}

beforeEach(() => {
  chamadas = [];
  respostaDaDecisao = { status: 200, corpo: {} };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const metodo = init?.method ?? "GET";
      const autorizacao = (init?.headers as Record<string, string> | undefined)?.Authorization;
      chamadas.push({ url, metodo, autorizacao });
      if (url === ROTA && metodo === "GET") return resposta(200, { propostas: PROPOSTAS });
      if (metodo === "POST") return resposta(respostaDaDecisao.status, respostaDaDecisao.corpo);
      return resposta(404, { detail: "rota desconhecida no dublê" });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("as propostas da IA para o dicionário", () => {
  it("lista cada termo com o código e a descrição propostos", async () => {
    render(<PropostasDoDicionario token="token-de-teste" />);

    const secao = await screen.findByRole("region", { name: "Propostas da IA para o dicionário" });
    const enoxaparina = await within(secao).findByTestId("proposta-p-1");
    expect(enoxaparina.textContent).toContain("ENOXAPARINA 40MG/0,4ML SER");
    expect(enoxaparina.textContent).toContain("90030001");
    expect(enoxaparina.textContent).toContain("CLEXANE 40MG/0,4ML");
    expect(within(secao).getByTestId("proposta-p-2").textContent).toContain("ROCURONIO 10MG/ML");
    expect(chamadas[0]).toEqual({ url: ROTA, metodo: "GET", autorizacao: "Bearer token-de-teste" });
  });

  it("confirmar e rejeitar mandam a decisão da proposta e tiram a linha da lista", async () => {
    render(<PropostasDoDicionario token="token-de-teste" />);
    const enoxaparina = await screen.findByTestId("proposta-p-1");

    fireEvent.click(within(enoxaparina).getByRole("button", { name: "Confirmar" }));
    await expectSumir("proposta-p-1");
    fireEvent.click(within(screen.getByTestId("proposta-p-2")).getByRole("button", { name: "Rejeitar" }));
    await expectSumir("proposta-p-2");

    expect(chamadas.filter((c) => c.metodo === "POST")).toEqual([
      { url: `${ROTA}/p-1/confirmar`, metodo: "POST", autorizacao: "Bearer token-de-teste" },
      { url: `${ROTA}/p-2/rejeitar`, metodo: "POST", autorizacao: "Bearer token-de-teste" },
    ]);
    expect(screen.getByText("Nenhuma proposta à espera.")).toBeTruthy();
  });

  it("a decisão recusada pelo servidor mostra o motivo e a linha fica", async () => {
    respostaDaDecisao = { status: 409, corpo: { detail: "A proposta não existe ou já foi decidida." } };
    render(<PropostasDoDicionario token="token-de-teste" />);
    const enoxaparina = await screen.findByTestId("proposta-p-1");

    fireEvent.click(within(enoxaparina).getByRole("button", { name: "Confirmar" }));

    expect((await screen.findByRole("alert")).textContent).toContain("A proposta não existe ou já foi decidida.");
    expect(screen.getByTestId("proposta-p-1")).toBeTruthy();
  });
});

async function expectSumir(testId: string) {
  await vi.waitFor(() => expect(screen.queryByTestId(testId)).toBeNull());
}
