/**
 * @vitest-environment jsdom
 */

/**
 * A página de acompanhamento da notificação de incidente (issue #1987).
 *
 * Quem notificou sem se identificar entra com o protocolo e o código; quem se
 * identificou, com o protocolo e o e-mail ou telefone. A tela mostra só o
 * estado em palavras simples, e a recusa do servidor é a mesma para todo dado
 * errado. A régua do servidor está em
 * `backend/tests/test_seguranca_do_paciente_notificacoes.py`.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AcompanharNotificacaoPage from "./page";

let enviados: { url: string; corpo: Record<string, unknown> }[] = [];

function servidor(status: number, corpo: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      enviados.push({ url, corpo: JSON.parse(String(init?.body ?? "{}")) });
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

describe("acompanhar a notificação", () => {
  it("tem a linha de orientação no topo e o rodapé", () => {
    servidor(200, {});
    render(<AcompanharNotificacaoPage />);

    expect(screen.getByRole("heading", { level: 1, name: "Acompanhar notificação" })).toBeTruthy();
    expect(screen.getByText("Informe o protocolo e o código, ou o e-mail ou telefone que você deixou.")).toBeTruthy();
    expect(screen.getByText("Notificar não gera punição.")).toBeTruthy();
  });

  it("sem se identificar: manda protocolo e código e mostra só o estado", async () => {
    servidor(200, { protocolo: "NSP-2026-0007", estado: "Em análise" });
    render(<AcompanharNotificacaoPage />);

    fireEvent.click(botao("Notifiquei sem me identificar"));
    escrever("Protocolo", " NSP-2026-0007 ");
    escrever("Código de acompanhamento", "ABCDE-FGHJK");
    fireEvent.click(botao("Consultar"));

    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Em análise"));
    // Depois do estado, as perguntas de esclarecimento, com a mesma chave (issue #1991).
    await waitFor(() => expect(enviados).toHaveLength(2));
    expect(enviados).toEqual([
      {
        url: "/api/nsp/publico/acompanhamento",
        corpo: { protocolo: "NSP-2026-0007", codigo: "ABCDE-FGHJK" },
      },
      {
        url: "/api/nsp/publico/perguntas",
        corpo: { protocolo: "NSP-2026-0007", codigo: "ABCDE-FGHJK" },
      },
    ]);
  });

  it("com o nome: manda protocolo e contato", async () => {
    servidor(200, { protocolo: "NSP-2026-0007", estado: "Recebida" });
    render(<AcompanharNotificacaoPage />);

    fireEvent.click(botao("Notifiquei com o meu nome"));
    escrever("Protocolo", "NSP-2026-0007");
    escrever("E-mail ou telefone", "profissional@hsm.test");
    fireEvent.click(botao("Consultar"));

    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Recebida"));
    expect(enviados[0].corpo).toEqual({ protocolo: "NSP-2026-0007", contato: "profissional@hsm.test" });
  });

  it("dado errado mostra a recusa do servidor", async () => {
    const recusa =
      "Não encontramos uma notificação com esses dados. Confira o protocolo e o código, ou o e-mail ou telefone que você deixou.";
    servidor(404, { detail: recusa });
    render(<AcompanharNotificacaoPage />);

    fireEvent.click(botao("Notifiquei sem me identificar"));
    escrever("Protocolo", "NSP-2026-0007");
    escrever("Código de acompanhamento", "ERRAD-OOOOO");
    fireEvent.click(botao("Consultar"));

    await waitFor(() => expect(screen.getByRole("alert").textContent).toBe(recusa));
    expect(screen.queryByRole("status")).toBeNull();
  });
});

describe("as perguntas de esclarecimento no acompanhamento (issue #1991)", () => {
  const PERGUNTA = "O paciente precisou de transfusão?";

  function servidorComPerguntas(perguntas: string[], depois: string[] = []) {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        enviados.push({ url, corpo: JSON.parse(String(init?.body ?? "{}")) });
        const corpo =
          url === "/api/nsp/publico/acompanhamento"
            ? { protocolo: "NSP-2026-0007", estado: "Recebida" }
            : url === "/api/nsp/publico/perguntas"
              ? { perguntas, aguardando: false }
              : { perguntas: depois };
        return { ok: true, status: 200, json: async () => corpo } as Response;
      })
    );
  }

  async function consultarComContato() {
    render(<AcompanharNotificacaoPage />);
    fireEvent.click(botao("Notifiquei com o meu nome"));
    escrever("Protocolo", "NSP-2026-0007");
    escrever("E-mail ou telefone", "profissional@hsm.test");
    fireEvent.click(botao("Consultar"));
    await waitFor(() => expect(screen.getByText("Recebida")).toBeTruthy());
  }

  it("mostra as perguntas sem resposta e aceita a resposta pelo protocolo e contato", async () => {
    servidorComPerguntas([PERGUNTA]);
    await consultarComContato();

    const bloco = await screen.findByRole("region", { name: "Perguntas do Núcleo" });
    expect(within(bloco).queryByRole("link", { name: "Responder depois" })).toBeNull();
    fireEvent.change(within(bloco).getByLabelText(PERGUNTA), { target: { value: "Sim, duas bolsas." } });
    fireEvent.click(within(bloco).getByRole("button", { name: "Enviar respostas" }));

    await waitFor(() => expect(screen.getByText("Obrigado. A resposta chegou ao Núcleo.")).toBeTruthy());
    expect(enviados.find((e) => e.url === "/api/nsp/publico/respostas")?.corpo).toEqual({
      protocolo: "NSP-2026-0007",
      contato: "profissional@hsm.test",
      respostas: [{ pergunta: PERGUNTA, resposta: "Sim, duas bolsas." }],
    });
    expect(screen.queryByLabelText(PERGUNTA)).toBeNull();
  });

  it("sem pergunta em aberto, a página mostra só o estado", async () => {
    servidorComPerguntas([]);
    await consultarComContato();

    await waitFor(() => expect(enviados.some((e) => e.url === "/api/nsp/publico/perguntas")).toBe(true));
    expect(screen.queryByRole("region", { name: "Perguntas do Núcleo" })).toBeNull();
  });
});
