/**
 * @vitest-environment jsdom
 */

/**
 * As duas páginas públicas da notificação de incidente (issue #1987): a origem
 * gravada vem da página que a pessoa abriu. O QR do cartaz aponta para
 * `/notificar/qr` e grava `qr`; o endereço `/notificar` grava `endereco`. O
 * teste do formulário recebe a porta pronta; aqui se confere a ligação entre a
 * página e a porta, montando a página inteira.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import NotificarPage from "./page";
import NotificarPeloQrPage from "./qr/page";

vi.mock("@/lib/supabase/client", () => ({
  createClient: () => ({ auth: { getSession: async () => ({ data: { session: null } }) } }),
}));

let envios: { url: string; corpo: Record<string, unknown> }[] = [];

beforeEach(() => {
  envios = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "/api/nsp/publico/setores") {
        return { ok: true, status: 200, json: async () => ({ setores: [{ id: "setor-uti", nome: "UTI Adulto" }] }) } as Response;
      }
      if (url === "/api/nsp/publico/perguntas") {
        // A confirmação pergunta se o agente propôs perguntas (issue #1991).
        return { ok: true, status: 200, json: async () => ({ perguntas: [], aguardando: false }) } as Response;
      }
      envios.push({ url, corpo: JSON.parse(String(init?.body ?? "{}")) });
      return {
        ok: true,
        status: 201,
        json: async () => ({ protocolo: "NSP-2026-0009", criado_em: null, codigo_acompanhamento: "ABCDE-FGHJK" }),
      } as Response;
    })
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function botao(nome: string) {
  return screen.getByRole("button", { name: nome });
}

function escolher(grupo: string, opcao: string) {
  fireEvent.click(within(screen.getByRole("group", { name: grupo })).getByRole("button", { name: opcao }));
}

async function notificarSemSeIdentificar() {
  fireEvent.change(screen.getByLabelText("O que aconteceu"), { target: { value: "Queda no banheiro." } });
  fireEvent.click(botao("Continuar"));
  await waitFor(() => expect(screen.getByRole("option", { name: "UTI Adulto" })).toBeTruthy());
  fireEvent.change(screen.getByLabelText("Setor"), { target: { value: "setor-uti" } });
  escolher("Turno", "Tarde");
  fireEvent.click(botao("Continuar"));
  escolher("O incidente chegou ao paciente?", "Não chegou");
  fireEvent.click(botao("Continuar"));
  fireEvent.click(botao("Sem me identificar"));
  fireEvent.click(botao("Enviar notificação"));
  await waitFor(() => expect(screen.getByText("NSP-2026-0009")).toBeTruthy());
}

describe("a origem vem da página aberta", () => {
  it("/notificar/qr, para onde o QR do cartaz aponta, grava a origem QR", async () => {
    render(<NotificarPeloQrPage />);
    await notificarSemSeIdentificar();

    expect(envios).toHaveLength(1);
    expect(envios[0].url).toBe("/api/nsp/publico/notificacoes");
    expect(envios[0].corpo.origem).toBe("qr");
  });

  it("/notificar, o endereço, grava a origem endereço", async () => {
    render(<NotificarPage />);
    await notificarSemSeIdentificar();

    expect(envios).toHaveLength(1);
    expect(envios[0].url).toBe("/api/nsp/publico/notificacoes");
    expect(envios[0].corpo.origem).toBe("endereco");
  });
});
